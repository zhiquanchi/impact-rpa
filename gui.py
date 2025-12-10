"""
Impact RPA - PyQt GUI 版本
使用 PySide6 实现图形界面
"""

import sys
import os
import json
from datetime import datetime
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QSpinBox, QTextEdit, QTabWidget,
    QGroupBox, QListWidget, QListWidgetItem, QLineEdit,
    QMessageBox, QStatusBar, QProgressBar, QSplitter,
    QInputDialog, QComboBox
)
from PySide6.QtCore import Qt, QThread, Signal, QTimer
from PySide6.QtGui import QFont, QTextCursor

# 导入核心功能模块
from main import (
    init_browser, reconnect_browser,
    load_template, load_all_templates, save_all_templates,
    load_settings, save_settings, get_next_template_id,
    safe_find_elements, safe_find_element, safe_click,
    get_selected_tab_value, select_public_commission,
    logger, extract_send_proposal_buttons
)

# 配置文件路径
CONFIG_DIR = os.path.join(os.path.dirname(__file__), 'config')
TEMPLATES_FILE = os.path.join(CONFIG_DIR, 'templates.json')
SETTINGS_FILE = os.path.join(CONFIG_DIR, 'settings.json')


class WorkerThread(QThread):
    """后台工作线程，执行 Send Proposal 操作"""
    progress = Signal(int, int)  # 当前进度, 总数
    log_message = Signal(str)    # 日志消息
    finished_signal = Signal(int)  # 完成信号，参数为成功数量
    error_signal = Signal(str)   # 错误信号

    def __init__(self, max_count):
        super().__init__()
        self.max_count = max_count
        self.is_running = True

    def stop(self):
        self.is_running = False

    def run(self):
        """执行发送操作"""
        clicked_count = 0
        try:
            clicked_count = extract_send_proposal_buttons(self.max_count)
            self.finished_signal.emit(clicked_count)
        except Exception as e:
            self.error_signal.emit(str(e))


