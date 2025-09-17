# processing_engine.py

import os
import math
import shutil
import tempfile
import logging
from pathlib import Path
from typing import List, Dict, Tuple, Optional, Set
log = logging.getLogger(__name__)
# Attempt to import image processing libraries
try:
    import cv2
    import numpy as np
except ImportError as e:
    log.error(f"Failed to import cv2 or numpy in processing_engine.py: {e}", exc_info=True)
    print("ERROR: Missing required image processing libraries. Please install opencv-python and numpy:")
    print("pip install opencv-python numpy")
    # Allow import to fail but log error; execution will likely fail later
    cv2 = None
    np = None


try:
    from configuration import Configuration, ConfigurationError
    from rule_structure import SourceRule, AssetRule, FileRule
    from utils.path_utils import generate_path_from_pattern, sanitize_filename
    from processing.utils import image_processing_utils as ipu # Corrected import
except ImportError as e:
     # Temporarily print to console as log might not be initialized yet
     print(f"ERROR during initial imports in processing_engine.py: {e}")
     # log.error(f"Failed to import Configuration or rule_structure classes in processing_engine.py: {e}", exc_info=True) # Log will be used after init
     print("ERROR: Cannot import Configuration or rule_structure classes.")
     print("Ensure configuration.py and rule_structure.py are in the same directory or Python path.")
     # Allow import to fail but log error; execution will likely fail later
     Configuration = None
     SourceRule = None
     AssetRule = None
     FileRule = None


# Initialize logger early
log = logging.getLogger(__name__)
# Basic config if logger hasn't been set up elsewhere (e.g., during testing)
if not log.hasHandlers():
     logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')

# Use logger defined in main.py (or configure one here if run standalone)

from processing.pipeline.orchestrator import PipelineOrchestrator
# from processing.pipeline.asset_context import AssetProcessingContext # AssetProcessingContext is used by the orchestrator
# Import stages that will be passed to the orchestrator (outer stages)
from processing.pipeline.stages.supplier_determination import SupplierDeterminationStage
from processing.pipeline.stages.asset_skip_logic import AssetSkipLogicStage
from processing.pipeline.stages.metadata_initialization import MetadataInitializationStage
from processing.pipeline.stages.file_rule_filter import FileRuleFilterStage
from processing.pipeline.stages.gloss_to_rough_conversion import GlossToRoughConversionStage
from processing.pipeline.stages.alpha_extraction_to_mask import AlphaExtractionToMaskStage
from processing.pipeline.stages.normal_map_green_channel import NormalMapGreenChannelStage
# Removed: from processing.pipeline.stages.individual_map_processing import IndividualMapProcessingStage
# Removed: from processing.pipeline.stages.map_merging import MapMergingStage
from processing.pipeline.stages.metadata_finalization_save import MetadataFinalizationAndSaveStage
from processing.pipeline.stages.output_organization import OutputOrganizationStage

# --- Custom Exception ---
class ProcessingEngineError(Exception):
    """Custom exception for errors during processing engine operations."""
    pass

# Helper functions moved to processing.utils.image_processing_utils

