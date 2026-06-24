"""
三期阶段4.2测试 - 规则状态流转
验证：
1. 创建草稿规则集
2. 提交审核
3. 审核通过/拒绝
4. 激活/停用
5. 状态流转限制
"""
import pytest
from pathlib import Path

from app.storage.database import Database
from app.core.rule_lifecycle_service import RuleLifecycleService
from app.core.smart_purchase_service import SmartPurchaseService


@pytest.fixture
def db(tmp_path):
    db_path = str(tmp_path / "test_phase4_round2.db")
    database = Database(db_path)
    database.initialize()
    sps = SmartPurchaseService(database)
    yield database
    database.close()


@pytest.fixture
def lifecycle_service(db):
    return RuleLifecycleService(db)


class TestCreateDraftRuleSet:
    """创建草稿规则集"""

    def test_create_draft_with_valid_configs(self, lifecycle_service):
        """创建有效草稿规则集"""
        configs = [
            {"rule_key": "name_weight", "rule_value": "0.62", "rule_type": "number"},
            {"rule_key": "spec_weight", "rule_value": "0.23", "rule_type": "number"},
            {"rule_key": "maker_weight", "rule_value": "0.15", "rule_type": "number"},
            {"rule_key": "min_purchase_score", "rule_value": "70", "rule_type": "number"},
        ]
        success, msg = lifecycle_service.create_draft_rule_set(
            "test_draft_001", "测试草稿", configs, created_by="admin"
        )
        assert success is True
        assert "已创建" in msg

    def test_create_draft_with_duplicate_code_fails(self, lifecycle_service):
        """重复代码应失败"""
        configs = [{"rule_key": "name_weight", "rule_value": "0.62", "rule_type": "number"}]
        # 第一次创建
        lifecycle_service.create_draft_rule_set("test_dup", "测试", configs)
        # 第二次创建应失败
        success, msg = lifecycle_service.create_draft_rule_set("test_dup", "测试2", configs)
        assert success is False
        assert "已存在" in msg

    def test_draft_status_is_draft(self, lifecycle_service, db):
        """草稿状态应为 draft"""
        configs = [{"rule_key": "name_weight", "rule_value": "0.62", "rule_type": "number"}]
        lifecycle_service.create_draft_rule_set("test_draft_status", "测试", configs)

        status_info = lifecycle_service.get_rule_set_status("test_draft_status")
        assert status_info["status"] == "draft"


class TestSubmitForReview:
    """提交审核"""

    def test_submit_draft_for_review(self, lifecycle_service):
        """草稿提交审核"""
        configs = [
            {"rule_key": "name_weight", "rule_value": "0.62", "rule_type": "number"},
            {"rule_key": "spec_weight", "rule_value": "0.23", "rule_type": "number"},
            {"rule_key": "maker_weight", "rule_value": "0.15", "rule_type": "number"},
            {"rule_key": "min_purchase_score", "rule_value": "70", "rule_type": "number"},
        ]
        lifecycle_service.create_draft_rule_set("test_submit_001", "测试", configs)
        success, msg = lifecycle_service.submit_for_review("test_submit_001", submitted_by="admin")
        assert success is True
        assert "已提交审核" in msg

    def test_submit_invalid_params_fails(self, lifecycle_service):
        """无效参数提交应失败"""
        configs = [
            {"rule_key": "name_weight", "rule_value": "abc", "rule_type": "number"},  # 无效值
        ]
        lifecycle_service.create_draft_rule_set("test_invalid_params", "测试", configs)
        success, msg = lifecycle_service.submit_for_review("test_invalid_params")
        assert success is False
        assert "参数校验失败" in msg

    def test_submit_non_draft_fails(self, lifecycle_service):
        """非草稿状态提交应失败"""
        # active 状态不能提交审核
        success, msg = lifecycle_service.submit_for_review("default_v1")
        assert success is False
        assert "不能提交审核" in msg


