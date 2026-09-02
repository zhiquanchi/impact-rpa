"""Invite to Campaign 服务 - 负责 hover 显示按钮、打开弹窗、选择 campaign、发送邀请并监听结果。"""

import re
import time

from DrissionPage.errors import NoRectError
from loguru import logger

from domain.invite_campaign_result import InviteCampaignResult
from domain.invite_campaign_selectors import (
    CAMPAIGN_DROPDOWN_SELECTORS,
    CAMPAIGN_OPTION_SELECTORS,
    CAMPAIGN_SELECT_BUTTON_SELECTORS,
    CARD_SELECTORS,
    INVITE_API_URL_KEYWORD,
    INVITE_BUTTON_SELECTORS,
    MESSAGE_TEXTAREA_SELECTORS,
    MODAL_SELECTORS,
    PARTNER_GROUP_DROPDOWN_SELECTORS,
    PARTNER_GROUP_INPUT_SELECTORS,
    PARTNER_GROUP_OPTION_SELECTORS,
    SEND_INVITE_BUTTON_SELECTORS,
)
from domain.partner_category_listener import (
    CATEGORY_MORE_TRIGGER_XPATH,
    PartnerCategoryListener,
)

HOVER_WAIT = 1.0
MODAL_WAIT = 2.0
DROPDOWN_WAIT = 1.5
LISTENER_TIMEOUT = 15

ALL_PARTNERS_TEXT = "all partners"


def _normalize_group_text(text: str) -> str:
    """规范化 Partner Group 文本用于匹配（去计数后缀、去空白、忽略大小写）。"""
    raw = re.sub(r"\s*\(\d+\)\s*$", "", text or "")
    return re.sub(r"\s+", "", raw).strip().lower()


