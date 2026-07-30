"""hover 显示 Invite to Campaign 按钮，点击后选择 campaign 发送邀请。

使用 DrissionPage 的网络监听功能捕获邀请请求的响应，
判断是否成功并写入日志。
"""

import time
import sys
import json
sys.stdout.reconfigure(encoding='utf-8')

from loguru import logger
from DrissionPage import Chromium
from DrissionPage.errors import NoRectError

# ========== 配置 ==========
# 要选中的 campaign 名称（部分匹配即可）
CAMPAIGN_NAME = "TORRAS Japan"

# 个性化消息（留空则不填写）
PERSONALIZED_MESSAGE = ""  # TODO: 占位，以后需要时填写

# hover 等待时间
HOVER_WAIT = 1.0
# 弹窗等待时间
MODAL_WAIT = 2.0
# 下拉展开等待时间
DROPDOWN_WAIT = 1.5
# 监听超时（秒）
LISTENER_TIMEOUT = 15
# ==========================


def setup_logger() -> None:
    """配置 loguru 日志输出。"""
    logger.remove()
    logger.add(
        sys.stderr,
        level="INFO",
        format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {message}",
    )
    logger.add(
        "logs/invite_campaign_{time:YYYY-MM-DD}.log",
        level="INFO",
        format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {message}",
        rotation="00:00",
        retention="30 days",
        encoding="utf-8",
    )


def hover_to_show_button(tab, card_xpath: str, btn_xpath: str) -> bool:
    """hover 卡片让按钮显示，返回是否成功。"""
    card = tab.ele(f"xpath:{card_xpath}", timeout=5)
    if not card:
        logger.warning("未找到卡片容器")
        return False

    card.scroll.to_see()
    time.sleep(0.5)

    for attempt in range(3):
        card.hover()
        time.sleep(HOVER_WAIT)
        btn = tab.ele(f"xpath:{btn_xpath}", timeout=2)
        if btn:
            try:
                rect = btn.rect
                if rect and rect.get('height', 0) > 0:
                    return True
            except Exception:
                pass
        logger.debug(f"第 {attempt + 1} 次 hover，按钮尚未显示，重试...")

    btn = tab.ele(f"xpath:{btn_xpath}", timeout=2)
    return btn is not None


def click_invite_button(tab, btn_xpath: str) -> bool:
    """点击 Invite to Campaign 按钮。"""
    btn = tab.ele(f"xpath:{btn_xpath}", timeout=3)
    if not btn:
        logger.warning("未找到 Invite to Campaign 按钮")
        return False

    try:
        btn.click()
    except NoRectError:
        logger.debug("普通点击失败，改用 JS 点击")
        btn.click(by_js=True)

    time.sleep(MODAL_WAIT)
    return True


def find_modal(tab):
    """查找 Invite to Campaign 弹窗。"""
    for xp in [
        "xpath:/html/body/div[22]/div[2]",
        "xpath://div[contains(@class, 'modal-container') and contains(., 'Invite to campaign')]",
    ]:
        modal = tab.ele(xp, timeout=2)
        if modal:
            return modal
    return None


def select_campaign(tab, modal, campaign_name: str) -> bool:
    """在弹窗中点击 Select 并选中指定的 campaign。"""
    select_btn = modal.ele("css:.iui-multi-select-input-button", timeout=2)
    if not select_btn:
        select_btn = modal.ele("text:Select", timeout=2)
    if not select_btn:
        logger.warning("未找到 Select 按钮")
        return False

    logger.info("点击 Select 展开 campaign 列表...")
    select_btn.click()
    time.sleep(DROPDOWN_WAIT)

    # 查找包含 campaign 名称的选项
    all_lis = tab.eles("tag:li", timeout=0.5)
    target = None
    for li in all_lis:
        try:
            text = li.text.strip()
            if campaign_name in text:
                rect = li.rect
                if rect and rect.get('height', 0) > 0:
                    target = li
                    break
        except Exception:
            continue

    if not target:
        lists = tab.eles("css:.iui-list", timeout=0.5)
        for lst in lists:
            items = lst.eles("tag:li")
            for li in items:
                try:
                    text = li.text.strip()
                    if campaign_name in text:
                        target = li
                        break
                except Exception:
                    continue
            if target:
                break

    if not target:
        logger.warning(f"未找到包含 '{campaign_name}' 的选项")
        return False

    logger.info(f"选中 campaign: {target.text.strip()}")
    target.click()
    time.sleep(0.8)
    return True


