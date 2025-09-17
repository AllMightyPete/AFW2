# Developer Guide: Codebase Structure

This document outlines the key files and directories within the Asset Processor Tool project.

```
Asset_processor_tool/
├── configuration.py               # Class for loading and accessing configuration (merges app_settings.json and presets)
├── Dockerfile                     # Instructions for building the Docker container image
├── main.py                        # Main application entry point (primarily GUI launcher)
├── monitor.py                     # Directory monitoring script for automated processing (async)
├── processing_engine.py           # Core class handling single asset processing based on SourceRule
├── requirements-docker.txt        # Dependencies specifically for the Docker environment
├── requirements.txt               # Python package dependencies for standard execution
├── rule_structure.py              # Dataclasses for hierarchical rules (SourceRule, AssetRule, FileRule)
├── blenderscripts/                # Scripts for integration with Blender
│   ├── create_materials.py        # Script to create materials linking to node groups
│   └── create_nodegroups.py       # Script to create node groups from processed assets
├── config/                        # Directory for configuration files
│   ├── app_settings.json          # Core settings, constants, and type definitions
│   └── suppliers.json             # Persistent list of known supplier names for GUI auto-completion
├── Deprecated/                    # Contains old code, documentation, and POC scripts
│   ├── ...
├── Documentation/                 # Directory for organized documentation (this structure)
│   ├── 00_Overview.md
│   ├── 01_User_Guide/
│   └── 02_Developer_Guide/
├── gui/                           # Contains files related to the Graphical User Interface (PySide6)
│   ├── asset_restructure_handler.py # Handles model updates for target asset changes
│   ├── base_prediction_handler.py # Abstract base class for prediction logic
│   ├── config_editor_dialog.py    # Dialog for editing configuration files
│   ├── delegates.py               # Custom delegates for inline editing in rule view
│   ├── llm_interaction_handler.py # Manages communication with LLM service
│   ├── llm_prediction_handler.py  # LLM-based prediction handler
│   ├── log_console_widget.py      # Widget for displaying logs
│   ├── main_panel_widget.py       # Main panel containing core GUI controls
│   ├── main_window.py             # Main GUI application window (coordinator)
│   ├── prediction_handler.py      # Rule-based prediction handler
│   ├── preset_editor_widget.py    # Widget for managing presets
│   ├── preview_table_model.py     # Model for the (deprecated?) preview table
│   ├── rule_editor_widget.py      # Widget containing the rule hierarchy view and editor
│   ├── rule_hierarchy_model.py    # Internal model for rule hierarchy data
│   └── unified_view_model.py      # QAbstractItemModel for the rule hierarchy view
├── llm_prototype/                 # Files related to the experimental LLM predictor prototype
│   ├── ...
├── Presets/                       # Preset definition files (JSON)
│   ├── _template.json             # Template for creating new presets
│   ├── Poliigon.json              # Example preset for Poliigon assets
│   └── ...                        # Other presets
├── ProjectNotes/                  # Directory for developer notes, plans, etc. (Markdown files)
│   ├── ...
├── PythonCheatsheats/             # Utility Python reference files
│   ├── ...
├── Testfiles/                     # Directory containing example input assets for testing
│   ├── ...
├── Tickets/                       # Directory for issue and feature tracking (Markdown files)
│   ├── ...
└── utils/                         # Utility modules shared across the application
    ├── prediction_utils.py        # Utilities for prediction (e.g., used by monitor)
    └── workspace_utils.py         # Utilities for managing processing workspaces
```

**Key Files and Directories:**

*   `config/`: Directory containing configuration files.
    *   `app_settings.json`: Stores global default settings, constants, core rules, and centralized definitions for allowed asset and file types (`ASSET_TYPE_DEFINITIONS`, `FILE_TYPE_DEFINITIONS`) used for validation, GUI elements, and coloring. Replaces the old `config.py`.
    *   `suppliers.json`: A JSON file storing a persistent list of known supplier names, used by the GUI for auto-completion.
