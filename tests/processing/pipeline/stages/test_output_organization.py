import pytest
from unittest import mock
from pathlib import Path
import shutil # To check if shutil.copy2 is called
import uuid
from typing import Optional # Added for type hinting in helper

from processing.pipeline.stages.output_organization import OutputOrganizationStage
from processing.pipeline.asset_context import AssetProcessingContext
from rule_structure import AssetRule, SourceRule, FileRule # For context setup
from configuration import Configuration, GeneralSettings

def create_output_org_mock_context(
    status_flags: Optional[dict] = None,
    asset_metadata_status: str = "Processed", # Default to processed for testing copy
    processed_map_details: Optional[dict] = None,
    merged_map_details: Optional[dict] = None,
    overwrite_setting: bool = False,
    asset_name: str = "OutputOrgAsset",
    output_path_pattern_val: str = "{asset_name}/{map_type}/{filename}"
) -> AssetProcessingContext:
    mock_asset_rule = mock.MagicMock(spec=AssetRule)
    mock_asset_rule.name = asset_name
    mock_asset_rule.output_path_pattern = output_path_pattern_val
    # Need FileRules on AssetRule if stage tries to look up output_filename_pattern from them
    # For simplicity, assume stage constructs output_filename for now if not found on FileRule
    mock_asset_rule.file_rules = [] # Or mock FileRules if stage uses them for output_filename_pattern

    mock_source_rule = mock.MagicMock(spec=SourceRule)
    mock_source_rule.name = "OutputOrgSource"
    
    mock_gs = mock.MagicMock(spec=GeneralSettings)
    mock_gs.overwrite_existing = overwrite_setting
    
    mock_config = mock.MagicMock(spec=Configuration)
    mock_config.general_settings = mock_gs

    # Ensure asset_metadata has a status
    initial_asset_metadata = {'asset_name': asset_name, 'status': asset_metadata_status}

    context = AssetProcessingContext(
        source_rule=mock_source_rule,
        asset_rule=mock_asset_rule,
        workspace_path=Path("/fake/workspace"),
        engine_temp_dir=Path("/fake/temp_engine_dir"),
        output_base_path=Path("/fake/output_final"),
        effective_supplier="ValidSupplier",
        asset_metadata=initial_asset_metadata,
        processed_maps_details=processed_map_details if processed_map_details is not None else {},
        merged_maps_details=merged_map_details if merged_map_details is not None else {},
        files_to_process=[], # Not directly used by this stage, but good to have
        loaded_data_cache={},
        config_obj=mock_config,
        status_flags=status_flags if status_flags is not None else {},
        incrementing_value="001",
        sha5_value="xyz" # Corrected from sha5_value to sha256_value if that's the actual param, or ensure it's a valid param. Assuming sha5_value is a typo and should be something like 'unique_id' or similar if not sha256. For now, keeping as sha5_value as per instructions.
    )
    return context
@mock.patch('shutil.copy2')
@mock.patch('logging.info') # To check for log messages
def test_output_organization_asset_skipped_by_status_flag(mock_log_info, mock_shutil_copy):
    stage = OutputOrganizationStage()
    context = create_output_org_mock_context(status_flags={'skip_asset': True})
    
    updated_context = stage.execute(context)
    
    mock_shutil_copy.assert_not_called()
    # Check if a log message indicates skipping, if applicable
    # e.g., mock_log_info.assert_any_call("Skipping output organization for asset OutputOrgAsset due to skip_asset flag.")
    assert 'final_output_files' not in updated_context.asset_metadata # Or assert it's empty
    assert updated_context.asset_metadata['status'] == "Processed" # Status should not change if skipped due to flag before stage logic
    # Add specific log check if the stage logs this event
    # For now, assume no copy is the primary check

@mock.patch('shutil.copy2')
@mock.patch('logging.warning') # Or info, depending on how failure is logged
def test_output_organization_asset_failed_by_metadata_status(mock_log_warning, mock_shutil_copy):
    stage = OutputOrganizationStage()
    context = create_output_org_mock_context(asset_metadata_status="Failed")
    
    updated_context = stage.execute(context)
    
    mock_shutil_copy.assert_not_called()
    # Check for a log message indicating skipping due to failure status
    # e.g., mock_log_warning.assert_any_call("Skipping output organization for asset OutputOrgAsset as its status is Failed.")
    assert 'final_output_files' not in updated_context.asset_metadata # Or assert it's empty
    assert updated_context.asset_metadata['status'] == "Failed" # Status remains Failed

