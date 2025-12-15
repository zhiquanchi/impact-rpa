from DrissionPage import Chromium
from DrissionPage.errors import ElementNotFoundError, PageDisconnectedError, ContextLostError
import time
import os
import json
import re
from datetime import datetime, timedelta
from loguru import logger
import questionary
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.syntax import Syntax
from rich import print as rprint
import pyperclip
from exception_handler import exception_handler


class ConfigManager:
    """配置管理类，负责处理所有配置文件的读写"""
    
    def __init__(self, base_dir: str = None):
        self.base_dir = base_dir or os.path.dirname(__file__)
        self.config_dir = os.path.join(self.base_dir, 'config')
        self.log_dir = os.path.join(self.base_dir, 'logs')
        self.template_file = os.path.join(self.config_dir, 'template.txt')
        self.templates_file = os.path.join(self.config_dir, 'templates.json')
        self.settings_file = os.path.join(self.config_dir, 'settings.json')
        
        # 默认设置
        self.default_settings = {
            "max_proposals": 10,
            "scroll_delay": 1.0,
            "click_delay": 0.5,
            "modal_wait": 20.0,
            # Proposal 弹窗内的 Template Term 下拉默认选择项
            # 例如："Commission Tier Terms" / "Public Terms" / "Ulanzi Terms"
            "template_term": "Commission Tier Terms",
        }
        
        # 确保目录存在
        os.makedirs(self.config_dir, exist_ok=True)
        os.makedirs(self.log_dir, exist_ok=True)
        
        # 配置日志
        self._setup_logger()
    
    def _setup_logger(self):
        """配置日志"""
        logger.add(
            os.path.join(self.log_dir, 'impact_rpa_{time:YYYY-MM-DD}.log'),
            rotation='1 day',
            retention='7 days',
            level='INFO',
            format='{time:YYYY-MM-DD HH:mm:ss} | {level} | {message}',
            encoding='utf-8'
        )
    
    def load_settings(self) -> dict:
        """加载设置"""
        try:
            if os.path.exists(self.settings_file):
                with open(self.settings_file, 'r', encoding='utf-8') as f:
                    return {**self.default_settings, **json.load(f)}
        except Exception as e:
            logger.error(f"加载设置失败: {e}")
        return self.default_settings.copy()
    
    def save_settings(self, settings: dict) -> bool:
        """保存设置"""
        try:
            with open(self.settings_file, 'w', encoding='utf-8') as f:
                json.dump(settings, f, indent=4)
            logger.info("设置保存成功")
            return True
        except Exception as e:
            logger.error(f"保存设置失败: {e}")
            return False


class TemplateManager:
    """模板管理类，负责处理留言模板的CRUD操作"""
    
    def __init__(self, config: ConfigManager):
        self.config = config
        self._default_data = {"templates": [], "active_template_id": None}
    
    def load_all(self) -> dict:
        """加载所有模板数据"""
        try:
            if os.path.exists(self.config.templates_file):
                with open(self.config.templates_file, 'r', encoding='utf-8') as f:
                    return {**self._default_data, **json.load(f)}
            # 兼容旧的单模板文件
            elif os.path.exists(self.config.template_file):
                with open(self.config.template_file, 'r', encoding='utf-8') as f:
                    content = f.read().strip()
                    if content:
                        return {
                            "templates": [{"id": 1, "name": "默认模板", "content": content}],
                            "active_template_id": 1
                        }
        except Exception as e:
            logger.error(f"加载模板数据失败: {e}")
        return self._default_data.copy()
    
    def save_all(self, data: dict) -> bool:
        """保存所有模板数据"""
        try:
            with open(self.config.templates_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=4, ensure_ascii=False)
            logger.info("模板数据保存成功")
            return True
        except Exception as e:
            logger.error(f"保存模板数据失败: {e}")
            return False
    
    def get_active_template(self) -> str:
        """获取当前激活的模板内容"""
        try:
            data = self.load_all()
            active_id = data.get('active_template_id', 1)
            for tpl in data.get('templates', []):
                if tpl.get('id') == active_id:
                    return tpl.get('content', '')
            # 如果没找到激活的模板，返回第一个
            if data.get('templates'):
                return data['templates'][0].get('content', '')
        except Exception as e:
            logger.error(f"加载模板失败: {e}")
        return ""
    
    def get_active_template_info(self) -> dict:
        """获取当前激活的模板完整信息"""
        data = self.load_all()
        active_id = data.get('active_template_id')
        for tpl in data.get('templates', []):
            if tpl.get('id') == active_id:
                return tpl
        return None
    
    def get_next_id(self, data: dict = None) -> int:
        """获取下一个可用的模板ID"""
        if data is None:
            data = self.load_all()
        if not data.get('templates'):
            return 1
        max_id = max(tpl.get('id', 0) for tpl in data['templates'])
        return max_id + 1
    
    def add_template(self, name: str, content: str, activate: bool = True) -> bool:
        """添加新模板"""
        try:
            data = self.load_all()
            new_id = self.get_next_id(data)
            data['templates'].append({
                "id": new_id,
                "name": name or f"模板 {new_id}",
                "content": content
            })
            if activate:
                data['active_template_id'] = new_id
            return self.save_all(data)
        except Exception as e:
            logger.error(f"添加模板失败: {e}")
            return False
    
    def update_template(self, template_id: int, name: str = None, content: str = None) -> bool:
        """更新模板"""
        try:
            data = self.load_all()
            for tpl in data['templates']:
                if tpl.get('id') == template_id:
                    if name is not None:
                        tpl['name'] = name
                    if content is not None:
                        tpl['content'] = content
                    return self.save_all(data)
            return False
        except Exception as e:
            logger.error(f"更新模板失败: {e}")
            return False
    
    def delete_template(self, template_id: int) -> bool:
        """删除模板"""
        try:
            data = self.load_all()
            if len(data['templates']) <= 1:
                return False
            data['templates'] = [t for t in data['templates'] if t.get('id') != template_id]
            # 如果删除的是激活的模板，切换到第一个
            if template_id == data.get('active_template_id') and data['templates']:
                data['active_template_id'] = data['templates'][0].get('id')
            return self.save_all(data)
        except Exception as e:
            logger.error(f"删除模板失败: {e}")
            return False
    
    def set_active(self, template_id: int) -> bool:
        """设置激活的模板"""
        try:
            data = self.load_all()
            data['active_template_id'] = template_id
            return self.save_all(data)
        except Exception as e:
            logger.error(f"设置激活模板失败: {e}")
            return False


