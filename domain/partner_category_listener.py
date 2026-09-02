"""Partner 分类监听器 — 监听发现页列表接口，捕获列表分类与每个 Partner 自身的分类。

数据来源（DrissionPage 网络监听）：
- 列表接口 GET /partner-ui/api/discover/listings?businessModels=... 在页面初始加载
  和每次滚动加载更多时触发。URL 的 businessModels 参数即当前 tab 的分类。
- 响应体 records[].businessModel.dv 是每个 Partner 自身的分类，比 tab 栏更全
  （含 More 菜单中的 Technology Solutions / Search / Comparison 等）。
- records[].name 为 {dv: {name: "..."}} 嵌套结构，businessModel 为 {dv: "..."}。

用途：批量发送 Proposal 时，具体 tab（Creators 等）直接用 tab 分类填 Partner Group；
All Partners（businessModels=all）混合列表下按 Partner 自身分类填入。
"""

import time
from urllib.parse import parse_qs, urlparse

from loguru import logger

# 发现页列表接口：滚动加载更多 Partner 时触发，其 businessModels 参数即当前分类 tab。
LISTINGS_API_KEYWORD = "partner-ui/api/discover/listings"

# 表格结构接口：页面加载时请求，其 searchWidget.filterTypes 含 businessModels
# 的完整 label<->value 列表 —— 账号无关的权威分类映射来源，运行时自动捕获。
TABLESTRUCTURE_KEYWORD = "partner-ui/api/discover/tablestructure"

# 分类监听的全部目标（listings 取当前分类与 Partner 自身分类，tablestructure 取映射表）
LISTEN_TARGETS = [LISTINGS_API_KEYWORD, TABLESTRUCTURE_KEYWORD]

# businessModels 值 -> 分类显示名 的兜底映射（平台标准枚举，各账号一致）。
# 运行时优先使用 tablestructure API 捕获的 label<->value（见 _bm_label_map），
# 拉取失败才用本表；本表数据为 2026-09-02 实测采集（scripts/collect_category_mapping.py）。
# 注意三处易错点：
# - Cross Audience Monetization 的 URL 值是缩写 CROSS_AUDIENCE（非全称）；
# - Deal / Coupons 的值是 DEAL_COUPON（无 S）；
# - Search / Comparison=MEDIA_ARBITRAGE、Technology Solutions=COMMERCE_SOLUTION（More 菜单）。
# 分类名与各账号 Partner Groups 组名（如 "Deal/Coupons (166758)"）通常仅空格差异，
# 归一化去空格后可精确匹配；账号未建对应组时 tag 下拉匹配不上会自动跳过。

# 列表页分类触发元素：文本只是 "More"，真实分类在点击展开的下拉选中项里。
CATEGORY_MORE_TRIGGER_XPATH = '//*[@id="app"]/div/div[1]/div/div[2]/div[2]/div/div'

# 展开的分类下拉中，当前选中项的候选选择器（iui 组件族，按精确度排序）
CATEGORY_DROPDOWN_SELECTED_SELECTORS = [
    'css:.iui-menu-item.selected',
    'css:.iui-dropdown-item.selected',
    'css:.iui-list-item.selected',
    'css:[role="menu"] [aria-selected="true"]',
    'css:[role="menuitem"][aria-checked="true"]',
    'css:li.selected',
]

BUSINESS_MODELS_TO_TAB = {
    "home": "Home",
    "all": "All Partners",
    "CREATORS": "Creators",
    "CONTENT_REVIEWS": "Content / Reviews",
    "CROSS_AUDIENCE": "Cross Audience Monetization",
    "DEAL_COUPON": "Deal / Coupons",
    "EMAIL_NEWSLETTER": "Email / Newsletter",
    "LOYALTY_REWARDS": "Loyalty / Rewards",
    "NETWORK": "Network",
    "MEDIA_ARBITRAGE": "Search / Comparison",
    "COMMERCE_SOLUTION": "Technology Solutions",
}


