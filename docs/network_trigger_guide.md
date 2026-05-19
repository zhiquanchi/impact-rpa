# 如何正确触发并获取网络请求数据与字段映射关系

通过分析 Impact 的前端界面结构以及其实际发起的 HTTP 网络请求，以下是正确触发网络请求、捕获数据并精准映射核心指标字段的完整指南。

## 1. 初始状态检测与触发策略

在开始抓取之前，必须首先检测页面当前的状态，因为不同的状态决定了触发网络请求的方式。

**状态检测依据：**
检查 DOM 中是否存在侧边栏容器元素：
`#unified-program-slideout-app > div > div:nth-child(1) > div > div > div.side-modal-container`

**策略分支：**

*   **情况 A：元素存在（Slideout 详情页已打开）**
    *   说明当前已经打开了某个 Partner 的详情页。此时如果再次点击主列表中的该 Partner，**不会**产生新的网络响应。
    *   **触发方式**：可以直接在当前的 Slideout 内部点击**“Next（下一个）”**按钮来切换到下一个 Partner，这会直接触发一组新的数据请求。
    *   *注意*：必须精准定位“Next”按钮（例如查找带有 `arrow-right` 图标的按钮），严禁误触旁边的“Send Email”按钮（XPath 对应 `... > button:nth-child(2)`，带有 `envelope` 图标）。

*   **情况 B：元素不存在（Slideout 未打开）**
    *   说明当前在纯列表视图。
    *   **触发方式**：需要点击主页面左侧的**合作伙伴列表项**来打开详情，并触发初次网络请求。
    *   *列表项 XPath 模式*：`//*[@id="app"]/div/div[2]/div[2]/div/div[3]/div/div[1]/div/div` 及其子项。

## 2. 目标网络请求与核心字段精确映射

用户指定的 UI 区域（`.uicc-footer-fragments-grid.uicc-footer-grid-clickable`）通常显示以下四项核心数据：
`Semrush global rank`、`Monthly visitors`、`Moz spam score`、`Moz domain authority`。

经过对真实拦截到的网络数据包进行深度分析，**这些数据实际上分布在两个不同的 API 响应中**，不能简单地通过一次文本搜索来获取：

### 请求 A: 基础属性信息 (包含 Moz 数据)
*   **API 路径特征**：`partner-ui/api/slideout`
*   **JSON 结构与字段对应**：
    该接口返回合作伙伴的基础架构信息。**Moz 相关的指标**位于该响应体中。
    *   **Moz spam score** 对应字段：
        `response.body.program.mediaProperties[i].website.mozSpamScore`
    *   **Moz domain authority** 对应字段：
        `response.body.program.mediaProperties[i].website.mozDomainAuthority`

### 请求 B: 深度流量与媒体属性 (包含 Semrush 和 Visitors 数据)
*   **API 路径特征**：`partner-ui/api/slideout/mediaproperties`
*   **JSON 结构与字段对应**：
    该接口返回详细的流量和审计数据。数据以具体的 URL 作为 Key。**Semrush 排名和月访问量**位于此响应中。
    *   **Semrush global rank** 对应字段：
        `response.body["<具体的网站URL>"].intelligenceApiWeb.Traffic.Summary.Rank`
    *   **Monthly visitors** 对应字段：
        `response.body["<具体的网站URL>"].intelligenceApiWeb.Traffic.Summary.Visits` 
        *(注意：该字段的值为原始数字字符串，如 `"8344697"`，前端将其格式化为了 `8.3M`)*

## 3. 规避的错误操作（供代码审查参考）

1.  **未区分初始状态的盲目点击**：没有判断 Slideout 是否已打开，导致在已打开状态下重复点击原列表项，从而导致捕获不到任何网络包。
2.  **错误定位导航按钮**：在处理“Next”翻页时定位不准，容易误触“发送邮件”等危险按钮。必须使用具有明确语义的属性（如 `arrow-right` 图标或 aria-label）来约束点击。
3.  **错误的提取方式**：使用 DOM 的 `innerText` 提取数据不仅容易受前端样式改版影响，而且无法拿到未格式化的精确数值。必须通过监听上述两个 API 提取原始 JSON。
4.  **单一的关键字匹配**：企图通过全局搜索 `monthlyVisitors` 或类似 `169M` 的格式化文本来寻找 JSON 节点是错误的。Impact 的后端返回的是诸如 `Visits: "169450000"` 这样的原始字段，且分布在多个异步的 API 接口中。必须严格按照上述确定的 JSON 路径进行反序列化和精确提取。