def fill_personalized_message(modal, message: str) -> None:
    """填写个性化消息（占位实现）。"""
    if not message:
        logger.info("个性化消息为空，跳过填写")
        return
    # TODO: 找到 Personalized Message 输入框并填写内容
    # textarea = modal.ele("tag:textarea", timeout=2)
    # if textarea:
    #     textarea.input(message)
    logger.info(f"[占位] 个性化消息将填写: {message[:50]}...")


def is_invite_request(url: str) -> bool:
    """判断 URL 是否是邀请相关的 API 请求。"""
    keywords = ["invite", "sendInvite", "partnerInvite", "invitePartner", "campaignInvite"]
    url_lower = url.lower()
    return any(kw in url_lower for kw in keywords)


def wait_for_invite_response(tab, timeout: int = 15) -> dict | None:
    """等待邀请 API 的响应，返回响应数据。

    使用 DrissionPage 的 listen 功能监听网络请求。
    """
    # 启动监听
    tab.listen.start(
        target="",  # 监听所有请求，我们在回调中过滤
        is_regex=False,
    )
    logger.debug("网络监听已启动")

    # 等待结果
    start = time.time()
    invite_response = None

    while time.time() - start < timeout:
        try:
            packet = tab.listen.wait(timeout=1)
            # listen.wait 超时返回 False（非 None），需用真值判断
            if not packet:
                continue

            url = packet.url
            if is_invite_request(url):
                logger.info(f"捕获到邀请请求: {url}")
                logger.info(f"  请求方法: {packet.method}")
                logger.info(f"  响应状态: {packet.response_status}")

                # 尝试获取响应 body
                try:
                    body = packet.response.body
                    if body:
                        # 尝试解析 JSON
                        if isinstance(body, (dict, list)):
                            logger.info(f"  响应体: {json.dumps(body, ensure_ascii=False)[:500]}")
                            invite_response = body
                        elif isinstance(body, str):
                            logger.info(f"  响应体: {body[:500]}")
                            try:
                                invite_response = json.loads(body)
                            except json.JSONDecodeError:
                                invite_response = {"raw": body}
                        else:
                            logger.info(f"  响应体类型: {type(body)}")
                            invite_response = {"raw": str(body)[:500]}
                    else:
                        invite_response = {"status": packet.response_status}
                except Exception as e:
                    logger.debug(f"读取响应体失败: {e}")
                    invite_response = {"status": packet.response_status, "error": str(e)}

                break
        except Exception as e:
            logger.debug(f"监听循环异常: {e}")
            break

    # 停止监听
    try:
        tab.listen.stop()
    except Exception:
        pass

    return invite_response


def click_send_invite(modal) -> bool:
    """点击 Send Invite 按钮（只负责点击，不判断结果）。"""
    send_btn = modal.ele("text:Send Invite", timeout=2)
    if not send_btn:
        logger.warning("未找到 Send Invite 按钮")
        return False
    logger.info("点击 Send Invite...")
    send_btn.click()
    return True


def judge_success(response) -> tuple[bool, str]:
    """根据 API 响应判断邀请是否成功。

    Returns:
        (是否成功, 状态描述)
    """
    if response is None:
        return False, "未捕获到邀请请求的响应"

    # 如果有 HTTP 状态码
    status = response.get("status")
    if status and isinstance(status, int):
        if status >= 400:
            return False, f"HTTP 状态码: {status}"

    # 常见的成功/失败字段判断
    success_keys = ["success", "ok", "isSuccess", "status", "code"]
    message_keys = ["message", "msg", "error", "errorMessage", "description"]

    # 检查成功标识
    for key in success_keys:
        if key in response:
            val = response[key]
            if isinstance(val, bool):
                return val, f"成功字段 {key}={val}"
            if isinstance(val, (int, float)):
                return val >= 0, f"成功字段 {key}={val}"
            if isinstance(val, str):
                lower = val.lower()
                if lower in ("success", "ok", "true", "0"):
                    return True, f"成功字段 {key}={val}"
                if lower in ("fail", "failed", "error", "false"):
                    return False, f"失败字段 {key}={val}"

    # 取消息
    msg = ""
    for key in message_keys:
        if key in response and isinstance(response[key], str):
            msg = response[key]
            break

    # 默认：有数据就当成功
    return True, msg or "响应成功（默认判断）"


