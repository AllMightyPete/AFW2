import logging
from typing import List, Dict, Optional # Added Optional

import numpy as np

from .base_stage import ProcessingStage
# Import necessary context classes and utils
from ..asset_context import SaveVariantsInput, SaveVariantsOutput
from processing.utils import image_saving_utils as isu # Absolute import
from utils.path_utils import get_filename_friendly_map_type # Absolute import

log = logging.getLogger(__name__)


class SaveVariantsStage(ProcessingStage):
    """
    Takes final processed image data and configuration, calls the
    save_image_variants utility, and returns the results.
    """

    def execute(self, input_data: SaveVariantsInput) -> SaveVariantsOutput:
        """
        Calls isu.save_image_variants with data from input_data.
        """
        internal_map_type = input_data.internal_map_type
        # The input_data for SaveVariantsStage doesn't directly contain the ProcessingItem.
        # It receives data *derived* from a ProcessingItem by previous stages.
        # For debugging, we'd need to pass more context or rely on what's in output_filename_pattern_tokens.
        resolution_key_from_tokens = input_data.output_filename_pattern_tokens.get('resolution', 'UnknownResKey')
        log_prefix = f"Save Variants Stage (Type: {internal_map_type}, ResKey: {resolution_key_from_tokens})"
        
        log.info(f"{log_prefix}: Starting.")
        log.debug(f"{log_prefix}: Input image_data shape: {input_data.image_data.shape if input_data.image_data is not None else 'None'}")
        log.debug(f"{log_prefix}: Input source_bit_depth_info: {input_data.source_bit_depth_info}")
        log.debug(f"{log_prefix}: Configured image_resolutions for saving: {input_data.image_resolutions}")
        log.debug(f"{log_prefix}: Output filename pattern tokens: {input_data.output_filename_pattern_tokens}")

        # Initialize output object with default failure state
        result = SaveVariantsOutput(
            saved_files_details=[],
            status="Failed",
            error_message="Initialization error"
        )

        if input_data.image_data is None or input_data.image_data.size == 0:
            result.error_message = "Input image data is None or empty."
            log.error(f"{log_prefix}: {result.error_message}")
            return result

        try:
            # --- Prepare arguments for save_image_variants ---

            # Get the filename-friendly base map type using the helper
            # This assumes the save utility expects the friendly type. Adjust if needed.
            base_map_type_friendly = get_filename_friendly_map_type(
                internal_map_type, input_data.file_type_defs
            )
            log.debug(f"{log_prefix}: Using filename-friendly base type '{base_map_type_friendly}' for saving.")

            save_args = {
                "source_image_data": input_data.image_data,
                "base_map_type": base_map_type_friendly, # Use the friendly type
                "source_bit_depth_info": input_data.source_bit_depth_info,
                "image_resolutions": input_data.image_resolutions,
                "file_type_defs": input_data.file_type_defs,
                "output_format_8bit": input_data.output_format_8bit,
                "output_format_16bit_primary": input_data.output_format_16bit_primary,
                "output_format_16bit_fallback": input_data.output_format_16bit_fallback,
                "png_compression_level": input_data.png_compression_level,
                "jpg_quality": input_data.jpg_quality,
                "output_filename_pattern_tokens": input_data.output_filename_pattern_tokens,
                "output_filename_pattern": input_data.output_filename_pattern,
                "resolution_threshold_for_jpg": input_data.resolution_threshold_for_jpg, # Added
            }

            log.debug(f"{log_prefix}: Calling save_image_variants utility with args: {save_args}")
            saved_files_details: List[Dict] = isu.save_image_variants(**save_args)

            if saved_files_details:
                log.info(f"{log_prefix}: Save utility completed successfully. Saved {len(saved_files_details)} variants: {[details.get('filepath') for details in saved_files_details]}")
                result.saved_files_details = saved_files_details
                result.status = "Processed"
                result.error_message = None
            else:
                # This might not be an error, maybe no variants were configured?
                log.warning(f"{log_prefix}: Save utility returned no saved file details. This might be expected if no resolutions/formats matched.")
                result.saved_files_details = []
                result.status = "Processed (No Output)" # Indicate processing happened but nothing saved
                result.error_message = "Save utility reported no files saved (check configuration/resolutions)."


        except Exception as e:
            log.exception(f"{log_prefix}: Error calling or executing save_image_variants: {e}")
            result.status = "Failed"
            result.error_message = f"Save utility call failed: {e}"
            result.saved_files_details = [] # Ensure empty list on error

        return result