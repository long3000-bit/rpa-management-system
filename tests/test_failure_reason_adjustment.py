"""
测试失败原因回写优化调整方案（开发完成后测试结果与调整方案）
根据测试结果补充自动化测试
"""
import pytest
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.smart_purchase_service import SmartPurchaseService
from app.storage.database import Database


class TestPythonPriceErrorContainsContext:
    """测试Python价格校验失败原因包含关键上下文"""

    @pytest.fixture(autouse=True)
    def setup(self):
        self.db = Database()
        self.service = SmartPurchaseService(self.db)

    def test_price_error_contains_row_number(self):
        """测试1：价格失败原因包含行号"""
        item = {
            "row_number": 1,
            "source_name": "测试商品",
            "expected_price": 10.0,
            "smart_price": 0
        }
        
        error, max_price = self.service._validate_price(item)
        
        assert "第1行" in error, "价格失败原因应该包含行号"
        print(f"✓ 价格失败原因包含行号: {error}")

    def test_price_error_contains_item_name(self):
        """测试2：价格失败原因包含商品名"""
        item = {
            "row_number": 1,
            "source_name": "测试商品",
            "expected_price": 10.0,
            "smart_price": 0
        }
        
        error, max_price = self.service._validate_price(item)
        
        assert "测试商品" in error, "价格失败原因应该包含商品名"
        print(f"✓ 价格失败原因包含商品名: {error}")

    def test_price_error_contains_expected_price(self):
        """测试3：价格失败原因包含期望价"""
        item = {
            "row_number": 1,
            "source_name": "测试商品",
            "expected_price": 10.0,
            "smart_price": 15.0
        }
        
        error, max_price = self.service._validate_price(item)
        
        assert "期望价" in error, "价格失败原因应该包含期望价"
        assert "10" in error, "价格失败原因应该包含期望价数值"
        print(f"✓ 价格失败原因包含期望价: {error}")

    def test_price_error_contains_max_allowed_price(self):
        """测试4：价格失败原因包含最高允许价"""
        item = {
            "row_number": 1,
            "source_name": "测试商品",
            "expected_price": 10.0,
            "smart_price": 15.0
        }
        
        error, max_price = self.service._validate_price(item)
        
        assert "最高允许价" in error, "价格失败原因应该包含最高允许价"
        print(f"✓ 价格失败原因包含最高允许价: {error}")

    def test_price_error_contains_candidate_price(self):
        """测试5：价格失败原因包含候选价"""
        item = {
            "row_number": 1,
            "source_name": "测试商品",
            "expected_price": 10.0,
            "smart_price": 15.0
        }
        
        error, max_price = self.service._validate_price(item)
        
        assert "候选价" in error, "价格失败原因应该包含候选价"
        assert "15" in error, "价格失败原因应该包含候选价数值"
        print(f"✓ 价格失败原因包含候选价: {error}")

    def test_price_error_contains_compare_price(self):
        """测试6：价格失败原因包含折后比较价"""
        item = {
            "row_number": 1,
            "source_name": "测试商品",
            "expected_price": 10.0,
            "smart_price": 15.0
        }
        
        error, max_price = self.service._validate_price(item)
        
        assert "折后比较价" in error, "价格失败原因应该包含折后比较价"
        print(f"✓ 价格失败原因包含折后比较价: {error}")

    def test_price_error_contains_suggestion(self):
        """测试7：价格失败原因包含建议动作"""
        item = {
            "row_number": 1,
            "source_name": "测试商品",
            "expected_price": 10.0,
            "smart_price": 15.0
        }
        
        error, max_price = self.service._validate_price(item)
        
        assert "建议" in error, "价格失败原因应该包含建议动作"
        print(f"✓ 价格失败原因包含建议动作: {error}")


