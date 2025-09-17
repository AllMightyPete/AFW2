# Developer Guide: Key Components

This document describes the major classes and modules that form the core of the Asset Processor Tool.

## Core Processing Architecture

The asset processing pipeline has been refactored into a staged architecture, managed by an orchestrator.

### `ProcessingEngine` (`processing_engine.py`)

The `ProcessingEngine` class serves as the primary entry point for initiating an asset processing task. Its main responsibilities are:

*   Initializing a `PipelineOrchestrator` instance.
*   Providing the `PipelineOrchestrator` with the global `Configuration` object and a predefined list of processing stages.
*   Invoking the orchestrator's `process_source_rule()` method with the input `SourceRule`, workspace path, output path, and other processing parameters.
*   Managing a top-level temporary directory for the engine's operations if needed, though individual stages might also use sub-temporary directories via the `AssetProcessingContext`.

It no longer contains the detailed logic for each processing step (like map manipulation, merging, etc.) directly. Instead, it delegates these tasks to the orchestrator and its stages.

### `PipelineOrchestrator` (`processing/pipeline/orchestrator.py`)

The `PipelineOrchestrator` class is responsible for managing the execution of the asset processing pipeline. Its key functions include:

*   Receiving a `SourceRule` object, `Configuration`, and a list of `ProcessingStage` objects.
*   For each `AssetRule` within the `SourceRule`:
    *   Creating an `AssetProcessingContext` instance.
    *   Sequentially executing each registered `ProcessingStage`, passing the `AssetProcessingContext` to each stage.
    *   Handling exceptions that occur within stages and managing the overall status of asset processing (processed, skipped, failed).
*   Managing a temporary directory for the duration of a `SourceRule` processing, which is made available to stages via the `AssetProcessingContext`.

### `AssetProcessingContext` (`processing/pipeline/asset_context.py`)

The `AssetProcessingContext` is a dataclass that acts as a stateful container for all data related to the processing of a single `AssetRule`. An instance of this context is created by the `PipelineOrchestrator` for each asset and is passed through each processing stage. Key information it holds includes:

*   The input `SourceRule` and the current `AssetRule`.
*   Paths: `workspace_path`, `engine_temp_dir`, `output_base_path`.
*   The `Configuration` object.
*   `effective_supplier`: Determined by an early stage.
*   `asset_metadata`: A dictionary to accumulate metadata about the asset.
*   `processed_maps_details`: Stores details about individually processed maps (paths, dimensions, etc.).
*   `merged_maps_details`: Stores details about merged maps.
*   `files_to_process`: A list of `FileRule` objects to be processed for the current asset.
*   `loaded_data_cache`: For caching loaded image data within an asset's processing.
*   `status_flags`: For signaling conditions like `skip_asset` or `asset_failed`.
*   `incrementing_value`, `sha5_value`: Optional values for path generation.

Each stage reads from and writes to this context, allowing data and state to flow through the pipeline.

### `Processing Stages` (`processing/pipeline/stages/`)

The actual processing logic is broken down into a series of discrete stages, each inheriting from `ProcessingStage` (`processing/pipeline/stages/base_stage.py`). Each stage implements an `execute(context: AssetProcessingContext)` method. Key stages include (in typical execution order):

*   **`SupplierDeterminationStage`**: Determines the effective supplier.
*   **`AssetSkipLogicStage`**: Checks if the asset processing should be skipped.
*   **`MetadataInitializationStage`**: Initializes basic asset metadata.
*   **`FileRuleFilterStage`**: Filters `FileRule`s to decide which files to process.
*   **`GlossToRoughConversionStage`**: Handles gloss-to-roughness map inversion.
*   **`AlphaExtractionToMaskStage`**: Extracts alpha channels to create masks.
*   **`NormalMapGreenChannelStage`**: Inverts normal map green channels if required.
*   **`IndividualMapProcessingStage`**: Processes individual maps (POT scaling, resolution variants, color conversion, stats, aspect ratio, filename conventions).
*   **`MapMergingStage`**: Merges map channels based on rules.
*   **`MetadataFinalizationAndSaveStage`**: Collects all metadata and saves `metadata.json` to a temporary location.
*   **`OutputOrganizationStage`**: Copies all processed files and metadata to the final output directory structure.

