"""飞书 Webhook 通知渠道。"""

from __future__ import annotations

import requests
from loguru import logger

from core.notification.types import ProposalRunEvent, ProposalRunPayload


class FeishuChannel:
    def __init__(self, webhook_url: str):
        self.webhook_url = webhook_url.strip()

    def send(self, event: ProposalRunEvent, payload: ProposalRunPayload) -> None:
        if not self.webhook_url:
            logger.warning("飞书通知渠道未配置 webhook_url，已跳过")
            return

        text = payload.format_message(event)
        body = {"msg_type": "text", "content": {"text": text}}

        try:
            resp = requests.post(self.webhook_url, json=body, timeout=10)
            if resp.status_code != 200:
                logger.warning(
                    f"飞书通知发送失败: HTTP {resp.status_code}, body={resp.text[:200]}"
                )
                return
            data = resp.json()
            if data.get("code") not in (0, None):
                logger.warning(f"飞书通知返回错误: {data}")
        except Exception as e:
            logger.warning(f"飞书通知发送异常: {e}")
