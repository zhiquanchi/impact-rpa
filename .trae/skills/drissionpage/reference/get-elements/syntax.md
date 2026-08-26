# Locator Syntax (Detailed)
## Basic Attributes
| Syntax | Description |
|--------|-------------|
| `@tag()` | Tag name (e.g., `'div'`). |
| `@attr_name` | Attribute value (e.g., `'@id'`, `'@class'`). |
| `@text()` | Element text content. |
## Single Match `@`
`@attr_name=value` – exact match; `@attr_name:value` – fuzzy match; `@attr_name^value` – starts with; `@attr_name$value` – ends with.
```python
tab.ele('@id=row1')
tab.ele('@class:p_')  # class contains 'p_'
tab.ele('@name')      # has attribute 'name'
```
## Multi-Attribute AND `@@`
```python
tab.ele('@@class=p_cls@@text()=第三行')
```
## Multi-Attribute OR `@|`
```python
tab.eles('@|id=row1@|id=row2')
```
## Negation `@!`
```python
tab.ele('@!id=row1')      # id != 'row1'
tab.ele('@@class=p_cls@!id=row1')  # AND with negation
tab.ele('@|class=p_cls@!id=row1')  # OR with negation
```
## Shorthand
| Shorthand | Full | Description |
|-----------|------|-------------|
| `#id` | `@id=id` | By id (must be first, standalone). |
| `.class` | `@class=class` | By class (must be first, standalone). |
| `text:...` | `@text():...` | By text content (default fuzzy, if no prefix). |
| `tag:div` | `@tag()=div` | By tag name. |
| `t` | `tag` | Short for `tag`. |
| `tx` | `text` | Short for `text`. |
| `x` | `xpath` | XPath mode. |
| `c` | `css` | CSS selector mode. |
| `sr` | `shadow_root` | Get shadow root. |
## Matching Modes
| Symbol | Meaning | Example |
|--------|---------|---------|
| `=` | Exact match | `@id=row1` |
| `:` | Fuzzy match (contains) | `@id:ow` |
| `^` | Starts with | `@id^row` |
| `$` | Ends with | `@id$w1` |
## Special Characters
When text contains HTML entities like `&nbsp;`, convert to hex (e.g., `\u00A0` for `&nbsp;`). See full table in reference file `sheet.md`.
## Examples
```python
tab.ele('#one')                  # id='one'
tab.ele('.p_cls')                # class='p_cls'
tab.ele('text=第二行')           # exact text match
tab.ele('text:第二')             # text contains '第二'
tab.ele('tag:div')               # first div
tab.ele('tag:p@class=p_cls')     # p with class='p_cls'
tab.ele('css:.div')              # CSS selector
tab.ele('xpath://div[@id="div1"]')  # XPath
tab.ele((By.ID, 'one'))          # Selenium locator tuple
```
## Text Matching Tips
- `text:...` (no prefix) is default fuzzy text match.
- `@@text():...` searches entire inner text (not just direct children).
- Use `tag:li@@text():前沿技术` to find `<li>` by its descendant text.
- Do not use `@@text():...` alone without a tag restriction.
## `find()` – Multiple Locators
```python
res = tab.find(['#kw', '#su'])
# returns tuple(locator, element) if any_one=True
# or dict{locator: element} if any_one=False
```
Parameters: `locators` (list), `any_one` (bool), `first_ele` (bool), `timeout`.
