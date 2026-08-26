# SessionPage Overview
`SessionPage` is for data-packet based web access (using `requests` + `lxml`). It provides the same API as browser pages but much faster.
## Basic Usage
```python
from DrissionPage import SessionPage
page = SessionPage()
page.get('https://gitee.com/explore/all')
items = page.eles('t:h3')
for item in items:
    lnk = item('tag:a')
    print(lnk.text, lnk.link)
```
## Creating SessionPage
```python
# Default (reads ini)
page = SessionPage()
# With SessionOptions
from DrissionPage import SessionOptions
so = SessionOptions().set_proxies(http='127.0.0.1:1080')
page = SessionPage(session_or_options=so)
# Passing existing Session
session = page1.session
page2 = SessionPage(session_or_options=session)
```
## Visiting Pages
### `get()`
```python
page.get(url, show_errmsg=False, retry=None, interval=None, timeout=None, **kwargs)
```
`**kwargs` includes: params, data, json, headers, cookies, files, auth, allow_redirects, proxies, hooks, stream, verify, cert.
Returns `bool` success. Does not return `Response`; use `page.html` etc.
### `post()`
```python
page.post(url, **kwargs)
```
Similar to `get()`. Returns `bool`.
### Other HTTP Methods
```python
session = page.session
response = session.head('https://www.baidu.com')
```
## Getting Page Info
| Property | Description |
|----------|-------------|
| `url` | Current URL. |
| `url_available` | `bool`: whether URL is accessible. |
| `title` | Page title. |
| `raw_data` | Raw bytes from response (`response.content`). |
| `html` | Page HTML string. |
| `json` | JSON-parsed response body (dict). |
| `user_agent` | User agent used. |
| `timeout` | Request timeout. |
| `retry_times` | Retry count. |
| `retry_interval` | Retry interval. |
| `encoding` | Active encoding (if manually set). |
| `cookies(all_domains=False, all_info=False)` | Cookies list. Supports `as_str()`, `as_dict()`, `as_json()`. |
| `session` | The underlying `Session` object. |
| `response` | The `Response` object from last request. |
## Settings
| Method | Description |
|--------|-------------|
| `set.retry_times(times)` | Set retry count. |
| `set.retry_interval(interval)` | Set retry interval. |
| `set.timeout(second)` | Set timeout. |
| `set.encoding(encoding, set_all=True)` | Set encoding. |
| `set.cookies(cookies)` | Set cookies. |
| `set.cookies.clear()` | Clear cookies. |
| `set.cookies.remove(name)` | Remove a cookie by name. |
| `set.headers(headers)` | Set headers (dict or str). |
| `set.header(name, value)` | Set one header. |
| `set.user_agent(ua)` | Set user agent. |
| `set.proxies(http=None, https=None)` | Set proxies. |
| `set.auth(auth)` | Set authentication. |
| `set.hooks(hooks)` | Set hooks. |
| `set.params(params)` | Set URL params. |
| `set.verify(on_off)` | SSL verification. |
| `set.cert(cert)` | Set SSL client cert. |
| `set.stream(on_off)` | Stream response. |
| `set.trust_env(on_off)` | Trust environment. |
| `set.max_redirects(times)` | Max redirects. |
| `set.add_adapter(url, adapter)` | Add adapter. |
| `close()` | Close session. |
## SessionOptions
Used to configure `SessionPage` before creation.
```python
from DrissionPage import SessionOptions
so = SessionOptions()  # reads ini by default
so = SessionOptions(read_file=False)  # empty defaults
so = SessionOptions(ini_path='./my.ini')
```
### Methods
| Method | Description |
|--------|-------------|
| `set_headers(headers)` | Set entire headers (dict or str). |
| `set_a_header(name, value)` | Set one header. |
| `remove_a_header(name)` | Remove one header. |
| `clear_headers()` | Clear all headers. |
| `set_cookies(cookies)` | Set cookies (overwrites previous). |
| `set_timeout(second)` | Set timeout. |
| `set_retry(times=None, interval=None)` | Set retry. |
| `set_proxies(http=None, https=None)` | Set proxies. |
| `set_download_path(path)` | Set download path. |
| `set_auth(auth)` | Set authentication. |
| `set_hooks(hooks)` | Set hooks. |
| `set_params(params)` | Set URL params. |
| `set_cert(cert)` | Set SSL cert. |
| `set_verify(on_off)` | SSL verification. |
| `set_stream(on_off)` | Stream response. |
| `set_trust_env(on_off)` | Trust environment. |
| `set_max_redirects(times)` | Max redirects. |
| `add_adapter(url, adapter)` | Add adapter. |
| `save(path=None)` | Save to ini file. |
| `save_to_default()` | Save to default ini. |
### Properties
`headers`, `cookies` (list), `proxies` (dict), `auth`, `hooks`, `params`, `verify`, `cert`, `adapters` (list), `stream`, `trust_env`, `max_redirects`, `timeout`, `download_path`, `retry_times`, `retry_interval`.
