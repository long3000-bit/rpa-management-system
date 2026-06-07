from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel
from PySide6.QtCore import Qt


class HomePage(QWidget):
    
    def __init__(self):
        super().__init__()
        self._init_ui()
    
    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignCenter)
        
        welcome = QLabel("欢迎使用RPA管理系统")
        welcome.setStyleSheet("font-size: 24px; color: #333;")
        layout.addWidget(welcome)
        
        hint = QLabel("请从左侧菜单选择功能模块")
        hint.setStyleSheet("font-size: 14px; color: #666; margin-top: 20px;")
        layout.addWidget(hint)
