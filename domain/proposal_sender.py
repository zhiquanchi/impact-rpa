import time
from loguru import logger

from legacy_main import ProposalSender as LegacyProposalSender, SendProposalsResult
from domain.proposal_modal_service import ProposalModalService
from domain.selectors import MODAL_IFRAME_SELECTOR
from domain.wait_utils import wait_until


class ProposalSender(LegacyProposalSender):
    """在保留原行为的基础上，增加服务化边界与公开接口。"""

    def __init__(self, browser, template_manager, console, config):
        super().__init__(browser, template_manager, console, config)
        self.modal_service = ProposalModalService(self)

    def get_template_term_options(self, iframe) -> list[str]:
        """菜单层可调用的公开方法，替代跨层访问私有方法。"""
        return self._get_template_term_options(iframe)

    def _handle_proposal_modal(self, selected_tab: str | None = None, template_content: str = "") -> bool:
        return self.modal_service.handle_modal(selected_tab=selected_tab, template_content=template_content)

    def _wait_for_modal_iframe(self):
        start_time = time.time()
        iframe = wait_until(
            lambda: self.browser.find_element(MODAL_IFRAME_SELECTOR, timeout=0.5),
            timeout=self.modal_wait_timeout,
            interval=self.modal_poll_interval,
        )
        if iframe:
            elapsed = time.time() - start_time
            if elapsed > 2.0:
                logger.debug(f"弹窗 iframe 出现（等待了 {elapsed:.2f} 秒）")
            return iframe

        elapsed = time.time() - start_time
        logger.warning(f"等待 Proposal 弹窗超时（等待了 {elapsed:.2f} 秒，超时设置: {self.modal_wait_timeout} 秒）")
        return None


__all__ = ["ProposalSender", "SendProposalsResult"]

