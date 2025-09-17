# Developer Guide: Debugging Notes

This document provides deeper technical details about the internal workings of the Asset Processor Tool, intended to aid in debugging unexpected behavior.

## Internal Logic & Algorithms

*   **Configuration Preparation (`Configuration` class in `configuration.py`):**
    *   Instantiated per preset (`__init__`).
    *   Loads core settings from `config.py` using `importlib.util`.
    *   Loads specified preset from `presets/{preset_name}.json`.
    *   Validates basic structure of loaded settings (`_validate_configs`), checking for required keys and basic types (e.g., `map_type_mapping` is a list of dicts).
    *   Compiles regex patterns (`_compile_regex_patterns`) from preset rules (extra, model, bit depth, map keywords) using `re.compile` (mostly case-insensitive) and stores them on the instance (e.g., `self.compiled_map_keyword_regex`). Uses `_fnmatch_to_regex` helper for basic wildcard conversion.

*   **CLI Argument Parsing (`main.py:setup_arg_parser`):**
    *   Uses `argparse` to define and parse command-line arguments.
    *   Key arguments influencing flow: `--preset` (required), `--output-dir` (optional override), `--workers` (concurrency), `--overwrite` (force reprocessing), `--verbose` (logging level), `--nodegroup-blend`, `--materials-blend`.
    *   Calculates a default worker count based on `os.cpu_count()`.

*   **Output Directory Resolution (`main.py:main`):**
    *   Determines the base output directory by checking `--output-dir` argument first, then falling back to `OUTPUT_BASE_DIR` from `config.py`.
    *   Resolves the path to an absolute path and ensures the directory exists (`Path.resolve()`, `Path.mkdir(parents=True, exist_ok=True)`).

*   **Asset Processing (`AssetProcessor` class in `asset_processor.py`):**
    *   **Classification (`_inventory_and_classify_files`):**
        *   Multi-pass approach: Explicit Extra (regex) -> Models (regex) -> Potential Maps (keyword regex) -> Standalone 16-bit check (regex) -> Prioritize 16-bit variants -> Final Maps -> Remaining as Unrecognised (Extra).
        *   Uses compiled regex patterns provided by the `Configuration` object passed during initialization.
        *   Sorts potential map variants based on: 1. Preset rule index, 2. Keyword index within rule, 3. Alphabetical path. Suffixes (`-1`, `-2`) are assigned later per-asset based on this sort order and `RESPECT_VARIANT_MAP_TYPES`.
    *   **Map Processing (`_process_maps`):**
        *   Loads images using `cv2.imread` (flags: `IMREAD_UNCHANGED` or `IMREAD_GRAYSCALE`). Converts loaded 3-channel images from BGR to RGB for internal consistency (stats, merging).
        *   **Saving Channel Order:** Before saving with `cv2.imwrite`, 3-channel images are conditionally converted back from RGB to BGR *only* if the target output format is *not* EXR (e.g., for PNG, JPG, TIF). This ensures correct channel order for standard formats while preserving RGB for EXR. (Fix for ISSUE-010).
        *   Handles Gloss->Roughness inversion: Loads gloss, inverts using float math (`1.0 - img/norm`), stores as float32 with original dtype. Prioritizes gloss source if both gloss and native rough exist.
        *   Resizes using `cv2.resize` (interpolation: `INTER_LANCZOS4` for downscale, `INTER_CUBIC` for potential same-size/upscale - though upscaling is generally avoided by checks).
        *   Determines output format based on hierarchy: `FORCE_LOSSLESS_MAP_TYPES` > `RESOLUTION_THRESHOLD_FOR_JPG` > Input format priority (TIF/EXR often lead to lossless) > Configured defaults (`OUTPUT_FORMAT_16BIT_PRIMARY`, `OUTPUT_FORMAT_8BIT`).
        *   Determines output bit depth based on `MAP_BIT_DEPTH_RULES` ('respect' vs 'force_8bit').
        *   Converts dtype before saving (e.g., float to uint8/uint16 using scaling factors 255.0/65535.0).
        *   Calculates stats (`_calculate_image_stats`) on normalized float64 data (in RGB space) for a specific resolution (`CALCULATE_STATS_RESOLUTION`).
        *   Calculates aspect ratio string (`_normalize_aspect_ratio_change`) based on relative dimension changes.
        *   Handles save fallback: If primary 16-bit format (e.g., EXR) fails, attempts fallback (e.g., PNG).
    *   **Merging (`_merge_maps_from_source`):**
        *   Identifies the required *source* files for merge inputs based on classified files.
        *   Determines common resolutions based on available processed maps (as a proxy for size compatibility).
        *   Loads required source maps for each common resolution using the `_load_and_transform_source` helper (utilizing the cache).
        *   Converts loaded inputs to float32 (normalized 0-1).
        *   Injects default values (from rule `defaults`) for missing channels.
        *   Merges channels using `cv2.merge`.
        *   Determines output bit depth based on rule (`force_16bit`, `respect_inputs`).
        *   Determines output format based on complex rules (`config.py` and preset), considering the highest format among *source* inputs if not forced lossless or over JPG threshold. Handles JPG 16-bit conflict by forcing 8-bit.
        *   Saves the merged image using the `_save_image` helper, including final data type/color space conversions and fallback logic (e.g., EXR->PNG).
    *   **Metadata (`_determine_base_metadata`, `_determine_single_asset_metadata`, `_generate_metadata_file`):**
        *   Base name determined using `source_naming` separator/index from `Configuration`, with fallback to common prefix or input name. Handles multiple assets within one input.
        *   Category determined by model presence or `decal_keywords` from `Configuration`.
        *   Archetype determined by matching keywords in `archetype_rules` (from `Configuration`) against file stems/base name.
        *   Final `metadata.json` populated by accumulating results (map details, stats, features, etc.) during the per-asset processing loop.

