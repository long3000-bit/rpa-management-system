from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, 
    QPushButton, QComboBox, QTableWidget,
    QTableWidgetItem, QMessageBox, QGroupBox,
    QLineEdit, QDateEdit, QTextEdit, QSplitter, QHeaderView
)
from PySide6.QtCore import Qt, QDate
from PySide6.QtGui import QFont
from datetime import datetime
from decimal import Decimal
from pathlib import Path
import logging

from app.storage.database import Database
from app.ui.widgets.table_highlight import enable_table_highlight
from app.core.database_config_service import DatabaseConfigService, InboundQueryService


class InboundQueryPage(QWidget):
    
    def __init__(self, db: Database):
        super().__init__()
        self.db = db
        self.db_config_service = DatabaseConfigService(db)
        self.inbound_rows = []
        self._init_ui()
        self._load_db_configs()
    
    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(10)
        
        config_group = QGroupBox("数据库配置")
        config_layout = QHBoxLayout(config_group)
        
        config_layout.addWidget(QLabel("数据库:"))
        self.db_config_combo = QComboBox()
        self.db_config_combo.setMinimumWidth(250)
        self.db_config_combo.currentIndexChanged.connect(self._on_db_config_changed)
        config_layout.addWidget(self.db_config_combo)
        
        self.refresh_btn = QPushButton("刷新")
        self.refresh_btn.clicked.connect(self._load_db_configs)
        config_layout.addWidget(self.refresh_btn)
        
        self.test_btn = QPushButton("测试连接")
        self.test_btn.clicked.connect(self._test_connection)
        config_layout.addWidget(self.test_btn)
        
        config_layout.addStretch()
        layout.addWidget(config_group)
        
        sql_group = QGroupBox("查询SQL")
        sql_layout = QVBoxLayout(sql_group)
        
        self.sql_input = QTextEdit()
        self.sql_input.setPlaceholderText("输入入库单查询SQL...")
        self.sql_input.setMinimumHeight(100)
        sql_layout.addWidget(self.sql_input)
        
        sql_btn_layout = QHBoxLayout()
        self.load_sql_btn = QPushButton("加载默认SQL")
        self.load_sql_btn.clicked.connect(self._load_default_sql)
        sql_btn_layout.addWidget(self.load_sql_btn)
        
        self.save_sql_btn = QPushButton("保存SQL")
        self.save_sql_btn.clicked.connect(self._save_sql)
        sql_btn_layout.addWidget(self.save_sql_btn)
        
        sql_btn_layout.addStretch()
        sql_layout.addLayout(sql_btn_layout)
        
        layout.addWidget(sql_group)
        
        filter_group = QGroupBox("查询条件")
        filter_layout = QVBoxLayout(filter_group)
        
        filter_row1 = QHBoxLayout()
        filter_row1.addWidget(QLabel("日期范围:"))
        
        self.start_date = QDateEdit()
        self.start_date.setCalendarPopup(True)
        self.start_date.setDate(QDate.currentDate().addMonths(-1))
        filter_row1.addWidget(self.start_date)
        
        filter_row1.addWidget(QLabel("至"))
        
        self.end_date = QDateEdit()
        self.end_date.setCalendarPopup(True)
        self.end_date.setDate(QDate.currentDate())
        filter_row1.addWidget(self.end_date)
        
        self.query_btn = QPushButton("查询")
        self.query_btn.clicked.connect(self._execute_query)
        self.query_btn.setStyleSheet("background-color: #4CAF50; color: white;")
        filter_row1.addWidget(self.query_btn)
        
        filter_row1.addStretch()
        filter_layout.addLayout(filter_row1)
        
        filter_row2 = QHBoxLayout()
        filter_row2.addWidget(QLabel("搜索:"))
        
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("输入商品名称、供应商或单号搜索...")
        self.search_input.setMinimumWidth(400)
        self.search_input.textChanged.connect(self._on_search_changed)
        filter_row2.addWidget(self.search_input)
        
        self.export_btn = QPushButton("导出")
        self.export_btn.clicked.connect(self._export_data)
        filter_row2.addWidget(self.export_btn)
        
        filter_row2.addStretch()
        filter_layout.addLayout(filter_row2)
        
        layout.addWidget(filter_group)
        
        result_group = QGroupBox("查询结果")
        result_layout = QVBoxLayout(result_group)
        
        self.result_table = QTableWidget()
        self.result_table.setAlternatingRowColors(True)
        self.result_table.setSortingEnabled(True)
        enable_table_highlight(self.result_table)
        result_layout.addWidget(self.result_table)
        
        self.result_label = QLabel("共 0 条记录")
        result_layout.addWidget(self.result_label)
        
        layout.addWidget(result_group)
    
    def _load_db_configs(self):
        configs = self.db_config_service.get_all_configs()
        
        self.db_config_combo.clear()
        self.db_config_combo.addItem("请选择数据库配置", None)
        
        for config in configs:
            self.db_config_combo.addItem(f"{config.name} ({config.host}:{config.port})", config.id)
    
    def _on_db_config_changed(self):
        config_id = self.db_config_combo.currentData()
        if config_id:
            config = self.db_config_service.get_config_by_id(config_id)
            if config and config.inbound_sql:
                self.sql_input.setPlainText(config.inbound_sql)
    
    def _test_connection(self):
        config_id = self.db_config_combo.currentData()
        if not config_id:
            QMessageBox.warning(self, "提示", "请先选择数据库配置")
            return
        
        config = self.db_config_service.get_config_by_id(config_id)
        if not config:
            QMessageBox.warning(self, "提示", "数据库配置不存在")
            return
        
        service = InboundQueryService(config)
        success, message = service.test_connection()
        
        if success:
            QMessageBox.information(self, "成功", f"连接成功！\n{message}")
        else:
            QMessageBox.critical(self, "失败", f"连接失败！\n{message}")
    
    def _load_default_sql(self):
        default_sql = """SELECT 
    入库单号,
    入库日期,
    供应商名称,
    商品名称,
    规格,
    厂家,
    批号,
    数量,
    单价,
    金额,
    批准文号,
    条形码
FROM 入库单表
WHERE 入库日期 BETWEEN ? AND ?
ORDER BY 入库日期 DESC"""
        
        self.sql_input.setPlainText(default_sql)
    
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
    
    def _execute_query(self):
        config_id = self.db_config_combo.currentData()
        if not config_id:
            QMessageBox.warning(self, "提示", "请先选择数据库配置")
            return
        
        sql = self.sql_input.toPlainText().strip()
        if not sql:
            QMessageBox.warning(self, "提示", "请输入SQL查询语句")
            return
        
        config = self.db_config_service.get_config_by_id(config_id)
        if not config:
            QMessageBox.warning(self, "提示", "数据库配置不存在")
            return
        
        start_date = self.start_date.date().toString("yyyy-MM-dd")
        end_date = self.end_date.date().toString("yyyy-MM-dd")
        
        self.result_label.setText("正在查询...")
        
        try:
            service = InboundQueryService(config)
            self.inbound_rows, error = service.query_all(sql, start_date, end_date)
            
            if error:
                QMessageBox.critical(self, "错误", f"查询失败:\n{error}")
                self.result_label.setText("查询失败")
                return
            
            self._display_results(self._filter_rows_by_search(self.inbound_rows))
            
        except Exception as e:
            QMessageBox.critical(self, "错误", f"查询过程发生错误:\n{str(e)}")
            self.result_label.setText("查询失败")
    
    def _display_results(self, rows):
        if not rows:
            self.result_table.setRowCount(0)
            self.result_label.setText("共 0 条记录，金额合计 0.00")
            return
        
        if len(rows) > 0:
            first_row = rows[0]
            headers = list(first_row.keys())
            
            self.result_table.setColumnCount(len(headers))
            self.result_table.setHorizontalHeaderLabels(headers)
            self.result_table.setRowCount(len(rows))
            
            for row_idx, row in enumerate(rows):
                for col_idx, key in enumerate(headers):
                    value = row.get(key, '')
                    self.result_table.setItem(row_idx, col_idx, QTableWidgetItem(str(value) if value else ''))
            
            self.result_table.resizeColumnsToContents()
        
        total_amount = self._sum_amount(rows)
        self.result_label.setText(f"共 {len(rows)} 条记录，金额合计 {total_amount:.2f}")
    
    def _sum_amount(self, rows: list[dict]) -> Decimal:
        total = Decimal("0")
        amount_fields = [
            "amount", "金额", "入库金额", "dec_amt", "Dec_Amt",
            "total_amount", "TotalAmount", "价税合计", "含税金额"
        ]
        
        for row in rows:
            total += self._to_decimal(self._get_first_value(row, amount_fields))
        
        return total
    
    def _get_first_value(self, row: dict, fields: list[str]):
        if not row:
            return None
        
        normalized = {str(key).strip().lower(): value for key, value in row.items()}
        for field in fields:
            value = row.get(field)
            if value not in (None, ""):
                return value
            
            value = normalized.get(str(field).strip().lower())
            if value not in (None, ""):
                return value
        
        return None
    
    def _to_decimal(self, value) -> Decimal:
        if value in (None, ""):
            return Decimal("0")
        
        text = str(value).replace(",", "").replace("￥", "").replace("¥", "").strip()
        try:
            return Decimal(text)
        except Exception:
            return Decimal("0")
    
    def _on_search_changed(self):
        pass
    
    def _filter_results(self):
        if not self.inbound_rows:
            QMessageBox.warning(self, "提示", "请先执行查询")
            return
        
        self._display_results(self._filter_rows_by_search(self.inbound_rows))
    
    def _filter_rows_by_search(self, rows: list[dict]) -> list[dict]:
        search_text = self.search_input.text().strip().lower()
        if not search_text:
            return rows
        
        return [
            row for row in rows
            if search_text in ' '.join(str(v).lower() for v in row.values() if v)
        ]
    
    def _export_data(self):
        QMessageBox.information(self, "提示", "导出功能开发中...")
