"""今日招募（邀请到 Campaign）成功/失败计数，按自然日持久化。"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path


class DailyInviteCounter:
    def __init__(self, stats_file: Path):
        self.stats_file = stats_file

    def _today(self) -> str:
        return datetime.now().strftime("%Y-%m-%d")

    def _load(self) -> dict:
        try:
            if self.stats_file.exists():
                data = json.loads(self.stats_file.read_text(encoding="utf-8"))
                if data.get("date") == self._today():
                    return {
                        "date": self._today(),
                        "success": int(data.get("success", 0)),
                        "failed": int(data.get("failed", 0)),
                    }
        except Exception:
            pass
        return {"date": self._today(), "success": 0, "failed": 0}

    def _save(self, data: dict) -> None:
        self.stats_file.parent.mkdir(parents=True, exist_ok=True)
        self.stats_file.write_text(
            json.dumps(data, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    def get_counts(self) -> tuple[int, int]:
        """返回 (今日成功数, 今日失败数)。"""
        data = self._load()
        return int(data["success"]), int(data["failed"])

    def add(self, success: int = 0, failed: int = 0) -> tuple[int, int]:
        """累加成功/失败数并返回最新 (成功数, 失败数)。"""
        if success <= 0 and failed <= 0:
            return self.get_counts()
        data = self._load()
        data["success"] = int(data["success"]) + max(success, 0)
        data["failed"] = int(data["failed"]) + max(failed, 0)
        self._save(data)
        return int(data["success"]), int(data["failed"])
