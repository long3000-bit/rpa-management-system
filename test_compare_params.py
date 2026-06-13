"""测试价格比对参数"""

import logging
logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')

import sys
sys.path.insert(0, 'd:/project/RPA')

from app.storage.database import Database
from app.core.medical_price_compare_service import MedicalPriceCompareService

db = Database()

# 检查批次数据
conn = db.get_connection()
cursor = conn.cursor()

print("=" * 60)
print("检查批次数据")
print("=" * 60)

cursor.execute('''
    SELECT batch_type, batch_id, file_name, import_status 
    FROM medical_import_batches 
    ORDER BY created_at DESC
''')
batches = cursor.fetchall()

for batch in batches:
    print(f"{batch['batch_type']}: {batch['batch_id']} - {batch['file_name']} ({batch['import_status']})")

print("\n" + "=" * 60)
print("测试比对服务")
print("=" * 60)

# 测试比对服务
compare_service = MedicalPriceCompareService(db)

# 获取最新批次
cursor.execute('''
    SELECT batch_id FROM medical_import_batches
    WHERE batch_type = 'medical_price_limit' AND import_status = 'success'
    ORDER BY created_at DESC LIMIT 1
''')
row = cursor.fetchone()
medical_price_limit_batch = row['batch_id'] if row else None
print(f"medical_price_limit_batch: {medical_price_limit_batch} (type: {type(medical_price_limit_batch)})")

cursor.execute('''
    SELECT batch_id FROM medical_import_batches
    WHERE batch_type = 'cloud_pharmacy_catalog' AND import_status = 'success'
    ORDER BY created_at DESC LIMIT 1
''')
row = cursor.fetchone()
cloud_pharmacy_batch = row['batch_id'] if row else None
print(f"cloud_pharmacy_batch: {cloud_pharmacy_batch} (type: {type(cloud_pharmacy_batch)})")

cursor.execute('''
    SELECT batch_id FROM medical_import_batches
    WHERE batch_type = 'junyuan_sales_price' AND import_status = 'success'
    ORDER BY created_at DESC LIMIT 1
''')
row = cursor.fetchone()
junyuan_price_batch = row['batch_id'] if row else None
print(f"junyuan_price_batch: {junyuan_price_batch} (type: {type(junyuan_price_batch)})")

cursor.execute('''
    SELECT batch_id FROM medical_import_batches
    WHERE batch_type IN ('medical_catalog_western', 'medical_catalog_chinese')
    AND import_status = 'success'
    ORDER BY created_at DESC
''')
rows = cursor.fetchall()
medical_catalog_batches = [row['batch_id'] for row in rows]
print(f"medical_catalog_batches: {medical_catalog_batches} (type: {type(medical_catalog_batches)})")

# 检查批次类型
for batch in medical_catalog_batches:
    cursor.execute('SELECT batch_type FROM medical_import_batches WHERE batch_id = ?', (batch,))
    row = cursor.fetchone()
    print(f"  batch {batch}: type = {row['batch_type'] if row else 'NOT FOUND'}")

print("\n" + "=" * 60)
print("检查数据关联")
print("=" * 60)

# 检查君元销售价格数据
cursor.execute('SELECT COUNT(*) as cnt FROM junyuan_sales_price WHERE batch_id = ?', (junyuan_price_batch,))
row = cursor.fetchone()
print(f"君元销售价格数据: {row['cnt']} 条")

# 检查云药店商品目录数据
cursor.execute('SELECT COUNT(*) as cnt FROM cloud_pharmacy_catalog WHERE batch_id = ?', (cloud_pharmacy_batch,))
row = cursor.fetchone()
print(f"云药店商品目录数据: {row['cnt']} 条")

# 检查三同口径数据
cursor.execute('SELECT COUNT(*) as cnt FROM medical_price_limit WHERE batch_id = ?', (medical_price_limit_batch,))
row = cursor.fetchone()
print(f"三同口径数据: {row['cnt']} 条")

# 检查西药目录数据
for batch in medical_catalog_batches:
    cursor.execute('SELECT COUNT(*) as cnt FROM medical_catalog_western WHERE batch_id = ?', (batch,))
    row = cursor.fetchone()
    print(f"西药目录数据 (batch={batch}): {row['cnt']} 条")

# 检查中成药目录数据
for batch in medical_catalog_batches:
    cursor.execute('SELECT COUNT(*) as cnt FROM medical_catalog_chinese WHERE batch_id = ?', (batch,))
    row = cursor.fetchone()
    print(f"中成药目录数据 (batch={batch}): {row['cnt']} 条")

# 检查君元销售价格是否有旧商品编码
cursor.execute('SELECT COUNT(*) as cnt FROM junyuan_sales_price WHERE batch_id = ? AND 商品编码 IS NOT NULL AND 商品编码 != ""', (junyuan_price_batch,))
row = cursor.fetchone()
print(f"君元销售价格有商品编码: {row['cnt']} 条")