class InviteCampaignService:
    """邀请到 Campaign 的服务类。

    使用方式：
        service = InviteCampaignService(browser_manager)
        service.start_batch()               # 批任务开始：启动分类监听、清空缓存
        result = service.invite(campaign_name="TORRAS Japan")
        service.stop_batch()                # 批任务结束
    """

    def __init__(self, browser):
        self.browser = browser
        # 分类映射缓存（config/category_mapping.json，GUI 手动刷新）
        from domain.category_mapping_store import mapping_path

        config_dir = getattr(getattr(browser, "config", None), "config_dir", None)
        self.category_listener = PartnerCategoryListener(
            browser, mapping_file=mapping_path(config_dir) if config_dir else None
        )
        # 批内缓存：具体 tab 分类与兜底元素文本（整批相同，各解析一次复用）
        self._list_category_cache: str | None = None
        self._list_category_resolved = False
        self._source_text_cache: str | None = None

    # ------------------------------------------------------------------
    # 批任务生命周期
    # ------------------------------------------------------------------
    def start_batch(self) -> None:
        """批任务开始：启动列表接口监听，无数据时刷新页面捕获，重置缓存。"""
        self._list_category_cache = None
        self._list_category_resolved = False
        self._source_text_cache = None
        self.category_listener.start()
        self.category_listener.ensure_list_category()

    def stop_batch(self) -> None:
        """批任务结束：停止监听。"""
        self.category_listener.stop()

    # ------------------------------------------------------------------
    # 公开 API
    # ------------------------------------------------------------------
    def invite(
        self,
        campaign_name: str,
        message: str | None = None,
        card_index: int = 1,
    ) -> InviteCampaignResult:
        """对指定卡片执行邀请操作。

        Args:
            campaign_name: 要选中的 campaign 名称（部分匹配即可）
            message: 个性化消息，None 则不填写
            card_index: 操作第几个卡片（从 1 开始）

        Returns:
            InviteCampaignResult 邀请结果
        """
        try:
            # 1. hover 卡片让按钮显示
            card = self._find_card(card_index)
            if not card:
                return InviteCampaignResult(success=False, message="未找到卡片")

            if not self._hover_to_show_button(card):
                return InviteCampaignResult(success=False, message="hover 后按钮未显示")

            logger.info("Invite to Campaign 按钮已显示")

            # 1.5 解析 Partner Groups 分类：须在弹窗打开前完成 ——
            #     DOM 兜底要点击页面分类下拉，弹窗打开后会被遮罩挡住
            partner_group = self._resolve_partner_group(card)

            # 2. 点击按钮打开弹窗
            if not self._click_invite_button(card):
                return InviteCampaignResult(success=False, message="点击按钮失败")

            logger.info("已打开 Invite to Campaign 弹窗")

            # 3. 找到弹窗
            modal = self._find_modal()
            if not modal:
                return InviteCampaignResult(success=False, message="未找到弹窗")

            # 4. 选择 campaign
            if not self._select_campaign(modal, campaign_name):
                return InviteCampaignResult(success=False, message=f"选择 campaign 失败: {campaign_name}")

            logger.info(f"已选中 campaign: {campaign_name}")

            # 5. 填入 Partner Groups：
            #    - 具体 tab（Creators 等）：监听捕获的 businessModels 分类，批内缓存复用；
            #    - All Partners：混合列表，逐卡片用监听捕获的该 Partner 自身分类；
            #    - 监听完全无数据：点击分类下拉读取选中项兜底（批内缓存）。
            if partner_group:
                self._fill_partner_group(modal, partner_group)

            # 6. 填写个性化消息
            if message:
                self._fill_message(modal, message)

            # 7. 发送邀请并监听响应
            return self._send_and_listen(modal)

        except Exception as e:
            error_msg = str(e).lower()
            if "disconnect" in error_msg or "context" in error_msg or "target closed" in error_msg:
                logger.warning(f"邀请操作时页面断开: {e}")
                raise
            logger.error(f"邀请操作失败: {e}")
            return InviteCampaignResult(success=False, message=str(e))

    # ------------------------------------------------------------------
    # Partner Groups
    # ------------------------------------------------------------------
    def _resolve_partner_group(self, card) -> str | None:
        """解析这张卡片要填入的 Partner Groups 分类（监听优先，元素文本兜底）。

        - 具体 tab：businessModels 整批相同，批内解析一次并缓存复用；
        - All Partners（或监听无 tab 分类）：每个 Partner 用监听捕获的自身分类
          （列表响应 records[].businessModel.dv），逐卡片解析不缓存；
        - 监听完全无数据：取分类显示元素（PARTNER_GROUP_SOURCE_XPATH）文本，
          批内解析一次缓存复用。
        """
        category = self._get_list_category()
        if category and category.strip().lower() != ALL_PARTNERS_TEXT:
            return category

        if category is not None:
            # All Partners：逐卡片用监听捕获的自身分类
            try:
                self.category_listener.drain()
            except Exception as e:
                logger.debug(f"消费分类监听数据失败: {e}")

            name = PartnerCategoryListener.get_partner_name(card)
            if not name:
                logger.debug("未能从卡片提取 Partner 名称，跳过 Partner Groups 填写")
                return None
            own = self.category_listener.partner_business_model(name)
            if own:
                logger.info(
                    f"All Partners 列表下 [{name}] 自身分类: {own}（用于 Partner Groups）"
                )
                return own
            logger.info(
                f"All Partners 列表下 [{name}] 未监听到自身分类，跳过 Partner Groups 填写"
            )
            return None

        # 监听完全无数据：分类显示元素文本兜底
        return self._read_partner_group_source_text()

    def _get_list_category(self) -> str | None:
        """获取列表分类（URL businessModels 优先，其次监听捕获），批内缓存。"""
        if self._list_category_resolved:
            return self._list_category_cache
        self._list_category_resolved = True
        self._list_category_cache = None

        try:
            self.category_listener.drain()
        except Exception as e:
            logger.debug(f"消费分类监听数据失败: {e}")

        category = self.category_listener.current_list_category()
        if category:
            self._list_category_cache = category.strip()
            logger.info(f"本批次列表分类: {self._list_category_cache}")
        return self._list_category_cache

    def _read_partner_group_source_text(self) -> str | None:
        """监听无数据时的兜底：点击分类下拉读取选中项（批内缓存）。"""
        if self._source_text_cache is not None:
            return self._source_text_cache
        text = self.category_listener.read_category_display_text()
        if not text:
            logger.warning(
                f"监听无数据且未能从分类下拉取到选中项 "
                f"({CATEGORY_MORE_TRIGGER_XPATH})，本批次跳过 Partner Groups 填写"
            )
            return None
        self._source_text_cache = text
        logger.info(f"本批次 Partner Groups 取自分类下拉选中项兜底: {text}（整批复用）")
        return self._source_text_cache

    def _fill_partner_group(self, modal, value: str) -> bool:
        """在邀请弹窗的 Partner Groups tag 输入框中输入并选中匹配项。

        填写失败仅记录日志，不阻断邀请流程。
        """
        tag_input = None
        for sel in PARTNER_GROUP_INPUT_SELECTORS:
            try:
                ele = modal.ele(sel, timeout=0.5)
                if ele:
                    tag_input = ele
                    break
            except Exception:
                continue
        if not tag_input:
            logger.debug("邀请弹窗内未找到 Partner Groups 输入框，跳过填写")
            return False

        try:
            tag_input.click(by_js=True)
            time.sleep(0.1)
            tag_input.clear()
            tag_input.input(re.sub(r"\s+", "", value))
            time.sleep(0.5)
        except Exception as e:
            logger.warning(f"Partner Groups 输入失败: {e}")
            return False

        dropdown = self._find_partner_group_dropdown(tag_input, modal)
        if not dropdown:
            logger.warning(f"Partner Groups 输入 '{value}' 后未出现下拉选项")
            return False

        target = self._match_partner_group_option(dropdown, value)
        if not target:
            logger.warning(f"Partner Groups 下拉中未找到匹配 '{value}' 的选项")
            return False

        try:
            target.click()
            time.sleep(0.3)
            picked = (target.text or "").strip() or value
            logger.info(f"已填入 Partner Groups: {picked}")
            return True
        except Exception as e:
            logger.warning(f"点击 Partner Groups 选项失败: {e}")
            return False

    def _find_partner_group_dropdown(self, tag_input, modal):
        """查找 Partner Groups 下拉浮层（独立浮层挂 body / tag-input 容器内 / 弹窗内）。"""
        # 新版独立浮层（渲染在 body 下，不在弹窗内）
        for sel in PARTNER_GROUP_DROPDOWN_SELECTORS:
            try:
                ele = self.browser.find_element(sel, timeout=1)
                if ele:
                    return ele
            except Exception:
                continue

        # tag-input 容器内（下拉选项直接挂在容器下）
        try:
            container = tag_input.ele(
                'xpath:ancestor::*[@data-testid="uicl-tag-input"][1]', timeout=0.3
            )
            if container:
                return container
        except Exception:
            pass

        return modal

    def _match_partner_group_option(self, dropdown, value: str):
        """在下拉中查找与目标分类匹配的选项元素（精确 > 包含）。"""
        target_norm = _normalize_group_text(value)
        fallback = None
        for sel in PARTNER_GROUP_OPTION_SELECTORS:
            try:
                nodes = dropdown.eles(sel, timeout=0.3)
            except Exception:
                nodes = []
            for node in nodes or []:
                try:
                    text = (node.text or "").strip()
                    if not text:
                        continue
                    norm = _normalize_group_text(text)
                    if norm == target_norm:
                        return node
                    if target_norm in norm or norm in target_norm:
                        fallback = fallback or node
                except Exception:
                    continue
        return fallback

    # ------------------------------------------------------------------
    # 卡片与按钮
    # ------------------------------------------------------------------
    def _find_card(self, index: int):
        """找到第 N 个卡片。"""
        cards = self.browser.find_elements(CARD_SELECTORS[0], timeout=3)
        if not cards or len(cards) < index:
            logger.warning(f"未找到第 {index} 个卡片（共 {len(cards) if cards else 0} 个）")
            return None
        return cards[index - 1]

    def _hover_to_show_button(self, card) -> bool:
        """hover 卡片让 Invite to Campaign 按钮显示。"""
        try:
            self.browser.scroll_to_element(card)
            time.sleep(0.5)
        except Exception:
            pass

        for attempt in range(3):
            try:
                card.hover()
            except Exception:
                pass
            time.sleep(HOVER_WAIT)

            btn = self._find_invite_button_in_card(card)
            if btn:
                try:
                    rect = btn.rect
                    if rect and rect.get("height", 0) > 0:
                        return True
                except Exception:
                    return True
            logger.debug(f"第 {attempt + 1} 次 hover，按钮尚未显示")

        # 最后检查一次
        return self._find_invite_button_in_card(card) is not None

    def _find_invite_button_in_card(self, card):
        """在卡片内查找 Invite to Campaign 按钮。"""
        for sel in INVITE_BUTTON_SELECTORS:
            try:
                ele = card.ele(sel, timeout=0.3)
                if ele:
                    return ele
            except Exception:
                continue
        return None

    def _click_invite_button(self, card) -> bool:
        """点击 Invite to Campaign 按钮。"""
        btn = self._find_invite_button_in_card(card)
        if not btn:
            logger.warning("未找到 Invite to Campaign 按钮")
            return False

        try:
            btn.click()
        except NoRectError:
            logger.debug("普通点击失败，改用 JS 点击")
            try:
                btn.click(by_js=True)
            except Exception as e:
                logger.warning(f"JS 点击也失败: {e}")
                return False
        except Exception as e:
            logger.warning(f"点击按钮失败: {e}")
            return False

        time.sleep(MODAL_WAIT)
        return True

    # ------------------------------------------------------------------
    # 弹窗操作
    # ------------------------------------------------------------------
    def _find_modal(self):
        """查找 Invite to Campaign 弹窗。"""
        for sel in MODAL_SELECTORS:
            try:
                ele = self.browser.find_element(sel, timeout=2)
                if ele:
                    return ele
            except Exception:
                continue
        return None

    def _select_campaign(self, modal, campaign_name: str) -> bool:
        """点击 Select 展开下拉，选中指定 campaign。"""
        # 点击 Select 按钮
        select_btn = None
        for sel in CAMPAIGN_SELECT_BUTTON_SELECTORS:
            try:
                ele = modal.ele(sel, timeout=0.5)
                if ele:
                    select_btn = ele
                    break
            except Exception:
                continue

        if not select_btn:
            logger.warning("未找到 Select 按钮")
            return False

        try:
            select_btn.click()
        except Exception as e:
            logger.warning(f"点击 Select 按钮失败: {e}")
            return False
        time.sleep(DROPDOWN_WAIT)

        # 找 campaign 下拉浮层
        dropdown = None
        for sel in CAMPAIGN_DROPDOWN_SELECTORS:
            try:
                ele = self.browser.find_element(sel, timeout=2)
                if ele:
                    dropdown = ele
                    break
            except Exception:
                continue

        if not dropdown:
            logger.warning("未找到 campaign-select-dropdown")
            return False

        # 找目标选项
        target = None
        for sel in CAMPAIGN_OPTION_SELECTORS:
            try:
                options = dropdown.eles(sel, timeout=0.3)
            except Exception:
                options = []
            for opt in options or []:
                try:
                    text = opt.text.strip()
                    if campaign_name in text:
                        target = opt
                        break
                except Exception:
                    continue
            if target:
                break

        if not target:
            logger.warning(f"下拉中未找到包含 '{campaign_name}' 的选项")
            available = []
            try:
                all_options = dropdown.eles(CAMPAIGN_OPTION_SELECTORS[0], timeout=0.2)
                available = [o.text.strip() for o in all_options if o.text.strip()]
            except Exception:
                pass
            if available:
                logger.info(f"可用选项: {available}")
            return False

        # 点击 checkbox 选中
        try:
            checkbox = target.ele("css:[role='checkbox']", timeout=0.5)
            if checkbox:
                checkbox.click()
            else:
                target.click()
        except Exception as e:
            logger.warning(f"点击选项失败: {e}")
            return False

        time.sleep(0.8)
        return True

    def _fill_message(self, modal, message: str) -> bool:
        """填写个性化消息（占位实现）。"""
        # TODO: 实际填写逻辑，待确认输入框定位
        for sel in MESSAGE_TEXTAREA_SELECTORS:
            try:
                ele = modal.ele(sel, timeout=0.5)
                if ele:
                    ele.click(by_js=True)
                    time.sleep(0.1)
                    ele.clear()
                    ele.input(message)
                    logger.info(f"已填写个性化消息（长度: {len(message)}）")
                    return True
            except Exception:
                continue
        logger.warning("未找到个性化消息输入框")
        return False

    # ------------------------------------------------------------------
    # 发送 + 网络监听
    # ------------------------------------------------------------------
    def _stop_invite_listener(self) -> None:
        """停止 invite 监听，并恢复分类监听（保留已捕获数据）。

        DrissionPage 每个 tab 只有一组监听目标，_send_and_listen 启动 invite
        监听时会覆盖分类监听；恢复后后续卡片滚动加载时仍能捕获分类。
        """
        try:
            self.browser.tab.listen.stop()
        except Exception:
            pass
        try:
            self.category_listener.start(clear=False)
        except Exception as e:
            logger.debug(f"恢复分类监听失败: {e}")

    def _send_and_listen(self, modal) -> InviteCampaignResult:
        """点击 Send Invite 并通过网络监听判断结果。"""
        send_btn = None
        for sel in SEND_INVITE_BUTTON_SELECTORS:
            try:
                ele = modal.ele(sel, timeout=0.5)
                if ele:
                    send_btn = ele
                    break
            except Exception:
                continue

        if not send_btn:
            return InviteCampaignResult(success=False, message="未找到 Send Invite 按钮")

        # 启动监听
        tab = self.browser.tab
        tab.listen.start(INVITE_API_URL_KEYWORD, is_regex=False)
        logger.debug("网络监听已启动")

        logger.info("点击 Send Invite...")
        try:
            send_btn.click()
        except Exception as e:
            self._stop_invite_listener()
            return InviteCampaignResult(success=False, message=f"点击 Send Invite 失败: {e}")

        # 等待响应
        status_code = None
        body = ""
        post_data: dict = {}
        is_failed = True
        captured = False

        start = time.time()
        while time.time() - start < LISTENER_TIMEOUT:
            try:
                packet = tab.listen.wait(timeout=1)
                # listen.wait 超时返回 False（非 None），需用真值判断
                if not packet:
                    continue

                if INVITE_API_URL_KEYWORD not in packet.url.lower():
                    continue

                captured = True
                logger.info(f"捕获到邀请请求: {packet.url}")
                logger.info(f"  请求方法: {packet.method}")

                # 等待响应体加载完成
                try:
                    packet.wait_extra_info()
                except Exception:
                    pass

                is_failed = bool(packet.is_failed)
                post_data = packet.request.postData or {}

                # 读取状态码
                try:
                    all_info = packet.response.extra_info.all_info
                    status_code = all_info.get("statusCode")
                except Exception:
                    pass

                # 读取响应体
                try:
                    body = packet.response.body or ""
                except Exception:
                    body = ""

                logger.info(f"  HTTP 状态码: {status_code}")
                logger.info(f"  is_failed: {is_failed}")

                campaign_ids = post_data.get("campaignId", [])
                influencer_id = post_data.get("influencerId")
                logger.info(f"  campaignId: {campaign_ids}")
                logger.info(f"  influencerId: {influencer_id}")
                if body:
                    logger.info(f"  响应体: {body[:300]}")

                break

            except Exception as e:
                logger.debug(f"监听循环异常: {e}")
                break

        try:
            self._stop_invite_listener()
        except Exception:
            pass

        if not captured:
            return InviteCampaignResult(
                success=False,
                message="未捕获到邀请请求的响应",
            )

        # 判断成功
        if is_failed:
            success = False
            desc = "请求失败（网络层）"
        elif status_code and 200 <= status_code < 300:
            success = True
            desc = f"HTTP {status_code} OK"
        elif status_code:
            success = False
            desc = f"HTTP {status_code}"
            if body:
                desc += f" - {body[:100]}"
        else:
            success = not is_failed
            desc = "成功（无状态码，默认判断）"

        return InviteCampaignResult(
            success=success,
            message=desc,
            status_code=status_code,
            campaign_id=post_data.get("campaignId", []),
            influencer_id=post_data.get("influencerId"),
            response_body=body,
        )


__all__ = ["InviteCampaignService"]
