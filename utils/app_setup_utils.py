import os
import sys
import platform

def get_app_data_dir():
    """
    Gets the OS-specific application data directory for Asset Processor.
    Uses standard library methods as appdirs is not available.
    """
    app_name = "AssetProcessor"
    if platform.system() == "Windows":
        # On Windows, use APPDATA environment variable
        app_data_dir = os.path.join(os.environ.get("APPDATA", "~"), app_name)
    elif platform.system() == "Darwin":
        # On macOS, use ~/Library/Application Support
        app_data_dir = os.path.join("~", "Library", "Application Support", app_name)
    else:
        # On Linux and other Unix-like systems, use ~/.config
        app_data_dir = os.path.join("~", ".config", app_name)

    # Expand the user home directory symbol if present
    return os.path.expanduser(app_data_dir)

def get_persistent_config_path_file():
    """
    Gets the full path to the file storing the user's chosen config directory.
    """
    app_data_dir = get_app_data_dir()
    # Ensure the app data directory exists
    os.makedirs(app_data_dir, exist_ok=True)
    return os.path.join(app_data_dir, "asset_processor_user_root.txt")

def read_saved_user_config_path():
    """
    Reads the saved user config path from the persistent file.
    Returns the path string or None if the file doesn't exist or is empty.
    """
    path_file = get_persistent_config_path_file()
    if os.path.exists(path_file):
        try:
            with open(path_file, "r", encoding="utf-8") as f:
                saved_path = f.read().strip()
                if saved_path:
                    return saved_path
        except IOError:
            # Handle potential file reading errors
            pass
    return None

def save_user_config_path(user_config_path):
    """
    Saves the user's chosen config path to the persistent file.
    """
    path_file = get_persistent_config_path_file()
    try:
        with open(path_file, "w", encoding="utf-8") as f:
            f.write(user_config_path)
    except IOError:
        # Handle potential file writing errors
        print(f"Error saving user config path to {path_file}", file=sys.stderr)

def get_first_run_marker_file(user_config_path):
    """
    Gets the full path to the first-run marker file within the user config directory.
    """
    return os.path.join(user_config_path, ".first_run_complete")