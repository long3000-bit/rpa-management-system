"""创建价格比对所需索引"""

import sqlite3
import os

db_path = 'd:/project/RPA/data/app.db'

if not os.path.exists(db_path):
    print(f"数据库文件不存在: {db_path}")
    exit(1)

print(f"连接数据库: {db_path}")
conn = sqlite3.connect(db_path)
cursor = conn.cursor()

# 索引列表
indexes = [
    ("idx_jy_product_code", "junyuan_sales_price", "商品编码"),
    ("idx_cpc_old_code", "cloud_pharmacy_catalog", "旧商品编码"),
    ("idx_cpc_medical_code", "cloud_pharmacy_catalog", "医保编码"),
    ("idx_mpl_medical_code", "medical_price_limit", "医保编码"),
    ("idx_mcw_code", "medical_catalog_western", "国家药品代码"),
    ("idx_mcc_code", "medical_catalog_chinese", "国家药品代码"),
]

print("创建索引...")
for idx_name, table, column in indexes:
    try:
        sql = f"CREATE INDEX IF NOT EXISTS {idx_name} ON {table} ({column})"
        cursor.execute(sql)
        print(f"  [OK] {idx_name} on {table}.{column}")
    except Exception as e:
        print(f"  [FAIL] {idx_name}: {e}")

conn.commit()
conn.close()
print("完成!")