from loguru import logger


class ProposalModalService:
    """负责 Proposal 弹窗内的流程编排。"""

    def __init__(self, sender):
        self.sender = sender

    def handle_modal(self, selected_tab: str | None = None, template_content: str = "") -> bool:
        try:
            iframe = self.sender._wait_for_modal_iframe()
            if not iframe:
                logger.warning(f"未找到弹窗 iframe (类别: {selected_tab or '未知'})，可能弹窗加载超时")
                return False

            ok = self.sender._select_template_term(iframe, self.sender.template_term)
            if not ok:
                raise RuntimeError(f"template_term_not_found: {self.sender.template_term}")

            self.sender._select_tomorrow_date(iframe)
            self.sender._input_comment(iframe, template_content)

            should_input_partner_groups = bool(getattr(self.sender, "input_partner_groups_tag", True))
            if should_input_partner_groups and selected_tab:
                self.sender._input_tag_and_select(iframe, selected_tab)

            self.sender._submit_proposal(iframe)
            return True
        except Exception as e:
            error_msg = str(e).lower()
            if "disconnect" in error_msg or "context" in error_msg or "target closed" in error_msg:
                logger.warning(f"处理弹窗时页面断开: {e}")
                raise
            logger.error(f"处理弹窗失败: {e}")
        return False