def find_card_container(ele, max_levels: int = 12):
    """从任意元素向上查找其所属卡片容器（.iui-card / .discovery-card）。"""
    cur = ele
    for _ in range(max_levels):
        if not cur:
            return None
        try:
            cls = (cur.attr("class") or "").lower()
            if "iui-card" in cls or "discovery-card" in cls:
                return cur
            cur = cur.parent()
        except Exception:
            return None
    return None


def dv_text(value) -> str:
    """提取列表响应中 {dv: ...} 结构的文本值。

    dv 可能是字符串（businessModel={"dv": "Creators"}），
    也可能是对象（name={"dv": {"name": "Mega American", ...}}）。
    """
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, dict):
        dv = value.get("dv")
        if isinstance(dv, str):
            return dv.strip()
        if isinstance(dv, dict):
            return (dv.get("name") or "").strip()
    return ""


class PartnerCategoryListener:
    """监听列表接口，维护「列表分类」与「Partner 名称 -> 自身分类」映射。

    使用方式：
        listener = PartnerCategoryListener(browser)
        listener.start()                  # send_proposals 入口
        listener.drain()                  # 主循环每轮调用（非阻塞）
        listener.resolve_partner_group_value(btn, selected_tab)  # 点击前解析
        listener.stop()                   # 退出时
    """

    def __init__(self, browser, mapping_file: str | None = None):
        self.browser = browser
        self._list_category: str | None = None
        self._partner_business_model: dict[str, str] = {}
        # businessModels 值 -> 显示名：配置文件缓存作初始值（很少变动，GUI 手动刷新），
        # 运行时 tablestructure 捕获自动覆盖，最后是静态兜底表。
        self._bm_label_map: dict[str, str] = {}
        if mapping_file:
            from domain.category_mapping_store import load_mapping

            cached = load_mapping(mapping_file)
            if cached:
                self._bm_label_map = cached
                logger.debug(f"已从配置文件加载分类映射 {len(cached)} 项")

    # ------------------------------------------------------------------
    # 监听生命周期
    # ------------------------------------------------------------------
    @property
    def list_category(self) -> str | None:
        """当前列表分类（最后一次捕获的 businessModels 映射值）。"""
        return self._list_category

    def bm_to_label(self, bm: str) -> str:
        """businessModels 原始值 -> 分类显示名。

        优先用 tablestructure 捕获的映射（随账号/平台变化自动更新），
        其次静态兜底表，最后按平台命名规律拼接。
        """
        if not bm:
            return ""
        return self._bm_label_map.get(bm) or BUSINESS_MODELS_TO_TAB.get(
            bm, bm.replace("_", " ").title()
        )

    def partner_business_model(self, name: str) -> str | None:
        """按 Partner 显示名称查询监听捕获的自身分类（All Partners 混合列表用）。"""
        return self._partner_business_model.get((name or "").strip().lower())

    def start(self, clear: bool = True) -> None:
        """开始监听列表接口。

        Args:
            clear: True 时清空已捕获的分类数据（批任务开始）；
                   False 时保留数据仅重启监听（被其他监听覆盖后恢复用）。
        """
        if clear:
            self._list_category = None
            self._partner_business_model = {}
        try:
            self.browser.tab.listen.start(LISTEN_TARGETS, is_regex=False)
            logger.debug(f"已启动分类相关接口监听: {LISTEN_TARGETS}")
        except Exception as e:
            logger.debug(f"启动分类监听失败（不影响发送，回退 DOM 读取）: {e}")

    def stop(self) -> None:
        """停止监听列表接口。"""
        try:
            self.browser.tab.listen.stop()
        except Exception:
            pass

    def ensure_list_category(
        self, first_wait: float = 5.0, retry_wait: float = 3.0
    ) -> bool:
        """确保已捕获列表分类；没有数据时刷新页面（必要时滚动触发）再等。

        监听只能捕获 start() 之后的请求，而首屏列表往往在任务开始前已加载完成；
        刷新页面让列表接口重新请求即可捕获。刷新后仍未捕获时，滚动列表容器
        触发加载更多再试一次。

        Returns:
            True=已有或已捕获列表分类；False=最终未捕获（调用方自行兜底）。
        """
        self.drain()
        if self._list_category:
            return True

        tab = self.browser.tab
        if tab is None:
            return False

        try:
            logger.info("监听暂无列表数据，刷新页面以捕获")
            tab.refresh()
            try:
                tab.wait.doc_loaded(timeout=15)
            except Exception:
                pass
            if self._wait_list_category(first_wait):
                return True

            logger.debug("刷新后仍未捕获列表接口，滚动列表容器触发加载更多")
            try:
                self.browser.scroll_down(400)
                time.sleep(1.0)
                if self._wait_list_category(retry_wait):
                    return True
            except Exception as e:
                logger.debug(f"滚动触发加载失败: {e}")

            logger.warning("监听未捕获到列表接口数据，分类将回退 DOM 读取")
            return False
        except Exception as e:
            logger.debug(f"刷新捕获分类失败（不影响任务执行）: {e}")
            return False

    def _wait_list_category(self, timeout: float) -> bool:
        """轮询 drain 监听数据，捕获到列表分类即返回 True。"""
        deadline = time.time() + timeout
        while time.time() < deadline:
            self.drain()
            if self._list_category:
                logger.info(f"监听已捕获列表分类: {self._list_category}")
                return True
            time.sleep(0.3)
        return False

    def read_category_display_text(self) -> str:
        """兜底：点击分类栏 More 触发元素展开下拉，读取当前选中的具体分类值。

        触发元素自身文本只是 "More" 不是具体分类，真实分类在展开下拉的
        选中项里；取不到（元素缺失/未展开/无选中项）返回空串。
        """
        tab = self.browser.tab
        if tab is None:
            return ""
        try:
            more_ele = self.browser.find_element(
                f"xpath:{CATEGORY_MORE_TRIGGER_XPATH}", timeout=2
            )
        except Exception:
            more_ele = None
        if not more_ele:
            logger.debug(f"未找到分类触发元素: {CATEGORY_MORE_TRIGGER_XPATH}")
            return ""

        # 点击展开下拉（真实点击优先，失败回退 JS 点击）
        try:
            more_ele.click()
        except Exception:
            try:
                more_ele.click(by_js=True)
            except Exception as e:
                logger.debug(f"点击分类触发元素失败: {e}")
                return ""
        time.sleep(0.5)

        # 读取下拉中当前选中项（"More" 自身的选中态不算）
        value = ""
        for sel in CATEGORY_DROPDOWN_SELECTED_SELECTORS:
            try:
                nodes = tab.eles(sel, timeout=0.5)
            except Exception:
                nodes = []
            for node in nodes or []:
                try:
                    text = (node.text or "").strip()
                except Exception:
                    continue
                if text and text.lower() != "more":
                    value = text
                    break
            if value:
                break
        if not value:
            logger.debug("分类下拉中未找到选中的具体分类项")

        # 收起下拉：再点一次触发元素，失败则按 Esc
        try:
            more_ele.click()
        except Exception:
            try:
                tab.actions.key("ESC")
            except Exception:
                pass
        time.sleep(0.2)
        if value:
            logger.info(f"分类下拉选中项: {value}")
        return value

    def drain(self) -> None:
        """非阻塞消费监听到的列表请求，更新列表分类与 Partner 自身分类映射。

        列表请求在页面初始加载和每次滚动加载更多时触发，
        因此滚动过程中分类会自动保持最新（如用户中途切换了 tab）。
        """
        try:
            while True:
                packet = self.browser.tab.listen.wait(timeout=0.05)
                if not packet:
                    break
                self._consume_packet(packet)
        except Exception as e:
            logger.debug(f"消费分类监听数据失败: {e}")

    # ------------------------------------------------------------------
    # 分类解析
    # ------------------------------------------------------------------
    def resolve_partner_group_value(self, ele, selected_tab: str | None) -> str | None:
        """决定填入 Partner Group 的分类值。

        - 具体 tab（Creators 等）：直接用当前 tab 分类。
        - All Partners（businessModels=all）：列表混合了所有分类，
          用列表响应中该 Partner 自身的 businessModel.dv（listener 捕获）；
          查不到时回退当前 tab 值。
        """
        if not selected_tab or selected_tab == "All Partners":
            name = self.get_partner_name(ele)
            if name:
                own = self._partner_business_model.get(name.lower())
                if own:
                    logger.debug(
                        f"All Partners 列表下 [{name}] 自身分类: {own}（用于 Partner Group）"
                    )
                    return own
        return selected_tab

    @staticmethod
    def get_partner_name(ele) -> str | None:
        """从按钮/卡片元素提取 Partner 显示名称（卡片 .name 区域文本）。"""
        card = find_card_container(ele)
        target = card or ele
        try:
            for sel in ("css:.name .text-ellipsis", "css:.name"):
                n = target.ele(sel, timeout=0.1)
                if n and (n.text or "").strip():
                    return n.text.strip()
        except Exception:
            pass
        return None

    # ------------------------------------------------------------------
    # 内部
    # ------------------------------------------------------------------
    def _consume_packet(self, packet) -> None:
        """按 URL 分流消费：tablestructure 取分类映射，listings 取当前分类。"""
        url = getattr(packet, "url", "") or ""
        if TABLESTRUCTURE_KEYWORD in url:
            self._consume_tablestructure(packet)
            return
        if LISTINGS_API_KEYWORD not in url:
            return

        qs = parse_qs(urlparse(url).query)
        bm = (qs.get("businessModels") or [""])[0]
        if bm:
            self._list_category = self.bm_to_label(bm)
            logger.debug(
                f"列表接口捕获分类: businessModels={bm} -> {self._list_category}"
            )

        try:
            body = packet.response.body
        except Exception:
            body = None
        records = body.get("records") if isinstance(body, dict) else None
        for rec in records or []:
            try:
                if not isinstance(rec, dict):
                    continue
                name = dv_text(rec.get("name"))
                category = dv_text(rec.get("businessModel"))
                if name and category:
                    self._partner_business_model[name.lower()] = category
            except Exception:
                continue

    def _consume_tablestructure(self, packet) -> None:
        """从 tablestructure 响应提取 businessModels 的 value<->label 完整映射。"""
        try:
            body = packet.response.body
        except Exception:
            return
        if not isinstance(body, dict):
            return
        try:
            widget = body.get("searchWidget") or {}
            for ft in widget.get("filterTypes") or []:
                if not isinstance(ft, dict) or ft.get("parameterName") != "businessModels":
                    continue
                items = ft.get("filterValues")
                if not isinstance(items, list):
                    continue
                for item in items:
                    if not isinstance(item, dict):
                        continue
                    value = (item.get("value") or "").strip()
                    label = (item.get("label") or "").strip()
                    if value and label:
                        self._bm_label_map[value] = label
                if self._bm_label_map:
                    logger.debug(
                        f"tablestructure 捕获分类映射 {len(self._bm_label_map)} 项"
                    )
                return
        except Exception as e:
            logger.debug(f"解析 tablestructure 失败: {e}")


__all__ = [
    "LISTINGS_API_KEYWORD",
    "TABLESTRUCTURE_KEYWORD",
    "LISTEN_TARGETS",
    "CATEGORY_MORE_TRIGGER_XPATH",
    "CATEGORY_DROPDOWN_SELECTED_SELECTORS",
    "BUSINESS_MODELS_TO_TAB",
    "PartnerCategoryListener",
    "find_card_container",
    "dv_text",
]
