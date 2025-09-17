import pytest
from unittest import mock
from pathlib import Path
import datetime
import json # For comparing dumped content
import uuid
from typing import Optional, Dict, Any

from processing.pipeline.stages.metadata_finalization_save import MetadataFinalizationAndSaveStage
from processing.pipeline.asset_context import AssetProcessingContext
from rule_structure import AssetRule, SourceRule
from configuration import Configuration, GeneralSettings # Added GeneralSettings as it's in the helper


def create_metadata_save_mock_context(
    status_flags: Optional[Dict[str, Any]] = None,
    initial_asset_metadata: Optional[Dict[str, Any]] = None,
    processed_details: Optional[Dict[str, Any]] = None,
    merged_details: Optional[Dict[str, Any]] = None,
    asset_name: str = "MetaSaveAsset",
    output_path_pattern_val: str = "{asset_name}/metadata/{filename}",
    # ... other common context fields ...
) -> AssetProcessingContext:
    mock_asset_rule = mock.MagicMock(spec=AssetRule)
    mock_asset_rule.name = asset_name
    mock_asset_rule.output_path_pattern = output_path_pattern_val
    mock_asset_rule.id = uuid.uuid4() # Needed for generate_path_from_pattern if it uses it

    mock_source_rule = mock.MagicMock(spec=SourceRule)
    mock_source_rule.name = "MetaSaveSource"
    
    mock_config = mock.MagicMock(spec=Configuration)
    # mock_config.general_settings = mock.MagicMock(spec=GeneralSettings) # If needed

    context = AssetProcessingContext(
        source_rule=mock_source_rule,
        asset_rule=mock_asset_rule,
        workspace_path=Path("/fake/workspace"),
        engine_temp_dir=Path("/fake/temp_engine_dir"),
        output_base_path=Path("/fake/output_base"), # For generate_path
        effective_supplier="ValidSupplier",
        asset_metadata=initial_asset_metadata if initial_asset_metadata is not None else {},
        processed_maps_details=processed_details if processed_details is not None else {},
        merged_maps_details=merged_details if merged_details is not None else {},
        files_to_process=[],
        loaded_data_cache={},
        config_obj=mock_config,
        status_flags=status_flags if status_flags is not None else {},
        incrementing_value="001", # Example for path generation
        sha5_value="abc"      # Example for path generation
    )
    return context
@mock.patch('processing.pipeline.stages.metadata_finalization_save.json.dump')
@mock.patch('builtins.open', new_callable=mock.mock_open)
@mock.patch('pathlib.Path.mkdir')
@mock.patch('processing.pipeline.stages.metadata_finalization_save.generate_path_from_pattern')
@mock.patch('datetime.datetime')
def test_asset_skipped_before_metadata_init(
    mock_dt, mock_gen_path, mock_mkdir, mock_file_open, mock_json_dump
):
    """
    Tests that if an asset is marked for skipping and has no initial metadata,
    the stage returns early without attempting to save metadata.
    """
    stage = MetadataFinalizationAndSaveStage()
    context = create_metadata_save_mock_context(
        status_flags={'skip_asset': True},
        initial_asset_metadata={} # Explicitly empty
    )

    updated_context = stage.execute(context)

    # Assert that no processing or saving attempts were made
    mock_dt.now.assert_not_called() # Should not even try to set end time if no metadata
    mock_gen_path.assert_not_called()
    mock_mkdir.assert_not_called()
    mock_file_open.assert_not_called()
    mock_json_dump.assert_not_called()

    assert updated_context.asset_metadata == {} # Metadata remains empty
    assert 'metadata_file_path' not in updated_context.asset_metadata
    assert updated_context.status_flags.get('metadata_save_error') is None
