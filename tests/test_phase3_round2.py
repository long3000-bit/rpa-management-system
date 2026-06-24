"""
三期第二阶段测试 - 规则选择服务与批次规则字段
验证：
1. 批次规则字段迁移
2. RuleSelectionService 规则解析
3. 规则选择保存到批次
4. 快照生成使用实际规则集
5. UI规则选择控件
"""
import json
import os
import tempfile
import pytest
from pathlib import Path

from app.storage.database import Database
from app.core.rule_snapshot_service import RuleSnapshotService
from app.core.rule_selection_service import RuleSelectionService
from app.core.smart_purchase_service import SmartPurchaseService


@pytest.fixture
def db(tmp_path):
    """创建临时数据库"""
    db_path = str(tmp_path / "test_phase3_round2.db")
    database = Database(db_path)
    database.initialize()
    # SmartPurchaseService._ensure_tables() 创建 smart_purchase_batches 表
    sps = SmartPurchaseService(database)
    del sps
    yield database
    database.close()


@pytest.fixture
def snapshot_service(db):
    return RuleSnapshotService(db)


@pytest.fixture
def selection_service(db):
    return RuleSelectionService(db)


@pytest.fixture
def purchase_service(db):
    return SmartPurchaseService(db)


class TestBatchRuleFieldsMigration:
    """批次规则字段迁移"""

    def test_batch_table_has_rule_fields(self, db):
        """批次表应包含规则选择字段"""
        conn = db.get_connection()
        cursor = conn.cursor()
        cursor.execute("PRAGMA table_info(smart_purchase_batches)")
        columns = {row["name"] for row in cursor.fetchall()}

        expected_fields = [
            "rule_set_code", "rule_set_version", "rule_select_mode",
            "rule_select_reason", "rule_snapshot_id", "rule_selected_by",
            "rule_selected_at"
        ]
        for field in expected_fields:
            assert field in columns, f"缺少字段: {field}"

    def test_batch_rule_fields_default_values(self, db, purchase_service):
        """新建批次的规则字段应有默认值"""
        # 创建一个测试批次
        conn = db.get_connection()
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO smart_purchase_batches (batch_id, batch_name, created_at)
            VALUES (?, ?, ?)
        ''', ("test_batch_001", "测试批次", "2026-01-01T00:00:00"))
        conn.commit()

        cursor.execute("SELECT * FROM smart_purchase_batches WHERE batch_id = ?", ("test_batch_001",))
        row = cursor.fetchone()

        assert row["rule_set_code"] is None  # 未选择时为NULL
        assert row["rule_select_mode"] == "default"  # 默认模式
        assert row["rule_snapshot_id"] is None

    def test_migration_idempotent(self, tmp_path):
        """迁移应幂等"""
        db_path = str(tmp_path / "test_idempotent.db")
        db1 = Database(db_path)
        db1.initialize()
        # 需要初始化 SmartPurchaseService 来创建 smart_purchase_batches 表
        sps1 = SmartPurchaseService(db1)
        del sps1
        db1.close()

        # 再次初始化
        db2 = Database(db_path)
        db2.initialize()
        sps2 = SmartPurchaseService(db2)
        del sps2
        conn = db2.get_connection()
        cursor = conn.cursor()
        cursor.execute("PRAGMA table_info(smart_purchase_batches)")
        columns = {row["name"] for row in cursor.fetchall()}
        db2.close()

        assert "rule_set_code" in columns
        assert "rule_select_mode" in columns


class TestRuleSelectionService:
    """规则选择服务"""

    def test_resolve_default_rule_set(self, selection_service):
        """默认规则解析：应返回 is_default=1 的规则集"""
        result = selection_service.resolve_rule_set("test_batch")
        assert result["resolved"] is True
        assert result["rule_set_code"] == "default_v1"
        assert result["rule_select_mode"] == "default"

    def test_resolve_manual_rule_set(self, selection_service):
        """手工指定规则集"""
        result = selection_service.resolve_rule_set("test_batch", manual_rule_set_code="strict_spec_v1")
        assert result["resolved"] is True
        assert result["rule_set_code"] == "strict_spec_v1"
        assert result["rule_select_mode"] == "manual"

    def test_resolve_invalid_manual_rule_set_falls_back(self, selection_service):
        """手工指定无效规则集应回退到默认"""
        result = selection_service.resolve_rule_set("test_batch", manual_rule_set_code="nonexistent_v1")
        # 应该回退到默认规则
        assert result["rule_set_code"] == "default_v1"
        assert result["rule_select_mode"] == "default"

    def test_resolve_disabled_rule_set_falls_back(self, selection_service, db):
        """禁用的规则集应回退"""
        conn = db.get_connection()
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE smart_match_rule_sets SET is_enabled = 0 WHERE rule_set_code = 'strict_spec_v1'"
        )
        conn.commit()

        result = selection_service.resolve_rule_set("test_batch", manual_rule_set_code="strict_spec_v1")
        assert result["resolved"] is False or result["rule_select_mode"] != "manual"

        # 恢复
        cursor.execute(
            "UPDATE smart_match_rule_sets SET is_enabled = 1 WHERE rule_set_code = 'strict_spec_v1'"
        )
        conn.commit()

    def test_save_and_get_rule_selection(self, selection_service, db):
        """保存并获取规则选择"""
        # 创建测试批次
        conn = db.get_connection()
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO smart_purchase_batches (batch_id, batch_name, created_at)
            VALUES (?, ?, ?)
        ''', ("test_batch_save", "测试批次", "2026-01-01T00:00:00"))
        conn.commit()

        # 保存规则选择
        selection = {
            "rule_set_code": "strict_spec_v1",
            "rule_set_version": "v1.0.0",
            "rule_select_mode": "manual",
            "rule_select_reason": "测试手工选择",
            "resolved": True,
        }
        result = selection_service.save_rule_selection_to_batch("test_batch_save", selection, selected_by="admin")
        assert result is True

        # 获取规则集代码
        code = selection_service.get_batch_rule_set_code("test_batch_save")
        assert code == "strict_spec_v1"

    def test_get_available_rule_sets(self, selection_service):
        """获取可用规则集列表"""
        rule_sets = selection_service.get_available_rule_sets()
        assert len(rule_sets) >= 2  # 至少有 default_v1 和 strict_spec_v1

        codes = [rs["rule_set_code"] for rs in rule_sets]
        assert "default_v1" in codes
        assert "strict_spec_v1" in codes

        # default_v1 应标记为默认
        default_rs = next(rs for rs in rule_sets if rs["rule_set_code"] == "default_v1")
        assert default_rs["is_default"] is True