# 检查云药店商品目录是否有旧商品编码
cursor.execute('SELECT COUNT(*) as cnt FROM cloud_pharmacy_catalog WHERE batch_id = ? AND 旧商品编码 IS NOT NULL AND 旧商品编码 != ""', (cloud_pharmacy_batch,))
row = cursor.fetchone()
print(f"云药店商品目录有旧商品编码: {row['cnt']} 条")

# 检查关联情况
cursor.execute('''
    SELECT COUNT(*) as cnt
    FROM junyuan_sales_price jy
    LEFT JOIN cloud_pharmacy_catalog cpc 
        ON jy.商品编码 = cpc.旧商品编码 AND cpc.batch_id = ?
    WHERE jy.batch_id = ? AND cpc.商品编码 IS NOT NULL
''', (cloud_pharmacy_batch, junyuan_price_batch))
row = cursor.fetchone()
print(f"君元价格关联云药店目录: {row['cnt']} 条")

print("\n" + "=" * 60)
print("直接测试SQL查询")
print("=" * 60)

# 构建SQL查询
western_batches = ['MED_20260612153442_d06fe3ad']  # 西药
chinese_batches = ['MED_20260612153847_ce462bf9']  # 中成药

western_placeholders = ','.join(['?' for _ in western_batches])
chinese_placeholders = ','.join(['?' for _ in chinese_batches])

query = f'''
    SELECT 
        cpc.商品编码,
        cpc.旧商品编码,
        cpc.商品名称,
        cpc.规格,
        cpc.生产厂家,
        cpc.医保编码,
        jy.销售价,
        jy.包装价,
        jy.单片价,
        mpl.三同药品参比价 as 医保价格上限,
        COALESCE(
            NULLIF(mcw.医保支付标准, ''),
            NULLIF(mcw.省集中采购上限价含企业承诺价, ''),
            NULLIF(mcw.政府定价元, '')
        ) as 医保基础价格,
        COALESCE(
            NULLIF(mcc.医保支付标准, ''),
            NULLIF(mcc.省集中采购上限价含企业承诺价, ''),
            NULLIF(mcc.政府定价元, '')
        ) as 医保基础价格_中成药
    FROM junyuan_sales_price jy
    LEFT JOIN cloud_pharmacy_catalog cpc 
        ON jy.商品编码 = cpc.旧商品编码 AND cpc.batch_id = ?
    LEFT JOIN medical_price_limit mpl 
        ON cpc.医保编码 = mpl.医保编码 AND mpl.batch_id = ?
    LEFT JOIN medical_catalog_western mcw 
        ON cpc.医保编码 = mcw.国家药品代码 AND mcw.batch_id IN ({western_placeholders})
    LEFT JOIN medical_catalog_chinese mcc 
        ON cpc.医保编码 = mcc.国家药品代码 AND mcc.batch_id IN ({chinese_placeholders})
    WHERE jy.batch_id = ?
'''

params = [
    cloud_pharmacy_batch,
    medical_price_limit_batch,
]
params.extend(western_batches)
params.extend(chinese_batches)
params.append(junyuan_price_batch)

print(f"SQL参数: {params}")

cursor.execute(query, params)
rows = cursor.fetchall()
print(f"SQL查询结果: {len(rows)} 条")

if rows:
    print("前5条数据:")
    for i, row in enumerate(rows[:5]):
        print(f"  {i+1}. 商品编码={row['商品编码']}, 医保编码={row['医保编码']}, 销售价={row['销售价']}")

print("\n" + "=" * 60)
print("清理测试数据")
print("=" * 60)

# 检查现有比对批次
cursor.execute('SELECT batch_id FROM medical_compare_batches ORDER BY created_at DESC LIMIT 5')
rows = cursor.fetchall()
print(f"现有比对批次: {[row['batch_id'] for row in rows]}")

# 删除之前的测试比对结果
cursor.execute('DELETE FROM medical_price_compare_result')
cursor.execute('DELETE FROM medical_compare_batches')
conn.commit()
conn.close()  # 关闭连接，让比对服务使用新连接
print("已清理所有比对数据并关闭连接")

print("\n" + "=" * 60)
print("执行比对（带详细日志）")
print("=" * 60)

# 重新创建数据库连接
db2 = Database()
compare_service2 = MedicalPriceCompareService(db2)

try:
    result = compare_service2.run_compare(
        medical_catalog_batch=medical_catalog_batches,
        medical_price_limit_batch=medical_price_limit_batch,
        cloud_pharmacy_batch=cloud_pharmacy_batch,
        junyuan_price_batch=junyuan_price_batch,
        compare_by="test"
    )
    print(f"比对结果: {result.compare_status}")
    print(f"错误信息: {result.error_message}")
    print(f"总数: {result.total_count}")
    print(f"正常: {result.normal_count}")
    print(f"异常: {result.abnormal_count}")
    print(f"严重异常: {result.severe_count}")
except Exception as e:
    print(f"比对失败: {e}")
    import traceback
    traceback.print_exc()