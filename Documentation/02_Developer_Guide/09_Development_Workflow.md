# Developer Guide: Development Workflow

This document provides guidance for developers on the typical workflow for contributing to or modifying the Asset Processor Tool.

## Modifying Core Processing Logic

Changes to how assets are classified, maps are processed (resizing, format conversion, bit depth handling), channels are merged, or metadata is generated primarily involve editing the `AssetProcessor` class in `asset_processor.py`. Understanding the processing pipeline steps outlined in `05_Processing_Pipeline.md` is crucial here.

## Changing Global Settings/Rules

Adjustments to default output paths, standard image resolutions, default format rules, map merge definitions, Blender paths, or other global constants should be made in `config.py`.

## Adding/Modifying Supplier Rules (Presets)

To add support for a new asset source or change how an existing one is interpreted, you need to create or edit the corresponding JSON file in the `Presets/` directory.

*   Use `Presets/_template.json` as a base for new presets.
*   Focus on defining accurate regex patterns and rules in fields like `map_type_mapping`, `bit_depth_variants`, `model_patterns`, `source_naming_convention`, etc.
*   Refer to `04_Configuration_System_and_Presets.md` for a detailed explanation of the preset file structure and the configuration loading process.

## Adjusting CLI Behavior

Changes to command-line arguments, argument parsing logic, or the overall CLI workflow are handled in `main.py`. This includes how arguments are parsed using `argparse`, how parallel processing is orchestrated, and how Blender scripts are triggered from the CLI.

## Modifying the GUI

Work on the Graphical User Interface involves the files within the `gui/` directory.

*   UI layout changes, adding new controls, or altering event handling are typically done in `main_window.py`.
*   Modifications to how background processing tasks are managed for the GUI are handled in `processing_handler.py`.
*   Changes to how file classification previews are generated and updated in the UI are in `prediction_handler.py`.
*   Understanding Qt's signals and slots mechanism and the use of `QThread` and `ProcessPoolExecutor` (as detailed in `06_GUI_Internals.md`) is essential for GUI development.

## Enhancing Blender Integration

Improvements or changes to how node groups or materials are created in Blender require editing the Python scripts within the `blenderscripts/` directory (`create_nodegroups.py`, `create_materials.py`).

*   These scripts are designed to be executed *within* Blender and interact with Blender's `bpy` API.
*   Consider how these scripts are invoked by the Asset Processor (via subprocess calls) and what data they expect (primarily from `metadata.json` and `sys.argv`).
*   Refer to `08_Blender_Integration_Internals.md` for details on the execution mechanism and script specifics.

## General Development Practices

*   Adhere to the project's coding conventions (see `10_Coding_Conventions.md`).
*   Utilize the standard Python `logging` module for outputting information and debugging messages.
*   Use `try...except` blocks for error handling, and leverage the custom exceptions (`ConfigurationError`, `AssetProcessingError`) where appropriate.
*   When working with file paths, use `pathlib.Path` for consistency and robustness.
*   Be mindful of concurrency when working with the GUI or parallel processing in the CLI.

This workflow provides a general guide; specific tasks may require delving into multiple files and understanding the interactions between different components.