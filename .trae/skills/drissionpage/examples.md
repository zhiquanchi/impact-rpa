# DrissionPage Code Examples
## Basic Browser Automation (Login Example)
```python
from DrissionPage import Chromium
# Connect and get a tab
tab = Chromium().latest_tab
# Navigate
tab.get('https://gitee.com/login')
# Find elements and interact
tab.ele('#user_login').input('your_username')
tab.ele('#user_password').input('your_password\n')  # '\n' submits
```
## Data Packets (SessionPage)
```python
from DrissionPage import SessionPage
page = SessionPage()
for i in range(1, 4):
    page.get(f'https://gitee.com/explore/all?page={i}')
    links = page.eles('.title project-namespace-path')
    for link in links:
        print(link.text, link.link)
```
## Mode Switching (Browser → HTTP)
```python
from DrissionPage import Chromium
tab = Chromium().latest_tab
tab.get('https://gitee.com/explore/all')
tab.change_mode()  # switch to HTTP session mode (still same cookies)
items = tab.ele('.ui relaxed divided list').eles('.item')
for item in items:
    print(item('t:h3').text)
```
## Network Listener
```python
from DrissionPage import Chromium
tab = Chromium().latest_tab
tab.listen.start('gitee.com/explore')  # filter by URL
tab.get('https://gitee.com/explore/all')
for packet in tab.listen.steps():
    print(packet.url)
    tab('@rel=next').click()
    # exit after enough packets
```
## Actions Chain
```python
from DrissionPage import Chromium
from DrissionPage.common import Keys
tab = Chromium().latest_tab
tab.get('https://www.baidu.com')
tab.actions.move_to('#kw').click().type('DrissionPage').move_to('#su').click()
# Ctrl+A example
tab.actions.click('tag:input').key_down(Keys.CTRL).type('a').key_up(Keys.CTRL)
```
## File Download
```python
from DrissionPage import SessionPage
page = SessionPage()
url = 'https://www.baidu.com/img/flexible/logo/pc/result.png'
page.download(url, 'C:\download')
```
## Browser Download Management
```python
from DrissionPage import Chromium
tab = Chromium().latest_tab
tab.get('https://im.qq.com/pcqq')
# Click download and manage the task
mission = tab('.download-btn').click.to_download(save_path='tmp', rename='QQ.exe')
mission.wait()  # wait until done
print(mission.final_path)
```
## Console Monitoring
```python
from DrissionPage import Chromium
tab = Chromium().latest_tab
tab.console.start()
tab.run_js('console.log("Hello from DrissionPage!");')
data = tab.console.wait()
print(data.text)
```
## Screenshot
```python
tab.get_screenshot('screenshot.png', full_page=True)
img_bytes = tab('tag:img').get_screenshot(as_bytes='png')
```
## iframe Cross-Level Element Access
```python
# Same-origin iframe: access directly
ele = tab('#elementInsideIframe')
# Cross-origin iframe: get frame object first
iframe = tab.get_frame('t:iframe')
ele = iframe('#elementInsideIframe')
```
## Accelerated Data Extraction
```python
from DrissionPage import Chromium
tab = Chromium().latest_tab
tab.get('https://www.163.com')
# Convert to static for extremely fast text extraction
s_body = tab('t:body').s_ele()
for lnk in s_body.eles('t:a'):
    print(lnk.text)
```
