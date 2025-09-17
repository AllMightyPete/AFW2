import logging
from .base_stage import ProcessingStage
from ..asset_context import AssetProcessingContext

class AssetSkipLogicStage(ProcessingStage):
    """
    Processing stage to determine if an asset should be skipped based on various conditions.
    """
    def execute(self, context: AssetProcessingContext) -> AssetProcessingContext:
        """
        Executes the asset skip logic.

        Args:
            context: The asset processing context.

        Returns:
            The updated asset processing context.
        """
        context.status_flags['skip_asset'] = False  # Initialize/reset skip flag
        asset_name_for_log = context.asset_rule.asset_name if context.asset_rule else "Unknown Asset"

        # 1. Check for Supplier Error
        # Assuming 'supplier_error' might be set by a previous stage (e.g., SupplierDeterminationStage)
        # or if effective_supplier is None after attempts to determine it.
        if context.effective_supplier is None or context.status_flags.get('supplier_error', False):
            logging.info(f"Asset '{asset_name_for_log}': Skipping due to missing or invalid supplier.")
            context.status_flags['skip_asset'] = True
            context.status_flags['skip_reason'] = "Invalid or missing supplier"
            return context

        # 2. Check process_status in asset_rule.common_metadata
        process_status = context.asset_rule.common_metadata.get('process_status')

        if process_status == "SKIP":
            logging.info(f"Asset '{asset_name_for_log}': Skipping as per common_metadata.process_status 'SKIP'.")
            context.status_flags['skip_asset'] = True
            context.status_flags['skip_reason'] = "Process status set to SKIP in common_metadata"
            return context

        # Assuming context.config_obj.general_settings.overwrite_existing is a valid path.
        # This might need adjustment if 'general_settings' or 'overwrite_existing' is not found.
        # For now, we'll assume it's correct based on the original code's intent.
        if process_status == "PROCESSED" and \
           hasattr(context.config_obj, 'general_settings') and \
           not getattr(context.config_obj.general_settings, 'overwrite_existing', True): # Default to True (allow overwrite) if not found
            logging.info(
                f"Asset '{asset_name_for_log}': Skipping as it's already 'PROCESSED' (from common_metadata) "
                f"and overwrite is disabled."
            )
            context.status_flags['skip_asset'] = True
            context.status_flags['skip_reason'] = "Already processed (common_metadata), overwrite disabled"
            return context

        # If none of the above conditions are met, skip_asset remains False.
        return context