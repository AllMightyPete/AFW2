import pytest
from unittest import mock
from pathlib import Path
import uuid
from typing import Optional # Added Optional for type hinting

from processing.pipeline.stages.file_rule_filter import FileRuleFilterStage
from processing.pipeline.asset_context import AssetProcessingContext
from rule_structure import AssetRule, SourceRule, FileRule # FileRule is key here
from configuration import Configuration # Minimal config needed

def create_mock_file_rule(
    id_val: Optional[uuid.UUID] = None,
    map_type: str = "Diffuse",
    filename_pattern: str = "*.tif",
    item_type: str = "MAP_COL", # e.g., MAP_COL, FILE_IGNORE
    active: bool = True
) -> mock.MagicMock: # Return MagicMock to easily set other attributes if needed
    mock_fr = mock.MagicMock(spec=FileRule)
    mock_fr.id = id_val if id_val else uuid.uuid4()
    mock_fr.map_type = map_type
    mock_fr.filename_pattern = filename_pattern
    mock_fr.item_type = item_type
    mock_fr.active = active
    return mock_fr

def create_file_filter_mock_context(
    file_rules_list: Optional[list] = None, # List of mock FileRule objects
    skip_asset_flag: bool = False,
    asset_name: str = "FileFilterAsset"
) -> AssetProcessingContext:
    mock_asset_rule = mock.MagicMock(spec=AssetRule)
    mock_asset_rule.name = asset_name
    mock_asset_rule.file_rules = file_rules_list if file_rules_list is not None else []

    mock_source_rule = mock.MagicMock(spec=SourceRule)
    mock_config = mock.MagicMock(spec=Configuration)

    context = AssetProcessingContext(
        source_rule=mock_source_rule,
        asset_rule=mock_asset_rule,
        workspace_path=Path("/fake/workspace"),
        engine_temp_dir=Path("/fake/temp"),
        output_base_path=Path("/fake/output"),
        effective_supplier="ValidSupplier", # Assume valid for this stage
        asset_metadata={'asset_name': asset_name}, # Assume metadata init happened
        processed_maps_details={},
        merged_maps_details={},
        files_to_process=[], # Stage will populate this
        loaded_data_cache={},
        config_obj=mock_config,
        status_flags={'skip_asset': skip_asset_flag},
        incrementing_value=None,
        sha5_value=None # Corrected from sha5_value to sha256_value based on AssetProcessingContext
    )
    return context
# Test Cases for FileRuleFilterStage.execute()

@mock.patch('logging.info')
@mock.patch('logging.debug')
def test_file_rule_filter_asset_skipped(mock_log_debug, mock_log_info):
    """
    Test case: Asset Skipped - status_flags['skip_asset'] is True.
    Assert context.files_to_process remains empty.
    """
    stage = FileRuleFilterStage()
    context = create_file_filter_mock_context(skip_asset_flag=True)
    
    updated_context = stage.execute(context)
    
    assert len(updated_context.files_to_process) == 0
    mock_log_info.assert_any_call(f"Asset '{context.asset_rule.name}': Skipping file rule filtering as 'skip_asset' is True.")

@mock.patch('logging.info')
@mock.patch('logging.debug')
def test_file_rule_filter_no_file_rules(mock_log_debug, mock_log_info):
    """
    Test case: No File Rules - asset_rule.file_rules is empty.
    Assert context.files_to_process is empty.
    """
    stage = FileRuleFilterStage()
    context = create_file_filter_mock_context(file_rules_list=[])
    
    updated_context = stage.execute(context)
    
    assert len(updated_context.files_to_process) == 0
    mock_log_info.assert_any_call(f"Asset '{context.asset_rule.name}': No file rules defined. Skipping file rule filtering.")

