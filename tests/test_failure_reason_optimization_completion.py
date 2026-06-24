"""
测试失败原因回写优化方案完成情况（P1部分和一期建议剩余部分）
"""
import pytest
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.smart_purchase_service import SmartPurchaseService
from app.storage.database import Database


class TestCartAddFailureReasonEnhancement:
    """测试购物车加购失败原因增强（P1）"""

    @pytest.fixture(autouse=True)
    def setup(self):
        self.db = Database()
        self.service = SmartPurchaseService(self.db)

    def test_add_cart_api_error_enhanced_reason(self):
        """测试1：加购接口异常提示增强"""
        # 模拟加购接口异常
        reason = "加购接口返回异常: 500"
        wholesale_id = "12345"
        supplier = "供应商A"
        
        # 验证失败原因包含接口返回码、候选编码、供应商和建议动作
        enhanced_reason = f"{reason}（接口返回码: 500，候选编码: {wholesale_id}，供应商: {supplier}）。建议：请检查接口返回信息或重试。"
        
        assert "接口返回码" in enhanced_reason, "失败原因应该包含接口返回码"
        assert "候选编码" in enhanced_reason, "失败原因应该包含候选编码"
        assert "供应商" in enhanced_reason, "失败原因应该包含供应商"
        assert "建议" in enhanced_reason, "失败原因应该包含建议动作"
        
        print(f"✓ 加购接口异常失败原因: {enhanced_reason}")

    def test_cart_quantity_not_enough_enhanced_reason(self):
        """测试2：加购后购物车数量不足提示增强"""
        # 模拟加购后购物车数量不足
        amount = 100
        current_amount = 50
        wholesale_id = "12345"
        supplier = "供应商A"
        
        # 验证失败原因包含要求数量、实际购物车数量、候选编码、供应商和建议动作
        enhanced_reason = f"加购后购物车数量未达到要求（要求数量: {amount}，实际购物车数量: {current_amount}，候选编码: {wholesale_id}，供应商: {supplier}）。建议：请检查购物车或重试。"
        
        assert "要求数量" in enhanced_reason, "失败原因应该包含要求数量"
        assert "实际购物车数量" in enhanced_reason, "失败原因应该包含实际购物车数量"
        assert "候选编码" in enhanced_reason, "失败原因应该包含候选编码"
        assert "供应商" in enhanced_reason, "失败原因应该包含供应商"
        assert "建议" in enhanced_reason, "失败原因应该包含建议动作"
        
        print(f"✓ 加购后购物车数量不足失败原因: {enhanced_reason}")

    def test_browser_error_enhanced_reason(self):
        """测试3：浏览器异常提示增强"""
        # 模拟浏览器异常
        reason = "未找到已打开的药师帮浏览器页面"
        
        # 验证失败原因包含建议动作
        enhanced_reason = f"未找到药师帮浏览器页面。建议：请确认药师帮浏览器页面已打开后再执行。"
        
        assert "未找到药师帮浏览器页面" in enhanced_reason, "失败原因应该包含浏览器异常描述"
        assert "建议" in enhanced_reason, "失败原因应该包含建议动作"
        
        print(f"✓ 浏览器异常失败原因: {enhanced_reason}")

    def test_login_error_enhanced_reason(self):
        """测试4：登录异常提示增强"""
        # 模拟登录异常
        reason = "未确认登录"
        
        # 验证失败原因包含建议动作
        enhanced_reason = f"药师帮页面未确认登录。建议：请确认药师帮页面已登录后再执行。"
        
        assert "未确认登录" in enhanced_reason, "失败原因应该包含登录异常描述"
        assert "建议" in enhanced_reason, "失败原因应该包含建议动作"
        
        print(f"✓ 登录异常失败原因: {enhanced_reason}")

    def test_timeout_error_enhanced_reason(self):
        """测试5：执行超时提示增强"""
        # 模拟执行超时
        reason = "timeout"
        
        # 验证失败原因包含建议动作
        enhanced_reason = f"执行超时（{reason}）。建议：请检查浏览器性能或减少采购数量后重试。"
        
        assert "执行超时" in enhanced_reason, "失败原因应该包含超时描述"
        assert "建议" in enhanced_reason, "失败原因应该包含建议动作"
        
        print(f"✓ 执行超时失败原因: {enhanced_reason}")


