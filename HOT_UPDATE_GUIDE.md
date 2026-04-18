# 热更新功能说明

## 功能概述

应用内一键更新到最新版本，支持多镜像源、代理配置、实时进度显示。

## 实现原理

1. **版本检查** - 启动时自动检查一图流 API
2. **下载更新** - 后台下载更新包，WebSocket 实时推送进度
3. **自动安装** - 批处理脚本替换文件并重启程序

## 核心功能

### 一键更新
- 点击"一键更新"按钮直接完成下载和安装
- 实时显示下载进度、速度、文件大小
- 支持取消下载（使用任务取消机制立即中断网络请求）
- 失败时显示错误信息和重试按钮，无需重新检查更新

### 多镜像源
- 一图流 API 返回的镜像（global、cn）
- GitHub 官方
- ghproxy 镜像（多个节点）
- gitmirror、gh.con.sh、githubproxy.cc 等镜像
- fastgit 镜像
- 下载过程中可动态切换

### 代理支持
- 可配置代理端口（默认 7890）
- 下载过程中可启用/禁用
- 格式：`http://127.0.0.1:{port}`

## 新增文件

### 后端
- `src/endfield_essence_recognizer/updater/` - 更新模块
  - `__init__.py` - 模块入口
  - `checker.py` - 版本检查
  - `downloader.py` - 下载管理
  - `installer.py` - 安装逻辑
  - `manager.py` - 更新管理器
  - `mirrors.py` - 镜像源配置
- `src/endfield_essence_recognizer/api/routes/update.py` - 更新 API
- `src/endfield_essence_recognizer/api/websockets/update_progress.py` - 进度推送

### 前端
- 修改 `frontend/src/composables/useUpdateChecker.ts` - 一键更新逻辑
- 修改 `frontend/src/components/UpdateDialogs.vue` - 进度对话框
- 修改 `frontend/src/pages/settings.vue` - 更新设置

### 配置
- `pyproject.toml` - 添加 `packaging`、`aiofiles` 依赖
- `src/endfield_essence_recognizer/schemas/user_setting.py` - 新增 `update_mirror` 和 `update_proxy` 字段
- `src/endfield_essence_recognizer/api/router.py` - 注册更新路由

## API 接口

### GET /api/update/check
检查是否有新版本（数据来源：一图流 API）

```json
{
  "has_update": true,
  "update_info": {
    "version": "0.9.0",
    "download_url": "https://github.com/.../release.zip",
    "mirrors": {
      "global": {"downloadUrl": "https://github.com/..."},
      "cn": {"downloadUrl": "https://cos.yituliu.cn/..."}
    }
  }
}
```

### POST /api/update/install
下载并安装更新

```json
{
  "success": true
}
```

### POST /api/update/cancel
取消当前下载

### GET /api/update/mirrors
获取可用镜像源列表

```json
{
  "mirrors": [
    {"title": "GitHub 官方", "value": "github"},
    {"title": "ghproxy 镜像", "value": "ghproxy"}
  ]
}
```

### WebSocket /ws/update/progress
实时推送下载进度

```json
{
  "progress": 45.5,
  "downloaded": 5242880,
  "total": 11534336,
  "speed": 1048576
}
```

## 使用方式

1. **自动检查** - 程序启动时自动检查
2. **手动检查** - 点击顶部工具栏更新按钮
3. **一键更新** - 发现新版本后点击"一键更新"
4. **配置设置** - 在设置页面配置镜像源和代理

## 更新流程

### 基于 Manifest 的增量更新

更新包中包含一个 `manifest.json` 文件（由 CI 在构建时自动生成），描述了该版本应有的所有文件和受保护路径：

```json
{
  "version": "0.9.0",
  "files": [
    "endfield-essence-recognizer.exe",
    "_internal/python3.dll",
    "README.md",
    ...
  ],
  "protected": [
    "config.json",
    "logs/",
    "screenshots/",
    ...
  ]
}
```

安装时根据 manifest 执行三步操作：
1. **删除旧版本文件**：读取目标目录中的旧 manifest.json，删除其中列出的所有文件（排除 protected 列表）
2. **复制新版本文件**：将新 manifest 中列出的所有文件从更新包复制到目标目录
3. **清理**：删除临时更新文件

**安全特性**：
- 只删除程序自己的旧文件（在旧 manifest 中列出的）
- 用户手动添加的文件不会被删除（不在旧 manifest 中）
- 所有程序文件都会被新版本替换（全量复制）
- protected 列表保护用户数据

**示例场景**：
- 目标目录现有：`app.exe(v0.8)`, `old.dll`, `config.json`, `user_notes.txt`
- 旧 manifest.files：`["app.exe", "old.dll"]`
- 新 manifest.files：`["app.exe", "new.dll"]`
- 执行结果：
  - 删除：`app.exe(v0.8)`, `old.dll`（旧版本文件）
  - 保留：`config.json`（protected）, `user_notes.txt`（用户文件）
  - 复制：`app.exe(v0.9)`, `new.dll`（新版本文件）

如更新包中不包含 manifest.json（兼容旧版更新包），则回退到硬编码删除列表 + 全量复制的方案。

### 执行步骤

1. 用户点击"一键更新"
2. 显示进度对话框，建立 WebSocket 连接
3. 后端下载更新包到 `_updates` 目录
4. 实时推送下载进度
5. 解压到临时目录 `_update_temp`
6. 读取 manifest.json（如存在）
7. 对比新旧 manifest，生成删除清单和文件列表
8. 生成批处理脚本（manifest 模式或回退模式）
9. 启动脚本并退出当前程序
10. 脚本等待进程完全退出和文件句柄释放
11. 删除旧版本文件（基于旧 manifest）
12. 复制新版本文件（基于新 manifest）
13. 自动启动新版本程序
14. 清理临时文件和更新包

## 安全特性

### 文件保护

更新通过 manifest 的 `protected` 列表保护用户数据，以下路径在更新时不会被删除：

- `config.json` - 用户配置
- `logs/` - 运行日志
- `screenshots/` - 用户截图
- `_updates/` - 下载缓存
- `.env` - 环境变量配置

如需修改保护列表，编辑 `scripts/generate_manifest.py` 中的 `PROTECTED_PATHS` 常量。

### 路径穿越防护

解压更新包时会校验每个 zip 条目的目标路径，拒绝包含 `../` 等路径穿越攻击的条目。

## 注意事项

1. 需要管理员权限
2. 更新过程中会短暂关闭程序
3. 确保网络连接正常
4. 更新包从 GitHub Releases 获取

## 配置说明

### 后端配置
修改 `src/endfield_essence_recognizer/updater/checker.py`：

```python
UPDATE_CHECK_URL = "https://cos.yituliu.cn/endfield/endfield-essence-recognizer/version.json"
```

### 用户配置
在设置页面或更新对话框中配置：
- 镜像源选择
- 代理端口（默认 7890）
- 是否启用代理

## 发布新版本

1. 更新 `pyproject.toml` 中的版本号（`version.py` 通过 `importlib.metadata` 动态读取包版本，无需手动修改）
2. 构建并打包应用
3. CI 会自动在 PyInstaller 构建后执行 `scripts/generate_manifest.py`，将 manifest.json 打入 zip 包
4. 在 GitHub 创建 Release 并上传 zip 包
5. 用户端会自动检测到新版本

**本地测试 manifest 生成：**
```bash
# 构建后手动生成 manifest
uv run python scripts/generate_manifest.py --dist-dir dist/endfield-essence-recognizer

# 或指定自定义路径
uv run python scripts/generate_manifest.py --dist-dir /path/to/dist --version 0.9.0
```
