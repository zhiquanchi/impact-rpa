"""
视觉 RPA 模块 - 基于视觉大模型的自动化操作

使用兼容 OpenAI SDK 格式的 VL LLM 进行视觉分析和交互
"""

import os
import json
import base64
import time
import re
from datetime import datetime
from typing import Callable, Tuple, Optional, Any
from dataclasses import dataclass
from loguru import logger

try:
    from openai import OpenAI
except ImportError:
    OpenAI = None

try:
    import pyautogui
    PYAUTOGUI_AVAILABLE = True
except ImportError:
    PYAUTOGUI_AVAILABLE = False
    pyautogui = None


@dataclass
class VisionConfig:
    """视觉 RPA 配置"""
    api_key: str = None
    base_url: str = None  # 兼容 OpenAI 格式的 API 地址
    model: str = "gpt-4o"  # 或其他兼容的视觉模型
    max_tokens: int = 1024
    temperature: float = 0.1
    timeout: int = 30
    # 浏览器 UI 偏移（标签栏+地址栏高度，单位：像素）
    # 不同浏览器和窗口状态的默认值可能不同，可以手动调整
    browser_ui_offset_x: int = 0  # 内容区域左侧偏移
    browser_ui_offset_y: int = 0  # 内容区域顶部偏移（通常是标签栏+地址栏高度，约 100-150px）
    
    @classmethod
    def from_env(cls) -> "VisionConfig":
        """从环境变量加载配置"""
        return cls(
            api_key=os.getenv("OPENAI_API_KEY") or os.getenv("VL_API_KEY"),
            base_url=os.getenv("OPENAI_BASE_URL") or os.getenv("VL_BASE_URL"),
            model=os.getenv("VL_MODEL", "gpt-4o"),
            max_tokens=int(os.getenv("VL_MAX_TOKENS", "1024")),
            temperature=float(os.getenv("VL_TEMPERATURE", "0.1")),
            timeout=int(os.getenv("VL_TIMEOUT", "30")),
            browser_ui_offset_x=int(os.getenv("VL_BROWSER_UI_OFFSET_X", "0")),
            browser_ui_offset_y=int(os.getenv("VL_BROWSER_UI_OFFSET_Y", "0")),
        )
    
    @classmethod
    def from_dict(cls, data: dict) -> "VisionConfig":
        """从字典加载配置"""
        return cls(
            api_key=data.get("api_key"),
            base_url=data.get("base_url"),
            model=data.get("model", "gpt-4o"),
            max_tokens=data.get("max_tokens", 1024),
            temperature=data.get("temperature", 0.1),
            timeout=data.get("timeout", 30),
            browser_ui_offset_x=data.get("browser_ui_offset_x", 0),
            browser_ui_offset_y=data.get("browser_ui_offset_y", 0),
        )


@dataclass
class ClickTarget:
    """点击目标"""
    x: int  # 相对于图像的 x 坐标
    y: int  # 相对于图像的 y 坐标
    confidence: float = 1.0  # 置信度
    description: str = ""  # 描述


