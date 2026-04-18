"""更新检查器。"""

from __future__ import annotations

import httpx
from packaging import version

from endfield_essence_recognizer.utils.log import logger
from endfield_essence_recognizer.version import __version__

UPDATE_CHECK_URL = "https://wasdwx.github.io/endfield-essence-recognizer/version.json"


class UpdateCheckError(Exception):
    """更新检查失败。"""

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class NoUpdateAvailable:
    """当前已是最新版本。"""

    pass


async def check_for_updates(
    proxy: str | None = None,
) -> dict | NoUpdateAvailable | UpdateCheckError:
    """从 GitHub Pages 的静态清单中检查更新。"""
    if not __version__:
        return UpdateCheckError("当前版本号无效")

    try:
        async with httpx.AsyncClient(timeout=10.0, proxy=proxy or None) as client:
            response = await client.get(UPDATE_CHECK_URL)
            response.raise_for_status()
            data = response.json()

            latest_version = data["latestVersion"]

            if version.parse(latest_version) > version.parse(__version__):
                logger.info(f"发现新版本：{latest_version}")
                return {
                    "version": latest_version,
                    "download_url": data["downloadUrl"],
                    "mirrors": data.get("mirrors", {}),
                    "sha256": data.get("sha256"),
                }

            logger.info("当前已是最新版本")
            return NoUpdateAvailable()

    except Exception as exc:
        logger.warning(f"检查更新失败：{exc}")
        return UpdateCheckError(str(exc))
