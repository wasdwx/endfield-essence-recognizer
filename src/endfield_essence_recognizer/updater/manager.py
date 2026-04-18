"""更新管理器"""

import asyncio
import hashlib
from collections.abc import Callable
from pathlib import Path

from endfield_essence_recognizer.updater.checker import (
    NoUpdateAvailable,
    UpdateCheckError,
    check_for_updates,
)
from endfield_essence_recognizer.updater.downloader import download_update
from endfield_essence_recognizer.updater.installer import install_update
from endfield_essence_recognizer.utils.log import logger


def _verify_sha256(file_path: Path, expected: str) -> bool:
    """校验文件的 SHA-256 哈希值。

    Args:
        file_path: 待校验的文件。
        expected: 期望的 hex 格式 sha256。

    Returns:
        True 表示哈希匹配。
    """
    sha256 = hashlib.sha256()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            sha256.update(chunk)
    actual = sha256.hexdigest()
    match = actual == expected
    if not match:
        logger.error(f"SHA-256 校验失败: 期望 {expected[:16]}... 实际 {actual[:16]}...")
    else:
        logger.info("SHA-256 校验通过")
    return match


class UpdateManager:
    """更新管理器"""

    def __init__(self, download_dir: Path | None = None):
        self.download_dir = download_dir or Path.cwd() / "_updates"
        self.update_info: dict | None = None
        self.cancel_event = asyncio.Event()
        self.is_downloading = False
        self.download_lock = asyncio.Lock()
        self.download_task: asyncio.Task | None = None

    async def check_and_prompt(
        self, proxy: str | None = None
    ) -> dict | NoUpdateAvailable | UpdateCheckError:
        """检查更新并返回更新信息。

        返回值由 checker 的三种类型决定，调用方必须按类型分派。
        """
        result = await check_for_updates(proxy=proxy)
        if isinstance(result, dict):
            self.update_info = result
        return result

    def _compute_sha256(self, file_path: Path) -> str:
        """计算文件 SHA-256，供前端展示实际值。"""
        sha256 = hashlib.sha256()
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                sha256.update(chunk)
        return sha256.hexdigest()

    async def download_and_install(
        self,
        progress_callback: Callable[[int, int, float], None] | None = None,
        proxy: str | None = None,
        download_url: str | None = None,
        skip_verify: bool = False,
    ) -> dict:
        """下载并安装更新。

        返回值：
        - {"success": True}                     → 安装成功
        - {"success": False, "error": "xxx"}     → 一般错误
        - {"success": False, "error": "sha256_mismatch", ...} → 校验失败（前端可提示用户）
        """
        async with self.download_lock:
            if not self.update_info:
                logger.warning("没有可用的更新信息")
                return {"success": False, "error": "没有可用的更新信息"}

            download_path = (
                self.download_dir / f"update_{self.update_info['version']}.zip"
            )

            self.cancel_event.clear()
            self.is_downloading = True

            try:
                # 创建下载任务
                url = download_url or self.update_info["download_url"]
                self.download_task = asyncio.create_task(
                    download_update(
                        url,
                        download_path,
                        progress_callback,
                        self.cancel_event,
                        proxy,
                    )
                )
                success = await self.download_task

                if not success:
                    return {"success": False, "error": "下载失败或已取消"}

                # SHA-256 完整性校验
                expected_hash = self.update_info.get("sha256")
                if expected_hash and not skip_verify:
                    actual_hash = await asyncio.to_thread(
                        self._compute_sha256, download_path
                    )
                    if actual_hash != expected_hash:
                        logger.error(
                            f"SHA-256 校验失败: "
                            f"期望 {expected_hash[:16]}... 实际 {actual_hash[:16]}..."
                        )
                        return {
                            "success": False,
                            "error": "sha256_mismatch",
                            "sha256_expected": expected_hash,
                            "sha256_actual": actual_hash,
                        }
                    else:
                        logger.info("SHA-256 校验通过")
                elif expected_hash and skip_verify:
                    logger.warning("用户选择跳过 SHA-256 校验")
                else:
                    logger.info("无可用的 sha256 校验值，跳过完整性验证")

                # 安装更新（放到线程中执行，避免阻塞事件循环）
                install_ok = await asyncio.to_thread(install_update, download_path)
                if install_ok:
                    return {"success": True}
                else:
                    return {"success": False, "error": "安装失败"}
            except Exception as exc:
                logger.error(f"更新流程异常: {exc}")
                return {"success": False, "error": str(exc)}
            finally:
                self.is_downloading = False
                self.download_task = None

    def cancel_download(self) -> bool:
        """取消下载"""
        if self.is_downloading and self.download_task and not self.download_task.done():
            self.cancel_event.set()
            self.download_task.cancel()
            logger.info("已发送取消下载信号")
            return True
        logger.warning("当前没有正在进行的下载")
        return False