# --- Processing Engine Class ---
class ProcessingEngine:
    """
    Handles the core processing pipeline for assets based on explicit rules
    provided in a SourceRule object and static configuration.
    It does not perform classification, prediction, or rule fallback internally.
    """
    def __init__(self, config_obj: Configuration):
        """
        Initializes the processing engine with static configuration.

        Args:
            config_obj: The loaded Configuration object containing static settings.
        """
        if cv2 is None or np is None or Configuration is None or SourceRule is None:
             raise ProcessingEngineError("Essential libraries (OpenCV, NumPy) or classes (Configuration, SourceRule) are not available.")

        if not isinstance(config_obj, Configuration):
            raise ProcessingEngineError("config_obj must be a valid Configuration object.")

        self.config_obj: Configuration = config_obj
        self.temp_dir: Path | None = None # Path to the temporary working directory for a process run
        self.loaded_data_cache: dict = {} # Cache for loaded/resized data within a single process call

        # --- Pipeline Orchestrator Setup ---
        # Define pre-item and post-item processing stages
        pre_item_stages = [
            SupplierDeterminationStage(),
            AssetSkipLogicStage(),
            MetadataInitializationStage(),
            FileRuleFilterStage(),
            GlossToRoughConversionStage(), # Assumed to run on context.files_to_process if needed by old logic
            AlphaExtractionToMaskStage(),  # Same assumption as above
            NormalMapGreenChannelStage(),  # Same assumption as above
            # Note: The new RegularMapProcessorStage and MergedTaskProcessorStage handle their own transformations
            # on the specific items they process. These global transformation stages might need review
            # if they were intended to operate on a broader scope or if their logic is now fully
            # encapsulated in the new item-specific processor stages. For now, keeping them as pre-stages.
        ]

        post_item_stages = [
            OutputOrganizationStage(),         # Must run after all items are saved to temp
            MetadataFinalizationAndSaveStage(),# Must run after output organization to have final paths
        ]

        try:
            self.pipeline_orchestrator = PipelineOrchestrator(
                config_obj=self.config_obj,
                pre_item_stages=pre_item_stages,
                post_item_stages=post_item_stages
            )
            log.info("PipelineOrchestrator initialized successfully in ProcessingEngine with pre and post stages.")
        except Exception as e:
            log.error(f"Failed to initialize PipelineOrchestrator in ProcessingEngine: {e}", exc_info=True)
            self.pipeline_orchestrator = None # Ensure it's None if init fails

        log.debug("ProcessingEngine initialized.")


    def process(
        self,
        source_rule: SourceRule,
        workspace_path: Path,
        output_base_path: Path,
        overwrite: bool = False,
        incrementing_value: Optional[str] = None,
        sha5_value: Optional[str] = None
    ) -> Dict[str, List[str]]:
        """
        Executes the processing pipeline for all assets defined in the SourceRule.

        Args:
            source_rule: The SourceRule object containing explicit instructions for all assets and files.
            workspace_path: The path to the directory containing the source files (e.g., extracted archive).
            output_base_path: The base directory where processed output will be saved.
            overwrite: If True, forces reprocessing even if output exists for an asset.
            incrementing_value: Optional incrementing value for path tokens.
            sha5_value: Optional SHA5 hash value for path tokens.

        Returns:
            Dict[str, List[str]]: A dictionary summarizing the status of each asset:
                                  {"processed": [asset_name1, ...],
                                   "skipped": [asset_name2, ...],
                                   "failed": [asset_name3, ...]}
        """
        log.info(f"VERIFY: ProcessingEngine.process called with rule for input: {source_rule.input_path}") # DEBUG Verify
        log.debug(f"  VERIFY Rule Details: {source_rule}") # DEBUG Verify (Optional detailed log)
        if not isinstance(source_rule, SourceRule):
            raise ProcessingEngineError("process() requires a valid SourceRule object.")
        if not isinstance(workspace_path, Path) or not workspace_path.is_dir():
            raise ProcessingEngineError(f"Invalid workspace path provided: {workspace_path}")
        if not isinstance(output_base_path, Path):
            raise ProcessingEngineError(f"Invalid output base path provided: {output_base_path}")

        log.info(f"ProcessingEngine starting process for {len(source_rule.assets)} asset(s) defined in SourceRule.")
        overall_status = {"processed": [], "skipped": [], "failed": []}
        self.loaded_data_cache = {} # Reset cache for this run
        # Store incoming optional values for use in path generation
        self.current_incrementing_value = incrementing_value
        self.current_sha5_value = sha5_value
        log.debug(f"Received incrementing_value: {self.current_incrementing_value}, sha5_value: {self.current_sha5_value}")

        # Use a temporary directory for intermediate files (like saved maps)
        try:
            self.temp_dir = Path(tempfile.mkdtemp(prefix=self.config_obj.temp_dir_prefix))
            log.debug(f"Created temporary workspace for engine: {self.temp_dir}")
            # --- NEW PIPELINE ORCHESTRATOR LOGIC ---
            if hasattr(self, 'pipeline_orchestrator') and self.pipeline_orchestrator:
                log.info("Processing source rule using PipelineOrchestrator.")
                overall_status = self.pipeline_orchestrator.process_source_rule(
                    source_rule=source_rule,
                    workspace_path=workspace_path, # This is the path to the source files (e.g. extracted archive)
                    output_base_path=output_base_path,
                    overwrite=overwrite,
                    incrementing_value=self.current_incrementing_value,
                    sha5_value=self.current_sha5_value
                )
            else:
                log.error(f"PipelineOrchestrator not available for SourceRule '{source_rule.input_path}'. Marking all {len(source_rule.assets)} assets as failed.")
                for asset_rule in source_rule.assets:
                    overall_status["failed"].append(asset_rule.asset_name)

            log.info(f"ProcessingEngine finished. Summary: {overall_status}")
            return overall_status

        except Exception as e:
            log.exception(f"Processing engine failed unexpectedly: {e}")
            # Ensure all assets not processed/skipped are marked as failed
            processed_or_skipped = set(overall_status["processed"] + overall_status["skipped"])
            for asset_rule in source_rule.assets:
                if asset_rule.asset_name not in processed_or_skipped:
                    overall_status["failed"].append(asset_rule.asset_name)
            return overall_status # Return partial status if possible
        finally:
            self._cleanup_workspace()


    def _cleanup_workspace(self):
        """Removes the temporary workspace directory if it exists."""
        if self.temp_dir and self.temp_dir.exists():
            try:
                log.debug(f"Cleaning up engine temporary workspace: {self.temp_dir}")
                # Ignore errors during cleanup (e.g., permission errors on copied .git files)
                shutil.rmtree(self.temp_dir, ignore_errors=True)
                self.temp_dir = None
                log.debug("Engine temporary workspace cleaned up successfully.")
            except Exception as e:
                log.error(f"Failed to remove engine temporary workspace {self.temp_dir}: {e}", exc_info=True)
        self.loaded_data_cache = {} # Clear cache after cleanup

