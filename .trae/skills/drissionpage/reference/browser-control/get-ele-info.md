# Getting Element Information
## Content and Attributes
| Property | Description |
|----------|-------------|
| `tag` | Tag name (e.g., `'div'`). |
| `html` | `outerHTML`. |
| `inner_html` | `innerHTML`. |
| `text` | Formatted text (decoded, whitespace trimmed). |
| `raw_text` | Original raw text. |
| `texts(text_node_only=False)` | List of direct child text contents. |
| `comments` | List of comments. |
| `attrs` | Dict of all attributes. |
| `attr(name)` | Value of attribute `name`. `src`/`href` are fully qualified. |
| `property(name)` | Value of property `name`. |
| `value` | The `value` property. |
| `link` | `href` or `src` attribute, or `None`. |
| `pseudo.before` | `::before` pseudo-element content. |
| `pseudo.after` | `::after` pseudo-element content. |
| `style(style, pseudo_ele='')` | CSS style value. |
| `shadow_root` | `ShadowRoot` object or `None`. |
| `child_count` | Number of direct child elements. |
## Size and Position
| Property | Description |
|----------|-------------|
| `rect.size` | `(width, height)` as floats. |
| `rect.location` | Top-left coordinate in page. |
| `rect.midpoint` | Center coordinate in page. |
| `rect.click_point` | Click point coordinate (upper-center). |
| `rect.corners` | `[(tl), (tr), (br), (bl)]` in page. |
| `rect.viewport_corners` | Corners in viewport. |
| `rect.viewport_location` | Top-left in viewport. |
| `rect.viewport_midpoint` | Center in viewport. |
| `rect.viewport_click_point` | Click point in viewport. |
| `rect.screen_location` | Top-left on screen. |
| `rect.screen_midpoint` | Center on screen. |
| `rect.screen_click_point` | Click point on screen. |
| `rect.scroll_position` | `(x, y)` scroll position within the element. |
| `xpath` | Absolute XPath. |
| `css_path` | Absolute CSS selector. |
## Batch Get from List
Elements list (from `eles()`) has a `get` property:
```python
eles = tab.eles('t:a')
print(eles.get.attrs('href'))   # list of href values
print(eles.get.links())          # list of links
print(eles.get.texts())          # list of texts
```
## State Information
| Property | Description |
|----------|-------------|
| `timeout` | Timeout for inner/relative search (from page). |
| `states.is_in_viewport` | `bool`: is click point in viewport. |
| `states.is_whole_in_viewport` | `bool`: entire element in viewport. |
| `states.is_alive` | `bool`: element still valid (not stale). |
| `states.is_checked` | `bool`: checkbox/radio checked. |
| `states.is_selected` | `bool`: `<select>` option selected. |
| `states.is_enabled` | `bool`: element is enabled. |
| `states.is_displayed` | `bool`: element is visible. |
| `states.is_covered` | `False` or `int` (covering element's id). |
| `states.is_clickable` | `bool`: can be clicked (has size, enabled, displayed, responsive). |
| `states.has_rect` | `False` or list of four corner coordinates in page. |
## Saving Element Resources
| Method | Description |
|--------|---------|
| `src(timeout=None, base64_to_bytes=True)` | Get the resource from `src` attribute. Returns `str` (or `bytes` for base64). |
| `save(path=None, name=None, timeout=None, rename=True)` | Save resource to file. Returns save path. |
## Comparing Elements
```python
ele1 = tab('t:div')
ele2 = tab('t:div')
print(ele1 == ele2)  # True if same element
```
