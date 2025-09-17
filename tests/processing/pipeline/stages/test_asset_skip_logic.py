import pytest
from unittest import mock
from pathlib import Path
from typing import Dict, Optional, Any

from processing.pipeline.stages.asset_skip_logic import AssetSkipLogicStage
from processing.pipeline.asset_context import AssetProcessingContext
from rule_structure import AssetRule, SourceRule
from configuration import Configuration, GeneralSettings

# Helper function to create a mock AssetProcessingContext
def create_skip_logic_mock_context(
    effective_supplier: Optional[str] = "ValidSupplier",
    asset_process_status: str = "PENDING",
    overwrite_existing: bool = False,
    asset_name: str = "TestAssetSkip"
) -> AssetProcessingContext:
    mock_asset_rule = mock.MagicMock(spec=AssetRule)
    mock_asset_rule.name = asset_name
    mock_asset_rule.process_status = asset_process_status
    mock_asset_rule.source_path = "fake/source" # Added for completeness
    mock_asset_rule.output_path = "fake/output" # Added for completeness
    mock_asset_rule.maps = [] # Added for completeness
    mock_asset_rule.metadata = {} # Added for completeness
    mock_asset_rule.material_name = None # Added for completeness
    mock_asset_rule.notes = None # Added for completeness
    mock_asset_rule.tags = [] # Added for completeness
    mock_asset_rule.enabled = True # Added for completeness


    mock_source_rule = mock.MagicMock(spec=SourceRule)
    mock_source_rule.name = "TestSourceRule" # Added for completeness
    mock_source_rule.path = "fake/source_rule_path" # Added for completeness
    mock_source_rule.default_supplier = None # Added for completeness
    mock_source_rule.assets = [mock_asset_rule] # Added for completeness
    mock_source_rule.enabled = True # Added for completeness

    mock_general_settings = mock.MagicMock(spec=GeneralSettings)
    mock_general_settings.overwrite_existing = overwrite_existing
    
    mock_config = mock.MagicMock(spec=Configuration)
    mock_config.general_settings = mock_general_settings
    mock_config.suppliers = {"ValidSupplier": mock.MagicMock()} 

    context = AssetProcessingContext(
        source_rule=mock_source_rule,
        asset_rule=mock_asset_rule,
        workspace_path=Path("/fake/workspace"),
        engine_temp_dir=Path("/fake/temp"),
        output_base_path=Path("/fake/output"),
        effective_supplier=effective_supplier,
        asset_metadata={},
        processed_maps_details={},
        merged_maps_details={},
        files_to_process=[],
        loaded_data_cache={},
        config_obj=mock_config,
        status_flags={},
        incrementing_value=None,
        sha5_value=None # Corrected from sha5_value to sha256_value if that's the actual field
    )
    # Ensure status_flags is initialized if AssetSkipLogicStage expects it
    # context.status_flags = {} # Already done in constructor
    return context
@mock.patch('logging.info')
def test_skip_due_to_missing_supplier(mock_log_info):
    """
    Test that the asset is skipped if effective_supplier is None.
    """
    stage = AssetSkipLogicStage()
    context = create_skip_logic_mock_context(effective_supplier=None, asset_name="MissingSupplierAsset")
    
    updated_context = stage.execute(context)
    
    assert updated_context.status_flags.get('skip_asset') is True
    assert updated_context.status_flags.get('skip_reason') == "Invalid or missing supplier"
    mock_log_info.assert_any_call(f"Asset 'MissingSupplierAsset': Skipping due to missing or invalid supplier.")

@mock.patch('logging.info')
def test_skip_due_to_process_status_skip(mock_log_info):
    """
    Test that the asset is skipped if asset_rule.process_status is "SKIP".
    """
    stage = AssetSkipLogicStage()
    context = create_skip_logic_mock_context(asset_process_status="SKIP", asset_name="SkipStatusAsset")
    
    updated_context = stage.execute(context)
    
    assert updated_context.status_flags.get('skip_asset') is True
    assert updated_context.status_flags.get('skip_reason') == "Process status set to SKIP"
    mock_log_info.assert_any_call(f"Asset 'SkipStatusAsset': Skipping because process_status is 'SKIP'.")