class BrowserManager:
    """浏览器管理类，负责浏览器连接和元素操作"""
    
    def __init__(self, console: Console):
        self.browser = None
        self.tab = None
        self.console = console
        self.max_retries = 3
    
    def init(self) -> bool:
        """初始化或重新连接浏览器"""
        try:
            self.browser = Chromium()
            self.tab = self.browser.latest_tab
            logger.info("浏览器连接成功")
            return True
        except Exception as e:
            logger.error(f"浏览器连接失败: {e}")
            return False
    
    def reconnect(self) -> bool:
        """重新连接浏览器"""
        self.console.print("[yellow]检测到页面断开，正在重新连接...[/yellow]")
        logger.warning("页面断开，尝试重新连接浏览器")
        
        for i in range(self.max_retries):
            try:
                self.browser = Chromium()
                self.tab = self.browser.latest_tab
                self.console.print("[green]✓ 浏览器重新连接成功[/green]")
                logger.info("浏览器重新连接成功")
                return True
            except Exception as e:
                logger.error(f"重连尝试 {i+1}/{self.max_retries} 失败: {e}")
                time.sleep(1)
        
        self.console.print("[red]✗ 浏览器重新连接失败[/red]")
        return False
    
    def is_connected(self) -> bool:
        """检查浏览器是否已连接"""
        return self.tab is not None
    
    def find_element(self, locator: str, timeout: int = 3, parent=None):
        """安全地查找元素"""
        target = parent if parent else self.tab
        try:
            element = target.ele(locator, timeout=timeout)
            return element
        except (ElementNotFoundError, PageDisconnectedError, ContextLostError) as e:
            logger.warning(f"查找元素失败: {e}")
            exception_handler.log_exception(
                e,
                context={
                    "operation": "查找元素",
                    "locator": locator,
                    "timeout": timeout
                }
            )
            return None
        except Exception as e:
            error_msg = str(e).lower()
            if 'disconnect' in error_msg or 'context' in error_msg or 'target closed' in error_msg:
                logger.warning(f"页面可能已断开: {e}")
                exception_handler.log_exception(
                    e,
                    context={
                        "operation": "查找元素",
                        "locator": locator,
                        "timeout": timeout,
                        "error_type": "页面断开"
                    }
                )
                return None
            raise
    
    def find_elements(self, locator: str, timeout: int = 3, parent=None) -> list:
        """安全地查找多个元素"""
        target = parent if parent else self.tab
        try:
            elements = target.eles(locator, timeout=timeout)
            return elements if elements else []
        except (ElementNotFoundError, PageDisconnectedError, ContextLostError) as e:
            logger.warning(f"查找元素失败: {e}")
            exception_handler.log_exception(
                e,
                context={
                    "operation": "查找多个元素",
                    "locator": locator,
                    "timeout": timeout
                }
            )
            return []
        except Exception as e:
            error_msg = str(e).lower()
            if 'disconnect' in error_msg or 'context' in error_msg or 'target closed' in error_msg:
                logger.warning(f"页面可能已断开: {e}")
                exception_handler.log_exception(
                    e,
                    context={
                        "operation": "查找多个元素",
                        "locator": locator,
                        "timeout": timeout,
                        "error_type": "页面断开"
                    }
                )
                return []
            raise
    
    def click(self, element, by_js: bool = False) -> bool:
        """安全地点击元素"""
        try:
            if by_js:
                element.click(by_js=True)
            else:
                element.click()
            return True
        except Exception as e:
            logger.warning(f"点击元素失败: {e}")
            return False
    
    def wait_for_page_ready(self, timeout: int = 10) -> bool:
        """等待页面就绪"""
        try:
            self.tab.wait.doc_loaded(timeout=timeout)
            time.sleep(0.5)
            return True
        except Exception as e:
            logger.warning(f"等待页面就绪失败: {e}")
            return False
    
    def scroll_down(self, pixels: int = 500) -> bool:
        """向下滚动页面"""
        try:
            self.tab.scroll.down(pixels)
            return True
        except Exception as e:
            logger.warning(f"滚动失败: {e}")
            return False
    
    def scroll_to_element(self, element) -> bool:
        """滚动到元素可见"""
        try:
            self.tab.scroll.to_see(element)
            return True
        except Exception as e:
            logger.warning(f"滚动到元素失败: {e}")
            return False
    
    def navigate(self, url: str) -> bool:
        """导航到指定URL"""
        try:
            self.tab.get(url)
            return self.wait_for_page_ready()
        except Exception as e:
            logger.error(f"导航失败: {e}")
            return False


