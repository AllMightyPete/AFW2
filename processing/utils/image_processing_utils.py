import cv2
import numpy as np
from pathlib import Path
import math
from typing import Optional, Union, List, Tuple, Dict

# --- Basic Power-of-Two Utilities ---

def is_power_of_two(n: int) -> bool:
    """Checks if a number is a power of two."""
    return (n > 0) and (n & (n - 1) == 0)

def get_nearest_pot(value: int) -> int:
    """Finds the nearest power of two to the given value."""
    if value <= 0:
        return 1  # POT must be positive, return 1 as a fallback
    if is_power_of_two(value):
        return value

    lower_pot = 1 << (value.bit_length() - 1)
    upper_pot = 1 << value.bit_length()

    if (value - lower_pot) < (upper_pot - value):
        return lower_pot
    else:
        return upper_pot

def get_nearest_power_of_two_downscale(value: int) -> int:
    """
    Finds the nearest power of two that is less than or equal to the given value.
    If the value is already a power of two, it returns the value itself.
    Returns 1 if the value is less than 1.
    """
    if value < 1:
        return 1
    if is_power_of_two(value):
        return value
    # Find the largest power of two strictly less than value,
    # unless value itself is POT.
    # (1 << (value.bit_length() - 1)) achieves this.
    # Example: value=7 (0111, bl=3), 1<<2 = 4.
    # Example: value=8 (1000, bl=4), 1<<3 = 8.
    # Example: value=9 (1001, bl=4), 1<<3 = 8.
    return 1 << (value.bit_length() - 1)
# --- Dimension Calculation ---

def calculate_target_dimensions(
    original_width: int,
    original_height: int,
    target_width: Optional[int] = None,
    target_height: Optional[int] = None,
    resize_mode: str = "fit",  # e.g., "fit", "stretch", "max_dim_pot"
    ensure_pot: bool = False,
    allow_upscale: bool = False,
    target_max_dim_for_pot_mode: Optional[int] = None # Specific for "max_dim_pot"
) -> Tuple[int, int]:
    """
    Calculates target dimensions based on various modes and constraints.

    Args:
        original_width: Original width of the image.
        original_height: Original height of the image.
        target_width: Desired target width.
        target_height: Desired target height.
        resize_mode:
            - "fit": Scales to fit within target_width/target_height, maintaining aspect ratio.
                     Requires at least one of target_width or target_height.
            - "stretch": Scales to exactly target_width and target_height, ignoring aspect ratio.
                         Requires both target_width and target_height.
            - "max_dim_pot": Scales to fit target_max_dim_for_pot_mode while maintaining aspect ratio,
                             then finds nearest POT for each dimension. Requires target_max_dim_for_pot_mode.
        ensure_pot: If True, final dimensions will be adjusted to the nearest power of two.
        allow_upscale: If False, dimensions will not exceed original dimensions unless ensure_pot forces it.
        target_max_dim_for_pot_mode: Max dimension to use when resize_mode is "max_dim_pot".

    Returns:
        A tuple (new_width, new_height).
    """
    if original_width <= 0 or original_height <= 0:
        # Fallback for invalid original dimensions
        fallback_dim = 1
        if ensure_pot:
            if target_width and target_height:
                fallback_dim = get_nearest_pot(max(target_width, target_height, 1))
            elif target_width:
                fallback_dim = get_nearest_pot(target_width)
            elif target_height:
                fallback_dim = get_nearest_pot(target_height)
            elif target_max_dim_for_pot_mode:
                 fallback_dim = get_nearest_pot(target_max_dim_for_pot_mode)
            else: # Default POT if no target given
                fallback_dim = 256
            return (fallback_dim, fallback_dim)
        return (target_width or 1, target_height or 1)


    w, h = original_width, original_height

    if resize_mode == "max_dim_pot":
        if target_max_dim_for_pot_mode is None:
            raise ValueError("target_max_dim_for_pot_mode must be provided for 'max_dim_pot' resize_mode.")
        
        # Logic adapted from old processing_engine.calculate_target_dimensions
        ratio = w / h
        if ratio > 1:  # Width is dominant
            scaled_w = target_max_dim_for_pot_mode
            scaled_h = max(1, round(scaled_w / ratio))
        else:  # Height is dominant or square
            scaled_h = target_max_dim_for_pot_mode
            scaled_w = max(1, round(scaled_h * ratio))
        
        # Upscale check for this mode is implicitly handled by target_max_dim
        # If ensure_pot is true (as it was in the original logic), it's applied here
        # For this mode, ensure_pot is effectively always true for the final step
        w = get_nearest_pot(scaled_w)
        h = get_nearest_pot(scaled_h)
        return int(w), int(h)

    elif resize_mode == "fit":
        if target_width is None and target_height is None:
            raise ValueError("At least one of target_width or target_height must be provided for 'fit' mode.")
        
        if target_width and target_height:
            ratio_orig = w / h
            ratio_target = target_width / target_height
            if ratio_orig > ratio_target: # Original is wider than target aspect
                w_new = target_width
                h_new = max(1, round(w_new / ratio_orig))
            else: # Original is taller or same aspect
                h_new = target_height
                w_new = max(1, round(h_new * ratio_orig))
        elif target_width:
            w_new = target_width
            h_new = max(1, round(w_new / (w / h)))
        else: # target_height is not None
            h_new = target_height
            w_new = max(1, round(h_new * (w / h)))
        w, h = w_new, h_new

    elif resize_mode == "stretch":
        if target_width is None or target_height is None:
            raise ValueError("Both target_width and target_height must be provided for 'stretch' mode.")
        w, h = target_width, target_height
    
    else:
        raise ValueError(f"Unsupported resize_mode: {resize_mode}")

    if not allow_upscale:
        if w > original_width: w = original_width
        if h > original_height: h = original_height
    
    if ensure_pot:
        w = get_nearest_pot(w)
        h = get_nearest_pot(h)
        # Re-check upscale if POT adjustment made it larger than original and not allowed
        if not allow_upscale:
            if w > original_width: w = get_nearest_pot(original_width) # Get closest POT to original
            if h > original_height: h = get_nearest_pot(original_height)


    return int(max(1, w)), int(max(1, h))


