"""
Template Term 相关工具函数

提供获取和选择 Template Term 下拉选项的功能，供确认弹窗和执行流程使用。
"""

import re
import time

from loguru import logger

# Template Term 管理页面的 URL（从中读取所有可用选项）
TEMPLATE_TERM_SOURCE_URL = (
    "https://app.impact.com/secure/advertiser/engage/contracts/library/"
    "view-manage-ios-flow.ihtml?execution=e23s1#fqe__ios=ACTIVE"
)

# 这个是点击展开和收齐 Template Term 下拉框的元素
TEMPLATE_TERM = """//input[@name='insertionOrderId']/preceding-sibling::div//button[@data-testid='uicl-multi-select-input-button']"""


def get_template_term_options(iframe, tab=None) -> list[str]:
    """
    获取 Template Term 下拉框的所有选项值

    Args:
        iframe: iframe 对象
        tab: 主页面 tab 对象，用于查找 portal 渲染的下拉层

    Returns:
        list[str]: 选项文本列表，如果失败则返回空列表
    """
    options_list = []
    try:
        dropdown = _open_template_term_dropdown(iframe, tab=tab)
        if not dropdown:
            logger.debug("未能安全打开 Template Term 下拉框，返回空选项列表")
            return []

        # 先尝试获取 li[@role="option"] 元素
        items = dropdown.eles('xpath:.//li[@role="option"]')
        logger.debug(f"li[@role=option] 查找结果: {len(items) if items else 0} 个")
        for it in items or []:
            txt = it.text or ""
            if txt.strip():
                options_list.append(txt.strip())

        # 如果没有找到，尝试获取 div.text-ellipsis 元素
        if not options_list:
            nodes = dropdown.eles("css:div.text-ellipsis")
            logger.debug(f"div.text-ellipsis 查找结果: {len(nodes) if nodes else 0} 个")
            for it in nodes or []:
                txt = it.text or ""
                if txt.strip():
                    options_list.append(txt.strip())

        # 如果还是没有找到，尝试从 select 元素获取
        if not options_list:
            term_dropdown = iframe.ele(
                'css:select[data-testid="uicl-select"]', timeout=2
            )
            if term_dropdown:
                try:
                    option_elements = term_dropdown.eles("css:option")
                    logger.debug(f"<select> option 查找结果: {len(option_elements) if option_elements else 0} 个")
                    for opt in option_elements or []:
                        txt = opt.text or opt.attr("value") or ""
                        if txt.strip():
                            options_list.append(txt.strip())
                except Exception:
                    pass

        # 去重并过滤占位符（Select 等只是 UI 占位符，不是真正的 Template Term）
        seen = set()
        _placeholder_norms = {
            "",
            "select",
            "select template term",
            "choose",
            "please select",
        }
        unique_options = []
        for opt in options_list:
            norm = re.sub(r"\s+", " ", opt).strip().lower()
            if norm not in seen and norm not in _placeholder_norms:
                seen.add(norm)
                unique_options.append(opt)

        logger.info(f"获取到 {len(unique_options)} 个 Template Term 选项: {unique_options}")

        # 获取完成后收起下拉框，恢复 UI 状态
        try:
            btn = iframe.ele(f'xpath:{TEMPLATE_TERM}', timeout=2)
            if btn:
                btn.click()
                logger.debug("已收起 Template Term 下拉框")
        except Exception:
            pass

        return unique_options

    except Exception as e:
        logger.error(f"获取 Template Term 选项失败: {e}")
        return []


def _open_template_term_dropdown(iframe, tab=None):
    """安全打开 Template Term 下拉框

    Args:
        iframe: iframe 对象，触发器按钮在 iframe 内
        tab: 主页面 tab 对象，下拉层可能通过 portal 渲染在主文档中

    Returns:
        下拉列表元素对象，如果失败则返回 None
    """
    try:
        # 先检查下拉层是否已存在（避免重复点击导致收起）
        existing = None
        if tab:
            try:
                existing = tab.ele(
                    'xpath://div[@data-testid="uicl-multi-select-dropdown" or @role="listbox"]', timeout=1
                )
            except Exception:
                pass
        if not existing:
            try:
                existing = iframe.ele(
                    'xpath://div[@data-testid="uicl-multi-select-dropdown" or @role="listbox"]', timeout=1
                )
            except Exception:
                pass
        if existing:
            logger.debug("Template Term 下拉层已存在，直接返回")
            return existing

        # 使用 xpath 语法定位并点击展开下拉框
        btn = iframe.ele(f'xpath:{TEMPLATE_TERM}', timeout=5)
        if not btn:
            logger.debug("未找到 Template Term 下拉框按钮")
            return None
        btn.click()
        logger.debug("已点击展开 Template Term 下拉框")

        # 等待下拉层出现，优先从主文档（portal）查找
        dropdown = None
        if tab:
            dropdown = tab.ele(
                'xpath://div[@data-testid="uicl-multi-select-dropdown" or @role="listbox"]', timeout=3
            )
        # 如果 portal 中没找到，尝试在 iframe 内查找
        if not dropdown:
            dropdown = iframe.ele(
                'xpath://div[@data-testid="uicl-multi-select-dropdown" or @role="listbox"]', timeout=2
            )
        if dropdown:
            logger.debug("成功定位到 Template Term 下拉层")
        else:
            logger.debug("点击后未找到 Template Term 下拉层")
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
            # 优先 text，其次 name 属性，最后 value
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
        # 等待页面稳定（iframe / JS 渲染）
        time.sleep(3)

        all_options: list[str] = []

        # 策略1: 通过 name 属性关键词查找 select 元素
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

        # 策略2: 通过 data-testid 查找
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

        # 策略3: 遍历页面上所有 select 元素，取第一个有有效选项的
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

        # 策略4: 如果没找到原生 select，尝试查找自定义下拉组件
        if not all_options:
            try:
                # 尝试查找常见自定义下拉结构
                dropdowns = tab.eles('css:[role="listbox"], [data-testid*="dropdown"]')
                logger.debug(f"找到 {len(dropdowns)} 个自定义下拉组件")
                for dd in dropdowns:
                    items = dd.eles('css:[role="option"], .text-ellipsis')
                    for it in items or []:
                        txt = it.text or ""
                        if txt.strip():
                            all_options.append(txt.strip())
                    if all_options:
                        break
            except Exception as e:
                logger.debug(f"查找自定义下拉组件失败: {e}")

        # 去重并过滤占位符
        seen = set()
        _placeholder_norms = {
            "",
            "select",
            "select template term",
            "choose",
            "please select",
            "-- select --",
        }
        unique_options = []
        for opt in all_options:
            norm = re.sub(r"\s+", " ", opt).strip().lower()
            if norm not in seen and norm not in _placeholder_norms:
                seen.add(norm)
                unique_options.append(opt)

        logger.info(
            f"从来源页面获取到 {len(unique_options)} 个 Template Term 选项: {unique_options}"
        )
        return unique_options

    except Exception as e:
        logger.error(f"从来源页面获取 Template Term 选项失败: {e}")
        return []
    finally:
        # 恢复原始页面
        if original_url:
            try:
                tab.get(original_url)
                logger.debug(f"已恢复原始页面: {original_url}")
            except Exception as e:
                logger.warning(f"恢复原始页面失败: {e}")
