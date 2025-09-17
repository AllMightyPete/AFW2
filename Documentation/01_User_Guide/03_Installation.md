# User Guide: Installation

This document details the requirements and steps for installing the Asset Processor Tool.

## Requirements

*   Python 3.8 +
*   Required Python Packages (see `requirements.txt`):
    *   `opencv-python` (image processing)
    *   `numpy` (numerical operations)
    *   `py7zr` (7z archive support)
    *   `rarfile` (RAR archive support)
    *   `PySide6` (for the GUI only)
    *   `watchdog` (for the directory monitor)
*   Optional Python Packages:
    *   `OpenEXR` (improved `.exr` handling, recommended if processing EXR sources)
*   **Blender:** A working installation is required for optional Blender integration. Configure the path in `config.py` or ensure it's in the system PATH.

## Installation Steps

1.  Navigate to the project root directory in your terminal.
2.  Install core dependencies using pip:

    ```bash
    pip install -r requirements.txt
    ```

3.  If you plan to use the GUI, ensure `PySide6` is installed. It might be included in `requirements.txt`, or install separately:

    ```bash
    pip install PySide6
    ```

4.  If you plan to use the directory monitor script, ensure `watchdog` is installed. It might be included in `requirements.txt`, or install separately:

    ```bash
    pip install watchdog