# Console Information
Monitor console output from the browser.
## Start/Stop
```python
tab.console.start()   # starts listening
tab.console.stop()    # stops and clears list
```
## Getting Messages
| Method | Description |
|--------|-------------|
| `console.wait(timeout=None)` | Wait for one console message. Returns `ConsoleData` or `False`. |
| `console.steps(timeout=None)` | Generator: yields `ConsoleData` as they arrive. Use in `for` loop. Stops on timeout. |
| `console.messages` | Property: returns `list` of `ConsoleData` and clears internal list. |
## Other
| Property/Method | Description |
|-----------------|-------------|
| `console.listening` | `bool`: whether listening is active. |
| `console.clear()` | Clear received messages without returning. |
## `ConsoleData` Object Properties
| Attribute | Type | Description |
|-----------|------|-------------|
| `source` | `str` | Source. |
| `level` | `str` | Level (log, warning, error, etc.). |
| `text` | `str` | Message text. |
| `body` | `Any` | JSON-parsed text. |
| `url` | `str` | URL. |
| `line` | `str` | Line number. |
| `column` | `str` | Column number. |
## Example
```python
from DrissionPage import Chromium
tab = Chromium().latest_tab
tab.console.start()
tab.run_js('console.log("DrissionPage");')
data = tab.console.wait()
print(data.text)  # DrissionPage
```
