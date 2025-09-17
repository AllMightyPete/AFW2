# Plan for New Definitions Editor UI

## 1. Overview

This document outlines the plan to create a new, dedicated UI for managing "Asset Type Definitions", "File Type Definitions", and "Supplier Settings". This editor will provide a more structured and user-friendly way to manage these core application configurations, which are currently stored in separate JSON files.

## 2. General Design Principles

*   **Dedicated Dialog:** The editor will be a new `QDialog` (e.g., `DefinitionsEditorDialog`).
*   **Access Point:** Launched from the `MainWindow` menu bar (e.g., under a "Definitions" menu or "Edit" -> "Edit Definitions...").
*   **Tabbed Interface:** The dialog will use a `QTabWidget` to separate the management of different definition types.
*   **List/Details View:** Each tab will generally follow a two-pane layout:
    *   **Left Pane:** A `QListWidget` displaying the primary keys or names of the definitions (e.g., asset type names, file type IDs, supplier names). Includes "Add" and "Remove" buttons for managing these primary entries.
    *   **Right Pane:** A details area (e.g., `QGroupBox` with a `QFormLayout`) that shows the specific settings for the item selected in the left-pane list.
*   **Data Persistence:** The dialog will load from and save to the respective JSON configuration files:
    *   Asset Types: `config/asset_type_definitions.json`
    *   File Types: `config/file_type_definitions.json`
    *   Supplier Settings: `config/suppliers.json` (This file will be refactored from a simple list to a dictionary of supplier objects).
*   **User Experience:** Standard "Save" and "Cancel" buttons, with a check for unsaved changes.

## 3. Tab-Specific Plans

### 3.1. Asset Type Definitions Tab

*   **Manages:** `config/asset_type_definitions.json`
*   **UI Sketch:**
    ```mermaid
    graph LR
        subgraph AssetTypeTab [Asset Type Definitions Tab]
            direction LR
            AssetList[QListWidget (Asset Type Keys e.g., "Surface")] --> AssetDetailsGroup{Details for Selected Asset Type};
        end

        subgraph AssetDetailsGroup
            direction TB
            Desc[Description: QTextEdit]
            Color[Color: QPushButton ("Choose Color...") + Color Swatch Display]
            Examples[Examples: QListWidget + Add/Remove Example Buttons]
        end
        AssetActions["Add Asset Type (Prompt for Name)\nRemove Selected Asset Type"] --> AssetList
    ```
*   **Details:**
    *   **Left Pane:** `QListWidget` for asset type names. "Add Asset Type" (prompts for new key) and "Remove Selected Asset Type" buttons.
    *   **Right Pane (Details):**
        *   `description`: `QTextEdit`.
        *   `color`: `QPushButton` opening `QColorDialog`, with an adjacent `QLabel` to display the color swatch.
        *   `examples`: `QListWidget` with "Add Example" (`QInputDialog.getText`) and "Remove Selected Example" buttons.

### 3.2. File Type Definitions Tab

*   **Manages:** `config/file_type_definitions.json`
*   **UI Sketch:**
    ```mermaid
    graph LR
        subgraph FileTypeTab [File Type Definitions Tab]
            direction LR
            FileList[QListWidget (File Type Keys e.g., "MAP_COL")] --> FileDetailsGroup{Details for Selected File Type};
        end

        subgraph FileDetailsGroup
            direction TB
            DescF[Description: QTextEdit]
            ColorF[Color: QPushButton ("Choose Color...") + Color Swatch Display]
            ExamplesF[Examples: QListWidget + Add/Remove Example Buttons]
            StdType[Standard Type: QLineEdit]
            BitDepth[Bit Depth Rule: QComboBox ("respect", "force_8bit", "force_16bit")]
            IsGrayscale[Is Grayscale: QCheckBox]
            Keybind[Keybind: QLineEdit (1 char)]
        end
        FileActions["Add File Type (Prompt for ID)\nRemove Selected File Type"] --> FileList
    ```
*   **Details:**
    *   **Left Pane:** `QListWidget` for file type IDs. "Add File Type" (prompts for new key) and "Remove Selected File Type" buttons.
    *   **Right Pane (Details):**
        *   `description`: `QTextEdit`.
        *   `color`: `QPushButton` opening `QColorDialog`, with an adjacent `QLabel` for color swatch.
        *   `examples`: `QListWidget` with "Add Example" and "Remove Selected Example" buttons.
        *   `standard_type`: `QLineEdit`.
        *   `bit_depth_rule`: `QComboBox` (options: "respect", "force_8bit", "force_16bit").
        *   `is_grayscale`: `QCheckBox`.
        *   `keybind`: `QLineEdit` (validation for single character recommended).

