# Developer Guide: GUI Internals

This document provides technical details about the implementation of the Graphical User Interface (GUI) for developers.

## Framework

The GUI is built using `PySide6`, which provides Python bindings for the Qt framework.

## Main Window (`gui/main_window.py`)

The `MainWindow` class acts as the central **coordinator** for the GUI application. It is responsible for:

*   Setting up the main application window structure and menu bar, including actions to launch configuration and definition editors.
*   **Layout:** Arranging the main GUI components using a `QSplitter`.
    *   **Left Pane:** Contains the preset selection controls (from `PresetEditorWidget`) permanently displayed at the top. Below this, a `QStackedWidget` switches between the preset JSON editor (also from `PresetEditorWidget`) and the `LLMEditorWidget`.
    *   **Right Pane:** Contains the `MainPanelWidget`.
*   Instantiating and managing the major GUI widgets:
    *   `PresetEditorWidget` (`gui/preset_editor_widget.py`): Provides the preset selector and the JSON editor parts.
    *   `LLMEditorWidget` (`gui/llm_editor_widget.py`): Provides the editor for LLM settings (from `config/llm_settings.json`).
    *   `MainPanelWidget` (`gui/main_panel_widget.py`): Contains the rule hierarchy view and processing controls.
    *   `LogConsoleWidget` (`gui/log_console_widget.py`): Displays application logs.
*   Instantiating key models and handlers:
    *   `UnifiedViewModel` (`gui/unified_view_model.py`): The model for the rule hierarchy view.
    *   `LLMInteractionHandler` (`gui/llm_interaction_handler.py`): Manages communication with the LLM service.
    *   `AssetRestructureHandler` (`gui/asset_restructure_handler.py`): Handles rule restructuring.
*   Connecting signals and slots between these components to orchestrate the application flow.
*   **Editor Switching:** Handling the `preset_selection_changed_signal` from `PresetEditorWidget` in its `_on_preset_selection_changed` slot. This slot:
    *   Switches the `QStackedWidget` (`editor_stack`) to display either the `PresetEditorWidget`'s JSON editor or the `LLMEditorWidget` based on the selected mode ("preset", "llm", "placeholder").
    *   Calls `llm_editor_widget.load_settings()` when switching to LLM mode.
    *   Updates the window title.
    *   Triggers `update_preview()`.
*   Handling top-level user interactions like drag-and-drop for loading sources (`add_input_paths`). This method now handles the "placeholder" state (no preset selected) by scanning directories or inspecting archives (ZIP) and creating placeholder `SourceRule`/`AssetRule`/`FileRule` objects to immediately populate the `UnifiedViewModel` with the file structure.
*   Initiating predictions based on the selected preset mode (Rule-Based or LLM) when presets change or sources are added (`update_preview`).
*   Starting the processing task (`_on_process_requested`): This slot now filters the `SourceRule` list obtained from the `UnifiedViewModel`, excluding sources where no asset has a `Target Asset` name assigned, before emitting the `start_backend_processing` signal. It also manages enabling/disabling controls.
*   Managing the background prediction threads (`RuleBasedPredictionHandler` via `QThread`, `LLMPredictionHandler` via `LLMInteractionHandler`).
*   Implementing slots to handle results from background tasks:
    *   `_on_rule_hierarchy_ready`: Handles results from `RuleBasedPredictionHandler`.
    *   `_on_llm_prediction_ready_from_handler`: Handles results from `LLMInteractionHandler`.
    *   `_on_prediction_error`: Handles errors from both prediction paths.
    *   `_handle_prediction_completion`: Centralized logic to track completion and update UI state after each prediction result or error.
    *   Slots to handle status and state changes from `LLMInteractionHandler`.

## Threading and Background Tasks

To keep the UI responsive, prediction tasks run in background threads managed by a `QThreadPool`.

