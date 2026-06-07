from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QLineEdit, QPushButton, QCheckBox,
    QSpacerItem, QSizePolicy, QDialog, QMessageBox
)
from PySide6.QtCore import Qt, Signal

from app.config import APP_NAME, APP_VERSION
from app.core.auth_service import AuthService
from app.core.password_service import PasswordService


class ChangePasswordDialog(QDialog):
    """修改密码对话框"""
    
    def __init__(self, username: str, auth_service: AuthService, parent=None):
        super().__init__(parent)
        self.username = username
        self.auth_service = auth_service
        self.setWindowTitle("修改密码")
        self.setFixedSize(400, 280)
        self.setStyleSheet(self._get_stylesheet())
        self._init_ui()
    
    def _get_stylesheet(self):
        return """
            QWidget {
                background-color: #ffffff;
                font-family: "Microsoft YaHei", "SimHei", sans-serif;
            }
            QLabel#title {
                font-size: 18px;
                font-weight: bold;
                color: #1a73e8;
            }
            QLabel#warning {
                color: #d32f2f;
                font-size: 14px;
            }
            QLineEdit {
                padding: 0 15px;
                border: 2px solid #aaa;
                border-radius: 8px;
                background-color: #fafafa;
                font-size: 16px;
                color: #333;
                height: 44px;
            }
            QLineEdit:focus {
                border: 2px solid #1a73e8;
                background-color: white;
            }
            QPushButton#confirmBtn {
                background-color: #1a73e8;
                color: white;
                border: none;
                border-radius: 8px;
                font-size: 16px;
                font-weight: bold;
                height: 44px;
            }
            QPushButton#confirmBtn:hover {
                background-color: #1557b0;
            }
            QPushButton#cancelBtn {
                background-color: #f0f0f0;
                color: #333;
                border: 2px solid #aaa;
                border-radius: 8px;
                font-size: 16px;
                height: 44px;
            }
            QPushButton#cancelBtn:hover {
                background-color: #e0e0e0;
            }
        """
    
    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(30, 20, 30, 20)
        layout.setSpacing(12)
        
        # 标题
        title_label = QLabel("请修改临时密码")
        title_label.setObjectName("title")
        title_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(title_label)
        
        # 提示信息
        warning_label = QLabel("您的账号使用临时密码，请立即修改以确保安全")
        warning_label.setObjectName("warning")
        warning_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(warning_label)
        
        # 新密码输入
        layout.addWidget(QLabel("新密码:"))
        self.new_password_input = QLineEdit()
        self.new_password_input.setPlaceholderText("请输入新密码（至少8位，包含字母和数字）")
        self.new_password_input.setEchoMode(QLineEdit.Password)
        layout.addWidget(self.new_password_input)
        
        # 确认密码输入
        layout.addWidget(QLabel("确认密码:"))
        self.confirm_password_input = QLineEdit()
        self.confirm_password_input.setPlaceholderText("请再次输入新密码")
        self.confirm_password_input.setEchoMode(QLineEdit.Password)
        layout.addWidget(self.confirm_password_input)
        
        # 错误提示
        self.error_label = QLabel("")
        self.error_label.setObjectName("warning")
        self.error_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.error_label)
        
        # 按钮
        btn_layout = QHBoxLayout()
        
        self.confirm_btn = QPushButton("确认修改")
        self.confirm_btn.setObjectName("confirmBtn")
        self.confirm_btn.clicked.connect(self._confirm_change)
        btn_layout.addWidget(self.confirm_btn)
        
        self.cancel_btn = QPushButton("取消")
        self.cancel_btn.setObjectName("cancelBtn")
        self.cancel_btn.clicked.connect(self.reject)
        btn_layout.addWidget(self.cancel_btn)
        
        layout.addLayout(btn_layout)
    
    def _confirm_change(self):
        new_password = self.new_password_input.text()
        confirm_password = self.confirm_password_input.text()
        
        self.error_label.setText("")
        
        # 验证密码
        if not new_password:
            self.error_label.setText("请输入新密码")
            return
        
        if new_password != confirm_password:
            self.error_label.setText("两次输入的密码不一致")
            return
        
        # 验证密码复杂度
        valid, msg = PasswordService.validate_password(new_password)
        if not valid:
            self.error_label.setText(msg)
            return
        
        # 修改密码（临时密码场景，不需要验证旧密码）
        # 直接更新密码并清除 must_change_password 标记
        try:
            password_data = PasswordService.create_password_hash(new_password)
            self.auth_service.db.update_password(
                self.username,
                password_data['password_hash'],
                password_data['salt'],
                password_data['hash_iterations']
            )
            
            # 清除 must_change_password 标记
            conn = self.auth_service.db.get_connection()
            cursor = conn.cursor()
            cursor.execute('''
                UPDATE users SET must_change_password = 0, updated_at = ?
                WHERE username = ?
            ''', (self.auth_service.db._get_now(), self.username))
            conn.commit()
            
            QMessageBox.information(self, "成功", "密码修改成功，请重新登录")
            self.accept()
        except Exception as e:
            self.error_label.setText(f"修改失败: {e}")


