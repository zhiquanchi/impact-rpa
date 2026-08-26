# DownloadKit (Built-in Downloader)
Every page object has an internal download tool based on `requests`. Supports multi-thread, chunking, retry, conflict handling.
## Basic Download
### Single-thread (blocking)
```python
from DrissionPage import SessionPage
page = SessionPage()
res = page.download('https://example.com/file.zip', 'C:\download')
print(res)  # ('success', 'C:\download\file.zip')
```
### Multi-thread (concurrent)
```python
page.download.add('http://.../file1.exe', 'files')
page.download.add('http://.../file2.exe', 'files')
```
### Chunked Download
```python
page.download.set.block_size('30m')  # chunk size
page.download.add('http://.../demo.zip')  # auto-chunks files > 50MB
page.download.add('http://.../demo.zip', split=False)  # no chunking
```
## Settings
| Method | Description |
|--------|-------------|
| `download.set.****()` | Various global settings (save path, thread count, chunk size, retry, conflict mode, logging). |
## Task Management
### Getting Mission Objects
```python
mission = page.download.add('http://.../file.pdf')
print(mission.id, mission.rate, mission.state, mission.info, mission.result)
# Get by id
mission = page.download.get_mission(mission.id)
# All missions
print(page.download.missions)
# Failed missions
failed = page.download.get_failed_missions()
```
### Blocking per Task
```python
page.download.add('http://.../demo.zip').wait()
```
> For full docs, see [DownloadKit](http://drissionpage.cn/DownloadKitDocs).
