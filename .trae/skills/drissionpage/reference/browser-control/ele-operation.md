# Element Interaction (`ChromiumElement`)
## Clicking
| Method | Description |
|--------|-------------|
| `click(by_js=None, timeout=1.5, wait_stop=True)` | Left click. `by_js=None`: auto (simulated first, fallback to JS); `True`: JS click; `False`: forced simulated. Returns `True`/`False`. |
| `click.right()` | Right click. |
| `click.middle(get_tab=True)` | Middle click. Returns new Tab if `get_tab=True`. |
| `click.multi(times=2)` | Multi-click (left). |
| `click.at(offset_x=None, offset_y=None, button='left', count=1)` | Click with offset relative to element top-left. |
| `click.to_upload(file_paths, by_js=False)` | Click to trigger file upload and fill paths. |
| `click.to_download(save_path, rename=None, suffix=None, new_tab=False, by_js=False, timeout=None)` | Click to trigger download, returns `DownloadMission`. |
| `click.for_new_tab(by_js=False)` | Click expecting a new tab, returns the new Tab object. |
## Input
| Method | Description |
|--------|-------------|
| `clear(by_js=False)` | Clear element text (simulated ctrl-a+del or JS). |
| `input(vals, clear=False, by_js=False)` | Input text or combination. Supports file paths. |
| `focus()` | Focus the element. |
### Using Keys
```python
from DrissionPage.common import Keys
ele.input((Keys.CTRL, 'a', Keys.DEL))  # ctrl+a+del
ele.input(Keys.CTRL_A)  # shortcut: ctrl+a
```
## Drag and Hover
| Method | Description |
|--------|-------------|
| `drag(offset_x=0, offset_y=0, duration=0.5)` | Drag relative to current position. |
| `drag_to(ele_or_loc, duration=0.5)` | Drag onto another element or coordinate. |
| `hover(offset_x=None, offset_y=None)` | Hover with optional offset. |
## Modifying Element
| Method | Description |
|--------|-------------|
| `set.innerHTML(html)` | Set innerHTML. |
| `set.property(name, value)` | Set property. |
| `set.style(name, value)` | Set CSS style. |
| `set.attr(name, value)` | Set attribute. |
| `remove_attr(name)` | Remove attribute. |
| `set.value(value)` | Set `value` property. |
| `check(uncheck=False, by_js=False)` | Check/uncheck checkbox/radio. |
## Execute JavaScript
| Method | Description |
|--------|-------------|
| `run_js(script, *args, as_expr=False, timeout=None)` | Execute JS on element. `this` refers to the element. Returns result. |
| `run_async_js(script, *args, as_expr=False)` | Execute JS asynchronously. |
| `add_init_js(script)` | Add init script run before page loads. Returns script id. |
| `remove_init_js(script_id=None)` | Remove init script. `None` removes all. |
## Scrolling
All scroll methods are in `scroll` sub-property.
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
| `scroll.to_location(x, y)` | Scroll to specific position. |
| `scroll.to_see(center=None)` | Scroll until element visible. |
| `scroll.to_center()` | Scroll element to viewport center. |
All return the element itself.
## List Selection (`<select>` elements)
The `select` property provides methods for `<select>` elements.
| Method | Description |
|--------|-------------|
| `select(text)` or `select.by_text(text, timeout=None)` | Select by visible text. |
| `select.by_value(value, timeout=None)` | Select by `value` attribute. |
| `select.by_index(index, timeout=None)` | Select by index (1-based). |
| `select.by_locator(locator, timeout=None)` | Select by locator matching `<option>` elements. |
| `select.by_option(option)` | Select by `ChromiumElement` option objects. |
| `select.cancel_by_text(text, timeout=None)` | Deselect by text. |
| `select.cancel_by_value(value, timeout=None)` | Deselect by value. |
| `select.cancel_by_index(index, timeout=None)` | Deselect by index. |
| `select.cancel_by_locator(locator, timeout=None)` | Deselect by locator. |
| `select.cancel_by_option(option)` | Deselect by option objects. |
| `select.all()` | Select all (multi-select). |
| `select.clear()` | Clear all selections. |
| `select.invert()` | Invert selections. |
| Property | Description |
|----------|-------------|
| `select.is_multi` | `bool`: is multi-select. |
| `select.options` | List of all `<option>` elements. |
| `select.selected_option` | Selected option (single). |
| `select.selected_options` | All selected options (multi). |
