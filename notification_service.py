from typing import Optional

from loguru import logger
from plyer import notification as plyer_notification
from pydantic import BaseModel

from core.notification.factory import create_channels
from core.notification.types import ProposalRunEvent, ProposalRunPayload
from core.settings_models import AppSettings


class NotificationPayload(BaseModel):
    title: str = "Impact-RPA"
    message: str
    icon: Optional[str] = None
    timeout: int = 5


class NotificationService:
    def send(self, payload: NotificationPayload) -> None:
        notify = plyer_notification.notify
        if notify is None:
            logger.warning("桌面通知不可用：plyer.notify 未初始化")
            return
        notify(
            title=payload.title,
            message=payload.message,
            app_icon=payload.icon,
            timeout=payload.timeout,
        )

    def notify_proposal_run(
        self,
        *,
        settings: AppSettings,
        clicked_count: int,
        completed_all: bool,
        error_message: str | None = None,
        mode: str | None = None,
    ) -> None:
        notif = settings.notifications

        if not notif.enabled:
            return

        if error_message:
            event = ProposalRunEvent.ERROR
            if not notif.on_error:
                return
        elif completed_all:
            event = ProposalRunEvent.COMPLETE
            if not notif.on_complete:
                return
        else:
            event = ProposalRunEvent.EARLY_EXIT
            if not notif.on_early_exit:
                return

        payload = ProposalRunPayload(
            clicked_count=clicked_count,
            error_message=error_message,
            mode=mode,
        )
        channels = create_channels([channel.model_dump() for channel in notif.channels])
        for channel in channels:
            try:
                channel.send(event, payload)
            except Exception as e:
                logger.warning(f"通知渠道发送失败: {e}")
