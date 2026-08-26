# Browser Download Management
Manage downloads triggered by browser interaction.
## Concepts
- The download management feature is **disabled by default**. It activates when `set.download_path()` is called or `click.to_download()` is used.
- Each tab can have its own download path.
- Filenames can be set before download.
- Always wait for downloads to finish: `tab.wait.downloads_done()`.
## Setting Paths
```python
from DrissionPage import Chromium
browser = Chromium()
browser.set.download_path('C:\tmp')  # global path for all new tabs
tab = browser.latest_tab
tab.set.download_path('C:\path1')  # tab-specific path
```
## Setting Filename
```python
tab.set.download_file_name('new_file')
# After trigger, the next download will be named 'new_file' (auto-adds extension)
```
## `click.to_download()`
```python
mission = ele.click.to_download(save_path='tmp', rename='QQ.exe')
mission.wait()  # wait for completion
```
Parameters: `save_path`, `rename`, `suffix`, `new_tab`, `by_js`, `timeout`.
## Waiting
| Method | Description |
|--------|-------------|
| `tab.wait.download_begin(timeout=None, cancel_it=False)` | Wait for a download to start. Returns `DownloadMission`. |
| `tab.wait.downloads_done(timeout=None, cancel_if_timeout=True)` | Wait for all tab downloads. |
| `browser.wait.downloads_done(timeout=None, cancel_if_timeout=True)` | Wait for all browser downloads. |
## Intercepting Downloads
```python
data = tab.wait.download_begin(cancel_it=True)  # cancel and get info
tab.download(data.url)  # re-download via DownloadKit
```
## Conflict Handling
```python
tab.set.when_download_file_exists('rename')  # default: add _1, _2, etc.
tab.set.when_download_file_exists('overwrite')
tab.set.when_download_file_exists('skip')
```
## `DownloadMission` Object
| Attribute | Description |
|-----------|-------------|
| `url` | Download URL. |
| `tab_id` | Triggering tab id. |
| `id` | Mission id. |
| `folder` | Save folder. |
| `name` | Filename. |
| `tmp_path` | Temporary file path. |
| `state` | `'running'`, `'done'`, `'canceled'`, `'skipped'`. |
| `total_bytes` | Total bytes. |
| `received_bytes` | Received bytes. |
| `final_path` | Final path (after completion). |
| Method | Description |
|--------|-------------|
| `wait(show=True, timeout=None, cancel_if_timeout=False)` | Wait until done. Returns path or `False`. |
| `cancel()` | Cancel and delete partial file. |
```python
mission = tab.wait.download_begin()
while not mission.is_done:
    print(f'\r{mission.rate}%', end='')
```
