from app.storage.database import Database
from app.core.medical_price_import_service import MedicalPriceImportService

# 初始化数据库和服务
db = Database()
import_service = MedicalPriceImportService(db)

# 测试导入云药店商品目录
file_path = 'D:/project/RPA/商品信息维护20260608162511.xlsx'
result = import_service.import_cloud_pharmacy_catalog(file_path)

print(f"导入结果:")
print(f"  批次ID: {result.batch_id}")
print(f"  批次类型: {result.batch_type}")
print(f"  文件名: {result.file_name}")
print(f"  工作表: {result.sheet_name}")
print(f"  总行数: {result.total_rows}")
print(f"  成功行数: {result.success_rows}")
print(f"  失败行数: {result.failed_rows}")
print(f"  导入状态: {result.import_status}")
print(f"  错误信息: {result.error_message}")

if result.failures:
    print(f"\n失败明细（前5条）:")
    for failure in result.failures[:5]:
        print(f"  行 {failure['row_index']}: {failure['failure_reason']}")