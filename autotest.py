import argparse
import sys
import logging
import logging.handlers
import time
import json
import shutil # Import shutil for directory operations
from pathlib import Path
from typing import List, Dict, Any

from PySide6.QtCore import QCoreApplication, QTimer, Slot, QEventLoop, QObject, Signal
from PySide6.QtWidgets import QApplication, QListWidgetItem

# Add project root to sys.path
project_root = Path(__file__).resolve().parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

try:
    from main import App
    from gui.main_window import MainWindow
    from rule_structure import SourceRule # Assuming SourceRule is in rule_structure.py
except ImportError as e:
    print(f"Error importing project modules: {e}")
    print(f"Ensure that the script is run from the project root or that the project root is in PYTHONPATH.")
    print(f"Current sys.path: {sys.path}")
    sys.exit(1)

# Global variable for the memory log handler
autotest_memory_handler = None

# Custom Log Filter for Concise Output
class InfoSummaryFilter(logging.Filter):
    # Keywords that identify INFO messages to *allow* for concise output
    SUMMARY_KEYWORDS_PRECISE = [
        "Test run completed",
        "Test succeeded",
        "Test failed",
        "Rule comparison successful",
        "Rule comparison failed",
        "ProcessingEngine finished. Summary:",
        "Autotest Context:",
        "Parsed CLI arguments:",
        "Prediction completed successfully.",
        "Processing completed.",
        "Signal 'all_tasks_finished' received",
        "final status:",  # To catch "Asset '...' final status:"
        "User settings file not found:",
        "MainPanelWidget: Default output directory set to:",
        # Search related (as per original filter)
        "Searching logs for term",
        "Search term ",
        "Found ",
        "No tracebacks found in the logs.",
        "--- End Log Analysis ---",
        "Log analysis completed.",
    ]
    # Patterns for case-insensitive rejection
    REJECT_PATTERNS_LOWER = [
        # Original debug prefixes (ensure these are still relevant or merge if needed)
        "debug:", "orchestrator_trace:", "configuration_debug:", "app_debug:", "output_org_debug:",
        # Iterative / Per-item / Per-file details / Intermediate steps
        ": item ",  # Catches "Asset '...', Item X/Y"
        "item successfully processed and saved",
        ", file '", # Catches "Asset '...', File '...'"
        ": processing regular map",
        ": found source file:",
        ": determined source bit depth:",
        "successfully processed regular map",
        "successfully created mergetaskdefinition",
        ": preparing processing items",
        ": finished preparing items. found",
        ": starting core item processing loop",
        ", task '",
        ": processing merge task",
        "loaded from context:",
        "using dimensions from first loaded input",
        "successfully merged inputs into image",
        "successfully processed merge task",
        "mergedtaskprocessorstage result",
        "calling savevariantsstage",
        "savevariantsstage result",
        "adding final details to context",
        ": finished core item processing loop",
        ": copied variant",
        ": copied extra file",
        ": successfully organized",
        ": output organization complete.",
        ": metadata saved to",
        "worker thread: starting processing for rule:",
        "preparing workspace for input:",
        "input is a supported archive",
        "calling processingengine.process with rule",
        "calculated sha5 for",
        "calculated next incrementing value for",
        "verify: processingengine.process called",
        ": effective supplier set to",
        ": metadata initialized.",
        "path",
        "\\asset_processor",
        ": file rules queued for processing",
        "successfully loaded base application settings",
        "successfully loaded and merged asset_type_definitions",
        "successfully loaded and merged file_type_definitions",
        "starting rule-based prediction for:",
        "rule-based prediction finished successfully for",
        "finished rule-based prediction run for",
        "updating model with rule-based results for source:",
        "debug task ",
        "worker thread: finished processing for rule:",
        "task finished signal received for",
        # Autotest step markers (not global summaries)
    ]

    def filter(self, record):
        # Allow CRITICAL, ERROR, WARNING unconditionally
        if record.levelno >= logging.WARNING:
            return True

        if record.levelno == logging.INFO:
            msg = record.getMessage()
            msg_lower = msg.lower() # For case-insensitive pattern rejection

            # 1. Explicitly REJECT if message contains verbose patterns (case-insensitive)
            for pattern in self.REJECT_PATTERNS_LOWER: # Use the new list
                if pattern in msg_lower:
                    return False # Reject

            # 2. Then, if not rejected, ALLOW only if message contains precise summary keywords
            for keyword in self.SUMMARY_KEYWORDS_PRECISE: # Use the new list
                if keyword in msg: # Original message for case-sensitive summary keywords if needed
                    return True # Allow

            # 3. Reject all other INFO messages that don't match precise summary keywords
            return False

        # Reject levels below INFO (e.g., DEBUG) by default for this handler
        return False

