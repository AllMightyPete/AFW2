# User Guide: Usage - Command-Line Interface (CLI)

This document explains how to use the Asset Processor Tool's Command-Line Interface.

## Running the CLI

From the project root directory, run the following command:

```bash
python main.py [OPTIONS] INPUT_PATH [INPUT_PATH ...]
```

## Arguments

*   `INPUT_PATH`: One or more paths to input `.zip`, `.rar`, `.7z` files, or folders.

## Options

*   `-p PRESET`, `--preset PRESET`: **(Required)** Name of the preset (e.g., `Poliigon`).
*   `-o OUTPUT_DIR`, `--output-dir OUTPUT_DIR`: Override `OUTPUT_BASE_DIR` from `config.py`.
*   `-w WORKERS`, `--workers WORKERS`: Number of parallel processes (default: auto).
*   `--overwrite`: Force reprocessing and overwrite existing output.
*   `-v`, `--verbose`: Enable detailed DEBUG level logging.
*   `--nodegroup-blend NODEGROUP_BLEND`: Path to `.blend` for node groups. Triggers script if provided. Overrides `config.py`.
*   `--materials-blend MATERIALS_BLEND`: Path to `.blend` for materials. Triggers script if provided. Overrides `config.py`.

## Example

```bash
python main.py "C:/Downloads/WoodFine001.zip" -p Poliigon -o "G:/Assets/Processed" --workers 4 --overwrite --nodegroup-blend "G:/Blender/Libraries/NodeGroups.blend" --materials-blend "G:/Blender/Libraries/Materials.blend"