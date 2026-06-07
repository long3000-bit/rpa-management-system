from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, 
    QPushButton, QLineEdit, QComboBox, QGroupBox,
    QTableWidget, QTableWidgetItem, QMessageBox,
    QTextEdit, QProgressBar, QFileDialog, QHeaderView, QSpinBox
)
from PySide6.QtCore import Qt, QThread, Signal
from app.core.db_import_service import DbImportService, DbImportResult
from app.core.database_config_service import DatabaseConfigService
from app.core.permission_checker import PermissionChecker, PermissionCodes
from app.ui.widgets.table_highlight import enable_table_highlight


class ImportWorker(QThread):
    progress = Signal(int, str)
    finished = Signal(object)
    
    def __init__(self, service: DbImportService, sql_file: str, db_name: str):
        super().__init__()
        self.service = service
        self.sql_file = sql_file
        self.db_name = db_name
    
    def run(self):
        result = self.service.import_sql(
            self.sql_file, 
            self.db_name,
            lambda progress, msg: self.progress.emit(progress, msg)
        )
        self.finished.emit(result)


class DbImportPage(QWidget):
    
    def __init__(self, db, username: str = None):
        super().__init__()
        self.db = db
        self.username = username or 'admin'
        self.db_config_service = DatabaseConfigService(db)
        self.import_service = DbImportService()
        
        # 创建权限检查器
        self.permission_checker = PermissionChecker(db, self.username)
        
        self.import_worker = None
        self._init_ui()
        self._load_configs()
    
    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(15)
        
        conn_group = QGroupBox("数据库连接（从配置中心读取）")
        conn_layout = QVBoxLayout(conn_group)
        
        row1 = QHBoxLayout()
        row1.addWidget(QLabel("选择配置:"))
        self.config_combo = QComboBox()
        self.config_combo.setMinimumWidth(200)
        self.config_combo.currentIndexChanged.connect(self._on_config_changed)
        row1.addWidget(self.config_combo)
        
        self.refresh_btn = QPushButton("刷新配置")
        self.refresh_btn.clicked.connect(self._load_configs)
        row1.addWidget(self.refresh_btn)
        
        self.goto_settings_btn = QPushButton("配置中心")
        self.goto_settings_btn.clicked.connect(self._goto_settings)
        row1.addWidget(self.goto_settings_btn)
        
        row1.addStretch()
        conn_layout.addLayout(row1)
        
        info_row = QHBoxLayout()
        info_row.addWidget(QLabel("当前连接:"))
        self.conn_info_label = QLabel("未选择配置")
        self.conn_info_label.setStyleSheet("color: #666;")
        info_row.addWidget(self.conn_info_label)
        info_row.addStretch()
        conn_layout.addLayout(info_row)
        
        layout.addWidget(conn_group)
        
        db_group = QGroupBox("数据库管理")
        db_layout = QVBoxLayout(db_group)
        
        row2 = QHBoxLayout()
        row2.addWidget(QLabel("现有数据库:"))
        self.db_combo = QComboBox()
        self.db_combo.setMinimumWidth(200)
        row2.addWidget(self.db_combo)
        
        self.refresh_db_btn = QPushButton("刷新列表")
        self.refresh_db_btn.clicked.connect(self._refresh_databases)
        row2.addWidget(self.refresh_db_btn)
        
        row2.addWidget(QLabel("新建数据库名:"))
        self.new_db_input = QLineEdit()
        self.new_db_input.setPlaceholderText("输入新数据库名称")
        self.new_db_input.setFixedWidth(150)
        row2.addWidget(self.new_db_input)
        
        self.create_db_btn = QPushButton("创建数据库")
        self.create_db_btn.clicked.connect(self._create_database)
        row2.addWidget(self.create_db_btn)
        
        self.drop_db_btn = QPushButton("删除数据库")
        self.drop_db_btn.clicked.connect(self._drop_database)
        row2.addWidget(self.drop_db_btn)
        
        row2.addStretch()
        db_layout.addLayout(row2)
        layout.addWidget(db_group)
        
        import_group = QGroupBox("SQL文件导入")
        import_layout = QVBoxLayout(import_group)
        
        options_row = QHBoxLayout()
        options_row.addWidget(QLabel("字符集:"))
        self.charset_combo = QComboBox()
        self.charset_combo.addItems(["utf8mb4", "utf8", "gbk"])
        options_row.addWidget(self.charset_combo)
        
        options_row.addWidget(QLabel("导入超时(秒):"))
        self.timeout_spin = QSpinBox()
        self.timeout_spin.setRange(60, 7200)
        self.timeout_spin.setValue(3600)
        options_row.addWidget(self.timeout_spin)
        options_row.addStretch()
        import_layout.addLayout(options_row)
        
        row3 = QHBoxLayout()
        row3.addWidget(QLabel("SQL文件:"))
        self.sql_file_input = QLineEdit()
        self.sql_file_input.setReadOnly(True)
        self.sql_file_input.setPlaceholderText("选择要导入的SQL文件")
        row3.addWidget(self.sql_file_input)
        
        self.select_file_btn = QPushButton("选择文件")
        self.select_file_btn.clicked.connect(self._select_sql_file)
        row3.addWidget(self.select_file_btn)
        
        row3.addWidget(QLabel("导入到:"))
        self.target_db_combo = QComboBox()
        self.target_db_combo.setMinimumWidth(150)
        row3.addWidget(self.target_db_combo)
        
        self.import_btn = QPushButton("开始导入")
        self.import_btn.clicked.connect(self._start_import)
        row3.addWidget(self.import_btn)
        
        import_layout.addLayout(row3)
        
        progress_row = QHBoxLayout()
        self.progress_bar = QProgressBar()
        progress_row.addWidget(self.progress_bar)
        
        self.status_label = QLabel("就绪")
        self.status_label.setMinimumWidth(200)
        progress_row.addWidget(self.status_label)
        
        import_layout.addLayout(progress_row)
        layout.addWidget(import_group)
        
        result_group = QGroupBox("导入结果")
        result_layout = QVBoxLayout(result_group)
        
        self.result_table = QTableWidget()
        self.result_table.setColumnCount(2)
        self.result_table.setHorizontalHeaderLabels(["项目", "值"])
        self.result_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.result_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.result_table.setRowCount(4)
        enable_table_highlight(self.result_table)
        
        items = [
            ("状态", "-"),
            ("数据库名", "-"),
            ("表数量", "-"),
            ("错误信息", "-"),
        ]
        for row, (label, value) in enumerate(items):
            self.result_table.setItem(row, 0, QTableWidgetItem(label))
            self.result_table.setItem(row, 1, QTableWidgetItem(value))
        
        result_layout.addWidget(self.result_table)
        layout.addWidget(result_group)
        
        tables_group = QGroupBox("数据库表列表")
        tables_layout = QVBoxLayout(tables_group)
        
        tables_row = QHBoxLayout()
        tables_row.addWidget(QLabel("选择数据库:"))
        self.view_tables_combo = QComboBox()
        self.view_tables_combo.setMinimumWidth(150)
        tables_row.addWidget(self.view_tables_combo)
        
        self.view_tables_btn = QPushButton("查看表")
        self.view_tables_btn.clicked.connect(self._view_tables)
        tables_row.addWidget(self.view_tables_btn)
        
        tables_row.addStretch()
        tables_layout.addLayout(tables_row)
        
        self.tables_list = QTableWidget()
        self.tables_list.setColumnCount(1)
        self.tables_list.setHorizontalHeaderLabels(["表名"])
        self.tables_list.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.tables_list.setMaximumHeight(200)
        tables_layout.addWidget(self.tables_list)
        
        layout.addWidget(tables_group)
    
    def _load_configs(self):
        configs = self.db_config_service.get_all_configs()
        
        self.config_combo.clear()
        self.config_combo.addItem("-- 请选择配置 --", None)
        
        for config in configs:
            self.config_combo.addItem(f"{config.name} ({config.host}/{config.database_name})", config.id)
    
    def _on_config_changed(self, index: int):
        config_id = self.config_combo.currentData()
        
        if config_id:
            config = self.db_config_service.get_config_by_id(config_id)
            if config:
                self.import_service = DbImportService(
                    host=config.host,
                    port=config.port,
                    username=config.username,
                    password=config.password
                )
                self.conn_info_label.setText(f"{config.host}:{config.port} / {config.username}")
                self.conn_info_label.setStyleSheet("color: #333;")
                self._refresh_databases()
        else:
            self.conn_info_label.setText("未选择配置")
            self.conn_info_label.setStyleSheet("color: #666;")
    
    def _goto_settings(self):
        from app.ui.main_window import MainWindow
        main_window = self.window()
        if hasattr(main_window, '_switch_page'):
            main_window._switch_page('settings')
    
    def _refresh_databases(self):
        dbs, error = self.import_service.get_databases()
        
        if error:
            QMessageBox.warning(self, "错误", f"获取数据库列表失败: {error}")
            return
        
        self.db_combo.clear()
        self.target_db_combo.clear()
        self.view_tables_combo.clear()
        
        for db in dbs:
            self.db_combo.addItem(db)
            self.target_db_combo.addItem(db)
            self.view_tables_combo.addItem(db)
    
    def _create_database(self):
        # 权限检查
        if not self.permission_checker.check_permission(PermissionCodes.OP_DB_IMPORT_RESTORE, self):
            return
        
        db_name = self.new_db_input.text().strip()
        if not db_name:
            QMessageBox.warning(self, "提示", "请输入数据库名称")
            return
        
        success, msg = self.import_service.create_database(db_name)
        
        if success:
            QMessageBox.information(self, "成功", msg)
            self._refresh_databases()
            self.target_db_combo.setCurrentText(db_name)
        else:
            QMessageBox.warning(self, "失败", msg)
    
    def _drop_database(self):
        # 权限检查
        if not self.permission_checker.check_permission(PermissionCodes.OP_DB_IMPORT_RESTORE, self):
            return
        
        db_name = self.db_combo.currentText()
        if not db_name:
            QMessageBox.warning(self, "提示", "请选择要删除的数据库")
            return
        
        reply = QMessageBox.question(
            self, "确认删除",
            f"确定要删除数据库 '{db_name}' 吗？\n此操作不可恢复！",
            QMessageBox.Yes | QMessageBox.No
        )
        
        if reply == QMessageBox.Yes:
            success, msg = self.import_service.drop_database(db_name)
            
            if success:
                QMessageBox.information(self, "成功", msg)
                self._refresh_databases()
            else:
                QMessageBox.warning(self, "失败", msg)
    
    def _select_sql_file(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self, "选择SQL文件", "", "SQL文件 (*.sql);;所有文件 (*.*)"
        )
        if file_path:
            self.sql_file_input.setText(file_path)
    
    def _start_import(self):
        # 权限检查
        if not self.permission_checker.check_permission(PermissionCodes.OP_DB_IMPORT_RESTORE, self):
            return
        
        config_id = self.config_combo.currentData()
        if not config_id:
            QMessageBox.warning(self, "提示", "请先选择数据库配置")
            return
        
        sql_file = self.sql_file_input.text()
        db_name = self.target_db_combo.currentText()
        
        if not sql_file:
            QMessageBox.warning(self, "提示", "请选择SQL文件")
            return
        
        if not db_name:
            QMessageBox.warning(self, "提示", "请选择或创建目标数据库")
            return
        
        self.import_service.charset = self.charset_combo.currentText()
        self.import_service.import_timeout = self.timeout_spin.value()
        
        self.import_btn.setEnabled(False)
        self.progress_bar.setValue(0)
        self.status_label.setText("准备导入...")
        
        self.import_worker = ImportWorker(self.import_service, sql_file, db_name)
        self.import_worker.progress.connect(self._on_import_progress)
        self.import_worker.finished.connect(self._on_import_finished)
        self.import_worker.start()
    
    def _on_import_progress(self, progress: int, message: str):
        self.progress_bar.setValue(progress)
        self.status_label.setText(message)
    
    def _on_import_finished(self, result: DbImportResult):
        self.import_btn.setEnabled(True)
        
        self.result_table.setItem(0, 1, QTableWidgetItem("成功" if result.success else "失败"))
        self.result_table.setItem(1, 1, QTableWidgetItem(self.target_db_combo.currentText()))
        self.result_table.setItem(2, 1, QTableWidgetItem(str(result.tables_count)))
        self.result_table.setItem(3, 1, QTableWidgetItem(result.error_detail or result.message))
        
        if result.success:
            QMessageBox.information(self, "成功", result.message)
            self._refresh_databases()
        else:
            QMessageBox.warning(self, "失败", result.message)
    
    def _view_tables(self):
        db_name = self.view_tables_combo.currentText()
        if not db_name:
            return
        
        tables, error = self.import_service.get_tables(db_name)
        
        if error:
            QMessageBox.warning(self, "错误", f"获取表列表失败: {error}")
            return
        
        self.tables_list.setRowCount(len(tables))
        for row, table in enumerate(tables):
            self.tables_list.setItem(row, 0, QTableWidgetItem(table))
