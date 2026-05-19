import json
from domain.proposal_modal_service import ProposalModalService
from domain.selectors import MODAL_IFRAME_SELECTOR
from domain.wait_utils import wait_until

import os
import re
import time
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from loguru import logger
import questionary
from rich.panel import Panel
from difflib import SequenceMatcher

from exception_handler import exception_handler
from domain.date_picker import DatePicker


@dataclass(frozen=True)
class SendProposalsResult:
    """send_proposals 执行结果，用于区分「全部完成」与「提前退出」"""

    clicked_count: int
    completed_all: bool


class ProposalSender:
    """Proposal发送类，负责核心的RPA操作"""

    def __init__(self, browser, template_manager, console, config, config_store=None):
        self.browser = browser
        self.template_manager = template_manager
        self.console = console
        self.max_scrolls = 100
        self.max_consecutive_errors = 3
        self._stop_requested = False
        # 从配置中读取弹窗等待时间，默认 20 秒，用于应对 iframe 加载较慢的情况
        settings = config.load_settings()
        self._apply_settings(settings)
        self.modal_poll_interval = 0.2
        # 缓存每个 Partner Group 文本达到唯一匹配所需的最短输入长度
        self._partner_group_prefix_len_cache: dict[str, int] = {}
        # 缓存当前日期，保证同一批次内所有 proposal 使用一致的 T+1
        self._cached_today: date | None = None
        self.counted_attr = 'data-impact-rpa-counted'
        self.clicked_attr = 'data-impact-rpa-clicked'
        # TODO: 优化方向 - 在网页上判断联盟客是否已点击过，避免重复处理
        # 可以通过检查页面上是否有已发送的标记、按钮状态变化、或DOM结构变化来判断
        self.config = config

        self.modal_service = ProposalModalService(self)
        self._config_store = config_store
        # 初始化日期选择器
        self.date_picker = DatePicker(console)

        # 订阅配置热更新（如果启用）
        try:
            store = getattr(self.config, "store", None)
            if store is not None:
                store.subscribe("settings", lambda _k, payload: self.refresh_from_settings(payload))
        except Exception:
            pass

        # 滚动进度追踪（防卡顿机制）
        self._scroll_progress = {
            'last_element_count': 0,
            'no_progress_frames': 0,
            'last_scroll_position': 0,
            'stuck_frames': 0,
            'max_stuck_frames': 30,  # 连续30帧无进展认为卡顿
        }

    def request_stop(self) -> None:
        """请求在下一个安全检查点停止当前批次。"""
        self._stop_requested = True
        logger.info("收到停止请求，将在下一个安全检查点结束当前批次")

    def clear_stop_request(self) -> None:
        self._stop_requested = False

    def _reset_scroll_progress(self):
        """重置滚动进度追踪"""
        self._scroll_progress = {
            'last_element_count': 0,
            'no_progress_frames': 0,
            'last_scroll_position': 0,
            'stuck_frames': 0,
            'max_stuck_frames': 30,
        }

    def _check_scroll_progress(self, elements_count: int) -> dict:
        """检查滚动进度，检测是否卡顿
        
        Returns:
            dict: {
                'is_stuck': bool,  # 是否卡顿
                'progress_type': str,  # 'new_elements', 'scrolled', 'stuck'
                'details': str  # 详细信息
            }
        """
        try:
            # 获取当前滚动位置
            current_scroll = 0
            try:
                scroll_info = self.browser.tab.run_js("""
                    (function() {
                        // 查找主要滚动容器
                        function findMainScrollContainer() {
                            const containers = [];
                            const allElements = document.querySelectorAll('*');
                            
                            for (const el of allElements) {
                                const style = window.getComputedStyle(el);
                                if ((style.overflowY === 'auto' || style.overflowY === 'scroll' ||
                                     style.overflow === 'auto' || style.overflow === 'scroll') &&
                                    el.scrollHeight > el.clientHeight &&
                                    el.tagName.toLowerCase() !== 'html' &&
                                    el.tagName.toLowerCase() !== 'body') {
                                    containers.push(el);
                                }
                            }
                            
                            if (containers.length > 0) {
                                containers.sort((a, b) => 
                                    (b.scrollHeight - b.clientHeight) - (a.scrollHeight - a.clientHeight)
                                );
                                return containers[0];
                            }
                            return null;
                        }
                        
                        const container = findMainScrollContainer();
                        if (container) {
                            return {
                                type: 'container',
                                position: container.scrollTop,
                                maxScroll: container.scrollHeight - container.clientHeight,
                                tagName: container.tagName.toLowerCase(),
                                id: container.id || ''
                            };
                        }
                        
                        return {
                            type: 'window',
                            position: window.scrollY || window.pageYOffset,
                            maxScroll: document.body.scrollHeight - window.innerHeight
                        };
                    })()
                """)
                
                if scroll_info and isinstance(scroll_info, dict):
                    current_scroll = scroll_info.get('position', 0)
            except Exception as e:
                logger.debug(f"获取滚动位置失败: {e}")
                current_scroll = self._scroll_progress['last_scroll_position']
            
            # 检查是否有新元素
            has_new_elements = elements_count > self._scroll_progress['last_element_count']
            
            # 检查是否有实际滚动
            has_scrolled = abs(current_scroll - self._scroll_progress['last_scroll_position']) > 10
            
            # 更新进度
            if has_new_elements:
                self._scroll_progress['no_progress_frames'] = 0
                self._scroll_progress['stuck_frames'] = 0
                self._scroll_progress['last_element_count'] = elements_count
                self._scroll_progress['last_scroll_position'] = current_scroll
                
                return {
                    'is_stuck': False,
                    'progress_type': 'new_elements',
                    'details': f'检测到新元素 ({elements_count} 个)'
                }
            
            if has_scrolled:
                self._scroll_progress['stuck_frames'] = 0
                self._scroll_progress['last_scroll_position'] = current_scroll
                # 注意：不重置 no_progress_frames，因为可能是虚拟列表
                
                return {
                    'is_stuck': False,
                    'progress_type': 'scrolled',
                    'details': f'已滚动到 {current_scroll:.0f}px'
                }
            
            # 既没有新元素，也没有滚动
            self._scroll_progress['no_progress_frames'] += 1
            self._scroll_progress['stuck_frames'] += 1
            
            is_stuck = self._scroll_progress['stuck_frames'] >= self._scroll_progress['max_stuck_frames']
            
            return {
                'is_stuck': is_stuck,
                'progress_type': 'stuck',
                'details': f'连续 {self._scroll_progress["stuck_frames"]} 帧无进展'
            }
            
        except Exception as e:
            logger.warning(f"检查滚动进度失败: {e}")
            return {
                'is_stuck': False,
                'progress_type': 'error',
                'details': str(e)
            }

    def _apply_settings(self, settings: dict) -> None:
        """将 settings 应用到实例字段（支持热刷新）。"""
        self.modal_wait_timeout = float(settings.get("modal_wait", 20.0))
        self.scroll_delay = float(settings.get("scroll_delay", 1.0))
        self.template_term = (settings.get("template_term") or "Commission Tier Terms").strip()
        self.input_partner_groups_tag = bool(settings.get("input_partner_groups_tag", True))
        self.partner_groups_debug_logging = bool(settings.get("partner_groups_debug_logging", False))
        self.dry_run = bool(settings.get("dry_run", False))
        default_pg: dict = {"mode": "ui", "api": {}, "id_by_name": {}}
        user_pg = settings.get("partner_groups")
        if isinstance(user_pg, dict):
            merged = {**default_pg, **user_pg}
            api_u = user_pg.get("api")
            if isinstance(api_u, dict):
                merged["api"] = {**(default_pg.get("api") or {}), **api_u}
            id_u = user_pg.get("id_by_name")
            if isinstance(id_u, dict):
                merged["id_by_name"] = {**(default_pg.get("id_by_name") or {}), **id_u}
            self.partner_groups = merged
        else:
            self.partner_groups = dict(default_pg)

    def refresh_from_settings(self, settings: dict) -> None:
        """配置变更时刷新运行期字段（无需重启进程）。"""
        try:
            self._apply_settings(settings or {})
        except Exception:
            pass

    def _maybe_refresh_settings(self) -> None:
        """发送前兜底刷新一次，避免 watcher 轮询间隔导致的短暂不一致。"""
        try:
            store = getattr(self.config, "store", None)
            if store is not None:
                self.refresh_from_settings(store.get_settings())
        except Exception:
            pass

    def _find_send_proposal_buttons(self) -> list:
        """
        在列表页查找可点击的 Send Proposal 按钮（多策略兜底）。

        说明：Impact 的 DOM/测试 id 可能变动，单一 selector 容易导致一直"找不到按钮 → 滚动"。
        """
        results: list = []
        seen: set[int] = set()

        def _add(ele) -> None:
            if not ele:
                return
            key = id(ele)
            if key in seen:
                return
            seen.add(key)
            results.append(ele)

        # 策略1：优先按 uicl-button testid（历史实现）
        try:
            btns = self.browser.find_elements('css:button[data-testid="uicl-button"]', timeout=1.5)
            for b in btns or []:
                try:
                    if 'Send Proposal' in ((b.text or '').strip()):
                        _add(b)
                except Exception:
                    continue
        except Exception:
            pass

        # 策略2：直接扫描所有 button 文本
        if not results:
            try:
                btns = self.browser.find_elements('tag:button', timeout=1.5)
                for b in btns or []:
                    try:
                        if 'Send Proposal' in ((b.text or '').strip()):
                            _add(b)
                    except Exception:
                        continue
            except Exception:
                pass

        # 策略3：按文本定位到节点后向上找 button/role=button
        if not results:
            try:
                nodes = self.browser.find_elements('text:Send Proposal', timeout=1.5)
                for n in nodes or []:
                    cur = n
                    for _ in range(8):
                        if not cur:
                            break
                        try:
                            tag = getattr(cur, 'tag', None)
                            if isinstance(tag, str) and tag.lower() == 'button':
                                _add(cur)
                                break
                        except Exception:
                            pass
                        try:
                            if (cur.attr('role') or '').strip().lower() == 'button':
                                _add(cur)
                                break
                        except Exception:
                            pass
                        try:
                            cur = cur.parent()
                        except Exception:
                            break
            except Exception:
                pass

        return results
    
    def send_proposals(
        self,
        max_count: int = 10,
        template_content: str | None = None,
        start_index: int = 1,
        skip_ready_prompt: bool = False,
    ) -> SendProposalsResult:
        """
        循环点击页面上所有的 Send Proposal 按钮
        
        Args:
            max_count: 最大发送数量
            template_content: 留言模板内容，None 时使用当前激活模板
            start_index: 起始序号（从 1 开始）。例如 3 表示跳过前 2 个可发送目标
            
        Returns:
            SendProposalsResult(clicked_count, completed_all)。
            completed_all 仅当达到 max_count 时为 True；重连失败等会 raise，不返回。
        """
        self._maybe_refresh_settings()
        self.clear_stop_request()
        # 等待用户操作完成
        if not skip_ready_prompt:
            self.console.print(Panel(
                "[bold]请在浏览器中完成以下操作：[/bold]\n"
                "1. 导航到目标页面\n"
                "2. 登录账号（如果需要）\n"
                "3. 完成人机验证（如果出现）\n"
                "4. 确保页面已正常加载",
                title="[cyan]提示[/cyan]",
                border_style="cyan"
            ))
            questionary.press_any_key_to_continue("操作完成后，按任意键继续...").ask()
        
        if start_index < 1:
            logger.warning(f"收到无效 start_index={start_index}，已回退为 1")
            start_index = 1
        skip_remaining = start_index - 1
        skipped_before_start = 0

        logger.info(f"开始发送 Send Proposal，目标数量: {max_count}，起始序号: {start_index}")

        # 缓存当前日期，保证同一批次内 T+1 一致
        self._cached_today = date.today()
        logger.info(f"本批次使用日期: T={self._cached_today.isoformat()}, T+1={self._cached_today + timedelta(days=1)}")

        if template_content is None:
            template_content = self.template_manager.get_active_template()
        
        clicked_count = 0             # 已成功点击的 Send Proposal 按钮数量
        total_scrolls = 0             # 已执行的页面向下滚动次数（用于查找新按钮）
        consecutive_errors = 0        # 连续发生的异常次数（如超限则尝试重连）
        pending_batch_buttons = 0     # 尚未完成点击的按钮批次数，控制批量操作时逻辑
        total_detected_buttons = 0    # 累计检测到的所有 Send Proposal 按钮总数
        empty_scrolls = 0             # 连续未检测到新按钮的滚动次数（可能已无可点目标）
        
        # 根据目标数量动态调整最大滚动次数（至少为目标数量的3倍，但不超过固定上限）
        # 这样可以确保有足够的滚动次数来找到目标数量的按钮
        effective_max_scrolls = min(max(max_count * 3, 200), self.max_scrolls * 5)
        
        if self.dry_run:
            self.console.print(Panel(
                "[bold yellow]⚠️  开发测试模式 (DRY-RUN)[/bold yellow]\n"
                "会点击列表页的 Send Proposal 按钮并打开弹窗\n"
                "会填写弹窗表单，但[bold]不会点击弹窗中的提交按钮[/bold]\n"
                "如需正式运行，请在 config/settings.json 中设置 \"dry_run\": false",
                title="[yellow]测试模式[/yellow]",
                border_style="yellow"
            ))
            logger.info("[DRY-RUN] 开发测试模式已启用，不会点击弹窗中的提交按钮")
        
        self.console.print(
            f"\n[bold cyan]开始循环点击 Send Proposal 按钮 "
            f"(目标: {max_count} 个，起始序号: {start_index}，最大滚动: {effective_max_scrolls} 次)...[/bold cyan]"
        )
        if skip_remaining > 0:
            self.console.print(f"[dim]将先跳过前 {skip_remaining} 个可发送目标[/dim]")

        # 重置滚动进度追踪
        self._reset_scroll_progress()

        # 循环条件：未达到目标数量 且 未超过最大滚动次数（安全限制）
        while clicked_count < max_count and total_scrolls < effective_max_scrolls:
            if self._stop_requested:
                self.console.print("[yellow]检测到停止请求，结束当前发送任务[/yellow]")
                logger.info(f"发送任务被请求停止，已发送 {clicked_count}/{max_count} 个")
                break
            # 检查是否需要重连
            if consecutive_errors >= self.max_consecutive_errors:
                self.console.print("[yellow]连续多次错误，尝试重新连接浏览器...[/yellow]")
                if self.browser.reconnect():
                    consecutive_errors = 0
                    time.sleep(1)
                else:
                    err = Exception("浏览器重连失败")
                    exception_handler.log_exception(
                        err,
                        context={
                            "consecutive_errors": consecutive_errors,
                            "total_scrolls": total_scrolls,
                            "clicked_count": clicked_count
                        },
                        send_notification=False,
                    )
                    self.console.print("[red]重连失败，停止执行[/red]")
                    raise RuntimeError("浏览器重连失败") from err
            
            try:
                # 查找当前可见的所有 Send Proposal 按钮（多策略兜底）
                buttons = self._find_send_proposal_buttons()
                
                if buttons is None:
                    consecutive_errors += 1
                    if self.browser.reconnect():
                        consecutive_errors = 0
                        time.sleep(1)
                    continue
                
                # _find_send_proposal_buttons 已过滤为目标按钮，这里直接使用
                send_proposal_buttons = [b for b in (buttons or []) if b]
                
                available_buttons = []
                newly_counted = 0
                raw_buttons_count = len(send_proposal_buttons)
                skipped_clicked_count = 0
                already_counted_count = 0
                mark_count_failed = 0
                for btn in send_proposal_buttons:
                    if btn.attr(self.clicked_attr) == 'true':
                        skipped_clicked_count += 1
                        continue
                    if btn.attr(self.counted_attr) != 'true':
                        if self._mark_button_state(btn, self.counted_attr):
                            pending_batch_buttons += 1
                            total_detected_buttons += 1
                            newly_counted += 1
                        else:
                            mark_count_failed += 1
                    else:
                        already_counted_count += 1
                    available_buttons.append(btn)
                
                if newly_counted > 0:
                    empty_scrolls = 0
                    self.console.print(
                        f"[dim]检测到新按钮 {newly_counted} 个，当前批次待发送 {pending_batch_buttons} 个（累计 {total_detected_buttons} 个）[/dim]"
                    )
                    logger.debug(
                        f"新增 {newly_counted} 个 Send Proposal 按钮，当前批次待发送 {pending_batch_buttons} 个"
                    )
                
                if not available_buttons:
                    if pending_batch_buttons <= 0:
                        if raw_buttons_count == 0:
                            logger.debug(
                                "当前页面未检测到任何 Send Proposal 按钮，准备滚动加载更多。"
                            )
                        elif skipped_clicked_count == raw_buttons_count:
                            logger.debug(
                                f"当前页面检测到 {raw_buttons_count} 个 Send Proposal 按钮，"
                                f"但全部已标记为已点击({self.clicked_attr}=true)，准备滚动加载更多。"
                            )
                        else:
                            logger.debug(
                                f"当前页面检测到 {raw_buttons_count} 个 Send Proposal 按钮，"
                                f"可用按钮为 0（已点击标记: {skipped_clicked_count}，"
                                f"已计数未点击: {already_counted_count}，计数标记失败: {mark_count_failed}），"
                                "准备滚动加载更多。"
                            )
                        empty_scrolls += 1
                        
                        # 检查滚动进度（防卡顿机制）
                        scroll_check = self._check_scroll_progress(raw_buttons_count)
                        if scroll_check['is_stuck']:
                            logger.warning(
                                f"检测到滚动卡顿：{scroll_check['details']}，"
                                f"提前退出（已发送 {clicked_count}/{max_count}）"
                            )
                            self.console.print(
                                f"\n[yellow]滚动连续无进展（{scroll_check['details']}），提前结束。"
                                f"已发送 {clicked_count}/{max_count} 个。[/yellow]\n"
                            )
                            break
                        
                        # 连续多次空滚动仍未发现新按钮，则提前退出，避免看起来像"卡死/报错"
                        max_empty_scrolls = max(20, max_count * 2)
                        if empty_scrolls >= max_empty_scrolls:
                            logger.info(
                                f"连续空滚动 {empty_scrolls} 次仍未发现新按钮，提前退出（已发送 {clicked_count}/{max_count}）"
                            )
                            self.console.print(
                                f"\n[yellow]未发现更多 Send Proposal 按钮（连续滚动 {empty_scrolls} 次无新增），提前结束。"
                                f"已发送 {clicked_count}/{max_count} 个。[/yellow]\n"
                            )
                            break
                        logger.debug(
                            f"执行第 {total_scrolls + 1} 次滚动（空滚动累计: {empty_scrolls}/{max_empty_scrolls}，"
                            f"已发送: {clicked_count}/{max_count}，累计检测到按钮: {total_detected_buttons}，"
                            f"滚动状态: {scroll_check['details']}）。"
                        )
                        if not self.browser.scroll_down(500):
                            consecutive_errors += 1
                            logger.warning(
                                f"滚动失败，连续错误计数 +1 -> {consecutive_errors} "
                                f"(已发送: {clicked_count}/{max_count})"
                            )
                            continue
                        time.sleep(self.scroll_delay)
                        total_scrolls += 1
                        continue
                    else:
                        logger.debug(
                            f"存在待发送计数({pending_batch_buttons})但当前未找到可用按钮；"
                            f"本轮检测到按钮总数 {raw_buttons_count}（已点击标记: {skipped_clicked_count}），"
                            "重置待发送计数以避免阻塞。"
                        )
                        pending_batch_buttons = 0
                        continue
                
                send_proposal_buttons = available_buttons
                
                # 重置连续错误计数
                consecutive_errors = 0
                
                # 遍历当前可见的按钮并点击
                should_scroll_after_batch = False
                for btn in send_proposal_buttons:
                    if self._stop_requested:
                        self.console.print("[yellow]检测到停止请求，结束当前发送任务[/yellow]")
                        logger.info(f"发送任务在批次内被请求停止，已发送 {clicked_count}/{max_count} 个")
                        return SendProposalsResult(
                            clicked_count=clicked_count,
                            completed_all=False,
                        )
                    if clicked_count >= max_count:
                        logger.info(f"已达到目标数量 {max_count}，停止发送")
                        self.console.print(f"\n[bold green]✓ 已达到目标数量 {max_count}，停止发送[/bold green]")
                        self.console.print(f"\n[bold cyan]===== 完成！共发送了 {clicked_count} 个 Send Proposal =====[/bold cyan]")
                        return SendProposalsResult(clicked_count=clicked_count, completed_all=True)

                    if skip_remaining > 0:
                        if self._mark_button_state(btn, self.clicked_attr):
                            skip_remaining -= 1
                            skipped_before_start += 1
                            if pending_batch_buttons > 0:
                                pending_batch_buttons = max(pending_batch_buttons - 1, 0)
                            if skip_remaining == 0:
                                logger.info(f"已完成起始偏移，累计跳过 {skipped_before_start} 个按钮，开始正式发送")
                                self.console.print(
                                    f"[dim]已跳过前 {skipped_before_start} 个目标，开始正式发送[/dim]"
                                )
                            if pending_batch_buttons == 0:
                                should_scroll_after_batch = True
                        else:
                            logger.warning("起始偏移阶段标记按钮失败，稍后重试该按钮")
                        continue
                    
                    try:
                        selected_tab = self._get_selected_tab_value(btn)
                        
                        parent = btn.parent()
                        for retry_idx in range(10):
                            if parent:
                                try:
                                    self.browser.scroll_to_element(parent)
                                    time.sleep(0.2)
                                    parent.hover()
                                    time.sleep(0.3)
                                    
                                    clicked = False
                                    try:
                                        btn.click(by_js=True)
                                        clicked = True
                                    except Exception as click_err:
                                        error_msg = str(click_err).lower()
                                        if 'norect' in error_msg or '没有位置' in error_msg:
                                            try:
                                                parent.click(by_js=True)
                                                clicked = True
                                            except Exception as parent_click_err:
                                                logger.warning(f"点击父元素失败: {parent_click_err}")
                                                pass
                                        if not clicked:
                                            raise click_err
                                    
                                    if not clicked:
                                        raise Exception("点击按钮失败")
                                    
                                    # 先处理弹窗，只有成功时才标记按钮和增加计数
                                    time.sleep(0.5)
                                    modal_success = self._handle_proposal_modal(selected_tab, template_content)
                                    
                                    if modal_success:
                                        # 弹窗处理成功，增加计数并标记按钮
                                        clicked_count += 1
                                        if self.dry_run:
                                            logger.info(f"[DRY-RUN] [{clicked_count}/{max_count}] 已处理弹窗（未提交）(类别: {selected_tab})")
                                            self.console.print(f"[cyan]⚡ [DRY-RUN] [{clicked_count}/{max_count}][/cyan] 已处理弹窗（未提交）[dim](类别: {selected_tab})[/dim]")
                                        else:
                                            logger.info(f"[{clicked_count}/{max_count}] 已点击 Send Proposal 按钮 (类别: {selected_tab})")
                                            self.console.print(f"[green]✓ [{clicked_count}/{max_count}][/green] 已点击 Send Proposal 按钮 [dim](类别: {selected_tab})[/dim]")
                                        self._mark_button_state(btn, self.clicked_attr)
                                        if pending_batch_buttons > 0:
                                            pending_batch_buttons = max(pending_batch_buttons - 1, 0)
                                        if pending_batch_buttons == 0:
                                            should_scroll_after_batch = True
                                    else:
                                        # 弹窗处理失败，记录警告但不标记按钮
                                        logger.warning(f"弹窗处理失败，跳过此按钮 (类别: {selected_tab})")
                                        self.console.print(f"[yellow]⚠ 弹窗处理失败，跳过此按钮 (类别: {selected_tab})[/yellow]")
                                        # 不增加计数，不标记按钮，继续处理下一个按钮
                                    
                                    break
                                except Exception as e:
                                    error_msg = str(e).lower()
                                    if 'disconnect' in error_msg or 'context' in error_msg or 'target closed' in error_msg:
                                        raise
                                    if retry_idx < 9:
                                        parent = parent.parent()
                                    else:
                                        raise
                            else:
                                break
                    except Exception as e:
                        error_msg = str(e).lower()
                        if 'disconnect' in error_msg or 'context' in error_msg or 'target closed' in error_msg or 'no such' in error_msg:
                            logger.warning(f"页面可能已刷新: {e}")
                            self.console.print("[yellow]⚠ 页面可能已刷新，尝试重连...[/yellow]")
                            consecutive_errors += 1
                            break
                        else:
                            logger.exception(
                                f"点击按钮时出错（已发送: {clicked_count}/{max_count}, "
                                f"滚动次数: {total_scrolls}, 待发送计数: {pending_batch_buttons}）"
                            )
                            self.console.print(f"[red]✗ 点击按钮时出错: {e}[/red]")
                        continue
                
                if clicked_count >= max_count:
                    break
                
                if should_scroll_after_batch:
                    # 检查滚动进度（防卡顿机制）
                    scroll_check = self._check_scroll_progress(len(send_proposal_buttons))
                    if scroll_check['is_stuck']:
                        logger.warning(
                            f"批次后滚动检测到卡顿：{scroll_check['details']}，"
                            f"提前退出（已发送 {clicked_count}/{max_count}）"
                        )
                        self.console.print(
                            f"\n[yellow]滚动连续无进展（{scroll_check['details']}），提前结束。"
                            f"已发送 {clicked_count}/{max_count} 个。[/yellow]\n"
                        )
                        break
                    
                    if not self.browser.scroll_down(500):
                        consecutive_errors += 1
                        continue
                    time.sleep(self.scroll_delay)
                    total_scrolls += 1
                    self.console.print(
                        f"[dim]当前批次已发送完，滚动第 {total_scrolls} 次加载更多按钮[/dim]"
                    )
                    continue

                if pending_batch_buttons > 0:
                    # 仍有待发送的已计数按钮，继续下一轮尝试，不滚动
                    continue

                # 检查滚动进度（防卡顿机制）
                scroll_check = self._check_scroll_progress(len(send_proposal_buttons))
                if scroll_check['is_stuck']:
                    logger.warning(
                        f"常规滚动检测到卡顿：{scroll_check['details']}，"
                        f"提前退出（已发送 {clicked_count}/{max_count}）"
                    )
                    self.console.print(
                        f"\n[yellow]滚动连续无进展（{scroll_check['details']}），提前结束。"
                        f"已发送 {clicked_count}/{max_count} 个。[/yellow]\n"
                    )
                    break

                if not self.browser.scroll_down(500):
                    consecutive_errors += 1
                    continue
                time.sleep(self.scroll_delay)
                total_scrolls += 1
                self.console.print(f"[dim]滚动第 {total_scrolls} 次，已发送 {clicked_count}/{max_count} 个[/dim]")
                
            except Exception as e:
                error_msg = str(e).lower()
                if 'disconnect' in error_msg or 'context' in error_msg or 'target closed' in error_msg:
                    logger.warning(f"检测到页面断开: {e}")
                    consecutive_errors += 1
                else:
                    logger.exception(
                        f"发送主循环异常（已发送: {clicked_count}/{max_count}, "
                        f"滚动次数: {total_scrolls}, 连续错误: {consecutive_errors}, "
                        f"空滚动: {empty_scrolls}, 待发送计数: {pending_batch_buttons}）"
                    )
                    if 'template_term_not_found' in error_msg:
                        raise
                    consecutive_errors += 1
        
        logger.info(f"发送完成，共发送 {clicked_count} 个 Send Proposal")
        self.console.print(f"\n[bold cyan]===== 完成！共发送了 {clicked_count} 个 Send Proposal =====[/bold cyan]")
        return SendProposalsResult(
            clicked_count=clicked_count,
            completed_all=(clicked_count >= max_count),
        )

    def send_proposal_by_table_row(
        self,
        row_index: int,
        template_content: str | None = None,
        skip_names: set[str] | None = None,
    ) -> tuple[bool, str | None, str | None, bool]:
        """
        在 Creator Search / Partner Marketplace 中点击指定行，再点击出现的 Send Proposal 按钮，
        弹窗后的处理与 send_proposals 中点击 Send Proposal 之后一致（_handle_proposal_modal）。

        Args:
            row_index: 表格行号，从 1 开始。
            template_content: 留言模板内容，None 时使用当前激活模板。
            skip_names: 需要跳过的 Creator 名称集合（已发送过的）。

        Returns:
            (success, name, psi, skipped): 
            - 成功返回 (True, name, psi_id, False)
            - 跳过返回 (False, name, psi_id, True)
            - 失败返回 (False, name, psi_id, False)
        """
        if template_content is None:
            template_content = self.template_manager.get_active_template()
        psi_id = None
        creator_name = None
        try:
            # 两种布局，在 Creator Search 和 Partner Marketplace 中一致：
            # 1) 卡片/网格视图：css:.iui-grid > .iui-card:nth-child(N) .creator-card
            # 2) 表格视图屏底：css:div.table-body > div:nth-child(N)
            row_el = self.browser.find_element(
                f"css:.iui-grid > .iui-card:nth-child({row_index}) .creator-card",
                timeout=3,
            )
            if not row_el:
                row_el = self.browser.find_element(
                    f"css:div.table-body > div:nth-child({row_index})",
                    timeout=3,
                )

            if not row_el:
                logger.warning(f"未找到表格行: row_index={row_index}")
                self.console.print(f"[red]未找到表格行 (第 {row_index} 行)[/red]")
                return False, None, None, False

            logger.debug(f"第 {row_index} 行已定位")

            self.browser.scroll_to_element(row_el)
            time.sleep(0.2)
            row_el.click(by_js=True)
            time.sleep(0.5)
            
            # 提取 Creator 名称和 psi ID
            creator_name = self._extract_creator_name(row_el)
            psi_id = self._extract_creator_psi()
            
            # 检查是否需要跳过（已发送过）
            if skip_names and creator_name and creator_name in skip_names:
                logger.info(f"第 {row_index} 行 [{creator_name}] 已发送过，跳过")
                return False, creator_name, psi_id, True  # 跳过
            
            # 点击行后出现的 Send Proposal 按钮：优先按文本查找并点击
            send_btn = self.browser.find_element("text:Send Proposal", timeout=10)
            if not send_btn:
                buttons = self.browser.find_elements('css:button[data-testid="uicl-button"]')
                for btn in buttons or []:
                    if not btn:
                        continue
                    if 'Send Proposal' in (btn.text or ''):
                        send_btn = btn
                        break
            if not send_btn:
                logger.warning("点击行后未找到 Send Proposal 按钮")
                self.console.print("[red]点击行后未找到 Send Proposal 按钮[/red]")
                return False, creator_name, psi_id, False
            parent = send_btn.parent()
            if parent:
                self.browser.scroll_to_element(parent)
                time.sleep(0.2)
            send_btn.click(by_js=True)
            time.sleep(0.5)
            modal_success = self._handle_proposal_modal(selected_tab=None, template_content=template_content or "")
            
            # 检测发送成功消息
            if modal_success:
                success_confirmed = self._wait_for_success_message()
                if success_confirmed:
                    logger.info(f"第 {row_index} 行 Creator [{creator_name}] (psi={psi_id}) 发送成功")
                    return True, creator_name, psi_id, False
                else:
                    logger.warning(f"第 {row_index} 行未检测到成功消息")
                    return True, creator_name, psi_id, False  # 弹窗处理成功但未检测到消息
            return False, creator_name, psi_id, False
        except Exception as e:
            error_msg = str(e).lower()
            if 'disconnect' in error_msg or 'context' in error_msg or 'target closed' in error_msg:
                raise
            logger.error(f"按表格行发送失败: {e}")
            self.console.print(f"[red]按表格行发送失败: {e}[/red]")
            return False, creator_name, psi_id, False

    def _extract_creator_name(self, row_el=None) -> str | None:
        """从当前页面或表格行提取 Creator 的名称"""
        try:
            # 方法1：从表格行本身提取（优先）
            if row_el:
                # 查找行内的链接或标题文本
                link = row_el.ele('tag:a', timeout=0.2)
                if link:
                    name = (link.text or '').strip()
                    # 过滤掉太短或不像名字的文本
                    if name and len(name) > 1 and not name.startswith('http'):
                        logger.debug(f"从表格行提取到 Creator 名称: {name}")
                        return name
                # 查找行内第一个有意义的文本
                for sel in ['css:[class*="name"]', 'css:span', 'css:div']:
                    el = row_el.ele(sel, timeout=0.1)
                    if el:
                        name = (el.text or '').strip()
                        if name and len(name) > 2 and len(name) < 100:
                            logger.debug(f"从表格行提取到 Creator 名称: {name}")
                            return name
            
            # 方法2：等待侧边栏加载后从标题提取
            time.sleep(0.3)  # 等待侧边栏更新
            selectors = [
                'css:[class*="slideout"] h1',
                'css:[class*="slideout"] h2',
                'css:[class*="detail"] h1',
                'css:[class*="detail"] h2',
                'css:[class*="panel"] h1',
                'css:[class*="panel"] h2',
                'css:[class*="creator-name"]',
                'css:[class*="partner-name"]',
                'css:[class*="profile-name"]',
            ]
            for sel in selectors:
                el = self.browser.find_element(sel, timeout=0.3)
                if el:
                    name = (el.text or '').strip()
                    if name and len(name) > 1:
                        logger.debug(f"提取到 Creator 名称: {name}")
                        return name
            
            # 方法3：从 Send Proposal 按钮附近查找
            send_btn = self.browser.find_element("text:Send Proposal", timeout=0.3)
            if send_btn:
                parent = send_btn.parent()
                for _ in range(5):
                    if parent:
                        for tag in ['h1', 'h2', 'h3']:
                            header = parent.ele(f'tag:{tag}', timeout=0.1)
                            if header:
                                name = (header.text or '').strip()
                                if name and len(name) > 1:
                                    logger.debug(f"提取到 Creator 名称: {name}")
                                    return name
                        parent = parent.parent()
                        
        except Exception as e:
            logger.debug(f"提取 Creator 名称失败: {e}")
        return None

    def _extract_creator_psi(self) -> str | None:
        """从当前页面提取 Creator 的 psi ID"""
        try:
            # 尝试从 URL 或页面元素中提取 psi
            # 方法1：从侧边栏的链接中提取
            slideout = self.browser.find_element('css:[class*="slideout"], [class*="detail"], [class*="panel"]', timeout=1)
            if slideout:
                # 查找包含 psi 的链接或属性
                links = slideout.eles('tag:a', timeout=0.5)
                for link in links or []:
                    href = link.attr('href') or ''
                    if 'psi=' in href:
                        import re
                        match = re.search(r'psi=([a-f0-9-]+)', href)
                        if match:
                            return match.group(1)
            
            # 方法2：从 iframe src 中提取
            iframe = self.browser.find_element('css:iframe[src*="psi="]', timeout=0.5)
            if iframe:
                src = iframe.attr('src') or ''
                import re
                match = re.search(r'psi=([a-f0-9-]+)', src)
                if match:
                    return match.group(1)
            
            # 方法3：从页面上的隐藏元素或 data 属性提取
            psi_el = self.browser.find_element('css:[data-psi], [data-partner-id]', timeout=0.5)
            if psi_el:
                return psi_el.attr('data-psi') or psi_el.attr('data-partner-id')
                
        except Exception as e:
            logger.debug(f"提取 psi 失败: {e}")
        return None

    def _wait_for_success_message(self, timeout: float = 5.0) -> bool:
        """等待 'Proposal sent successfully.' 成功消息出现"""
        deadline = time.time() + timeout
        while time.time() < deadline:
            try:
                success_el = self.browser.find_element('text:Proposal sent successfully', timeout=0.5)
                if success_el:
                    logger.info("检测到发送成功消息")
                    time.sleep(0.5)  # 等待消息显示完成
                    return True
            except Exception:
                pass
            time.sleep(0.3)
        return False

    def send_proposals_creator_search(
        self,
        max_count: int = 10,
        start_row: int = 1,
        template_content: str | None = None,
    ) -> SendProposalsResult:
        """
        Creator Search 批量发送：从指定行开始，依次发送 Proposal。
        用 name 来区分已发送的 Creator，避免重复发送。
        
        Args:
            max_count: 最大发送数量
            start_row: 起始行号（从 1 开始）
            template_content: 留言模板内容
            
        Returns:
            SendProposalsResult: 发送结果
        """
        self._maybe_refresh_settings()
        self.clear_stop_request()
        if template_content is None:
            template_content = self.template_manager.get_active_template()
        
        # 加载已发送的 name 列表
        sent_names = self._load_sent_names()
        if sent_names:
            self.console.print(f"[dim]已加载 {len(sent_names)} 个已发送的 Creator 记录[/dim]")
        
        sent_count = 0
        sent_records: list[dict] = []  # 记录已发送的 Creator
        skipped_count = 0  # 跳过的重复 Creator 数量
        current_row = start_row
        consecutive_errors = 0
        max_consecutive_errors = 3
        
        self.console.print(f"\n[bold cyan]开始 Creator Search 批量发送 (目标: {max_count} 个，起始行: {start_row})...[/bold cyan]")

        # 缓存当前日期，保证同一批次内 T+1 一致
        self._cached_today = date.today()
        logger.info(f"本批次使用日期: T={self._cached_today.isoformat()}, T+1={self._cached_today + timedelta(days=1)}")

        while sent_count < max_count:
            if self._stop_requested:
                self.console.print("[yellow]检测到停止请求，结束当前发送任务[/yellow]")
                logger.info(f"Creator Search 任务被请求停止，已发送 {sent_count}/{max_count} 个")
                break
            if consecutive_errors >= max_consecutive_errors:
                self.console.print(f"[red]连续 {max_consecutive_errors} 次错误，停止发送[/red]")
                break
            
            self.console.print(f"\n[dim]正在处理第 {current_row} 行...[/dim]")
            
            try:
                success, creator_name, psi_id, was_skipped = self.send_proposal_by_table_row(
                    current_row, template_content, skip_names=sent_names
                )
                
                # 检查是否被跳过（已发送过）
                if was_skipped:
                    self.console.print(f"[yellow][SKIP] 第 {current_row} 行 [{creator_name}] 已发送过，跳过[/yellow]")
                    skipped_count += 1
                    current_row += 1
                    self._close_creator_slideout()
                    time.sleep(0.3)
                    continue
                
                if success:
                    sent_count += 1
                    consecutive_errors = 0
                    record = {
                        'row': current_row,
                        'name': creator_name,
                        'psi': psi_id,
                        'status': 'success',
                        'timestamp': datetime.now().isoformat(),
                    }
                    sent_records.append(record)
                    # 添加到已发送列表
                    if creator_name:
                        sent_names.add(creator_name)
                    
                    self.console.print(f"[green][OK] [{sent_count}/{max_count}] 第 {current_row} 行 [{creator_name or '未知'}] 发送成功[/green]")
                    logger.info(f"发送成功: row={current_row}, name={creator_name}, psi={psi_id}")
                    
                    # 关闭侧边栏（如果有的话），准备下一个
                    self._close_creator_slideout()
                else:
                    consecutive_errors += 1
                    self.console.print(f"[yellow][SKIP] 第 {current_row} 行 [{creator_name or '未知'}] 发送失败，跳过[/yellow]")
                
                current_row += 1
                time.sleep(0.5)  # 短暂等待页面稳定
                
            except Exception as e:
                error_msg = str(e).lower()
                if 'disconnect' in error_msg or 'context' in error_msg or 'target closed' in error_msg:
                    raise
                consecutive_errors += 1
                logger.error(f"处理第 {current_row} 行时出错: {e}")
                self.console.print(f"[red][ERR] 第 {current_row} 行出错: {e}[/red]")
                current_row += 1
        
        # 保存发送记录
        self._save_sent_records(sent_records)
        
        if skipped_count > 0:
            self.console.print(f"[dim]跳过了 {skipped_count} 个已发送的 Creator[/dim]")
        
        self.console.print(f"\n[bold cyan]===== 完成！共发送了 {sent_count} 个 Proposal =====[/bold cyan]")
        logger.info(f"Creator Search 批量发送完成，共发送 {sent_count} 个")
        
        return SendProposalsResult(
            clicked_count=sent_count,
            completed_all=(sent_count >= max_count),
        )

    def _close_creator_slideout(self):
        """关闭 Creator 详情侧边栏"""
        try:
            # 尝试点击关闭按钮
            close_btn = self.browser.find_element('css:button[aria-label="Close"], button[class*="close"], [class*="slideout"] button[class*="close"]', timeout=0.5)
            if close_btn:
                close_btn.click(by_js=True)
                time.sleep(0.3)
                return
            
            # 尝试按 ESC
            try:
                self.browser.tab.actions.key_down('Escape').key_up('Escape').perform()
                time.sleep(0.3)
            except Exception:
                pass
        except Exception as e:
            logger.debug(f"关闭侧边栏失败: {e}")

    def _save_sent_records(self, records: list[dict]):
        """保存发送记录到文件"""
        if not records:
            return
        try:
            import json
            log_dir = os.path.join(os.path.dirname(__file__), 'logs')
            os.makedirs(log_dir, exist_ok=True)
            
            filename = f"creator_search_sent_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
            filepath = os.path.join(log_dir, filename)
            
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(records, f, ensure_ascii=False, indent=2)
            
            logger.info(f"发送记录已保存到: {filepath}")
            self.console.print(f"[dim]发送记录已保存到: {filename}[/dim]")
        except Exception as e:
            logger.warning(f"保存发送记录失败: {e}")

    def _load_sent_names(self) -> set[str]:
        """加载所有已发送的 Creator 名称（从 logs 目录中的所有记录文件）"""
        sent_names: set[str] = set()
        try:
            import json
            import glob
            log_dir = os.path.join(os.path.dirname(__file__), 'logs')
            if not os.path.exists(log_dir):
                return sent_names
            
            # 读取所有 creator_search_sent_*.json 文件
            pattern = os.path.join(log_dir, 'creator_search_sent_*.json')
            for filepath in glob.glob(pattern):
                try:
                    with open(filepath, 'r', encoding='utf-8') as f:
                        records = json.load(f)
                        for record in records:
                            name = record.get('name')
                            if name:
                                sent_names.add(name)
                except Exception as e:
                    logger.debug(f"读取记录文件失败 {filepath}: {e}")
            
            logger.debug(f"已加载 {len(sent_names)} 个已发送的 Creator 名称")
        except Exception as e:
            logger.warning(f"加载已发送记录失败: {e}")
        return sent_names

    def _get_selected_tab_value(self, btn) -> str | None:
        """获取按钮所在行的 selected-tab 值"""
        try:
            parent = btn.parent()
            for _ in range(20):
                if parent:
                    selected_tab_ele = self.browser.find_element('css:.selected-tab', timeout=0.1, parent=parent)
                    if selected_tab_ele:
                        return selected_tab_ele.text.strip()
                    parent = parent.parent()
                else:
                    break
            
            # 备用方案
            selected_tab_ele = self.browser.find_element('css:.selected-tab', timeout=0.5)
            if selected_tab_ele:
                return selected_tab_ele.text.strip()
        except Exception as e:
            logger.error(f"获取 selected-tab 失败: {e}")
        return None
    
    def _handle_proposal_modal(self, selected_tab: str | None = None, template_content: str = "") -> bool:
        """处理 Proposal 弹窗"""
        try:
            iframe = self._wait_for_modal_iframe()
            if not iframe:
                logger.warning(f"未找到弹窗 iframe (类别: {selected_tab or '未知'})，可能弹窗加载超时")
                return False
            
            ok = self._select_template_term(iframe, self.template_term)
            if not ok:
                raise RuntimeError(f"template_term_not_found: {self.template_term}")

            self._select_tomorrow_date(iframe)
            self._input_comment(iframe, template_content)

            if self.input_partner_groups_tag and selected_tab:
                self._apply_partner_group(iframe, selected_tab)

            self._submit_proposal(iframe)
            return True
            
        except Exception as e:
            error_msg = str(e).lower()
            if 'disconnect' in error_msg or 'context' in error_msg or 'target closed' in error_msg:
                logger.warning(f"处理弹窗时页面断开: {e}")
                raise
            logger.error(f"处理弹窗失败: {e}")
        return False

    def _is_date_like_trigger(self, ele) -> bool:
        """判断元素是否属于日期/时间相关触发器，避免误点到 Contract Dates 区域的控件。

        真实 DOM 规律：
        - 日期选择按钮：data-testid="uicl-date-input"，icon class 含 "calendar-vnext"
        - 时分/AM-PM/时区下拉：data-testid="uicl-multi-select-input-button"，
          但其 field-label-pair 祖先节点的 class 含 "standard-date-time-input"
        - Template Term 的 field-label-pair class 含 "select-input"（不含 standard-date-time-input）
        """
        if not ele:
            return True

        # 日期按钮：data-testid="uicl-date-input"
        try:
            data_testid = (ele.attr('data-testid') or '').strip().lower()
            if data_testid == 'uicl-date-input':
                return True
        except Exception:
            pass

        # aria-label 含 date/calendar
        try:
            aria_label = (ele.attr('aria-label') or '').strip().lower()
            if 'date' in aria_label or 'calendar' in aria_label:
                return True
        except Exception:
            pass

        # 文本内容形如日期格式（例如 "May 8, 2026"）
        try:
            text = re.sub(r'\s+', ' ', (ele.text or '').strip())
            if re.match(r'^(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+\d{1,2},\s+\d{4}$', text):
                return True
        except Exception:
            pass

        # 向上找祖先节点，检查是否在 standard-date-time-input 的 field-label-pair 内
        # 这能识别时分/AM-PM/时区下拉——它们与日期按钮同属 Contract Dates 区域
        try:
            cur = ele.parent()
            for _ in range(6):
                if not cur:
                    break
                cls = (cur.attr('class') or '')
                if 'standard-date-time-input' in cls:
                    return True
                # 到达 iui-form-section 层级就停止向上检查，避免误判
                if 'iui-form-section' in cls:
                    break
                cur = cur.parent()
        except Exception:
            pass

        return False

    def _find_template_term_trigger(self, iframe):
        """仅在 Template Term 字段容器内寻找下拉触发器，避免误点日期/时区等其他控件。

        定位策略（按优先级）：
        1. 通过 input[name="insertionOrderId"] 精确定位 Template Term 的 multiselect 容器
           （该隐藏字段唯一属于 Template Term 组件，Contract Dates 区域没有此 name）
        2. 通过 Template Term 文字标签向上找到 iui-form-section，
           再在其内找 class 含 "select-input" 的 field-label-pair（排除 standard-date-time-input）
        """
        # ── 策略1：通过唯一隐藏字段 name="insertionOrderId" 精确定位 ──────────────
        # 真实 DOM 结构：Template Term multiselect 内有 <input type="hidden" name="insertionOrderId">
        # Contract Dates 区域的 name 是 startDateTime/endDateTime/lengthOption，不含此字段
        try:
            hidden = iframe.ele('css:input[name="insertionOrderId"]', timeout=2)
            if hidden:
                # 向上至多爬 3 层，找到 data-testid="uicl-multiselect-input" 容器
                cur = hidden.parent()
                for _ in range(3):
                    if not cur:
                        break
                    if (cur.attr('data-testid') or '') == 'uicl-multiselect-input':
                        trigger = cur.ele(
                            'css:button[data-testid="uicl-multi-select-input-button"]',
                            timeout=0.3,
                        )
                        if trigger and not self._is_date_like_trigger(trigger):
                            logger.debug("Template Term 触发器：通过 input[name=insertionOrderId] 定位")
                            return trigger
                        break
                    cur = cur.parent()
        except Exception as e:
            logger.debug(f"策略1定位 Template Term 触发器失败: {e}")

        # ── 策略2：通过 Template Term 标签 → iui-form-section → select-input 字段对 ──
        # 真实 DOM：Template Term 的 field-label-pair class 含 "select-input"
        # Contract Dates 的 field-label-pair class 含 "standard-date-time-input"，不会被误选
        try:
            term_label = iframe.ele('text:Template Term', timeout=2)
            if not term_label:
                logger.debug("未找到 Template Term 标签")
                return None

            # 向上找到 iui-form-section（最多爬 5 层）
            cur = term_label.parent()
            for _ in range(5):
                if not cur:
                    break
                cls = (cur.attr('class') or '')
                if 'iui-form-section' in cls:
                    # 只在含 "select-input" 的 field-label-pair 内查找（排除日期时间字段）
                    try:
                        field = cur.ele(
                            'css:div[data-testid="uicl-field-label-pair"][class*="select-input"]',
                            timeout=0.3,
                        )
                    except Exception:
                        field = None
                    if field:
                        trigger = field.ele(
                            'css:button[data-testid="uicl-multi-select-input-button"]',
                            timeout=0.3,
                        )
                        if trigger and not self._is_date_like_trigger(trigger):
                            logger.debug("Template Term 触发器：通过 iui-form-section > select-input 定位")
                            return trigger
                    break
                cur = cur.parent()
        except Exception as e:
            logger.debug(f"策略2定位 Template Term 触发器失败: {e}")

        logger.debug("未能在 Template Term 字段附近找到安全的下拉触发器")
        return None

    def _get_visible_template_term_dropdown(self, iframe):
        """获取当前真正可见的 Template Term 下拉层。"""
        dropdown = None
        js_find_visible = """
        return (function() {
            var selectors = ['div[data-testid="uicl-dropdown"]', 'div.iui-dropdown', 'ul[role="listbox"]'];
            for (var sel of selectors) {
                var els = document.querySelectorAll(sel);
                for (var el of els) {
                    var rect = el.getBoundingClientRect();
                    var style = window.getComputedStyle(el);
                    if (rect.width > 50 && rect.height > 50 && style.display !== 'none') {
                        el.setAttribute('data-rpa-visible-dropdown', 'true');
                        return 'found';
                    }
                }
            }
            return 'not_found';
        })();
        """
        try:
            result = iframe.run_js(js_find_visible)
            if result == 'found':
                dropdown = iframe.ele('css:[data-rpa-visible-dropdown="true"]', timeout=1)
                if dropdown:
                    try:
                        dropdown.run_js('this.removeAttribute("data-rpa-visible-dropdown");')
                    except Exception:
                        pass
        except Exception:
            dropdown = None

        if dropdown:
            return dropdown

        try:
            dropdowns = iframe.eles('css:div[data-testid="uicl-dropdown"]')
        except Exception:
            dropdowns = []

        for dd in dropdowns or []:
            try:
                rect_js = "var r = this.getBoundingClientRect(); var s = window.getComputedStyle(this); return JSON.stringify({w: r.width, h: r.height, d: s.display});"
                data = json.loads(dd.run_js(rect_js))
                if data['w'] > 0 and data['h'] > 0 and data['d'] != 'none':
                    return dd
            except Exception:
                continue

        return None

    def _open_template_term_dropdown(self, iframe):
        """安全打开 Template Term 下拉框，仅允许点击字段自身触发器。"""
        trigger = self._find_template_term_trigger(iframe)
        if not trigger:
            return None

        try:
            trigger.click(by_js=True)
        except Exception:
            try:
                trigger.click()
            except Exception as e:
                logger.debug(f"点击 Template Term 触发器失败: {e}")
                return None

        time.sleep(0.2)
        return self._get_visible_template_term_dropdown(iframe)
    
    def get_template_term_options(self, iframe) -> list[str]:
        """菜单层可调用的公开方法，替代跨层访问私有方法。"""
        return self._get_template_term_options(iframe)

    def _get_template_term_options(self, iframe) -> list[str]:
        """
        获取 Template Term 下拉框的所有选项值
        
        Args:
            iframe: iframe 对象
            
        Returns:
            list[str]: 选项文本列表，如果失败则返回空列表
        """
        options_list = []
        try:
            dropdown = self._open_template_term_dropdown(iframe)
            if not dropdown:
                logger.debug("未能安全打开 Template Term 下拉框，返回空选项列表")
                return []
            
            if dropdown:
                # 先尝试获取 li[@role="option"] 元素
                items = dropdown.eles('xpath:.//li[@role="option"]')
                for it in items or []:
                    txt = it.text or ''
                    if txt.strip():
                        options_list.append(txt.strip())
                
                # 如果没有找到，尝试获取 div.text-ellipsis 元素
                if not options_list:
                    nodes = dropdown.eles('css:div.text-ellipsis')
                    for it in nodes or []:
                        txt = it.text or ''
                        if txt.strip():
                            options_list.append(txt.strip())
            
            # 如果还是没有找到，尝试从 select 元素获取
            if not options_list:
                term_dropdown = iframe.ele('css:select[data-testid="uicl-select"]', timeout=2)
                if term_dropdown:
                    try:
                        option_elements = term_dropdown.eles('css:option')
                        for opt in option_elements or []:
                            txt = opt.text or opt.attr('value') or ''
                            if txt.strip():
                                options_list.append(txt.strip())
                    except Exception:
                        pass
            
            # 去重并保持顺序：仅按显示文本去重，保留 "(1)/(2)" 这类明确区分值
            seen = set()
            unique_options = []
            for opt in options_list:
                norm = re.sub(r'\s+', ' ', opt).strip().lower()
                if norm not in seen:
                    seen.add(norm)
                    unique_options.append(opt)

            return unique_options
            
        except Exception as e:
            logger.error(f"获取 Template Term 选项失败: {e}")
            return []

    def _select_template_term(self, iframe, term_text: str = "Commission Tier Terms") -> bool:
        """选择 Template Term"""
        try:
            desired = (term_text or "Commission Tier Terms").strip()
            desired_norm = re.sub(r'\s+', ' ', desired).strip().lower()
            logger.debug(f"匹配 Template Term: desired='{desired}', desired_norm='{desired_norm}'")
            term_sim_threshold = 0.72
            term_sim_tie_eps = 0.005

            term_dropdown = iframe.ele('css:select[data-testid="uicl-select"]', timeout=2)
            
            if term_dropdown:
                try:
                    term_dropdown.select(desired)
                    logger.info(f"已选择 Template Term: {desired}")
                    time.sleep(0.3)
                    return True
                except Exception as e:
                    logger.warning(f"<select> 选择 Template Term 失败，尝试自定义下拉: {e}")

            dropdown = self._open_template_term_dropdown(iframe)

            if dropdown:
                options = []
                # 优先从 listbox 中获取选项
                listbox = dropdown.ele('css:ul[role="listbox"]', timeout=0.5)
                if listbox:
                    items = listbox.eles('css:li')
                else:
                    items = dropdown.eles('xpath:.//li[@role="option"]')

                for it in items or []:
                    txt = it.text or ''
                    txtn = re.sub(r'\s+', ' ', txt).strip().lower()
                    options.append((txt, txtn, it))
                if not options:
                    nodes = dropdown.eles('css:div.text-ellipsis')
                    for it in nodes or []:
                        txt = it.text or ''
                        txtn = re.sub(r'\s+', ' ', txt).strip().lower()
                        options.append((txt, txtn, it))

                # 去重：避免 DOM 中相同显示文本的重复节点，但保留 "(1)/(2)" 这类明确值
                seen_norm = set()
                unique_options = []
                for txt, txtn, ele in options:
                    if txtn not in seen_norm:
                        seen_norm.add(txtn)
                        unique_options.append((txt, txtn, ele))
                options = unique_options
                logger.debug(f"找到 {len(options)} 个唯一 Template Term 选项: {[txt for txt, _, _ in options]}")

                def _click_term_row(elem, picked_label: str, persist_choice: bool = False) -> bool:
                    try:
                        elem.wait.clickable()
                    except Exception:
                        pass
                    try:
                        elem.click()
                    except Exception:
                        elem.click(by_js=True)
                    if persist_choice:
                        settings = self.config.load_settings()
                        settings['template_term'] = picked_label
                        self.config.save_settings(settings)
                        self.template_term = picked_label
                    logger.info(f"已选择 Template Term: {picked_label}")
                    time.sleep(0.3)
                    return True

                def _ask_choice(total: int):
                    sel = questionary.text(
                        "请输入编号:",
                        validate=lambda x: x.isdigit() and 1 <= int(x) <= total or "请输入有效编号",
                    ).ask()
                    if sel and sel.isdigit():
                        return int(sel) - 1
                    return None

                def _prompt_and_pick(candidates, title: str) -> bool:
                    """候选项结构: [(display_text, element, persist_label)]"""
                    if title:
                        self.console.print(title)
                    for idx, (display_text, _, _) in enumerate(candidates, start=1):
                        self.console.print(f"{idx}. {display_text}")
                    picked_index = _ask_choice(len(candidates))
                    if picked_index is None:
                        return False
                    _, element, persist_label = candidates[picked_index]
                    return _click_term_row(element, persist_label, persist_choice=True)

                scored = [
                    (SequenceMatcher(None, desired_norm, n).ratio(), t, e) for (t, n, e) in options
                ]
                scored.sort(key=lambda x: -x[0])
                best_score = scored[0][0] if scored else 0.0
                logger.debug(f"Template Term 相似度得分: {[(t, f'{score:.3f}') for score, t, _ in scored]}")
                logger.debug(f"最佳得分: {best_score:.3f}, 阈值: {term_sim_threshold}")
                if best_score >= term_sim_threshold:
                    top = [s for s in scored if s[0] >= best_score - term_sim_tie_eps]
                    logger.debug(f"匹配成功，最佳得分 {best_score:.3f} ≥ 阈值 {term_sim_threshold}，找到 {len(top)} 个候选项")
                    if len(top) == 1:
                        return _click_term_row(top[0][2], top[0][1])
                    top_candidates = [
                        (f"{t}  [dim](相似度 {best_score:.2f})[/dim]", e, t)
                        for (_, t, e) in top
                    ]
                    if _prompt_and_pick(top_candidates, "\n[bold]多个相似候选项，请选择：[/bold]"):
                        return True
                    return False

                logger.debug(f"匹配失败，最佳得分 {best_score:.3f} < 阈值 {term_sim_threshold}")
                if options:
                    self.console.print(
                        f"\n[bold]未匹配到配置项（最高相似度 {best_score:.2f}，需 ≥{term_sim_threshold:.2f}），"
                        "以下为所有可选项：[/bold]"
                    )
                    all_candidates = [(t, e, t) for (t, _, e) in options]
                    if _prompt_and_pick(all_candidates, ""):
                        return True
                    return False
            
            logger.debug("未找到 Template Term 下拉框或选项")
            self.console.print("\n[bold]未找到可选项[/bold]")
            return False
            
        except Exception as e:
            logger.error(f"选择 Template Term 失败: {e}")
            return False
    
    def _normalize_partner_group_text(self, text: str) -> str:
        """规范化 Partner Group 文本用于匹配。"""
        raw = text or ""
        raw = re.sub(r'\s*\(\d+\)\s*$', '', raw)
        raw = re.sub(r'\s+', '', raw)
        return raw.strip().lower()

    def _calc_text_similarity(self, text1: str, text2: str) -> float:
        """
        计算两个文本的相似度（0.0 ~ 1.0）。
        用于处理下拉框选项和输入值不完全匹配但相似度高的情况。
        """
        # 规范化两个文本
        norm1 = self._normalize_partner_group_text(text1)
        norm2 = self._normalize_partner_group_text(text2)

        if not norm1 or not norm2:
            return 0.0

        # 完全匹配
        if norm1 == norm2:
            return 1.0

        # 包含匹配（一个包含另一个）
        if norm1 in norm2 or norm2 in norm1:
            longer = max(len(norm1), len(norm2))
            shorter = min(len(norm1), len(norm2))
            return 0.8 + 0.2 * (shorter / longer)  # 基础 0.8 分，根据长度比例加分

        # 计算编辑距离相似度（Levenshtein 距离简化版）
        # 使用最长公共子序列（LCS）的近似
        len1, len2 = len(norm1), len(norm2)
        max_len = max(len1, len2)
        if max_len == 0:
            return 1.0

        # 简单的字符匹配计数
        matches = sum(c1 == c2 for c1, c2 in zip(norm1, norm2))
        # 考虑错位匹配
        common_chars = len(set(norm1) & set(norm2))

        # 综合分数：位置匹配占 60%，字符集合匹配占 40%
        position_score = matches / max_len
        char_set_score = common_chars / max_len
        return position_score * 0.6 + char_set_score * 0.4

    def _find_best_matching_option(
        self,
        options: list[tuple[str, str, object]],
        target_text: str,
        similarity_threshold: float = 0.7,
    ) -> tuple[str, str, object] | None:
        """
        从选项列表中找到与目标文本最匹配的选项。

        Args:
            options: (显示文本, 规范化文本, 元素) 的列表
            target_text: 目标文本
            similarity_threshold: 相似度阈值，低于此值的选项会被过滤

        Returns:
            最匹配的选项，如果没有符合条件的返回 None
        """
        if not options:
            return None

        target_norm = self._normalize_partner_group_text(target_text)

        # 计算每个选项的相似度
        scored_options = []
        for display_text, norm_text, element in options:
            # 首先检查规范化文本是否完全匹配
            if norm_text == target_norm:
                return (display_text, norm_text, element)  # 完全匹配，直接返回

            # 计算相似度
            sim = self._calc_text_similarity(display_text, target_text)
            if sim >= similarity_threshold:
                scored_options.append((sim, display_text, norm_text, element))

        if not scored_options:
            return None

        # 按相似度排序，返回最高的
        scored_options.sort(key=lambda x: x[0], reverse=True)
        best = scored_options[0]

        if self.partner_groups_debug_logging:
            logger.info(
                f"[PartnerGroupsDebug] 最佳匹配选项: '{best[1]}' (相似度={best[0]:.2f})，"
                f"目标='{target_text}'"
            )

        return (best[1], best[2], best[3])

    def _read_partner_group_dropdown_options(
        self,
        dropdown,
        *,
        emit_debug_log: bool | None = None,
    ) -> list[tuple[str, str, object]]:
        """读取 Partner Group 下拉选项，返回 (显示文本, 规范化文本, 元素)。"""
        # 注意：class 名如 _4-15-1_Baf2T、_4-48-2_Baf2T 是动态生成的，使用 [class*="Baf2T"] 匹配
        # xpath://ul/li/div/div 对应用户提供的结构 @/html/body/div[12]/div/div/ul/li/div/div
        selectors = [
            'css:li[role="option"]',
            'css:div[role="option"]',
            'css:[class*="Baf2T"]',
            'xpath://ul/li/div/div',  # 用户提供的 XPath 模式（简化为相对路径）
            'css:li',
        ]
        options: list[tuple[str, str, object]] = []
        seen: set[str] = set()

        for selector in selectors:
            try:
                nodes = dropdown.eles(selector, timeout=0.2)
            except Exception:
                nodes = []
            if self.partner_groups_debug_logging and nodes:
                logger.info(f"[PartnerGroupsDebug] Selector '{selector}' 找到 {len(nodes)} 个节点")
            for node in nodes or []:
                try:
                    text = (node.text or "").strip()
                    if not text:
                        continue
                    norm_text = self._normalize_partner_group_text(text)
                    key = f"{norm_text}::{text}"
                    if key in seen:
                        continue
                    seen.add(key)
                    options.append((text, norm_text, node))
                except Exception:
                    continue
            if options:
                break

        # 如果基于特定 selector 仍然没有解析到任何可选项，做一次兜底：遍历下拉内所有子元素，
        # 取有可见文本的元素作为候选项，按规范化文本+原始文本去重。
        if not options:
            try:
                nodes = dropdown.eles('xpath:.//*', timeout=0.2)
            except Exception:
                nodes = []
            for node in nodes or []:
                try:
                    text = (node.text or "").strip()
                    if not text:
                        continue
                    norm_text = self._normalize_partner_group_text(text)
                    key = f"{norm_text}::{text}"
                    if key in seen:
                        continue
                    seen.add(key)
                    options.append((text, norm_text, node))
                except Exception:
                    continue
        should_log = (
            self.partner_groups_debug_logging
            if emit_debug_log is None
            else (emit_debug_log and self.partner_groups_debug_logging)
        )

        if should_log:
            # 打印下拉解析结果，便于分析未点击场景
            try:
                logger.info(
                    f"[PartnerGroupsDebug] 解析下拉选项数量={len(options)}，详细列表={[t for t, _, _ in options]}"
                )
            except Exception:
                # 日志本身不影响流程
                pass

        return options

    def _verify_partner_group_selected(self, iframe, target_norm: str, *, emit_failure_log: bool = False) -> bool:
        """
        验证 Partner Group 是否已经被成功选中（尽量避免误判）。

        背景：
        - DrissionPage 的 click() 通常不返回 True/False，成功与否主要靠是否抛异常；
        - 但 Impact 的 UI 有时会出现「click 不报错但业务上未真正选中」或
          「已经选中但我们用的 selector 找不到 chip」两类问题。

        本函数尽量用"文本匹配 + 排除下拉 option 区域"的方式验证：
        1) 定位 tag 输入容器（优先 data-testid，其次 class 回退）；
        2) 扫描容器内所有有文本的节点，过滤掉 role=option/listbox 及其子树；
        3) 对文本做规范化后与 target_norm 比较。
        """
        try:
            base_container = None
            # 优先：新版 tag-input 容器（注意：有些 UI 结构里 .iui-tag-input 可能只是 input-wrap，需要继续向上找）
            for selector in (
                'css:[data-testid="uicl-tag-input"]',
                'css:.iui-tag-input',
                'css:[class*="tag-input"]',
            ):
                try:
                    base_container = iframe.ele(selector, timeout=0.6)
                except Exception:
                    base_container = None
                if base_container:
                    break

            if not base_container:
                # 兜底：用 input 的父节点作为容器
                try:
                    input_ele = iframe.ele('css:input[data-testid="uicl-tag-input-text-input"]', timeout=0.8)
                    if input_ele:
                        base_container = input_ele.parent()
                except Exception:
                    base_container = None

            if not base_container:
                if self.partner_groups_debug_logging and emit_failure_log:
                    logger.warning("[PartnerGroupsDebug] 未找到 tag 容器，无法验证是否已选中 Partner Group。")
                return False

            # 收集多个候选容器：base_container + 若干层父节点（以及 input 的父链），避免选到过窄的 input-wrap 导致误判
            containers: list = []
            seen_ids: set[int] = set()

            def _add_container(ele) -> None:
                if not ele:
                    return
                k = id(ele)
                if k in seen_ids:
                    return
                seen_ids.add(k)
                containers.append(ele)

            cur = base_container
            for _ in range(4):
                _add_container(cur)
                try:
                    cur = cur.parent()
                except Exception:
                    break

            try:
                input_ele2 = iframe.ele('css:input[data-testid="uicl-tag-input-text-input"]', timeout=0.6)
            except Exception:
                input_ele2 = None
            if input_ele2:
                cur = input_ele2.parent()
                for _ in range(4):
                    _add_container(cur)
                    try:
                        cur = cur.parent()
                    except Exception:
                        break

            def _is_in_dropdown(node) -> bool:
                cur = node
                for _ in range(10):
                    if not cur:
                        break
                    try:
                        role = (cur.attr('role') or '').strip().lower()
                        if role in ('option', 'listbox'):
                            return True
                    except Exception:
                        pass
                    try:
                        dtid = (cur.attr('data-testid') or '').strip()
                        if dtid == 'uicl-tag-input-dropdown':
                            return True
                    except Exception:
                        pass
                    try:
                        cur = cur.parent()
                    except Exception:
                        break
                return False

            reports: list[dict] = []

            for idx, container in enumerate(containers):
                try:
                    nodes = container.eles('xpath:.//*', timeout=0.4)
                except Exception:
                    nodes = []

                scanned: int = 0
                matched_text: str | None = None
                samples: list[str] = []

                best_similarity = 0.0
                best_match_text = None

                for node in nodes or []:
                    try:
                        text = (node.text or "").strip()
                    except Exception:
                        continue
                    if not text:
                        continue
                    if _is_in_dropdown(node):
                        continue

                    scanned += 1
                    norm = self._normalize_partner_group_text(text)
                    if self.partner_groups_debug_logging and emit_failure_log and len(samples) < 20:
                        samples.append(f"{text} -> {norm}")

                    # 优先完全匹配
                    if norm == target_norm:
                        matched_text = text
                        break

                    # 计算相似度，记录最佳匹配
                    sim = self._calc_text_similarity(text, target_norm)
                    if sim > best_similarity:
                        best_similarity = sim
                        best_match_text = text

                # 没有完全匹配时，使用相似度阈值判断
                if matched_text is None and best_similarity >= 0.8:
                    matched_text = best_match_text
                    if self.partner_groups_debug_logging:
                        logger.info(
                            f"[PartnerGroupsDebug] 验证时使用相似度匹配成功: "
                            f"text='{best_match_text}', target='{target_norm}', sim={best_similarity:.2f}"
                        )

                if matched_text is not None:
                    if self.partner_groups_debug_logging:
                        try:
                            cls = (container.attr('class') or '').strip()
                        except Exception:
                            cls = ''
                        logger.info(
                            f"[PartnerGroupsDebug] 验证成功，在候选容器#{idx}找到目标: 原始文本='{matched_text}', "
                            f"target_norm='{target_norm}', container_class='{cls}'"
                        )
                    return True

                if emit_failure_log:
                    try:
                        cls = (container.attr('class') or '').strip()
                    except Exception:
                        cls = ''
                    reports.append(
                        {
                            "idx": idx,
                            "scanned": scanned,
                            "class": cls,
                            "samples": samples,
                        }
                    )

            if self.partner_groups_debug_logging and emit_failure_log:
                # 只输出前几个容器的摘要，避免日志过长
                logger.warning(
                    f"[PartnerGroupsDebug] 验证失败：未在任何候选容器找到目标，target_norm='{target_norm}'，"
                    f"candidates={len(containers)}，reports={reports[:3]}"
                )
            return False
        except Exception as e:
            if self.partner_groups_debug_logging and emit_failure_log:
                logger.error(f"[PartnerGroupsDebug] 验证 Partner Group 选中状态时出错: {e!r}")
            return False

    def _click_partner_group_option_and_verify(
        self,
        iframe,
        dropdown,
        pick_ele,
        pick_text: str,
        target_norm: str,
        *,
        wait_timeout: float = 0.5,
    ) -> bool:
        """
        点击 Partner Group 下拉选项，并等待验证通过（避免 click() 无异常但业务未选中的情况）。

        策略（优化后）：
        - 只使用传入的元素本身，不再尝试父元素（减少不必要尝试）
        - 只保留 JS click 和真实点击两种方式，移除事件派发（加速）
        - 减少默认等待时间到 0.5 秒（总超时从 12+ 秒降到 ~2 秒）
        """

        def _gather_targets(base_ele) -> list:
            # 优化：只返回当前元素，不再尝试父元素
            # 实际测试表明直接点击选项元素本身成功率已足够高
            return [base_ele] if base_ele else []

        def _refresh_base_ele() -> tuple[str, object]:
            if not dropdown:
                return pick_text, pick_ele
            try:
                opts = self._read_partner_group_dropdown_options(dropdown)
            except Exception:
                opts = []
            # 优先按规范化文本完全匹配
            for t, n, e in opts or []:
                if n == target_norm:
                    return t, e
            # 次选：使用相似度匹配（支持大小写、空格不一致等情况）
            best_match = self._find_best_matching_option(
                opts, pick_text, similarity_threshold=0.6
            )
            if best_match:
                return best_match[0], best_match[2]
            # 兜底：如果只有一个选项，直接返回
            if len(opts or []) == 1:
                t, _, e = opts[0]
                return t, e
            return pick_text, pick_ele

        def _get_tag_input_value() -> str:
            try:
                inp = iframe.ele('css:input[data-testid="uicl-tag-input-text-input"]', timeout=0.2)
            except Exception:
                inp = None
            if not inp:
                return ""
            try:
                return ((inp.attr('value') or "").strip())
            except Exception:
                return ""

        def _dropdown_has_target() -> bool:
            # 尝试使用传入的 dropdown，如果失败则从 iframe 重新查找
            dropdown_ele = dropdown
            if not dropdown_ele:
                try:
                    dropdown_ele = iframe.ele('css:[data-testid="uicl-tag-input-dropdown"]', timeout=0.3)
                except Exception:
                    try:
                        tag_input = iframe.ele('css:input[data-testid="uicl-tag-input-text-input"]', timeout=0.2)
                        dropdown_ele = tag_input.ele('xpath:ancestor::*[@data-testid="uicl-tag-input"][1]', timeout=0.2)
                    except Exception:
                        dropdown_ele = None

            if not dropdown_ele:
                if self.partner_groups_debug_logging:
                    logger.info("[PartnerGroupsDebug] 无法找到 dropdown 元素")
                return False

            try:
                opts = self._read_partner_group_dropdown_options(dropdown_ele, emit_debug_log=False)
            except Exception as e:
                if self.partner_groups_debug_logging:
                    logger.warning(f"[PartnerGroupsDebug] 读取下拉选项时出错: {e!r}")
                opts = []

            if not opts:
                if self.partner_groups_debug_logging:
                    logger.info("[PartnerGroupsDebug] 下拉列表为空或无法读取")
                return False

            # 使用相似度匹配，而不是完全相等
            for display_text, norm_text, _ in opts:
                # 完全匹配
                if norm_text == target_norm:
                    if self.partner_groups_debug_logging:
                        logger.info(f"[PartnerGroupsDebug] 下拉中仍包含目标(完全匹配): '{display_text}'")
                    return True
                # 相似度匹配
                sim = self._calc_text_similarity(display_text, target_norm)
                if sim >= 0.8:
                    if self.partner_groups_debug_logging:
                        logger.info(f"[PartnerGroupsDebug] 下拉中仍包含目标(相似度{sim:.2f}): '{display_text}'")
                    return True

            if self.partner_groups_debug_logging:
                logger.info(f"[PartnerGroupsDebug] 下拉中不包含目标选项，当前选项: {[t for t, _, _ in opts]}")
            return False

        def _wait_selected(timeout_s: float) -> bool:
            deadline = time.time() + timeout_s
            click_time = time.time()
            while time.time() < deadline:
                # 方式1：chip 已存在，直接成功（最可靠）
                if self._verify_partner_group_selected(iframe, target_norm, emit_failure_log=False):
                    # 验证通过：chip 已存在，主动清空输入框（防止组件未自动清空）
                    try:
                        inp = iframe.ele('css:input[data-testid="uicl-tag-input-text-input"]', timeout=0.2)
                        if inp:
                            # 使用 JS 清空输入框，确保干净
                            inp.run_js("this.value=''; this.dispatchEvent(new Event('input', {bubbles:true}));")
                            if self.partner_groups_debug_logging:
                                logger.info("[PartnerGroupsDebug] 选中后已主动清空输入框")
                    except Exception as e:
                        if self.partner_groups_debug_logging:
                            logger.warning(f"[PartnerGroupsDebug] 清空输入框时出错: {e!r}")
                    return True

                # 方式2：输入框清空 + 下拉不再包含目标项
                input_empty = _get_tag_input_value() == ""
                dropdown_cleared = not _dropdown_has_target()

                if self.partner_groups_debug_logging:
                    logger.info(f"[PartnerGroupsDebug] 验证中: input_empty={input_empty}, dropdown_cleared={dropdown_cleared}")

                if input_empty and dropdown_cleared:
                    if self.partner_groups_debug_logging:
                        logger.info("[PartnerGroupsDebug] 验证通过：输入框已清空且下拉已不包含目标选项")
                    return True

                # 方式3：点击后等待足够时间（给 DOM 更新），且输入框已清空
                # 某些情况下 dropdown 不会立即消失，但 chip 已添加
                if input_empty and (time.time() - click_time) >= 0.3:
                    # 再检查一次 chip 是否存在（可能在 dropdown 没消失时已添加）
                    if self._verify_partner_group_selected(iframe, target_norm, emit_failure_log=False):
                        if self.partner_groups_debug_logging:
                            logger.info("[PartnerGroupsDebug] 验证通过：点击后延迟检查 chip 存在")
                        return True

                time.sleep(0.1)  # 优化：减少轮询间隔，加快验证速度

            # 只在最终失败时输出一次验证详情，避免轮询期间刷屏
            if self.partner_groups_debug_logging:
                self._verify_partner_group_selected(iframe, target_norm, emit_failure_log=True)
            return False

        def _scroll_into_view(ele) -> None:
            try:
                ele.run_js('this.scrollIntoView({block:"center", inline:"nearest"});')
            except Exception:
                pass

        # 优化：只保留两种最常用的点击方式，移除 dispatch（减少尝试次数）
        # JS 点击通常最可靠（避免遮挡问题），真实点击作为兜底
        click_methods = [
            ("js", lambda e: e.click(by_js=True)),
            ("real", lambda e: e.click()),
        ]

        # 两轮：先用原始元素尝试，再刷新一次下拉元素引用（防止 DOM 重渲染导致点到旧引用）
        for refresh_round in range(2):
            if refresh_round == 0:
                base_text, base_ele = pick_text, pick_ele
            else:
                base_text, base_ele = _refresh_base_ele()

            for target_ele in _gather_targets(base_ele):
                _scroll_into_view(target_ele)
                for method_name, do_click in click_methods:
                    if self.partner_groups_debug_logging:
                        logger.info(
                            f"[PartnerGroupsDebug] 尝试点击选项 method={method_name}，option_text='{base_text}'"
                        )
                    try:
                        do_click(target_ele)
                    except Exception as e:
                        if self.partner_groups_debug_logging:
                            logger.warning(
                                f"[PartnerGroupsDebug] 点击异常 method={method_name}，option_text='{base_text}'，error={e!r}"
                            )
                        continue
                    if _wait_selected(wait_timeout):
                        if self.partner_groups_debug_logging:
                            logger.info(
                                f"[PartnerGroupsDebug] 点击后验证成功 method={method_name}，option_text='{base_text}'"
                            )
                        return True
                    if self.partner_groups_debug_logging:
                        logger.warning(
                            f"[PartnerGroupsDebug] 点击后验证仍失败 method={method_name}，option_text='{base_text}'"
                        )

        return False

    def _apply_partner_group(self, iframe, selected_tab: str) -> None:
        """根据配置使用 UI 下拉或直连 API 设置 Partner Group。"""
        pg = getattr(self, "partner_groups", None) or {}
        mode = (pg.get("mode") or "ui").strip().lower()
        if mode == "api":
            from domain.partner_groups_api import set_partner_group_via_api

            set_partner_group_via_api(
                iframe,
                selected_tab,
                pg,
                debug=bool(getattr(self, "partner_groups_debug_logging", False)),
            )
            return
        self._input_tag_and_select(iframe, selected_tab)

    def _input_tag_and_select(self, iframe, selected_tab: str) -> bool:
        """在 tag-input 中逐字符输入，完整输入后出现唯一匹配时立即选中。"""
        try:
            search_text = re.sub(r'\s+', '', selected_tab or "")
            if not search_text:
                raise Exception("selected_tab 为空，无法输入 Partner Group")

            target_norm = self._normalize_partner_group_text(search_text)
            cache_key = target_norm
            cached_len = self._partner_group_prefix_len_cache.get(cache_key)

            tag_input = iframe.ele('css:input[data-testid="uicl-tag-input-text-input"]', timeout=3)
            if not tag_input:
                raise Exception("未找到 tag-input 输入框")

            input_lengths: list[int] = []
            if cached_len and 1 <= cached_len <= len(search_text):
                input_lengths.append(cached_len)
            input_lengths.extend([i for i in range(1, len(search_text) + 1) if i not in input_lengths])

            for input_len in input_lengths:
                prefix = search_text[:input_len]

                tag_input.click(by_js=True)
                time.sleep(0.1)
                tag_input.clear()
                tag_input.input(prefix)
                if self.partner_groups_debug_logging:
                    logger.info(
                        f"[PartnerGroupsDebug] 尝试输入前缀: '{prefix}' (长度={input_len})，"
                        f"selected_tab='{selected_tab}', cached_len={cached_len}, "
                        f"cache_key='{cache_key}', 计划尝试长度序列={input_lengths}"
                    )
                else:
                    logger.debug(f"Partner Group 尝试输入前缀: '{prefix}' (长度={input_len})")
                time.sleep(0.25)

                # 兼容旧版和新版 UI：
                # - 旧版存在独立的 [data-testid=\"uicl-tag-input-dropdown\"] 容器；
                # - 新版下拉选项直接挂在 tag-input 容器内（data-testid=\"uicl-tag-input\"）。
                dropdown = None
                try:
                    dropdown = iframe.ele('css:[data-testid=\"uicl-tag-input-dropdown\"]', timeout=1)
                except Exception:
                    dropdown = None

                # 优化：使用 xpath 直接查找祖先元素，代替循环 4 层 parent()
                if not dropdown:
                    try:
                        dropdown = tag_input.ele('xpath:ancestor::*[@data-testid="uicl-tag-input"][1]', timeout=0.3)
                    except Exception:
                        dropdown = None

                if not dropdown:
                    dropdown = tag_input

                options = self._read_partner_group_dropdown_options(dropdown)
                if not options:
                    if self.partner_groups_debug_logging:
                        logger.info(
                            "[PartnerGroupsDebug] 当前前缀未解析到任何下拉选项，继续尝试更长输入；"
                            f"prefix='{prefix}', input_len={input_len}"
                        )
                    else:
                        logger.debug("Partner Group 下拉为空，继续尝试下一长度")
                    continue

                # 每次输入后，如果下拉列表中只有一个元素，直接选中并缓存当前输入长度
                if len(options) == 1:
                    pick_text, _, pick_ele = options[0]
                    if self.partner_groups_debug_logging:
                        logger.info(
                            f"[PartnerGroupsDebug] 检测到唯一选项，准备点击。"
                            f"prefix='{prefix}', input_len={input_len}, pick_text='{pick_text}', "
                            f"options_count={len(options)}"
                        )
                    ok = self._click_partner_group_option_and_verify(
                        iframe=iframe,
                        dropdown=dropdown,
                        pick_ele=pick_ele,
                        pick_text=pick_text,
                        target_norm=target_norm,
                        wait_timeout=0.5,
                    )
                    if not ok:
                        raise Exception(f"Partner Group 选项点击后验证失败: {pick_text}")

                    self._partner_group_prefix_len_cache[cache_key] = input_len
                    logger.info(
                        f"已选择 Partner Group: {pick_text}（当前输入长度={input_len}，仅 1 个可见选项，已缓存）"
                    )
                    time.sleep(0.2)
                    return True

                # 完整输入整个名称后，使用相似度匹配查找最佳选项
                # 支持大小写不一致、空格不一致等情况
                if input_len == len(search_text):
                    # 首先尝试完全匹配
                    exact_matches = [opt for opt in options if opt[1] == target_norm]
                    if exact_matches:
                        pick_text, _, pick_ele = exact_matches[0]
                        if self.partner_groups_debug_logging:
                            logger.info(
                                f"[PartnerGroupsDebug] 完整输入且找到完全匹配项；"
                                f"target_norm='{target_norm}', pick_text='{pick_text}'"
                            )
                    else:
                        # 没有完全匹配时，使用相似度匹配找最佳选项
                        best_match = self._find_best_matching_option(
                            options, selected_tab, similarity_threshold=0.6
                        )
                        if best_match:
                            pick_text, _, pick_ele = best_match
                            if self.partner_groups_debug_logging:
                                logger.info(
                                    f"[PartnerGroupsDebug] 完整输入且找到相似度匹配项；"
                                    f"target='{selected_tab}', pick_text='{pick_text}'"
                                )
                        else:
                            pick_text, pick_ele = None, None

                    if pick_text and pick_ele:
                        ok = self._click_partner_group_option_and_verify(
                            iframe=iframe,
                            dropdown=dropdown,
                            pick_ele=pick_ele,
                            pick_text=pick_text,
                            target_norm=target_norm,
                            wait_timeout=0.5,
                        )
                        if not ok:
                            raise Exception(f"Partner Group 匹配项点击后验证失败: {pick_text}")

                        self._partner_group_prefix_len_cache[cache_key] = input_len
                        logger.info(
                            f"已选择 Partner Group: {pick_text}（完整输入={input_len}字符，已缓存）"
                        )
                        time.sleep(0.2)
                        return True

            if self.partner_groups_debug_logging:
                logger.warning(
                    f"[PartnerGroupsDebug] 所有前缀尝试完毕，仍未找到可点击的唯一匹配项；"
                    f"selected_tab='{selected_tab}', search_text='{search_text}', "
                    f"尝试长度序列={input_lengths}, 当前缓存={self._partner_group_prefix_len_cache.get(cache_key)}"
                )
            raise Exception(f"未找到唯一匹配项: {selected_tab}")

        except Exception as e:
            logger.error(f"输入 tag 并选择失败: {e}")
            raise
    
    def _get_today(self) -> date:
        """获取当前日期（带缓存），保证同一批次内所有 proposal 使用一致的 T+1"""
        if self._cached_today is None:
            self._cached_today = date.today()
            logger.info(f"当前日期已缓存: {self._cached_today.isoformat()}")
        return self._cached_today

    def _select_tomorrow_date(self, iframe) -> bool:
        """
        选择明天的日期

        Args:
            iframe: iframe 对象

        Returns:
            bool: 是否成功
        """
        try:
            today = self._get_today()
            tomorrow = today + timedelta(days=1)
            target_date = datetime.combine(tomorrow, datetime.min.time())
            result = self.date_picker.select_date(
                context=iframe,
                target_date=target_date,
                open_picker=True,
            )
            
            if result.success:
                logger.info(f"日期选择成功，使用方法: {result.method}")
                return True
            else:
                logger.warning(f"日期选择失败: {result.error}")
                return False
                
        except Exception as e:
            logger.error(f"选择日期失败: {e}")
        return False
    
    def _input_comment(self, iframe, template_content: str = "") -> bool:
        """填写留言"""
        try:
            template = template_content or self.template_manager.get_active_template()
            if not template:
                logger.warning("留言模板为空")
                logger.warning("留言模板为空")
                return False
            
            textarea = iframe.ele('css:textarea[data-testid="uicl-textarea"]', timeout=3)
            if not textarea:
                textarea = iframe.ele('css:textarea[name="comment"]', timeout=2)
            
            if not textarea:
                logger.warning("未找到留言输入框")
                logger.warning("未找到留言输入框")
                return False
            
            textarea.click(by_js=True)
            time.sleep(0.2)
            textarea.clear()
            textarea.input(template)
            logger.info("已填写留言内容")
            logger.info("已填写留言内容")
            time.sleep(0.3)
            return True
            
        except Exception as e:
            logger.error(f"填写留言失败: {e}")
            logger.error(f"填写留言失败: {e}")
        return False
    
    def _submit_proposal(self, iframe) -> bool:
        """提交 Proposal"""
        try:
            # 开发测试模式：不点击弹窗中的提交按钮
            if self.dry_run:
                logger.info("[DRY-RUN] 跳过点击弹窗中的 Send Proposal 提交按钮")
                self.console.print("[cyan]⚡ [DRY-RUN] 跳过点击弹窗中的提交按钮[/cyan]")
                # 关闭弹窗（点击关闭按钮或按 ESC）
                self._close_modal(iframe)
                return True
            
            submit_btn = iframe.ele('css:button[data-testid="uicl-button"]', timeout=3)
            if submit_btn and 'Send Proposal' in submit_btn.text:
                submit_btn.click(by_js=True)
                logger.info("已点击提交按钮")
                time.sleep(1)
                self._click_understand_button(iframe)
                return True
            
            submit_btn = iframe.ele('text:Send Proposal', timeout=2)
            if submit_btn and submit_btn.tag == 'button':
                submit_btn.click(by_js=True)
                logger.info("已点击提交按钮")
                time.sleep(1)
                self._click_understand_button(iframe)
                return True
            
            buttons = iframe.eles('css:button[data-testid="uicl-button"]')
            for btn in buttons:
                if 'Send Proposal' in btn.text:
                    btn.click(by_js=True)
                    logger.info("已点击提交按钮")
                    time.sleep(1)
                    self._click_understand_button(iframe)
                    return True
            
            logger.warning("未找到提交按钮")
            return False
            
        except Exception as e:
            logger.error(f"点击提交按钮失败: {e}")
        return False
    
    def _close_modal(self, iframe) -> bool:
        """关闭弹窗（用于 dry_run 模式）"""
        try:
            # 尝试点击关闭按钮
            close_btn = self.browser.find_element(
                'css:button[data-testid="uicl-icon-button"]',
                timeout=1,
                parent=iframe
            )
            if close_btn:
                self.browser.click(close_btn, by_js=True)
                logger.info("[DRY-RUN] 已关闭弹窗")
                time.sleep(0.5)
                return True
            
            # 备用：尝试点击 Cancel 按钮
            cancel_btn = iframe.ele('text:Cancel', timeout=1)
            if cancel_btn and cancel_btn.tag == 'button':
                cancel_btn.click(by_js=True)
                logger.info("[DRY-RUN] 已点击 Cancel 关闭弹窗")
                time.sleep(0.5)
                return True
            
            # 再备用：按 ESC 键
            try:
                self.browser.tab.actions.key_down('Escape').key_up('Escape').perform()
                logger.info("[DRY-RUN] 已按 ESC 关闭弹窗")
                time.sleep(0.5)
                return True
            except Exception:
                pass
            
            logger.warning("[DRY-RUN] 未能自动关闭弹窗，请手动关闭")
            return False
            
        except Exception as e:
            logger.warning(f"[DRY-RUN] 关闭弹窗失败: {e}")
        return False
    
    def _click_understand_button(self, iframe) -> bool:
        """点击确认按钮"""
        try:
            time.sleep(0.5)
            
            understand_btn = self.browser.find_element('text:I understand', timeout=3, parent=iframe)
            if understand_btn and understand_btn.tag == 'button':
                self.browser.click(understand_btn, by_js=True)
                logger.info("已点击 'I understand' 确认按钮")
                time.sleep(0.5)
                return True
            
            buttons = self.browser.find_elements('css:button[data-testid="uicl-button"]', parent=iframe)
            for btn in buttons:
                if btn and 'I understand' in (btn.text or ''):
                    self.browser.click(btn, by_js=True)
                    logger.info("已点击 'I understand' 确认按钮")
                    time.sleep(0.5)
                    return True
            
            understand_btn = self.browser.find_element('text:I understand', timeout=2)
            if understand_btn and understand_btn.tag == 'button':
                self.browser.click(understand_btn, by_js=True)
                logger.info("已点击 'I understand' 确认按钮")
                time.sleep(0.5)
                return True
            
            logger.warning("未找到 'I understand' 按钮")
            return False
            
        except Exception as e:
            logger.error(f"点击确认按钮失败: {e}")
        return False

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


    def _mark_button_state(self, button, attr: str, value: str = "true") -> bool:
        """为按钮设置指定的 DOM 属性标记"""
        try:
            current = button.attr(attr)
            if current == value:
                return True
            button.attr(attr, value)
            return True
        except Exception:
            try:
                button.run_js(f'this.setAttribute("{attr}", "{value}")')
                return True
            except Exception as e:
                logger.debug(f"设置按钮属性 {attr} 失败: {e}")
        return False



__all__ = ["ProposalSender", "SendProposalsResult"]
