import os
from pathlib import Path

APP_NAME = "RPA管理系统"
APP_VERSION = "1.0.0"

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
LOGS_DIR = BASE_DIR / "logs"

DATA_DIR.mkdir(parents=True, exist_ok=True)
LOGS_DIR.mkdir(parents=True, exist_ok=True)

DATABASE_PATH = DATA_DIR / "app.db"
LOG_FILE = LOGS_DIR / "app.log"

DEFAULT_ADMIN_USERNAME = "admin"
DEFAULT_ADMIN_PASSWORD = "admin123"

PASSWORD_MIN_LENGTH = 6
HASH_ITERATIONS = 100000
