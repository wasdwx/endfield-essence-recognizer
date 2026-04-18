from __future__ import annotations

from threading import RLock
from typing import TYPE_CHECKING

from endfield_essence_recognizer.core.path import (
    get_bundled_static_data_dir,
    get_static_data_override_dir,
)
from endfield_essence_recognizer.game_data.static_game_data import StaticGameData
from endfield_essence_recognizer.schemas.data_update import DataSource

if TYPE_CHECKING:
    from pathlib import Path


class StaticDataRuntime:
    """Own the currently active static game data snapshot."""

    def __init__(
        self,
        bundled_root: Path | None = None,
        override_root: Path | None = None,
    ) -> None:
        self._bundled_root = bundled_root or get_bundled_static_data_dir()
        self._override_root = override_root or get_static_data_override_dir()
        self._lock = RLock()
        self._current_data_source = DataSource.BUNDLED
        self._static_game_data = self._load_static_game_data()

    def get_static_game_data(self) -> StaticGameData:
        with self._lock:
            return self._static_game_data

    def reload(self) -> StaticGameData:
        with self._lock:
            self._static_game_data = self._load_static_game_data()
            return self._static_game_data

    def get_current_data_source(self) -> DataSource:
        with self._lock:
            return self._current_data_source

    def _load_static_game_data(self) -> StaticGameData:
        if self._override_files_exist():
            self._current_data_source = DataSource.OVERRIDE
            return StaticGameData(self._override_root, fallback_root=self._bundled_root)
        self._current_data_source = DataSource.BUNDLED
        return StaticGameData(self._bundled_root)

    def _override_files_exist(self) -> bool:
        return (self._override_root / "Weapon.json").is_file() and (
            self._override_root / "WeaponType.json"
        ).is_file()