@mock.patch('logging.info')
@mock.patch('logging.debug')
def test_file_rule_filter_only_active_processable_rules(mock_log_debug, mock_log_info):
    """
    Test case: Only Active, Processable Rules - All FileRules are active=True and item_type="MAP_COL".
    Assert all are added to context.files_to_process.
    """
    stage = FileRuleFilterStage()
    fr1 = create_mock_file_rule(filename_pattern="diffuse.png", item_type="MAP_COL", active=True)
    fr2 = create_mock_file_rule(filename_pattern="normal.png", item_type="MAP_COL", active=True)
    context = create_file_filter_mock_context(file_rules_list=[fr1, fr2])
    
    updated_context = stage.execute(context)
    
    assert len(updated_context.files_to_process) == 2
    assert fr1 in updated_context.files_to_process
    assert fr2 in updated_context.files_to_process
    mock_log_info.assert_any_call(f"Asset '{context.asset_rule.name}': 2 file rules queued for processing after filtering.")

@mock.patch('logging.info')
@mock.patch('logging.debug')
def test_file_rule_filter_inactive_rules(mock_log_debug, mock_log_info):
    """
    Test case: Inactive Rules - Some FileRules have active=False.
    Assert only active rules are added.
    """
    stage = FileRuleFilterStage()
    fr_active = create_mock_file_rule(filename_pattern="active.png", item_type="MAP_COL", active=True)
    fr_inactive = create_mock_file_rule(filename_pattern="inactive.png", item_type="MAP_COL", active=False)
    fr_another_active = create_mock_file_rule(filename_pattern="another_active.jpg", item_type="MAP_COL", active=True)
    context = create_file_filter_mock_context(file_rules_list=[fr_active, fr_inactive, fr_another_active])
    
    updated_context = stage.execute(context)
    
    assert len(updated_context.files_to_process) == 2
    assert fr_active in updated_context.files_to_process
    assert fr_another_active in updated_context.files_to_process
    assert fr_inactive not in updated_context.files_to_process
    mock_log_debug.assert_any_call(f"Asset '{context.asset_rule.name}': Skipping inactive file rule: '{fr_inactive.filename_pattern}'")
    mock_log_info.assert_any_call(f"Asset '{context.asset_rule.name}': 2 file rules queued for processing after filtering.")

@mock.patch('logging.info')
@mock.patch('logging.debug')
def test_file_rule_filter_file_ignore_simple_match(mock_log_debug, mock_log_info):
    """
    Test case: FILE_IGNORE Rule (Simple Match).
    One FILE_IGNORE rule with filename_pattern="*_ignore.png".
    One MAP_COL rule with filename_pattern="diffuse_ignore.png".
    One MAP_COL rule with filename_pattern="normal_process.png".
    Assert only "normal_process.png" rule is added.
    """
    stage = FileRuleFilterStage()
    fr_ignore = create_mock_file_rule(filename_pattern="*_ignore.png", item_type="FILE_IGNORE", active=True)
    fr_ignored_map = create_mock_file_rule(filename_pattern="diffuse_ignore.png", item_type="MAP_COL", active=True)
    fr_process_map = create_mock_file_rule(filename_pattern="normal_process.png", item_type="MAP_COL", active=True)
    context = create_file_filter_mock_context(file_rules_list=[fr_ignore, fr_ignored_map, fr_process_map])

    updated_context = stage.execute(context)

    assert len(updated_context.files_to_process) == 1
    assert fr_process_map in updated_context.files_to_process
    assert fr_ignored_map not in updated_context.files_to_process
    mock_log_debug.assert_any_call(f"Asset '{context.asset_rule.name}': Registering ignore pattern: '{fr_ignore.filename_pattern}'")
    mock_log_debug.assert_any_call(f"Asset '{context.asset_rule.name}': Skipping file rule '{fr_ignored_map.filename_pattern}' due to matching ignore pattern.")
    mock_log_info.assert_any_call(f"Asset '{context.asset_rule.name}': 1 file rules queued for processing after filtering.")

