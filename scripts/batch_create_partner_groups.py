"""
批量从 Discovery 页面提取标签并同步创建为 Partner Groups。
使用 DrissionPage UI 自动化：通过 Chromium 连接本机已打开的 Chrome/Edge（与主程序一致）。

重要：脚本只「附加」到你已启动的调试浏览器，结束时不会调用 browser.quit()，不会关闭浏览器。
"""
from DrissionPage._units.listener import DataPacket

import time
import json
from typing import Any

from loguru import logger
from pydantic import BaseModel, ConfigDict, Field

# ========== Pydantic 模型定义 ==========

# --- myMediaPartnerGroupsJSON.ihtml ---


class PublisherGroupNameCell(BaseModel):
    """表格单元格：展示值 dv、比较/排序用 crv（可为 str 或数字）。"""

    model_config = ConfigDict(extra="allow")

    dv: str | None = None
    crv: str | int | float | None = None


class PartnerGroupRecord(BaseModel):
    """合作伙伴组列表中的一行。"""

    model_config = ConfigDict(extra="allow")

    rowId: int | None = None
    publisherGroupName: PublisherGroupNameCell | str | None = None


class PartnerGroupResponse(BaseModel):
    """myMediaPartnerGroupsJSON 根结构。"""

    model_config = ConfigDict(extra="allow")

    totalCount: int = 0
    totRow: dict[str, Any] | None = None
    records: list[PartnerGroupRecord] = Field(default_factory=list)


# --- partner-ui/api/discover/tablestructure ---


class DiscoverFilterTypeItem(BaseModel):
    """searchWidget.filterTypes 中的单项。"""

    model_config = ConfigDict(extra="allow")

    parameterName: str = ""
    filterValues: Any = None


class DiscoverSearchWidget(BaseModel):
    """Discovery 表格结构中的搜索组件。"""

    model_config = ConfigDict(extra="allow")

    filterTypes: list[DiscoverFilterTypeItem] = Field(default_factory=list)


class DiscoverTableStructureResponse(BaseModel):
    """Discovery tablestructure API 根结构（字段较多，允许额外键）。"""

    model_config = ConfigDict(extra="allow")

    tableId: str | None = None
    filterValues: Any = None
    searchWidget: DiscoverSearchWidget | None = None


def _normalize_response_body(body: Any) -> dict | None:
    """将 listener 的 response.body 转为 dict（支持 JSON 字符串）。"""
    if body is None:
        return None
    if isinstance(body, dict):
        return body
    if isinstance(body, (bytes, bytearray)):
        try:
            body = body.decode("utf-8", errors="ignore")
        except Exception:
            return None
        if not body:
            return None
    if isinstance(body, str):
        try:
            parsed = json.loads(body)
        except json.JSONDecodeError:
            return None
        return parsed if isinstance(parsed, dict) else None
    return None


def dv_from_publisher_group_name_field(field: PublisherGroupNameCell | str | None) -> str | None:
    """从 publisherGroupName 单元格取展示用 dv（兼容极少数直接为 str 的情况）。"""
    if field is None:
        return None
    if isinstance(field, str):
        s = field.strip()
        return s or None
    dv = field.dv
    if isinstance(dv, str):
        s = dv.strip()
        return s or None
    return None


def dv_from_partner_group_record(record: PartnerGroupRecord) -> str | None:
    return dv_from_publisher_group_name_field(record.publisherGroupName)


# ========== 提取函数 ==========

def extract_publisher_group_names_from_response(response_data: dict) -> list[str]:
    """
    从 API 响应数据中提取所有 publisherGroupName 中的 dv 值
    
    Args:
        response_data: API 响应的字典数据
    
    Returns:
        List[str]: dv 值列表，例如 ["Network (161004)", "Deal/Coupons (136405)", ...]
    """
    try:
        # 使用 Pydantic 验证和解析数据
        parsed_response = PartnerGroupResponse.model_validate(response_data)

        dv_values: list[str] = []
        for record in parsed_response.records:
            name = dv_from_partner_group_record(record)
            if name:
                dv_values.append(name)

        logger.info(f"成功提取 {len(dv_values)} 个合作伙伴组名称")
        return dv_values
        
    except Exception as e:
        logger.error(f"解析响应数据失败: {e}")
        return []


#
# 说明：本文件允许被 `app.py` 集成调用。
# 为了避免重复连接浏览器，这里不在模块导入时创建 `Chromium()` 实例，
# 而是由外部传入已初始化的 `BrowserManager`（复用 `legacy_main.py:235`）。
#

