# blenderscripts/create_materials.py
# Version: 1.2
# Description: Scans a library processed by the Asset Processor Tool,
#              reads metadata.json files, finds corresponding PBRSET node groups
#              in a specified Blender .blend file, and creates Blender materials
#              linking to those node groups. Skips assets if material already exists.
#              Sets material viewport properties and custom previews based on metadata.
# Changes v1.2:
#   - Modified to link PBRSET node groups directly from a specified .blend file path
#     passed as a command-line argument, instead of relying on an Asset Catalog name.
#   - Removed PBRSET_ASSET_LIBRARY_NAME configuration and related checks.
# Changes v1.1:
#   - Added logic to link PBRSET node groups from an external asset library.
#   - Added logic to skip processing if the target material already exists.
#   - Added configuration for the PBRSET asset library name.

import bpy
import os
import json
from pathlib import Path
import time
import base64 # Although not directly used here, keep for consistency if reusing more code later
import sys

# --- USER CONFIGURATION ---

# Path to the root output directory of the Asset Processor Tool
# Example: r"G:\Assets\Processed"
# IMPORTANT: This should point to the base directory containing supplier folders (e.g., Poliigon)
# This will be overridden by command-line arguments if provided.
PROCESSED_ASSET_LIBRARY_ROOT = None # Set to None initially

# Path to the .blend file containing the PBRSET node groups.
# This will be overridden by command-line arguments if provided.
NODEGROUP_BLEND_FILE_PATH = None # Set to None initially

# Name of the required template material in the Blender file
TEMPLATE_MATERIAL_NAME = "Template_PBRMaterial"

# Label of the placeholder Group node within the template material's node tree
# where the PBRSET node group will be linked
PLACEHOLDER_NODE_LABEL = "PBRSET_PLACEHOLDER"

# Prefix for the created materials
MATERIAL_NAME_PREFIX = "Mat_"

# Prefix used for the PBRSET node groups created by create_nodegroups.py
PBRSET_GROUP_PREFIX = "PBRSET_"

# Map type(s) to use for finding a reference image for the material preview
# The script will look for these in order and use the first one found.
REFERENCE_MAP_TYPES = ["COL", "COL-1", "COL-2"]

# Preferred resolution order for reference image (lowest first is often faster)
REFERENCE_RESOLUTION_ORDER = ["1K", "512", "2K", "4K"] # Adjust as needed

# Assumed filename pattern for processed images.
# [assetname], [maptype], [resolution], [ext] will be replaced.
# This should match OUTPUT_FILENAME_PATTERN from app_settings.json.
IMAGE_FILENAME_PATTERN = "[assetname]_[maptype]_[resolution].[ext]"

# Fallback extensions to try if the primary format from metadata is not found
# Order matters - first found will be used.
FALLBACK_IMAGE_EXTENSIONS = ['png', 'jpg', 'exr', 'tif']

# Map types to check in metadata's 'image_stats_1k' for viewport diffuse color
VIEWPORT_COLOR_MAP_TYPES = ["COL", "COL-1", "COL-2"]

# Map types to check in metadata's 'image_stats_1k' for viewport roughness
VIEWPORT_ROUGHNESS_MAP_TYPES = ["ROUGH"]

# Map types to check in metadata's 'image_stats_1k' for viewport metallic
VIEWPORT_METALLIC_MAP_TYPES = ["METAL"]

# --- END USER CONFIGURATION ---


# --- Helper Functions ---

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
                assetname=asset_name,        # Token is 'assetname'
                maptype=map_type,            # Token is 'maptype'
                resolution=resolution,       # Token is 'resolution'
                ext=primary_format.lower()   # Token is 'ext'
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
                assetname=asset_name,        # Token is 'assetname'
                maptype=map_type,            # Token is 'maptype'
                resolution=resolution,       # Token is 'resolution'
                ext=ext.lower()              # Token is 'ext'
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


