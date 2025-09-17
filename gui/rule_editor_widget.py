import sys
from PySide6.QtWidgets import (QApplication, QWidget, QVBoxLayout, QLabel, QLineEdit,
                               QFormLayout, QComboBox, QCheckBox, QSpinBox, QDoubleSpinBox)
from PySide6.QtCore import Signal, Slot, QObject


class RuleEditorWidget(QWidget):
     """
     A widget to display and edit hierarchical processing rules (Source, Asset, File).
     """
     rule_updated = Signal(object)
 
     def __init__(self, asset_types: list[str] | None = None, file_types: list[str] | None = None, parent=None):
         """
         Initializes the RuleEditorWidget.
 
         Args:
             asset_types (list[str] | None): A list of available asset type names. Defaults to None.
             file_types (list[str] | None): A list of available file type names (keys from FILE_TYPE_DEFINITIONS). Defaults to None.
             parent: The parent widget.
         """
         super().__init__(parent)
         self.asset_types = asset_types if asset_types else []
         self.file_types = file_types if file_types else []
         self.current_rule_type = None
         self.current_rule_object = None
 
         self.layout = QVBoxLayout(self)
         self.rule_type_label = QLabel("Select an item in the hierarchy to view/edit rules.")
         self.layout.addWidget(self.rule_type_label)
 
         self.form_layout = QFormLayout()
         self.layout.addLayout(self.form_layout)
 
         self.layout.addStretch() # Add stretch to push content to the top
 
         self.setLayout(self.layout)
         self.clear_editor()
 
     @Slot(object, str)
     def load_rule(self, rule_object, rule_type_name):
         """
         Loads a rule object into the editor.
 
         Args:
             rule_object: The SourceRule, AssetRule, or FileRule object.
             rule_type_name: The name of the rule type ('SourceRule', 'AssetRule', 'FileRule').
         """
         self.clear_editor()
         self.current_rule_object = rule_object
         self.current_rule_type = rule_type_name
         self.rule_type_label.setText(f"Editing: {rule_type_name}")
 
         if rule_object:
             # Dynamically create form fields based on rule object attributes
             for attr_name, attr_value in vars(rule_object).items():
                 if attr_name.startswith('_'): # Skip private attributes
                     continue
 
                 label = QLabel(attr_name.replace('_', ' ').title() + ":")
                 editor_widget = self._create_editor_widget(attr_name, attr_value)
                 if editor_widget:
                     self.form_layout.addRow(label, editor_widget)
                     self._connect_editor_signal(editor_widget, attr_name)
 
     def _create_editor_widget(self, attr_name, attr_value):
         """
         Creates an appropriate editor widget based on the attribute type.
         """
         # --- Special Handling for Asset Type Dropdown ---
         if self.current_rule_type == 'AssetRule' and attr_name in ('asset_type', 'asset_type_override') and self.asset_types:
             widget = QComboBox()
             widget.addItems(self.asset_types)
             # Handle None case for override: if None, don't select anything or select a placeholder
             if attr_value is None and attr_name == 'asset_type_override':
                  # Optionally add a placeholder like "<None>" or "<Default>"
                  widget.setCurrentIndex(-1) # No selection or placeholder
             elif attr_value in self.asset_types:
                 widget.setCurrentText(attr_value)
             elif self.asset_types: # Select first item if current value is invalid (and not None override)
                 widget.setCurrentIndex(0)
             return widget
         # --- Special Handling for FileRule item_type and item_type_override ---
         elif self.current_rule_type == 'FileRule' and attr_name in ('item_type', 'item_type_override') and self.file_types:
             widget = QComboBox()
             widget.addItems(self.file_types)
             if attr_value in self.file_types:
                 widget.setCurrentText(attr_value)
             elif self.file_types: # Select first item if current value is invalid
                 widget.setCurrentIndex(0)
             return widget
         # --- Standard Type Handling ---
         elif isinstance(attr_value, bool):
             widget = QCheckBox()
             widget.setChecked(attr_value)
             return widget
         elif isinstance(attr_value, int):
             widget = QSpinBox()
             widget.setRange(-2147483648, 2147483647) # Default integer range
             widget.setValue(attr_value)
             return widget
         elif isinstance(attr_value, float):
             widget = QDoubleSpinBox()
             widget.setRange(-sys.float_info.max, sys.float_info.max) # Default float range
             widget.setValue(attr_value)
             return widget
         elif isinstance(attr_value, (str, type(None))): # Handle None for strings
             widget = QLineEdit()
             widget.setText(str(attr_value) if attr_value is not None else "")
             return widget
         else:
             # For unsupported types, just display the value
             label = QLabel(str(attr_value))
             return label
 
     def _connect_editor_signal(self, editor_widget, attr_name):
         """
         Connects the appropriate signal of the editor widget to the update logic.
         """
         if isinstance(editor_widget, QLineEdit):
             editor_widget.textChanged.connect(lambda text: self._update_rule_attribute(attr_name, text))
         elif isinstance(editor_widget, QCheckBox):
             editor_widget.toggled.connect(lambda checked: self._update_rule_attribute(attr_name, checked))
         elif isinstance(editor_widget, QSpinBox):
             editor_widget.valueChanged.connect(lambda value: self._update_rule_attribute(attr_name, value))
         elif isinstance(editor_widget, QDoubleSpinBox):
             editor_widget.valueChanged.connect(lambda value: self._update_rule_attribute(attr_name, value))
         elif isinstance(editor_widget, QComboBox):
             # Use currentTextChanged to get the string value directly
             editor_widget.currentTextChanged.connect(lambda text: self._update_rule_attribute(attr_name, text))
 
     def _update_rule_attribute(self, attr_name, value):
         """
         Updates the attribute of the current rule object and emits the signal.
         """
         if self.current_rule_object:
             # Basic type conversion based on the original attribute type
             original_value = getattr(self.current_rule_object, attr_name)
             try:
                 if isinstance(original_value, bool):
                     converted_value = bool(value)
                 elif isinstance(original_value, int):
                     converted_value = int(value)
                 elif isinstance(original_value, float):
                     converted_value = float(value)
                 elif isinstance(original_value, (str, type(None))):
                      converted_value = str(value) if value != "" else None # Convert empty string to None for original None types
                 else:
                     converted_value = value # Fallback for other types
                 setattr(self.current_rule_object, attr_name, converted_value)
                 self.rule_updated.emit(self.current_rule_object)
             except ValueError:
                 # Handle potential conversion errors (e.g., non-numeric input for int/float)
                 print(f"Error converting value '{value}' for attribute '{attr_name}'")
                 # Optionally, revert the editor widget to the original value or show an error indicator
 
     def clear_editor(self):
         """
         Clears the form layout.
         """
         self.current_rule_object = None
         self.current_rule_type = None
         self.rule_type_label.setText("Select an item in the hierarchy to view/edit rules.")
         while self.form_layout.rowCount() > 0:
             self.form_layout.removeRow(0)

