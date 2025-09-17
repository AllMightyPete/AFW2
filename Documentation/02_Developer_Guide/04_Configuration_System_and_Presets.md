# Developer Guide: Configuration System and Presets

This document provides technical details about the configuration system and the structure of preset files for developers working on the Asset Processor Tool.

## Configuration System Overview

The tool's configuration is managed by the `configuration.py` module and loaded from several JSON files, providing a layered approach for defaults, user overrides, definitions, and source-specific presets.

### Configuration Files

The tool's configuration is loaded from several JSON files, providing a layered approach for defaults, user overrides, definitions, and source-specific presets.

1.  **Application Settings (`config/app_settings.json`):** This JSON file defines the core global default settings, constants, and rules that apply generally across different asset sources (e.g., the global `OUTPUT_DIRECTORY_PATTERN` and `OUTPUT_FILENAME_PATTERN`, standard image resolutions, map merge rules, output format rules, Blender paths, temporary directory prefix, initial scaling mode, merge dimension mismatch strategy). See the [User Guide: Output Structure](../01_User_Guide/09_Output_Structure.md#available-tokens) for a list of available tokens for these patterns.
    *   *Note:* `ASSET_TYPE_DEFINITIONS` and `FILE_TYPE_DEFINITIONS` are no longer stored here; they have been moved to dedicated files.
    *   It also includes settings for new features like the "Low-Resolution Fallback":
        *   `ENABLE_LOW_RESOLUTION_FALLBACK` (boolean): Enables or disables the generation of "LOWRES" variants for small source images. Defaults to `true`.
        *   `LOW_RESOLUTION_THRESHOLD` (integer): The pixel dimension threshold (largest side) below which a "LOWRES" variant is created if the feature is enabled. Defaults to `512`.

2.  **User Settings (`config/user_settings.json`):** This optional JSON file allows users to override specific settings defined in `config/app_settings.json`. If this file exists, its values for corresponding keys will take precedence over the base application settings. This file is primarily managed through the GUI's Application Preferences Editor.

3.  **Asset Type Definitions (`config/asset_type_definitions.json`):** This dedicated JSON file contains the definitions for different asset types (e.g., Surface, Model, Decal), including their descriptions, colors for UI representation, and example usage strings.

4.  **File Type Definitions (`config/file_type_definitions.json`):** This dedicated JSON file contains the definitions for different file types (specifically texture maps and models), including descriptions, colors for UI representation, examples of keywords/patterns, a standard alias (`standard_type`), bit depth handling rules (`bit_depth_rule`), a grayscale flag (`is_grayscale`), and an optional GUI keybind (`keybind`).
    *   **`keybind` Property:** Each file type object within `FILE_TYPE_DEFINITIONS` can optionally include a `keybind` property. This property accepts a single character string (e.g., `"C"`, `"R"`) representing the keyboard key. In the GUI, this key (typically combined with `Ctrl`) is used as a shortcut to set or toggle the corresponding file type for selected items in the Preview Table.
        *Example:*
        ```json
        "MAP_COL": {
            "description": "Color/Albedo Map",
            "color": "#ffaa00",
            "examples": ["_col.", "_basecolor.", "albedo", "diffuse"],
            "standard_type": "COL",
            "bit_depth_rule": "force_8bit",
            "is_grayscale": false,
            "keybind": "C"
        },
        ```
        Note: The `bit_depth_rule` property in `FILE_TYPE_DEFINITIONS` is the primary source for determining bit depth handling for a given map type.

5.  **Supplier Settings (`config/suppliers.json`):** This JSON file stores settings specific to different asset suppliers. It is now structured as a dictionary where keys are supplier names and values are objects containing supplier-specific configurations.
    *   **Structure:**
        ```json
        {
          "SupplierName1": {
            "setting_key1": "value",
            "setting_key2": "value"
          },
          "SupplierName2": {
            "setting_key1": "value"
          }
        }
        ```
    *   **`normal_map_type` Property:** A key setting within each supplier's object is `normal_map_type`, specifying whether normal maps from this supplier use "OpenGL" or "DirectX" conventions.
        *Example:*
        ```json
        {
          "Poliigon": {
            "normal_map_type": "DirectX"
          },
          "Dimensiva": {
            "normal_map_type": "OpenGL"
          }
        }
        ```

6.  **LLM Settings (`config/llm_settings.json`):** This JSON file contains settings specifically related to the LLM predictor, such as the API endpoint, model name, prompt template, and examples. These settings are managed through the GUI using the `LLMEditorWidget`.

7.  **Preset Files (`Presets/*.json`):** These JSON files define source-specific rules and overrides. They contain patterns to interpret filenames, classify map types, handle variants, define naming conventions, and specify other source-specific behaviors. Preset settings override values from `app_settings.json` and `user_settings.json` where applicable.


### Configuration Loading and Access

The `configuration.py` module contains the `Configuration` class and standalone functions for loading and saving settings.

*   **`Configuration` Class:** This is the primary class used by the processing engine and other core components. When initialized with a `preset_name`, it loads settings in the following order, with later files overriding earlier ones for shared keys:
    1.  `config/app_settings.json` (Base Defaults)
    2.  `config/user_settings.json` (User Overrides - if exists)
    3.  `config/asset_type_definitions.json` (Asset Type Definitions)
    4.  `config/file_type_definitions.json` (File Type Definitions)
    5.  `config/llm_settings.json` (LLM Settings)
    6.  `Presets/{preset_name}.json` (Preset Overrides)

    The loaded settings are merged into internal dictionaries, and most are accessible via instance properties (e.g., `config.output_base_dir`, `config.llm_endpoint_url`, `config.get_asset_type_definitions()`). Regex patterns defined in the merged configuration are pre-compiled for performance.

*   **`load_base_config()` function:** This standalone function is primarily used by the GUI for initial setup and displaying default/user-overridden settings before a specific preset is selected. It loads and merges the following files:
    1.  `config/app_settings.json`
    2.  `config/user_settings.json` (if exists)
    3.  `config/asset_type_definitions.json`
    4.  `config/file_type_definitions.json`

    It returns a single dictionary containing the combined settings and definitions.

*   **Saving Functions:**
    *   `save_base_config(settings_dict)`: Saves the provided dictionary to `config/app_settings.json`. (Used less frequently now for user-driven saves).
    *   `save_user_config(settings_dict)`: Saves the provided dictionary to `config/user_settings.json`. Used by `ConfigEditorDialog`.
    *   `save_llm_config(settings_dict)`: Saves the provided dictionary to `config/llm_settings.json`. Used by `LLMEditorWidget`.

## Supplier Management (`config/suppliers.json`)

A file, `config/suppliers.json`, is used to store a persistent list of known supplier names. This file is a simple JSON array of strings.

*   **Purpose:** Provides a list of suggestions for the "Supplier" field in the GUI's Unified View, enabling auto-completion.
*   **Management:** The GUI's `SupplierSearchDelegate` is responsible for loading this list on startup, adding new, unique supplier names entered by the user, and saving the updated list back to the file.

## GUI Configuration Editors

The GUI provides dedicated editors for modifying configuration files:

*   **`ConfigEditorDialog` (`gui/config_editor_dialog.py`):** Edits user-configurable application settings.
*   **`LLMEditorWidget` (`gui/llm_editor_widget.py`):** Edits the LLM-specific settings.

### `ConfigEditorDialog` (`gui/config_editor_dialog.py`)

The GUI includes a dedicated editor for modifying user-configurable settings. This is implemented in `gui/config_editor_dialog.py`.

*   **Purpose:** Provides a user-friendly interface for viewing the effective application settings (defaults + user overrides + definitions) and editing the user-specific overrides.
*   **Implementation:** The dialog loads the effective settings using `load_base_config()`. It presents relevant settings in a tabbed layout ("General", "Output & Naming", etc.). When saving, it now performs a **granular save**: it loads the current content of `config/user_settings.json`, identifies only the settings that were changed by the user during the current dialog session (by comparing against the initial state), updates only those specific values in the loaded `user_settings.json` content, and saves the modified content back to `config/user_settings.json` using `save_user_config()`. This preserves any other settings in `user_settings.json` that were not touched. The dialog displays definitions from `asset_type_definitions.json` and `file_type_definitions.json` but does not save changes to these files.
*   **Limitations:** Currently, editing complex fields like `IMAGE_RESOLUTIONS` or the full details of `MAP_MERGE_RULES` via the UI is not fully supported for saving to `user_settings.json`.

### `LLMEditorWidget` (`gui/llm_editor_widget.py`)

*   **Purpose:** Provides a user-friendly interface for viewing and editing the LLM settings defined in `config/llm_settings.json`.
*   **Implementation:** Uses tabs for "Prompt Settings" and "API Settings". Allows editing the prompt, managing examples, and configuring API details. When saving, it also performs a **granular save**: it loads the current content of `config/llm_settings.json`, identifies only the settings changed by the user in the current session, updates only those values, and saves the modified content back to `config/llm_settings.json` using `configuration.save_llm_config()`.

## Preset File Structure (`Presets/*.json`)

Preset files are the primary way to adapt the tool to new asset sources. Developers should use `Presets/_template.json` as a starting point. Key fields include:

*   `supplier_name`: The name of the asset source (e.g., `"Poliigon"`). Used for output directory naming.
*   `map_type_mapping`: A list of dictionaries, each mapping source filename patterns/keywords to a specific file type. The `target_type` for this mapping **must** be a key from the `FILE_TYPE_DEFINITIONS` now located in `config/file_type_definitions.json`.
    *   `target_type`: The specific file type key from `FILE_TYPE_DEFINITIONS` (e.g., `"MAP_COL"`, `"MAP_NORM_GL"`, `"MAP_RGH"`). This replaces previous alias-based systems. The common aliases like "COL" or "NRM" are now derived from the `standard_type` property within `FILE_TYPE_DEFINITIONS` but are not used directly for `target_type`.
    *   `keywords`: A list of filename patterns (regex or fnmatch-style wildcards) used to identify this map type. The order of keywords within this list, and the order of dictionaries in the `map_type_mapping` list, determines the priority for assigning variant suffixes (`-1`, `-2`, etc.) when multiple files match the same `target_type`.
*   `bit_depth_variants`: A dictionary mapping standard map types (e.g., `"NRM"`) to a pattern identifying its high bit-depth variant (e.g., `"*_NRM16*.tif"`). Files matching these patterns are prioritized over their standard counterparts.
*   `map_bit_depth_rules`: Defines how to handle the bit depth of source maps. Can specify a default behavior (`"respect"` or `"force_8bit"`) and overrides for specific map types.
*   `model_patterns`: A list of regex patterns to identify model files (e.g., `".*\\.fbx"`, `".*\\.obj"`).
*   `move_to_extra_patterns`: A list of regex patterns for files that should be moved directly to the `Extra/` output subdirectory without further processing.
*   `source_naming_convention`: Rules for extracting the base asset name and potentially the archetype from source filenames or directory structures (e.g., using separators and indices).
*   `asset_category_rules`: Keywords or patterns used to determine the asset category (e.g., identifying `"Decal"` based on keywords).
*   `archetype_rules`: Keywords or patterns used to determine the asset archetype (e.g., identifying `"Wood"` or `"Metal"`).

Careful definition of these patterns and rules, especially the regex in `map_type_mapping`, `bit_depth_variants`, `model_patterns`, and `move_to_extra_patterns`, is essential for correct asset processing.

**Note on Data Passing:** As mentioned in the Architecture documentation, major changes to the data passing mechanisms between the GUI, Main (CLI orchestration), and `AssetProcessor` modules are currently being planned. The descriptions of how configuration data is handled and passed within this document reflect the current state and will require review and updates once the plan for these changes is finalized.

## Supplier Management (`config/suppliers.json`)

A new file, `config/suppliers.json`, is used to store a persistent list of known supplier names. This file is a simple JSON array of strings.

*   **Purpose:** Provides a list of suggestions for the "Supplier" field in the GUI's Unified View, enabling auto-completion.
*   **Management:** The GUI's `SupplierSearchDelegate` is responsible for loading this list on startup, adding new, unique supplier names entered by the user, and saving the updated list back to the file.

## `Configuration` Class (`configuration.py`)

The `Configuration` class is central to the new configuration system. It is responsible for loading, merging, and preparing the configuration settings for use by the `ProcessingEngine` and other components like the `PredictionHandler` and `LLMPredictionHandler`.

*   **Initialization:** An instance is created with a specific `preset_name`.
*   **Loading:**
    *   It first loads the base application settings from `config/app_settings.json`.
    *   It then loads the LLM-specific settings from `config/llm_settings.json`.
    *   Finally, it loads the specified preset JSON file from the `Presets/` directory.
*   **Merging & Access:** The base settings from `app_settings.json` are merged with the preset rules. LLM settings are stored separately. Most settings are accessible via instance properties (e.g., `config.llm_endpoint_url`). Preset values generally override the base settings where applicable. **Exception:** The `OUTPUT_DIRECTORY_PATTERN` and `OUTPUT_FILENAME_PATTERN` are loaded *only* from `app_settings.json` and are accessed via `config.output_directory_pattern` and `config.output_filename_pattern` respectively; they are not defined in or overridden by presets.
*   **Validation (`_validate_configs`):** Performs basic structural validation on the loaded settings (base, LLM, and preset), checking for the presence of required keys and basic data types. Logs warnings for missing optional LLM keys.
*   **Regex Compilation (`_compile_regex_patterns`):** Compiles regex patterns defined in the merged configuration (from base settings and the preset) for performance. Compiled regex objects are stored as instance attributes (e.g., `self.compiled_map_keyword_regex`).
*   **LLM Settings Access:** The `Configuration` class provides direct property access (e.g., `config.llm_endpoint_url`, `config.llm_api_key`, `config.llm_model_name`, `config.llm_temperature`, `config.llm_request_timeout`, `config.llm_predictor_prompt`, `config.get_llm_examples()`) to allow components like the `LLMPredictionHandler` to easily access the necessary LLM configuration values loaded from `config/llm_settings.json`.

An instance of `Configuration` is created within each worker process (`main.process_single_asset_wrapper`) to ensure that each concurrently processed asset uses the correct, isolated configuration based on the specified preset and the base application settings. The `LLMInteractionHandler` loads LLM settings directly using helper functions or file access, not the `Configuration` class.

## GUI Configuration Editors

The GUI provides dedicated editors for modifying configuration files:

*   **`ConfigEditorDialog` (`gui/config_editor_dialog.py`):** Edits the core `config/app_settings.json`.
*   **`LLMEditorWidget` (`gui/llm_editor_widget.py`):** Edits the LLM-specific `config/llm_settings.json`.

### `ConfigEditorDialog` (`gui/config_editor_dialog.py`)

The GUI includes a dedicated editor for modifying the `config/app_settings.json` file. This is implemented in `gui/config_editor_dialog.py`.

*   **Purpose:** Provides a user-friendly interface for viewing and editing the core application settings defined in `app_settings.json`.
*   **Implementation:** The dialog loads the JSON content of `app_settings.json`, presents it in a tabbed layout ("General", "Output & Naming", etc.) using standard GUI widgets mapped to the JSON structure, and saves the changes back to the file. The "Output & Naming" tab specifically handles the global `OUTPUT_DIRECTORY_PATTERN` and `OUTPUT_FILENAME_PATTERN`. It supports editing basic fields, tables for definitions (`FILE_TYPE_DEFINITIONS`, `ASSET_TYPE_DEFINITIONS`), and a list/detail view for merge rules (`MAP_MERGE_RULES`). The definitions tables include dynamic color editing features.
*   **Limitations:** Currently, editing complex fields like `IMAGE_RESOLUTIONS` or the full details of `MAP_MERGE_RULES` via the UI is not fully supported.
*   **Note:** Changes made through the `ConfigEditorDialog` are written directly to `config/app_settings.json` (using `save_base_config`) but require an application restart to be loaded and applied by the `Configuration` class during processing.

### `LLMEditorWidget` (`gui/llm_editor_widget.py`)

*   **Purpose:** Provides a user-friendly interface for viewing and editing the LLM settings defined in `config/llm_settings.json`.
*   **Implementation:** Uses tabs for "Prompt Settings" and "API Settings". Allows editing the prompt, managing examples, and configuring API details.
*   **Persistence:** Saves changes directly to `config/llm_settings.json` using the `configuration.save_llm_config()` function. Changes are loaded by the `LLMInteractionHandler` the next time an LLM task is initiated.

## Preset File Structure (`Presets/*.json`)

Preset files are the primary way to adapt the tool to new asset sources. Developers should use `Presets/_template.json` as a starting point. Key fields include:

*   `supplier_name`: The name of the asset source (e.g., `"Poliigon"`). Used for output directory naming.
*   `map_type_mapping`: A list of dictionaries, each mapping source filename patterns/keywords to a specific file type. The `target_type` for this mapping **must** be a key from `FILE_TYPE_DEFINITIONS` located in `config/app_settings.json`.
    *   `target_type`: The specific file type key from `FILE_TYPE_DEFINITIONS` (e.g., `"MAP_COL"`, `"MAP_NORM_GL"`, `"MAP_RGH"`). This replaces previous alias-based systems. The common aliases like "COL" or "NRM" are now derived from the `standard_type` property within `FILE_TYPE_DEFINITIONS` but are not used directly for `target_type`.
    *   `keywords`: A list of filename patterns (regex or fnmatch-style wildcards) used to identify this map type. The order of keywords within this list, and the order of dictionaries in the `map_type_mapping` list, determines the priority for assigning variant suffixes (`-1`, `-2`, etc.) when multiple files match the same `target_type`.
*   `bit_depth_variants`: A dictionary mapping standard map types (e.g., `"NRM"`) to a pattern identifying its high bit-depth variant (e.g., `"*_NRM16*.tif"`). Files matching these patterns are prioritized over their standard counterparts.
*   `map_bit_depth_rules`: Defines how to handle the bit depth of source maps. Can specify a default behavior (`"respect"` or `"force_8bit"`) and overrides for specific map types.
*   `model_patterns`: A list of regex patterns to identify model files (e.g., `".*\\.fbx"`, `".*\\.obj"`).
*   `move_to_extra_patterns`: A list of regex patterns for files that should be moved directly to the `Extra/` output subdirectory without further processing.
*   `source_naming_convention`: Rules for extracting the base asset name and potentially the archetype from source filenames or directory structures (e.g., using separators and indices).
*   `asset_category_rules`: Keywords or patterns used to determine the asset category (e.g., identifying `"Decal"` based on keywords).
*   `archetype_rules`: Keywords or patterns used to determine the asset archetype (e.g., identifying `"Wood"` or `"Metal"`).

Careful definition of these patterns and rules, especially the regex in `map_type_mapping`, `bit_depth_variants`, `model_patterns`, and `move_to_extra_patterns`, is essential for correct asset processing.

**Note on Data Passing:** As mentioned in the Architecture documentation, major changes to the data passing mechanisms between the GUI, Main (CLI orchestration), and `AssetProcessor` modules are currently being planned. The descriptions of how configuration data is handled and passed within this document reflect the current state and will require review and updates once the plan for these changes is finalized.