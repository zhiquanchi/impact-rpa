import html
import io
import json
import os
import subprocess
import sys
from datetime import datetime

from PyQt6.QtCore import Qt, QThread, QTimer, pyqtSignal
from PyQt6.QtGui import QFont, QTextCursor
from PyQt6.QtWidgets import (
    QApplication,
    QCheckBox,
    QDialog,
    QFormLayout,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSplitter,
    QTabWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)
from rich.console import Console

from core.config_manager import ConfigManager
from core.settings_service import SettingsService
from core.template_manager import TemplateManager
from domain.proposal_sender import ProposalSender
from infra.browser_manager import BrowserManager


def count_today_sent(config: ConfigManager) -> int:
    today_str = datetime.now().strftime("%Y-%m-%d")
    log_file = os.path.join(config.log_dir, f"impact_rpa_{today_str}.log")
    success_markers = (
        "已点击 Send Proposal 按钮",
        "发送成功: row=",
    )
    count = 0

    try:
        if os.path.exists(log_file):
            with open(log_file, "r", encoding="utf-8") as f:
                for line in f:
                    if any(marker in line for marker in success_markers):
                        count += 1
    except Exception:
        pass

    if count > 0:
        return count

    try:
        for filename in os.listdir(config.log_dir):
            if not filename.startswith("creator_search_sent_") or not filename.endswith(".json"):
                continue
            filepath = os.path.join(config.log_dir, filename)
            with open(filepath, "r", encoding="utf-8") as f:
                records = json.load(f)
            for record in records:
                timestamp = str(record.get("timestamp", ""))
                if timestamp.startswith(today_str):
                    count += 1
    except Exception:
        pass

    return count


def infer_log_level(message: str) -> str:
    lowered = message.lower()
    if any(token in lowered for token in ("失败", "异常", "错误", "[err]", "traceback")):
        return "error"
    if any(token in lowered for token in ("警告", "超时", "跳过", "停止请求", "[skip]", "warn")):
        return "warn"
    if any(token in lowered for token in ("完成", "成功", "[ok]", "✓")):
        return "success"
    if any(token in lowered for token in ("开始", "准备", "目标", "处理中")):
        return "highlight"
    return "info"


def has_browser_process() -> bool:
    try:
        import psutil

        for proc in psutil.process_iter(["name"]):
            name = (proc.info.get("name") or "").lower()
            if "chrome" in name or "edge" in name or "msedge" in name:
                return True
    except Exception:
        pass

    if sys.platform.startswith("win"):
        try:
            output = subprocess.check_output(
                ["tasklist"],
                text=True,
                encoding="utf-8",
                errors="ignore",
            ).lower()
            return "chrome.exe" in output or "msedge.exe" in output
        except Exception:
            return False

    return False


class QtLogStream:
    def __init__(self, emit_line):
        self.emit_line = emit_line
        self._buffer = ""

    def write(self, text: str) -> int:
        if not text:
            return 0
        self._buffer += text.replace("\r", "")
        while "\n" in self._buffer:
            line, self._buffer = self._buffer.split("\n", 1)
            line = line.strip()
            if line:
                self.emit_line(line)
        return len(text)

    def flush(self) -> None:
        pending = self._buffer.strip()
        if pending:
            self.emit_line(pending)
        self._buffer = ""

    def isatty(self) -> bool:
        return False