*   **Blender Integration (`main.py:run_blender_script`, `gui/processing_handler.py:_run_blender_script_subprocess`):**
    *   Uses `subprocess.run` to execute Blender.
    *   Command includes `-b` (background), the target `.blend` file, `--python` followed by the script path (`blenderscripts/*.py`), and `--` separator.
    *   Arguments after `--` (currently just the `asset_root_dir`, and optionally the nodegroup blend path for the materials script) are passed to the Python script via `sys.argv`.
    *   Uses `--factory-startup` in GUI handler. Checks return code and logs stdout/stderr.

## State Management

*   **`Configuration` Object:** Holds the loaded and merged configuration state (core + preset) and compiled regex patterns. Designed to be immutable after initialization. Instantiated once per worker process.
*   **`AssetProcessor` Instance:** Primarily stateless between calls to `process()`. State *within* a `process()` call is managed through local variables scoped to the overall call or the per-asset loop (e.g., `current_asset_metadata`, `processed_maps_details_asset`). `self.classified_files` is populated once by `_inventory_and_classify_files` early in `process()` and then used read-only (filtered copies) within the per-asset loop.
*   **`main.py` (CLI):** Tracks overall run progress (processed, skipped, failed counts) based on results returned from worker processes.
*   **`gui/processing_handler.py`:** Manages the state of a GUI processing run using internal flags (`_is_running`, `_cancel_requested`) and stores `Future` objects in `self._futures` dictionary while the pool is active.
*   **Image Data:** `numpy.ndarray` (Handled by OpenCV).

## Error Handling & Propagation

