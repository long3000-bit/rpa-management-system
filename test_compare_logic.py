"""测试价格比对逻辑"""

import sys
sys.path.insert(0, 'd:/project/RPA')

from app.storage.database import Database
from app.core.medical_price_compare_service import MedicalPriceCompareService

db = Database()
conn = db.get_connection()
cursor = conn.cursor()

print("=" * 60)
print("检查各数据源批次")
print("=" * 60)

# 检查西药目录批次
cursor.execute("""
    SELECT batch_id, file_name, total_rows, success_rows, import_status
    FROM medical_import_batches
    WHERE batch_type = 'medical_catalog_western' AND import_status = 'success'
    ORDER BY created_at DESC LIMIT 1
""")
western = cursor.fetchone()
print(f"西药目录批次: {western['batch_id'] if western else '无'}, 总行数: {western['total_rows'] if western else 0}")

# 检查中成药目录批次
cursor.execute("""
    SELECT batch_id, file_name, total_rows, success_rows, import_status
    FROM medical_import_batches
    WHERE batch_type = 'medical_catalog_chinese' AND import_status = 'success'
    ORDER BY created_at DESC LIMIT 1
""")
chinese = cursor.fetchone()
print(f"中成药目录批次: {chinese['batch_id'] if chinese else '无'}, 总行数: {chinese['total_rows'] if chinese else 0}")

# 检查三同口径批次
cursor.execute("""
    SELECT batch_id, file_name, total_rows, success_rows, import_status
    FROM medical_import_batches
    WHERE batch_type = 'medical_price_limit' AND import_status = 'success'
    ORDER BY created_at DESC LIMIT 1
""")
price_limit = cursor.fetchone()
print(f"三同口径批次: {price_limit['batch_id'] if price_limit else '无'}, 总行数: {price_limit['total_rows'] if price_limit else 0}")

# 检查云药店商品目录批次
cursor.execute("""
    SELECT batch_id, file_name, total_rows, success_rows, import_status
    FROM medical_import_batches
    WHERE batch_type = 'cloud_pharmacy_catalog' AND import_status = 'success'
    ORDER BY created_at DESC LIMIT 1
""")
cloud = cursor.fetchone()
print(f"云药店商品目录批次: {cloud['batch_id'] if cloud else '无'}, 总行数: {cloud['total_rows'] if cloud else 0}")

# 检查君元销售价格批次
cursor.execute("""
    SELECT batch_id, file_name, total_rows, success_rows, import_status
    FROM medical_import_batches
    WHERE batch_type = 'junyuan_sales_price' AND import_status = 'success'
    ORDER BY created_at DESC LIMIT 1
""")
junyuan = cursor.fetchone()
print(f"君元销售价格批次: {junyuan['batch_id'] if junyuan else '无'}, 总行数: {junyuan['total_rows'] if junyuan else 0}")

print("\n" + "=" * 60)
print("检查数据关联情况")
print("=" * 60)

# 检查云药店商品目录是否有医保编码
cursor.execute("""
    SELECT COUNT(*) as total,
           SUM(CASE WHEN 医保编码 IS NOT NULL AND 医保编码 != '' THEN 1 ELSE 0 END) as has_medical_code
    FROM cloud_pharmacy_catalog
""")
cloud_stats = cursor.fetchone()
print(f"云药店商品目录: 总数 {cloud_stats['total']}, 有医保编码 {cloud_stats['has_medical_code']}")

# 检查云药店商品目录是否有旧商品编码
cursor.execute("""
    SELECT COUNT(*) as total,
           SUM(CASE WHEN 旧商品编码 IS NOT NULL AND 旧商品编码 != '' THEN 1 ELSE 0 END) as has_old_code
    FROM cloud_pharmacy_catalog
""")
cloud_old_stats = cursor.fetchone()
print(f"云药店商品目录: 总数 {cloud_old_stats['total']}, 有旧商品编码 {cloud_old_stats['has_old_code']}")

# 检查君元销售价格是否有商品编码
cursor.execute("""
    SELECT COUNT(*) as total,
           SUM(CASE WHEN 商品编码 IS NOT NULL AND 商品编码 != '' THEN 1 ELSE 0 END) as has_code
    FROM junyuan_sales_price
""")
jy_stats = cursor.fetchone()
print(f"君元销售价格: 总数 {jy_stats['total']}, 有商品编码 {jy_stats['has_code']}")

# 检查西药目录是否有国家药品代码
cursor.execute("""
    SELECT COUNT(*) as total,
           SUM(CASE WHEN 国家药品代码 IS NOT NULL AND 国家药品代码 != '' THEN 1 ELSE 0 END) as has_code
    FROM medical_catalog_western
""")
western_stats = cursor.fetchone()
print(f"西药目录: 总数 {western_stats['total']}, 有国家药品代码 {western_stats['has_code']}")

# 检查三同口径是否有医保编码
cursor.execute("""
    SELECT COUNT(*) as total,
           SUM(CASE WHEN 医保编码 IS NOT NULL AND 医保编码 != '' THEN 1 ELSE 0 END) as has_code
    FROM medical_price_limit
""")
limit_stats = cursor.fetchone()
print(f"三同口径: 总数 {limit_stats['total']}, 有医保编码 {limit_stats['has_code']}")

print("\n" + "=" * 60)
print("测试关联查询")
print("=" * 60)

# 测试关联查询
if western and cloud and price_limit:
    medical_batch_placeholders = '?'
    
    query = f'''
        SELECT 
            cpc.商品编码,
            cpc.旧商品编码,
            cpc.商品名称,
            cpc.医保编码,
            jy.销售价,
            mpl.三同药品参比价 as 医保价格上限,
            COALESCE(
                NULLIF(mcw.医保支付标准, ''),
                NULLIF(mcw.省集中采购上限价含企业承诺价, ''),
                NULLIF(mcw.政府定价元, '')
            ) as 医保基础价格
        FROM cloud_pharmacy_catalog cpc
        LEFT JOIN junyuan_sales_price jy 
            ON cpc.旧商品编码 = jy.商品编码 AND jy.batch_id = ?
        LEFT JOIN medical_price_limit mpl 
            ON cpc.医保编码 = mpl.医保编码 AND mpl.batch_id = ?
        LEFT JOIN medical_catalog_western mcw 
            ON cpc.医保编码 = mcw.国家药品代码 AND mcw.batch_id IN ({medical_batch_placeholders})
        WHERE cpc.batch_id = ?
        LIMIT 10
    '''
    
    params = [
        junyuan['batch_id'] if junyuan else None,
        price_limit['batch_id'],
        western['batch_id'],
        cloud['batch_id']
    ]
    
    print(f"查询参数: {params}")
    
    cursor.execute(query, params)
    results = cursor.fetchall()
    
    print(f"关联查询结果数量: {len(results)}")
    
    for row in results:
        print(f"\n商品: {row['商品名称']}")
        print(f"  商品编码: {row['商品编码']}")
        print(f"  旧商品编码: {row['旧商品编码']}")
        print(f"  医保编码: {row['医保编码']}")
        print(f"  销售价: {row['销售价']}")
        print(f"  医保价格上限: {row['医保价格上限']}")
        print(f"  医保基础价格: {row['医保基础价格']}")