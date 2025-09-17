# User Guide: Configuration and Presets

This document explains how to configure the Asset Processor Tool and use presets.

## Application Settings (`config/app_settings.json`)

The tool's core settings are now stored in `config/app_settings.json`. This JSON file contains the base configuration for the application.

The `configuration.py` module is responsible for loading the settings from `app_settings.json` (including loading and saving the JSON content), merging them with the rules from the selected preset file, and providing the base configuration via the `load_base_config()` function. Note that the old `config.py` file has been deleted.

The `app_settings.json` file is structured into several key sections, including:
*   `FILE_TYPE_DEFINITIONS`: Defines known file types (like different texture maps, models, etc.) and their properties. Each definition now includes a `"standard_type"` key for aliasing to a common type (e.g., "COL" for color maps, "NRM" for normal maps), an `"is_grayscale"` boolean property, and a `"bit_depth_rule"` key specifying how to handle bit depth for this file type. The separate `MAP_BIT_DEPTH_RULES` section has been removed. For users creating or editing presets, it's important to note that internal mapping rules (like `Map_type_Mapping.target_type` within a preset's `FileRule`) now directly use the main keys from these `FILE_TYPE_DEFINITIONS` (e.g., `"MAP_COL"`, `"MAP_RGH"`), not just the `standard_type` aliases.
*   `ASSET_TYPE_DEFINITIONS`: Defines known asset types (like Surface, Model, Decal) and their properties.
*   `MAP_MERGE_RULES`: Defines how multiple input maps can be merged into a single output map (e.g., combining Normal and Roughness into one).

### Low-Resolution Fallback Settings

These settings control the generation of low-resolution "fallback" variants for source images:

*   `ENABLE_LOW_RESOLUTION_FALLBACK` (boolean, default: `true`):
    *   If `true`, the tool will generate an additional "LOWRES" variant for source images whose largest dimension is smaller than the `LOW_RESOLUTION_THRESHOLD`.
    *   This "LOWRES" variant uses the original dimensions of the source image and is saved in addition to any other standard resolution outputs (e.g., 1K, PREVIEW).
    *   If `false`, this feature is disabled.
*   `LOW_RESOLUTION_THRESHOLD` (integer, default: `512`):
    *   Defines the pixel dimension (for the largest side of an image) below which the "LOWRES" fallback variant will be generated (if enabled).
    *   For example, if set to `512`, any source image smaller than 512x512 (e.g., 256x512, 128x128) will have a "LOWRES" variant created.

### LLM Predictor Settings

For users who wish to utilize the experimental LLM Predictor feature, the following settings are available in `config/llm_settings.json`:

*   `llm_endpoint_url`: The URL of the LLM API endpoint. For local LLMs like LM Studio or Ollama, this will typically be `http://localhost:<port>/v1`. Consult your LLM server documentation for the exact endpoint.
*   `llm_api_key`: The API key required to access the LLM endpoint. Some local LLM servers may not require a key, in which case this can be left empty.
*   `llm_model_name`: The name of the specific LLM model to use for prediction. This must match a model available at your specified endpoint.
*   `llm_temperature`: Controls the randomness of the LLM's output. Lower values (e.g., 0.1-0.5) make the output more deterministic and focused, while higher values (e.g., 0.6-1.0) make it more creative and varied. For prediction tasks, lower temperatures are generally recommended.
*   `llm_request_timeout`: The maximum time (in seconds) to wait for a response from the LLM API. Adjust this based on the performance of your LLM server and the complexity of the requests.

Note that the `llm_predictor_prompt` and `llm_predictor_examples` settings are also present in `config/llm_settings.json`. These define the instructions and examples provided to the LLM for prediction. While they can be viewed here, they are primarily intended for developer reference and tuning the LLM's behavior, and most users will not need to modify them directly via the file. These settings are editable via the LLM Editor panel in the main GUI when the LLM interpretation mode is selected.

## Application Preferences (`config/app_settings.json` overrides)

You can modify user-overridable application settings using the built-in GUI editor. These settings are loaded from `config/app_settings.json` and saved as overrides in `config/user_settings.json`. Access it via the **Edit** -> **Preferences...** menu.

