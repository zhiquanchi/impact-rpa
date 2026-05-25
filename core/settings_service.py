from core.config_manager import ConfigManager
from core.settings_models import AppSettings


class SettingsService:
    """统一 settings 读写。"""

    def __init__(self, config: ConfigManager):
        self.config = config

    def load(self) -> AppSettings:
        return self.config.load_settings()

    def save(self, settings: AppSettings) -> bool:
        return self.config.save_settings(settings)

    def get_snapshot(self) -> AppSettings:
        return self.load()
