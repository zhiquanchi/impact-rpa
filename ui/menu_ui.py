from loguru import logger
import questionary
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
import pyperclip

from core.config_manager import ConfigManager
from core.template_manager import TemplateManager
from infra.browser_manager import BrowserManager
from domain.proposal_sender import ProposalSender
from domain.selectors import MODAL_IFRAME_SELECTOR

class MenuUI:
    """用户界面类，负责菜单显示和用户交互"""
    
    def __init__(
        self,
        config: ConfigManager,
        template_manager: TemplateManager,
        logger,
        browser: BrowserManager | None = None,
        proposal_sender: "ProposalSender | None" = None,
    ):
        self.config = config
        self.template_manager = template_manager
        self.logger = logger
        self.console = Console()
        self.browser = browser
        self.proposal_sender = proposal_sender
    
    def show_main_menu(self) -> str | None:
        """显示主菜单"""
        self.console.print(Panel.fit(
            "[bold cyan]Impact RPA - Send Proposal 自动化工具[/bold cyan]",
            border_style="cyan"
        ))
        
        choices = [
            questionary.Choice("🚀 开始发送 Send Proposal", value="1"),
            questionary.Choice("📋 Creator Search 批量发送", value="8"),
            questionary.Choice("📄 预览当前留言模板", value="2"),
            questionary.Choice("✏️  编辑留言模板", value="3"),
            questionary.Choice("🔢 设置发送数量", value="4"),
            questionary.Choice("⚙️  查看当前设置", value="5"),
            questionary.Choice("🔧 设置 Template Term 下拉选项", value="6"),
            questionary.Choice("🏷️  设置是否输入 Partner Groups 标签", value="9"),
            questionary.Choice("🔄 检查并更新代码", value="7"),
            questionary.Choice("🚪  退出程序", value="0"),
        ]
        
        return questionary.select(
            "请选择操作:",
            choices=choices,
            style=questionary.Style([
                ('highlighted', 'fg:cyan bold'),
                ('pointer', 'fg:cyan bold'),
            ])
        ).ask()
    
    def preview_template(self):
        """预览当前模板"""
        active_tpl = self.template_manager.get_active_template_info()
        
        if active_tpl and active_tpl.get('content'):
            name = active_tpl.get('name', '未命名')
            self.console.print(Panel(
                active_tpl['content'],
                title=f"[bold green]当前模板: {name}[/bold green]",
                border_style="green"
            ))
        else:
            self.console.print("[yellow]没有激活的模板[/yellow]")
        
        questionary.press_any_key_to_continue("按任意键返回主菜单...").ask()
    
    def edit_template_menu(self):
        """模板编辑菜单"""
        while True:
            choices = [
                questionary.Choice("📋 查看所有模板", value="list"),
                questionary.Choice("👁️  预览当前模板", value="preview"),
                questionary.Choice("✅ 选择激活模板", value="select"),
                questionary.Choice("➕ 添加新模板", value="add"),
                questionary.Choice("✏️  编辑模板", value="edit"),
                questionary.Choice("🗑️  删除模板", value="delete"),
                questionary.Choice("🔙 返回主菜单", value="back"),
            ]
            
            choice = questionary.select(
                "模板管理:",
                choices=choices,
                style=questionary.Style([
                    ('highlighted', 'fg:yellow bold'),
                    ('pointer', 'fg:yellow bold'),
                ])
            ).ask()
            
            if choice is None or choice == 'back':
                break
            elif choice == 'list':
                self._list_all_templates()
            elif choice == 'preview':
                self.preview_template()
            elif choice == 'select':
                self._select_active_template()
            elif choice == 'add':
                self._add_new_template()
            elif choice == 'edit':
                self._edit_existing_template()
            elif choice == 'delete':
                self._delete_template()
    
    def _list_all_templates(self):
        """列出所有模板"""
        data = self.template_manager.load_all()
        templates = data.get('templates', [])
        active_id = data.get('active_template_id')
        
        if not templates:
            self.console.print("[yellow]没有模板[/yellow]")
            questionary.press_any_key_to_continue("按任意键继续...").ask()
            return
        
        table = Table(title="所有留言模板", border_style="blue")
        table.add_column("ID", style="cyan", width=5)
        table.add_column("状态", width=6)
        table.add_column("名称", style="green", width=20)
        table.add_column("内容预览", style="dim", width=50)
        
        for tpl in templates:
            tpl_id = tpl.get('id', 0)
            name = tpl.get('name', '未命名')
            content = tpl.get('content', '')
            preview = content.replace('\n', ' ')[:50]
            if len(content) > 50:
                preview += "..."
            
            status = "[green]✓ 激活[/green]" if tpl_id == active_id else ""
            table.add_row(str(tpl_id), status, name, preview)
        
        self.console.print(table)
        questionary.press_any_key_to_continue("按任意键继续...").ask()
    
    def _select_active_template(self):
        """选择激活模板"""
        data = self.template_manager.load_all()
        templates = data.get('templates', [])
        active_id = data.get('active_template_id')
        
        if not templates:
            self.console.print("[yellow]没有模板可选择[/yellow]")
            return
        
        choices = []
        for tpl in templates:
            tpl_id = tpl.get('id', 0)
            name = tpl.get('name', '未命名')
            mark = " ✓" if tpl_id == active_id else ""
            choices.append(questionary.Choice(f"{name}{mark}", value=tpl_id))
        choices.append(questionary.Choice("🔙 取消", value=None))
        
        selected = questionary.select("选择要激活的模板:", choices=choices).ask()
        
        if selected is not None:
            if self.template_manager.set_active(selected):
                name = next((t.get('name', '未命名') for t in templates if t.get('id') == selected), '未命名')
                self.console.print(f"[bold green]✓ 已激活模板: {name}[/bold green]")
    
    def _add_new_template(self):
        """添加新模板"""
        name = questionary.text("请输入模板名称 (可选):", default="").ask()
        if name is None:
            return
        
        self.console.print("\n[bold]请选择模板内容的输入方式:[/bold]")
        content = self._get_multiline_input()
        
        if not content or not content.strip():
            self.console.print("[yellow]模板内容为空，未保存[/yellow]")
            return
        
        self.console.print(Panel(content, title="[bold yellow]新模板预览[/bold yellow]", border_style="yellow"))
        
        if not questionary.confirm("确认保存?", default=True).ask():
            self.console.print("[yellow]已取消[/yellow]")
            return
        
        activate = questionary.confirm("是否将此模板设为当前激活模板?", default=True).ask()
        
        if self.template_manager.add_template(name, content, activate):
            self.console.print("[bold green]✓ 模板已保存[/bold green]")
        else:
            self.console.print("[bold red]✗ 保存失败[/bold red]")
    
    def _edit_existing_template(self):
        """编辑现有模板"""
        data = self.template_manager.load_all()
        templates = data.get('templates', [])
        
        if not templates:
            self.console.print("[yellow]没有模板可编辑[/yellow]")
            return
        
        choices = []
        for tpl in templates:
            tpl_id = tpl.get('id', 0)
            name = tpl.get('name', '未命名')
            choices.append(questionary.Choice(f"{name} (ID: {tpl_id})", value=tpl_id))
        choices.append(questionary.Choice("🔙 取消", value=None))
        
        selected_id = questionary.select("选择要编辑的模板:", choices=choices).ask()
        if selected_id is None:
            return
        
        tpl = next((t for t in templates if t.get('id') == selected_id), None)
        if tpl is None:
            self.console.print("[red]模板不存在[/red]")
            return
        
        edit_choices = [
            questionary.Choice("📝 编辑名称", value="name"),
            questionary.Choice("📄 编辑内容", value="content"),
            questionary.Choice("🔙 取消", value=None),
        ]
        
        edit_choice = questionary.select("选择要编辑的内容:", choices=edit_choices).ask()
        
        if edit_choice is None:
            return
        elif edit_choice == "name":
            new_name = questionary.text("请输入新的模板名称:", default=tpl.get('name', '')).ask()
            if new_name:
                if self.template_manager.update_template(selected_id, name=new_name):
                    self.console.print(f"[bold green]✓ 模板名称已更新为: {new_name}[/bold green]")
        elif edit_choice == "content":
            self.console.print("[bold]当前内容:[/bold]")
            self.console.print(Panel(tpl.get('content', ''), border_style="dim"))
            
            self.console.print("\n[bold]请选择新内容的输入方式:[/bold]")
            new_content = self._get_multiline_input()
            
            if new_content and new_content.strip():
                self.console.print(Panel(new_content, title="[bold yellow]新内容预览[/bold yellow]", border_style="yellow"))
                if questionary.confirm("确认保存?", default=True).ask():
                    if self.template_manager.update_template(selected_id, content=new_content):
                        self.console.print("[bold green]✓ 模板内容已更新[/bold green]")
            else:
                self.console.print("[yellow]内容为空，未更新[/yellow]")
    
    def _delete_template(self):
        """删除模板"""
        data = self.template_manager.load_all()
        templates = data.get('templates', [])
        active_id = data.get('active_template_id')
        
        if not templates:
            self.console.print("[yellow]没有模板可删除[/yellow]")
            return
        
        if len(templates) == 1:
            self.console.print("[yellow]至少需要保留一个模板[/yellow]")
            return
        
        choices = []
        for tpl in templates:
            tpl_id = tpl.get('id', 0)
            name = tpl.get('name', '未命名')
            mark = " [激活]" if tpl_id == active_id else ""
            choices.append(questionary.Choice(f"{name}{mark} (ID: {tpl_id})", value=tpl_id))
        choices.append(questionary.Choice("🔙 取消", value=None))
        
        selected_id = questionary.select("选择要删除的模板:", choices=choices).ask()
        if selected_id is None:
            return
        
        tpl_name = next((t.get('name', '未命名') for t in templates if t.get('id') == selected_id), '未命名')
        
        if not questionary.confirm(f"确认删除模板 '{tpl_name}'?", default=False).ask():
            self.console.print("[yellow]已取消[/yellow]")
            return
        
        if self.template_manager.delete_template(selected_id):
            self.console.print(f"[bold green]✓ 模板 '{tpl_name}' 已删除[/bold green]")
    
    def _get_multiline_input(self) -> str | None:
        """获取多行输入"""
        choices = [
            questionary.Choice("📋 从剪贴板粘贴", value="clipboard"),
            questionary.Choice("⌨️  手动输入（输入 END 结束）", value="manual"),
            questionary.Choice("🔙 取消", value="cancel"),
        ]
        
        method = questionary.select("选择输入方式:", choices=choices).ask()
        
        if method is None or method == "cancel":
            return None
        
        if method == "clipboard":
            try:
                content = pyperclip.paste()
                if content and content.strip():
                    self.console.print("\n[bold green]已从剪贴板读取内容：[/bold green]")
                    self.console.print(Panel(content, border_style="green"))
                    if questionary.confirm("确认使用此内容?", default=True).ask():
                        return content
                    return None
                else:
                    self.console.print("[yellow]剪贴板为空[/yellow]")
                    return None
            except Exception as e:
                self.console.print(f"[red]读取剪贴板失败: {e}[/red]")
                return None
        else:
            self.console.print("[cyan]请输入内容（输入单独一行 'END' 结束）:[/cyan]")
            lines = []
            while True:
                try:
                    line = input()
                    if line.strip() == 'END':
                        break
                    lines.append(line)
                except EOFError:
                    break
            return '\n'.join(lines) if lines else None
    
    def set_proposal_count(self):
        """设置发送数量"""
        settings = self.config.load_settings()
        self.console.print(f"[cyan]当前设置的发送数量: [bold]{settings['max_proposals']}[/bold][/cyan]")
        
        new_count = questionary.text(
            "请输入新的发送数量:",
            default=str(settings['max_proposals']),
            validate=lambda x: x.isdigit() and int(x) > 0 or "请输入大于0的数字"
        ).ask()
        
        if new_count:
            settings['max_proposals'] = int(new_count)
            self.config.save_settings(settings)
            self.console.print(f"[bold green]✓ 发送数量已设置为: {new_count}[/bold green]")
    
    def view_settings(self):
        """查看当前设置"""
        settings = self.config.load_settings()
        
        table = Table(title="当前设置", border_style="blue")
        table.add_column("设置项", style="cyan")
        table.add_column("值", style="green")
        
        table.add_row("发送数量上限", str(settings['max_proposals']))
        table.add_row("滚动延迟", f"{settings['scroll_delay']} 秒")
        table.add_row("点击延迟", f"{settings['click_delay']} 秒")
        table.add_row("弹窗等待", f"{settings['modal_wait']} 秒")
        table.add_row("Template Term", (settings.get('template_term') or '').strip() or "(未设置)")
        table.add_row("输入 Partner Groups 标签", "是" if settings.get('input_partner_groups_tag', True) else "否")
        
        self.console.print(table)
        questionary.press_any_key_to_continue("按任意键返回主菜单...").ask()
    
    def set_template_term(self):
        """设置 Template Term 文本"""
        settings = self.config.load_settings()
        current = (settings.get('template_term') or '').strip()
        
        self.console.print(f"[cyan]当前 Template Term: [bold]{current or '(未设置)'}[/bold][/cyan]")
        
        # 选择设置方式
        choices = [
            questionary.Choice("⌨️  手动输入", value="manual"),
            questionary.Choice("🌐 从浏览器弹窗获取选项列表", value="browser"),
            questionary.Choice("🔙 取消", value="cancel"),
        ]
        
        method = questionary.select("选择设置方式:", choices=choices).ask()
        
        if method is None or method == "cancel":
            return
        
        if method == "manual":
            new_value = questionary.text("请输入 Template Term 文本:", default=current).ask()
            if new_value is None:
                return
            new_value = (new_value or '').strip()
            settings['template_term'] = new_value
            if self.config.save_settings(settings):
                self.console.print(f"[bold green]✓ Template Term 已设置为: {new_value or '(未设置)'}[/bold green]")
        
        elif method == "browser":
            self._set_template_term_from_browser(settings, current)

    def set_partner_groups_tag_input(self):
        """设置 Partner Groups：网页下拉、直连 API，或跳过。"""
        settings = self.config.load_settings()
        current_input = bool(settings.get("input_partner_groups_tag", True))
        pg = settings.get("partner_groups")
        if not isinstance(pg, dict):
            pg = {}
        current_mode = (pg.get("mode") or "ui").strip().lower()

        if not current_input:
            mode_desc = "跳过"
        elif current_mode == "api":
            mode_desc = "接口（API）"
        else:
            mode_desc = "网页输入与下拉选择"

        self.console.print(
            f"[cyan]当前：Partner Groups = [bold]{mode_desc}[/bold][/cyan]"
        )

        selected = questionary.select(
            "请选择 Partner Groups 设置方式:",
            choices=[
                questionary.Choice("✅ 网页输入并下拉选择", value="ui"),
                questionary.Choice("🌐 直连接口（在 settings.json 的 partner_groups.api 填写 Reqable 抓到的 URL/Body）", value="api"),
                questionary.Choice("🚫 跳过", value="skip"),
                questionary.Choice("🔙 取消", value=None),
            ],
            style=questionary.Style([
                ('highlighted', 'fg:cyan bold'),
                ('pointer', 'fg:cyan bold'),
            ])
        ).ask()

        if selected is None:
            self.console.print("[yellow]已取消[/yellow]")
            return

        base_pg = {
            "mode": "ui",
            "api": {
                "url": "",
                "method": "POST",
                "headers": {},
                "body": None,
                "csrf_meta_selector": "",
                "csrf_header_name": "X-CSRF-Token",
                "success_status_min": 200,
                "success_status_max": 299,
            },
            "id_by_name": {},
        }
        merged_pg = {**base_pg, **pg} if isinstance(pg, dict) else dict(base_pg)
        if isinstance(pg.get("api"), dict):
            merged_pg["api"] = {**base_pg["api"], **pg["api"]}

        if selected == "skip":
            settings["input_partner_groups_tag"] = False
        elif selected == "api":
            settings["input_partner_groups_tag"] = True
            merged_pg["mode"] = "api"
        else:
            settings["input_partner_groups_tag"] = True
            merged_pg["mode"] = "ui"

        settings["partner_groups"] = merged_pg
        if self.config.save_settings(settings):
            if self.proposal_sender:
                self.proposal_sender.refresh_from_settings(self.config.load_settings())
            if selected == "skip":
                self.console.print("[bold green]✓ 已设置：跳过 Partner Groups[/bold green]")
            elif selected == "api":
                self.console.print(
                    "[bold green]✓ 已切换为 API 模式[/bold green]；请确认 "
                    "[cyan]config/settings.json[/cyan] 中 [bold]partner_groups.api.url[/bold] 等已按 Reqable 抓包填写。"
                )
            else:
                self.console.print("[bold green]✓ 已切换为网页下拉选择模式[/bold green]")
    
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
    def check_and_update(self):
        """检查并更新代码"""
        try:
            from update_manager import UpdateManager
            update_manager = UpdateManager(console=self.console)
            update_manager.show_update_ui()
            questionary.press_any_key_to_continue("按任意键返回主菜单...").ask()
        except ImportError:
            self.console.print("[red]错误：无法导入更新管理器模块[/red]")
            self.console.print("[yellow]请检查 update_manager.py 是否存在且依赖已正确安装[/yellow]")
            questionary.press_any_key_to_continue("按任意键返回主菜单...").ask()
        except Exception as e:
            self.console.print(f"[red]更新失败: {e}[/red]")
            logger.error(f"更新失败: {e}")
            questionary.press_any_key_to_continue("按任意键返回主菜单...").ask()