class SettingsDialog(QDialog):
    def __init__(self, snapshot: dict, parent=None):
        super().__init__(parent)
        self.setWindowTitle("系统设置")
        self.setFixedSize(420, 320)

        layout = QVBoxLayout(self)
        form_layout = QFormLayout()

        self.max_proposals_input = QLineEdit(str(snapshot.get("max_proposals", 10)))
        self.scroll_delay_input = QLineEdit(str(snapshot.get("scroll_delay", 1.0)))
        self.click_delay_input = QLineEdit(str(snapshot.get("click_delay", 0.5)))
        self.modal_wait_input = QLineEdit(str(snapshot.get("modal_wait", 20.0)))
        self.dry_run_check = QCheckBox("启用 Dry Run（只跑流程，不提交）")
        self.dry_run_check.setChecked(bool(snapshot.get("dry_run", False)))
        self.partner_groups_check = QCheckBox("在 Proposal 弹窗内输入 Partner Groups 标签")
        self.partner_groups_check.setChecked(bool(snapshot.get("input_partner_groups_tag", True)))

        form_layout.addRow("默认发送数量:", self.max_proposals_input)
        form_layout.addRow("滚动延迟 (秒):", self.scroll_delay_input)
        form_layout.addRow("点击延迟 (秒):", self.click_delay_input)
        form_layout.addRow("弹窗等待时间 (秒):", self.modal_wait_input)
        form_layout.addRow("", self.dry_run_check)
        form_layout.addRow("", self.partner_groups_check)
        layout.addLayout(form_layout)

        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        cancel_btn = QPushButton("取消")
        cancel_btn.clicked.connect(self.reject)
        save_btn = QPushButton("保存设置")
        save_btn.setObjectName("primaryBtn")
        save_btn.clicked.connect(self.accept)
        btn_layout.addWidget(cancel_btn)
        btn_layout.addWidget(save_btn)
        layout.addLayout(btn_layout)

    def get_settings(self) -> dict:
        return {
            "max_proposals": self._parse_positive_int(self.max_proposals_input.text(), "默认发送数量"),
            "scroll_delay": self._parse_positive_float(self.scroll_delay_input.text(), "滚动延迟"),
            "click_delay": self._parse_positive_float(self.click_delay_input.text(), "点击延迟", allow_zero=True),
            "modal_wait": self._parse_positive_float(self.modal_wait_input.text(), "弹窗等待时间"),
            "dry_run": self.dry_run_check.isChecked(),
            "input_partner_groups_tag": self.partner_groups_check.isChecked(),
        }

    @staticmethod
    def _parse_positive_int(value: str, field_name: str) -> int:
        try:
            parsed = int(value.strip())
        except ValueError as exc:
            raise ValueError(f"{field_name} 请输入有效整数") from exc
        if parsed < 1:
            raise ValueError(f"{field_name} 需大于等于 1")
        return parsed

    @staticmethod
    def _parse_positive_float(value: str, field_name: str, allow_zero: bool = False) -> float:
        try:
            parsed = float(value.strip())
        except ValueError as exc:
            raise ValueError(f"{field_name} 请输入有效数字") from exc
        if allow_zero and parsed < 0:
            raise ValueError(f"{field_name} 不能小于 0")
        if not allow_zero and parsed <= 0:
            raise ValueError(f"{field_name} 需大于 0")
        return parsed


