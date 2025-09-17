
import tempfile
import shutil
import zipfile
import logging
from pathlib import Path
from typing import Union

log = logging.getLogger(__name__)

# Add more archive extensions as needed (e.g., '.rar', '.7z').
# Non-zip formats may require additional libraries like patoolib.
SUPPORTED_ARCHIVES = {'.zip'}

def prepare_processing_workspace(input_path_str: Union[str, Path]) -> Path:
    """
    Prepares a temporary workspace for processing an asset source.

    Handles copying directory contents or extracting supported archives
    into a unique temporary directory.

    Args:
        input_path_str: The path (as a string or Path object) to the input
                        directory or archive file.

    Returns:
        The Path object representing the created temporary workspace directory.
        The caller is responsible for cleaning up this directory.

    Raises:
        FileNotFoundError: If the input_path does not exist.
        ValueError: If the input_path is not a directory or a supported archive type.
        zipfile.BadZipFile: If a zip file is corrupted.
        OSError: If there are issues creating the temp directory or copying files.
    """
    input_path = Path(input_path_str)
    log.info(f"Preparing workspace for input: {input_path}")

    if not input_path.exists():
        raise FileNotFoundError(f"Input path does not exist: {input_path}")

    try:
        temp_workspace_dir = tempfile.mkdtemp(prefix="asset_proc_")
        prepared_workspace_path = Path(temp_workspace_dir)
        log.info(f"Created temporary workspace: {prepared_workspace_path}")
    except OSError as e:
        log.error(f"Failed to create temporary directory: {e}")
        raise

    try:
        if input_path.is_dir():
            log.info(f"Input is a directory, copying contents to workspace: {input_path}")
            shutil.copytree(input_path, prepared_workspace_path, dirs_exist_ok=True)
        elif input_path.is_file() and input_path.suffix.lower() in SUPPORTED_ARCHIVES:
            log.info(f"Input is a supported archive ({input_path.suffix}), extracting to workspace: {input_path}")
            if input_path.suffix.lower() == '.zip':
                with zipfile.ZipFile(input_path, 'r') as zip_ref:
                    zip_ref.extractall(prepared_workspace_path)
            # Add elif blocks here for other archive types (e.g., using patoolib)
            else:
                # This case should ideally not be reached if SUPPORTED_ARCHIVES is correct
                raise ValueError(f"Archive type {input_path.suffix} marked as supported but no extraction logic defined.")
        else:
            raise ValueError(f"Unsupported input type: {input_path}. Must be a directory or a supported archive ({', '.join(SUPPORTED_ARCHIVES)}).")

        log.debug(f"Workspace preparation successful for: {input_path}")
        return prepared_workspace_path

    except (FileNotFoundError, ValueError, zipfile.BadZipFile, OSError, ImportError) as e:
        log.error(f"Error during workspace preparation for {input_path}: {e}. Cleaning up workspace.")
        if prepared_workspace_path.exists():
            try:
                shutil.rmtree(prepared_workspace_path)
                log.info(f"Cleaned up failed workspace: {prepared_workspace_path}")
            except OSError as cleanup_error:
                log.error(f"Failed to cleanup workspace {prepared_workspace_path} after error: {cleanup_error}")
        raise