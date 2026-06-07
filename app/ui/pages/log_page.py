from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel
from PySide6.QtCore import Qt


class LogPage(QWidget):
    
    def __init__(self):
        super().__init__()
        self._init_ui()
    
    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignCenter)
        
        label = QLabel("日志与截图")
        label.setStyleSheet("font-size: 20px; color: #333;")
        layout.addWidget(label)
        
        hint = QLabel("功能开发中...")
        hint.setStyleSheet("font-size: 14px; color: #999; margin-top: 10px;")
        layout.addWidget(hint)
