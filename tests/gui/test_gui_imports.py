import importlib
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from configuration import load_base_config

GUI_MODULES = [
    "gui.main_window",
    "gui.main_panel_widget",
    "gui.unified_view_model",
]


@pytest.mark.parametrize("module_name", GUI_MODULES)
def test_gui_modules_import_with_load_base_config(module_name):
    pytest.importorskip("PySide6")
    try:
        module = importlib.import_module(module_name)
    except ImportError as exc:
        if "PySide6" in str(exc) or "libGL" in str(exc):
            pytest.skip(f"Qt libraries not available: {exc}")
        raise
    load_fn = getattr(module, "load_base_config", None)
    assert callable(load_fn), f"{module_name} should expose load_base_config"
    data = load_fn()
    assert isinstance(data, dict)
    assert "ASSET_TYPE_DEFINITIONS" in data
    assert "FILE_TYPE_DEFINITIONS" in data


def test_load_base_config_returns_definitions():
    data = load_base_config()
    assert isinstance(data, dict)
    assert "ASSET_TYPE_DEFINITIONS" in data
    assert "FILE_TYPE_DEFINITIONS" in data
