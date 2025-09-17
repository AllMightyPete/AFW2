# Asset System - Metadata Schema

This document defines the structure and contents of the `metadata.json` file that is generated for every asset processed by the Asset Organiser. This file acts as a self-contained "map" or "descriptor" for the asset, providing all the necessary information for external tools, such as DCC importers, to understand and utilize the asset correctly.

## Purpose

-   **DCC Integration:** To provide a standardized data structure that DCC plugins can parse to automatically import models, create materials, and assign textures.
-   **Asset Indexing:** To act as a manifest of all files belonging to the asset, their roles, and their properties.
-   **Data Integrity:** To store critical processing information, such as original file resolutions, applied transformations (e.g., stretching), and quality metrics.
-   **Future-Proofing:** To create a flexible schema that can be extended with new information without breaking existing importers.

## Schema Definition

This schema is optimized for efficiency and clarity. It avoids storing redundant data by defining a `filename_pattern` that allows importers to construct file paths at runtime. Information common to all resolutions of a map (like `aspect_ratio` and `stats`) is stored only once.

```json
{
  "asset_id": "a4c8f1b2e...",
  "asset_name": "Worn_Painted_Wood_Planks",
  "asset_type": "Surface",
  "supplier": "ExampleTextures",
  "filename_pattern": "[assetname]_[filetype]_[resolution]",
  "processing_timestamp_utc": "2025-07-26T10:30:00Z",
  "app_version": "2.1.0",
  "files": [
    {
      "type": "MAP_COL",
      "bit_depth": 8,
      "aspect_ratio": "1:1",
      "stats": { "mean": 0.45, "min": 0.02, "max": 0.98 },
      "resolutions": {
        "4K": { "dimensions": [4096, 4096], "file_extension": "png" },
        "2K": { "dimensions": [2048, 2048], "file_extension": "png" },
        "1K": { "dimensions": [1024, 1024], "file_extension": "png" },
        "PREVIEW": { "dimensions": [128, 128], "file_extension": "jpg" }
      }
    },
    {
      "type": "MAP_NRM",
      "bit_depth": 8,
      "aspect_ratio": "1:1",
      "normal_format": "DirectX",
      "stats": { "mean": 0.5, "min": 0.0, "max": 1.0 },
      "resolutions": {
        "4K": { "dimensions": [4096, 4096], "file_extension": "png" }
      }
    },
    {
      "type": "FILE_MODEL",
      "path": "./Worn_Painted_Wood_Planks.fbx",
      "poly_count": 1500
    }
  ],
  "available_resolutions": ["4K", "2K", "1K", "PREVIEW"],
  "tags": ["wood", "planks", "painted"]
}
```

Notes:
- Filename patterns use underscores (e.g., `[assetname]_[filetype]_[resolution]`) for consistency with processing outputs.
- Paths in metadata use forward slashes for cross-platform clarity; the application normalizes OS-specific paths at runtime.

## Field Descriptions

-   **asset_id**: A unique identifier for the asset.
-   **asset_name**: The final, clean name of the asset.
-   **asset_type**: The classification of the asset (e.g., "Surface", "Model").
-   **supplier**: The original supplier of the asset.
-   **filename_pattern**: The template used for constructing image filenames. A DCC importer will substitute tokens like `[assetname]`, `[filetype]`, and `[resolution]` at runtime.
-   **processing_timestamp_utc**: The ISO 8601 timestamp of when the asset was processed.
-   **app_version**: The version of the Asset Organiser used to process the asset.
-   **files**: An array of objects. Each object represents a logical file type (e.g., `MAP_COL`) or a unique file (e.g., `FILE_MODEL`).
    -   **type**: The `File-Type` of the file (e.g., "MAP_COL").
    -   **path**: For non-procedurally named files (like models), the explicit relative path.
    -   **bit_depth**, **aspect_ratio**, **stats**, **normal_format**: Properties common to all resolutions of an image type.
    -   **poly_count / vertex_count**: For model files, stores geometry information.
    -   **resolutions**: An object present for image types. The keys are descriptive names (e.g., "4K", "PREVIEW") and the values are objects containing resolution-specific data.
        -   **dimensions**: The pixel dimensions as an `[x, y]` array.
        -   **file_extension**: The file extension (e.g., "png", "jpg") for this specific resolution.
-   **available_resolutions**: An array of strings listing all resolution keys generated for this asset.
-   **tags**: An array of semantic tags.
