# Developer Guide: Architecture

This document provides a high-level overview of the Asset Processor Tool's architecture and core components for developers.

## High-Level Architecture

The Asset Processor Tool is designed to process 3D asset source files into a standardized library format. Its high-level architecture consists of:

1.  **Core Processing Initiation (`processing_engine.py`):** The `ProcessingEngine` class acts as the entry point for an asset processing task. It initializes and runs a `PipelineOrchestrator`.
2.  **Pipeline Orchestration (`processing/pipeline/orchestrator.py`):** The `PipelineOrchestrator` manages a sequence of discrete processing stages. It creates an `AssetProcessingContext` for each asset and passes this context through each stage.
3.  **Processing Stages (`processing/pipeline/stages/`):** Individual modules, each responsible for a specific task in the pipeline (e.g., filtering files, processing maps, merging channels, organizing output). They operate on the `AssetProcessingContext`.
4.  **Prediction System:** Responsible for analyzing input files and generating the initial `SourceRule` hierarchy with predicted values. This system utilizes a base handler (`gui/base_prediction_handler.py::BasePredictionHandler`) with specific implementations:
    *   **Rule-Based Predictor (`gui/prediction_handler.py::RuleBasedPredictionHandler`):** Uses predefined rules from presets to classify files and determine initial processing parameters.
    *   **LLM Predictor (`gui/llm_prediction_handler.py::LLMPredictionHandler`):** An experimental alternative that uses a Large Language Model (LLM) to interpret file contents and context to predict processing parameters.
5.  **Configuration System (`Configuration`):** Handles loading core settings (including centralized type definitions and LLM-specific configuration) and merging them with supplier-specific rules defined in JSON presets and the persistent `config/suppliers.json` file.
6.  **Multiple Interfaces:** Provides different ways to interact with the tool:
    *   Graphical User Interface (GUI)
    *   Command-Line Interface (CLI) - *Note: The primary CLI execution logic (`run_cli` in `main.py`) is currently non-functional/commented out post-refactoring.*
    *   Directory Monitor for automated processing.
The GUI acts as the primary source of truth for processing rules, coordinating the generation and management of the `SourceRule` hierarchy before sending it to the `ProcessingEngine`. It accumulates prediction results from multiple input sources before updating the view. The Monitor interface can also generate `SourceRule` objects (using `utils/prediction_utils.py`) to bypass the GUI for automated workflows.
7.  **Optional Integration:** Includes scripts (`blenderscripts/`) for integrating with Blender. Logic for executing these scripts was intended to be centralized in `utils/blender_utils.py`, but this utility has not yet been implemented.

## Hierarchical Rule System

A key addition to the architecture is the **Hierarchical Rule System**, which provides a dynamic layer of configuration that can override the static settings loaded from presets. This system is represented by a hierarchy of rule objects: `SourceRule`, `AssetRule`, and `FileRule`.

*   **SourceRule:** Represents rules applied at the top level, typically corresponding to an entire input source (e.g., a ZIP file or folder).
*   **AssetRule:** Represents rules applied to a specific asset within a source (a source can contain multiple assets).
*   **FileRule:** Represents rules applied to individual files within an asset.

This hierarchy allows for fine-grained control over processing parameters. The GUI's prediction logic generates this hierarchy with initial predicted values for overridable fields based on presets and file analysis. The `ProcessingEngine` (via the `PipelineOrchestrator` and its stages) then operates *solely* on the explicit values provided in this `SourceRule` object and static configuration, without internal prediction or fallback logic.

## Core Components