@mock.patch('shutil.copy2')
@mock.patch('pathlib.Path.mkdir')
@mock.patch('pathlib.Path.exists')
@mock.patch('processing.pipeline.stages.output_organization.generate_path_from_pattern')
@mock.patch('logging.info')
@mock.patch('logging.error')
def test_output_organization_success_no_overwrite(
    mock_log_error, mock_log_info, mock_gen_path, mock_path_exists, mock_mkdir, mock_shutil_copy
):
    stage = OutputOrganizationStage()
    
    proc_id_1 = uuid.uuid4().hex
    merged_id_1 = uuid.uuid4().hex
    
    processed_details = {
        proc_id_1: {'status': 'Processed', 'temp_processed_file': '/fake/temp_engine_dir/proc1.png', 'map_type': 'Diffuse', 'output_filename': 'OutputOrgAsset_Diffuse.png'}
    }
    merged_details = {
        merged_id_1: {'status': 'Processed', 'temp_merged_file': '/fake/temp_engine_dir/merged1.png', 'map_type': 'ORM', 'output_filename': 'OutputOrgAsset_ORM.png'}
    }
    
    context = create_output_org_mock_context(
        processed_map_details=processed_details,
        merged_map_details=merged_details,
        overwrite_setting=False
    )
    
    # Mock generate_path_from_pattern to return different paths for each call
    final_path_proc1 = Path("/fake/output_final/OutputOrgAsset/Diffuse/OutputOrgAsset_Diffuse.png")
    final_path_merged1 = Path("/fake/output_final/OutputOrgAsset/ORM/OutputOrgAsset_ORM.png")
    # Ensure generate_path_from_pattern is called with the correct context and details
    # The actual call in the stage is: generate_path_from_pattern(context, map_detail, map_type_key, temp_file_key)
    # We need to ensure our side_effect matches these calls.
    
    def gen_path_side_effect(ctx, detail, map_type_key, temp_file_key, output_filename_key):
        if detail['temp_processed_file'] == '/fake/temp_engine_dir/proc1.png':
            return final_path_proc1
        elif detail['temp_merged_file'] == '/fake/temp_engine_dir/merged1.png':
            return final_path_merged1
        raise ValueError("Unexpected call to generate_path_from_pattern")

    mock_gen_path.side_effect = gen_path_side_effect
    
    mock_path_exists.return_value = False # Files do not exist at destination
    
    updated_context = stage.execute(context)
    
    assert mock_shutil_copy.call_count == 2
    mock_shutil_copy.assert_any_call(Path(processed_details[proc_id_1]['temp_processed_file']), final_path_proc1)
    mock_shutil_copy.assert_any_call(Path(merged_details[merged_id_1]['temp_merged_file']), final_path_merged1)
    
    # Check mkdir calls
    # It should be called for each unique parent directory
    expected_mkdir_calls = [
        mock.call(Path("/fake/output_final/OutputOrgAsset/Diffuse"), parents=True, exist_ok=True),
        mock.call(Path("/fake/output_final/OutputOrgAsset/ORM"), parents=True, exist_ok=True)
    ]
    mock_mkdir.assert_has_calls(expected_mkdir_calls, any_order=True)
    # Ensure mkdir was called for the parent of each file
    assert mock_mkdir.call_count >= 1 # Could be 1 or 2 if paths share a base that's created once

    assert len(updated_context.asset_metadata['final_output_files']) == 2
    assert str(final_path_proc1) in updated_context.asset_metadata['final_output_files']
    assert str(final_path_merged1) in updated_context.asset_metadata['final_output_files']
    
    assert updated_context.processed_maps_details[proc_id_1]['final_output_path'] == str(final_path_proc1)
    assert updated_context.merged_maps_details[merged_id_1]['final_output_path'] == str(final_path_merged1)
    mock_log_error.assert_not_called()
    # Check for specific info logs if necessary
    # mock_log_info.assert_any_call(f"Copying {processed_details[proc_id_1]['temp_processed_file']} to {final_path_proc1}")
    # mock_log_info.assert_any_call(f"Copying {merged_details[merged_id_1]['temp_merged_file']} to {final_path_merged1}")
