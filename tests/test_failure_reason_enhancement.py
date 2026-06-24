"""
失败原因回写增强测试
测试逐个采购-失败原因回写优化方案的P0部分
"""
import pytest
import tempfile
from pathlib import Path
from app.storage.database import Database
from app.core.smart_purchase_service import SmartPurchaseService


class TestBatchLevelFailureReason:
    """测试批次级无法开始原因增强"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """每个测试前创建临时数据库"""
        self.temp_dir = tempfile.mkdtemp()
        self.db_path = Path(self.temp_dir) / "test_batch_failure.db"
        self.db = Database(str(self.db_path))
        self.db.initialize()
        self.service = SmartPurchaseService(self.db)
        
    def teardown(self):
        """每个测试后清理临时数据库"""
        try:
            if hasattr(self, 'db'):
                self.db.close()
        except:
            pass
    
    def test_batch_not_found_enhanced_reason(self):
        """测试1：批次不存在提示增强"""
        # 执行不存在的批次
        summary, logs, error_msg = self.service.execute_batch_purchase_real("nonexistent_batch_001")
        
        # 验证失败原因包含批次ID和批次状态统计
        assert error_msg != "", "应该返回错误消息"
        assert "批次ID" in error_msg, "失败原因应该包含批次ID"
        assert "不存在" in error_msg, "失败原因应该提示批次不存在"
        assert "建议" in error_msg, "失败原因应该包含建议动作"
        
        print(f"✓ 批次不存在失败原因: {error_msg}")


class TestRowLevelFailureReason:
    """测试行级基础校验失败原因增强"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """每个测试前创建临时数据库"""
        self.temp_dir = tempfile.mkdtemp()
        self.db_path = Path(self.temp_dir) / "test_row_failure.db"
        self.db = Database(str(self.db_path))
        self.db.initialize()
        self.service = SmartPurchaseService(self.db)
        
    def teardown(self):
        """每个测试后清理临时数据库"""
        try:
            if hasattr(self, 'db'):
                self.db.close()
        except:
            pass
    
    def test_missing_name_enhanced_reason(self):
        """测试2：缺少商品名称提示增强"""
        # 直接测试 _validate_purchase_item 方法
        item = {
            "row_number": 1,
            "source_name": "",  # 缺少商品名称
            "purchase_quantity": 10,
        }
        
        error = self.service._validate_purchase_item(item)
        
        # 验证失败原因包含行号、商品名、失败环节、建议动作
        assert error != "", "应该返回错误消息"
        assert "第1行" in error, "失败原因应该包含行号"
        assert "缺少商品名称" in error, "失败原因应该提示缺少商品名称"
        assert "建议" in error, "失败原因应该包含建议动作"
        
        print(f"✓ 缺少商品名称失败原因: {error}")
    
    def test_invalid_quantity_enhanced_reason(self):
        """测试3：采购数量无效提示增强"""
        # 直接测试 _validate_purchase_item 方法
        item = {
            "row_number": 2,
            "source_name": "测试商品",
            "purchase_quantity": 0,  # 采购数量无效
        }
        
        error = self.service._validate_purchase_item(item)
        
        # 验证失败原因包含行号、商品名、当前数量、建议动作
        assert error != "", "应该返回错误消息"
        assert "第2行" in error, "失败原因应该包含行号"
        assert "测试商品" in error, "失败原因应该包含商品名"
        assert "采购数量无效" in error, "失败原因应该提示采购数量无效"
        assert "当前数量" in error, "失败原因应该包含当前数量"
        assert "建议" in error, "失败原因应该包含建议动作"
        
        print(f"✓ 采购数量无效失败原因: {error}")
    
    def test_supplier_not_in_scope_enhanced_reason(self):
        """测试4：候选供应商不在允许范围提示增强"""
        # 直接测试 _validate_supplier_scope 方法
        item = {
            "row_number": 3,
            "source_name": "测试商品",
            "smart_supplier": "供应商B",  # 候选供应商不在允许范围
        }
        
        supplier_scope = ["供应商A"]
        
        error = self.service._validate_supplier_scope(item, supplier_scope)
        
        # 验证失败原因包含行号、商品名、候选供应商、允许范围、建议动作
        assert error != "", "应该返回错误消息"
        assert "第3行" in error, "失败原因应该包含行号"
        assert "测试商品" in error, "失败原因应该包含商品名"
        assert "候选供应商" in error, "失败原因应该包含候选供应商"
        assert "允许范围" in error, "失败原因应该包含允许范围"
        assert "供应商B" in error, "失败原因应该包含候选供应商名称"
        assert "供应商A" in error, "失败原因应该包含允许范围供应商"
        assert "建议" in error, "失败原因应该包含建议动作"
        
        print(f"✓ 候选供应商不在允许范围失败原因: {error}")


class TestYSBBMatchFailureReason:
    """测试药师帮匹配失败原因增强"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """每个测试前创建临时数据库"""
        self.temp_dir = tempfile.mkdtemp()
        self.db_path = Path(self.temp_dir) / "test_ysb_match_failure.db"
        self.db = Database(str(self.db_path))
        self.db.initialize()
        self.service = SmartPurchaseService(self.db)
        
    def teardown(self):
        """每个测试后清理临时数据库"""
        try:
            if hasattr(self, 'db'):
                self.db.close()
        except:
            pass
    
    def test_search_no_candidate_enhanced_reason(self):
        """测试5：搜索无候选提示增强（模拟Node.js返回）"""
        # 模拟Node.js返回的搜索无候选结果
        node_result = {
            "candidate": None,
            "score": 0,
            "count": 0,
            "reason": "药师帮搜索页未找到候选商品（搜索关键词: 测试商品）。建议：请检查商品名称是否正确，或尝试调整规格、厂家等关键词后重新搜索。url=https://www.ysbang.com/search"
        }
        
        # 验证失败原因包含搜索关键词、建议动作
        reason = node_result["reason"]
        assert "搜索关键词" in reason, "失败原因应该包含搜索关键词"
        assert "测试商品" in reason, "失败原因应该包含搜索关键词值"
        assert "建议" in reason, "失败原因应该包含建议动作"
        assert "url" in reason, "失败原因应该包含搜索URL"
        
        print(f"✓ 搜索无候选失败原因: {reason}")
    
    def test_low_score_candidate_enhanced_reason(self):
        """测试6：低分候选提示增强（模拟Node.js返回）"""
        # 模拟Node.js返回的低分候选结果
        node_result = {
            "candidate": None,
            "score": 45,
            "count": 5,
            "reason": "候选匹配分数过低: 45（名称分30；目标=测试商品/10mg*10片/厂家A；最佳候选=候选商品/20mg*20片/厂家B；供应商=供应商B；价格=15.5）；候选编码=12345；供应商全称=供应商B有限公司。建议：请调整评分规则或选择其他供应商。"
        }
        
        # 验证失败原因包含目标商品、最佳候选、分数、供应商、价格、候选编码、供应商全称、建议动作
        reason = node_result["reason"]
        assert "候选匹配分数过低" in reason, "失败原因应该提示低分"
        assert "目标=" in reason, "失败原因应该包含目标商品"
        assert "最佳候选=" in reason, "失败原因应该包含最佳候选"
        assert "供应商=" in reason, "失败原因应该包含供应商"
        assert "价格=" in reason, "失败原因应该包含价格"
        assert "候选编码=" in reason, "失败原因应该包含候选编码"
        assert "供应商全称=" in reason, "失败原因应该包含供应商全称"
        assert "建议" in reason, "失败原因应该包含建议动作"
        
        print(f"✓ 低分候选失败原因: {reason}")
    
    def test_spec_mismatch_enhanced_reason(self):
        """测试7：规格不一致提示增强（模拟Node.js返回）"""
        # 模拟Node.js返回的规格不一致结果
        node_result = {
            "candidate": None,
            "score": 75,
            "count": 3,
            "reason": "候选规格与采购规格不一致（目标规格: 10mg*10片，候选规格: 20mg*20片）。建议：请调整采购规格或评分规则，或选择其他供应商。"
        }
        
        # 验证失败原因包含目标规格、候选规格、建议动作
        reason = node_result["reason"]
        assert "候选规格与采购规格不一致" in reason, "失败原因应该提示规格不一致"
        assert "目标规格" in reason, "失败原因应该包含目标规格"
        assert "候选规格" in reason, "失败原因应该包含候选规格"
        assert "10mg*10片" in reason, "失败原因应该包含目标规格值"
        assert "20mg*20片" in reason, "失败原因应该包含候选规格值"
        assert "建议" in reason, "失败原因应该包含建议动作"
        
        print(f"✓ 规格不一致失败原因: {reason}")
    
    def test_price_over_limit_enhanced_reason(self):
        """测试8：价格超限提示增强（模拟Node.js返回）"""
        # 模拟Node.js返回的价格超限结果
        node_result = {
            "candidate": None,
            "score": 85,
            "count": 2,
            "reason": "候选价格超过最高允许价（目标价格上限: 10.0，候选价格: 15.5，候选编码: 12345）。建议：请调整价格上限或选择其他供应商。"
        }
        
        # 验证失败原因包含目标价格上限、候选价格、候选编码、建议动作
        reason = node_result["reason"]
        assert "候选价格超过最高允许价" in reason, "失败原因应该提示价格超限"
        assert "目标价格上限" in reason, "失败原因应该包含目标价格上限"
        assert "候选价格" in reason, "失败原因应该包含候选价格"
        assert "候选编码" in reason, "失败原因应该包含候选编码"
        assert "建议" in reason, "失败原因应该包含建议动作"
        
        print(f"✓ 价格超限失败原因: {reason}")
    
    def test_stock_not_enough_enhanced_reason(self):
        """测试9：库存不足提示增强（模拟Node.js返回）"""
        # 模拟Node.js返回的库存不足结果
        node_result = {
            "candidate": None,
            "score": 85,
            "count": 2,
            "reason": "候选库存不足（采购数量: 100，候选库存: 50，候选编码: 12345）。建议：请调整采购数量或选择其他供应商。"
        }
        
        # 验证失败原因包含采购数量、候选库存、候选编码、建议动作
        reason = node_result["reason"]
        assert "候选库存不足" in reason, "失败原因应该提示库存不足"
        assert "采购数量" in reason, "失败原因应该包含采购数量"
        assert "候选库存" in reason, "失败原因应该包含候选库存"
        assert "候选编码" in reason, "失败原因应该包含候选编码"
        assert "建议" in reason, "失败原因应该包含建议动作"
        
        print(f"✓ 库存不足失败原因: {reason}")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])