"""PyQt 桌面版今日发送计数，按自然日持久化。"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path


class DailySentCounter:
    def __init__(self, stats_file: Path):
        self.stats_file = stats_file

    def _today(self) -> str:
        return datetime.now().strftime("%Y-%m-%d")

    def _load(self) -> dict[str, int | str]:
        try:
            if self.stats_file.exists():
                data = json.loads(self.stats_file.read_text(encoding="utf-8"))
                if data.get("date") == self._today():
                    return {"date": self._today(), "count": int(data.get("count", 0))}
        except Exception:
            pass
        return {"date": self._today(), "count": 0}

    def _save(self, data: dict[str, int | str]) -> None:
        self.stats_file.parent.mkdir(parents=True, exist_ok=True)
        self.stats_file.write_text(
            json.dumps(data, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    def get_count(self) -> int:
        count = self._load()["count"]
        return int(count)

    def add(self, count: int) -> int:
        if count <= 0:
            return self.get_count()
        data = self._load()
        data["count"] = int(data["count"]) + count
        self._save(data)
        return int(data["count"])
