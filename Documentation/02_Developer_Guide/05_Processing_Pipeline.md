Cl# Developer Guide: Processing Pipeline

This document details the step-by-step technical process executed by the asset processing pipeline, which is initiated by the [`ProcessingEngine`](processing_engine.py:73) class (`processing_engine.py`) and orchestrated by the [`PipelineOrchestrator`](processing/pipeline/orchestrator.py:36) (`processing/pipeline/orchestrator.py`).

The [`ProcessingEngine.process()`](processing_engine.py:131) method serves as the main entry point. It initializes a [`PipelineOrchestrator`](processing/pipeline/orchestrator.py:36) instance, providing it with the application's [`Configuration`](configuration.py:68) object and predefined lists of pre-item and post-item processing stages. The [`PipelineOrchestrator.process_source_rule()`](processing/pipeline/orchestrator.py:95) method then manages the execution of these stages for each asset defined in the input [`SourceRule`](rule_structure.py:40).

A crucial component in this architecture is the [`AssetProcessingContext`](processing/pipeline/asset_context.py:86) (`processing/pipeline/asset_context.py`). An instance of this dataclass is created for each [`AssetRule`](rule_structure.py:22) being processed. It acts as a stateful container, carrying all relevant data (source files, rules, configuration, intermediate results, metadata) and is passed sequentially through each stage. Each stage can read from and write to the context, allowing data to flow and be modified throughout the pipeline.

The pipeline execution for each asset follows this general flow:

1.  **Pre-Item Stages:** A sequence of stages executed once per asset before the core item processing loop. These stages typically perform initial setup, filtering, and asset-level transformations.
2.  **Core Item Processing Loop:** The [`PipelineOrchestrator`](processing/pipeline/orchestrator.py:36) iterates through a list of "processing items" (individual files or merge tasks) prepared by a dedicated stage. For each item, a sequence of core processing stages is executed.
3.  **Post-Item Stages:** A sequence of stages executed once per asset after the core item processing loop is complete. These stages handle final tasks like organizing output files and saving metadata.

## Pipeline Stages

The stages are executed in the following order for each asset:

### Pre-Item Stages

These stages are executed sequentially once for each asset before the core item processing loop begins.

1.  **[`SupplierDeterminationStage`](processing/pipeline/stages/supplier_determination.py:6)** (`processing/pipeline/stages/supplier_determination.py`):
    *   **Responsibility**: Determines the effective supplier for the asset based on the [`SourceRule`](rule_structure.py:40)'s `supplier_override`, `supplier_identifier`, and validation against configured suppliers.
    *   **Context Interaction**: Sets `context.effective_supplier` and may set a `supplier_error` flag in `context.status_flags`.

2.  **[`AssetSkipLogicStage`](processing/pipeline/stages/asset_skip_logic.py:5)** (`processing/pipeline/stages/asset_skip_logic.py`):
    *   **Responsibility**: Checks if the entire asset should be skipped based on conditions like a missing/invalid supplier, a "SKIP" status in asset metadata, or if the asset is already processed and overwrite is disabled.
    *   **Context Interaction**: Sets the `skip_asset` flag and `skip_reason` in `context.status_flags` if the asset should be skipped.

3.  **[`MetadataInitializationStage`](processing/pipeline/stages/metadata_initialization.py:81)** (`processing/pipeline/stages/metadata_initialization.py`):
    *   **Responsibility**: Initializes the `context.asset_metadata` dictionary with base information derived from the [`AssetRule`](rule_structure.py:22), [`SourceRule`](rule_structure.py:40), and [`Configuration`](configuration.py:68). This includes asset name, IDs, source/output paths, timestamps, and initial status.
    *   **Context Interaction**: Populates `context.asset_metadata`. Initializes `context.processed_maps_details` and `context.merged_maps_details` as empty dictionaries (these are used internally by subsequent stages but are not directly part of the final `metadata.json` in their original form).