class TemplateDialog(QDialog):
    template_updated = pyqtSignal()

    def __init__(self, template_manager: TemplateManager, parent=None):
        super().__init__(parent)
        self.template_manager = template_manager
        self.current_template_id: int | None = None

        self.setWindowTitle("模板管理")
        self.resize(860, 520)

        layout = QHBoxLayout(self)

        left_panel = QVBoxLayout()
        self.add_btn = QPushButton("+ 新建模板")
        self.add_btn.clicked.connect(self.create_template)
        self.list_widget = QListWidget()
        self.list_widget.currentRowChanged.connect(self.on_template_selected)
        left_panel.addWidget(self.add_btn)
        left_panel.addWidget(self.list_widget)

        right_panel = QVBoxLayout()
        self.name_input = QLineEdit()
        self.name_input.setPlaceholderText("模板名称")
        self.content_input = QTextEdit()
        self.content_input.setPlaceholderText("模板内容...")

        btn_layout = QHBoxLayout()
        self.delete_btn = QPushButton("删除")
        self.delete_btn.clicked.connect(self.delete_template)
        self.set_active_btn = QPushButton("设为当前激活模板")
        self.set_active_btn.clicked.connect(self.set_active_template)
        self.save_btn = QPushButton("保存")
        self.save_btn.setObjectName("primaryBtn")
        self.save_btn.clicked.connect(self.save_template)

        btn_layout.addWidget(self.delete_btn)
        btn_layout.addWidget(self.set_active_btn)
        btn_layout.addStretch()
        btn_layout.addWidget(self.save_btn)

        right_panel.addWidget(QLabel("模板名称"))
        right_panel.addWidget(self.name_input)
        right_panel.addWidget(QLabel("模板内容"))
        right_panel.addWidget(self.content_input)
        right_panel.addLayout(btn_layout)

        layout.addLayout(left_panel, 1)
        layout.addLayout(right_panel, 2)

        self.load_templates()

    def load_templates(self, select_id: int | None = None) -> None:
        self.data = self.template_manager.load_all()
        self.templates = self.data.get("templates", [])
        self.active_id = self.data.get("active_template_id")

        self.list_widget.clear()
        for tpl in self.templates:
            display_text = f"{tpl.get('name', '未命名')} {'(激活)' if tpl.get('id') == self.active_id else ''}"
            self.list_widget.addItem(display_text)

        if not self.templates:
            self.current_template_id = None
            self.name_input.clear()
            self.content_input.clear()
            self._update_buttons_state()
            return

        target_id = select_id
        if target_id is None:
            target_id = self.current_template_id or self.active_id or self.templates[0].get("id")

        for index, tpl in enumerate(self.templates):
            if tpl.get("id") == target_id:
                self.list_widget.setCurrentRow(index)
                return
        self.list_widget.setCurrentRow(0)

    def on_template_selected(self, row: int) -> None:
        if row < 0 or row >= len(self.templates):
            return
        tpl = self.templates[row]
        self.current_template_id = tpl.get("id")
        self.name_input.setText(tpl.get("name", ""))
        self.content_input.setPlainText(tpl.get("content", ""))
        self._update_buttons_state()

    def create_template(self) -> None:
        self.current_template_id = None
        self.list_widget.setCurrentRow(-1)
        self.list_widget.clearSelection()
        self.name_input.clear()
        self.content_input.clear()
        self._update_buttons_state()
        self.name_input.setFocus()

    def _update_buttons_state(self) -> None:
        is_saved_template = self.current_template_id is not None
        is_active = is_saved_template and self.current_template_id == self.active_id
        self.delete_btn.setEnabled(is_saved_template and len(self.templates) > 1)
        self.set_active_btn.setEnabled(is_saved_template and not is_active)
        self.set_active_btn.setText("当前激活模板" if is_active else "设为当前激活模板")

    def set_active_template(self) -> None:
        if self.current_template_id is None:
            QMessageBox.warning(self, "提示", "请先选择已保存的模板")
            return
        if self.template_manager.set_active(self.current_template_id):
            self.template_updated.emit()
            self.load_templates(select_id=self.current_template_id)

    def save_template(self) -> None:
        name = self.name_input.text().strip() or "未命名模板"
        content = self.content_input.toPlainText().strip()
        if not content:
            QMessageBox.warning(self, "提示", "模板内容不能为空")
            return

        if self.current_template_id is None:
            if not self.template_manager.add_template(name, content, activate=False):
                QMessageBox.critical(self, "失败", "新建模板失败")
                return
            saved_data = self.template_manager.load_all()
            saved_templates = saved_data.get("templates", [])
            if saved_templates:
                self.current_template_id = max(tpl.get("id", 0) for tpl in saved_templates)
        else:
            if not self.template_manager.update_template(self.current_template_id, name=name, content=content):
                QMessageBox.critical(self, "失败", "保存模板失败")
                return

        self.template_updated.emit()
        self.load_templates(select_id=self.current_template_id)
        QMessageBox.information(self, "成功", "模板已保存")

    def delete_template(self) -> None:
        if self.current_template_id is None:
            return
        if QMessageBox.question(self, "确认删除", "确定删除当前模板吗？") != QMessageBox.StandardButton.Yes:
            return
        if not self.template_manager.delete_template(self.current_template_id):
            QMessageBox.warning(self, "提示", "删除失败，至少需要保留一个模板")
            return
        self.current_template_id = None
        self.template_updated.emit()
        self.load_templates()


