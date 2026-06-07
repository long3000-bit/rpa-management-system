from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, 
    QPushButton, QLineEdit, QFileDialog, QComboBox,
    QGroupBox, QTextEdit, QProgressBar, QTableWidget,
    QTableWidgetItem, QMessageBox, QDateEdit, QSpinBox,
    QDoubleSpinBox, QTabWidget, QSplitter, QFrame,
    QScrollArea, QHeaderView
)
from PySide6.QtCore import Qt, QDate, Signal, QThread
from PySide6.QtGui import QFont, QColor
from datetime import datetime
from decimal import Decimal
from pathlib import Path
import uuid
import logging

from app.core.ysb_excel_reader import YsbExcelReader, YsbExcelData
from app.core.database_config_service import DatabaseConfigService, InboundQueryService
from app.core.reconciliation_engine import ReconciliationEngine
from app.core.result_exporter import ResultExporter
from app.core.permission_checker import PermissionChecker, PermissionCodes
from app.core.data_permission_service import DataPermissionService
from app.ui.widgets.table_highlight import enable_table_highlight
from app.config import DATA_DIR


class ImportWorker(QThread):
    progress = Signal(int, str)
    finished = Signal(dict)
    
    def __init__(self, import_service, file_path, sheet_type, sheet_name, 
                 account_year, account_month, allow_duplicate=False, username: str = None):
        super().__init__()
        self.import_service = import_service
        self.file_path = file_path
        self.sheet_type = sheet_type
        self.sheet_name = sheet_name
        self.account_year = account_year
        self.account_month = account_month
        self.allow_duplicate = allow_duplicate
        self.username = username or 'admin'
    
    def run(self):
        try:
            result = self.import_service.import_from_excel(
                file_path=self.file_path,
                sheet_type=self.sheet_type,
                sheet_name=self.sheet_name,
                imported_by=self.username,
                allow_duplicate=self.allow_duplicate,
                account_year=self.account_year,
                account_month=self.account_month,
                progress_callback=self._update_progress
            )
            self.finished.emit(result)
        except Exception as e:
            self.finished.emit({
                'success': False,
                'error': str(e)
            })
    
    def _update_progress(self, value: int, message: str):
        self.progress.emit(value, message)


class ReconciliationWorker(QThread):
    progress = Signal(str, int)
    finished = Signal(bool, str, str)
    
    def __init__(self, ysb_data, inbound_rows, amount_tol, auto_threshold=80.0, suspected_threshold=60.0):
        super().__init__()
        self.ysb_data = ysb_data
        self.inbound_rows = inbound_rows
        self.amount_tol = amount_tol
        self.auto_threshold = auto_threshold
        self.suspected_threshold = suspected_threshold
        self.supplier_results = None
        self.detail_results = None
        self.product_results = None
        self.summary = None
    
    def run(self):
        try:
            self.progress.emit("执行对账中...", 50)
            
            engine = ReconciliationEngine(
                amount_tolerance=self.amount_tol,
                auto_match_threshold=self.auto_threshold,
                suspected_match_threshold=self.suspected_threshold
            )
            (
                self.supplier_results,
                self.detail_results,
                self.product_results,
                self.summary
            ) = engine.reconcile(
                self.ysb_data.items,
                self.inbound_rows
            )
            
            self.progress.emit("对账完成", 100)
            self.finished.emit(True, "对账完成", "")
        except Exception as e:
            self.finished.emit(False, "", str(e))


