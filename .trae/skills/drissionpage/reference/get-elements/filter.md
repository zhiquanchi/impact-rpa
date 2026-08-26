# Filtering Element Lists
Methods `eles()`, `nexts()`, etc. return lists with `filter` and `filter_one` properties for further filtering.
## Single Element Filtering (`filter_one`)
| Method | Description |
|--------|-------------|
| `filter_one.displayed(equal=True)` | First displayed/hidden element. |
| `filter_one.checked(equal=True)` | First checked/unchecked. |
| `filter_one.selected(equal=True)` | First selected/unselected (`<select>`). |
| `filter_one.enabled(equal=True)` | First enabled/disabled. |
| `filter_one.clickable(equal=True)` | First clickable/not. |
| `filter_one.have_rect(equal=True)` | First with/without size. |
| `filter_one.style(name, value, equal=True)` | First with matching style. |
| `filter_one.property(name, value, equal=True)` | First with matching property. |
| `filter_one.attr(name, value, equal=True)` | First with matching attribute. |
| `filter_one.text(text, fuzzy=True, contain=True)` | First with/without text. |
| `filter_one.tag(name, equal=True)` | First of/skipping a tag. |
`filter_one` can take an index: `eles.filter_one(2).text('图')` gets the second element containing '图'.
## All Elements Filtering (`filter`)
Same methods but return a new `Filter` list (chainable).
## Or Condition Filtering (`search` / `search_one`)
```python
# Returns list matching OR conditions
eles.search(displayed=True, enabled=True)
# Returns first matching element
ele = eles.search_one(displayed=True, enabled=True, index=1)
```
Parameters: `displayed`, `checked`, `selected`, `enabled`, `clickable`, `have_rect`, `have_text`, `tag` (all optional `bool` or `None`).
## Getting Attributes from Filtered List
```python
eles.filter.displayed().get.texts()
eles.get.attrs('href')
eles.get.links()
eles.filter.displayed().get.texts()
```
## Example
```python
from DrissionPage import Chromium
tab = Chromium().latest_tab
tab.get('https://www.baidu.com')
eles = tab('#s-top-left').eles('t:a')
for ele in eles.filter.displayed():
    print(ele.text, end=' ')
# Output: 新闻 hao123 地图 贴吧 视频 图片 网盘 文库 更多
```
