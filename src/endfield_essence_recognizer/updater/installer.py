"""更新安装模块

基于 manifest.json 实现增量更新：
- 新增：manifest 中有、本地没有的文件 → 复制
- 覆盖：manifest 中有、本地也有的文件 → 覆盖
- 删除：本地有、manifest 中没有、且不在 protected 列表中的文件 → 删除
- protected 保护"删除"和"覆盖"双重语义

manifest.json 存放在 ``_internal/manifest.json``，随更新包一起被复制到目标目录，
下次更新时作为"旧 manifest"被读取。
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from endfield_essence_recognizer.utils.log import logger

# manifest 在安装目录中的相对路径（与 generate_manifest.py 保持一致）
MANIFEST_RELATIVE_PATH = "_internal/manifest.json"


def _is_path_traversal(temp_dir: Path, member: str) -> bool:
    """检查 zip 条目是否存在路径穿越风险。

    使用 Path.relative_to() 做严格的路径归属判断，而非字符串前缀匹配，
    避免前缀碰撞绕过（如 temp_dir="/tmp/u" + member="../update_evil"）。

    Args:
        temp_dir: 解压目标目录（已 resolve）。
        member: zip 条目名称。

    Returns:
        True 表示存在穿越风险，应拒绝该条目。
    """
    resolved_temp = temp_dir.resolve()
    try:
        member_path = (resolved_temp / member).resolve()
        member_path.relative_to(resolved_temp)
        return False
    except ValueError:
        return True


def _load_manifest(temp_dir: Path) -> dict | None:
    """从解压目录中加载 manifest.json。

    读取 ``_internal/manifest.json``（新规范位置），同时兼容根目录 ``manifest.json``
    （旧版更新包回退）。

    Args:
        temp_dir: 解压后的临时目录。

    Returns:
        manifest 字典，如果文件不存在则返回 None。
    """
    # 优先尝试新位置 _internal/manifest.json
    manifest_path = temp_dir / MANIFEST_RELATIVE_PATH
    if not manifest_path.is_file():
        # 回退：旧版更新包把 manifest.json 放在根目录
        manifest_path = temp_dir / "manifest.json"
        if not manifest_path.is_file():
            logger.warning("更新包中未找到 manifest.json，将使用回退方案")
            return None

    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        # 基本校验
        if "files" not in manifest or "protected" not in manifest:
            logger.error("manifest.json 格式不完整，缺少 files 或 protected 字段")
            return None
        logger.info(
            f"加载 manifest: version={manifest.get('version', '?')}, "
            f"files={len(manifest['files'])}, protected={len(manifest['protected'])}"
        )
        return manifest
    except (json.JSONDecodeError, OSError) as exc:
        logger.error(f"加载 manifest.json 失败: {exc}")
        return None


def _is_protected(file_path: str, protected: set[str]) -> bool:
    """判断文件是否被 protected 列表保护（精确匹配或前缀目录匹配）。"""
    if file_path in protected:
        return True
    return any(file_path.startswith(p) for p in protected)


def _generate_update_script_manifest(
    current_dir: Path,
    temp_dir: Path,
    manifest: dict,
) -> str:
    """生成基于 manifest 的批处理更新脚本。

    脚本流程：
    1. 等待程序关闭
    2. 备份 protected 文件（防止被覆盖）
    3. 按删除清单删除旧文件
    4. 按复制清单复制新文件（已排除 protected）
    5. 恢复 protected 文件
    6. 清理并启动新版本

    Args:
        current_dir: 当前程序所在目录。
        temp_dir: 解压后的临时目录。
        manifest: manifest 字典。

    Returns:
        批处理脚本内容。
    """
    # manifest 文件本身也需要在更新后保留
    # （它已经在 manifest["files"] 中了，因为 generate_manifest 会把它加进去）

    script = r"""@echo off
setlocal EnableDelayedExpansion

echo ========================================
echo  EER Updater - Manifest-based Update
echo ========================================

REM Root directory detection (prevent installation to C:\ or D:\)
set "check_dir=%~dp0"
REM Remove drive letter and colon (e.g., "C:" -> "")
set "check_dir=%check_dir:~2%"
REM Remove trailing backslash
if "%check_dir:~-1%"=="\\" set "check_dir=%check_dir:~0,-1%"
REM If empty after removing drive and backslash, we're at root
if "%check_dir%"=="" (
    echo ERROR: Do not install to a root directory like C:\ or D:\
    echo Please create a subfolder, e.g. D:\EER\
    echo Press any key to exit...
    pause >nul
    exit /b 1
)

