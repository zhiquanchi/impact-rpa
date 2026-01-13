"""
浏览器连接诊断工具

检查 DrissionPage 是否能正常连接浏览器
"""

import sys
from rich.console import Console
from rich.panel import Panel
from loguru import logger

console = Console()

def check_browser_connection():
    """检查浏览器连接"""
    console.print(Panel.fit("[bold cyan]浏览器连接诊断[/bold cyan]", border_style="cyan"))
    
    console.print("\n[cyan]步骤 1: 检查 DrissionPage 模块...[/cyan]")
    try:
        from DrissionPage import Chromium
        from DrissionPage import ChromiumOptions
        console.print("[green]✓ DrissionPage 模块正常[/green]")
    except ImportError as e:
        console.print(f"[red]✗ DrissionPage 模块导入失败: {e}[/red]")
        console.print("[yellow]请运行: pip install DrissionPage[/yellow]")
        return False
    
    console.print("\n[cyan]步骤 2: 检查浏览器进程...[/cyan]")
    try:
        import psutil
        chrome_found = False
        edge_found = False
        
        for proc in psutil.process_iter(['pid', 'name']):
            name = proc.info['name'].lower()
            if 'chrome' in name and 'chromium' not in name:
                chrome_found = True
            if 'msedge' in name or 'edge' in name:
                edge_found = True
        
        if chrome_found:
            console.print("[green]✓ 检测到 Chrome 浏览器进程[/green]")
        if edge_found:
            console.print("[green]✓ 检测到 Edge 浏览器进程[/green]")
        if not chrome_found and not edge_found:
            console.print("[yellow]⚠ 未检测到浏览器进程，请先打开 Chrome 或 Edge[/yellow]")
    except ImportError:
        console.print("[dim]⚠ psutil 未安装，跳过进程检查[/dim]")
        console.print("[dim]可以安装: pip install psutil[/dim]")
    except Exception as e:
        console.print(f"[dim]进程检查失败: {e}[/dim]")
    
    console.print("\n[cyan]步骤 3: 尝试连接浏览器...[/cyan]")
    try:
        # 方式1: 默认连接
        console.print("[dim]尝试方式 1: 默认连接...[/dim]")
        browser = Chromium()
        tab = browser.latest_tab
        if tab:
            console.print("[green]✓ 成功连接到浏览器（默认方式）[/green]")
            try:
                url = tab.url
                console.print(f"[dim]当前标签页: {url[:80]}...[/dim]")
            except:
                pass
            browser.close()
            return True
    except Exception as e:
        console.print(f"[dim]方式 1 失败: {type(e).__name__}: {str(e)[:100]}[/dim]")
    
    try:
        # 方式2: 使用 ChromiumOptions
        console.print("[dim]尝试方式 2: 使用 ChromiumOptions...[/dim]")
        from DrissionPage import ChromiumOptions
        options = ChromiumOptions()
        browser = Chromium(addr_or_opts=options)
        tab = browser.latest_tab
        if tab:
            console.print("[green]✓ 成功连接到浏览器（ChromiumOptions）[/green]")
            browser.close()
            return True
    except Exception as e:
        console.print(f"[dim]方式 2 失败: {type(e).__name__}: {str(e)[:100]}[/dim]")
    
    console.print("\n[red]✗ 所有连接方式均失败[/red]")
    console.print("\n[yellow]可能的解决方案：[/yellow]")
    console.print("1. 确保 Chrome 或 Edge 浏览器已打开至少一个窗口")
    console.print("2. 关闭所有浏览器窗口，然后重新打开一个")
    console.print("3. 检查防火墙/杀毒软件是否阻止连接")
    console.print("4. 尝试以管理员权限运行此脚本")
    console.print("5. 检查 DrissionPage 版本: pip show DrissionPage")
    
    return False

if __name__ == "__main__":
    try:
        success = check_browser_connection()
        sys.exit(0 if success else 1)
    except KeyboardInterrupt:
        console.print("\n[yellow]诊断被中断[/yellow]")
        sys.exit(1)
    except Exception as e:
        console.print(f"\n[red]诊断出错: {e}[/red]")
        logger.exception("诊断异常")
        sys.exit(1)

