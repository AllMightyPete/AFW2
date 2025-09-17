import pytest
from unittest import mock
from pathlib import Path
import uuid
import shutil # For checking rmtree
import tempfile # For mocking mkdtemp

from processing.pipeline.orchestrator import PipelineOrchestrator
from processing.pipeline.asset_context import AssetProcessingContext
from processing.pipeline.stages.base_stage import ProcessingStage # For mocking stages
from rule_structure import SourceRule, AssetRule, FileRule
from configuration import Configuration, GeneralSettings

# Mock Stage that modifies context
class MockPassThroughStage(ProcessingStage):
    def __init__(self, stage_name="mock_stage"):
        self.stage_name = stage_name
        self.execute_call_count = 0
        self.contexts_called_with = [] # To store contexts for verification

    def execute(self, context: AssetProcessingContext) -> AssetProcessingContext:
        self.execute_call_count += 1
        self.contexts_called_with.append(context)
        # Optionally, modify context for testing
        context.asset_metadata[f'{self.stage_name}_executed'] = True
        if self.stage_name == "skipper_stage": # Example conditional logic
            context.status_flags['skip_asset'] = True
            context.status_flags['skip_reason'] = "Skipped by skipper_stage"
        elif self.stage_name == "error_stage": # Example error-raising stage
            raise ValueError("Simulated error in error_stage")
        
        # Simulate status update based on stage execution
        if not context.status_flags.get('skip_asset') and not context.status_flags.get('asset_failed'):
             context.asset_metadata['status'] = "Processed" # Default to processed if not skipped/failed
        return context

def create_orchestrator_test_config() -> mock.MagicMock:
    mock_config = mock.MagicMock(spec=Configuration)
    mock_config.general_settings = mock.MagicMock(spec=GeneralSettings)
    mock_config.general_settings.temp_dir_override = None # Default, can be overridden in tests
    # Add other config details if orchestrator or stages depend on them directly
    return mock_config

def create_orchestrator_test_asset_rule(name: str, num_file_rules: int = 1) -> mock.MagicMock:
    asset_rule = mock.MagicMock(spec=AssetRule)
    asset_rule.name = name
    asset_rule.id = uuid.uuid4()
    asset_rule.source_path = Path(f"/fake/source/{name}") # Using Path object
    asset_rule.file_rules = [mock.MagicMock(spec=FileRule) for _ in range(num_file_rules)]
    asset_rule.enabled = True
    asset_rule.map_types = {} # Initialize as dict
    asset_rule.material_name_scheme = "{asset_name}"
    asset_rule.texture_name_scheme = "{asset_name}_{map_type}"
    asset_rule.output_path_scheme = "{source_name}/{asset_name}"
    # ... other necessary AssetRule fields ...
    return asset_rule

def create_orchestrator_test_source_rule(name: str, num_assets: int = 1, asset_names: list = None) -> mock.MagicMock:
    source_rule = mock.MagicMock(spec=SourceRule)
    source_rule.name = name
    source_rule.id = uuid.uuid4()
    if asset_names:
        source_rule.assets = [create_orchestrator_test_asset_rule(an) for an in asset_names]
    else:
        source_rule.assets = [create_orchestrator_test_asset_rule(f"Asset_{i+1}_in_{name}") for i in range(num_assets)]
    source_rule.enabled = True
    source_rule.source_path = Path(f"/fake/source_root/{name}") # Using Path object
    # ... other necessary SourceRule fields ...
    return source_rule

# --- Test Cases for PipelineOrchestrator.process_source_rule() ---

