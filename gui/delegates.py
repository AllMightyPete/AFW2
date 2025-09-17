from pathlib import Path
from PySide6.QtWidgets import QStyledItemDelegate, QLineEdit, QComboBox
from PySide6.QtCore import Qt, QModelIndex
from configuration import Configuration, ConfigurationError, load_base_config # Keep load_base_config for SupplierSearchDelegate
from PySide6.QtWidgets import QListWidgetItem

import json
import logging
import os
from PySide6.QtWidgets import QCompleter

log = logging.getLogger(__name__)
SUPPLIERS_CONFIG_PATH = "config/suppliers.json"

class LineEditDelegate(QStyledItemDelegate):
    """Delegate for editing string values using a QLineEdit."""
    def createEditor(self, parent, option, index):
        editor = QLineEdit(parent)
        return editor

    def setEditorData(self, editor: QLineEdit, index: QModelIndex):
        # Use EditRole to get the raw data suitable for editing.
        value = index.model().data(index, Qt.EditRole)
        editor.setText(str(value) if value is not None else "")

    def setModelData(self, editor: QLineEdit, model, index: QModelIndex):
        value = editor.text()
        # Pass the potentially modified text back to the model's setData.
        model.setData(index, value, Qt.EditRole)

    def updateEditorGeometry(self, editor, option, index):
        editor.setGeometry(option.rect)


class ComboBoxDelegate(QStyledItemDelegate):
    """
    Delegate for editing string values from a predefined list using a QComboBox.
    Determines the list source based on column index by accessing the
    UnifiedViewModel directly.
    """
    # REMOVED main_window parameter
    def __init__(self, parent=None):
        super().__init__(parent)
        # REMOVED self.main_window store

    def createEditor(self, parent, option, index: QModelIndex):
        editor = QComboBox(parent)
        column = index.column()
        model = index.model()

        # Add a "clear" option first, associating None with it.
        editor.addItem("---", None) # UserData = None

        # Populate based on column by accessing the model's cached keys
        items_keys = [] # Default to empty list

        # --- Get keys directly from the UnifiedViewModel ---
        # Check if the model is the correct type and has the attributes
        if hasattr(model, '_asset_type_keys') and hasattr(model, '_file_type_keys'):
            try:
                # Use column constants from the model if available
                COL_ASSET_TYPE = getattr(model, 'COL_ASSET_TYPE', 3) # Default fallback
                COL_ITEM_TYPE = getattr(model, 'COL_ITEM_TYPE', 4)   # Default fallback

                if column == COL_ASSET_TYPE:
                    items_keys = model._asset_type_keys # Use cached keys
                elif column == COL_ITEM_TYPE:
                    items_keys = model._file_type_keys  # Use cached keys

            except Exception as e:
                log.error(f"Error getting keys from UnifiedViewModel in ComboBoxDelegate: {e}")
                items_keys = [] # Fallback on error
        else:
            log.warning("ComboBoxDelegate: Model is not a UnifiedViewModel or is missing key attributes (_asset_type_keys, _file_type_keys). Dropdown may be empty.")
        # --- End key retrieval from model ---

        # REMOVED the entire block that loaded Configuration based on main_window preset

        if items_keys:
            for item_key in sorted(items_keys): # Sort keys alphabetically for consistency
                # Add item with the key string itself as text and UserData
                editor.addItem(item_key, item_key)
        else:
            # If the delegate is incorrectly applied to another column,
            # it will just have the "---" option.
            pass

        return editor

    def setEditorData(self, editor: QComboBox, index: QModelIndex):
        # Get the current string value (or None) from the model via EditRole.
        value = index.model().data(index, Qt.EditRole) # This should be a string or None

        idx = -1
        if value is not None:
            # Find the index corresponding to the string value.
            idx = editor.findText(value)
        else:
            # If the model value is None, find the "---" item.
            idx = editor.findData(None) # Find the item with UserData == None

        # Set the current index, defaulting to 0 ("---") if not found.
        editor.setCurrentIndex(idx if idx != -1 else 0)


    def setModelData(self, editor: QComboBox, model, index: QModelIndex):
        # Get the UserData associated with the currently selected item.
        # This will be the string value or None (for the "---" option).
        value = editor.currentData() # This is either the string or None
        # Pass this string value or None back to the model's setData.
        model.setData(index, value, Qt.EditRole)

    def updateEditorGeometry(self, editor, option, index):
        editor.setGeometry(option.rect)