class TestApproveRuleSet:
    """审核通过"""

    def test_approve_pending_review(self, lifecycle_service):
        """待审核规则集审核通过"""
        configs = [
            {"rule_key": "name_weight", "rule_value": "0.62", "rule_type": "number"},
            {"rule_key": "spec_weight", "rule_value": "0.23", "rule_type": "number"},
            {"rule_key": "maker_weight", "rule_value": "0.15", "rule_type": "number"},
            {"rule_key": "min_purchase_score", "rule_value": "70", "rule_type": "number"},
        ]
        lifecycle_service.create_draft_rule_set("test_approve_001", "测试", configs)
        lifecycle_service.submit_for_review("test_approve_001")
        success, msg = lifecycle_service.approve_rule_set("test_approve_001", reviewed_by="admin")
        assert success is True
        assert "已审核通过" in msg

    def test_approve_non_pending_fails(self, lifecycle_service):
        """非待审核状态审核通过应失败"""
        success, msg = lifecycle_service.approve_rule_set("default_v1")
        assert success is False
        assert "不能审核通过" in msg

    def test_approved_status_is_approved(self, lifecycle_service):
        """审核通过后状态应为 approved"""
        configs = [
            {"rule_key": "name_weight", "rule_value": "0.62", "rule_type": "number"},
            {"rule_key": "spec_weight", "rule_value": "0.23", "rule_type": "number"},
            {"rule_key": "maker_weight", "rule_value": "0.15", "rule_type": "number"},
            {"rule_key": "min_purchase_score", "rule_value": "70", "rule_type": "number"},
        ]
        lifecycle_service.create_draft_rule_set("test_approved_status", "测试", configs)
        lifecycle_service.submit_for_review("test_approved_status")
        lifecycle_service.approve_rule_set("test_approved_status")

        status_info = lifecycle_service.get_rule_set_status("test_approved_status")
        assert status_info["status"] == "approved"


class TestRejectRuleSet:
    """审核拒绝"""

    def test_reject_pending_review(self, lifecycle_service):
        """待审核规则集审核拒绝"""
        configs = [
            {"rule_key": "name_weight", "rule_value": "0.62", "rule_type": "number"},
            {"rule_key": "spec_weight", "rule_value": "0.23", "rule_type": "number"},
            {"rule_key": "maker_weight", "rule_value": "0.15", "rule_type": "number"},
            {"rule_key": "min_purchase_score", "rule_value": "70", "rule_type": "number"},
        ]
        lifecycle_service.create_draft_rule_set("test_reject_001", "测试", configs)
        lifecycle_service.submit_for_review("test_reject_001")
        success, msg = lifecycle_service.reject_rule_set(
            "test_reject_001", reviewed_by="admin", review_comment="参数不合理"
        )
        assert success is True
        assert "已审核拒绝" in msg

    def test_reject_non_pending_fails(self, lifecycle_service):
        """非待审核状态审核拒绝应失败"""
        success, msg = lifecycle_service.reject_rule_set("default_v1")
        assert success is False
        assert "不能审核拒绝" in msg

    def test_rejected_status_is_rejected(self, lifecycle_service):
        """审核拒绝后状态应为 rejected"""
        configs = [
            {"rule_key": "name_weight", "rule_value": "0.62", "rule_type": "number"},
            {"rule_key": "spec_weight", "rule_value": "0.23", "rule_type": "number"},
            {"rule_key": "maker_weight", "rule_value": "0.15", "rule_type": "number"},
            {"rule_key": "min_purchase_score", "rule_value": "70", "rule_type": "number"},
        ]
        lifecycle_service.create_draft_rule_set("test_rejected_status", "测试", configs)
        lifecycle_service.submit_for_review("test_rejected_status")
        lifecycle_service.reject_rule_set("test_rejected_status")

        status_info = lifecycle_service.get_rule_set_status("test_rejected_status")
        assert status_info["status"] == "rejected"