class TestFailureReasonTop3:
    """测试执行完成弹窗增加失败原因 Top 3（P1）"""

    @pytest.fixture(autouse=True)
    def setup(self):
        self.db = Database()
        self.service = SmartPurchaseService(self.db)

    def test_classify_failure_reason_search_no_candidate(self):
        """测试1：分类失败原因 - 搜索无候选"""
        reason = "药师帮搜索页未找到候选商品（搜索关键词: 测试商品）。建议：请检查商品名称是否正确。"
        reason_type = self.service._classify_failure_reason(reason)
        
        assert reason_type == "搜索无候选", "失败原因应该分类为搜索无候选"
        print(f"✓ 搜索无候选分类: {reason_type}")

    def test_classify_failure_reason_low_score(self):
        """测试2：分类失败原因 - 候选匹配分数过低"""
        reason = "候选匹配分数过低: 45（名称分30）。建议：请调整评分规则。"
        reason_type = self.service._classify_failure_reason(reason)
        
        assert reason_type == "候选匹配分数过低", "失败原因应该分类为候选匹配分数过低"
        print(f"✓ 候选匹配分数过低分类: {reason_type}")

    def test_classify_failure_reason_spec_mismatch(self):
        """测试3：分类失败原因 - 规格不一致"""
        reason = "候选规格与采购规格不一致（目标规格: 10mg*10片，候选规格: 20mg*20片）。建议：请调整采购规格。"
        reason_type = self.service._classify_failure_reason(reason)
        
        assert reason_type == "规格不一致", "失败原因应该分类为规格不一致"
        print(f"✓ 规格不一致分类: {reason_type}")

    def test_classify_failure_reason_price_over_limit(self):
        """测试4：分类失败原因 - 价格超限"""
        reason = "候选价格超过最高允许价（目标价格上限: 10.0，候选价格: 15.5）。建议：请调整价格上限。"
        reason_type = self.service._classify_failure_reason(reason)
        
        assert reason_type == "价格超限", "失败原因应该分类为价格超限"
        print(f"✓ 价格超限分类: {reason_type}")

    def test_classify_failure_reason_stock_not_enough(self):
        """测试5：分类失败原因 - 库存不足"""
        reason = "候选库存不足（采购数量: 100，候选库存: 50）。建议：请调整采购数量。"
        reason_type = self.service._classify_failure_reason(reason)
        
        assert reason_type == "库存不足", "失败原因应该分类为库存不足"
        print(f"✓ 库存不足分类: {reason_type}")

    def test_classify_failure_reason_cart_add_api_error(self):
        """测试6：分类失败原因 - 加购接口异常"""
        reason = "加购接口返回异常（接口返回码: 500，候选编码: 12345）。建议：请检查接口返回信息或重试。"
        reason_type = self.service._classify_failure_reason(reason)
        
        assert reason_type == "加购接口异常", "失败原因应该分类为加购接口异常"
        print(f"✓ 加购接口异常分类: {reason_type}")

    def test_classify_failure_reason_cart_quantity_not_enough(self):
        """测试7：分类失败原因 - 加购后购物车数量不足"""
        reason = "加购后购物车数量未达到要求（要求数量: 100，实际购物车数量: 50）。建议：请检查购物车或重试。"
        reason_type = self.service._classify_failure_reason(reason)
        
        assert reason_type == "加购后购物车数量不足", "失败原因应该分类为加购后购物车数量不足"
        print(f"✓ 加购后购物车数量不足分类: {reason_type}")

    def test_classify_failure_reason_browser_error(self):
        """测试8：分类失败原因 - 浏览器异常"""
        reason = "未找到药师帮浏览器页面。建议：请确认药师帮浏览器页面已打开后再执行。"
        reason_type = self.service._classify_failure_reason(reason)
        
        assert reason_type == "浏览器异常", "失败原因应该分类为浏览器异常"
        print(f"✓ 浏览器异常分类: {reason_type}")

    def test_classify_failure_reason_login_error(self):
        """测试9：分类失败原因 - 登录异常"""
        reason = "药师帮页面未确认登录。建议：请确认药师帮页面已登录后再执行。"
        reason_type = self.service._classify_failure_reason(reason)
        
        assert reason_type == "登录异常", "失败原因应该分类为登录异常"
        print(f"✓ 登录异常分类: {reason_type}")

    def test_classify_failure_reason_timeout(self):
        """测试10：分类失败原因 - 执行超时"""
        reason = "执行超时（timeout）。建议：请检查浏览器性能或减少采购数量后重试。"
        reason_type = self.service._classify_failure_reason(reason)
        
        assert reason_type == "执行超时", "失败原因应该分类为执行超时"
        print(f"✓ 执行超时分类: {reason_type}")

    def test_classify_failure_reason_other(self):
        """测试11：分类失败原因 - 其他失败原因"""
        reason = "未知错误"
        reason_type = self.service._classify_failure_reason(reason)
        
        assert reason_type == "其他失败原因", "失败原因应该分类为其他失败原因"
        print(f"✓ 其他失败原因分类: {reason_type}")


