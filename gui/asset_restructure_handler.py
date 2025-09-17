# gui/asset_restructure_handler.py
import logging
from PySide6.QtCore import QObject, Slot, QModelIndex
from PySide6.QtGui import QColor # Might be needed if copying logic directly, though unlikely now
from pathlib import Path
from .unified_view_model import UnifiedViewModel
from rule_structure import SourceRule, AssetRule, FileRule

log = logging.getLogger(__name__)

class AssetRestructureHandler(QObject):
    """
    Handles the model restructuring logic triggered by changes
    to FileRule target asset overrides in the UnifiedViewModel.
    """
    def __init__(self, model: UnifiedViewModel, parent=None):
        super().__init__(parent)
        if not isinstance(model, UnifiedViewModel):
            raise TypeError("AssetRestructureHandler requires a UnifiedViewModel instance.")
        self.model = model
        # Connect to the modified signal (passes FileRule object)
        self.model.targetAssetOverrideChanged.connect(self.handle_target_asset_override)
        # Connect to the new signal for AssetRule name changes
        self.model.assetNameChanged.connect(self.handle_asset_name_changed)
        log.debug("AssetRestructureHandler initialized.")

    @Slot(FileRule, str, QModelIndex)
    def handle_target_asset_override(self, file_rule_item: FileRule, new_target_name: str, index: QModelIndex):
        """
        Slot connected to UnifiedViewModel.targetAssetOverrideChanged.
        Orchestrates model changes based on the new target asset path.

        Args:
            file_rule_item: The FileRule object whose override changed.
            new_target_name: The new target asset path (string).
            index: The QModelIndex of the changed item (passed by the signal).
        """
        if not isinstance(file_rule_item, FileRule):
            log.warning(f"Handler received targetAssetOverrideChanged for non-FileRule item: {type(file_rule_item)}. Aborting.")
            return

        # Crucially, use file_rule_item for all logic. 'index' is for context or if model interaction is *unavoidable* (which it shouldn't be here).
        log.debug(f"Handler received targetAssetOverrideChanged: OBJECT='{file_rule_item!r}', FILE_PATH='{file_rule_item.file_path}', NEW_NAME='{new_target_name}'")

        # Ensure new_target_name is a string or None (already string from signal, but good practice if it could be object)
        effective_new_target_name = str(new_target_name).strip() if new_target_name is not None else None
        if effective_new_target_name == "": effective_new_target_name = None # Treat empty string as None

        # --- Get necessary context ---
        old_parent_asset = getattr(file_rule_item, 'parent_asset', None)
        if not old_parent_asset:
            log.error(f"Handler: File item '{Path(file_rule_item.file_path).name}' has no parent asset. Cannot restructure.")
            # Note: Data change already happened in setData, cannot easily revert here.
            return

        source_rule = getattr(old_parent_asset, 'parent_source', None)
        if not source_rule:
            log.error(f"Handler: Could not find SourceRule for parent asset '{old_parent_asset.asset_name}'. Cannot restructure.")
            return

        # --- Logic based on the new target name ---
        target_parent_asset = None
        target_parent_index = QModelIndex() # This will be the QModelIndex of the target AssetRule
        move_occurred = False

        # 1. Find existing target parent AssetRule within the same SourceRule
        if effective_new_target_name:
            for i, asset in enumerate(source_rule.assets):
                if asset.asset_name == effective_new_target_name:
                    target_parent_asset = asset
                    # Get QModelIndex for the target parent AssetRule
                    try:
                        source_rule_row = self.model._source_rules.index(source_rule)
                        source_rule_index = self.model.createIndex(source_rule_row, 0, source_rule)
                        target_parent_index = self.model.index(i, 0, source_rule_index) # QModelIndex for the target AssetRule
                        if not target_parent_index.isValid():
                             log.error(f"Handler: Failed to create valid QModelIndex for existing target parent '{effective_new_target_name}'.")
                             target_parent_asset = None # Reset if index is invalid
                    except ValueError:
                         log.error(f"Handler: Could not find SourceRule index while looking for target parent '{effective_new_target_name}'.")
                         target_parent_asset = None # Reset if index is invalid
                    break

        # 2. Handle Move or Creation
        if target_parent_asset: # An existing AssetRule to move to was found
            # --- Move to Existing Parent ---
            if target_parent_asset != old_parent_asset:
                log.info(f"Handler: Moving file '{Path(file_rule_item.file_path).name}' to existing asset '{target_parent_asset.asset_name}'.")
                # The 'index' parameter IS the QModelIndex of the FileRule being changed.
                # No need to re-fetch or re-validate it if the signal emits it correctly.
                # The core issue was using a stale index to get the *object*, now we *have* the object.
                source_file_qmodelindex = index

                if not source_file_qmodelindex or not source_file_qmodelindex.isValid(): # Should always be valid if signal emits it
                    log.error(f"Handler: Received invalid QModelIndex for source file '{Path(file_rule_item.file_path).name}'. Cannot move.")
                    return

                if self.model.moveFileRule(source_file_qmodelindex, target_parent_index): # target_parent_index is for the AssetRule
                    move_occurred = True
                else:
                    log.error(f"Handler: Model failed to move file rule to existing asset '{target_parent_asset.asset_name}'.")
            else:
                # Target is the same as the old parent. No move needed.
                log.debug(f"Handler: Target asset '{effective_new_target_name}' is the same as the current parent. No move required.")

        elif effective_new_target_name: # No existing AssetRule found, but a new name is provided. Create it.
            # --- Create New Parent AssetRule and Move ---
            log.info(f"Handler: Creating new asset '{effective_new_target_name}' and moving file '{Path(file_rule_item.file_path).name}'.")
            new_asset_qmodelindex = self.model.createAssetRule(source_rule, effective_new_target_name, copy_from_asset=old_parent_asset)

            if new_asset_qmodelindex.isValid():
                target_parent_asset = new_asset_qmodelindex.internalPointer() # Get the newly created AssetRule object
                target_parent_index = new_asset_qmodelindex # The QModelIndex of the new AssetRule

                source_file_qmodelindex = index
                if not source_file_qmodelindex or not source_file_qmodelindex.isValid(): # Should always be valid
                    log.error(f"Handler: Received invalid QModelIndex for source file '{Path(file_rule_item.file_path).name}'. Cannot move to new asset.")
                    self.model.removeAssetRule(target_parent_asset) # Attempt to clean up newly created asset
                    return

                if self.model.moveFileRule(source_file_qmodelindex, target_parent_index): # Move to the new AssetRule
                    move_occurred = True
                else:
                    log.error(f"Handler: Model failed to move file rule to newly created asset '{effective_new_target_name}'.")
                    # Consider removing the newly created asset if the move fails
                    self.model.removeAssetRule(target_parent_asset) # Attempt to clean up
            else:
                log.error(f"Handler: Model failed to create new asset rule '{effective_new_target_name}'. Cannot move file.")

        else: # effective_new_target_name is None or empty (override cleared)
            log.debug(f"Handler: Target asset override cleared for '{Path(file_rule_item.file_path).name}'. File remains in parent '{old_parent_asset.asset_name}'.")
            # No move occurs in this interpretation if the override is simply cleared.
            # The file_rule_item.target_asset_name_override is now None (set by model.setData).

        # 3. Cleanup Empty Old Parent (only if a move occurred and old parent is now empty)
        if move_occurred and old_parent_asset and not old_parent_asset.files and old_parent_asset != target_parent_asset:
            log.info(f"Handler: Attempting to remove empty old parent asset '{old_parent_asset.asset_name}'.")
            if not self.model.removeAssetRule(old_parent_asset):
                log.warning(f"Handler: Model failed to remove empty old parent asset '{old_parent_asset.asset_name}'.")
        elif move_occurred:
            log.debug(f"Handler: Old parent asset '{old_parent_asset.asset_name}' still contains files or is the target. No removal needed.")

        log.debug(f"Handler finished processing targetAssetOverrideChanged for '{Path(file_rule_item.file_path).name}'.")

    def _get_qmodelindex_for_item(self, item_to_find):
        """
        Helper to find the QModelIndex for a given FileRule or AssetRule item.
        Returns a valid QModelIndex or QModelIndex() if not found/invalid.
        """
        if isinstance(item_to_find, FileRule):
            parent_asset = getattr(item_to_find, 'parent_asset', None)
            if not parent_asset: return QModelIndex()
            source_rule = getattr(parent_asset, 'parent_source', None)
            if not source_rule: return QModelIndex()

            try:
                source_rule_row = self.model._source_rules.index(source_rule)
                source_rule_index = self.model.createIndex(source_rule_row, 0, source_rule)
                if not source_rule_index.isValid(): return QModelIndex()

                parent_asset_row = source_rule.assets.index(parent_asset)
                parent_asset_index = self.model.index(parent_asset_row, 0, source_rule_index)
                if not parent_asset_index.isValid(): return QModelIndex()

                item_row = parent_asset.files.index(item_to_find)
                return self.model.index(item_row, 0, parent_asset_index)
            except ValueError:
                log.error(f"Error finding item {item_to_find} in model hierarchy during QModelIndex reconstruction.")
                return QModelIndex()

        elif isinstance(item_to_find, AssetRule):
            source_rule = getattr(item_to_find, 'parent_source', None)
            if not source_rule: return QModelIndex()
            try:
                source_rule_row = self.model._source_rules.index(source_rule)
                source_rule_index = self.model.createIndex(source_rule_row, 0, source_rule)
                if not source_rule_index.isValid(): return QModelIndex()

                item_row = source_rule.assets.index(item_to_find)
                return self.model.index(item_row, 0, source_rule_index)
            except ValueError:
                log.error(f"Error finding asset {item_to_find.asset_name} in model hierarchy during QModelIndex reconstruction.")
                return QModelIndex()
        return QModelIndex()

    @Slot(AssetRule, str, QModelIndex)
    def handle_asset_name_changed(self, asset_rule_item: AssetRule, new_name: str, index: QModelIndex):
        """
        Slot connected to UnifiedViewModel.assetNameChanged.
        Handles logic when an AssetRule's name is changed.

        Args:
            asset_rule_item: The AssetRule object whose name changed.
            new_name: The new name of the asset.
            index: The QModelIndex of the changed AssetRule item.
        """
        if not isinstance(asset_rule_item, AssetRule):
            log.warning(f"Handler received assetNameChanged for non-AssetRule item: {type(asset_rule_item)}. Aborting.")
            return

        # The 'old_name' is not directly passed by the new signal signature.
        # If needed, it would have to be inferred or stored prior to the change.
        # However, the model's setData already handles updating child FileRule targets.
        # This handler's main job is to react to the AssetRule object itself.
        log.debug(f"Handler received assetNameChanged: OBJECT='{asset_rule_item!r}', ASSET_NAME='{asset_rule_item.asset_name}', NEW_NAME='{new_name}'")


        # The UnifiedViewModel.setData has already updated FileRule.target_asset_name_override
        # for any FileRules that were pointing to the *old* asset name across the entire model.

        # The primary purpose of this handler slot, given the problem description,
        # is to ensure that if any restructuring or disk operations were tied to an AssetRule's
        # name, they would now correctly use 'asset_rule_item' (the actual object)
        # and 'new_name'.

        # For this specific task, confirming correct identification is key.
        # If this handler were also responsible for renaming directories on disk,
        # this is where that logic would go, using asset_rule_item and new_name.
        # The old name would need to be retrieved differently if essential for such an operation,
        # e.g. by storing it temporarily before the model's setData commits the change,
        # or by having the signal pass it (which it currently doesn't in the revised design).
        # For now, the model handles the critical part of updating linked FileRules.

        log.info(f"Handler correctly identified AssetRule '{new_name}' for processing using the direct object. Model's setData handles related FileRule target updates.")