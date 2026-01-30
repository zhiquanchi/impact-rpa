"""测试 Creator Search 批量发送功能"""
import time
from main import BrowserManager, ProposalSender, ConfigManager, TemplateManager
from rich.console import Console

console = Console()

def main():
    console.print("[cyan]===== Creator Search 批量发送测试 =====[/cyan]")
    
    # 初始化组件
    config = ConfigManager()
    browser = BrowserManager(console)
    template_manager = TemplateManager(config)
    
    if not browser.init():
        console.print("[red]无法连接浏览器，请确保浏览器已打开并启用调试端口[/red]")
        return
    
    console.print("[green]浏览器连接成功[/green]")
    
    # 读取模板
    template = template_manager.get_active_template()
    if template:
        console.print(f"[dim]模板预览 (前100字符): {template[:100]}...[/dim]")
    else:
        console.print("[yellow]警告: 模板为空[/yellow]")
    
    # 创建 ProposalSender (参数顺序: browser, template_manager, console, config)
    proposal_sender = ProposalSender(browser, template_manager, console, config)
    
    console.print("\n[bold]请确保浏览器已打开 Creator Search 页面并加载了搜索结果[/bold]")
    console.print("[dim]5 秒后开始发送第 1 行...[/dim]")
    time.sleep(5)
    
    # 测试发送第 1 行
    console.print("\n[cyan]开始发送...[/cyan]")
    result = proposal_sender.send_proposals_creator_search(
        max_count=1,
        start_row=1,
        template_content=template,
    )
    
    console.print(f"\n[bold]发送结果: 成功 {result.clicked_count} 个, 全部完成: {result.completed_all}[/bold]")

if __name__ == "__main__":
    main()
