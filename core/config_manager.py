import json
import os
from loguru import logger


class ConfigManager:
    """配置管理类，负责处理所有配置文件的读写。"""

    def __init__(self, base_dir: str | None = None):
        self.base_dir = base_dir or os.path.dirname(os.path.dirname(__file__))
        self.config_dir = os.path.join(self.base_dir, "config")
        self.log_dir = os.path.join(self.base_dir, "logs")
        self.template_file = os.path.join(self.config_dir, "template.txt")
        self.templates_file = os.path.join(self.config_dir, "templates.json")
        self.settings_file = os.path.join(self.config_dir, "settings.json")
        # 可选：由组合根注入，用于配置热更新
        self.store = None

        self.default_settings = {
            "max_proposals": 10,
            "scroll_delay": 1.0,
            "click_delay": 0.5,
            "modal_wait": 20.0,
            "dry_run": False,
            "template_term": "Commission Tier Terms",
            "input_partner_groups_tag": True,
            # 是否输出 Partner Groups 下拉解析与点击的详细调试日志
            "partner_groups_debug_logging": False,
            "partner_groups": {
                "mode": "ui",
                "api": {
                    "url": "",
                    "method": "POST",
                    "headers": {},
                    "body": None,
                    "csrf_meta_selector": "",
                    "csrf_header_name": "X-CSRF-Token",
                    "success_status_min": 200,
                    "success_status_max": 299,
                },
                "id_by_name": {},
            },
            "screenshot_on_error": True,
            "screenshot_full_page": False,
            "vision_rpa": {
                "enabled": False,
                "api_key": "",
                "base_url": "",
                "model": "gpt-4o",
                "max_tokens": 1024,
                "temperature": 0.1,
                "timeout": 30,
                "browser_ui_offset_x": 0,
                "browser_ui_offset_y": 0,
            },
        }

        os.makedirs(self.config_dir, exist_ok=True)
        os.makedirs(self.log_dir, exist_ok=True)
        self._setup_logger()

    def _setup_logger(self) -> None:
        logger.add(
            os.path.join(self.log_dir, "impact_rpa_{time:YYYY-MM-DD}.log"),
            rotation="1 day",
            retention="7 days",
            level="INFO",
            format="{time:YYYY-MM-DD HH:mm:ss} | {level} | {message}",
            encoding="utf-8",
        )

    def load_settings(self) -> dict:
        try:
            if os.path.exists(self.settings_file):
                with open(self.settings_file, "r", encoding="utf-8") as f:
                    return {**self.default_settings, **json.load(f)}
        except Exception as e:
            logger.error(f"加载设置失败: {e}")
        return self.default_settings.copy()

    def save_settings(self, settings: dict) -> bool:
        try:
            with open(self.settings_file, "w", encoding="utf-8") as f:
                json.dump(settings, f, indent=4)
            logger.info("设置保存成功")
            try:
                if self.store is not None:
                    self.store.force_reload_settings()
            except Exception:
                pass
            return True
        except Exception as e:
            logger.error(f"保存设置失败: {e}")
            return False

