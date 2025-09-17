import logging
from pathlib import Path
import time
import os
import re
import tempfile
import zipfile
from collections import defaultdict, Counter
from typing import List, Dict, Any

# --- PySide6 Imports ---
from PySide6.QtCore import QObject, Slot # Keep QObject for parent type hint, Slot for classify_files if kept as method
# Removed Signal, QThread as they are handled by BasePredictionHandler or caller

# --- Backend Imports ---
import sys
script_dir = Path(__file__).parent
project_root = script_dir.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

try:
    from configuration import Configuration, ConfigurationError
    from rule_structure import SourceRule, AssetRule, FileRule
    from .base_prediction_handler import BasePredictionHandler
    BACKEND_AVAILABLE = True
except ImportError as e:
    print(f"ERROR (RuleBasedPredictionHandler): Failed to import backend/config/base modules: {e}")
    Configuration = None
    load_base_config = None
    ConfigurationError = Exception
    SourceRule, AssetRule, FileRule = (None,)*3
    BACKEND_AVAILABLE = False

log = logging.getLogger(__name__)
if not log.hasHandlers():
     logging.basicConfig(level=logging.INFO, format='%(levelname)s (RuleBasedPredictHandler): %(message)s')


def classify_files(file_list: List[str], config: Configuration) -> Dict[str, List[Dict[str, Any]]]:
    """
    Analyzes a list of files based on configuration rules to group them by asset
    and determine initial file properties, applying prioritization based on
    'priority_keywords' in map_type_mapping.

    Args:
        file_list: List of absolute file paths.
        config: The loaded Configuration object containing naming rules.

    Returns:
        A dictionary grouping file information by predicted asset name.
        Example:
        {
            'AssetName1': [
                {'file_path': '/path/to/AssetName1_DISP16.png', 'item_type': 'MAP_DISP', 'asset_name': 'AssetName1'},
                {'file_path': '/path/to/AssetName1_Color.png', 'item_type': 'MAP_COL', 'asset_name': 'AssetName1'}
            ],
            # ... other assets
        }
        Files marked as "FILE_IGNORE" will also be included in the output.
        Returns an empty dict if classification fails or no files are provided.
    """
    classified_files_info: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    file_matches: Dict[str, List[Tuple[str, int, bool]]] = defaultdict(list) # {file_path: [(target_type, rule_index, is_priority), ...]}
    files_to_ignore: Set[str] = set()

    # --- DEBUG: Log the input file_list ---
    log.info(f"DEBUG_ROO_CLASSIFY_INPUT: classify_files received file_list (len={len(file_list)}): {file_list}")
    # --- END DEBUG ---

    # --- Validation ---
    if not file_list or not config:
        log.warning("Classification skipped: Missing file list or config.")
        return {}
    if not hasattr(config, 'compiled_map_keyword_regex') or not config.compiled_map_keyword_regex:
        log.warning("Classification skipped: Missing compiled map keyword regex in config.")
        # Proceeding might still classify EXTRA/FILE_IGNORE if those rules exist
    if not hasattr(config, 'compiled_extra_regex'):
         log.warning("Configuration object missing 'compiled_extra_regex'. Cannot classify extra files.")
         compiled_extra_regex = [] # Provide default to avoid errors
    else:
         compiled_extra_regex = getattr(config, 'compiled_extra_regex', [])

    compiled_map_regex = getattr(config, 'compiled_map_keyword_regex', {})
    # Note: compiled_bit_depth_regex_map is no longer used for primary classification logic here

    num_map_rules = sum(len(patterns) for patterns in compiled_map_regex.values())
    num_extra_rules = len(compiled_extra_regex)

    log.debug(f"Starting classification for {len(file_list)} files using {num_map_rules} map keyword patterns and {num_extra_rules} extra patterns.")

    # --- Asset Name Extraction Helper ---
    def get_asset_name(f_path: Path, cfg: Configuration) -> str:
        filename = f_path.name
        asset_name = None
        try:
            separator = cfg.source_naming_separator
            indices = cfg.source_naming_indices
            base_name_index = indices.get('base_name')

            if separator is not None and base_name_index is not None:
                stem = f_path.stem
                parts = stem.split(separator)
                if 0 <= base_name_index < len(parts):
                    asset_name = parts[base_name_index]
                else:
                    log.warning(f"Preset base_name index {base_name_index} out of bounds for '{stem}' split by '{separator}'. Falling back.")
            else:
                 log.debug(f"Preset rules for asset name extraction incomplete (separator: {separator}, index: {base_name_index}). Falling back for '{filename}'.")

            if not asset_name:
                asset_name = f_path.stem.split('_')[0] if '_' in f_path.stem else f_path.stem
                log.debug(f"Used fallback asset name extraction: '{asset_name}' for '{filename}'.")

        except Exception as e:
            log.exception(f"Error extracting asset name for '{filename}': {e}. Falling back to stem.")
            asset_name = f_path.stem

        if not asset_name:
             asset_name = f_path.stem
             log.warning(f"Asset name extraction resulted in empty string for '{filename}'. Using stem: '{asset_name}'.")
        return asset_name

    # --- Pass 1: Collect all potential matches for each file ---
    # For each file, find all map_type_mapping rules it matches (both regular and priority keywords).
    # Store the target_type, original rule_index, and whether it was a priority match.
    log.debug("--- Starting Classification Pass 1: Collect Potential Matches ---")
    file_matches: Dict[str, List[Tuple[str, int, bool]]] = defaultdict(list) # {file_path: [(target_type, rule_index, is_priority), ...]}
    files_classified_as_extra: Set[str] = set() # Files already classified as EXTRA

    compiled_map_regex = getattr(config, 'compiled_map_keyword_regex', {})
    compiled_extra_regex = getattr(config, 'compiled_extra_regex', [])

    for file_path_str in file_list:
        file_path = Path(file_path_str)
        filename = file_path.name
        asset_name = get_asset_name(file_path, config)

        if "BoucleChunky001" in file_path_str:
            log.info(f"DEBUG_ROO: Processing file: {file_path_str}")

        # Check for EXTRA files first
        is_extra = False
        for extra_pattern in compiled_extra_regex:
            if extra_pattern.search(filename):
                if "BoucleChunky001_DISP_1K_METALNESS.png" in filename and extra_pattern.search(filename):
                    log.info(f"DEBUG_ROO: EXTRA MATCH: File '{filename}' matched EXTRA pattern: {extra_pattern.pattern}")
                log.debug(f"PASS 1: File '{filename}' matched EXTRA pattern: {extra_pattern.pattern}")
                # For EXTRA, we assign it directly and don't check map rules for this file
                classified_files_info[asset_name].append({
                    'file_path': file_path_str,
                    'item_type': "EXTRA",
                    'asset_name': asset_name
                })
                files_classified_as_extra.add(file_path_str)
                is_extra = True
                break

        if "BoucleChunky001_DISP_1K_METALNESS.png" in filename and not is_extra: # after the extra loop
            log.info(f"DEBUG_ROO: EXTRA CHECK FAILED for {filename}. is_extra: {is_extra}")

        if "BoucleChunky001_DISP_1K_METALNESS.png" in filename and not is_extra:
            log.info(f"DEBUG_ROO: EXTRA CHECK FAILED for {filename}. is_extra: {is_extra}")

        if is_extra:
            continue # Move to the next file

        # If not EXTRA, check for MAP matches (collect all potential matches)
        for target_type, patterns_list in compiled_map_regex.items():
            for compiled_regex, original_keyword, rule_index, is_priority in patterns_list:
                match = compiled_regex.search(filename)
                if match:
                    if "BoucleChunky001" in file_path_str:
                        log.info(f"DEBUG_ROO: PASS 1 MAP MATCH: File '{filename}' matched keyword '{original_keyword}' (priority: {is_priority}) for target type '{target_type}' (Rule Index: {rule_index}).")
                    log.debug(f"  PASS 1: File '{filename}' matched keyword '{original_keyword}' (priority: {is_priority}) for target type '{target_type}' (Rule Index: {rule_index}).")
                    file_matches[file_path_str].append((target_type, rule_index, is_priority))

    log.debug(f"--- Finished Pass 1. Collected matches for {len(file_matches)} files. ---")

    # --- Pass 2: Determine Trumped Regular Matches ---
    # Identify which regular matches are trumped by a priority match for the same rule_index within the asset.
    log.debug("--- Starting Classification Pass 2: Determine Trumped Regular Matches ---")

    trumped_regular_matches: Set[Tuple[str, int]] = set() # Set of (file_path_str, rule_index) pairs that are trumped

    # First, determine which rule_indices have *any* priority match across the entire asset
    rule_index_has_priority_match_in_asset: Set[int] = set()
    for file_path_str, matches in file_matches.items():
        for match_target, match_rule_index, match_is_priority in matches:
            if match_is_priority:
                rule_index_has_priority_match_in_asset.add(match_rule_index)

    log.debug(f"  Rule indices with priority matches in asset: {sorted(list(rule_index_has_priority_match_in_asset))}")

    # Then, for each file, check its matches against the rules that had priority matches
    for file_path_str in file_list:
        if file_path_str in files_classified_as_extra:
            continue

        matches_for_this_file = file_matches.get(file_path_str, [])

        # Determine if this file has any priority match for a given rule_index
        file_has_priority_match_for_rule: Dict[int, bool] = defaultdict(bool)
        for match_target, match_rule_index, match_is_priority in matches_for_this_file:
            if match_is_priority:
                file_has_priority_match_for_rule[match_rule_index] = True

        # Determine if this file has any regular match for a given rule_index
        file_has_regular_match_for_rule: Dict[int, bool] = defaultdict(bool)
        for match_target, match_rule_index, match_is_priority in matches_for_this_file:
            if not match_is_priority:
                file_has_regular_match_for_rule[match_rule_index] = True

        # Identify trumped regular matches for this file
        for match_target, match_rule_index, match_is_priority in matches_for_this_file:
            if not match_is_priority: # Only consider regular matches
                if match_rule_index in rule_index_has_priority_match_in_asset:
                    # This regular match is for a rule_index that had a priority match somewhere in the asset
                    if not file_has_priority_match_for_rule[match_rule_index]:
                        # And this specific file did NOT have a priority match for this rule_index
                        trumped_regular_matches.add((file_path_str, match_rule_index))
                        log.debug(f"  File '{Path(file_path_str).name}': Regular match for Rule Index {match_rule_index} is trumped.")
                        if "BoucleChunky001" in file_path_str:
                            log.info(f"DEBUG_ROO: TRUMPED: File '{Path(file_path_str).name}': Regular match for Rule Index {match_rule_index} (target {match_target}) is trumped.")
                        if "BoucleChunky001" in file_path_str: # Check if it was actually added by checking the set, or just log if the condition was met
                             if (file_path_str, match_rule_index) in trumped_regular_matches:
                                log.info(f"DEBUG_ROO: TRUMPED: File '{Path(file_path_str).name}': Regular match for Rule Index {match_rule_index} (target {match_target}) is trumped.")


    log.debug(f"--- Finished Pass 2. Identified {len(trumped_regular_matches)} trumped regular matches. ---")

    # --- Pass 3: Final Assignment & Inter-Entry Resolution ---
    # Iterate through files, apply ignore rules, and then apply earliest rule wins for remaining valid matches.
    log.debug("--- Starting Classification Pass 3: Final Assignment ---")

    final_file_assignments: Dict[str, str] = {} # {file_path: final_item_type}


    for file_path_str in file_list:
        # Check if the file was already classified as EXTRA in Pass 1 and added to classified_files_info
        if file_path_str in files_classified_as_extra:
            log.debug(f"  Final Assignment: Skipping '{Path(file_path_str).name}' as it was already classified as EXTRA in Pass 1.")
            continue # Skip this file in Pass 3 as it's already handled

        asset_name = get_asset_name(Path(file_path_str), config) # Need asset name for the final output structure

        # Get valid matches for this file after considering intra-entry priority trumps regular
        valid_matches = []
        for match_target, match_rule_index, match_is_priority in file_matches.get(file_path_str, []):
            if (file_path_str, match_rule_index) not in trumped_regular_matches:
                valid_matches.append((match_target, match_rule_index, match_is_priority))
                log.debug(f"    File '{Path(file_path_str).name}': Valid match - Target: '{match_target}', Rule Index: {match_rule_index}, Priority: {match_is_priority}")
            else:
                log.debug(f"    File '{Path(file_path_str).name}': Invalid match (trumped by priority) - Target: '{match_target}', Rule Index: {match_rule_index}, Priority: {match_is_priority}")

        if "BoucleChunky001" in file_path_str:
            log.info(f"DEBUG_ROO: PASS 3 PRE-ASSIGN: File '{Path(file_path_str).name}'. Valid matches: {valid_matches}")

        if "BoucleChunky001" in file_path_str:
            log.info(f"DEBUG_ROO: PASS 3 PRE-ASSIGN: File '{Path(file_path_str).name}'. Valid matches: {valid_matches}")

        final_item_type = "FILE_IGNORE" # Default to ignore if no valid matches
        if valid_matches:
            # Apply earliest rule wins among valid matches
            best_match = min(valid_matches, key=lambda x: x[1]) # Find match with lowest rule_index
            final_item_type = best_match[0] # Assign the target_type of the best match
            log.debug(f"  File '{Path(file_path_str).name}': Best valid match -> Target: '{best_match[0]}', Rule Index: {best_match[1]}. Final type: '{final_item_type}'.")
        else:
             log.debug(f"  File '{Path(file_path_str).name}'': No valid matches after filtering. Final type: '{final_item_type}'.")

        if "BoucleChunky001" in file_path_str:
            log.info(f"DEBUG_ROO: PASS 3 FINAL ASSIGN: File '{Path(file_path_str).name}' -> Final Type: '{final_item_type}'")
        final_file_assignments[file_path_str] = final_item_type

        if "BoucleChunky001" in file_path_str:
            log.info(f"DEBUG_ROO: PASS 3 FINAL ASSIGN: File '{Path(file_path_str).name}' -> Final Type: '{final_item_type}'")

        # Add the file info to the classified_files_info structure
        log.info(f"DEBUG_ROO: PASS 3 APPEND: Appending file '{Path(file_path_str).name}' with type '{final_item_type}' to classified_files_info['{asset_name}']")
        classified_files_info[asset_name].append({
            'file_path': file_path_str,
            'item_type': final_item_type,
            'asset_name': asset_name
        })
        log.debug(f"  Final Grouping: '{Path(file_path_str).name}' -> '{final_item_type}' (Asset: '{asset_name}')")


    log.debug(f"Classification complete. Found {len(classified_files_info)} potential assets.")
    # Enhanced logging for the content of classified_files_info
    boucle_chunky_data = {
        key: val for key, val in classified_files_info.items()
        if 'BoucleChunky001' in key or any('BoucleChunky001' in (f_info.get('file_path','')) for f_info in val)
    }
    import json # Make sure json is imported if not already at top of file
    log.info(f"DEBUG_ROO: Final classified_files_info for BoucleChunky001 (content): \n{json.dumps(boucle_chunky_data, indent=2)}")
    return dict(classified_files_info)


