# Visiting Pages
## `get()`
```python
tab.get(url, show_errmsg=False, retry=None, interval=None, timeout=None, **kwargs)
```
- `url`: target URL (can be local file path).
- `retry/interval/timeout`: override page-level settings.
- `**kwargs`: for s mode only (params, data, json, headers, cookies, files, auth, allow_redirects, proxies, hooks, stream, verify, cert).
- Returns `bool` success.
## `post()`
`post(url, ...)` – sends a POST request using the built-in `Session` object. Same parameters as `get()` (s-mode specific). Returns `Response` object.
## Load Modes
| Mode | Description |
|------|-------------|
| `'normal'` (default) | Wait for all resources to load. |
| `'eager'` | Stop after DOM is ready. |
| `'none'` | Never stop loading (unless manually done). Useful with listener: wait for needed packet, then `stop_loading()`. |
Set via `tab.set.load_mode.normal()` / `.eager()` / `.none()`.
## Example: `none` mode with listener
```python
tab.set.load_mode.none()
tab.listen.start('api/getkeydata')
tab.get('http://www.hao123.com/')
packet = tab.listen.wait()
tab.stop_loading()
print(packet.response.body)
```
