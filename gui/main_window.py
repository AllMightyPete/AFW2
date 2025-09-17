import sys
import os
import json
import logging
import time
import zipfile
from pathlib import Path
from functools import partial
log = logging.getLogger(__name__)
log.info(f"sys.path: {sys.path}")

from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QSplitter, QTableView,
    QPushButton, QComboBox, QTableWidget, QTableWidgetItem, QHeaderView, QStackedWidget,
    QProgressBar, QLabel, QFrame, QCheckBox, QSpinBox, QListWidget, QTextEdit,
    QLineEdit, QMessageBox, QFileDialog, QInputDialog, QListWidgetItem, QTabWidget,
    QFormLayout, QGroupBox, QAbstractItemView, QSizePolicy,
    QMenuBar, QMenu, QTreeView
)
from PySide6.QtCore import Qt, QThread, Slot, Signal, QObject, QModelIndex, QItemSelectionModel, QPoint, QTimer
from PySide6.QtGui import QColor, QAction, QPalette, QClipboard
from PySide6.QtGui import QKeySequence

# --- Local GUI Imports ---
from .preset_editor_widget import PresetEditorWidget
from .llm_editor_widget import LLMEditorWidget
from .log_console_widget import LogConsoleWidget
from .main_panel_widget import MainPanelWidget

from .definitions_editor_dialog import DefinitionsEditorDialog
# --- Backend Imports for Data Structures ---
from rule_structure import SourceRule, AssetRule, FileRule


# --- GUI Model Imports ---
from gui.unified_view_model import UnifiedViewModel, CustomRoles
# Removed delegate imports, now handled by MainPanelWidget
from .prediction_handler import RuleBasedPredictionHandler
from .llm_interaction_handler import LLMInteractionHandler
from .asset_restructure_handler import AssetRestructureHandler

 # --- Backend Imports ---
script_dir = Path(__file__).parent
project_root = script_dir.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

try:
    from configuration import Configuration, ConfigurationError, load_base_config


except ImportError as e:
    print(f"ERROR: Failed to import backend modules: {e}")
    print(f"Ensure GUI is run from project root or backend modules are in PYTHONPATH.")
    Configuration = None
    load_base_config = None
    ConfigurationError = Exception
    AssetProcessor = None
    RuleBasedPredictionHandler = None
    AssetProcessingError = Exception


# --- Constants ---
PRESETS_DIR = project_root / "presets"
TEMPLATE_PATH = PRESETS_DIR / "_template.json"

# Setup basic logging
log = logging.getLogger(__name__)
if not log.hasHandlers():
     logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')


# --- Custom Log Handler ---
class QtLogHandler(logging.Handler, QObject):
    """
    Custom logging handler that emits a Qt signal for each log record.
    Inherits from QObject to support signals.
    """
    log_record_received = Signal(str)

    def __init__(self, parent=None):
        logging.Handler.__init__(self)
        QObject.__init__(self, parent)

    def emit(self, record):
        """
        Overrides the default emit method to format the record and emit a signal.
        """
        try:
            msg = self.format(record)
            self.log_record_received.emit(msg)
        except Exception:
            self.handleError(record)


