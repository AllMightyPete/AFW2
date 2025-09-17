Asset System - Processor

Once the user has reviewed and approved the classifications in the UI, they can stage the source(s) for processing. The **Processor** is the service responsible for executing this final, transformative stage.

The UI initiates a job by calling the `ProcessingService`, providing it with the "source of truth" JSON object, the location of the original source files, and a **snapshot of all relevant processing rules** (e.g., output paths, naming patterns, channel packing recipes, export profiles). This ensures the processing job runs with a consistent set of rules from start to finish.

To optimize performance and handle multiple inputs, each source is processed in a parallel subprocess.

### The Processing Plan

A key architectural concept is the "processing-plan". Before any files are actually written or heavily manipulated, the processor first generates a step-by-step plan for each asset based on the configuration it received. This plan outlines all the required operations. The plan is then executed in a single pass where possible, minimizing I/O and preventing redundant operations (e.g., opening and saving the same image multiple times for different steps).

The processing plan for an asset can include the following steps:

- **Archive Extraction:** The source archive (e.g., `.zip`) is extracted to a temporary location for processing.
    
- **Handling of Extra Files:** Files classified with the `FILE_EXTRA` type are moved directly to a sub-folder named `Extra` within the asset directory. They are not processed further.
    
- **File Naming & Directory Structure:** Files are renamed and placed into a directory structure based on a user-defined token system.
    
    > _Example Path:_ `[supplier]/[assettype]/[assetname]/[assetname]_[filetype]_[resolution].[ext]`
    
- **Image Resizing:** Source images are downscaled to create a complete set of textures. The processor will generate a version for every resolution defined in the `IMAGE_RESOLUTIONS` configuration that is less than or equal to the source image's resolution.
    
    > _Example:_ If the user has defined `["8K", "4K", "2K", "1K"]` in their settings and the source image is 8K, the processor will export all four versions. If the source is 4K, it will export 4K, 2K, and 1K versions.
    
- **Normal Map Correction:** The green channel of normal maps is automatically inverted to conform to the output standard (e.g., converting an input "OpenGL" map to "DirectX").
    
- **Gloss to Roughness Conversion:** To standardize the material pipeline, any file identified with the `MAP_GLOSS` file-type is automatically inverted during processing. The output file is then treated as a `MAP_ROUGH` for all subsequent steps, including naming.
    
- **Channel Packing:** New images are created by packing specific channels from different source maps.
    
- **Channel Extraction:** Single channels are extracted from a source image to create new, separate files.
    
- **Image Stretching:** Optionally stretches images to the nearest power-of-two dimensions. The non-uniform scaling factor is saved in the asset's metadata for later use in a DCC.
    
- **Image Format Profile-Based Exporting:** This final step saves the processed image data. The processor uses a direct mapping from the general settings to assign an export profile based on conditions like bit depth. The selected profile's settings are then passed to the appropriate file-format module. (JPG, PNG, EXR, QOIF)
    
- **Histogram Analysis:** For each channel of every processed image, calculate and store basic histogram statistics (Minimum, Maximum, Mean, and Median values). This data is saved into the asset's metadata.
    
- **Metadata Generation:** For each processed asset group, a `metadata.json` file is saved. This file acts as an index for the asset, containing crucial information for later use, as defined in the [[Asset System - Metadata Schema]].
    

### Phase 1: Planning (Building the Dependency Graph)

The "brain" of the processor. It builds a complete map of all required operations before performing any heavy file manipulation. This happens in two stages:

1. **Initial Plan Generation:** The planner creates a preliminary dependency graph based on the user-defined outputs from the provided configuration.
    
2. **Plan Refinement & Expansion:** The planner then performs a lightweight metadata check on the source files. Using a set of **Implied Task Rules** from the provided configuration, it discovers and adds new tasks to the graph. For example, if it finds an alpha channel in a `MAP_COL` file, it will dynamically add the steps required to extract and save it as a `MAP_MASK`.
    

The output of this phase is a final, complete **Processing Plan**.

### Phase 2: Execution (Processing the Graph)

The processor executes the generated plan. Using an in-memory cache, it traverses the dependency graph, ensuring that each source file is loaded only once and each transformation (like inverting a gloss map) is performed only once, even if the results are used in multiple different output files.

### Example Processing Plan

This example shows the final JSON plan for an asset that requires resizing, gloss-to-rough inversion, channel packing, and a discovered mask extraction.

```json
{
  "nodes": {
    "src_col":   { "op": "load", "path": "/temp/source/Albedo.png" },
    "src_gloss": { "op": "load", "path": "/temp/source/Gloss.png" },
    "src_ao":    { "op": "load", "path": "/temp/source/AO.png" },
    
    "rough_map_highres": { "op": "invert", "source": "src_gloss" },
    "mask_map_highres":  { "op": "extract_channel", "source": "src_col", "channel": "A" },

    "col_4k":    { "op": "resize", "source": "src_col", "size": 4096 },
    "rough_4k":  { "op": "resize", "source": "rough_map_highres", "size": 4096 },
    "ao_4k":     { "op": "resize", "source": "src_ao", "size": 4096 },
    "mask_4k":   { "op": "resize", "source": "mask_map_highres", "size": 4096 },
    
    "packed_arm_4k": {
      "op": "pack_channels",
      "sources": { "R": "ao_4k", "G": "rough_4k", "B": "..." }
    }
  },
  "exports": [
    { "node": "col_4k", "profile": "PNG-8bit", "path": "/Library/Asset/asset_col_4k.png"},
    { "node": "mask_4k", "profile": "PNG-8bit", "path": "/Library/Asset/asset_mask_4k.png"},
    { "node": "packed_arm_4k", "profile": "PNG-8bit", "path": "/Library/Asset/asset_arm_4k.png"}
  ]
}
```

### Phase 3: Exporting

After all files have successfully been processed in a temp directory, these files are then moved to their desired output path - Assets that contain errors are instead and their temporary path is deleted. An error report is returned to the UI.

### Indexing Integration

If semantic search is enabled, the `ProcessingService` will notify the `IndexingService` after successful exports. The `IndexingService` writes embeddings to a library-scoped database located at `.asset-library/index.db` within the target asset library root.
