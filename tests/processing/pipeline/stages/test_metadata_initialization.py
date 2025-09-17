import pytest
from unittest import mock
from pathlib import Path
import datetime
import uuid
from typing import Optional

from processing.pipeline.stages.metadata_initialization import MetadataInitializationStage
from processing.pipeline.asset_context import AssetProcessingContext
from rule_structure import AssetRule, SourceRule
from configuration import Configuration, GeneralSettings

# Helper function to create a mock AssetProcessingContext
def create_metadata_init_mock_context(
    skip_asset_flag: bool = False,
    asset_name: str = "MetaAsset",
    asset_id: uuid.UUID = None, # Allow None to default to uuid.uuid4()
    source_path_str: str = "source/meta_asset",
    output_pattern: str = "{asset_name}/{map_type}",
    tags: list = None,
    custom_fields: dict = None,
    source_rule_name: str = "MetaSource",
    source_rule_id: uuid.UUID = None, # Allow None to default to uuid.uuid4()
    eff_supplier: Optional[str] = "SupplierMeta",
    app_version_str: str = "1.0.0-test",
    inc_val: Optional[str] = None,
    sha_val: Optional[str] = None
) -> AssetProcessingContext:
    mock_asset_rule = mock.MagicMock(spec=AssetRule)
    mock_asset_rule.name = asset_name
    mock_asset_rule.id = asset_id if asset_id is not None else uuid.uuid4()
    mock_asset_rule.source_path = Path(source_path_str)
    mock_asset_rule.output_path_pattern = output_pattern
    mock_asset_rule.tags = tags if tags is not None else ["tag1", "test_tag"]
    mock_asset_rule.custom_fields = custom_fields if custom_fields is not None else {"custom_key": "custom_value"}

    mock_source_rule = mock.MagicMock(spec=SourceRule)
    mock_source_rule.name = source_rule_name
    mock_source_rule.id = source_rule_id if source_rule_id is not None else uuid.uuid4()
    
    mock_general_settings = mock.MagicMock(spec=GeneralSettings)
    mock_general_settings.app_version = app_version_str
    
    mock_config = mock.MagicMock(spec=Configuration)
    mock_config.general_settings = mock_general_settings

    context = AssetProcessingContext(
        source_rule=mock_source_rule,
        asset_rule=mock_asset_rule,
        workspace_path=Path("/fake/workspace"),
        engine_temp_dir=Path("/fake/temp"),
        output_base_path=Path("/fake/output"),
        effective_supplier=eff_supplier,
        asset_metadata={},
        processed_maps_details={},
        merged_maps_details={},
        files_to_process=[],
        loaded_data_cache={},
        config_obj=mock_config,
        status_flags={'skip_asset': skip_asset_flag},
        incrementing_value=inc_val,
        sha5_value=sha_val
    )
    return context

@mock.patch('processing.pipeline.stages.metadata_initialization.datetime')
def test_metadata_initialization_not_skipped(mock_datetime_module):
    stage = MetadataInitializationStage()
    
    fixed_now = datetime.datetime(2023, 10, 26, 12, 0, 0, tzinfo=datetime.timezone.utc)
    mock_datetime_module.datetime.now.return_value = fixed_now
    
    asset_id_val = uuid.uuid4()
    source_id_val = uuid.uuid4()
    
    context = create_metadata_init_mock_context(
        skip_asset_flag=False,
        asset_id=asset_id_val,
        source_rule_id=source_id_val,
        inc_val="001",
        sha_val="abcde"
    )
    
    updated_context = stage.execute(context)
    
    assert isinstance(updated_context.asset_metadata, dict)
    assert isinstance(updated_context.processed_maps_details, dict)
    assert isinstance(updated_context.merged_maps_details, dict)
    
    md = updated_context.asset_metadata
    assert md['asset_name'] == "MetaAsset"
    assert md['asset_id'] == str(asset_id_val)
    assert md['source_rule_name'] == "MetaSource"
    assert md['source_rule_id'] == str(source_id_val)
    assert md['source_path'] == "source/meta_asset"
    assert md['effective_supplier'] == "SupplierMeta"
    assert md['output_path_pattern'] == "{asset_name}/{map_type}"
    assert md['processing_start_time'] == fixed_now.isoformat()
    assert md['status'] == "Pending"
    assert md['version'] == "1.0.0-test"
    assert md['tags'] == ["tag1", "test_tag"]
    assert md['custom_fields'] == {"custom_key": "custom_value"}
    assert md['incrementing_value'] == "001"
    assert md['sha5_value'] == "abcde"

@mock.patch('processing.pipeline.stages.metadata_initialization.datetime')
def test_metadata_initialization_not_skipped_none_inc_sha(mock_datetime_module):
    stage = MetadataInitializationStage()
    
    fixed_now = datetime.datetime(2023, 10, 26, 12, 0, 0, tzinfo=datetime.timezone.utc)
    mock_datetime_module.datetime.now.return_value = fixed_now
    
    context = create_metadata_init_mock_context(
        skip_asset_flag=False,
        inc_val=None,
        sha_val=None
    )
    
    updated_context = stage.execute(context)
    
    md = updated_context.asset_metadata
    assert 'incrementing_value' not in md # Or assert md['incrementing_value'] is None, depending on desired behavior
    assert 'sha5_value' not in md # Or assert md['sha5_value'] is None

def test_metadata_initialization_skipped():
    stage = MetadataInitializationStage()
    context = create_metadata_init_mock_context(skip_asset_flag=True)
    
    # Make copies of initial state to ensure they are not modified
    initial_asset_metadata = dict(context.asset_metadata)
    initial_processed_maps = dict(context.processed_maps_details)
    initial_merged_maps = dict(context.merged_maps_details)
            
    updated_context = stage.execute(context)
    
    assert updated_context.asset_metadata == initial_asset_metadata
    assert updated_context.processed_maps_details == initial_processed_maps
    assert updated_context.merged_maps_details == initial_merged_maps
    assert not updated_context.asset_metadata # Explicitly check it's empty as per initial setup
    assert not updated_context.processed_maps_details
    assert not updated_context.merged_maps_details

@mock.patch('processing.pipeline.stages.metadata_initialization.datetime')
def test_tags_and_custom_fields_are_copies(mock_datetime_module):
    stage = MetadataInitializationStage()
    fixed_now = datetime.datetime(2023, 10, 26, 12, 0, 0, tzinfo=datetime.timezone.utc)
    mock_datetime_module.datetime.now.return_value = fixed_now

    original_tags = ["original_tag"]
    original_custom_fields = {"original_key": "original_value"}

    context = create_metadata_init_mock_context(
        skip_asset_flag=False,
        tags=original_tags,
        custom_fields=original_custom_fields
    )

    # Modify originals after context creation but before stage execution
    original_tags.append("modified_after_creation")
    original_custom_fields["new_key_after_creation"] = "new_value"

    updated_context = stage.execute(context)

    md = updated_context.asset_metadata
    assert md['tags'] == ["original_tag"] # Should not have "modified_after_creation"
    assert md['tags'] is not original_tags # Ensure it's a different object

    assert md['custom_fields'] == {"original_key": "original_value"} # Should not have "new_key_after_creation"
    assert md['custom_fields'] is not original_custom_fields # Ensure it's a different object