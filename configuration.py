import json
import os
import sys
import shutil
from pathlib import Path
import logging
import re
import collections.abc
from typing import Optional, Union

log = logging.getLogger(__name__)

# This BASE_DIR is primarily for fallback when not bundled or for locating bundled resources relative to the script.
_SCRIPT_DIR = Path(__file__).resolve().parent

class ConfigurationError(Exception):
    """Custom exception for configuration loading errors."""
    pass

def _get_user_config_path_placeholder() -> Optional[Path]:
    """
    Placeholder function. In a real scenario, this would retrieve the
    saved user configuration path (e.g., from a settings file).
    Returns None if not set, triggering first-time setup behavior.
    """
    # For this subtask, we assume this path is determined externally and passed to Configuration.
    # If we were to implement the settings.ini check here, it would look like:
    # try:
    #     app_data_dir = Path(os.getenv('APPDATA')) / "AssetProcessor"
    #     settings_ini = app_data_dir / "settings.ini"
    #     if settings_ini.exists():
    #         with open(settings_ini, 'r') as f:
    #             path_str = f.read().strip()
    #         return Path(path_str)
    # except Exception:
    #     return None
    return None


def _get_base_map_type(target_map_string: str) -> str:
   """Extracts the base map type (e.g., 'COL') from a potentially numbered string ('COL-1')."""
   # Use regex to find the leading alphabetical part
   match = re.match(r"([a-zA-Z]+)", target_map_string)
   if match:
       return match.group(1).upper()
   # Fallback if no number suffix or unexpected format
   return target_map_string.upper()

def _fnmatch_to_regex(pattern: str) -> str:
    """
    Converts an fnmatch pattern to a regex pattern string.
    Handles basic wildcards (*, ?) and escapes other regex special characters.
    """
    i, n = 0, len(pattern)
    res = ''
    while i < n:
        c = pattern[i]
        i = i + 1
        if c == '*':
            res = res + '.*'
        elif c == '?':
            res = res + '.'
        elif c == '[':
            j = i
            if j < n and pattern[j] == '!':
                j = j + 1
            if j < n and pattern[j] == ']':
                j = j + 1
            while j < n and pattern[j] != ']':
                j = j + 1
            if j >= n:
                res = res + '\\['
            else:
                stuff = pattern[i:j].replace('\\','\\\\')
                i = j + 1
                if stuff[0] == '!':
                    stuff = '^' + stuff[1:]
                elif stuff[0] == '^':
                    stuff = '\\' + stuff
                res = '%s[%s]' % (res, stuff)
        else:
            res = res + re.escape(c)
    # We want to find the pattern anywhere in the filename for flexibility,
    # so don't anchor with ^$ by default. Anchoring might be needed for specific cases.
    # Let's return the core pattern and let the caller decide on anchoring if needed.
    # For filename matching, we usually want to find the pattern, not match the whole string.
    return res

def _deep_merge_dicts(base_dict: dict, override_dict: dict) -> dict:
    """
    Recursively merges override_dict into base_dict.
    If a key exists in both and both values are dicts, it recursively merges them.
    Otherwise, the value from override_dict takes precedence.
    Modifies base_dict in place and returns it.
    """
    for key, value in override_dict.items():
        if isinstance(value, collections.abc.Mapping):
            node = base_dict.get(key) # Use .get() to avoid creating empty dicts if not needed for override
            if isinstance(node, collections.abc.Mapping):
                _deep_merge_dicts(node, value) # node is base_dict[key], modified in place
            else:
                # If base_dict[key] is not a dict or doesn't exist, override it
                base_dict[key] = value
        else:
            base_dict[key] = value
    return base_dict


