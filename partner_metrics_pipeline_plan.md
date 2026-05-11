# Partner 指标后处理流水线（计划）

本文档描述在已有 **网络监听抓取**（见 [`network_trigger_guide.md`](network_trigger_guide.md)）与合并落盘脚本（[`scripts/fetch_element_value.py`](scripts/fetch_element_value.py)）之后，基于 [`partner_metrics.json`](partner_metrics.json) 开展的后续能力规划。**目标**：从每条记录中取 `partnerName` 对应的站点 **URL** 与 **Monthly visitors**，先做本地规则校验以筛掉不符合流量要求的条目，仅在必要时调用 **LLM** 推断 URL 所属 **类目**，从而控制调用成本。

---

## 1. 上下游关系

| 环节 | 说明 |
|------|------|
| 触发与 API 映射 | 按 [`network_trigger_guide.md`](network_trigger_guide.md)：区分 Slideout 已开/未开、`api/slideout`（Moz）与 `api/slideout/mediaproperties`（Semrush / Visits）。 |
| 抓取与合并 | [`scripts/fetch_element_value.py`](scripts/fetch_element_value.py)：监听双 API，合并为 `partner_metrics.json`。 |
| 本计划（未实现） | 读取 JSON → 访客门槛过滤 → （通过后再）LLM 类目分析。 |

---

## 2. `partner_metrics.json` 中与计划相关的字段

[`scripts/fetch_element_value.py`](scripts/fetch_element_value.py) 写入的每条对象大致为：

- `partnerName`：合作伙伴名称（同一 partner 可能对应多条 `propertyUrl`）。
- `propertyUrl`：**计划中的「URL」**（即站点的媒体属性 URL，与 API 2 的 key 一致）。
- `Monthly visitors`：**字符串形式的原始访问量**（如 `"4648384"`），与指南中 `Visits` 一致；可能为 `null`（未返回流量数据）。
- 其他字段（Moz、Semrush 等）暂不纳入本阶段流水线，除非你后续想把它们并入门槛条件。

---

## 3. 推荐处理顺序（降低 LLM 消耗）

```
读取 partner_metrics.json
    → 规范化 Monthly visitors（解析为整数；null/无效 → 「不满足」或单独标记跳过 LLM）
    → 【阶段 A】判断是否满足「访问量」等业务门槛（纯本地逻辑，不调 LLM）
    → 仅当阶段 A 通过时，进入【阶段 B】用 LLM 分析 propertyUrl 的类目
    → 输出：带类目、门禁结果、被拒原因的结构化结果（如新 JSON 或与原文件并列）
```

**原则**：先做 **Monthly visitors（及可选其他本地规则）** 判断，只有通过的数据才触发 **类目识别** 的 LLM 请求。

---

## 4. 阶段 A：访问量门槛（待定实现细节）

- **输入**：每条记录的 `Monthly visitors`（字符串或 `null`）。
- **建议行为**：
  - 将可解析的数字与配置中的 **下限（及可选上限）** 比较；
  - `null`、空串、非数字：策略二选一——（1）直接视为不通过；（2）标为 `unknown` 且不调 LLM，由人工或离线处理。
- **配置占位**（实现时抽到 `settings` 或环境变量即可）：
  - `monthly_visitors_min`（必填意图）
  - 可选：`monthly_visitors_max`、`treat_missing_as_fail` 等。
- **与 partner 粒度**：默认按 **每条 `propertyUrl` 记录** 独立判断即可；若需「同一 `partnerName` 任一站达标即通过」再在计划中增加聚合规则。

---

## 5. 阶段 B：LLM 分析 URL 类目（待定实现细节）

