import logging
import fnmatch
from typing import List, Set

from .base_stage import ProcessingStage
from ..asset_context import AssetProcessingContext
from rule_structure import FileRule


class FileRuleFilterStage(ProcessingStage):
    """
    Determines which FileRules associated with an AssetRule should be processed.
    Populates context.files_to_process, respecting FILE_IGNORE rules.
    """

    def execute(self, context: AssetProcessingContext) -> AssetProcessingContext:
        """
        Executes the file rule filtering logic.

        Args:
            context: The AssetProcessingContext for the current asset.

        Returns:
            The modified AssetProcessingContext.
        """
        asset_name_for_log = context.asset_rule.asset_name if context.asset_rule else "Unknown Asset"
        if context.status_flags.get('skip_asset'):
            logging.debug(f"Asset '{asset_name_for_log}': Skipping FileRuleFilterStage due to 'skip_asset' flag.")
            return context

        context.files_to_process: List[FileRule] = []
        ignore_patterns: Set[str] = set()

        # Step 1: Collect all FILE_IGNORE patterns
        if context.asset_rule and context.asset_rule.files:
            for file_rule in context.asset_rule.files:
                if file_rule.item_type == "FILE_IGNORE": # Removed 'and file_rule.active'
                    if hasattr(file_rule, 'file_path') and file_rule.file_path:
                        ignore_patterns.add(file_rule.file_path)
                        logging.debug(
                            f"Asset '{asset_name_for_log}': Registering ignore pattern: '{file_rule.file_path}'"
                        )
                    else:
                        logging.warning(f"Asset '{asset_name_for_log}': FILE_IGNORE rule found without a file_path. Skipping this ignore rule.")
        else:
            logging.debug(f"Asset '{asset_name_for_log}': No file rules (context.asset_rule.files) to process or asset_rule is None.")
            # Still need to return context even if there are no rules
            logging.info(f"Asset '{asset_name_for_log}': 0 file rules queued for processing after filtering.")
            return context


        # Step 2: Filter and add processable FileRules
        for file_rule in context.asset_rule.files: # Iterate over .files
            # Removed 'if not file_rule.active:' check

            if file_rule.item_type == "FILE_IGNORE":
                # Already processed, skip.
                continue

            is_ignored = False
            # Ensure file_rule.file_path exists before using it with fnmatch
            current_file_path = file_rule.file_path if hasattr(file_rule, 'file_path') else None
            if not current_file_path:
                logging.warning(f"Asset '{asset_name_for_log}': FileRule found without a file_path. Skipping this rule for ignore matching.")
                # Decide if this rule should be added or skipped if it has no path
                # For now, let's assume it might be an error and not add it if it can't be matched.
                # If it should be added by default, this logic needs adjustment.
                continue


            for ignore_pat in ignore_patterns:
                if fnmatch.fnmatch(current_file_path, ignore_pat):
                    is_ignored = True
                    logging.debug(
                        f"Asset '{asset_name_for_log}': Skipping file rule for '{current_file_path}' "
                        f"due to matching ignore pattern '{ignore_pat}'."
                    )
                    break
            
            if not is_ignored:
                context.files_to_process.append(file_rule)
                logging.debug(
                    f"Asset '{asset_name_for_log}': Adding file rule for '{current_file_path}' "
                    f"(type: {file_rule.item_type}) to processing queue."
                )

        logging.info(
            f"Asset '{asset_name_for_log}': {len(context.files_to_process)} file rules queued for processing after filtering."
        )
        return context