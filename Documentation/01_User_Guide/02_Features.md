# User Guide: Features

This document outlines the key features of the Asset Processor Tool.

## Core Processing & Classification

*   **Preset-Driven:** Uses JSON presets (`presets/`) to define rules for different asset suppliers (e.g., `Poliigon.json`).
*   **Multi-Asset Input Handling:** Correctly identifies and processes multiple distinct assets contained within a single input `.zip`, `.rar`, `.7z` archive, or folder, creating separate outputs for each.
*   **File Classification:** Automatically identifies map types (Color, Normal, Roughness, etc.), models, explicitly marked extra files, and unrecognised files based on preset rules.
    *   **Variant Handling:** Map types listed in `RESPECT_VARIANT_MAP_TYPES` (in `config.py`, e.g., `"COL"`) always receive a numeric suffix (`-1`, `-2`, etc.). Numbering priority uses preset keyword order first, then alphabetical filename sorting as a tie-breaker. Other map types never receive a suffix.
    *   **16-bit Prioritization:** Correctly identifies and prioritizes 16-bit variants defined in preset `bit_depth_variants` (e.g., `*_NRM16.tif`), ignoring the corresponding 8-bit version (marked as `Ignored` in GUI).
*   **Map Processing:**
    *   Resizes texture maps to configured resolutions (e.g., 4K, 2K, 1K), avoiding upscaling.
    *   Handles Glossiness map inversion to Roughness.
    *   Applies bit-depth rules (`respect` source or `force_8bit`).
    *   Saves maps in appropriate formats (JPG, PNG, EXR) based on complex rules involving map type (`FORCE_LOSSLESS_MAP_TYPES`), resolution (`RESOLUTION_THRESHOLD_FOR_JPG`), bit depth, and source format.
    *   Calculates basic image statistics (Min/Max/Mean) for a reference resolution.
    *   Calculates and stores the relative aspect ratio change string in metadata (e.g., `EVEN`, `X150`, `Y125`).
    *   **Low-Resolution Fallback:** If enabled (`ENABLE_LOW_RESOLUTION_FALLBACK`), automatically saves an additional "LOWRES" variant of source images if their largest dimension is below a configurable threshold (`LOW_RESOLUTION_THRESHOLD`). This "LOWRES" variant uses the original image dimensions and is saved in addition to any standard resolution outputs.
*   **Channel Merging:** Combines channels from different maps into packed textures (e.g., NRMRGH) based on preset rules (`MAP_MERGE_RULES` in `config.py`).
*   **Metadata Generation:** Creates a `metadata.json` file for each asset containing details about maps, category, archetype, aspect ratio change, processing settings, etc.
*   **Output Organization:** Creates a clean, structured output directory (`<output_base>/<supplier>/<asset_name>/`).
*   **Optimized Classification:** Pre-compiles regular expressions from presets for faster file identification.

## Interface & Automation

*   **Dual Interface:** Provides both a user-friendly GUI and a powerful CLI.
*   **Parallel Processing:** Utilizes multiple CPU cores for faster processing (configurable via `--workers` in CLI or GUI control).
*   **Skip/Overwrite:** Can skip processing if the output already exists or force reprocessing (`--overwrite` flag / checkbox).
*   **Directory Monitor:** Includes `monitor.py` script for automated processing of assets dropped into a watched folder.
*   **Responsive GUI:** Uses background threads (`QThread`, `ProcessPoolExecutor`, `ThreadPoolExecutor`) to keep the UI responsive during intensive operations.
*   **GUI Features:**
    *   Drag-and-drop input (ZIPs / folders).
    *   Integrated preset editor panel.
    *   Configurable output directory field with browse button.
    *   Enhanced live preview table showing predicted file status.
    *   Toggleable preview mode (detailed file list vs simple asset list).
    *   Toggleable log console panel.
    *   Progress bar, cancellation button, clear queue button.

## Integration

*   **Blender Integration:** Optionally runs Blender scripts (`create_nodegroups.py`, `create_materials.py`) after asset processing to automate node group and material creation in specified `.blend` files. Available via both CLI and GUI.
    *   **GUI Controls:** Checkbox to enable/disable Blender integration and input fields with browse buttons for target `.blend` files.
*   **Docker Support:** Includes a `Dockerfile` for containerized execution.