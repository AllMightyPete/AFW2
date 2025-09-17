# Refactoring Plan for Preferences Window (ConfigEditorDialog)

## 1. Overview

This document outlines the plan to refactor the preferences window (`gui/config_editor_dialog.py`). The primary goal is to address issues related to misaligned scope, poor user experience for certain data types, and incomplete interactivity. The refactoring will focus on making the `ConfigEditorDialog` a robust editor for settings in `config/app_settings.json` that are intended to be overridden by the user via `config/user_settings.json`.

## 2. Assessment Summary

*   **Misaligned Scope:** The dialog currently includes UI for "Asset Type Definitions" and "File Type Definitions". However, these are managed in separate dedicated JSON files ([`config/asset_type_definitions.json`](config/asset_type_definitions.json) and [`config/file_type_definitions.json`](config/file_type_definitions.json)) and are not saved by this dialog (which targets `config/user_settings.json`).
*   **Poor UX for Data Types:**
    *   Lists (e.g., `RESPECT_VARIANT_MAP_TYPES`) are edited as comma-separated strings.
    *   Dictionary-like structures (e.g., `IMAGE_RESOLUTIONS`) are handled inconsistently (JSON defines as dict, UI attempts list-of-pairs).
    *   Editing complex list-of-objects (e.g., `MAP_MERGE_RULES`) is functionally incomplete.
*   **Incomplete Interactivity:** Many table-based editors lack "Add/Remove Row" functionality and proper cell delegates for intuitive editing.
*   **LLM Settings:** Confirmed to be correctly managed by the separate `LLMEditorWidget` and `config/llm_settings.json`, so they are out of scope for this specific dialog refactor.

## 3. Refactoring Phases and Plan Details

```mermaid
graph TD
    A[Start: Current State] --> B{Phase 1: Correct Scope & Critical UX/Data Fixes};
    B --> C{Phase 2: Enhance MAP_MERGE_RULES Editor};
    C --> D{Phase 3: General UX & Table Interactivity};
    D --> E[End: Refactored Preferences Window];

    subgraph "Phase 1: Correct Scope & Critical UX/Data Fixes"
        B1[Remove Definitions Editing from ConfigEditorDialog]
        B2[Improve List Editing for RESPECT_VARIANT_MAP_TYPES]
        B3[Fix IMAGE_RESOLUTIONS Handling (Dictionary)]
        B4[Handle Simple Nested Settings (e.g., general_settings)]
    end

    subgraph "Phase 2: Enhance MAP_MERGE_RULES Editor"
        C1[Implement Add/Remove for Merge Rules]
        C2[Improve Rule Detail Editing (ComboBoxes, SpinBoxes)]
    end

    subgraph "Phase 3: General UX & Table Interactivity"
        D1[Implement IMAGE_RESOLUTIONS Table Add/Remove Buttons]
        D2[Implement Necessary Table Cell Delegates (e.g., for IMAGE_RESOLUTIONS values)]
        D3[Review/Refine Tab Layout & Widget Grouping]
    end

    B --> B1; B --> B2; B --> B3; B --> B4;
    C --> C1; C --> C2;
    D --> D1; D --> D2; D --> D3;
```

### Phase 1: Correct Scope & Critical UX/Data Fixes (in `gui/config_editor_dialog.py`)

1.  **Remove Definitions Editing:**
    *   **Action:** In `populate_definitions_tab`, remove the inner `QTabWidget` and the code that creates/populates the "Asset Types" and "File Types" tables.
    *   The `DEFAULT_ASSET_CATEGORY` `QComboBox` (for the setting from `app_settings.json`) should remain. Its items should be populated using keys obtained from the `Configuration` class (which loads the actual `ASSET_TYPE_DEFINITIONS` from its dedicated file).
    *   **Rationale:** Simplifies the dialog to settings managed via `user_settings.json`. Editing of the full definition files requires dedicated UI (see Future Enhancements note).

2.  **Improve `RESPECT_VARIANT_MAP_TYPES` Editing:**
    *   **Action:** In `populate_output_naming_tab`, replace the `QLineEdit` for `RESPECT_VARIANT_MAP_TYPES` with a `QListWidget` and "Add"/"Remove" buttons.
    *   "Add" button: Use `QInputDialog.getItem` with items populated from `Configuration.get_file_type_keys()` (or similar method accessing loaded `FILE_TYPE_DEFINITIONS`) to allow users to select a valid file type key.
    *   "Remove" button: Remove the selected item from the `QListWidget`.
    *   Update `save_settings` to read the list of strings from this `QListWidget`.
    *   Update `populate_widgets_from_settings` to populate this `QListWidget`.

