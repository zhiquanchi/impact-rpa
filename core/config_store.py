import json
import os
import threading
import time
from collections.abc import Callable
from typing import Any

from loguru import logger

from core.config_manager import ConfigManager


ConfigKind = str  # "settings" | "templates"
Subscriber = Callable[[ConfigKind, dict], None]


class ConfigStore:
    """
    进程内配置缓存 + 文件变更监听（轮询）+ 订阅通知。

    目标：
    - 外部编辑 config/settings.json、config/templates.json、config/template.txt 后无需重启生效
    - 应用内保存配置后立即刷新缓存并通知订阅者
    """

    def __init__(self, config: ConfigManager):
        self._config = config
        self._lock = threading.RLock()

        self._settings_cache: dict[str, Any] | None = None
        self._templates_cache: dict[str, Any] | None = None

        self._mtimes: dict[str, float | None] = {
            "settings": None,
            "templates_json": None,
            "template_txt": None,
        }

        self._subscribers: dict[ConfigKind, list[Subscriber]] = {"settings": [], "templates": []}

        self._watch_thread: threading.Thread | None = None
        self._watch_stop = threading.Event()
        self._watch_interval_s = 0.8

    # ----------------------------
    # Public API
    # ----------------------------
    def subscribe(self, kind: ConfigKind, callback: Subscriber) -> None:
        if kind not in self._subscribers:
            raise ValueError(f"unknown kind: {kind}")
        with self._lock:
            self._subscribers[kind].append(callback)

    def get_settings(self) -> dict[str, Any]:
        with self._lock:
            if self._settings_cache is None:
                self._reload_settings_locked(notify=False)
            return dict(self._settings_cache or {})

    def get_templates_data(self) -> dict[str, Any]:
        with self._lock:
            if self._templates_cache is None:
                self._reload_templates_locked(notify=False)
            return dict(self._templates_cache or {})

    def force_reload_settings(self) -> dict[str, Any]:
        with self._lock:
            return self._reload_settings_locked(notify=True)

    def force_reload_templates(self) -> dict[str, Any]:
        with self._lock:
            return self._reload_templates_locked(notify=True)

    def reload_if_changed(self) -> None:
        with self._lock:
            changed_settings = self._settings_changed_locked()
            changed_templates = self._templates_changed_locked()
            if changed_settings:
                self._reload_settings_locked(notify=True)
            if changed_templates:
                self._reload_templates_locked(notify=True)

    def start_watching(self, interval_s: float = 0.8) -> None:
        with self._lock:
            self._watch_interval_s = max(0.2, float(interval_s))
            if self._watch_thread and self._watch_thread.is_alive():
                return
            self._watch_stop.clear()
            t = threading.Thread(target=self._watch_loop, name="ConfigStoreWatcher", daemon=True)
            self._watch_thread = t
            t.start()

    def stop_watching(self, timeout_s: float = 2.0) -> None:
        self._watch_stop.set()
        t = None
        with self._lock:
            t = self._watch_thread
        if t and t.is_alive():
            t.join(timeout=max(0.1, float(timeout_s)))

    # ----------------------------
    # Internal: watcher & change detection
    # ----------------------------
    def _watch_loop(self) -> None:
        while not self._watch_stop.is_set():
            try:
                self.reload_if_changed()
            except Exception as e:
                logger.debug(f"ConfigStore watcher error: {e}")
            self._watch_stop.wait(self._watch_interval_s)

    def _safe_mtime(self, path: str) -> float | None:
        try:
            return os.path.getmtime(path) if os.path.exists(path) else None
        except Exception:
            return None

    def _settings_changed_locked(self) -> bool:
        new_mtime = self._safe_mtime(self._config.settings_file)
        old = self._mtimes.get("settings")
        if old is None and new_mtime is None:
            return False
        if old != new_mtime:
            self._mtimes["settings"] = new_mtime
            return True
        return False

    def _templates_changed_locked(self) -> bool:
        tj = self._safe_mtime(self._config.templates_file)
        tt = self._safe_mtime(self._config.template_file)

        changed = False
        if self._mtimes.get("templates_json") != tj:
            self._mtimes["templates_json"] = tj
            changed = True
        if self._mtimes.get("template_txt") != tt:
            self._mtimes["template_txt"] = tt
            changed = True
        return changed

    def _notify_locked(self, kind: ConfigKind, payload: dict[str, Any]) -> None:
        callbacks = list(self._subscribers.get(kind, []))
        # 避免订阅者异常阻塞 watcher
        for cb in callbacks:
            try:
                cb(kind, dict(payload))
            except Exception as e:
                logger.debug(f"ConfigStore subscriber error(kind={kind}): {e}")

    # ----------------------------
    # Internal: reload
    # ----------------------------
    def _reload_settings_locked(self, notify: bool) -> dict[str, Any]:
        settings = self._config.load_settings() or {}
        if settings != self._settings_cache:
            self._settings_cache = dict(settings)
            if notify:
                self._notify_locked("settings", self._settings_cache)
        return dict(self._settings_cache or {})

    def _reload_templates_locked(self, notify: bool) -> dict[str, Any]:
        data: dict[str, Any] = {"templates": [], "active_template_id": None}

        try:
            if os.path.exists(self._config.templates_file):
                with open(self._config.templates_file, "r", encoding="utf-8") as f:
                    data = {**data, **(json.load(f) or {})}
            elif os.path.exists(self._config.template_file):
                with open(self._config.template_file, "r", encoding="utf-8") as f:
                    content = (f.read() or "").strip()
                    if content:
                        data = {
                            "templates": [{"id": 1, "name": "默认模板", "content": content}],
                            "active_template_id": 1,
                        }
        except Exception as e:
            logger.error(f"ConfigStore: 加载模板数据失败: {e}")

        if data != self._templates_cache:
            self._templates_cache = dict(data)
            if notify:
                self._notify_locked("templates", self._templates_cache)
        return dict(self._templates_cache or {})

