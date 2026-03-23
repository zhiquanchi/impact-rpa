"""
通过浏览器上下文（iframe 内同步 XHR）调用 Partner Groups 相关接口。

在 Reqable 中抓到设置 Partner Group 的请求后，将 method、URL、headers、body 填入
settings.json 的 partner_groups.api 段；body 支持占位符：
  {{selected_tab}} {{partner_group_name}} {{partner_group_id}} {{creator_psi}} {{psi}}

partner_group_id 来自 partner_groups.id_by_name（按 selected_tab 或去空格后的键查找）。

authorization：若未在 headers 中配置，会在页面内从 localStorage 键名前缀
`_messagingtoken_` 解析 JWT（同站点多 token 时取未过期且 exp 最大者）；也可设置环境变量
IMPACT_PARTNER_GROUPS_AUTHORIZATION。
"""

from __future__ import annotations

import copy
import json
import os
import re
from typing import Any

from loguru import logger

PLACEHOLDER_PATTERN = re.compile(r"\{\{\s*([a-zA-Z0-9_]+)\s*\}\}")


def _render_placeholders(value: Any, ctx: dict[str, str]) -> Any:
    if isinstance(value, str):

        def repl(m: re.Match[str]) -> str:
            key = m.group(1)
            return ctx.get(key, m.group(0))

        return PLACEHOLDER_PATTERN.sub(repl, value)
    if isinstance(value, dict):
        return {k: _render_placeholders(v, ctx) for k, v in value.items()}
    if isinstance(value, list):
        return [_render_placeholders(x, ctx) for x in value]
    return value


def _normalize_tab_key(text: str) -> str:
    return re.sub(r"\s+", "", text or "")


def _build_context(selected_tab: str, id_by_name: dict[str, str] | None) -> dict[str, str]:
    norm = _normalize_tab_key(selected_tab)
    mapping = id_by_name or {}
    pid = (
        mapping.get(selected_tab, "")
        or mapping.get(norm, "")
        or mapping.get(selected_tab.strip(), "")
        or ""
    )
    return {
        "selected_tab": selected_tab,
        "partner_group_name": selected_tab,
        "partner_group_id": str(pid) if pid is not None else "",
    }


def _extract_creator_psi(iframe) -> str:
    """
    从当前页面 URL / iframe src / data 属性中提取 creator psi。
    """
    js = """
(function() {
  function pick(urlText) {
    if (!urlText) return "";
    try {
      var u = new URL(urlText, location.origin);
      return (
        u.searchParams.get("slideout_psi") ||
        u.searchParams.get("psi") ||
        u.searchParams.get("partner_psi") ||
        ""
      );
    } catch (e) {
      return "";
    }
  }
  var psi = pick(location.href);
  if (!psi && document.referrer) psi = pick(document.referrer);
  if (!psi && window.frameElement && window.frameElement.src) psi = pick(window.frameElement.src);
  try {
    if (!psi && window.parent && window.parent !== window) {
      psi = pick(window.parent.location.href);
    }
  } catch (e) {}
  if (!psi) {
    var el = document.querySelector("[data-psi],[data-partner-id]");
    if (el) psi = el.getAttribute("data-psi") || el.getAttribute("data-partner-id") || "";
  }
  return psi || "";
})();
"""
    try:
        val = iframe.run_js(js)
    except Exception:
        val = ""
    if val is None:
        return ""
    if isinstance(val, str):
        return val.strip()
    return str(val).strip()


