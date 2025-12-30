from typing import Optional
from pydantic import BaseModel
from plyer import notification


class NotificationPayload(BaseModel):
    title: str = "Impact-RPA"
    message: str
    icon: Optional[str] = None
    timeout: int = 5


class NotificationService:
    def send(self, payload: NotificationPayload) -> None:
        notification.notify(
            title=payload.title,
            message=payload.message,
            app_icon=payload.icon,
            timeout=payload.timeout,
        )
