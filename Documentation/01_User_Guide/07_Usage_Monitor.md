# User Guide: Usage - Directory Monitor (Automated Processing)

This document explains how to use the Asset Processor Tool's Directory Monitor for automated processing.

## Running the Monitor

From the project root directory, run the following command:

```bash
python monitor.py
```

## Functionality

The monitor script uses the `watchdog` library to continuously monitor a specified input directory for new `.zip`, `.rar`, or `.7z` files. When a new supported archive file is detected, it expects the filename to follow the format `[preset]_filename.zip`, `[preset]_filename.rar`, or `[preset]_filename.7z`. It extracts the preset name from the filename and automatically processes the asset using that preset. After processing, the source archive file is moved to either a 'processed' directory (on success or skip) or an 'error' directory (on failure or invalid preset).

**Note:** The directory monitor does *not* currently support optional Blender script execution (this is only available via the CLI or GUI).

## Configuration (Environment Variables)

The monitor's behavior is configured using environment variables:

*   `INPUT_DIR`: The directory to monitor (default: `/data/input`).
*   `OUTPUT_DIR`: The base output directory (default: `/data/output`).
*   `PROCESSED_DIR`: Directory for successful source ZIPs (default: `/data/processed`).
*   `ERROR_DIR`: Directory for failed source ZIPs (default: `/data/error`).
*   `LOG_LEVEL`: Logging verbosity (`INFO`, `DEBUG`) (default: `INFO`).
*   `POLL_INTERVAL`: Check frequency (seconds) (default: `5`).
*   `PROCESS_DELAY`: Delay before processing detected file (seconds) (default: `2`).
*   `NUM_WORKERS`: Number of parallel workers (default: auto).

## Output

The monitor logs messages to the console. It creates processed assets in the `OUTPUT_DIR` and moves the source `.zip` file as described above.