import json
import os
import shutil
import subprocess
import threading
import urllib.request
from pathlib import Path

from PySide6.QtCore import QObject, QThread, Signal, Slot
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QLineEdit,
    QComboBox, QFileDialog, QGroupBox, QTableWidget, QTableWidgetItem,
    QMessageBox, QTextEdit, QCheckBox, QHeaderView, QApplication
)

from app.core.smart_purchase_service import SmartPurchaseService
from app.core.permission_checker import PermissionChecker, PermissionCodes
from app.core.permission_service import PermissionService
from app.core.data_permission_service import DataPermissionService
from app.storage.database import Database


class SmartPurchaseWorker(QObject):
    progress = Signal(str)
    web_error = Signal(str)
    finished = Signal(dict, list, str)
    
    def __init__(self, db_path: Path, batch_id: str, use_cart_adapter: bool, retry_failed: bool = False):
        super().__init__()
        self.db_path = db_path
        self.batch_id = batch_id
        self.use_cart_adapter = use_cart_adapter
        self.retry_failed = retry_failed
        self._web_decision_event = threading.Event()
        self._web_decision_continue = False
        self._stop_event = threading.Event()
    
    @Slot()
    def run(self):
        db = Database(self.db_path)
        try:
            service = SmartPurchaseService(db)
            summary, logs, error = service.execute_batch_purchase_real(
                self.batch_id,
                retry_failed=self.retry_failed,
                use_cart_adapter=self.use_cart_adapter,
                progress_callback=self.progress.emit,
                web_error_callback=self._ask_web_continue,
                pause_callback=self._should_stop
            )
            self.finished.emit(summary or {}, logs or [], error or "")
        except Exception as e:
            self.finished.emit({}, [], str(e))
        finally:
            db.close()

    def _ask_web_continue(self, message: str) -> bool:
        self._web_decision_continue = False
        self._web_decision_event.clear()
        self.web_error.emit(message)
        self._web_decision_event.wait()
        return self._web_decision_continue
    
    @Slot(bool)
    def set_web_decision(self, should_continue: bool):
        self._web_decision_continue = should_continue
        self._web_decision_event.set()

    def _should_stop(self) -> bool:
        return self._stop_event.is_set()

    @Slot()
    def request_stop(self):
        self._stop_event.set()
        self._web_decision_continue = False
        self._web_decision_event.set()
        self.progress.emit("已请求停止，当前品种处理完成后结束本次采购")


class CartBackfillWorker(QObject):
    progress = Signal(str)
    finished = Signal(dict, list, str)

    def __init__(self, db_path: Path, batch_id: str):
        super().__init__()
        self.db_path = db_path
        self.batch_id = batch_id

    @Slot()
    def run(self):
        db = Database(self.db_path)
        try:
            service = SmartPurchaseService(db)
            summary, logs, error = service.execute_cart_backfill(
                self.batch_id,
                progress_callback=self.progress.emit
            )
            self.finished.emit(summary or {}, logs or [], error or "")
        except Exception as e:
            self.finished.emit({}, [], str(e))
        finally:
            db.close()


