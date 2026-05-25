import copy

from core.config_manager import ConfigManager


def deep_merge(base: dict[str, object], override: dict[str, object]) -> dict[str, object]:
    merged = copy.deepcopy(base)
    for key, value in (override or {}).items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = deep_merge(merged[key], value)  # type: ignore[arg-type]
        else:
            merged[key] = value
    return merged


def get_int_setting(settings: dict[str, object], key: str, default: int = 0) -> int:
    value = settings.get(key, default)
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str) and value.strip():
        return int(value)
    return default


class SettingsService:
    """统一 settings 读写，并对嵌套配置做深合并。"""

    def __init__(self, config: ConfigManager):
        self.config = config

    def load(self) -> dict[str, object]:
        raw = self.config.load_settings() or {}
        return deep_merge(self.config.default_settings, raw)

    def save(self, settings: dict[str, object]) -> bool:
        normalized = deep_merge(self.config.default_settings, settings or {})
        return self.config.save_settings(normalized)

    def get_snapshot(self) -> dict[str, object]:
        return self.load()
