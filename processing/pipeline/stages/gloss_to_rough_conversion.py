import logging
from pathlib import Path
import numpy as np
from typing import List
import dataclasses

from .base_stage import ProcessingStage
from ..asset_context import AssetProcessingContext
from rule_structure import FileRule
from ...utils import image_processing_utils as ipu
from utils.path_utils import sanitize_filename

logger = logging.getLogger(__name__)

class GlossToRoughConversionStage(ProcessingStage):
    """
    Processing stage to convert glossiness maps to roughness maps.
    Iterates through FileRules, identifies GLOSS maps, loads their
    corresponding temporary processed images, inverts them, and saves
    them as new temporary ROUGHNESS maps. Updates the FileRule and
    context.processed_maps_details accordingly.
    """

    def execute(self, context: AssetProcessingContext) -> AssetProcessingContext:
        """
        Executes the gloss to roughness conversion logic.

        Args:
            context: The AssetProcessingContext containing asset and processing details.

        Returns:
            The updated AssetProcessingContext.
        """
        asset_name_for_log = context.asset_rule.asset_name if context.asset_rule else "Unknown Asset"
        if context.status_flags.get('skip_asset'):
            logger.debug(f"Asset '{asset_name_for_log}': Skipping GlossToRoughConversionStage due to skip_asset flag.")
            return context

        if not context.processed_maps_details: # files_to_process might be empty if only gloss maps existed and all are converted
            logger.debug(
                f"Asset '{asset_name_for_log}': processed_maps_details is empty in GlossToRoughConversionStage. Skipping."
            )
            return context

        # Start with a copy of the current file rules. We will modify this list.
        new_files_to_process: List[FileRule] = list(context.files_to_process) if context.files_to_process else []
        processed_a_gloss_map = False
        successful_conversion_statuses = ['BasePOTSaved', 'Processed_With_Variants', 'Processed_No_Variants']

        logger.info(f"Asset '{asset_name_for_log}': Starting Gloss to Roughness Conversion Stage. Examining {len(context.processed_maps_details)} processed map entries.")

        # Iterate using the index (map_key_index) as the key, which is now standard.
        for map_key_index, map_details in context.processed_maps_details.items():
            # Use the standardized internal_map_type field
            internal_map_type = map_details.get('internal_map_type', '')
            map_status = map_details.get('status')
            original_temp_path_str = map_details.get('temp_processed_file')
            # source_file_rule_idx from details should align with map_key_index.
            # We primarily use map_key_index for accessing FileRule from context.files_to_process.
            source_file_rule_idx_from_details = map_details.get('source_file_rule_index')
            processing_tag = map_details.get('processing_tag')

            if map_key_index != source_file_rule_idx_from_details:
                logger.warning(
                    f"Asset '{asset_name_for_log}', Map Key Index {map_key_index}: Mismatch between map key index and 'source_file_rule_index' ({source_file_rule_idx_from_details}) in details. "
                    f"Using map_key_index ({map_key_index}) for FileRule lookup. This might indicate a data consistency issue from previous stage."
                )

            if not processing_tag:
                logger.warning(f"Asset '{asset_name_for_log}', Map Key Index {map_key_index}: 'processing_tag' is missing in map_details. Using a fallback for temp filename. This is unexpected.")
                processing_tag = f"mki_{map_key_index}_fallback_tag"


            # Check if the map is a GLOSS map using the standardized internal_map_type
            if not internal_map_type.startswith("MAP_GLOSS"):
                # logger.debug(f"Asset '{asset_name_for_log}', Map Key Index {map_key_index}: Type '{internal_map_type}' is not GLOSS. Skipping.")
                continue

            logger.info(f"Asset '{asset_name_for_log}', Map Key Index {map_key_index} (Tag: {processing_tag}): Identified potential GLOSS map (Type: {internal_map_type}).")

            if map_status not in successful_conversion_statuses:
                logger.warning(
                    f"Asset '{asset_name_for_log}', Map Key Index {map_key_index} (Tag: {processing_tag}) (GLOSS): Status '{map_status}' is not one of {successful_conversion_statuses}. "
                    f"Skipping conversion for this map."
                )
                continue

            if not original_temp_path_str:
                logger.warning(
                    f"Asset '{asset_name_for_log}', Map Key Index {map_key_index} (Tag: {processing_tag}) (GLOSS): 'temp_processed_file' missing in details. "
                    f"Skipping conversion."
                )
                continue
            
            original_temp_path = Path(original_temp_path_str)
            if not original_temp_path.exists():
                logger.error(
                    f"Asset '{asset_name_for_log}', Map Key Index {map_key_index} (Tag: {processing_tag}) (GLOSS): Temporary file {original_temp_path_str} "
                    f"does not exist. Skipping conversion."
                )
                continue

            # Use map_key_index directly to access the FileRule
            # Ensure map_key_index is a valid index for context.files_to_process
            if not isinstance(map_key_index, int) or map_key_index < 0 or map_key_index >= len(context.files_to_process):
                logger.error(
                    f"Asset '{asset_name_for_log}', Map Key Index {map_key_index} (Tag: {processing_tag}) (GLOSS): Invalid map_key_index ({map_key_index}) for accessing files_to_process (len: {len(context.files_to_process)}). "
                    f"Skipping conversion."
                )
                continue
            
            original_file_rule = context.files_to_process[map_key_index]
            source_file_path_for_log = original_file_rule.file_path if hasattr(original_file_rule, 'file_path') else "Unknown source path"
            logger.debug(f"Asset '{asset_name_for_log}', Map Key Index {map_key_index} (Tag: {processing_tag}): Processing GLOSS map from '{original_temp_path_str}' (Original FileRule path: '{source_file_path_for_log}') for conversion.")

            image_data = ipu.load_image(str(original_temp_path))
            if image_data is None:
                logger.error(
                    f"Asset '{asset_name_for_log}', Map Key Index {map_key_index} (Tag: {processing_tag}): Failed to load image data from {original_temp_path_str}. "
                    f"Skipping conversion."
                )
                continue

            # Perform Inversion
            inverted_image_data: np.ndarray
            if np.issubdtype(image_data.dtype, np.floating):
                inverted_image_data = 1.0 - image_data
                inverted_image_data = np.clip(inverted_image_data, 0.0, 1.0)
                logger.debug(f"Asset '{asset_name_for_log}', Map Key Index {map_key_index} (Tag: {processing_tag}): Inverted float image data.")
            elif np.issubdtype(image_data.dtype, np.integer):
                max_val = np.iinfo(image_data.dtype).max
                inverted_image_data = max_val - image_data
                logger.debug(f"Asset '{asset_name_for_log}', Map Key Index {map_key_index} (Tag: {processing_tag}): Inverted integer image data (max_val: {max_val}).")
            else:
                logger.error(
                    f"Asset '{asset_name_for_log}', Map Key Index {map_key_index} (Tag: {processing_tag}): Unsupported image data type {image_data.dtype} "
                    f"for GLOSS map. Cannot invert. Skipping conversion."
                )
                continue
            
            # Save New Temporary (Roughness) Map
            new_temp_filename = f"rough_from_gloss_{processing_tag}{original_temp_path.suffix}"
            new_temp_path = context.engine_temp_dir / new_temp_filename
            
            save_success = ipu.save_image(str(new_temp_path), inverted_image_data)

            if save_success:
                logger.info(
                    f"Asset '{asset_name_for_log}', Map Key Index {map_key_index} (Tag: {processing_tag}): Converted GLOSS map {original_temp_path_str} "
                    f"to ROUGHNESS map {new_temp_path}."
                )
                
                update_dict = {'item_type': "MAP_ROUGH", 'item_type_override': "MAP_ROUGH"}
                
                modified_file_rule: Optional[FileRule] = None
                if hasattr(original_file_rule, 'model_copy') and callable(original_file_rule.model_copy): # Pydantic
                    modified_file_rule = original_file_rule.model_copy(update=update_dict)
                elif dataclasses.is_dataclass(original_file_rule): # Dataclass
                    modified_file_rule = dataclasses.replace(original_file_rule, **update_dict)
                else:
                    logger.error(f"Asset '{asset_name_for_log}', Map Key Index {map_key_index} (Tag: {processing_tag}): Original FileRule is neither Pydantic nor dataclass. Cannot modify. Skipping update for this rule.")
                    continue
                
                new_files_to_process[map_key_index] = modified_file_rule # Replace using map_key_index
                
                # Update context.processed_maps_details for this map_key_index
                map_details['temp_processed_file'] = str(new_temp_path)
                map_details['original_map_type_before_conversion'] = internal_map_type # Store the original internal type
                map_details['internal_map_type'] = "MAP_ROUGH" # Use the standardized MAP_ prefixed field
                map_details['map_type'] = "Roughness" # Keep standard type for metadata/naming consistency if needed
                map_details['status'] = "Converted_To_Rough"
                map_details['notes'] = map_details.get('notes', '') + "; Converted from GLOSS by GlossToRoughConversionStage"
                if 'base_pot_resolution_name' in map_details:
                    map_details['processed_resolution_name'] = map_details['base_pot_resolution_name']

                processed_a_gloss_map = True
            else:
                logger.error(
                    f"Asset '{asset_name_for_log}', Map Key Index {map_key_index} (Tag: {processing_tag}): Failed to save inverted ROUGHNESS map to {new_temp_path}. "
                    f"Original GLOSS FileRule remains."
                )
        
        context.files_to_process = new_files_to_process

        if processed_a_gloss_map:
            logger.info(
                f"Asset '{asset_name_for_log}': Gloss to Roughness conversion stage finished. Processed one or more maps and updated file list and map details."
            )
        else:
            logger.info(
                f"Asset '{asset_name_for_log}': No gloss maps were converted in GlossToRoughConversionStage. "
                f"File list for next stage contains original non-gloss maps and any gloss maps that failed or were ineligible for conversion."
            )

        return context