*   `configuration.py`: Defines the `Configuration` class. Responsible for loading core settings from `config/app_settings.json` and merging them with a specified preset JSON file (`Presets/*.json`). Pre-compiles regex patterns from presets for efficiency. An instance of this class is passed to the `ProcessingEngine`.
*   `rule_structure.py`: Defines the `SourceRule`, `AssetRule`, and `FileRule` dataclasses. These structures represent the hierarchical processing rules and are the primary data contract passed from the rule generation layer (GUI, Monitor) to the processing engine.
*   `processing_engine.py`: Defines the `ProcessingEngine` class. This is the core component that executes the processing pipeline for a single asset based *solely* on a provided `SourceRule` object and the static `Configuration`. It contains no internal prediction or fallback logic.
*   `main.py`: Main entry point for the application. Primarily responsible for initializing and launching the GUI (`gui.main_window.MainWindow`). Contains non-functional/commented-out CLI logic (`run_cli`).
*   `monitor.py`: Implements the automated directory monitoring feature using `watchdog`. It now processes detected archives asynchronously using a `ThreadPoolExecutor`. It utilizes `utils.prediction_utils.generate_source_rule_from_archive` for rule-based prediction and `utils.workspace_utils.prepare_processing_workspace` for workspace setup before invoking the `ProcessingEngine`.
*   `gui/`: Directory containing all code related to the Graphical User Interface (GUI), built with PySide6. The `MainWindow` acts as a coordinator, delegating functionality to specialized widgets and handlers.
    *   `main_window.py`: Defines the `MainWindow` class. Acts as the main application window and coordinator, connecting signals and slots between different GUI components.
    *   `main_panel_widget.py`: Defines `MainPanelWidget`, containing the primary user controls (source loading, preset selection, rule view/editor integration, processing buttons).
    *   `preset_editor_widget.py`: Defines `PresetEditorWidget` for managing presets (loading, saving, editing).
    *   `log_console_widget.py`: Defines `LogConsoleWidget` for displaying application logs within the GUI.
    *   `rule_editor_widget.py`: Defines `RuleEditorWidget`, which houses the `QTreeView` for displaying the rule hierarchy.
    *   `unified_view_model.py`: Defines `UnifiedViewModel` (`QAbstractItemModel`) for the rule hierarchy view. Holds `SourceRule` data, manages display logic (coloring), handles inline editing requests, and caches configuration data for performance.
    *   `rule_hierarchy_model.py`: Defines `RuleHierarchyModel`, a simpler internal model used by `UnifiedViewModel` to manage the underlying `SourceRule` data structure.
    *   `delegates.py`: Contains custom `QStyledItemDelegate` implementations used by the `UnifiedViewModel` to provide appropriate inline editors (e.g., dropdowns, text boxes) for different rule attributes.
    *   `asset_restructure_handler.py`: Defines `AssetRestructureHandler`. Handles the complex logic of modifying the `SourceRule` hierarchy when a user changes a file's target asset via the GUI, ensuring data integrity. Triggered by signals from the model.
    *   `base_prediction_handler.py`: Defines the abstract `BasePredictionHandler` class, providing a common interface and threading (`QRunnable`) for prediction tasks.
    *   `prediction_handler.py`: Defines `RuleBasedPredictionHandler` (inherits from `BasePredictionHandler`). Generates the initial `SourceRule` hierarchy with predicted values based on input files and the selected preset rules. Runs in a background thread.
    *   `llm_prediction_handler.py`: Defines `LLMPredictionHandler` (inherits from `BasePredictionHandler`). Experimental handler using an LLM for prediction. Runs in a background thread.
    *   `llm_interaction_handler.py`: Defines `LLMInteractionHandler`. Manages the communication details (API calls, etc.) with the LLM service, used by `LLMPredictionHandler`.
*   `utils/`: Directory containing shared utility modules.
    *   `workspace_utils.py`: Provides functions for managing processing workspaces, such as creating temporary directories and extracting archives (`prepare_processing_workspace`). Used by `main.py` (ProcessingTask) and `monitor.py`.
    *   `prediction_utils.py`: Provides utility functions related to prediction, such as generating a `SourceRule` from an archive (`generate_source_rule_from_archive`), used by `monitor.py`.
*   `blenderscripts/`: Contains Python scripts (`create_nodegroups.py`, `create_materials.py`) designed to be executed *within* Blender for post-processing.
*   `Presets/`: Contains supplier-specific configuration files in JSON format, used by the `RuleBasedPredictionHandler` for initial rule generation.
*   `Testfiles/`: Contains example input assets for testing purposes.
*   `Tickets/`: Directory for issue and feature tracking using Markdown files.
*   `Deprecated/`: Contains older code, documentation, and proof-of-concept scripts that are no longer actively used.