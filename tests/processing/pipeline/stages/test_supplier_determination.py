import pytest
from unittest import mock
from pathlib import Path
from typing import Dict, List, Optional, Any

# Assuming pytest is run from project root, adjust if necessary
from processing.pipeline.stages.supplier_determination import SupplierDeterminationStage
from processing.pipeline.asset_context import AssetProcessingContext
from rule_structure import AssetRule, SourceRule, FileRule # For constructing mock context
from configuration import Configuration, GeneralSettings, Supplier # For mock config

# Example helper (can be a pytest fixture too)
def create_mock_context(
    asset_rule_supplier_override: Optional[str] = None,
    source_rule_supplier: Optional[str] = None,
    config_suppliers: Optional[Dict[str, Any]] = None, # Mocked Supplier objects or dicts
    asset_name: str = "TestAsset"
) -> AssetProcessingContext:
    mock_asset_rule = mock.MagicMock(spec=AssetRule)
    mock_asset_rule.name = asset_name
    mock_asset_rule.supplier_override = asset_rule_supplier_override
    # ... other AssetRule fields if needed by the stage ...

    mock_source_rule = mock.MagicMock(spec=SourceRule)
    mock_source_rule.supplier = source_rule_supplier
    # ... other SourceRule fields ...

    mock_config = mock.MagicMock(spec=Configuration)
    mock_config.suppliers = config_suppliers if config_suppliers is not None else {}
    
    # Basic AssetProcessingContext fields
    context = AssetProcessingContext(
        source_rule=mock_source_rule,
        asset_rule=mock_asset_rule,
        workspace_path=Path("/fake/workspace"),
        engine_temp_dir=Path("/fake/temp"),
        output_base_path=Path("/fake/output"),
        effective_supplier=None,
        asset_metadata={},
        processed_maps_details={},
        merged_maps_details={},
        files_to_process=[],
        loaded_data_cache={},
        config_obj=mock_config,
        status_flags={},
        incrementing_value=None,
        sha5_value=None # Corrected from sha5_value to sha256_value if that's the actual field name
    )
    return context

@pytest.fixture
def supplier_stage():
    return SupplierDeterminationStage()

@mock.patch('logging.error')
@mock.patch('logging.info')
def test_supplier_from_asset_rule_override_valid(mock_log_info, mock_log_error, supplier_stage):
    mock_suppliers_config = {"SupplierA": mock.MagicMock(spec=Supplier)}
    context = create_mock_context(
        asset_rule_supplier_override="SupplierA",
        config_suppliers=mock_suppliers_config
    )
    
    updated_context = supplier_stage.execute(context)
    
    assert updated_context.effective_supplier == "SupplierA"
    assert not updated_context.status_flags.get('supplier_error')
    mock_log_info.assert_any_call("Effective supplier for asset 'TestAsset' set to 'SupplierA' from asset rule override.")
    mock_log_error.assert_not_called()

@mock.patch('logging.error')
@mock.patch('logging.info')
def test_supplier_from_source_rule_fallback_valid(mock_log_info, mock_log_error, supplier_stage):
    mock_suppliers_config = {"SupplierB": mock.MagicMock(spec=Supplier)}
    context = create_mock_context(
        asset_rule_supplier_override=None,
        source_rule_supplier="SupplierB",
        config_suppliers=mock_suppliers_config
    )
    
    updated_context = supplier_stage.execute(context)
    
    assert updated_context.effective_supplier == "SupplierB"
    assert not updated_context.status_flags.get('supplier_error')
    mock_log_info.assert_any_call("Effective supplier for asset 'TestAsset' set to 'SupplierB' from source rule.")
    mock_log_error.assert_not_called()

@mock.patch('logging.error')
@mock.patch('logging.warning') # supplier_determination uses logging.warning for invalid suppliers
def test_asset_rule_override_invalid_supplier(mock_log_warning, mock_log_error, supplier_stage):
    context = create_mock_context(
        asset_rule_supplier_override="InvalidSupplier",
        config_suppliers={"SupplierA": mock.MagicMock(spec=Supplier)} # "InvalidSupplier" not in config
    )
    
    updated_context = supplier_stage.execute(context)
    
    assert updated_context.effective_supplier is None
    assert updated_context.status_flags.get('supplier_error') is True
    mock_log_warning.assert_any_call(
        "Asset 'TestAsset' has supplier_override 'InvalidSupplier' which is not defined in global suppliers. No supplier set."
    )
    mock_log_error.assert_not_called()