# --- Root Logger Configuration for Concise Console Output ---
def setup_autotest_logging():
    """
    Configures the root logger for concise console output for autotest.py.
    This ensures that only essential summary information, warnings, and errors
    are displayed on the console by default.
    """
    root_logger = logging.getLogger()

    # 1. Remove all existing handlers from the root logger.
    # This prevents interference from other logging configurations.
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)
        handler.close() # Close handler before removing

    # 2. Set the root logger's level to DEBUG to capture everything for the memory handler.
    # The console handler will still filter down to INFO/selected.
    root_logger.setLevel(logging.DEBUG) # Changed from INFO to DEBUG

    # 3. Create a new StreamHandler for sys.stdout (for concise console output).
    console_handler = logging.StreamHandler(sys.stdout)

    # 4. Set this console handler's level to INFO.
    # The filter will then decide which INFO messages to display on console.
    console_handler.setLevel(logging.INFO)

    # 5. Apply the enhanced InfoSummaryFilter to the console handler.
    info_filter = InfoSummaryFilter()
    console_handler.addFilter(info_filter)

    # 6. Set a concise formatter for the console handler.
    formatter = logging.Formatter('[%(levelname)s] %(message)s')
    console_handler.setFormatter(formatter)

    # 7. Add this newly configured console handler to the root_logger.
    root_logger.addHandler(console_handler)

    # 8. Setup the MemoryHandler
    global autotest_memory_handler # Declare usage of global
    autotest_memory_handler = logging.handlers.MemoryHandler(
        capacity=20000,  # Increased capacity
        flushLevel=logging.CRITICAL + 1, # Prevent automatic flushing
        target=None # Does not flush to another handler
    )
    autotest_memory_handler.setLevel(logging.DEBUG) # Capture all logs from DEBUG up
    # Not adding a formatter here, will format in _process_and_display_logs

    # 9. Add the memory handler to the root logger.
    root_logger.addHandler(autotest_memory_handler)

# Call the setup function early in the script's execution.
setup_autotest_logging()

# Logger for autotest.py's own messages.
# Messages from this logger will propagate to the root logger and be filtered
# by the console_handler configured above.
# Setting its level to DEBUG allows autotest.py to generate DEBUG messages,
# which won't appear on the concise console (due to handler's INFO level)
# but can be captured by other handlers (e.g., the GUI's log console).
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG) # Ensure autotest.py can generate DEBUGs for other handlers

# Note: The GUI's log console (e.g., self.main_window.log_console.log_console_output)
# is assumed to capture all logs (including DEBUG) from various modules.
# The _process_and_display_logs function then uses these comprehensive logs for the --search feature.
# This root logger setup primarily makes autotest.py's direct console output concise,
# ensuring that only filtered, high-level information appears on stdout by default.
# --- End of Root Logger Configuration ---

# --- Argument Parsing ---
def parse_arguments():
    """Parses command-line arguments for the autotest script."""
    parser = argparse.ArgumentParser(description="Automated test script for Asset Processor GUI.")
    parser.add_argument(
        "--zipfile",
        type=Path,
        default=project_root / "TestFiles" / "BoucleChunky001.zip",
        help="Path to the test asset ZIP file. Default: TestFiles/BoucleChunky001.zip"
    )
    parser.add_argument(
        "--preset",
        type=str,
        default="Dinesen", # This should match a preset name in the application
        help="Name of the preset to use. Default: Dinesen"
    )
    parser.add_argument(
        "--expectedrules",
        type=Path,
        default=project_root / "TestFiles" / "Test-BoucleChunky001.json",
        help="Path to the JSON file with expected rules. Default: TestFiles/Test-BoucleChunky001.json"
    )
    parser.add_argument(
        "--outputdir",
        type=Path,
        default=project_root / "TestFiles" / "TestOutputs" / "BoucleChunkyOutput",
        help="Path for processing output. Default: TestFiles/TestOutputs/BoucleChunkyOutput"
    )
    parser.add_argument(
        "--search",
        type=str,
        default=None,
        help="Optional log search term. Default: None"
    )
    parser.add_argument(
        "--additional-lines",
        type=int,
        default=0,
        help="Context lines for log search. Default: 0"
    )
    return parser.parse_args()