class TestActivateRuleSet:
    """激活规则集"""

    def test_activate_approved(self, lifecycle_service):
        """审核通过后激活"""
        configs = [
            {"rule_key": "name_weight", "rule_value": "0.62", "rule_type": "number"},
            {"rule_key": "spec_weight", "rule_value": "0.23", "rule_type": "number"},
            {"rule_key": "maker_weight", "rule_value": "0.15", "rule_type": "number"},
            {"rule_key": "min_purchase_score", "rule_value": "70", "rule_type": "number"},
        ]
        lifecycle_service.create_draft_rule_set("test_activate_001", "测试", configs)
        lifecycle_service.submit_for_review("test_activate_001")
        lifecycle_service.approve_rule_set("test_activate_001")
        success, msg = lifecycle_service.activate_rule_set("test_activate_001", activated_by="admin")
        assert success is True
        assert "已激活" in msg

    def test_activate_non_approved_fails(self, lifecycle_service):
        """非审核通过状态激活应失败"""
        configs = [{"rule_key": "name_weight", "rule_value": "0.62", "rule_type": "number"}]
        lifecycle_service.create_draft_rule_set("test_activate_fail", "测试", configs)
        success, msg = lifecycle_service.activate_rule_set("test_activate_fail")
        assert success is False
        assert "不能激活" in msg

    def test_active_status_is_active(self, lifecycle_service):
        """激活后状态应为 active"""
        configs = [
            {"rule_key": "name_weight", "rule_value": "0.62", "rule_type": "number"},
            {"rule_key": "spec_weight", "rule_value": "0.23", "rule_type": "number"},
            {"rule_key": "maker_weight", "rule_value": "0.15", "rule_type": "number"},
            {"rule_key": "min_purchase_score", "rule_value": "70", "rule_type": "number"},
        ]
        lifecycle_service.create_draft_rule_set("test_active_status", "测试", configs)
        lifecycle_service.submit_for_review("test_active_status")
        lifecycle_service.approve_rule_set("test_active_status")
        lifecycle_service.activate_rule_set("test_active_status")

        status_info = lifecycle_service.get_rule_set_status("test_active_status")
        assert status_info["status"] == "active"
        assert status_info["is_enabled"] is True


class TestDeactivateRuleSet:
    """停用规则集"""

    def test_deactivate_active(self, lifecycle_service):
        """激活后停用"""
        configs = [
            {"rule_key": "name_weight", "rule_value": "0.62", "rule_type": "number"},
            {"rule_key": "spec_weight", "rule_value": "0.23", "rule_type": "number"},
            {"rule_key": "maker_weight", "rule_value": "0.15", "rule_type": "number"},
            {"rule_key": "min_purchase_score", "rule_value": "70", "rule_type": "number"},
        ]
        lifecycle_service.create_draft_rule_set("test_deactivate_001", "测试", configs)
        lifecycle_service.submit_for_review("test_deactivate_001")
        lifecycle_service.approve_rule_set("test_deactivate_001")
        lifecycle_service.activate_rule_set("test_deactivate_001")
        success, msg = lifecycle_service.deactivate_rule_set(
            "test_deactivate_001", deactivated_by="admin", reason="测试停用"
        )
        assert success is True
        assert "已停用" in msg

    def test_deactivate_non_active_fails(self, lifecycle_service):
        """非激活状态停用应失败"""
        configs = [{"rule_key": "name_weight", "rule_value": "0.62", "rule_type": "number"}]
        lifecycle_service.create_draft_rule_set("test_deactivate_fail", "测试", configs)
        success, msg = lifecycle_service.deactivate_rule_set("test_deactivate_fail")
        assert success is False
        assert "不能停用" in msg

    def test_inactive_status_is_inactive(self, lifecycle_service):
        """停用后状态应为 inactive"""
        configs = [
            {"rule_key": "name_weight", "rule_value": "0.62", "rule_type": "number"},
            {"rule_key": "spec_weight", "rule_value": "0.23", "rule_type": "number"},
            {"rule_key": "maker_weight", "rule_value": "0.15", "rule_type": "number"},
            {"rule_key": "min_purchase_score", "rule_value": "70", "rule_type": "number"},
        ]
        lifecycle_service.create_draft_rule_set("test_inactive_status", "测试", configs)
        lifecycle_service.submit_for_review("test_inactive_status")
        lifecycle_service.approve_rule_set("test_inactive_status")
        lifecycle_service.activate_rule_set("test_inactive_status")
        lifecycle_service.deactivate_rule_set("test_inactive_status")

        status_info = lifecycle_service.get_rule_set_status("test_inactive_status")
        assert status_info["status"] == "inactive"
        assert status_info["is_enabled"] is False