## `Rule Structure` (`rule_structure.py`)

This module defines the data structures used to represent the hierarchical processing rules:

*   `SourceRule`: A dataclass representing rules applied at the source level. It contains nested `AssetRule` objects.
*   `AssetRule`: A dataclass representing rules applied at the asset level. It contains nested `FileRule` objects.
*   `FileRule`: A dataclass representing rules applied at the file level.

These classes hold specific rule parameters (e.g., `supplier_identifier`, `asset_type`, `asset_type_override`, `item_type`, `item_type_override`, `target_asset_name_override`, `resolution_override`, `channel_merge_instructions`). Attributes like `asset_type` and `item_type_override` now use string types, which are validated against centralized lists in `config/app_settings.json`. These structures support serialization (Pickle, JSON) to allow them to be passed between different parts of theapplication, including across process boundaries. The `PipelineOrchestrator` and its stages heavily rely on the information within these rule objects, passed via the `AssetProcessingContext`.

## `Configuration` (`configuration.py`)

The `Configuration` class manages the tool's settings. It is responsible for:

*   Loading the core default settings defined in `config/app_settings.json` (e.g., `FILE_TYPE_DEFINITIONS`, `ASSET_TYPE_DEFINITIONS`, `image_resolutions`, `map_merge_rules`, `output_filename_pattern`).
*   Loading the supplier-specific rules from a selected preset JSON file (`Presets/*.json`).
*   Merging the core settings and preset rules into a single, unified configuration object.
*   Validating the loaded configuration to ensure required settings are present.
*   Pre-compiling regular expression patterns defined in the preset for efficient file classification by the prediction handlers.

An instance of the `Configuration` class is typically created once per application run (or per processing batch) and passed to the `ProcessingEngine`, which then makes it available to the `PipelineOrchestrator` and subsequently to each stage via the `AssetProcessingContext`.

## GUI Components (`gui/`)

The GUI has been refactored into several key components:

### `MainWindow` (`gui/main_window.py`)

The `MainWindow` class acts as the main application window and **coordinator** for the GUI. Its primary responsibilities now include:

*   Setting up the main window structure (using a `QSplitter`) and menu bar.
*   Instantiating and arranging the major GUI widgets:
    *   `PresetEditorWidget` (providing selector and JSON editor parts)
    *   `LLMEditorWidget` (for LLM settings)
    *   `MainPanelWidget` (containing the rule view and processing controls)
    *   `LogConsoleWidget`
*   **Layout Management:** Placing the preset selector statically and using a `QStackedWidget` to switch between the `PresetEditorWidget`'s JSON editor and the `LLMEditorWidget`.
*   **Editor Switching:** Handling the `preset_selection_changed_signal` from `PresetEditorWidget` to switch the stacked editor view (`_on_preset_selection_changed` slot).
*   Connecting signals and slots between widgets, models (`UnifiedViewModel`), and handlers (`LLMInteractionHandler`, `AssetRestructureHandler`).
*   Managing the overall application state related to GUI interactions (e.g., enabling/disabling controls).
*   Handling top-level actions like loading sources (drag-and-drop), initiating predictions (`update_preview`), and starting the processing task (`_on_process_requested`).
*   Managing background prediction threads (Rule-Based via `QThread`, LLM via `LLMInteractionHandler`).
*   Implementing slots (`_on_rule_hierarchy_ready`, `_on_llm_prediction_ready_from_handler`, `_on_prediction_error`, `_handle_prediction_completion`) to update the model/view when prediction results/errors arrive.

### `MainPanelWidget` (`gui/main_panel_widget.py`)

This widget contains the central part of the GUI, including:

*   Controls for loading source files/directories.
*   The preset selection dropdown.
*   Buttons for initiating prediction and processing.
*   The `RuleEditorWidget` which houses the hierarchical rule view.

### `PresetEditorWidget` (`gui/preset_editor_widget.py`)

This widget provides the interface for managing presets:

*   Loading, saving, and editing preset files (`Presets/*.json`).
*   Displaying preset rules and settings in a tabbed JSON editor.
*   Providing the preset selection list (`QListWidget`) including the "LLM Interpretation" option.
*   **Refactored:** Exposes its selector (`selector_container`) and JSON editor (`json_editor_container`) as separate widgets for use by `MainWindow`.
*   Emits `preset_selection_changed_signal` when the selection changes.