@mock.patch('shutil.rmtree')
@mock.patch('tempfile.mkdtemp')
def test_orchestrator_basic_flow_mock_stages(mock_mkdtemp, mock_rmtree):
    mock_mkdtemp.return_value = "/fake/engine_temp_dir_path" # Path for mkdtemp
    
    config = create_orchestrator_test_config()
    stage1 = MockPassThroughStage("stage1")
    stage2 = MockPassThroughStage("stage2")
    orchestrator = PipelineOrchestrator(config_obj=config, stages=[stage1, stage2])
    
    source_rule = create_orchestrator_test_source_rule("MySourceRule", num_assets=2)
    asset1_name = source_rule.assets[0].name
    asset2_name = source_rule.assets[1].name

    # Mock asset_metadata to be updated by stages for status check
    # The MockPassThroughStage already sets a 'status' = "Processed" if not skipped/failed
    # and adds '{stage_name}_executed' = True to asset_metadata.

    results = orchestrator.process_source_rule(
        source_rule, Path("/ws"), Path("/out"), False, "inc_val_123", "sha_val_abc"
    )
    
    assert stage1.execute_call_count == 2 # Called for each asset
    assert stage2.execute_call_count == 2 # Called for each asset
    
    assert asset1_name in results['processed']
    assert asset2_name in results['processed']
    assert not results['skipped']
    assert not results['failed']
    
    # Verify context modifications by stages
    for i in range(2): # For each asset
        # Stage 1 context checks
        s1_context_asset = stage1.contexts_called_with[i]
        assert s1_context_asset.asset_metadata.get('stage1_executed') is True
        assert s1_context_asset.asset_metadata.get('stage2_executed') is None # Stage 2 not yet run for this asset

        # Stage 2 context checks
        s2_context_asset = stage2.contexts_called_with[i]
        assert s2_context_asset.asset_metadata.get('stage1_executed') is True # From stage 1
        assert s2_context_asset.asset_metadata.get('stage2_executed') is True
        assert s2_context_asset.asset_metadata.get('status') == "Processed"

    mock_mkdtemp.assert_called_once()
    # The orchestrator creates a subdirectory within the mkdtemp path
    expected_temp_path = Path(mock_mkdtemp.return_value) / source_rule.id.hex
    mock_rmtree.assert_called_once_with(expected_temp_path, ignore_errors=True)

@mock.patch('shutil.rmtree')
@mock.patch('tempfile.mkdtemp')
def test_orchestrator_asset_skipping_by_stage(mock_mkdtemp, mock_rmtree):
    mock_mkdtemp.return_value = "/fake/engine_temp_dir_path_skip"
    
    config = create_orchestrator_test_config()
    skipper_stage = MockPassThroughStage("skipper_stage") # This stage will set skip_asset = True
    stage_after_skip = MockPassThroughStage("stage_after_skip")
    
    orchestrator = PipelineOrchestrator(config_obj=config, stages=[skipper_stage, stage_after_skip])
    
    source_rule = create_orchestrator_test_source_rule("SkipSourceRule", num_assets=1)
    asset_to_skip_name = source_rule.assets[0].name
    
    results = orchestrator.process_source_rule(
        source_rule, Path("/ws_skip"), Path("/out_skip"), False, "inc_skip", "sha_skip"
    )
    
    assert skipper_stage.execute_call_count == 1 # Called for the asset
    assert stage_after_skip.execute_call_count == 0 # Not called because asset was skipped
    
    assert asset_to_skip_name in results['skipped']
    assert not results['processed']
    assert not results['failed']
    
    # Verify skip reason in context if needed (MockPassThroughStage stores contexts)
    skipped_context = skipper_stage.contexts_called_with[0]
    assert skipped_context.status_flags['skip_asset'] is True
    assert skipped_context.status_flags['skip_reason'] == "Skipped by skipper_stage"
    
    mock_mkdtemp.assert_called_once()
    expected_temp_path = Path(mock_mkdtemp.return_value) / source_rule.id.hex
    mock_rmtree.assert_called_once_with(expected_temp_path, ignore_errors=True)

@mock.patch('shutil.rmtree')
@mock.patch('tempfile.mkdtemp')
def test_orchestrator_no_assets_in_source_rule(mock_mkdtemp, mock_rmtree):
    mock_mkdtemp.return_value = "/fake/engine_temp_dir_no_assets"
    
    config = create_orchestrator_test_config()
    stage1 = MockPassThroughStage("stage1_no_assets")
    orchestrator = PipelineOrchestrator(config_obj=config, stages=[stage1])
    
    source_rule = create_orchestrator_test_source_rule("NoAssetSourceRule", num_assets=0)
    
    results = orchestrator.process_source_rule(
        source_rule, Path("/ws_no_assets"), Path("/out_no_assets"), False, "inc_no", "sha_no"
    )
    
    assert stage1.execute_call_count == 0
    assert not results['processed']
    assert not results['skipped']
    assert not results['failed']
    
    # mkdtemp should still be called for the source rule processing, even if no assets
    mock_mkdtemp.assert_called_once()
    expected_temp_path = Path(mock_mkdtemp.return_value) / source_rule.id.hex
    mock_rmtree.assert_called_once_with(expected_temp_path, ignore_errors=True)


