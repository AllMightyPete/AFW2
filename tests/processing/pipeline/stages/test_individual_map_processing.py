import pytest
from unittest import mock
from pathlib import Path
import uuid
import numpy as np
from typing import Optional # Added for type hinting in helper functions

from processing.pipeline.stages.individual_map_processing import IndividualMapProcessingStage
from processing.pipeline.asset_context import AssetProcessingContext
from rule_structure import AssetRule, SourceRule, FileRule # Key models
from configuration import Configuration, GeneralSettings
# cv2 might be imported by the stage for interpolation constants, ensure it's mockable if so.
# For now, assume ipu handles interpolation details.

def create_mock_transform_settings(
    target_width=0, target_height=0, resize_mode="FIT",
    ensure_pot=False, allow_upscale=True, target_color_profile="RGB" # Add other fields as needed
) -> mock.MagicMock:
    ts = mock.MagicMock(spec=TransformSettings)
    ts.target_width = target_width
    ts.target_height = target_height
    ts.resize_mode = resize_mode
    ts.ensure_pot = ensure_pot
    ts.allow_upscale = allow_upscale
    ts.target_color_profile = target_color_profile
    # ts.resize_filter = "AREA" # if your stage uses this
    return ts

def create_mock_file_rule_for_individual_processing(
    id_val: Optional[uuid.UUID] = None,
    map_type: str = "ALBEDO",
    filename_pattern: str = "albedo_*.png", # Pattern for glob
    item_type: str = "MAP_COL",
    active: bool = True,
    transform_settings: Optional[mock.MagicMock] = None
) -> mock.MagicMock:
    mock_fr = mock.MagicMock(spec=FileRule)
    mock_fr.id = id_val if id_val else uuid.uuid4()
    mock_fr.map_type = map_type
    mock_fr.filename_pattern = filename_pattern
    mock_fr.item_type = item_type
    mock_fr.active = active
    mock_fr.transform_settings = transform_settings if transform_settings else create_mock_transform_settings()
    return mock_fr

def create_individual_map_proc_mock_context(
    initial_file_rules: Optional[list] = None,
    asset_source_path_str: str = "/fake/asset_source",
    skip_asset_flag: bool = False,
    asset_name: str = "IndividualMapAsset"
) -> AssetProcessingContext:
    mock_asset_rule = mock.MagicMock(spec=AssetRule)
    mock_asset_rule.name = asset_name
    mock_asset_rule.source_path = Path(asset_source_path_str)
    # file_rules on AssetRule not directly used by stage, context.files_to_process is

    mock_source_rule = mock.MagicMock(spec=SourceRule)
    mock_config = mock.MagicMock(spec=Configuration)
    # mock_config.general_settings = mock.MagicMock(spec=GeneralSettings) # If needed

    context = AssetProcessingContext(
        source_rule=mock_source_rule,
        asset_rule=mock_asset_rule,
        workspace_path=Path("/fake/workspace"),
        engine_temp_dir=Path("/fake/temp_engine_dir"),
        output_base_path=Path("/fake/output"),
        effective_supplier="ValidSupplier",
        asset_metadata={'asset_name': asset_name},
        processed_maps_details={}, # Stage populates this
        merged_maps_details={},
        files_to_process=list(initial_file_rules) if initial_file_rules else [],
        loaded_data_cache={},
        config_obj=mock_config,
        status_flags={'skip_asset': skip_asset_flag},
        incrementing_value=None,
        sha5_value=None # Corrected from sha5_value to sha_value if that's the actual param
    )
    return context

# Placeholder for tests to be added next
@mock.patch('processing.pipeline.stages.individual_map_processing.ipu')
@mock.patch('logging.info')
def test_asset_skipped_if_flag_is_true(mock_log_info, mock_ipu):
    stage = IndividualMapProcessingStage()
    context = create_individual_map_proc_mock_context(skip_asset_flag=True)
    
    # Add a dummy file rule to ensure it's not processed
    file_rule = create_mock_file_rule_for_individual_processing()
    context.files_to_process = [file_rule]

    updated_context = stage.execute(context)

    mock_ipu.load_image.assert_not_called()
    mock_ipu.save_image.assert_not_called()
    assert not updated_context.processed_maps_details # No details should be added
    # Check for a log message indicating skip, if applicable (depends on stage's logging)
    # mock_log_info.assert_any_call("Skipping asset IndividualMapAsset due to status_flags['skip_asset'] = True") # Example