### `LogConsoleWidget` (`gui/log_console_widget.py`)

This widget displays application logs within the GUI:

*   Provides a text area for log messages.
*   Integrates with Python's `logging` system via a custom `QtLogHandler`.
*   Can be shown/hidden via the main window's "View" menu.

### `LLMEditorWidget` (`gui/llm_editor_widget.py`)

A new widget dedicated to editing LLM settings:

*   Provides a tabbed interface ("Prompt Settings", "API Settings") to edit `config/llm_settings.json`.
*   Allows editing the main prompt, managing examples (add/delete/edit JSON), and configuring API details (URL, key, model, temperature, timeout).
*   Loads settings via `load_settings()` and saves them using `_save_settings()` (which calls `configuration.save_llm_config()`).
*   Placed within `MainWindow`'s `QStackedWidget`.

### `UnifiedViewModel` (`gui/unified_view_model.py`)

The `UnifiedViewModel` implements a `QAbstractItemModel` for use with Qt's model-view architecture. It is specifically designed to:

*   Wrap a list of `SourceRule` objects and expose their hierarchical structure (Source -> Asset -> File) to a `QTreeView` (the Unified Hierarchical View).
*   Provide methods (`data`, `index`, `parent`, `rowCount`, `columnCount`, `flags`, `setData`) required by `QAbstractItemModel` to allow the `QTreeView` to display the rule hierarchy and support inline editing of specific attributes (e.g., `supplier_override`, `asset_type_override`, `item_type_override`, `target_asset_name_override`).
*   Handle requests for data editing (`setData`) by validating input and updating the underlying `RuleHierarchyModel`. **Note:** Complex restructuring logic (e.g., moving files between assets when `target_asset_name_override` changes) is now delegated to the `AssetRestructureHandler`.
*   Determine row background colors based on the `asset_type` and `item_type`/`item_type_override` using color metadata from the `Configuration`.
*   Hold the `SourceRule` data (via `RuleHierarchyModel`) that is the single source of truth for the GUI's processing rules.
*   Cache configuration data (`ASSET_TYPE_DEFINITIONS`, `FILE_TYPE_DEFINITIONS`, color maps) during initialization for improved performance in the `data()` method.
*   Includes the `update_rules_for_sources` method, which intelligently merges new prediction results into the existing model data, preserving user overrides where possible.

### `RuleHierarchyModel` (`gui/rule_hierarchy_model.py`)

A simpler, non-Qt model used internally by `UnifiedViewModel` to manage the list of `SourceRule` objects and provide methods for accessing and modifying the hierarchy.

### `AssetRestructureHandler` (`gui/asset_restructure_handler.py`)

This handler contains the complex logic required to modify the `SourceRule` hierarchy when a file's target asset is changed via the GUI's `UnifiedViewModel`. It:

*   Is triggered by a signal (`targetAssetOverrideChanged`) from the `UnifiedViewModel`.
*   Uses dedicated methods on the `RuleHierarchyModel` (`moveFileRule`, `createAssetRule`, `removeAssetRule`) to safely move `FileRule` objects between `AssetRule`s, creating or removing `AssetRule`s as needed.
*   Ensures data consistency during these potentially complex restructuring operations.

### `Delegates` (`gui/delegates.py`)

This module contains custom `QStyledItemDelegate` implementations used by the Unified Hierarchical View (`QTreeView`) to provide inline editors for specific data types or rule attributes. Examples include delegates for:

*   `ComboBoxDelegate`: For selecting from predefined lists of allowed asset and file types, sourced from the `Configuration` (originally from `config/app_settings.json`).
*   `LineEditDelegate`: For free-form text editing, such as the `target_asset_name_override`.
*   `SupplierSearchDelegate`: For the "Supplier" column. Provides a `QLineEdit` with auto-completion suggestions loaded from `config/suppliers.json` and handles adding/saving new suppliers.

These delegates handle the presentation and editing of data within the tree view cells, interacting with the `UnifiedViewModel` to get and set data.

## Prediction Handlers (`gui/`)

Prediction logic is handled by classes inheriting from a common base class, running in background threads.

