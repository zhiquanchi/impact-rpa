# Screenshots and Screen Recording
## Page Screenshot
`get_screenshot(path=None, name=None, as_bytes=None, as_base64=None, full_page=False, left_top=None, right_bottom=None)`
- `path`: save path (None = current folder).
- `name`: filename (with suffix: `'jpg'`, `'jpeg'`, `'png'`, `'webp'`).
- `as_bytes`: return bytes (True or format string).
- `as_base64`: return base64 string.
- `full_page`: screenshot entire page (needs browser >= 90).
- `left_top`, `right_bottom`: crop coordinates.
Priority: `as_bytes` > `as_base64` > `path`.
```python
tab.get_screenshot('tmp/pic.jpg', full_page=True)
bytes_data = tab.get_screenshot(as_bytes='png')
```
## Element Screenshot
`ele.get_screenshot(path=None, name=None, as_bytes=None, as_base64=None, scroll_to_center=True)`
Similar parameters. `scroll_to_center` scrolls element into view center before capture.
## Page Screen Recording
Use `screencast` property.
### Modes
| Mode | Description |
|------|-------------|
| `video_mode()` | Continuous recording → silent video. |
| `frugal_video_mode()` | Record only on changes → silent video. |
| `js_video_mode()` | Can record audio but needs manual start. |
| `imgs_mode()` | Continuous screenshots. |
| `frugal_imgs_mode()` | Screenshots on changes. |
### Usage
```python
tab.screencast.set_save_path('video')
tab.screencast.set_mode.video_mode()
tab.screencast.start()
tab.wait(3)
tab.screencast.stop()
```
> **Note**: Video modes require `opencv-python`. Path and filename must be in English.