**平台选型（已确认）**：使用 Vertex AI 上的 Gemini，通过 **Google Gen AI SDK** 调用（与官方「Gen AI SDK 概览」一致）。Python 侧依赖为 PyPI 包 `google-genai`，文档入口：[Google Gen AI SDK 概览（含 Python / Vertex）](https://docs.cloud.google.com/vertex-ai/generative-ai/docs/sdks/overview?hl=zh-cn)。

- **认证（JSON 密钥，可配置路径）**：使用 GCP **服务账号** 下载的 **JSON 密钥文件**（密钥内容仍为 JSON）。实现时 **不要** 把密钥文件提交进仓库；在配置或环境中只存放 **密钥文件的路径**：
  - 推荐与 Google 惯例一致：通过环境变量 `GOOGLE_APPLICATION_CREDENTIALS` 指向该 JSON 文件的绝对/相对路径；或
  - 在应用配置（如 `config/settings.json` 增补字段）中提供等价项（例如 `vertex_credentials_path`），由启动脚本在内存中设为 `GOOGLE_APPLICATION_CREDENTIALS` 或使用 SDK 支持的凭据构造方式（以 `google-genai` 与 `google-auth` 为准）。
- **Vertex 开关**：`GOOGLE_GENAI_USE_VERTEXAI=True`（或 SDK 构造参数等价设置），与文档一致。
- **输入**：仅阶段 A **通过** 的 `propertyUrl`（必要时可附带 `partnerName` 作为辅助上下文）。
- **输出占位**（可与团队对齐 taxonomy）：
  - 类目标签（多级或单标签）、简短理由、置信度（可选）。
- **实现时注意**：
  - 请求去重：同一域名/规范化 URL 可缓存类目结果；
  - 限速与重试、超时与成本控制（仅对通过门禁的 URL 计费）；
  - 优先使用 `generate_content` + **结构化输出**（如 JSON schema / 响应解析约定），便于落盘与审计。

### 5.1 建议配置项（均需可配置）

下列项在实现阶段应全部外置为配置或环境变量，避免写死在代码中。

| 配置项 | 含义 | 说明 |
|--------|------|------|
| `vertex_credentials_path`（或仅用 `GOOGLE_APPLICATION_CREDENTIALS`） | 服务账号 JSON 密钥 **文件路径** | 禁止把 JSON 内容写入仓库；CI/本机各自放置密钥并指向路径。 |
| `vertex_project_id` / `GOOGLE_CLOUD_PROJECT` | GCP 项目 ID | 可与密钥 JSON 内 `project_id` 一致；若希望与密钥解耦，可单独配置并由实现校验一致性。 |
| `vertex_location` / `GOOGLE_CLOUD_LOCATION` | 区域 | 例如 `us-central1`、`global` 等，按 Vertex 上模型与合规要求选择。 |
| `vertex_model` | 模型资源 ID | 例如 `gemini-2.5-flash`，以 Vertex 上实际可用名称为准。 |
| `category_taxonomy` | 类目定义 | **可配置**：建议为独立 JSON/YAML 文件路径，或 `settings` 内嵌结构。内容可包含：允许的标签列表、层级（若有）、每类简短说明（写入 prompt）、是否允许 `other`、输出字段名约定等。更换业务线时只改配置即可。 |

**阶段 A** 的 `monthly_visitors_min` 等与 **阶段 B** 的 Vertex 配置可放在同一「Partner 指标流水线」配置块中，便于一份文件管理（实现时再定具体键名与是否合并进现有 `config/settings.json`）。

---

## 6. 验收与风险提示

- **验收**：给定样例 [`partner_metrics.json`](partner_metrics.json)，能列出「被拒（访客不达标）」「未调用 LLM」与「已进入 LLM 类目」三部分数量，且类目步骤条数不超过通过门禁的 URL 条数。
- **风险**：`Monthly visitors` 为 API 字符串，需与前端展示（如 `8.3M`）区分，始终以原始数值为准（与指南一致）。
- **风险**：一对多 `partnerName` ↔ `propertyUrl`，门禁与类目应对齐到 **`propertyUrl` 行**，避免误合并多条 URL 的流量。
- **安全**：JSON 密钥具有完整 API 权限风险，配置文件与备份中仅存 **路径**；`.gitignore` 应忽略密钥文件与本地覆盖配置（若沿用仓库惯例）。

---

## 7. 后续实现时可拆的任务（备忘）

1. 小模块：`load_partner_metrics` + `parse_visits_int`。
2. 小模块：`passes_visit_gate(record, config) -> bool` + 可读 `reason`。
3. （可选）`normalize_url_for_cache`。
4. `classify_property_url_llm(url, ...) -> CategoryResult`，且入口处校验「仅 gate 通过后调用」。

---

## 8. 与主程序（`main.py` / `app.py`）如何结合

仓库里 **`ImpactRPA` 组合根**在 [`app.py`](app.py)：通过 [`core/config_manager.py`](core/config_manager.py) 读写 [`config/settings.json`](config/settings.json)，[`core/config_store.py`](core/config_store.py) 会轮询文件变更，远端同步见 [`core/remote_sync_service.py`](core/remote_sync_service.py)。**Partner 指标抓取**目前是独立脚本 [`scripts/fetch_element_value.py`](scripts/fetch_element_value.py)，产物为仓库根目录的 [`partner_metrics.json`](partner_metrics.json)，与 **`ProposalSender` 发送提案**尚无代码级耦合——集成是指把「门禁 + Vertex 类目」接进**同一套配置与可选入口**，而不是重写浏览器自动化主干。

推荐分层（便于测试、也避免 LLM 拖慢 UI 线程）：

| 层级 | 职责 | 与主代码关系 |
|------|------|----------------|
| **采集** | 已有：`fetch_element_value.py` → `partner_metrics.json` | 需浏览器时已登录 Impact；可继续做独立脚本。 |
| **后处理（计划实现）** | 读 JSON → 阶段 A 门禁 → 阶段 B Vertex（路径/区域/模型/类目均读配置） | 建议做成 **纯 Python 模块**（例如将来放在 `domain/` 或 `core/`），**不依赖** DrissionPage；入参为 `partner_metrics.json` 路径 + 流水线配置 dict。 |
| **配置** | `partner_metrics_pipeline` 等段落放进 `settings.json`，或单独的 JSON 再在 `settings` 里写 `partner_metrics_pipeline_config_path` | 与现有 `ConfigManager.load_settings()` 一致；若使用远程同步，**密钥路径仅本机**，一般不要推到远端共用。 |
| **入口**（三选一或多选） | ① **`uv run python scripts/xxx.py`** 只处理后处理（CI/定时/手工）② **主菜单新项**：在菜单里调用同一模块③ 将来若要与发提案联动：在业务明确 **Impact 列表行与 `propertyUrl`/partner 的关联键** 后再在 `ProposalSender` 前置过滤 | ① 最便宜；② 与 `ImpactRPA` 共用配置；③ 需额外对齐数据模型（慎用仅用 `partnerName` 做主键）。 |

**典型使用顺序**：浏览器里跑抓取脚本得到 `partner_metrics.json` → 同机配置好密钥路径与 `vertex_*`、`category_taxonomy` → 运行后处理脚本或菜单 → 查看带 `gate_reason` / `category` 的扩展 JSON，再决定哪些 partner 要走「发送 Proposal」或其它运营动作。

文档版本：与当前仓库中 `partner_metrics.json` 字段及 `fetch_element_value.py` 落盘格式对齐。LLM 侧：**Vertex + `google-genai`，凭据为可配置路径的 JSON 服务账号密钥**；**区域、模型、类目 taxonomy** 均以配置驱动，不写死。
