"""从配置创建通知渠道。"""

from __future__ import annotations

from loguru import logger

from core.notification.channel import NotificationChannel
from core.notification.feishu_channel import FeishuChannel


def create_channels(channels_config: list[dict[str, object]]) -> list[NotificationChannel]:
    channels: list[NotificationChannel] = []
    for item in channels_config or []:
        if not isinstance(item, dict) or not item.get("enabled", True):
            continue

        channel_type = item.get("type", "")
        if channel_type == "feishu":
            webhook_url = item.get("webhook_url", "")
            url = webhook_url if isinstance(webhook_url, str) else str(webhook_url)
            channels.append(FeishuChannel(webhook_url=url))
        else:
            logger.warning(f"未知通知渠道类型: {channel_type!r}，已跳过")

    return channels
