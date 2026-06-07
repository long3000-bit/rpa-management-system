from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QTableWidget, QTableWidgetItem,
    QMessageBox, QHeaderView, QGroupBox, QComboBox, QLineEdit
)
from PySide6.QtCore import Qt
import logging

from app.storage.database import Database
from app.core.yys_stock_import_service import YysStockImportService
from app.core.data_permission_service import DataPermissionService


class YysStockQueryPage(QWidget):
    
    def __init__(self, db: Database, username: str, role_code: str):
        super().__init__()
        self.db = db
        self.username = username
        self.role_code = role_code
        self.yys_import_service = YysStockImportService(db)
        self.data_permission_service = DataPermissionService(db)
        
        self.current_batch_id = None
        
        self._init_ui()
        self._load_batches()
    
    def _init_ui(self):
        layout = QVBoxLayout(self)
        
        title = QLabel("云药店库存查询")
        title.setStyleSheet("font-size: 18px; font-weight: bold;")
        layout.addWidget(title)
        
        batch_group = QGroupBox("导入批次")
        batch_layout = QHBoxLayout(batch_group)
        
        self.batch_combo = QComboBox()
        self.batch_combo.currentIndexChanged.connect(self._on_batch_changed)
        batch_layout.addWidget(self.batch_combo)
        
        refresh_btn = QPushButton("刷新")
        refresh_btn.clicked.connect(self._load_batches)
        batch_layout.addWidget(refresh_btn)
        
        delete_btn = QPushButton("删除批次")
        delete_btn.clicked.connect(self._delete_batch)
        batch_layout.addWidget(delete_btn)
        
        layout.addWidget(batch_group)
        
        info_group = QGroupBox("批次信息")
        info_layout = QHBoxLayout(info_group)
        
        self.batch_name_label = QLabel("批次名称: -")
        self.total_label = QLabel("总记录数: 0")
        self.valid_label = QLabel("有效记录: 0")
        self.invalid_label = QLabel("无效记录: 0")
        self.import_time_label = QLabel("导入时间: -")
        
        info_layout.addWidget(self.batch_name_label)
        info_layout.addWidget(self.total_label)
        info_layout.addWidget(self.valid_label)
        info_layout.addWidget(self.invalid_label)
        info_layout.addWidget(self.import_time_label)
        
        layout.addWidget(info_group)
        
        # 查询条件
        query_group = QGroupBox("查询条件")
        query_layout = QHBoxLayout(query_group)
        
        query_layout.addWidget(QLabel("商品编码:"))
        self.productno_edit = QLineEdit()
        self.productno_edit.setPlaceholderText("输入商品编码")
        self.productno_edit.setMaximumWidth(120)
        query_layout.addWidget(self.productno_edit)
        
        query_layout.addWidget(QLabel("旧商品编码:"))
        self.oldproductno_edit = QLineEdit()
        self.oldproductno_edit.setPlaceholderText("输入旧商品编码")
        self.oldproductno_edit.setMaximumWidth(120)
        query_layout.addWidget(self.oldproductno_edit)
        
        query_layout.addWidget(QLabel("药品名称:"))
        self.productname_edit = QLineEdit()
        self.productname_edit.setPlaceholderText("输入药品名称")
        self.productname_edit.setMaximumWidth(150)
        query_layout.addWidget(self.productname_edit)
        
        query_layout.addWidget(QLabel("批号:"))
        self.lotno_edit = QLineEdit()
        self.lotno_edit.setPlaceholderText("输入批号")
        self.lotno_edit.setMaximumWidth(100)
        query_layout.addWidget(self.lotno_edit)
        
        query_btn = QPushButton("查询")
        query_btn.clicked.connect(self._do_query)
        query_layout.addWidget(query_btn)
        
        clear_btn = QPushButton("清空")
        clear_btn.clicked.connect(self._clear_query)
        query_layout.addWidget(clear_btn)
        
        query_layout.addStretch()
        
        layout.addWidget(query_group)
        
        self.detail_table = QTableWidget()
        self.detail_table.setColumnCount(25)
        self.detail_table.setHorizontalHeaderLabels([
            "行号", "商品编码", "旧商品编码", "药品名称", "批号", "库存数量", "仓库",
            "规格", "单位", "生产厂家", "供应商", "有效期", "生产日期",
            "零售价", "批发价", "金额", "税率", "毛利", "毛利率",
            "库存状态", "条形码", "批准文号", "中药标志", "入库时间", "导入状态"
        ])
        self.detail_table.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
        self.detail_table.setSelectionBehavior(QTableWidget.SelectRows)
        
        layout.addWidget(self.detail_table)
    
    def _load_batches(self):
        # 使用数据权限服务获取过滤后的批次
        batches = self.data_permission_service.get_filtered_batches(
            'yys_import_batch', self.role_code, self.username,
            order_by="imported_at DESC"
        )
        
        self.batch_combo.clear()
        
        for batch in batches:
            self.batch_combo.addItem(
                f"{batch['batch_name']} ({batch['batch_id']})",
                batch['batch_id']
            )
        
        if batches:
            self._on_batch_changed(0)
    
    def _on_batch_changed(self, index):
        batch_id = self.batch_combo.currentData()
        
        if not batch_id:
            return
        
        self.current_batch_id = batch_id
        
        self._load_batch_info(batch_id)
        self._load_batch_details(batch_id)
    
    def _load_batch_info(self, batch_id):
        try:
            conn = self.db.get_connection()
            cursor = conn.cursor()
            
            cursor.execute('''
                SELECT batch_name, total_count, valid_count, invalid_count, imported_at
                FROM yys_import_batch
                WHERE batch_id = ?
            ''', (batch_id,))
            
            row = cursor.fetchone()
            
            if row:
                self.batch_name_label.setText(f"批次名称: {row['batch_name'] or '-'}")
                self.total_label.setText(f"总记录数: {row['total_count'] or 0}")
                self.valid_label.setText(f"有效记录: {row['valid_count'] or 0}")
                self.invalid_label.setText(f"无效记录: {row['invalid_count'] or 0}")
                self.import_time_label.setText(f"导入时间: {row['imported_at'] or '-'}")
            
        except Exception as e:
            logging.error(f"加载批次信息失败: {e}")
    
    def _load_batch_details(self, batch_id):
        productno = self.productno_edit.text().strip()
        oldproductno = self.oldproductno_edit.text().strip()
        productname = self.productname_edit.text().strip()
        lotno = self.lotno_edit.text().strip()
        
        details = self.yys_import_service.get_batch_details_with_filter(
            batch_id, productno, oldproductno, productname, lotno
        )
        
        self.detail_table.setRowCount(len(details))
        
        for row_idx, detail in enumerate(details):
            self.detail_table.setItem(row_idx, 0, QTableWidgetItem(str(detail['row_number'] or 0)))
            self.detail_table.setItem(row_idx, 1, QTableWidgetItem(detail['productno'] or ""))
            self.detail_table.setItem(row_idx, 2, QTableWidgetItem(detail['oldproductno'] or ""))
            self.detail_table.setItem(row_idx, 3, QTableWidgetItem(detail['productname'] or ""))
            self.detail_table.setItem(row_idx, 4, QTableWidgetItem(detail['lotno'] or ""))
            self.detail_table.setItem(row_idx, 5, QTableWidgetItem(str(detail['yys_quantity'] or 0)))
            self.detail_table.setItem(row_idx, 6, QTableWidgetItem(detail['warehouse'] or ""))
            self.detail_table.setItem(row_idx, 7, QTableWidgetItem(detail['specification'] or ""))
            self.detail_table.setItem(row_idx, 8, QTableWidgetItem(detail['unit'] or ""))
            self.detail_table.setItem(row_idx, 9, QTableWidgetItem(detail['manufacturer'] or ""))
            self.detail_table.setItem(row_idx, 10, QTableWidgetItem(detail['supplier'] or ""))
            self.detail_table.setItem(row_idx, 11, QTableWidgetItem(detail['valid_date'] or ""))
            self.detail_table.setItem(row_idx, 12, QTableWidgetItem(detail['production_date'] or ""))
            self.detail_table.setItem(row_idx, 13, QTableWidgetItem(str(detail['retail_price'] or 0)))
            self.detail_table.setItem(row_idx, 14, QTableWidgetItem(str(detail['batch_price'] or 0)))
            self.detail_table.setItem(row_idx, 15, QTableWidgetItem(str(detail['amount'] or 0)))
            self.detail_table.setItem(row_idx, 16, QTableWidgetItem(detail['tax_rate'] or ""))
            self.detail_table.setItem(row_idx, 17, QTableWidgetItem(str(detail['gross_profit'] or 0)))
            self.detail_table.setItem(row_idx, 18, QTableWidgetItem(detail['gross_profit_rate'] or ""))
            self.detail_table.setItem(row_idx, 19, QTableWidgetItem(detail['stock_status'] or ""))
            self.detail_table.setItem(row_idx, 20, QTableWidgetItem(detail['barcode'] or ""))
            self.detail_table.setItem(row_idx, 21, QTableWidgetItem(detail['approval_number'] or ""))
            self.detail_table.setItem(row_idx, 22, QTableWidgetItem(detail['chinese_medicine_flag'] or ""))
            self.detail_table.setItem(row_idx, 23, QTableWidgetItem(detail['inbound_time'] or ""))
            
            status = detail['import_status'] or ""
            status_text = {'valid': '有效', 'invalid': '无效'}.get(status, status)
            self.detail_table.setItem(row_idx, 24, QTableWidgetItem(status_text))
    
    def _do_query(self):
        if not self.current_batch_id:
            QMessageBox.warning(self, "提示", "请先选择批次")
            return
        
        self._load_batch_details(self.current_batch_id)
    
    def _clear_query(self):
        self.productno_edit.clear()
        self.oldproductno_edit.clear()
        self.productname_edit.clear()
        self.lotno_edit.clear()
        
        if self.current_batch_id:
            self._load_batch_details(self.current_batch_id)
    
    def _delete_batch(self):
        batch_id = self.batch_combo.currentData()
        
        if not batch_id:
            QMessageBox.warning(self, "提示", "请选择要删除的批次")
            return
        
        reply = QMessageBox.question(self, "确认", "确定要删除此批次及其所有明细数据吗？", QMessageBox.Yes | QMessageBox.No)
        
        if reply != QMessageBox.Yes:
            return
        
        success, error = self.yys_import_service.delete_batch(batch_id)
        
        if success:
            self._load_batches()
            QMessageBox.information(self, "成功", "删除成功")
        else:
            QMessageBox.warning(self, "错误", error)