@mock.patch('logging.info')
def test_skip_due_to_processed_and_overwrite_disabled(mock_log_info):
    """
    Test that the asset is skipped if asset_rule.process_status is "PROCESSED"
    and overwrite_existing is False.
    """
    stage = AssetSkipLogicStage()
    context = create_skip_logic_mock_context(
        asset_process_status="PROCESSED", 
        overwrite_existing=False,
        asset_name="ProcessedNoOverwriteAsset"
    )
    
    updated_context = stage.execute(context)
    
    assert updated_context.status_flags.get('skip_asset') is True
    assert updated_context.status_flags.get('skip_reason') == "Already processed, overwrite disabled"
    mock_log_info.assert_any_call(f"Asset 'ProcessedNoOverwriteAsset': Skipping because already processed and overwrite is disabled.")

@mock.patch('logging.info')
def test_no_skip_when_processed_and_overwrite_enabled(mock_log_info):
    """
    Test that the asset is NOT skipped if asset_rule.process_status is "PROCESSED"
    but overwrite_existing is True.
    """
    stage = AssetSkipLogicStage()
    context = create_skip_logic_mock_context(
        asset_process_status="PROCESSED", 
        overwrite_existing=True,
        effective_supplier="ValidSupplier", # Ensure supplier is valid
        asset_name="ProcessedOverwriteAsset"
    )
    
    updated_context = stage.execute(context)
    
    assert updated_context.status_flags.get('skip_asset', False) is False # Default to False if key not present
    # No specific skip_reason to check if not skipped
    # Check that no skip log message was called for this specific reason
    for call_args in mock_log_info.call_args_list:
        assert "Skipping because already processed and overwrite is disabled" not in call_args[0][0]
        assert "Skipping due to missing or invalid supplier" not in call_args[0][0]
        assert "Skipping because process_status is 'SKIP'" not in call_args[0][0]


@mock.patch('logging.info')
def test_no_skip_when_process_status_pending(mock_log_info):
    """
    Test that the asset is NOT skipped if asset_rule.process_status is "PENDING".
    """
    stage = AssetSkipLogicStage()
    context = create_skip_logic_mock_context(
        asset_process_status="PENDING",
        effective_supplier="ValidSupplier", # Ensure supplier is valid
        asset_name="PendingAsset"
    )
    
    updated_context = stage.execute(context)
    
    assert updated_context.status_flags.get('skip_asset', False) is False
    # Check that no skip log message was called
    for call_args in mock_log_info.call_args_list:
        assert "Skipping" not in call_args[0][0]


@mock.patch('logging.info')
def test_no_skip_when_process_status_failed_previously(mock_log_info):
    """
    Test that the asset is NOT skipped if asset_rule.process_status is "FAILED_PREVIOUSLY".
    """
    stage = AssetSkipLogicStage()
    context = create_skip_logic_mock_context(
        asset_process_status="FAILED_PREVIOUSLY",
        effective_supplier="ValidSupplier", # Ensure supplier is valid
        asset_name="FailedPreviouslyAsset"
    )
    
    updated_context = stage.execute(context)
    
    assert updated_context.status_flags.get('skip_asset', False) is False
    # Check that no skip log message was called
    for call_args in mock_log_info.call_args_list:
        assert "Skipping" not in call_args[0][0]

@mock.patch('logging.info')
def test_no_skip_when_process_status_other_valid_status(mock_log_info):
    """
    Test that the asset is NOT skipped for other valid, non-skip process statuses.
    """
    stage = AssetSkipLogicStage()
    context = create_skip_logic_mock_context(
        asset_process_status="READY_FOR_PROCESSING", # Example of another non-skip status
        effective_supplier="ValidSupplier",
        asset_name="ReadyAsset"
    )
    updated_context = stage.execute(context)
    assert updated_context.status_flags.get('skip_asset', False) is False
    for call_args in mock_log_info.call_args_list:
        assert "Skipping" not in call_args[0][0]

@mock.patch('logging.info')
def test_skip_asset_flag_initialized_if_not_present(mock_log_info):
    """
    Test that 'skip_asset' is initialized to False in status_flags if not skipped and not present.
    """
    stage = AssetSkipLogicStage()
    context = create_skip_logic_mock_context(
        asset_process_status="PENDING",
        effective_supplier="ValidSupplier",
        asset_name="InitFlagAsset"
    )
    # Ensure status_flags is empty before execute
    context.status_flags = {} 
    
    updated_context = stage.execute(context)
    
    # If not skipped, 'skip_asset' should be explicitly False.
    assert updated_context.status_flags.get('skip_asset') is False 
    # No skip reason should be set
    assert 'skip_reason' not in updated_context.status_flags
    for call_args in mock_log_info.call_args_list:
        assert "Skipping" not in call_args[0][0]