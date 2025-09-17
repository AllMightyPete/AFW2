import pytest
from unittest import mock
from pathlib import Path
import uuid
import numpy as np
from typing import Optional # Added Optional for type hinting

from processing.pipeline.stages.map_merging import MapMergingStage
from processing.pipeline.asset_context import AssetProcessingContext
from rule_structure import AssetRule, SourceRule, FileRule
from configuration import Configuration

# Mock Helper Functions
def create_mock_merge_input_channel(
    file_rule_id: uuid.UUID, source_channel: int = 0, target_channel: int = 0, invert: bool = False
) -> mock.MagicMock:
    mic = mock.MagicMock(spec=MergeInputChannel)
    mic.file_rule_id = file_rule_id
    mic.source_channel = source_channel
    mic.target_channel = target_channel
    mic.invert_source_channel = invert
    mic.default_value_if_missing = 0 # Or some other default
    return mic

def create_mock_merge_settings(
    input_maps: Optional[list] = None, # List of mock MergeInputChannel
    output_channels: int = 3
) -> mock.MagicMock:
    ms = mock.MagicMock(spec=MergeSettings)
    ms.input_maps = input_maps if input_maps is not None else []
    ms.output_channels = output_channels
    return ms

def create_mock_file_rule_for_merging(
    id_val: Optional[uuid.UUID] = None,
    map_type: str = "ORM", # Output map type
    item_type: str = "MAP_MERGE",
    merge_settings: Optional[mock.MagicMock] = None
) -> mock.MagicMock:
    mock_fr = mock.MagicMock(spec=FileRule)
    mock_fr.id = id_val if id_val else uuid.uuid4()
    mock_fr.map_type = map_type
    mock_fr.filename_pattern = f"{map_type.lower()}_merged.png" # Placeholder
    mock_fr.item_type = item_type
    mock_fr.active = True
    mock_fr.merge_settings = merge_settings if merge_settings else create_mock_merge_settings()
    return mock_fr

def create_map_merging_mock_context(
    initial_file_rules: Optional[list] = None, # Will contain the MAP_MERGE rule
    initial_processed_details: Optional[dict] = None, # Pre-processed inputs for merge
    skip_asset_flag: bool = False,
    asset_name: str = "MergeAsset"
) -> AssetProcessingContext:
    mock_asset_rule = mock.MagicMock(spec=AssetRule)
    mock_asset_rule.name = asset_name
    mock_source_rule = mock.MagicMock(spec=SourceRule)
    mock_config = mock.MagicMock(spec=Configuration)

    context = AssetProcessingContext(
        source_rule=mock_source_rule,
        asset_rule=mock_asset_rule,
        workspace_path=Path("/fake/workspace"),
        engine_temp_dir=Path("/fake/temp_engine_dir"),
        output_base_path=Path("/fake/output"),
        effective_supplier="ValidSupplier",
        asset_metadata={'asset_name': asset_name},
        processed_maps_details=initial_processed_details if initial_processed_details is not None else {},
        merged_maps_details={}, # Stage populates this
        files_to_process=list(initial_file_rules) if initial_file_rules else [],
        loaded_data_cache={},
        config_obj=mock_config,
        status_flags={'skip_asset': skip_asset_flag},
        incrementing_value=None,
        sha5_value=None # Corrected from sha5_value to sha_value based on AssetProcessingContext
    )
    return context
def test_asset_skipped():
    stage = MapMergingStage()
    context = create_map_merging_mock_context(skip_asset_flag=True)
    
    updated_context = stage.execute(context)
    
    assert updated_context == context # No changes expected
    assert not updated_context.merged_maps_details # No maps should be merged

def test_no_map_merge_rules():
    stage = MapMergingStage()
    # Context with a non-MAP_MERGE rule
    non_merge_rule = create_mock_file_rule_for_merging(item_type="TEXTURE_MAP", map_type="Diffuse")
    context = create_map_merging_mock_context(initial_file_rules=[non_merge_rule])
    
    updated_context = stage.execute(context)
    
    assert updated_context == context # No changes expected
    assert not updated_context.merged_maps_details # No maps should be merged

