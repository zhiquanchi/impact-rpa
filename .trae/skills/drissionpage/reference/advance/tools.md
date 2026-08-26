# Utility Tools
Import from `DrissionPage.common`.
## `make_session_ele(html_or_ele, loc=None, index=1)`
Create a static `SessionElement` from HTML text or convert a browser element/page to its static version.
- `html_or_ele`: `str` HTML, or any element/page object.
- `loc`: locator to search within (optional).
- `index`: which result (int) or `None` for all.
```python
from DrissionPage.common import make_session_ele
ele = make_session_ele('<html><body><div>abc</div></body></html>')
print(ele.text)  # abc
```
## `get_blob(page, url, as_bytes=True)`
Get a blob resource's content.
- `page`: the page object where the blob resides.
- `url`: blob URL.
- `as_bytes`: `True` → bytes, `False` → base64 string.
## `configs_to_here(save_name=None)`
Copy default ini to current folder. Default name `'dp_configs.ini'`.
## `wait_until(function, kwargs=None, timeout=10)`
Wait until the callable returns truthy. Raises `TimeoutError` on timeout.
## `tree(ele_or_page, text=False, show_js=False, show_css=False)`
Print the element/page structure tree.
## `Keys`
Key constants for keyboard input. Includes shortcuts like `CTRL_A`, `CTRL_C`, `CTRL_V`, `CTRL_X`, `CTRL_Z`, `CTRL_Y`, `ENTER`, `TAB`, `ESC`, etc.
## `By`
Selenium-compatible `By` class: `By.ID`, `By.XPATH`, `By.CLASS_NAME`, etc.
## `from_selenium(driver)`
Converts a Selenium `WebDriver` to `ChromiumPage`.
## `from_playwright(page_or_browser)`
Converts a Playwright `Page` or `Browser` to `ChromiumPage`.
