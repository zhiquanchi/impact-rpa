"""
通过接口自动创建 Partner Group。

用法示例：
    uv run python scripts/create_partner_groups_api.py "Network" "Deal/Coupons"
    uv run python scripts/create_partner_groups_api.py --file groups.txt

说明：
    - 依赖当前已打开并登录 Impact 的 Chrome/Edge
    - 使用浏览器同源上下文里的 fetch 提交表单，不模拟点击
    - 默认跳过已存在的 Group 名称
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any, Iterable

from loguru import logger
from rich.console import Console

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from legacy_main import BrowserManager, ConfigManager  # noqa: E402
from scripts.batch_create_partner_groups import (  # noqa: E402
    get_partner_group_names_from_myMediaPartnerGroupsJSON,
)

GROUPS_URL = (
    "https://app.impact.com/secure/advertiser/engage/mediapartners/"
    "view-mediapartnergroups-flow.ihtml"
)


def _load_names_from_file(path: Path) -> list[str]:
    if not path.is_file():
        raise FileNotFoundError(f"找不到文件: {path}")
    names: list[str] = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        name = raw.strip()
        if name:
            names.append(name)
    return names


def _dedupe_names(names: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for name in names:
        value = name.strip()
        if not value or value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result


def _group_exists(group_name: str, existing_groups: list[str]) -> bool:
    """兼容列表页里 `Name (id)` 的展示格式。"""
    for existing in existing_groups:
        if existing == group_name:
            return True
        if existing.startswith(group_name):
            return True
        if group_name in existing:
            return True
    return False


def _get_groups_tab(browser):
    tabs = browser.get_tabs(url="view-mediapartnergroups-flow.ihtml")
    if tabs:
        groups_tab = tabs[0]
        logger.info("复用已打开的 Partner Groups 标签页。")
    else:
        logger.info("未找到 Partner Groups 标签页，新开一个。")
        groups_tab = browser.new_tab(url=GROUPS_URL)

    try:
        browser.activate_tab(groups_tab)
    except Exception as e:
        logger.debug("activate_tab 失败: {}", e)

    return groups_tab


def _run_api_create_script(page, group_name: str) -> dict[str, Any]:
    """在页面同源上下文里直接提交创建请求。"""
    script = f"""
