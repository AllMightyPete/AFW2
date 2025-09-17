import datetime
import logging

from .base_stage import ProcessingStage
from ..asset_context import AssetProcessingContext # Adjusted import path assuming asset_context is in processing.pipeline
# If AssetProcessingContext is directly under 'processing', the import would be:
# from ...asset_context import AssetProcessingContext
# Based on the provided file structure, asset_context.py is in processing/pipeline/
# So, from ...asset_context import AssetProcessingContext is likely incorrect.
# It should be: from ..asset_context import AssetProcessingContext
# Correcting this based on typical Python package structure and the location of base_stage.py

# Re-evaluating import based on common structure:
# If base_stage.py is in processing/pipeline/stages/
# and asset_context.py is in processing/pipeline/
# then the import for AssetProcessingContext from metadata_initialization.py (in stages) would be:
# from ..asset_context import AssetProcessingContext

# Let's assume the following structure for clarity:
# processing/
# L-- pipeline/
#     L-- __init__.py
#     L-- asset_context.py
#     L-- base_stage.py (Mistake here, base_stage is in stages, so it's ..base_stage)
#     L-- stages/
#         L-- __init__.py
#         L-- metadata_initialization.py
#         L-- base_stage.py (Corrected: base_stage.py is here)

# Corrected imports based on the plan and typical structure:
# base_stage.py is in processing/pipeline/stages/
# asset_context.py is in processing/pipeline/

# from ..base_stage import ProcessingStage # This would mean base_stage is one level up from stages (i.e. in pipeline)
# The plan says: from ..base_stage import ProcessingStage
# This implies that metadata_initialization.py is in a subdirectory of where base_stage.py is.
# However, the file path for metadata_initialization.py is processing/pipeline/stages/metadata_initialization.py
# And base_stage.py is listed as processing/pipeline/stages/base_stage.py in the open tabs.
# So, the import should be:
# from .base_stage import ProcessingStage

# AssetProcessingContext is at processing/pipeline/asset_context.py
# So from processing/pipeline/stages/metadata_initialization.py, it would be:
# from ..asset_context import AssetProcessingContext

# Final check on imports based on instructions:
# `from ..base_stage import ProcessingStage` -> This means base_stage.py is in `processing/pipeline/`
# `from ...asset_context import AssetProcessingContext` -> This means asset_context.py is in `processing/`
# Let's verify the location of these files from the environment details.
# processing/pipeline/asset_context.py
# processing/pipeline/stages/base_stage.py
#
# So, from processing/pipeline/stages/metadata_initialization.py:
# To import ProcessingStage from processing/pipeline/stages/base_stage.py:
# from .base_stage import ProcessingStage
# To import AssetProcessingContext from processing/pipeline/asset_context.py:
# from ..asset_context import AssetProcessingContext

# The instructions explicitly state:
# `from ..base_stage import ProcessingStage`
# `from ...asset_context import AssetProcessingContext`
# This implies a different structure than what seems to be in the file tree.
# I will follow the explicit import instructions from the task.
# This means:
# base_stage.py is expected at `processing/pipeline/base_stage.py`
# asset_context.py is expected at `processing/asset_context.py`

# Given the file tree:
# processing/pipeline/asset_context.py
# processing/pipeline/stages/base_stage.py
# The imports in `processing/pipeline/stages/metadata_initialization.py` should be:
# from .base_stage import ProcessingStage
# from ..asset_context import AssetProcessingContext

# I will use the imports that align with the provided file structure.



logger = logging.getLogger(__name__)

