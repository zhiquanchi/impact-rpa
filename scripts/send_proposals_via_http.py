"""
Replay Impact proposal flow via direct HTTP requests.

Usage:
    python scripts/send_proposals_via_http.py --config config/http_flow.json --max-count 10

How to use with go-mitmproxy:
1. Start go-mitmproxy and route browser traffic through it.
2. Manually complete one successful "Send Proposal" in Impact UI.
3. Copy request URLs/methods/headers/body from captured flows.
4. Fill config/http_flow.json based on config/http_flow.example.json.
5. Run this script to execute the same flow directly via HTTP.
"""

from __future__ import annotations

import argparse
import copy
import json
import re
import ssl
import time
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin
from urllib.request import Request, urlopen

from loguru import logger


PLACEHOLDER_PATTERN = re.compile(r"\{\{\s*([a-zA-Z0-9_]+)\s*\}\}")


def _default_json_headers() -> dict[str, str]:
    return {
        "Accept": "application/json, text/plain, */*",
        "Content-Type": "application/json",
    }


def _build_ssl_context(verify_tls: bool) -> ssl.SSLContext | None:
    if verify_tls:
        return None
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    return ctx


def _get_by_path(obj: Any, path: str, default: Any = None) -> Any:
    cur = obj
    if not path:
        return cur
    for part in path.split("."):
        if isinstance(cur, dict):
            cur = cur.get(part, default)
        elif isinstance(cur, list):
            if not part.isdigit():
                return default
            idx = int(part)
            if idx < 0 or idx >= len(cur):
                return default
            cur = cur[idx]
        else:
            return default
        if cur is default:
            return default
    return cur


def _render_placeholders(value: Any, context: dict[str, Any]) -> Any:
    if isinstance(value, dict):
        return {k: _render_placeholders(v, context) for k, v in value.items()}
    if isinstance(value, list):
        return [_render_placeholders(v, context) for v in value]
    if isinstance(value, str):
        def _replace(match: re.Match[str]) -> str:
            key = match.group(1)
            resolved = context.get(key)
            return "" if resolved is None else str(resolved)

        return PLACEHOLDER_PATTERN.sub(_replace, value)
    return value


@dataclass
class HttpResult:
    status_code: int
    headers: dict[str, str]
    body: str
    json_body: dict[str, Any] | list[Any] | None


class HttpFlowRunner:
    def __init__(self, config: dict[str, Any]):
        self.config = config
        self.base_url = config["base_url"].rstrip("/")
        self.timeout_seconds = int(config.get("timeout_seconds", 30))
        self.verify_tls = bool(config.get("verify_tls", True))
        self.ssl_context = _build_ssl_context(self.verify_tls)
        self.retry_count = int(config.get("retry_count", 2))
        self.retry_delay_seconds = float(config.get("retry_delay_seconds", 1.0))
        self.common_headers = {
            **_default_json_headers(),
            **(config.get("common_headers") or {}),
        }
        cookie = (config.get("cookie") or "").strip()
        if cookie:
            self.common_headers["Cookie"] = cookie

    def _request(
        self,
        method: str,
        path_or_url: str,
        headers: dict[str, str] | None = None,
        query: dict[str, Any] | None = None,
        body: Any = None,
    ) -> HttpResult:
        url = path_or_url if path_or_url.startswith("http") else urljoin(f"{self.base_url}/", path_or_url.lstrip("/"))
        if query:
            from urllib.parse import urlencode
            sep = "&" if "?" in url else "?"
            url = f"{url}{sep}{urlencode(query)}"

        request_headers = {**self.common_headers, **(headers or {})}
        data: bytes | None = None
        if body is not None:
            data = json.dumps(body, ensure_ascii=False).encode("utf-8")

        req = Request(url=url, method=method.upper(), headers=request_headers, data=data)

        for attempt in range(1, self.retry_count + 2):
            try:
                with urlopen(req, timeout=self.timeout_seconds, context=self.ssl_context) as resp:
                    raw = resp.read()
                    text = raw.decode("utf-8", errors="replace")
                    parsed_json = None
                    try:
                        parsed_json = json.loads(text) if text else None
                    except json.JSONDecodeError:
                        parsed_json = None
                    return HttpResult(
                        status_code=resp.status,
                        headers=dict(resp.headers.items()),
                        body=text,
                        json_body=parsed_json,
                    )
            except HTTPError as e:
                err_body = e.read().decode("utf-8", errors="replace")
                logger.error("HTTP {} {} failed: status={}, body={}", method, url, e.code, err_body[:500])
                if attempt > self.retry_count:
                    raise
            except URLError as e:
                logger.error("HTTP {} {} failed: {}", method, url, e)
                if attempt > self.retry_count:
                    raise

            logger.warning("Retrying request ({}/{}) after {}s", attempt, self.retry_count + 1, self.retry_delay_seconds)
            time.sleep(self.retry_delay_seconds)

        raise RuntimeError("unexpected request flow failure")

    def run_endpoint(self, endpoint_name: str, context: dict[str, Any]) -> HttpResult:
        endpoints = self.config.get("endpoints") or {}
        endpoint = endpoints.get(endpoint_name)
        if not endpoint:
            raise KeyError(f"missing endpoint config: {endpoint_name}")

        method = endpoint.get("method", "GET")
        path = _render_placeholders(endpoint.get("path", ""), context)
        query = _render_placeholders(endpoint.get("query"), context)
        body = _render_placeholders(copy.deepcopy(endpoint.get("body")), context)
        headers = _render_placeholders(endpoint.get("headers"), context) or {}

        logger.info("-> endpoint={} method={} path={}", endpoint_name, method, path)
        result = self._request(method=method, path_or_url=path, headers=headers, query=query, body=body)
        logger.info("<- endpoint={} status={}", endpoint_name, result.status_code)
        return result


