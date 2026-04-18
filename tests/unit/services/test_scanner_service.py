import threading
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock

from endfield_essence_recognizer.schemas.scan_summary import (
    CustomTreasureSummaryState,
    ScanSummaryState,
)
from endfield_essence_recognizer.services.scanner_service import ScannerService


class FakeScanner:
    def __init__(
        self,
        counts: dict[str, int] | None = None,
        summary: ScanSummaryState | None = None,
    ) -> None:
        self._counts = counts or {}
        self._summary = summary
        self.started = threading.Event()
        self.block = threading.Event()
        self.execute_call_count = 0

    def execute(self, _stop_event) -> None:
        self.execute_call_count += 1
        self.started.set()
        self.block.wait()

    def get_weapon_essence_counts(self) -> dict[str, int]:
        return self._counts.copy()

    def get_scan_summary(self) -> ScanSummaryState | None:
        return (
            self._summary.model_copy(deep=True) if self._summary is not None else None
        )


def test_scanner_service_start_scan():
    scanner = FakeScanner()
    service = ScannerService()

    assert not service.is_running()
    service.start_scan(scanner_factory=lambda: scanner)

    assert scanner.started.wait(timeout=1.0)
    assert service.is_running()

    scanner.block.set()
    service.stop_scan()
    assert not service.is_running()


def test_scanner_service_toggle_scan():
    scanner = FakeScanner()
    service = ScannerService()

    service.toggle_scan(scanner_factory=lambda: scanner)
    assert scanner.started.wait(timeout=1.0)
    assert service.is_running()

    scanner.block.set()
    service.toggle_scan(scanner_factory=lambda: scanner)
    assert not service.is_running()
    assert service._stop_event.is_set()


def test_scanner_service_already_running():
    scanner = FakeScanner()
    service = ScannerService()

    service.start_scan(scanner_factory=lambda: scanner)
    assert scanner.started.wait(timeout=1.0)

    service.start_scan(scanner_factory=lambda: FakeScanner())

    assert scanner.execute_call_count == 1

    scanner.block.set()
    service.stop_scan()


def test_scanner_service_preserves_live_and_last_counts():
    scanner = FakeScanner(counts={"wpn_test": 2})
    service = ScannerService()

    service.start_scan(scanner_factory=lambda: scanner)
    assert scanner.started.wait(timeout=1.0)
    assert service.get_weapon_essence_counts() == {"wpn_test": 2}

    scanner.block.set()
    service._thread.join(timeout=1.0)  # type: ignore[union-attr]

    assert not service.is_running()
    assert service.get_weapon_essence_counts() == {"wpn_test": 2}


def test_scanner_service_loads_persisted_summary(monkeypatch, tmp_path: Path):
    summary_path = tmp_path / "scan_summary_state.json"
    summary = ScanSummaryState(
        scanned_at=datetime(2026, 4, 10, 12, 0, 0),
        total_essence_count=5,
        weapon_counts={"weapon_a": 2},
        weapon_best_level_combos={"weapon_a": [(2, 1, 1)]},
        custom_treasures=[
            CustomTreasureSummaryState(
                key="A|B|C",
                attribute="A",
                secondary="B",
                skill="C",
                count=1,
                best_level_combos=[(2, 1, 1)],
            )
        ],
    )
    summary_path.write_text(summary.model_dump_json(indent=2), encoding="utf-8")
    monkeypatch.setattr(
        "endfield_essence_recognizer.services.scanner_service.get_scan_summary_state_path",
        lambda: summary_path,
    )

    service = ScannerService()

    assert service.get_weapon_essence_counts() == {"weapon_a": 2}
    loaded_summary = service.get_last_scan_summary()
    assert loaded_summary is not None
    assert loaded_summary.total_essence_count == 5
    assert loaded_summary.custom_treasures[0].best_level_combos == [(2, 1, 1)]


def test_scanner_service_persists_summary_after_scan(monkeypatch, tmp_path: Path):
    summary_path = tmp_path / "scan_summary_state.json"
    monkeypatch.setattr(
        "endfield_essence_recognizer.services.scanner_service.get_scan_summary_state_path",
        lambda: summary_path,
    )
    summary = ScanSummaryState(
        scanned_at=datetime(2026, 4, 10, 12, 0, 0),
        total_essence_count=7,
        weapon_counts={"weapon_a": 3},
        weapon_best_level_combos={"weapon_a": [(2, 1, 1), (2, 1, 1)]},
        custom_treasures=[
            CustomTreasureSummaryState(
                key="A|B|C",
                attribute="A",
                secondary="B",
                skill="C",
                count=2,
                best_level_combos=[(2, 1, 1), (2, 1, 1)],
            )
        ],
    )
    scanner = FakeScanner(counts={"weapon_a": 3}, summary=summary)
    service = ScannerService()

    service.start_scan(scanner_factory=lambda: scanner)
    assert scanner.started.wait(timeout=1.0)

    scanner.block.set()
    service._thread.join(timeout=1.0)  # type: ignore[union-attr]

    assert summary_path.exists()
    saved = ScanSummaryState.model_validate_json(
        summary_path.read_text(encoding="utf-8")
    )
    assert saved.total_essence_count == 7
    assert saved.weapon_counts == {"weapon_a": 3}
    assert saved.custom_treasures[0].count == 2


def test_scanner_service_logs_persisted_summary(monkeypatch, tmp_path: Path):
    summary_path = tmp_path / "scan_summary_state.json"
    summary = ScanSummaryState(
        scanned_at=datetime(2026, 4, 10, 12, 0, 0),
        total_essence_count=5,
        weapon_counts={"weapon_a": 2},
        weapon_best_level_combos={"weapon_a": [(2, 1, 1), (2, 1, 1)]},
        custom_treasures=[],
    )
    summary_path.write_text(summary.model_dump_json(indent=2), encoding="utf-8")
    monkeypatch.setattr(
        "endfield_essence_recognizer.services.scanner_service.get_scan_summary_state_path",
        lambda: summary_path,
    )
    messages: list[str] = []

    class FakeLogger:
        def opt(self, **_kwargs):
            return self

        def success(self, message, *args):
            messages.append(message.format(*args) if args else message)

    monkeypatch.setattr(
        "endfield_essence_recognizer.services.scanner_service.logger", FakeLogger()
    )
    static_game_data = MagicMock()
    weapon = MagicMock()
    weapon.name = "TestWeapon"
    weapon.rarity = 6
    weapon.weapon_type = "sword"
    weapon_type = MagicMock()
    weapon_type.name = "Sword"
    static_game_data.get_weapon.return_value = weapon
    static_game_data.get_weapon_type.return_value = weapon_type
    static_game_data.get_rarity_color.return_value = "#FFD700"

    service = ScannerService()
    service.log_last_scan_summary(static_game_data)

    assert any("上次扫描时间" in msg for msg in messages)
    assert any("TestWeapon" in msg for msg in messages)
    assert any("最优 <green><bold>+2/+1/+1（2次）" in msg for msg in messages)
