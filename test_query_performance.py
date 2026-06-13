"""测试SQL查询性能"""

import sys
sys.path.insert(0, 'd:/project/RPA')

import time
from app.storage.database import Database

db = Database()
conn = db.get_connection()
cursor = conn.cursor()

print("=" * 60)
print("获取批次ID")
print("=" * 60)

# 获取批次ID
cursor.execute('''
    SELECT batch_id FROM medical_import_batches
    WHERE batch_type IN ('medical_catalog_western', 'medical_catalog_chinese')
    AND import_status = 'success'
    ORDER BY created_at DESC
''')
rows = cursor.fetchall()
medical_catalog_batches = [row['batch_id'] for row in rows]
print(f"医保目录批次: {medical_catalog_batches}")

cursor.execute('''
    SELECT batch_id FROM medical_import_batches
    WHERE batch_type = 'medical_price_limit' AND import_status = 'success'
    ORDER BY created_at DESC LIMIT 1
''')
row = cursor.fetchone()
medical_price_limit_batch = row['batch_id'] if row else None
print(f"三同口径批次: {medical_price_limit_batch}")

cursor.execute('''
    SELECT batch_id FROM medical_import_batches
    WHERE batch_type = 'cloud_pharmacy_catalog' AND import_status = 'success'
    ORDER BY created_at DESC LIMIT 1
''')
row = cursor.fetchone()
cloud_pharmacy_batch = row['batch_id'] if row else None
print(f"云药店商品目录批次: {cloud_pharmacy_batch}")

cursor.execute('''
    SELECT batch_id FROM medical_import_batches
    WHERE batch_type = 'junyuan_sales_price' AND import_status = 'success'
    ORDER BY created_at DESC LIMIT 1
''')
row = cursor.fetchone()
junyuan_price_batch = row['batch_id'] if row else None
print(f"君元销售价格批次: {junyuan_price_batch}")

# 分离西药和中成药批次
western_batches = []
chinese_batches = []

for batch_id in medical_catalog_batches:
    cursor.execute('''
        SELECT batch_type FROM medical_import_batches WHERE batch_id = ?
    ''', (batch_id,))
    row = cursor.fetchone()
    if row:
        if row['batch_type'] == 'medical_catalog_western':
            western_batches.append(batch_id)
        elif row['batch_type'] == 'medical_catalog_chinese':
            chinese_batches.append(batch_id)

print(f"西药批次: {western_batches}")
print(f"中成药批次: {chinese_batches}")

# 构建批次IN条件
western_placeholders = ','.join(['?' for _ in western_batches])
chinese_placeholders = ','.join(['?' for _ in chinese_batches])

print("\n" + "=" * 60)
print("执行关联查询")
print("=" * 60)

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
    FROM cloud_pharmacy_catalog cpc
    LEFT JOIN junyuan_sales_price jy 
        ON cpc.旧商品编码 = jy.商品编码 AND jy.batch_id = ?
    LEFT JOIN medical_price_limit mpl 
        ON cpc.医保编码 = mpl.医保编码 AND mpl.batch_id = ?
    LEFT JOIN medical_catalog_western mcw 
        ON cpc.医保编码 = mcw.国家药品代码 AND mcw.batch_id IN ({western_placeholders})
    LEFT JOIN medical_catalog_chinese mcc 
        ON cpc.医保编码 = mcc.国家药品代码 AND mcc.batch_id IN ({chinese_placeholders})
    WHERE cpc.batch_id = ?
'''

params = [
    junyuan_price_batch,
    medical_price_limit_batch,
]
params.extend(western_batches)
params.extend(chinese_batches)
params.append(cloud_pharmacy_batch)

print(f"查询参数: {params}")

start_time = time.time()
cursor.execute(query, params)
linked_data = cursor.fetchall()
end_time = time.time()

print(f"查询耗时: {end_time - start_time:.2f}秒")
print(f"返回数据量: {len(linked_data)}")

# 检查数据分布
normal_count = 0
abnormal_count = 0
severe_count = 0
missing_price_count = 0
missing_code_count = 0
pending_count = 0

for row in linked_data:
    medical_code = row.get('医保编码', '')
    base_price = row.get('医保基础价格') or row.get('医保基础价格_中成药')
    limit_price = row.get('医保价格上限')
    sales_price = row.get('销售价')
    
    if not medical_code:
        missing_code_count += 1
    elif not base_price or not limit_price:
        missing_price_count += 1
    elif not sales_price:
        pending_count += 1
    elif sales_price and base_price and limit_price:
        try:
            sp = float(sales_price)
            bp = float(base_price) if base_price else None
            lp = float(limit_price) if limit_price else None
            
            if sp > lp:
                severe_count += 1
            elif sp > bp:
                abnormal_count += 1
            else:
                normal_count += 1
        except:
            pending_count += 1
    else:
        pending_count += 1

print(f"\n数据分布:")
print(f"  正常: {normal_count}")
print(f"  异常: {abnormal_count}")
print(f"  严重异常: {severe_count}")
print(f"  待补价格: {missing_price_count}")
print(f"  待补编码: {missing_code_count}")
print(f"  待确认: {pending_count}")
print(f"  总数: {len(linked_data)}")