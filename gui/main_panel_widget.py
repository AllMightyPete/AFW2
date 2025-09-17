import functools
import sys
import os
import json
import logging
import time
from pathlib import Path
from functools import partial

from PySide6.QtWidgets import QApplication
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QSplitter, QTableView,
    QPushButton, QComboBox, QTableWidget, QTableWidgetItem, QHeaderView,
    QProgressBar, QLabel, QFrame, QCheckBox, QSpinBox, QListWidget, QTextEdit,
    QLineEdit, QMessageBox, QFileDialog, QInputDialog, QListWidgetItem, QTabWidget,
    QFormLayout, QGroupBox, QAbstractItemView, QSizePolicy, QTreeView, QMenu
)
from PySide6.QtCore import Qt, Signal, Slot, QPoint, QModelIndex, QTimer
from PySide6.QtGui import QColor, QAction, QPalette, QClipboard, QGuiApplication

from .delegates import LineEditDelegate, ComboBoxDelegate, SupplierSearchDelegate, ItemTypeSearchDelegate
from .unified_view_model import UnifiedViewModel

from rule_structure import SourceRule, AssetRule, FileRule
import configuration
try:
    from configuration import ConfigurationError, load_base_config
except ImportError:
    ConfigurationError = Exception
    load_base_config = None
    class configuration:
        PRESETS_DIR = "Presets"

log = logging.getLogger(__name__)

