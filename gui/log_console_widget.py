import logging
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QTextEdit, QLabel, QSizePolicy
)
from PySide6.QtCore import Slot

log = logging.getLogger(__name__)

class LogConsoleWidget(QWidget):
    """
    A dedicated widget to display log messages.
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        self._init_ui()

    def _init_ui(self):
        """Initializes the UI elements for the log console."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 5, 0, 0)

        log_console_label = QLabel("Log Console:")
        self.log_console_output = QTextEdit()
        self.log_console_output.setReadOnly(True)
        self.log_console_output.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding) # Allow vertical expansion

        layout.addWidget(log_console_label)
        layout.addWidget(self.log_console_output)

        self.setVisible(False)

    @Slot(str)
    def _append_log_message(self, message):
        self.log_console_output.append(message)
        self.log_console_output.verticalScrollBar().setValue(self.log_console_output.verticalScrollBar().maximum())
