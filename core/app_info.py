"""应用版本信息：优先从 git 提交派生（随提交自动更新），无 git 环境回退 pyproject.toml。"""

from __future__ import annotations

import subprocess
import tomllib
from functools import lru_cache
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_FALLBACK_VERSION = "0.0.0"


def _run_git(*args: str) -> str | None:
    try:
        result = subprocess.run(
            ["git", *args],
            cwd=_PROJECT_ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="ignore",
            timeout=5,
        )
        if result.returncode != 0:
            return None
        return result.stdout.strip() or None
    except Exception:
        return None


def _is_dirty() -> bool:
    status = _run_git("status", "--porcelain")
    return bool(status)


@lru_cache(maxsize=1)
def get_app_version() -> str:
    """版本号：v{提交数}-{短hash}[-dirty]，如 v25-564a2e5、v25-564a2e5-dirty。

    随每次 git 提交自动更新；工作区有未提交改动时追加 -dirty。
    git 不可用（如打包环境）时回退 pyproject.toml 的 version。
    """
    count = _run_git("rev-list", "--count", "HEAD")
    short = _run_git("rev-parse", "--short", "HEAD")
    if count and short:
        version = f"v{count}-{short}"
        if _is_dirty():
            version += "-dirty"
        return version

    pyproject = _PROJECT_ROOT / "pyproject.toml"
    try:
        with pyproject.open("rb") as f:
            return str(tomllib.load(f)["project"]["version"])
    except Exception:
        return _FALLBACK_VERSION


@lru_cache(maxsize=1)
def get_commit_info() -> str:
    """最新提交信息：`{短hash} {提交标题}`，如 `564a2e5 feat(category): ...`；取不到返回空串。"""
    short = _run_git("rev-parse", "--short", "HEAD")
    subject = _run_git("log", "-1", "--pretty=format:%s")
    if short and subject:
        return f"{short} {subject}"
    return ""
