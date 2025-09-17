import os
import json
import logging
from pathlib import Path

from PySide6.QtCore import QObject, Signal, QThread, Slot, QTimer

# --- Backend Imports ---
# Assuming these might be needed based on MainWindow's usage
try:
    from configuration import ConfigurationError # Keep error class
    from .llm_prediction_handler import LLMPredictionHandler # Backend handler
    from rule_structure import SourceRule # For signal emission type hint
except ImportError as e:
    logging.getLogger(__name__).critical(f"Failed to import backend modules for LLMInteractionHandler: {e}")
    LLMPredictionHandler = None
    ConfigurationError = Exception
    SourceRule = None # Define as None if import fails

log = logging.getLogger(__name__)
# Define config file paths relative to this handler's location
CONFIG_DIR = Path(__file__).parent.parent / "config"
APP_SETTINGS_PATH = CONFIG_DIR / "app_settings.json"
LLM_SETTINGS_PATH = CONFIG_DIR / "llm_settings.json"

class LLMInteractionHandler(QObject):
    """
    Handles the logic for interacting with the LLM prediction service,
    including managing the queue, thread, and communication.
    """
    # Signals to communicate results/status back to MainWindow or other components
    llm_prediction_ready = Signal(str, list) # input_path, List[SourceRule]
    llm_prediction_error = Signal(str, str)  # input_path, error_message
    llm_status_update = Signal(str)          # status_message
    llm_processing_state_changed = Signal(bool) # is_processing (True when busy, False when idle)

    def __init__(self, main_window_ref, parent=None):
        """
        Initializes the handler.

        Args:
            main_window_ref: A reference to the MainWindow instance for accessing
                             shared components like status bar or models if needed.
            parent: The parent QObject.
        """
        super().__init__(parent)
        self.main_window = main_window_ref # Store reference if needed for status updates etc.
        self.llm_processing_queue = [] # Unified queue for initial adds and re-interpretations
        self.llm_prediction_thread = None
        self.llm_prediction_handler = None
        self._is_processing = False # Internal flag to track processing state

    def _set_processing_state(self, processing: bool):
        """Updates the internal processing state and emits a signal."""
        if self._is_processing != processing:
            self._is_processing = processing
            log.debug(f"LLM Handler processing state changed to: {processing}")
            self.llm_processing_state_changed.emit(processing)

    def force_reset_state(self):
        """Forces the processing state to False. Use with caution."""
        log.warning("Forcing LLMInteractionHandler state reset.")
        if self.llm_prediction_thread and self.llm_prediction_thread.isRunning():
            log.warning("Force reset called while thread is running. Attempting to stop thread.")
            # Attempt graceful shutdown first
            self.llm_prediction_thread.quit()
            if not self.llm_prediction_thread.wait(500): # Wait 0.5 sec
                log.warning("LLM thread did not quit gracefully after force reset. Terminating.")
                self.llm_prediction_thread.terminate()
                self.llm_prediction_thread.wait() # Wait after terminate
        self.llm_prediction_thread = None
        self.llm_prediction_handler = None
        self._set_processing_state(False)
        # Do NOT clear the queue here, let the user decide via Clear Queue button

    @Slot(str, list)
    def queue_llm_request(self, input_path: str, file_list: list | None):
        """Adds a request to the LLM processing queue."""
        log.debug(f"Queueing LLM request for '{input_path}'. Current queue size: {len(self.llm_processing_queue)}")
        # Avoid duplicates? Check if already in queue
        is_in_queue = any(item[0] == input_path for item in self.llm_processing_queue)
        if not is_in_queue:
            self.llm_processing_queue.append((input_path, file_list))
            log.info(f"Added '{input_path}' to LLM queue. New size: {len(self.llm_processing_queue)}")
            # If not currently processing, start the queue
            if not self._is_processing:
                 # Use QTimer.singleShot to avoid immediate processing if called rapidly
                 QTimer.singleShot(0, self._process_next_llm_item)
        else:
            log.debug(f"Skipping duplicate add to LLM queue for: {input_path}")

    @Slot(list)
    def queue_llm_requests_batch(self, requests: list[tuple[str, list | None]]):
        """Adds multiple requests to the LLM processing queue."""
        added_count = 0
        log.debug(f"Queueing batch. Current queue content: {self.llm_processing_queue}")
        for input_path, file_list in requests:
            is_in_queue = any(item[0] == input_path for item in self.llm_processing_queue)
            if not is_in_queue:
                self.llm_processing_queue.append((input_path, file_list))
                added_count += 1
            else:
                log.debug(f"Skipping duplicate add to LLM queue for: {input_path}")

        if added_count > 0:
            log.info(f"Added {added_count} requests to LLM queue. New size: {len(self.llm_processing_queue)}")
            if not self._is_processing:
                 QTimer.singleShot(0, self._process_next_llm_item)

    # --- Methods to be moved from MainWindow ---

    @Slot()
    def _reset_llm_thread_references(self):
        """Resets LLM thread and handler references after the thread finishes."""
        log.debug("--> Entered LLMInteractionHandler._reset_llm_thread_references")
        log.debug("Resetting LLM prediction thread and handler references.")
        self.llm_prediction_thread = None
        self.llm_prediction_handler = None
        # --- Process next item now that the previous thread is fully finished ---
        log.debug("Previous LLM thread finished. Setting processing state to False.")
        self._set_processing_state(False) # Mark processing as finished
        # The next item will be processed when _handle_llm_result or _handle_llm_error
        # calls _process_next_llm_item after popping the completed item.
        log.debug("<-- Exiting LLMInteractionHandler._reset_llm_thread_references")


    def _start_llm_prediction(self, input_path_str: str, file_list: list = None):
        """
        Sets up and starts the LLMPredictionHandler in a separate thread.
        Emits signals for results, errors, or status updates.
        If file_list is not provided, it will be extracted.
        """
        log.debug(f"Attempting to start LLM prediction for: {input_path_str}")
        # Extract file list if not provided (needed for re-interpretation calls)
        if file_list is None:
            log.debug(f"File list not provided for {input_path_str}, extracting...")
            if hasattr(self.main_window, '_extract_file_list'):
                 file_list = self.main_window._extract_file_list(input_path_str)
                 if file_list is None:
                     error_msg = f"Failed to extract file list for {input_path_str} in _start_llm_prediction."
                     log.error(error_msg)
                     self.llm_status_update.emit(f"Error extracting files for {os.path.basename(input_path_str)}")
                     self.llm_prediction_error.emit(input_path_str, error_msg) # Signal error
                     return # Stop if extraction failed
            else:
                 error_msg = f"MainWindow reference does not have _extract_file_list method."
                 log.error(error_msg)
                 self.llm_status_update.emit(f"Internal Error: Cannot extract files for {os.path.basename(input_path_str)}")
                 self.llm_prediction_error.emit(input_path_str, error_msg)
                 return # Stop

        input_path_obj = Path(input_path_str) # Still needed for basename

        if not file_list:
             error_msg = f"LLM Error: No files found/extracted for {input_path_str}"
             log.error(error_msg)
             self.llm_status_update.emit(f"LLM Error: No files found for {input_path_obj.name}")
             self.llm_prediction_error.emit(input_path_str, error_msg)
             return

        # --- Load Required Settings Directly ---
        llm_settings = {}
        try:
            log.debug(f"Loading LLM settings from: {LLM_SETTINGS_PATH}")
            with open(LLM_SETTINGS_PATH, 'r') as f:
                llm_data = json.load(f)
            # Extract required fields with defaults
            llm_settings['endpoint_url'] = llm_data.get('llm_endpoint_url')
            llm_settings['api_key'] = llm_data.get('llm_api_key') # Can be None
            llm_settings['model_name'] = llm_data.get('llm_model_name', 'local-model')
            llm_settings['temperature'] = llm_data.get('llm_temperature', 0.5)
            llm_settings['request_timeout'] = llm_data.get('llm_request_timeout', 120)
            llm_settings['predictor_prompt'] = llm_data.get('llm_predictor_prompt', '')
            llm_settings['examples'] = llm_data.get('llm_examples', [])

            log.debug(f"Loading App settings from: {APP_SETTINGS_PATH}")
            with open(APP_SETTINGS_PATH, 'r') as f:
                app_data = json.load(f)
            # Extract required fields
            llm_settings['asset_type_definitions'] = app_data.get('ASSET_TYPE_DEFINITIONS', {})
            llm_settings['file_type_definitions'] = app_data.get('FILE_TYPE_DEFINITIONS', {})

            # Validate essential settings
            if not llm_settings['endpoint_url']:
                raise ValueError("LLM endpoint URL is missing in llm_settings.json")
            if not llm_settings['predictor_prompt']:
                 raise ValueError("LLM predictor prompt is missing in llm_settings.json")

            log.debug("LLM and App settings loaded successfully for LLMInteractionHandler.")

        except FileNotFoundError as e:
            error_msg = f"LLM Error: Configuration file not found: {e.filename}"
            log.critical(error_msg)
            self.llm_status_update.emit("LLM Error: Cannot load configuration file.")
            self.llm_prediction_error.emit(input_path_str, error_msg)
            return
        except json.JSONDecodeError as e:
            error_msg = f"LLM Error: Failed to parse configuration file: {e}"
            log.critical(error_msg)
            self.llm_status_update.emit("LLM Error: Cannot parse configuration file.")
            self.llm_prediction_error.emit(input_path_str, error_msg)
            return
        except ValueError as e: # Catch validation errors
            error_msg = f"LLM Error: Invalid configuration - {e}"
            log.critical(error_msg)
            self.llm_status_update.emit("LLM Error: Invalid configuration.")
            self.llm_prediction_error.emit(input_path_str, error_msg)
            return
        except Exception as e: # Catch other potential errors
            error_msg = f"LLM Error: Unexpected error loading configuration: {e}"
            log.critical(error_msg, exc_info=True)
            self.llm_status_update.emit("LLM Error: Cannot load application configuration.")
            self.llm_prediction_error.emit(input_path_str, error_msg)
            return

        # --- Wrap thread/handler setup and start in try...except ---
        try:
            # --- Check if Handler Class is Available ---
            if LLMPredictionHandler is None:
                # Raise ValueError to be caught below
                raise ValueError("LLMPredictionHandler class not available.")

            # --- Clean up previous thread/handler if necessary ---
            # (Keep this cleanup logic as it handles potential stale threads)
            if self.llm_prediction_thread and self.llm_prediction_thread.isRunning():
                log.warning("Warning: Previous LLM prediction thread still running when trying to start new one. Attempting cleanup.")
                if self.llm_prediction_handler:
                    if hasattr(self.llm_prediction_handler, 'cancel'):
                        self.llm_prediction_handler.cancel()
                self.llm_prediction_thread.quit()
                if not self.llm_prediction_thread.wait(1000): # Wait 1 sec
                     log.warning("LLM thread did not quit gracefully. Forcing termination.")
                     self.llm_prediction_thread.terminate()
                     self.llm_prediction_thread.wait() # Wait after terminate
                self.llm_prediction_thread = None
                self.llm_prediction_handler = None

            log.info(f"Starting LLM prediction thread for source: {input_path_str} with {len(file_list)} files.")
            self.llm_status_update.emit(f"Starting LLM interpretation for {input_path_obj.name}...")

            # --- Create Thread and Handler ---
            self.llm_prediction_thread = QThread(self) # Parent thread to self
            # Pass the loaded settings dictionary
            self.llm_prediction_handler = LLMPredictionHandler(input_path_str, file_list, llm_settings)
            self.llm_prediction_handler.moveToThread(self.llm_prediction_thread)

            # Connect signals from handler to *internal* slots or directly emit signals
            self.llm_prediction_handler.prediction_ready.connect(self._handle_llm_result)
            self.llm_prediction_handler.prediction_error.connect(self._handle_llm_error)
            self.llm_prediction_handler.status_update.connect(self.llm_status_update) # Pass status through

            # Connect thread signals
            self.llm_prediction_thread.started.connect(self.llm_prediction_handler.run)
            # Clean up thread and handler when finished
            self.llm_prediction_thread.finished.connect(self._reset_llm_thread_references)
            self.llm_prediction_thread.finished.connect(self.llm_prediction_handler.deleteLater)
            self.llm_prediction_thread.finished.connect(self.llm_prediction_thread.deleteLater)
            # Also ensure thread quits when handler signals completion/error
            self.llm_prediction_handler.prediction_ready.connect(self.llm_prediction_thread.quit)
            self.llm_prediction_handler.prediction_error.connect(self.llm_prediction_thread.quit)

            # TODO: Add a logging.debug statement at the very beginning of LLMPredictionHandler.run()
            # to confirm if the method is being reached. Example:
            # log.debug(f"--> Entered LLMPredictionHandler.run() for {self.input_path}")

            self.llm_prediction_thread.start()
            log.debug(f"LLM prediction thread start() called for {input_path_str}. Is running: {self.llm_prediction_thread.isRunning()}")
            # Log success *after* start() is called successfully
            log.debug(f"Successfully initiated LLM prediction thread for {input_path_str}.")

        except Exception as e:
            # --- Handle errors during setup/start ---
            log.exception(f"Critical error during LLM thread setup/start for {input_path_str}: {e}")
            error_msg = f"Error initializing LLM task for {input_path_obj.name}: {e}"
            self.llm_status_update.emit(error_msg)
            self.llm_prediction_error.emit(input_path_str, error_msg) # Signal the error

            # --- Crucially, reset processing state if setup fails ---
            log.warning("Resetting processing state due to thread setup/start error.")
            self._set_processing_state(False)

            # Clean up potentially partially created objects
            if self.llm_prediction_handler:
                self.llm_prediction_handler.deleteLater()
                self.llm_prediction_handler = None
            if self.llm_prediction_thread:
                if self.llm_prediction_thread.isRunning():
                    self.llm_prediction_thread.quit()
                    self.llm_prediction_thread.wait(500)
                    self.llm_prediction_thread.terminate() # Force if needed
                    self.llm_prediction_thread.wait()
                self.llm_prediction_thread.deleteLater()
                self.llm_prediction_thread = None

            # Do NOT automatically try the next item here, as the error might be persistent.
            # Let the error signal handle popping the item and trying the next one.
            # The error signal (_handle_llm_error) will pop the item and call _process_next_llm_item.


    def is_processing(self) -> bool:
        """Safely checks if the LLM prediction thread is currently running."""
        # Use the internal flag, which is more reliable than checking thread directly
        # due to potential race conditions during cleanup.
        # The thread check can be a fallback.
        is_running_flag = self._is_processing
        # Also check thread as a safeguard, though the flag should be primary
        try:
            is_thread_alive = self.llm_prediction_thread is not None and self.llm_prediction_thread.isRunning()
            if is_running_flag != is_thread_alive:
                 # This might indicate the flag wasn't updated correctly, log it.
                 log.warning(f"LLM Handler processing flag ({is_running_flag}) mismatch with thread state ({is_thread_alive}). Flag is primary.")
            return is_running_flag
        except RuntimeError:
            log.debug("is_processing: Caught RuntimeError checking isRunning (thread likely deleted).")
            # If thread died unexpectedly, the flag might be stale. Reset it.
            if self._is_processing:
                 self._set_processing_state(False)
            return False


    def _process_next_llm_item(self):
        """Processes the next directory in the unified LLM processing queue."""
        log.debug(f"--> Entered _process_next_llm_item. Queue size: {len(self.llm_processing_queue)}")

        if self.is_processing():
             log.info("LLM processing already running. Waiting for current item to finish.")
             # Do not pop from queue if already running, wait for _reset_llm_thread_references to call this again
             return

        if not self.llm_processing_queue:
            log.info("LLM processing queue is empty. Finishing.")
            self.llm_status_update.emit("LLM processing complete.")
            self._set_processing_state(False) # Ensure state is set to idle
            log.debug("<-- Exiting _process_next_llm_item (queue empty)")
            return

        # Set state to busy *before* starting
        self._set_processing_state(True)

        # Get next item *without* removing it yet
        next_item = self.llm_processing_queue[0] # Peek at the first item
        next_dir, file_list = next_item # Unpack the tuple

        # --- Update Status/Progress ---
        total_in_queue_now = len(self.llm_processing_queue)
        status_msg = f"LLM Processing {os.path.basename(next_dir)} ({total_in_queue_now} remaining)..."
        self.llm_status_update.emit(status_msg)
        log.info(status_msg)

        # --- Start Prediction (which might fail) ---
        try:
            # Pass the potentially None file_list. _start_llm_prediction handles extraction if needed.
            self._start_llm_prediction(next_dir, file_list=file_list)
            # --- DO NOT pop item here. Item is popped in _handle_llm_result or _handle_llm_error ---
        except Exception as e:
            # This block now catches errors from _start_llm_prediction itself
            log.exception(f"Error occurred *during* _start_llm_prediction call for {next_dir}: {e}")
            error_msg = f"Error starting LLM for {os.path.basename(next_dir)}: {e}"
            self.llm_status_update.emit(error_msg)
            self.llm_prediction_error.emit(next_dir, error_msg) # Signal the error
            # --- Remove the failed item from the queue ---
            try:
                failed_item = self.llm_processing_queue.pop(0)
                log.warning(f"Removed failed item {failed_item} from LLM queue due to start error.")
            except IndexError:
                log.error("Attempted to pop failed item from already empty LLM queue after start error.")
            # --- Attempt to process the *next* item ---
            # Reset processing state since this one failed *before* the thread finished signal could
            self._set_processing_state(False)
            # Use QTimer.singleShot to avoid deep recursion
            QTimer.singleShot(100, self._process_next_llm_item) # Try next item after a short delay

    # --- Internal Slots to Handle Results/Errors from LLMPredictionHandler ---
    @Slot(str, list)
    def _handle_llm_result(self, input_path: str, source_rules: list):
        """Internal slot to receive results, pop item, and emit the public signal."""
        log.debug(f"LLM Handler received result for {input_path}. Removing from queue and emitting llm_prediction_ready.")
        # Remove the completed item from the queue
        try:
            # Find and remove the item by input_path
            self.llm_processing_queue = [item for item in self.llm_processing_queue if item[0] != input_path]
            log.debug(f"Removed '{input_path}' from LLM queue after successful prediction. New size: {len(self.llm_processing_queue)}")
        except Exception as e:
            log.error(f"Error removing '{input_path}' from LLM queue after success: {e}")

        self.llm_prediction_ready.emit(input_path, source_rules)

        # Process the next item in the queue
        QTimer.singleShot(0, self._process_next_llm_item)

    @Slot(str, str)
    def _handle_llm_error(self, input_path: str, error_message: str):
        """Internal slot to receive errors, pop item, and emit the public signal."""
        log.debug(f"LLM Handler received error for {input_path}: {error_message}. Removing from queue and emitting llm_prediction_error.")
        # Remove the failed item from the queue
        try:
            # Find and remove the item by input_path
            self.llm_processing_queue = [item for item in self.llm_processing_queue if item[0] != input_path]
            log.debug(f"Removed '{input_path}' from LLM queue after error. New size: {len(self.llm_processing_queue)}")
        except Exception as e:
            log.error(f"Error removing '{input_path}' from LLM queue after error: {e}")

        self.llm_prediction_error.emit(input_path, error_message)

        # Process the next item in the queue
        QTimer.singleShot(0, self._process_next_llm_item)

    def clear_queue(self):
        """Clears the LLM processing queue."""
        log.info(f"Clearing LLM processing queue ({len(self.llm_processing_queue)} items).")
        self.llm_processing_queue.clear()
        # TODO: Should we also attempt to cancel any *currently* running LLM task?
        # This might be complex. For now, just clears the queue of pending items.
        if self.is_processing():
             log.warning("LLM queue cleared, but a task is currently running. It will complete.")
        else:
             self.llm_status_update.emit("LLM queue cleared.")