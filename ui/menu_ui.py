import questionary
from legacy_main import MenuUI as LegacyMenuUI
from domain.selectors import MODAL_IFRAME_SELECTOR


class MenuUI(LegacyMenuUI):
    """菜单层仅依赖公开接口。"""

    def _set_template_term_from_browser(self, settings: dict, current: str):
        if not self.browser or not self.proposal_sender:
            self.console.print("[red]浏览器未初始化，无法从浏览器获取选项[/red]")
            return

        if not self.browser.is_connected():
            self.console.print("[red]浏览器未连接，请先确保浏览器已打开[/red]")
            return

        self.console.print(
            "[cyan]请先手动打开任意 Send Proposal 弹窗，然后回到终端继续。[/cyan]"
        )
        questionary.press_any_key_to_continue("弹窗打开后，按任意键继续...").ask()

        iframe = self.browser.find_element(MODAL_IFRAME_SELECTOR, timeout=5)
        if not iframe:
            self.console.print("[red]未找到弹窗 iframe，请确保 Send Proposal 弹窗已打开[/red]")
            return

        options = self.proposal_sender.get_template_term_options(iframe)
        if not options:
            self.console.print("[yellow]未获取到选项列表，可能弹窗结构已变化[/yellow]")
            return

        option_choices = [questionary.Choice(f"{opt}{' ✓' if opt.lower() == current.lower() else ''}", value=opt) for opt in options]
        option_choices.append(questionary.Choice("🔙 取消", value=None))
        selected = questionary.select("请选择 Template Term:", choices=option_choices).ask()

        if selected is None:
            self.console.print("[yellow]已取消[/yellow]")
            return

        settings["template_term"] = selected
        if self.config.save_settings(settings):
            self.console.print(f"[bold green]✓ Template Term 已设置为: {selected}[/bold green]")
            self.console.print("[dim]提示：请手动关闭浏览器中的弹窗[/dim]")

