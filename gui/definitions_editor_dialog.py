import logging
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QTabWidget, QWidget, QListWidget, QListWidgetItem, QPushButton,
    QHBoxLayout, QLabel, QGroupBox, QDialogButtonBox, QFormLayout,
    QTextEdit, QColorDialog, QInputDialog, QMessageBox, QFrame, QComboBox,
    QLineEdit, QCheckBox, QAbstractItemView
)
from PySide6.QtGui import QColor, QPalette, QMouseEvent # Added QMouseEvent
from PySide6.QtCore import Qt, QEvent

# Assuming load_asset_definitions, load_file_type_definitions, load_supplier_settings
# are in configuration.py at the root level.
# Adjust the import path if configuration.py is located elsewhere relative to this file.
# For example, if configuration.py is in the parent directory:
# from ..configuration import load_asset_definitions, load_file_type_definitions, load_supplier_settings
# Or if it's in the same directory (less likely for a root config file):
# from .configuration import ...
# Given the project structure, configuration.py is at the root.
import sys
import os
# Add project root to sys.path to allow direct import of configuration
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
try:
    from configuration import (
        load_asset_definitions, save_asset_definitions,
        load_file_type_definitions, save_file_type_definitions,
        load_supplier_settings, save_supplier_settings
    )
except ImportError as e:
    logging.error(f"Failed to import configuration functions: {e}. Ensure configuration.py is in the project root and accessible.")
    # Provide dummy functions if import fails, so the UI can still be tested somewhat
    def load_asset_definitions(): return {}
    def save_asset_definitions(data): pass
    def load_file_type_definitions(): return {}
    def save_file_type_definitions(data): pass
    def load_supplier_settings(): return {}
    # def save_supplier_settings(data): pass

logger = logging.getLogger(__name__)

class DebugListWidget(QListWidget):
    def mousePressEvent(self, event: QMouseEvent): # QMouseEvent needs to be imported from PySide6.QtGui
        logger.info(f"DebugListWidget.mousePressEvent: pos={event.pos()}")
        item = self.itemAt(event.pos())
        if item:
            logger.info(f"DebugListWidget.mousePressEvent: Item under cursor: {item.text()}")
        else:
            logger.info("DebugListWidget.mousePressEvent: No item under cursor.")
        super().mousePressEvent(event)
        logger.info("DebugListWidget.mousePressEvent: super call finished.")

class DefinitionsEditorDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Definitions Editor")
        self.setGeometry(200, 200, 800, 600)  # x, y, width, height

        self.asset_type_data = {}
        self.file_type_data = {}
        self.supplier_data = {}
        self.unsaved_changes = False # For unsaved changes tracking
        self.asset_types_tab_page_for_filtering = None # For event filtering

        self._load_all_definitions()

        main_layout = QVBoxLayout(self)

        self.tab_widget = QTabWidget()
        main_layout.addWidget(self.tab_widget)

        self._create_ui() # Creates and adds tabs to self.tab_widget

        self.button_box = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        self.button_box.accepted.connect(self.save_definitions)
        self.button_box.rejected.connect(self.reject)
        main_layout.addWidget(self.button_box)

        self.setLayout(main_layout)
        # self.tab_widget.installEventFilter(self) # Temporarily disable event filter on tab_widget for this test
        # logger.info(f"Event filter on self.tab_widget ({self.tab_widget}) TEMPORARILY DISABLED for DebugListWidget test.")

    def _load_all_definitions(self):
        logger.info("Loading all definitions...")
        try:
            self.asset_type_data = load_asset_definitions()
            logger.info(f"Loaded {len(self.asset_type_data)} asset type definitions.")
        except Exception as e:
            logger.error(f"Failed to load asset type definitions: {e}")
            self.asset_type_data = {} # Ensure it's an empty dict on failure

        try:
            self.file_type_data = load_file_type_definitions()
            logger.info(f"Loaded {len(self.file_type_data)} file type definitions.")
        except Exception as e:
            logger.error(f"Failed to load file type definitions: {e}")
            self.file_type_data = {}

        try:
            self.supplier_data = load_supplier_settings()
            logger.info(f"Loaded {len(self.supplier_data)} supplier settings.")
        except Exception as e:
            logger.error(f"Failed to load supplier settings: {e}")
            self.supplier_data = {}
        logger.info("Finished loading definitions.")


    def _create_ui(self):
        self.tab_widget.addTab(self._create_asset_types_tab(), "Asset Type Definitions")
        self.tab_widget.addTab(self._create_file_types_tab(), "File Type Definitions")
        self.tab_widget.addTab(self._create_suppliers_tab(), "Supplier Settings")

        # Add a diagnostic button
        self.diag_button = QPushButton("Test Select Item 2 (Asset)")
        self.diag_button.clicked.connect(self._run_diag_selection)
        # Assuming main_layout is accessible here or passed if _create_ui is part of __init__
        # If main_layout is self.layout() established in __init__
        if self.layout(): # Check if layout exists
            self.layout().addWidget(self.diag_button)
        else:
            logger.error("Main layout not found for diagnostic button in _create_ui. Button not added.")


    def _run_diag_selection(self):
        logger.info("Diagnostic button clicked. Attempting to select second item in asset_type_list_widget.")
        if hasattr(self, 'asset_type_list_widget') and self.asset_type_list_widget.count() > 1:
            logger.info(f"Asset type list widget isEnabled: {self.asset_type_list_widget.isEnabled()}") # Check if enabled
            logger.info(f"Asset type list widget signalsBlocked: {self.asset_type_list_widget.signalsBlocked()}")
            
            self.asset_type_list_widget.setFocus() # Explicitly set focus
            logger.info(f"Attempted to set focus to asset_type_list_widget. Has focus: {self.asset_type_list_widget.hasFocus()}")
            
            item_to_select = self.asset_type_list_widget.item(1) # Select the second item (index 1)
            if item_to_select:
                logger.info(f"Programmatically selecting: {item_to_select.text()}")
                self.asset_type_list_widget.setCurrentItem(item_to_select)
                # Check if it's actually selected
                if self.asset_type_list_widget.currentItem() == item_to_select:
                    logger.info(f"Programmatic selection successful. Current item is now: {self.asset_type_list_widget.currentItem().text()}")
                else:
                    logger.warning("Programmatic selection FAILED. Current item did not change as expected.")
            else:
                logger.warning("Second item not found in asset_type_list_widget.")
        elif hasattr(self, 'asset_type_list_widget'):
            logger.warning("asset_type_list_widget has less than 2 items for diagnostic selection.")
        else:
            logger.warning("asset_type_list_widget not found for diagnostic selection.")

    def _create_tab_pane(self, title_singular, data_dict, list_widget_name):
        tab_page = QWidget()
        tab_page.setFocusPolicy(Qt.FocusPolicy.ClickFocus)
        tab_layout = QHBoxLayout(tab_page)

        # Left Pane
        left_pane_layout = QVBoxLayout()
        
        lbl_list_title = QLabel(f"{title_singular}s:")
        left_pane_layout.addWidget(lbl_list_title)

        if list_widget_name == "asset_type_list_widget":
            logger.info(f"Creating DebugListWidget for {list_widget_name}")
            list_widget = DebugListWidget(self) # Pass parent
        else:
            list_widget = QListWidget(self) # Pass parent
            
        from PySide6.QtWidgets import QAbstractItemView
        list_widget.setSelectionMode(QAbstractItemView.SingleSelection)
        list_widget.setEnabled(True)
        logger.info(f"For {list_widget_name}, SelectionMode set to SingleSelection, Enabled set to True.")
        setattr(self, list_widget_name, list_widget) # e.g., self.asset_type_list_widget = list_widget
        logger.info(f"Creating tab pane for {title_singular}, list_widget_name: {list_widget_name}")
        logger.info(f"List widget instance for {list_widget_name}: {list_widget}")
        
        # Ensure no other event filters are active on the list_widget for this specific test
        if list_widget_name == "asset_type_list_widget":
            # If an event filter was installed on list_widget by a previous debug step via self.installEventFilter(list_widget),
            # it would need to be removed here, or the logic installing it should be conditional.
            # For now, we assume no other filter is on list_widget itself.
            logger.info(f"Ensuring no stray event filter on DebugListWidget instance for {list_widget_name}.")

        if isinstance(data_dict, dict):
            for key, value_dict in data_dict.items(): # Iterate over items for UserRole data
                item = QListWidgetItem(key)
                item.setData(Qt.UserRole, value_dict) # Store the whole dict
                item.setFlags(item.flags() | Qt.ItemIsSelectable | Qt.ItemIsEnabled) # Explicitly set flags
                list_widget.addItem(item)
        else:
            logger.warning(f"Data for {title_singular} is not a dictionary, cannot populate list.")

        left_pane_layout.addWidget(list_widget)

        buttons_layout = QHBoxLayout()
        btn_add = QPushButton(f"Add {title_singular}")
        btn_remove = QPushButton(f"Remove Selected {title_singular}")
        
        # Connections for these buttons will be specific to each tab type
        if list_widget_name == "asset_type_list_widget":
            btn_add.clicked.connect(self._add_asset_type)
            btn_remove.clicked.connect(self._remove_asset_type)
            # The event filter on asset_type_list_widget should be disabled for this test.
            # Assuming the Debug mode task that set it up can be told to disable/remove it,
            # or we ensure it's not re-added here if it was part of this method.
            # For now, we just connect currentItemChanged directly.
            list_widget.currentItemChanged.connect(
                lambda current, previous, name=list_widget_name:
                    logger.info(f"LAMBDA: currentItemChanged for {name}. Current: {current.text() if current else 'None'}")
            )
            list_widget.currentItemChanged.connect(self._display_asset_type_details)
            logger.info(f"Connected currentItemChanged for {list_widget_name} to _display_asset_type_details AND diagnostic lambda.")
        elif list_widget_name == "file_type_list_widget":
            # For other list widgets, keep the previous event filter setup if it was specific,
            # or remove if it was generic and now we only want DebugListWidget for assets.
            # For this step, we are only changing asset_type_list_widget.
            btn_add.clicked.connect(self._add_file_type)
            btn_remove.clicked.connect(self._remove_file_type)
            list_widget.currentItemChanged.connect(
                lambda current, previous, name=list_widget_name:
                    logger.info(f"LAMBDA: currentItemChanged for {name}. Current: {current.text() if current else 'None'}")
            )
            list_widget.currentItemChanged.connect(self._display_file_type_details)
            logger.info(f"Connected currentItemChanged for {list_widget_name} to _display_file_type_details AND diagnostic lambda.")
        elif list_widget_name == "supplier_list_widget": # Connections for Supplier tab
            btn_add.clicked.connect(self._add_supplier)
            btn_remove.clicked.connect(self._remove_supplier)
            list_widget.currentItemChanged.connect(
                lambda current, previous, name=list_widget_name:
                    logger.info(f"LAMBDA: currentItemChanged for {name}. Current: {current.text() if current else 'None'}")
            )
            list_widget.currentItemChanged.connect(self._display_supplier_details)
            logger.info(f"Connected currentItemChanged for {list_widget_name} to _display_supplier_details AND diagnostic lambda.")

        buttons_layout.addWidget(btn_add)
        buttons_layout.addWidget(btn_remove)
        left_pane_layout.addLayout(buttons_layout)

        tab_layout.addLayout(left_pane_layout, 1) # 1 part for left pane

        # Right Pane - This will be customized by specific tab creation methods
        right_pane_widget = QWidget() # Create a generic widget to be returned
        tab_layout.addWidget(right_pane_widget, 2) # 2 parts for right pane
        
        tab_page.setEnabled(True) # Explicitly enable the tab page widget
        logger.info(f"Tab page for {title_singular} explicitly enabled.")
        tab_page.setLayout(tab_layout)
        return tab_page, right_pane_widget # Return the pane for customization

    def _create_asset_types_tab(self):
        tab_page, right_pane_container = self._create_tab_pane("Asset Type", self.asset_type_data, "asset_type_list_widget")
        self.asset_types_tab_page_for_filtering = tab_page # Store reference for event filter
        # Ensure event filter on tab_page is also disabled if it was installed
        # logger.info(f"Event filter on asset_types_tab_page ({tab_page}) should be disabled for DebugListWidget test.")
 
        # Customize the right pane for Asset Types
        right_pane_groupbox = QGroupBox("Details for Selected Asset Type")
        details_layout = QFormLayout(right_pane_groupbox)

        # Description
        self.asset_description_edit = QTextEdit()
        details_layout.addRow("Description:", self.asset_description_edit)

        # Color
        color_layout = QHBoxLayout()
        self.asset_color_swatch_label = QLabel()
        self.asset_color_swatch_label.setFixedSize(20, 20)
        self.asset_color_swatch_label.setAutoFillBackground(True)
        self._update_color_swatch("#ffffff") # Default color
        
        btn_choose_color = QPushButton("Choose Color...")
        btn_choose_color.clicked.connect(self._choose_asset_color)
        color_layout.addWidget(self.asset_color_swatch_label)
        color_layout.addWidget(btn_choose_color)
        color_layout.addStretch()
        details_layout.addRow("Color:", color_layout)

        # Examples
        examples_group = QGroupBox("Examples")
        examples_layout = QVBoxLayout(examples_group)
        
        self.asset_examples_list_widget = QListWidget()
        examples_layout.addWidget(self.asset_examples_list_widget)

        example_buttons_layout = QHBoxLayout()
        btn_add_example = QPushButton("Add Example")
        btn_remove_example = QPushButton("Remove Selected Example")
        btn_add_example.clicked.connect(self._add_asset_example)
        btn_remove_example.clicked.connect(self._remove_asset_example)
        example_buttons_layout.addWidget(btn_add_example)
        example_buttons_layout.addWidget(btn_remove_example)
        examples_layout.addLayout(example_buttons_layout)
        
        details_layout.addRow(examples_group)
        
        # Replace the generic right_pane_widget with our specific groupbox
        # To do this, we need to find the layout of right_pane_container's parent (which is tab_layout)
        # and replace the widget.
        parent_layout = right_pane_container.parentWidget().layout()
        if parent_layout:
            parent_layout.replaceWidget(right_pane_container, right_pane_groupbox)
            right_pane_container.deleteLater() # Remove the placeholder

        # Connect signals for editing
        self.asset_description_edit.textChanged.connect(self._on_asset_detail_changed)
        
        # Initial population of list widget (if not already done by _create_tab_pane)
        # and display details for the first item if any.
        self._populate_asset_type_list() # Ensure data is loaded with UserRole
        if self.asset_type_list_widget.count() > 0:
            self.asset_type_list_widget.setCurrentRow(0)
            # self._display_asset_type_details(self.asset_type_list_widget.currentItem()) # Already connected

        return tab_page

    def _populate_asset_type_list(self):
        self.asset_type_list_widget.clear()
        for key, asset_data_item in self.asset_type_data.items():
            item = QListWidgetItem(key)
            # Ensure asset_data_item is a dictionary, if not, create a default one
            if not isinstance(asset_data_item, dict):
                logger.warning(f"Asset data for '{key}' is not a dict: {asset_data_item}. Using default.")
                asset_data_item = {"description": str(asset_data_item), "color": "#ffffff", "examples": []}
            
            # Ensure essential keys exist
            asset_data_item.setdefault('description', '')
            asset_data_item.setdefault('color', '#ffffff')
            asset_data_item.setdefault('examples', [])

            item.setData(Qt.UserRole, asset_data_item)
            self.asset_type_list_widget.addItem(item)

    def _display_asset_type_details(self, current_item, previous_item=None):
        logger.info(f"_display_asset_type_details called. Current: {current_item.text() if current_item else 'None'}, Previous: {previous_item.text() if previous_item else 'None'}")
        if current_item:
            logger.info(f"Current item text: {current_item.text()}")
            logger.info(f"Current item data (UserRole): {current_item.data(Qt.UserRole)}")
        else:
            logger.info("Current item is None for asset_type_details.")

        try:
            # Disconnect signals temporarily to prevent feedback loops during population
            if hasattr(self, 'asset_description_edit'):
                try:
                    self.asset_description_edit.textChanged.disconnect(self._on_asset_detail_changed)
                    logger.debug("Disconnected asset_description_edit.textChanged")
                except TypeError: # Signal not connected
                    logger.debug("asset_description_edit.textChanged was not connected or already disconnected.")
                    pass

            if current_item:
                asset_data = current_item.data(Qt.UserRole)
                if not isinstance(asset_data, dict): # Should not happen if _populate is correct
                    logger.error(f"Invalid data for item {current_item.text()}. Expected dict, got {type(asset_data)}")
                    asset_data = {"description": "Error: Invalid data", "color": "#ff0000", "examples": []}

                self.asset_description_edit.setText(asset_data.get('description', ''))
                
                color_hex = asset_data.get('color', '#ffffff')
                self._update_color_swatch(color_hex)

                self.asset_examples_list_widget.clear()
                for example in asset_data.get('examples', []):
                    self.asset_examples_list_widget.addItem(example)
                logger.debug(f"Populated details for {current_item.text()}")
            else:
                # Clear details if no item is selected
                self.asset_description_edit.clear()
                self._update_color_swatch("#ffffff")
                self.asset_examples_list_widget.clear()
                logger.debug("Cleared asset type details as no item is selected.")

        except Exception as e:
            logger.error(f"Error in _display_asset_type_details: {e}", exc_info=True)
        finally:
            # Reconnect signals
            if hasattr(self, 'asset_description_edit'):
                try:
                    self.asset_description_edit.textChanged.connect(self._on_asset_detail_changed)
                    logger.debug("Reconnected asset_description_edit.textChanged")
                except Exception as e:
                    logger.error(f"Failed to reconnect asset_description_edit.textChanged: {e}", exc_info=True)
            logger.info("_display_asset_type_details finished.")

    def _update_color_swatch(self, color_hex):
        if hasattr(self, 'asset_color_swatch_label'):
            palette = self.asset_color_swatch_label.palette()
            palette.setColor(QPalette.Window, QColor(color_hex))
            self.asset_color_swatch_label.setPalette(palette)

    def _choose_asset_color(self):
        current_item = self.asset_type_list_widget.currentItem()
        if not current_item:
            return

        asset_data = current_item.data(Qt.UserRole)
        initial_color = QColor(asset_data.get('color', '#ffffff'))
        
        color = QColorDialog.getColor(initial_color, self, "Choose Asset Type Color")
        if color.isValid():
            color_hex = color.name()
            self._update_color_swatch(color_hex)
            asset_data['color'] = color_hex
            current_item.setData(Qt.UserRole, asset_data) # Update data in item
            self.unsaved_changes = True
            # No need to call _on_asset_detail_changed explicitly for color, direct update is fine

    def _on_asset_detail_changed(self):
        current_item = self.asset_type_list_widget.currentItem()
        if not current_item:
            return

        asset_data = current_item.data(Qt.UserRole)
        if not isinstance(asset_data, dict): return # Should not happen

        # Update description
        asset_data['description'] = self.asset_description_edit.toPlainText()
        
        # Examples are handled by their own add/remove buttons
        # Color is handled by _choose_asset_color

        current_item.setData(Qt.UserRole, asset_data) # Save changes back to the item's data
        self.unsaved_changes = True

    def _add_asset_type(self):
        new_name, ok = QInputDialog.getText(self, "Add Asset Type", "Enter name for the new asset type:")
        if ok and new_name:
            if new_name in self.asset_type_data:
                QMessageBox.warning(self, "Name Exists", f"An asset type named '{new_name}' already exists.")
                return

            default_asset_type = {
                "description": "",
                "color": "#ffffff",
                "examples": []
            }
            self.asset_type_data[new_name] = default_asset_type

            item = QListWidgetItem(new_name)
            item.setData(Qt.UserRole, default_asset_type) # Store a copy
            self.asset_type_list_widget.addItem(item)
            self.asset_type_list_widget.setCurrentItem(item) # Triggers _display_asset_type_details
            logger.info(f"Added new asset type: {new_name}")
            self.unsaved_changes = True
        elif ok and not new_name:
            QMessageBox.warning(self, "Invalid Name", "Asset type name cannot be empty.")

    def _remove_asset_type(self):
        current_item = self.asset_type_list_widget.currentItem()
        if not current_item:
            QMessageBox.information(self, "No Selection", "Please select an asset type to remove.")
            return

        asset_name = current_item.text()
        reply = QMessageBox.question(self, "Confirm Removal",
                                     f"Are you sure you want to remove the asset type '{asset_name}'?",
                                     QMessageBox.Yes | QMessageBox.No, QMessageBox.No)

        if reply == QMessageBox.Yes:
            if asset_name in self.asset_type_data:
                del self.asset_type_data[asset_name]
            
            row = self.asset_type_list_widget.row(current_item)
            self.asset_type_list_widget.takeItem(row)
            logger.info(f"Removed asset type: {asset_name}")
            self.unsaved_changes = True
            
            if self.asset_type_list_widget.count() > 0:
                new_row_to_select = max(0, row - 1) if row > 0 else 0
                if self.asset_type_list_widget.count() > new_row_to_select: # Ensure new_row_to_select is valid
                     self.asset_type_list_widget.setCurrentRow(new_row_to_select)
                else: # if list becomes empty or selection is out of bounds
                    self._display_asset_type_details(None, None)
            else:
                self._display_asset_type_details(None, None) # Clear details if list is empty

    def _add_asset_example(self):
        current_asset_item = self.asset_type_list_widget.currentItem()
        if not current_asset_item:
            QMessageBox.information(self, "No Asset Type Selected", "Please select an asset type first.")
            return

        new_example, ok = QInputDialog.getText(self, "Add Example", "Enter new example string:")
        if ok and new_example:
            asset_data = current_asset_item.data(Qt.UserRole)
            if not isinstance(asset_data, dict) or 'examples' not in asset_data:
                logger.error("Asset data is not a dict or 'examples' key is missing.")
                QMessageBox.critical(self, "Error", "Internal data error for selected asset type.")
                return
            
            if not isinstance(asset_data['examples'], list): # Ensure 'examples' is a list
                asset_data['examples'] = []

            asset_data['examples'].append(new_example)
            current_asset_item.setData(Qt.UserRole, asset_data) # Update data in item
            
            self.asset_examples_list_widget.addItem(new_example)
            logger.info(f"Added example '{new_example}' to asset type '{current_asset_item.text()}'")
            self.unsaved_changes = True
        elif ok and not new_example:
            QMessageBox.warning(self, "Invalid Example", "Example string cannot be empty.")

    def _remove_asset_example(self):
        current_asset_item = self.asset_type_list_widget.currentItem()
        if not current_asset_item:
            QMessageBox.information(self, "No Asset Type Selected", "Please select an asset type first.")
            return

        current_example_item = self.asset_examples_list_widget.currentItem()
        if not current_example_item:
            QMessageBox.information(self, "No Example Selected", "Please select an example to remove.")
            return

        example_text = current_example_item.text()
        
        # No confirmation needed as per typical list item removal, but can be added if desired.
        # reply = QMessageBox.question(self, "Confirm Removal",
        #                              f"Are you sure you want to remove the example '{example_text}'?",
        #                              QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        # if reply == QMessageBox.No:
        #     return

        asset_data = current_asset_item.data(Qt.UserRole)
        if not isinstance(asset_data, dict) or 'examples' not in asset_data or not isinstance(asset_data['examples'], list):
            logger.error("Asset data issue during example removal.")
            QMessageBox.critical(self, "Error", "Internal data error for selected asset type.")
            return

        try:
            asset_data['examples'].remove(example_text)
            current_asset_item.setData(Qt.UserRole, asset_data) # Update data in item
            
            row = self.asset_examples_list_widget.row(current_example_item)
            self.asset_examples_list_widget.takeItem(row)
            logger.info(f"Removed example '{example_text}' from asset type '{current_asset_item.text()}'")
            self.unsaved_changes = True
        except ValueError:
            logger.warning(f"Example '{example_text}' not found in internal list for asset '{current_asset_item.text()}'. UI might be out of sync.")
            # Still remove from UI if it was there
            row = self.asset_examples_list_widget.row(current_example_item)
            if row >=0: self.asset_examples_list_widget.takeItem(row)


    def _update_file_type_color_swatch(self, color_hex, swatch_label):
        if hasattr(self, swatch_label): # Check if the specific swatch label exists
            palette = swatch_label.palette()
            palette.setColor(QPalette.Window, QColor(color_hex))
            swatch_label.setPalette(palette)

    def _create_file_types_tab(self):
        tab_page, right_pane_container = self._create_tab_pane("File Type", self.file_type_data, "file_type_list_widget")

        right_pane_groupbox = QGroupBox("Details for Selected File Type")
        details_layout = QFormLayout(right_pane_groupbox)

        # Description
        self.ft_description_edit = QTextEdit()
        details_layout.addRow("Description:", self.ft_description_edit)

        # Color
        ft_color_layout = QHBoxLayout()
        self.ft_color_swatch_label = QLabel()
        self.ft_color_swatch_label.setFixedSize(20, 20)
        self.ft_color_swatch_label.setAutoFillBackground(True)
        self._update_color_swatch_generic(self.ft_color_swatch_label, "#ffffff") # Default

        btn_ft_choose_color = QPushButton("Choose Color...")
        btn_ft_choose_color.clicked.connect(self._choose_file_type_color)
        ft_color_layout.addWidget(self.ft_color_swatch_label)
        ft_color_layout.addWidget(btn_ft_choose_color)
        ft_color_layout.addStretch()
        details_layout.addRow("Color:", ft_color_layout)

        # Examples
        ft_examples_group = QGroupBox("Examples")
        ft_examples_layout = QVBoxLayout(ft_examples_group)
        self.ft_examples_list_widget = QListWidget()
        ft_examples_layout.addWidget(self.ft_examples_list_widget)
        ft_example_buttons_layout = QHBoxLayout()
        btn_ft_add_example = QPushButton("Add Example")
        btn_ft_remove_example = QPushButton("Remove Selected Example")
        btn_ft_add_example.clicked.connect(self._add_file_type_example)
        btn_ft_remove_example.clicked.connect(self._remove_file_type_example)
        ft_example_buttons_layout.addWidget(btn_ft_add_example)
        ft_example_buttons_layout.addWidget(btn_ft_remove_example)
        ft_examples_layout.addLayout(ft_example_buttons_layout)
        details_layout.addRow(ft_examples_group)

        # Standard Type
        self.ft_standard_type_edit = QLineEdit()
        details_layout.addRow("Standard Type:", self.ft_standard_type_edit)

        # Bit Depth Rule
        self.ft_bit_depth_combo = QComboBox()
        self.ft_bit_depth_combo.addItems(["respect", "force_8bit", "force_16bit"])
        details_layout.addRow("Bit Depth Rule:", self.ft_bit_depth_combo)

        # Is Grayscale
        self.ft_is_grayscale_check = QCheckBox("Is Grayscale")
        details_layout.addRow(self.ft_is_grayscale_check) # No label for checkbox itself

        # Keybind
        self.ft_keybind_edit = QLineEdit()
        self.ft_keybind_edit.setMaxLength(1) # Basic validation
        details_layout.addRow("Keybind:", self.ft_keybind_edit)

        parent_layout = right_pane_container.parentWidget().layout()
        if parent_layout:
            parent_layout.replaceWidget(right_pane_container, right_pane_groupbox)
            right_pane_container.deleteLater()

        # Connect signals for editing
        self.ft_description_edit.textChanged.connect(self._on_file_type_detail_changed)
        self.ft_standard_type_edit.textChanged.connect(self._on_file_type_detail_changed)
        self.ft_bit_depth_combo.currentIndexChanged.connect(self._on_file_type_detail_changed)
        self.ft_is_grayscale_check.stateChanged.connect(self._on_file_type_detail_changed)
        self.ft_keybind_edit.textChanged.connect(self._on_file_type_detail_changed)

        self._populate_file_type_list()
        if self.file_type_list_widget.count() > 0:
            self.file_type_list_widget.setCurrentRow(0)
            # _display_file_type_details is connected to currentItemChanged

        return tab_page

    def _populate_file_type_list(self):
        self.file_type_list_widget.clear()
        for key, ft_data_item in self.file_type_data.items():
            item = QListWidgetItem(key)
            if not isinstance(ft_data_item, dict):
                logger.warning(f"File type data for '{key}' is not a dict: {ft_data_item}. Using default.")
                ft_data_item = {
                    "description": str(ft_data_item), "color": "#ffffff", "examples": [],
                    "standard_type": "", "bit_depth_rule": "respect",
                    "is_grayscale": False, "keybind": ""
                }
            
            # Ensure all essential keys exist with defaults
            ft_data_item.setdefault('description', '')
            ft_data_item.setdefault('color', '#ffffff')
            ft_data_item.setdefault('examples', [])
            ft_data_item.setdefault('standard_type', '')
            ft_data_item.setdefault('bit_depth_rule', 'respect')
            ft_data_item.setdefault('is_grayscale', False)
            ft_data_item.setdefault('keybind', '')

            item.setData(Qt.UserRole, ft_data_item)
            self.file_type_list_widget.addItem(item)

    def _display_file_type_details(self, current_item, previous_item=None):
        logger.info(f"_display_file_type_details called. Current: {current_item.text() if current_item else 'None'}, Previous: {previous_item.text() if previous_item else 'None'}")
        if current_item:
            logger.info(f"Current item text: {current_item.text()}")
            logger.info(f"Current item data (UserRole): {current_item.data(Qt.UserRole)}")
        else:
            logger.info("Current item is None for file_type_details.")

        try:
            # Disconnect signals temporarily
            logger.debug("Disconnecting file type detail signals...")
            try: self.ft_description_edit.textChanged.disconnect(self._on_file_type_detail_changed)
            except TypeError: pass
            try: self.ft_standard_type_edit.textChanged.disconnect(self._on_file_type_detail_changed)
            except TypeError: pass
            try: self.ft_bit_depth_combo.currentIndexChanged.disconnect(self._on_file_type_detail_changed)
            except TypeError: pass
            try: self.ft_is_grayscale_check.stateChanged.disconnect(self._on_file_type_detail_changed)
            except TypeError: pass
            try: self.ft_keybind_edit.textChanged.disconnect(self._on_file_type_detail_changed)
            except TypeError: pass
            logger.debug("Finished disconnecting file type detail signals.")

            if current_item:
                ft_data = current_item.data(Qt.UserRole)
                if not isinstance(ft_data, dict):
                    logger.error(f"Invalid data for file type item {current_item.text()}. Expected dict, got {type(ft_data)}")
                    ft_data = {
                        "description": "Error: Invalid data", "color": "#ff0000", "examples": [],
                        "standard_type": "error", "bit_depth_rule": "respect",
                        "is_grayscale": False, "keybind": "X"
                    }

                self.ft_description_edit.setText(ft_data.get('description', ''))
                self._update_color_swatch_generic(self.ft_color_swatch_label, ft_data.get('color', '#ffffff'))
                
                self.ft_examples_list_widget.clear()
                for example in ft_data.get('examples', []):
                    self.ft_examples_list_widget.addItem(example)
                
                self.ft_standard_type_edit.setText(ft_data.get('standard_type', ''))
                
                bdr_index = self.ft_bit_depth_combo.findText(ft_data.get('bit_depth_rule', 'respect'))
                if bdr_index != -1:
                    self.ft_bit_depth_combo.setCurrentIndex(bdr_index)
                else:
                    self.ft_bit_depth_combo.setCurrentIndex(0) # Default to 'respect'

                self.ft_is_grayscale_check.setChecked(ft_data.get('is_grayscale', False))
                self.ft_keybind_edit.setText(ft_data.get('keybind', ''))
                logger.debug(f"Populated details for file type {current_item.text()}")
            else:
                # Clear details if no item is selected
                self.ft_description_edit.clear()
                self._update_color_swatch_generic(self.ft_color_swatch_label, "#ffffff")
                self.ft_examples_list_widget.clear()
                self.ft_standard_type_edit.clear()
                self.ft_bit_depth_combo.setCurrentIndex(0)
                self.ft_is_grayscale_check.setChecked(False)
                self.ft_keybind_edit.clear()
                logger.debug("Cleared file type details as no item is selected.")

        except Exception as e:
            logger.error(f"Error in _display_file_type_details: {e}", exc_info=True)
        finally:
            # Reconnect signals
            logger.debug("Reconnecting file type detail signals...")
            try:
                self.ft_description_edit.textChanged.connect(self._on_file_type_detail_changed)
                self.ft_standard_type_edit.textChanged.connect(self._on_file_type_detail_changed)
                self.ft_bit_depth_combo.currentIndexChanged.connect(self._on_file_type_detail_changed)
                self.ft_is_grayscale_check.stateChanged.connect(self._on_file_type_detail_changed)
                self.ft_keybind_edit.textChanged.connect(self._on_file_type_detail_changed)
                logger.debug("Finished reconnecting file type detail signals.")
            except Exception as e:
                logger.error(f"Failed to reconnect file type detail signals: {e}", exc_info=True)
            logger.info("_display_file_type_details finished.")

    def _update_color_swatch_generic(self, swatch_label, color_hex):
        """Generic color swatch update for any QLabel."""
        if swatch_label: # Check if the swatch label exists and is passed correctly
            palette = swatch_label.palette()
            palette.setColor(QPalette.Window, QColor(color_hex))
            swatch_label.setPalette(palette)
            swatch_label.update() # Ensure the label repaints

    # --- File Type action methods ---
    def _add_file_type(self):
        new_id, ok = QInputDialog.getText(self, "Add File Type", "Enter ID for the new file type (e.g., MAP_ALB):")
        if ok and new_id:
            new_id = new_id.strip() # Remove leading/trailing whitespace
            if not new_id: # Check if empty after strip
                QMessageBox.warning(self, "Invalid ID", "File type ID cannot be empty.")
                return
            if new_id in self.file_type_data:
                QMessageBox.warning(self, "ID Exists", f"A file type with ID '{new_id}' already exists.")
                return

            default_file_type = {
                "description": "",
                "color": "#ffffff",
                "examples": [],
                "standard_type": "",
                "bit_depth_rule": "respect",
                "is_grayscale": False,
                "keybind": ""
            }
            self.file_type_data[new_id] = default_file_type

            item = QListWidgetItem(new_id)
            item.setData(Qt.UserRole, default_file_type.copy()) # Store a copy for the item
            self.file_type_list_widget.addItem(item)
            self.file_type_list_widget.setCurrentItem(item) # Triggers _display_file_type_details
            logger.info(f"Added new file type: {new_id}")
            self.unsaved_changes = True
        elif ok and not new_id.strip(): # Also catch if user entered only spaces and pressed OK
            QMessageBox.warning(self, "Invalid ID", "File type ID cannot be empty.")

    def _remove_file_type(self):
        current_item = self.file_type_list_widget.currentItem()
        if not current_item:
            QMessageBox.information(self, "No Selection", "Please select a file type to remove.")
            return

        file_type_id = current_item.text()
        reply = QMessageBox.question(self, "Confirm Removal",
                                     f"Are you sure you want to remove the file type '{file_type_id}'?",
                                     QMessageBox.Yes | QMessageBox.No, QMessageBox.No)

        if reply == QMessageBox.Yes:
            if file_type_id in self.file_type_data:
                del self.file_type_data[file_type_id]
            
            row = self.file_type_list_widget.row(current_item)
            self.file_type_list_widget.takeItem(row)
            logger.info(f"Removed file type: {file_type_id}")
            self.unsaved_changes = True
            
            if self.file_type_list_widget.count() > 0:
                new_row_to_select = max(0, row - 1) if row > 0 else 0
                if self.file_type_list_widget.count() > new_row_to_select:
                     self.file_type_list_widget.setCurrentRow(new_row_to_select)
                else: # if list becomes empty or selection is out of bounds
                    self._display_file_type_details(None, None) # Clear details
            else:
                self._display_file_type_details(None, None) # Clear details if list is empty

    def _choose_file_type_color(self):
        current_item = self.file_type_list_widget.currentItem()
        if not current_item:
            return

        ft_data = current_item.data(Qt.UserRole)
        if not isinstance(ft_data, dict): # Should not happen
            logger.error("File type item data is not a dict in _choose_file_type_color.")
            return
            
        initial_color = QColor(ft_data.get('color', '#ffffff'))
        
        color = QColorDialog.getColor(initial_color, self, "Choose File Type Color")
        if color.isValid():
            color_hex = color.name()
            self._update_color_swatch_generic(self.ft_color_swatch_label, color_hex)
            ft_data['color'] = color_hex
            current_item.setData(Qt.UserRole, ft_data) # Update data in item
            self.unsaved_changes = True

    def _add_file_type_example(self):
        current_ft_item = self.file_type_list_widget.currentItem()
        if not current_ft_item:
            QMessageBox.information(self, "No File Type Selected", "Please select a file type first.")
            return

        new_example, ok = QInputDialog.getText(self, "Add File Type Example", "Enter new example string (e.g., _alb.png, .exr):")
        if ok and new_example:
            new_example = new_example.strip()
            if not new_example:
                QMessageBox.warning(self, "Invalid Example", "Example string cannot be empty.")
                return

            ft_data = current_ft_item.data(Qt.UserRole)
            if not isinstance(ft_data, dict) or 'examples' not in ft_data:
                logger.error("File type data is not a dict or 'examples' key is missing.")
                QMessageBox.critical(self, "Error", "Internal data error for selected file type.")
                return
            
            if not isinstance(ft_data['examples'], list): # Ensure 'examples' is a list
                ft_data['examples'] = []

            if new_example in ft_data['examples']:
                QMessageBox.information(self, "Example Exists", f"The example '{new_example}' already exists for this file type.")
                return

            ft_data['examples'].append(new_example)
            current_ft_item.setData(Qt.UserRole, ft_data) # Update data in item
            
            self.ft_examples_list_widget.addItem(new_example)
            logger.info(f"Added example '{new_example}' to file type '{current_ft_item.text()}'")
            self.unsaved_changes = True
        elif ok and not new_example.strip():
            QMessageBox.warning(self, "Invalid Example", "Example string cannot be empty.")

    def _remove_file_type_example(self):
        current_ft_item = self.file_type_list_widget.currentItem()
        if not current_ft_item:
            QMessageBox.information(self, "No File Type Selected", "Please select a file type first.")
            return

        current_example_item = self.ft_examples_list_widget.currentItem()
        if not current_example_item:
            QMessageBox.information(self, "No Example Selected", "Please select an example to remove.")
            return

        example_text = current_example_item.text()
        
        ft_data = current_ft_item.data(Qt.UserRole)
        if not isinstance(ft_data, dict) or 'examples' not in ft_data or not isinstance(ft_data['examples'], list):
            logger.error("File type data issue during example removal.")
            QMessageBox.critical(self, "Error", "Internal data error for selected file type.")
            return

        try:
            ft_data['examples'].remove(example_text)
            current_ft_item.setData(Qt.UserRole, ft_data) # Update data in item
            
            row = self.ft_examples_list_widget.row(current_example_item)
            self.ft_examples_list_widget.takeItem(row)
            logger.info(f"Removed example '{example_text}' from file type '{current_ft_item.text()}'")
            self.unsaved_changes = True
        except ValueError:
            logger.warning(f"Example '{example_text}' not found in internal list for file type '{current_ft_item.text()}'. UI might be out of sync.")
            row = self.ft_examples_list_widget.row(current_example_item)
            if row >=0: self.ft_examples_list_widget.takeItem(row)
        
    def _on_file_type_detail_changed(self):
        current_item = self.file_type_list_widget.currentItem()
        if not current_item:
            return

        ft_data = current_item.data(Qt.UserRole)
        if not isinstance(ft_data, dict):
            logger.error("File type item data is not a dict in _on_file_type_detail_changed.")
            return

        # Update based on which widget triggered (or update all)
        ft_data['description'] = self.ft_description_edit.toPlainText()
        ft_data['standard_type'] = self.ft_standard_type_edit.text()
        ft_data['bit_depth_rule'] = self.ft_bit_depth_combo.currentText()
        ft_data['is_grayscale'] = self.ft_is_grayscale_check.isChecked()
        
        # Keybind validation (force uppercase)
        keybind_text = self.ft_keybind_edit.text()
        if keybind_text: # MaxLength(1) is already set
            # Disconnect to prevent recursive call during setText
            try: self.ft_keybind_edit.textChanged.disconnect(self._on_file_type_detail_changed)
            except TypeError: pass
            self.ft_keybind_edit.setText(keybind_text.upper())
            # Reconnect
            self.ft_keybind_edit.textChanged.connect(self._on_file_type_detail_changed)
            ft_data['keybind'] = keybind_text.upper()
        else:
            ft_data['keybind'] = ''
            
        current_item.setData(Qt.UserRole, ft_data)
        logger.debug(f"File type '{current_item.text()}' data updated: {ft_data}")
        self.unsaved_changes = True
    # --- End Placeholder methods ---

    def _create_suppliers_tab(self):
        tab_page, right_pane_container = self._create_tab_pane("Supplier", self.supplier_data, "supplier_list_widget")

        right_pane_groupbox = QGroupBox("Details for Selected Supplier")
        details_layout = QFormLayout(right_pane_groupbox)

        # Normal Map Type
        self.supplier_normal_map_type_combo = QComboBox()
        self.supplier_normal_map_type_combo.addItems(["OpenGL", "DirectX"])
        details_layout.addRow("Normal Map Type:", self.supplier_normal_map_type_combo)

        # Replace the generic right_pane_widget
        parent_layout = right_pane_container.parentWidget().layout()
        if parent_layout:
            parent_layout.replaceWidget(right_pane_container, right_pane_groupbox)
            right_pane_container.deleteLater()

        # Connect signals for editing
        self.supplier_normal_map_type_combo.currentIndexChanged.connect(self._on_supplier_detail_changed)

        # Initial population and display
        self._populate_supplier_list()
        if self.supplier_list_widget.count() > 0:
            self.supplier_list_widget.setCurrentRow(0)
            # _display_supplier_details is connected to currentItemChanged

        return tab_page

    def _populate_supplier_list(self):
        self.supplier_list_widget.clear()
        for key, sup_data_item in self.supplier_data.items():
            item = QListWidgetItem(key)
            if not isinstance(sup_data_item, dict):
                logger.warning(f"Supplier data for '{key}' is not a dict: {sup_data_item}. Using default.")
                sup_data_item = {"normal_map_type": "OpenGL"}
            sup_data_item.setdefault('normal_map_type', 'OpenGL') # Ensure key exists
            item.setData(Qt.UserRole, sup_data_item)
            self.supplier_list_widget.addItem(item)

    def _display_supplier_details(self, current_item, previous_item=None):
        logger.info(f"_display_supplier_details called. Current: {current_item.text() if current_item else 'None'}, Previous: {previous_item.text() if previous_item else 'None'}")
        if current_item:
            logger.info(f"Current item text: {current_item.text()}")
            logger.info(f"Current item data (UserRole): {current_item.data(Qt.UserRole)}")
        else:
            logger.info("Current item is None for supplier_details.")

        try:
            # Disconnect signals temporarily
            if hasattr(self, 'supplier_normal_map_type_combo'):
                try:
                    self.supplier_normal_map_type_combo.currentIndexChanged.disconnect(self._on_supplier_detail_changed)
                    logger.debug("Disconnected supplier_normal_map_type_combo.currentIndexChanged")
                except TypeError:
                    logger.debug("supplier_normal_map_type_combo.currentIndexChanged was not connected or already disconnected.")
                    pass

            if current_item:
                supplier_name = current_item.text()
                supplier_data = self.supplier_data.get(supplier_name)
                
                if not isinstance(supplier_data, dict):
                    logger.error(f"Invalid data for supplier item {supplier_name}. Expected dict, got {type(supplier_data)}")
                    item_data_role = current_item.data(Qt.UserRole)
                    if isinstance(item_data_role, dict):
                        supplier_data = item_data_role
                    else:
                        supplier_data = {"normal_map_type": "OpenGL"}

                normal_map_type = supplier_data.get('normal_map_type', 'OpenGL')
                nmt_index = self.supplier_normal_map_type_combo.findText(normal_map_type)
                if nmt_index != -1:
                    self.supplier_normal_map_type_combo.setCurrentIndex(nmt_index)
                else:
                    self.supplier_normal_map_type_combo.setCurrentIndex(0)
                logger.debug(f"Populated details for supplier {current_item.text()}")
            else:
                # Clear details if no item is selected
                if hasattr(self, 'supplier_normal_map_type_combo'):
                    self.supplier_normal_map_type_combo.setCurrentIndex(0)
                logger.debug("Cleared supplier details as no item is selected.")

        except Exception as e:
            logger.error(f"Error in _display_supplier_details: {e}", exc_info=True)
        finally:
            # Reconnect signals
            if hasattr(self, 'supplier_normal_map_type_combo'):
                try:
                    self.supplier_normal_map_type_combo.currentIndexChanged.connect(self._on_supplier_detail_changed)
                    logger.debug("Reconnected supplier_normal_map_type_combo.currentIndexChanged")
                except Exception as e:
                    logger.error(f"Failed to reconnect supplier_normal_map_type_combo.currentIndexChanged: {e}", exc_info=True)
            logger.info("_display_supplier_details finished.")

    def _on_supplier_detail_changed(self):
        current_item = self.supplier_list_widget.currentItem()
        if not current_item:
            return

        supplier_name = current_item.text()
        if supplier_name not in self.supplier_data:
            logger.error(f"Supplier '{supplier_name}' not found in self.supplier_data during detail change.")
            return # Or create it, but that might be unexpected here

        # Ensure the entry in self.supplier_data is a dictionary
        if not isinstance(self.supplier_data[supplier_name], dict):
            self.supplier_data[supplier_name] = {} # Initialize if it's not a dict

        new_normal_map_type = self.supplier_normal_map_type_combo.currentText()
        self.supplier_data[supplier_name]['normal_map_type'] = new_normal_map_type
        
        # Update the item's UserRole data as well to keep it in sync
        current_item.setData(Qt.UserRole, self.supplier_data[supplier_name].copy())
        
        logger.debug(f"Supplier '{supplier_name}' normal_map_type updated to: {new_normal_map_type}")
        self.unsaved_changes = True

    def _add_supplier(self):
        new_name, ok = QInputDialog.getText(self, "Add Supplier", "Enter name for the new supplier:")
        if ok and new_name:
            new_name = new_name.strip()
            if not new_name:
                QMessageBox.warning(self, "Invalid Name", "Supplier name cannot be empty.")
                return
            if new_name in self.supplier_data:
                QMessageBox.warning(self, "Name Exists", f"A supplier named '{new_name}' already exists.")
                return

            default_supplier_settings = {"normal_map_type": "OpenGL"}
            self.supplier_data[new_name] = default_supplier_settings

            item = QListWidgetItem(new_name)
            item.setData(Qt.UserRole, default_supplier_settings.copy()) # Store a copy
            self.supplier_list_widget.addItem(item)
            self.supplier_list_widget.setCurrentItem(item) # Triggers display
            logger.info(f"Added new supplier: {new_name}")
            self.unsaved_changes = True
        elif ok and not new_name.strip():
            QMessageBox.warning(self, "Invalid Name", "Supplier name cannot be empty.")

    def _remove_supplier(self):
        current_item = self.supplier_list_widget.currentItem()
        if not current_item:
            QMessageBox.information(self, "No Selection", "Please select a supplier to remove.")
            return

        supplier_name = current_item.text()
        reply = QMessageBox.question(self, "Confirm Removal",
                                     f"Are you sure you want to remove the supplier '{supplier_name}'?",
                                     QMessageBox.Yes | QMessageBox.No, QMessageBox.No)

        if reply == QMessageBox.Yes:
            if supplier_name in self.supplier_data:
                del self.supplier_data[supplier_name]
            
            row = self.supplier_list_widget.row(current_item)
            self.supplier_list_widget.takeItem(row)
            logger.info(f"Removed supplier: {supplier_name}")
            self.unsaved_changes = True
            
            # Select another item or clear details
            if self.supplier_list_widget.count() > 0:
                new_row_to_select = max(0, row - 1) if row > 0 else 0
                if self.supplier_list_widget.count() > new_row_to_select:
                     self.supplier_list_widget.setCurrentRow(new_row_to_select)
                else:
                    self._display_supplier_details(None, None)
            else:
                self._display_supplier_details(None, None) # Clear details if list is empty

    def save_definitions(self):
        logger.info("Attempting to save definitions...")
        try:
            # --- Asset Type Definitions ---
            # Ensure self.asset_type_data is consistent with the QListWidget items.
            # All edits should have updated the item's UserRole data.
            # Add/Remove operations update self.asset_type_data directly.
            # This loop ensures any in-place modifications to item data (like description, color)
            # are reflected in the self.asset_type_data before saving.
            
            current_keys_in_list = set()
            if hasattr(self, 'asset_type_list_widget'): # Check if the widget exists
                for i in range(self.asset_type_list_widget.count()):
                    item = self.asset_type_list_widget.item(i)
                    key = item.text()
                    current_keys_in_list.add(key)
                    # Update self.asset_type_data with the (potentially modified) UserRole data
                    item_data = item.data(Qt.UserRole)
                    if isinstance(item_data, dict):
                         self.asset_type_data[key] = item_data
                    else:
                        logger.warning(f"Item '{key}' in asset_type_list_widget has non-dict UserRole data: {type(item_data)}. Skipping update for this item in self.asset_type_data.")
            
            # Remove any keys from self.asset_type_data that are no longer in the list
            # (should be handled by _remove_asset_type, but this is a safeguard)
            keys_to_remove_from_dict = set(self.asset_type_data.keys()) - current_keys_in_list
            for key in keys_to_remove_from_dict:
                logger.info(f"Removing orphaned key '{key}' from self.asset_type_data before saving.")
                del self.asset_type_data[key]

            save_asset_definitions(self.asset_type_data)
            logger.info("Asset Type definitions saved successfully.")

            # --- File Type Definitions ---
            if hasattr(self, 'file_type_data') and hasattr(self, 'file_type_list_widget'):
                current_ft_keys_in_list = set()
                for i in range(self.file_type_list_widget.count()):
                    item = self.file_type_list_widget.item(i)
                    key = item.text()
                    current_ft_keys_in_list.add(key)
                    item_data = item.data(Qt.UserRole)
                    if isinstance(item_data, dict):
                        self.file_type_data[key] = item_data
                    else:
                        logger.warning(f"Item '{key}' in file_type_list_widget has non-dict UserRole data: {type(item_data)}. Skipping.")
                
                keys_to_remove_ft = set(self.file_type_data.keys()) - current_ft_keys_in_list
                for key in keys_to_remove_ft:
                    logger.info(f"Removing orphaned key '{key}' from self.file_type_data before saving.")
                    del self.file_type_data[key]
                
                save_file_type_definitions(self.file_type_data)
                logger.info("File Type definitions saved successfully.")
            else:
                logger.info("File type data or list widget not found, skipping save for file types.")

            # --- Supplier Settings ---
            if hasattr(self, 'supplier_data') and hasattr(self, 'supplier_list_widget'):
                current_s_keys_in_list = set()
                for i in range(self.supplier_list_widget.count()):
                    item = self.supplier_list_widget.item(i)
                    key = item.text()
                    current_s_keys_in_list.add(key)
                    item_data = item.data(Qt.UserRole)
                    if isinstance(item_data, dict):
                         self.supplier_data[key] = item_data # Ensure self.supplier_data is up-to-date
                    else:
                        logger.warning(f"Item '{key}' in supplier_list_widget has non-dict UserRole data: {type(item_data)}. Skipping update for this item in self.supplier_data.")

                keys_to_remove_s = set(self.supplier_data.keys()) - current_s_keys_in_list
                for key in keys_to_remove_s:
                    logger.info(f"Removing orphaned key '{key}' from self.supplier_data before saving.")
                    del self.supplier_data[key]
                
                save_supplier_settings(self.supplier_data)
                logger.info("Supplier settings saved successfully.")
            else:
                logger.info("Supplier data or list widget not found, skipping save for suppliers.")


            QMessageBox.information(self, "Save Successful", "Definitions saved successfully.")
            self.unsaved_changes = False # Reset flag
            self.accept() # Close dialog on successful save

        except Exception as e:
            logger.error(f"Failed to save definitions: {e}", exc_info=True)
            QMessageBox.critical(self, "Save Error", f"Could not save definitions: {e}")
            # Optionally, do not close the dialog on error by removing self.accept() or calling self.reject()

    def reject(self):
        if self.unsaved_changes:
            reply = QMessageBox.question(self, "Unsaved Changes",
                                         "You have unsaved changes. Are you sure you want to cancel?",
                                         QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
            if reply == QMessageBox.No:
                return # Do not close
        super().reject() # Proceed with closing

    def closeEvent(self, event):
        if self.unsaved_changes:
            reply = QMessageBox.question(self, "Unsaved Changes",
                                         "You have unsaved changes. Are you sure you want to close?",
                                         QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
            if reply == QMessageBox.Yes:
                event.accept()
            else:
                event.ignore()
        else:
            event.accept()

    def eventFilter(self, watched, event: QEvent): # Renamed from mouse_event_filter
        event_type = event.type()

        if watched == self.tab_widget:
            # Construct a more identifiable name for the tab widget in logs
            tab_widget_name_for_log = self.tab_widget.objectName() if self.tab_widget.objectName() else watched.__class__.__name__
            prefix = f"EventFilter (QTabWidget '{tab_widget_name_for_log}'):"

            if event_type == QEvent.MouseButtonPress or event_type == QEvent.MouseButtonRelease:
                event_name = "Press" if event_type == QEvent.MouseButtonPress else "Release"
                
                # Ensure event has position method (it's a QMouseEvent)
                if hasattr(event, 'position') and hasattr(event, 'globalPosition') and hasattr(event, 'button'):
                    log_line = (f"{prefix} MouseButton{event_name} "
                                f"global_pos={event.globalPosition().toPoint()}, "
                                f"widget_pos={event.position().toPoint()}, "
                                f"button={event.button()}, accepted={event.isAccepted()}")
                    logger.info(log_line)

                    current_page = self.tab_widget.currentWidget()
                    if current_page:
                        # event.position() is relative to self.tab_widget (the watched object)
                        tab_widget_event_pos_float = event.position() # QPointF
                        tab_widget_event_pos = tab_widget_event_pos_float.toPoint() # QPoint

                        # Map event position from tab_widget coordinates to global, then to page coordinates
                        global_pos = self.tab_widget.mapToGlobal(tab_widget_event_pos)
                        page_event_pos = current_page.mapFromGlobal(global_pos)

                        is_over_page = current_page.rect().contains(page_event_pos)
                        page_name_for_log = current_page.objectName() if current_page.objectName() else current_page.__class__.__name__
                        
                        logger.info(f"{prefix} Event mapped to page '{page_name_for_log}' coords: {page_event_pos}. "
                                    f"Page rect: {current_page.rect()}. Is over page: {is_over_page}")

                        if is_over_page:
                            logger.info(f"{prefix} Event IS OVER CURRENT PAGE. "
                                        f"Current event.isAccepted(): {event.isAccepted()}. "
                                        f"Returning False from filter to allow propagation to QTabWidget's default handling.")
                            # Returning False means this filter does not stop the event.
                            # The event will be sent to self.tab_widget.event() for its default handling,
                            # which should then propagate to children if appropriate.
                            return False
                        else:
                            logger.info(f"{prefix} Event is NOT over current page (likely on tab bar). Allowing default QTabWidget handling.")
                    else:
                        logger.info(f"{prefix} No current page for tab_widget during mouse event.")
                else:
                    logger.warning(f"{prefix} MouseButton{event_name} received, but event object lacks expected QMouseEvent attributes.")
            
            # Example: Log other event types if needed for debugging, but keep it concise
            # elif event_type == QEvent.Enter:
            #     logger.debug(f"{prefix} Enter event")
            # elif event_type == QEvent.Leave:
            #     logger.debug(f"{prefix} Leave event")
            # elif event_type == QEvent.FocusIn:
            #     logger.debug(f"{prefix} FocusIn event")
            # elif event_type == QEvent.FocusOut:
            #     logger.debug(f"{prefix} FocusOut event")

        # For other watched objects (if any were installed on), or for events on self.tab_widget
        # that were not explicitly handled (e.g., not mouse press/release over page),
        # call the base class implementation.
        return super().eventFilter(watched, event)

if __name__ == '__main__':
    # This is for testing the dialog independently
    from PyQt5.QtWidgets import QApplication
    import sys

    # Setup basic logging for testing
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(name)s - %(message)s')

    # Create dummy config files if they don't exist for testing
    config_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'config'))
    os.makedirs(config_dir, exist_ok=True)
    
    asset_types_path = os.path.join(config_dir, 'asset_type_definitions.json')
    file_types_path = os.path.join(config_dir, 'file_type_definitions.json')
    suppliers_path = os.path.join(config_dir, 'suppliers.json')

    if not os.path.exists(asset_types_path):
        with open(asset_types_path, 'w') as f:
            f.write('{"GenericModel": {"description": "A generic 3D model"}, "TextureSet": {"description": "A set of PBR textures"}}')
    if not os.path.exists(file_types_path):
        with open(file_types_path, 'w') as f:
            f.write('{".fbx": {"description": "Filmbox format"}, ".png": {"description": "Portable Network Graphics"}}')
    if not os.path.exists(suppliers_path):
        with open(suppliers_path, 'w') as f:
            f.write('{"Poliigon": {"api_key": "dummy_key"}, "Local": {}}')

    app = QApplication(sys.argv)
    dialog = DefinitionsEditorDialog()
    dialog.show()
    sys.exit(app.exec_())