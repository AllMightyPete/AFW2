import pytest
from unittest import mock
from pathlib import Path
import uuid
import numpy as np
import logging # Added for mocking logger

from processing.pipeline.stages.normal_map_green_channel import NormalMapGreenChannelStage
from processing.pipeline.asset_context import AssetProcessingContext
from rule_structure import AssetRule, SourceRule, FileRule
from configuration import Configuration, GeneralSettings

# Helper functions
def create_mock_file_rule_for_normal_test(
    id_val: uuid.UUID = None, # Corrected type hint from Optional[uuid.UUID]
    map_type: str = "NORMAL", 
    filename_pattern: str = "normal.png"
) -> mock.MagicMock:
    mock_fr = mock.MagicMock(spec=FileRule)
    mock_fr.id = id_val if id_val else uuid.uuid4()
    mock_fr.map_type = map_type
    mock_fr.filename_pattern = filename_pattern
    mock_fr.item_type = "MAP_COL" # As per example, though not directly used by stage
    mock_fr.active = True # As per example
    return mock_fr

def create_normal_map_mock_context(
    initial_file_rules: list = None, # Corrected type hint
    initial_processed_details: dict = None, # Corrected type hint
    invert_green_globally: bool = False,
    skip_asset_flag: bool = False,
    asset_name: str = "NormalMapAsset"
) -> AssetProcessingContext:
    mock_asset_rule = mock.MagicMock(spec=AssetRule)
    mock_asset_rule.name = asset_name
    
    mock_source_rule = mock.MagicMock(spec=SourceRule)
    
    mock_gs = mock.MagicMock(spec=GeneralSettings)
    mock_gs.invert_normal_map_green_channel_globally = invert_green_globally 
    
    mock_config = mock.MagicMock(spec=Configuration)
    mock_config.general_settings = mock_gs

    context = AssetProcessingContext(
        source_rule=mock_source_rule,
        asset_rule=mock_asset_rule,
        workspace_path=Path("/fake/workspace"),
        engine_temp_dir=Path("/fake/temp_engine_dir"),
        output_base_path=Path("/fake/output"),
        effective_supplier="ValidSupplier",
        asset_metadata={'asset_name': asset_name},
        processed_maps_details=initial_processed_details if initial_processed_details is not None else {},
        merged_maps_details={},
        files_to_process=list(initial_file_rules) if initial_file_rules else [],
        loaded_data_cache={},
        config_obj=mock_config,
        status_flags={'skip_asset': skip_asset_flag},
        incrementing_value=None, # Added as per AssetProcessingContext constructor
        sha5_value=None # Added as per AssetProcessingContext constructor
    )
    return context

# Unit tests will be added below
@mock.patch('processing.pipeline.stages.normal_map_green_channel.ipu.save_image')
@mock.patch('processing.pipeline.stages.normal_map_green_channel.ipu.load_image')
def test_asset_skipped(mock_load_image, mock_save_image):
    stage = NormalMapGreenChannelStage()
    normal_fr = create_mock_file_rule_for_normal_test(map_type="NORMAL")
    initial_details = {
        normal_fr.id.hex: {'temp_processed_file': '/fake/temp_engine_dir/processed_normal.png', 'status': 'Processed', 'map_type': 'NORMAL', 'notes': ''}
    }
    context = create_normal_map_mock_context(
        initial_file_rules=[normal_fr],
        initial_processed_details=initial_details,
        invert_green_globally=True,
        skip_asset_flag=True # Asset is skipped
    )
    original_details = context.processed_maps_details.copy()

    updated_context = stage.execute(context)

    mock_load_image.assert_not_called()
    mock_save_image.assert_not_called()
    assert updated_context.processed_maps_details == original_details
    assert normal_fr in updated_context.files_to_process # Ensure rule is still there

