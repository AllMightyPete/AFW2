import pytest
from unittest import mock
from pathlib import Path
import uuid
import numpy as np
from typing import Optional, List, Dict

from processing.pipeline.stages.gloss_to_rough_conversion import GlossToRoughConversionStage
from processing.pipeline.asset_context import AssetProcessingContext
from rule_structure import AssetRule, SourceRule, FileRule
from configuration import Configuration, GeneralSettings
# No direct ipu import needed in test if we mock its usage by the stage

def create_mock_file_rule_for_gloss_test(
    id_val: Optional[uuid.UUID] = None,
    map_type: str = "GLOSS", # Test with GLOSS and other types
    filename_pattern: str = "gloss.png"
) -> mock.MagicMock:
    mock_fr = mock.MagicMock(spec=FileRule)
    mock_fr.id = id_val if id_val else uuid.uuid4()
    mock_fr.map_type = map_type
    mock_fr.filename_pattern = filename_pattern
    mock_fr.item_type = "MAP_COL"
    mock_fr.active = True
    return mock_fr

def create_gloss_conversion_mock_context(
    initial_file_rules: Optional[List[FileRule]] = None, # Type hint corrected
    initial_processed_details: Optional[Dict] = None, # Type hint corrected
    skip_asset_flag: bool = False,
    asset_name: str = "GlossAsset",
    # Add a mock for general_settings if your stage checks a global flag
    # convert_gloss_globally: bool = True
) -> AssetProcessingContext:
    mock_asset_rule = mock.MagicMock(spec=AssetRule)
    mock_asset_rule.name = asset_name
    mock_asset_rule.file_rules = initial_file_rules if initial_file_rules is not None else []

    mock_source_rule = mock.MagicMock(spec=SourceRule)

    mock_gs = mock.MagicMock(spec=GeneralSettings)
    # if your stage uses a global flag:
    # mock_gs.convert_gloss_to_rough_globally = convert_gloss_globally

    mock_config = mock.MagicMock(spec=Configuration)
    mock_config.general_settings = mock_gs


    context = AssetProcessingContext(
        source_rule=mock_source_rule,
        asset_rule=mock_asset_rule,
        workspace_path=Path("/fake/workspace"),
        engine_temp_dir=Path("/fake/temp_engine_dir"), # Important for new temp file paths
        output_base_path=Path("/fake/output"),
        effective_supplier="ValidSupplier",
        asset_metadata={'asset_name': asset_name},
        processed_maps_details=initial_processed_details if initial_processed_details is not None else {},
        merged_maps_details={},
        files_to_process=list(initial_file_rules) if initial_file_rules else [], # Stage modifies this list
        loaded_data_cache={},
        config_obj=mock_config,
        status_flags={'skip_asset': skip_asset_flag},
        incrementing_value=None, # Added as per AssetProcessingContext definition
        sha5_value=None # Added as per AssetProcessingContext definition
    )
    return context

# Unit tests will be added below
@mock.patch('processing.pipeline.stages.gloss_to_rough_conversion.ipu.save_image')
@mock.patch('processing.pipeline.stages.gloss_to_rough_conversion.ipu.load_image')
def test_asset_skipped(mock_load_image, mock_save_image):
    """
    Test that if 'skip_asset' is True, no processing occurs.
    """
    stage = GlossToRoughConversionStage()
    
    gloss_rule_id = uuid.uuid4()
    gloss_fr = create_mock_file_rule_for_gloss_test(id_val=gloss_rule_id, map_type="GLOSS")
    
    initial_details = {
        gloss_fr.id.hex: {'temp_processed_file': '/fake/temp_engine_dir/processed_gloss_map.png', 'status': 'Processed', 'map_type': 'GLOSS'}
    }
    context = create_gloss_conversion_mock_context(
        initial_file_rules=[gloss_fr],
        initial_processed_details=initial_details,
        skip_asset_flag=True # Asset is skipped
    )
    
    # Keep a copy of files_to_process and processed_maps_details to compare
    original_files_to_process = list(context.files_to_process)
    original_processed_maps_details = context.processed_maps_details.copy()
    
    updated_context = stage.execute(context)
    
    mock_load_image.assert_not_called()
    mock_save_image.assert_not_called()
    
    assert updated_context.files_to_process == original_files_to_process, "files_to_process should not change if asset is skipped"
    assert updated_context.processed_maps_details == original_processed_maps_details, "processed_maps_details should not change if asset is skipped"
    assert updated_context.status_flags['skip_asset'] is True
