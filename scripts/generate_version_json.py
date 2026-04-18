from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


def read_version_from_pyproject(project_root: Path) -> str:
    pyproject_path = project_root / 'pyproject.toml'
    if not pyproject_path.is_file():
        raise FileNotFoundError(f'pyproject.toml 不存在: {pyproject_path}')

    for line in pyproject_path.read_text(encoding='utf-8').splitlines():
        stripped = line.strip()
        if stripped.startswith('version') and '=' in stripped:
            return stripped.split('=', maxsplit=1)[1].strip().strip('"').strip("'")

    raise ValueError('pyproject.toml 中未找到 version 字段')


def normalize_version(value: str) -> str:
    return value[1:] if value.startswith('v') else value


def compute_file_sha256(file_path: Path) -> str:
    sha256 = hashlib.sha256()
    with open(file_path, 'rb') as handle:
        for chunk in iter(lambda: handle.read(8192), b''):
            sha256.update(chunk)
    return sha256.hexdigest()


def parse_mirror(raw: str) -> tuple[str, dict[str, str]]:
    if '=' not in raw:
        raise ValueError(f'镜像参数格式错误: {raw}')
    key, url = raw.split('=', maxsplit=1)
    key = key.strip()
    url = url.strip()
    if not key or not url:
        raise ValueError(f'镜像参数格式错误: {raw}')
    return key, {'downloadUrl': url}


def main() -> None:
    parser = argparse.ArgumentParser(description='生成 GitHub Pages version.json')
    parser.add_argument('--version', type=str, default=None, help='程序版本号，可带 v 前缀')
    parser.add_argument('--download-url', type=str, required=True, help='主下载地址')
    parser.add_argument('--asset-path', type=Path, default=None, help='用于计算 sha256 的本地文件')
    parser.add_argument('--sha256', type=str, default=None, help='手动指定 sha256')
    parser.add_argument('--output', type=Path, required=True, help='输出文件路径')
    parser.add_argument('--mirror', action='append', default=[], help='附加镜像，格式为 key=url')
    parser.add_argument('--published-at', type=str, default=None, help='可选发布时间')
    parser.add_argument('--notes-url', type=str, default=None, help='可选发布说明链接')
    args = parser.parse_args()

    project_root = Path(__file__).resolve().parent.parent
    latest_version = normalize_version(args.version or read_version_from_pyproject(project_root))

    sha256 = args.sha256
    if args.asset_path is not None:
        sha256 = compute_file_sha256(args.asset_path)

    mirrors: dict[str, dict[str, str]] = {'github': {'downloadUrl': args.download_url}}
    for raw in args.mirror:
        key, value = parse_mirror(raw)
        mirrors[key] = value

    payload: dict[str, object] = {
        'latestVersion': latest_version,
        'downloadUrl': args.download_url,
        'mirrors': mirrors,
    }
    if sha256:
        payload['sha256'] = sha256
    if args.published_at:
        payload['publishedAt'] = args.published_at
    if args.notes_url:
        payload['notesUrl'] = args.notes_url

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + '\n',
        encoding='utf-8',
    )


if __name__ == '__main__':
    main()
