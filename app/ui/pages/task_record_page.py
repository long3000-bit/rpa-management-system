from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, 
    QPushButton, QComboBox, QTableWidget,
    QTableWidgetItem, QMessageBox, QGroupBox,
    QLineEdit, QHeaderView
)
from PySide6.QtCore import Qt
from datetime import datetime
import subprocess
import platform
import logging

from app.storage.database import Database
from app.ui.widgets.table_highlight import enable_table_highlight
from app.core.data_permission_service import DataPermissionService


class TaskRecordPage(QWidget):
    
    def __init__(self, db, username: str, role_code: str):
        super().__init__()
        self.db = db
        self.username = username
        self.role_code = role_code
        self.data_permission_service = DataPermissionService(db)
        self._init_ui()
        self._load_records()
    
    def _init_ui(self):
        layout = QVBoxLayout(self)
        
        header_layout = QHBoxLayout()
        header_layout.addWidget(QLabel("对账任务记录"))
        
        self.refresh_btn = QPushButton("刷新")
        self.refresh_btn.clicked.connect(self._load_records)
        header_layout.addWidget(self.refresh_btn)
        
        layout.addLayout(header_layout)
        
        self.table = QTableWidget()
        self.table.setColumnCount(10)
        self.table.setHorizontalHeaderLabels([
            "任务ID", "账期", "药师帮文件", "状态",
            "药师帮行数", "入库行数", "一致", "差异",
            "创建时间", "操作",
        ])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(9, QHeaderView.ResizeToContents)
        enable_table_highlight(self.table)
        layout.addWidget(self.table)
    
    def _load_records(self):
        conn = self.db.get_connection()
        cursor = conn.cursor()
        
        try:
            # 构建基础查询
            query = '''
                SELECT task_id, account_period_start, ysb_file, status,
                       ysb_row_count, inbound_row_count, matched_count, diff_count,
                       created_at, result_file, created_by
                FROM reconciliation_tasks
            '''
            params = []
            
            # 应用数据权限过滤
            query, filter_params = self.data_permission_service.apply_data_filter_to_query(
                query, 'reconciliation_tasks', self.role_code, self.username
            )
            params.extend(filter_params)
            
            # 添加排序和限制
            query = f"{query} ORDER BY created_at DESC LIMIT 100"
            
            cursor.execute(query, params)
            rows = cursor.fetchall()
            
            self.table.setRowCount(len(rows))
            
            for row_idx, row in enumerate(rows):
                self.table.setItem(row_idx, 0, QTableWidgetItem(row['task_id']))
                self.table.setItem(row_idx, 1, QTableWidgetItem(row['account_period_start'] or ""))
                
                ysb_file = row['ysb_file'] or ""
                if len(ysb_file) > 30:
                    ysb_file = ysb_file[-30:]
                self.table.setItem(row_idx, 2, QTableWidgetItem(ysb_file))
                
                status = row['status'] or ""
                status_item = QTableWidgetItem(status)
                if status == "completed":
                    status_item.setBackground(Qt.green)
                elif status == "failed":
                    status_item.setBackground(Qt.red)
                self.table.setItem(row_idx, 3, status_item)
                
                self.table.setItem(row_idx, 4, QTableWidgetItem(str(row['ysb_row_count'])))
                self.table.setItem(row_idx, 5, QTableWidgetItem(str(row['inbound_row_count'])))
                self.table.setItem(row_idx, 6, QTableWidgetItem(str(row['matched_count'])))
                self.table.setItem(row_idx, 7, QTableWidgetItem(str(row['diff_count'])))
                
                created = row['created_at'] or ""
                if created:
                    try:
                        dt = datetime.fromisoformat(created)
                        created = dt.strftime("%m-%d %H:%M")
                    except:
                        pass
                self.table.setItem(row_idx, 8, QTableWidgetItem(created))
                
                result_file = row['result_file'] or ""
                open_btn = QPushButton("打开")
                open_btn.clicked.connect(lambda checked, f=result_file: self._open_result_file(f))
                self.table.setCellWidget(row_idx, 9, open_btn)
                
        except Exception as e:
            QMessageBox.warning(self, "错误", f"加载记录失败: {str(e)}")
    
    def _open_result_file(self, file_path: str):
        if not file_path:
            QMessageBox.warning(self, "提示", "无结果文件")
            return
        
        try:
            if platform.system() == "Windows":
                subprocess.run(['start', '', file_path], shell=True)
            elif platform.system() == "Darwin":
                subprocess.run(['open', file_path])
            else:
                subprocess.run(['xdg-open', file_path])
        except Exception as e:
            QMessageBox.warning(self, "错误", f"打开文件失败: {str(e)}")
