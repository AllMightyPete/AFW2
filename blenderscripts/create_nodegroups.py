# Blender Script: Create/Update Node Groups from Asset Processor Output
# Version: 1.5
# Description: Scans a library processed by the Asset Processor Tool,
#              reads metadata.json files, and creates/updates corresponding
#              PBR node groups in the active Blender file.
# Changes v1.5:
#   - Corrected aspect ratio calculation (`calculate_aspect_correction_factor`)
#     to use actual image dimensions from a loaded reference image and the
#     `aspect_ratio_change_string`, mirroring original script logic for
#     "EVEN", "Xnnn", "Ynnn" formats.
#   - Added logic in main loop to load reference image for dimensions.
# Changes v1.3:
#   - Added logic to find the highest resolution present for an asset.
#   - Added logic to set a "HighestResolution" Value node in the parent group
#     (maps 1K->1.0, 2K->2.0, 4K->3.0, 8K->4.0).
# Changes v1.2:
#   - Added Base64 encoding for child node group names (PBRTYPE_...).
#   - Added fallback logic for reconstructing image paths with different extensions.
#   - Added logic to set custom asset preview for new parent groups (using lowest res COL map).
# Changes v1.1:
#   - Updated metadata parsing to match actual structure (using processed_map_resolutions, image_stats_1k, map_details).
#   - Added logic to reconstruct image file paths based on metadata and assumed naming convention.

import bpy
import os
import json
from pathlib import Path
import time
import re # For parsing aspect ratio string
import base64 # For encoding node group names
import sys

# --- USER CONFIGURATION ---

# Path to the root output directory of the Asset Processor Tool
# Example: r"G:\Assets\Processed"
# IMPORTANT: This should point to the base directory containing supplier folders (e.g., Poliigon)
# This will be overridden by command-line arguments if provided.
PROCESSED_ASSET_LIBRARY_ROOT = None

# Names of the required node group templates in the Blender file
PARENT_TEMPLATE_NAME = "Template_PBRSET"
CHILD_TEMPLATE_NAME = "Template_PBRTYPE"

# Labels of specific nodes within the PARENT template
ASPECT_RATIO_NODE_LABEL = "AspectRatioCorrection" # Value node for UV X-scaling factor
STATS_NODE_PREFIX = "Histogram-" # Prefix for Combine XYZ nodes storing stats (e.g., "Histogram-ROUGH")
HIGHEST_RESOLUTION_NODE_LABEL = "HighestResolution" # Value node to store highest res index

# Enable/disable the manifest system to track processed assets/maps
# If enabled, requires the blend file to be saved.
ENABLE_MANIFEST = False # Disabled based on user feedback in previous run

# Assumed filename pattern for processed images.
# [assetname], [maptype], [resolution], [ext] will be replaced.
# This should match OUTPUT_FILENAME_PATTERN from app_settings.json.
IMAGE_FILENAME_PATTERN = "[assetname]_[maptype]_[resolution].[ext]"

# Fallback extensions to try if the primary format from metadata is not found
# Order matters - first found will be used.
FALLBACK_IMAGE_EXTENSIONS = ['png', 'jpg', 'exr', 'tif']

# Map type(s) to use for generating the asset preview AND for aspect ratio calculation reference
# The script will look for these in order and use the first one found.
REFERENCE_MAP_TYPES = ["COL", "COL-1", "COL-2"] # Used for preview and aspect calc
# Preferred resolution order for reference image (lowest first is often faster)
REFERENCE_RESOLUTION_ORDER = ["1K", "512", "2K", "4K"] # Adjust as needed

# Mapping from resolution string to numerical value for the HighestResolution node
RESOLUTION_VALUE_MAP = {"1K": 1.0, "2K": 2.0, "4K": 3.0, "8K": 4.0}
# Order to check resolutions to find the highest present (highest value first)
RESOLUTION_ORDER_DESC = ["8K", "4K", "2K", "1K"] # Add others like "512" if needed and map them in RESOLUTION_VALUE_MAP

# Map PBR type strings (from metadata) to Blender color spaces
# Add more mappings as needed based on your metadata types
PBR_COLOR_SPACE_MAP = {
    "AO": "Non-Color", # Usually Non-Color, but depends on workflow
    "COL": "sRGB",
    "COL-1": "sRGB", # Handle variants if present in metadata
    "COL-2": "sRGB",
    "COL-3": "sRGB",
    "DISP": "Non-Color",
    "NRM": "Non-Color",
    "REFL": "Non-Color", # Reflection/Specular
    "ROUGH": "Non-Color",
    "METAL": "Non-Color",
    "OPC": "Non-Color", # Opacity/Alpha
    "TRN": "Non-Color", # Transmission
    "SSS": "sRGB",      # Subsurface Color
    "EMISS": "sRGB",    # Emission Color
    "NRMRGH": "Non-Color", # Added for merged map
    "FUZZ": "Non-Color",
    # Add other types like GLOSS, HEIGHT, etc. if needed
}
DEFAULT_COLOR_SPACE = "sRGB" # Fallback if map type not in the dictionary

# Map types for which stats should be applied (if found in metadata and node exists)
# Reads stats from the 'image_stats_1k' section of metadata.json
APPLY_STATS_FOR_MAP_TYPES = ["ROUGH", "DISP", "METAL", "AO", "REFL"] # Add others if needed

# Categories for which full nodegroup generation should occur
CATEGORIES_FOR_NODEGROUP_GENERATION = ["Surface", "Decal"]

# --- END USER CONFIGURATION ---


# --- Helper Functions ---

def encode_name_b64(name_str):
    """Encodes a string using URL-safe Base64 for node group names."""
    try:
        name_str = str(name_str)
        return base64.urlsafe_b64encode(name_str.encode('utf-8')).decode('ascii')
    except Exception as e:
        print(f"        Error base64 encoding '{name_str}': {e}")
        return name_str # Fallback to original name on error

