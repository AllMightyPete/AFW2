import os
import sys
import datetime
import re
import logging
from pathlib import Path
from typing import Optional, Dict

logger = logging.getLogger(__name__)

def generate_path_from_pattern(pattern_string: str, token_data: dict) -> str:
    """
    Generates a file path by replacing tokens in a pattern string with values
    from the provided token_data dictionary.

    Args:
        pattern_string: The string containing tokens to be replaced (e.g.,
                        "[Assettype]/[supplier]/[assetname]_[resolution].[ext]").
        token_data: A dictionary where keys are token names (without brackets,
                    case-insensitive) and values are the replacement strings.
                    Special tokens like 'IncrementingValue' or '####' should
                    be provided here if used in the pattern.

    Returns:
        The generated path string with tokens replaced.

    Raises:
        ValueError: If a token required by the pattern (excluding date/time/apppath)
                    is not found in token_data.
        KeyError: If internal logic fails to find expected date/time components.
    """
    if not isinstance(pattern_string, str):
        raise TypeError("pattern_string must be a string")
    if not isinstance(token_data, dict):
        raise TypeError("token_data must be a dictionary")

    # Normalize token keys in the input data for case-insensitive matching
    normalized_token_data = {k.lower(): v for k, v in token_data.items()}

    # --- Prepare dynamic/default token values ---
    now = datetime.datetime.now()
    dynamic_tokens = {
        'date': now.strftime('%Y%m%d'),
        'time': now.strftime('%H%M%S'),
        # Provide a default ApplicationPath, can be overridden by token_data
        'applicationpath': os.path.abspath(os.getcwd())
    }

    # Merge dynamic tokens with provided data, allowing overrides
    # Provided data takes precedence
    full_token_data = {**dynamic_tokens, **normalized_token_data}

    # --- Define known tokens (lowercase) ---
    # Add variations like #### for IncrementingValue
    known_tokens_lc = {
        'assettype', 'supplier', 'assetname', 'resolution', 'ext',
        'incrementingvalue', '####', 'date', 'time', 'sha5', 'applicationpath'
    }

    output_path = pattern_string

    # --- Regex to find all tokens like [TokenName] ---
    token_pattern = re.compile(r'\[([^\]]+)\]')
    tokens_found = token_pattern.findall(pattern_string)

    processed_tokens_lc = set()

    for token_name in tokens_found:
        token_name_lc = token_name.lower()

        # Handle alias #### for IncrementingValue
        lookup_key = 'incrementingvalue' if token_name_lc == '####' else token_name_lc

        if lookup_key in processed_tokens_lc:
            continue # Already processed this token type

        if lookup_key in full_token_data:
            replacement_value = str(full_token_data[lookup_key]) # Ensure string
            # Replace all occurrences of this token (case-insensitive original name)
            # We use a regex finditer to replace only the specific token format
            # to avoid replacing substrings within other words.
            current_token_pattern = re.compile(re.escape(f'[{token_name}]'), re.IGNORECASE)
            output_path = current_token_pattern.sub(replacement_value, output_path)
            processed_tokens_lc.add(lookup_key)
        elif lookup_key in known_tokens_lc:
            # Known token but not found in data (and not a dynamic one we generated)
            logger.warning(f"Token '[{token_name}]' found in pattern but not in token_data.")
            # Raise error for non-optional tokens if needed, or replace with placeholder
            # For now, let's raise an error to be explicit
            raise ValueError(f"Required token '[{token_name}]' not found in token_data.")
        else:
            # Token not recognized
            logger.warning(f"Unknown token '[{token_name}]' found in pattern string. Leaving it unchanged.")

    # --- Final path cleaning (optional, e.g., normalize separators) ---
    # output_path = os.path.normpath(output_path) # Consider implications on mixed separators

    return output_path
