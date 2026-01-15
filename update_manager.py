"""
Update Manager - 使用 Dulwich 管理代码更新
提供 git pull 功能，并自动忽略配置文件
"""
import os
from pathlib import Path
from typing import Dict, Optional, Tuple
from loguru import logger
from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn
import questionary


class UpdateManager:
    """代码更新管理类，使用 Dulwich 实现 git pull 功能"""
    
    # 需要保护的配置文件列表（不会被更新覆盖）
    PROTECTED_FILES = [
        'config/settings.json',
        'config/template.txt',
        'config/templates.json',
    ]
    
    def __init__(self, repo_path: Optional[str] = None, console: Optional[Console] = None):
        """
        初始化更新管理器
        
        Args:
            repo_path: Git 仓库路径，默认为当前目录
            console: Rich Console 对象，用于输出
        """
        self.repo_path = Path(repo_path or os.path.dirname(__file__)).absolute()
        self.console = console or Console()
        self._repo = None
    
    def _get_repo(self):
        """获取 Dulwich Repo 对象"""
        if self._repo is None:
            try:
                from dulwich.repo import Repo
                self._repo = Repo(str(self.repo_path))
            except Exception as e:
                logger.error(f"无法打开 Git 仓库: {e}")
                raise
        return self._repo
    
    def _backup_config_files(self) -> Dict[str, bytes]:
        """备份配置文件内容"""
        backups: Dict[str, bytes] = {}
        for file_path in self.PROTECTED_FILES:
            full_path = self.repo_path / file_path
            if full_path.exists():
                try:
                    with open(full_path, 'rb') as f:
                        backups[file_path] = f.read()
                    logger.debug(f"已备份配置文件: {file_path}")
                except Exception as e:
                    logger.warning(f"备份配置文件失败 {file_path}: {e}")
        return backups
    
    def _restore_config_files(self, backups: Dict[str, bytes]):
        """恢复配置文件内容"""
        for file_path, content in backups.items():
            full_path = self.repo_path / file_path
            try:
                full_path.parent.mkdir(parents=True, exist_ok=True)
                with open(full_path, 'wb') as f:
                    f.write(content)
                logger.debug(f"已恢复配置文件: {file_path}")
            except Exception as e:
                logger.error(f"恢复配置文件失败 {file_path}: {e}")
    
    def check_for_updates(self) -> Tuple[bool, str]:
        """
        检查是否有可用更新
        
        Returns:
            (has_updates, message): 是否有更新和描述信息
        """
        try:
            from dulwich.client import get_transport_and_path
            from dulwich.porcelain import get_remote_repo
            
            repo = self._get_repo()
            
            # 获取远程仓库信息
            config = repo.get_config()
            remote_url = config.get((b'remote', b'origin'), b'url')
            if not remote_url:
                return False, "未配置远程仓库"
            
            remote_url = remote_url.decode('utf-8')
            
            # 获取当前分支
            head = repo.head()
            current_commit = repo[head]
            
            # 获取远程最新提交
            try:
                client, path = get_transport_and_path(remote_url)
                remote_refs = client.fetch(path, repo)
                
                # 获取远程 HEAD
                remote_head = remote_refs.get(b'refs/heads/main') or remote_refs.get(b'refs/heads/master')
                if not remote_head:
                    return False, "无法获取远程分支信息"
                
                # 安全地格式化 commit hash
                current_hash = head[:7].decode('utf-8', errors='ignore') if len(head) >= 7 else head.decode('utf-8', errors='ignore')
                remote_hash = remote_head[:7].decode('utf-8', errors='ignore') if len(remote_head) >= 7 else remote_head.decode('utf-8', errors='ignore')
                
                if head != remote_head:
                    return True, f"有新的更新可用\n当前: {current_hash}\n最新: {remote_hash}"
                else:
                    return False, "已是最新版本"
                    
            except Exception as e:
                logger.warning(f"检查远程更新失败: {e}")
                return False, f"检查更新失败: {str(e)}"
                
        except Exception as e:
            logger.error(f"检查更新时出错: {e}")
            return False, f"检查更新失败: {str(e)}"
    
    def pull_updates(self) -> Tuple[bool, str]:
        """
        从远程仓库拉取更新
        
        Returns:
            (success, message): 是否成功和描述信息
        """
        try:
            from dulwich.porcelain import pull
            
            # 备份配置文件
            self.console.print("[cyan]正在备份配置文件...[/cyan]")
            backups = self._backup_config_files()
            
            # 执行 git pull
            self.console.print("[cyan]正在拉取远程更新...[/cyan]")
            
            try:
                repo = self._get_repo()
                config = repo.get_config()
                remote_url = config.get((b'remote', b'origin'), b'url')
                
                if not remote_url:
                    return False, "未配置远程仓库"
                
                remote_url = remote_url.decode('utf-8')
                
                # 使用 dulwich.porcelain.pull
                result = pull(str(self.repo_path), remote_url)
                
                # 恢复配置文件
                self.console.print("[cyan]正在恢复配置文件...[/cyan]")
                self._restore_config_files(backups)
                
                logger.info("代码更新成功")
                return True, "更新成功！配置文件已保护"
                
            except Exception as e:
                # 更新失败，恢复配置文件
                logger.error(f"更新失败: {e}")
                self._restore_config_files(backups)
                return False, f"更新失败: {str(e)}"
                
        except Exception as e:
            logger.error(f"拉取更新时出错: {e}")
            return False, f"更新失败: {str(e)}"
    
    def get_current_version(self) -> str:
        """
        获取当前版本信息（当前 commit）
        
        Returns:
            当前版本的 commit hash 和信息
        """
        try:
            repo = self._get_repo()
            head = repo.head()
            commit = repo[head]
            
            # 获取提交信息
            message = commit.message.decode('utf-8').strip().split('\n')[0]
            author = commit.author.decode('utf-8')
            commit_time = commit.commit_time
            
            from datetime import datetime
            commit_date = datetime.fromtimestamp(commit_time).strftime('%Y-%m-%d %H:%M:%S')
            
            # 安全地格式化 commit hash
            commit_hash = head[:7].decode('utf-8', errors='ignore') if len(head) >= 7 else head.decode('utf-8', errors='ignore')
            
            version_info = (
                f"Commit: {commit_hash}\n"
                f"信息: {message}\n"
                f"作者: {author}\n"
                f"日期: {commit_date}"
            )
            
            return version_info
            
        except Exception as e:
            logger.error(f"获取版本信息失败: {e}")
            return f"无法获取版本信息: {str(e)}"
    
    def show_update_ui(self):
        """显示更新界面（TUI）"""
        self.console.print(Panel.fit(
            "[bold cyan]代码更新工具[/bold cyan]",
            border_style="cyan"
        ))
        
        # 显示当前版本
        self.console.print("\n[bold]当前版本信息：[/bold]")
        self.console.print(Panel(
            self.get_current_version(),
            border_style="blue"
        ))
        
        # 检查更新
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=self.console,
            transient=True
        ) as progress:
            progress.add_task(description="正在检查更新...", total=None)
            has_updates, message = self.check_for_updates()
        
        if has_updates:
            self.console.print(Panel(
                f"[bold green]{message}[/bold green]",
                title="检测到更新",
                border_style="green"
            ))
            
            # 询问是否更新
            if questionary.confirm("是否立即更新?", default=True).ask():
                with Progress(
                    SpinnerColumn(),
                    TextColumn("[progress.description]{task.description}"),
                    console=self.console,
                    transient=True
                ) as progress:
                    progress.add_task(description="正在更新代码...", total=None)
                    success, result_msg = self.pull_updates()
                
                if success:
                    self.console.print(Panel(
                        f"[bold green]{result_msg}[/bold green]\n\n"
                        "[yellow]提示：更新完成后，建议重启程序以加载最新代码[/yellow]",
                        title="更新成功",
                        border_style="green"
                    ))
                else:
                    self.console.print(Panel(
                        f"[bold red]{result_msg}[/bold red]",
                        title="更新失败",
                        border_style="red"
                    ))
            else:
                self.console.print("[yellow]已取消更新[/yellow]")
        else:
            self.console.print(Panel(
                f"[bold blue]{message}[/bold blue]",
                title="检查完成",
                border_style="blue"
            ))
