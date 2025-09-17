import os
import json
import requests
import re
import logging
from pathlib import Path
from PySide6.QtCore import QObject, Slot
# Removed Signal, QThread as they are handled by BasePredictionHandler or caller
from typing import List, Dict, Any

# Assuming rule_structure defines SourceRule, AssetRule, FileRule etc.
# Adjust the import path if necessary based on project structure
from rule_structure import SourceRule, AssetRule, FileRule

# Assuming configuration loads app_settings.json
# Adjust the import path if necessary
# Removed Configuration import
from .base_prediction_handler import BasePredictionHandler

log = logging.getLogger(__name__)

class LLMPredictionHandler(BasePredictionHandler):
    """
    Handles the interaction with an LLM for predicting asset structures
    based on a directory's file list. Inherits from BasePredictionHandler.
    """
    # Signals (prediction_ready, prediction_error, status_update) are inherited

    # Changed 'config: Configuration' to 'settings: dict'
    def __init__(self, input_source_identifier: str, file_list: list, settings: dict, parent: QObject = None):
        """
        Initializes the LLM handler.

        Args:
            input_source_identifier: The unique identifier for the input source (e.g., file path).
            file_list: A list of *relative* file paths extracted from the input source.
                       (LLM expects relative paths based on the prompt template).
            settings: A dictionary containing required LLM and App settings.
            parent: The parent QObject.
        """
        super().__init__(input_source_identifier, parent)
        # input_source_identifier is stored by the base class as self.input_source_identifier
        self.file_list = file_list
        self.settings = settings
        # Access LLM settings via self.settings['key']
        # _is_running and _is_cancelled are handled by the base class

    # The run() and cancel() slots are provided by the base class.
    # We only need to implement the core logic in _perform_prediction.

    def _perform_prediction(self) -> List[SourceRule]:
        """
        Performs the LLM prediction by preparing the prompt, calling the LLM,
        and parsing the response. Implements the abstract method from BasePredictionHandler.

        Returns:
            A list containing a single SourceRule object based on the LLM response,
            or an empty list if prediction fails or yields no results.

        Raises:
            ValueError: If required settings (like endpoint URL or prompt template) are missing.
            ConnectionError: If the LLM API call fails due to network issues or timeouts.
            Exception: For other errors during prompt preparation, API call, or parsing.
        """
        log.debug(f"--> Entered LLMPredictionHandler._perform_prediction() for {self.input_source_identifier}")
        log.info(f"Performing LLM prediction for: {self.input_source_identifier}")
        base_name = Path(self.input_source_identifier).name

        if not self.file_list:
            log.warning(f"No files provided for LLM prediction for {self.input_source_identifier}. Returning empty list.")
            self.status_update.emit(f"No files found for {base_name}.")
            return [] # Return empty list, not an error

        # Check for cancellation before preparing prompt
        if self._is_cancelled:
            log.info("LLM prediction cancelled before preparing prompt.")
            return []

        # --- Prepare Prompt ---
        self.status_update.emit(f"Preparing LLM input for {base_name}...")
        try:
            prompt = self._prepare_prompt(self.file_list)
        except Exception as e:
            log.exception("Error preparing LLM prompt.")
            raise ValueError(f"Error preparing LLM prompt: {e}") from e # Re-raise for base handler

        if self._is_cancelled:
            log.info("LLM prediction cancelled after preparing prompt.")
            return []

        # --- Call LLM ---
        self.status_update.emit(f"Calling LLM for {base_name}...")
        try:
            llm_response_json_str = self._call_llm(prompt)
        except Exception as e:
            log.exception("Error calling LLM API.")
            # Re-raise potentially specific errors (ConnectionError, ValueError) or a generic one
            raise RuntimeError(f"Error calling LLM: {e}") from e

        if self._is_cancelled:
            log.info("LLM prediction cancelled after calling LLM.")
            return []

        # --- Parse Response ---
        self.status_update.emit(f"Parsing LLM response for {base_name}...")
        try:
            predicted_rules = self._parse_llm_response(llm_response_json_str)
        except Exception as e:
            log.exception("Error parsing LLM response.")
            raise ValueError(f"Error parsing LLM response: {e}") from e # Re-raise for base handler

        if self._is_cancelled:
            log.info("LLM prediction cancelled after parsing response.")
            return []

        log.info(f"LLM prediction finished successfully for '{self.input_source_identifier}'.")
        # The base class run() method will emit prediction_ready with these results
        return predicted_rules


    # --- Helper Methods (Keep these internal to this class) ---

    def _prepare_prompt(self, relative_file_list: List[str]) -> str:
        """
        Prepares the full prompt string to send to the LLM using stored settings.
        """
        prompt_template = self.settings.get('predictor_prompt')
        if not prompt_template:
            raise ValueError("LLM predictor prompt template content is empty or missing in settings.")


        asset_defs = json.dumps(self.settings.get('asset_type_definitions', {}), indent=4)
        # Combine file type defs and examples (assuming structure from Configuration class)
        file_type_defs_combined = {}
        file_type_defs = self.settings.get('file_type_definitions', {})
        for key, definition in file_type_defs.items():
             # Add examples if they exist within the definition structure
             file_type_defs_combined[key] = {
                 "description": definition.get("description", ""),
                 "examples": definition.get("examples", [])
             }
        file_defs = json.dumps(file_type_defs_combined, indent=4)
        examples = json.dumps(self.settings.get('examples', []), indent=2)

        # Format *relative* file list as a single string with newlines
        file_list_str = "\n".join(relative_file_list)

        prompt = prompt_template.replace('{ASSET_TYPE_DEFINITIONS}', asset_defs)
        prompt = prompt.replace('{FILE_TYPE_DEFINITIONS}', file_defs)
        prompt = prompt.replace('{EXAMPLE_INPUT_OUTPUT_PAIRS}', examples)
        prompt = prompt.replace('{FILE_LIST}', file_list_str)

        return prompt

    def _call_llm(self, prompt: str) -> str:
        """
        Calls the configured LLM API endpoint with the prepared prompt.

        Args:
            prompt: The complete prompt string.

        Returns:
            The content string from the LLM response, expected to be JSON.

        Raises:
            ConnectionError: If the request fails due to network issues or timeouts.
            ValueError: If the endpoint URL is not configured or the response is invalid.
            requests.exceptions.RequestException: For other request-related errors.
        """
        endpoint_url = self.settings.get('endpoint_url')
        if not endpoint_url:
            raise ValueError("LLM endpoint URL is not configured in settings.")

        headers = {
            "Content-Type": "application/json",
        }
        api_key = self.settings.get('api_key')
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"

        # Construct payload based on OpenAI Chat Completions format
        payload = {
            "model": self.settings.get('model_name', 'local-model'),
            "messages": [{"role": "user", "content": prompt}],
            "temperature": self.settings.get('temperature', 0.5),
            # Ensure the LLM is instructed to return JSON in the prompt itself
        }

        print(f"--- Calling LLM API: {endpoint_url} ---")

        # Note: Exceptions raised here (Timeout, RequestException, ValueError)
        # will be caught by the _perform_prediction method's handler.

        response = requests.post(
            endpoint_url,
            headers=headers,
            json=payload,
            timeout=self.settings.get('request_timeout', 120)
        )
        response.raise_for_status() # Raise HTTPError for bad responses (4xx or 5xx)

        response_data = response.json()

        # Extract content - structure depends on the API (OpenAI format assumed)
        if "choices" in response_data and len(response_data["choices"]) > 0:
            message = response_data["choices"][0].get("message", {})
            content = message.get("content")
            if content:
                # The content itself should be the JSON string we asked for
                log.debug("--- LLM Response Content Extracted Successfully ---")
                return content.strip()
            else:
                raise ValueError("LLM response missing 'content' in choices[0].message.")
        else:
            raise ValueError("LLM response missing 'choices' array or it's empty.")

    def _parse_llm_response(self, llm_response_json_str: str) -> List[SourceRule]:
        """
        Parses the LLM's JSON response string (new two-part format) into a
        list containing a single SourceRule object.
        Includes sanitization for comments and markdown fences.
        """
        # Note: Exceptions (JSONDecodeError, ValueError) raised here
        # will be caught by the _perform_prediction method's handler.

        # --- Sanitize Input String ---
        clean_json_str = re.sub(r'/\*.*?\*/', '', llm_response_json_str.strip(), flags=re.DOTALL)

        # 2. Remove single-line // comments (handle potential URLs carefully)
        #    Only remove // if it's likely a comment (e.g., whitespace before it,
        #    or at the start of a line after stripping leading whitespace).
        lines = clean_json_str.splitlines()
        cleaned_lines = []
        for line in lines:
            stripped_line = line.strip()
            # Find the first // that isn't preceded by a : (to avoid breaking URLs like http://)
            comment_index = -1
            search_start = 0
            while True:
                idx = stripped_line.find('//', search_start)
                if idx == -1:
                    break # No more // found
                if idx == 0 or stripped_line[idx-1] != ':':
                    # Found a potential comment marker
                    # Check if it's inside quotes
                    in_quotes = False
                    quote_char = ''
                    for i in range(idx):
                        char = stripped_line[i]
                        if char in ('"', "'") and (i == 0 or stripped_line[i-1] != '\\'): # Handle escaped quotes
                            if not in_quotes:
                                in_quotes = True
                                quote_char = char
                            elif char == quote_char:
                                in_quotes = False
                                quote_char = ''
                    if not in_quotes:
                        comment_index = idx
                        break # Found valid comment marker
                    else:
                        # // is inside quotes, continue searching after it
                        search_start = idx + 2
                else:
                    # Found ://, likely a URL, continue searching after it
                    search_start = idx + 2

            if comment_index != -1:
                # Find the original position in the non-stripped line
                original_comment_start = line.find(stripped_line[comment_index:])
                cleaned_lines.append(line[:original_comment_start].rstrip())
            else:
                cleaned_lines.append(line)
        clean_json_str = "\n".join(cleaned_lines)


        # 3. Remove markdown code fences
        clean_json_str = clean_json_str.strip()
        if clean_json_str.startswith("```json"):
            clean_json_str = clean_json_str[7:].strip()
        if clean_json_str.endswith("```"):
            clean_json_str = clean_json_str[:-3].strip()

        # 4. Remove <think> tags (just in case)
        clean_json_str = re.sub(r'<think>.*?</think>', '', clean_json_str, flags=re.DOTALL | re.IGNORECASE).strip()

        # --- Parse Sanitized JSON ---
        try:
            response_data = json.loads(clean_json_str)
        except json.JSONDecodeError as e:
            error_detail = f"Failed to decode LLM JSON response after sanitization: {e}\nSanitized Response Attempted:\n{clean_json_str}"
            log.error(f"ERROR: {error_detail}")
            raise ValueError(error_detail)

        # --- Validate Top-Level Structure ---
        if not isinstance(response_data, dict):
             raise ValueError("Invalid LLM response: Root element is not a JSON object.")

        if "individual_file_analysis" not in response_data or not isinstance(response_data["individual_file_analysis"], list):
            raise ValueError("Invalid LLM response format: 'individual_file_analysis' key missing or not a list.")

        if "asset_group_classifications" not in response_data or not isinstance(response_data["asset_group_classifications"], dict):
            raise ValueError("Invalid LLM response format: 'asset_group_classifications' key missing or not a dictionary.")

        # --- Prepare for Rule Creation ---
        source_rule = SourceRule(input_path=self.input_source_identifier)
        valid_asset_types = list(self.settings.get('asset_type_definitions', {}).keys())
        valid_file_types = list(self.settings.get('file_type_definitions', {}).keys())
        asset_rules_map: Dict[str, AssetRule] = {} # Maps group_name to AssetRule

        # --- Process Individual Files and Build Rules ---
        for file_data in response_data["individual_file_analysis"]:
            # Check for cancellation within the loop
            if self._is_cancelled:
                log.info("LLM prediction cancelled during response parsing (files).")
                return []

            if not isinstance(file_data, dict):
                log.warning(f"Skipping invalid file data entry (not a dict): {file_data}")
                continue

            file_path_rel = file_data.get("relative_file_path")
            file_type = file_data.get("classified_file_type")
            group_name = file_data.get("proposed_asset_group_name") # Can be string or null

            # --- Validate File Data ---
            if not file_path_rel or not isinstance(file_path_rel, str):
                log.warning(f"Missing or invalid 'relative_file_path' in file data: {file_data}. Skipping file.")
                continue

            if not file_type or not isinstance(file_type, str):
                log.warning(f"Missing or invalid 'classified_file_type' for file '{file_path_rel}'. Skipping file.")
                continue

            # Handle FILE_IGNORE explicitly
            if file_type == "FILE_IGNORE":
                log.debug(f"Ignoring file as per LLM prediction: {file_path_rel}")
                continue # Skip creating a rule for this file

            # Validate file_type against definitions
            if file_type not in valid_file_types:
                log.warning(f"Invalid predicted_file_type '{file_type}' for file '{file_path_rel}'. Defaulting to EXTRA.")
                file_type = "EXTRA"

            # --- Handle Grouping and Asset Type ---
            if not group_name or not isinstance(group_name, str):
                log.warning(f"File '{file_path_rel}' has missing, null, or invalid 'proposed_asset_group_name' ({group_name}). Cannot assign to an asset. Skipping file.")
                continue

            asset_type = response_data["asset_group_classifications"].get(group_name)

            if not asset_type:
                log.warning(f"No classification found in 'asset_group_classifications' for group '{group_name}' (proposed for file '{file_path_rel}'). Skipping file.")
                continue

            if asset_type not in valid_asset_types:
                 log.warning(f"Invalid asset_type '{asset_type}' found in 'asset_group_classifications' for group '{group_name}'. Skipping file '{file_path_rel}'.")
                 continue

            # --- Construct Absolute Path ---
            try:
                base_path = Path(self.input_source_identifier)
                if base_path.is_file():
                    base_path = base_path.parent
                clean_rel_path = Path(file_path_rel.strip().replace('\\', '/'))
                file_path_abs = str(base_path / clean_rel_path)
            except Exception as path_e:
                log.warning(f"Error constructing absolute path for '{file_path_rel}' relative to '{self.input_source_identifier}': {path_e}. Skipping file.")
                continue

            # --- Get or Create Asset Rule ---
            asset_rule = asset_rules_map.get(group_name)
            if not asset_rule:
                # Create new AssetRule if this is the first file for this group
                log.debug(f"Creating new AssetRule for group '{group_name}' with type '{asset_type}'.")
                asset_rule = AssetRule(asset_name=group_name, asset_type=asset_type)
                source_rule.assets.append(asset_rule)
                asset_rules_map[group_name] = asset_rule

            # --- Create and Add File Rule ---
            file_rule = FileRule(
                file_path=file_path_abs,
                item_type=file_type,
                item_type_override=file_type, # Initial override based on LLM
                target_asset_name_override=group_name,
                output_format_override=None,
                resolution_override=None,
                channel_merge_instructions={}
            )
            asset_rule.files.append(file_rule)
            log.debug(f"Added file '{file_path_rel}' (type: {file_type}) to asset '{group_name}'.")


        # Log if no assets were created
        if not source_rule.assets:
            log.warning(f"LLM prediction for '{self.input_source_identifier}' resulted in zero valid assets after parsing.")

        return [source_rule] # Return list containing the single SourceRule
