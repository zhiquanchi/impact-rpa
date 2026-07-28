"""邀请 Campaign 的结果数据类。"""

from dataclasses import dataclass, field


@dataclass(frozen=True)
class InviteCampaignResult:
    """邀请 Campaign 执行结果。"""

    success: bool
    message: str = ""
    status_code: int | None = None
    campaign_id: list[str] = field(default_factory=list)
    influencer_id: str | int | None = None
    response_body: str = ""


__all__ = ["InviteCampaignResult"]
