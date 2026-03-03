MODAL_IFRAME_SELECTOR = 'css:iframe[data-testid="uicl-modal-iframe-content"]'

DATE_INPUT_SELECTORS = [
    'css:button[data-testid="uicl-date-input"]',
    'css:input[type="date"]',
    'css:input[data-testid*="date"]',
    'css:[data-testid*="date-input"]',
    'css:.date-input',
    'css:[class*="date-picker"] input',
    'css:[class*="datepicker"] input',
]

PREV_MONTH_SELECTORS = [
    'css:button[aria-label="Previous"]',
    'css:button[aria-label*="Previous"]',
    'css:button[aria-label*="Prev"]',
    'css:button[aria-label*="previous"]',
    'css:button[aria-label*="prev"]',
    'css:[data-testid*="prev"]',
    'css:[data-testid*="Prev"]',
    'css:button.prev',
    'css:.prev',
    'css:[class*="prev"]',
    'css:[class*="Prev"]',
    'css:[class*="chevron-left"]',
    'css:[class*="arrow-left"]',
    'css:[class*="left-arrow"]',
    'css:[class*="caret-left"]',
    'css:button[title*="Previous"]',
    'css:button[title*="previous"]',
    'css:button[title*="Prev"]',
]

NEXT_MONTH_SELECTORS = [
    'css:button[aria-label="Next"]',
    'css:button[aria-label*="Next"]',
    'css:button[aria-label*="Next month"]',
    'css:button[aria-label*="next"]',
    'css:[data-testid*="next"]',
    'css:[data-testid*="Next"]',
    'css:button.next',
    'css:.next',
    'css:[class*="next"]',
    'css:[class*="Next"]',
    'css:[class*="chevron-right"]',
    'css:[class*="arrow-right"]',
    'css:[class*="right-arrow"]',
    'css:[class*="caret-right"]',
    'css:button[title*="Next"]',
    'css:button[title*="next"]',
]

DATE_CELL_SELECTORS = [
    'css:button',
    'css:[role="gridcell"]',
    'css:td',
    'css:.day',
    'css:[class*="day"]',
    'css:[class*="date"]',
]

