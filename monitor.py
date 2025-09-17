
import os
import sys
import time
import logging
import re
import shutil
import tempfile
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from watchdog.observers.polling import PollingObserver as Observer # Use polling for better compatibility
from watchdog.events import FileSystemEventHandler, FileCreatedEvent

from utils.hash_utils import calculate_sha256
from utils.path_utils import get_next_incrementing_value

from configuration import load_config, ConfigurationError
from processing_engine import ProcessingEngine, ProcessingError
from rule_structure import SourceRule
try:
    from utils.workspace_utils import prepare_processing_workspace, WorkspaceError
except ImportError:
    log = logging.getLogger(__name__) # Need logger early for this message
    log.warning("Could not import workspace_utils. Workspace preparation/cleanup might fail.")
    # Define dummy functions/exceptions if import fails to avoid NameErrors later,
    # but log prominently.
    def prepare_processing_workspace(archive_path: Path) -> Path:
        log.error("prepare_processing_workspace is not available!")
        # Create a dummy temp dir to allow code flow, but it won't be the real one
        return Path(tempfile.mkdtemp(prefix="dummy_workspace_"))
    class WorkspaceError(Exception): pass

from utils.prediction_utils import generate_source_rule_from_archive, PredictionError


INPUT_DIR = Path(os.environ.get('INPUT_DIR', '/data/input'))
OUTPUT_DIR = Path(os.environ.get('OUTPUT_DIR', '/data/output'))
PROCESSED_DIR = Path(os.environ.get('PROCESSED_DIR', '/data/processed'))
ERROR_DIR = Path(os.environ.get('ERROR_DIR', '/data/error'))
LOG_LEVEL_STR = os.environ.get('LOG_LEVEL', 'INFO').upper()
POLL_INTERVAL = int(os.environ.get('POLL_INTERVAL', '5'))
PROCESS_DELAY = int(os.environ.get('PROCESS_DELAY', '2'))
# Default workers for monitor - can be overridden if needed via env var
DEFAULT_WORKERS = max(1, os.cpu_count() // 2 if os.cpu_count() else 1)
NUM_WORKERS = int(os.environ.get('NUM_WORKERS', str(DEFAULT_WORKERS)))

# Configure logging (ensure logger is available before potential import errors)
log_level = getattr(logging, LOG_LEVEL_STR, logging.INFO)
log_format = '%(asctime)s [%(levelname)-8s] %(name)s: %(message)s'
date_format = '%Y-%m-%d %H:%M:%S'
logging.basicConfig(level=log_level, format=log_format, datefmt=date_format, handlers=[logging.StreamHandler(sys.stdout)])
log = logging.getLogger("monitor") # Define logger after basicConfig

log.info(f"Logging level set to: {logging.getLevelName(log_level)}")
log.info(f"Monitoring Input Directory: {INPUT_DIR}")
log.info(f"Output Directory: {OUTPUT_DIR}")
log.info(f"Processed Files Directory: {PROCESSED_DIR}")
log.info(f"Error Files Directory: {ERROR_DIR}")
log.info(f"Polling Interval: {POLL_INTERVAL}s")
log.info(f"Processing Delay: {PROCESS_DELAY}s")
log.info(f"Max Workers: {NUM_WORKERS}")


SUPPORTED_SUFFIXES = ['.zip', '.rar', '.7z']

class ZipHandler(FileSystemEventHandler):
    """Handles file system events for new ZIP files."""

    def __init__(self, input_dir: Path, output_dir: Path, processed_dir: Path, error_dir: Path):
        self.input_dir = input_dir.resolve()
        self.output_dir = output_dir.resolve()
        self.processed_dir = processed_dir.resolve()
        self.error_dir = error_dir.resolve()
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.processed_dir.mkdir(parents=True, exist_ok=True)
        self.error_dir.mkdir(parents=True, exist_ok=True)

        self.executor = ThreadPoolExecutor(max_workers=NUM_WORKERS)
        log.info(f"Handler initialized, target directories ensured. ThreadPoolExecutor started with {NUM_WORKERS} workers.")

    def on_created(self, event: FileCreatedEvent):
        """Called when a file or directory is created. Submits task to executor."""
        if event.is_directory:
            return

        src_path = Path(event.src_path)
        log.debug(f"File creation event detected: {src_path}")

        if src_path.suffix.lower() not in SUPPORTED_SUFFIXES:
            log.debug(f"Ignoring file with unsupported extension: {src_path.name}")
            return

        log.info(f"Detected new archive: {src_path.name}. Waiting {PROCESS_DELAY}s before queueing...")
        time.sleep(PROCESS_DELAY) # Wait for file write to complete

        # Re-check if file still exists (might have been temporary or moved quickly)
        if not src_path.exists():
            log.warning(f"File disappeared after delay: {src_path.name}")
            return

        log.info(f"Queueing processing task for: {src_path.name}")
        self.executor.submit(
            _process_archive_task,
            archive_path=src_path,
            output_dir=self.output_dir,
            processed_dir=self.processed_dir,
            error_dir=self.error_dir
        )

    def shutdown(self):
        """Shuts down the thread pool executor."""
        log.info("Shutting down thread pool executor...")
        self.executor.shutdown(wait=True)
        log.info("Executor shut down.")

    # move_file remains largely the same, but called from _process_archive_task now
    # We make it static or move it outside the class if _process_archive_task is outside
    @staticmethod
    def move_file(src: Path, dest_dir: Path, reason: str):
        """Safely moves a file, handling potential name collisions."""
        if not src.exists():
            log.warning(f"Source file {src} does not exist, cannot move for reason: {reason}.")
            return
        try:
            dest_path = dest_dir / src.name
            # Handle potential name collision in destination
            counter = 1
            while dest_path.exists():
                dest_path = dest_dir / f"{src.stem}_{counter}{src.suffix}"
                counter += 1
                if counter > 100: # Safety break
                     log.error(f"Could not find unique name for {src.name} in {dest_dir} after 100 attempts. Aborting move.")
                     return

            log.info(f"Moving '{src.name}' to '{dest_dir.name}/' directory (Reason: {reason}). Final path: {dest_path.name}")
            shutil.move(str(src), str(dest_path))
        except Exception as e:
            log.exception(f"Failed to move file {src.name} to {dest_dir}: {e}")


def _process_archive_task(archive_path: Path, output_dir: Path, processed_dir: Path, error_dir: Path):
    """
    Task executed by the ThreadPoolExecutor to process a single archive file.
    """
    log.info(f"[Task:{archive_path.name}] Starting processing.")
    temp_workspace_path: Optional[Path] = None
    config = None
    source_rule = None
    move_reason = "unknown_error" # Default reason if early exit

    try:
        log.debug(f"[Task:{archive_path.name}] Loading configuration...")
        # Assuming load_config() loads the main app config (e.g., app_settings.json)
        # and potentially merges preset defaults or paths. Adjust if needed.
        config = load_config() # Might need path argument depending on implementation
        if not config:
            raise ConfigurationError("Failed to load application configuration.")
        log.debug(f"[Task:{archive_path.name}] Configuration loaded.")

        log.debug(f"[Task:{archive_path.name}] Generating source rule prediction...")
        # This function now handles preset extraction and validation internally
        source_rule = generate_source_rule_from_archive(archive_path, config)
        log.info(f"[Task:{archive_path.name}] SourceRule generated successfully.")

        log.debug(f"[Task:{archive_path.name}] Preparing processing workspace...")
        # This utility should handle extraction and return the temp dir path
        temp_workspace_path = prepare_processing_workspace(archive_path)
        log.info(f"[Task:{archive_path.name}] Workspace prepared at: {temp_workspace_path}")

        log.debug(f"[Task:{archive_path.name}] Initializing Processing Engine...")
        engine = ProcessingEngine(config=config, output_base_dir=output_dir)
        log.info(f"[Task:{archive_path.name}] Running Processing Engine...")


        sha5_value = None
        try:
            if archive_path.is_file():
                log.debug(f"[Task:{archive_path.name}] Calculating SHA256 for file: {archive_path}")
                full_sha = calculate_sha256(archive_path)
                if full_sha:
                    sha5_value = full_sha[:5]
                    log.info(f"[Task:{archive_path.name}] Calculated SHA5: {sha5_value}")
                else:
                    log.warning(f"[Task:{archive_path.name}] SHA256 calculation returned None for {archive_path}")
            # No need to check is_dir here as monitor only processes files based on SUPPORTED_SUFFIXES
            else:
                 log.warning(f"[Task:{archive_path.name}] Input path {archive_path} is not a valid file for SHA5 calculation (unexpected).")
        except FileNotFoundError:
            log.error(f"[Task:{archive_path.name}] SHA5 calculation failed: File not found at {archive_path}")
        except Exception as e:
            log.exception(f"[Task:{archive_path.name}] Error calculating SHA5 for {archive_path}: {e}")

        next_increment_str = None
        try:
            # Assuming config object has 'output_directory_pattern' attribute/key
            pattern = getattr(config, 'output_directory_pattern', None) # Use getattr for safety
            if pattern:
                if re.search(r"\[IncrementingValue\]|#+", pattern):
                    log.debug(f"[Task:{archive_path.name}] Incrementing token found in pattern '{pattern}'. Calculating next value for dir: {output_dir}")
                    next_increment_str = get_next_incrementing_value(output_dir, pattern)
                    log.info(f"[Task:{archive_path.name}] Calculated next incrementing value: {next_increment_str}")
                else:
                    log.debug(f"[Task:{archive_path.name}] No incrementing token found in pattern '{pattern}'. Skipping increment calculation.")
                    next_increment_str = None
            else:
                # Check if config is a dict as fallback (depends on load_config implementation)
                if isinstance(config, dict):
                    pattern = config.get('output_directory_pattern')
                    if pattern:
                        if re.search(r"\[IncrementingValue\]|#+", pattern):
                            log.debug(f"[Task:{archive_path.name}] Incrementing token found in pattern '{pattern}' (from dict). Calculating next value for dir: {output_dir}")
                            next_increment_str = get_next_incrementing_value(output_dir, pattern)
                            log.info(f"[Task:{archive_path.name}] Calculated next incrementing value (from dict): {next_increment_str}")
                        else:
                            log.debug(f"[Task:{archive_path.name}] No incrementing token found in pattern '{pattern}' (from dict). Skipping increment calculation.")
                            next_increment_str = None
                    else:
                        log.warning(f"[Task:{archive_path.name}] Cannot calculate incrementing value: 'output_directory_pattern' not found in configuration dictionary.")
                else:
                    log.warning(f"[Task:{archive_path.name}] Cannot calculate incrementing value: 'output_directory_pattern' not found in configuration object.")
        except Exception as e:
            log.exception(f"[Task:{archive_path.name}] Error calculating next incrementing value for {output_dir}: {e}")

        # The engine uses the source_rule to guide processing on the workspace files
        log.info(f"[Task:{archive_path.name}] Calling engine.run with sha5='{sha5_value}', incrementing_value='{next_increment_str}'")
        engine.run(
            workspace_path=temp_workspace_path,
            source_rule=source_rule,
            incrementing_value=next_increment_str,
            sha5_value=sha5_value
        )
        log.info(f"[Task:{archive_path.name}] Processing Engine finished successfully.")
        move_reason = "processed"

        # If engine.run completes without exception, assume success for now.
        # More granular results could be returned by engine.run if needed.
        # Moving is handled outside the main try block based on move_reason

        # TODO: Add call to utils.blender_utils.run_blender_script if needed later


    except FileNotFoundError as e:
        log.error(f"[Task:{archive_path.name}] Prerequisite file not found: {e}")
        move_reason = "file_not_found"
    except (ConfigurationError, PredictionError, WorkspaceError, ProcessingError) as e:
        log.error(f"[Task:{archive_path.name}] Processing failed: {e}", exc_info=True)
        move_reason = f"{type(e).__name__.lower()}" # e.g., "predictionerror"
    except Exception as e:
        log.exception(f"[Task:{archive_path.name}] An unexpected error occurred during processing: {e}")
        move_reason = "unexpected_exception"

    finally:
        log.debug(f"[Task:{archive_path.name}] Moving original archive based on outcome: {move_reason}")
        dest_dir = processed_dir if move_reason == "processed" else error_dir
        try:
            ZipHandler.move_file(archive_path, dest_dir, move_reason)
        except Exception as move_err:
            log.exception(f"[Task:{archive_path.name}] CRITICAL: Failed to move archive file {archive_path} after processing: {move_err}")

        if temp_workspace_path and temp_workspace_path.exists():
            log.debug(f"[Task:{archive_path.name}] Cleaning up workspace: {temp_workspace_path}")
            try:
                shutil.rmtree(temp_workspace_path)
                log.info(f"[Task:{archive_path.name}] Workspace cleaned up successfully.")
            except OSError as e:
                log.error(f"[Task:{archive_path.name}] Error removing temporary workspace {temp_workspace_path}: {e}", exc_info=True)
        elif temp_workspace_path:
             log.warning(f"[Task:{archive_path.name}] Temporary workspace path recorded but not found for cleanup: {temp_workspace_path}")

        log.info(f"[Task:{archive_path.name}] Processing task finished with status: {move_reason}")


if __name__ == "__main__":
    if not INPUT_DIR.is_dir():
        log.error(f"Input directory does not exist or is not a directory: {INPUT_DIR}")
        log.error("Please create the directory or mount a volume correctly.")
        sys.exit(1)

    event_handler = ZipHandler(INPUT_DIR, OUTPUT_DIR, PROCESSED_DIR, ERROR_DIR)
    observer = Observer()
    observer.schedule(event_handler, str(INPUT_DIR), recursive=False) # Don't watch subdirectories

    log.info("Starting file system monitor...")
    observer.start()
    log.info("Monitor started. Press Ctrl+C to stop.")

    try:
        while True:
            # Keep the main thread alive, observer runs in background thread
            time.sleep(1)
    except KeyboardInterrupt:
        log.info("Keyboard interrupt received, stopping monitor and executor...")
        observer.stop()
        event_handler.shutdown() # Gracefully shutdown the executor
    except Exception as e:
        log.exception(f"An unexpected error occurred in the main loop: {e}")
        observer.stop()
        event_handler.shutdown() # Ensure shutdown on other exceptions too

    observer.join()
    log.info("Monitor stopped.")