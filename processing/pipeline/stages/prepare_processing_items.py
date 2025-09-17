import logging
from typing import List, Union, Optional, Tuple, Dict # Added Dict
from pathlib import Path # Added Path

from .base_stage import ProcessingStage
from ..asset_context import AssetProcessingContext, MergeTaskDefinition
from rule_structure import FileRule, ProcessingItem # Added ProcessingItem
from processing.utils import image_processing_utils as ipu # Added ipu

log = logging.getLogger(__name__)

class PrepareProcessingItemsStage(ProcessingStage):
    """
    Identifies and prepares a unified list of ProcessingItem and MergeTaskDefinition objects
    to be processed in subsequent stages. Performs initial validation and explodes
    FileRules into specific ProcessingItems for each required output variant.
    """

    def _get_target_resolutions(self, source_w: int, source_h: int, config_resolutions: dict, file_rule: FileRule) -> Dict[str, int]:
        """
        Determines the target output resolutions for a given source image.
        Placeholder logic: Uses all config resolutions smaller than or equal to source, plus PREVIEW if smaller.
        Needs to be refined to consider FileRule.resolution_override and actual project requirements.
        """
        # For now, very basic logic:
        # If FileRule has a resolution_override (e.g., (1024,1024)), that might be the *only* target.
        # This needs to be clarified. Assuming override means *only* that size.
        if file_rule.resolution_override and isinstance(file_rule.resolution_override, tuple) and len(file_rule.resolution_override) == 2:
            # How to get a "key" for an arbitrary override? For now, skip if overridden.
            # This part of the design (how overrides interact with standard resolutions) is unclear.
            # Let's assume for now that if resolution_override is set, we don't generate standard named resolutions.
            # This is likely incorrect for a full implementation.
            log.warning(f"FileRule '{file_rule.file_path}' has resolution_override. Standard resolution key generation skipped (needs design refinement).")
            return {}


        target_res = {}
        max_source_dim = max(source_w, source_h)

        for key, res_val in config_resolutions.items():
            if key == "PREVIEW": # Always consider PREVIEW if its value is smaller
                if res_val < max_source_dim : # Or just always include PREVIEW? For now, if smaller.
                     target_res[key] = res_val
            elif res_val <= max_source_dim:
                target_res[key] = res_val
        
        # Ensure PREVIEW is included if it's defined and smaller than the smallest other target, or if no other targets.
        # This logic is still a bit naive.
        if "PREVIEW" in config_resolutions and config_resolutions["PREVIEW"] < max_source_dim:
            if not target_res or config_resolutions["PREVIEW"] < min(v for k,v in target_res.items() if k != "PREVIEW" and isinstance(v,int)):
                 target_res["PREVIEW"] = config_resolutions["PREVIEW"]
        elif "PREVIEW" in config_resolutions and not target_res : # if only preview is applicable
             if config_resolutions["PREVIEW"] <= max_source_dim:
                  target_res["PREVIEW"] = config_resolutions["PREVIEW"]


        if not target_res and max_source_dim > 0 : # If no standard res is smaller, but image exists
             log.debug(f"No standard resolutions from config are <= source dimension {max_source_dim}. Only LOWRES (if applicable) or PREVIEW (if smaller) might be generated.")
        
        log.debug(f"Determined target resolutions for source {source_w}x{source_h}: {target_res}")
        return target_res


    def execute(self, context: AssetProcessingContext) -> AssetProcessingContext:
        """
        Populates context.processing_items with ProcessingItem and MergeTaskDefinition objects.
        """
        asset_name_for_log = context.asset_rule.asset_name if context.asset_rule else "Unknown Asset"
        log.info(f"Asset '{asset_name_for_log}': Preparing processing items...")

        if context.status_flags.get('skip_asset', False):
            log.info(f"Asset '{asset_name_for_log}': Skipping item preparation due to skip_asset flag.")
            context.processing_items = []
            return context

        # Output list will now be List[Union[ProcessingItem, MergeTaskDefinition]]
        items_to_process: List[Union[ProcessingItem, MergeTaskDefinition]] = []
        preparation_failed = False
        config = context.config_obj

        # --- Process FileRules into ProcessingItems ---
        if context.files_to_process:
            source_path_valid = True
            if not context.source_rule or not context.source_rule.input_path:
                log.error(f"Asset '{asset_name_for_log}': SourceRule or SourceRule.input_path is not set.")
                source_path_valid = False
                preparation_failed = True
                context.status_flags['prepare_items_failed_reason'] = "SourceRule.input_path missing"
            elif not context.workspace_path or not context.workspace_path.is_dir():
                 log.error(f"Asset '{asset_name_for_log}': Workspace path '{context.workspace_path}' is invalid.")
                 source_path_valid = False
                 preparation_failed = True
                 context.status_flags['prepare_items_failed_reason'] = "Workspace path invalid"

            if source_path_valid:
                for file_rule in context.files_to_process:
                    log_prefix_fr = f"Asset '{asset_name_for_log}', FileRule '{file_rule.file_path}'"
                    if not file_rule.file_path:
                         log.warning(f"{log_prefix_fr}: Skipping FileRule with empty file_path.")
                         continue
                    
                    item_type = file_rule.item_type_override or file_rule.item_type
                    if not item_type or item_type == "EXTRA" or not item_type.startswith("MAP_"):
                        log.debug(f"{log_prefix_fr}: Item type is '{item_type}'. Not creating map ProcessingItems.")
                        # Optionally, create a different kind of ProcessingItem for EXTRAs if they need pipeline processing
                        continue

                    source_image_path = context.workspace_path / file_rule.file_path
                    if not source_image_path.is_file():
                        log.error(f"{log_prefix_fr}: Source image file not found at '{source_image_path}'. Skipping this FileRule.")
                        preparation_failed = True # Individual file error can contribute to overall stage failure
                        context.status_flags.setdefault('prepare_items_file_errors', []).append(str(source_image_path))
                        continue
                    
                    # Load image data to get dimensions and for LOWRES variant
                    # This data will be passed to subsequent stages via ProcessingItem.
                    # Consider caching this load if RegularMapProcessorStage also loads.
                    # For now, load here as dimensions are needed for LOWRES decision.
                    log.debug(f"{log_prefix_fr}: Loading image from '{source_image_path}' to determine dimensions and prepare items.")
                    source_image_data = ipu.load_image(str(source_image_path))
                    if source_image_data is None:
                        log.error(f"{log_prefix_fr}: Failed to load image from '{source_image_path}'. Skipping this FileRule.")
                        preparation_failed = True
                        context.status_flags.setdefault('prepare_items_file_errors', []).append(f"Failed to load {source_image_path}")
                        continue
                    
                    orig_h, orig_w = source_image_data.shape[:2]
                    original_dimensions_wh = (orig_w, orig_h)
                    source_bit_depth = ipu.get_image_bit_depth(str(source_image_path)) # Get bit depth from file
                    source_channels = ipu.get_image_channels(source_image_data)


                    # Determine standard resolutions to generate
                    # This logic needs to be robust and consider file_rule.resolution_override, etc.
                    # Using a placeholder _get_target_resolutions for now.
                    target_resolutions = self._get_target_resolutions(orig_w, orig_h, config.image_resolutions, file_rule)

                    for res_key, _res_val in target_resolutions.items():
                        pi = ProcessingItem(
                            source_file_info_ref=str(source_image_path), # Using full path as ref
                            map_type_identifier=item_type,
                            resolution_key=res_key,
                            image_data=source_image_data.copy(), # Give each PI its own copy
                            original_dimensions=original_dimensions_wh,
                            current_dimensions=original_dimensions_wh,
                            bit_depth=source_bit_depth,
                            channels=source_channels,
                            status="Pending"
                        )
                        items_to_process.append(pi)
                        log.debug(f"{log_prefix_fr}: Created standard ProcessingItem: {pi.map_type_identifier}_{pi.resolution_key}")

                    # Create LOWRES variant if applicable
                    if config.enable_low_resolution_fallback and max(orig_w, orig_h) < config.low_resolution_threshold:
                        # Check if a LOWRES item for this source_file_info_ref already exists (e.g. if target_resolutions was empty)
                        # This check is important if _get_target_resolutions might return empty for small images.
                        # A more robust way is to ensure LOWRES is distinct from standard resolutions.
                        
                        # Avoid duplicate LOWRES if _get_target_resolutions somehow already made one (unlikely with current placeholder)
                        is_lowres_already_added = any(p.resolution_key == "LOWRES" and p.source_file_info_ref == str(source_image_path) for p in items_to_process if isinstance(p, ProcessingItem))

                        if not is_lowres_already_added:
                            pi_lowres = ProcessingItem(
                                source_file_info_ref=str(source_image_path),
                                map_type_identifier=item_type,
                                resolution_key="LOWRES",
                                image_data=source_image_data.copy(), # Fresh copy for LOWRES
                                original_dimensions=original_dimensions_wh,
                                current_dimensions=original_dimensions_wh,
                                bit_depth=source_bit_depth,
                                channels=source_channels,
                                status="Pending"
                            )
                            items_to_process.append(pi_lowres)
                            log.info(f"{log_prefix_fr}: Created LOWRES ProcessingItem because {orig_w}x{orig_h} < {config.low_resolution_threshold}px threshold.")
                        else:
                            log.debug(f"{log_prefix_fr}: LOWRES item for this source already added by target resolution logic. Skipping duplicate LOWRES creation.")
                    elif config.enable_low_resolution_fallback:
                         log.debug(f"{log_prefix_fr}: Image {orig_w}x{orig_h} not below LOWRES threshold {config.low_resolution_threshold}px.")


            else: # Source path not valid
                 log.warning(f"Asset '{asset_name_for_log}': Skipping creation of ProcessingItems from FileRules due to invalid source/workspace path.")

        # --- Add MergeTaskDefinitions --- (This part remains largely the same)
        merged_tasks_list = getattr(config, 'map_merge_rules', None)
        if merged_tasks_list and isinstance(merged_tasks_list, list):
            log.debug(f"Asset '{asset_name_for_log}': Found {len(merged_tasks_list)} merge tasks in global config.")
            for task_idx, task_data in enumerate(merged_tasks_list):
                if isinstance(task_data, dict):
                    task_key = f"merged_task_{task_idx}"
                    if not task_data.get('output_map_type') or not isinstance(task_data.get('inputs'), dict):
                        log.warning(f"Asset '{asset_name_for_log}', Task Index {task_idx}: Skipping merge task due to missing 'output_map_type' or valid 'inputs'. Task data: {task_data}")
                        continue
                    merge_def = MergeTaskDefinition(task_data=task_data, task_key=task_key)
                    items_to_process.append(merge_def)
                    log.info(f"Asset '{asset_name_for_log}': Added MergeTaskDefinition: Key='{merge_def.task_key}', OutputType='{merge_def.task_data.get('output_map_type', 'N/A')}'")
                else:
                    log.warning(f"Asset '{asset_name_for_log}': Item at index {task_idx} in config.map_merge_rules is not a dict. Skipping. Item: {task_data}")
        # ... (rest of merge task handling) ...

        if not items_to_process and not preparation_failed: # Check preparation_failed too
             log.info(f"Asset '{asset_name_for_log}': No valid items (ProcessingItem or MergeTaskDefinition) found to process.")

        context.processing_items = items_to_process
        context.intermediate_results = {} # Initialize intermediate results storage

        if preparation_failed:
             # Set a flag indicating failure during preparation, even if some items might have been added before failure
             context.status_flags['prepare_items_failed'] = True
             log.error(f"Asset '{asset_name_for_log}': Item preparation failed. Reason: {context.status_flags.get('prepare_items_failed_reason', 'Unknown')}")
             # Optionally, clear items if failure means nothing should proceed
             # context.processing_items = []

        log.info(f"Asset '{asset_name_for_log}': Finished preparing items. Found {len(context.processing_items)} valid items.")
        return context