class SupplierSearchDelegate(QStyledItemDelegate):
    """
    Delegate for editing supplier names using a QLineEdit with auto-completion.
    Loads known suppliers from config/suppliers.json and allows adding new ones.
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        self.known_suppliers = self._load_suppliers()

    def _load_suppliers(self):
        """Loads the list of known suppliers from the JSON config file."""
        try:
            with open(SUPPLIERS_CONFIG_PATH, 'r') as f:
                suppliers_data = json.load(f) # Renamed variable for clarity
                if isinstance(suppliers_data, list):
                    # Ensure all items are strings
                    return sorted([str(s) for s in suppliers_data if isinstance(s, str)])
                elif isinstance(suppliers_data, dict): # ADDED: Handle dictionary case
                    # If it's a dictionary, extract keys as supplier names
                    return sorted([str(key) for key in suppliers_data.keys() if isinstance(key, str)])
                else: # MODIFIED: Updated warning message
                    log.warning(f"'{SUPPLIERS_CONFIG_PATH}' does not contain a valid list or dictionary of suppliers. Starting fresh.")
                    return []
        except FileNotFoundError:
            log.info(f"'{SUPPLIERS_CONFIG_PATH}' not found. Starting with an empty supplier list.")
            return []
        except json.JSONDecodeError:
            log.error(f"Error decoding JSON from '{SUPPLIERS_CONFIG_PATH}'. Starting fresh.", exc_info=True)
            return []
        except Exception as e:
            log.error(f"An unexpected error occurred loading '{SUPPLIERS_CONFIG_PATH}': {e}", exc_info=True)
            return []

    def _save_suppliers(self):
        """Saves the current list of known suppliers back to the JSON config file."""
        try:
            # Ensure the directory exists (though write_to_file handled initial creation)
            os.makedirs(os.path.dirname(SUPPLIERS_CONFIG_PATH), exist_ok=True)
            with open(SUPPLIERS_CONFIG_PATH, 'w') as f:
                json.dump(self.known_suppliers, f, indent=4) # Save sorted list with indentation
            log.debug(f"Successfully saved updated supplier list to '{SUPPLIERS_CONFIG_PATH}'.")
        except IOError as e:
            log.error(f"Could not write to '{SUPPLIERS_CONFIG_PATH}': {e}", exc_info=True)
        except Exception as e:
            log.error(f"An unexpected error occurred saving '{SUPPLIERS_CONFIG_PATH}': {e}", exc_info=True)


    def createEditor(self, parent, option, index):
        """Creates the QLineEdit editor with a QCompleter."""
        editor = QLineEdit(parent)
        completer = QCompleter(self.known_suppliers, editor)
        completer.setCaseSensitivity(Qt.CaseInsensitive)
        completer.setFilterMode(Qt.MatchContains) # More flexible matching
        completer.setCompletionMode(QCompleter.PopupCompletion) # Standard popup
        editor.setCompleter(completer)
        return editor

    def setEditorData(self, editor: QLineEdit, index: QModelIndex):
        """Sets the editor's initial data from the model."""
        # Use EditRole as defined in the model's data() method for supplier
        value = index.model().data(index, Qt.EditRole)
        editor.setText(str(value) if value is not None else "")

    def setModelData(self, editor: QLineEdit, model, index: QModelIndex):
        """Commits the editor's data back to the model and handles new suppliers."""
        final_text = editor.text().strip()
        value_to_set = final_text if final_text else None # Set None if empty after stripping

        # Set data in the model first
        model.setData(index, value_to_set, Qt.EditRole)

        # Add new supplier if necessary
        if final_text and final_text not in self.known_suppliers:
            log.info(f"Adding new supplier '{final_text}' to known list.")
            self.known_suppliers.append(final_text)
            self.known_suppliers.sort() # Keep the list sorted

            # Update the completer's model immediately
            completer = editor.completer()
            if completer:
                completer.model().setStringList(self.known_suppliers)

            # Save the updated list back to the file
            self._save_suppliers()

    def updateEditorGeometry(self, editor, option, index):
        """Ensures the editor widget is placed correctly."""
        editor.setGeometry(option.rect)
class ItemTypeSearchDelegate(QStyledItemDelegate):
    """
    Delegate for editing item types using a QLineEdit with auto-completion.
    Loads known item types from the provided list.
    """
    def __init__(self, item_type_keys: list[str] | None = None, parent=None):
        super().__init__(parent)
        self.item_type_keys = item_type_keys if item_type_keys else []
        log.debug(f"ItemTypeSearchDelegate initialized with {len(self.item_type_keys)} keys: {self.item_type_keys}")

    def createEditor(self, parent, option, index: QModelIndex):
        """Creates the QLineEdit editor with a QCompleter."""
        editor = QLineEdit(parent)
        # Use the keys passed during initialization
        completer = QCompleter(self.item_type_keys, editor)
        completer.setCaseSensitivity(Qt.CaseInsensitive)
        completer.setFilterMode(Qt.MatchContains)
        completer.setCompletionMode(QCompleter.PopupCompletion)
        editor.setCompleter(completer)
        return editor

    def setEditorData(self, editor: QLineEdit, index: QModelIndex):
        """Sets the editor's initial data from the model."""
        # Use EditRole as defined in the model's data() method for item type override
        value = index.model().data(index, Qt.EditRole)
        editor.setText(str(value) if value is not None else "")

    def setModelData(self, editor: QLineEdit, model, index: QModelIndex):
        """Commits the editor's data back to the model."""
        final_text = editor.text().strip()
        value_to_set = final_text if final_text else None # Set None if empty after stripping

        # Set data in the model
        # The model's setData handles updating the override and item_type
        model.setData(index, value_to_set, Qt.EditRole)
        # DO NOT add to a persistent list or save back to config

    def updateEditorGeometry(self, editor, option, index):
        """Ensures the editor widget is placed correctly."""
        editor.setGeometry(option.rect)