def get_next_incrementing_value(output_base_path: Path, output_directory_pattern: str) -> str:
    """Determines the next incrementing value based on existing directories."""
    logger.debug(f"Calculating next increment value for pattern '{output_directory_pattern}' in '{output_base_path}'")
    match = re.match(r"(.*?)(\[IncrementingValue\]|(#+))(.*)", output_directory_pattern)
    if not match:
        logger.warning(f"Could not find incrementing token ([IncrementingValue] or #+) in pattern '{output_directory_pattern}'. Defaulting to '00'.")
        return "00" # Default fallback if pattern doesn't contain the token

    prefix_pattern, increment_token, suffix_pattern = match.groups()
    num_digits = len(increment_token) if increment_token.startswith("#") else 2 # Default to 2 for [IncrementingValue] if not specified otherwise
    logger.debug(f"Parsed pattern: prefix='{prefix_pattern}', token='{increment_token}' ({num_digits} digits), suffix='{suffix_pattern}'")

    # Replace other tokens in prefix/suffix with '*' for globbing
    glob_prefix = re.sub(r'\[[^\]]+\]', '*', prefix_pattern)
    glob_suffix = re.sub(r'\[[^\]]+\]', '*', suffix_pattern)
    # Construct the glob pattern part for the number itself
    glob_increment_part = f"[{'0-9' * num_digits}]" # Matches exactly num_digits
    glob_pattern = f"{glob_prefix}{glob_increment_part}{glob_suffix}"
    logger.debug(f"Constructed glob pattern: {glob_pattern}")

    max_value = -1
    try:
        # Prepare regex to extract the number from directory names matching the full pattern
        # Escape regex special characters in the literal parts of the pattern
        extract_prefix_re = re.escape(prefix_pattern)
        extract_suffix_re = re.escape(suffix_pattern)
        # The regex captures exactly num_digits between the escaped prefix and suffix
        extract_regex = re.compile(rf"^{extract_prefix_re}(\d{{{num_digits}}}){extract_suffix_re}.*")
        logger.debug(f"Constructed extraction regex: {extract_regex.pattern}")

        if not output_base_path.is_dir():
            logger.warning(f"Output base path '{output_base_path}' does not exist or is not a directory. Cannot scan for existing values.")
        else:
            for item in output_base_path.glob(glob_pattern):
                if item.is_dir():
                    logger.debug(f"Checking directory: {item.name}")
                    num_match = extract_regex.match(item.name)
                    if num_match:
                        try:
                            current_val = int(num_match.group(1))
                            logger.debug(f"Extracted value {current_val} from {item.name}")
                            max_value = max(max_value, current_val)
                        except (ValueError, IndexError) as e:
                            logger.warning(f"Could not parse number from matching directory '{item.name}': {e}")
                    else:
                         logger.debug(f"Directory '{item.name}' matched glob but not extraction regex.")

    except Exception as e:
        logger.error(f"Error searching for incrementing values using glob pattern '{glob_pattern}' in '{output_base_path}': {e}", exc_info=True)
        # Decide on fallback behavior - returning "00" might be safer than raising
        return "00" # Fallback on error during search

    next_value = max_value + 1
    format_string = f"{{:0{num_digits}d}}"
    next_value_str = format_string.format(next_value)
    logger.info(f"Determined next incrementing value: {next_value_str} (Max found: {max_value})")
    return next_value_str

def sanitize_filename(name: str) -> str:
    """Removes or replaces characters invalid for filenames/directory names."""
    if not isinstance(name, str): name = str(name)
    name = re.sub(r'[^\w.\-]+', '_', name) # Allow alphanumeric, underscore, hyphen, dot
    name = re.sub(r'_+', '_', name)
    name = name.strip('_')
    if not name: name = "invalid_name"
    return name

def get_filename_friendly_map_type(internal_map_type: str, file_type_definitions: Optional[Dict[str, Dict]]) -> str:
    """Derives a filename-friendly map type from the internal map type."""
    filename_friendly_map_type = internal_map_type # Fallback
    if not file_type_definitions or not isinstance(file_type_definitions, dict) or not file_type_definitions:
        logger.warning(f"Filename-friendly lookup: FILE_TYPE_DEFINITIONS not available or invalid. Falling back to internal type: {internal_map_type}")
        return filename_friendly_map_type

    base_map_key_val = None
    suffix_part = ""
    # Sort keys by length descending to match longest prefix first (e.g., MAP_ROUGHNESS before MAP_ROUGH)
    sorted_known_base_keys = sorted(list(file_type_definitions.keys()), key=len, reverse=True)

    for known_key in sorted_known_base_keys:
        if internal_map_type.startswith(known_key):
            base_map_key_val = known_key
            suffix_part = internal_map_type[len(known_key):]
            break

    if base_map_key_val:
        definition = file_type_definitions.get(base_map_key_val)
        if definition and isinstance(definition, dict):
            standard_type_alias = definition.get("standard_type")
            if standard_type_alias and isinstance(standard_type_alias, str) and standard_type_alias.strip():
                filename_friendly_map_type = standard_type_alias.strip() + suffix_part
                logger.debug(f"Filename-friendly lookup: Transformed '{internal_map_type}' -> '{filename_friendly_map_type}'")
            else:
                 logger.warning(f"Filename-friendly lookup: Standard type alias for '{base_map_key_val}' is missing or invalid. Falling back.")
        else:
            logger.warning(f"Filename-friendly lookup: No valid definition for '{base_map_key_val}'. Falling back.")
    else:
        logger.warning(f"Filename-friendly lookup: Could not parse base key from '{internal_map_type}'. Falling back.")

    return filename_friendly_map_type