@mock.patch('processing.pipeline.stages.metadata_finalization_save.json.dump')
@mock.patch('builtins.open', new_callable=mock.mock_open)
@mock.patch('pathlib.Path.mkdir')
@mock.patch('processing.pipeline.stages.metadata_finalization_save.generate_path_from_pattern')
@mock.patch('datetime.datetime')
def test_asset_skipped_after_metadata_init(
    mock_dt, mock_gen_path, mock_mkdir, mock_file_open, mock_json_dump
):
    """
    Tests that if an asset is marked for skipping but has initial metadata,
    the status is updated to 'Skipped' and metadata is saved.
    """
    stage = MetadataFinalizationAndSaveStage()
    
    fixed_now = datetime.datetime(2023, 1, 1, 12, 0, 0)
    mock_dt.now.return_value = fixed_now
    
    fake_metadata_path_str = "/fake/output_base/SkippedAsset/metadata/SkippedAsset_metadata.json"
    mock_gen_path.return_value = fake_metadata_path_str
    
    initial_meta = {'asset_name': "SkippedAsset", 'status': "Pending"}
    
    context = create_metadata_save_mock_context(
        asset_name="SkippedAsset",
        status_flags={'skip_asset': True},
        initial_asset_metadata=initial_meta
    )
    
    updated_context = stage.execute(context)
    
    mock_dt.now.assert_called_once()
    mock_gen_path.assert_called_once_with(
        context.asset_rule.output_path_pattern,
        context.asset_rule,
        context.source_rule,
        context.output_base_path,
        context.asset_metadata, # Original metadata passed for path gen
        context.incrementing_value,
        context.sha5_value,
        filename_override=f"{context.asset_rule.name}_metadata.json"
    )
    mock_mkdir.assert_called_once_with(parents=True, exist_ok=True)
    mock_file_open.assert_called_once_with(Path(fake_metadata_path_str), 'w')
    mock_json_dump.assert_called_once()
    
    dumped_data = mock_json_dump.call_args[0][0]
    assert dumped_data['status'] == "Skipped"
    assert dumped_data['processing_end_time'] == fixed_now.isoformat()
    assert 'processed_map_details' not in dumped_data # Should not be present if skipped early
    assert 'merged_map_details' not in dumped_data   # Should not be present if skipped early
    
    assert updated_context.asset_metadata['status'] == "Skipped"
    assert updated_context.asset_metadata['processing_end_time'] == fixed_now.isoformat()
    assert updated_context.asset_metadata['metadata_file_path'] == fake_metadata_path_str
    assert updated_context.status_flags.get('metadata_save_error') is None
@mock.patch('processing.pipeline.stages.metadata_finalization_save.json.dump')
@mock.patch('builtins.open', new_callable=mock.mock_open) # Mocks open()
@mock.patch('pathlib.Path.mkdir')
@mock.patch('processing.pipeline.stages.metadata_finalization_save.generate_path_from_pattern')
@mock.patch('datetime.datetime')
def test_metadata_save_success(mock_dt, mock_gen_path, mock_mkdir, mock_file_open, mock_json_dump):
    """
    Tests successful metadata finalization and saving, including serialization of Path objects.
    """
    stage = MetadataFinalizationAndSaveStage()
    
    fixed_now = datetime.datetime(2023, 1, 1, 12, 30, 0)
    mock_dt.now.return_value = fixed_now
    
    fake_metadata_path_str = "/fake/output_base/MetaSaveAsset/metadata/MetaSaveAsset_metadata.json"
    mock_gen_path.return_value = fake_metadata_path_str
    
    initial_meta = {'asset_name': "MetaSaveAsset", 'status': "Pending", 'processing_start_time': "2023-01-01T12:00:00"}
    # Example of a Path object that needs serialization
    proc_details = {'map1': {'temp_processed_file': Path('/fake/temp_engine_dir/map1.png'), 'final_file_path': Path('/fake/output_base/MetaSaveAsset/map1.png')}} 
    merged_details = {'merged_map_A': {'output_path': Path('/fake/output_base/MetaSaveAsset/merged_A.png')}}
    
    context = create_metadata_save_mock_context(
        initial_asset_metadata=initial_meta,
        processed_details=proc_details,
        merged_details=merged_details,
        status_flags={} # No errors, no skip
    )
    
    updated_context = stage.execute(context)
    
    mock_dt.now.assert_called_once()
    mock_gen_path.assert_called_once_with(
        context.asset_rule.output_path_pattern,
        context.asset_rule,
        context.source_rule,
        context.output_base_path,
        context.asset_metadata, # The metadata *before* adding end_time, status etc.
        context.incrementing_value,
        context.sha5_value,
        filename_override=f"{context.asset_rule.name}_metadata.json"
    )
    mock_mkdir.assert_called_once_with(parents=True, exist_ok=True) # Checks parent dir of fake_metadata_path_str
    mock_file_open.assert_called_once_with(Path(fake_metadata_path_str), 'w')
    mock_json_dump.assert_called_once()
    
    # Check what was passed to json.dump
    dumped_data = mock_json_dump.call_args[0][0]
    assert dumped_data['status'] == "Processed"
    assert dumped_data['processing_end_time'] == fixed_now.isoformat()
    assert 'processing_start_time' in dumped_data # Ensure existing fields are preserved

    # Verify processed_map_details and Path serialization
    assert 'processed_map_details' in dumped_data
    assert dumped_data['processed_map_details']['map1']['temp_processed_file'] == '/fake/temp_engine_dir/map1.png'
    assert dumped_data['processed_map_details']['map1']['final_file_path'] == '/fake/output_base/MetaSaveAsset/map1.png'

    # Verify merged_map_details and Path serialization
    assert 'merged_map_details' in dumped_data
    assert dumped_data['merged_map_details']['merged_map_A']['output_path'] == '/fake/output_base/MetaSaveAsset/merged_A.png'
            
    assert updated_context.asset_metadata['metadata_file_path'] == fake_metadata_path_str
    assert updated_context.asset_metadata['status'] == "Processed"
    assert updated_context.status_flags.get('metadata_save_error') is None