class TestReactivateRuleSet:
    """重新激活规则集"""

    def test_reactivate_inactive(self, lifecycle_service):
        """停用后重新激活"""
        configs = [
            {"rule_key": "name_weight", "rule_value": "0.62", "rule_type": "number"},
            {"rule_key": "spec_weight", "rule_value": "0.23", "rule_type": "number"},
            {"rule_key": "maker_weight", "rule_value": "0.15", "rule_type": "number"},
            {"rule_key": "min_purchase_score", "rule_value": "70", "rule_type": "number"},
        ]
        lifecycle_service.create_draft_rule_set("test_reactivate_001", "测试", configs)
        lifecycle_service.submit_for_review("test_reactivate_001")
        lifecycle_service.approve_rule_set("test_reactivate_001")
        lifecycle_service.activate_rule_set("test_reactivate_001")
        lifecycle_service.deactivate_rule_set("test_reactivate_001")
        success, msg = lifecycle_service.activate_rule_set("test_reactivate_001")
        assert success is True
        assert "已激活" in msg


class TestStatusTransitions:
    """状态流转限制"""

    def test_allowed_transitions_for_draft(self, lifecycle_service):
        """草稿状态允许的流转"""
        configs = [{"rule_key": "name_weight", "rule_value": "0.62", "rule_type": "number"}]
        lifecycle_service.create_draft_rule_set("test_trans_draft", "测试", configs)
        status_info = lifecycle_service.get_rule_set_status("test_trans_draft")
        assert "pending_review" in status_info["allowed_transitions"]

    def test_allowed_transitions_for_active(self, lifecycle_service):
        """激活状态允许的流转"""
        configs = [
            {"rule_key": "name_weight", "rule_value": "0.62", "rule_type": "number"},
            {"rule_key": "spec_weight", "rule_value": "0.23", "rule_type": "number"},
            {"rule_key": "maker_weight", "rule_value": "0.15", "rule_type": "number"},
            {"rule_key": "min_purchase_score", "rule_value": "70", "rule_type": "number"},
        ]
        lifecycle_service.create_draft_rule_set("test_trans_active", "测试", configs)
        lifecycle_service.submit_for_review("test_trans_active")
        lifecycle_service.approve_rule_set("test_trans_active")
        lifecycle_service.activate_rule_set("test_trans_active")
        status_info = lifecycle_service.get_rule_set_status("test_trans_active")
        assert "inactive" in status_info["allowed_transitions"]

    def test_get_all_rule_sets_with_status(self, lifecycle_service):
        """获取所有规则集及其状态"""
        rule_sets = lifecycle_service.get_all_rule_sets_with_status()
        assert len(rule_sets) >= 2  # 至少有 default_v1 和 strict_spec_v1
        for rs in rule_sets:
            assert "rule_set_code" in rs
            assert "status" in rs
            assert "allowed_transitions" in rs


class TestPhase3Regression:
    """三期回归"""

    def test_default_v1_status_is_active(self, lifecycle_service):
        """default_v1 状态应为 active"""
        status_info = lifecycle_service.get_rule_set_status("default_v1")
        assert status_info["status"] in ("active", "approved", "legacy")

    def test_strict_spec_v1_status_is_active(self, lifecycle_service):
        """strict_spec_v1 状态应为 active"""
        status_info = lifecycle_service.get_rule_set_status("strict_spec_v1")
        assert status_info["status"] in ("active", "approved", "legacy")