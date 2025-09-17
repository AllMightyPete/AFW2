
import logging
import re
from pathlib import Path
from typing import Optional, Dict, Any

from rule_structure import SourceRule, RuleSet, MapRule, AssetRule
from configuration import load_preset
from utils.structure_analyzer import analyze_archive_structure # Hypothetical utility

log = logging.getLogger(__name__)

# Regex to extract preset name (similar to monitor.py)
# Matches "[PresetName]_anything.zip/rar/7z"
PRESET_FILENAME_REGEX = re.compile(r"^\[?([a-zA-Z0-9_-]+)\]?_.*\.(zip|rar|7z)$", re.IGNORECASE)

class PredictionError(Exception):
    """Custom exception for prediction failures."""
    pass

def generate_source_rule_from_archive(archive_path: Path, config: Dict[str, Any]) -> SourceRule:
    """
    Generates a SourceRule hierarchy based on rules defined in a preset,
    determined by the archive filename.

    Args:
        archive_path: Path to the input archive file.
        config: The loaded application configuration dictionary, expected
                to contain preset information or a way to load it.

    Returns:
        The generated SourceRule hierarchy.

    Raises:
        PredictionError: If the preset cannot be determined, loaded, or
                         if rule generation fails.
        FileNotFoundError: If the archive_path does not exist.
    """
    if not archive_path.is_file():
        raise FileNotFoundError(f"Archive file not found: {archive_path}")

    log.debug(f"Generating SourceRule for archive: {archive_path.name}")

    match = PRESET_FILENAME_REGEX.match(archive_path.name)
    if not match:
        raise PredictionError(f"Filename '{archive_path.name}' does not match expected format '[preset]_filename.ext'. Cannot determine preset.")

    preset_name = match.group(1)
    log.info(f"Extracted preset name: '{preset_name}' from {archive_path.name}")

    try:
        # Assuming load_preset takes the name and maybe the base config/path
        # Adjust based on the actual signature of load_preset
        preset_config = load_preset(preset_name) # This might need config path or dict
        if not preset_config:
             raise PredictionError(f"Preset '{preset_name}' configuration is empty or invalid.")
        # Assuming the preset config directly contains the RuleSet structure
        # or needs parsing into RuleSet. Let's assume it needs parsing.
        # This part is highly dependent on how presets are stored and loaded.
        # For now, let's assume preset_config IS the RuleSet dictionary.
        if not isinstance(preset_config.get('rules'), dict):
             raise PredictionError(f"Preset '{preset_name}' does not contain a valid 'rules' dictionary.")
        rule_set_dict = preset_config['rules']
        # Assuming RuleSet has a class method or similar for this
        rule_set = RuleSet.from_dict(rule_set_dict) # Placeholder for actual deserialization

    except FileNotFoundError:
         raise PredictionError(f"Preset file for '{preset_name}' not found.")
    except Exception as e:
        log.exception(f"Failed to load or parse preset '{preset_name}': {e}")
        raise PredictionError(f"Failed to load or parse preset '{preset_name}': {e}")

    if not rule_set:
        raise PredictionError(f"Failed to obtain RuleSet for preset '{preset_name}'.")

    log.debug(f"Successfully loaded RuleSet for preset: {preset_name}")

    # This simulates what a RuleBasedPredictionHandler might do, but without
    # needing the actual extracted files for *this* step. The rules themselves
    # define the expected structure. The ProcessingEngine will later use this
    # rule against the actual extracted files.

    # The actual structure (AssetRules, MapRules) comes directly from the RuleSet.
    # We might need to adapt the archive name slightly (e.g., remove preset prefix)
    # for the root node name, depending on desired output structure.
    root_name = archive_path.stem
    source_rule = SourceRule(name=root_name, rule_set=rule_set)

    # Potentially add logic here if basic archive structure analysis *is* needed
    # for rule generation (e.g., using utils.structure_analyzer if it exists)

    log.info(f"Generated initial SourceRule for '{archive_path.name}' based on preset '{preset_name}'.")

    # No temporary workspace needed/created in this function based on current plan.
    # Cleanup is not required here.
    return source_rule

# Example Usage (Conceptual - requires actual config/presets)
if __name__ == '__main__':
    logging.basicConfig(level=logging.DEBUG)
    log.info("Testing prediction_utils...")

    dummy_archive = Path("./[TestPreset]_MyAsset.zip")
    dummy_archive.touch()

    preset_dir = Path(__file__).parent.parent / "Presets"
    preset_dir.mkdir(exist_ok=True)
    dummy_preset_path = preset_dir / "TestPreset.json"
    dummy_preset_content = """
    {
        "name": "TestPreset",
        "description": "A dummy preset for testing",
        "rules": {
            "map_rules": [
                {"pattern": ".*albedo.*", "map_type": "Albedo", "color_space": "sRGB"},
                {"pattern": ".*normal.*", "map_type": "Normal", "color_space": "Non-Color"}
            ],
            "asset_rules": [
                {"pattern": ".*", "material_name": "{asset_name}"}
            ]
        },
        "settings": {}
    }
    """







    log.warning("Note: Main execution block is commented out as it requires specific implementations of load_preset and RuleSet.from_dict.")