class ProposalSender:
    """Proposal发送类，负责核心的RPA操作"""
    
    def __init__(self, browser: BrowserManager, template_manager: TemplateManager, console: Console, config: ConfigManager):
        self.browser = browser
        self.template_manager = template_manager
        self.console = console
        self.max_scrolls = 100
        self.max_consecutive_errors = 3
        # 从配置中读取弹窗等待时间，默认 20 秒，用于应对 iframe 加载较慢的情况
        settings = config.load_settings()
        self.modal_wait_timeout = float(settings.get("modal_wait", 20.0))
        self.modal_poll_interval = 0.2
        self.scroll_delay = float(settings.get("scroll_delay", 1.0))
        self.template_term = (settings.get("template_term") or "Commission Tier Terms").strip()
        self.counted_attr = 'data-impact-rpa-counted'
        self.clicked_attr = 'data-impact-rpa-clicked'
    
    def send_proposals(self, max_count: int = 10, template_content: str | None = None) -> int:
        """
        循环点击页面上所有的 Send Proposal 按钮
        
        Args:
            max_count: 最大发送数量
            
        Returns:
            实际发送的数量
        """
        # 等待用户操作完成
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
        
        logger.info(f"开始发送 Send Proposal，目标数量: {max_count}")

        if template_content is None:
            template_content = self.template_manager.get_active_template()
        
        clicked_count = 0
        total_scrolls = 0
        consecutive_errors = 0
        pending_batch_buttons = 0
        total_detected_buttons = 0
        
        self.console.print(f"\n[bold cyan]开始循环点击 Send Proposal 按钮 (目标: {max_count} 个)...[/bold cyan]")
        
        while total_scrolls < self.max_scrolls:
            # 检查是否需要重连
            if consecutive_errors >= self.max_consecutive_errors:
                self.console.print("[yellow]连续多次错误，尝试重新连接浏览器...[/yellow]")
                if self.browser.reconnect():
                    consecutive_errors = 0
                    time.sleep(1)
                else:
                    # 记录重连失败的异常
                    exception_handler.log_exception(
                        Exception("浏览器重连失败"),
                        context={
                            "consecutive_errors": consecutive_errors,
                            "total_scrolls": total_scrolls,
                            "clicked_count": clicked_count
                        },
                        send_notification=True
                    )
                    self.console.print("[red]重连失败，停止执行[/red]")
                    break
            
            try:
                # 查找当前可见的所有 Send Proposal 按钮
                buttons = self.browser.find_elements('css:button[data-testid="uicl-button"]')
                
                if buttons is None:
                    consecutive_errors += 1
                    if self.browser.reconnect():
                        consecutive_errors = 0
                        time.sleep(1)
                    continue
                
                send_proposal_buttons = []
                for btn in buttons:
                    if not btn:
                        continue
                    if 'Send Proposal' in (btn.text or ''):
                        send_proposal_buttons.append(btn)
                
                available_buttons = []
                newly_counted = 0
                for btn in send_proposal_buttons:
                    if btn.attr(self.clicked_attr) == 'true':
                        continue
                    if btn.attr(self.counted_attr) != 'true':
                        if self._mark_button_state(btn, self.counted_attr):
                            pending_batch_buttons += 1
                            total_detected_buttons += 1
                            newly_counted += 1
                    available_buttons.append(btn)
                
                if newly_counted > 0:
                    self.console.print(
                        f"[dim]检测到新按钮 {newly_counted} 个，当前批次待发送 {pending_batch_buttons} 个（累计 {total_detected_buttons} 个）[/dim]"
                    )
                    logger.debug(
                        f"新增 {newly_counted} 个 Send Proposal 按钮，当前批次待发送 {pending_batch_buttons} 个"
                    )
                
                if not available_buttons:
                    if pending_batch_buttons <= 0:
                        logger.debug("当前页面没有未发送的 Send Proposal 按钮，滚动加载更多...")
                        if not self.browser.scroll_down(500):
                            consecutive_errors += 1
                            continue
                        time.sleep(self.scroll_delay)
                        total_scrolls += 1
                        continue
                    else:
                        logger.debug("存在待发送计数但未找到按钮，重置计数以避免阻塞")
                        pending_batch_buttons = 0
                        continue
                
                send_proposal_buttons = available_buttons
                
                # 重置连续错误计数
                consecutive_errors = 0
                
                # 遍历当前可见的按钮并点击
                should_scroll_after_batch = False
                for btn in send_proposal_buttons:
                    if clicked_count >= max_count:
                        logger.info(f"已达到目标数量 {max_count}，停止发送")
                        self.console.print(f"\n[bold green]✓ 已达到目标数量 {max_count}，停止发送[/bold green]")
                        self.console.print(f"\n[bold cyan]===== 完成！共发送了 {clicked_count} 个 Send Proposal =====[/bold cyan]")
                        return clicked_count
                    
                    try:
                        selected_tab = self._get_selected_tab_value(btn)
                        
                        parent = btn.parent()
                        for _ in range(10):
                            if parent:
                                try:
                                    self.browser.scroll_to_element(parent)
                                    time.sleep(0.2)
                                    parent.hover()
                                    time.sleep(0.3)
                                    
                                    if not self.browser.click(btn):
                                        raise Exception("点击按钮失败")
                                    
                                    clicked_count += 1
                                    logger.info(f"[{clicked_count}/{max_count}] 已点击 Send Proposal 按钮 (类别: {selected_tab})")
                                    self.console.print(f"[green]✓ [{clicked_count}/{max_count}][/green] 已点击 Send Proposal 按钮 [dim](类别: {selected_tab})[/dim]")
                                    time.sleep(0.5)
                                    self._mark_button_state(btn, self.clicked_attr)
                                    if pending_batch_buttons > 0:
                                        pending_batch_buttons = max(pending_batch_buttons - 1, 0)
                                    if pending_batch_buttons == 0:
                                        should_scroll_after_batch = True
                                    
                                    self._handle_proposal_modal(selected_tab, template_content)
                                    break
                                except Exception as e:
                                    error_msg = str(e).lower()
                                    if 'disconnect' in error_msg or 'context' in error_msg or 'target closed' in error_msg:
                                        raise
                                    parent = parent.parent()
                            else:
                                break
                    except Exception as e:
                        error_msg = str(e).lower()
                        if 'disconnect' in error_msg or 'context' in error_msg or 'target closed' in error_msg or 'no such' in error_msg:
                            logger.warning(f"页面可能已刷新: {e}")
                            self.console.print(f"[yellow]⚠ 页面可能已刷新，尝试重连...[/yellow]")
                            consecutive_errors += 1
                            break
                        else:
                            logger.error(f"点击按钮时出错: {e}")
                            self.console.print(f"[red]✗ 点击按钮时出错: {e}[/red]")
                        continue
                
                if clicked_count >= max_count:
                    break
                
                if should_scroll_after_batch:
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
                    logger.error(f"循环中出错: {e}")
                    consecutive_errors += 1
        
        logger.info(f"发送完成，共发送 {clicked_count} 个 Send Proposal")
        self.console.print(f"\n[bold cyan]===== 完成！共发送了 {clicked_count} 个 Send Proposal =====[/bold cyan]")
        return clicked_count
    
    def _get_selected_tab_value(self, btn) -> str:
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
            print(f"  -> 获取 selected-tab 失败: {e}")
        return None
    
    def _handle_proposal_modal(self, selected_tab: str = None, template_content: str = "") -> bool:
        """处理 Proposal 弹窗"""
        try:
            iframe = self._wait_for_modal_iframe()
            if not iframe:
                print("  -> 未找到弹窗 iframe")
                return False
            
            self._select_template_term(iframe, self.template_term)
            
            if selected_tab:
                self._input_tag_and_select(iframe, selected_tab)
            
            self._select_tomorrow_date(iframe)
            self._input_comment(iframe, template_content)
            self._submit_proposal(iframe)
            return True
            
        except Exception as e:
            error_msg = str(e).lower()
            if 'disconnect' in error_msg or 'context' in error_msg or 'target closed' in error_msg:
                logger.warning(f"处理弹窗时页面断开: {e}")
                raise
            print(f"  -> 处理弹窗失败: {e}")
        return False
    
    def _select_template_term(self, iframe, term_text: str = "Commission Tier Terms") -> bool:
        """选择 Template Term"""
        try:
            desired = (term_text or "Commission Tier Terms").strip()

            term_dropdown = iframe.ele('css:select[data-testid="uicl-select"]', timeout=2)
            
            if term_dropdown:
                try:
                    term_dropdown.select(desired)
                    print(f"  -> 已选择 Template Term: {desired}")
                    time.sleep(0.3)
                    return True
                except Exception as e:
                    print(f"  -> <select> 选择 Template Term 失败，尝试自定义下拉: {e}")
            
            term_section = iframe.ele('text:Template Term', timeout=2)
            if term_section:
                parent = term_section.parent()
                for _ in range(5):
                    if parent:
                        # 优先点中该控件的“下拉触发器”按钮
                        dropdown_btn = parent.ele(
                            'css:button[data-testid="uicl-multi-select-input-button"]',
                            timeout=0.2,
                        )
                        if not dropdown_btn:
                            dropdown_btn = parent.ele(
                                'css:button.iui-multi-select-input-button, button[aria-haspopup="listbox"], button[role="button"]',
                                timeout=0.2,
                            )
                        if not dropdown_btn:
                            dropdown_btn = parent.ele(
                                'css:button, [class*="select"], [class*="dropdown"]',
                                timeout=0.2,
                            )

                        if dropdown_btn:
                            dropdown_btn.click(by_js=True)
                            # 等待下拉列表弹出
                            dropdown = iframe.ele('css:div[data-testid="uicl-dropdown"]', timeout=2)
                            if dropdown:
                                break
                            time.sleep(0.2)
                        parent = parent.parent()
            
            time.sleep(0.3)

            # 优先在当前弹出的 uicl-dropdown 中精确点击目标项（更稳定，避免点到别的区域同名文本）
            dropdown = None
            dropdowns = iframe.eles('css:div[data-testid="uicl-dropdown"]')
            if dropdowns:
                dropdown = dropdowns[-1]

            if dropdown:
                opt = dropdown.ele(
                    f'xpath:.//li[@role="option"][.//*[normalize-space()="{desired}"]]'
                )
                if opt:
                    opt.click(by_js=True)
                    print(f"  -> 已选择 Template Term: {desired}")
                    time.sleep(0.3)
                    return True

            # 备用：直接用文本定位（可能会命中多个，稳定性略低）
            desired_ele = iframe.ele(f'text={desired}', timeout=2)
            if desired_ele:
                desired_ele.click(by_js=True)
                print(f"  -> 已选择 Template Term: {desired}")
                time.sleep(0.3)
                return True

            term_options = iframe.eles('css:div.text-ellipsis')
            for opt in term_options:
                if opt and opt.text and opt.text.strip() == desired:
                    opt.click(by_js=True)
                    print(f"  -> 已选择 Template Term: {desired}")
                    time.sleep(0.3)
                    return True
            
            print(f"  -> 未找到 Template Term 下拉框或选项: {desired}")
            return False
            
        except Exception as e:
            print(f"  -> 选择 Template Term 失败: {e}")
            return False
    
    def _input_tag_and_select(self, iframe, selected_tab: str) -> bool:
        """在 tag-input 中输入值并选择"""
        try:
            search_text = selected_tab.replace(" ", "")
            
            tag_input = iframe.ele('css:input[data-testid="uicl-tag-input-text-input"]', timeout=3)
            if not tag_input:
                raise Exception("未找到 tag-input 输入框")
            
            tag_input.click(by_js=True)
            time.sleep(0.3)
            tag_input.input(search_text)
            print(f"  -> 已输入 tag: {search_text}")
            time.sleep(0.5)
            
            dropdown = iframe.ele('css:[data-testid="uicl-tag-input-dropdown"]', timeout=3)
            if not dropdown:
                raise Exception("未找到下拉列表")
            
            option_div = dropdown.ele('css:div._4-15-1_Baf2T', timeout=2)
            if not option_div:
                options = dropdown.eles('css:li')
                if not options:
                    raise Exception("下拉列表中没有选项")
                option_div = options[0]
            
            option_text = option_div.text.strip()
            print(f"  -> 下拉选项文本: {option_text}")
            
            option_category = re.sub(r'\s*\(\d+\)\s*$', '', option_text).replace(" ", "")
            
            if search_text.lower() != option_category.lower():
                raise Exception(f"输入值 '{search_text}' 与下拉选项 '{option_category}' 不匹配")
            
            option_div.click(by_js=True)
            print(f"  -> 已选择下拉选项: {option_text}")
            time.sleep(0.3)
            return True
            
        except Exception as e:
            print(f"  -> 输入 tag 并选择失败: {e}")
            raise
    
    def _select_tomorrow_date(self, iframe) -> bool:
        """选择明天的日期"""
        try:
            date_btn = iframe.ele('css:button[data-testid="uicl-date-input"]', timeout=3)
            if date_btn:
                date_btn.click(by_js=True)
                print("  -> 已打开日期选择器")
                time.sleep(0.5)
                
                tomorrow = datetime.now() + timedelta(days=1)
                tomorrow_day = str(tomorrow.day)
                
                date_cells = iframe.eles('css:td, .day, [class*="day"], [class*="date"]')
                for cell in date_cells:
                    if cell.text.strip() == tomorrow_day:
                        cell.click(by_js=True)
                        print(f"  -> 已选择日期: {tomorrow.strftime('%Y-%m-%d')}")
                        time.sleep(0.3)
                        return True
                
                date_ele = iframe.ele(f'text={tomorrow_day}', timeout=2)
                if date_ele:
                    date_ele.click(by_js=True)
                    logger.info(f"已选择日期: {tomorrow.strftime('%Y-%m-%d')}")
                    print(f"  -> 已选择日期: {tomorrow.strftime('%Y-%m-%d')}")
                    time.sleep(0.3)
                    return True
                
                logger.warning("未找到明天的日期")
                print("  -> 未找到明天的日期")
                return False
            else:
                logger.warning("未找到日期输入按钮")
                print("  -> 未找到日期输入按钮")
                return False
                
        except Exception as e:
            logger.error(f"选择日期失败: {e}")
            print(f"  -> 选择日期失败: {e}")
        return False
    
    def _input_comment(self, iframe, template_content: str = "") -> bool:
        """填写留言"""
        try:
            template = template_content or self.template_manager.get_active_template()
            if not template:
                logger.warning("留言模板为空")
                print("  -> 留言模板为空")
                return False
            
            textarea = iframe.ele('css:textarea[data-testid="uicl-textarea"]', timeout=3)
            if not textarea:
                textarea = iframe.ele('css:textarea[name="comment"]', timeout=2)
            
            if not textarea:
                logger.warning("未找到留言输入框")
                print("  -> 未找到留言输入框")
                return False
            
            textarea.click(by_js=True)
            time.sleep(0.2)
            textarea.clear()
            textarea.input(template)
            logger.info("已填写留言内容")
            print("  -> 已填写留言内容")
            time.sleep(0.3)
            return True
            
        except Exception as e:
            logger.error(f"填写留言失败: {e}")
            print(f"  -> 填写留言失败: {e}")
        return False
    
    def _submit_proposal(self, iframe) -> bool:
        """提交 Proposal"""
        try:
            submit_btn = iframe.ele('css:button[data-testid="uicl-button"]', timeout=3)
            if submit_btn and 'Send Proposal' in submit_btn.text:
                submit_btn.click(by_js=True)
                logger.info("已点击提交按钮")
                print("  -> 已点击提交按钮")
                time.sleep(1)
                self._click_understand_button(iframe)
                return True
            
            submit_btn = iframe.ele('text:Send Proposal', timeout=2)
            if submit_btn and submit_btn.tag == 'button':
                submit_btn.click(by_js=True)
                print("  -> 已点击提交按钮")
                time.sleep(1)
                self._click_understand_button(iframe)
                return True
            
            buttons = iframe.eles('css:button[data-testid="uicl-button"]')
            for btn in buttons:
                if 'Send Proposal' in btn.text:
                    btn.click(by_js=True)
                    print("  -> 已点击提交按钮")
                    time.sleep(1)
                    self._click_understand_button(iframe)
                    return True
            
            print("  -> 未找到提交按钮")
            return False
            
        except Exception as e:
            print(f"  -> 点击提交按钮失败: {e}")
        return False
    
    def _click_understand_button(self, iframe) -> bool:
        """点击确认按钮"""
        try:
            time.sleep(0.5)
            
            understand_btn = self.browser.find_element('text:I understand', timeout=3, parent=iframe)
            if understand_btn and understand_btn.tag == 'button':
                self.browser.click(understand_btn, by_js=True)
                print("  -> 已点击 'I understand' 确认按钮")
                time.sleep(0.5)
                return True
            
            buttons = self.browser.find_elements('css:button[data-testid="uicl-button"]', parent=iframe)
            for btn in buttons:
                if btn and 'I understand' in (btn.text or ''):
                    self.browser.click(btn, by_js=True)
                    print("  -> 已点击 'I understand' 确认按钮")
                    time.sleep(0.5)
                    return True
            
            understand_btn = self.browser.find_element('text:I understand', timeout=2)
            if understand_btn and understand_btn.tag == 'button':
                self.browser.click(understand_btn, by_js=True)
                print("  -> 已点击 'I understand' 确认按钮")
                time.sleep(0.5)
                return True
            
            print("  -> 未找到 'I understand' 按钮")
            return False
            
        except Exception as e:
            print(f"  -> 点击确认按钮失败: {e}")
        return False

    def _wait_for_modal_iframe(self):
        """等待 Proposal 弹窗 iframe 出现"""
        deadline = time.time() + self.modal_wait_timeout
        while time.time() < deadline:
            iframe = self.browser.find_element(
                'css:iframe[data-testid="uicl-modal-iframe-content"]',
                timeout=0.5
            )
            if iframe:
                return iframe
            time.sleep(self.modal_poll_interval)
        logger.warning("等待 Proposal 弹窗超时")
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


