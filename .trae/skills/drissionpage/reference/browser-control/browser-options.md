# Browser Startup Options (`ChromiumOptions`)
Manages browser startup configuration. Created before launching browser, ineffective afterwards.
## Create
```python
from DrissionPage import ChromiumOptions
co = ChromiumOptions()  # reads from ini by default
co = ChromiumOptions(read_file=False)  # use defaults
```
## Usage
```python
co.no_imgs(True).mute(True).headless(True)
page = Chromium(addr_or_opts=co)
```
## Command-Line Arguments
| Method | Description |
|--------|-------------|
| `set_argument(arg, value=None)` | Set startup argument (e.g. `'--start-maximized'`, `'--window-size'`). |
| `remove_argument(arg)` | Remove an argument. |
| `clear_arguments()` | Clear all arguments. |
## Path & Port
| Method | Description |
|--------|-------------|
| `set_browser_path(path)` | Set browser executable path. |
| `set_tmp_path(path)` | Set temporary files path. |
| `set_local_port(port)` | Set local port. Mutually exclusive with `set_address()` and `auto_port()`. |
| `set_address(address)` | Set browser address (`'ip:port'` or ws). |
| `auto_port(on_off=True, scope=None)` | Use auto-assigned port and temp user folder. |
| `set_user_data_path(path)` | Set user data folder path. |
| `use_system_user_path(on_off=True)` | Use system installation's user folder. |
| `set_cache_path(path)` | Set cache path. |
| `existing_only(on_off=True)` | Only connect to existing browser, don't start new. |
## Extensions
| Method | Description |
|--------|-------------|
| `add_extension(path)` | Add extension path. |
| `remove_extensions()` | Remove all extensions. |
## Preferences
| Method | Description |
|--------|-------------|
| `set_user(user='Default')` | Set user profile directory name. |
| `set_pref(arg, value)` | Set a preference. |
| `remove_pref(arg)` | Remove a preference from current config. |
| `remove_pref_from_file(arg)` | Remove a preference from actual user profile file. |
| `clear_prefs()` | Clear all prefs. |
## Run Parameters
| Method | Description |
|--------|-------------|
| `set_timeouts(base=None, page_load=None, script=None)` | Set timeout values. |
| `set_retry(times=None, interval=None)` | Set retry times/interval. |
| `set_load_mode(value)` | Set load mode: `'normal'`, `'eager'`, `'none'`. |
| `set_proxy(proxy)` | Set proxy (e.g. `'http://localhost:1080'`). |
| `set_download_path(path)` | Set download path. |
## Other Settings
| Method | Description |
|--------|-------------|
| `headless(on_off=True)` | Headless mode. |
| `new_env(on_off=True)` | Use completely new environment. |
| `set_flag(flag, value=None)` | Set Chrome flag (from `chrome://flags`). |
| `clear_flags_in_file()` | Clear flags from profile. |
| `clear_flags()` | Clear flags from current config. |
| `incognito(on_off=True)` | Incognito mode. |
| `ignore_certificate_errors(on_off=True)` | Ignore SSL errors. |
| `no_imgs(on_off=True)` | Disable image loading. |
| `no_js(on_off=True)` | Disable JavaScript. |
| `mute(on_off=True)` | Mute audio. |
| `set_user_agent(user_agent)` | Set User-Agent. |
## Save Configuration
| Method | Description |
|--------|-------------|
| `save(path=None)` | Save config to ini file. |
| `save_to_default()` | Save to default ini file. |
## Properties
| Property | Type | Description |
|----------|------|-------------|
| `address` | `str` | Browser address (`'ip:port'`). |
| `browser_path` | `str` | Path to browser executable. |
| `user_data_path` | `str` | User data folder. |
| `tmp_path` | `str` | Temporary folder. |
| `download_path` | `str` | Download folder. |
| `user` | `str` | User profile name. |
| `load_mode` | `str` | Load mode. |
| `timeouts` | `dict` | `{'base': 10, 'page_load': 30, 'script': 30}`. |
| `retry_times` | `int` | Retry count. |
| `retry_interval` | `float` | Retry interval. |
| `proxy` | `str` | Proxy. |
| `arguments` | `list` | Startup arguments. |
| `extensions` | `list` | Extension paths. |
| `preferences` | `dict` | Preferences. |
| `system_user_path` | `bool` | Using system user path. |
| `is_existing_only` | `bool` | Only connect to existing. |
| `is_auto_port` | `bool` | Auto port mode. |
| `is_headless` | `bool` | Headless mode. |