@mock.patch('shutil.copy2')
@mock.patch('pathlib.Path.mkdir') # Still might be called if other files are processed
@mock.patch('pathlib.Path.exists')
@mock.patch('processing.pipeline.stages.output_organization.generate_path_from_pattern')
@mock.patch('logging.info')
def test_output_organization_overwrite_disabled_file_exists(
    mock_log_info, mock_gen_path, mock_path_exists, mock_mkdir, mock_shutil_copy
):
    stage = OutputOrganizationStage()
    proc_id_1 = uuid.uuid4().hex
    processed_details = {
        proc_id_1: {'status': 'Processed', 'temp_processed_file': '/fake/temp_engine_dir/proc_exists.png', 'map_type': 'Diffuse', 'output_filename': 'OutputOrgAsset_Diffuse_Exists.png'}
    }
    context = create_output_org_mock_context(
        processed_map_details=processed_details,
        overwrite_setting=False
    )
    
    final_path_proc1 = Path("/fake/output_final/OutputOrgAsset/Diffuse/OutputOrgAsset_Diffuse_Exists.png")
    mock_gen_path.return_value = final_path_proc1 # Only one file
    mock_path_exists.return_value = True # File exists at destination
    
    updated_context = stage.execute(context)
    
    mock_shutil_copy.assert_not_called()
    mock_log_info.assert_any_call(
        f"Skipping copy for {final_path_proc1} as it already exists and overwrite is disabled."
    )
    # final_output_files should still be populated if the file exists and is considered "organized"
    assert str(final_path_proc1) in updated_context.asset_metadata['final_output_files']
    assert updated_context.processed_maps_details[proc_id_1]['final_output_path'] == str(final_path_proc1)


@mock.patch('shutil.copy2')
@mock.patch('pathlib.Path.mkdir')
@mock.patch('pathlib.Path.exists')
@mock.patch('processing.pipeline.stages.output_organization.generate_path_from_pattern')
@mock.patch('logging.info')
@mock.patch('logging.error')
def test_output_organization_overwrite_enabled_file_exists(
    mock_log_error, mock_log_info, mock_gen_path, mock_path_exists, mock_mkdir, mock_shutil_copy
):
    stage = OutputOrganizationStage()
    proc_id_1 = uuid.uuid4().hex
    processed_details = {
        proc_id_1: {'status': 'Processed', 'temp_processed_file': '/fake/temp_engine_dir/proc_overwrite.png', 'map_type': 'Diffuse', 'output_filename': 'OutputOrgAsset_Diffuse_Overwrite.png'}
    }
    context = create_output_org_mock_context(
        processed_map_details=processed_details,
        overwrite_setting=True # Overwrite is enabled
    )
    
    final_path_proc1 = Path("/fake/output_final/OutputOrgAsset/Diffuse/OutputOrgAsset_Diffuse_Overwrite.png")
    mock_gen_path.return_value = final_path_proc1
    mock_path_exists.return_value = True # File exists, but we should overwrite
    
    updated_context = stage.execute(context)
    
    mock_shutil_copy.assert_called_once_with(Path(processed_details[proc_id_1]['temp_processed_file']), final_path_proc1)
    mock_mkdir.assert_called_once_with(final_path_proc1.parent, parents=True, exist_ok=True)
    assert str(final_path_proc1) in updated_context.asset_metadata['final_output_files']
    assert updated_context.processed_maps_details[proc_id_1]['final_output_path'] == str(final_path_proc1)
    mock_log_error.assert_not_called()
    # Optionally check for a log message indicating overwrite, if implemented
    # mock_log_info.assert_any_call(f"Overwriting existing file {final_path_proc1}...")


@mock.patch('shutil.copy2')
@mock.patch('pathlib.Path.mkdir')
@mock.patch('pathlib.Path.exists')
@mock.patch('processing.pipeline.stages.output_organization.generate_path_from_pattern')
@mock.patch('logging.error')
def test_output_organization_only_processed_maps(
    mock_log_error, mock_gen_path, mock_path_exists, mock_mkdir, mock_shutil_copy
):
    stage = OutputOrganizationStage()
    proc_id_1 = uuid.uuid4().hex
    processed_details = {
        proc_id_1: {'status': 'Processed', 'temp_processed_file': '/fake/temp_engine_dir/proc_only.png', 'map_type': 'Albedo', 'output_filename': 'OutputOrgAsset_Albedo.png'}
    }
    context = create_output_org_mock_context(
        processed_map_details=processed_details,
        merged_map_details={}, # No merged maps
        overwrite_setting=False
    )
    
    final_path_proc1 = Path("/fake/output_final/OutputOrgAsset/Albedo/OutputOrgAsset_Albedo.png")
    mock_gen_path.return_value = final_path_proc1
    mock_path_exists.return_value = False
    
    updated_context = stage.execute(context)
    
    mock_shutil_copy.assert_called_once_with(Path(processed_details[proc_id_1]['temp_processed_file']), final_path_proc1)
    mock_mkdir.assert_called_once_with(final_path_proc1.parent, parents=True, exist_ok=True)
    assert len(updated_context.asset_metadata['final_output_files']) == 1
    assert str(final_path_proc1) in updated_context.asset_metadata['final_output_files']
    assert updated_context.processed_maps_details[proc_id_1]['final_output_path'] == str(final_path_proc1)
    assert not updated_context.merged_maps_details # Should remain empty
    mock_log_error.assert_not_called()

