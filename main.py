from DrissionPage import Chromium

browser = Chromium()
tab = browser.latest_tab


def main():
    url = 'https://app.impact.com/secure/mediapartner/marketplace/new-campaign-marketplace-flow.ihtml?execution=e1s1#sortBy=salepercent&sortOrder=DESC'
    tab.get(url)
    # 等待页面加载
    tab.wait.doc_loaded()
    # 查找人机验证元素
    人机验证 = tab.ele('text=请完成以下操作，验证您是真人。')
    if 人机验证:
        print("检测到人机验证，正在尝试点击...")
        # 人机验证.click()
    else:
        print("未检测到人机验证。")
    # tab.get(url=url)

def goto_work_web():
    url = ''


if __name__ == "__main__":
    # main()
    pass
