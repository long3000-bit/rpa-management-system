"""测试医保价格上限导入功能"""

from app.storage.database import Database
from app.core.medical_price_import_service import MedicalPriceImportService
import logging

# 设置详细日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# 初始化数据库和服务
db = Database()
import_service = MedicalPriceImportService(db)

# 删除旧数据
conn = db.get_connection()
cursor = conn.cursor()
cursor.execute("DELETE FROM medical_price_limit")
cursor.execute("DELETE FROM medical_import_batches WHERE batch_type = 'medical_price_limit'")
conn.commit()
print("旧数据已删除")

# 导入数据
file_path = "D:/project/RPA/20260604三同口径目录(1).xlsx"
print(f"\n导入文件: {file_path}")

result = import_service.import_medical_price_limit(file_path)

print(f"\n导入结果:")
print(f"  批次ID: {result.batch_id}")
print(f"  文件名: {result.file_name}")
print(f"  工作表: {result.sheet_name}")
print(f"  总行数: {result.total_rows}")
print(f"  成功行数: {result.success_rows}")
print(f"  失败行数: {result.failed_rows}")
print(f"  导入状态: {result.import_status}")

if result.error_message:
    print(f"  错误信息: {result.error_message}")

if result.failures:
    print(f"\n失败详情（前5条）:")
    for failure in result.failures[:5]:
        print(f"  行 {failure['row_index']}: {failure['failure_reason']}")

# 检查导入后的数据
cursor.execute("SELECT COUNT(*) as count FROM medical_price_limit")
count = cursor.fetchone()
print(f"\n数据库中的数据总数: {count['count']}")

if count['count'] > 0:
    cursor.execute("""
        SELECT 医保编码, 药品名称, 企业名称, 规格, 医保价格上限
        FROM medical_price_limit 
        LIMIT 10
    """)
    rows = cursor.fetchall()
    print(f"\n前10条数据:")
    for i, row in enumerate(rows, 1):
        print(f"{i}. 医保编码: {row['医保编码']}")
        print(f"   药品名称: {row['药品名称']}")
        print(f"   企业名称: {row['企业名称']}")
        print(f"   规格: {row['规格']}")
        print(f"   医保价格上限: {row['医保价格上限']}")
        print()
    
    # 检查数据质量
    cursor.execute("SELECT COUNT(*) as count FROM medical_price_limit WHERE 医保编码 IS NOT NULL AND 医保编码 != ''")
    valid_count = cursor.fetchone()
    print(f"有效数据（医保编码不为空）: {valid_count['count']}")
    
    cursor.execute("SELECT COUNT(*) as count FROM medical_price_limit WHERE 医保价格上限 IS NOT NULL AND 医保价格上限 != ''")
    price_count = cursor.fetchone()
    print(f"有价格数据（医保价格上限不为空）: {price_count['count']}")