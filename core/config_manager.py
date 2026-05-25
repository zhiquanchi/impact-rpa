import json
import os
from typing import TYPE_CHECKING

from loguru import logger
from pydantic import ValidationError

from core.settings_models import AppSettings

if TYPE_CHECKING:
    from core.config_store import ConfigStore


class ConfigManager:
    """配置管理类，负责处理所有配置文件的读写。"""

    _file_logger_configured = False

    def __init__(self, base_dir: str | None = None):
        self.base_dir = base_dir or os.path.dirname(os.path.dirname(__file__))
        self.config_dir = os.path.join(self.base_dir, "config")
        self.log_dir = os.path.join(self.base_dir, "logs")
        self.template_file = os.path.join(self.config_dir, "template.txt")
        self.template_terms_file = os.path.join(self.config_dir, "template_terms.json")
        self.templates_file = os.path.join(self.config_dir, "templates.json")
        self.settings_file = os.path.join(self.config_dir, "settings.json")
        # 可选：由组合根注入，用于配置热更新
        self.store: ConfigStore | None = None

        os.makedirs(self.config_dir, exist_ok=True)
        os.makedirs(self.log_dir, exist_ok=True)
        self._setup_logger()

    @property
    def default_settings(self) -> AppSettings:
        return AppSettings()

    def _setup_logger(self) -> None:
        if ConfigManager._file_logger_configured:
            return
        logger.add(
            os.path.join(self.log_dir, "impact_rpa_{time:YYYY-MM-DD}.log"),
            rotation="1 day",
            retention="7 days",
            level="INFO",
            format="{time:YYYY-MM-DD HH:mm:ss} | {level} | {message}",
            encoding="utf-8",
        )
        ConfigManager._file_logger_configured = True

    def load_settings(self) -> AppSettings:
        try:
            if os.path.exists(self.settings_file):
                with open(self.settings_file, "r", encoding="utf-8") as f:
                    raw = json.load(f) or {}
                return AppSettings.model_validate(raw)
        except ValidationError as e:
            logger.error(f"加载设置失败（校验错误）: {e}")
        except Exception as e:
            logger.error(f"加载设置失败: {e}")
        return AppSettings()

    def save_settings(self, settings: AppSettings) -> bool:
        try:
            with open(self.settings_file, "w", encoding="utf-8") as f:
                json.dump(settings.model_dump(mode="json"), f, indent=4)
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