class MainWindow(QMainWindow):
    """主窗口"""

    def __init__(self):
        super().__init__()
        self.worker_thread = None
        self.init_ui()
        self.load_data()

    def init_ui(self):
        """初始化 UI"""
        self.setWindowTitle("Impact RPA - Send Proposal 自动化工具")
        self.setMinimumSize(900, 700)

        # 中央部件
        central_widget = QWidget()
        self.setCentralWidget(central_widget)

        # 主布局
        main_layout = QVBoxLayout(central_widget)

        # 创建标签页
        tab_widget = QTabWidget()
        main_layout.addWidget(tab_widget)

        # 标签页1: 发送控制
        send_tab = self.create_send_tab()
        tab_widget.addTab(send_tab, "🚀 发送控制")

        # 标签页2: 模板管理
        template_tab = self.create_template_tab()
        tab_widget.addTab(template_tab, "📄 模板管理")

        # 标签页3: 设置
        settings_tab = self.create_settings_tab()
        tab_widget.addTab(settings_tab, "⚙️ 设置")

        # 标签页4: 浏览器控制
        browser_tab = self.create_browser_tab()
        tab_widget.addTab(browser_tab, "🌐 浏览器")

        # 状态栏
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        self.status_bar.showMessage("就绪")

        # 进度条（添加到状态栏）
        self.progress_bar = QProgressBar()
        self.progress_bar.setMaximumWidth(200)
        self.progress_bar.setVisible(False)
        self.status_bar.addPermanentWidget(self.progress_bar)

    def create_send_tab(self):
        """创建发送控制标签页"""
        widget = QWidget()
        layout = QVBoxLayout(widget)

        # 控制区域
        control_group = QGroupBox("发送控制")
        control_layout = QHBoxLayout(control_group)

        # 发送数量
        control_layout.addWidget(QLabel("发送数量:"))
        self.count_spinbox = QSpinBox()
        self.count_spinbox.setRange(1, 1000)
        self.count_spinbox.setValue(10)
        control_layout.addWidget(self.count_spinbox)

        control_layout.addStretch()

        # 开始/停止按钮
        self.start_btn = QPushButton("▶️ 开始发送")
        self.start_btn.setMinimumWidth(120)
        self.start_btn.clicked.connect(self.on_start_clicked)
        control_layout.addWidget(self.start_btn)

        self.stop_btn = QPushButton("⏹️ 停止")
        self.stop_btn.setMinimumWidth(80)
        self.stop_btn.setEnabled(False)
        self.stop_btn.clicked.connect(self.on_stop_clicked)
        control_layout.addWidget(self.stop_btn)

        layout.addWidget(control_group)

        # 当前模板预览
        template_group = QGroupBox("当前模板预览")
        template_layout = QVBoxLayout(template_group)
        self.template_preview = QTextEdit()
        self.template_preview.setReadOnly(True)
        self.template_preview.setMaximumHeight(100)
        template_layout.addWidget(self.template_preview)
        layout.addWidget(template_group)

        # 日志区域
        log_group = QGroupBox("运行日志")
        log_layout = QVBoxLayout(log_group)
        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setFont(QFont("Consolas", 9))
        log_layout.addWidget(self.log_text)

        # 清空日志按钮
        clear_log_btn = QPushButton("清空日志")
        clear_log_btn.clicked.connect(lambda: self.log_text.clear())
        log_layout.addWidget(clear_log_btn)

        layout.addWidget(log_group)

        return widget

    def create_template_tab(self):
        """创建模板管理标签页"""
        widget = QWidget()
        layout = QHBoxLayout(widget)

        # 左侧：模板列表
        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)
        left_layout.setContentsMargins(0, 0, 0, 0)

        left_layout.addWidget(QLabel("模板列表:"))
        self.template_list = QListWidget()
        self.template_list.currentRowChanged.connect(self.on_template_selected)
        left_layout.addWidget(self.template_list)

        # 模板操作按钮
        btn_layout = QHBoxLayout()

        add_btn = QPushButton("➕ 添加")
        add_btn.clicked.connect(self.on_add_template)
        btn_layout.addWidget(add_btn)

        delete_btn = QPushButton("🗑️ 删除")
        delete_btn.clicked.connect(self.on_delete_template)
        btn_layout.addWidget(delete_btn)

        activate_btn = QPushButton("✅ 激活")
        activate_btn.clicked.connect(self.on_activate_template)
        btn_layout.addWidget(activate_btn)

        left_layout.addLayout(btn_layout)

        # 右侧：模板编辑
        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)
        right_layout.setContentsMargins(0, 0, 0, 0)

        # 模板名称
        name_layout = QHBoxLayout()
        name_layout.addWidget(QLabel("模板名称:"))
        self.template_name_edit = QLineEdit()
        name_layout.addWidget(self.template_name_edit)
        right_layout.addLayout(name_layout)

        # 模板内容
        right_layout.addWidget(QLabel("模板内容:"))
        self.template_content_edit = QTextEdit()
        right_layout.addWidget(self.template_content_edit)

        # 保存按钮
        save_btn = QPushButton("💾 保存修改")
        save_btn.clicked.connect(self.on_save_template)
        right_layout.addWidget(save_btn)

        # 添加到 splitter
        splitter = QSplitter(Qt.Horizontal)
        splitter.addWidget(left_widget)
        splitter.addWidget(right_widget)
        splitter.setSizes([200, 400])

        layout.addWidget(splitter)

        return widget

    def create_settings_tab(self):
        """创建设置标签页"""
        widget = QWidget()
        layout = QVBoxLayout(widget)

        # 基本设置
        basic_group = QGroupBox("基本设置")
        basic_layout = QVBoxLayout(basic_group)

        # 发送数量
        count_layout = QHBoxLayout()
        count_layout.addWidget(QLabel("默认发送数量:"))
        self.max_proposals_spin = QSpinBox()
        self.max_proposals_spin.setRange(1, 1000)
        self.max_proposals_spin.setValue(10)
        count_layout.addWidget(self.max_proposals_spin)
        count_layout.addStretch()
        basic_layout.addLayout(count_layout)

        layout.addWidget(basic_group)

        # 延迟设置
        delay_group = QGroupBox("延迟设置 (秒)")
        delay_layout = QVBoxLayout(delay_group)

        # 滚动延迟
        scroll_layout = QHBoxLayout()
        scroll_layout.addWidget(QLabel("滚动延迟:"))
        self.scroll_delay_spin = QSpinBox()
        self.scroll_delay_spin.setRange(1, 10)
        self.scroll_delay_spin.setValue(1)
        scroll_layout.addWidget(self.scroll_delay_spin)
        scroll_layout.addStretch()
        delay_layout.addLayout(scroll_layout)

        # 点击延迟
        click_layout = QHBoxLayout()
        click_layout.addWidget(QLabel("点击延迟:"))
        self.click_delay_spin = QSpinBox()
        self.click_delay_spin.setRange(1, 10)
        self.click_delay_spin.setValue(1)
        click_layout.addWidget(self.click_delay_spin)
        click_layout.addStretch()
        delay_layout.addLayout(click_layout)

        # 弹窗等待
        modal_layout = QHBoxLayout()
        modal_layout.addWidget(QLabel("弹窗等待:"))
        self.modal_wait_spin = QSpinBox()
        self.modal_wait_spin.setRange(1, 10)
        self.modal_wait_spin.setValue(1)
        modal_layout.addWidget(self.modal_wait_spin)
        modal_layout.addStretch()
        delay_layout.addLayout(modal_layout)

        layout.addWidget(delay_group)

        # 保存设置按钮
        save_settings_btn = QPushButton("💾 保存设置")
        save_settings_btn.clicked.connect(self.on_save_settings)
        layout.addWidget(save_settings_btn)

        layout.addStretch()

        return widget

    def create_browser_tab(self):
        """创建浏览器控制标签页"""
        widget = QWidget()
        layout = QVBoxLayout(widget)

        # 浏览器状态
        browser_group = QGroupBox("浏览器状态")
        browser_layout = QVBoxLayout(browser_group)

        # 连接状态
        status_layout = QHBoxLayout()
        status_layout.addWidget(QLabel("状态:"))
        self.browser_status_label = QLabel("未连接")
        self.browser_status_label.setStyleSheet("color: red; font-weight: bold;")
        status_layout.addWidget(self.browser_status_label)
        status_layout.addStretch()

        connect_btn = QPushButton("🔗 连接浏览器")
        connect_btn.clicked.connect(self.on_connect_browser)
        status_layout.addWidget(connect_btn)

        disconnect_btn = QPushButton("🚫 断开")
        disconnect_btn.clicked.connect(self.on_disconnect_browser)
        status_layout.addWidget(disconnect_btn)

        browser_layout.addLayout(status_layout)

        # 导航控制
        nav_group = QGroupBox("页面导航")
        nav_layout = QVBoxLayout(nav_group)

        # URL 输入
        url_layout = QHBoxLayout()
        url_layout.addWidget(QLabel("URL:"))
        self.url_input = QLineEdit()
        self.url_input.setText('https://app.impact.com/secure/mediapartner/marketplace/new-campaign-marketplace-flow.ihtml?execution=e1s1#sortBy=salepercent&sortOrder=DESC')
        url_layout.addWidget(self.url_input)

        nav_btn = QPushButton("🌐 访问")
        nav_btn.clicked.connect(self.on_navigate)
        url_layout.addWidget(nav_btn)

        nav_layout.addLayout(url_layout)

        # 预定义URL按钮
        predef_layout = QHBoxLayout()
        
        marketplace_btn = QPushButton("市场页面")
        marketplace_btn.clicked.connect(lambda: self.url_input.setText('https://app.impact.com/secure/mediapartner/marketplace/new-campaign-marketplace-flow.ihtml?execution=e1s1#sortBy=salepercent&sortOrder=DESC'))
        predef_layout.addWidget(marketplace_btn)

        campaigns_btn = QPushButton("活动页面")
        campaigns_btn.clicked.connect(lambda: self.url_input.setText('https://app.impact.com/secure/mediapartner/campaigns.ihtml'))
        predef_layout.addWidget(campaigns_btn)

        nav_layout.addLayout(predef_layout)

        browser_layout.addWidget(nav_group)
        
        # 刷新按钮
        refresh_btn = QPushButton("🔄 刷新页面")
        refresh_btn.clicked.connect(self.on_refresh_page)
        browser_layout.addWidget(refresh_btn)

        layout.addWidget(browser_group)
        layout.addStretch()

        return widget

    def load_data(self):
        """加载数据"""
        # 加载设置
        settings = load_settings()
        self.count_spinbox.setValue(settings.get('max_proposals', 10))
        self.max_proposals_spin.setValue(settings.get('max_proposals', 10))
        self.scroll_delay_spin.setValue(int(settings.get('scroll_delay', 1)))
        self.click_delay_spin.setValue(int(settings.get('click_delay', 1)))
        self.modal_wait_spin.setValue(int(settings.get('modal_wait', 1)))

        # 加载模板
        self.refresh_template_list()

        # 更新模板预览
        self.update_template_preview()

        # 检查浏览器连接
        self.check_browser_status()

    def refresh_template_list(self):
        """刷新模板列表"""
        self.template_list.clear()
        templates_data = load_all_templates()
        templates = templates_data.get('templates', [])
        active_id = templates_data.get('active_template_id')

        for tpl in templates:
            tpl_id = tpl.get('id', 0)
            name = tpl.get('name', '未命名')
            mark = " ✓" if tpl_id == active_id else ""
            item = QListWidgetItem(f"{name}{mark}")
            item.setData(Qt.UserRole, tpl_id)
            self.template_list.addItem(item)

    def update_template_preview(self):
        """更新模板预览"""
        template = load_template()
        self.template_preview.setText(template if template else "(无模板)")

    def check_browser_status(self):
        """检查浏览器连接状态"""
        from main import tab
        if tab:
            self.browser_status_label.setText("✅ 已连接")
            self.browser_status_label.setStyleSheet("color: green; font-weight: bold;")
        else:
            self.browser_status_label.setText("❌ 未连接")
            self.browser_status_label.setStyleSheet("color: red; font-weight: bold;")

    def log(self, message):
        """添加日志"""
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.log_text.append(f"[{timestamp}] {message}")
        # 滚动到底部
        cursor = self.log_text.textCursor()
        cursor.movePosition(QTextCursor.End)
        self.log_text.setTextCursor(cursor)

    # ========== 事件处理 ==========

    def on_start_clicked(self):
        """开始发送"""
        from main import tab

        if not tab:
            QMessageBox.warning(self, "警告", "请先连接浏览器！")
            return

        # 确认
        count = self.count_spinbox.value()
        reply = QMessageBox.question(
            self, "确认",
            f"确认开始发送 {count} 个 Proposal?\n\n请确保浏览器已导航到目标页面。",
            QMessageBox.Yes | QMessageBox.No
        )

        if reply != QMessageBox.Yes:
            return

        # 更新 UI 状态
        self.start_btn.setEnabled(False)
        self.stop_btn.setEnabled(True)
        self.progress_bar.setVisible(True)
        self.progress_bar.setMaximum(count)
        self.progress_bar.setValue(0)
        self.status_bar.showMessage("正在发送...")

        # 启动工作线程
        self.worker_thread = WorkerThread(count)
        self.worker_thread.progress.connect(self.on_progress)
        self.worker_thread.log_message.connect(self.log)
        self.worker_thread.finished_signal.connect(self.on_finished)
        self.worker_thread.error_signal.connect(self.on_error)
        self.worker_thread.start()

    def on_stop_clicked(self):
        """停止发送"""
        if self.worker_thread:
            self.worker_thread.stop()
            self.log("⏹️ 正在停止...")

    def on_progress(self, current, total):
        """进度更新"""
        self.progress_bar.setValue(current)
        self.status_bar.showMessage(f"正在发送... {current}/{total}")

    def on_finished(self, count):
        """完成"""
        self.start_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
        self.progress_bar.setVisible(False)
        self.status_bar.showMessage(f"完成！共发送 {count} 个 Proposal")
        self.log(f"===== 完成！共发送了 {count} 个 Send Proposal =====")
        QMessageBox.information(self, "完成", f"发送完成！共发送 {count} 个 Proposal")

    def on_error(self, message):
        """错误"""
        self.start_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
        self.progress_bar.setVisible(False)
        self.status_bar.showMessage("发生错误")
        self.log(f"❌ 错误: {message}")
        QMessageBox.critical(self, "错误", message)

    def on_connect_browser(self):
        """连接浏览器"""
        if init_browser():
            self.check_browser_status()
            self.log("✅ 浏览器连接成功")
            QMessageBox.information(self, "成功", "浏览器连接成功！")
        else:
            self.check_browser_status()
            self.log("❌ 浏览器连接失败")
            QMessageBox.critical(self, "错误", "浏览器连接失败！请确保浏览器已打开。")

    def on_disconnect_browser(self):
        """断开浏览器"""
        from main import browser
        if browser:
            try:
                browser.quit()
                self.log("✅ 浏览器已断开")
                self.check_browser_status()
                QMessageBox.information(self, "成功", "浏览器已断开连接")
            except:
                pass

    def on_navigate(self):
        """导航到URL"""
        from main import tab
        if not tab:
            QMessageBox.warning(self, "警告", "请先连接浏览器！")
            return

        url = self.url_input.text()
        if not url:
            QMessageBox.warning(self, "警告", "请输入有效的URL！")
            return

        try:
            tab.get(url)
            self.log(f"✅ 导航到: {url}")
            QMessageBox.information(self, "成功", f"已导航到:\n{url}")
        except Exception as e:
            self.log(f"❌ 导航失败: {e}")
            QMessageBox.critical(self, "错误", f"导航失败: {e}")

    def on_refresh_page(self):
        """刷新页面"""
        from main import tab
        if not tab:
            QMessageBox.warning(self, "警告", "请先连接浏览器！")
            return

        try:
            tab.refresh()
            self.log("✅ 页面已刷新")
            QMessageBox.information(self, "成功", "页面已刷新")
        except Exception as e:
            self.log(f"❌ 刷新失败: {e}")
            QMessageBox.critical(self, "错误", f"刷新失败: {e}")

    def on_template_selected(self, row):
        """选择模板"""
        if row < 0:
            return

        item = self.template_list.item(row)
        tpl_id = item.data(Qt.UserRole)

        templates_data = load_all_templates()
        for tpl in templates_data.get('templates', []):
            if tpl.get('id') == tpl_id:
                self.template_name_edit.setText(tpl.get('name', ''))
                self.template_content_edit.setText(tpl.get('content', ''))
                break

    def on_add_template(self):
        """添加模板"""
        name, ok = QInputDialog.getText(self, "添加模板", "请输入模板名称:")
        if not ok or not name:
            return

        templates_data = load_all_templates()
        new_id = get_next_template_id(templates_data)
        templates_data['templates'].append({
            "id": new_id,
            "name": name,
            "content": ""
        })

        if save_all_templates(templates_data):
            self.refresh_template_list()
            self.log(f"✅ 模板 '{name}' 已添加")

    def on_delete_template(self):
        """删除模板"""
        row = self.template_list.currentRow()
        if row < 0:
            QMessageBox.warning(self, "警告", "请先选择一个模板")
            return

        templates_data = load_all_templates()
        if len(templates_data.get('templates', [])) <= 1:
            QMessageBox.warning(self, "警告", "至少需要保留一个模板")
            return

        item = self.template_list.item(row)
        tpl_id = item.data(Qt.UserRole)

        reply = QMessageBox.question(
            self, "确认删除",
            "确定要删除这个模板吗？",
            QMessageBox.Yes | QMessageBox.No
        )

        if reply != QMessageBox.Yes:
            return

        templates_data['templates'] = [t for t in templates_data['templates'] if t.get('id') != tpl_id]

        # 如果删除的是激活的模板，切换到第一个
        if tpl_id == templates_data.get('active_template_id') and templates_data['templates']:
            templates_data['active_template_id'] = templates_data['templates'][0].get('id')

        if save_all_templates(templates_data):
            self.refresh_template_list()
            self.update_template_preview()
            self.log("✅ 模板已删除")

    def on_activate_template(self):
        """激活模板"""
        row = self.template_list.currentRow()
        if row < 0:
            QMessageBox.warning(self, "警告", "请先选择一个模板")
            return

        item = self.template_list.item(row)
        tpl_id = item.data(Qt.UserRole)

        templates_data = load_all_templates()
        templates_data['active_template_id'] = tpl_id

        if save_all_templates(templates_data):
            self.refresh_template_list()
            self.update_template_preview()
            self.log("✅ 模板已激活")

    def on_save_template(self):
        """保存模板"""
        row = self.template_list.currentRow()
        if row < 0:
            QMessageBox.warning(self, "警告", "请先选择一个模板")
            return

        item = self.template_list.item(row)
        tpl_id = item.data(Qt.UserRole)

        templates_data = load_all_templates()
        for i, tpl in enumerate(templates_data.get('templates', [])):
            if tpl.get('id') == tpl_id:
                templates_data['templates'][i]['name'] = self.template_name_edit.text()
                templates_data['templates'][i]['content'] = self.template_content_edit.toPlainText()
                break

        if save_all_templates(templates_data):
            self.refresh_template_list()
            self.update_template_preview()
            self.log("✅ 模板已保存")
            QMessageBox.information(self, "成功", "模板保存成功！")

    def on_save_settings(self):
        """保存设置"""
        settings = load_settings()
        settings['max_proposals'] = self.max_proposals_spin.value()
        settings['scroll_delay'] = self.scroll_delay_spin.value()
        settings['click_delay'] = self.click_delay_spin.value()
        settings['modal_wait'] = self.modal_wait_spin.value()

        if save_settings(settings):
            self.log("✅ 设置已保存")
            QMessageBox.information(self, "成功", "设置保存成功！")

    def closeEvent(self, event):
        """关闭窗口"""
        if self.worker_thread and self.worker_thread.isRunning():
            reply = QMessageBox.question(
                self, "确认退出",
                "任务正在运行中，确定要退出吗？",
                QMessageBox.Yes | QMessageBox.No
            )
            if reply == QMessageBox.No:
                event.ignore()
                return
            self.worker_thread.stop()
            self.worker_thread.wait()
        event.accept()


def main():
    app = QApplication(sys.argv)

    # 设置样式
    app.setStyle('Fusion')

    window = MainWindow()
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()