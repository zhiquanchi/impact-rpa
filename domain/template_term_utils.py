"""
Template Term 相关工具函数

提供获取和选择 Template Term 下拉选项的功能，供确认弹窗和执行流程使用。
"""

import json
import re
import time

from loguru import logger

# Template Term 管理页面的 URL（从中读取所有可用选项）
TEMPLATE_TERM_SOURCE_URL = (
    "https://app.impact.com/secure/advertiser/engage/contracts/library/"
    "view-manage-ios-flow.ihtml?execution=e23s1#fqe__ios=ACTIVE"
)

# 旧版 XPath 兜底（DOM 结构变化时仍可能命中）
TEMPLATE_TERM_XPATH = (
    "//input[@name='insertionOrderId']/preceding-sibling::div"
    "//button[@data-testid='uicl-multi-select-input-button']"
)

_PLACEHOLDER_NORMS = {
    "",
    "select",
    "select template term",
    "choose",
    "please select",
    "-- select --",
}


def _normalize_term_text(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "")).strip().lower()


def _is_date_like_trigger(ele) -> bool:
    """判断元素是否属于日期/时间相关触发器，避免误点 Contract Dates 区域。"""
    if not ele:
        return True

    try:
        data_testid = (ele.attr("data-testid") or "").strip().lower()
        if data_testid == "uicl-date-input":
            return True
    except Exception:
        pass

    try:
        aria_label = (ele.attr("aria-label") or "").strip().lower()
        if "date" in aria_label or "calendar" in aria_label:
            return True
    except Exception:
        pass

    try:
        text = re.sub(r"\s+", " ", (ele.text or "").strip())
        if re.match(
            r"^(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+\d{1,2},\s+\d{4}$",
            text,
        ):
            return True
    except Exception:
        pass

    try:
        cur = ele.parent()
        for _ in range(6):
            if not cur:
                break
            cls = cur.attr("class") or ""
            if "standard-date-time-input" in cls:
                return True
            if "iui-form-section" in cls:
                break
            cur = cur.parent()
    except Exception:
        pass

    return False


def _find_template_term_trigger(iframe):
    """在 Template Term 字段容器内寻找下拉触发器，避免误点其他 multi-select。"""
    # 策略1：hidden input[name=insertionOrderId] → uicl-multiselect-input → button
    try:
        hidden = iframe.ele('css:input[name="insertionOrderId"]', timeout=2)
        if hidden:
            cur = hidden.parent()
            for _ in range(5):
                if not cur:
                    break
                if (cur.attr("data-testid") or "") == "uicl-multiselect-input":
                    trigger = cur.ele(
                        'css:button[data-testid="uicl-multi-select-input-button"]',
                        timeout=0.3,
                    )
                    if trigger and not _is_date_like_trigger(trigger):
                        logger.debug(
                            "Template Term 触发器：通过 input[name=insertionOrderId] 定位"
                        )
                        return trigger
                    break
                cur = cur.parent()
    except Exception as e:
        logger.debug(f"策略1定位 Template Term 触发器失败: {e}")

    # 策略2：Template Term 标签 → iui-form-section → select-input 字段对
    try:
        term_label = iframe.ele("text:Template Term", timeout=2)
        if term_label:
            cur = term_label.parent()
            for _ in range(5):
                if not cur:
                    break
                cls = cur.attr("class") or ""
                if "iui-form-section" in cls:
                    try:
                        field = cur.ele(
                            'css:div[data-testid="uicl-field-label-pair"][class*="select-input"]',
                            timeout=0.3,
                        )
                    except Exception:
                        field = None
                    if field:
                        trigger = field.ele(
                            'css:button[data-testid="uicl-multi-select-input-button"]',
                            timeout=0.3,
                        )
                        if trigger and not _is_date_like_trigger(trigger):
                            logger.debug(
                                "Template Term 触发器：通过 iui-form-section > select-input 定位"
                            )
                            return trigger
                    break
                cur = cur.parent()
    except Exception as e:
        logger.debug(f"策略2定位 Template Term 触发器失败: {e}")

    # 策略3：旧 XPath 兜底
    try:
        trigger = iframe.ele(f"xpath:{TEMPLATE_TERM_XPATH}", timeout=1)
        if trigger and not _is_date_like_trigger(trigger):
            logger.debug("Template Term 触发器：通过 legacy XPath 定位")
            return trigger
    except Exception as e:
        logger.debug(f"策略3定位 Template Term 触发器失败: {e}")

    logger.debug("未能在 Template Term 字段附近找到安全的下拉触发器")
    return None


