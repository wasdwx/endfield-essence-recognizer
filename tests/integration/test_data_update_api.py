from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from endfield_essence_recognizer.dependencies import get_data_update_service
from endfield_essence_recognizer.schemas.data_update import (
    DataSource,
    DataUpdateActionResponse,
    DataUpdateStatusResponse,
)
from endfield_essence_recognizer.server import app


@pytest.fixture
def mock_data_update_service():
    service = MagicMock()
    base_status = DataUpdateStatusResponse(
        current_data_source=DataSource.BUNDLED,
        applied_version=None,
        pending_version=None,
        last_checked_version="remote-sha",
        update_available=True,
        pending_apply=False,
        last_checked_at=None,
        last_downloaded_at=None,
        last_applied_at=None,
        last_error=None,
    )
    service.get_status.return_value = base_status
    service.check_for_updates.return_value = DataUpdateActionResponse(
        status=base_status,
        message="检测到新的武器数据，可以开始下载。",
        downloaded=False,
        applied=False,
    )
    service.download_updates.return_value = DataUpdateActionResponse(
        status=DataUpdateStatusResponse(
            current_data_source=DataSource.OVERRIDE,
            applied_version="remote-sha",
            pending_version=None,
            last_checked_version="remote-sha",
            update_available=False,
            pending_apply=False,
            last_checked_at=None,
            last_downloaded_at=None,
            last_applied_at=None,
            last_error=None,
        ),
        message="武器数据已更新并立即生效。",
        downloaded=True,
        applied=True,
    )
    return service


@pytest.fixture
def client(mock_data_update_service):
    app.dependency_overrides[get_data_update_service] = lambda: mock_data_update_service

    with TestClient(app) as test_client:
        yield test_client

    app.dependency_overrides.clear()


def test_get_data_update_status(client, mock_data_update_service):
    response = client.get("/api/data_update/status")

    assert response.status_code == 200
    assert response.json() == {
        "currentDataSource": "bundled",
        "appliedVersion": None,
        "pendingVersion": None,
        "lastCheckedVersion": "remote-sha",
        "updateAvailable": True,
        "pendingApply": False,
        "lastCheckedAt": None,
        "lastDownloadedAt": None,
        "lastAppliedAt": None,
        "lastError": None,
    }
    mock_data_update_service.get_status.assert_called_once()


def test_check_data_update(client, mock_data_update_service):
    response = client.post("/api/data_update/check")

    assert response.status_code == 200
    assert response.json()["message"] == "检测到新的武器数据，可以开始下载。"
    assert response.json()["downloaded"] is False
    assert response.json()["applied"] is False
    assert response.json()["status"]["updateAvailable"] is True
    mock_data_update_service.check_for_updates.assert_called_once()


def test_download_data_update(client, mock_data_update_service):
    response = client.post("/api/data_update/download")

    assert response.status_code == 200
    assert response.json()["message"] == "武器数据已更新并立即生效。"
    assert response.json()["downloaded"] is True
    assert response.json()["applied"] is True
    assert response.json()["status"]["currentDataSource"] == "override"
    assert response.json()["status"]["pendingApply"] is False
    mock_data_update_service.download_updates.assert_called_once()