class VisionRPA:
    """
    视觉 RPA 处理器
    
    使用视觉大模型分析页面截图，识别目标元素位置并执行点击
    """
    
    def __init__(self, config: VisionConfig = None):
        if OpenAI is None:
            raise ImportError("请安装 openai 库: pip install openai")
        
        self.config = config or VisionConfig.from_env()
        
        if not self.config.api_key:
            raise ValueError("未配置 API Key，请设置环境变量 OPENAI_API_KEY 或 VL_API_KEY")
        
        self.client = OpenAI(
            api_key=self.config.api_key,
            base_url=self.config.base_url,
            timeout=self.config.timeout,
        )
    
    def analyze_image(
        self,
        image_path: str = None,
        image_base64: str = None,
        prompt: str = None,
    ) -> str:
        """
        分析图像并返回模型响应
        
        Args:
            image_path: 图像文件路径
            image_base64: Base64 编码的图像
            prompt: 分析提示词
            
        Returns:
            模型响应文本
        """
        if not image_path and not image_base64:
            raise ValueError("必须提供 image_path 或 image_base64")
        
        if image_path and not image_base64:
            image_base64 = self._encode_image(image_path)
        
        # 检测图像格式
        image_format = "jpeg"
        if image_path:
            ext = os.path.splitext(image_path)[1].lower()
            if ext in (".png",):
                image_format = "png"
            elif ext in (".gif",):
                image_format = "gif"
            elif ext in (".webp",):
                image_format = "webp"
        
        messages = [
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": prompt or "请描述这张图片",
                    },
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/{image_format};base64,{image_base64}",
                        },
                    },
                ],
            }
        ]
        
        response = self.client.chat.completions.create(
            model=self.config.model,
            messages=messages,
            max_tokens=self.config.max_tokens,
            temperature=self.config.temperature,
        )
        
        return response.choices[0].message.content
    
    def find_click_target(
        self,
        image_path: str = None,
        image_base64: str = None,
        target_description: str = None,
        image_width: int = None,
        image_height: int = None,
    ) -> Optional[ClickTarget]:
        """
        在图像中查找点击目标的坐标
        
        Args:
            image_path: 图像文件路径
            image_base64: Base64 编码的图像
            target_description: 目标描述（如 "日期 2026-01-05" 或 "数字 5"）
            image_width: 图像宽度（用于坐标计算）
            image_height: 图像高度（用于坐标计算）
            
        Returns:
            ClickTarget 或 None
        """
        prompt = f"""分析这张图片，找到"{target_description}"的位置。

请以 JSON 格式返回点击目标的坐标（相对于图像左上角的像素坐标）：
{{
    "found": true/false,
    "x": <x坐标>,
    "y": <y坐标>,
    "confidence": <0-1之间的置信度>,
    "description": "<对找到元素的描述>"
}}

如果找不到目标，返回：
{{
    "found": false,
    "reason": "<原因>"
}}

只返回 JSON，不要有其他内容。"""

        try:
            response = self.analyze_image(
                image_path=image_path,
                image_base64=image_base64,
                prompt=prompt,
            )
            
            # 解析 JSON 响应
            # 尝试提取 JSON
            json_match = re.search(r'\{[\s\S]*\}', response)
            if json_match:
                result = json.loads(json_match.group())
                
                if result.get("found"):
                    return ClickTarget(
                        x=int(result.get("x", 0)),
                        y=int(result.get("y", 0)),
                        confidence=float(result.get("confidence", 1.0)),
                        description=result.get("description", ""),
                    )
                else:
                    logger.warning(f"视觉模型未找到目标: {result.get('reason', '未知原因')}")
            else:
                logger.warning(f"视觉模型响应格式错误: {response[:200]}")
                
        except Exception as e:
            logger.error(f"视觉分析失败: {e}")
        
        return None
    
    def find_date_in_calendar(
        self,
        image_path: str = None,
        image_base64: str = None,
        target_date: datetime = None,
    ) -> Optional[ClickTarget]:
        """
        在日历截图中查找目标日期
        
        Args:
            image_path: 日历截图路径
            image_base64: Base64 编码的日历截图
            target_date: 目标日期
            
        Returns:
            ClickTarget 或 None
        """
        if target_date is None:
            target_date = datetime.now()
        
        day = target_date.day
        month = target_date.month
        year = target_date.year
        date_iso = target_date.strftime('%Y-%m-%d')
        
        prompt = f"""这是一个日期选择器/日历的截图。
请找到日期 {year}年{month}月{day}日 (即 {date_iso}) 对应的可点击位置。

注意：
1. 日历中可能显示多个月份的日期，请确保找到的是正确月份的日期
2. 灰色或半透明的日期通常属于相邻月份，请避免选择这些
3. 返回日期数字的中心点坐标

请以 JSON 格式返回（坐标为相对于图像左上角的像素值）：
{{
    "found": true,
    "x": <x坐标>,
    "y": <y坐标>,
    "confidence": <0-1之间的置信度>,
    "description": "<描述，如'找到了5号在第2行第3列'>"
}}

如果：
- 目标日期不在当前显示的月份中，返回 {{"found": false, "reason": "目标日期不在当前月份", "need_navigation": "next" 或 "prev"}}
- 找不到目标日期，返回 {{"found": false, "reason": "<原因>"}}

只返回 JSON，不要有其他内容。"""

        try:
            response = self.analyze_image(
                image_path=image_path,
                image_base64=image_base64,
                prompt=prompt,
            )
            
            json_match = re.search(r'\{[\s\S]*\}', response)
            if json_match:
                result = json.loads(json_match.group())
                
                if result.get("found"):
                    return ClickTarget(
                        x=int(result.get("x", 0)),
                        y=int(result.get("y", 0)),
                        confidence=float(result.get("confidence", 1.0)),
                        description=result.get("description", ""),
                    )
                else:
                    reason = result.get("reason", "未知原因")
                    nav = result.get("need_navigation")
                    logger.info(f"视觉模型: {reason}" + (f", 需要导航: {nav}" if nav else ""))
                    # 返回特殊标记，表示需要导航
                    if nav:
                        return ClickTarget(x=-1, y=-1, confidence=0, description=f"need_navigation:{nav}")
            else:
                logger.warning(f"视觉模型响应格式错误: {response[:200]}")
                
        except Exception as e:
            logger.error(f"视觉分析日历失败: {e}")
        
        return None
    
    def _encode_image(self, image_path: str) -> str:
        """将图像文件编码为 Base64"""
        with open(image_path, "rb") as f:
            return base64.b64encode(f.read()).decode("utf-8")


