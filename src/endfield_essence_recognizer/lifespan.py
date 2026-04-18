from __future__ import annotations

import importlib.resources
import mimetypes
from contextlib import asynccontextmanager
from pathlib import Path
from typing import TYPE_CHECKING

from fastapi.staticfiles import StaticFiles

from endfield_essence_recognizer.core.config import ServerConfig, get_server_config
from endfield_essence_recognizer.dependencies import (
    default_user_setting_manager,
    get_log_service,
)
from endfield_essence_recognizer.dependencies.services import (
    get_scanner_service,
    get_static_game_data,
    sync_audio_service_enabled,
)
from endfield_essence_recognizer.hotkey_entrypoints import bind_hotkeys
from endfield_essence_recognizer.utils.log import logger

if TYPE_CHECKING:
    from fastapi import FastAPI


def log_welcome_message() -> None:
    """输出启动欢迎信息与基本使用说明。"""
    message = """
==================================================
<green><bold>终末地武器基质识别器</></>
==================================================
<green><bold>使用前请确认：</></>
  - 游戏窗口保持前台，且分辨率与当前配置匹配
  - 建议使用 1080p 或已适配的布局配置
  - 先按 "<green><bold>N</></>" 打开背包，再切到武器基质页面
  - 扫描过程中尽量不要切走终末地窗口

<green><bold>默认快捷键：</></>
  - 按 "<green><bold>[</></>" 开始 / 停止扫描
  - 按 "<green><bold>]</></>" 执行单次识别
  - 按 "<green><bold>Alt+Delete</></>" 退出程序

  <cyan><bold>提示：</></>如果你启用了自动翻页、声音提示或武器热更新，
  程序会在启动后自动加载对应配置。
==================================================
"""
    logger.opt(colors=True).info(message)


def init_load_user_setting() -> None:
    """启动时加载用户配置。"""
    user_setting_manager = default_user_setting_manager()
    user_setting_manager.load_user_setting()
    sync_audio_service_enabled(user_setting_manager.get_user_setting_ref().enable_sound)


def log_last_scan_summary() -> None:
    """打印上次持久化的扫描汇总。"""
    try:
        get_scanner_service().log_last_scan_summary(get_static_game_data())
    except Exception as exc:
        logger.warning(f"读取上次扫描汇总时加载静态数据失败：{exc}")


def init_mount_frontend_build(app: FastAPI, server_config: ServerConfig) -> None:
    """挂载前端静态构建目录。"""
    if server_config.dev_mode:
        return

    mimetypes.add_type("application/javascript", ".js")
    mimetypes.add_type("application/javascript", ".mjs")
    mimetypes.add_type("text/css", ".css")
    mimetypes.add_type("application/json", ".json")
    mimetypes.add_type("application/json", ".map")
    mimetypes.add_type("image/svg+xml", ".svg")
    mimetypes.add_type("image/webp", ".webp")
    mimetypes.add_type("application/xml", ".xml")
    mimetypes.add_type("application/wasm", ".wasm")
    mimetypes.add_type("font/woff2", ".woff2")
    mimetypes.add_type("font/woff", ".woff")
    mimetypes.add_type("font/ttf", ".ttf")

    if not server_config.dist_dir:
        dist_dir = (
            Path(str(importlib.resources.files("endfield_essence_recognizer")))
            / "webui_dist"
        )
    else:
        dist_dir = Path(server_config.dist_dir)

    if dist_dir.exists():
        app.mount("/", StaticFiles(directory=dist_dir, html=True), name="dist")
    else:
        logger.error("未找到前端构建目录，无法挂载 Web UI。")


@asynccontextmanager
async def lifespan(app: FastAPI):
    server_config = get_server_config()
    async with get_log_service().scope(server_config):
        logger.success(f"Server configuration: {server_config.model_dump()}")
        init_mount_frontend_build(app, server_config)
        init_load_user_setting()
        log_welcome_message()
        log_last_scan_summary()
        with bind_hotkeys(server_config):
            yield