class Configuration:
    """
    Loads and provides access to core settings combined with a specific preset,
    managing bundled and user-specific configuration paths.
    """
    BASE_DIR_APP_BUNDLED_CONFIG_SUBDIR_NAME = "config"
    PRESETS_DIR_APP_BUNDLED_NAME = "Presets"
    USER_SETTINGS_FILENAME = "user_settings.json"
    APP_SETTINGS_FILENAME = "app_settings.json"
    ASSET_TYPE_DEFINITIONS_FILENAME = "asset_type_definitions.json"
    FILE_TYPE_DEFINITIONS_FILENAME = "file_type_definitions.json"
    LLM_SETTINGS_FILENAME = "llm_settings.json"
    SUPPLIERS_CONFIG_FILENAME = "suppliers.json"
    USER_CONFIG_SUBDIR_NAME = "config" # Subdirectory within user's chosen config root for most jsons
    USER_PRESETS_SUBDIR_NAME = "Presets" # Subdirectory within user's chosen config root for presets

    def __init__(self, preset_name: str, base_dir_user_config: Optional[Path] = None, is_first_run_setup: bool = False):
        """
        Loads core config, user overrides, and the specified preset file.

        Args:
            preset_name: The name of the preset (without .json extension).
            base_dir_user_config: The root path for user-specific configurations.
                                  If None, loading of user-specific files will be skipped or may fail.
            is_first_run_setup: Flag indicating if this is part of the initial setup
                                process where user config dir might be empty and fallbacks
                                should not aggressively try to copy from bundle until UI confirms.
        Raises:
            ConfigurationError: If critical configurations cannot be loaded/validated.
        """
        log.debug(f"Initializing Configuration with preset: '{preset_name}', user_config_dir: '{base_dir_user_config}', first_run_flag: {is_first_run_setup}")
        self._preset_filename_stem = preset_name
        self.base_dir_user_config: Optional[Path] = base_dir_user_config
        self.is_first_run_setup = is_first_run_setup
        self.base_dir_app_bundled: Path = self._determine_base_dir_app_bundled()

        log.info(f"Determined BASE_DIR_APP_BUNDLED: {self.base_dir_app_bundled}")
        log.info(f"Using BASE_DIR_USER_CONFIG: {self.base_dir_user_config}")

        # 1. Load core application settings (always from bundled)
        app_settings_path = self.base_dir_app_bundled / self.BASE_DIR_APP_BUNDLED_CONFIG_SUBDIR_NAME / self.APP_SETTINGS_FILENAME
        self._core_settings: dict = self._load_json_file(
            app_settings_path,
            is_critical=True,
            description="Core application settings"
        )

        # 2. Load user settings (from user config dir, if provided)
        user_settings_overrides: dict = {}
        if self.base_dir_user_config:
            user_settings_file_path = self.base_dir_user_config / self.USER_SETTINGS_FILENAME
            user_settings_overrides = self._load_json_file(
                user_settings_file_path,
                is_critical=False, # Not critical if missing, especially on first run
                description=f"User settings from {user_settings_file_path}"
            ) or {} # Ensure it's a dict
        else:
            log.info(f"{self.USER_SETTINGS_FILENAME} not loaded: User config directory not set.")

        # 3. Deep merge user settings onto core settings
        if user_settings_overrides:
            log.info(f"Applying user setting overrides to core settings.")
            _deep_merge_dicts(self._core_settings, user_settings_overrides)
        
        # 4. Load other definition files (from user config dir, with fallback from bundled)
        self._asset_type_definitions: dict = self._load_definition_file_with_fallback(
            self.ASSET_TYPE_DEFINITIONS_FILENAME, "ASSET_TYPE_DEFINITIONS"
        )
        self._file_type_definitions: dict = self._load_definition_file_with_fallback(
            self.FILE_TYPE_DEFINITIONS_FILENAME, "FILE_TYPE_DEFINITIONS"
        )
        self._llm_settings: dict = self._load_definition_file_with_fallback(
            self.LLM_SETTINGS_FILENAME, None # LLM settings might be flat (no root key)
        )
        self._suppliers_config: dict = self._load_definition_file_with_fallback(
            self.SUPPLIERS_CONFIG_FILENAME, None # Suppliers config is flat
        )

        # 5. Load preset settings (from user config dir, with fallback from bundled)
        self._preset_settings: dict = self._load_preset_with_fallback(self._preset_filename_stem)
        
        self.actual_internal_preset_name = self._preset_settings.get("preset_name", self._preset_filename_stem)
        log.info(f"Configuration instance: Loaded preset file '{self._preset_filename_stem}.json', internal preset_name is '{self.actual_internal_preset_name}'")

        # 6. Validate and compile (after all base/user/preset settings are established)
        self._validate_configs()
        self._compile_regex_patterns()
        log.info(f"Configuration loaded successfully using preset: '{self.actual_internal_preset_name}'")

    def _determine_base_dir_app_bundled(self) -> Path:
        """Determines the base directory for bundled application resources."""
        if getattr(sys, 'frozen', False) and hasattr(sys, '_MEIPASS'):
            # Running in a PyInstaller bundle
            log.debug(f"Running as bundled app, _MEIPASS: {sys._MEIPASS}")
            return Path(sys._MEIPASS)
        else:
            # Running as a script
            log.debug(f"Running as script, using _SCRIPT_DIR: {_SCRIPT_DIR}")
            return _SCRIPT_DIR

    def _ensure_dir_exists(self, dir_path: Path):
        """Ensures a directory exists, creating it if necessary."""
        try:
            if not dir_path.exists():
                log.info(f"Directory not found, creating: {dir_path}")
                dir_path.mkdir(parents=True, exist_ok=True)
            elif not dir_path.is_dir():
                raise ConfigurationError(f"Expected directory but found file: {dir_path}")
        except OSError as e:
            raise ConfigurationError(f"Failed to create or access directory {dir_path}: {e}")

    def _copy_default_if_missing(self, user_target_path: Path, bundled_source_subdir: str, filename: str) -> bool:
        """
        Copies a default file from the bundled location to the user config directory
        if it's missing in the user directory. This is for post-first-time-setup fallback.
        """
        if not self.base_dir_user_config:
            log.error(f"Cannot copy default for '{filename}': base_dir_user_config is not set.")
            return False
        
        if user_target_path.exists():
            log.debug(f"User file '{user_target_path}' already exists. No copy needed from bundle.")
            return False

        # This fallback copy should NOT happen during the initial UI-driven setup phase
        # where the UI is responsible for the first population of the user directory.
        # It's for subsequent runs where a user might have deleted a file.
        if self.is_first_run_setup:
            log.debug(f"'{filename}' missing in user dir during first_run_setup phase. UI should handle initial copy. Skipping fallback copy.")
            return False # File is missing, but UI should handle it.

        bundled_file_path = self.base_dir_app_bundled / bundled_source_subdir / filename
        if not bundled_file_path.is_file():
            log.warning(f"Default bundled file '{bundled_file_path}' not found. Cannot copy to user location '{user_target_path}'.")
            return False

        log.warning(f"User file '{user_target_path}' is missing. Attempting to restore from bundled default: '{bundled_file_path}'.")
        try:
            self._ensure_dir_exists(user_target_path.parent)
            shutil.copy2(bundled_file_path, user_target_path)
            log.info(f"Successfully copied '{bundled_file_path}' to '{user_target_path}'.")
            return True # File was copied
        except Exception as e:
            log.error(f"Failed to copy '{bundled_file_path}' to '{user_target_path}': {e}")
            return False # Copy failed

    def _load_json_file(self, file_path: Optional[Path], is_critical: bool = False, description: str = "configuration") -> dict:
        """Loads a JSON file, handling errors. Returns empty dict if not found and not critical."""
        if not file_path:
            if is_critical:
                raise ConfigurationError(f"Critical {description} file path is not defined.")
            log.debug(f"{description} file path is not defined. Returning empty dict.")
            return {}

        log.debug(f"Attempting to load {description} from: {file_path}")
        if not file_path.is_file():
            if is_critical:
                raise ConfigurationError(f"Critical {description} file not found: {file_path}")
            log.info(f"{description} file not found: {file_path}. Returning empty dict.")
            return {}
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                settings = json.load(f)
            log.debug(f"{description} loaded successfully from {file_path}.")
            return settings
        except json.JSONDecodeError as e:
            msg = f"Failed to parse {description} file {file_path}: Invalid JSON - {e}"
            if is_critical: raise ConfigurationError(msg)
            log.warning(msg + ". Returning empty dict.")
            return {}
        except Exception as e:
            msg = f"Failed to read {description} file {file_path}: {e}"
            if is_critical: raise ConfigurationError(msg)
            log.warning(msg + ". Returning empty dict.")
            return {}

    def _load_definition_file_with_fallback(self, filename: str, root_key: Optional[str] = None) -> dict:
        """
        Loads a definition JSON file from the user config subdir.
        If not found and not first_run_setup, attempts to copy from bundled config subdir and then loads it.
        If base_dir_user_config is not set, loads directly from bundled (read-only).
        """
        data = {}
        user_file_path = None

        if self.base_dir_user_config:
            user_file_path = self.base_dir_user_config / self.USER_CONFIG_SUBDIR_NAME / filename
            data = self._load_json_file(user_file_path, is_critical=False, description=f"User {filename}")

            if not data: # If not found or failed to load from user path
                # Attempt fallback copy only if not in the initial setup phase by UI
                # and if the file was genuinely missing (not a parse error for an existing file)
                if not user_file_path.exists() and not self.is_first_run_setup:
                    if self._copy_default_if_missing(user_file_path, self.BASE_DIR_APP_BUNDLED_CONFIG_SUBDIR_NAME, filename):
                        data = self._load_json_file(user_file_path, is_critical=False, description=f"User {filename} after copy")
        else:
            # No user_config_dir, load directly from bundled (read-only)
            log.warning(f"User config directory not set. Loading '{filename}' from bundled defaults (read-only).")
            bundled_path = self.base_dir_app_bundled / self.BASE_DIR_APP_BUNDLED_CONFIG_SUBDIR_NAME / filename
            data = self._load_json_file(bundled_path, is_critical=False, description=f"Bundled {filename}")

        if not data:
            # If still no data, it's an issue, especially for critical definitions
            is_critical_def = filename in [self.ASSET_TYPE_DEFINITIONS_FILENAME, self.FILE_TYPE_DEFINITIONS_FILENAME]
            err_msg = f"Failed to load '{filename}' from user dir '{user_file_path if user_file_path else 'N/A'}' or bundled defaults. Critical functionality may be affected."
            if is_critical_def: raise ConfigurationError(err_msg)
            log.error(err_msg)
            return {}

        if root_key:
            if root_key not in data:
                raise ConfigurationError(f"Key '{root_key}' not found in loaded {filename} data: {data.keys()}")
            content = data[root_key]
            # Ensure content is a dictionary if a root_key is expected to yield one
            if not isinstance(content, dict):
                raise ConfigurationError(f"Content under root key '{root_key}' in {filename} must be a dictionary, got {type(content)}.")
            return content
        return data # For flat files

    def _load_preset_with_fallback(self, preset_name_stem: str) -> dict:
        """
        Loads a preset JSON file from the user's Presets subdir.
        If not found and not first_run_setup, attempts to copy from bundled Presets and then loads it.
        If base_dir_user_config is not set, loads directly from bundled (read-only).
        """
        preset_filename = f"{preset_name_stem}.json"
        preset_data = {}
        user_preset_file_path = None

        if self.base_dir_user_config:
            user_presets_dir = self.base_dir_user_config / self.USER_PRESETS_SUBDIR_NAME
            user_preset_file_path = user_presets_dir / preset_filename
            preset_data = self._load_json_file(user_preset_file_path, is_critical=False, description=f"User preset '{preset_filename}'")

            if not preset_data: # If not found or failed to load
                if not user_preset_file_path.exists() and not self.is_first_run_setup:
                    if self._copy_default_if_missing(user_preset_file_path, self.PRESETS_DIR_APP_BUNDLED_NAME, preset_filename):
                        preset_data = self._load_json_file(user_preset_file_path, is_critical=False, description=f"User preset '{preset_filename}' after copy")
        else:
            log.warning(f"User config directory not set. Loading preset '{preset_filename}' from bundled defaults (read-only).")
            bundled_presets_dir = self.base_dir_app_bundled / self.PRESETS_DIR_APP_BUNDLED_NAME
            bundled_preset_file_path = bundled_presets_dir / preset_filename
            # Presets are generally critical for operation if one is specified
            preset_data = self._load_json_file(bundled_preset_file_path, is_critical=True, description=f"Bundled preset '{preset_filename}'")

        if not preset_data:
            raise ConfigurationError(f"Preset file '{preset_filename}' could not be loaded from user dir '{user_preset_file_path if user_preset_file_path else 'N/A'}' or bundled defaults.")
        return preset_data


    def _compile_regex_patterns(self):
        """Compiles regex patterns from config/preset for faster matching."""
        log.debug("Compiling regex patterns from configuration...")
        self.compiled_extra_regex: list[re.Pattern] = []
        self.compiled_model_regex: list[re.Pattern] = []
        self.compiled_bit_depth_regex_map: dict[str, re.Pattern] = {}
        # Map: base_map_type -> list of tuples: (compiled_regex, original_keyword, rule_index, is_priority)
        self.compiled_map_keyword_regex: dict[str, list[tuple[re.Pattern, str, int, bool]]] = {}

        for pattern in self.move_to_extra_patterns:
            try:
                regex_str = _fnmatch_to_regex(pattern)
                self.compiled_extra_regex.append(re.compile(regex_str, re.IGNORECASE))
            except re.error as e:
                log.warning(f"Failed to compile 'extra' regex pattern '{pattern}': {e}. Skipping pattern.")

        model_patterns = self.asset_category_rules.get('model_patterns', [])
        for pattern in model_patterns:
             try:
                 regex_str = _fnmatch_to_regex(pattern)
                 self.compiled_model_regex.append(re.compile(regex_str, re.IGNORECASE))
             except re.error as e:
                 log.warning(f"Failed to compile 'model' regex pattern '{pattern}': {e}. Skipping pattern.")

        for map_type, pattern in self.source_bit_depth_variants.items():
            try:
                regex_str = _fnmatch_to_regex(pattern)
                if pattern.endswith('*'):
                    regex_str = regex_str.removesuffix('.*')

                final_regex_str = regex_str
                self.compiled_bit_depth_regex_map[map_type] = re.compile(final_regex_str, re.IGNORECASE)
                log.debug(f"  Compiled bit depth variant for '{map_type}' as regex (IGNORECASE): {final_regex_str}")
            except re.error as e:
                log.warning(f"Failed to compile 'bit depth' regex pattern '{pattern}' for map type '{map_type}': {e}. Skipping pattern.")

        separator = re.escape(self.source_naming_separator)
        from collections import defaultdict
        temp_compiled_map_regex = defaultdict(list)

        for rule_index, mapping_rule in enumerate(self.map_type_mapping):
            if not isinstance(mapping_rule, dict) or \
               'target_type' not in mapping_rule: # Removed 'keywords' check here as it's handled below
                log.warning(f"Skipping invalid map_type_mapping rule at index {rule_index}: {mapping_rule}. Expected dict with 'target_type'.")
                continue

            target_type = mapping_rule['target_type'].upper()
            
            # Ensure 'keywords' exists and is a list, default to empty list if not found or not a list
            regular_keywords = mapping_rule.get('keywords', [])
            if not isinstance(regular_keywords, list):
                log.warning(f"Rule {rule_index} for target '{target_type}' has 'keywords' but it's not a list. Treating as empty.")
                regular_keywords = []
            
            priority_keywords = mapping_rule.get('priority_keywords', []) # Optional, defaults to empty list
            if not isinstance(priority_keywords, list):
                log.warning(f"Rule {rule_index} for target '{target_type}' has 'priority_keywords' but it's not a list. Treating as empty.")
                priority_keywords = []

            # Process regular keywords
            for keyword in regular_keywords:
                if not isinstance(keyword, str):
                    log.warning(f"Skipping non-string regular keyword '{keyword}' in rule {rule_index} for target '{target_type}'.")
                    continue
                try:
                    kw_regex_part = _fnmatch_to_regex(keyword)
                    # Ensure the keyword is treated as a whole word or is at the start/end of a segment
                    regex_str = rf"(?:^|{separator})({kw_regex_part})(?:$|{separator})"
                    compiled_regex = re.compile(regex_str, re.IGNORECASE)
                    # Add False for is_priority
                    temp_compiled_map_regex[target_type].append((compiled_regex, keyword, rule_index, False)) 
                    log.debug(f"  Compiled regular keyword '{keyword}' (rule {rule_index}) for target '{target_type}' as regex: {regex_str}")
                except re.error as e:
                    log.warning(f"Failed to compile regular map keyword regex '{keyword}' for target type '{target_type}': {e}. Skipping keyword.")

            # Process priority keywords
            for keyword in priority_keywords:
                if not isinstance(keyword, str):
                    log.warning(f"Skipping non-string priority keyword '{keyword}' in rule {rule_index} for target '{target_type}'.")
                    continue
                try:
                    kw_regex_part = _fnmatch_to_regex(keyword)
                    regex_str = rf"(?:^|{separator})({kw_regex_part})(?:$|{separator})"
                    compiled_regex = re.compile(regex_str, re.IGNORECASE)
                    # Add True for is_priority
                    temp_compiled_map_regex[target_type].append((compiled_regex, keyword, rule_index, True)) 
                    log.debug(f"  Compiled priority keyword '{keyword}' (rule {rule_index}) for target '{target_type}' as regex: {regex_str}")
                except re.error as e:
                    log.warning(f"Failed to compile priority map keyword regex '{keyword}' for target type '{target_type}': {e}. Skipping keyword.")

        self.compiled_map_keyword_regex = dict(temp_compiled_map_regex)
        log.debug(f"Compiled map keyword regex keys: {list(self.compiled_map_keyword_regex.keys())}")

        log.debug("Finished compiling regex patterns.")



    def _validate_configs(self):
        """Performs basic validation checks on loaded settings."""
        log.debug("Validating loaded configurations...")

        # Validate new definition files first
        if not isinstance(self._asset_type_definitions, dict):
            raise ConfigurationError("Asset type definitions were not loaded correctly or are not a dictionary.")
        if not self._asset_type_definitions: # Check if empty
             raise ConfigurationError("Asset type definitions are empty.")

        if not isinstance(self._file_type_definitions, dict):
            raise ConfigurationError("File type definitions were not loaded correctly or are not a dictionary.")
        if not self._file_type_definitions: # Check if empty
            raise ConfigurationError("File type definitions are empty.")

        # Preset validation
        required_preset_keys = [
            "preset_name", "supplier_name", "source_naming", "map_type_mapping",
            "asset_category_rules", "archetype_rules", "move_to_extra_patterns"
        ]
        for key in required_preset_keys:
            if key not in self._preset_settings:
                raise ConfigurationError(f"Preset file '{self._preset_filename_stem}.json' (internal name: '{self.actual_internal_preset_name}') is missing required key: '{key}'.")

        # Validate map_type_mapping structure (new format)
        if not isinstance(self._preset_settings['map_type_mapping'], list):
             raise ConfigurationError(f"Preset file '{self._preset_filename_stem}.json': 'map_type_mapping' must be a list.")
        for index, rule in enumerate(self._preset_settings['map_type_mapping']):
             if not isinstance(rule, dict):
                  raise ConfigurationError(f"Preset file '{self._preset_filename_stem}.json': Rule at index {index} in 'map_type_mapping' must be a dictionary.")
             if 'target_type' not in rule or not isinstance(rule['target_type'], str):
                  raise ConfigurationError(f"Preset file '{self._preset_filename_stem}.json': Rule at index {index} in 'map_type_mapping' is missing 'target_type' string.")
 
             valid_file_type_keys = self._file_type_definitions.keys()
             if rule['target_type'] not in valid_file_type_keys:
                 raise ConfigurationError(
                     f"Preset file '{self._preset_filename_stem}.json': Rule at index {index} in 'map_type_mapping' "
                     f"has an invalid 'target_type': '{rule['target_type']}'. "
                     f"Must be one of {list(valid_file_type_keys)}."
                 )

             # 'keywords' is optional if 'priority_keywords' is present and not empty,
             # but if 'keywords' IS present, it must be a list of strings.
             if 'keywords' in rule:
                 if not isinstance(rule['keywords'], list):
                     raise ConfigurationError(f"Preset file '{self._preset_filename_stem}.json': Rule at index {index} in 'map_type_mapping' has 'keywords' but it's not a list.")
                 for kw_index, keyword in enumerate(rule['keywords']):
                      if not isinstance(keyword, str):
                           raise ConfigurationError(f"Preset file '{self._preset_filename_stem}.json': Keyword at index {kw_index} in rule {index} ('{rule['target_type']}') must be a string.")
             elif not ('priority_keywords' in rule and rule['priority_keywords']): # if 'keywords' is not present, 'priority_keywords' must be
                 raise ConfigurationError(f"Preset file '{self._preset_filename_stem}.json': Rule at index {index} in 'map_type_mapping' must have 'keywords' or non-empty 'priority_keywords'.")

             # Validate priority_keywords if present
             if 'priority_keywords' in rule:
                 if not isinstance(rule['priority_keywords'], list):
                     raise ConfigurationError(f"Preset file '{self._preset_filename_stem}.json': Rule at index {index} in 'map_type_mapping' has 'priority_keywords' but it's not a list.")
                 for prio_kw_index, prio_keyword in enumerate(rule['priority_keywords']):
                     if not isinstance(prio_keyword, str):
                         raise ConfigurationError(f"Preset file '{self._preset_filename_stem}.json': Priority keyword at index {prio_kw_index} in rule {index} ('{rule['target_type']}') must be a string.")

        if not isinstance(self._core_settings.get('TARGET_FILENAME_PATTERN'), str):
             raise ConfigurationError("Core config 'TARGET_FILENAME_PATTERN' must be a string.")
        if not isinstance(self._core_settings.get('OUTPUT_DIRECTORY_PATTERN'), str):
             raise ConfigurationError("Core config 'OUTPUT_DIRECTORY_PATTERN' must be a string.")
        if not isinstance(self._core_settings.get('OUTPUT_FILENAME_PATTERN'), str):
             raise ConfigurationError("Core config 'OUTPUT_FILENAME_PATTERN' must be a string.")
        if not isinstance(self._core_settings.get('IMAGE_RESOLUTIONS'), dict):
             raise ConfigurationError("Core config 'IMAGE_RESOLUTIONS' must be a dictionary.")

        # Validate DEFAULT_ASSET_CATEGORY
        valid_asset_type_keys = self._asset_type_definitions.keys()
        default_asset_category_value = self._core_settings.get('DEFAULT_ASSET_CATEGORY')
        if not default_asset_category_value:
            raise ConfigurationError("Core config 'DEFAULT_ASSET_CATEGORY' is missing.")
        if default_asset_category_value not in valid_asset_type_keys:
            raise ConfigurationError(
                f"Core config 'DEFAULT_ASSET_CATEGORY' ('{default_asset_category_value}') "
                f"is not a valid key in ASSET_TYPE_DEFINITIONS. "
                f"Must be one of {list(valid_asset_type_keys)}."
            )
 
        if self._llm_settings:
           required_llm_keys = [
               "llm_predictor_examples", "llm_endpoint_url", "llm_api_key",
               "llm_model_name", "llm_temperature", "llm_request_timeout",
               "llm_predictor_prompt"
           ]
           for key in required_llm_keys:
               if key not in self._llm_settings:
                   # Log warning instead of raising error to allow partial functionality
                   log.warning(f"LLM config is missing recommended key: '{key}'. LLM features might not work correctly.")
        log.debug("Configuration validation passed.")


    @property
    def supplier_name(self) -> str: # From preset
        return self._preset_settings.get('supplier_name', 'DefaultSupplier')

    @property
    def suppliers_config(self) -> dict: # From suppliers.json
        """Returns the loaded suppliers configuration."""
        return self._suppliers_config

    @property
    def internal_display_preset_name(self) -> str:
        """Returns the 'preset_name' field from within the loaded preset JSON,
           or falls back to the filename stem if not present."""
        return self.actual_internal_preset_name

    @property
    def default_asset_category(self) -> str:
        """Gets the default asset category from core settings."""
        # Fallback should align with a valid key, and validation should catch issues.
        return self._core_settings.get('DEFAULT_ASSET_CATEGORY', 'Surface')

    @property
    def target_filename_pattern(self) -> str:
        return self._core_settings['TARGET_FILENAME_PATTERN']

    @property
    def output_directory_pattern(self) -> str:
        """Gets the output directory pattern ONLY from core settings."""
        # Default pattern if missing in core settings (should be caught by validation)
        default_pattern = "[supplier]/[assetname]"
        return self._core_settings.get('OUTPUT_DIRECTORY_PATTERN', default_pattern)

    @property
    def output_filename_pattern(self) -> str:
        """Gets the output filename pattern ONLY from core settings."""
        # Default pattern if missing in core settings (should be caught by validation)
        default_pattern = "[assetname]_[maptype]_[resolution].[ext]"
        return self._core_settings.get('OUTPUT_FILENAME_PATTERN', default_pattern)

    @property
    def image_resolutions(self) -> dict[str, int]:
        return self._core_settings['IMAGE_RESOLUTIONS']


    @property
    def map_type_mapping(self) -> list:
        return self._preset_settings['map_type_mapping']

    @property
    def source_naming_separator(self) -> str:
        return self._preset_settings.get('source_naming', {}).get('separator', '_')

    @property
    def source_naming_indices(self) -> dict:
        return self._preset_settings.get('source_naming', {}).get('part_indices', {})

    @property
    def source_glossiness_keywords(self) -> list:
        return self._preset_settings.get('source_naming', {}).get('glossiness_keywords', [])

    @property
    def source_bit_depth_variants(self) -> dict:
         return self._preset_settings.get('source_naming', {}).get('bit_depth_variants', {})

    @property
    def archetype_rules(self) -> list:
         return self._preset_settings['archetype_rules']

    @property
    def asset_category_rules(self) -> dict:
         return self._preset_settings['asset_category_rules']

    @property
    def move_to_extra_patterns(self) -> list:
        return self._preset_settings['move_to_extra_patterns']

    @property
    def extra_files_subdir(self) -> str:
        return self._core_settings['EXTRA_FILES_SUBDIR']

    @property
    def metadata_filename(self) -> str:
        return self._core_settings['METADATA_FILENAME']

    @property
    def calculate_stats_resolution(self) -> str:
        return self._core_settings['CALCULATE_STATS_RESOLUTION']

    @property
    def map_merge_rules(self) -> list:
         return self._core_settings['MAP_MERGE_RULES']

    @property
    def aspect_ratio_decimals(self) -> int:
         return self._core_settings['ASPECT_RATIO_DECIMALS']

    @property
    def temp_dir_prefix(self) -> str:
         return self._core_settings['TEMP_DIR_PREFIX']

    @property
    def jpg_quality(self) -> int:
        """Gets the configured JPG quality level."""
        return self._core_settings.get('JPG_QUALITY', 95)

    @property
    def invert_normal_green_globally(self) -> bool:
        """Gets the global setting for inverting the green channel of normal maps."""
        # Default to False if the setting is missing in the core config
        return self._core_settings.get('invert_normal_map_green_channel_globally', False)

    @property
    def overwrite_existing(self) -> bool:
        """Gets the setting for overwriting existing files from core settings."""
        return self._core_settings.get('overwrite_existing', False)

    @property
    def png_compression_level(self) -> int:
        """Gets the PNG compression level from core settings."""
        return self._core_settings.get('PNG_COMPRESSION', 6) # Default to 6 if not found

    @property
    def resolution_threshold_for_jpg(self) -> int:
        """Gets the pixel dimension threshold for using JPG for 8-bit images."""
        value = self._core_settings.get('RESOLUTION_THRESHOLD_FOR_JPG', 4096)
        log.info(f"CONFIGURATION_DEBUG: resolution_threshold_for_jpg property returning: {value} (type: {type(value)})")
        # Ensure it's an int, as downstream might expect it.
        # The .get() default is an int, but if the JSON had null or a string, it might be different.
        if not isinstance(value, int):
            log.warning(f"CONFIGURATION_DEBUG: RESOLUTION_THRESHOLD_FOR_JPG was not an int, got {type(value)}. Defaulting to 4096.")
            return 4096
        return value

    @property
    def respect_variant_map_types(self) -> list:
        """Gets the list of map types that should always respect variant numbering."""
        # Ensure it returns a list, even if missing from config.py (though defaults should handle it)
        return self._core_settings.get('RESPECT_VARIANT_MAP_TYPES', [])

    @property
    def force_lossless_map_types(self) -> list:
        """Gets the list of map types that must always be saved losslessly."""
        return self._core_settings.get('FORCE_LOSSLESS_MAP_TYPES', [])

    def get_bit_depth_rule(self, map_type_input: str) -> str:
        """
        Gets the bit depth rule ('respect', 'force_8bit', 'force_16bit') for a given map type identifier.
        The map_type_input can be an FTD key (e.g., "MAP_COL") or a suffixed FTD key (e.g., "MAP_COL-1").
        """
        if not self._file_type_definitions: # Check if the attribute exists and is not empty
            log.warning("File type definitions not loaded. Cannot determine bit depth rule.")
            return "respect"

        file_type_definitions = self._file_type_definitions
        
        # 1. Try direct match with map_type_input as FTD key
        definition = file_type_definitions.get(map_type_input)
        if definition:
            rule = definition.get('bit_depth_rule')
            if rule in ['respect', 'force_8bit', 'force_16bit']:
                return rule
            else:
                log.warning(f"FTD key '{map_type_input}' found, but 'bit_depth_rule' is missing or invalid: '{rule}'. Defaulting to 'respect'.")
                return "respect"

        # 2. Try to derive base FTD key by stripping common variant suffixes
        #    Regex to remove trailing suffixes like -<digits>, -<alphanum>, _<alphanum>
        base_ftd_key_candidate = re.sub(r"(-[\w\d]+|_[\w\d]+)$", "", map_type_input)
        if base_ftd_key_candidate != map_type_input:
            definition = file_type_definitions.get(base_ftd_key_candidate)
            if definition:
                rule = definition.get('bit_depth_rule')
                if rule in ['respect', 'force_8bit', 'force_16bit']:
                    log.debug(f"Derived base FTD key '{base_ftd_key_candidate}' from '{map_type_input}' and found bit depth rule: {rule}")
                    return rule
                else:
                    log.warning(f"Derived base FTD key '{base_ftd_key_candidate}' from '{map_type_input}', but 'bit_depth_rule' is missing/invalid: '{rule}'. Defaulting to 'respect'.")
                    return "respect"
        
        # If no match found after trying direct and derived keys
        log.warning(f"Map type identifier '{map_type_input}' (or its derived base) not found in FILE_TYPE_DEFINITIONS. Defaulting bit depth rule to 'respect'.")
        return "respect"

    def get_16bit_output_formats(self) -> tuple[str, str]:
        """Gets the primary and fallback format names for 16-bit output."""
        primary = self._core_settings.get('OUTPUT_FORMAT_16BIT_PRIMARY', 'png')
        fallback = self._core_settings.get('OUTPUT_FORMAT_16BIT_FALLBACK', 'png')
        return primary.lower(), fallback.lower()

    def get_8bit_output_format(self) -> str:
        """Gets the format name for 8-bit output."""
        return self._core_settings.get('OUTPUT_FORMAT_8BIT', 'png').lower()

    def get_standard_map_type_aliases(self) -> list[str]:
        """
        Derives a sorted list of unique standard map type aliases
        from FILE_TYPE_DEFINITIONS.
        """
        aliases = set()
        # _file_type_definitions is guaranteed to be a dict by the loader
        for _key, definition in self._file_type_definitions.items():
            if isinstance(definition, dict):
                standard_type = definition.get('standard_type')
                if standard_type and isinstance(standard_type, str) and standard_type.strip():
                    aliases.add(standard_type)
        return sorted(list(aliases))
 
    def get_asset_type_definitions(self) -> dict:
        """Returns the _asset_type_definitions dictionary."""
        return self._asset_type_definitions

    def get_asset_type_keys(self) -> list:
        """Returns a list of valid asset type keys from core settings."""
        return list(self.get_asset_type_definitions().keys())

    def get_file_type_definitions_with_examples(self) -> dict:
        """Returns the _file_type_definitions dictionary (including descriptions and examples)."""
        return self._file_type_definitions

    def get_file_type_keys(self) -> list:
        """Returns a list of valid file type keys from core settings."""
        return list(self.get_file_type_definitions_with_examples().keys())

    def get_llm_examples(self) -> list:
        """Returns the list of LLM input/output examples from LLM settings."""
        # Use empty list as fallback if LLM settings file is missing/invalid
        return self._llm_settings.get('llm_predictor_examples', [])

    @property
    def llm_predictor_prompt(self) -> str:
        """Returns the LLM predictor prompt string from LLM settings."""
        return self._llm_settings.get('llm_predictor_prompt', '')

    @property
    def llm_endpoint_url(self) -> str:
        """Returns the LLM endpoint URL from LLM settings."""
        return self._llm_settings.get('llm_endpoint_url', '')

    @property
    def llm_api_key(self) -> str:
        """Returns the LLM API key from LLM settings."""
        return self._llm_settings.get('llm_api_key', '')

    @property
    def llm_model_name(self) -> str:
        """Returns the LLM model name from LLM settings."""
        return self._llm_settings.get('llm_model_name', '')

    @property
    def llm_temperature(self) -> float:
        """Returns the LLM temperature from LLM settings."""
        return self._llm_settings.get('llm_temperature', 0.5)

    @property
    def llm_request_timeout(self) -> int:
        """Returns the LLM request timeout in seconds from LLM settings."""
        return self._llm_settings.get('llm_request_timeout', 120)

    @property
    def app_version(self) -> Optional[str]:
        """Returns the application version from general_settings."""
        gs = self._core_settings.get('general_settings')
        if isinstance(gs, dict):
            return gs.get('app_version')
        return None

    @property
    def enable_low_resolution_fallback(self) -> bool:
        """Gets the setting for enabling low-resolution fallback."""
        return self._core_settings.get('ENABLE_LOW_RESOLUTION_FALLBACK', True)

    @property
    def low_resolution_threshold(self) -> int:
        """Gets the pixel dimension threshold for low-resolution fallback."""
        return self._core_settings.get('LOW_RESOLUTION_THRESHOLD', 512)

    @property
    def FILE_TYPE_DEFINITIONS(self) -> dict: # Kept for compatibility if used directly
        return self._file_type_definitions

    # --- Save Methods ---
    def _save_json_to_user_config(self, data_to_save: dict, filename: str, subdir: Optional[str] = None, is_root_key_data: Optional[str] = None):
        """Helper to save a dictionary to a JSON file in the user config directory."""
        if not self.base_dir_user_config:
            raise ConfigurationError(f"Cannot save {filename}: User config directory (base_dir_user_config) is not set.")
        
        target_dir = self.base_dir_user_config
        if subdir:
            target_dir = target_dir / subdir
        
        self._ensure_dir_exists(target_dir)
        path = target_dir / filename

        data_for_json = {is_root_key_data: data_to_save} if is_root_key_data else data_to_save
        
        log.debug(f"Saving data to: {path}")
        try:
            with open(path, 'w', encoding='utf-8') as f:
                json.dump(data_for_json, f, indent=4)
            log.info(f"Data saved successfully to {path}")
        except Exception as e:
            log.error(f"Failed to save file {path}: {e}")
            raise ConfigurationError(f"Failed to save {filename}: {e}")

    def save_user_settings(self, settings_dict: dict):
        """Saves the provided settings dictionary to user_settings.json in the user config directory."""
        self._save_json_to_user_config(settings_dict, self.USER_SETTINGS_FILENAME)

    def save_llm_settings(self, settings_dict: dict):
        """Saves LLM settings to the user config directory's 'config' subdir."""
        self._save_json_to_user_config(settings_dict, self.LLM_SETTINGS_FILENAME, subdir=self.USER_CONFIG_SUBDIR_NAME)

    def save_asset_type_definitions(self, data: dict):
        """Saves asset type definitions to the user config directory's 'config' subdir."""
        self._save_json_to_user_config(data, self.ASSET_TYPE_DEFINITIONS_FILENAME, subdir=self.USER_CONFIG_SUBDIR_NAME, is_root_key_data="ASSET_TYPE_DEFINITIONS")

    def save_file_type_definitions(self, data: dict):
        """Saves file type definitions to the user config directory's 'config' subdir."""
        self._save_json_to_user_config(data, self.FILE_TYPE_DEFINITIONS_FILENAME, subdir=self.USER_CONFIG_SUBDIR_NAME, is_root_key_data="FILE_TYPE_DEFINITIONS")

    def save_supplier_settings(self, data: dict):
        """Saves supplier settings to the user config directory's 'config' subdir."""
        self._save_json_to_user_config(data, self.SUPPLIERS_CONFIG_FILENAME, subdir=self.USER_CONFIG_SUBDIR_NAME)

    def save_preset(self, preset_data: dict, preset_name_stem: str):
        """Saves a preset to the user config directory's 'Presets' subdir."""
        if not preset_name_stem:
            raise ConfigurationError("Preset name stem cannot be empty for saving.")
        preset_filename = f"{preset_name_stem}.json"
        # Ensure the preset_data itself contains the correct 'preset_name' field
        # or update it before saving if necessary.
        # For example: preset_data['preset_name'] = preset_name_stem
        self._save_json_to_user_config(preset_data, preset_filename, subdir=self.USER_PRESETS_SUBDIR_NAME)


    @property
    def keybind_config(self) -> dict[str, list[str]]:
        """
        Processes FILE_TYPE_DEFINITIONS to create a mapping of keybinds
        to their associated file type keys.
        Example: {'C': ['MAP_COL'], 'R': ['MAP_ROUGH', 'MAP_GLOSS']}
        """
        keybinds = {}
        # _file_type_definitions is guaranteed to be a dict by the loader
        for ftd_key, ftd_value in self._file_type_definitions.items():
            if isinstance(ftd_value, dict) and 'keybind' in ftd_value:
                key = ftd_value['keybind']
                if key not in keybinds:
                    keybinds[key] = []
                keybinds[key].append(ftd_key)
        
        # Ensure toggleable keybinds have their file types in a consistent order if necessary
        # For example, for 'R': ['MAP_ROUGH', 'MAP_GLOSS']
        # The order from app_settings.json is generally preserved by dict iteration in Python 3.7+
        # but explicit sorting could be added if a specific cycle order is critical beyond config file order.
        # For now, we rely on the order they appear in the config.
        return keybinds