This editor provides a tabbed interface to view and change various application behaviors. The tabs include:
*   **General:** Basic settings like output base directory and temporary file prefix.
*   **Output & Naming:** Settings controlling output directory and filename patterns, and how variants are handled.
*   **Image Processing:** Settings related to image resolution definitions, compression levels, and format choices.
*   **Map Merging:** Configuration for how multiple input maps are combined into single output maps.
*   **Postprocess Scripts:** Paths to default Blender files for post-processing.

Note that this editor focuses on user-specific overrides of core application settings. **Asset Type Definitions, File Type Definitions, and Supplier Settings are managed in a separate Definitions Editor.**

Any changes made through the Preferences editor require an application restart to take effect.

*(Ideally, a screenshot of the Application Preferences editor would be included here.)*

## Definitions Editor (`config/asset_type_definitions.json`, `config/file_type_definitions.json`, `config/suppliers.json`)

Core application definitions that are separate from general user preferences are managed in the dedicated Definitions Editor. This includes defining known asset types, file types, and configuring settings specific to different suppliers. Access it via the **Edit** -> **Edit Definitions...** menu.

The editor is organized into three tabs:
*   **Asset Type Definitions:** Define the different categories of assets (e.g., Surface, Model, Decal). For each asset type, you can configure its description, a color for UI representation, and example usage strings.
*   **File Type Definitions:** Define the specific types of files the tool recognizes (e.g., MAP_COL, MAP_NRM, MODEL). For each file type, you can configure its description, a color, example keywords/patterns, a standard type alias, bit depth handling rules, whether it's grayscale, and an optional keybind for quick assignment in the GUI.
*   **Supplier Settings:** Configure settings that are specific to assets originating from different suppliers. Currently, this includes the "Normal Map Type" (OpenGL or DirectX) used for normal maps from that supplier.

Each tab presents a list of the defined items on the left (Asset Types, File Types, or Suppliers). Selecting an item in the list displays its configurable details on the right. Buttons are provided to add new definitions or remove existing ones.

Changes made in the Definitions Editor are saved directly to their respective configuration files (`config/asset_type_definitions.json`, `config/file_type_definitions.json`, and `config/suppliers.json`). Some changes may require an application restart to take full effect in processing logic.

*(Ideally, screenshots of the Definitions Editor tabs would be included here.)*

## Preset Files (`presets/*.json`)

Preset files define supplier-specific rules for interpreting asset source files. They are crucial for the tool to correctly classify files and process assets from different sources.

*   Presets are located in the `presets/` directory.
*   Each preset is a JSON file named after the supplier (e.g., `Poliigon.json`).
*   Presets contain rules based on filename patterns and keywords to identify map types, models, and other files.
*   They also define how variants (like different resolutions or bit depths) are handled and how asset names and categories are determined from the source filename. When defining `map_type_mapping` rules within a preset, the `target_type` field must now use a valid key from the `FILE_TYPE_DEFINITIONS` in `config/app_settings.json` (e.g., `"MAP_AO"` instead of a custom alias like `"AO"`).

When processing assets, you must specify which preset to use. The tool then loads the core settings from `config/app_settings.json` and merges them with the rules from the selected preset to determine how to process the input.

A template preset file (`presets/_template.json`) is provided as a base for creating new presets.
## Global Output Path Configuration

The structure and naming of the output files generated by the tool are now controlled by two global settings defined exclusively in `config/app_settings.json`:

*   `OUTPUT_DIRECTORY_PATTERN`: Defines the directory structure where processed assets will be saved.
*   `OUTPUT_FILENAME_PATTERN`: Defines the naming convention for the individual output files within the generated directory.

**Important:** These settings are global and apply to all processing tasks, regardless of the selected preset. They are **not** part of individual preset files and cannot be modified using the Preset Editor. You can view and edit these patterns in the main application preferences (**Edit** -> **Preferences...**).

These patterns use special tokens (e.g., `[assetname]`, `[maptype]`) that are replaced with actual values during processing. For a detailed explanation of how these patterns work together, the available tokens, and examples, please refer to the [Output Structure](./09_Output_Structure.md) section of the User Guide.