# --- Image Statistics ---

def get_image_bit_depth(image_path_str: str) -> Optional[int]:
    """
    Determines the bit depth of an image file.
    """
    try:
        # Use IMREAD_UNCHANGED to preserve original bit depth
        img = cv2.imread(image_path_str, cv2.IMREAD_UNCHANGED)
        if img is None:
            # logger.error(f"Failed to read image for bit depth: {image_path_str}") # Use print for utils
            print(f"Warning: Failed to read image for bit depth: {image_path_str}")
            return None
        
        dtype_to_bit_depth = {
            np.dtype('uint8'): 8,
            np.dtype('uint16'): 16,
            np.dtype('float32'): 32, # Typically for EXR etc.
            np.dtype('int8'): 8, # Unlikely for images but good to have
            np.dtype('int16'): 16, # Unlikely
            # Add other dtypes if necessary
        }
        bit_depth = dtype_to_bit_depth.get(img.dtype)
        if bit_depth is None:
            # logger.warning(f"Unknown dtype {img.dtype} for image {image_path_str}, cannot determine bit depth.") # Use print for utils
            print(f"Warning: Unknown dtype {img.dtype} for image {image_path_str}, cannot determine bit depth.")
            pass # Return None
        return bit_depth
    except Exception as e:
        # logger.error(f"Error getting bit depth for {image_path_str}: {e}") # Use print for utils
        print(f"Error getting bit depth for {image_path_str}: {e}")
        return None

def get_image_channels(image_data: np.ndarray) -> Optional[int]:
    """Determines the number of channels in an image."""
    if image_data is None:
        return None
    if len(image_data.shape) == 2: # Grayscale
        return 1
    elif len(image_data.shape) == 3: # Color
        return image_data.shape[2]
    return None # Unknown shape