def get_stat_value(stats_dict, map_type_list, stat_key):
    """
    Safely retrieves a specific statistic (e.g., 'mean') for the first matching
    map type from the provided list within the image_stats_1k dictionary.

    Args:
        stats_dict (dict): The 'image_stats_1k' dictionary from metadata.
        map_type_list (list): List of map type strings to check (e.g., ["COL", "COL-1"]).
        stat_key (str): The statistic key to retrieve (e.g., "mean", "min", "max").

    Returns:
        The found statistic value (can be float, list, etc.), or None if not found.
    """
    if not stats_dict or not isinstance(stats_dict, dict):
        return None

    for map_type in map_type_list:
        if map_type in stats_dict:
            map_stats = stats_dict[map_type]
            if isinstance(map_stats, dict) and stat_key in map_stats:
                return map_stats[stat_key] # Return the value for the first match
            else:
                pass # Continue checking other map types in the list

    return None # Return None if no matching map type or stat key was found


# --- Core Logic ---

def process_library_for_materials(context, asset_library_root_override=None, nodegroup_blend_file_path_override=None): # Add nodegroup blend file path override
    global PROCESSED_ASSET_LIBRARY_ROOT # Allow modification of global
    global NODEGROUP_BLEND_FILE_PATH # Allow modification of global
    """
    Scans the library, reads metadata, finds PBRSET node groups in the specified
    .blend file, and creates/updates materials linking to them.
    """
    print("DEBUG: Script started.")
    start_time = time.time()
    print(f"\n--- Starting Material Creation from Node Groups ({time.strftime('%Y-%m-%d %H:%M:%S')}) ---")
    print(f"  DEBUG: Received asset_library_root_override: {asset_library_root_override}")
    print(f"  DEBUG: Received nodegroup_blend_file_path_override: {nodegroup_blend_file_path_override}")


    # --- Determine Asset Library Root ---
    if asset_library_root_override:
        PROCESSED_ASSET_LIBRARY_ROOT = asset_library_root_override
        print(f"Using asset library root from argument: '{PROCESSED_ASSET_LIBRARY_ROOT}'")
    elif not PROCESSED_ASSET_LIBRARY_ROOT:
        print("!!! ERROR: Processed asset library root not set in script and not provided via argument.")
        print("--- Script aborted. ---")
        return False
    print(f"  DEBUG: Using final PROCESSED_ASSET_LIBRARY_ROOT: {PROCESSED_ASSET_LIBRARY_ROOT}")

    # --- Determine Nodegroup Blend File Path ---
    if nodegroup_blend_file_path_override:
        NODEGROUP_BLEND_FILE_PATH = nodegroup_blend_file_path_override
        print(f"Using nodegroup blend file path from argument: '{NODEGROUP_BLEND_FILE_PATH}'")
    elif not NODEGROUP_BLEND_FILE_PATH:
        print("!!! ERROR: Nodegroup blend file path not set in script and not provided via argument.")
        print("--- Script aborted. ---")
        return False
    print(f"  DEBUG: Using final NODEGROUP_BLEND_FILE_PATH: {NODEGROUP_BLEND_FILE_PATH}")


    # --- Pre-run Checks ---
    print("Performing pre-run checks...")
    valid_setup = True
    # 1. Check Processed Asset Library Root Path
    root_path = Path(PROCESSED_ASSET_LIBRARY_ROOT)
    if not root_path.is_dir():
        print(f"!!! ERROR: Processed asset library root directory not found or not a directory:")
        print(f"!!!        '{PROCESSED_ASSET_LIBRARY_ROOT}'")
        valid_setup = False
    else:
        print(f"   Processed Asset Library Root: '{root_path}'")

    # 2. Check Nodegroup Blend File Path
    pbrset_blend_file_path = Path(NODEGROUP_BLEND_FILE_PATH)
    if not pbrset_blend_file_path.is_file() or pbrset_blend_file_path.suffix.lower() != '.blend':
        print(f"!!! ERROR: Nodegroup blend file path is invalid or not a .blend file:")
        print(f"!!!        '{NODEGROUP_BLEND_FILE_PATH}'")
        valid_setup = False
    else:
        print(f"   Using PBRSET library file: '{pbrset_blend_file_path}'")


    # 3. Check Template Material and Placeholder Node
    template_mat = bpy.data.materials.get(TEMPLATE_MATERIAL_NAME)
    placeholder_node_found_in_template = False
    if not template_mat:
        print(f"!!! ERROR: Template material '{TEMPLATE_MATERIAL_NAME}' not found in this Blender file.")
        valid_setup = False
    elif not template_mat.use_nodes:
        print(f"!!! ERROR: Template material '{TEMPLATE_MATERIAL_NAME}' does not use nodes.")
        valid_setup = False
    else:
        placeholder_nodes = find_nodes_by_label(template_mat.node_tree, PLACEHOLDER_NODE_LABEL, 'ShaderNodeGroup')
        if not placeholder_nodes:
            print(f"!!! ERROR: Placeholder node '{PLACEHOLDER_NODE_LABEL}' not found in template material '{TEMPLATE_MATERIAL_NAME}'.")
            valid_setup = False
        else:
            placeholder_node_found_in_template = True
            print(f"   Found Template Material: '{TEMPLATE_MATERIAL_NAME}' with placeholder '{PLACEHOLDER_NODE_LABEL}'")
    print(f"  DEBUG: Template Material Found: {template_mat is not None}")
    print(f"  DEBUG: Placeholder Node Found in Template: {placeholder_node_found_in_template}")


    if not valid_setup:
        print("\n--- Script aborted due to configuration errors. Please fix the issues above. ---")
        return False
    print("Pre-run checks passed.")
    # --- End Pre-run Checks ---

    # --- Initialize Counters ---
    metadata_files_found = 0
    assets_processed = 0
    assets_skipped = 0
    materials_created = 0
    node_groups_linked = 0
    previews_set = 0
    viewport_colors_set = 0
    viewport_roughness_set = 0
    viewport_metallic_set = 0
    errors_encountered = 0
    pbrset_groups_missing_in_library = 0
    placeholder_nodes_missing = 0
    library_link_errors = 0
    # --- End Counters ---

    print(f"\nScanning for metadata files in '{root_path}'...")

    # --- Scan for metadata.json ---
    metadata_paths = []
    for supplier_dir in root_path.iterdir():
        if supplier_dir.is_dir():
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
    print(f"  DEBUG: Starting metadata file loop. Found {len(metadata_paths)} files.")
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
            processed_resolutions = metadata.get("processed_map_resolutions", {})
            merged_resolutions = metadata.get("merged_map_resolutions", {})
            map_details = metadata.get("map_details", {})
            image_stats_1k = metadata.get("image_stats_1k")

            all_map_resolutions = {**processed_resolutions, **merged_resolutions}

            if not asset_name:
                print(f"    !!! ERROR: Metadata file is missing 'asset_name'. Skipping.")
                errors_encountered += 1
                continue
            print(f"    DEBUG: Valid metadata loaded for asset: {asset_name}")


            print(f"  Asset Name: {asset_name}")

            # --- Determine Target Names ---
            target_material_name = f"{MATERIAL_NAME_PREFIX}{asset_name}"
            target_pbrset_group_name = f"{PBRSET_GROUP_PREFIX}{asset_name}"
            print(f"    DEBUG: Target Material Name: {target_material_name}")
            print(f"    DEBUG: Target PBRSET Group Name: {target_pbrset_group_name}")


            # --- Check if Material Already Exists (Skip Logic) ---
            if bpy.data.materials.get(target_material_name):
                print(f"  Skipping asset '{asset_name}': Material '{target_material_name}' already exists.")
                assets_skipped += 1
                continue # Move to the next metadata file
            print(f"    DEBUG: Material '{target_material_name}' does not exist. Proceeding with creation.")


            # --- Create New Material ---
            print(f"  Creating new material: '{target_material_name}'")
            print(f"    DEBUG: Copying template material '{TEMPLATE_MATERIAL_NAME}'")
            material = template_mat.copy()
            if not material:
                print(f"    !!! ERROR: Failed to copy template material '{TEMPLATE_MATERIAL_NAME}'. Skipping asset '{asset_name}'.")
                errors_encountered += 1
                continue
            material.name = target_material_name
            materials_created += 1
            print(f"    DEBUG: Material '{material.name}' created.")


            # --- Find Placeholder Node ---
            if not material.use_nodes or not material.node_tree:
                 print(f"    !!! ERROR: Newly created material '{material.name}' does not use nodes or has no node tree. Skipping node linking.")
                 placeholder_node = None # Ensure it's None
            else:
                placeholder_nodes = find_nodes_by_label(material.node_tree, PLACEHOLDER_NODE_LABEL, 'ShaderNodeGroup')
                if not placeholder_nodes:
                    print(f"    !!! WARNING: Placeholder node '{PLACEHOLDER_NODE_LABEL}' not found in material '{material.name}'. Cannot link PBRSET group.")
                    placeholder_nodes_missing += 1
                    placeholder_node = None # Ensure it's None
                else:
                    placeholder_node = placeholder_nodes[0] # Assume first is correct
                    print(f"    DEBUG: Found placeholder node '{placeholder_node.label}' in material '{material.name}'.")


            # --- Find and Link PBRSET Node Group from Library ---
            linked_pbrset_group = None
            if placeholder_node and pbrset_blend_file_path: # Only proceed if placeholder exists and library file is known
                print(f"    DEBUG: Placeholder node exists and PBRSET library file path is known: {pbrset_blend_file_path}")
                # Check if the group is already linked in the current file
                existing_linked_group = bpy.data.node_groups.get(target_pbrset_group_name)
                # Check if the existing group's library filepath matches the target blend file path
                if existing_linked_group and existing_linked_group.library and bpy.path.abspath(existing_linked_group.library.filepath) == str(pbrset_blend_file_path.resolve()):
                     linked_pbrset_group = existing_linked_group
                     print(f"    Found existing linked PBRSET group: '{linked_pbrset_group.name}'")
                else:
                    # Link the node group from the external file
                    print(f"    Attempting to link PBRSET group '{target_pbrset_group_name}' from '{pbrset_blend_file_path.name}'...")
                    try:
                        with bpy.data.libraries.load(str(pbrset_blend_file_path.resolve()), link=True, relative=False) as (data_from, data_to):
                            if target_pbrset_group_name in data_from.node_groups:
                                data_to.node_groups = [target_pbrset_group_name]
                            else:
                                print(f"      !!! ERROR: Node group '{target_pbrset_group_name}' not found in library file '{pbrset_blend_file_path.name}'.")
                                pbrset_groups_missing_in_library += 1

                        # Verify linking was successful
                        linked_pbrset_group = bpy.data.node_groups.get(target_pbrset_group_name)
                        if not linked_pbrset_group or not linked_pbrset_group.library:
                            print(f"      !!! ERROR: Failed to link node group '{target_pbrset_group_name}'.")
                            library_link_errors += 1
                            linked_pbrset_group = None # Ensure it's None on failure
                        else:
                             print(f"      Successfully linked node group: '{linked_pbrset_group.name}'")

                    except Exception as e_lib_load:
                        print(f"      !!! ERROR loading library or linking node group: {e_lib_load}")
                        library_link_errors += 1
                        linked_pbrset_group = None # Ensure it's None on failure

            # --- Link Linked Node Group to Placeholder ---
            if placeholder_node and linked_pbrset_group:
                print(f"    DEBUG: Attempting to link PBRSET group '{linked_pbrset_group.name}' to placeholder '{placeholder_node.label}'.")
                if placeholder_node.node_tree != linked_pbrset_group:
                    try:
                        placeholder_node.node_tree = linked_pbrset_group
                        print(f"    Linked PBRSET group '{linked_pbrset_group.name}' to placeholder '{placeholder_node.label}'.")
                        node_groups_linked += 1
                    except TypeError as e_assign:
                        print(f"    !!! ERROR: Could not assign linked PBRSET group to placeholder '{placeholder_node.label}'. Is it a Group Node? Error: {e_assign}")
                        errors_encountered += 1
                    except Exception as e_link:
                         print(f"    !!! UNEXPECTED ERROR linking PBRSET group to placeholder: {e_link}")
                         errors_encountered += 1
            elif placeholder_node and not linked_pbrset_group:
                 print(f"    Info: Cannot link node group as it was not found or failed to link.")
            # No 'else' needed if placeholder_node is None, error already logged


            # --- Mark Material as Asset ---
            if not material.asset_data:
                print(f"    DEBUG: Marking material '{material.name}' as asset.")
                try:
                    material.asset_mark()
                    print(f"    Marked material '{material.name}' as asset.")
                except Exception as e_mark:
                    print(f"    !!! ERROR: Failed to mark material '{material.name}' as asset: {e_mark}")

            # --- Copy Asset Tags ---
            if material.asset_data and linked_pbrset_group and linked_pbrset_group.asset_data:
                print(f"    DEBUG: Copying asset tags from PBRSET group to material.")
                tags_copied_count = 0
                if supplier_name:
                    if add_tag_if_new(material.asset_data, supplier_name): tags_copied_count += 1
                if archetype:
                    if add_tag_if_new(material.asset_data, archetype): tags_copied_count += 1
                # Copy other tags from PBRSET group
                for ng_tag in linked_pbrset_group.asset_data.tags:
                     if add_tag_if_new(material.asset_data, ng_tag.name): tags_copied_count += 1


            # --- Set Custom Preview ---
            ref_image_path = None
            for ref_map_type in REFERENCE_MAP_TYPES:
                if ref_map_type in all_map_resolutions:
                    available_resolutions = all_map_resolutions[ref_map_type]
                    lowest_res = None
                    for res_pref in REFERENCE_RESOLUTION_ORDER:
                        if res_pref in available_resolutions:
                            lowest_res = res_pref
                            break
                    if lowest_res:
                        ref_map_details = map_details.get(ref_map_type, {})
                        ref_format = ref_map_details.get("output_format")
                        ref_image_path = reconstruct_image_path_with_fallback(
                            asset_dir_path=asset_dir_path,
                            asset_name=asset_name,
                            map_type=ref_map_type,
                            resolution=lowest_res,
                            primary_format=ref_format
                        )
                        if ref_image_path:
                            break

            if ref_image_path and material.asset_data:
                print(f"    Attempting to set preview from: {Path(ref_image_path).name}")
                try:
                    with context.temp_override(id=material):
                         bpy.ops.ed.lib_id_load_custom_preview(filepath=ref_image_path)
                    print(f"      Successfully set custom preview for material.")
                    previews_set += 1
                except RuntimeError as e_op:
                    print(f"      !!! ERROR running preview operator for material '{material.name}': {e_op}")
                    errors_encountered += 1
                except Exception as e_preview:
                    print(f"      !!! UNEXPECTED ERROR setting custom preview for material: {e_preview}")
                    errors_encountered += 1
            elif not material.asset_data:
                 print(f"    Info: Cannot set preview for '{material.name}' as it's not marked as an asset.")
            else:
                 print(f"    Info: Could not find suitable reference image ({REFERENCE_MAP_TYPES} at {REFERENCE_RESOLUTION_ORDER}) for preview.")


            # --- Set Viewport Properties from Stats ---
            if image_stats_1k and isinstance(image_stats_1k, dict):
                print(f"    DEBUG: Applying viewport properties from stats.")
                # Viewport Color
                color_mean = get_stat_value(image_stats_1k, VIEWPORT_COLOR_MAP_TYPES, 'mean')
                if isinstance(color_mean, list) and len(color_mean) >= 3:
                    color_rgba = (*color_mean[:3], 1.0)
                    print(f"    Debug: Raw color_mean from metadata: {color_mean[:3]}")
                    if tuple(material.diffuse_color[:3]) != tuple(color_rgba[:3]):
                         material.diffuse_color = color_rgba
                         print(f"    Set viewport color: {color_rgba[:3]}")
                         viewport_colors_set += 1

                # Viewport Roughness & Metallic Check
                roughness_mean = get_stat_value(image_stats_1k, VIEWPORT_ROUGHNESS_MAP_TYPES, 'mean')
                metallic_mean = get_stat_value(image_stats_1k, VIEWPORT_METALLIC_MAP_TYPES, 'mean')
                metal_map_found = metallic_mean is not None

                # Roughness
                if roughness_mean is not None:
                    rough_val = roughness_mean[0] if isinstance(roughness_mean, list) else roughness_mean
                    if isinstance(rough_val, (float, int)):
                        final_roughness = float(rough_val)
                        if not metal_map_found:
                            final_roughness = 1.0 - final_roughness
                        final_roughness = max(0.0, min(1.0, final_roughness))
                        if abs(material.roughness - final_roughness) > 0.001:
                             material.roughness = final_roughness
                             print(f"    Set viewport roughness: {final_roughness:.3f}")
                             viewport_roughness_set += 1

                # Metallic
                if metal_map_found:
                    metal_val = metallic_mean[0] if isinstance(metallic_mean, list) else metallic_mean
                    if isinstance(metal_val, (float, int)):
                        final_metallic = max(0.0, min(1.0, float(metal_val)))
                        if abs(material.metallic - final_metallic) > 0.001:
                             material.metallic = final_metallic
                             print(f"    Set viewport metallic: {final_metallic:.3f}")
                             viewport_metallic_set += 1
                else:
                    if material.metallic != 0.0:
                        material.metallic = 0.0
                        print(f"    Set viewport metallic to default: 0.0 (No metal map found)")
                        viewport_metallic_set += 1

            assets_processed += 1 # Count assets where processing was attempted (even if errors occurred later)

        except FileNotFoundError:
            print(f"    !!! ERROR: Metadata file not found (should not happen if scan worked): {metadata_path}")
            errors_encountered += 1
        except json.JSONDecodeError:
            print(f"    !!! ERROR: Invalid JSON in metadata file: {metadata_path}")
            errors_encountered += 1
        except Exception as e_main_loop:
            print(f"    !!! UNEXPECTED ERROR processing asset from {metadata_path}: {e_main_loop}")
            import traceback
            traceback.print_exc()
            errors_encountered += 1

    # --- End Metadata File Loop ---

    # --- Final Summary ---
    end_time = time.time()
    duration = end_time - start_time
    print("\n--- Material Creation Script Finished ---")
    print(f"Duration: {duration:.2f} seconds")
    print(f"Metadata Files Found: {metadata_files_found}")
    print(f"Assets Processed/Attempted: {assets_processed}")
    print(f"Assets Skipped (Already Exist): {assets_skipped}")
    print(f"Materials Created: {materials_created}")
    print(f"PBRSET Node Groups Linked: {node_groups_linked}")
    print(f"Material Previews Set: {previews_set}")
    print(f"Viewport Colors Set: {viewport_colors_set}")
    print(f"Viewport Roughness Set: {viewport_roughness_set}")
    print(f"Viewport Metallic Set: {viewport_metallic_set}")
    if pbrset_groups_missing_in_library > 0:
        print(f"!!! PBRSET Node Groups Missing in Library File: {pbrset_groups_missing_in_library} !!!")
    if library_link_errors > 0:
         print(f"!!! Library Link Errors: {library_link_errors} !!!")
    if placeholder_nodes_missing > 0:
         print(f"!!! Placeholder Nodes Missing in Materials: {placeholder_nodes_missing} !!!")
    if errors_encountered > 0:
        print(f"!!! Other Errors Encountered: {errors_encountered} !!!")
    print("---------------------------------------")

    # --- Explicit Save ---
    print(f"  DEBUG: Attempting explicit save for file: {bpy.data.filepath}")
    try:
        bpy.ops.wm.save_as_mainfile(filepath=bpy.data.filepath)
        print("\n--- Explicitly saved the .blend file. ---")
    except Exception as e_save:
        print(f"\n!!! ERROR explicitly saving .blend file: {e_save} !!!")
        # Note: We don't have an errors_encountered counter in this script currently.
        # If needed, we could add one or just rely on the printout.
        # For now, just printing the error is sufficient for debugging.

    return True


