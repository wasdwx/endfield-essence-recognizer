from datetime import datetime
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from endfield_essence_recognizer.dependencies import (
    get_delivery_claimer_engine_dep,
    get_one_time_recognition_engine_dep,
    get_scanner_engine_dep,
    get_scanner_service,
    get_static_game_data,
    require_game_or_webview_is_active,
    require_game_window_exists,
)
from endfield_essence_recognizer.schemas.scan_summary import (
    CustomTreasureSummaryState,
    ScanSummaryState,
)
from endfield_essence_recognizer.server import app
from endfield_essence_recognizer.services.scanner_service import ScannerService


@pytest.fixture
def mock_scanner_service():
    """Mock ScannerService to avoid starting real threads."""
    service = ScannerService()
    service.start_scan = MagicMock()
    service.stop_scan = MagicMock()
    service.toggle_scan = MagicMock()
    service.is_running = MagicMock(return_value=False)
    service.get_weapon_essence_counts = MagicMock(return_value={"wpn_test": 3})
    service.get_last_scan_summary = MagicMock(return_value=None)
    return service


@pytest.fixture
def client(mock_scanner_service):
    """FastAPI TestClient with overridden dependencies."""
    app.dependency_overrides[get_scanner_service] = lambda: mock_scanner_service
    # Mock engines to avoid real initialization
    # use explicit lambdas to avoid fastapi caching MagicMock instance
    app.dependency_overrides[get_scanner_engine_dep] = lambda: MagicMock()
    app.dependency_overrides[get_one_time_recognition_engine_dep] = lambda: MagicMock()
    app.dependency_overrides[get_delivery_claimer_engine_dep] = lambda: MagicMock()

    # Bypass window checks
    app.dependency_overrides[require_game_window_exists] = lambda: None
    app.dependency_overrides[require_game_or_webview_is_active] = lambda: None
    static_game_data = MagicMock()
    static_game_data.get_rarity_color.return_value = "#FFD700"

    def get_weapon(weapon_id: str):
        weapon = MagicMock()
        weapon.name = "TestWeapon" if weapon_id == "wpn_test" else weapon_id
        weapon.rarity = 6
        weapon.weapon_type = "sword"
        return weapon

    static_game_data.get_weapon.side_effect = get_weapon
    weapon_type = MagicMock()
    weapon_type.name = "Sword"
    static_game_data.get_weapon_type.return_value = weapon_type
    static_game_data.get_stat.side_effect = lambda stat_id: type(
        "Stat",
        (),
        {"name": {"A": "攻击提升", "B": "物伤提升", "C": "技巧"}.get(stat_id, stat_id)},
    )()
    app.dependency_overrides[get_static_game_data] = lambda: static_game_data

    with TestClient(app) as client:
        yield client
    app.dependency_overrides.clear()


def test_recognize_once_endpoint(client, mock_scanner_service):
    """Test POST /api/recognize_once."""
    response = client.post("/api/recognize_once")
    assert response.status_code == 200
    assert mock_scanner_service.start_scan.called


def test_start_scanning_endpoint(client, mock_scanner_service):
    """Test POST /api/start_scanning."""
    response = client.post("/api/start_scanning")
    # This is the original endpoint used by the frontend
    assert response.status_code == 200
    assert mock_scanner_service.toggle_scan.called


def test_toggle_scanning_essence(client, mock_scanner_service):
    """Test POST /api/toggle_scanning for essence."""
    response = client.post("/api/toggle_scanning", json={"task_type": "essence"})
    assert response.status_code == 200
    assert mock_scanner_service.toggle_scan.called


def test_toggle_scanning_delivery(client, mock_scanner_service):
    """Test POST /api/toggle_scanning for delivery_claim."""
    response = client.post("/api/toggle_scanning", json={"task_type": "delivery_claim"})
    assert response.status_code == 200
    assert mock_scanner_service.toggle_scan.called


def test_toggle_scanning_invalid(client):
    """Test POST /api/toggle_scanning with invalid task type."""
    response = client.post("/api/toggle_scanning", json={"task_type": "invalid"})
    assert response.status_code == 422


def test_get_weapon_essence_counts(client, mock_scanner_service):
    response = client.get("/api/weapon_essence_counts")

    assert response.status_code == 200
    assert response.json() == {"wpn_test": 3}
    mock_scanner_service.get_weapon_essence_counts.assert_called_once()


def test_get_scanning_status(client, mock_scanner_service):
    mock_scanner_service.is_running.return_value = True

    response = client.get("/api/scanning_status")

    assert response.status_code == 200
    assert response.json() == {"is_running": True}


def test_get_last_scan_summary(client, mock_scanner_service):
    mock_scanner_service.get_last_scan_summary.return_value = ScanSummaryState(
        scanned_at=datetime(2026, 4, 10, 12, 0, 0),
        total_essence_count=5,
        weapon_counts={"wpn_test": 3},
        weapon_best_level_combos={"wpn_test": [(2, 1, 1), (2, 1, 1)]},
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

    response = client.get("/api/last_scan_summary")

    assert response.status_code == 200
    data = response.json()
    assert data["total_essence_count"] == 5
    assert data["weapons"][0]["weapon_id"] == "wpn_test"
    assert data["weapons"][0]["best_levels_text"] == "+2/+1/+1（2次）"
    assert data["custom_treasures"][0]["label"] == "攻击提升 / 物伤提升 / 技巧"
    assert data["custom_treasures"][0]["best_levels_text"] == "+2/+1/+1（2次）"
