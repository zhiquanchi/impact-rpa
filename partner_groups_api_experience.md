# Partner Group 接口版创建经验

本文记录的是把 Impact 里的 `Create Partner Group` 流程，从“点 UI”整理成“接口调用”的过程，方便后续复用和排错。

## 目标

把下面这个创建流程自动化：

1. 打开 `Partner Groups` 页面
2. 点击 `Create Group`
3. 填写 `publisherGroupName`
4. 提交创建

最终希望能直接用脚本完成创建，而不是手动点击。

## 结论

这条流程本质上不是单独的 JSON API，而是一个 `Vue + WebForm` 页面：

- 页面会渲染一个表单
- 输入框字段名是 `publisherGroupName`
- 提交按钮本质上触发表单提交
- 真实提交依赖当前会话里的 `cookie`、`uitk_csrf` 和 `execution`

所以“接口版”并不是自己拼一个全新 API，而是：

1. 在浏览器同源上下文里构造 `fetch`
2. 先拿到正确的表单 `action`
3. 再提交 `publisherGroupName` 和 `_eventId=submit`

## 已验证的请求形态

### 1. 打开创建弹窗

```http
POST /secure/advertiser/engage/mediapartners/view-mediapartnergroups-flow.ihtml?execution=e1s1&_eventId=addPublisherGroup
```

常见请求体类似：

```http
_eventId=addPublisherGroup&hasFilters=true&fqe__grp=&execution=e1s1&uitk_csrf=...
```

这个请求会跳到创建表单页。

### 2. 提交创建

表单真实 `action` 会带上 `execution` 和 `uitk_csrf`，例如：

```http
POST /secure/advertiser/engage/mediapartners/view-mediapartnergroups-flow.ihtml?execution=e1s2&uitk_csrf=...
```

提交体类似：

```http
publisherGroupName=API+Script+Test&_eventId=submit
```

## 关键前端实现

页面是一个 `WebForm`，它内部最终会调用原生 `form.submit()`。

重要点：

- 输入框字段名：`publisherGroupName`
- 提交按钮：`Submit`
- 提交事件：`_eventId=submit`
- 表单 `action` 才是正确的提交地址，不能直接拿当前页面 URL 代替

## 脚本实现

当前仓库里已经有两个相关脚本：

- `scripts/create_partner_groups_ui.py`
- `scripts/create_partner_groups_api.py`

其中接口版脚本的核心思路是：

1. 连接当前已登录的 Chrome / Edge
2. 切到 `Partner Groups` 页面
3. 读取当前页面的 `uitk_csrf`
4. 读取表单真实 `action`
5. 用 `fetch(..., { credentials: "include" })` 提交

## 这次踩过的坑

### 坑 1：把提交 URL 写成了当前页面 URL

一开始我直接把请求提交到当前页面地址，结果返回 `403`，并且响应被重定向到登录页。

原因是：

- 当前页面 URL 不一定等于表单 `action`
- 真正可提交的地址包含页面渲染出来的 `uitk_csrf`

修正方式：

- 直接从 DOM 读取 `form.action`
- 如果当前页面还没有表单，就先发一次 `addPublisherGroup` 请求，再从返回的 HTML 里提取新表单的 `action`

### 坑 2：以为这是一个标准 JSON API

实际上这更像是一个“表单提交流”，不是纯 JSON 接口。

所以不能只看 XHR 面板里有没有一个干净的 `POST /api/...`；
要把页面的表单、CSRF、重定向链一起看。

### 坑 3：只抓到了打开弹窗请求，没抓到保存请求

这是因为按钮本身只是触发表单状态切换，真正的保存动作是表单提交。

解决办法：

- 先点击 `Create Group`
- 再找 `input[name="publisherGroupName"]`
- 最后提交表单

## 测试结果

我已经实际测试过接口版脚本，成功创建了一个测试组：

- `API Script Test 2026-05-13 1812`

测试成功时的返回特征：

- HTTP 状态码 `200`
- 最终跳转到新的 `execution`，例如 `e2s1`

## 可复用命令

### 创建单个 Group

```powershell
uv run python scripts/create_partner_groups_api.py "Network"
```

### 批量从文件创建

```powershell
uv run python scripts/create_partner_groups_api.py --file groups.txt
```

### 如果想看 UI 版脚本

```powershell
uv run python scripts/create_partner_groups_ui.py "Network"
```

## 后续建议

- 如果要做正式批量化，建议先加一个 `dry-run`，只打印会提交的名称
- 如果要稳定运行，最好再加一层创建后校验，确认列表里确实出现了新 Group
- cookie、CSRF、JWT 这类值不要写入仓库，保持只从当前浏览器会话中读取

