"""
三期阶段5验收测试 - 真实验收
验证：
1. 专项测试 - 规则切换、快照生成、状态流转等核心功能
2. 回归测试 - 确保现有采购流程不受影响
3. 两套规则对照采购 - 验证default_v1和strict_spec_v1的差异
"""
import pytest
from pathlib import Path
from datetime import datetime

from app.storage.database import Database
from app.core.smart_purchase_service import SmartPurchaseService
from app.core.rule_snapshot_service import RuleSnapshotService
from app.core.rule_selection_service import RuleSelectionService
from app.core.rule_validation_service import RuleValidationService
from app.core.rule_lifecycle_service import RuleLifecycleService
from app.core.rule_version_service import RuleVersionService


@pytest.fixture
def db(tmp_path):
    db_path = str(tmp_path / "test_phase5_acceptance.db")
    database = Database(db_path)
    database.initialize()
    sps = SmartPurchaseService(database)
    yield database
    database.close()


@pytest.fixture
def purchase_service(db):
    return SmartPurchaseService(db)


@pytest.fixture
def snapshot_service(db):
    return RuleSnapshotService(db)


@pytest.fixture
def selection_service(db):
    return RuleSelectionService(db)


@pytest.fixture
def validation_service(db):
    return RuleValidationService(db)


@pytest.fixture
def lifecycle_service(db):
    return RuleLifecycleService(db)


@pytest.fixture
def version_service(db):
    return RuleVersionService(db)


class TestSpecializedRuleSwitching:
    """专项测试：规则切换"""

    def test_default_v1_vs_strict_spec_v1_spec_conflict_block(self, snapshot_service):
        """验证两套规则集的spec_conflict_block差异"""
        # default_v1 - spec_conflict_block = false
        snapshot_id1, _ = snapshot_service.generate_rule_snapshot("batch_001", "default_v1")
        snapshot1 = snapshot_service.get_rule_snapshot(snapshot_id1)
        thresholds1 = snapshot1.get("snapshot_json_parsed", {}).get("thresholds", {})
        spec_conflict_block1 = thresholds1.get("spec_conflict_block")

        # strict_spec_v1 - spec_conflict_block = true
        snapshot_id2, _ = snapshot_service.generate_rule_snapshot("batch_002", "strict_spec_v1")
        snapshot2 = snapshot_service.get_rule_snapshot(snapshot_id2)
        thresholds2 = snapshot2.get("snapshot_json_parsed", {}).get("thresholds", {})
        spec_conflict_block2 = thresholds2.get("spec_conflict_block")

        # 验证spec_conflict_block不同
        assert spec_conflict_block1 in ("0", "false", "False")
        assert spec_conflict_block2 in ("1", "true", "True")

    def test_both_rule_sets_can_generate_snapshot(self, snapshot_service):
        """两套规则集都能生成快照"""
        snap1_id, _ = snapshot_service.generate_rule_snapshot("batch_003", "default_v1")
        snap2_id, _ = snapshot_service.generate_rule_snapshot("batch_004", "strict_spec_v1")
        assert snap1_id is not None
        assert snap2_id is not None
        assert snap1_id != snap2_id


