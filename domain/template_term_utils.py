"""
Template Term 相关工具函数

提供获取和选择 Template Term 下拉选项的功能，供确认弹窗和执行流程使用。
"""

from loguru import logger
import re
import time


def get_template_term_options(iframe) -> list[str]:
    """
    获取 Template Term 下拉框的所有选项值

    Args:
        iframe: iframe 对象

    Returns:
        list[str]: 选项文本列表，如果失败则返回空列表
    """
    options_list = []
    try:
        dropdown = _open_template_term_dropdown(iframe)
        if not dropdown:
            logger.debug("未能安全打开 Template Term 下拉框，返回空选项列表")
            return []

        # 先尝试获取 li[@role="option"] 元素
        items = dropdown.eles('xpath:.//li[@role="option"]')
        for it in items or []:
            txt = it.text or ""
            if txt.strip():
                options_list.append(txt.strip())

        # 如果没有找到，尝试获取 div.text-ellipsis 元素
        if not options_list:
            nodes = dropdown.eles("css:div.text-ellipsis")
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
                    for opt in option_elements or []:
                        txt = opt.text or opt.attr("value") or ""
                        if txt.strip():
                            options_list.append(txt.strip())
                except Exception:
                    pass

        # 去重并保持顺序
        seen = set()
        unique_options = []
        for opt in options_list:
            norm = re.sub(r"\s+", " ", opt).strip().lower()
            if norm not in seen:
                seen.add(norm)
                unique_options.append(opt)

        logger.debug(f"获取到 {len(unique_options)} 个 Template Term 选项")
        return unique_options

    except Exception as e:
        logger.error(f"获取 Template Term 选项失败: {e}")
        return []


def _open_template_term_dropdown(iframe):
    """安全打开 Template Term 下拉框"""
    trigger = _find_template_term_trigger(iframe)
    if not trigger:
        logger.debug("未找到 Template Term 触发器")
        return None
    try:
        trigger.click(by_js=True)
    except Exception:
        try:
            trigger.click()
        except Exception as e:
            logger.debug(f"点击 Template Term 触发器失败: {e}")
            return None

    time.sleep(0.2)
    return _get_visible_template_term_dropdown(iframe)


def _find_template_term_trigger(iframe):
    """仅在 Template Term 字段容器内寻找下拉触发器，避免误点日期/时区等其他控件。"""
    # 策略1：通过唯一隐藏字段 name="insertionOrderId" 精确定位
    try:
        hidden = iframe.ele('css:input[name="insertionOrderId"]', timeout=2)
        if hidden:
            cur = hidden.parent()
            for _ in range(3):
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

    # 策略2：通过 Template Term 标签 → iui-form-section → select-input 字段对
    try:
        term_label = iframe.ele("text:Template Term", timeout=2)
        if not term_label:
            logger.debug("未找到 Template Term 标签")
            return None

        cur = term_label.parent()
        for _ in range(5):
            if not cur:
                break
            cls = cur.attr("class") or ""
            if "iui-form-section" in cls:
                break
            cur = cur.parent()

        if cur:
            for pair in cur.eles("css:.field-label-pair.select-input", timeout=0.5):
                try:
                    btn = pair.ele(
                        'css:button[data-testid="uicl-multi-select-input-button"]',
                        timeout=0.3,
                    )
                    if btn and not _is_date_like_trigger(btn):
                        logger.debug(
                            "Template Term 触发器：通过 iui-form-section > select-input 定位"
                        )
                        return btn
                except Exception:
                    continue
    except Exception as e:
        logger.debug(f"策略2定位 Template Term 触发器失败: {e}")

    logger.debug("未能在 Template Term 字段附近找到安全的下拉触发器")
    return None


def _is_date_like_trigger(ele) -> bool:
    """判断元素是否属于日期/时间相关触发器"""
    if not ele:
        return True

    # 日期按钮
    try:
        data_testid = (ele.attr("data-testid") or "").strip().lower()
        if data_testid == "uicl-date-input":
            return True
    except Exception:
        pass

    # aria-label 含 date/calendar
    try:
        aria_label = (ele.attr("aria-label") or "").strip().lower()
        if "date" in aria_label or "calendar" in aria_label:
            return True
    except Exception:
        pass

    # 文本内容形如日期格式
    try:
        text = re.sub(r"\s+", " ", (ele.text or "").strip())
        if re.match(
            r"^(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+\d{1,2},\s+\d{4}$",
            text,
        ):
            return True
    except Exception:
        pass

    # 检查是否在 standard-date-time-input 的 field-label-pair 内
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


def _get_visible_template_term_dropdown(iframe):
    """获取当前真正可见的 Template Term 下拉层"""
    try:
        dropdown = iframe.ele(
            'css:div[data-testid="uicl-multiselect-dropdown"]', timeout=1
        )
        if dropdown:
            return dropdown

        # 回退：查找包含 "Template Term" 文本的父容器
        term_label = iframe.ele("text:Template Term", timeout=1)
        if term_label:
            cur = term_label.parent()
            for _ in range(10):
                if not cur:
                    break
                cls = cur.attr("class") or ""
                if "multiselect" in cls.lower() or "dropdown" in cls.lower():
                    return cur
                cur = cur.parent()
    except Exception:
        pass

    return None
