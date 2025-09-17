# User Guide: Usage - Automated GUI Testing (`autotest.py`)

This document explains how to use the `autotest.py` script for automated sanity checks of the Asset Processor Tool's GUI-driven workflow.

## Overview

The `autotest.py` script provides a way to run predefined test scenarios headlessly (without displaying the GUI). It simulates the core user actions: loading an asset, selecting a preset, allowing rules to be predicted, processing the asset, and then checks the results against expectations. This is primarily intended as a developer tool for regression testing and ensuring core functionality remains stable.

## Running the Autotest Script

From the project root directory, you can run the script using Python:

```bash
python autotest.py [OPTIONS]
```

### Command-Line Options

The script accepts several command-line arguments to configure the test run. If not provided, they use predefined default values.

*   `--zipfile PATH_TO_ZIP`:
    *   Specifies the path to the input asset `.zip` file to be used for the test.
    *   Default: `TestFiles/BoucleChunky001.zip`
*   `--preset PRESET_NAME`:
    *   Specifies the name of the preset to be selected and used for rule prediction and processing.
    *   Default: `Dinesen`
*   `--expectedrules PATH_TO_JSON`:
    *   Specifies the path to a JSON file containing the expected rule structure that should be generated after the preset is applied to the input asset.
    *   Default: `TestFiles/test-BoucleChunky001.json`
*   `--outputdir PATH_TO_DIR`:
    *   Specifies the directory where the processed assets will be written.
    *   Default: `TestFiles/TestOutputs/DefaultTestOutput`
*   `--search "SEARCH_TERM"` (optional):
    *   A string to search for within the application logs generated during the test run. If found, matching log lines (with context) will be highlighted.
    *   Default: None
*   `--additional-lines NUM_LINES` (optional):
    *   When using `--search`, this specifies how many lines of context before and after each matching log line should be displayed. A good non-zero value is 1-2.
    *   Default: `0`

**Example Usage:**

```bash
# Run with default test files and settings
python autotest.py

# Run with specific test files and search for a log message
python autotest.py --zipfile TestFiles/MySpecificAsset.zip --preset MyPreset --expectedrules TestFiles/MySpecificAsset_rules.json --outputdir TestFiles/TestOutputs/MySpecificOutput --search "Processing complete for asset"
```

## `TestFiles` Directory

The autotest script relies on a directory named `TestFiles` located in the project root. This directory should contain:

*   **Test Asset `.zip` files:** The actual asset archives used as input for tests (e.g., `default_test_asset.zip`, `MySpecificAsset.zip`).
*   **Expected Rules `.json` files:** JSON files defining the expected rule structure for a given asset and preset combination (e.g., `default_test_asset_rules.json`, `MySpecificAsset_rules.json`). The structure of this file is detailed in the main autotest plan (`AUTOTEST_GUI_PLAN.md`).
*   **`TestOutputs/` subdirectory:** This is the default parent directory where the autotest script will create specific output folders for each test run (e.g., `TestFiles/TestOutputs/DefaultTestOutput/`).

## Test Workflow

When executed, `autotest.py` performs the following steps:

1.  **Initialization:** Parses command-line arguments and initializes the main application components headlessly.
2.  **Load Expected Rules:** Loads the `expected_rules.json` file.
3.  **Load Asset:** Loads the specified `.zip` file into the application.
4.  **Select Preset:** Selects the specified preset. This triggers the internal rule prediction process.
5.  **Await Prediction:** Waits for the rule prediction to complete.
6.  **Compare Rules:** Retrieves the predicted rules from the application and compares them against the loaded expected rules. If there's a mismatch, the test typically fails at this point.
7.  **Start Processing:** If the rules match, it initiates the asset processing pipeline, directing output to the specified output directory.
8.  **Await Processing:** Waits for all backend processing tasks to complete.
9.  **Check Output:** Verifies the existence of the output directory and lists its contents. Basic checks ensure some output was generated.
10. **Analyze Logs:** Retrieves logs from the application. If a search term was provided, it filters and displays relevant log portions. It also checks for Python tracebacks, which usually indicate a failure.
11. **Report Result:** Prints a summary of the test outcome (success or failure) and exits with an appropriate status code (0 for success, 1 for failure).

## Interpreting Results

*   **Console Output:** The script will log its progress and the results of each step to the console.
*   **Log Analysis:** Pay attention to the log output, especially if a `--search` term was used or if any tracebacks are reported.
*   **Exit Code:**
    *   `0`: Test completed successfully.
    *   `1`: Test failed at some point (e.g., rule mismatch, processing error, traceback found).
*   **Output Directory:** Inspect the contents of the specified output directory to manually verify the processed assets if needed.

This automated test helps ensure the stability of the core processing logic when driven by GUI-equivalent actions.

Note: Under some conditions, the autotest will exit with errorcode "3221226505". This has no consequence and can therefor be ignore.