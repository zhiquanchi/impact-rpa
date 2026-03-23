"""
Partner Groups API 模式冒烟测试（无需登录浏览器）。

验证占位符渲染、mock iframe 下 set_partner_group_via_api 的成功路径。
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

# 保证仓库根在 path
_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from domain import partner_groups_api as pg  # noqa: E402
from domain.partner_groups_api import set_partner_group_via_api  # noqa: E402


class _FakeIframe:
    def __init__(self, psi: str) -> None:
        self.psi = psi
        self.xhr_scripts: list[str] = []

    def run_js(self, script: str):
        if "fetch(" in script:
            self.xhr_scripts.append(script)
            return json.dumps({"ok": True, "status": 200, "text": "{}"})
        return self.psi


def test_placeholders() -> None:
    ctx = {
        **pg._build_context("Network", {}),
        "creator_psi": "1eff5966-f4f4-6455-af61-35f26236132e",
        "psi": "1eff5966-f4f4-6455-af61-35f26236132e",
    }
    body = pg._render_placeholders(
        {"psi": "{{creator_psi}}", "groups": ["{{selected_tab}}"]},
        ctx,
    )
    assert body == {
        "psi": "1eff5966-f4f4-6455-af61-35f26236132e",
        "groups": ["Network"],
    }, body


def test_set_via_api_mock() -> None:
    psi = "1eff5966-f4f4-6455-af61-35f26236132e"
    fake = _FakeIframe(psi)
    cfg = {
        "api": {
            "url": "https://app.impact.com/partner-ui/api/relationship/groups",
            "method": "PUT",
            "headers": {"Content-Type": "application/json"},
            "body": {"psi": "{{creator_psi}}", "groups": ["{{selected_tab}}"]},
        }
    }
    set_partner_group_via_api(fake, "Network", cfg, debug=False)
    assert len(fake.xhr_scripts) == 1
    s = fake.xhr_scripts[0]
    assert "partner-ui/api/relationship/groups" in s
    assert "PUT" in s
    assert psi in s
    assert "Network" in s


def main() -> int:
    test_placeholders()
    test_set_via_api_mock()
    print("partner_groups_api smoke: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