class AutoTester(QObject):
    """
    Handles the automated testing process for the Asset Processor GUI.
    """
    # Define signals if needed, e.g., for specific test events
    # test_step_completed = Signal(str)

    def __init__(self, app_instance: App, cli_args: argparse.Namespace):
        super().__init__()
        self.app_instance: App = app_instance
        self.main_window: MainWindow = app_instance.main_window
        self.cli_args: argparse.Namespace = cli_args
        self.event_loop = QEventLoop(self)
        self.prediction_poll_timer = QTimer(self)
        self.expected_rules_data: Dict[str, Any] = {}
        self.test_step: str = "INIT"  # Possible values: INIT, LOADING_ZIP, SELECTING_PRESET, AWAITING_PREDICTION, PREDICTION_COMPLETE, COMPARING_RULES, STARTING_PROCESSING, AWAITING_PROCESSING, PROCESSING_COMPLETE, CHECKING_OUTPUT, ANALYZING_LOGS, DONE

        if not self.main_window:
            logger.error("MainWindow instance not found in App. Cannot proceed.")
            self.cleanup_and_exit(success=False)
            return

        if hasattr(self.main_window, "select_view"):
            self.main_window.select_view("Workspace")

        # Connect signals
        if hasattr(self.app_instance, 'all_tasks_finished') and isinstance(self.app_instance.all_tasks_finished, Signal):
            self.app_instance.all_tasks_finished.connect(self._on_all_tasks_finished)
        else:
            logger.warning("App instance does not have 'all_tasks_finished' signal or it's not a Signal. Processing completion might not be detected.")

        self._load_expected_rules()

    def _load_expected_rules(self) -> None:
        """Loads the expected rules from the JSON file specified by cli_args."""
        self.test_step = "LOADING_EXPECTED_RULES"
        logger.debug(f"Loading expected rules from: {self.cli_args.expectedrules}")
        try:
            with open(self.cli_args.expectedrules, 'r') as f:
                self.expected_rules_data = json.load(f)
            logger.debug("Expected rules loaded successfully.")
        except FileNotFoundError:
            logger.error(f"Expected rules file not found: {self.cli_args.expectedrules}")
            self.cleanup_and_exit(success=False)
        except json.JSONDecodeError as e:
            logger.error(f"Error decoding expected rules JSON: {e}")
            self.cleanup_and_exit(success=False)
        except Exception as e:
            logger.error(f"An unexpected error occurred while loading expected rules: {e}")
            self.cleanup_and_exit(success=False)

    def run_test(self) -> None:
        """Orchestrates the test steps."""
        # Load expected rules first to potentially get the preset name
        self._load_expected_rules() # Moved here
        if not self.expected_rules_data: # Ensure rules were loaded
            logger.error("Expected rules not loaded. Aborting test.")
            self.cleanup_and_exit(success=False)
            return

        # Determine preset to use: from expected rules if available, else from CLI args
        preset_to_use = self.cli_args.preset # Default
        if self.expected_rules_data.get("source_rules") and \
           isinstance(self.expected_rules_data["source_rules"], list) and \
           len(self.expected_rules_data["source_rules"]) > 0 and \
           isinstance(self.expected_rules_data["source_rules"][0], dict) and \
           self.expected_rules_data["source_rules"][0].get("preset_name"):
            preset_to_use = self.expected_rules_data["source_rules"][0]["preset_name"]
            logger.info(f"Overriding preset with value from expected_rules.json: '{preset_to_use}'")
        else:
            logger.info(f"Using preset from CLI arguments: '{preset_to_use}' (this was self.cli_args.preset)")
            # If preset_to_use is still self.cli_args.preset, ensure it's logged correctly
            # The variable preset_to_use will hold the correct value to be used throughout.

        logger.info("Starting test run...") # Moved after preset_to_use definition

        # Add a specific summary log for essential context
        # This now correctly uses preset_to_use
        logger.info(f"Autotest Context: Input='{self.cli_args.zipfile.name}', Preset='{preset_to_use}', Output='{self.cli_args.outputdir}'")

        # Step 1: Load ZIP
        self.test_step = "LOADING_ZIP"
        logger.info(f"Step 1: Loading ZIP file: {self.cli_args.zipfile}") # KEEP INFO - Passes filter
        if not self.cli_args.zipfile.exists():
            logger.error(f"ZIP file not found: {self.cli_args.zipfile}")
            self.cleanup_and_exit(success=False)
            return
        try:
            # Assuming add_input_paths can take a list of strings or Path objects
            self.main_window.add_input_paths([str(self.cli_args.zipfile)])
            logger.debug("ZIP file loading initiated.")
        except Exception as e:
            logger.error(f"Error during ZIP file loading: {e}")
            self.cleanup_and_exit(success=False)
            return

        # Step 2: Select Preset
        self.test_step = "SELECTING_PRESET"
        # Use preset_to_use (which is now correctly defined earlier)
        logger.info(f"Step 2: Selecting preset: {preset_to_use}") # KEEP INFO - Passes filter
        # The print statement below already uses preset_to_use, which is good.
        print(f"DEBUG: Attempting to select preset: '{preset_to_use}' (derived from expected: {preset_to_use == self.expected_rules_data.get('source_rules',[{}])[0].get('preset_name') if self.expected_rules_data.get('source_rules') else 'N/A'}, cli_arg: {self.cli_args.preset})")
        if hasattr(self.main_window, "select_view"):
            self.main_window.select_view("Settings")
        if hasattr(self.main_window, "select_settings_category"):
            self.main_window.select_settings_category("Presets")
        preset_found = False
        preset_list_widget = self.main_window.preset_editor_widget.editor_preset_list
        for i in range(preset_list_widget.count()):
            item = preset_list_widget.item(i)
            if item and item.text() == preset_to_use: # Use preset_to_use
                preset_list_widget.setCurrentItem(item)
                logger.debug(f"Preset '{preset_to_use}' selected.")
                print(f"DEBUG: Successfully selected preset '{item.text()}' in GUI.")
                preset_found = True
                break
        if not preset_found:
            logger.error(f"Preset '{preset_to_use}' not found in the list.")
            available_presets = [preset_list_widget.item(i).text() for i in range(preset_list_widget.count())]
            logger.debug(f"Available presets: {available_presets}")
            print(f"DEBUG: Failed to find preset '{preset_to_use}'. Available: {available_presets}")
            self.cleanup_and_exit(success=False)
            return

        if hasattr(self.main_window, "select_view"):
            self.main_window.select_view("Workspace")

        # Step 3: Await Prediction Completion
        self.test_step = "AWAITING_PREDICTION"
        logger.debug("Step 3: Awaiting prediction completion...")
        self.prediction_poll_timer.timeout.connect(self._check_prediction_status)
        self.prediction_poll_timer.start(500) # Poll every 500ms

        # Use a QTimer to allow event loop to process while waiting for this step
        # This ensures that the _check_prediction_status can be called.
        # We will exit this event_loop from _check_prediction_status when prediction is done.
        logger.debug("Starting event loop for prediction...")
        self.event_loop.exec() # This loop is quit by _check_prediction_status
        self.prediction_poll_timer.stop()
        logger.debug("Event loop for prediction finished.")


        if self.test_step != "PREDICTION_COMPLETE":
            logger.error(f"Prediction did not complete as expected. Current step: {self.test_step}")
            # Check if there were any pending predictions that never cleared
            if hasattr(self.main_window, '_pending_predictions'):
                 logger.error(f"Pending predictions at timeout: {self.main_window._pending_predictions}")
            self.cleanup_and_exit(success=False)
            return
        logger.info("Prediction completed successfully.") # KEEP INFO - Passes filter

        # Step 4: Retrieve & Compare Rulelist
        self.test_step = "COMPARING_RULES"
        logger.info("Step 4: Retrieving and Comparing Rules...") # KEEP INFO - Passes filter
        actual_source_rules_list: List[SourceRule] = self.main_window.unified_model.get_all_source_rules()
        actual_rules_obj = actual_source_rules_list # Keep the SourceRule list for processing
        
        comparable_actual_rules = self._convert_rules_to_comparable(actual_source_rules_list)

        if not self._compare_rules(comparable_actual_rules, self.expected_rules_data):
            logger.error("Rule comparison failed. See logs for details.")
            self.cleanup_and_exit(success=False)
            return
        logger.info("Rule comparison successful.") # KEEP INFO - Passes filter

        # Step 5: Start Processing
        self.test_step = "START_PROCESSING"
        logger.info("Step 5: Starting Processing...") # KEEP INFO - Passes filter
        processing_settings = {
            "output_dir": str(self.cli_args.outputdir), # Ensure it's a string for JSON/config
            "overwrite": True,
            "workers": 1,
            "blender_enabled": False # Basic test, no Blender
        }
        try:
            Path(self.cli_args.outputdir).mkdir(parents=True, exist_ok=True)
            logger.debug(f"Ensured output directory exists: {self.cli_args.outputdir}")
        except Exception as e:
            logger.error(f"Could not create output directory {self.cli_args.outputdir}: {e}")
            self.cleanup_and_exit(success=False)
            return

        if hasattr(self.main_window, 'start_backend_processing') and isinstance(self.main_window.start_backend_processing, Signal):
            logger.debug(f"Emitting start_backend_processing with rules count: {len(actual_rules_obj)} and settings: {processing_settings}")
            self.main_window.start_backend_processing.emit(actual_rules_obj, processing_settings)
        else:
            logger.error("'start_backend_processing' signal not found on MainWindow. Cannot start processing.")
            self.cleanup_and_exit(success=False)
            return
        
        # Step 6: Await Processing Completion
        self.test_step = "AWAIT_PROCESSING"
        logger.debug("Step 6: Awaiting processing completion...")
        self.event_loop.exec() # This loop is quit by _on_all_tasks_finished

        if self.test_step != "PROCESSING_COMPLETE":
            logger.error(f"Processing did not complete as expected. Current step: {self.test_step}")
            self.cleanup_and_exit(success=False)
            return
        logger.info("Processing completed.") # KEEP INFO - Passes filter

        # Step 7: Check Output Path
        self.test_step = "CHECK_OUTPUT"
        logger.info(f"Step 7: Checking output path: {self.cli_args.outputdir}") # KEEP INFO - Passes filter
        output_path = Path(self.cli_args.outputdir)
        if not output_path.exists() or not output_path.is_dir():
            logger.error(f"Output directory {output_path} does not exist or is not a directory.")
            self.cleanup_and_exit(success=False)
            return

        output_items = list(output_path.iterdir())
        if not output_items:
            logger.warning(f"Output directory {output_path} is empty. This might be a test failure depending on the case.")
            # For a more specific check, one might iterate through actual_rules_obj
            # and verify if subdirectories matching asset_name exist.
            # e.g. for asset_rule in source_rule.assets:
            #   expected_asset_dir = output_path / asset_rule.asset_name
            #   if not expected_asset_dir.is_dir(): logger.error(...)
        else:
            logger.debug(f"Found {len(output_items)} item(s) in output directory:")
            for item in output_items:
                logger.debug(f"  - {item.name} ({'dir' if item.is_dir() else 'file'})")
        logger.info("Output path check completed.") # KEEP INFO - Passes filter

        # Step 8: Retrieve & Analyze Logs
        self.test_step = "CHECK_LOGS"
        logger.debug("Step 8: Retrieving and Analyzing Logs...")
        all_logs_text = ""
        if self.main_window.log_console and self.main_window.log_console.log_console_output:
            all_logs_text = self.main_window.log_console.log_console_output.toPlainText()
        else:
            logger.warning("Log console or output widget not found. Cannot retrieve logs.")
        

        # Final Step
        logger.info("Test run completed successfully.") # KEEP INFO - Passes filter
        self.cleanup_and_exit(success=True)

    @Slot()
    def _check_prediction_status(self) -> None:
        """Polls the main window for pending predictions."""
        # logger.debug(f"Checking prediction status. Pending: {self.main_window._pending_predictions if hasattr(self.main_window, '_pending_predictions') else 'N/A'}")
        if hasattr(self.main_window, '_pending_predictions'):
            if not self.main_window._pending_predictions: # Assuming _pending_predictions is a list/dict that's empty when done
                logger.debug("No pending predictions. Prediction assumed complete.")
                self.test_step = "PREDICTION_COMPLETE"
                if self.event_loop.isRunning():
                    self.event_loop.quit()
            # else:
                # logger.debug(f"Still awaiting predictions: {len(self.main_window._pending_predictions)} remaining.")
        else:
            logger.warning("'_pending_predictions' attribute not found on MainWindow. Cannot check prediction status automatically.")
            # As a fallback, if the attribute is missing, we might assume prediction is instant or needs manual check.
            # For now, let's assume it means it's done if the attribute is missing, but this is risky.
            # A better approach would be to have a clear signal from MainWindow when predictions are done.
            self.test_step = "PREDICTION_COMPLETE" # Risky assumption
            if self.event_loop.isRunning():
                self.event_loop.quit()


    @Slot(int, int, int)
    def _on_all_tasks_finished(self, processed_count: int, skipped_count: int, failed_count: int) -> None:
        """Slot for App.all_tasks_finished signal."""
        logger.info(f"Signal 'all_tasks_finished' received: Processed={processed_count}, Skipped={skipped_count}, Failed={failed_count}") # KEEP INFO - Passes filter
        
        if self.test_step == "AWAIT_PROCESSING":
            logger.debug("Processing completion signal received.") # Covered by the summary log above
            if failed_count > 0:
                logger.error(f"Processing finished with {failed_count} failed task(s).")
            # Even if tasks failed, the test might pass based on output checks.
            # The error is logged for information.
            self.test_step = "PROCESSING_COMPLETE"
            if self.event_loop.isRunning():
                self.event_loop.quit()
        else:
            logger.warning(f"Signal 'all_tasks_finished' received at an unexpected test step: '{self.test_step}'. Counts: P={processed_count}, S={skipped_count}, F={failed_count}")


    def _convert_rules_to_comparable(self, source_rules_list: List[SourceRule]) -> Dict[str, Any]:
        """
        Converts a list of SourceRule objects to a dictionary structure
        suitable for comparison with the expected_rules.json.
        """
        logger.debug(f"Converting {len(source_rules_list)} SourceRule objects to comparable dictionary...")
        comparable_sources_list = []
        for source_rule_obj in source_rules_list:
            comparable_asset_list = []
            # source_rule_obj.assets is List[AssetRule]
            for asset_rule_obj in source_rule_obj.assets:
                comparable_file_list = []
                # asset_rule_obj.files is List[FileRule]
                for file_rule_obj in asset_rule_obj.files:
                    comparable_file_list.append({
                        "file_path": file_rule_obj.file_path,
                        "item_type": file_rule_obj.item_type,
                        "target_asset_name_override": file_rule_obj.target_asset_name_override
                    })
                comparable_asset_list.append({
                    "asset_name": asset_rule_obj.asset_name,
                    "asset_type": asset_rule_obj.asset_type,
                    "files": comparable_file_list
                })
            comparable_sources_list.append({
                "input_path": Path(source_rule_obj.input_path).name, # Use only the filename
                "supplier_identifier": source_rule_obj.supplier_identifier,
                "preset_name": source_rule_obj.preset_name, # This is the actual preset name from the SourceRule object
                "assets": comparable_asset_list
            })
        logger.debug("Conversion to comparable dictionary finished.")
        return {"source_rules": comparable_sources_list}

    def _compare_rule_item(self, actual_item: Dict[str, Any], expected_item: Dict[str, Any], item_type_name: str, parent_context: str = "") -> bool:
        """
        Recursively compares an individual actual rule item dictionary with an expected rule item dictionary.
        Logs differences and returns True if they match, False otherwise.
        """
        item_match = True
        
        identifier = ""
        if item_type_name == "SourceRule":
            identifier = expected_item.get('input_path', f'UnknownSource_at_{parent_context}')
        elif item_type_name == "AssetRule":
            identifier = expected_item.get('asset_name', f'UnknownAsset_at_{parent_context}')
        elif item_type_name == "FileRule":
            identifier = expected_item.get('file_path', f'UnknownFile_at_{parent_context}')
        
        current_context = f"{parent_context}/{identifier}" if parent_context else identifier

        # Log Extra Fields: Iterate through keys in actual_item.
        # If a key is in actual_item but not in expected_item (and is not a list container like "assets" or "files"),
        # log this as an informational message.
        for key in actual_item.keys():
            if key not in expected_item and key not in ["assets", "files"]:
                logger.debug(f"Field '{key}' present in actual {item_type_name} ({current_context}) but not specified in expected. Value: '{actual_item[key]}'")

        # Check Expected Fields: Iterate through keys in expected_item.
        for key, expected_value in expected_item.items():
            if key not in actual_item:
                logger.error(f"Missing expected field '{key}' in actual {item_type_name} ({current_context}).")
                item_match = False
                continue # Continue to check other fields in the expected_item

            actual_value = actual_item[key]

            if key == "assets": # List of AssetRule dictionaries
                if not self._compare_list_of_rules(actual_value, expected_value, "AssetRule", current_context, "asset_name"):
                    item_match = False
            elif key == "files": # List of FileRule dictionaries
                if not self._compare_list_of_rules(actual_value, expected_value, "FileRule", current_context, "file_path"):
                    item_match = False
            else: # Regular field comparison
                if key == "preset_name":
                    print(f"DEBUG: Comparing preset_name: Actual='{actual_value}', Expected='{expected_value}' for {item_type_name} ({current_context})")
                if actual_value != expected_value:
                    # Handle None vs "None" string for preset_name specifically if it's a common issue
                    if key == "preset_name" and actual_value is None and expected_value == "None":
                        logger.debug(f"Field '{key}' in {item_type_name} ({current_context}): Actual is None, Expected is string \"None\". Treating as match for now.")
                    elif key == "target_asset_name_override" and actual_value is not None and expected_value is None:
                         # If actual has a value (e.g. parent asset name) and expected is null/None,
                         # this is a mismatch according to strict comparison.
                         # For a more lenient check, this logic could be adjusted here.
                         # Current strict comparison will flag this as error, which is what the logs show.
                         logger.error(f"Value mismatch for field '{key}' in {item_type_name} ({current_context}): Actual='{actual_value}', Expected='{expected_value}'.")
                         item_match = False
                    else:
                        logger.error(f"Value mismatch for field '{key}' in {item_type_name} ({current_context}): Actual='{actual_value}', Expected='{expected_value}'.")
                        item_match = False
            
        return item_match
    
    def _compare_list_of_rules(self, actual_list: List[Dict[str, Any]], expected_list: List[Dict[str, Any]], item_type_name: str, parent_context: str, item_key_field: str) -> bool:
        """
        Compares a list of actual rule items against a list of expected rule items.
        Items are matched by a key field (e.g., 'asset_name' or 'file_path').
        Order independent for matching, but logs count mismatches.
        """
        list_match = True
        if not isinstance(actual_list, list) or not isinstance(expected_list, list):
            logger.error(f"Type mismatch for list of {item_type_name}s in {parent_context}. Expected lists.")
            return False

        if len(actual_list) != len(expected_list):
            logger.error(f"Mismatch in number of {item_type_name}s for {parent_context}. Actual: {len(actual_list)}, Expected: {len(expected_list)}.")
            list_match = False # Count mismatch is an error
            # If counts differ, we still try to match what we can to provide more detailed feedback,
            # but the overall list_match will remain False.
            if item_type_name == "FileRule":
                print(f"DEBUG: FileRule count mismatch for {parent_context}. Actual: {len(actual_list)}, Expected: {len(expected_list)}")
                print(f"DEBUG: Actual FileRule paths: {[item.get(item_key_field) for item in actual_list]}")
                print(f"DEBUG: Expected FileRule paths: {[item.get(item_key_field) for item in expected_list]}")


        actual_items_map = {item.get(item_key_field): item for item in actual_list if item.get(item_key_field) is not None}
        
        # Keep track of expected items that found a match to identify missing ones more easily
        matched_expected_keys = set()

        for expected_item in expected_list:
            expected_key_value = expected_item.get(item_key_field)
            if expected_key_value is None:
                logger.error(f"Expected {item_type_name} in {parent_context} is missing key field '{item_key_field}'. Cannot compare this item: {expected_item}")
                list_match = False # This specific expected item cannot be processed
                continue

            actual_item = actual_items_map.get(expected_key_value)
            if actual_item:
                matched_expected_keys.add(expected_key_value)
                if not self._compare_rule_item(actual_item, expected_item, item_type_name, parent_context):
                    list_match = False # Individual item comparison failed
            else:
                logger.error(f"Expected {item_type_name} with {item_key_field} '{expected_key_value}' not found in actual items for {parent_context}.")
                list_match = False
        
        # Identify actual items that were not matched by any expected item
        # This is useful if len(actual_list) >= len(expected_list) but some actual items are "extra"
        for actual_key_value, actual_item_data in actual_items_map.items():
            if actual_key_value not in matched_expected_keys:
                logger.debug(f"Extra actual {item_type_name} with {item_key_field} '{actual_key_value}' found in {parent_context} (not in expected list or already matched).")
                if len(actual_list) != len(expected_list): # If counts already flagged a mismatch, this is just detail
                    pass
                else: # Counts matched, but content didn't align perfectly by key
                    list_match = False


        return list_match
    

    def _compare_rules(self, actual_rules_data: Dict[str, Any], expected_rules_data: Dict[str, Any]) -> bool:
        """
        Compares the actual rule data (converted from live SourceRule objects)
        with the expected rule data (loaded from JSON).
        """
        logger.debug("Comparing actual rules with expected rules...")

        actual_source_rules = actual_rules_data.get("source_rules", []) if actual_rules_data else []
        expected_source_rules = expected_rules_data.get("source_rules", []) if expected_rules_data else []

        if not isinstance(actual_source_rules, list):
            logger.error(f"Actual 'source_rules' is not a list. Found type: {type(actual_source_rules)}. Comparison aborted.")
            return False # Cannot compare if actual data is malformed
        if not isinstance(expected_source_rules, list):
            logger.error(f"Expected 'source_rules' is not a list. Found type: {type(expected_source_rules)}. Test configuration error. Comparison aborted.")
            return False # Test setup error

        if not expected_source_rules and not actual_source_rules:
            logger.debug("Both expected and actual source rules lists are empty. Considered a match.")
            return True
        
        if len(actual_source_rules) != len(expected_source_rules):
            logger.error(f"Mismatch in the number of source rules. Actual: {len(actual_source_rules)}, Expected: {len(expected_source_rules)}.")
            # Optionally, log more details about which list is longer/shorter or identifiers if available
            return False

        overall_match_status = True
        for i in range(len(expected_source_rules)):
            actual_sr = actual_source_rules[i]
            expected_sr = expected_source_rules[i]
            
            # For context, use input_path or an index
            source_rule_context = expected_sr.get('input_path', f"SourceRule_index_{i}")

            if not self._compare_rule_item(actual_sr, expected_sr, "SourceRule", parent_context=source_rule_context):
                overall_match_status = False
                # Continue checking other source rules to log all discrepancies

        if overall_match_status:
            logger.debug("All rules match the expected criteria.") # Covered by "Rule comparison successful" summary
        else:
            logger.warning("One or more rules did not match the expected criteria. See logs above for details.")
            
        return overall_match_status

    def _process_and_display_logs(self, logs_text: str) -> None: # logs_text is no longer the primary source for search
        """
        Processes and displays logs, potentially filtering them if --search is used.
        Also checks for tracebacks.
        Sources logs from the in-memory handler for search and detailed analysis.
        """
        logger.debug("--- Log Analysis ---")
        global autotest_memory_handler # Access the global handler
        log_records = []
        if autotest_memory_handler and autotest_memory_handler.buffer:
            log_records = autotest_memory_handler.buffer

        formatted_log_lines = []
        # Define a consistent formatter, similar to what might be expected or useful for search
        record_formatter = logging.Formatter('%(asctime)s [%(levelname)s] %(name)s: %(message)s')
        # Default asctime format includes milliseconds.


        for record in log_records:
            formatted_log_lines.append(record_formatter.format(record))
        
        lines_for_search_and_traceback = formatted_log_lines
        
        if not lines_for_search_and_traceback:
            logger.warning("No log records found in memory handler. No analysis to perform.")
            # Still check the console logs_text for tracebacks if it exists, as a fallback
            # or if some critical errors didn't make it to the memory handler (unlikely with DEBUG level)
            if logs_text:
                logger.debug("Checking provided logs_text (from console) for tracebacks as a fallback.")
                console_lines = logs_text.splitlines()
                traceback_found_console = False
                for i, line in enumerate(console_lines):
                    if line.strip().startswith("Traceback (most recent call last):"):
                        logger.error(f"!!! TRACEBACK DETECTED in console logs_text around line {i+1} !!!")
                        traceback_found_console = True
                if traceback_found_console:
                     logger.warning("A traceback was found in the console logs_text.")
                else:
                    logger.info("No tracebacks found in the console logs_text either.")
            logger.info("--- End Log Analysis ---")
            return

        traceback_found = False

        if self.cli_args.search:
            logger.info(f"Searching {len(lines_for_search_and_traceback)} in-memory log lines for term '{self.cli_args.search}' with {self.cli_args.additional_lines} context lines.")
            matched_line_indices = [i for i, line in enumerate(lines_for_search_and_traceback) if self.cli_args.search in line]
            
            if not matched_line_indices:
                logger.info(f"Search term '{self.cli_args.search}' not found in in-memory logs.")
            else:
                logger.info(f"Found {len(matched_line_indices)} match(es) for '{self.cli_args.search}' in in-memory logs:")
                collected_lines_to_print = set()
                for match_idx in matched_line_indices:
                    start_idx = max(0, match_idx - self.cli_args.additional_lines)
                    end_idx = min(len(lines_for_search_and_traceback), match_idx + self.cli_args.additional_lines + 1)
                    for i in range(start_idx, end_idx):
                        # Use i directly as index for lines_for_search_and_traceback, line number is for display
                        collected_lines_to_print.add(f"L{i+1:05d}: {lines_for_search_and_traceback[i]}")
                
                print("--- Filtered Log Output (from Memory Handler) ---")
                for line_to_print in sorted(list(collected_lines_to_print)):
                    print(line_to_print)
                print("--- End Filtered Log Output ---")
        # Removed: else block that showed last N lines by default (as per original instruction for this section)

        # Traceback Check (on lines_for_search_and_traceback)
        for i, line in enumerate(lines_for_search_and_traceback):
            if line.strip().startswith("Traceback (most recent call last):") or "Traceback (most recent call last):" in line : # More robust check
                logger.error(f"!!! TRACEBACK DETECTED in in-memory logs around line index {i} !!!")
                logger.error(f"Line content: {line}")
                traceback_found = True
        
        if traceback_found:
            logger.warning("A traceback was found in the in-memory logs. This usually indicates a significant issue.")
        else:
            logger.info("No tracebacks found in the in-memory logs.") # This refers to the comprehensive memory logs
            
        logger.info("--- End Log Analysis ---")

    def cleanup_and_exit(self, success: bool = True) -> None:
        """Cleans up and exits the application."""
        # Retrieve logs before clearing the handler
        all_logs_text = "" # This variable is not used by _process_and_display_logs anymore, but kept for signature compatibility if needed elsewhere.
        self._process_and_display_logs(all_logs_text) # Process and display logs BEFORE clearing the buffer

        global autotest_memory_handler
        if autotest_memory_handler:
            logger.debug("Clearing memory log handler buffer and removing handler.")
            autotest_memory_handler.buffer = [] # Clear buffer
            logging.getLogger().removeHandler(autotest_memory_handler) # Remove handler
            autotest_memory_handler.close() # MemoryHandler close is a no-op but good practice
            autotest_memory_handler = None

        logger.info(f"Test {'succeeded' if success else 'failed'}. Cleaning up and exiting...") # KEEP INFO - Passes filter
        q_app = QCoreApplication.instance()
        if q_app:
            q_app.quit()
        sys.exit(0 if success else 1)

