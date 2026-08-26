# Network Listener
Each tab and frame has a built-in listener for network packets.
## Start/Set Targets
```python
tab.listen.start(targets=None, is_regex=None, method=None, res_type=None)
```
- `targets`: `str`, `list`, `tuple`, or `set` of URL patterns; `True` for all. Starts listening.
- `is_regex`: whether targets are regex patterns.
- `method`: HTTP methods to filter (default `('GET', 'POST')`).
- `res_type`: resource types (default `True` = all).
```python
tab.listen.set_targets(targets=True, is_regex=False, method=('GET', 'POST'), res_type=True)
```
Modifies targets while listening (does not start if not started).
## Getting Packets
| Method | Description |
|--------|-------------|
| `listen.wait(count=1, timeout=None, fit_count=True, raise_err=None)` | Wait for `count` matching packets. Returns `DataPacket` (if count=1) or list. `fit_count=True` returns `False` on timeout if not all packets received. |
| `listen.steps(count=None, timeout=None, gap=1)` | Generator. Yields `DataPacket` (if gap=1) or list each time `gap` packets arrive. Stops on timeout. |
| `listen.wait_silent(timeout=None, targets_only=False, limit=0)` | Wait until all requests finish. `limit`: allowed remaining connections. |
## Pause/Resume/Stop
| Method | Description |
|--------|-------------|
| `listen.pause(clear=True)` | Pause listening. |
| `listen.resume()` | Resume. |
| `listen.stop()` | Stop and clear queue (targets preserved). |
## `DataPacket` Object
| Attribute | Description |
|-----------|-------------|
| `tab_id` | Tab id that produced the request. |
| `frameId` | Frame id. |
| `target` | Matched target pattern. |
| `url` | Request URL. |
| `method` | HTTP method. |
| `is_failed` | Whether connection failed. |
| `resourceType` | Resource type. |
| `request` | `Request` object. |
| `response` | `Response` object. |
| `fail_info` | `FailInfo` object. |
| Method | Description |
|--------|-------------|
| `wait_extra_info(timeout=None)` | Wait for extra info to load (some packets have delayed extra data). |
### `Request` Object
| Attribute | Description |
|-----------|-------------|
| `url` | Request URL. |
| `method` | HTTP method. |
| `params` | URL parameters as dict. |
| `headers` | Case-insensitive headers. |
| `cookies` | List of cookies sent. |
| `postData` | POST body (dict if JSON). |
### `Response` Object
| Attribute | Description |
|-----------|-------------|
| `url` | Request URL. |
| `headers` | Case-insensitive headers. |
| `body` | Response body. JSON → dict, base64 → bytes, else str. |
| `raw_body` | Unprocessed body text. |
| `status` | HTTP status code. |
| `statusText` | Status text. |
### `FailInfo` Object
| Attribute | Description |
|-----------|-------------|
| `errorText` | Error text. |
| `canceled` | Whether canceled. |
| `blockedReason` | Blocking reason. |
| `corsErrorStatus` | CORS error status. |
## Example
```python
from DrissionPage import Chromium
tab = Chromium().latest_tab
tab.listen.start('gitee.com/explore')  # filter by URL
tab.get('https://gitee.com/explore/all')
for packet in tab.listen.steps():
    print(packet.url)
    tab('@rel=next').click()
    # break after enough packets
```
