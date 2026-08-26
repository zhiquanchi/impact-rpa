# Tab Management
## Getting Tab Objects
### Latest Tab
```python
from DrissionPage import Chromium
browser = Chromium()
tab = browser.latest_tab  # returns MixTab (or tab id if singleton disabled)
```
### By Criteria
```python
tab = browser.get_tab(1)  # first tab in activation order
tab = browser.get_tab('tabIdString')
tab = browser.get_tab(url='DrissionPage.cn')
tab = browser.get_tab(title='My Page')
tabs = browser.get_tabs(url='example.com')  # all matching
```
### New Tab
```python
tab = browser.new_tab('http://example.com')
# parameters: url, new_window (bool), background (bool), new_context (bool)
```
### Click to Open New Tab
```python
tab2 = ele.click.for_new_tab()
tab2 = ele.click.middle()  # middle click opens in new tab
```
## Multi-Tab Collaboration
Each tab object is independent; can operate simultaneously without switching focus.
```python
tab1 = browser.get_tab(1)
tab2 = browser.get_tab(2)
tab1.get('https://www.baidu.com')
tab2.get('https://www.163.com')
print(tab1.title, tab2.title)  # both work
```
## Singleton Mode
By default, one tab → one Tab object. `get_tab()` returns the same object.
```python
from DrissionPage.common import Settings
Settings.set_singleton_tab_obj(False)  # allow multiple Tab objects per tab
```
## Tab States
| Property | Description |
|----------|-------------|
| `tab_id` | Unique id of the tab. |
| `states.is_loading` | Whether page is loading. |
| `states.is_alive` | Whether tab is still open. |
| `states.ready_state` | `'connecting'`, `'loading'`, `'interactive'`, `'complete'`. |
| `states.has_alert` | Whether an alert is present. |
