"""
对比 Discovery 页面的 businessModels 标签与已有 Partner Groups，
报告哪些 group names 需要创建（不实际创建）。

使用方式：
    uv run python scripts/test_partner_groups_comparison.py

前提：Chrome/Edge 已打开并登录 Impact 平台。
"""
from __future__ import annotations

import sys
from pathlib import Path

# 直接 `python scripts/本文件.py` 时，sys.path[0] 是 scripts/ 目录，找不到 `scripts` 包；
# 必须在任何 `from scripts...` / `from legacy_main...` 之前把仓库根目录放进 sys.path。
REPO_ROOT = Path(__file__).resolve().parent.parent
_repo_root_s = str(REPO_ROOT)
if _repo_root_s not in sys.path:
    sys.path.insert(0, _repo_root_s)

import json
from typing import Any

from loguru import logger
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

# 复用 batch_create_partner_groups.py 中的解析模型和工具函数
from scripts.batch_create_partner_groups import (
    DiscoverTableStructureResponse,
    DiscoverSearchWidget,
    DiscoverFilterTypeItem,
    PartnerGroupResponse,
    dv_from_partner_group_record,
    extract_filtertype_values_list_from_discovery_page,
    get_partner_group_names_from_myMediaPartnerGroupsJSON,
    _normalize_response_body,
    _tags_need_to_create,
)

# 复用 legacy_main 中的 BrowserManager / ConfigManager
from legacy_main import BrowserManager, ConfigManager

DISCOVERY_URL = (
    "https://app.impact.com/secure/advertiser/discover/radius/fr/"
    "partner_discover.ihtml?page=marketplace&slideout_id_type=partner"
)

GROUPS_URL = (
    "https://app.impact.com/secure/advertiser/engage/mediapartners/"
    "view-mediapartnergroups-flow.ihtml"
)


def extract_business_models_labels(page) -> list[str]:
    """
    从 Discovery 页面提取 businessModels 筛选标签的 label 值。

    复用 extract_filtertype_values_list_from_discovery_page 抓取
    searchWidget.filterTypes 中 businessModels 的 filterValues，
    然后从中提取每项的 label 字段。
    """
    items = extract_filtertype_values_list_from_discovery_page(
        page, parameter_name="businessModels"
    )
    if not items:
        logger.warning("未获取到 businessModels 筛选值")
        return []

    labels: list[str] = []
    seen: set[str] = set()
    for item in items:
        label: str | None = None
        if isinstance(item, dict):
            label = item.get("label") or item.get("value")
        elif item is not None:
            label = str(item)

        if not label:
            continue
        label_s = label.strip()
        if label_s and label_s not in seen:
            seen.add(label_s)
            labels.append(label_s)

    logger.info(f"提取到 businessModels 标签: {len(labels)} 个")
    return labels


def get_existing_group_names_from_browser(browser) -> list[str]:
    """
    从浏览器已有的 Groups 标签页或通过新建标签页读取已有 Partner Groups。
    """
    groups_url_full = GROUPS_URL
    existing_tabs = browser.get_tabs(url="view-mediapartnergroups-flow.ihtml")
    if existing_tabs:
        groups_tab = existing_tabs[0]
        logger.info("复用已打开的 Partner Groups 标签页。")
    else:
        logger.info("未找到 Groups 标签页，新开一个。")
        groups_tab = browser.new_tab(url=groups_url_full)

    try:
        browser.activate_tab(groups_tab)
    except Exception as e:
        logger.debug("activate_tab: {}", e)

    logger.info("正在通过 myMediaPartnerGroupsJSON 读取 Partner Groups 列表...")
    group_names = get_partner_group_names_from_myMediaPartnerGroupsJSON(groups_tab) or []
    if not group_names:
        logger.warning("myMediaPartnerGroupsJSON 返回空的 Group Names")
    else:
        logger.info(f"读取到已有 Partner Groups: {len(group_names)} 个")
    return group_names


def print_comparison_report(
    business_models: list[str],
    group_names: list[str],
    need_to_create: list[str],
) -> None:
    """使用 Rich 格式化输出对比结果。"""
    console = Console()
    divider = "=" * 50

    console.print()
    console.print(Panel("Partner Groups 对比结果", style="bold cyan"))
    console.print()

    # Discovery businessModels 标签
    console.print(f"[bold yellow]Discovery businessModels 标签 ({len(business_models)} 个):[/bold yellow]")
    if business_models:
        for label in business_models:
            console.print(f"  - {label}")
    else:
        console.print("  [dim](无)[/dim]")
    console.print()

    # 已有 Partner Groups
    console.print(f"[bold green]已有 Partner Groups ({len(group_names)} 个):[/bold green]")
    if group_names:
        for name in group_names:
            console.print(f"  - {name}")
    else:
        console.print("  [dim](无)[/dim]")
    console.print()

    # 需要创建的 Group Names
    console.print(f"[bold red]需要创建的 Group Names ({len(need_to_create)} 个):[/bold red]")
    if need_to_create:
        for name in need_to_create:
            console.print(f"  - {name}")
    else:
        console.print("  [bold green]所有标签已存在，无需创建。[/bold green]")
    console.print()
    console.print(divider)


def main() -> int:
    console = Console()
    config = ConfigManager()
    browser_manager = BrowserManager(console=console, config=config)

    if not browser_manager.init():
        logger.error("BrowserManager 初始化失败：无法连接浏览器")
        return 1

    browser = getattr(browser_manager, "browser", None)
    if browser is None:
        logger.error("browser_manager.browser 为空")
        return 1

    # 1. 寻找或打开 Discovery 标签页
    # DrissionPage 的 get_tab 在无匹配时会抛 RuntimeError，不会返回 None；与 Groups 一样用 get_tabs。
    logger.info("正在寻找 Discovery 标签页...")
    discovery_candidates = browser.get_tabs(url="partner_discover.ihtml")
    if discovery_candidates:
        discovery_tab = discovery_candidates[0]
        logger.info("复用已打开的 Discovery 标签页。")
    else:
        logger.info("未找到 Discovery 标签页，新开一个。")
        discovery_tab = browser.new_tab(url=DISCOVERY_URL)

    try:
        browser.activate_tab(discovery_tab)
    except Exception as e:
        logger.debug("activate_tab: {}", e)

    # 2. 提取 businessModels 标签
    logger.info("正在从 Discovery 页面提取 businessModels 标签...")
    business_models = extract_business_models_labels(discovery_tab)
    if not business_models:
        logger.error("未提取到任何 businessModels 标签，退出。")
        return 1

    # 3. 读取已有 Partner Groups
    logger.info("正在读取已有 Partner Groups...")
    group_names = get_existing_group_names_from_browser(browser)

    # 4. 对比差异
    need_to_create = _tags_need_to_create(business_models, group_names)

    # 5. 打印报告
    print_comparison_report(business_models, group_names, need_to_create)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
