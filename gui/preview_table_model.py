import logging
import time # For logging timestamps
from PySide6.QtCore import QAbstractTableModel, Qt, QModelIndex, QSortFilterProxyModel, QThread
from PySide6.QtGui import QColor

log = logging.getLogger(__name__)

# Define colors for alternating asset groups
COLOR_ASSET_GROUP_1 = QColor("#292929") # Dark grey 1
COLOR_ASSET_GROUP_2 = QColor("#343434") # Dark grey 2

class PreviewTableModel(QAbstractTableModel):
    """
    Custom table model for the GUI preview table.
    Holds detailed file prediction results or a simple list of source assets.
    """
    # Define text colors for statuses
    STATUS_COLORS = {
        "Mapped": QColor("#9dd9db"),
        "Ignored": QColor("#c1753d"),
        "Extra": QColor("#cfdca4"),
        "Unrecognised": QColor("#92371f"),
        "Model": QColor("#a4b8dc"),
        "Unmatched Extra": QColor("#777777"),
        "Error": QColor(Qt.GlobalColor.red),
        "[No Status]": None # Use default color for no status
    }

    # Define column roles for clarity (Detailed Mode)
    COL_STATUS = 0
    COL_PREDICTED_ASSET = 1
    COL_ORIGINAL_PATH = 2
    COL_PREDICTED_OUTPUT = 3 # Kept for internal data access, but hidden in view
    COL_DETAILS = 4
    COL_ADDITIONAL_FILES = 5 # New column for ignored/extra files

    # Define internal data roles for sorting/filtering
    ROLE_RAW_STATUS = Qt.ItemDataRole.UserRole + 1
    ROLE_SOURCE_ASSET = Qt.ItemDataRole.UserRole + 2

    # Column for Simple Mode
    COL_SIMPLE_PATH = 0

    def __init__(self, data=None, parent=None):
        super().__init__(parent)
        log.debug("PreviewTableModel initialized.")
        # Data format: List of dictionaries, each representing a file's details
        # Example: {'original_path': '...', 'predicted_asset_name': '...', 'predicted_output_name': '...', 'status': '...', 'details': '...', 'source_asset': '...'}
        self._data = [] # Keep the original flat data for reference if needed, but not for display
        self._table_rows = [] # New structure for displaying rows
        self._simple_data = [] # List of unique source asset paths for simple mode
        self._simple_mode = False # Flag to toggle between detailed and simple view
        self._headers_detailed = ["Status", "Predicted Asset", "Original Path", "Predicted Output", "Details", "Additional Files"] # Added new column header
        self._sorted_unique_assets = [] # Store sorted unique asset names for coloring
        self._headers_simple = ["Input Path"]
        self.set_data(data or [])

    def set_simple_mode(self, enabled: bool):
        """Toggles the model between detailed and simple view modes."""
        thread_id = QThread.currentThread()
        log.info(f"[{time.time():.4f}][T:{thread_id}] --> Entered PreviewTableModel.set_simple_mode(enabled={enabled}). Current mode: {self._simple_mode}")
        if self._simple_mode != enabled:
            log.info(f"[{time.time():.4f}][T:{thread_id}]     Calling beginResetModel()...")
            self.beginResetModel()
            log.info(f"[{time.time():.4f}][T:{thread_id}]     Returned from beginResetModel(). Setting mode.")
            self._simple_mode = enabled
            log.info(f"[{time.time():.4f}][T:{thread_id}]     Mode changed to: {self._simple_mode}. Calling endResetModel()...")
            self.endResetModel()
            log.info(f"[{time.time():.4f}][T:{thread_id}]     Returned from endResetModel().")
        else:
            log.info(f"[{time.time():.4f}][T:{thread_id}]     PreviewTableModel mode is already as requested. No change.")
        log.info(f"[{time.time():.4f}][T:{thread_id}] <-- Exiting PreviewTableModel.set_simple_mode.")


    def rowCount(self, parent=QModelIndex()):
        """Returns the number of rows in the model."""
        if parent.isValid():
            return 0
        row_count = len(self._simple_data) if self._simple_mode else len(self._table_rows) # Use _table_rows for detailed mode
        return row_count

    def columnCount(self, parent=QModelIndex()):
        """Returns the number of columns in the model."""
        if parent.isValid():
            return 0
        col_count = len(self._headers_simple) if self._simple_mode else len(self._headers_detailed) # Use updated headers_detailed
        return col_count

    def data(self, index: QModelIndex, role: int = Qt.ItemDataRole.DisplayRole):
        """Returns the data for a given index and role."""
        if not index.isValid():
            return None

        row = index.row()
        col = index.column()

        # --- Simple Mode ---
        if self._simple_mode:
            if row >= len(self._simple_data):
                return None
            source_asset_path = self._simple_data[row]
            if role == Qt.ItemDataRole.DisplayRole:
                if col == self.COL_SIMPLE_PATH:
                    return source_asset_path
            elif role == Qt.ItemDataRole.ToolTipRole:
                 if col == self.COL_SIMPLE_PATH:
                     return f"Input Asset: {source_asset_path}"
            return None

        # --- Detailed Mode ---
        if row >= len(self._table_rows): # Use _table_rows
            return None
        row_data = self._table_rows[row] # Get data from the structured row

        # --- Handle Custom Internal Roles ---
        if role == self.ROLE_RAW_STATUS:
             # Return status of the main file if it exists, otherwise a placeholder for additional rows
             main_file = row_data.get('main_file')
             return main_file.get('status', '[No Status]') if main_file else '[Additional]'
        if role == self.ROLE_SOURCE_ASSET:
            return row_data.get('source_asset', 'N/A')

        # --- Handle Display Role ---
        if role == Qt.ItemDataRole.DisplayRole:
            if col == self.COL_STATUS:
                main_file = row_data.get('main_file')
                if main_file:
                    raw_status = main_file.get('status', '[No Status]')
                    details = main_file.get('details', '')

                    # Implement status text simplification
                    if raw_status == "Unmatched Extra":
                        if details and details.startswith("[Unmatched Extra (Regex match:"):
                            try:
                                pattern = details.split("match: '")[1].split("'")[0]
                                return f"[Extra={pattern}]"
                            except IndexError:
                                return "Extra" # Fallback if parsing fails
                        else:
                            return "Extra"
                    elif raw_status == "Ignored" and details and "Superseed by 16bit variant for" in details:
                         try:
                             filename = details.split("Superseed by 16bit variant for ")[1]
                             return f"Superseeded by 16bit {filename}"
                         except IndexError:
                             return raw_status # Fallback if parsing fails
                    else:
                        return raw_status # Return original status if no simplification applies
                else:
                    return "" # Empty for additional-only rows

            elif col == self.COL_PREDICTED_ASSET:
                main_file = row_data.get('main_file')
                return main_file.get('predicted_asset_name', 'N/A') if main_file else ""
            elif col == self.COL_ORIGINAL_PATH:
                main_file = row_data.get('main_file')
                return main_file.get('original_path', '[Missing Path]') if main_file else ""
            elif col == self.COL_PREDICTED_OUTPUT:
                main_file = row_data.get('main_file')
                return main_file.get('predicted_output_name', '') if main_file else ""
            elif col == self.COL_DETAILS:
                main_file = row_data.get('main_file')
                return main_file.get('details', '') if main_file else ""
            elif col == self.COL_ADDITIONAL_FILES:
                return row_data.get('additional_file_path', '')
            return None # Should not happen with defined columns

        # --- Handle Tooltip Role ---
        if role == Qt.ItemDataRole.ToolTipRole:
             if col == self.COL_ORIGINAL_PATH:
                 main_file = row_data.get('main_file')
                 if main_file:
                     source_asset = row_data.get('source_asset', 'N/A')
                     original_path = main_file.get('original_path', '[Missing Path]')
                     return f"Source Asset: {source_asset}\nFull Path: {original_path}"
                 else:
                     return "" # No tooltip for empty cells
             elif col == self.COL_STATUS:
                 main_file = row_data.get('main_file')
                 if main_file:
                     return main_file.get('details', main_file.get('status', '[No Status]'))
                 else:
                     return "" # No tooltip for empty cells
             elif col == self.COL_PREDICTED_ASSET:
                 main_file = row_data.get('main_file')
                 if main_file:
                     predicted_asset_name = main_file.get('predicted_asset_name', 'None')
                     return f"Predicted Asset Name: {predicted_asset_name}"
                 else:
                     return "" # No tooltip for empty cells
             elif col == self.COL_PREDICTED_OUTPUT:
                 main_file = row_data.get('main_file')
                 if main_file:
                     predicted_output_name = main_file.get('predicted_output_name', 'None')
                     return f"Predicted Output Name: {predicted_output_name}"
                 else:
                     return "" # No tooltip for empty cells
             elif col == self.COL_DETAILS:
                 main_file = row_data.get('main_file')
                 if main_file:
                     return main_file.get('details', '')
                 else:
                     return "" # No tooltip for empty cells
             elif col == self.COL_ADDITIONAL_FILES:
                 additional_file = row_data.get('additional_file_details')
                 if additional_file:
                     status = additional_file.get('status', '[No Status]')
                     details = additional_file.get('details', '')
                     return f"Status: {status}\nDetails: {details}"
                 else:
                     return "" # No tooltip if no additional file in this cell
             return None

        # --- Handle Foreground (Text Color) Role ---
        if role == Qt.ItemDataRole.ForegroundRole:
            row_data = self._table_rows[row] # Get data from the structured row
            status = None

            # Determine the relevant status based on column and row data
            if col in [self.COL_STATUS, self.COL_PREDICTED_ASSET, self.COL_ORIGINAL_PATH, self.COL_PREDICTED_OUTPUT, self.COL_DETAILS]:
                # These columns relate to the main file
                main_file = row_data.get('main_file')
                if main_file:
                    status = main_file.get('status', '[No Status]')
            elif col == self.COL_ADDITIONAL_FILES:
                # This column relates to the additional file
                additional_file = row_data.get('additional_file_details')
                if additional_file:
                    status = additional_file.get('status', '[No Status]')

            # Look up color based on determined status
            if status in self.STATUS_COLORS:
                 return self.STATUS_COLORS[status]
            else:
                return None # Use default text color if no specific status color or no relevant file data

        # --- Handle Background Role ---
        if role == Qt.ItemDataRole.BackgroundRole:
            # Apply alternating background color based on asset group
            source_asset = row_data.get('source_asset')
            if source_asset and source_asset in self._sorted_unique_assets:
                try:
                    asset_index = self._sorted_unique_assets.index(source_asset)
                    if asset_index % 2 == 0:
                        return COLOR_ASSET_GROUP_1
                    else:
                        return COLOR_ASSET_GROUP_2
                except ValueError:
                    # Should not happen if logic is correct, but handle defensively
                    log.warning(f"Asset '{source_asset}' not found in _sorted_unique_assets.")
                    return None # Use default background
            return None # Use default background for rows without a source asset


        # --- Handle Text Alignment Role ---
        if role == Qt.ItemDataRole.TextAlignmentRole:
            if col == self.COL_ORIGINAL_PATH:
                return int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
            elif col == self.COL_ADDITIONAL_FILES:
                return int(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            # For other columns, return default alignment (or None)
            return None




        return None

    def headerData(self, section: int, orientation: Qt.Orientation, role: int = Qt.ItemDataRole.DisplayRole):
        """Returns the header data for a given section, orientation, and role."""
        if role == Qt.ItemDataRole.DisplayRole and orientation == Qt.Orientation.Horizontal:
            headers = self._headers_simple if self._simple_mode else self._headers_detailed
            if 0 <= section < len(headers):
                return headers[section]
        return None

    def set_data(self, data: list):
        """Sets the model's data, extracts simple data, and emits signals."""
        # Removed diagnostic import here
        thread_id = QThread.currentThread()
        log.info(f"[{time.time():.4f}][T:{thread_id}] --> Entered PreviewTableModel.set_data. Received {len(data)} items.")
        log.info(f"[{time.time():.4f}][T:{thread_id}]     Calling beginResetModel()...")
        self.beginResetModel()
        log.info(f"[{time.time():.4f}][T:{thread_id}]     Returned from beginResetModel(). Processing data...")
        self._data = data or [] # Keep original data for reference if needed
        self._table_rows = [] # Clear previous structured data

        # Group files by source asset
        grouped_data = {}
        unique_sources = set()
        if data and isinstance(data[0], dict): # Ensure data is in detailed format
            for file_details in data:
                source_asset = file_details.get('source_asset')
                if source_asset:
                    if source_asset not in grouped_data:
                        grouped_data[source_asset] = {'main_files': [], 'additional_files': []}
                        unique_sources.add(source_asset)

                    status = file_details.get('status')
                    # Separate into main and additional files based on status
                    if status in ["Mapped", "Model", "Error"]:
                        grouped_data[source_asset]['main_files'].append(file_details)
                    else: # Ignored, Extra, Unrecognised, Unmatched Extra
                        grouped_data[source_asset]['additional_files'].append(file_details)

        # Sort main and additional files within each group (e.g., by original_path)
        for asset_data in grouped_data.values():
            asset_data['main_files'].sort(key=lambda x: x.get('original_path', ''))
            asset_data['additional_files'].sort(key=lambda x: x.get('original_path', '')) # Sort additional by their path

        # Build the _table_rows structure
        sorted_assets = sorted(list(unique_sources)) # Sort assets alphabetically
        for asset_name in sorted_assets:
            asset_data = grouped_data[asset_name]
            main_files = asset_data['main_files']
            additional_files = asset_data['additional_files']
            max_rows = max(len(main_files), len(additional_files))

            for i in range(max_rows):
                main_file = main_files[i] if i < len(main_files) else None
                additional_file = additional_files[i] if i < len(additional_files) else None

                row_data = {
                    'source_asset': asset_name,
                    'main_file': main_file, # Store the full dict for easy access
                    'additional_file_path': additional_file.get('original_path', '') if additional_file else '',
                    'additional_file_details': additional_file, # Store full dict for tooltip
                    'is_main_row': main_file is not None # True if this row has a main file
                }
                self._table_rows.append(row_data)

       # Store sorted unique asset paths for simple mode and coloring
        self._sorted_unique_assets = sorted(list(unique_sources))
        self._simple_data = self._sorted_unique_assets # Simple data is just the sorted unique assets


        log.info(f"[{time.time():.4f}][T:{thread_id}]     Structured data built: {len(self._table_rows)} rows.")
        log.info(f"[{time.time():.4f}][T:{thread_id}]     Simple data extracted: {len(self._simple_data)} unique sources.")
        log.info(f"[{time.time():.4f}][T:{thread_id}]     Calling endResetModel()...")
        self.endResetModel()
        log.info(f"[{time.time():.4f}][T:{thread_id}]     Returned from endResetModel().")
        log.info(f"[{time.time():.4f}][T:{thread_id}] <-- Exiting PreviewTableModel.set_data.")

    def clear_data(self):
        """Clears the model's data."""
        thread_id = QThread.currentThread()
        log.info(f"[{time.time():.4f}][T:{thread_id}] PreviewTableModel.clear_data called.")
        self.set_data([])


class PreviewSortFilterProxyModel(QSortFilterProxyModel):
    """
    Custom proxy model for sorting the preview table.
    Implements multi-level sorting and custom status order.
    """
    # Define the desired status priority for sorting
    # Lower numbers sort first. Mapped/Model have same priority.
    STATUS_PRIORITY = {
        "Error": 0,
        "Mapped": 1,
        "Model": 1,
        "Ignored": 2,
        "Extra": 3,
        "Unrecognised": 3, # Treat as Extra
        "Unmatched Extra": 3, # Treat as Extra
        "[No Status]": 99 # Lowest priority
    }

    def __init__(self, parent=None):
        super().__init__(parent)
        log.debug("PreviewSortFilterProxyModel initialized.")
        # Set default sort column and order (Status column, Ascending)
        # This will be overridden by the custom lessThan logic
        self.setSortRole(PreviewTableModel.ROLE_RAW_STATUS) # Sort using the raw status role
        self.sort(PreviewTableModel.COL_STATUS, Qt.SortOrder.AscendingOrder) # Apply initial sort

    def lessThan(self, left: QModelIndex, right: QModelIndex):
        """
        Custom comparison logic for multi-level sorting.
        Sorts by:
        1. Source Asset (Ascending)
        2. Status (Custom Order: Error > Mapped/Model > Ignored > Extra)
        3. Original Path (Ascending)
        """
        model = self.sourceModel()
        if not model:
            return super().lessThan(left, right) # Fallback if no source model

        # If in simple mode, sort by the simple path column
        if isinstance(model, PreviewTableModel) and model._simple_mode:
             left_path = model.data(left.siblingAtColumn(model.COL_SIMPLE_PATH), Qt.ItemDataRole.DisplayRole)
             right_path = model.data(right.siblingAtColumn(model.COL_SIMPLE_PATH), Qt.ItemDataRole.DisplayRole)
             if not left_path: return True
             if not right_path: return False
             return left_path < right_path


        # --- Detailed Mode Sorting ---
        # Get the full row data from the source model's _table_rows
        left_row_data = model._table_rows[left.row()]
        right_row_data = model._table_rows[right.row()]

        # --- Level 1: Sort by Source Asset ---
        left_asset = left_row_data.get('source_asset', 'N/A')
        right_asset = right_row_data.get('source_asset', 'N/A')

        if left_asset != right_asset:
            # Handle None/empty strings for consistent sorting
            if not left_asset or left_asset == 'N/A': return True # Empty asset comes first
            if not right_asset or right_asset == 'N/A': return False # Non-empty asset comes first
            return left_asset < right_asset # Alphabetical sort for assets

        # --- Level 2: Sort by Row Type (Main vs Additional-only) ---
        # Main rows (is_main_row == True) should come before additional-only rows
        left_is_main = left_row_data.get('is_main_row', False)
        right_is_main = right_row_data.get('is_main_row', False)

        if left_is_main != right_is_main:
            return left_is_main > right_is_main # True > False

        # --- Level 3: Sort within the row type ---
        if left_is_main: # Both are main rows
            # Sort by Original Path (Alphabetical)
            left_path = left_row_data.get('main_file', {}).get('original_path', '')
            right_path = right_row_data.get('main_file', {}).get('original_path', '')

            if not left_path: return True
            if not right_path: return False
            return left_path < right_path

        else: # Both are additional-only rows
            # Sort by Additional File Path (Alphabetical)
            left_additional_path = left_row_data.get('additional_file_path', '')
            right_additional_path = right_row_data.get('additional_file_path', '')

            if not left_additional_path: return True
            if not right_additional_path: return False
            return left_additional_path < right_additional_path

        # Should not reach here if logic is correct, but include a fallback
        return super().lessThan(left, right)

    # Override sort method to ensure custom sorting is used
    def sort(self, column: int, order: Qt.SortOrder = Qt.SortOrder.AscendingOrder):
        # We ignore the column and order here and rely on lessThan for multi-level sort
        # However, calling this method is necessary to trigger the proxy model's sorting mechanism.
        # We can potentially use the column/order to toggle ascending/descending within each level in lessThan,
        # but for now, we'll stick to the defined order.
        log.debug(f"ProxyModel.sort called with column {column}, order {order}. Triggering lessThan.")
        # Call base class sort to trigger update. Pass a valid column, e.g., COL_STATUS,
        # as the actual sorting logic is in lessThan.
        super().sort(PreviewTableModel.COL_STATUS, Qt.SortOrder.AscendingOrder)