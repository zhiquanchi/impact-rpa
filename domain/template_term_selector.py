"""
Template Term 下拉框选择器

将 ProposalSender 中 Template Term 下拉框的选择逻辑独立出来，
包含选项解析、相似度匹配、交互式选择及配置持久化。
"""

import re
import time
from difflib import SequenceMatcher

import questionary
from loguru import logger

from domain.template_term_utils import (
    _open_template_term_dropdown,
    try_native_template_term_select,
)


class TemplateTermNotConfiguredError(Exception):
    """Template Term 未配置异常

    当 settings.template_term 为空、未定义或不存在时抛出此异常。
    """

    def __init__(self, message: str = "Template Term 未配置"):
        self.message = message
        super().__init__(self.message)


class TemplateTermSelector:
    """Template Term 下拉框选择器，负责在 iframe 中选择指定 Template Term。"""

    # 相似度匹配阈值
    SIMILARITY_THRESHOLD = 0.72
    # 相似度平局容差（得分差在此范围内的视为并列）
    SIMILARITY_TIE_EPS = 0.005

    def __init__(self, config=None):
        """
        Args:
            config: 配置对象，需提供 load_settings() / save_settings()，
                    用于持久化用户通过交互式选择做出的 Template Term 选择。
                    为 None 时跳过持久化。
        """
        self.config = config

    def select(self, iframe, term_text: str | None, tab=None) -> bool:
        """在 iframe 中选择指定的 Template Term。

        Args:
            iframe: 弹窗 iframe 对象
            term_text: 要选择的 Template Term 文本。
                       为空时抛出 TemplateTermNotConfiguredError。
            tab: 主页面 tab 对象（用于 portal 渲染的下拉层定位）

        Returns:
            bool: 选择成功返回 True，失败返回 False

        Raises:
            TemplateTermNotConfiguredError: 当 term_text 为空时抛出
            RuntimeError: 当无法找到匹配的 Template Term 时抛出
        """
        if not term_text or not str(term_text).strip():
            error_msg = (
                "Template Term 未配置！\n"
                "当前 settings.template_term 为空或未定义。\n"
                "请在开始发送前通过确认弹窗选择 Template Term。"
            )
            logger.error(error_msg)
            raise TemplateTermNotConfiguredError(error_msg)

        try:
            desired = (term_text or "Commission Tier Terms").strip()
            desired_norm = re.sub(r"\s+", " ", desired).strip().lower()
            logger.debug(
                f"匹配 Template Term: desired='{desired}', desired_norm='{desired_norm}'"
            )

            # 策略1：Template Term 关联的原生 select（选中后校验，失败则回退）
            if try_native_template_term_select(iframe, desired):
                time.sleep(0.3)
                return True

            # 策略2：自定义 multi-select 下拉组件
            dropdown = _open_template_term_dropdown(iframe, tab=tab)
            if not dropdown:
                logger.debug("未找到 Template Term 下拉框或选项")
                return False

            options = self._parse_dropdown_options(dropdown)
            if not options:
                logger.debug("Template Term 下拉框中无可用选项")
                return False

            return self._match_and_select(iframe, options, desired, desired_norm)

        except Exception as e:
            logger.error(f"选择 Template Term 失败: {e}")
            return False

    # ------------------------------------------------------------------
    # 内部方法
    # ------------------------------------------------------------------

    def _parse_dropdown_options(self, dropdown) -> list[tuple[str, str, object]]:
        """解析下拉框中的选项，返回 (显示文本, 规范化文本, 元素) 列表（已去重）。"""
        options: list[tuple[str, str, object]] = []

        # 优先从 listbox 中获取选项
        listbox = dropdown.ele('css:ul[role="listbox"]', timeout=0.5)
        if listbox:
            items = listbox.eles("css:li")
        else:
            items = dropdown.eles('xpath:.//li[@role="option"]')

        for it in items or []:
            txt = it.text or ""
            txtn = re.sub(r"\s+", " ", txt).strip().lower()
            if txtn:
                options.append((txt, txtn, it))

        if not options:
            nodes = dropdown.eles("css:div.text-ellipsis")
            for it in nodes or []:
                txt = it.text or ""
                txtn = re.sub(r"\s+", " ", txt).strip().lower()
                if txtn:
                    options.append((txt, txtn, it))

        # 去重
        seen_norm = set()
        unique: list[tuple[str, str, object]] = []
        for txt, txtn, ele in options:
            if txtn not in seen_norm:
                seen_norm.add(txtn)
                unique.append((txt, txtn, ele))

        logger.debug(
            f"找到 {len(unique)} 个唯一 Template Term 选项: {[txt for txt, _, _ in unique]}"
        )
        return unique

    def _match_and_select(
        self,
        iframe,
        options: list[tuple[str, str, object]],
        desired: str,
        desired_norm: str,
    ) -> bool:
        """根据相似度匹配选项并执行选择。"""
        scored = [
            (SequenceMatcher(None, desired_norm, n).ratio(), t, e)
            for (t, n, e) in options
        ]
        scored.sort(key=lambda x: -x[0])
        best_score = scored[0][0] if scored else 0.0
        logger.debug(
            f"Template Term 相似度得分: {[(t, f'{score:.3f}') for score, t, _ in scored]}"
        )
        logger.debug(f"最佳得分: {best_score:.3f}, 阈值: {self.SIMILARITY_THRESHOLD}")

        if best_score >= self.SIMILARITY_THRESHOLD:
            top = [s for s in scored if s[0] >= best_score - self.SIMILARITY_TIE_EPS]
            logger.debug(
                f"匹配成功，最佳得分 {best_score:.3f} ≥ 阈值 {self.SIMILARITY_THRESHOLD}，"
                f"找到 {len(top)} 个候选项"
            )
            if len(top) == 1:
                return self._click_option(top[0][2], top[0][1])

            # 多个并列候选 → 交互式选择
            candidates = [
                (f"{t}  [dim](相似度 {best_score:.2f})[/dim]", e, t)
                for (_, t, e) in top
            ]
            return self._prompt_and_pick(
                candidates, "\n[bold]多个相似候选项，请选择：[/bold]"
            )

        logger.debug(
            f"匹配失败，最佳得分 {best_score:.3f} < 阈值 {self.SIMILARITY_THRESHOLD}"
        )
        if options:
            self.console_print(
                f"\n[bold]未匹配到配置项（最高相似度 {best_score:.2f}，"
                f"需 ≥{self.SIMILARITY_THRESHOLD:.2f}），以下为所有可选项：[/bold]"
            )
            all_candidates = [(t, e, t) for (t, _, e) in options]
            return self._prompt_and_pick(all_candidates, "")

        logger.debug("未找到可选项")
        return False

    def _click_option(self, elem, label: str, *, persist_choice: bool = False) -> bool:
        """点击选项元素，可选地将选择持久化到配置。"""
        try:
            elem.wait.clickable()
        except Exception:
            pass
        try:
            elem.click()
        except Exception:
            elem.click(by_js=True)

        if persist_choice:
            self._persist_choice(label)

        logger.info(f"已选择 Template Term: {label}")
        time.sleep(0.3)
        return True

    def _prompt_and_pick(
        self, candidates: list[tuple[str, object, str]], title: str
    ) -> bool:
        """交互式候选项选择。

        Args:
            candidates: [(display_text, element, persist_label)]
            title: 标题文本，为空时不输出
        """
        if title:
            self.console_print(title)
        for idx, (display_text, _, _) in enumerate(candidates, start=1):
            self.console_print(f"{idx}. {display_text}")

        sel = questionary.text(
            "请输入编号:",
            validate=lambda x: (
                x.isdigit() and 1 <= int(x) <= len(candidates) or "请输入有效编号"
            ),
        ).ask()
        if not sel or not sel.isdigit():
            return False
        picked_index = int(sel) - 1
        if picked_index < 0 or picked_index >= len(candidates):
            return False

        _, element, persist_label = candidates[picked_index]
        return self._click_option(element, persist_label, persist_choice=True)

    def _persist_choice(self, label: str) -> None:
        """将用户选择持久化到配置文件。"""
        if self.config is None:
            return
        try:
            settings = self.config.load_settings()
            self.config.save_settings(
                settings.model_copy(update={"template_term": label})
            )
        except Exception as e:
            logger.warning(f"持久化 Template Term 选择失败: {e}")

    @staticmethod
    def console_print(text: str) -> None:
        """输出到控制台（解耦 rich Console 实例）。"""
        from rich.console import Console

        Console().print(text)


__all__ = ["TemplateTermSelector", "TemplateTermNotConfiguredError"]