@mock.patch('processing.pipeline.stages.individual_map_processing.ipu')
@mock.patch('logging.info')
def test_no_processing_if_no_map_col_rules(mock_log_info, mock_ipu):
    stage = IndividualMapProcessingStage()
    
    # Create a file rule that is NOT of item_type MAP_COL
    non_map_col_rule = create_mock_file_rule_for_individual_processing(item_type="METADATA")
    context = create_individual_map_proc_mock_context(initial_file_rules=[non_map_col_rule])

    updated_context = stage.execute(context)

    mock_ipu.load_image.assert_not_called()
    mock_ipu.save_image.assert_not_called()
    assert not updated_context.processed_maps_details
    # mock_log_info.assert_any_call("No FileRules of item_type 'MAP_COL' to process for asset IndividualMapAsset.") # Example


@mock.patch('processing.pipeline.stages.individual_map_processing.ipu.save_image')
@mock.patch('processing.pipeline.stages.individual_map_processing.ipu.resize_image')
@mock.patch('processing.pipeline.stages.individual_map_processing.ipu.calculate_target_dimensions')
@mock.patch('processing.pipeline.stages.individual_map_processing.ipu.load_image')
@mock.patch('pathlib.Path.glob') # Mocking Path.glob used by the stage's _find_source_file
@mock.patch('logging.info')
@mock.patch('logging.error')
def test_individual_map_processing_success_no_resize(
    mock_log_error, mock_log_info, mock_path_glob, mock_load_image,
    mock_calc_dims, mock_resize_image, mock_save_image
):
    stage = IndividualMapProcessingStage()

    source_file_name = "albedo_source.png"
    # The glob is called on context.asset_rule.source_path, so mock that Path object's glob
    mock_asset_source_path = Path("/fake/asset_source")
    mock_found_source_path = mock_asset_source_path / source_file_name
    
    # We need to mock the glob method of the Path instance
    # that represents the asset's source directory.
    # The stage does something like: Path(context.asset_rule.source_path).glob(...)
    # So, we need to ensure that when Path() is called with that specific string,
    # the resulting object's glob method is our mock.
    # A more robust way is to mock Path itself to return a mock object
    # whose glob method is also a mock.

    # Simpler approach for now: assume Path.glob is used as a static/class method call
    # or that the instance it's called on is correctly patched by @mock.patch('pathlib.Path.glob')
    # if the stage does `from pathlib import Path` and then `Path(path_str).glob(...)`.
    # The prompt example uses @mock.patch('pathlib.Path.glob'), implying the stage might do this:
    # for f_pattern in patterns:
    #   for found_file in Path(base_dir).glob(f_pattern): ...
    # Let's refine the mock_path_glob setup.
    # The stage's _find_source_file likely does:
    # search_path = Path(self.context.asset_rule.source_path)
    # found_files = list(search_path.glob(filename_pattern))

    # To correctly mock this, we need to mock the `glob` method of the specific Path instance.
    # Or, if `_find_source_file` instantiates `Path` like `Path(str(context.asset_rule.source_path)).glob(...)`,
    # then patching `pathlib.Path.glob` might work if it's treated as a method that gets bound.
    # Let's stick to the example's @mock.patch('pathlib.Path.glob') and assume it covers the usage.
    mock_path_glob.return_value = [mock_found_source_path] # Glob finds one file

    ts = create_mock_transform_settings(target_width=100, target_height=100)
    file_rule = create_mock_file_rule_for_individual_processing(
        map_type="ALBEDO", filename_pattern="albedo_*.png", transform_settings=ts
    )
    context = create_individual_map_proc_mock_context(
        initial_file_rules=[file_rule],
        asset_source_path_str=str(mock_asset_source_path) # Ensure context uses this path
    )

    mock_img_data = np.zeros((100, 100, 3), dtype=np.uint8) # Original dimensions
    mock_load_image.return_value = mock_img_data
    mock_calc_dims.return_value = (100, 100) # No resize needed
    mock_save_image.return_value = True

    updated_context = stage.execute(context)

    # Assert that Path(context.asset_rule.source_path).glob was called
    # This requires a bit more intricate mocking if Path instances are created inside.
    # For now, assert mock_path_glob was called with the pattern.
    # The actual call in stage is `Path(context.asset_rule.source_path).glob(file_rule.filename_pattern)`
    # So, `mock_path_glob` (if it patches `Path.glob` globally) should be called.
    # We need to ensure the mock_path_glob is associated with the correct Path instance or that
    # the global patch works as intended.
    # A common pattern is:
    # with mock.patch.object(Path, 'glob', return_value=[mock_found_source_path]) as specific_glob_mock:
    #    # execute code
    #    specific_glob_mock.assert_called_once_with(file_rule.filename_pattern)
    # However, the decorator @mock.patch('pathlib.Path.glob') should work if the stage code is
    # `from pathlib import Path; p = Path(...); p.glob(...)`
    
    # The stage's _find_source_file will instantiate a Path object from context.asset_rule.source_path
    # and then call glob on it.
    # So, @mock.patch('pathlib.Path.glob') is patching the method on the class.
    # When an instance calls it, the mock is used.
    mock_path_glob.assert_called_once_with(file_rule.filename_pattern)


    mock_load_image.assert_called_once_with(mock_found_source_path)
    # The actual call to calculate_target_dimensions is:
    # ipu.calculate_target_dimensions(original_dims, ts.target_width, ts.target_height, ts.resize_mode, ts.ensure_pot, ts.allow_upscale)
    mock_calc_dims.assert_called_once_with(
        (100, 100), ts.target_width, ts.target_height, ts.resize_mode, ts.ensure_pot, ts.allow_upscale
    )
    mock_resize_image.assert_not_called() # Crucial for this test case
    mock_save_image.assert_called_once()

    # Check save path and data
    saved_image_arg, saved_path_arg = mock_save_image.call_args[0]
    assert np.array_equal(saved_image_arg, mock_img_data) # Ensure correct image data is passed to save
    assert "processed_ALBEDO_" in saved_path_arg.name # Based on map_type
    assert file_rule.id.hex in saved_path_arg.name # Ensure unique name with FileRule ID
    assert saved_path_arg.parent == context.engine_temp_dir

    assert file_rule.id.hex in updated_context.processed_maps_details
    details = updated_context.processed_maps_details[file_rule.id.hex]
    assert details['status'] == 'Processed'
    assert details['source_file'] == str(mock_found_source_path)
    assert Path(details['temp_processed_file']) == saved_path_arg
    assert details['original_dimensions'] == (100, 100)
    assert details['processed_dimensions'] == (100, 100)
    assert details['map_type'] == file_rule.map_type
    mock_log_error.assert_not_called()
    mock_log_info.assert_any_call(f"Successfully processed map {file_rule.map_type} (ID: {file_rule.id.hex}) for asset {context.asset_rule.name}. Output: {saved_path_arg}")