# The global load_base_config() is effectively replaced by Configuration.__init__
# Global save/load functions for individual files are refactored to be methods
# of the Configuration class or called by them, using instance paths.

# For example, to get a list of preset names, one might need a static method
# or a function that knows about both bundled and user preset directories.
def get_available_preset_names(base_dir_user_config: Optional[Path], base_dir_app_bundled: Path) -> list[str]:
    """
    Gets a list of available preset names (stems) by looking in user presets
    and then bundled presets. User presets take precedence.
    """
    preset_names = set()
    
    # Check user presets first
    if base_dir_user_config:
        user_presets_dir = base_dir_user_config / Configuration.USER_PRESETS_SUBDIR_NAME
        if user_presets_dir.is_dir():
            for f in user_presets_dir.glob("*.json"):
                preset_names.add(f.stem)
                
    # Check bundled presets
    bundled_presets_dir = base_dir_app_bundled / Configuration.PRESETS_DIR_APP_BUNDLED_NAME
    if bundled_presets_dir.is_dir():
        for f in bundled_presets_dir.glob("*.json"):
            preset_names.add(f.stem) # Adds if not already present from user dir
            
    if not preset_names:
        log.warning("No preset files found in user or bundled preset directories.")
        # Consider adding a default/template preset if none are found, or ensure one always exists in bundle.
        # For now, return empty list.
    
    return sorted(list(preset_names))

