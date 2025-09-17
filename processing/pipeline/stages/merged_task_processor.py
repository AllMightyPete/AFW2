import logging
import re
from pathlib import Path
from typing import List, Optional, Tuple, Dict, Any

import cv2
import numpy as np

from .base_stage import ProcessingStage
# Import necessary context classes and utils
from ..asset_context import AssetProcessingContext, MergeTaskDefinition, ProcessedMergedMapData
from ...utils import image_processing_utils as ipu

log = logging.getLogger(__name__)

class MergedTaskProcessorStage(ProcessingStage):
    """
    Processes a single merge task defined in the configuration.
    Loads inputs, applies transformations to inputs, handles fallbacks/resizing,
    performs the merge, and returns the merged data.
    """

    def _find_input_map_details_in_context(
        self,
        required_map_type: str,
        processed_map_details_context: Dict[str, Dict[str, Any]],
        log_prefix_for_find: str
    ) -> Optional[Dict[str, Any]]:
        """
        Finds the details of a required input map from the context's processed_maps_details.
        Prefers exact match for full types (e.g. MAP_TYPE-1), or base type / base type + "-1" for base types (e.g. MAP_TYPE).
        Returns the details dictionary for the found map if it has saved_files_info.
        """
        # Try exact match first (e.g., rule asks for "MAP_NRM-1" or "MAP_NRM" if that's how it was processed)
        for item_key, details in processed_map_details_context.items():
            if details.get('internal_map_type') == required_map_type:
                if details.get('saved_files_info') and isinstance(details['saved_files_info'], list) and len(details['saved_files_info']) > 0:
                    log.debug(f"{log_prefix_for_find}: Found exact match for '{required_map_type}' with key '{item_key}'.")
                    return details
                log.warning(f"{log_prefix_for_find}: Found exact match for '{required_map_type}' (key '{item_key}') but no saved_files_info.")
                return None # Found type but no usable files

        # If exact match not found, and required_map_type is a base type (e.g. "MAP_NRM")
        # try to find the primary suffixed version "MAP_NRM-1" or the base type itself if it was processed without a suffix.
        if not re.search(r'-\d+$', required_map_type): # if it's a base type like MAP_XXX
            # Prefer "MAP_XXX-1" as the primary variant if suffixed types exist
            primary_suffixed_type = f"{required_map_type}-1"
            for item_key, details in processed_map_details_context.items():
                if details.get('internal_map_type') == primary_suffixed_type:
                    if details.get('saved_files_info') and isinstance(details['saved_files_info'], list) and len(details['saved_files_info']) > 0:
                        log.debug(f"{log_prefix_for_find}: Found primary suffixed match '{primary_suffixed_type}' for base '{required_map_type}' with key '{item_key}'.")
                        return details
                    log.warning(f"{log_prefix_for_find}: Found primary suffixed match '{primary_suffixed_type}' (key '{item_key}') but no saved_files_info.")
                    return None # Found type but no usable files
        
        log.debug(f"{log_prefix_for_find}: No suitable match found for '{required_map_type}' via exact or primary suffixed type search.")
        return None

    def execute(
        self,
        context: AssetProcessingContext,
        merge_task: MergeTaskDefinition # Specific item passed by orchestrator
    ) -> ProcessedMergedMapData:
        """
        Processes the given MergeTaskDefinition item.
        """
        asset_name_for_log = context.asset_rule.asset_name if context.asset_rule else "Unknown Asset"
        task_key = merge_task.task_key
        task_data = merge_task.task_data
        log_prefix = f"Asset '{asset_name_for_log}', Task '{task_key}'"
        log.info(f"{log_prefix}: Processing Merge Task.")

        # Initialize output object with default failure state
        result = ProcessedMergedMapData(
            merged_image_data=np.array([]), # Placeholder
            output_map_type=task_data.get('output_map_type', 'UnknownMergeOutput'),
            source_bit_depths=[],
            final_dimensions=None,
            transformations_applied_to_inputs={},
            status="Failed",
            error_message="Initialization error"
        )

        try:
            # --- Configuration & Task Data ---
            config = context.config_obj
            file_type_definitions = getattr(config, "FILE_TYPE_DEFINITIONS", {})
            invert_normal_green = config.invert_normal_green_globally
            merge_dimension_mismatch_strategy = getattr(config, "MERGE_DIMENSION_MISMATCH_STRATEGY", "USE_LARGEST")
            workspace_path = context.workspace_path # Base for resolving relative input paths

            # input_map_sources_from_task is no longer used for paths. Paths are sourced from context.processed_maps_details.
            target_dimensions_hw = task_data.get('source_dimensions') # Expected dimensions (h, w) for fallback creation, must be in config.
            merge_inputs_config = task_data.get('inputs', {}) # e.g., {'R': 'MAP_AO', 'G': 'MAP_ROUGH', ...}
            merge_defaults = task_data.get('defaults', {}) # e.g., {'R': 255, 'G': 255, ...}
            merge_channels_order = task_data.get('channel_order', 'RGB') # e.g., 'RGB', 'RGBA'

            # Target dimensions are crucial if fallbacks are needed.
            # Merge inputs config is essential.
            # Merge inputs config is essential. Check directly in task_data.
            inputs_from_task_data = task_data.get('inputs')
            if not isinstance(inputs_from_task_data, dict) or not inputs_from_task_data:
                 result.error_message = "Merge task data is incomplete (missing or invalid 'inputs' dictionary in task_data)."
                 log.error(f"{log_prefix}: {result.error_message}")
                 return result
            if not target_dimensions_hw and any(merge_defaults.get(ch) is not None for ch in merge_inputs_config.keys()):
                log.warning(f"{log_prefix}: Merge task has defaults defined, but 'source_dimensions' (target_dimensions_hw) is missing in task_data. Fallback image creation might fail if needed.")
                # Not returning error yet, as fallbacks might not be triggered.

            loaded_inputs_for_merge: Dict[str, np.ndarray] = {} # Channel char -> image data
            actual_input_dimensions: List[Tuple[int, int]] = [] # List of (h, w) for loaded files
            input_source_bit_depths: Dict[str, int] = {} # Channel char -> bit depth
            all_transform_notes: Dict[str, List[str]] = {} # Channel char -> list of transform notes

            # --- Load, Transform, and Prepare Inputs ---
            log.debug(f"{log_prefix}: Loading and preparing inputs...")
            for channel_char, required_map_type_from_rule in merge_inputs_config.items():
                # Validate that the required input map type starts with "MAP_"
                if not required_map_type_from_rule.startswith("MAP_"):
                    result.error_message = (
                        f"Invalid input map type '{required_map_type_from_rule}' for channel '{channel_char}'. "
                        f"Input map types for merging must start with 'MAP_'."
                    )
                    log.error(f"{log_prefix}: {result.error_message}")
                    return result # Fail the task if an input type is invalid

                input_image_data: Optional[np.ndarray] = None
                input_source_desc = f"Fallback for {required_map_type_from_rule}"
                input_log_prefix = f"{log_prefix}, Input '{required_map_type_from_rule}' (Channel '{channel_char}')"
                channel_transform_notes: List[str] = []

                # 1. Attempt to load from context.processed_maps_details
                found_input_map_details = self._find_input_map_details_in_context(
                    required_map_type_from_rule, context.processed_maps_details, input_log_prefix
                )

                if found_input_map_details:
                    # Assuming the first saved file is the primary one for merging.
                    # This might need refinement if specific variants (resolutions/formats) are required.
                    primary_saved_file_info = found_input_map_details['saved_files_info'][0]
                    input_file_path_str = primary_saved_file_info.get('path')

                    if input_file_path_str:
                        input_file_path = Path(input_file_path_str) # Path is absolute from SaveVariantsStage
                        if input_file_path.is_file():
                            try:
                                input_image_data = ipu.load_image(str(input_file_path))
                                if input_image_data is not None:
                                    log.info(f"{input_log_prefix}: Loaded from context: {input_file_path}")
                                    actual_input_dimensions.append(input_image_data.shape[:2]) # (h, w)
                                    input_source_desc = str(input_file_path)
                                    # Bit depth from the saved variant info
                                    input_source_bit_depths[channel_char] = primary_saved_file_info.get('bit_depth', 8)
                                else:
                                    log.warning(f"{input_log_prefix}: Failed to load image from {input_file_path} (found in context). Attempting fallback.")
                                    input_image_data = None # Ensure fallback is triggered
                            except Exception as e:
                                log.warning(f"{input_log_prefix}: Error loading image from {input_file_path} (found in context): {e}. Attempting fallback.")
                                input_image_data = None # Ensure fallback is triggered
                        else:
                            log.warning(f"{input_log_prefix}: Input file path '{input_file_path}' (from context) not found. Attempting fallback.")
                            input_image_data = None # Ensure fallback is triggered
                    else:
                        log.warning(f"{input_log_prefix}: Found map type '{required_map_type_from_rule}' in context, but 'path' is missing in saved_files_info. Attempting fallback.")
                        input_image_data = None # Ensure fallback is triggered
                else:
                    log.info(f"{input_log_prefix}: Input map type '{required_map_type_from_rule}' not found in context.processed_maps_details. Attempting fallback.")
                    input_image_data = None # Ensure fallback is triggered

                # 2. Apply Fallback if needed
                if input_image_data is None:
                    fallback_value = merge_defaults.get(channel_char)
                    if fallback_value is not None:
                        try:
                            if not target_dimensions_hw:
                                result.error_message = f"Cannot create fallback for channel '{channel_char}': 'source_dimensions' (target_dimensions_hw) not defined in task_data."
                                log.error(f"{log_prefix}: {result.error_message}")
                                return result # Critical failure if dimensions for fallback are missing
                            h, w = target_dimensions_hw
                            # Infer shape/dtype for fallback (simplified)
                            num_channels = 1 if isinstance(fallback_value, (int, float)) else len(fallback_value) if isinstance(fallback_value, (list, tuple)) else 1
                            dtype = np.uint8 # Default dtype
                            shape = (h, w) if num_channels == 1 else (h, w, num_channels)

                            input_image_data = np.full(shape, fallback_value, dtype=dtype)
                            log.warning(f"{input_log_prefix}: Using fallback value {fallback_value} (Target Dims: {target_dimensions_hw}).")
                            input_source_desc = f"Fallback value {fallback_value}"
                            input_source_bit_depths[channel_char] = 8 # Assume 8-bit for fallbacks
                            channel_transform_notes.append(f"Used fallback value {fallback_value}")
                        except Exception as e:
                            result.error_message = f"Error creating fallback for channel '{channel_char}': {e}"
                            log.error(f"{log_prefix}: {result.error_message}")
                            return result # Critical failure
                    else:
                        result.error_message = f"Missing input '{required_map_type_from_rule}' and no fallback default provided for channel '{channel_char}'."
                        log.error(f"{log_prefix}: {result.error_message}")
                        return result # Critical failure

                # 3. Apply Transformations to the loaded/fallback input
                if input_image_data is not None:
                    input_image_data, _, transform_notes = ipu.apply_common_map_transformations(
                        input_image_data.copy(), # Transform a copy
                        required_map_type_from_rule, # Use the type required by the rule
                        invert_normal_green,
                        file_type_definitions,
                        input_log_prefix
                    )
                    channel_transform_notes.extend(transform_notes)
                else:
                    # This case should be prevented by fallback logic, but as a safeguard:
                    result.error_message = f"Input data for channel '{channel_char}' is None after load/fallback attempt."
                    log.error(f"{log_prefix}: {result.error_message} This indicates an internal logic error.")
                    return result

                loaded_inputs_for_merge[channel_char] = input_image_data
                all_transform_notes[channel_char] = channel_transform_notes

            result.transformations_applied_to_inputs = all_transform_notes # Store notes

            # --- Handle Dimension Mismatches (using transformed inputs) ---
            log.debug(f"{log_prefix}: Handling dimension mismatches...")
            unique_dimensions = set(actual_input_dimensions)
            target_merge_dims_hw = target_dimensions_hw # Default

            if len(unique_dimensions) > 1:
                log.warning(f"{log_prefix}: Mismatched dimensions found among loaded inputs: {unique_dimensions}. Applying strategy: {merge_dimension_mismatch_strategy}")
                mismatch_note = f"Mismatched input dimensions ({unique_dimensions}), applied {merge_dimension_mismatch_strategy}"
                # Add note to all relevant inputs? Or just a general note? Add general for now.
                # result.status_notes.append(mismatch_note) # Need a place for general notes

                if merge_dimension_mismatch_strategy == "ERROR_SKIP":
                    result.error_message = "Dimension mismatch and strategy is ERROR_SKIP."
                    log.error(f"{log_prefix}: {result.error_message}")
                    return result
                elif merge_dimension_mismatch_strategy == "USE_LARGEST":
                    max_h = max(h for h, w in unique_dimensions)
                    max_w = max(w for h, w in unique_dimensions)
                    target_merge_dims_hw = (max_h, max_w)
                elif merge_dimension_mismatch_strategy == "USE_FIRST":
                    target_merge_dims_hw = actual_input_dimensions[0] if actual_input_dimensions else target_dimensions_hw
                # Add other strategies or default to USE_LARGEST

                log.info(f"{log_prefix}: Resizing inputs to target merge dimensions: {target_merge_dims_hw}")
                # Resize loaded inputs (not fallbacks unless they were treated as having target dims)
                for channel_char, img_data in loaded_inputs_for_merge.items():
                     # Only resize if it was a loaded input that contributed to the mismatch check
                     if img_data.shape[:2] in unique_dimensions and img_data.shape[:2] != target_merge_dims_hw:
                         resized_img = ipu.resize_image(img_data, target_merge_dims_hw[1], target_merge_dims_hw[0]) # w, h
                         if resized_img is None:
                             result.error_message = f"Failed to resize input for channel '{channel_char}' to {target_merge_dims_hw}."
                             log.error(f"{log_prefix}: {result.error_message}")
                             return result
                         loaded_inputs_for_merge[channel_char] = resized_img
                         log.debug(f"{log_prefix}: Resized input for channel '{channel_char}'.")

            # If target_merge_dims_hw is still None (no source_dimensions and no mismatch), use first loaded input's dimensions
            if target_merge_dims_hw is None and actual_input_dimensions:
                target_merge_dims_hw = actual_input_dimensions[0]
                log.info(f"{log_prefix}: Using dimensions from first loaded input: {target_merge_dims_hw}")

            # --- Perform Merge ---
            log.debug(f"{log_prefix}: Performing merge operation for channels '{merge_channels_order}'.")
            try:
                # Final check for valid dimensions before unpacking
                if not isinstance(target_merge_dims_hw, tuple) or len(target_merge_dims_hw) != 2:
                    result.error_message = "Could not determine valid target dimensions for merge operation."
                    log.error(f"{log_prefix}: {result.error_message} (target_merge_dims_hw: {target_merge_dims_hw})")
                    return result

                output_channels = len(merge_channels_order)
                h, w = target_merge_dims_hw # Use the potentially adjusted dimensions

                # Determine output dtype (e.g., based on inputs or config) - Assume uint8 for now
                output_dtype = np.uint8

                if output_channels == 1:
                     # Assume the first channel in order is the one to use
                     channel_char_to_use = merge_channels_order[0]
                     source_img = loaded_inputs_for_merge[channel_char_to_use]
                     # Ensure it's grayscale (take first channel if it's multi-channel)
                     if len(source_img.shape) == 3:
                         merged_image = source_img[:, :, 0].copy().astype(output_dtype)
                     else:
                         merged_image = source_img.copy().astype(output_dtype)
                elif output_channels > 1:
                    merged_image = np.zeros((h, w, output_channels), dtype=output_dtype)
                    for i, channel_char in enumerate(merge_channels_order):
                        source_img = loaded_inputs_for_merge.get(channel_char)
                        if source_img is not None:
                             # Extract the correct channel (e.g., R from RGB, or use grayscale directly)
                             if len(source_img.shape) == 3:
                                 # Simple approach: take the first channel if source is color. Needs refinement if specific channel mapping (R->R, G->G etc.) is needed.
                                 merged_image[:, :, i] = source_img[:, :, 0]
                             else: # Grayscale source
                                 merged_image[:, :, i] = source_img
                        else:
                             # This case should have been caught by fallback logic earlier
                             result.error_message = f"Internal error: Missing prepared input for channel '{channel_char}' during final merge assembly."
                             log.error(f"{log_prefix}: {result.error_message}")
                             return result
                else:
                     result.error_message = f"Invalid channel_order '{merge_channels_order}' in merge config."
                     log.error(f"{log_prefix}: {result.error_message}")
                     return result

                result.merged_image_data = merged_image
                result.final_dimensions = (merged_image.shape[1], merged_image.shape[0]) # w, h
                result.source_bit_depths = list(input_source_bit_depths.values()) # Collect bit depths used
                log.info(f"{log_prefix}: Successfully merged inputs into image with shape {result.merged_image_data.shape}")

            except Exception as e:
                log.exception(f"{log_prefix}: Error during merge operation: {e}")
                result.error_message = f"Merge operation failed: {e}"
                return result

            # --- Success ---
            result.status = "Processed"
            result.error_message = None
            log.info(f"{log_prefix}: Successfully processed merge task.")

        except Exception as e:
            log.exception(f"{log_prefix}: Unhandled exception during processing: {e}")
            result.status = "Failed"
            result.error_message = f"Unhandled exception: {e}"
            # Ensure image data is empty on failure
            if result.merged_image_data is None or result.merged_image_data.size == 0:
                 result.merged_image_data = np.array([])

        return result