# --- Basic Unit Tests ---
if __name__ == "__main__":
    print("Running basic tests for path_utils.generate_path_from_pattern...")

    test_pattern_1 = "[Assettype]/[supplier]/[assetname]_[resolution]_[Date]_[Time].[ext]"
    test_data_1 = {
        "AssetType": "Texture",
        "supplier": "MegaScans",
        "assetName": "RustyMetalPanel",
        "Resolution": "4k",
        "EXT": "png",
        "Sha5": "abcde" # Included but not in pattern
    }
    expected_1_base = f"Texture/MegaScans/RustyMetalPanel_4k_"
    try:
        result_1 = generate_path_from_pattern(test_pattern_1, test_data_1)
        assert result_1.startswith(expected_1_base)
        assert result_1.endswith(".png")
        assert len(result_1.split('_')) == 5 # Check date and time were added
        print(f"PASS: Test 1 - Basic replacement: {result_1}")
    except Exception as e:
        print(f"FAIL: Test 1 - {e}")

    test_pattern_2 = "Output/[assetname]/[assetname]_####.[ext]"
    test_data_2 = {
        "assetname": "WoodFloor",
        "IncrementingValue": "001",
        "ext": "jpg"
    }
    expected_2 = "Output/WoodFloor/WoodFloor_001.jpg"
    try:
        result_2 = generate_path_from_pattern(test_pattern_2, test_data_2)
        assert result_2 == expected_2
        print(f"PASS: Test 2 - IncrementingValue (####): {result_2}")
    except Exception as e:
        print(f"FAIL: Test 2 - {e}")

    test_pattern_3 = "AppPath=[ApplicationPath]/[assetname].[ext]"
    test_data_3 = {"assetname": "Test", "ext": "txt"}
    expected_3_start = f"AppPath={os.path.abspath(os.getcwd())}/Test.txt"
    try:
        result_3 = generate_path_from_pattern(test_pattern_3, test_data_3)
        assert result_3 == expected_3_start
        print(f"PASS: Test 3 - ApplicationPath (default): {result_3}")
    except Exception as e:
        print(f"FAIL: Test 3 - {e}")

    test_pattern_4 = "AppPath=[ApplicationPath]/[assetname].[ext]"
    test_data_4 = {"assetname": "Test", "ext": "txt", "ApplicationPath": "/custom/path"}
    expected_4 = "/custom/path/Test.txt" # Note: AppPath= part is replaced by the token logic
    # Correction: The pattern includes "AppPath=", so it should remain.
    expected_4_corrected = "AppPath=/custom/path/Test.txt"
    try:
        result_4 = generate_path_from_pattern(test_pattern_4, test_data_4)
        assert result_4 == expected_4_corrected
        print(f"PASS: Test 4 - ApplicationPath (override): {result_4}")
    except Exception as e:
        print(f"FAIL: Test 4 - {e}")


    test_pattern_5 = "[assetname]/[MissingToken].[ext]"
    test_data_5 = {"assetname": "FailureTest", "ext": "err"}
    try:
        generate_path_from_pattern(test_pattern_5, test_data_5)
        print("FAIL: Test 5 - Expected ValueError for missing token")
    except ValueError as e:
        assert "MissingToken" in str(e)
        print(f"PASS: Test 5 - Correctly raised ValueError for missing token: {e}")
    except Exception as e:
        print(f"FAIL: Test 5 - Incorrect exception type: {e}")


    test_pattern_6 = "[assetname]/[UnknownToken].[ext]"
    test_data_6 = {"assetname": "UnknownTest", "ext": "dat"}
    expected_6 = "UnknownTest/[UnknownToken].dat" # Unknown tokens are left as is
    try:
        # Capture warnings
        logging.basicConfig()
        with logging.catch_warnings(record=True) as w:
            result_6 = generate_path_from_pattern(test_pattern_6, test_data_6)
            assert result_6 == expected_6
            assert len(w) == 1
            assert "Unknown token '[UnknownToken]'" in str(w[0].message)
            print(f"PASS: Test 6 - Unknown token left unchanged: {result_6}")
    except Exception as e:
        print(f"FAIL: Test 6 - {e}")

    test_pattern_7 = "[assetname]/[assetname].png" # Case check
    test_data_7 = {"AssetName": "CaseTest"}
    expected_7 = "CaseTest/CaseTest.png"
    try:
        result_7 = generate_path_from_pattern(test_pattern_7, test_data_7)
        assert result_7 == expected_7
        print(f"PASS: Test 7 - Case insensitivity: {result_7}")
    except Exception as e:
        print(f"FAIL: Test 7 - {e}")


    print("Basic tests finished.")