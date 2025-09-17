import argparse
import sys
import time
import os
import json
import logging
from pathlib import Path
import re # Added for checking incrementing token
from concurrent.futures import ProcessPoolExecutor, as_completed
import subprocess
import shutil
import tempfile
import zipfile
from typing import List, Dict, Tuple, Optional

# --- Utility Imports ---
from utils.hash_utils import calculate_sha256
from utils.path_utils import get_next_incrementing_value
from utils import app_setup_utils # Import the new utility module

# --- Qt Imports for Application Structure ---
from PySide6.QtCore import QObject, Slot, QThreadPool, QRunnable, Signal
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QDialog # Import QDialog for the setup dialog

# --- Backend Imports ---
# Add current directory to sys.path for direct execution
import sys
import os
sys.path.append(os.path.dirname(__file__))
print(f"DEBUG: sys.path after append: {sys.path}")

try:
    print("DEBUG: Attempting to import Configuration...")
    from configuration import Configuration, ConfigurationError, get_available_preset_names
    print("DEBUG: Successfully imported Configuration.")

    print("DEBUG: Attempting to import ProcessingEngine...")
    from processing_engine import ProcessingEngine
    print("DEBUG: Successfully imported ProcessingEngine.")

    print("DEBUG: Attempting to import SourceRule...")
    from rule_structure import SourceRule
    print("DEBUG: Successfully imported SourceRule.")

    print("DEBUG: Attempting to import MainWindow...")
    from gui.main_window import MainWindow
    print("DEBUG: Successfully imported MainWindow.")

    print("DEBUG: Attempting to import FirstTimeSetupDialog...")
    from gui.first_time_setup_dialog import FirstTimeSetupDialog # Import the setup dialog
    print("DEBUG: Successfully imported FirstTimeSetupDialog.")

    print("DEBUG: Attempting to import prepare_processing_workspace...")
    from utils.workspace_utils import prepare_processing_workspace
    print("DEBUG: Successfully imported prepare_processing_workspace.")

except ImportError as e:
    script_dir = Path(__file__).parent.resolve()
    print(f"ERROR: Cannot import Configuration or rule_structure classes.")
    print(f"Ensure configuration.py and rule_structure.py are in the same directory or Python path.")
    print(f"ERROR: Failed to import necessary classes: {e}")
    print(f"DEBUG: Exception type: {type(e)}")
    print(f"DEBUG: Exception args: {e.args}")
    import traceback
    print("DEBUG: Full traceback of the ImportError:")
    traceback.print_exc()
    print(f"Ensure 'configuration.py' and 'asset_processor.py' exist in the directory:")
    print(f"  {script_dir}")
    print("Or that the directory is included in your PYTHONPATH.")
    sys.exit(1)

# --- Setup Logging ---
# Keep setup_logging as is, it's called by main() or potentially monitor.py
def setup_logging(verbose: bool):
    """Configures logging for the application."""
    log_level = logging.DEBUG if verbose else logging.INFO
    log_format = '%(asctime)s [%(levelname)-8s] %(name)s: %(message)s'
    date_format = '%Y-%m-%d %H:%M:%S'

    # Remove existing handlers to avoid duplication if re-run in same session
    for handler in logging.root.handlers[:]:
        logging.root.removeHandler(handler)

    logging.basicConfig(
        level=log_level,
        format=log_format,
        datefmt=date_format,
        handlers=[
            logging.StreamHandler(sys.stdout)
        ]
    )
    log = logging.getLogger(__name__)
    log.info(f"Logging level set to: {logging.getLevelName(log_level)}")

log = logging.getLogger(__name__)


