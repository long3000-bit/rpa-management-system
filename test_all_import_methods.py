"""测试导入服务的所有方法"""

from app.storage.database import Database
from app.core.medical_price_import_service import MedicalPriceImportService

# 初始化数据库和服务
db = Database()
import_service = MedicalPriceImportService(db)

# 测试所有方法
print("=" * 60)
print("测试导入服务的所有方法")
print("=" * 60)

# 1. 测试 get_import_batches 方法
print("\n1. 测试 get_import_batches 方法:")
batches = import_service.get_import_batches(limit=5)
print(f"   获取到 {len(batches)} 个批次")

# 2. 测试 get_available_batches_for_compare 方法
print("\n2. 测试 get_available_batches_for_compare 方法:")
try:
    available_batches = import_service.get_available_batches_for_compare()
    print(f"   方法调用成功！")
    print(f"   西药目录批次: {len(available_batches.get('medical_catalog_western', []))}")
    print(f"   中成药目录批次: {len(available_batches.get('medical_catalog_chinese', []))}")
    print(f"   价格上限批次: {len(available_batches.get('medical_price_limit', []))}")
    print(f"   云药店商品目录批次: {len(available_batches.get('cloud_pharmacy_catalog', []))}")
    print(f"   君元销售价格批次: {len(available_batches.get('junyuan_sales_price', []))}")
except AttributeError as e:
    print(f"   ❌ 方法不存在: {e}")
except Exception as e:
    print(f"   ❌ 方法调用失败: {e}")

# 3. 测试 delete_batch 方法
print("\n3. 测试 delete_batch 方法:")
print(f"   方法存在: {hasattr(import_service, 'delete_batch')}")

print("\n" + "=" * 60)
print("测试完成")
print("=" * 60)