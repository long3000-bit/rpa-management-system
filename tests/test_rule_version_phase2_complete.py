"""
规则版本管理二期完整测试
验证所有阶段功能：规则版本管理、灰度发布、规则生效范围控制、规则效果统计、规则可持续优化
"""

import pytest
import tempfile
import json
from pathlib import Path
from datetime import datetime
from app.storage.database import Database
from app.core.smart_rule_version_service import SmartRuleVersionService
from app.core.gray_release_service import GrayReleaseService
from app.core.rule_effect_service import RuleEffectService
from app.core.rule_scope_service import RuleScopeService
from app.core.rule_optimization_service import RuleOptimizationService


class TestRuleScopeControl:
    """测试规则生效范围控制功能（阶段三）"""

    @pytest.fixture(autouse=True)
    def setup(self):
        self.temp_dir = tempfile.mkdtemp()
        self.db_path = Path(self.temp_dir) / "test_rule_scope.db"
        self.db = Database(str(self.db_path))
        self.db.initialize()

        self.rule_version_service = SmartRuleVersionService(self.db)
        self.rule_scope_service = RuleScopeService(self.db)

    def test_set_rule_scope(self):
        """测试1：设置规则生效范围"""
        # 先创建规则版本
        rule_data = {
            "rule_set_code": "test_scope",
            "rule_set_name": "测试规则集",
            "description": "测试",
            "version_number": "v1.0.0",
            "change_reason": "初始版本",
            "change_type": "new",
            "configs": [
                {
                    "rule_key": "name_weight",
                    "rule_name": "名称权重",
                    "rule_value": "0.60",
                    "rule_type": "weight",
                    "sort_order": 1
                }
            ]
        }

        self.rule_version_service.create_rule_version(rule_data, "test_user")

        # 设置规则生效范围
        scope_config = {
            "scope_type": "batch",
            "scope_value": ["batch1", "batch2", "batch3"],
            "scope_priority": 1,
            "scope_status": "active"
        }

        success, error_msg = self.rule_scope_service.set_rule_scope("test_scope", scope_config, "test_user")
        assert success, f"设置规则生效范围失败：{error_msg}"

        # 验证范围配置已保存
        conn = self.db.get_connection()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT scope_type, scope_value, scope_status FROM smart_rule_scope_configs WHERE rule_set_code = ?",
            ("test_scope",)
        )
        row = cursor.fetchone()
        assert row is not None, "范围配置应该已保存"
        assert row["scope_type"] == "batch", "范围类型应该为batch"
        assert row["scope_status"] == "active", "范围状态应该为active"

        print("✓ 设置规则生效范围测试通过")

    def test_get_rule_scope(self):
        """测试2：获取规则生效范围"""
        # 先创建规则版本和范围配置
        rule_data = {
            "rule_set_code": "test_get_scope",
            "rule_set_name": "测试规则集",
            "description": "测试",
            "version_number": "v1.0.0",
            "change_reason": "初始版本",
            "change_type": "new",
            "configs": [
                {
                    "rule_key": "name_weight",
                    "rule_name": "名称权重",
                    "rule_value": "0.60",
                    "rule_type": "weight",
                    "sort_order": 1
                }
            ]
        }

        self.rule_version_service.create_rule_version(rule_data, "test_user")

        scope_config = {
            "scope_type": "user",
            "scope_value": ["user1", "user2"],
            "scope_priority": 2,
            "scope_status": "active"
        }

        self.rule_scope_service.set_rule_scope("test_get_scope", scope_config, "test_user")

        # 获取规则生效范围
        scope_list, error_msg = self.rule_scope_service.get_rule_scope("test_get_scope")
        assert not error_msg, f"获取规则生效范围失败：{error_msg}"
        assert len(scope_list) > 0, "应该有范围配置"

        # 验证范围配置内容
        scope_data = scope_list[0]
        assert scope_data["scope_type"] == "user", "范围类型应该为user"
        assert scope_data["scope_value"] == ["user1", "user2"], "范围值应该正确"

        print("✓ 获取规则生效范围测试通过")

    def test_check_rule_scope(self):
        """测试3：检查规则是否生效"""
        # 先创建规则版本并发布
        rule_data = {
            "rule_set_code": "test_check_scope",
            "rule_set_name": "测试规则集",
            "description": "测试",
            "version_number": "v1.0.0",
            "change_reason": "初始版本",
            "change_type": "new",
            "configs": [
                {
                    "rule_key": "name_weight",
                    "rule_name": "名称权重",
                    "rule_value": "0.60",
                    "rule_type": "weight",
                    "sort_order": 1
                }
            ]
        }

        self.rule_version_service.create_rule_version(rule_data, "test_user")

        # 审核并发布
        conn = self.db.get_connection()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT audit_id FROM smart_rule_audit_logs WHERE rule_set_code = ?",
            ("test_check_scope",)
        )
        row = cursor.fetchone()
        audit_id = row["audit_id"]

        self.rule_version_service.audit_rule_version(audit_id, "approved", "auditor", "审核通过")
        self.rule_version_service.release_rule_version("test_check_scope", "full")

        # 设置规则生效范围
        scope_config = {
            "scope_type": "batch",
            "scope_value": ["batch1", "batch2"],
            "scope_priority": 1,
            "scope_status": "active"
        }

        self.rule_scope_service.set_rule_scope("test_check_scope", scope_config, "test_user")

        # 检查规则是否生效
        is_effective, error_msg = self.rule_scope_service.check_rule_scope(
            "test_check_scope", "batch1", "user1", {}
        )
        assert is_effective, f"规则应该生效：{error_msg}"

        # 检查不符合范围的批次
        is_effective, error_msg = self.rule_scope_service.check_rule_scope(
            "test_check_scope", "batch3", "user1", {}
        )
        assert not is_effective, "规则不应该生效"

        print("✓ 检查规则是否生效测试通过")

    def test_delete_rule_scope(self):
        """测试4：删除规则生效范围"""
        # 先创建规则版本和范围配置
        rule_data = {
            "rule_set_code": "test_delete_scope",
            "rule_set_name": "测试规则集",
            "description": "测试",
            "version_number": "v1.0.0",
            "change_reason": "初始版本",
            "change_type": "new",
            "configs": [
                {
                    "rule_key": "name_weight",
                    "rule_name": "名称权重",
                    "rule_value": "0.60",
                    "rule_type": "weight",
                    "sort_order": 1
                }
            ]
        }

        self.rule_version_service.create_rule_version(rule_data, "test_user")

        scope_config = {
            "scope_type": "batch",
            "scope_value": ["batch1"],
            "scope_priority": 1,
            "scope_status": "active"
        }

        self.rule_scope_service.set_rule_scope("test_delete_scope", scope_config, "test_user")

        # 删除规则生效范围
        success, error_msg = self.rule_scope_service.delete_rule_scope("test_delete_scope", "batch")
        assert success, f"删除规则生效范围失败：{error_msg}"

        # 验证范围配置已删除
        conn = self.db.get_connection()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT COUNT(*) as count FROM smart_rule_scope_configs WHERE rule_set_code = ?",
            ("test_delete_scope",)
        )
        row = cursor.fetchone()
        assert row["count"] == 0, "范围配置应该已删除"

        print("✓ 删除规则生效范围测试通过")


