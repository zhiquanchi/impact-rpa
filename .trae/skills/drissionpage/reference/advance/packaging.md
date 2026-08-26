# Packaging with PyInstaller
## Use a Clean Virtual Environment
Install only necessary packages to minimize exe size (~14 MB with DrissionPage alone).
## Handling Ini File
From `v4.0.4.1`, missing ini file does NOT cause an error. But for older versions or explicit control:
### Option 1: Include ini with executable
```python
page = Chromium(ini_path='./configs.ini')  # use relative path
# Or use configs_to_here() to copy ini to project
```
### Option 2: Write config in code (no ini)
```python
from DrissionPage import Chromium, ChromiumOptions, SessionOptions
co = ChromiumOptions(read_file=False)  # skip ini
co.set_browser_path(r'.\.\chrome.exe')
co.set_local_port(9888)
browser = Chromium(addr_or_opts=co, session_options=False)  # session_options=False disables SessionPage ini
```
## Example: Portable Chrome + Packaged Exe
```python
from DrissionPage import Chromium, ChromiumOptions
co = (ChromiumOptions(read_file=False)
      .set_local_port(9888)
      .set_cache_path(r'.\Chrome\chrome.exe')
      .set_user_data_path(r'.\Chrome\userData'))
browser = Chromium(addr_or_opts=co, session_options=False)
tab = browser.latest_tab
tab.get('http://DrissionPage.cn')
```
Key points:
- Set `read_file=False` in `ChromiumOptions()`.
- Pass `session_options=False` if s mode is not needed.
