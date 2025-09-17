import sys
import os
import json
import logging
from pathlib import Path
from functools import partial

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QListWidget, QPushButton, QLabel, QTabWidget, QComboBox,
    QLineEdit, QTextEdit, QSpinBox, QTableWidget, QGroupBox, QFormLayout,
    QHeaderView, QAbstractItemView, QListWidgetItem, QTableWidgetItem, QMessageBox,
    QFileDialog, QInputDialog, QSizePolicy
)
from PySide6.QtCore import Qt, Signal, QObject, Slot
from PySide6.QtGui import QAction # Keep QAction if needed for context menus within editor later

# --- Constants ---
# Assuming project root is parent of the directory containing this file
script_dir = Path(__file__).parent
project_root = script_dir.parent
PRESETS_DIR = project_root / "Presets"
TEMPLATE_PATH = PRESETS_DIR / "_template.json"
APP_SETTINGS_PATH_LOCAL = project_root / "config" / "app_settings.json" # Retain for other settings if used elsewhere
FILE_TYPE_DEFINITIONS_PATH = project_root / "config" / "file_type_definitions.json"


log = logging.getLogger(__name__)

# --- Preset Editor Widget ---

class PresetEditorWidget(QWidget):
    """
    Widget dedicated to managing and editing presets.
    Contains the preset list, editor tabs, and save/load functionality.
    """
    # Signal emitted when presets list changes (saved, deleted, new)
    presets_changed_signal = Signal()
    # Signal emitted when the selected preset (or LLM/Placeholder) changes
    # Emits: mode ("preset", "llm", "placeholder"), display_name (str or None), file_path (Path or None)
    preset_selection_changed_signal = Signal(str, str, Path)

    def __init__(self, parent=None):
        super().__init__(parent)

        # --- Internal State ---
        self._last_valid_preset_name = None # Store the name of the last valid preset loaded
        self.current_editing_preset_path = None
        self.editor_unsaved_changes = False
        self._is_loading_editor = False # Flag to prevent signals during load

        # --- UI Setup ---
        self._init_ui()

        # --- Initial State ---
        self._ftd_keys = self._get_file_type_definition_keys()
        self._clear_editor()
        self._set_editor_enabled(False)
        self.populate_presets()

        # --- Connect Editor Signals ---
        self._connect_editor_change_signals()

    def _get_file_type_definition_keys(self) -> list[str]:
        """Loads FILE_TYPE_DEFINITIONS keys from app_settings.json."""
        keys = []
        try:
            if FILE_TYPE_DEFINITIONS_PATH.is_file():
                with open(FILE_TYPE_DEFINITIONS_PATH, 'r', encoding='utf-8') as f:
                    settings = json.load(f)
                # The FILE_TYPE_DEFINITIONS key is at the root of file_type_definitions.json
                ftd = settings.get("FILE_TYPE_DEFINITIONS", {})
                keys = list(ftd.keys())
                log.debug(f"Successfully loaded {len(keys)} FILE_TYPE_DEFINITIONS keys from {FILE_TYPE_DEFINITIONS_PATH}.")
            else:
                log.error(f"file_type_definitions.json not found at {FILE_TYPE_DEFINITIONS_PATH} for PresetEditorWidget.")
        except json.JSONDecodeError as e:
            log.error(f"Failed to parse file_type_definitions.json in PresetEditorWidget: {e}")
        except Exception as e:
            log.error(f"Error loading FILE_TYPE_DEFINITIONS keys from {FILE_TYPE_DEFINITIONS_PATH} in PresetEditorWidget: {e}")
        return keys

    def _init_ui(self):
        """Initializes the UI elements for the preset editor."""
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0) # Let containers manage margins
        main_layout.setSpacing(0) # No space between selector and editor containers

        # Preset List and Controls
        self.selector_container = QWidget()
        selector_layout = QVBoxLayout(self.selector_container)
        selector_layout.setContentsMargins(5, 5, 5, 5) # Margins for selector area

        selector_layout.addWidget(QLabel("Presets:"))
        self.editor_preset_list = QListWidget()
        self.editor_preset_list.currentItemChanged.connect(self._load_selected_preset_for_editing)
        selector_layout.addWidget(self.editor_preset_list)

        list_button_layout = QHBoxLayout()
        self.editor_new_button = QPushButton("New")
        self.editor_delete_button = QPushButton("Delete")
        self.editor_new_button.clicked.connect(self._new_preset)
        self.editor_delete_button.clicked.connect(self._delete_selected_preset)
        list_button_layout.addWidget(self.editor_new_button)
        list_button_layout.addWidget(self.editor_delete_button)
        selector_layout.addLayout(list_button_layout)
        main_layout.addWidget(self.selector_container)

        # Editor Tabs
        self.json_editor_container = QWidget()
        editor_layout = QVBoxLayout(self.json_editor_container)
        editor_layout.setContentsMargins(5, 0, 5, 5) # Margins for editor area (no top margin)

        self.editor_tab_widget = QTabWidget()
        self.editor_tab_general_naming = QWidget()
        self.editor_tab_mapping_rules = QWidget()
        self.editor_tab_widget.addTab(self.editor_tab_general_naming, "General & Naming")
        self.editor_tab_widget.addTab(self.editor_tab_mapping_rules, "Mapping & Rules")
        self._create_editor_general_tab()
        self._create_editor_mapping_tab()
        editor_layout.addWidget(self.editor_tab_widget, 1) # Allow tabs to stretch

        # Save Buttons
        save_button_layout = QHBoxLayout()
        self.editor_save_button = QPushButton("Save")
        self.editor_save_as_button = QPushButton("Save As...")
        self.editor_save_button.setEnabled(False)
        self.editor_save_button.clicked.connect(self._save_current_preset)
        self.editor_save_as_button.clicked.connect(self._save_preset_as)
        save_button_layout.addStretch()
        save_button_layout.addWidget(self.editor_save_button)
        save_button_layout.addWidget(self.editor_save_as_button)
        editor_layout.addLayout(save_button_layout)

        main_layout.addWidget(self.json_editor_container)

    def _create_editor_general_tab(self):
        """Creates the widgets and layout for the 'General & Naming' editor tab."""
        layout = QVBoxLayout(self.editor_tab_general_naming)
        form_layout = QFormLayout()
        form_layout.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)

        # Basic Info
        self.editor_preset_name = QLineEdit()
        self.editor_supplier_name = QLineEdit()
        self.editor_notes = QTextEdit()
        self.editor_notes.setAcceptRichText(False)
        self.editor_notes.setFixedHeight(60)
        form_layout.addRow("Preset Name:", self.editor_preset_name)
        form_layout.addRow("Supplier Name:", self.editor_supplier_name)
        form_layout.addRow("Notes:", self.editor_notes)

        layout.addLayout(form_layout)

        # Source Naming Group
        naming_group = QGroupBox("Source File Naming Rules")
        naming_layout_outer = QVBoxLayout(naming_group)
        naming_layout_form = QFormLayout()
        self.editor_separator = QLineEdit()
        self.editor_separator.setMaxLength(1)
        self.editor_spin_base_name_idx = QSpinBox()
        self.editor_spin_base_name_idx.setMinimum(-1)
        self.editor_spin_map_type_idx = QSpinBox()
        self.editor_spin_map_type_idx.setMinimum(-1)
        naming_layout_form.addRow("Separator:", self.editor_separator)
        naming_layout_form.addRow("Base Name Index:", self.editor_spin_base_name_idx)
        naming_layout_form.addRow("Map Type Index:", self.editor_spin_map_type_idx)
        naming_layout_outer.addLayout(naming_layout_form)
        # Gloss Keywords List
        self._setup_list_widget_with_controls(naming_layout_outer, "Glossiness Keywords", "editor_list_gloss_keywords")
        # Bit Depth Variants Table
        self._setup_table_widget_with_controls(naming_layout_outer, "16-bit Variant Patterns", "editor_table_bit_depth_variants", ["Map Type", "Pattern"])
        self.editor_table_bit_depth_variants.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.editor_table_bit_depth_variants.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        layout.addWidget(naming_group)

        # Extra Files Group
        self._setup_list_widget_with_controls(layout, "Move to 'Extra' Folder Patterns", "editor_list_extra_patterns")

        layout.addStretch(1)

    def _create_editor_mapping_tab(self):
        """Creates the widgets and layout for the 'Mapping & Rules' editor tab."""
        layout = QVBoxLayout(self.editor_tab_mapping_rules)

        # Map Type Mapping Group
        self._setup_table_widget_with_controls(layout, "Map Type Mapping (Standard Type <- Input Keywords)", "editor_table_map_type_mapping", ["Standard Type", "Input Keywords (comma-sep)"])
        self.editor_table_map_type_mapping.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.editor_table_map_type_mapping.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)

        # Category Rules Group
        category_group = QGroupBox("Asset Category Rules")
        category_layout = QVBoxLayout(category_group)
        self._setup_list_widget_with_controls(category_layout, "Model File Patterns", "editor_list_model_patterns")
        self._setup_list_widget_with_controls(category_layout, "Decal Keywords", "editor_list_decal_keywords")
        layout.addWidget(category_group)

        # Archetype Rules Group
        self._setup_table_widget_with_controls(layout, "Archetype Rules", "editor_table_archetype_rules", ["Archetype Name", "Match Any (comma-sep)", "Match All (comma-sep)"])
        self.editor_table_archetype_rules.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.editor_table_archetype_rules.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.editor_table_archetype_rules.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)

        layout.addStretch(1)

    # --- Helper Functions for UI Setup (Moved into class) ---
    def _setup_list_widget_with_controls(self, parent_layout, label_text, attribute_name):
        """Adds a QListWidget with Add/Remove buttons to a layout."""
        list_widget = QListWidget()
        list_widget.setAlternatingRowColors(True)
        list_widget.setEditTriggers(QAbstractItemView.EditTrigger.DoubleClicked | QAbstractItemView.EditTrigger.SelectedClicked | QAbstractItemView.EditTrigger.EditKeyPressed)
        setattr(self, attribute_name, list_widget)

        add_button = QPushButton("+")
        remove_button = QPushButton("-")
        add_button.setFixedWidth(30)
        remove_button.setFixedWidth(30)

        button_layout = QVBoxLayout()
        button_layout.addWidget(add_button)
        button_layout.addWidget(remove_button)
        button_layout.addStretch()

        list_layout = QHBoxLayout()
        list_layout.addWidget(list_widget)
        list_layout.addLayout(button_layout)

        group_box = QGroupBox(label_text)
        group_box_layout = QVBoxLayout(group_box)
        group_box_layout.addLayout(list_layout)

        parent_layout.addWidget(group_box)

        # Connections
        add_button.clicked.connect(partial(self._editor_add_list_item, list_widget))
        remove_button.clicked.connect(partial(self._editor_remove_list_item, list_widget))
        list_widget.itemChanged.connect(self._mark_editor_unsaved)

    def _setup_table_widget_with_controls(self, parent_layout, label_text, attribute_name, columns):
        """Adds a QTableWidget with Add/Remove buttons to a layout."""
        table_widget = QTableWidget()
        table_widget.setColumnCount(len(columns))
        table_widget.setHorizontalHeaderLabels(columns)
        table_widget.setAlternatingRowColors(True)
        setattr(self, attribute_name, table_widget)

        add_button = QPushButton("+ Row")
        remove_button = QPushButton("- Row")

        button_layout = QHBoxLayout()
        button_layout.addStretch()
        button_layout.addWidget(add_button)
        button_layout.addWidget(remove_button)

        group_box = QGroupBox(label_text)
        group_box_layout = QVBoxLayout(group_box)
        group_box_layout.addWidget(table_widget)
        group_box_layout.addLayout(button_layout)

        parent_layout.addWidget(group_box)

        # Connections
        add_button.clicked.connect(partial(self._editor_add_table_row, table_widget))
        remove_button.clicked.connect(partial(self._editor_remove_table_row, table_widget))
        table_widget.itemChanged.connect(self._mark_editor_unsaved)

    # --- Preset Population and Handling ---
    def populate_presets(self):
        """Scans presets dir and populates the editor list."""
        log.debug("Populating preset list in PresetEditorWidget...")
        current_list_item = self.editor_preset_list.currentItem()
        current_list_selection_text = current_list_item.text() if current_list_item else None

        self.editor_preset_list.clear()
        log.debug("Preset list cleared.")

        placeholder_item = QListWidgetItem("--- Select a Preset ---")
        placeholder_item.setFlags(placeholder_item.flags() & ~Qt.ItemFlag.ItemIsSelectable & ~Qt.ItemFlag.ItemIsEditable)
        placeholder_item.setData(Qt.ItemDataRole.UserRole, "__PLACEHOLDER__")
        self.editor_preset_list.addItem(placeholder_item)
        log.debug("Added '--- Select a Preset ---' placeholder item.")

        llm_item = QListWidgetItem("- LLM Interpretation -")
        llm_item.setData(Qt.ItemDataRole.UserRole, "__LLM__") # Special identifier
        self.editor_preset_list.addItem(llm_item)
        log.debug("Added '- LLM Interpretation -' item.")

        if not PRESETS_DIR.is_dir():
            msg = f"Error: Presets directory not found at {PRESETS_DIR}"
            log.error(msg)
            return

        presets = sorted([f for f in PRESETS_DIR.glob("*.json") if f.is_file() and not f.name.startswith('_')])

        if not presets:
            msg = "Warning: No presets found in presets directory."
            log.warning(msg)
        else:
            for preset_path in presets:
                preset_display_name = preset_path.stem # Fallback
                try:
                    with open(preset_path, 'r', encoding='utf-8') as f:
                        preset_content = json.load(f)
                    internal_name = preset_content.get("preset_name")
                    if internal_name and isinstance(internal_name, str) and internal_name.strip():
                        preset_display_name = internal_name.strip()
                    else:
                        log.warning(f"Preset file {preset_path.name} is missing 'preset_name' or it's empty. Using filename stem '{preset_path.stem}' as display name.")
                except json.JSONDecodeError:
                    log.error(f"Failed to parse JSON from {preset_path.name}. Using filename stem '{preset_path.stem}' as display name.")
                except Exception as e:
                    log.error(f"Error reading {preset_path.name}: {e}. Using filename stem '{preset_path.stem}' as display name.")
                
                item = QListWidgetItem(preset_display_name)
                item.setData(Qt.ItemDataRole.UserRole, preset_path) # Store the path for loading
                self.editor_preset_list.addItem(item)
            log.info(f"Loaded {len(presets)} presets into editor list.")

        # Select the "Select a Preset" item by default
        log.debug("Preset list populated. Selecting '--- Select a Preset ---' item.")
        self.editor_preset_list.setCurrentItem(placeholder_item)

    # --- Preset Editor Methods ---

    def _editor_add_list_item(self, list_widget: QListWidget):
        """Adds an editable item to the specified list widget in the editor."""
        text, ok = QInputDialog.getText(self, f"Add Item", "Enter value:")
        if ok and text:
            item = QListWidgetItem(text)
            list_widget.addItem(item)
            self._mark_editor_unsaved()

    def _editor_remove_list_item(self, list_widget: QListWidget):
        """Removes the selected item from the specified list widget in the editor."""
        selected_items = list_widget.selectedItems()
        if not selected_items: return
        for item in selected_items: list_widget.takeItem(list_widget.row(item))
        self._mark_editor_unsaved()

    def _editor_add_table_row(self, table_widget: QTableWidget):
        """Adds an empty row to the specified table widget in the editor."""
        row_count = table_widget.rowCount()
        table_widget.insertRow(row_count)

        if table_widget == self.editor_table_map_type_mapping:
            # Column 0: Standard Type (QComboBox)
            combo_box = QComboBox()
            if self._ftd_keys:
                combo_box.addItems(self._ftd_keys)
            else:
                log.warning("FILE_TYPE_DEFINITIONS keys not available for ComboBox in map_type_mapping.")
            combo_box.currentIndexChanged.connect(self._mark_editor_unsaved)
            table_widget.setCellWidget(row_count, 0, combo_box)
            # Column 1: Input Keywords (QTableWidgetItem)
            table_widget.setItem(row_count, 1, QTableWidgetItem(""))
        else: # For other tables
            for col in range(table_widget.columnCount()):
                table_widget.setItem(row_count, col, QTableWidgetItem(""))
        self._mark_editor_unsaved()

    def _editor_remove_table_row(self, table_widget: QTableWidget):
        """Removes the selected row(s) from the specified table widget in the editor."""
        selected_rows = sorted(list(set(index.row() for index in table_widget.selectedIndexes())), reverse=True)
        if not selected_rows:
            if table_widget.rowCount() > 0: selected_rows = [table_widget.rowCount() - 1]
            else: return
        for row in selected_rows: table_widget.removeRow(row)
        self._mark_editor_unsaved()

    def _mark_editor_unsaved(self):
        """Marks changes in the editor panel as unsaved."""
        if self._is_loading_editor: return
        self.editor_unsaved_changes = True
        self.editor_save_button.setEnabled(True)

    def _connect_editor_change_signals(self):
        """Connect signals from all editor widgets to mark_editor_unsaved."""
        self.editor_preset_name.textChanged.connect(self._mark_editor_unsaved)
        self.editor_supplier_name.textChanged.connect(self._mark_editor_unsaved)
        self.editor_notes.textChanged.connect(self._mark_editor_unsaved)
        self.editor_separator.textChanged.connect(self._mark_editor_unsaved)
        self.editor_spin_base_name_idx.valueChanged.connect(self._mark_editor_unsaved)
        self.editor_spin_map_type_idx.valueChanged.connect(self._mark_editor_unsaved)
        # List/Table widgets are connected via helper functions
    def check_unsaved_changes(self) -> bool:
        """
        Checks for unsaved changes in the editor and prompts the user.
        Returns True if the calling action should be cancelled.
        (Called by MainWindow's closeEvent or before loading a new preset).
        """
        if not self.editor_unsaved_changes: return False # No unsaved changes, proceed
        reply = QMessageBox.question(self, "Unsaved Preset Changes", # Use self as parent
                                     "You have unsaved changes in the preset editor. Discard them?",
                                     QMessageBox.StandardButton.Save | QMessageBox.StandardButton.Discard | QMessageBox.StandardButton.Cancel,
                                     QMessageBox.StandardButton.Cancel)
        if reply == QMessageBox.StandardButton.Save:
            save_successful = self._save_current_preset()
            return not save_successful # Return True (cancel) if save fails
        elif reply == QMessageBox.StandardButton.Discard:
            return False # Discarded, proceed
        else: # Cancelled
            return True # Cancel the original action

    def _set_editor_enabled(self, enabled: bool):
        """Enables or disables all editor widgets."""
        # Target the container holding the tabs and save buttons
        self.json_editor_container.setEnabled(enabled)
        # Save button state still depends on unsaved changes, but only if container is enabled
        self.editor_save_button.setEnabled(enabled and self.editor_unsaved_changes)

    def _clear_editor(self):
        """Clears the editor fields and resets state."""
        self._is_loading_editor = True
        try:
            self.editor_preset_name.clear()
            self.editor_supplier_name.clear()
            self.editor_notes.clear()
            self.editor_separator.clear()
            self.editor_spin_base_name_idx.setValue(0)
            self.editor_spin_map_type_idx.setValue(1)
            self.editor_list_gloss_keywords.clear()
            self.editor_table_bit_depth_variants.setRowCount(0)
            self.editor_list_extra_patterns.clear()
            self.editor_table_map_type_mapping.setRowCount(0)
            self.editor_list_model_patterns.clear()
            self.editor_list_decal_keywords.clear()
            self.editor_table_archetype_rules.setRowCount(0)
            self.current_editing_preset_path = None
            self.editor_unsaved_changes = False
            self.editor_save_button.setEnabled(False)
            self._set_editor_enabled(False)
        finally:
            self._is_loading_editor = False

    def _populate_editor_from_data(self, preset_data: dict):
        """Helper method to populate editor UI widgets from a preset data dictionary."""
        self._is_loading_editor = True
        try:
            self.editor_preset_name.setText(preset_data.get("preset_name", ""))
            self.editor_supplier_name.setText(preset_data.get("supplier_name", ""))
            self.editor_notes.setText(preset_data.get("notes", ""))
            naming_data = preset_data.get("source_naming", {})
            self.editor_separator.setText(naming_data.get("separator", "_"))
            indices = naming_data.get("part_indices", {})
            self.editor_spin_base_name_idx.setValue(indices.get("base_name", 0))
            self.editor_spin_map_type_idx.setValue(indices.get("map_type", 1))
            self.editor_list_gloss_keywords.clear()
            self.editor_list_gloss_keywords.addItems(naming_data.get("glossiness_keywords", []))
            self.editor_table_bit_depth_variants.setRowCount(0)
            bit_depth_vars = naming_data.get("bit_depth_variants", {})
            for i, (map_type, pattern) in enumerate(bit_depth_vars.items()):
                self.editor_table_bit_depth_variants.insertRow(i)
                self.editor_table_bit_depth_variants.setItem(i, 0, QTableWidgetItem(map_type))
                self.editor_table_bit_depth_variants.setItem(i, 1, QTableWidgetItem(pattern))
            self.editor_list_extra_patterns.clear()
            self.editor_list_extra_patterns.addItems(preset_data.get("move_to_extra_patterns", []))

            self.editor_table_map_type_mapping.setRowCount(0) # Clear before populating
            map_mappings = preset_data.get("map_type_mapping", [])
            for i, mapping_dict in enumerate(map_mappings):
                if isinstance(mapping_dict, dict) and "target_type" in mapping_dict and "keywords" in mapping_dict:
                    std_type = mapping_dict["target_type"]
                    keywords = mapping_dict["keywords"]
                    self.editor_table_map_type_mapping.insertRow(i)

                    # Column 0: Standard Type (QComboBox)
                    combo_box = QComboBox()
                    if self._ftd_keys:
                        combo_box.addItems(self._ftd_keys)
                        if std_type in self._ftd_keys:
                            combo_box.setCurrentText(std_type)
                        else:
                            log.warning(f"Preset '{preset_data.get('preset_name', 'Unknown')}': target_type '{std_type}' not found in FILE_TYPE_DEFINITIONS. Selecting first available.")
                            if self._ftd_keys: combo_box.setCurrentIndex(0)
                    else:
                        log.warning("FILE_TYPE_DEFINITIONS keys not available for ComboBox in map_type_mapping during population.")
                    
                    combo_box.currentIndexChanged.connect(self._mark_editor_unsaved)
                    self.editor_table_map_type_mapping.setCellWidget(i, 0, combo_box)

                    # Column 1: Input Keywords (QTableWidgetItem)
                    keywords_str = [str(k) for k in keywords if isinstance(k, str)]
                    self.editor_table_map_type_mapping.setItem(i, 1, QTableWidgetItem(", ".join(keywords_str)))
                else:
                    log.warning(f"Skipping invalid map_type_mapping item during editor population: {mapping_dict}")
            
            category_rules = preset_data.get("asset_category_rules", {})
            self.editor_list_model_patterns.clear()
            self.editor_list_model_patterns.addItems(category_rules.get("model_patterns", []))
            self.editor_list_decal_keywords.clear()
            self.editor_list_decal_keywords.addItems(category_rules.get("decal_keywords", []))
            # Archetype rules population (assuming table exists)
            self.editor_table_archetype_rules.setRowCount(0)
            arch_rules_data = preset_data.get("archetype_rules", [])
            for i, rule_entry in enumerate(arch_rules_data):
                 # Handle both list and dict format for backward compatibility? Assuming list for now.
                 if isinstance(rule_entry, (list, tuple)) and len(rule_entry) == 2:
                     name, conditions = rule_entry
                     if isinstance(conditions, dict):
                         match_any = conditions.get("match_any", [])
                         match_all = conditions.get("match_all", [])
                         self.editor_table_archetype_rules.insertRow(i)
                         self.editor_table_archetype_rules.setItem(i, 0, QTableWidgetItem(str(name)))
                         self.editor_table_archetype_rules.setItem(i, 1, QTableWidgetItem(", ".join(map(str, match_any))))
                         self.editor_table_archetype_rules.setItem(i, 2, QTableWidgetItem(", ".join(map(str, match_all))))
                     else:
                         log.warning(f"Skipping invalid archetype rule condition format: {conditions}")
                 else:
                     log.warning(f"Skipping invalid archetype rule format: {rule_entry}")

        finally:
            self._is_loading_editor = False

    def _load_preset_for_editing(self, file_path: Path):
        """Loads the content of the selected preset file into the editor widgets."""
        if not file_path or not file_path.is_file():
            self._clear_editor()
            return
        log.info(f"Loading preset into editor: {file_path.name}")
        try:
            with open(file_path, 'r', encoding='utf-8') as f: preset_data = json.load(f)
            self._populate_editor_from_data(preset_data)
            self._set_editor_enabled(True)
            self.current_editing_preset_path = file_path
            self.editor_unsaved_changes = False
            self.editor_save_button.setEnabled(False)
            log.info(f"Preset '{file_path.name}' loaded into editor.")
        except json.JSONDecodeError as json_err:
             log.error(f"Invalid JSON in {file_path.name}: {json_err}")
             QMessageBox.warning(self, "Load Error", f"Failed to load preset '{file_path.name}'.\nInvalid JSON structure:\n{json_err}")
             self._clear_editor()
        except Exception as e:
            log.exception(f"Error loading preset file {file_path}: {e}")
            QMessageBox.critical(self, "Error", f"Could not load preset file:\n{file_path}\n\nError: {e}")
            self._clear_editor()

    @Slot(QListWidgetItem, QListWidgetItem)
    def _load_selected_preset_for_editing(self, current_item: QListWidgetItem, previous_item: QListWidgetItem):
        """Loads the preset currently selected in the editor list and emits selection change signal."""
        log.debug(f"PresetEditor: currentItemChanged signal triggered. current: {current_item.text() if current_item else 'None'}")

        mode = "placeholder"
        display_name_to_emit = None # Changed from preset_name
        file_path_to_emit = None    # New variable for Path

        # Check for unsaved changes before proceeding
        if self.check_unsaved_changes():
            # If user cancels, revert selection
            if previous_item:
                log.debug("Unsaved changes check cancelled. Reverting selection.")
                self.editor_preset_list.blockSignals(True)
                self.editor_preset_list.setCurrentItem(previous_item)
                self.editor_preset_list.blockSignals(False)
            return # Stop processing

        # Determine mode and preset name based on selection
        if current_item:
            item_data = current_item.data(Qt.ItemDataRole.UserRole)
            current_display_text = current_item.text() # This is the internal name from populate_presets

            if item_data == "__PLACEHOLDER__":
                log.debug("Placeholder item selected.")
                self._clear_editor()
                self._set_editor_enabled(False)
                mode = "placeholder"
                display_name_to_emit = None
                file_path_to_emit = None
                self._last_valid_preset_name = None # Clear last valid name
            elif item_data == "__LLM__":
                log.debug("LLM Interpretation item selected.")
                self._clear_editor()
                self._set_editor_enabled(False)
                mode = "llm"
                display_name_to_emit = None # LLM mode has no specific preset display name
                file_path_to_emit = None
                # Keep _last_valid_preset_name as it was (it should be the display name)
            elif isinstance(item_data, Path): # item_data is the Path object for a preset
                log.debug(f"Loading preset for editing: {current_display_text}")
                preset_file_path_obj = item_data
                self._load_preset_for_editing(preset_file_path_obj)
                # _last_valid_preset_name should store the display name for delegate use
                self._last_valid_preset_name = current_display_text
                mode = "preset"
                display_name_to_emit = current_display_text
                file_path_to_emit = preset_file_path_obj
            else: # Should not happen if list is populated correctly
                log.error(f"Invalid data type for preset path: {type(item_data)}. Clearing editor.")
                self._clear_editor()
                self._set_editor_enabled(False)
                mode = "placeholder"
                display_name_to_emit = None
                file_path_to_emit = None
                self._last_valid_preset_name = None
        else: # No current_item (e.g., list cleared)
             log.debug("No preset selected. Clearing editor.")
             self._clear_editor()
             self._set_editor_enabled(False)
             mode = "placeholder"
             display_name_to_emit = None
             file_path_to_emit = None
             self._last_valid_preset_name = None

        # Emit the signal with all three arguments
        log.debug(f"Emitting preset_selection_changed_signal: mode='{mode}', display_name='{display_name_to_emit}', file_path='{file_path_to_emit}'")
        self.preset_selection_changed_signal.emit(mode, display_name_to_emit, file_path_to_emit)

    def _gather_editor_data(self) -> dict:
        """Gathers data from all editor UI widgets and returns a dictionary."""
        preset_data = {}
        preset_data["preset_name"] = self.editor_preset_name.text().strip()
        preset_data["supplier_name"] = self.editor_supplier_name.text().strip()
        preset_data["notes"] = self.editor_notes.toPlainText().strip()
        naming_data = {}
        naming_data["separator"] = self.editor_separator.text()
        naming_data["part_indices"] = { "base_name": self.editor_spin_base_name_idx.value(), "map_type": self.editor_spin_map_type_idx.value() }
        naming_data["glossiness_keywords"] = [self.editor_list_gloss_keywords.item(i).text() for i in range(self.editor_list_gloss_keywords.count())]
        naming_data["bit_depth_variants"] = {self.editor_table_bit_depth_variants.item(r, 0).text(): self.editor_table_bit_depth_variants.item(r, 1).text()
                                             for r in range(self.editor_table_bit_depth_variants.rowCount()) if self.editor_table_bit_depth_variants.item(r, 0) and self.editor_table_bit_depth_variants.item(r, 1)}
        preset_data["source_naming"] = naming_data
        preset_data["move_to_extra_patterns"] = [self.editor_list_extra_patterns.item(i).text() for i in range(self.editor_list_extra_patterns.count())]
        
        map_mappings = []
        for r in range(self.editor_table_map_type_mapping.rowCount()):
            target_type_widget = self.editor_table_map_type_mapping.cellWidget(r, 0)
            keywords_item = self.editor_table_map_type_mapping.item(r, 1)
            
            target_type = ""
            if isinstance(target_type_widget, QComboBox):
                target_type = target_type_widget.currentText()
            elif self.editor_table_map_type_mapping.item(r, 0): # Fallback if item is not a widget
                target_type_item = self.editor_table_map_type_mapping.item(r, 0)
                if target_type_item:
                    target_type = target_type_item.text().strip()

            if target_type and keywords_item and keywords_item.text():
                 keywords = [k.strip() for k in keywords_item.text().split(',') if k.strip()]
                 if keywords: # Ensure keywords list is not empty after stripping
                      map_mappings.append({"target_type": target_type, "keywords": keywords})
                 else:
                      log.warning(f"Skipping row {r} in map type mapping table due to empty keywords after processing for target_type '{target_type}'.")
            else:
                 # Log if target_type is empty or keywords_item is problematic
                 if not target_type:
                     log.warning(f"Skipping row {r} in map type mapping table due to empty target_type.")
                 if not (keywords_item and keywords_item.text()):
                     log.warning(f"Skipping row {r} in map type mapping table for target_type '{target_type}' due to missing or empty keywords item.")
        preset_data["map_type_mapping"] = map_mappings
        
        category_rules = {}
        category_rules["model_patterns"] = [self.editor_list_model_patterns.item(i).text() for i in range(self.editor_list_model_patterns.count())]
        category_rules["decal_keywords"] = [self.editor_list_decal_keywords.item(i).text() for i in range(self.editor_list_decal_keywords.count())]
        preset_data["asset_category_rules"] = category_rules
        arch_rules = []
        for r in range(self.editor_table_archetype_rules.rowCount()):
            name_item = self.editor_table_archetype_rules.item(r, 0)
            any_item = self.editor_table_archetype_rules.item(r, 1)
            all_item = self.editor_table_archetype_rules.item(r, 2)
            if name_item and name_item.text() and any_item and all_item: # Check name has text
                 match_any = [k.strip() for k in any_item.text().split(',') if k.strip()]
                 match_all = [k.strip() for k in all_item.text().split(',') if k.strip()]
                 # Only add if name is present and at least one condition list is non-empty? Or allow empty conditions?
                 # Let's allow empty conditions for now.
                 arch_rules.append([name_item.text().strip(), {"match_any": match_any, "match_all": match_all}])
            else:
                 log.warning(f"Skipping row {r} in archetype rules table due to missing items or empty name.")
        preset_data["archetype_rules"] = arch_rules
        return preset_data

    def _save_current_preset(self) -> bool:
        """Saves the current editor content to the currently loaded file path."""
        if not self.current_editing_preset_path: return self._save_preset_as()
        log.info(f"Saving preset: {self.current_editing_preset_path.name}")
        try:
            preset_data = self._gather_editor_data()
            if not preset_data.get("preset_name"): QMessageBox.warning(self, "Save Error", "Preset Name cannot be empty."); return False
            if not preset_data.get("supplier_name"): QMessageBox.warning(self, "Save Error", "Supplier Name cannot be empty."); return False
            content_to_save = json.dumps(preset_data, indent=4, ensure_ascii=False)
            with open(self.current_editing_preset_path, 'w', encoding='utf-8') as f: f.write(content_to_save)
            self.editor_unsaved_changes = False
            self.editor_save_button.setEnabled(False)
            self.presets_changed_signal.emit()
            log.info("Preset saved successfully.")
            self.populate_presets()
            # Reselect the saved item
            items = self.editor_preset_list.findItems(self.current_editing_preset_path.stem, Qt.MatchFlag.MatchExactly)
            if items: self.editor_preset_list.setCurrentItem(items[0])
            return True
        except Exception as e:
            log.exception(f"Error saving preset file {self.current_editing_preset_path}: {e}")
            QMessageBox.critical(self, "Save Error", f"Could not save preset file:\n{self.current_editing_preset_path}\n\nError: {e}")
            return False

    def _save_preset_as(self) -> bool:
        """Saves the current editor content to a new file chosen by the user."""
        log.debug("Save As action triggered.")
        try:
            preset_data = self._gather_editor_data()
            new_preset_name = preset_data.get("preset_name")
            if not new_preset_name: QMessageBox.warning(self, "Save As Error", "Preset Name cannot be empty."); return False
            if not preset_data.get("supplier_name"): QMessageBox.warning(self, "Save As Error", "Supplier Name cannot be empty."); return False
            content_to_save = json.dumps(preset_data, indent=4, ensure_ascii=False)
            suggested_name = f"{new_preset_name}.json"
            default_path = PRESETS_DIR / suggested_name
            file_path_str, _ = QFileDialog.getSaveFileName(self, "Save Preset As", str(default_path), "JSON Files (*.json);;All Files (*)")
            if not file_path_str: log.debug("Save As cancelled by user."); return False
            save_path = Path(file_path_str)
            if save_path.suffix.lower() != ".json": save_path = save_path.with_suffix(".json")
            if save_path.exists() and save_path != self.current_editing_preset_path:
                 reply = QMessageBox.warning(self, "Confirm Overwrite", f"Preset '{save_path.name}' already exists. Overwrite?", QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, QMessageBox.StandardButton.No)
                 if reply == QMessageBox.StandardButton.No: log.debug("Save As overwrite cancelled."); return False
            log.info(f"Saving preset as: {save_path.name}")
            with open(save_path, 'w', encoding='utf-8') as f: f.write(content_to_save)
            self.current_editing_preset_path = save_path
            self.editor_unsaved_changes = False
            self.editor_save_button.setEnabled(False)
            self.presets_changed_signal.emit()
            log.info("Preset saved successfully (Save As).")
            # Refresh list and select the new item
            self.populate_presets()
            items = self.editor_preset_list.findItems(save_path.stem, Qt.MatchFlag.MatchExactly)
            if items: self.editor_preset_list.setCurrentItem(items[0])
            return True
        except Exception as e:
            log.exception(f"Error saving preset file (Save As): {e}")
            QMessageBox.critical(self, "Save Error", f"Could not save preset file.\n\nError: {e}")
            return False

    def _new_preset(self):
        """Clears the editor and loads data from _template.json."""
        log.debug("New Preset action triggered.")
        if self.check_unsaved_changes(): return # Check unsaved changes first
        self._clear_editor()
        if TEMPLATE_PATH.is_file():
            log.info("Loading new preset from _template.json")
            try:
                with open(TEMPLATE_PATH, 'r', encoding='utf-8') as f: template_data = json.load(f)
                self._populate_editor_from_data(template_data)
                # Override specific fields for a new preset
                self.editor_preset_name.setText("NewPreset")
            except Exception as e:
                log.exception(f"Error loading template preset file {TEMPLATE_PATH}: {e}")
                QMessageBox.critical(self, "Error", f"Could not load template preset file:\n{TEMPLATE_PATH}\n\nError: {e}")
                self._clear_editor()
            self.editor_supplier_name.setText("MySupplier")
        else:
            log.warning("Presets/_template.json not found. Creating empty preset.")
            self.editor_preset_name.setText("NewPreset")
            self.editor_supplier_name.setText("MySupplier")
        self._set_editor_enabled(True)
        self.editor_unsaved_changes = True
        self.editor_save_button.setEnabled(True)
        # Select the placeholder item to avoid auto-loading the "NewPreset"
        placeholder_item = self.editor_preset_list.findItems("--- Select a Preset ---", Qt.MatchFlag.MatchExactly)
        if placeholder_item:
            self.editor_preset_list.setCurrentItem(placeholder_item[0])
        # Emit selection change for the new state (effectively placeholder)
        self.preset_selection_changed_signal.emit("placeholder", None)


    def _delete_selected_preset(self):
        """Deletes the currently selected preset file from the editor list after confirmation."""
        current_item = self.editor_preset_list.currentItem()
        if not current_item: QMessageBox.information(self, "Delete Preset", "Please select a preset from the list to delete."); return

        item_data = current_item.data(Qt.ItemDataRole.UserRole)
        # Ensure it's a real preset path before attempting delete
        if not isinstance(item_data, Path):
            QMessageBox.information(self, "Delete Preset", "Cannot delete placeholder or LLM option.")
            return

        preset_path = item_data
        preset_name = preset_path.stem
        reply = QMessageBox.warning(self, "Confirm Delete", f"Are you sure you want to permanently delete the preset '{preset_name}'?", QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, QMessageBox.StandardButton.No)
        if reply == QMessageBox.StandardButton.Yes:
            log.info(f"Deleting preset: {preset_path.name}")
            try:
                preset_path.unlink()
                log.info("Preset deleted successfully.")
                if self.current_editing_preset_path == preset_path: self._clear_editor()
                self.presets_changed_signal.emit()
                self.populate_presets()
            except Exception as e:
                log.exception(f"Error deleting preset file {preset_path}: {e}")
                QMessageBox.critical(self, "Delete Error", f"Could not delete preset file:\n{preset_path}\n\nError: {e}")

    # --- Public Access Methods for MainWindow ---

    def get_selected_preset_mode(self) -> tuple[str, str | None, Path | None]:
        """
        Returns the current selection mode, display name, and file path for loading.
        Returns: tuple(mode_string, display_name_string_or_None, file_path_or_None)
                 mode_string can be "preset", "llm", "placeholder"
        """
        current_item = self.editor_preset_list.currentItem()
        if current_item:
            item_data = current_item.data(Qt.ItemDataRole.UserRole)
            display_text = current_item.text() # This is now the internal name

            if item_data == "__PLACEHOLDER__":
                return "placeholder", None, None
            elif item_data == "__LLM__":
                return "llm", None, None # LLM mode doesn't have a specific preset file path
            elif isinstance(item_data, Path):
                # For a preset, display_text is the internal name, item_data is the Path
                return "preset", display_text, item_data # Return internal name and path
        return "placeholder", None, None # Default or if no item selected

    def get_last_valid_preset_name(self) -> str | None:
        """
        Returns the name (stem) of the last valid preset that was loaded.
        Used by delegates to populate dropdowns based on the original context.
        """
        return self._last_valid_preset_name

    # --- Slots for MainWindow Interaction ---
