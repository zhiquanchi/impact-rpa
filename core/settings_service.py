import copy
from core.config_manager import ConfigManager


def deep_merge(base: dict, override: dict) -> dict:
    merged = copy.deepcopy(base)
    for key, value in (override or {}).items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


class SettingsService:
    """统一 settings 读写，并对嵌套配置做深合并。"""

    def __init__(self, config: ConfigManager):
        self.config = config

    def load(self) -> dict:
        raw = self.config.load_settings() or {}
        return deep_merge(self.config.default_settings, raw)

    def save(self, settings: dict) -> bool:
        normalized = deep_merge(self.config.default_settings, settings or {})
        return self.config.save_settings(normalized)

    def get_snapshot(self) -> dict:
        return self.load()