class TestPythonMinQtyErrorContainsContext:
    """测试Python起购校验失败原因包含关键上下文"""

    @pytest.fixture(autouse=True)
    def setup(self):
        self.db = Database()
        self.service = SmartPurchaseService(self.db)

    def test_min_qty_error_contains_row_number(self):
        """测试1：起购失败原因包含行号"""
        item = {
            "row_number": 1,
            "source_name": "测试商品",
            "purchase_quantity": 10,
            "min_purchase_quantity": 20
        }
        
        error = self.service._validate_min_quantity_and_stock(item)
        
        assert "第1行" in error, "起购失败原因应该包含行号"
        print(f"✓ 起购失败原因包含行号: {error}")

    def test_min_qty_error_contains_item_name(self):
        """测试2：起购失败原因包含商品名"""
        item = {
            "row_number": 1,
            "source_name": "测试商品",
            "purchase_quantity": 10,
            "min_purchase_quantity": 20
        }
        
        error = self.service._validate_min_quantity_and_stock(item)
        
        assert "测试商品" in error, "起购失败原因应该包含商品名"
        print(f"✓ 起购失败原因包含商品名: {error}")

    def test_min_qty_error_contains_purchase_quantity(self):
        """测试3：起购失败原因包含采购数量"""
        item = {
            "row_number": 1,
            "source_name": "测试商品",
            "purchase_quantity": 10,
            "min_purchase_quantity": 20
        }
        
        error = self.service._validate_min_quantity_and_stock(item)
        
        assert "采购数量" in error, "起购失败原因应该包含采购数量"
        assert "10" in error, "起购失败原因应该包含采购数量数值"
        print(f"✓ 起购失败原因包含采购数量: {error}")

    def test_min_qty_error_contains_min_quantity(self):
        """测试4：起购失败原因包含候选起购数量"""
        item = {
            "row_number": 1,
            "source_name": "测试商品",
            "purchase_quantity": 10,
            "min_purchase_quantity": 20
        }
        
        error = self.service._validate_min_quantity_and_stock(item)
        
        assert "候选起购数量" in error, "起购失败原因应该包含候选起购数量"
        assert "20" in error, "起购失败原因应该包含候选起购数量数值"
        print(f"✓ 起购失败原因包含候选起购数量: {error}")

    def test_min_qty_error_contains_suggestion(self):
        """测试5：起购失败原因包含建议动作"""
        item = {
            "row_number": 1,
            "source_name": "测试商品",
            "purchase_quantity": 10,
            "min_purchase_quantity": 20
        }
        
        error = self.service._validate_min_quantity_and_stock(item)
        
        assert "建议" in error, "起购失败原因应该包含建议动作"
        print(f"✓ 起购失败原因包含建议动作: {error}")


class TestPythonStockErrorContainsContext:
    """测试Python库存校验失败原因包含关键上下文"""

    @pytest.fixture(autouse=True)
    def setup(self):
        self.db = Database()
        self.service = SmartPurchaseService(self.db)

    def test_stock_error_contains_row_number(self):
        """测试1：库存失败原因包含行号"""
        item = {
            "row_number": 1,
            "source_name": "测试商品",
            "purchase_quantity": 100,
            "available_stock": 50
        }
        
        error = self.service._validate_min_quantity_and_stock(item)
        
        assert "第1行" in error, "库存失败原因应该包含行号"
        print(f"✓ 库存失败原因包含行号: {error}")

    def test_stock_error_contains_item_name(self):
        """测试2：库存失败原因包含商品名"""
        item = {
            "row_number": 1,
            "source_name": "测试商品",
            "purchase_quantity": 100,
            "available_stock": 50
        }
        
        error = self.service._validate_min_quantity_and_stock(item)
        
        assert "测试商品" in error, "库存失败原因应该包含商品名"
        print(f"✓ 库存失败原因包含商品名: {error}")

    def test_stock_error_contains_purchase_quantity(self):
        """测试3：库存失败原因包含采购数量"""
        item = {
            "row_number": 1,
            "source_name": "测试商品",
            "purchase_quantity": 100,
            "available_stock": 50
        }
        
        error = self.service._validate_min_quantity_and_stock(item)
        
        assert "采购数量" in error, "库存失败原因应该包含采购数量"
        assert "100" in error, "库存失败原因应该包含采购数量数值"
        print(f"✓ 库存失败原因包含采购数量: {error}")

    def test_stock_error_contains_stock(self):
        """测试4：库存失败原因包含候选库存"""
        item = {
            "row_number": 1,
            "source_name": "测试商品",
            "purchase_quantity": 100,
            "available_stock": 50
        }
        
        error = self.service._validate_min_quantity_and_stock(item)
        
        assert "候选库存" in error, "库存失败原因应该包含候选库存"
        assert "50" in error, "库存失败原因应该包含候选库存数值"
        print(f"✓ 库存失败原因包含候选库存: {error}")

    def test_stock_error_contains_suggestion(self):
        """测试5：库存失败原因包含建议动作"""
        item = {
            "row_number": 1,
            "source_name": "测试商品",
            "purchase_quantity": 100,
            "available_stock": 50
        }
        
        error = self.service._validate_min_quantity_and_stock(item)
        
        assert "建议" in error, "库存失败原因应该包含建议动作"
        print(f"✓ 库存失败原因包含建议动作: {error}")


class TestNodeInvalidAmountReasonContainsContext:
    """测试Node无效采购数量失败原因包含关键上下文"""

    def test_node_invalid_amount_reason_format(self):
        """测试1：Node无效采购数量失败原因格式"""
        # 模拟Node返回的失败原因
        row_number = 1
        name = "测试商品"
        amount = 0
        
        # 验证失败原因包含行号、商品名、当前数量、建议动作
        expected_reason = f"第{row_number}行 {name}: 采购数量无效（当前数量: {amount}）。建议：请修改采购数量为大于0的数值后重试。"
        
        assert "第1行" in expected_reason, "失败原因应该包含行号"
        assert "测试商品" in expected_reason, "失败原因应该包含商品名"
        assert "当前数量" in expected_reason, "失败原因应该包含当前数量"
        assert "0" in expected_reason, "失败原因应该包含当前数量数值"
        assert "建议" in expected_reason, "失败原因应该包含建议动作"
        
        print(f"✓ Node无效采购数量失败原因格式: {expected_reason}")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])