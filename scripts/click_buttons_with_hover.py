"""依次点击匹配指定 XPath 的所有按钮。

每个按钮在点击前需要先 hover（悬停）才会出现/激活，
点击后页面 DOM 可能会刷新，因此每次按索引重新查找元素。
"""

import time

from DrissionPage import Chromium

XPATH = "/html/body/div[1]/div[3]/div[1]/div[4]/div/div[2]/div[2]/div/div[3]/div/div[1]/div/div[2]/button"

HOVER_WAIT = 0.6    # hover 后等待按钮可点击的时间（秒）
CLICK_WAIT = 1.0    # 每次点击后等待页面反应的时间（秒）
MAX_RETRY = 3       # 单个按钮点击失败时的重试次数


def hover_then_click(tab, xpath: str) -> None:
    buttons = tab.eles(f"xpath:{xpath}", timeout=5)
    total = len(buttons)
    if total == 0:
        print(f"未找到任何匹配元素: {xpath}")
        return

    print(f"共找到 {total} 个按钮，开始依次 hover + 点击")

    for index in range(total):
        success = False
        for attempt in range(1, MAX_RETRY + 1):
            try:
                # 点击后 DOM 可能刷新，每次按索引重新获取元素
                buttons = tab.eles(f"xpath:{xpath}", timeout=3)
                if index >= len(buttons):
                    print(f"[{index + 1}/{total}] 元素已不存在（可能已被点击移除），跳过")
                    success = True
                    break

                ele = buttons[index]

                # 先滚动到元素可见，再 hover，最后点击
                ele.scroll.to_see()
                time.sleep(0.3)
                ele.hover()
                time.sleep(HOVER_WAIT)
                ele.click()
                time.sleep(CLICK_WAIT)

                print(f"[{index + 1}/{total}] 点击成功")
                success = True
                break
            except Exception as e:
                print(f"[{index + 1}/{total}] 第 {attempt}/{MAX_RETRY} 次尝试失败: {e}")
                time.sleep(1)

        if not success:
            print(f"[{index + 1}/{total}] 多次尝试后仍失败，跳过该按钮")

    print("全部处理完成")


def main() -> None:
    browser = Chromium()
    tab = browser.latest_tab
    print(f"当前页面: {tab.url}")
    hover_then_click(tab, XPATH)


if __name__ == "__main__":
    main()
