"""Invite to Campaign 服务 - 负责 hover 显示按钮、打开弹窗、选择 campaign、发送邀请并监听结果。"""

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
    SEND_INVITE_BUTTON_SELECTORS,
)

HOVER_WAIT = 1.0
MODAL_WAIT = 2.0
DROPDOWN_WAIT = 1.5
LISTENER_TIMEOUT = 15


class InviteCampaignService:
    """邀请到 Campaign 的服务类。

    使用方式：
        service = InviteCampaignService(browser_manager)
        result = service.invite(campaign_name="TORRAS Japan")
    """

    def __init__(self, browser):
        self.browser = browser

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

            # 5. 填写个性化消息
            if message:
                self._fill_message(modal, message)

            # 6. 发送邀请并监听响应
            return self._send_and_listen(modal)

        except Exception as e:
            error_msg = str(e).lower()
            if "disconnect" in error_msg or "context" in error_msg or "target closed" in error_msg:
                logger.warning(f"邀请操作时页面断开: {e}")
                raise
            logger.error(f"邀请操作失败: {e}")
            return InviteCampaignResult(success=False, message=str(e))

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
            tab.listen.stop()
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
                if packet is None:
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
            tab.listen.stop()
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