@mock.patch('processing.pipeline.stages.gloss_to_rough_conversion.ipu.save_image')
@mock.patch('processing.pipeline.stages.gloss_to_rough_conversion.ipu.load_image')
def test_no_gloss_map_present(mock_load_image, mock_save_image):
    """
    Test that if no GLOSS maps are in files_to_process, no conversion occurs.
    """
    stage = GlossToRoughConversionStage()
    
    normal_rule_id = uuid.uuid4()
    normal_fr = create_mock_file_rule_for_gloss_test(id_val=normal_rule_id, map_type="NORMAL", filename_pattern="normal.png")
    albedo_fr = create_mock_file_rule_for_gloss_test(map_type="ALBEDO", filename_pattern="albedo.jpg")
    
    initial_details = {
        normal_fr.id.hex: {'temp_processed_file': '/fake/temp_engine_dir/processed_normal_map.png', 'status': 'Processed', 'map_type': 'NORMAL'}
    }
    context = create_gloss_conversion_mock_context(
        initial_file_rules=[normal_fr, albedo_fr],
        initial_processed_details=initial_details
    )
    
    original_files_to_process = list(context.files_to_process)
    original_processed_maps_details = context.processed_maps_details.copy()
    
    updated_context = stage.execute(context)
    
    mock_load_image.assert_not_called()
    mock_save_image.assert_not_called()
    
    assert updated_context.files_to_process == original_files_to_process, "files_to_process should not change if no GLOSS maps are present"
    assert updated_context.processed_maps_details == original_processed_maps_details, "processed_maps_details should not change if no GLOSS maps are present"
    
    # Ensure map types of existing rules are unchanged
    for fr_in_list in updated_context.files_to_process:
        if fr_in_list.id == normal_fr.id:
            assert fr_in_list.map_type == "NORMAL"
        elif fr_in_list.id == albedo_fr.id:
            assert fr_in_list.map_type == "ALBEDO"
