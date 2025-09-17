import sys
import os
import shutil
import json
from pathlib import Path
from typing import Optional, Tuple

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton,
    QFileDialog, QMessageBox, QGroupBox, QFormLayout, QSpinBox, QDialogButtonBox
)
from PySide6.QtCore import Qt, Slot

# Constants for bundled resource locations relative to app base
BUNDLED_CONFIG_SUBDIR_NAME = "config"
BUNDLED_PRESETS_SUBDIR_NAME = "Presets"
DEFAULT_USER_DATA_SUBDIR_NAME = "user_data" # For portable path attempt

# Files to copy from bundled config to user config
DEFAULT_CONFIG_FILES = [
    "asset_type_definitions.json",
    "file_type_definitions.json",
    "llm_settings.json",
    "suppliers.json"
]
# app_settings.json is NOT copied. user_settings.json is handled separately.

USER_SETTINGS_FILENAME = "user_settings.json"
PERSISTENT_PATH_MARKER_FILENAME = ".first_run_complete"
PERSISTENT_CONFIG_ROOT_STORAGE_FILENAME = "asset_processor_user_root.txt" # Stores USER_CHOSEN_PATH

APP_NAME = "AssetProcessor" # Used for AppData paths

def get_app_base_dir() -> Path:
    """Determines the base directory for the application (executable or script)."""
    if getattr(sys, 'frozen', False) and hasattr(sys, '_MEIPASS'):
        # Running in a PyInstaller bundle
        return Path(sys._MEIPASS)
    else:
        # Running as a script
        return Path(__file__).resolve().parent.parent # Assuming this file is in gui/ subdir

def get_os_specific_app_data_dir() -> Path:
    """Gets the OS-specific application data directory."""
    if sys.platform == "win32":
        path_str = os.getenv('APPDATA')
        if path_str:
            return Path(path_str) / APP_NAME
        # Fallback if APPDATA is not set, though unlikely
        return Path.home() / "AppData" / "Roaming" / APP_NAME
    elif sys.platform == "darwin": # macOS
        return Path.home() / "Library" / "Application Support" / APP_NAME
    else: # Linux and other Unix-like
        return Path.home() / ".config" / APP_NAME

class FirstTimeSetupDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Asset Processor - First-Time Setup")
        self.setModal(True)
        self.setMinimumWidth(600)

        self.app_base_dir = get_app_base_dir()
        self.user_chosen_path: Optional[Path] = None

        self._init_ui()
        self._propose_default_config_path()

    def _init_ui(self):
        main_layout = QVBoxLayout(self)

        # Configuration Path Group
        config_path_group = QGroupBox("Configuration Location")
        config_path_layout = QVBoxLayout()

        self.proposed_path_label = QLabel("Proposed default configuration path:")
        config_path_layout.addWidget(self.proposed_path_label)

        path_selection_layout = QHBoxLayout()
        self.config_path_edit = QLineEdit()
        self.config_path_edit.setReadOnly(False) # Allow editing, then validate
        path_selection_layout.addWidget(self.config_path_edit)
        
        browse_button = QPushButton("Browse...")
        browse_button.clicked.connect(self._browse_config_path)
        path_selection_layout.addWidget(browse_button)
        config_path_layout.addLayout(path_selection_layout)
        config_path_group.setLayout(config_path_layout)
        main_layout.addWidget(config_path_group)

        # User Settings Group
        user_settings_group = QGroupBox("Initial User Settings")
        user_settings_form_layout = QFormLayout()

        self.output_base_dir_edit = QLineEdit()
        output_base_dir_browse_button = QPushButton("Browse...")
        output_base_dir_browse_button.clicked.connect(self._browse_output_base_dir)
        output_base_dir_layout = QHBoxLayout()
        output_base_dir_layout.addWidget(self.output_base_dir_edit)
        output_base_dir_layout.addWidget(output_base_dir_browse_button)
        user_settings_form_layout.addRow("Default Library Output Path:", output_base_dir_layout)

        self.output_dir_pattern_edit = QLineEdit("[supplier]/[asset_category]/[asset_name]")
        user_settings_form_layout.addRow("Asset Structure Pattern:", self.output_dir_pattern_edit)
        
        self.output_format_16bit_primary_edit = QLineEdit("png")
        user_settings_form_layout.addRow("Default 16-bit Output Format (Primary):", self.output_format_16bit_primary_edit)

        self.output_format_8bit_edit = QLineEdit("png")
        user_settings_form_layout.addRow("Default 8-bit Output Format:", self.output_format_8bit_edit)

        self.resolution_threshold_jpg_spinbox = QSpinBox()
        self.resolution_threshold_jpg_spinbox.setRange(256, 16384)
        self.resolution_threshold_jpg_spinbox.setValue(4096)
        self.resolution_threshold_jpg_spinbox.setSuffix(" px")
        user_settings_form_layout.addRow("JPG Resolution Threshold (for 8-bit):", self.resolution_threshold_jpg_spinbox)
        
        user_settings_group.setLayout(user_settings_form_layout)
        main_layout.addWidget(user_settings_group)

        # Dialog Buttons
        self.button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        self.button_box.button(QDialogButtonBox.StandardButton.Ok).setText("Finish Setup")
        self.button_box.accepted.connect(self._on_finish_setup)
        self.button_box.rejected.connect(self.reject)
        main_layout.addWidget(self.button_box)

    def _propose_default_config_path(self):
        proposed_path = None
        
        # 1. Try portable path: user_data/ next to the application base dir
        # If running from script, app_base_dir is .../Asset_processor_tool/gui, so parent is .../Asset_processor_tool
        # If bundled, app_base_dir is the directory of the executable.
        
        # Let's refine app_base_dir for portable path logic
        # If script: Path(__file__).parent.parent = Asset_processor_tool
        # If frozen: sys._MEIPASS (which is the temp extraction dir, not ideal for persistent user_data)
        # A better approach for portable if frozen: Path(sys.executable).parent
        
        current_app_dir = Path(sys.executable).parent if getattr(sys, 'frozen', False) else self.app_base_dir

        portable_path_candidate = current_app_dir / DEFAULT_USER_DATA_SUBDIR_NAME
        try:
            portable_path_candidate.mkdir(parents=True, exist_ok=True)
            if os.access(str(portable_path_candidate), os.W_OK):
                proposed_path = portable_path_candidate
                self.proposed_path_label.setText(f"Proposed portable path (writable):")
            else:
                self.proposed_path_label.setText(f"Portable path '{portable_path_candidate}' not writable.")
        except Exception as e:
            self.proposed_path_label.setText(f"Could not use portable path '{portable_path_candidate}': {e}")
            print(f"Error checking/creating portable path: {e}") # For debugging

        # 2. Fallback to OS-specific app data directory
        if not proposed_path:
            os_specific_path = get_os_specific_app_data_dir()
            try:
                os_specific_path.mkdir(parents=True, exist_ok=True)
                if os.access(str(os_specific_path), os.W_OK):
                    proposed_path = os_specific_path
                    self.proposed_path_label.setText(f"Proposed standard path (writable):")
                else:
                    self.proposed_path_label.setText(f"Standard path '{os_specific_path}' not writable. Please choose a location.")
            except Exception as e:
                self.proposed_path_label.setText(f"Could not use standard path '{os_specific_path}': {e}. Please choose a location.")
                print(f"Error checking/creating standard path: {e}") # For debugging

        if proposed_path:
            self.config_path_edit.setText(str(proposed_path.resolve()))
        else:
            # Should not happen if OS specific path creation works, but as a last resort:
            self.config_path_edit.setText(str(Path.home())) # Default to home if all else fails
            QMessageBox.warning(self, "Path Issue", "Could not determine a default writable configuration path. Please select one manually.")

    @Slot()
    def _browse_config_path(self):
        directory = QFileDialog.getExistingDirectory(
            self,
            "Select Configuration Directory",
            self.config_path_edit.text() or str(Path.home())
        )
        if directory:
            self.config_path_edit.setText(directory)

    @Slot()
    def _browse_output_base_dir(self):
        directory = QFileDialog.getExistingDirectory(
            self,
            "Select Default Library Output Directory",
            self.output_base_dir_edit.text() or str(Path.home())
        )
        if directory:
            self.output_base_dir_edit.setText(directory)

    def _validate_inputs(self) -> bool:
        # Validate chosen config path
        path_str = self.config_path_edit.text().strip()
        if not path_str:
            QMessageBox.warning(self, "Input Error", "Configuration path cannot be empty.")
            return False
        
        self.user_chosen_path = Path(path_str)
        try:
            self.user_chosen_path.mkdir(parents=True, exist_ok=True)
            if not os.access(str(self.user_chosen_path), os.W_OK):
                QMessageBox.warning(self, "Path Error", f"The chosen configuration path '{self.user_chosen_path}' is not writable.")
                return False
        except Exception as e:
            QMessageBox.warning(self, "Path Error", f"Error with chosen configuration path '{self.user_chosen_path}': {e}")
            return False

        # Validate output base dir
        output_base_dir_str = self.output_base_dir_edit.text().strip()
        if not output_base_dir_str:
            QMessageBox.warning(self, "Input Error", "Default Library Output Path cannot be empty.")
            return False
        try:
            Path(output_base_dir_str).mkdir(parents=True, exist_ok=True) # Check if creatable
            if not os.access(output_base_dir_str, os.W_OK):
                 QMessageBox.warning(self, "Path Error", f"The chosen output base path '{output_base_dir_str}' is not writable.")
                 return False
        except Exception as e:
            QMessageBox.warning(self, "Path Error", f"Error with output base path '{output_base_dir_str}': {e}")
            return False
            
        if not self.output_dir_pattern_edit.text().strip():
            QMessageBox.warning(self, "Input Error", "Asset Structure Pattern cannot be empty.")
            return False
        if not self.output_format_16bit_primary_edit.text().strip():
            QMessageBox.warning(self, "Input Error", "Default 16-bit Output Format cannot be empty.")
            return False
        if not self.output_format_8bit_edit.text().strip():
            QMessageBox.warning(self, "Input Error", "Default 8-bit Output Format cannot be empty.")
            return False
            
        return True

    def _copy_default_files(self):
        if not self.user_chosen_path:
            return

        bundled_config_dir = self.app_base_dir / BUNDLED_CONFIG_SUBDIR_NAME
        user_target_config_dir = self.user_chosen_path / BUNDLED_CONFIG_SUBDIR_NAME # User files also go into a 'config' subdir

        try:
            user_target_config_dir.mkdir(parents=True, exist_ok=True)
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Could not create user config subdirectory '{user_target_config_dir}': {e}")
            return

        for filename in DEFAULT_CONFIG_FILES:
            source_file = bundled_config_dir / filename
            target_file = user_target_config_dir / filename
            if not target_file.exists():
                if source_file.is_file():
                    try:
                        shutil.copy2(str(source_file), str(target_file))
                        print(f"Copied '{source_file}' to '{target_file}'")
                    except Exception as e:
                        QMessageBox.warning(self, "File Copy Error", f"Could not copy '{filename}' to '{target_file}': {e}")
                else:
                    print(f"Default config file '{source_file}' not found in bundle.")
            else:
                print(f"User config file '{target_file}' already exists. Skipping copy.")

        # Copy Presets
        bundled_presets_dir = self.app_base_dir / BUNDLED_PRESETS_SUBDIR_NAME
        user_target_presets_dir = self.user_chosen_path / BUNDLED_PRESETS_SUBDIR_NAME
        
        if bundled_presets_dir.is_dir():
            try:
                user_target_presets_dir.mkdir(parents=True, exist_ok=True)
                for item in bundled_presets_dir.iterdir():
                    target_item = user_target_presets_dir / item.name
                    if not target_item.exists():
                        if item.is_file():
                            shutil.copy2(str(item), str(target_item))
                            print(f"Copied preset '{item.name}' to '{target_item}'")
                        # Add elif item.is_dir() for recursive copy if presets can have subdirs
            except Exception as e:
                QMessageBox.warning(self, "Preset Copy Error", f"Could not copy presets to '{user_target_presets_dir}': {e}")
        else:
            print(f"Bundled presets directory '{bundled_presets_dir}' not found.")


    def _save_initial_user_settings(self):
        if not self.user_chosen_path:
            return

        user_settings_path = self.user_chosen_path / USER_SETTINGS_FILENAME
        settings_data = {}

        # Load existing if it exists (though unlikely for first-time setup, but good practice)
        if user_settings_path.exists():
            try:
                with open(user_settings_path, 'r', encoding='utf-8') as f:
                    settings_data = json.load(f)
            except Exception as e:
                QMessageBox.warning(self, "Error Loading Settings", f"Could not load existing user settings from '{user_settings_path}': {e}. Will create a new one.")
                settings_data = {}
        
        # Update with new values from dialog
        settings_data['OUTPUT_BASE_DIR'] = self.output_base_dir_edit.text().strip()
        settings_data['OUTPUT_DIRECTORY_PATTERN'] = self.output_dir_pattern_edit.text().strip()
        settings_data['OUTPUT_FORMAT_16BIT_PRIMARY'] = self.output_format_16bit_primary_edit.text().strip().lower()
        settings_data['OUTPUT_FORMAT_8BIT'] = self.output_format_8bit_edit.text().strip().lower()
        settings_data['RESOLUTION_THRESHOLD_FOR_JPG'] = self.resolution_threshold_jpg_spinbox.value()
        
        # Ensure general_settings exists for app_version if needed, or other core settings
        if 'general_settings' not in settings_data:
            settings_data['general_settings'] = {}
        # Example: settings_data['general_settings']['some_new_user_setting'] = True

        try:
            with open(user_settings_path, 'w', encoding='utf-8') as f:
                json.dump(settings_data, f, indent=4)
            print(f"Saved user settings to '{user_settings_path}'")
        except Exception as e:
            QMessageBox.critical(self, "Error Saving Settings", f"Could not save user settings to '{user_settings_path}': {e}")


    def _save_persistent_info(self):
        if not self.user_chosen_path:
            return

        # 1. Save USER_CHOSEN_PATH to a persistent location (e.g., AppData)
        persistent_storage_dir = get_os_specific_app_data_dir()
        try:
            persistent_storage_dir.mkdir(parents=True, exist_ok=True)
            persistent_path_file = persistent_storage_dir / PERSISTENT_CONFIG_ROOT_STORAGE_FILENAME
            with open(persistent_path_file, 'w', encoding='utf-8') as f:
                f.write(str(self.user_chosen_path.resolve()))
            print(f"Saved chosen config path to '{persistent_path_file}'")
        except Exception as e:
            QMessageBox.warning(self, "Error Saving Path", f"Could not persistently save the chosen configuration path: {e}")
            # This is not critical enough to stop the setup, but user might need to re-select on next launch.

        # 2. Create marker file in USER_CHOSEN_PATH
        marker_file = self.user_chosen_path / PERSISTENT_PATH_MARKER_FILENAME
        try:
            with open(marker_file, 'w', encoding='utf-8') as f:
                f.write("Asset Processor first-time setup complete.")
            print(f"Created marker file at '{marker_file}'")
        except Exception as e:
            QMessageBox.warning(self, "Error Creating Marker", f"Could not create first-run marker file at '{marker_file}': {e}")

    @Slot()
    def _on_finish_setup(self):
        if not self._validate_inputs():
            return

        # Confirmation before proceeding
        reply = QMessageBox.question(self, "Confirm Setup",
                                     f"The following path will be used for configuration and user data:\n"
                                     f"{self.user_chosen_path}\n\n"
                                     f"Default configuration files and presets will be copied if they don't exist.\n"
                                     f"Initial user settings will be saved.\n\nProceed with setup?",
                                     QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                                     QMessageBox.StandardButton.No)
        if reply == QMessageBox.StandardButton.No:
            return

        try:
            self._copy_default_files()
            self._save_initial_user_settings()
            self._save_persistent_info()
            QMessageBox.information(self, "Setup Complete", "First-time setup completed successfully!")
            self.accept()
        except Exception as e:
            QMessageBox.critical(self, "Setup Error", f"An unexpected error occurred during setup: {e}")
            # Optionally, attempt cleanup or guide user
            
    def get_chosen_config_path(self) -> Optional[Path]:
        """Returns the path chosen by the user after successful completion."""
        if self.result() == QDialog.DialogCode.Accepted:
            return self.user_chosen_path
        return None

if __name__ == '__main__':
    from PySide6.QtWidgets import QApplication
    app = QApplication(sys.argv)
    dialog = FirstTimeSetupDialog()
    if dialog.exec():
        chosen_path = dialog.get_chosen_config_path()
        print(f"Dialog accepted. Chosen config path: {chosen_path}")
    else:
        print("Dialog cancelled.")
    sys.exit()