def _find_template_term_native_select(iframe):
    """查找与 Template Term 字段关联的原生 select（避免误用页面其他 uicl-select）。"""
    try:
        hidden = iframe.ele('css:input[name="insertionOrderId"]', timeout=1)
        if hidden:
            cur = hidden.parent()
            for _ in range(6):
                if not cur:
                    break
                try:
                    sel = cur.ele('css:select[data-testid="uicl-select"]', timeout=0.2)
                except Exception:
                    sel = None
                if sel:
                    return sel
                cur = cur.parent()
    except Exception:
        pass
    return None


def _read_native_select_value(select_ele) -> str:
    try:
        value = select_ele.run_js(
            """
            const opt = this.options[this.selectedIndex];
            return opt ? (opt.text || opt.label || opt.value || '') : (this.value || '');
            """
        )
        if value:
            return str(value).strip()
    except Exception:
        pass
    try:
        selected = select_ele.ele("css:option:checked", timeout=0.2)
        if selected:
            return (selected.text or selected.attr("value") or "").strip()
    except Exception:
        pass
    return ""


def try_native_template_term_select(iframe, desired: str) -> bool:
    """尝试通过 Template Term 关联的原生 select 选择，并校验选中结果。"""
    select_ele = _find_template_term_native_select(iframe)
    if not select_ele:
        return False

    desired_norm = _normalize_term_text(desired)
    try:
        select_ele.select(desired)
        time.sleep(0.2)
        selected_norm = _normalize_term_text(_read_native_select_value(select_ele))
        if not selected_norm:
            logger.debug("原生 select 选择后未读到有效选中值，回退到 multi-select")
            return False
        if selected_norm == desired_norm or desired_norm in selected_norm:
            logger.info(f"已通过原生 select 选择 Template Term: {desired}")
            return True
        logger.debug(
            f"原生 select 选中值不匹配: expected='{desired_norm}', actual='{selected_norm}'"
        )
    except Exception as e:
        logger.warning(f"原生 select 选择 Template Term 失败，尝试 multi-select: {e}")
    return False


def _click_element(ele) -> bool:
    if not ele:
        return False
    try:
        ele.scroll.to_see(center=True)
    except Exception:
        pass
    try:
        ele.click(by_js=True)
        return True
    except Exception:
        pass
    try:
        ele.click()
        return True
    except Exception as e:
        logger.debug(f"点击元素失败: {e}")
    return False


def _is_element_visible(ele) -> bool:
    if not ele:
        return False
    try:
        data = json.loads(
            ele.run_js(
                """
                const r = this.getBoundingClientRect();
                const s = window.getComputedStyle(this);
                return JSON.stringify({
                    w: r.width,
                    h: r.height,
                    display: s.display,
                    visibility: s.visibility,
                    opacity: s.opacity
                });
                """
            )
        )
        return (
            float(data.get("w", 0)) > 20
            and float(data.get("h", 0)) > 20
            and data.get("display") != "none"
            and data.get("visibility") != "hidden"
            and float(data.get("opacity", 1)) > 0
        )
    except Exception:
        return False


def _dropdown_has_options(dropdown) -> bool:
    if not dropdown:
        return False
    try:
        opts = dropdown.eles('xpath:.//li[@role="option"]', timeout=0.3)
        if opts:
            return True
        opts = dropdown.eles("css:div.text-ellipsis", timeout=0.3)
        return bool(opts)
    except Exception:
        return False


