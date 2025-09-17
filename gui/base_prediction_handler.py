import logging
import time
from abc import ABC, abstractmethod
from pathlib import Path
from typing import List, Any

from PySide6.QtCore import QObject, Signal, Slot, QThread

# Assuming rule_structure defines SourceRule
try:
    from rule_structure import SourceRule
except ImportError:
    print("ERROR (BasePredictionHandler): Failed to import SourceRule. Predictions might fail.")
    # Define a placeholder if the import fails to allow type hinting
    class SourceRule: pass

from abc import ABCMeta
from PySide6.QtCore import QObject

# Combine metaclasses to avoid conflict between QObject and ABC
class QtABCMeta(type(QObject), ABCMeta):
    pass
log = logging.getLogger(__name__)

class BasePredictionHandler(QObject, ABC, metaclass=QtABCMeta):
    """
    Abstract base class for prediction handlers that generate SourceRule hierarchies.
    Designed to be run in a separate QThread.
    """
    # --- Standardized Signals ---
    # Emitted when prediction is successfully completed.
    # Args: input_source_identifier (str), results (List[SourceRule])
    prediction_ready = Signal(str, list)

    # Emitted when an error occurs during prediction.
    # Args: input_source_identifier (str), error_message (str)
    prediction_error = Signal(str, str)

    # Emitted for status updates during the prediction process.
    # Args: status_message (str)
    status_update = Signal(str)

    def __init__(self, input_source_identifier: str, parent: QObject = None):
        """
        Initializes the base handler.

        Args:
            input_source_identifier: The unique identifier for the input source (e.g., file path).
            parent: The parent QObject.
        """
        super().__init__(parent)
        self.input_source_identifier = input_source_identifier
        self._is_running = False
        self._is_cancelled = False

    @property
    def is_running(self) -> bool:
        """Returns True if the handler is currently processing."""
        return self._is_running

    @Slot()
    def run(self):
        """
        Main execution slot intended to be connected to QThread.started.
        Handles the overall process: setup, execution, error handling, signaling.
        """
        log.debug(f"--> Entered BasePredictionHandler.run() for {self.input_source_identifier}")
        if self._is_running:
            log.warning(f"Handler for '{self.input_source_identifier}' is already running. Aborting.")
            return
        if self._is_cancelled:
            log.info(f"Handler for '{self.input_source_identifier}' was cancelled before starting.")
            # Optionally emit an error or specific signal for cancellation before start
            return

        self._is_running = True
        self._is_cancelled = False
        thread_id = QThread.currentThread() # Use currentThread() for PySide6
        log.info(f"[{time.time():.4f}][T:{thread_id}] Starting prediction run for: {self.input_source_identifier}")
        self.status_update.emit(f"Starting analysis for '{Path(self.input_source_identifier).name}'...")

        try:
            # --- Execute Core Logic ---
            results = self._perform_prediction()

            if self._is_cancelled:
                log.info(f"Prediction cancelled during execution for: {self.input_source_identifier}")
                self.prediction_error.emit(self.input_source_identifier, "Prediction cancelled by user.")
            else:
                # --- Emit Success Signal ---
                log.info(f"[{time.time():.4f}][T:{thread_id}] Prediction successful for '{self.input_source_identifier}'. Emitting results.")
                self.prediction_ready.emit(self.input_source_identifier, results)
                self.status_update.emit(f"Analysis complete for '{Path(self.input_source_identifier).name}'.")

        except Exception as e:
            # --- Emit Error Signal ---
            log.exception(f"[{time.time():.4f}][T:{thread_id}] Error during prediction for '{self.input_source_identifier}': {e}")
            error_msg = f"Error analyzing '{Path(self.input_source_identifier).name}': {e}"
            self.prediction_error.emit(self.input_source_identifier, error_msg)
            # Status update might be redundant if error is shown elsewhere, but can be useful
            # Status update might be redundant if error is shown elsewhere, but can be useful

        finally:
            # --- Cleanup ---
            self._is_running = False
            log.info(f"[{time.time():.4f}][T:{thread_id}] Finished prediction run for: {self.input_source_identifier}")
            # Note: The thread itself should be managed (quit/deleteLater) by the caller
            # based on the signals emitted (prediction_ready, prediction_error).

    @Slot()
    def cancel(self):
        """
        Sets the cancellation flag. The running process should check this flag periodically.
        """
        log.info(f"Cancellation requested for handler: {self.input_source_identifier}")
        self._is_cancelled = True
        self.status_update.emit(f"Cancellation requested for '{Path(self.input_source_identifier).name}'...")


    @abstractmethod
    def _perform_prediction(self) -> List[SourceRule]:
        """
        Abstract method to be implemented by concrete subclasses.
        This method contains the specific logic for generating the SourceRule list.
        It should periodically check `self._is_cancelled`.

        Returns:
            A list of SourceRule objects representing the prediction results.

        Raises:
            Exception: If any critical error occurs during the prediction process.
        """
        pass