@mock.patch('processing.pipeline.stages.individual_map_processing.ipu.save_image')
@mock.patch('processing.pipeline.stages.individual_map_processing.ipu.resize_image')
@mock.patch('processing.pipeline.stages.individual_map_processing.ipu.calculate_target_dimensions')
@mock.patch('processing.pipeline.stages.individual_map_processing.ipu.load_image')
@mock.patch('pathlib.Path.glob')
@mock.patch('logging.info')
@mock.patch('logging.error')
def test_source_file_not_found(
    mock_log_error, mock_log_info, mock_path_glob, mock_load_image,
    mock_calc_dims, mock_resize_image, mock_save_image
):
    stage = IndividualMapProcessingStage()
    mock_asset_source_path = Path("/fake/asset_source")
    
    mock_path_glob.return_value = [] # Glob finds no files

    file_rule = create_mock_file_rule_for_individual_processing(filename_pattern="nonexistent_*.png")
    context = create_individual_map_proc_mock_context(
        initial_file_rules=[file_rule],
        asset_source_path_str=str(mock_asset_source_path)
    )

    updated_context = stage.execute(context)

    mock_path_glob.assert_called_once_with(file_rule.filename_pattern)
    mock_load_image.assert_not_called()
    mock_calc_dims.assert_not_called()
    mock_resize_image.assert_not_called()
    mock_save_image.assert_not_called()

    assert file_rule.id.hex in updated_context.processed_maps_details
    details = updated_context.processed_maps_details[file_rule.id.hex]
    assert details['status'] == 'Source Not Found'
    assert details['source_file'] is None
    assert details['temp_processed_file'] is None
    assert details['error_message'] is not None # Check an error message is present
    mock_log_error.assert_called_once()
    # Example: mock_log_error.assert_called_with(f"Could not find source file for rule {file_rule.id} (pattern: {file_rule.filename_pattern}) in {context.asset_rule.source_path}")