@mock.patch('processing.pipeline.stages.gloss_to_rough_conversion.logging') # Mock logging
@mock.patch('processing.pipeline.stages.gloss_to_rough_conversion.ipu.save_image')
@mock.patch('processing.pipeline.stages.gloss_to_rough_conversion.ipu.load_image')
def test_gloss_conversion_uint8_success(mock_load_image, mock_save_image, mock_logging):
    """
    Test successful conversion of a GLOSS map (uint8 data) to ROUGHNESS.
    """
    stage = GlossToRoughConversionStage()
    
    gloss_rule_id = uuid.uuid4()
    # Use a distinct filename for the gloss map to ensure correct path construction
    gloss_fr = create_mock_file_rule_for_gloss_test(id_val=gloss_rule_id, map_type="GLOSS", filename_pattern="my_gloss_map.png")
    other_fr_id = uuid.uuid4()
    other_fr = create_mock_file_rule_for_gloss_test(id_val=other_fr_id, map_type="NORMAL", filename_pattern="normal_map.png")
    
    initial_gloss_temp_path = Path("/fake/temp_engine_dir/processed_gloss_map.png")
    initial_other_temp_path = Path("/fake/temp_engine_dir/processed_normal_map.png")

    initial_details = {
        gloss_fr.id.hex: {'temp_processed_file': str(initial_gloss_temp_path), 'status': 'Processed', 'map_type': 'GLOSS'},
        other_fr.id.hex: {'temp_processed_file': str(initial_other_temp_path), 'status': 'Processed', 'map_type': 'NORMAL'}
    }
    context = create_gloss_conversion_mock_context(
        initial_file_rules=[gloss_fr, other_fr],
        initial_processed_details=initial_details
    )

    mock_loaded_gloss_data = np.array([10, 50, 250], dtype=np.uint8)
    mock_load_image.return_value = mock_loaded_gloss_data
    mock_save_image.return_value = True # Simulate successful save
    
    updated_context = stage.execute(context)
    
    mock_load_image.assert_called_once_with(initial_gloss_temp_path)
    
    # Check that save_image was called with inverted data and correct path
    expected_inverted_data = 255 - mock_loaded_gloss_data
    
    # call_args[0] is a tuple of positional args, call_args[1] is a dict of kwargs
    saved_path_arg = mock_save_image.call_args[0][0]
    saved_data_arg = mock_save_image.call_args[0][1]
    
    assert np.array_equal(saved_data_arg, expected_inverted_data), "Image data passed to save_image is not correctly inverted."
    assert "rough_from_gloss_" in saved_path_arg.name, "Saved file name should indicate conversion from gloss."
    assert saved_path_arg.parent == Path("/fake/temp_engine_dir"), "Saved file should be in the engine temp directory."
    # Ensure the new filename is based on the original gloss map's ID for uniqueness
    assert gloss_fr.id.hex in saved_path_arg.name

    # Check context.files_to_process
    assert len(updated_context.files_to_process) == 2, "Number of file rules in context should remain the same."
    converted_rule_found = False
    other_rule_untouched = False
    for fr_in_list in updated_context.files_to_process:
        if fr_in_list.id == gloss_fr.id: # Should be the same rule object, modified
            assert fr_in_list.map_type == "ROUGHNESS", "GLOSS map_type should be changed to ROUGHNESS."
            # Check if filename_pattern was updated (optional, depends on stage logic)
            # For now, assume it might not be, as the primary identifier is map_type and ID
            converted_rule_found = True
        elif fr_in_list.id == other_fr.id:
            assert fr_in_list.map_type == "NORMAL", "Other map_type should remain unchanged."
            other_rule_untouched = True
    assert converted_rule_found, "The converted GLOSS rule was not found or not updated correctly in files_to_process."
    assert other_rule_untouched, "The non-GLOSS rule was modified unexpectedly."

    # Check context.processed_maps_details
    assert len(updated_context.processed_maps_details) == 2, "Number of entries in processed_maps_details should remain the same."
    
    gloss_detail = updated_context.processed_maps_details[gloss_fr.id.hex]
    assert "rough_from_gloss_" in gloss_detail['temp_processed_file'], "temp_processed_file for gloss map not updated."
    assert Path(gloss_detail['temp_processed_file']).name == saved_path_arg.name, "Path in details should match saved path."
    assert gloss_detail['original_map_type_before_conversion'] == "GLOSS", "original_map_type_before_conversion not set correctly."
    assert "Converted from GLOSS to ROUGHNESS" in gloss_detail['notes'], "Conversion notes not added or incorrect."
    assert gloss_detail['map_type'] == "ROUGHNESS", "map_type in details not updated to ROUGHNESS."


    other_detail = updated_context.processed_maps_details[other_fr.id.hex]
    assert other_detail['temp_processed_file'] == str(initial_other_temp_path), "Other map's temp_processed_file should be unchanged."
    assert other_detail['map_type'] == "NORMAL", "Other map's map_type should be unchanged."
    assert 'original_map_type_before_conversion' not in other_detail, "Other map should not have conversion history."
    assert 'notes' not in other_detail or "Converted from GLOSS" not in other_detail['notes'], "Other map should not have conversion notes."

    mock_logging.info.assert_any_call(f"Successfully converted GLOSS map {gloss_fr.id.hex} to ROUGHNESS.")
