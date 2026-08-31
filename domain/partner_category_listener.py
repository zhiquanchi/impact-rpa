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

from urllib.parse import parse_qs, urlparse

from loguru import logger

# 发现页列表接口：滚动加载更多 Partner 时触发，其 businessModels 参数即当前分类 tab。
# 实测映射：All Partners=all, Creators=CREATORS, Content / Reviews=CONTENT_REVIEWS,
# Network=NETWORK（其余 tab 为名称转下划线大写，未经逐个实测，解析失败时回退 DOM 读取）。
LISTINGS_API_KEYWORD = "partner-ui/api/discover/listings"
BUSINESS_MODELS_TO_TAB = {
    "all": "All Partners",
    "CREATORS": "Creators",
    "CONTENT_REVIEWS": "Content / Reviews",
    "CROSS_AUDIENCE_MONETIZATION": "Cross Audience Monetization",
    "DEAL_COUPONS": "Deal / Coupons",
    "EMAIL_NEWSLETTER": "Email / Newsletter",
    "LOYALTY_REWARDS": "Loyalty / Rewards",
    "NETWORK": "Network",
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

    def __init__(self, browser):
        self.browser = browser
        self._list_category: str | None = None
        self._partner_business_model: dict[str, str] = {}

    # ------------------------------------------------------------------
    # 监听生命周期
    # ------------------------------------------------------------------
    @property
    def list_category(self) -> str | None:
        """当前列表分类（最后一次捕获的 businessModels 映射值）。"""
        return self._list_category

    def start(self) -> None:
        """开始监听列表接口，并清空已捕获的分类数据。"""
        self._list_category = None
        self._partner_business_model = {}
        try:
            self.browser.tab.listen.start(LISTINGS_API_KEYWORD, is_regex=False)
            logger.debug(f"已启动列表接口监听: {LISTINGS_API_KEYWORD}")
        except Exception as e:
            logger.debug(f"启动分类监听失败（不影响发送，回退 DOM 读取）: {e}")

    def stop(self) -> None:
        """停止监听列表接口。"""
        try:
            self.browser.tab.listen.stop()
        except Exception:
            pass

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
        """解析单个列表请求：URL 参数取列表分类，响应体取 Partner 自身分类。"""
        url = getattr(packet, "url", "") or ""
        if LISTINGS_API_KEYWORD not in url:
            return

        qs = parse_qs(urlparse(url).query)
        bm = (qs.get("businessModels") or [""])[0]
        if bm:
            self._list_category = BUSINESS_MODELS_TO_TAB.get(
                bm, bm.replace("_", " ").title()
            )
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


__all__ = [
    "LISTINGS_API_KEYWORD",
    "BUSINESS_MODELS_TO_TAB",
    "PartnerCategoryListener",
    "find_card_container",
    "dv_text",
]
