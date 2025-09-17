import datetime
import json
import logging
from pathlib import Path
from typing import Any, Dict

from ..asset_context import AssetProcessingContext
from .base_stage import ProcessingStage
from utils.path_utils import generate_path_from_pattern, sanitize_filename


logger = logging.getLogger(__name__)

class MetadataFinalizationAndSaveStage(ProcessingStage):
    """
    This stage finalizes the asset_metadata (e.g., setting processing end time,
    final status) and saves it as a JSON file.
    """

    def execute(self, context: AssetProcessingContext) -> AssetProcessingContext:
        """
        Finalizes metadata, determines output path, and saves the metadata JSON file.
        """
        asset_name_for_log = "Unknown Asset"
        if hasattr(context, 'asset_rule') and context.asset_rule and hasattr(context.asset_rule, 'asset_name'):
            asset_name_for_log = context.asset_rule.asset_name

        if not hasattr(context, 'asset_metadata') or not context.asset_metadata:
            if context.status_flags.get('skip_asset'):
                logger.info(
                    f"Asset '{asset_name_for_log}': "
                    f"Skipped before metadata initialization. No metadata file will be saved."
                )
            else:
                logger.warning(
                    f"Asset '{asset_name_for_log}': "
                    f"asset_metadata not initialized. Skipping metadata finalization and save."
                )
            return context
    
        # Check Skip Flag
        if context.status_flags.get('skip_asset'):
            context.asset_metadata['status'] = "Skipped"
            # context.asset_metadata['processing_end_time'] = datetime.datetime.now().isoformat()
            context.asset_metadata['notes'] = context.status_flags.get('skip_reason', 'Skipped early in pipeline')
            logger.info(
                f"Asset '{asset_name_for_log}': Marked as skipped. Reason: {context.asset_metadata['notes']}"
            )
            # Assuming we save metadata for skipped assets if it was initialized.
            # If not, the logic to skip saving would be here or before path generation.
            # However, if we are here, asset_metadata IS initialized.

        # A. Finalize Metadata
        # context.asset_metadata['processing_end_time'] = datetime.datetime.now().isoformat()

        # Determine final status (if not already set to Skipped)
        if context.asset_metadata.get('status') != "Skipped":
            has_errors = any(
                context.status_flags.get(error_flag)
                for error_flag in ['file_processing_error', 'merge_error', 'critical_error',
                                   'individual_map_processing_failed', 'metadata_save_error'] # Added more flags
            )
            if has_errors:
                context.asset_metadata['status'] = "Failed"
            else:
                context.asset_metadata['status'] = "Processed"

        # Add details of processed and merged maps
        # Restructure processed_map_details before assigning
        restructured_processed_maps = {}
        # getattr(context, 'processed_maps_details', {}) is the source (plural 'maps')
        original_processed_maps = getattr(context, 'processed_maps_details', {})
        
        # Define keys to remove at the top level of each map entry
        map_keys_to_remove = [
            "status", "source_file_path", "temp_processed_file", # Assuming "source_file_path" is the correct key
            "original_resolution_name", "base_pot_resolution_name", "processed_resolution_name"
        ]
        # Define keys to remove from each variant
        variant_keys_to_remove = ["temp_path", "dimensions"]

        for map_key, map_detail_original in original_processed_maps.items():
            # Create a new dictionary for the modified map entry
            new_map_entry = {}
            for key, value in map_detail_original.items():
                if key not in map_keys_to_remove:
                    new_map_entry[key] = value
            
            if "variants" in map_detail_original and isinstance(map_detail_original["variants"], dict):
                new_variants_dict = {}
                for variant_name, variant_data_original in map_detail_original["variants"].items():
                    new_variant_entry = {}
                    for key, value in variant_data_original.items():
                        if key not in variant_keys_to_remove:
                            new_variant_entry[key] = value
                    
                    # Add 'path_to_file'
                    # This path is expected to be set by OutputOrganizationStage in the context.
                    # It should be a Path object representing the path relative to the metadata directory,
                    # or an absolute Path that make_serializable can convert.
                    # Using 'final_output_path_for_metadata' as the key from context.
                    if 'final_output_path_for_metadata' in variant_data_original:
                        new_variant_entry['path_to_file'] = variant_data_original['final_output_path_for_metadata']
                    else:
                        # Log a warning if the expected path is not found
                        logger.warning(
                            f"Asset '{asset_name_for_log}': 'final_output_path_for_metadata' "
                            f"missing for variant '{variant_name}' in map '{map_key}'. "
                            f"Metadata will be incomplete for this variant's path."
                        )
                        new_variant_entry['path_to_file'] = "ERROR_PATH_NOT_FOUND" # Placeholder
                    new_variants_dict[variant_name] = new_variant_entry
                new_map_entry["variants"] = new_variants_dict
            
            restructured_processed_maps[map_key] = new_map_entry

        # Assign the restructured details. Note: 'processed_map_details' (singular 'map') is the key in asset_metadata.
        # context.asset_metadata['processed_map_details'] = restructured_processed_maps
        # context.asset_metadata['merged_map_details'] = getattr(context, 'merged_maps_details', {})

        # (Optional) Add a list of all temporary files
        # context.asset_metadata['temporary_files'] = getattr(context, 'temporary_files', []) # Assuming this is populated elsewhere

        # B. Determine Metadata Output Path
        # asset_name_for_log is defined at the top of the function if asset_metadata exists
            
        source_rule_identifier_for_path = "unknown_source"
        if hasattr(context, 'source_rule') and context.source_rule:
            if hasattr(context.source_rule, 'supplier_identifier') and context.source_rule.supplier_identifier:
                source_rule_identifier_for_path = context.source_rule.supplier_identifier
            elif hasattr(context.source_rule, 'input_path') and context.source_rule.input_path:
                source_rule_identifier_for_path = Path(context.source_rule.input_path).stem # Use stem of input path if no identifier
            else:
                source_rule_identifier_for_path = "unknown_source_details"
        
        # Use the configured metadata filename from config_obj
        metadata_filename_from_config = getattr(context.config_obj, 'metadata_filename', "metadata.json")
        # Ensure asset_name_for_log is safe for filenames
        safe_asset_name = sanitize_filename(asset_name_for_log) # asset_name_for_log is defined at the top
        final_metadata_filename = f"{safe_asset_name}_{metadata_filename_from_config}"

        # Output path pattern should come from config_obj, not asset_rule
        output_path_pattern_from_config = getattr(context.config_obj, 'output_directory_pattern', "[supplier]/[assetname]")
            
        sha_value = getattr(context, 'sha5_value', None) # Prefer sha5_value if explicitly set on context
        if sha_value is None: # Fallback to sha256_value if that was the intended attribute
            sha_value = getattr(context, 'sha256_value', None)

        token_data = {
            "assetname": asset_name_for_log,
            "supplier": context.effective_supplier if context.effective_supplier else source_rule_identifier_for_path,
            "sourcerulename": source_rule_identifier_for_path,
            "incrementingvalue": getattr(context, 'incrementing_value', None),
            "sha5": sha_value, # Assuming pattern uses [sha5] or similar for sha_value
            "maptype": "metadata", # Added maptype to token_data
            "filename": final_metadata_filename # Added filename to token_data
            # Add other tokens if your output_path_pattern_from_config expects them
        }
        # Clean None values, as generate_path_from_pattern might not handle them well for all tokens
        token_data_cleaned = {k: v for k, v in token_data.items() if v is not None}

        # Generate the relative directory path using the pattern and tokens
        relative_dir_path_str = generate_path_from_pattern(
            pattern_string=output_path_pattern_from_config, # This pattern should resolve to a directory
            token_data=token_data_cleaned
        )
        
        # Construct the full path by joining the base output path, the generated relative directory, and the final filename
        metadata_save_path = Path(context.output_base_path) / Path(relative_dir_path_str) / Path(final_metadata_filename)

        # C. Save Metadata File
        try:
            metadata_save_path.parent.mkdir(parents=True, exist_ok=True)

            def make_serializable(data: Any) -> Any:
                if isinstance(data, Path):
                    # metadata_save_path is available from the outer scope
                    metadata_dir = metadata_save_path.parent
                    try:
                        # Attempt to make the path relative if it's absolute and under the same root
                        if data.is_absolute():
                            # Check if the path can be made relative (e.g., same drive on Windows)
                            # This check might need to be more robust depending on os.path.relpath behavior
                            # For pathlib, relative_to will raise ValueError if not possible.
                            return str(data.relative_to(metadata_dir))
                        else:
                            # If it's already relative, assume it's correct or handle as needed
                            return str(data)
                    except ValueError:
                        # If paths are on different drives or cannot be made relative,
                        # log a warning and return the absolute path as a string.
                        # This can happen if an output path was explicitly set to an unrelated directory.
                        logger.warning(
                            f"Asset '{asset_name_for_log}': Could not make path {data} "
                            f"relative to {metadata_dir}. Storing as absolute."
                        )
                        return str(data)
                if isinstance(data, datetime.datetime): # Ensure datetime is serializable
                    return data.isoformat()
                if isinstance(data, dict):
                    return {k: make_serializable(v) for k, v in data.items()}
                if isinstance(data, list):
                    return [make_serializable(i) for i in data]
                return data

            # final_output_files is populated by OutputOrganizationStage. Explicitly remove it as per user request.
            context.asset_metadata.pop('final_output_files', None)
            serializable_metadata = make_serializable(context.asset_metadata)

            with open(metadata_save_path, 'w') as f:
                json.dump(serializable_metadata, f, indent=4)
            logger.info(f"Asset '{asset_name_for_log}': Metadata saved to {metadata_save_path}") # Use asset_name_for_log
            context.asset_metadata['metadata_file_path'] = str(metadata_save_path)
        except Exception as e:
            logger.error(f"Asset '{asset_name_for_log}': Failed to save metadata to {metadata_save_path}. Error: {e}") # Use asset_name_for_log
            context.asset_metadata['status'] = "Failed (Metadata Save Error)"
            context.status_flags['metadata_save_error'] = True

        return context