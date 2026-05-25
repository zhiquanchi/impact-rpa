import json
import os
import platform
import re
import socket
import subprocess
import urllib.error
import urllib.request
from typing import TypedDict

from loguru import logger


class CdpResult(TypedDict, total=False):
    is_cdp: bool
    browser_version: str | None
    web_socket_debugger_url: str | None
    error: str | None


class PortStatus(TypedDict, total=False):
    port: int
    is_listening: bool
    pid: str | None
    process_name: str | None
    local_address: str | None
    can_connect: bool
    error: str | None


def is_cdp_endpoint(port: int) -> CdpResult:
    """检查端口上的服务是否是真正的 Chrome CDP（Chrome DevTools Protocol）端点"""
    result: CdpResult = {
        "is_cdp": False,
        "browser_version": None,
        "web_socket_debugger_url": None,
        "error": None,
    }
    url = f"http://127.0.0.1:{port}/json/version"
    try:
        req = urllib.request.Request(url, method="GET")
        with urllib.request.urlopen(req, timeout=3) as resp:
            if resp.status == 200:
                data = json.loads(resp.read().decode("utf-8"))
                result["is_cdp"] = True
                result["browser_version"] = data.get("Browser", "")
                result["web_socket_debugger_url"] = data.get("webSocketDebuggerUrl", "")
    except urllib.error.HTTPError as e:
        result["error"] = f"HTTP {e.code}: port occupied but not a CDP endpoint"
    except urllib.error.URLError as e:
        result["error"] = f"Connection failed: {e.reason}"
    except Exception as e:
        result["error"] = str(e)
    return result


def kill_process(pid: int) -> bool:
    """终止指定 PID 的进程"""
    system = platform.system()
    try:
        if system == "Windows":
            subprocess.run(
                ["taskkill", "/F", "/PID", str(pid)],
                check=True,
                capture_output=True,
            )
        else:
            os.kill(pid, 9)  # SIGKILL equivalent
        return True
    except subprocess.CalledProcessError as e:
        stderr_text = e.stderr.decode("gbk", errors="ignore") if system == "Windows" else e.stderr.decode("utf-8", errors="ignore")
        logger.error("终止进程 {} 失败: {}", pid, stderr_text)
        return False
    except Exception as e:
        logger.error("终止进程 {} 异常: {}", pid, e)
        return False


def check_port(port: int) -> PortStatus:
    """检查端口状态"""
    result: PortStatus = {
        'port': port,
        'is_listening': False,
        'pid': None,
        'process_name': None,
        'local_address': None
    }

    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(1)
        socket_result = sock.connect_ex(('127.0.0.1', port))
        sock.close()

        result['can_connect'] = socket_result == 0
    except Exception as e:
        result['can_connect'] = False
        result['error'] = str(e)

    system = platform.system()

    if system == 'Windows':
        try:
            output = subprocess.check_output(
                ['netstat', '-ano'],
                encoding='gbk',
                errors='ignore'
            )

            for line in output.split('\n'):
                if f':{port}' in line and 'LISTENING' in line:
                    parts = re.split(r'\s+', line.strip())
                    if len(parts) >= 5:
                        result['is_listening'] = True
                        result['local_address'] = parts[1]
                        result['pid'] = parts[4]

                        if result['pid']:
                            try:
                                proc_output = subprocess.check_output(
                                    ['tasklist', '/FI', f'PID eq {result["pid"]}'],
                                    encoding='gbk',
                                    errors='ignore'
                                )
                                for proc_line in proc_output.split('\n'):
                                    if result['pid'] in proc_line and '.exe' in proc_line:
                                        proc_parts = re.split(r'\s+', proc_line.strip())
                                        result['process_name'] = proc_parts[0]
                                        break
                            except Exception:
                                pass
                    break
        except Exception as e:
            result['error'] = str(e)

    else:
        try:
            output = subprocess.check_output(
                ['lsof', '-i', f':{port}'],
                text=True
            )
            lines = output.strip().split('\n')
            if len(lines) > 1:
                parts = re.split(r'\s+', lines[1])
                result['is_listening'] = True
                result['process_name'] = parts[0]
                result['pid'] = parts[1]
        except Exception:
            pass

    return result


def print_port_status(port: int = 9222):
    """打印端口状态"""
    logger.info("\n" + "="*50)
    logger.info("端口 {} 状态检查", port)
    logger.info("="*50)

    status = check_port(port)

    logger.info("端口: {}", status['port'])
    logger.info("监听状态: {}", "✓ 正在监听" if status['is_listening'] else "✗ 未被监听")
    logger.info("可连接性: {}", "✓ 可以连接" if status.get('can_connect') else "✗ 无法连接")

    if status['pid']:
        logger.info("进程 PID: {}", status['pid'])
    if status['process_name']:
        logger.info("进程名称: {}", status['process_name'])
    if status['local_address']:
        logger.info("监听地址: {}", status['local_address'])

    if 'error' in status and status['error']:
        logger.error("错误: {}", status['error'])

    if not status['is_listening']:
        logger.info("💡 建议操作:")
        logger.info("  1. 启动 Chrome 时指定调试端口:")
        logger.info(r'     "C:\Program Files\Google\Chrome\Application\chrome.exe" --remote-debugging-port=9222')
        logger.info("  2. 或者检查代码中是否配置了自动启动浏览器")
    else:
        logger.info("端口 {} 被 {} 占用，正在验证是否为 CDP 端点...", port, status['process_name'] or status['pid'])

        # 验证是否是真正的 CDP remote-debugging
        cdp_result = is_cdp_endpoint(port)
        if cdp_result["is_cdp"]:
            logger.info("✅ 确认为 Chrome CDP 端点")
            if cdp_result["browser_version"]:
                logger.info("   浏览器版本: {}", cdp_result['browser_version'])
            if cdp_result["web_socket_debugger_url"]:
                logger.info("   WebSocket URL: {}...", cdp_result['web_socket_debugger_url'][:80])
        else:
            reason = cdp_result.get("error", "未知原因")
            logger.error("不是 Chrome CDP 端点 ({})", reason)
            pid = status["pid"]
            if pid:
                logger.warning("正在终止非 CDP 进程 (PID: {}, 名称: {}) ...", pid, status['process_name'])
                if kill_process(int(pid)):
                    logger.info("进程 {} 已终止", pid)
                else:
                    logger.error("终止进程 {} 失败，请手动处理", pid)
            else:
                logger.error("无法获取 PID，请手动终止占用端口的进程")

    logger.info("="*50 + "\n")


if __name__ == '__main__':
    print_port_status(9222)