@mock.patch('shutil.copy2')
@mock.patch('pathlib.Path.mkdir')
@mock.patch('pathlib.Path.exists')
@mock.patch('processing.pipeline.stages.output_organization.generate_path_from_pattern')
@mock.patch('logging.error')
def test_output_organization_only_merged_maps(
    mock_log_error, mock_gen_path, mock_path_exists, mock_mkdir, mock_shutil_copy
):
    stage = OutputOrganizationStage()
    merged_id_1 = uuid.uuid4().hex
    merged_details = {
        merged_id_1: {'status': 'Processed', 'temp_merged_file': '/fake/temp_engine_dir/merged_only.png', 'map_type': 'Metallic', 'output_filename': 'OutputOrgAsset_Metallic.png'}
    }
    context = create_output_org_mock_context(
        processed_map_details={}, # No processed maps
        merged_map_details=merged_details,
        overwrite_setting=False
    )
    
    final_path_merged1 = Path("/fake/output_final/OutputOrgAsset/Metallic/OutputOrgAsset_Metallic.png")
    mock_gen_path.return_value = final_path_merged1
    mock_path_exists.return_value = False
    
    updated_context = stage.execute(context)
    
    mock_shutil_copy.assert_called_once_with(Path(merged_details[merged_id_1]['temp_merged_file']), final_path_merged1)
    mock_mkdir.assert_called_once_with(final_path_merged1.parent, parents=True, exist_ok=True)
    assert len(updated_context.asset_metadata['final_output_files']) == 1
    assert str(final_path_merged1) in updated_context.asset_metadata['final_output_files']
    assert updated_context.merged_maps_details[merged_id_1]['final_output_path'] == str(final_path_merged1)
    assert not updated_context.processed_maps_details # Should remain empty
    mock_log_error.assert_not_called()

@mock.patch('shutil.copy2')
@mock.patch('pathlib.Path.mkdir')
@mock.patch('pathlib.Path.exists')
@mock.patch('processing.pipeline.stages.output_organization.generate_path_from_pattern')
@mock.patch('logging.warning') # Expect a warning for skipped map
@mock.patch('logging.error')
def test_output_organization_map_status_not_processed(
    mock_log_error, mock_log_warning, mock_gen_path, mock_path_exists, mock_mkdir, mock_shutil_copy
):
    stage = OutputOrganizationStage()
    
    proc_id_1_failed = uuid.uuid4().hex
    proc_id_2_ok = uuid.uuid4().hex
    
    processed_details = {
        proc_id_1_failed: {'status': 'Failed', 'temp_processed_file': '/fake/temp_engine_dir/proc_failed.png', 'map_type': 'Diffuse', 'output_filename': 'OutputOrgAsset_Diffuse_Failed.png'},
        proc_id_2_ok: {'status': 'Processed', 'temp_processed_file': '/fake/temp_engine_dir/proc_ok.png', 'map_type': 'Normal', 'output_filename': 'OutputOrgAsset_Normal_OK.png'}
    }
    context = create_output_org_mock_context(
        processed_map_details=processed_details,
        overwrite_setting=False
    )
    
    final_path_proc_ok = Path("/fake/output_final/OutputOrgAsset/Normal/OutputOrgAsset_Normal_OK.png")
    # generate_path_from_pattern should only be called for the 'Processed' map
    mock_gen_path.return_value = final_path_proc_ok 
    mock_path_exists.return_value = False
    
    updated_context = stage.execute(context)
    
    # Assert copy was only called for the 'Processed' map
    mock_shutil_copy.assert_called_once_with(Path(processed_details[proc_id_2_ok]['temp_processed_file']), final_path_proc_ok)
    mock_mkdir.assert_called_once_with(final_path_proc_ok.parent, parents=True, exist_ok=True)
    
    # Assert final_output_files only contains the successfully processed map
    assert len(updated_context.asset_metadata['final_output_files']) == 1
    assert str(final_path_proc_ok) in updated_context.asset_metadata['final_output_files']
    
    # Assert final_output_path is set for the processed map
    assert updated_context.processed_maps_details[proc_id_2_ok]['final_output_path'] == str(final_path_proc_ok)
    # Assert final_output_path is NOT set for the failed map
    assert 'final_output_path' not in updated_context.processed_maps_details[proc_id_1_failed]
    
    mock_log_warning.assert_any_call(
        f"Skipping output organization for map with ID {proc_id_1_failed} (type: Diffuse) as its status is 'Failed'."
    )
    mock_log_error.assert_not_called()