@mock.patch('logging.info')
@mock.patch('logging.debug')
def test_file_rule_filter_file_ignore_glob_pattern(mock_log_debug, mock_log_info):
    """
    Test case: FILE_IGNORE Rule (Glob Pattern).
    One FILE_IGNORE rule with filename_pattern="*_ignore.*".
    MAP_COL rules: "tex_ignore.tif", "tex_process.png".
    Assert only "tex_process.png" rule is added.
    """
    stage = FileRuleFilterStage()
    fr_ignore_glob = create_mock_file_rule(filename_pattern="*_ignore.*", item_type="FILE_IGNORE", active=True)
    fr_ignored_tif = create_mock_file_rule(filename_pattern="tex_ignore.tif", item_type="MAP_COL", active=True)
    fr_process_png = create_mock_file_rule(filename_pattern="tex_process.png", item_type="MAP_COL", active=True)
    context = create_file_filter_mock_context(file_rules_list=[fr_ignore_glob, fr_ignored_tif, fr_process_png])

    updated_context = stage.execute(context)

    assert len(updated_context.files_to_process) == 1
    assert fr_process_png in updated_context.files_to_process
    assert fr_ignored_tif not in updated_context.files_to_process
    mock_log_debug.assert_any_call(f"Asset '{context.asset_rule.name}': Registering ignore pattern: '{fr_ignore_glob.filename_pattern}'")
    mock_log_debug.assert_any_call(f"Asset '{context.asset_rule.name}': Skipping file rule '{fr_ignored_tif.filename_pattern}' due to matching ignore pattern.")
    mock_log_info.assert_any_call(f"Asset '{context.asset_rule.name}': 1 file rules queued for processing after filtering.")

@mock.patch('logging.info')
@mock.patch('logging.debug')
def test_file_rule_filter_multiple_file_ignore_rules(mock_log_debug, mock_log_info):
    """
    Test case: Multiple FILE_IGNORE Rules.
    Test with several ignore patterns and ensure they are all respected.
    """
    stage = FileRuleFilterStage()
    fr_ignore1 = create_mock_file_rule(filename_pattern="*.tmp", item_type="FILE_IGNORE", active=True)
    fr_ignore2 = create_mock_file_rule(filename_pattern="backup_*", item_type="FILE_IGNORE", active=True)
    fr_ignore3 = create_mock_file_rule(filename_pattern="*_old.png", item_type="FILE_IGNORE", active=True)
    
    fr_map_ignored1 = create_mock_file_rule(filename_pattern="data.tmp", item_type="MAP_COL", active=True)
    fr_map_ignored2 = create_mock_file_rule(filename_pattern="backup_diffuse.jpg", item_type="MAP_COL", active=True)
    fr_map_ignored3 = create_mock_file_rule(filename_pattern="normal_old.png", item_type="MAP_COL", active=True)
    fr_map_process = create_mock_file_rule(filename_pattern="final_texture.tif", item_type="MAP_COL", active=True)
    
    context = create_file_filter_mock_context(file_rules_list=[
        fr_ignore1, fr_ignore2, fr_ignore3,
        fr_map_ignored1, fr_map_ignored2, fr_map_ignored3, fr_map_process
    ])

    updated_context = stage.execute(context)

    assert len(updated_context.files_to_process) == 1
    assert fr_map_process in updated_context.files_to_process
    assert fr_map_ignored1 not in updated_context.files_to_process
    assert fr_map_ignored2 not in updated_context.files_to_process
    assert fr_map_ignored3 not in updated_context.files_to_process
    mock_log_debug.assert_any_call(f"Asset '{context.asset_rule.name}': Registering ignore pattern: '{fr_ignore1.filename_pattern}'")
    mock_log_debug.assert_any_call(f"Asset '{context.asset_rule.name}': Registering ignore pattern: '{fr_ignore2.filename_pattern}'")
    mock_log_debug.assert_any_call(f"Asset '{context.asset_rule.name}': Registering ignore pattern: '{fr_ignore3.filename_pattern}'")
    mock_log_debug.assert_any_call(f"Asset '{context.asset_rule.name}': Skipping file rule '{fr_map_ignored1.filename_pattern}' due to matching ignore pattern.")
    mock_log_debug.assert_any_call(f"Asset '{context.asset_rule.name}': Skipping file rule '{fr_map_ignored2.filename_pattern}' due to matching ignore pattern.")
    mock_log_debug.assert_any_call(f"Asset '{context.asset_rule.name}': Skipping file rule '{fr_map_ignored3.filename_pattern}' due to matching ignore pattern.")
    mock_log_info.assert_any_call(f"Asset '{context.asset_rule.name}': 1 file rules queued for processing after filtering.")