# Global functions like load_asset_definitions, save_asset_definitions etc.
# are now instance methods of the Configuration class (e.g., self.save_asset_type_definitions).
# If any external code was calling these global functions, it will need to be updated
# to instantiate a Configuration object and call its methods, or these global
# functions need to be carefully adapted to instantiate Configuration internally
# or accept a Configuration instance.

# For now, let's assume the primary interaction is via Configuration instance.
# The old global functions below this point are effectively deprecated by the class methods.
# I will remove them to avoid confusion and ensure all save/load operations
# are managed through the Configuration instance with correct path context.

# Removing old global load/save functions as their logic is now
# part of the Configuration class or replaced by its new loading/saving mechanisms.
# load_base_config() - Replaced by Configuration.__init__()
# save_llm_config(settings_dict: dict) - Replaced by Configuration.save_llm_settings()
# save_user_config(settings_dict: dict) - Replaced by Configuration.save_user_settings()
# save_base_config(settings_dict: dict) - Bundled app_settings.json should be read-only.
# load_asset_definitions() -> dict - Replaced by Configuration._load_definition_file_with_fallback() logic
# save_asset_definitions(data: dict) - Replaced by Configuration.save_asset_type_definitions()
# load_file_type_definitions() -> dict - Replaced by Configuration._load_definition_file_with_fallback() logic
# save_file_type_definitions(data: dict) - Replaced by Configuration.save_file_type_definitions()
# load_supplier_settings() -> dict - Replaced by Configuration._load_definition_file_with_fallback() logic
# save_supplier_settings(data: dict) - Replaced by Configuration.save_supplier_settings()
