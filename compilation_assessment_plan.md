# Plan: Assessing Compilation of Asset Processor with PyInstaller and Cython

## Objective

To assess the feasibility and create a plan for compiling the Asset Processor project into standalone executables using PyInstaller, incorporating Cython for general speedup and source code obfuscation. A key requirement is to maintain user access to, and the ability to modify, configuration files (like `user_settings.json`, `asset_type_definitions.json`, etc.) and `Preset` files post-compilation.

---

## Phase 1: Initial Analysis & Information Gathering

*   **Project Dependencies (from [`requirements.txt`](requirements.txt:1)):**
    *   `opencv-python`
    *   `numpy`
    *   `openexr`
    *   `PySide6`
    *   `py7zr`
    *   `rarfile`
    *   `requests`
    *   *Note: `PySide6`, `opencv-python`, and `openexr` may require special handling with PyInstaller (e.g., hidden imports, hooks).*
*   **Configuration Loading (based on [`configuration.py`](configuration.py:1)):**
    *   Configuration files (`app_settings.json`, `llm_settings.json`, `asset_type_definitions.json`, `file_type_definitions.json`, `user_settings.json`, `suppliers.json`) are loaded from a `config/` subdirectory relative to [`configuration.py`](configuration.py:1).
    *   Preset files are loaded from a `Presets/` subdirectory relative to [`configuration.py`](configuration.py:1).
    *   `BASE_DIR` is `Path(__file__).parent`, which will refer to the bundled location in a PyInstaller build.
    *   [`user_settings.json`](configuration.py:16) is designed for overrides and is a candidate for external management.
    *   Saving functions write back to these relative paths, which needs adaptation.
*   **Potential Cython Candidates:**
    *   Modules within the `processing/` directory.
    *   Specifically: `processing/utils/image_processing_utils.py` and individual stage files in `processing/pipeline/stages/` (e.g., `alpha_extraction_to_mask.py`, `gloss_to_rough_conversion.py`, etc.).
    *   Other modules (e.g., `processing/pipeline/orchestrator.py`) could be Cythonized primarily for obfuscation.
*   **User-Accessible Files (Defaults):**
    *   The `config/` directory (containing `app_settings.json`, `asset_type_definitions.json`, `file_type_definitions.json`, `llm_settings.json`, `suppliers.json`).
    *   The `Presets/` directory and its contents.

---

## Phase 2: Strategy Development

1.  **Cython Strategy:**
    *   **Build Integration:** Utilize a `setup.py` script with `setuptools` and `Cython.Build.cythonize` to compile `.py` files into C extensions (`.pyd` on Windows, `.so` on Linux/macOS).
    *   **Candidate Prioritization:** Focus on `processing/` modules for performance gains and obfuscation.
    *   **Compatibility & Challenges:**
        *   GUI modules (PySide6) are generally left as Python.
        *   Ensure compatibility with OpenCV, NumPy, and OpenEXR.
        *   Address potential issues with highly dynamic Python code.
        *   Consider iterative conversion to `.pyx` files with C-style type annotations for maximum performance in identified hot spots.
    *   **Obfuscation:** The primary goal for many modules might be obfuscation rather than pure speedup.

2.  **PyInstaller Strategy:**
    *   **Bundle Type:** One-directory bundle (`--onedir`) is recommended for easier debugging and data file management.
    *   **Data Files (`.spec` file `datas` section):**
        *   Bundle default `config/` directory (containing `app_settings.json`, `asset_type_definitions.json`, `file_type_definitions.json`, `llm_settings.json`, `suppliers.json`).
        *   Bundle default `Presets/` directory.
        *   Include any other necessary GUI assets (icons, etc.).
        *   Consider bundling the `blender_addon/` if it's to be deployed with the app.
    *   **Hidden Imports & Hooks (`.spec` file):**
        *   Add explicit `hiddenimports` for `PySide6`, `opencv-python`, `openexr`, and any other problematic libraries.
        *   Utilize or create PyInstaller hooks if necessary.
    *   **Console Window:** Disable for GUI application (`console=False`).

