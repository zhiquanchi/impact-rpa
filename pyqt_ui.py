import html
import io
import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import IO, cast

from loguru import logger
from loguru._logger import Logger as LoguruLogger
from pydantic import BaseModel, Field, ValidationError, field_validator
from PyQt6.QtCore import QEvent, QObject, Qt, QThread, QTimer, pyqtSignal
from PyQt6.QtGui import QFont, QTextCursor
from PyQt6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
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
    QProgressBar,
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
from domain.selectors import MODAL_IFRAME_SELECTOR
from infra.browser_manager import BrowserManager


def count_today_sent(config: ConfigManager) -> int:
    today_str = datetime.now().strftime("%Y-%m-%d")
    log_dir = Path(config.log_dir)
    log_file = log_dir / f"impact_rpa_{today_str}.log"
    success_markers = (
        "已点击 Send Proposal 按钮",
        "发送成功: row=",
    )
    count = 0

    try:
        if log_file.exists():
            with log_file.open("r", encoding="utf-8") as f:
                for line in f:
                    if any(marker in line for marker in success_markers):
                        count += 1
    except Exception:
        pass

    if count > 0:
        return count

    try:
        for filepath in log_dir.iterdir():
            if not filepath.name.startswith(
                "creator_search_sent_"
            ) or not filepath.name.endswith(".json"):
                continue
            with filepath.open("r", encoding="utf-8") as f:
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
    if any(
        token in lowered for token in ("失败", "异常", "错误", "[err]", "traceback")
    ):
        return "error"
    if any(
        token in lowered
        for token in ("警告", "超时", "跳过", "停止请求", "[skip]", "warn")
    ):
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


class QtLogStream(io.TextIOBase):
    def __init__(self, emit_line):
        super().__init__()
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


class SettingsFormModel(BaseModel):
    max_proposals: int = Field(ge=1)
    scroll_delay: float = Field(gt=0)
    click_delay: float = Field(ge=0)
    modal_wait: float = Field(gt=0)
    dry_run: bool = False
    input_partner_groups_tag: bool = True

    @field_validator(
        "max_proposals", "scroll_delay", "click_delay", "modal_wait", mode="before"
    )
    @classmethod
    def _strip_numeric_inputs(cls, value):
        if isinstance(value, str):
            return value.strip()
        return value


class PositiveIntInputModel(BaseModel):
    value: int = Field(ge=1)

    @field_validator("value", mode="before")
    @classmethod
    def _strip_input(cls, value):
        if isinstance(value, str):
            return value.strip()
        return value


class PositiveFloatInputModel(BaseModel):
    value: float = Field(gt=0)

    @field_validator("value", mode="before")
    @classmethod
    def _strip_input(cls, value):
        if isinstance(value, str):
            return value.strip()
        return value


class NonNegativeFloatInputModel(BaseModel):
    value: float = Field(ge=0)

    @field_validator("value", mode="before")
    @classmethod
    def _strip_input(cls, value):
        if isinstance(value, str):
            return value.strip()
        return value


def format_validation_error(exc: ValidationError, field_labels: dict[str, str]) -> str:
    messages: list[str] = []
    for error in exc.errors():
        field = str(error.get("loc", ("",))[0])
        label = field_labels.get(field, field)
        error_type = error.get("type", "")
        ctx = error.get("ctx", {}) or {}

        if error_type.endswith("_parsing"):
            message = f"{label} 请输入有效{'整数' if 'int' in error_type else '数字'}"
        elif error_type == "greater_than_equal":
            message = f"{label} 需大于等于 {ctx.get('ge')}"
        elif error_type == "greater_than":
            message = f"{label} 需大于 {ctx.get('gt')}"
        else:
            message = f"{label} 输入无效"
        messages.append(message)

    return "\n".join(messages) if messages else "输入无效"


def validate_positive_int(value: str, field_name: str) -> int:
    try:
        return PositiveIntInputModel.model_validate({"value": value}).value
    except ValidationError as exc:
        raise ValueError(format_validation_error(exc, {"value": field_name})) from exc


def validate_positive_float(
    value: str, field_name: str, allow_zero: bool = False
) -> float:
    model = NonNegativeFloatInputModel if allow_zero else PositiveFloatInputModel
    try:
        return model.model_validate({"value": value}).value
    except ValidationError as exc:
        raise ValueError(format_validation_error(exc, {"value": field_name})) from exc


class TemplateTermFetchWorker(QThread):
    """后台获取 Template Term 选项，避免阻塞设置弹窗。"""

    fetch_done = pyqtSignal(list, str)

    def __init__(self, browser: BrowserManager, parent=None):
        super().__init__(parent)
        self.browser = browser

    def run(self) -> None:
        try:
            from domain.template_term_fetcher import TemplateTermOptionsFetcher

            options = TemplateTermOptionsFetcher(self.browser).fetch()
            self.fetch_done.emit(options, "")
        except Exception as exc:
            self.fetch_done.emit([], str(exc))