@mock.patch('processing.pipeline.stages.individual_map_processing.ipu.save_image')
@mock.patch('processing.pipeline.stages.individual_map_processing.ipu.resize_image')
@mock.patch('processing.pipeline.stages.individual_map_processing.ipu.calculate_target_dimensions')
@mock.patch('processing.pipeline.stages.individual_map_processing.ipu.load_image')
@mock.patch('pathlib.Path.glob')
@mock.patch('logging.info')
@mock.patch('logging.error')
def test_load_image_fails(
    mock_log_error, mock_log_info, mock_path_glob, mock_load_image,
    mock_calc_dims, mock_resize_image, mock_save_image
):
    stage = IndividualMapProcessingStage()
    source_file_name = "albedo_corrupt.png"
    mock_asset_source_path = Path("/fake/asset_source")
    mock_found_source_path = mock_asset_source_path / source_file_name
    mock_path_glob.return_value = [mock_found_source_path]

    mock_load_image.return_value = None # Simulate load failure

    file_rule = create_mock_file_rule_for_individual_processing(filename_pattern="albedo_*.png")
    context = create_individual_map_proc_mock_context(
        initial_file_rules=[file_rule],
        asset_source_path_str=str(mock_asset_source_path)
    )

    updated_context = stage.execute(context)

    mock_path_glob.assert_called_once_with(file_rule.filename_pattern)
    mock_load_image.assert_called_once_with(mock_found_source_path)
    mock_calc_dims.assert_not_called()
    mock_resize_image.assert_not_called()
    mock_save_image.assert_not_called()

    assert file_rule.id.hex in updated_context.processed_maps_details
    details = updated_context.processed_maps_details[file_rule.id.hex]
    assert details['status'] == 'Load Failed'
    assert details['source_file'] == str(mock_found_source_path)
    assert details['temp_processed_file'] is None
    assert details['error_message'] is not None
    mock_log_error.assert_called_once()
    # Example: mock_log_error.assert_called_with(f"Failed to load image {mock_found_source_path} for rule {file_rule.id}")


