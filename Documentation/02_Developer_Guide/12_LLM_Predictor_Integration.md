# LLM Predictor Integration

## Overview

The LLM Predictor feature provides an alternative method for classifying asset textures using a Large Language Model (LLM). This allows for more flexible and potentially more accurate classification compared to traditional rule-based methods, especially for diverse or complex asset names.

## Configuration

The LLM Predictor is configured via settings in the dedicated `config/llm_settings.json` file. These settings control the behavior of the LLM interaction:

-   `llm_predictor_prompt`: The template for the prompt sent to the LLM. This prompt should guide the LLM to classify the asset based on its name and potentially other context. It can include placeholders that will be replaced with actual data during processing.
-   `llm_endpoint_url`: The URL of the LLM API endpoint.
-   `llm_api_key`: The API key required for authentication with the LLM endpoint.
-   `llm_model_name`: The name of the specific LLM model to be used for prediction.
-   `llm_temperature`: Controls the randomness of the LLM's output. A lower temperature results in more deterministic output, while a higher temperature increases creativity.
-   `llm_request_timeout`: The maximum time (in seconds) to wait for a response from the LLM API.
-   `llm_predictor_examples`: A list of example input/output pairs to include in the prompt for few-shot learning, helping the LLM understand the desired output format and classification logic.

**Editing:** These settings can be edited directly through the GUI using the **`LLMEditorWidget`** (`gui/llm_editor_widget.py`), which provides a user-friendly interface for modifying the prompt, examples, and API parameters. Changes are saved back to `config/llm_settings.json` via the `configuration.save_llm_config()` function.

**Loading:** The `LLMInteractionHandler` now loads these settings directly from `config/llm_settings.json` and relevant parts of `config/app_settings.json` when it needs to start an `LLMPredictionHandler` task. It no longer relies on the main `Configuration` class for LLM-specific settings. The prompt structure remains crucial for effective classification. Placeholders within the prompt template (e.g., `{FILE_LIST}`) are dynamically replaced with relevant data before the request is sent.

## Expected LLM Output Format (Refactored)

The LLM is now expected to return a JSON object containing two distinct parts. This structure helps the LLM maintain context across multiple files belonging to the same conceptual asset and allows for a more robust grouping mechanism.

**Rationale:** The previous implicit format made it difficult for the LLM to consistently group related files (e.g., different texture maps for the same material) under a single asset, especially in complex archives. The new two-part structure explicitly separates file-level analysis from asset-level classification, improving accuracy and consistency.

**Structure:**

```json
{
  "individual_file_analysis": [
    {
      "relative_file_path": "Textures/Wood_Floor_01/Wood_Floor_01_BaseColor.png",
      "classified_file_type": "BaseColor",
      "proposed_asset_group_name": "Wood_Floor_01"
    },
    {
      "relative_file_path": "Textures/Wood_Floor_01/Wood_Floor_01_Roughness.png",
      "classified_file_type": "Roughness",
      "proposed_asset_group_name": "Wood_Floor_01"
    },
    {
      "relative_file_path": "Textures/Metal_Plate_03/Metal_Plate_03_Metallic.jpg",
      "classified_file_type": "Metallic",
      "proposed_asset_group_name": "Metal_Plate_03"
    }
  ],
  "asset_group_classifications": {
    "Wood_Floor_01": "PBR Material",
    "Metal_Plate_03": "PBR Material"
  }
}
```

-   **`individual_file_analysis`**: A list where each object represents a single file within the source.
    -   `relative_file_path`: The path of the file relative to the source root.
    -   `classified_file_type`: The LLM's prediction for the *type* of this specific file (e.g., "BaseColor", "Normal", "Model"). This corresponds to the `item_type` in the `FileRule`.
    -   `proposed_asset_group_name`: A name suggested by the LLM to group this file with others belonging to the same conceptual asset. This is used internally by the parser.
-   **`asset_group_classifications`**: A dictionary mapping the `proposed_asset_group_name` values from the list above to a final `asset_type` (e.g., "PBR Material", "HDR Environment").

## `LLMInteractionHandler` (Refactored)

The `gui/llm_interaction_handler.py` module contains the `LLMInteractionHandler` class, which now acts as the central manager for LLM prediction tasks.

Key Responsibilities & Methods:

-   **Queue Management:** Maintains a queue (`llm_processing_queue`) of pending prediction requests (input path, file list). Handles adding single (`queue_llm_request`) or batch (`queue_llm_requests_batch`) requests.
-   **State Management:** Tracks whether an LLM task is currently running (`_is_processing`) and emits `llm_processing_state_changed(bool)` to update the GUI (e.g., disable preset editor). Includes `force_reset_state()` for recovery.
-   **Task Orchestration:** Processes the queue sequentially (`_process_next_llm_item`). For each item:
    *   Loads required settings directly from `config/llm_settings.json` and `config/app_settings.json`.
    *   Instantiates an `LLMPredictionHandler` in a new `QThread`.
    *   Passes the loaded settings dictionary to the `LLMPredictionHandler`.
    *   Connects signals from the handler (`prediction_ready`, `prediction_error`, `status_update`) to internal slots (`_handle_llm_result`, `_handle_llm_error`) or directly re-emits them (`llm_status_update`).
    *   Starts the thread.
