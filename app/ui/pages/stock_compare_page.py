from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QTableWidget, QTableWidgetItem,
    QMessageBox, QFileDialog, QComboBox, QGroupBox,
    QFormLayout, QLineEdit, QHeaderView, QProgressBar,
    QTabWidget, QCheckBox, QDialog, QTextEdit
)
from PySide6.QtCore import Qt, QThread, Signal
import logging
import random
import uuid
from datetime import datetime
from pathlib import Path
import pandas as pd

from app.storage.database import Database
from app.core.yys_stock_import_service import YysStockImportService
from app.core.jy_stock_query_service import JyStockQueryService
from app.core.stock_compare_service import StockCompareService
from app.core.yys_api_service import YysApiService
from app.core.database_config_service import DatabaseConfigService
from app.core.permission_checker import PermissionChecker, PermissionCodes
from app.core.data_permission_service import DataPermissionService


class SyncWorker(QThread):
    progress = Signal(int, int, str, str)
    finished = Signal(int, int, int)
    
    def __init__(self, api_service, config_id, items):
        super().__init__()
        self.api_service = api_service
        self.config_id = config_id
        self.items = items
    
    def run(self):
        success, failed, skipped = self.api_service.batch_update_stock(
            self.config_id,
            self.items,
            lambda current, total, status, msg: self.progress.emit(current, total, status, msg)
        )
        self.finished.emit(success, failed, skipped)


class ImportWorker(QThread):
    finished = Signal(str, int, int, str)
    
    def __init__(self, import_service, file_path, sheet_name, username: str = None):
        super().__init__()
        self.import_service = import_service
        self.file_path = file_path
        self.sheet_name = sheet_name
        self.username = username or 'admin'
    
    def run(self):
        batch_id, valid_count, invalid_count, error = self.import_service.import_excel_full(
            self.file_path, self.sheet_name, imported_by=self.username
        )
        self.finished.emit(batch_id, valid_count, invalid_count, error)


