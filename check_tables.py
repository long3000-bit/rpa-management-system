"""
检查数据库中的所有表
"""
import sqlite3
import logging

# 配置日志
logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')

# 数据库路径
db_path = 'data/rpa.db'

try:
    # 连接数据库
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # 查询所有表
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
    tables = [row['name'] for row in cursor.fetchall()]
    
    logging.info(f"数据库中的所有表: {tables}")
    
    # 检查每个表的结构
    for table in tables:
        cursor.execute(f"PRAGMA table_info({table})")
        columns = [row['name'] for row in cursor.fetchall()]
        logging.info(f"\n{table} 表字段: {columns}")
    
except Exception as e:
    logging.error(f"查询失败: {e}")
finally:
    conn.close()
    logging.info("\n数据库连接已关闭")