@mock.patch('processing.pipeline.stages.individual_map_processing.ipu.save_image')
@mock.patch('processing.pipeline.stages.individual_map_processing.ipu.resize_image')
@mock.patch('processing.pipeline.stages.individual_map_processing.ipu.calculate_target_dimensions')
@mock.patch('processing.pipeline.stages.individual_map_processing.ipu.load_image')
@mock.patch('pathlib.Path.glob')
@mock.patch('logging.info')
@mock.patch('logging.error')
def test_resize_occurs_when_dimensions_differ(
    mock_log_error, mock_log_info, mock_path_glob, mock_load_image,
    mock_calc_dims, mock_resize_image, mock_save_image
):
    stage = IndividualMapProcessingStage()
    source_file_name = "albedo_resize.png"
    mock_asset_source_path = Path("/fake/asset_source")
    mock_found_source_path = mock_asset_source_path / source_file_name
    mock_path_glob.return_value = [mock_found_source_path]

    original_dims = (100, 100)
    target_dims = (50, 50) # Different dimensions
    mock_img_data = np.zeros((*original_dims, 3), dtype=np.uint8)
    mock_resized_img_data = np.zeros((*target_dims, 3), dtype=np.uint8)

    mock_load_image.return_value = mock_img_data
    ts = create_mock_transform_settings(target_width=target_dims[0], target_height=target_dims[1])
    file_rule = create_mock_file_rule_for_individual_processing(transform_settings=ts)
    context = create_individual_map_proc_mock_context(
        initial_file_rules=[file_rule],
        asset_source_path_str=str(mock_asset_source_path)
    )
    
    mock_calc_dims.return_value = target_dims # Simulate calc_dims returning new dimensions
    mock_resize_image.return_value = mock_resized_img_data # Simulate resize returning new image data
    mock_save_image.return_value = True

    updated_context = stage.execute(context)

    mock_load_image.assert_called_once_with(mock_found_source_path)
    mock_calc_dims.assert_called_once_with(
        original_dims, ts.target_width, ts.target_height, ts.resize_mode, ts.ensure_pot, ts.allow_upscale
    )
    # The actual call to resize_image is:
    # ipu.resize_image(loaded_image, target_dims, ts.resize_filter) # Assuming resize_filter is used
    # If resize_filter is not on TransformSettings or not used, adjust this.
    # For now, let's assume it's ipu.resize_image(loaded_image, target_dims) or similar
    # The stage code is: resized_image = ipu.resize_image(loaded_image, target_dims_calculated, file_rule.transform_settings.resize_filter)
    # So we need to mock ts.resize_filter
    ts.resize_filter = "LANCZOS4" # Example filter
    mock_resize_image.assert_called_once_with(mock_img_data, target_dims, ts.resize_filter)
    
    saved_image_arg, saved_path_arg = mock_save_image.call_args[0]
    assert np.array_equal(saved_image_arg, mock_resized_img_data) # Check resized data is saved
    assert "processed_ALBEDO_" in saved_path_arg.name
    assert saved_path_arg.parent == context.engine_temp_dir

    assert file_rule.id.hex in updated_context.processed_maps_details
    details = updated_context.processed_maps_details[file_rule.id.hex]
    assert details['status'] == 'Processed'
    assert details['original_dimensions'] == original_dims
    assert details['processed_dimensions'] == target_dims
    mock_log_error.assert_not_called()


@mock.patch('processing.pipeline.stages.individual_map_processing.ipu.save_image')
@mock.patch('processing.pipeline.stages.individual_map_processing.ipu.resize_image')
@mock.patch('processing.pipeline.stages.individual_map_processing.ipu.calculate_target_dimensions')
@mock.patch('processing.pipeline.stages.individual_map_processing.ipu.load_image')
@mock.patch('pathlib.Path.glob')
@mock.patch('logging.info')
@mock.patch('logging.error')
def test_save_image_fails(
    mock_log_error, mock_log_info, mock_path_glob, mock_load_image,
    mock_calc_dims, mock_resize_image, mock_save_image
):
    stage = IndividualMapProcessingStage()
    source_file_name = "albedo_save_fail.png"
    mock_asset_source_path = Path("/fake/asset_source")
    mock_found_source_path = mock_asset_source_path / source_file_name
    mock_path_glob.return_value = [mock_found_source_path]

    mock_img_data = np.zeros((100, 100, 3), dtype=np.uint8)
    mock_load_image.return_value = mock_img_data
    mock_calc_dims.return_value = (100, 100) # No resize
    mock_save_image.return_value = False # Simulate save failure

    ts = create_mock_transform_settings()
    file_rule = create_mock_file_rule_for_individual_processing(transform_settings=ts)
    context = create_individual_map_proc_mock_context(
        initial_file_rules=[file_rule],
        asset_source_path_str=str(mock_asset_source_path)
    )

    updated_context = stage.execute(context)

    mock_save_image.assert_called_once() # Attempt to save should still happen
    
    assert file_rule.id.hex in updated_context.processed_maps_details
    details = updated_context.processed_maps_details[file_rule.id.hex]
    assert details['status'] == 'Save Failed'
    assert details['source_file'] == str(mock_found_source_path)
    assert details['temp_processed_file'] is not None # Path was generated
    assert details['error_message'] is not None
    mock_log_error.assert_called_once()
    # Example: mock_log_error.assert_called_with(f"Failed to save processed image for rule {file_rule.id} to {details['temp_processed_file']}")


