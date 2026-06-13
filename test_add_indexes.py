"""检查和添加数据库索引"""

import sys
sys.path.insert(0, 'd:/project/RPA')

from app.storage.database import Database

db = Database()
conn = db.get_connection()
cursor = conn.cursor()

print("=" * 60)
print("检查现有索引")
print("=" * 60)

# 检查各表的索引
tables = [
    'cloud_pharmacy_catalog',
    'junyuan_sales_price',
    'medical_price_limit',
    'medical_catalog_western',
    'medical_catalog_chinese'
]

for table in tables:
    cursor.execute(f"PRAGMA index_list({table})")
    indexes = cursor.fetchall()
    print(f"\n{table} 表索引:")
    if indexes:
        for idx in indexes:
            cursor.execute(f"PRAGMA index_info({idx['name']})")
            columns = cursor.fetchall()
            print(f"  {idx['name']}: {[c['name'] for c in columns]}")
    else:
        print("  无索引")

print("\n" + "=" * 60)
print("添加必要的索引")
print("=" * 60)

# 添加索引
indexes_to_add = [
    # cloud_pharmacy_catalog 表索引
    ("idx_cloud_pharmacy_catalog_batch_id", "cloud_pharmacy_catalog", "batch_id"),
    ("idx_cloud_pharmacy_catalog_medical_code", "cloud_pharmacy_catalog", "医保编码"),
    ("idx_cloud_pharmacy_catalog_old_code", "cloud_pharmacy_catalog", "旧商品编码"),
    
    # junyuan_sales_price 表索引
    ("idx_junyuan_sales_price_batch_id", "junyuan_sales_price", "batch_id"),
    ("idx_junyuan_sales_price_code", "junyuan_sales_price", "商品编码"),
    
    # medical_price_limit 表索引
    ("idx_medical_price_limit_batch_id", "medical_price_limit", "batch_id"),
    ("idx_medical_price_limit_medical_code", "medical_price_limit", "医保编码"),
    
    # medical_catalog_western 表索引
    ("idx_medical_catalog_western_batch_id", "medical_catalog_western", "batch_id"),
    ("idx_medical_catalog_western_code", "medical_catalog_western", "国家药品代码"),
    
    # medical_catalog_chinese 表索引
    ("idx_medical_catalog_chinese_batch_id", "medical_catalog_chinese", "batch_id"),
    ("idx_medical_catalog_chinese_code", "medical_catalog_chinese", "国家药品代码"),
]

for idx_name, table, column in indexes_to_add:
    try:
        cursor.execute(f"CREATE INDEX IF NOT EXISTS {idx_name} ON {table} ({column})")
        print(f"  ✓ 创建索引 {idx_name} on {table}.{column}")
    except Exception as e:
        print(f"  ✗ 创建索引失败 {idx_name}: {e}")

conn.commit()

print("\n索引创建完成！")