### 3.3. Supplier Settings Tab

*   **Manages:** `config/suppliers.json` (This file will be refactored to a dictionary structure, e.g., `{"SupplierName": {"normal_map_type": "OpenGL", ...}}`).
*   **UI Sketch:**
    ```mermaid
    graph LR
        subgraph SupplierTab [Supplier Settings Tab]
            direction LR
            SupplierList[QListWidget (Supplier Names)] --> SupplierDetailsGroup{Details for Selected Supplier};
        end

        subgraph SupplierDetailsGroup
            direction TB
            NormalMapType[Normal Map Type: QComboBox ("OpenGL", "DirectX")]
            %% Future supplier-specific settings can be added here
        end
        SupplierActions["Add Supplier (Prompt for Name)\nRemove Selected Supplier"] --> SupplierList
    ```
*   **Details:**
    *   **Left Pane:** `QListWidget` for supplier names. "Add Supplier" (prompts for new name) and "Remove Selected Supplier" buttons.
    *   **Right Pane (Details):**
        *   `normal_map_type`: `QComboBox` (options: "OpenGL", "DirectX"). Default for new suppliers: "OpenGL".
        *   *(Space for future supplier-specific settings).*
*   **Data Handling Note for `config/suppliers.json`:**
    *   The editor will load from and save to `config/suppliers.json` using the new dictionary format (supplier name as key, object of settings as value).
    *   Initial implementation might require `config/suppliers.json` to be manually updated to this new format if it currently exists as a simple list. Alternatively, the editor could attempt an automatic conversion on first load if the old list format is detected, or prompt the user. For the first pass, assuming the editor works with the new format is simpler.

## 4. Implementation Steps (High-Level)

1.  **(Potentially Manual First Step) Refactor `config/suppliers.json`:** If `config/suppliers.json` exists as a list, manually convert it to the new dictionary structure (e.g., `{"SupplierName": {"normal_map_type": "OpenGL"}}`) before starting UI development for this tab, or plan for the editor to handle this conversion.
2.  **Create `DefinitionsEditorDialog` Class:** Inherit from `QDialog`.
3.  **Implement UI Structure:** Main `QTabWidget`, and for each tab, the two-pane layout with `QListWidget`, `QGroupBox` for details, and relevant input widgets (`QLineEdit`, `QTextEdit`, `QComboBox`, `QCheckBox`, `QPushButton`).
4.  **Implement Loading Logic:**
    *   For each tab, read data from its corresponding JSON file.
    *   Populate the left-pane `QListWidget` with the primary keys/names.
    *   Store the full data structure internally (e.g., in dictionaries within the dialog instance).
5.  **Implement Display Logic:**
    *   When an item is selected in a `QListWidget`, populate the right-pane detail fields with the data for that item.
6.  **Implement Editing Logic:**
    *   Ensure that changes made in the detail fields (text edits, combobox selections, checkbox states, color choices, list example modifications) update the corresponding internal data structure for the currently selected item.
7.  **Implement Add/Remove Functionality:**
    *   For each definition type (Asset Type, File Type, Supplier), implement the "Add" and "Remove" buttons.
        *   "Add": Prompt for a unique key/name, create a new default entry in the internal data, and add it to the `QListWidget`.
        *   "Remove": Remove the selected item from the `QListWidget` and the internal data.
    *   For "examples" lists within Asset and File types, implement their "Add Example" and "Remove Selected Example" buttons.
8.  **Implement Saving Logic:**
    *   When the main "Save" button is clicked:
        *   Write the (potentially modified) Asset Type definitions data structure to `config/asset_type_definitions.json`.
        *   Write File Type definitions to `config/file_type_definitions.json`.
        *   Write Supplier settings (in the new dictionary format) to `config/suppliers.json`.
    *   Consider creating new dedicated save functions in `configuration.py` for each of these files if they don't already exist or if existing ones are not suitable.
9.  **Implement Unsaved Changes Check & Cancel Logic.**
10. **Integrate Dialog Launch:** Add a menu action in `MainWindow.py` to open the `DefinitionsEditorDialog`.

This plan provides a comprehensive approach to creating a dedicated editor for these crucial application definitions.