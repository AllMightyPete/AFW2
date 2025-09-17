import logging
import cv2
import numpy as np
from pathlib import Path
from typing import List, Dict, Any, Tuple, Optional

# Potentially import ipu from ...utils import image_processing_utils as ipu
# Assuming ipu is available in the same utils directory or parent
try:
    from . import image_processing_utils as ipu
except ImportError:
    # Fallback for different import structures if needed, adjust based on actual project structure
    # For this project structure, the relative import should work.
    logging.warning("Could not import image_processing_utils using relative path. Attempting absolute import.")
    try:
        from processing.utils import image_processing_utils as ipu
    except ImportError:
        logging.error("Could not import image_processing_utils.")
        ipu = None # Handle case where ipu is not available

logger = logging.getLogger(__name__)

def save_image_variants(
    source_image_data: np.ndarray,
    base_map_type: str, # Filename-friendly map type
    source_bit_depth_info: List[Optional[int]],
    image_resolutions: Dict[str, int],
    file_type_defs: Dict[str, Dict[str, Any]],
    output_format_8bit: str,
    output_format_16bit_primary: str,
    output_format_16bit_fallback: str,
    png_compression_level: int,
    jpg_quality: int,
    output_filename_pattern_tokens: Dict[str, Any], # Must include 'output_base_directory': Path and 'asset_name': str
    output_filename_pattern: str,
    resolution_threshold_for_jpg: Optional[int] = None, # Added
    # Consider adding ipu or relevant parts of it if not importing globally
) -> List[Dict[str, Any]]:
    """
    Centralizes image saving logic, generating and saving various resolution variants
    according to configuration.

    Args:
        source_image_data (np.ndarray): High-res image data (in memory, potentially transformed).
        base_map_type (str): Final map type (e.g., "COL", "ROUGH", "NORMAL", "MAP_NRMRGH").
                             This is the filename-friendly map type.
        source_bit_depth_info (List[Optional[int]]): List of original source bit depth(s)
                                                     (e.g., [8], [16], [8, 16]). Can contain None.
        image_resolutions (Dict[str, int]): Dictionary mapping resolution keys (e.g., "4K")
                                            to max dimensions (e.g., 4096).
        file_type_defs (Dict[str, Dict[str, Any]]): Dictionary defining properties for map types,
                                                    including 'bit_depth_rule'.
        output_format_8bit (str): File extension for 8-bit output (e.g., "jpg", "png").
        output_format_16bit_primary (str): Primary file extension for 16-bit output (e.g., "png", "tif").
        output_format_16bit_fallback (str): Fallback file extension for 16-bit output.
        png_compression_level (int): Compression level for PNG output (0-9).
        jpg_quality (int): Quality level for JPG output (0-100).
        output_filename_pattern_tokens (Dict[str, Any]): Dictionary of tokens for filename
                                                        pattern replacement. Must include
                                                        'output_base_directory' (Path) and
                                                        'asset_name' (str).
        output_filename_pattern (str): Pattern string for generating output filenames
                                       (e.g., "[assetname]_[maptype]_[resolution].[ext]").

    Returns:
        List[Dict[str, Any]]: A list of dictionaries, each containing details about a saved file.
                              Example: [{'path': str, 'resolution_key': str, 'format': str,
                                         'bit_depth': int, 'dimensions': (w,h)}, ...]
    """
    if ipu is None:
        logger.error("image_processing_utils is not available. Cannot save images.")
        return []

    saved_file_details = []
    source_h, source_w = source_image_data.shape[:2]
    source_max_dim = max(source_h, source_w)

    # 1. Use provided configuration inputs (already available as function arguments)
    logger.info(f"SaveImageVariants: Starting for map type: {base_map_type}. Source shape: {source_image_data.shape}, Source bit depths: {source_bit_depth_info}")
    logger.debug(f"SaveImageVariants: Resolutions: {image_resolutions}, File Type Defs: {file_type_defs.keys()}, Output Formats: 8bit={output_format_8bit}, 16bit_pri={output_format_16bit_primary}, 16bit_fall={output_format_16bit_fallback}")
    logger.debug(f"SaveImageVariants: PNG Comp: {png_compression_level}, JPG Qual: {jpg_quality}")
    logger.debug(f"SaveImageVariants: Output Tokens: {output_filename_pattern_tokens}, Output Pattern: {output_filename_pattern}")
    logger.debug(f"SaveImageVariants: Received resolution_threshold_for_jpg: {resolution_threshold_for_jpg}") # Log received threshold

    # 2. Determine Target Bit Depth
    target_bit_depth = 8 # Default
    bit_depth_rule = file_type_defs.get(base_map_type, {}).get('bit_depth_rule', 'force_8bit')
    if bit_depth_rule not in ['force_8bit', 'respect_inputs']:
        logger.warning(f"Unknown bit_depth_rule '{bit_depth_rule}' for map type '{base_map_type}'. Defaulting to 'force_8bit'.")
        bit_depth_rule = 'force_8bit'

    if bit_depth_rule == 'respect_inputs':
        # Check if any source bit depth is > 8, ignoring None
        if any(depth is not None and depth > 8 for depth in source_bit_depth_info):
            target_bit_depth = 16
        else:
            target_bit_depth = 8
        logger.info(f"Bit depth rule 'respect_inputs' applied. Source bit depths: {source_bit_depth_info}. Target bit depth: {target_bit_depth}")
    else: # force_8bit
        target_bit_depth = 8
        logger.info(f"Bit depth rule 'force_8bit' applied. Target bit depth: {target_bit_depth}")


    # 3. Determine Output File Format(s)
    if target_bit_depth == 8:
        output_ext = output_format_8bit.lstrip('.').lower()
    elif target_bit_depth == 16:
        # Prioritize primary, fallback to fallback if primary is not supported/desired
        # For now, just use primary. More complex logic might be needed later.
        output_ext = output_format_16bit_primary.lstrip('.').lower()
        # Basic fallback logic example (can be expanded)
        if output_ext not in ['png', 'tif']: # Assuming common 16-bit formats
             output_ext = output_format_16bit_fallback.lstrip('.').lower()
             logger.warning(f"Primary 16-bit format '{output_format_16bit_primary}' might not be suitable. Using fallback '{output_format_16bit_fallback}'.")
    else:
        logger.error(f"Unsupported target bit depth: {target_bit_depth}. Defaulting to 8-bit format.")
        output_ext = output_format_8bit.lstrip('.').lower()
    
    current_output_ext = output_ext # Store the initial extension based on bit depth

    logger.info(f"SaveImageVariants: Determined target bit depth: {target_bit_depth}, Initial output format: {current_output_ext} for map type {base_map_type}")

    # 4. Generate and Save Resolution Variants
    # Sort resolutions by max dimension descending
    sorted_resolutions = sorted(image_resolutions.items(), key=lambda item: item[1], reverse=True)

    for res_key, res_max_dim in sorted_resolutions:
        logger.info(f"SaveImageVariants: Processing variant {res_key} ({res_max_dim}px) for {base_map_type}")

        # --- Prevent Upscaling ---
        # Skip this resolution variant if its target dimension is larger than the source image's largest dimension.
        if res_max_dim > source_max_dim:
            logger.info(f"SaveImageVariants: Skipping variant {res_key} ({res_max_dim}px) for {base_map_type} because target resolution is larger than source ({source_max_dim}px).")
            continue # Skip to the next resolution

        # Calculate target dimensions for valid variants (equal or smaller than source)
        if source_max_dim == res_max_dim:
            # Use source dimensions if target is equal
            target_w_res, target_h_res = source_w, source_h
            logger.info(f"SaveImageVariants: Using source resolution ({source_w}x{source_h}) for {res_key} variant of {base_map_type} as target matches source.")
        else: # Downscale (source_max_dim > res_max_dim)
            # Downscale, maintaining aspect ratio
            aspect_ratio = source_w / source_h
            if source_w >= source_h: # Use >= to handle square images correctly
                target_w_res = res_max_dim
                target_h_res = max(1, int(res_max_dim / aspect_ratio)) # Ensure height is at least 1
            else:
                target_h_res = res_max_dim
                target_w_res = max(1, int(res_max_dim * aspect_ratio)) # Ensure width is at least 1
            logger.info(f"SaveImageVariants: Calculated downscale for {base_map_type} {res_key}: from ({source_w}x{source_h}) to ({target_w_res}x{target_h_res})")


        # Resize source_image_data (only if necessary)
        if (target_w_res, target_h_res) == (source_w, source_h):
            # No resize needed if dimensions match
            variant_data = source_image_data.copy() # Copy to avoid modifying original if needed later
            logger.debug(f"SaveImageVariants: No resize needed for {base_map_type} {res_key}, using copy of source data.")
        else:
            # Perform resize only if dimensions differ (i.e., downscaling)
            interpolation_method = cv2.INTER_AREA # Good for downscaling
            try:
                variant_data = ipu.resize_image(source_image_data, target_w_res, target_h_res, interpolation=interpolation_method)
                if variant_data is None: # Check if resize failed
                    raise ValueError("ipu.resize_image returned None")
                logger.debug(f"SaveImageVariants: Resized variant data shape for {base_map_type} {res_key}: {variant_data.shape}")
            except Exception as e:
                logger.error(f"SaveImageVariants: Error resizing image for {base_map_type} {res_key} variant: {e}")
                continue # Skip this variant if resizing fails

        # Filename Construction
        current_tokens = output_filename_pattern_tokens.copy()
        current_tokens['maptype'] = base_map_type
        current_tokens['resolution'] = res_key
        
        # Determine final extension for this variant, considering JPG threshold
        final_variant_ext = current_output_ext
        
        # --- Start JPG Threshold Logging ---
        logger.debug(f"SaveImageVariants: JPG Threshold Check for {base_map_type} {res_key}:")
        logger.debug(f"  - target_bit_depth: {target_bit_depth}")
        logger.debug(f"  - resolution_threshold_for_jpg: {resolution_threshold_for_jpg}")
        logger.debug(f"  - target_w_res: {target_w_res}, target_h_res: {target_h_res}")
        logger.debug(f"  - max(target_w_res, target_h_res): {max(target_w_res, target_h_res)}")
        logger.debug(f"  - current_output_ext: {current_output_ext}")
        
        cond_bit_depth = target_bit_depth == 8
        cond_threshold_not_none = resolution_threshold_for_jpg is not None
        cond_res_exceeded = False
        if cond_threshold_not_none: # Avoid comparison if threshold is None
             cond_res_exceeded = max(target_w_res, target_h_res) > resolution_threshold_for_jpg
        cond_is_png = current_output_ext == 'png'
        
        logger.debug(f"  - Condition (target_bit_depth == 8): {cond_bit_depth}")
        logger.debug(f"  - Condition (resolution_threshold_for_jpg is not None): {cond_threshold_not_none}")
        logger.debug(f"  - Condition (max(res) > threshold): {cond_res_exceeded}")
        logger.debug(f"  - Condition (current_output_ext == 'png'): {cond_is_png}")
        # --- End JPG Threshold Logging ---

        if cond_bit_depth and cond_threshold_not_none and cond_res_exceeded and cond_is_png:
            final_variant_ext = 'jpg'
            logger.info(f"SaveImageVariants: Overriding 8-bit PNG to JPG for {base_map_type} {res_key} due to resolution {max(target_w_res, target_h_res)}px > threshold {resolution_threshold_for_jpg}px.")
        
        current_tokens['ext'] = final_variant_ext

        try:
            # Replace placeholders in the pattern
            filename = output_filename_pattern
            for token, value in current_tokens.items():
                 # Ensure value is string for replacement, handle Path objects later
                 filename = filename.replace(f"[{token}]", str(value))

            # Construct full output path
            output_base_directory = current_tokens.get('output_base_directory')
            if not isinstance(output_base_directory, Path):
                 logger.error(f"'output_base_directory' token is missing or not a Path object: {output_base_directory}. Cannot save file.")
                 continue # Skip this variant

            output_path = output_base_directory / filename
            logger.info(f"SaveImageVariants: Constructed output path for {base_map_type} {res_key}: {output_path}")

            # Ensure parent directory exists
            output_path.parent.mkdir(parents=True, exist_ok=True)
            logger.debug(f"SaveImageVariants: Ensured directory exists for {base_map_type} {res_key}: {output_path.parent}")

        except Exception as e:
            logger.error(f"SaveImageVariants: Error constructing filepath for {base_map_type} {res_key} variant: {e}")
            continue # Skip this variant if path construction fails


        # Prepare Save Parameters
        save_params_cv2 = []
        if final_variant_ext == 'jpg': # Check against final_variant_ext
            save_params_cv2.append(cv2.IMWRITE_JPEG_QUALITY)
            save_params_cv2.append(jpg_quality)
            logger.debug(f"SaveImageVariants: Using JPG quality: {jpg_quality} for {base_map_type} {res_key}")
        elif final_variant_ext == 'png': # Check against final_variant_ext
            save_params_cv2.append(cv2.IMWRITE_PNG_COMPRESSION)
            save_params_cv2.append(png_compression_level)
            logger.debug(f"SaveImageVariants: Using PNG compression level: {png_compression_level} for {base_map_type} {res_key}")
        # Add other format specific parameters if needed (e.g., TIFF compression)


        # Bit Depth Conversion is handled by ipu.save_image via output_dtype_target
        image_data_for_save = variant_data # Use the resized variant data directly

        # Determine the target dtype for ipu.save_image
        output_dtype_for_save: Optional[np.dtype] = None
        if target_bit_depth == 8:
            output_dtype_for_save = np.uint8
        elif target_bit_depth == 16:
            output_dtype_for_save = np.uint16
        # Add other target bit depths like float16/float32 if necessary
        # elif target_bit_depth == 32: # Assuming float32 for EXR etc.
        #     output_dtype_for_save = np.float32


        # Saving
        try:
            # ipu.save_image is expected to handle the actual cv2.imwrite call
            logger.debug(f"SaveImageVariants: Attempting to save {base_map_type} {res_key} to {output_path} with params {save_params_cv2}, target_dtype: {output_dtype_for_save}")
            success = ipu.save_image(
                str(output_path),
                image_data_for_save,
                output_dtype_target=output_dtype_for_save, # Pass the target dtype
                params=save_params_cv2
            )
            if success:
                logger.info(f"SaveImageVariants: Successfully saved {base_map_type} {res_key} variant to {output_path}")
                # Collect details for the returned list
                saved_file_details.append({
                    'path': str(output_path),
                    'resolution_key': res_key,
                    'format': final_variant_ext, # Log the actual saved format
                    'bit_depth': target_bit_depth,
                    'dimensions': (target_w_res, target_h_res)
                })
            else:
                logger.error(f"SaveImageVariants: Failed to save {base_map_type} {res_key} variant to {output_path} (ipu.save_image returned False)")

        except Exception as e:
            logger.error(f"SaveImageVariants: Error during ipu.save_image for {base_map_type} {res_key} variant to {output_path}: {e}", exc_info=True)
            # Continue to next variant even if one fails


        # Discard in-memory variant after saving (Python's garbage collection handles this)
        del variant_data
        del image_data_for_save


    # 5. Return List of Saved File Details
    logger.info(f"Finished saving variants for map type: {base_map_type}. Saved {len(saved_file_details)} variants.")
    return saved_file_details

# Optional Helper Functions (can be added here if needed)
# def _determine_target_bit_depth(...): ...
# def _determine_output_format(...): ...
# def _construct_variant_filepath(...): ...