echo [1/6] Waiting for program to close...
timeout /t 3 /nobreak >nul

:wait_loop
tasklist /FI "IMAGENAME eq endfield-essence-recognizer.exe" 2>NUL | find /I /N "endfield-essence-recognizer.exe">NUL
if "%ERRORLEVEL%"=="0" (
    echo   Program still running, waiting...
    timeout /t 1 /nobreak >nul
    goto wait_loop
)

echo [2/6] Waiting for file handles to release...
timeout /t 2 /nobreak >nul

REM Check write permission
echo test >"%~dp0__write_test__.tmp" 2>nul
if errorlevel 1 (
    echo ERROR: No write permission! Please run as administrator.
    echo Press any key to exit...
    pause >nul
    exit /b 1
)
del "%~dp0__write_test__.tmp" 2>nul

echo [3/6] Backing up protected files...

if not exist "%~dp0_update_temp\\__protected_files.txt" (
    echo   No protected files to back up.
    goto delete_old
)

set backup_count=0
for /F "usebackq delims=" %%F in ("%~dp0_update_temp\\__protected_files.txt") do (
    if exist "%~dp0%%F" (
        REM Backup to _update_temp directory (will be restored after update)
        for %%D in ("%~dp0_update_temp\\__backup\\%%F") do (
            if not exist "%%~dpD" mkdir "%%~dpD" 2>nul
        )
        copy /Y "%~dp0%%F" "%~dp0_update_temp\\__backup\\%%F" >nul
        if not errorlevel 1 (
            echo   Backed up: %%F
            set /a backup_count+=1
        ) else (
            echo   FAILED to back up: %%F
        )
    )
)
echo   Backed up !backup_count! protected files.

:delete_old
echo [4/6] Removing old version files...

if not exist "%~dp0_update_temp\\__to_delete.txt" (
    echo   No old files to delete ^(first install or no old manifest^).
    goto copy_files
)

set delete_count=0
for /F "usebackq delims=" %%F in ("%~dp0_update_temp\\__to_delete.txt") do (
    if exist "%~dp0%%F" (
        del /F /Q "%~dp0%%F" 2>nul
        if not errorlevel 1 (
            echo   Deleted: %%F
            set /a delete_count+=1
        ) else (
            echo   FAILED to delete: %%F
        )
    )
)

echo   Deleted !delete_count! old files.

REM Clean up empty directories left after file deletion
echo [4.5/6] Removing empty directories...
REM First pass: remove immediate parent directories of deleted files
for /F "usebackq delims=" %%D in ("%~dp0_update_temp\\__to_delete.txt") do (
    for %%P in ("%~dp0%%D") do (
        if exist "%%~dpP" (
            rmdir "%%~dpP" 2>nul
        )
    )
)
REM Second pass: recursively remove empty directories in _internal
for /d %%D in ("%~dp0_internal\*") do (
    rmdir "%%D" 2>nul
    if exist "%%D" (
        for /d %%S in ("%%D\*") do (
            rmdir "%%S" 2>nul
        )
        rmdir "%%D" 2>nul
    )
)
echo   Empty directories cleaned.

:copy_files
echo [5/7] Copying new / updated files from update package...

REM Verify manifest file exists
if not exist "%~dp0_update_temp\\__manifest_files.txt" (
    echo ERROR: Manifest file missing! Update aborted.
    echo Press any key to exit...
    pause >nul
    exit /b 1
)

set copy_failed=0
set copy_count=0

REM Copy all files listed in manifest (new + overwrite), protected files excluded
for /F "usebackq delims=" %%F in ("%~dp0_update_temp\\__manifest_files.txt") do (
    if exist "%~dp0_update_temp\\%%F" (
        REM Ensure target directory exists
        for %%D in ("%~dp0%%F") do (
            if not exist "%%~dpD" mkdir "%%~dpD" 2>nul
        )
        copy /Y "%~dp0_update_temp\\%%F" "%~dp0%%F" >nul
        if errorlevel 1 (
            echo   FAILED: %%F
            set copy_failed=1
        ) else (
            set /a copy_count+=1
        )
    )
)

if !copy_failed!==1 (
    echo WARNING: Some files failed to copy.
    echo Press any key to exit...
    pause >nul
    exit /b 1
)

echo   Copied !copy_count! files.

