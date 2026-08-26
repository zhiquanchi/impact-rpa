# File Upload
## Natural Method (Recommended)
`click.to_upload(file_paths, by_js=False)` – Click an element to trigger file dialog and automatically fill the paths.
- `file_paths`: `str`, `Path`, `list`, or `tuple`. Multiple files can be separated by `'\n'` in a string.
```python
ele = tab('#uploadButton')
ele.click.to_upload(r'C:\text.txt')
```
### Manual Method
```python
tab.set.upload_files('demo.txt')  # set paths before clicking
btn_ele.click()
tab.wait.upload_paths_inputted()  # wait for paths to be filled
```
> **Note**: For file uploads inside a cross-origin `<iframe>`, you must use the `ChromiumFrame` object to set paths and click:
> ```python
> iframe = tab.get_frame(1)
> iframe.set.upload_files('demo.txt')
> iframe.ele('@type=file').click()
> iframe.wait.upload_paths_inputted()
> ```
## Traditional Method
Find the `<input type="file">` element and use `input()`:
```python
upload = tab('tag:input@type=file')
upload.input('D:\test1.txt')
upload.input(['D:\test1.txt', 'D:\test2.txt'])  # multiple files
```
