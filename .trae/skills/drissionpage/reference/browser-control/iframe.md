# iframe Operations
DrissionPage handles `<iframe>` elements without switching context. You can access elements inside same-origin iframes directly from the tab.
## Getting Frame Objects
| Method | Description |
|--------|-------------|
| `get_frame(loc_ind_ele, timeout=None)` | Get a `ChromiumFrame` by locator, index, id, name, or existing Frame object. |
| `get_frames(locator=None, timeout=None)` | Get list of matching frames. |
```python
iframe = tab.get_frame('t:iframe')  # by locator
iframe = tab.get_frame(1)           # first frame
iframe = tab.get_frame('#myframe')  # by id
```
You can also get frames like regular elements:
```python
iframe = tab('t:iframe')  # returns ChromiumElement, but it's actually ChromiumFrame
# Better to wrap:
iframe = tab.get_frame(tab('t:iframe'))
```
## Finding Elements Inside iframes
### Same-origin (cross-level)
```python
# Directly from tab, even nested frames:
ele = tab('#abc')  # finds element inside any same-origin iframe
```
### Cross-origin
Must get the `ChromiumFrame` object first:
```python
iframe = tab.get_frame('t:iframe')
ele = iframe('网易首页')
```
## ChromiumFrame Properties
A `ChromiumFrame` has both element and page properties:
- Element: `iframe.tag`, `.html`, `.remove_attr()`, `.states.is_alive`
- Page: `iframe.get()`, `.get_screenshot()`, `.listen.start()`
It also supports all waiting and element-finding methods.