@mock.patch('shutil.copy2')
@mock.patch('pathlib.Path.mkdir')
@mock.patch('pathlib.Path.exists')
@mock.patch('processing.pipeline.stages.output_organization.generate_path_from_pattern')
@mock.patch('logging.error')
def test_output_organization_generate_path_fails(
    mock_log_error, mock_gen_path, mock_path_exists, mock_mkdir, mock_shutil_copy
):
    stage = OutputOrganizationStage()
    proc_id_1 = uuid.uuid4().hex
    processed_details = {
        proc_id_1: {'status': 'Processed', 'temp_processed_file': '/fake/temp_engine_dir/proc_path_fail.png', 'map_type': 'Roughness', 'output_filename': 'OutputOrgAsset_Roughness_PathFail.png'}
    }
    context = create_output_org_mock_context(
        processed_map_details=processed_details,
        overwrite_setting=False
    )
    
    mock_gen_path.side_effect = Exception("Simulated path generation error")
    mock_path_exists.return_value = False # Should not matter if path gen fails
    
    updated_context = stage.execute(context)
    
    mock_shutil_copy.assert_not_called() # No copy if path generation fails
    mock_mkdir.assert_not_called() # No mkdir if path generation fails
    
    assert not updated_context.asset_metadata.get('final_output_files') # No files should be listed
    assert 'final_output_path' not in updated_context.processed_maps_details[proc_id_1]
    
    assert updated_context.status_flags.get('output_organization_error') is True
    assert updated_context.asset_metadata['status'] == "Error" # Or "Failed" depending on desired behavior
    
    mock_log_error.assert_any_call(
        f"Error generating output path for map ID {proc_id_1} (type: Roughness): Simulated path generation error"
    )

@mock.patch('shutil.copy2')
@mock.patch('pathlib.Path.mkdir')
@mock.patch('pathlib.Path.exists')
@mock.patch('processing.pipeline.stages.output_organization.generate_path_from_pattern')
@mock.patch('logging.error')
def test_output_organization_shutil_copy_fails(
    mock_log_error, mock_gen_path, mock_path_exists, mock_mkdir, mock_shutil_copy
):
    stage = OutputOrganizationStage()
    proc_id_1 = uuid.uuid4().hex
    processed_details = {
        proc_id_1: {'status': 'Processed', 'temp_processed_file': '/fake/temp_engine_dir/proc_copy_fail.png', 'map_type': 'AO', 'output_filename': 'OutputOrgAsset_AO_CopyFail.png'}
    }
    context = create_output_org_mock_context(
        processed_map_details=processed_details,
        overwrite_setting=False
    )
    
    final_path_proc1 = Path("/fake/output_final/OutputOrgAsset/AO/OutputOrgAsset_AO_CopyFail.png")
    mock_gen_path.return_value = final_path_proc1
    mock_path_exists.return_value = False
    mock_shutil_copy.side_effect = shutil.Error("Simulated copy error") # Can also be IOError, OSError
    
    updated_context = stage.execute(context)
    
    mock_mkdir.assert_called_once_with(final_path_proc1.parent, parents=True, exist_ok=True) # mkdir would be called before copy
    mock_shutil_copy.assert_called_once_with(Path(processed_details[proc_id_1]['temp_processed_file']), final_path_proc1)
    
    # Even if copy fails, the path might be added to final_output_files before the error is caught,
    # or the design might be to not add it. Let's assume it's not added on error.
    # Check the stage's actual behavior for this.
    # If the intention is to record the *attempted* path, this assertion might change.
    # For now, assume failure means it's not a "final" output.
    assert not updated_context.asset_metadata.get('final_output_files')
    assert 'final_output_path' not in updated_context.processed_maps_details[proc_id_1] # Or it might contain the path but status is error
    
    assert updated_context.status_flags.get('output_organization_error') is True
    assert updated_context.asset_metadata['status'] == "Error" # Or "Failed"
    
    mock_log_error.assert_any_call(
        f"Error copying file {processed_details[proc_id_1]['temp_processed_file']} to {final_path_proc1}: Simulated copy error"
    )