import dataclasses # Added import
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional

from rule_structure import AssetRule, FileRule, SourceRule
from configuration import Configuration

# Imports needed for new dataclasses
import numpy as np
from typing import Any, Tuple, Union

# --- Stage Input/Output Dataclasses ---

# Item types for PrepareProcessingItemsStage output
@dataclass
class MergeTaskDefinition:
    """Represents a merge task identified by PrepareProcessingItemsStage."""
    task_data: Dict # The original task data from context.merged_image_tasks
    task_key: str   # e.g., "merged_task_0"

# Output for RegularMapProcessorStage
@dataclass
class ProcessedRegularMapData:
    processed_image_data: np.ndarray
    final_internal_map_type: str
    source_file_path: Path
    original_bit_depth: Optional[int]
    original_dimensions: Optional[Tuple[int, int]] # (width, height)
    transformations_applied: List[str]
    resolution_key: Optional[str] = None # Added field
    status: str = "Processed"
    error_message: Optional[str] = None

# Output for MergedTaskProcessorStage
@dataclass
class ProcessedMergedMapData:
    merged_image_data: np.ndarray
    output_map_type: str # Internal type
    source_bit_depths: List[int]
    final_dimensions: Optional[Tuple[int, int]] # (width, height)
    transformations_applied_to_inputs: Dict[str, List[str]] # Map type -> list of transforms
    status: str = "Processed"
    error_message: Optional[str] = None

# Input for InitialScalingStage
@dataclass
class InitialScalingInput:
    image_data: np.ndarray
    initial_scaling_mode: str # Moved before fields with defaults
    original_dimensions: Optional[Tuple[int, int]] # (width, height)
    resolution_key: Optional[str] = None # Added field
    # Configuration needed

# Output for InitialScalingStage
@dataclass
class InitialScalingOutput:
    scaled_image_data: np.ndarray
    scaling_applied: bool
    final_dimensions: Tuple[int, int] # (width, height)
    resolution_key: Optional[str] = None # Added field

# Input for SaveVariantsStage
@dataclass
class SaveVariantsInput:
    image_data: np.ndarray # Final data (potentially scaled)
    internal_map_type: str # Final internal type (e.g., MAP_ROUGH, MAP_COL-1)
    source_bit_depth_info: List[int]
    # Configuration needed
    output_filename_pattern_tokens: Dict[str, Any]
    image_resolutions: List[int]
    file_type_defs: Dict[str, Dict]
    output_format_8bit: str
    output_format_16bit_primary: str
    output_format_16bit_fallback: str
    png_compression_level: int
    jpg_quality: int
    output_filename_pattern: str
    resolution_threshold_for_jpg: Optional[int] # Added for JPG conversion

# Output for SaveVariantsStage
@dataclass
class SaveVariantsOutput:
    saved_files_details: List[Dict]
    status: str = "Processed"
    error_message: Optional[str] = None

# Add a field to AssetProcessingContext for the prepared items
@dataclass
class AssetProcessingContext:
    source_rule: SourceRule
    asset_rule: AssetRule
    workspace_path: Path
    engine_temp_dir: Path
    output_base_path: Path
    effective_supplier: Optional[str]
    asset_metadata: Dict
    processed_maps_details: Dict[str, Dict] # Will store final results per item_key
    merged_maps_details: Dict[str, Dict] # This might become redundant? Keep for now.
    files_to_process: List[FileRule]
    loaded_data_cache: Dict
    config_obj: Configuration
    status_flags: Dict
    incrementing_value: Optional[str]
    sha5_value: Optional[str] # Keep existing fields
    # New field for prepared items
    processing_items: Optional[List[Union[FileRule, MergeTaskDefinition]]] = None
    # Temporary storage during pipeline execution (managed by orchestrator)
    # Keys could be FileRule object hash/id or MergeTaskDefinition task_key
    intermediate_results: Optional[Dict[Any, Union[ProcessedRegularMapData, ProcessedMergedMapData, InitialScalingOutput]]] = None