import json
import os
import threading
import requests
from loguru import logger
from core.config_manager import ConfigManager

class RemoteSyncService:
    """
    远程同步服务（观察者）。
    负责在配置变更时同步到云端，以及在启动时拉取配置。
    """
    APP_ID = "impact-rpa"

    def __init__(self, api_base_url: str, uid: str):
        self.api_base_url = api_base_url.rstrip('/')
        self.uid = uid
        self._lock = threading.Lock()

    def pull_and_apply(self, config_manager: ConfigManager):
        """
        从远端拉取最新配置并应用到本地文件。
        建议在程序启动、ConfigStore 启动监听之前调用。
        """
        url = f"{self.api_base_url}/api/sync/{self.APP_ID}/{self.uid}"
        try:
            logger.info(f"正在从云端找回配置 (App: {self.APP_ID}, UID: {self.uid[:8]}...)...")
            # 设置较短的超时，避免服务器宕机导致程序启动过慢
            resp = requests.get(url, timeout=5)
            if resp.status_code == 200:
                data = resp.json()
                configs = data.get("configs", {})
                
                # 更新 settings.json
                if "settings" in configs and configs["settings"]:
                    with open(config_manager.settings_file, "w", encoding="utf-8") as f:
                        json.dump(configs["settings"], f, indent=4, ensure_ascii=False)
                    logger.info("已找回并应用云端设置")

                # 更新 templates.json
                if "templates_data" in configs and configs["templates_data"]:
                    with open(config_manager.templates_file, "w", encoding="utf-8") as f:
                        json.dump(configs["templates_data"], f, indent=4, ensure_ascii=False)
                    logger.info("已找回并应用云端模板")
            elif resp.status_code == 404:
                logger.info("云端暂无此机器的备份记录")
            else:
                logger.warning(f"云端找回失败: HTTP {resp.status_code}")
        except Exception as e:
            logger.error(f"云端找回发生异常: {e}")

    def on_config_changed(self, kind: str, data: dict):
        """
        观察者回调接口。
        kind: "settings" | "templates"
        data: 最新的配置字典
        """
        # 异步推送，不阻塞主流程或 UI
        threading.Thread(
            target=self._push_worker,
            args=(kind, data),
            name=f"SyncWorker-{kind}",
            daemon=True
        ).start()

    def _push_worker(self, kind: str, data: dict):
        """实际执行推送的任务函数"""
        url = f"{self.api_base_url}/api/sync/{self.APP_ID}/{self.uid}"
        
        # 构造负载。后端支持增量更新。
        # 映射字段名以保持向后兼容或符合后端预期
        key = "templates_data" if kind == "templates" else kind
        payload = {"configs": {key: data}}

        try:
            resp = requests.post(url, json=payload, timeout=10)
            if resp.status_code == 200:
                logger.debug(f"云端同步成功 ({kind})")
            else:
                logger.warning(f"云端同步失败 ({kind}): HTTP {resp.status_code}")
        except Exception as e:
            logger.error(f"云端同步异常 ({kind}): {e}")