class TestRuleOptimization:
    """测试规则可持续优化功能（阶段六）"""

    @pytest.fixture(autouse=True)
    def setup(self):
        self.temp_dir = tempfile.mkdtemp()
        self.db_path = Path(self.temp_dir) / "test_rule_optimization.db"
        self.db = Database(str(self.db_path))
        self.db.initialize()

        self.rule_version_service = SmartRuleVersionService(self.db)
        self.rule_optimization_service = RuleOptimizationService(self.db)

    def test_adjust_rule_params(self):
        """测试1：调整规则参数"""
        # 先创建规则版本
        rule_data = {
            "rule_set_code": "test_optimization",
            "rule_set_name": "测试规则集",
            "description": "测试",
            "version_number": "v1.0.0",
            "change_reason": "初始版本",
            "change_type": "new",
            "configs": [
                {
                    "rule_key": "name_weight",
                    "rule_name": "名称权重",
                    "rule_value": "0.60",
                    "rule_type": "weight",
                    "sort_order": 1
                },
                {
                    "rule_key": "spec_weight",
                    "rule_name": "规格权重",
                    "rule_value": "0.20",
                    "rule_type": "weight",
                    "sort_order": 2
                }
            ]
        }

        self.rule_version_service.create_rule_version(rule_data, "test_user")

        # 调整规则参数
        params = {
            "adjustment_type": "weight",
            "new_params": {
                "name_weight": "0.65",
                "spec_weight": "0.25"
            },
            "adjustment_reason": "优化权重配置"
        }

        adjustment_id, error_msg = self.rule_optimization_service.adjust_rule_params("test_optimization", params, "test_user")
        assert not error_msg, f"调整规则参数失败：{error_msg}"
        assert adjustment_id, "调整ID应该不为空"

        # 验证调整记录已创建
        conn = self.db.get_connection()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT adjustment_id, adjustment_type, test_status FROM smart_rule_param_adjustments WHERE adjustment_id = ?",
            (adjustment_id,)
        )
        row = cursor.fetchone()
        assert row is not None, "调整记录应该已创建"
        assert row["adjustment_type"] == "weight", "调整类型应该为weight"
        assert row["test_status"] == "pending", "测试状态应该为pending"

        print("✓ 调整规则参数测试通过")

    def test_test_rule_adjustment(self):
        """测试2：测试规则调整"""
        # 先创建规则版本和调整记录
        rule_data = {
            "rule_set_code": "test_adjustment",
            "rule_set_name": "测试规则集",
            "description": "测试",
            "version_number": "v1.0.0",
            "change_reason": "初始版本",
            "change_type": "new",
            "configs": [
                {
                    "rule_key": "name_weight",
                    "rule_name": "名称权重",
                    "rule_value": "0.60",
                    "rule_type": "weight",
                    "sort_order": 1
                }
            ]
        }

        self.rule_version_service.create_rule_version(rule_data, "test_user")

        params = {
            "adjustment_type": "weight",
            "new_params": {
                "name_weight": "0.70"
            },
            "adjustment_reason": "提高名称权重"
        }

        adjustment_id, _ = self.rule_optimization_service.adjust_rule_params("test_adjustment", params, "test_user")

        # 测试规则调整
        test_data = {
            "test_items": [
                {"name": "商品1", "spec": "规格1"},
                {"name": "商品2", "spec": "规格2"}
            ],
            "test_batch_id": "test_batch"
        }

        test_result, error_msg = self.rule_optimization_service.test_rule_adjustment(adjustment_id, test_data)
        assert not error_msg, f"测试规则调整失败：{error_msg}"
        assert "test_items_count" in test_result, "测试结果应该包含测试商品数"
        assert test_result["test_items_count"] == 2, "测试商品数应该为2"

        # 验证测试状态已更新
        conn = self.db.get_connection()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT test_status FROM smart_rule_param_adjustments WHERE adjustment_id = ?",
            (adjustment_id,)
        )
        row = cursor.fetchone()
        assert row["test_status"] == "completed", "测试状态应该为completed"

        print("✓ 测试规则调整测试通过")

    def test_verify_rule_adjustment(self):
        """测试3：验证规则调整"""
        # 先创建规则版本、调整记录并测试
        rule_data = {
            "rule_set_code": "test_verify",
            "rule_set_name": "测试规则集",
            "description": "测试",
            "version_number": "v1.0.0",
            "change_reason": "初始版本",
            "change_type": "new",
            "configs": [
                {
                    "rule_key": "name_weight",
                    "rule_name": "名称权重",
                    "rule_value": "0.60",
                    "rule_type": "weight",
                    "sort_order": 1
                }
            ]
        }

        self.rule_version_service.create_rule_version(rule_data, "test_user")

        params = {
            "adjustment_type": "weight",
            "new_params": {
                "name_weight": "0.70"
            },
            "adjustment_reason": "提高名称权重"
        }

        adjustment_id, _ = self.rule_optimization_service.adjust_rule_params("test_verify", params, "test_user")

        test_data = {
            "test_items": [{"name": "商品1"}]
        }

        self.rule_optimization_service.test_rule_adjustment(adjustment_id, test_data)

        # 验证规则调整
        success, error_msg = self.rule_optimization_service.verify_rule_adjustment(adjustment_id)
        assert success, f"验证规则调整失败：{error_msg}"

        # 验证验证状态已更新
        conn = self.db.get_connection()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT verify_status FROM smart_rule_param_adjustments WHERE adjustment_id = ?",
            (adjustment_id,)
        )
        row = cursor.fetchone()
        assert row["verify_status"] == "approved", "验证状态应该为approved"

        print("✓ 验证规则调整测试通过")

    def test_apply_rule_adjustment(self):
        """测试4：应用规则调整"""
        # 先创建规则版本、调整记录、测试并验证
        rule_data = {
            "rule_set_code": "test_apply",
            "rule_set_name": "测试规则集",
            "description": "测试",
            "version_number": "v1.0.0",
            "change_reason": "初始版本",
            "change_type": "new",
            "configs": [
                {
                    "rule_key": "name_weight",
                    "rule_name": "名称权重",
                    "rule_value": "0.60",
                    "rule_type": "weight",
                    "sort_order": 1
                }
            ]
        }

        self.rule_version_service.create_rule_version(rule_data, "test_user")

        params = {
            "adjustment_type": "weight",
            "new_params": {
                "name_weight": "0.70"
            },
            "adjustment_reason": "提高名称权重"
        }

        adjustment_id, _ = self.rule_optimization_service.adjust_rule_params("test_apply", params, "test_user")

        test_data = {
            "test_items": [{"name": "商品1"}]
        }

        self.rule_optimization_service.test_rule_adjustment(adjustment_id, test_data)
        self.rule_optimization_service.verify_rule_adjustment(adjustment_id)

        # 应用规则调整
        success, error_msg = self.rule_optimization_service.apply_rule_adjustment(adjustment_id, "test_user")
        assert success, f"应用规则调整失败：{error_msg}"

        # 验证规则配置已更新
        conn = self.db.get_connection()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT rule_value FROM smart_match_rule_configs WHERE rule_set_code = ? AND rule_key = ?",
            ("test_apply", "name_weight")
        )
        row = cursor.fetchone()
        assert row["rule_value"] == "0.70", "规则配置应该已更新"

        # 验证版本号已升级
        cursor.execute(
            "SELECT version_number FROM smart_match_rule_sets WHERE rule_set_code = ?",
            ("test_apply",)
        )
        row = cursor.fetchone()
        assert row["version_number"] == "v1.0.1", "版本号应该已升级"

        print("✓ 应用规则调整测试通过")

    def test_get_adjustment_history(self):
        """测试5：获取调整历史"""
        # 先创建规则版本和调整记录
        rule_data = {
            "rule_set_code": "test_history",
            "rule_set_name": "测试规则集",
            "description": "测试",
            "version_number": "v1.0.0",
            "change_reason": "初始版本",
            "change_type": "new",
            "configs": [
                {
                    "rule_key": "name_weight",
                    "rule_name": "名称权重",
                    "rule_value": "0.60",
                    "rule_type": "weight",
                    "sort_order": 1
                }
            ]
        }

        self.rule_version_service.create_rule_version(rule_data, "test_user")

        params = {
            "adjustment_type": "weight",
            "new_params": {
                "name_weight": "0.70"
            },
            "adjustment_reason": "提高名称权重"
        }

        self.rule_optimization_service.adjust_rule_params("test_history", params, "test_user")

        # 获取调整历史
        history_list, error_msg = self.rule_optimization_service.get_adjustment_history("test_history")
        assert not error_msg, f"获取调整历史失败：{error_msg}"
        assert len(history_list) > 0, "应该有调整历史"

        # 验证历史记录内容
        history_record = history_list[0]
        assert history_record["adjustment_type"] == "weight", "调整类型应该为weight"
        assert history_record["test_status"] == "pending", "测试状态应该为pending"

        print("✓ 获取调整历史测试通过")

    def test_rollback_adjustment(self):
        """测试6：回滚调整"""
        # 先创建规则版本、调整记录、测试、验证并应用
        rule_data = {
            "rule_set_code": "test_rollback_adjustment",
            "rule_set_name": "测试规则集",
            "description": "测试",
            "version_number": "v1.0.0",
            "change_reason": "初始版本",
            "change_type": "new",
            "configs": [
                {
                    "rule_key": "name_weight",
                    "rule_name": "名称权重",
                    "rule_value": "0.60",
                    "rule_type": "weight",
                    "sort_order": 1
                }
            ]
        }

        self.rule_version_service.create_rule_version(rule_data, "test_user")

        params = {
            "adjustment_type": "weight",
            "new_params": {
                "name_weight": "0.70"
            },
            "adjustment_reason": "提高名称权重"
        }

        adjustment_id, _ = self.rule_optimization_service.adjust_rule_params("test_rollback_adjustment", params, "test_user")

        test_data = {
            "test_items": [{"name": "商品1"}]
        }

        self.rule_optimization_service.test_rule_adjustment(adjustment_id, test_data)
        self.rule_optimization_service.verify_rule_adjustment(adjustment_id)
        self.rule_optimization_service.apply_rule_adjustment(adjustment_id, "test_user")

        # 回滚调整
        success, error_msg = self.rule_optimization_service.rollback_adjustment(adjustment_id, "test_user")
        assert success, f"回滚调整失败：{error_msg}"

        # 验证规则配置已回滚
        conn = self.db.get_connection()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT rule_value FROM smart_match_rule_configs WHERE rule_set_code = ? AND rule_key = ?",
            ("test_rollback_adjustment", "name_weight")
        )
        row = cursor.fetchone()
        assert row["rule_value"] == "0.60", "规则配置应该已回滚"

        # 验证版本号已升级（回滚也算版本升级）
        cursor.execute(
            "SELECT version_number FROM smart_match_rule_sets WHERE rule_set_code = ?",
            ("test_rollback_adjustment",)
        )
        row = cursor.fetchone()
        assert row["version_number"] == "v1.0.2", "版本号应该已升级"

        print("✓ 回滚调整测试通过")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])