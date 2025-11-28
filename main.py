from DrissionPage import Chromium
import time
import os
import json
import re
from datetime import datetime, timedelta
from loguru import logger
import questionary
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.syntax import Syntax
from rich import print as rprint
import pyperclip

console = Console()

# 配置日志
LOG_DIR = os.path.join(os.path.dirname(__file__), 'logs')
os.makedirs(LOG_DIR, exist_ok=True)
logger.add(
    os.path.join(LOG_DIR, 'impact_rpa_{time:YYYY-MM-DD}.log'),
    rotation='1 day',
    retention='7 days',
    level='INFO',
    format='{time:YYYY-MM-DD HH:mm:ss} | {level} | {message}',
    encoding='utf-8'
)

# 配置文件路径
CONFIG_DIR = os.path.join(os.path.dirname(__file__), 'config')
TEMPLATE_FILE = os.path.join(CONFIG_DIR, 'template.txt')
TEMPLATES_FILE = os.path.join(CONFIG_DIR, 'templates.json')
SETTINGS_FILE = os.path.join(CONFIG_DIR, 'settings.json')

browser = Chromium()
tab = browser.latest_tab


def load_template():
    """加载当前激活的留言模板"""
    try:
        templates_data = load_all_templates()
        active_id = templates_data.get('active_template_id', 1)
        for tpl in templates_data.get('templates', []):
            if tpl.get('id') == active_id:
                return tpl.get('content', '')
        # 如果没找到激活的模板，返回第一个
        if templates_data.get('templates'):
            return templates_data['templates'][0].get('content', '')
    except Exception as e:
        logger.error(f"加载模板失败: {e}")
    return ""


def load_all_templates():
    """加载所有模板数据"""
    default_data = {"templates": [], "active_template_id": None}
    try:
        if os.path.exists(TEMPLATES_FILE):
            with open(TEMPLATES_FILE, 'r', encoding='utf-8') as f:
                return {**default_data, **json.load(f)}
        # 兼容旧的单模板文件
        elif os.path.exists(TEMPLATE_FILE):
            with open(TEMPLATE_FILE, 'r', encoding='utf-8') as f:
                content = f.read().strip()
                if content:
                    return {
                        "templates": [{"id": 1, "name": "默认模板", "content": content}],
                        "active_template_id": 1
                    }
    except Exception as e:
        logger.error(f"加载模板数据失败: {e}")
    return default_data


def save_all_templates(data):
    """保存所有模板数据"""
    try:
        os.makedirs(CONFIG_DIR, exist_ok=True)
        with open(TEMPLATES_FILE, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=4, ensure_ascii=False)
        logger.info("模板数据保存成功")
        return True
    except Exception as e:
        logger.error(f"保存模板数据失败: {e}")
        return False


def get_next_template_id(templates_data):
    """获取下一个可用的模板ID"""
    if not templates_data.get('templates'):
        return 1
    max_id = max(tpl.get('id', 0) for tpl in templates_data['templates'])
    return max_id + 1


def get_multiline_input():
    """获取多行输入（支持从剪贴板读取）"""
    choices = [
        questionary.Choice("📋 从剪贴板粘贴", value="clipboard"),
        questionary.Choice("⌨️  手动输入（输入 END 结束）", value="manual"),
        questionary.Choice("🔙 取消", value="cancel"),
    ]
    
    method = questionary.select(
        "选择输入方式:",
        choices=choices
    ).ask()
    
    if method is None or method == "cancel":
        return None
    
    if method == "clipboard":
        try:
            content = pyperclip.paste()
            if content and content.strip():
                console.print("\n[bold green]已从剪贴板读取内容：[/bold green]")
                console.print(Panel(content, border_style="green"))
                
                if questionary.confirm("确认使用此内容?", default=True).ask():
                    return content
                else:
                    return None
            else:
                console.print("[yellow]剪贴板为空[/yellow]")
                return None
        except Exception as e:
            console.print(f"[red]读取剪贴板失败: {e}[/red]")
            return None
    
    else:  # manual
        console.print("[cyan]请输入内容（输入单独一行 'END' 结束）:[/cyan]")
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


def save_template(content):
    """保存留言模板（兼容旧接口，添加为新模板）"""
    try:
        templates_data = load_all_templates()
        new_id = get_next_template_id(templates_data)
        templates_data['templates'].append({
            "id": new_id,
            "name": f"模板 {new_id}",
            "content": content
        })
        templates_data['active_template_id'] = new_id
        return save_all_templates(templates_data)
    except Exception as e:
        logger.error(f"保存模板失败: {e}")
        return False


