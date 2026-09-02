import inspect
import os
import re
import time
from datetime import datetime
from typing import Protocol

from DrissionPage import Chromium
from DrissionPage.errors import ContextLostError, ElementNotFoundError, PageDisconnectedError
from loguru import logger

from exception_handler import exception_handler

from core.settings_models import AppSettings


class LogSink(Protocol):
    def info(self, message: str) -> None: ...

    def warning(self, message: str) -> None: ...

    def error(self, message: str) -> None: ...

    def debug(self, message: str) -> None: ...


class BrowserManager:
    """浏览器管理类，负责浏览器连接和元素操作"""

    def __init__(self, log: LogSink, config=None):
        self.browser = None
        self.tab = None
        self.logger = log
        self.max_retries = 3
        self.config = config

        base_dir = None
        try:
            base_dir = getattr(config, 'base_dir', None)
        except Exception:
            base_dir = None
        self.base_dir = base_dir or os.path.dirname(os.path.dirname(__file__))

        settings = AppSettings()
        try:
            if config:
                settings = config.load_settings()
        except Exception:
            settings = AppSettings()

        self.screenshot_on_error = settings.screenshot_on_error
        self.screenshot_full_page = settings.screenshot_full_page
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
            self.logger.error("所有浏览器连接方式均失败")
            self.logger.error("[yellow]提示：请确保浏览器已打开，并允许 DrissionPage 连接[/yellow]")
            self.logger.error("[yellow]或者手动启动浏览器后重试[/yellow]")
            self.logger.error("[dim]常见解决方案：[/dim]")
            self.logger.error("[dim]1. 确保 Chrome/Edge 浏览器已打开[/dim]")
            self.logger.error("[dim]2. 检查是否有防火墙/安全软件阻止连接[/dim]")
            self.logger.error("[dim]3. 尝试以管理员权限运行[/dim]")
            self.logger.error("[dim]4. 如果使用 Chrome，尝试关闭所有 Chrome 窗口后重新打开[/dim]")
            return False

        except Exception as e:
            self.logger.error(f"浏览器连接失败: {e}")
            import traceback
            self.logger.debug(traceback.format_exc())
            return False

    def reconnect(self) -> bool:
        """重新连接浏览器"""
        self.logger.warning("检测到页面断开，正在重新连接...")
        self.logger.warning("页面断开，尝试重新连接浏览器")

        for i in range(self.max_retries):
            try:
                self.browser = Chromium()
                try:
                    impact_tab = self.browser.get_tab(url='https://app.impact.com/secure/')
                except Exception:
                    impact_tab = None
                self.tab = impact_tab or self.browser.latest_tab
                self.logger.info("浏览器重新连接成功")
                logger.info("浏览器重新连接成功")
                return True
            except Exception as e:
                self.logger.error(f"重连尝试 {i+1}/{self.max_retries} 失败: {e}")
                time.sleep(1)

        self.logger.error("✗ 浏览器重新连接失败")
        return False

    def is_connected(self) -> bool:
        """检查浏览器是否已连接"""
        if self.browser is None or self.tab is None:
            return False
        try:
            latest_tab = getattr(self.browser, "latest_tab", None)
            if latest_tab is not None:
                try:
                    impact_tab = self.browser.get_tab(url='https://app.impact.com/secure/')
                except Exception:
                    impact_tab = None
                self.tab = impact_tab or latest_tab
            _ = self.tab.url
            return True
        except (PageDisconnectedError, ContextLostError):
            logger.warning("浏览器连接已失效：页面上下文已断开")
            return False
        except Exception as e:
            logger.debug(f"浏览器连接检测失败: {e}")
            return False

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

    def find_element(self, locator: str, timeout: float = 3.0, parent=None):
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
                    "timeout": timeout,
                    "page": self._get_page_context(),
                    "caller": self._caller_brief()
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
                        "error_type": "页面断开",
                        "page": self._get_page_context(),
                        "caller": self._caller_brief()
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
            exception_handler.log_exception(
                e,
                context={
                    "operation": "查找多个元素",
                    "locator": locator,
                    "timeout": timeout,
                    "page": self._get_page_context(),
                    "caller": self._caller_brief()
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
                        "error_type": "页面断开",
                        "page": self._get_page_context(),
                        "caller": self._caller_brief()
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
            exception_handler.log_exception(
                e,
                context={
                    "operation": "点击元素",
                    "by_js": by_js,
                    "page": self._get_page_context(),
                    "caller": self._caller_brief(),
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

    def scroll_down(self, pixels: int = 500, incremental: bool = True) -> bool:
        """向下滚动页面（使用 DrissionPage PageScroller）

        Args:
            pixels: 滚动像素数
            incremental: True=渐进式滚动（推荐），False=滚动到底部
        """
        try:
            if incremental:
                self.tab.scroll.down(pixels)
                logger.debug(f"页面已向下滚动 {pixels}px")
            else:
                self.tab.scroll.to_bottom()
                logger.debug("页面已滚动到底部")
            return True

        except Exception as e:
            logger.warning(f"向下滚动失败: {e}")
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
        """滚动到元素可见（使用 DrissionPage ElementScroller，居中显示）"""
        try:
            element.scroll.to_see(center=True)
            return True
        except Exception as e:
            logger.warning(f"滚动到元素失败: {e}")
            exception_handler.log_exception(
                e,
                context={
                    "operation": "滚动到元素",
                    "page": self._get_page_context(),
                    "caller": self._caller_brief(),
                },
            )
            return False

    def get_scroll_container_info(self) -> dict:
        """获取当前页面的滚动容器信息（用于调试和诊断）"""
        try:
            info = self.tab.run_js("""
                (function() {
                    function findScrollContainers() {
                        const containers = [];
                        const allElements = document.querySelectorAll('*');

                        for (const el of allElements) {
                            const style = window.getComputedStyle(el);
                            const overflowY = style.overflowY;
                            const overflow = style.overflow;

                            if ((overflowY === 'auto' || overflowY === 'scroll' ||
                                 overflow === 'auto' || overflow === 'scroll') &&
                                el.scrollHeight > el.clientHeight) {
                                if (el.tagName.toLowerCase() !== 'html' &&
                                    el.tagName.toLowerCase() !== 'body') {
                                    containers.push({
                                        tagName: el.tagName.toLowerCase(),
                                        id: el.id || '',
                                        className: (el.className || '').toString().slice(0, 80),
                                        scrollTop: el.scrollTop,
                                        scrollHeight: el.scrollHeight,
                                        clientHeight: el.clientHeight,
                                        scrollable: el.scrollHeight - el.clientHeight
                                    });
                                }
                            }
                        }

                        containers.sort((a, b) => b.scrollable - a.scrollable);
                        return containers.slice(0, 5); // 返回前5个最大的容器
                    }

                    return {
                        containers: findScrollContainers(),
                        windowScrollY: window.scrollY || window.pageYOffset,
                        documentHeight: document.body.scrollHeight
                    };
                })()
            """)

            return info if isinstance(info, dict) else {}
        except Exception as e:
            logger.warning(f"获取滚动容器信息失败: {e}")
            return {}

    def _capture_screenshot(self, label: str, element=None) -> str | None:
        """捕获页面截图（失败时静默返回 None）"""
        try:
            now_ts = time.time()
            if now_ts - self._last_screenshot_ts < self._screenshot_min_interval:
                return None
            self._last_screenshot_ts = now_ts

            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            safe_label = re.sub(r'[^\w\-]', '_', label)[:20]
            filename = f"{timestamp}_{safe_label}.png"
            filepath = os.path.join(self.screenshot_dir, filename)

            if element:
                try:
                    element.get_screenshot(filepath)
                except Exception:
                    self.tab.get_screenshot(filepath, full_page=self.screenshot_full_page)
            else:
                self.tab.get_screenshot(filepath, full_page=self.screenshot_full_page)

            return filepath
        except Exception:
            return None


__all__ = ["BrowserManager"]
