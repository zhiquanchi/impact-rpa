# Waiting Methods
## Browser-level (`Chromium` object)
| Method | Description |
|--------|-------------|
| `wait(second, scope=None)` | Wait seconds (or random). |
| `wait.new_tab(timeout=None, curr_tab=None, raise_err=None)` | Wait for new tab. Returns id. |
| `wait.download_begin(timeout=None, cancel_it=False)` | Wait for download start. Returns `DownloadMission`. |
| `wait.downloads_done(timeout=None, cancel_if_timeout=True)` | Wait for all downloads. |
## Page-level (`MixTab`, `ChromiumTab`, `ChromiumFrame`)
| Method | Description |
|--------|-------------|
| `wait.load_start(timeout=None, raise_err=None)` | Wait for page to start loading. |
| `wait.doc_loaded(timeout=None, raise_err=None)` | Wait for document to finish loading. |
| `wait.eles_loaded(locator, timeout=None, any_one=False, raise_err=None)` | Wait for element(s) to be in DOM. |
| `wait.ele_displayed(loc_or_ele, timeout=None, raise_err=None)` | Wait for element to be visible. |
| `wait.ele_hidden(loc_or_ele, timeout=None, raise_err=None)` | Wait for element to be hidden. |
| `wait.ele_deleted(loc_or_ele, timeout=None, raise_err=None)` | Wait for element to be removed from DOM. |
| `wait.download_begin(timeout=None, cancel_it=False)` | Wait for download start. |
| `wait.downloads_done(timeout=None, cancel_if_timeout=True)` | Wait for tab's downloads. |
| `wait.upload_paths_inputted()` | Wait for upload paths to be filled. |
| `wait.title_change(text, exclude=False, timeout=None, raise_err=None)` | Wait for title to contain/exclude text. |
| `wait.url_change(text, exclude=False, timeout=None, raise_err=None)` | Wait for URL to contain/exclude text. |
| `wait.alert_closed(timeout=None)` | Wait for alert to be closed. |
## Element-level
| Method | Description |
|--------|-------------|
| `wait.displayed(timeout=None, raise_err=None)` | Wait to be visible. |
| `wait.hidden(timeout=None, raise_err=None)` | Wait to be hidden. |
| `wait.deleted(timeout=None, raise_err=None)` | Wait to be deleted from DOM. |
| `wait.has_rect(timeout=None, raise_err=None)` | Wait to have size/position. |
| `wait.covered(timeout=None, raise_err=None)` | Wait to be covered by another element. |
| `wait.not_covered(timeout=None, raise_err=None)` | Wait not to be covered. |
| `wait.enabled(timeout=None, raise_err=None)` | Wait to be enabled. |
| `wait.disabled(timeout=None, raise_err=None)` | Wait to be disabled. |
| `wait.stop_moving(timeout=None, gap=0.1, raise_err=None)` | Wait to stop moving. |
| `wait.clickable(wait_moved=True, timeout=None, raise_err=None)` | Wait to be clickable. |
| `wait.disabled_or_deleted(timeout=None, raise_err=None)` | Wait to be disabled or deleted. |
All return the element itself on success, `False` on timeout (unless `raise_err=True`).
