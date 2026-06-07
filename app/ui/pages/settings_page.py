from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, 
    QPushButton, QLineEdit, QComboBox, QGroupBox,
    QTableWidget, QTableWidgetItem, QMessageBox,
    QTextEdit, QSpinBox, QTabWidget, QHeaderView,
    QCheckBox
)
from PySide6.QtCore import Qt
from app.core.database_config_service import DatabaseConfigService, DbConfig
from app.core.db_import_service import DbImportService
from app.core.permission_checker import PermissionChecker, PermissionCodes
from app.ui.widgets.table_highlight import enable_table_highlight


class SettingsPage(QWidget):
    
    def __init__(self, db, username: str = None):
        super().__init__()
        self.db = db
        self.username = username or 'admin'
        self.db_config_service = DatabaseConfigService(db)
        
        # 创建权限检查器
        self.permission_checker = PermissionChecker(db, self.username)
        
        self._init_ui()
        self._load_configs()
    
    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(15)
        
        tabs = QTabWidget()
        
        db_config_tab = self._create_db_config_tab()
        tabs.addTab(db_config_tab, "数据库连接配置")
        
        import_config_tab = self._create_import_config_tab()
        tabs.addTab(import_config_tab, "导入配置")
        
        layout.addWidget(tabs)
    
    def _create_db_config_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setSpacing(10)
        
        list_group = QGroupBox("已保存的数据库配置")
        list_layout = QVBoxLayout(list_group)
        
        self.config_table = QTableWidget()
        self.config_table.setColumnCount(6)
        self.config_table.setHorizontalHeaderLabels(["名称", "主机", "端口", "数据库", "用户名", "操作"])
        self.config_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.config_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.config_table.horizontalHeader().setSectionResizeMode(5, QHeaderView.ResizeToContents)
        enable_table_highlight(self.config_table)
        list_layout.addWidget(self.config_table)
        
        btn_row = QHBoxLayout()
        
        self.add_config_btn = QPushButton("新增配置")
        self.add_config_btn.clicked.connect(self._add_config)
        btn_row.addWidget(self.add_config_btn)
        
        btn_row.addStretch()
        list_layout.addLayout(btn_row)
        
        layout.addWidget(list_group)
        
        edit_group = QGroupBox("编辑配置")
        edit_layout = QVBoxLayout(edit_group)
        
        row1 = QHBoxLayout()
        row1.addWidget(QLabel("配置名称:"))
        self.config_name_input = QLineEdit()
        self.config_name_input.setPlaceholderText("如：生产环境、测试环境")
        row1.addWidget(self.config_name_input)
        
        row1.addWidget(QLabel("主机:"))
        self.host_input = QLineEdit("localhost")
        row1.addWidget(self.host_input)
        
        row1.addWidget(QLabel("端口:"))
        self.port_input = QSpinBox()
        self.port_input.setRange(1, 65535)
        self.port_input.setValue(3306)
        row1.addWidget(self.port_input)
        
        edit_layout.addLayout(row1)
        
        row2 = QHBoxLayout()
        row2.addWidget(QLabel("数据库名:"))
        self.db_name_input = QLineEdit()
        row2.addWidget(self.db_name_input)
        
        row2.addWidget(QLabel("用户名:"))
        self.username_input = QLineEdit("root")
        row2.addWidget(self.username_input)
        
        row2.addWidget(QLabel("密码:"))
        self.password_input = QLineEdit()
        self.password_input.setEchoMode(QLineEdit.Password)
        row2.addWidget(self.password_input)
        
        edit_layout.addLayout(row2)
        
        row3 = QHBoxLayout()
        row3.addWidget(QLabel("字符集:"))
        self.charset_combo = QComboBox()
        self.charset_combo.addItems(["utf8mb4", "utf8", "gbk", "latin1"])
        row3.addWidget(self.charset_combo)
        
        row3.addWidget(QLabel("超时(秒):"))
        self.timeout_input = QSpinBox()
        self.timeout_input.setRange(1, 300)
        self.timeout_input.setValue(30)
        row3.addWidget(self.timeout_input)
        
        row3.addStretch()
        edit_layout.addLayout(row3)
        
        row4 = QHBoxLayout()
        row4.addWidget(QLabel("入库查询SQL:"))
        edit_layout.addLayout(row4)
        
        self.sql_input = QTextEdit()
        self.sql_input.setPlaceholderText("SELECT inbound_no, inbound_date, product_name, manufacturer, spec, quantity, unit_price, amount, barcode FROM inbound_table WHERE inbound_date BETWEEN '{start_date}' AND '{end_date}'")
        self.sql_input.setMaximumHeight(100)
        edit_layout.addWidget(self.sql_input)
        
        btn_row2 = QHBoxLayout()
        
        self.test_btn = QPushButton("测试连接")
        self.test_btn.clicked.connect(self._test_connection)
        btn_row2.addWidget(self.test_btn)
        
        self.save_btn = QPushButton("保存配置")
        self.save_btn.clicked.connect(self._save_config)
        btn_row2.addWidget(self.save_btn)
        
        self.clear_btn = QPushButton("清空")
        self.clear_btn.clicked.connect(self._clear_form)
        btn_row2.addWidget(self.clear_btn)
        
        btn_row2.addStretch()
        edit_layout.addLayout(btn_row2)
        
        layout.addWidget(edit_group)
        
        self.editing_config_id = None
        
        return tab
    
    def _create_import_config_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setSpacing(10)
        
        info_group = QGroupBox("导入说明")
        info_layout = QVBoxLayout(info_group)
        
        info_text = QLabel("""
数据库导入功能说明：

1. 支持导入 .sql 格式的数据库备份文件
2. 自动处理原数据库引用（如 `72972`.table 会自动修正）
3. 支持大文件导入（建议不超过500MB）
4. 导入前请确保目标数据库已创建

使用步骤：
1. 在"数据库连接配置"中配置好MySQL连接
2. 进入"数据库导入"页面
3. 选择SQL文件并执行导入
        """)
        info_text.setStyleSheet("color: #666; line-height: 1.5;")
        info_layout.addWidget(info_text)
        
        layout.addWidget(info_group)
        
        default_group = QGroupBox("默认导入设置")
        default_layout = QVBoxLayout(default_group)
        
        row1 = QHBoxLayout()
        row1.addWidget(QLabel("默认字符集:"))
        self.import_charset_combo = QComboBox()
        self.import_charset_combo.addItems(["utf8mb4", "utf8", "gbk"])
        row1.addWidget(self.import_charset_combo)
        
        row1.addWidget(QLabel("导入超时(秒):"))
        self.import_timeout_input = QSpinBox()
        self.import_timeout_input.setRange(60, 3600)
        self.import_timeout_input.setValue(600)
        row1.addWidget(self.import_timeout_input)
        
        row1.addStretch()
        default_layout.addLayout(row1)
        
        layout.addWidget(default_group)
        layout.addStretch()
        
        return tab
    
    def _load_configs(self):
        configs = self.db_config_service.get_all_configs()
        
        self.config_table.setRowCount(len(configs))
        
        for row, config in enumerate(configs):
            self.config_table.setItem(row, 0, QTableWidgetItem(config.name))
            self.config_table.setItem(row, 1, QTableWidgetItem(config.host))
            self.config_table.setItem(row, 2, QTableWidgetItem(str(config.port)))
            self.config_table.setItem(row, 3, QTableWidgetItem(config.database_name))
            self.config_table.setItem(row, 4, QTableWidgetItem(config.username))
            
            edit_btn = QPushButton("编辑")
            edit_btn.setProperty("config_id", config.id)
            edit_btn.clicked.connect(lambda checked, cid=config.id: self._edit_config(cid))
            
            delete_btn = QPushButton("删除")
            delete_btn.setProperty("config_id", config.id)
            delete_btn.clicked.connect(lambda checked, cid=config.id: self._delete_config(cid))
            
            btn_widget = QWidget()
            btn_layout = QHBoxLayout(btn_widget)
            btn_layout.setContentsMargins(2, 2, 2, 2)
            btn_layout.addWidget(edit_btn)
            btn_layout.addWidget(delete_btn)
            
            self.config_table.setCellWidget(row, 5, btn_widget)
    
    def _add_config(self):
        self._clear_form()
    
    def _edit_config(self, config_id: int):
        config = self.db_config_service.get_config_by_id(config_id)
        if config:
            self.editing_config_id = config_id
            self.config_name_input.setText(config.name)
            self.host_input.setText(config.host)
            self.port_input.setValue(config.port)
            self.db_name_input.setText(config.database_name)
            self.username_input.setText(config.username)
            self.password_input.setText(config.password)
            self.charset_combo.setCurrentText(config.charset)
            self.timeout_input.setValue(config.timeout)
            self.sql_input.setPlainText(config.inbound_sql or "")
    
    def _delete_config(self, config_id: int):
        # 权限检查
        if not self.permission_checker.check_permission(PermissionCodes.OP_CONFIG_SAVE_DATABASE, self):
            return
        
        reply = QMessageBox.question(
            self, "确认删除",
            "确定要删除此配置吗？",
            QMessageBox.Yes | QMessageBox.No
        )
        
        if reply == QMessageBox.Yes:
            self.db_config_service.delete_config(config_id)
            self._load_configs()
            QMessageBox.information(self, "成功", "配置已删除")
    
    def _test_connection(self):
        config = DbConfig(
            name=self.config_name_input.text(),
            host=self.host_input.text(),
            port=self.port_input.value(),
            database_name=self.db_name_input.text(),
            username=self.username_input.text(),
            password=self.password_input.text()
        )
        
        success, msg = self.db_config_service.test_connection(config)
        
        if success:
            QMessageBox.information(self, "成功", msg)
        else:
            QMessageBox.warning(self, "失败", msg)
    
    def _save_config(self):
        # 权限检查
        if not self.permission_checker.check_permission(PermissionCodes.OP_CONFIG_SAVE_DATABASE, self):
            return
        
        name = self.config_name_input.text().strip()
        if not name:
            QMessageBox.warning(self, "提示", "请输入配置名称")
            return
        
        host = self.host_input.text().strip()
        if not host:
            QMessageBox.warning(self, "提示", "请输入主机地址")
            return
        
        db_name = self.db_name_input.text().strip()
        if not db_name:
            QMessageBox.warning(self, "提示", "请输入数据库名")
            return
        
        config = DbConfig(
            id=self.editing_config_id or 0,
            name=name,
            host=host,
            port=self.port_input.value(),
            database_name=db_name,
            username=self.username_input.text(),
            password=self.password_input.text(),
            charset=self.charset_combo.currentText(),
            timeout=self.timeout_input.value(),
            inbound_sql=self.sql_input.toPlainText()
        )
        
        config_id = self.db_config_service.save_config(config)
        self.editing_config_id = config_id
        
        self._load_configs()
        QMessageBox.information(self, "成功", "配置已保存")
    
    def _clear_form(self):
        self.editing_config_id = None
        self.config_name_input.clear()
        self.host_input.setText("localhost")
        self.port_input.setValue(3306)
        self.db_name_input.clear()
        self.username_input.setText("root")
        self.password_input.clear()
        self.charset_combo.setCurrentText("utf8mb4")
        self.timeout_input.setValue(30)
        self.sql_input.clear()
