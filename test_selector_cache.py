"""
测试日期选择器的选择器缓存功能

验证选择器缓存是否正常工作，避免重复计算选择器语法
"""

import os
import sys
from datetime import datetime, timedelta

from loguru import logger
from rich.console import Console

sys.path.insert(0, os.path.dirname(__file__))

from main import DatePicker


def test_selector_cache():
    """测试选择器缓存功能"""
    console = Console()
    picker = DatePicker(console)
    
    console.print("[bold cyan]===== 测试选择器缓存功能 =====[/bold cyan]\n")
    
    # 测试 1: 验证初始状态下选择器缓存为空
    console.print(f"[yellow]测试 1: 验证初始状态[/yellow]")
    console.print(f"选择器缓存: {picker._selector_cache}")
    
    if all(v is None for v in picker._selector_cache.values()):
        console.print(f"[green]✓ 初始状态下所有选择器缓存为空[/green]")
    else:
        console.print(f"[red]✗ 初始状态异常[/red]")
        return False
    
    # 测试 2: 模拟设置缓存
    console.print(f"\n[yellow]测试 2: 模拟设置选择器缓存[/yellow]")
    picker._selector_cache['date_input'] = 'css:button[data-testid="uicl-date-input"]'
    picker._selector_cache['prev_month'] = 'css:button[aria-label="Previous"]'
    picker._selector_cache['next_month'] = 'css:button[aria-label="Next"]'
    picker._selector_cache['date_cell'] = 'css:button'
    
    console.print(f"设置后的缓存:")
    for key, value in picker._selector_cache.items():
        console.print(f"  - {key}: {value}")
    
    if all(v is not None for v in picker._selector_cache.values()):
        console.print(f"[green]✓ 选择器缓存设置成功[/green]")
    else:
        console.print(f"[red]✗ 选择器缓存设置失败[/red]")
        return False
    
    # 测试 3: 验证缓存可以被清除
    console.print(f"\n[yellow]测试 3: 验证缓存可以被清除[/yellow]")
    picker._selector_cache['date_input'] = None
    picker._selector_cache['prev_month'] = None
    
    console.print(f"清除部分缓存后:")
    for key, value in picker._selector_cache.items():
        console.print(f"  - {key}: {value}")
    
    if (picker._selector_cache['date_input'] is None and 
        picker._selector_cache['prev_month'] is None and
        picker._selector_cache['next_month'] is not None and
        picker._selector_cache['date_cell'] is not None):
        console.print(f"[green]✓ 选择器缓存可以被正确清除[/green]")
    else:
        console.print(f"[red]✗ 选择器缓存清除异常[/red]")
        return False
    
    # 测试 4: 验证缓存独立性（多个 DatePicker 实例）
    console.print(f"\n[yellow]测试 4: 验证缓存独立性[/yellow]")
    picker2 = DatePicker(console)
    
    # picker 有缓存，picker2 没有缓存
    console.print(f"picker1 的缓存: {picker._selector_cache}")
    console.print(f"picker2 的缓存: {picker2._selector_cache}")
    
    if (picker._selector_cache['next_month'] is not None and
        picker2._selector_cache['next_month'] is None):
        console.print(f"[green]✓ 不同实例的缓存相互独立[/green]")
    else:
        console.print(f"[red]✗ 缓存独立性异常[/red]")
        return False
    
    # 测试 5: 验证选择器缓存结构
    console.print(f"\n[yellow]测试 5: 验证选择器缓存结构[/yellow]")
    picker3 = DatePicker(console)
    
    expected_keys = {'date_input', 'prev_month', 'next_month', 'date_cell'}
    actual_keys = set(picker3._selector_cache.keys())
    
    if expected_keys == actual_keys:
        console.print(f"[green]✓ 选择器缓存包含所有必需的键[/green]")
        console.print(f"  缓存键: {list(picker3._selector_cache.keys())}")
    else:
        console.print(f"[red]✗ 选择器缓存键不匹配[/red]")
        console.print(f"  期望: {expected_keys}")
        console.print(f"  实际: {actual_keys}")
        return False
    
    # 测试 6: 结合导航缓存验证完整功能
    console.print(f"\n[yellow]测试 6: 验证选择器缓存与导航缓存共存[/yellow]")
    picker4 = DatePicker(console)
    
    # 设置导航缓存
    target_date = datetime.now() + timedelta(days=1)
    picker4.precalculate_navigation(target_date)
    
    # 设置选择器缓存
    picker4._selector_cache['date_input'] = 'css:button[data-testid="test"]'
    
    console.print(f"导航缓存数量: {len(picker4._navigation_cache)}")
    console.print(f"选择器缓存: {picker4._selector_cache}")
    
    if (len(picker4._navigation_cache) > 0 and
        picker4._selector_cache['date_input'] is not None):
        console.print(f"[green]✓ 导航缓存和选择器缓存可以共存[/green]")
    else:
        console.print(f"[red]✗ 缓存共存异常[/red]")
        return False
    
    console.print(f"\n[bold green]===== 所有测试通过！ =====[/bold green]")
    return True


if __name__ == "__main__":
    try:
        success = test_selector_cache()
        sys.exit(0 if success else 1)
    except Exception as e:
        logger.exception(f"测试失败: {e}")
        sys.exit(1)