def calculate_image_stats(image_data: np.ndarray) -> Optional[Dict]:
    """
    Calculates min, max, mean for a given numpy image array.
    Handles grayscale and multi-channel images. Converts to float64 for calculation.
    Normalizes uint8/uint16 data to 0-1 range before calculating stats.
    """
    if image_data is None:
        return None
    try:
        data_float = image_data.astype(np.float64)

        if image_data.dtype == np.uint16:
            data_float /= 65535.0
        elif image_data.dtype == np.uint8:
            data_float /= 255.0
        
        stats = {}
        if len(data_float.shape) == 2:  # Grayscale (H, W)
            stats["min"] = float(np.min(data_float))
            stats["max"] = float(np.max(data_float))
            stats["mean"] = float(np.mean(data_float))
            stats["median"] = float(np.median(data_float))
        elif len(data_float.shape) == 3:  # Color (H, W, C)
            stats["min"] = [float(v) for v in np.min(data_float, axis=(0, 1))]
            stats["max"] = [float(v) for v in np.max(data_float, axis=(0, 1))]
            stats["mean"] = [float(v) for v in np.mean(data_float, axis=(0, 1))]
            stats["median"] = [float(v) for v in np.median(data_float, axis=(0, 1))]
        else:
            return None # Unsupported shape
        return stats
    except Exception:
        return {"error": "Error calculating image stats"}

# --- Aspect Ratio String ---

def normalize_aspect_ratio_change(original_width: int, original_height: int, resized_width: int, resized_height: int, decimals: int = 2) -> str:
    """
    Calculates the aspect ratio change string (e.g., "EVEN", "X133").
    """
    if original_width <= 0 or original_height <= 0:
        return "InvalidInput"
    if resized_width <= 0 or resized_height <= 0:
        return "InvalidResize"

    width_change_percentage = ((resized_width - original_width) / original_width) * 100
    height_change_percentage = ((resized_height - original_height) / original_height) * 100

    normalized_width_change = width_change_percentage / 100
    normalized_height_change = height_change_percentage / 100

    normalized_width_change = min(max(normalized_width_change + 1, 0), 2)
    normalized_height_change = min(max(normalized_height_change + 1, 0), 2)
    
    epsilon = 1e-9
    if abs(normalized_width_change) < epsilon and abs(normalized_height_change) < epsilon:
         closest_value_to_one = 1.0
    elif abs(normalized_width_change) < epsilon:
         closest_value_to_one = abs(normalized_height_change)
    elif abs(normalized_height_change) < epsilon:
         closest_value_to_one = abs(normalized_width_change)
    else:
         closest_value_to_one = min(abs(normalized_width_change), abs(normalized_height_change))

    scale_factor = 1 / (closest_value_to_one + epsilon) if abs(closest_value_to_one) < epsilon else 1 / closest_value_to_one

    scaled_normalized_width_change = scale_factor * normalized_width_change
    scaled_normalized_height_change = scale_factor * normalized_height_change

    output_width = round(scaled_normalized_width_change, decimals)
    output_height = round(scaled_normalized_height_change, decimals)

    if abs(output_width - 1.0) < epsilon: output_width = 1
    if abs(output_height - 1.0) < epsilon: output_height = 1

    # Helper to format the number part
    def format_value(val, dec):
        # Multiply by 10^decimals, convert to int to keep trailing zeros in effect
        # e.g. val=1.1, dec=2 -> 1.1 * 100 = 110
        # e.g. val=1.0, dec=2 -> 1.0 * 100 = 100 (though this might become "1" if it's exactly 1.0 before this)
        # The existing logic already handles output_width/height being 1.0 to produce "EVEN" or skip a component.
        # This formatting is for when output_width/height is NOT 1.0.
        return str(int(round(val * (10**dec))))

    if abs(output_width - output_height) < epsilon: # Handles original square or aspect maintained
        output = "EVEN"
    elif output_width != 1 and abs(output_height - 1.0) < epsilon : # Width changed, height maintained relative to width
        output = f"X{format_value(output_width, decimals)}"
    elif output_height != 1 and abs(output_width - 1.0) < epsilon: # Height changed, width maintained relative to height
        output = f"Y{format_value(output_height, decimals)}"
    else: # Both changed relative to each other
        output = f"X{format_value(output_width, decimals)}Y{format_value(output_height, decimals)}"
    return output

