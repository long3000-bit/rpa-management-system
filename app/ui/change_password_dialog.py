from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QLabel, QLineEdit, 
    QPushButton, QMessageBox
)
from PySide6.QtCore import Qt

from app.core.auth_service import AuthService


class ChangePasswordDialog(QDialog):
    
    def __init__(self, db, username: str, parent=None):
        super().__init__(parent)
        self.db = db
        self.username = username
        self.auth_service = AuthService(db)
        self._init_ui()
    
    def _init_ui(self):
        self.setWindowTitle("修改密码")
        self.setFixedSize(350, 280)
        self.setStyleSheet(self._get_stylesheet())
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(30, 30, 30, 30)
        layout.setSpacing(15)
        
        title = QLabel("修改密码")
        title.setObjectName("title")
        title.setAlignment(Qt.AlignCenter)
        layout.addWidget(title)
        
        self.old_password_input = QLineEdit()
        self.old_password_input.setPlaceholderText("当前密码")
        self.old_password_input.setEchoMode(QLineEdit.Password)
        self.old_password_input.setObjectName("inputField")
        layout.addWidget(self.old_password_input)
        
        self.new_password_input = QLineEdit()
        self.new_password_input.setPlaceholderText("新密码")
        self.new_password_input.setEchoMode(QLineEdit.Password)
        self.new_password_input.setObjectName("inputField")
        layout.addWidget(self.new_password_input)
        
        self.confirm_password_input = QLineEdit()
        self.confirm_password_input.setPlaceholderText("确认新密码")
        self.confirm_password_input.setEchoMode(QLineEdit.Password)
        self.confirm_password_input.setObjectName("inputField")
        layout.addWidget(self.confirm_password_input)
        
        self.error_label = QLabel("")
        self.error_label.setObjectName("errorLabel")
        self.error_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.error_label)
        
        btn_layout = QVBoxLayout()
        
        self.confirm_btn = QPushButton("确认修改")
        self.confirm_btn.setObjectName("confirmBtn")
        self.confirm_btn.clicked.connect(self._change_password)
        btn_layout.addWidget(self.confirm_btn)
        
        self.cancel_btn = QPushButton("取消")
        self.cancel_btn.setObjectName("cancelBtn")
        self.cancel_btn.clicked.connect(self.reject)
        btn_layout.addWidget(self.cancel_btn)
        
        layout.addLayout(btn_layout)
    
    def _get_stylesheet(self):
        return """
            QDialog {
                background-color: #f5f5f5;
            }
            
            QLabel#title {
                font-size: 18px;
                font-weight: bold;
                color: #333;
            }
            
            QLineEdit#inputField {
                padding: 10px;
                border: 1px solid #ddd;
                border-radius: 5px;
                background-color: white;
                font-size: 14px;
            }
            
            QLineEdit#inputField:focus {
                border-color: #4a90d9;
            }
            
            QLabel#errorLabel {
                color: #d32f2f;
                font-size: 12px;
            }
            
            QPushButton#confirmBtn {
                padding: 10px;
                background-color: #4a90d9;
                color: white;
                border: none;
                border-radius: 5px;
                font-size: 14px;
            }
            
            QPushButton#confirmBtn:hover {
                background-color: #357abd;
            }
            
            QPushButton#cancelBtn {
                padding: 10px;
                background-color: #95a5a6;
                color: white;
                border: none;
                border-radius: 5px;
                font-size: 14px;
            }
            
            QPushButton#cancelBtn:hover {
                background-color: #7f8c8d;
            }
        """
    
    def _change_password(self):
        old_password = self.old_password_input.text()
        new_password = self.new_password_input.text()
        confirm_password = self.confirm_password_input.text()
        
        self.error_label.setText("")
        
        if not old_password:
            self.error_label.setText("请输入当前密码")
            return
        
        if not new_password:
            self.error_label.setText("请输入新密码")
            return
        
        if new_password != confirm_password:
            self.error_label.setText("两次输入的新密码不一致")
            return
        
        success, message = self.auth_service.change_password(
            self.username, old_password, new_password
        )
        
        if success:
            QMessageBox.information(self, "成功", "密码修改成功")
            self.accept()
        else:
            self.error_label.setText(message)
