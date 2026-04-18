import json
from pathlib import Path

import httpx

from endfield_essence_recognizer.schemas.data_update import DataSource
from endfield_essence_recognizer.services.data_update_service import DataUpdateService
from endfield_essence_recognizer.services.static_data_runtime import StaticDataRuntime


class _FakeScannerService:
    def __init__(self, running: bool = False):
        self._running = running
        self._callbacks = []

    def is_running(self) -> bool:
        return self._running

    def register_idle_callback(self, callback):
        self._callbacks.append(callback)

    def finish(self):
        self._running = False
        for callback in list(self._callbacks):
            callback()


def _write_data_root(
    root: Path,
    *,
    weapon_name: str,
    weapon_type_name: str = "Sword",
) -> None:
    root.mkdir(parents=True, exist_ok=True)
    weapon_data = {
        "weapon_1": {
            "weapon_id": "weapon_1",
            "name": weapon_name,
            "weapon_type": "SWORD",
            "rarity": 4,
            "icon_id": "icon_1",
            "stat1_id": "stat_a",
            "stat2_id": "stat_b",
            "stat3_id": None,
        }
    }
    (root / "Weapon.json").write_text(json.dumps(weapon_data), encoding="utf-8")

    stat_data = {
        "stat_a": {"stat_id": "stat_a", "name": "Stat A", "type": "ATTRIBUTE"},
        "stat_b": {"stat_id": "stat_b", "name": "Stat B", "type": "SECONDARY"},
    }
    (root / "EssenceStat.json").write_text(json.dumps(stat_data), encoding="utf-8")

    type_data = {
        "SWORD": {
            "weapon_type_id": "SWORD",
            "name": weapon_type_name,
            "wiki_group_id": "group_1",
            "icon_id": "icon_t1",
            "sort_order": 1,
        }
    }
    (root / "WeaponType.json").write_text(json.dumps(type_data), encoding="utf-8")

    rarity_data = {"4": {"color": "#9452FA"}}
    (root / "RarityColor.json").write_text(json.dumps(rarity_data), encoding="utf-8")


def _build_mock_client(
    file_contents: dict[str, str],
    *,
    commit: str = "abc123",
) -> tuple[httpx.Client, list[str]]:
    requested_paths: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requested_paths.append(str(request.url))
        if (
            request.url.host == "api.github.com"
            and request.url.path == "/repos/Logical-Byte/eer-resource/commits/main"
        ):
            return httpx.Response(200, json={"sha": commit})
        if (
            request.url.host == "raw.githubusercontent.com"
            and request.url.path.startswith(
                f"/Logical-Byte/eer-resource/{commit}/data/v2/"
            )
        ):
            name = Path(request.url.path).name
            return httpx.Response(200, text=file_contents[name])
        return httpx.Response(404, text="not found")

    return httpx.Client(transport=httpx.MockTransport(handler)), requested_paths


def test_check_for_updates_uses_upstream_api(tmp_path):
    bundled_root = tmp_path / "bundled"
    override_root = tmp_path / "override"
    state_path = tmp_path / "data_update_state.json"
    _write_data_root(bundled_root, weapon_name="Bundled Weapon")

    client, requested_paths = _build_mock_client(
        {
            "Weapon.json": "{}",
            "WeaponType.json": "{}",
        }
    )
    service = DataUpdateService(
        client=client,
        state_path=state_path,
        override_root=override_root,
        bundled_root=bundled_root,
    )

    result = service.check_for_updates()

    assert result.status.last_checked_version == "eer-resource@abc123"
    assert any(
        url == "https://api.github.com/repos/Logical-Byte/eer-resource/commits/main"
        for url in requested_paths
    )


def test_download_updates_applies_immediately_when_scanner_is_idle(tmp_path):
    bundled_root = tmp_path / "bundled"
    override_root = tmp_path / "override"
    state_path = tmp_path / "data_update_state.json"
    _write_data_root(bundled_root, weapon_name="Bundled Weapon")

    remote_root = tmp_path / "remote"
    _write_data_root(remote_root, weapon_name="Updated Weapon")
    client, _requested_paths = _build_mock_client(
        {
            "Weapon.json": (remote_root / "Weapon.json").read_text(encoding="utf-8"),
            "WeaponType.json": (remote_root / "WeaponType.json").read_text(
                encoding="utf-8"
            ),
        }
    )

    runtime = StaticDataRuntime(bundled_root=bundled_root, override_root=override_root)
    scanner = _FakeScannerService(running=False)
    service = DataUpdateService(
        client=client,
        state_path=state_path,
        override_root=override_root,
        bundled_root=bundled_root,
        apply_updates_callback=runtime.reload,
        scanner_service=scanner,
        static_data_runtime=runtime,
    )

    result = service.download_updates()
    status = service.get_status()

    assert result.downloaded is True
    assert result.applied is True
    assert status.current_data_source == DataSource.OVERRIDE
    assert status.pending_apply is False
    assert status.pending_version is None
    assert status.applied_version == "eer-resource@abc123"
    assert (
        runtime.get_static_game_data().get_weapon("weapon_1").name == "Updated Weapon"
    )  # type: ignore[union-attr]


