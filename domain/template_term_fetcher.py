"""Template Term 选项获取器。

通过 DrissionPage 网络监听读取 Impact Template Terms 管理页的接口响应，
只返回 Template Terms 的 name 字段。
"""

from __future__ import annotations

import html
import json
import re
import time
from typing import Any

from loguru import logger


class TemplateTermOptionsFetcher:
    """通过管理页网络响应获取 Template Term 下拉选项。"""

    SOURCE_URL = (
        "https://app.impact.com/secure/advertiser/engage/contracts/library/"
        "view-manage-ios-flow.ihtml"
    )
    # 使用正则匹配目标 API，忽略动态参数
    LISTEN_TARGET_REGEX = r".*myInsertionOrdersJSON\.ihtml.*"

    def __init__(
        self,
        browser,
        *,
        source_url: str | None = None,
        listen_timeout: float = 10.0,
    ):
        self.browser = browser
        self.source_url = source_url or self.SOURCE_URL
        self.listen_timeout = listen_timeout

    def fetch(self) -> list[str]:
        """获取 Template Term 选项的入口函数。"""
        tab = self.get_tab()
        original_url = self.get_current_url(tab)
        listener_started = False

        try:
            self.start_listener(tab)
            listener_started = True
            self.open_source_page(tab)
            # 页面加载过程中会自动请求 myInsertionOrdersJSON.ihtml
            packet = self.wait_for_target_packet(tab)
            if not packet:
                logger.warning("未捕获到 Template Terms 接口响应")
                return []

            options = self.extract_options_from_packet(packet)
            return self.normalize_options(options)
        finally:
            if listener_started:
                self.stop_listener(tab)
            self.restore_page(tab, original_url)

    def get_tab(self) -> Any:
        """获取当前浏览器 tab。"""
        # 优先使用 browser 的 latest_tab，如果存在则返回
        if hasattr(self.browser, "latest_tab"):
            tab = self.browser.latest_tab
            if tab:
                return tab
        # 兼容旧的 .tab 属性
        tab = getattr(self.browser, "tab", None)
        if not tab:
            raise RuntimeError("浏览器未连接，无法获取 Template Term 选项")
        return tab

    def get_current_url(self, tab: Any) -> str:
        """获取当前页面 URL，便于结束后恢复页面。"""
        try:
            return str(tab.url or "")
        except Exception:
            return ""

    def start_listener(self, tab: Any) -> None:
        """启动网络监听，必须在打开管理页之前调用。"""
        tab.listen.start(
            targets=self.LISTEN_TARGET_REGEX,
            is_regex=True,
            method="GET",
            res_type=True,
        )
        logger.debug(
            f"已启动 Template Terms 接口监听，正则模式: {self.LISTEN_TARGET_REGEX}"
        )

    def stop_listener(self, tab: Any) -> None:
        """停止网络监听。"""
        try:
            tab.listen.stop()
        except Exception as exc:
            logger.debug(f"停止 Template Terms 接口监听失败: {exc}")

    def open_source_page(self, tab: Any) -> None:
        """打开 Template Term 管理页以触发相关网络请求。"""
        logger.info(f"正在打开 Template Terms 管理页: {self.source_url}")
        try:
            # 使用 get 方法会自动等待页面加载完成
            tab.get(self.source_url, timeout=20)
        except TypeError:
            # 兼容性处理
            tab.get(self.source_url)

    def wait_for_target_packet(self, tab: Any) -> Any:
        """等待并返回目标 API 的网络包。"""
        deadline = time.time() + self.listen_timeout
        while time.time() < deadline:
            # wait 方法会等待一个数据包，超时返回 False（非 None）
            packet = tab.listen.wait(timeout=min(1.0, deadline - time.time()))
            if packet and self.is_template_term_packet(packet):
                return packet
        return None

    def is_template_term_packet(self, packet: Any) -> bool:
        """判断网络包是否包含 Template Term 选项数据。"""
        url = str(getattr(packet, "url", "") or "")
        return bool(re.search(self.LISTEN_TARGET_REGEX, url))

    def extract_options_from_packet(self, packet: Any) -> list[str]:
        """从单个网络包响应中提取 Template Term 选项。"""
        body = getattr(getattr(packet, "response", None), "body", None)
        data = self._normalize_response_body(body)
        if not isinstance(data, dict):
            return []

        records = data.get("records")
        if not isinstance(records, list):
            return []

        names: list[str] = []
        for record in records:
            if not isinstance(record, dict):
                continue

            name_info = record.get("insertionOrderInfo.name")
            if not isinstance(name_info, dict):
                continue

            raw_name = name_info.get("dv") or name_info.get("crv") or ""
            name = self._strip_html(str(raw_name))
            if name:
                names.append(name)

        return names

    def normalize_options(self, options: list[str]) -> list[str]:
        """清洗、去重并过滤无效选项。"""
        seen: set[str] = set()
        normalized_options: list[str] = []

        for option in options:
            text = re.sub(r"\s+", " ", str(option)).strip()
            norm = text.lower()
            if not text or norm in seen:
                continue
            seen.add(norm)
            normalized_options.append(text)

        logger.info(
            f"获取到 {len(normalized_options)} 个 Template Terms: {normalized_options}"
        )
        return normalized_options

    def restore_page(self, tab: Any, original_url: str) -> None:
        """获取完成后恢复到原始页面。"""
        if not original_url or original_url == self.source_url:
            return

        try:
            try:
                tab.get(original_url, timeout=20)
            except TypeError:
                tab.get(original_url)
            logger.debug(f"已恢复原始页面: {original_url}")
        except Exception as exc:
            logger.warning(f"恢复原始页面失败: {exc}")

    def _normalize_response_body(self, body: Any) -> Any:
        if body is None:
            return None
        if isinstance(body, (dict, list)):
            return body
        if isinstance(body, bytes):
            body = body.decode("utf-8", errors="ignore")
        if isinstance(body, str):
            text = body.strip()
            if not text:
                return None
            return json.loads(text)
        return body

    def _strip_html(self, value: str) -> str:
        text = re.sub(r"<br\s*/?>", " ", value, flags=re.IGNORECASE)
        text = re.sub(r"<[^>]+>", "", text)
        return html.unescape(text).strip()