class MenuUI:
    """用户界面类，负责菜单显示和用户交互"""
    
    def __init__(self, config: ConfigManager, template_manager: TemplateManager, console: Console):
        self.config = config
        self.template_manager = template_manager
        self.console = console
    
    def show_main_menu(self) -> str:
        """显示主菜单"""
        self.console.print(Panel.fit(
            "[bold cyan]Impact RPA - Send Proposal 自动化工具[/bold cyan]",
            border_style="cyan"
        ))
        
        choices = [
            questionary.Choice("🚀 开始发送 Send Proposal", value="1"),
            questionary.Choice("📄 预览当前留言模板", value="2"),
            questionary.Choice("✏️  编辑留言模板", value="3"),
            questionary.Choice("🔢 设置发送数量", value="4"),
            questionary.Choice("⚙️  查看当前设置", value="5"),
            questionary.Choice("🚪 退出程序", value="0"),
        ]
        
        return questionary.select(
            "请选择操作:",
            choices=choices,
            style=questionary.Style([
                ('highlighted', 'fg:cyan bold'),
                ('pointer', 'fg:cyan bold'),
            ])
        ).ask()
    
    def preview_template(self):
        """预览当前模板"""
        active_tpl = self.template_manager.get_active_template_info()
        
        if active_tpl and active_tpl.get('content'):
            name = active_tpl.get('name', '未命名')
            self.console.print(Panel(
                active_tpl['content'],
                title=f"[bold green]当前模板: {name}[/bold green]",
                border_style="green"
            ))
        else:
            self.console.print("[yellow]没有激活的模板[/yellow]")
        
        questionary.press_any_key_to_continue("按任意键返回主菜单...").ask()
    
    def edit_template_menu(self):
        """模板编辑菜单"""
        while True:
            choices = [
                questionary.Choice("📋 查看所有模板", value="list"),
                questionary.Choice("👁️  预览当前模板", value="preview"),
                questionary.Choice("✅ 选择激活模板", value="select"),
                questionary.Choice("➕ 添加新模板", value="add"),
                questionary.Choice("✏️  编辑模板", value="edit"),
                questionary.Choice("🗑️  删除模板", value="delete"),
                questionary.Choice("🔙 返回主菜单", value="back"),
            ]
            
            choice = questionary.select(
                "模板管理:",
                choices=choices,
                style=questionary.Style([
                    ('highlighted', 'fg:yellow bold'),
                    ('pointer', 'fg:yellow bold'),
                ])
            ).ask()
            
            if choice is None or choice == 'back':
                break
            elif choice == 'list':
                self._list_all_templates()
            elif choice == 'preview':
                self.preview_template()
            elif choice == 'select':
                self._select_active_template()
            elif choice == 'add':
                self._add_new_template()
            elif choice == 'edit':
                self._edit_existing_template()
            elif choice == 'delete':
                self._delete_template()
    
    def _list_all_templates(self):
        """列出所有模板"""
        data = self.template_manager.load_all()
        templates = data.get('templates', [])
        active_id = data.get('active_template_id')
        
        if not templates:
            self.console.print("[yellow]没有模板[/yellow]")
            questionary.press_any_key_to_continue("按任意键继续...").ask()
            return
        
        table = Table(title="所有留言模板", border_style="blue")
        table.add_column("ID", style="cyan", width=5)
        table.add_column("状态", width=6)
        table.add_column("名称", style="green", width=20)
        table.add_column("内容预览", style="dim", width=50)
        
        for tpl in templates:
            tpl_id = tpl.get('id', 0)
            name = tpl.get('name', '未命名')
            content = tpl.get('content', '')
            preview = content.replace('\n', ' ')[:50]
            if len(content) > 50:
                preview += "..."
            
            status = "[green]✓ 激活[/green]" if tpl_id == active_id else ""
            table.add_row(str(tpl_id), status, name, preview)
        
        self.console.print(table)
        questionary.press_any_key_to_continue("按任意键继续...").ask()
    
    def _select_active_template(self):
        """选择激活模板"""
        data = self.template_manager.load_all()
        templates = data.get('templates', [])
        active_id = data.get('active_template_id')
        
        if not templates:
            self.console.print("[yellow]没有模板可选择[/yellow]")
            return
        
        choices = []
        for tpl in templates:
            tpl_id = tpl.get('id', 0)
            name = tpl.get('name', '未命名')
            mark = " ✓" if tpl_id == active_id else ""
            choices.append(questionary.Choice(f"{name}{mark}", value=tpl_id))
        choices.append(questionary.Choice("🔙 取消", value=None))
        
        selected = questionary.select("选择要激活的模板:", choices=choices).ask()
        
        if selected is not None:
            if self.template_manager.set_active(selected):
                name = next((t.get('name', '未命名') for t in templates if t.get('id') == selected), '未命名')
                self.console.print(f"[bold green]✓ 已激活模板: {name}[/bold green]")
    
    def _add_new_template(self):
        """添加新模板"""
        name = questionary.text("请输入模板名称 (可选):", default="").ask()
        if name is None:
            return
        
        self.console.print("\n[bold]请选择模板内容的输入方式:[/bold]")
        content = self._get_multiline_input()
        
        if not content or not content.strip():
            self.console.print("[yellow]模板内容为空，未保存[/yellow]")
            return
        
        self.console.print(Panel(content, title="[bold yellow]新模板预览[/bold yellow]", border_style="yellow"))
        
        if not questionary.confirm("确认保存?", default=True).ask():
            self.console.print("[yellow]已取消[/yellow]")
            return
        
        activate = questionary.confirm("是否将此模板设为当前激活模板?", default=True).ask()
        
        if self.template_manager.add_template(name, content, activate):
            self.console.print(f"[bold green]✓ 模板已保存[/bold green]")
        else:
            self.console.print("[bold red]✗ 保存失败[/bold red]")
    
    def _edit_existing_template(self):
        """编辑现有模板"""
        data = self.template_manager.load_all()
        templates = data.get('templates', [])
        
        if not templates:
            self.console.print("[yellow]没有模板可编辑[/yellow]")
            return
        
        choices = []
        for tpl in templates:
            tpl_id = tpl.get('id', 0)
            name = tpl.get('name', '未命名')
            choices.append(questionary.Choice(f"{name} (ID: {tpl_id})", value=tpl_id))
        choices.append(questionary.Choice("🔙 取消", value=None))
        
        selected_id = questionary.select("选择要编辑的模板:", choices=choices).ask()
        if selected_id is None:
            return
        
        tpl = next((t for t in templates if t.get('id') == selected_id), None)
        if tpl is None:
            self.console.print("[red]模板不存在[/red]")
            return
        
        edit_choices = [
            questionary.Choice("📝 编辑名称", value="name"),
            questionary.Choice("📄 编辑内容", value="content"),
            questionary.Choice("🔙 取消", value=None),
        ]
        
        edit_choice = questionary.select("选择要编辑的内容:", choices=edit_choices).ask()
        
        if edit_choice is None:
            return
        elif edit_choice == "name":
            new_name = questionary.text("请输入新的模板名称:", default=tpl.get('name', '')).ask()
            if new_name:
                if self.template_manager.update_template(selected_id, name=new_name):
                    self.console.print(f"[bold green]✓ 模板名称已更新为: {new_name}[/bold green]")
        elif edit_choice == "content":
            self.console.print("[bold]当前内容:[/bold]")
            self.console.print(Panel(tpl.get('content', ''), border_style="dim"))
            
            self.console.print("\n[bold]请选择新内容的输入方式:[/bold]")
            new_content = self._get_multiline_input()
            
            if new_content and new_content.strip():
                self.console.print(Panel(new_content, title="[bold yellow]新内容预览[/bold yellow]", border_style="yellow"))
                if questionary.confirm("确认保存?", default=True).ask():
                    if self.template_manager.update_template(selected_id, content=new_content):
                        self.console.print("[bold green]✓ 模板内容已更新[/bold green]")
            else:
                self.console.print("[yellow]内容为空，未更新[/yellow]")
    
    def _delete_template(self):
        """删除模板"""
        data = self.template_manager.load_all()
        templates = data.get('templates', [])
        active_id = data.get('active_template_id')
        
        if not templates:
            self.console.print("[yellow]没有模板可删除[/yellow]")
            return
        
        if len(templates) == 1:
            self.console.print("[yellow]至少需要保留一个模板[/yellow]")
            return
        
        choices = []
        for tpl in templates:
            tpl_id = tpl.get('id', 0)
            name = tpl.get('name', '未命名')
            mark = " [激活]" if tpl_id == active_id else ""
            choices.append(questionary.Choice(f"{name}{mark} (ID: {tpl_id})", value=tpl_id))
        choices.append(questionary.Choice("🔙 取消", value=None))
        
        selected_id = questionary.select("选择要删除的模板:", choices=choices).ask()
        if selected_id is None:
            return
        
        tpl_name = next((t.get('name', '未命名') for t in templates if t.get('id') == selected_id), '未命名')
        
        if not questionary.confirm(f"确认删除模板 '{tpl_name}'?", default=False).ask():
            self.console.print("[yellow]已取消[/yellow]")
            return
        
        if self.template_manager.delete_template(selected_id):
            self.console.print(f"[bold green]✓ 模板 '{tpl_name}' 已删除[/bold green]")
    
    def _get_multiline_input(self) -> str:
        """获取多行输入"""
        choices = [
            questionary.Choice("📋 从剪贴板粘贴", value="clipboard"),
            questionary.Choice("⌨️  手动输入（输入 END 结束）", value="manual"),
            questionary.Choice("🔙 取消", value="cancel"),
        ]
        
        method = questionary.select("选择输入方式:", choices=choices).ask()
        
        if method is None or method == "cancel":
            return None
        
        if method == "clipboard":
            try:
                content = pyperclip.paste()
                if content and content.strip():
                    self.console.print("\n[bold green]已从剪贴板读取内容：[/bold green]")
                    self.console.print(Panel(content, border_style="green"))
                    if questionary.confirm("确认使用此内容?", default=True).ask():
                        return content
                    return None
                else:
                    self.console.print("[yellow]剪贴板为空[/yellow]")
                    return None
            except Exception as e:
                self.console.print(f"[red]读取剪贴板失败: {e}[/red]")
                return None
        else:
            self.console.print("[cyan]请输入内容（输入单独一行 'END' 结束）:[/cyan]")
            lines = []
            while True:
                try:
                    line = input()
                    if line.strip() == 'END':
                        break
                    lines.append(line)
                except EOFError:
                    break
            return '\n'.join(lines) if lines else None
    
    def set_proposal_count(self):
        """设置发送数量"""
        settings = self.config.load_settings()
        self.console.print(f"[cyan]当前设置的发送数量: [bold]{settings['max_proposals']}[/bold][/cyan]")
        
        new_count = questionary.text(
            "请输入新的发送数量:",
            default=str(settings['max_proposals']),
            validate=lambda x: x.isdigit() and int(x) > 0 or "请输入大于0的数字"
        ).ask()
        
        if new_count:
            settings['max_proposals'] = int(new_count)
            self.config.save_settings(settings)
            self.console.print(f"[bold green]✓ 发送数量已设置为: {new_count}[/bold green]")
    
    def view_settings(self):
        """查看当前设置"""
        settings = self.config.load_settings()
        
        table = Table(title="当前设置", border_style="blue")
        table.add_column("设置项", style="cyan")
        table.add_column("值", style="green")
        
        table.add_row("发送数量上限", str(settings['max_proposals']))
        table.add_row("滚动延迟", f"{settings['scroll_delay']} 秒")
        table.add_row("点击延迟", f"{settings['click_delay']} 秒")
        table.add_row("弹窗等待", f"{settings['modal_wait']} 秒")
        
        self.console.print(table)
        questionary.press_any_key_to_continue("按任意键返回主菜单...").ask()


