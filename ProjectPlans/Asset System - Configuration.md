# Asset System - Configuration

The power of the application lies in its deep customizability. The user can edit all apects of the classification and processing logic via a dedicated configuration UI. The UI sends changes to the `ConfigService`, which validates them, persists them to disk, and makes them available for all subsequent operations.

---
## Configuration UI Design

The "Settings" view in the application provides a structured and user-friendly way to edit the configuration. It uses a two-panel layout, with a list of categories on the left and a dedicated editor for the selected category on the right.

### 1. General Settings
This page controls the fundamental I/O of the processor.
-   **Layout:** A simple form with labeled fields.
-   **Fields:**
    -   **Output Base Directory:** Text input with a "Browse" button.
    -   **Output Directory Pattern:** Text input displaying available tokens (e.g., `[supplier]`, `[assettype]`).
    -   **Output Filename Pattern:** Text input displaying available tokens (e.g., `[assetname]`, `[filetype]`).
    -   **Default Asset Type:** Dropdown menu populated from user-defined `Asset Types`.
    -   **Metadata Filename:** Text input, defaulting to `metadata.json`.

### 2. File Types Settings
This page manages the definitions of all file types.
-   **Layout:** A master-detail view.
    -   **Master (Left):** A searchable list of all defined `File-Types` with "Add" and "Remove" buttons.
    -   **Detail (Right):** A form to edit the properties of the selected `File-Type`.
-   **Detail Form Fields:** ID (read-only), Alias, UI Color, UI Hotkey, Is Standalone (boolean), LLM Description, LLM Examples (tag editor).

### 3. Asset Types Settings
Similar to File Types, but simpler.
-   **Layout:** A master-detail view.
    -   **Master (Left):** List of `Asset-Types` with "Add/Remove" buttons.
    -   **Detail (Right):** Form for the selected type.
-   **Detail Form Fields:** ID (read-only), Description, Examples, UI Color.

### 4. Suppliers Settings
-   **Layout:** A simple table view.
-   **Columns:** `Supplier Name`, `Default Normal Map Format (OpenGL/DirectX)`.
-   **Functionality:** "Add" and "Remove" buttons to manage rows.

### 5. Classification Settings
This page holds the "brains" for the classification service.
-   **Layout:** A tabbed view within the editor panel.
-   **Tabs:**
    -   **Providers:** A master-detail view to manage LLM connections.
        -   **Master:** A list of provider profiles (e.g., "OpenAI - GPT-4o"). Includes "Add/Remove" buttons and a radio button to select the active profile.
        -   **Detail:** A form to edit the selected profile's `Profile Name`, `Provider` (dropdown), `API Key` (masked input), and `Model Endpoint`.
    -   **LLM Prompts:** A text editor for editing the main system prompt used by the LLM.
    -   **Keyword Rules:** A table to define direct `Keyword` to `File Type` mappings for fast, non-LLM classification.

### 6. Processing Settings
This page defines the "how" of the processing stage.
-   **Layout:** A tabbed view.
-   **Tabs:**
    -   **Channel Packing:** A master-detail view where the detail panel is a visual editor for RGBA channels with dropdowns to select source `File-Types`.
    -   **Export Profiles:** A master-detail view to manage profiles. The detail form fields dynamically change based on the selected export module (e.g., PNG, JPG).
    -   **Image Resolutions:** A list editor to define resolution names and their corresponding pixel widths (e.g., `4K` -> `4096`).

### 7. Indexing Settings
This page controls the semantic search feature.
-   **Layout:** A simple form.
-   **Fields:**
    -   **Enable Semantic Search:** Checkbox.
    -   **Embedding Model:** Dropdown of compatible models.
    -   **Rendering Engine (for 3D models):** Dropdown (e.g., "Internal", "Blender").
    -   **"Re-index Entire Library" button** with a confirmation dialog.

---
## Configuration File Examples

Below are examples of the JSON structures that the UI will be editing.

### Asset-Type & File-Type Definitions
The user can define their own library of `Asset-Types` and `File-Types`.

