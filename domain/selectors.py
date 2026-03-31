"""Impact Send Proposal 弹窗专用选择器（仅保留本页面实际使用的选择器）。"""

MODAL_IFRAME_SELECTOR = 'css:iframe[data-testid="uicl-modal-iframe-content"]'

DATE_INPUT_SELECTORS = [
    'css:button[data-testid="uicl-date-input"]',
]

PREV_MONTH_SELECTORS = [
    'css:button[data-testid="uicl-calendar-previous-month"]',
    'css:button[aria-label="Previous Month"]',
    'css:button[aria-label^="Previous"]',
]

NEXT_MONTH_SELECTORS = [
    'css:button[data-testid="uicl-calendar-next-month"]',
    'css:button[aria-label="Next Month"]',
    'css:button[aria-label^="Next"]',
]

DATE_CELL_SELECTORS = [
    'css:td, .day, [class*="day"], [class*="date"]',
]