### `BasePredictionHandler` (`gui/base_prediction_handler.py`)

An abstract base class (`QRunnable`) for prediction handlers. It defines the common structure and signals (`prediction_signal`) used by specific predictor implementations. It's designed to be run in a `QThreadPool`.

### `RuleBasedPredictionHandler` (`gui/prediction_handler.py`)

This class (inheriting from `BasePredictionHandler`) is responsible for generating the initial `SourceRule` hierarchy using predefined rules from presets. It:

*   Takes an input source identifier, file list, and `Configuration` object.
*   Analyzes files based on regex patterns and rules defined in the loaded preset.
*   Constructs a `SourceRule` hierarchy with predicted values.
*   Emits the `prediction_signal` with the generated `SourceRule` object.

### `LLMPredictionHandler` (`gui/llm_prediction_handler.py`)

An experimental predictor (inheriting from `BasePredictionHandler`) that uses a Large Language Model (LLM). It:

*   Takes an input source identifier, file list, and `Configuration` object.
*   Interacts with the `LLMInteractionHandler` to send data to the LLM and receive predictions.
*   **Parses the LLM's JSON response**: It expects a specific two-part JSON structure (see `12_LLM_Predictor_Integration.md`). It first sanitizes the response (removing comments/markdown) and then parses the JSON.
*   **Constructs `SourceRule`**: It groups files based on the `proposed_asset_group_name` from the JSON, assigns the final `asset_type` using the `asset_group_classifications` map, and builds the complete `SourceRule` hierarchy.
*   Emits the `prediction_signal` with the generated `SourceRule` object or `error_signal` on failure.

### `LLMInteractionHandler` (`gui/llm_interaction_handler.py`)

This class now acts as the central manager for LLM prediction tasks:

*   **Manages the LLM prediction queue** and processes items sequentially.
*   **Loads LLM configuration** directly from `config/llm_settings.json` and `config/app_settings.json`.
*   **Instantiates and manages** the `LLMPredictionHandler` and its `QThread`.
*   **Handles LLM task state** (running/idle) and signals changes to the GUI.
*   Receives results/errors from `LLMPredictionHandler` and **emits signals** (`llm_prediction_ready`, `llm_prediction_error`, `llm_status_update`, `llm_processing_state_changed`) to `MainWindow`.

## Utility Modules (`utils/`)

Common utility functions have been extracted into separate modules:

### `workspace_utils.py`

Contains functions related to managing the processing workspace:

*   `prepare_processing_workspace`: Creates temporary directories, extracts archive files (ZIP, RAR, 7z), and returns the path to the prepared workspace. Used by `main.ProcessingTask` and `monitor.py`.

### `prediction_utils.py`

Contains utility functions supporting prediction tasks:

*   `generate_source_rule_from_archive`: A helper function used by `monitor.py` to perform rule-based prediction directly on an archive file without needing the full GUI setup. It extracts files temporarily, runs prediction logic similar to `RuleBasedPredictionHandler`, and returns a `SourceRule`.

## Monitor (`monitor.py`)

The `monitor.py` script implements the directory monitoring feature. It has been refactored to:

*   Use `watchdog` to detect new archive files in the input directory.
*   Use a `ThreadPoolExecutor` to process detected archives asynchronously in a `_process_archive_task` function.
*   Within the task, it:
    *   Loads the necessary `Configuration`.
    *   Calls `utils.prediction_utils.generate_source_rule_from_archive` to get the `SourceRule`.
    *   Calls `utils.workspace_utils.prepare_processing_workspace` to set up the workspace.
    *   Instantiates and runs the `ProcessingEngine` (which in turn uses the `PipelineOrchestrator`).
    *   Handles moving the source archive to 'processed' or 'error' directories.
    *   Cleans up the workspace.

## Summary

These key components, along with the refactored GUI structure and new utility modules, work together to provide the tool's functionality. The architecture emphasizes separation of concerns (configuration, rule generation, processing, UI), utilizes background processing for responsiveness (GUI prediction, Monitor tasks), and relies on the `SourceRule` object as the central data structure passed between different stages of the workflow. The processing core is now a staged pipeline managed by the `PipelineOrchestrator`, enhancing modularity and maintainability.