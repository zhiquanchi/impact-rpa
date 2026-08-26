# Browser Object (`Chromium`)
Represents the entire browser. Manages tabs, settings, cookies.
## Getting Tabs
| Method | Description |
|--------|-------------|
| `get_tab(id_or_num=None, title=None, url=None, tab_type='page', as_id=False)` | Get a tab by id (str), number (int), or filter by title/url/type. Returns `MixTab` or id. |
| `get_tabs(title=None, url=None, tab_type='page', as_id=False)` | Return list of matching tabs. |
| `latest_tab` | Property: returns the last activated tab (last created for remote). |
| `tabs_count` | Property: number of ordinary tabs. |
| `tab_ids` | Property: list of all tab ids. |
## Tab Operations
| Method | Description |
|--------|-------------|
| `new_tab(url=None, new_window=False, background=False, new_context=False)` | Create a new tab, return `MixTab`. |
| `activate_tab(id_ind_tab)` | Bring a tab to front. Accepts id, int index, or Tab object. |
| `close_tabs(tabs_or_ids, others=False)` | Close specified tabs, or others if `others=True`. |
## Browser Settings
| Property | Description |
|----------|-------------|
| `user_data_path` | User data folder path. |
| `download_path` | Default download path. |
| `timeouts` | Dict: `{'base': float, 'page_load': float, 'script': float}`. |
| `timeout` | Base timeout (seconds). |
| `load_mode` | `'none'`, `'normal'`, `'eager'`. |
| Method | Description |
|--------|-------------|
| `set.timeouts(base=None, page_load=None, script=None)` | Set timeout values. |
| `set.load_mode.normal()` / `eager()` / `none()` | Set page load strategy. |
| `set.retry_times(times)` | Set connection retry times. |
| `set.retry_interval(interval)` | Set retry interval (seconds). |
| `set.cookies(cookies)` | Set one or more cookies. Must include `domain`. |
| `set.cookies.clear()` | Clear all cookies. |
| `set.auto_handle_alert(on_off=True, accept=True)` | Auto-handle alerts. |
| `set.download_path(path)` | Set default download path. |
| `set.download_file_name(name, suffix=None)` | Set next download file name. |
| `set.when_download_file_exists(mode)` | Behavior on existing file: `'rename'`, `'overwrite'`, `'skip'`. |
| `set.NoneElement_value(value, on_off=True)` | Set default value for missing elements. |
## Browser Info
| Property | Description |
|----------|-------------|
| `cookies(all_info=False)` | Returns cookies as list. Supports `as_str()`, `as_dict()`, `as_json()`. |
| `process_id` | Browser process PID. |
| `states.is_alive` | Whether browser is alive. |
| `states.is_existed` | Whether browser was pre-existing (not created by this program). |
| `states.is_headless` | Whether in headless mode. |
| `states.is_incognito` | Whether in incognito mode. |
## Other
| Method | Description |
|--------|-------------|
| `wait(second, scope=None)` | Wait for `second` seconds. |
| `wait.new_tab(timeout=None, curr_tab=None, raise_err=None)` | Wait for a new tab to appear. Returns id. |
| `wait.download_begin(timeout=None, cancel_it=False)` | Wait for a download to start. Returns `DownloadMission`. |
| `wait.downloads_done(timeout=None, cancel_if_timeout=True)` | Wait for all downloads to finish. |
| `clear_cache(cache=True, cookies=True)` | Clear browser cache/cookies. |
| `reconnect()` | Reconnect to browser. |
| `quit(timeout=5, force=False, del_data=False)` | Close browser. |