4.  **[`FileRuleFilterStage`](processing/pipeline/stages/file_rule_filter.py:10)** (`processing/pipeline/stages/file_rule_filter.py`):
    *   **Responsibility**: Filters the [`FileRule`](rule_structure.py:5) objects associated with the asset to determine which individual files should be considered for processing. It identifies and excludes files matching "FILE_IGNORE" rules based on their `item_type`.
    *   **Context Interaction**: Populates `context.files_to_process` with the list of [`FileRule`](rule_structure.py:5) objects that are not ignored.

5.  **[`GlossToRoughConversionStage`](processing/pipeline/stages/gloss_to_rough_conversion.py:15)** (`processing/pipeline/stages/gloss_to_rough_conversion.py`):
    *   **Responsibility**: Identifies processed maps in `context.processed_maps_details` whose `internal_map_type` starts with "MAP_GLOSS". If found, it loads the temporary image data, inverts it using the shared utility function [`apply_common_map_transformations`](processing/utils/image_processing_utils.py), saves a new temporary roughness map ("MAP_ROUGH"), and updates the corresponding details in `context.processed_maps_details` (setting `internal_map_type` to "MAP_ROUGH") and the relevant [`FileRule`](rule_structure.py:5) in `context.files_to_process` (setting `item_type` to "MAP_ROUGH").
    *   **Context Interaction**: Reads from and updates `context.processed_maps_details` (specifically `internal_map_type` and `temp_processed_file`) and `context.files_to_process` (specifically `item_type`).

6.  **[`AlphaExtractionToMaskStage`](processing/pipeline/stages/alpha_extraction_to_mask.py:16)** (`processing/pipeline/stages/alpha_extraction_to_mask.py`):
    *   **Responsibility**: If no mask map is explicitly defined for the asset (as a [`FileRule`](rule_structure.py:5) with `item_type="MAP_MASK"`), this stage searches `context.processed_maps_details` for a suitable source map (e.g., a "MAP_COL" with an alpha channel, based on its `internal_map_type`). If found, it extracts the alpha channel, saves it as a new temporary mask map, and adds a new [`FileRule`](rule_structure.py:5) (with `item_type="MAP_MASK"`) and corresponding details (with `internal_map_type="MAP_MASK"`) to the context.
    *   **Context Interaction**: Reads from `context.processed_maps_details`, adds a new [`FileRule`](rule_structure.py:5) to `context.files_to_process`, and adds a new entry to `context.processed_maps_details` (setting `internal_map_type`).

7.  **[`NormalMapGreenChannelStage`](processing/pipeline/stages/normal_map_green_channel.py:14)** (`processing/pipeline/stages/normal_map_green_channel.py`):
    *   **Responsibility**: Identifies processed normal maps in `context.processed_maps_details` (those with an `internal_map_type` starting with "MAP_NRM"). If the global `invert_normal_map_green_channel_globally` configuration is true, it loads the temporary image data, inverts the green channel using the shared utility function [`apply_common_map_transformations`](processing/utils/image_processing_utils.py), saves a new temporary modified normal map, and updates the `temp_processed_file` path in `context.processed_maps_details`.
    *   **Context Interaction**: Reads from and updates `context.processed_maps_details` (specifically `temp_processed_file` and `notes`).

### Core Item Processing Loop

The [`PipelineOrchestrator`](processing/pipeline/orchestrator.py:36) iterates through the `context.processing_items` list (populated by the [`PrepareProcessingItemsStage`](processing/pipeline/stages/prepare_processing_items.py:10)). Each `item` in this list is now either a [`ProcessingItem`](rule_structure.py:0) (representing a specific variant of a source map, e.g., Color at 1K, or Color at LOWRES) or a [`MergeTaskDefinition`](processing/pipeline/asset_context.py:16).

