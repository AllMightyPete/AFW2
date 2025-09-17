import pytest
from unittest import mock
from pathlib import Path
import uuid
import numpy as np

from processing.pipeline.stages.alpha_extraction_to_mask import AlphaExtractionToMaskStage
from processing.pipeline.asset_context import AssetProcessingContext
from rule_structure import AssetRule, SourceRule, FileRule
from configuration import Configuration, GeneralSettings
import processing.utils.image_processing_utils as ipu # Ensure ipu is available for mocking

# Helper Functions
def create_mock_file_rule_for_alpha_test(
    id_val: uuid.UUID = None,
    map_type: str = "ALBEDO",
    filename_pattern: str = "albedo.png",
    item_type: str = "MAP_COL",
    active: bool = True
) -> mock.MagicMock:
    mock_fr = mock.MagicMock(spec=FileRule)
    mock_fr.id = id_val if id_val else uuid.uuid4()
    mock_fr.map_type = map_type
    mock_fr.filename_pattern = filename_pattern
    mock_fr.item_type = item_type
    mock_fr.active = active
    mock_fr.transform_settings = mock.MagicMock(spec=TransformSettings)
    return mock_fr

def create_alpha_extraction_mock_context(
    initial_file_rules: list = None,
    initial_processed_details: dict = None,
    skip_asset_flag: bool = False,
    asset_name: str = "AlphaAsset",
    # extract_alpha_globally: bool = True # If stage checks this
) -> AssetProcessingContext:
    mock_asset_rule = mock.MagicMock(spec=AssetRule)
    mock_asset_rule.name = asset_name
    
    mock_source_rule = mock.MagicMock(spec=SourceRule)
    
    mock_gs = mock.MagicMock(spec=GeneralSettings)
    # if your stage uses a global flag:
    # mock_gs.extract_alpha_to_mask_globally = extract_alpha_globally
    
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
        incrementing_value=None,
        sha5_value=None
    )
    return context

# Unit Tests
@mock.patch('processing.pipeline.stages.alpha_extraction_to_mask.ipu.save_image')
@mock.patch('processing.pipeline.stages.alpha_extraction_to_mask.ipu.load_image')
@mock.patch('logging.info') # Mock logging to avoid console output during tests
def test_asset_skipped(mock_log_info, mock_load_image, mock_save_image):
    stage = AlphaExtractionToMaskStage()
    context = create_alpha_extraction_mock_context(skip_asset_flag=True)
    
    updated_context = stage.execute(context)
    
    assert updated_context == context # Context should be unchanged
    mock_load_image.assert_not_called()
    mock_save_image.assert_not_called()
    assert len(updated_context.files_to_process) == 0
    assert not updated_context.processed_maps_details

@mock.patch('processing.pipeline.stages.alpha_extraction_to_mask.ipu.save_image')
@mock.patch('processing.pipeline.stages.alpha_extraction_to_mask.ipu.load_image')
@mock.patch('logging.info')
def test_existing_mask_map(mock_log_info, mock_load_image, mock_save_image):
    stage = AlphaExtractionToMaskStage()
    
    existing_mask_rule = create_mock_file_rule_for_alpha_test(map_type="MASK", filename_pattern="mask.png")
    context = create_alpha_extraction_mock_context(initial_file_rules=[existing_mask_rule])
    
    updated_context = stage.execute(context)
    
    assert updated_context == context
    mock_load_image.assert_not_called()
    mock_save_image.assert_not_called()
    assert len(updated_context.files_to_process) == 1
    assert updated_context.files_to_process[0].map_type == "MASK"