class VisionDatePickerHandler:
    """
    视觉日期选择处理器
    
    用于 DatePicker 类的视觉 RPA 回调
    """
    
    def __init__(self, vision_rpa: VisionRPA = None, config: VisionConfig = None):
        self.vision_rpa = vision_rpa or VisionRPA(config)
        self.config = config or VisionConfig()
        self.max_navigation_attempts = 3
        
        # 配置 PyAutoGUI（如果可用）
        if PYAUTOGUI_AVAILABLE:
            # 设置点击延迟，避免操作过快
            pyautogui.PAUSE = 0.1
            # 禁用 fail-safe（将鼠标移到屏幕角落中断），避免干扰自动化
            pyautogui.FAILSAFE = False
    
    def __call__(
        self,
        context,  # iframe 或 page 对象
        target_date: datetime,
        screenshot_path: str = None,
    ) -> bool:
        """
        视觉方式选择日期
        
        Args:
            context: DrissionPage 的 iframe 或 tab 对象
            target_date: 目标日期
            screenshot_path: 已有的截图路径（可选）
            
        Returns:
            是否成功选择日期
        """
        for attempt in range(self.max_navigation_attempts + 1):
            # 截图
            if not screenshot_path or attempt > 0:
                try:
                    screenshot_dir = os.path.join(os.path.dirname(__file__), 'logs', 'screenshots')
                    os.makedirs(screenshot_dir, exist_ok=True)
                    screenshot_path = context.get_screenshot(
                        path=screenshot_dir,
                        name=f"vision_calendar_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}.jpg"
                    )
                except Exception as e:
                    logger.error(f"视觉 RPA 截图失败: {e}")
                    return False
            
            # 使用视觉模型分析
            target = self.vision_rpa.find_date_in_calendar(
                image_path=screenshot_path,
                target_date=target_date,
            )
            
            if target is None:
                logger.warning("视觉模型未返回有效结果")
                return False
            
            # 检查是否需要导航
            if target.x == -1 and target.y == -1:
                if "need_navigation:" in target.description:
                    nav_direction = target.description.split(":")[-1].strip()
                    if not self._navigate_month(context, nav_direction):
                        return False
                    time.sleep(0.5)
                    screenshot_path = None  # 重新截图
                    continue
                return False
            
            # 执行点击（传递截图路径用于坐标系转换）
            if self._click_at_position(context, target.x, target.y, screenshot_path):
                logger.info(f"视觉 RPA 成功点击日期: {target.description}")
                return True
            else:
                logger.warning("视觉 RPA 点击失败")
                return False
        
        logger.warning("视觉 RPA 达到最大导航尝试次数")
        return False
    
    def _navigate_month(self, context, direction: str) -> bool:
        """导航到上/下个月"""
        try:
            if direction == 'prev':
                selectors = [
                    'css:button[aria-label*="Previous"]',
                    'css:button[aria-label*="Prev"]',
                    'css:[class*="prev"]',
                    'css:[class*="chevron-left"]',
                ]
            else:
                selectors = [
                    'css:button[aria-label*="Next"]',
                    'css:[class*="next"]',
                    'css:[class*="chevron-right"]',
                ]
            
            for sel in selectors:
                try:
                    btn = context.ele(sel, timeout=0.5)
                    if btn:
                        btn.click(by_js=True)
                        time.sleep(0.4)
                        return True
                except Exception:
                    continue
            
            logger.warning(f"视觉 RPA 未找到月份导航按钮: {direction}")
            return False
            
        except Exception as e:
            logger.error(f"视觉 RPA 月份导航失败: {e}")
            return False
    
    def _click_at_position(self, context, x: int, y: int, screenshot_path: str = None) -> bool:
        """
        使用 PyAutoGUI 在指定坐标点击（真实鼠标操作）
        
        Args:
            context: iframe 或 page 对象
            x: 截图中的 x 坐标（像素）
            y: 截图中的 y 坐标（像素）
            screenshot_path: 截图路径（用于获取截图尺寸）
            
        Returns:
            是否成功点击
        """
        if not PYAUTOGUI_AVAILABLE:
            logger.error("PyAutoGUI 未安装，请运行: pip install pyautogui")
            # 回退到 JS 方式
            return self._click_at_position_js_fallback(context, x, y)
        
        try:
            # 获取元素的屏幕位置和尺寸
            rect_info = self._get_element_screen_rect(context)
            if not rect_info:
                logger.warning("无法获取元素屏幕位置，使用回退方案")
                return self._click_at_position_js_fallback(context, x, y)
            
            # 获取截图尺寸
            screenshot_width, screenshot_height = self._get_screenshot_size(screenshot_path)
            if screenshot_width is None or screenshot_height is None:
                logger.warning("无法获取截图尺寸，使用 JS 回退方案")
                return self._click_at_position_js_fallback(context, x, y)
            
            # 计算缩放比例
            scale_x = rect_info['width'] / screenshot_width
            scale_y = rect_info['height'] / screenshot_height
            
            # 将截图坐标转换为元素内的实际坐标
            element_x = x * scale_x
            element_y = y * scale_y
            
            # 计算屏幕绝对坐标
            screen_x = rect_info['x'] + element_x
            screen_y = rect_info['y'] + element_y
            
            logger.debug(
                f"坐标转换: 截图({x}, {y}) -> 元素({element_x:.1f}, {element_y:.1f}) "
                f"-> 屏幕({screen_x:.1f}, {screen_y:.1f})"
            )
            
            # 使用 PyAutoGUI 点击
            pyautogui.click(int(screen_x), int(screen_y))
            logger.info(f"PyAutoGUI 成功点击屏幕坐标: ({int(screen_x)}, {int(screen_y)})")
            time.sleep(0.3)
            return True
            
        except Exception as e:
            logger.error(f"PyAutoGUI 坐标点击失败: {e}")
            # 回退到 JS 方式
            return self._click_at_position_js_fallback(context, x, y)
    
    def _click_at_position_js_fallback(self, context, x: int, y: int) -> bool:
        """JS 回退方案（当 PyAutoGUI 不可用时使用）"""
        try:
            context.run_js(f'''
                (function() {{
                    var event = new MouseEvent('click', {{
                        view: window,
                        bubbles: true,
                        cancelable: true,
                        clientX: {x},
                        clientY: {y}
                    }});
                    var element = document.elementFromPoint({x}, {y});
                    if (element) {{
                        element.dispatchEvent(event);
                        return true;
                    }}
                    return false;
                }})();
            ''')
            time.sleep(0.3)
            logger.debug("使用 JS 回退方案点击")
            return True
        except Exception as e:
            logger.error(f"JS 回退方案也失败: {e}")
            return False
    
    def _get_element_screen_rect(self, context) -> Optional[dict]:
        """
        获取元素在屏幕上的位置和尺寸
        
        Returns:
            dict: {'x': 屏幕x坐标, 'y': 屏幕y坐标, 'width': 宽度, 'height': 高度}
        """
        try:
            # 使用 JS 获取更完整的窗口和元素信息
            js_code = '''
            (function() {
                var result = {
                    isFrame: !!window.frameElement,
                    windowScreenX: window.screenX || window.screenLeft || 0,
                    windowScreenY: window.screenY || window.screenTop || 0,
                    innerWidth: window.innerWidth,
                    innerHeight: window.innerHeight,
                    scrollX: window.scrollX || window.pageXOffset || 0,
                    scrollY: window.scrollY || window.pageYOffset || 0,
                };
                
                if (window.frameElement) {
                    // iframe 情况
                    var frameRect = window.frameElement.getBoundingClientRect();
                    // 获取父窗口信息（如果可能）
                    try {
                        var parentScreenX = window.parent.screenX || window.parent.screenLeft || 0;
                        var parentScreenY = window.parent.screenY || window.parent.screenTop || 0;
                        result.parentScreenX = parentScreenX;
                        result.parentScreenY = parentScreenY;
                    } catch(e) {}
                    
                    result.iframeRect = {
                        left: frameRect.left,
                        top: frameRect.top,
                        width: frameRect.width,
                        height: frameRect.height
                    };
                } else {
                    // 主页面情况，尝试获取浏览器内容区域的偏移
                    // Chrome/Edge 的标签栏和地址栏高度
                    result.contentOffsetY = 0;
                    try {
                        // 尝试获取浏览器 UI 的偏移（这个需要从浏览器 API 获取，这里简化）
                        result.contentOffsetY = 0;
                    } catch(e) {}
                }
                
                return JSON.stringify(result);
            })();
            '''
            
            result_str = context.run_js(js_code)
            if not result_str:
                return None
            
            data = json.loads(result_str)
            
            # 计算屏幕坐标
            if data.get('isFrame'):
                # iframe 情况
                iframe_rect = data.get('iframeRect', {})
                # 使用父窗口坐标（如果可用）或当前窗口坐标
                base_x = data.get('parentScreenX', data.get('windowScreenX', 0))
                base_y = data.get('parentScreenY', data.get('windowScreenY', 0))
                
                return {
                    'x': base_x + iframe_rect.get('left', 0),
                    'y': base_y + iframe_rect.get('top', 0),
                    'width': iframe_rect.get('width', data.get('innerWidth', 0)),
                    'height': iframe_rect.get('height', data.get('innerHeight', 0)),
                }
            else:
                # 主页面情况
                # 使用配置的浏览器 UI 偏移
                return {
                    'x': data.get('windowScreenX', 0) + self.config.browser_ui_offset_x,
                    'y': data.get('windowScreenY', 0) + self.config.browser_ui_offset_y,
                    'width': data.get('innerWidth', 0),
                    'height': data.get('innerHeight', 0),
                }
                
        except Exception as e:
            logger.warning(f"获取元素屏幕位置失败: {e}")
            # 回退方案：尝试使用 PyAutoGUI 的 locateOnScreen 或手动指定偏移
            return None
    
    def _get_screenshot_size(self, screenshot_path: str = None) -> Tuple[Optional[int], Optional[int]]:
        """获取截图尺寸"""
        if not screenshot_path or not os.path.exists(screenshot_path):
            return None, None
        
        try:
            from PIL import Image
            with Image.open(screenshot_path) as img:
                return img.width, img.height
        except ImportError:
            logger.warning("PIL 未安装，无法获取截图尺寸，请安装: pip install pillow")
            return None, None
        except Exception as e:
            logger.warning(f"获取截图尺寸失败: {e}")
            return None, None


def create_vision_handler(config: VisionConfig = None) -> VisionDatePickerHandler:
    """
    创建视觉日期选择处理器
    
    Args:
        config: 视觉 RPA 配置，如果为 None 则从环境变量加载
        
    Returns:
        VisionDatePickerHandler 实例
    """
    return VisionDatePickerHandler(config=config)


# 便捷函数：从环境变量创建处理器
def create_vision_handler_from_env() -> VisionDatePickerHandler:
    """从环境变量创建视觉日期选择处理器"""
    return VisionDatePickerHandler(config=VisionConfig.from_env())

