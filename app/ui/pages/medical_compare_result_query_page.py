"""医保价格比对结果查询页面"""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGroupBox, QLabel, 
    QComboBox, QLineEdit, QPushButton, QTableWidget, QHeaderView,
    QMessageBox, QFileDialog, QTableWidgetItem
)
from PySide6.QtCore import Qt
import logging


class MedicalCompareResultQueryPage(QWidget):
    """医保价格比对结果查询页面"""
    
    def __init__(self, db, user):
        super().__init__()
        self.db = db
        self.user = user
        self.username = user.get('username', 'unknown')
        
        from app.core.medical_price_compare_service import MedicalPriceCompareService
        self.compare_service = MedicalPriceCompareService(db)
        
        self.current_compare_batch = None
        
        self._init_ui()
        self._load_compare_batches()
    
    def _init_ui(self):
        """初始化界面"""
        layout = QVBoxLayout(self)
        
        # 标题
        title_label = QLabel("医保价格比对结果查询")
        title_label.setStyleSheet("font-size: 16px; font-weight: bold; margin-bottom: 10px;")
        layout.addWidget(title_label)
        
        # 比对批次选择
        compare_batch_group = QGroupBox("比对批次")
        compare_batch_layout = QHBoxLayout(compare_batch_group)
        
        compare_batch_layout.addWidget(QLabel("选择比对批次:"))
        self.compare_batch_combo = QComboBox()
        self.compare_batch_combo.setMinimumWidth(300)
        compare_batch_layout.addWidget(self.compare_batch_combo)
        
        refresh_compare_btn = QPushButton("刷新比对批次")
        refresh_compare_btn.clicked.connect(self._load_compare_batches)
        compare_batch_layout.addWidget(refresh_compare_btn)
        
        compare_batch_layout.addWidget(QLabel("当前比对批次:"))
        self.current_batch_label = QLabel("未选择")
        compare_batch_layout.addWidget(self.current_batch_label)
        
        layout.addWidget(compare_batch_group)
        
        # 过滤条件
        filter_group = QGroupBox("过滤条件")
        filter_layout = QHBoxLayout(filter_group)
        
        filter_layout.addWidget(QLabel("异常等级:"))
        self.abnormal_filter_combo = QComboBox()
        self.abnormal_filter_combo.addItems(["全部", "正常", "异常", "严重异常", "待补价格", "待补编码", "待确认"])
        filter_layout.addWidget(self.abnormal_filter_combo)
        
        filter_layout.addWidget(QLabel("处理状态:"))
        self.handle_status_filter_combo = QComboBox()
        self.handle_status_filter_combo.addItems(["全部", "未处理", "已调价", "已确认不处理", "已忽略"])
        filter_layout.addWidget(self.handle_status_filter_combo)
        
        filter_layout.addWidget(QLabel("搜索:"))
        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("商品名称/编码/医保编码")
        filter_layout.addWidget(self.search_edit)
        
        search_btn = QPushButton("查询")
        search_btn.clicked.connect(self._load_compare_results)
        filter_layout.addWidget(search_btn)
        
        layout.addWidget(filter_group)
        
        # 结果表格
        self.result_table = QTableWidget()
        self.result_table.setColumnCount(25)  # 添加库存数量、三同药品参比价、超基础金额、超基础金额_中成药、超上限金额列
        self.result_table.setHorizontalHeaderLabels([
            "君元商品编码", "君元商品名称", "君元规格", "君元生产厂家", "君元库存数量",
            "商品编码", "旧商品编码", "商品名称", "规格", "生产厂家", 
            "医保编码", "西药医保编码", "中成药医保编码", "三同医保编码",
            "君元销售价", "君元包装价", "君元单片价", 
            "三同药品参比价", "医保价格上限", "医保基础价格", "医保基础价格_中成药",
            "超基础金额", "超基础金额_中成药", "超上限金额", "异常等级"
        ])
        
        # 设置选择模式：整行选择
        self.result_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.result_table.setSelectionMode(QTableWidget.SingleSelection)
        
        # 启用表头点击排序功能
        self.result_table.setSortingEnabled(True)
        
        # 设置表格滚动条
        self.result_table.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.result_table.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        
        # 设置列宽模式：允许滚动查看所有列
        header = self.result_table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.Interactive)  # 允许用户调整列宽
        
        # 设置每列的默认宽度
        column_widths = [120, 200, 100, 150, 100, 120, 120, 200, 100, 150, 120, 120, 120, 120, 100, 100, 100, 120, 120, 120, 150, 100, 100, 100, 100]
        for i, width in enumerate(column_widths):
            self.result_table.setColumnWidth(i, width)
        
        layout.addWidget(self.result_table)
        
        # 操作按钮
        btn_row = QHBoxLayout()
        
        self.export_btn = QPushButton("导出结果")
        self.export_btn.clicked.connect(self._export_results)
        btn_row.addWidget(self.export_btn)
        
        layout.addLayout(btn_row)
    
    def _load_compare_batches(self):
        """加载比对批次列表"""
        try:
            batches = self.compare_service.get_compare_batches(limit=20)
            
            self.compare_batch_combo.clear()
            self.compare_batch_combo.addItem("请选择比对批次")
            
            for batch in batches:
                self.compare_batch_combo.addItem(
                    f"{batch['batch_id']} - {batch.get('比对时间', '')} (总数: {batch.get('总数量', 0)})"
                )
            
            self.compare_batch_combo.currentIndexChanged.connect(self._on_compare_batch_selected)
            
        except Exception as e:
            logging.error(f"加载比对批次失败: {e}")
            QMessageBox.warning(self, "错误", f"加载比对批次失败: {e}")
    
    def _on_compare_batch_selected(self, index):
        """选择比对批次"""
        if index <= 0:
            self.current_compare_batch = None
            self.current_batch_label.setText("未选择")
            return
        
        batch_text = self.compare_batch_combo.currentText()
        batch_id = batch_text.split(" - ")[0]
        self.current_compare_batch = batch_id
        self.current_batch_label.setText(batch_id)
        self._load_compare_results()
    
    def _load_compare_results(self):
        """加载比对结果"""
        if not self.current_compare_batch:
            QMessageBox.warning(self, "提示", "请先选择比对批次")
            return
        
        abnormal_level = self.abnormal_filter_combo.currentText()
        if abnormal_level == "全部":
            abnormal_level = None
        
        handle_status = self.handle_status_filter_combo.currentText()
        if handle_status == "全部":
            handle_status = None
        
        search_keyword = self.search_edit.text()
        
        try:
            results = self.compare_service.get_compare_results(
                batch_id=self.current_compare_batch,
                abnormal_level=abnormal_level,
                handle_status=handle_status,
                search_keyword=search_keyword,
                limit=10000  # 显示全部记录（最多10000条）
            )
            
            self.result_table.setRowCount(len(results))
            
            for row_idx, result in enumerate(results):
                self.result_table.setItem(row_idx, 0, QTableWidgetItem(result.get('君元商品编码', '')))
                self.result_table.setItem(row_idx, 1, QTableWidgetItem(result.get('君元商品名称', '')))
                self.result_table.setItem(row_idx, 2, QTableWidgetItem(result.get('君元规格', '')))
                self.result_table.setItem(row_idx, 3, QTableWidgetItem(result.get('君元生产厂家', '')))
                self.result_table.setItem(row_idx, 4, QTableWidgetItem(result.get('君元库存数量', '')))
                self.result_table.setItem(row_idx, 5, QTableWidgetItem(result.get('商品编码', '')))
                self.result_table.setItem(row_idx, 6, QTableWidgetItem(result.get('旧商品编码', '')))
                self.result_table.setItem(row_idx, 7, QTableWidgetItem(result.get('商品名称', '')))
                self.result_table.setItem(row_idx, 8, QTableWidgetItem(result.get('规格', '')))
                self.result_table.setItem(row_idx, 9, QTableWidgetItem(result.get('生产厂家', '')))
                self.result_table.setItem(row_idx, 10, QTableWidgetItem(result.get('医保编码', '')))
                self.result_table.setItem(row_idx, 11, QTableWidgetItem(result.get('西药医保编码', '')))
                self.result_table.setItem(row_idx, 12, QTableWidgetItem(result.get('中成药医保编码', '')))
                self.result_table.setItem(row_idx, 13, QTableWidgetItem(result.get('三同医保编码', '')))
                self.result_table.setItem(row_idx, 14, QTableWidgetItem(result.get('君元销售价', '')))
                self.result_table.setItem(row_idx, 15, QTableWidgetItem(result.get('君元包装价', '')))
                self.result_table.setItem(row_idx, 16, QTableWidgetItem(result.get('君元单片价', '')))
                self.result_table.setItem(row_idx, 17, QTableWidgetItem(result.get('三同药品参比价', '')))
                self.result_table.setItem(row_idx, 18, QTableWidgetItem(result.get('医保价格上限', '')))
                self.result_table.setItem(row_idx, 19, QTableWidgetItem(result.get('医保基础价格', '')))
                self.result_table.setItem(row_idx, 20, QTableWidgetItem(result.get('医保基础价格_中成药', '')))
                self.result_table.setItem(row_idx, 21, QTableWidgetItem(result.get('超基础金额', '')))
                self.result_table.setItem(row_idx, 22, QTableWidgetItem(result.get('超基础金额_中成药', '')))
                self.result_table.setItem(row_idx, 23, QTableWidgetItem(result.get('超上限金额', '')))
                self.result_table.setItem(row_idx, 24, QTableWidgetItem(result.get('异常等级', '')))
            
        except Exception as e:
            logging.error(f"加载比对结果失败: {e}")
            QMessageBox.warning(self, "错误", f"加载比对结果失败: {e}")
    
    def _export_results(self):
        """导出结果"""
        if not self.current_compare_batch:
            QMessageBox.warning(self, "提示", "请先选择比对批次")
            return
        
        file_path, _ = QFileDialog.getSaveFileName(
            self, "保存Excel文件", f"{self.current_compare_batch}_结果.xlsx", "Excel Files (*.xlsx)"
        )
        
        if not file_path:
            return
        
        try:
            import pandas as pd
            
            abnormal_level = self.abnormal_filter_combo.currentText()
            if abnormal_level == "全部":
                abnormal_level = None
            
            handle_status = self.handle_status_filter_combo.currentText()
            if handle_status == "全部":
                handle_status = None
            
            results = self.compare_service.export_compare_results(
                batch_id=self.current_compare_batch,
                abnormal_level=abnormal_level,
                handle_status=handle_status
            )
            
            df = pd.DataFrame(results)
            df.to_excel(file_path, index=False)
            
            QMessageBox.information(self, "成功", f"导出成功: {file_path}")
            
        except Exception as e:
            logging.error(f"导出失败: {e}")
            QMessageBox.warning(self, "错误", f"导出失败: {e}")