*   **Custom Exceptions:** `ConfigurationError` (raised by `Configuration` on load/validation failure), `AssetProcessingError` (raised by `AssetProcessor` for various processing failures).
*   **Configuration:** `ConfigurationError` halts initialization. Regex compilation errors are logged as warnings but do not stop initialization.
*   **AssetProcessor:** Uses `try...except Exception` within key pipeline steps (`_process_maps`, `_merge_maps`, etc.) and within the per-asset loop in `process()`. Errors specific to one asset are logged (`log.error(exc_info=True)`), the asset is marked "failed" in the returned status dictionary, and the loop continues to the next asset. Critical setup errors (e.g., workspace creation) raise `AssetProcessingError`, halting the entire `process()` call. Includes specific save fallback logic (EXR->PNG) on `cv2.imwrite` failure for 16-bit formats.
*   **Worker Wrapper (`main.py:process_single_asset_wrapper`):** Catches `ConfigurationError`, `AssetProcessingError`, and general `Exception` during worker execution. Logs the error and returns a ("failed", error_message) status tuple to the main process.
*   **Process Pool (`main.py`, `gui/processing_handler.py`):** The `with ProcessPoolExecutor(...)` block handles pool setup/teardown. A `try...except` around `as_completed` or `future.result()` catches critical worker failures (e.g., process crash).
*   **GUI Communication (`ProcessingHandler`):** Catches exceptions during `future.result()` retrieval. Emits `file_status_updated` signal with "failed" status and error message. Emits `processing_finished` with final counts.
*   **Blender Scripts:** Checks `subprocess.run` return code. Logs stderr as ERROR if return code is non-zero, otherwise as WARNING. Catches `FileNotFoundError` if the Blender executable path is invalid.

## Key Data Structures

*   **`Configuration` Instance Attributes:**
    *   `compiled_map_keyword_regex`: `dict[str, list[tuple[re.Pattern, str, int]]]` (Base type -> list of compiled regex tuples)
    *   `compiled_extra_regex`, `compiled_model_regex`: `list[re.Pattern]`
    *   `compiled_bit_depth_regex_map`: `dict[str, re.Pattern]` (Base type -> compiled regex)
*   **`AssetProcessor` Internal Structures (within `process()`):**
    *   `self.classified_files`: `dict[str, list[dict]]` (Category -> list of file info dicts like `{'source_path': Path, 'map_type': str, ...}`)
    *   `processed_maps_details_asset`, `merged_maps_details_asset`: `dict[str, dict[str, dict]]` (Map Type -> Resolution Key -> Details Dict `{'path': Path, 'width': int, ...}`)
    *   `file_to_base_name_map`: `dict[Path, Optional[str]]` (Source relative path -> Determined asset base name or None)
    *   `current_asset_metadata`: `dict` (Accumulates name, category, archetype, stats, map details per asset)
*   **Return Values:**
    *   `AssetProcessor.process()`: `Dict[str, List[str]]` (e.g., `{"processed": [...], "skipped": [...], "failed": [...]}`)
    *   `main.process_single_asset_wrapper()`: `Tuple[str, str, Optional[str]]` (input_path, status_string, error_message)
*   **`ProcessingHandler._futures`:** `dict[Future, str]` (Maps `concurrent.futures.Future` object to the input path string)
*   **Image Data:** `numpy.ndarray` (Handled by OpenCV).

## Concurrency Models (CLI & GUI)

*   **Common Core:** Both CLI and GUI utilize `concurrent.futures.ProcessPoolExecutor` for parallel processing. The target function executed by workers is `main.process_single_asset_wrapper`.
*   **Isolation:** Crucially, `Configuration` and `AssetProcessor` objects are instantiated *within* the `process_single_asset_wrapper` function, meaning each worker process gets its own independent configuration and processor instance based on the arguments passed. This prevents state conflicts between concurrent asset processing tasks. Data is passed between the main process and workers via pickling of arguments and return values.
*   **CLI Orchestration (`main.py:run_processing`):**
    *   Creates the `ProcessPoolExecutor`.
    *   Submits all `process_single_asset_wrapper` tasks.
    *   Uses `concurrent.futures.as_completed` to iterate over finished futures as they complete, blocking until the next one is done.
    *   Gathers results synchronously within the main script's execution flow.