class TestSnapshotWithActualRuleSet:
    """快照生成使用实际规则集"""

    def test_snapshot_uses_default_rule_set(self, snapshot_service, selection_service, db):
        """默认规则集生成快照"""
        # 创建测试批次
        conn = db.get_connection()
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO smart_purchase_batches (batch_id, batch_name, created_at)
            VALUES (?, ?, ?)
        ''', ("test_batch_default", "测试批次", "2026-01-01T00:00:00"))
        conn.commit()

        # 解析规则集
        selection = selection_service.resolve_rule_set("test_batch_default")
        rule_set_code = selection["rule_set_code"]

        # 生成快照
        snapshot_id, error = snapshot_service.generate_rule_snapshot("test_batch_default", rule_set_code)
        assert snapshot_id != ""
        assert error == ""

        # 验证快照使用正确的规则集
        snapshot = snapshot_service.get_rule_snapshot(snapshot_id)
        assert snapshot["rule_set_code"] == "default_v1"

    def test_snapshot_uses_strict_spec_rule_set(self, snapshot_service, selection_service, db):
        """strict_spec_v1 规则集生成快照"""
        # 创建测试批次
        conn = db.get_connection()
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO smart_purchase_batches (batch_id, batch_name, created_at)
            VALUES (?, ?, ?)
        ''', ("test_batch_strict", "测试批次", "2026-01-01T00:00:00"))
        conn.commit()

        # 解析规则集
        selection = selection_service.resolve_rule_set("test_batch_strict", manual_rule_set_code="strict_spec_v1")
        rule_set_code = selection["rule_set_code"]

        # 生成快照
        snapshot_id, error = snapshot_service.generate_rule_snapshot("test_batch_strict", rule_set_code)
        assert snapshot_id != ""

        # 验证快照使用正确的规则集
        snapshot = snapshot_service.get_rule_snapshot(snapshot_id)
        assert snapshot["rule_set_code"] == "strict_spec_v1"

        # 验证快照内容包含规格冲突阻断
        config = json.loads(snapshot["snapshot_json"])
        assert config["thresholds"]["spec_conflict_block"] in ("1", True, 1)

    def test_snapshot_default_parameter_uses_default_rule(self, snapshot_service, db):
        """不传 rule_set_code 时应使用默认规则集"""
        # 创建测试批次
        conn = db.get_connection()
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO smart_purchase_batches (batch_id, batch_name, created_at)
            VALUES (?, ?, ?)
        ''', ("test_batch_no_code", "测试批次", "2026-01-01T00:00:00"))
        conn.commit()

        # 不传 rule_set_code
        snapshot_id, error = snapshot_service.generate_rule_snapshot("test_batch_no_code")
        assert snapshot_id != ""

        snapshot = snapshot_service.get_rule_snapshot(snapshot_id)
        assert snapshot["rule_set_code"] == "default_v1"

    def test_different_rulesets_produce_different_snapshots(self, snapshot_service, db):
        """不同规则集应产生不同快照"""
        # 创建两个测试批次
        conn = db.get_connection()
        cursor = conn.cursor()
        for batch_id in ["batch_a", "batch_b"]:
            cursor.execute('''
                INSERT INTO smart_purchase_batches (batch_id, batch_name, created_at)
                VALUES (?, ?, ?)
            ''', (batch_id, f"批次{batch_id}", "2026-01-01T00:00:00"))
        conn.commit()

        # 分别用不同规则集生成快照
        snap_a, _ = snapshot_service.generate_rule_snapshot("batch_a", "default_v1")
        snap_b, _ = snapshot_service.generate_rule_snapshot("batch_b", "strict_spec_v1")

        config_a = json.loads(snapshot_service.get_rule_snapshot(snap_a)["snapshot_json"])
        config_b = json.loads(snapshot_service.get_rule_snapshot(snap_b)["snapshot_json"])

        # spec_conflict_block 应不同（default_v1=0, strict_spec_v1=1）
        assert config_a["thresholds"]["spec_conflict_block"] != config_b["thresholds"]["spec_conflict_block"]

        # ruleSetCode 应不同
        assert config_a["ruleSetCode"] == "default_v1"
        assert config_b["ruleSetCode"] == "strict_spec_v1"


class TestBatchRuleSelectionIntegration:
    """批次规则选择集成测试"""

    def test_full_flow_default_rule(self, selection_service, snapshot_service, db):
        """完整流程：默认规则选择 → 快照生成 → 保存到批次"""
        batch_id = "test_full_default"
        conn = db.get_connection()
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO smart_purchase_batches (batch_id, batch_name, created_at)
            VALUES (?, ?, ?)
        ''', (batch_id, "完整流程测试", "2026-01-01T00:00:00"))
        conn.commit()

        # 1. 解析规则集
        selection = selection_service.resolve_rule_set(batch_id)
        assert selection["resolved"] is True

        # 2. 保存到批次
        selection_service.save_rule_selection_to_batch(batch_id, selection, selected_by="admin")

        # 3. 生成快照
        snapshot_id, error = snapshot_service.generate_rule_snapshot(batch_id, selection["rule_set_code"])
        assert snapshot_id != ""

        # 4. 回写快照ID到批次
        cursor.execute(
            "UPDATE smart_purchase_batches SET rule_snapshot_id = ? WHERE batch_id = ?",
            (snapshot_id, batch_id)
        )
        conn.commit()

        # 5. 验证批次记录
        cursor.execute("SELECT * FROM smart_purchase_batches WHERE batch_id = ?", (batch_id,))
        row = cursor.fetchone()
        assert row["rule_set_code"] == "default_v1"
        assert row["rule_select_mode"] == "default"
        assert row["rule_snapshot_id"] == snapshot_id
        assert row["rule_selected_by"] == "admin"

    def test_full_flow_manual_rule(self, selection_service, snapshot_service, db):
        """完整流程：手工选择规则 → 快照生成 → 保存到批次"""
        batch_id = "test_full_manual"
        conn = db.get_connection()
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO smart_purchase_batches (batch_id, batch_name, created_at)
            VALUES (?, ?, ?)
        ''', (batch_id, "手工选择测试", "2026-01-01T00:00:00"))
        conn.commit()

        # 1. 手工选择规则
        selection = selection_service.resolve_rule_set(batch_id, manual_rule_set_code="strict_spec_v1")
        assert selection["resolved"] is True
        assert selection["rule_select_mode"] == "manual"

        # 2. 保存到批次
        selection_service.save_rule_selection_to_batch(batch_id, selection, selected_by="admin")

        # 3. 生成快照
        snapshot_id, error = snapshot_service.generate_rule_snapshot(batch_id, selection["rule_set_code"])
        assert snapshot_id != ""

        # 4. 验证快照使用 strict_spec_v1
        snapshot = snapshot_service.get_rule_snapshot(snapshot_id)
        assert snapshot["rule_set_code"] == "strict_spec_v1"

    def test_batch_rule_set_code_persists(self, selection_service, db):
        """批次规则集代码持久化"""
        batch_id = "test_persist"
        conn = db.get_connection()
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO smart_purchase_batches (batch_id, batch_name, created_at)
            VALUES (?, ?, ?)
        ''', (batch_id, "持久化测试", "2026-01-01T00:00:00"))
        conn.commit()

        # 保存规则选择
        selection = selection_service.resolve_rule_set(batch_id, manual_rule_set_code="strict_spec_v1")
        selection_service.save_rule_selection_to_batch(batch_id, selection)

        # 重新获取
        code = selection_service.get_batch_rule_set_code(batch_id)
        assert code == "strict_spec_v1"

        # 模拟第二次采购，应使用已保存的规则
        selection2 = selection_service.resolve_rule_set(batch_id, manual_rule_set_code=code)
        assert selection2["rule_set_code"] == "strict_spec_v1"


class TestPhase2Regression:
    """二期回归测试"""

    def test_snapshot_generation_still_works(self, snapshot_service, db):
        """快照生成仍正常"""
        snapshot_id, error = snapshot_service.generate_rule_snapshot("regression_test")
        assert snapshot_id != ""
        assert error == ""

    def test_node_config_still_has_required_fields(self, snapshot_service, db):
        """Node配置仍包含必要字段"""
        snapshot_id, _ = snapshot_service.generate_rule_snapshot("regression_node_test")
        config = snapshot_service.get_rule_config_for_node(snapshot_id)
        assert "nameWeight" in config
        assert "specWeight" in config
        assert "makerWeight" in config
        assert "specConflictBlock" in config

    def test_dual_table_still_works(self, db):
        """双表一致性仍正常"""
        conn = db.get_connection()
        cursor = conn.cursor()
        # 验证双表存在
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='purchase_candidate_scores'")
        assert cursor.fetchone() is not None
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='smart_purchase_candidates'")
        assert cursor.fetchone() is not None
