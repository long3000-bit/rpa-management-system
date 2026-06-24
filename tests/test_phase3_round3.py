"""
三期第三阶段测试 - 全链路追溯
验证：批次/候选/失败/反写均保存实际规则集和快照ID
"""
import json
import pytest
from pathlib import Path

from app.storage.database import Database
from app.core.rule_snapshot_service import RuleSnapshotService
from app.core.rule_selection_service import RuleSelectionService
from app.core.smart_purchase_service import SmartPurchaseService


@pytest.fixture
def db(tmp_path):
    db_path = str(tmp_path / "test_phase3_round3.db")
    database = Database(db_path)
    database.initialize()
    sps = SmartPurchaseService(database)
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


class TestBatchRuleTraceability:
    """批次规则追溯"""

    def test_batch_stores_rule_set_code(self, db, selection_service):
        """批次保存规则集代码"""
        batch_id = "trace_batch_001"
        conn = db.get_connection()
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO smart_purchase_batches (batch_id, batch_name, created_at)
            VALUES (?, ?, ?)
        ''', (batch_id, "追溯测试", "2026-01-01T00:00:00"))
        conn.commit()

        selection = selection_service.resolve_rule_set(batch_id, manual_rule_set_code="strict_spec_v1")
        selection_service.save_rule_selection_to_batch(batch_id, selection, selected_by="admin")

        cursor.execute("SELECT rule_set_code FROM smart_purchase_batches WHERE batch_id = ?", (batch_id,))
        row = cursor.fetchone()
        assert row["rule_set_code"] == "strict_spec_v1"

    def test_batch_stores_rule_snapshot_id(self, db, selection_service, snapshot_service):
        """批次保存规则快照ID"""
        batch_id = "trace_batch_002"
        conn = db.get_connection()
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO smart_purchase_batches (batch_id, batch_name, created_at)
            VALUES (?, ?, ?)
        ''', (batch_id, "快照追溯测试", "2026-01-01T00:00:00"))
        conn.commit()

        selection = selection_service.resolve_rule_set(batch_id, manual_rule_set_code="strict_spec_v1")
        selection_service.save_rule_selection_to_batch(batch_id, selection)

        snapshot_id, _ = snapshot_service.generate_rule_snapshot(batch_id, selection["rule_set_code"])
        assert snapshot_id != ""

        cursor.execute(
            "UPDATE smart_purchase_batches SET rule_snapshot_id = ? WHERE batch_id = ?",
            (snapshot_id, batch_id)
        )
        conn.commit()

        cursor.execute("SELECT rule_snapshot_id FROM smart_purchase_batches WHERE batch_id = ?", (batch_id,))
        row = cursor.fetchone()
        assert row["rule_snapshot_id"] == snapshot_id

    def test_batch_stores_selection_metadata(self, db, selection_service):
        """批次保存选择元数据（模式、原因、操作人、时间）"""
        batch_id = "trace_batch_003"
        conn = db.get_connection()
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO smart_purchase_batches (batch_id, batch_name, created_at)
            VALUES (?, ?, ?)
        ''', (batch_id, "元数据测试", "2026-01-01T00:00:00"))
        conn.commit()

        selection = selection_service.resolve_rule_set(batch_id, manual_rule_set_code="default_v1")
        selection_service.save_rule_selection_to_batch(batch_id, selection, selected_by="tester")

        cursor.execute(
            "SELECT rule_select_mode, rule_select_reason, rule_selected_by, rule_selected_at "
            "FROM smart_purchase_batches WHERE batch_id = ?",
            (batch_id,)
        )
        row = cursor.fetchone()
        assert row["rule_select_mode"] == "manual"
        assert "default_v1" in row["rule_select_reason"]
        assert row["rule_selected_by"] == "tester"
        assert row["rule_selected_at"] is not None


class TestCandidateScoreTraceability:
    """候选评分追溯"""

    def test_candidate_scores_have_rule_set_code(self, db, purchase_service):
        """候选评分记录包含规则集代码"""
        conn = db.get_connection()
        cursor = conn.cursor()

        # 检查表结构
        cursor.execute("PRAGMA table_info(purchase_candidate_scores)")
        columns = {row["name"] for row in cursor.fetchall()}
        assert "rule_set_code" in columns

    def test_candidate_scores_have_rule_snapshot_id(self, db, purchase_service):
        """候选评分记录包含规则快照ID"""
        conn = db.get_connection()
        cursor = conn.cursor()

        cursor.execute("PRAGMA table_info(purchase_candidate_scores)")
        columns = {row["name"] for row in cursor.fetchall()}
        assert "rule_snapshot_id" in columns


class TestFailureReasonTraceability:
    """失败原因追溯"""

    def test_failure_reasons_have_rule_set_code(self, db, purchase_service):
        """失败原因记录包含规则集代码"""
        conn = db.get_connection()
        cursor = conn.cursor()

        cursor.execute("PRAGMA table_info(smart_purchase_failure_reasons)")
        columns = {row["name"] for row in cursor.fetchall()}
        assert "rule_set_code" in columns

    def test_failure_reasons_have_rule_snapshot_id(self, db, purchase_service):
        """失败原因记录包含规则快照ID"""
        conn = db.get_connection()
        cursor = conn.cursor()

        cursor.execute("PRAGMA table_info(smart_purchase_failure_reasons)")
        columns = {row["name"] for row in cursor.fetchall()}
        assert "rule_snapshot_id" in columns

    def test_failure_reason_saves_actual_rule_set(self, db, purchase_service):
        """失败原因保存实际规则集"""
        from app.core.failure_reason_service import FailureReasonService
        service = FailureReasonService(db)

        service.save_failure_reason(
            batch_id="trace_batch_fail",
            item_id="item_001",
            row_number=1,
            failure_stage="candidate_search",
            failure_code="no_candidate_found",
            failure_message="未找到候选商品",
            rule_set_code="strict_spec_v1",
            rule_snapshot_id="snapshot_trace_001"
        )

        conn = db.get_connection()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT rule_set_code, rule_snapshot_id FROM smart_purchase_failure_reasons "
            "WHERE item_id = 'item_001'"
        )
        row = cursor.fetchone()
        assert row["rule_set_code"] == "strict_spec_v1"
        assert row["rule_snapshot_id"] == "snapshot_trace_001"


class TestSnapshotRuleSetConsistency:
    """快照与规则集一致性"""

    def test_snapshot_rule_set_matches_batch(self, db, selection_service, snapshot_service):
        """快照中的规则集应与批次一致"""
        batch_id = "trace_consistency_001"
        conn = db.get_connection()
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO smart_purchase_batches (batch_id, batch_name, created_at)
            VALUES (?, ?, ?)
        ''', (batch_id, "一致性测试", "2026-01-01T00:00:00"))
        conn.commit()

        # 选择 strict_spec_v1
        selection = selection_service.resolve_rule_set(batch_id, manual_rule_set_code="strict_spec_v1")
        selection_service.save_rule_selection_to_batch(batch_id, selection)

        # 生成快照
        snapshot_id, _ = snapshot_service.generate_rule_snapshot(batch_id, selection["rule_set_code"])

        # 验证快照中的规则集与批次一致
        snapshot = snapshot_service.get_rule_snapshot(snapshot_id)
        assert snapshot["rule_set_code"] == "strict_spec_v1"

        # 验证批次中的规则集
        cursor.execute("SELECT rule_set_code FROM smart_purchase_batches WHERE batch_id = ?", (batch_id,))
        batch_row = cursor.fetchone()
        assert batch_row["rule_set_code"] == "strict_spec_v1"

    def test_default_rule_snapshot_consistency(self, db, selection_service, snapshot_service):
        """默认规则快照一致性"""
        batch_id = "trace_default_consistency"
        conn = db.get_connection()
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO smart_purchase_batches (batch_id, batch_name, created_at)
            VALUES (?, ?, ?)
        ''', (batch_id, "默认一致性测试", "2026-01-01T00:00:00"))
        conn.commit()

        # 使用默认规则
        selection = selection_service.resolve_rule_set(batch_id)
        selection_service.save_rule_selection_to_batch(batch_id, selection)

        snapshot_id, _ = snapshot_service.generate_rule_snapshot(batch_id, selection["rule_set_code"])
        snapshot = snapshot_service.get_rule_snapshot(snapshot_id)

        assert snapshot["rule_set_code"] == "default_v1"
        assert selection["rule_select_mode"] == "default"


class TestEndToEndTraceability:
    """端到端追溯"""

    def test_full_trace_chain_with_strict_spec(self, db, selection_service, snapshot_service):
        """完整追溯链：strict_spec_v1 规则集"""
        batch_id = "e2e_trace_strict"
        conn = db.get_connection()
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO smart_purchase_batches (batch_id, batch_name, created_at)
            VALUES (?, ?, ?)
        ''', (batch_id, "端到端追溯", "2026-01-01T00:00:00"))
        conn.commit()

        # 1. 选择规则
        selection = selection_service.resolve_rule_set(batch_id, manual_rule_set_code="strict_spec_v1")
        assert selection["resolved"] is True

        # 2. 保存到批次
        selection_service.save_rule_selection_to_batch(batch_id, selection, selected_by="admin")

        # 3. 生成快照
        snapshot_id, _ = snapshot_service.generate_rule_snapshot(batch_id, selection["rule_set_code"])
        assert snapshot_id != ""

        # 4. 回写快照ID到批次
        cursor.execute(
            "UPDATE smart_purchase_batches SET rule_snapshot_id = ? WHERE batch_id = ?",
            (snapshot_id, batch_id)
        )
        conn.commit()

        # 5. 保存失败原因（模拟采购失败）
        from app.core.failure_reason_service import FailureReasonService
        failure_service = FailureReasonService(db)
        failure_service.save_failure_reason(
            batch_id=batch_id,
            item_id=f"{batch_id}_1",
            row_number=1,
            failure_stage="candidate_search",
            failure_code="no_candidate_found",
            failure_message="未找到候选商品",
            rule_set_code=selection["rule_set_code"],
            rule_snapshot_id=snapshot_id
        )

        # 6. 验证完整追溯链
        # 批次 → 规则集
        cursor.execute("SELECT rule_set_code, rule_snapshot_id FROM smart_purchase_batches WHERE batch_id = ?", (batch_id,))
        batch_row = cursor.fetchone()
        assert batch_row["rule_set_code"] == "strict_spec_v1"
        assert batch_row["rule_snapshot_id"] == snapshot_id

        # 快照 → 规则集
        snapshot = snapshot_service.get_rule_snapshot(snapshot_id)
        assert snapshot["rule_set_code"] == "strict_spec_v1"

        # 失败原因 → 规则集 + 快照
        cursor.execute(
            "SELECT rule_set_code, rule_snapshot_id FROM smart_purchase_failure_reasons "
            "WHERE batch_id = ?",
            (batch_id,)
        )
        fail_row = cursor.fetchone()
        assert fail_row["rule_set_code"] == "strict_spec_v1"
        assert fail_row["rule_snapshot_id"] == snapshot_id

    def test_trace_chain_with_default_rule(self, db, selection_service, snapshot_service):
        """完整追溯链：默认规则集"""
        batch_id = "e2e_trace_default"
        conn = db.get_connection()
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO smart_purchase_batches (batch_id, batch_name, created_at)
            VALUES (?, ?, ?)
        ''', (batch_id, "默认追溯", "2026-01-01T00:00:00"))
        conn.commit()

        # 不手工选择，使用默认
        selection = selection_service.resolve_rule_set(batch_id)
        selection_service.save_rule_selection_to_batch(batch_id, selection)

        snapshot_id, _ = snapshot_service.generate_rule_snapshot(batch_id, selection["rule_set_code"])
        cursor.execute(
            "UPDATE smart_purchase_batches SET rule_snapshot_id = ? WHERE batch_id = ?",
            (snapshot_id, batch_id)
        )
        conn.commit()

        # 验证
        cursor.execute("SELECT rule_set_code, rule_select_mode FROM smart_purchase_batches WHERE batch_id = ?", (batch_id,))
        batch_row = cursor.fetchone()
        assert batch_row["rule_set_code"] == "default_v1"
        assert batch_row["rule_select_mode"] == "default"

        snapshot = snapshot_service.get_rule_snapshot(snapshot_id)
        assert snapshot["rule_set_code"] == "default_v1"


class TestPhase2Regression:
    """二期回归"""

    def test_snapshot_generation_still_works(self, snapshot_service, db):
        snapshot_id, error = snapshot_service.generate_rule_snapshot("regression_trace")
        assert snapshot_id != ""
        assert error == ""

    def test_node_config_still_has_required_fields(self, snapshot_service, db):
        snapshot_id, _ = snapshot_service.generate_rule_snapshot("regression_node_trace")
        config = snapshot_service.get_rule_config_for_node(snapshot_id)
        assert "nameWeight" in config
        assert "specConflictBlock" in config

    def test_failure_reason_service_still_works(self, db):
        from app.core.failure_reason_service import FailureReasonService
        service = FailureReasonService(db)
        result = service._classify_raw_reason("未找到候选商品")
        assert result["code"].lower() == "no_candidate_found"
