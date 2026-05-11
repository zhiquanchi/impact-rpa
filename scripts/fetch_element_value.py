from DrissionPage import Chromium
from pydantic import BaseModel, ConfigDict
from typing import List, Optional, Dict, Any
import json
import time

# --- Pydantic Models for API 1: /api/slideout ---

class WebsiteBase(BaseModel):
    model_config = ConfigDict(extra='ignore')
    mozSpamScore: Optional[int] = None
    mozDomainAuthority: Optional[int] = None

class MediaPropertyBase(BaseModel):
    model_config = ConfigDict(extra='ignore')
    url: str
    website: Optional[WebsiteBase] = None

class Program(BaseModel):
    model_config = ConfigDict(extra='ignore')
    name: str
    mediaProperties: List[MediaPropertyBase] = []

class SlideoutBaseResponse(BaseModel):
    model_config = ConfigDict(extra='ignore')
    program: Optional[Program] = None

# --- Pydantic Models for API 2: /api/slideout/mediaproperties ---

class TrafficSummary(BaseModel):
    model_config = ConfigDict(extra='ignore')
    Visits: Optional[str] = None
    Rank: Optional[str] = None

class IntelligenceTraffic(BaseModel):
    model_config = ConfigDict(extra='ignore')
    Summary: Optional[TrafficSummary] = None

class IntelligenceApiWeb(BaseModel):
    model_config = ConfigDict(extra='ignore')
    Traffic: Optional[IntelligenceTraffic] = None

class MediaPropertyDetail(BaseModel):
    model_config = ConfigDict(extra='ignore')
    intelligenceApiWeb: Optional[IntelligenceApiWeb] = None

# This API returns a dictionary where keys are URLs and values are MediaPropertyDetail
# We'll handle this parsing in the logic.

# --- Extraction Logic ---

