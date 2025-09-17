import logging
import uuid
from pathlib import Path
from typing import List, Optional, Dict

import numpy as np

from .base_stage import ProcessingStage
from ..asset_context import AssetProcessingContext
from ...utils import image_processing_utils as ipu
from rule_structure import FileRule
from utils.path_utils import sanitize_filename

logger = logging.getLogger(__name__)

class AlphaExtractionToMaskStage(ProcessingStage):
    """
    Extracts an alpha channel from a suitable source map (e.g., Albedo, Diffuse)
    to generate a MASK map if one is not explicitly defined.
    """
    # Use MAP_ prefixed types for internal logic checks
    SUITABLE_SOURCE_MAP_TYPES = ["MAP_COL", "MAP_ALBEDO", "MAP_BASECOLOR"] # Map types likely to have alpha

    def execute(self, context: AssetProcessingContext) -> AssetProcessingContext:
        asset_name_for_log = context.asset_rule.asset_name if context.asset_rule else "Unknown Asset"
        logger.debug(f"Asset '{asset_name_for_log}': Running AlphaExtractionToMaskStage.")

        if context.status_flags.get('skip_asset'):
            logger.debug(f"Asset '{asset_name_for_log}': Skipping due to 'skip_asset' flag.")
            return context

        if not context.files_to_process or not context.processed_maps_details:
            logger.debug(
                f"Asset '{asset_name_for_log}': Skipping alpha extraction - "
                f"no files to process or no processed map details."
            )
            return context

        # A. Check for Existing MASK Map
        for file_rule in context.files_to_process:
            # Assuming file_rule has 'map_type' and 'file_path' (instead of filename_pattern)
            # Check for existing MASK map using the correct item_type field and MAP_ prefix
            if file_rule.item_type == "MAP_MASK":
                file_path_for_log = file_rule.file_path if hasattr(file_rule, 'file_path') else "Unknown file path"
                logger.info(
                    f"Asset '{asset_name_for_log}': MASK map already defined by FileRule "
                    f"for '{file_path_for_log}'. Skipping alpha extraction."
                )
                return context

        # B. Find Suitable Source Map with Alpha
        source_map_details_for_alpha: Optional[Dict] = None
        source_file_rule_id_for_alpha: Optional[str] = None # This ID comes from processed_maps_details keys

        for file_rule_id, details in context.processed_maps_details.items():
            # Check for suitable source map using the standardized internal_map_type field
            internal_map_type = details.get('internal_map_type') # Use the standardized field
            if details.get('status') == 'Processed' and \
               internal_map_type in self.SUITABLE_SOURCE_MAP_TYPES:
                try:
                    temp_path = Path(details['temp_processed_file'])
                    if not temp_path.exists():
                        logger.warning(
                            f"Asset '{asset_name_for_log}': Temp file {temp_path} for map "
                            f"{details['map_type']} (ID: {file_rule_id}) does not exist. Cannot check for alpha."
                        )
                        continue
                    
                    image_data = ipu.load_image(temp_path)

                    if image_data is not None and image_data.ndim == 3 and image_data.shape[2] == 4:
                        source_map_details_for_alpha = details
                        source_file_rule_id_for_alpha = file_rule_id
                        logger.info(
                            f"Asset '{asset_name_for_log}': Found potential source for alpha extraction: "
                            f"{temp_path} (MapType: {details['map_type']})"
                        )
                        break
                except Exception as e:
                    logger.warning(
                        f"Asset '{asset_name_for_log}': Error checking alpha for {details.get('temp_processed_file', 'N/A')}: {e}"
                    )
                    continue


        if source_map_details_for_alpha is None or source_file_rule_id_for_alpha is None:
            logger.info(
                f"Asset '{asset_name_for_log}': No suitable source map with alpha channel found "
                f"for MASK extraction."
            )
            return context

        # C. Extract Alpha Channel
        source_image_path = Path(source_map_details_for_alpha['temp_processed_file'])
        full_image_data = ipu.load_image(source_image_path) # Reload to ensure we have the original RGBA

        if full_image_data is None or not (full_image_data.ndim == 3 and full_image_data.shape[2] == 4):
            logger.error(
                f"Asset '{asset_name_for_log}': Failed to reload or verify alpha channel from "
                f"{source_image_path} for MASK extraction."
            )
            return context
        
        alpha_channel: np.ndarray = full_image_data[:, :, 3] # Extract alpha (0-255)

        # D. Save New Temporary MASK Map
        if alpha_channel.ndim == 2: # Expected
            pass
        elif alpha_channel.ndim == 3 and alpha_channel.shape[2] == 1: # (H, W, 1)
             alpha_channel = alpha_channel.squeeze(axis=2)
        else:
            logger.error(
                f"Asset '{asset_name_for_log}': Extracted alpha channel has unexpected dimensions: "
                f"{alpha_channel.shape}. Cannot save."
            )
            return context

        mask_temp_filename = (
            f"mask_from_alpha_{sanitize_filename(source_map_details_for_alpha['map_type'])}"
            f"_{source_file_rule_id_for_alpha}{source_image_path.suffix}"
        )
        mask_temp_path = context.engine_temp_dir / mask_temp_filename
        
        save_success = ipu.save_image(mask_temp_path, alpha_channel)
        
        if not save_success:
            logger.error(
                f"Asset '{asset_name_for_log}': Failed to save extracted alpha mask to {mask_temp_path}."
            )
            return context
        
        logger.info(
            f"Asset '{asset_name_for_log}': Extracted alpha and saved as new MASK map: {mask_temp_path}"
        )

        # E. Create New FileRule for the MASK and Update Context
        # FileRule does not have id, active, transform_settings, source_map_ids_for_generation
        # It has file_path, item_type, item_type_override, etc.
        new_mask_file_rule = FileRule(
            file_path=mask_temp_path.name, # Use file_path
            item_type="MAP_MASK", # This should be the item_type for a mask
            map_type="MASK" # Explicitly set map_type if FileRule has it, or handle via item_type
            # Other FileRule fields like item_type_override can be set if needed
        )
        # If FileRule needs a unique identifier, it should be handled differently,
        # perhaps by generating one and storing it in common_metadata or a separate mapping.
        # For now, we create a simple FileRule.
        
        context.files_to_process.append(new_mask_file_rule)
        
        # For processed_maps_details, we need a unique key. Using a new UUID.
        new_mask_processed_map_key = uuid.uuid4().hex

        original_dims = source_map_details_for_alpha.get('original_dimensions')
        if original_dims is None and full_image_data is not None: # Fallback if not in details
             original_dims = (full_image_data.shape[1], full_image_data.shape[0])


        context.processed_maps_details[new_mask_processed_map_key] = {
            'internal_map_type': "MAP_MASK", # Use the standardized MAP_ prefixed field
            'map_type': "MASK", # Keep standard type for metadata/naming consistency if needed
            'source_file': str(source_image_path),
            'temp_processed_file': str(mask_temp_path),
            'original_dimensions': original_dims,
            'processed_dimensions': (alpha_channel.shape[1], alpha_channel.shape[0]),
            'status': 'Processed',
            'notes': (
                f"Generated from alpha of {source_map_details_for_alpha.get('internal_map_type', 'unknown type')} " # Use internal_map_type for notes
                f"(Source Detail ID: {source_file_rule_id_for_alpha})"
            ),
            # 'file_rule_id': new_mask_file_rule_id_str # FileRule doesn't have an ID to link here directly
        }
        
        logger.info(
            f"Asset '{asset_name_for_log}': Added new FileRule for generated MASK "
            f"and updated processed_maps_details with key '{new_mask_processed_map_key}'."
        )

        return context