import logging
import shutil
from pathlib import Path
from typing import List, Dict, Optional

from .base_stage import ProcessingStage
from ..asset_context import AssetProcessingContext
from utils.path_utils import generate_path_from_pattern, sanitize_filename, get_filename_friendly_map_type # Absolute import
from rule_structure import FileRule # Assuming these are needed for type hints if not directly in context

log = logging.getLogger(__name__)
logger = logging.getLogger(__name__)

class OutputOrganizationStage(ProcessingStage):
    """
    Organizes output files by copying temporary processed files to their final destinations.
    """

    def execute(self, context: AssetProcessingContext) -> AssetProcessingContext:
        asset_name_for_log_early = context.asset_rule.asset_name if hasattr(context, 'asset_rule') and context.asset_rule else "Unknown Asset (early)"
        log.info(f"OUTPUT_ORG_DEBUG: Stage execution started for asset '{asset_name_for_log_early}'.")
        logger.debug(f"OUTPUT_ORG_DEBUG: Entry - context.output_base_path = {context.output_base_path}") # Modified
        log.info(f"OUTPUT_ORG_DEBUG: Received context.config_obj.output_directory_base (raw from config) = {getattr(context.config_obj, 'output_directory_base', 'N/A')}")
        # resolved_base = "N/A"
        # if hasattr(context.config_obj, '_settings') and context.config_obj._settings.get('OUTPUT_BASE_DIR'):
        #     base_dir_from_settings = context.config_obj._settings.get('OUTPUT_BASE_DIR')
            # Path resolution logic might be complex
        # log.info(f"OUTPUT_ORG_DEBUG: Received context.config_obj._settings.OUTPUT_BASE_DIR (resolved guess) = {resolved_base}")
        log.info(f"OUTPUT_ORG_DEBUG: context.processed_maps_details at start: {context.processed_maps_details}")
        """
        Copies temporary processed and merged files to their final output locations
        based on path patterns and updates AssetProcessingContext.
        """
        asset_name_for_log = context.asset_rule.asset_name if hasattr(context, 'asset_rule') and context.asset_rule else "Unknown Asset"
        logger.debug(f"Asset '{asset_name_for_log}': Starting output organization stage.")

        if context.status_flags.get('skip_asset'):
            logger.info(f"Asset '{asset_name_for_log}': Output organization skipped as 'skip_asset' is True.")
            return context

        current_status = context.asset_metadata.get('status', '')
        if current_status.startswith("Failed") or current_status == "Skipped":
            logger.info(f"Asset '{asset_name_for_log}': Output organization skipped due to prior status: {current_status}.")
            return context

        final_output_files: List[str] = []
        overwrite_existing = context.config_obj.overwrite_existing
        
        output_dir_pattern = getattr(context.config_obj, 'output_directory_pattern', "[supplier]/[assetname]")
        output_filename_pattern_config = getattr(context.config_obj, 'output_filename_pattern', "[assetname]_[maptype]_[resolution].[ext]")


        # A. Organize Processed Individual Maps
        if context.processed_maps_details:
            logger.debug(f"Asset '{asset_name_for_log}': Organizing {len(context.processed_maps_details)} processed individual map entries.")
            for processed_map_key, details in context.processed_maps_details.items():
                map_status = details.get('status')
                # Retrieve the internal map type first
                internal_map_type = details.get('internal_map_type', 'unknown_map_type')
                # Convert internal type to filename-friendly type using the helper
                file_type_definitions = getattr(context.config_obj, "FILE_TYPE_DEFINITIONS", {})
                base_map_type = get_filename_friendly_map_type(internal_map_type, file_type_definitions) # Final filename-friendly type

                # --- Handle maps processed by the SaveVariantsStage (identified by having saved_files_info) ---
                saved_files_info = details.get('saved_files_info') # This is a list of dicts from SaveVariantsOutput
                
                # Check if 'saved_files_info' exists and is a non-empty list.
                # This indicates the item was processed by SaveVariantsStage.
                if saved_files_info and isinstance(saved_files_info, list) and len(saved_files_info) > 0:
                    logger.debug(f"Asset '{asset_name_for_log}': Organizing {len(saved_files_info)} variants for map key '{processed_map_key}' (map type: {base_map_type}) from SaveVariantsStage.")
                    
                    # Use base_map_type (e.g., "COL") as the key for the map entry
                    map_metadata_entry = context.asset_metadata.setdefault('maps', {}).setdefault(base_map_type, {})
                    # map_type is now the key, so no need to store it inside the entry
                    # map_metadata_entry['map_type'] = base_map_type
                    map_metadata_entry.setdefault('variant_paths', {}) # Initialize if not present

                    processed_any_variant_successfully = False
                    failed_any_variant = False

                    for variant_index, variant_detail in enumerate(saved_files_info):
                        # Extract info from the save utility's output structure
                        temp_variant_path_str = variant_detail.get('path') # Key is 'path'
                        if not temp_variant_path_str:
                            logger.warning(f"Asset '{asset_name_for_log}': Variant {variant_index} for map '{processed_map_key}' is missing 'path' in saved_files_info. Skipping.")
                            # Optionally update variant_detail status if it's mutable and tracked, otherwise just skip
                            continue

                        temp_variant_path = Path(temp_variant_path_str)
                        if not temp_variant_path.is_file():
                             logger.warning(f"Asset '{asset_name_for_log}': Temporary variant file '{temp_variant_path}' for map '{processed_map_key}' not found. Skipping.")
                             continue

                        variant_resolution_key = variant_detail.get('resolution_key', f"varRes{variant_index}")
                        variant_ext = variant_detail.get('format', temp_variant_path.suffix.lstrip('.')) # Use 'format' key

                        token_data_variant = {
                            "assetname": asset_name_for_log,
                            "supplier": context.effective_supplier or "DefaultSupplier",
                            "maptype": base_map_type,
                            "resolution": variant_resolution_key,
                            "ext": variant_ext,
                            "incrementingvalue": getattr(context, 'incrementing_value', None),
                            "sha5": getattr(context, 'sha5_value', None)
                        }
                        token_data_variant_cleaned = {k: v for k, v in token_data_variant.items() if v is not None}
                        output_filename_variant = generate_path_from_pattern(output_filename_pattern_config, token_data_variant_cleaned)

                        try:
                            relative_dir_path_str_variant = generate_path_from_pattern(
                                pattern_string=output_dir_pattern,
                                token_data=token_data_variant_cleaned
                            )
                            logger.debug(f"OUTPUT_ORG_DEBUG: Variants - Using context.output_base_path = {context.output_base_path} for final_variant_path construction.") # Added
                            final_variant_path = Path(context.output_base_path) / Path(relative_dir_path_str_variant) / Path(output_filename_variant)
                            logger.debug(f"OUTPUT_ORG_DEBUG: Variants - Constructed final_variant_path = {final_variant_path}") # Added
                            final_variant_path.parent.mkdir(parents=True, exist_ok=True)

                            if final_variant_path.exists() and not overwrite_existing:
                                logger.info(f"Asset '{asset_name_for_log}': Output variant file {final_variant_path} for map '{processed_map_key}' (res: {variant_resolution_key}) exists and overwrite is disabled. Skipping copy.")
                                # Optionally update variant_detail status if needed
                            else:
                                shutil.copy2(temp_variant_path, final_variant_path)
                                logger.info(f"Asset '{asset_name_for_log}': Copied variant {temp_variant_path} to {final_variant_path} for map '{processed_map_key}'.")
                                final_output_files.append(str(final_variant_path))
                                # Optionally update variant_detail status if needed

                                # Store relative path in metadata
                                # Store only the filename, as it's relative to the metadata.json location
                                map_metadata_entry['variant_paths'][variant_resolution_key] = output_filename_variant
                                processed_any_variant_successfully = True

                        except Exception as e:
                            logger.error(f"Asset '{asset_name_for_log}': Failed to copy variant {temp_variant_path} for map key '{processed_map_key}' (res: {variant_resolution_key}). Error: {e}", exc_info=True)
                            context.status_flags['output_organization_error'] = True
                            context.asset_metadata['status'] = "Failed (Output Organization Error - Variant)"
                            # Optionally update variant_detail status if needed
                            failed_any_variant = True

                    # Update parent map detail status based on variant outcomes
                    if failed_any_variant:
                        details['status'] = 'Organization Failed (Save Utility Variants)'
                    elif processed_any_variant_successfully:
                        details['status'] = 'Organized (Save Utility Variants)'
                    else: # No variants were successfully copied (e.g., all skipped due to existing file or missing temp file)
                        details['status'] = 'Organization Skipped (No Save Utility Variants Copied/Needed)'

                # --- Handle older/other processing statuses (like single file processing) ---
                elif map_status in ['Processed', 'Processed_No_Variants', 'Converted_To_Rough']: # Add other single-file statuses if needed
                    temp_file_path_str = details.get('temp_processed_file')
                    if not temp_file_path_str:
                        logger.warning(f"Asset '{asset_name_for_log}': Skipping map key '{processed_map_key}' (status '{map_status}') due to missing 'temp_processed_file'.")
                        details['status'] = 'Organization Skipped (Missing Temp File)'
                        continue

                    temp_file_path = Path(temp_file_path_str)
                    if not temp_file_path.is_file():
                         logger.warning(f"Asset '{asset_name_for_log}': Temporary file '{temp_file_path}' for map '{processed_map_key}' not found. Skipping.")
                         details['status'] = 'Organization Skipped (Temp File Not Found)'
                         continue

                    resolution_str = details.get('processed_resolution_name', details.get('original_resolution_name', 'resX'))

                    token_data = {
                        "assetname": asset_name_for_log,
                        "supplier": context.effective_supplier or "DefaultSupplier",
                        "maptype": base_map_type,
                        "resolution": resolution_str,
                        "ext": temp_file_path.suffix.lstrip('.'),
                        "incrementingvalue": getattr(context, 'incrementing_value', None),
                        "sha5": getattr(context, 'sha5_value', None)
                    }
                    token_data_cleaned = {k: v for k, v in token_data.items() if v is not None}

                    output_filename = generate_path_from_pattern(output_filename_pattern_config, token_data_cleaned)

                    try:
                        relative_dir_path_str = generate_path_from_pattern(
                            pattern_string=output_dir_pattern,
                            token_data=token_data_cleaned
                        )
                        logger.debug(f"OUTPUT_ORG_DEBUG: SingleFile - Using context.output_base_path = {context.output_base_path} for final_path construction.") # Added
                        final_path = Path(context.output_base_path) / Path(relative_dir_path_str) / Path(output_filename)
                        logger.debug(f"OUTPUT_ORG_DEBUG: SingleFile - Constructed final_path = {final_path}") # Added
                        final_path.parent.mkdir(parents=True, exist_ok=True)

                        if final_path.exists() and not overwrite_existing:
                            logger.info(f"Asset '{asset_name_for_log}': Output file {final_path} for map '{processed_map_key}' exists and overwrite is disabled. Skipping copy.")
                            details['status'] = 'Organized (Exists, Skipped Copy)'
                        else:
                            shutil.copy2(temp_file_path, final_path)
                            logger.info(f"Asset '{asset_name_for_log}': Copied {temp_file_path} to {final_path} for map '{processed_map_key}'.")
                            final_output_files.append(str(final_path))
                            details['status'] = 'Organized'

                        details['final_output_path'] = str(final_path)

                        # Update asset_metadata for metadata.json
                        # Use base_map_type (e.g., "COL") as the key for the map entry
                        map_metadata_entry = context.asset_metadata.setdefault('maps', {}).setdefault(base_map_type, {})
                        # map_type is now the key, so no need to store it inside the entry
                        # map_metadata_entry['map_type'] = base_map_type
                        # Store single path in variant_paths, keyed by its resolution string
                        # Store only the filename, as it's relative to the metadata.json location
                        map_metadata_entry.setdefault('variant_paths', {})[resolution_str] = output_filename
                        # Remove old cleanup logic, as variant_paths is now the standard
                        # if 'variant_paths' in map_metadata_entry:
                        #     del map_metadata_entry['variant_paths']

                    except Exception as e:
                        logger.error(f"Asset '{asset_name_for_log}': Failed to copy {temp_file_path} for map key '{processed_map_key}'. Error: {e}", exc_info=True)
                        context.status_flags['output_organization_error'] = True
                        context.asset_metadata['status'] = "Failed (Output Organization Error)"
                        details['status'] = 'Organization Failed'

                # --- Handle other statuses (Skipped, Failed, etc.) ---
                else: # Catches statuses not explicitly handled above
                    logger.debug(f"Asset '{asset_name_for_log}': Skipping map key '{processed_map_key}' (status: '{map_status}') for organization as it's not a recognized final processed state or variant state.")
                    continue
        else:
            logger.debug(f"Asset '{asset_name_for_log}': No processed individual maps to organize.")

        # B. Organize Merged Maps (OBSOLETE BLOCK - Merged maps are handled by the main loop processing context.processed_maps_details)
        # The log "No merged maps to organize" will no longer appear from here.
        # If merged maps are not appearing, the issue is likely that they are not being added
        # to context.processed_maps_details with 'saved_files_info' by the orchestrator/SaveVariantsStage.

        # C. Organize Extra Files (e.g., previews, text files)
        logger.debug(f"Asset '{asset_name_for_log}': Checking for EXTRA files to organize.")
        extra_files_organized_count = 0
        if hasattr(context, 'files_to_process') and context.files_to_process:
            extra_subdir_name = getattr(context.config_obj, 'extra_files_subdir', 'Extra') # Default to 'Extra'

            for file_rule in context.files_to_process:
                if file_rule.item_type == 'EXTRA':
                    source_file_path = context.workspace_path / file_rule.file_path
                    if not source_file_path.is_file():
                        logger.warning(f"Asset '{asset_name_for_log}': EXTRA file '{source_file_path}' not found. Skipping.")
                        continue

                    # Basic token data for the asset's base output directory
                    # We don't use map_type, resolution, or ext for the base directory of extras.
                    # However, generate_path_from_pattern might expect them or handle their absence.
                    # For the base asset directory, only assetname and supplier are typically primary.
                    base_token_data = {
                        "assetname": asset_name_for_log,
                        "supplier": context.effective_supplier or "DefaultSupplier",
                        # Add other tokens if your output_directory_pattern uses them at the asset level
                        "incrementingvalue": getattr(context, 'incrementing_value', None),
                        "sha5": getattr(context, 'sha5_value', None)
                    }
                    base_token_data_cleaned = {k: v for k, v in base_token_data.items() if v is not None}

                    try:
                        asset_base_output_dir_str = generate_path_from_pattern(
                            pattern_string=output_dir_pattern, # Uses the same pattern as other maps for base dir
                            token_data=base_token_data_cleaned
                        )
                        # Destination: <output_base_path>/<asset_base_output_dir_str>/<extra_subdir_name>/<original_filename>
                        logger.debug(f"OUTPUT_ORG_DEBUG: ExtraFiles - Using context.output_base_path = {context.output_base_path} for final_dest_path construction.") # Added
                        final_dest_path = (Path(context.output_base_path) /
                                           Path(asset_base_output_dir_str) /
                                           Path(extra_subdir_name) /
                                           source_file_path.name) # Use original filename
                        logger.debug(f"OUTPUT_ORG_DEBUG: ExtraFiles - Constructed final_dest_path = {final_dest_path}") # Added

                        final_dest_path.parent.mkdir(parents=True, exist_ok=True)

                        if final_dest_path.exists() and not overwrite_existing:
                            logger.info(f"Asset '{asset_name_for_log}': EXTRA file destination {final_dest_path} exists and overwrite is disabled. Skipping copy.")
                        else:
                            shutil.copy2(source_file_path, final_dest_path)
                            logger.info(f"Asset '{asset_name_for_log}': Copied EXTRA file {source_file_path} to {final_dest_path}")
                            final_output_files.append(str(final_dest_path))
                            extra_files_organized_count += 1
                        
                        # Optionally, add more detailed tracking for extra files in context.asset_metadata
                        # For example:
                        # if 'extra_files_details' not in context.asset_metadata:
                        #     context.asset_metadata['extra_files_details'] = []
                        # context.asset_metadata['extra_files_details'].append({
                        #     'source_path': str(source_file_path),
                        #     'destination_path': str(final_dest_path),
                        #     'status': 'Organized'
                        # })

                    except Exception as e:
                        logger.error(f"Asset '{asset_name_for_log}': Failed to copy EXTRA file {source_file_path} to destination. Error: {e}", exc_info=True)
                        context.status_flags['output_organization_error'] = True
                        context.asset_metadata['status'] = "Failed (Output Organization Error - Extra Files)"
                        # Optionally, update status for the specific file_rule if tracked
        
        if extra_files_organized_count > 0:
            logger.info(f"Asset '{asset_name_for_log}': Successfully organized {extra_files_organized_count} EXTRA file(s).")
        else:
            logger.debug(f"Asset '{asset_name_for_log}': No EXTRA files were processed or found to organize.")


        context.asset_metadata['final_output_files'] = final_output_files

        if context.status_flags.get('output_organization_error'):
            logger.error(f"Asset '{asset_name_for_log}': Output organization encountered errors. Status: {context.asset_metadata['status']}")
        else:
            logger.info(f"Asset '{asset_name_for_log}': Output organization complete. {len(final_output_files)} files placed.")
        
        logger.debug(f"Asset '{asset_name_for_log}': Output organization stage finished.")
        return context