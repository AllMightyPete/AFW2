# Configuration System Refactoring Plan

This document outlines the plan for refactoring the configuration system of the Asset Processor Tool.

## Overall Goals

1.  **Decouple Definitions:** Separate `ASSET_TYPE_DEFINITIONS` and `FILE_TYPE_DEFINITIONS` from the main `config/app_settings.json` into dedicated files.
2.  **Introduce User Overrides:** Allow users to override base settings via a new `config/user_settings.json` file.
3.  **Improve GUI Saving:** (Lower Priority) Make GUI configuration saving more targeted to avoid overwriting unrelated settings when saving changes from `ConfigEditorDialog` or `LLMEditorWidget`.

## Proposed Plan Phases

**Phase 1: Decouple Definitions**

1.  **Create New Definition Files:**
    *   Create `config/asset_type_definitions.json`.
    *   Create `config/file_type_definitions.json`.
2.  **Migrate Content:**
    *   Move `ASSET_TYPE_DEFINITIONS` object from `config/app_settings.json` to `config/asset_type_definitions.json`.
    *   Move `FILE_TYPE_DEFINITIONS` object from `config/app_settings.json` to `config/file_type_definitions.json`.
3.  **Update `configuration.py`:**
    *   Add constants for new definition file paths.
    *   Modify `Configuration` class to load these new files.
    *   Update property methods (e.g., `get_asset_type_definitions`, `get_file_type_definitions_with_examples`) to use data from the new definition dictionaries.
    *   Adjust validation (`_validate_configs`) as needed.
4.  **Update GUI & `load_base_config()`:**
    *   Modify `load_base_config()` to load and return a combined dictionary including `app_settings.json` and the two new definition files.
    *   Update GUI components relying on `load_base_config()` to ensure they receive the necessary definition data.

**Phase 2: Implement User Overrides**

1.  **Define `user_settings.json`:**
    *   Establish `config/user_settings.json` for user-specific overrides, mirroring parts of `app_settings.json`.
2.  **Update `configuration.py` Loading:**
    *   In `Configuration.__init__`, load `app_settings.json`, then definition files, then attempt to load and deep merge `user_settings.json` (user settings override base).
    *   Load presets *after* the base+user merge (presets override combined base+user).
    *   Modify `load_base_config()` to also load and merge `user_settings.json` after `app_settings.json`.
3.  **Update GUI Editors:**
    *   Modify `ConfigEditorDialog` to load the effective settings (base+user) but save changes *only* to `config/user_settings.json`.
    *   `LLMEditorWidget` continues targeting `llm_settings.json`.

**Phase 3: Granular GUI Saving (Lower Priority)**

1.  **Refactor Saving Logic:**
    *   In `ConfigEditorDialog` and `LLMEditorWidget`:
        *   Load the current target file (`user_settings.json` or `llm_settings.json`).
        *   Identify specific setting(s) changed by the user in the GUI session.
        *   Update only those specific key(s) in the loaded dictionary.
        *   Write the entire modified dictionary back to the target file, preserving untouched settings.

## Proposed File Structure & Loading Flow

```mermaid
graph LR
    subgraph Config Files
        A[config/asset_type_definitions.json]
        B[config/file_type_definitions.json]
        C[config/app_settings.json (Base Defaults)]
        D[config/user_settings.json (User Overrides)]
        E[config/llm_settings.json]
        F[config/suppliers.json]
        G[Presets/*.json]
    end

    subgraph Code
        H[configuration.py]
        I[GUI]
        J[Processing Engine / Pipeline]
        K[LLM Handlers]
    end

    subgraph Loading Flow (Configuration Class)
        L(Load Asset Types) --> H
        M(Load File Types) --> H
        N(Load Base Settings) --> P(Merge Base + User)
        O(Load User Settings) --> P
        P --> R(Merge Preset Overrides)
        Q(Load LLM Settings) --> H
        R --> T(Final Config Object)
        G -- Load Preset --> R
        H -- Contains --> T
    end

    subgraph Loading Flow (GUI - load_base_config)
        L2(Load Asset Types) --> U(Return Merged Defaults + Defs)
        M2(Load File Types) --> U
        N2(Load Base Settings) --> V(Merge Base + User)
        O2(Load User Settings) --> V
        V --> U
        I -- Calls --> U
    end


    T -- Used by --> J
    T -- Used by --> K

    I -- Edits --> D
    I -- Edits --> E
    I -- Manages --> F

    style A fill:#f9f,stroke:#333,stroke-width:2px
    style B fill:#f9f,stroke:#333,stroke-width:2px
    style C fill:#ccf,stroke:#333,stroke-width:2px
    style D fill:#9cf,stroke:#333,stroke-width:2px
    style E fill:#ccf,stroke:#333,stroke-width:2px
    style F fill:#9cf,stroke:#333,stroke-width:2px
    style G fill:#ffc,stroke:#333,stroke-width:2px