def load_settings():
    """加载设置"""
    default_settings = {
        "max_proposals": 10,
        "scroll_delay": 1.0,
        "click_delay": 0.5,
        "modal_wait": 1.0
    }
    try:
        if os.path.exists(SETTINGS_FILE):
            with open(SETTINGS_FILE, 'r', encoding='utf-8') as f:
                return {**default_settings, **json.load(f)}
    except Exception as e:
        logger.error(f"加载设置失败: {e}")
    return default_settings


def save_settings(settings):
    """保存设置"""
    try:
        os.makedirs(CONFIG_DIR, exist_ok=True)
        with open(SETTINGS_FILE, 'w', encoding='utf-8') as f:
            json.dump(settings, f, indent=4)
        logger.info("设置保存成功")
        return True
    except Exception as e:
        logger.error(f"保存设置失败: {e}")
        return False


def show_menu():
    """显示主菜单并返回用户选择"""
    console.print(Panel.fit(
        "[bold cyan]Impact RPA - Send Proposal 自动化工具[/bold cyan]",
        border_style="cyan"
    ))
    
    choices = [
        questionary.Choice("🚀 开始发送 Send Proposal", value="1"),
        questionary.Choice("📄 预览当前留言模板", value="2"),
        questionary.Choice("✏️  编辑留言模板", value="3"),
        questionary.Choice("🔢 设置发送数量", value="4"),
        questionary.Choice("⚙️  查看当前设置", value="5"),
        questionary.Choice("🚪 退出程序", value="0"),
    ]
    
    return questionary.select(
        "请选择操作:",
        choices=choices,
        style=questionary.Style([
            ('highlighted', 'fg:cyan bold'),
            ('pointer', 'fg:cyan bold'),
        ])
    ).ask()


def preview_template():
    """预览当前激活的留言模板"""
    templates_data = load_all_templates()
    active_id = templates_data.get('active_template_id')
    
    active_tpl = None
    for tpl in templates_data.get('templates', []):
        if tpl.get('id') == active_id:
            active_tpl = tpl
            break
    
    if active_tpl and active_tpl.get('content'):
        name = active_tpl.get('name', '未命名')
        console.print(Panel(
            active_tpl['content'],
            title=f"[bold green]当前模板: {name}[/bold green]",
            border_style="green"
        ))
    else:
        console.print("[yellow]没有激活的模板[/yellow]")
    
    questionary.press_any_key_to_continue("按任意键返回主菜单...").ask()


def edit_template():
    """编辑留言模板（多模板管理）"""
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
            list_all_templates()
        elif choice == 'preview':
            preview_template()
        elif choice == 'select':
            select_active_template()
        elif choice == 'add':
            add_new_template()
        elif choice == 'edit':
            edit_existing_template()
        elif choice == 'delete':
            delete_template()


def list_all_templates():
    """列出所有模板"""
    templates_data = load_all_templates()
    templates = templates_data.get('templates', [])
    active_id = templates_data.get('active_template_id')
    
    if not templates:
        console.print("[yellow]没有模板[/yellow]")
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
        # 只显示前50个字符作为预览
        preview = content.replace('\n', ' ')[:50]
        if len(content) > 50:
            preview += "..."
        
        status = "[green]✓ 激活[/green]" if tpl_id == active_id else ""
        table.add_row(str(tpl_id), status, name, preview)
    
    console.print(table)
    questionary.press_any_key_to_continue("按任意键继续...").ask()


def select_active_template():
    """选择激活的模板"""
    templates_data = load_all_templates()
    templates = templates_data.get('templates', [])
    active_id = templates_data.get('active_template_id')
    
    if not templates:
        console.print("[yellow]没有模板可选择[/yellow]")
        return
    
    choices = []
    for tpl in templates:
        tpl_id = tpl.get('id', 0)
        name = tpl.get('name', '未命名')
        mark = " ✓" if tpl_id == active_id else ""
        choices.append(questionary.Choice(f"{name}{mark}", value=tpl_id))
    
    choices.append(questionary.Choice("🔙 取消", value=None))
    
    selected = questionary.select(
        "选择要激活的模板:",
        choices=choices
    ).ask()
    
    if selected is not None:
        templates_data['active_template_id'] = selected
        if save_all_templates(templates_data):
            # 找到模板名称
            name = next((t.get('name', '未命名') for t in templates if t.get('id') == selected), '未命名')
            console.print(f"[bold green]✓ 已激活模板: {name}[/bold green]")


