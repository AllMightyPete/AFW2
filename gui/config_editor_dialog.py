
import json
import os # Added for path operations
import copy # Added for deepcopy
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QTabWidget, QWidget,
    QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox, QCheckBox,
    QPushButton, QFileDialog, QLabel, QTableWidget,
    QTableWidgetItem, QDialogButtonBox, QMessageBox, QListWidget,
    QListWidgetItem, QFormLayout, QGroupBox, QStackedWidget, QInputDialog,
    QHeaderView, QSizePolicy
)
from PySide6.QtGui import QColor, QPainter
from PySide6.QtCore import Qt, QEvent
from PySide6.QtWidgets import QColorDialog, QStyledItemDelegate, QApplication

# Assuming configuration.py is in the parent directory or accessible
try:
    from configuration import load_base_config, save_user_config, ConfigurationError
except ImportError:
    # Fallback import for testing or different project structure
    from ..configuration import load_base_config, save_user_config, ConfigurationError, Configuration


# --- Custom Delegate for Color Editing ---
class ColorDelegate(QStyledItemDelegate):
    def paint(self, painter: QPainter, option, index):
        # Get color string from model data (EditRole is where we store it)
        color_str = index.model().data(index, Qt.EditRole)
        if isinstance(color_str, str) and color_str.startswith('#'):
            color = QColor(color_str)
            if color.isValid():
                painter.fillRect(option.rect, color)
                # Optionally draw text (e.g., the hex code) centered
                # painter.drawText(option.rect, Qt.AlignCenter, color_str)
                return # Prevent default painting

        # Fallback to default painting if no valid color
        super().paint(painter, option, index)

    def createEditor(self, parent, option, index):
        # No editor needed, handled by editorEvent
        return None

    def editorEvent(self, event, model, option, index):
        if event.type() == QEvent.MouseButtonPress and event.button() == Qt.LeftButton:
            current_color_str = model.data(index, Qt.EditRole)
            initial_color = QColor(current_color_str) if isinstance(current_color_str, str) else Qt.white

            color = QColorDialog.getColor(initial_color, None, "Select Color")

            if color.isValid():
                new_color_str = color.name() # Get #RRGGBB format
                model.setData(index, new_color_str, Qt.EditRole)
                # Trigger update for the background role as well, although paint should handle it
                # model.setData(index, QColor(new_color_str), Qt.BackgroundRole)
                return True # Event handled
        return False # Event not handled

    def setModelData(self, editor, model, index):
        # Not strictly needed as setData is called in editorEvent
        pass

# --- Custom Delegate for ComboBox Editing in Tables ---
class ComboBoxDelegate(QStyledItemDelegate):
    def __init__(self, items=None, parent=None):
        super().__init__(parent)
        self.items = items if items is not None else []

    def createEditor(self, parent, option, index):
        editor = QComboBox(parent)
        editor.addItems(self.items)
        return editor

    def setEditorData(self, editor, index):
        value = index.model().data(index, Qt.EditRole)
        if value is not None:
            editor.setCurrentText(str(value))

    def setModelData(self, editor, model, index):
        value = editor.currentText()
        model.setData(index, value, Qt.EditRole)

    def updateEditorGeometry(self, editor, option, index):
        editor.setGeometry(option.rect)

# --- Custom Delegate for DoubleSpinBox Editing in Tables ---
class DoubleSpinBoxDelegate(QStyledItemDelegate):
    def __init__(self, min_val=0.0, max_val=1.0, decimals=2, step=0.01, parent=None):
        super().__init__(parent)
        self.min_val = min_val
        self.max_val = max_val
        self.decimals = decimals
        self.step = step

    def createEditor(self, parent, option, index):
        editor = QDoubleSpinBox(parent)
        editor.setMinimum(self.min_val)
        editor.setMaximum(self.max_val)
        editor.setDecimals(self.decimals)
        editor.setSingleStep(self.step)
        return editor

    def setEditorData(self, editor, index):
        value = index.model().data(index, Qt.EditRole)
        try:
            editor.setValue(float(value))
        except (TypeError, ValueError):
            editor.setValue(self.min_val) # Default if conversion fails

    def setModelData(self, editor, model, index):
        editor.interpretText() # Ensure the editor's value is up-to-date
        value = editor.value()
        model.setData(index, value, Qt.EditRole)

    def updateEditorGeometry(self, editor, option, index):
        editor.setGeometry(option.rect)


class SpinBoxDelegate(QStyledItemDelegate):
    def __init__(self, min_val=1, max_val=32768, step=1, parent=None):
        super().__init__(parent)
        self.min_val = min_val
        self.max_val = max_val
        self.step = step

    def createEditor(self, parent, option, index):
        editor = QSpinBox(parent)
        editor.setMinimum(self.min_val)
        editor.setMaximum(self.max_val)
        editor.setSingleStep(self.step)
        return editor

    def setEditorData(self, editor, index):
        value = index.model().data(index, Qt.EditRole)
        try:
            editor.setValue(int(value))
        except (TypeError, ValueError):
            editor.setValue(self.min_val) # Default if conversion fails

    def setModelData(self, editor, model, index):
        editor.interpretText() # Ensure the editor's value is up-to-date
        value = editor.value()
        model.setData(index, value, Qt.EditRole)

    def updateEditorGeometry(self, editor, option, index):
        editor.setGeometry(option.rect)

class ConfigEditorDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Configuration Editor")
        self.setGeometry(100, 100, 800, 600)

        self.settings = {}
        self.widgets = {} # Dictionary to hold references to created widgets

        self.main_layout = QVBoxLayout(self)
        self.tab_widget = QTabWidget()
        self.main_layout.addWidget(self.tab_widget)

        self.button_box = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        self.button_box.accepted.connect(self.save_settings)
        self.button_box.rejected.connect(self.reject)
        self.main_layout.addWidget(self.button_box)

        self.load_settings() # Load settings FIRST
        self.create_tabs() # THEN create widgets based on settings
        self.populate_widgets_from_settings() # Populate widgets after creation

    def load_settings(self):
        """Loads settings from the configuration file."""
        try:
            self.settings = load_base_config()
            # Store a deep copy of the initial user-configurable settings for granular save.
            # These are settings from the effective configuration (base + user + defs)
            # that this dialog manages and are intended for user_settings.json.
            # Exclude definitions that are stored in separate files or not directly managed here.
            self.original_user_configurable_settings = {} # Initialize first
            if self.settings: # Ensure settings were loaded
                keys_to_copy = [
                    k for k in self.settings
                    if k not in ["ASSET_TYPE_DEFINITIONS", "FILE_TYPE_DEFINITIONS"]
                ]
                # Create a temporary dictionary with only the keys to be copied
                temp_original_settings = {
                    k: self.settings[k] for k in keys_to_copy if k in self.settings
                }
                self.original_user_configurable_settings = copy.deepcopy(temp_original_settings)
                print("Original user-configurable settings (relevant parts) deep copied for comparison.") # Debug print
            else:
                # If self.settings is None or empty, original_user_configurable_settings remains an empty dict.
                print("Settings not loaded or empty; original_user_configurable_settings initialized as empty.") # Debug print
        except Exception as e:
            QMessageBox.critical(self, "Loading Error", f"Failed to load configuration: {e}")
            self.settings = {} # Use empty settings on failure
            self.original_user_configurable_settings = {}
            # Optionally disable save button or widgets if loading fails
            self.button_box.button(QDialogButtonBox.Save).setEnabled(False)

    def create_tabs(self):
        """Creates tabs based on the redesigned UI plan."""
        if not self.settings:
            return

        # --- Create Tabs ---
        self.tabs = {
            "general": QWidget(),
            "output_naming": QWidget(),
            "image_processing": QWidget(),
            "definitions": QWidget(),
            "map_merging": QWidget(),
            "postprocess_scripts": QWidget()
        }
        self.tab_widget.addTab(self.tabs["general"], "General")
        self.tab_widget.addTab(self.tabs["output_naming"], "Output & Naming")
        self.tab_widget.addTab(self.tabs["image_processing"], "Image Processing")
        self.tab_widget.addTab(self.tabs["definitions"], "Definitions")
        self.tab_widget.addTab(self.tabs["map_merging"], "Map Merging")
        self.tab_widget.addTab(self.tabs["postprocess_scripts"], "Postprocess Scripts")


        # --- Setup Layouts for Tabs ---
        self.tab_layouts = {name: QVBoxLayout(tab) for name, tab in self.tabs.items()}

        # --- Populate Tabs ---
        self.populate_general_tab(self.tab_layouts["general"])
        self.populate_output_naming_tab(self.tab_layouts["output_naming"])
        self.populate_image_processing_tab(self.tab_layouts["image_processing"])
        self.populate_definitions_tab(self.tab_layouts["definitions"])
        self.populate_map_merging_tab(self.tab_layouts["map_merging"])
        self.populate_postprocess_scripts_tab(self.tab_layouts["postprocess_scripts"])

    def create_widget_for_setting(self, parent_layout, key, value, setting_key_prefix=""):
        """Creates an appropriate widget for a single setting key-value pair."""
        full_key = f"{setting_key_prefix}{key}" if setting_key_prefix else key
        label_text = key.replace('_', ' ').title()
        label = QLabel(label_text + ":")
        widget = None
        layout_to_add = None # Use this for widgets needing extra controls (like browse button)

        if isinstance(value, str):
            widget = QLineEdit(value)
        elif isinstance(value, int):
            widget = QSpinBox()
            widget.setRange(-2147483648, 2147483647)
            widget.setValue(value)
        elif isinstance(value, float):
            widget = QDoubleSpinBox()
            widget.setRange(-1.7976931348623157e+308, 1.7976931348623157e+308)
            widget.setValue(value)
        elif isinstance(value, bool):
            widget = QCheckBox()
            widget.setChecked(value)
        elif isinstance(value, list): # Handle simple lists as comma-separated strings
             widget = QLineEdit(", ".join(map(str, value)))
        # Complex dicts/lists like ASSET_TYPE_DEFINITIONS, MAP_MERGE_RULES etc. are handled in dedicated methods

        if widget:
            parent_layout.addRow(label, widget)
            self.widgets[full_key] = widget
        else:
            # Optionally handle unsupported types or log a warning
            # print(f"Skipping widget creation for key '{full_key}' with unsupported type: {type(value)}")
            pass

    def populate_general_tab(self, layout):
        """Populates the General tab according to the plan."""
        # Clear existing widgets in the layout first
        while layout.count():
            item = layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()
            sub_layout = item.layout()
            if sub_layout:
                 # Basic clearing for sub-layouts like QHBoxLayout used below
                 while sub_layout.count():
                     sub_item = sub_layout.takeAt(0)
                     sub_widget = sub_item.widget()
                     if sub_widget:
                         sub_widget.deleteLater()

        # Clear any potentially lingering widget references for this tab
        self.widgets.pop("OUTPUT_BASE_DIR", None)
        self.widgets.pop("EXTRA_FILES_SUBDIR", None)
        self.widgets.pop("METADATA_FILENAME", None)
        self.widgets.pop("TEMP_DIR_PREFIX", None)

        form_layout = QFormLayout()

        # 1. OUTPUT_BASE_DIR: QLineEdit + QPushButton
        output_dir_label = QLabel("Output Base Directory:")
        output_dir_edit = QLineEdit()
        output_dir_button = QPushButton("Browse...")
        # Ensure lambda captures the correct widget reference
        output_dir_button.clicked.connect(
            lambda checked=False, w=output_dir_edit: self.browse_path(w, "OUTPUT_BASE_DIR", is_dir=True)
        )
        output_dir_layout = QHBoxLayout()
        output_dir_layout.addWidget(output_dir_edit)
        output_dir_layout.addWidget(output_dir_button)
        form_layout.addRow(output_dir_label, output_dir_layout)
        self.widgets["OUTPUT_BASE_DIR"] = output_dir_edit

        # 2. EXTRA_FILES_SUBDIR: QLineEdit
        extra_subdir_label = QLabel("Subdirectory for Extra Files:")
        extra_subdir_edit = QLineEdit()
        form_layout.addRow(extra_subdir_label, extra_subdir_edit)
        self.widgets["EXTRA_FILES_SUBDIR"] = extra_subdir_edit

        # 3. METADATA_FILENAME: QLineEdit
        metadata_label = QLabel("Metadata Filename:")
        metadata_edit = QLineEdit()
        form_layout.addRow(metadata_label, metadata_edit)
        self.widgets["METADATA_FILENAME"] = metadata_edit

        # 4. TEMP_DIR_PREFIX: QLineEdit
        temp_dir_label = QLabel("Temporary Directory Prefix:")
        temp_dir_edit = QLineEdit()
        temp_dir_edit.setToolTip("Prefix for temporary directories created during processing.")
        form_layout.addRow(temp_dir_label, temp_dir_edit)
        self.widgets["TEMP_DIR_PREFIX"] = temp_dir_edit

        layout.addLayout(form_layout)
        layout.addStretch() # Keep stretch at the end

    def populate_output_naming_tab(self, layout):
        """Populates the Output & Naming tab according to the plan."""
        # Clear existing widgets in the layout first
        while layout.count():
            item = layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()
            sub_layout = item.layout()
            if sub_layout:
                 # Basic clearing for sub-layouts
                 while sub_layout.count():
                     sub_item = sub_layout.takeAt(0)
                     sub_widget = sub_item.widget()
                     if sub_widget:
                         sub_widget.deleteLater()
                     sub_sub_layout = sub_item.layout()
                     if sub_sub_layout: # Clear nested layouts (like the button HBox)
                         while sub_sub_layout.count():
                             ss_item = sub_sub_layout.takeAt(0)
                             ss_widget = ss_item.widget()
                             if ss_widget:
                                 ss_widget.deleteLater()


        # Clear potentially lingering widget references for this tab
        self.widgets.pop("TARGET_FILENAME_PATTERN", None)
        # self.widgets.pop("RESPECT_VARIANT_MAP_TYPES_LISTWIDGET", None) # This was an intermediate key, ensure it's gone
        self.widgets.pop("RESPECT_VARIANT_MAP_TYPES", None) # This is the correct key for the QListWidget
        self.widgets.pop("ASPECT_RATIO_DECIMALS", None)
        self.widgets.pop("OUTPUT_DIRECTORY_PATTERN", None)
        self.widgets.pop("OUTPUT_FILENAME_PATTERN", None)

        main_tab_layout = QVBoxLayout()

        form_layout = QFormLayout()

        # 1. TARGET_FILENAME_PATTERN: QLineEdit
        target_filename_label = QLabel("Output Filename Pattern:")
        target_filename_edit = QLineEdit()
        target_filename_edit.setToolTip(
            "Define the output filename structure.\n"
            "Placeholders: {asset_name}, {map_type}, {resolution}, {variant}, {udim}"
        )
        form_layout.addRow(target_filename_label, target_filename_edit)
        self.widgets["TARGET_FILENAME_PATTERN"] = target_filename_edit

        # 2. RESPECT_VARIANT_MAP_TYPES: QListWidget + Add/Remove Buttons
        respect_variant_label = QLabel("Map Types Respecting Variants:")
        
        self.respect_variant_list_widget = QListWidget()
        self.respect_variant_list_widget.setToolTip("List of map types that should respect variant naming.")
        self.widgets["RESPECT_VARIANT_MAP_TYPES"] = self.respect_variant_list_widget # Use the actual setting key

        respect_variant_buttons_layout = QHBoxLayout()
        add_respect_variant_button = QPushButton("Add")
        add_respect_variant_button.clicked.connect(self.add_respect_variant_map_type)
        remove_respect_variant_button = QPushButton("Remove")
        remove_respect_variant_button.clicked.connect(self.remove_respect_variant_map_type)
        respect_variant_buttons_layout.addWidget(add_respect_variant_button)
        respect_variant_buttons_layout.addWidget(remove_respect_variant_button)
        respect_variant_buttons_layout.addStretch()

        respect_variant_layout = QVBoxLayout()
        respect_variant_layout.addWidget(self.respect_variant_list_widget)
        respect_variant_layout.addLayout(respect_variant_buttons_layout)
        
        form_layout.addRow(respect_variant_label, respect_variant_layout)
        # self.widgets["RESPECT_VARIANT_MAP_TYPES"] will now refer to the list widget for population/saving logic

        # 3. ASPECT_RATIO_DECIMALS: QSpinBox
        aspect_ratio_label = QLabel("Aspect Ratio Precision (Decimals):")
        aspect_ratio_spinbox = QSpinBox()
        aspect_ratio_spinbox.setRange(0, 6) # Min: 0, Max: ~6
        form_layout.addRow(aspect_ratio_label, aspect_ratio_spinbox)
        self.widgets["ASPECT_RATIO_DECIMALS"] = aspect_ratio_spinbox

        # 4. OUTPUT_DIRECTORY_PATTERN: QLineEdit
        output_dir_pattern_label = QLabel("Output Directory Pattern:")
        output_dir_pattern_edit = QLineEdit()
        output_dir_pattern_edit.setToolTip(
            "Define the output subdirectory structure relative to Output Base Directory.\n"
            "Placeholders: {supplier}, {asset_name}, {asset_category}, etc."
        )
        form_layout.addRow(output_dir_pattern_label, output_dir_pattern_edit)
        self.widgets["OUTPUT_DIRECTORY_PATTERN"] = output_dir_pattern_edit
        
        # 5. OUTPUT_FILENAME_PATTERN: QLineEdit (Note: app_settings.json has TARGET_FILENAME_PATTERN and OUTPUT_FILENAME_PATTERN)
        # Assuming this is the one from app_settings.json line 9
        output_filename_pattern_label = QLabel("Output Filename Pattern (Legacy/Alternative):")
        output_filename_pattern_edit = QLineEdit()
        output_filename_pattern_edit.setToolTip(
             "Alternative output filename structure if different from Target Filename Pattern.\n"
             "Placeholders: {assetname}, {maptype}, {resolution}, {ext}, etc."
        )
        form_layout.addRow(output_filename_pattern_label, output_filename_pattern_edit)
        self.widgets["OUTPUT_FILENAME_PATTERN"] = output_filename_pattern_edit


        main_tab_layout.addLayout(form_layout)
 
        layout.addLayout(main_tab_layout)
        layout.addStretch() # Keep stretch at the end of the tab's main layout


    def populate_image_processing_tab(self, layout):
        """Populates the Image Processing tab according to the plan."""
        # Clear existing widgets in the layout first
        while layout.count():
            item = layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()
            sub_layout = item.layout()
            if sub_layout:
                 # Basic clearing for sub-layouts
                 while sub_layout.count():
                     sub_item = sub_layout.takeAt(0)
                     sub_widget = sub_item.widget()
                     if sub_widget:
                         sub_widget.deleteLater()
                     sub_sub_layout = sub_item.layout()
                     if sub_sub_layout: # Clear nested layouts (like button HBox)
                         while sub_sub_layout.count():
                             ss_item = sub_sub_layout.takeAt(0)
                             ss_widget = ss_item.widget()
                             if ss_widget:
                                 ss_widget.deleteLater()

        # Clear potentially lingering widget references for this tab
        keys_to_clear = [
            "IMAGE_RESOLUTIONS_TABLE", "CALCULATE_STATS_RESOLUTION",
            "PNG_COMPRESSION_LEVEL", "JPG_QUALITY",
            "RESOLUTION_THRESHOLD_FOR_JPG", "OUTPUT_FORMAT_8BIT",
            "OUTPUT_FORMAT_16BIT_PRIMARY", "OUTPUT_FORMAT_16BIT_FALLBACK",
            "general_settings.invert_normal_map_green_channel_globally",
            "INITIAL_SCALING_MODE"
        ]
        for key in keys_to_clear:
            self.widgets.pop(key, None)

        main_tab_layout = QVBoxLayout()

        # --- IMAGE_RESOLUTIONS Section ---
        resolutions_layout = QVBoxLayout()
        resolutions_label = QLabel("Defined Image Resolutions")
        resolutions_layout.addWidget(resolutions_label)

        resolutions_table = QTableWidget()
        resolutions_table.setColumnCount(2)
        resolutions_table.setHorizontalHeaderLabels(["Name", "Resolution (px)"])
        resolutions_table.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred) # Adjust size policy
        resolutions_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        resolutions_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Interactive) # Allow user resize, or ResizeToContents
        
        # Set SpinBox delegate for "Resolution (px)" column
        # Ensure self.resolution_delegate is initialized if not already
        if not hasattr(self, 'resolution_delegate'):
            self.resolution_delegate = SpinBoxDelegate(min_val=1, max_val=65536, parent=resolutions_table) # Max typical texture size
        resolutions_table.setItemDelegateForColumn(1, self.resolution_delegate)

        resolutions_layout.addWidget(resolutions_table)
        self.widgets["IMAGE_RESOLUTIONS_TABLE"] = resolutions_table

        resolutions_button_layout = QHBoxLayout()
        add_res_button = QPushButton("Add Row")
        remove_res_button = QPushButton("Remove Row")
        
        # Ensure methods exist before connecting
        if hasattr(self, 'add_image_resolution_row') and hasattr(self, 'remove_image_resolution_row'):
            add_res_button.clicked.connect(self.add_image_resolution_row)
            remove_res_button.clicked.connect(self.remove_image_resolution_row)
        else:
            print("Warning: add_image_resolution_row or remove_image_resolution_row not found during connect.")
            
        resolutions_button_layout.addWidget(add_res_button)
        resolutions_button_layout.addWidget(remove_res_button)
        resolutions_button_layout.addStretch() # Push buttons left
        resolutions_layout.addLayout(resolutions_button_layout)

        main_tab_layout.addLayout(resolutions_layout)

        # --- Form Layout for other settings ---
        form_layout = QFormLayout()

        # CALCULATE_STATS_RESOLUTION: QComboBox
        stats_res_label = QLabel("Resolution for Stats Calculation:")
        stats_res_combo = QComboBox()
        # Population deferred - will be populated from IMAGE_RESOLUTIONS_TABLE
        form_layout.addRow(stats_res_label, stats_res_combo)
        self.widgets["CALCULATE_STATS_RESOLUTION"] = stats_res_combo

        # PNG_COMPRESSION_LEVEL: QSpinBox
        png_level_label = QLabel("PNG Compression Level:")
        png_level_spinbox = QSpinBox()
        png_level_spinbox.setRange(0, 9)
        form_layout.addRow(png_level_label, png_level_spinbox)
        self.widgets["PNG_COMPRESSION_LEVEL"] = png_level_spinbox

        # JPG_QUALITY: QSpinBox
        jpg_quality_label = QLabel("JPG Quality:")
        jpg_quality_spinbox = QSpinBox()
        jpg_quality_spinbox.setRange(1, 100)
        form_layout.addRow(jpg_quality_label, jpg_quality_spinbox)
        self.widgets["JPG_QUALITY"] = jpg_quality_spinbox

        # RESOLUTION_THRESHOLD_FOR_JPG: QComboBox
        jpg_threshold_label = QLabel("Use JPG Above Resolution:")
        jpg_threshold_combo = QComboBox()
        # Population deferred - will be populated from IMAGE_RESOLUTIONS_TABLE + "Never"/"Always"
        form_layout.addRow(jpg_threshold_label, jpg_threshold_combo)
        self.widgets["RESOLUTION_THRESHOLD_FOR_JPG"] = jpg_threshold_combo

        # OUTPUT_FORMAT_8BIT: QComboBox
        format_8bit_label = QLabel("Output Format (8-bit):")
        format_8bit_combo = QComboBox()
        format_8bit_combo.addItems(["png", "jpg"])
        form_layout.addRow(format_8bit_label, format_8bit_combo)
        self.widgets["OUTPUT_FORMAT_8BIT"] = format_8bit_combo

        # OUTPUT_FORMAT_16BIT_PRIMARY: QComboBox
        format_16bit_primary_label = QLabel("Primary Output Format (16-bit+):")
        format_16bit_primary_combo = QComboBox()
        format_16bit_primary_combo.addItems(["png", "exr", "tif"])
        form_layout.addRow(format_16bit_primary_label, format_16bit_primary_combo)
        self.widgets["OUTPUT_FORMAT_16BIT_PRIMARY"] = format_16bit_primary_combo

        # OUTPUT_FORMAT_16BIT_FALLBACK: QComboBox
        format_16bit_fallback_label = QLabel("Fallback Output Format (16-bit+):")
        format_16bit_fallback_combo = QComboBox()
        format_16bit_fallback_combo.addItems(["png", "exr", "tif"])
        form_layout.addRow(format_16bit_fallback_label, format_16bit_fallback_combo)
        self.widgets["OUTPUT_FORMAT_16BIT_FALLBACK"] = format_16bit_fallback_combo

        main_tab_layout.addLayout(form_layout)
        
        # Add general_settings.invert_normal_map_green_channel_globally QCheckBox
        invert_normal_checkbox = QCheckBox("Invert Normal Map Green Channel Globally")
        invert_normal_checkbox.setToolTip("Applies green channel inversion for normal maps project-wide.")
        # Add to form_layout or main_tab_layout. Let's add to form_layout for consistency.
        form_layout.addRow(invert_normal_checkbox) # Label can be omitted if checkbox text is descriptive
        self.widgets["general_settings.invert_normal_map_green_channel_globally"] = invert_normal_checkbox

        # INITIAL_SCALING_MODE: QComboBox
        initial_scaling_label = QLabel("Initial Scaling Mode:")
        initial_scaling_combo = QComboBox()
        initial_scaling_combo.addItems(["POT_DOWNSCALE", "POT_UPSCALE", "NONE", "ASPECT_PRESERVING_DOWNSCALE"]) # Add likely options
        initial_scaling_combo.setToolTip("Determines how images are initially scaled if they are not power-of-two.")
        form_layout.addRow(initial_scaling_label, initial_scaling_combo)
        self.widgets["INITIAL_SCALING_MODE"] = initial_scaling_combo

        layout.addLayout(main_tab_layout)
        layout.addStretch() # Keep stretch at the end of the tab's main layout

    def populate_definitions_tab(self, layout):
        """Populates the Definitions tab according to the plan."""
        # Clear existing widgets in the layout first
        while layout.count():
            item = layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()
            sub_layout = item.layout()
            if sub_layout:
                 # Recursively clear sub-layouts
                 while sub_layout.count():
                     sub_item = sub_layout.takeAt(0)
                     sub_widget = sub_item.widget()
                     if sub_widget:
                         sub_widget.deleteLater()
                     sub_sub_layout = sub_item.layout()
                     if sub_sub_layout:
                         # Clear nested layouts (like button HBox or inner tabs)
                         while sub_sub_layout.count():
                             ss_item = sub_sub_layout.takeAt(0)
                             ss_widget = ss_item.widget()
                             if ss_widget:
                                 ss_widget.deleteLater()
                             # Add more levels if necessary, but this covers the planned structure

        # Clear potentially lingering widget references for this tab
        self.widgets.pop("DEFAULT_ASSET_CATEGORY", None)
        self.widgets.pop("ASSET_TYPE_DEFINITIONS_TABLE", None)
        self.widgets.pop("FILE_TYPE_DEFINITIONS_TABLE", None)
        # Remove references to widgets no longer used in this tab's structure
        self.widgets.pop("MAP_BIT_DEPTH_RULES_TABLE", None)


        overall_layout = QVBoxLayout()

        # --- Top Widget: DEFAULT_ASSET_CATEGORY ---
        default_category_layout = QHBoxLayout() # Use QHBox for label + combo
        default_category_label = QLabel("Default Asset Category:")
        default_category_combo = QComboBox()
        # Population is deferred, will happen in populate_widgets_from_settings
        default_category_layout.addWidget(default_category_label)
        default_category_layout.addWidget(default_category_combo)
        default_category_layout.addStretch() # Push label/combo left
        overall_layout.addLayout(default_category_layout)
        self.widgets["DEFAULT_ASSET_CATEGORY"] = default_category_combo

        # Inner QTabWidget and its contents (Asset Types and File Types tables) are removed
        # as per Phase 1, Item 1 of the refactoring plan.
        # The DEFAULT_ASSET_CATEGORY QComboBox remains above, part of overall_layout.

        layout.addLayout(overall_layout)
        layout.addStretch() # Keep stretch at the end of the tab's main layout


    def populate_map_merging_tab(self, layout):
        """Populates the Map Merging tab according to the plan."""
        # Clear existing widgets in the layout first
        while layout.count():
            item = layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()
            sub_layout = item.layout()
            if sub_layout:
                 # Basic clearing for sub-layouts
                 while sub_layout.count():
                     sub_item = sub_layout.takeAt(0)
                     sub_widget = sub_item.widget()
                     if sub_widget:
                         sub_widget.deleteLater()
                     # Clear nested layouts if needed (e.g., button layout)
                     sub_sub_layout = sub_item.layout()
                     if sub_sub_layout:
                         while sub_sub_layout.count():
                             ss_item = sub_sub_layout.takeAt(0)
                             ss_widget = ss_item.widget()
                             if ss_widget:
                                 ss_widget.deleteLater()

        # Clear potentially lingering widget references for this tab
        self.widgets.pop("MAP_MERGE_RULES_DATA", None)
        self.widgets.pop("MERGE_DIMENSION_MISMATCH_STRATEGY", None)
        # Clear references to the list and details group if they exist
        if hasattr(self, 'merge_rules_list'):
            del self.merge_rules_list
        if hasattr(self, 'merge_rule_details_group'):
            del self.merge_rule_details_group
        if hasattr(self, 'merge_rule_details_layout'):
             del self.merge_rule_details_layout
        if hasattr(self, 'merge_rule_widgets'):
             del self.merge_rule_widgets


        top_form_layout = QFormLayout()

        # MERGE_DIMENSION_MISMATCH_STRATEGY: QComboBox
        merge_strategy_label = QLabel("Merge Dimension Mismatch Strategy:")
        merge_strategy_combo = QComboBox()
        merge_strategy_combo.addItems(["USE_LARGEST", "USE_SMALLEST", "ERROR_OUT"]) # Add likely options
        merge_strategy_combo.setToolTip("How to handle merging maps of different dimensions.")
        top_form_layout.addRow(merge_strategy_label, merge_strategy_combo)
        self.widgets["MERGE_DIMENSION_MISMATCH_STRATEGY"] = merge_strategy_combo
        
        layout.addLayout(top_form_layout) # Add this form layout to the main tab layout

        # Layout: QHBoxLayout for rules list and details.
        h_layout = QHBoxLayout()
        layout.addLayout(h_layout)

        # Left Side: QListWidget displaying output_map_type for each rule.
        left_layout = QVBoxLayout()
        left_layout.addWidget(QLabel("Merge Rules:"))
        self.merge_rules_list = QListWidget()
        self.merge_rules_list.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Expanding) # Allow list to expand vertically
        self.merge_rules_list.currentItemChanged.connect(self.display_merge_rule_details)
        left_layout.addWidget(self.merge_rules_list)

        button_layout = QHBoxLayout()
        add_button = QPushButton("Add Rule")
        remove_button = QPushButton("Remove Rule")
        add_button.clicked.connect(self.add_merge_rule)
        remove_button.clicked.connect(self.remove_merge_rule)
        button_layout.addWidget(add_button)
        button_layout.addWidget(remove_button)
        left_layout.addLayout(button_layout)

        h_layout.addLayout(left_layout, 1) # Give list more space

        # Right Side: QStackedWidget or dynamically populated QWidget showing details
        self.merge_rule_details_group = QGroupBox("Rule Details")
        self.merge_rule_details_group.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred) # Allow groupbox to expand horizontally
        self.merge_rule_details_layout = QFormLayout(self.merge_rule_details_group)
        h_layout.addWidget(self.merge_rule_details_group, 2) # Give details form more space

        self.merge_rule_widgets = {} # Widgets for the currently displayed rule

        if "MAP_MERGE_RULES" in self.settings:
             # Make a deep copy for local modification if needed, or manage through QListWidgetItems directly
             self.current_map_merge_rules = copy.deepcopy(self.settings.get("MAP_MERGE_RULES", []))
             self.populate_merge_rules_list(self.current_map_merge_rules)
             # self.widgets["MAP_MERGE_RULES_DATA"] = self.current_map_merge_rules # This will be the list of dicts
        else:
             self.current_map_merge_rules = []
             self.populate_merge_rules_list([]) # Populate with empty list

        layout.addStretch()


    def populate_postprocess_scripts_tab(self, layout):
        """Populates the Postprocess Scripts tab according to the plan."""
        # Clear existing widgets in the layout first
        while layout.count():
            item = layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()
            sub_layout = item.layout()
            if sub_layout:
                 # Basic clearing for sub-layouts (like the QHBoxLayouts used below)
                 while sub_layout.count():
                     sub_item = sub_layout.takeAt(0)
                     sub_widget = sub_item.widget()
                     if sub_widget:
                         sub_widget.deleteLater()

        # Clear potentially lingering widget references for this tab
        self.widgets.pop("DEFAULT_NODEGROUP_BLEND_PATH", None)
        self.widgets.pop("DEFAULT_MATERIALS_BLEND_PATH", None)
        self.widgets.pop("BLENDER_EXECUTABLE_PATH", None)

        form_layout = QFormLayout()

        # 1. DEFAULT_NODEGROUP_BLEND_PATH: QLineEdit + QPushButton
        nodegroup_label = QLabel("Default Node Group Library (.blend):")
        nodegroup_widget = QLineEdit()
        nodegroup_button = QPushButton("Browse...")
        nodegroup_button.clicked.connect(
            lambda checked=False, w=nodegroup_widget: self.browse_path(w, "DEFAULT_NODEGROUP_BLEND_PATH")
        )
        nodegroup_layout = QHBoxLayout()
        nodegroup_layout.addWidget(nodegroup_widget)
        nodegroup_layout.addWidget(nodegroup_button)
        form_layout.addRow(nodegroup_label, nodegroup_layout)
        self.widgets["DEFAULT_NODEGROUP_BLEND_PATH"] = nodegroup_widget

        # 2. DEFAULT_MATERIALS_BLEND_PATH: QLineEdit + QPushButton
        materials_label = QLabel("Default Materials Library (.blend):")
        materials_widget = QLineEdit()
        materials_button = QPushButton("Browse...")
        materials_button.clicked.connect(
            lambda checked=False, w=materials_widget: self.browse_path(w, "DEFAULT_MATERIALS_BLEND_PATH")
        )
        materials_layout = QHBoxLayout()
        materials_layout.addWidget(materials_widget)
        materials_layout.addWidget(materials_button)
        form_layout.addRow(materials_label, materials_layout)
        self.widgets["DEFAULT_MATERIALS_BLEND_PATH"] = materials_widget

        # 3. BLENDER_EXECUTABLE_PATH: QLineEdit + QPushButton
        blender_label = QLabel("Blender Executable Path:")
        blender_widget = QLineEdit()
        blender_button = QPushButton("Browse...")
        blender_button.clicked.connect(
            lambda checked=False, w=blender_widget: self.browse_path(w, "BLENDER_EXECUTABLE_PATH")
        )
        blender_layout = QHBoxLayout()
        blender_layout.addWidget(blender_widget)
        blender_layout.addWidget(blender_button)
        form_layout.addRow(blender_label, blender_layout)
        self.widgets["BLENDER_EXECUTABLE_PATH"] = blender_widget

        layout.addLayout(form_layout)
        layout.addStretch()

    def create_asset_definitions_table_widget(self, layout, definitions_data):
        """Creates a QTableWidget for editing asset type definitions."""
        table = QTableWidget()
        # Columns: "Type Name", "Description", "Color", "Examples (comma-sep.)"
        table.setColumnCount(4)
        table.setHorizontalHeaderLabels(["Type Name", "Description", "Color", "Examples (comma-sep.)"])
        # Row count will be set when populating

        # TODO: Implement "Add Row" and "Remove Row" buttons
        # TODO: Implement custom delegate for "Color" column (QPushButton)
        # TODO: Implement custom delegate for "Examples" column (QLineEdit)

        layout.addWidget(table)
        self.widgets["ASSET_TYPE_DEFINITIONS_TABLE"] = table

    def create_file_type_definitions_table_widget(self, layout, definitions_data):
        """Creates a QTableWidget for editing file type definitions."""
        table = QTableWidget()
        # Columns: "Type ID", "Description", "Color", "Examples (comma-sep.)", "Standard Type", "Bit Depth Rule"
        table.setColumnCount(6)
        table.setHorizontalHeaderLabels(["Type ID", "Description", "Color", "Examples (comma-sep.)", "Standard Type", "Bit Depth Rule"])
        # Row count will be set when populating

        # TODO: Implement "Add Row" and "Remove Row" buttons
        # TODO: Implement custom delegate for "Color" column (QPushButton)
        # TODO: Implement custom delegate for "Examples" column (QLineEdit)
        # TODO: Implement custom delegate for "Standard Type" column (QComboBox)
        # TODO: Implement custom delegate for "Bit Depth Rule" column (QComboBox)

        layout.addWidget(table)
        self.widgets["FILE_TYPE_DEFINITIONS_TABLE"] = table

    def create_image_resolutions_table_widget(self, layout, resolutions_data):
        """Creates a QTableWidget for editing image resolutions."""
        table = QTableWidget()
        # Columns: "Name", "Resolution (px)"
        table.setColumnCount(2)
        table.setHorizontalHeaderLabels(["Name", "Resolution (px)"])
        # Row count will be set when populating

        # TODO: Implement "Add Row" and "Remove Row" buttons
        # TODO: Implement custom delegate for "Resolution (px)" column (e.g., QLineEdit with validation or two SpinBoxes)

        layout.addWidget(table)
        self.widgets["IMAGE_RESOLUTIONS_TABLE"] = table

    def create_map_bit_depth_rules_table_widget(self, layout, rules_data: dict):
        """Creates a QTableWidget for editing map bit depth rules (Map Type -> Rule)."""
        table = QTableWidget()
        # Columns: "Map Type", "Rule (respect/force_8bit)"
        table.setColumnCount(2)
        table.setHorizontalHeaderLabels(["Map Type", "Rule (respect/force_8bit)"])
        # Row count will be set when populating

        # TODO: Implement "Add Row" and "Remove Row" buttons
        # TODO: Implement custom delegate for "Rule" column (QComboBox)

        layout.addWidget(table)
        self.widgets["MAP_BIT_DEPTH_RULES_TABLE"] = table


    def create_map_merge_rules_widget(self, layout, rules_data):
        """Creates the Map Merging UI (ListWidget + Details Form) according to the plan."""
        # This method is called by populate_map_merging_tab and sets up the QHBoxLayout,
        # ListWidget, and details group box. The details population is handled by
        # display_merge_rule_details.
        pass # Structure is already set up in populate_map_merging_tab

    def populate_merge_rules_list(self, rules_data):
        """Populates the list widget with map merge rules."""
        self.merge_rules_list.clear()
        for rule in rules_data:
            # Use output_map_type for the display text
            item_text = rule.get("output_map_type", "Unnamed Rule")
            item = QListWidgetItem(item_text)
            item.setData(Qt.UserRole, rule) # Store the rule dictionary in the item
            self.merge_rules_list.addItem(item)

    def display_merge_rule_details(self, current, previous):
        """Displays details of the selected merge rule according to the plan."""
        # Clear previous widgets
        for i in reversed(range(self.merge_rule_details_layout.count())):
            widget_item = self.merge_rule_details_layout.itemAt(i)
            if widget_item:
                widget = widget_item.widget()
                if widget:
                    widget.deleteLater()
                layout = widget_item.layout()
                if layout:
                    # Recursively delete widgets in layout
                    while layout.count():
                        item = layout.takeAt(0)
                        widget = item.widget()
                        if widget:
                            widget.deleteLater()
                        elif item.layout():
                            # Handle nested layouts if necessary
                            pass # For simplicity, assuming no deeply nested layouts here

        self.merge_rule_widgets.clear()

        if current:
            rule_data = current.data(Qt.UserRole)
            if rule_data:
                # Rule Detail Form:
                # output_map_type: QLineEdit. Label: "Output Map Type Name".
                if "output_map_type" in rule_data:
                    label = QLabel("Output Map Type Name:")
                    combo_output_map_type = QComboBox()
                    file_type_keys = list(self.settings.get("FILE_TYPE_DEFINITIONS", {}).keys())
                    if not file_type_keys: # Fallback if no keys found
                        file_type_keys = ["NEW_RULE", rule_data["output_map_type"]] # Add current value as an option
                    
                    # Ensure current value is in list, add if not (e.g. for "NEW_RULE")
                    if rule_data["output_map_type"] not in file_type_keys:
                        file_type_keys.insert(0, rule_data["output_map_type"])
                        
                    combo_output_map_type.addItems(file_type_keys)
                    combo_output_map_type.setCurrentText(rule_data["output_map_type"])
                    combo_output_map_type.currentIndexChanged.connect(
                        lambda index, cb=combo_output_map_type: self.update_rule_output_map_type(cb.currentText())
                    )
                    self.merge_rule_details_layout.addRow(label, combo_output_map_type)
                    self.merge_rule_widgets["output_map_type"] = combo_output_map_type

                # inputs: QTableWidget (Fixed Rows: R, G, B, A. Columns: "Channel", "Input Map Type"). Label: "Channel Inputs".
                if "inputs" in rule_data and isinstance(rule_data["inputs"], dict):
                    group = QGroupBox("Channel Inputs")
                    group_layout = QVBoxLayout(group)
                    input_table = QTableWidget(4, 2) # R, G, B, A rows, 2 columns
                    input_table.setHorizontalHeaderLabels(["Channel", "Input Map Type"])
                    input_table.setVerticalHeaderLabels(["R", "G", "B", "A"])
                    
                    file_type_keys_with_none = [""] + list(self.settings.get("FILE_TYPE_DEFINITIONS", {}).keys())
                    inputs_delegate = ComboBoxDelegate(items=file_type_keys_with_none, parent=input_table)
                    input_table.setItemDelegateForColumn(1, inputs_delegate)

                    channels = ["R", "G", "B", "A"]
                    for i, channel_key in enumerate(channels):
                        input_map_type = rule_data["inputs"].get(channel_key, "")
                        channel_item = QTableWidgetItem(channel_key)
                        channel_item.setFlags(channel_item.flags() & ~Qt.ItemIsEditable) # Make channel name not editable
                        input_table.setItem(i, 0, channel_item)
                        
                        map_type_item = QTableWidgetItem(input_map_type)
                        input_table.setItem(i, 1, map_type_item)
                    
                    input_table.itemChanged.connect(lambda item, table=input_table, data_key="inputs": self.update_rule_data_from_table(item, table, data_key))
                    group_layout.addWidget(input_table)
                    self.merge_rule_details_layout.addRow(group)
                    self.merge_rule_widgets["inputs_table"] = input_table


                # defaults: QTableWidget (Fixed Rows: R, G, B, A. Columns: "Channel", "Default Value"). Label: "Channel Defaults (if input missing)".
                if "defaults" in rule_data and isinstance(rule_data["defaults"], dict):
                    group = QGroupBox("Channel Defaults (if input missing)")
                    group_layout = QVBoxLayout(group)
                    defaults_table = QTableWidget(4, 2) # R, G, B, A rows, 2 columns
                    defaults_table.setHorizontalHeaderLabels(["Channel", "Default Value"])
                    defaults_table.setVerticalHeaderLabels(["R", "G", "B", "A"])

                    defaults_delegate = DoubleSpinBoxDelegate(min_val=0.0, max_val=1.0, decimals=3, step=0.01, parent=defaults_table) # Example range
                    defaults_table.setItemDelegateForColumn(1, defaults_delegate)

                    channels = ["R", "G", "B", "A"]
                    for i, channel_key in enumerate(channels):
                        default_value = rule_data["defaults"].get(channel_key, 0.0 if channel_key != "A" else 1.0) # A defaults to 1.0
                        channel_item = QTableWidgetItem(channel_key)
                        channel_item.setFlags(channel_item.flags() & ~Qt.ItemIsEditable) # Make channel name not editable
                        defaults_table.setItem(i, 0, channel_item)
                        
                        value_item = QTableWidgetItem(str(default_value))
                        defaults_table.setItem(i, 1, value_item)

                    defaults_table.itemChanged.connect(lambda item, table=defaults_table, data_key="defaults": self.update_rule_data_from_table(item, table, data_key))
                    group_layout.addWidget(defaults_table)
                    self.merge_rule_details_layout.addRow(group)
                    self.merge_rule_widgets["defaults_table"] = defaults_table


                # output_bit_depth: QComboBox (Options: "respect_inputs", "force_8bit", "force_16bit"). Label: "Output Bit Depth".
                if "output_bit_depth" in rule_data:
                    label = QLabel("Output Bit Depth:")
                    widget = QComboBox()
                    options = ["respect_inputs", "force_8bit", "force_16bit"]
                    widget.addItems(options)
                    if rule_data["output_bit_depth"] in options:
                        widget.setCurrentText(rule_data["output_bit_depth"])
                    self.merge_rule_details_layout.addRow(label, widget)
                    self.merge_rule_widgets["output_bit_depth"] = widget

                # Add stretch to push widgets to the top
                self.merge_rule_details_layout.addStretch()


                # Connect output_bit_depth QComboBox to update rule data
                if "output_bit_depth" in self.merge_rule_widgets and isinstance(self.merge_rule_widgets["output_bit_depth"], QComboBox):
                    self.merge_rule_widgets["output_bit_depth"].currentTextChanged.connect(
                        lambda text, key="output_bit_depth": self.update_rule_data_simple_field(text, key)
                    )


    def update_rule_output_map_type(self, new_text):
        """Updates the output_map_type in the rule data and QListWidgetItem text."""
        current_list_item = self.merge_rules_list.currentItem()
        if current_list_item:
            rule_data = current_list_item.data(Qt.UserRole)
            if rule_data and isinstance(rule_data, dict):
                rule_data["output_map_type"] = new_text
                current_list_item.setData(Qt.UserRole, rule_data) # Update the stored data
                current_list_item.setText(new_text) # Update the display text in the list

    def update_rule_data_from_table(self, item: QTableWidgetItem, table_widget: QTableWidget, data_key: str):
        """Updates the rule data when a table item changes (for inputs or defaults)."""
        current_list_item = self.merge_rules_list.currentItem()
        if not current_list_item:
            return

        rule_data = current_list_item.data(Qt.UserRole)
        if not rule_data or not isinstance(rule_data, dict):
            return

        row = item.row()
        col = item.column()

        if col == 1: # Only update for the value column (Input Map Type or Default Value)
            channel_key_item = table_widget.verticalHeaderItem(row)
            if not channel_key_item: # Should have vertical headers R,G,B,A
                 channel_key_item = table_widget.item(row, 0) # Fallback if no vertical header
            
            if channel_key_item:
                channel_key = channel_key_item.text()
                new_value = item.text()

                if data_key == "inputs":
                    if "inputs" not in rule_data or not isinstance(rule_data["inputs"], dict):
                        rule_data["inputs"] = {}
                    rule_data["inputs"][channel_key] = new_value
                elif data_key == "defaults":
                    if "defaults" not in rule_data or not isinstance(rule_data["defaults"], dict):
                        rule_data["defaults"] = {}
                    try:
                        rule_data["defaults"][channel_key] = float(new_value)
                    except ValueError:
                        # Handle error or revert, for now, just print
                        print(f"Invalid float value for default: {new_value}")
                        # Optionally revert item text: item.setText(str(rule_data["defaults"].get(channel_key, 0.0)))
                        return
                
                current_list_item.setData(Qt.UserRole, rule_data) # Update the stored data
                # print(f"Updated rule data for {channel_key} in {data_key}: {new_value}") # Debug

    def update_rule_data_simple_field(self, new_value, field_key):
        """Updates a simple field in the rule data (e.g., output_bit_depth)."""
        current_list_item = self.merge_rules_list.currentItem()
        if current_list_item:
            rule_data = current_list_item.data(Qt.UserRole)
            if rule_data and isinstance(rule_data, dict):
                rule_data[field_key] = new_value
                current_list_item.setData(Qt.UserRole, rule_data) # Update the stored data
                # print(f"Updated rule field {field_key} to: {new_value}") # Debug


    def browse_path(self, widget, key, is_dir=False):
        """Opens a file or directory dialog based on the setting key and is_dir flag."""
        if is_dir:
            path = QFileDialog.getExistingDirectory(self, "Select Directory", widget.text())
        elif 'BLEND_PATH' in key.upper():
             path, _ = QFileDialog.getOpenFileName(self, "Select File", widget.text(), "Blender Files (*.blend)")
        else:
            path, _ = QFileDialog.getOpenFileName(self, "Select File", widget.text())

        if path:
            widget.setText(path)

    def add_respect_variant_map_type(self):
        """Adds a map type to the RESPECT_VARIANT_MAP_TYPES list."""
        # Ensure configuration and file_type_definitions are loaded
        if not hasattr(self, 'settings') or "FILE_TYPE_DEFINITIONS" not in self.settings:
            QMessageBox.warning(self, "Configuration Error", "File type definitions are not loaded.")
            return

        file_type_definitions = self.settings.get("FILE_TYPE_DEFINITIONS", {})
        map_type_keys = list(file_type_definitions.keys())
        if not map_type_keys:
            QMessageBox.warning(self, "No Map Types", "No map types available to add.")
            return

        item, ok = QInputDialog.getItem(self, "Add Map Type",
                                        "Select map type to add:", map_type_keys, 0, False)
        if ok and item:
            # Check if item already exists
            for i in range(self.respect_variant_list_widget.count()):
                if self.respect_variant_list_widget.item(i).text() == item:
                    QMessageBox.information(self, "Duplicate", f"Map type '{item}' is already in the list.")
                    return
            self.respect_variant_list_widget.addItem(item)

    def remove_respect_variant_map_type(self):
        """Removes the selected map type from the RESPECT_VARIANT_MAP_TYPES list."""
        selected_items = self.respect_variant_list_widget.selectedItems()
        if not selected_items:
            QMessageBox.warning(self, "No Selection", "Please select a map type to remove.")
            return
        for item in selected_items:
            self.respect_variant_list_widget.takeItem(self.respect_variant_list_widget.row(item))

    def add_merge_rule(self):
        """Adds a new default map merge rule."""
        new_rule = {
            "output_map_type": "NEW_RULE",
            "inputs": {"R": "", "G": "", "B": "", "A": ""},
            "defaults": {"R": 0.0, "G": 0.0, "B": 0.0, "A": 1.0},
            "output_bit_depth": "respect_inputs"
        }
        
        # Add to the internal list that backs the UI
        # self.current_map_merge_rules.append(new_rule) # This list is now managed by QListWidgetItems

        item_text = new_rule.get("output_map_type", "Unnamed Rule")
        item = QListWidgetItem(item_text)
        item.setData(Qt.UserRole, copy.deepcopy(new_rule)) # Store a mutable copy for this item
        self.merge_rules_list.addItem(item)
        self.merge_rules_list.setCurrentItem(item) # Select the new item to display its details

    def remove_merge_rule(self):
        """Removes the currently selected map merge rule."""
        current_item = self.merge_rules_list.currentItem()
        if not current_item:
            QMessageBox.warning(self, "No Selection", "Please select a rule to remove.")
            return

        # No need to manage self.current_map_merge_rules separately if Qt.UserRole is the source of truth
        # rule_to_remove = current_item.data(Qt.UserRole)
        # if rule_to_remove in self.current_map_merge_rules:
        #     self.current_map_merge_rules.remove(rule_to_remove)
       
        row = self.merge_rules_list.row(current_item)
        self.merge_rules_list.takeItem(row)

        # Clear details panel or select next/previous
        if self.merge_rules_list.count() > 0:
            self.merge_rules_list.setCurrentRow(max(0, row -1)) # Select previous or first
        else:
            self.display_merge_rule_details(None, None) # Clear details if list is empty

    # Ensure this method is defined within the class ConfigEditorDialog
    def add_image_resolution_row(self):
        """Adds a new row to the IMAGE_RESOLUTIONS table after prompting the user."""
        table = self.widgets.get("IMAGE_RESOLUTIONS_TABLE")
        if not table:
            return

        name, ok_name = QInputDialog.getText(self, "Add Resolution", "Enter Name (e.g., 16K):")
        if not ok_name or not name.strip():
            if ok_name and not name.strip(): # User pressed OK but entered empty name
                QMessageBox.warning(self, "Invalid Input", "Name cannot be empty.")
            return # User cancelled or entered empty name

        # Check for duplicate name
        for r in range(table.rowCount()):
            if table.item(r, 0) and table.item(r, 0).text() == name:
                QMessageBox.warning(self, "Duplicate Name", f"The resolution name '{name}' already exists.")
                return

        resolution, ok_res = QInputDialog.getInt(self, "Add Resolution", "Enter Resolution (px):", 1024, 1, 65536, 1)
        if not ok_res:
            return # User cancelled

        row_position = table.rowCount()
        table.insertRow(row_position)
        table.setItem(row_position, 0, QTableWidgetItem(name))
        table.setItem(row_position, 1, QTableWidgetItem(str(resolution)))
        
        self._update_resolution_dependent_combos()

    def remove_image_resolution_row(self):
        """Removes the selected row(s) from the IMAGE_RESOLUTIONS table."""
        table = self.widgets.get("IMAGE_RESOLUTIONS_TABLE")
        if not table:
            return

        selected_rows = sorted(list(set(index.row() for index in table.selectedIndexes())), reverse=True)
        if not selected_rows:
            QMessageBox.warning(self, "No Selection", "Please select row(s) to remove.")
            return

        for row in selected_rows:
            table.removeRow(row)
            
        self._update_resolution_dependent_combos()

    def _update_resolution_dependent_combos(self):
        """Updates ComboBoxes that depend on IMAGE_RESOLUTIONS."""
        table = self.widgets.get("IMAGE_RESOLUTIONS_TABLE")
        stats_combo = self.widgets.get("CALCULATE_STATS_RESOLUTION")
        jpg_threshold_combo = self.widgets.get("RESOLUTION_THRESHOLD_FOR_JPG")

        if not table or (not stats_combo and not jpg_threshold_combo):
            return

        current_stats_selection = stats_combo.currentText() if stats_combo else None
        current_jpg_threshold_selection = jpg_threshold_combo.currentText() if jpg_threshold_combo else None

        resolution_names = []
        for r in range(table.rowCount()):
            name_item = table.item(r, 0)
            if name_item and name_item.text():
                resolution_names.append(name_item.text())
        
        if stats_combo:
            stats_combo.clear()
            stats_combo.addItems(resolution_names)
            if current_stats_selection in resolution_names:
                stats_combo.setCurrentText(current_stats_selection)
            elif resolution_names: # Select first item if previous selection is gone
                stats_combo.setCurrentIndex(0)

        if jpg_threshold_combo:
            jpg_threshold_combo.clear()
            jpg_threshold_options = ["Never", "Always"] + resolution_names
            jpg_threshold_combo.addItems(jpg_threshold_options)
            if current_jpg_threshold_selection in jpg_threshold_options:
                jpg_threshold_combo.setCurrentText(current_jpg_threshold_selection)
            elif jpg_threshold_options: # Select first item if previous selection is gone
                jpg_threshold_combo.setCurrentIndex(0)


    def pick_color(self, widget):
        """Opens a color dialog and sets the selected color in the widget."""
        color = QColorDialog.getColor(QColor(widget.text()))
        if color.isValid():
            widget.setText(color.name()) # Get color as hex string

    def save_settings(self):
        """
        Reads values from widgets, compares them to the original loaded settings,
        and saves only the changed values to config/user_settings.json, preserving
        other existing user settings.
        """
        # 1a. Load Current Target File (user_settings.json)
        user_settings_path = os.path.join("config", "user_settings.json")

        target_file_content = {}
        if os.path.exists(user_settings_path):
            try:
                with open(user_settings_path, 'r') as f:
                    target_file_content = json.load(f)
            except json.JSONDecodeError:
                QMessageBox.warning(self, "Warning",
                                    f"File {user_settings_path} is corrupted or not valid JSON. "
                                    f"It will be overwritten if changes are saved.")
                target_file_content = {} # Start fresh if corrupted
            except Exception as e:
                QMessageBox.critical(self, "Error Loading User Settings",
                                     f"Failed to load {user_settings_path}: {e}. "
                                     f"Proceeding with empty user settings for this save operation.")
                target_file_content = {}
        
        # 1b. Get current settings from UI by populating a full settings dictionary
        full_ui_state = copy.deepcopy(self.settings) # Start with the loaded settings structure

        # --- Populate full_ui_state from ALL widgets ---
        for widget_config_key, widget_obj in self.widgets.items():
            keys_path = widget_config_key.split('.')
            current_level_dict = full_ui_state
            for i, part_of_key in enumerate(keys_path):
                if i == len(keys_path) - 1:
                    if isinstance(widget_obj, QLineEdit):
                        current_level_dict[part_of_key] = widget_obj.text()
                    elif isinstance(widget_obj, QSpinBox):
                        current_level_dict[part_of_key] = widget_obj.value()
                    elif isinstance(widget_obj, QDoubleSpinBox):
                        current_level_dict[part_of_key] = widget_obj.value()
                    elif isinstance(widget_obj, QCheckBox):
                        if widget_config_key == "general_settings.invert_normal_map_green_channel_globally":
                            if 'general_settings' not in full_ui_state:
                                full_ui_state['general_settings'] = {}
                            full_ui_state['general_settings']['invert_normal_map_green_channel_globally'] = widget_obj.isChecked()
                        else:
                            current_level_dict[part_of_key] = widget_obj.isChecked()
                    elif isinstance(widget_obj, QListWidget) and widget_config_key == "RESPECT_VARIANT_MAP_TYPES":
                        items = [widget_obj.item(i_item).text() for i_item in range(widget_obj.count())]
                        current_level_dict[part_of_key] = items
                    elif isinstance(widget_obj, QComboBox):
                        if widget_config_key == "RESOLUTION_THRESHOLD_FOR_JPG":
                            selected_text = widget_obj.currentText()
                            image_resolutions_data = full_ui_state.get('IMAGE_RESOLUTIONS', {})
                            if selected_text == "Never": current_level_dict[part_of_key] = 999999
                            elif selected_text == "Always": current_level_dict[part_of_key] = 1
                            elif isinstance(image_resolutions_data, dict) and selected_text in image_resolutions_data:
                                current_level_dict[part_of_key] = image_resolutions_data[selected_text]
                            else: current_level_dict[part_of_key] = selected_text # Fallback
                        else:
                            current_level_dict[part_of_key] = widget_obj.currentText()
                    elif widget_config_key == "IMAGE_RESOLUTIONS_TABLE" and isinstance(widget_obj, QTableWidget):
                        table = widget_obj
                        resolutions_dict = {}
                        for row in range(table.rowCount()):
                            name_item = table.item(row, 0)
                            res_item = table.item(row, 1)
                            if name_item and name_item.text() and res_item and res_item.text():
                                name = name_item.text()
                                try:
                                    resolutions_dict[name] = int(res_item.text())
                                except ValueError:
                                    print(f"Warning: Resolution value '{res_item.text()}' for '{name}' is not an integer. Skipping.")
                        full_ui_state['IMAGE_RESOLUTIONS'] = resolutions_dict
                else:
                    if part_of_key not in current_level_dict or not isinstance(current_level_dict[part_of_key], dict):
                        current_level_dict[part_of_key] = {}
                    current_level_dict = current_level_dict[part_of_key]

        # Special handling for MAP_MERGE_RULES - build from QListWidget items
        if hasattr(self, 'merge_rules_list'):
            updated_merge_rules = []
            for i in range(self.merge_rules_list.count()):
                item = self.merge_rules_list.item(i)
                rule_data = item.data(Qt.UserRole)
                if rule_data:
                    updated_merge_rules.append(copy.deepcopy(rule_data)) # Add a copy to avoid issues if UserRole is reused
            full_ui_state['MAP_MERGE_RULES'] = updated_merge_rules
        
        # --- End of populating full_ui_state ---

        # 2. Identify Changes by comparing with self.original_user_configurable_settings
        changed_settings_count = 0
        for key_to_check, original_value in self.original_user_configurable_settings.items():
            current_value_from_ui = full_ui_state.get(key_to_check)
            if current_value_from_ui != original_value:
                target_file_content[key_to_check] = copy.deepcopy(current_value_from_ui)
                changed_settings_count += 1
                print(f"Setting '{key_to_check}' changed. Old: {original_value}, New: {current_value_from_ui}")

        # 3. Save Updated Content to user_settings.json
        if changed_settings_count > 0 or not os.path.exists(user_settings_path):
            try:
                save_user_config(target_file_content)
                QMessageBox.information(self, "Settings Saved",
                                        f"User settings saved successfully to {user_settings_path}.\n"
                                        f"{changed_settings_count} setting(s) updated. "
                                        "Some changes may require an application restart.")
                self.accept()
            except ConfigurationError as e:
                QMessageBox.critical(self, "Saving Error", f"Failed to save user configuration: {e}")
            except Exception as e:
                QMessageBox.critical(self, "Saving Error", f"An unexpected error occurred while saving: {e}")
        else:
            QMessageBox.information(self, "No Changes", "No changes were made to user-configurable settings.")
            self.accept()

    def populate_widgets_from_settings(self):
        """Populates the created widgets with loaded settings."""
        if not self.settings or not self.widgets:
            return

        for key, value in self.settings.items():
            # Handle simple settings directly if they have a corresponding widget
            if key == "general_settings": # Handle nested dictionary
                if isinstance(value, dict):
                    for sub_key, sub_value in value.items():
                        widget_full_key = f"{key}.{sub_key}"
                        if widget_full_key in self.widgets:
                            widget = self.widgets[widget_full_key]
                            if isinstance(widget, QCheckBox) and isinstance(sub_value, bool):
                                widget.setChecked(sub_value)
            elif key in self.widgets and isinstance(self.widgets[key], (QLineEdit, QSpinBox, QDoubleSpinBox, QCheckBox, QComboBox, QListWidget)): # Added QListWidget
                 widget = self.widgets[key]
                 if key == "RESPECT_VARIANT_MAP_TYPES" and isinstance(widget, QListWidget):
                     widget.clear()
                     if isinstance(value, list):
                         for item_text in value: # value is the list of strings from settings
                             widget.addItem(str(item_text))
                 elif isinstance(widget, QLineEdit):
                     # This case should not be hit for RESPECT_VARIANT_MAP_TYPES anymore
                     if isinstance(value, (str, int, float, bool)):
                          widget.setText(str(value))
                 elif isinstance(widget, QSpinBox) and isinstance(value, int):
                     widget.setValue(value)
                 elif isinstance(widget, QDoubleSpinBox) and isinstance(value, (int, float)):
                     widget.setValue(float(value))
                 elif isinstance(widget, QCheckBox) and isinstance(value, bool):
                     widget.setChecked(value)
                 elif isinstance(widget, QComboBox):
                      if value in [widget.itemText(i) for i in range(widget.count())]:
                          widget.setCurrentText(value)


            # Handle complex structures with dedicated widgets (Tables and Lists)
            elif key == "ASSET_TYPE_DEFINITIONS" and "ASSET_TYPE_DEFINITIONS_TABLE" in self.widgets:
                 self.populate_asset_definitions_table(self.widgets["ASSET_TYPE_DEFINITIONS_TABLE"], value)
            elif key == "FILE_TYPE_DEFINITIONS" and "FILE_TYPE_DEFINITIONS_TABLE" in self.widgets:
                 self.populate_file_type_definitions_table(self.widgets["FILE_TYPE_DEFINITIONS_TABLE"], value)
            elif key == "IMAGE_RESOLUTIONS" and "IMAGE_RESOLUTIONS_TABLE" in self.widgets:
                 self.populate_image_resolutions_table(self.widgets["IMAGE_RESOLUTIONS_TABLE"], value)
                 # Populate ComboBoxes that depend on Image Resolutions - now handled by _update_resolution_dependent_combos
                 # Call it here to ensure initial population is correct after table is filled.
                 self._update_resolution_dependent_combos()
                 # Restore original selection if possible
                 if "CALCULATE_STATS_RESOLUTION" in self.settings and self.widgets.get("CALCULATE_STATS_RESOLUTION"):
                     if self.settings["CALCULATE_STATS_RESOLUTION"] in [self.widgets["CALCULATE_STATS_RESOLUTION"].itemText(i) for i in range(self.widgets["CALCULATE_STATS_RESOLUTION"].count())]:
                        self.widgets["CALCULATE_STATS_RESOLUTION"].setCurrentText(self.settings["CALCULATE_STATS_RESOLUTION"])
                 
                 if "RESOLUTION_THRESHOLD_FOR_JPG" in self.settings and self.widgets.get("RESOLUTION_THRESHOLD_FOR_JPG"):
                    # Map stored integer value back to text for selection
                    stored_jpg_threshold_val = self.settings["RESOLUTION_THRESHOLD_FOR_JPG"]
                    current_text_selection = None
                    if isinstance(stored_jpg_threshold_val, int):
                        if stored_jpg_threshold_val == 999999: current_text_selection = "Never"
                        elif stored_jpg_threshold_val == 1: current_text_selection = "Always"
                        else: # Try to find by value in the resolutions
                            res_table = self.widgets["IMAGE_RESOLUTIONS_TABLE"]
                            for r_idx in range(res_table.rowCount()):
                                if res_table.item(r_idx, 1) and int(res_table.item(r_idx, 1).text()) == stored_jpg_threshold_val:
                                    current_text_selection = res_table.item(r_idx, 0).text()
                                    break
                    elif isinstance(stored_jpg_threshold_val, str): # If it was already a name
                        current_text_selection = stored_jpg_threshold_val

                    if current_text_selection and current_text_selection in [self.widgets["RESOLUTION_THRESHOLD_FOR_JPG"].itemText(i) for i in range(self.widgets["RESOLUTION_THRESHOLD_FOR_JPG"].count())]:
                        self.widgets["RESOLUTION_THRESHOLD_FOR_JPG"].setCurrentText(current_text_selection)


            elif key == "MAP_BIT_DEPTH_RULES" and "MAP_BIT_DEPTH_RULES_TABLE" in self.widgets:
                 self.populate_map_bit_depth_rules_table(self.widgets["MAP_BIT_DEPTH_RULES_TABLE"], value)


            elif key == "MAP_MERGE_RULES" and hasattr(self, 'merge_rules_list'): # Check if the list widget exists
                 self.populate_merge_rules_list(value)
                 # Select the first item to display details if the list is not empty
                 if self.merge_rules_list.count() > 0:
                     self.merge_rules_list.setCurrentRow(0)


    def populate_asset_definitions_table(self, table: QTableWidget, definitions_data: dict):
        """Populates the asset definitions table."""
        table.setRowCount(len(definitions_data))
        row = 0
        for asset_type, details in definitions_data.items():
            item_type_name = QTableWidgetItem(asset_type)
            item_description = QTableWidgetItem(details.get("description", ""))
            table.setItem(row, 0, item_type_name)
            table.setItem(row, 1, item_description)

            # Color column - Set item with color string as data
            color_str = details.get("color", "#ffffff") # Default to white if missing
            item_color = QTableWidgetItem() # No text needed, delegate handles paint
            item_color.setData(Qt.EditRole, color_str) # Store hex string for delegate/editing
            # item_color.setBackground(QColor(color_str)) # Optional: Set initial background via item
            table.setItem(row, 2, item_color)

            # Examples column
            examples_list = details.get("examples", [])
            examples_str = ", ".join(examples_list) if isinstance(examples_list, list) else ""
            item_examples = QTableWidgetItem(examples_str)
            table.setItem(row, 3, item_examples)

            # Background color is now handled by the delegate's paint method based on data

            row += 1

        # After populating the Asset Types table, populate the DEFAULT_ASSET_CATEGORY ComboBox
        if "DEFAULT_ASSET_CATEGORY" in self.widgets and isinstance(self.widgets["DEFAULT_ASSET_CATEGORY"], QComboBox):
            asset_types = list(definitions_data.keys())
            self.widgets["DEFAULT_ASSET_CATEGORY"].addItems(asset_types)
            # Set the current value if it exists in settings
            if "DEFAULT_ASSET_CATEGORY" in self.settings and self.settings["DEFAULT_ASSET_CATEGORY"] in asset_types:
                 self.widgets["DEFAULT_ASSET_CATEGORY"].setCurrentText(self.settings["DEFAULT_ASSET_CATEGORY"])


    def populate_file_type_definitions_table(self, table: QTableWidget, definitions_data: dict):
        """Populates the file type definitions table."""
        table.setRowCount(len(definitions_data))
        row = 0
        for file_type, details in definitions_data.items():
            item_type_id = QTableWidgetItem(file_type)
            item_description = QTableWidgetItem(details.get("description", ""))
            table.setItem(row, 0, item_type_id)
            table.setItem(row, 1, item_description)

            # Color column - Set item with color string as data
            color_str = details.get("color", "#ffffff") # Default to white if missing
            item_color = QTableWidgetItem() # No text needed, delegate handles paint
            item_color.setData(Qt.EditRole, color_str) # Store hex string for delegate/editing
            # item_color.setBackground(QColor(color_str)) # Optional: Set initial background via item
            table.setItem(row, 2, item_color)

            # Examples column
            examples_list = details.get("examples", [])
            examples_str = ", ".join(examples_list) if isinstance(examples_list, list) else ""
            item_examples = QTableWidgetItem(examples_str)
            table.setItem(row, 3, item_examples)

            # Standard Type column (simple QTableWidgetItem for now)
            standard_type_str = details.get("standard_type", "")
            item_standard_type = QTableWidgetItem(standard_type_str)
            table.setItem(row, 4, item_standard_type)

            # Bit Depth Rule column (simple QTableWidgetItem for now)
            bit_depth_rule_str = details.get("bit_depth_rule", "")
            item_bit_depth_rule = QTableWidgetItem(bit_depth_rule_str)
            table.setItem(row, 5, item_bit_depth_rule)

            # Background color is now handled by the delegate's paint method based on data

            row += 1

    def populate_image_resolutions_table(self, table: QTableWidget, resolutions_data: dict):
        """Populates the image resolutions table from a dictionary."""
        table.setRowCount(0) # Clear existing rows before populating
        table.setRowCount(len(resolutions_data))
        row = 0
        for name, resolution_value in resolutions_data.items():
            try:
                name_item = QTableWidgetItem(str(name))
                res_item = QTableWidgetItem(str(resolution_value))
                
                # Make items editable for Phase 1 (actual editing will be improved in Phase 3)
                name_item.setFlags(name_item.flags() | Qt.ItemIsEditable)
                res_item.setFlags(res_item.flags() | Qt.ItemIsEditable)

                table.setItem(row, 0, name_item)
                table.setItem(row, 1, res_item)
            except Exception as e:
                 print(f"Error populating resolution row for '{name}': {e}")
                 # Optionally add a row indicating error
                 table.setItem(row, 0, QTableWidgetItem(str(name)))
                 table.setItem(row, 1, QTableWidgetItem(f"Error: {e}"))
            row += 1


    def populate_map_bit_depth_rules_table(self, table: QTableWidget, rules_data: dict):
        """Populates the map bit depth rules table."""
        table.setRowCount(len(rules_data))
        row = 0
        for map_type, rule in rules_data.items():
            table.setItem(row, 0, QTableWidgetItem(map_type))
            table.setItem(row, 1, QTableWidgetItem(str(rule))) # Rule (respect/force_8bit)
            row += 1




# Example usage (for testing the dialog independently)
if __name__ == '__main__':
    # Use PySide6 instead of PyQt5 for consistency
    from PySide6.QtWidgets import QApplication
    import sys

    app = QApplication(sys.argv)
    dialog = ConfigEditorDialog()
    dialog.exec() # Use exec() for PySide6 QDialog
    sys.exit(app.exec()) # Use exec() for PySide6 QApplication