return (async function() {{
  function findCsrfToken() {{
    try {{
      if (typeof window.getCsrfToken === "function") {{
        var token = window.getCsrfToken();
        if (token) return String(token).trim();
      }}
    }} catch (e) {{}}
    try {{
      var meta = document.querySelector('meta[name="uitk_csrf"]');
      if (meta) {{
        var token = meta.content || meta.getAttribute("content") || "";
        if (token) return String(token).trim();
      }}
    }} catch (e) {{}}
    try {{
      var input = document.querySelector('input[name="uitk_csrf"]');
      if (input) {{
        var token = input.value || input.getAttribute("value") || "";
        if (token) return String(token).trim();
      }}
    }} catch (e) {{}}
    try {{
      var u = new URL(location.href);
      var token = u.searchParams.get("uitk_csrf") || "";
      if (token) return String(token).trim();
    }} catch (e) {{}}
    return "";
  }}

  async function postForm(url, fields) {{
    var body = new URLSearchParams(fields);
    var res = await fetch(url, {{
      method: "POST",
      credentials: "include",
      headers: {{
        "Content-Type": "application/x-www-form-urlencoded;charset=UTF-8"
      }},
      body: body.toString()
    }});
    var text = await res.text();
    return {{
      ok: res.ok,
      status: res.status,
      url: res.url,
      text: text.slice(0, 4000)
    }};
  }}

  function extractFormAction(html) {{
    if (!html) return "";
    var match = String(html).match(/<form[^>]+action=\"([^\"]+)\"/i);
    if (!match) return "";
    var action = match[1].replace(/&amp;/g, "&");
    try {{
      return new URL(action, location.origin).href;
    }} catch (e) {{
      return action;
    }}
  }}

  var groupName = {json.dumps(group_name)};
  var current = new URL(location.href);
  var csrf = findCsrfToken();
  if (!csrf) {{
    return JSON.stringify({{
      ok: false,
      error: "missing_csrf",
      detail: "无法从当前页面解析 uitk_csrf"
    }});
  }}

  var hasForm = !!document.querySelector('input[name="publisherGroupName"]');
  var form = document.querySelector('form.iui-web-form');
  var submitUrl = form ? form.action : current.href;
  var openInfo = null;

  if (!hasForm) {{
    var execution = current.searchParams.get("execution") || "";
    if (!execution) {{
      return JSON.stringify({{
        ok: false,
        error: "missing_execution",
        detail: "当前 URL 中没有 execution 参数"
      }});
    }}

    var openUrl = current.origin + current.pathname + "?execution=" + encodeURIComponent(execution) + "&uitk_csrf=" + encodeURIComponent(csrf);
    openInfo = await postForm(openUrl, {{
      _eventId: "addPublisherGroup",
      hasFilters: "true",
      fqe__grp: "",
      execution: execution,
      uitk_csrf: csrf
    }});
    submitUrl = extractFormAction(openInfo.text) || openInfo.url || openUrl;
  }}

  var submitInfo = await postForm(submitUrl, {{
    publisherGroupName: groupName,
    _eventId: "submit"
  }});

  return JSON.stringify({{
    ok: submitInfo.ok,
    csrf: csrf,
    hasForm: hasForm,
    openInfo: openInfo,
    submitInfo: submitInfo
  }});
}})();
"""
    raw = page.run_js(script)
    if raw is None:
        raise RuntimeError("API 创建脚本没有返回值")
    if isinstance(raw, dict):
        data = raw
    elif isinstance(raw, str):
        try:
            data = json.loads(raw)
        except json.JSONDecodeError as e:
            raise RuntimeError(f"无法解析 API 创建脚本返回值: {raw[:500]!r}") from e
    else:
        raise RuntimeError(f"意外返回类型: {type(raw)!r}")
    return data


def _create_group_api(page, group_name: str) -> None:
    logger.info("准备通过接口创建 Group: {}", group_name)
    result = _run_api_create_script(page, group_name)

    if result.get("error"):
        raise RuntimeError(f"接口创建失败: {result.get('error')} — {result.get('detail')}")

    submit_info = result.get("submitInfo") or {}
    status = int(submit_info.get("status", 0))
    if not result.get("ok") or not (200 <= status < 400):
        snippet = (submit_info.get("text") or "")[:1500]
        raise RuntimeError(f"接口创建失败: HTTP {status} body[:1500]={snippet!r}")

    logger.info(
        "接口创建请求已发送: status={} url={}",
        status,
        submit_info.get("url") or "",
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="通过接口自动创建 Partner Group")
    parser.add_argument(
        "names",
        nargs="*",
        help="要创建的 Partner Group 名称，支持多个",
    )
    parser.add_argument(
        "-f",
        "--file",
        type=Path,
        help="从文本文件读取名称，每行一个",
    )
    parser.add_argument(
        "--no-skip-existing",
        dest="skip_existing",
        action="store_false",
        help="不要跳过已存在的 Group",
    )
    parser.add_argument(
        "--skip-existing",
        dest="skip_existing",
        action="store_true",
        default=True,
        help="跳过已存在的 Group（默认）",
    )
    parser.add_argument(
        "--pause",
        type=float,
        default=0.5,
        help="每次创建后的暂停秒数，避免请求过快",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    names: list[str] = []
    if args.file:
        names.extend(_load_names_from_file(args.file))
    names.extend(args.names)
    names = _dedupe_names(names)

    if not names:
        logger.error("请至少提供一个 Partner Group 名称，或使用 --file 读取。")
        return 2

    console = Console()
    config = ConfigManager(base_dir=str(REPO_ROOT))
    browser_manager = BrowserManager(console=console, config=config)

    if not browser_manager.init():
        logger.error("BrowserManager 初始化失败：无法连接浏览器")
        return 1

    browser = getattr(browser_manager, "browser", None)
    if browser is None:
        logger.error("browser 为空")
        return 1

    groups_tab = _get_groups_tab(browser)
    existing_groups = get_partner_group_names_from_myMediaPartnerGroupsJSON(groups_tab) or []
    logger.info("当前已有 Partner Groups: {}", len(existing_groups))

    created = 0
    skipped = 0
    failed = 0

    for index, group_name in enumerate(names, start=1):
        if args.skip_existing and _group_exists(group_name, existing_groups):
            logger.info("[{}/{}] 已存在，跳过: {}", index, len(names), group_name)
            skipped += 1
            continue

        try:
            _create_group_api(groups_tab, group_name)
            created += 1
            existing_groups.append(group_name)
            logger.info("[{}/{}] 创建成功: {}", index, len(names), group_name)
        except Exception as e:
            failed += 1
            logger.exception("[{}/{}] 创建失败: {} — {}", index, len(names), group_name, e)

        if args.pause > 0 and index < len(names):
            time.sleep(args.pause)

    logger.info(
        "执行完成：total={} created={} skipped={} failed={}",
        len(names),
        created,
        skipped,
        failed,
    )
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
