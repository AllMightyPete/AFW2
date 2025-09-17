# --- Imports ---
import logging
import shutil
import tempfile
from pathlib import Path
from typing import List, Dict, Optional, Any, Union # Added Any, Union

import numpy as np # Added numpy

from configuration import Configuration
from rule_structure import SourceRule, AssetRule, FileRule, ProcessingItem # Added ProcessingItem

# Import new context classes and stages
from .asset_context import (
    AssetProcessingContext,
    MergeTaskDefinition,
    ProcessedRegularMapData,
    ProcessedMergedMapData,
    InitialScalingInput,
    InitialScalingOutput,
    SaveVariantsInput,
    SaveVariantsOutput,
)
from .stages.base_stage import ProcessingStage
# Import the new stages we created
from .stages.prepare_processing_items import PrepareProcessingItemsStage
from .stages.regular_map_processor import RegularMapProcessorStage
from .stages.merged_task_processor import MergedTaskProcessorStage
from .stages.initial_scaling import InitialScalingStage
from .stages.save_variants import SaveVariantsStage

log = logging.getLogger(__name__)

# --- PipelineOrchestrator Class ---

class PipelineOrchestrator:
    """
    Orchestrates the processing of assets based on source rules and a series of processing stages.
    Manages the overall flow, including the core item processing sequence.
    """

    def __init__(self, config_obj: Configuration,
                 pre_item_stages: List[ProcessingStage],
                 post_item_stages: List[ProcessingStage]):
        """
        Initializes the PipelineOrchestrator.

        Args:
            config_obj: The main configuration object.
            pre_item_stages: Stages to run before the core item processing loop.
            post_item_stages: Stages to run after the core item processing loop.
        """
        self.config_obj: Configuration = config_obj
        self.pre_item_stages: List[ProcessingStage] = pre_item_stages
        self.post_item_stages: List[ProcessingStage] = post_item_stages
        # Instantiate the core item processing stages internally
        self._prepare_stage = PrepareProcessingItemsStage()
        self._regular_processor_stage = RegularMapProcessorStage()
        self._merged_processor_stage = MergedTaskProcessorStage()
        self._scaling_stage = InitialScalingStage()
        self._save_stage = SaveVariantsStage()

    def _execute_specific_stages(
        self, context: AssetProcessingContext,
        stages_to_run: List[ProcessingStage],
        stage_group_name: str,
        stop_on_skip: bool = True
    ) -> AssetProcessingContext:
        """Executes a specific list of stages."""
        asset_name = context.asset_rule.asset_name if context.asset_rule else "Unknown"
        log.debug(f"Asset '{asset_name}': Executing {stage_group_name} stages...")
        for stage in stages_to_run:
            stage_name = stage.__class__.__name__
            log.debug(f"Asset '{asset_name}': Executing {stage_group_name} stage: {stage_name}")
            try:
                # Check if stage expects context directly or specific input
                # For now, assume outer stages take context directly
                # This might need refinement if outer stages also adopt Input/Output pattern
                context = stage.execute(context)
            except Exception as e:
                log.error(f"Asset '{asset_name}': Error during outer stage '{stage_name}': {e}", exc_info=True)
                context.status_flags["asset_failed"] = True
                context.status_flags["asset_failed_stage"] = stage_name
                context.status_flags["asset_failed_reason"] = str(e)
                # Update overall metadata immediately on outer stage failure
                context.asset_metadata["status"] = f"Failed: Error in stage {stage_name}"
                context.asset_metadata["error_message"] = str(e)
                break # Stop processing outer stages for this asset on error

            if stop_on_skip and context.status_flags.get("skip_asset"):
                log.info(f"Asset '{asset_name}': Skipped by outer stage '{stage_name}'. Reason: {context.status_flags.get('skip_reason', 'N/A')}")
                break # Skip remaining outer stages for this asset
        return context

    def process_source_rule(
        self,
        source_rule: SourceRule,
        workspace_path: Path,
        output_base_path: Path,
        overwrite: bool,
        incrementing_value: Optional[str],
        sha5_value: Optional[str] # Keep param name consistent for now
    ) -> Dict[str, List[str]]:
        """
        Processes a single source rule, applying pre-processing stages,
        the core item processing loop (Prepare, Process, Scale, Save),
        and post-processing stages.
        """
        overall_status: Dict[str, List[str]] = {
            "processed": [],
            "skipped": [],
            "failed": [],
        }
        engine_temp_dir_path: Optional[Path] = None

        try:
            # --- Setup Temporary Directory ---
            temp_dir_path_str = tempfile.mkdtemp(prefix=self.config_obj.temp_dir_prefix)
            engine_temp_dir_path = Path(temp_dir_path_str)
            log.debug(f"PipelineOrchestrator created temporary directory: {engine_temp_dir_path}")

            # --- Process Each Asset Rule ---
            for asset_rule in source_rule.assets:
                asset_name = asset_rule.asset_name
                log.info(f"Orchestrator: Processing asset '{asset_name}'")

                # --- Initialize Asset Context ---
                context = AssetProcessingContext(
                    source_rule=source_rule,
                    asset_rule=asset_rule,
                    workspace_path=workspace_path,
                    engine_temp_dir=engine_temp_dir_path,
                    output_base_path=output_base_path,
                    effective_supplier=None,
                    asset_metadata={},
                    processed_maps_details={}, # Final results per item
                    merged_maps_details={}, # Keep for potential backward compat or other uses?
                    files_to_process=[], # Populated by FileRuleFilterStage (assumed in outer_stages)
                    loaded_data_cache={},
                    config_obj=self.config_obj,
                    status_flags={"skip_asset": False, "asset_failed": False},
                    incrementing_value=incrementing_value,
                    sha5_value=sha5_value,
                    processing_items=[], # Initialize new fields
                    intermediate_results={}
                )

                # --- Execute Pre-Item-Processing Outer Stages ---
                # (e.g., MetadataInit, SupplierDet, FileRuleFilter, GlossToRough, NormalInvert)
                # Identify which outer stages run before the item loop
                # This requires knowing the intended order. Assume all run before for now.
                context = self._execute_specific_stages(context, self.pre_item_stages, "pre-item", stop_on_skip=True)

                # Check if asset should be skipped or failed after pre-processing
                if context.status_flags.get("asset_failed"):
                    log.error(f"Asset '{asset_name}': Failed during pre-processing stage '{context.status_flags.get('asset_failed_stage', 'Unknown')}'. Skipping item processing.")
                    overall_status["failed"].append(f"{asset_name} (Failed in {context.status_flags.get('asset_failed_stage', 'Pre-Processing')})")
                    continue # Move to the next asset rule

                if context.status_flags.get("skip_asset"):
                    log.info(f"Asset '{asset_name}': Skipped during pre-processing. Skipping item processing.")
                    overall_status["skipped"].append(asset_name)
                    continue # Move to the next asset rule

                # --- Prepare Processing Items ---
                log.debug(f"Asset '{asset_name}': Preparing processing items...")
                try:
                    log.info(f"ORCHESTRATOR_TRACE: Asset '{asset_name}': Attempting to call _prepare_stage.execute(). Current context.status_flags: {context.status_flags}")
                    # Prepare stage modifies context directly
                    context = self._prepare_stage.execute(context)
                    log.info(f"ORCHESTRATOR_TRACE: Asset '{asset_name}': Successfully RETURNED from _prepare_stage.execute(). context.processing_items count: {len(context.processing_items) if context.processing_items is not None else 'None'}. context.status_flags: {context.status_flags}")
                except Exception as e:
                     log.error(f"ORCHESTRATOR_TRACE: Asset '{asset_name}': EXCEPTION during _prepare_stage.execute(): {e}", exc_info=True)
                     context.status_flags["asset_failed"] = True
                     context.status_flags["asset_failed_stage"] = "PrepareProcessingItemsStage"
                     context.status_flags["asset_failed_reason"] = str(e)
                     overall_status["failed"].append(f"{asset_name} (Failed in Prepare Items)")
                     continue # Move to next asset

                if context.status_flags.get('prepare_items_failed'):
                     log.error(f"Asset '{asset_name}': Failed during item preparation. Reason: {context.status_flags.get('prepare_items_failed_reason', 'Unknown')}. Skipping item processing loop.")
                     overall_status["failed"].append(f"{asset_name} (Failed Prepare Items: {context.status_flags.get('prepare_items_failed_reason', 'Unknown')})")
                     continue # Move to next asset

                if not context.processing_items:
                    log.info(f"Asset '{asset_name}': No items to process after preparation stage.")
                    # Status will be determined at the end

                # --- Core Item Processing Loop ---
                log.info("ORCHESTRATOR: Starting processing items loop for asset '%s'", asset_name) # Corrected indentation and message
                log.info(f"Asset '{asset_name}': Starting core item processing loop for {len(context.processing_items)} items...")
                asset_had_item_errors = False
                for item_index, item in enumerate(context.processing_items):
                    item_key: Any = None # Key for storing results (FileRule object or task_key string)
                    item_log_prefix = f"Asset '{asset_name}', Item {item_index + 1}/{len(context.processing_items)}"
                    processed_data: Optional[Union[ProcessedRegularMapData, ProcessedMergedMapData]] = None
                    scaled_data_output: Optional[InitialScalingOutput] = None # Store output object
                    saved_data: Optional[SaveVariantsOutput] = None
                    item_status = "Failed" # Default item status
                    current_image_data: Optional[np.ndarray] = None # Track current image data ref

                    try:
                        # The 'item' is now expected to be a ProcessingItem or MergeTaskDefinition
                        
                        if isinstance(item, ProcessingItem):
                            item_key = f"{item.source_file_info_ref}_{item.map_type_identifier}_{item.resolution_key}"
                            item_log_prefix = f"Asset '{asset_name}', ProcItem '{item_key}'"
                            log.info(f"{item_log_prefix}: Starting processing.")

                            # Data for ProcessingItem is already loaded by PrepareProcessingItemsStage
                            current_image_data = item.image_data
                            current_dimensions = item.current_dimensions
                            item_resolution_key = item.resolution_key
                            
                            # Transformations (like gloss to rough, normal invert) are assumed to be applied
                            # by RegularMapProcessorStage if it's still used, or directly in PrepareProcessingItemsStage
                            # before creating the ProcessingItem, or a new dedicated transformation stage.
                            # For now, assume item.image_data is ready for scaling/saving.
                            
                            # Store initial ProcessingItem data as "processed_data" for consistency if RegularMapProcessor is bypassed
                            # This is a simplification; a dedicated transformation stage would be cleaner.
                            # For now, we assume transformations happened before or within PrepareProcessingItemsStage.
                            # The 'processed_data' variable here is more of a placeholder for what would feed into scaling.
                            
                            # Create a simple ProcessedRegularMapData-like structure for logging/details if needed,
                            # or adapt the final_details population later.
                            # For now, we'll directly use 'item' fields.

                            # 2. Scale (Optional)
                            scaling_mode = getattr(context.config_obj, "INITIAL_SCALING_MODE", "NONE")
                            # Pass the item's resolution_key to InitialScalingInput
                            scale_input = InitialScalingInput(
                                image_data=current_image_data,
                                original_dimensions=current_dimensions,
                                initial_scaling_mode=scaling_mode,
                                resolution_key=item_resolution_key # Pass the key
                            )
                            # Add _source_file_path for logging within InitialScalingStage if available
                            setattr(scale_input, '_source_file_path', item.source_file_info_ref)

                            log.debug(f"{item_log_prefix}: Calling InitialScalingStage. Input res_key: {scale_input.resolution_key}")
                            scaled_data_output = self._scaling_stage.execute(scale_input)
                            current_image_data = scaled_data_output.scaled_image_data
                            current_dimensions = scaled_data_output.final_dimensions # Dimensions after scaling
                            # The resolution_key from item is passed through by InitialScalingOutput
                            output_resolution_key = scaled_data_output.resolution_key
                            log.debug(f"{item_log_prefix}: InitialScalingStage output. Scaled: {scaled_data_output.scaling_applied}, New Dims: {current_dimensions}, Output ResKey: {output_resolution_key}")
                            context.intermediate_results[item_key] = scaled_data_output


                            # 3. Save Variants
                            if current_image_data is None or current_image_data.size == 0:
                                log.warning(f"{item_log_prefix}: Skipping save stage because image data is empty.")
                                context.processed_maps_details[item_key] = {"status": "Skipped", "notes": "No image data to save", "stage": "SaveVariantsStage"}
                                continue

                            log.debug(f"{item_log_prefix}: Preparing to save variant with resolution key '{output_resolution_key}'...")
                            
                            output_filename_tokens = {
                                'asset_name': asset_name,
                                'output_base_directory': context.engine_temp_dir,
                                'supplier': context.effective_supplier or 'UnknownSupplier',
                                'resolution': output_resolution_key # Use the key from the item/scaling stage
                            }
                            
                            # Determine image_resolutions argument for save_image_variants
                            save_specific_resolutions = {}
                            if output_resolution_key == "LOWRES":
                                # For LOWRES, the "resolution value" is its actual dimension.
                                # image_saving_utils needs a dict like {"LOWRES": 64} if current_dim is 64x64
                                # Assuming current_dimensions[0] is width.
                                save_specific_resolutions = {"LOWRES": current_dimensions[0] if current_dimensions else 0}
                                log.debug(f"{item_log_prefix}: Preparing to save LOWRES variant. Dimensions: {current_dimensions}. Save resolutions arg: {save_specific_resolutions}")
                            elif output_resolution_key in context.config_obj.image_resolutions:
                                save_specific_resolutions = {output_resolution_key: context.config_obj.image_resolutions[output_resolution_key]}
                            else:
                                log.warning(f"{item_log_prefix}: Resolution key '{output_resolution_key}' not found in config.image_resolutions and not LOWRES. Saving might fail or use full res.")
                                # Fallback: pass all configured resolutions, image_saving_utils will try to match by size.
                                # This might not be ideal if the key is truly unknown.
                                # Or, more strictly, fail here if key is unknown and not LOWRES.
                                # For now, let image_saving_utils handle it by passing all.
                                save_specific_resolutions = context.config_obj.image_resolutions


                            save_input = SaveVariantsInput(
                                image_data=current_image_data,
                                internal_map_type=item.map_type_identifier,
                                source_bit_depth_info=[item.bit_depth] if item.bit_depth is not None else [8], # Default to 8 if not set
                                output_filename_pattern_tokens=output_filename_tokens,
                                image_resolutions=save_specific_resolutions, # Pass the specific resolution(s)
                                file_type_defs=getattr(context.config_obj, "FILE_TYPE_DEFINITIONS", {}),
                                output_format_8bit=context.config_obj.get_8bit_output_format(),
                                output_format_16bit_primary=context.config_obj.get_16bit_output_formats()[0],
                                output_format_16bit_fallback=context.config_obj.get_16bit_output_formats()[1],
                                png_compression_level=context.config_obj.png_compression_level,
                                jpg_quality=context.config_obj.jpg_quality,
                                output_filename_pattern=context.config_obj.output_filename_pattern,
                                resolution_threshold_for_jpg=getattr(context.config_obj, "resolution_threshold_for_jpg", None)
                            )
                            saved_data = self._save_stage.execute(save_input)
                            
                            if saved_data and saved_data.status.startswith("Processed"):
                                item_status = saved_data.status
                                log.info(f"{item_log_prefix}: Item successfully processed and saved. Status: {item_status}")
                                context.processed_maps_details[item_key] = {
                                    "status": item_status,
                                    "saved_files_info": saved_data.saved_files_details,
                                    "internal_map_type": item.map_type_identifier,
                                    "resolution_key": output_resolution_key,
                                    "original_dimensions": item.original_dimensions,
                                    "final_dimensions": current_dimensions, # Dimensions after scaling
                                    "source_file": item.source_file_info_ref,
                                }
                            else:
                                error_msg = saved_data.error_message if saved_data else "Save stage returned None"
                                log.error(f"{item_log_prefix}: Failed during save stage. Error: {error_msg}")
                                context.processed_maps_details[item_key] = {"status": "Failed", "notes": f"Save Error: {error_msg}", "stage": "SaveVariantsStage"}
                                asset_had_item_errors = True
                                item_status = "Failed"

                        elif isinstance(item, MergeTaskDefinition):
                            # --- This part needs similar refactoring for resolution_key if merged outputs can be LOWRES ---
                            # --- For now, assume merged tasks always produce standard resolutions ---
                            item_key = item.task_key
                            item_log_prefix = f"Asset '{asset_name}', MergeTask '{item_key}'"
                            log.info(f"{item_log_prefix}: Processing MergeTask.")

                            # 1. Process Merge Task
                            processed_data = self._merged_processor_stage.execute(context, item)
                            if not processed_data or processed_data.status != "Processed":
                                error_msg = processed_data.error_message if processed_data else "Merge processor returned None"
                                log.error(f"{item_log_prefix}: Failed during merge processing. Error: {error_msg}")
                                context.processed_maps_details[item_key] = {"status": "Failed", "notes": f"Merge Error: {error_msg}", "stage": "MergedTaskProcessorStage"}
                                asset_had_item_errors = True
                                continue
                            
                            context.intermediate_results[item_key] = processed_data
                            current_image_data = processed_data.merged_image_data
                            current_dimensions = processed_data.final_dimensions

                            # 2. Scale Merged Output (Optional)
                            # Merged tasks typically don't have a single "resolution_key" like LOWRES from source.
                            # They produce an image that then gets downscaled to 1K, PREVIEW etc.
                            # So, resolution_key for InitialScalingInput here would be None or a default.
                            scaling_mode = getattr(context.config_obj, "INITIAL_SCALING_MODE", "NONE")
                            scale_input = InitialScalingInput(
                                image_data=current_image_data,
                                original_dimensions=current_dimensions,
                                initial_scaling_mode=scaling_mode,
                                resolution_key=None # Merged outputs are not "LOWRES" themselves before this scaling
                            )
                            setattr(scale_input, '_source_file_path', f"MergeTask_{item_key}") # For logging
                            
                            log.debug(f"{item_log_prefix}: Calling InitialScalingStage for merged data.")
                            scaled_data_output = self._scaling_stage.execute(scale_input)
                            current_image_data = scaled_data_output.scaled_image_data
                            current_dimensions = scaled_data_output.final_dimensions
                            # Merged items don't have a specific output_resolution_key from source,
                            # they will be saved to all applicable resolutions from config.
                            # So scaled_data_output.resolution_key will be None here.
                            context.intermediate_results[item_key] = scaled_data_output

                            # 3. Save Merged Variants
                            if current_image_data is None or current_image_data.size == 0:
                                log.warning(f"{item_log_prefix}: Skipping save for merged task, image data is empty.")
                                context.processed_maps_details[item_key] = {"status": "Skipped", "notes": "No merged image data to save", "stage": "SaveVariantsStage"}
                                continue

                            output_filename_tokens = {
                                'asset_name': asset_name,
                                'output_base_directory': context.engine_temp_dir,
                                'supplier': context.effective_supplier or 'UnknownSupplier',
                                # 'resolution' token will be filled by image_saving_utils for each variant
                            }
                            
                            # For merged tasks, we usually want to generate all standard resolutions.
                            # The `resolution_key` from the item itself is not applicable here for the `resolution` token.
                            # The `image_saving_utils.save_image_variants` will iterate through `context.config_obj.image_resolutions`.
                            save_input = SaveVariantsInput(
                                image_data=current_image_data,
                                internal_map_type=processed_data.output_map_type,
                                source_bit_depth_info=processed_data.source_bit_depths,
                                output_filename_pattern_tokens=output_filename_tokens,
                                image_resolutions=context.config_obj.image_resolutions, # Pass all configured resolutions
                                file_type_defs=getattr(context.config_obj, "FILE_TYPE_DEFINITIONS", {}),
                                output_format_8bit=context.config_obj.get_8bit_output_format(),
                                output_format_16bit_primary=context.config_obj.get_16bit_output_formats()[0],
                                output_format_16bit_fallback=context.config_obj.get_16bit_output_formats()[1],
                                png_compression_level=context.config_obj.png_compression_level,
                                jpg_quality=context.config_obj.jpg_quality,
                                output_filename_pattern=context.config_obj.output_filename_pattern,
                                resolution_threshold_for_jpg=getattr(context.config_obj, "resolution_threshold_for_jpg", None)
                            )
                            saved_data = self._save_stage.execute(save_input)

                            if saved_data and saved_data.status.startswith("Processed"):
                                item_status = saved_data.status
                                log.info(f"{item_log_prefix}: Merged task successfully processed and saved. Status: {item_status}")
                                context.processed_maps_details[item_key] = {
                                    "status": item_status,
                                    "saved_files_info": saved_data.saved_files_details,
                                    "internal_map_type": processed_data.output_map_type,
                                    "final_dimensions": current_dimensions,
                                }
                            else:
                                error_msg = saved_data.error_message if saved_data else "Save stage for merged task returned None"
                                log.error(f"{item_log_prefix}: Failed during save stage for merged task. Error: {error_msg}")
                                context.processed_maps_details[item_key] = {"status": "Failed", "notes": f"Save Error (Merged): {error_msg}", "stage": "SaveVariantsStage"}
                                asset_had_item_errors = True
                                item_status = "Failed"
                        else:
                            log.warning(f"{item_log_prefix}: Unknown item type in loop: {type(item)}. Skipping.")
                            # Ensure some key exists to prevent KeyError if item_key was not set
                            unknown_item_key = f"unknown_item_at_index_{item_index}"
                            context.processed_maps_details[unknown_item_key] = {"status": "Skipped", "notes": f"Unknown item type {type(item)}"}
                            asset_had_item_errors = True
                            continue

                    except Exception as e:
                        log.exception(f"Asset '{asset_name}', Item Loop Index {item_index}: Unhandled exception: {e}")
                        # Ensure details are recorded even on unhandled exception
                        if item_key is not None:
                             context.processed_maps_details[item_key] = {"status": "Failed", "notes": f"Unhandled Loop Error: {e}", "stage": "OrchestratorLoop"}
                        else:
                             log.error(f"Asset '{asset_name}': Unhandled exception in item loop before item key was set.")
                        asset_had_item_errors = True
                        item_status = "Failed"
                        # Optionally break loop or continue? Continue for now to process other items.

                log.info("ORCHESTRATOR: Finished processing items loop for asset '%s'", asset_name)
                log.info(f"Asset '{asset_name}': Finished core item processing loop.")

                # --- Execute Post-Item-Processing Outer Stages ---
                # (e.g., OutputOrganization, MetadataFinalizationSave)
                # Identify which outer stages run after the item loop
                # This needs better handling based on stage purpose. Assume none run after for now.
                if not context.status_flags.get("asset_failed"):
                    log.info("ORCHESTRATOR: Executing post-item-processing outer stages for asset '%s'", asset_name)
                    context = self._execute_specific_stages(context, self.post_item_stages, "post-item", stop_on_skip=False)

                # --- Final Asset Status Determination ---
                final_asset_status = "Unknown"
                fail_reason = ""
                if context.status_flags.get("asset_failed"):
                    final_asset_status = "Failed"
                    fail_reason = f"(Failed in {context.status_flags.get('asset_failed_stage', 'Unknown Stage')}: {context.status_flags.get('asset_failed_reason', 'Unknown Reason')})"
                elif context.status_flags.get("skip_asset"):
                     final_asset_status = "Skipped"
                     fail_reason = f"(Skipped: {context.status_flags.get('skip_reason', 'Unknown Reason')})"
                elif asset_had_item_errors:
                     final_asset_status = "Failed"
                     fail_reason = "(One or more items failed)"
                elif not context.processing_items:
                     # No items prepared, no errors -> consider skipped or processed based on definition?
                     final_asset_status = "Skipped" # Or "Processed (No Items)"
                     fail_reason = "(No items to process)"
                elif not context.processed_maps_details and context.processing_items:
                     # Items were prepared, but none resulted in processed_maps_details entry
                     final_asset_status = "Skipped" # Or Failed?
                     fail_reason = "(All processing items skipped or failed internally)"
                elif context.processed_maps_details:
                    # Check if all items in processed_maps_details are actually processed successfully
                    all_processed_ok = all(
                        str(details.get("status", "")).startswith("Processed")
                        for details in context.processed_maps_details.values()
                    )
                    some_processed_ok = any(
                         str(details.get("status", "")).startswith("Processed")
                        for details in context.processed_maps_details.values()
                    )

                    if all_processed_ok:
                        final_asset_status = "Processed"
                    elif some_processed_ok:
                         final_asset_status = "Partial" # Introduce a partial status? Or just Failed?
                         fail_reason = "(Some items failed)"
                         final_asset_status = "Failed" # Treat partial as Failed for overall status
                    else: # No items processed successfully
                        final_asset_status = "Failed"
                        fail_reason = "(All items failed)"
                else:
                     # Should not happen if processing_items existed
                     final_asset_status = "Failed"
                     fail_reason = "(Unknown state after item processing)"


                # Update overall status list
                if final_asset_status == "Processed":
                    overall_status["processed"].append(asset_name)
                elif final_asset_status == "Skipped":
                    overall_status["skipped"].append(f"{asset_name} {fail_reason}")
                else: # Failed or Unknown
                    overall_status["failed"].append(f"{asset_name} {fail_reason}")

                log.info(f"Asset '{asset_name}' final status: {final_asset_status} {fail_reason}")
                # Clean up intermediate results for the asset to save memory
                context.intermediate_results = {}


        except Exception as e:
            log.error(f"PipelineOrchestrator.process_source_rule failed critically: {e}", exc_info=True)
            # Mark all assets from this source rule that weren't finished as failed
            processed_or_skipped_or_failed = set(overall_status["processed"]) | \
                                             set(name.split(" ")[0] for name in overall_status["skipped"]) | \
                                             set(name.split(" ")[0] for name in overall_status["failed"])
            for asset_rule in source_rule.assets:
                if asset_rule.asset_name not in processed_or_skipped_or_failed:
                    overall_status["failed"].append(f"{asset_rule.asset_name} (Orchestrator Error: {e})")
        finally:
            # --- Cleanup Temporary Directory ---
            if engine_temp_dir_path and engine_temp_dir_path.exists():
                try:
                    log.debug(f"PipelineOrchestrator cleaning up temporary directory: {engine_temp_dir_path}")
                    shutil.rmtree(engine_temp_dir_path, ignore_errors=True)
                except Exception as e:
                    log.error(f"Error cleaning up orchestrator temporary directory {engine_temp_dir_path}: {e}", exc_info=True)

        return overall_status