1.  **[`PrepareProcessingItemsStage`](processing/pipeline/stages/prepare_processing_items.py:10)** (`processing/pipeline/stages/prepare_processing_items.py`):
    *   **Responsibility**: (Executed once before the loop) This stage is now responsible for "exploding" each relevant [`FileRule`](rule_structure.py:5) into one or more [`ProcessingItem`](rule_structure.py:0) objects.
        *   For each [`FileRule`](rule_structure.py:5) that represents an image map:
            *   It loads the source image data and determines its original dimensions and bit depth.
            *   It creates standard [`ProcessingItem`](rule_structure.py:0)s for each required output resolution (e.g., "1K", "PREVIEW"), populating them with a copy of the source image data and the respective `resolution_key`.
            *   If the "Low-Resolution Fallback" feature is enabled (`ENABLE_LOW_RESOLUTION_FALLBACK` in config) and the source image's largest dimension is below `LOW_RESOLUTION_THRESHOLD`, it creates an additional [`ProcessingItem`](rule_structure.py:0) with `resolution_key="LOWRES"`, using the original image data and dimensions.
        *   It also adds [`MergeTaskDefinition`](processing/pipeline/asset_context.py:16)s derived from global `map_merge_rules`.
    *   **Context Interaction**: Reads `context.files_to_process` and `context.config_obj`. Populates `context.processing_items` with a list of [`ProcessingItem`](rule_structure.py:0) and [`MergeTaskDefinition`](processing/pipeline/asset_context.py:16) objects. Initializes `context.intermediate_results`.

For each `item` in `context.processing_items`:

2.  **Transformations (Implicit or via a dedicated stage - formerly `RegularMapProcessorStage` logic):**
    *   **Responsibility**: If the `item` is a [`ProcessingItem`](rule_structure.py:0), its `image_data` (loaded by `PrepareProcessingItemsStage`) may need transformations (Gloss-to-Rough, Normal Green Invert). This logic, previously in `RegularMapProcessorStage`, might be integrated into `PrepareProcessingItemsStage` before `ProcessingItem` creation, or handled by a new dedicated transformation stage that operates on `ProcessingItem.image_data`. The `item.map_type_identifier` would be updated if a transformation like Gloss-to-Rough occurs.
    *   **Context Interaction**: Modifies `item.image_data` and `item.map_type_identifier` within the [`ProcessingItem`](rule_structure.py:0) object.

3.  **[`MergedTaskProcessorStage`](processing/pipeline/stages/merged_task_processor.py:68)** (`processing/pipeline/stages/merged_task_processor.py`):
    *   **Responsibility**: (Executed if `item` is a [`MergeTaskDefinition`](processing/pipeline/asset_context.py:16)) Same as before: validates inputs, loads source map data (likely from `ProcessingItem`s in `context.processing_items` or a cache populated from them), applies transformations, merges channels, and returns [`ProcessedMergedMapData`](processing/pipeline/asset_context.py:35).
    *   **Context Interaction**: Reads [`MergeTaskDefinition`](processing/pipeline/asset_context.py:16), potentially `context.processing_items` (or a cache derived from it) for input image data. Returns [`ProcessedMergedMapData`](processing/pipeline/asset_context.py:35).

4.  **[`InitialScalingStage`](processing/pipeline/stages/initial_scaling.py:14)** (`processing/pipeline/stages/initial_scaling.py`):
    *   **Responsibility**: (Executed per item)
        *   If `item` is a [`ProcessingItem`](rule_structure.py:0): Takes `item.image_data`, `item.current_dimensions`, and `item.resolution_key` as input. If `item.resolution_key` is "LOWRES", POT scaling is skipped. Otherwise, applies POT scaling if configured.
        *   If `item` is from a `MergeTaskDefinition` (i.e., `processed_data` from `MergedTaskProcessorStage`): Applies POT scaling as before.
    *   **Context Interaction**: Takes [`InitialScalingInput`](processing/pipeline/asset_context.py:46) (now including `resolution_key`). Returns [`InitialScalingOutput`](processing/pipeline/asset_context.py:54) (also including `resolution_key`), which updates `context.intermediate_results`. The `current_image_data` and `current_dimensions` for saving are taken from this output.

