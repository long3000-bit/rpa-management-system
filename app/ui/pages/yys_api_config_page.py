import logging
import uuid
from datetime import datetime

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QTableWidget, QTableWidgetItem,
    QMessageBox, QDialog, QFormLayout, QLineEdit,
    QSpinBox, QCheckBox, QHeaderView
)

from app.storage.database import Database
from app.core.permission_checker import PermissionChecker, PermissionCodes
from app.core.permission_service import PermissionService


DEFAULT_YYS_API_CONFIG = {
    "config_name": "江阴云药店",
    "host": "http://61.177.139.195:21456/",
    "appkey": "neusoft",
    "appsecret": "f7377865580a02f9a89533b31e4ca7b7",
    "orgcode": "P32028100457",
    "timeout": 30,
}


class YysApiConfigDialog(QDialog):

    def __init__(self, db: Database, config_id: str = None, parent=None):
        super().__init__(parent)
        self.db = db
        self.config_id = config_id
        self._init_ui()

        if config_id:
            self._load_config()
        else:
            self._load_defaults()

    def _init_ui(self):
        self.setWindowTitle("云药店API配置")
        self.setMinimumWidth(560)

        layout = QFormLayout(self)
        layout.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)

        self.name_edit = QLineEdit()
        self.name_edit.setPlaceholderText("例如：江阴云药店")
        layout.addRow("配置名称:", self.name_edit)

        self.host_edit = QLineEdit()
        self.host_edit.setPlaceholderText("例如：http://61.177.139.195:21456/")
        layout.addRow("API地址:", self.host_edit)

        self.appkey_edit = QLineEdit()
        self.appkey_edit.setPlaceholderText("例如：neusoft")
        layout.addRow("appkey:", self.appkey_edit)

        self.appsecret_edit = QLineEdit()
        self.appsecret_edit.setPlaceholderText("例如：f7377865580a02f9a89533b31e4ca7b7")
        layout.addRow("appsecret:", self.appsecret_edit)

        self.orgcode_edit = QLineEdit()
        self.orgcode_edit.setPlaceholderText("例如：P32028100457")
        layout.addRow("药店编码:", self.orgcode_edit)

        self.timeout_spin = QSpinBox()
        self.timeout_spin.setRange(5, 120)
        self.timeout_spin.setValue(DEFAULT_YYS_API_CONFIG["timeout"])
        self.timeout_spin.setSuffix(" 秒")
        layout.addRow("超时时间:", self.timeout_spin)

        self.enabled_checkbox = QCheckBox("启用")
        self.enabled_checkbox.setChecked(True)
        layout.addRow("", self.enabled_checkbox)

        hint = QLabel("说明：当前库存查询接口已关闭，本配置用于 /public/syncstock 差异库存同步。")
        hint.setStyleSheet("color: #666;")
        layout.addRow("", hint)

        btn_layout = QHBoxLayout()

        save_btn = QPushButton("保存")
        save_btn.clicked.connect(self._save)
        btn_layout.addWidget(save_btn)

        cancel_btn = QPushButton("取消")
        cancel_btn.clicked.connect(self.reject)
        btn_layout.addWidget(cancel_btn)

        layout.addRow("", btn_layout)

    def _load_defaults(self):
        self.name_edit.setText(DEFAULT_YYS_API_CONFIG["config_name"])
        self.host_edit.setText(DEFAULT_YYS_API_CONFIG["host"])
        self.appkey_edit.setText(DEFAULT_YYS_API_CONFIG["appkey"])
        self.appsecret_edit.setText(DEFAULT_YYS_API_CONFIG["appsecret"])
        self.orgcode_edit.setText(DEFAULT_YYS_API_CONFIG["orgcode"])
        self.timeout_spin.setValue(DEFAULT_YYS_API_CONFIG["timeout"])
        self.enabled_checkbox.setChecked(True)

    def _load_config(self):
        try:
            conn = self.db.get_connection()
            cursor = conn.cursor()

            cursor.execute('''
                SELECT config_name, host, appkey, appsecret, orgcode, timeout, enabled
                FROM yys_api_config
                WHERE config_id = ?
            ''', (self.config_id,))

            row = cursor.fetchone()
            if row:
                self.name_edit.setText(row['config_name'] or "")
                self.host_edit.setText(row['host'] or "")
                self.appkey_edit.setText(row['appkey'] or "")
                self.appsecret_edit.setText(row['appsecret'] or "")
                self.orgcode_edit.setText(row['orgcode'] or "")
                self.timeout_spin.setValue(row['timeout'] or DEFAULT_YYS_API_CONFIG["timeout"])
                self.enabled_checkbox.setChecked(row['enabled'] == 1)

        except Exception as e:
            logging.error(f"加载API配置失败: {e}")

    def _save(self):
        name = self.name_edit.text().strip()
        host = self.host_edit.text().strip()
        appkey = self.appkey_edit.text().strip()
        appsecret = self.appsecret_edit.text().strip()
        orgcode = self.orgcode_edit.text().strip()
        timeout = self.timeout_spin.value()
        enabled = 1 if self.enabled_checkbox.isChecked() else 0

        if not name:
            QMessageBox.warning(self, "提示", "请输入配置名称")
            return

        if not host:
            QMessageBox.warning(self, "提示", "请输入API地址")
            return

        if not appkey:
            QMessageBox.warning(self, "提示", "请输入appkey")
            return

        if not appsecret:
            QMessageBox.warning(self, "提示", "请输入appsecret")
            return

        if not orgcode:
            QMessageBox.warning(self, "提示", "请输入药店编码")
            return

        try:
            conn = self.db.get_connection()
            cursor = conn.cursor()
            now = datetime.now().isoformat()

            if self.config_id:
                cursor.execute('''
                    UPDATE yys_api_config
                    SET config_name = ?, host = ?, appkey = ?, appsecret = ?, orgcode = ?, timeout = ?, enabled = ?, updated_at = ?
                    WHERE config_id = ?
                ''', (name, host, appkey, appsecret, orgcode, timeout, enabled, now, self.config_id))
            else:
                config_id = uuid.uuid4().hex
                cursor.execute('''
                    INSERT INTO yys_api_config
                    (config_id, config_name, host, appkey, appsecret, orgcode, timeout, enabled, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (config_id, name, host, appkey, appsecret, orgcode, timeout, enabled, now, now))

            conn.commit()
            self.accept()

        except Exception as e:
            logging.error(f"保存API配置失败: {e}")
            QMessageBox.warning(self, "错误", f"保存失败: {str(e)}")


class YysApiConfigPage(QWidget):
    
    def __init__(self, db: Database, username: str = None):
        super().__init__()
        self.db = db
        self.username = username or 'admin'
        
        # 创建权限检查器
        self.permission_checker = PermissionChecker(db, self.username)
        self.permission_service = PermissionService(db)
        
        self._init_ui()
        self._load_configs()

    def _init_ui(self):
        layout = QVBoxLayout(self)

        header_layout = QHBoxLayout()

        title = QLabel("云药店API配置管理")
        title.setStyleSheet("font-size: 16px; font-weight: bold;")
        header_layout.addWidget(title)

        header_layout.addStretch()

        add_btn = QPushButton("新增配置")
        add_btn.clicked.connect(self._add_config)
        header_layout.addWidget(add_btn)

        layout.addLayout(header_layout)

        self.config_table = QTableWidget()
        self.config_table.setColumnCount(7)
        self.config_table.setHorizontalHeaderLabels([
            "配置名称", "API地址", "appkey", "药店编码", "超时时间", "状态", "操作"
        ])
        self.config_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.config_table.setSelectionBehavior(QTableWidget.SelectRows)

        layout.addWidget(self.config_table)

    def _load_configs(self):
        try:
            conn = self.db.get_connection()
            cursor = conn.cursor()

            cursor.execute('''
                SELECT config_id, config_name, host, appkey, orgcode, timeout, enabled
                FROM yys_api_config
                ORDER BY created_at DESC
            ''')

            rows = cursor.fetchall()
            self.config_table.setRowCount(len(rows))

            for row_idx, row in enumerate(rows):
                self.config_table.setItem(row_idx, 0, QTableWidgetItem(row['config_name'] or ""))
                self.config_table.setItem(row_idx, 1, QTableWidgetItem(row['host'] or ""))
                self.config_table.setItem(row_idx, 2, QTableWidgetItem(row['appkey'] or ""))
                self.config_table.setItem(row_idx, 3, QTableWidgetItem(row['orgcode'] or ""))
                self.config_table.setItem(row_idx, 4, QTableWidgetItem(f"{row['timeout'] or 30} 秒"))

                status = "启用" if row['enabled'] == 1 else "禁用"
                self.config_table.setItem(row_idx, 5, QTableWidgetItem(status))

                config_id = row['config_id']

                btn_widget = QWidget()
                btn_layout = QHBoxLayout(btn_widget)
                btn_layout.setContentsMargins(0, 0, 0, 0)

                edit_btn = QPushButton("编辑")
                edit_btn.clicked.connect(lambda checked, cid=config_id: self._edit_config(cid))
                btn_layout.addWidget(edit_btn)

                delete_btn = QPushButton("删除")
                delete_btn.clicked.connect(lambda checked, cid=config_id: self._delete_config(cid))
                btn_layout.addWidget(delete_btn)

                self.config_table.setCellWidget(row_idx, 6, btn_widget)

        except Exception as e:
            logging.error(f"加载API配置列表失败: {e}")

    def _add_config(self):
        # 权限检查
        if not self.permission_checker.check_permission(PermissionCodes.OP_CONFIG_SAVE_YYS_API, self):
            return
        
        dialog = YysApiConfigDialog(self.db, parent=self)
        if dialog.exec():
            # 记录操作日志
            self.permission_service.log_operation(
                username=self.username,
                operation_type='config_create',
                operation_desc='新增云药店API配置',
                target_type='yys_api_config',
                target_id='new',
                detail={'config_name': dialog.name_edit.text()}
            )
            self._load_configs()

    def _edit_config(self, config_id: str):
        # 权限检查
        if not self.permission_checker.check_permission(PermissionCodes.OP_CONFIG_SAVE_YYS_API, self):
            return
        
        dialog = YysApiConfigDialog(self.db, config_id, parent=self)
        if dialog.exec():
            # 记录操作日志
            self.permission_service.log_operation(
                username=self.username,
                operation_type='config_edit',
                operation_desc='编辑云药店API配置',
                target_type='yys_api_config',
                target_id=config_id,
                detail={'config_name': dialog.name_edit.text()}
            )
            self._load_configs()

    def _delete_config(self, config_id: str):
        # 权限检查
        if not self.permission_checker.check_permission(PermissionCodes.OP_CONFIG_SAVE_YYS_API, self):
            return
        
        # 获取配置名称用于日志记录
        config_name = ""
        try:
            conn = self.db.get_connection()
            cursor = conn.cursor()
            cursor.execute('SELECT config_name FROM yys_api_config WHERE config_id = ?', (config_id,))
            row = cursor.fetchone()
            if row:
                config_name = row['config_name']
        except:
            pass
        
        reply = QMessageBox.question(self, "确认", "确定要删除此配置吗？", QMessageBox.Yes | QMessageBox.No)

        if reply == QMessageBox.Yes:
            try:
                conn = self.db.get_connection()
                cursor = conn.cursor()

                cursor.execute('DELETE FROM yys_api_config WHERE config_id = ?', (config_id,))
                conn.commit()

                # 记录操作日志
                self.permission_service.log_operation(
                    username=self.username,
                    operation_type='config_delete',
                    operation_desc='删除云药店API配置',
                    target_type='yys_api_config',
                    target_id=config_id,
                    detail={'config_name': config_name}
                )

                self._load_configs()

            except Exception as e:
                logging.error(f"删除API配置失败: {e}")
                QMessageBox.warning(self, "错误", f"删除失败: {str(e)}")
