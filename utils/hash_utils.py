import hashlib
import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

def calculate_sha256(file_path: Path) -> Optional[str]:
    """
    Calculates the SHA-256 hash of a file.

    Args:
        file_path: The path to the file.

    Returns:
        The SHA-256 hash as a hexadecimal string, or None if an error occurs.
    """
    if not isinstance(file_path, Path):
        try:
            file_path = Path(file_path)
        except TypeError:
            logger.error(f"Invalid file path type: {type(file_path)}. Expected Path object or string.")
            return None

    if not file_path.is_file():
        logger.error(f"File not found or is not a regular file: {file_path}")
        return None

    sha256_hash = hashlib.sha256()
    buffer_size = 65536  # Read in 64k chunks

    try:
        with open(file_path, "rb") as f:
            while True:
                data = f.read(buffer_size)
                if not data:
                    break
                sha256_hash.update(data)
        return sha256_hash.hexdigest()
    except IOError as e:
        logger.error(f"Error reading file {file_path}: {e}")
        return None
    except Exception as e:
        logger.error(f"An unexpected error occurred while hashing {file_path}: {e}")
        return None