class SettingsDialog(QDialog):
    def __init__(self, snapshot: dict, browser=None, parent=None):
        super().__init__(parent)
        self.browser = browser
        self._term_fetch_worker: TemplateTermFetchWorker | None = None
        self.setWindowTitle("系统设置")
        self.setFixedSize(420, 400)

        layout = QVBoxLayout(self)
        form_layout = QFormLayout()

        self.max_proposals_input = QLineEdit(str(snapshot.get("max_proposals", 10)))
        self.scroll_delay_input = QLineEdit(str(snapshot.get("scroll_delay", 1.0)))
        self.click_delay_input = QLineEdit(str(snapshot.get("click_delay", 0.5)))
        self.modal_wait_input = QLineEdit(str(snapshot.get("modal_wait", 20.0)))
        self.dry_run_check = QCheckBox("启用 Dry Run（只跑流程，不提交）")
        self.dry_run_check.setChecked(bool(snapshot.get("dry_run", False)))
        self.partner_groups_check = QCheckBox(
            "在 Proposal 弹窗内输入 Partner Groups 标签"
        )
        self.partner_groups_check.setChecked(
            bool(snapshot.get("input_partner_groups_tag", True))
        )

        # Template Term 可编辑下拉框 + 获取按钮
        term_layout = QHBoxLayout()
        self.term_combo = QComboBox()
        self.term_combo.setEditable(True)
        current_term = snapshot.get("template_term", "")
        # 从缓存文件加载历史选项
        cached_terms: list[str] = self._load_cached_terms()
        if cached_terms:
            for opt in cached_terms:
                self.term_combo.addItem(opt)
            if current_term:
                idx = self.term_combo.findText(current_term)
                if idx >= 0:
                    self.term_combo.setCurrentIndex(idx)
                else:
                    self.term_combo.setCurrentText(current_term)
            else:
                self.term_combo.setCurrentIndex(0)
        else:
            if current_term:
                self.term_combo.addItem(current_term)
                self.term_combo.setCurrentText(current_term)
        # 无配置值且无缓存时禁用下拉框
        if not current_term and not cached_terms:
            self.term_combo.setEnabled(False)

        self.fetch_term_btn = QPushButton("获取选项")
        self.fetch_term_btn.setToolTip("深度分析并获取 Template Term 的所有选项")
        self.fetch_term_btn.clicked.connect(self._fetch_term_options)
        term_layout.addWidget(self.term_combo, 1)
        term_layout.addWidget(self.fetch_term_btn)

        form_layout.addRow("默认发送数量:", self.max_proposals_input)
        form_layout.addRow("滚动延迟 (秒):", self.scroll_delay_input)
        form_layout.addRow("点击延迟 (秒):", self.click_delay_input)
        form_layout.addRow("弹窗等待时间 (秒):", self.modal_wait_input)
        form_layout.addRow("Template Term:", term_layout)
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

    def _fetch_term_options(self) -> None:
        """从 Template Term 管理页网络响应获取下拉选项"""
        if not self.browser or not self.browser.is_connected():
            QMessageBox.warning(self, "浏览器未连接", "请先连接浏览器后再获取选项。")
            return

        reply = QMessageBox.question(
            self,
            "获取 Template Term 选项",
            "会花费一些时间，请耐心等待。是否继续？",
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        self.fetch_term_btn.setEnabled(False)
        self.fetch_term_btn.setText("获取中...")

        # 模态加载对话框
        self._fetch_progress_dialog = QDialog(self)
        self._fetch_progress_dialog.setWindowTitle("获取中")
        self._fetch_progress_dialog.setModal(True)
        self._fetch_progress_dialog.setFixedSize(320, 100)
        self._fetch_progress_dialog.setWindowFlags(
            self._fetch_progress_dialog.windowFlags()
            & ~Qt.WindowType.WindowCloseButtonHint
        )
        progress_layout = QVBoxLayout(self._fetch_progress_dialog)
        progress_layout.addWidget(
            QLabel("正在深度分析并获取 Template Term 的所有选项...")
        )
        progress_bar = QProgressBar()
        progress_bar.setMinimum(0)
        progress_bar.setMaximum(0)  # 不确定进度模式
        progress_bar.setTextVisible(False)
        progress_bar.setFixedHeight(20)
        progress_layout.addWidget(progress_bar)

        self._fetch_progress_dialog.show()

        self._term_fetch_worker = TemplateTermFetchWorker(self.browser, self)
        self._term_fetch_worker.fetch_done.connect(self._on_term_options_fetched)
        self._term_fetch_worker.start()

    def _on_term_options_fetched(self, options: list[str], error: str) -> None:
        # 关闭模态加载对话框
        if hasattr(self, "_fetch_progress_dialog") and self._fetch_progress_dialog:
            self._fetch_progress_dialog.close()
            self._fetch_progress_dialog = None

        self.fetch_term_btn.setEnabled(True)
        self.fetch_term_btn.setText("获取选项")
        self._term_fetch_worker = None

        if error:
            QMessageBox.warning(self, "获取失败", f"获取选项时发生错误：{error}")
            return
        if not options:
            QMessageBox.warning(
                self,
                "获取失败",
                "未能从管理页网络响应获取到 Template Term 选项。\n"
                "请确认浏览器已登录 Impact，并重试一次。",
            )
            return

        # 保存到缓存文件
        self._save_cached_terms(options)

        current_text = self.term_combo.currentText()
        self.term_combo.setEnabled(True)
        self.term_combo.clear()
        # 保留空选项
        for opt in options:
            self.term_combo.addItem(opt)

        if current_text:
            idx = self.term_combo.findText(current_text)
            if idx >= 0:
                self.term_combo.setCurrentIndex(idx)
            else:
                self.term_combo.setCurrentText(current_text)
        else:
            self.term_combo.setCurrentIndex(0)

        QMessageBox.information(
            self,
            "获取成功",
            f"已从管理页网络响应获取 {len(options)} 个选项并填充到下拉框。",
        )

    def _get_terms_file_path(self) -> Path:
        """获取 Template Terms 缓存文件路径"""
        config = ConfigManager()
        return Path(config.template_terms_file)

    def _load_cached_terms(self) -> list[str]:
        """从缓存文件加载 Template Term 选项列表"""
        try:
            path = self._get_terms_file_path()
            if path.exists():
                data = json.loads(path.read_text(encoding="utf-8"))
                return data.get("terms", [])
        except Exception:
            pass
        return []

    def _save_cached_terms(self, terms: list[str]) -> None:
        """将 Template Term 选项列表保存到缓存文件"""
        try:
            path = self._get_terms_file_path()
            path.write_text(
                json.dumps({"terms": terms}, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
        except Exception:
            pass

    def get_settings(self) -> dict:
        try:
            settings = SettingsFormModel.model_validate(
                {
                    "max_proposals": self.max_proposals_input.text(),
                    "scroll_delay": self.scroll_delay_input.text(),
                    "click_delay": self.click_delay_input.text(),
                    "modal_wait": self.modal_wait_input.text(),
                    "dry_run": self.dry_run_check.isChecked(),
                    "input_partner_groups_tag": self.partner_groups_check.isChecked(),
                }
            )
        except ValidationError as exc:
            raise ValueError(
                format_validation_error(
                    exc,
                    {
                        "max_proposals": "默认发送数量",
                        "scroll_delay": "滚动延迟",
                        "click_delay": "点击延迟",
                        "modal_wait": "弹窗等待时间",
                    },
                )
            ) from exc

        result = settings.model_dump()
        result["template_term"] = self.term_combo.currentText()
        return result

    @staticmethod
    def _parse_positive_int(value: str, field_name: str) -> int:
        return validate_positive_int(value, field_name)

    @staticmethod
    def _parse_positive_float(
        value: str, field_name: str, allow_zero: bool = False
    ) -> float:
        return validate_positive_float(value, field_name, allow_zero=allow_zero)


class ConfirmDialog(QDialog):
    """通用确认对话框"""

    def __init__(self, title: str, message: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setMinimumWidth(400)
        self.setModal(True)

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(message))

        btn_layout = QHBoxLayout()
        btn_layout.addStretch()

        self.cancel_btn = QPushButton("取消")
        self.cancel_btn.clicked.connect(self.reject)
        self.confirm_btn = QPushButton("确认")
        self.confirm_btn.setObjectName("primaryBtn")
        self.confirm_btn.clicked.connect(self.accept)

        btn_layout.addWidget(self.cancel_btn)
        btn_layout.addWidget(self.confirm_btn)
        layout.addLayout(btn_layout)

        self.setStyleSheet("""
            QDialog { background-color: white; }
            QLabel { font-size: 14px; color: #1e293b; padding: 10px; }
        """)


class ProposalConfirmDialog(QDialog):
    """Proposal 发送确认对话框，包含模板预览和参数确认"""

    confirmed = False
    mode: str
    max_count: int
    start_value: int
    selected_term: str | None

    def __init__(
        self,
        mode: str,
        max_count: int,
        start_value: int,
        template_name: str,
        template_content: str,
        current_term: str,
        term_options: list[str] | None = None,
        parent=None,
    ):
        super().__init__(parent)
        self.mode = mode
        self.max_count = max_count
        self.start_value = start_value
        self.selected_term = None

        mode_display = "列表页批量发送" if mode == "list" else "Creator Search 表格发送"
        start_label = "起始序号" if mode == "list" else "起始行号"

        self.setWindowTitle("确认发送 Proposal")
        self.setMinimumWidth(500)
        self.setMinimumHeight(400)
        self.setModal(True)

        layout = QVBoxLayout(self)

        # 参数信息
        info_group = QGroupBox("发送参数")
        info_layout = QFormLayout(info_group)
        info_layout.addRow("执行模式:", QLabel(mode_display))
        info_layout.addRow("发送数量:", QLabel(str(max_count)))
        info_layout.addRow(f"{start_label}:", QLabel(str(start_value)))
        layout.addWidget(info_group)

        # 模板预览
        tpl_group = QGroupBox("当前激活模板")
        tpl_layout = QVBoxLayout(tpl_group)

        tpl_name_label = QLabel(f"模板名称: {template_name or '未命名'}")
        tpl_name_label.setStyleSheet("font-weight: bold; color: #0f172a;")
        tpl_layout.addWidget(tpl_name_label)

        self.tpl_preview = QTextEdit()
        self.tpl_preview.setReadOnly(True)
        self.tpl_preview.setMaximumHeight(120)
        self.tpl_preview.setPlainText(template_content or "(空模板)")
        self.tpl_preview.setStyleSheet("""
            background-color: #f8fafc;
            border: 1px solid #e2e8f0;
            border-radius: 4px;
            color: #334155;
            font-family: Consolas, monospace;
        """)
        tpl_layout.addWidget(self.tpl_preview)

        layout.addWidget(tpl_group)

        # Template Term 选择（如果有选项）
        self.term_combo: QComboBox | None = None
        if term_options:
            term_group = QGroupBox("Template Term 设置")
            term_layout = QVBoxLayout(term_group)

            term_desc = QLabel("请选择 Template Term（可选）：")
            term_desc.setStyleSheet("color: #64748b;")
            term_layout.addWidget(term_desc)

            self.term_combo = QComboBox()
            self.term_combo.addItem("使用当前设置", userData=None)
            for opt in term_options:
                self.term_combo.addItem(opt, userData=opt)
            # 尝试选中当前值
            for i in range(self.term_combo.count()):
                if self.term_combo.itemData(i) == current_term:
                    self.term_combo.setCurrentIndex(i)
                    break
            term_layout.addWidget(self.term_combo)
            layout.addWidget(term_group)

        elif current_term:
            term_label = QLabel(f"当前 Template Term: {current_term}")
            term_label.setStyleSheet("color: #64748b; padding: 5px 0;")
            layout.addWidget(term_label)

        layout.addStretch()

        # 按钮区域
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()

        self.cancel_btn = QPushButton("取消")
        self.cancel_btn.setStyleSheet("""
            QPushButton {
                background-color: #f1f5f9;
                color: #475569;
                border: 1px solid #cbd5e1;
                border-radius: 6px;
                padding: 8px 20px;
                font-weight: bold;
            }
            QPushButton:hover { background-color: #e2e8f0; }
        """)
        self.cancel_btn.clicked.connect(self.reject)

        self.confirm_btn = QPushButton("确认开始发送")
        self.confirm_btn.setObjectName("primaryBtn")
        self.confirm_btn.setMinimumHeight(40)
        self.confirm_btn.clicked.connect(self._on_confirm)

        btn_layout.addWidget(self.cancel_btn)
        btn_layout.addWidget(self.confirm_btn)
        layout.addLayout(btn_layout)

        self.setStyleSheet("""
            QDialog { background-color: #f8fafc; }
            QGroupBox {
                background-color: white;
                border: 1px solid #e2e8f0;
                border-radius: 8px;
                margin-top: 10px;
                font-weight: bold;
                color: #1e293b;
            }
            QGroupBox::title { subcontrol-origin: margin; left: 10px; padding: 0 5px; }
            QLabel { color: #334155; }
            QFormLayout QLabel { color: #64748b; }
            QComboBox {
                border: 1px solid #cbd5e1;
                border-radius: 4px;
                padding: 6px;
                background-color: white;
            }
        """)

    def _on_confirm(self) -> None:
        """确认按钮点击处理"""
        if self.term_combo and self.term_combo.currentData() is not None:
            self.selected_term = self.term_combo.currentData()
        self.accept()

    def get_selected_term(self) -> str | None:
        """获取用户选择的 Template Term"""
        return self.selected_term


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
            target_id = (
                self.current_template_id
                or self.active_id
                or self.templates[0].get("id")
            )

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
                self.current_template_id = max(
                    tpl.get("id", 0) for tpl in saved_templates
                )
        else:
            if not self.template_manager.update_template(
                self.current_template_id, name=name, content=content
            ):
                QMessageBox.critical(self, "失败", "保存模板失败")
                return

        self.template_updated.emit()
        self.load_templates(select_id=self.current_template_id)
        QMessageBox.information(self, "成功", "模板已保存")

    def delete_template(self) -> None:
        if self.current_template_id is None:
            return
        if (
            QMessageBox.question(self, "确认删除", "确定删除当前模板吗？")
            != QMessageBox.StandardButton.Yes
        ):
            return
        if not self.template_manager.delete_template(self.current_template_id):
            QMessageBox.warning(self, "提示", "删除失败，至少需要保留一个模板")
            return
        self.current_template_id = None
        self.template_updated.emit()
        self.load_templates()


class BrowserProbeWorker(QThread):
    """后台浏览器连接检测线程"""

    probe_result = pyqtSignal(bool)

    def __init__(self, browser: BrowserManager, timeout_ms: int = 200, parent=None):
        super().__init__(parent)
        self.browser = browser
        self.timeout_ms = timeout_ms

    def run(self) -> None:
        connected = False
        try:
            import threading

            result = {"connected": False}

            def check():
                try:
                    if self.browser and self.browser.is_connected():
                        result["connected"] = True
                except Exception:
                    pass

            t = threading.Thread(target=check)
            t.daemon = True
            t.start()
            t.join(timeout=self.timeout_ms / 1000.0)
            connected = result["connected"]
        except Exception:
            connected = False
        self.probe_result.emit(connected)


class TaskWorker(QThread):
    log_line = pyqtSignal(str)
    task_done = pyqtSignal(int, bool, str)

    def __init__(
        self,
        browser: BrowserManager,
        config: ConfigManager,
        mode: str,
        max_count: int,
        start_value: int,
        parent=None,
    ):
        super().__init__(parent)
        self.browser = browser
        self.config = config
        self.mode = mode
        self.max_count = max_count
        self.start_value = start_value
        self._stop_requested = False
        self.proposal_sender: ProposalSender | None = None

    def request_stop(self) -> None:
        self._stop_requested = True
        if self.proposal_sender is not None:
            self.proposal_sender.request_stop()

    def run(self) -> None:
        try:
            template_manager = TemplateManager(self.config)
            log_stream = QtLogStream(self.log_line.emit)
            console = Console(
                file=cast(IO[str], log_stream),
                force_terminal=False,
                color_system=None,
                width=120,
            )

            self.proposal_sender = ProposalSender(
                self.browser, template_manager, console, self.config
            )
            if self._stop_requested:
                self.proposal_sender.request_stop()

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
        # 限制最小宽度
        self.setMinimumWidth(900)
        # 限制最小高度
        self.setMinimumHeight(600)

        self.setStyleSheet(self.get_stylesheet())

        self.config = ConfigManager()
        self.settings_service = SettingsService(self.config)
        self.template_manager = TemplateManager(self.config)
        self.browser: BrowserManager | None = None
        self.worker: TaskWorker | None = None
        self.probe_worker: BrowserProbeWorker | None = None
        self._cached_browser_connected = False
        self._lock_widgets: list = []
        self._highlight_animation: QTimer | None = None

        self.init_ui()
        self._install_event_filters()
        self.refresh_all()

        self.refresh_timer = QTimer(self)
        self.refresh_timer.timeout.connect(self.refresh_runtime_state)
        self.refresh_timer.start(10000)

    def eventFilter(self, obj: QObject, event: QEvent) -> bool:  # ty:ignore[invalid-method-override]
        """拦截被锁定控件的点击事件"""
        if obj in self._lock_widgets and event.type() == QEvent.Type.MouseButtonPress:
            widget = cast(QWidget, obj)
            # 只有在控件被禁用时才显示提示（浏览器未连接时）
            if not widget.isEnabled():
                self._show_connect_prompt(widget)
                return True
        return super().eventFilter(obj, event)

    def _install_event_filters(self) -> None:
        """为被锁定的控件安装事件过滤器"""
        self._lock_widgets = [
            self.tab_widget,
            self.start_btn,
            self.list_max_count_input,
            self.list_start_idx_input,
            self.search_max_count_input,
            self.search_start_row_input,
        ]
        for widget in self._lock_widgets:
            widget.installEventFilter(self)

    def _show_connect_prompt(self, source_widget) -> None:
        """显示连接提示并引导用户到连接按钮"""
        # 显示提示框
        msg_box = QMessageBox(self)
        msg_box.setIcon(QMessageBox.Icon.Information)
        msg_box.setWindowTitle("界面已锁定")
        msg_box.setText("请先点击右上角的「连接浏览器」按钮")
        msg_box.setStandardButtons(QMessageBox.StandardButton.Ok)
        msg_box.exec()

        # 开始高亮动效引导
        self._start_highlight_animation()

    def _start_highlight_animation(self) -> None:
        """启动高亮闪烁动效引导用户视线"""
        if self._highlight_animation is not None:
            self._highlight_animation.stop()

        self._highlight_animation = QTimer(self)
        highlight_state = {"on": False}

        # 保存原始样式
        original_style = self.connect_btn.styleSheet()

        def animate():
            highlight_state["on"] = not highlight_state["on"]
            if highlight_state["on"]:
                self.connect_btn.setStyleSheet(
                    original_style
                    + """
                    QPushButton {
                        background-color: #E74C3C;
                        color: #FFFFFF;
                        border: 2px solid #C0392B;
                        border-radius: 12px;
                        padding: 6px 16px;
                        font-weight: bold;
                    }
                """
                )
                # 确保按钮在视口内
                rect = self.connect_btn.geometry()
                if rect.top() < 0:
                    self.scroll_to_widget(self.connect_btn)
            else:
                self.connect_btn.setStyleSheet(original_style)

        self._highlight_animation.timeout.connect(animate)
        self._highlight_animation.start(400)  # 每400ms切换状态

        # 3秒后自动停止高亮
        QTimer.singleShot(3000, self._stop_highlight_animation)

    def _stop_highlight_animation(self) -> None:
        """停止高亮动效"""
        if self._highlight_animation is not None:
            self._highlight_animation.stop()
            self._highlight_animation = None
        # 恢复原始样式
        self.connect_btn.setStyleSheet("""
            QPushButton {
                background-color: #34495E;
                color: #ECF0F1;
                border: none;
                border-radius: 12px;
                padding: 6px 16px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #2C3E50;
            }
            QPushButton:disabled {
                background-color: #1ABC9C;
                color: #ECF0F1;
            }
        """)

    def scroll_to_widget(self, widget: QWidget) -> None:
        """滚动到指定控件位置"""
        # 确保按钮在视口内
        self.ensurePolished()
        self.activateWindow()
        self.raise_()

    @staticmethod
    def _build_silent_console() -> Console:
        return Console(
            file=io.StringIO(), force_terminal=False, color_system=None, width=120
        )

    def init_ui(self) -> None:
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)
        main_layout.setContentsMargins(20, 20, 20, 20)
        main_layout.setSpacing(20)

        nav_layout = QHBoxLayout()
        title_label = QLabel("Impact RPA")
        title_label.setObjectName("appTitle")

        self.browser_connected = False
        self.connect_btn = QPushButton("连接浏览器")
        self.connect_btn.setObjectName("connectBtn")
        self.connect_btn.setStyleSheet("""
            QPushButton {
                background-color: #34495E;
                color: #ECF0F1;
                border: none;
                border-radius: 12px;
                padding: 6px 16px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #2C3E50;
            }
            QPushButton:disabled {
                background-color: #1ABC9C;
                color: #ECF0F1;
            }
        """)
        self.connect_btn.clicked.connect(self._on_connect_browser_clicked)

        settings_btn = QPushButton("设置")
        settings_btn.clicked.connect(self.open_settings)

        nav_layout.addWidget(title_label)
        nav_layout.addStretch()
        nav_layout.addWidget(self.connect_btn)
        nav_layout.addWidget(settings_btn)
        main_layout.addLayout(nav_layout)

        stats_layout = QHBoxLayout()
        self.stat_sent_label = QLabel("0")
        self.stat_sent_label.setObjectName("statValue")
        stats_layout.addWidget(
            self.create_stat_card("今日已发送", self.stat_sent_label, "Send")
        )

        self.stat_tpl_label = QLabel("-")
        self.stat_tpl_label.setObjectName("statValue")
        stats_layout.addWidget(
            self.create_stat_card("当前激活模板", self.stat_tpl_label, "Tpl")
        )

        self.stat_term_label = QLabel("-")
        self.stat_term_label.setObjectName("statValue")
        stats_layout.addWidget(
            self.create_stat_card("Template Term", self.stat_term_label, "Term")
        )
        main_layout.addLayout(stats_layout)

        content_splitter = QSplitter(Qt.Orientation.Horizontal)

        left_panel = QWidget()
        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(0, 0, 10, 0)

        task_group = QGroupBox("执行任务 (Send Proposals)")
        task_layout = QVBoxLayout(task_group)

        self.tab_widget = QTabWidget()
        self.tab_widget.setStyleSheet("""
            QTabBar::tab {
                background-color: #34495E;
                color: #ECF0F1;
                padding: 8px 16px;
                border: 1px solid #2C3E50;
                border-bottom: none;
            }
            QTabBar::tab:selected {
                background-color: #ECF0F1;
                color: #34495E;
                font-weight: bold;
            }
            QTabBar::tab:!selected {
                background-color: #34495E;
            }
            QWidget#list_tab, QWidget#search_tab {
                background-color: #ECF0F1;
            }
        """)

        list_tab = QWidget()
        list_tab.setObjectName("list_tab")
        list_layout = QFormLayout(list_tab)
        self.list_max_count_input = QLineEdit("10")
        self.list_start_idx_input = QLineEdit("1")
        list_layout.addRow("发送数量 (Max Count):", self.list_max_count_input)
        list_layout.addRow("起始序号 (Start Index):", self.list_start_idx_input)
        list_layout.addRow(QLabel("提示: 请确保浏览器已导航到 Impact 目标列表页。"))
        self.tab_widget.addTab(list_tab, "列表页批量发送")

        search_tab = QWidget()
        search_tab.setObjectName("search_tab")
        search_layout = QFormLayout(search_tab)
        self.search_max_count_input = QLineEdit("10")
        self.search_start_row_input = QLineEdit("1")
        search_layout.addRow("发送数量 (Max Count):", self.search_max_count_input)
        search_layout.addRow("起始行号 (Start Row):", self.search_start_row_input)
        search_layout.addRow(
            QLabel("提示: Creator Search 模式，请先在浏览器内完成筛选。")
        )
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
        self._lock_interface()
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
        self.refresh_templates()
        self.refresh_settings_inputs()
        self._start_browser_probe()

    def _start_browser_probe(self) -> None:
        """启动后台浏览器连接检测（200ms 超时）"""
        if self.probe_worker and self.probe_worker.isRunning():
            return

        target_browser = (
            self.worker.browser
            if (self.worker and self.worker.browser)
            else self.browser
        )
        if not target_browser:
            self.update_browser_status(False)
            return

        self.probe_worker = BrowserProbeWorker(
            target_browser, timeout_ms=200, parent=self
        )
        self.probe_worker.probe_result.connect(self._on_browser_probe_result)
        self.probe_worker.start()

    def _on_browser_probe_result(self, connected: bool) -> None:
        """处理浏览器连接检测结果"""
        self._cached_browser_connected = connected
        self.update_browser_status(connected)

    def detect_browser_connected(self) -> bool:
        """返回缓存的浏览器连接状态"""
        return self._cached_browser_connected

    def _lock_interface(self) -> None:
        """锁定界面，禁用除连接按钮外的所有交互元素"""
        self.tab_widget.setEnabled(False)
        self.start_btn.setEnabled(False)
        self.list_max_count_input.setEnabled(False)
        self.list_start_idx_input.setEnabled(False)
        self.search_max_count_input.setEnabled(False)
        self.search_start_row_input.setEnabled(False)

    def _unlock_interface(self) -> None:
        """解锁界面，恢复所有交互元素"""
        self._stop_highlight_animation()
        self.tab_widget.setEnabled(True)
        self.start_btn.setEnabled(True)
        self.list_max_count_input.setEnabled(True)
        self.list_start_idx_input.setEnabled(True)
        self.search_max_count_input.setEnabled(True)
        self.search_start_row_input.setEnabled(True)

    def update_browser_status(self, connected: bool) -> None:
        self._cached_browser_connected = connected
        if connected:
            self.connect_btn.setText("浏览器已连接")
            self.connect_btn.setEnabled(False)
            self._unlock_interface()
        else:
            self.connect_btn.setText("连接浏览器")
            self.connect_btn.setEnabled(True)
            self._lock_interface()

    def _on_connect_browser_clicked(self) -> None:
        """手动点击连接浏览器按钮"""
        self.connect_btn.setText("连接中...")
        self.connect_btn.setEnabled(False)

        def do_connect():
            try:
                self.browser = BrowserManager(cast(LoguruLogger, logger), self.config)
                if self.browser.init() and self.browser.is_connected():
                    self.update_browser_status(True)
                    logger.info("浏览器连接成功")
                else:
                    self.update_browser_status(False)
                    QMessageBox.warning(
                        self,
                        "连接失败",
                        "无法连接浏览器，请确认 Chrome/Edge 已打开并已登录 Impact",
                    )
                    logger.warning("浏览器连接失败")
            except Exception as e:
                self.update_browser_status(False)
                QMessageBox.warning(self, "连接错误", f"连接浏览器时发生错误: {e}")
                logger.error(f"连接浏览器时发生错误: {e}")

        QTimer.singleShot(100, do_connect)

    def open_settings(self) -> None:
        dialog = SettingsDialog(
            self.settings_service.get_snapshot(), self.browser, self
        )
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
        return validate_positive_int(value, field_name)

    def _show_confirm_dialog(self) -> ProposalConfirmDialog | None:
        """显示确认对话框，返回对话框实例或 None（如果取消）"""
        try:
            if self.tab_widget.currentIndex() == 0:
                mode = "list"
                max_count = self.parse_positive_int(
                    self.list_max_count_input.text(), "发送数量"
                )
                start_value = self.parse_positive_int(
                    self.list_start_idx_input.text(), "起始序号"
                )
            else:
                mode = "search"
                max_count = self.parse_positive_int(
                    self.search_max_count_input.text(), "发送数量"
                )
                start_value = self.parse_positive_int(
                    self.search_start_row_input.text(), "起始行号"
                )
        except ValueError as e:
            QMessageBox.warning(self, "输入错误", str(e))
            return None

        if not self.browser or not self.browser.is_connected():
            QMessageBox.warning(
                self, "浏览器未连接", "请先点击「连接浏览器」按钮连接浏览器"
            )
            return None

        # 获取当前模板信息
        active_tpl = self.template_manager.get_active_template_info()
        template_name = active_tpl.get("name", "") if active_tpl else ""
        template_content = active_tpl.get("content", "") if active_tpl else ""

        # 获取当前 Template Term 设置
        settings = self.settings_service.get_snapshot()
        current_term = settings.get("template_term", "")

        # 获取 Template Term 选项（需要浏览器连接）
        term_options: list[str] = []
        if self.browser and self.browser.is_connected() and self.browser.tab:
            try:
                iframe = self.browser.find_element(MODAL_IFRAME_SELECTOR, timeout=3)
                if iframe:
                    from domain.template_term_utils import get_template_term_options

                    term_options = get_template_term_options(
                        iframe, tab=self.browser.tab
                    )
            except Exception:
                pass

        # 显示确认对话框
        dialog = ProposalConfirmDialog(
            mode=mode,
            max_count=max_count,
            start_value=start_value,
            template_name=template_name,
            template_content=template_content,
            current_term=current_term,
            term_options=term_options if term_options else None,
            parent=self,
        )

        return dialog

    def _ensure_template_term(self) -> bool:
        """确保 Template Term 已配置，未配置时弹出强制选择对话框"""
        settings = self.settings_service.get_snapshot()
        current_term = settings.get("template_term", "")
        if current_term:
            return True

        if not self.browser or not self.browser.is_connected():
            QMessageBox.warning(
                self,
                "Template Term 未配置",
                "当前 Template Term 为空，请先连接浏览器以获取选项列表。",
            )
            return False

        term_options: list[str] = []
        try:
            iframe = self.browser.find_element(MODAL_IFRAME_SELECTOR, timeout=3)
            if iframe:
                from domain.template_term_utils import get_template_term_options

                term_options = get_template_term_options(iframe, tab=self.browser.tab)
        except Exception:
            pass

        if not term_options:
            QMessageBox.warning(
                self,
                "无法获取 Template Term 选项",
                "未能从浏览器获取 Template Term 选项列表。\n"
                "请确保已打开 Send Proposal 弹窗，或在「设置」中手动填写。",
            )
            return False

        dialog = QDialog(self)
        dialog.setWindowTitle("配置 Template Term")
        dialog.setMinimumWidth(420)
        dialog.setModal(True)

        layout = QVBoxLayout(dialog)
        info = QLabel("Template Term 尚未配置，请在下方选择一个选项：")
        info.setWordWrap(True)
        info.setStyleSheet("color: #ef4444; font-weight: bold; padding: 5px;")
        layout.addWidget(info)

        combo = QComboBox()
        for opt in term_options:
            combo.addItem(opt)
        layout.addWidget(combo)

        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        confirm_btn = QPushButton("确认选择")
        confirm_btn.setObjectName("primaryBtn")
        confirm_btn.clicked.connect(dialog.accept)
        btn_layout.addWidget(confirm_btn)
        layout.addLayout(btn_layout)

        if dialog.exec() != QDialog.DialogCode.Accepted:
            return False

        selected = combo.currentText()
        settings["template_term"] = selected
        self.settings_service.save(settings)
        self.refresh_settings_inputs()
        self.log_message(f"已配置 Template Term: {selected}", "info")
        return True

    def start_task(self) -> None:
        if self.worker and self.worker.isRunning():
            return

        # 强制检查 Template Term
        if not self._ensure_template_term():
            self.log_message("Template Term 未配置，任务取消", "warn")
            return

        # 显示确认对话框
        dialog = self._show_confirm_dialog()
        if dialog is None:
            return

        if not dialog.exec():
            self.log_message("用户取消发送", "warn")
            return

        # 获取用户选择的参数
        mode = dialog.mode
        max_count = dialog.max_count
        start_value = dialog.start_value
        selected_term = dialog.get_selected_term()

        # 如果用户选择了新的 Template Term，更新设置
        if selected_term:
            settings = self.settings_service.get_snapshot()
            settings["template_term"] = selected_term
            self.settings_service.save(settings)
            self.log_message(f"已更新 Template Term 为: {selected_term}", "info")

        self.log_message(
            f"开始发送 Send Proposal，模式: {'列表页' if mode == 'list' else 'Creator Search'}，"
            f"目标数量: {max_count}，{'起始序号' if mode == 'list' else '起始行号'}: {start_value}",
            "highlight",
        )

        self.worker = TaskWorker(
            self.browser, self.config, mode, max_count, start_value, self
        )
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

    def handle_task_done(
        self, clicked_count: int, completed_all: bool, error_message: str
    ) -> None:
        if self.worker and self.worker.browser and self.worker.browser.is_connected():
            self.browser = self.worker.browser

        self.start_btn.setText("开始执行")
        self.stop_btn.setEnabled(False)
        self.stop_btn.setText("强制停止")

        if error_message:
            self.log_message(f"任务执行失败: {error_message}", "error")
        elif completed_all:
            self.log_message(f"任务完成，共发送 {clicked_count} 个 Proposal", "success")
        else:
            self.log_message(
                f"任务结束，当前批次共发送 {clicked_count} 个 Proposal", "warn"
            )

        self.update_browser_status(self.detect_browser_connected())
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