@mock.patch('processing.pipeline.stages.map_merging.ipu.save_image')
@mock.patch('processing.pipeline.stages.map_merging.ipu.resize_image') # If testing resize
@mock.patch('processing.pipeline.stages.map_merging.ipu.load_image')
@mock.patch('logging.info')
@mock.patch('logging.error')
def test_map_merging_rgb_success(mock_log_error, mock_log_info, mock_load_image, mock_resize_image, mock_save_image):
    stage = MapMergingStage()

    # Input FileRules (mocked as already processed)
    r_id, g_id, b_id = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    processed_details = {
        r_id.hex: {'temp_processed_file': '/fake/red.png', 'status': 'Processed', 'map_type': 'RED_SRC'},
        g_id.hex: {'temp_processed_file': '/fake/green.png', 'status': 'Processed', 'map_type': 'GREEN_SRC'},
        b_id.hex: {'temp_processed_file': '/fake/blue.png', 'status': 'Processed', 'map_type': 'BLUE_SRC'}
    }
    # Mock loaded image data (grayscale for inputs)
    mock_r_data = np.full((10, 10), 200, dtype=np.uint8)
    mock_g_data = np.full((10, 10), 100, dtype=np.uint8)
    mock_b_data = np.full((10, 10), 50, dtype=np.uint8)
    mock_load_image.side_effect = [mock_r_data, mock_g_data, mock_b_data]

    # Merge Rule setup
    merge_inputs = [
        create_mock_merge_input_channel(file_rule_id=r_id, source_channel=0, target_channel=0), # R to R
        create_mock_merge_input_channel(file_rule_id=g_id, source_channel=0, target_channel=1), # G to G
        create_mock_merge_input_channel(file_rule_id=b_id, source_channel=0, target_channel=2)  # B to B
    ]
    merge_settings = create_mock_merge_settings(input_maps=merge_inputs, output_channels=3)
    merge_rule_id = uuid.uuid4()
    merge_rule = create_mock_file_rule_for_merging(id_val=merge_rule_id, map_type="RGB_Combined", merge_settings=merge_settings)
    
    context = create_map_merging_mock_context(
        initial_file_rules=[merge_rule], 
        initial_processed_details=processed_details
    )
    mock_save_image.return_value = True
    
    updated_context = stage.execute(context)

    assert mock_load_image.call_count == 3
    mock_resize_image.assert_not_called() # Assuming all inputs are same size for this test
    mock_save_image.assert_called_once()
    
    # Check that the correct filename was passed to save_image
    # The filename is constructed as: f"{context.asset_rule.name}_merged_{merge_rule.map_type}{Path(first_input_path).suffix}"
    # In this case, first_input_path is '/fake/red.png', so suffix is '.png'
    # Asset name is "MergeAsset"
    expected_filename_part = f"{context.asset_rule.name}_merged_{merge_rule.map_type}.png"
    saved_path_arg = mock_save_image.call_args[0][0]
    assert expected_filename_part in str(saved_path_arg)


    saved_data = mock_save_image.call_args[0][1]
    assert saved_data.shape == (10, 10, 3)
    assert np.all(saved_data[:,:,0] == 200) # Red channel
    assert np.all(saved_data[:,:,1] == 100) # Green channel
    assert np.all(saved_data[:,:,2] == 50)  # Blue channel

    assert merge_rule.id.hex in updated_context.merged_maps_details
    details = updated_context.merged_maps_details[merge_rule.id.hex]
    assert details['status'] == 'Processed'
    # The temp_merged_file path will be under engine_temp_dir / asset_name / filename
    assert f"{context.engine_temp_dir / context.asset_rule.name / expected_filename_part}" == details['temp_merged_file']
    mock_log_error.assert_not_called()
    mock_log_info.assert_any_call(f"Successfully merged map '{merge_rule.map_type}' for asset '{context.asset_rule.name}'.")