@mock.patch('processing.pipeline.stages.metadata_finalization_save.json.dump')
@mock.patch('builtins.open', new_callable=mock.mock_open)
@mock.patch('pathlib.Path.mkdir')
@mock.patch('processing.pipeline.stages.metadata_finalization_save.generate_path_from_pattern')
@mock.patch('datetime.datetime')
def test_processing_failed_due_to_previous_error(
    mock_dt, mock_gen_path, mock_mkdir, mock_file_open, mock_json_dump
):
    """
    Tests that if a previous stage set an error flag, the status is 'Failed'
    and metadata (including any existing details) is saved.
    """
    stage = MetadataFinalizationAndSaveStage()
    
    fixed_now = datetime.datetime(2023, 1, 1, 12, 45, 0)
    mock_dt.now.return_value = fixed_now
    
    fake_metadata_path_str = "/fake/output_base/FailedAsset/metadata/FailedAsset_metadata.json"
    mock_gen_path.return_value = fake_metadata_path_str
    
    initial_meta = {'asset_name': "FailedAsset", 'status': "Processing"}
    # Simulate some details might exist even if a later stage failed
    proc_details = {'map1_partial': {'temp_processed_file': Path('/fake/temp_engine_dir/map1_partial.png')}}
    
    context = create_metadata_save_mock_context(
        asset_name="FailedAsset",
        initial_asset_metadata=initial_meta,
        processed_details=proc_details,
        merged_details={}, # No merged details if processing failed before that
        status_flags={'file_processing_error': True, 'error_message': "Something went wrong"}
    )
    
    updated_context = stage.execute(context)
    
    mock_dt.now.assert_called_once()
    mock_gen_path.assert_called_once() # Path generation should still occur
    mock_mkdir.assert_called_once_with(parents=True, exist_ok=True)
    mock_file_open.assert_called_once_with(Path(fake_metadata_path_str), 'w')
    mock_json_dump.assert_called_once()
    
    dumped_data = mock_json_dump.call_args[0][0]
    assert dumped_data['status'] == "Failed"
    assert dumped_data['processing_end_time'] == fixed_now.isoformat()
    assert 'error_message' in dumped_data # Assuming error messages from status_flags are copied
    assert dumped_data['error_message'] == "Something went wrong"

    # Check that existing details are included
    assert 'processed_map_details' in dumped_data
    assert dumped_data['processed_map_details']['map1_partial']['temp_processed_file'] == '/fake/temp_engine_dir/map1_partial.png'
    assert 'merged_map_details' in dumped_data # Should be present, even if empty
    assert dumped_data['merged_map_details'] == {}
            
    assert updated_context.asset_metadata['status'] == "Failed"
    assert updated_context.asset_metadata['metadata_file_path'] == fake_metadata_path_str
    assert updated_context.status_flags.get('metadata_save_error') is None
    # Ensure the original error flag is preserved
    assert updated_context.status_flags['file_processing_error'] is True
