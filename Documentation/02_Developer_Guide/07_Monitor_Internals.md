# Developer Guide: Monitor Internals

This document provides technical details about the implementation of the Directory Monitor script (`monitor.py`) for developers.

## Overview

The `monitor.py` script provides an automated way to process assets by monitoring a specified input directory for new archive files. It has been refactored to use a `ThreadPoolExecutor` for asynchronous processing.

## Key Components

*   **`watchdog` Library:** Used for monitoring file system events (specifically file creation) in the `INPUT_DIR`. A `PollingObserver` is typically used.
*   **`concurrent.futures.ThreadPoolExecutor`:** Manages a pool of worker threads to process detected archives concurrently. The number of workers can often be configured (e.g., via `NUM_WORKERS` environment variable).
*   **`_process_archive_task` Function:** The core function executed by the thread pool for each detected archive. It encapsulates the entire processing workflow for a single archive.
*   **`utils.prediction_utils.generate_source_rule_from_archive`:** A utility function called by `_process_archive_task` to perform rule-based prediction directly on the archive file and generate the necessary `SourceRule` object.
*   **`utils.workspace_utils.prepare_processing_workspace`:** A utility function called by `_process_archive_task` to create a temporary workspace and extract the archive contents into it.
*   **`ProcessingEngine` (`processing_engine.py`):** The core engine instantiated and run within `_process_archive_task` to perform the actual asset processing based on the generated `SourceRule`.
*   **`Configuration` (`configuration.py`):** Loaded within `_process_archive_task` based on the preset derived from the archive filename.

## Functionality Details (Asynchronous Workflow)

1.  **Watching:** A `watchdog` observer monitors the `INPUT_DIR` for file creation events.
2.  **Event Handling:** When a file is created, an event handler (e.g., `on_created` method) is triggered.
3.  **Archive Detection:** The handler checks if the new file is a supported archive type (e.g., `.zip`, `.rar`, `.7z`).
4.  **Filename Parsing:** If it's a supported archive, the script attempts to parse the filename to extract the intended preset name (e.g., using a regex like `[preset]_filename.ext`).
5.  **Preset Validation:** The extracted preset name is validated against existing preset files (`Presets/*.json`).
6.  **Task Submission:** If the preset is valid, the path to the archive file and the validated preset name are submitted as a task to the `ThreadPoolExecutor`, which will eventually run the `_process_archive_task` function with these arguments in a worker thread.
7.  **`_process_archive_task` Execution (Worker Thread):**
    *   **Load Configuration:** Loads the `Configuration` object using the provided preset name.
    *   **Generate SourceRule:** Calls `utils.prediction_utils.generate_source_rule_from_archive`, passing the archive path and `Configuration`. This utility handles temporary extraction (if needed internally) and rule-based prediction, returning the `SourceRule`.
    *   **Prepare Workspace:** Calls `utils.workspace_utils.prepare_processing_workspace`, passing the archive path. This creates a unique temporary directory and extracts the archive contents. It returns the path to the prepared workspace. This step should ideally be wrapped in a `try...finally` block to ensure cleanup.
    *   **Instantiate Engine:** Creates an instance of the `ProcessingEngine`, passing the loaded `Configuration` and the prepared workspace path.
    *   **Run Processing:** Calls the `ProcessingEngine.process()` method, passing the generated `SourceRule`.
    *   **Handle Results:** Based on the success or failure of the processing, moves the original source archive file from `INPUT_DIR` to either `PROCESSED_DIR` or `ERROR_DIR`.
    *   **Cleanup Workspace:** Ensures the temporary workspace directory created by `prepare_processing_workspace` is removed (e.g., in the `finally` block).

## Configuration

The monitor's behavior is controlled by environment variables or configuration settings, likely including `INPUT_DIR`, `OUTPUT_DIR`, `PROCESSED_DIR`, `ERROR_DIR`, `LOG_LEVEL`, `POLL_INTERVAL`, and potentially `NUM_WORKERS` to control the size of the `ThreadPoolExecutor`.

## Limitations

*   The monitor likely still does *not* support triggering optional Blender script execution post-processing, as this integration point was complex and potentially removed or not yet reimplemented in the refactored workflow.

Understanding the asynchronous nature, the role of the `ThreadPoolExecutor`, the `_process_archive_task` function, and the reliance on utility modules (`prediction_utils`, `workspace_utils`) is key to debugging or modifying the directory monitoring functionality.