# Unit tests will be added below this line
@mock.patch('processing.pipeline.stages.map_merging.ipu.save_image')
@mock.patch('processing.pipeline.stages.map_merging.ipu.resize_image')
@mock.patch('processing.pipeline.stages.map_merging.ipu.load_image')
@mock.patch('logging.info')
@mock.patch('logging.error')
def test_map_merging_channel_inversion(mock_log_error, mock_log_info, mock_load_image, mock_resize_image, mock_save_image):
    stage = MapMergingStage()

    # Input FileRule
    input_id = uuid.uuid4()
    processed_details = {
        input_id.hex: {'temp_processed_file': '/fake/source.png', 'status': 'Processed', 'map_type': 'SOURCE_MAP'}
    }
    # Mock loaded image data (single channel for simplicity, to be inverted)
    mock_source_data = np.array([[0, 100], [155, 255]], dtype=np.uint8)
    mock_load_image.return_value = mock_source_data

    # Merge Rule setup: one input, inverted, to one output channel
    merge_inputs = [
        create_mock_merge_input_channel(file_rule_id=input_id, source_channel=0, target_channel=0, invert=True)
    ]
    merge_settings = create_mock_merge_settings(input_maps=merge_inputs, output_channels=1)
    merge_rule_id = uuid.uuid4()
    merge_rule = create_mock_file_rule_for_merging(id_val=merge_rule_id, map_type="Inverted_Gray", merge_settings=merge_settings)
    
    context = create_map_merging_mock_context(
        initial_file_rules=[merge_rule], 
        initial_processed_details=processed_details
    )
    mock_save_image.return_value = True
    
    updated_context = stage.execute(context)

    mock_load_image.assert_called_once_with(Path('/fake/source.png'))
    mock_resize_image.assert_not_called()
    mock_save_image.assert_called_once()
    
    saved_data = mock_save_image.call_args[0][1]
    assert saved_data.shape == (2, 2) # Grayscale output
    
    # Expected inverted data: 255-original
    expected_inverted_data = np.array([[255, 155], [100, 0]], dtype=np.uint8)
    assert np.all(saved_data == expected_inverted_data)

    assert merge_rule.id.hex in updated_context.merged_maps_details
    details = updated_context.merged_maps_details[merge_rule.id.hex]
    assert details['status'] == 'Processed'
    assert "merged_Inverted_Gray" in details['temp_merged_file']
    mock_log_error.assert_not_called()
    mock_log_info.assert_any_call(f"Successfully merged map '{merge_rule.map_type}' for asset '{context.asset_rule.name}'.")
@mock.patch('processing.pipeline.stages.map_merging.ipu.save_image')
@mock.patch('processing.pipeline.stages.map_merging.ipu.load_image')
@mock.patch('logging.error')
def test_map_merging_input_map_missing(mock_log_error, mock_load_image, mock_save_image):
    stage = MapMergingStage()

    # Input FileRule ID that will be missing from processed_details
    missing_input_id = uuid.uuid4()
    
    # Merge Rule setup
    merge_inputs = [
        create_mock_merge_input_channel(file_rule_id=missing_input_id, source_channel=0, target_channel=0)
    ]
    merge_settings = create_mock_merge_settings(input_maps=merge_inputs, output_channels=1)
    merge_rule_id = uuid.uuid4()
    merge_rule = create_mock_file_rule_for_merging(id_val=merge_rule_id, map_type="TestMissing", merge_settings=merge_settings)
    
    # processed_details is empty, so missing_input_id will not be found
    context = create_map_merging_mock_context(
        initial_file_rules=[merge_rule], 
        initial_processed_details={} 
    )
    
    updated_context = stage.execute(context)

    mock_load_image.assert_not_called()
    mock_save_image.assert_not_called()
    
    assert merge_rule.id.hex in updated_context.merged_maps_details
    details = updated_context.merged_maps_details[merge_rule.id.hex]
    assert details['status'] == 'Failed'
    assert 'error_message' in details
    assert f"Input map FileRule ID {missing_input_id.hex} not found in processed_maps_details or not successfully processed" in details['error_message']
    
    mock_log_error.assert_called_once()
    assert f"Failed to merge map '{merge_rule.map_type}' for asset '{context.asset_rule.name}'" in mock_log_error.call_args[0][0]
    assert f"Input map FileRule ID {missing_input_id.hex} not found in processed_maps_details or not successfully processed" in mock_log_error.call_args[0][0]