class MainPanelWidget(QWidget):
    """
    Widget handling the main interaction panel:
    - Output directory selection
    - Asset preview/editing view (Unified View)
    - Blender post-processing options
    - Processing controls (Start, Cancel, Clear, LLM Re-interpret)
    """
    # --- Signals Emitted by the Panel ---

    # Request to start the main processing job
    process_requested = Signal(dict)

    cancel_requested = Signal()

    clear_queue_requested = Signal()

    llm_reinterpret_requested = Signal(list)
    preset_reinterpret_requested = Signal(list, str)

    output_dir_changed = Signal(str)

    blender_settings_changed = Signal(bool, str, str)

    def __init__(self, unified_model: UnifiedViewModel, parent=None, file_type_keys: list[str] | None = None):
        """
        Initializes the MainPanelWidget.

        Args:
            unified_model: The shared UnifiedViewModel instance.
            parent: The parent widget.
            file_type_keys: A list of available file type names (keys from FILE_TYPE_DEFINITIONS).
        """
        super().__init__(parent)
        self.unified_model = unified_model
        self.file_type_keys = file_type_keys if file_type_keys else []
        self.llm_processing_active = False

        script_dir = Path(__file__).parent
        self.project_root = script_dir.parent

        self._setup_ui()
        self._connect_signals()

    def _setup_ui(self):
        """Sets up the UI elements for the panel."""
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(5, 5, 5, 5)

        output_layout = QHBoxLayout()
        self.output_dir_label = QLabel("Output Directory:")
        self.output_path_edit = QLineEdit()
        self.browse_output_button = QPushButton("Browse...")
        output_layout.addWidget(self.output_dir_label)
        output_layout.addWidget(self.output_path_edit, 1)
        output_layout.addWidget(self.browse_output_button)
        main_layout.addLayout(output_layout)

        if load_base_config:
            try:
                base_config = load_base_config()
                output_base_dir_config = base_config.get('OUTPUT_BASE_DIR', '../Asset_Processor_Output')
                default_output_dir = (self.project_root / output_base_dir_config).resolve()
                self.output_path_edit.setText(str(default_output_dir))
                log.info(f"MainPanelWidget: Default output directory set to: {default_output_dir}")
            except ConfigurationError as e:
                 log.error(f"MainPanelWidget: Error reading base configuration for default output directory: {e}")
                 self.output_path_edit.setText("")
            except Exception as e:
                log.exception(f"MainPanelWidget: Error setting default output directory: {e}")
                self.output_path_edit.setText("")
        else:
            log.warning("MainPanelWidget: load_base_config not available to set default output path.")
            self.output_path_edit.setText("")


        self.unified_view = QTreeView()
        self.unified_view.setModel(self.unified_model)

        lineEditDelegate = LineEditDelegate(self.unified_view)
        # TODO: Revisit ComboBoxDelegate dependency
        comboBoxDelegate = ComboBoxDelegate(self)
        supplierSearchDelegate = SupplierSearchDelegate(self)
        itemTypeSearchDelegate = ItemTypeSearchDelegate(self.file_type_keys, self)

        self.unified_view.setItemDelegateForColumn(UnifiedViewModel.COL_SUPPLIER, supplierSearchDelegate)
        self.unified_view.setItemDelegateForColumn(UnifiedViewModel.COL_ASSET_TYPE, comboBoxDelegate)
        self.unified_view.setItemDelegateForColumn(UnifiedViewModel.COL_TARGET_ASSET, lineEditDelegate)
        self.unified_view.setItemDelegateForColumn(UnifiedViewModel.COL_ITEM_TYPE, itemTypeSearchDelegate)
        self.unified_view.setItemDelegateForColumn(UnifiedViewModel.COL_NAME, lineEditDelegate)

        self.unified_view.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.unified_view.setAlternatingRowColors(True)
        self.unified_view.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.unified_view.setEditTriggers(QAbstractItemView.EditTrigger.DoubleClicked | QAbstractItemView.EditTrigger.SelectedClicked | QAbstractItemView.EditTrigger.EditKeyPressed)
        self.unified_view.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)

        header = self.unified_view.header()
        header.setStretchLastSection(False)
        header.setSectionResizeMode(UnifiedViewModel.COL_NAME, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(UnifiedViewModel.COL_TARGET_ASSET, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(UnifiedViewModel.COL_SUPPLIER, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(UnifiedViewModel.COL_ASSET_TYPE, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(UnifiedViewModel.COL_ITEM_TYPE, QHeaderView.ResizeMode.ResizeToContents)

        self.unified_view.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)

        self.unified_view.setDragEnabled(True)
        self.unified_view.setAcceptDrops(True)
        self.unified_view.setDropIndicatorShown(True)
        self.unified_view.setDefaultDropAction(Qt.MoveAction)
        self.unified_view.setDragDropMode(QAbstractItemView.InternalMove)
        self.unified_view.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)

        main_layout.addWidget(self.unified_view, 1)

        self.progress_bar = QProgressBar()
        self.progress_bar.setValue(0)
        self.progress_bar.setTextVisible(True)
        self.progress_bar.setFormat("Idle")
        main_layout.addWidget(self.progress_bar)

        blender_group = QGroupBox("Blender Post-Processing")
        blender_layout = QVBoxLayout(blender_group)

        self.blender_integration_checkbox = QCheckBox("Run Blender Scripts After Processing")
        self.blender_integration_checkbox.setToolTip("If checked, attempts to run create_nodegroups.py and create_materials.py in Blender.")
        blender_layout.addWidget(self.blender_integration_checkbox)

        nodegroup_layout = QHBoxLayout()
        nodegroup_layout.addWidget(QLabel("Nodegroup .blend:"))
        self.nodegroup_blend_path_input = QLineEdit()
        self.browse_nodegroup_blend_button = QPushButton("...")
        self.browse_nodegroup_blend_button.setFixedWidth(30)
        nodegroup_layout.addWidget(self.nodegroup_blend_path_input)
        nodegroup_layout.addWidget(self.browse_nodegroup_blend_button)
        blender_layout.addLayout(nodegroup_layout)

        materials_layout = QHBoxLayout()
        materials_layout.addWidget(QLabel("Materials .blend:"))
        self.materials_blend_path_input = QLineEdit()
        self.browse_materials_blend_button = QPushButton("...")
        self.browse_materials_blend_button.setFixedWidth(30)
        materials_layout.addWidget(self.materials_blend_path_input)
        materials_layout.addWidget(self.browse_materials_blend_button)
        blender_layout.addLayout(materials_layout)

        if load_base_config:
            try:
                base_config = load_base_config()
                default_ng_path = base_config.get('DEFAULT_NODEGROUP_BLEND_PATH', '')
                default_mat_path = base_config.get('DEFAULT_MATERIALS_BLEND_PATH', '')
                self.nodegroup_blend_path_input.setText(default_ng_path if default_ng_path else "")
                self.materials_blend_path_input.setText(default_mat_path if default_mat_path else "")
            except ConfigurationError as e:
                 log.error(f"MainPanelWidget: Error reading base configuration for default Blender paths: {e}")
            except Exception as e:
                log.error(f"MainPanelWidget: Error reading default Blender paths from config: {e}")
        else:
            log.warning("MainPanelWidget: load_base_config not available to set default Blender paths.")


        self.nodegroup_blend_path_input.setEnabled(False)
        self.browse_nodegroup_blend_button.setEnabled(False)
        self.materials_blend_path_input.setEnabled(False)
        self.browse_materials_blend_button.setEnabled(False)

        main_layout.addWidget(blender_group)

        bottom_controls_layout = QHBoxLayout()
        self.overwrite_checkbox = QCheckBox("Overwrite Existing")
        self.overwrite_checkbox.setToolTip("If checked, existing output folders for processed assets will be deleted and replaced.")
        bottom_controls_layout.addWidget(self.overwrite_checkbox)

        self.workers_label = QLabel("Workers:")
        self.workers_spinbox = QSpinBox()
        default_workers = 1
        try:
            cores = os.cpu_count()
            if cores: default_workers = max(1, cores // 2)
        except NotImplementedError: pass
        self.workers_spinbox.setMinimum(1)
        self.workers_spinbox.setMaximum(os.cpu_count() or 32)
        self.workers_spinbox.setValue(default_workers)
        self.workers_spinbox.setToolTip("Number of assets to process concurrently.")
        bottom_controls_layout.addWidget(self.workers_label)
        bottom_controls_layout.addWidget(self.workers_spinbox)
        bottom_controls_layout.addStretch(1)


        self.clear_queue_button = QPushButton("Clear Queue")
        self.start_button = QPushButton("Start Processing")
        self.cancel_button = QPushButton("Cancel")
        self.cancel_button.setEnabled(False)

        bottom_controls_layout.addWidget(self.clear_queue_button)
        bottom_controls_layout.addWidget(self.start_button)
        bottom_controls_layout.addWidget(self.cancel_button)
        main_layout.addLayout(bottom_controls_layout)

    def _connect_signals(self):
        """Connect internal UI signals to slots or emit panel signals."""
        self.browse_output_button.clicked.connect(self._browse_for_output_directory)
        self.output_path_edit.editingFinished.connect(self._on_output_path_changed)

        self.unified_view.customContextMenuRequested.connect(self._show_unified_view_context_menu)

        self.blender_integration_checkbox.toggled.connect(self._toggle_blender_controls)
        self.browse_nodegroup_blend_button.clicked.connect(self._browse_for_nodegroup_blend)
        self.browse_materials_blend_button.clicked.connect(self._browse_for_materials_blend)
        self.nodegroup_blend_path_input.editingFinished.connect(self._emit_blender_settings_changed)
        self.materials_blend_path_input.editingFinished.connect(self._emit_blender_settings_changed)
        self.blender_integration_checkbox.toggled.connect(self._emit_blender_settings_changed)


        self.clear_queue_button.clicked.connect(self.clear_queue_requested)
        self.start_button.clicked.connect(self._on_start_processing_clicked)
        self.cancel_button.clicked.connect(self.cancel_requested)


    @Slot()
    def _browse_for_output_directory(self):
        """Opens a dialog to select the output directory."""
        current_path = self.output_path_edit.text()
        if not current_path or not Path(current_path).is_dir():
            current_path = str(self.project_root)

        directory = QFileDialog.getExistingDirectory(
            self,
            "Select Output Directory",
            current_path,
            QFileDialog.Option.ShowDirsOnly | QFileDialog.Option.DontResolveSymlinks
        )
        if directory:
            self.output_path_edit.setText(directory)
            self._on_output_path_changed()

    @Slot()
    def _on_output_path_changed(self):
        """Emits the output_dir_changed signal."""
        self.output_dir_changed.emit(self.output_path_edit.text())

    @Slot(bool)
    def _toggle_blender_controls(self, checked):
        """Enable/disable Blender path inputs based on the checkbox state."""
        self.nodegroup_blend_path_input.setEnabled(checked)
        self.browse_nodegroup_blend_button.setEnabled(checked)
        self.materials_blend_path_input.setEnabled(checked)
        self.browse_materials_blend_button.setEnabled(checked)

    def _browse_for_blend_file(self, line_edit_widget: QLineEdit):
        """Opens a dialog to select a .blend file and updates the line edit."""
        current_path = line_edit_widget.text()
        start_dir = str(Path(current_path).parent) if current_path and Path(current_path).exists() else str(self.project_root)

        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Select Blender File",
            start_dir,
            "Blender Files (*.blend);;All Files (*)"
        )
        if file_path:
            line_edit_widget.setText(file_path)
            line_edit_widget.editingFinished.emit()

    @Slot()
    def _browse_for_nodegroup_blend(self):
        self._browse_for_blend_file(self.nodegroup_blend_path_input)

    @Slot()
    def _browse_for_materials_blend(self):
        self._browse_for_blend_file(self.materials_blend_path_input)

    @Slot()
    def _emit_blender_settings_changed(self):
        """Gathers current Blender settings and emits the blender_settings_changed signal."""
        enabled = self.blender_integration_checkbox.isChecked()
        ng_path = self.nodegroup_blend_path_input.text()
        mat_path = self.materials_blend_path_input.text()
        self.blender_settings_changed.emit(enabled, ng_path, mat_path)

    @Slot()
    def _on_start_processing_clicked(self):
        """Gathers settings and emits the process_requested signal."""
        output_dir = self.output_path_edit.text().strip()
        if not output_dir:
            QMessageBox.warning(self, "Missing Output Directory", "Please select an output directory.")
            return

        try:
            Path(output_dir).mkdir(parents=True, exist_ok=True)
        except Exception as e:
             QMessageBox.warning(self, "Invalid Output Directory", f"Cannot use output directory:\n{output_dir}\n\nError: {e}")
             return

        settings = {
            "output_dir": output_dir,
            "overwrite": self.overwrite_checkbox.isChecked(),
            "workers": self.workers_spinbox.value(),
            "blender_enabled": self.blender_integration_checkbox.isChecked(),
            "nodegroup_blend_path": self.nodegroup_blend_path_input.text(),
            "materials_blend_path": self.materials_blend_path_input.text()
        }
        self.process_requested.emit(settings)


    def _get_unique_source_dirs_from_selection(self, selected_indexes: list[QModelIndex]) -> set[str]:
        """
        Extracts unique, valid source directory/zip paths from the selected QModelIndex list.
        Traverses up the model hierarchy to find the parent SourceRule for each index.
        """
        unique_source_dirs = set()
        model = self.unified_view.model()
        if not model:
            log.error("Unified view model not found.")
            return unique_source_dirs

        processed_source_paths = set()

        for index in selected_indexes:
            if not index.isValid():
                continue

            item_node = model.getItem(index)
            source_rule_node = None

            source_rule_node = None
            current_index = index
            while current_index.isValid():
                current_item = model.getItem(current_index)
                if isinstance(current_item, SourceRule):
                    source_rule_node = current_item
                    break
                current_index = model.parent(current_index) # Move to the parent index
            # If loop finishes without break, source_rule_node remains None

            if source_rule_node:
                source_path = getattr(source_rule_node, 'input_path', None)
                if source_path and source_path not in processed_source_paths:
                    source_path_obj = Path(source_path)
                    if source_path_obj.is_dir() or (source_path_obj.is_file() and source_path_obj.suffix.lower() == '.zip'):
                        log.debug(f"Identified source path for re-interpretation: {source_path}")
                        unique_source_dirs.add(source_path)
                        processed_source_paths.add(source_path)
                    else:
                         log.warning(f"Selected item's source path is not a directory or zip file: {source_path}")
                elif not source_path:
                     log.warning(f"Parent SourceRule found for index {index.row()},{index.column()} but has no 'input_path' attribute.")

            else:
                log.warning(f"Could not find parent SourceRule for selected index: {index.row()},{index.column()} (Node type: {type(item_node).__name__})")

        return unique_source_dirs

    @Slot()
    def _on_llm_reinterpret_clicked(self):
        """Gathers selected source paths and emits the llm_reinterpret_requested signal. (Triggered by context menu)"""
        if self.llm_processing_active:
             QMessageBox.warning(self, "Busy", "LLM processing is already in progress. Please wait.")
             return

        selected_indexes = self.unified_view.selectionModel().selectedIndexes()
        unique_source_dirs = self._get_unique_source_dirs_from_selection(selected_indexes)

        if not unique_source_dirs:
            log.warning("No valid source directories found for selected items to re-interpret with LLM.")
            # Optionally show status bar message via MainWindow reference if available
            return

        log.info(f"Emitting llm_reinterpret_requested for {len(unique_source_dirs)} paths.")
        self.llm_reinterpret_requested.emit(list(unique_source_dirs))


    @Slot(str, QModelIndex)
    def _on_reinterpret_preset_selected(self, preset_name: str, index: QModelIndex):
        """Handles the selection of a preset from the re-interpret context sub-menu."""
        log.info(f"Preset re-interpretation requested: Preset='{preset_name}', Index='{index.row()},{index.column()}'")
        selected_indexes = self.unified_view.selectionModel().selectedIndexes()
        unique_source_dirs = self._get_unique_source_dirs_from_selection(selected_indexes)

        if not unique_source_dirs:
            log.warning("No valid source directories found for selected items to re-interpret with preset.")
            # Optionally show status bar message via MainWindow reference if available
            return

        log.info(f"Emitting preset_reinterpret_requested for {len(unique_source_dirs)} paths with preset '{preset_name}'.")
        self.preset_reinterpret_requested.emit(list(unique_source_dirs), preset_name)


    @Slot(QPoint)
    def _show_unified_view_context_menu(self, point: QPoint):
        """Shows the context menu for the unified view."""
        index = self.unified_view.indexAt(point)
        if not index.isValid():
            return

        model = self.unified_view.model()
        if not model: return
        item_node = model.getItem(index)

        # Find the SourceRule node associated with the clicked index
        source_rule_node = None
        current_index = index
        while current_index.isValid():
            current_item = model.getItem(current_index)
            if isinstance(current_item, SourceRule):
                source_rule_node = current_item
                break
            current_index = model.parent(current_index) # Move to the parent index
        # If loop finishes without break, source_rule_node remains None

        menu = QMenu(self)

        if source_rule_node: # Only show if we clicked on or within a SourceRule item
            reinterpet_menu = menu.addMenu("Re-interpret selected source")

            preset_names = []
            try:
                presets_dir = configuration.PRESETS_DIR
                if os.path.isdir(presets_dir):
                    for filename in os.listdir(presets_dir):
                        if filename.endswith(".json") and filename != "_template.json":
                            preset_name = os.path.splitext(filename)[0]
                            preset_names.append(preset_name)
                    preset_names.sort()
                else:
                    log.warning(f"Presets directory not found or not a directory: {presets_dir}")
            except Exception as e:
                log.exception(f"Error listing presets in {configuration.PRESETS_DIR}: {e}")

            if preset_names:
                for preset_name in preset_names:
                    preset_action = QAction(preset_name, self)
                    preset_action.triggered.connect(functools.partial(self._on_reinterpret_preset_selected, preset_name, index))
                    reinterpet_menu.addAction(preset_action)
            else:
                 no_presets_action = QAction("No presets found", self)
                 no_presets_action.setEnabled(False)
                 reinterpet_menu.addAction(no_presets_action)


            reinterpet_menu.addSeparator()
            llm_action = QAction("LLM", self)
            llm_action.triggered.connect(self._on_llm_reinterpret_clicked)
            llm_action.setEnabled(not self.llm_processing_active)
            reinterpet_menu.addAction(llm_action)

            menu.addSeparator()

        if source_rule_node: # Check again if it's a source item for this action
            copy_llm_example_action = QAction("Copy LLM Example to Clipboard", self)
            copy_llm_example_action.setToolTip("Copies a JSON structure representing the input files and predicted output, suitable for LLM examples.")
            copy_llm_example_action.triggered.connect(lambda: self._copy_llm_example_to_clipboard(source_rule_node))
            menu.addAction(copy_llm_example_action)


        if not menu.isEmpty():
            menu.exec(self.unified_view.viewport().mapToGlobal(point))

    @Slot(SourceRule)
    def _copy_llm_example_to_clipboard(self, source_rule_node: SourceRule | None):
        """Copies a JSON structure for the given SourceRule node to the clipboard."""
        if not source_rule_node:
             log.warning(f"No SourceRule node provided to copy LLM example.")
             return

        source_rule: SourceRule = source_rule_node
        log.info(f"Attempting to generate LLM example JSON for source: {source_rule.input_path}")

        all_file_paths = []
        predicted_assets_data = []

        for asset_rule in source_rule.assets:
            asset_files_data = []
            for file_rule in asset_rule.files:
                if file_rule.file_path:
                    all_file_paths.append(file_rule.file_path)
                    asset_files_data.append({
                        "file_path": file_rule.file_path,
                        "predicted_file_type": file_rule.item_type or "UNKNOWN"
                    })
            asset_files_data.sort(key=lambda x: x['file_path'])
            predicted_assets_data.append({
                "suggested_asset_name": asset_rule.asset_name or "UnnamedAsset",
                "predicted_asset_type": asset_rule.asset_type or "UNKNOWN",
                "files": asset_files_data
            })

        predicted_assets_data.sort(key=lambda x: x['suggested_asset_name'])
        all_file_paths.sort()

        if not all_file_paths:
            log.warning(f"No file paths found for source: {source_rule.input_path}. Cannot generate example.")
            # Cannot show status bar message here
            return

        llm_example = {
            "input": "\n".join(all_file_paths),
            "output": {"predicted_assets": predicted_assets_data}
        }

        try:
            json_string = json.dumps(llm_example, indent=2)
            clipboard = QGuiApplication.clipboard()
            if clipboard:
                clipboard.setText(json_string)
                log.info(f"Copied LLM example JSON to clipboard for source: {source_rule.input_path}")
            else:
                log.error("Failed to get system clipboard.")
        except Exception as e:
            log.exception(f"Error copying LLM example JSON to clipboard: {e}")


    # --- Public Slots for MainWindow to Call ---

    @Slot(int, int)
    def update_progress_bar(self, current_count, total_count):
        """Updates the progress bar display."""
        if total_count > 0:
            percentage = int((current_count / total_count) * 100)
            log.debug(f"Updating progress bar: current={current_count}, total={total_count}, calculated_percentage={percentage}")
            self.progress_bar.setValue(percentage)
            self.progress_bar.setFormat(f"%p% ({current_count}/{total_count})")
            QApplication.processEvents()
        else:
            self.progress_bar.setValue(0)
            self.progress_bar.setFormat("0/0")

    @Slot(str)
    def set_progress_bar_text(self, text: str):
        """Sets the text format of the progress bar."""
        self.progress_bar.setFormat(text)
        if not "%" in text:
             self.progress_bar.setValue(0)


    @Slot(bool)
    def set_controls_enabled(self, enabled: bool):
        """Enables or disables controls within the panel."""
        self.output_path_edit.setEnabled(enabled)
        self.browse_output_button.setEnabled(enabled)
        self.unified_view.setEnabled(enabled)
        self.overwrite_checkbox.setEnabled(enabled)
        self.workers_spinbox.setEnabled(enabled)
        self.clear_queue_button.setEnabled(enabled)
        self.blender_integration_checkbox.setEnabled(enabled)

        # Start button is enabled only if controls are generally enabled AND preset mode is active (handled by MainWindow)
        # Cancel button is enabled only when processing is active (handled by MainWindow)
        # LLM button state depends on selection and LLM status (handled by _update_llm_reinterpret_button_state)

        # Blender path inputs depend on both 'enabled' and the checkbox state
        blender_paths_enabled = enabled and self.blender_integration_checkbox.isChecked()
        self.nodegroup_blend_path_input.setEnabled(blender_paths_enabled)
        self.browse_nodegroup_blend_button.setEnabled(blender_paths_enabled)
        self.materials_blend_path_input.setEnabled(blender_paths_enabled)
        self.browse_materials_blend_button.setEnabled(blender_paths_enabled)



    @Slot(bool)
    def set_start_button_enabled(self, enabled: bool):
        """Sets the enabled state of the Start Processing button."""
        self.start_button.setEnabled(enabled)

    @Slot(str)
    def set_start_button_text(self, text: str):
        """Sets the text of the Start Processing button."""
        self.start_button.setText(text)

    @Slot(bool)
    def set_cancel_button_enabled(self, enabled: bool):
        """Sets the enabled state of the Cancel button."""
        self.cancel_button.setEnabled(enabled)

    @Slot(bool)
    def set_llm_processing_status(self, active: bool):
        """Informs the panel whether LLM processing is active (used for context menu state)."""
        self.llm_processing_active = active
        # No button state to update directly, but context menu will check this flag when built.

    # TODO: Add method to get current output path if needed by MainWindow before processing
    def get_output_directory() -> str:
        return self.output_path_edit.text().strip()

    # TODO: Add method to get current Blender settings if needed by MainWindow before processing
    def get_blender_settings() -> dict:
        return {
            "enabled": self.blender_integration_checkbox.isChecked(),
            "nodegroup_blend_path": self.nodegroup_blend_path_input.text(),
            "materials_blend_path": self.materials_blend_path_input.text()
        }

    # TODO: Add method to get current worker count if needed by MainWindow before processing
    def get_worker_count() -> int:
        return self.workers_spinbox.value()

    # TODO: Add method to get current overwrite setting if needed by MainWindow before processing
    def get_overwrite_setting() -> bool:
        return self.overwrite_checkbox.isChecked()

    def get_llm_source_preset_name() -> str | None:
        """
        Placeholder for providing context to delegates.
        Ideally, the required info (like last preset name) should be passed
        from MainWindow when the delegate needs it, or the delegate's dependency
        should be refactored.
        """
        log.warning("MainPanelWidget.get_llm_source_preset_name called - needs proper implementation or refactoring.")
        # This needs to get the info from MainWindow, perhaps via a signal/slot or passed reference.
        # Returning None for now.
        return None