# --- Execution Block ---

if __name__ == "__main__":
    # Ensure we are running within Blender
    try:
        import bpy
        import sys
    except ImportError:
        print("!!! ERROR: This script must be run from within Blender. !!!")
    else:
        # --- Argument Parsing for Asset Library Root and Nodegroup Blend File ---
        asset_root_arg = None
        nodegroup_blend_file_arg = None
        try:
            # Blender arguments passed after '--' appear in sys.argv
            if "--" in sys.argv:
                args_after_dash = sys.argv[sys.argv.index("--") + 1:]
                if len(args_after_dash) >= 1:
                    asset_root_arg = args_after_dash[0]
                    print(f"Found asset library root argument: {asset_root_arg}")
                if len(args_after_dash) >= 2: # Check for second argument
                    nodegroup_blend_file_arg = args_after_dash[1]
                    print(f"Found nodegroup blend file path argument: {nodegroup_blend_file_arg}")
                else:
                    print("Info: '--' found but not enough arguments after it for nodegroup blend file.")
        except Exception as e:
            print(f"Error parsing command line arguments: {e}")
        # --- End Argument Parsing ---

        process_library_for_materials(bpy.context,
                                      asset_library_root_override=asset_root_arg,
                                      nodegroup_blend_file_path_override=nodegroup_blend_file_arg)