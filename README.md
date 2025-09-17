# Asset Processing Utility

This tool streamlines the conversion of raw 3D asset source files from supplies (archives or folders) into a configurable library format. 
Goals include automatically updating Assets in various DCC's on import as well - minimising end user workload.

## Features

*   **Multithreaded Processing:** Leverages multiple CPU cores for parallel input processing, especially beneficial for large batches of inputs.
*   **Token-based Output Naming:** Offers highly flexible and configurable output directory structures and file naming conventions using a token system (e.g., `[supplier]`, `[assetname]`, `[resolution]`).
*   **Adjustable Resolutions:** Automatically resizes texture maps to multiple user-defined resolutions (e.g., 4K, 2K, 1K) during processing.
*   **Adjustable image formats:** Allows configuration of prefered image output formats, allowing for overrides depending on various factors (prefer EXR over PNG for 16Bit, Prefer JPG over PNG for resolutions above certain thesholds). User can configure compression settings for each image format.
*   **Gloss to Roughness Conversions:** Includes functionality to automatically invert Glossiness maps to Roughness maps, ensuring PBR workflow compatibility.
*   **Configurable Channel Packing:** Supports customizable channel packing, allowing users to define rules for merging channels from different source maps into optimized packed textures (e.g., Normal + Roughness into a single NRMRGH map).
*   **User-Friendly GUI:** Provides an intuitive Graphical User Interface for easy drag-and-drop input, interactive review and refinement of asset predictions, preset management, and process monitoring.
*   **Asset Identification by LLM:** Supports using customizable Large Language Model (LLM) for intelligent and flexible identification of asset and file types.
*   **Customizable Asset and File Types:** Allows for extensive customization of asset and file type definitions through configurable presets, enabling adaptation to various asset sources and conventions.
*   **Blender Asset Catalog Post-processing Step:** Optionally runs Blender scripts after processing, providing automatic creation of PBR node groups and materials, and marking them as assets for use in Blender's Asset Browser without needing user interaction.

## Core Workflow

1.  **Input Sources:** Drop asset archives or folders into the GUI.
2.  **Identify Inputs:** The tool reads the directory contents and performs an initial identification of asset and file types using configurable presets or an customizable LLM. Users can then review and refine these predictions interactively in a preview table. This involves confirming or correcting asset names, suppliers, types, and individual file types using direct editing, keyboard shortcuts, or triggering re-interpretation for specific sources.
3.  **Export to Library:** Once the inputs are correctly arranged and user verified, initiate the processing. The tool then automates tasks such as file classification, image resizings, format conversion, channel packing, and metadata generation, exporting the processed assets to a configurable output directory structure and naming convention. Most processing steps can be configured to fit user requirements.

In addition to the interactive GUI, the tool also offers a Command-Line Interface (CLI) for batch processing and scripting, and a Directory Monitor for automated processing of files dropped into a watched folder. (Docker Support Planned)

## Documentation

For detailed information on installation, configuration, usage of the different interfaces, and the output structure, please refer to the [`Documentation`](Documentation/00_Overview.md)