# --- Image Loading, Conversion, Resizing ---

def load_image(image_path: Union[str, Path], read_flag: int = cv2.IMREAD_UNCHANGED) -> Optional[np.ndarray]:
    """Loads an image from the specified path. Converts BGR/BGRA to RGB/RGBA if color."""
    try:
        img = cv2.imread(str(image_path), read_flag)
        if img is None:
            # print(f"Warning: Failed to load image: {image_path}") # Optional: for debugging utils
            return None

        # Ensure RGB/RGBA for color images
        if len(img.shape) == 3:
            if img.shape[2] == 4: # BGRA from OpenCV
                img = cv2.cvtColor(img, cv2.COLOR_BGRA2RGBA)
            elif img.shape[2] == 3: # BGR from OpenCV
                img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
        return img
    except Exception: # as e:
        # print(f"Error loading image {image_path}: {e}") # Optional: for debugging utils
        return None

def convert_bgr_to_rgb(image: np.ndarray) -> np.ndarray:
    """Converts an image from BGR/BGRA to RGB/RGBA color space."""
    if image is None or len(image.shape) < 3:
        return image # Return as is if not a color image or None
    
    if image.shape[2] == 4: # BGRA
        return cv2.cvtColor(image, cv2.COLOR_BGRA2RGBA) # Keep alpha, convert to RGBA
    elif image.shape[2] == 3: # BGR
        return cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
    return image # Return as is if not 3 or 4 channels

def convert_rgb_to_bgr(image: np.ndarray) -> np.ndarray:
    """Converts an image from RGB/RGBA to BGR/BGRA color space."""
    if image is None or len(image.shape) < 3:
        return image # Return as is if not a color image or None
    
    if image.shape[2] == 4: # RGBA
        return cv2.cvtColor(image, cv2.COLOR_RGBA2BGRA)
    elif image.shape[2] == 3: # RGB
        return cv2.cvtColor(image, cv2.COLOR_RGB2BGR)
    return image # Return as is if not 3 or 4 channels


def resize_image(image: np.ndarray, target_width: int, target_height: int, interpolation: Optional[int] = None) -> np.ndarray:
    """Resizes an image to target_width and target_height."""
    if image is None:
        raise ValueError("Cannot resize a None image.")
    if target_width <= 0 or target_height <= 0:
        raise ValueError("Target width and height must be positive.")

    original_height, original_width = image.shape[:2]

    if interpolation is None:
        # Default interpolation: Lanczos for downscaling, Cubic for upscaling/same
        if (target_width * target_height) < (original_width * original_height):
            interpolation = cv2.INTER_LANCZOS4
        else:
            interpolation = cv2.INTER_CUBIC
            
    return cv2.resize(image, (target_width, target_height), interpolation=interpolation)

# --- Image Saving ---

