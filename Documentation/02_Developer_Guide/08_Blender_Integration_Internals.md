# Developer Guide: Blender Integration Internals

This document provides technical details about how the Asset Processor Tool integrates with Blender for automated post-processing tasks.

## Overview

The tool can optionally execute Python scripts within a Blender instance after successfully processing a batch of assets. This is primarily used to automate the creation of PBR node groups and materials in specified `.blend` files, linking to the newly processed textures and their associated `metadata.json` files.

## Execution Mechanism

The Blender scripts are executed by the main orchestrator (`main.py` for CLI, `gui/processing_handler.py` for GUI) using Python's `subprocess.run`.

*   The command executed is typically: `blender -b <target_blend_file> --python <script_path> -- <arguments_for_script>`
    *   `blender`: The path to the Blender executable (configured in `config.py` or found in the system PATH).
    *   `-b`: Runs Blender in background mode (headless, no GUI).
    *   `<target_blend_file>`: The `.blend` file that the script will operate on.
    *   `--python <script_path>`: Specifies the Python script to run within Blender. The scripts are located in the `blenderscripts/` directory (`create_nodegroups.py`, `create_materials.py`).
    *   `--`: This separator is crucial. Arguments placed after `--` are passed to the Python script's `sys.argv`.
    *   `<arguments_for_script>`: The Asset Processor Tool passes necessary information to the Blender scripts via `sys.argv`. Currently, this includes the path to the processed asset's root directory (containing `metadata.json`) and, for the materials script, the path to the `.blend` file containing the node groups.

*   The GUI handler (`gui/processing_handler.py`) also uses `--factory-startup` in the subprocess call, which starts Blender with factory defaults, potentially avoiding issues with user preferences or addons.

*   The orchestrator checks the return code of the `subprocess.run` call. A non-zero return code indicates an error during script execution within Blender. Stdout and stderr from the Blender process are captured and logged by the Asset Processor Tool.

## Blender Scripts (`blenderscripts/`)

The `blenderscripts/` directory contains Python scripts designed to be run *inside* a Blender environment. They import Blender's `bpy` module to interact with the `.blend` file data.

*   **`create_nodegroups.py`**:
    *   **Purpose:** Creates or updates PBR node groups in a target `.blend` file based on processed assets.
    *   **Execution:** Typically triggered by the Asset Processor after asset processing. Can also be run manually within Blender's Text Editor.
    *   **Input:** Reads the `metadata.json` file from the processed asset's directory (path received via `sys.argv`).
    *   **Functionality:** Accesses `bpy.data.node_groups` to create or modify node groups. Loads texture images using `bpy.data.images.load`. Sets up nodes and links within the node group. Applies metadata settings (aspect ratio, stats, resolution) to the node group interface or properties. Sets preview images for the node groups. Saves the target `.blend` file.
    *   **Prerequisites (for manual run):** Processed asset library available, target `.blend` file containing template node groups (`Template_PBRSET`, `Template_PBRTYPE`).
    *   **Configuration (for manual run):** Requires setting `PROCESSED_ASSET_LIBRARY_ROOT` internally (overridden by Asset Processor when triggered).

*   **`create_materials.py`**:
    *   **Purpose:** Creates or updates materials in a target `.blend` file that link to the PBR node groups created by `create_nodegroups.py`.
    *   **Execution:** Typically triggered by the Asset Processor after `create_nodegroups.py` has run. Can also be run manually within Blender's Text Editor.
    *   **Input:** Reads the `metadata.json` file (path via `sys.argv`). Receives the path to the `.blend` file containing the node groups (via `sys.argv`).
    *   **Functionality:** Accesses `bpy.data.materials` to create or modify materials. Copies a template material (`Template_PBRMaterial`). Links the corresponding PBRSET node group from the specified library `.blend` file using `bpy.data.libraries.load`. Replaces a placeholder node (`PLACEHOLDER_NODE_LABEL`) in the template material's node tree with the linked node group. Marks the material as an asset. Copies tags. Sets preview images and viewport properties. Saves the target `.blend` file.
    *   **Prerequisites (for manual run):** Processed asset library available, the `.blend` file containing the PBRSET node groups, and the *current* target `.blend` file must contain a template material named `Template_PBRMaterial` with a Group node labeled `PLACEHOLDER_NODE_LABEL`.
    *   **Configuration (for manual run):** Requires setting `PROCESSED_ASSET_LIBRARY_ROOT` and `NODEGROUP_BLEND_FILE_PATH` internally (overridden by Asset Processor when triggered). Constants like `TEMPLATE_MATERIAL_NAME` and `PLACEHOLDER_NODE_LABEL` can be adjusted.

## Data Flow

Information is passed from the Asset Processor to the Blender scripts primarily through the `metadata.json` file and command-line arguments (`sys.argv`). The scripts read the `metadata.json` to get details about the processed maps, stats, etc., and use the provided paths to locate the necessary files and target `.blend` files.

## Limitations

*   The Directory Monitor (`monitor.py`) does not currently support triggering the Blender integration scripts.
*   Cancellation of the main Asset Processor process does not necessarily stop a Blender subprocess that has already been launched.
*   The Blender scripts rely on specific naming conventions for template node groups and materials within the target `.blend` files.

Understanding the subprocess execution, the data passed via `sys.argv` and `metadata.json`, and the `bpy` API usage within the scripts is essential for developing or debugging the Blender integration.