@mock.patch('processing.pipeline.stages.individual_map_processing.ipu.save_image')
@mock.patch('processing.pipeline.stages.individual_map_processing.ipu.resize_image')
@mock.patch('processing.pipeline.stages.individual_map_processing.ipu.calculate_target_dimensions')
@mock.patch('processing.pipeline.stages.individual_map_processing.ipu.load_image')
@mock.patch('processing.pipeline.stages.individual_map_processing.ipu.convert_bgr_to_rgb')
@mock.patch('pathlib.Path.glob')
@mock.patch('logging.info')
@mock.patch('logging.error')
def test_color_conversion_bgr_to_rgb(
    mock_log_error, mock_log_info, mock_path_glob, mock_convert_bgr, mock_load_image,
    mock_calc_dims, mock_resize_image, mock_save_image
):
    stage = IndividualMapProcessingStage()
    source_file_name = "albedo_bgr.png"
    mock_asset_source_path = Path("/fake/asset_source")
    mock_found_source_path = mock_asset_source_path / source_file_name
    mock_path_glob.return_value = [mock_found_source_path]

    mock_bgr_img_data = np.zeros((100, 100, 3), dtype=np.uint8) # Loaded as BGR
    mock_rgb_img_data = np.zeros((100, 100, 3), dtype=np.uint8) # After conversion
    
    mock_load_image.return_value = mock_bgr_img_data # Image is loaded (assume BGR by default from cv2)
    mock_convert_bgr.return_value = mock_rgb_img_data # Mock the conversion
    mock_calc_dims.return_value = (100, 100) # No resize
    mock_save_image.return_value = True

    # Transform settings request RGB, and stage assumes load might be BGR
    ts = create_mock_transform_settings(target_color_profile="RGB") 
    file_rule = create_mock_file_rule_for_individual_processing(transform_settings=ts)
    context = create_individual_map_proc_mock_context(
        initial_file_rules=[file_rule],
        asset_source_path_str=str(mock_asset_source_path)
    )
    # The stage code is:
    # if file_rule.transform_settings.target_color_profile == "RGB" and loaded_image.shape[2] == 3:
    #     logger.info(f"Attempting to convert image from BGR to RGB for {file_rule_id_hex}")
    #     processed_image_data = ipu.convert_bgr_to_rgb(processed_image_data)

    updated_context = stage.execute(context)

    mock_load_image.assert_called_once_with(mock_found_source_path)
    mock_convert_bgr.assert_called_once_with(mock_bgr_img_data)
    mock_resize_image.assert_not_called()
    
    saved_image_arg, _ = mock_save_image.call_args[0]
    assert np.array_equal(saved_image_arg, mock_rgb_img_data) # Ensure RGB data is saved
    mock_log_error.assert_not_called()
    mock_log_info.assert_any_call(f"Attempting to convert image from BGR to RGB for {file_rule.id.hex}")


