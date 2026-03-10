import json
import os
from loguru import logger
from core.config_manager import ConfigManager


class TemplateManager:
    """模板管理类，负责处理留言模板的CRUD操作。"""

    def __init__(self, config: ConfigManager):
        self.config = config
        self._default_data = {"templates": [], "active_template_id": None}

    def load_all(self) -> dict:
        try:
            if os.path.exists(self.config.templates_file):
                with open(self.config.templates_file, "r", encoding="utf-8") as f:
                    return {**self._default_data, **json.load(f)}
            elif os.path.exists(self.config.template_file):
                with open(self.config.template_file, "r", encoding="utf-8") as f:
                    content = f.read().strip()
                    if content:
                        return {
                            "templates": [{"id": 1, "name": "默认模板", "content": content}],
                            "active_template_id": 1,
                        }
        except Exception as e:
            logger.error(f"加载模板数据失败: {e}")
        return self._default_data.copy()

    def save_all(self, data: dict) -> bool:
        try:
            with open(self.config.templates_file, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=4, ensure_ascii=False)
            logger.info("模板数据保存成功")
            try:
                if getattr(self.config, "store", None) is not None:
                    self.config.store.force_reload_templates()
            except Exception:
                pass
            return True
        except Exception as e:
            logger.error(f"保存模板数据失败: {e}")
            return False

    def get_active_template(self) -> str:
        try:
            data = self.load_all()
            active_id = data.get("active_template_id", 1)
            for tpl in data.get("templates", []):
                if tpl.get("id") == active_id:
                    return tpl.get("content", "")
            if data.get("templates"):
                return data["templates"][0].get("content", "")
        except Exception as e:
            logger.error(f"加载模板失败: {e}")
        return ""

    def get_active_template_info(self) -> dict | None:
        data = self.load_all()
        active_id = data.get("active_template_id")
        for tpl in data.get("templates", []):
            if tpl.get("id") == active_id:
                return tpl
        return None

    def get_next_id(self, data: dict | None = None) -> int:
        if data is None:
            data = self.load_all()
        if not data.get("templates"):
            return 1
        return max(tpl.get("id", 0) for tpl in data["templates"]) + 1

    def add_template(self, name: str, content: str, activate: bool = True) -> bool:
        try:
            data = self.load_all()
            new_id = self.get_next_id(data)
            data["templates"].append({"id": new_id, "name": name or f"模板 {new_id}", "content": content})
            if activate:
                data["active_template_id"] = new_id
            return self.save_all(data)
        except Exception as e:
            logger.error(f"添加模板失败: {e}")
            return False

    def update_template(self, template_id: int, name: str | None = None, content: str | None = None) -> bool:
        try:
            data = self.load_all()
            for tpl in data["templates"]:
                if tpl.get("id") == template_id:
                    if name is not None:
                        tpl["name"] = name
                    if content is not None:
                        tpl["content"] = content
                    return self.save_all(data)
            return False
        except Exception as e:
            logger.error(f"更新模板失败: {e}")
            return False

    def delete_template(self, template_id: int) -> bool:
        try:
            data = self.load_all()
            if len(data["templates"]) <= 1:
                return False
            data["templates"] = [t for t in data["templates"] if t.get("id") != template_id]
            if template_id == data.get("active_template_id") and data["templates"]:
                data["active_template_id"] = data["templates"][0].get("id")
            return self.save_all(data)
        except Exception as e:
            logger.error(f"删除模板失败: {e}")
            return False

    def set_active(self, template_id: int) -> bool:
        try:
            data = self.load_all()
            data["active_template_id"] = template_id
            return self.save_all(data)
        except Exception as e:
            logger.error(f"设置激活模板失败: {e}")
            return False