@mock.patch('processing.pipeline.stages.map_merging.ipu.save_image')
@mock.patch('processing.pipeline.stages.map_merging.ipu.load_image')
@mock.patch('logging.error')
def test_map_merging_input_map_status_not_processed(mock_log_error, mock_load_image, mock_save_image):
    stage = MapMergingStage()

    input_id = uuid.uuid4()
    processed_details = {
        # Status is 'Failed', not 'Processed'
        input_id.hex: {'temp_processed_file': '/fake/source.png', 'status': 'Failed', 'map_type': 'SOURCE_MAP'}
    }
    
    merge_inputs = [
        create_mock_merge_input_channel(file_rule_id=input_id, source_channel=0, target_channel=0)
    ]
    merge_settings = create_mock_merge_settings(input_maps=merge_inputs, output_channels=1)
    merge_rule_id = uuid.uuid4()
    merge_rule = create_mock_file_rule_for_merging(id_val=merge_rule_id, map_type="TestNotProcessed", merge_settings=merge_settings)
    
    context = create_map_merging_mock_context(
        initial_file_rules=[merge_rule], 
        initial_processed_details=processed_details
    )
    
    updated_context = stage.execute(context)

    mock_load_image.assert_not_called()
    mock_save_image.assert_not_called()
    
    assert merge_rule.id.hex in updated_context.merged_maps_details
    details = updated_context.merged_maps_details[merge_rule.id.hex]
    assert details['status'] == 'Failed'
    assert 'error_message' in details
    assert f"Input map FileRule ID {input_id.hex} not found in processed_maps_details or not successfully processed" in details['error_message']
    
    mock_log_error.assert_called_once()
    assert f"Failed to merge map '{merge_rule.map_type}' for asset '{context.asset_rule.name}'" in mock_log_error.call_args[0][0]
    assert f"Input map FileRule ID {input_id.hex} not found in processed_maps_details or not successfully processed" in mock_log_error.call_args[0][0]
@mock.patch('processing.pipeline.stages.map_merging.ipu.save_image')
@mock.patch('processing.pipeline.stages.map_merging.ipu.load_image')
@mock.patch('logging.error')
def test_map_merging_load_image_fails(mock_log_error, mock_load_image, mock_save_image):
    stage = MapMergingStage()

    input_id = uuid.uuid4()
    processed_details = {
        input_id.hex: {'temp_processed_file': '/fake/source.png', 'status': 'Processed', 'map_type': 'SOURCE_MAP'}
    }
    
    # Configure mock_load_image to raise an exception
    mock_load_image.side_effect = Exception("Failed to load image")

    merge_inputs = [
        create_mock_merge_input_channel(file_rule_id=input_id, source_channel=0, target_channel=0)
    ]
    merge_settings = create_mock_merge_settings(input_maps=merge_inputs, output_channels=1)
    merge_rule_id = uuid.uuid4()
    merge_rule = create_mock_file_rule_for_merging(id_val=merge_rule_id, map_type="TestLoadFail", merge_settings=merge_settings)
    
    context = create_map_merging_mock_context(
        initial_file_rules=[merge_rule], 
        initial_processed_details=processed_details
    )
    
    updated_context = stage.execute(context)

    mock_load_image.assert_called_once_with(Path('/fake/source.png'))
    mock_save_image.assert_not_called()
    
    assert merge_rule.id.hex in updated_context.merged_maps_details
    details = updated_context.merged_maps_details[merge_rule.id.hex]
    assert details['status'] == 'Failed'
    assert 'error_message' in details
    assert "Failed to load image for merge input" in details['error_message']
    assert str(Path('/fake/source.png')) in details['error_message']
    
    mock_log_error.assert_called_once()
    assert f"Failed to merge map '{merge_rule.map_type}' for asset '{context.asset_rule.name}'" in mock_log_error.call_args[0][0]
    assert "Failed to load image for merge input" in mock_log_error.call_args[0][0]