def test_download_updates_defers_apply_until_scan_finishes(tmp_path):
    bundled_root = tmp_path / "bundled"
    override_root = tmp_path / "override"
    state_path = tmp_path / "data_update_state.json"
    _write_data_root(bundled_root, weapon_name="Bundled Weapon")

    remote_root = tmp_path / "remote"
    _write_data_root(remote_root, weapon_name="Updated Weapon")
    client, _requested_paths = _build_mock_client(
        {
            "Weapon.json": (remote_root / "Weapon.json").read_text(encoding="utf-8"),
            "WeaponType.json": (remote_root / "WeaponType.json").read_text(
                encoding="utf-8"
            ),
        }
    )

    runtime = StaticDataRuntime(bundled_root=bundled_root, override_root=override_root)
    scanner = _FakeScannerService(running=True)
    service = DataUpdateService(
        client=client,
        state_path=state_path,
        override_root=override_root,
        bundled_root=bundled_root,
        apply_updates_callback=runtime.reload,
        scanner_service=scanner,
        static_data_runtime=runtime,
    )

    result = service.download_updates()

    assert result.downloaded is True
    assert result.applied is False
    assert service.get_status().current_data_source == DataSource.BUNDLED
    assert service.get_status().pending_apply is True
    assert (
        runtime.get_static_game_data().get_weapon("weapon_1").name == "Bundled Weapon"
    )  # type: ignore[union-attr]

    scanner.finish()
    status = service.get_status()

    assert status.current_data_source == DataSource.OVERRIDE
    assert status.pending_apply is False
    assert status.pending_version is None
    assert (
        runtime.get_static_game_data().get_weapon("weapon_1").name == "Updated Weapon"
    )  # type: ignore[union-attr]


def test_download_updates_does_not_replace_existing_override_on_invalid_payload(
    tmp_path,
):
    bundled_root = tmp_path / "bundled"
    override_root = tmp_path / "override"
    state_path = tmp_path / "data_update_state.json"
    _write_data_root(bundled_root, weapon_name="Bundled Weapon")
    _write_data_root(override_root, weapon_name="Existing Override")

    existing_weapon_json = (override_root / "Weapon.json").read_text(encoding="utf-8")
    client, _requested_paths = _build_mock_client(
        {
            "Weapon.json": "{invalid json",
            "WeaponType.json": (bundled_root / "WeaponType.json").read_text(
                encoding="utf-8"
            ),
        }
    )
    service = DataUpdateService(
        client=client,
        state_path=state_path,
        override_root=override_root,
        bundled_root=bundled_root,
    )

    result = service.download_updates()

    assert result.downloaded is False
    assert result.status.current_data_source == DataSource.OVERRIDE
    assert result.status.last_error is not None
    assert (override_root / "Weapon.json").read_text(
        encoding="utf-8"
    ) == existing_weapon_json


def test_missing_override_files_reset_state(tmp_path):
    bundled_root = tmp_path / "bundled"
    override_root = tmp_path / "override"
    state_path = tmp_path / "data_update_state.json"
    _write_data_root(bundled_root, weapon_name="Bundled Weapon")

    remote_root = tmp_path / "remote"
    _write_data_root(remote_root, weapon_name="Updated Weapon")
    remote_files = {
        "Weapon.json": (remote_root / "Weapon.json").read_text(encoding="utf-8"),
        "WeaponType.json": (remote_root / "WeaponType.json").read_text(
            encoding="utf-8"
        ),
    }
    client, _requested_paths = _build_mock_client(remote_files)

    runtime = StaticDataRuntime(bundled_root=bundled_root, override_root=override_root)
    service = DataUpdateService(
        client=client,
        state_path=state_path,
        override_root=override_root,
        bundled_root=bundled_root,
        apply_updates_callback=runtime.reload,
        static_data_runtime=runtime,
    )
    service.download_updates()

    for name in ("Weapon.json", "WeaponType.json"):
        (override_root / name).unlink()

    reset_client, _requested_paths = _build_mock_client(remote_files)
    reset_service = DataUpdateService(
        client=reset_client,
        state_path=state_path,
        override_root=override_root,
        bundled_root=bundled_root,
        static_data_runtime=StaticDataRuntime(
            bundled_root=bundled_root, override_root=override_root
        ),
    )
    status = reset_service.get_status()

    assert status.current_data_source == DataSource.BUNDLED
    assert status.applied_version is None
    assert status.pending_apply is False