def save_image(
    image_path: Union[str, Path],
    image_data: np.ndarray,
    output_format: Optional[str] = None, # e.g. "png", "jpg", "exr"
    output_dtype_target: Optional[np.dtype] = None, # e.g. np.uint8, np.uint16, np.float16
    params: Optional[List[int]] = None,
    convert_to_bgr_before_save: bool = True # True for most formats except EXR
) -> bool:
    """
    Saves image data to a file. Handles data type and color space conversions.

    Args:
        image_path: Path to save the image.
        image_data: NumPy array of the image.
        output_format: Desired output format (e.g., 'png', 'jpg'). If None, derived from extension.
        output_dtype_target: Target NumPy dtype for saving (e.g., np.uint8, np.uint16).
                             If None, tries to use image_data.dtype or a sensible default.
        params: OpenCV imwrite parameters (e.g., [cv2.IMWRITE_JPEG_QUALITY, 90]).
        convert_to_bgr_before_save: If True and image is 3-channel, converts RGB to BGR.
                                   Set to False for formats like EXR that expect RGB.

    Returns:
        True if saving was successful, False otherwise.
    """
    if image_data is None:
        return False
    
    img_to_save = image_data.copy()
    path_obj = Path(image_path)
    path_obj.parent.mkdir(parents=True, exist_ok=True)

    # 1. Data Type Conversion
    if output_dtype_target is not None:
        if output_dtype_target == np.uint8 and img_to_save.dtype != np.uint8:
            if img_to_save.dtype == np.uint16: img_to_save = (img_to_save.astype(np.float32) / 65535.0 * 255.0).astype(np.uint8)
            elif img_to_save.dtype in [np.float16, np.float32, np.float64]: img_to_save = (np.clip(img_to_save, 0.0, 1.0) * 255.0).astype(np.uint8)
            else: img_to_save = img_to_save.astype(np.uint8)
        elif output_dtype_target == np.uint16 and img_to_save.dtype != np.uint16:
            if img_to_save.dtype == np.uint8: img_to_save = (img_to_save.astype(np.float32) / 255.0 * 65535.0).astype(np.uint16) # More accurate
            elif img_to_save.dtype in [np.float16, np.float32, np.float64]: img_to_save = (np.clip(img_to_save, 0.0, 1.0) * 65535.0).astype(np.uint16)
            else: img_to_save = img_to_save.astype(np.uint16)
        elif output_dtype_target == np.float16 and img_to_save.dtype != np.float16:
            if img_to_save.dtype == np.uint16: img_to_save = (img_to_save.astype(np.float32) / 65535.0).astype(np.float16)
            elif img_to_save.dtype == np.uint8: img_to_save = (img_to_save.astype(np.float32) / 255.0).astype(np.float16)
            elif img_to_save.dtype in [np.float32, np.float64]: img_to_save = img_to_save.astype(np.float16)
            # else: cannot convert to float16 easily
        elif output_dtype_target == np.float32 and img_to_save.dtype != np.float32:
             if img_to_save.dtype == np.uint16: img_to_save = (img_to_save.astype(np.float32) / 65535.0)
             elif img_to_save.dtype == np.uint8: img_to_save = (img_to_save.astype(np.float32) / 255.0)
             elif img_to_save.dtype == np.float16: img_to_save = img_to_save.astype(np.float32)


    # 2. Color Space Conversion (Internal RGB/RGBA -> BGR/BGRA for OpenCV)
    # Input `image_data` is assumed to be in RGB/RGBA format (due to `load_image` changes).
    # OpenCV's `imwrite` typically expects BGR/BGRA for formats like PNG, JPG.
    # EXR format usually expects RGB/RGBA.
    # The `convert_to_bgr_before_save` flag controls this behavior.
    current_format = output_format if output_format else path_obj.suffix.lower().lstrip('.')
    
    if convert_to_bgr_before_save and current_format != 'exr':
        # If image is 3-channel (RGB) or 4-channel (RGBA), convert to BGR/BGRA.
        if len(img_to_save.shape) == 3 and (img_to_save.shape[2] == 3 or img_to_save.shape[2] == 4):
            img_to_save = convert_rgb_to_bgr(img_to_save) # Handles RGB->BGR and RGBA->BGRA
    # If `convert_to_bgr_before_save` is False or format is 'exr',
    # the image (assumed RGB/RGBA) is saved as is.

    # 3. Save Image
    try:
        if params:
            cv2.imwrite(str(path_obj), img_to_save, params)
        else:
            cv2.imwrite(str(path_obj), img_to_save)
        return True
    except Exception: # as e:
        # print(f"Error saving image {path_obj}: {e}") # Optional: for debugging utils
        return False