class LoginWindow(QWidget):
    
    login_success = Signal(dict)
    
    def __init__(self, db):
        super().__init__()
        self.db = db
        self.auth_service = AuthService(db)
        self._init_ui()
        self._load_remembered_username()
    
    def _init_ui(self):
        self.setWindowTitle(f"{APP_NAME} - 登录")
        self.setFixedSize(420, 360)
        self.setStyleSheet(self._get_stylesheet())
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(42, 36, 42, 28)
        layout.setSpacing(14)
        
        title_label = QLabel(APP_NAME)
        title_label.setObjectName("title")
        title_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(title_label)
        
        layout.addSpacerItem(QSpacerItem(20, 20, QSizePolicy.Minimum, QSizePolicy.Expanding))
        
        self.username_input = QLineEdit()
        self.username_input.setPlaceholderText("用户名")
        self.username_input.setObjectName("inputField")
        self.username_input.setFixedHeight(52)
        self.username_input.returnPressed.connect(self._attempt_login)
        layout.addWidget(self.username_input)
        
        password_container = QHBoxLayout()
        password_container.setSpacing(0)
        
        self.password_input = QLineEdit()
        self.password_input.setPlaceholderText("密码")
        self.password_input.setEchoMode(QLineEdit.Password)
        self.password_input.setObjectName("passwordField")
        self.password_input.setFixedHeight(52)
        self.password_input.returnPressed.connect(self._attempt_login)
        password_container.addWidget(self.password_input)
        
        self.toggle_password_btn = QPushButton("显示")
        self.toggle_password_btn.setObjectName("toggleBtn")
        self.toggle_password_btn.setFixedSize(64, 52)
        self.toggle_password_btn.clicked.connect(self._toggle_password_visibility)
        password_container.addWidget(self.toggle_password_btn)
        
        layout.addLayout(password_container)
        
        self.remember_checkbox = QCheckBox("记住用户名")
        self.remember_checkbox.setObjectName("checkbox")
        layout.addWidget(self.remember_checkbox)
        
        self.login_btn = QPushButton("登 录")
        self.login_btn.setObjectName("loginBtn")
        self.login_btn.setFixedHeight(52)
        self.login_btn.clicked.connect(self._attempt_login)
        layout.addWidget(self.login_btn)
        
        self.error_label = QLabel("")
        self.error_label.setObjectName("errorLabel")
        self.error_label.setAlignment(Qt.AlignCenter)
        self.error_label.setFixedHeight(22)
        layout.addWidget(self.error_label)
        
        layout.addSpacerItem(QSpacerItem(20, 20, QSizePolicy.Minimum, QSizePolicy.Expanding))
        
        version_label = QLabel(f"版本: {APP_VERSION}")
        version_label.setObjectName("versionLabel")
        version_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(version_label)
    
    def _get_stylesheet(self):
        return """
            QWidget {
                background-color: #ffffff;
                font-family: "Microsoft YaHei", "SimHei", sans-serif;
            }
            
            QLabel#title {
                font-size: 28px;
                font-weight: bold;
                color: #1a73e8;
                padding: 10px;
            }
            
            QLineEdit#inputField, QLineEdit#passwordField {
                padding: 0 15px;
                border: 2px solid #aaa;
                border-radius: 8px;
                background-color: #fafafa;
                font-size: 16px;
                color: #333;
            }
            
            QLineEdit#passwordField {
                border-top-right-radius: 0;
                border-bottom-right-radius: 0;
            }
            
            QLineEdit#inputField:focus, QLineEdit#passwordField:focus {
                border: 2px solid #1a73e8;
                background-color: white;
            }
            
            QLineEdit#inputField::placeholder, QLineEdit#passwordField::placeholder {
                color: #666;
            }
            
            QPushButton#toggleBtn {
                border: 2px solid #aaa;
                border-left: none;
                border-radius: 0 8px 8px 0;
                background-color: #f0f0f0;
                color: #333;
                font-size: 14px;
                font-weight: bold;
            }
            
            QPushButton#toggleBtn:hover {
                background-color: #e0e0e0;
            }
            
            QCheckBox#checkbox {
                color: #444;
                font-size: 14px;
            }
            
            QCheckBox#checkbox::indicator {
                width: 18px;
                height: 18px;
            }
            
            QPushButton#loginBtn {
                padding: 0;
                background-color: #1a73e8;
                color: white;
                border: none;
                border-radius: 8px;
                font-size: 18px;
                font-weight: bold;
            }
            
            QPushButton#loginBtn:hover {
                background-color: #1557b0;
            }
            
            QPushButton#loginBtn:pressed {
                background-color: #0d47a1;
            }
            
            QLabel#errorLabel {
                color: #d32f2f;
                font-size: 14px;
                font-weight: bold;
            }
            
            QLabel#versionLabel {
                color: #888;
                font-size: 12px;
            }
        """
    
    def _load_remembered_username(self):
        username = self.auth_service.get_remembered_username()
        if username:
            self.username_input.setText(username)
            self.remember_checkbox.setChecked(True)
            self.password_input.setFocus()
    
    def _toggle_password_visibility(self):
        if self.password_input.echoMode() == QLineEdit.Password:
            self.password_input.setEchoMode(QLineEdit.Normal)
            self.toggle_password_btn.setText("隐藏")
        else:
            self.password_input.setEchoMode(QLineEdit.Password)
            self.toggle_password_btn.setText("显示")
    
    def _attempt_login(self):
        username = self.username_input.text().strip()
        password = self.password_input.text()
        
        self.error_label.setText("")
        
        result = self.auth_service.login(username, password)
        
        if result.success:
            # 检查是否需要强制修改密码
            if result.must_change_password:
                # 弹出修改密码对话框
                dialog = ChangePasswordDialog(username, self.auth_service, self)
                if dialog.exec() == QDialog.Accepted:
                    # 密码修改成功，清空密码输入框，让用户重新登录
                    self.password_input.clear()
                    self.error_label.setText("密码已修改，请使用新密码重新登录")
                    self.password_input.setFocus()
                else:
                    # 用户取消修改，不允许进入系统
                    self.error_label.setText("请修改临时密码后才能使用系统")
                    self.password_input.clear()
                    self.password_input.setFocus()
                return
            
            if self.remember_checkbox.isChecked():
                self.auth_service.set_remembered_username(username)
            else:
                self.auth_service.set_remembered_username("")
            
            self.login_success.emit(result.user)
        else:
            self.error_label.setText(result.message)
            self.password_input.clear()
            self.password_input.setFocus()
