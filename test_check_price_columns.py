"""检查医保目录表的价格列"""

import sys
sys.path.insert(0, 'd:/project/RPA')

from app.storage.database import Database

db = Database()
conn = db.get_connection()
cursor = conn.cursor()

print("=" * 60)
print("检查西药目录价格列")
print("=" * 60)

cursor.execute("PRAGMA table_info(medical_catalog_western)")
columns = cursor.fetchall()
print("表列名:")
for col in columns:
    if '价' in col['name'] or '标准' in col['name']:
        print(f"  {col['name']} ({col['type']})")

print("\n" + "=" * 60)
print("检查中成药目录价格列")
print("=" * 60)

cursor.execute("PRAGMA table_info(medical_catalog_chinese)")
columns = cursor.fetchall()
print("表列名:")
for col in columns:
    if '价' in col['name'] or '标准' in col['name']:
        print(f"  {col['name']} ({col['type']})")

print("\n" + "=" * 60)
print("检查西药目录价格数据示例")
print("=" * 60)

cursor.execute("""
    SELECT 医保药品名称, 医保支付标准, 省集中采购上限价含企业承诺价, 政府定价元
    FROM medical_catalog_western 
    WHERE 医保支付标准 IS NOT NULL AND 医保支付标准 != ''
    LIMIT 5
""")
rows = cursor.fetchall()
print("有医保支付标准的记录:")
for row in rows:
    print(f"  {row['医保药品名称']}: 医保支付标准={row['医保支付标准']}, 省集中采购上限价={row['省集中采购上限价含企业承诺价']}, 政府定价={row['政府定价元']}")

cursor.execute("""
    SELECT 医保药品名称, 医保支付标准, 省集中采购上限价含企业承诺价, 政府定价元
    FROM medical_catalog_western 
    WHERE (医保支付标准 IS NULL OR 医保支付标准 = '') 
      AND 省集中采购上限价含企业承诺价 IS NOT NULL AND 省集中采购上限价含企业承诺价 != ''
    LIMIT 5
""")
rows = cursor.fetchall()
print("\n有省集中采购上限价的记录:")
for row in rows:
    print(f"  {row['医保药品名称']}: 医保支付标准={row['医保支付标准']}, 省集中采购上限价={row['省集中采购上限价含企业承诺价']}, 政府定价={row['政府定价元']}")

cursor.execute("""
    SELECT 医保药品名称, 医保支付标准, 省集中采购上限价含企业承诺价, 政府定价元
    FROM medical_catalog_western 
    WHERE (医保支付标准 IS NULL OR 医保支付标准 = '') 
      AND (省集中采购上限价含企业承诺价 IS NULL OR 省集中采购上限价含企业承诺价 = '')
      AND 政府定价元 IS NOT NULL AND 政府定价元 != ''
    LIMIT 5
""")
rows = cursor.fetchall()
print("\n只有政府定价的记录:")
for row in rows:
    print(f"  {row['医保药品名称']}: 医保支付标准={row['医保支付标准']}, 省集中采购上限价={row['省集中采购上限价含企业承诺价']}, 政府定价={row['政府定价元']}")