@mock.patch('shutil.rmtree')
@mock.patch('tempfile.mkdtemp')
def test_orchestrator_error_during_stage_execution(mock_mkdtemp, mock_rmtree):
    mock_mkdtemp.return_value = "/fake/engine_temp_dir_error"
    
    config = create_orchestrator_test_config()
    error_stage = MockPassThroughStage("error_stage") # This stage will raise an error
    stage_after_error = MockPassThroughStage("stage_after_error")
    
    orchestrator = PipelineOrchestrator(config_obj=config, stages=[error_stage, stage_after_error])
    
    # Test with two assets, one fails, one processes (if orchestrator continues)
    # The current orchestrator's process_asset is per asset, so an error in one
    # should not stop processing of other assets in the same source_rule.
    source_rule = create_orchestrator_test_source_rule("ErrorSourceRule", asset_names=["AssetFails", "AssetSucceeds"])
    asset_fails_name = source_rule.assets[0].name
    asset_succeeds_name = source_rule.assets[1].name

    # Make only the first asset's processing trigger the error
    original_execute = error_stage.execute
    def error_execute_side_effect(context: AssetProcessingContext):
        if context.asset_rule.name == asset_fails_name:
            # The MockPassThroughStage is already configured to raise ValueError for "error_stage"
            # but we need to ensure it's only for the first asset.
            # We can achieve this by modifying the stage_name temporarily or by checking asset_rule.name
            # For simplicity, let's assume the mock stage's error logic is fine,
            # and we just need to check the outcome.
            # The error_stage will raise ValueError("Simulated error in error_stage")
            # The orchestrator's _process_single_asset catches generic Exception.
            return original_execute(context) # This will call the erroring logic
        else:
            # For the second asset, make it pass through without error
            context.asset_metadata[f'{error_stage.stage_name}_executed'] = True
            context.asset_metadata['status'] = "Processed"
            return context
    
    error_stage.execute = mock.MagicMock(side_effect=error_execute_side_effect)
    # stage_after_error should still be called for the successful asset
    
    results = orchestrator.process_source_rule(
        source_rule, Path("/ws_error"), Path("/out_error"), False, "inc_err", "sha_err"
    )
    
    assert error_stage.execute.call_count == 2 # Called for both assets
    # stage_after_error is only called for the asset that didn't fail in error_stage
    assert stage_after_error.execute_call_count == 1 
    
    assert asset_fails_name in results['failed']
    assert asset_succeeds_name in results['processed']
    assert not results['skipped']
    
    # Verify the context of the failed asset
    failed_context = None
    for ctx in error_stage.contexts_called_with:
        if ctx.asset_rule.name == asset_fails_name:
            failed_context = ctx
            break
    assert failed_context is not None
    assert failed_context.status_flags['asset_failed'] is True
    assert "Simulated error in error_stage" in failed_context.status_flags['failure_reason']

    # Verify the context of the successful asset after stage_after_error
    successful_context_after_s2 = None
    for ctx in stage_after_error.contexts_called_with:
        if ctx.asset_rule.name == asset_succeeds_name:
            successful_context_after_s2 = ctx
            break
    assert successful_context_after_s2 is not None
    assert successful_context_after_s2.asset_metadata.get('error_stage_executed') is True # from the non-erroring path
    assert successful_context_after_s2.asset_metadata.get('stage_after_error_executed') is True
    assert successful_context_after_s2.asset_metadata.get('status') == "Processed"


    mock_mkdtemp.assert_called_once()
    expected_temp_path = Path(mock_mkdtemp.return_value) / source_rule.id.hex
    mock_rmtree.assert_called_once_with(expected_temp_path, ignore_errors=True)


@mock.patch('shutil.rmtree')
@mock.patch('tempfile.mkdtemp')
def test_orchestrator_asset_processing_context_initialization(mock_mkdtemp, mock_rmtree):
    mock_engine_temp_dir = "/fake/engine_temp_dir_context_init"
    mock_mkdtemp.return_value = mock_engine_temp_dir
    
    config = create_orchestrator_test_config()
    mock_stage = MockPassThroughStage("context_check_stage")
    orchestrator = PipelineOrchestrator(config_obj=config, stages=[mock_stage])
    
    source_rule = create_orchestrator_test_source_rule("ContextSourceRule", num_assets=1)
    asset_rule = source_rule.assets[0]
    
    workspace_path = Path("/ws_context")
    output_base_path = Path("/out_context")
    incrementing_value = "inc_context_123"
    sha5_value = "sha_context_abc"
    
    orchestrator.process_source_rule(
        source_rule, workspace_path, output_base_path, False, incrementing_value, sha5_value
    )
    
    assert mock_stage.execute_call_count == 1
    
    # Retrieve the context passed to the mock stage
    captured_context = mock_stage.contexts_called_with[0]
    
    assert captured_context.source_rule == source_rule
    assert captured_context.asset_rule == asset_rule
    assert captured_context.workspace_path == workspace_path
    
    # engine_temp_dir for the asset is a sub-directory of the source_rule's temp dir
    # which itself is a sub-directory of the main engine_temp_dir from mkdtemp
    expected_source_rule_temp_dir = Path(mock_engine_temp_dir) / source_rule.id.hex
    expected_asset_temp_dir = expected_source_rule_temp_dir / asset_rule.id.hex
    assert captured_context.engine_temp_dir == expected_asset_temp_dir
    
    assert captured_context.output_base_path == output_base_path
    assert captured_context.config_obj == config
    assert captured_context.incrementing_value == incrementing_value
    assert captured_context.sha5_value == sha5_value
    
    # Check initial state of other context fields
    assert captured_context.asset_metadata == {} # Should be empty initially for an asset
    assert captured_context.status_flags == {}   # Should be empty initially
    assert captured_context.shared_data == {}    # Should be empty initially
    assert captured_context.current_files == []  # Should be empty initially

    mock_mkdtemp.assert_called_once()
    mock_rmtree.assert_called_once_with(expected_source_rule_temp_dir, ignore_errors=True)