def set_partner_group_via_api(
    iframe,
    selected_tab: str,
    partner_groups_cfg: dict[str, Any],
    *,
    debug: bool = False,
    creator_psi_override: str | None = None,
) -> None:
    """
    在 iframe/tab 的 window 上用 fetch 发起请求（credentials: include，携带同源 Cookie）。

    说明：DrissionPage 的 run_js 对同步 XMLHttpRequest 往往拿不到返回值，故使用 async fetch
    （run_js 会等待 Promise 结果）。

    Raises:
        RuntimeError: 配置缺失、HTTP 非成功或脚本执行失败。
    """
    api = (partner_groups_cfg or {}).get("api") or {}
    raw_url = (api.get("url") or "").strip()
    if not raw_url:
        raise RuntimeError(
            "partner_groups.mode 为 api 但未配置 partner_groups.api.url；"
            "请用 Reqable 抓取设置 Partner Group 的请求后填入。"
        )

    method = (api.get("method") or "POST").strip().upper()
    id_by_name = partner_groups_cfg.get("id_by_name")
    if not isinstance(id_by_name, dict):
        id_by_name = {}

    ctx = _build_context(selected_tab, id_by_name)
    override = (creator_psi_override or "").strip()
    if override:
        ctx["creator_psi"] = override
        ctx["psi"] = override
    else:
        creator_psi = _extract_creator_psi(iframe)
        if creator_psi:
            ctx["creator_psi"] = creator_psi
            ctx["psi"] = creator_psi
        else:
            ctx.setdefault("creator_psi", "")
            ctx.setdefault("psi", "")
    headers_in = copy.deepcopy(api.get("headers") or {})
    if not isinstance(headers_in, dict):
        headers_in = {}
    headers_rendered = _render_placeholders(headers_in, ctx)
    headers: dict[str, str] = {str(k): str(v) for k, v in headers_rendered.items()}
    blocked = {"cookie", "host", "content-length"}
    headers = {k: v for k, v in headers.items() if k.lower() not in blocked}

    env_auth = (os.environ.get("IMPACT_PARTNER_GROUPS_AUTHORIZATION") or "").strip()
    if env_auth and "authorization" not in {k.lower() for k in headers}:
        headers["authorization"] = env_auth

    body_template = api.get("body")
    body_json_str: str | None = None
    if body_template is not None and method not in ("GET", "HEAD"):
        rendered = _render_placeholders(copy.deepcopy(body_template), ctx)
        if isinstance(rendered, dict) and rendered.get("psi") in ("", None):
            raise RuntimeError(
                "Partner Group API：body 中 psi 为空。请在父页 URL 含 slideout_psi 时打开弹窗，"
                "或调用时传入 creator_psi_override（实机脚本可用 --psi）。"
            )
        body_json_str = json.dumps(rendered, ensure_ascii=False)
        headers.setdefault("Content-Type", "application/json")

    csrf_meta_selector = (api.get("csrf_meta_selector") or "").strip() or None
    csrf_header_name = (api.get("csrf_header_name") or "").strip() or None

    min_status = int(api.get("success_status_min", 200))
    max_status = int(api.get("success_status_max", 299))

    script = f"""
return (async function() {{
  try {{
    function jwtExp(jwt) {{
      try {{
        var parts = String(jwt).split(".");
        if (parts.length < 2) return 0;
        var b = parts[1].replace(/-/g, "+").replace(/_/g, "/");
        while (b.length % 4) b += "=";
        var json = atob(b);
        var p = JSON.parse(json);
        return typeof p.exp === "number" ? p.exp : 0;
      }} catch (e) {{
        return 0;
      }}
    }}
    function tryFindJwt() {{
      var candidates = [
        "access_token", "id_token", "jwt", "token", "authToken", "auth_token",
        "bearer", "impact_token", "ipc_token"
      ];
      var i, k, v, prefix = "_messagingtoken_";
      var best = "", bestExp = 0, now = Math.floor(Date.now() / 1000);
      for (i = 0; i < localStorage.length; i++) {{
        k = localStorage.key(i);
        if (k && k.indexOf(prefix) === 0) {{
          v = k.slice(prefix.length);
          if (!v || !/^eyJ/.test(v)) continue;
          var exp = jwtExp(v);
          if (exp >= now && exp >= bestExp) {{
            bestExp = exp;
            best = v;
          }}
        }}
      }}
      if (best) return best;
      for (i = 0; i < localStorage.length; i++) {{
        k = localStorage.key(i);
        if (k && k.indexOf(prefix) === 0) {{
          v = k.slice(prefix.length);
          if (v && /^eyJ/.test(v)) return v;
        }}
      }}
      for (i = 0; i < candidates.length; i++) {{
        k = candidates[i];
        v = localStorage.getItem(k) || sessionStorage.getItem(k);
        if (v && /^eyJ/.test(String(v).trim())) return String(v).trim();
      }}
      for (i = 0; i < localStorage.length; i++) {{
        k = localStorage.key(i);
        v = localStorage.getItem(k);
        if (!v) continue;
        v = String(v).trim();
        if (/^eyJ[A-Za-z0-9_-]+\\.[A-Za-z0-9_-]+\\.[A-Za-z0-9_-]+$/.test(v)) return v;
      }}
      return "";
    }}
    function hasAuthHeader(h) {{
      var key;
      for (key in h) {{
        if (h.hasOwnProperty(key) && String(key).toLowerCase() === "authorization") return true;
      }}
      return false;
    }}
    var rawUrl = {json.dumps(raw_url)};
    var method = {json.dumps(method)};
    var headers = {json.dumps(headers)};
    var bodyJson = {json.dumps(body_json_str)};
    var metaSel = {json.dumps(csrf_meta_selector or "")};
    var csrfHdr = {json.dumps(csrf_header_name or "")};
    if (metaSel && csrfHdr) {{
      var el = document.querySelector(metaSel);
      var tok = el && (el.content || el.getAttribute("content"));
      if (tok) headers[csrfHdr] = tok;
    }}
    if (!hasAuthHeader(headers)) {{
      var j = tryFindJwt();
      if (j) headers["authorization"] = j;
    }}
    var url;
    try {{
      url = new URL(rawUrl, location.origin).href;
    }} catch (e) {{
      return JSON.stringify({{ ok: false, error: "bad_url", detail: String(e) }});
    }}
    var init = {{ method: method, headers: headers, credentials: "include" }};
    if (bodyJson !== null && method !== "GET" && method !== "HEAD") {{
      init.body = bodyJson;
    }}
    var res = await fetch(url, init);
    var text = await res.text();
    return JSON.stringify({{
      ok: res.status >= {min_status} && res.status <= {max_status},
      status: res.status,
      text: text.length > 12000 ? text.slice(0, 12000) : text
    }});
  }} catch (e) {{
    return JSON.stringify({{ ok: false, error: "fetch_exception", detail: String(e) }});
  }}
}})();
"""

    if debug:
        logger.info(
            "[PartnerGroupsDebug] API 模式: method={} url(模板)={} context={}",
            method,
            raw_url,
            ctx,
        )

    raw = iframe.run_js(script)
    if raw is None:
        raise RuntimeError("Partner Group API：run_js 无返回值")

    if isinstance(raw, str):
        try:
            data = json.loads(raw)
        except json.JSONDecodeError as e:
            raise RuntimeError(f"Partner Group API：无法解析 JS 返回: {raw[:500]!r}") from e
    elif isinstance(raw, dict):
        data = raw
    else:
        raise RuntimeError(f"Partner Group API：意外返回类型 {type(raw)!r}")

    if data.get("error") == "bad_url":
        raise RuntimeError(f"Partner Group API：URL 无效 — {data.get('detail')}")
    if data.get("error") == "fetch_exception":
        raise RuntimeError(f"Partner Group API：fetch 异常 — {data.get('detail')}")

    status = int(data.get("status", 0))
    if not data.get("ok"):
        snippet = (data.get("text") or "")[:2000]
        raise RuntimeError(f"Partner Group API 失败: HTTP {status} body[:2000]={snippet!r}")

    logger.info("Partner Group 已通过 API 设置（HTTP {}）", status)


__all__ = ["set_partner_group_via_api"]
