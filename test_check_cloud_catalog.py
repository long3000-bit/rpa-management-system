"""检查 cloud_pharmacy_catalog 表结构和数据"""

import sys
sys.path.insert(0, 'd:/project/RPA')

from app.storage.database import Database

db = Database()
conn = db.get_connection()
cursor = conn.cursor()

print("=" * 60)
print("检查 cloud_pharmacy_catalog 表结构")
print("=" * 60)

cursor.execute("PRAGMA table_info(cloud_pharmacy_catalog)")
columns = cursor.fetchall()
print("表列名:")
for col in columns:
    print(f"  {col['name']} ({col['type']})")

print("\n" + "=" * 60)
print("检查数据示例")
print("=" * 60)

cursor.execute("SELECT * FROM cloud_pharmacy_catalog LIMIT 3")
rows = cursor.fetchall()
for row in rows:
    print(f"\n行数据:")
    for key, value in dict(row).items():
        if value:
            print(f"  {key}: {value}")

print("\n" + "=" * 60)
print("检查是否有医保编码字段")
print("=" * 60)

cursor.execute("""
    SELECT 商品编码, 商品名称, 旧商品编码, 医保编码
    FROM cloud_pharmacy_catalog 
    LIMIT 5
""")
rows = cursor.fetchall()
print("商品目录数据:")
for row in rows:
    print(f"  商品编码: {row['商品编码']}, 商品名称: {row['商品名称']}, 旧商品编码: {row['旧商品编码']}, 医保编码: {row['医保编码']}")