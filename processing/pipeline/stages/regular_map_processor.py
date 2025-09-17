import logging
import re
from pathlib import Path
from typing import List, Optional, Tuple, Dict

import cv2
import numpy as np

from .base_stage import ProcessingStage # Assuming base_stage is in the same directory
from ..asset_context import AssetProcessingContext, ProcessedRegularMapData
from rule_structure import FileRule, AssetRule
from processing.utils import image_processing_utils as ipu # Absolute import
from utils.path_utils import get_filename_friendly_map_type # Absolute import

log = logging.getLogger(__name__)


class RegularMapProcessorStage(ProcessingStage):
    """
    Processes a single regular texture map defined by a FileRule.
    Loads the image, determines map type, applies transformations,
    and returns the processed data.
    """

    # --- Helper Methods (Adapted from IndividualMapProcessingStage) ---

    def _get_suffixed_internal_map_type(
        self,
        asset_rule: Optional[AssetRule],
        current_file_rule: FileRule,
        initial_internal_map_type: str,
        respect_variant_map_types: List[str],
        asset_name_for_log: str
    ) -> str:
        """
        Determines the potentially suffixed internal map type (e.g., MAP_COL-1).
        """
        final_internal_map_type = initial_internal_map_type # Default

        base_map_type_match = re.match(r"(MAP_[A-Z]+)", initial_internal_map_type)
        if not base_map_type_match or not asset_rule or not asset_rule.files:
            return final_internal_map_type # Cannot determine suffix without base type or asset rule files

        true_base_map_type = base_map_type_match.group(1) # This is "MAP_XXX"

        # Find all FileRules in the asset with the same base map type
        peers_of_same_base_type = []
        for fr_asset in asset_rule.files:
            fr_asset_item_type = fr_asset.item_type_override or fr_asset.item_type or "UnknownMapType"
            fr_asset_base_match = re.match(r"(MAP_[A-Z]+)", fr_asset_item_type)
            if fr_asset_base_match and fr_asset_base_match.group(1) == true_base_map_type:
                peers_of_same_base_type.append(fr_asset)

        num_occurrences = len(peers_of_same_base_type)
        current_instance_index = 0 # 1-based index

        try:
            # Find the index based on the FileRule object itself (requires object identity)
            current_instance_index = peers_of_same_base_type.index(current_file_rule) + 1
        except ValueError:
            # Fallback: try matching by file_path if object identity fails (less reliable)
            try:
                 current_instance_index = [fr.file_path for fr in peers_of_same_base_type].index(current_file_rule.file_path) + 1
                 log.warning(f"Asset '{asset_name_for_log}', FileRule path '{current_file_rule.file_path}': Found peer index using file_path fallback for suffixing.")
            except (ValueError, AttributeError): # Catch AttributeError if file_path is None
                 log.warning(
                    f"Asset '{asset_name_for_log}', FileRule path '{current_file_rule.file_path}' (Initial Type: '{initial_internal_map_type}', Base: '{true_base_map_type}'): "
                    f"Could not find its own instance in the list of {num_occurrences} peers from asset_rule.files using object identity or path. Suffixing may be incorrect."
                 )
                 # Keep index 0, suffix logic below will handle it

        # Determine Suffix
        map_type_for_respect_check = true_base_map_type.replace("MAP_", "") # e.g., "COL"
        is_in_respect_list = map_type_for_respect_check in respect_variant_map_types

        suffix_to_append = ""
        if num_occurrences > 1:
            if current_instance_index > 0:
                suffix_to_append = f"-{current_instance_index}"
            else:
                 # If index is still 0 (not found), don't add suffix to avoid ambiguity
                 log.warning(f"Asset '{asset_name_for_log}', FileRule path '{current_file_rule.file_path}': Index for multi-occurrence map type '{true_base_map_type}' (count: {num_occurrences}) not determined. Omitting numeric suffix.")
        elif num_occurrences == 1 and is_in_respect_list:
            suffix_to_append = "-1" # Add suffix even for single instance if in respect list

        if suffix_to_append:
            final_internal_map_type = true_base_map_type + suffix_to_append

        if final_internal_map_type != initial_internal_map_type:
             log.debug(f"Asset '{asset_name_for_log}', FileRule path '{current_file_rule.file_path}': Suffixed internal map type determined: '{initial_internal_map_type}' -> '{final_internal_map_type}'")

        return final_internal_map_type


    # --- Execute Method ---

    def execute(
        self,
        context: AssetProcessingContext,
        file_rule: FileRule # Specific item passed by orchestrator
    ) -> ProcessedRegularMapData:
        """
        Processes the given FileRule item.
        """
        asset_name_for_log = context.asset_rule.asset_name if context.asset_rule else "Unknown Asset"
        log_prefix = f"Asset '{asset_name_for_log}', File '{file_rule.file_path}'"
        log.info(f"{log_prefix}: Processing Regular Map.")

        # Initialize output object with default failure state
        result = ProcessedRegularMapData(
            processed_image_data=np.array([]), # Placeholder
            final_internal_map_type="Unknown",
            source_file_path=Path(file_rule.file_path or "InvalidPath"),
            original_bit_depth=None,
            original_dimensions=None,
            transformations_applied=[],
            status="Failed",
            error_message="Initialization error"
        )

        try:
            # --- Configuration ---
            config = context.config_obj
            file_type_definitions = getattr(config, "FILE_TYPE_DEFINITIONS", {})
            respect_variant_map_types = getattr(config, "respect_variant_map_types", [])
            invert_normal_green = config.invert_normal_green_globally

            # --- Determine Map Type (with suffix) ---
            initial_internal_map_type = file_rule.item_type_override or file_rule.item_type or "UnknownMapType"
            if not initial_internal_map_type or initial_internal_map_type == "UnknownMapType":
                 result.error_message = "Map type (item_type) not defined in FileRule."
                 log.error(f"{log_prefix}: {result.error_message}")
                 return result # Early exit

            # Explicitly skip if the determined type doesn't start with "MAP_"
            if not initial_internal_map_type.startswith("MAP_"):
                result.status = "Skipped (Invalid Type)"
                result.error_message = f"FileRule item_type '{initial_internal_map_type}' does not start with 'MAP_'. Skipping processing."
                log.warning(f"{log_prefix}: {result.error_message}")
                return result # Early exit

            processing_map_type = self._get_suffixed_internal_map_type(
                context.asset_rule, file_rule, initial_internal_map_type, respect_variant_map_types, asset_name_for_log
            )
            result.final_internal_map_type = processing_map_type # Store initial suffixed type

            # --- Find and Load Source File ---
            if not file_rule.file_path: # Should have been caught by Prepare stage, but double-check
                result.error_message = "FileRule has empty file_path."
                log.error(f"{log_prefix}: {result.error_message}")
                return result

            source_base_path = context.workspace_path
            potential_source_path = source_base_path / file_rule.file_path
            source_file_path_found: Optional[Path] = None

            if potential_source_path.is_file():
                 source_file_path_found = potential_source_path
                 log.info(f"{log_prefix}: Found source file: {source_file_path_found}")
            else:
                # Optional: Add globbing fallback if needed, similar to original stage
                log.warning(f"{log_prefix}: Source file not found directly at '{potential_source_path}'. Add globbing if necessary.")
                result.error_message = f"Source file not found at '{potential_source_path}'"
                log.error(f"{log_prefix}: {result.error_message}")
                return result

            result.source_file_path = source_file_path_found # Update result with found path

            # Load image
            source_image_data = ipu.load_image(str(source_file_path_found))
            if source_image_data is None:
                result.error_message = f"Failed to load image from '{source_file_path_found}'."
                log.error(f"{log_prefix}: {result.error_message}")
                return result

            original_height, original_width = source_image_data.shape[:2]
            result.original_dimensions = (original_width, original_height)
            log.debug(f"{log_prefix}: Loaded image {result.original_dimensions[0]}x{result.original_dimensions[1]}.")

            # Get original bit depth
            try:
                result.original_bit_depth = ipu.get_image_bit_depth(str(source_file_path_found))
                log.info(f"{log_prefix}: Determined source bit depth: {result.original_bit_depth}")
            except Exception as e:
                 log.warning(f"{log_prefix}: Could not determine source bit depth for {source_file_path_found}: {e}. Setting to None.")
                 result.original_bit_depth = None # Indicate failure to determine

            # --- Apply Transformations ---
            transformed_image_data, final_map_type, transform_notes = ipu.apply_common_map_transformations(
                source_image_data.copy(), # Pass a copy to avoid modifying original load
                processing_map_type,
                invert_normal_green,
                file_type_definitions,
                log_prefix
            )
            result.processed_image_data = transformed_image_data
            result.final_internal_map_type = final_map_type # Update if Gloss->Rough changed it
            result.transformations_applied = transform_notes

            # --- Determine Resolution Key for LOWRES ---
            if config.enable_low_resolution_fallback and result.original_dimensions:
                w, h = result.original_dimensions
                if max(w, h) < config.low_resolution_threshold:
                    result.resolution_key = "LOWRES"
                    log.info(f"{log_prefix}: Image dimensions ({w}x{h}) are below threshold ({config.low_resolution_threshold}px). Flagging as LOWRES.")

            # --- Success ---
            result.status = "Processed"
            result.error_message = None
            log.info(f"{log_prefix}: Successfully processed regular map. Final type: '{result.final_internal_map_type}', ResolutionKey: {result.resolution_key}.")

        except Exception as e:
            log.exception(f"{log_prefix}: Unhandled exception during processing: {e}")
            result.status = "Failed"
            result.error_message = f"Unhandled exception: {e}"
            # Ensure image data is empty on failure if it wasn't set
            if result.processed_image_data is None or result.processed_image_data.size == 0:
                 result.processed_image_data = np.array([])

        return result