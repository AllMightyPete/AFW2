# Asset System - Application Flow

## Application: CG Asset Organiser

**Description:** A portable Python application for artists that organizes unstructured files from various suppliers into a uniform, customizable file system. This allows for automated import and setup of assets in DCC software.

## Flow:

The application is a self-contained desktop utility built with PySide6.

1.  **Initialization:** The user launches the application executable. The main window appears, ready to accept files.

2.  **File Input:** The user drags and drops one or more source files or directories directly into the application window.

3.  **Classification:**
    -   The application reads the list of files from the source(s).
    -   The UI calls the `Classification Service`, which analyzes the file list based on the active library's configuration.
    -   The service returns a structured data object representing its initial classification.

4.  **User Review and Refinement:**
    -   The main UI displays the classified files in a hierarchical table view.
    -   The user can now interact with this data:
        -   Correct file-types using dropdowns or hotkeys.
        -   Re-assign files to different assets via drag-and-drop.
        -   Rename assets or create new ones.
    -   The UI directly manipulates an in-memory data model that acts as the "source of truth" for the current session.

5.  **Processing:**
    -   Once satisfied, the user clicks the "Process" button.
    -   The UI calls the `Processing Service`, passing it the final, user-approved data model and the path to the source files.
    -   The `Processing Service` runs the entire processing plan (renaming, resizing, packing, etc.) and writes the final assets to the designated library path.

6.  **Indexing (Optional):**
    -   If semantic search is enabled, the `Processing Service` notifies the `Indexing Service` upon successful completion.
    -   The `Indexing Service` then generates vector embeddings for the new assets and adds them to the library's vector database.

### UI Data Structure Example:

The UI manages a data structure that represents the state of the files being organized. This structure is initialized by the `Classification Service` and modified by the user.

```json
{
  "Source01.zip": {
    "metadata": {
      "normal_format": "OpenGL",
      "supplier": "AssetSupplier01",
      "SHA256-ID": "SHA256-Digits-Of-Archive-Or-First-Found-File-In-Directory"
    },
    "contents": {
      "01": { "filename": "File01.jpg", "filetype": "MAP_COL" },
      "02": { "filename": "File02.jpg", "filetype": "MAP_NRM" },
      "03": { "filename": "Folder/File03.txt", "filetype": "IGNORE" },
      "04": { "filename": "File04.fbx", "filetype": "FILE_MODEL" },
      "05": { "filename": "File05.jpg", "filetype": "UNIDENTIFIED" }
    },
    "Assets": {
      "Assetname01": {
        "Assettype": "Model",
        "Assettags": [ "Tag01", "Tag02" ],
        "AssetContents": [ "01", "02", "04", "05" ]
      }
    }
  }
}
```

### UI Workspace Mockup:

A detailed mockup and description of the UI is available in the [[Asset System - UI Interaction]] document.