# --- Common Map Transformations ---

import re
import logging

ipu_log = logging.getLogger(__name__)

def apply_common_map_transformations(
    image_data: np.ndarray,
    processing_map_type: str, # The potentially suffixed internal type
    invert_normal_green: bool,
    file_type_definitions: Dict[str, Dict],
    log_prefix: str
) -> Tuple[np.ndarray, str, List[str]]:
    """
    Applies common in-memory transformations (Gloss-to-Rough, Normal Green Invert).
    Returns potentially transformed image data, potentially updated map type, and notes.
    """
    transformation_notes = []
    current_image_data = image_data # Start with original data
    updated_processing_map_type = processing_map_type # Start with original type

    # Gloss-to-Rough
    # Check if the base type is Gloss (before suffix)
    base_map_type_match = re.match(r"(MAP_GLOSS)", processing_map_type)
    if base_map_type_match:
        ipu_log.info(f"{log_prefix}: Applying Gloss-to-Rough conversion.")
        inversion_succeeded = False
        if np.issubdtype(current_image_data.dtype, np.floating):
            current_image_data = 1.0 - current_image_data
            current_image_data = np.clip(current_image_data, 0.0, 1.0)
            ipu_log.debug(f"{log_prefix}: Inverted float image data for Gloss->Rough.")
            inversion_succeeded = True
        elif np.issubdtype(current_image_data.dtype, np.integer):
            max_val = np.iinfo(current_image_data.dtype).max
            current_image_data = max_val - current_image_data
            ipu_log.debug(f"{log_prefix}: Inverted integer image data (max_val: {max_val}) for Gloss->Rough.")
            inversion_succeeded = True
        else:
             ipu_log.error(f"{log_prefix}: Unsupported image data type {current_image_data.dtype} for GLOSS map. Cannot invert.")
             transformation_notes.append("Gloss-to-Rough FAILED (unsupported dtype)")

        if inversion_succeeded:
            # Update the type string itself (e.g., MAP_GLOSS-1 -> MAP_ROUGH-1)
            updated_processing_map_type = processing_map_type.replace("GLOSS", "ROUGH")
            ipu_log.info(f"{log_prefix}: Map type updated: '{processing_map_type}' -> '{updated_processing_map_type}'")
            transformation_notes.append("Gloss-to-Rough applied")

    # Normal Green Invert
    # Check if the base type is Normal (before suffix)
    base_map_type_match_nrm = re.match(r"(MAP_NRM)", processing_map_type)
    if base_map_type_match_nrm and invert_normal_green:
        ipu_log.info(f"{log_prefix}: Applying Normal Map Green Channel Inversion (Global Setting).")
        current_image_data = invert_normal_map_green_channel(current_image_data)
        transformation_notes.append("Normal Green Inverted (Global)")

    return current_image_data, updated_processing_map_type, transformation_notes

# --- Normal Map Utilities ---

def invert_normal_map_green_channel(normal_map: np.ndarray) -> np.ndarray:
    """
    Inverts the green channel of a normal map.
    Assumes the normal map is in RGB or RGBA format (channel order R, G, B, A).
    """
    if normal_map is None or len(normal_map.shape) < 3 or normal_map.shape[2] < 3:
        # Not a valid color image with at least 3 channels
        return normal_map

    # Ensure data is mutable
    inverted_map = normal_map.copy()

    # Invert the green channel (index 1)
    # Handle different data types
    if np.issubdtype(inverted_map.dtype, np.floating):
        inverted_map[:, :, 1] = 1.0 - inverted_map[:, :, 1]
    elif np.issubdtype(inverted_map.dtype, np.integer):
        max_val = np.iinfo(inverted_map.dtype).max
        inverted_map[:, :, 1] = max_val - inverted_map[:, :, 1]
    else:
        # Unsupported dtype, return original
        print(f"Warning: Unsupported dtype {inverted_map.dtype} for normal map green channel inversion.")
        return normal_map

    return inverted_map