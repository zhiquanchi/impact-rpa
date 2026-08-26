# Connecting to Browser
`Chromium` object connects to and manages a browser.
## Initialization
`Chromium(addr_or_opts=None, session_options=None)`
- `addr_or_opts`: `str` (ip:port or ws address), `int` (port), `ChromiumOptions` object, or `None` (uses ini).
- `session_options`: `SessionOptions`, `None` (uses ini), or `False` (skip ini).
## Direct Creation
```python
from DrissionPage import Chromium
browser = Chromium()          # default port 9222
browser = Chromium(9333)      # specific port
browser = Chromium('127.0.0.1:9333')
browser = Chromium('ws://127.0.0.1:8987/devtools/browser/...')
```
## Using ChromiumOptions
```python
from DrissionPage import Chromium, ChromiumOptions
co = ChromiumOptions().set_browser_path(r'D:\chrome.exe')
browser = Chromium(addr_or_opts=co)
```
## Reusing an Existing Browser
- If the address (`'ip:port'`) already has a browser running, DrissionPage takes over automatically.
- Manually start with `--remote-debugging-port=9333`.
## Multiple Browsers
- Each browser needs a separate **port** and **user data folder**.
- `auto_port()` assigns an available port and temp user folder automatically.
```python
co1 = ChromiumOptions().set_local_port(9111).set_user_data_path(r'D:\data1')
co2 = ChromiumOptions().set_local_port(9222).set_user_data_path(r'D:\data2')
b1 = Chromium(addr_or_opts=co1)
b2 = Chromium(addr_or_opts=co2)
```
## Using System Browser User Folder
```python
co = ChromiumOptions().use_system_user_path()
browser = Chromium(co)
```
## Creating a Fresh Browser
- `auto_port()` – new port + new temp user folder.
- `new_env()` – close existing browser on that port, start fresh.
- Manually specify a free port and empty user data folder.
## User Folder Locations
- Default: `%TEMP%\DrissionPage\userData\<port>`
- `auto_port()`: `%TEMP%\DrissionPage\autoPortData\<port>` (auto-cleaned)
- Custom: use `set_tmp_path()` or `set_user_data_path()`