*   `config/app_settings.json`: Defines core, global settings, constants, and centralized definitions for allowed asset and file types (`ASSET_TYPE_DEFINITIONS`, `FILE_TYPE_DEFINITIONS`), including metadata like colors and descriptions. This replaces the old `config.py` file.
*   `config/suppliers.json`: A persistent JSON file storing known supplier names for GUI auto-completion.
*   `Presets/*.json`: Supplier-specific JSON files defining rules for file interpretation and initial prediction.
*   `configuration.py` (`Configuration` class): Loads `config/app_settings.json` settings and merges them with a selected preset, pre-compiling regex patterns for efficiency. This static configuration is used by the processing pipeline.
*   `rule_structure.py`: Defines the `SourceRule`, `AssetRule`, and `FileRule` dataclasses used to represent the hierarchical processing rules.
*   `gui/`: Directory containing modules for the Graphical User Interface (GUI), built with PySide6. The `MainWindow` (`main_window.py`) acts as a coordinator, orchestrating interactions between various components. Key GUI components include:
    *   `main_panel_widget.py::MainPanelWidget`: Contains the primary controls for loading sources, selecting presets, viewing/editing rules, and initiating processing.
    *   `preset_editor_widget.py::PresetEditorWidget`: Provides the interface for managing presets.
    *   `log_console_widget.py::LogConsoleWidget`: Displays application logs.
    *   `unified_view_model.py::UnifiedViewModel`: Implements the `QAbstractItemModel` for the hierarchical rule view, holding `SourceRule` data and managing display logic (coloring, etc.). Caches configuration data for performance.
    *   `rule_hierarchy_model.py::RuleHierarchyModel`: A simpler model used internally by the `UnifiedViewModel` to manage the `SourceRule` data structure.
    *   `delegates.py`: Contains custom `QStyledItemDelegate` implementations for inline editing in the rule view.
    *   `asset_restructure_handler.py::AssetRestructureHandler`: Handles complex model updates when a file's target asset is changed via the GUI, ensuring the `SourceRule` hierarchy is correctly modified.
    *   `base_prediction_handler.py::BasePredictionHandler`: Abstract base class for prediction logic.
    *   `prediction_handler.py::RuleBasedPredictionHandler`: Generates the initial `SourceRule` hierarchy based on presets and file analysis. Inherits from `BasePredictionHandler`.
    *   `llm_prediction_handler.py::LLMPredictionHandler`: Experimental predictor using an LLM. Inherits from `BasePredictionHandler`.
    *   `llm_interaction_handler.py::LLMInteractionHandler`: Manages communication with the LLM service for the LLM predictor.
*   `processing_engine.py` (`ProcessingEngine` class): The entry-point class that initializes and runs the `PipelineOrchestrator` for a given `SourceRule` and `Configuration`.
*   `processing/pipeline/orchestrator.py` (`PipelineOrchestrator` class): Manages the sequence of processing stages, creating and passing an `AssetProcessingContext` through them.
*   `processing/pipeline/asset_context.py` (`AssetProcessingContext` class): A dataclass holding all data and state for the processing of a single asset, passed between stages.
*   `processing/pipeline/stages/`: Directory containing individual processing stage modules, each handling a specific part of the pipeline (e.g., `IndividualMapProcessingStage`, `MapMergingStage`).
*   `main.py`: The main entry point for the application. Primarily launches the GUI. Contains commented-out/non-functional CLI logic (`run_cli`).
*   `monitor.py`: Implements the directory monitoring feature using `watchdog`. It now processes archives asynchronously using a `ThreadPoolExecutor`, leveraging `utils.prediction_utils.py` for rule generation and `utils.workspace_utils.py` for workspace management before invoking the `ProcessingEngine`.
*   `blenderscripts/`: Contains Python scripts designed to be executed *within* Blender for post-processing tasks.
*   `utils/`: Directory containing utility modules:
    *   `workspace_utils.py`: Contains functions like `prepare_processing_workspace` for handling temporary directories and archive extraction.
    *   `prediction_utils.py`: Contains functions like `generate_source_rule_from_archive` used by the monitor for rule-based prediction.
    *   `blender_utils.py`: (Intended location for Blender script execution logic, currently not implemented).

## Processing Pipeline (Simplified Overview)

The asset processing pipeline, initiated by `processing_engine.py` and managed by `PipelineOrchestrator`, executes a series of stages for each asset defined in the `SourceRule`. An `AssetProcessingContext` object carries data between stages. The typical sequence is:

1.  **Supplier Determination**: Identify the effective supplier.
2.  **Asset Skip Logic**: Check if the asset should be skipped.
3.  **Metadata Initialization**: Set up initial asset metadata.
4.  **File Rule Filtering**: Determine which files to process.
5.  **Pre-Map Processing**:
    *   Gloss-to-Roughness Conversion.
    *   Alpha Channel Extraction.
    *   Normal Map Green Channel Inversion.
6.  **Individual Map Processing**: Handle individual maps (scaling, variants, stats, naming).
7.  **Map Merging**: Combine channels from different maps.
8.  **Metadata Finalization & Save**: Generate and save `metadata.json` (temporarily).
9.  **Output Organization**: Copy all processed files to final output locations.

External steps like workspace preparation/cleanup and optional Blender script execution bracket this core pipeline. This architecture allows for a modular design, separating configuration, rule generation/management, and core processing execution.