def add_new_template():
    """添加新模板"""
    # 输入模板名称
    name = questionary.text(
        "请输入模板名称 (可选，直接回车跳过):",
        default=""
    ).ask()
    
    if name is None:  # 用户按 Ctrl+C
        return
    
    console.print("\n[bold]请选择模板内容的输入方式:[/bold]")
    content = get_multiline_input()
    
    if not content or not content.strip():
        console.print("[yellow]模板内容为空，未保存[/yellow]")
        return
    
    # 预览
    console.print(Panel(
        content,
        title="[bold yellow]新模板预览[/bold yellow]",
        border_style="yellow"
    ))
    
    if not questionary.confirm("确认保存?", default=True).ask():
        console.print("[yellow]已取消[/yellow]")
        return
    
    # 保存
    templates_data = load_all_templates()
    new_id = get_next_template_id(templates_data)
    
    if not name:
        name = f"模板 {new_id}"
    
    templates_data['templates'].append({
        "id": new_id,
        "name": name,
        "content": content
    })
    
    # 询问是否激活
    if questionary.confirm("是否将此模板设为当前激活模板?", default=True).ask():
        templates_data['active_template_id'] = new_id
    
    if save_all_templates(templates_data):
        console.print(f"[bold green]✓ 模板 '{name}' 已保存[/bold green]")
    else:
        console.print("[bold red]✗ 保存失败[/bold red]")


def edit_existing_template():
    """编辑现有模板"""
    templates_data = load_all_templates()
    templates = templates_data.get('templates', [])
    
    if not templates:
        console.print("[yellow]没有模板可编辑[/yellow]")
        return
    
    # 选择要编辑的模板
    choices = []
    for tpl in templates:
        tpl_id = tpl.get('id', 0)
        name = tpl.get('name', '未命名')
        choices.append(questionary.Choice(f"{name} (ID: {tpl_id})", value=tpl_id))
    
    choices.append(questionary.Choice("🔙 取消", value=None))
    
    selected_id = questionary.select(
        "选择要编辑的模板:",
        choices=choices
    ).ask()
    
    if selected_id is None:
        return
    
    # 找到模板
    tpl_index = None
    tpl = None
    for i, t in enumerate(templates):
        if t.get('id') == selected_id:
            tpl_index = i
            tpl = t
            break
    
    if tpl is None:
        console.print("[red]模板不存在[/red]")
        return
    
    # 选择编辑内容
    edit_choices = [
        questionary.Choice("📝 编辑名称", value="name"),
        questionary.Choice("📄 编辑内容", value="content"),
        questionary.Choice("🔙 取消", value=None),
    ]
    
    edit_choice = questionary.select(
        "选择要编辑的内容:",
        choices=edit_choices
    ).ask()
    
    if edit_choice is None:
        return
    elif edit_choice == "name":
        new_name = questionary.text(
            "请输入新的模板名称:",
            default=tpl.get('name', '')
        ).ask()
        
        if new_name:
            templates_data['templates'][tpl_index]['name'] = new_name
            if save_all_templates(templates_data):
                console.print(f"[bold green]✓ 模板名称已更新为: {new_name}[/bold green]")
    
    elif edit_choice == "content":
        console.print("[bold]当前内容:[/bold]")
        console.print(Panel(tpl.get('content', ''), border_style="dim"))
        
        console.print("\n[bold]请选择新内容的输入方式:[/bold]")
        new_content = get_multiline_input()
        
        if new_content and new_content.strip():
            console.print(Panel(
                new_content,
                title="[bold yellow]新内容预览[/bold yellow]",
                border_style="yellow"
            ))
            
            if questionary.confirm("确认保存?", default=True).ask():
                templates_data['templates'][tpl_index]['content'] = new_content
                if save_all_templates(templates_data):
                    console.print("[bold green]✓ 模板内容已更新[/bold green]")
        else:
            console.print("[yellow]内容为空，未更新[/yellow]")