def find_nodes_by_label(node_tree, label, node_type=None):
    """Finds ALL nodes in a node tree matching the label and optionally type."""
    if not node_tree:
        return []
    matching_nodes = []
    for node in node_tree.nodes:
        # Use node.label for labeled nodes, node.name for non-labeled (like Group Input/Output)
        node_identifier = node.label if node.label else node.name
        if node_identifier and node_identifier == label:
            if node_type is None or node.bl_idname == node_type or node.type == node_type: # Check bl_idname and type for flexibility
                matching_nodes.append(node)
    return matching_nodes

def add_tag_if_new(asset_data, tag_name):
    """Adds a tag to the asset data if it's not None/empty and doesn't already exist."""
    if not asset_data or not tag_name or not isinstance(tag_name, str):
        return False
    cleaned_tag_name = tag_name.strip()
    if not cleaned_tag_name:
        return False

    # Check if tag already exists (case-insensitive check might be better sometimes)
    if cleaned_tag_name not in [t.name for t in asset_data.tags]:
        try:
            asset_data.tags.new(cleaned_tag_name)
            print(f"        + Added Asset Tag: '{cleaned_tag_name}'")
            return True
        except Exception as e:
            print(f"        Error adding tag '{cleaned_tag_name}': {e}")
            return False
    return False # Tag already existed

def get_color_space(map_type):
    """Returns the appropriate Blender color space name for a given map type string."""
    # Attempt to map map_type (e.g., "MAP_COL", "COL-1", "NRMRGH") to a standard type for color space lookup.
    # PBR_COLOR_SPACE_MAP usually contains standard types like "COL", "NRM".
    map_type_upper = map_type.upper()

    # 1. Direct match (e.g., "NRMRGH", "COL")
    if map_type_upper in PBR_COLOR_SPACE_MAP:
        return PBR_COLOR_SPACE_MAP[map_type_upper]

    # 2. Handle variants like "COL-1", "MAP_ROUGH-2"
    # Try to get the part before a hyphen if a hyphen exists
    base_type_candidate = map_type_upper.split('-')[0]
    if base_type_candidate in PBR_COLOR_SPACE_MAP:
        return PBR_COLOR_SPACE_MAP[base_type_candidate]
    
    # 3. Handle cases like "MAP_COL" -> "COL"
    # This is a simple heuristic. A more robust solution would involve access to FILE_TYPE_DEFINITIONS.
    # For this script, we assume PBR_COLOR_SPACE_MAP might contain the direct standard_type.
    # Example: if map_type is "MAP_DIFFUSE" and PBR_COLOR_SPACE_MAP has "DIFFUSE"
    if base_type_candidate.startswith("MAP_") and len(base_type_candidate) > 4:
        short_type = base_type_candidate[4:] # Get "COL" from "MAP_COL"
        if short_type in PBR_COLOR_SPACE_MAP:
            return PBR_COLOR_SPACE_MAP[short_type]
            
    # Fallback if no specific rule found
    return DEFAULT_COLOR_SPACE

def calculate_aspect_correction_factor(image_width, image_height, aspect_string):
    """
    Calculates the UV X-axis scaling factor needed to correct distortion,
    based on image dimensions and the aspect_ratio_change_string ("EVEN", "Xnnn", "Ynnn").
    Mirrors the logic from the original POC script.
    Returns 1.0 if dimensions are invalid or string is "EVEN" or invalid.
    """
    if image_height <= 0 or image_width <= 0:
        print("        Warn: Invalid image dimensions for aspect ratio calculation. Returning 1.0.")
        return 1.0

    current_aspect_ratio = image_width / image_height

    if not aspect_string or aspect_string.upper() == "EVEN":
        # If scaling was even, the correction factor is just the image's aspect ratio
        # to make UVs match the image proportions.
        return current_aspect_ratio

    # Handle non-uniform scaling cases ("Xnnn", "Ynnn")
    # Use search instead of match to find anywhere in string (though unlikely needed based on format)
    match = re.search(r"([XY])(\d+)", aspect_string, re.IGNORECASE)
    if not match:
        print(f"        Warn: Invalid Scaling string format '{aspect_string}'. Returning current ratio {current_aspect_ratio:.4f} as fallback.")
        return current_aspect_ratio # Fallback to the image's own ratio

    axis = match.group(1).upper()
    try:
        amount = int(match.group(2))
        if amount <= 0:
            print(f"        Warn: Zero or negative Amount in Scaling string '{aspect_string}'. Returning current ratio {current_aspect_ratio:.4f}.")
            return current_aspect_ratio
    except ValueError:
        print(f"        Warn: Invalid Amount in Scaling string '{aspect_string}'. Returning current ratio {current_aspect_ratio:.4f}.")
        return current_aspect_ratio

    # Apply the non-uniform correction formula based on original script logic
    scaling_factor_percent = amount / 100.0
    correction_factor = current_aspect_ratio

    try:
        if axis == 'X':
            if scaling_factor_percent == 0: raise ZeroDivisionError("X scaling factor is zero")
            # If image was stretched horizontally (X > 1), divide UV.x by factor
            correction_factor = current_aspect_ratio / scaling_factor_percent
        elif axis == 'Y':
            # If image was stretched vertically (Y > 1), multiply UV.x by factor
            correction_factor = current_aspect_ratio * scaling_factor_percent
        # No 'else' needed as regex ensures X or Y

    except ZeroDivisionError as e:
        print(f"        Warn: Division by zero during aspect factor calculation ({e}). Returning current ratio {current_aspect_ratio:.4f}.")
        return current_aspect_ratio
    except Exception as e:
         print(f"        Error calculating aspect correction factor: {e}. Returning current ratio {current_aspect_ratio:.4f}.")
         return current_aspect_ratio

    return correction_factor


