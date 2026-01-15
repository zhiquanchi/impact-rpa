#!/usr/bin/env python
"""
测试脚本：验证更新功能
"""
import os
import sys
from pathlib import Path
from update_manager import UpdateManager
from rich.console import Console

def test_update_manager():
    """测试 UpdateManager 基本功能"""
    console = Console()
    console.print("[bold cyan]测试 UpdateManager 功能[/bold cyan]\n")
    
    # 1. 创建 UpdateManager 实例
    console.print("[yellow]1. 创建 UpdateManager 实例...[/yellow]")
    try:
        um = UpdateManager(console=console)
        console.print("[green]✓ 创建成功[/green]\n")
    except Exception as e:
        console.print(f"[red]✗ 创建失败: {e}[/red]")
        return False
    
    # 2. 获取当前版本
    console.print("[yellow]2. 获取当前版本...[/yellow]")
    try:
        version = um.get_current_version()
        console.print("[green]✓ 获取成功:[/green]")
        console.print(f"[dim]{version}[/dim]\n")
    except Exception as e:
        console.print(f"[red]✗ 获取失败: {e}[/red]")
        return False
    
    # 3. 检查更新
    console.print("[yellow]3. 检查远程更新...[/yellow]")
    try:
        has_updates, message = um.check_for_updates()
        console.print(f"[green]✓ 检查完成:[/green]")
        console.print(f"[dim]有更新: {has_updates}[/dim]")
        console.print(f"[dim]消息: {message}[/dim]\n")
    except Exception as e:
        console.print(f"[red]✗ 检查失败: {e}[/red]")
        return False
    
    # 4. 验证配置文件保护
    console.print("[yellow]4. 验证配置文件保护列表...[/yellow]")
    protected = UpdateManager.PROTECTED_FILES
    console.print(f"[green]✓ 保护的文件: {len(protected)} 个[/green]")
    for f in protected:
        console.print(f"[dim]  - {f}[/dim]")
    console.print()
    
    # 5. 测试备份功能
    console.print("[yellow]5. 测试配置文件备份...[/yellow]")
    try:
        backups = um._backup_config_files()
        console.print(f"[green]✓ 备份成功: {len(backups)} 个文件[/green]")
        for f in backups:
            console.print(f"[dim]  - {f} ({len(backups[f])} bytes)[/dim]")
    except Exception as e:
        console.print(f"[red]✗ 备份失败: {e}[/red]")
        return False
    
    console.print("\n[bold green]所有测试通过！[/bold green]")
    return True

if __name__ == "__main__":
    success = test_update_manager()
    sys.exit(0 if success else 1)