def delete_template():
    """删除模板"""
    templates_data = load_all_templates()
    templates = templates_data.get('templates', [])
    active_id = templates_data.get('active_template_id')
    
    if not templates:
        console.print("[yellow]没有模板可删除[/yellow]")
        return
    
    if len(templates) == 1:
        console.print("[yellow]至少需要保留一个模板[/yellow]")
        return
    
    # 选择要删除的模板
    choices = []
    for tpl in templates:
        tpl_id = tpl.get('id', 0)
        name = tpl.get('name', '未命名')
        mark = " [激活]" if tpl_id == active_id else ""
        choices.append(questionary.Choice(f"{name}{mark} (ID: {tpl_id})", value=tpl_id))
    
    choices.append(questionary.Choice("🔙 取消", value=None))
    
    selected_id = questionary.select(
        "选择要删除的模板:",
        choices=choices
    ).ask()
    
    if selected_id is None:
        return
    
    # 确认删除
    tpl_name = next((t.get('name', '未命名') for t in templates if t.get('id') == selected_id), '未命名')
    
    if not questionary.confirm(f"确认删除模板 '{tpl_name}'?", default=False).ask():
        console.print("[yellow]已取消[/yellow]")
        return
    
    # 删除
    templates_data['templates'] = [t for t in templates if t.get('id') != selected_id]
    
    # 如果删除的是激活的模板，切换到第一个
    if selected_id == active_id and templates_data['templates']:
        templates_data['active_template_id'] = templates_data['templates'][0].get('id')
    
    if save_all_templates(templates_data):
        console.print(f"[bold green]✓ 模板 '{tpl_name}' 已删除[/bold green]")


def set_proposal_count():
    """设置发送数量"""
    settings = load_settings()
    console.print(f"[cyan]当前设置的发送数量: [bold]{settings['max_proposals']}[/bold][/cyan]")
    
    new_count = questionary.text(
        "请输入新的发送数量:",
        default=str(settings['max_proposals']),
        validate=lambda x: x.isdigit() and int(x) > 0 or "请输入大于0的数字"
    ).ask()
    
    if new_count:
        settings['max_proposals'] = int(new_count)
        save_settings(settings)
        console.print(f"[bold green]✓ 发送数量已设置为: {new_count}[/bold green]")


def view_settings():
    """查看当前设置"""
    settings = load_settings()
    
    table = Table(title="当前设置", border_style="blue")
    table.add_column("设置项", style="cyan")
    table.add_column("值", style="green")
    
    table.add_row("发送数量上限", str(settings['max_proposals']))
    table.add_row("滚动延迟", f"{settings['scroll_delay']} 秒")
    table.add_row("点击延迟", f"{settings['click_delay']} 秒")
    table.add_row("弹窗等待", f"{settings['modal_wait']} 秒")
    
    console.print(table)
    questionary.press_any_key_to_continue("按任意键返回主菜单...").ask()


def main_menu():
    """主菜单循环"""
    while True:
        choice = show_menu()
        
        if choice is None:  # 用户按 Ctrl+C
            console.print("\n[yellow]已取消[/yellow]")
            break
        elif choice == '1':
            start_send_proposals()
        elif choice == '2':
            preview_template()
        elif choice == '3':
            edit_template()
        elif choice == '4':
            set_proposal_count()
        elif choice == '5':
            view_settings()
        elif choice == '0':
            console.print("\n[bold cyan]感谢使用，再见！👋[/bold cyan]")
            break


def start_send_proposals():
    """开始发送 Send Proposal"""
    settings = load_settings()
    max_count = settings['max_proposals']
    
    console.print(f"\n[cyan]准备发送 [bold]{max_count}[/bold] 个 Send Proposal[/cyan]")
    
    # 预览模板
    template = load_template()
    if not template:
        console.print("[bold yellow]⚠️  警告: 留言模板为空！[/bold yellow]")
        if not questionary.confirm("是否继续?", default=False).ask():
            return
    else:
        console.print("\n[bold]当前留言模板预览:[/bold]")
        console.print(Panel(template, border_style="dim"))
    
    if not questionary.confirm(
        f"确认开始发送 {max_count} 个 Proposal?",
        default=False
    ).ask():
        console.print("[yellow]已取消[/yellow]")
        return
    
    # 执行发送
    extract_send_proposal_buttons(max_count)


def main():
    url = 'https://app.impact.com/secure/mediapartner/marketplace/new-campaign-marketplace-flow.ihtml?execution=e1s1#sortBy=salepercent&sortOrder=DESC'
    tab.get(url)
    # 等待页面加载
    tab.wait.doc_loaded()
    # 查找人机验证元素
    人机验证 = tab.ele('text=请完成以下操作，验证您是真人。')
    if 人机验证:
        logger.info("检测到人机验证，正在尝试点击...")
        # 人机验证.click()
    else:
        logger.info("未检测到人机验证。")
    # tab.get(url=url)