@mock.patch('logging.error')
@mock.patch('logging.warning')
def test_source_rule_fallback_invalid_supplier(mock_log_warning, mock_log_error, supplier_stage):
    context = create_mock_context(
        asset_rule_supplier_override=None,
        source_rule_supplier="InvalidSupplierB",
        config_suppliers={"SupplierA": mock.MagicMock(spec=Supplier)} # "InvalidSupplierB" not in config
    )
    
    updated_context = supplier_stage.execute(context)
    
    assert updated_context.effective_supplier is None
    assert updated_context.status_flags.get('supplier_error') is True
    mock_log_warning.assert_any_call(
        "Asset 'TestAsset' has source rule supplier 'InvalidSupplierB' which is not defined in global suppliers. No supplier set."
    )
    mock_log_error.assert_not_called()

@mock.patch('logging.error')
@mock.patch('logging.warning')
def test_no_supplier_defined(mock_log_warning, mock_log_error, supplier_stage):
    context = create_mock_context(
        asset_rule_supplier_override=None,
        source_rule_supplier=None,
        config_suppliers={"SupplierA": mock.MagicMock(spec=Supplier)}
    )
    
    updated_context = supplier_stage.execute(context)
    
    assert updated_context.effective_supplier is None
    assert updated_context.status_flags.get('supplier_error') is True
    mock_log_warning.assert_any_call(
        "No supplier could be determined for asset 'TestAsset'. "
        "AssetRule override is None and SourceRule supplier is None or empty."
    )
    mock_log_error.assert_not_called()

@mock.patch('logging.error')
@mock.patch('logging.warning')
def test_empty_config_suppliers_with_asset_override(mock_log_warning, mock_log_error, supplier_stage):
    context = create_mock_context(
        asset_rule_supplier_override="SupplierX",
        config_suppliers={} # Empty global supplier config
    )
    
    updated_context = supplier_stage.execute(context)
    
    assert updated_context.effective_supplier is None
    assert updated_context.status_flags.get('supplier_error') is True
    mock_log_warning.assert_any_call(
         "Asset 'TestAsset' has supplier_override 'SupplierX' which is not defined in global suppliers. No supplier set."
    )
    mock_log_error.assert_not_called()

@mock.patch('logging.error')
@mock.patch('logging.warning')
def test_empty_config_suppliers_with_source_rule(mock_log_warning, mock_log_error, supplier_stage):
    context = create_mock_context(
        source_rule_supplier="SupplierY",
        config_suppliers={} # Empty global supplier config
    )
    
    updated_context = supplier_stage.execute(context)
    
    assert updated_context.effective_supplier is None
    assert updated_context.status_flags.get('supplier_error') is True
    mock_log_warning.assert_any_call(
        "Asset 'TestAsset' has source rule supplier 'SupplierY' which is not defined in global suppliers. No supplier set."
    )
    mock_log_error.assert_not_called()

@mock.patch('logging.error')
@mock.patch('logging.info')
def test_asset_rule_override_empty_string(mock_log_info, mock_log_error, supplier_stage):
    # This scenario should fall back to source_rule.supplier if asset_rule.supplier_override is ""
    mock_suppliers_config = {"SupplierB": mock.MagicMock(spec=Supplier)}
    context = create_mock_context(
        asset_rule_supplier_override="", # Empty string override
        source_rule_supplier="SupplierB",
        config_suppliers=mock_suppliers_config
    )
    
    updated_context = supplier_stage.execute(context)
    
    assert updated_context.effective_supplier == "SupplierB" # Falls back to SourceRule
    assert not updated_context.status_flags.get('supplier_error')
    mock_log_info.assert_any_call("Effective supplier for asset 'TestAsset' set to 'SupplierB' from source rule.")
    mock_log_error.assert_not_called()

@mock.patch('logging.error')
@mock.patch('logging.warning')
def test_source_rule_supplier_empty_string(mock_log_warning, mock_log_error, supplier_stage):
    # This scenario should result in an error if asset_rule.supplier_override is None and source_rule.supplier is ""
    context = create_mock_context(
        asset_rule_supplier_override=None,
        source_rule_supplier="", # Empty string source supplier
        config_suppliers={"SupplierA": mock.MagicMock(spec=Supplier)}
    )
    
    updated_context = supplier_stage.execute(context)
    
    assert updated_context.effective_supplier is None
    assert updated_context.status_flags.get('supplier_error') is True
    mock_log_warning.assert_any_call(
        "No supplier could be determined for asset 'TestAsset'. "
        "AssetRule override is None and SourceRule supplier is None or empty."
    )
    mock_log_error.assert_not_called()