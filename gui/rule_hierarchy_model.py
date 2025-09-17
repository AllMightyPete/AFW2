from PySide6.QtCore import QAbstractItemModel, QModelIndex, Qt, Signal, Slot
from PySide6.QtGui import QIcon # Assuming we might want icons later
from rule_structure import SourceRule, AssetRule, FileRule

class RuleHierarchyModel(QAbstractItemModel):
    """
    A custom model for displaying the hierarchical structure of SourceRule,
    AssetRule, and FileRule objects in a QTreeView.
    """
    def __init__(self, root_rule: SourceRule = None, parent=None):
        super().__init__(parent)
        self._root_rule = root_rule

    def set_root_rule(self, root_rule: SourceRule):
        """Sets the root SourceRule for the model and resets the model."""
        self.beginResetModel()
        self._root_rule = root_rule
        self.endResetModel()

    def rowCount(self, parent: QModelIndex = QModelIndex()):
        """Returns the number of rows (children) for the given parent index."""
        if not parent.isValid():
            # Root item (SourceRule)
            return 1 if self._root_rule else 0
        else:
            parent_item = parent.internalPointer()
            if isinstance(parent_item, SourceRule):
                # Children of SourceRule are AssetRules
                return len(parent_item.assets)
            elif isinstance(parent_item, AssetRule):
                # Children of AssetRule are FileRules
                return len(parent_item.files)
            elif isinstance(parent_item, FileRule):
                # FileRules have no children
                return 0
            else:
                return 0

    def columnCount(self, parent: QModelIndex = QModelIndex()):
        """Returns the number of columns."""
        return 1 # We only need one column for the hierarchy name

    def data(self, index: QModelIndex, role: int = Qt.ItemDataRole.DisplayRole):
        """Returns the data for the given index and role."""
        if not index.isValid():
            return None

        item = index.internalPointer()

        if role == Qt.ItemDataRole.DisplayRole:
            if isinstance(item, SourceRule):
                return f"Source: {item.input_path}" # Or some other identifier
            elif isinstance(item, AssetRule):
                return f"Asset: {item.asset_name}" # Or some other identifier
            elif isinstance(item, FileRule):
                return f"File: {item.file_path}" # Or some other identifier
            else:
                return None
        # Add other roles as needed (e.g., Qt.ItemDataRole.DecorationRole for icons)

        return None

    def index(self, row: int, column: int, parent: QModelIndex = QModelIndex()):
        """Returns the model index for the given row, column, and parent index."""
        if not self.hasIndex(row, column, parent):
            return QModelIndex()

        if not parent.isValid():
            # Requesting index for the root item (SourceRule)
            if self._root_rule and row == 0:
                return self.createIndex(row, column, self._root_rule)
            else:
                return QModelIndex()
        else:
            parent_item = parent.internalPointer()
            if isinstance(parent_item, SourceRule):
                # Children are AssetRules
                if 0 <= row < len(parent_item.assets):
                    child_item = parent_item.assets[row]
                    return self.createIndex(row, column, child_item)
                else:
                    return QModelIndex()
            elif isinstance(parent_item, AssetRule):
                # Children are FileRules
                if 0 <= row < len(parent_item.files):
                    child_item = parent_item.files[row]
                    return self.createIndex(row, column, child_item)
                else:
                    return QModelIndex()
            else:
                return QModelIndex() # Should not happen for FileRule parents

    def parent(self, index: QModelIndex):
        """Returns the parent index for the given index."""
        if not index.isValid():
            return QModelIndex()

        child_item = index.internalPointer()

        if isinstance(child_item, SourceRule):
            # SourceRule is the root, has no parent in the model hierarchy
            return QModelIndex()
        elif isinstance(child_item, AssetRule):
            # Find the SourceRule that contains this AssetRule
            if self._root_rule and child_item in self._root_rule.assets:
                 # The row of the SourceRule is always 0 in this model
                 return self.createIndex(0, 0, self._root_rule)
            else:
                 return QModelIndex() # Should not happen if data is consistent
        elif isinstance(child_item, FileRule):
            # Find the AssetRule that contains this FileRule
            if self._root_rule:
                for asset_row, asset_rule in enumerate(self._root_rule.assets):
                    if child_item in asset_rule.files:
                        # The row of the parent AssetRule within the SourceRule's children
                        return self.createIndex(asset_row, 0, asset_rule)
            return QModelIndex() # Should not happen if data is consistent
        else:
            return QModelIndex() # Unknown item type

    def headerData(self, section: int, orientation: Qt.Orientation, role: int = Qt.ItemDataRole.DisplayRole):
        """Returns the data for the header."""
        if orientation == Qt.Orientation.Horizontal and role == Qt.ItemDataRole.DisplayRole:
            if section == 0:
                return "Hierarchy"
        return None

    def get_item_from_index(self, index: QModelIndex):
        """Helper to get the underlying rule object from a model index."""
        if index.isValid():
            return index.internalPointer()
        return None

if __name__ == '__main__':
    # Example Usage (for testing the model)
    from PySide6.QtWidgets import QApplication, QTreeView
    from dataclasses import dataclass, field

    # Define placeholder rule structures if not imported
    @dataclass
    class FileRule:
        name: str = "file"
        setting_f1: str = "value1"
        setting_f2: int = 10

    @dataclass
    class AssetRule:
        name: str = "asset"
        files: list[FileRule] = field(default_factory=list)
        setting_a1: bool = True
        setting_a2: float = 3.14

    @dataclass
    class SourceRule:
        name: str = "source"
        assets: list[AssetRule] = field(default_factory=list)
        setting_s1: str = "hello"

    # Create a sample hierarchical structure
    file1 = FileRule(name="texture_diffuse.png")
    file2 = FileRule(name="texture_normal.png")
    file3 = FileRule(name="model.obj")

    asset1 = AssetRule(name="Material_01", files=[file1, file2])
    asset2 = AssetRule(name="Model_01", files=[file3])

    source_rule_instance = SourceRule(name="Input_Archive", assets=[asset1, asset2])

    app = QApplication([])
    tree_view = QTreeView()
    model = RuleHierarchyModel(source_rule_instance)
    tree_view.setModel(model)
    tree_view.setWindowTitle("Rule Hierarchy Example")
    tree_view.show()
    app.exec()