class MainWindow(QMainWindow):
    start_prediction_signal = Signal(str, list, str)
    start_backend_processing = Signal(list, dict)

    def __init__(self):
        super().__init__()

        self.setWindowTitle("Asset Processor Tool")
        self.resize(1200, 700)

        # --- Internal State ---
        self.current_asset_paths = set()
        self._pending_predictions = set()
        self._completed_predictions = set()
        self._accumulated_rules = {}
        self._source_file_lists = {}
        # Removed the problematic instantiation of Configuration without a preset.
        # self.config_manager will be set when a specific preset is loaded,
        # or LLM settings will be loaded directly via load_base_config().
        self.config_manager = None
        self.llm_processing_queue = []
        self._current_output_dir = ""
        self._current_blender_settings = {}

        # --- Threading Setup ---
        self.prediction_thread = None
        self.prediction_handler = None
        # LLM thread/handler are now managed by LLMInteractionHandler
        self.setup_threads()

        # --- Instantiate Handlers ---
        self.llm_interaction_handler = LLMInteractionHandler(self)


        # --- Main Layout with Splitter ---
        self.splitter = QSplitter(Qt.Orientation.Horizontal)
        self.setCentralWidget(self.splitter)

        # --- Create Models ---
        self.unified_model = UnifiedViewModel()
        # --- Instantiate Handlers that depend on the model ---
        self.restructure_handler = AssetRestructureHandler(self.unified_model, self)

        # --- Create Panels ---
        self.preset_editor_widget = PresetEditorWidget()
        self.llm_editor_widget = LLMEditorWidget()

        # --- Load File Type Definitions for Rule Editor ---
        file_type_keys = []
        try:
            base_cfg_data = load_base_config()
            if base_cfg_data and "FILE_TYPE_DEFINITIONS" in base_cfg_data:
                file_type_keys = list(base_cfg_data["FILE_TYPE_DEFINITIONS"].keys())
                log.info(f"Loaded {len(file_type_keys)} FILE_TYPE_DEFINITIONS keys for RuleEditor.")
            else:
                log.warning("FILE_TYPE_DEFINITIONS not found in base_config. RuleEditor item_type dropdown might be empty.")
        except Exception as e:
            log.exception(f"Error loading FILE_TYPE_DEFINITIONS for RuleEditor: {e}")

        # Instantiate MainPanelWidget, passing the model, self (MainWindow) for context, and file_type_keys
        self.main_panel_widget = MainPanelWidget(self.unified_model, self, file_type_keys=file_type_keys)
        self.log_console = LogConsoleWidget(self)

        # --- Create Left Pane with Static Selector and Stacked Editor ---
        self.left_pane_widget = QWidget()
        left_pane_layout = QVBoxLayout(self.left_pane_widget)
        left_pane_layout.setContentsMargins(0, 0, 0, 0)
        left_pane_layout.setSpacing(0)

        left_pane_layout.addWidget(self.preset_editor_widget.selector_container)

        self.editor_stack = QStackedWidget()
        self.editor_stack.addWidget(self.preset_editor_widget.json_editor_container)
        self.editor_stack.addWidget(self.llm_editor_widget)
        left_pane_layout.addWidget(self.editor_stack)

        self.splitter.addWidget(self.left_pane_widget)
        self.splitter.addWidget(self.main_panel_widget)

        # --- Setup UI Elements ---
        # Main panel UI is handled internally by MainPanelWidget
        self.setup_menu_bar()

        # --- Status Bar ---
        self.statusBar().showMessage("Ready")

        # --- Initial State ---
        self.setup_logging_handler()

        # --- Connect Signals from PresetEditorWidget ---
        self.preset_editor_widget.preset_selection_changed_signal.connect(self._on_preset_selection_changed)
        # --- Connect Signals from MainPanelWidget ---
        self.main_panel_widget.process_requested.connect(self._on_process_requested)
        self.main_panel_widget.cancel_requested.connect(self._on_cancel_requested)
        self.main_panel_widget.clear_queue_requested.connect(self._on_clear_queue_requested)
        self.main_panel_widget.llm_reinterpret_requested.connect(self._delegate_llm_reinterpret)
        self.main_panel_widget.output_dir_changed.connect(self._on_output_dir_changed)
        self.main_panel_widget.blender_settings_changed.connect(self._on_blender_settings_changed)

        self.main_panel_widget.preset_reinterpret_requested.connect(self._on_preset_reinterpret_requested)
        # --- Connect Signals from LLMInteractionHandler ---
        self.llm_interaction_handler.llm_prediction_ready.connect(self._on_llm_prediction_ready_from_handler)
        self.llm_interaction_handler.llm_prediction_error.connect(self._on_prediction_error)
        self.llm_interaction_handler.llm_status_update.connect(self.show_status_message)
        self.llm_interaction_handler.llm_processing_state_changed.connect(self._on_llm_processing_state_changed)

        # --- Connect Model Signals ---
        self.unified_model.targetAssetOverrideChanged.connect(self.restructure_handler.handle_target_asset_override)
        self.unified_model.assetNameChanged.connect(self.restructure_handler.handle_asset_name_changed)
        # --- Connect LLM Editor Signals ---
        self.llm_editor_widget.settings_saved.connect(self._on_llm_settings_saved)

        # --- Adjust Splitter ---
        self.splitter.setSizes([400, 800])

        # --- Initialize Keybind Map ---
        self.key_char_to_qt_key = {
            'C': Qt.Key_C, 'R': Qt.Key_R, 'N': Qt.Key_N, 'M': Qt.Key_M,
            'D': Qt.Key_D, 'E': Qt.Key_E, 'X': Qt.Key_X
        }
        self.qt_key_to_ftd_map = {}
        try:
            base_settings = load_base_config()
            file_type_defs = base_settings.get('FILE_TYPE_DEFINITIONS', {})
            for ftd_key, ftd_value in file_type_defs.items():
                if isinstance(ftd_value, dict) and 'keybind' in ftd_value:
                    char_key = ftd_value['keybind']
                    qt_key_val = self.key_char_to_qt_key.get(char_key)
                    if qt_key_val:
                        if qt_key_val not in self.qt_key_to_ftd_map:
                            self.qt_key_to_ftd_map[qt_key_val] = []
                        # Ensure consistent order for toggleable types if they are defined together under one key
                        # For example, if 'R' maps to ROUGH then GLOSS, they should appear in that order.
                        # This relies on the order in app_settings.json and dict iteration (Python 3.7+).
                        self.qt_key_to_ftd_map[qt_key_val].append(ftd_key)
            log.info(f"Loaded keybind map: {self.qt_key_to_ftd_map}")
        except Exception as e:
            log.error(f"Failed to load keybind configurations: {e}")
            # self.qt_key_to_ftd_map will be empty, keybinds won't work.


    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls(): event.acceptProposedAction()
        else: event.ignore()

    def dropEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
            urls = event.mimeData().urls()
            paths = [url.toLocalFile() for url in urls]
            self.add_input_paths(paths)
        else: event.ignore()

    def _extract_file_list(self, input_path_str: str) -> list | None:
        """Extracts a list of relative file paths from a directory or zip archive."""
        input_path = Path(input_path_str)
        file_list = []
        try:
            if input_path.is_dir():
                log.debug(f"Extracting files from directory: {input_path_str}")
                for root, _, files in os.walk(input_path):
                    for file in files:
                        full_path = Path(root) / file
                        # Use POSIX paths for consistency
                        relative_path = full_path.relative_to(input_path).as_posix()
                        file_list.append(relative_path)
                log.debug(f"Found {len(file_list)} files in directory.")
            elif input_path.is_file() and input_path.suffix.lower() == '.zip':
                log.debug(f"Extracting files from zip archive: {input_path_str}")
                if not zipfile.is_zipfile(input_path):
                    log.warning(f"File is not a valid zip archive: {input_path_str}")
                    return None
                with zipfile.ZipFile(input_path, 'r') as zip_ref:
                    # Filter out directory entries if any exist in the zip explicitly
                    file_list = [name for name in zip_ref.namelist() if not name.endswith('/')]
                log.debug(f"Found {len(file_list)} files in zip archive.")
            else:
                log.warning(f"Input path is neither a directory nor a supported .zip file: {input_path_str}")
                return None
            return file_list
        except FileNotFoundError:
            log.error(f"File or directory not found during extraction: {input_path_str}")
            self.statusBar().showMessage(f"Error: Input not found: {input_path.name}", 5000)
            return None
        except zipfile.BadZipFile:
            log.error(f"Bad zip file encountered: {input_path_str}")
            self.statusBar().showMessage(f"Error: Invalid zip file: {input_path.name}", 5000)
            return None
        except PermissionError:
            log.error(f"Permission denied accessing: {input_path_str}")
            self.statusBar().showMessage(f"Error: Permission denied for: {input_path.name}", 5000)
            return None
        except Exception as e:
            log.exception(f"Unexpected error extracting files from {input_path_str}: {e}")
            self.statusBar().showMessage(f"Error extracting files from: {input_path.name}", 5000)
            return None

    def add_input_paths(self, paths):
        log.debug(f"--> Entered add_input_paths with paths: {paths}")
        if not hasattr(self, 'current_asset_paths'): self.current_asset_paths = set()
        added_count = 0
        newly_added_paths = []
        for p_str in paths:
            p = Path(p_str)
            if p.exists():
                # Only support directories and .zip files for now
                if p.is_dir() or (p.is_file() and p.suffix.lower() == '.zip'):
                    if p_str not in self.current_asset_paths:
                        self.current_asset_paths.add(p_str)
                        newly_added_paths.append(p_str)
                        added_count += 1
                    else: log.debug(f"Skipping duplicate asset path: {p_str}")
                else: self.statusBar().showMessage(f"Invalid input (not dir or .zip): {p.name}", 5000); log.warning(f"Invalid input (not dir or .zip): {p_str}")
            else: self.statusBar().showMessage(f"Input path not found: {p.name}", 5000); print(f"Input path not found: {p_str}")
        if added_count > 0:
            log.info(f"Added {added_count} new asset paths: {newly_added_paths}")
            self.statusBar().showMessage(f"Added {added_count} asset(s). Updating preview...", 3000)

            mode, selected_display_name, preset_file_path = self.preset_editor_widget.get_selected_preset_mode()

            if mode == "llm":
                log.info(f"LLM Interpretation selected. Preparing LLM prediction for {len(newly_added_paths)} new paths.")
                llm_requests_to_queue = []
                for input_path_str in newly_added_paths:
                    file_list = self._extract_file_list(input_path_str)
                    if file_list is not None:
                        log.info(f"Extracted {len(file_list)} files for LLM prediction from: {input_path_str}")
                        self._source_file_lists[input_path_str] = file_list
                        # Use the same pending set for now
                        self._pending_predictions.add(input_path_str)
                        llm_requests_to_queue.append((input_path_str, file_list))
                    else:
                        log.warning(f"Skipping LLM prediction queuing for {input_path_str} due to extraction error.")
                if llm_requests_to_queue:
                    log.info(f"Delegating {len(llm_requests_to_queue)} LLM requests to the handler.")
                    self.llm_interaction_handler.queue_llm_requests_batch(llm_requests_to_queue)
                # The handler manages starting its own processing internally.
            elif mode == "preset" and selected_display_name and preset_file_path:
                preset_name_for_loading = preset_file_path.stem
                log.info(f"Preset '{selected_display_name}' (file: {preset_name_for_loading}.json) selected. Triggering prediction for {len(newly_added_paths)} new paths.")
                if self.prediction_thread and not self.prediction_thread.isRunning():
                    log.debug("Starting prediction thread from add_input_paths.")
                    self.prediction_thread.start()
                for input_path_str in newly_added_paths:
                    file_list = self._extract_file_list(input_path_str)
                    if file_list is not None:
                        log.debug(f"Extracted {len(file_list)} files for {input_path_str}. Emitting signal.")
                        log.info(f"VERIFY: Extracted file list for '{input_path_str}'. Count: {len(file_list)}. Emitting prediction signal.")
                        self._source_file_lists[input_path_str] = file_list
                        self._pending_predictions.add(input_path_str)
                        log.debug(f"Added '{input_path_str}' to pending predictions. Current pending: {self._pending_predictions}")
                        # Pass the filename stem for loading, not the display name
                        self.start_prediction_signal.emit(input_path_str, file_list, preset_name_for_loading)
                    else:
                        log.warning(f"Skipping prediction for {input_path_str} due to extraction error.")
            elif mode == "placeholder":
                log.info(f"Added {added_count} asset(s) while placeholder selected. Adding directories with file contents to view.")
                rules_to_add = []
                for input_path_str in newly_added_paths:
                    input_path = Path(input_path_str)
                    if input_path.is_dir():
                        log.debug(f"Processing directory in placeholder mode: {input_path_str}")
                        file_rules = []
                        try:
                            for item_name in os.listdir(input_path):
                                item_path = input_path / item_name
                                if item_path.is_file():
                                    relative_path = item_name
                                    file_rules.append(FileRule(file_path=relative_path, map_type=""))
                                    log.debug(f"  Found file: {relative_path}")
                        except OSError as e:
                            log.warning(f"Could not list directory contents for {input_path_str}: {e}")
                            # Optionally add the directory itself even if listing fails
                            continue

                        dummy_asset = AssetRule(asset_name="", asset_type="", files=file_rules)
                        source_rule = SourceRule(input_path=input_path_str, assets=[dummy_asset])
                        rules_to_add.append(source_rule)
                        log.debug(f"Created SourceRule with {len(file_rules)} child files for directory: {input_path_str}")

                    elif input_path.is_file() and input_path.suffix.lower() == '.zip':
                        log.debug(f"Processing zip file in placeholder mode (inspecting contents): {input_path_str}")
                        file_rules = []
                        try:
                            if not zipfile.is_zipfile(input_path):
                                log.warning(f"File is not a valid zip archive: {input_path_str}")
                                self.statusBar().showMessage(f"Warning: Not a valid zip: {input_path.name}", 5000)
                                continue

                            with zipfile.ZipFile(input_path, 'r') as zip_ref:
                                for name in zip_ref.namelist():
                                    # Filter out directory entries explicitly marked with '/'
                                    if not name.endswith('/'):
                                        file_rules.append(FileRule(file_path=name))
                                        log.debug(f"  Found file in zip: {name}")

                            # This structure allows the UnifiedViewModel to display it hierarchically
                            dummy_asset = AssetRule(asset_name="", asset_type="", files=file_rules)
                            source_rule = SourceRule(input_path=input_path_str, assets=[dummy_asset])
                            rules_to_add.append(source_rule)
                            log.debug(f"Created SourceRule with {len(file_rules)} child files for zip archive: {input_path_str}")

                        except zipfile.BadZipFile:
                            log.error(f"Bad zip file encountered: {input_path_str}")
                            self.statusBar().showMessage(f"Error: Invalid zip file: {input_path.name}", 5000)
                            continue
                        except FileNotFoundError: # Should ideally not happen due to earlier checks
                            log.error(f"File not found during zip processing: {input_path_str}")
                            self.statusBar().showMessage(f"Error: Input not found: {input_path.name}", 5000)
                            continue
                        except PermissionError:
                            log.error(f"Permission denied accessing zip: {input_path_str}")
                            self.statusBar().showMessage(f"Error: Permission denied for: {input_path.name}", 5000)
                            continue
                        except Exception as e:
                            log.exception(f"Unexpected error processing zip file {input_path_str}: {e}")
                            self.statusBar().showMessage(f"Error reading zip: {input_path.name}", 5000)
                            continue
                    else:
                        # This case should ideally not be reached due to earlier checks, but log just in case
                        log.warning(f"Skipping unexpected item type in placeholder mode: {input_path_str}")

                if rules_to_add:
                    try:
                        log.info(f"Updating model with {len(rules_to_add)} SourceRules (placeholder mode with directory contents).")
                        self.unified_model.update_rules_for_sources(rules_to_add)
                        if hasattr(self, 'main_panel_widget'):
                            self.main_panel_widget.unified_view.expandToDepth(1)
                        self.statusBar().showMessage(f"Added {len(rules_to_add)} item(s) to view. Select preset/LLM for details.", 3000)
                    except Exception as e:
                        log.exception(f"Error updating model with placeholder rules: {e}")
                        self.statusBar().showMessage(f"Error adding items to view: {e}", 5000)
                else:
                     # This might happen if only non-dir/zip items were added or directory listing failed for all
                     self.statusBar().showMessage(f"Added {added_count} input(s), but no valid items to display in placeholder mode.", 5000)

            else:
                log.error(f"Added {added_count} asset(s), but encountered unexpected preset mode: {mode}. Prediction not triggered.")
                self.statusBar().showMessage(f"Added {added_count} asset(s). Error determining preset mode.", 3000)

            # The preview update is now triggered per-item via the signal emission above,
            # and also when the preset selection changes (handled in update_preview).


    # --- Slots for Handling Requests from MainPanelWidget ---

    @Slot(dict)
    def _on_process_requested(self, settings: dict):
        """Handles the process_requested signal from the MainPanelWidget."""
        log.info(f"Received process request signal with settings: {settings}")

        if not hasattr(self, 'current_asset_paths') or not self.current_asset_paths:
            self.statusBar().showMessage("No assets added to process.", 3000)
            return

        # mode, selected_preset_name, preset_file_path are relevant here if processing depends on the *loaded* preset's config
        # For now, _on_process_requested uses the rules already in unified_model, which should have been generated
        # using the correct preset context. The preset name itself isn't directly used by the processing engine,
        # as the SourceRule object already contains the necessary preset-derived information or the preset name string.
        # We'll rely on the SourceRule objects in unified_model.get_all_source_rules() to be correct.
        # mode, selected_display_name, preset_file_path = self.preset_editor_widget.get_selected_preset_mode()


        output_dir_str = settings.get("output_dir")
        if not output_dir_str:
            self.statusBar().showMessage("Error: Output directory cannot be empty.", 5000)
            log.error("Start processing failed: Output directory field is empty.")
            return
        try:
            output_dir = Path(output_dir_str)
            output_dir.mkdir(parents=True, exist_ok=True)
            temp_file = output_dir / f".writable_check_{time.time()}"
            temp_file.touch()
            temp_file.unlink()
            log.info(f"Using validated output directory: {output_dir_str}")
            self._current_output_dir = output_dir_str
        except OSError as e:
            error_msg = f"Error creating/accessing output directory '{output_dir_str}': {e}"
            self.statusBar().showMessage(error_msg, 5000)
            log.error(error_msg)
            return
        except Exception as e:
            error_msg = f"Invalid output directory path '{output_dir_str}': {e}"
            self.statusBar().showMessage(error_msg, 5000)
            log.error(error_msg)
            return

        try:
            final_source_rules = self.unified_model.get_all_source_rules()
            if not final_source_rules:
                log.warning("No source rules found in the model. Nothing to process.")
                self.statusBar().showMessage("No rules generated or assets added. Nothing to process.", 3000)
                return
        except AttributeError:
            log.error("UnifiedViewModel does not have 'get_all_source_rules()' method.")
            self.statusBar().showMessage("Error: Cannot retrieve rules from model.", 5000)
            return
        except Exception as e:
            log.exception(f"Error getting rules from model: {e}")
            self.statusBar().showMessage(f"Error retrieving rules: {e}", 5000)
            return

        log.info(f"Retrieved {len(final_source_rules)} SourceRule objects from the model.")

        filtered_source_rules = []
        for source_rule in final_source_rules:
            has_valid_target = False
            if hasattr(source_rule, 'assets') and source_rule.assets:
                for asset_rule in source_rule.assets:
                    # Check if asset_name (Target Asset) is not None and not empty/whitespace
                    if asset_rule.asset_name and asset_rule.asset_name.strip():
                        has_valid_target = True
                        # Found one valid target, no need to check others in this source
                        break
            if has_valid_target:
                filtered_source_rules.append(source_rule)
            else:
                log.info(f"Filtering out SourceRule '{source_rule.input_path}' as it has no assets with a Target Asset name.")

        if not filtered_source_rules:
            log.warning("All SourceRules were filtered out. No items have a valid Target Asset. Nothing to process.")
            self.statusBar().showMessage("No items have a Target Asset assigned. Nothing to process.", 5000)
            self.set_controls_enabled(True)
            self.main_panel_widget.set_start_button_text("Start Processing")
            self.main_panel_widget.set_cancel_button_enabled(False)
            self.main_panel_widget.set_progress_bar_text("Idle")
            return

        log.info(f"Processing {len(filtered_source_rules)} SourceRule objects after filtering (originally {len(final_source_rules)}).")

        self.main_panel_widget.set_progress_bar_text("Waiting for processing start...")
        self.statusBar().showMessage(f"Requested processing for {len(filtered_source_rules)} rule sets...", 0)
        self.set_controls_enabled(False)
        self.main_panel_widget.set_start_button_enabled(False)
        self.main_panel_widget.set_start_button_text("Processing...")
        self.main_panel_widget.set_cancel_button_enabled(True)

        processing_data = {
            "output_dir": output_dir_str,
            "overwrite": settings.get("overwrite", False),
            "workers": settings.get("workers", 1),
            "blender_enabled": settings.get("blender_enabled", False),
            "nodegroup_blend_path": settings.get("nodegroup_blend_path", ""),
            "materials_blend_path": settings.get("materials_blend_path", "")
        }
        log.info(f"Emitting start_backend_processing with {len(filtered_source_rules)} rules and settings: {processing_data}")
        self.start_backend_processing.emit(filtered_source_rules, processing_data)

    @Slot()
    def _on_cancel_requested(self):
        """Handles the cancel_requested signal from the MainPanelWidget."""
        # TODO: Implement cancellation by signaling the App/main thread to stop the QThreadPool tasks
        log.warning("Cancel requested, but cancellation logic needs reimplementation in main application.")
        self.statusBar().showMessage("Cancellation request sent (implementation pending).", 3000)
        # Optionally, re-enable controls immediately or wait for confirmation

    @Slot()
    def _on_clear_queue_requested(self):
        """Handles the clear_queue_requested signal from the MainPanelWidget."""
        # TODO: Check processing state via App/main thread if needed before clearing

        if hasattr(self, 'current_asset_paths') and self.current_asset_paths:
            log.info(f"Clearing asset queue ({len(self.current_asset_paths)} items).")
            self.current_asset_paths.clear()
            self.unified_model.clear_data()
            if hasattr(self, 'main_panel_widget'):
                self.main_panel_widget.set_start_button_enabled(False)
            self._pending_predictions.clear()
            self._accumulated_rules.clear()
            self._source_file_lists.clear()
            self.llm_interaction_handler.clear_queue()
            log.info("Cleared accumulation state and delegated LLM queue clear.")
            self.statusBar().showMessage("Asset queue and prediction state cleared.", 3000)
            self.main_panel_widget.set_progress_bar_text("Idle")
        else:
            self.statusBar().showMessage("Asset queue is already empty.", 3000)

    @Slot(list)
    def _delegate_llm_reinterpret(self, source_paths: list):
        """
        Slot to receive the llm_reinterpret_requested signal from MainPanelWidget
        and delegate the request to the LLMInteractionHandler.
        """
        log.info(f"Received LLM re-interpret request for {len(source_paths)} paths. Delegating to handler.")

        if not source_paths:
            self.statusBar().showMessage("No valid source directories selected for re-interpretation.", 5000)
            return

        # Check handler status before queueing (optional, handler manages internally)
        if self.llm_interaction_handler.is_processing():
             QMessageBox.warning(self, "Busy", "LLM interpretation is already in progress. Request added to queue.")
             # Proceed to queue anyway, handler manages the queue

        requests = [(path, None) for path in source_paths]

        self.llm_interaction_handler.queue_llm_requests_batch(requests)
        # Status updates (like "Added X directories to queue") will come from the handler via signals

    @Slot(str)
    def _on_output_dir_changed(self, path: str):
        """Stores the output directory path when it changes in the panel."""
        self._current_output_dir = path
        log.debug(f"MainWindow stored output directory: {path}")

    @Slot(bool, str, str)
    def _on_blender_settings_changed(self, enabled: bool, ng_path: str, mat_path: str):
        """Stores the Blender settings when they change in the panel."""
        self._current_blender_settings = {
            "enabled": enabled,
            "nodegroup_blend_path": ng_path,
            "materials_blend_path": mat_path
        }
        log.debug(f"MainWindow stored Blender settings: {self._current_blender_settings}")
    @Slot(list, str)
    def _on_preset_reinterpret_requested(self, source_paths: list, preset_name: str):
        """Handles the preset_reinterpret_requested signal from MainPanelWidget."""
        log.info(f"Received preset re-interpret request for {len(source_paths)} paths using preset '{preset_name}'.")

        if not source_paths:
            self.statusBar().showMessage("No valid source directories selected for preset re-interpretation.", 5000)
            return

        # Check if rule-based prediction is already running (optional, handler might manage internally)
        # Note: QueuedConnection on the signal helps, but check anyway for immediate feedback/logging
        # TODO: Add is_running() method to RuleBasedPredictionHandler if needed for this check - NOTE: is_running is a property now
        if self.prediction_handler and hasattr(self.prediction_handler, 'is_running') and self.prediction_handler.is_running:
             log.warning("Rule-based prediction is already running. Queuing re-interpretation request.")
             # Proceed, relying on QueuedConnection

        if self.prediction_thread and not self.prediction_thread.isRunning():
            log.debug("Starting prediction thread for preset re-interpretation.")
            self.prediction_thread.start()
        elif not self.prediction_thread:
             log.error("Prediction thread not initialized. Cannot perform preset re-interpretation.")
             self.statusBar().showMessage("Error: Prediction system not ready.", 5000)
             return


        self.statusBar().showMessage(f"Starting re-interpretation for {len(source_paths)} item(s) using preset '{preset_name}'...", 0)
        for input_path_str in source_paths:
            self._pending_predictions.add(input_path_str)
            self._completed_predictions.discard(input_path_str)

            # Update status in model (Requires update_status method in UnifiedViewModel)
            try:
                if hasattr(self.unified_model, 'update_status'):
                    self.unified_model.update_status(input_path_str, "Re-interpreting...")
                else:
                    log.warning("UnifiedViewModel does not have 'update_status' method. Cannot update status visually.")
            except Exception as e:
                log.exception(f"Error calling unified_model.update_status for {input_path_str}: {e}")


            file_list = self._extract_file_list(input_path_str)
            if file_list is not None:
                log.debug(f"Emitting start_prediction_signal for re-interpretation: Path='{input_path_str}', Preset='{preset_name}'")
                self.start_prediction_signal.emit(input_path_str, file_list, preset_name)
            else:
                log.warning(f"Skipping re-interpretation for {input_path_str} due to extraction error.")
                # Update status in model to reflect error (Requires update_status method)
                try:
                    if hasattr(self.unified_model, 'update_status'):
                        self.unified_model.update_status(input_path_str, "Error extracting files")
                    else:
                        log.warning("UnifiedViewModel does not have 'update_status' method. Cannot update error status visually.")
                except Exception as e:
                    log.exception(f"Error calling unified_model.update_status (error case) for {input_path_str}: {e}")

                self._handle_prediction_completion(input_path_str)

    def update_preview(self):
        log.info(f"--> Entered update_preview. View Action exists: {hasattr(self, 'toggle_preview_action')}")
        log.debug(f"[{time.time():.4f}] ### LOG: Entering update_preview")
        log.debug("--> Entered update_preview")
        thread_id = QThread.currentThread()
        log.info(f"[{time.time():.4f}][T:{thread_id}] --> Entered update_preview. View Action exists: {hasattr(self, 'toggle_preview_action')}")
        if hasattr(self, 'toggle_preview_action'):
             log.info(f"[{time.time():.4f}][T:{thread_id}]     Disable Preview Action checked: {self.toggle_preview_action.isChecked()}")


        if self.prediction_handler and self.prediction_handler.is_running:
            log.warning(f"[{time.time():.4f}][T:{thread_id}] Prediction is running. Attempting to call prediction_handler.request_cancel()...")
            try:
                # --- THIS METHOD DOES NOT EXIST IN PredictionHandler ---
                self.prediction_handler.request_cancel()
                log.info(f"[{time.time():.4f}][T:{thread_id}]     Called prediction_handler.request_cancel() (Method might be missing!).")
            except AttributeError as e:
                log.error(f"[{time.time():.4f}][T:{thread_id}]     AttributeError calling prediction_handler.request_cancel(): {e}. Prediction cannot be cancelled.")
            except Exception as e:
                 log.exception(f"[{time.time():.4f}][T:{thread_id}]     Unexpected error calling prediction_handler.request_cancel(): {e}")
            # Note: Cancellation is not immediate even if it existed. The thread would stop when it next checks the flag.
            # We proceed with updating the UI immediately.


        log.debug(f"[{time.time():.4f}] ### LOG: Checking if prediction handler is running")
        if self.prediction_handler and self.prediction_handler.is_running:
            log.warning(f"[{time.time():.4f}] Preview update requested, but already running.")
            log.debug(f"[{time.time():.4f}] ### LOG: Inside 'is_running' check")
            # Removed the 'return' statement here to allow the signal to be emitted
        # The rest of the logic should execute regardless of is_running state,
        # though the handler itself should handle being called multiple times.
        # A better fix might involve properly resetting is_running in the handler.

        if RuleBasedPredictionHandler is None:
                log.error("RuleBasedPredictionHandler not loaded. Cannot update preview.")
                self.statusBar().showMessage("Error: Prediction components not loaded.", 5000)
                return
        mode, selected_display_name, preset_file_path = self.preset_editor_widget.get_selected_preset_mode()

        if mode == "placeholder":
            log.debug("Update preview called with placeholder preset selected. Showing existing raw inputs (detailed view).")
            # Model is always detailed now, no need to set simple mode
            # Don't clear data here, _on_preset_selection_changed handles mode switch,
            # and add_input_paths handles adding raw data if needed.
            # If current_asset_paths is empty, the view will be empty anyway.
            if not self.current_asset_paths:
                self.unified_model.clear_data()

            self.statusBar().showMessage("Select a preset or LLM to generate preview.", 3000)
            return

        if not hasattr(self, 'current_asset_paths') or not self.current_asset_paths:
            log.debug("Update preview called with no assets tracked.")
            self.unified_model.clear_data()
            return
        input_paths = list(self.current_asset_paths)

        if mode == "llm":
            log.info(f"[{time.time():.4f}] LLM mode selected. Preparing LLM prediction for {len(input_paths)} assets.")
            self.statusBar().showMessage(f"Starting LLM interpretation for assets...", 0)
            log.debug("Clearing accumulated rules and pending predictions for LLM batch.")
            self._accumulated_rules.clear()
            self._pending_predictions = set(input_paths)
            self._completed_predictions.clear()
            log.debug(f"Reset pending predictions for LLM batch: {self._pending_predictions}")

            llm_requests_to_queue = []
            if input_paths:
                log.info(f"Preparing LLM prediction requests for {len(input_paths)} existing assets.")
                for input_path_str in input_paths:
                    # Duplication check is handled by the handler's queue method
                    file_list = self._extract_file_list(input_path_str)
                    if file_list is not None:
                        log.debug(f"Extracted {len(file_list)} files for LLM prediction from existing asset: {input_path_str}")
                        # Store file list (still needed for context if prediction fails before handler starts?)
                        self._source_file_lists[input_path_str] = file_list
                        llm_requests_to_queue.append((input_path_str, file_list))
                    else:
                        log.warning(f"Skipping LLM prediction queuing for existing asset {input_path_str} due to extraction error.")
                        self._pending_predictions.discard(input_path_str)
                        self.statusBar().showMessage(f"Error extracting files for {Path(input_path_str).name}", 5000)
            else:
                 log.warning("LLM selected, but no input paths currently in view to process.")
                 self.statusBar().showMessage("LLM selected, but no assets are loaded.", 3000)

            if llm_requests_to_queue:
                log.info(f"Delegating {len(llm_requests_to_queue)} LLM requests to the handler from update_preview.")
                self.llm_interaction_handler.queue_llm_requests_batch(llm_requests_to_queue)
            # The handler manages starting its own processing internally.
            # Do not return here; let the function exit normally after handling LLM case.
            # The standard prediction path below will be skipped because mode is 'llm'.

        elif mode == "preset" and selected_display_name and preset_file_path:
            preset_name_for_loading = preset_file_path.stem
            log.info(f"[{time.time():.4f}] Requesting background preview update for {len(input_paths)} items using Preset Display='{selected_display_name}' (File Stem='{preset_name_for_loading}')")
            self.statusBar().showMessage(f"Updating preview for '{selected_display_name}'...", 0)

            log.debug("Clearing accumulated rules for new standard preview batch.")
            self._accumulated_rules.clear()
            self._pending_predictions = set(input_paths)
            log.debug(f"Reset pending standard predictions for batch: {self._pending_predictions}")

            if self.prediction_thread and self.prediction_handler:
                self.prediction_thread.start()
                log.debug(f"[{time.time():.4f}] Iterating through {len(input_paths)} paths to extract files and emit standard prediction signals.")
                for input_path_str in input_paths:
                    file_list = self._extract_file_list(input_path_str)
                    if file_list is not None:
                        log.debug(f"[{time.time():.4f}] Emitting start_prediction_signal for: {input_path_str} with {len(file_list)} files, using preset file stem: {preset_name_for_loading}.")
                        self.start_prediction_signal.emit(input_path_str, file_list, preset_name_for_loading) # Pass stem for loading
                    else:
                        log.warning(f"[{time.time():.4f}] Skipping standard prediction signal for {input_path_str} due to extraction error.")
            else:
                log.error(f"[{time.time():.4f}][T:{thread_id}] Failed to trigger standard prediction: Thread or handler not initialized.")
                self.statusBar().showMessage("Error: Failed to initialize standard prediction thread.", 5000)

        log.info(f"[{time.time():.4f}][T:{thread_id}] <-- Exiting update_preview.")


    def setup_threads(self):

        if RuleBasedPredictionHandler and self.prediction_thread is None:
            self.prediction_thread = QThread(self)
            self.prediction_handler = RuleBasedPredictionHandler(input_source_identifier="", original_input_paths=[], preset_name="")
            self.prediction_handler.moveToThread(self.prediction_thread)

            self.start_prediction_signal.connect(self.prediction_handler.run_prediction, Qt.ConnectionType.QueuedConnection)

            self.prediction_handler.prediction_ready.connect(self._on_rule_hierarchy_ready)
            self.prediction_handler.prediction_error.connect(self._on_prediction_error)
            self.prediction_handler.status_update.connect(self.show_status_message)

            # Keep thread alive (no automatic quit/deleteLater for persistent handler)
            log.debug("Rule-Based Prediction thread and handler set up to be persistent.")
            self.prediction_thread.start()
        elif not RuleBasedPredictionHandler:
             log.error("RuleBasedPredictionHandler not available. Cannot set up prediction thread.")

        # LLM Thread setup is now handled internally by LLMInteractionHandler


    @Slot()
    def _reset_prediction_thread_references(self):
        # This slot is no longer connected, but keep it for now in case needed later
        log.debug("Resetting prediction thread and handler references (Slot disconnected).")


    @Slot(int, int)
    def update_progress_bar(self, current_count, total_count):
        if hasattr(self, 'main_panel_widget'):
            self.main_panel_widget.update_progress_bar(current_count, total_count)


    # Completion is handled by _on_rule_hierarchy_ready or _on_prediction_error
    @Slot(str, str, str)
    def update_file_status(self, input_path_str, status, message):
        # TODO: Update status bar or potentially find rows in table later
        status_text = f"Asset '{Path(input_path_str).name}': {status.upper()}"
        if status == "failed" and message: status_text += f" - Error: {message}"
        self.statusBar().showMessage(status_text, 5000)
        log.debug(f"Received file status update: {input_path_str} - {status}")

    # TODO: This slot needs to be connected to a signal from the App/main thread
    # indicating that all tasks in the QThreadPool are complete.
    @Slot(int, int, int)
    def on_processing_finished(self, processed_count, skipped_count, failed_count):
        # This log message might be inaccurate until signal source is updated
        log.info(f"GUI received processing_finished signal: P={processed_count}, S={skipped_count}, F={failed_count}")
        self.set_controls_enabled(True)
        self.main_panel_widget.set_cancel_button_enabled(False)
        self.main_panel_widget.set_start_button_text("Start Processing")
        # Start button enabled state depends on preset mode, handled by _on_preset_selection_changed or set_controls_enabled
        self.main_panel_widget.set_progress_bar_text(f"Finished: {processed_count} processed, {skipped_count} skipped, {failed_count} failed.")

    # Signature changed: Base class signal only emits message string
    @Slot(str)
    def show_status_message(self, message):
        # Show message indefinitely until replaced
        self.statusBar().showMessage(message)

    def set_controls_enabled(self, enabled: bool):
        """Enables/disables input controls in relevant panels during processing."""
        self.setAcceptDrops(enabled)
        self.preset_editor_widget.setEnabled(enabled)
        if hasattr(self, 'main_panel_widget'):
            self.main_panel_widget.set_controls_enabled(enabled)
            if enabled:
                model_has_items = self.unified_model.rowCount() > 0
                self.main_panel_widget.set_start_button_enabled(model_has_items)
            else:
                self.main_panel_widget.set_start_button_enabled(False)


    def setup_menu_bar(self):
        """Creates the main menu bar and adds menus/actions."""
        self.menu_bar = self.menuBar()

        # --- File Menu (Optional, add if needed later) ---
        # file_menu = self.menu_bar.addMenu("&File")
        # Add actions like New, Open, Save, Exit

        edit_menu = self.menu_bar.addMenu("&Edit")

        self.preferences_action = QAction("&Preferences...", self)
        self.preferences_action.triggered.connect(self._open_config_editor)
        edit_menu.addAction(self.preferences_action)
        edit_menu.addSeparator()

        self.definitions_editor_action = QAction("Edit Definitions...", self)
        self.definitions_editor_action.triggered.connect(self._open_definitions_editor)
        edit_menu.addAction(self.definitions_editor_action)

        view_menu = self.menu_bar.addMenu("&View")

        self.toggle_log_action = QAction("Show Log Console", self, checkable=True)
        self.toggle_log_action.setChecked(False)
        self.toggle_log_action.toggled.connect(self._toggle_log_console_visibility)
        view_menu.addAction(self.toggle_log_action)


        self.toggle_verbose_action = QAction("Verbose Logging (DEBUG)", self, checkable=True)
        self.toggle_verbose_action.setChecked(False)
        self.toggle_verbose_action.toggled.connect(self._toggle_verbose_logging)
        view_menu.addAction(self.toggle_verbose_action)

    def setup_logging_handler(self):
        """Creates and configures the custom QtLogHandler."""
        self.log_handler = QtLogHandler(self)
        log_format = '%(levelname)s: %(message)s'
        formatter = logging.Formatter(log_format)
        self.log_handler.setFormatter(formatter)
        self.log_handler.setLevel(logging.INFO)
        # Add handler to the root logger to capture logs from all modules
        logging.getLogger().addHandler(self.log_handler)
        self.log_handler.log_record_received.connect(self.log_console._append_log_message)
        log.info("UI Log Handler Initialized.")

    @Slot()
    def _open_config_editor(self):
        """Opens the configuration editor dialog."""
        log.debug("Opening configuration editor dialog.")
        try:
            # Import locally to avoid circular dependency if needed
            from .config_editor_dialog import ConfigEditorDialog
            dialog = ConfigEditorDialog(self)
            dialog.exec_()
            log.debug("Configuration editor dialog closed.")
        except ImportError:
            log.error("Failed to import ConfigEditorDialog. Ensure gui/config_editor_dialog.py exists and is accessible.")
            QMessageBox.critical(self, "Error", "Could not open configuration editor.\nRequired file not found or has errors.")
        except Exception as e:
            log.exception(f"Error opening configuration editor dialog: {e}")
            QMessageBox.critical(self, "Error", f"An error occurred while opening the configuration editor:\n{e}")

    @Slot() # PySide6.QtCore.Slot
    def _open_definitions_editor(self):
        log.debug("Opening Definitions Editor dialog.")
        try:
            # DefinitionsEditorDialog is imported at the top of the file
            dialog = DefinitionsEditorDialog(self)
            dialog.exec_() # Use exec_() for modal dialog
            log.debug("Definitions Editor dialog closed.")
        except Exception as e:
            log.exception(f"Error opening Definitions Editor dialog: {e}")
            QMessageBox.critical(self, "Error", f"An error occurred while opening the Definitions Editor:\n{e}")

    @Slot(bool)
    def _toggle_log_console_visibility(self, checked):
        """Shows or hides the log console widget."""
        if hasattr(self, 'log_console'):
            self.log_console.setVisible(checked)
            log.debug(f"Log console visibility set to: {checked}")
        else:
            log.warning("Attempted to toggle log console visibility, but widget not found.")


    @Slot(bool)
    def _toggle_verbose_logging(self, checked):
        """Sets the logging level for the root logger and the GUI handler."""
        if not hasattr(self, 'log_handler'):
            log.error("Log handler not initialized, cannot change level.")
            return

        new_level = logging.DEBUG if checked else logging.INFO
        root_logger = logging.getLogger()
        root_logger.setLevel(new_level)
        self.log_handler.setLevel(new_level)
        log.info(f"Root and GUI logging level set to: {logging.getLevelName(new_level)}")
        self.statusBar().showMessage(f"Logging level set to {logging.getLevelName(new_level)}", 3000)


    def closeEvent(self, event):
        """Overrides close event to check for unsaved changes in the editor widget."""
        if self.preset_editor_widget.check_unsaved_changes():
            event.ignore()
        else:
            event.accept()


    # Slot signature updated to match BasePredictionHandler.prediction_ready: Signal(str, list)
    @Slot(str, list)
    def _on_rule_hierarchy_ready(self, input_path: str, source_rules_list: list):
        """
        Receives rule-based prediction results (a list containing one SourceRule)
        for a single input path, updates the model preserving overrides,
        and handles completion tracking.
        """
        log.debug(f"--> Entered _on_rule_hierarchy_ready for '{input_path}'")

        if not input_path:
            log.error("Received rule hierarchy ready signal with empty input_path. Cannot process.")
            return

        if input_path not in self._pending_predictions:
            log.warning(f"Received rule hierarchy for '{input_path}', but it was not in the pending set. Ignoring stale result? Pending: {self._pending_predictions}")
            return

        if source_rules_list:
            try:
                log.info(f"Updating model with rule-based results for source: {input_path}")
                log.debug(f"DEBUG: Type of self.unified_model: {type(self.unified_model)}")
                log.debug(f"DEBUG: hasattr(self.unified_model, 'update_rules_for_sources'): {hasattr(self.unified_model, 'update_rules_for_sources')}")
                self.unified_model.update_rules_for_sources(source_rules_list)
                log.info("Model update call successful.")
                if hasattr(self, 'main_panel_widget'):
                    self.main_panel_widget.unified_view.expandToDepth(1)
            except Exception as e:
                error_msg = f"Error updating model with rule-based results for {input_path}: {e}"
                log.exception(error_msg)
                self.statusBar().showMessage(error_msg, 8000)
                # Fall through to completion handling even if model update fails
        else:
            log.warning(f"Received empty source_rules_list for '{input_path}'. Prediction likely failed. Model not updated.")

        self._handle_prediction_completion(input_path)

    # Replaced by _on_llm_prediction_ready_from_handler

    # Errors now connect to _on_prediction_error

    @Slot(str, list)
    def _on_llm_prediction_ready_from_handler(self, input_path: str, source_rules: list):
        """
        Handles the successful LLM prediction result received from LLMInteractionHandler.
        Updates the model and handles completion tracking.
        """
        log.info(f"Received LLM prediction result from handler for {input_path}. {len(source_rules)} source rule(s) found.")

        if source_rules:
            try:
                log.info(f"Updating model with LLM results for source: {input_path}")
                self.unified_model.update_rules_for_sources(source_rules)
                log.info("Model update call successful.")
                if hasattr(self, 'main_panel_widget'):
                    self.main_panel_widget.unified_view.expandToDepth(1)
            except Exception as e:
                error_msg = f"Error updating model with LLM results for {input_path}: {e}"
                log.exception(error_msg)
                self.statusBar().showMessage(error_msg, 8000)
                # Fall through to completion handling even if model update fails
        else:
            log.info(f"No source rules returned by LLM handler for {input_path}. Model not updated.")

        self._handle_prediction_completion(input_path)

    @Slot(str, str)
    def _on_prediction_error(self, input_path: str, error_message: str):
        """Handles errors reported by any prediction handler (RuleBased or LLM)."""
        log.error(f"Prediction Error for '{input_path}': {error_message}")
        self.statusBar().showMessage(f"Error analyzing {Path(input_path).name}: {error_message}", 8000)

        self._handle_prediction_completion(input_path)

    def _handle_prediction_completion(self, input_path: str):
        """
        Centralized method to handle completion tracking for both successful
        predictions and errors for a given input path.
        """
        log.debug(f"--> Entered _handle_prediction_completion for '{input_path}'")

        if input_path in self._pending_predictions:
            self._pending_predictions.discard(input_path)
            self._completed_predictions.add(input_path)
            log.debug(f"Marked '{input_path}' as completed. Pending: {len(self._pending_predictions)}, Completed: {len(self._completed_predictions)}")

            if not self._pending_predictions:
                log.info("All pending predictions processed. Model should be up-to-date.")
                self.statusBar().showMessage(f"Preview generation complete.", 5000)
                if hasattr(self, 'main_panel_widget'):
                    self.main_panel_widget.set_start_button_enabled(self.unified_model.rowCount() > 0)
                # Optional: Resize columns after all updates are done (Access view via panel)
                if hasattr(self, 'main_panel_widget'):
                    view = self.main_panel_widget.unified_view
                    for col in range(self.unified_model.columnCount()):
                        view.resizeColumnToContents(col)
                    view.expandToDepth(1)
            else:
                completed_count = len(self._completed_predictions)
                pending_count = len(self._pending_predictions)
                # Estimate total based on initial request size (might be slightly off if items were added/removed)
                total_requested = completed_count + pending_count
                status_msg = f"Preview updated for {Path(input_path).name}. Waiting for {pending_count} more ({completed_count}/{total_requested} processed)..."
                self.statusBar().showMessage(status_msg, 5000)
                log.debug(status_msg)
        else:
            log.warning(f"Received completion signal for '{input_path}', but it was not in the pending set. Ignoring?")

        log.debug(f"<-- Exiting _handle_prediction_completion for '{input_path}'")


    @Slot(str, str, Path) # mode, display_name, file_path (Path can be None)
    def _on_preset_selection_changed(self, mode: str, display_name: str | None, file_path: Path | None ):
        """
        Handles changes in the preset editor selection (preset, LLM, placeholder).
        Switches between PresetEditorWidget and LLMEditorWidget.
        """
        log.info(f"Preset selection changed: mode='{mode}', display_name='{display_name}', file_path='{file_path}'")

        if mode == "llm":
            log.debug("Switching editor stack to LLM Editor Widget.")
            # Force reset the LLM handler state in case it got stuck
            if hasattr(self, 'llm_interaction_handler'):
                self.llm_interaction_handler.force_reset_state()
            self.editor_stack.setCurrentWidget(self.llm_editor_widget)
            # Load settings *after* switching the stack
            try:
                self.llm_editor_widget.load_settings()
            except Exception as e:
                log.exception(f"Error loading LLM settings in _on_preset_selection_changed: {e}")
                QMessageBox.critical(self, "LLM Settings Error", f"Failed to load LLM settings:\n{e}")
        elif mode == "preset":
            log.debug("Switching editor stack to Preset JSON Editor Widget.")
            self.editor_stack.setCurrentWidget(self.preset_editor_widget.json_editor_container)
        else:
            log.debug("Switching editor stack to Preset JSON Editor Widget (placeholder selected).")
            self.editor_stack.setCurrentWidget(self.preset_editor_widget.json_editor_container)
            # The PresetEditorWidget's internal logic handles disabling/clearing the editor fields.

        if mode == "preset" and display_name: # Use display_name for window title
            # This might be redundant if the editor handles its own title updates on save/load
            # but good for consistency.
            unsaved = self.preset_editor_widget.editor_unsaved_changes
            self.setWindowTitle(f"Asset Processor Tool - {display_name}{'*' if unsaved else ''}")
        elif mode == "llm":
            self.setWindowTitle("Asset Processor Tool - LLM Interpretation")
        else:
            self.setWindowTitle("Asset Processor Tool")

        if hasattr(self, 'main_panel_widget'):
            model_has_items = self.unified_model.rowCount() > 0
            self.main_panel_widget.set_start_button_enabled(model_has_items)
            self.main_panel_widget.set_llm_processing_status(self.llm_interaction_handler.is_processing())

        # Display mode is always detailed, no need to set it here
        # update_preview will now respect the mode set above
        self.update_preview()

    @Slot()
    def _on_llm_settings_saved(self):
        """Slot called when LLM settings are saved successfully."""
        log.info("LLM settings saved signal received by MainWindow.")
        self.statusBar().showMessage("LLM settings saved successfully.", 3000)
        # Optionally, trigger a reload of configuration if needed elsewhere,
        # or update the LLMInteractionHandler if it caches settings.
        # For now, just show a status message.
        # If the LLM handler uses the config directly, no action needed here.
        # If it caches, we might need: self.llm_interaction_handler.reload_settings()

    @Slot(bool)
    def _on_llm_processing_state_changed(self, is_processing: bool):
        """Updates the UI based on the LLM handler's processing state."""
        log.debug(f"Received LLM processing state change from handler: {is_processing}")
        self.preset_editor_widget.setEnabled(not is_processing)
        if hasattr(self, 'main_panel_widget'):
            self.main_panel_widget.set_llm_processing_status(is_processing)

    # Use self.llm_interaction_handler.is_processing()

    def get_llm_source_preset_name(self) -> str | None:
        """
        Returns the name (stem) of the last valid preset that was loaded
        before switching to LLM mode or triggering re-interpretation.
        Used by delegates to populate dropdowns based on the original context.
        Delegates this call to the PresetEditorWidget.
        """
        if hasattr(self, 'preset_editor_widget'):
            last_name = self.preset_editor_widget.get_last_valid_preset_name()
            log.debug(f"get_llm_source_preset_name called, returning from widget: {last_name}")
            return last_name
        else:
            log.warning("get_llm_source_preset_name called before preset_editor_widget was initialized.")
            return None

    def keyPressEvent(self, event):
        """Handles key press events for implementing keybinds."""
        log.debug(f"KeyPressEvent: key={event.key()}, modifiers={event.modifiers()}, text='{event.text()}'")

        if not self.main_panel_widget or not self.unified_model:
            log.warning("Key press ignored: Main panel or unified model not available.")
            super().keyPressEvent(event)
            return

        selected_view_indexes = self.main_panel_widget.unified_view.selectionModel().selectedIndexes()
        if not selected_view_indexes:
            log.debug("Key press ignored: No items selected.")
            super().keyPressEvent(event)
            return

        # Assuming unified_view uses unified_model directly or proxy maps correctly
        model_indexes_to_process = []
        unique_rows = set()
        for view_idx in selected_view_indexes:
            model_idx = view_idx
            if model_idx.row() not in unique_rows:
                # Ensure we are getting the index for column 0 if multiple columns are selected for the same row
                model_indexes_to_process.append(self.unified_model.index(model_idx.row(), 0, model_idx.parent()))
                unique_rows.add(model_idx.row())
        
        if not model_indexes_to_process:
            super().keyPressEvent(event)
            return

        pressed_key = event.key()
        modifiers = event.modifiers()
        keybind_processed = False

        if pressed_key == Qt.Key_F2 and not modifiers:
            log.debug("F2 pressed for asset name change.")
            first_selected_item_index = model_indexes_to_process[0]
            first_item_object = self.unified_model.getItem(first_selected_item_index)
            current_name_suggestion = ""

            if isinstance(first_item_object, AssetRule):
                # For AssetRule, its name is in COL_NAME (which is first_selected_item_index's column, typically 0)
                # The index itself (first_selected_item_index) can be used as it's for COL_NAME.
                current_name_suggestion = self.unified_model.data(first_selected_item_index, Qt.DisplayRole) or ""
            elif isinstance(first_item_object, FileRule):
                # For FileRule, its target asset name override is in COL_TARGET_ASSET
                target_asset_col_idx = self.unified_model.COL_TARGET_ASSET
                target_asset_index_for_suggestion = first_selected_item_index.siblingAtColumn(target_asset_col_idx)
                current_name_suggestion = self.unified_model.data(target_asset_index_for_suggestion, Qt.DisplayRole) or ""

            new_name_input, ok = QInputDialog.getText(self, "Set Name", "Enter new name for selected items:", QLineEdit.EchoMode.Normal, current_name_suggestion)
            if ok and new_name_input is not None:
                stripped_name = new_name_input.strip()
                if stripped_name:
                    log.info(f"User entered new name: '{stripped_name}' for selected items.")

                    initial_selected_indices = self.main_panel_widget.unified_view.selectedIndexes()
                    objects_to_rename = []
                    # To avoid processing same underlying item multiple times if multiple columns selected
                    processed_rows_for_object_collection = set()

                    for view_idx in initial_selected_indices:
                        model_idx_for_item = self.unified_model.index(view_idx.row(), 0, view_idx.parent())
                        if model_idx_for_item.row() not in processed_rows_for_object_collection:
                            item = self.unified_model.getItem(model_idx_for_item)
                            if isinstance(item, (AssetRule, FileRule)):
                                objects_to_rename.append(item)
                                processed_rows_for_object_collection.add(model_idx_for_item.row())
                            else:
                                log.debug(f"F2 RENAME: Skipping item {item!r} (type: {type(item)}) during object collection as it's not AssetRule or FileRule.")
                    
                    log.debug(f"F2 RENAME: Collected {len(objects_to_rename)} AssetRule/FileRule objects to rename.")

                    successful_renames = 0
                    for item_object in objects_to_rename:
                        current_model_index = self.unified_model.findIndexForItem(item_object)

                        if current_model_index is None or not current_model_index.isValid():
                            item_repr = getattr(item_object, 'asset_name', getattr(item_object, 'file_path', repr(item_object)))
                            log.warning(f"F2 RENAME: Could not find current index for item {item_repr!r}. It might have been moved/deleted unexpectedly. Skipping.")
                            continue

                        target_column = -1
                        item_description_for_log = ""

                        if isinstance(item_object, AssetRule):
                            target_column = self.unified_model.COL_NAME
                            item_description_for_log = f"AssetRule '{item_object.asset_name}'"
                        elif isinstance(item_object, FileRule):
                            target_column = self.unified_model.COL_TARGET_ASSET
                            item_description_for_log = f"FileRule '{Path(item_object.file_path).name}'"
                        
                        if target_column == -1:
                            log.warning(f"F2 RENAME: Unknown item type for {item_object!r}. Cannot determine target column. Skipping.")
                            continue

                        index_to_update_in_column = current_model_index.siblingAtColumn(target_column)
                        
                        log.debug(f"F2 RENAME: Attempting to set new name '{stripped_name}' for {item_description_for_log} at index r={index_to_update_in_column.row()}, c={index_to_update_in_column.column()}")
                        success = self.unified_model.setData(index_to_update_in_column, stripped_name, Qt.EditRole)
                        
                        if success:
                            successful_renames += 1
                            log.info(f"F2 RENAME: Successfully renamed {item_description_for_log} to '{stripped_name}'.")
                        else:
                            log.warning(f"F2 RENAME: Failed to rename {item_description_for_log} to '{stripped_name}'. setData returned False.")

                    self.statusBar().showMessage(f"{successful_renames} item(s) renamed to '{stripped_name}'.", 3000)
                    keybind_processed = True
                else:
                    log.debug("Asset name change aborted: name was empty after stripping.")
            else:
                log.debug("Asset name change cancelled or empty name entered.")
            event.accept()
            return

        if modifiers == Qt.ControlModifier:
            log.debug(f"Ctrl modifier detected with key: {pressed_key}")
            qt_key_sequence_str = QKeySequence(pressed_key).toString()
            if pressed_key in self.qt_key_to_ftd_map:
                target_ftd_keys = self.qt_key_to_ftd_map[pressed_key]
                log.debug(f"Keybind match: Ctrl+{qt_key_sequence_str} maps to FTDs: {target_ftd_keys}")
                if not target_ftd_keys:
                    log.warning(f"No FTDs configured for key Ctrl+{qt_key_sequence_str}")
                    super().keyPressEvent(event)
                    return
                
                for index in model_indexes_to_process:
                    item = self.unified_model.getItem(index)
                    log.debug(f"Processing item for keybind: row={index.row()}, column={index.column()}")
                    log.debug(f"  Item object: {item!r}")
                    log.debug(f"  Item type: {type(item)}")
                    log.debug(f"  Is instance of FileRule: {isinstance(item, FileRule)}")
                    if hasattr(item, '__dict__'):
                        log.debug(f"  Item attributes: {item.__dict__}")

                    if not isinstance(item, FileRule):
                        log.debug(f"Skipping item at row {index.row()} because it's not a FileRule instance (actual type: {type(item)}).")
                        continue

                    item_type_display_index = self.unified_model.index(index.row(), self.unified_model.COL_ITEM_TYPE, index.parent())
                    current_map_type = self.unified_model.data(item_type_display_index, Qt.DisplayRole)
                    log.debug(f"Item at row {index.row()} ({Path(item.file_path).name}), current map_type (DisplayRole): '{current_map_type}'")

                    new_map_type = ""
                    if len(target_ftd_keys) == 1:
                        new_map_type = target_ftd_keys[0]
                        log.debug(f"  Single target FTD: '{new_map_type}'")
                    else:
                        log.debug(f"  Toggle FTDs: {target_ftd_keys}. Current: '{current_map_type}'")
                        try:
                            current_ftd_index = target_ftd_keys.index(current_map_type)
                            next_ftd_index = (current_ftd_index + 1) % len(target_ftd_keys)
                            new_map_type = target_ftd_keys[next_ftd_index]
                            log.debug(f"  Calculated next FTD: '{new_map_type}'")
                        except ValueError:
                            new_map_type = target_ftd_keys[0]
                            log.debug(f"  Current not in toggle list, defaulting to first: '{new_map_type}'")

                    if new_map_type and new_map_type != current_map_type:
                        log.debug(f"  Updating item at row {index.row()} ({Path(item.file_path).name}) from '{current_map_type}' to '{new_map_type}'")
                        item_type_edit_index = self.unified_model.index(index.row(), self.unified_model.COL_ITEM_TYPE, index.parent())
                        success = self.unified_model.setData(item_type_edit_index, new_map_type, Qt.EditRole)
                        log.debug(f"  setData call successful: {success}")
                    elif not new_map_type:
                        log.debug(f"  Skipping update for item at row {index.row()}, new_map_type is empty.")
                    else:
                        log.debug(f"  Skipping update for item at row {index.row()}, new_map_type ('{new_map_type}') is same as current ('{current_map_type}').")
                
                # The model should emit dataChanged for each setData call.
                self.statusBar().showMessage(f"File types updated for selected items.", 3000)
                keybind_processed = True
                event.accept()
                return

        if not keybind_processed:
            log.debug("Key press not handled by custom keybinds, passing to super.")
            super().keyPressEvent(event)


def run_gui():
    """Initializes and runs the Qt application."""
    print("--- Reached run_gui() ---")
    from PySide6.QtGui import QKeySequence

    app = QApplication(sys.argv)

    palette = app.palette()
    grey_color = QColor("#3a3a3a")
    palette.setColor(QPalette.ColorRole.Base, grey_color)
    palette.setColor(QPalette.ColorRole.AlternateBase, grey_color.lighter(110))
    # You might need to experiment with other roles depending on which widgets are affected

    app.setPalette(palette)

    window = MainWindow()
    window.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    run_gui()