@mock.patch('logging.info')
@mock.patch('logging.debug')
def test_file_rule_filter_file_ignore_rule_is_inactive(mock_log_debug, mock_log_info):
    """
    Test case: FILE_IGNORE Rule is Inactive.
    An ignore rule itself is active=False. Assert its pattern is NOT used for filtering.
    """
    stage = FileRuleFilterStage()
    fr_inactive_ignore = create_mock_file_rule(filename_pattern="*_ignore.tif", item_type="FILE_IGNORE", active=False)
    fr_should_process1 = create_mock_file_rule(filename_pattern="diffuse_ignore.tif", item_type="MAP_COL", active=True) # Should be processed
    fr_should_process2 = create_mock_file_rule(filename_pattern="normal_ok.png", item_type="MAP_COL", active=True)
    context = create_file_filter_mock_context(file_rules_list=[fr_inactive_ignore, fr_should_process1, fr_should_process2])

    updated_context = stage.execute(context)

    assert len(updated_context.files_to_process) == 2
    assert fr_should_process1 in updated_context.files_to_process
    assert fr_should_process2 in updated_context.files_to_process
    # Ensure the inactive ignore rule's pattern was not registered
    # We check this by ensuring no debug log for registering *that specific* pattern was made.
    # A more robust way would be to check mock_log_debug.call_args_list, but this is simpler for now.
    for call in mock_log_debug.call_args_list:
        args, kwargs = call
        if "Registering ignore pattern" in args[0] and fr_inactive_ignore.filename_pattern in args[0]:
            pytest.fail(f"Inactive ignore pattern '{fr_inactive_ignore.filename_pattern}' was incorrectly registered.")
    mock_log_debug.assert_any_call(f"Asset '{context.asset_rule.name}': Skipping inactive file rule: '{fr_inactive_ignore.filename_pattern}' (type: FILE_IGNORE)")
    mock_log_info.assert_any_call(f"Asset '{context.asset_rule.name}': 2 file rules queued for processing after filtering.")


@mock.patch('logging.info')
@mock.patch('logging.debug')
def test_file_rule_filter_no_file_ignore_rules(mock_log_debug, mock_log_info):
    """
    Test case: No FILE_IGNORE Rules.
    All rules are MAP_COL or other processable types.
    Assert all active, processable rules are included.
    """
    stage = FileRuleFilterStage()
    fr1 = create_mock_file_rule(filename_pattern="diffuse.png", item_type="MAP_COL", active=True)
    fr2 = create_mock_file_rule(filename_pattern="normal.png", item_type="MAP_COL", active=True)
    fr_other_type = create_mock_file_rule(filename_pattern="spec.tif", item_type="MAP_SPEC", active=True) # Assuming MAP_SPEC is processable
    fr_inactive = create_mock_file_rule(filename_pattern="ao.jpg", item_type="MAP_AO", active=False)
    
    context = create_file_filter_mock_context(file_rules_list=[fr1, fr2, fr_other_type, fr_inactive])
    
    updated_context = stage.execute(context)
    
    assert len(updated_context.files_to_process) == 3
    assert fr1 in updated_context.files_to_process
    assert fr2 in updated_context.files_to_process
    assert fr_other_type in updated_context.files_to_process
    assert fr_inactive not in updated_context.files_to_process
    mock_log_debug.assert_any_call(f"Asset '{context.asset_rule.name}': Skipping inactive file rule: '{fr_inactive.filename_pattern}'")
    mock_log_info.assert_any_call(f"Asset '{context.asset_rule.name}': 3 file rules queued for processing after filtering.")