def reconstruct_image_path_with_fallback(asset_dir_path, asset_name, map_type, resolution, primary_format=None):
    """
    Constructs the expected image file path.
    If primary_format is provided, tries that first.
    Then falls back to common extensions if the path doesn't exist or primary_format was None.
    Returns the found path as a string, or None if not found.
    """
    if not all([asset_dir_path, asset_name, map_type, resolution]):
        print(f"    !!! ERROR: Missing data for path reconstruction ({asset_name}/{map_type}/{resolution}).")
        return None

    found_path = None

    # 1. Try the primary format if provided
    if primary_format:
        try:
            filename = IMAGE_FILENAME_PATTERN.format(
                assetname=asset_name,
                maptype=map_type,
                resolution=resolution,
                ext=primary_format.lower()
            )
            primary_path = asset_dir_path / filename
            if primary_path.is_file():
                return str(primary_path)
        except KeyError as e:
            print(f"    !!! ERROR: Missing key '{e}' in IMAGE_FILENAME_PATTERN. Cannot reconstruct path.")
            return None # Cannot proceed without valid pattern
        except Exception as e:
            print(f"    !!! ERROR reconstructing primary image path: {e}")
            # Continue to fallback

    # 2. Try fallback extensions
    for ext in FALLBACK_IMAGE_EXTENSIONS:
        # Skip if we already tried this extension as primary (and it failed)
        if primary_format and ext.lower() == primary_format.lower():
            continue
        try:
            fallback_filename = IMAGE_FILENAME_PATTERN.format(
                assetname=asset_name,
                maptype=map_type,
                resolution=resolution,
                ext=ext.lower()
            )
            fallback_path = asset_dir_path / fallback_filename
            if fallback_path.is_file():
                print(f"          Found fallback path: {str(fallback_path)}")
                return str(fallback_path) # Found it!
        except KeyError:
             # Should not happen if primary format worked, but handle defensively
             print(f"    !!! ERROR: Missing key in IMAGE_FILENAME_PATTERN during fallback. Cannot reconstruct path.")
             return None
        except Exception as e_fallback:
            print(f"    !!! ERROR reconstructing fallback image path ({ext}): {e_fallback}")
            continue # Try next extension

    # If we get here, neither primary nor fallbacks worked
    if primary_format:
        print(f"    !!! ERROR: Could not find image file for {map_type}/{resolution} using primary format '{primary_format}' or fallbacks {FALLBACK_IMAGE_EXTENSIONS}.")
    else:
        print(f"    !!! ERROR: Could not find image file for {map_type}/{resolution} using fallbacks {FALLBACK_IMAGE_EXTENSIONS}.")
    return None # Not found after all checks


# --- Manifest Functions ---

def get_manifest_path(context):
    """Gets the expected path for the manifest JSON file."""
    if not context or not context.blend_data or not context.blend_data.filepath:
        return None # Cannot determine path if blend file is not saved
    blend_path = Path(context.blend_data.filepath)
    manifest_filename = f"{blend_path.stem}_manifest.json"
    return blend_path.parent / manifest_filename