def extract_tags_from_discovery_page(page):
    """使用监听的方式捕获 Discovery tablestructure，并只提取顶层 filterValues(dict)。"""
    # loadedAt/key 这类参数会变化，所以用正则做模糊匹配。
    targets_pattern = (
        r"https://app\.impact\.com/partner-ui/api/discover/tablestructure\?"
        r".*impid=6627832.*impcid=44072.*format=dv_0_9.*icpt=AFFILIATE"
    )
    page.listen.start(targets=targets_pattern, is_regex=True, method="GET", res_type=True)

    discovery_url = "https://app.impact.com/secure/advertiser/discover/radius/fr/partner_discover.ihtml?page=marketplace&slideout_id_type=partner"
    page.get(discovery_url)

    packet: list[DataPacket] | DataPacket | None = page.listen.wait(timeout=10)
    if not packet:
        logger.error("未捕获到 tablestructure 数据包")
        return None

    packets = packet if isinstance(packet, list) else [packet]
    for dp in packets:
        if not isinstance(dp, DataPacket):
            continue
        raw = _normalize_response_body(dp.response.body)
        if not raw:
            continue
        try:
            parsed = DiscoverTableStructureResponse.model_validate(raw)
        except Exception as e:
            logger.error(f"解析 tablestructure 数据包失败: {e}")
            continue

        fv: dict[str, Any] = parsed.filterValues if isinstance(parsed.filterValues, dict) else {}
        logger.info(f"提取到顶层筛选值 filterValues: {len(fv)} 类")
        return fv

    logger.error("未解析出任何有效的 tablestructure JSON")
    return None


def extract_filtertype_values_list_from_discovery_page(page, *, parameter_name: str) -> list[Any]:
    """
    提取 searchWidget.filterTypes 中指定 parameterName 的 filterValues 列表。

    例如：parameter_name="businessModels" 时，返回对应 multiselect 的下拉项列表。
    """
    targets_pattern = (
        r"https://app\.impact\.com/partner-ui/api/discover/tablestructure\?"
        r".*impid=6627832.*impcid=44072.*format=dv_0_9.*icpt=AFFILIATE"
    )
    page.listen.start(targets=targets_pattern, is_regex=True, method="GET", res_type=True)

    discovery_url = "https://app.impact.com/secure/advertiser/discover/radius/fr/partner_discover.ihtml?page=marketplace&slideout_id_type=partner"
    page.get(discovery_url)

    packet: list[DataPacket] | DataPacket | None = page.listen.wait(timeout=10)
    if not packet:
        logger.error("未捕获到 tablestructure 数据包")
        return []

    packets = packet if isinstance(packet, list) else [packet]
    for dp in packets:
        if not isinstance(dp, DataPacket):
            continue
        raw = _normalize_response_body(dp.response.body)
        if not raw:
            continue
        try:
            parsed = DiscoverTableStructureResponse.model_validate(raw)
        except Exception as e:
            logger.error(f"解析 tablestructure 数据包失败: {e}")
            continue

        if not parsed.searchWidget or not parsed.searchWidget.filterTypes:
            continue

        for ft in parsed.searchWidget.filterTypes:
            if ft.parameterName != parameter_name:
                continue
            items = ft.filterValues
            if isinstance(items, list):
                logger.info("提取到 filterType %s 的列表项数: %d", parameter_name, len(items))
                return items
            logger.warning("filterType %s 的 filterValues 不是 list，类型=%s", parameter_name, type(items))
            return []

    logger.error("未找到匹配的 filterType: %s", parameter_name)
    return []