class RuleBasedPredictionHandler(BasePredictionHandler):
    """
    Handles running rule-based predictions in a separate thread using presets.
    Generates the initial SourceRule hierarchy based on file lists and presets.
    Inherits from BasePredictionHandler for common threading and signaling.
    """

    def __init__(self, input_source_identifier: str, original_input_paths: list[str], preset_name: str, parent: QObject = None):
        """
        Initializes the rule-based handler.

        Args:
            input_source_identifier: The unique identifier for the input source (e.g., file path).
            original_input_paths: List of absolute file paths extracted from the source.
            preset_name: The name of the preset configuration to use.
            parent: The parent QObject.
        """
        super().__init__(input_source_identifier, parent)
        self.original_input_paths = original_input_paths
        self.preset_name = preset_name
        self._current_input_path = None
        self._current_file_list = None
        self._current_preset_name = None

    # Re-introduce run_prediction as the main slot to receive requests
    @Slot(str, list, str)
    def run_prediction(self, input_source_identifier: str, original_input_paths: list[str], preset_name: str):
        """
        Generates the initial SourceRule hierarchy for a given source identifier,
        file list, and preset name. Populates only overridable fields based on
        classification and preset defaults.
        This method is intended to be run in the handler's QThread.
        Uses the base class signals for reporting results/errors.
        """
        # Check if already running a prediction for a *different* source
        # Allow re-triggering for the *same* source if needed (e.g., preset changed)
        if self._is_running and self._current_input_path != input_source_identifier:
            log.warning(f"RuleBasedPredictionHandler is busy with '{self._current_input_path}'. Ignoring request for '{input_source_identifier}'.")
            return

        self._is_running = True
        self._is_cancelled = False
        self._current_input_path = input_source_identifier
        self._current_file_list = original_input_paths
        self._current_preset_name = preset_name

        log.info(f"Starting rule-based prediction for: {input_source_identifier} using preset: {preset_name}")
        self.status_update.emit(f"Starting analysis for '{Path(input_source_identifier).name}'...")

        source_rules_list = []
        try:
            if not BACKEND_AVAILABLE:
                raise RuntimeError("Backend/config modules not available. Cannot run prediction.")

            if not preset_name:
                log.warning("No preset selected for prediction.")
                self.status_update.emit("No preset selected.")
                self.prediction_ready.emit(input_source_identifier, [])
                self._is_running = False
                return

            source_path = Path(input_source_identifier)
            if not source_path.exists():
                 log.warning(f"Input source path does not exist: '{input_source_identifier}'. Skipping prediction.")
                 raise FileNotFoundError(f"Input source path not found: {input_source_identifier}")

            # --- Load Configuration ---
            config = Configuration(preset_name)
            log.info(f"Successfully loaded configuration for preset '{preset_name}'.")

            if self._is_cancelled: raise RuntimeError("Prediction cancelled before classification.")

            # --- Perform Classification ---
            self.status_update.emit(f"Classifying files for '{source_path.name}'...")
            try:
                 classified_assets = classify_files(original_input_paths, config)
            except Exception as e:
                 log.exception(f"Error during file classification for source '{input_source_identifier}': {e}")
                 raise RuntimeError(f"Error classifying files: {e}") from e

            if self._is_cancelled: raise RuntimeError("Prediction cancelled after classification.")

            if not classified_assets:
                 log.warning(f"Classification yielded no assets for source '{input_source_identifier}'.")
                 self.status_update.emit("No assets identified from files.")
                 self.prediction_ready.emit(input_source_identifier, [])
                 self._is_running = False
                 return

            # --- Build the Hierarchy ---
            self.status_update.emit(f"Building rule hierarchy for '{source_path.name}'...")
            try:
                supplier_identifier = config.supplier_name
                source_rule = SourceRule(
                    input_path=input_source_identifier,
                    supplier_identifier=supplier_identifier,
                    # Use the internal display name from the config object
                    preset_name=config.internal_display_preset_name
                )
                asset_rules = []
                file_type_definitions = config._core_settings.get('FILE_TYPE_DEFINITIONS', {})

                for asset_name, files_info in classified_assets.items():
                    if self._is_cancelled: raise RuntimeError("Prediction cancelled during hierarchy building (assets).")
                    if not files_info: continue

                    asset_category_rules = config.asset_category_rules
                    asset_type_definitions = config.get_asset_type_definitions()
                    asset_type_keys = list(asset_type_definitions.keys())

                    # Initialize predicted_asset_type using the validated default
                    predicted_asset_type = config.default_asset_category
                    log.debug(f"Asset '{asset_name}': Initial predicted_asset_type set to default: '{predicted_asset_type}'.")

                    # 1. Check asset_category_rules from preset
                    determined_by_rule = False

                    # Check for Model type based on file patterns
                    if "Model" in asset_type_keys:
                        model_patterns_regex = config.compiled_model_regex
                        for f_info in files_info:
                            if f_info['item_type'] in ["EXTRA", "FILE_IGNORE"]:
                                continue
                            file_path_obj = Path(f_info['file_path'])
                            for pattern_re in model_patterns_regex:
                                if pattern_re.search(file_path_obj.name):
                                    predicted_asset_type = "Model"
                                    determined_by_rule = True
                                    log.debug(f"Asset '{asset_name}' classified as 'Model' due to file '{file_path_obj.name}' matching pattern '{pattern_re.pattern}'.")
                                    break
                            if determined_by_rule:
                                break

                    # Check for Decal type based on keywords in asset name (if not already Model)
                    if not determined_by_rule and "Decal" in asset_type_keys:
                        decal_keywords = asset_category_rules.get('decal_keywords', [])
                        for keyword in decal_keywords:
                            # Ensure keyword is a string before trying to escape it
                            if isinstance(keyword, str) and keyword:
                                try:
                                    if re.search(r'\b' + re.escape(keyword) + r'\b', asset_name, re.IGNORECASE):
                                        predicted_asset_type = "Decal"
                                        determined_by_rule = True
                                        log.debug(f"Asset '{asset_name}' classified as 'Decal' due to keyword '{keyword}'.")
                                        break
                                except re.error as e_re:
                                    log.warning(f"Regex error with decal_keyword '{keyword}': {e_re}")
                        if determined_by_rule:
                             pass

                    # 2. If not determined by specific rules, check for Surface (if not Model/Decal by rule)
                    if not determined_by_rule and predicted_asset_type == config.default_asset_category and "Surface" in asset_type_keys:
                        item_types_in_asset = {f_info['item_type'] for f_info in files_info}
                        # Ensure we are checking against standard map types from FILE_TYPE_DEFINITIONS
                        # This check is primarily for PBR texture sets.
                        material_indicators = {
                            ft_key for ft_key, ft_def in config.get_file_type_definitions_with_examples().items()
                            if ft_def.get('standard_type') and ft_def.get('standard_type') not in ["", "EXTRA", "FILE_IGNORE", "MODEL"]
                        }
                        # Add common direct standard types as well for robustness
                        material_indicators.update({"COL", "NRM", "ROUGH", "METAL", "AO", "DISP"})


                        has_material_map = False
                        for item_type in item_types_in_asset:
                            # Check if the item_type itself is a material indicator or its standard_type is
                            if item_type in material_indicators:
                                has_material_map = True
                                break
                            # Check standard type if item_type is a key in FILE_TYPE_DEFINITIONS
                            item_def = config.get_file_type_definitions_with_examples().get(item_type)
                            if item_def and item_def.get('standard_type') in material_indicators:
                                has_material_map = True
                                break

                        if has_material_map:
                            predicted_asset_type = "Surface"
                            log.debug(f"Asset '{asset_name}' classified as 'Surface' due to material indicators.")

                    # 3. Final validation: Ensure predicted_asset_type is a valid key.
                    if predicted_asset_type not in asset_type_keys:
                        log.warning(f"Derived AssetType '{predicted_asset_type}' for asset '{asset_name}' is not in ASSET_TYPE_DEFINITIONS. "
                                    f"Falling back to default: '{config.default_asset_category}'.")
                        predicted_asset_type = config.default_asset_category

                    asset_rule = AssetRule(asset_name=asset_name, asset_type=predicted_asset_type)
                    file_rules = []
                    for file_info in files_info:
                        if self._is_cancelled: raise RuntimeError("Prediction cancelled during hierarchy building (files).")

                        base_item_type = file_info['item_type']
                        target_asset_name_override = file_info['asset_name']
                        final_item_type = base_item_type
                        # The classification logic now returns the final item_type directly,
                        # including "FILE_IGNORE" and correctly prioritized MAP_ types.
                        # No need for the old MAP_ prefixing logic here.

                        # Validate the final_item_type against definitions, unless it's EXTRA or FILE_IGNORE
                        if final_item_type not in ["EXTRA", "FILE_IGNORE"] and file_type_definitions and final_item_type not in file_type_definitions:
                             log.warning(f"Predicted ItemType '{final_item_type}' for file '{file_info['file_path']}' is not in FILE_TYPE_DEFINITIONS. Setting to FILE_IGNORE.")
                             final_item_type = "FILE_IGNORE"


                        file_rule = FileRule(
                            file_path=file_info['file_path'],
                            item_type=final_item_type,
                            item_type_override=final_item_type, # item_type_override defaults to item_type
                            target_asset_name_override=target_asset_name_override,
                            output_format_override=None,
                            resolution_override=None,
                            channel_merge_instructions={},
                        )
                        file_rules.append(file_rule)
                    asset_rule.files = file_rules
                    asset_rules.append(asset_rule)
                source_rule.assets = asset_rules
                source_rules_list.append(source_rule)

                # DEBUG: Log the structure of the source_rule being emitted
                if source_rule and source_rule.assets:
                    for asset_r_idx, asset_r in enumerate(source_rule.assets):
                        log.info(f"DEBUG_ROO_EMIT: Source '{input_source_identifier}', Asset {asset_r_idx} ('{asset_r.asset_name}') has {len(asset_r.files)} FileRules.")
                        for fr_idx, fr in enumerate(asset_r.files):
                            log.info(f"DEBUG_ROO_EMIT:   FR {fr_idx}: Path='{fr.file_path}', Type='{fr.item_type}', TargetAsset='{fr.target_asset_name_override}'")
                elif source_rule:
                    log.info(f"DEBUG_ROO_EMIT: Emitting SourceRule for {input_source_identifier} but it has no assets.")
                else:
                    log.info(f"DEBUG_ROO_EMIT: Attempting to emit for {input_source_identifier}, but source_rule object is None.")
                # END DEBUG

            except Exception as e:
                 log.exception(f"Error building rule hierarchy for source '{input_source_identifier}': {e}")
                 raise RuntimeError(f"Error building rule hierarchy: {e}") from e

            # --- Emit Success Signal ---
            log.info(f"Rule-based prediction finished successfully for '{input_source_identifier}'.")
            self.prediction_ready.emit(input_source_identifier, source_rules_list)

        except Exception as e:
            # --- Emit Error Signal ---
            log.exception(f"Error during rule-based prediction for '{input_source_identifier}': {e}")
            error_msg = f"Error analyzing '{Path(input_source_identifier).name}': {e}"
            self.prediction_error.emit(input_source_identifier, error_msg)

        finally:
            self._is_running = False
            self._current_input_path = None
            self._current_file_list = None
            self._current_preset_name = None
            log.info(f"Finished rule-based prediction run for: {input_source_identifier}")
def is_running(self) -> bool:
        """Returns True if the handler is currently processing a prediction request."""
        return self._is_running