@mock.patch('processing.pipeline.stages.alpha_extraction_to_mask.ipu.save_image')
@mock.patch('processing.pipeline.stages.alpha_extraction_to_mask.ipu.load_image')
@mock.patch('logging.info')
def test_alpha_extraction_success(mock_log_info, mock_load_image, mock_save_image):
    stage = AlphaExtractionToMaskStage()
    
    albedo_rule_id = uuid.uuid4()
    albedo_fr = create_mock_file_rule_for_alpha_test(id_val=albedo_rule_id, map_type="ALBEDO")
    
    initial_processed_details = {
        albedo_fr.id.hex: {'temp_processed_file': '/fake/temp_engine_dir/processed_albedo.png', 'status': 'Processed', 'map_type': 'ALBEDO', 'source_file_path': Path('/fake/source/albedo.png')}
    }
    context = create_alpha_extraction_mock_context(
        initial_file_rules=[albedo_fr],
        initial_processed_details=initial_processed_details
    )

    mock_rgba_data = np.zeros((10, 10, 4), dtype=np.uint8)
    mock_rgba_data[:, :, 3] = 128 # Example alpha data
    mock_load_image.side_effect = [mock_rgba_data, mock_rgba_data] 
    
    mock_save_image.return_value = True
    
    updated_context = stage.execute(context)
    
    assert mock_load_image.call_count == 2
    # First call to check for alpha, second to get data for saving
    mock_load_image.assert_any_call(Path('/fake/temp_engine_dir/processed_albedo.png')) 
    
    mock_save_image.assert_called_once()
    saved_path_arg = mock_save_image.call_args[0][0]
    saved_data_arg = mock_save_image.call_args[0][1]
    
    assert isinstance(saved_path_arg, Path)
    assert "mask_from_alpha_" in saved_path_arg.name
    assert np.array_equal(saved_data_arg, mock_rgba_data[:, :, 3])
    
    assert len(updated_context.files_to_process) == 2
    new_mask_rule = None
    for fr in updated_context.files_to_process:
        if fr.map_type == "MASK":
            new_mask_rule = fr
            break
    assert new_mask_rule is not None
    assert new_mask_rule.item_type == "MAP_DER" # Derived map
    
    assert new_mask_rule.id.hex in updated_context.processed_maps_details
    new_mask_detail = updated_context.processed_maps_details[new_mask_rule.id.hex]
    assert new_mask_detail['map_type'] == "MASK"
    assert "mask_from_alpha_" in new_mask_detail['temp_processed_file']
    assert "Generated from alpha of ALBEDO" in new_mask_detail['notes'] # Check for specific note
    assert new_mask_detail['status'] == 'Processed'

@mock.patch('processing.pipeline.stages.alpha_extraction_to_mask.ipu.save_image')
@mock.patch('processing.pipeline.stages.alpha_extraction_to_mask.ipu.load_image')
@mock.patch('logging.info')
def test_no_alpha_channel_in_source(mock_log_info, mock_load_image, mock_save_image):
    stage = AlphaExtractionToMaskStage()
    
    albedo_rule_id = uuid.uuid4()
    albedo_fr = create_mock_file_rule_for_alpha_test(id_val=albedo_rule_id, map_type="ALBEDO")
    initial_processed_details = {
        albedo_fr.id.hex: {'temp_processed_file': '/fake/temp_engine_dir/processed_rgb_albedo.png', 'status': 'Processed', 'map_type': 'ALBEDO', 'source_file_path': Path('/fake/source/albedo_rgb.png')}
    }
    context = create_alpha_extraction_mock_context(
        initial_file_rules=[albedo_fr],
        initial_processed_details=initial_processed_details
    )

    mock_rgb_data = np.zeros((10, 10, 3), dtype=np.uint8) # RGB, no alpha
    mock_load_image.return_value = mock_rgb_data # Only called once for check
    
    updated_context = stage.execute(context)
    
    mock_load_image.assert_called_once_with(Path('/fake/temp_engine_dir/processed_rgb_albedo.png'))
    mock_save_image.assert_not_called()
    assert len(updated_context.files_to_process) == 1 # No new MASK rule
    assert albedo_fr.id.hex in updated_context.processed_maps_details
    assert len(updated_context.processed_maps_details) == 1


@mock.patch('processing.pipeline.stages.alpha_extraction_to_mask.ipu.save_image')
@mock.patch('processing.pipeline.stages.alpha_extraction_to_mask.ipu.load_image')
@mock.patch('logging.info')
def test_no_suitable_source_map_type(mock_log_info, mock_load_image, mock_save_image):
    stage = AlphaExtractionToMaskStage()
    
    normal_rule_id = uuid.uuid4()
    normal_fr = create_mock_file_rule_for_alpha_test(id_val=normal_rule_id, map_type="NORMAL")
    initial_processed_details = {
        normal_fr.id.hex: {'temp_processed_file': '/fake/temp_engine_dir/processed_normal.png', 'status': 'Processed', 'map_type': 'NORMAL'}
    }
    context = create_alpha_extraction_mock_context(
        initial_file_rules=[normal_fr],
        initial_processed_details=initial_processed_details
    )
    
    updated_context = stage.execute(context)
    
    mock_load_image.assert_not_called()
    mock_save_image.assert_not_called()
    assert len(updated_context.files_to_process) == 1
    assert normal_fr.id.hex in updated_context.processed_maps_details
    assert len(updated_context.processed_maps_details) == 1