*   **GUI Orchestration (`gui/processing_handler.py`):**
    *   The `ProcessingHandler` object (a `QObject`) contains the `run_processing` method.
    *   This method is intended to be run in a separate `QThread` (managed by `MainWindow`) to avoid blocking the main UI thread.
    *   Inside `run_processing`, it creates and manages the `ProcessPoolExecutor`.
    *   It uses `as_completed` similarly to the CLI to iterate over finished futures.
    *   **Communication:** Instead of blocking the thread gathering results, it emits Qt signals (`progress_updated`, `file_status_updated`, `processing_finished`) from within the `as_completed` loop. These signals are connected to slots in `MainWindow` (running on the main UI thread), allowing for thread-safe updates to the GUI (progress bar, table status, status bar messages).
*   **Cancellation (GUI - `gui/processing_handler.py:request_cancel`):**
    *   Sets an internal `_cancel_requested` flag.
    *   Attempts `executor.shutdown(wait=False)` which prevents new tasks from starting and may cancel pending ones (depending on Python version).
    *   Manually iterates through stored `_futures` and calls `future.cancel()` on those not yet running or done.
    *   **Limitation:** This does *not* forcefully terminate worker processes that are already executing the `process_single_asset_wrapper` function. Cancellation primarily affects pending tasks and the processing of results from already running tasks (they will be marked as failed/cancelled when their future completes).

## Resource Management

*   **Configuration:** Preset JSON files are opened and closed using `with open(...)`.
*   **AssetProcessor:**
    *   Temporary workspace directory created using `tempfile.mkdtemp()`.
    *   Cleanup (`_cleanup_workspace`) uses `shutil.rmtree()` and is called within a `finally` block in the main `process()` method, ensuring cleanup attempt even if errors occur.
    *   Metadata JSON file written using `with open(...)`.
    *   Image data is loaded into memory using OpenCV/NumPy; memory usage depends on image size and number of concurrent workers.
*   **Process Pool:** The `ProcessPoolExecutor` manages the lifecycle of worker processes. Using it within a `with` statement (as done in `main.py` and `gui/processing_handler.py`) ensures proper shutdown and resource release for the pool itself.

## Known Limitations & Edge Cases

*   **Configuration:**
    *   Validation (`_validate_configs`) is primarily structural (key presence, basic types), not deeply logical (e.g., doesn't check if regex patterns are *sensible*).
    *   Regex compilation errors in `_compile_regex_patterns` are logged as warnings but don't prevent `Configuration` initialization, potentially leading to unexpected classification later.
    *   `_fnmatch_to_regex` helper only handles basic `*` and `?` wildcards. Complex fnmatch patterns might not translate correctly.
*   **AssetProcessor:**
    *   Heavily reliant on correct filename patterns and rules defined in presets. Ambiguous or incorrect patterns lead to misclassification.
    *   Potential for high memory usage when processing very large images, especially with many workers.
    *   Error handling within `process()` is per-asset; a failure during map processing for one asset marks the whole asset as failed, without attempting other maps for that asset. No partial recovery within an asset.
    *   Gloss->Roughness inversion assumes gloss map is single channel or convertible to grayscale.
    *   `predict_output_structure` and `get_detailed_file_predictions` use simplified logic (e.g., assuming PNG output, highest resolution only) and may not perfectly match final output names/formats in all cases.
    *   Filename sanitization (`_sanitize_filename`) is basic and might not cover all edge cases for all filesystems.
*   **CLI (`main.py`):**
    *   Preset existence check (`{preset}.json`) happens only in the main process before workers start.
    *   Blender executable finding logic relies on `config.py` path being valid or `blender` being in the system PATH.
*   **GUI Concurrency (`gui/processing_handler.py`):**
    *   Cancellation (`request_cancel`) is not immediate for tasks already running in worker processes. It prevents new tasks and stops processing results from completed futures once the flag is checked.
*   **General:**
    *   Limited input format support (ZIP archives, folders). Internal file formats limited by OpenCV (`cv2.imread`, `cv2.imwrite`). Optional `OpenEXR` package recommended for full EXR support.
    *   Error messages propagated from workers might lack full context in some edge cases.