@mock.patch('processing.pipeline.stages.individual_map_processing.ipu.save_image')
@mock.patch('processing.pipeline.stages.individual_map_processing.ipu.resize_image')
@mock.patch('processing.pipeline.stages.individual_map_processing.ipu.calculate_target_dimensions')
@mock.patch('processing.pipeline.stages.individual_map_processing.ipu.load_image')
@mock.patch('pathlib.Path.glob')
@mock.patch('logging.info')
@mock.patch('logging.error')
def test_multiple_map_col_rules_processed(
    mock_log_error, mock_log_info, mock_path_glob, mock_load_image,
    mock_calc_dims, mock_resize_image, mock_save_image
):
    stage = IndividualMapProcessingStage()
    mock_asset_source_path = Path("/fake/asset_source")

    # Rule 1: Albedo
    ts1 = create_mock_transform_settings(target_width=100, target_height=100)
    file_rule1_id = uuid.uuid4()
    file_rule1 = create_mock_file_rule_for_individual_processing(
        id_val=file_rule1_id, map_type="ALBEDO", filename_pattern="albedo_*.png", transform_settings=ts1
    )
    source_file1 = mock_asset_source_path / "albedo_map.png"
    img_data1 = np.zeros((100, 100, 3), dtype=np.uint8)

    # Rule 2: Roughness
    ts2 = create_mock_transform_settings(target_width=50, target_height=50) # Resize
    ts2.resize_filter = "AREA"
    file_rule2_id = uuid.uuid4()
    file_rule2 = create_mock_file_rule_for_individual_processing(
        id_val=file_rule2_id, map_type="ROUGHNESS", filename_pattern="rough_*.png", transform_settings=ts2
    )
    source_file2 = mock_asset_source_path / "rough_map.png"
    img_data2_orig = np.zeros((200, 200, 1), dtype=np.uint8) # Original, needs resize
    img_data2_resized = np.zeros((50, 50, 1), dtype=np.uint8) # Resized

    context = create_individual_map_proc_mock_context(
        initial_file_rules=[file_rule1, file_rule2],
        asset_source_path_str=str(mock_asset_source_path)
    )

    # Mock behaviors for Path.glob, load_image, calc_dims, resize, save
    # Path.glob will be called twice
    mock_path_glob.side_effect = [
        [source_file1], # For albedo_*.png
        [source_file2]  # For rough_*.png
    ]
    mock_load_image.side_effect = [img_data1, img_data2_orig]
    mock_calc_dims.side_effect = [
        (100, 100), # For rule1 (no change)
        (50, 50)    # For rule2 (change)
    ]
    mock_resize_image.return_value = img_data2_resized # Only called for rule2
    mock_save_image.return_value = True

    updated_context = stage.execute(context)

    # Assertions for Rule 1 (Albedo)
    assert mock_path_glob.call_args_list[0][0][0] == file_rule1.filename_pattern
    assert mock_load_image.call_args_list[0][0][0] == source_file1
    assert mock_calc_dims.call_args_list[0][0] == ((100,100), ts1.target_width, ts1.target_height, ts1.resize_mode, ts1.ensure_pot, ts1.allow_upscale)
    
    # Assertions for Rule 2 (Roughness)
    assert mock_path_glob.call_args_list[1][0][0] == file_rule2.filename_pattern
    assert mock_load_image.call_args_list[1][0][0] == source_file2
    assert mock_calc_dims.call_args_list[1][0] == ((200,200), ts2.target_width, ts2.target_height, ts2.resize_mode, ts2.ensure_pot, ts2.allow_upscale)
    mock_resize_image.assert_called_once_with(img_data2_orig, (50,50), ts2.resize_filter)
    
    assert mock_save_image.call_count == 2
    # Check saved image for rule 1
    saved_img1_arg, saved_path1_arg = mock_save_image.call_args_list[0][0]
    assert np.array_equal(saved_img1_arg, img_data1)
    assert "processed_ALBEDO_" in saved_path1_arg.name
    assert file_rule1_id.hex in saved_path1_arg.name

    # Check saved image for rule 2
    saved_img2_arg, saved_path2_arg = mock_save_image.call_args_list[1][0]
    assert np.array_equal(saved_img2_arg, img_data2_resized)
    assert "processed_ROUGHNESS_" in saved_path2_arg.name
    assert file_rule2_id.hex in saved_path2_arg.name

    # Check context details
    assert file_rule1_id.hex in updated_context.processed_maps_details
    details1 = updated_context.processed_maps_details[file_rule1_id.hex]
    assert details1['status'] == 'Processed'
    assert details1['original_dimensions'] == (100, 100)
    assert details1['processed_dimensions'] == (100, 100)

    assert file_rule2_id.hex in updated_context.processed_maps_details
    details2 = updated_context.processed_maps_details[file_rule2_id.hex]
    assert details2['status'] == 'Processed'
    assert details2['original_dimensions'] == (200, 200) # Original dims of img_data2_orig
    assert details2['processed_dimensions'] == (50, 50)
    
    mock_log_error.assert_not_called()