def fetch_partner_data(count=5):
    print(f"Connecting to browser to intercept {count} items from dual APIs...")
    browser = Chromium()
    tab = browser.latest_tab
    
    # 启动网络监听，监听两个核心 API
    tab.listen.start(['api/slideout', 'api/slideout/mediaproperties'])

    # 触发逻辑
    trigger_js = """
    function triggerData() {
        function findInShadows(selector, root = document) {
            const el = root.querySelector(selector);
            if (el) return el;
            const all = root.querySelectorAll('*');
            for (const item of all) {
                if (item.shadowRoot) {
                    const found = findInShadows(selector, item.shadowRoot);
                    if (found) return found;
                }
            }
            return null;
        }

        const containerSelector = '#unified-program-slideout-app > div > div:nth-child(1) > div > div > div.side-modal-container';
        const container = findInShadows(containerSelector);

        if (container) {
            // 状态 A: Slideout 已打开，点击 Next
            const root = findInShadows('#unified-program-slideout-app');
            const buttons = Array.from(root.querySelectorAll('button'));
            
            // 寻找带有 arrow-right 图标的 Next 按钮，避开 envelope
            const nextBtn = buttons.find(b => 
                b.querySelector('.arrow-right') || 
                (b.getAttribute('aria-label') || '').toLowerCase().includes('next')
            );
            
            if (nextBtn) {
                nextBtn.click();
                return "CLICKED_NEXT";
            }
            return "NEXT_BTN_NOT_FOUND";
        } else {
            // 状态 B: Slideout 未打开，点击列表项
            const listXPath = '//*[@id="app"]/div/div[2]/div[2]/div/div[3]/div/div[1]/div/div[1]';
            const item = document.evaluate(listXPath, document, null, XPathResult.FIRST_ORDERED_NODE_TYPE, null).singleNodeValue;
            
            if (item) {
                item.click();
                return "CLICKED_LIST_ITEM";
            }
            return "LIST_ITEM_NOT_FOUND";
        }
    }
    return triggerData();
    """

    results = []

    for i in range(count):
        print(f"\n--- Processing Partner {i+1}/{count} ---")
        tab.listen.clear()
        
        status = tab.run_js(trigger_js)
        print(f"Trigger Status: {status}")
        
        if status in ["NEXT_BTN_NOT_FOUND", "LIST_ITEM_NOT_FOUND"]:
            print("Failed to trigger data load. Stopping.")
            break

        # 我们需要同时捕获两个 API 的数据
        partner_name = "Unknown"
        moz_data = {}      # 存储从 API 1 获取的数据
        traffic_data = {}  # 存储从 API 2 获取的数据
        
        # 等待最多 8 秒以捕获两个 API 的响应
        start_wait = time.time()
        api1_captured = False
        api2_captured = False
        
        while time.time() - start_wait < 8 and not (api1_captured and api2_captured):
            packet = tab.listen.wait(timeout=0.5)
            if packet and packet.response and packet.response.body:
                try:
                    raw_json = packet.response.body
                    if isinstance(raw_json, str):
                        raw_json = json.loads(raw_json)
                    
                    url_lower = packet.url.lower()
                    
                    # API 1: 基础属性信息 (包含 Moz 数据)
                    if 'api/slideout?' in url_lower or ('api/slideout' in url_lower and 'mediaproperties' not in url_lower):
                        # 处理直接返回 dict 或 body包裹的情况
                        data_to_parse = raw_json.get('body', raw_json) if isinstance(raw_json, dict) and 'body' in raw_json else raw_json
                        
                        if isinstance(data_to_parse, dict) and 'program' in data_to_parse:
                            model = SlideoutBaseResponse.model_validate(data_to_parse)
                            if model.program:
                                partner_name = model.program.name
                                for prop in model.program.mediaProperties:
                                    if prop.website:
                                        moz_data[prop.url] = {
                                            "mozSpamScore": prop.website.mozSpamScore,
                                            "mozDomainAuthority": prop.website.mozDomainAuthority
                                        }
                                api1_captured = True
                                print(f"  [√] Captured Base API (Moz Data)")

                    # API 2: 深度流量属性 (包含 Semrush 和 Visitors 数据)
                    elif 'api/slideout/mediaproperties' in url_lower:
                        data_to_parse = raw_json.get('body', raw_json) if isinstance(raw_json, dict) and 'body' in raw_json else raw_json
                        
                        if isinstance(data_to_parse, dict):
                            # 这个接口的 key 是 url
                            for property_url, details in data_to_parse.items():
                                # 跳过非详情对象 (如 contentIndexApi 等)
                                if not isinstance(details, dict) or 'intelligenceApiWeb' not in details:
                                    continue
                                    
                                model = MediaPropertyDetail.model_validate(details)
                                if model.intelligenceApiWeb and model.intelligenceApiWeb.Traffic and model.intelligenceApiWeb.Traffic.Summary:
                                    summary = model.intelligenceApiWeb.Traffic.Summary
                                    traffic_data[property_url] = {
                                        "Semrush global rank": summary.Rank,
                                        "Monthly visitors": summary.Visits
                                    }
                            api2_captured = True
                            print(f"  [√] Captured Traffic API (Semrush/Visitors)")

                except Exception as e:
                    # 忽略解析错误，继续处理下一个包
                    pass

        # 合并当前合作伙伴的数据
        if api1_captured or api2_captured:
            # 找到所有的 URL keys
            all_urls = set(list(moz_data.keys()) + list(traffic_data.keys()))
            
            for url in all_urls:
                m_data = moz_data.get(url, {})
                t_data = traffic_data.get(url, {})
                
                # 只保存有至少一项有意义数据的记录
                if any(v is not None for v in m_data.values()) or any(v is not None for v in t_data.values()):
                    combined = {
                        "partnerName": partner_name,
                        "propertyUrl": url,
                        "Moz spam score": m_data.get("mozSpamScore"),
                        "Moz domain authority": m_data.get("mozDomainAuthority"),
                        "Semrush global rank": t_data.get("Semrush global rank"),
                        "Monthly visitors": t_data.get("Monthly visitors")
                    }
                    results.append(combined)
                    print(f"    -> Extracted data for URL: {url}")
        else:
            print("  [WARN] Neither Base API nor Traffic API captured.")

        time.sleep(1)

    tab.listen.stop()
    
    # 打印最终结果
    print("\n" + "="*80)
    print("FINAL EXTRACTED METRICS")
    print("="*80)
    print(f"{'Partner Name':<20} | {'URL':<30} | {'Visitors':>10} | {'Rank':>8} | {'Spam':>4} | {'DA':>4}")
    print("-" * 80)
    
    for r in results:
        p_name = str(r['partnerName'])[:18] + '..' if len(str(r['partnerName'])) > 20 else str(r['partnerName'])
        url = str(r['propertyUrl'])[:28] + '..' if len(str(r['propertyUrl'])) > 30 else str(r['propertyUrl'])
        
        vis = str(r['Monthly visitors']) if r['Monthly visitors'] else "N/A"
        rank = str(r['Semrush global rank']) if r['Semrush global rank'] else "N/A"
        spam = str(r['Moz spam score']) if r['Moz spam score'] is not None else "N/A"
        da = str(r['Moz domain authority']) if r['Moz domain authority'] is not None else "N/A"
        
        print(f"{p_name:<20} | {url:<30} | {vis:>10} | {rank:>8} | {spam:>4} | {da:>4}")
        
    print("="*80)
    
    # 保存结果
    with open('partner_metrics.json', 'w', encoding='utf-8') as f:
        json.dump(results, f, indent=2, ensure_ascii=False)
    print("Data saved to 'partner_metrics.json'")

if __name__ == "__main__":
    fetch_partner_data(5)