if __name__ == '__main__':
    app = QApplication(sys.argv)

    # Placeholder Rule Classes for testing
    from dataclasses import dataclass, field

    @dataclass
    class SourceRule:
        source_setting_1: str = "default_source_string"
        source_setting_2: int = 123
        source_setting_3: bool = True

    @dataclass
    class AssetRule:
        asset_setting_a: float = 4.56
        asset_setting_b: str = None
        asset_setting_c: bool = False

    @dataclass
    class FileRule:
        file_setting_x: int = 789
        file_setting_y: str = "default_file_string"

    # Example usage: Provide asset types during instantiation
    asset_types_from_config = ["Surface", "Model", "Decal", "Atlas", "UtilityMap"]
    file_types_from_config = ["MAP_COL", "MAP_NRM", "MAP_METAL", "MAP_ROUGH", "MAP_AO", "MAP_DISP", "MAP_REFL", "MAP_SSS", "MAP_FUZZ", "MAP_IDMAP", "MAP_MASK", "MAP_IMPERFECTION", "MODEL", "EXTRA", "FILE_IGNORE"]
    editor = RuleEditorWidget(asset_types=asset_types_from_config, file_types=file_types_from_config)

    # Test loading different rule types
    source_rule = SourceRule()
    asset_rule = AssetRule()
    file_rule = FileRule()

    editor.load_rule(source_rule, "SourceRule")


    editor.show()
    sys.exit(app.exec())