def load_manifest(context):
    """Loads the manifest data from the JSON file."""
    if not ENABLE_MANIFEST:
        return {} # Manifest disabled

    manifest_path = get_manifest_path(context)
    if not manifest_path:
        print("   Manifest Info: Blend file not saved. Cannot load manifest.")
        return {} # Cannot load without a path

    if not manifest_path.exists():
        print(f"   Manifest Info: No manifest file found at '{manifest_path.name}'. Starting fresh.")
        return {} # No manifest file exists yet

    try:
        with open(manifest_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        print(f"   Manifest Loaded from: {manifest_path.name}")
        # Basic validation (check if it's a dictionary)
        if not isinstance(data, dict):
             print(f"!!! WARNING: Manifest file '{manifest_path.name}' has invalid format (not a dictionary). Starting fresh. !!!")
             return {}
        return data
    except json.JSONDecodeError:
        print(f"!!! WARNING: Manifest file '{manifest_path.name}' is corrupted. Starting fresh. !!!")
        return {}
    except Exception as e:
        print(f"!!! ERROR: Could not load manifest file '{manifest_path.name}': {e} !!!")
        return {} # Treat as starting fresh on error

def save_manifest(context, manifest_data):
    """Saves the manifest data to the JSON file."""
    if not ENABLE_MANIFEST or not manifest_data: # Don't save if disabled or empty
        return False

    manifest_path = get_manifest_path(context)
    if not manifest_path:
        print("   Manifest Error: Blend file not saved. Cannot save manifest.")
        return False

    try:
        with open(manifest_path, 'w', encoding='utf-8') as f:
            json.dump(manifest_data, f, indent=2, sort_keys=True) # Use indent and sort for readability
        print(f"   Manifest Saved to: {manifest_path.name}")
        return True
    except Exception as e:
        print(f"!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!\n"
              f"!!! Manifest save FAILED to '{manifest_path.name}': {e} !!!\n"
              f"!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!")
        return False

def is_asset_processed(manifest_data, asset_name):
    """Checks if the entire asset (all its maps/resolutions) is marked as processed."""
    if not ENABLE_MANIFEST: return False
    # Basic check if asset entry exists. Detailed check happens at map level.
    return asset_name in manifest_data

def is_map_processed(manifest_data, asset_name, map_type, resolution):
    """Checks if a specific map type and resolution for an asset is processed."""
    if not ENABLE_MANIFEST: return False
    return resolution in manifest_data.get(asset_name, {}).get(map_type, [])

def update_manifest(manifest_data, asset_name, map_type=None, resolution=None):
    """Updates the manifest dictionary in memory."""
    if not ENABLE_MANIFEST: return False

    # Ensure asset entry exists
    if asset_name not in manifest_data:
        manifest_data[asset_name] = {}

    # If map_type and resolution are provided, update the specific map entry
    if map_type and resolution:
        if map_type not in manifest_data[asset_name]:
            manifest_data[asset_name][map_type] = []

        if resolution not in manifest_data[asset_name][map_type]:
            manifest_data[asset_name][map_type].append(resolution)
            manifest_data[asset_name][map_type].sort() # Keep sorted
            return True # Indicate that a change was made
    return False # No change made to this specific map/res


# --- Core Logic ---

def process_library(context, asset_library_root_override=None):
    global ENABLE_MANIFEST # Declare intent to modify global if needed
    global PROCESSED_ASSET_LIBRARY_ROOT # Allow modification of global
    """Scans the library, reads metadata, creates/updates node groups."""
    start_time = time.time()
    print(f"\n--- Starting Node Group Processing ({time.strftime('%Y-%m-%d %H:%M:%S')}) ---")
    print(f"  DEBUG: Received asset_library_root_override: {asset_library_root_override}")

    # --- Determine Asset Library Root ---
    if asset_library_root_override:
        PROCESSED_ASSET_LIBRARY_ROOT = asset_library_root_override
        print(f"Using asset library root from argument: '{PROCESSED_ASSET_LIBRARY_ROOT}'")
    elif not PROCESSED_ASSET_LIBRARY_ROOT:
        print("!!! ERROR: Processed asset library root not set in script and not provided via argument.")
        print("--- Script aborted. ---")
        return False
    print(f"  DEBUG: Using final PROCESSED_ASSET_LIBRARY_ROOT: {PROCESSED_ASSET_LIBRARY_ROOT}")

    # --- Pre-run Checks ---
    print("Performing pre-run checks...")
    valid_setup = True
    # 1. Check Library Root Path
    root_path = Path(PROCESSED_ASSET_LIBRARY_ROOT)
    if not root_path.is_dir():
        print(f"!!! ERROR: Processed asset library root directory not found or not a directory:")
        print(f"!!!        '{PROCESSED_ASSET_LIBRARY_ROOT}'")
        valid_setup = False
    else:
        print(f"   Asset Library Root: '{root_path}'")
    print(f"  DEBUG: Checking for templates: '{PARENT_TEMPLATE_NAME}', '{CHILD_TEMPLATE_NAME}'")

    # 2. Check Templates
    template_parent = bpy.data.node_groups.get(PARENT_TEMPLATE_NAME)
    template_child = bpy.data.node_groups.get(CHILD_TEMPLATE_NAME)
    if not template_parent:
        print(f"!!! ERROR: Parent template node group '{PARENT_TEMPLATE_NAME}' not found in this Blender file.")
        valid_setup = False
    if not template_child:
        print(f"!!! ERROR: Child template node group '{CHILD_TEMPLATE_NAME}' not found in this Blender file.")
        valid_setup = False
    if template_parent and template_child:
         print(f"   Found Templates: '{PARENT_TEMPLATE_NAME}', '{CHILD_TEMPLATE_NAME}'")
    print(f"  DEBUG: Template Parent Found: {template_parent is not None}")
    print(f"  DEBUG: Template Child Found: {template_child is not None}")

    # 3. Check Blend File Saved (if manifest enabled)
    if ENABLE_MANIFEST and not context.blend_data.filepath:
        print(f"!!! WARNING: Manifest is enabled, but the current Blender file is not saved.")
        print(f"!!!          Manifest cannot be loaded or saved. Processing will continue without manifest checks.")
        ENABLE_MANIFEST = False # Disable manifest for this run

    if not valid_setup:
        print("\n--- Script aborted due to configuration errors. Please fix the issues above. ---")
        return False
    print("Pre-run checks passed.")
    # --- End Pre-run Checks ---

    manifest_data = load_manifest(context)
    manifest_needs_saving = False

    # --- Initialize Counters ---
    metadata_files_found = 0
    assets_processed = 0
    assets_skipped_manifest = 0
    parent_groups_created = 0
    parent_groups_updated = 0
    child_groups_created = 0
    child_groups_updated = 0
    images_loaded = 0
    images_assigned = 0
    maps_processed = 0
    maps_skipped_manifest = 0
    errors_encountered = 0
    previews_set = 0
    highest_res_set = 0
    aspect_ratio_set = 0
    # --- End Counters ---

    print(f"\nScanning for metadata files in '{root_path}'...")

    # --- Scan for metadata.json ---
    # Scan one level deeper for supplier folders (e.g., Poliigon)
    # Then scan within each supplier for asset folders containing metadata.json
    metadata_paths = []
    for supplier_dir in root_path.iterdir():
        if supplier_dir.is_dir():
            # Now look for asset folders inside the supplier directory
            for asset_dir in supplier_dir.iterdir():
                if asset_dir.is_dir():
                    metadata_file = asset_dir / 'metadata.json'
                    if metadata_file.is_file():
                        metadata_paths.append(metadata_file)

    metadata_files_found = len(metadata_paths)
    print(f"Found {metadata_files_found} metadata.json files.")
    print(f"  DEBUG: Metadata paths found: {metadata_paths}")

    if metadata_files_found == 0:
        print("No metadata files found. Nothing to process.")
        print("--- Script Finished ---")
        return True # No work needed is considered success

    # --- Process Each Metadata File ---
    for metadata_path in metadata_paths:
        asset_dir_path = metadata_path.parent
        print(f"\n--- Processing Metadata: {metadata_path.relative_to(root_path)} ---")
        print(f"  DEBUG: Processing file: {metadata_path}")
        try:
            with open(metadata_path, 'r', encoding='utf-8') as f:
                metadata = json.load(f)

            # --- Extract Key Info ---
            asset_name = metadata.get("asset_name")
            supplier_name = metadata.get("supplier_name")
            archetype = metadata.get("archetype")
            asset_category = metadata.get("category", "Unknown")
            processed_resolutions = metadata.get("processed_map_resolutions", {}) # Default to empty dict
            merged_resolutions = metadata.get("merged_map_resolutions", {}) # Get merged maps too
            map_details = metadata.get("map_details", {}) # Default to empty dict
            image_stats_1k = metadata.get("image_stats_1k") # Dict: {map_type: {stats}}
            aspect_string = metadata.get("aspect_ratio_change_string")

            # Combine processed and merged maps for iteration
            all_map_resolutions = {**processed_resolutions, **merged_resolutions}

            # Validate essential data
            if not asset_name:
                print(f"    !!! ERROR: Metadata file is missing 'asset_name'. Skipping.")
                errors_encountered += 1
                continue
            if not all_map_resolutions:
                 print(f"    !!! ERROR: Metadata file has no 'processed_map_resolutions' or 'merged_map_resolutions'. Skipping asset '{asset_name}'.")
                 errors_encountered += 1
                 continue
            # map_details check remains a warning as merged maps won't be in it
            print(f"    DEBUG: Valid metadata loaded for asset: {asset_name}")

            print(f"  Asset Name: {asset_name}")

            # --- Determine Highest Resolution ---
            highest_resolution_value = 0.0
            highest_resolution_str = "Unknown"
            all_resolutions_present = set()
            if all_map_resolutions: # Check combined dict
                for res_list in all_map_resolutions.values():
                    if isinstance(res_list, list):
                         all_resolutions_present.update(res_list)

            if all_resolutions_present:
                for res_str in RESOLUTION_ORDER_DESC:
                    if res_str in all_resolutions_present:
                        highest_resolution_value = RESOLUTION_VALUE_MAP.get(res_str, 0.0)
                        highest_resolution_str = res_str
                        if highest_resolution_value > 0.0:
                            break # Found the highest valid resolution

            print(f"    Highest resolution found: {highest_resolution_str} (Value: {highest_resolution_value})")

            # --- Load Reference Image for Aspect Ratio ---
            ref_image_path = None
            ref_image_width = 0
            ref_image_height = 0
            ref_image_loaded = False
            # Use combined resolutions dict to find reference map
            for ref_map_type in REFERENCE_MAP_TYPES:
                if ref_map_type in all_map_resolutions:
                    available_resolutions = all_map_resolutions[ref_map_type]
                    lowest_res = None
                    for res_pref in REFERENCE_RESOLUTION_ORDER:
                        if res_pref in available_resolutions:
                            lowest_res = res_pref
                            break
                    if lowest_res:
                        # Get format from map_details if available, otherwise None
                        ref_map_details = map_details.get(ref_map_type, {})
                        ref_format = ref_map_details.get("output_format")
                        ref_image_path = reconstruct_image_path_with_fallback(
                            asset_dir_path=asset_dir_path,
                            asset_name=asset_name,
                            map_type=ref_map_type,
                            resolution=lowest_res,
                            primary_format=ref_format # Pass None if not in map_details
                        )
                        if ref_image_path:
                            break # Found a suitable reference image path

            if ref_image_path:
                print(f"    Loading reference image for aspect ratio: {Path(ref_image_path).name}")
                try:
                    # Load image temporarily
                    ref_img = bpy.data.images.load(ref_image_path, check_existing=True)
                    if ref_img:
                        ref_image_width = ref_img.size[0]
                        ref_image_height = ref_img.size[1]
                        ref_image_loaded = True
                        print(f"      Reference image dimensions: {ref_image_width}x{ref_image_height}")
                        # Remove the temporary image datablock to save memory
                        bpy.data.images.remove(ref_img)
                    else:
                        print(f"      !!! ERROR: Failed loading reference image via bpy.data.images.load: {ref_image_path}")
                except Exception as e_ref_load:
                    print(f"      !!! ERROR loading reference image '{ref_image_path}': {e_ref_load}")
            else:
                print(f"    !!! WARNING: Could not find suitable reference image ({REFERENCE_MAP_TYPES} at {REFERENCE_RESOLUTION_ORDER}) for aspect ratio calculation.")


            # --- Manifest Check (Asset Level - Basic) ---
            if ENABLE_MANIFEST and is_asset_processed(manifest_data, asset_name):
                # Perform a quick check if *any* map needs processing for this asset
                needs_processing = False
                for map_type, resolutions in all_map_resolutions.items(): # Check combined maps
                    for resolution in resolutions:
                        if not is_map_processed(manifest_data, asset_name, map_type, resolution):
                            needs_processing = True
                            break
                    if needs_processing:
                        break
                if not needs_processing:
                    print(f"  Skipping asset '{asset_name}' (already fully processed according to manifest).")
                    assets_skipped_manifest += 1
                    continue # Skip to next metadata file


            # Conditional skip based on asset_category
            if asset_category not in CATEGORIES_FOR_NODEGROUP_GENERATION:
                print(f"    Skipping nodegroup content generation for asset '{asset_name}' (Category: '{asset_category}'). Tag added.")
                assets_processed += 1 # Still count as processed for summary, even if skipped
                continue # Skip the rest of the processing for this asset

            # --- Parent Group Handling ---
            target_parent_name = f"PBRSET_{asset_name}"
            parent_group = bpy.data.node_groups.get(target_parent_name)
            is_new_parent = False

            if parent_group is None:
                print(f"  Creating new parent group: '{target_parent_name}'")
                print(f"    DEBUG: Copying parent template '{PARENT_TEMPLATE_NAME}'")
                parent_group = template_parent.copy()
                if not parent_group:
                    print(f"    !!! ERROR: Failed to copy parent template '{PARENT_TEMPLATE_NAME}'. Skipping asset '{asset_name}'.")
                    errors_encountered += 1
                    continue
                parent_group.name = target_parent_name
                parent_groups_created += 1
                is_new_parent = True
            else:
                print(f"  Updating existing parent group: '{target_parent_name}'")
                print(f"    DEBUG: Found existing parent group.")
                parent_groups_updated += 1

            # Ensure marked as asset
            if not parent_group.asset_data:
                try:
                    parent_group.asset_mark()
                    print(f"    Marked '{parent_group.name}' as asset.")
                except Exception as e_mark:
                    print(f"    !!! ERROR: Failed to mark group '{parent_group.name}' as asset: {e_mark}")
                    # Continue processing other parts if possible

            # Apply Asset Tags
            if parent_group.asset_data:
                if supplier_name:
                    add_tag_if_new(parent_group.asset_data, supplier_name)
                if archetype:
                    add_tag_if_new(parent_group.asset_data, archetype)
                if asset_category:
                    add_tag_if_new(parent_group.asset_data, asset_category)
                # Add other tags if needed


            # Apply Aspect Ratio Correction
            aspect_nodes = find_nodes_by_label(parent_group, ASPECT_RATIO_NODE_LABEL, 'ShaderNodeValue')
            if aspect_nodes:
                aspect_node = aspect_nodes[0]
                correction_factor = 1.0 # Default if ref image fails
                if ref_image_loaded:
                    correction_factor = calculate_aspect_correction_factor(ref_image_width, ref_image_height, aspect_string)
                    print(f"    Calculated aspect correction factor: {correction_factor:.4f}")
                else:
                    print(f"    !!! WARNING: Using default aspect ratio correction (1.0) due to missing reference image.")

                # Check if update is needed
                current_val = aspect_node.outputs[0].default_value
                if abs(current_val - correction_factor) > 0.0001:
                    aspect_node.outputs[0].default_value = correction_factor
                    print(f"    Set '{ASPECT_RATIO_NODE_LABEL}' value to {correction_factor:.4f} (was {current_val:.4f})")
                    aspect_ratio_set += 1

            # Apply Highest Resolution Value
            hr_nodes = find_nodes_by_label(parent_group, HIGHEST_RESOLUTION_NODE_LABEL, 'ShaderNodeValue')
            if hr_nodes:
                hr_node = hr_nodes[0]
                current_hr_val = hr_node.outputs[0].default_value
                if highest_resolution_value > 0.0 and abs(current_hr_val - highest_resolution_value) > 0.001:
                    hr_node.outputs[0].default_value = highest_resolution_value
                    print(f"    Set '{HIGHEST_RESOLUTION_NODE_LABEL}' value to {highest_resolution_value} ({highest_resolution_str}) (was {current_hr_val:.1f})")
                    highest_res_set += 1 # Count successful sets


            # Apply Stats (using image_stats_1k)
            if image_stats_1k and isinstance(image_stats_1k, dict):
                for map_type_to_stat in APPLY_STATS_FOR_MAP_TYPES:
                    if map_type_to_stat in image_stats_1k:
                        # Find the stats node in the parent group
                        stats_node_label = f"{STATS_NODE_PREFIX}{map_type_to_stat}"
                        stats_nodes = find_nodes_by_label(parent_group, stats_node_label, 'ShaderNodeCombineXYZ')
                        if stats_nodes:
                            stats_node = stats_nodes[0]
                            stats = image_stats_1k[map_type_to_stat]

                            if stats and isinstance(stats, dict):
                                # Handle potential list format for RGB stats (use first value) or direct float
                                def get_stat_value(stat_val):
                                    if isinstance(stat_val, list):
                                        return stat_val[0] if stat_val else None
                                    return stat_val

                                min_val = get_stat_value(stats.get("min"))
                                max_val = get_stat_value(stats.get("max"))
                                mean_val = get_stat_value(stats.get("mean")) # Often stored as 'mean' or 'avg'

                                updated_stat = False
                                # Check inputs exist before assigning
                                input_x = stats_node.inputs.get("X")
                                input_y = stats_node.inputs.get("Y")
                                input_z = stats_node.inputs.get("Z")

                                if input_x and min_val is not None and abs(input_x.default_value - min_val) > 0.0001:
                                    input_x.default_value = min_val
                                    updated_stat = True
                                if input_y and max_val is not None and abs(input_y.default_value - max_val) > 0.0001:
                                    input_y.default_value = max_val
                                    updated_stat = True
                                if input_z and mean_val is not None and abs(input_z.default_value - mean_val) > 0.0001:
                                    input_z.default_value = mean_val
                                    updated_stat = True

                                if updated_stat:
                                    print(f"    Set stats in '{stats_node_label}': Min={min_val:.4f}, Max={max_val:.4f}, Mean={mean_val:.4f}")

            # --- Set Asset Preview (only for new parent groups) ---
            # Use the reference image path found earlier if available
            if is_new_parent and parent_group.asset_data:
                if ref_image_loaded and ref_image_path: # Check if ref image was successfully loaded earlier
                    print(f"    Attempting to set preview from reference image: {Path(ref_image_path).name}")
                    try:
                        # Ensure the ID (node group) is the active one for the operator context
                        with context.temp_override(id=parent_group):
                             bpy.ops.ed.lib_id_load_custom_preview(filepath=ref_image_path)
                        print(f"      Successfully set custom preview.")
                        previews_set += 1
                    except Exception as e_preview:
                        print(f"      !!! ERROR setting custom preview: {e_preview}")
                        errors_encountered += 1
                else:
                     print(f"    Info: Could not set preview for '{asset_name}' as reference image was not found or loaded.")


            # --- Child Group Handling ---
            # Iterate through the COMBINED map types
            print(f"  DEBUG: Starting child group loop for asset '{asset_name}'. Map types: {list(all_map_resolutions.keys())}")
            for map_type, resolutions in all_map_resolutions.items():
                print(f"    Processing Map Type: {map_type}")

                # Determine if this is a merged map (not in map_details)
                is_merged_map = map_type not in map_details

                current_map_details = map_details.get(map_type, {})
                # For merged maps, primary_format will be None
                output_format = current_map_details.get("output_format")

                if not output_format and not is_merged_map:
                    # This case should ideally not happen if metadata is well-formed
                    # but handle defensively for processed maps.
                    print(f"      !!! WARNING: Missing 'output_format' in map_details for processed map '{map_type}'. Path reconstruction might fail.")
                    # We will rely solely on fallback for this map type

                # Find placeholder node in parent
                holder_nodes = find_nodes_by_label(parent_group, map_type, 'ShaderNodeGroup')
                if not holder_nodes:
                    print(f"      !!! WARNING: No placeholder node labeled '{map_type}' found in parent group '{parent_group.name}'. Skipping this map type.")
                    continue
                holder_node = holder_nodes[0] # Assume first is correct
                print(f"      DEBUG: Found placeholder node '{holder_node.label}' for map type '{map_type}'.")

                # Determine child group name (LOGICAL and ENCODED)
                logical_child_name = f"{asset_name}_{map_type}"
                target_child_name_b64 = encode_name_b64(logical_child_name) # Use Base64 name

                child_group = bpy.data.node_groups.get(target_child_name_b64) # Find using encoded name
                is_new_child = False

                if child_group is None:
                    print(f"      DEBUG: Child group '{target_child_name_b64}' not found. Creating new one.")
                    child_group = template_child.copy()
                    if not child_group:
                        print(f"        !!! ERROR: Failed to copy child template '{CHILD_TEMPLATE_NAME}'. Skipping map type '{map_type}'.")
                        errors_encountered += 1
                        continue
                    child_group.name = target_child_name_b64 # Set encoded name
                    child_groups_created += 1
                    is_new_child = True
                else:
                    print(f"      DEBUG: Found existing child group '{target_child_name_b64}'.")
                    child_groups_updated += 1

                # Assign child group to placeholder if needed
                if holder_node.node_tree != child_group:
                    try:
                        holder_node.node_tree = child_group
                        print(f"      Assigned child group '{child_group.name}' to placeholder '{holder_node.label}'.")
                    except TypeError as e_assign: # Catch potential type errors if placeholder isn't a group node
                         print(f"        !!! ERROR: Could not assign child group to placeholder '{holder_node.label}'. Is it a Group Node? Error: {e_assign}")
                         continue # Skip this map type if assignment fails

                # Link placeholder output to parent output socket
                try:
                    # Find parent's output node
                    group_output_node = next((n for n in parent_group.nodes if n.type == 'GROUP_OUTPUT'), None)
                    if group_output_node:
                        # Get the specific output socket on the placeholder (usually index 0 or named 'Color'/'Value')
                        source_socket = holder_node.outputs.get("Color") or holder_node.outputs.get("Value") or holder_node.outputs[0]
                        # Get the specific input socket on the parent output node (matching map_type)
                        target_socket = group_output_node.inputs.get(map_type)

                        if source_socket and target_socket:
                            # Check if link already exists
                            link_exists = any(link.from_socket == source_socket and link.to_socket == target_socket for link in parent_group.links)
                            if not link_exists:
                                parent_group.links.new(source_socket, target_socket)
                                print(f"        Linked '{holder_node.label}' output to parent output socket '{map_type}'.")

                except Exception as e_link:
                    print(f"        !!! ERROR linking sockets for '{map_type}': {e_link}")

                # Ensure parent output socket type is Color (if it exists)
                try:
                    # Use the interface API for modern Blender versions
                    item = parent_group.interface.items_tree.get(map_type)
                    if item and item.item_type == 'SOCKET' and item.in_out == 'OUTPUT':
                         # Common useful types: 'NodeSocketColor', 'NodeSocketVector', 'NodeSocketFloat'
                         # Defaulting to Color seems reasonable for most PBR outputs
                        if item.socket_type != 'NodeSocketColor':
                            item.socket_type = 'NodeSocketColor'
                except Exception as e_sock_type:
                    print(f"        Warn: Could not verify/set socket type for '{map_type}': {e_sock_type}")


                # --- Image Node Handling (Inside Child Group) ---
                if not isinstance(resolutions, list):
                     print(f"      !!! ERROR: Invalid format for resolutions list for map type '{map_type}'. Skipping.")
                     continue

                for resolution in resolutions:
                    # --- Manifest Check (Map/Resolution Level) ---
                    if ENABLE_MANIFEST and is_map_processed(manifest_data, asset_name, map_type, resolution):
                        maps_skipped_manifest += 1
                        continue
                    print(f"        DEBUG: Processing map '{map_type}' resolution '{resolution}'. Manifest skip check passed.")

                    print(f"        Processing Resolution: {resolution}")

                    # Reconstruct the image path using fallback logic
                    # Pass output_format (which might be None for merged maps)
                    image_path_str = reconstruct_image_path_with_fallback(
                        asset_dir_path=asset_dir_path,
                        asset_name=asset_name,
                        map_type=map_type,
                        resolution=resolution,
                        primary_format=output_format
                    )
                    print(f"          DEBUG: Reconstructed image path for {map_type}/{resolution}: {image_path_str}")

                    if not image_path_str:
                        # Error already printed by reconstruct function
                        errors_encountered += 1
                        continue # Skip this resolution if path not found

                    # Find image texture node within the CHILD group (labeled by resolution, e.g., "4K")
                    image_nodes = find_nodes_by_label(child_group, resolution, 'ShaderNodeTexImage')
                    if not image_nodes:
                        print(f"          !!! WARNING: No Image Texture node labeled '{resolution}' found in child group '{child_group.name}'. Cannot assign image.")
                        continue # Skip this resolution if node not found
                    print(f"          DEBUG: Found {len(image_nodes)} image node(s) labeled '{resolution}' in child group '{child_group.name}'.")

                    # --- Load Image ---
                    img = None
                    image_load_failed = False
                    try:
                        image_path = Path(image_path_str) # Path object created from already found path string
                        # Use check_existing=True to reuse existing datablocks if path matches
                        img = bpy.data.images.load(str(image_path), check_existing=True)
                        if not img:
                            print(f"          !!! ERROR: Failed loading image via bpy.data.images.load: {image_path_str}")
                            image_load_failed = True
                        else:
                            # Only count as loaded if bpy.data.images.load succeeded
                            # Check if it's newly loaded or reused
                            is_newly_loaded = img.library is None # Newly loaded images don't have a library initially
                            if is_newly_loaded: images_loaded += 1

                    except RuntimeError as e_runtime_load:
                        # Catch specific Blender runtime errors (e.g., unsupported format)
                        print(f"          !!! ERROR loading image '{image_path_str}': {e_runtime_load}")
                        image_load_failed = True
                    except Exception as e_gen_load:
                        print(f"          !!! UNEXPECTED ERROR loading image '{image_path_str}': {e_gen_load}")
                        image_load_failed = True
                        errors_encountered += 1

                    # --- Assign Image & Set Color Space ---
                    if not image_load_failed and img:
                        assigned_count_this_res = 0
                        for image_node in image_nodes:
                            if image_node.image != img:
                                image_node.image = img
                                assigned_count_this_res += 1

                        if assigned_count_this_res > 0:
                             images_assigned += assigned_count_this_res
                             print(f"          Assigned image '{img.name}' to {assigned_count_this_res} node(s).")

                        # Set Color Space
                        correct_color_space = get_color_space(map_type)
                        try:
                            if img.colorspace_settings.name != correct_color_space:
                                img.colorspace_settings.name = correct_color_space
                                print(f"          Set '{img.name}' color space -> {correct_color_space}")
                        except TypeError as e_cs: # Handle case where colorspace name is invalid
                             print(f"          !!! WARNING: Could not set color space '{correct_color_space}' for image '{img.name}'. Is the color space available in Blender? Error: {e_cs}")
                        except Exception as e_cs_gen:
                             print(f"          !!! ERROR setting color space for image '{img.name}': {e_cs_gen}")


                        # --- Update Manifest (Map/Resolution Level) ---
                        if update_manifest(manifest_data, asset_name, map_type, resolution):
                            manifest_needs_saving = True
                        maps_processed += 1

                    else:
                        # Increment error count if loading failed
                        if image_load_failed: errors_encountered += 1

                # --- End Resolution Loop ---
            # --- End Map Type Loop ---

            assets_processed += 1

        except FileNotFoundError:
            print(f"    !!! ERROR: Metadata file not found (should not happen if scan worked): {metadata_path}")
            errors_encountered += 1
        except json.JSONDecodeError:
            print(f"    !!! ERROR: Invalid JSON in metadata file: {metadata_path}")
            errors_encountered += 1
        except Exception as e_main_loop:
            print(f"    !!! UNEXPECTED ERROR processing asset from {metadata_path}: {e_main_loop}")
            import traceback
            traceback.print_exc() # Print detailed traceback for debugging
            errors_encountered += 1
            # Continue to the next asset

    # --- End Metadata File Loop ---

    # --- Final Manifest Save ---
    if ENABLE_MANIFEST and manifest_needs_saving:
        print("\nAttempting final manifest save...")
        save_manifest(context, manifest_data)
    elif ENABLE_MANIFEST:
        print("\nManifest is enabled, but no changes require saving.")
    # --- End Final Manifest Save ---

    # --- Final Summary ---
    end_time = time.time()
    duration = end_time - start_time
    print("\n--- Script Run Finished ---")
    print(f"Duration: {duration:.2f} seconds")
    print(f"Metadata Files Found: {metadata_files_found}")
    print(f"Assets Processed/Attempted: {assets_processed}")
    if ENABLE_MANIFEST:
        print(f"Assets Skipped (Manifest): {assets_skipped_manifest}")
        print(f"Maps Skipped (Manifest): {maps_skipped_manifest}")
    print(f"Parent Groups Created: {parent_groups_created}")
    print(f"Parent Groups Updated: {parent_groups_updated}")
    print(f"Child Groups Created: {child_groups_created}")
    print(f"Child Groups Updated: {child_groups_updated}")
    print(f"Images Loaded: {images_loaded}")
    print(f"Image Nodes Assigned: {images_assigned}")
    print(f"Individual Maps Processed: {maps_processed}")
    print(f"Asset Previews Set: {previews_set}")
    print(f"Highest Resolution Nodes Set: {highest_res_set}")
    print(f"Aspect Ratio Nodes Set: {aspect_ratio_set}")
    if errors_encountered > 0:
        print(f"!!! Errors Encountered: {errors_encountered} !!!")
    print("---------------------------")

    # --- Explicit Save ---
    print(f"  DEBUG: Attempting explicit save for file: {bpy.data.filepath}")
    try:
        bpy.ops.wm.save_as_mainfile(filepath=bpy.data.filepath)
        print("\n--- Explicitly saved the .blend file. ---")
    except Exception as e_save:
        print(f"\n!!! ERROR explicitly saving .blend file: {e_save} !!!")
        errors_encountered += 1 # Count save errors

    return True


# --- Execution Block ---

if __name__ == "__main__":
    # Ensure we are running within Blender
    try:
        import bpy
        import base64 # Ensure base64 is imported here too if needed globally
        import sys
    except ImportError:
        print("!!! ERROR: This script must be run from within Blender. !!!")
    else:
        # --- Argument Parsing for Asset Library Root ---
        asset_root_arg = None
        try:
            # Blender arguments passed after '--' appear in sys.argv
            if "--" in sys.argv:
                args_after_dash = sys.argv[sys.argv.index("--") + 1:]
                if len(args_after_dash) >= 1:
                    asset_root_arg = args_after_dash[0]
                    print(f"Found asset library root argument: {asset_root_arg}")
                else:
                    print("Info: '--' found but no arguments after it.")
        except Exception as e:
            print(f"Error parsing command line arguments: {e}")
        # --- End Argument Parsing ---

        process_library(bpy.context, asset_library_root_override=asset_root_arg)