3.  **User-Accessible Files & First-Time Setup Strategy:**
    *   **First-Run Detection:** Application checks for a marker file or stored configuration path.
    *   **First-Time Setup UI (PySide6 Dialog):**
        *   **Configuration Location Choice:**
            *   Option A (Recommended): Store in user profile (e.g., `Documents/AssetProcessor` or `AppData/Roaming/AssetProcessor`).
            *   Option B (Advanced): User chooses a custom folder.
        *   The application copies default `config/` (excluding `app_settings.json` but including other definition files) and `Presets/` to the chosen location.
        *   The chosen path is saved.
        *   **Key Application Settings Configuration (saved to `user_settings.json` in user's chosen location):**
            *   Default Library Output Path (`OUTPUT_BASE_DIR`).
            *   Asset Structure (`OUTPUT_DIRECTORY_PATTERN`).
            *   Image Output Formats (`OUTPUT_FORMAT_16BIT_PRIMARY`, `OUTPUT_FORMAT_16BIT_FALLBACK`, `OUTPUT_FORMAT_8BIT`).
            *   JPG Threshold (`RESOLUTION_THRESHOLD_FOR_JPG`).
            *   Blender Paths (`DEFAULT_NODEGROUP_BLEND_PATH`, `DEFAULT_MATERIALS_BLEND_PATH`, `BLENDER_EXECUTABLE_PATH`).
    *   **Configuration Loading Logic Modification ([`configuration.py`](configuration.py:1)):**
        *   `BASE_DIR` for user-modifiable files will point to the user-chosen location.
        *   `app_settings.json` (master defaults) always loaded from the bundle.
        *   `user_settings.json` loaded from the user-chosen location, containing overrides.
        *   Other definition files and `Presets` loaded from the user-chosen location, with a fallback/re-copy mechanism from bundled defaults if missing.
    *   **Saving Logic Modification ([`configuration.py`](configuration.py:1)):**
        *   All configuration saving functions will write to the user-chosen configuration location. Bundled defaults remain read-only post-installation.

---

## Phase 3: Outline of Combined Build Process

1.  **Environment Setup (Developer):** Install Python, Cython, PyInstaller, and project dependencies.
2.  **Cythonization (`setup.py`):**
    *   Create `setup.py` using `setuptools` and `Cython.Build.cythonize`.
    *   List `.py` files/modules for compilation (e.g., `processing.utils.image_processing_utils`, `processing.pipeline.stages.*`).
    *   Include `numpy.get_include()` if Cython files use NumPy C-API.
    *   Run `python setup.py build_ext --inplace` to generate `.pyd`/`.so` files.
3.  **PyInstaller Packaging (`.spec` file):**
    *   Generate initial `AssetProcessor.spec` with `pyinstaller --name AssetProcessor main.py`.
    *   Modify `.spec` file:
        *   `datas`: Add default `config/` and `Presets/` directories, and other assets.
        *   `hiddenimports`: List modules for `PySide6`, `opencv-python`, etc.
        *   `excludes`: Optionally exclude original `.py` files for Cythonized modules.
        *   Set `onedir = True`, `onefile = False`, `console = False`.
    *   Run `pyinstaller AssetProcessor.spec` to create `dist/AssetProcessor`.
4.  **Post-Build Steps (Optional):**
    *   Clean up original `.py` files from `dist/` if obfuscation is paramount.
    *   Archive `dist/AssetProcessor` for distribution (ZIP, installer).

---

## Phase 4: Distribution Structure

**Inside `dist/AssetProcessor/` (Distribution Package):**

*   `AssetProcessor.exe` (or platform equivalent)
*   Core Python and library dependencies (DLLs/SOs)
*   Cythonized modules (`.pyd`/`.so` files, e.g., `processing/utils/image_processing_utils.pyd`)
*   Non-Cythonized Python modules (`.pyc` files)
*   Bundled default `config/` directory (with `app_settings.json`, `asset_type_definitions.json`, etc.)
*   Bundled default `Presets/` directory (with `_template.json`, `Dinesen.json`, etc.)
*   Other GUI assets (icons, etc.)
*   Potentially `blender_addon/` files if bundled.

**User's Configuration Directory (e.g., `Documents/AssetProcessor/`, created on first run):**

*   `user_settings.json` (user's choices for paths, formats, etc.)
*   Copied `config/` directory (for user modification of `asset_type_definitions.json`, etc.)
*   Copied `Presets/` directory (for user modification/additions)
*   Marker file for first-time setup choice.

---

## Phase 5: Plan for Testing & Validation

1.  **Core Functionality:** Test GUI operations, Directory Monitor, CLI (if applicable).
2.  **Configuration System:**
    *   Verify first-time setup UI, config location choice, copying of defaults.
    *   Confirm loading from and saving to the user's chosen config location.
    *   Test modification of user configs and application's reflection of changes.
3.  **Dependency Checks:** Ensure bundled libraries (PySide6, OpenCV) function correctly.
4.  **Performance (Cython):** Basic comparison of critical operations (Python vs. Cythonized).
5.  **Obfuscation (Cython):** Verify absence of original `.py` files for Cythonized modules in distribution (if desired) and that `.pyd`/`.so` files are used.
6.  **Cross-Platform Testing:** Repeat build and test process on all target OS.

---

## Phase 6: Documentation Outline

1.  **Developer/Build Documentation:**
    *   Build environment setup.
    *   `setup.py` (Cython) and `pyinstaller` command usage.
    *   Structure of `setup.py` and `.spec` file, key configurations.
    *   Troubleshooting common build issues.
2.  **User Documentation:**
    *   First-time setup guide (config location, initial settings).
    *   Managing user-specific configurations and presets (location, backup).
    *   How to reset to default configurations.

---

## Phase 7: Risk Assessment & Mitigation (Brief)

*   **Risk:** Cython compilation issues.
    *   **Mitigation:** Incremental compilation, selective Cythonization.
*   **Risk:** PyInstaller packaging complexities.
    *   **Mitigation:** Thorough testing, community hooks, iterative `.spec` refinement.
*   **Risk:** Logic errors in new configuration loading/saving.
    *   **Mitigation:** Careful coding, detailed testing of config pathways.
*   **Risk:** Cython performance not meeting expectations.
    *   **Mitigation:** Profile Python code first; focus Cython on CPU-bound loops.
*   **Risk:** Increased build complexity.
    *   **Mitigation:** Automate build steps with scripts.