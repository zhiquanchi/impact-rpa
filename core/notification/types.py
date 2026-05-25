"""Proposal 任务通知事件与载荷类型。"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class ProposalRunEvent(str, Enum):
    COMPLETE = "complete"
    ERROR = "error"
    EARLY_EXIT = "early_exit"


@dataclass(frozen=True)
class ProposalRunPayload:
    clicked_count: int
    error_message: str | None = None
    mode: str | None = None

    def format_message(self, event: ProposalRunEvent) -> str:
        if event == ProposalRunEvent.ERROR:
            return f"发送失败: {self.error_message or '未知错误'}"
        if event == ProposalRunEvent.COMPLETE:
            return f"发送完成，共发送 {self.clicked_count} 个 Proposal"
        return f"任务提前结束，当前批次共发送 {self.clicked_count} 个 Proposal"