def _load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"config file not found: {path}")
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def _resolve_creators(config: dict[str, Any], runner: HttpFlowRunner, runtime_ctx: dict[str, Any]) -> list[dict[str, Any]]:
    creators = config.get("creators") or []
    if creators:
        return creators

    discovery = config.get("discovery") or {}
    endpoint_name = discovery.get("endpoint")
    if not endpoint_name:
        return []

    result = runner.run_endpoint(endpoint_name, runtime_ctx)
    if not isinstance(result.json_body, (dict, list)):
        return []

    items_path = discovery.get("items_path", "")
    items = _get_by_path(result.json_body, items_path) if items_path else result.json_body
    if not isinstance(items, list):
        return []

    id_field = discovery.get("id_field", "psi")
    name_field = discovery.get("name_field", "name")
    category_field = discovery.get("category_field")

    normalized: list[dict[str, Any]] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        psi = item.get(id_field)
        if not psi:
            continue
        row = {"psi": psi, "name": item.get(name_field, "")}
        if category_field:
            row["category"] = item.get(category_field, "")
        normalized.append(row)
    return normalized


def run_flow(config: dict[str, Any], max_count: int | None = None) -> int:
    runner = HttpFlowRunner(config)
    target_count = max_count if max_count is not None else int(config.get("max_count", 10))

    runtime_ctx: dict[str, Any] = {
        "today": date.today().isoformat(),
        "tomorrow": (date.today() + timedelta(days=1)).isoformat(),
        "template_term": config.get("template_term", ""),
        "comment": config.get("comment_template", ""),
        "category": config.get("default_category", ""),
    }

    bootstrap = config.get("bootstrap_requests") or []
    for endpoint_name in bootstrap:
        runner.run_endpoint(endpoint_name, runtime_ctx)

    creators = _resolve_creators(config, runner, runtime_ctx)
    if not creators:
        logger.warning("No creators available. Configure `creators` or `discovery` in config.")
        return 0

    send_endpoint_name = config.get("send_endpoint", "send_proposal")
    per_creator_requests = config.get("per_creator_requests") or []

    sent = 0
    for creator in creators:
        if sent >= target_count:
            break

        row_ctx = {
            **runtime_ctx,
            "psi": creator.get("psi", ""),
            "creator_name": creator.get("name", ""),
            "category": creator.get("category") or runtime_ctx.get("category", ""),
        }

        try:
            for endpoint_name in per_creator_requests:
                runner.run_endpoint(endpoint_name, row_ctx)

            send_result = runner.run_endpoint(send_endpoint_name, row_ctx)
            if 200 <= send_result.status_code < 300:
                sent += 1
                logger.info("[{}/{}] sent proposal for {} ({})", sent, target_count, row_ctx["creator_name"], row_ctx["psi"])
            else:
                logger.warning("send failed for {} status={}", row_ctx["psi"], send_result.status_code)
        except Exception as e:
            logger.error("send failed for {}: {}", row_ctx["psi"], e)

    logger.info("Flow completed: sent={}/{}", sent, target_count)
    return sent


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Send Impact proposals using direct HTTP requests")
    parser.add_argument("--config", required=True, help="Path to http flow JSON config")
    parser.add_argument("--max-count", type=int, default=None, help="Override target count")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    config_path = Path(args.config)
    config = _load_json(config_path)
    run_flow(config, max_count=args.max_count)


if __name__ == "__main__":
    main()