# --- Argument Parser Setup ---
# Keep setup_arg_parser as is, it's only used when running main.py directly
def setup_arg_parser():
    """Sets up and returns the command-line argument parser."""
    default_workers = 1
    try:
        # Use half the cores, but at least 1, max maybe 8-16? Depends on task nature.
        # Let's try max(1, os.cpu_count() // 2)
        cores = os.cpu_count()
        if cores:
            default_workers = max(1, cores // 2)
    except NotImplementedError:
        log.warning("Could not detect CPU count, defaulting workers to 1.")

    parser = argparse.ArgumentParser(
        description="Process asset files (ZIPs or folders) into a standardized library format using presets.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter
    )
    parser.add_argument(
        "input_paths",
        metavar="INPUT_PATH",
        type=str,
        nargs='*',
        default=[],
        help="Path(s) to the input ZIP file(s) or folder(s) containing assets (Required for CLI mode)."
    )
    parser.add_argument(
        "-p", "--preset",
        type=str,
        required=False,
        default=None,
        help="Name of the configuration preset (Required for CLI mode)."
    )
    parser.add_argument(
        "-o", "--output-dir",
        type=str,
        required=False,
        default=None,
        help="Override the default base output directory defined in config.py."
    )
    parser.add_argument(
        "-w", "--workers",
        type=int,
        default=default_workers,
        help="Maximum number of assets to process concurrently in parallel processes."
    )
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Enable detailed DEBUG level logging for troubleshooting."
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Force reprocessing and overwrite existing output asset folders if they exist."
    )
    parser.add_argument(
        "--nodegroup-blend",
        type=str,
        default=None,
        help="Path to the .blend file for creating/updating node groups. Overrides config.py default."
    )
    parser.add_argument(
        "--materials-blend",
        type=str,
        default=None,
        help="Path to the .blend file for creating/updating materials. Overrides config.py default."
    )
    parser.add_argument(
        "--gui",
        action="store_true",
        help="Force launch in GUI mode, ignoring other arguments."
    )
    return parser


# --- Worker Runnable for Thread Pool ---
class TaskSignals(QObject):
    finished = Signal(str, str, object) # rule_input_path, status, result/error