@mock.patch('processing.pipeline.stages.gloss_to_rough_conversion.logging') # Mock logging
@mock.patch('processing.pipeline.stages.gloss_to_rough_conversion.ipu.save_image')
@mock.patch('processing.pipeline.stages.gloss_to_rough_conversion.ipu.load_image')
def test_gloss_conversion_float_success(mock_load_image, mock_save_image, mock_logging):
    """
    Test successful conversion of a GLOSS map (float data) to ROUGHNESS.
    """
    stage = GlossToRoughConversionStage()
    
    gloss_rule_id = uuid.uuid4()
    gloss_fr = create_mock_file_rule_for_gloss_test(id_val=gloss_rule_id, map_type="GLOSS", filename_pattern="gloss_float.hdr") # Example float format
    
    initial_gloss_temp_path = Path("/fake/temp_engine_dir/processed_gloss_float.hdr")
    initial_details = {
        gloss_fr.id.hex: {'temp_processed_file': str(initial_gloss_temp_path), 'status': 'Processed', 'map_type': 'GLOSS'}
    }
    context = create_gloss_conversion_mock_context(
        initial_file_rules=[gloss_fr],
        initial_processed_details=initial_details
    )

    mock_loaded_gloss_data = np.array([0.1, 0.5, 0.9], dtype=np.float32)
    mock_load_image.return_value = mock_loaded_gloss_data
    mock_save_image.return_value = True # Simulate successful save
    
    updated_context = stage.execute(context)
    
    mock_load_image.assert_called_once_with(initial_gloss_temp_path)
    
    expected_inverted_data = 1.0 - mock_loaded_gloss_data
    
    saved_path_arg = mock_save_image.call_args[0][0]
    saved_data_arg = mock_save_image.call_args[0][1]
    
    assert np.allclose(saved_data_arg, expected_inverted_data), "Image data (float) passed to save_image is not correctly inverted."
    assert "rough_from_gloss_" in saved_path_arg.name, "Saved file name should indicate conversion from gloss."
    assert saved_path_arg.parent == Path("/fake/temp_engine_dir"), "Saved file should be in the engine temp directory."
    assert gloss_fr.id.hex in saved_path_arg.name

    assert len(updated_context.files_to_process) == 1
    converted_rule = updated_context.files_to_process[0]
    assert converted_rule.id == gloss_fr.id
    assert converted_rule.map_type == "ROUGHNESS"

    gloss_detail = updated_context.processed_maps_details[gloss_fr.id.hex]
    assert "rough_from_gloss_" in gloss_detail['temp_processed_file']
    assert Path(gloss_detail['temp_processed_file']).name == saved_path_arg.name
    assert gloss_detail['original_map_type_before_conversion'] == "GLOSS"
    assert "Converted from GLOSS to ROUGHNESS" in gloss_detail['notes']
    assert gloss_detail['map_type'] == "ROUGHNESS"

    mock_logging.info.assert_any_call(f"Successfully converted GLOSS map {gloss_fr.id.hex} to ROUGHNESS.")
@mock.patch('processing.pipeline.stages.gloss_to_rough_conversion.logging')
@mock.patch('processing.pipeline.stages.gloss_to_rough_conversion.ipu.save_image')
@mock.patch('processing.pipeline.stages.gloss_to_rough_conversion.ipu.load_image')
def test_load_image_fails(mock_load_image, mock_save_image, mock_logging):
    """
    Test behavior when ipu.load_image fails (returns None).
    The original FileRule should be kept, and an error logged.
    """
    stage = GlossToRoughConversionStage()
    
    gloss_rule_id = uuid.uuid4()
    gloss_fr = create_mock_file_rule_for_gloss_test(id_val=gloss_rule_id, map_type="GLOSS", filename_pattern="gloss_fails_load.png")
    
    initial_gloss_temp_path = Path("/fake/temp_engine_dir/processed_gloss_fails_load.png")
    initial_details = {
        gloss_fr.id.hex: {'temp_processed_file': str(initial_gloss_temp_path), 'status': 'Processed', 'map_type': 'GLOSS'}
    }
    context = create_gloss_conversion_mock_context(
        initial_file_rules=[gloss_fr],
        initial_processed_details=initial_details
    )
    
    # Keep a copy for comparison
    original_file_rule_map_type = gloss_fr.map_type 
    original_details_entry = context.processed_maps_details[gloss_fr.id.hex].copy()

    mock_load_image.return_value = None # Simulate load failure
    
    updated_context = stage.execute(context)
    
    mock_load_image.assert_called_once_with(initial_gloss_temp_path)
    mock_save_image.assert_not_called() # Save should not be attempted
    
    # Check context.files_to_process: rule should be unchanged
    assert len(updated_context.files_to_process) == 1
    processed_rule = updated_context.files_to_process[0]
    assert processed_rule.id == gloss_fr.id
    assert processed_rule.map_type == original_file_rule_map_type, "FileRule map_type should not change if load fails."
    assert processed_rule.map_type == "GLOSS" # Explicitly check it's still GLOSS

    # Check context.processed_maps_details: details should be unchanged
    current_details_entry = updated_context.processed_maps_details[gloss_fr.id.hex]
    assert current_details_entry['temp_processed_file'] == str(initial_gloss_temp_path)
    assert current_details_entry['map_type'] == "GLOSS"
    assert 'original_map_type_before_conversion' not in current_details_entry
    assert 'notes' not in current_details_entry or "Converted from GLOSS" not in current_details_entry['notes']
    
    mock_logging.error.assert_called_once_with(
        f"Failed to load image data for GLOSS map {gloss_fr.id.hex} from {initial_gloss_temp_path}. Skipping conversion for this map."
    )
