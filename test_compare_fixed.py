"""测试修复后的比对服务"""

import sys
sys.path.insert(0, 'd:/project/RPA')

from app.storage.database import Database
from app.core.medical_price_compare_service import MedicalPriceCompareService

db = Database()
compare_service = MedicalPriceCompareService(db)

print("=" * 60)
print("测试修复后的价格比对")
print("=" * 60)

result = compare_service.run_compare(compare_by="test")

print(f"\n比对结果:")
print(f"  批次ID: {result.batch_id}")
print(f"  比对状态: {result.compare_status}")
print(f"  总数: {result.total_count}")
print(f"  正常: {result.normal_count}")
print(f"  异常: {result.abnormal_count}")
print(f"  严重异常: {result.severe_count}")
print(f"  待补价格: {result.missing_price_count}")
print(f"  待补编码: {result.missing_code_count}")
print(f"  待确认: {result.pending_count}")
print(f"  错误信息: {result.error_message}")

if result.total_count > 0:
    print(f"\n百分比:")
    total = result.total_count
    print(f"  正常: {result.normal_count / total * 100:.1f}%")
    print(f"  异常: {result.abnormal_count / total * 100:.1f}%")
    print(f"  严重异常: {result.severe_count / total * 100:.1f}%")
    print(f"  待补价格: {result.missing_price_count / total * 100:.1f}%")
    print(f"  待补编码: {result.missing_code_count / total * 100:.1f}%")
    print(f"  待确认: {result.pending_count / total * 100:.1f}%")