"""Invite to Campaign 脚本入口。

用法：
    python scripts/invite_to_campaign.py
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from loguru import logger
from rich.console import Console

from domain.invite_campaign_service import InviteCampaignService
from infra.browser_manager import BrowserManager

# ========== 配置 ==========
CAMPAIGN_NAME = "TORRAS Japan"
PERSONALIZED_MESSAGE = None  # None 或 "" 表示不填写
CARD_INDEX = 1  # 操作第几个卡片（从 1 开始）
# ==========================


def setup_logger() -> None:
    logger.remove()
    logger.add(
        sys.stderr,
        level="INFO",
        format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {message}",
    )
    logger.add(
        "logs/invite_campaign_{time:YYYY-MM-DD}.log",
        level="INFO",
        format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {message}",
        rotation="00:00",
        retention="30 days",
        encoding="utf-8",
    )


def main() -> None:
    setup_logger()
    console = Console(highlight=False)

    browser = BrowserManager(log=logger)
    if not browser.init():
        console.print("[red]浏览器连接失败[/red]")
        sys.exit(1)

    logger.info(f"当前页面: {browser.tab.title}")
    logger.info(f"URL: {browser.tab.url}")

    service = InviteCampaignService(browser)

    logger.info(
        f"开始 Invite to Campaign (campaign: {CAMPAIGN_NAME}, 卡片: 第 {CARD_INDEX} 个)"
    )

    result = service.invite(
        campaign_name=CAMPAIGN_NAME,
        message=PERSONALIZED_MESSAGE,
        card_index=CARD_INDEX,
    )

    if result.success:
        console.print(f"\n[bold green]OK 邀请发送成功！{result.message}[/bold green]")
        logger.success(f"邀请发送成功！{result.message}")
    else:
        console.print(f"\n[bold red]FAIL 邀请发送失败！{result.message}[/bold red]")
        logger.error(f"邀请发送失败！{result.message}")

    if result.status_code:
        logger.info(f"状态码: {result.status_code}")
    if result.campaign_id:
        logger.info(f"campaignId: {result.campaign_id}")
    if result.influencer_id:
        logger.info(f"influencerId: {result.influencer_id}")


if __name__ == "__main__":
    main()
