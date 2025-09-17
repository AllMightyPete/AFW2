# User Guide: Usage - Blender Integration

This document explains how to use the optional Blender integration feature of the Asset Processor Tool.

## Overview

The Asset Processor Tool can optionally run Blender scripts after processing assets. These scripts automate the creation of PBR node groups and materials in specified `.blend` files, linking to the processed textures. This feature is available when using the tool via the Command-Line Interface (CLI) or the Graphical User Interface (GUI).

## How it Works (User Perspective)

When the Blender integration is enabled and configured, the Asset Processor Tool will:

1.  Process the input assets and generate the output files, including the `metadata.json` file for each asset.
2.  Execute Blender in the background using the specified Blender executable path.
3.  Run the `blenderscripts/create_nodegroups.py` script within Blender, passing the path to the processed asset's output directory and the target `.blend` file for node groups. This script reads the `metadata.json` and creates/updates PBR node groups in the target `.blend` file.
4.  If configured, execute the `blenderscripts/create_materials.py` script within Blender, passing the path to the processed asset's output directory, the target `.blend` file for materials, and the `.blend` file containing the node groups. This script reads the `metadata.json`, creates/updates materials in the target materials `.blend` file, and links them to the node groups created in the node group `.blend` file.

## Enabling and Configuring Blender Integration

### In the GUI

*   Locate the "Blender Post-Processing" section in the Processing Panel.
*   Check the box to enable the Blender integration.
*   Input fields and browse buttons will appear for specifying the target `.blend` files for Node Groups and Materials. These fields will default to the paths configured in `config.py`.

### In the CLI

*   Use the `--nodegroup-blend` option followed by the path to the target `.blend` file for node groups.
*   Use the `--materials-blend` option followed by the path to the target `.blend` file for materials.

Providing either of these options in the CLI will trigger the respective Blender script execution after asset processing. These command-line options override the default paths set in `config.py`.

## Requirements

*   A working installation of Blender.
*   The path to the Blender executable configured in `config.py` or accessible in your system's PATH.
*   For the material creation script, the target `.blend` file must contain a template material named `Template_PBRMaterial` with a Group node labeled `PLACEHOLDER_NODE_LABEL` (as defined in `blenderscripts/create_materials.py`).