class ImpactRPA:
    """Impact RPA 主应用类"""
    
    def __init__(self):
        self.console = Console()
        self.config = ConfigManager()
        self.template_manager = TemplateManager(self.config)
        self.browser = BrowserManager(self.console)
        self.proposal_sender = ProposalSender(self.browser, self.template_manager, self.console, self.config)
        self.menu = MenuUI(self.config, self.template_manager, self.console)
    
    def start(self):
        """启动应用"""
        # 初始化浏览器
        if not self.browser.init():
            self.console.print("[red]无法连接浏览器，请确保浏览器已打开[/red]")
            return
        
        self._main_loop()
    
    def _main_loop(self):
        """主循环"""
        while True:
            choice = self.menu.show_main_menu()
            
            if choice is None:
                self.console.print("\n[yellow]已取消[/yellow]")
                break
            elif choice == '1':
                self._start_send_proposals()
            elif choice == '2':
                self.menu.preview_template()
            elif choice == '3':
                self.menu.edit_template_menu()
            elif choice == '4':
                self.menu.set_proposal_count()
            elif choice == '5':
                self.menu.view_settings()
            elif choice == '0':
                self.console.print("\n[bold cyan]感谢使用，再见！👋[/bold cyan]")
                break
    
    def _start_send_proposals(self):
        """开始发送 Proposal"""
        if not self.browser.is_connected():
            if not self.browser.init():
                self.console.print("[red]无法连接浏览器，请确保浏览器已打开[/red]")
                return
        
        settings = self.config.load_settings()
        max_count = settings['max_proposals']
        
        self.console.print(f"\n[cyan]准备发送 [bold]{max_count}[/bold] 个 Send Proposal[/cyan]")
        
        template = self.template_manager.get_active_template()
        if not template:
            self.console.print("[bold yellow]⚠️  警告: 留言模板为空！[/bold yellow]")
            if not questionary.confirm("是否继续?", default=False).ask():
                return
        else:
            self.console.print("\n[bold]当前留言模板预览:[/bold]")
            self.console.print(Panel(template, border_style="dim"))
        
        if not questionary.confirm(f"确认开始发送 {max_count} 个 Proposal?", default=False).ask():
            self.console.print("[yellow]已取消[/yellow]")
            return
        
        self.proposal_sender.send_proposals(max_count, template)


if __name__ == "__main__":
    app = ImpactRPA()
    app.start()
