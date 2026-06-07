from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, 
    QPushButton, QComboBox, QTableWidget, QTableWidgetItem,
    QMessageBox, QGroupBox, QLineEdit, QTextEdit, 
    QSpinBox, QCheckBox, QFileDialog, QSplitter,
    QHeaderView, QFormLayout
)
from PySide6.QtCore import Qt
from pathlib import Path
import logging
from datetime import datetime

from app.storage.database import Database
from app.core.rpa_exe_config_service import RpaExeConfigService
from app.ui.widgets.table_highlight import enable_table_highlight


class RpaExeConfigPage(QWidget):
    
    def __init__(self, db: Database):
        super().__init__()
        self.db = db
        self.exe_config_service = RpaExeConfigService(db)
        self.current_config_id = ""
        
        self._init_ui()
        self._load_configs()
    
    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(10)
        
        splitter = QSplitter(Qt.Horizontal)
        
        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)
        
        list_group = QGroupBox("EXE配置列表")
        list_layout = QVBoxLayout(list_group)
        
        list_toolbar = QHBoxLayout()
        self.refresh_btn = QPushButton("刷新列表")
        self.refresh_btn.clicked.connect(self._load_configs)
        list_toolbar.addWidget(self.refresh_btn)
        
        self.new_config_btn = QPushButton("新增配置")
        self.new_config_btn.clicked.connect(self._new_config)
        list_toolbar.addWidget(self.new_config_btn)
        
        list_toolbar.addStretch()
        list_layout.addLayout(list_toolbar)
        
        self.config_table = QTableWidget()
        self.config_table.setAlternatingRowColors(True)
        self.config_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.config_table.setSelectionMode(QTableWidget.SingleSelection)
        self.config_table.setMinimumWidth(400)
        self.config_table.cellClicked.connect(self._on_config_selected)
        enable_table_highlight(self.config_table)
        list_layout.addWidget(self.config_table)
        
        left_layout.addWidget(list_group)
        splitter.addWidget(left_widget)
        
        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)
        
        edit_group = QGroupBox("配置详情")
        edit_layout = QFormLayout(edit_group)
        
        self.config_name_input = QLineEdit()
        edit_layout.addRow("配置名称:", self.config_name_input)
        
        exe_row = QHBoxLayout()
        self.exe_path_input = QLineEdit()
        exe_row.addWidget(self.exe_path_input)
        
        self.select_exe_btn = QPushButton("选择EXE")
        self.select_exe_btn.clicked.connect(self._select_exe_file)
        exe_row.addWidget(self.select_exe_btn)
        edit_layout.addRow("EXE路径:", exe_row)
        
        self.process_name_input = QLineEdit()
        edit_layout.addRow("进程名:", self.process_name_input)
        
        self.main_window_title_input = QLineEdit()
        edit_layout.addRow("主窗口标题:", self.main_window_title_input)
        
        self.login_window_title_input = QLineEdit()
        edit_layout.addRow("登录窗口标题:", self.login_window_title_input)
        
        self.username_input = QLineEdit()
        edit_layout.addRow("登录账号:", self.username_input)
        
        self.password_input = QLineEdit()
        self.password_input.setEchoMode(QLineEdit.Password)
        edit_layout.addRow("登录密码:", self.password_input)
        
        self.login_success_rule_input = QLineEdit()
        self.login_success_rule_input.setPlaceholderText("如: 窗口标题包含 '主界面'")
        edit_layout.addRow("登录成功规则:", self.login_success_rule_input)
        
        self.default_wait_time_spin = QSpinBox()
        self.default_wait_time_spin.setMinimum(1)
        self.default_wait_time_spin.setMaximum(60)
        self.default_wait_time_spin.setValue(5)
        edit_layout.addRow("默认等待时间(秒):", self.default_wait_time_spin)
        
        self.operation_timeout_spin = QSpinBox()
        self.operation_timeout_spin.setMinimum(10)
        self.operation_timeout_spin.setMaximum(300)
        self.operation_timeout_spin.setValue(30)
        edit_layout.addRow("操作超时时间(秒):", self.operation_timeout_spin)
        
        options_row = QHBoxLayout()
        self.close_old_process_check = QCheckBox("启动前关闭旧进程")
        self.close_old_process_check.setChecked(True)
        options_row.addWidget(self.close_old_process_check)
        
        self.auto_login_check = QCheckBox("自动登录")
        self.auto_login_check.setChecked(True)
        options_row.addWidget(self.auto_login_check)
        edit_layout.addRow("选项:", options_row)
        
        right_layout.addWidget(edit_group)
        
        test_group = QGroupBox("测试操作")
        test_layout = QHBoxLayout(test_group)
        
        self.test_launch_btn = QPushButton("测试启动")
        self.test_launch_btn.clicked.connect(self._test_launch)
        test_layout.addWidget(self.test_launch_btn)
        
        self.test_connection_btn = QPushButton("测试连接")
        self.test_connection_btn.clicked.connect(self._test_connection)
        test_layout.addWidget(self.test_connection_btn)
        
        self.get_process_btn = QPushButton("获取进程列表")
        self.get_process_btn.clicked.connect(self._get_process_list)
        test_layout.addWidget(self.get_process_btn)
        
        test_layout.addStretch()
        right_layout.addWidget(test_group)
        
        save_group = QGroupBox("保存操作")
        save_layout = QHBoxLayout(save_group)
        
        self.save_btn = QPushButton("保存配置")
        self.save_btn.clicked.connect(self._save_config)
        self.save_btn.setStyleSheet("background-color: #4CAF50; color: white;")
        save_layout.addWidget(self.save_btn)
        
        self.delete_btn = QPushButton("删除配置")
        self.delete_btn.clicked.connect(self._delete_config)
        self.delete_btn.setStyleSheet("background-color: #f44336; color: white;")
        save_layout.addWidget(self.delete_btn)
        
        save_layout.addStretch()
        right_layout.addWidget(save_group)
        
        log_group = QGroupBox("操作日志")
        log_layout = QVBoxLayout(log_group)
        
        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setMinimumHeight(100)
        log_layout.addWidget(self.log_text)
        
        right_layout.addWidget(log_group)
        
        splitter.addWidget(right_widget)
        
        splitter.setSizes([400, 500])
        
        layout.addWidget(splitter)
    
    def _load_configs(self):
        configs, error = self.exe_config_service.get_all_configs()
        if error:
            self._log(f"加载配置列表失败: {error}")
            return
        
        headers = ["配置名称", "EXE路径", "进程名", "主窗口标题", "创建时间"]
        self.config_table.clear()
        self.config_table.setColumnCount(len(headers))
        self.config_table.setHorizontalHeaderLabels(headers)
        self.config_table.setRowCount(len(configs))
        
        for row_idx, config in enumerate(configs):
            self.config_table.setItem(row_idx, 0, QTableWidgetItem(config['config_name']))
            self.config_table.setItem(row_idx, 1, QTableWidgetItem(config['exe_path']))
            self.config_table.setItem(row_idx, 2, QTableWidgetItem(config['process_name'] or ""))
            self.config_table.setItem(row_idx, 3, QTableWidgetItem(config['main_window_title'] or ""))
            created_at = config['created_at']
            self.config_table.setItem(row_idx, 4, QTableWidgetItem(created_at[:10] if created_at else ""))
            
            self.config_table.item(row_idx, 0).setData(Qt.UserRole, config['config_id'])
        
        self.config_table.resizeColumnsToContents()
        self._log(f"已加载 {len(configs)} 个EXE配置")
    
    def _on_config_selected(self, row, col):
        config_id = self.config_table.item(row, 0).data(Qt.UserRole)
        if config_id:
            self._load_config_detail(config_id)
    
    def _load_config_detail(self, config_id):
        config, error = self.exe_config_service.get_config(config_id)
        if error:
            self._log(f"加载配置详情失败: {error}")
            return
        
        self.current_config_id = config_id
        
        self.config_name_input.setText(config['config_name'])
        self.exe_path_input.setText(config['exe_path'])
        self.process_name_input.setText(config['process_name'] or "")
        self.main_window_title_input.setText(config['main_window_title'] or "")
        self.login_window_title_input.setText(config['login_window_title'] or "")
        self.username_input.setText(config['username'] or "")
        self.password_input.setText(config['password'] or "")
        self.login_success_rule_input.setText(config['login_success_rule'] or "")
        self.default_wait_time_spin.setValue(config['default_wait_time'] or 5)
        self.operation_timeout_spin.setValue(config['operation_timeout'] or 30)
        self.close_old_process_check.setChecked(config['close_old_process'] == 1)
        self.auto_login_check.setChecked(config['auto_login'] == 1)
        
        self._log(f"已加载配置: {config['config_name']}")
    
    def _new_config(self):
        self.current_config_id = ""
        
        self.config_name_input.clear()
        self.exe_path_input.clear()
        self.process_name_input.clear()
        self.main_window_title_input.clear()
        self.login_window_title_input.clear()
        self.username_input.clear()
        self.password_input.clear()
        self.login_success_rule_input.clear()
        self.default_wait_time_spin.setValue(5)
        self.operation_timeout_spin.setValue(30)
        self.close_old_process_check.setChecked(True)
        self.auto_login_check.setChecked(True)
        
        self._log("新建配置，请填写配置信息")
    
    def _select_exe_file(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "选择EXE文件",
            "",
            "可执行文件 (*.exe)"
        )
        
        if file_path:
            self.exe_path_input.setText(file_path)
            
            exe_name = Path(file_path).stem
            if not self.process_name_input.text():
                self.process_name_input.setText(f"{exe_name}.exe")
            
            if not self.config_name_input.text():
                self.config_name_input.setText(exe_name)
            
            self._log(f"已选择EXE: {file_path}")
    
    def _save_config(self):
        config_name = self.config_name_input.text()
        exe_path = self.exe_path_input.text()
        
        if not config_name:
            QMessageBox.warning(self, "提示", "请输入配置名称")
            return
        
        if not exe_path:
            QMessageBox.warning(self, "提示", "请选择EXE文件")
            return
        
        config_data = {
            'config_id': self.current_config_id,
            'config_name': config_name,
            'exe_path': exe_path,
            'process_name': self.process_name_input.text(),
            'main_window_title': self.main_window_title_input.text(),
            'login_window_title': self.login_window_title_input.text(),
            'username': self.username_input.text(),
            'password': self.password_input.text(),
            'login_success_rule': self.login_success_rule_input.text(),
            'default_wait_time': self.default_wait_time_spin.value(),
            'operation_timeout': self.operation_timeout_spin.value(),
            'close_old_process': 1 if self.close_old_process_check.isChecked() else 0,
            'auto_login': 1 if self.auto_login_check.isChecked() else 0
        }
        
        config_id, error = self.exe_config_service.save_config(config_data)
        if error:
            QMessageBox.warning(self, "保存失败", f"保存配置失败:\n{error}")
            self._log(f"保存失败: {error}")
            return
        
        self.current_config_id = config_id
        self._log(f"保存成功: {config_id}")
        
        QMessageBox.information(self, "保存成功", f"配置已保存\n配置ID: {config_id}")
        
        self._load_configs()
    
    def _delete_config(self):
        if not self.current_config_id:
            QMessageBox.warning(self, "提示", "请先选择要删除的配置")
            return
        
        reply = QMessageBox.question(
            self, "确认删除",
            "确认删除此配置?",
            QMessageBox.Yes | QMessageBox.No
        )
        
        if reply != QMessageBox.Yes:
            return
        
        success, error = self.exe_config_service.delete_config(self.current_config_id)
        if error:
            QMessageBox.warning(self, "删除失败", f"删除配置失败:\n{error}")
            self._log(f"删除失败: {error}")
            return
        
        self._log(f"删除成功: {self.current_config_id}")
        
        self.current_config_id = ""
        self._new_config()
        self._load_configs()
    
    def _test_launch(self):
        if not self.current_config_id:
            QMessageBox.warning(self, "提示", "请先保存配置后再测试")
            return
        
        self._log("正在启动EXE...")
        
        success, message = self.exe_config_service.test_launch(self.current_config_id)
        if success:
            QMessageBox.information(self, "启动成功", message)
            self._log(f"启动成功: {message}")
        else:
            QMessageBox.warning(self, "启动失败", message)
            self._log(f"启动失败: {message}")
    
    def _test_connection(self):
        if not self.current_config_id:
            QMessageBox.warning(self, "提示", "请先保存配置后再测试")
            return
        
        self._log("正在测试连接...")
        
        success, message = self.exe_config_service.test_connection(self.current_config_id)
        if success:
            QMessageBox.information(self, "连接成功", message)
            self._log(f"连接成功: {message}")
        else:
            QMessageBox.warning(self, "连接失败", message)
            self._log(f"连接失败: {message}")
    
    def _get_process_list(self):
        processes, error = self.exe_config_service.get_process_list()
        if error:
            self._log(f"获取进程列表失败: {error}")
            return
        
        process_names = [p['name'] for p in processes[:50]]
        
        self._log(f"当前运行进程 (前50个):\n" + "\n".join(process_names))
        
        QMessageBox.information(
            self, "进程列表",
            f"当前运行进程数: {len(processes)}\n\n前50个进程:\n" + "\n".join(process_names)
        )
    
    def _log(self, message):
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.log_text.append(f"{timestamp} {message}")
        logging.info(f"EXE配置: {message}")