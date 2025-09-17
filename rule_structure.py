import dataclasses
import json
from typing import List, Dict, Any, Tuple, Optional
import numpy as np # Added for ProcessingItem
@dataclasses.dataclass
class FileRule:
    file_path: str = None
    item_type: str = None # Base type determined by classification (e.g., MAP_COL, EXTRA)
    item_type_override: str = None # Renamed from map_type_override
    target_asset_name_override: str = None
    resolution_override: Tuple[int, int] = None
    channel_merge_instructions: Dict[str, Any] = dataclasses.field(default_factory=dict)
    output_format_override: str = None
    processing_items: List['ProcessingItem'] = dataclasses.field(default_factory=list) # Added field

    def to_json(self) -> str:
        # Need to handle ProcessingItem serialization if it contains non-serializable types like np.ndarray
        # For now, assume asdict handles it or it's handled before calling to_json for persistence.
        # A custom asdict_factory might be needed for robust serialization.
        return json.dumps(dataclasses.asdict(self), indent=4)

    @classmethod
    def from_json(cls, json_string: str) -> 'FileRule':
        data = json.loads(json_string)
        return cls(**data)

@dataclasses.dataclass
class AssetRule:
    asset_name: str = None
    asset_type: str = None # Predicted type
    asset_type_override: str = None
    common_metadata: Dict[str, Any] = dataclasses.field(default_factory=dict)
    files: List[FileRule] = dataclasses.field(default_factory=list)

    def to_json(self) -> str:
        return json.dumps(dataclasses.asdict(self), indent=4)

    @classmethod
    def from_json(cls, json_string: str) -> 'AssetRule':
        data = json.loads(json_string)
        # Manually deserialize nested FileRule objects
        data['files'] = [FileRule.from_json(json.dumps(file_data)) for file_data in data.get('files', [])]
        return cls(**data)

@dataclasses.dataclass
class SourceRule:
    supplier_identifier: str = None # Predicted/Original identifier
    supplier_override: str = None
    high_level_sorting_parameters: Dict[str, Any] = dataclasses.field(default_factory=dict)
    assets: List[AssetRule] = dataclasses.field(default_factory=list)
    input_path: str = None
    preset_name: str = None

    def to_json(self) -> str:
        return json.dumps(dataclasses.asdict(self), indent=4)

    @classmethod
    def from_json(cls, json_string: str) -> 'SourceRule':
        data = json.loads(json_string)
        # Manually deserialize nested AssetRule objects
        data['assets'] = [AssetRule.from_json(json.dumps(asset_data)) for asset_data in data.get('assets', [])]
        # Need to handle ProcessingItem deserialization if it was serialized
        # For now, from_json for FileRule doesn't explicitly handle processing_items from JSON.
        return cls(**data)

@dataclasses.dataclass
class ProcessingItem:
    """
    Represents a specific version of an image map to be processed and saved.
    This could be a standard resolution (1K, 2K), a preview, or a special
    variant like 'LOWRES'.
    """
    source_file_info_ref: str  # Reference to the original SourceFileInfo or unique ID of the source image
    map_type_identifier: str   # The internal map type (e.g., "MAP_COL", "MAP_ROUGH")
    resolution_key: str        # The resolution identifier (e.g., "1K", "PREVIEW", "LOWRES")
    image_data: np.ndarray     # The actual image data for this item
    original_dimensions: Tuple[int, int] # (width, height) of the source image for this item
    current_dimensions: Tuple[int, int]  # (width, height) of the image_data in this item
    target_filename: str = ""  # Will be populated by SaveVariantsStage
    is_extra: bool = False     # If this item should be treated as an 'extra' file
    bit_depth: Optional[int] = None
    channels: Optional[int] = None
    file_extension: Optional[str] = None # Determined during saving based on format
    processing_applied_log: List[str] = dataclasses.field(default_factory=list)
    status: str = "Pending" # e.g., Pending, Processed, Failed
    error_message: Optional[str] = None

    # __getstate__ and __setstate__ might be needed if we pickle these objects
    # and np.ndarray causes issues. For JSON, image_data would typically not be serialized.
    def __getstate__(self):
        state = self.__dict__.copy()
        # Don't pickle image_data if it's large or not needed for state
        if 'image_data' in state: # Or a more sophisticated check
            del state['image_data'] # Example: remove it
        return state

    def __setstate__(self, state):
        self.__dict__.update(state)
        # Potentially re-initialize or handle missing 'image_data'
        if 'image_data' not in self.__dict__:
             self.image_data = None # Or load it if a path was stored instead