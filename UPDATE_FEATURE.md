# 代码更新功能说明

## 功能概述

Impact RPA 现在支持通过 TUI 界面进行代码更新，使用 Dulwich 库（纯 Python 实现的 Git 客户端）从远程仓库拉取最新代码。

## 主要特性

1. **自动检查更新**：检测远程仓库是否有新的提交
2. **配置文件保护**：更新时自动备份和恢复用户配置文件
3. **TUI 集成**：友好的终端用户界面，便于操作
4. **安全性**：更新失败时自动恢复配置文件

## 使用方法

### 从主菜单访问

1. 启动程序：`python main.py`
2. 在主菜单中选择：`🔄 检查并更新代码` (选项 7)
3. 程序将显示当前版本信息
4. 自动检查远程更新
5. 如果有更新，询问是否立即更新
6. 更新完成后建议重启程序

### 命令行使用

也可以直接导入 `UpdateManager` 类使用：

```python
from update_manager import UpdateManager
from rich.console import Console

console = Console()
um = UpdateManager(console=console)

# 检查更新
has_updates, message = um.check_for_updates()
if has_updates:
    print(f"有更新可用: {message}")
    
    # 执行更新
    success, result = um.pull_updates()
    if success:
        print("更新成功！")
```

## 保护的配置文件

以下配置文件在更新时会被自动保护（备份并恢复）：

- `config/settings.json` - 用户设置
- `config/template.txt` - 留言模板（旧版）
- `config/templates.json` - 留言模板（新版）

## 依赖

- `dulwich>=0.21.0` - Git 操作库
- `loguru` - 日志记录
- `rich` - 终端 UI

## 注意事项

1. **首次使用前需要安装依赖**：
   ```bash
   pip install dulwich
   # 或使用 uv
   uv pip install dulwich
   ```

2. **网络连接**：更新功能需要访问 GitHub，确保网络连接正常

3. **Git 仓库**：此功能仅在 Git 仓库中运行有效

4. **配置文件**：用户的配置文件不会被覆盖，即使远程仓库有同名文件更新

5. **重启建议**：更新完成后建议重启程序以确保新代码生效

## 故障排查

### 问题：提示"无法导入更新管理器模块"

**解决**：安装 dulwich 库
```bash
pip install dulwich
```

### 问题：更新失败

**可能原因**：
- 网络连接问题
- Git 仓库状态异常
- 权限问题

**解决方法**：
1. 检查网络连接
2. 确认有 Git 仓库的访问权限
3. 查看日志文件了解详细错误信息

### 问题：配置文件丢失

**说明**：更新功能会自动保护配置文件，正常情况下不会丢失。如果出现问题：
- 检查 `logs/` 目录下的日志文件
- 配置文件已在 `.gitignore` 中，不会被 Git 覆盖

## 技术实现

- **Dulwich**：使用纯 Python 实现的 Git 客户端，无需系统安装 Git
- **文件保护**：更新前备份配置文件内容到内存，更新后恢复
- **错误处理**：任何更新失败都会触发配置文件恢复机制
- **UI 集成**：使用 Rich 库提供美观的终端界面

## 开发说明

如需修改保护的文件列表，编辑 `update_manager.py` 中的 `PROTECTED_FILES` 常量：

```python
PROTECTED_FILES = [
    'config/settings.json',
    'config/template.txt',
    'config/templates.json',
    # 添加其他需要保护的文件
]
```