@mock.patch('processing.pipeline.stages.map_merging.ipu.save_image')
@mock.patch('processing.pipeline.stages.map_merging.ipu.load_image')
@mock.patch('logging.error')
def test_map_merging_save_image_fails(mock_log_error, mock_load_image, mock_save_image):
    stage = MapMergingStage()

    input_id = uuid.uuid4()
    processed_details = {
        input_id.hex: {'temp_processed_file': '/fake/source.png', 'status': 'Processed', 'map_type': 'SOURCE_MAP'}
    }
    mock_source_data = np.full((10, 10), 128, dtype=np.uint8)
    mock_load_image.return_value = mock_source_data
    
    # Configure mock_save_image to return False (indicating failure)
    mock_save_image.return_value = False

    merge_inputs = [
        create_mock_merge_input_channel(file_rule_id=input_id, source_channel=0, target_channel=0)
    ]
    merge_settings = create_mock_merge_settings(input_maps=merge_inputs, output_channels=1)
    merge_rule_id = uuid.uuid4()
    merge_rule = create_mock_file_rule_for_merging(id_val=merge_rule_id, map_type="TestSaveFail", merge_settings=merge_settings)
    
    context = create_map_merging_mock_context(
        initial_file_rules=[merge_rule], 
        initial_processed_details=processed_details
    )
    
    updated_context = stage.execute(context)

    mock_load_image.assert_called_once_with(Path('/fake/source.png'))
    mock_save_image.assert_called_once() # save_image is called, but returns False
    
    assert merge_rule.id.hex in updated_context.merged_maps_details
    details = updated_context.merged_maps_details[merge_rule.id.hex]
    assert details['status'] == 'Failed'
    assert 'error_message' in details
    assert "Failed to save merged map" in details['error_message']
    
    mock_log_error.assert_called_once()
    assert f"Failed to merge map '{merge_rule.map_type}' for asset '{context.asset_rule.name}'" in mock_log_error.call_args[0][0]
    assert "Failed to save merged map" in mock_log_error.call_args[0][0]