@mock.patch('logging.info')
@mock.patch('logging.debug')
def test_file_rule_filter_item_type_not_processable(mock_log_debug, mock_log_info):
    """
    Test case: Item type is not processable (e.g., not MAP_COL, MAP_AO etc., but something else like 'METADATA_ONLY').
    Assert such rules are not added to files_to_process, unless they are FILE_IGNORE.
    """
    stage = FileRuleFilterStage()
    fr_processable = create_mock_file_rule(filename_pattern="diffuse.png", item_type="MAP_COL", active=True)
    fr_not_processable = create_mock_file_rule(filename_pattern="info.txt", item_type="METADATA_ONLY", active=True)
    fr_ignore = create_mock_file_rule(filename_pattern="*.bak", item_type="FILE_IGNORE", active=True)
    fr_ignored_by_bak = create_mock_file_rule(filename_pattern="diffuse.bak", item_type="MAP_COL", active=True)

    context = create_file_filter_mock_context(file_rules_list=[fr_processable, fr_not_processable, fr_ignore, fr_ignored_by_bak])
    
    updated_context = stage.execute(context)
    
    assert len(updated_context.files_to_process) == 1
    assert fr_processable in updated_context.files_to_process
    assert fr_not_processable not in updated_context.files_to_process
    assert fr_ignored_by_bak not in updated_context.files_to_process

    mock_log_debug.assert_any_call(f"Asset '{context.asset_rule.name}': Registering ignore pattern: '{fr_ignore.filename_pattern}'")
    mock_log_debug.assert_any_call(f"Asset '{context.asset_rule.name}': Skipping file rule '{fr_not_processable.filename_pattern}' as its item_type '{fr_not_processable.item_type}' is not processable.")
    mock_log_debug.assert_any_call(f"Asset '{context.asset_rule.name}': Skipping file rule '{fr_ignored_by_bak.filename_pattern}' due to matching ignore pattern.")
    mock_log_info.assert_any_call(f"Asset '{context.asset_rule.name}': 1 file rules queued for processing after filtering.")

# Example tests from instructions (can be adapted or used as a base)
@mock.patch('logging.info')
@mock.patch('logging.debug')
def test_file_rule_filter_basic_active_example(mock_log_debug, mock_log_info): # Renamed to avoid conflict
    stage = FileRuleFilterStage()
    fr1 = create_mock_file_rule(filename_pattern="diffuse.png", item_type="MAP_COL", active=True)
    fr2 = create_mock_file_rule(filename_pattern="normal.png", item_type="MAP_COL", active=True)
    context = create_file_filter_mock_context(file_rules_list=[fr1, fr2])
    
    updated_context = stage.execute(context)
    
    assert len(updated_context.files_to_process) == 2
    assert fr1 in updated_context.files_to_process
    assert fr2 in updated_context.files_to_process
    mock_log_info.assert_any_call(f"Asset '{context.asset_rule.name}': 2 file rules queued for processing after filtering.")

@mock.patch('logging.info')
@mock.patch('logging.debug')
def test_file_rule_filter_with_file_ignore_example(mock_log_debug, mock_log_info): # Renamed to avoid conflict
    stage = FileRuleFilterStage()
    fr_ignore = create_mock_file_rule(filename_pattern="*_ignore.tif", item_type="FILE_IGNORE", active=True)
    fr_process = create_mock_file_rule(filename_pattern="diffuse_ok.tif", item_type="MAP_COL", active=True)
    fr_skip = create_mock_file_rule(filename_pattern="normal_ignore.tif", item_type="MAP_COL", active=True)
    context = create_file_filter_mock_context(file_rules_list=[fr_ignore, fr_process, fr_skip])

    updated_context = stage.execute(context)

    assert len(updated_context.files_to_process) == 1
    assert fr_process in updated_context.files_to_process
    assert fr_skip not in updated_context.files_to_process
    mock_log_debug.assert_any_call(f"Asset '{context.asset_rule.name}': Registering ignore pattern: '{fr_ignore.filename_pattern}'")
    mock_log_debug.assert_any_call(f"Asset '{context.asset_rule.name}': Skipping file rule '{fr_skip.filename_pattern}' due to matching ignore pattern.")
    mock_log_info.assert_any_call(f"Asset '{context.asset_rule.name}': 1 file rules queued for processing after filtering.")