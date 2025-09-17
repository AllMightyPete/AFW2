# Plan for Autotest GUI Mode Implementation

**I. Objective:**
Create an `autotest.py` script that can launch the Asset Processor GUI headlessly, load a predefined asset (`.zip`), select a predefined preset, verify the predicted rule structure against an expected JSON, trigger processing to a predefined output directory, check the output, and analyze logs for errors or specific messages. This serves as a sanity check for core GUI-driven workflows.

**II. `TestFiles` Directory:**
A new directory named `TestFiles` will be created in the project root (`c:/Users/Theis/Assetprocessor/Asset-Frameworker/TestFiles/`). This directory will house:
*   Sample asset `.zip` files for testing (e.g., `TestFiles/SampleAsset1.zip`).
*   Expected rule structure JSON files (e.g., `TestFiles/SampleAsset1_PresetX_expected_rules.json`).
*   A subdirectory for test outputs (e.g., `TestFiles/TestOutputs/`).

**III. `autotest.py` Script:**

1.  **Location:** `c:/Users/Theis/Assetprocessor/Asset-Frameworker/autotest.py` (or `scripts/autotest.py`).
2.  **Command-Line Arguments (with defaults pointing to `TestFiles/`):**
    *   `--zipfile`: Path to the test asset. Default: `TestFiles/default_test_asset.zip`.
    *   `--preset`: Name of the preset. Default: `DefaultTestPreset`.
    *   `--expectedrules`: Path to expected rules JSON. Default: `TestFiles/default_test_asset_rules.json`.
    *   `--outputdir`: Path for processing output. Default: `TestFiles/TestOutputs/DefaultTestOutput`.
    *   `--search` (optional): Log search term. Default: `None`.
    *   `--additional-lines` (optional): Context lines for log search. Default: `0`.
3.  **Core Structure:**
    *   Imports necessary modules from the main application and PySide6.
    *   Adds project root to `sys.path` for imports.
    *   `AutoTester` class:
        *   **`__init__(self, app_instance: App)`:**
            *   Stores `app_instance` and `main_window`.
            *   Initializes `QEventLoop`.
            *   Connects `app_instance.all_tasks_finished` to `self._on_all_tasks_finished`.
            *   Loads expected rules from the `--expectedrules` file.
        *   **`run_test(self)`:** Orchestrates the test steps sequentially:
            1.  Load ZIP (`main_window.add_input_paths()`).
            2.  Select Preset (`main_window.preset_editor_widget.editor_preset_list.setCurrentItem()`).
            3.  Await Prediction (using `QTimer` to poll `main_window._pending_predictions`, manage with `QEventLoop`).
            4.  Retrieve & Compare Rulelist:
                *   Get actual rules: `main_window.unified_model.get_all_source_rules()`.
                *   Convert actual rules to comparable dict (`_convert_rules_to_comparable()`).
                *   Compare with loaded expected rules (`_compare_rules()`). If mismatch, log and fail.
            5.  Start Processing (emit `main_window.start_backend_processing` with rules and output settings).
            6.  Await Processing (use `QEventLoop` waiting for `_on_all_tasks_finished`).
            7.  Check Output Path (verify existence of output dir, list contents, basic sanity checks like non-emptiness or presence of key asset folders).
            8.  Retrieve & Analyze Logs (`main_window.log_console.log_console_output.toPlainText()`, filter by `--search`, check for tracebacks).
            9.  Report result and call `cleanup_and_exit()`.
        *   **`_check_prediction_status(self)`:** Slot for prediction polling timer.
        *   **`_on_all_tasks_finished(self, processed_count, skipped_count, failed_count)`:** Slot for `App.all_tasks_finished` signal.
        *   **`_convert_rules_to_comparable(self, source_rules_list: List[SourceRule]) -> dict`:** Converts `SourceRule` objects to the JSON structure defined below.
        *   **`_compare_rules(self, actual_rules_data: dict, expected_rules_data: dict) -> bool`:** Implements Option 1 comparison logic:
            *   Errors if an expected field is missing or its value mismatches.
            *   Logs (but doesn't error on) fields present in actual but not in expected.
        *   **`_process_and_display_logs(self, logs_text: str)`:** Handles log filtering/display.
        *   **`cleanup_and_exit(self, success=True)`:** Quits `QCoreApplication` and `sys.exit()`.
    *   `main()` function:
        *   Parses CLI arguments.
        *   Initializes `QApplication`.
        *   Instantiates `main.App()` (does *not* show the GUI).
        *   Instantiates `AutoTester(app_instance)`.
        *   Uses `QTimer.singleShot(0, tester.run_test)` to start the test.
        *   Runs `q_app.exec()`.

**IV. `expected_rules.json` Structure (Revised):**
Located in `TestFiles/`. Example: `TestFiles/SampleAsset1_PresetX_expected_rules.json`.
```json
{
  "source_rules": [
    {
      "input_path": "SampleAsset1.zip",
      "supplier_identifier": "ExpectedSupplier",
      "preset_name": "PresetX",
      "assets": [
        {
          "asset_name": "AssetNameFromPrediction",
          "asset_type": "Prop",
          "files": [
            {
              "file_path": "relative/path/to/file1.png",
              "item_type": "MAP_COL",
              "target_asset_name_override": null
            }
          ]
        }
      ]
    }
  ]
}
```

**V. Mermaid Diagram of Autotest Flow:**
```mermaid
graph TD
    A[Start autotest.py with CLI Args (defaults to TestFiles/)] --> B{Setup Args & Logging};
    B --> C[Init QApplication & main.App (GUI Headless)];
    C --> D[Instantiate AutoTester(app_instance)];
    D --> E[QTimer.singleShot -> AutoTester.run_test()];

    subgraph AutoTester.run_test()
        E --> F[Load Expected Rules from --expectedrules JSON];
        F --> G[Load ZIP (--zipfile) via main_window.add_input_paths()];
        G --> H[Select Preset (--preset) via main_window.preset_editor_widget];
        H --> I[Await Prediction (Poll main_window._pending_predictions via QTimer & QEventLoop)];
        I -- Prediction Done --> J[Get Actual Rules from main_window.unified_model];
        J --> K[Convert Actual Rules to Comparable JSON Structure];
        K --> L{Compare Actual vs Expected Rules (Option 1 Logic)};
        L -- Match --> M[Start Processing (Emit main_window.start_backend_processing with --outputdir)];
        L -- Mismatch --> ZFAIL[Log Mismatch & Call cleanup_and_exit(False)];
        M --> N[Await Processing (QEventLoop for App.all_tasks_finished signal)];
        N -- Processing Done --> O[Check Output Dir (--outputdir): Exists? Not Empty? Key Asset Folders?];
        O --> P[Retrieve & Analyze Logs (Search, Tracebacks)];
        P --> Q[Log Test Success & Call cleanup_and_exit(True)];
    end

    ZFAIL --> ZEND[AutoTester.cleanup_and_exit() -> QCoreApplication.quit() & sys.exit()];
    Q --> ZEND;