@mock.patch('processing.pipeline.stages.map_merging.ipu.save_image')
@mock.patch('processing.pipeline.stages.map_merging.ipu.resize_image')
@mock.patch('processing.pipeline.stages.map_merging.ipu.load_image')
@mock.patch('logging.info')
@mock.patch('logging.error')
def test_map_merging_dimension_mismatch_handling(mock_log_error, mock_log_info, mock_load_image, mock_resize_image, mock_save_image):
    stage = MapMergingStage()

    # Input FileRules
    id1, id2 = uuid.uuid4(), uuid.uuid4()
    processed_details = {
        id1.hex: {'temp_processed_file': '/fake/img1.png', 'status': 'Processed', 'map_type': 'IMG1_SRC'},
        id2.hex: {'temp_processed_file': '/fake/img2.png', 'status': 'Processed', 'map_type': 'IMG2_SRC'}
    }
    
    # Mock loaded image data with different dimensions
    mock_img1_data = np.full((10, 10), 100, dtype=np.uint8) # 10x10
    mock_img2_data_original = np.full((5, 5), 200, dtype=np.uint8) # 5x5, will be resized
    
    mock_load_image.side_effect = [mock_img1_data, mock_img2_data_original]

    # Mock resize_image to return an image of the target dimensions
    # For simplicity, it just creates a new array of the target size filled with a value.
    mock_img2_data_resized = np.full((10, 10), 210, dtype=np.uint8) # Resized to 10x10
    mock_resize_image.return_value = mock_img2_data_resized

    # Merge Rule setup: two inputs, one output channel (e.g., averaging them)
    # Target channel 0 for both, the stage should handle combining them if they map to the same target.
    # However, the current stage logic for multiple inputs to the same target channel is to take the last one.
    # Let's make them target different channels for a clearer test of resize.
    merge_inputs = [
        create_mock_merge_input_channel(file_rule_id=id1, source_channel=0, target_channel=0),
        create_mock_merge_input_channel(file_rule_id=id2, source_channel=0, target_channel=1) 
    ]
    merge_settings = create_mock_merge_settings(input_maps=merge_inputs, output_channels=2) # Outputting 2 channels
    merge_rule_id = uuid.uuid4()
    merge_rule = create_mock_file_rule_for_merging(id_val=merge_rule_id, map_type="ResizedMerge", merge_settings=merge_settings)
    
    context = create_map_merging_mock_context(
        initial_file_rules=[merge_rule], 
        initial_processed_details=processed_details
    )
    mock_save_image.return_value = True
    
    updated_context = stage.execute(context)

    assert mock_load_image.call_count == 2
    mock_load_image.assert_any_call(Path('/fake/img1.png'))
    mock_load_image.assert_any_call(Path('/fake/img2.png'))

    # Assert resize_image was called for the second image to match the first's dimensions
    mock_resize_image.assert_called_once()
    # The first argument to resize_image is the image data, second is target_shape tuple (height, width)
    # np.array_equal is needed for comparing numpy arrays in mock calls
    assert np.array_equal(mock_resize_image.call_args[0][0], mock_img2_data_original)
    assert mock_resize_image.call_args[0][1] == (10, 10) 

    mock_save_image.assert_called_once()
    
    saved_data = mock_save_image.call_args[0][1]
    assert saved_data.shape == (10, 10, 2) # 2 output channels
    assert np.all(saved_data[:,:,0] == mock_img1_data)     # First channel from img1
    assert np.all(saved_data[:,:,1] == mock_img2_data_resized) # Second channel from resized img2

    assert merge_rule.id.hex in updated_context.merged_maps_details
    details = updated_context.merged_maps_details[merge_rule.id.hex]
    assert details['status'] == 'Processed'
    assert "merged_ResizedMerge" in details['temp_merged_file']
    mock_log_error.assert_not_called()
    mock_log_info.assert_any_call(f"Resized input map from {Path('/fake/img2.png')} from {mock_img2_data_original.shape} to {(10,10)} to match first loaded map.")
    mock_log_info.assert_any_call(f"Successfully merged map '{merge_rule.map_type}' for asset '{context.asset_rule.name}'.")