class TaskWorker(QThread):
    log_line = pyqtSignal(str)
    task_done = pyqtSignal(int, bool, str)

    def __init__(self, config: ConfigManager, mode: str, max_count: int, start_value: int, parent=None):
        super().__init__(parent)
        self.config = config
        self.mode = mode
        self.max_count = max_count
        self.start_value = start_value
        self._stop_requested = False
        self.browser: BrowserManager | None = None
        self.proposal_sender: ProposalSender | None = None

    def request_stop(self) -> None:
        self._stop_requested = True
        if self.proposal_sender is not None:
            self.proposal_sender.request_stop()

    def run(self) -> None:
        try:
            template_manager = TemplateManager(self.config)
            log_stream = QtLogStream(self.log_line.emit)
            console = Console(file=log_stream, force_terminal=False, color_system=None, width=120)

            self.browser = BrowserManager(console, self.config)
            self.proposal_sender = ProposalSender(self.browser, template_manager, console, self.config)
            if self._stop_requested:
                self.proposal_sender.request_stop()

            if not self.browser.is_connected() and not self.browser.init():
                raise RuntimeError("无法连接浏览器，请确认 Chrome/Edge 已打开并已登录 Impact")

            template = template_manager.get_active_template()
            if self.mode == "list":
                result = self.proposal_sender.send_proposals(
                    self.max_count,
                    template,
                    start_index=self.start_value,
                    skip_ready_prompt=True,
                )
            else:
                result = self.proposal_sender.send_proposals_creator_search(
                    max_count=self.max_count,
                    start_row=self.start_value,
                    template_content=template,
                )

            log_stream.flush()
            self.task_done.emit(result.clicked_count, result.completed_all, "")
        except Exception as e:
            self.task_done.emit(0, False, str(e))


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Impact RPA - PyQt 桌面版")
        self.resize(1120, 760)
        self.setStyleSheet(self.get_stylesheet())

        self.config = ConfigManager()
        self.settings_service = SettingsService(self.config)
        self.template_manager = TemplateManager(self.config)
        self.browser_probe = BrowserManager(self._build_silent_console(), self.config)
        self.worker: TaskWorker | None = None

        self.init_ui()
        self.refresh_all()

        self.refresh_timer = QTimer(self)
        self.refresh_timer.timeout.connect(self.refresh_runtime_state)
        self.refresh_timer.start(5000)

    @staticmethod
    def _build_silent_console() -> Console:
        return Console(file=io.StringIO(), force_terminal=False, color_system=None, width=120)

    def init_ui(self) -> None:
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)
        main_layout.setContentsMargins(20, 20, 20, 20)
        main_layout.setSpacing(20)

        nav_layout = QHBoxLayout()
        title_label = QLabel("Impact RPA")
        title_label.setObjectName("appTitle")

        self.status_label = QLabel("浏览器状态检测中...")
        self.status_label.setObjectName("statusLabel")

        settings_btn = QPushButton("设置")
        settings_btn.clicked.connect(self.open_settings)

        nav_layout.addWidget(title_label)
        nav_layout.addStretch()
        nav_layout.addWidget(self.status_label)
        nav_layout.addWidget(settings_btn)
        main_layout.addLayout(nav_layout)

        stats_layout = QHBoxLayout()
        self.stat_sent_label = QLabel("0")
        self.stat_sent_label.setObjectName("statValue")
        stats_layout.addWidget(self.create_stat_card("今日已发送", self.stat_sent_label, "Send"))

        self.stat_tpl_label = QLabel("-")
        self.stat_tpl_label.setObjectName("statValue")
        stats_layout.addWidget(self.create_stat_card("当前激活模板", self.stat_tpl_label, "Tpl"))

        self.stat_term_label = QLabel("-")
        self.stat_term_label.setObjectName("statValue")
        stats_layout.addWidget(self.create_stat_card("Template Term", self.stat_term_label, "Term"))
        main_layout.addLayout(stats_layout)

        content_splitter = QSplitter(Qt.Orientation.Horizontal)

        left_panel = QWidget()
        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(0, 0, 10, 0)

        task_group = QGroupBox("执行任务 (Send Proposals)")
        task_layout = QVBoxLayout(task_group)

        self.tab_widget = QTabWidget()

        list_tab = QWidget()
        list_layout = QFormLayout(list_tab)
        self.list_max_count_input = QLineEdit("10")
        self.list_start_idx_input = QLineEdit("1")
        list_layout.addRow("发送数量 (Max Count):", self.list_max_count_input)
        list_layout.addRow("起始序号 (Start Index):", self.list_start_idx_input)
        list_layout.addRow(QLabel("提示: 请确保浏览器已导航到 Impact 目标列表页。"))
        self.tab_widget.addTab(list_tab, "列表页批量发送")

        search_tab = QWidget()
        search_layout = QFormLayout(search_tab)
        self.search_max_count_input = QLineEdit("10")
        self.search_start_row_input = QLineEdit("1")
        search_layout.addRow("发送数量 (Max Count):", self.search_max_count_input)
        search_layout.addRow("起始行号 (Start Row):", self.search_start_row_input)
        search_layout.addRow(QLabel("提示: Creator Search 模式，请先在浏览器内完成筛选。"))
        self.tab_widget.addTab(search_tab, "Creator Search 表格发送")

        task_layout.addWidget(self.tab_widget)

        self.start_btn = QPushButton("开始执行")
        self.start_btn.setObjectName("primaryBtn")
        self.start_btn.setMinimumHeight(40)
        self.start_btn.clicked.connect(self.start_task)
        task_layout.addWidget(self.start_btn)

        left_layout.addWidget(task_group)

        tpl_group = QGroupBox("当前留言模板")
        tpl_layout = QVBoxLayout(tpl_group)

        header_layout = QHBoxLayout()
        manage_tpl_btn = QPushButton("管理所有模板")
        manage_tpl_btn.clicked.connect(self.open_template_manager)
        header_layout.addStretch()
        header_layout.addWidget(manage_tpl_btn)
        tpl_layout.addLayout(header_layout)

        self.tpl_preview = QTextEdit()
        self.tpl_preview.setReadOnly(True)
        self.tpl_preview.setObjectName("tplPreview")
        tpl_layout.addWidget(self.tpl_preview)

        left_layout.addWidget(tpl_group)

        right_panel = QWidget()
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(10, 0, 0, 0)

        console_group = QGroupBox("执行日志 (Console)")
        console_layout = QVBoxLayout(console_group)

        self.console_output = QTextEdit()
        self.console_output.setReadOnly(True)
        self.console_output.setObjectName("consoleOutput")
        console_layout.addWidget(self.console_output)

        self.stop_btn = QPushButton("强制停止")
        self.stop_btn.setObjectName("dangerBtn")
        self.stop_btn.setEnabled(False)
        self.stop_btn.clicked.connect(self.stop_task)
        console_layout.addWidget(self.stop_btn)

        right_layout.addWidget(console_group)

        content_splitter.addWidget(left_panel)
        content_splitter.addWidget(right_panel)
        content_splitter.setSizes([620, 420])
        main_layout.addWidget(content_splitter, 1)

    def create_stat_card(self, title: str, value_label: QLabel, icon: str) -> QFrame:
        card = QFrame()
        card.setObjectName("statCard")
        layout = QHBoxLayout(card)

        icon_label = QLabel(icon)
        icon_label.setFont(QFont("Segoe UI", 12, QFont.Weight.Bold))
        icon_label.setFixedWidth(48)
        icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        text_layout = QVBoxLayout()
        title_label = QLabel(title)
        title_label.setObjectName("statTitle")
        text_layout.addWidget(title_label)
        text_layout.addWidget(value_label)

        layout.addWidget(icon_label)
        layout.addLayout(text_layout)
        layout.addStretch()
        return card

    def refresh_all(self) -> None:
        self.refresh_templates()
        self.refresh_settings_inputs()
        self.refresh_runtime_state()
        self.log_message("系统启动，真实配置已加载", "info")

    def refresh_templates(self) -> None:
        active_tpl = self.template_manager.get_active_template_info()
        if active_tpl:
            self.stat_tpl_label.setText(active_tpl.get("name", "未命名"))
            self.tpl_preview.setPlainText(active_tpl.get("content", ""))
        else:
            self.stat_tpl_label.setText("未配置")
            self.tpl_preview.setPlainText("")

    def refresh_settings_inputs(self) -> None:
        settings = self.settings_service.get_snapshot()
        default_max = str(settings.get("max_proposals", 10))
        for widget in (self.list_max_count_input, self.search_max_count_input):
            if not widget.text().strip() or widget.text().strip() == "10":
                widget.setText(default_max)
        self.stat_term_label.setText(settings.get("template_term", "-"))
        self.stat_term_label.setToolTip(settings.get("template_term", "-"))

    def refresh_runtime_state(self) -> None:
        self.stat_sent_label.setText(str(count_today_sent(self.config)))
        self.update_browser_status(self.detect_browser_connected())
        self.refresh_templates()
        self.refresh_settings_inputs()

    def detect_browser_connected(self) -> bool:
        if self.worker and self.worker.browser and self.worker.browser.is_connected():
            return True

        if self.browser_probe.is_connected():
            return True

        if not has_browser_process():
            return False

        probe = BrowserManager(self._build_silent_console(), self.config)
        if probe.init() and probe.is_connected():
            self.browser_probe = probe
            return True

        return False

    def update_browser_status(self, connected: bool) -> None:
        if connected:
            self.status_label.setText("浏览器已连接")
            self.status_label.setStyleSheet(
                "color: #15803d; background-color: #f0fdf4; border: 1px solid #bbf7d0; "
                "border-radius: 12px; padding: 4px 10px; font-weight: bold;"
            )
        else:
            self.status_label.setText("浏览器未连接")
            self.status_label.setStyleSheet(
                "color: #b91c1c; background-color: #fef2f2; border: 1px solid #fecaca; "
                "border-radius: 12px; padding: 4px 10px; font-weight: bold;"
            )

    def open_settings(self) -> None:
        dialog = SettingsDialog(self.settings_service.get_snapshot(), self)
        if dialog.exec():
            try:
                snapshot = self.settings_service.get_snapshot()
                snapshot.update(dialog.get_settings())
                if not self.settings_service.save(snapshot):
                    raise RuntimeError("保存设置失败")
                self.refresh_all()
                QMessageBox.information(self, "成功", "设置已保存")
            except Exception as e:
                QMessageBox.warning(self, "提示", str(e))

    def open_template_manager(self) -> None:
        dialog = TemplateDialog(self.template_manager, self)
        dialog.template_updated.connect(self.refresh_all)
        dialog.exec()
        self.refresh_all()

    def log_message(self, message: str, level: str = "info") -> None:
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        color_map = {
            "info": "#cbd5e1",
            "success": "#4ade80",
            "warn": "#facc15",
            "error": "#f87171",
            "highlight": "#38bdf8",
        }
        safe_message = html.escape(message)
        color = color_map.get(level, "#cbd5e1")
        formatted_msg = f'<span style="color: {color};">[{timestamp}] [{level.upper()}] {safe_message}</span><br>'
        self.console_output.moveCursor(QTextCursor.MoveOperation.End)
        self.console_output.insertHtml(formatted_msg)
        self.console_output.moveCursor(QTextCursor.MoveOperation.End)

    @staticmethod
    def parse_positive_int(value: str, field_name: str) -> int:
        try:
            parsed = int(value.strip())
        except ValueError as exc:
            raise ValueError(f"{field_name} 请输入有效整数") from exc
        if parsed < 1:
            raise ValueError(f"{field_name} 需大于等于 1")
        return parsed

    def start_task(self) -> None:
        if self.worker and self.worker.isRunning():
            return

        try:
            if self.tab_widget.currentIndex() == 0:
                mode = "list"
                max_count = self.parse_positive_int(self.list_max_count_input.text(), "发送数量")
                start_value = self.parse_positive_int(self.list_start_idx_input.text(), "起始序号")
                self.log_message(
                    f"开始发送 Send Proposal，模式: 列表页，目标数量: {max_count}，起始序号: {start_value}",
                    "highlight",
                )
            else:
                mode = "search"
                max_count = self.parse_positive_int(self.search_max_count_input.text(), "发送数量")
                start_value = self.parse_positive_int(self.search_start_row_input.text(), "起始行号")
                self.log_message(
                    f"开始发送 Send Proposal，模式: Creator Search，目标数量: {max_count}，起始行号: {start_value}",
                    "highlight",
                )
        except ValueError as e:
            QMessageBox.warning(self, "输入错误", str(e))
            return

        self.worker = TaskWorker(self.config, mode, max_count, start_value, self)
        self.worker.log_line.connect(self.handle_worker_log)
        self.worker.task_done.connect(self.handle_task_done)
        self.worker.start()

        self.start_btn.setEnabled(False)
        self.start_btn.setText("执行中...")
        self.stop_btn.setEnabled(True)
        self.stop_btn.setText("强制停止")

    def handle_worker_log(self, message: str) -> None:
        self.log_message(message, infer_log_level(message))

    def stop_task(self) -> None:
        if not self.worker or not self.worker.isRunning():
            return
        self.worker.request_stop()
        self.stop_btn.setEnabled(False)
        self.stop_btn.setText("停止请求中...")
        self.log_message("已发送停止请求，将在当前步骤完成后停止", "warn")

    def handle_task_done(self, clicked_count: int, completed_all: bool, error_message: str) -> None:
        if self.worker and self.worker.browser and self.worker.browser.is_connected():
            self.browser_probe = self.worker.browser

        self.start_btn.setEnabled(True)
        self.start_btn.setText("开始执行")
        self.stop_btn.setEnabled(False)
        self.stop_btn.setText("强制停止")

        if error_message:
            self.log_message(f"任务执行失败: {error_message}", "error")
        elif completed_all:
            self.log_message(f"任务完成，共发送 {clicked_count} 个 Proposal", "success")
        else:
            self.log_message(f"任务结束，当前批次共发送 {clicked_count} 个 Proposal", "warn")

        self.refresh_runtime_state()
        self.worker = None

    def get_stylesheet(self) -> str:
        return """
        QMainWindow {
            background-color: #f8fafc;
            font-family: "Segoe UI", "Microsoft YaHei", sans-serif;
        }
        QLabel#appTitle {
            font-size: 20px;
            font-weight: bold;
            color: #0f172a;
        }
        QLabel#statusLabel {
            border-radius: 12px;
            padding: 4px 10px;
            font-weight: bold;
        }
        QFrame#statCard {
            background-color: white;
            border: 1px solid #e2e8f0;
            border-radius: 8px;
            padding: 10px;
        }
        QLabel#statTitle {
            color: #64748b;
            font-size: 12px;
            font-weight: bold;
        }
        QLabel#statValue {
            color: #1e293b;
            font-size: 18px;
            font-weight: bold;
        }
        QGroupBox {
            background-color: white;
            border: 1px solid #e2e8f0;
            border-radius: 8px;
            margin-top: 20px;
            font-weight: bold;
            color: #1e293b;
        }
        QGroupBox::title {
            subcontrol-origin: margin;
            left: 15px;
            padding: 0 5px;
        }
        QPushButton {
            background-color: #f1f5f9;
            color: #475569;
            border: 1px solid #cbd5e1;
            border-radius: 6px;
            padding: 6px 12px;
            font-weight: bold;
        }
        QPushButton:hover {
            background-color: #e2e8f0;
        }
        QPushButton#primaryBtn {
            background-color: #0ea5e9;
            color: white;
            border: none;
        }
        QPushButton#primaryBtn:hover {
            background-color: #0284c7;
        }
        QPushButton#primaryBtn:disabled {
            background-color: #94a3b8;
        }
        QPushButton#dangerBtn {
            background-color: transparent;
            color: #ef4444;
            border: 1px solid #ef4444;
        }
        QPushButton#dangerBtn:hover {
            background-color: #fef2f2;
        }
        QPushButton#dangerBtn:disabled {
            color: #94a3b8;
            border: 1px solid #cbd5e1;
        }
        QTextEdit#tplPreview {
            background-color: #f8fafc;
            border: 1px solid #e2e8f0;
            border-radius: 6px;
            color: #334155;
            font-family: Consolas, monospace;
        }
        QTextEdit#consoleOutput {
            background-color: #0f172a;
            color: #cbd5e1;
            font-family: Consolas, monospace;
            border-radius: 6px;
            padding: 5px;
        }
        QTabWidget::pane {
            border: 1px solid #e2e8f0;
            border-radius: 4px;
            background: white;
        }
        QTabBar::tab {
            background: #f1f5f9;
            color: #64748b;
            padding: 8px 16px;
            border: 1px solid #e2e8f0;
            border-bottom: none;
            border-top-left-radius: 4px;
            border-top-right-radius: 4px;
        }
        QTabBar::tab:selected {
            background: white;
            color: #0f172a;
            font-weight: bold;
        }
        QLineEdit, QTextEdit {
            border: 1px solid #cbd5e1;
            border-radius: 4px;
            padding: 4px;
        }
        """


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())
