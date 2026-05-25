from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


class PartnerGroupsApiSettings(BaseModel):
    model_config = ConfigDict(extra="ignore")

    url: str = ""
    method: str = "POST"
    headers: dict[str, Any] = Field(default_factory=dict)
    body: Any = None
    csrf_meta_selector: str = ""
    csrf_header_name: str = "X-CSRF-Token"
    success_status_min: int = 200
    success_status_max: int = 299


class PartnerGroupsSettings(BaseModel):
    model_config = ConfigDict(extra="ignore")

    mode: str = "ui"
    api: PartnerGroupsApiSettings = Field(default_factory=PartnerGroupsApiSettings)
    id_by_name: dict[str, str] = Field(default_factory=dict)


class VisionRpaSettings(BaseModel):
    model_config = ConfigDict(extra="ignore")

    enabled: bool = False
    api_key: str = ""
    base_url: str = ""
    model: str = "gpt-4o"
    max_tokens: int = 1024
    temperature: float = 0.1
    timeout: int = 30
    browser_ui_offset_x: int = 0
    browser_ui_offset_y: int = 0


class NotificationChannelSettings(BaseModel):
    model_config = ConfigDict(extra="ignore")

    type: str = "feishu"
    enabled: bool = True
    webhook_url: str = ""


class NotificationSettings(BaseModel):
    model_config = ConfigDict(extra="ignore")

    enabled: bool = True
    on_complete: bool = True
    on_error: bool = True
    on_early_exit: bool = True
    channels: list[NotificationChannelSettings] = Field(
        default_factory=lambda: [NotificationChannelSettings()]
    )


class AppSettings(BaseModel):
    model_config = ConfigDict(extra="ignore")

    max_proposals: int = Field(default=10, ge=1)
    scroll_delay: float = Field(default=1.0, gt=0)
    click_delay: float = Field(default=0.5, ge=0)
    modal_wait: float = Field(default=20.0, gt=0)
    dry_run: bool = False
    template_term: str = ""
    input_partner_groups_tag: bool = True
    partner_groups_debug_logging: bool = False
    partner_groups_batch_create_done: bool = False
    partner_groups: PartnerGroupsSettings = Field(default_factory=PartnerGroupsSettings)
    screenshot_on_error: bool = True
    screenshot_full_page: bool = False
    vision_rpa: VisionRpaSettings = Field(default_factory=VisionRpaSettings)
    notifications: NotificationSettings = Field(default_factory=NotificationSettings)


class SettingsDialogUpdate(BaseModel):
    """设置对话框可编辑字段的校验模型。"""

    max_proposals: int = Field(ge=1)
    scroll_delay: float = Field(gt=0)
    click_delay: float = Field(ge=0)
    modal_wait: float = Field(gt=0)
    dry_run: bool = False
    input_partner_groups_tag: bool = True

    @field_validator(
        "max_proposals", "scroll_delay", "click_delay", "modal_wait", mode="before"
    )
    @classmethod
    def _strip_numeric_inputs(cls, value: object) -> object:
        if isinstance(value, str):
            return value.strip()
        return value


def get_feishu_channel(notif: NotificationSettings) -> NotificationChannelSettings:
    for item in notif.channels:
        if item.type == "feishu":
            return item
    return NotificationChannelSettings(type="feishu", enabled=False, webhook_url="")