@mock.patch('shutil.rmtree')
@mock.patch('tempfile.mkdtemp')
def test_orchestrator_temp_dir_override_from_config(mock_mkdtemp, mock_rmtree):
    # This test verifies that if config.general_settings.temp_dir_override is set,
    # mkdtemp is NOT called, and the override path is used and cleaned up.
    
    config = create_orchestrator_test_config()
    override_temp_path_str = "/override/temp/path"
    config.general_settings.temp_dir_override = override_temp_path_str
    
    stage1 = MockPassThroughStage("stage_temp_override")
    orchestrator = PipelineOrchestrator(config_obj=config, stages=[stage1])
    
    source_rule = create_orchestrator_test_source_rule("TempOverrideRule", num_assets=1)
    asset_rule = source_rule.assets[0]

    results = orchestrator.process_source_rule(
        source_rule, Path("/ws_override"), Path("/out_override"), False, "inc_override", "sha_override"
    )
    
    assert stage1.execute_call_count == 1
    assert asset_rule.name in results['processed']
    
    mock_mkdtemp.assert_not_called() # mkdtemp should not be called due to override

    # The orchestrator should create its source-rule specific subdir within the override
    expected_source_rule_temp_dir_in_override = Path(override_temp_path_str) / source_rule.id.hex
    
    # Verify the context passed to the stage uses the overridden path structure
    captured_context = stage1.contexts_called_with[0]
    expected_asset_temp_dir_in_override = expected_source_rule_temp_dir_in_override / asset_rule.id.hex
    assert captured_context.engine_temp_dir == expected_asset_temp_dir_in_override
    
    # rmtree should be called on the source_rule's directory within the override path
    mock_rmtree.assert_called_once_with(expected_source_rule_temp_dir_in_override, ignore_errors=True)

@mock.patch('shutil.rmtree')
@mock.patch('tempfile.mkdtemp')
def test_orchestrator_disabled_asset_rule_is_skipped(mock_mkdtemp, mock_rmtree):
    mock_mkdtemp.return_value = "/fake/engine_temp_dir_disabled_asset"
    
    config = create_orchestrator_test_config()
    stage1 = MockPassThroughStage("stage_disabled_check")
    orchestrator = PipelineOrchestrator(config_obj=config, stages=[stage1])
    
    source_rule = create_orchestrator_test_source_rule("DisabledAssetSourceRule", asset_names=["EnabledAsset", "DisabledAsset"])
    enabled_asset = source_rule.assets[0]
    disabled_asset = source_rule.assets[1]
    disabled_asset.enabled = False # Disable this asset rule
    
    results = orchestrator.process_source_rule(
        source_rule, Path("/ws_disabled"), Path("/out_disabled"), False, "inc_dis", "sha_dis"
    )
    
    assert stage1.execute_call_count == 1 # Only called for the enabled asset
    
    assert enabled_asset.name in results['processed']
    assert disabled_asset.name in results['skipped']
    assert not results['failed']
    
    # Verify context for the processed asset
    assert stage1.contexts_called_with[0].asset_rule.name == enabled_asset.name

    # Verify skip reason for the disabled asset (this is set by the orchestrator itself)
    # The orchestrator's _process_single_asset checks asset_rule.enabled
    # We need to inspect the results dictionary for the skip reason if it's stored there,
    # or infer it. The current structure of `results` doesn't store detailed skip reasons directly,
    # but the test ensures it's in the 'skipped' list.
    # For a more detailed check, one might need to adjust how results are reported or mock deeper.
    # For now, confirming it's in 'skipped' and stage1 wasn't called for it is sufficient.

    mock_mkdtemp.assert_called_once()
    expected_temp_path = Path(mock_mkdtemp.return_value) / source_rule.id.hex
    mock_rmtree.assert_called_once_with(expected_temp_path, ignore_errors=True)