# Custom Exceptions
Import from `DrissionPage.errors`:
```python
from DrissionPage.errors import *
```
| Exception | Cause |
|-----------|-------|
| `ElementNotFoundError` | Element not found. |
| `AlertExistsError` | Unhandled alert exists when executing JS or related function. |
| `ContextLostError` | Page refreshed, element from old page still used. |
| `ElementLostError` | Element itself refreshed/disappeared. |
| `CDPError` | CDP method execution error. |
| `PageDisconnectedError` | Page closed or disconnected. |
| `JavaScriptError` | JS execution error. |
| `NoRectError` | Element has no size/position info. |
| `BrowserConnectError` | Browser connection fails. |
| `NoResourceError` | Resource fetch fails (`src()`/`save()`). |
| `CanNotClickError` | Element cannot be clicked (if set to raise). |
| `GetDocumentError` | Failed to get page document. |
| `WaitTimeoutError` | Wait fails (if set to raise). |
| `IncorrectURLError` | Malformed URL. |
| `StorageError` | Website blocks storage operation. |
| `CookieFormatError` | Invalid cookie format. |
| `LocatorError` | Invalid locator format. |
| `UnknownError` | Unknown error. |
