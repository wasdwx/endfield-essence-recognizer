"""更新安装器和 manifest 生成的测试。"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

# 将项目根目录加入 sys.path，以便导入 scripts 模块
_PROJECT_ROOT = Path(__file__).parent.parent.parent.parent.resolve()
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from scripts.generate_manifest import (  # noqa: E402
    MANIFEST_RELATIVE_PATH,
    PROTECTED_PATHS,
    generate_manifest,
    scan_dist_directory,
)


@pytest.fixture()
def fake_dist_dir(tmp_path: Path) -> Path:
    """创建一个模拟的 dist 目录结构。"""
    dist = tmp_path / "endfield-essence-recognizer"
    dist.mkdir()

    # 模拟典型 PyInstaller 输出
    (dist / "endfield-essence-recognizer.exe").write_text("exe")
    internal = dist / "_internal"
    internal.mkdir()
    (internal / "python3.dll").write_text("dll")
    (internal / "cv2").mkdir()
    (internal / "cv2" / "cv2.pyd").write_text("pyd")

    resources = dist / "resources"
    resources.mkdir()
    (resources / "images").mkdir()
    (resources / "images" / "error.webp").write_text("webp")

    (dist / "README.md").write_text("readme")
    (dist / "config.json").write_text("{}")  # 用户配置，应该被 protected

    return dist


class TestScanDistDirectory:
    """扫描 dist 目录的测试。"""

    def test_scan_returns_all_files(self, fake_dist_dir: Path) -> None:
        """应返回目录中所有文件的相对路径。"""
        files = scan_dist_directory(fake_dist_dir)
        assert "endfield-essence-recognizer.exe" in files
        assert "_internal/python3.dll" in files
        assert "_internal/cv2/cv2.pyd" in files
        assert "resources/images/error.webp" in files
        assert "README.md" in files
        assert "config.json" in files

    def test_scan_uses_forward_slashes(self, fake_dist_dir: Path) -> None:
        """路径应统一使用正斜杠。"""
        files = scan_dist_directory(fake_dist_dir)
        for file_path in files:
            assert "\\" not in file_path, f"路径包含反斜杠: {file_path}"

    def test_scan_sorted_output(self, fake_dist_dir: Path) -> None:
        """输出应按字母顺序排序。"""
        files = scan_dist_directory(fake_dist_dir)
        assert files == sorted(files)

    def test_scan_nonexistent_dir_raises(self, tmp_path: Path) -> None:
        """不存在的目录应抛出异常。"""
        with pytest.raises(FileNotFoundError):
            scan_dist_directory(tmp_path / "nonexistent")


class TestGenerateManifest:
    """生成 manifest 的测试。"""

    def test_manifest_structure(self, fake_dist_dir: Path) -> None:
        """manifest 应包含 version、files、protected 三个字段。"""
        manifest = generate_manifest(fake_dist_dir, "1.0.0")
        assert "version" in manifest
        assert "files" in manifest
        assert "protected" in manifest

    def test_manifest_version(self, fake_dist_dir: Path) -> None:
        """版本号应与传入参数一致。"""
        manifest = generate_manifest(fake_dist_dir, "2.3.4")
        assert manifest["version"] == "2.3.4"

    def test_manifest_files_count(self, fake_dist_dir: Path) -> None:
        """文件数量应匹配实际文件数 + manifest.json 自身。"""
        manifest = generate_manifest(fake_dist_dir, "1.0.0")
        # 6 个实际文件 + manifest.json 自身被自动加入 files 列表
        assert len(manifest["files"]) == 7

    def test_manifest_includes_self(self, fake_dist_dir: Path) -> None:
        """manifest.json 自身必须在 files 列表中。"""
        manifest = generate_manifest(fake_dist_dir, "1.0.0")
        assert MANIFEST_RELATIVE_PATH in manifest["files"]

    def test_manifest_protected_defaults(self, fake_dist_dir: Path) -> None:
        """默认应使用 PROTECTED_PATHS 作为保护列表。"""
        manifest = generate_manifest(fake_dist_dir, "1.0.0")
        assert manifest["protected"] == sorted(PROTECTED_PATHS)
        assert "config.json" in manifest["protected"]
        assert "logs/" in manifest["protected"]

    def test_manifest_custom_protected(self, fake_dist_dir: Path) -> None:
        """应支持自定义保护列表。"""
        custom = ["my_data.json", "custom_dir/"]
        manifest = generate_manifest(fake_dist_dir, "1.0.0", protected_paths=custom)
        assert manifest["protected"] == sorted(custom)

    def test_manifest_json_serializable(self, fake_dist_dir: Path) -> None:
        """manifest 应可序列化为 JSON。"""
        manifest = generate_manifest(fake_dist_dir, "1.0.0")
        text = json.dumps(manifest, ensure_ascii=False)
        restored = json.loads(text)
        assert restored == manifest


class TestProtectedPaths:
    """受保护路径的测试。"""

    def test_config_json_is_protected(self) -> None:
        """config.json 必须在保护列表中。"""
        assert "config.json" in PROTECTED_PATHS

    def test_logs_dir_is_protected(self) -> None:
        """logs/ 目录必须在保护列表中。"""
        assert "logs/" in PROTECTED_PATHS

    def test_screenshots_dir_is_protected(self) -> None:
        """screenshots/ 目录必须在保护列表中。"""
        assert "screenshots/" in PROTECTED_PATHS


class TestDeleteListGeneration:
    """删除清单生成的测试。"""

    def test_delete_all_old_files_except_protected(self, tmp_path: Path) -> None:
        """应删除旧 manifest 中的所有文件（排除 protected）。"""
        from src.endfield_essence_recognizer.updater.installer import (
            _prepare_delete_list,
        )

        # 创建旧 manifest
        current_dir = tmp_path / "current"
        current_dir.mkdir()
        old_manifest = {
            "version": "0.8.0",
            "files": ["app.exe", "old.dll", "lib.pyd", "config.json"],
            "protected": ["config.json", "logs/"],
        }
        (current_dir / "manifest.json").write_text(
            json.dumps(old_manifest), encoding="utf-8"
        )

        # 新 manifest
        temp_dir = tmp_path / "temp"
        temp_dir.mkdir()
        new_manifest = {
            "version": "0.9.0",
            "files": ["app.exe", "new.dll", "lib.pyd"],
            "protected": ["config.json", "logs/"],
        }

        # 生成删除清单
        _prepare_delete_list(current_dir, temp_dir, new_manifest)

        # 读取删除清单
        delete_list = (temp_dir / "__to_delete.txt").read_text(encoding="utf-8")
        deleted_files = [line for line in delete_list.strip().split("\n") if line]

        # 验证：应删除所有旧文件（排除 protected）
        assert "app.exe" in deleted_files
        assert "old.dll" in deleted_files
        assert "lib.pyd" in deleted_files
        assert "config.json" not in deleted_files  # protected

    def test_no_old_manifest_only_cleans_program_files_in_manifest_dirs(
        self, tmp_path: Path
    ) -> None:
        """首次升级（无旧 manifest）只清理 manifest 目录下的旧程序文件，不删用户文件。"""
        from src.endfield_essence_recognizer.updater.installer import (
            _prepare_delete_list,
        )

        current_dir = tmp_path / "current"
        current_dir.mkdir()
        _internal = current_dir / "_internal"
        _internal.mkdir()
        # 旧程序文件在 manifest 目录下 → 应删除
        (_internal / "old.dll").write_text("old")
        (_internal / "old.exe").write_text("old")
        # 新文件 → 不删除（复制阶段覆盖）
        (_internal / "new.dll").write_text("new")
        # 根目录的用户文件 → 不删除
        (current_dir / "my_data.txt").write_text("user")
        (current_dir / "config.json").write_text("{}")  # protected
        # 根目录的旧程序文件（不在 manifest 目录下）→ 不删除
        (current_dir / "old_root.exe").write_text("old")
        # protected 目录
        (current_dir / "logs").mkdir()
        (current_dir / "logs" / "app.log").write_text("log")

        temp_dir = tmp_path / "temp"
        temp_dir.mkdir()
        new_manifest = {
            "version": "0.9.0",
            "files": [
                "app.exe",
                "_internal/new.dll",
                "_internal/manifest.json",
                "config.json",
                "logs/app.log",
            ],
            "protected": ["config.json", "logs/"],
        }

        _prepare_delete_list(current_dir, temp_dir, new_manifest)

        delete_list = (temp_dir / "__to_delete.txt").read_text(encoding="utf-8")
        deleted_files = [line for line in delete_list.strip().split("\n") if line]

        # _internal/ 下的旧程序文件 → 删除（Windows 路径格式）
        assert "_internal\\old.dll" in deleted_files
        assert "_internal\\old.exe" in deleted_files
        # _internal/ 下的新文件 → 不删除
        assert "_internal\\new.dll" not in deleted_files
        # 根目录的用户文件 → 不删除
        assert "my_data.txt" not in deleted_files
        # 根目录的旧程序文件（不在 manifest 目录下）→ 不删除
        assert "old_root.exe" not in deleted_files
        # protected → 不删除
        assert "config.json" not in deleted_files
        assert "logs\\app.log" not in deleted_files

    def test_no_old_manifest_empty_install_dir(self, tmp_path: Path) -> None:
        """首次升级且安装目录为空时，删除清单也应为空。"""
        from src.endfield_essence_recognizer.updater.installer import (
            _prepare_delete_list,
        )

        current_dir = tmp_path / "current"
        current_dir.mkdir()
        # 安装目录为空

        temp_dir = tmp_path / "temp"
        temp_dir.mkdir()
        new_manifest = {
            "version": "0.9.0",
            "files": ["app.exe", "new.dll"],
            "protected": ["config.json"],
        }

        _prepare_delete_list(current_dir, temp_dir, new_manifest)

        delete_list = (temp_dir / "__to_delete.txt").read_text(encoding="utf-8")
        assert delete_list.strip() == ""

    def test_protected_prefix_matching(self, tmp_path: Path) -> None:
        """protected 目录下的文件应被保护（前缀匹配）。"""
        from src.endfield_essence_recognizer.updater.installer import (
            _prepare_delete_list,
        )

        current_dir = tmp_path / "current"
        current_dir.mkdir()
        old_manifest = {
            "version": "0.8.0",
            "files": ["app.exe", "logs/app.log", "logs/error.log"],
            "protected": ["logs/"],
        }
        (current_dir / "manifest.json").write_text(
            json.dumps(old_manifest), encoding="utf-8"
        )

        temp_dir = tmp_path / "temp"
        temp_dir.mkdir()
        new_manifest = {
            "version": "0.9.0",
            "files": ["app.exe"],
            "protected": ["logs/"],
        }

        _prepare_delete_list(current_dir, temp_dir, new_manifest)

        delete_list = (temp_dir / "__to_delete.txt").read_text(encoding="utf-8")
        deleted_files = [line for line in delete_list.strip().split("\n") if line]

        # logs/ 下的文件应被保护
        assert "app.exe" in deleted_files
        assert "logs/app.log" not in deleted_files
        assert "logs/error.log" not in deleted_files


class TestCopyListExcludesProtected:
    """复制清单应排除 protected 文件。"""

    def test_protected_excluded_from_copy_list(self, tmp_path: Path) -> None:
        """protected 文件不应出现在 __manifest_files.txt 中。"""
        from src.endfield_essence_recognizer.updater.installer import (
            _prepare_manifest_files_list,
        )

        temp_dir = tmp_path / "temp"
        temp_dir.mkdir()
        manifest = {
            "version": "0.9.0",
            "files": ["app.exe", "config.json", "lib.dll", "logs/app.log"],
            "protected": ["config.json", "logs/"],
        }

        _prepare_manifest_files_list(temp_dir, manifest)

        copy_list = (temp_dir / "__manifest_files.txt").read_text(encoding="utf-8")
        copy_files = [line for line in copy_list.strip().split("\n") if line]

        assert "app.exe" in copy_files
        assert "lib.dll" in copy_files
        assert "config.json" not in copy_files
        assert "logs/app.log" not in copy_files

    def test_manifest_json_always_in_copy_list(self, tmp_path: Path) -> None:
        """manifest.json 自身（_internal/manifest.json）必须在复制清单中。"""
        from src.endfield_essence_recognizer.updater.installer import (
            MANIFEST_RELATIVE_PATH,
            _prepare_manifest_files_list,
        )

        temp_dir = tmp_path / "temp"
        temp_dir.mkdir()
        manifest = {
            "version": "0.9.0",
            "files": ["app.exe", MANIFEST_RELATIVE_PATH],
            "protected": ["config.json"],
        }

        _prepare_manifest_files_list(temp_dir, manifest)

        copy_list = (temp_dir / "__manifest_files.txt").read_text(encoding="utf-8")
        copy_files = [line for line in copy_list.strip().split("\n") if line]

        # Windows 路径格式
        assert MANIFEST_RELATIVE_PATH.replace("/", "\\") in copy_files


class TestProtectedBackupList:
    """protected 文件备份清单测试。"""

    def test_protected_files_list(self, tmp_path: Path) -> None:
        """__protected_files.txt 应包含非目录的 protected 条目。"""
        from src.endfield_essence_recognizer.updater.installer import (
            _prepare_protected_files_list,
        )

        temp_dir = tmp_path / "temp"
        temp_dir.mkdir()
        manifest = {
            "version": "0.9.0",
            "files": ["app.exe", "config.json"],
            "protected": ["config.json", "logs/", ".env"],
        }

        _prepare_protected_files_list(temp_dir, manifest)

        protected_list = (temp_dir / "__protected_files.txt").read_text(
            encoding="utf-8"
        )
        entries = [line for line in protected_list.strip().split("\n") if line]

        # 目录条目（logs/）不应在备份列表中
        assert "logs/" not in entries
        # 文件条目应在备份列表中
        assert "config.json" in entries
        assert ".env" in entries


class TestPathTraversalProtection:
    """路径穿越保护测试。"""

    def test_normal_path_allowed(self, tmp_path: Path) -> None:
        """正常路径不应被拒绝。"""
        from src.endfield_essence_recognizer.updater.installer import (
            _is_path_traversal,
        )

        assert not _is_path_traversal(tmp_path, "app.exe")
        assert not _is_path_traversal(tmp_path, "_internal/python3.dll")
        assert not _is_path_traversal(tmp_path, "resources/images/icon.png")

    def test_dotdot_traversal_rejected(self, tmp_path: Path) -> None:
        """../ 路径穿越应被拒绝。"""
        from src.endfield_essence_recognizer.updater.installer import (
            _is_path_traversal,
        )

        assert _is_path_traversal(tmp_path, "../evil.exe")
        assert _is_path_traversal(tmp_path, "subdir/../../evil.exe")
        assert _is_path_traversal(tmp_path, "_internal/../../../etc/passwd")

    def test_prefix_collision_rejected(self, tmp_path: Path) -> None:
        """前缀碰撞绕过应被拒绝（字符串前缀法的已知弱点）。"""
        from src.endfield_essence_recognizer.updater.installer import (
            _is_path_traversal,
        )

        # 使用类似前缀的目录名
        tricky_dir = tmp_path / "update"
        tricky_dir.mkdir()

        # "update_evil/../update/../../evil.exe" 不应通过
        assert _is_path_traversal(tricky_dir, "../update/../../evil.exe")

    def test_absolute_path_rejected(self, tmp_path: Path) -> None:
        """绝对路径应被拒绝。"""
        from src.endfield_essence_recognizer.updater.installer import (
            _is_path_traversal,
        )

        # 在 Linux 上测试绝对路径
        assert _is_path_traversal(tmp_path, "/etc/passwd")
