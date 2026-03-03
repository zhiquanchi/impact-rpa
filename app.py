import questionary
from rich.console import Console
from rich.panel import Panel

from core.config_manager import ConfigManager
from core.settings_service import SettingsService
from core.template_manager import TemplateManager
from domain.proposal_sender import ProposalSender, SendProposalsResult
from infra.browser_manager import BrowserManager
from ui.menu_ui import MenuUI


class ImpactRPA:
    """Impact RPA 主应用类（组合根）。"""

    def __init__(self):
        self.console = Console()
        self.config = ConfigManager()
        self.settings = SettingsService(self.config)
        self.template_manager = TemplateManager(self.config)
        self.browser = BrowserManager(self.console, self.config)
        self.proposal_sender = ProposalSender(self.browser, self.template_manager, self.console, self.config)
        self.menu = MenuUI(
            self.config,
            self.template_manager,
            self.console,
            browser=self.browser,
            proposal_sender=self.proposal_sender,
        )

    def start(self):
        if not self.browser.init():
            self.console.print("[red]无法连接浏览器，请确保浏览器已打开[/red]")
            try:
                from notification_service import NotificationService, NotificationPayload
                NotificationService().send(NotificationPayload(message="无法连接浏览器"))
            except Exception:
                pass
            return
        self._main_loop()

    def _main_loop(self):
        while True:
            choice = self.menu.show_main_menu()
            if choice is None:
                self.console.print("\n[yellow]已取消[/yellow]")
                break
            if choice == "1":
                self._start_send_proposals()
            elif choice == "8":
                self._send_proposal_by_table_row()
            elif choice == "2":
                self.menu.preview_template()
            elif choice == "3":
                self.menu.edit_template_menu()
            elif choice == "4":
                self.menu.set_proposal_count()
            elif choice == "5":
                self.menu.view_settings()
            elif choice == "6":
                self.menu.set_template_term()
            elif choice == "7":
                self.menu.check_and_update()
            elif choice == "0":
                self.console.print("\n[bold cyan]感谢使用，再见！👋[/bold cyan]")
                break

    def _notify_proposal_run(self, result: SendProposalsResult | None = None, error: Exception | None = None) -> None:
        if error is not None:
            msg = f"发送失败: {error}"
        elif result is not None and result.completed_all:
            msg = f"发送完成，共发送 {result.clicked_count} 个"
        else:
            return
        try:
            from notification_service import NotificationService, NotificationPayload
            NotificationService().send(NotificationPayload(message=msg))
        except Exception:
            pass

    def _start_send_proposals(self):
        if not self.browser.is_connected() and not self.browser.init():
            self.console.print("[red]无法连接浏览器，请确保浏览器已打开[/red]")
            return

        settings = self.settings.get_snapshot()
        max_count = settings["max_proposals"]
        self.console.print(f"\n[cyan]准备发送 [bold]{max_count}[/bold] 个 Send Proposal[/cyan]")

        template = self.template_manager.get_active_template()
        if not template:
            self.console.print("[bold yellow]⚠️  警告: 留言模板为空！[/bold yellow]")
            if not questionary.confirm("是否继续?", default=False).ask():
                return
        else:
            self.console.print("\n[bold]当前留言模板预览:[/bold]")
            self.console.print(Panel(template, border_style="dim"))

        if not questionary.confirm(f"确认开始发送 {max_count} 个 Proposal?", default=False).ask():
            self.console.print("[yellow]已取消[/yellow]")
            return

        try:
            result = self.proposal_sender.send_proposals(max_count, template)
            self._notify_proposal_run(result=result, error=None)
        except Exception as e:
            self._notify_proposal_run(result=None, error=e)

    def _send_proposal_by_table_row(self):
        if not self.browser.is_connected() and not self.browser.init():
            self.console.print("[red]无法连接浏览器，请确保浏览器已打开[/red]")
            return

        self.console.print(Panel(
            "[bold]请在浏览器中完成以下操作：[/bold]\n"
            "1. 导航到 Creator Search 页面 (creator-rt-searches.ihtml)\n"
            "2. 设置好筛选条件并获取搜索结果\n"
            "3. 确保搜索结果列表已加载\n"
            "4. 返回此处按任意键继续",
            title="[cyan]Creator Search 批量发送[/cyan]",
            border_style="cyan",
        ))
        questionary.press_any_key_to_continue("操作完成后，按任意键继续...").ask()

        settings = self.settings.get_snapshot()
        default_count = settings.get("max_proposals", 10)
        count_input = questionary.text(f"请输入要发送的数量 (默认 {default_count}):", default=str(default_count)).ask()
        if count_input is None:
            self.console.print("[yellow]已取消[/yellow]")
            return
        try:
            max_count = int(count_input.strip()) if count_input.strip() else default_count
        except ValueError:
            self.console.print("[red]请输入有效的数字[/red]")
            return
        if max_count < 1:
            self.console.print("[red]数量需大于等于 1[/red]")
            return

        start_input = questionary.text("请输入起始行号 (从 1 开始，默认 1):", default="1").ask()
        if start_input is None:
            self.console.print("[yellow]已取消[/yellow]")
            return
        try:
            start_row = int(start_input.strip()) if start_input.strip() else 1
        except ValueError:
            self.console.print("[red]请输入有效的整数行号[/red]")
            return
        if start_row < 1:
            self.console.print("[red]行号需大于等于 1[/red]")
            return

        template = self.template_manager.get_active_template()
        if not template:
            self.console.print("[bold yellow]⚠️  警告: 留言模板为空！[/bold yellow]")
            if not questionary.confirm("是否继续?", default=False).ask():
                return
        else:
            self.console.print("\n[bold]当前留言模板预览:[/bold]")
            self.console.print(Panel(template, border_style="dim"))

        self.console.print(f"\n[cyan]即将从第 {start_row} 行开始，发送 {max_count} 个 Proposal[/cyan]")
        if not questionary.confirm("确认开始批量发送?", default=False).ask():
            self.console.print("[yellow]已取消[/yellow]")
            return

        try:
            result = self.proposal_sender.send_proposals_creator_search(
                max_count=max_count, start_row=start_row, template_content=template
            )
            self._notify_proposal_run(result=result, error=None)
        except Exception as e:
            self._notify_proposal_run(result=None, error=e)


def main() -> None:
    app = ImpactRPA()
    app.start()


if __name__ == "__main__":
    main()