def extract_send_proposal_buttons(max_count=10):
    """
    循环点击页面上所有的 Send Proposal 按钮
    点击后关闭弹窗，继续点击下一个
    
    Args:
        max_count: 最大发送数量
    """
    url = 'https://app.impact.com/secure/advertiser/discover/radius/fr/partner_discover.ihtml?page=marketplace&slideout_id_type=partner#businessModels=all&sizeRating=large%2Cextra_large&sortBy=reachRating&sortOrder=DESC'
    tab.get(url)
    tab.wait.doc_loaded()
    
    # 等待用户操作完成（如登录、人机验证等）
    console.print(Panel(
        "[bold]浏览器已打开，请完成以下操作：[/bold]\n"
        "1. 登录账号（如果需要）\n"
        "2. 完成人机验证（如果出现）\n"
        "3. 确保页面已正常加载",
        title="[cyan]提示[/cyan]",
        border_style="cyan"
    ))
    questionary.press_any_key_to_continue("操作完成后，按任意键继续...").ask()
    
    logger.info(f"开始发送 Send Proposal，目标数量: {max_count}")
    
    clicked_count = 0
    total_scrolls = 0
    max_scrolls = 100  # 最大滚动次数，防止无限循环
    
    console.print(f"\n[bold cyan]开始循环点击 Send Proposal 按钮 (目标: {max_count} 个)...[/bold cyan]")
    
    while total_scrolls < max_scrolls:
        # 查找当前可见的所有 Send Proposal 按钮
        buttons = tab.eles('css:button[data-testid="uicl-button"]')
        send_proposal_buttons = [btn for btn in buttons if 'Send Proposal' in btn.text]
        
        if not send_proposal_buttons:
            logger.debug("当前页面没有 Send Proposal 按钮，滚动加载更多...")
            tab.scroll.down(500)
            time.sleep(1)
            total_scrolls += 1
            continue
        
        # 遍历当前可见的按钮并点击
        for btn in send_proposal_buttons:
            # 检查是否达到目标数量
            if clicked_count >= max_count:
                logger.info(f"已达到目标数量 {max_count}，停止发送")
                console.print(f"\n[bold green]✓ 已达到目标数量 {max_count}，停止发送[/bold green]")
                console.print(f"\n[bold cyan]===== 完成！共发送了 {clicked_count} 个 Send Proposal =====[/bold cyan]")
                return clicked_count
            
            try:
                # 先获取 selected-tab 的值（在点击按钮之前）
                selected_tab = get_selected_tab_value(btn)
                
                # 向上查找父元素并悬停
                parent = btn.parent()
                for _ in range(10):
                    if parent:
                        try:
                            tab.scroll.to_see(parent)
                            time.sleep(0.2)
                            parent.hover()
                            time.sleep(0.3)
                            
                            # 点击 Send Proposal 按钮
                            btn.click()
                            clicked_count += 1
                            logger.info(f"[{clicked_count}/{max_count}] 已点击 Send Proposal 按钮 (类别: {selected_tab})")
                            console.print(f"[green]✓ [{clicked_count}/{max_count}][/green] 已点击 Send Proposal 按钮 [dim](类别: {selected_tab})[/dim]")
                            time.sleep(0.5)
                            
                            # 在弹窗中选择 Public Commission，并传入 selected_tab 值
                            select_public_commission(selected_tab)
                            break
                        except Exception:
                            parent = parent.parent()
                    else:
                        break
            except Exception as e:
                logger.error(f"点击按钮时出错: {e}")
                console.print(f"[red]✗ 点击按钮时出错: {e}[/red]")
                continue
        
        # 检查是否达到目标数量
        if clicked_count >= max_count:
            break
        
        # 滚动加载更多
        tab.scroll.down(500)
        time.sleep(1)
        total_scrolls += 1
        console.print(f"[dim]滚动第 {total_scrolls} 次，已发送 {clicked_count}/{max_count} 个[/dim]")
    
    logger.info(f"发送完成，共发送 {clicked_count} 个 Send Proposal")
    console.print(f"\n[bold cyan]===== 完成！共发送了 {clicked_count} 个 Send Proposal =====[/bold cyan]")
    return clicked_count