class StockComparePage(QWidget):
    
    def __init__(self, db: Database, username: str = None, role_code: str = None):
        super().__init__()
        self.db = db
        self.username = username or 'admin'
        self.role_code = role_code or 'store_manager'
        self.yys_import_service = YysStockImportService(db)
        self.jy_query_service = JyStockQueryService(db)
        self.compare_service = StockCompareService(db)
        self.api_service = YysApiService(db)
        self.db_config_service = DatabaseConfigService(db)
        self.data_permission_service = DataPermissionService(db)
        
        # 创建权限检查器
        self.permission_checker = PermissionChecker(db, self.username)
        
        self.current_batch_id = None
        self.sync_worker = None
        self.query_worker = None
        self.import_worker = None
        
        self._init_ui()
        self._load_batches()
        self._load_db_configs()
    
    def _init_ui(self):
        layout = QVBoxLayout(self)
        
        title = QLabel("库存对比")
        title.setStyleSheet("font-size: 18px; font-weight: bold;")
        layout.addWidget(title)
        
        import_group = QGroupBox("云药店库存导入")
        import_layout = QVBoxLayout(import_group)
        
        # Row 1: File selection
        file_row = QHBoxLayout()
        self.file_edit = QLineEdit()
        self.file_edit.setPlaceholderText("选择云药店库存Excel文件...")
        file_row.addWidget(self.file_edit)
        
        select_file_btn = QPushButton("选择文件")
        select_file_btn.clicked.connect(self._select_file)
        file_row.addWidget(select_file_btn)
        
        self.import_btn = QPushButton("导入")
        self.import_btn.clicked.connect(self._import_yys_stock)
        file_row.addWidget(self.import_btn)
        
        import_layout.addLayout(file_row)
        
        # Row 2: Batch selection
        batch_row = QHBoxLayout()
        batch_row.addWidget(QLabel("选择批次:"))
        self.batch_combo = QComboBox()
        self.batch_combo.setMinimumWidth(300)
        self.batch_combo.currentIndexChanged.connect(self._on_batch_changed)
        batch_row.addWidget(self.batch_combo)
        
        self.refresh_batch_btn = QPushButton("刷新批次")
        self.refresh_batch_btn.clicked.connect(self._load_batches)
        batch_row.addWidget(self.refresh_batch_btn)
        
        batch_row.addStretch()
        import_layout.addLayout(batch_row)
        
        layout.addWidget(import_group)
        
        query_group = QGroupBox("君元库存查询（从配置中心读取）")
        query_layout = QVBoxLayout(query_group)
        
        row1 = QHBoxLayout()
        row1.addWidget(QLabel("选择配置:"))
        self.db_config_combo = QComboBox()
        self.db_config_combo.setMinimumWidth(200)
        self.db_config_combo.currentIndexChanged.connect(self._on_db_config_changed)
        row1.addWidget(self.db_config_combo)
        
        self.refresh_config_btn = QPushButton("刷新配置")
        self.refresh_config_btn.clicked.connect(self._load_db_configs)
        row1.addWidget(self.refresh_config_btn)
        
        self.test_conn_btn = QPushButton("测试连接")
        self.test_conn_btn.clicked.connect(self._test_db_connection)
        row1.addWidget(self.test_conn_btn)
        
        row1.addStretch()
        query_layout.addLayout(row1)
        
        info_row = QHBoxLayout()
        info_row.addWidget(QLabel("当前连接:"))
        self.conn_info_label = QLabel("未选择配置")
        self.conn_info_label.setStyleSheet("color: #666;")
        info_row.addWidget(self.conn_info_label)
        info_row.addStretch()
        query_layout.addLayout(info_row)
        
        query_layout.addWidget(QLabel("查询SQL:"))
        self.sql_edit = QTextEdit()
        self.sql_edit.setPlaceholderText("输入查询君元库存的SQL语句，结果需包含药品编码、批号、库存数量等字段")
        self.sql_edit.setMaximumHeight(120)
        query_layout.addWidget(self.sql_edit)
        
        sql_btn_row = QHBoxLayout()
        
        self.save_sql_btn = QPushButton("保存SQL")
        self.save_sql_btn.clicked.connect(self._save_stock_query_sql)
        sql_btn_row.addWidget(self.save_sql_btn)
        
        sql_btn_row.addStretch()
        
        self.query_btn = QPushButton("预览")
        self.query_btn.clicked.connect(self._query_jy_stock)
        sql_btn_row.addWidget(self.query_btn)
        
        query_layout.addLayout(sql_btn_row)
        
        layout.addWidget(query_group)
        
        compare_group = QGroupBox("库存对比")
        compare_layout = QHBoxLayout(compare_group)
        
        self.compare_btn = QPushButton("执行对比")
        self.compare_btn.clicked.connect(self._compare_stock)
        compare_layout.addWidget(self.compare_btn)
        
        export_btn = QPushButton("导出Excel")
        export_btn.clicked.connect(self._export_excel)
        compare_layout.addWidget(export_btn)
        
        self.match_label = QLabel("匹配: 0")
        self.diff_label = QLabel("差异: 0")
        self.yys_only_label = QLabel("云药店独有: 0")
        
        compare_layout.addWidget(self.match_label)
        compare_layout.addWidget(self.diff_label)
        compare_layout.addWidget(self.yys_only_label)
        
        layout.addWidget(compare_group)
        
        sync_group = QGroupBox("差异同步")
        sync_layout = QHBoxLayout(sync_group)
        
        self.api_config_combo = QComboBox()
        self._load_api_configs()
        sync_layout.addWidget(QLabel("API配置:"))
        sync_layout.addWidget(self.api_config_combo)
        
        test_api_btn = QPushButton("测试API")
        self.test_api_btn = test_api_btn
        self.test_api_btn.setText("测试API")
        self.test_api_btn.clicked.connect(self._test_api_connection)
        sync_layout.addWidget(self.test_api_btn)
        
        self.sync_btn = QPushButton("同步差异库存")
        self.sync_btn.clicked.connect(self._sync_diff_stock)
        sync_layout.addWidget(self.sync_btn)
        
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        sync_layout.addWidget(self.progress_bar)
        
        layout.addWidget(sync_group)
        
        # 查询条件区域
        query_group = QGroupBox("查询条件")
        query_layout = QHBoxLayout(query_group)
        
        query_layout.addWidget(QLabel("药品编码:"))
        self.productno_edit = QLineEdit()
        self.productno_edit.setPlaceholderText("输入药品编码")
        self.productno_edit.setMaximumWidth(120)
        query_layout.addWidget(self.productno_edit)
        
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
        
        query_layout.addWidget(QLabel("对比状态:"))
        self.compare_status_combo = QComboBox()
        self.compare_status_combo.addItem("全部", "")
        self.compare_status_combo.addItem("匹配", "match")
        self.compare_status_combo.addItem("差异", "diff")
        self.compare_status_combo.addItem("云药店独有", "yys_only")
        self.compare_status_combo.addItem("君元独有", "jy_only")
        query_layout.addWidget(self.compare_status_combo)
        
        query_layout.addWidget(QLabel("同步状态:"))
        self.sync_status_combo = QComboBox()
        self.sync_status_combo.addItem("全部", "")
        self.sync_status_combo.addItem("待同步", "pending")
        self.sync_status_combo.addItem("成功", "success")
        self.sync_status_combo.addItem("失败", "failed")
        self.sync_status_combo.addItem("跳过", "skipped")
        query_layout.addWidget(self.sync_status_combo)
        
        query_btn = QPushButton("查询")
        query_btn.clicked.connect(self._query_results)
        query_layout.addWidget(query_btn)
        
        clear_btn = QPushButton("清空")
        clear_btn.clicked.connect(self._clear_query)
        query_layout.addWidget(clear_btn)
        
        query_layout.addStretch()
        
        layout.addWidget(query_group)
        
        self.result_table = QTableWidget()
        self.result_table.setColumnCount(10)
        self.result_table.setHorizontalHeaderLabels([
            "药品编码", "药品名称", "批号", "君元库存", "云药店库存", "差异",
            "对比状态", "同步状态", "同步时间", "同步消息"
        ])
        self.result_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.result_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.result_table.setSortingEnabled(True)  # 启用点击表头排序
        
        layout.addWidget(self.result_table)
    
    def _load_db_configs(self):
        configs = self.db_config_service.get_all_configs()
        self.db_config_combo.clear()
        
        for config in configs:
            self.db_config_combo.addItem(config.name, config.id)
        
        if configs:
            self._on_db_config_changed(0)
    
    def _on_db_config_changed(self, index):
        config_id = self.db_config_combo.currentData()
        
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
    
    def _save_stock_query_sql(self):
        config_id = self.db_config_combo.currentData()
        
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
    
    def _export_excel(self):
        # 权限检查
        if not self.permission_checker.check_permission(PermissionCodes.OP_YYS_STOCK_EXPORT_RESULT, self):
            return
        
        if not self.current_batch_id:
            QMessageBox.warning(self, "提示", "请先执行库存对比")
            return
        
        results = self.compare_service.get_compare_results(self.current_batch_id)
        
        if not results:
            QMessageBox.warning(self, "提示", "没有对比结果可导出")
            return
        
        # 选择保存路径，文件名包含批次ID
        default_name = f"库存对比_{self.current_batch_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
        file_path, _ = QFileDialog.getSaveFileName(self, "保存Excel", default_name, "Excel文件 (*.xlsx)")
        
        if not file_path:
            return
        
        try:
            # 准备数据，包含批次信息
            data = []
            for result in results:
                compare_status = result['compare_status'] or ""
                status_text = {'match': '匹配', 'diff': '差异', 'yys_only': '云药店独有', 'jy_only': '君元独有'}.get(compare_status, compare_status)
                
                sync_status = result['sync_status'] or ""
                sync_text = {'pending': '待同步', 'success': '成功', 'failed': '失败', 'skipped': '跳过'}.get(sync_status, sync_status)
                
                data.append({
                    '批次号': self.current_batch_id,
                    '药品编码': result['oldproductno'] or "",
                    '药品名称': result['productname'] or "",
                    '批号': result['lotno'] or "",
                    '君元库存': result['jy_quantity'] or 0,
                    '云药店库存': result['yys_quantity'] or 0,
                    '差异': result['diff_quantity'] or 0,
                    '对比状态': status_text,
                    '同步状态': sync_text,
                    '同步时间': result['sync_time'] or "",
                    '同步消息': result['sync_message'] or ""
                })
            
            # 导出Excel
            df = pd.DataFrame(data)
            df.to_excel(file_path, index=False, engine='openpyxl')
            
            QMessageBox.information(self, "成功", f"导出成功\n文件路径: {file_path}")
            
        except Exception as e:
            logging.error(f"导出Excel失败: {e}")
            QMessageBox.warning(self, "错误", f"导出失败: {e}")
    
    def _load_api_configs(self):
        try:
            conn = self.db.get_connection()
            cursor = conn.cursor()
            
            cursor.execute('''
                SELECT config_id, config_name
                FROM yys_api_config
                WHERE enabled = 1
                ORDER BY created_at DESC
            ''')
            
            rows = cursor.fetchall()
            
            self.api_config_combo.clear()
            
            for row in rows:
                self.api_config_combo.addItem(row['config_name'], row['config_id'])
            
        except Exception as e:
            logging.error(f"加载API配置失败: {e}")
    
    def _select_file(self):
        file_path, _ = QFileDialog.getOpenFileName(self, "选择云药店库存文件", "", "Excel文件 (*.xlsx *.xls)")
        
        if file_path:
            self.file_edit.setText(file_path)
    
    def _import_yys_stock(self):
        # 权限检查
        if not self.permission_checker.check_permission(PermissionCodes.OP_YYS_STOCK_IMPORT_EXCEL, self):
            return
        
        file_path = self.file_edit.text()
        
        if not file_path:
            QMessageBox.warning(self, "提示", "请选择Excel文件")
            return
        
        sheets, error = self.yys_import_service.get_sheets(file_path)
        
        if error:
            QMessageBox.warning(self, "错误", error)
            return
        
        self.import_btn.setEnabled(False)
        self.import_btn.setText("导入中...")
        
        self.import_worker = ImportWorker(self.yys_import_service, file_path, sheets[0], self.username)
        self.import_worker.finished.connect(self._on_import_finished)
        self.import_worker.start()
    
    def _on_import_finished(self, batch_id, valid_count, invalid_count, error):
        self.import_btn.setEnabled(True)
        self.import_btn.setText("导入")
        
        if error:
            QMessageBox.warning(self, "错误", error)
            return
        
        self.current_batch_id = batch_id
        
        # Refresh batch list and select the new batch
        self._load_batches()
        
        # Find and select the new batch in combo
        for i in range(self.batch_combo.count()):
            if self.batch_combo.itemData(i) == batch_id:
                self.batch_combo.setCurrentIndex(i)
                break
        
        QMessageBox.information(self, "成功", f"导入成功\n批次号: {batch_id}\n有效记录: {valid_count}\n无效记录: {invalid_count}")
    
    def _load_batches(self):
        self.batch_combo.clear()
        # 使用数据权限服务获取过滤后的批次
        batches = self.data_permission_service.get_filtered_batches(
            'yys_import_batch', self.role_code, self.username,
            order_by="imported_at DESC"
        )
        for batch in batches:
            batch_id = batch.get('batch_id', '')
            batch_name = batch.get('batch_name', '')
            valid_count = batch.get('valid_count', 0)
            imported_at = batch.get('imported_at', '')
            display_text = f"{batch_name} ({valid_count}条) - {imported_at[:10] if imported_at else ''}"
            self.batch_combo.addItem(display_text, batch_id)
        
        if batches:
            self.batch_combo.setCurrentIndex(0)
            self.current_batch_id = batches[0].get('batch_id', '')
    
    def _on_batch_changed(self, index):
        if index >= 0:
            self.current_batch_id = self.batch_combo.currentData()
    
    def _test_db_connection(self):
        config_id = self.db_config_combo.currentData()
        
        if not config_id:
            QMessageBox.warning(self, "提示", "请选择数据库配置")
            return
        
        success, message = self.jy_query_service.test_connection(config_id)
        
        if success:
            QMessageBox.information(self, "成功", message)
        else:
            QMessageBox.warning(self, "失败", message)
    
    def _query_jy_stock(self):
        # 权限检查
        if not self.permission_checker.check_permission(PermissionCodes.OP_YYS_STOCK_QUERY_JY_STOCK, self):
            return
        
        if not self.current_batch_id:
            QMessageBox.warning(self, "提示", "请先导入云药店库存")
            return
        
        config_id = self.db_config_combo.currentData()
        
        if not config_id:
            QMessageBox.warning(self, "提示", "请选择数据库配置")
            return
        
        custom_sql = self.sql_edit.toPlainText().strip()
        
        if not custom_sql:
            QMessageBox.warning(self, "提示", "请输入查询SQL")
            return
        
        self.jy_query_service.clear_query_results(self.current_batch_id)
        
        self.query_btn.setEnabled(False)
        
        query_count, _, error = self.jy_query_service.query_stock(config_id, self.current_batch_id, custom_sql)
        
        self.query_btn.setEnabled(True)
        
        if error:
            QMessageBox.warning(self, "错误", error)
            return
        
        QMessageBox.information(self, "成功", f"查询成功\n查询记录数: {query_count}")
    
    def _compare_stock(self):
        # 权限检查
        if not self.permission_checker.check_permission(PermissionCodes.OP_YYS_STOCK_COMPARE_STOCK, self):
            return
        
        if not self.current_batch_id:
            QMessageBox.warning(self, "提示", "请先导入云药店库存")
            return
        
        config_id = self.db_config_combo.currentData()
        
        if not config_id:
            QMessageBox.warning(self, "提示", "请选择数据库配置")
            return
        
        custom_sql = self.sql_edit.toPlainText().strip()
        
        if not custom_sql:
            QMessageBox.warning(self, "提示", "请输入查询SQL")
            return
        
        # 先查询君元库存
        self.jy_query_service.clear_query_results(self.current_batch_id)
        
        self.query_btn.setEnabled(False)
        self.compare_btn.setEnabled(False)
        
        query_count, _, error = self.jy_query_service.query_stock(config_id, self.current_batch_id, custom_sql)
        
        self.query_btn.setEnabled(True)
        self.compare_btn.setEnabled(True)
        
        if error:
            QMessageBox.warning(self, "错误", f"查询君元库存失败: {error}")
            return
        
        # 然后执行对比
        match_count, diff_count, yys_only_count, error = self.compare_service.compare_stock(self.current_batch_id, self.username)
        
        if error:
            QMessageBox.warning(self, "错误", error)
            return
        
        self.match_label.setText(f"匹配: {match_count}")
        self.diff_label.setText(f"差异: {diff_count}")
        self.yys_only_label.setText(f"云药店独有: {yys_only_count}")
        
        self._load_compare_results()
        
        QMessageBox.information(self, "成功", f"对比完成\n君元库存查询: {query_count}条\n匹配: {match_count}\n差异: {diff_count}\n云药店独有: {yys_only_count}")
    
    def _query_results(self):
        if not self.current_batch_id:
            QMessageBox.warning(self, "提示", "请先执行库存对比")
            return
        
        self._load_compare_results()
    
    def _clear_query(self):
        self.productno_edit.clear()
        self.productname_edit.clear()
        self.lotno_edit.clear()
        self.compare_status_combo.setCurrentIndex(0)
        self.sync_status_combo.setCurrentIndex(0)
        
        if self.current_batch_id:
            self._load_compare_results()
    
    def _load_compare_results(self):
        if not self.current_batch_id:
            return
        
        # 禁用排序以便正确设置数据
        self.result_table.setSortingEnabled(False)
        
        compare_status = self.compare_status_combo.currentData()
        sync_status = self.sync_status_combo.currentData()
        productno = self.productno_edit.text().strip()
        productname = self.productname_edit.text().strip()
        lotno = self.lotno_edit.text().strip()
        
        results = self.compare_service.get_compare_results(
            self.current_batch_id, compare_status, sync_status, productno, productname, lotno
        )
        
        self.result_table.setRowCount(len(results))
        
        for row_idx, result in enumerate(results):
            self.result_table.setItem(row_idx, 0, QTableWidgetItem(result['oldproductno'] or ""))
            self.result_table.setItem(row_idx, 1, QTableWidgetItem(result['productname'] or ""))
            self.result_table.setItem(row_idx, 2, QTableWidgetItem(result['lotno'] or ""))
            self.result_table.setItem(row_idx, 3, QTableWidgetItem(str(result['jy_quantity'] or 0)))
            self.result_table.setItem(row_idx, 4, QTableWidgetItem(str(result['yys_quantity'] or 0)))
            self.result_table.setItem(row_idx, 5, QTableWidgetItem(str(result['diff_quantity'] or 0)))
            
            compare_status = result['compare_status'] or ""
            status_text = {'match': '匹配', 'diff': '差异', 'yys_only': '云药店独有', 'jy_only': '君元独有'}.get(compare_status, compare_status)
            self.result_table.setItem(row_idx, 6, QTableWidgetItem(status_text))
            
            sync_status = result['sync_status'] or ""
            sync_text = {'pending': '待同步', 'success': '成功', 'failed': '失败', 'skipped': '跳过'}.get(sync_status, sync_status)
            self.result_table.setItem(row_idx, 7, QTableWidgetItem(sync_text))
            
            self.result_table.setItem(row_idx, 8, QTableWidgetItem(result['sync_time'] or ""))
            self.result_table.setItem(row_idx, 9, QTableWidgetItem(result['sync_message'] or ""))
        
        # 重新启用排序
        self.result_table.setSortingEnabled(True)
    
    def _test_api_connection(self):
        # 权限检查
        if not self.permission_checker.check_permission(PermissionCodes.OP_YYS_STOCK_TEST_API_SYNC, self):
            return
        
        if not self.current_batch_id:
            QMessageBox.warning(self, "提示", "请先执行库存对比")
            return

        config_id = self.api_config_combo.currentData()

        if not config_id:
            QMessageBox.warning(self, "提示", "请选择API配置")
            return

        diff_items = self.compare_service.get_diff_items(self.current_batch_id)

        if not diff_items:
            QMessageBox.information(self, "提示", "没有待同步的差异库存")
            return

        sample_count = min(5, len(diff_items))
        sample_items = random.sample(diff_items, sample_count)

        reply = QMessageBox.question(
            self,
            "确认测试API",
            f"测试API会随机抽取 {sample_count} 条待同步数据并真实同步到云药店，完成后更新状态。\n确定继续吗？",
            QMessageBox.Yes | QMessageBox.No
        )

        if reply != QMessageBox.Yes:
            return

        self.test_api_btn.setEnabled(False)
        self.sync_btn.setEnabled(False)
        self.progress_bar.setVisible(True)
        self.progress_bar.setMaximum(sample_count)
        self.progress_bar.setValue(0)

        self.sync_worker = SyncWorker(self.api_service, config_id, sample_items)
        self.sync_worker.progress.connect(self._on_sync_progress)
        self.sync_worker.finished.connect(self._on_test_api_finished)
        self.sync_worker.start()
    
    def _sync_diff_stock(self):
        # 权限检查
        if not self.permission_checker.check_permission(PermissionCodes.OP_YYS_STOCK_SYNC_DIFF, self):
            return
        
        if not self.current_batch_id:
            QMessageBox.warning(self, "提示", "请先执行库存对比")
            return
        
        config_id = self.api_config_combo.currentData()
        
        if not config_id:
            QMessageBox.warning(self, "提示", "请选择API配置")
            return
        
        diff_items = self.compare_service.get_diff_items(self.current_batch_id)
        
        if not diff_items:
            QMessageBox.information(self, "提示", "没有需要同步的差异库存")
            return
        
        reply = QMessageBox.question(self, "确认", f"确定要同步 {len(diff_items)} 条差异库存吗？", QMessageBox.Yes | QMessageBox.No)
        
        if reply != QMessageBox.Yes:
            return
        
        self.sync_btn.setEnabled(False)
        self.progress_bar.setVisible(True)
        self.progress_bar.setMaximum(len(diff_items))
        self.progress_bar.setValue(0)
        
        self.sync_worker = SyncWorker(self.api_service, config_id, diff_items)
        self.sync_worker.progress.connect(self._on_sync_progress)
        self.sync_worker.finished.connect(self._on_sync_finished)
        self.sync_worker.start()
    
    def _on_sync_progress(self, current, total, status, message):
        self.progress_bar.setValue(current)
    
    def _on_sync_finished(self, success, failed, skipped):
        self.sync_btn.setEnabled(True)
        self.test_api_btn.setEnabled(True)
        self.progress_bar.setVisible(False)
        
        self._load_compare_results()
        
        QMessageBox.information(self, "完成", f"同步完成\n成功: {success}\n失败: {failed}\n跳过: {skipped}")

    def _on_test_api_finished(self, success, failed, skipped):
        self.test_api_btn.setEnabled(True)
        self.sync_btn.setEnabled(True)
        self.progress_bar.setVisible(False)

        self._load_compare_results()

        QMessageBox.information(
            self,
            "测试API完成",
            f"测试API完成\n成功: {success}\n失败: {failed}\n跳过: {skipped}"
        )