*   **`BasePredictionHandler` (`gui/base_prediction_handler.py`):** An abstract `QRunnable` base class defining the common interface and signals (`prediction_signal`, `status_signal`) for prediction tasks.
*   **`RuleBasedPredictionHandler` (`gui/prediction_handler.py`):** Inherits from `BasePredictionHandler`. Runs as a `QRunnable` in the thread pool when a rule-based preset is selected. Generates the `SourceRule` hierarchy based on preset rules and emits `prediction_signal`.
*   **`LLMPredictionHandler` (`gui/llm_prediction_handler.py`):** Inherits from `BasePredictionHandler`. Runs as a `QRunnable` in the thread pool when "- LLM Interpretation -" is selected. Interacts with `LLMInteractionHandler`, parses the response, generates the `SourceRule` hierarchy for a *single* input item, and emits `prediction_signal` and `status_signal`.
*   **`LLMInteractionHandler` (`gui/llm_interaction_handler.py`):** Manages the communication with the LLM service. This handler itself may perform network operations but typically runs synchronously within the `LLMPredictionHandler`'s thread.

*(Note: The actual processing via `ProcessingEngine` is now handled by `main.ProcessingTask`, which runs in a separate process managed outside the GUI's direct threading model, though the GUI initiates it).*

## Communication (Signals and Slots)

Communication between the `MainWindow` (main UI thread) and the background prediction tasks relies on Qt's signals and slots.

*   Prediction handlers (`RuleBasedPredictionHandler`, `LLMPredictionHandler`) emit signals from the `BasePredictionHandler`:
    *   `prediction_signal(source_id, source_rule_list)`: Indicates prediction for a source is complete.
    *   `status_signal(message)`: Provides status updates (primarily from LLM handler).
*   The `MainWindow` connects slots to these signals:
    *   `prediction_signal` -> `MainWindow._handle_prediction_completion(source_id, source_rule_list)`
    *   `status_signal` -> `MainWindow._on_status_update(message)` (updates status bar)
*   Signals from the `UnifiedViewModel` (`dataChanged`, `layoutChanged`) trigger updates in the `QTreeView`.
*   Signals from the `UnifiedViewModel` (`targetAssetOverrideChanged`) trigger the `AssetRestructureHandler`.

## Preset Editor (`gui/preset_editor_widget.py`)

The `PresetEditorWidget` provides a dedicated interface for managing presets. It handles loading, displaying, editing, and saving preset `.json` files.

*   **Refactoring:** This widget has been refactored to expose its main components:
    *   `selector_container`: A `QWidget` containing the preset list (`QListWidget`) and New/Delete buttons. Used statically by `MainWindow`.
    *   `json_editor_container`: A `QWidget` containing the tabbed editor (`QTabWidget`) for preset JSON details and the Save/Save As buttons. Placed in `MainWindow`'s `QStackedWidget`.
*   **Functionality:** Still manages the logic for populating the preset list, loading/saving presets, handling unsaved changes, and providing the editor UI for preset details.
*   **Communication:** Emits `preset_selection_changed_signal(mode, preset_name)` when the user selects a preset, the LLM option, or the placeholder. This signal is crucial for `MainWindow` to switch the editor stack and trigger preview updates.

## LLM Settings Editor (`gui/llm_editor_widget.py`)

This new widget provides a dedicated interface for editing LLM-specific settings stored in `config/llm_settings.json`.

*   **Purpose:** Allows users to configure the LLM predictor's behavior without directly editing the JSON file.
*   **Structure:** Uses a `QTabWidget` with two tabs:
    *   **"Prompt Settings":** Contains a `QPlainTextEdit` for the main prompt and a nested `QTabWidget` for managing examples (add/delete/edit JSON in `QTextEdit` widgets).
    *   **"API Settings":** Contains fields (`QLineEdit`, `QDoubleSpinBox`, `QSpinBox`) for endpoint URL, API key, model name, temperature, and timeout.
*   **Functionality:**
    *   `load_settings()`: Reads `config/llm_settings.json` and populates the UI fields. Handles file not found or JSON errors. Called by `MainWindow` when switching to LLM mode.
    *   `_save_settings()`: Gathers data from the UI, validates example JSON, constructs the settings dictionary, and calls `configuration.save_llm_config()` to write back to the file. Emits `settings_saved` signal on success.
    *   Manages unsaved changes state and enables/disables the "Save LLM Settings" button accordingly.

## Unified Hierarchical View

The core rule editing interface is built around a `QTreeView` managed within the `MainPanelWidget`, using a custom model and delegates.

*   **`UnifiedViewModel` (`gui/unified_view_model.py`):** Implements `QAbstractItemModel`.
    *   Wraps the `RuleHierarchyModel` to expose the `SourceRule` list (Source -> Asset -> File) to the `QTreeView`.
    *   Provides data for display and flags for editing.
    *   **Handles `setData` requests:** Validates input and updates the underlying `RuleHierarchyModel`. Crucially, it **delegates** complex restructuring (when `target_asset_name_override` changes) to the `AssetRestructureHandler` by emitting the `targetAssetOverrideChanged` signal.
    *   **Row Coloring:** Provides data for `Qt.ForegroundRole` (text color) based on the `item_type` and the colors defined in `config/app_settings.json`. Provides data for `Qt.BackgroundRole` based on calculating a 30% darker shade of the parent asset's background color.
    *   **Caching:** Caches configuration data (`ASSET_TYPE_DEFINITIONS`, `FILE_TYPE_DEFINITIONS`, color maps) in `__init__` for performance.
    *   **`update_rules_for_sources` Method:** Intelligently merges new prediction results or placeholder rules into the existing model data, preserving user overrides where applicable.
    *   *(Note: The previous concept of switching between "simple" and "detailed" display modes has been removed. The model always represents the full detailed structure.)*
*   **`RuleHierarchyModel` (`gui/rule_hierarchy_model.py`):** A non-Qt model holding the actual list of `SourceRule` objects. Provides methods for accessing and modifying the hierarchy (used by `UnifiedViewModel` and `AssetRestructureHandler`).
*   **`AssetRestructureHandler` (`gui/asset_restructure_handler.py`):** Contains the logic to modify the `RuleHierarchyModel` when a file's target asset is changed. It listens for the `targetAssetOverrideChanged` signal from the `UnifiedViewModel` and uses methods on the `RuleHierarchyModel` (`moveFileRule`, `createAssetRule`, `removeAssetRule`) to perform the restructuring safely.
*   **`Delegates` (`gui/delegates.py`):** Custom `QStyledItemDelegate` implementations provide inline editors:
    *   **`ComboBoxDelegate`:** For selecting predefined types (from `Configuration`).
    *   **`LineEditDelegate`:** For free-form text editing.
    *   **`SupplierSearchDelegate`:** For supplier names with auto-completion (using `config/suppliers.json`).

**Data Flow Diagram (GUI Rule Management - Refactored):**

```mermaid
graph TD
    subgraph MainWindow [MainWindow Coordinator]
        direction LR
        MW_Input[User Input (Drag/Drop)] --> MW(MainWindow);
        MW -- Owns/Manages --> Splitter(QSplitter);
        MW -- Owns/Manages --> LLMIH(LLMInteractionHandler);
        MW -- Owns/Manages --> ARH(AssetRestructureHandler);
        MW -- Owns/Manages --> VM(UnifiedViewModel);
        MW -- Owns/Manages --> LCW(LogConsoleWidget);
        MW -- Initiates --> PredPool{Prediction Threads};
        MW -- Connects Signals --> VM;
        MW -- Connects Signals --> ARH;
        MW -- Connects Signals --> LLMIH;
        MW -- Connects Signals --> PEW(PresetEditorWidget);
        MW -- Connects Signals --> LLMEDW(LLMEditorWidget);
    end

    subgraph LeftPane [Left Pane Widgets]
        direction TB
        Splitter -- Adds Widget --> LPW(Left Pane Container);
        LPW -- Contains --> PEW_Sel(PresetEditorWidget - Selector);
        LPW -- Contains --> Stack(QStackedWidget);
        Stack -- Contains --> PEW_Edit(PresetEditorWidget - JSON Editor);
        Stack -- Contains --> LLMEDW;
    end

    subgraph RightPane [Right Pane Widgets]
        direction TB
        Splitter -- Adds Widget --> MPW(MainPanelWidget);
        MPW -- Contains --> TV(QTreeView - Rule View);
        MPW_UI[UI Controls (Process Btn, etc)];
        MPW_UI --> MPW;
    end

    subgraph Prediction [Background Prediction]
        direction TB
        PredPool -- Runs --> RBP(RuleBasedPredictionHandler);
        PredPool -- Runs --> LLMP(LLMPredictionHandler);
        LLMIH -- Manages/Starts --> LLMP;
        RBP -- prediction_ready/error/status --> MW;
        LLMIH -- llm_prediction_ready/error/status --> MW;
    end

    subgraph ModelView [Model/View Components]
        direction TB
        TV -- Sets Model --> VM;
        TV -- Displays Data From --> VM;
        TV -- Uses Delegates --> Del(Delegates);
        UserEdit[User Edits Rules] --> TV;
        TV -- setData --> VM;
        VM -- Wraps --> RHM(RuleHierarchyModel);
        VM -- dataChanged/layoutChanged --> TV;
        VM -- targetAssetOverrideChanged --> ARH;
        ARH -- Modifies --> RHM;
        Del -- Get/Set Data --> VM;
    end

    %% MainWindow Interactions
    MW_Input -- Triggers --> MW;
    PEW -- preset_selection_changed_signal --> MW;
    LLMEDW -- settings_saved --> MW;
    MPW -- process_requested/etc --> MW;
    MW -- _on_preset_selection_changed --> Stack;
    MW -- _on_preset_selection_changed --> LLMEDW;
    MW -- _handle_prediction_completion --> VM;
    MW -- Triggers Processing --> ProcTask(main.ProcessingTask);

    %% Connections between subgraphs
    PEW --> LPW; %% PresetEditorWidget parts are in Left Pane
    LLMEDW --> Stack; %% LLMEditorWidget is in Stack
    MPW --> Splitter; %% MainPanelWidget is in Right Pane
    VM --> MW;
    ARH --> MW;
    LLMIH --> MW;
    LCW --> MW;
```

## Application Styling

The application style is explicitly set to 'Fusion' in `gui/main_window.py`. A custom `QPalette` adjusts default colors.

## Logging (`gui/log_console_widget.py`)

The `LogConsoleWidget` displays logs captured by a custom `QtLogHandler` from Python's `logging` module.

## Cancellation

The GUI provides a "Cancel" button. Cancellation logic for the actual processing is now likely handled within the `main.ProcessingTask` or the code that manages it, as the `ProcessingHandler` has been removed. The GUI button would signal this external task manager.

## Application Preferences Editor (`gui/config_editor_dialog.py`)

A dedicated dialog for editing user-overridable application settings. It loads base settings from `config/app_settings.json` and saves user overrides to `config/user_settings.json`.

*   **Functionality:** Provides a tabbed interface to edit various application settings, including general paths, output/naming patterns, image processing options (like resolutions and compression), and map merging rules. It no longer includes editors for Asset Type or File Type Definitions.
*   **Integration:** Launched by `MainWindow` via the "Edit" -> "Preferences..." menu.
*   **Persistence:** Saves changes to `config/user_settings.json`. Changes require an application restart to take effect in processing logic.

The refactored GUI separates concerns into distinct widgets and handlers, coordinated by the `MainWindow`. Background tasks use `QThreadPool` and `QRunnable`. The `UnifiedViewModel` focuses on data presentation and simple edits, delegating complex restructuring to the `AssetRestructureHandler`.

## Definitions Editor (`gui/definitions_editor_dialog.py`)

A new dedicated dialog for managing core application definitions that are separate from general user preferences.

*   **Purpose:** Provides a structured UI for editing Asset Type Definitions, File Type Definitions, and Supplier Settings.
*   **Structure:** Uses a `QTabWidget` with three tabs:
    *   **Asset Type Definitions:** Manages definitions from `config/asset_type_definitions.json`. Presents a list of asset types and allows editing their description, color, and examples.
    *   **File Type Definitions:** Manages definitions from `config/file_type_definitions.json`. Presents a list of file types and allows editing their description, color, examples, standard type, bit depth rule, grayscale status, and keybind.
    *   **Supplier Settings:** Manages settings from `config/suppliers.json`. Presents a list of suppliers and allows editing supplier-specific settings (e.g., Normal Map Type).
*   **Integration:** Launched by `MainWindow` via the "Edit" -> "Edit Definitions..." menu.
*   **Persistence:** Saves changes directly to the respective configuration files (`config/asset_type_definitions.json`, `config/file_type_definitions.json`, `config/suppliers.json`). Some changes may require an application restart.