@mock.patch('processing.pipeline.stages.gloss_to_rough_conversion.logging')
@mock.patch('processing.pipeline.stages.gloss_to_rough_conversion.ipu.save_image')
@mock.patch('processing.pipeline.stages.gloss_to_rough_conversion.ipu.load_image')
def test_save_image_fails(mock_load_image, mock_save_image, mock_logging):
    """
    Test behavior when ipu.save_image fails (returns False).
    The original FileRule should be kept, and an error logged.
    """
    stage = GlossToRoughConversionStage()
    
    gloss_rule_id = uuid.uuid4()
    gloss_fr = create_mock_file_rule_for_gloss_test(id_val=gloss_rule_id, map_type="GLOSS", filename_pattern="gloss_fails_save.png")
    
    initial_gloss_temp_path = Path("/fake/temp_engine_dir/processed_gloss_fails_save.png")
    initial_details = {
        gloss_fr.id.hex: {'temp_processed_file': str(initial_gloss_temp_path), 'status': 'Processed', 'map_type': 'GLOSS'}
    }
    context = create_gloss_conversion_mock_context(
        initial_file_rules=[gloss_fr],
        initial_processed_details=initial_details
    )
    
    original_file_rule_map_type = gloss_fr.map_type
    original_details_entry = context.processed_maps_details[gloss_fr.id.hex].copy()

    mock_loaded_gloss_data = np.array([10, 50, 250], dtype=np.uint8)
    mock_load_image.return_value = mock_loaded_gloss_data
    mock_save_image.return_value = False # Simulate save failure
    
    updated_context = stage.execute(context)
    
    mock_load_image.assert_called_once_with(initial_gloss_temp_path)
    
    # Check that save_image was called with correct data and path
    expected_inverted_data = 255 - mock_loaded_gloss_data
    # call_args[0] is a tuple of positional args
    saved_path_arg = mock_save_image.call_args[0][0]
    saved_data_arg = mock_save_image.call_args[0][1]
    
    assert np.array_equal(saved_data_arg, expected_inverted_data), "Image data passed to save_image is not correctly inverted even on failure."
    assert "rough_from_gloss_" in saved_path_arg.name, "Attempted save file name should indicate conversion from gloss."
    assert saved_path_arg.parent == Path("/fake/temp_engine_dir"), "Attempted save file should be in the engine temp directory."

    # Check context.files_to_process: rule should be unchanged
    assert len(updated_context.files_to_process) == 1
    processed_rule = updated_context.files_to_process[0]
    assert processed_rule.id == gloss_fr.id
    assert processed_rule.map_type == original_file_rule_map_type, "FileRule map_type should not change if save fails."
    assert processed_rule.map_type == "GLOSS"

    # Check context.processed_maps_details: details should be unchanged
    current_details_entry = updated_context.processed_maps_details[gloss_fr.id.hex]
    assert current_details_entry['temp_processed_file'] == str(initial_gloss_temp_path)
    assert current_details_entry['map_type'] == "GLOSS"
    assert 'original_map_type_before_conversion' not in current_details_entry
    assert 'notes' not in current_details_entry or "Converted from GLOSS" not in current_details_entry['notes']
    
    mock_logging.error.assert_called_once_with(
        f"Failed to save inverted GLOSS map {gloss_fr.id.hex} to {saved_path_arg}. Retaining original GLOSS map."
    )
@mock.patch('processing.pipeline.stages.gloss_to_rough_conversion.logging')
@mock.patch('processing.pipeline.stages.gloss_to_rough_conversion.ipu.save_image')
@mock.patch('processing.pipeline.stages.gloss_to_rough_conversion.ipu.load_image')
def test_gloss_map_in_files_to_process_but_not_in_details(mock_load_image, mock_save_image, mock_logging):
    """
    Test behavior when a GLOSS FileRule is in files_to_process but its details
    are missing from processed_maps_details.
    The stage should log an error and skip this FileRule.
    """
    stage = GlossToRoughConversionStage()
    
    gloss_rule_id = uuid.uuid4()
    # This FileRule is in files_to_process
    gloss_fr_in_list = create_mock_file_rule_for_gloss_test(id_val=gloss_rule_id, map_type="GLOSS", filename_pattern="orphan_gloss.png")
    
    # processed_maps_details is empty or does not contain gloss_fr_in_list.id.hex
    initial_details = {} 
    
    context = create_gloss_conversion_mock_context(
        initial_file_rules=[gloss_fr_in_list],
        initial_processed_details=initial_details 
    )
    
    original_files_to_process = list(context.files_to_process)
    original_processed_maps_details = context.processed_maps_details.copy()
    
    updated_context = stage.execute(context)
    
    mock_load_image.assert_not_called() # Load should not be attempted if details are missing
    mock_save_image.assert_not_called() # Save should not be attempted
    
    # Check context.files_to_process: rule should be unchanged
    assert len(updated_context.files_to_process) == 1
    processed_rule = updated_context.files_to_process[0]
    assert processed_rule.id == gloss_fr_in_list.id
    assert processed_rule.map_type == "GLOSS", "FileRule map_type should not change if its details are missing."

    # Check context.processed_maps_details: should remain unchanged
    assert updated_context.processed_maps_details == original_processed_maps_details, "processed_maps_details should not change."
    
    mock_logging.error.assert_called_once_with(
        f"GLOSS map {gloss_fr_in_list.id.hex} found in files_to_process but missing from processed_maps_details. Skipping conversion."
    )