class ProcessingTask(QRunnable):
    """Wraps a call to processing_engine.process for execution in a thread pool."""

    def __init__(self, engine: ProcessingEngine, rule: SourceRule, workspace_path: Path, output_base_path: Path):
        super().__init__()
        self.engine = engine
        self.rule = rule
        self.workspace_path = workspace_path
        self.output_base_path = output_base_path
        self.signals = TaskSignals()

    @Slot() # Decorator required for QRunnable's run method
    def run(self):
        """Prepares input files and executes the engine's process method."""
        log.info(f"Worker Thread: Starting processing for rule: {self.rule.input_path}")
        log.debug(f"DEBUG: Rule passed to ProcessingTask.run: {self.rule}")
        status = "failed"
        result_or_error = None
        prepared_workspace_path = None # Initialize path for prepared content outside try

        try:
            # --- 1. Prepare Input Workspace using Utility Function ---
            # The utility function creates the temp dir, prepares it, and returns its path.
            # It raises exceptions on failure (FileNotFoundError, ValueError, zipfile.BadZipFile, OSError).
            prepared_workspace_path = prepare_processing_workspace(self.rule.input_path)
            log.info(f"Workspace prepared successfully at: {prepared_workspace_path}")

            # --- DEBUG: List files in prepared workspace ---
            try:
                log.debug(f"Listing contents of prepared workspace: {prepared_workspace_path}")
                for item in prepared_workspace_path.rglob('*'):
                     log.debug(f"  Found item: {item.relative_to(prepared_workspace_path)}")
            except Exception as list_err:
                log.error(f"Error listing prepared workspace contents: {list_err}")
            # --- END DEBUG ---
            # --- 2. Execute Processing Engine ---
            log.info(f"Calling ProcessingEngine.process with rule for input: {self.rule.input_path}, prepared workspace: {prepared_workspace_path}, output: {self.output_base_path}")
            log.debug(f"  Rule Details: {self.rule}")

            # --- Calculate SHA5 and Incrementing Value ---
            config = self.engine.config_obj
            archive_path = self.rule.input_path
            output_dir = self.output_base_path # This is already a Path object from App.on_processing_requested

            sha5_value = None
            try:
                archive_path_obj = Path(archive_path)
                if archive_path_obj.is_file():
                    log.debug(f"Calculating SHA256 for file: {archive_path_obj}")
                    full_sha = calculate_sha256(archive_path_obj)
                    if full_sha:
                        sha5_value = full_sha[:5]
                        log.info(f"Calculated SHA5 for {archive_path}: {sha5_value}")
                    else:
                        log.warning(f"SHA256 calculation returned None for {archive_path}")
                elif archive_path_obj.is_dir():
                    log.debug(f"Input path {archive_path} is a directory, skipping SHA5 calculation.")
                else:
                    log.warning(f"Input path {archive_path} is not a valid file or directory for SHA5 calculation.")
            except FileNotFoundError:
                log.error(f"SHA5 calculation failed: File not found at {archive_path}")
            except Exception as e:
                log.exception(f"Error calculating SHA5 for {archive_path}: {e}")

            next_increment_str = None
            try:
                # output_dir should already be a Path object
                pattern = getattr(config, 'output_directory_pattern', None)
                if pattern:
                    # Only call get_next_incrementing_value if the pattern contains an incrementing token
                    if re.search(r"\[IncrementingValue\]|#+", pattern):
                        log.debug(f"Incrementing token found in pattern '{pattern}'. Calculating next value for dir: {output_dir}")
                        next_increment_str = get_next_incrementing_value(output_dir, pattern)
                        log.info(f"Calculated next incrementing value for {output_dir}: {next_increment_str}")
                    else:
                        log.debug(f"No incrementing token found in pattern '{pattern}'. Skipping increment calculation.")
                        next_increment_str = None # Or a default like "00" if downstream expects a string, but None is cleaner if handled.
                else:
                    log.warning(f"Cannot calculate incrementing value: 'output_directory_pattern' not found in configuration for preset {config.preset_name}")
            except Exception as e:
                log.exception(f"Error calculating next incrementing value for {output_dir}: {e}")
            # --- End Calculation ---

            log.info(f"Calling engine.process with sha5='{sha5_value}', incrementing_value='{next_increment_str}'")
            result_or_error = self.engine.process(
                self.rule,
                workspace_path=prepared_workspace_path,
                output_base_path=self.output_base_path,
                incrementing_value=next_increment_str,
                sha5_value=sha5_value
            )
            status = "processed" # Assume success if no exception
            log.info(f"Worker Thread: Finished processing for rule: {self.rule.input_path}, Status: {status}")
            # Signal emission moved to finally block

        except (FileNotFoundError, ValueError, zipfile.BadZipFile, OSError) as prep_error:
            log.exception(f"Worker Thread: Error preparing workspace for rule {self.rule.input_path}: {prep_error}")
            status = "failed_preparation"
            result_or_error = str(prep_error)
            # Signal emission moved to finally block
        except Exception as proc_error:
            log.exception(f"Worker Thread: Error during engine processing for rule {self.rule.input_path}: {proc_error}")
            status = "failed_processing"
            result_or_error = str(proc_error)
            # Signal emission moved to finally block
        finally:
            # --- Emit finished signal regardless of success or failure ---
            try:
                 self.signals.finished.emit(str(self.rule.input_path), status, result_or_error)
                 log.debug(f"Worker Thread: Emitted finished signal for {self.rule.input_path} with status {status}")
            except Exception as sig_err:
                 log.error(f"Worker Thread: Error emitting finished signal for {self.rule.input_path}: {sig_err}")

            # --- 3. Cleanup Workspace ---
            # Use the path returned by the utility function for cleanup
            if prepared_workspace_path and prepared_workspace_path.exists():
                try:
                    log.info(f"Cleaning up temporary workspace: {prepared_workspace_path}")
                    shutil.rmtree(prepared_workspace_path)
                except OSError as cleanup_error:
                    log.error(f"Worker Thread: Failed to cleanup temporary workspace {prepared_workspace_path}: {cleanup_error}")