3.  **Fix `IMAGE_RESOLUTIONS` Handling:**
    *   **Action:** In `populate_image_processing_tab`:
        *   The `QTableWidget` for `IMAGE_RESOLUTIONS` should have two columns: "Name" (string, for the dictionary key) and "Resolution (px)" (integer, for the dictionary value).
        *   In `populate_image_resolutions_table`, ensure it correctly populates from the dictionary structure in `self.settings['IMAGE_RESOLUTIONS']` (from `app_settings.json`).
        *   In `save_settings`, ensure it correctly reads data from the table and reconstructs the `IMAGE_RESOLUTIONS` dictionary (e.g., `{"4K": 4096, "2K": 2048}`) when saving to `user_settings.json`.
    *   ComboBoxes `CALCULATE_STATS_RESOLUTION` and `RESOLUTION_THRESHOLD_FOR_JPG` should be populated with the *keys* (names like "4K", "2K") from the `IMAGE_RESOLUTIONS` dictionary. `RESOLUTION_THRESHOLD_FOR_JPG` should also include "Never" and "Always" options. The `save_settings` method needs to correctly map these special ComboBox values back to appropriate storable values if necessary (e.g., sentinel numbers or specific strings if the backend configuration expects them for "Never"/"Always").

4.  **Handle Simple Nested Settings (e.g., `general_settings`):**
    *   **Action:** For `general_settings.invert_normal_map_green_channel_globally` (from `config/app_settings.json`):
        *   Add a `QCheckBox` labeled "Invert Normal Map Green Channel Globally" to an appropriate tab (e.g., "Image Processing" or a "General" tab after layout review).
        *   Update `populate_widgets_from_settings` to read `self.settings.get('general_settings', {}).get('invert_normal_map_green_channel_globally', False)`.
        *   Update `save_settings` to write this value back to `target_file_content.setdefault('general_settings', {})['invert_normal_map_green_channel_globally'] = widget.isChecked()`.

### Phase 2: Enhance `MAP_MERGE_RULES` Editor (in `gui/config_editor_dialog.py`)

1.  **Rule Management:**
    *   **Action:** In `populate_map_merging_tab`:
        *   Connect the "Add Rule" button:
            *   Create a default new rule dictionary (e.g., `{"output_map_type": "NEW_RULE", "inputs": {}, "defaults": {}, "output_bit_depth": "respect_inputs"}`).
            *   Add it to the internal list of rules that will be saved (e.g., a copy of `self.settings['MAP_MERGE_RULES']` that gets modified).
            *   Add a new `QListWidgetItem` for it and select it to display its details.
        *   Connect the "Remove Rule" button:
            *   Remove the selected rule from the internal list and the `QListWidget`.
            *   Clear the details panel.

2.  **Rule Details Panel Improvements (`display_merge_rule_details`):**
    *   **`output_map_type`:** Change the `QLineEdit` to a `QComboBox`. Populate its items from `Configuration.get_file_type_keys()`.
    *   **`inputs` Table:** The "Input Map Type" column cells should use a `QComboBox` delegate, populated with `Configuration.get_file_type_keys()` plus an empty/None option.
    *   **`defaults` Table:** The "Default Value" column cells should use a `QDoubleSpinBox` delegate (e.g., range 0.0 to 1.0, or 0-255 if appropriate for specific channel types).
    *   Ensure changes in these detail editors update the underlying rule data associated with the selected `QListWidgetItem` and the internal list of rules.

### Phase 3: General UX & Table Interactivity (in `gui/config_editor_dialog.py`)

1.  **Implement `IMAGE_RESOLUTIONS` Table Add/Remove Buttons:**
    *   **Action:** In `populate_image_processing_tab`, connect the "Add Row" and "Remove Row" buttons for the `IMAGE_RESOLUTIONS` table.
        *   "Add Row": Prompt for "Name" (string) and "Resolution (px)" (integer).
        *   "Remove Row": Remove the selected row from the table and the underlying data.
2.  **Implement Necessary Table Cell Delegates:**
    *   **Action:** For the `IMAGE_RESOLUTIONS` table, the "Resolution (px)" column should use a `QSpinBox` delegate or a `QLineEdit` with integer validation to ensure correct data input.
3.  **Review/Refine Tab Layout & Widget Grouping:**
    *   **Action:** After the functional changes, review the overall layout of tabs and the grouping of settings within `gui/config_editor_dialog.py`.
        *   Ensure settings from `config/app_settings.json` are logically placed and clearly labeled.
        *   Verify widget labels are descriptive and tooltips are helpful where needed.
        *   Confirm correct mapping between UI widgets and the keys in `app_settings.json` (e.g., `OUTPUT_FILENAME_PATTERN` vs. `TARGET_FILENAME_PATTERN`).

## 4. Future Enhancements (Out of Scope for this Refactor)

*   **Dedicated Editors for Definitions:** As per user feedback, if `ASSET_TYPE_DEFINITIONS` and `FILE_TYPE_DEFINITIONS` require UI-based editing, dedicated dialogs/widgets should be created. These would read from and save to their respective files ([`config/asset_type_definitions.json`](config/asset_type_definitions.json) and [`config/file_type_definitions.json`](config/file_type_definitions.json)) and could adopt a list/details UI similar to the `MAP_MERGE_RULES` editor.
*   **Live Updates:** Consider mechanisms for applying some settings without requiring an application restart, if feasible for specific settings.

This plan aims to create a more focused, usable, and correct preferences window.