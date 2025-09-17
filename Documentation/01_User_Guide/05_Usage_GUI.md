# User Guide: Usage - Graphical User Interface (GUI)

This document explains how to use the Asset Processor Tool's Graphical User Interface.

## Running the GUI

From the project root directory, run the following command:

```bash
python -m gui.main_window
```

## Interface Overview

*   **Menu Bar:** The "Edit" menu contains options to configure application settings and definitions:
    *   **Preferences...:** Opens the Application Preferences editor for user-overridable settings (saved to `config/user_settings.json`).
    *   **Edit Definitions...:** Opens the Definitions Editor for managing Asset Type Definitions, File Type Definitions, and Supplier Settings (saved to their respective files).
The "View" menu allows you to toggle the visibility of the Log Console and the Detailed File Preview.
*   **Preset Editor Panel (Left):**
    *   **Optional Log Console:** Displays application logs (toggle via View menu).
    *   **Preset List:** Create, delete, load, edit, and save presets. On startup, the "-- Select a Preset --" item is explicitly selected. You must select a specific preset from this list to load it into the editor below, enable the detailed file preview, and enable the "Start Processing" button.
    *   **Preset Editor Tabs:** Edit the details of the selected preset.
*   **Processing Panel (Right):**
    *   **Preset Selector:** Choose the preset to use for *processing* the current queue. (Note: LLM interpretation is now initiated via the right-click context menu in the Preview Table).
    *   **Output Directory:** Set the output path (defaults to `config/app_settings.json`, use "Browse...")
    *   **Drag and Drop Area:** Add asset `.zip`, `.rar`, `.7z` files, or folders by dragging and dropping them here.
    *   **Preview Table:** Shows queued assets in a hierarchical view (Source -> Asset -> File). Assets (files, directories, archives) added via drag-and-drop appear immediately in the table. This table is interactive:
        *   **Editable Fields:** The 'Name' field for Assets and the 'Target Asset', 'Supplier', 'Asset Type', and 'Item Type' fields for all items can be edited directly in the table.
            *   Editing an **Asset Name** automatically updates the 'Target Asset' field for all its child files.
            *   The **Item Type** field is a text input with auto-suggestions based on available types.
        *   **Drag-and-Drop Re-parenting:** File rows can be dragged and dropped onto different Asset rows to change their parent asset association.
        *   **Right-Click Context Menu:** Right-clicking on Source, Asset, or File rows brings up a context menu:
            *   **Re-interpret selected source:** This sub-menu allows re-running the prediction process for the selected source item(s) using either a specific preset or the LLM predictor. The available presets and the "LLM" option are listed dynamically. This replaces the previous standalone "Re-interpret Selected with LLM" button.
*   **Keybinds for Item Management:** When items are selected in the Preview Table, the following keybinds can be used:
            *   `Ctrl + C`: Sets the file type of selected items to Color/Albedo (`MAP_COL`).
            *   `Ctrl + R`: Toggles the file type of selected items between Roughness (`MAP_ROUGH`) and Glossiness (`MAP_GLOSS`).
            *   `Ctrl + N`: Sets the file type of selected items to Normal (`MAP_NRM`).
            *   `Ctrl + M`: Toggles the file type of selected items between Metalness (`MAP_METAL`) and Reflection/Specular (`MAP_REFL`).
            *   `Ctrl + D`: Sets the file type of selected items to Displacement/Height (`MAP_DISP`).
            *   `Ctrl + E`: Sets the file type of selected items to Extra (`EXTRA`).
            *   `Ctrl + X`: Sets the file type of selected items to Ignore (`FILE_IGNORE`).
            *   `F2`: Prompts to set the asset name for all selected items. This name propagates to the `AssetRule` name or the `FileRule` `target_asset_name_override` for the files under the selected assets. If individual files are selected, it will affect their `target_asset_name_override`.
        *   **Prediction Population:** If a valid preset is selected in the Preset Selector (or if re-interpretation is triggered), the table populates with prediction results as they become available. If no preset is selected, added items show empty prediction fields.
        *   **Columns:** The table displays columns: Name, Target Asset, Supplier, Asset Type, Item Type. The "Target Asset" column stretches to fill available space.
        *   **Coloring:** The *text color* of file items is determined by their Item Type (colors defined in `config/app_settings.json`). The *background color* of file items is a 30% darker shade of their parent asset's background, helping to visually group files within an asset. Asset rows themselves may use alternating background colors based on the application theme.
*   **Progress Bar:** Shows overall processing progress.
*   **Blender Post-Processing:** Checkbox to enable Blender scripts. If enabled, shows fields and browse buttons for target `.blend` files (defaults from `config/app_settings.json`).
    *   **Options & Controls (Bottom):**
        *   `Overwrite Existing`: Checkbox to force reprocessing.
        *   `Workers`: Spinbox for concurrent processes.
        *   `Clear Queue`: Button to clear the queue and preview.
        *   `Start Processing`: Button to start processing the queue. This button is enabled as long as there are items listed in the Preview Table. When clicked, any items that do not have a value assigned in the "Target Asset" column will be automatically ignored for that processing run.
        *   `Cancel`: Button to attempt stopping processing.
*   **Status Bar:** Displays current status, errors, and completion messages. During LLM processing, the status bar will show messages indicating the progress of the LLM requests.

## GUI Configuration Editor

Access the GUI Configuration Editor via the **Edit** -> **Preferences...** menu. This dialog allows you to directly edit the `config/app_settings.json` file, which contains the core application settings. The editor uses a tabbed layout (e.g., "General", "Output & Naming") to organize settings.

Any changes made in the GUI Configuration Editor require you to restart the application for them to take effect.

*(Ideally, a screenshot of the GUI Configuration Editor would be included here.)*