@mock.patch('processing.pipeline.stages.normal_map_green_channel.ipu.save_image')
@mock.patch('processing.pipeline.stages.normal_map_green_channel.ipu.load_image')
def test_no_normal_map_present(mock_load_image, mock_save_image):
    stage = NormalMapGreenChannelStage()
    # Create a non-normal map rule
    diffuse_fr = create_mock_file_rule_for_normal_test(map_type="DIFFUSE", filename_pattern="diffuse.png")
    initial_details = {
        diffuse_fr.id.hex: {'temp_processed_file': '/fake/temp_engine_dir/processed_diffuse.png', 'status': 'Processed', 'map_type': 'DIFFUSE', 'notes': ''}
    }
    context = create_normal_map_mock_context(
        initial_file_rules=[diffuse_fr],
        initial_processed_details=initial_details,
        invert_green_globally=True # Inversion enabled, but no normal map
    )
    original_details = context.processed_maps_details.copy()

    updated_context = stage.execute(context)

    mock_load_image.assert_not_called()
    mock_save_image.assert_not_called()
    assert updated_context.processed_maps_details == original_details
    assert diffuse_fr in updated_context.files_to_process

@mock.patch('processing.pipeline.stages.normal_map_green_channel.ipu.save_image')
@mock.patch('processing.pipeline.stages.normal_map_green_channel.ipu.load_image')
def test_normal_map_present_inversion_disabled(mock_load_image, mock_save_image):
    stage = NormalMapGreenChannelStage()
    normal_rule_id = uuid.uuid4()
    normal_fr = create_mock_file_rule_for_normal_test(id_val=normal_rule_id, map_type="NORMAL")
    initial_details = {
        normal_fr.id.hex: {'temp_processed_file': '/fake/temp_engine_dir/processed_normal.png', 'status': 'Processed', 'map_type': 'NORMAL', 'notes': 'Initial note'}
    }
    context = create_normal_map_mock_context(
        initial_file_rules=[normal_fr],
        initial_processed_details=initial_details,
        invert_green_globally=False # Inversion disabled
    )
    original_details_entry = context.processed_maps_details[normal_fr.id.hex].copy()

    updated_context = stage.execute(context)

    mock_load_image.assert_not_called()
    mock_save_image.assert_not_called()
    assert updated_context.processed_maps_details[normal_fr.id.hex] == original_details_entry
    assert normal_fr in updated_context.files_to_process

@mock.patch('processing.pipeline.stages.normal_map_green_channel.ipu.save_image')
@mock.patch('processing.pipeline.stages.normal_map_green_channel.ipu.load_image')
@mock.patch('logging.info')
@mock.patch('logging.debug')
def test_normal_map_inversion_uint8_success(mock_log_debug, mock_log_info, mock_load_image, mock_save_image):
    stage = NormalMapGreenChannelStage()
    
    normal_rule_id = uuid.uuid4()
    normal_fr = create_mock_file_rule_for_normal_test(id_val=normal_rule_id, map_type="NORMAL")
    
    initial_temp_path = Path('/fake/temp_engine_dir/processed_normal.png')
    initial_details = {
        normal_fr.id.hex: {'temp_processed_file': str(initial_temp_path), 'status': 'Processed', 'map_type': 'NORMAL', 'notes': 'Initial note'}
    }
    context = create_normal_map_mock_context(
        initial_file_rules=[normal_fr],
        initial_processed_details=initial_details,
        invert_green_globally=True # Enable inversion
    )

    # R=10, G=50, B=100
    mock_loaded_normal_data = np.array([[[10, 50, 100]]], dtype=np.uint8) 
    mock_load_image.return_value = mock_loaded_normal_data
    mock_save_image.return_value = True # Simulate successful save
    
    updated_context = stage.execute(context)
    
    mock_load_image.assert_called_once_with(initial_temp_path)
    
    # Check that save_image was called with green channel inverted
    assert mock_save_image.call_count == 1
    saved_path_arg, saved_data_arg = mock_save_image.call_args[0]
    
    assert saved_data_arg[0,0,0] == 10 # R unchanged
    assert saved_data_arg[0,0,1] == 255 - 50 # G inverted
    assert saved_data_arg[0,0,2] == 100 # B unchanged
    
    assert isinstance(saved_path_arg, Path)
    assert "normal_g_inv_" in saved_path_arg.name
    assert saved_path_arg.parent == initial_temp_path.parent # Should be in same temp dir

    normal_detail = updated_context.processed_maps_details[normal_fr.id.hex]
    assert "normal_g_inv_" in normal_detail['temp_processed_file']
    assert Path(normal_detail['temp_processed_file']).name == saved_path_arg.name
    assert "Green channel inverted" in normal_detail['notes']
    assert "Initial note" in normal_detail['notes'] # Check existing notes preserved
    
    assert normal_fr in updated_context.files_to_process