@mock.patch('processing.pipeline.stages.metadata_finalization_save.json.dump')
@mock.patch('builtins.open', new_callable=mock.mock_open)
@mock.patch('pathlib.Path.mkdir')
@mock.patch('processing.pipeline.stages.metadata_finalization_save.generate_path_from_pattern')
@mock.patch('datetime.datetime')
@mock.patch('logging.error') # To check if error is logged
def test_generate_path_fails(
    mock_log_error, mock_dt, mock_gen_path, mock_mkdir, mock_file_open, mock_json_dump
):
    """
    Tests behavior when generate_path_from_pattern raises an exception.
    Ensures status is updated, error flag is set, and no save is attempted.
    """
    stage = MetadataFinalizationAndSaveStage()
    
    fixed_now = datetime.datetime(2023, 1, 1, 12, 50, 0)
    mock_dt.now.return_value = fixed_now
    
    mock_gen_path.side_effect = Exception("Simulated path generation error")
    
    initial_meta = {'asset_name': "PathFailAsset", 'status': "Processing"}
    context = create_metadata_save_mock_context(
        asset_name="PathFailAsset",
        initial_asset_metadata=initial_meta,
        status_flags={} 
    )
    
    updated_context = stage.execute(context)
    
    mock_dt.now.assert_called_once() # Time is set before path generation
    mock_gen_path.assert_called_once() # generate_path_from_pattern is called
    
    # File operations should NOT be called if path generation fails
    mock_mkdir.assert_not_called()
    mock_file_open.assert_not_called()
    mock_json_dump.assert_not_called()
    
    mock_log_error.assert_called_once() # Check that an error was logged
    # Example: check if the log message contains relevant info, if needed
    # assert "Failed to generate metadata path" in mock_log_error.call_args[0][0]

    assert updated_context.asset_metadata['status'] == "Failed" # Or a more specific error status
    assert 'processing_end_time' in updated_context.asset_metadata # End time should still be set
    assert updated_context.asset_metadata['processing_end_time'] == fixed_now.isoformat()
    assert 'metadata_file_path' not in updated_context.asset_metadata # Path should not be set
    
    assert updated_context.status_flags.get('metadata_save_error') is True
    assert 'error_message' in updated_context.asset_metadata # Check if error message is populated
    assert "Simulated path generation error" in updated_context.asset_metadata['error_message']
@mock.patch('processing.pipeline.stages.metadata_finalization_save.json.dump')
@mock.patch('builtins.open', new_callable=mock.mock_open)
@mock.patch('pathlib.Path.mkdir')
@mock.patch('processing.pipeline.stages.metadata_finalization_save.generate_path_from_pattern')
@mock.patch('datetime.datetime')
@mock.patch('logging.error') # To check if error is logged
def test_json_dump_fails(
    mock_log_error, mock_dt, mock_gen_path, mock_mkdir, mock_file_open, mock_json_dump
):
    """
    Tests behavior when json.dump raises an exception during saving.
    Ensures status is updated, error flag is set, and error is logged.
    """
    stage = MetadataFinalizationAndSaveStage()
    
    fixed_now = datetime.datetime(2023, 1, 1, 12, 55, 0)
    mock_dt.now.return_value = fixed_now
    
    fake_metadata_path_str = "/fake/output_base/JsonDumpFailAsset/metadata/JsonDumpFailAsset_metadata.json"
    mock_gen_path.return_value = fake_metadata_path_str
    
    mock_json_dump.side_effect = IOError("Simulated JSON dump error") # Or TypeError for non-serializable
    
    initial_meta = {'asset_name': "JsonDumpFailAsset", 'status': "Processing"}
    context = create_metadata_save_mock_context(
        asset_name="JsonDumpFailAsset",
        initial_asset_metadata=initial_meta,
        status_flags={}
    )
    
    updated_context = stage.execute(context)
    
    mock_dt.now.assert_called_once()
    mock_gen_path.assert_called_once()
    mock_mkdir.assert_called_once_with(parents=True, exist_ok=True)
    mock_file_open.assert_called_once_with(Path(fake_metadata_path_str), 'w')
    mock_json_dump.assert_called_once() # json.dump was attempted
    
    mock_log_error.assert_called_once()
    # assert "Failed to save metadata JSON" in mock_log_error.call_args[0][0]

    assert updated_context.asset_metadata['status'] == "Failed" # Or specific "Metadata Save Failed"
    assert 'processing_end_time' in updated_context.asset_metadata
    assert updated_context.asset_metadata['processing_end_time'] == fixed_now.isoformat()
    # metadata_file_path might be set if path generation succeeded, even if dump failed.
    # Depending on desired behavior, this could be asserted or not.
    # For now, let's assume it's set if path generation was successful.
    assert updated_context.asset_metadata['metadata_file_path'] == fake_metadata_path_str 
                                                                    
    assert updated_context.status_flags.get('metadata_save_error') is True
    assert 'error_message' in updated_context.asset_metadata
    assert "Simulated JSON dump error" in updated_context.asset_metadata['error_message']