# --- Main Application Class (Integrates GUI and Engine) ---
class App(QObject):
    # Signal emitted when all queued processing tasks are complete
    all_tasks_finished = Signal(int, int, int) # processed_count, skipped_count, failed_count (Placeholder counts for now)

    def __init__(self, user_config_path: str | Path | None = None, preset_name: str | None = None):
        super().__init__()
        # Normalize the provided paths/overrides
        if isinstance(user_config_path, Path):
            self.user_config_path = user_config_path
        elif user_config_path:
            self.user_config_path = Path(user_config_path)
        else:
            self.user_config_path = None

        self._preset_override = preset_name.strip() if isinstance(preset_name, str) and preset_name.strip() else None
        self.config_obj = None
        self.processing_engine = None
        self.main_window = None
        self.thread_pool = QThreadPool()
        self._active_tasks_count = 0
        self._task_results = {"processed": 0, "skipped": 0, "failed": 0}
        log.info(f"Maximum threads for pool: {self.thread_pool.maxThreadCount()}")

        self.active_preset_name = None

        self._load_config(self.user_config_path, self._preset_override)
        self._init_engine()
        self._init_gui()

    def _determine_app_base_dir(self) -> Path:
        """Matches Configuration's bundled base dir detection."""
        if getattr(sys, 'frozen', False) and hasattr(sys, '_MEIPASS'):
            return Path(sys._MEIPASS)
        return Path(__file__).resolve().parent

    def _read_saved_preset_name(self, user_config_dir: Path | None) -> str | None:
        """Attempts to read a persisted preset preference from user settings."""
        if not user_config_dir:
            return None

        possible_paths = [
            user_config_dir / Configuration.USER_SETTINGS_FILENAME,
            user_config_dir / Configuration.USER_CONFIG_SUBDIR_NAME / Configuration.USER_SETTINGS_FILENAME,
        ]
        preset_keys = (
            "default_gui_preset",
            "default_preset",
            "default_preset_name",
            "last_used_preset",
            "last_selected_preset",
        )

        for settings_path in possible_paths:
            if not settings_path.is_file():
                continue
            try:
                with open(settings_path, "r", encoding="utf-8") as settings_file:
                    settings_data = json.load(settings_file)
            except json.JSONDecodeError as exc:
                log.warning(f"Could not parse user settings JSON at '{settings_path}': {exc}")
                continue
            except OSError as exc:
                log.warning(f"Could not read user settings file '{settings_path}': {exc}")
                continue

            # Try direct keys first
            if isinstance(settings_data, dict):
                for key in preset_keys:
                    value = settings_data.get(key)
                    if isinstance(value, str) and value.strip():
                        return value.strip()

                general_settings = settings_data.get("general_settings")
                if isinstance(general_settings, dict):
                    for key in preset_keys:
                        value = general_settings.get(key)
                        if isinstance(value, str) and value.strip():
                            return value.strip()

        return None

    def _determine_initial_preset(self, user_config_dir: Path | None, preset_override: str | None) -> str:
        """Determines which preset should be used when loading configuration."""
        base_dir_app_bundled = self._determine_app_base_dir()
        available_presets = get_available_preset_names(user_config_dir, base_dir_app_bundled)
        available_lookup = {name.lower(): name for name in available_presets}

        def resolve_candidate(candidate: str | None) -> str | None:
            if not candidate:
                return None
            normalized = candidate.strip().lower()
            resolved_name = available_lookup.get(normalized)
            if resolved_name:
                return resolved_name
            log.warning(f"Requested preset '{candidate}' not found among available presets: {available_presets}")
            return None

        preset_candidate = resolve_candidate(preset_override)
        if not preset_candidate:
            preset_candidate = resolve_candidate(self._read_saved_preset_name(user_config_dir))

        if not preset_candidate:
            # Fallback to bundled defaults in a predictable order (skip templates if possible)
            non_template_presets = [name for name in available_presets if not name.startswith('_')]
            preset_candidate = (non_template_presets or available_presets)[0] if available_presets else None

        if not preset_candidate:
            raise ConfigurationError(
                "No presets available to initialize configuration. Ensure at least one preset JSON file exists."
            )

        return preset_candidate

    def _load_config(self, user_config_path: Path | None, preset_override: str | None = None):
        """Loads the base configuration using the determined user config path."""
        try:
            actual_user_config_dir = user_config_path if isinstance(user_config_path, Path) else None
            preset_to_use = self._determine_initial_preset(actual_user_config_dir, preset_override)
            self.config_obj = Configuration(
                preset_name=preset_to_use,
                base_dir_user_config=actual_user_config_dir,
            )
            self.active_preset_name = preset_to_use
            log.info(
                "Base configuration loaded using preset '%s' and user config path '%s'.",
                preset_to_use,
                actual_user_config_dir if actual_user_config_dir else "<bundled defaults>",
            )
        except ConfigurationError as e:
            log.error(f"Fatal: Failed to load base configuration using user config path '{user_config_path}': {e}")
            # In a real app, show this error to the user before exiting
            sys.exit(1)
        except Exception as e:
            log.exception(f"Fatal: Unexpected error loading configuration: {e}")
            sys.exit(1)

    def _init_engine(self):
        """Initializes the ProcessingEngine."""
        if self.config_obj:
            try:
                self.processing_engine = ProcessingEngine(self.config_obj)
                log.info("ProcessingEngine initialized.")
            except Exception as e:
                log.exception(f"Fatal: Failed to initialize ProcessingEngine: {e}")
                # Show error and exit
                sys.exit(1)
        else:
            log.error("Fatal: Cannot initialize ProcessingEngine without configuration.")
            sys.exit(1)

    def _init_gui(self):
        """Initializes the MainWindow and connects signals."""
        if self.processing_engine:
            self.main_window = MainWindow() # MainWindow now part of the App
            # Connect the signal from the GUI to the App's slot using QueuedConnection
            # Connect the signal from the MainWindow (which is triggered by the panel) to the App's slot
            connection_success = self.main_window.start_backend_processing.connect(self.on_processing_requested, Qt.ConnectionType.QueuedConnection)
            log.info(f"DEBUG: Connection result for processing_requested (Queued): {connection_success}")
            if not connection_success:
                log.error("*********************************************************")
                log.error("FATAL: Failed to connect MainWindow.processing_requested signal to App.on_processing_requested slot!")
                log.error("*********************************************************")
            # Connect the App's completion signal to the MainWindow's slot
            self.all_tasks_finished.connect(self.main_window.on_processing_finished)
            log.info("MainWindow initialized and signals connected.")
        else:
            log.error("Fatal: Cannot initialize MainWindow without ProcessingEngine.")
            sys.exit(1)

    @Slot(list, dict) # Slot to receive List[SourceRule] and processing_settings dict
    def on_processing_requested(self, source_rules: list, processing_settings: dict):
        log.debug("DEBUG: App.on_processing_requested slot entered.")
        """Handles the processing request from the GUI."""
        log.info(f"Received processing request for {len(source_rules)} rule sets.")
        log.info(f"DEBUG: Rules received by on_processing_requested: {source_rules}")
        log.info(f"VERIFY: App.on_processing_requested received {len(source_rules)} rules.")
        for i, rule in enumerate(source_rules):
            log.debug(f"  VERIFY Rule {i}: Input='{rule.input_path}', Assets={len(rule.assets)}")
        if not self.processing_engine:
            log.error("Processing engine not available. Cannot process request.")
            self.main_window.statusBar().showMessage("Error: Processing Engine not ready.", 5000)
            return
        if not source_rules:
            log.warning("Processing requested with an empty rule list.")
            self.main_window.statusBar().showMessage("No rules to process.", 3000)
            return

        # Reset task counter and results for this batch
        self._active_tasks_count = len(source_rules)
        self._task_results = {"processed": 0, "skipped": 0, "failed": 0}
        log.debug(f"Initialized active task count to: {self._active_tasks_count}")

        # Update GUI progress bar/status via MainPanelWidget
        total_tasks = self.main_window.main_panel_widget.progress_bar.maximum()
        completed_tasks = total_tasks - self._active_tasks_count
        self.main_window.main_panel_widget.update_progress_bar(completed_tasks, total_tasks) # Use MainPanelWidget's method

        # Update status for the specific file in the GUI (if needed)

        if self._active_tasks_count == 0:
            log.info("All processing tasks finished.")
            # Emit the signal with the final counts
            self.all_tasks_finished.emit(
                self._task_results["processed"],
                self._task_results["skipped"],
                self._task_results["failed"]
            )
        elif self._active_tasks_count < 0:
             log.error("Error: Active task count went below zero!") # Should not happen

    def run(self):
        """Shows the main window."""
        if self.main_window:
            self.main_window.show()
            log.info("Application started. Showing main window.")
        else:
            log.error("Cannot run application, MainWindow not initialized.")


