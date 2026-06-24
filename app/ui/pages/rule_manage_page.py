"""
评分规则管理页面（完整版）
二期整改：规则集列表、规则配置查看/编辑、规则快照查看、失败编码统计、规则效果统计
新增：新建规则集、编辑规则项、审核、发布（测试/灰度/全量）、版本回滚、版本对比
"""

import json
from datetime import date, datetime

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTabWidget, QTableWidget, QTableWidgetItem, QHeaderView,
    QMessageBox, QTextEdit, QComboBox, QLineEdit, QGroupBox,
    QDialog, QFormLayout, QSpinBox, QDoubleSpinBox, QCheckBox,
    QDialogButtonBox, QSplitter
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont, QColor

from app.storage.database import Database
from app.core.rule_snapshot_service import RuleSnapshotService
from app.core.failure_reason_service import FailureReasonService
from app.core.rule_effect_service import RuleEffectService
from app.core.smart_rule_version_service import SmartRuleVersionService


# ── 新建规则集对话框 ──

class NewRuleSetDialog(QDialog):
    """新建规则集对话框"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("新建规则集")
        self.setMinimumWidth(500)
        self._init_ui()

    def _init_ui(self):
        layout = QFormLayout(self)

        self.code_input = QLineEdit()
        self.code_input.setPlaceholderText("如: custom_v1（英文+数字+下划线）")
        layout.addRow("规则集编码*:", self.code_input)

        self.name_input = QLineEdit()
        self.name_input.setPlaceholderText("如: 自定义规则集V1")
        layout.addRow("规则集名称*:", self.name_input)

        self.version_input = QLineEdit("v1.0.0")
        layout.addRow("版本号:", self.version_input)

        self.desc_input = QLineEdit()
        self.desc_input.setPlaceholderText("可选，规则集描述")
        layout.addRow("描述:", self.desc_input)

        self.reason_input = QLineEdit()
        self.reason_input.setPlaceholderText("如: 新建自定义评分规则")
        layout.addRow("变更原因*:", self.reason_input)

        # 默认规则配置
        config_group = QGroupBox("默认规则配置（可稍后编辑）")
        config_layout = QFormLayout(config_group)

        self.min_purchase_score = QSpinBox()
        self.min_purchase_score.setRange(0, 100)
        self.min_purchase_score.setValue(60)
        config_layout.addRow("候选最低分 (minPurchaseScore):", self.min_purchase_score)

        self.cart_backfill_min_score = QSpinBox()
        self.cart_backfill_min_score.setRange(0, 100)
        self.cart_backfill_min_score.setValue(60)
        config_layout.addRow("反写最低分 (cartBackfillMinScore):", self.cart_backfill_min_score)

        self.price_compare_discount = QDoubleSpinBox()
        self.price_compare_discount.setRange(0.0, 1.0)
        self.price_compare_discount.setSingleStep(0.01)
        self.price_compare_discount.setValue(0.95)
        config_layout.addRow("价格比较折扣 (priceCompareDiscount):", self.price_compare_discount)

        self.price_upper_rate = QDoubleSpinBox()
        self.price_upper_rate.setRange(1.0, 2.0)
        self.price_upper_rate.setSingleStep(0.01)
        self.price_upper_rate.setValue(1.05)
        config_layout.addRow("价格上浮比率 (priceUpperRate):", self.price_upper_rate)

        self.price_upper_plus = QDoubleSpinBox()
        self.price_upper_plus.setRange(0, 100)
        self.price_upper_plus.setValue(1)
        config_layout.addRow("价格上浮加价 (priceUpperPlus):", self.price_upper_plus)

        self.name_weight = QDoubleSpinBox()
        self.name_weight.setRange(0.0, 1.0)
        self.name_weight.setSingleStep(0.01)
        self.name_weight.setValue(0.62)
        config_layout.addRow("名称权重 (nameWeight):", self.name_weight)

        self.spec_weight = QDoubleSpinBox()
        self.spec_weight.setRange(0.0, 1.0)
        self.spec_weight.setSingleStep(0.01)
        self.spec_weight.setValue(0.23)
        config_layout.addRow("规格权重 (specWeight):", self.spec_weight)

        self.maker_weight = QDoubleSpinBox()
        self.maker_weight.setRange(0.0, 1.0)
        self.maker_weight.setSingleStep(0.01)
        self.maker_weight.setValue(0.15)
        config_layout.addRow("厂家权重 (makerWeight):", self.maker_weight)

        self.name_core_min_score = QSpinBox()
        self.name_core_min_score.setRange(0, 100)
        self.name_core_min_score.setValue(70)
        config_layout.addRow("名称核心最低分 (nameCoreMinScore):", self.name_core_min_score)

        self.spec_similar_min_score = QSpinBox()
        self.spec_similar_min_score.setRange(0, 100)
        self.spec_similar_min_score.setValue(70)
        config_layout.addRow("规格相似最低分 (specSimilarMinScore):", self.spec_similar_min_score)

        self.factory_similar_min_score = QSpinBox()
        self.factory_similar_min_score.setRange(0, 100)
        self.factory_similar_min_score.setValue(70)
        config_layout.addRow("厂家相似最低分 (factorySimilarMinScore):", self.factory_similar_min_score)

        self.cart_existing_min_score = QSpinBox()
        self.cart_existing_min_score.setRange(0, 100)
        self.cart_existing_min_score.setValue(70)
        config_layout.addRow("购物车同品种最低分 (cartExistingSameProductMinScore):", self.cart_existing_min_score)

        layout.addRow(config_group)

        # 按钮
        btn_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        btn_box.accepted.connect(self.accept)
        btn_box.rejected.connect(self.reject)
        layout.addRow(btn_box)

    def get_rule_data(self) -> dict:
        return {
            "rule_set_code": self.code_input.text().strip(),
            "rule_set_name": self.name_input.text().strip(),
            "description": self.desc_input.text().strip(),
            "version_number": self.version_input.text().strip() or "v1.0.0",
            "change_reason": self.reason_input.text().strip(),
            "change_type": "new",
            "configs": [
                {"rule_key": "min_purchase_score", "rule_name": "候选最低分", "rule_value": str(self.min_purchase_score.value()), "rule_type": "int", "sort_order": 1},
                {"rule_key": "cart_backfill_min_score", "rule_name": "反写最低分", "rule_value": str(self.cart_backfill_min_score.value()), "rule_type": "int", "sort_order": 2},
                {"rule_key": "price_compare_discount", "rule_name": "价格比较折扣", "rule_value": str(self.price_compare_discount.value()), "rule_type": "float", "sort_order": 3},
                {"rule_key": "price_upper_rate", "rule_name": "价格上浮比率", "rule_value": str(self.price_upper_rate.value()), "rule_type": "float", "sort_order": 4},
                {"rule_key": "price_upper_plus", "rule_name": "价格上浮加价", "rule_value": str(self.price_upper_plus.value()), "rule_type": "float", "sort_order": 5},
                {"rule_key": "name_weight", "rule_name": "名称权重", "rule_value": str(self.name_weight.value()), "rule_type": "float", "sort_order": 6},
                {"rule_key": "spec_weight", "rule_name": "规格权重", "rule_value": str(self.spec_weight.value()), "rule_type": "float", "sort_order": 7},
                {"rule_key": "maker_weight", "rule_name": "厂家权重", "rule_value": str(self.maker_weight.value()), "rule_type": "float", "sort_order": 8},
                {"rule_key": "name_core_min_score", "rule_name": "名称核心最低分", "rule_value": str(self.name_core_min_score.value()), "rule_type": "int", "sort_order": 9},
                {"rule_key": "spec_similar_min_score", "rule_name": "规格相似最低分", "rule_value": str(self.spec_similar_min_score.value()), "rule_type": "int", "sort_order": 10},
                {"rule_key": "factory_similar_min_score", "rule_name": "厂家相似最低分", "rule_value": str(self.factory_similar_min_score.value()), "rule_type": "int", "sort_order": 11},
                {"rule_key": "cart_existing_same_product_min_score", "rule_name": "购物车同品种最低分", "rule_value": str(self.cart_existing_min_score.value()), "rule_type": "int", "sort_order": 12},
            ]
        }


# ── 编辑规则项对话框 ──

class EditRuleConfigDialog(QDialog):
    """编辑规则配置项对话框"""

    def __init__(self, rule_set_code: str, configs: list, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"编辑规则配置 - {rule_set_code}")
        self.setMinimumWidth(600)
        self.setMinimumHeight(500)
        self.rule_set_code = rule_set_code
        self._configs = configs
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)

        self.table = QTableWidget()
        self.table.setColumnCount(4)
        self.table.setHorizontalHeaderLabels(["规则键", "规则名称", "规则值", "类型"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table.setRowCount(len(self._configs))
        for i, c in enumerate(self._configs):
            self.table.setItem(i, 0, QTableWidgetItem(c.get("rule_key", "")))
            self.table.setItem(i, 1, QTableWidgetItem(c.get("rule_name", "")))
            self.table.setItem(i, 2, QTableWidgetItem(c.get("rule_value", "")))
            self.table.setItem(i, 3, QTableWidgetItem(c.get("rule_type", "")))
        layout.addWidget(self.table)

        btn_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        btn_box.accepted.connect(self.accept)
        btn_box.rejected.connect(self.reject)
        layout.addWidget(btn_box)

    def get_configs(self) -> list:
        configs = []
        for i in range(self.table.rowCount()):
            key_item = self.table.item(i, 0)
            name_item = self.table.item(i, 1)
            value_item = self.table.item(i, 2)
            type_item = self.table.item(i, 3)
            if key_item and value_item:
                configs.append({
                    "rule_key": key_item.text(),
                    "rule_name": name_item.text() if name_item else "",
                    "rule_value": value_item.text(),
                    "rule_type": type_item.text() if type_item else "string",
                    "sort_order": i + 1,
                })
        return configs


# ── 主页面 ──

class RuleManagePage(QWidget):
    """评分规则管理页面（完整版）"""

    def __init__(self, db: Database, username: str = "", role_code: str = ""):
        super().__init__()
        self.db = db
        self.username = username
        self.role_code = role_code
        self._snapshot_service = RuleSnapshotService(db)
        self._failure_service = FailureReasonService(db)
        self._effect_service = RuleEffectService(db)
        self._version_service = SmartRuleVersionService(db)
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)

        # 标题
        title = QLabel("评分规则管理")
        title.setFont(QFont("", 14, QFont.Weight.Bold))
        layout.addWidget(title)

        # Tab 页
        self.tabs = QTabWidget()
        self.tabs.addTab(self._create_rule_set_tab(), "规则集管理")
        self.tabs.addTab(self._create_snapshot_tab(), "规则快照")
        self.tabs.addTab(self._create_failure_stats_tab(), "失败编码统计")
        self.tabs.addTab(self._create_effect_stats_tab(), "规则效果统计")
        layout.addWidget(self.tabs)

        # 刷新按钮
        btn_layout = QHBoxLayout()
        refresh_btn = QPushButton("刷新数据")
        refresh_btn.clicked.connect(self._refresh_all)
        btn_layout.addStretch()
        btn_layout.addWidget(refresh_btn)
        layout.addLayout(btn_layout)

    # ── 规则集管理 Tab ──

    def _create_rule_set_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)

        # 操作按钮区
        op_layout = QHBoxLayout()
        new_btn = QPushButton("新建规则集")
        new_btn.clicked.connect(self._on_new_rule_set)
        op_layout.addWidget(new_btn)

        edit_btn = QPushButton("编辑配置")
        edit_btn.clicked.connect(self._on_edit_rule_config)
        op_layout.addWidget(edit_btn)

        audit_btn = QPushButton("提交审核")
        audit_btn.clicked.connect(self._on_audit_rule)
        op_layout.addWidget(audit_btn)

        publish_test_btn = QPushButton("测试发布")
        publish_test_btn.clicked.connect(lambda: self._on_publish("testing"))
        op_layout.addWidget(publish_test_btn)

        publish_gray_btn = QPushButton("灰度发布")
        publish_gray_btn.clicked.connect(lambda: self._on_publish("gray"))
        op_layout.addWidget(publish_gray_btn)

        publish_full_btn = QPushButton("全量发布")
        publish_full_btn.clicked.connect(lambda: self._on_publish("full"))
        op_layout.addWidget(publish_full_btn)

        rollback_btn = QPushButton("版本回滚")
        rollback_btn.clicked.connect(self._on_rollback)
        op_layout.addWidget(rollback_btn)

        compare_btn = QPushButton("版本对比")
        compare_btn.clicked.connect(self._on_compare)
        op_layout.addWidget(compare_btn)

        op_layout.addStretch()
        layout.addLayout(op_layout)

        # 规则集列表
        self.rule_set_table = QTableWidget()
        self.rule_set_table.setColumnCount(8)
        self.rule_set_table.setHorizontalHeaderLabels([
            "规则集编码", "规则集名称", "版本号", "状态", "审核状态",
            "是否默认", "创建时间", "更新时间"
        ])
        self.rule_set_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.rule_set_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.rule_set_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        layout.addWidget(self.rule_set_table)

        # 规则配置查看区
        config_group = QGroupBox("规则配置（选中规则集后显示）")
        config_layout = QVBoxLayout(config_group)
        self.config_text = QTextEdit()
        self.config_text.setReadOnly(True)
        self.config_text.setMaximumHeight(200)
        config_layout.addWidget(self.config_text)
        layout.addWidget(config_group)

        self.rule_set_table.itemSelectionChanged.connect(self._on_rule_set_selected)
        self._load_rule_sets()
        return widget

    def _load_rule_sets(self):
        conn = self.db.get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute(
                "SELECT rule_set_code, rule_set_name, version_number, "
                "COALESCE(version_status, status) as status, "
                "COALESCE(audit_status, '') as audit_status, "
                "is_default, created_at, updated_at "
                "FROM smart_match_rule_sets ORDER BY is_default DESC, created_at DESC"
            )
            rows = cursor.fetchall()
            self.rule_set_table.setRowCount(len(rows))
            for i, row in enumerate(rows):
                self.rule_set_table.setItem(i, 0, QTableWidgetItem(row["rule_set_code"] or ""))
                self.rule_set_table.setItem(i, 1, QTableWidgetItem(row["rule_set_name"] or ""))
                self.rule_set_table.setItem(i, 2, QTableWidgetItem(str(row["version_number"] or "")))
                status_item = QTableWidgetItem(row["status"] or "")
                # 状态颜色
                status = row["status"] or ""
                if status == "active":
                    status_item.setForeground(QColor("green"))
                elif status == "draft":
                    status_item.setForeground(QColor("gray"))
                elif status == "testing":
                    status_item.setForeground(QColor("orange"))
                elif status == "deprecated":
                    status_item.setForeground(QColor("red"))
                self.rule_set_table.setItem(i, 3, status_item)
                self.rule_set_table.setItem(i, 4, QTableWidgetItem(row["audit_status"] or ""))
                self.rule_set_table.setItem(i, 5, QTableWidgetItem("是" if row["is_default"] else "否"))
                self.rule_set_table.setItem(i, 6, QTableWidgetItem(row["created_at"] or ""))
                self.rule_set_table.setItem(i, 7, QTableWidgetItem(row["updated_at"] or ""))
        except Exception:
            self.rule_set_table.setRowCount(0)

    def _get_selected_rule_set_code(self) -> str:
        rows = self.rule_set_table.selectedItems()
        if not rows:
            return ""
        row = rows[0].row()
        code_item = self.rule_set_table.item(row, 0)
        return code_item.text() if code_item else ""

    def _on_rule_set_selected(self):
        rule_set_code = self._get_selected_rule_set_code()
        if not rule_set_code:
            return

        conn = self.db.get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute(
                "SELECT rule_key, rule_name, rule_value, rule_type, "
                "COALESCE(description, rule_desc, '') as description "
                "FROM smart_match_rule_configs WHERE rule_set_code = ? AND is_enabled = 1 ORDER BY sort_order",
                (rule_set_code,)
            )
            configs = cursor.fetchall()
            if configs:
                lines = [f"规则集: {rule_set_code}\n"]
                for c in configs:
                    desc = c["description"] or ""
                    lines.append(f"  {c['rule_key']} = {c['rule_value']}  ({c['rule_name']}, 类型: {c['rule_type']}){f'  // {desc}' if desc else ''}")
                self.config_text.setText("\n".join(lines))
            else:
                self.config_text.setText(f"规则集 {rule_set_code} 暂无配置项（可能使用内置默认值）")
        except Exception as e:
            self.config_text.setText(f"读取配置失败: {e}")

    def _on_new_rule_set(self):
        dialog = NewRuleSetDialog(self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            rule_data = dialog.get_rule_data()
            if not rule_data["rule_set_code"] or not rule_data["rule_set_name"] or not rule_data["change_reason"]:
                QMessageBox.warning(self, "提示", "规则集编码、名称、变更原因不能为空")
                return
            _, error = self._version_service.create_rule_version(rule_data, self.username or "admin")
            if error:
                QMessageBox.critical(self, "创建失败", error)
            else:
                QMessageBox.information(self, "成功", f"规则集 {rule_data['rule_set_code']} 创建成功")
                self._load_rule_sets()

    def _on_edit_rule_config(self):
        rule_set_code = self._get_selected_rule_set_code()
        if not rule_set_code:
            QMessageBox.warning(self, "提示", "请先选中一个规则集")
            return

        conn = self.db.get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute(
                "SELECT rule_key, rule_name, rule_value, rule_type "
                "FROM smart_match_rule_configs WHERE rule_set_code = ? AND is_enabled = 1 ORDER BY sort_order",
                (rule_set_code,)
            )
            configs = [dict(row) for row in cursor.fetchall()]
        except Exception as e:
            QMessageBox.critical(self, "读取失败", str(e))
            return

        if not configs:
            QMessageBox.information(self, "提示", "该规则集暂无配置项，请先新建规则集")
            return

        dialog = EditRuleConfigDialog(rule_set_code, configs, self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            new_configs = dialog.get_configs()
            rule_data = {
                "rule_set_code": rule_set_code,
                "configs": new_configs,
                "change_reason": "编辑规则配置",
                "change_type": "update",
            }
            ok, error = self._version_service.update_rule_version(rule_set_code, rule_data, self.username or "admin")
            if error:
                QMessageBox.critical(self, "编辑失败", error)
            else:
                QMessageBox.information(self, "成功", f"规则集 {rule_set_code} 配置已更新")
                self._load_rule_sets()
                self._on_rule_set_selected()

    def _on_audit_rule(self):
        rule_set_code = self._get_selected_rule_set_code()
        if not rule_set_code:
            QMessageBox.warning(self, "提示", "请先选中一个规则集")
            return

        # 查找待审核记录
        conn = self.db.get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute(
                "SELECT audit_id, rule_set_code, change_type, new_version, audit_status "
                "FROM smart_rule_audit_logs WHERE rule_set_code = ? AND audit_status = 'pending' "
                "ORDER BY created_at DESC LIMIT 1",
                (rule_set_code,)
            )
            audit_row = cursor.fetchone()
        except Exception:
            audit_row = None

        if not audit_row:
            QMessageBox.information(self, "提示", f"规则集 {rule_set_code} 没有待审核记录")
            return

        audit_id = audit_row["audit_id"]
        reply = QMessageBox.question(
            self, "审核确认",
            f"规则集: {rule_set_code}\n变更类型: {audit_row['change_type']}\n新版本: {audit_row['new_version']}\n\n是否通过审核？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No | QMessageBox.StandardButton.Cancel
        )
        if reply == QMessageBox.StandardButton.Cancel:
            return

        audit_status = "approved" if reply == QMessageBox.StandardButton.Yes else "rejected"
        ok, error = self._version_service.audit_rule_version(
            audit_id, audit_status, self.username or "admin", ""
        )
        if error:
            QMessageBox.critical(self, "审核失败", error)
        else:
            QMessageBox.information(self, "成功", f"审核{'通过' if audit_status == 'approved' else '拒绝'}")
            self._load_rule_sets()

    def _on_publish(self, release_type: str):
        rule_set_code = self._get_selected_rule_set_code()
        if not rule_set_code:
            QMessageBox.warning(self, "提示", "请先选中一个规则集")
            return

        type_names = {"testing": "测试发布", "gray": "灰度发布", "full": "全量发布"}
        gray_config = None

        if release_type == "gray":
            # 灰度配置
            gray_ratio, ok = QInputDialog.getInt(self, "灰度配置", "灰度比例 (0-100):", 10, 0, 100)
            if not ok:
                return
            gray_config = {"gray_type": "ratio", "gray_ratio": gray_ratio}

        confirm = QMessageBox.question(
            self, "发布确认",
            f"确认对规则集 {rule_set_code} 执行 {type_names[release_type]}？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if confirm != QMessageBox.StandardButton.Yes:
            return

        ok, error = self._version_service.release_rule_version(rule_set_code, release_type, gray_config)
        if error:
            QMessageBox.critical(self, "发布失败", error)
        else:
            QMessageBox.information(self, "成功", f"{type_names[release_type]}成功")
            self._load_rule_sets()

    def _on_rollback(self):
        rule_set_code = self._get_selected_rule_set_code()
        if not rule_set_code:
            QMessageBox.warning(self, "提示", "请先选中一个规则集")
            return

        # 查询可用版本
        conn = self.db.get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute(
                "SELECT version_number, version_status FROM smart_match_rule_sets "
                "WHERE rule_set_code = ? ORDER BY created_at DESC",
                (rule_set_code,)
            )
            versions = cursor.fetchall()
        except Exception:
            versions = []

        if not versions:
            QMessageBox.information(self, "提示", "无可用版本")
            return

        version_strs = [f"{v['version_number']} ({v['version_status']})" for v in versions]
        from PySide6.QtWidgets import QInputDialog
        version_str, ok = QInputDialog.getItem(
            self, "版本回滚", f"选择回滚到的版本（规则集: {rule_set_code}）:", version_strs, 0, False
        )
        if not ok:
            return

        rollback_version = version_str.split(" ")[0]
        confirm = QMessageBox.question(
            self, "回滚确认",
            f"确认将规则集 {rule_set_code} 回滚到版本 {rollback_version}？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if confirm != QMessageBox.StandardButton.Yes:
            return

        ok, error = self._version_service.rollback_rule_version(rule_set_code, rollback_version)
        if error:
            QMessageBox.critical(self, "回滚失败", error)
        else:
            QMessageBox.information(self, "成功", f"已回滚到版本 {rollback_version}")
            self._load_rule_sets()

    def _on_compare(self):
        rule_set_code = self._get_selected_rule_set_code()
        if not rule_set_code:
            QMessageBox.warning(self, "提示", "请先选中一个规则集")
            return

        # 查询版本列表
        conn = self.db.get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute(
                "SELECT version_number FROM smart_match_rule_sets "
                "WHERE rule_set_code = ? ORDER BY created_at DESC",
                (rule_set_code,)
            )
            versions = [row["version_number"] for row in cursor.fetchall()]
        except Exception:
            versions = []

        if len(versions) < 2:
            QMessageBox.information(self, "提示", "至少需要2个版本才能对比")
            return

        from PySide6.QtWidgets import QInputDialog
        v1_str, ok1 = QInputDialog.getItem(self, "版本对比", "选择版本1:", versions, 0, False)
        if not ok1:
            return
        v2_str, ok2 = QInputDialog.getItem(self, "版本对比", "选择版本2:", versions, min(1, len(versions) - 1), False)
        if not ok2:
            return

        version1 = f"{rule_set_code}@{v1_str}"
        version2 = f"{rule_set_code}@{v2_str}"
        result, error = self._version_service.compare_rule_versions(version1, version2)
        if error:
            QMessageBox.critical(self, "对比失败", error)
            return

        # 显示对比结果
        diff_text = json.dumps(result, ensure_ascii=False, indent=2)
        dialog = QDialog(self)
        dialog.setWindowTitle(f"版本对比: {v1_str} vs {v2_str}")
        dialog.setMinimumSize(600, 400)
        dlg_layout = QVBoxLayout(dialog)
        text_edit = QTextEdit()
        text_edit.setReadOnly(True)
        text_edit.setText(diff_text)
        dlg_layout.addWidget(text_edit)
        close_btn = QPushButton("关闭")
        close_btn.clicked.connect(dialog.close)
        dlg_layout.addWidget(close_btn)
        dialog.exec()

    # ── 规则快照 Tab ──

    def _create_snapshot_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)

        search_layout = QHBoxLayout()
        search_layout.addWidget(QLabel("批次ID:"))
        self.snapshot_batch_input = QLineEdit()
        self.snapshot_batch_input.setPlaceholderText("输入批次ID搜索快照")
        search_layout.addWidget(self.snapshot_batch_input)
        search_btn = QPushButton("搜索")
        search_btn.clicked.connect(self._load_snapshots)
        search_layout.addWidget(search_btn)
        search_layout.addStretch()
        layout.addLayout(search_layout)

        self.snapshot_table = QTableWidget()
        self.snapshot_table.setColumnCount(7)
        self.snapshot_table.setHorizontalHeaderLabels([
            "快照ID", "批次ID", "规则集编码", "版本", "Fallback", "Fallback原因", "创建时间"
        ])
        self.snapshot_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.snapshot_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        layout.addWidget(self.snapshot_table)

        snapshot_detail_group = QGroupBox("快照内容（选中快照后显示）")
        snapshot_detail_layout = QVBoxLayout(snapshot_detail_group)
        self.snapshot_detail_text = QTextEdit()
        self.snapshot_detail_text.setReadOnly(True)
        self.snapshot_detail_text.setMaximumHeight(250)
        snapshot_detail_layout.addWidget(self.snapshot_detail_text)
        layout.addWidget(snapshot_detail_group)

        self.snapshot_table.itemSelectionChanged.connect(self._on_snapshot_selected)
        self._load_snapshots()
        return widget

    def _load_snapshots(self):
        batch_id = self.snapshot_batch_input.text().strip()
        conn = self.db.get_connection()
        cursor = conn.cursor()
        try:
            if batch_id:
                cursor.execute(
                    "SELECT snapshot_id, batch_id, rule_set_code, rule_set_version, "
                    "fallback_used, fallback_reason, created_at "
                    "FROM smart_match_rule_snapshots WHERE batch_id LIKE ? ORDER BY created_at DESC LIMIT 50",
                    (f"%{batch_id}%",)
                )
            else:
                cursor.execute(
                    "SELECT snapshot_id, batch_id, rule_set_code, rule_set_version, "
                    "fallback_used, fallback_reason, created_at "
                    "FROM smart_match_rule_snapshots ORDER BY created_at DESC LIMIT 50"
                )
            rows = cursor.fetchall()
            self.snapshot_table.setRowCount(len(rows))
            for i, row in enumerate(rows):
                self.snapshot_table.setItem(i, 0, QTableWidgetItem(row["snapshot_id"] or ""))
                self.snapshot_table.setItem(i, 1, QTableWidgetItem(row["batch_id"] or ""))
                self.snapshot_table.setItem(i, 2, QTableWidgetItem(row["rule_set_code"] or ""))
                self.snapshot_table.setItem(i, 3, QTableWidgetItem(str(row["rule_set_version"] or "")))
                self.snapshot_table.setItem(i, 4, QTableWidgetItem("是" if row["fallback_used"] else "否"))
                self.snapshot_table.setItem(i, 5, QTableWidgetItem(row["fallback_reason"] or ""))
                self.snapshot_table.setItem(i, 6, QTableWidgetItem(row["created_at"] or ""))
        except Exception:
            self.snapshot_table.setRowCount(0)

    def _on_snapshot_selected(self):
        rows = self.snapshot_table.selectedItems()
        if not rows:
            return
        row = rows[0].row()
        sid_item = self.snapshot_table.item(row, 0)
        if not sid_item:
            return
        snapshot_id = sid_item.text()
        snapshot = self._snapshot_service.get_rule_snapshot(snapshot_id)
        if snapshot:
            try:
                parsed = json.loads(snapshot.get("snapshot_json", "{}"))
                self.snapshot_detail_text.setText(json.dumps(parsed, ensure_ascii=False, indent=2))
            except Exception:
                self.snapshot_detail_text.setText(snapshot.get("snapshot_json", ""))
        else:
            self.snapshot_detail_text.setText("未找到快照")

    # ── 失败编码统计 Tab ──

    def _create_failure_stats_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)

        search_layout = QHBoxLayout()
        search_layout.addWidget(QLabel("批次ID:"))
        self.failure_batch_input = QLineEdit()
        self.failure_batch_input.setPlaceholderText("输入批次ID筛选（留空查全部）")
        search_layout.addWidget(self.failure_batch_input)
        search_btn = QPushButton("查询")
        search_btn.clicked.connect(self._load_failure_stats)
        search_layout.addWidget(search_btn)
        search_layout.addStretch()
        layout.addLayout(search_layout)

        self.failure_stats_table = QTableWidget()
        self.failure_stats_table.setColumnCount(5)
        self.failure_stats_table.setHorizontalHeaderLabels([
            "失败编码", "失败阶段", "数量", "失败消息", "建议"
        ])
        self.failure_stats_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.failure_stats_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        layout.addWidget(self.failure_stats_table)

        self._load_failure_stats()
        return widget

    def _load_failure_stats(self):
        batch_id = self.failure_batch_input.text().strip()
        try:
            stats = self._failure_service.get_failure_stats_by_code(batch_id=batch_id or None)
            self.failure_stats_table.setRowCount(len(stats))
            for i, s in enumerate(stats):
                self.failure_stats_table.setItem(i, 0, QTableWidgetItem(s.get("failure_code", "")))
                self.failure_stats_table.setItem(i, 1, QTableWidgetItem(s.get("failure_stage", "")))
                self.failure_stats_table.setItem(i, 2, QTableWidgetItem(str(s.get("count", 0))))
                self.failure_stats_table.setItem(i, 3, QTableWidgetItem(s.get("failure_message", "")))
                self.failure_stats_table.setItem(i, 4, QTableWidgetItem(s.get("suggestion", "")))
        except Exception:
            self.failure_stats_table.setRowCount(0)

    # ── 规则效果统计 Tab ──

    def _create_effect_stats_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)

        search_layout = QHBoxLayout()
        search_layout.addWidget(QLabel("规则集编码:"))
        self.effect_rule_set_input = QLineEdit("default_v1")
        search_layout.addWidget(self.effect_rule_set_input)
        search_layout.addWidget(QLabel("开始日期:"))
        self.effect_start_input = QLineEdit()
        self.effect_start_input.setPlaceholderText(date.today().strftime("%Y-%m-%d"))
        search_layout.addWidget(self.effect_start_input)
        search_layout.addWidget(QLabel("结束日期:"))
        self.effect_end_input = QLineEdit()
        self.effect_end_input.setPlaceholderText(date.today().strftime("%Y-%m-%d"))
        search_layout.addWidget(self.effect_end_input)
        search_btn = QPushButton("查询")
        search_btn.clicked.connect(self._load_effect_stats)
        search_layout.addWidget(search_btn)
        search_layout.addStretch()
        layout.addLayout(search_layout)

        self.effect_stats_text = QTextEdit()
        self.effect_stats_text.setReadOnly(True)
        layout.addWidget(self.effect_stats_text)

        return widget

    def _load_effect_stats(self):
        rule_set_code = self.effect_rule_set_input.text().strip() or "default_v1"
        start_date = self.effect_start_input.text().strip()
        end_date = self.effect_end_input.text().strip()
        if not start_date or not end_date:
            today = date.today().strftime("%Y-%m-%d")
            start_date = start_date or today
            end_date = end_date or today

        result, error = self._effect_service.get_rule_effect_stats(rule_set_code, start_date, end_date)
        if error:
            self.effect_stats_text.setText(f"查询失败: {error}")
            return

        lines = [
            f"规则集: {result.get('rule_set_code', '')}",
            f"统计区间: {result.get('start_date', '')} ~ {result.get('end_date', '')}",
            f"总商品数: {result.get('total_items', 0)}",
            f"匹配数: {result.get('matched_items', 0)}",
            f"采购成功数: {result.get('purchased_items', 0)}",
            f"失败数: {result.get('failed_items', 0)}",
            f"匹配成功率: {result.get('match_success_rate', 0):.1%}",
            f"采购成功率: {result.get('purchase_success_rate', 0):.1%}",
            f"平均匹配分: {result.get('avg_match_score', 0):.1f}",
            "",
            "=== 失败编码分布 ===",
        ]
        fcd = result.get("failure_code_distribution", {})
        if fcd:
            for code, count in fcd.items():
                lines.append(f"  {code}: {count}")
        else:
            lines.append("  暂无数据")

        lines.append("")
        lines.append("=== 失败原因分布（旧口径）===")
        frd = result.get("failure_reason_distribution", {})
        if frd:
            for reason, count in frd.items():
                lines.append(f"  {reason}: {count}")
        else:
            lines.append("  暂无数据")

        lines.append("")
        lines.append("=== 评分分布 ===")
        sd = result.get("score_distribution", {})
        if sd:
            for rng, count in sd.items():
                lines.append(f"  {rng}: {count}")
        else:
            lines.append("  暂无数据")

        self.effect_stats_text.setText("\n".join(lines))

    # ── 刷新 ──

    def _refresh_all(self):
        self._load_rule_sets()
        self._load_snapshots()
        self._load_failure_stats()
        self.config_text.clear()
        self.snapshot_detail_text.clear()
