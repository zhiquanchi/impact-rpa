# Global Settings (`Settings`)
Located in `DrissionPage.common`.
```python
from DrissionPage.common import Settings
```
## Methods
| Method | Default | Description |
|--------|---------|-------------|
| `set_raise_when_ele_not_found(on_off=True)` | `False` | Raise exception when element not found (else returns `NoneElement`). |
| `set_raise_when_click_failed(on_off=True)` | `False` | Raise exception when click fails. |
| `set_raise_when_wait_failed(on_off=True)` | `False` | Raise exception when wait times out. |
| `set_singleton_tab_obj(on_off=True)` | `True` | Whether Tab objects are singletons (one tab → one object). |
| `set_cdp_timeout(second)` | `30` | CDP execution timeout. |
| `set_browser_connect_timeout(second)` | `30` | Browser connection timeout. |
| `set_auto_handle_alert(accept=None)` | Off | Global auto alert handling. `None` = off; `True` = accept; `False` = cancel. |
| `set_language(code)` | `'zh_cn'` | Language for errors/prompts. `'zh_cn'` or `'en'`. |
| `set_suffixes_list(path)` | Auto | Local file path for domain suffix parsing (for offline use). |
All methods return the `Settings` class, supporting chaining:
```python
Settings.set_raise_when_wait_failed(True).set_language('en')
```
