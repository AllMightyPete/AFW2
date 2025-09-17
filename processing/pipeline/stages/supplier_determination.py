import logging

from .base_stage import ProcessingStage
from ..asset_context import AssetProcessingContext

class SupplierDeterminationStage(ProcessingStage):
    """
    Determines the effective supplier for an asset based on asset and source rules.
    """

    def execute(self, context: AssetProcessingContext) -> AssetProcessingContext:
        """
        Determines and validates the effective supplier for the asset.

        Args:
            context: The asset processing context.

        Returns:
            The updated asset processing context.
        """
        effective_supplier = None
        logger = logging.getLogger(__name__) # Using a logger specific to this module
        asset_name_for_log = context.asset_rule.asset_name if context.asset_rule else "Unknown Asset"

        # 1. Check source_rule.supplier_override (highest precedence)
        if context.source_rule and context.source_rule.supplier_override:
            effective_supplier = context.source_rule.supplier_override
            logger.debug(f"Asset '{asset_name_for_log}': Supplier override from source_rule found: '{effective_supplier}'.")
        # 2. If not overridden, check source_rule.supplier_identifier
        elif context.source_rule and context.source_rule.supplier_identifier:
            effective_supplier = context.source_rule.supplier_identifier
            logger.debug(f"Asset '{asset_name_for_log}': Supplier identifier from source_rule found: '{effective_supplier}'.")

        # 3. Validation
        if not effective_supplier:
            logger.error(f"Asset '{asset_name_for_log}': No supplier defined in source_rule (override or identifier).")
            context.effective_supplier = None
            if 'status_flags' not in context: # Ensure status_flags exists
                context.status_flags = {}
            context.status_flags['supplier_error'] = True
        # Assuming context.config_obj.suppliers is a valid way to get the list of configured suppliers.
        # This might need further investigation if errors occur here later.
        elif context.config_obj and hasattr(context.config_obj, 'suppliers') and effective_supplier not in context.config_obj.suppliers:
            logger.warning(
                f"Asset '{asset_name_for_log}': Determined supplier '{effective_supplier}' not found in global supplier configuration. "
                f"Available: {list(context.config_obj.suppliers.keys()) if context.config_obj.suppliers else 'None'}"
            )
            context.effective_supplier = None
            if 'status_flags' not in context: # Ensure status_flags exists
                context.status_flags = {}
            context.status_flags['supplier_error'] = True
        else:
            context.effective_supplier = effective_supplier
            logger.info(f"Asset '{asset_name_for_log}': Effective supplier set to '{effective_supplier}'.")
            # Optionally clear the error flag if previously set and now resolved.
            if 'supplier_error' in context.status_flags:
                 del context.status_flags['supplier_error']
        
        # merged_image_tasks are loaded from app_settings.json into Configuration object,
        # not from supplier-specific presets.
        # Ensure the attribute exists on context for PrepareProcessingItemsStage,
        # which will get it from context.config_obj.
        if not hasattr(context, 'merged_image_tasks'):
             context.merged_image_tasks = []


        return context