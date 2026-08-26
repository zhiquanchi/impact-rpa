# Relative Positioning
## DOM-based
All methods accept a locator or index.
### Parent
`parent(level_or_loc=1, index=1, timeout=0)`
- `level_or_loc`: number (how many levels up) or locator string.
- `index`: which result when using locator.
```python
ele2 = ele1.parent(2)       # 2 levels up
ele2 = ele1.parent('#id1')  # find ancestor with id='id1'
```
### Children
`child(locator='', index=1, timeout=None, ele_only=True)` – single direct child.
`children(locator='', timeout=None, ele_only=True)` – list of direct children.
### Siblings
`next(locator='', index=1, timeout=None, ele_only=True)` – next sibling.
`nexts(locator='', timeout=None, ele_only=True)` – list of following siblings.
`prev(locator='', index=1, timeout=None, ele_only=True)` – previous sibling.
`prevs(locator='', timeout=None, ele_only=True)` – list of preceding siblings.
### Anywhere in Document
`after(locator='', index=1, timeout=None, ele_only=True)` – next node anywhere.
`afters(locator='', timeout=None, ele_only=True)` – list of following nodes.
`before(locator='', index=1, timeout=None, ele_only=True)` – previous node anywhere.
`befores(locator='', timeout=None, ele_only=True)` – list of preceding nodes.
> All these methods work on both `ChromiumElement` and `SessionElement`. `ele_only=False` includes text and comment nodes.
## Visual-based (Browser only)
Only visible elements.
| Method | Description |
|--------|-------------|
| `east(loc_or_pixel=None, index=1)` | Get element to the right. |
| `west(loc_or_pixel=None, index=1)` | Get element to the left. |
| `south(loc_or_pixel=None, index=1)` | Get element below. |
| `north(loc_or_pixel=None, index=1)` | Get element above. |
| `offset(offset_x, offset_y)` | Get element at offset from top-left. |
| `over(timeout=None)` | Get element covering this one. |
`loc_or_pixel` can be a locator string (no xpath/css) or an integer distance in pixels.