if __name__ == "__main__":
    parser = setup_arg_parser()
    args = parser.parse_args()

    setup_logging(args.verbose)

    # Determine mode based on presence of required CLI args
    if not args.gui and (args.input_paths or args.preset):
        # If either input_paths or preset is provided (and GUI not forced), assume CLI mode
        # run_cli will handle validation that *both* are actually present
        log.info("CLI arguments detected (input_paths or preset), attempting CLI mode.")
        run_cli(args)
    else:
        # If neither input_paths nor preset is provided, run GUI mode
        log.info("No required CLI arguments detected, starting GUI mode.")
        # --- Run the GUI Application ---
        try:
            user_config_path = app_setup_utils.read_saved_user_config_path()
            log.debug(f"Read saved user config path: {user_config_path}")

            first_run_needed = False
            if user_config_path is None or not user_config_path.strip():
                log.info("No saved user config path found. First run setup needed.")
                first_run_needed = True
            else:
                user_config_dir = Path(user_config_path)
                marker_file = app_setup_utils.get_first_run_marker_file(user_config_path)
                if not user_config_dir.is_dir():
                    log.warning(f"Saved user config directory does not exist: {user_config_path}. First run setup needed.")
                    first_run_needed = True
                elif not Path(marker_file).is_file():
                    log.warning(f"First run marker file not found in {user_config_path}. First run setup needed.")
                    first_run_needed = True
                else:
                    log.info(f"Saved user config path found and valid: {user_config_path}. Marker file exists.")

            qt_app = None
            if first_run_needed:
                log.info("Initiating first-time setup dialog.")
                # Need a QApplication instance to show the dialog
                qt_app = QApplication.instance()
                if qt_app is None:
                    qt_app = QApplication(sys.argv)

                dialog = FirstTimeSetupDialog()
                if dialog.exec() == QDialog.Accepted:
                    user_config_path = dialog.get_chosen_path()
                    log.info(f"First-time setup completed. Chosen path: {user_config_path}")
                    # The dialog should have already saved the path and created the marker file
                else:
                    log.info("First-time setup cancelled by user. Exiting application.")
                    sys.exit(0) # Exit gracefully

            # If qt_app was created for the dialog, reuse it. Otherwise, create it now.
            if qt_app is None:
                 qt_app = QApplication.instance()
                 if qt_app is None:
                     qt_app = QApplication(sys.argv)


            # Ensure user_config_path is set before initializing App
            if not user_config_path or not Path(user_config_path).is_dir():
                 log.error(f"Fatal: User config path is invalid or not set after setup: {user_config_path}. Cannot proceed.")
                 sys.exit(1)


            preset_override = args.preset if args.gui and args.preset else None

            app_instance = App(user_config_path=user_config_path, preset_name=preset_override)
            app_instance.run()

            sys.exit(qt_app.exec())
        except Exception as gui_exc:
             log.exception(f"An error occurred during GUI startup or execution: {gui_exc}")
             sys.exit(1)