@mock.patch('processing.pipeline.stages.normal_map_green_channel.ipu.save_image')
@mock.patch('processing.pipeline.stages.normal_map_green_channel.ipu.load_image')
@mock.patch('logging.info')
@mock.patch('logging.debug')
def test_normal_map_inversion_float_success(mock_log_debug, mock_log_info, mock_load_image, mock_save_image):
    stage = NormalMapGreenChannelStage()
    normal_rule_id = uuid.uuid4()
    normal_fr = create_mock_file_rule_for_normal_test(id_val=normal_rule_id, map_type="NORMAL")
    initial_temp_path = Path('/fake/temp_engine_dir/processed_normal_float.png')
    initial_details = {
        normal_fr.id.hex: {'temp_processed_file': str(initial_temp_path), 'status': 'Processed', 'map_type': 'NORMAL', 'notes': 'Float image'}
    }
    context = create_normal_map_mock_context(
        initial_file_rules=[normal_fr],
        initial_processed_details=initial_details,
        invert_green_globally=True
    )

    # R=0.1, G=0.25, B=0.75
    mock_loaded_normal_data = np.array([[[0.1, 0.25, 0.75]]], dtype=np.float32)
    mock_load_image.return_value = mock_loaded_normal_data
    mock_save_image.return_value = True

    updated_context = stage.execute(context)

    mock_load_image.assert_called_once_with(initial_temp_path)
    
    assert mock_save_image.call_count == 1
    saved_path_arg, saved_data_arg = mock_save_image.call_args[0]

    assert np.isclose(saved_data_arg[0,0,0], 0.1) # R unchanged
    assert np.isclose(saved_data_arg[0,0,1], 1.0 - 0.25) # G inverted
    assert np.isclose(saved_data_arg[0,0,2], 0.75) # B unchanged
    
    assert "normal_g_inv_" in saved_path_arg.name
    normal_detail = updated_context.processed_maps_details[normal_fr.id.hex]
    assert "normal_g_inv_" in normal_detail['temp_processed_file']
    assert "Green channel inverted" in normal_detail['notes']
    assert "Float image" in normal_detail['notes']
    assert normal_fr in updated_context.files_to_process

@mock.patch('processing.pipeline.stages.normal_map_green_channel.ipu.save_image')
@mock.patch('processing.pipeline.stages.normal_map_green_channel.ipu.load_image')
@mock.patch('logging.error')
def test_load_image_fails(mock_log_error, mock_load_image, mock_save_image):
    stage = NormalMapGreenChannelStage()
    normal_rule_id = uuid.uuid4()
    normal_fr = create_mock_file_rule_for_normal_test(id_val=normal_rule_id, map_type="NORMAL")
    initial_temp_path_str = '/fake/temp_engine_dir/processed_normal_load_fail.png'
    initial_details = {
        normal_fr.id.hex: {'temp_processed_file': initial_temp_path_str, 'status': 'Processed', 'map_type': 'NORMAL', 'notes': 'Load fail test'}
    }
    context = create_normal_map_mock_context(
        initial_file_rules=[normal_fr],
        initial_processed_details=initial_details,
        invert_green_globally=True
    )
    original_details_entry = context.processed_maps_details[normal_fr.id.hex].copy()

    mock_load_image.return_value = None # Simulate load failure

    updated_context = stage.execute(context)

    mock_load_image.assert_called_once_with(Path(initial_temp_path_str))
    mock_save_image.assert_not_called()
    mock_log_error.assert_called_once()
    assert f"Failed to load image {Path(initial_temp_path_str)} for green channel inversion." in mock_log_error.call_args[0][0]
    
    # Details should be unchanged
    assert updated_context.processed_maps_details[normal_fr.id.hex] == original_details_entry
    assert normal_fr in updated_context.files_to_process