# Test for Case 8.2 (GLOSS map ID in processed_maps_details but no corresponding FileRule in files_to_process)
# This case is implicitly handled because the stage iterates files_to_process.
# If a FileRule isn't in files_to_process, its corresponding entry in processed_maps_details (if any) won't be acted upon.
# We can add a simple test to ensure no errors occur and non-relevant details are untouched.

@mock.patch('processing.pipeline.stages.gloss_to_rough_conversion.logging')
@mock.patch('processing.pipeline.stages.gloss_to_rough_conversion.ipu.save_image')
@mock.patch('processing.pipeline.stages.gloss_to_rough_conversion.ipu.load_image')
def test_gloss_detail_exists_but_not_in_files_to_process(mock_load_image, mock_save_image, mock_logging):
    """
    Test that if a GLOSS map detail exists in processed_maps_details but
    no corresponding FileRule is in files_to_process, it's simply ignored
    without error, and other valid conversions proceed.
    """
    stage = GlossToRoughConversionStage()

    # This rule will be processed
    convert_rule_id = uuid.uuid4()
    convert_fr = create_mock_file_rule_for_gloss_test(id_val=convert_rule_id, map_type="GLOSS", filename_pattern="convert_me.png")
    convert_initial_temp_path = Path("/fake/temp_engine_dir/processed_convert_me.png")

    # This rule's details exist, but the rule itself is not in files_to_process
    orphan_detail_id = uuid.uuid4()
    
    initial_details = {
        convert_fr.id.hex: {'temp_processed_file': str(convert_initial_temp_path), 'status': 'Processed', 'map_type': 'GLOSS'},
        orphan_detail_id.hex: {'temp_processed_file': '/fake/temp_engine_dir/orphan.png', 'status': 'Processed', 'map_type': 'GLOSS', 'notes': 'This is an orphan'}
    }
    
    context = create_gloss_conversion_mock_context(
        initial_file_rules=[convert_fr], # Only convert_fr is in files_to_process
        initial_processed_details=initial_details
    )
    
    mock_loaded_data = np.array([100], dtype=np.uint8)
    mock_load_image.return_value = mock_loaded_data
    mock_save_image.return_value = True

    updated_context = stage.execute(context)

    # Assert that load/save were called only for the rule in files_to_process
    mock_load_image.assert_called_once_with(convert_initial_temp_path)
    mock_save_image.assert_called_once() # Check it was called, details checked in other tests

    # Check that the orphan detail in processed_maps_details is untouched
    assert orphan_detail_id.hex in updated_context.processed_maps_details
    orphan_entry = updated_context.processed_maps_details[orphan_detail_id.hex]
    assert orphan_entry['temp_processed_file'] == '/fake/temp_engine_dir/orphan.png'
    assert orphan_entry['map_type'] == 'GLOSS'
    assert orphan_entry['notes'] == 'This is an orphan'
    assert 'original_map_type_before_conversion' not in orphan_entry

    # Check that the processed rule was indeed converted
    assert convert_fr.id.hex in updated_context.processed_maps_details
    converted_entry = updated_context.processed_maps_details[convert_fr.id.hex]
    assert converted_entry['map_type'] == 'ROUGHNESS'
    assert "rough_from_gloss_" in converted_entry['temp_processed_file']

    # No errors should have been logged regarding the orphan detail
    for call_args in mock_logging.error.call_args_list:
        assert str(orphan_detail_id.hex) not in call_args[0][0], "Error logged for orphan detail"