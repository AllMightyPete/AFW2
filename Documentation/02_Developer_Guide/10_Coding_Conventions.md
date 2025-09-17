# Developer Guide: Coding Conventions

This document outlines the coding conventions and general practices followed within the Asset Processor Tool codebase. Adhering to these conventions helps maintain consistency and readability.

## General Principles

*   **Readability:** Code should be easy to read and understand. Use clear variable and function names.
*   **Consistency:** Follow existing patterns and styles within the codebase.
*   **Maintainability:** Write code that is easy to modify and extend.
*   **Explicitness:** Be explicit rather than implicit.

## Specific Conventions

*   **Object-Oriented Programming (OOP):** The codebase heavily utilizes classes to structure the application logic (e.g., `AssetProcessor`, `Configuration`, `MainWindow`, various Handlers). Follow standard OOP principles.
*   **Type Hinting:** Use Python type hints throughout the code to indicate the expected types of function arguments, return values, and variables. This improves code clarity and allows for static analysis.
*   **Logging:** Use the standard Python `logging` module for all output messages (information, warnings, errors, debug). Avoid using `print()` for application output. Configure log levels appropriately. The GUI uses a custom `QtLogHandler` to integrate logging with the UI.
*   **Error Handling:** Use standard `try...except` blocks to handle potential errors gracefully. Define and use custom exceptions (e.g., `ConfigurationError`, `AssetProcessingError`) for specific error conditions within the application logic. Log exceptions with `exc_info=True` to include traceback information.
*   **Parallelism:** When implementing CPU-bound tasks that can be run concurrently, use `concurrent.futures.ProcessPoolExecutor` as demonstrated in `main.py` and `gui/processing_handler.py`. Ensure that shared state is handled correctly (e.g., by instantiating necessary objects within worker processes).
*   **GUI Development (`PySide6`):**
    *   Use Qt's signals and slots mechanism for communication between objects, especially across threads.
    *   Run long-running or blocking tasks in separate `QThread`s to keep the main UI thread responsive.
    *   Perform UI updates only from the main UI thread.
*   **Configuration:** Core application settings are defined in `config/app_settings.json`. Supplier-specific rules are managed in JSON files within the `Presets/` directory. The `Configuration` class (`configuration.py`) is responsible for loading `app_settings.json` and merging it with the selected preset file.
*   **File Paths:** Use `pathlib.Path` objects for handling file system paths. Avoid using string manipulation for path joining or parsing.
*   **Docstrings:** Write clear and concise docstrings for modules, classes, methods, and functions, explaining their purpose, arguments, and return values.
*   **Comments:** Use comments to explain complex logic or non-obvious parts of the code. Avoid obsolete comments (e.g., commented-out old code) and redundant comments (e.g., comments stating the obvious, like `# Import module` or `# Initialize variable`). The goal is to maintain clarity while minimizing unnecessary token usage for LLM tools.
*   **Imports:** Organize imports at the top of the file, grouped by standard library, third-party libraries, and local modules.
*   **Naming:**
    *   Use `snake_case` for function and variable names.
    *   Use `PascalCase` for class names.
    *   Use `UPPER_CASE` for constants.
    *   Use a leading underscore (`_`) for internal or "protected" methods/attributes.

## Terminology and Data Standards

To ensure consistency and clarity across the codebase, particularly concerning asset and file classifications, the following standards must be adhered to. These primarily revolve around definitions stored in `config/app_settings.json`.

### `FILE_TYPE_DEFINITIONS`

`FILE_TYPE_DEFINITIONS` in `config/app_settings.json` is the **single source of truth** for all file type identifiers used within the application.

*   **`FileRule.item_type` and `FileRule.item_type_override`**: When defining or interpreting `SourceRule` objects (and their constituent `FileRule` instances), the `item_type` and `item_type_override` attributes **must** always use a key directly from `FILE_TYPE_DEFINITIONS`.
    *   Example: `file_rule.item_type = "MAP_COL"` (for a color map) or `file_rule.item_type = "MODEL_FBX"` (for an FBX model).

*   **`standard_type` Property**: Each entry in `FILE_TYPE_DEFINITIONS` includes a `standard_type` property. This provides a common, often abbreviated, alias for the file type.
    *   Example: `FILE_TYPE_DEFINITIONS["MAP_COL"]["standard_type"]` might be `"COL"`.
    *   Example: `FILE_TYPE_DEFINITIONS["MAP_NORM_GL"]["standard_type"]` might be `"NRM"`.

*   **Removal of `STANDARD_MAP_TYPES`**: The global constant `STANDARD_MAP_TYPES` (previously in `config.py`) has been **removed**. Standard map type aliases (e.g., "COL", "NRM", "RGH") are now derived dynamically from the `standard_type` property of the relevant entry in `FILE_TYPE_DEFINITIONS`.

*   **`map_type` Usage**:
    *   **Filename Tokens**: When used as a token in output filename patterns (e.g., `[maptype]`), `map_type` is typically derived from the `standard_type` of the file's effective `item_type`. It may also include a variant suffix if applicable (e.g., "COL", "COL_var01").
    *   **General Classification**: For precise classification within code logic or rules, developers should refer to the full `FILE_TYPE_DEFINITIONS` key (e.g., `"MAP_COL"`, `"MAP_METAL"`). The `standard_type` can be used for broader categorization or when a common alias is needed.

*   **`Map_type_Mapping.target_type` in Presets**: Within preset files (e.g., `Presets/Poliigon.json`), the `map_type_mapping` rules found inside a `FileRule`'s `map_processing_options` now use keys from `FILE_TYPE_DEFINITIONS` for the `target_type` field.
    *   Example:
        ```json
        // Inside a FileRule in a preset
        "map_processing_options": {
            "map_type_mapping": {
                "source_type_pattern": ".*ambient occlusion.*",
                "target_type": "MAP_AO", // Uses FILE_TYPE_DEFINITIONS key
                "source_channels": "RGB"
            }
        }
        ```
        This replaces old aliases like `"AO"` or `"OCC"`.

*   **`is_grayscale` Property**: `FILE_TYPE_DEFINITIONS` entries can now include an `is_grayscale` boolean property. This flag indicates whether the file type is inherently grayscale (e.g., a roughness map). It can be used by the processing engine to inform decisions about channel handling, compression, or specific image operations.
    *   Example: `FILE_TYPE_DEFINITIONS["MAP_RGH"]["is_grayscale"]` might be `true`.

### `ASSET_TYPE_DEFINITIONS`

Similarly, `ASSET_TYPE_DEFINITIONS` in `config/app_settings.json` is the **single source of truth** for all asset type identifiers.

*   **`AssetRule.asset_type`, `AssetRule.asset_type_override`, and `AssetRule.asset_category`**: When defining or interpreting `SourceRule` objects (and their constituent `AssetRule` instances), the `asset_type`, `asset_type_override`, and `asset_category` attributes **must** always use a key directly from `ASSET_TYPE_DEFINITIONS`.
    *   Example: `asset_rule.asset_type = "SURFACE_3D"` or `asset_rule.asset_category = "FABRIC"`.

Adherence to these definitions ensures that terminology remains consistent throughout the application, from configuration to core logic and output.

Adhering to these conventions will make the codebase more consistent, easier to understand, and more maintainable for all contributors.