def _trigger_is_expanded(trigger) -> bool:
    if not trigger:
        return False
    try:
        if (trigger.attr("aria-expanded") or "").strip().lower() == "true":
            return True
    except Exception:
        pass
    try:
        cur = trigger.parent()
        for _ in range(4):
            if not cur:
                break
            if (cur.attr("aria-expanded") or "").strip().lower() == "true":
                return True
            cur = cur.parent()
    except Exception:
        pass
    return False


def _find_visible_template_term_dropdown(tab, iframe):
    """查找可见的 Template Term 下拉层（优先 portal 主文档，再 iframe）。"""
    selectors = [
        'css:div[data-testid="uicl-multi-select-dropdown"]',
        'css:div[data-testid="uicl-dropdown"]',
    ]
    for root in (tab, iframe):
        if not root:
            continue
        for selector in selectors:
            try:
                nodes = root.eles(selector, timeout=0.5)
            except Exception:
                nodes = []
            for node in nodes or []:
                if _is_element_visible(node) and _dropdown_has_options(node):
                    return node
    return None


def _close_template_term_dropdown(iframe, tab=None) -> None:
    trigger = _find_template_term_trigger(iframe)
    if not trigger:
        return
    if _trigger_is_expanded(trigger) or _find_visible_template_term_dropdown(tab, iframe):
        if _click_element(trigger):
            logger.debug("已收起 Template Term 下拉框")
            time.sleep(0.2)


def _parse_options_from_dropdown(dropdown) -> list[str]:
    options_list: list[str] = []

    items = dropdown.eles('xpath:.//li[@role="option"]')
    for it in items or []:
        txt = (it.text or "").strip()
        if txt:
            options_list.append(txt)

    if not options_list:
        nodes = dropdown.eles("css:div.text-ellipsis")
        for it in nodes or []:
            txt = (it.text or "").strip()
            if txt:
                options_list.append(txt)

    return _dedupe_options(options_list)


def _dedupe_options(options_list: list[str]) -> list[str]:
    seen = set()
    unique_options = []
    for opt in options_list:
        norm = _normalize_term_text(opt)
        if norm not in seen and norm not in _PLACEHOLDER_NORMS:
            seen.add(norm)
            unique_options.append(opt)
    return unique_options


def get_template_term_options(iframe, tab=None) -> list[str]:
    """
    获取 Template Term 下拉框的所有选项值

    Args:
        iframe: iframe 对象
        tab: 主页面 tab 对象，用于查找 portal 渲染的下拉层

    Returns:
        list[str]: 选项文本列表，如果失败则返回空列表
    """
    options_list: list[str] = []
    try:
        dropdown = _open_template_term_dropdown(iframe, tab=tab)
        if not dropdown:
            logger.debug("未能安全打开 Template Term 下拉框，返回空选项列表")
            return []

        options_list = _parse_options_from_dropdown(dropdown)

        if not options_list:
            term_dropdown = _find_template_term_native_select(iframe)
            if term_dropdown:
                try:
                    option_elements = term_dropdown.eles("css:option")
                    for opt in option_elements or []:
                        txt = opt.text or opt.attr("value") or ""
                        if txt.strip():
                            options_list.append(txt.strip())
                except Exception:
                    pass

        unique_options = _dedupe_options(options_list)
        logger.info(
            f"获取到 {len(unique_options)} 个 Template Term 选项: {unique_options}"
        )

        _close_template_term_dropdown(iframe, tab=tab)
        return unique_options

    except Exception as e:
        logger.error(f"获取 Template Term 选项失败: {e}")
        return []


