"""
实机测试：在已登录 Impact 的浏览器中，对当前 Send Proposal 弹窗 iframe 发起
partner_groups.api 配置的 PUT（会真实改 Partner Group，请谨慎）。

前置条件：
  - Chrome/Edge 已打开，DrissionPage 可连接（与主程序相同）
  - 已在 app.impact.com 登录
  - 已打开 Send Proposal 弹窗（或本脚本等待期间你手动打开）
  - 若接口返回 401：在已登录页面的 localStorage 中需能解析到 JWT，或设置环境变量
    IMPACT_PARTNER_GROUPS_AUTHORIZATION（与 curl 中 authorization 头相同，勿提交到仓库）

用法：
  uv run python scripts/test_partner_groups_api_live.py
  uv run python scripts/test_partner_groups_api_live.py --group Network --psi 1eff5966-f4f4-6455-af61-35f26236132e
  uv run python scripts/test_partner_groups_api_live.py --wait-seconds 60
"""

from __future__ import annotations

import argparse
import re
import sys
import time
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from loguru import logger  # noqa: E402

from core.config_manager import ConfigManager  # noqa: E402
from domain.partner_groups_api import set_partner_group_via_api  # noqa: E402
from domain.selectors import MODAL_IFRAME_SELECTOR  # noqa: E402


def _connect_tab():
    from DrissionPage import Chromium

    browser = Chromium()
    try:
        tab = browser.get_tab(url="https://app.impact.com")
    except Exception:
        tab = None
    tab = tab or browser.latest_tab
    return browser, tab


def _wait_modal_iframe(tab, wait_seconds: float, poll: float = 0.5):
    deadline = time.time() + wait_seconds
    while time.time() < deadline:
        try:
            iframe = tab.ele(MODAL_IFRAME_SELECTOR, timeout=poll)
            if iframe:
                return iframe
        except Exception:
            pass
        time.sleep(poll)
    return None


def _psi_from_top_url(url: str) -> str | None:
    if not url:
        return None
    m = re.search(r"[?&]slideout_psi=([a-fA-F0-9-]+)", url)
    if m:
        return m.group(1)
    m = re.search(r"[?&]psi=([a-fA-F0-9-]+)", url)
    return m.group(1) if m else None


def _selected_tab_from_page(tab) -> str | None:
    try:
        el = tab.ele("css:.selected-tab", timeout=2)
        if el and (el.text or "").strip():
            return el.text.strip()
    except Exception:
        pass
    return None


def main() -> int:
    parser = argparse.ArgumentParser(description="实机测试 Partner Groups API（PUT relationship/groups）")
    parser.add_argument("--group", default=None, help="Partner Group 名称；默认从页面 .selected-tab 读取")
    parser.add_argument("--psi", default=None, help="Creator psi；iframe 内解析不到父页 URL 时必传")
    parser.add_argument("--wait-seconds", type=float, default=45.0, help="等待弹窗出现的超时（秒）")
    args = parser.parse_args()

    cfg = ConfigManager(base_dir=str(_ROOT))
    settings = cfg.load_settings()
    pg = settings.get("partner_groups") or {}
    if (pg.get("mode") or "ui").lower() != "api":
        logger.warning("settings 中 partner_groups.mode 不是 api，仍将按 api 逻辑调用（使用当前 partner_groups.api 配置）")

    try:
        _browser, tab = _connect_tab()
        if not tab:
            logger.error("未找到浏览器标签页，请打开 Chrome/Edge 并登录 Impact 后重试")
            return 1

        logger.info("已连接标签页: {}", (tab.url or "")[:120])
        logger.info("请在 {} 秒内打开 Send Proposal 弹窗（若已打开可立即继续）", int(args.wait_seconds))
        iframe = _wait_modal_iframe(tab, args.wait_seconds)
        if not iframe:
            url = tab.url or ""
            if "slideout_psi=" in url or (args.psi and args.psi.strip()):
                logger.warning(
                    "未检测到弹窗 iframe，改用当前标签页执行 fetch（与 app.impact.com 同源，Cookie 仍有效）"
                )
                iframe = tab
            else:
                logger.error(
                    "超时：未找到弹窗 iframe ({})，且当前 URL 无 slideout_psi；"
                    "请打开 Send Proposal 或加上 URL 参数 slideout_psi=，或传 --psi",
                    MODAL_IFRAME_SELECTOR,
                )
                return 2

        group = (args.group or "").strip() or _selected_tab_from_page(tab) or ""
        if not group:
            logger.error("未指定 --group 且页面无 .selected-tab，请传入 --group")
            return 1

        psi_override = (args.psi or "").strip() or None
        if not psi_override:
            psi_override = _psi_from_top_url(tab.url or "")

        logger.info("将调用 API: group={!r} psi_override={!r}", group, psi_override)
        set_partner_group_via_api(
            iframe,
            group,
            pg,
            debug=True,
            creator_psi_override=psi_override,
        )
        logger.info("实机测试完成：HTTP 成功")
        return 0
    except Exception as e:
        logger.exception("实机测试失败: {}", e)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
