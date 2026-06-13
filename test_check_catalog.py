"""检查 medical_catalog_western 表结构"""

import sys
sys.path.insert(0, 'd:/project/RPA')

from app.storage.database import Database

db = Database()
conn = db.get_connection()
cursor = conn.cursor()

print("=" * 60)
print("检查 medical_catalog_western 表结构")
print("=" * 60)

cursor.execute("PRAGMA table_info(medical_catalog_western)")
columns = cursor.fetchall()
print("表列名:")
for col in columns:
    print(f"  {col['name']} ({col['type']})")

print("\n" + "=" * 60)
print("检查 medical_catalog_chinese 表结构")
print("=" * 60)

cursor.execute("PRAGMA table_info(medical_catalog_chinese)")
columns = cursor.fetchall()
print("表列名:")
for col in columns:
    print(f"  {col['name']} ({col['type']})")

print("\n" + "=" * 60)
print("检查数据示例")
print("=" * 60)

cursor.execute("SELECT * FROM medical_catalog_western LIMIT 2")
rows = cursor.fetchall()
print("\n西药目录示例:")
for row in rows:
    print(f"\n行数据:")
    for key, value in dict(row).items():
        if value:
            print(f"  {key}: {value}")

cursor.execute("SELECT * FROM medical_catalog_chinese LIMIT 2")
rows = cursor.fetchall()
print("\n中成药目录示例:")
for row in rows:
    print(f"\n行数据:")
    for key, value in dict(row).items():
        if value:
            print(f"  {key}: {value}")