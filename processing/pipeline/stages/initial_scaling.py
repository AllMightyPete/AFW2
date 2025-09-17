import logging
from typing import Tuple, Optional # Added Optional

import cv2 # Assuming cv2 is available for interpolation flags
import numpy as np

from .base_stage import ProcessingStage
# Import necessary context classes and utils
from ..asset_context import InitialScalingInput, InitialScalingOutput
# ProcessingItem is no longer created here, so its import can be removed if not used otherwise.
# For now, keep rule_structure import if other elements from it might be needed,
# but ProcessingItem itself is not directly instantiated by this stage anymore.
# from rule_structure import ProcessingItem
from ...utils import image_processing_utils as ipu
import numpy as np
import cv2 # Added cv2 for interpolation flags (already used implicitly by ipu.resize_image)

log = logging.getLogger(__name__)

class InitialScalingStage(ProcessingStage):
    """
    Applies initial Power-of-Two (POT) downscaling to image data if configured
    and if the item is not already a 'LOWRES' variant.
    """

    def execute(self, input_data: InitialScalingInput) -> InitialScalingOutput:
        """
        Applies POT scaling based on input_data.initial_scaling_mode,
        unless input_data.resolution_key is 'LOWRES'.
        Passes through the resolution_key.
        """
        # Safely access source_file_path for logging, if provided by orchestrator via underscore attribute
        source_file_path = getattr(input_data, '_source_file_path', "UnknownSourcePath")
        log_prefix = f"InitialScalingStage (Source: {source_file_path}, ResKey: {input_data.resolution_key})"

        log.debug(f"{log_prefix}: Mode '{input_data.initial_scaling_mode}'. Received resolution_key: '{input_data.resolution_key}'")

        image_to_scale = input_data.image_data
        current_dimensions_wh = input_data.original_dimensions # Dimensions of the image_to_scale
        scaling_mode = input_data.initial_scaling_mode
        
        output_resolution_key = input_data.resolution_key # Pass through the resolution key

        if image_to_scale is None or image_to_scale.size == 0:
            log.warning(f"{log_prefix}: Input image data is None or empty. Skipping POT scaling.")
            return InitialScalingOutput(
                scaled_image_data=np.array([]),
                scaling_applied=False,
                final_dimensions=(0, 0),
                resolution_key=output_resolution_key
            )

        if not current_dimensions_wh:
            log.warning(f"{log_prefix}: Original dimensions not provided for POT scaling. Using current image shape.")
            h_pre_pot_scale, w_pre_pot_scale = image_to_scale.shape[:2]
        else:
            w_pre_pot_scale, h_pre_pot_scale = current_dimensions_wh
        
        final_image_data = image_to_scale # Default to original if no scaling happens
        scaling_applied = False

        # Skip POT scaling if the item is already a LOWRES variant or scaling mode is NONE
        if output_resolution_key == "LOWRES":
            log.info(f"{log_prefix}: Item is a 'LOWRES' variant. Skipping POT downscaling.")
        elif scaling_mode == "NONE":
            log.info(f"{log_prefix}: Mode is NONE. No POT scaling applied.")
        elif scaling_mode == "POT_DOWNSCALE":
            pot_w = ipu.get_nearest_power_of_two_downscale(w_pre_pot_scale)
            pot_h = ipu.get_nearest_power_of_two_downscale(h_pre_pot_scale)

            if (pot_w, pot_h) != (w_pre_pot_scale, h_pre_pot_scale):
                log.info(f"{log_prefix}: Applying POT Downscale from ({w_pre_pot_scale},{h_pre_pot_scale}) to ({pot_w},{pot_h}).")
                resized_img = ipu.resize_image(image_to_scale, pot_w, pot_h, interpolation=cv2.INTER_AREA)
                if resized_img is not None:
                    final_image_data = resized_img
                    scaling_applied = True
                    log.debug(f"{log_prefix}: POT Downscale applied successfully.")
                else:
                    log.warning(f"{log_prefix}: POT Downscale resize failed. Using pre-POT-scaled data.")
            else:
                log.info(f"{log_prefix}: Image already POT or smaller. No POT scaling needed.")
        else:
            log.warning(f"{log_prefix}: Unknown INITIAL_SCALING_MODE '{scaling_mode}'. Defaulting to NONE (no scaling).")

        # Determine final dimensions
        if final_image_data is not None and final_image_data.size > 0:
            final_h, final_w = final_image_data.shape[:2]
            final_dims_wh = (final_w, final_h)
        else:
            final_dims_wh = (0,0)
            if final_image_data is None: # Ensure it's an empty array for consistency if None
                 final_image_data = np.array([])

        return InitialScalingOutput(
            scaled_image_data=final_image_data,
            scaling_applied=scaling_applied,
            final_dimensions=final_dims_wh,
            resolution_key=output_resolution_key # Pass through the resolution key
        )