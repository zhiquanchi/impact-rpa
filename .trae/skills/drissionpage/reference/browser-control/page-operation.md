# Page Interaction (Tab Object)
## Page Navigation
| Method | Description |
|--------|-------------|
| `get(url, show_errmsg=False, retry=None, interval=None, timeout=None, **kwargs)` | Navigate to URL. Returns `bool` success. |
| `back(steps=1)` | Go back in history. |
| `forward(steps=1)` | Go forward in history. |
| `refresh(ignore_cache=False)` | Refresh page. |
| `stop_loading()` | Force stop page load. |
| `set.blocked_urls(urls)` | Block certain URLs (supports `'*'`). |
## Element Management
| Method | Description |
|--------|-------------|
| `add_ele(html_or_info, insert_to=None, before=None)` | Create an element. If `html_or_info` is `(tag, {attr:val})`, it's not inserted to DOM. Returns new `ChromiumElement`. |
| `remove_ele(loc_or_ele)` | Remove an element from DOM. |
## Execute Scripts/Commands
| Method | Description |
|--------|-------------|
| `run_js(script, *args, as_expr=False, timeout=None)` | Execute JS. `args` are accessible as `arguments[...]`. Returns result. |
| `run_js_loaded(script, *args, as_expr=False, timeout=None)` | Execute JS after page load. |
| `run_async_js(script, *args, as_expr=False)` | Execute JS asynchronously. |
| `run_cdp(cmd, **cmd_args)` | Execute Chrome DevTools Protocol command. |
| `run_cdp_loaded(cmd, **cmd_args)` | Execute CDP after page load. |
## Cookies & Cache
| Method | Description |
|--------|-------------|
| `set.cookies(cookies)` | Set one or multiple cookies. |
| `set.cookies.clear()` | Clear all cookies. |
| `set.cookies.remove(name, url=None, domain=None, path=None)` | Remove a cookie. |
| `set.session_storage(item, value)` | Set (or delete if value=`False`) sessionStorage item. |
| `set.local_storage(item, value)` | Set (or delete if value=`False`) localStorage item. |
| `clear_cache(session_storage=True, local_storage=True, cache=True, cookies=True)` | Clear cache. |
## Window Management (via `set.window`)
| Method | Description |
|--------|-------------|
| `set.window.max()` | Maximize window. |
| `set.window.mini()` | Minimize. |
| `set.window.full()` | Fullscreen. |
| `set.window.normal()` | Normal mode. |
| `set.window.size(width=None, height=None)` | Set window size. |
| `set.window.location(x=None, y=None)` | Set window position. |
| `set.window.hide()` | Hide window (Windows only, needs pypiwin32). |
| `set.window.show()` | Show window. |
## Page Scrolling
All scroll methods are in `scroll` sub-property. They return the page object.
| Method | Description |
|--------|-------------|
| `scroll(pixel)` or `scroll.down(pixel)` | Scroll down. |
| `scroll.up(pixel)` | Scroll up. |
| `scroll.right(pixel)` | Scroll right. |
| `scroll.left(pixel)` | Scroll left. |
| `scroll.to_top()` | Scroll to top. |
| `scroll.to_bottom()` | Scroll to bottom. |
| `scroll.to_half()` | Scroll to vertical middle. |
| `scroll.to_rightmost()` | Scroll to rightmost. |
| `scroll.to_leftmost()` | Scroll to leftmost. |
| `scroll.to_location(x, y)` | Scroll to `(x, y)`. |
| `scroll.to_see(loc_or_ele, center=None)` | Scroll until element visible. |
## Alert Handling
| Method | Description |
|--------|-------------|
| `handle_alert(accept=True, send=None, timeout=None, next_one=False)` | Handle alert. Returns text or `False`. |
| `set.auto_handle_alert(on_off=True, accept=True)` | Auto-handle alerts for this tab. |
## Close / Disconnect
| Method | Description |
|--------|-------------|
| `disconnect()` | Disconnect from page (does not close tab). |
| `reconnect(wait=0)` | Disconnect and reconnect. |
| `close(others=False, session=False)` | Close this tab (or others if `others=True`). |
## Scroll Settings
```python
tab.set.scroll.smooth(on_off=False)  # disable smooth scrolling
tab.set.scroll.wait_complete(on_off=True)  # wait for scroll to finish
```
