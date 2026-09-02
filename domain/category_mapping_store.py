"""businessModels 分类映射的持久化存储与手动刷新采集。

映射（value -> label，如 "COMMERCE_SOLUTION" -> "Technology Solutions"）很少变动，
平时从配置文件 config/category_mapping.json 读取；GUI 的「分类映射」按钮
手动触发重新采集（打开/刷新 discovery 页捕获 tablestructure 接口）并写回。
"""

from __future__ import annotations

import json
import time
from datetime import datetime
from pathlib import Path

from loguru import logger

MAPPING_FILENAME = "category_mapping.json"

DISCOVERY_URL = (
    "https://app.impact.com/secure/advertiser/discover/radius/fr/"
    "partner_discover.ihtml?page=marketplace&slideout_id_type=partner"
)
TABLESTRUCTURE_KEYWORD = "partner-ui/api/discover/tablestructure"


def mapping_path(config_dir: str | Path) -> Path:
    return Path(config_dir) / MAPPING_FILENAME


def load_mapping(path: str | Path) -> dict[str, str]:
    """读取持久化的映射；文件缺失或损坏返回空 dict。"""
    try:
        p = Path(path)
        if not p.exists():
            return {}
        data = json.loads(p.read_text(encoding="utf-8"))
        raw = data.get("businessModels") if isinstance(data, dict) else None
        if not isinstance(raw, dict):
            return {}
        return {
            str(k).strip(): str(v).strip()
            for k, v in raw.items()
            if str(k).strip() and str(v).strip()
        }
    except Exception as e:
        logger.debug(f"读取分类映射缓存失败: {e}")
        return {}


def save_mapping(path: str | Path, mapping: dict[str, str]) -> bool:
    """写入映射文件，附带更新时间。"""
    try:
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(
            json.dumps(
                {
                    "updatedAt": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    "businessModels": mapping,
                },
                indent=2,
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        return True
    except Exception as e:
        logger.warning(f"写入分类映射缓存失败: {e}")
        return False


def refresh_mapping_from_browser(browser, path: str | Path) -> tuple[int, str]:
    """连接浏览器采集最新映射并写入配置文件。

    找已打开的 discovery 页刷新；没有则新开一个（采集完关闭）。
    Returns:
        (捕获的映射项数, 结果消息)
    """
    tab = None
    for t in browser.browser.get_tabs():
        if "partner_discover" in (t.url or ""):
            tab = t
            break

    opened_new = tab is None
    if opened_new:
        tab = browser.browser.new_tab(DISCOVERY_URL)

    mapping: dict[str, str] = {}
    try:
        try:
            tab.listen.start(TABLESTRUCTURE_KEYWORD, is_regex=False)
            if opened_new:
                try:
                    tab.wait.doc_loaded(timeout=15)
                except Exception:
                    pass
            else:
                tab.refresh()
                try:
                    tab.wait.doc_loaded(timeout=15)
                except Exception:
                    pass

            deadline = time.time() + 10
            while time.time() < deadline:
                packet = tab.listen.wait(timeout=1)
                if not packet:
                    continue
                if TABLESTRUCTURE_KEYWORD not in (getattr(packet, "url", "") or ""):
                    continue
                try:
                    body = packet.response.body
                except Exception:
                    continue
                mapping = _extract_business_models(body)
                if mapping:
                    break
        finally:
            try:
                tab.listen.stop()
            except Exception:
                pass
    finally:
        if opened_new:
            try:
                tab.close()
            except Exception:
                pass

    if not mapping:
        return 0, "未捕获到 tablestructure 数据，请确认浏览器已登录 Impact 并停留在发现页"

    save_mapping(path, mapping)
    logger.info(f"分类映射已更新并写入 {path}（{len(mapping)} 项）")
    return len(mapping), f"已捕获 {len(mapping)} 项分类映射并写入配置文件"


def _extract_business_models(body) -> dict[str, str]:
    """从 tablestructure 响应体提取 businessModels 的 value->label 映射。"""
    if not isinstance(body, dict):
        return {}
    try:
        widget = body.get("searchWidget") or {}
        for ft in widget.get("filterTypes") or []:
            if not isinstance(ft, dict) or ft.get("parameterName") != "businessModels":
                continue
            items = ft.get("filterValues")
            if not isinstance(items, list):
                continue
            mapping: dict[str, str] = {}
            for item in items:
                if not isinstance(item, dict):
                    continue
                value = (item.get("value") or "").strip()
                label = (item.get("label") or "").strip()
                if value and label:
                    mapping[value] = label
            return mapping
    except Exception as e:
        logger.debug(f"解析 tablestructure 失败: {e}")
    return {}


__all__ = [
    "MAPPING_FILENAME",
    "mapping_path",
    "load_mapping",
    "save_mapping",
    "refresh_mapping_from_browser",
]
