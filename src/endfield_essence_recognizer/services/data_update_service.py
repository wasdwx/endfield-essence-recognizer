from __future__ import annotations

import hashlib
import shutil
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING

import httpx
from pydantic import AliasChoices, BaseModel, Field

from endfield_essence_recognizer.core.path import (
    get_bundled_static_data_dir,
    get_data_update_state_path,
    get_static_data_override_dir,
)
from endfield_essence_recognizer.game_data.static_game_data import StaticGameData
from endfield_essence_recognizer.schemas.data_update import (
    DataSource,
    DataUpdateActionResponse,
    DataUpdateStatusResponse,
)
from endfield_essence_recognizer.utils.log import logger

if TYPE_CHECKING:
    from collections.abc import Callable

    from endfield_essence_recognizer.services.scanner_service import ScannerService
    from endfield_essence_recognizer.services.static_data_runtime import (
        StaticDataRuntime,
    )


class _DataUpdateState(BaseModel):
    applied_version: str | None = None
    pending_version: str | None = None
    last_checked_version: str | None = None
    pending_apply: bool = False
    last_checked_at: datetime | None = None
    last_downloaded_at: datetime | None = None
    last_applied_at: datetime | None = None
    last_error: str | None = None


class _RemoteFileManifest(BaseModel):
    url: str | None = Field(
        default=None,
        validation_alias=AliasChoices("url", "downloadUrl"),
    )
    sha256: str | None = None


class _RemoteManifest(BaseModel):
    version: str | None = None
    commit: str | None = None
    files: dict[str, _RemoteFileManifest]