#### File-Type Definition Example
```json
{
  "FILE_TYPE_DEFINITIONS": {
    "MAP_COL": {
      "alias": "COL",
      "bit_depth_policy": "force_8bit",
      "is_grayscale": false,
      "is_standalone": false,
      "UI-color": "#ffaa00",
      "UI-keybind": "C",
      "LLM-description": "Color/Albedo Map",
      "LLM-examples": [ "_col.", "_basecolor.", "albedo", "diffuse" ]
    },
    "MAP_NRM": {
      "alias": "NRM",
      "bit_depth_policy": "preserve",
      "is_grayscale": false,
      "is_standalone": false,
      "UI-color": "#cca2f1",
      "UI-keybind": "N",
      "LLM-description": "Normal Map",
      "LLM-examples": [ "_nrm.", "_normal." ],
      "OVERRIDE_EXPORT_PROFILES": {
        "8-bit-lossy": "JPG-Normal-100"
      }
    }
  }
}
```

#### Asset-Type Definition Example
```json
{
  "ASSET_TYPE_DEFINITIONS": {
    "Surface": {
      "color": "#1f3e5d",
      "LLM-description": "A single Standard PBR material set for a surface.",
      "LLM-examples": [ "Set: Wood01_COL + Wood01_NRM + WOOD01_ROUGH" ]
    },
    "Model": {
      "color": "#b67300",
      "LLM-description": "A set that contains models, can include PBR textureset",
      "LLM-examples": [ "Set = Plant02.fbx + Plant02_col + Plant02_SSS" ]
    }
  }
}
```

### General Settings Example
Global parameters that control the `Processor`.
```json
{
  "OUTPUT_BASE_DIR": "../Asset_Library",
  "OUTPUT_DIRECTORY_PATTERN": "[supplier]/[assettype]/[assetname]",
  "OUTPUT_FILENAME_PATTERN": "[assetname]_[filetype]_[resolution]",
  "METADATA_FILENAME": "metadata.json",
  "RESOLUTION_THRESHOLD_FOR_LOSSY": 4096,
  "IMAGE_RESOLUTIONS": {
    "8K": 8192,
    "4K": 4096,
    "2K": 2048,
    "1K": 1024,
    "PREVIEW": 128
  },
  "DEFAULT_EXPORT_PROFILES": {
    "16-bit": "EXR-DWAA-16bit",
    "8-bit-lossless": "PNG-lossless-8bit",
    "8-bit-lossy": "JPG-quality-95"
  },
  "CALCULATE_STATS_RESOLUTION": "1K",
  "DEFAULT_ASSET_TYPE": "Surface",
  "MERGE_DIMENSION_MISMATCH_STRATEGY": "USE_LARGEST"
}
```

### Channel Packing Rules Example
A list of recipes for the `Processor` to create new packed textures.
```json
{
  "MAP_MERGE_RULES": [
    {
      "output_file_type": "MAP_ARM",
      "inputs": {
        "R": {"file_type": "MAP_AO", "channel": "Grayscale"},
        "G": {"file_type": "MAP_ROUGH", "channel": "Grayscale"},
        "B": {"file_type": "MAP_METAL", "channel": "Grayscale"}
      },
      "defaults": { "R": 1, "G": 1, "B": 0 },
      "output_bit_depth": "preserve"
    }
  ]
}
```

### File Export Profiles Example
User-defined presets for saving image files, leveraging dedicated modules for each file format.
```json
{
  "FILE_EXPORT_PROFILES": {
    "JPG-quality-95": {
      "module": "JPG",
      "settings": {
        "quality": 95,
        "chroma_subsampling": "4:4:4"
      }
    },
    "PNG-lossless-8bit": {
      "module": "PNG",
      "settings": {
        "bit_depth": 8,
        "compression_level": 6 
      }
    },
    "EXR-DWAA-16bit": {
      "module": "EXR",
      "settings": {
        "bit_depth": "half",
        "compression": "DWAA"
      }
    }
  }
}
```

### Other Configurations
- **Suppliers:** A list of known asset suppliers and their default properties.
  - JSON key for normal map preference: `default_normal_format` (e.g., `OpenGL`, `DirectX`).
- **LLM Settings:**
    - **Model Profiles:** A list of LLM providers, endpoints, and the user's API keys.
    - **System Prompts:** The user can edit the underlying system prompts used by the `Classification Service`.