5.  **[`SaveVariantsStage`](processing/pipeline/stages/save_variants.py:15)** (`processing/pipeline/stages/save_variants.py`):
    *   **Responsibility**: (Executed per item) Saves the (potentially scaled) `current_image_data`.
    *   **Context Interaction**:
        *   Takes [`SaveVariantsInput`](processing/pipeline/asset_context.py:61).
        *   `internal_map_type` is set from `item.map_type_identifier` (for `ProcessingItem`) or `processed_data.output_map_type` (for merged).
        *   `output_filename_pattern_tokens['resolution']` is set to the `resolution_key` obtained from `scaled_data_output.resolution_key` (which originates from `item.resolution_key` for `ProcessingItem`s, or is `None` for merged items that get all standard resolutions).
        *   `image_resolutions` argument for `SaveVariantsInput`:
            *   If `resolution_key == "LOWRES"`: Set to `{"LOWRES": width_of_lowres_data}`.
            *   If `resolution_key` is a standard key (e.g., "1K"): Set to `{resolution_key: configured_dimension}`.
            *   For merged items (where `resolution_key` from scaling is likely `None`): Set to the full `config.image_resolutions` map to generate all applicable standard sizes.
        *   Returns [`SaveVariantsOutput`](processing/pipeline/asset_context.py:79). Orchestrator stores details in `context.processed_maps_details`.

### Post-Item Stages

These stages are executed sequentially once for each asset after the core item processing loop has finished for all items.

1.  **[`OutputOrganizationStage`](processing/pipeline/stages/output_organization.py:14)** (`processing/pipeline/stages/output_organization.py`):
    *   **Responsibility**: Determines the final output paths for all processed maps (including variants) and extra files based on configured patterns. It copies the temporary files generated by the core stages to these final destinations, creating directories as needed and respecting overwrite settings.
    *   **Context Interaction**: Reads from `context.processed_maps_details`, `context.files_to_process` (for 'EXTRA' files), `context.output_base_path`, and [`Configuration`](configuration.py:68). Updates entries in `context.processed_maps_details` with organization status. Populates `context.asset_metadata['maps']` with the final map structure:
        *   The `maps` object is a dictionary where keys are standard map types (e.g., "COL", "REFL").
        *   Each entry contains a `variant_paths` dictionary, where keys are resolution strings (e.g., "8K", "4K") and values are the filenames of the map variants (relative to the asset's output directory).
        It also populates `context.asset_metadata['final_output_files']` with a list of absolute paths to all generated files (this list itself is not saved in the final `metadata.json`).

2.  **[`MetadataFinalizationAndSaveStage`](processing/pipeline/stages/metadata_finalization_save.py:14)** (`processing/pipeline/stages/metadata_finalization_save.py`):
    *   **Responsibility**: Finalizes the `context.asset_metadata` (setting final status based on flags). It determines the save path for the metadata file based on configuration and patterns, serializes the `context.asset_metadata` (which now contains the structured `maps` data from `OutputOrganizationStage`) to JSON, and saves the `metadata.json` file.
    *   **Context Interaction**: Reads from `context.asset_metadata` (including the `maps` structure), `context.output_base_path`, and [`Configuration`](configuration.py:68). Before saving, it explicitly removes the `final_output_files` key from `context.asset_metadata`. The `processing_end_time` is also no longer added. The `metadata.json` file is written, and `context.asset_metadata` is updated with its final path and status. The older `processed_maps_details` and `merged_maps_details` from the context are not directly included in the JSON.

## External Steps

Certain steps are integral to the overall asset processing workflow but are handled outside the [`PipelineOrchestrator`](processing/pipeline/orchestrator.py:36)'s direct execution loop:

*   **Workspace Preparation and Cleanup**: Handled by the code that invokes [`ProcessingEngine.process()`](processing_engine.py:131) (e.g., `main.ProcessingTask`, `monitor._process_archive_task`), typically involving extracting archives and setting up temporary directories. The engine itself manages a sub-temporary directory (`engine_temp_dir`) for intermediate processing files.
*   **Prediction and Rule Generation**: Performed before the [`ProcessingEngine`](processing_engine.py:73) is called. This involves analyzing source files and generating the [`SourceRule`](rule_structure.py:40) object with its nested [`AssetRule`](rule_structure.py:22)s and [`FileRule`](rule_structure.py:5)s, often involving prediction logic (potentially using LLMs).
*   **Optional Blender Script Execution**: Can be triggered externally after successful processing to perform tasks like material setup in Blender using the generated output files and metadata.

This staged pipeline provides a modular and extensible architecture for asset processing, with clear separation of concerns for each step. The [`AssetProcessingContext`](processing/pipeline/asset_context.py:86) ensures that data flows consistently between these stages.