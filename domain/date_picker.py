import time
from datetime import datetime

from loguru import logger
from rich.console import Console


class DatePickerResult:
    """日期选择结果"""
    def __init__(self, success: bool, method: str | None = None, error: str | None = None):
        self.success = success
        self.method = method
        self.error = error


class DatePicker:
    """日期选择器 - 精简版，仅保留 Impact 平台核心功能"""
    # 仅保留最精确的 data-testid 选择器
    DATE_INPUT_SELECTORS = ['css:button[data-testid="uicl-date-input"]']
    PREV_MONTH_SELECTORS = ['css:button[data-testid="uicl-calendar-previous-month"]']
    NEXT_MONTH_SELECTORS = ['css:button[data-testid="uicl-calendar-next-month"]']
    DATE_CELL_SELECTORS = ['css:td']

    # 仅保留实际使用的禁用关键词
    DISABLED_KEYWORDS = ('disabled', 'prev-month', 'next-month', 'other-month', 'unavailable')

    def __init__(self, console: Console | None = None):
        self.console = console or Console()

    def select_date(self, context, target_date: datetime, open_picker: bool = True) -> DatePickerResult:
        """选择指定日期（仅使用元素点击策略）"""
        target_day = str(target_date.day)
        target_iso = target_date.strftime('%Y-%m-%d')

        try:
            success = self._select_by_element_click(
                context=context,
                target_date=target_date,
                target_day=target_day,
                target_iso=target_iso,
                open_picker=open_picker,
            )
            if success:
                return DatePickerResult(success=True, method='element_click')
        except Exception as e:
            logger.warning(f"日期选择失败: {e}")
            return DatePickerResult(success=False, error=str(e))

        return DatePickerResult(success=False, error=f"无法选择日期: {target_iso}")

    def _select_by_element_click(self, context, target_date: datetime, target_day: str, target_iso: str, open_picker: bool = True) -> bool:
        """通过元素点击方式选择日期 - 核心跨月逻辑"""
        if open_picker and not self._open_date_picker(context):
            return False

        now = datetime.now()
        months_diff = (target_date.year - now.year) * 12 + (target_date.month - now.month)

        # 当前月份快速路径
        if months_diff == 0 and self._is_impact_modal_iframe(context):
            if self._try_pick_by_text(context, target_day, target_iso):
                return True

        direction = 'next' if months_diff >= 0 else 'prev'
        max_attempts = max(abs(months_diff) + 2, 3)

        for step in range(max_attempts):
            if step > 0:
                if not self._click_month_nav(context, direction):
                    break
            # 导航到目标月前，仅用属性匹配防止误点
            need_attr_only = (months_diff != 0 and step == 0)
            if self._try_pick_date_in_view(context, target_day, target_iso, attr_only=need_attr_only):
                return True

        return False

    def _is_impact_modal_iframe(self, context) -> bool:
        """判断是否为 Impact Proposal 弹窗 iframe"""
        try:
            return (context.attr('data-testid') or '').strip() == 'uicl-modal-iframe-content'
        except Exception:
            return False

    def _open_date_picker(self, context) -> bool:
        """打开日期选择器 - 精简版"""
        try:
            btn = context.ele(self.DATE_INPUT_SELECTORS[0], timeout=0.2)
            if btn:
                try:
                    btn.click(by_js=True)
                except Exception:
                    btn.click(by_js=None)
                time.sleep(0.25)
                return True
        except Exception:
            pass
        return False

    def _is_disabled(self, ele) -> bool:
        """检查元素是否禁用 - 精简版"""
        try:
            cls = (ele.attr('class') or '').lower()
            return any(k in cls for k in self.DISABLED_KEYWORDS)
        except Exception:
            return False

    def _try_pick_by_text(self, context, target_day: str, target_iso: str) -> bool:
        """Impact 专用：当月日期按文本快速点击"""
        try:
            cells = context.eles('css:td')
        except Exception:
            return False

        for cell in cells or []:
            try:
                if (cell.text or '').strip() != target_day:
                    continue
                try:
                    cell.click(by_js=True)
                except Exception:
                    cell.click()
                logger.info(f"已选择日期: {target_iso}")
                time.sleep(0.2)
                return True
            except Exception:
                continue
        return False

    def _try_pick_date_in_view(self, context, target_day: str, target_iso: str, *, attr_only: bool = False) -> bool:
        """尝试在当前视图中选择日期 - 优先属性匹配"""
        try:
            date_cells = context.eles(self.DATE_CELL_SELECTORS[0])
        except Exception:
            return False

        if not date_cells:
            return False

        # 优先通过 data-date 属性精确匹配
        for cell in date_cells:
            if self._is_disabled(cell):
                continue
            try:
                data_date = cell.attr('data-date') or ''
                if target_iso in data_date:
                    cell.click(by_js=None)
                    logger.info(f"已选择日期: {target_iso}")
                    time.sleep(0.3)
                    return True
            except Exception:
                continue

        if attr_only:
            return False

        # 兜底：按文本匹配
        for cell in date_cells:
            if self._is_disabled(cell):
                continue
            try:
                if (cell.text or '').strip() == target_day:
                    cell.click(by_js=None)
                    logger.info(f"已选择日期: {target_iso}")
                    time.sleep(0.3)
                    return True
            except Exception:
                continue

        return False

    def _click_month_nav(self, context, direction: str) -> bool:
        """点击月份导航按钮 - 仅使用精确选择器"""
        selectors = self.PREV_MONTH_SELECTORS if direction == 'prev' else self.NEXT_MONTH_SELECTORS

        for sel in selectors:
            try:
                btn = context.ele(sel, timeout=0.15)
                if btn:
                    btn.click(by_js=True)
                    time.sleep(0.25)
                    logger.debug(f"已点击 {direction} 月份按钮")
                    return True
            except Exception:
                continue

        return False


__all__ = ["DatePicker", "DatePickerResult"]
