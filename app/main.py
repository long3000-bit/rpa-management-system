import sys
import logging
from pathlib import Path
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.config import APP_NAME, LOG_FILE, LOGS_DIR
from app.storage.database import Database
from app.ui.login_window import LoginWindow
from app.ui.main_window import MainWindow


def setup_logging():
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler(LOG_FILE, encoding='utf-8'),
            logging.StreamHandler()
        ]
    )


def main():
    setup_logging()
    logging.info(f"启动 {APP_NAME}")
    
    db = Database()
    db.initialize()
    
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    
    main_window = None
    
    def on_login_success(user):
        nonlocal main_window
        login_window.hide()
        main_window = MainWindow(db, user)
        main_window.show()
    
    login_window = LoginWindow(db)
    login_window.login_success.connect(on_login_success)
    login_window.show()
    
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
