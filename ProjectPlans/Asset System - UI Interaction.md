# Asset System - UI Interaction

## Overall Application Design

The application is designed as a single-window experience to provide a seamless and focused workflow. Navigation is handled by a main sidebar on the left, which switches between the application's primary contexts: **Workspace**, **Library**, and **Settings**. The area to the right of the sidebar is the main content area, which updates based on the selected view.

```
+-----------------------------------------------------------------------------+
| [ICON] Workspace   |                                                        |
| [ICON] Library     |                                                        |
| [ICON] Settings    |               MAIN CONTENT AREA                        |
|                    |                                                        |
|                    |                                                        |
|                    |                                                        |
|                    |                                                        |
|--------------------|                                                        |
| Status Bar: Ready                                                           |
+-----------------------------------------------------------------------------+
```

---

## 1. Workspace View

This is the primary "working" area where the core workflow of input -> classify -> process occurs. It is designed as a single, unified panel to give the user a complete overview of all loaded sources at once, directly aligning with the vision in the "Application Flow" document.

-   **Purpose:** To manage the classification and processing of all new assets in a single, unified tree.
-   **Layout:** A single panel containing the "Unified Asset Tree".
    -   **Unified Asset Tree:** This is the central component. The hierarchy is structured as:
        -   **Top-Level:** Source nodes (e.g., `BrownBark013.zip`). Each is collapsible.
        -   **Second-Level:** Asset nodes within each source.
        -   **Third-Level:** File nodes within each asset.
    -   File-Type IDs are displayed in uppercase (e.g., `MAP_COL`, `FILE_MODEL`) and use colors/hotkeys sourced from the configuration.
    -   This structure allows the user to see and manage multiple sources and their contents in one continuous view. All interactive elements (dropdowns for types, renaming fields, drag-and-drop) are present at their respective levels in the tree.
-   **Toolbar:** Located at the top of the view, containing all relevant actions:
    -   **"Add Source(s)"**: Opens a file dialog to add new files/folders.
    -   **"Remove Selected"**: Removes the selected source, asset, or file from the tree.
    -   **"Classify Selected"**: Runs the `Classification Service` on the currently selected Source node(s).
    -   **"Process All"**: Runs the `Processing Service` on every source currently loaded in the tree.

### Workspace Mockup

```
+-----------------------------------------------------------------------------+
| Workspace | [Toolbar: Add | Remove | Classify Selected | Process All]        |
| Library   | +---------------------------------------------------------------+
| Settings  | | ▼ Source: BrownBark013.zip [Supplier: Poliigon ▼]             |
|           | |   └─ ▼ Asset: BrownBark_3K [Type: Surface ▼]                  |
|           | |      ├─ Bark_COL.jpg      [File Type: MAP_COL ▼]              |
|           | |      ├─ Bark_NRM.jpg      [File Type: MAP_NRM ▼]              |
|           | |      └─ Bark_ROUGH.jpg    [File Type: MAP_ROUGH ▼]            |
|           | | ▼ Source: Concrete_Set_04/ [Supplier: Textures.com ▼]         |
|           | |   └─ ...                                                      |
+-----------------------------------------------------------------------------+
```

---

## 2. Library View

This view is for interacting with the final, processed asset library.

-   **Purpose:** To search, browse, and inspect already processed assets.
-   **Layout:**
    -   **Top Search/Filter Bar:**
        -   A prominent **semantic search bar** for natural language queries (optional; shown only when indexing is enabled).
        -   Additional filter controls for `Asset-Type`, `Supplier`, `Tags`, etc.
    -   **Main Area: "Results Grid"**
        -   Displays search results as a grid of asset thumbnails.
    -   **Side Panel: "Metadata Inspector"**
        -   When an asset thumbnail is selected, this panel displays its detailed information, read from its `metadata.json` file.
        -   Includes a larger preview image, asset name, type, a list of all associated files, available resolutions, and tags.
        -   Provides a button to "Show in File Explorer".

---

## 3. Settings View

This view consolidates all application and library configurations into a single, organized area.

-   **Purpose:** To manage all the rules, definitions, and settings that control the classification and processing logic.
-   **Layout:** A two-panel view.
    -   **Left Panel: "Settings Categories"**
        -   A navigation list of all configurable areas:
            -   `General`: Output paths, naming patterns.
            -   `File Types`: Definitions, colors, keywords.
            -   `Asset Types`: Definitions, descriptions.
            -   `Suppliers`: List of known asset suppliers.
            -   `Classification`: LLM system prompts, keyword-based rules.
            -   `Processing`: Channel packing recipes, image export profiles.
            -   `Indexing`: Semantic search model configuration.
    -   **Right Panel: "Configuration Editor"**
        -   A dynamic area that displays the appropriate editor for the category selected on the left. For example, selecting `File Types` shows a table for managing file type definitions.

---

## Interaction Tools (within Workspace View)

The user has various tools available for correcting and refining the classification of assets. While the `Classification Service` performs the initial automated organization, the user always has the final say through these direct manipulation tools within the **Unified Asset Tree**.

### File-Type Assigning Tools:

-   **Dropdown Menu:** Directly change a file's type using the dropdown menu next to its name in the table.
-   **Hotkeys:** Select one or more files and use keyboard shortcuts to assign a specific `File-Type`.

### Asset Grouping Tools:

-   **Drag and Drop:** Re-assign a file to a different asset group by simply dragging it from one group to another.
-   **Rename to Reassign:** Change the asset group for all its contained files by editing the `Assetname` field in the table. New asset groups can be created this way.
-   **Automatic Dissolving:** Asset groups are automatically removed if they no longer contain any files, keeping the workspace clean.