@mock.patch('processing.pipeline.stages.normal_map_green_channel.ipu.save_image')
@mock.patch('processing.pipeline.stages.normal_map_green_channel.ipu.load_image')
@mock.patch('logging.error')
def test_save_image_fails(mock_log_error, mock_load_image, mock_save_image):
    stage = NormalMapGreenChannelStage()
    normal_rule_id = uuid.uuid4()
    normal_fr = create_mock_file_rule_for_normal_test(id_val=normal_rule_id, map_type="NORMAL")
    initial_temp_path = Path('/fake/temp_engine_dir/processed_normal_save_fail.png')
    initial_details = {
        normal_fr.id.hex: {'temp_processed_file': str(initial_temp_path), 'status': 'Processed', 'map_type': 'NORMAL', 'notes': 'Save fail test'}
    }
    context = create_normal_map_mock_context(
        initial_file_rules=[normal_fr],
        initial_processed_details=initial_details,
        invert_green_globally=True
    )
    original_details_entry = context.processed_maps_details[normal_fr.id.hex].copy()

    mock_loaded_normal_data = np.array([[[10, 50, 100]]], dtype=np.uint8)
    mock_load_image.return_value = mock_loaded_normal_data
    mock_save_image.return_value = False # Simulate save failure

    updated_context = stage.execute(context)

    mock_load_image.assert_called_once_with(initial_temp_path)
    mock_save_image.assert_called_once() # Save is attempted
    
    saved_path_arg = mock_save_image.call_args[0][0] # Get the path it tried to save to
    mock_log_error.assert_called_once()
    assert f"Failed to save green channel inverted image to {saved_path_arg}." in mock_log_error.call_args[0][0]
    
    # Details should be unchanged
    assert updated_context.processed_maps_details[normal_fr.id.hex] == original_details_entry
    assert normal_fr in updated_context.files_to_process

@mock.patch('processing.pipeline.stages.normal_map_green_channel.ipu.save_image')
@mock.patch('processing.pipeline.stages.normal_map_green_channel.ipu.load_image')
@mock.patch('logging.error')
@pytest.mark.parametrize("unsuitable_data, description", [
    (np.array([[1, 2], [3, 4]], dtype=np.uint8), "2D array"), # 2D array
    (np.array([[[1, 2]]], dtype=np.uint8), "2-channel image") # Image with less than 3 channels
])
def test_image_not_suitable_for_inversion(mock_log_error, mock_load_image, mock_save_image, unsuitable_data, description):
    stage = NormalMapGreenChannelStage()
    normal_rule_id = uuid.uuid4()
    normal_fr = create_mock_file_rule_for_normal_test(id_val=normal_rule_id, map_type="NORMAL")
    initial_temp_path_str = f'/fake/temp_engine_dir/unsuitable_{description.replace(" ", "_")}.png'
    initial_details = {
        normal_fr.id.hex: {'temp_processed_file': initial_temp_path_str, 'status': 'Processed', 'map_type': 'NORMAL', 'notes': f'Unsuitable: {description}'}
    }
    context = create_normal_map_mock_context(
        initial_file_rules=[normal_fr],
        initial_processed_details=initial_details,
        invert_green_globally=True
    )
    original_details_entry = context.processed_maps_details[normal_fr.id.hex].copy()

    mock_load_image.return_value = unsuitable_data

    updated_context = stage.execute(context)

    mock_load_image.assert_called_once_with(Path(initial_temp_path_str))
    mock_save_image.assert_not_called() # Save should not be attempted
    mock_log_error.assert_called_once()
    assert f"Image at {Path(initial_temp_path_str)} is not suitable for green channel inversion (e.g., not RGB/RGBA)." in mock_log_error.call_args[0][0]
    
    # Details should be unchanged
    assert updated_context.processed_maps_details[normal_fr.id.hex] == original_details_entry
    assert normal_fr in updated_context.files_to_process