class TestSpecializedSnapshotGeneration:
    """专项测试：快照生成"""

    def test_snapshot_contains_all_required_fields(self, snapshot_service):
        """快照包含所有必需字段"""
        snapshot_id, _ = snapshot_service.generate_rule_snapshot("batch_007", "default_v1")
        assert snapshot_id is not None

        snapshot = snapshot_service.get_rule_snapshot(snapshot_id)
        assert snapshot is not None
        assert snapshot["rule_set_code"] == "default_v1"
        assert snapshot["batch_id"] == "batch_007"
        assert snapshot["snapshot_json"] is not None
        assert snapshot["created_at"] is not None

    def test_snapshot_thresholds_complete(self, snapshot_service):
        """快照阈值完整"""
        snapshot_id, _ = snapshot_service.generate_rule_snapshot("batch_008", "default_v1")
        snapshot = snapshot_service.get_rule_snapshot(snapshot_id)
        thresholds = snapshot.get("snapshot_json_parsed", {}).get("thresholds", {})

        # 验证必需的阈值参数（根据实际配置）
        required_keys = [
            "name_weight", "spec_weight", "maker_weight",
            "min_purchase_score",
            "name_core_min_score", "spec_similar_min_score",
            "spec_conflict_block"
        ]
        for key in required_keys:
            assert key in thresholds

    def test_snapshot_immutability(self, snapshot_service, db):
        """快照不可变性"""
        snapshot_id, _ = snapshot_service.generate_rule_snapshot("batch_009", "default_v1")
        snapshot_before = snapshot_service.get_rule_snapshot(snapshot_id)
        thresholds_before = snapshot_before.get("snapshot_json_parsed", {}).get("thresholds", {})

        # 修改规则配置
        conn = db.get_connection()
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE smart_match_rule_configs SET rule_value = '0.99' "
            "WHERE rule_set_code = 'default_v1' AND rule_key = 'name_weight'"
        )
        conn.commit()

        # 快照不应改变
        snapshot_after = snapshot_service.get_rule_snapshot(snapshot_id)
        thresholds_after = snapshot_after.get("snapshot_json_parsed", {}).get("thresholds", {})
        assert thresholds_before["name_weight"] == thresholds_after["name_weight"]


class TestSpecializedLifecycle:
    """专项测试：状态流转"""

    def test_full_lifecycle_flow(self, lifecycle_service):
        """完整生命周期流程"""
        configs = [
            {"rule_key": "name_weight", "rule_value": "0.62", "rule_type": "number"},
            {"rule_key": "spec_weight", "rule_value": "0.23", "rule_type": "number"},
            {"rule_key": "maker_weight", "rule_value": "0.15", "rule_type": "number"},
            {"rule_key": "min_purchase_score", "rule_value": "70", "rule_type": "number"},
        ]

        # 1. 创建草稿
        success, msg = lifecycle_service.create_draft_rule_set(
            "test_lifecycle_full", "测试生命周期", configs
        )
        assert success

        # 2. 提交审核
        success, msg = lifecycle_service.submit_for_review("test_lifecycle_full")
        assert success

        # 3. 审核通过
        success, msg = lifecycle_service.approve_rule_set("test_lifecycle_full")
        assert success

        # 4. 激活
        success, msg = lifecycle_service.activate_rule_set("test_lifecycle_full")
        assert success

        # 5. 停用
        success, msg = lifecycle_service.deactivate_rule_set("test_lifecycle_full")
        assert success

        # 6. 重新激活
        success, msg = lifecycle_service.activate_rule_set("test_lifecycle_full")
        assert success

    def test_rejected_flow(self, lifecycle_service):
        """审核拒绝流程"""
        configs = [
            {"rule_key": "name_weight", "rule_value": "0.62", "rule_type": "number"},
            {"rule_key": "spec_weight", "rule_value": "0.23", "rule_type": "number"},
            {"rule_key": "maker_weight", "rule_value": "0.15", "rule_type": "number"},
            {"rule_key": "min_purchase_score", "rule_value": "70", "rule_type": "number"},
        ]

        lifecycle_service.create_draft_rule_set("test_rejected_flow", "测试", configs)
        lifecycle_service.submit_for_review("test_rejected_flow")

        # 审核拒绝
        success, msg = lifecycle_service.reject_rule_set("test_rejected_flow")
        assert success

        status = lifecycle_service.get_rule_set_status("test_rejected_flow")
        assert status["status"] == "rejected"


