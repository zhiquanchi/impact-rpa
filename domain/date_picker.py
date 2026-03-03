from legacy_main import DatePicker, DatePickerResult
from domain import selectors

# 与旧实现保持一致，仅将选择器集中管理。
DatePicker.DATE_INPUT_SELECTORS = selectors.DATE_INPUT_SELECTORS
DatePicker.PREV_MONTH_SELECTORS = selectors.PREV_MONTH_SELECTORS
DatePicker.NEXT_MONTH_SELECTORS = selectors.NEXT_MONTH_SELECTORS
DatePicker.DATE_CELL_SELECTORS = selectors.DATE_CELL_SELECTORS

__all__ = ["DatePicker", "DatePickerResult"]

