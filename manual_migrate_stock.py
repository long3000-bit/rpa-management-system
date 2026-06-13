"""
手动执行数据库迁移：为junyuan_sales_price表添加库存数量字段
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
    
    # 检查表结构
    cursor.execute("PRAGMA table_info(junyuan_sales_price)")
    columns = [row['name'] for row in cursor.fetchall()]
    
    logging.info(f"junyuan_sales_price表当前字段: {columns}")
    
    # 添加库存数量字段（如果不存在）
    if '库存数量' not in columns:
        cursor.execute("ALTER TABLE junyuan_sales_price ADD COLUMN 库存数量 TEXT")
        logging.info("✓ 已为 junyuan_sales_price 表添加 库存数量 字段")
    else:
        logging.info("✓ junyuan_sales_price 表已存在 库存数量 字段")
    
    # 检查medical_price_compare_result表
    cursor.execute("PRAGMA table_info(medical_price_compare_result)")
    medical_columns = [row['name'] for row in cursor.fetchall()]
    
    logging.info(f"medical_price_compare_result表当前字段: {medical_columns}")
    
    # 添加君元库存数量字段（如果不存在）
    if '君元库存数量' not in medical_columns:
        cursor.execute("ALTER TABLE medical_price_compare_result ADD COLUMN 君元库存数量 TEXT")
        logging.info("✓ 已为 medical_price_compare_result 表添加 君元库存数量 字段")
    else:
        logging.info("✓ medical_price_compare_result 表已存在 君元库存数量 字段")
    
    # 提交更改
    conn.commit()
    logging.info("✓ 数据库迁移成功完成")
    
    # 验证结果
    cursor.execute("PRAGMA table_info(junyuan_sales_price)")
    new_columns = [row['name'] for row in cursor.fetchall()]
    logging.info(f"迁移后 junyuan_sales_price 表字段: {new_columns}")
    
    cursor.execute("PRAGMA table_info(medical_price_compare_result)")
    new_medical_columns = [row['name'] for row in cursor.fetchall()]
    logging.info(f"迁移后 medical_price_compare_result 表字段: {new_medical_columns}")
    
except Exception as e:
    logging.error(f"数据库迁移失败: {e}")
    conn.rollback()
finally:
    conn.close()
    logging.info("数据库连接已关闭")