class SmartPurchasePage(QWidget):
    YSBANG_URL = "https://dian.ysbang.cn/#/home"
    CDP_JSON_URL = "http://127.0.0.1:9222/json/list"
    SUPPLIER_SCOPE_SETTING_KEY = "smart_purchase_supplier_scope"
    KEEP_CART_SETTING_KEY = "smart_purchase_keep_cart"
    
    def __init__(self, db, username: str = None, role_code: str = None):
        super().__init__()
        self.db = db
        self.username = username or 'admin'
        self.role_code = role_code or 'store_manager'
        self.service = SmartPurchaseService(db)
        self.data_permission_service = DataPermissionService(db)
        
        # 创建权限检查器
        self.permission_checker = PermissionChecker(db, self.username)
        self.permission_service = PermissionService(db)
        
        self.excel_file_path = ""
        self.headers = []
        self.preview_rows = []
        self.purchase_thread = None
        self.purchase_worker = None
        self.purchase_stop_requested = False
        self.cart_backfill_thread = None
        self.cart_backfill_worker = None
        self._init_ui()
        self._load_purchase_settings()
        self._load_batches()
    
    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(10)
        
        import_group = QGroupBox("采购目录导入")
        import_layout = QVBoxLayout(import_group)
        
        file_row = QHBoxLayout()
        file_row.addWidget(QLabel("Excel文件:"))
        self.file_path_input = QLineEdit()
        self.file_path_input.setReadOnly(True)
        self.file_path_input.setMinimumWidth(360)
        file_row.addWidget(self.file_path_input)
        
        self.select_file_btn = QPushButton("选择文件")
        self.select_file_btn.clicked.connect(self._select_file)
        file_row.addWidget(self.select_file_btn)
        
        file_row.addWidget(QLabel("工作表:"))
        self.sheet_combo = QComboBox()
        self.sheet_combo.setMinimumWidth(160)
        file_row.addWidget(self.sheet_combo)
        
        self.preview_btn = QPushButton("预览数据")
        self.preview_btn.clicked.connect(self._preview_data)
        file_row.addWidget(self.preview_btn)
        
        self.import_btn = QPushButton("导入系统")
        self.import_btn.clicked.connect(self._import_data)
        self.import_btn.setEnabled(False)
        file_row.addWidget(self.import_btn)
        
        file_row.addStretch()
        import_layout.addLayout(file_row)
        
        rule_row = QHBoxLayout()
        rule_row.addWidget(QLabel("供应商范围:"))
        self.supplier_scope_input = QLineEdit()
        self.supplier_scope_input.setPlaceholderText("例如：小药精, 采药易, 药中缘；每次采购前需重新确认")
        rule_row.addWidget(self.supplier_scope_input)
        
        self.save_supplier_scope_btn = QPushButton("保存配置")
        self.save_supplier_scope_btn.clicked.connect(self._save_purchase_settings)
        rule_row.addWidget(self.save_supplier_scope_btn)
        
        self.keep_cart_check = QCheckBox("允许购物车保留原有商品")
        self.keep_cart_check.setChecked(True)
        rule_row.addWidget(self.keep_cart_check)
        import_layout.addLayout(rule_row)
        
        layout.addWidget(import_group)
        
        batch_group = QGroupBox("采购批次")
        batch_layout = QHBoxLayout(batch_group)
        
        batch_layout.addWidget(QLabel("导入批次:"))
        self.batch_combo = QComboBox()
        self.batch_combo.setMinimumWidth(360)
        self.batch_combo.currentIndexChanged.connect(self._on_batch_changed)
        batch_layout.addWidget(self.batch_combo)
        
        self.refresh_batch_btn = QPushButton("刷新")
        self.refresh_batch_btn.clicked.connect(self._load_batches)
        batch_layout.addWidget(self.refresh_batch_btn)
        
        self.delete_batch_btn = QPushButton("删除批次")
        self.delete_batch_btn.clicked.connect(self._delete_batch)
        batch_layout.addWidget(self.delete_batch_btn)
        
        batch_layout.addWidget(QLabel("状态:"))
        self.status_combo = QComboBox()
        self.status_combo.addItem("全部", "all")
        self.status_combo.addItem("待处理", "pending")
        self.status_combo.addItem("成功", "success")
        self.status_combo.addItem("失败", "failed")
        self.status_combo.addItem("无效", "invalid")
        self.status_combo.currentIndexChanged.connect(self._load_batch_items)
        batch_layout.addWidget(self.status_combo)
        
        batch_layout.addWidget(QLabel("关键字:"))
        self.keyword_input = QLineEdit()
        self.keyword_input.setMaximumWidth(180)
        self.keyword_input.setPlaceholderText("编码/名称/批准文号")
        self.keyword_input.textChanged.connect(self._load_batch_items)
        batch_layout.addWidget(self.keyword_input)
        
        batch_layout.addStretch()
        layout.addWidget(batch_group)
        
        self.summary_label = QLabel("未导入采购目录")
        self.summary_label.setStyleSheet("color: #555;")
        layout.addWidget(self.summary_label)
        
        self.table = QTableWidget()
        self.table.setAlternatingRowColors(True)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        layout.addWidget(self.table, 1)
        
        control_group = QGroupBox("执行控制")
        control_layout = QHBoxLayout(control_group)
        
        self.start_purchase_btn = QPushButton("开始逐个采购")
        self.start_purchase_btn.clicked.connect(self._start_purchase)
        self.start_purchase_btn.setStyleSheet("background-color: #4CAF50; color: white;")
        control_layout.addWidget(self.start_purchase_btn)

        self.pause_purchase_btn = QPushButton("停止")
        self.pause_purchase_btn.clicked.connect(self._stop_purchase)
        self.pause_purchase_btn.setEnabled(False)
        control_layout.addWidget(self.pause_purchase_btn)
        
        self.cart_adapter_check = QCheckBox("连接药师帮购物车真实加购")
        self.cart_adapter_check.setChecked(True)
        self.cart_adapter_check.setToolTip("需要浏览器以 --remote-debugging-port=9222 打开并已登录 dian.ysbang.cn")
        control_layout.addWidget(self.cart_adapter_check)
        
        self.retry_btn = QPushButton("二次重试")
        self.retry_btn.clicked.connect(self._retry_failed_purchase)
        control_layout.addWidget(self.retry_btn)

        self.cart_backfill_btn = QPushButton("购物车反写")
        self.cart_backfill_btn.clicked.connect(self._start_cart_backfill)
        self.cart_backfill_btn.setToolTip("只读取当前药师帮购物车并反写当前采购批次，不执行加购")
        control_layout.addWidget(self.cart_backfill_btn)
        
        self.export_btn = QPushButton("导出结果")
        self.export_btn.clicked.connect(self._export_results)
        control_layout.addWidget(self.export_btn)
        
        self.clear_cart_btn = QPushButton("清空购物车")
        self.clear_cart_btn.clicked.connect(self._clear_cart)
        self.clear_cart_btn.setStyleSheet("background-color: #f44336; color: white;")
        self.clear_cart_btn.setToolTip("清空药师帮购物车中的所有商品")
        control_layout.addWidget(self.clear_cart_btn)
        
        control_layout.addStretch()
        layout.addWidget(control_group)
        
        log_group = QGroupBox("执行日志")
        log_layout = QVBoxLayout(log_group)
        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setMaximumHeight(120)
        log_layout.addWidget(self.log_text)
        layout.addWidget(log_group)
    
    def _load_purchase_settings(self):
        supplier_scope = self.db.get_setting(self.SUPPLIER_SCOPE_SETTING_KEY) or ""
        keep_cart = self.db.get_setting(self.KEEP_CART_SETTING_KEY)
        if supplier_scope:
            self.supplier_scope_input.setText(supplier_scope)
        if keep_cart is not None:
            self.keep_cart_check.setChecked(keep_cart == "1")
    
    def _save_purchase_settings(self, show_message: bool = True):
        # 权限检查
        if not self.permission_checker.check_permission(PermissionCodes.OP_CONFIG_SAVE_SUPPLIER_SCOPE, self):
            return
        
        supplier_scope = self.supplier_scope_input.text().strip()
        keep_cart = "1" if self.keep_cart_check.isChecked() else "0"
        
        self.db.set_setting(self.SUPPLIER_SCOPE_SETTING_KEY, supplier_scope)
        self.db.set_setting(self.KEEP_CART_SETTING_KEY, keep_cart)
        
        # 记录操作日志
        self.permission_service.log_operation(
            username=self.username,
            operation_type='config_save',
            operation_desc='保存智能采购供应商范围配置',
            target_type='smart_purchase_config',
            target_id='supplier_scope',
            detail={'supplier_scope': supplier_scope, 'keep_cart': keep_cart}
        )
        
        self._append_log("智能采购供应商配置已保存")
        if show_message:
            QMessageBox.information(self, "保存成功", "供应商范围配置已保存")
    
    def _select_file(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "选择采购目录Excel",
            "",
            "Excel Files (*.xlsx *.xls)"
        )
        if not file_path:
            return
        
        self.excel_file_path = file_path
        self.file_path_input.setText(file_path)
        self.sheet_combo.clear()
        
        sheets, error = self.service.get_sheets(file_path)
        if error:
            QMessageBox.warning(self, "错误", f"读取工作表失败:\n{error}")
            return
        
        self.sheet_combo.addItems(sheets)
        self._append_log(f"已选择采购目录：{file_path}")
    
    def _preview_data(self):
        if not self.excel_file_path:
            QMessageBox.warning(self, "提示", "请先选择采购目录Excel")
            return
        
        headers, rows, error = self.service.read_preview(
            self.excel_file_path,
            self.sheet_combo.currentText(),
            max_rows=100
        )
        if error:
            QMessageBox.warning(self, "错误", f"预览失败:\n{error}")
            return
        
        self.headers = headers
        self.preview_rows = rows
        self._show_preview(headers, rows)
        self.import_btn.setEnabled(True)
        self.summary_label.setText(f"预览 {len(rows)} 条，字段 {len(headers)} 个")
        self._append_log(f"预览完成：{len(rows)} 条，字段 {len(headers)} 个")
    
    def _import_data(self):
        # 权限检查
        if not self.permission_checker.check_permission(PermissionCodes.OP_SMART_PURCHASE_IMPORT_EXCEL, self):
            return
        
        if not self.excel_file_path:
            QMessageBox.warning(self, "提示", "请先选择采购目录Excel")
            return
        
        self._save_purchase_settings(show_message=False)
        
        batch_id, valid_count, invalid_count, error = self.service.import_excel(
            self.excel_file_path,
            self.sheet_combo.currentText(),
            supplier_scope=self.supplier_scope_input.text().strip(),
            allow_keep_cart=self.keep_cart_check.isChecked(),
            imported_by=self.username
        )
        if error:
            QMessageBox.warning(self, "错误", f"导入失败:\n{error}")
            return
        
        QMessageBox.information(
            self,
            "成功",
            f"导入完成\n批次号: {batch_id}\n有效: {valid_count}\n无效: {invalid_count}"
        )
        self._append_log(f"导入完成：{batch_id}，有效 {valid_count}，无效 {invalid_count}")
        self._load_batches(select_batch_id=batch_id)
    
    def _load_batches(self, select_batch_id: str = ""):
        # 使用数据权限服务获取过滤后的批次
        batches = self.data_permission_service.get_filtered_batches(
            'smart_purchase_batches', self.role_code, self.username,
            order_by="imported_at DESC"
        )
        self.batch_combo.blockSignals(True)
        self.batch_combo.clear()
        for batch in batches:
            text = (
                f"{batch['batch_name']} | {batch['batch_id']} | "
                f"总{batch['total_count']} 有效{batch['valid_count']} 无效{batch['invalid_count']}"
            )
            self.batch_combo.addItem(text, batch["batch_id"])
        self.batch_combo.blockSignals(False)
        
        if select_batch_id:
            index = self.batch_combo.findData(select_batch_id)
            if index >= 0:
                self.batch_combo.setCurrentIndex(index)
        elif batches:
            self.batch_combo.setCurrentIndex(0)
        
        self._load_batch_items()
    
    def _on_batch_changed(self, *_args):
        self._load_batch_items()
    
    def _load_batch_items(self, *_args):
        batch_id = self.batch_combo.currentData()
        if not batch_id:
            self.table.setRowCount(0)
            self.summary_label.setText("未选择采购批次")
            return
        
        rows = self.service.get_batch_items(
            batch_id,
            status_filter=self.status_combo.currentData(),
            keyword=self.keyword_input.text().strip()
        )
        keys = [
            "row_number", "item_code", "source_name", "source_spec", "source_maker",
            "source_approval", "purchase_quantity", "expected_price",
            "smart_supplier", "smart_price", "ysb_code", "import_status",
            "purchase_status", "purchase_reason", "actual_ysb_code",
            "purchase_supplier", "purchase_product", "purchase_spec", "purchase_maker",
            "purchase_valid_date", "purchase_quantity_result", "purchase_price"
        ]
        headers = [
            "行号", "商品编码", "商品名称", "规格", "厂家", "批准文号",
            "采购数量", "期望价格", "智能供应商", "智能价格",
            "药师帮编码", "导入状态", "采购状态", "原因", "实际药师帮编码",
            "采购供应商", "采购商品", "采购规格", "采购厂家", "有效期", "采购数量结果", "采购价格",
        ]
        
        self.table.setSortingEnabled(False)
        self.table.setColumnCount(len(headers))
        self.table.setHorizontalHeaderLabels(headers)
        self.table.setRowCount(len(rows))
        
        for row_index, row in enumerate(rows):
            for col_index, key in enumerate(keys):
                value = row.get(key, "")
                self.table.setItem(row_index, col_index, QTableWidgetItem(str(value) if value is not None else ""))
        
        self.table.resizeColumnsToContents()
        self.table.setSortingEnabled(True)
        self.summary_label.setText(f"当前显示 {len(rows)} 条采购明细")
    
    def _show_preview(self, headers, rows):
        self.table.setSortingEnabled(False)
        self.table.setColumnCount(len(headers))
        self.table.setHorizontalHeaderLabels(headers)
        self.table.setRowCount(len(rows))
        for row_index, row in enumerate(rows):
            for col_index, value in enumerate(row):
                self.table.setItem(row_index, col_index, QTableWidgetItem(str(value)))
        self.table.resizeColumnsToContents()
        self.table.setSortingEnabled(True)
    
    def _delete_batch(self):
        batch_id = self.batch_combo.currentData()
        if not batch_id:
            QMessageBox.warning(self, "提示", "请选择要删除的批次")
            return
        
        reply = QMessageBox.question(
            self,
            "确认删除",
            "确定删除当前智能采购批次及明细吗？",
            QMessageBox.Yes | QMessageBox.No
        )
        if reply != QMessageBox.Yes:
            return
        
        success, error = self.service.delete_batch(batch_id)
        if success:
            self._append_log(f"已删除采购批次：{batch_id}")
            self._load_batches()
        else:
            QMessageBox.warning(self, "错误", error)
    
    def _start_purchase(self):
        self._run_purchase(retry_failed=False)
    
    def _retry_failed_purchase(self):
        # 权限检查
        if not self.permission_checker.check_permission(PermissionCodes.OP_SMART_PURCHASE_RETRY_FAILED, self):
            return
        
        self._run_purchase(retry_failed=True)

    def _start_cart_backfill(self):
        # 权限检查
        if not self.permission_checker.check_permission(PermissionCodes.OP_SMART_PURCHASE_CART_BACKFILL, self):
            return
        
        batch_id = self.batch_combo.currentData()
        if not batch_id:
            QMessageBox.warning(self, "提示", "请先选择采购批次")
            return
        if not self._ensure_ysbang_browser_ready():
            return

        reply = QMessageBox.question(
            self,
            "确认购物车反写",
            "将只读取当前药师帮购物车，并反写当前采购批次中匹配到的明细。\n\n"
            "不会执行加购；购物车未匹配到的明细不会修改原状态。\n\n"
            "确定开始反写吗？",
            QMessageBox.Yes | QMessageBox.No
        )
        if reply != QMessageBox.Yes:
            return

        self.start_purchase_btn.setEnabled(False)
        self.retry_btn.setEnabled(False)
        self.cart_backfill_btn.setEnabled(False)
        self._append_log("开始购物车反写...")

        self.cart_backfill_thread = QThread(self)
        self.cart_backfill_worker = CartBackfillWorker(Path(self.db.db_path), batch_id)
        self.cart_backfill_worker.moveToThread(self.cart_backfill_thread)
        self.cart_backfill_thread.started.connect(self.cart_backfill_worker.run)
        self.cart_backfill_worker.progress.connect(self._append_log)
        self.cart_backfill_worker.finished.connect(self._on_cart_backfill_finished)
        self.cart_backfill_worker.finished.connect(self.cart_backfill_thread.quit)
        self.cart_backfill_worker.finished.connect(self.cart_backfill_worker.deleteLater)
        self.cart_backfill_thread.finished.connect(self.cart_backfill_thread.deleteLater)
        self.cart_backfill_thread.start()
    
    def _run_purchase(self, retry_failed: bool = False):
        # 权限检查
        if not self.permission_checker.check_permission(PermissionCodes.OP_SMART_PURCHASE_RUN_ONE_BY_ONE, self):
            return
        
        batch_id = self.batch_combo.currentData()
        if not batch_id:
            QMessageBox.warning(self, "提示", "请先选择采购批次")
            return
        
        action_title = "二次重试" if retry_failed else "开始逐个采购"
        action_desc = "将只重新执行当前批次中失败的采购明细。" if retry_failed else "将按当前批次全量逐个处理采购明细。"
        reply = QMessageBox.question(
            self,
            f"确认{action_title}",
            f"{action_desc}\n\n"
            "当前版本会先执行逐行匹配和规则判断；匹配失败会回写原因。\n"
            "药师帮购物车真实加购适配器接入前，不会假装加购成功。\n\n"
            f"确定{action_title}吗？",
            QMessageBox.Yes | QMessageBox.No
        )
        if reply != QMessageBox.Yes:
            return
        
        if self.cart_adapter_check.isChecked() and not self._ensure_ysbang_browser_ready():
            return
        
        self.start_purchase_btn.setEnabled(False)
        self.retry_btn.setEnabled(False)
        self.cart_backfill_btn.setEnabled(False)
        self.pause_purchase_btn.setEnabled(True)
        self.pause_purchase_btn.setText("停止")
        self.purchase_stop_requested = False
        self._append_log(f"{action_title}...")
        
        self.purchase_thread = QThread(self)
        self.purchase_worker = SmartPurchaseWorker(
            Path(self.db.db_path),
            batch_id,
            self.cart_adapter_check.isChecked(),
            retry_failed=retry_failed
        )
        self.purchase_worker.moveToThread(self.purchase_thread)
        self.purchase_thread.started.connect(self.purchase_worker.run)
        self.purchase_worker.progress.connect(self._append_log)
        self.purchase_worker.web_error.connect(self._on_purchase_web_error)
        self.purchase_worker.finished.connect(self._on_purchase_finished)
        self.purchase_worker.finished.connect(self.purchase_thread.quit)
        self.purchase_worker.finished.connect(self.purchase_worker.deleteLater)
        self.purchase_thread.finished.connect(self.purchase_thread.deleteLater)
        self.purchase_thread.start()

    @Slot(str)
    def _on_purchase_web_error(self, message: str):
        self._append_log(f"药师帮网页异常，已暂停：{message}")
        reply = QMessageBox.question(
            self,
            "药师帮网页异常",
            "采购执行过程中检测到药师帮网页或浏览器异常，已暂停。\n\n"
            f"异常信息：{message}\n\n"
            "请检查浏览器是否仍打开、是否登录成功、药师帮页面是否正常。\n\n"
            "检查完成后点击“是”继续加购；点击“否”结束本次加购并反写已完成结果。",
            QMessageBox.Yes | QMessageBox.No
        )
        should_continue = reply == QMessageBox.Yes
        if self.purchase_worker:
            self.purchase_worker.set_web_decision(should_continue)
    
    @Slot(dict, list, str)
    def _on_purchase_finished(self, summary, logs, error):
        if error:
            QMessageBox.warning(self, "错误", f"执行失败:\n{error}")
            self._append_log(f"执行失败：{error}")
        else:
            QMessageBox.information(
                self,
                "执行完成",
                f"逐个采购处理完成\n"
                f"总数: {summary.get('total', 0)}\n"
                f"成功: {summary.get('success', 0)}\n"
                f"失败: {summary.get('failed', 0)}\n"
                f"跳过: {summary.get('skipped', 0)}"
            )
            self._append_log(
                f"执行完成：总{summary.get('total', 0)}，"
                f"成功{summary.get('success', 0)}，失败{summary.get('failed', 0)}，跳过{summary.get('skipped', 0)}"
            )
        
        self.start_purchase_btn.setEnabled(True)
        self.retry_btn.setEnabled(True)
        self.cart_backfill_btn.setEnabled(True)
        self.pause_purchase_btn.setEnabled(False)
        self.pause_purchase_btn.setText("停止")
        self.purchase_stop_requested = False
        self._load_batch_items()
        self.purchase_thread = None
        self.purchase_worker = None

    def _stop_purchase(self):
        if not self.purchase_worker:
            return
        if self.purchase_stop_requested:
            return
        self.purchase_stop_requested = True
        self.purchase_worker.request_stop()
        self.pause_purchase_btn.setText("停止中...")
        self.pause_purchase_btn.setEnabled(False)

    @Slot(dict, list, str)
    def _on_cart_backfill_finished(self, summary, logs, error):
        if error:
            QMessageBox.warning(self, "错误", f"购物车反写失败:\n{error}")
            self._append_log(f"购物车反写失败：{error}")
        else:
            for log in logs[:80]:
                self._append_log(log)
            if len(logs) > 80:
                self._append_log(f"还有 {len(logs) - 80} 条反写日志已省略，可查看执行日志文件")
            QMessageBox.information(
                self,
                "购物车反写完成",
                f"购物车反写完成\n"
                f"批次明细: {summary.get('total', 0)}\n"
                f"已反写: {summary.get('updated', 0)}\n"
                f"未匹配: {summary.get('unmatched', 0)}\n"
                f"额外登记: {summary.get('extra', 0)}"
            )
            self._append_log(
                f"购物车反写完成：批次明细{summary.get('total', 0)}，"
                f"已反写{summary.get('updated', 0)}，未匹配{summary.get('unmatched', 0)}，"
                f"额外登记{summary.get('extra', 0)}"
            )

        self.start_purchase_btn.setEnabled(True)
        self.retry_btn.setEnabled(True)
        self.cart_backfill_btn.setEnabled(True)
        self._load_batch_items()
        self.cart_backfill_thread = None
        self.cart_backfill_worker = None
    
    def _ensure_ysbang_browser_ready(self) -> bool:
        if self._is_ysbang_page_open():
            self._append_log("已检测到药师帮浏览器页面")
            return True
        
        opened, message = self._open_ysbang_browser()
        if not opened:
            QMessageBox.warning(self, "浏览器打开失败", message)
            self._append_log(f"药师帮浏览器打开失败：{message}")
            return False
        
        self._append_log("未检测到药师帮页面，已自动打开浏览器")
        reply = QMessageBox.question(
            self,
            "确认药师帮登录",
            "已打开药师帮页面。\n\n"
            "请在浏览器中完成登录，并确认已进入药师帮系统后，点击“是”继续逐个采购。\n"
            "如果还没有登录成功，请点击“否”取消本次执行。",
            QMessageBox.Yes | QMessageBox.No
        )
        if reply != QMessageBox.Yes:
            self._append_log("用户取消：药师帮尚未确认登录")
            return False
        
        if not self._is_ysbang_page_open():
            QMessageBox.warning(
                self,
                "未检测到药师帮页面",
                "仍未检测到 9222 调试端口上的药师帮页面，请确认浏览器没有被关闭后再执行。"
            )
            self._append_log("未检测到 9222 调试端口上的药师帮页面")
            return False
        
        self._append_log("用户确认药师帮登录成功，继续执行逐个采购")
        return True
    
    def _is_ysbang_page_open(self) -> bool:
        try:
            with urllib.request.urlopen(self.CDP_JSON_URL, timeout=1.5) as response:
                pages = json.loads(response.read().decode("utf-8", errors="ignore"))
            return any("dian.ysbang.cn" in str(page.get("url", "")) for page in pages)
        except Exception:
            return False
    
    def _open_ysbang_browser(self) -> tuple[bool, str]:
        browser_path = self._find_browser_path()
        if not browser_path:
            return False, "未找到 Edge 或 Chrome 浏览器"
        
        profile_dir = Path.cwd() / "runtime" / "browser_profiles" / "ysbang_9222"
        profile_dir.mkdir(parents=True, exist_ok=True)
        args = [
            browser_path,
            "--remote-debugging-port=9222",
            f"--user-data-dir={profile_dir}",
            "--new-window",
            self.YSBANG_URL,
        ]
        try:
            subprocess.Popen(args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return True, ""
        except Exception as e:
            return False, str(e)
    
    def _find_browser_path(self) -> str:
        candidates = [
            shutil.which("msedge"),
            shutil.which("chrome"),
            os.path.join(os.environ.get("ProgramFiles", ""), "Microsoft", "Edge", "Application", "msedge.exe"),
            os.path.join(os.environ.get("ProgramFiles(x86)", ""), "Microsoft", "Edge", "Application", "msedge.exe"),
            os.path.join(os.environ.get("ProgramFiles", ""), "Google", "Chrome", "Application", "chrome.exe"),
            os.path.join(os.environ.get("ProgramFiles(x86)", ""), "Google", "Chrome", "Application", "chrome.exe"),
        ]
        for candidate in candidates:
            if candidate and os.path.exists(candidate):
                return candidate
        return ""
    
    def _export_results(self):
        # 权限检查
        if not self.permission_checker.check_permission(PermissionCodes.OP_SMART_PURCHASE_EXPORT_RESULT, self):
            return
        
        batch_id = self.batch_combo.currentData()
        if not batch_id:
            QMessageBox.warning(self, "提示", "请先选择采购批次")
            return
        
        self._append_log("开始导出采购结果...")
        
        output_file, error = self.service.export_results(batch_id)
        if error:
            QMessageBox.warning(self, "导出失败", f"导出采购结果失败:\n{error}")
            self._append_log(f"导出失败: {error}")
            return
        
        self._append_log(f"采购结果已导出: {output_file}")
        QMessageBox.information(
            self,
            "导出成功",
            f"采购结果已导出:\n{output_file}"
        )
    
    def _clear_cart(self):
        reply = QMessageBox.question(
            self,
            "确认清空",
            "确定要清空药师帮购物车中的所有商品吗？\n此操作不可撤销！",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )
        if reply != QMessageBox.Yes:
            return
        
        self._append_log("开始清空购物车...")
        self.clear_cart_btn.setEnabled(False)
        
        script_path = Path(__file__).resolve().parents[2] / "automation" / "ysbang_cart_clear.mjs"
        if not script_path.exists():
            QMessageBox.warning(self, "错误", f"清空购物车脚本不存在:\n{script_path}")
            self.clear_cart_btn.setEnabled(True)
            return
        
        try:
            process = subprocess.Popen(
                ["node", str(script_path)],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True
            )
            
            stdout_lines = []
            
            while process.poll() is None:
                line = process.stdout.readline()
                if line:
                    line = line.strip()
                    stdout_lines.append(line)
                    if line:
                        self._append_log(line)
                        QApplication.processEvents()
                
            remaining_stdout = process.stdout.read()
            if remaining_stdout:
                remaining_stdout = remaining_stdout.strip()
                stdout_lines.append(remaining_stdout)
                if remaining_stdout:
                    self._append_log(remaining_stdout)
            
            stderr_output = process.stderr.read().strip()
            if stderr_output:
                self._append_log(f"错误: {stderr_output}")
            
            output = stdout_lines[-1] if stdout_lines else ""
            
            if output:
                try:
                    data = json.loads(output)
                    if data.get("success"):
                        deleted_count = data.get("deletedCount", 0)
                        self._append_log(f"购物车清空成功，共删除 {deleted_count} 个商品")
                        QMessageBox.information(self, "成功", f"购物车已清空，共删除 {deleted_count} 个商品")
                    else:
                        error_msg = data.get("error", "清空购物车失败")
                        self._append_log(f"购物车清空失败: {error_msg}")
                        QMessageBox.warning(self, "失败", error_msg)
                except json.JSONDecodeError:
                    pass
            else:
                if stderr_output:
                    QMessageBox.warning(self, "失败", f"清空购物车失败:\n{stderr_output}")
                else:
                    self._append_log("清空购物车脚本无输出")
                    QMessageBox.warning(self, "失败", "清空购物车脚本无输出")
        except Exception as e:
            self._append_log(f"清空购物车异常: {str(e)}")
            QMessageBox.warning(self, "异常", f"清空购物车异常:\n{str(e)}")
        finally:
            self.clear_cart_btn.setEnabled(True)
    
    def _append_log(self, message: str):
        self.log_text.append(message)
