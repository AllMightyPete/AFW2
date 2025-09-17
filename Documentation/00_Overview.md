# Asset Processor Tool Documentation

This documentation provides information about the Asset Processor Tool, covering both user-facing features and technical details for developers.

## Overview

This tool processes 3D asset source files (texture sets, models, etc., provided as ZIP, RAR, 7z archives, or folders) into a standardized library format. It uses configurable presets to interpret different asset sources and automates tasks like file classification, image resizing, channel merging, and metadata generation.

The tool offers both a Graphical User Interface (GUI) for interactive use and a Command-Line Interface (CLI) for batch processing and scripting. It also includes a Directory Monitor for automated processing of assets dropped into a watched folder, and optional integration with Blender for automated material/nodegroup creation.

This documentation strictly excludes details on environment setup, dependency installation, building the project, or deployment procedures, assuming familiarity with Python and the relevant libraries (OpenCV, NumPy, PySide6).

## Architecture and Codebase Summary

For developers interested in contributing, the tool's architecture centers on a **Core Processing Engine** (`processing_engine.py`) which initializes and runs a **Pipeline Orchestrator** (`processing/pipeline/orchestrator.py::PipelineOrchestrator`). This orchestrator executes a defined sequence of **Processing Stages** (located in `processing/pipeline/stages/`) based on a **Hierarchical Rule System** (`rule_structure.py`) and a **Configuration System** (`configuration.py` loading `config/app_settings.json` and `Presets/*.json`). The **Graphical User Interface** (`gui/`) has been significantly refactored: `MainWindow` (`main_window.py`) acts as a coordinator, delegating tasks to specialized widgets (`MainPanelWidget`, `PresetEditorWidget`, `LogConsoleWidget`) and background handlers (`RuleBasedPredictionHandler`, `LLMPredictionHandler`, `LLMInteractionHandler`, `AssetRestructureHandler`). The **Directory Monitor** (`monitor.py`) now processes archives asynchronously using a thread pool and utility functions (`utils/prediction_utils.py`, `utils/workspace_utils.py`). The **Command-Line Interface** entry point (`main.py`) primarily launches the GUI, with core CLI functionality currently non-operational. Optional **Blender Integration** (`blenderscripts/`) remains. A new `utils/` directory houses shared helper functions.

The codebase reflects this structure. The `gui/` directory contains the refactored UI components, `utils/` holds shared utilities, `processing/pipeline/` contains the orchestrator and individual processing stages, `Presets/` contains JSON presets, and `blenderscripts/` holds Blender scripts. Core logic resides in `processing_engine.py`, `processing/pipeline/orchestrator.py`, `configuration.py`, `rule_structure.py`, `monitor.py`, and `main.py`. The processing pipeline, initiated by `processing_engine.py` and executed by the `PipelineOrchestrator`, relies entirely on the input `SourceRule` and static configuration. Each stage in the pipeline operates on an `AssetProcessingContext` object (`processing/pipeline/asset_context.py`) to perform specific tasks like map processing, channel merging, and metadata generation.

## Table of Contents

*   [Overview](00_Overview.md) - This document, providing a high-level summary and table of contents.
*   **User Guide** - Information for end-users of the tool.
    *   [Introduction](01_User_Guide/01_Introduction.md) - Purpose and scope of the tool for users.
    *   [Features](01_User_Guide/02_Features.md) - Detailed list of the tool's capabilities.
    *   [Installation](01_User_Guide/03_Installation.md) - Requirements and setup instructions.
    *   [Configuration and Presets](01_User_Guide/04_Configuration_and_Presets.md) - How to configure the tool and use presets.
    *   [Usage: GUI](01_User_Guide/05_Usage_GUI.md) - Guide to using the Graphical User Interface.
    *   [Usage: CLI](01_User_Guide/06_Usage_CLI.md) - Guide to using the Command-Line Interface.
    *   [Usage: Monitor](01_User_Guide/07_Usage_Monitor.md) - Guide to using the Directory Monitor for automated processing.
    *   [Usage: Blender Integration](01_User_Guide/08_Usage_Blender.md) - How the optional Blender integration works for users.
    *   [Output Structure](01_User_Guide/09_Output_Structure.md) - Description of the generated asset library structure.
    *   [Docker](01_User_Guide/10_Docker.md) - Instructions for using the tool with Docker.
*   **Developer Guide** - Technical information for developers contributing to the tool.
    *   [Architecture](02_Developer_Guide/01_Architecture.md) - High-level system design and component overview.
    *   [Codebase Structure](02_Developer_Guide/02_Codebase_Structure.md) - Detailed breakdown of project files and directories.
    *   [Key Components](02_Developer_Guide/03_Key_Components.md) - In-depth explanation of major classes and modules.
    *   [Configuration System and Presets](02_Developer_Guide/04_Configuration_System_and_Presets.md) - Technical details of configuration loading and preset structure.
    *   [Processing Pipeline](02_Developer_Guide/05_Processing_Pipeline.md) - Step-by-step technical breakdown of the asset processing logic.
    *   [GUI Internals](02_Developer_Guide/06_GUI_Internals.md) - Technical details of the GUI implementation (threading, signals, etc.).
    *   [Monitor Internals](02_Developer_Guide/07_Monitor_Internals.md) - Technical details of the Directory Monitor implementation.
    *   [Blender Integration Internals](02_Developer_Guide/08_Blender_Integration_Internals.md) - Technical details of Blender script execution and interaction.
    *   [Development Workflow](02_Developer_Guide/09_Development_Workflow.md) - Guidance on contributing and modifying the codebase.
    *   [Coding Conventions](02_Developer_Guide/10_Coding_Conventions.md) - Project's coding standards and practices.
    *   [Debugging Notes](02_Developer_Guide/11_Debugging_Notes.md) - Advanced internal details, state management, error handling, and limitations.