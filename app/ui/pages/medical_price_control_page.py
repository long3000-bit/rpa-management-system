"""
医保价格管控页面

功能：
1. 数据导入（医保目录、医保价格上限、云药店商品目录）
2. 君元价格抓取
3. 价格比对
4. 异常查看与处理
5. 结果导出
"""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QTableWidget, QTableWidgetItem,
    QMessageBox, QFileDialog, QComboBox, QGroupBox,
    QFormLayout, QLineEdit, QHeaderView, QProgressBar,
    QTabWidget, QDialog, QTextEdit, QSpinBox, QListWidget,
    QListWidgetItem, QAbstractItemView
)
from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtGui import QShowEvent
import logging
from datetime import datetime
from pathlib import Path
import pandas as pd

from app.storage.database import Database
from app.core.medical_price_import_service import MedicalPriceImportService
from app.core.junyuan_price_fetch_service import JunyuanPriceFetchService
from app.core.medical_price_compare_service import MedicalPriceCompareService
from app.core.database_config_service import DatabaseConfigService
from app.core.permission_checker import PermissionChecker, PermissionCodes


class ImportWorker(QThread):
    """导入工作线程"""
    finished = Signal(object)
    
    def __init__(self, import_service, import_func, file_path, sheet_name, username):
        super().__init__()
        self.import_service = import_service
        self.import_func = import_func
        self.file_path = file_path
        self.sheet_name = sheet_name
        self.username = username
    
    def run(self):
        result = self.import_func(self.file_path, self.sheet_name, self.username)
        self.finished.emit(result)


class FetchWorker(QThread):
    """价格抓取工作线程"""
    finished = Signal(object)
    
    def __init__(self, fetch_service, db_config_id, custom_sql, username):
        super().__init__()
        self.fetch_service = fetch_service
        self.db_config_id = db_config_id
        self.custom_sql = custom_sql
        self.username = username
    
    def run(self):
        result = self.fetch_service.fetch_junyuan_prices(
            db_config_id=self.db_config_id,
            custom_sql=self.custom_sql,
            imported_by=self.username
        )
        self.finished.emit(result)


class CompareWorker(QThread):
    """比对工作线程"""
    finished = Signal(object)
    
    def __init__(self, compare_service, batches, username):
        super().__init__()
        self.compare_service = compare_service
        self.batches = batches
        self.username = username
    
    def run(self):
        result = self.compare_service.run_compare(
            medical_catalog_batch=self.batches.get('medical_catalog'),
            medical_price_limit_batch=self.batches.get('medical_price_limit'),
            cloud_pharmacy_batch=self.batches.get('cloud_pharmacy'),
            junyuan_price_batch=self.batches.get('junyuan_price'),
            compare_by=self.username
        )
        self.finished.emit(result)


