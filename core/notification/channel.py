"""通知渠道接口。"""

from __future__ import annotations

from typing import Protocol

from core.notification.types import ProposalRunEvent, ProposalRunPayload


class NotificationChannel(Protocol):
    def send(self, event: ProposalRunEvent, payload: ProposalRunPayload) -> None: ...
