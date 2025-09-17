import logging
import numpy as np
from pathlib import Path
from typing import List

from .base_stage import ProcessingStage
from ..asset_context import AssetProcessingContext
from rule_structure import FileRule
from ...utils import image_processing_utils as ipu
from utils.path_utils import sanitize_filename

logger = logging.getLogger(__name__)

class NormalMapGreenChannelStage(ProcessingStage):
    """
    Processing stage to invert the green channel of normal maps if configured.
    This is often needed when converting between DirectX (Y-) and OpenGL (Y+) normal map formats.
    """

    def execute(self, context: AssetProcessingContext) -> AssetProcessingContext:
        """
        Identifies NORMAL maps, checks configuration for green channel inversion,
        performs inversion if needed, saves a new temporary file, and updates
        the AssetProcessingContext.
        """
        asset_name_for_log = context.asset_rule.asset_name if context.asset_rule else "Unknown Asset"
        if context.status_flags.get('skip_asset'):
            logger.debug(f"Asset '{asset_name_for_log}': Skipping NormalMapGreenChannelStage due to skip_asset flag.")
            return context

        if not context.processed_maps_details: # Check processed_maps_details primarily
            logger.debug(
                f"Asset '{asset_name_for_log}': No processed_maps_details in NormalMapGreenChannelStage. Skipping."
            )
            return context

        processed_a_normal_map = False

        # Iterate through processed maps, as FileRule objects don't have IDs directly
        for map_id_hex, map_details in context.processed_maps_details.items():
            # Check if the map is a processed normal map using the standardized internal_map_type
            internal_map_type = map_details.get('internal_map_type')
            if internal_map_type and internal_map_type.startswith("MAP_NRM") and map_details.get('status') == 'Processed':
                
                # Check configuration for inversion
                # Assuming general_settings is an attribute of config_obj and might be a dict or an object
                should_invert = False
                if hasattr(context.config_obj, 'general_settings'):
                    if isinstance(context.config_obj.general_settings, dict):
                        should_invert = context.config_obj.general_settings.get('invert_normal_map_green_channel_globally', False)
                    elif hasattr(context.config_obj.general_settings, 'invert_normal_map_green_channel_globally'):
                        should_invert = getattr(context.config_obj.general_settings, 'invert_normal_map_green_channel_globally', False)
                
                original_temp_path_str = map_details.get('temp_processed_file')
                if not original_temp_path_str:
                    logger.warning(f"Asset '{asset_name_for_log}': Normal map (ID: {map_id_hex}) missing 'temp_processed_file' in details. Skipping.")
                    continue
                
                original_temp_path = Path(original_temp_path_str)
                original_filename_for_log = original_temp_path.name

                if not should_invert:
                    logger.debug(
                        f"Asset '{asset_name_for_log}': Normal map green channel inversion not enabled. "
                        f"Skipping for {original_filename_for_log} (ID: {map_id_hex})."
                    )
                    continue

                if not original_temp_path.exists():
                    logger.error(
                        f"Asset '{asset_name_for_log}': Temporary file {original_temp_path} for normal map "
                        f"{original_filename_for_log} (ID: {map_id_hex}) does not exist. Cannot invert green channel."
                    )
                    continue

                image_data = ipu.load_image(original_temp_path)

                if image_data is None:
                    logger.error(
                        f"Asset '{asset_name_for_log}': Failed to load image from {original_temp_path} "
                        f"for normal map {original_filename_for_log} (ID: {map_id_hex})."
                    )
                    continue

                if image_data.ndim != 3 or image_data.shape[2] < 2: # Must have at least R, G channels
                    logger.error(
                        f"Asset '{asset_name_for_log}': Image {original_temp_path} for normal map "
                        f"{original_filename_for_log} (ID: {map_id_hex}) is not a valid RGB/normal map "
                        f"(ndim={image_data.ndim}, channels={image_data.shape[2] if image_data.ndim == 3 else 'N/A'}) "
                        f"for green channel inversion."
                    )
                    continue

                # Perform Green Channel Inversion
                modified_image_data = image_data.copy()
                try:
                    if np.issubdtype(modified_image_data.dtype, np.floating):
                        modified_image_data[:, :, 1] = 1.0 - modified_image_data[:, :, 1]
                    elif np.issubdtype(modified_image_data.dtype, np.integer):
                        max_val = np.iinfo(modified_image_data.dtype).max
                        modified_image_data[:, :, 1] = max_val - modified_image_data[:, :, 1]
                    else:
                        logger.error(
                            f"Asset '{asset_name_for_log}': Unsupported image data type "
                            f"{modified_image_data.dtype} for normal map {original_temp_path}. Cannot invert green channel."
                        )
                        continue
                except IndexError:
                     logger.error(
                        f"Asset '{asset_name_for_log}': Image {original_temp_path} for normal map "
                        f"{original_filename_for_log} (ID: {map_id_hex}) does not have a green channel (index 1) "
                        f"or has unexpected dimensions ({modified_image_data.shape}). Cannot invert."
                    )
                     continue

                # Save New Temporary (Modified Normal) Map
                # Sanitize map_details.get('map_type') in case it's missing, though it should be 'NORMAL' here
                map_type_for_filename = sanitize_filename(map_details.get('map_type', 'NORMAL'))
                new_temp_filename = f"normal_g_inv_{map_type_for_filename}_{map_id_hex}{original_temp_path.suffix}"
                new_temp_path = context.engine_temp_dir / new_temp_filename

                save_success = ipu.save_image(new_temp_path, modified_image_data)

                if save_success:
                    logger.info(
                        f"Asset '{asset_name_for_log}': Inverted green channel for NORMAL map "
                        f"{original_filename_for_log}, saved to {new_temp_path.name}."
                    )
                    # Update processed_maps_details for this map_id_hex
                    context.processed_maps_details[map_id_hex]['temp_processed_file'] = str(new_temp_path)
                    current_notes = context.processed_maps_details[map_id_hex].get('notes', '')
                    context.processed_maps_details[map_id_hex]['notes'] = \
                        f"{current_notes}; Green channel inverted by NormalMapGreenChannelStage".strip('; ')
                    
                    processed_a_normal_map = True
                else:
                    logger.error(
                        f"Asset '{asset_name_for_log}': Failed to save inverted normal map to {new_temp_path} "
                        f"for original {original_filename_for_log}."
                    )
            # No need to explicitly manage new_files_to_process list in this loop,
            # as we are modifying the temp_processed_file path within processed_maps_details.
            # The existing FileRule objects in context.files_to_process (if any) would
            # be linked to these details by a previous stage (e.g. IndividualMapProcessing)
            # if that stage populates a 'file_rule_id' in map_details.

        # context.files_to_process remains unchanged by this stage directly,
        # as we modify the data pointed to by processed_maps_details.

        if processed_a_normal_map:
            logger.info(f"Asset '{asset_name_for_log}': NormalMapGreenChannelStage processed relevant normal maps.")
        else:
            logger.debug(f"Asset '{asset_name_for_log}': No normal maps found or processed in NormalMapGreenChannelStage.")

        return context