def get_selected_tab_value(btn):
    """
    获取按钮所在行的 selected-tab 值
    """
    try:
        # 向上查找包含 selected-tab 的父元素
        parent = btn.parent()
        for _ in range(20):  # 最多向上查找20层
            if parent:
                selected_tab_ele = parent.ele('css:.selected-tab', timeout=0.1)
                if selected_tab_ele:
                    value = selected_tab_ele.text.strip()
                    return value
                parent = parent.parent()
            else:
                break
        
        # 备用方案：直接在页面查找
        selected_tab_ele = tab.ele('css:.selected-tab', timeout=0.5)
        if selected_tab_ele:
            value = selected_tab_ele.text.strip()
            return value
            
    except Exception as e:
        print(f"  -> 获取 selected-tab 失败: {e}")
    return None


def select_public_commission(selected_tab=None):
    """
    在弹窗的 iframe 中选择 Public Commission 选项，输入 tag，然后选择日期，最后填写留言
    """
    try:
        time.sleep(1)  # 等待弹窗完全加载
        
        # 查找 iframe 并切换进去
        iframe = tab.ele('css:iframe[data-testid="uicl-modal-iframe-content"]', timeout=3)
        if not iframe:
            print("  -> 未找到弹窗 iframe")
            return False
        
        # 在 iframe 中查找并点击 Public Commission
        option = iframe.ele('text:Public Commission', timeout=5)
        if option:
            option.click(by_js=True)
            print("  -> 已选择 Public Commission")
            time.sleep(0.5)
            
            # 如果有 selected_tab 值，在 tag-input 中输入并选择
            if selected_tab:
                input_tag_and_select(iframe, selected_tab)
            
            # 选择日期（第二天）
            select_tomorrow_date(iframe)
            
            # 填写留言
            input_comment(iframe)
            
            # 点击提交按钮
            submit_proposal(iframe)
            return True
        
        # 备用方案：在 iframe 中用 CSS 选择器查找
        options = iframe.eles('css:div.text-ellipsis')
        for opt in options:
            if 'Public Commission' in opt.text:
                opt.click(by_js=True)
                print("  -> 已选择 Public Commission")
                time.sleep(0.5)
                
                # 如果有 selected_tab 值，在 tag-input 中输入并选择
                if selected_tab:
                    input_tag_and_select(iframe, selected_tab)
                
                # 选择日期（第二天）
                select_tomorrow_date(iframe)
                
                # 填写留言
                input_comment(iframe)
                
                # 点击提交按钮
                submit_proposal(iframe)
                return True
            
        print("  -> 未找到 Public Commission 选项")
        return False
            
    except Exception as e:
        print(f"  -> 选择 Public Commission 失败: {e}")
    return False


def input_tag_and_select(iframe, selected_tab):
    """
    在 tag-input 中输入值并从下拉列表中选择
    """
    try:
        # 处理 selected_tab 值，去掉所有空格
        # "Content / Reviews" -> "Content/Reviews"
        search_text = selected_tab.replace(" ", "")
        
        # 查找 tag-input 输入框
        tag_input = iframe.ele('css:input[data-testid="uicl-tag-input-text-input"]', timeout=3)
        if not tag_input:
            raise Exception("未找到 tag-input 输入框")
        
        # 点击输入框
        tag_input.click(by_js=True)
        time.sleep(0.3)
        
        # 输入搜索文本
        tag_input.input(search_text)
        print(f"  -> 已输入 tag: {search_text}")
        time.sleep(0.5)
        
        # 等待下拉列表出现并选择匹配项
        dropdown = iframe.ele('css:[data-testid="uicl-tag-input-dropdown"]', timeout=3)
        if not dropdown:
            raise Exception("未找到下拉列表，输入后没有出现填充项")
        
        # 查找下拉列表中的选项文本（如 "Content/Reviews (136819)"）
        option_div = dropdown.ele('css:div._4-15-1_Baf2T', timeout=2)
        if not option_div:
            # 备用方案：查找 li 元素
            options = dropdown.eles('css:li')
            if not options:
                raise Exception("下拉列表中没有选项")
            option_div = options[0]
        
        option_text = option_div.text.strip()
        print(f"  -> 下拉选项文本: {option_text}")
        
        # 提取选项中的类别名称（去掉括号中的数字）
        # "Content/Reviews (136819)" -> "Content/Reviews"
        import re
        option_category = re.sub(r'\s*\(\d+\)\s*$', '', option_text).replace(" ", "")
        
        # 验证输入的值和下拉选项是否匹配
        if search_text.lower() != option_category.lower():
            raise Exception(f"输入值 '{search_text}' 与下拉选项 '{option_category}' 不匹配")
        
        # 点击选项
        option_div.click(by_js=True)
        print(f"  -> 已选择下拉选项: {option_text}")
        time.sleep(0.3)
        
        # 验证选择是否成功（检查输入框或 hidden input 的值）
        # 查找 tag 容器，确认已添加
        tag_container = iframe.ele('css:.iui-tag-input', timeout=1)
        if tag_container:
            # 检查是否有已选中的 tag
            selected_tags = tag_container.eles('css:.tag, [class*="tag"]')
            if selected_tags:
                print(f"  -> 验证成功，已选择 tag")
                return True
        
        return True
            
    except Exception as e:
        print(f"  -> 输入 tag 并选择失败: {e}")
        raise  # 重新抛出异常