class DataUpdateService:
    UPSTREAM_OWNER = "Logical-Byte"
    UPSTREAM_REPO = "eer-resource"
    UPSTREAM_REF = "main"
    TARGET_FILES = ("Weapon.json", "WeaponType.json")

    def __init__(
        self,
        client: httpx.Client | None = None,
        state_path: Path | None = None,
        override_root: Path | None = None,
        bundled_root: Path | None = None,
        upstream_owner: str | None = None,
        upstream_repo: str | None = None,
        upstream_ref: str | None = None,
        apply_updates_callback: Callable[[], object] | None = None,
        scanner_service: ScannerService | None = None,
        static_data_runtime: StaticDataRuntime | None = None,
    ) -> None:
        self._client = client
        self._bundled_root = bundled_root or get_bundled_static_data_dir()
        self._state_path = state_path or get_data_update_state_path()
        self._override_root = override_root or get_static_data_override_dir()
        self._upstream_owner = upstream_owner or self.UPSTREAM_OWNER
        self._upstream_repo = upstream_repo or self.UPSTREAM_REPO
        self._upstream_ref = upstream_ref or self.UPSTREAM_REF
        self._apply_updates_callback = apply_updates_callback
        self._scanner_service = scanner_service
        self._static_data_runtime = static_data_runtime
        self._state = self._load_state()
        self._reconcile_state()

        if self._scanner_service is not None:
            self._scanner_service.register_idle_callback(
                self.apply_pending_updates_if_idle
            )

        self.apply_pending_updates_if_idle()

    def get_status(self) -> DataUpdateStatusResponse:
        self._reconcile_state()
        self.apply_pending_updates_if_idle()
        return self._build_status()

    def check_for_updates(self) -> DataUpdateActionResponse:
        try:
            manifest = self._fetch_remote_manifest()
            remote_version = self._resolve_remote_version(manifest)
            now = datetime.now(UTC)
            self._state.last_checked_version = remote_version
            self._state.last_checked_at = now
            self._state.last_error = None
            self._save_state()

            self.apply_pending_updates_if_idle()
            status = self._build_status(remote_version=remote_version)
            if status.pending_apply:
                message = "最新武器数据已下载，当前扫描结束后会自动应用。"
            elif status.update_available:
                message = "检测到新的武器数据，可以开始下载。"
            else:
                message = "当前武器数据已是最新。"
            return DataUpdateActionResponse(
                status=status,
                message=message,
                downloaded=False,
                applied=False,
            )
        except Exception as exc:
            message = f"检查武器数据更新失败：{exc}"
            logger.warning(message)
            self._state.last_error = str(exc)
            self._save_state()
            return DataUpdateActionResponse(
                status=self._build_status(),
                message=message,
                downloaded=False,
                applied=False,
            )

    def download_updates(self) -> DataUpdateActionResponse:
        try:
            manifest = self._fetch_remote_manifest()
            remote_version = self._resolve_remote_version(manifest)
            now = datetime.now(UTC)
            self._state.last_checked_version = remote_version
            self._state.last_checked_at = now

            if (
                remote_version == self._state.applied_version
                and not self._state.pending_apply
                and self._override_files_exist()
            ):
                self._state.last_error = None
                self._save_state()
                return DataUpdateActionResponse(
                    status=self._build_status(remote_version=remote_version),
                    message="当前武器数据已是最新。",
                    downloaded=False,
                    applied=False,
                )

            if (
                remote_version == self._state.pending_version
                and self._state.pending_apply
            ):
                applied = self.apply_pending_updates_if_idle()
                self._state.last_error = None
                self._save_state()
                return DataUpdateActionResponse(
                    status=self._build_status(remote_version=remote_version),
                    message=(
                        "武器数据已更新并立即生效。"
                        if applied
                        else "最新武器数据已下载，当前扫描结束后会自动应用。"
                    ),
                    downloaded=False,
                    applied=applied,
                )

            file_contents = self._download_remote_files(manifest)
            self._write_override_files(file_contents)

            self._state.pending_version = remote_version
            self._state.pending_apply = True
            self._state.last_checked_version = remote_version
            self._state.last_checked_at = now
            self._state.last_downloaded_at = now
            self._state.last_error = None
            self._save_state()

            applied = self.apply_pending_updates_if_idle()
            message = (
                "武器数据已更新并立即生效。"
                if applied
                else "武器数据已下载，当前扫描结束后会自动应用。"
            )
            return DataUpdateActionResponse(
                status=self._build_status(remote_version=remote_version),
                message=message,
                downloaded=True,
                applied=applied,
            )
        except Exception as exc:
            message = f"刷新武器数据失败：{exc}"
            logger.warning(message)
            self._state.last_error = str(exc)
            self._save_state()
            return DataUpdateActionResponse(
                status=self._build_status(),
                message=message,
                downloaded=False,
                applied=False,
            )

    def apply_pending_updates_if_idle(self) -> bool:
        if not self._state.pending_apply or not self._state.pending_version:
            return False

        if not self._override_files_exist():
            self._state.pending_apply = False
            self._state.pending_version = None
            self._save_state()
            return False

        if self._scanner_service is not None and self._scanner_service.is_running():
            return False

        if self._apply_updates_callback is None:
            return False

        try:
            self._apply_updates_callback()
        except Exception as exc:
            self._state.last_error = str(exc)
            self._save_state()
            logger.exception(f"应用下载后的武器数据失败：{exc}")
            return False

        now = datetime.now(UTC)
        self._state.applied_version = self._state.pending_version
        self._state.pending_version = None
        self._state.pending_apply = False
        self._state.last_applied_at = now
        self._state.last_error = None
        self._save_state()
        logger.info("已在运行时应用新的武器数据。")
        return True

    def _load_state(self) -> _DataUpdateState:
        if not self._state_path.exists():
            return _DataUpdateState()
        try:
            return _DataUpdateState.model_validate_json(
                self._state_path.read_text(encoding="utf-8")
            )
        except Exception as exc:
            logger.warning(f"读取武器数据更新状态失败，将重置状态：{exc}")
            return _DataUpdateState(last_error=f"状态文件损坏：{exc}")

    def _save_state(self) -> None:
        self._state_path.parent.mkdir(parents=True, exist_ok=True)
        self._state_path.write_text(
            self._state.model_dump_json(indent=2),
            encoding="utf-8",
        )

    def _reconcile_state(self) -> None:
        state_changed = False

        if not self._override_files_exist():
            if self._state.applied_version is not None:
                self._state.applied_version = None
                state_changed = True
            if self._state.pending_version is not None:
                self._state.pending_version = None
                state_changed = True
            if self._state.pending_apply:
                self._state.pending_apply = False
                state_changed = True

        if self._state.pending_version == self._state.applied_version:
            self._state.pending_version = None
            self._state.pending_apply = False
            state_changed = True

        if self._state.pending_apply and not self._state.pending_version:
            self._state.pending_apply = False
            state_changed = True

        if state_changed:
            self._save_state()

    def _build_status(
        self,
        remote_version: str | None = None,
    ) -> DataUpdateStatusResponse:
        known_remote_version = remote_version or self._state.last_checked_version
        update_available = (
            known_remote_version is not None
            and known_remote_version
            not in {self._state.applied_version, self._state.pending_version}
        )
        return DataUpdateStatusResponse(
            current_data_source=self._detect_current_data_source(),
            applied_version=self._state.applied_version,
            pending_version=self._state.pending_version,
            last_checked_version=known_remote_version,
            update_available=update_available,
            pending_apply=self._state.pending_apply,
            last_checked_at=self._state.last_checked_at,
            last_downloaded_at=self._state.last_downloaded_at,
            last_applied_at=self._state.last_applied_at,
            last_error=self._state.last_error,
        )

    def _detect_current_data_source(self) -> DataSource:
        if self._static_data_runtime is not None:
            return self._static_data_runtime.get_current_data_source()
        return (
            DataSource.OVERRIDE if self._override_files_exist() else DataSource.BUNDLED
        )

    def _override_files_exist(self) -> bool:
        return all((self._override_root / name).is_file() for name in self.TARGET_FILES)

    def _fetch_remote_manifest(self) -> _RemoteManifest:
        commit = self._fetch_latest_commit()
        files = {
            name: _RemoteFileManifest(url=self._build_raw_url(commit, name))
            for name in self.TARGET_FILES
        }
        return _RemoteManifest(
            version=f"{self._upstream_repo}@{commit}",
            commit=commit,
            files=files,
        )

    def _resolve_remote_version(self, manifest: _RemoteManifest) -> str:
        if manifest.version:
            return manifest.version
        if manifest.commit:
            return f"eer-resource@{manifest.commit}"

        parts: list[str] = []
        for name in self.TARGET_FILES:
            file_info = manifest.files[name]
            parts.append(f"{name}:{file_info.sha256 or file_info.url}")
        return "|".join(parts)

    def _download_remote_files(self, manifest: _RemoteManifest) -> dict[str, str]:
        file_contents: dict[str, str] = {}
        for name in self.TARGET_FILES:
            file_info = manifest.files[name]
            response = self._client_get(file_info.url)
            response.raise_for_status()

            if file_info.sha256:
                actual_sha256 = hashlib.sha256(response.content).hexdigest()
                if actual_sha256.lower() != file_info.sha256.lower():
                    raise RuntimeError(
                        f"{name} 的 SHA-256 校验失败：期望 {file_info.sha256}，实际 {actual_sha256}"
                    )

            file_contents[name] = response.text
        return file_contents

    def _fetch_latest_commit(self) -> str:
        response = self._client_get(self._build_commit_api_url())
        response.raise_for_status()
        payload = response.json()
        commit = payload.get("sha")
        if not commit:
            raise RuntimeError("上游 API 未返回 commit SHA")
        return str(commit)

    def _build_commit_api_url(self) -> str:
        return (
            f"https://api.github.com/repos/"
            f"{self._upstream_owner}/{self._upstream_repo}/commits/{self._upstream_ref}"
        )

    def _build_raw_url(self, commit: str, name: str) -> str:
        return (
            f"https://raw.githubusercontent.com/"
            f"{self._upstream_owner}/{self._upstream_repo}/{commit}/data/v2/{name}"
        )

    def _client_get(self, url: str) -> httpx.Response:
        if self._client is not None:
            return self._client.get(url)

        with httpx.Client(
            timeout=10.0,
            follow_redirects=True,
            headers={
                "User-Agent": "endfield-essence-recognizer-data-updater",
                "Accept": "application/vnd.github+json, application/json, text/plain;q=0.9, */*;q=0.8",
            },
        ) as client:
            return client.get(url)

    def _write_override_files(self, file_contents: dict[str, str]) -> None:
        self._override_root.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=self._override_root.parent) as temp_dir:
            temp_root = Path(temp_dir)
            for name, content in file_contents.items():
                (temp_root / name).write_text(content, encoding="utf-8")

            StaticGameData(temp_root, fallback_root=self._bundled_root)

            self._override_root.mkdir(parents=True, exist_ok=True)
            for name in self.TARGET_FILES:
                shutil.copyfile(temp_root / name, self._override_root / name)
