import importlib.resources
import os
import sys
from pathlib import Path

if getattr(sys, "frozen", False) and (_MEIPASS := getattr(sys, "_MEIPASS", None)):
    _ROOT_DIR = Path(
        _MEIPASS
    ).parent.resolve()  # frozen executable root, contains the executable file
else:
    _ROOT_DIR = Path(
        __file__
    ).parent.parent.parent.parent.resolve()  # development project root


def get_root_dir() -> Path:
    """
    The root directory of the project. In development, this is the project root.
    In production (frozen by PyInstaller), this is the directory that holds the executable.
    The `logs` and `config.json` files are located in this directory. The `.env` file in this
    directory is also used for configuration in development and production.
    """
    return _ROOT_DIR


def get_resources_dir() -> Path:
    return get_root_dir() / "resources"


def get_resources_data_dir() -> Path:
    return get_resources_dir() / "data" / "v2"


def get_resources_assets_dir() -> Path:
    return get_resources_dir() / "assets"


def get_resources_images_dir() -> Path:
    return get_resources_dir() / "images"


def get_package_data_dir() -> Path:
    return (
        Path(str(importlib.resources.files("endfield_essence_recognizer")))
        / "data"
        / "v2"
    )


def get_bundled_static_data_dir() -> Path:
    resources_data_dir = get_resources_data_dir()
    if resources_data_dir.exists():
        return resources_data_dir
    return get_package_data_dir()


def get_config_path() -> Path:
    """Get the path to the config.json file in the root directory."""
    return get_root_dir() / "config.json"


def get_logs_dir() -> Path:
    """Get the path to the logs directory in the root directory."""
    return get_root_dir() / "logs"


def get_screenshots_dir() -> Path:
    """Get the path to the screenshots directory in the root directory."""
    return get_root_dir() / "screenshots"


def get_appdata_dir() -> Path:
    appdata = os.environ.get("APPDATA")
    if appdata:
        return Path(appdata).resolve() / "endfield-essence-recognizer"
    return get_root_dir() / ".appdata"


def get_static_data_override_dir() -> Path:
    return get_appdata_dir() / "data" / "v2"


def get_data_update_state_path() -> Path:
    return get_appdata_dir() / "data_update_state.json"


def get_scan_summary_state_path() -> Path:
    return get_appdata_dir() / "scan_summary_state.json"
