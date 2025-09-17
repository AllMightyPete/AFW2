# gui/unified_view_model.py
import logging
log = logging.getLogger(__name__)
from PySide6.QtCore import QAbstractItemModel, QModelIndex, Qt, Signal, Slot, QMimeData, QByteArray, QDataStream, QIODevice
from PySide6.QtGui import QColor
from pathlib import Path
from rule_structure import SourceRule, AssetRule, FileRule
from configuration import load_base_config
from typing import List

class CustomRoles:
    MapTypeRole = Qt.UserRole + 1
    TargetAssetRole = Qt.UserRole + 2
    # Add other custom roles here as needed
class UnifiedViewModel(QAbstractItemModel):
    # --- Color Constants for Row Backgrounds ---
    # Old colors removed, using config now + fixed source color
    SOURCE_RULE_COLOR = QColor("#306091")
    # -----------------------------------------

    """
    A QAbstractItemModel for displaying and editing the hierarchical structure
    of SourceRule -> AssetRule -> FileRule.
    """
    # Signal emitted when a FileRule's target asset override changes.
    # Carries the FileRule object and the new target asset path (or None).
    targetAssetOverrideChanged = Signal(FileRule, str, QModelIndex)

    # Signal emitted when an AssetRule's name changes.
    # Carries the AssetRule object, the new name, and the index.
    assetNameChanged = Signal(AssetRule, str, QModelIndex)

    Columns = [
        "Name", "Target Asset", "Supplier",
        "Asset Type", "Item Type"
    ]

    COL_NAME = 0
    COL_TARGET_ASSET = 1
    COL_SUPPLIER = 2
    COL_ASSET_TYPE = 3
    COL_ITEM_TYPE = 4
    # COL_STATUS = 5 # Removed
    # COL_OUTPUT_PATH = 6 # Removed

    # --- Drag and Drop MIME Type ---
    MIME_TYPE = "application/x-filerule-index-list"

    def __init__(self, parent=None):
        super().__init__(parent)
        self._source_rules = []
        # self._display_mode removed
        self._asset_type_colors = {}
        self._file_type_colors = {}
        self._asset_type_keys = []
        self._file_type_keys = []
        self._load_definitions()

    def _load_definitions(self):
        """Loads configuration and caches colors and type keys."""
        try:
            base_config = load_base_config()
            asset_type_defs = base_config.get('ASSET_TYPE_DEFINITIONS', {})
            file_type_defs = base_config.get('FILE_TYPE_DEFINITIONS', {})

            # Cache Asset Type Definitions (Keys and Colors)
            self._asset_type_keys = sorted(list(asset_type_defs.keys()))
            for type_name, type_info in asset_type_defs.items():
                hex_color = type_info.get("color")
                if hex_color:
                    try:
                        self._asset_type_colors[type_name] = QColor(hex_color)
                    except ValueError:
                        log.warning(f"Invalid hex color '{hex_color}' for asset type '{type_name}' in config.")

            # Cache File Type Definitions (Keys and Colors)
            self._file_type_keys = sorted(list(file_type_defs.keys()))
            for type_name, type_info in file_type_defs.items():
                hex_color = type_info.get("color")
                if hex_color:
                    try:
                        self._file_type_colors[type_name] = QColor(hex_color)
                    except ValueError:
                        log.warning(f"Invalid hex color '{hex_color}' for file type '{type_name}' in config.")

        except Exception as e:
            log.exception(f"Error loading or caching colors from configuration: {e}")
            # Ensure caches/lists are empty if loading fails
            self._asset_type_colors = {}
            self._file_type_colors = {}
            self._asset_type_keys = []
            self._file_type_keys = []

    def load_data(self, source_rules_list: list):
        """Loads or reloads the model with a list of SourceRule objects."""
        # Consider if color cache needs refreshing if config can change dynamically
        # self._load_and_cache_colors() # Uncomment if config can change and needs refresh
        self.beginResetModel()
        self._source_rules = source_rules_list if source_rules_list else []
        # Ensure back-references for parent lookup are set on the NEW items
        for source_rule in self._source_rules:
            for asset_rule in source_rule.assets:
                asset_rule.parent_source = source_rule
                for file_rule in asset_rule.files:
                    file_rule.parent_asset = asset_rule
        self.endResetModel()

    def clear_data(self):
        """Clears the model data."""
        self.beginResetModel()
        self._source_rules = []
        self.endResetModel()

    def get_all_source_rules(self) -> list:
        """Returns the internal list of SourceRule objects."""
        return self._source_rules

    # set_display_mode removed

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:
        """Returns the number of rows under the given parent."""
        if not parent.isValid():
            # Parent is the invisible root. Children are the SourceRules.
            return len(self._source_rules)

        parent_item = parent.internalPointer()
        if isinstance(parent_item, SourceRule):
            return len(parent_item.assets)
        elif isinstance(parent_item, AssetRule):
            return len(parent_item.files)
        elif isinstance(parent_item, FileRule):
            return 0

        return 0 # Should not happen for valid items

    def columnCount(self, parent: QModelIndex = QModelIndex()) -> int:
        """Returns the number of columns."""
        return len(self.Columns)

    def parent(self, index: QModelIndex) -> QModelIndex:
        """Returns the parent of the model item with the given index."""
        if not index.isValid():
            return QModelIndex()

        child_item = index.internalPointer()
        if child_item is None:
             return QModelIndex()

        # Determine the parent based on the item type
        if isinstance(child_item, SourceRule):
             # Parent is the invisible root
             return QModelIndex()
        elif isinstance(child_item, AssetRule):
             # Parent is a SourceRule. Find its row in the _source_rules list.
             parent_item = getattr(child_item, 'parent_source', None)
             if parent_item and parent_item in self._source_rules:
                 try:
                     parent_row = self._source_rules.index(parent_item)
                     return self.createIndex(parent_row, 0, parent_item)
                 except ValueError:
                      return QModelIndex() # Should not happen if parent_source is correct
             else:
                 return QModelIndex() # Parent SourceRule not found or reference missing

        elif isinstance(child_item, FileRule):
            # Parent is an AssetRule. Find its row within its parent SourceRule.
            parent_item = getattr(child_item, 'parent_asset', None)
            if parent_item:
                 grandparent_item = getattr(parent_item, 'parent_source', None)
                 if grandparent_item:
                     try:
                         parent_row = grandparent_item.assets.index(parent_item)
                         # We need the index of the grandparent (SourceRule) to create the parent index
                         grandparent_row = self._source_rules.index(grandparent_item)
                         return self.createIndex(parent_row, 0, parent_item)
                     except ValueError:
                         return QModelIndex() # Parent AssetRule or Grandparent SourceRule not found in respective lists
                 else:
                      return QModelIndex() # Grandparent (SourceRule) reference missing
            else:
                 return QModelIndex() # Parent AssetRule reference missing

        return QModelIndex() # Should not be reached


    def index(self, row: int, column: int, parent: QModelIndex = QModelIndex()) -> QModelIndex:
        """Returns the index of the item in the model specified by the given row, column and parent index."""
        if not self.hasIndex(row, column, parent):
             return QModelIndex()

        parent_item = None
        if not parent.isValid():
            # Parent is invisible root. Children are SourceRules.
            if row < len(self._source_rules):
                child_item = self._source_rules[row]
                return self.createIndex(row, column, child_item)
            else:
                return QModelIndex() # Row out of bounds for top-level items
        else:
            # Parent is a valid index, get its item
            parent_item = parent.internalPointer()

        child_item = None
        if isinstance(parent_item, SourceRule):
            if row < len(parent_item.assets):
                child_item = parent_item.assets[row]
                if not hasattr(child_item, 'parent_source'):
                     child_item.parent_source = parent_item
        elif isinstance(parent_item, AssetRule):
            if row < len(parent_item.files):
                child_item = parent_item.files[row]
                if not hasattr(child_item, 'parent_asset'):
                    child_item.parent_asset = parent_item

        if child_item:
            return self.createIndex(row, column, child_item)
        else:
            return QModelIndex()

    def data(self, index: QModelIndex, role: int = Qt.DisplayRole):
        """Returns the data stored under the given role for the item referred to by the index."""
        if not index.isValid():
            return None

        item = index.internalPointer()
        column = index.column()

        # --- Handle Background Role ---
        if role == Qt.BackgroundRole:
            if isinstance(item, SourceRule):
                return self.SOURCE_RULE_COLOR
            elif isinstance(item, AssetRule):
                # Determine effective asset type
                asset_type = item.asset_type_override if item.asset_type_override else item.asset_type
                if asset_type:
                    # Use cached color
                    return self._asset_type_colors.get(asset_type)
                else:
                    return None # Fallback if no asset_type determined
            elif isinstance(item, FileRule):
                # --- New Logic: Darkened Parent Background ---
                parent_asset = getattr(item, 'parent_asset', None)
                if parent_asset:
                    parent_asset_type = parent_asset.asset_type_override if parent_asset.asset_type_override else parent_asset.asset_type
                    parent_bg_color = self._asset_type_colors.get(parent_asset_type) if parent_asset_type else None

                    if parent_bg_color:
                        # Darken the parent color by ~30% (factor 130)
                        return parent_bg_color.darker(130)
                    else:
                        # Parent has no specific color, use default background
                        return None
                else:
                    # Should not happen if structure is correct, but fallback to default
                    return None
                # --- End New Logic ---
            else:
                return None
        # --- Handle Foreground Role (Text Color) ---
        elif role == Qt.ForegroundRole:
            if isinstance(item, FileRule):
                # Determine effective item type
                effective_item_type = item.item_type_override if item.item_type_override is not None else item.item_type
                if effective_item_type:
                    # Use cached color for text
                    return self._file_type_colors.get(effective_item_type)
            # For SourceRule and AssetRule, return None to use default text color (usually contrasts well)
            return None

        # --- Handle other roles (Display, Edit, etc.) ---
        if isinstance(item, SourceRule):
            if role == Qt.DisplayRole or role == Qt.EditRole:
                if column == self.COL_NAME:
                    return Path(item.input_path).name
                elif column == self.COL_SUPPLIER:
                    display_value = item.supplier_override if item.supplier_override is not None else item.supplier_identifier
                    return display_value if display_value is not None else ""
            return None # Other columns/roles are blank for SourceRule

        # --- Logic for AssetRule and FileRule (previously detailed mode only) ---
        elif isinstance(item, AssetRule):
            if role == Qt.DisplayRole:
                if column == self.COL_NAME: return item.asset_name
                elif column == self.COL_ASSET_TYPE:
                    display_value = item.asset_type_override if item.asset_type_override is not None else item.asset_type
                    return display_value if display_value else ""
            elif role == Qt.EditRole:
                 if column == self.COL_NAME:
                     return item.asset_name
                 elif column == self.COL_ASSET_TYPE:
                     return item.asset_type_override
            return None

        elif isinstance(item, FileRule):
            if role == Qt.DisplayRole:
                if column == self.COL_NAME: return Path(item.file_path).name
                elif column == self.COL_TARGET_ASSET:
                    return item.target_asset_name_override if item.target_asset_name_override is not None else ""
                elif column == self.COL_ITEM_TYPE:
                    override = item.item_type_override
                    initial_type = item.item_type
                    if override is not None: return override
                    else: return initial_type if initial_type else ""
            elif role == Qt.EditRole:
                if column == self.COL_TARGET_ASSET: return item.target_asset_name_override if item.target_asset_name_override is not None else ""
                elif column == self.COL_ITEM_TYPE: return item.item_type_override
            return None

        return None

    def setData(self, index: QModelIndex, value, role: int = Qt.EditRole) -> bool:
        """Sets the role data for the item at index to value."""
        if not index.isValid() or role != Qt.EditRole:
            return False

        item = index.internalPointer()
        if item is None:
             return False
        column = index.column()
        changed = False

        # --- Handle different item types ---
        if isinstance(item, SourceRule):
            if column == self.COL_SUPPLIER:
                # Get the new value, strip whitespace, treat empty as None
                log.debug(f"setData COL_SUPPLIER: Index=({index.row()},{column}), Value='{value}', Type={type(value)}")
                new_value = str(value).strip() if value is not None and str(value).strip() else None

                # Get the original identifier (assuming it exists on SourceRule)
                original_identifier = getattr(item, 'supplier_identifier', None)

                # If the new value is the same as the original, clear the override
                if new_value == original_identifier:
                    new_value = None

                # Update supplier_override only if it's different
                if item.supplier_override != new_value:
                    item.supplier_override = new_value
                    changed = True

        elif isinstance(item, AssetRule):
            if column == self.COL_NAME:
                new_asset_name = str(value).strip() if value else None
                if not new_asset_name:
                    log.warning("setData: Asset name cannot be empty.")
                    return False

                if item.asset_name == new_asset_name:
                    return False

                # --- Validation: Check for duplicates within the same SourceRule ---
                parent_source = getattr(item, 'parent_source', None)
                if parent_source:
                    for existing_asset in parent_source.assets:
                        if existing_asset.asset_name == new_asset_name and existing_asset is not item:
                            log.warning(f"setData: Duplicate asset name '{new_asset_name}' detected within the same source. Aborting rename.")
                            # Optionally, provide user feedback here via a signal or message box
                            return False
                else:
                    log.error("setData: Cannot validate asset name, parent SourceRule not found.")
                    # Decide how to handle this - proceed cautiously or abort? Aborting is safer.
                    return False
                # --- End Validation ---

                log.info(f"setData: Renaming AssetRule from '{item.asset_name}' to '{new_asset_name}'")
                old_asset_name = item.asset_name
                item.asset_name = new_asset_name
                changed = True
                # Emit signal for asset name change, including the index
                self.assetNameChanged.emit(item, new_asset_name, index)

                # --- Update Child FileRule Target Asset Overrides ---
                log.debug(f"setData: Updating FileRule target overrides from '{old_asset_name}' to '{new_asset_name}'")
                updated_file_indices = []
                for src_idx, source_rule in enumerate(self._source_rules):
                    source_rule_index = self.createIndex(src_idx, 0, source_rule)
                    for asset_idx, asset_rule in enumerate(source_rule.assets):
                        asset_rule_index = self.createIndex(asset_idx, 0, asset_rule)
                        for file_idx, file_rule in enumerate(asset_rule.files):
                            if file_rule.target_asset_name_override == old_asset_name:
                                log.debug(f"  Updating target for file: {Path(file_rule.file_path).name}")
                                file_rule.target_asset_name_override = new_asset_name
                                # Get the correct index for the file rule to emit dataChanged
                                file_rule_parent_index = self.parent(self.createIndex(file_idx, 0, file_rule))
                                file_rule_index = self.index(file_idx, self.COL_TARGET_ASSET, file_rule_parent_index)
                                if file_rule_index.isValid():
                                    updated_file_indices.append(file_rule_index)
                                else:
                                     log.warning(f"  Could not get valid index for updated file rule target: {Path(file_rule.file_path).name}")


                # Emit dataChanged for all updated file rules *after* the loop
                for file_index in updated_file_indices:
                    self.dataChanged.emit(file_index, file_index, [Qt.DisplayRole, Qt.EditRole])
                # --- End Child Update ---

            elif column == self.COL_ASSET_TYPE:
                # Delegate provides string value (e.g., "Surface", "Model") or None
                new_value = str(value) if value is not None else None
                if new_value == "": new_value = None
                # Update asset_type_override
                if item.asset_type_override != new_value:
                    item.asset_type_override = new_value
                    changed = True

        elif isinstance(item, FileRule):
            if column == self.COL_TARGET_ASSET:
                # Ensure value is string or None
                new_value = str(value).strip() if value is not None else None
                if new_value == "": new_value = None
                # Update target_asset_name_override
                if item.target_asset_name_override != new_value:
                    old_value = item.target_asset_name_override
                    item.target_asset_name_override = new_value
                    changed = True
                    # Emit signal that the override changed, let handler deal with restructuring
                    # Pass the FileRule item itself, the new value, and the index
                    self.targetAssetOverrideChanged.emit(item, new_value, index)
            elif column == self.COL_ITEM_TYPE:
                  # Delegate provides string value (e.g., "MAP_COL") or None
                 new_value = str(value) if value is not None else None
                 if new_value == "": new_value = None
                 # Update item_type_override
                 if item.item_type_override != new_value:
                     log.debug(f"setData COL_ITEM_TYPE: File='{Path(item.file_path).name}', Original Override='{item.item_type_override}', New Value='{new_value}'")
                     old_override = item.item_type_override
                     item.item_type_override = new_value
                     changed = True

                     # standard_map_type is no longer stored on FileRule.
                     # Remove the logic that updated it here.
                     pass

                     log.debug(f"setData COL_ITEM_TYPE: File='{Path(item.file_path).name}', Final Override='{item.item_type_override}'")


        if changed:
            # Emit dataChanged for the specific index and affected roles
            self.dataChanged.emit(index, index, [Qt.DisplayRole, Qt.EditRole])
            return True

        return False

    def flags(self, index: QModelIndex) -> Qt.ItemFlags:
        """Returns the item flags for the given index."""
        if not index.isValid():
             return Qt.NoItemFlags

        # Start with default flags for a valid item
        default_flags = Qt.ItemIsEnabled | Qt.ItemIsSelectable

        item = index.internalPointer()
        if not item:
            return Qt.NoItemFlags
        column = index.column()

        can_edit = False
        if isinstance(item, SourceRule):
            if column == self.COL_SUPPLIER: can_edit = True
        elif isinstance(item, AssetRule):
            if column == self.COL_NAME: can_edit = True
            if column == self.COL_ASSET_TYPE: can_edit = True
            # AssetRule items can accept drops
            default_flags |= Qt.ItemIsDropEnabled
        elif isinstance(item, FileRule):
            if column == self.COL_TARGET_ASSET: can_edit = True
            if column == self.COL_ITEM_TYPE: can_edit = True
            # FileRule items can be dragged
            default_flags |= Qt.ItemIsDragEnabled

        if can_edit:
            default_flags |= Qt.ItemIsEditable

        return default_flags
        # Removed erroneous else block

    def headerData(self, section: int, orientation: Qt.Orientation, role: int = Qt.DisplayRole):
        """Returns the data for the given role and section in the header."""
        if orientation == Qt.Horizontal and role == Qt.DisplayRole:
            if 0 <= section < len(self.Columns):
                return self.Columns[section]
        # Optionally handle Vertical header (row numbers)
        # if orientation == Qt.Vertical and role == Qt.DisplayRole:
        #     return str(section + 1)
        return None

    # Helper to get item from index
    def getItem(self, index: QModelIndex):
        """Safely returns the item associated with the index."""
        if index.isValid():
            item = index.internalPointer()
            if item:
                 return item
        return None
    # --- Method to update model based on prediction results, preserving overrides ---
    def update_rules_for_sources(self, new_source_rules: List[SourceRule]):
        """
        Updates the model's internal data based on a list of new SourceRule objects
        (typically from prediction results), merging them with existing data while
        preserving user overrides.

        Args:
            new_source_rules: A list of SourceRule objects containing the new structure.
        """
        if not new_source_rules:
            log.warning("UnifiedViewModel: update_rules_for_sources called with empty list.")
            return

        log.info(f"UnifiedViewModel: Updating rules for {len(new_source_rules)} source(s).")

        for new_source_rule in new_source_rules:
            source_path = new_source_rule.input_path
            existing_source_rule = None
            existing_source_row = -1

            # 1. Find existing SourceRule in the model
            for i, rule in enumerate(self._source_rules):
                if rule.input_path == source_path:
                    existing_source_rule = rule
                    existing_source_row = i
                    break

            if existing_source_rule is None:
                # 2. Add New SourceRule if not found
                log.debug(f"Adding new SourceRule for '{source_path}'")
                # Ensure parent references are set within the new rule hierarchy
                for asset_rule in new_source_rule.assets:
                    asset_rule.parent_source = new_source_rule
                    for file_rule in asset_rule.files:
                        file_rule.parent_asset = asset_rule

                # Add to model's internal list and emit signal
                insert_row = len(self._source_rules)
                self.beginInsertRows(QModelIndex(), insert_row, insert_row)
                self._source_rules.append(new_source_rule)
                self.endInsertRows()
                continue

            # 3. Merge Existing SourceRule
            log.debug(f"Merging SourceRule for '{source_path}'")
            existing_source_index = self.createIndex(existing_source_row, 0, existing_source_rule)
            if not existing_source_index.isValid():
                log.error(f"Could not create valid index for existing SourceRule: {source_path}. Skipping.")
                continue

            # Update non-override SourceRule fields (e.g., supplier identifier if needed)
            if existing_source_rule.supplier_identifier != new_source_rule.supplier_identifier:
                 # Only update if override is not set, or if you want prediction to always update base identifier
                 if existing_source_rule.supplier_override is None:
                     existing_source_rule.supplier_identifier = new_source_rule.supplier_identifier
                     # Emit dataChanged for the supplier column if it's displayed/editable at source level
                     supplier_col_index = self.createIndex(existing_source_row, self.COL_SUPPLIER, existing_source_rule)
                     self.dataChanged.emit(supplier_col_index, supplier_col_index, [Qt.DisplayRole, Qt.EditRole])

            # Always update the preset_name from the new_source_rule, as this reflects the latest prediction context
            if existing_source_rule.preset_name != new_source_rule.preset_name:
                log.debug(f"  Updating preset_name for SourceRule '{source_path}' from '{existing_source_rule.preset_name}' to '{new_source_rule.preset_name}'")
                existing_source_rule.preset_name = new_source_rule.preset_name
                # Note: preset_name is not directly displayed in the view, so no dataChanged needed for a specific column,
                # but if it influenced other display elements, dataChanged would be emitted for those.


            # --- Merge AssetRules ---
            existing_assets_dict = {asset.asset_name: asset for asset in existing_source_rule.assets}
            new_assets_dict = {asset.asset_name: asset for asset in new_source_rule.assets}
            processed_asset_names = set()

            # Iterate through new assets to update existing or add new ones
            for asset_name, new_asset in new_assets_dict.items():
                processed_asset_names.add(asset_name)
                existing_asset = existing_assets_dict.get(asset_name)

                if existing_asset:
                    # --- Update Existing AssetRule ---
                    log.debug(f"  Merging AssetRule: {asset_name}")
                    existing_asset_row = existing_source_rule.assets.index(existing_asset)
                    existing_asset_index = self.createIndex(existing_asset_row, 0, existing_asset)

                    # Update non-override fields (e.g., asset_type)
                    if existing_asset.asset_type != new_asset.asset_type and existing_asset.asset_type_override is None:
                        existing_asset.asset_type = new_asset.asset_type
                        asset_type_col_index = self.createIndex(existing_asset_row, self.COL_ASSET_TYPE, existing_asset)
                        self.dataChanged.emit(asset_type_col_index, asset_type_col_index, [Qt.DisplayRole, Qt.EditRole, Qt.BackgroundRole])

                    # --- Merge FileRules within the AssetRule ---
                    self._merge_file_rules(existing_asset, new_asset, existing_asset_index)

                else:
                    # --- Add New AssetRule ---
                    log.debug(f"  Adding new AssetRule: {asset_name}")
                    new_asset.parent_source = existing_source_rule
                    # Ensure file parents are set
                    for file_rule in new_asset.files:
                        file_rule.parent_asset = new_asset

                    insert_row = len(existing_source_rule.assets)
                    self.beginInsertRows(existing_source_index, insert_row, insert_row)
                    existing_source_rule.assets.append(new_asset)
                    self.endInsertRows()

            # --- Remove Old AssetRules ---
            # Find assets in existing but not in new, and remove them in reverse order
            assets_to_remove = []
            for i, existing_asset in reversed(list(enumerate(existing_source_rule.assets))):
                 if existing_asset.asset_name not in processed_asset_names:
                     assets_to_remove.append((i, existing_asset.asset_name))

            for row_index, asset_name_to_remove in assets_to_remove:
                 log.debug(f"  Removing old AssetRule: {asset_name_to_remove}")
                 self.beginRemoveRows(existing_source_index, row_index, row_index)
                 existing_source_rule.assets.pop(row_index)
                 self.endRemoveRows()


    def _merge_file_rules(self, existing_asset: AssetRule, new_asset: AssetRule, parent_asset_index: QModelIndex):
        """Helper method to merge FileRules for a given AssetRule."""
        existing_files_dict = {file.file_path: file for file in existing_asset.files}
        new_files_dict = {file.file_path: file for file in new_asset.files}
        processed_file_paths = set()

        # Iterate through new files to update existing or add new ones
        for file_path, new_file in new_files_dict.items():
            processed_file_paths.add(file_path)
            existing_file = existing_files_dict.get(file_path)

            if existing_file:
                # --- Update Existing FileRule ---
                log.debug(f"    Merging FileRule: {Path(file_path).name}")
                existing_file_row = existing_asset.files.index(existing_file)
                existing_file_index = self.createIndex(existing_file_row, 0, existing_file)

                # Update non-override fields (item_type, standard_map_type)
                changed_roles = []
                if existing_file.item_type != new_file.item_type and existing_file.item_type_override is None:
                    existing_file.item_type = new_file.item_type
                    changed_roles.extend([Qt.DisplayRole, Qt.EditRole, Qt.BackgroundRole])

                # standard_map_type is no longer stored on FileRule.
                # Remove the logic that updated it during merge.
                pass


                # Emit dataChanged only if something actually changed
                if changed_roles:
                    # Emit for all relevant columns potentially affected by type changes
                    for col in [self.COL_ITEM_TYPE]:
                        col_index = self.createIndex(existing_file_row, col, existing_file)
                        self.dataChanged.emit(col_index, col_index, changed_roles)

            else:
                # --- Add New FileRule ---
                log.debug(f"    Adding new FileRule: {Path(file_path).name}")
                new_file.parent_asset = existing_asset
                insert_row = len(existing_asset.files)
                self.beginInsertRows(parent_asset_index, insert_row, insert_row)
                existing_asset.files.append(new_file)
                self.endInsertRows()

        # --- Remove Old FileRules ---
        files_to_remove = []
        for i, existing_file in reversed(list(enumerate(existing_asset.files))):
             if existing_file.file_path not in processed_file_paths:
                 files_to_remove.append((i, Path(existing_file.file_path).name))

        for row_index, file_name_to_remove in files_to_remove:
             log.debug(f"    Removing old FileRule: {file_name_to_remove}")
             self.beginRemoveRows(parent_asset_index, row_index, row_index)
             existing_asset.files.pop(row_index)
             self.endRemoveRows()


    # --- Dedicated Model Restructuring Methods ---

    def moveFileRule(self, source_file_index: QModelIndex, target_parent_asset_index: QModelIndex):
        """Moves a FileRule (source_file_index) to a different AssetRule parent (target_parent_asset_index)."""
        if not source_file_index.isValid() or not target_parent_asset_index.isValid():
            log.error("moveFileRule: Invalid source or target index provided.")
            return False

        file_item = source_file_index.internalPointer()
        target_parent_asset = target_parent_asset_index.internalPointer()

        if not isinstance(file_item, FileRule) or not isinstance(target_parent_asset, AssetRule):
            log.error("moveFileRule: Invalid item types for source or target.")
            return False

        old_parent_asset = getattr(file_item, 'parent_asset', None)
        if not old_parent_asset:
            log.error(f"moveFileRule: Source file '{Path(file_item.file_path).name}' has no parent asset.")
            return False

        if old_parent_asset == target_parent_asset:
            log.debug("moveFileRule: Source and target parent are the same. No move needed.")
            return True

        # Get old parent index
        source_rule = getattr(old_parent_asset, 'parent_source', None)
        if not source_rule:
             log.error(f"moveFileRule: Could not find SourceRule parent for old asset '{old_parent_asset.asset_name}'.")
             return False

        try:
            old_parent_row = source_rule.assets.index(old_parent_asset)
            old_parent_index = self.createIndex(old_parent_row, 0, old_parent_asset)
            source_row = old_parent_asset.files.index(file_item)
        except ValueError:
            log.error("moveFileRule: Could not find old parent or source file within their respective lists.")
            return False

        target_row = len(target_parent_asset.files)

        log.debug(f"Moving file '{Path(file_item.file_path).name}' from '{old_parent_asset.asset_name}' (row {source_row}) to '{target_parent_asset.asset_name}' (row {target_row})")
        self.beginMoveRows(old_parent_index, source_row, source_row, target_parent_asset_index, target_row)
        # Restructure internal data
        old_parent_asset.files.pop(source_row)
        target_parent_asset.files.append(file_item)
        file_item.parent_asset = target_parent_asset
        self.endMoveRows()
        return True

    def createAssetRule(self, source_rule: SourceRule, new_asset_name: str, copy_from_asset: AssetRule = None) -> QModelIndex:
        """Creates a new AssetRule under the given SourceRule and returns its index."""
        if not isinstance(source_rule, SourceRule) or not new_asset_name:
            log.error("createAssetRule: Invalid SourceRule or empty asset name provided.")
            return QModelIndex()

        # Check if asset already exists under this source
        for asset in source_rule.assets:
            if asset.asset_name == new_asset_name:
                log.warning(f"createAssetRule: Asset '{new_asset_name}' already exists under '{Path(source_rule.input_path).name}'.")
                # Return existing index? Or fail? Let's return existing for now.
                try:
                    existing_row = source_rule.assets.index(asset)
                    return self.createIndex(existing_row, 0, asset)
                except ValueError:
                     log.error("createAssetRule: Found existing asset but failed to get its index.")
                     return QModelIndex()

        log.debug(f"Creating new AssetRule '{new_asset_name}' under '{Path(source_rule.input_path).name}'")
        new_asset_rule = AssetRule(asset_name=new_asset_name)
        new_asset_rule.parent_source = source_rule

        # Optionally copy type info from another asset
        if isinstance(copy_from_asset, AssetRule):
            new_asset_rule.asset_type = copy_from_asset.asset_type
            new_asset_rule.asset_type_override = copy_from_asset.asset_type_override

        # Find parent SourceRule index
        try:
            grandparent_row = self._source_rules.index(source_rule)
            grandparent_index = self.createIndex(grandparent_row, 0, source_rule)
        except ValueError:
            log.error(f"createAssetRule: Could not find SourceRule '{Path(source_rule.input_path).name}' in the model's root list.")
            return QModelIndex()

        # Determine insertion row for the new parent (e.g., append)
        new_parent_row = len(source_rule.assets)

        # Emit signals for inserting the new parent row
        self.beginInsertRows(grandparent_index, new_parent_row, new_parent_row)
        source_rule.assets.insert(new_parent_row, new_asset_rule)
        self.endInsertRows()

        # Return index for the newly created asset
        return self.createIndex(new_parent_row, 0, new_asset_rule)


    def removeAssetRule(self, asset_rule_to_remove: AssetRule):
        """Removes an AssetRule if it's empty."""
        if not isinstance(asset_rule_to_remove, AssetRule):
            log.error("removeAssetRule: Invalid AssetRule provided.")
            return False

        if asset_rule_to_remove.files:
            log.warning(f"removeAssetRule: Asset '{asset_rule_to_remove.asset_name}' is not empty. Removal aborted.")
            return False

        source_rule = getattr(asset_rule_to_remove, 'parent_source', None)
        if not source_rule:
            log.error(f"removeAssetRule: Could not find parent SourceRule for asset '{asset_rule_to_remove.asset_name}'.")
            return False

        # Find parent SourceRule index and the row of the asset to remove
        try:
            grandparent_row = self._source_rules.index(source_rule)
            grandparent_index = self.createIndex(grandparent_row, 0, source_rule)
            asset_row_for_removal = source_rule.assets.index(asset_rule_to_remove)
        except ValueError:
            log.error(f"removeAssetRule: Could not find parent SourceRule or the AssetRule within its parent's list.")
            return False

    def get_asset_type_keys(self) -> List[str]:
        """Returns the cached list of asset type keys."""
        return self._asset_type_keys

    def get_file_type_keys(self) -> List[str]:
        """Returns the cached list of file type keys."""
        return self._file_type_keys

    def findIndexForItem(self, target_item_object) -> QModelIndex | None:
        """
        Finds the QModelIndex for a given item object (SourceRule, AssetRule, or FileRule)
        by traversing the model's internal tree structure.

        Args:
            target_item_object: The specific SourceRule, AssetRule, or FileRule object to find.

        Returns:
            QModelIndex for the item if found, otherwise None.
        """
        if target_item_object is None:
            return None

        for sr_row, source_rule in enumerate(self._source_rules):
            if source_rule is target_item_object:
                return self.createIndex(sr_row, 0, source_rule)

            parent_source_rule_index = self.createIndex(sr_row, 0, source_rule)
            if not parent_source_rule_index.isValid():
                log.error(f"findIndexForItem: Could not create valid index for SourceRule: {source_rule.input_path}")
                continue


            for ar_row, asset_rule in enumerate(source_rule.assets):
                if asset_rule is target_item_object:
                    return self.index(ar_row, 0, parent_source_rule_index)

                parent_asset_rule_index = self.index(ar_row, 0, parent_source_rule_index)
                if not parent_asset_rule_index.isValid():
                    log.error(f"findIndexForItem: Could not create valid index for AssetRule: {asset_rule.asset_name}")
                    continue

                for fr_row, file_rule in enumerate(asset_rule.files):
                    if file_rule is target_item_object:
                        return self.index(fr_row, 0, parent_asset_rule_index)
        
        log.debug(f"findIndexForItem: Item {target_item_object!r} not found in the model.")
        return None

    # --- removeAssetRule continued (log.debug was separated by the insert) ---
    # This log line belongs to the removeAssetRule method defined earlier.
    # It's being re-indented here to its correct place if it was part of that method's flow.
    # However, looking at the original structure, the `return True` for removeAssetRule
    # was at line 802, and the log.debug was at 798. This indicates the log.debug
    # was likely the *start* of the problematic section in the previous attempt,
    # and the `return True` was the end of `removeAssetRule`.
    # The `log.debug` at original line 798 should be part of `removeAssetRule`'s positive path.
    # The `return True` at original line 802 should be the final return of `removeAssetRule`.

    # Correcting the end of removeAssetRule:
        log.debug(f"Removing empty AssetRule '{asset_rule_to_remove.asset_name}' at row {asset_row_for_removal} under '{Path(source_rule.input_path).name}'")
        self.beginRemoveRows(grandparent_index, asset_row_for_removal, asset_row_for_removal)
        source_rule.assets.pop(asset_row_for_removal)
        self.endRemoveRows()
        return True

    def update_status(self, source_path: str, status_text: str):
        """
        Finds the SourceRule node for the given source_path and updates its status.
        Emits dataChanged for the corresponding row.
        """
        log.debug(f"Attempting to update status for source '{source_path}' to '{status_text}'")
        found_row = -1
        found_rule = None
        for i, rule in enumerate(self._source_rules):
            if rule.input_path == source_path:
                found_row = i
                found_rule = rule
                break

        if found_rule is not None and found_row != -1:
            try:
                # Attempt to set a status attribute (e.g., _status_message)
                # Note: This attribute isn't formally defined in SourceRule structure yet.
                setattr(found_rule, '_status_message', status_text)
                log.info(f"Updated status for SourceRule '{source_path}' (row {found_row}) to '{status_text}'")

                # Emit dataChanged for the entire row to potentially trigger updates
                # (e.g., delegates, background color based on status if implemented later)
                start_index = self.createIndex(found_row, 0, found_rule)
                end_index = self.createIndex(found_row, self.columnCount() - 1, found_rule)
                self.dataChanged.emit(start_index, end_index, [Qt.DisplayRole])

            except Exception as e:
                log.exception(f"Error setting status attribute or emitting dataChanged for {source_path}: {e}")
        else:
            log.warning(f"Could not find SourceRule with path '{source_path}' to update status.")

    # --- Placeholder for node finding method (Original Request - Replaced by direct list search above) ---
    # Kept for reference, but the logic above directly searches self._source_rules

    # --- Drag and Drop Methods ---

    def supportedDropActions(self) -> Qt.DropActions:
        """Specifies that only Move actions are supported."""
        return Qt.MoveAction

    def mimeTypes(self) -> list[str]:
        """Returns the list of supported MIME types for dragging."""
        return [self.MIME_TYPE]

    def mimeData(self, indexes: list[QModelIndex]) -> QMimeData:
        """Encodes information about the dragged FileRule items."""
        mime_data = QMimeData()
        encoded_data = QByteArray()
        stream = QDataStream(encoded_data, QIODevice.OpenModeFlag.WriteOnly)

        dragged_file_info = []
        for index in indexes:
            if not index.isValid() or index.column() != 0:
                continue
            item = index.internalPointer()
            if isinstance(item, FileRule):
                parent_index = self.parent(index)
                if parent_index.isValid():
                    # Store: source_row, source_parent_row, source_grandparent_row
                    # This allows reconstructing the index later
                    grandparent_index = self.parent(parent_index)
                    # Ensure grandparent_index is valid before accessing its row
                    if grandparent_index.isValid():
                        dragged_file_info.append((index.row(), parent_index.row(), grandparent_index.row()))
                    else:
                        # Handle case where grandparent is the root (shouldn't happen for FileRule, but safety)
                        # Or if parent() failed unexpectedly
                        log.warning(f"mimeData: Could not get valid grandparent index for FileRule at row {index.row()}, parent row {parent_index.row()}")

                else:
                     log.warning(f"mimeData: Could not get parent index for FileRule at row {index.row()}")

        # Write the number of items first, then each tuple
        stream.writeInt8(len(dragged_file_info))
        for info in dragged_file_info:
            stream.writeInt8(info[0])
            stream.writeInt8(info[1])
            stream.writeInt8(info[2])

        mime_data.setData(self.MIME_TYPE, encoded_data)
        log.debug(f"mimeData: Encoded {len(dragged_file_info)} FileRule indices.")
        return mime_data

    def canDropMimeData(self, data: QMimeData, action: Qt.DropAction, row: int, column: int, parent: QModelIndex) -> bool:
        """Checks if the data can be dropped at the specified location."""
        if action != Qt.MoveAction or not data.hasFormat(self.MIME_TYPE):
            return False

        # Check if the drop target is a valid AssetRule
        if not parent.isValid():
            return False

        target_item = parent.internalPointer()
        if not isinstance(target_item, AssetRule):
            return False

        # Optional: Prevent dropping onto the original parent? (Might be confusing)
        # For now, allow dropping onto the same parent (moveFileRule handles this)

        return True

    def dropMimeData(self, data: QMimeData, action: Qt.DropAction, row: int, column: int, parent: QModelIndex) -> bool:
        """Handles the dropping of FileRule items onto an AssetRule."""
        if not self.canDropMimeData(data, action, row, column, parent):
             log.warning("dropMimeData: canDropMimeData check failed.")
             return False

        target_asset_item = parent.internalPointer()
        if not isinstance(target_asset_item, AssetRule):
             log.error("dropMimeData: Target item is not an AssetRule.")
             return False

        encoded_data = data.data(self.MIME_TYPE)
        stream = QDataStream(encoded_data, QIODevice.OpenModeFlag.ReadOnly)

        num_items = stream.readInt8()
        source_indices_info = []
        for _ in range(num_items):
            source_row = stream.readInt8()
            source_parent_row = stream.readInt8()
            source_grandparent_row = stream.readInt8()
            source_indices_info.append((source_row, source_parent_row, source_grandparent_row))

        log.debug(f"dropMimeData: Decoded {len(source_indices_info)} source indices. Target Asset: '{target_asset_item.asset_name}'")

        if not source_indices_info:
            log.warning("dropMimeData: No valid source index information decoded.")
            return False

        # Keep track of original parents that might become empty
        original_parents = set()
        moved_files_new_indices = {}

        # --- BEGIN FIX: Reconstruct all source indices BEFORE the move loop ---
        source_indices_to_process = []
        log.debug("Reconstructing initial source indices...")
        for src_row, src_parent_row, src_grandparent_row in source_indices_info:
            grandparent_index = self.index(src_grandparent_row, 0, QModelIndex())
            if not grandparent_index.isValid():
                log.error(f"dropMimeData: Failed initial reconstruction of grandparent index (row {src_grandparent_row}). Skipping item.")
                continue
            old_parent_index = self.index(src_parent_row, 0, grandparent_index)
            if not old_parent_index.isValid():
                log.error(f"dropMimeData: Failed initial reconstruction of old parent index (row {src_parent_row}). Skipping item.")
                continue
            source_file_index = self.index(src_row, 0, old_parent_index)
            if not source_file_index.isValid():
                # Log the specific parent it failed under for better debugging
                parent_name = getattr(old_parent_index.internalPointer(), 'asset_name', 'Unknown Parent')
                log.error(f"dropMimeData: Failed initial reconstruction of source file index (original row {src_row}) under parent '{parent_name}'. Skipping item.")
                continue

            # Check if the reconstructed index actually points to a FileRule
            item_check = source_file_index.internalPointer()
            if isinstance(item_check, FileRule):
                 source_indices_to_process.append(source_file_index)
                 log.debug(f"  Successfully reconstructed index for file: {Path(item_check.file_path).name}")
            else:
                 log.warning(f"dropMimeData: Initial reconstructed index (row {src_row}) does not point to a FileRule. Skipping.")

        log.debug(f"Successfully reconstructed {len(source_indices_to_process)} valid source indices.")
        # --- END FIX ---


        # Process moves using the pre-calculated valid indices
        for source_file_index in source_indices_to_process:
            # Get the file item (already validated during reconstruction)
            file_item = source_file_index.internalPointer()

            # Track original parent for cleanup (using the valid index)
            old_parent_index = self.parent(source_file_index)
            if old_parent_index.isValid():
                 old_parent_asset = old_parent_index.internalPointer()
                 if isinstance(old_parent_asset, AssetRule):
                      # Need grandparent row for the tuple key
                      grandparent_index = self.parent(old_parent_index)
                      if grandparent_index.isValid():
                           original_parents.add((grandparent_index.row(), old_parent_asset.asset_name))
                      else:
                           log.warning(f"Could not get grandparent index for original parent '{old_parent_asset.asset_name}' during cleanup tracking.")
                 else:
                      log.warning(f"Parent of file '{Path(file_item.file_path).name}' is not an AssetRule.")
            else:
                 log.warning(f"Could not get valid parent index for file '{Path(file_item.file_path).name}' during cleanup tracking.")


            # Perform the move using the model's method and the valid source_file_index
            if self.moveFileRule(source_file_index, parent):
                # --- Update Target Asset Override After Successful Move ---
                # The file_item's parent_asset reference should now be updated by moveFileRule
                new_parent_asset = getattr(file_item, 'parent_asset', None)
                if new_parent_asset == target_asset_item:
                    if file_item.target_asset_name_override != target_asset_item.asset_name:
                        log.debug(f"  Updating target override for '{Path(file_item.file_path).name}' to '{target_asset_item.asset_name}'")
                        file_item.target_asset_name_override = target_asset_item.asset_name
                        # Need the *new* index of the moved file to emit dataChanged
                        try:
                            new_row = target_asset_item.files.index(file_item)
                            new_file_index_col0 = self.index(new_row, 0, parent)
                            new_file_index_target_col = self.index(new_row, self.COL_TARGET_ASSET, parent)
                            if new_file_index_target_col.isValid():
                                 moved_files_new_indices[file_item.file_path] = new_file_index_target_col
                            else:
                                log.warning(f"  Could not get valid *new* index for target column of moved file: {Path(file_item.file_path).name}")
                        except ValueError:
                             log.error(f"  Could not find moved file '{Path(file_item.file_path).name}' in target parent's list after move.")

                else:
                     log.error(f"  Move reported success, but file's parent reference ('{getattr(new_parent_asset, 'asset_name', 'None')}') doesn't match target ('{target_asset_item.asset_name}'). Override not updated.")
            else:
                log.error(f"dropMimeData: moveFileRule failed for file '{Path(file_item.file_path).name}'.")
                # If one move fails, should we stop? For now, continue processing others.
                continue

        # --- Emit dataChanged for Target Asset column AFTER all moves ---
        for source_path, new_index in moved_files_new_indices.items():
             self.dataChanged.emit(new_index, new_index, [Qt.DisplayRole, Qt.EditRole])

        # --- Cleanup: Remove any original parent AssetRules that are now empty ---
        log.debug(f"dropMimeData: Checking original parents for cleanup: {list(original_parents)}")
        for gp_row, asset_name in list(original_parents):
            try:
                if 0 <= gp_row < len(self._source_rules):
                    source_rule = self._source_rules[gp_row]
                    # Find the asset rule within the correct source rule
                    asset_rule_to_check = next((asset for asset in source_rule.assets if asset.asset_name == asset_name), None)

                    if asset_rule_to_check and not asset_rule_to_check.files and asset_rule_to_check != target_asset_item:
                        log.info(f"dropMimeData: Attempting cleanup of now empty original parent: '{asset_rule_to_check.asset_name}'")
                        if not self.removeAssetRule(asset_rule_to_check):
                            log.warning(f"dropMimeData: Failed to remove empty original parent '{asset_rule_to_check.asset_name}'.")
                    elif not asset_rule_to_check:
                         log.warning(f"dropMimeData: Cleanup check failed. Could not find original parent asset '{asset_name}' in source rule at row {gp_row}.")
                else:
                    log.warning(f"dropMimeData: Cleanup check failed. Invalid grandparent row index {gp_row} found in original_parents set.")
            except Exception as e:
                log.exception(f"dropMimeData: Error during cleanup check for parent '{asset_name}' (gp_row {gp_row}): {e}")


        return True