class ReconciliationPage(QWidget):
    
    def __init__(self, db, username: str = None, role_code: str = None):
        super().__init__()
        self.db = db
        self.username = username or 'admin'
        self.role_code = role_code or 'store_manager'
        self.db_config_service = DatabaseConfigService(db)
        self.data_permission_service = DataPermissionService(db)
        
        # 创建权限检查器
        self.permission_checker = PermissionChecker(db, self.username)
        
        self.ysb_data: YsbExcelData = None
        self.inbound_rows = []
        self.supplier_results = None
        self.detail_results = None
        self.product_results = None
        self.recon_summary = None
        self.result_file = ""
        self.recon_type = ""
        
        self._init_ui()
        self._load_db_configs()
        
        logging.info("准备加载日期设置（临时断开信号）...")
        
        try:
            self.period_start.dateChanged.disconnect(self._save_date_settings)
            self.period_end.dateChanged.disconnect(self._save_date_settings)
            self.inbound_start.dateChanged.disconnect(self._save_date_settings)
            self.inbound_end.dateChanged.disconnect(self._save_date_settings)
            
            self._load_date_settings()
            
            self.period_start.dateChanged.connect(self._save_date_settings)
            self.period_end.dateChanged.connect(self._save_date_settings)
            self.inbound_start.dateChanged.connect(self._save_date_settings)
            self.inbound_end.dateChanged.connect(self._save_date_settings)
            
            logging.info("✓ 日期设置加载完成，信号已重新连接")
        except Exception as e:
            logging.warning(f"日期加载过程异常: {e}")
            self._load_date_settings()
            logging.info("使用备用方式完成日期加载")
    
    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(10)
        
        file_group = QGroupBox("药师帮账单文件")
        file_layout = QVBoxLayout(file_group)
        
        file_row1 = QHBoxLayout()
        self.file_path_input = QLineEdit()
        self.file_path_input.setReadOnly(True)
        self.file_path_input.setPlaceholderText("选择药师帮对账单Excel文件")
        file_row1.addWidget(self.file_path_input)
        
        self.select_file_btn = QPushButton("选择文件")
        self.select_file_btn.clicked.connect(self._select_ysb_file)
        file_row1.addWidget(self.select_file_btn)
        
        self.preview_ysb_btn = QPushButton("预览数据")
        self.preview_ysb_btn.clicked.connect(self._preview_ysb_data)
        file_row1.addWidget(self.preview_ysb_btn)
        
        self.import_to_db_btn = QPushButton("导入到数据库")
        self.import_to_db_btn.clicked.connect(self._import_ysb_to_db)
        self.import_to_db_btn.setStyleSheet("background-color: #4CAF50; color: white;")
        file_row1.addWidget(self.import_to_db_btn)
        
        file_layout.addLayout(file_row1)
        
        file_row_data_source = QHBoxLayout()
        file_row_data_source.addWidget(QLabel("数据来源:"))
        
        self.data_source_combo = QComboBox()
        self.data_source_combo.addItem("优先使用数据库", "auto")
        self.data_source_combo.addItem("从数据库读取", "database")
        self.data_source_combo.addItem("从Excel文件读取", "excel")
        self.data_source_combo.setMinimumWidth(200)
        file_row_data_source.addWidget(self.data_source_combo)
        
        self.check_db_btn = QPushButton("检查数据库")
        self.check_db_btn.clicked.connect(self._check_database_data)
        file_row_data_source.addWidget(self.check_db_btn)
        
        file_row_data_source.addStretch()
        file_layout.addLayout(file_row_data_source)
        
        file_row2 = QHBoxLayout()
        file_row2.addWidget(QLabel("工作表:"))
        self.sheet_combo = QComboBox()
        self.sheet_combo.setMinimumWidth(200)
        self.sheet_combo.currentTextChanged.connect(self._on_sheet_changed)
        file_row2.addWidget(self.sheet_combo)
        file_row2.addStretch()
        file_layout.addLayout(file_row2)
        
        layout.addWidget(file_group)
        
        db_group = QGroupBox("入库数据来源（从配置中心选择）")
        db_layout = QHBoxLayout(db_group)
        
        db_layout.addWidget(QLabel("数据库配置:"))
        self.db_config_combo = QComboBox()
        self.db_config_combo.setMinimumWidth(250)
        self.db_config_combo.currentIndexChanged.connect(self._on_db_config_changed)
        db_layout.addWidget(self.db_config_combo)
        
        self.refresh_config_btn = QPushButton("刷新")
        self.refresh_config_btn.clicked.connect(self._load_db_configs)
        db_layout.addWidget(self.refresh_config_btn)
        
        self.test_db_btn = QPushButton("测试连接")
        self.test_db_btn.clicked.connect(self._test_db_connection)
        db_layout.addWidget(self.test_db_btn)
        
        self.goto_settings_btn = QPushButton("配置中心")
        self.goto_settings_btn.clicked.connect(self._goto_settings)
        db_layout.addWidget(self.goto_settings_btn)
        
        db_layout.addStretch()
        layout.addWidget(db_group)
        
        sql_group = QGroupBox("入库查询SQL")
        sql_layout = QVBoxLayout(sql_group)
        
        self.sql_input = QTextEdit()
        self.sql_input.setPlaceholderText("SELECT inbound_no, inbound_date, product_name, manufacturer, spec, quantity, unit_price, amount, barcode FROM inbound_table WHERE inbound_date BETWEEN '{start_date}' AND '{end_date}'")
        self.sql_input.setMaximumHeight(80)
        sql_layout.addWidget(self.sql_input)
        
        sql_btn_layout = QHBoxLayout()
        self.preview_sql_btn = QPushButton("预览SQL")
        self.preview_sql_btn.clicked.connect(self._preview_sql)
        sql_btn_layout.addWidget(self.preview_sql_btn)
        
        self.save_sql_btn = QPushButton("保存SQL")
        self.save_sql_btn.clicked.connect(self._save_sql)
        sql_btn_layout.addWidget(self.save_sql_btn)
        
        sql_btn_layout.addStretch()
        sql_layout.addLayout(sql_btn_layout)
        
        layout.addWidget(sql_group)
        
        rule_group = QGroupBox("对账规则")
        rule_layout = QHBoxLayout(rule_group)
        
        rule_layout.addWidget(QLabel("账期开始:"))
        self.period_start = QDateEdit()
        self.period_start.setCalendarPopup(True)
        self.period_start.setDate(QDate.currentDate().addMonths(-1))
        self.period_start.dateChanged.connect(self._save_date_settings)
        rule_layout.addWidget(self.period_start)
        
        rule_layout.addWidget(QLabel("账期结束:"))
        self.period_end = QDateEdit()
        self.period_end.setCalendarPopup(True)
        self.period_end.setDate(QDate.currentDate())
        self.period_end.dateChanged.connect(self._save_date_settings)
        rule_layout.addWidget(self.period_end)
        
        rule_layout.addWidget(QLabel("入库开始:"))
        self.inbound_start = QDateEdit()
        self.inbound_start.setCalendarPopup(True)
        self.inbound_start.setDate(QDate.currentDate().addMonths(-1))
        self.inbound_start.dateChanged.connect(self._save_date_settings)
        rule_layout.addWidget(self.inbound_start)
        
        rule_layout.addWidget(QLabel("入库结束:"))
        self.inbound_end = QDateEdit()
        self.inbound_end.setCalendarPopup(True)
        self.inbound_end.setDate(QDate.currentDate())
        self.inbound_end.dateChanged.connect(self._save_date_settings)
        rule_layout.addWidget(self.inbound_end)
        
        self.save_date_btn = QPushButton("保存日期")
        self.save_date_btn.setToolTip("手动保存当前选择的日期到数据库")
        self.save_date_btn.clicked.connect(self._manual_save_dates)
        self.save_date_btn.setFixedWidth(80)
        rule_layout.addWidget(self.save_date_btn)
        
        self.show_settings_btn = QPushButton("查看设置")
        self.show_settings_btn.setToolTip("查看数据库中保存的所有日期设置")
        self.show_settings_btn.clicked.connect(self._show_saved_settings)
        self.show_settings_btn.setFixedWidth(80)
        rule_layout.addWidget(self.show_settings_btn)
        
        rule_layout.addStretch()
        layout.addWidget(rule_group)
        
        tol_layout = QHBoxLayout()
        tol_layout.addWidget(QLabel("供应商金额误差:"))
        self.supplier_amount_tol = QDoubleSpinBox()
        self.supplier_amount_tol.setValue(1.0)
        self.supplier_amount_tol.setDecimals(2)
        self.supplier_amount_tol.setSingleStep(0.1)
        tol_layout.addWidget(self.supplier_amount_tol)
        
        tol_layout.addWidget(QLabel("商品金额误差:"))
        self.product_amount_tol = QDoubleSpinBox()
        self.product_amount_tol.setValue(1.0)
        self.product_amount_tol.setDecimals(2)
        self.product_amount_tol.setSingleStep(0.1)
        tol_layout.addWidget(self.product_amount_tol)
        
        tol_layout.addWidget(QLabel("数量误差:"))
        self.quantity_tol = QDoubleSpinBox()
        self.quantity_tol.setValue(1.0)
        self.quantity_tol.setDecimals(2)
        self.quantity_tol.setSingleStep(1.0)
        tol_layout.addWidget(self.quantity_tol)
        
        tol_layout.addWidget(QLabel("自动匹配阈值:"))
        self.auto_threshold = QDoubleSpinBox()
        self.auto_threshold.setValue(85.0)
        self.auto_threshold.setDecimals(0)
        self.auto_threshold.setRange(0, 100)
        tol_layout.addWidget(self.auto_threshold)
        
        tol_layout.addWidget(QLabel("疑似匹配阈值:"))
        self.suspected_threshold = QDoubleSpinBox()
        self.suspected_threshold.setValue(70.0)
        self.suspected_threshold.setDecimals(0)
        self.suspected_threshold.setRange(0, 100)
        tol_layout.addWidget(self.suspected_threshold)
        
        tol_layout.addStretch()
        layout.addLayout(tol_layout)
        
        exec_group = QGroupBox("执行")
        exec_layout = QVBoxLayout(exec_group)
        
        btn_layout = QHBoxLayout()
        
        self.supplier_recon_btn = QPushButton("供应商对账")
        self.supplier_recon_btn.clicked.connect(self._execute_supplier_reconciliation)
        btn_layout.addWidget(self.supplier_recon_btn)
        
        btn_layout.addWidget(QLabel("商品对账模式:"))
        self.product_recon_mode_combo = QComboBox()
        self.product_recon_mode_combo.addItem("全量供应商核对商品", "all")
        self.product_recon_mode_combo.addItem("按异常供应商核对商品", "diff_only")
        btn_layout.addWidget(self.product_recon_mode_combo)
        
        self.product_recon_btn = QPushButton("供应商商品对账")
        self.product_recon_btn.clicked.connect(self._execute_product_reconciliation)
        btn_layout.addWidget(self.product_recon_btn)
        
        self.export_btn = QPushButton("导出结果")
        self.export_btn.clicked.connect(self._export_result)
        self.export_btn.setEnabled(False)
        btn_layout.addWidget(self.export_btn)
        
        btn_layout.addStretch()
        exec_layout.addLayout(btn_layout)
        
        progress_layout = QHBoxLayout()
        self.progress_bar = QProgressBar()
        progress_layout.addWidget(self.progress_bar)
        
        self.status_label = QLabel("就绪")
        progress_layout.addWidget(self.status_label)
        exec_layout.addLayout(progress_layout)
        
        layout.addWidget(exec_group)
        
        result_group = QGroupBox("结果概览")
        result_layout = QVBoxLayout(result_group)
        
        self.result_table = QTableWidget()
        self.result_table.setColumnCount(4)
        self.result_table.setHorizontalHeaderLabels(["指标", "数值", "指标", "数值"])
        self.result_table.setRowCount(5)
        self.result_table.horizontalHeader().setStretchLastSection(True)
        enable_table_highlight(self.result_table)
        result_layout.addWidget(self.result_table)
        
        layout.addWidget(result_group)
    
    def _load_date_settings(self):
        logging.info(f"===========================================")
        logging.info(f"开始加载日期设置...")
        logging.info(f"===========================================")
        
        try:
            test_key = '_date_settings_test'
            test_value = 'test_ok'
            self.db.set_setting(test_key, test_value)
            read_back = self.db.get_setting(test_key)
            
            if read_back == test_value:
                logging.info(f"✓ 数据库读写测试通过")
            else:
                logging.error(f"❌ 数据库读写测试失败: 写入={test_value}, 读取={read_back}")
            
            settings_to_load = [
                ('recon_period_start', 'period_start', '账期开始'),
                ('recon_period_end', 'period_end', '账期结束'),
                ('recon_inbound_start', 'inbound_start', '入库开始'),
                ('recon_inbound_end', 'inbound_end', '入库结束'),
            ]
            
            loaded_count = 0
            for setting_key, attr_name, display_name in settings_to_load:
                value = self.db.get_setting(setting_key)
                
                if value:
                    date = QDate.fromString(value, "yyyy-MM-dd")
                    if date.isValid():
                        getattr(self, attr_name).setDate(date)
                        loaded_count += 1
                        logging.info(f"✓ 加载 {display_name}: {value}")
                    else:
                        logging.warning(f"✗ {display_name} 值无效: {value}")
                else:
                    logging.info(f"○ {display_name}: 未保存过 (使用默认值)")
            
            logging.info(f"日期设置加载完成: 成功加载 {loaded_count}/4 个")
            
            logging.info(f"当前日期选择器值:")
            logging.info(f"  账期开始: {self.period_start.date().toString('yyyy-MM-dd')}")
            logging.info(f"  账期结束: {self.period_end.date().toString('yyyy-MM-dd')}")
            logging.info(f"  入库开始: {self.inbound_start.date().toString('yyyy-MM-dd')}")
            logging.info(f"  入库结束: {self.inbound_end.date().toString('yyyy-MM-dd')}")
            
        except Exception as e:
            logging.error(f"❌ 加载日期设置失败: {e}")
            import traceback
            logging.error(traceback.format_exc())
    
    def _save_date_settings(self):
        logging.info(f"--- 保存日期设置 ---")
        
        try:
            settings_to_save = [
                ('recon_period_start', self.period_start, '账期开始'),
                ('recon_period_end', self.period_end, '账期结束'),
                ('recon_inbound_start', self.inbound_start, '入库开始'),
                ('recon_inbound_end', self.inbound_end, '入库结束'),
            ]
            
            saved_count = 0
            for setting_key, date_edit, display_name in settings_to_save:
                date_value = date_edit.date().toString("yyyy-MM-dd")
                self.db.set_setting(setting_key, date_value)
                saved_count += 1
                logging.info(f"✓ 保存 {display_name}: {date_value}")
            
            logging.info(f"日期设置保存完成: {saved_count}/4 个")
            
        except Exception as e:
            logging.error(f"❌ 保存日期设置失败: {e}")
            import traceback
            logging.error(traceback.format_exc())
    
    def _manual_save_dates(self):
        logging.info(f"===========================================")
        logging.info(f"手动保存日期设置")
        logging.info(f"===========================================")
        
        self._save_date_settings()
        
        QMessageBox.information(self, "成功", 
            f"日期已保存到数据库！\n\n"
            f"账期开始: {self.period_start.date().toString('yyyy-MM-dd')}\n"
            f"账期结束: {self.period_end.date().toString('yyyy-MM-dd')}\n"
            f"入库开始: {self.inbound_start.date().toString('yyyy-MM-dd')}\n"
            f"入库结束: {self.inbound_end.date().toString('yyyy-MM-dd')}\n\n"
            f"下次打开界面时会自动加载这些日期。")
    
    def _show_saved_settings(self):
        settings = [
            ('recon_period_start', '账期开始'),
            ('recon_period_end', '账期结束'),
            ('recon_inbound_start', '入库开始'),
            ('recon_inbound_end', '入库结束'),
        ]
        
        message = "数据库中保存的日期设置：\n\n"
        
        for key, name in settings:
            value = self.db.get_setting(key)
            if value:
                message += f"✓ {name}: {value}\n"
            else:
                message += f"○ {name}: (未保存)\n"
        
        message += "\n当前界面显示的日期：\n\n"
        message += f"• 账期开始: {self.period_start.date().toString('yyyy-MM-dd')}\n"
        message += f"• 账期结束: {self.period_end.date().toString('yyyy-MM-dd')}\n"
        message += f"• 入库开始: {self.inbound_start.date().toString('yyyy-MM-dd')}\n"
        message += f"• 入库结束: {self.inbound_end.date().toString('yyyy-MM-dd')}"
        
        QMessageBox.information(self, "日期设置详情", message)
        
        logging.info("用户点击了'查看设置'按钮")
        for key, name in settings:
            value = self.db.get_setting(key)
            logging.info(f"  数据库 - {name}: {value or '(未保存)'}")
    
    def _load_db_configs(self):
        configs = self.db_config_service.get_all_configs()
        self.db_config_combo.clear()
        self.db_config_combo.addItem("-- 请选择配置 --", None)
        
        for config in configs:
            self.db_config_combo.addItem(f"{config.name} ({config.host}/{config.database_name})", config.id)
        
        if configs:
            self.db_config_combo.setCurrentIndex(1)
    
    def _on_db_config_changed(self, index: int):
        config_id = self.db_config_combo.currentData()
        
        if config_id:
            config = self.db_config_service.get_config_by_id(config_id)
            if config and config.inbound_sql:
                self.sql_input.setPlainText(config.inbound_sql)
    
    def _goto_settings(self):
        main_window = self.window()
        if hasattr(main_window, '_switch_page'):
            main_window._switch_page('settings')
    
    def _select_ysb_file(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self, "选择药师帮对账单", "", "Excel文件 (*.xlsx *.xls)"
        )
        if file_path:
            self.file_path_input.setText(file_path)
            self._load_sheet_names(file_path)
    
    def _load_sheet_names(self, file_path: str):
        sheet_names, error = YsbExcelReader.get_sheet_names(file_path)
        
        if error:
            QMessageBox.warning(self, "错误", f"无法读取Excel文件: {error}")
            return
        
        self.sheet_combo.clear()
        self.sheet_combo.addItems(sheet_names)
        
        preferred_sheets = ["本月支付账单明细", "明细"]
        for preferred in preferred_sheets:
            if preferred in sheet_names:
                self.sheet_combo.setCurrentText(preferred)
                break
        
        self._load_ysb_file(file_path)
    
    def _load_ysb_file(self, file_path: str):
        sheet_name = self.sheet_combo.currentText() if self.sheet_combo.count() > 0 else None
        reader = YsbExcelReader(file_path, sheet_name=sheet_name)
        self.ysb_data = reader.read()
        
        if self.ysb_data.error_message:
            QMessageBox.warning(self, "错误", self.ysb_data.error_message)
            self.status_label.setText("文件加载失败")
        elif self.ysb_data.total_rows == 0:
            QMessageBox.warning(self, "提示", f"文件已读取，但未找到数据。\n工作表: {self.ysb_data.sheet_name}\n请确认Excel中包含商品明细")
            self.status_label.setText("未找到数据")
        else:
            self.status_label.setText(f"已加载 {self.ysb_data.total_rows} 条药师帮数据 (工作表: {self.ysb_data.sheet_name})")
            QMessageBox.information(self, "成功", f"成功加载 {self.ysb_data.total_rows} 条药师帮数据\n工作表: {self.ysb_data.sheet_name}")
    
    def _select_account_period(self):
        from PySide6.QtWidgets import QDialog, QFormLayout, QDialogButtonBox
        
        dialog = QDialog(self)
        dialog.setWindowTitle("选择核算年月")
        dialog.setMinimumWidth(300)
        
        layout = QFormLayout(dialog)
        
        current_year = datetime.now().year
        current_month = datetime.now().month
        
        year_combo = QComboBox()
        for y in range(current_year - 2, current_year + 2):
            year_combo.addItem(str(y), y)
        year_combo.setCurrentText(str(current_year))
        layout.addRow("核算年:", year_combo)
        
        month_combo = QComboBox()
        for m in range(1, 13):
            month_combo.addItem(f"{m}月", m)
        month_combo.setCurrentText(f"{current_month}月")
        layout.addRow("核算月:", month_combo)
        
        info_label = QLabel("说明: 同一核算年月只能有一个批次的数据\n导入时将删除该核算年月的旧数据")
        info_label.setStyleSheet("color: gray; font-size: 11px;")
        layout.addRow(info_label)
        
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addRow(buttons)
        
        if dialog.exec() == QDialog.Accepted:
            return year_combo.currentData(), month_combo.currentData()
        
        return None, None
    
    def _on_sheet_changed(self, sheet_name: str):
        file_path = self.file_path_input.text()
        if file_path and sheet_name:
            self._load_ysb_file(file_path)
    
    def _import_ysb_to_db(self):
        # 权限检查
        if not self.permission_checker.check_permission(PermissionCodes.OP_YSB_RECONCILE_IMPORT_EXCEL, self):
            return
        
        file_path = self.file_path_input.text()
        if not file_path:
            QMessageBox.warning(self, "提示", "请先选择药师帮对账单文件")
            return
        
        if not Path(file_path).exists():
            QMessageBox.warning(self, "提示", "文件不存在，请重新选择")
            return
        
        account_year, account_month = self._select_account_period()
        if account_year is None or account_month is None:
            return
        
        msg = QMessageBox(self)
        msg.setWindowTitle("选择导入范围")
        msg.setText("请选择要导入的工作表范围：")
        msg.setInformativeText(
            f"文件: {Path(file_path).name}\n"
            f"当前工作表: {self.sheet_combo.currentText()}\n"
            f"共有 {self.sheet_combo.count()} 个工作表\n"
            f"核算年月: {account_year}年{account_month}月"
        )
        
        btn_current = msg.addButton(f"仅导入当前工作表 ({self.sheet_combo.currentText()})", QMessageBox.ButtonRole.AcceptRole)
        btn_all = msg.addButton("导入所有工作表", QMessageBox.ButtonRole.AcceptRole)
        btn_cancel = msg.addButton("取消", QMessageBox.ButtonRole.RejectRole)
        
        msg.exec()
        
        clicked_button = msg.clickedButton()
        
        if clicked_button == btn_cancel:
            return
        
        import_all = (clicked_button == btn_all)
        
        self._import_sheets(file_path, account_year, account_month, import_all)
    
    def _import_sheets(self, file_path: str, account_year: int, account_month: int, import_all: bool):
        from app.core.ysb_data_import_service import YsbDataImportService
        
        self.import_service = YsbDataImportService(self.db)
        
        if import_all:
            self._import_all_sheets(file_path, account_year, account_month)
        else:
            sheet_name = self.sheet_combo.currentText() if self.sheet_combo.count() > 0 else None
            sheet_type = "detail" if "明细" in sheet_name else "supplier" if "支付订单" in sheet_name else "auto"
            self._start_import_worker(file_path, sheet_type, sheet_name, account_year, account_month)
    
    def _import_all_sheets(self, file_path: str, account_year: int, account_month: int):
        self.sheet_names = [self.sheet_combo.itemText(i) for i in range(self.sheet_combo.count())]
        self.current_sheet_idx = 0
        self.import_results = []
        self.total_rows = 0
        
        self._import_next_sheet(file_path, account_year, account_month)
    
    def _import_next_sheet(self, file_path: str, account_year: int, account_month: int):
        if self.current_sheet_idx >= len(self.sheet_names):
            self._show_import_results(file_path)
            return
        
        sheet_name = self.sheet_names[self.current_sheet_idx]
        sheet_type = "detail" if "明细" in sheet_name else "supplier" if "支付订单" in sheet_name else "auto"
        
        self.status_label.setText(f"正在导入工作表 {self.current_sheet_idx+1}/{len(self.sheet_names)}: {sheet_name}...")
        
        self._start_import_worker(file_path, sheet_type, sheet_name, account_year, account_month, for_all_sheets=True)
    
    def _start_import_worker(self, file_path: str, sheet_type: str, sheet_name: str,
                             account_year: int, account_month: int, allow_duplicate: bool = False, for_all_sheets: bool = False):
        self.import_worker = ImportWorker(
            self.import_service, file_path, sheet_type, sheet_name,
            account_year, account_month, allow_duplicate, self.username
        )
        self.import_worker.progress.connect(self._on_import_progress)
        self.import_worker.finished.connect(lambda result: self._on_import_finished(result, file_path, account_year, account_month, for_all_sheets))
        self.import_worker.start()
    
    def _on_import_progress(self, value: int, message: str):
        self.progress_bar.setValue(value)
        self.status_label.setText(message)
    
    def _on_import_finished(self, result: dict, file_path: str, account_year: int, account_month: int, for_all_sheets: bool):
        if not result['success'] and result.get('error') == 'duplicate':
            existing = result.get('existing_batch', {})
            reply = QMessageBox.question(
                self,
                "检测到重复导入",
                f"工作表已导入过：\n\n"
                f"批次ID: {existing.get('batch_id', '')[:8]}...\n"
                f"导入时间: {existing.get('imported_at', '')}\n"
                f"记录数: {existing.get('total_rows', 0)} 条\n\n"
                f"是否重新导入（将删除旧数据）？",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No | QMessageBox.StandardButton.Cancel
            )
            
            if reply == QMessageBox.StandardButton.Yes:
                old_batch_id = existing.get('batch_id')
                if old_batch_id:
                    self.import_service.delete_batch(old_batch_id)
                    logging.info(f"✓ 删除旧批次: {old_batch_id}")
                
                sheet_name = existing.get('sheet_name')
                sheet_type = "detail" if "明细" in sheet_name else "supplier" if "支付订单" in sheet_name else "auto"
                self._start_import_worker(file_path, sheet_type, sheet_name, account_year, account_month, allow_duplicate=True, for_all_sheets=for_all_sheets)
                return
            elif reply == QMessageBox.StandardButton.No:
                result = {
                    'success': True,
                    'batch_id': existing.get('batch_id'),
                    'total_rows': existing.get('total_rows', 0),
                    'sheet_name': existing.get('sheet_name'),
                    'skipped': True
                }
            else:
                result = {
                    'success': False,
                    'error': 'cancelled',
                    'error_message': '用户取消导入'
                }
        
        if for_all_sheets:
            self.import_results.append({
                'sheet_name': result.get('sheet_name', ''),
                'result': result
            })
            
            if result['success']:
                self.total_rows += result.get('total_rows', 0)
            
            self.current_sheet_idx += 1
            self._import_next_sheet(file_path, account_year, account_month)
        else:
            if result['success']:
                self.progress_bar.setValue(100)
                self.status_label.setText(f"✓ 导入成功: {result['total_rows']} 条数据")
                
                QMessageBox.information(
                    self,
                    "导入成功",
                    f"药师帮数据已成功导入数据库！\n\n"
                    f"批次ID: {result['batch_id']}\n"
                    f"文件名: {result['file_name']}\n"
                    f"工作表: {result['sheet_name']}\n"
                    f"数据类型: {result['sheet_type']}\n"
                    f"总记录数: {result['total_rows']}\n\n"
                    f"数据已保存到本地数据库，可随时查看。"
                )
            else:
                self.progress_bar.setValue(0)
                self.status_label.setText("导入失败")
                QMessageBox.critical(self, "导入失败", f"导入数据失败:\n{result.get('error', '未知错误')}")
    
    def _show_import_results(self, file_path: str):
        self.progress_bar.setValue(100)
        self.status_label.setText(f"✓ 全部导入完成: {self.total_rows} 条数据")
        
        success_sheets = [r for r in self.import_results if r['result']['success'] and not r['result'].get('skipped')]
        skipped_sheets = [r for r in self.import_results if r['result']['success'] and r['result'].get('skipped')]
        failed_sheets = [r for r in self.import_results if not r['result']['success']]
        
        msg_text = f"药师帮数据导入完成！\n\n"
        msg_text += f"文件名: {Path(file_path).name}\n"
        msg_text += f"新导入: {len(success_sheets)} 个工作表\n"
        msg_text += f"跳过: {len(skipped_sheets)} 个工作表\n"
        msg_text += f"总记录数: {self.total_rows} 条\n\n"
        
        if success_sheets:
            msg_text += "新导入的工作表:\n"
            for r in success_sheets:
                msg_text += f"  ✓ {r['sheet_name']}: {r['result']['total_rows']} 条\n"
        
        if skipped_sheets:
            msg_text += "\n跳过的工作表（已存在）:\n"
            for r in skipped_sheets:
                msg_text += f"  ○ {r['sheet_name']}: {r['result']['total_rows']} 条\n"
        
        if failed_sheets:
            msg_text += "\n失败的工作表:\n"
            for r in failed_sheets:
                msg_text += f"  ✗ {r['sheet_name']}: {r['result'].get('error_message', r['result'].get('error', '未知错误'))}\n"
        
        msg_text += "\n数据已保存到本地数据库，可随时查看。"
        
        QMessageBox.information(self, "导入完成", msg_text)
    
    def _check_database_data(self):
        try:
            from app.core.ysb_data_query_service import YsbDataQueryService
            
            query_service = YsbDataQueryService(self.db)
            batch_list = query_service.get_batch_list(limit=10)
            
            if not batch_list:
                QMessageBox.information(
                    self,
                    "数据库检查",
                    "数据库中没有找到导入的药师帮数据。\n\n"
                    "请先点击'导入到数据库'按钮导入数据。"
                )
                return
            
            msg_text = "数据库中的药师帮数据批次：\n\n"
            
            for idx, batch in enumerate(batch_list, 1):
                imported_at = batch['imported_at']
                if imported_at:
                    try:
                        dt = datetime.fromisoformat(imported_at)
                        imported_at = dt.strftime("%Y-%m-%d %H:%M")
                    except:
                        pass
                
                msg_text += f"{idx}. {batch['file_name']}\n"
                msg_text += f"   导入时间: {imported_at}\n"
                msg_text += f"   明细数据: {batch['detail_count']} 条\n"
                msg_text += f"   供应商汇总: {batch['supplier_count']} 条\n\n"
            
            msg_text += f"\n最新批次将用于对账。"
            
            QMessageBox.information(self, "数据库检查", msg_text)
            
        except Exception as e:
            QMessageBox.critical(self, "错误", f"检查数据库失败:\n{str(e)}")
    
    def _load_ysb_data_for_reconciliation(self, required_type: str = "auto") -> bool:
        data_source = self.data_source_combo.currentData()
        
        if data_source in ["auto", "database"]:
            try:
                from app.core.ysb_data_query_service import YsbDataQueryService
                
                query_service = YsbDataQueryService(self.db)
                period_start = self.period_start.date().toString("yyyy-MM-dd")
                period_end = self.period_end.date().toString("yyyy-MM-dd")
                db_data = query_service.get_data_by_business_date_range(
                    period_start,
                    period_end,
                    required_type
                )
                
                if db_data:
                    has_data = False
                    
                    if required_type in ["auto", "detail"] and db_data.items:
                        has_data = True
                    elif required_type in ["auto", "supplier"] and db_data.supplier_summaries:
                        has_data = True
                    
                    if has_data:
                        self.ysb_data = db_data
                        logging.info(f"✓ 从数据库加载药师帮数据成功")
                        return True
                    else:
                        logging.warning(f"数据库批次存在但没有{required_type}类型数据")
                        if data_source == "database":
                            QMessageBox.warning(
                                self,
                                "提示",
                                f"数据库中没有找到{required_type}类型的数据。\n\n"
                                f"请先导入数据或选择其他数据来源。"
                            )
                            return False
                        else:
                            logging.info(f"数据源为auto，尝试从Excel加载...")
                else:
                    if data_source == "database":
                        QMessageBox.warning(
                            self,
                            "提示",
                            "数据库中没有找到药师帮数据。\n\n"
                            "请先点击'导入到数据库'按钮导入数据。"
                        )
                        return False
                    else:
                        logging.info(f"数据库无数据，数据源为auto，尝试从Excel加载...")
                    
            except Exception as e:
                logging.error(f"从数据库加载数据失败: {e}")
                if data_source == "database":
                    QMessageBox.critical(self, "错误", f"从数据库加载数据失败:\n{str(e)}")
                    return False
                else:
                    logging.info(f"数据库加载失败，数据源为auto，尝试从Excel加载...")
        
        if data_source in ["auto", "excel"]:
            file_path = self.file_path_input.text()
            
            if not file_path:
                if data_source == "excel":
                    QMessageBox.warning(self, "提示", "请先选择药师帮对账单文件")
                    return False
                else:
                    logging.warning(f"数据源为auto但未选择Excel文件，无法加载数据")
                    QMessageBox.warning(
                        self,
                        "提示",
                        f"数据库中存在数据批次，但没有供应商汇总数据。\n\n"
                        f"可能原因：\n"
                        f"1. 导入的Excel文件只有明细数据，没有供应商汇总工作表\n"
                        f"2. 导入时未选择供应商汇总类型\n\n"
                        f"请选择以下操作之一：\n"
                        f"1. 导入包含供应商汇总数据的Excel文件到数据库\n"
                        f"2. 选择Excel文件（包含供应商汇总）作为数据来源"
                    )
                    return False
            
            if not Path(file_path).exists():
                QMessageBox.warning(self, "提示", "Excel文件不存在，请重新选择")
                return False
            
            self.status_label.setText("从Excel读取数据...")
            self.progress_bar.setValue(5)
            
            reader = YsbExcelReader(file_path, sheet_type=required_type)
            self.ysb_data = reader.read()
            
            if self.ysb_data.error_message:
                QMessageBox.warning(self, "错误", f"读取Excel失败: {self.ysb_data.error_message}")
                return False
            
            logging.info(f"✓ 从Excel加载药师帮数据成功")
            return True
        
        return False
    
    def _preview_ysb_data(self):
        if not self.ysb_data:
            QMessageBox.warning(self, "提示", "请先选择药师帮对账单文件")
            return
        
        if self.ysb_data.error_message:
            QMessageBox.warning(self, "错误", f"文件加载失败:\n{self.ysb_data.error_message}")
            return
        
        dialog = QWidget(self, Qt.Dialog)
        dialog.setWindowTitle(f"药师帮数据预览 - {self.ysb_data.sheet_name}")
        dialog.setMinimumSize(1200, 600)
        
        layout = QVBoxLayout(dialog)
        
        logging.info(f"===========================================")
        logging.info(f"预览药师帮数据")
        logging.info(f"  工作表: {self.ysb_data.sheet_name}")
        logging.info(f"  明细数据条数: {len(self.ysb_data.items) if self.ysb_data.items else 0}")
        logging.info(f"  供应商汇总条数: {len(self.ysb_data.supplier_summaries) if self.ysb_data.supplier_summaries else 0}")
        logging.info(f"===========================================")
        
        if self.ysb_data.supplier_summaries and len(self.ysb_data.supplier_summaries) > 0:
            info_label = QLabel(
                f"<b>工作表:</b> {self.ysb_data.sheet_name} | "
                f"<b>类型:</b> 供应商汇总 | "
                f"<b>共:</b> {len(self.ysb_data.supplier_summaries)} 条供应商记录"
            )
            info_label.setStyleSheet("color: #2196F3; padding: 5px; background-color: #E3F2FD; border-radius: 3px;")
            layout.addWidget(info_label)
            
            table = QTableWidget()
            
            supplier_fields = [
                ("企业名称", "ysb_company_name"),
                ("供应商", "ysb_supplier_name"),
                ("显示名称", "supplier_display_name"),
                ("实际支付金额", "actual_payment_amount"),
                ("订单数", "order_count"),
            ]
            
            items = self.ysb_data.supplier_summaries
            
            total_amount = Decimal("0")
            non_zero_count = 0
            for item in items:
                amount = getattr(item, 'actual_payment_amount', Decimal("0"))
                total_amount += amount
                if amount > Decimal("0"):
                    non_zero_count += 1
            
            summary_text = (
                f"<b>数据统计:</b> 总记录数={len(items)} | "
                f"有金额记录={non_zero_count} | "
                f"零金额记录={len(items) - non_zero_count} | "
                f"总金额={total_amount}"
            )
            
            if total_amount == Decimal("0") and len(items) > 0:
                summary_text += f" | <span style='color:red;'>⚠️ 所有金额都为0！</span>"
            
            summary_label = QLabel(summary_text)
            summary_label.setStyleSheet("color: #666; padding: 5px; font-size: 11px; background-color: #FFF9C4;")
            layout.addWidget(summary_label)
            
            table.setColumnCount(len(supplier_fields))
            table.setHorizontalHeaderLabels([label for label, _ in supplier_fields])
            table.setRowCount(len(items))
            table.setAlternatingRowColors(True)
            enable_table_highlight(table)
            
            for row_idx, item in enumerate(items):
                for col_idx, (label, field) in enumerate(supplier_fields):
                    value = getattr(item, field, None)
                    
                    if field == "actual_payment_amount":
                        if value is None or value == Decimal("0"):
                            text = "0 ⚠️"
                            item_widget = QTableWidgetItem(text)
                            item_widget.setBackground(QColor("#FFCDD2"))
                            item_widget.setForeground(QColor("#B71C1C"))
                        else:
                            text = str(value)
                            item_widget = QTableWidgetItem(text)
                            item_widget.setBackground(QColor("#C8E6C9"))
                            item_widget.setForeground(QColor("#1B5E20"))
                        
                        table.setItem(row_idx, col_idx, item_widget)
                        logging.info(f"  供应商行{row_idx + 1}: 名称={getattr(item, 'supplier_display_name', '')}, 金额={value}")
                    elif field == "supplier_display_name":
                        text = str(value) if value else ""
                        table.setItem(row_idx, col_idx, QTableWidgetItem(text))
                    else:
                        text = str(value) if value else ""
                        table.setItem(row_idx, col_idx, QTableWidgetItem(text))
            
            table.resizeColumnsToContents()
            
            scroll_area = QScrollArea()
            scroll_area.setWidget(table)
            scroll_area.setWidgetResizable(True)
            scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
            scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
            layout.addWidget(scroll_area)
            
            debug_btn = QPushButton("显示原始数据详情")
            debug_btn.clicked.connect(lambda: self._show_ysb_debug_info())
            debug_btn.setToolTip("查看每条记录的完整字段值")
            layout.addWidget(debug_btn)
            
            close_btn = QPushButton("关闭")
            close_btn.clicked.connect(dialog.close)
            layout.addWidget(close_btn)
            
            logging.info(f"✓ 药师帮供应商数据预览完成:")
            logging.info(f"   总记录: {len(items)}")
            logging.info(f"   有金额: {non_zero_count}")
            logging.info(f"   总金额: {total_amount}")
            
        elif self.ysb_data.items and len(self.ysb_data.items) > 0:
            info_label = QLabel(f"工作表: {self.ysb_data.sheet_name} | 共 {self.ysb_data.total_rows} 条数据 (显示前100条)")
            layout.addWidget(info_label)
            
            table = QTableWidget()
        
        display_fields = [
            ("订单号", "ysb_order_no"),
            ("订单类型", "order_type"),
            ("药店名称", "ysb_store_name"),
            ("供应商", "ysb_supplier_name"),
            ("商品名称", "product_name"),
            ("厂家", "manufacturer"),
            ("规格", "spec"),
            ("单位", "unit"),
            ("条形码", "barcode"),
            ("批号", "batch_no"),
            ("单价", "unit_price"),
            ("折后价", "discount_price"),
            ("数量", "quantity"),
            ("下单数量", "order_quantity"),
            ("退款数量", "refund_quantity"),
            ("金额", "total_amount"),
            ("折后金额", "discount_amount"),
            ("运费", "freight"),
            ("采购时间", "purchase_time"),
        ]
        
        items = self.ysb_data.items[:100]
        
        has_data = {}
        for item in items:
            for label, field in display_fields:
                val = getattr(item, field, None)
                if val is not None and str(val).strip() and str(val) != "0":
                    has_data[field] = True
        
        visible_fields = [(label, field) for label, field in display_fields if has_data.get(field, False)]
        
        if not visible_fields:
            visible_fields = display_fields[:8]
        
        table.setColumnCount(len(visible_fields))
        table.setHorizontalHeaderLabels([label for label, _ in visible_fields])
        table.setRowCount(len(items))
        
        for row, item in enumerate(items):
            for col, (label, field) in enumerate(visible_fields):
                value = getattr(item, field, None)
                if value is None:
                    text = ""
                elif hasattr(value, '__class__') and value.__class__.__name__ == 'Decimal':
                    text = f"{value:.2f}"
                else:
                    text = str(value)
                table.setItem(row, col, QTableWidgetItem(text))
        
        table.resizeColumnsToContents()
        enable_table_highlight(table)
        layout.addWidget(table)
        
        close_btn = QPushButton("关闭")
        close_btn.clicked.connect(dialog.close)
        layout.addWidget(close_btn)
        
        dialog.show()

    
    def _test_db_connection(self):
        config_id = self.db_config_combo.currentData()
        if not config_id:
            QMessageBox.warning(self, "提示", "请先选择数据库配置")
            return
        
        config = self.db_config_service.get_config_by_id(config_id)
        if config:
            success, msg = self.db_config_service.test_connection(config)
            if success:
                QMessageBox.information(self, "成功", msg)
            else:
                QMessageBox.warning(self, "失败", msg)
    
    def _preview_sql(self):
        config_id = self.db_config_combo.currentData()
        if not config_id:
            QMessageBox.warning(self, "提示", "请先选择数据库配置")
            return
        
        config = self.db_config_service.get_config_by_id(config_id)
        sql = self.sql_input.toPlainText()
        
        if not sql:
            QMessageBox.warning(self, "提示", "请输入SQL查询语句")
            return
        
        start_date = self.inbound_start.date().toString("yyyy-MM-dd")
        end_date = self.inbound_end.date().toString("yyyy-MM-dd")
        
        logging.info(f"===========================================")
        logging.info(f"预览SQL - 日期范围: {start_date} ~ {end_date}")
        logging.info(f"===========================================")
        
        service = InboundQueryService(config)
        rows, error = service.preview(sql, start_date, end_date, limit=None)
        
        if error:
            QMessageBox.warning(self, "错误", error)
            return
        
        if not rows:
            QMessageBox.information(self, "提示", 
                f"查询结果为空！\n\n"
                f"日期范围: {start_date} ~ {end_date}\n\n"
                f"可能原因：\n"
                f"1. 该时间段内无数据\n"
                f"2. SQL语句中的日期字段名不匹配\n"
                f"3. 数据库连接问题")
            return
        
        dialog = QWidget(self, Qt.Dialog)
        dialog.setWindowTitle(f"SQL预览 - 共 {len(rows)} 条数据 (范围: {start_date} ~ {end_date})")
        dialog.setMinimumSize(1200, 600)
        
        layout = QVBoxLayout(dialog)
        
        info_label = QLabel(
            f"<b>查询结果:</b> 共 {len(rows)} 条数据 (已显示全部) | "
            f"<b>日期范围:</b> {start_date} ~ {end_date} | "
            f"<b>说明:</b> 已自动过滤不在日期范围内的数据"
        )
        info_label.setStyleSheet("color: #2196F3; padding: 5px; background-color: #E3F2FD; border-radius: 3px;")
        info_label.setWordWrap(True)
        layout.addWidget(info_label)
        
        table = QTableWidget()
        table.setAlternatingRowColors(True)
        enable_table_highlight(table)
        headers = list(rows[0].keys())
        table.setColumnCount(len(headers))
        table.setHorizontalHeaderLabels(headers)
        table.setRowCount(len(rows))
        
        for row_idx, row in enumerate(rows):
            for col_idx, key in enumerate(headers):
                value = str(row.get(key, ""))
                
                date_fields_lower = ['inbound_date', 'date_opr', 'purchase_time']
                if key.lower() in [f.lower() for f in date_fields_lower]:
                    item = QTableWidgetItem(value)
                    item.setBackground(QColor("#FFF9C4"))
                    table.setItem(row_idx, col_idx, item)
                else:
                    table.setItem(row_idx, col_idx, QTableWidgetItem(value))
        
        table.resizeColumnsToContents()
        table.horizontalHeader().setStretchLastSection(True)
        
        scroll_area = QScrollArea()
        scroll_area.setWidget(table)
        scroll_area.setWidgetResizable(True)
        scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        layout.addWidget(scroll_area)
        
        close_btn = QPushButton("关闭")
        close_btn.clicked.connect(dialog.close)
        layout.addWidget(close_btn)
        
        logging.info(f"✓ SQL预览完成: 显示全部 {len(rows)} 条过滤后数据")
        
        stats_label = QLabel(
            f"<b>数据统计:</b> 总行数 {len(rows)} | "
            f"列数 {len(headers)} | "
            f"日期范围 {start_date} ~ {end_date}"
        )
        stats_label.setStyleSheet("color: #666; padding: 5px; font-size: 11px;")
        layout.addWidget(stats_label)
        
        dialog.show()
    
    def _show_ysb_debug_info(self):
        if not self.ysb_data or not self.ysb_data.supplier_summaries:
            QMessageBox.warning(self, "提示", "没有供应商数据可显示")
            return
        
        dialog = QWidget(self, Qt.Dialog)
        dialog.setWindowTitle("药师帮原始数据调试信息")
        dialog.setMinimumSize(1000, 700)
        
        layout = QVBoxLayout(dialog)
        
        info_text = QTextEdit()
        info_text.setReadOnly(True)
        info_text.setFont(QFont("Consolas", 9))
        
        debug_info = []
        debug_info.append("=" * 80)
        debug_info.append("药师帮供应商数据 - 完整调试信息")
        debug_info.append("=" * 80)
        debug_info.append("")
        
        debug_info.append(f"工作表名称: {self.ysb_data.sheet_name}")
        debug_info.append(f"总记录数: {len(self.ysb_data.supplier_summaries)}")
        debug_info.append("")
        
        total_amount = Decimal("0")
        
        for idx, item in enumerate(self.ysb_data.supplier_summaries, 1):
            debug_info.append("-" * 80)
            debug_info.append(f"记录 #{idx} (Excel行{item.raw_row_index}):")
            debug_info.append("")
            
            all_fields = vars(item)
            for field_name, field_value in all_fields.items():
                if field_name == 'raw_row_index':
                    continue
                
                display_value = field_value
                if isinstance(field_value, Decimal):
                    display_value = f"{field_value:.2f}"
                
                is_amount_field = 'amount' in field_name.lower() or '金额' in field_name
                prefix = "💰 " if is_amount_field else "   "
                
                debug_info.append(f"{prefix}{field_name:25s} = {display_value}")
                
                if is_amount_field and isinstance(field_value, Decimal):
                    total_amount += field_value
            
            debug_info.append("")
        
        debug_info.append("=" * 80)
        debug_info.append(f"所有记录的actual_payment_amount总和: {total_amount:.2f}")
        
        non_zero_count = sum(1 for item in self.ysb_data.supplier_summaries 
                           if getattr(item, 'actual_payment_amount', Decimal("0")) > Decimal("0"))
        debug_info.append(f"有非零金额的记录数: {non_zero_count}/{len(self.ysb_data.supplier_summaries)}")
        
        if total_amount == Decimal("0"):
            debug_info.append("")
            debug_info.append("⚠️  警告：所有金额都为0！")
            debug_info.append("")
            debug_info.append("可能的原因：")
            debug_info.append("1. Excel中'实际支付金额(已减退款)'列的数据确实为0或空")
            debug_info.append("2. 列名不匹配（请检查上方的字段映射日志）")
            debug_info.append("3. 数据格式问题（文本格式而非数字）")
            debug_info.append("")
            debug_info.append("建议操作：")
            debug_info.append("1. 打开Excel文件，检查'本月支付订单'工作表")
            debug_info.append("2. 确认'实际支付金额(已减退款)'列是否有数值数据")
            debug_info.append("3. 如果列名不同，请告诉我实际的列名")
        
        debug_info.append("=" * 80)
        
        info_text.setPlainText("\n".join(debug_info))
        layout.addWidget(info_text)
        
        close_btn = QPushButton("关闭")
        close_btn.clicked.connect(dialog.close)
        layout.addWidget(close_btn)
        
        logging.info("用户点击了'显示原始数据详情'按钮")
        dialog.show()
    
    def _save_sql(self):
        config_id = self.db_config_combo.currentData()
        if not config_id:
            QMessageBox.warning(self, "提示", "请先选择数据库配置")
            return
        
        sql = self.sql_input.toPlainText().strip()
        if not sql:
            QMessageBox.warning(self, "提示", "请输入SQL查询语句")
            return
        
        config = self.db_config_service.get_config_by_id(config_id)
        if config:
            config.inbound_sql = sql
            self.db_config_service.save_config(config)
            QMessageBox.information(self, "成功", f"SQL已保存到配置 [{config.name}]")
    
    def _execute_supplier_reconciliation(self):
        # 权限检查
        if not self.permission_checker.check_permission(PermissionCodes.OP_YSB_RECONCILE_SUPPLIER_RECONCILE, self):
            return
        
        if not self.ysb_data or not self.ysb_data.supplier_summaries:
            self.status_label.setText("加载药师帮数据...")
            self.progress_bar.setValue(5)
            
            if not self._load_ysb_data_for_reconciliation(required_type="supplier"):
                return
            
            if not self.ysb_data.supplier_summaries:
                QMessageBox.warning(self, "提示", "未找到供应商汇总数据")
                self.status_label.setText("无数据")
                return
            
            total_ysb_amount = Decimal("0")
            zero_amount_suppliers = []
            
            for item in self.ysb_data.supplier_summaries:
                amount = getattr(item, 'actual_payment_amount', Decimal("0"))
                supplier_name = getattr(item, 'supplier_display_name', '') or getattr(item, 'ysb_supplier_name', '')
                total_ysb_amount += amount
                
                if amount == Decimal("0"):
                    zero_amount_suppliers.append(supplier_name)
            
            logging.info(f"===========================================")
            logging.info(f"供应商数据金额检查:")
            logging.info(f"  总记录数: {len(self.ysb_data.supplier_summaries)}")
            logging.info(f"  总金额: {total_ysb_amount}")
            logging.info(f"  有金额记录: {len(self.ysb_data.supplier_summaries) - len(zero_amount_suppliers)}")
            logging.info(f"  零金额记录: {len(zero_amount_suppliers)}")
            
            if len(zero_amount_suppliers) > 0 and len(zero_amount_suppliers) <= 5:
                logging.warning(f"  零金额供应商: {zero_amount_suppliers}")
            elif len(zero_amount_suppliers) > 5:
                logging.warning(f"  零金额供应商: 前5个={zero_amount_suppliers[:5]}...")
            
            logging.info(f"===========================================")
            
            if total_ysb_amount == Decimal("0") and len(self.ysb_data.supplier_summaries) > 0:
                QMessageBox.critical(
                    self,
                    "⚠️ 药师帮金额全部为0",
                    f"<h3>警告：所有供应商的实际支付金额都为0！</h3>"
                    f"<p>这可能导致对账结果不准确。</p>"
                    f"<br><b>可能原因：</b><br>"
                    f"1. Excel中'实际支付金额(已减退款)'列的数据确实为0或空<br>"
                    f"2. 列名不匹配（系统无法识别该列）<br>"
                    f"3. 数据格式问题（文本格式而非数字）<br>"
                    f"<br><b>建议操作：</b><br>"
                    f"1. 点击'预览药师帮数据'按钮查看详细数据<br>"
                    f"2. 在预览窗口中点击'显示原始数据详情'<br>"
                    f"3. 检查控制台日志中的字段映射信息<br>"
                    f"<br><b>是否继续对账？</b>",
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
                )
        
        config_id = self.db_config_combo.currentData()
        if not config_id:
            QMessageBox.warning(self, "提示", "请先选择数据库配置")
            return
        
        sql = self.sql_input.toPlainText()
        if not sql:
            QMessageBox.warning(self, "提示", "请输入SQL查询语句")
            return
        
        config = self.db_config_service.get_config_by_id(config_id)
        start_date = self.inbound_start.date().toString("yyyy-MM-dd")
        end_date = self.inbound_end.date().toString("yyyy-MM-dd")
        
        logging.info(f"===========================================")
        logging.info(f"供应商对账 - 入库查询参数:")
        logging.info(f"  开始日期: {start_date}")
        logging.info(f"  结束日期: {end_date}")
        logging.info(f"===========================================")
        
        self.status_label.setText(f"查询入库数据 ({start_date} ~ {end_date})...")
        self.progress_bar.setValue(10)
        
        service = InboundQueryService(config)
        self.inbound_rows, error = service.query_all(sql, start_date, end_date)
        
        if error:
            QMessageBox.warning(self, "错误", f"查询入库数据失败: {error}")
            self.status_label.setText("查询失败")
            return
        
        logging.info(f"✓ 供应商对账 - 入库查询完成: 返回 {len(self.inbound_rows)} 条数据")
        
        if len(self.inbound_rows) == 0:
            QMessageBox.warning(self, "提示", 
                f"未查询到入库数据！\n\n"
                f"请检查：\n"
                f"1. SQL语句是否正确\n"
                f"2. 日期范围 ({start_date} ~ {end_date}) 是否有数据\n"
                f"3. 数据库连接是否正常")
            self.status_label.setText("无入库数据")
            return
        
        self.progress_bar.setValue(30)
        self.status_label.setText(f"执行供应商对账... (入库数据: {len(self.inbound_rows)} 条)")
        
        engine = ReconciliationEngine(
            amount_tolerance=self.supplier_amount_tol.value()
        )
        (
            self.supplier_results,
            self.detail_results,
            self.product_results,
            self.recon_summary
        ) = engine.supplier_reconciliation(
            self.ysb_data.supplier_summaries,
            self.inbound_rows
        )
        
        self._save_reconciliation_results(engine, "supplier")
        
        self.recon_type = "supplier"
        self.progress_bar.setValue(100)
        self.status_label.setText("供应商对账完成")
        self.export_btn.setEnabled(True)
        
        self._update_supplier_result_table()
    
    def _save_reconciliation_results(self, engine, recon_type: str):
        import uuid
        from datetime import datetime
        
        task_id = uuid.uuid4().hex[:8]
        
        conn = self.db.get_connection()
        cursor = conn.cursor()
        now = datetime.now().isoformat()
        
        start_date = self.inbound_start.date().toString("yyyy-MM-dd")
        end_date = self.inbound_end.date().toString("yyyy-MM-dd")
        
        ysb_file = ""
        if self.ysb_data:
            ysb_file = getattr(self.ysb_data, 'file_path', '') or ""
        
        try:
            cursor.execute('''
                INSERT INTO reconciliation_tasks
                (task_id, task_type, ysb_file, account_period_start, account_period_end,
                 inbound_query_start, inbound_query_end, db_config_id, status,
                 supplier_match_count, supplier_diff_count, product_match_count, product_diff_count,
                 ysb_row_count, inbound_row_count, created_at, created_by)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                task_id,
                recon_type,
                ysb_file,
                start_date,
                end_date,
                start_date,
                end_date,
                self.db_config_combo.currentData() or 0,
                'completed',
                self.recon_summary.supplier_match_count if self.recon_summary else 0,
                self.recon_summary.supplier_diff_count if self.recon_summary else 0,
                self.recon_summary.product_match_count if self.recon_summary else 0,
                self.recon_summary.product_diff_count if self.recon_summary else 0,
                len(self.ysb_data.items) if self.ysb_data and self.ysb_data.items else (len(self.ysb_data.supplier_summaries) if self.ysb_data and self.ysb_data.supplier_summaries else 0),
                len(self.inbound_rows) if self.inbound_rows else 0,
                now,
                self.username
            ))
            
            engine.save_results_to_db(self.db, task_id)
            
            conn.commit()
            logging.info(f"✓ 对账结果已保存到数据库，任务ID: {task_id}")
            
        except Exception as e:
            conn.rollback()
            logging.error(f"❌ 保存对账结果失败: {e}")
    
    def _execute_product_reconciliation(self):
        # 权限检查
        if not self.permission_checker.check_permission(PermissionCodes.OP_YSB_RECONCILE_SUPPLIER_PRODUCT_RECONCILE, self):
            return
        
        recon_mode = self.product_recon_mode_combo.currentData()
        
        if not self.ysb_data or not self.ysb_data.items:
            self.status_label.setText("加载药师帮数据...")
            self.progress_bar.setValue(5)
            
            if not self._load_ysb_data_for_reconciliation(required_type="detail"):
                return
            
            if not self.ysb_data.items:
                QMessageBox.warning(self, "提示", "未找到明细数据")
                self.status_label.setText("无数据")
                return
        
        config_id = self.db_config_combo.currentData()
        if not config_id:
            QMessageBox.warning(self, "提示", "请先选择数据库配置")
            return
        
        sql = self.sql_input.toPlainText()
        if not sql:
            QMessageBox.warning(self, "提示", "请输入SQL查询语句")
            return
        
        config = self.db_config_service.get_config_by_id(config_id)
        start_date = self.inbound_start.date().toString("yyyy-MM-dd")
        end_date = self.inbound_end.date().toString("yyyy-MM-dd")
        
        logging.info(f"===========================================")
        logging.info(f"供应商商品对账 - 入库查询参数:")
        logging.info(f"  开始日期: {start_date}")
        logging.info(f"  结束日期: {end_date}")
        logging.info(f"  对账模式: {recon_mode}")
        logging.info(f"===========================================")
        
        self.status_label.setText(f"查询入库数据 ({start_date} ~ {end_date})...")
        self.progress_bar.setValue(10)
        
        service = InboundQueryService(config)
        self.inbound_rows, error = service.query_all(sql, start_date, end_date)
        
        if error:
            QMessageBox.warning(self, "错误", f"查询入库数据失败: {error}")
            self.status_label.setText("查询失败")
            return
        
        logging.info(f"✓ 供应商商品对账 - 入库查询完成: 返回 {len(self.inbound_rows)} 条数据")
        
        if len(self.inbound_rows) == 0:
            QMessageBox.warning(self, "提示", 
                f"未查询到入库数据！\n\n"
                f"请检查：\n"
                f"1. SQL语句是否正确\n"
                f"2. 日期范围 ({start_date} ~ {end_date}) 是否有数据\n"
                f"3. 数据库连接是否正常")
            self.status_label.setText("无入库数据")
            return
        
        self.progress_bar.setValue(30)
        
        engine = ReconciliationEngine(
            amount_tolerance=self.product_amount_tol.value(),
            quantity_tolerance=self.quantity_tol.value(),
            auto_match_threshold=self.auto_threshold.value(),
            suspected_match_threshold=self.suspected_threshold.value()
        )
        
        if recon_mode == "diff_only":
            self.status_label.setText("查询供应商对账结果...")
            self.progress_bar.setValue(40)
            
            try:
                conn = self.db.get_connection()
                cursor = conn.cursor()
                
                cursor.execute('''
                    SELECT task_id, created_at
                    FROM reconciliation_tasks
                    WHERE task_type = 'supplier'
                    AND status = 'completed'
                    ORDER BY created_at DESC
                    LIMIT 1
                ''')
                
                latest_task = cursor.fetchone()
                
                if not latest_task:
                    QMessageBox.warning(self, "提示", 
                        "未找到供应商对账结果！\n\n"
                        "请先执行供应商对账，然后再选择'按异常供应商核对商品'模式。")
                    self.status_label.setText("无供应商对账结果")
                    self.progress_bar.setValue(100)
                    return
                
                task_id = latest_task['task_id']
                logging.info(f"✓ 找到最近供应商对账任务: {task_id[:8]}, 时间: {latest_task['created_at']}")
                
                cursor.execute('''
                    SELECT ysb_supplier, inbound_supplier, status
                    FROM supplier_reconciliation_results
                    WHERE task_id = ?
                    AND status = '差异'
                ''', (task_id,))
                
                diff_results = cursor.fetchall()
                
                diff_suppliers = []
                for row in diff_results:
                    supplier = row['ysb_supplier'] or row['inbound_supplier']
                    if supplier:
                        diff_suppliers.append(supplier)
                
                conn.close()
                
                logging.info(f"✓ 从数据库查询到 {len(diff_suppliers)} 个差异供应商")
                logging.info(f"  差异供应商列表: {diff_suppliers}")
                
                if len(diff_suppliers) == 0:
                    QMessageBox.information(self, "提示", 
                        "供应商对账结果全部一致，无需进行商品核对！\n\n"
                        "如需核对所有供应商的商品，请选择'全量供应商核对商品'模式。")
                    self.status_label.setText("无差异供应商")
                    self.progress_bar.setValue(100)
                    return
                
                self.progress_bar.setValue(50)
                self.status_label.setText(f"按异常供应商核对商品... (差异供应商: {len(diff_suppliers)} 个)")
                
                (
                    self.supplier_results,
                    self.detail_results,
                    self.product_results,
                    self.recon_summary
                ) = engine.product_reconciliation_by_suppliers(
                    self.ysb_data.items,
                    self.inbound_rows,
                    diff_suppliers
                )
                
                self.recon_summary.supplier_diff_count = len(diff_suppliers)
                
            except Exception as e:
                logging.error(f"查询供应商对账结果失败: {e}")
                QMessageBox.warning(self, "错误", f"查询供应商对账结果失败: {str(e)}")
                self.status_label.setText("查询失败")
                return
            
        else:
            self.status_label.setText(f"执行全量供应商商品对账... (入库数据: {len(self.inbound_rows)} 条)")
            
            (
                self.supplier_results,
                self.detail_results,
                self.product_results,
                self.recon_summary
            ) = engine.product_reconciliation(
                self.ysb_data.items,
                self.inbound_rows
            )
        
        self.recon_type = "supplier_product"
        self._save_reconciliation_results(engine, "supplier_product")
        self.progress_bar.setValue(100)
        self.status_label.setText("供应商商品对账完成")
        self.export_btn.setEnabled(True)
        
        self._update_product_result_table()
    
    def _update_supplier_result_table(self):
        if not self.recon_summary:
            return
        
        s = self.recon_summary
        data = [
            ("药师帮供应商数", s.ysb_supplier_count, "入库供应商数", s.inbound_supplier_count),
            ("供应商一致数", s.supplier_match_count, "供应商差异数", s.supplier_diff_count),
            ("", "", "", ""),
            ("药师帮总金额", f"{s.ysb_total_amount:.2f}", "入库总金额", f"{s.inbound_total_amount:.2f}"),
        ]
        
        self.result_table.setRowCount(len(data))
        for row_idx, (label1, value1, label2, value2) in enumerate(data):
            self.result_table.setItem(row_idx, 0, QTableWidgetItem(label1))
            self.result_table.setItem(row_idx, 1, QTableWidgetItem(str(value1)))
            self.result_table.setItem(row_idx, 2, QTableWidgetItem(label2))
            self.result_table.setItem(row_idx, 3, QTableWidgetItem(str(value2)))
    
    def _update_product_result_table(self):
        if not self.recon_summary:
            return
        
        s = self.recon_summary
        data = [
            ("药师帮行数", s.ysb_row_count, "入库行数", s.inbound_row_count),
            ("", "", "", ""),
            ("自动匹配数", s.detail_matched_count, "疑似匹配数", s.detail_suspected_count),
            ("未匹配数", s.detail_unmatched_count, "", ""),
            ("", "", "", ""),
            ("商品汇总一致", s.product_match_count, "商品汇总差异", s.product_diff_count),
            ("", "", "", ""),
            ("药师帮总金额", f"{s.ysb_total_amount:.2f}", "入库总金额", f"{s.inbound_total_amount:.2f}"),
        ]
        
        self.result_table.setRowCount(len(data))
        for row_idx, (label1, value1, label2, value2) in enumerate(data):
            self.result_table.setItem(row_idx, 0, QTableWidgetItem(label1))
            self.result_table.setItem(row_idx, 1, QTableWidgetItem(str(value1)))
            self.result_table.setItem(row_idx, 2, QTableWidgetItem(label2))
            self.result_table.setItem(row_idx, 3, QTableWidgetItem(str(value2)))
        
        for row, (label1, val1, label2, val2) in enumerate(data):
            self.result_table.setItem(row, 0, QTableWidgetItem(label1))
            self.result_table.setItem(row, 1, QTableWidgetItem(str(val1)))
            self.result_table.setItem(row, 2, QTableWidgetItem(label2))
            self.result_table.setItem(row, 3, QTableWidgetItem(str(val2)))
    
    def _export_result(self):
        # 权限检查
        if not self.permission_checker.check_permission(PermissionCodes.OP_YSB_RECONCILE_EXPORT_RESULT, self):
            return
        
        if not self.recon_summary:
            QMessageBox.warning(self, "提示", "请先执行对账")
            return
        
        output_dir = QFileDialog.getExistingDirectory(
            self, "选择保存文件夹", str(DATA_DIR)
        )
        if not output_dir:
            return
        
        account_period = self.period_start.date().toString("yyyy-MM")
        ysb_file = self.file_path_input.text()
        inbound_range = (
            self.inbound_start.date().toString("yyyy-MM-dd"),
            self.inbound_end.date().toString("yyyy-MM-dd")
        )
        
        exporter = ResultExporter()
        self.result_file = exporter.export(
            self.supplier_results,
            self.detail_results,
            self.product_results,
            self.recon_summary,
            account_period,
            ysb_file,
            inbound_range,
            output_dir=output_dir,
            recon_type=self.recon_type
        )
        
        QMessageBox.information(self, "成功", f"结果已导出:\n{self.result_file}")
        
        self._save_task_record()
    
    def _save_task_record(self):
        conn = self.db.get_connection()
        cursor = conn.cursor()
        
        task_id = str(uuid.uuid4())
        now = datetime.now().isoformat()
        
        cursor.execute('''
            INSERT INTO reconciliation_tasks (
                task_id, task_type, ysb_file, account_period_start, account_period_end,
                inbound_query_start, inbound_query_end, status, result_file,
                ysb_row_count, inbound_row_count, matched_count, diff_count,
                supplier_match_count, supplier_diff_count, detail_matched_count,
                detail_suspected_count, detail_unmatched_count, product_match_count,
                product_diff_count, created_at, created_by
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            task_id,
            self.recon_type if self.recon_type else "all",
            self.file_path_input.text(),
            self.period_start.date().toString("yyyy-MM-dd"),
            self.period_end.date().toString("yyyy-MM-dd"),
            self.inbound_start.date().toString("yyyy-MM-dd"),
            self.inbound_end.date().toString("yyyy-MM-dd"),
            "completed",
            self.result_file,
            self.recon_summary.ysb_row_count if hasattr(self.recon_summary, 'ysb_row_count') else 0,
            self.recon_summary.inbound_row_count,
            self.recon_summary.detail_matched_count if hasattr(self.recon_summary, 'detail_matched_count') else 0,
            self.recon_summary.detail_unmatched_count + self.recon_summary.supplier_diff_count if hasattr(self.recon_summary, 'detail_unmatched_count') else 0,
            self.recon_summary.supplier_match_count if hasattr(self.recon_summary, 'supplier_match_count') else 0,
            self.recon_summary.supplier_diff_count if hasattr(self.recon_summary, 'supplier_diff_count') else 0,
            self.recon_summary.detail_matched_count if hasattr(self.recon_summary, 'detail_matched_count') else 0,
            self.recon_summary.detail_suspected_count if hasattr(self.recon_summary, 'detail_suspected_count') else 0,
            self.recon_summary.detail_unmatched_count if hasattr(self.recon_summary, 'detail_unmatched_count') else 0,
            self.recon_summary.product_match_count if hasattr(self.recon_summary, 'product_match_count') else 0,
            self.recon_summary.product_diff_count if hasattr(self.recon_summary, 'product_diff_count') else 0,
            now,
            self.username
        ))
        
        conn.commit()
        logging.info(f"对账任务已保存: {task_id}")
        
        if self.supplier_results:
            for result in self.supplier_results:
                cursor.execute('''
                    INSERT INTO supplier_reconciliation_results 
                    (task_id, status, diff_type, ysb_supplier, inbound_supplier,
                     ysb_amount, inbound_amount, amount_diff, ysb_count, inbound_count,
                     match_method, remark, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (
                    task_id,
                    result.status,
                    result.diff_type,
                    result.ysb_supplier,
                    result.inbound_supplier,
                    str(result.ysb_amount),
                    str(result.inbound_amount),
                    str(result.amount_diff),
                    result.ysb_count,
                    result.inbound_count,
                    result.match_method,
                    result.remark,
                    now
                ))
            
            logging.info(f"✓ 保存供应商对账结果: {len(self.supplier_results)} 条")
        
        if self.product_results:
            for result in self.product_results:
                cursor.execute('''
                    INSERT INTO product_reconciliation_results 
                    (task_id, status, diff_type, supplier, product_code, product_name,
                     spec, manufacturer, ysb_amount, inbound_amount, amount_diff,
                     ysb_quantity, inbound_quantity, quantity_diff, ysb_supplier, inbound_supplier,
                     remark, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (
                    task_id,
                    result.status,
                    result.diff_type,
                    result.supplier,
                    result.product_code,
                    result.product_name,
                    result.spec,
                    result.manufacturer,
                    str(result.ysb_amount),
                    str(result.inbound_amount),
                    str(result.amount_diff),
                    str(result.ysb_quantity),
                    str(result.inbound_quantity),
                    str(result.quantity_diff),
                    result.ysb_supplier,
                    result.inbound_supplier,
                    result.remark,
                    now
                ))
            
            logging.info(f"✓ 保存商品对账结果: {len(self.product_results)} 条")
        
        conn.commit()
        logging.info(f"✓ 对账结果保存成功")
