"""应用版本信息，读取自 pyproject.toml。"""

from __future__ import annotations

import tomllib
from pathlib import Path

_FALLBACK_VERSION = "0.0.0"


def get_app_version() -> str:
    """返回应用版本号；pyproject.toml 缺失或损坏时返回占位版本。"""
    pyproject = Path(__file__).resolve().parent.parent / "pyproject.toml"
    try:
        with pyproject.open("rb") as f:
            return str(tomllib.load(f)["project"]["version"])
    except Exception:
        return _FALLBACK_VERSION