def get_partner_group_names_from_myMediaPartnerGroupsJSON(groups_page, *, page_size: int = 25, max_pages: int = 10):
    """
    通过你给的接口：myMediaPartnerGroupsJSON.ihtml 拉取 Groups 列表。
    优点：使用 DrissionPage listener 直接抓网络响应，不依赖前端表格 DOM 渲染/等待。
    """
    base = "https://app.impact.com/secure/nositemesh/advertiser/myMediaPartnerGroupsJSON.ihtml"
    all_names: list[str] = []
    seen: set[str] = set()

    for page in range(1, max_pages + 1):
        start_index = (page - 1) * page_size
        url = (
            f"{base}?fqe__grp=&sortBy=&sortOrder="
            f"&tableId=t367&page={page}&startIndex={start_index}&pageSize={page_size}"
        )
        # 监听网络请求，避免依赖 DOM 或 async fetch 返回值
        listen = groups_page.listen
        listen.start(targets="myMediaPartnerGroupsJSON.ihtml", method="GET", res_type=True)
        try:
            js = f"""
(async function() {{
  const url = {json.dumps(url)};
  try {{
    await fetch(url, {{
      credentials: 'include',
      headers: {{
        'Accept': 'application/json, text/plain, */*',
        'X-Requested-With': 'XMLHttpRequest'
      }}
    }});
  }} catch (e) {{}}
  return true;
}})()
"""
            groups_page.run_js(js)
            packet = listen.wait(timeout=20, fit_count=True, raise_err=False)
        except Exception as e:
            logger.error(f"获取 Partner Group 列表失败: {e}")
            return all_names if all_names else None
        finally:
            try:
                listen.stop()
            except Exception:
                pass

        if not packet:
            logger.warning("监听未收到 myMediaPartnerGroupsJSON 响应，停止翻页。")
            break

        packets = packet if isinstance(packet, list) else [packet]
        data: dict | None = None
        for p in reversed(packets):
            if not p or not p.response or not p.response.body:
                continue
            body = _normalize_response_body(p.response.body)
            if body and "records" in body:
                data = body
                break

        if not data:
            logger.warning("无法从响应中解析含 records 的 JSON，停止翻页。")
            break

        try:
            parsed_page = PartnerGroupResponse.model_validate(data)
        except Exception as e:
            logger.warning(f"Partner Group 列表页 JSON 校验失败，停止翻页: {e}")
            break

        records = parsed_page.records
        total_count = int(parsed_page.totalCount or 0)

        for record in records:
            name = dv_from_partner_group_record(record)
            if name and name not in seen:
                seen.add(name)
                all_names.append(name)

        if not records:
            break
        if start_index + len(records) >= total_count:
            break
        if len(records) < page_size:
            break

    return all_names if all_names else None


def create_group_ui(page, group_name):
    """通过 UI 自动化创建单个 Partner Group"""
    base_url = "https://app.impact.com/secure/advertiser/engage/mediapartners/view-mediapartnergroups-flow.ihtml"
    
    logger.info("准备创建 Group: {}", group_name)
    # 每次创建前回到列表页，确保状态干净
    page.get(base_url)
    
    # 1. 点击 "Create Group" 按钮
    create_btn = page.ele('text:Create Group', timeout=10)
    if not create_btn:
        logger.error("未找到 'Create Group' 按钮")
        return False
    
    create_btn.click()
    
    # 2. 等待并输入名称
    # 使用较长的等待时间，并尝试通过 name 属性定位
    name_input = page.ele('@name=publisherGroupName', timeout=10)
    if not name_input:
        logger.error("未找到输入框 'publisherGroupName'")
        # 截个图方便调试
        page.get_screenshot(path="logs/error_create_group.png")
        return False
    
    name_input.input(group_name, clear=True)
    
    # 3. 提交
    # 寻找文本为 Submit 的按钮
    submit_btn = page.ele('text=Submit', timeout=5)
    if not submit_btn:
        submit_btn = page.ele('@type=submit', timeout=2) # 备选方案
        
    if not submit_btn:
        logger.error("未找到 'Submit' 按钮")
        return False
    
    submit_btn.click()
    
    # 4. 验证成功
    # 检查是否回到了列表页，或者是否有错误提示
    page.wait.load_start()
    time.sleep(1.5)
    
    if "already exists" in page.html:
        logger.warning("Group '{}' 已存在，跳过。", group_name)
        return True # 视为广义成功
        
    if group_name in page.html:
        logger.success("成功通过 UI 创建 Group: {}", group_name)
        return True
    else:
        logger.warning("创建操作已完成，但未能验证 '{}' 是否出现在列表中。", group_name)
        return True

def get_partner_group_names_from_groups_page(groups_page):
    """
    UI 回退方案：尽量复用同一套接口抓取（UI DOM 解析在页面结构变动时很脆弱）。
    """
    try:
        # 加大页数上限，尽量覆盖全部 records。
        return get_partner_group_names_from_myMediaPartnerGroupsJSON(
            groups_page, page_size=25, max_pages=50
        ) or []
    except Exception as e:
        logger.warning("回退读取 Group 名称失败: {}", e)
        return []


def __tags_need_to_create(tags: dict[str, Any] | list[Any] | None, group_names: list[str]) -> list[str]:
    """根据 Discovery 返回的筛选项生成候选 tag，并与已有 `group_names` 做包含匹配去重。"""
    if not tags:
        return []

    candidates: list[str] = []
    seen: set[str] = set()

    def add_item(it: Any) -> None:
        cand: str | None = None
        if isinstance(it, dict):
            # 倾向使用 label（更接近 UI 展示/Group 名）
            cand = it.get("label") or it.get("value")
        elif it is not None:
            cand = str(it)

        if not cand:
            return
        cand_s = str(cand).strip()
        if not cand_s or cand_s in seen:
            return
        seen.add(cand_s)
        candidates.append(cand_s)

    if isinstance(tags, dict):
        # 顶层 filterValues 的 value 通常是 list[ {label:..., value:...}, ... ]
        for _, items in tags.items():
            if not isinstance(items, list):
                continue
            for it in items:
                add_item(it)
    elif isinstance(tags, list):
        for it in tags:
            add_item(it)

    def exists_in_groups(name: str) -> bool:
        # group_names 的显示值可能是 "Label (id)"，所以做 contains/prefix 宽松匹配。
        for existing in group_names:
            if existing == name:
                return True
            if existing.startswith(name):
                return True
            if name in existing:
                return True
        return False

    return [c for c in candidates if not exists_in_groups(c)]