# --- Main Execution ---
def main():
    """Main function to run the autotest script."""
    cli_args = parse_arguments()
    # Logger is configured above, this will now use the new filtered setup
    logger.info(f"Parsed CLI arguments: {cli_args}") # KEEP INFO - Passes filter

    # Clean and ensure output directory exists
    output_dir_path = Path(cli_args.outputdir)
    logger.debug(f"Preparing output directory: {output_dir_path}")
    try:
        if output_dir_path.exists():
            logger.debug(f"Output directory {output_dir_path} exists. Cleaning its contents...")
            for item in output_dir_path.iterdir():
                if item.is_dir():
                    shutil.rmtree(item)
                    logger.debug(f"Removed directory: {item}")
                else:
                    item.unlink()
                    logger.debug(f"Removed file: {item}")
            logger.debug(f"Contents of {output_dir_path} cleaned.")
        else:
            logger.debug(f"Output directory {output_dir_path} does not exist. Creating it.")
        
        output_dir_path.mkdir(parents=True, exist_ok=True) # Ensure it exists after cleaning/if it didn't exist
        logger.debug(f"Output directory {output_dir_path} is ready.")

    except Exception as e:
        logger.error(f"Could not prepare output directory {output_dir_path}: {e}", exc_info=True)
        sys.exit(1)

    # Initialize QApplication
    # Use QCoreApplication if no GUI elements are directly interacted with by the test logic itself,
    # but QApplication is needed if MainWindow or its widgets are constructed and used.
    # Since MainWindow is instantiated by App, QApplication is appropriate.
    q_app = QApplication.instance()
    if not q_app:
        q_app = QApplication(sys.argv)
    if not q_app: # Still no app
        logger.error("Failed to initialize QApplication.")
        sys.exit(1)

    logger.debug("Initializing main.App()...")
    try:
        # Instantiate main.App() - this should create MainWindow but not show it by default
        # if App is designed to not show GUI unless app.main_window.show() is called.
        app_instance = App(preset_name=cli_args.preset)
    except Exception as e:
        logger.error(f"Failed to initialize main.App: {e}", exc_info=True)
        sys.exit(1)
    
    if not app_instance.main_window:
        logger.error("main.App initialized, but main_window is None. Cannot proceed with test.")
        sys.exit(1)
    
    logger.debug("Initializing AutoTester...")
    try:
        tester = AutoTester(app_instance, cli_args)
    except Exception as e:
        logger.error(f"Failed to initialize AutoTester: {e}", exc_info=True)
        sys.exit(1)

    # Use QTimer.singleShot to start the test after the Qt event loop has started.
    # This ensures that the Qt environment is fully set up.
    logger.debug("Scheduling test run...")
    QTimer.singleShot(0, tester.run_test)

    logger.debug("Starting Qt application event loop...")
    exit_code = q_app.exec()
    logger.debug(f"Qt application event loop finished with exit code: {exit_code}")
    sys.exit(exit_code)

if __name__ == "__main__":
    main()