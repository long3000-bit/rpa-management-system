from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, 
    QPushButton, QComboBox, QTableWidget,
    QTableWidgetItem, QMessageBox, QGroupBox,
    QLineEdit, QTabWidget, QCheckBox
)
from PySide6.QtCore import Qt, QTimer
from datetime import datetime
import logging

from app.storage.database import Database
from app.ui.widgets.table_highlight import enable_table_highlight


class ReconciliationResultPage(QWidget):
    
    def __init__(self, db: Database):
        super().__init__()
        self.db = db
        self.supplier_raw_data = []
        self._is_loading = False
        self._current_task_id = None
        self._init_ui()
        
        self._monitor_timer = QTimer(self)
        self._monitor_timer.timeout.connect(self._monitor_data_state)
        self._monitor_timer.start(5000)
        
        logging.info(f"对账结果查询页面 - 初始化完成, 启动数据状态监控定时器(5秒间隔)")
    
    def showEvent(self, event):
        super().showEvent(event)
        current_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        
        logging.info(f"对账结果查询页面 - 显示事件触发 [{current_time}]")
        logging.info(f"对账结果查询页面 - 当前状态: "
                    f"supplier_raw_data长度={len(self.supplier_raw_data)}, "
                    f"supplier_table行数={self.supplier_table.rowCount()}, "
                    f"product_table行数={self.product_table.rowCount()}, "
                    f"_is_loading={self._is_loading}, "
                    f"_current_task_id={self._current_task_id[:8] if self._current_task_id else 'None'}")
        
        if not self._monitor_timer.isActive():
            logging.info(f"对账结果查询页面 - 重新启动监控定时器")
            self._monitor_timer.start(5000)
        
        if not self._is_loading:
            if len(self.supplier_raw_data) == 0:
                logging.warning(f"对账结果查询页面 - 显示时发现supplier_raw_data为空, 自动重新加载")
                self._load_tasks()
            elif self.supplier_table.rowCount() == 0 and len(self.supplier_raw_data) > 0:
                logging.warning(f"对账结果查询页面 - 显示时发现表格为空但supplier_raw_data有数据, 重新应用筛选")
                self._apply_filters()
            elif self.product_table.rowCount() == 0 and self._current_task_id:
                logging.warning(f"对账结果查询页面 - 显示时发现商品表格为空, 重新查询商品数据")
                self._query_product_results(self._current_task_id)
    
    def hideEvent(self, event):
        super().hideEvent(event)
        logging.info(f"对账结果查询页面 - 隐藏事件触发, 停止监控定时器")
        if self._monitor_timer.isActive():
            self._monitor_timer.stop()
    
    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(10)
        
        filter_group = QGroupBox("查询条件")
        filter_layout = QVBoxLayout(filter_group)
        
        filter_row1 = QHBoxLayout()
        filter_row1.addWidget(QLabel("对账任务:"))
        
        self.task_combo = QComboBox()
        self.task_combo.setMinimumWidth(300)
        self.task_combo.currentIndexChanged.connect(self._on_task_changed)
        filter_row1.addWidget(self.task_combo)
        
        self.refresh_btn = QPushButton("查询")
        self.refresh_btn.clicked.connect(self._load_tasks)
        filter_row1.addWidget(self.refresh_btn)
        
        filter_row1.addStretch()
        filter_layout.addLayout(filter_row1)
        
        filter_row2 = QHBoxLayout()
        filter_row2.addWidget(QLabel("状态筛选:"))
        
        self.status_combo = QComboBox()
        self.status_combo.addItem("全部", "all")
        self.status_combo.addItem("一致", "一致")
        self.status_combo.addItem("差异", "差异")
        self.status_combo.currentIndexChanged.connect(self._apply_filters)
        filter_row2.addWidget(self.status_combo)
        
        filter_row2.addWidget(QLabel("供应商搜索:"))
        
        self.supplier_search = QLineEdit()
        self.supplier_search.setPlaceholderText("输入供应商名称关键词")
        self.supplier_search.setMaximumWidth(200)
        self.supplier_search.textChanged.connect(self._apply_filters)
        filter_row2.addWidget(self.supplier_search)
        
        self.clear_filter_btn = QPushButton("清除筛选")
        self.clear_filter_btn.clicked.connect(self._clear_filters)
        filter_row2.addWidget(self.clear_filter_btn)
        
        filter_row2.addStretch()
        filter_layout.addLayout(filter_row2)
        
        layout.addWidget(filter_group)
        
        self.tab_widget = QTabWidget()
        
        self.supplier_table = QTableWidget()
        self.supplier_table.setAlternatingRowColors(True)
        self.supplier_table.setSortingEnabled(True)
        enable_table_highlight(self.supplier_table)
        self.tab_widget.addTab(self.supplier_table, "供应商对账结果")
        
        self.product_table = QTableWidget()
        self.product_table.setAlternatingRowColors(True)
        self.product_table.setSortingEnabled(True)
        enable_table_highlight(self.product_table)
        self.tab_widget.addTab(self.product_table, "商品对账结果")
        
        layout.addWidget(self.tab_widget)
        
        self.result_label = QLabel("共 0 条记录")
        layout.addWidget(self.result_label)
    
    @staticmethod
    def _row_to_dict(row) -> dict:
        if isinstance(row, dict):
            return row
        try:
            return dict(row)
        except Exception:
            result = {}
            for key in row.keys():
                result[key] = row[key]
            return result
    
    def _monitor_data_state(self):
        try:
            current_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            
            supplier_raw_count = len(self.supplier_raw_data)
            supplier_table_rows = self.supplier_table.rowCount()
            product_table_rows = self.product_table.rowCount()
            
            current_task = self.task_combo.currentText()
            current_task_data = self.task_combo.currentData()
            
            result_text = self.result_label.text()
            
            logging.info(f"数据状态监控 [{current_time}] - "
                        f"supplier_raw_data: {supplier_raw_count}条, "
                        f"supplier_table: {supplier_table_rows}行, "
                        f"product_table: {product_table_rows}行, "
                        f"当前任务: {current_task}, "
                        f"结果标签: {result_text}, "
                        f"_is_loading: {self._is_loading}, "
                        f"_current_task_id: {self._current_task_id[:8] if self._current_task_id else 'None'}")
            
            if supplier_raw_count > 0 and supplier_table_rows == 0:
                logging.warning(f"数据状态监控 [{current_time}] - 异常: supplier_raw_data有{supplier_raw_count}条数据, 但表格为空!")
            
            if supplier_raw_count == 0 and supplier_table_rows > 0:
                logging.warning(f"数据状态监控 [{current_time}] - 异常: supplier_raw_data为空, 但表格有{supplier_table_rows}行数据!")
            
            if current_task_data and supplier_raw_count == 0:
                logging.warning(f"数据状态监控 [{current_time}] - 异常: 有选中任务但supplier_raw_data为空!")
        
        except Exception as e:
            logging.error(f"数据状态监控失败: {str(e)}", exc_info=True)
    
    def _load_tasks(self):
        if self._is_loading:
            logging.warning(f"对账结果查询 - 正在加载中,跳过重复请求")
            return
        
        self._is_loading = True
        
        try:
            logging.info(f"对账结果查询 - 开始加载任务, 时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
            logging.info(f"对账结果查询 - 当前状态: supplier_raw_data长度={len(self.supplier_raw_data)}, _current_task_id={self._current_task_id}")
            
            self.supplier_raw_data = []
            self._current_task_id = None
            
            self.supplier_table.setRowCount(0)
            self.product_table.setRowCount(0)
            self.result_label.setText("正在查询...")
            
            logging.info(f"对账结果查询 - 尝试获取数据库连接")
            conn = self.db.get_connection()
            logging.info(f"对账结果查询 - 数据库连接成功, 连接对象: {conn}")
            
            cursor = conn.cursor()
            logging.info(f"对账结果查询 - 创建游标成功")
            
            sql = '''
                SELECT 
                    task_id,
                    task_type,
                    ysb_file,
                    account_period_start,
                    account_period_end,
                    status,
                    supplier_match_count,
                    supplier_diff_count,
                    product_match_count,
                    product_diff_count,
                    created_at
                FROM reconciliation_tasks
                WHERE status = 'completed'
                ORDER BY created_at DESC
            '''
            logging.info(f"对账结果查询 - 执行SQL查询: {sql.strip()}")
            
            cursor.execute(sql)
            logging.info(f"对账结果查询 - SQL查询执行完成")
            
            raw_rows = cursor.fetchall()
            logging.info(f"对账结果查询 - 获取原始数据行数: {len(raw_rows)}, 类型: {type(raw_rows)}")
            
            if raw_rows and len(raw_rows) > 0:
                logging.info(f"对账结果查询 - 第一行原始数据类型: {type(raw_rows[0])}, 内容: {raw_rows[0]}")
            
            rows = [self._row_to_dict(r) for r in raw_rows]
            logging.info(f"对账结果查询 - 转换后的数据行数: {len(rows)}, 类型: {type(rows)}")
            
            if rows and len(rows) > 0:
                logging.info(f"对账结果查询 - 第一行转换后数据: {rows[0]}")
            
            self.task_combo.blockSignals(True)
            self.status_combo.blockSignals(True)
            self.supplier_search.blockSignals(True)
            
            self.task_combo.clear()
            self.task_combo.addItem("请选择对账任务", None)
            
            for row in rows:
                created_at = row.get('created_at', '')
                if created_at:
                    try:
                        dt = datetime.fromisoformat(created_at)
                        created_at = dt.strftime("%Y-%m-%d %H:%M")
                    except:
                        pass
                
                task_type = row.get('task_type', '')
                task_type_display = "供应商对账" if task_type == "supplier" else "供应商商品对账" if task_type == "supplier_product" else task_type
                
                supplier_hint = f"供应商匹配:{row.get('supplier_match_count', 0)}, 差异:{row.get('supplier_diff_count', 0)}"
                product_hint = f"商品匹配:{row.get('product_match_count', 0)}, 差异:{row.get('product_diff_count', 0)}"
                
                display_text = f"[{task_type_display}] {row.get('ysb_file', '')} ({created_at}) [{supplier_hint}] [{product_hint}]"
                
                task_data = {
                    'task_id': row.get('task_id'),
                    'supplier_match_count': row.get('supplier_match_count', 0),
                    'supplier_diff_count': row.get('supplier_diff_count', 0),
                    'product_match_count': row.get('product_match_count', 0),
                    'product_diff_count': row.get('product_diff_count', 0)
                }
                
                self.task_combo.addItem(display_text, task_data)
            
            if rows:
                self.task_combo.setCurrentIndex(1)
                task_data = self.task_combo.currentData()
                if task_data:
                    task_id = task_data.get('task_id')
                    self._current_task_id = task_id
                    self._query_supplier_results(task_id)
                    self._query_product_results(task_id)
            else:
                self.supplier_table.setRowCount(0)
                self.product_table.setRowCount(0)
                self.result_label.setText("共 0 条记录")
            
            self.task_combo.blockSignals(False)
            self.status_combo.blockSignals(False)
            self.supplier_search.blockSignals(False)
        
        except Exception as e:
            logging.error(f"对账结果查询失败: {str(e)}", exc_info=True)
            self.result_label.setText(f"查询失败: {str(e)}")
        
        finally:
            self._is_loading = False
    
    def _on_task_changed(self):
        if self._is_loading:
            logging.warning(f"任务切换 - 正在加载中,跳过切换")
            return
        
        task_data = self.task_combo.currentData()
        logging.info(f"任务切换 - 当前任务数据: {task_data}")
        
        if not task_data:
            logging.info(f"任务切换 - 无任务数据, 清空所有数据")
            self.supplier_raw_data = []
            self._current_task_id = None
            self.supplier_table.setRowCount(0)
            self.product_table.setRowCount(0)
            self.result_label.setText("共 0 条记录")
            return
        
        task_id = task_data.get('task_id')
        logging.info(f"任务切换 - 目标任务ID: {task_id[:8]}..., 当前任务ID: {self._current_task_id}")
        
        if task_id == self._current_task_id:
            logging.info(f"任务切换 - 任务ID相同, 跳过查询")
            return
        
        self._current_task_id = task_id
        
        logging.info(f"任务切换 - 开始查询新任务数据: {task_id[:8]}...")
        
        self._query_supplier_results(task_id)
        self._query_product_results(task_id)
        
        logging.info(f"任务切换 - 任务数据查询完成")
    
    def _query_supplier_results(self, task_id: str):
        try:
            logging.info(f"查询供应商对账结果 - 开始查询, task_id: {task_id[:8]}...")
            
            conn = self.db.get_connection()
            logging.info(f"查询供应商对账结果 - 数据库连接成功")
            
            cursor = conn.cursor()
            logging.info(f"查询供应商对账结果 - 创建游标成功")
            
            sql = '''
                SELECT 
                    status,
                    diff_type,
                    ysb_supplier,
                    inbound_supplier,
                    ysb_amount,
                    inbound_amount,
                    amount_diff,
                    ysb_count,
                    inbound_count,
                    match_method,
                    remark
                FROM supplier_reconciliation_results
                WHERE task_id = ?
                ORDER BY id
            '''
            logging.info(f"查询供应商对账结果 - 执行SQL查询, task_id: {task_id}")
            
            cursor.execute(sql, (task_id,))
            logging.info(f"查询供应商对账结果 - SQL查询执行完成")
            
            raw_rows = cursor.fetchall()
            logging.info(f"查询供应商对账结果 - 获取原始数据行数: {len(raw_rows)}, 类型: {type(raw_rows)}")
            
            if raw_rows and len(raw_rows) > 0:
                logging.info(f"查询供应商对账结果 - 第一行原始数据类型: {type(raw_rows[0])}")
            
            self.supplier_raw_data = [self._row_to_dict(r) for r in raw_rows]
            logging.info(f"查询供应商对账结果 - 转换后的数据行数: {len(self.supplier_raw_data)}, 类型: {type(self.supplier_raw_data)}")
            
            if self.supplier_raw_data:
                sample = self.supplier_raw_data[0]
                logging.info(f"查询供应商对账结果 - 示例数据: status={sample.get('status')}, ysb_supplier={sample.get('ysb_supplier')}, inbound_supplier={sample.get('inbound_supplier')}")
                logging.info(f"查询供应商对账结果 - 数据完整性检查: 共{len(self.supplier_raw_data)}条, 所有数据都有status字段: {all(r.get('status') is not None for r in self.supplier_raw_data)}")
            
            logging.info(f"查询供应商对账结果 - 开始应用筛选")
            self._apply_filters()
            logging.info(f"查询供应商对账结果 - 筛选应用完成")
        
        except Exception as e:
            logging.error(f"查询供应商对账结果失败: {str(e)}", exc_info=True)
            logging.error(f"查询供应商对账结果失败 - 异常类型: {type(e).__name__}")
            logging.error(f"查询供应商对账结果失败 - 异常详情: {str(e)}")
            self.supplier_raw_data = []
            self.supplier_table.setRowCount(0)
            self.result_label.setText(f"查询失败: {str(e)}")
    
    def _apply_filters(self):
        logging.info(f"应用筛选 - 开始, supplier_raw_data长度: {len(self.supplier_raw_data)}")
        
        if not self.supplier_raw_data:
            logging.warning(f"应用筛选 - supplier_raw_data为空, 清空表格")
            self.supplier_table.setRowCount(0)
            self.result_label.setText("共 0 条记录")
            return
        
        status_filter = self.status_combo.currentData()
        supplier_keyword = self.supplier_search.text().strip().lower()
        
        logging.info(f"应用筛选 - 状态筛选: {status_filter}, 供应商关键词: {supplier_keyword}")
        
        filtered_data = []
        for row in self.supplier_raw_data:
            if status_filter != "all" and row.get('status') != status_filter:
                continue
            
            if supplier_keyword:
                ysb_supplier = (row.get('ysb_supplier') or '').lower()
                inbound_supplier = (row.get('inbound_supplier') or '').lower()
                if supplier_keyword not in ysb_supplier and supplier_keyword not in inbound_supplier:
                    continue
            
            filtered_data.append(row)
        
        logging.info(f"应用筛选 - 筛选后数据行数: {len(filtered_data)}")
        
        headers = ["状态", "差异类型", "药师帮供应商", "入库供应商", "药师帮金额", "入库金额", 
                   "金额差异", "药师帮数量", "入库数量", "匹配方式", "备注"]
        keys = ['status', 'diff_type', 'ysb_supplier', 'inbound_supplier', 
                'ysb_amount', 'inbound_amount', 'amount_diff', 
                'ysb_count', 'inbound_count', 'match_method', 'remark']
        
        logging.info(f"应用筛选 - 禁用排序功能以填充数据")
        self.supplier_table.setSortingEnabled(False)
        
        logging.info(f"应用筛选 - 设置表格列数: {len(headers)}")
        self.supplier_table.setColumnCount(len(headers))
        self.supplier_table.setHorizontalHeaderLabels(headers)
        
        logging.info(f"应用筛选 - 清空表格行")
        self.supplier_table.setRowCount(0)
        
        logging.info(f"应用筛选 - 设置表格行数: {len(filtered_data)}")
        self.supplier_table.setRowCount(len(filtered_data))
        
        logging.info(f"应用筛选 - 开始填充表格数据")
        for row_idx, row in enumerate(filtered_data):
            logging.debug(f"应用筛选 - 填充第{row_idx}行, 数据: {row}")
            for col_idx, key in enumerate(keys):
                value = row.get(key)
                if value is None:
                    value = ''
                elif isinstance(value, float):
                    if value == int(value):
                        value = str(int(value))
                    else:
                        value = f"{value:.2f}"
                else:
                    value = str(value)
                
                item = QTableWidgetItem(value)
                self.supplier_table.setItem(row_idx, col_idx, item)
        
        logging.info(f"应用筛选 - 表格数据填充完成, 共{len(filtered_data)}行")
        self.supplier_table.resizeColumnsToContents()
        
        logging.info(f"应用筛选 - 重新启用排序功能")
        self.supplier_table.setSortingEnabled(True)
        
        self.result_label.setText(f"共 {len(filtered_data)} 条记录 (原始: {len(self.supplier_raw_data)} 条)")
        logging.info(f"应用筛选 - 完成, 结果标签: {self.result_label.text()}")
    
    def _clear_filters(self):
        self.status_combo.setCurrentIndex(0)
        self.supplier_search.clear()
    
    def _query_product_results(self, task_id: str):
        try:
            logging.info(f"查询商品对账结果 - 开始查询, task_id: {task_id[:8]}...")
            
            conn = self.db.get_connection()
            logging.info(f"查询商品对账结果 - 数据库连接成功")
            
            cursor = conn.cursor()
            logging.info(f"查询商品对账结果 - 创建游标成功")
            
            sql = '''
                SELECT 
                    status,
                    diff_type,
                    supplier,
                    product_code,
                    product_name,
                    spec,
                    manufacturer,
                    ysb_amount,
                    inbound_amount,
                    amount_diff,
                    ysb_quantity,
                    inbound_quantity,
                    quantity_diff,
                    ysb_supplier,
                    inbound_supplier,
                    remark
                FROM product_reconciliation_results
                WHERE task_id = ?
                ORDER BY id
            '''
            logging.info(f"查询商品对账结果 - 执行SQL查询, task_id: {task_id}")
            
            cursor.execute(sql, (task_id,))
            logging.info(f"查询商品对账结果 - SQL查询执行完成")
            
            raw_rows = cursor.fetchall()
            logging.info(f"查询商品对账结果 - 获取原始数据行数: {len(raw_rows)}, 类型: {type(raw_rows)}")
            
            rows = [self._row_to_dict(r) for r in raw_rows]
            logging.info(f"查询商品对账结果 - 转换后的数据行数: {len(rows)}")
            
            headers = ["状态", "差异类型", "供应商", "商品编码", "商品名称", "规格", "厂家",
                       "药师帮金额", "入库金额", "金额差异", "药师帮数量", "入库数量", "数量差异",
                       "药师帮供应商", "入库供应商", "采购时间", "入库时间", "备注"]
            keys = ['status', 'diff_type', 'supplier', 'product_code', 'product_name', 
                    'spec', 'manufacturer', 'ysb_amount', 'inbound_amount', 'amount_diff',
                    'ysb_quantity', 'inbound_quantity', 'quantity_diff',
                    'ysb_supplier', 'inbound_supplier', 'ysb_purchase_time', 'inbound_date', 'remark']
            
            logging.info(f"查询商品对账结果 - 禁用排序功能以填充数据")
            self.product_table.setSortingEnabled(False)
            
            self.product_table.setColumnCount(len(headers))
            self.product_table.setHorizontalHeaderLabels(headers)
            self.product_table.setRowCount(0)
            self.product_table.setRowCount(len(rows))
            
            logging.info(f"查询商品对账结果 - 开始填充表格数据")
            for row_idx, row in enumerate(rows):
                for col_idx, key in enumerate(keys):
                    value = row.get(key)
                    if value is None:
                        value = ''
                    elif isinstance(value, float):
                        if value == int(value):
                            value = str(int(value))
                        else:
                            value = f"{value:.2f}"
                    else:
                        value = str(value)
                    
                    item = QTableWidgetItem(value)
                    self.product_table.setItem(row_idx, col_idx, item)
            
            logging.info(f"查询商品对账结果 - 表格数据填充完成, 共{len(rows)}行")
            self.product_table.resizeColumnsToContents()
            
            logging.info(f"查询商品对账结果 - 重新启用排序功能")
            self.product_table.setSortingEnabled(True)
            
            supplier_count = self.supplier_table.rowCount()
            product_count = self.product_table.rowCount()
            self.result_label.setText(f"供应商对账: {supplier_count} 条 | 商品对账: {product_count} 条")
            logging.info(f"查询商品对账结果 - 完成, 结果标签: {self.result_label.text()}")
        
        except Exception as e:
            logging.error(f"查询商品对账结果失败: {str(e)}", exc_info=True)
            logging.error(f"查询商品对账结果失败 - 异常类型: {type(e).__name__}")
            self.product_table.setRowCount(0)
            self.result_label.setText(f"商品对账查询失败: {str(e)}")