@mock.patch('processing.pipeline.stages.map_merging.ipu.save_image')
@mock.patch('processing.pipeline.stages.map_merging.ipu.resize_image')
@mock.patch('processing.pipeline.stages.map_merging.ipu.load_image')
@mock.patch('logging.info')
@mock.patch('logging.error')
def test_map_merging_to_grayscale_output(mock_log_error, mock_log_info, mock_load_image, mock_resize_image, mock_save_image):
    stage = MapMergingStage()

    # Input FileRule (e.g., an RGB image)
    input_id = uuid.uuid4()
    processed_details = {
        input_id.hex: {'temp_processed_file': '/fake/rgb_source.png', 'status': 'Processed', 'map_type': 'RGB_SRC'}
    }
    # Mock loaded image data (3 channels)
    mock_rgb_data = np.full((10, 10, 3), [50, 100, 150], dtype=np.uint8)
    mock_load_image.return_value = mock_rgb_data

    # Merge Rule setup: take the Green channel (source_channel=1) from input and map it to the single output channel (target_channel=0)
    merge_inputs = [
        create_mock_merge_input_channel(file_rule_id=input_id, source_channel=1, target_channel=0) # G to Grayscale
    ]
    # output_channels = 1 for grayscale
    merge_settings = create_mock_merge_settings(input_maps=merge_inputs, output_channels=1) 
    merge_rule_id = uuid.uuid4()
    merge_rule = create_mock_file_rule_for_merging(id_val=merge_rule_id, map_type="GrayscaleFromGreen", merge_settings=merge_settings)
    
    context = create_map_merging_mock_context(
        initial_file_rules=[merge_rule], 
        initial_processed_details=processed_details
    )
    mock_save_image.return_value = True
    
    updated_context = stage.execute(context)

    mock_load_image.assert_called_once_with(Path('/fake/rgb_source.png'))
    mock_resize_image.assert_not_called() 
    mock_save_image.assert_called_once()
    
    saved_data = mock_save_image.call_args[0][1]
    assert saved_data.shape == (10, 10) # Grayscale output (2D)
    assert np.all(saved_data == 100)    # Green channel's value

    assert merge_rule.id.hex in updated_context.merged_maps_details
    details = updated_context.merged_maps_details[merge_rule.id.hex]
    assert details['status'] == 'Processed'
    assert "merged_GrayscaleFromGreen" in details['temp_merged_file']
    mock_log_error.assert_not_called()
    mock_log_info.assert_any_call(f"Successfully merged map '{merge_rule.map_type}' for asset '{context.asset_rule.name}'.")

@mock.patch('processing.pipeline.stages.map_merging.ipu.save_image')
@mock.patch('processing.pipeline.stages.map_merging.ipu.load_image')
@mock.patch('logging.error')
def test_map_merging_default_value_if_missing_channel(mock_log_error, mock_load_image, mock_save_image):
    stage = MapMergingStage()

    input_id = uuid.uuid4()
    processed_details = {
        # Input is a grayscale image (1 channel)
        input_id.hex: {'temp_processed_file': '/fake/gray_source.png', 'status': 'Processed', 'map_type': 'GRAY_SRC'}
    }
    mock_gray_data = np.full((10, 10), 50, dtype=np.uint8)
    mock_load_image.return_value = mock_gray_data
    
    # Merge Rule: try to read source_channel 1 (which doesn't exist in grayscale)
    # and use default_value_if_missing for target_channel 0.
    # Also, read source_channel 0 (which exists) for target_channel 1.
    mic1 = create_mock_merge_input_channel(file_rule_id=input_id, source_channel=1, target_channel=0)
    mic1.default_value_if_missing = 128 # Set a specific default value
    mic2 = create_mock_merge_input_channel(file_rule_id=input_id, source_channel=0, target_channel=1)

    merge_settings = create_mock_merge_settings(input_maps=[mic1, mic2], output_channels=2)
    merge_rule_id = uuid.uuid4()
    merge_rule = create_mock_file_rule_for_merging(id_val=merge_rule_id, map_type="DefaultValueTest", merge_settings=merge_settings)
    
    context = create_map_merging_mock_context(
        initial_file_rules=[merge_rule], 
        initial_processed_details=processed_details
    )
    mock_save_image.return_value = True
    
    updated_context = stage.execute(context)

    mock_load_image.assert_called_once_with(Path('/fake/gray_source.png'))
    mock_save_image.assert_called_once()
    
    saved_data = mock_save_image.call_args[0][1]
    assert saved_data.shape == (10, 10, 2)
    assert np.all(saved_data[:,:,0] == 128) # Default value for missing source channel 1
    assert np.all(saved_data[:,:,1] == 50)  # Value from existing source channel 0

    assert merge_rule.id.hex in updated_context.merged_maps_details
    details = updated_context.merged_maps_details[merge_rule.id.hex]
    assert details['status'] == 'Processed'
    mock_log_error.assert_not_called()