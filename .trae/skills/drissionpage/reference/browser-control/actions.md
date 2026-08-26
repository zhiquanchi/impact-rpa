# Actions Chain
Actions chain simulates mouse and keyboard interactions. Each action executes immediately.
## Using Built-in `actions` property
```python
from DrissionPage import Chromium
tab = Chromium().latest_tab
tab.get('https://www.baidu.com')
tab.actions.move_to('#kw').click().type('DrissionPage')
tab.actions.move_to('#su').click()
```
## Creating Separate Actions Object
```python
from DrissionPage import Chromium
from DrissionPage.common import Actions
tab = Chromium().latest_tab
ac = Actions(tab)
tab.get('https://www.baidu.com')
ac.move_to('#kw').click().type('DrissionPage')
ac.move_to('#su').click()
```
`Actions(page)` initializes with a `ChromiumPage`, `WebPage`, or `ChromiumTab`.
## Mouse Movement
| Method | Parameters | Description |
|--------|------------|-------------|
| `move_to(ele_or_loc, offset_x=None, offset_y=None, duration=0.5)` | `ChromiumElement`, `str` locator, or `(int,int)` absolute coordinates; `duration` in seconds for movement | Move mouse to element midpoint (if no offset) or to offset relative to element top-left. |
| `move(offset_x=0, offset_y=0, duration=0.5)` | | Move relative to current position. |
| `up(pixel)` | | Move up `pixel` pixels. |
| `down(pixel)` | | Move down. |
| `left(pixel)` | | Move left. |
| `right(pixel)` | | Move right. |
All return `Actions`.
## Mouse Clicks
| Method | Parameters | Description |
|--------|------------|-------------|
| `click(on_ele=None, times=1)` | `on_ele`: element or locator; `times`: click count | Left click (optionally on element first). |
| `r_click(on_ele=None, times=1)` | | Right click. |
| `m_click(on_ele=None, times=1)` | | Middle click. |
| `hold(on_ele=None)` | | Hold left button. |
| `release(on_ele=None)` | | Release left button. |
| `r_hold(on_ele=None)` | | Hold right button. |
| `r_release(on_ele=None)` | | Release right button. |
| `m_hold(on_ele=None)` | | Hold middle button. |
| `m_release(on_ele=None)` | | Release middle button. |
All return `Actions`.
## Scroll Wheel
`scroll(delta_y=0, delta_x=0, on_ele=None)` – `delta_y` positive down, `delta_x` positive right.
## Keyboard
| Method | Parameters | Description |
|--------|------------|-------------|
| `key_down(key)` | key name or `Keys` value | Press a key. |
| `key_up(key)` | | Release a key. |
| `input(text)` | `str`, `list`, or `tuple` | Input text or combinations. |
| `type(keys)` | `str`, `list`, or `tuple` | Type text by pressing each key (slower, simulates individual keystrokes). |
## File/Text Drag-in
`drag_in(ele_or_loc, files=None, text=None, title=None, baseURL=None)` – Drag file(s) or text into an element.
## Wait
`wait(second, scope=None)` – Wait `second` seconds, or random between `second` and `scope`.
## Properties
- `owner` – page object for this actions chain.
- `curr_x`, `curr_y` – current cursor coordinates.
## Example: Ctrl+A
```python
from DrissionPage import Chromium
from DrissionPage.common import Keys
tab = Chromium().latest_tab
tab.actions.move_to('tag:input').click()
tab.actions.key_down(Keys.CTRL).type('a').key_up(Keys.CTRL)
# or simpler:
tab.actions.click('tag:input').type(Keys.CTRL_A)
```
## Example: Drag Element
```python
tab.actions.hold('#div1').right(300).release()  # drag right 300px
tab.actions.hold('#div1').release('#div2')      # drag onto another element
```
