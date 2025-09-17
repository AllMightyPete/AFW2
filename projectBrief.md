# Project Brief: Asset Processor Tool

## 1. Main Goal & Purpose

The primary goal of the Asset Processor Tool is to provide **CG artists and 3D content teams with a friendly, fast, and flexible interface to process and organize 3D asset source files into a standardized library format.** It automates repetitive and complex tasks involved in preparing assets from various suppliers for use in production pipelines.

## 2. Key Features & Components

*   **Automated Asset Processing:** Ingests 3D asset source files (texture sets, models, etc.) from `.zip`, `.rar`, `.7z` archives, or folders.
*   **Preset-Driven Workflow:** Utilizes configurable JSON presets to interpret different asset sources (e.g., from various online vendors or internal standards), defining rules for file classification and processing.
*   **Comprehensive File Operations:**
    *   **Classification:** Automatically identifies map types (Color, Normal, Roughness, etc.), models, and other file categories based on preset rules.
    *   **Image Processing:** Performs tasks like image resizing (to standard resolutions like 1K, 2K, 4K, avoiding upscaling), glossiness-to-roughness conversion, normal map green channel inversion (OpenGL/DirectX handling), alpha channel extraction, bit-depth adjustments, and low-resolution fallback generation for small source images.
    *   **Channel Merging:** Combines channels from different source maps into packed textures (e.g., Normal + Roughness + Metallic into a single NRMRGH map).
*   **Metadata Generation:** Creates a detailed `metadata.json` file for each processed asset, containing information about maps, categories, processing settings, and more, for downstream tool integration.
*   **Flexible Output Organization:** Generates a clean, structured output directory based on user-configurable naming patterns and tokens.
*   **Multiple User Interfaces:**
    *   **Graphical User Interface (GUI):** The primary interface, designed to be user-friendly, offering drag-and-drop functionality, an integrated preset editor, a live preview table for rule validation and overrides, and clear processing controls.
    *   **Directory Monitor:** An automated script that watches a specified folder for new asset archives and processes them based on preset names embedded in the archive filename.
    *   **Command-Line Interface (CLI):** Intended for batch processing and scripting (currently with limited core functionality).
*   **Optional Blender Integration:** Can automatically run Blender scripts post-processing to create PBR node groups and materials in specified `.blend` files, linking to the newly processed textures.
*   **Hierarchical Rule System:** Allows for dynamic, granular overrides of preset configurations at the source, asset, or individual file level via the GUI.
*   **Experimental LLM Prediction:** Includes an option to use a Large Language Model for file interpretation and rule prediction.

## 3. Target Audience

*   **CG Artists:** Individual artists looking for an efficient way to manage and prepare their personal or downloaded asset libraries.
*   **3D Content Creation Teams:** Studios or groups needing a standardized pipeline for processing and organizing assets from multiple sources.
*   **Technical Artists/Pipeline Developers:** Who may extend or integrate the tool into broader production workflows.

## 4. Overall Architectural Style & Key Technologies

*   **Core Language:** Python
*   **GUI Framework:** PySide6
*   **Configuration:** Primarily JSON-based (application settings, user overrides, type definitions, supplier settings, presets, LLM settings).
*   **Processing Architecture:** A modular, staged processing pipeline orchestrated by a central engine. Each stage performs a discrete task on an `AssetProcessingContext` object.
*   **Key Libraries:** OpenCV (image processing), NumPy (numerical operations), py7zr/rarfile (archive handling), watchdog (directory monitoring).
*   **Design Principles:** Modularity, configurability, and user-friendliness (especially for the GUI).

## 5. Foundational Information

*   The tool aims to significantly reduce manual effort and ensure consistency in asset preparation.
*   It is designed to be adaptable to various asset sources and pipeline requirements through its extensive configuration options and preset system.
*   The output `metadata.json` is key for enabling further automation and integration with other tools or digital content creation (DCC) applications.