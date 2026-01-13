"""
验证 Impact 平台：在 Send Proposal 弹窗内，通过“真实点击”完成跨月选择（下个月 13 号）。

使用方式：
1) 先打开 Chrome/Edge，登录 Impact
2) 运行本脚本，它会导航到目标页面
3) 如遇登录/验证码等，按提示在浏览器完成后再继续

说明：
- 不使用 JS 直接赋值
- 需要你先在浏览器里打开一个 Send Proposal 弹窗（让 iframe 存在）
"""

import os
import sys
import time
from datetime import datetime, timedelta

from loguru import logger
from rich.console import Console
from rich.panel import Panel

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from main import BrowserManager, ConfigManager, DatePicker  # noqa: E402


IMPACT_URL = (
    "https://app.impact.com/secure/advertiser/discover/radius/fr/partner_discover.ihtml"
    "?page=marketplace&slideout_id_type=partner#businessModels=CREATORS&partnerStatuses=1"
    "&relationshipInclusions=prospecting&sortBy=reachRating&sortOrder=DESC"
)


def _next_month_date(day: int = 13) -> datetime:
    base = datetime.now().replace(day=1)
    nm = (base + timedelta(days=32)).replace(day=1)
    try:
        return nm.replace(day=day)
    except ValueError:
        # 退到月末
        return (nm + timedelta(days=32)).replace(day=1) - timedelta(days=1)


def main() -> int:
    console = Console()
    config = ConfigManager()
    browser = BrowserManager(console, config)
    picker = DatePicker(console)

    if not browser.init():
        console.print("[red]浏览器连接失败：请先打开 Chrome/Edge 再重试[/red]")
        return 2

    console.print(Panel(IMPACT_URL, title="[cyan]目标页面[/cyan]", border_style="cyan"))

    if not browser.navigate(IMPACT_URL):
        console.print("[red]导航失败[/red]")
        return 2

    console.print(
        Panel(
            "请先在浏览器中打开一个 Send Proposal 弹窗。\n"
            "进入弹窗后，保持弹窗不关闭，然后运行脚本。",
            title="[yellow]人工步骤[/yellow]",
            border_style="yellow",
        )
    )
    time.sleep(3)

    # 获取 Proposal 弹窗 iframe（这是日期控件所在位置）
    iframe = browser.find_element('css:iframe[data-testid="uicl-modal-iframe-content"]', timeout=3)
    if not iframe:
        console.print("[red]✗ 未找到 Proposal 弹窗 iframe：请先打开 Send Proposal 弹窗[/red]")
        return 2

    # 目标：下个月 13 号
    target = _next_month_date(13)
    target_iso = target.strftime("%Y-%m-%d")
    console.print(f"[bold]目标日期（下个月）: {target_iso}[/bold]")

    # element_click：在 iframe 内点击打开日期选择器，再导航到下个月并点 13
    result = picker.select_date(
        context=iframe,
        target_date=target,
        strategies=["element_click"],
        open_picker=True,
    )

    if not result.success:
        console.print(f"[red]✗ element_click 失败: {result.error}[/red]")
        return 1

    console.print(f"[green]✓ element_click 设置成功（method={result.method}）[/green]")
    logger.info(f"目标日期={target_iso} element_click 成功")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