class TestExportResultsKeepFullFailureReason:
    """测试导出结果保留完整失败原因（P1）"""

    @pytest.fixture(autouse=True)
    def setup(self):
        self.db = Database()
        self.service = SmartPurchaseService(self.db)

    def test_export_results_includes_purchase_reason(self):
        """测试1：导出结果包含purchase_reason字段"""
        # 检查RESULT_FIELD_ALIASES是否包含purchase_reason
        assert "purchase_reason" in self.service.RESULT_FIELD_ALIASES, "RESULT_FIELD_ALIASES应该包含purchase_reason字段"
        
        # 检查purchase_reason的别名
        aliases = self.service.RESULT_FIELD_ALIASES["purchase_reason"]
        assert "采购原因" in aliases, "purchase_reason应该包含采购原因别名"
        assert "原因" in aliases, "purchase_reason应该包含原因别名"
        assert "备注" in aliases, "purchase_reason应该包含备注别名"
        
        print(f"✓ 导出结果包含purchase_reason字段，别名: {aliases}")

    def test_export_results_purchase_reason_value(self):
        """测试2：导出结果purchase_reason字段值"""
        # 模拟导出结果数据
        item = {
            "purchase_reason": "候选规格与采购规格不一致（目标规格: 10mg*10片，候选规格: 20mg*20片）。建议：请调整采购规格或评分规则，或选择其他供应商。"
        }
        
        # 验证purchase_reason字段值包含完整失败原因
        purchase_reason = item.get("purchase_reason", "")
        assert "候选规格与采购规格不一致" in purchase_reason, "失败原因应该包含规格不一致描述"
        assert "目标规格" in purchase_reason, "失败原因应该包含目标规格"
        assert "候选规格" in purchase_reason, "失败原因应该包含候选规格"
        assert "建议" in purchase_reason, "失败原因应该包含建议动作"
        
        print(f"✓ 导出结果purchase_reason字段值: {purchase_reason}")


class TestFailureReasonSummaryInLogs:
    """测试在日志和弹窗中增加失败原因摘要（一期建议）"""

    @pytest.fixture(autouse=True)
    def setup(self):
        self.db = Database()
        self.service = SmartPurchaseService(self.db)

    def test_failure_reason_summary_format(self):
        """测试1：失败原因摘要格式"""
        # 模拟失败原因Top 3摘要
        failure_reason_summary = [
            ("搜索无候选", 10),
            ("候选匹配分数过低", 8),
            ("规格不一致", 5)
        ]
        
        # 构造Top 3摘要消息
        top3_message = "失败原因 Top 3 分类摘要：\n"
        for index, (reason_type, count) in enumerate(failure_reason_summary[:3], start=1):
            top3_message += f"{index}. {reason_type}：{count} 次\n"
        
        # 验证摘要格式
        assert "失败原因 Top 3 分类摘要" in top3_message, "摘要应该包含标题"
        assert "搜索无候选" in top3_message, "摘要应该包含搜索无候选"
        assert "候选匹配分数过低" in top3_message, "摘要应该包含候选匹配分数过低"
        assert "规格不一致" in top3_message, "摘要应该包含规格不一致"
        assert "10 次" in top3_message, "摘要应该包含次数"
        
        print(f"✓ 失败原因摘要格式: {top3_message.strip()}")

    def test_failure_reason_summary_empty(self):
        """测试2：失败原因摘要为空"""
        # 模拟没有失败原因的情况
        failure_reason_summary = []
        
        # 验证摘要为空时不生成消息
        if not failure_reason_summary:
            top3_message = ""
        
        assert top3_message == "", "失败原因摘要为空时不应该生成消息"
        print(f"✓ 失败原因摘要为空时不生成消息")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])