def _open_template_term_dropdown(iframe, tab=None):
    """安全打开 Template Term 下拉框，仅点击 Template Term 字段自身触发器。"""
    try:
        trigger = _find_template_term_trigger(iframe)
        if not trigger:
            logger.debug("未找到 Template Term 下拉框按钮")
            return None

        if _trigger_is_expanded(trigger):
            existing = _find_visible_template_term_dropdown(tab, iframe)
            if existing:
                logger.debug("Template Term 下拉层已展开且包含选项，直接返回")
                return existing

        visible = _find_visible_template_term_dropdown(tab, iframe)
        if visible and not _trigger_is_expanded(trigger):
            # 页面上有其他可见 dropdown，但不是 Template Term 展开态，忽略它
            logger.debug("检测到其他可见 dropdown，仍将点击 Template Term 触发器")

        if not _click_element(trigger):
            logger.debug("点击 Template Term 触发器失败")
            return None

        logger.debug("已点击展开 Template Term 下拉框")
        time.sleep(0.25)

        dropdown = _find_visible_template_term_dropdown(tab, iframe)
        if dropdown:
            logger.debug("成功定位到 Template Term 下拉层")
        else:
            logger.debug("点击后未找到可见的 Template Term 下拉层")
        return dropdown
    except Exception as e:
        logger.warning(f"打开 Template Term 下拉框失败: {e}")
        return None


def _read_options_from_select(select_ele) -> list[str]:
    """从 <select> 元素读取所有 option 文本（优先 text，其次 name，最后 value）"""
    options: list[str] = []
    try:
        opts = select_ele.eles("css:option")
        for opt in opts or []:
            txt = opt.text or opt.attr("name") or opt.attr("value") or ""
            if txt.strip():
                options.append(txt.strip())
    except Exception as e:
        logger.debug(f"读取 select option 失败: {e}")
    return options


def fetch_template_term_options_from_url(browser) -> list[str]:
    """导航到 Template Term 来源页面并读取所有可用选项

    Args:
        browser: BrowserManager 实例，需确保已连接

    Returns:
        list[str]: 去重后的选项列表
    """
    if not browser or not browser.tab:
        logger.warning("浏览器未连接，无法获取 Template Term 选项")
        return []

    tab = browser.tab
    original_url = tab.url
    logger.info(f"正在导航到 Template Term 来源页面: {TEMPLATE_TERM_SOURCE_URL}")

    try:
        tab.get(TEMPLATE_TERM_SOURCE_URL)
        time.sleep(3)

        all_options: list[str] = []

        name_keywords = ["insertionOrderId", "term", "template", "contract", "ios"]
        for kw in name_keywords:
            try:
                sel = tab.ele(f'css:select[name*="{kw}"]', timeout=1)
                if sel:
                    logger.debug(f"通过 name*={kw} 定位到 select 元素")
                    all_options = _read_options_from_select(sel)
                    if all_options:
                        break
            except Exception:
                continue

        if not all_options:
            for kw in ["uicl-select", "multi-select", "template"]:
                try:
                    sel = tab.ele(f'css:select[data-testid*="{kw}"]', timeout=1)
                    if sel:
                        logger.debug(f"通过 data-testid*={kw} 定位到 select 元素")
                        all_options = _read_options_from_select(sel)
                        if all_options:
                            break
                except Exception:
                    continue

        if not all_options:
            try:
                selects = tab.eles("css:select")
                logger.debug(f"页面上共找到 {len(selects)} 个 select 元素")
                for sel in selects:
                    opts = _read_options_from_select(sel)
                    if opts:
                        all_options = opts
                        break
            except Exception as e:
                logger.debug(f"遍历 select 元素失败: {e}")

        if not all_options:
            try:
                dropdowns = tab.eles('css:[role="listbox"], [data-testid*="dropdown"]')
                logger.debug(f"找到 {len(dropdowns)} 个自定义下拉组件")
                for dd in dropdowns:
                    items = dd.eles('css:[role="option"], .text-ellipsis')
                    for it in items or []:
                        txt = (it.text or "").strip()
                        if txt:
                            all_options.append(txt)
                    if all_options:
                        break
            except Exception as e:
                logger.debug(f"查找自定义下拉组件失败: {e}")

        unique_options = _dedupe_options(all_options)
        logger.info(
            f"从来源页面获取到 {len(unique_options)} 个 Template Term 选项: {unique_options}"
        )
        return unique_options

    except Exception as e:
        logger.error(f"从来源页面获取 Template Term 选项失败: {e}")
        return []
    finally:
        if original_url:
            try:
                tab.get(original_url)
                logger.debug(f"已恢复原始页面: {original_url}")
            except Exception as e:
                logger.warning(f"恢复原始页面失败: {e}")