REM Restore protected files (if backed up)
if exist "%~dp0_update_temp\\__backup" (
    echo [6/7] Restoring protected files...
    for /F "usebackq delims=" %%F in ("%~dp0_update_temp\\__protected_files.txt") do (
        if exist "%~dp0_update_temp\\__backup\\%%F" (
            for %%D in ("%~dp0%%F") do (
                if not exist "%%~dpD" mkdir "%%~dpD" 2>nul
            )
            copy /Y "%~dp0_update_temp\\__backup\\%%F" "%~dp0%%F" >nul
            echo   Restored: %%F
        )
    )
)

:cleanup
echo [7/7] Cleaning up update files...
rmdir /S /Q "%~dp0_update_temp" 2>nul
rmdir /S /Q "%~dp0_updates" 2>nul

echo.
echo ========================================
echo  Update complete! Starting new version...
echo ========================================
start "" "%~dp0endfield-essence-recognizer.exe"

timeout /t 1 /nobreak >nul
del "%~f0"
"""
    return script


def _generate_update_script_fallback(current_dir: Path, temp_dir: Path) -> str:
    """生成回退方案的批处理更新脚本（无 manifest 时使用）。

    保持与原始行为一致：硬编码删除列表 + xcopy 全量复制。

    Args:
        current_dir: 当前程序所在目录。
        temp_dir: 解压后的临时目录。

    Returns:
        批处理脚本内容。
    """
    return r"""@echo off
chcp 65001 >nul
setlocal EnableDelayedExpansion

echo ========================================
echo  EER Updater - Fallback Mode
echo ========================================

REM Root directory detection (prevent installation to C:\ or D:\)
set "check_dir=%~dp0"
REM Remove drive letter and colon (e.g., "C:" -> "")
set "check_dir=%check_dir:~2%"
REM Remove trailing backslash
if "%check_dir:~-1%"=="\\" set "check_dir=%check_dir:~0,-1%"
REM If empty after removing drive and backslash, we're at root
if "%check_dir%"=="" (
    echo ERROR: Do not install to a root directory like C:\ or D:\
    echo Please create a subfolder, e.g. D:\EER\
    echo Press any key to exit...
    pause >nul
    exit /b 1
)

echo [1/5] Waiting for program to close...
timeout /t 3 /nobreak >nul

:wait_loop
tasklist /FI "IMAGENAME eq endfield-essence-recognizer.exe" 2>NUL | find /I /N "endfield-essence-recognizer.exe">NUL
if "%ERRORLEVEL%"=="0" (
    echo   Program still running, waiting...
    timeout /t 1 /nobreak >nul
    goto wait_loop
)

echo [2/5] Waiting for file handles to release...
timeout /t 2 /nobreak >nul

echo [3/5] Protecting user configuration...
if exist "%~dp0config.json" (
    copy /Y "%~dp0config.json" "%~dp0config.json.protected" >nul
    echo   Config file backed up
)

echo [4/5] Deleting old program files...
if exist "%~dp0endfield-essence-recognizer.exe" del /F /Q "%~dp0endfield-essence-recognizer.exe" 2>nul
if exist "%~dp0_internal" rmdir /S /Q "%~dp0_internal" 2>nul
if exist "%~dp0logs" rmdir /S /Q "%~dp0logs" 2>nul
if exist "%~dp0resources" rmdir /S /Q "%~dp0resources" 2>nul
if exist "%~dp0README.md" del /F /Q "%~dp0README.md" 2>nul
if exist "%~dp0界面白屏解决方法.md" del /F /Q "%~dp0界面白屏解决方法.md" 2>nul
if exist "%~dp0遇到报错解决方法.webp" del /F /Q "%~dp0遇到报错解决方法.webp" 2>nul

echo [5/5] Copying new files...
set retry=0
:copy_retry
xcopy /E /Y /I "%~dp0_update_temp\\*" "%~dp0" 2>nul
if errorlevel 1 (
    set /a retry+=1
    if !retry! lss 5 (
        echo   Copy failed, retrying... ^(attempt !retry!/5^)
        timeout /t 2 /nobreak >nul
        goto copy_retry
    )
    echo ERROR: File copy failed after 5 attempts
    echo Press any key to exit...
    pause >nul
    exit /b 1
)

echo Cleaning up...
rmdir /S /Q "%~dp0_update_temp" 2>nul
rmdir /S /Q "%~dp0_updates" 2>nul

echo Restoring user configuration...
if exist "%~dp0config.json.protected" (
    move /Y "%~dp0config.json.protected" "%~dp0config.json" >nul
    echo   Config file restored
)

