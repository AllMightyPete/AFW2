# gui/llm_editor_widget.py
import json
import logging
import copy # Added for deepcopy
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QTabWidget, QPlainTextEdit, QGroupBox,
    QHBoxLayout, QPushButton, QFormLayout, QLineEdit, QDoubleSpinBox,
    QSpinBox, QMessageBox, QTextEdit
)
from PySide6.QtCore import Slot as pyqtSlot, Signal as pyqtSignal # Use PySide6 equivalents

# Assuming configuration module exists and has relevant functions later
from configuration import save_llm_config, ConfigurationError
# For now, define path directly for initial structure
LLM_CONFIG_PATH = "config/llm_settings.json"

logger = logging.getLogger(__name__)

class LLMEditorWidget(QWidget):
    """
    Widget for editing LLM settings stored in config/llm_settings.json.
    """
    settings_saved = pyqtSignal() # Signal emitted when settings are successfully saved

    def __init__(self, parent=None):
        super().__init__(parent)
        self._unsaved_changes = False
        self.original_llm_settings = {} # Initialize original_llm_settings
        self._init_ui()
        self._connect_signals()
        self.save_button.setEnabled(False) # Initially disabled

    def _init_ui(self):
        """Initialize the user interface components."""
        main_layout = QVBoxLayout(self)

        # --- Main Tab Widget ---
        self.tab_widget = QTabWidget()
        main_layout.addWidget(self.tab_widget)

        # --- Tab 1: Prompt Settings ---
        self.tab_prompt = QWidget()
        prompt_layout = QVBoxLayout(self.tab_prompt)
        self.tab_widget.addTab(self.tab_prompt, "Prompt Settings")

        self.prompt_editor = QPlainTextEdit()
        self.prompt_editor.setPlaceholderText("Enter the main LLM predictor prompt here...")
        prompt_layout.addWidget(self.prompt_editor)

        # Examples GroupBox
        examples_groupbox = QGroupBox("Examples")
        examples_layout = QVBoxLayout(examples_groupbox)
        prompt_layout.addWidget(examples_groupbox)

        self.examples_tab_widget = QTabWidget()
        self.examples_tab_widget.setTabsClosable(True)
        examples_layout.addWidget(self.examples_tab_widget)

        example_button_layout = QHBoxLayout()
        examples_layout.addLayout(example_button_layout)

        self.add_example_button = QPushButton("Add Example")
        example_button_layout.addWidget(self.add_example_button)

        self.delete_example_button = QPushButton("Delete Current Example")
        example_button_layout.addWidget(self.delete_example_button)
        example_button_layout.addStretch()


        # --- Tab 2: API Settings ---
        self.tab_api = QWidget()
        api_layout = QFormLayout(self.tab_api)
        self.tab_widget.addTab(self.tab_api, "API Settings")

        self.endpoint_url_edit = QLineEdit()
        api_layout.addRow("Endpoint URL:", self.endpoint_url_edit)

        self.api_key_edit = QLineEdit()
        self.api_key_edit.setEchoMode(QLineEdit.Password)
        api_layout.addRow("API Key:", self.api_key_edit)

        self.model_name_edit = QLineEdit()
        api_layout.addRow("Model Name:", self.model_name_edit)

        self.temperature_spinbox = QDoubleSpinBox()
        self.temperature_spinbox.setRange(0.0, 2.0)
        self.temperature_spinbox.setSingleStep(0.1)
        self.temperature_spinbox.setDecimals(2)
        api_layout.addRow("Temperature:", self.temperature_spinbox)

        self.timeout_spinbox = QSpinBox()
        self.timeout_spinbox.setRange(1, 600)
        self.timeout_spinbox.setSuffix(" s")
        api_layout.addRow("Request Timeout:", self.timeout_spinbox)

        # --- Save Button ---
        save_button_layout = QHBoxLayout()
        main_layout.addLayout(save_button_layout)
        save_button_layout.addStretch()
        self.save_button = QPushButton("Save LLM Settings")
        save_button_layout.addWidget(self.save_button)

        self.setLayout(main_layout)

    def _connect_signals(self):
        """Connect signals to slots."""
        self.save_button.clicked.connect(self._save_settings)

        self.prompt_editor.textChanged.connect(self._mark_unsaved)
        self.endpoint_url_edit.textChanged.connect(self._mark_unsaved)
        self.api_key_edit.textChanged.connect(self._mark_unsaved)
        self.model_name_edit.textChanged.connect(self._mark_unsaved)
        self.temperature_spinbox.valueChanged.connect(self._mark_unsaved)
        self.timeout_spinbox.valueChanged.connect(self._mark_unsaved)

        self.add_example_button.clicked.connect(self._add_example_tab)
        self.delete_example_button.clicked.connect(self._delete_current_example_tab)
        self.examples_tab_widget.tabCloseRequested.connect(self._remove_example_tab)

        # Note: Connecting textChanged for example editors needs to happen
        # when the tabs/editors are created (in load_settings and _add_example_tab)

    @pyqtSlot()
    def load_settings(self):
        """Load settings from the JSON file and populate the UI."""
        logger.info(f"Attempting to load LLM settings from {LLM_CONFIG_PATH}")
        self.setEnabled(True) # Enable widget before trying to load

        # Clear previous examples
        while self.examples_tab_widget.count() > 0:
            self.examples_tab_widget.removeTab(0)

        try:
            with open(LLM_CONFIG_PATH, 'r', encoding='utf-8') as f:
                settings = json.load(f)
            self.original_llm_settings = copy.deepcopy(settings) # Store a deep copy

            # Populate Prompt Settings
            self.prompt_editor.setPlainText(settings.get("llm_predictor_prompt", ""))

            # Populate Examples
            examples = settings.get("llm_predictor_examples", [])
            for i, example in enumerate(examples):
                try:
                    example_text = json.dumps(example, indent=4)
                    example_editor = QTextEdit()
                    example_editor.setPlainText(example_text)
                    example_editor.textChanged.connect(self._mark_unsaved)
                    self.examples_tab_widget.addTab(example_editor, f"Example {i+1}")
                except TypeError as e:
                    logger.error(f"Error formatting example {i+1}: {e}. Skipping.")
                    QMessageBox.warning(self, "Load Error", f"Could not format example {i+1}. It might be invalid.\nError: {e}")


            # Populate API Settings
            self.endpoint_url_edit.setText(settings.get("llm_endpoint_url", ""))
            self.api_key_edit.setText(settings.get("llm_api_key", "")) # Consider security implications
            self.model_name_edit.setText(settings.get("llm_model_name", ""))
            self.temperature_spinbox.setValue(settings.get("llm_temperature", 0.7))
            self.timeout_spinbox.setValue(settings.get("llm_request_timeout", 120))

            logger.info("LLM settings loaded successfully.")

        except FileNotFoundError:
            logger.warning(f"LLM settings file not found: {LLM_CONFIG_PATH}. Using defaults.")
            QMessageBox.warning(self, "Load Error",
                                f"LLM settings file not found:\n{LLM_CONFIG_PATH}\n\nNew settings will be created if you save.")
            # Reset to defaults (optional, or leave fields empty)
            self.prompt_editor.clear()
            self.endpoint_url_edit.clear()
            self.api_key_edit.clear()
            self.model_name_edit.clear()
            self.temperature_spinbox.setValue(0.7)
            self.timeout_spinbox.setValue(120)
            self.original_llm_settings = {} # Start with empty original settings if file not found

        except json.JSONDecodeError as e:
            logger.error(f"Error decoding JSON from {LLM_CONFIG_PATH}: {e}")
            QMessageBox.critical(self, "Load Error",
                                 f"Failed to parse LLM settings file:\n{LLM_CONFIG_PATH}\n\nError: {e}\n\nPlease check the file for syntax errors. Editor will be disabled.")
            self.setEnabled(False) # Disable editor on critical load error
            self.original_llm_settings = {} # Reset original settings on JSON error

        except Exception as e: # Catch other potential errors during loading/populating
             logger.error(f"An unexpected error occurred loading LLM settings: {e}", exc_info=True)
             QMessageBox.critical(self, "Load Error",
                                  f"An unexpected error occurred while loading settings:\n{e}\n\nEditor will be disabled.")
             self.setEnabled(False)
             self.original_llm_settings = {} # Reset original settings on other errors


        # Reset unsaved changes flag and disable save button after loading
        self.save_button.setEnabled(False)
        self._unsaved_changes = False

    @pyqtSlot()
    def _mark_unsaved(self):
        """Mark settings as having unsaved changes and enable the save button."""
        if not self._unsaved_changes:
            self._unsaved_changes = True
            self.save_button.setEnabled(True)
            logger.debug("Unsaved changes marked.")

    @pyqtSlot()
    def _save_settings(self):
        """Gather data from UI, save to JSON file, and handle errors."""
        logger.info("Attempting to save LLM settings...")

        # 1.a. Load Current Target File
        target_file_content = {}
        try:
            with open(LLM_CONFIG_PATH, 'r', encoding='utf-8') as f:
                target_file_content = json.load(f)
        except FileNotFoundError:
            logger.info(f"{LLM_CONFIG_PATH} not found. Will create a new one.")
            target_file_content = {} # Start with an empty dict if file doesn't exist
        except json.JSONDecodeError as e:
            logger.error(f"Error decoding existing {LLM_CONFIG_PATH}: {e}. Starting with an empty config for save.")
            QMessageBox.warning(self, "Warning",
                                f"Could not parse existing LLM settings file ({LLM_CONFIG_PATH}).\n"
                                f"Any pre-existing settings in that file might be overwritten if you save now.\nError: {e}")
            target_file_content = {} # Start fresh if current file is corrupt

        # 1.b. Gather current UI settings into current_llm_settings
        current_llm_settings = {}
        parsed_examples = []
        has_errors = False # For example parsing

        current_llm_settings["llm_endpoint_url"] = self.endpoint_url_edit.text().strip()
        current_llm_settings["llm_api_key"] = self.api_key_edit.text() # Keep as is
        current_llm_settings["llm_model_name"] = self.model_name_edit.text().strip()
        current_llm_settings["llm_temperature"] = self.temperature_spinbox.value()
        current_llm_settings["llm_request_timeout"] = self.timeout_spinbox.value()
        current_llm_settings["llm_predictor_prompt"] = self.prompt_editor.toPlainText().strip()

        for i in range(self.examples_tab_widget.count()):
            example_editor = self.examples_tab_widget.widget(i)
            if isinstance(example_editor, QTextEdit):
                example_text = example_editor.toPlainText().strip()
                if not example_text:
                    continue
                try:
                    parsed_example = json.loads(example_text)
                    parsed_examples.append(parsed_example)
                except json.JSONDecodeError as e:
                    has_errors = True
                    tab_name = self.examples_tab_widget.tabText(i)
                    logger.warning(f"Invalid JSON in '{tab_name}': {e}. Skipping example.")
                    QMessageBox.warning(self, "Invalid Example",
                                        f"The content in '{tab_name}' is not valid JSON and will not be saved.\n\nError: {e}\n\nPlease correct it or remove the tab.")
            else:
                logger.warning(f"Widget at index {i} in examples tab is not a QTextEdit. Skipping.")

        if has_errors:
            logger.warning("LLM settings not saved due to invalid JSON in examples.")
            return

        current_llm_settings["llm_predictor_examples"] = parsed_examples

        # 1.c. Identify Changes and Update Target File Content
        changed_settings_count = 0
        for key, current_value in current_llm_settings.items():
            original_value = self.original_llm_settings.get(key)

            # Special handling for lists (e.g., examples) - direct comparison works
            # For other types, direct comparison also works.
            # This includes new keys present in current_llm_settings but not in original_llm_settings
            if key not in self.original_llm_settings or current_value != original_value:
                target_file_content[key] = current_value
                logger.debug(f"Setting '{key}' changed or added. Old: '{original_value}', New: '{current_value}'")
                changed_settings_count +=1

        if changed_settings_count == 0 and self._unsaved_changes:
             logger.info("Save called, but no actual changes detected compared to original loaded settings.")
             # If _unsaved_changes was true, it means UI interaction happened,
             # but values might have been reverted to original.
             # We still proceed to save target_file_content as it might contain
             # values from a file that was modified externally since last load.
             # Or, if the file didn't exist, it will now be created with current UI values.

        # 1.d. Save Updated Content
        try:
            save_llm_config(target_file_content) # Save the potentially modified target_file_content
            QMessageBox.information(self, "Save Successful", f"LLM settings saved to:\n{LLM_CONFIG_PATH}")
            
            # Update original_llm_settings to reflect the newly saved state
            self.original_llm_settings = copy.deepcopy(target_file_content)
            
            self.save_button.setEnabled(False)
            self._unsaved_changes = False
            self.settings_saved.emit()
            logger.info("LLM settings saved successfully.")

        except ConfigurationError as e:
            logger.error(f"Failed to save LLM settings: {e}")
            QMessageBox.critical(self, "Save Error", f"Could not save LLM settings.\n\nError: {e}")
            self.save_button.setEnabled(True) # Keep save enabled
            self._unsaved_changes = True
        except Exception as e:
            logger.error(f"An unexpected error occurred during LLM settings save: {e}", exc_info=True)
            QMessageBox.critical(self, "Save Error", f"An unexpected error occurred while saving settings:\n{e}")
            self.save_button.setEnabled(True) # Keep save enabled
            self._unsaved_changes = True

    # --- Example Management Slots ---
    @pyqtSlot()
    def _add_example_tab(self):
        """Add a new, empty tab for an LLM example."""
        logger.debug("Adding new example tab.")
        new_example_editor = QTextEdit()
        new_example_editor.setPlaceholderText("Enter example JSON here...")
        new_example_editor.textChanged.connect(self._mark_unsaved)

        # Determine the next example number
        next_example_num = self.examples_tab_widget.count() + 1
        index = self.examples_tab_widget.addTab(new_example_editor, f"Example {next_example_num}")
        self.examples_tab_widget.setCurrentIndex(index) # Focus the new tab
        new_example_editor.setFocus() # Focus the editor within the tab

        self._mark_unsaved() # Mark changes since we added a tab

    @pyqtSlot()
    def _delete_current_example_tab(self):
        """Delete the currently selected example tab."""
        current_index = self.examples_tab_widget.currentIndex()
        if current_index != -1: # Check if a tab is selected
            logger.debug(f"Deleting current example tab at index {current_index}.")
            self._remove_example_tab(current_index) # Reuse the remove logic
        else:
            logger.debug("Delete current example tab called, but no tab is selected.")

    @pyqtSlot(int)
    def _remove_example_tab(self, index):
        """Remove the example tab at the given index."""
        if 0 <= index < self.examples_tab_widget.count():
            widget_to_remove = self.examples_tab_widget.widget(index)
            self.examples_tab_widget.removeTab(index)
            if widget_to_remove:
                # Disconnect signals if necessary, though Python's GC should handle it
                # widget_to_remove.textChanged.disconnect(self._mark_unsaved) # Optional cleanup
                widget_to_remove.deleteLater() # Ensure proper cleanup of the widget
            logger.debug(f"Removed example tab at index {index}.")

            # Renumber subsequent tabs
            for i in range(index, self.examples_tab_widget.count()):
                self.examples_tab_widget.setTabText(i, f"Example {i+1}")

            self._mark_unsaved() # Mark changes since we removed a tab
        else:
            logger.warning(f"Attempted to remove example tab at invalid index {index}.")