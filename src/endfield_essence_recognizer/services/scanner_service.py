from __future__ import annotations

import threading
from typing import TYPE_CHECKING

from endfield_essence_recognizer.core.path import get_scan_summary_state_path
from endfield_essence_recognizer.core.scanner.summary import (
    iter_scan_summary_log_messages,
)
from endfield_essence_recognizer.schemas.scan_summary import ScanSummaryState
from endfield_essence_recognizer.utils.log import logger

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

    from endfield_essence_recognizer.core.interfaces import AutomationEngine
    from endfield_essence_recognizer.game_data.static_game_data import StaticGameData
    from endfield_essence_recognizer.services.audio_service import AudioService


class ScannerService:
    """管理后台扫描线程的生命周期。"""

    def __init__(
        self,
        audio_service: AudioService | None = None,
    ) -> None:
        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        self._lock = threading.RLock()
        self._audio_service = audio_service
        self._current_scanner: AutomationEngine | None = None
        self._last_weapon_essence_counts: dict[str, int] = {}
        self._last_scan_summary: ScanSummaryState | None = (
            self._load_scan_summary_state()
        )
        if self._last_scan_summary is not None:
            self._last_weapon_essence_counts = (
                self._last_scan_summary.weapon_counts.copy()
            )
        self._idle_callbacks: list[Callable[[], None]] = []

    def _extract_weapon_essence_counts(
        self, scanner: AutomationEngine | None
    ) -> dict[str, int] | None:
        get_counts = getattr(scanner, "get_weapon_essence_counts", None)
        if not callable(get_counts):
            return None

        counts = get_counts()
        if isinstance(counts, dict):
            return dict(counts)
        return None

    def _extract_scan_summary(
        self, scanner: AutomationEngine | None
    ) -> ScanSummaryState | None:
        get_scan_summary = getattr(scanner, "get_scan_summary", None)
        if not callable(get_scan_summary):
            return None

        summary = get_scan_summary()
        if isinstance(summary, ScanSummaryState):
            return summary
        return None

    def _get_scan_summary_state_path(self) -> Path:
        return get_scan_summary_state_path()

    def _load_scan_summary_state(self) -> ScanSummaryState | None:
        path = self._get_scan_summary_state_path()
        try:
            if not path.exists():
                return None
            return ScanSummaryState.model_validate_json(
                path.read_text(encoding="utf-8")
            )
        except Exception as exc:
            logger.warning("读取扫描汇总缓存失败：{}", exc)
            return None

    def _save_scan_summary_state(self, summary: ScanSummaryState) -> None:
        path = self._get_scan_summary_state_path()
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(summary.model_dump_json(indent=2), encoding="utf-8")
        except Exception as exc:
            logger.warning("保存扫描汇总缓存失败：{}", exc)

    def _run_scanner(self, scanner: AutomationEngine) -> None:
        try:
            scanner.execute(self._stop_event)
        except Exception as exc:
            logger.exception(f"扫描线程执行异常：{exc}")
        finally:
            counts = self._extract_weapon_essence_counts(scanner)
            summary = self._extract_scan_summary(scanner)
            with self._lock:
                if counts is not None:
                    self._last_weapon_essence_counts = counts
                if summary is not None:
                    self._last_scan_summary = summary
                    self._last_weapon_essence_counts = summary.weapon_counts.copy()
                    self._save_scan_summary_state(summary)
                if self._current_scanner is scanner:
                    self._current_scanner = None
            self._notify_idle_callbacks()

    def register_idle_callback(self, callback: Callable[[], None]) -> None:
        with self._lock:
            self._idle_callbacks.append(callback)

    def _notify_idle_callbacks(self) -> None:
        with self._lock:
            callbacks = list(self._idle_callbacks)

        for callback in callbacks:
            try:
                callback()
            except Exception as exc:
                logger.exception(f"执行空闲回调失败：{exc}")

    def start_scan(self, scanner_factory: Callable[[], AutomationEngine]) -> None:
        with self._lock:
            if self.is_running():
                logger.warning("扫描已在进行中。")
                return

            if self._thread is not None:
                self._thread.join()

            logger.debug("准备启动扫描线程...")
            self._stop_event.clear()
            scanner = scanner_factory()
            self._current_scanner = scanner

            self._thread = threading.Thread(
                target=self._run_scanner,
                args=(scanner,),
                daemon=True,
                name="ScannerThread",
            )
            logger.debug("Starting scanner thread.")
            self._thread.start()

            if self._audio_service:
                self._audio_service.play_enable()

    def stop_scan(self) -> None:
        with self._lock:
            if not self.is_running():
                logger.warning("当前没有正在运行的扫描。")
                return

            logger.debug("正在请求停止扫描线程...")
            self._stop_event.set()
            thread = self._thread

        if thread is not None:
            thread.join()

        with self._lock:
            logger.debug("Scanner thread joined.")
            self._thread = None

            if self._audio_service:
                self._audio_service.play_disable()

    def is_running(self) -> bool:
        with self._lock:
            return self._thread is not None and self._thread.is_alive()

    def get_weapon_essence_counts(self) -> dict[str, int]:
        with self._lock:
            counts = self._extract_weapon_essence_counts(self._current_scanner)
            if (
                counts is not None
                and self._thread is not None
                and self._thread.is_alive()
            ):
                return counts
            return self._last_weapon_essence_counts.copy()

    def get_last_scan_summary(self) -> ScanSummaryState | None:
        with self._lock:
            if self._thread is not None and self._thread.is_alive():
                live_summary = self._extract_scan_summary(self._current_scanner)
                if live_summary is not None:
                    return live_summary

            if self._last_scan_summary is None:
                return None
            return self._last_scan_summary.model_copy(deep=True)

    def log_last_scan_summary(self, static_game_data: StaticGameData) -> None:
        summary = self.get_last_scan_summary()
        if summary is None:
            return

        for message in iter_scan_summary_log_messages(
            static_game_data,
            summary,
            include_scanned_at=True,
        ):
            logger.opt(colors=True).success(message)

    def toggle_scan(self, scanner_factory: Callable[[], AutomationEngine]) -> None:
        if self.is_running():
            self.stop_scan()
        else:
            self.start_scan(scanner_factory)
