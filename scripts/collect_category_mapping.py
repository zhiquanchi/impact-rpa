"""采集 Discovery 页分类映射（修正版）。

- 点击后等待请求稳定，取该轮最后一个 listings 包的 businessModels
- More 按钮限定在 tab 栏内定位；菜单项取包含 Technology Solutions 的浮层
"""
import json
import sys
import time
from urllib.parse import parse_qs, urlparse

sys.path.insert(0, ".")

from DrissionPage import Chromium

LISTINGS = "partner-ui/api/discover/listings"
E1 = 'xpath://*[@id="app"]/div/div[1]/div/div[2]/div[1]'
TAB_BAR = 'xpath://*[@id="app"]/div/div[1]/div/div[2]/div[2]/div/div'


def drain_last_bms(tab, settle=1.5, timeout=5.0):
    """等待 settle 秒让请求发出，再收包；返回最后一个 businessModels 值。"""
    time.sleep(settle)
    deadline = time.time() + timeout
    last = None
    while time.time() < deadline:
        packet = tab.listen.wait(timeout=0.4)
        if not packet:
            if last is not None:
                break  # 收完且无新包
            continue
        url = getattr(packet, "url", "") or ""
        if LISTINGS not in url:
            continue
        qs = parse_qs(urlparse(url).query)
        bm = (qs.get("businessModels") or [""])[0]
        if bm:
            last = bm
            deadline = time.time() + 1.5  # 再多等 1.5 秒看有没有更新的
    return last


def read_selected(tab):
    try:
        e = tab.ele(E1, timeout=0.5)
        return (e.text or "").strip() if e else ""
    except Exception:
        return ""


def collect(tab, label, ele):
    try:
        ele.click(by_js=True)
    except Exception as e:
        print(f"[skip] click {label} failed: {e}", flush=True)
        return None
    bm = drain_last_bms(tab)
    sel = read_selected(tab)
    print(f"  {label!r:34} bm={bm!r:32} display={sel!r}", flush=True)
    return {"tab": label, "businessModels": bm, "selected_display": sel}


def main():
    b = Chromium()
    tab = None
    for t in b.get_tabs():
        if "partner_discover" in (t.url or ""):
            tab = t
            break
    if tab is None:
        print("未找到 discovery 页，先打开", flush=True)
        tab = b.new_tab(
            "https://app.impact.com/secure/advertiser/discover/radius/fr/"
            "partner_discover.ihtml?page=marketplace&slideout_id_type=partner"
        )
        tab.wait.doc_loaded(timeout=15)
        time.sleep(2)

    # 回到 Home 起点
    print("PAGE:", (tab.url or "")[:80], flush=True)
    tab.listen.start(LISTINGS, is_regex=False)

    results = []
    tab_items = tab.eles("css:.iui-button-tabs.filter-tabs .iui-tab-item", timeout=3)
    labels = [i.text.strip() for i in tab_items]
    print("tab 栏:", labels, flush=True)

    print("== 顶部 tab 栏 ==", flush=True)
    for item in tab_items:
        label = (item.text or "").strip()
        if not label or label == "More":
            continue
        row = collect(tab, label, item)
        if row:
            results.append(row)

    # tab 栏内的 More 按钮
    print("== More 菜单 ==", flush=True)
    more_btn = tab.ele(f"xpath:{TAB_BAR}//*[text()='More']", timeout=1)
    menu_items = []
    if more_btn:
        try:
            more_btn.click(by_js=True)
            time.sleep(1.0)
        except Exception as e:
            print(f"open More failed: {e}", flush=True)
        # 用 Technology Solutions 锚定真菜单浮层，取其同级菜单项
        anchor = tab.ele("text:Technology Solutions", timeout=2)
        if anchor:
            try:
                container = anchor.ele(
                    "xpath:ancestor::ul[1] | ancestor::*[contains(@class,'menu')][1]",
                    timeout=0.5,
                )
                if container:
                    menu_items = container.eles("css:li | css:.iui-menu-item", timeout=0.5)
            except Exception:
                pass
            if not menu_items:
                menu_items = [anchor]
        menu_labels = [m.text.strip().split("\n")[0] for m in menu_items if m.text.strip()]
        print("More 菜单项:", menu_labels, flush=True)
    else:
        print("tab 栏内未找到 More 按钮", flush=True)

    for mi in menu_items:
        mlabel = (mi.text or "").strip().split("\n")[0]
        if not mlabel:
            continue
        row = collect(tab, f"More/{mlabel}", mi)
        if row:
            results.append(row)
        # 重新展开 More
        more_btn = tab.ele(f"xpath:{TAB_BAR}//*[text()='More']", timeout=1)
        if more_btn:
            try:
                more_btn.click(by_js=True)
                time.sleep(0.8)
            except Exception:
                pass

    tab.listen.stop()
    print("RESULT_JSON=", flush=True)
    print(json.dumps(results, ensure_ascii=False, indent=1), flush=True)


if __name__ == "__main__":
    main()
