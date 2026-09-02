"""补充采集：tab 栏 More 菜单内的分类（Technology Solutions / Search,Comparison 等）。"""
import json
import sys
import time
from urllib.parse import parse_qs, urlparse

sys.path.insert(0, ".")

from DrissionPage import Chromium

LISTINGS = "partner-ui/api/discover/listings"
E1 = 'xpath://*[@id="app"]/div/div[1]/div/div[2]/div[1]'


def drain_last_bms(tab, settle=1.5, timeout=5.0):
    time.sleep(settle)
    deadline = time.time() + timeout
    last = None
    while time.time() < deadline:
        packet = tab.listen.wait(timeout=0.4)
        if not packet:
            if last is not None:
                break
            continue
        url = getattr(packet, "url", "") or ""
        if LISTINGS not in url:
            continue
        qs = parse_qs(urlparse(url).query)
        bm = (qs.get("businessModels") or [""])[0]
        if bm:
            last = bm
            deadline = time.time() + 1.5
    return last


def read_selected(tab):
    try:
        e = tab.ele(E1, timeout=0.5)
        return (e.text or "").strip() if e else ""
    except Exception:
        return ""


def main():
    b = Chromium()
    tab = next(
        (t for t in b.get_tabs() if "partner_discover" in (t.url or "")), None
    )
    if tab is None:
        print("未找到 discovery 页", flush=True)
        return

    tab.listen.start(LISTINGS, is_regex=False)

    more_btn = None
    for item in tab.eles("css:.iui-button-tabs.filter-tabs .iui-tab-item", timeout=3):
        if "more" in (item.text or "").strip().lower():
            more_btn = item
            break
    if more_btn is None:
        print("tab 栏内未找到 More", flush=True)
        return
    print("找到 More 按钮", flush=True)

    more_btn.click(by_js=True)
    time.sleep(1.0)

    # 以 Technology Solutions 为锚，取其所在菜单容器
    anchor = tab.ele("text:Technology Solutions", timeout=2)
    menu_items = []
    if anchor:
        for xp in (
            "xpath:ancestor::ul[1]",
            "xpath:ancestor::*[contains(@class,'menu')][1]",
            "xpath:ancestor::div[contains(@class,'dropdown')][1]",
        ):
            try:
                c = anchor.ele(xp, timeout=0.5)
                if c:
                    items = c.eles("css:li", timeout=0.5) or c.eles("css:.iui-menu-item", timeout=0.5)
                    if items:
                        menu_items = items
                        break
            except Exception:
                continue
        if not menu_items:
            menu_items = [anchor]
    labels = [m.text.strip().split("\n")[0] for m in menu_items if (m.text or "").strip()]
    print("More 菜单项:", labels, flush=True)

    results = []
    for mi in menu_items:
        mlabel = (mi.text or "").strip().split("\n")[0]
        if not mlabel:
            continue
        try:
            mi.click(by_js=True)
        except Exception as e:
            print(f"click {mlabel} failed: {e}", flush=True)
            continue
        bm = drain_last_bms(tab)
        sel = read_selected(tab)
        print(f"  More/{mlabel!r:26} bm={bm!r:28} display={sel!r}", flush=True)
        results.append(
            {"tab": f"More/{mlabel}", "businessModels": bm, "selected_display": sel}
        )
        # 重新展开 More
        try:
            more_btn = None
            for item in tab.eles(
                "css:.iui-button-tabs.filter-tabs .iui-tab-item", timeout=2
            ):
                if "more" in (item.text or "").strip().lower():
                    more_btn = item
                    break
            if more_btn:
                more_btn.click(by_js=True)
                time.sleep(0.8)
        except Exception:
            pass

    tab.listen.stop()
    print("RESULT_JSON=", flush=True)
    print(json.dumps(results, ensure_ascii=False, indent=1), flush=True)


if __name__ == "__main__":
    main()
