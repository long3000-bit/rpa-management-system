"""医保数据通用查询页面

提供医保目录、价格上限、商品信息的查询功能
"""

import pandas as pd
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QTableWidget, QTableWidgetItem,
    QLineEdit, QComboBox, QMessageBox, QFileDialog,
    QGroupBox, QFormLayout, QHeaderView, QAbstractItemView
)
from PySide6.QtCore import Qt

from app.storage.database import Database


class MedicalDataQueryPage(QWidget):
    """医保数据通用查询页面基类"""
    
    def __init__(
        self,
        db: Database,
        user: dict,
        table_name: str,
        title: str,
        search_fields: list,
        display_columns: list,
        batch_type: str = None
    ):
        super().__init__()
        self.db = db
        self.user = user
        self.table_name = table_name
        self.title = title
        self.search_fields = search_fields  # 可搜索的字段列表
        self.display_columns = display_columns  # 显示的列配置 [(字段名, 显示名), ...]
        self.batch_type = batch_type
        
        self._init_ui()
        self._load_data()
    
    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(16)
        
        # 标题
        title_label = QLabel(self.title)
        title_label.setStyleSheet("font-size: 18px; font-weight: bold; color: #333;")
        layout.addWidget(title_label)
        
        # 搜索区域
        search_group = QGroupBox("搜索条件")
        search_layout = QFormLayout(search_group)
        
        # 批次选择
        self.batch_combo = QComboBox()
        self.batch_combo.addItem("全部批次")
        search_layout.addRow("选择批次:", self.batch_combo)
        
        # 搜索字段
        self.search_inputs = {}
        for field_name, field_label in self.search_fields:
            input_widget = QLineEdit()
            input_widget.setPlaceholderText(f"输入{field_label}...")
            input_widget.textChanged.connect(self._on_search_changed)
            search_layout.addRow(f"{field_label}:", input_widget)
            self.search_inputs[field_name] = input_widget
        
        # 搜索按钮
        btn_row = QHBoxLayout()
        
        search_btn = QPushButton("搜索")
        search_btn.clicked.connect(self._load_data)
        btn_row.addWidget(search_btn)
        
        clear_btn = QPushButton("清空条件")
        clear_btn.clicked.connect(self._clear_search)
        btn_row.addWidget(clear_btn)
        
        export_btn = QPushButton("导出Excel")
        export_btn.clicked.connect(self._export_data)
        btn_row.addWidget(export_btn)
        
        btn_row.addStretch()
        search_layout.addRow("", btn_row)
        
        layout.addWidget(search_group)
        
        # 数据表格
        data_group = QGroupBox("数据列表")
        data_layout = QVBoxLayout(data_group)
        
        self.data_table = QTableWidget()
        # 初始列数为0，加载数据时动态设置
        
        # 设置表格属性
        header = self.data_table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.Interactive)
        self.data_table.setSortingEnabled(True)
        self.data_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.data_table.setAlternatingRowColors(True)
        
        data_layout.addWidget(self.data_table)
        
        # 统计信息
        self.stats_label = QLabel("共 0 条记录")
        self.stats_label.setStyleSheet("color: #666; font-size: 13px;")
        data_layout.addWidget(self.stats_label)
        
        layout.addWidget(data_group)
        
        layout.addStretch()
    
    def _load_batches(self):
        """加载批次列表"""
        if not self.batch_type:
            return
        
        conn = self.db.get_connection()
        cursor = conn.cursor()
        
        try:
            cursor.execute('''
                SELECT batch_id, file_name, created_at, success_rows
                FROM medical_import_batches
                WHERE batch_type = ? AND import_status = 'success'
                ORDER BY created_at DESC
            ''', (self.batch_type,))
            
            batches = cursor.fetchall()
            
            self.batch_combo.clear()
            self.batch_combo.addItem("全部批次")
            
            for batch in batches:
                display_text = f"{batch['batch_id']}: {batch['file_name']} ({batch['success_rows']}行)"
                self.batch_combo.addItem(display_text, batch['batch_id'])
            
        except Exception as e:
            print(f"加载批次失败: {e}")
    
    def _load_data(self):
        """加载数据"""
        conn = self.db.get_connection()
        cursor = conn.cursor()
        
        try:
            # 构建查询条件
            conditions = []
            params = []
            
            # 批次过滤
            batch_id = self.batch_combo.currentData()
            if batch_id:
                conditions.append("batch_id = ?")
                params.append(batch_id)
            
            # 搜索条件
            for field_name, input_widget in self.search_inputs.items():
                value = input_widget.text().strip()
                if value:
                    # 使用参数化查询，避免SQL注入
                    conditions.append(f"{field_name} LIKE ?")
                    params.append(f"%{value}%")
            
            # 构建SQL
            where_clause = " WHERE " + " AND ".join(conditions) if conditions else ""
            
            # 查询全部字段和全部数据
            query = f"SELECT * FROM {self.table_name} {where_clause} ORDER BY created_at DESC"
            
            print(f"执行查询: {query}")
            print(f"参数: {params}")
            
            cursor.execute(query, params)
            rows = cursor.fetchall()
            
            print(f"查询结果: {len(rows)} 条记录")
            
            if len(rows) == 0:
                self.data_table.setRowCount(0)
                self.stats_label.setText("共 0 条记录")
                return
            
            # 获取所有列名
            column_names = rows[0].keys()
            
            # 设置表格列数和表头
            self.data_table.setColumnCount(len(column_names))
            self.data_table.setHorizontalHeaderLabels(column_names)
            
            # 暂时禁用排序
            self.data_table.setSortingEnabled(False)
            self.data_table.setRowCount(len(rows))
            
            for row_idx, row in enumerate(rows):
                for col_idx, col_name in enumerate(column_names):
                    # sqlite3.Row 不支持 .get() 方法，使用方括号访问
                    try:
                        value = str(row[col_name] if row[col_name] is not None else "")
                    except (KeyError, IndexError):
                        value = ""
                    item = QTableWidgetItem(value)
                    self.data_table.setItem(row_idx, col_idx, item)
            
            # 重新启用排序
            self.data_table.setSortingEnabled(True)
            
            # 更新统计
            self.stats_label.setText(f"共 {len(rows)} 条记录")
            
        except Exception as e:
            import traceback
            error_detail = traceback.format_exc()
            print(f"查询错误详情: {error_detail}")
            QMessageBox.warning(self, "查询失败", f"查询数据失败: {e}\n\n详细信息: {error_detail}")
    
    def _on_search_changed(self):
        """搜索条件改变时自动搜索"""
        # 可以选择实时搜索或延迟搜索
        pass
    
    def _clear_search(self):
        """清空搜索条件"""
        for input_widget in self.search_inputs.values():
            input_widget.clear()
        self.batch_combo.setCurrentIndex(0)
        self._load_data()
    
    def _export_data(self):
        """导出数据"""
        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "导出Excel",
            f"{self.title}.xlsx",
            "Excel文件 (*.xlsx)"
        )
        
        if not file_path:
            return
        
        try:
            # 获取表格数据
            data = []
            
            # 获取表头（所有列名）
            headers = []
            for col in range(self.data_table.columnCount()):
                headers.append(self.data_table.horizontalHeaderItem(col).text())
            
            for row in range(self.data_table.rowCount()):
                row_data = []
                for col in range(self.data_table.columnCount()):
                    item = self.data_table.item(row, col)
                    row_data.append(item.text() if item else "")
                data.append(row_data)
            
            # 导出Excel
            df = pd.DataFrame(data, columns=headers)
            df.to_excel(file_path, index=False)
            
            QMessageBox.information(self, "导出成功", f"已导出 {len(data)} 条记录到: {file_path}")
            
        except Exception as e:
            QMessageBox.warning(self, "导出失败", f"导出失败: {e}")