"""
Update Manager - 使用原生 Git 管理代码更新
提供 git fetch/pull 功能，并自动保护配置文件
"""
import os
import subprocess
from pathlib import Path
from typing import Dict, Optional, Tuple

import questionary
from loguru import logger
from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn


class UpdateManager:
    """代码更新管理类，使用原生 git 实现更新功能。"""
    
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
    
    def _run_git(self, *args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
        """运行 git 命令并返回结果。"""
        try:
            result = subprocess.run(
                ["git", *args],
                cwd=self.repo_path,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                check=False,
            )
        except FileNotFoundError as exc:
            logger.error("未找到 git 命令")
            raise RuntimeError("未找到 git 命令，请先安装 Git 并确保 git 已加入 PATH") from exc

        if check and result.returncode != 0:
            error_message = (result.stderr or result.stdout).strip() or "未知 Git 错误"
            logger.error(f"Git 命令失败 git {' '.join(args)}: {error_message}")
            raise RuntimeError(error_message)

        return result

    def _ensure_repo(self) -> None:
        """确认当前路径是 Git 仓库。"""
        output = self._run_git("rev-parse", "--is-inside-work-tree").stdout.strip().lower()
        if output != "true":
            raise RuntimeError(f"当前目录不是 Git 仓库: {self.repo_path}")

    def _get_current_branch(self) -> str:
        """获取当前分支名。"""
        branch = self._run_git("branch", "--show-current").stdout.strip()
        if not branch:
            raise RuntimeError("当前 HEAD 处于 detached 状态，无法自动更新")
        return branch

    def _get_upstream_ref(self) -> str:
        """获取当前分支的上游分支引用。"""
        upstream = self._run_git(
            "rev-parse",
            "--abbrev-ref",
            "--symbolic-full-name",
            "@{u}",
        ).stdout.strip()
        if not upstream:
            raise RuntimeError("当前分支未配置上游分支，无法检查更新")
        return upstream

    def _fetch_upstream(self, upstream_ref: str) -> None:
        """拉取上游远程最新引用。"""
        remote_name = upstream_ref.split("/", 1)[0]
        self._run_git("fetch", "--quiet", remote_name)

    def _get_commit_hash(self, ref: str = "HEAD", short: bool = True) -> str:
        """获取指定引用的 commit hash。"""
        flag = "--short=7" if short else "--verify"
        return self._run_git("rev-parse", flag, ref).stdout.strip()

    def _get_divergence(self) -> Tuple[int, int]:
        """获取当前分支相对上游的 ahead/behind 数量。"""
        output = self._run_git("rev-list", "--left-right", "--count", "HEAD...@{u}").stdout.strip()
        parts = output.split()
        if len(parts) != 2:
            raise RuntimeError(f"无法解析分支差异信息: {output}")
        ahead, behind = (int(parts[0]), int(parts[1]))
        return ahead, behind

    def _get_non_protected_local_changes(self) -> list[str]:
        """获取除受保护配置外的已跟踪本地改动。"""
        changed_files: set[str] = set()
        for args in (("diff", "--name-only"), ("diff", "--cached", "--name-only")):
            output = self._run_git(*args).stdout
            for line in output.splitlines():
                normalized = line.strip().replace("\\", "/")
                if normalized:
                    changed_files.add(normalized)

        protected = {path.replace("\\", "/") for path in self.PROTECTED_FILES}
        return sorted(path for path in changed_files if path not in protected)
    
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
            self._ensure_repo()
            branch = self._get_current_branch()
            upstream = self._get_upstream_ref()
            self._fetch_upstream(upstream)

            current_hash = self._get_commit_hash("HEAD")
            upstream_hash = self._get_commit_hash("@{u}")
            ahead, behind = self._get_divergence()

            if ahead > 0 and behind > 0:
                return False, (
                    f"当前分支 {branch} 与上游 {upstream} 已分叉\n"
                    f"本地提交: +{ahead}，远程提交: +{behind}\n"
                    "请先手动处理分叉后再更新"
                )

            if ahead > 0:
                return False, (
                    f"当前分支 {branch} 领先上游 {upstream} {ahead} 个提交\n"
                    "暂无可直接拉取的更新"
                )

            if behind > 0:
                return True, (
                    f"有新的更新可用\n"
                    f"分支: {branch}\n"
                    f"当前: {current_hash}\n"
                    f"最新: {upstream_hash}"
                )

            return False, "已是最新版本"
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
            # 备份配置文件
            self.console.print("[cyan]正在备份配置文件...[/cyan]")
            backups = self._backup_config_files()

            try:
                self._ensure_repo()
                branch = self._get_current_branch()
                upstream = self._get_upstream_ref()
                self._fetch_upstream(upstream)

                changed_files = self._get_non_protected_local_changes()
                if changed_files:
                    preview = "\n".join(f"- {path}" for path in changed_files[:10])
                    if len(changed_files) > 10:
                        preview += f"\n- ... 共 {len(changed_files)} 个文件"
                    return False, f"检测到未提交的本地改动，已阻止自动更新:\n{preview}"

                ahead, behind = self._get_divergence()
                if ahead > 0 and behind > 0:
                    return False, (
                        f"当前分支 {branch} 与上游 {upstream} 已分叉，"
                        "无法执行安全的自动更新，请先手动处理"
                    )
                if ahead > 0:
                    return False, (
                        f"当前分支 {branch} 领先上游 {upstream} {ahead} 个提交，"
                        "请先决定是否推送或重置后再更新"
                    )
                if behind == 0:
                    return True, "已是最新版本，无需更新"

                self.console.print("[cyan]正在拉取远程更新...[/cyan]")
                self._run_git("pull", "--ff-only")

                # 恢复配置文件
                self.console.print("[cyan]正在恢复配置文件...[/cyan]")
                self._restore_config_files(backups)

                logger.info("代码更新成功")
                return True, f"更新成功！当前分支 {branch} 已同步到 {upstream}"
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
            self._ensure_repo()
            commit_hash = self._get_commit_hash("HEAD")
            message = self._run_git("log", "-1", "--pretty=%s").stdout.strip()
            author = self._run_git("log", "-1", "--pretty=%an <%ae>").stdout.strip()
            commit_date = self._run_git(
                "log",
                "-1",
                "--date=format:%Y-%m-%d %H:%M:%S",
                "--pretty=%ad",
            ).stdout.strip()

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