class MedicalPriceControlPage(QWidget):
    """医保价格管控页面"""
    
    def __init__(self, db: Database, username: str = None, role_code: str = None):
        super().__init__()
        self.db = db
        self.username = username or 'admin'
        self.role_code = role_code or 'store_manager'
        
        self.import_service = MedicalPriceImportService(db)
        self.fetch_service = JunyuanPriceFetchService(db)
        self.compare_service = MedicalPriceCompareService(db)
        self.db_config_service = DatabaseConfigService(db)
        
        self.permission_checker = PermissionChecker(db, self.username)
        
        self.current_compare_batch = None
        self.import_worker = None
        self.fetch_worker = None
        self.compare_worker = None
        
        self._batches_loaded = False  # 标记批次是否已加载
        
        self._init_ui()
        # 延迟加载批次数据 - 不在初始化时加载
    
    def showEvent(self, event: QShowEvent):
        """页面显示事件 - 首次显示时加载批次数据"""
        super().showEvent(event)
        if not self._batches_loaded:
            self._batches_loaded = True
            self._load_batches()
    
    def _init_ui(self):
        layout = QVBoxLayout(self)
        
        # 标题
        title = QLabel("医保价格管控")
        title.setStyleSheet("font-size: 18px; font-weight: bold;")
        layout.addWidget(title)
        
        # 创建标签页
        tab_widget = QTabWidget()
        
        # 标签页1：数据导入
        import_tab = self._create_import_tab()
        tab_widget.addTab(import_tab, "数据导入")
        
        # 标签页2：价格比对
        compare_tab = self._create_compare_tab()
        tab_widget.addTab(compare_tab, "价格比对")
        
        # 标签页3：异常处理
        handle_tab = self._create_handle_tab()
        tab_widget.addTab(handle_tab, "异常处理")
        
        layout.addWidget(tab_widget)
    
    def _create_import_tab(self) -> QWidget:
        """创建数据导入标签页"""
        tab = QWidget()
        layout = QVBoxLayout(tab)
        
        # 医保目录导入
        medical_group = QGroupBox("医保目录导入")
        medical_layout = QVBoxLayout(medical_group)
        
        # 西药目录
        western_row = QHBoxLayout()
        western_row.addWidget(QLabel("医保目录-西药:"))
        self.western_file_edit = QLineEdit()
        western_row.addWidget(self.western_file_edit)
        western_btn = QPushButton("选择文件")
        western_btn.clicked.connect(lambda: self._select_file(self.western_file_edit))
        western_row.addWidget(western_btn)
        self.import_western_btn = QPushButton("导入西药目录")
        self.import_western_btn.clicked.connect(self._import_western_catalog)
        western_row.addWidget(self.import_western_btn)
        medical_layout.addLayout(western_row)
        
        # 中成药目录
        chinese_row = QHBoxLayout()
        chinese_row.addWidget(QLabel("医保目录-中成药:"))
        self.chinese_file_edit = QLineEdit()
        chinese_row.addWidget(self.chinese_file_edit)
        chinese_btn = QPushButton("选择文件")
        chinese_btn.clicked.connect(lambda: self._select_file(self.chinese_file_edit))
        chinese_row.addWidget(chinese_btn)
        self.import_chinese_btn = QPushButton("导入中成药目录")
        self.import_chinese_btn.clicked.connect(self._import_chinese_catalog)
        chinese_row.addWidget(self.import_chinese_btn)
        medical_layout.addLayout(chinese_row)
        
        layout.addWidget(medical_group)
        
        # 三同口径文件导入
        price_group = QGroupBox("三同口径文件导入")
        price_layout = QHBoxLayout(price_group)
        
        price_layout.addWidget(QLabel("三同口径文件:"))
        self.price_limit_file_edit = QLineEdit()
        price_layout.addWidget(self.price_limit_file_edit)
        price_btn = QPushButton("选择文件")
        price_btn.clicked.connect(lambda: self._select_file(self.price_limit_file_edit))
        price_layout.addWidget(price_btn)
        self.import_price_btn = QPushButton("导入三同口径")
        self.import_price_btn.clicked.connect(self._import_price_limit)
        price_layout.addWidget(self.import_price_btn)
        
        layout.addWidget(price_group)
        
        # 云药店商品目录导入
        cloud_group = QGroupBox("云药店商品目录导入")
        cloud_layout = QHBoxLayout(cloud_group)
        
        cloud_layout.addWidget(QLabel("商品目录文件:"))
        self.cloud_file_edit = QLineEdit()
        cloud_layout.addWidget(self.cloud_file_edit)
        cloud_btn = QPushButton("选择文件")
        cloud_btn.clicked.connect(lambda: self._select_file(self.cloud_file_edit))
        cloud_layout.addWidget(cloud_btn)
        self.import_cloud_btn = QPushButton("导入商品目录")
        self.import_cloud_btn.clicked.connect(self._import_cloud_catalog)
        cloud_layout.addWidget(self.import_cloud_btn)
        
        layout.addWidget(cloud_group)
        
        # 君元价格抓取
        jy_group = QGroupBox("君元销售价格抓取")
        jy_layout = QVBoxLayout(jy_group)
        
        # 数据库配置选择
        db_config_row = QHBoxLayout()
        db_config_row.addWidget(QLabel("数据库配置:"))
        self.jy_db_config_combo = QComboBox()
        self.jy_db_config_combo.setMinimumWidth(300)
        db_config_row.addWidget(self.jy_db_config_combo)
        
        refresh_config_btn = QPushButton("刷新配置")
        refresh_config_btn.clicked.connect(self._load_db_configs)
        db_config_row.addWidget(refresh_config_btn)
        
        db_config_row.addStretch()
        jy_layout.addLayout(db_config_row)
        
        # 自定义SQL输入
        sql_row = QHBoxLayout()
        sql_row.addWidget(QLabel("自定义SQL:"))
        
        self.custom_sql_edit = QTextEdit()
        self.custom_sql_edit.setMaximumHeight(100)
        self.custom_sql_edit.setPlaceholderText("可选：输入自定义SQL查询语句，不输入则使用默认SQL")
        sql_row.addWidget(self.custom_sql_edit)
        
        # SQL管理按钮
        sql_btn_widget = QWidget()
        sql_btn_layout = QVBoxLayout(sql_btn_widget)
        sql_btn_layout.setContentsMargins(0, 0, 0, 0)
        
        save_sql_btn = QPushButton("保存SQL")
        save_sql_btn.clicked.connect(self._save_custom_sql)
        sql_btn_layout.addWidget(save_sql_btn)
        
        use_saved_btn = QPushButton("读取保存的SQL")
        use_saved_btn.clicked.connect(self._load_saved_sql)
        sql_btn_layout.addWidget(use_saved_btn)
        
        sql_row.addWidget(sql_btn_widget)
        
        jy_layout.addLayout(sql_row)
        
        # 抓取按钮
        fetch_row = QHBoxLayout()
        self.fetch_price_btn = QPushButton("抓取价格")
        self.fetch_price_btn.clicked.connect(self._fetch_junyuan_prices)
        fetch_row.addWidget(self.fetch_price_btn)
        fetch_row.addStretch()
        jy_layout.addLayout(fetch_row)
        
        layout.addWidget(jy_group)
        
        # 进度条
        self.import_progress = QProgressBar()
        self.import_progress.setVisible(False)
        layout.addWidget(self.import_progress)
        
        # 导入批次列表
        batch_group = QGroupBox("导入批次记录")
        batch_layout = QVBoxLayout(batch_group)
        
        self.batch_table = QTableWidget()
        self.batch_table.setColumnCount(6)
        self.batch_table.setHorizontalHeaderLabels([
            "批次ID", "类型", "文件名", "成功行数", "失败行数", "导入时间"
        ])
        # 设置列宽模式为交互式，允许用户调整
        header = self.batch_table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.Interactive)
        # 设置初始列宽
        self.batch_table.setColumnWidth(0, 200)  # 批次ID
        self.batch_table.setColumnWidth(1, 150)  # 类型
        self.batch_table.setColumnWidth(2, 250)  # 文件名
        self.batch_table.setColumnWidth(3, 80)   # 成功行数
        self.batch_table.setColumnWidth(4, 80)   # 失败行数
        self.batch_table.setColumnWidth(5, 150)  # 导入时间
        # 启用排序
        self.batch_table.setSortingEnabled(True)
        self.batch_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.batch_table.setSelectionMode(QAbstractItemView.SingleSelection)
        batch_layout.addWidget(self.batch_table)
        
        # 批次操作按钮
        batch_btn_row = QHBoxLayout()
        
        refresh_btn = QPushButton("刷新批次")
        refresh_btn.clicked.connect(self._load_batches)
        batch_btn_row.addWidget(refresh_btn)
        
        delete_btn = QPushButton("删除选中批次")
        delete_btn.clicked.connect(self._delete_selected_batch)
        batch_btn_row.addWidget(delete_btn)
        
        batch_btn_row.addStretch()
        
        batch_layout.addLayout(batch_btn_row)
        
        layout.addWidget(batch_group)
        
        return tab
    
    def _create_compare_tab(self) -> QWidget:
        """创建价格比对标签页"""
        tab = QWidget()
        layout = QVBoxLayout(tab)
        
        # 选择批次
        batch_group = QGroupBox("选择数据批次")
        batch_layout = QFormLayout(batch_group)
        
        # 西药医保目录批次 - 下拉框单选
        self.western_catalog_combo = QComboBox()
        batch_layout.addRow("西药医保目录批次:", self.western_catalog_combo)
        
        # 中成药医保目录批次 - 下拉框单选
        self.chinese_catalog_combo = QComboBox()
        batch_layout.addRow("中成药医保目录批次:", self.chinese_catalog_combo)
        
        self.price_limit_combo = QComboBox()
        batch_layout.addRow("价格上限批次:", self.price_limit_combo)
        
        self.cloud_catalog_combo = QComboBox()
        batch_layout.addRow("商品目录批次:", self.cloud_catalog_combo)
        
        self.jy_price_combo = QComboBox()
        batch_layout.addRow("君元价格批次:", self.jy_price_combo)
        
        layout.addWidget(batch_group)
        
        # 执行比对
        compare_row = QHBoxLayout()
        self.run_compare_btn = QPushButton("执行价格比对")
        self.run_compare_btn.clicked.connect(self._run_compare)
        compare_row.addWidget(self.run_compare_btn)
        
        self.compare_progress = QProgressBar()
        self.compare_progress.setVisible(False)
        compare_row.addWidget(self.compare_progress)
        
        layout.addLayout(compare_row)
        
        # 比对结果统计
        stats_group = QGroupBox("比对结果统计")
        stats_layout = QHBoxLayout(stats_group)
        
        self.normal_label = QLabel("正常: 0 (0%)")
        self.abnormal_label = QLabel("异常: 0 (0%)")
        self.severe_label = QLabel("严重异常: 0 (0%)")
        self.missing_price_label = QLabel("待补价格: 0 (0%)")
        self.missing_code_label = QLabel("待补编码: 0 (0%)")
        self.pending_label = QLabel("待确认: 0 (0%)")
        self.total_label = QLabel("总数: 0")
        
        stats_layout.addWidget(self.normal_label)
        stats_layout.addWidget(self.abnormal_label)
        stats_layout.addWidget(self.severe_label)
        stats_layout.addWidget(self.missing_price_label)
        stats_layout.addWidget(self.missing_code_label)
        stats_layout.addWidget(self.pending_label)
        stats_layout.addWidget(self.total_label)
        
        layout.addWidget(stats_group)
        
        # 比对批次列表
        compare_batch_group = QGroupBox("比对批次记录")
        compare_batch_layout = QVBoxLayout(compare_batch_group)
        
        self.compare_batch_table = QTableWidget()
        self.compare_batch_table.setColumnCount(8)
        self.compare_batch_table.setHorizontalHeaderLabels([
            "批次ID", "比对时间", "总数量", "正常", "异常", "严重异常", "待确认", "比对状态"
        ])
        self.compare_batch_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        compare_batch_layout.addWidget(self.compare_batch_table)
        
        self.compare_batch_table.itemClicked.connect(self._select_compare_batch)
        
        # 比对批次操作按钮
        compare_batch_btn_row = QHBoxLayout()
        
        refresh_compare_batch_btn = QPushButton("刷新批次")
        refresh_compare_batch_btn.clicked.connect(self._load_batches)
        compare_batch_btn_row.addWidget(refresh_compare_batch_btn)
        
        delete_compare_batch_btn = QPushButton("删除选中批次")
        delete_compare_batch_btn.clicked.connect(self._delete_compare_batch)
        compare_batch_btn_row.addWidget(delete_compare_batch_btn)
        
        compare_batch_btn_row.addStretch()
        
        compare_batch_layout.addLayout(compare_batch_btn_row)
        
        layout.addWidget(compare_batch_group)
        
        return tab
    
    def _create_handle_tab(self) -> QWidget:
        """创建异常处理标签页"""
        tab = QWidget()
        layout = QVBoxLayout(tab)
        
        # 筛选条件
        filter_group = QGroupBox("筛选条件")
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
        self.result_table.setColumnCount(12)
        self.result_table.setHorizontalHeaderLabels([
            "ID", "商品名称", "规格", "生产厂家", "医保基础价格", "医保价格上限",
            "君元销售价", "异常等级", "超基础金额", "超上限金额", "处理状态", "处理备注"
        ])
        self.result_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        layout.addWidget(self.result_table)
        
        # 操作按钮
        btn_row = QHBoxLayout()
        
        self.handle_btn = QPushButton("处理选中项")
        self.handle_btn.clicked.connect(self._handle_selected)
        btn_row.addWidget(self.handle_btn)
        
        self.export_btn = QPushButton("导出结果")
        self.export_btn.clicked.connect(self._export_results)
        btn_row.addWidget(self.export_btn)
        
        btn_row.addWidget(QLabel("当前批次:"))
        self.current_batch_label = QLabel("未选择")
        btn_row.addWidget(self.current_batch_label)
        
        layout.addLayout(btn_row)
        
        return tab
    
    def _select_file(self, edit: QLineEdit):
        """选择文件"""
        file_path, _ = QFileDialog.getOpenFileName(
            self, "选择Excel文件", "", "Excel Files (*.xlsx *.xls)"
        )
        if file_path:
            edit.setText(file_path)
    
    def _import_western_catalog(self):
        """导入西药目录"""
        file_path = self.western_file_edit.text()
        if not file_path:
            QMessageBox.warning(self, "提示", "请选择文件")
            return
        
        self.import_western_btn.setEnabled(False)
        self.import_progress.setVisible(True)
        self.import_progress.setValue(0)
        
        self.import_worker = ImportWorker(
            self.import_service,
            self.import_service.import_medical_catalog_western,
            file_path,
            None,
            self.username
        )
        self.import_worker.finished.connect(self._on_import_finished)
        self.import_worker.start()
    
    def _import_chinese_catalog(self):
        """导入中成药目录"""
        file_path = self.chinese_file_edit.text()
        if not file_path:
            QMessageBox.warning(self, "提示", "请选择文件")
            return
        
        self.import_chinese_btn.setEnabled(False)
        self.import_progress.setVisible(True)
        self.import_progress.setValue(0)
        
        self.import_worker = ImportWorker(
            self.import_service,
            self.import_service.import_medical_catalog_chinese,
            file_path,
            None,
            self.username
        )
        self.import_worker.finished.connect(self._on_import_finished)
        self.import_worker.start()
    
    def _import_price_limit(self):
        """导入价格上限"""
        file_path = self.price_limit_file_edit.text()
        if not file_path:
            QMessageBox.warning(self, "提示", "请选择文件")
            return
        
        self.import_price_btn.setEnabled(False)
        self.import_progress.setVisible(True)
        self.import_progress.setValue(0)
        
        self.import_worker = ImportWorker(
            self.import_service,
            self.import_service.import_medical_price_limit,
            file_path,
            None,
            self.username
        )
        self.import_worker.finished.connect(self._on_import_finished)
        self.import_worker.start()
    
    def _import_cloud_catalog(self):
        """导入云药店商品目录"""
        file_path = self.cloud_file_edit.text()
        if not file_path:
            QMessageBox.warning(self, "提示", "请选择文件")
            return
        
        self.import_cloud_btn.setEnabled(False)
        self.import_progress.setVisible(True)
        self.import_progress.setValue(0)
        
        self.import_worker = ImportWorker(
            self.import_service,
            self.import_service.import_cloud_pharmacy_catalog,
            file_path,
            None,
            self.username
        )
        self.import_worker.finished.connect(self._on_import_finished)
        self.import_worker.start()
    
    def _fetch_junyuan_prices(self):
        """抓取君元价格"""
        # 检查数据库配置
        db_config_id = self.jy_db_config_combo.currentData()
        
        if not db_config_id:
            QMessageBox.warning(self, "提示", "请先配置数据库连接，或选择有效的数据库配置")
            return
        
        # 获取自定义SQL
        custom_sql = self.custom_sql_edit.toPlainText().strip()
        
        self.fetch_price_btn.setEnabled(False)
        self.import_progress.setVisible(True)
        self.import_progress.setValue(0)
        
        self.fetch_worker = FetchWorker(
            self.fetch_service,
            db_config_id,
            custom_sql if custom_sql else None,
            self.username
        )
        self.fetch_worker.finished.connect(self._on_fetch_finished)
        self.fetch_worker.start()
    
    def _on_import_finished(self, result):
        """导入完成"""
        self.import_progress.setVisible(False)
        self.import_western_btn.setEnabled(True)
        self.import_chinese_btn.setEnabled(True)
        self.import_price_btn.setEnabled(True)
        self.import_cloud_btn.setEnabled(True)
        
        if result.import_status == "success":
            QMessageBox.information(
                self, "导入成功",
                f"导入完成: 成功 {result.success_rows} 行, 失败 {result.failed_rows} 行"
            )
        else:
            QMessageBox.warning(
                self, "导入失败",
                f"导入失败: {result.error_message}\n成功 {result.success_rows} 行, 失败 {result.failed_rows} 行"
            )
        
        self._load_batches()
    
    def _on_fetch_finished(self, result):
        """抓取完成"""
        self.import_progress.setVisible(False)
        self.fetch_price_btn.setEnabled(True)
        
        if result.fetch_status == "success":
            QMessageBox.information(
                self, "抓取成功",
                f"抓取完成: 成功 {result.success_count} 条, 失败 {result.failed_count} 条"
            )
        else:
            QMessageBox.warning(
                self, "抓取失败",
                f"抓取失败: {result.error_message}"
            )
        
        self._load_batches()
    
    def _delete_selected_batch(self):
        """删除选中的批次"""
        selected_rows = self.batch_table.selectedItems()
        if not selected_rows:
            QMessageBox.warning(self, "提示", "请先选择要删除的批次")
            return
        
        # 获取选中行的批次ID
        row = selected_rows[0].row()
        batch_id = self.batch_table.item(row, 0).text()
        batch_type = self.batch_table.item(row, 1).text()
        file_name = self.batch_table.item(row, 2).text()
        
        # 确认删除
        reply = QMessageBox.question(
            self, "确认删除",
            f"确定要删除以下批次吗？\n\n批次ID: {batch_id}\n类型: {batch_type}\n文件名: {file_name}\n\n删除后将同时删除该批次的所有导入数据！",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )
        
        if reply == QMessageBox.Yes:
            # 执行删除
            if self.import_service.delete_batch(batch_id):
                QMessageBox.information(self, "成功", "批次已删除")
                self._load_batches()
            else:
                QMessageBox.warning(self, "失败", "删除批次失败")
    
    def _load_batches(self):
        """加载批次列表"""
        # 导入批次
        batches = self.import_service.get_import_batches(limit=20)
        
        # 暂时禁用排序，避免添加数据时出现问题
        self.batch_table.setSortingEnabled(False)
        self.batch_table.setRowCount(len(batches))
        
        for row, batch in enumerate(batches):
            self.batch_table.setItem(row, 0, QTableWidgetItem(batch.get('batch_id', '')))
            self.batch_table.setItem(row, 1, QTableWidgetItem(batch.get('batch_type', '')))
            self.batch_table.setItem(row, 2, QTableWidgetItem(batch.get('file_name', '')))
            self.batch_table.setItem(row, 3, QTableWidgetItem(str(batch.get('success_rows', 0))))
            self.batch_table.setItem(row, 4, QTableWidgetItem(str(batch.get('failed_rows', 0))))
            self.batch_table.setItem(row, 5, QTableWidgetItem(batch.get('imported_at', '')))
        
        # 重新启用排序
        self.batch_table.setSortingEnabled(True)
        
        # 加载比对批次下拉框
        available_batches = self.import_service.get_available_batches_for_compare()
        
        # 西药医保目录批次 - 下拉框
        self.western_catalog_combo.clear()
        self.western_catalog_combo.addItem("自动选择最新")
        western_batches = available_batches.get('medical_catalog_western', [])
        
        for batch in western_batches:
            self.western_catalog_combo.addItem(f"{batch['batch_id']}: {batch['file_name']}")
        
        # 中成药医保目录批次 - 下拉框
        self.chinese_catalog_combo.clear()
        self.chinese_catalog_combo.addItem("自动选择最新")
        chinese_batches = available_batches.get('medical_catalog_chinese', [])
        
        for batch in chinese_batches:
            self.chinese_catalog_combo.addItem(f"{batch['batch_id']}: {batch['file_name']}")
        
        self.price_limit_combo.clear()
        self.price_limit_combo.addItem("自动选择最新")
        for batch in available_batches.get('medical_price_limit', []):
            self.price_limit_combo.addItem(f"{batch['batch_id']}: {batch['file_name']}")
        
        self.cloud_catalog_combo.clear()
        self.cloud_catalog_combo.addItem("自动选择最新")
        for batch in available_batches.get('cloud_pharmacy_catalog', []):
            self.cloud_catalog_combo.addItem(f"{batch['batch_id']}: {batch['file_name']}")
        
        self.jy_price_combo.clear()
        self.jy_price_combo.addItem("自动选择最新")
        for batch in available_batches.get('junyuan_sales_price', []):
            self.jy_price_combo.addItem(f"{batch['batch_id']}: SQL抓取")
        
        # 加载比对批次记录
        compare_batches = self.compare_service.get_compare_batches(limit=20)
        self.compare_batch_table.setRowCount(len(compare_batches))
        
        for row, batch in enumerate(compare_batches):
            self.compare_batch_table.setItem(row, 0, QTableWidgetItem(batch.get('batch_id', '')))
            self.compare_batch_table.setItem(row, 1, QTableWidgetItem(batch.get('比对时间', '')))
            self.compare_batch_table.setItem(row, 2, QTableWidgetItem(str(batch.get('总数量', 0))))
            self.compare_batch_table.setItem(row, 3, QTableWidgetItem(str(batch.get('正常数量', 0))))
            self.compare_batch_table.setItem(row, 4, QTableWidgetItem(str(batch.get('异常数量', 0))))
            self.compare_batch_table.setItem(row, 5, QTableWidgetItem(str(batch.get('严重异常数量', 0))))
            self.compare_batch_table.setItem(row, 6, QTableWidgetItem(str(batch.get('待确认数量', 0))))
            self.compare_batch_table.setItem(row, 7, QTableWidgetItem(batch.get('比对状态', '')))
        
        # 加载数据库配置
        self._load_db_configs()
    
    def _load_db_configs(self):
        """加载数据库配置列表"""
        configs = self.db_config_service.get_all_configs()
        
        self.jy_db_config_combo.clear()
        
        if not configs:
            self.jy_db_config_combo.addItem("未配置数据库连接")
            return
        
        for config in configs:
            # DbConfig 是对象，使用属性访问
            display_text = f"{config.name} ({config.host}:{config.port}/{config.database_name})"
            self.jy_db_config_combo.addItem(display_text, config.id)
        
        # 默认读取保存的SQL
        self._load_saved_sql_silent()
    
    def _delete_compare_batch(self):
        """删除选中的比对批次"""
        selected_rows = self.compare_batch_table.selectedItems()
        if not selected_rows:
            QMessageBox.warning(self, "提示", "请先选择要删除的比对批次")
            return
        
        # 获取选中行的批次ID
        row = selected_rows[0].row()
        batch_id = self.compare_batch_table.item(row, 0).text()
        
        # 确认删除
        reply = QMessageBox.question(
            self, "确认删除",
            f"确定要删除比对批次吗？\n\n批次ID: {batch_id}\n\n删除后将同时删除该批次的所有比对结果数据！",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )
        
        if reply == QMessageBox.Yes:
            # 执行删除
            conn = self.db.get_connection()
            cursor = conn.cursor()
            
            try:
                # 删除比对结果
                cursor.execute("DELETE FROM medical_price_compare_result WHERE compare_batch_id = ?", (batch_id,))
                
                # 删除比对批次记录
                cursor.execute("DELETE FROM medical_compare_batches WHERE batch_id = ?", (batch_id,))
                
                conn.commit()
                
                QMessageBox.information(self, "成功", "比对批次已删除")
                self._load_batches()
                
            except Exception as e:
                conn.rollback()
                QMessageBox.warning(self, "失败", f"删除比对批次失败: {e}")
    
    def _save_custom_sql(self):
        """保存自定义SQL"""
        sql_content = self.custom_sql_edit.toPlainText().strip()
        
        if not sql_content:
            QMessageBox.warning(self, "提示", "请先输入SQL内容")
            return
        
        conn = self.db.get_connection()
        cursor = conn.cursor()
        
        try:
            from datetime import datetime
            now = datetime.now().isoformat()
            
            # 保存或更新SQL配置
            cursor.execute('''
                INSERT OR REPLACE INTO custom_sql_configs 
                (config_key, config_name, sql_content, description, created_by, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', (
                'junyuan_price_fetch_sql',
                '君元价格抓取SQL',
                sql_content,
                '君元销售价格抓取的自定义SQL查询语句',
                self.username,
                now,
                now
            ))
            
            conn.commit()
            QMessageBox.information(self, "成功", "SQL已保存")
            
        except Exception as e:
            QMessageBox.warning(self, "保存失败", f"保存SQL失败: {e}")
    
    def _load_saved_sql(self):
        """读取保存的SQL"""
        self._load_saved_sql_silent()
        QMessageBox.information(self, "成功", "已读取保存的SQL")
    
    def _load_saved_sql_silent(self):
        """静默读取保存的SQL（不显示消息框）"""
        conn = self.db.get_connection()
        cursor = conn.cursor()
        
        try:
            cursor.execute('''
                SELECT sql_content FROM custom_sql_configs 
                WHERE config_key = 'junyuan_price_fetch_sql'
                ORDER BY updated_at DESC LIMIT 1
            ''')
            
            result = cursor.fetchone()
            
            if result and result['sql_content']:
                self.custom_sql_edit.setText(result['sql_content'])
            else:
                # 如果没有保存的SQL，使用默认SQL
                default_sql = self.fetch_service.DEFAULT_SQL_TEMPLATE.strip()
                self.custom_sql_edit.setText(default_sql)
            
        except Exception as e:
            # 如果表不存在或其他错误，使用默认SQL
            default_sql = self.fetch_service.DEFAULT_SQL_TEMPLATE.strip()
            self.custom_sql_edit.setText(default_sql)
    
    def _run_compare(self):
        """执行比对"""
        self.run_compare_btn.setEnabled(False)
        self.compare_progress.setVisible(True)
        self.compare_progress.setValue(0)
        
        # 解析批次ID
        batches = {}
        
        # 西药医保目录批次 - 下拉框单选
        western_text = self.western_catalog_combo.currentText()
        western_batch_id = None
        if western_text and western_text != "自动选择最新":
            western_batch_id = western_text.split(":")[0]
        
        # 中成药医保目录批次 - 下拉框单选
        chinese_text = self.chinese_catalog_combo.currentText()
        chinese_batch_id = None
        if chinese_text and chinese_text != "自动选择最新":
            chinese_batch_id = chinese_text.split(":")[0]
        
        # 合并西药和中成药批次（如果有选择）
        medical_batch_ids = []
        if western_batch_id:
            medical_batch_ids.append(western_batch_id)
        if chinese_batch_id:
            medical_batch_ids.append(chinese_batch_id)
        
        if medical_batch_ids:
            batches['medical_catalog'] = medical_batch_ids
        else:
            batches['medical_catalog'] = None  # 自动选择最新
        
        price_text = self.price_limit_combo.currentText()
        if price_text and price_text != "自动选择最新":
            batches['medical_price_limit'] = price_text.split(":")[0]
        
        cloud_text = self.cloud_catalog_combo.currentText()
        if cloud_text and cloud_text != "自动选择最新":
            batches['cloud_pharmacy'] = cloud_text.split(":")[0]
        
        jy_text = self.jy_price_combo.currentText()
        if jy_text and jy_text != "自动选择最新":
            batches['junyuan_price'] = jy_text.split(":")[0]
        
        self.compare_worker = CompareWorker(
            self.compare_service,
            batches,
            self.username
        )
        self.compare_worker.finished.connect(self._on_compare_finished)
        self.compare_worker.start()
    
    def _on_compare_finished(self, result):
        """比对完成"""
        self.compare_progress.setVisible(False)
        self.run_compare_btn.setEnabled(True)
        
        if result.compare_status == "completed":
            # 计算百分比
            total = result.total_count or 1  # 避免除零
            
            normal_percent = (result.normal_count / total * 100) if total > 0 else 0
            abnormal_percent = (result.abnormal_count / total * 100) if total > 0 else 0
            severe_percent = (result.severe_count / total * 100) if total > 0 else 0
            missing_price_percent = (result.missing_price_count / total * 100) if total > 0 else 0
            missing_code_percent = (result.missing_code_count / total * 100) if total > 0 else 0
            pending_percent = (result.pending_count / total * 100) if total > 0 else 0
            
            # 更新统计显示（带百分比）
            self.normal_label.setText(f"正常: {result.normal_count} ({normal_percent:.1f}%)")
            self.abnormal_label.setText(f"异常: {result.abnormal_count} ({abnormal_percent:.1f}%)")
            self.severe_label.setText(f"严重异常: {result.severe_count} ({severe_percent:.1f}%)")
            self.missing_price_label.setText(f"待补价格: {result.missing_price_count} ({missing_price_percent:.1f}%)")
            self.missing_code_label.setText(f"待补编码: {result.missing_code_count} ({missing_code_percent:.1f}%)")
            self.pending_label.setText(f"待确认: {result.pending_count} ({pending_percent:.1f}%)")
            self.total_label.setText(f"总数: {result.total_count}")
            
            QMessageBox.information(
                self, "比对完成",
                f"比对完成: 总数 {result.total_count}\n"
                f"正常 {result.normal_count} ({normal_percent:.1f}%), "
                f"异常 {result.abnormal_count} ({abnormal_percent:.1f}%), "
                f"严重异常 {result.severe_count} ({severe_percent:.1f}%)"
            )
            
            self._load_batches()
        else:
            QMessageBox.warning(self, "比对失败", f"比对失败: {result.error_message}")
    
    def _select_compare_batch(self, item):
        """选择比对批次"""
        row = item.row()
        batch_id = self.compare_batch_table.item(row, 0).text()
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
        
        results = self.compare_service.get_compare_results(
            batch_id=self.current_compare_batch,
            abnormal_level=abnormal_level,
            handle_status=handle_status,
            search_keyword=search_keyword,
            limit=500
        )
        
        self.result_table.setRowCount(len(results))
        
        for row, result in enumerate(results):
            self.result_table.setItem(row, 0, QTableWidgetItem(str(result.get('id', ''))))
            self.result_table.setItem(row, 1, QTableWidgetItem(result.get('商品名称', '')))
            self.result_table.setItem(row, 2, QTableWidgetItem(result.get('规格', '')))
            self.result_table.setItem(row, 3, QTableWidgetItem(result.get('生产厂家', '')))
            self.result_table.setItem(row, 4, QTableWidgetItem(result.get('医保基础价格', '')))
            self.result_table.setItem(row, 5, QTableWidgetItem(result.get('医保价格上限', '')))
            self.result_table.setItem(row, 6, QTableWidgetItem(result.get('君元销售价', '')))
            self.result_table.setItem(row, 7, QTableWidgetItem(result.get('异常等级', '')))
            self.result_table.setItem(row, 8, QTableWidgetItem(result.get('超基础金额', '')))
            self.result_table.setItem(row, 9, QTableWidgetItem(result.get('超上限金额', '')))
            self.result_table.setItem(row, 10, QTableWidgetItem(result.get('处理状态', '')))
            self.result_table.setItem(row, 11, QTableWidgetItem(result.get('处理备注', '')))
    
    def _handle_selected(self):
        """处理选中项"""
        selected_rows = self.result_table.selectedItems()
        if not selected_rows:
            QMessageBox.warning(self, "提示", "请选择要处理的记录")
            return
        
        # 获取选中行的ID
        row = selected_rows[0].row()
        result_id = int(self.result_table.item(row, 0).text())
        
        # 弹出处理对话框
        dialog = HandleDialog(self)
        if dialog.exec() == QDialog.Accepted:
            handle_status = dialog.get_status()
            handle_remark = dialog.get_remark()
            
            if self.compare_service.update_handle_status(
                result_id, handle_status, handle_remark, self.username
            ):
                QMessageBox.information(self, "成功", "处理状态已更新")
                self._load_compare_results()
            else:
                QMessageBox.warning(self, "失败", "更新处理状态失败")
    
    def _export_results(self):
        """导出结果"""
        if not self.current_compare_batch:
            QMessageBox.warning(self, "提示", "请先选择比对批次")
            return
        
        file_path, _ = QFileDialog.getSaveFileName(
            self, "保存Excel文件", "", "Excel Files (*.xlsx)"
        )
        
        if file_path:
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
            
            if results:
                df = pd.DataFrame(results)
                df.to_excel(file_path, index=False)
                QMessageBox.information(self, "成功", f"已导出 {len(results)} 条记录")
            else:
                QMessageBox.warning(self, "提示", "没有数据可导出")
    
    def _select_all_list_items(self, list_widget: QListWidget):
        """全选列表项"""
        for i in range(list_widget.count()):
            list_widget.item(i).setSelected(True)


class HandleDialog(QDialog):
    """处理状态对话框"""
    
    def __init__(self, parent):
        super().__init__(parent)
        self.setWindowTitle("处理状态")
        self.setMinimumWidth(400)
        
        layout = QVBoxLayout(self)
        
        # 处理状态
        form_layout = QFormLayout()
        
        self.status_combo = QComboBox()
        self.status_combo.addItems(["已调价", "已确认不处理", "已忽略"])
        form_layout.addRow("处理状态:", self.status_combo)
        
        self.remark_edit = QTextEdit()
        self.remark_edit.setPlaceholderText("请输入处理备注...")
        form_layout.addRow("处理备注:", self.remark_edit)
        
        layout.addLayout(form_layout)
        
        # 按钮
        btn_layout = QHBoxLayout()
        
        save_btn = QPushButton("保存")
        save_btn.clicked.connect(self.accept)
        btn_layout.addWidget(save_btn)
        
        cancel_btn = QPushButton("取消")
        cancel_btn.clicked.connect(self.reject)
        btn_layout.addWidget(cancel_btn)
        
        layout.addLayout(btn_layout)
    
    def get_status(self) -> str:
        return self.status_combo.currentText()
    
    def get_remark(self) -> str:
        return self.remark_edit.toPlainText()