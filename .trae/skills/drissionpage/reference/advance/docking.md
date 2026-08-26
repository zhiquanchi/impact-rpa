# Integration with Other Tools
## Selenium
```python
from DrissionPage.common import from_selenium
from selenium.webdriver import Chrome
driver = Chrome()
page = from_selenium(driver)
page.get('http://DrissionPage.cn')
```
## Playwright
```python
from DrissionPage.common import from_playwright
from playwright.sync_api import sync_playwright
with sync_playwright() as p:
    browser = p.chromium.launch()
    pw_page = browser.new_page()
    page = from_playwright(pw_page)
    # or: page = from_playwright(browser)
    page.get('http://DrissionPage.cn')
```
> Only Chromium-based browsers are supported for conversion.