class MetadataInitializationStage(ProcessingStage):
    """
    Initializes metadata structures within the AssetProcessingContext.
    This stage sets up asset_metadata, processed_maps_details, and
    merged_maps_details.
    """
    def execute(self, context: AssetProcessingContext) -> AssetProcessingContext:
        logger.debug(f"METADATA_INIT_DEBUG: Entry - context.output_base_path = {context.output_base_path}") # Added
        """
        Executes the metadata initialization logic.

        Args:
            context: The AssetProcessingContext for the current asset.

        Returns:
            The modified AssetProcessingContext.
        """
        if context.status_flags.get('skip_asset', False):
            logger.debug(f"Asset '{context.asset_rule.asset_name if context.asset_rule else 'Unknown'}': Skipping metadata initialization as 'skip_asset' is True.")
            return context

        logger.debug(f"Asset '{context.asset_rule.asset_name if context.asset_rule else 'Unknown'}': Initializing metadata.")

        context.asset_metadata = {}
        context.processed_maps_details = {}
        context.merged_maps_details = {}

        # Populate Initial asset_metadata
        if context.asset_rule:
            context.asset_metadata['asset_name'] = context.asset_rule.asset_name
            # Attempt to get 'id' from common_metadata or use asset_name as a fallback
            asset_id_val = context.asset_rule.common_metadata.get('id', context.asset_rule.common_metadata.get('asset_id'))
            if asset_id_val is None:
                logger.warning(f"Asset '{context.asset_rule.asset_name}': No 'id' or 'asset_id' found in common_metadata. Using asset_name as asset_id.")
                asset_id_val = context.asset_rule.asset_name
            context.asset_metadata['asset_id'] = str(asset_id_val)

            # Assuming source_path, output_path_pattern, tags, custom_fields might also be in common_metadata
            context.asset_metadata['source_path'] = str(context.asset_rule.common_metadata.get('source_path', 'N/A'))
            context.asset_metadata['output_path_pattern'] = context.asset_rule.common_metadata.get('output_path_pattern', 'N/A')
            context.asset_metadata['tags'] = list(context.asset_rule.common_metadata.get('tags', []))
            context.asset_metadata['custom_fields'] = dict(context.asset_rule.common_metadata.get('custom_fields', {}))
        else:
            # Handle cases where asset_rule might be None, though typically it should be set
            logger.warning("AssetRule is not set in context during metadata initialization.")
            context.asset_metadata['asset_name'] = "Unknown Asset"
            context.asset_metadata['asset_id'] = "N/A"
            context.asset_metadata['source_path'] = "N/A"
            context.asset_metadata['output_path_pattern'] = "N/A"
            context.asset_metadata['tags'] = []
            context.asset_metadata['custom_fields'] = {}


        if context.source_rule:
            # SourceRule also doesn't have 'name' or 'id' directly.
            # Using 'input_path' as a proxy for name, and a placeholder for id.
            source_rule_name_val = context.source_rule.input_path if context.source_rule.input_path else "Unknown Source Rule Path"
            source_rule_id_val = context.source_rule.high_level_sorting_parameters.get('id', "N/A_SR_ID") # Check high_level_sorting_parameters
            logger.debug(f"SourceRule: using input_path '{source_rule_name_val}' as name, and '{source_rule_id_val}' as id.")
            context.asset_metadata['source_rule_name'] = source_rule_name_val
            context.asset_metadata['source_rule_id'] = str(source_rule_id_val)
        else:
            logger.warning("SourceRule is not set in context during metadata initialization.")
            context.asset_metadata['source_rule_name'] = "Unknown Source Rule"
            context.asset_metadata['source_rule_id'] = "N/A"

        context.asset_metadata['effective_supplier'] = context.effective_supplier
        context.asset_metadata['processing_start_time'] = datetime.datetime.now().isoformat()
        context.asset_metadata['status'] = "Pending"

        app_version_value = None
        if context.config_obj and hasattr(context.config_obj, 'app_version'):
            app_version_value = context.config_obj.app_version

        if app_version_value:
            context.asset_metadata['version'] = app_version_value
        else:
            logger.warning("App version not found using config_obj.app_version. Setting version to 'N/A'.")
            context.asset_metadata['version'] = "N/A"

        if context.incrementing_value is not None:
            context.asset_metadata['incrementing_value'] = context.incrementing_value
        
        # The plan mentions sha5_value, which is likely a typo for sha256 or similar.
        # Implementing as 'sha5_value' per instructions, but noting the potential typo.
        if hasattr(context, 'sha5_value') and context.sha5_value is not None: # Check attribute existence
            context.asset_metadata['sha5_value'] = context.sha5_value
        elif hasattr(context, 'sha256_value') and context.sha256_value is not None: # Fallback if sha5 was a typo
             logger.debug("sha5_value not found, using sha256_value if available for metadata.")
             context.asset_metadata['sha256_value'] = context.sha256_value


        logger.info(f"Asset '{context.asset_metadata.get('asset_name', 'Unknown')}': Metadata initialized.")
        # Example of how you might log the full metadata for debugging:
        # logger.debug(f"Initialized metadata: {context.asset_metadata}")

        logger.debug(f"METADATA_INIT_DEBUG: Exit - context.output_base_path = {context.output_base_path}") # Added
        return context