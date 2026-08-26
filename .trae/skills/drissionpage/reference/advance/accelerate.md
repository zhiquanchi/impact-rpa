# Data Extraction Acceleration
## The `s_ele()` / `s_eles()` Methods
Convert dynamic (browser) elements to static `SessionElement` for much faster data extraction.
```python
# Slow (4s on a large page):
links = tab('t:body').eles('t:a')
# Fast (0.28s):
links = tab('t:body').s_eles('t:a')
```
`s_ele(locator=None, index=1, timeout=None)` – returns static `SessionElement`.
- `locator=None`: return static copy of the element itself.
- `locator` present: find element in DOM, return its static version.
`s_eles(locator, timeout=None)` – returns list of `SessionElement`.
## Usage
```python
tab = Chromium().latest_tab
tab.get('https://www.163.com')
# Get static copy of body
s_body = tab('t:body').s_ele()
# Then work with s_body:
for link in s_body.eles('t:a'):
    print(link.text)
```
## Note
- Static elements cannot be used for interaction (click, input).
- Only need one `s_ele()` call on the container; avoid repeated conversions.
- ShadowRoot and iframe content are not included in the static copy of a parent element.