def select_tomorrow_date(iframe):
    """
    在 iframe 中选择日期（第二天）
    """
    try:
        # 点击日期输入按钮打开日期选择器
        date_btn = iframe.ele('css:button[data-testid="uicl-date-input"]', timeout=3)
        if date_btn:
            date_btn.click(by_js=True)
            print("  -> 已打开日期选择器")
            time.sleep(0.5)
            
            # 查找并点击明天的日期
            # 日期选择器通常会高亮今天，明天是下一个可选日期
            # 查找日期选择器中的日期按钮
            from datetime import datetime, timedelta
            tomorrow = datetime.now() + timedelta(days=1)
            tomorrow_day = str(tomorrow.day)
            
            # 查找包含明天日期的按钮/元素
            # 通常日期选择器的日期是按钮或可点击的 div
            date_cells = iframe.eles('css:td, .day, [class*="day"], [class*="date"]')
            for cell in date_cells:
                if cell.text.strip() == tomorrow_day:
                    cell.click(by_js=True)
                    print(f"  -> 已选择日期: {tomorrow.strftime('%Y-%m-%d')}")
                    time.sleep(0.3)
                    return True
            
            # 备用方案：通过文本查找
            date_ele = iframe.ele(f'text={tomorrow_day}', timeout=2)
            if date_ele:
                date_ele.click(by_js=True)
                logger.info(f"已选择日期: {tomorrow.strftime('%Y-%m-%d')}")
                print(f"  -> 已选择日期: {tomorrow.strftime('%Y-%m-%d')}")
                time.sleep(0.3)
                return True
                
            logger.warning("未找到明天的日期")
            print("  -> 未找到明天的日期")
            return False
        else:
            logger.warning("未找到日期输入按钮")
            print("  -> 未找到日期输入按钮")
            return False
            
    except Exception as e:
        logger.error(f"选择日期失败: {e}")
        print(f"  -> 选择日期失败: {e}")
    return False


def input_comment(iframe):
    """
    在 textarea 中输入留言内容
    """
    try:
        # 从文件加载模板
        template = load_template()
        if not template:
            logger.warning("留言模板为空")
            print("  -> 留言模板为空")
            return False
        
        # 查找 textarea
        textarea = iframe.ele('css:textarea[data-testid="uicl-textarea"]', timeout=3)
        if not textarea:
            textarea = iframe.ele('css:textarea[name="comment"]', timeout=2)
        
        if not textarea:
            logger.warning("未找到留言输入框")
            print("  -> 未找到留言输入框")
            return False
        
        # 清空并输入内容
        textarea.click(by_js=True)
        time.sleep(0.2)
        textarea.clear()
        textarea.input(template)
        logger.info("已填写留言内容")
        print("  -> 已填写留言内容")
        time.sleep(0.3)
        return True
        
    except Exception as e:
        logger.error(f"填写留言失败: {e}")
        print(f"  -> 填写留言失败: {e}")
    return False


def submit_proposal(iframe):
    """
    点击提交按钮提交 Proposal
    """
    try:
        # 查找 iframe 中的 Send Proposal 提交按钮
        submit_btn = iframe.ele('css:button[data-testid="uicl-button"]', timeout=3)
        if submit_btn and 'Send Proposal' in submit_btn.text:
            submit_btn.click(by_js=True)
            logger.info("已点击提交按钮")
            print("  -> 已点击提交按钮")
            time.sleep(1)
            
            # 点击确认按钮
            click_understand_button(iframe)
            return True
        
        # 备用方案：通过文本查找
        submit_btn = iframe.ele('text:Send Proposal', timeout=2)
        if submit_btn and submit_btn.tag == 'button':
            submit_btn.click(by_js=True)
            print("  -> 已点击提交按钮")
            time.sleep(1)
            
            # 点击确认按钮
            click_understand_button(iframe)
            return True
        
        # 备用方案2：查找所有按钮
        buttons = iframe.eles('css:button[data-testid="uicl-button"]')
        for btn in buttons:
            if 'Send Proposal' in btn.text:
                btn.click(by_js=True)
                print("  -> 已点击提交按钮")
                time.sleep(1)
                
                # 点击确认按钮
                click_understand_button(iframe)
                return True
        
        print("  -> 未找到提交按钮")
        return False
        
    except Exception as e:
        print(f"  -> 点击提交按钮失败: {e}")
    return False