@mock.patch('processing.pipeline.stages.alpha_extraction_to_mask.ipu.save_image')
@mock.patch('processing.pipeline.stages.alpha_extraction_to_mask.ipu.load_image')
@mock.patch('logging.warning') # Expect a warning log
def test_load_image_fails(mock_log_warning, mock_load_image, mock_save_image):
    stage = AlphaExtractionToMaskStage()
    
    albedo_rule_id = uuid.uuid4()
    albedo_fr = create_mock_file_rule_for_alpha_test(id_val=albedo_rule_id, map_type="ALBEDO")
    initial_processed_details = {
        albedo_fr.id.hex: {'temp_processed_file': '/fake/temp_engine_dir/processed_albedo_load_fail.png', 'status': 'Processed', 'map_type': 'ALBEDO', 'source_file_path': Path('/fake/source/albedo_load_fail.png')}
    }
    context = create_alpha_extraction_mock_context(
        initial_file_rules=[albedo_fr],
        initial_processed_details=initial_processed_details
    )

    mock_load_image.return_value = None # Simulate load failure
    
    updated_context = stage.execute(context)
    
    mock_load_image.assert_called_once_with(Path('/fake/temp_engine_dir/processed_albedo_load_fail.png'))
    mock_save_image.assert_not_called()
    assert len(updated_context.files_to_process) == 1
    assert albedo_fr.id.hex in updated_context.processed_maps_details
    assert len(updated_context.processed_maps_details) == 1
    mock_log_warning.assert_called_once() # Check that a warning was logged

@mock.patch('processing.pipeline.stages.alpha_extraction_to_mask.ipu.save_image')
@mock.patch('processing.pipeline.stages.alpha_extraction_to_mask.ipu.load_image')
@mock.patch('logging.error') # Expect an error log
def test_save_image_fails(mock_log_error, mock_load_image, mock_save_image):
    stage = AlphaExtractionToMaskStage()
    
    albedo_rule_id = uuid.uuid4()
    albedo_fr = create_mock_file_rule_for_alpha_test(id_val=albedo_rule_id, map_type="ALBEDO")
    initial_processed_details = {
        albedo_fr.id.hex: {'temp_processed_file': '/fake/temp_engine_dir/processed_albedo_save_fail.png', 'status': 'Processed', 'map_type': 'ALBEDO', 'source_file_path': Path('/fake/source/albedo_save_fail.png')}
    }
    context = create_alpha_extraction_mock_context(
        initial_file_rules=[albedo_fr],
        initial_processed_details=initial_processed_details
    )

    mock_rgba_data = np.zeros((10, 10, 4), dtype=np.uint8)
    mock_rgba_data[:, :, 3] = 128
    mock_load_image.side_effect = [mock_rgba_data, mock_rgba_data] # Load succeeds
    
    mock_save_image.return_value = False # Simulate save failure
    
    updated_context = stage.execute(context)
    
    assert mock_load_image.call_count == 2
    mock_save_image.assert_called_once() # Save was attempted
    
    assert len(updated_context.files_to_process) == 1 # No new MASK rule should be successfully added and detailed
    
    # Check that no new MASK details were added, or if they were, they reflect failure.
    # The current stage logic returns context early, so no new rule or details should be present.
    mask_rule_found = any(fr.map_type == "MASK" for fr in updated_context.files_to_process)
    assert not mask_rule_found

    mask_details_found = any(
        details['map_type'] == "MASK" 
        for fr_id, details in updated_context.processed_maps_details.items() 
        if fr_id != albedo_fr.id.hex # Exclude the original albedo
    )
    assert not mask_details_found
    mock_log_error.assert_called_once() # Check that an error was logged