def main() -> None:
    setup_logger()

    browser = Chromium(9222)
    tab = browser.latest_tab
    logger.info(f"当前页面: {tab.title}")
    logger.info(f"URL: {tab.url}")

    # 按钮和卡片的 XPath
    btn_xpath = "/html/body/div[1]/div[3]/div[1]/div[4]/div/div[2]/div[2]/div/div[3]/div/div[1]/div/div[2]/button"
    card_xpath = "/html/body/div[1]/div[3]/div[1]/div[4]/div/div[2]/div[2]/div/div[3]/div/div[1]"

    # 1. hover 让按钮显示
    logger.info("[1/6] Hover 卡片让 Invite to Campaign 按钮显示...")
    if not hover_to_show_button(tab, card_xpath, btn_xpath):
        logger.error("按钮始终未显示，退出")
        return
    logger.info("按钮已显示")

    # 2. 点击按钮打开弹窗
    logger.info("[2/6] 点击 Invite to Campaign 按钮...")
    if not click_invite_button(tab, btn_xpath):
        return
    logger.info("已点击")

    # 3. 找到弹窗
    logger.info("[3/6] 查找弹窗...")
    modal = find_modal(tab)
    if not modal:
        logger.error("未找到弹窗")
        return
    logger.info("已找到弹窗")

    # 4. 选择 campaign
    logger.info("[4/6] 选择 campaign...")
    if not select_campaign(tab, modal, CAMPAIGN_NAME):
        logger.error("选择 campaign 失败")
        return
    logger.info("已选中")

    # 5. 填写个性化消息（占位）
    logger.info("[5/6] 填写个性化消息...")
    fill_personalized_message(modal, PERSONALIZED_MESSAGE)

    # 6. 发送邀请并监听响应
    logger.info("[6/6] 发送邀请并监听响应...")

    # 先启动监听，再点击（确保不遗漏）
    tab.listen.start("", is_regex=False)
    logger.debug("网络监听已启动，准备点击 Send Invite")

    if not click_send_invite(modal):
        tab.listen.stop()
        return

    # 等待邀请响应
    invite_response = None
    start = time.time()

    while time.time() - start < LISTENER_TIMEOUT:
        try:
            packet = tab.listen.wait(timeout=1)
            # listen.wait 超时返回 False（非 None），需用真值判断
            if not packet:
                continue

            url = packet.url
            if is_invite_request(url):
                logger.info(f"捕获到邀请请求: {url}")
                logger.info(f"  请求方法: {packet.method}")
                logger.info(f"  响应状态: {packet.response_status}")

                # 获取响应 body
                try:
                    body = packet.response.body
                    if body:
                        if isinstance(body, (dict, list)):
                            body_str = json.dumps(body, ensure_ascii=False)
                            logger.info(f"  响应体: {body_str[:500]}")
                            invite_response = body if isinstance(body, dict) else {"data": body}
                        elif isinstance(body, str):
                            logger.info(f"  响应体: {body[:500]}")
                            try:
                                invite_response = json.loads(body)
                            except json.JSONDecodeError:
                                invite_response = {"raw": body}
                        else:
                            invite_response = {"raw": str(body)[:500]}
                    else:
                        invite_response = {"status": packet.response_status}
                except Exception as e:
                    logger.debug(f"读取响应体失败: {e}")
                    invite_response = {"status": packet.response_status, "read_error": str(e)}

                break
        except Exception as e:
            logger.debug(f"监听异常: {e}")
            break

    try:
        tab.listen.stop()
    except Exception:
        pass

    # 判断并记录结果
    success, desc = judge_success(invite_response)
    if success:
        logger.success(f"✅ 邀请发送成功！{desc}")
    else:
        logger.error(f"❌ 邀请发送失败！{desc}")

    if invite_response:
        logger.info(f"完整响应: {json.dumps(invite_response, ensure_ascii=False)[:1000]}")


if __name__ == "__main__":
    main()