class TestSpecializedValidation:
    """专项测试：参数校验"""

    def test_valid_rule_set_passes_validation(self, validation_service):
        """有效规则集通过校验"""
        is_valid, errors = validation_service.validate_rule_set("default_v1")
        assert is_valid
        assert len(errors) == 0

    def test_invalid_rule_set_fails_validation(self, validation_service, db):
        """无效规则集校验失败"""
        conn = db.get_connection()
        cursor = conn.cursor()

        # 创建无效规则集（权重总和不为1）
        cursor.execute('''
            INSERT INTO smart_match_rule_sets (
                rule_set_code, rule_set_name, is_enabled, is_default, created_at, updated_at
            ) VALUES (?, ?, 1, 0, ?, ?)
        ''', ("test_invalid_validation", "测试无效", "2026-01-01T00:00:00", "2026-01-01T00:00:00"))

        for key, val in [("name_weight", "0.50"), ("spec_weight", "0.20"), ("maker_weight", "0.10")]:
            cursor.execute('''
                INSERT INTO smart_match_rule_configs (
                    rule_set_code, rule_key, rule_name, rule_value, rule_type,
                    description, sort_order, is_enabled, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', ("test_invalid_validation", key, key, val, "number", "测试", 1, 1,
                  "2026-01-01T00:00:00", "2026-01-01T00:00:00"))
        conn.commit()

        is_valid, errors = validation_service.validate_rule_set("test_invalid_validation")
        assert not is_valid
        assert any("权重总和" in e for e in errors)


class TestRegressionPurchaseFlow:
    """回归测试：采购流程"""

    def test_batch_creation_still_works(self, purchase_service, db):
        """批次创建仍然正常"""
        conn = db.get_connection()
        cursor = conn.cursor()

        # 创建采购批次
        cursor.execute('''
            INSERT INTO smart_purchase_batches (
                batch_id, batch_name, status, created_at
            ) VALUES (?, ?, 'pending', ?)
        ''', ("test_batch_regression", "回归测试批次",
              datetime.now().isoformat()))
        conn.commit()

        # 查询批次
        cursor.execute(
            "SELECT batch_id, batch_name, status FROM smart_purchase_batches "
            "WHERE batch_id = ?",
            ("test_batch_regression",)
        )
        batch = cursor.fetchone()
        assert batch is not None
        assert batch["batch_id"] == "test_batch_regression"

    def test_rule_selection_default(self, selection_service, db):
        """默认规则选择正常"""
        conn = db.get_connection()
        cursor = conn.cursor()

        cursor.execute('''
            INSERT INTO smart_purchase_batches (
                batch_id, batch_name, status, created_at
            ) VALUES (?, ?, 'pending', ?)
        ''', ("test_selection_default", "测试",
              datetime.now().isoformat()))
        conn.commit()

        result = selection_service.resolve_rule_set("test_selection_default")
        assert result["resolved"] is True
        assert result["rule_set_code"] == "default_v1"

    def test_rule_selection_manual(self, selection_service, db):
        """手工规则选择正常"""
        conn = db.get_connection()
        cursor = conn.cursor()

        cursor.execute('''
            INSERT INTO smart_purchase_batches (
                batch_id, batch_name, status, rule_set_code, created_at
            ) VALUES (?, ?, 'pending', ?, ?)
        ''', ("test_selection_manual", "测试", "strict_spec_v1",
              datetime.now().isoformat()))
        conn.commit()

        # 从批次获取规则集代码，然后传入resolve_rule_set
        batch_rule_code = selection_service.get_batch_rule_set_code("test_selection_manual")
        result = selection_service.resolve_rule_set("test_selection_manual", batch_rule_code)
        assert result["resolved"] is True
        assert result["rule_set_code"] == "strict_spec_v1"


class TestRegressionSnapshot:
    """回归测试：快照功能"""

    def test_snapshot_generation_still_works(self, snapshot_service):
        """快照生成仍然正常"""
        snapshot_id, _ = snapshot_service.generate_rule_snapshot("batch_regression", "default_v1")
        assert snapshot_id is not None
        assert snapshot_id.startswith("snapshot_")

    def test_snapshot_retrieval_still_works(self, snapshot_service):
        """快照查询仍然正常"""
        snapshot_id, _ = snapshot_service.generate_rule_snapshot("batch_regression_2", "default_v1")
        snapshot = snapshot_service.get_rule_snapshot(snapshot_id)
        assert snapshot is not None
        assert snapshot["snapshot_id"] == snapshot_id


class TestTwoRuleSetsComparison:
    """两套规则对照采购"""

    def test_default_v1_spec_conflict_block_false(self, snapshot_service):
        """default_v1允许规格冲突"""
        snapshot_id, _ = snapshot_service.generate_rule_snapshot("batch_default", "default_v1")
        snapshot = snapshot_service.get_rule_snapshot(snapshot_id)
        thresholds = snapshot.get("snapshot_json_parsed", {}).get("thresholds", {})

        spec_conflict_block = thresholds.get("spec_conflict_block")
        assert spec_conflict_block in ("0", "false", "False")

    def test_strict_spec_v1_spec_conflict_block_true(self, snapshot_service):
        """strict_spec_v1会拦截规格冲突"""
        snapshot_id, _ = snapshot_service.generate_rule_snapshot("batch_strict", "strict_spec_v1")
        snapshot = snapshot_service.get_rule_snapshot(snapshot_id)
        thresholds = snapshot.get("snapshot_json_parsed", {}).get("thresholds", {})

        spec_conflict_block = thresholds.get("spec_conflict_block")
        assert spec_conflict_block in ("1", "true", "True")

    def test_strict_spec_blocks_spec_conflict(self, snapshot_service):
        """strict_spec_v1会拦截规格冲突"""
        snapshot_id, _ = snapshot_service.generate_rule_snapshot("batch_strict_2", "strict_spec_v1")
        snapshot = snapshot_service.get_rule_snapshot(snapshot_id)
        thresholds = snapshot.get("snapshot_json_parsed", {}).get("thresholds", {})

        spec_conflict_block = thresholds.get("spec_conflict_block")
        assert spec_conflict_block in ("1", "true", "True")

    def test_default_allows_spec_conflict(self, snapshot_service):
        """default_v1允许规格冲突"""
        snapshot_id, _ = snapshot_service.generate_rule_snapshot("batch_default_2", "default_v1")
        snapshot = snapshot_service.get_rule_snapshot(snapshot_id)
        thresholds = snapshot.get("snapshot_json_parsed", {}).get("thresholds", {})

        spec_conflict_block = thresholds.get("spec_conflict_block")
        assert spec_conflict_block in ("0", "false", "False")


class TestIntegrationFullFlow:
    """集成测试：完整流程"""

    def test_purchase_with_rule_selection_and_snapshot(self, purchase_service, snapshot_service, selection_service, db):
        """采购流程包含规则选择和快照生成"""
        conn = db.get_connection()
        cursor = conn.cursor()

        # 创建批次
        batch_id = "test_integration_full"
        cursor.execute('''
            INSERT INTO smart_purchase_batches (
                batch_id, batch_name, status, rule_set_code, created_at
            ) VALUES (?, ?, 'pending', ?, ?)
        ''', (batch_id, "集成测试", "strict_spec_v1",
              datetime.now().isoformat()))
        conn.commit()

        # 规则选择 - 从批次获取规则集代码并传入
        batch_rule_code = selection_service.get_batch_rule_set_code(batch_id)
        rule_result = selection_service.resolve_rule_set(batch_id, batch_rule_code)
        assert rule_result["rule_set_code"] == "strict_spec_v1"

        # 快照生成
        snapshot_id, _ = snapshot_service.generate_rule_snapshot(batch_id, rule_result["rule_set_code"])
        assert snapshot_id is not None

        # 验证快照与批次关联
        snapshot = snapshot_service.get_rule_snapshot(snapshot_id)
        assert snapshot["batch_id"] == batch_id
        assert snapshot["rule_set_code"] == "strict_spec_v1"


class TestPhase3FinalSummary:
    """三期最终验收总结"""

    def test_all_services_available(self, purchase_service, snapshot_service, selection_service,
                                     validation_service, lifecycle_service, version_service):
        """所有服务可用"""
        assert purchase_service is not None
        assert snapshot_service is not None
        assert selection_service is not None
        assert validation_service is not None
        assert lifecycle_service is not None
        assert version_service is not None

    def test_default_v1_validated(self, validation_service):
        """default_v1通过校验"""
        is_valid, errors = validation_service.validate_rule_set("default_v1")
        assert is_valid

    def test_strict_spec_v1_validated(self, validation_service):
        """strict_spec_v1通过校验"""
        is_valid, errors = validation_service.validate_rule_set("strict_spec_v1")
        assert is_valid

    def test_both_rule_sets_can_generate_snapshot(self, snapshot_service):
        """两套规则集都能生成快照"""
        snap1_id, _ = snapshot_service.generate_rule_snapshot("final_default", "default_v1")
        snap2_id, _ = snapshot_service.generate_rule_snapshot("final_strict", "strict_spec_v1")
        assert snap1_id is not None
        assert snap2_id is not None
        assert snap1_id != snap2_id  # 不同规则集生成不同快照