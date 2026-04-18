from functools import lru_cache

from fastapi import Depends

from endfield_essence_recognizer.game_data.static_game_data import StaticGameData
from endfield_essence_recognizer.services.audio_service import (
    AudioService,
    build_audio_service_profile,
)
from endfield_essence_recognizer.services.data_update_service import DataUpdateService
from endfield_essence_recognizer.services.log_service import LogService
from endfield_essence_recognizer.services.scanner_service import ScannerService
from endfield_essence_recognizer.services.screenshot_service import ScreenshotService
from endfield_essence_recognizer.services.static_data_runtime import StaticDataRuntime
from endfield_essence_recognizer.services.static_data_service import StaticDataService
from endfield_essence_recognizer.services.system_service import SystemService

from .window import get_game_window_manager


@lru_cache
def get_audio_service() -> AudioService:
    """
    Get the AudioService singleton.
    """
    from .settings import default_user_setting_manager

    service = AudioService(build_audio_service_profile())
    service.set_enabled(
        default_user_setting_manager().get_user_setting_ref().enable_sound
    )
    return service


def sync_audio_service_enabled(enabled: bool) -> AudioService:
    service = get_audio_service()
    service.set_enabled(enabled)
    return service


@lru_cache
def get_scanner_service() -> ScannerService:
    return ScannerService(audio_service=get_audio_service())


@lru_cache
def get_log_service() -> LogService:
    return LogService()


@lru_cache
def get_system_service() -> SystemService:
    return SystemService(scanner_service=get_scanner_service())


@lru_cache
def get_screenshot_service() -> ScreenshotService:
    """
    Get the ScreenshotService singleton.
    """
    return ScreenshotService(get_game_window_manager())


@lru_cache
def get_static_data_runtime() -> StaticDataRuntime:
    return StaticDataRuntime()


def reload_static_data_runtime() -> StaticGameData:
    from endfield_essence_recognizer.core.recognition import (
        prepare_attribute_recognizer,
    )
    from endfield_essence_recognizer.dependencies.recognition import (
        get_attribute_recognizer_dep,
    )

    static_game_data = get_static_data_runtime().reload()
    prepare_attribute_recognizer.cache_clear()
    get_attribute_recognizer_dep.cache_clear()
    return static_game_data


@lru_cache
def get_data_update_service() -> DataUpdateService:
    return DataUpdateService(
        scanner_service=get_scanner_service(),
        apply_updates_callback=reload_static_data_runtime,
        static_data_runtime=get_static_data_runtime(),
    )


def get_static_game_data() -> StaticGameData:
    """
    Get the currently active StaticGameData snapshot.
    """
    return get_static_data_runtime().get_static_game_data()


def get_static_data_service(
    static_data: StaticGameData = Depends(get_static_game_data),
) -> StaticDataService:
    """
    Get a StaticDataService instance.

    StaticDataService is lightweight so it is ok to create a new
    instance per request.
    """
    return StaticDataService(static_data)