echo.
echo ========================================
echo  Update complete! Starting new version...
echo ========================================
start "" "%~dp0endfield-essence-recognizer.exe"

timeout /t 1 /nobreak >nul
del "%~f0"
"""


def _prepare_delete_list(
    current_dir: Path,
    temp_dir: Path,
    new_manifest: dict,
) -> None:
    """基于旧 manifest 生成需要删除的文件列表。

    删除旧 manifest 中的所有文件（排除 protected），
    确保所有程序文件都会被新版本替换。

    如果没有旧 manifest（首次升级到 manifest 方案），则扫描磁盘上
    安装目录中的文件，删除那些"大概率是旧程序"的文件（.exe, .dll,
    .pyd, .pyz 等），但跳过 manifest 识别的新版本文件和 protected 文件。

    Args:
        current_dir: 当前程序所在目录。
        temp_dir: 解压后的临时目录。
        new_manifest: 新版本的 manifest 字典。
    """
    protected = set(new_manifest["protected"])
    new_files = set(new_manifest["files"])

    # 读取旧 manifest
    old_manifest_path = current_dir / MANIFEST_RELATIVE_PATH
    # 兼容旧版：旧版 manifest.json 在根目录
    if not old_manifest_path.is_file():
        old_manifest_path = current_dir / "manifest.json"

    old_files: set[str] = set()
    if old_manifest_path.is_file():
        try:
            old_manifest = json.loads(old_manifest_path.read_text(encoding="utf-8"))
            old_files = set(old_manifest.get("files", []))
            logger.info(f"读取旧 manifest: {len(old_files)} 个文件")
        except Exception as exc:
            logger.warning(f"无法读取旧 manifest: {exc}")

    to_delete: list[str] = []

    if old_files:
        # 有旧 manifest：精确删除旧文件（排除 protected）
        for file in old_files:
            if not _is_protected(file, protected):
                to_delete.append(file)
    else:
        # 无旧 manifest（首次升级到 manifest 方案）：
        # 核心原则：不要删除用户本来就有的文件。
        # 此前版本的更新策略是"删文件夹+重新解压"，不需要额外兜底。
        # 只清理 manifest 中声明的目录内的旧程序文件残留（.exe/.dll/.pyd），
        # 确保 _internal 等目录干净即可，其他文件一律不动。
        _PROGRAM_EXTENSIONS = {".exe", ".dll", ".pyd", ".pyz", ".pyi"}

        # 从新 manifest 中提取涉及的目录前缀
        manifest_dirs: set[str] = set()
        for f in new_files:
            parts = f.split("/")
            for i in range(1, len(parts)):
                manifest_dirs.add("/".join(parts[:i]) + "/")

        for path in current_dir.rglob("*"):
            if not path.is_file():
                continue
            try:
                rel = str(path.relative_to(current_dir).as_posix())
            except ValueError:
                continue
            # 跳过 protected
            if _is_protected(rel, protected):
                continue
            # 跳过新 manifest 中的文件
            if rel in new_files:
                continue
            # 只清理 manifest 涉及目录下的旧程序文件（.exe/.dll/.pyd 等）
            in_manifest_dir = any(rel.startswith(d) for d in manifest_dirs)
            if in_manifest_dir and path.suffix.lower() in _PROGRAM_EXTENSIONS:
                to_delete.append(rel)
        logger.info(
            f"首次升级（无旧 manifest）：清理 manifest 目录下的旧程序文件残留，"
            f"共 {len(to_delete)} 个"
        )

    # 写入删除清单（转换为 Windows 路径格式）
    delete_list_path = temp_dir / "__to_delete.txt"
    delete_list_path.write_text(
        "\n".join(f.replace("/", "\\") for f in sorted(to_delete)) + "\n"
        if to_delete
        else "",
        encoding="utf-8",
    )

    logger.info(f"生成删除清单: {len(to_delete)} 个文件")


def _prepare_manifest_files_list(temp_dir: Path, manifest: dict) -> None:
    """生成 manifest 文件列表，供批处理脚本复制使用。

    已排除 protected 文件，避免覆盖用户配置等敏感数据。
    manifest.json 自身（``_internal/manifest.json``）必须在列表中，
    确保更新后磁盘上保留"新 manifest"供下次更新使用。

    Args:
        temp_dir: 解压后的临时目录。
        manifest: manifest 字典。
    """
    protected = set(manifest["protected"])
    # 过滤掉 protected 文件和 .git 相关文件
    copy_files = [
        f
        for f in manifest["files"]
        if not _is_protected(f, protected)
        and not f.startswith(".git")
        and "/.git" not in f
        and not f.startswith("resources/.git")
        and "/resources/.git" not in f
    ]

    files_path = temp_dir / "__manifest_files.txt"
    # 转换为 Windows 路径格式
    files_path.write_text(
        "\n".join(f.replace("/", "\\") for f in sorted(copy_files)) + "\n",
        encoding="utf-8",
    )


def _prepare_protected_files_list(temp_dir: Path, manifest: dict) -> None:
    """生成 protected 文件列表，供批处理脚本备份/恢复使用。

    仅列出在磁盘上实际存在的 protected 文件（非目录）。

    Args:
        temp_dir: 解压后的临时目录。
        manifest: manifest 字典。
    """
    protected_path = temp_dir / "__protected_files.txt"
    # batch 脚本会在安装目录检查文件是否存在
    protected_entries = []
    for p in manifest["protected"]:
        # 目录条目（如 logs/）不需要备份，只备份具体文件
        if not p.endswith("/"):
            protected_entries.append(p)
    # 转换为 Windows 路径格式
    protected_path.write_text(
        "\n".join(p.replace("/", "\\") for p in sorted(protected_entries)) + "\n",
        encoding="utf-8",
    )


def install_update(zip_path: Path) -> bool:
    """安装更新。

    流程：
    1. 解压更新包到临时目录（含路径穿越校验）
    2. 读取 manifest.json（``_internal/manifest.json`` 或根目录回退）
    3. 生成删除清单（有旧 manifest 则精确删除，无则保守清理旧程序文件）
    4. 生成复制清单（已排除 protected）
    5. 生成 protected 备份清单
    6. 生成批处理更新脚本（备份 → 删除 → 复制 → 恢复 → 清理）
    7. 启动脚本并退出当前程序

    Args:
        zip_path: 更新包路径。

    Returns:
        bool: 安装是否成功。
    """
    import zipfile

    try:
        # 获取当前程序目录
        if getattr(sys, "frozen", False):
            current_dir = Path(sys.executable).parent
        else:
            current_dir = Path.cwd()

        # 创建临时解压目录
        temp_dir = current_dir / "_update_temp"
        if temp_dir.exists():
            import shutil

            shutil.rmtree(temp_dir)
        temp_dir.mkdir()

        # 解压更新包
        logger.info(f"解压更新包到: {temp_dir}")
        with zipfile.ZipFile(zip_path, "r") as zip_ref:
            # 安全校验：使用 Path.relative_to() 拒绝路径穿越
            for member in zip_ref.namelist():
                if _is_path_traversal(temp_dir, member):
                    logger.error(f"拒绝可疑的 zip 条目（路径穿越）: {member}")
                    return False
            zip_ref.extractall(temp_dir)

        # 尝试加载 manifest
        manifest = _load_manifest(temp_dir)

        if manifest is not None:
            # Manifest 模式：精确删除 + 排除 protected 的复制
            logger.info("使用 manifest 模式进行更新")
            _prepare_delete_list(current_dir, temp_dir, manifest)
            _prepare_manifest_files_list(temp_dir, manifest)
            _prepare_protected_files_list(temp_dir, manifest)
            script_content = _generate_update_script_manifest(
                current_dir, temp_dir, manifest
            )
            encoding = "ansi"
        else:
            # 回退模式：兼容无 manifest 的旧版更新包
            logger.info("使用回退模式进行全量更新")
            script_content = _generate_update_script_fallback(current_dir, temp_dir)
            encoding = "utf-8-sig"  # 回退模式需要 UTF-8 以支持中文文件名

        # 创建更新脚本
        updater_script = current_dir / "_updater.bat"
        updater_script.write_text(script_content, encoding=encoding, errors="replace")

        logger.info("启动更新脚本并退出程序")
        subprocess.Popen(
            ["cmd.exe", "/c", str(updater_script)],
            creationflags=subprocess.CREATE_NEW_CONSOLE,
        )

        # 延迟退出，确保响应返回给前端
        import threading

        def delayed_exit() -> None:
            import os
            import time

            time.sleep(1)
            os._exit(0)

        threading.Thread(target=delayed_exit, daemon=True).start()

        return True

    except Exception as exc:
        logger.error(f"安装更新失败: {exc}")
        return False
