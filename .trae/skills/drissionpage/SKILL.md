---
name: drissionpage
description: "Controls Chromium browsers for RPA and web automation. Use when you need to automate browser tasks like clicking, typing, data extraction, network monitoring, or file downloads using DrissionPage's simplified syntax. Trigger terms: DrissionPage, Chromium, RPA, browser automation, ele(), tab.get(), listener."
---
# DrissionPage Agent Skill
DrissionPage is a Python library for browser automation and data extraction. It uses a direct Chrome DevTools Protocol connection (no WebDriver), supports multiple tabs without switching, and provides a concise element locator syntax.
## Core Workflow
1. **Connect to browser**: `browser = Chromium()`
2. **Get a tab**: `tab = browser.latest_tab` or `tab = browser.get_tab()`
3. **Navigate**: `tab.get('https://example.com')`
4. **Find elements**: `tab.ele('#id')`, `tab.eles('tag:a')`, `tab('@class=myClass')`
5. **Interact**: `ele.click()`, `ele.input('text')`, `ele.hover()`
6. **Extract data**: `ele.text`, `ele.attr('href')`, `tab.html`
## Essential Patterns
### Starting the Browser
```python
from DrissionPage import Chromium
browser = Chromium()  # starts or reuses browser on port 9222
tab = browser.latest_tab
```
### Locator Syntax
- `'#id'` or `'@id=value'` – by id
- `'.class'` or `'@class=value'` – by class
- `'text:content'` – text contains (default)
- `'tag:div'` – tag name
- `'@name=value'` – any attribute
- `'xpath://...'` – XPath
- `'css:.class'` – CSS selector
- `'@@attr1=val1@@attr2=val2'` – multiple conditions (AND)
- `'@|attr1=val1@|attr2=val2'` – multiple conditions (OR)
- `'@!attr=val'` – negation
### Clicking
```python
tab.ele('#btn').click()                          # simulated click, auto-fallback to JS
tab.ele('#btn').click(by_js=True)                # force JS click
tab.ele('#btn').click.at(offset_x=10, offset_y=5)  # click with offset
```
### Typing
```python
tab.ele('#input').input('text')
tab.ele('#input').clear()
tab.ele('#input').input('text', clear=True)  # clear then type
```
### Waiting for Elements
```python
tab.wait.ele_displayed('#result', timeout=5)
tab.wait.ele_deleted('#loading')
tab.wait.eles_loaded('.item')
tab.wait.load_start()
tab.wait.doc_loaded()
```
### Network Monitoring
```python
tab.listen.start('api/data')  # filter by URL pattern
tab.get('...')
packet = tab.listen.wait()     # wait for one packet
print(packet.response.body)
```
### Working with iframes
```python
iframe = tab.get_frame(1)            # by index
iframe = tab.get_frame('#frameId')   # by id
# Cross-origin iframe: get frame object first
# Same-origin iframe: can be accessed directly from tab
```
## Common Subsystems
All detailed API references are in the references folder:
- `reference/browser-control/` – connection, options, pages, tabs, actions, waiting, listening, uploading, downloading, screenshots, scrolling
- `reference/get-elements/` – locator syntax, relative positioning, filtering, finding elements
- `reference/session-page/` – data-packet mode with SessionPage
- `reference/advance/` – accelerating data extraction, ini config, packing, errors, tools
- `reference/download/` – DownloadKit and browser download management
## Quitting
```python
browser.quit()  # close browser
```
