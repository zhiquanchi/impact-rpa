from DrissionPage import Chromium
from DrissionPage.errors import ElementNotFoundError, PageDisconnectedError, ContextLostError
import time
import os
import json
import re
from dataclasses import dataclass
from datetime import datetime, timedelta
from loguru import logger
import questionary
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
import pyperclip
from exception_handler import exception_handler
import inspect


class ConfigManager:
    """配置管理类，负责处理所有配置文件的读写"""
    
    def __init__(self, base_dir: str | None = None):
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
            # 开发测试模式：不会真正点击 Send Proposal 按钮，仅模拟流程
            "dry_run": False,
            # Proposal 弹窗内的 Template Term 下拉默认选择项
            # 例如："Commission Tier Terms" / "Public Terms" / "Ulanzi Terms"
            "template_term": "Commission Tier Terms",
            # 是否在 Proposal 弹窗内输入 Partner Groups 标签
            "input_partner_groups_tag": True,
            # 发生异常时是否截图（页面+尽可能元素），截图保存在 logs/screenshots
            "screenshot_on_error": True,
            # 是否整页截图（True=整页，False=仅可视区域；整页对浏览器内核版本有要求且更慢）
            "screenshot_full_page": False,
            # 视觉 RPA 配置（兼容 OpenAI SDK 格式的 VL LLM）
            "vision_rpa": {
                "enabled": False,  # 是否启用视觉 RPA
                "api_key": "",  # API Key，也可通过环境变量 VL_API_KEY 设置
                "base_url": "",  # API 地址，也可通过环境变量 VL_BASE_URL 设置
                "model": "gpt-4o",  # 模型名称
                "max_tokens": 1024,
                "temperature": 0.1,
                "timeout": 30,
                # 浏览器 UI 偏移（标签栏+地址栏高度，单位：像素）
                # Chrome/Edge 通常约为 100-150px，可根据实际情况调整
                "browser_ui_offset_x": 0,  # 内容区域左侧偏移
                "browser_ui_offset_y": 0,  # 内容区域顶部偏移（约 100-150px）
            },
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
            level='DEBUG',
            format='{time:YYYY-MM-DD HH:mm:ss} | {level} | {name}:{function}:{line} | {message}',
            backtrace=True,
            diagnose=True,
            encoding='utf-8',
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
    
    def get_active_template_info(self) -> dict | None:
        """获取当前激活的模板完整信息"""
        data = self.load_all()
        active_id = data.get('active_template_id')
        for tpl in data.get('templates', []):
            if tpl.get('id') == active_id:
                return tpl
        return None
    
    def get_next_id(self, data: dict | None = None) -> int:
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
    
    def update_template(self, template_id: int, name: str | None = None, content: str | None = None) -> bool:
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
    
    def __init__(self, console: Console, config: ConfigManager | None = None):
        self.browser = None
        self.tab = None
        self.console = console
        self.max_retries = 3
        self.config = config

        base_dir = None
        try:
            base_dir = getattr(config, 'base_dir', None)
        except Exception:
            base_dir = None
        self.base_dir = base_dir or os.path.dirname(__file__)

        settings = {}
        try:
            if config:
                settings = config.load_settings() or {}
        except Exception:
            settings = {}

        self.screenshot_on_error = bool(settings.get('screenshot_on_error', True))
        self.screenshot_full_page = bool(settings.get('screenshot_full_page', False))
        self.screenshot_dir = os.path.join(self.base_dir, 'logs', 'screenshots')
        os.makedirs(self.screenshot_dir, exist_ok=True)
        self._last_screenshot_ts = 0.0
        self._screenshot_min_interval = 1.5
    
    def init(self) -> bool:
        """初始化或重新连接浏览器"""
        try:
            # 尝试多种方式连接浏览器
            # 方式1: 默认连接（自动查找浏览器）
            try:
                self.browser = Chromium()
                try:
                    impact_tab = self.browser.get_tab(url='https://app.impact.com/secure/')
                except Exception:
                    impact_tab = None
                self.tab = impact_tab or self.browser.latest_tab
                if self.tab:
                    logger.info("浏览器连接成功（默认方式）")
                    return True
            except Exception as e1:
                logger.debug(f"默认连接方式失败: {e1}")
            
            # 方式2: 尝试连接已存在的浏览器（不启动新实例）
            try:
                # 某些 DrissionPage 版本不接受 None，这里直接使用默认构造尝试连接现有实例
                self.browser = Chromium()
                self.tab = self.browser.latest_tab
                if self.tab:
                    logger.info("浏览器连接成功（连接现有浏览器）")
                    return True
            except Exception as e2:
                logger.debug(f"连接现有浏览器失败: {e2}")
            
            # 方式3: 尝试通过浏览器 ID 连接
            try:
                from DrissionPage import ChromiumOptions
                # 不启动新浏览器，只连接现有实例
                options = ChromiumOptions()
                self.browser = Chromium(addr_or_opts=options)
                self.tab = self.browser.latest_tab
                if self.tab:
                    logger.info("浏览器连接成功（通过选项）")
                    return True
            except Exception as e3:
                logger.debug(f"通过选项连接失败: {e3}")
            
            # 如果所有方式都失败
            logger.error("所有浏览器连接方式均失败")
            self.console.print("[yellow]提示：请确保浏览器已打开，并允许 DrissionPage 连接[/yellow]")
            self.console.print("[yellow]或者手动启动浏览器后重试[/yellow]")
            self.console.print("[dim]常见解决方案：[/dim]")
            self.console.print("[dim]1. 确保 Chrome/Edge 浏览器已打开[/dim]")
            self.console.print("[dim]2. 检查是否有防火墙/安全软件阻止连接[/dim]")
            self.console.print("[dim]3. 尝试以管理员权限运行[/dim]")
            self.console.print("[dim]4. 如果使用 Chrome，尝试关闭所有 Chrome 窗口后重新打开[/dim]")
            return False
            
        except Exception as e:
            logger.error(f"浏览器连接失败: {e}")
            import traceback
            logger.debug(traceback.format_exc())
            return False
    
    def reconnect(self) -> bool:
        """重新连接浏览器"""
        self.console.print("[yellow]检测到页面断开，正在重新连接...[/yellow]")
        logger.warning("页面断开，尝试重新连接浏览器")
        
        for i in range(self.max_retries):
            try:
                self.browser = Chromium()
                try:
                    impact_tab = self.browser.get_tab(url='https://app.impact.com/secure/')
                except Exception:
                    impact_tab = None
                self.tab = impact_tab or self.browser.latest_tab
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

    def _get_page_context(self) -> dict:
        """获取当前页面上下文信息（用于异常日志定位问题）。"""
        ctx = {}
        try:
            if self.tab:
                try:
                    ctx["url"] = self.tab.url
                except Exception:
                    pass
                try:
                    # 某些版本可能没有 title 属性，失败则忽略
                    ctx["title"] = getattr(self.tab, "title", None)
                except Exception:
                    pass
        except Exception:
            pass
        return ctx

    def _ele_brief(self, ele) -> dict | None:
        """提取元素的关键信息，避免日志过大。"""
        if not ele:
            return None
        info = {}
        try:
            info["tag"] = getattr(ele, "tag", None)
        except Exception:
            pass

        def _attr(name: str):
            try:
                return ele.attr(name)
            except Exception:
                return None

        for k in ("id", "class", "data-testid", "data-pa-testid", "role", "name"):
            v = _attr(k)
            if v:
                info[k] = v
        try:
            t = (ele.text or "").strip()
            if t:
                info["text"] = t[:200]
        except Exception:
            pass
        return info or None

    def _caller_brief(self) -> dict | None:
        """返回调用 BrowserManager 方法的业务函数位置，便于快速定位。"""
        try:
            stack = inspect.stack()
            # [0] 当前方法，[1] BrowserManager 内部调用者，[2] 通常是业务层
            if len(stack) > 2:
                frame = stack[2]
                return {"file": frame.filename, "line": frame.lineno, "function": frame.function}
        except Exception:
            return None
        return None

    def _capture_screenshot(self, reason: str, element=None) -> dict | None:
        """按 DrissionPage 文档调用 get_screenshot() 保存截图，并返回路径信息。"""
        if not self.screenshot_on_error:
            return None
        if not self.tab:
            return None
        now = time.time()
        if now - self._last_screenshot_ts < self._screenshot_min_interval:
            return None
        self._last_screenshot_ts = now

        def _safe_name(s: str) -> str:
            s = (s or 'error').strip()
            s = re.sub(r'[^a-zA-Z0-9\-_.]+', '_', s)
            return s[:80] if len(s) > 80 else s

        stamp = datetime.now().strftime('%Y%m%d_%H%M%S_%f')
        tag = _safe_name(reason)
        info = {"reason": reason}
        try:
            page_name = f"page_{stamp}_{tag}.jpg"
            page_path = self.tab.get_screenshot(
                path=self.screenshot_dir,
                name=page_name,
                full_page=self.screenshot_full_page,
            )
            info["page"] = page_path
        except Exception as e:
            info["page_error"] = str(e)

        if element:
            try:
                ele_name = f"ele_{stamp}_{tag}.jpg"
                ele_path = element.get_screenshot(path=self.screenshot_dir, name=ele_name)
                info["element"] = ele_path
            except Exception as e:
                info["element_error"] = str(e)
        return info
    
    def find_element(self, locator: str, timeout: float = 3.0, parent=None):
        """安全地查找元素"""
        target = parent if parent else self.tab
        try:
            element = target.ele(locator, timeout=timeout)
            return element
        except (ElementNotFoundError, PageDisconnectedError, ContextLostError) as e:
            logger.warning(f"查找元素失败: {e}")
            shot = self._capture_screenshot(f"find_element_{locator}")
            exception_handler.log_exception(
                e,
                context={
                    "operation": "查找元素",
                    "locator": locator,
                    "timeout": timeout
                    ,"page": self._get_page_context()
                    ,"parent": self._ele_brief(parent)
                    ,"caller": self._caller_brief()
                    ,"screenshot": shot
                }
            )
            return None
        except Exception as e:
            error_msg = str(e).lower()
            if 'disconnect' in error_msg or 'context' in error_msg or 'target closed' in error_msg:
                logger.warning(f"页面可能已断开: {e}")
                shot = self._capture_screenshot(f"find_element_disconnect_{locator}")
                exception_handler.log_exception(
                    e,
                    context={
                        "operation": "查找元素",
                        "locator": locator,
                        "timeout": timeout,
                        "error_type": "页面断开"
                        ,"page": self._get_page_context()
                        ,"parent": self._ele_brief(parent)
                        ,"caller": self._caller_brief()
                        ,"screenshot": shot
                    }
                )
                return None
            raise
    
    def find_elements(self, locator: str, timeout: float = 3.0, parent=None) -> list:
        """安全地查找多个元素"""
        target = parent if parent else self.tab
        try:
            elements = target.eles(locator, timeout=timeout)
            return elements if elements else []
        except (ElementNotFoundError, PageDisconnectedError, ContextLostError) as e:
            logger.warning(f"查找元素失败: {e}")
            shot = self._capture_screenshot(f"find_elements_{locator}")
            exception_handler.log_exception(
                e,
                context={
                    "operation": "查找多个元素",
                    "locator": locator,
                    "timeout": timeout
                    ,"page": self._get_page_context()
                    ,"parent": self._ele_brief(parent)
                    ,"caller": self._caller_brief()
                    ,"screenshot": shot
                }
            )
            return []
        except Exception as e:
            error_msg = str(e).lower()
            if 'disconnect' in error_msg or 'context' in error_msg or 'target closed' in error_msg:
                logger.warning(f"页面可能已断开: {e}")
                shot = self._capture_screenshot(f"find_elements_disconnect_{locator}")
                exception_handler.log_exception(
                    e,
                    context={
                        "operation": "查找多个元素",
                        "locator": locator,
                        "timeout": timeout,
                        "error_type": "页面断开"
                        ,"page": self._get_page_context()
                        ,"parent": self._ele_brief(parent)
                        ,"caller": self._caller_brief()
                        ,"screenshot": shot
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
            error_msg = str(e).lower()
            if 'norect' in error_msg or '没有位置' in error_msg:
                try:
                    self.scroll_to_element(element)
                    time.sleep(0.3)
                    element.click(by_js=True)
                    return True
                except Exception:
                    pass
            
            logger.warning(f"点击元素失败: {e}")
            shot = self._capture_screenshot("click", element=element)
            exception_handler.log_exception(
                e,
                context={
                    "operation": "点击元素",
                    "by_js": by_js,
                    "page": self._get_page_context(),
                    "element": self._ele_brief(element),
                    "caller": self._caller_brief(),
                    "screenshot": shot,
                },
            )
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
            shot = self._capture_screenshot(f"scroll_down_{pixels}")
            exception_handler.log_exception(
                e,
                context={
                    "operation": "向下滚动",
                    "pixels": pixels,
                    "page": self._get_page_context(),
                    "caller": self._caller_brief(),
                    "screenshot": shot,
                },
            )
            return False
    
    def scroll_to_element(self, element) -> bool:
        """滚动到元素可见"""
        try:
            self.tab.scroll.to_see(element)
            return True
        except Exception as e:
            logger.warning(f"滚动到元素失败: {e}")
            shot = self._capture_screenshot("scroll_to_element", element=element)
            exception_handler.log_exception(
                e,
                context={
                    "operation": "滚动到元素",
                    "page": self._get_page_context(),
                    "element": self._ele_brief(element),
                    "caller": self._caller_brief(),
                    "screenshot": shot,
                },
            )
            return False
    
    def navigate(self, url: str) -> bool:
        """导航到指定URL"""
        try:
            self.tab.get(url)
            return self.wait_for_page_ready()
        except Exception as e:
            logger.error(f"导航失败: {e}")
            return False


class DatePickerResult:
    """日期选择结果"""
    
    def __init__(self, success: bool, method: str | None = None, error: str | None = None):
        self.success = success
        self.method = method  # 'element_click' | 'vision_rpa'
        self.error = error


class DatePicker:
    """
    日期选择器类，支持多种选择策略：
    1. 元素点击方式 (element_click)
    2. 视觉 RPA 方式 (vision_rpa) - 需要外部实现
    """
    # 日期触发器/输入框选择器（用于“打开日期选择器”）
    # 注意：这里不做 JS 写值，仅用于点击打开弹层
    DATE_INPUT_SELECTORS = [
        'css:button[data-testid="uicl-date-input"]',
    ]
    
    # 禁用状态的类名关键词（尽量通用；站点/组件不同会有差异）
    DISABLED_KEYWORDS = (
        # 通用
        'disabled', 'today', 'current',
        # 通用
        'inactive', 'outside', 'other', 'old', 'muted',
        'adjacent', 'faded', 'dim', 'grey', 'gray', 'secondary',
        'prev-month', 'next-month', 'other-month', 'not-current',
        'outsidemonth', 'notcurrent', 'grayed', 'unavailable',
    )
    
    # 月份切换按钮选择器
    PREV_MONTH_SELECTORS = [
        'css:button[aria-label="Previous"]',
    ]
    
    NEXT_MONTH_SELECTORS = [
        'css:button[aria-label="Next"]',
    ]
    
    # 日期单元格选择器
    DATE_CELL_SELECTORS = [
        'css:td, .day, [class*="day"], [class*="date"]',
    ]
    
    def __init__(self, console: Console | None = None):
        self.console = console or Console()
        self._vision_handler = None  # 视觉 RPA 处理器，由外部注入
    
    def set_vision_handler(self, handler):
        """
        设置视觉 RPA 处理器
        
        handler 应该是一个可调用对象，签名为:
        handler(context, target_date: datetime, screenshot_path: str = None) -> bool
        """
        self._vision_handler = handler
    
    def select_date(
        self,
        context,  # iframe 或 page 对象
        target_date: datetime,
        strategies: list | None = None,
        open_picker: bool = True,
    ) -> DatePickerResult:
        """
        选择指定日期
        
        Args:
            context: iframe 或 page 对象
            target_date: 目标日期
            strategies: 使用的策略列表，默认 ['element_click', 'vision_rpa']
            open_picker: 是否先打开日期选择器
            
        Returns:
            DatePickerResult: 选择结果
        """
        if strategies is None:
            # Impact：只使用真实点击（element_click）；必要时可启用 vision_rpa 兜底
            strategies = ['element_click']
        
        target_day = str(target_date.day)
        target_iso = target_date.strftime('%Y-%m-%d')
        
        last_error = None
        
        for strategy in strategies:
            try:
                if strategy == 'element_click':
                    success = self._select_by_element_click(
                        context=context,
                        target_date=target_date,
                        target_day=target_day,
                        target_iso=target_iso,
                        open_picker=open_picker,
                    )
                    if success:
                        return DatePickerResult(success=True, method='element_click')
                
                elif strategy == 'vision_rpa':
                    success = self._select_by_vision_rpa(context, target_date)
                    if success:
                        return DatePickerResult(success=True, method='vision_rpa')
                
            except Exception as e:
                last_error = str(e)
                logger.warning(f"日期选择策略 {strategy} 失败: {e}")
                continue
        
        return DatePickerResult(
            success=False,
            error=last_error or f"所有策略均失败，无法选择日期: {target_iso}"
        )
    
    def _select_by_element_click(
        self,
        context,
        target_date: datetime,
        target_day: str,
        target_iso: str,
        open_picker: bool = True,
    ) -> bool:
        """通过元素点击方式选择日期"""
        # 打开日期选择器
        if open_picker:
            if not self._open_date_picker(context):
                return False

        # Impact 专用快速路径：当前视图直接按日期文本点击，尽量避免复杂遍历
        if self._is_impact_modal_iframe(context):
            if self._try_pick_date_in_view_fast_impact(context, target_day, target_iso):
                return True

        # 计算月份差异
        now = datetime.now()
        months_diff = (target_date.year - now.year) * 12 + (target_date.month - now.month)
        direction = 'next' if months_diff >= 0 else 'prev'

        # 尝试在当前视图或切换月份后找到目标日期
        max_attempts = max(abs(months_diff) + 2, 3)
        # Impact 场景下日期通常在相邻月份内，限制尝试次数以减少多余导航
        if self._is_impact_modal_iframe(context) and max_attempts > 4:
            max_attempts = 4

        for step in range(max_attempts):
            if step > 0:
                if not self._click_month_nav(context, direction, fast_timeout=self._is_impact_modal_iframe(context)):
                    if step == 1 and direction == 'next':
                        if self._click_month_nav(context, 'prev', fast_timeout=self._is_impact_modal_iframe(context)):
                            if self._try_pick_date_in_view(context, target_day, target_iso):
                                return True
                    break
            if self._try_pick_date_in_view(context, target_day, target_iso):
                return True

        logger.warning(f"元素点击方式未找到目标日期: {target_iso}")
        return False
    
    def _select_by_vision_rpa(self, context, target_date: datetime) -> bool:
        """通过视觉 RPA 方式选择日期"""
        if not self._vision_handler:
            logger.debug("未设置视觉 RPA 处理器，跳过此策略")
            return False
        
        try:
            # 截取当前页面截图
            screenshot_path = None
            try:
                screenshot_path = context.get_screenshot(
                    path=os.path.join(os.path.dirname(__file__), 'logs', 'screenshots'),
                    name=f"date_picker_{datetime.now().strftime('%Y%m%d_%H%M%S')}.jpg"
                )
            except Exception as e:
                logger.warning(f"截图失败: {e}")
            
            # 调用视觉处理器
            result = self._vision_handler(context, target_date, screenshot_path)
            if result:
                logger.info(f"已通过视觉 RPA 选择日期: {target_date.strftime('%Y-%m-%d')}")
                return True
        except Exception as e:
            logger.warning(f"视觉 RPA 选择日期失败: {e}")
        
        return False
    
    def _is_impact_modal_iframe(self, context) -> bool:
        """判断是否为 Impact Proposal 弹窗 iframe"""
        try:
            data_testid = (context.attr('data-testid') or '').strip()
            return data_testid == 'uicl-modal-iframe-content'
        except Exception:
            return False

    def _try_pick_date_in_view_fast_impact(
        self,
        context,
        target_day: str,
        target_iso: str,
    ) -> bool:
        """Impact 专用快速路径：按日期文本直接点击"""
        try:
            cells = context.eles('css:td, .day, [class*="day"], [class*="date"]')
        except Exception:
            return False

        if not cells:
            return False

        for cell in cells or []:
            try:
                if (cell.text or '').strip() != target_day:
                    continue
                try:
                    cell.click(by_js=True)
                except Exception:
                    try:
                        cell.click()
                    except Exception:
                        continue
                logger.info(f"已通过快速路径选择日期: {target_iso}")
                time.sleep(0.2)
                return True
            except Exception:
                continue

        return False

    def _open_date_picker(self, context) -> bool:
        """打开日期选择器"""
        is_impact = self._is_impact_modal_iframe(context)
        timeout = 0.5
        if is_impact:
            timeout = 0.2
            # Impact 快速路径：仅用 DevTools 确认的精确选择器，避免遍历多选择器
            try:
                btn = context.ele(self.DATE_INPUT_SELECTORS[0], timeout=0.1)
                if btn:
                    try:
                        btn.click(by_js=True)
                    except Exception:
                        btn.click(by_js=None)
                    logger.info("已打开日期选择器")
                    time.sleep(0.25)
                    return True
            except Exception:
                pass

        for selector in self.DATE_INPUT_SELECTORS:
            try:
                btn = context.ele(selector, timeout=timeout)
                if btn:
                    if is_impact:
                        # Impact 场景：直接点击，避免额外的 clickable 等待
                        try:
                            btn.click(by_js=True)
                        except Exception:
                            btn.click(by_js=None)
                    else:
                        try:
                            btn.wait.clickable()
                        except Exception:
                            pass
                        btn.click(by_js=None)
                    logger.info("已打开日期选择器")
                    time.sleep(0.3 if is_impact else 0.5)
                    return True
            except Exception:
                continue
        
        # Impact 平台兜底：通过 Start Date 标签定位日期按钮
        # 日期按钮显示格式如 "Jan 30, 2026"
        try:
            # 方法1：通过 Start Date 标签向上查找父级中的按钮
            start_date_label = context.ele('text:Start Date', timeout=0.3 if is_impact else 0.5)
            if start_date_label:
                parent = start_date_label.parent()
                for _ in range(5):
                    if parent:
                        # 查找包含年份的按钮
                        current_year = datetime.now().year
                        btns = parent.eles('tag:button', timeout=0.2 if is_impact else 0.3)
                        for btn in btns or []:
                            btn_text = btn.text or ''
                            # 匹配日期格式：月份缩写 + 日 + 年
                            if any(m in btn_text for m in self.IMPACT_DATE_BUTTON_MONTHS):
                                if str(current_year) in btn_text or str(current_year + 1) in btn_text:
                                    btn.click(by_js=True)
                                    logger.info(f"已通过 Start Date 标签打开日期选择器: {btn_text}")
                                    time.sleep(0.3 if is_impact else 0.5)
                                    return True
                        parent = parent.parent()
        except Exception as e:
            logger.debug(f"通过 Start Date 标签查找失败: {e}")
        
        # 方法2：直接查找所有按钮，匹配日期格式
        try:
            current_year = datetime.now().year
            all_buttons = context.eles('tag:button', timeout=0.3 if is_impact else 0.5)
            for btn in all_buttons or []:
                btn_text = btn.text or ''
                if any(m in btn_text for m in self.IMPACT_DATE_BUTTON_MONTHS):
                    if str(current_year) in btn_text or str(current_year + 1) in btn_text:
                        btn.click(by_js=True)
                        logger.info(f"已通过日期格式匹配打开日期选择器: {btn_text}")
                        time.sleep(0.3 if is_impact else 0.5)
                        return True
        except Exception as e:
            logger.debug(f"通过日期格式匹配查找失败: {e}")
        
        logger.warning("未找到日期选择器按钮")
        return False
    
    # Impact 平台专用：日期按钮显示格式中的月份缩写
    IMPACT_DATE_BUTTON_MONTHS = ('Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec')
    
    def _is_disabled(self, ele) -> bool:
        """检查元素是否为禁用状态"""
        try:
            aria_disabled = (ele.attr('aria-disabled') or '').strip().lower()
            if aria_disabled == 'true':
                return True
        except Exception:
            pass
        
        try:
            cls = (ele.attr('class') or '').lower()
            # 通用禁用关键词检查
            disabled_keywords = [k for k in self.DISABLED_KEYWORDS if k not in ('today', 'current')]
            if any(k in cls for k in disabled_keywords):
                return True
            # 单独检查 "new" 以避免误匹配 "renew" 等词
            if ' new ' in f' {cls} ' or cls.startswith('new ') or cls.endswith(' new') or cls == 'new':
                return True
        except Exception:
            pass
        
        try:
            if ele.attr('disabled') is not None:
                return True
        except Exception:
            pass
        
        try:
            for attr_name in ('data-outside', 'data-other-month', 'data-adjacent'):
                val = ele.attr(attr_name)
                if val and val.lower() in ('true', '1', 'yes'):
                    return True
        except Exception:
            pass
        
        return False
    
    def _try_pick_date_in_view(self, context, target_day: str, target_iso: str) -> bool:
        """尝试在当前视图中选择目标日期"""
        date_cells = []
        # 尝试所有选择器
        for selector in self.DATE_CELL_SELECTORS:
            try:
                cells = context.eles(selector)
                if cells:
                    date_cells.extend(cells)
            except Exception:
                continue
        
        if not date_cells:
            return False
        
        # 优先通过属性匹配完整日期
        for cell in date_cells or []:
            try:
                if self._is_disabled(cell):
                    continue
                attrs = []
                for k in ('data-date', 'data-day', 'aria-label', 'title', 'data-testid'):
                    try:
                        v = cell.attr(k)
                        if v:
                            attrs.append(str(v))
                    except Exception:
                        continue
                attrs_text = ' '.join(attrs)
                if target_iso in attrs_text or target_iso.replace('-', '/') in attrs_text:
                    try:
                        cell.wait.clickable()
                    except Exception:
                        pass
                    cell.click(by_js=None)
                    logger.info(f"已选择日期: {target_iso}")
                    time.sleep(0.3)
                    return True
            except Exception:
                continue
        
        # 兜底：按日历格子的文本点击
        for cell in date_cells or []:
            try:
                if self._is_disabled(cell):
                    continue
                if (cell.text or '').strip() != target_day:
                    continue
                try:
                    cell.wait.clickable()
                except Exception:
                    pass
                cell.click(by_js=None)
                logger.info(f"已选择日期: {target_iso}")
                time.sleep(0.3)
                return True
            except Exception:
                continue
        
        return False
    
    def _click_month_nav(self, context, direction: str, fast_timeout: bool = False) -> bool:
        """点击月份导航按钮"""
        selectors = self.PREV_MONTH_SELECTORS if direction == 'prev' else self.NEXT_MONTH_SELECTORS
        timeout = 0.15 if fast_timeout else 0.3
        sleep_after = 0.25 if fast_timeout else 0.4

        for sel in selectors:
            try:
                btn = context.ele(sel, timeout=timeout)
                if btn:
                    try:
                        btn.click(by_js=True)
                        time.sleep(sleep_after)
                        logger.debug(f"成功点击月份切换按钮: {sel}")
                        return True
                    except Exception as e:
                        logger.debug(f"点击月份按钮失败 ({sel}): {e}")
                        continue
            except Exception:
                continue

        # 兜底：通过箭头字符查找
        try:
            header_btns = context.eles('css:button', timeout=0.3 if fast_timeout else 0.5)
            for btn in header_btns or []:
                try:
                    btn_text = (btn.text or '').strip()
                    if len(btn_text) > 10:
                        continue
                    if direction == 'prev' and any(c in btn_text for c in ('←', '<', '‹', '«')):
                        btn.click(by_js=True)
                        time.sleep(sleep_after)
                        return True
                    elif direction == 'next' and any(c in btn_text for c in ('→', '>', '›', '»')):
                        btn.click(by_js=True)
                        time.sleep(sleep_after)
                        return True
                except Exception:
                    continue
        except Exception:
            pass
        
        logger.warning(f"未找到月份切换按钮 (direction={direction})")
        return False


@dataclass(frozen=True)
class SendProposalsResult:
    """send_proposals 执行结果，用于区分「全部完成」与「提前退出」"""

    clicked_count: int
    completed_all: bool


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
        self.input_partner_groups_tag = bool(settings.get("input_partner_groups_tag", True))
        # Partner Groups 相关调试日志开关
        self.partner_groups_debug_logging = bool(settings.get("partner_groups_debug_logging", False))
        # 缓存每个 Partner Group 文本达到唯一匹配所需的最短输入长度
        self._partner_group_prefix_len_cache: dict[str, int] = {}
        self.counted_attr = 'data-impact-rpa-counted'
        self.clicked_attr = 'data-impact-rpa-clicked'
        # TODO: 优化方向 - 在网页上判断联盟客是否已点击过，避免重复处理
        # 可以通过检查页面上是否有已发送的标记、按钮状态变化、或DOM结构变化来判断
        self.dry_run = bool(settings.get("dry_run", False))
        self.config = config
        
        # 初始化日期选择器
        self.date_picker = DatePicker(console)
        
        # 配置视觉 RPA 处理器（如果启用）
        self._setup_vision_rpa(settings)
    
    def _setup_vision_rpa(self, settings: dict):
        """配置视觉 RPA 处理器"""
        vision_config = settings.get("vision_rpa", {})
        if not vision_config.get("enabled"):
            logger.debug("视觉 RPA 未启用")
            return
        
        try:
            from vision_rpa import VisionConfig, VisionDatePickerHandler
            
            # 优先使用配置文件中的设置，其次使用环境变量
            config = VisionConfig(
                api_key=vision_config.get("api_key") or os.getenv("VL_API_KEY") or os.getenv("OPENAI_API_KEY") or "",
                base_url=vision_config.get("base_url") or os.getenv("VL_BASE_URL") or os.getenv("OPENAI_BASE_URL") or "",
                model=vision_config.get("model", "gpt-4o"),
                max_tokens=vision_config.get("max_tokens", 1024),
                temperature=vision_config.get("temperature", 0.1),
                timeout=vision_config.get("timeout", 30),
                browser_ui_offset_x=vision_config.get("browser_ui_offset_x", 0),
                browser_ui_offset_y=vision_config.get("browser_ui_offset_y", 0),
            )
            
            if not config.api_key:
                logger.warning("视觉 RPA 已启用但未配置 API Key")
                return
            
            handler = VisionDatePickerHandler(config=config)
            self.date_picker.set_vision_handler(handler)
            logger.info(f"视觉 RPA 已启用，模型: {config.model}")
            
        except ImportError as e:
            logger.warning(f"视觉 RPA 依赖未安装: {e}")
        except Exception as e:
            logger.error(f"配置视觉 RPA 失败: {e}")

    def _find_send_proposal_buttons(self) -> list:
        """
        在列表页查找可点击的 Send Proposal 按钮（多策略兜底）。

        说明：Impact 的 DOM/测试 id 可能变动，单一 selector 容易导致一直“找不到按钮 → 滚动”。
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
    
    def send_proposals(self, max_count: int = 10, template_content: str | None = None) -> SendProposalsResult:
        """
        循环点击页面上所有的 Send Proposal 按钮
        
        Args:
            max_count: 最大发送数量
            template_content: 留言模板内容，None 时使用当前激活模板
            
        Returns:
            SendProposalsResult(clicked_count, completed_all)。
            completed_all 仅当达到 max_count 时为 True；重连失败等会 raise，不返回。
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
        
        self.console.print(f"\n[bold cyan]开始循环点击 Send Proposal 按钮 (目标: {max_count} 个，最大滚动: {effective_max_scrolls} 次)...[/bold cyan]")
        
        # 循环条件：未达到目标数量 且 未超过最大滚动次数（安全限制）
        while clicked_count < max_count and total_scrolls < effective_max_scrolls:
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
                        # 连续多次空滚动仍未发现新按钮，则提前退出，避免看起来像“卡死/报错”
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
                            f"已发送: {clicked_count}/{max_count}，累计检测到按钮: {total_detected_buttons}）。"
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
                    if clicked_count >= max_count:
                        logger.info(f"已达到目标数量 {max_count}，停止发送")
                        self.console.print(f"\n[bold green]✓ 已达到目标数量 {max_count}，停止发送[/bold green]")
                        self.console.print(f"\n[bold cyan]===== 完成！共发送了 {clicked_count} 个 Send Proposal =====[/bold cyan]")
                        return SendProposalsResult(clicked_count=clicked_count, completed_all=True)
                    
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
                                            except:
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
        在 Creator Search 表格中点击指定行，再点击出现的 Send Proposal 按钮，
        弹窗后的处理与 send_proposals 中点击 Send Proposal 之后一致（_handle_proposal_modal）。

        选择器: #pd-creator-rt-search-ui div.table-body > div:nth-child(N)，N 为行号（从 1 起）。

        Args:
            row_index: 表格行号，对应 div:nth-child(row_index)，从 1 开始。
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
        row_selector = (
            f"#pd-creator-rt-search-ui div.table-body > div:nth-child({row_index})"
        )
        psi_id = None
        creator_name = None
        try:
            row_el = self.browser.find_element(f"css:{row_selector}", timeout=5)
            if not row_el:
                logger.warning(f"未找到表格行: {row_selector}")
                self.console.print(f"[red]未找到表格行 (第 {row_index} 行)[/red]")
                return False, None, None, False
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
        
        while sent_count < max_count:
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
            
            if self.input_partner_groups_tag and selected_tab:
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
            logger.error(f"处理弹窗失败: {e}")
        return False
    
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
            opened = False
            
            # 尝试通过 Template Term 标签找到下拉按钮
            term_section = iframe.ele('text:Template Term', timeout=2)
            if term_section:
                parent = term_section.parent()
                for _ in range(5):
                    if parent:
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
                            dropdown = iframe.ele('css:div[data-testid="uicl-dropdown"]', timeout=2)
                            if dropdown:
                                opened = True
                                break
                            time.sleep(0.2)
                        parent = parent.parent()
            
            # 兜底：直接找触发器按钮
            if not opened:
                try:
                    dropdown_btn = iframe.ele('css:button[data-testid="uicl-multi-select-input-button"]', timeout=0.5)
                    if not dropdown_btn:
                        dropdown_btn = iframe.ele('css:.iui-multi-select-input-button', timeout=0.5)
                    if dropdown_btn:
                        dropdown_btn.click(by_js=True)
                        dropdown = iframe.ele('css:div[data-testid="uicl-dropdown"]', timeout=2)
                        if dropdown:
                            opened = True
                except Exception:
                    pass
            
            # 再兜底：点击 please-select
            if not opened:
                try:
                    please_select = iframe.ele('css:span.please-select', timeout=0.5)
                    if please_select:
                        please_select.click(by_js=True)
                        dropdown = iframe.ele('css:div[data-testid="uicl-dropdown"]', timeout=2)
                        if dropdown:
                            opened = True
                except Exception:
                    pass
            
            time.sleep(0.3)
            
            # 获取下拉框并提取选项
            dropdown = None
            dropdowns = iframe.eles('css:div[data-testid="uicl-dropdown"]')
            if dropdowns:
                dropdown = dropdowns[-1]
            
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
            
            # 去重并保持顺序
            seen = set()
            unique_options = []
            for opt in options_list:
                if opt.lower() not in seen:
                    seen.add(opt.lower())
                    unique_options.append(opt)
            
            return unique_options
            
        except Exception as e:
            logger.error(f"获取 Template Term 选项失败: {e}")
            return []
    
    def _select_template_term(self, iframe, term_text: str = "Commission Tier Terms") -> bool:
        """选择 Template Term"""
        try:
            desired = (term_text or "Commission Tier Terms").strip()
            desired_norm = re.sub(r'\s*\(\d+\)\s*$', '', desired).strip().lower()
            desired_norm = re.sub(r'\s+', ' ', desired_norm)

            term_dropdown = iframe.ele('css:select[data-testid="uicl-select"]', timeout=2)
            
            if term_dropdown:
                try:
                    term_dropdown.select(desired)
                    logger.info(f"已选择 Template Term: {desired}")
                    time.sleep(0.3)
                    return True
                except Exception as e:
                    logger.warning(f"<select> 选择 Template Term 失败，尝试自定义下拉: {e}")
            
            opened = False

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
                                opened = True
                                break
                            time.sleep(0.2)
                        parent = parent.parent()

            # 兜底：不依赖“Template Term”文本区域，直接找触发器点击（避免 DOM 结构变化导致 parent 链找不到）
            if not opened:
                try:
                    dropdown_btn = iframe.ele('css:button[data-testid="uicl-multi-select-input-button"]', timeout=0.5)
                    if not dropdown_btn:
                        dropdown_btn = iframe.ele('css:.iui-multi-select-input-button', timeout=0.5)
                    if dropdown_btn:
                        dropdown_btn.click(by_js=True)
                        dropdown = iframe.ele('css:div[data-testid="uicl-dropdown"]', timeout=2)
                        if dropdown:
                            opened = True
                except Exception:
                    pass

            # 再兜底：有些实现点击按钮内部的文字也能展开
            if not opened:
                try:
                    please_select = iframe.ele('css:span.please-select', timeout=0.5)
                    if please_select:
                        please_select.click(by_js=True)
                        dropdown = iframe.ele('css:div[data-testid="uicl-dropdown"]', timeout=2)
                        if dropdown:
                            opened = True
                except Exception:
                    pass
            
            time.sleep(0.3)

            # 使用 JS 找到真正可见的下拉框（避免找到隐藏的 Portal 元素）
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
                    # 清理标记
                    if dropdown:
                        try:
                            dropdown.run_js('this.removeAttribute("data-rpa-visible-dropdown");')
                        except Exception:
                            pass
            except Exception:
                pass
            
            # 备用：遍历所有下拉框找可见的
            if not dropdown:
                dropdowns = iframe.eles('css:div[data-testid="uicl-dropdown"]')
                for dd in dropdowns or []:
                    try:
                        rect_js = "var r = this.getBoundingClientRect(); var s = window.getComputedStyle(this); return JSON.stringify({w: r.width, h: r.height, d: s.display});"
                        import json
                        data = json.loads(dd.run_js(rect_js))
                        if data['w'] > 0 and data['h'] > 0 and data['d'] != 'none':
                            dropdown = dd
                            break
                    except Exception:
                        pass

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
                    txtn = re.sub(r'\s*\(\d+\)\s*$', '', txt).strip().lower()
                    txtn = re.sub(r'\s+', ' ', txtn)
                    options.append((txt, txtn, it))
                if not options:
                    nodes = dropdown.eles('css:div.text-ellipsis')
                    for it in nodes or []:
                        txt = it.text or ''
                        txtn = re.sub(r'\s*\(\d+\)\s*$', '', txt).strip().lower()
                        txtn = re.sub(r'\s+', ' ', txtn)
                        options.append((txt, txtn, it))
                matches = [(t, n, e) for (t, n, e) in options if n == desired_norm or desired_norm in n or n in desired_norm]
                if len(matches) == 1:
                    try:
                        matches[0][2].wait.clickable()
                    except Exception:
                        pass
                    # 优先使用原生点击（如果元素有尺寸）
                    try:
                        matches[0][2].click()
                    except Exception:
                        matches[0][2].click(by_js=True)
                    logger.info(f"已选择 Template Term: {matches[0][0]}")
                    time.sleep(0.3)
                    return True
                if len(matches) > 1:
                    self.console.print("\n[bold]检测到多个匹配项，请选择：[/bold]")
                    for idx, (t, _, _) in enumerate(matches, start=1):
                        self.console.print(f"{idx}. {t}")
                    sel = questionary.text("请输入编号:", validate=lambda x: x.isdigit() and 1 <= int(x) <= len(matches) or "请输入有效编号").ask()
                    if sel and sel.isdigit():
                        pick = matches[int(sel)-1]
                        try:
                            pick[2].wait.clickable()
                        except Exception:
                            pass
                        try:
                            pick[2].click()
                        except Exception:
                            pick[2].click(by_js=True)
                        settings = self.config.load_settings()
                        settings['template_term'] = pick[0]
                        self.config.save_settings(settings)
                        self.template_term = pick[0]
                        logger.info(f"已选择 Template Term: {pick[0]}")
                        time.sleep(0.3)
                        return True
                if not matches and options:
                    self.console.print("\n[bold]未匹配到配置项，以下为所有可选项：[/bold]")
                    for idx, (t, _, _) in enumerate(options, start=1):
                        self.console.print(f"{idx}. {t}")
                    sel = questionary.text("请输入编号:", validate=lambda x: x.isdigit() and 1 <= int(x) <= len(options) or "请输入有效编号").ask()
                    if sel and sel.isdigit():
                        pick = options[int(sel)-1]
                        try:
                            pick[2].wait.clickable()
                        except Exception:
                            pass
                        try:
                            pick[2].click()
                        except Exception:
                            pick[2].click(by_js=True)
                        settings = self.config.load_settings()
                        settings['template_term'] = pick[0]
                        self.config.save_settings(settings)
                        self.template_term = pick[0]
                        logger.info(f"已选择 Template Term: {pick[0]}")
                        time.sleep(0.3)
                        return True

            try:
                desired_ele = iframe.ele(f'text={desired}', timeout=2)
                if desired_ele:
                    try:
                        desired_ele.wait.clickable()
                    except Exception:
                        pass
                    desired_ele.click(by_js=None)
                    logger.info(f"已选择 Template Term: {desired}")
                    time.sleep(0.3)
                    return True
            except:
                pass

            term_options = iframe.eles('css:div.text-ellipsis')
            for opt in term_options:
                try:
                    if opt and opt.text:
                        txt = re.sub(r'\s*\(\d+\)\s*$', '', opt.text).strip().lower()
                        txt = re.sub(r'\s+', ' ', txt)
                        if txt == desired_norm or desired_norm in txt:
                            try:
                                opt.wait.clickable()
                            except Exception:
                                pass
                            opt.click(by_js=None)
                            logger.info(f"已选择 Template Term: {desired}")
                            time.sleep(0.3)
                            return True
                except:
                    continue
            
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

    def _read_partner_group_dropdown_options(
        self,
        dropdown,
        *,
        emit_debug_log: bool | None = None,
    ) -> list[tuple[str, str, object]]:
        """读取 Partner Group 下拉选项，返回 (显示文本, 规范化文本, 元素)。"""
        selectors = [
            'css:li[role="option"]',
            'css:div[role="option"]',
            'css:div._4-15-1_Baf2T',
            'css:li',
        ]
        options: list[tuple[str, str, object]] = []
        seen: set[str] = set()

        for selector in selectors:
            try:
                nodes = dropdown.eles(selector, timeout=0.2)
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

        本函数尽量用“文本匹配 + 排除下拉 option 区域”的方式验证：
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
                    if norm == target_norm:
                        matched_text = text
                        break

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
        wait_timeout: float = 2.0,
    ) -> bool:
        """
        点击 Partner Group 下拉选项，并等待验证通过（避免 click() 无异常但业务未选中的情况）。

        策略：
        - 优先真实点击，再尝试 JS click()，最后用事件派发兜底；
        - 点击后轮询验证：优先查找已选区域是否出现目标；如果找不到，则使用启发式：
          「输入框已清空 且 下拉不再包含目标项」。
        """

        def _gather_targets(base_ele) -> list:
            targets: list = []
            seen: set[int] = set()
            cur = base_ele
            for _ in range(2):  # 当前元素 + 1 层父节点，避免点到过大的容器
                if not cur:
                    break
                key = id(cur)
                if key not in seen:
                    seen.add(key)
                    targets.append(cur)
                try:
                    cur = cur.parent()
                except Exception:
                    break
            return targets

        def _refresh_base_ele() -> tuple[str, object]:
            if not dropdown:
                return pick_text, pick_ele
            try:
                opts = self._read_partner_group_dropdown_options(dropdown)
            except Exception:
                opts = []
            # 优先按规范化文本匹配（更稳）
            for t, n, e in opts or []:
                if n == target_norm:
                    return t, e
            # 次选：按原始文本匹配
            for t, n, e in opts or []:
                if (t or "").strip() == (pick_text or "").strip():
                    return t, e
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
            if not dropdown:
                return True
            try:
                opts = self._read_partner_group_dropdown_options(dropdown, emit_debug_log=False)
            except Exception:
                opts = []
            return any((n == target_norm) for _, n, _ in (opts or []))

        def _wait_selected(timeout_s: float) -> bool:
            deadline = time.time() + timeout_s
            while time.time() < deadline:
                if self._verify_partner_group_selected(iframe, target_norm, emit_failure_log=False):
                    return True
                # 启发式：输入框清空 + 下拉不再包含目标项，通常意味着已添加 chip
                if _get_tag_input_value() == "" and not _dropdown_has_target():
                    if self.partner_groups_debug_logging:
                        logger.info("[PartnerGroupsDebug] 验证通过：输入框已清空且下拉已不包含目标选项")
                    return True
                time.sleep(0.2)
            # 只在最终失败时输出一次验证详情，避免轮询期间刷屏
            if self.partner_groups_debug_logging:
                self._verify_partner_group_selected(iframe, target_norm, emit_failure_log=True)
            return False

        def _scroll_into_view(ele) -> None:
            try:
                ele.run_js('this.scrollIntoView({block:"center", inline:"nearest"});')
            except Exception:
                pass

        click_methods = [
            ("real", lambda e: e.click()),
            ("js", lambda e: e.click(by_js=True)),
            (
                "dispatch",
                lambda e: e.run_js(
                    "this.dispatchEvent(new MouseEvent('mousedown',{bubbles:true}));"
                    "this.dispatchEvent(new MouseEvent('mouseup',{bubbles:true}));"
                    "this.dispatchEvent(new MouseEvent('click',{bubbles:true}));"
                ),
            ),
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

                if not dropdown:
                    try:
                        parent = tag_input.parent()
                        for _ in range(4):
                            if not parent:
                                break
                            data_testid = (parent.attr('data-testid') or '').strip()
                            if data_testid == 'uicl-tag-input':
                                dropdown = parent
                                break
                            parent = parent.parent()
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
                        wait_timeout=2.0,
                    )
                    if not ok:
                        raise Exception(f"Partner Group 选项点击后验证失败: {pick_text}")

                    self._partner_group_prefix_len_cache[cache_key] = input_len
                    logger.info(
                        f"已选择 Partner Group: {pick_text}（当前输入长度={input_len}，仅 1 个可见选项，已缓存）"
                    )
                    time.sleep(0.2)
                    return True

                # 只有完整输入整个名称且存在规范化完全匹配时才按「精确匹配」逻辑选中
                if input_len == len(search_text):
                    exact_matches = [opt for opt in options if opt[1] == target_norm]
                    if self.partner_groups_debug_logging:
                        logger.info(
                            f"[PartnerGroupsDebug] 完整输入长度达到 search_text，准备走精确匹配逻辑；"
                            f"prefix='{prefix}', target_norm='{target_norm}', "
                            f"options_count={len(options)}, exact_match_count={len(exact_matches)}"
                        )
                    if exact_matches:
                        pick_text, _, pick_ele = exact_matches[0]
                        ok = self._click_partner_group_option_and_verify(
                            iframe=iframe,
                            dropdown=dropdown,
                            pick_ele=pick_ele,
                            pick_text=pick_text,
                            target_norm=target_norm,
                            wait_timeout=2.0,
                        )
                        if not ok:
                            raise Exception(f"Partner Group 精确匹配项点击后验证失败: {pick_text}")

                        self._partner_group_prefix_len_cache[cache_key] = input_len
                        logger.info(
                            f"已选择 Partner Group: {pick_text}（完整输入={input_len}字符，找到 {len(exact_matches)} 个匹配，已缓存）"
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
    
    def _select_tomorrow_date(self, iframe, strategies: list | None = None) -> bool:
        """
        选择明天的日期
        
        Args:
            iframe: iframe 对象
            strategies: 使用的策略列表，默认 ['element_click', 'vision_rpa']
            
        Returns:
            bool: 是否成功
        """
        try:
            target_date = datetime.now() + timedelta(days=1)
            if strategies is None:
                # 主流程只使用真实点击（element_click）。
                # 当今天是月末时，明天会自动变成下个月 1 号，由 element_click 负责跨月导航并点击。
                strategies = ['element_click']
            result = self.date_picker.select_date(
                context=iframe,
                target_date=target_date,
                strategies=strategies,
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
        """等待 Proposal 弹窗 iframe 出现"""
        deadline = time.time() + self.modal_wait_timeout
        start_time = time.time()
        while time.time() < deadline:
            iframe = self.browser.find_element(
                'css:iframe[data-testid="uicl-modal-iframe-content"]',
                timeout=0.5
            )
            if iframe:
                elapsed = time.time() - start_time
                if elapsed > 2.0:  # 如果等待超过2秒，记录日志
                    logger.debug(f"弹窗 iframe 出现（等待了 {elapsed:.2f} 秒）")
                return iframe
            time.sleep(self.modal_poll_interval)
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


class MenuUI:
    """用户界面类，负责菜单显示和用户交互"""
    
    def __init__(
        self,
        config: ConfigManager,
        template_manager: TemplateManager,
        console: Console,
        browser: BrowserManager | None = None,
        proposal_sender: "ProposalSender | None" = None,
    ):
        self.config = config
        self.template_manager = template_manager
        self.console = console
        self.browser = browser
        self.proposal_sender = proposal_sender
    
    def show_main_menu(self) -> str | None:
        """显示主菜单"""
        self.console.print(Panel.fit(
            "[bold cyan]Impact RPA - Send Proposal 自动化工具[/bold cyan]",
            border_style="cyan"
        ))
        
        choices = [
            questionary.Choice("🚀 开始发送 Send Proposal", value="1"),
            questionary.Choice("📋 Creator Search 批量发送", value="8"),
            questionary.Choice("📄 预览当前留言模板", value="2"),
            questionary.Choice("✏️  编辑留言模板", value="3"),
            questionary.Choice("🔢 设置发送数量", value="4"),
            questionary.Choice("⚙️  查看当前设置", value="5"),
            questionary.Choice("🔧 设置 Template Term 下拉选项", value="6"),
            questionary.Choice("🏷️  设置是否输入 Partner Groups 标签", value="9"),
            questionary.Choice("🔄 检查并更新代码", value="7"),
            questionary.Choice("🚪  退出程序", value="0"),
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
            self.console.print("[bold green]✓ 模板已保存[/bold green]")
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
    
    def _get_multiline_input(self) -> str | None:
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
        table.add_row("Template Term", (settings.get('template_term') or '').strip() or "(未设置)")
        table.add_row("输入 Partner Groups 标签", "是" if settings.get('input_partner_groups_tag', True) else "否")
        
        self.console.print(table)
        questionary.press_any_key_to_continue("按任意键返回主菜单...").ask()
    
    def set_template_term(self):
        """设置 Template Term 文本"""
        settings = self.config.load_settings()
        current = (settings.get('template_term') or '').strip()
        
        self.console.print(f"[cyan]当前 Template Term: [bold]{current or '(未设置)'}[/bold][/cyan]")
        
        # 选择设置方式
        choices = [
            questionary.Choice("⌨️  手动输入", value="manual"),
            questionary.Choice("🌐 从浏览器弹窗获取选项列表", value="browser"),
            questionary.Choice("🔙 取消", value="cancel"),
        ]
        
        method = questionary.select("选择设置方式:", choices=choices).ask()
        
        if method is None or method == "cancel":
            return
        
        if method == "manual":
            new_value = questionary.text("请输入 Template Term 文本:", default=current).ask()
            if new_value is None:
                return
            new_value = (new_value or '').strip()
            settings['template_term'] = new_value
            if self.config.save_settings(settings):
                self.console.print(f"[bold green]✓ Template Term 已设置为: {new_value or '(未设置)'}[/bold green]")
        
        elif method == "browser":
            self._set_template_term_from_browser(settings, current)

    def set_partner_groups_tag_input(self):
        """设置是否在弹窗中输入 Partner Groups 标签。"""
        settings = self.config.load_settings()
        current = bool(settings.get('input_partner_groups_tag', True))

        self.console.print(
            f"[cyan]当前设置：输入 Partner Groups 标签 = [bold]{'是' if current else '否'}[/bold][/cyan]"
        )

        selected = questionary.select(
            "请选择是否输入 Partner Groups 标签:",
            choices=[
                questionary.Choice("✅ 是（输入）", value=True),
                questionary.Choice("🚫 否（跳过）", value=False),
                questionary.Choice("🔙 取消", value=None),
            ],
            style=questionary.Style([
                ('highlighted', 'fg:cyan bold'),
                ('pointer', 'fg:cyan bold'),
            ])
        ).ask()

        if selected is None:
            self.console.print("[yellow]已取消[/yellow]")
            return

        settings['input_partner_groups_tag'] = bool(selected)
        if self.config.save_settings(settings):
            if self.proposal_sender:
                self.proposal_sender.input_partner_groups_tag = bool(selected)
            self.console.print(
                f"[bold green]✓ 已设置：输入 Partner Groups 标签 = {'是' if selected else '否'}[/bold green]"
            )
    
    def _set_template_term_from_browser(self, settings: dict, current: str):
        """从浏览器弹窗获取 Template Term 选项并让用户选择"""
        if not self.browser or not self.proposal_sender:
            self.console.print("[red]浏览器未初始化，无法从浏览器获取选项[/red]")
            return
        
        if not self.browser.is_connected():
            self.console.print("[red]浏览器未连接，请先确保浏览器已打开[/red]")
            return
        
        self.console.print(Panel(
            "[bold]请在浏览器中完成以下操作：[/bold]\n"
            "1. 导航到包含 Send Proposal 按钮的页面\n"
            "2. 手动点击任意一个 [bold cyan]Send Proposal[/bold cyan] 按钮\n"
            "3. 等待弹窗加载完成\n"
            "4. 返回此处按任意键继续",
            title="[cyan]操作指南[/cyan]",
            border_style="cyan"
        ))
        questionary.press_any_key_to_continue("弹窗打开后，按任意键继续...").ask()
        
        # 查找弹窗 iframe
        self.console.print("[cyan]正在查找弹窗...[/cyan]")
        iframe = self.browser.find_element(
            'css:iframe[data-testid="uicl-modal-iframe-content"]',
            timeout=5
        )
        
        if not iframe:
            self.console.print("[red]未找到弹窗 iframe，请确保 Send Proposal 弹窗已打开[/red]")
            return
        
        # 获取选项列表
        self.console.print("[cyan]正在获取 Template Term 选项列表...[/cyan]")
        options = self.proposal_sender._get_template_term_options(iframe)
        
        if not options:
            self.console.print("[yellow]未获取到选项列表，可能弹窗结构已变化[/yellow]")
            return
        
        # 显示选项列表让用户选择
        self.console.print(f"\n[bold]检测到 {len(options)} 个可选项：[/bold]")
        
        option_choices = []
        for opt in options:
            mark = " ✓" if opt.lower() == current.lower() else ""
            option_choices.append(questionary.Choice(f"{opt}{mark}", value=opt))
        option_choices.append(questionary.Choice("🔙 取消", value=None))
        
        selected = questionary.select(
            "请选择 Template Term:",
            choices=option_choices,
            style=questionary.Style([
                ('highlighted', 'fg:cyan bold'),
                ('pointer', 'fg:cyan bold'),
            ])
        ).ask()
        
        if selected is None:
            self.console.print("[yellow]已取消[/yellow]")
            return
        
        settings['template_term'] = selected
        if self.config.save_settings(settings):
            self.console.print(f"[bold green]✓ Template Term 已设置为: {selected}[/bold green]")
            
            # 提示用户关闭弹窗
            self.console.print("[dim]提示：请手动关闭浏览器中的弹窗[/dim]")
    
    def check_and_update(self):
        """检查并更新代码"""
        try:
            from update_manager import UpdateManager
            update_manager = UpdateManager(console=self.console)
            update_manager.show_update_ui()
            questionary.press_any_key_to_continue("按任意键返回主菜单...").ask()
        except ImportError:
            self.console.print("[red]错误：无法导入更新管理器模块[/red]")
            self.console.print("[yellow]请确保已安装 dulwich 库：pip install dulwich[/yellow]")
            questionary.press_any_key_to_continue("按任意键返回主菜单...").ask()
        except Exception as e:
            self.console.print(f"[red]更新失败: {e}[/red]")
            logger.error(f"更新失败: {e}")
            questionary.press_any_key_to_continue("按任意键返回主菜单...").ask()


class ImpactRPA:
    """Impact RPA 主应用类"""
    
    def __init__(self):
        self.console = Console()
        self.config = ConfigManager()
        self.template_manager = TemplateManager(self.config)
        self.browser = BrowserManager(self.console, self.config)
        self.proposal_sender = ProposalSender(self.browser, self.template_manager, self.console, self.config)
        self.menu = MenuUI(
            self.config,
            self.template_manager,
            self.console,
            browser=self.browser,
            proposal_sender=self.proposal_sender,
        )
    
    def start(self):
        """启动应用"""
        # 初始化浏览器
        if not self.browser.init():
            self.console.print("[red]无法连接浏览器，请确保浏览器已打开[/red]")
            try:
                from notification_service import NotificationService, NotificationPayload
                NotificationService().send(NotificationPayload(message="无法连接浏览器"))
            except Exception:
                pass
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
            elif choice == '8':
                self._send_proposal_by_table_row()
            elif choice == '2':
                self.menu.preview_template()
            elif choice == '3':
                self.menu.edit_template_menu()
            elif choice == '4':
                self.menu.set_proposal_count()
            elif choice == '5':
                self.menu.view_settings()
            elif choice == '6':
                self.menu.set_template_term()
            elif choice == '9':
                self.menu.set_partner_groups_tag_input()
            elif choice == '7':
                self.menu.check_and_update()
            elif choice == '0':
                self.console.print("\n[bold cyan]感谢使用，再见！👋[/bold cyan]")
                break
    
    def _notify_proposal_run(
        self,
        result: SendProposalsResult | None = None,
        error: Exception | None = None,
    ) -> None:
        """
        按策略发送桌面通知：仅在意料之外的异常或全部任务成功完成时通知。
        不通知：用户取消、未全部完成即正常退出等。
        """
        if error is not None:
            msg = f"发送失败: {error}"
        elif result is not None and result.completed_all:
            msg = f"发送完成，共发送 {result.clicked_count} 个"
        else:
            return
        try:
            from notification_service import NotificationService, NotificationPayload
            NotificationService().send(NotificationPayload(message=msg))
        except Exception:
            pass

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
        
        try:
            result = self.proposal_sender.send_proposals(max_count, template)
            self._notify_proposal_run(result=result, error=None)
        except Exception as e:
            self._notify_proposal_run(result=None, error=e)

    def _send_proposal_by_table_row(self):
        """Creator Search 批量发送：在 Creator Search 页面批量发送 Proposal"""
        if not self.browser.is_connected():
            if not self.browser.init():
                self.console.print("[red]无法连接浏览器，请确保浏览器已打开[/red]")
                return
        
        self.console.print(Panel(
            "[bold]请在浏览器中完成以下操作：[/bold]\n"
            "1. 导航到 Creator Search 页面 (creator-rt-searches.ihtml)\n"
            "2. 设置好筛选条件并获取搜索结果\n"
            "3. 确保搜索结果列表已加载\n"
            "4. 返回此处按任意键继续",
            title="[cyan]Creator Search 批量发送[/cyan]",
            border_style="cyan"
        ))
        questionary.press_any_key_to_continue("操作完成后，按任意键继续...").ask()
        
        # 获取发送数量
        settings = self.config.load_settings()
        default_count = settings.get('max_proposals', 10)
        
        count_input = questionary.text(
            f"请输入要发送的数量 (默认 {default_count}):",
            default=str(default_count)
        ).ask()
        if count_input is None:
            self.console.print("[yellow]已取消[/yellow]")
            return
        try:
            max_count = int(count_input.strip()) if count_input.strip() else default_count
        except ValueError:
            self.console.print("[red]请输入有效的数字[/red]")
            return
        if max_count < 1:
            self.console.print("[red]数量需大于等于 1[/red]")
            return
        
        # 获取起始行号
        start_input = questionary.text(
            "请输入起始行号 (从 1 开始，默认 1):",
            default="1"
        ).ask()
        if start_input is None:
            self.console.print("[yellow]已取消[/yellow]")
            return
        try:
            start_row = int(start_input.strip()) if start_input.strip() else 1
        except ValueError:
            self.console.print("[red]请输入有效的整数行号[/red]")
            return
        if start_row < 1:
            self.console.print("[red]行号需大于等于 1[/red]")
            return
        
        # 预览模板
        template = self.template_manager.get_active_template()
        if not template:
            self.console.print("[bold yellow]⚠️  警告: 留言模板为空！[/bold yellow]")
            if not questionary.confirm("是否继续?", default=False).ask():
                return
        else:
            self.console.print("\n[bold]当前留言模板预览:[/bold]")
            self.console.print(Panel(template, border_style="dim"))
        
        # 确认发送
        self.console.print(f"\n[cyan]即将从第 {start_row} 行开始，发送 {max_count} 个 Proposal[/cyan]")
        if not questionary.confirm("确认开始批量发送?", default=False).ask():
            self.console.print("[yellow]已取消[/yellow]")
            return
        
        try:
            result = self.proposal_sender.send_proposals_creator_search(
                max_count=max_count,
                start_row=start_row,
                template_content=template,
            )
            self._notify_proposal_run(result=result, error=None)
        except Exception as e:
            self._notify_proposal_run(result=None, error=e)


if __name__ == "__main__":
    app = ImpactRPA()
    app.start()