def click_understand_button(iframe):
    """
    点击 'I understand' 确认按钮
    """
    try:
        time.sleep(0.5)  # 等待弹窗出现
        
        # 在 iframe 中查找 I understand 按钮
        understand_btn = iframe.ele('text:I understand', timeout=3)
        if understand_btn and understand_btn.tag == 'button':
            understand_btn.click(by_js=True)
            print("  -> 已点击 'I understand' 确认按钮")
            time.sleep(0.5)
            return True
        
        # 备用方案：查找所有按钮
        buttons = iframe.eles('css:button[data-testid="uicl-button"]')
        for btn in buttons:
            if 'I understand' in btn.text:
                btn.click(by_js=True)
                print("  -> 已点击 'I understand' 确认按钮")
                time.sleep(0.5)
                return True
        
        # 备用方案2：在主页面查找（可能弹窗不在 iframe 内）
        understand_btn = tab.ele('text:I understand', timeout=2)
        if understand_btn and understand_btn.tag == 'button':
            understand_btn.click(by_js=True)
            print("  -> 已点击 'I understand' 确认按钮")
            time.sleep(0.5)
            return True
        
        print("  -> 未找到 'I understand' 按钮")
        return False
        
    except Exception as e:
        print(f"  -> 点击确认按钮失败: {e}")
    return False


def close_modal():
    """
    关闭弹窗
    """
    try:
        # 查找关闭按钮
        close_btn = tab.ele('css:button[data-testid="uicl-modal-close-button"]', timeout=2)
        if close_btn:
            close_btn.click()
            print("  -> 已关闭弹窗")
            time.sleep(0.3)
            return True
    except Exception as e:
        print(f"  -> 关闭弹窗失败: {e}")
    return False


def extract_buttons_with_hover():
    """
    通过悬停列表项来显示 Send Proposal 按钮，然后提取
    """
    url = 'https://app.impact.com/secure/mediapartner/marketplace/new-campaign-marketplace-flow.ihtml?execution=e1s1#sortBy=salepercent&sortOrder=DESC'
    tab.get(url)
    tab.wait.doc_loaded()
    time.sleep(2)  # 等待页面完全加载
    
    all_buttons = []
    last_count = 0
    no_change_count = 0
    max_no_change = 3
    
    print("开始滚动页面并通过悬停提取 Send Proposal 按钮...")
    
    while no_change_count < max_no_change:
        # 查找页面上的卡片/列表项元素（根据实际页面结构调整选择器）
        cards = tab.eles('css:.campaign-card, .list-item, [class*="card"], [class*="item"]')
        
        if not cards:
            # 如果没有找到，尝试其他选择器
            cards = tab.eles('css:div[class*="row"], tr, li')
        
        for card in cards:
            try:
                # 悬停在卡片上以显示按钮
                card.hover()
                time.sleep(0.3)  # 等待按钮显示
                
                # 在当前卡片中查找 Send Proposal 按钮
                btn = card.ele('xpath:.//button[contains(text(), "Send Proposal")]', timeout=0.5)
                if btn:
                    btn_html = btn.html
                    if btn_html not in [b['html'] for b in all_buttons]:
                        all_buttons.append({
                            'html': btn_html,
                            'text': btn.text,
                        })
                        print(f"找到按钮 {len(all_buttons)}: {btn.text}")
            except Exception as e:
                continue
        
        # 检查是否有新元素
        if len(all_buttons) == last_count:
            no_change_count += 1
        else:
            no_change_count = 0
            last_count = len(all_buttons)
        
        # 滚动页面
        tab.scroll.down(500)
        time.sleep(1)
    
    print(f"\n===== 共找到 {len(all_buttons)} 个 Send Proposal 按钮 =====\n")
    
    for i, btn_info in enumerate(all_buttons, 1):
        print(f"按钮 {i}:")
        print(btn_info['html'])
        print("-" * 50)
    
    return all_buttons


def goto_work_web():
    url = ''


if __name__ == "__main__":
    main_menu()
