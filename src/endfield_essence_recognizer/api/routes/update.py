"""更新相关 API 路由"""

import re

from fastapi import APIRouter, Depends

from endfield_essence_recognizer.api.websockets.update_progress import (
    reset_progress,
    update_progress,
)
from endfield_essence_recognizer.dependencies.settings import (
    get_user_setting_manager_dep,
)
from endfield_essence_recognizer.services.user_setting_manager import (
    UserSettingManager,
)
from endfield_essence_recognizer.updater.checker import (
    NoUpdateAvailable,
)
from endfield_essence_recognizer.updater.manager import UpdateManager
from endfield_essence_recognizer.updater.mirrors import MIRROR_NAMES
from endfield_essence_recognizer.utils.log import logger

router = APIRouter(prefix="/update", tags=["update"])

update_manager = UpdateManager()


@router.get("/mirrors")
async def get_mirrors():
    """获取可用的镜像源列表"""
    return {
        "mirrors": [{"title": name, "value": key} for key, name in MIRROR_NAMES.items()]
    }


@router.get("/check")
async def check_update(
    setting_manager: UserSettingManager = Depends(get_user_setting_manager_dep),
):
    """检查更新。

    前端可通过 has_update + error 两个字段区分三种状态：
    - has_update=true              → 有新版本
    - has_update=false, error=null → 已是最新
    - has_update=false, error=xxx  → 检查失败
    """
    try:
        settings = setting_manager.get_user_setting()
        proxy = settings.update_proxy if settings.update_proxy else None

        result = await update_manager.check_and_prompt(proxy=proxy)

        if isinstance(result, dict):
            return {"has_update": True, "update_info": result}
        elif isinstance(result, NoUpdateAvailable):
            return {"has_update": False, "error": None}
        else:
            # UpdateCheckError
            return {"has_update": False, "error": result.message}
    except Exception as e:
        logger.error(f"检查更新异常: {e}")
        return {"has_update": False, "error": str(e)}


@router.post("/install")
async def install_update_route(
    body: dict | None = None,
    setting_manager: UserSettingManager = Depends(get_user_setting_manager_dep),
):
    """下载并安装更新。

    请求体可选字段：
    - skip_verify: bool — 跳过 SHA-256 校验（用户在前端确认风险后主动选择）

    返回值包含 success + error（如有），其中 error="sha256_mismatch" 时
    附带 sha256_expected / sha256_actual 供前端展示。
    """
    try:
        skip_verify = bool((body or {}).get("skip_verify", False))

        settings = setting_manager.get_user_setting()
        proxy = settings.update_proxy if settings.update_proxy else None
        mirror = settings.update_mirror

        # 转换下载 URL
        download_url = None
        if mirror and mirror != "github" and update_manager.update_info:
            mirrors = update_manager.update_info.get("mirrors", {})
            # 优先使用一图流 API 返回的镜像
            if mirror in mirrors and "downloadUrl" in mirrors[mirror]:
                download_url = mirrors[mirror]["downloadUrl"]
                logger.info(f"使用 API 镜像源: {mirror}")
            elif "cn" in mirrors and "downloadUrl" in mirrors["cn"]:
                # 国内用户默认走 CN 镜像
                download_url = mirrors["cn"]["downloadUrl"]
                logger.info("使用 CN 镜像源")
            else:
                # 回退到 mirrors.py 中的模板镜像
                from endfield_essence_recognizer.updater.mirrors import get_mirror_url

                original_url = update_manager.update_info["download_url"]
                match = re.match(
                    r"https://github\.com/([^/]+)/([^/]+)/releases/download/([^/]+)/(.+)",
                    original_url,
                )
                if match:
                    owner, repo, tag, filename = match.groups()
                    download_url = get_mirror_url(
                        mirror, f"{owner}/{repo}", tag, filename
                    )
                    logger.info(f"使用模板镜像源: {mirror}")

        # 重置进度状态，避免上一轮残留值
        reset_progress()

        result = await update_manager.download_and_install(
            progress_callback=update_progress,
            proxy=proxy,
            download_url=download_url,
            skip_verify=skip_verify,
        )
        return result
    except Exception as e:
        logger.error(f"安装更新失败: {e}")
        return {"success": False, "error": str(e)}


@router.post("/cancel")
async def cancel_update():
    """取消下载

    只有在确实有活跃下载任务时才返回 success: true，
    避免前端在不确定取消结果时误触发重试逻辑。
    """
    try:
        cancelled = update_manager.cancel_download()
        return {"success": cancelled}
    except Exception as e:
        logger.error(f"取消更新失败: {e}")
        return {"success": False, "error": str(e)}
