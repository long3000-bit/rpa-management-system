from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QTableWidget, QTableWidgetItem,
    QMessageBox, QHeaderView, QGroupBox, QComboBox,
    QLineEdit, QTextEdit, QProgressBar
)
from PySide6.QtCore import Qt, QThread, Signal
import logging

from app.storage.database import Database
from app.core.jy_stock_query_service import JyStockQueryService
from app.core.database_config_service import DatabaseConfigService


class QueryWorker(QThread):
    progress = Signal(int, str)
    finished = Signal(int, int, str)
    
    def __init__(self, service: JyStockQueryService, config_id: int, batch_id: str, custom_sql: str):
        super().__init__()
        self.service = service
        self.config_id = config_id
        self.batch_id = batch_id
        self.custom_sql = custom_sql
    
    def run(self):
        query_count, _, error = self.service.query_stock(self.config_id, self.batch_id, self.custom_sql)
        self.finished.emit(query_count, 0, error)


class JyStockQueryPage(QWidget):
    
    def __init__(self, db: Database):
        super().__init__()
        self.db = db
        self.jy_query_service = JyStockQueryService(db)
        self.db_config_service = DatabaseConfigService(db)
        
        self.current_batch_id = None
        self.query_worker = None
        
        self._init_ui()
        self._load_configs()
    
    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(15)
        
        title = QLabel("君元库存查询")
        title.setStyleSheet("font-size: 18px; font-weight: bold;")
        layout.addWidget(title)
        
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
        
        self.test_conn_btn = QPushButton("测试连接")
        self.test_conn_btn.clicked.connect(self._test_connection)
        row1.addWidget(self.test_conn_btn)
        
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
        
        sql_group = QGroupBox("库存查询SQL")
        sql_layout = QVBoxLayout(sql_group)
        
        sql_layout.addWidget(QLabel("查询SQL:"))
        self.sql_edit = QTextEdit()
        self.sql_edit.setPlaceholderText("输入查询君元库存的SQL语句，结果需包含药品编码、批号、库存数量等字段")
        self.sql_edit.setMaximumHeight(120)
        sql_layout.addWidget(self.sql_edit)
        
        sql_btn_row = QHBoxLayout()
        
        self.save_sql_btn = QPushButton("保存SQL")
        self.save_sql_btn.clicked.connect(self._save_stock_query_sql)
        sql_btn_row.addWidget(self.save_sql_btn)
        
        sql_btn_row.addStretch()
        
        self.query_btn = QPushButton("预览")
        self.query_btn.clicked.connect(self._execute_query)
        sql_btn_row.addWidget(self.query_btn)
        
        sql_layout.addLayout(sql_btn_row)
        
        layout.addWidget(sql_group)
        
        result_group = QGroupBox("查询结果")
        result_layout = QVBoxLayout(result_group)
        
        # 查询条件
        query_filter_layout = QHBoxLayout()
        
        query_filter_layout.addWidget(QLabel("药品编码:"))
        self.oldproductno_edit = QLineEdit()
        self.oldproductno_edit.setPlaceholderText("输入药品编码")
        self.oldproductno_edit.setMaximumWidth(120)
        query_filter_layout.addWidget(self.oldproductno_edit)
        
        query_filter_layout.addWidget(QLabel("药品名称:"))
        self.productname_edit = QLineEdit()
        self.productname_edit.setPlaceholderText("输入药品名称")
        self.productname_edit.setMaximumWidth(150)
        query_filter_layout.addWidget(self.productname_edit)
        
        query_filter_layout.addWidget(QLabel("批号:"))
        self.lotno_edit = QLineEdit()
        self.lotno_edit.setPlaceholderText("输入批号")
        self.lotno_edit.setMaximumWidth(100)
        query_filter_layout.addWidget(self.lotno_edit)
        
        filter_btn = QPushButton("筛选")
        filter_btn.clicked.connect(self._filter_results)
        query_filter_layout.addWidget(filter_btn)
        
        clear_btn = QPushButton("清空")
        clear_btn.clicked.connect(self._clear_filter)
        query_filter_layout.addWidget(clear_btn)
        
        query_filter_layout.addStretch()
        result_layout.addLayout(query_filter_layout)
        
        result_header = QHBoxLayout()
        self.result_count_label = QLabel("查询记录数: 0")
        result_header.addWidget(self.result_count_label)
        
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        result_header.addWidget(self.progress_bar)
        
        result_header.addStretch()
        result_layout.addLayout(result_header)
        
        self.result_table = QTableWidget()
        self.result_table.setColumnCount(10)
        self.result_table.setHorizontalHeaderLabels([
            "药品编码", "药品名称", "批号", "库存数量", "仓库", "有效期", "规格", "批准文号", "查询时间", "批次号"
        ])
        self.result_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.result_table.setSelectionBehavior(QTableWidget.SelectRows)
        
        result_layout.addWidget(self.result_table)
        
        layout.addWidget(result_group)
    
    def _load_configs(self):
        configs = self.db_config_service.get_all_configs()
        
        self.config_combo.clear()
        
        for config in configs:
            self.config_combo.addItem(config.name, config.id)
        
        if configs:
            self._on_config_changed(0)
    
    def _on_config_changed(self, index):
        config_id = self.config_combo.currentData()
        
        if not config_id:
            self.conn_info_label.setText("未选择配置")
            self.sql_edit.setText("")
            return
        
        config = self.db_config_service.get_config_by_id(config_id)
        
        if config:
            conn_info = f"{config.host}:{config.port}/{config.database_name}"
            self.conn_info_label.setText(conn_info)
            
            if config.stock_query_sql:
                self.sql_edit.setText(config.stock_query_sql)
            elif config.inbound_sql:
                self.sql_edit.setText(config.inbound_sql)
            else:
                self.sql_edit.setText("")
    
    def _test_connection(self):
        config_id = self.config_combo.currentData()
        
        if not config_id:
            QMessageBox.warning(self, "提示", "请选择数据库配置")
            return
        
        success, message = self.jy_query_service.test_connection(config_id)
        
        if success:
            QMessageBox.information(self, "成功", message)
        else:
            QMessageBox.warning(self, "失败", message)
    
    def _save_stock_query_sql(self):
        config_id = self.config_combo.currentData()
        
        if not config_id:
            QMessageBox.warning(self, "提示", "请选择数据库配置")
            return
        
        sql = self.sql_edit.toPlainText().strip()
        
        if not sql:
            QMessageBox.warning(self, "提示", "请输入查询SQL")
            return
        
        config = self.db_config_service.get_config_by_id(config_id)
        
        if config:
            config.stock_query_sql = sql
            self.db_config_service.save_config(config)
            QMessageBox.information(self, "成功", "库存查询SQL已保存")
    
    def _execute_query(self):
        config_id = self.config_combo.currentData()
        
        if not config_id:
            QMessageBox.warning(self, "提示", "请选择数据库配置")
            return
        
        custom_sql = self.sql_edit.toPlainText().strip()
        
        if not custom_sql:
            QMessageBox.warning(self, "提示", "请输入查询SQL")
            return
        
        import uuid
        from datetime import datetime
        self.current_batch_id = f"JY{datetime.now().strftime('%Y%m%d%H%M%S')}{uuid.uuid4().hex[:4]}"
        
        self.jy_query_service.clear_query_results(self.current_batch_id)
        
        self.query_btn.setEnabled(False)
        self.progress_bar.setVisible(True)
        self.progress_bar.setRange(0, 0)
        
        self.query_worker = QueryWorker(
            self.jy_query_service,
            config_id,
            self.current_batch_id,
            custom_sql
        )
        self.query_worker.finished.connect(self._on_query_finished)
        self.query_worker.start()
    
    def _on_query_finished(self, query_count, _, error):
        self.query_btn.setEnabled(True)
        self.progress_bar.setVisible(False)
        
        if error:
            QMessageBox.warning(self, "错误", error)
            return
        
        self.result_count_label.setText(f"查询记录数: {query_count}")
        self._load_results(self.current_batch_id)
        
        QMessageBox.information(self, "成功", f"查询成功，共 {query_count} 条记录")
    
    def _load_results(self, batch_id):
        oldproductno = self.oldproductno_edit.text().strip()
        productname = self.productname_edit.text().strip()
        lotno = self.lotno_edit.text().strip()
        
        results = self.jy_query_service.get_query_results_with_filter(
            batch_id, oldproductno, productname, lotno
        )
        
        self.result_count_label.setText(f"查询记录数: {len(results)}")
        
        self.result_table.setRowCount(len(results))
        
        for row_idx, result in enumerate(results):
            self.result_table.setItem(row_idx, 0, QTableWidgetItem(result['oldproductno'] or ""))
            self.result_table.setItem(row_idx, 1, QTableWidgetItem(result['productname'] or ""))
            self.result_table.setItem(row_idx, 2, QTableWidgetItem(result['lotno'] or ""))
            self.result_table.setItem(row_idx, 3, QTableWidgetItem(str(result['jy_quantity'] or 0)))
            self.result_table.setItem(row_idx, 4, QTableWidgetItem(result['warehouse'] or ""))
            self.result_table.setItem(row_idx, 5, QTableWidgetItem(result['valid_date'] or ""))
            self.result_table.setItem(row_idx, 6, QTableWidgetItem(result['specification'] or ""))
            self.result_table.setItem(row_idx, 7, QTableWidgetItem(result['approval_number'] or ""))
            self.result_table.setItem(row_idx, 8, QTableWidgetItem(result['query_time'] or ""))
            self.result_table.setItem(row_idx, 9, QTableWidgetItem(batch_id))
    
    def _filter_results(self):
        if not self.current_batch_id:
            QMessageBox.warning(self, "提示", "请先执行查询")
            return
        
        self._load_results(self.current_batch_id)
    
    def _clear_filter(self):
        self.oldproductno_edit.clear()
        self.productname_edit.clear()
        self.lotno_edit.clear()
        
        if self.current_batch_id:
            self._load_results(self.current_batch_id)