def seed_partner_groups_from_discovery(browser_manager) -> bool:
    """
    从 Discovery 的 businessModels 抓取 tags，并在 Partner Groups 页面创建缺失的 Groups。

    约束：
    - 只依赖外部传入的 BrowserManager（复用它的 Chromium 会话）
    - 已存在 Group 的校验/读取：只走 myMediaPartnerGroupsJSON，不回退 UI/DOM 解析
    """
    try:
        browser = getattr(browser_manager, "browser", None)
        if browser is None:
            logger.error("seed_partner_groups_from_discovery: browser_manager.browser 为空")
            return False

        # 0. 寻找 Discovery 标签页
        logger.info("正在寻找 Discovery 标签页...")
        discovery_tab = browser.get_tab(url="partner_discover.ihtml")
        if not discovery_tab:
            logger.error("未找到 Discovery 标签页，请确保浏览器已打开该页面。")
            return False

        # 1. 提取 tags
        tags = extract_filtertype_values_list_from_discovery_page(
            discovery_tab, parameter_name="businessModels"
        )
        if not tags:
            logger.warning("未提取到任何有效标签，退出。")
            return False

        # 2. 寻找或打开 Groups 标签页（优先复用已有标签）
        logger.info("正在寻找或打开 Groups 标签页...")
        groups_url = "https://app.impact.com/secure/advertiser/engage/mediapartners/view-mediapartnergroups-flow.ihtml"
        existing_groups = browser.get_tabs(url="view-mediapartnergroups-flow.ihtml")
        if existing_groups:
            groups_tab = existing_groups[0]
            logger.info("复用已打开的 Partner Groups 标签页。")
        else:
            logger.info("未找到 Groups 标签页，新开一个。")
            groups_tab = browser.new_tab(url=groups_url)

        # 复用标签时若未激活，容易出现等待卡住
        try:
            browser.activate_tab(groups_tab)
        except Exception as e:
            logger.debug("activate_tab: {}", e)

        # 3. 读取当前已存在的 Partner Groups：只走 myMediaPartnerGroupsJSON
        logger.info("正在通过 myMediaPartnerGroupsJSON 读取 Partner Groups 列表...")
        group_names = get_partner_group_names_from_myMediaPartnerGroupsJSON(groups_tab) or []
        if not group_names:
            logger.warning("myMediaPartnerGroupsJSON 返回空的 Group Names")
            return False

        # 4. 计算缺失的 groups
        need_to_create_tags = __tags_need_to_create(tags, group_names)
        if len(need_to_create_tags) == 0:
            logger.info("所有标签已存在，无需创建。")
            return True

        logger.info("需要创建的标签: {}", need_to_create_tags)

        # 5. 创建缺失 groups（UI 点击方式）
        success_count = 0
        for tag in need_to_create_tags:
            if create_group_ui(groups_tab, tag):
                success_count += 1
            time.sleep(0.5)

        # 6. 创建后再次读取并验证缺失列表为空
        logger.info("创建完成，开始复验缺失情况（再次读取 myMediaPartnerGroupsJSON）...")
        group_names_after = get_partner_group_names_from_myMediaPartnerGroupsJSON(groups_tab) or []
        missing_after = __tags_need_to_create(tags, group_names_after)
        if len(missing_after) == 0:
            logger.info("复验通过：缺失列表为空。成功创建 {}/{} 个 Group。", success_count, len(need_to_create_tags))
            return True

        logger.warning("复验未通过：仍缺失 {} 个 Group：{}", len(missing_after), missing_after)
        return False

    except Exception as e:
        logger.exception("seed_partner_groups_from_discovery 出错: {}", e)
        return False


def main() -> int:
    """
    允许脚本独立运行：初始化 BrowserManager 并执行一次种子逻辑。
    """
    from rich.console import Console
    # 使用 legacy_main 暴露出来的同一类型，避免静态类型检查认为两处 ConfigManager 不同
    from legacy_main import BrowserManager, ConfigManager

    console = Console()
    config = ConfigManager()
    browser_manager = BrowserManager(console=console, config=config)

    if not browser_manager.init():
        logger.error("BrowserManager 初始化失败：无法连接浏览器")
        return 1

    ok = seed_partner_groups_from_discovery(browser_manager)
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
