"""
测试价格对比功能
"""
import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app.storage.database import Database
from app.core.medical_price_compare_service import MedicalPriceCompareService

def test_price_compare():
    """测试价格对比功能"""
    try:
        # 初始化数据库和服务
        db = Database()
        service = MedicalPriceCompareService(db)
        
        print("✓ 数据库和服务初始化成功")
        
        # 检查数据库表结构
        conn = db.get_connection()
        cursor = conn.cursor()
        
        # 检查junyuan_sales_price表
        cursor.execute("PRAGMA table_info(junyuan_sales_price)")
        jy_columns = [row['name'] for row in cursor.fetchall()]
        print(f"✓ junyuan_sales_price表字段: {jy_columns}")
        
        # 检查medical_price_compare_result表
        cursor.execute("PRAGMA table_info(medical_price_compare_result)")
        medical_columns = [row['name'] for row in cursor.fetchall()]
        print(f"✓ medical_price_compare_result表字段: {medical_columns}")
        
        # 检查是否有库存数量字段
        if '库存数量' in jy_columns:
            print("✓ junyuan_sales_price表包含库存数量字段")
        else:
            print("✗ junyuan_sales_price表缺少库存数量字段")
        
        if '君元库存数量' in medical_columns:
            print("✓ medical_price_compare_result表包含君元库存数量字段")
        else:
            print("✗ medical_price_compare_result表缺少君元库存数量字段")
        
        # 检查是否有批次数据
        cursor.execute("SELECT batch_id FROM junyuan_sales_price LIMIT 1")
        jy_batch = cursor.fetchone()
        
        if jy_batch:
            print(f"✓ 找到君元销售价格批次: {jy_batch['batch_id']}")
        else:
            print("✗ 未找到君元销售价格批次")
        
        print("\n✓ 测试完成")
        
    except Exception as e:
        print(f"✗ 测试失败: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_price_compare()