-   **Result/Error Handling:** Internal slots (`_handle_llm_result`, `_handle_llm_error`) receive results/errors from the `LLMPredictionHandler`, remove the completed/failed item from the queue, emit the corresponding public signal (`llm_prediction_ready`, `llm_prediction_error`), and trigger processing of the next queue item.
-   **Communication:** Emits signals to `MainWindow`:
    *   `llm_prediction_ready(input_path, source_rule_list)`
    *   `llm_prediction_error(input_path, error_message)`
    *   `llm_status_update(status_message)`
    *   `llm_processing_state_changed(is_processing)`

## `LLMPredictionHandler` (Refactored)

The `gui/llm_prediction_handler.py` module contains the `LLMPredictionHandler` class (inheriting from `BasePredictionHandler`), which performs the actual LLM prediction for a *single* input source. It runs in a background thread managed by the `LLMInteractionHandler`.

Key Responsibilities & Methods:

-   **Initialization**: Takes the source identifier, file list, and a **`settings` dictionary** (passed from `LLMInteractionHandler`) containing all necessary configuration (LLM endpoint, prompt, examples, API details, type definitions, etc.).
-   **`_perform_prediction()`**: Implements the core prediction logic:
    *   **Prompt Preparation (`_prepare_prompt`)**: Uses the passed `settings` dictionary to access the prompt template, type definitions, and examples to build the final prompt string.
    *   **API Call (`_call_llm`)**: Uses the passed `settings` dictionary to get the endpoint URL, API key, model name, temperature, and timeout to make the API request.
    *   **Parsing (`_parse_llm_response`)**: Parses the LLM's JSON response (using type definitions from the `settings` dictionary for validation) and constructs the `SourceRule` hierarchy based on the two-part format (`individual_file_analysis`, `asset_group_classifications`). Includes sanitization logic for comments and markdown fences.
-   **Signals (Inherited):** Emits `prediction_ready(input_path, source_rule_list)` or `prediction_error(input_path, error_message)` upon completion or failure, which are connected to the `LLMInteractionHandler`. Also emits `status_update(message)`.

## GUI Integration

-   The LLM predictor mode is selected via the preset dropdown in `PresetEditorWidget`.
-   Selecting "LLM Interpretation" triggers `MainWindow._on_preset_selection_changed`, which switches the editor view to the `LLMEditorWidget` and calls `update_preview`.
-   `MainWindow.update_preview` (or `add_input_paths`) delegates the LLM prediction request(s) to the `LLMInteractionHandler`'s queue.
-   `LLMInteractionHandler` manages the background tasks and signals results/errors/status back to `MainWindow`.
-   `MainWindow` slots (`_on_llm_prediction_ready_from_handler`, `_on_prediction_error`, `show_status_message`, `_on_llm_processing_state_changed`) handle these signals to update the `UnifiedViewModel` and the UI state (status bar, progress, button enablement).
-   The `LLMEditorWidget` allows users to modify settings, saving them via `configuration.save_llm_config()`. `MainWindow` listens for the `settings_saved` signal to provide user feedback.

## Model Integration (Refactored)

The `gui/unified_view_model.py` module's `update_rules_for_sources` method still incorporates the results.

-   When the `prediction_signal` is received from `LLMPredictionHandler`, the accompanying `SourceRule` object (which has already been constructed based on the new two-part JSON parsing logic) is passed to `update_rules_for_sources`.
-   This method then merges the new `SourceRule` hierarchy into the existing model data, preserving user overrides where applicable. The internal structure of the received `SourceRule` now directly reflects the groupings and classifications determined by the LLM and the new parser.

## Error Handling (Updated)

Error handling is distributed:

-   **Configuration Loading:** `LLMInteractionHandler` handles errors loading `llm_settings.json` or `app_settings.json` before starting a task.
-   **LLM API Errors:** Handled within `LLMPredictionHandler._call_llm` (e.g., `requests.exceptions.RequestException`, `HTTPError`) and propagated via the `prediction_error` signal.
-   **Sanitization/Parsing Errors:** `LLMPredictionHandler._parse_llm_response` catches errors during comment/markdown removal and `json.loads()`.
-   **Structure/Validation Errors:** `LLMPredictionHandler._parse_llm_response` includes explicit checks for the required two-part JSON structure and data consistency.
-   **Task Management Errors:** `LLMInteractionHandler` handles errors during thread setup/start.

All errors ultimately result in the `llm_prediction_error` signal being emitted by `LLMInteractionHandler`, allowing `MainWindow` to inform the user via the status bar and handle the completion state.