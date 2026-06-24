"""
逐个采购-建立评分规则表方案二期 第六轮测试
根据第五轮测试结果与整改要求（2026-06-21）：
1. P0: purchase_candidate_scores两处INSERT均未包含rule_snapshot_id → 已修复
2. P0: 双表写入放在同一事务中 → 已修复
3. P0: 购物车反写路径透传rule_snapshot_id → 已确认
4. 测试整改: 新增服务层测试，验证双表rule_snapshot_id一致性
5. 测试整改: 真实库测试改为数据库副本，禁止自动化测试直接初始化生产数据库
"""
import pytest
import json
import tempfile
import shutil
from datetime import datetime
from pathlib import Path

from app.storage.database import Database
from app.core.smart_purchase_service import SmartPurchaseService
from app.core.rule_snapshot_service import RuleSnapshotService
from app.core.failure_reason_service import FailureReasonService, FAILURE_CODES, FAILURE_STAGES


# ═══════════════════════════════════════════════════════════════
# 测试1: _save_single_candidate_score 服务层测试
# ═══════════════════════════════════════════════════════════════

class TestSaveSingleCandidateScoreService:
    """P0整改验证：_save_single_candidate_score 双表写入rule_snapshot_id"""

    @pytest.fixture(autouse=True)
    def setup(self):
        self.temp_dir = tempfile.mkdtemp()
        self.db_path = Path(self.temp_dir) / "test_r6_single_candidate.db"
        self.db = Database(str(self.db_path))
        self.db.initialize()
        self.service = SmartPurchaseService(self.db)

    def teardown_method(self):
        try:
            if hasattr(self, 'db'):
                self.db.close()
        except:
            pass

    def test_both_tables_have_rule_snapshot_id(self):
        """_save_single_candidate_score写入后两张表都有rule_snapshot_id"""
        conn = self.db.get_connection()
        cursor = conn.cursor()

        snapshot_id = "snap_r6_test_001"
        item = {"itemId": "item_r6_1"}
        candidate_data = {
            "name": "阿莫西林胶囊",
            "spec": "0.5g*24粒",
            "manufacturer": "某某药业",
            "supplier": "供应商A",
            "supplierFull": "供应商A有限公司",
            "minAmount": "10",
            "stock": "500",
            "price": "12.5",
            "score": 85,
            "detail": {
                "nameScore": 90,
                "specScore": 80,
                "makerScore": 85,
                "identityOk": True,
                "specOk": True,
                "manufacturerOk": True,
                "supplierOk": True,
                "priceOk": True,
                "qtyOk": True,
                "stockOk": True,
            },
            "specOk": True,
            "manufacturerOk": True,
            "supplierOk": True,
            "priceOk": True,
            "qtyOk": True,
            "stockOk": True,
            "isSelected": True,
            "reason": ""
        }
        adapter_item = {"name": "阿莫西林胶囊", "max_allowed_price": "15.0"}

        self.service._save_single_candidate_score(
            cursor=cursor,
            batch_id="batch_r6_single",
            item=item,
            candidate_data=candidate_data,
            adapter_item=adapter_item,
            purchase_status="success",
            candidate_rank=1,
            is_selected=True,
            rule_snapshot_id=snapshot_id
        )
        conn.commit()

        # 验证 purchase_candidate_scores 有 rule_snapshot_id
        cursor.execute(
            "SELECT rule_snapshot_id FROM purchase_candidate_scores WHERE purchase_batch_id = 'batch_r6_single'"
        )
        pcs_row = cursor.fetchone()
        assert pcs_row is not None, "purchase_candidate_scores应有记录"
        assert pcs_row["rule_snapshot_id"] == snapshot_id, \
            f"purchase_candidate_scores.rule_snapshot_id 应为 {snapshot_id}，实际为 {pcs_row['rule_snapshot_id']}"

        # 验证 smart_purchase_candidates 有 rule_snapshot_id
        cursor.execute(
            "SELECT rule_snapshot_id FROM smart_purchase_candidates WHERE purchase_batch_id = 'batch_r6_single'"
        )
        spc_row = cursor.fetchone()
        assert spc_row is not None, "smart_purchase_candidates应有记录"
        assert spc_row["rule_snapshot_id"] == snapshot_id, \
            f"smart_purchase_candidates.rule_snapshot_id 应为 {snapshot_id}，实际为 {spc_row['rule_snapshot_id']}"

    def test_dual_table_record_count_matches(self):
        """_save_single_candidate_score写入后两张表记录数一致"""
        conn = self.db.get_connection()
        cursor = conn.cursor()

        snapshot_id = "snap_r6_count_001"
        item = {"itemId": "item_r6_2"}
        adapter_item = {"name": "测试商品", "max_allowed_price": "20.0"}

        # 写入3个候选
        for i in range(3):
            candidate_data = {
                "name": f"候选{i+1}",
                "spec": "10mg",
                "manufacturer": "厂家",
                "supplier": "供应商",
                "price": "10.0",
                "score": 80 - i * 10,
                "detail": {"nameScore": 80, "specScore": 80, "makerScore": 80},
                "reason": ""
            }
            self.service._save_single_candidate_score(
                cursor=cursor,
                batch_id="batch_r6_count",
                item=item,
                candidate_data=candidate_data,
                adapter_item=adapter_item,
                purchase_status="success" if i == 0 else "failed",
                candidate_rank=i + 1,
                is_selected=(i == 0),
                rule_snapshot_id=snapshot_id
            )
        conn.commit()

        cursor.execute("SELECT COUNT(*) as cnt FROM purchase_candidate_scores WHERE purchase_batch_id = 'batch_r6_count'")
        pcs_count = cursor.fetchone()["cnt"]
        cursor.execute("SELECT COUNT(*) as cnt FROM smart_purchase_candidates WHERE purchase_batch_id = 'batch_r6_count'")
        spc_count = cursor.fetchone()["cnt"]
        assert pcs_count == spc_count == 3, \
            f"双表记录数应均为3: pcs={pcs_count}, spc={spc_count}"

    def test_dual_table_snapshot_ids_identical(self):
        """_save_single_candidate_score写入后两张表所有记录的rule_snapshot_id完全一致"""
        conn = self.db.get_connection()
        cursor = conn.cursor()

        snapshot_id = "snap_r6_identical_001"
        item = {"itemId": "item_r6_3"}
        adapter_item = {"name": "测试商品", "max_allowed_price": "20.0"}

        for i in range(3):
            candidate_data = {
                "name": f"候选{i+1}",
                "spec": "10mg",
                "manufacturer": "厂家",
                "supplier": "供应商",
                "price": "10.0",
                "score": 80 - i * 10,
                "detail": {},
                "reason": ""
            }
            self.service._save_single_candidate_score(
                cursor=cursor,
                batch_id="batch_r6_identical",
                item=item,
                candidate_data=candidate_data,
                adapter_item=adapter_item,
                purchase_status="failed",
                candidate_rank=i + 1,
                is_selected=False,
                rule_snapshot_id=snapshot_id
            )
        conn.commit()

        cursor.execute("SELECT rule_snapshot_id FROM purchase_candidate_scores WHERE purchase_batch_id = 'batch_r6_identical'")
        pcs_snapshots = [row["rule_snapshot_id"] for row in cursor.fetchall()]
        cursor.execute("SELECT rule_snapshot_id FROM smart_purchase_candidates WHERE purchase_batch_id = 'batch_r6_identical'")
        spc_snapshots = [row["rule_snapshot_id"] for row in cursor.fetchall()]

        assert all(s == snapshot_id for s in pcs_snapshots), \
            f"purchase_candidate_scores 所有记录的 rule_snapshot_id 应为 {snapshot_id}"
        assert all(s == snapshot_id for s in spc_snapshots), \
            f"smart_purchase_candidates 所有记录的 rule_snapshot_id 应为 {snapshot_id}"


# ═══════════════════════════════════════════════════════════════
# 测试2: _save_candidate_scores 服务层测试（有candidates字段）
# ═══════════════════════════════════════════════════════════════

class TestSaveCandidateScoresWithCandidates:
    """P0整改验证：_save_candidate_scores 有candidates时双表写入rule_snapshot_id"""

    @pytest.fixture(autouse=True)
    def setup(self):
        self.temp_dir = tempfile.mkdtemp()
        self.db_path = Path(self.temp_dir) / "test_r6_scores_candidates.db"
        self.db = Database(str(self.db_path))
        self.db.initialize()
        self.service = SmartPurchaseService(self.db)

    def teardown_method(self):
        try:
            if hasattr(self, 'db'):
                self.db.close()
        except:
            pass

    def test_candidates_path_both_tables_have_snapshot_id(self):
        """有candidates字段时两张表都有rule_snapshot_id"""
        snapshot_id = "snap_r6_cand_001"
        item = {"itemId": "item_r6_cand_1"}
        adapter_item = {"name": "测试商品", "max_allowed_price": "20.0"}
        result = {
            "status": "success",
            "candidates": [
                {
                    "name": "候选1",
                    "spec": "10mg",
                    "manufacturer": "厂家A",
                    "supplier": "供应商A",
                    "supplierFull": "供应商A有限公司",
                    "price": "10.0",
                    "score": 90,
                    "detail": {"nameScore": 90, "specScore": 90, "makerScore": 90},
                    "isSelected": True,
                    "reason": ""
                },
                {
                    "name": "候选2",
                    "spec": "20mg",
                    "manufacturer": "厂家B",
                    "supplier": "供应商B",
                    "price": "12.0",
                    "score": 75,
                    "detail": {"nameScore": 75, "specScore": 75, "makerScore": 75},
                    "isSelected": False,
                    "reason": "分数不足"
                }
            ]
        }

        self.service._save_candidate_scores(
            batch_id="batch_r6_cand",
            item=item,
            result=result,
            adapter_item=adapter_item,
            rule_snapshot_id=snapshot_id
        )

        conn = self.db.get_connection()
        cursor = conn.cursor()

        # 验证 purchase_candidate_scores
        cursor.execute(
            "SELECT rule_snapshot_id FROM purchase_candidate_scores WHERE purchase_batch_id = 'batch_r6_cand'"
        )
        pcs_rows = cursor.fetchall()
        assert len(pcs_rows) == 2, f"purchase_candidate_scores应有2条记录，实际{len(pcs_rows)}"
        for row in pcs_rows:
            assert row["rule_snapshot_id"] == snapshot_id, \
                f"purchase_candidate_scores.rule_snapshot_id 应为 {snapshot_id}，实际为 {row['rule_snapshot_id']}"

        # 验证 smart_purchase_candidates
        cursor.execute(
            "SELECT rule_snapshot_id FROM smart_purchase_candidates WHERE purchase_batch_id = 'batch_r6_cand'"
        )
        spc_rows = cursor.fetchall()
        assert len(spc_rows) == 2, f"smart_purchase_candidates应有2条记录，实际{len(spc_rows)}"
        for row in spc_rows:
            assert row["rule_snapshot_id"] == snapshot_id, \
                f"smart_purchase_candidates.rule_snapshot_id 应为 {snapshot_id}，实际为 {row['rule_snapshot_id']}"

    def test_candidates_path_dual_table_count_matches(self):
        """有candidates字段时两张表记录数一致"""
        snapshot_id = "snap_r6_count_002"
        item = {"itemId": "item_r6_count_2"}
        adapter_item = {"name": "测试商品", "max_allowed_price": "20.0"}
        result = {
            "status": "failed",
            "candidates": [
                {"name": f"候选{i}", "spec": "10mg", "manufacturer": "厂家", "supplier": "供应商",
                 "price": "10.0", "score": 80 - i * 5, "detail": {}, "reason": ""}
                for i in range(5)
            ]
        }

        self.service._save_candidate_scores(
            batch_id="batch_r6_count2",
            item=item,
            result=result,
            adapter_item=adapter_item,
            rule_snapshot_id=snapshot_id
        )

        conn = self.db.get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) as cnt FROM purchase_candidate_scores WHERE purchase_batch_id = 'batch_r6_count2'")
        pcs_count = cursor.fetchone()["cnt"]
        cursor.execute("SELECT COUNT(*) as cnt FROM smart_purchase_candidates WHERE purchase_batch_id = 'batch_r6_count2'")
        spc_count = cursor.fetchone()["cnt"]
        assert pcs_count == spc_count == 5, \
            f"双表记录数应均为5: pcs={pcs_count}, spc={spc_count}"


# ═══════════════════════════════════════════════════════════════
# 测试3: _save_candidate_scores 服务层测试（无candidates字段，走else分支）
# ═══════════════════════════════════════════════════════════════

class TestSaveCandidateScoresWithoutCandidates:
    """P0整改验证：_save_candidate_scores 无candidates时（else分支）双表写入rule_snapshot_id"""

    @pytest.fixture(autouse=True)
    def setup(self):
        self.temp_dir = tempfile.mkdtemp()
        self.db_path = Path(self.temp_dir) / "test_r6_scores_no_cand.db"
        self.db = Database(str(self.db_path))
        self.db.initialize()
        self.service = SmartPurchaseService(self.db)

    def teardown_method(self):
        try:
            if hasattr(self, 'db'):
                self.db.close()
        except:
            pass

    def test_no_candidates_path_both_tables_have_snapshot_id(self):
        """无candidates字段时两张表都有rule_snapshot_id"""
        snapshot_id = "snap_r6_nocand_001"
        item = {"itemId": "item_r6_nocand_1"}
        adapter_item = {"name": "测试商品", "max_allowed_price": "20.0"}
        result = {
            "status": "success",
            "matchScore": 85,
            "matchDetail": {
                "nameScore": 90,
                "specScore": 80,
                "makerScore": 85,
                "identityOk": True,
                "specOk": True,
                "manufacturerOk": True,
                "supplierOk": True,
                "priceOk": True,
                "qtyOk": True,
                "stockOk": True,
            },
            "matchedName": "匹配商品",
            "matchedSpec": "10mg*24片",
            "matchedManufacturer": "匹配厂家",
            "matchedSupplier": "匹配供应商",
            "matchedSupplierFull": "匹配供应商全称",
            "matchedPrice": "12.5",
            "matchedMinAmount": "5",
            "matchedStock": "200",
            "candidateRank": 1,
        }

        self.service._save_candidate_scores(
            batch_id="batch_r6_nocand",
            item=item,
            result=result,
            adapter_item=adapter_item,
            rule_snapshot_id=snapshot_id
        )

        conn = self.db.get_connection()
        cursor = conn.cursor()

        # 验证 purchase_candidate_scores
        cursor.execute(
            "SELECT rule_snapshot_id FROM purchase_candidate_scores WHERE purchase_batch_id = 'batch_r6_nocand'"
        )
        pcs_row = cursor.fetchone()
        assert pcs_row is not None, "purchase_candidate_scores应有记录"
        assert pcs_row["rule_snapshot_id"] == snapshot_id, \
            f"purchase_candidate_scores.rule_snapshot_id 应为 {snapshot_id}，实际为 {pcs_row['rule_snapshot_id']}"

        # 验证 smart_purchase_candidates
        cursor.execute(
            "SELECT rule_snapshot_id FROM smart_purchase_candidates WHERE purchase_batch_id = 'batch_r6_nocand'"
        )
        spc_row = cursor.fetchone()
        assert spc_row is not None, "smart_purchase_candidates应有记录"
        assert spc_row["rule_snapshot_id"] == snapshot_id, \
            f"smart_purchase_candidates.rule_snapshot_id 应为 {snapshot_id}，实际为 {spc_row['rule_snapshot_id']}"

    def test_no_candidates_path_dual_table_count_matches(self):
        """无candidates字段时两张表记录数一致"""
        snapshot_id = "snap_r6_nocand_count_001"
        item = {"itemId": "item_r6_nocand_count_1"}
        adapter_item = {"name": "测试商品", "max_allowed_price": "20.0"}
        result = {
            "status": "failed",
            "matchScore": 55,
            "matchDetail": {"nameScore": 60, "specScore": 50, "makerScore": 55},
            "matchedName": "匹配商品",
            "matchedSpec": "10mg",
            "matchedManufacturer": "厂家",
            "matchedSupplier": "供应商",
            "matchedPrice": "10.0",
            "candidateRank": 1,
        }

        self.service._save_candidate_scores(
            batch_id="batch_r6_nocand_count",
            item=item,
            result=result,
            adapter_item=adapter_item,
            rule_snapshot_id=snapshot_id
        )

        conn = self.db.get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) as cnt FROM purchase_candidate_scores WHERE purchase_batch_id = 'batch_r6_nocand_count'")
        pcs_count = cursor.fetchone()["cnt"]
        cursor.execute("SELECT COUNT(*) as cnt FROM smart_purchase_candidates WHERE purchase_batch_id = 'batch_r6_nocand_count'")
        spc_count = cursor.fetchone()["cnt"]
        assert pcs_count == spc_count == 1, \
            f"双表记录数应均为1: pcs={pcs_count}, spc={spc_count}"


# ═══════════════════════════════════════════════════════════════
# 测试4: 双表事务一致性 - 异常回滚测试
# ═══════════════════════════════════════════════════════════════

class TestDualTableTransactionConsistency:
    """P0整改验证：双表写入在同一事务中，异常时整体回滚"""

    @pytest.fixture(autouse=True)
    def setup(self):
        self.temp_dir = tempfile.mkdtemp()
        self.db_path = Path(self.temp_dir) / "test_r6_transaction.db"
        self.db = Database(str(self.db_path))
        self.db.initialize()
        self.service = SmartPurchaseService(self.db)

    def teardown_method(self):
        try:
            if hasattr(self, 'db'):
                self.db.close()
        except:
            pass

    def test_empty_snapshot_id_still_writes_to_both_tables(self):
        """空rule_snapshot_id时双表仍然同步写入"""
        conn = self.db.get_connection()
        cursor = conn.cursor()

        item = {"itemId": "item_r6_empty_snap"}
        candidate_data = {
            "name": "候选",
            "spec": "10mg",
            "manufacturer": "厂家",
            "supplier": "供应商",
            "price": "10.0",
            "score": 80,
            "detail": {},
            "reason": ""
        }
        adapter_item = {"name": "测试商品", "max_allowed_price": "20.0"}

        self.service._save_single_candidate_score(
            cursor=cursor,
            batch_id="batch_r6_empty_snap",
            item=item,
            candidate_data=candidate_data,
            adapter_item=adapter_item,
            purchase_status="failed",
            candidate_rank=1,
            is_selected=False,
            rule_snapshot_id=""  # 空快照ID
        )
        conn.commit()

        cursor.execute("SELECT COUNT(*) as cnt FROM purchase_candidate_scores WHERE purchase_batch_id = 'batch_r6_empty_snap'")
        pcs_count = cursor.fetchone()["cnt"]
        cursor.execute("SELECT COUNT(*) as cnt FROM smart_purchase_candidates WHERE purchase_batch_id = 'batch_r6_empty_snap'")
        spc_count = cursor.fetchone()["cnt"]
        assert pcs_count == spc_count == 1, \
            f"空快照ID时双表记录数应均为1: pcs={pcs_count}, spc={spc_count}"

    def test_second_table_insert_failure_triggers_rollback(self):
        """故障注入：smart_purchase_candidates插入失败时，purchase_candidate_scores也回滚"""
        import sqlite3

        conn = self.db.get_connection()
        cursor = conn.cursor()

        # 创建触发器：当插入特定batch_id时强制smart_purchase_candidates失败
        cursor.execute('''
            CREATE TRIGGER force_spc_insert_fail
            BEFORE INSERT ON smart_purchase_candidates
            WHEN NEW.purchase_batch_id = 'batch_r6_force_fail'
            BEGIN
                SELECT RAISE(ABORT, 'forced failure for testing rollback');
            END
        ''')
        conn.commit()

        item = {"itemId": "item_r6_force_fail"}
        candidate_data = {
            "name": "候选",
            "spec": "10mg",
            "manufacturer": "厂家",
            "supplier": "供应商",
            "price": "10.0",
            "score": 80,
            "detail": {},
            "reason": ""
        }
        adapter_item = {"name": "测试商品", "max_allowed_price": "20.0"}

        # 调用保存方法，预期因触发器而失败
        try:
            self.service._save_single_candidate_score(
                cursor=cursor,
                batch_id="batch_r6_force_fail",
                item=item,
                candidate_data=candidate_data,
                adapter_item=adapter_item,
                purchase_status="failed",
                candidate_rank=1,
                is_selected=False,
                rule_snapshot_id="snap_r6_force_fail"
            )
            conn.commit()
        except Exception:
            conn.rollback()

        # 验证：两张表均不应有残留记录
        cursor.execute("SELECT COUNT(*) as cnt FROM purchase_candidate_scores WHERE purchase_batch_id = 'batch_r6_force_fail'")
        pcs_count = cursor.fetchone()["cnt"]
        cursor.execute("SELECT COUNT(*) as cnt FROM smart_purchase_candidates WHERE purchase_batch_id = 'batch_r6_force_fail'")
        spc_count = cursor.fetchone()["cnt"]
        assert pcs_count == 0, \
            f"回滚后purchase_candidate_scores不应有残留记录: {pcs_count}"
        assert spc_count == 0, \
            f"回滚后smart_purchase_candidates不应有残留记录: {spc_count}"


# ═══════════════════════════════════════════════════════════════
# 测试5: 规则快照与候选评分关联完整性
# ═══════════════════════════════════════════════════════════════

class TestRuleSnapshotCandidateAssociation:
    """验证规则快照与候选评分的完整关联"""

    @pytest.fixture(autouse=True)
    def setup(self):
        self.temp_dir = tempfile.mkdtemp()
        self.db_path = Path(self.temp_dir) / "test_r6_association.db"
        self.db = Database(str(self.db_path))
        self.db.initialize()
        self.snapshot_service = RuleSnapshotService(self.db)
        self.service = SmartPurchaseService(self.db)

    def teardown_method(self):
        try:
            if hasattr(self, 'db'):
                self.db.close()
        except:
            pass

    def test_generated_snapshot_linked_to_candidates(self):
        """生成的规则快照ID与候选评分记录关联"""
        # 1. 生成规则快照
        batch_id = "batch_r6_assoc"
        snapshot_id, error = self.snapshot_service.generate_rule_snapshot(batch_id)
        assert snapshot_id, f"快照生成失败: {error}"

        # 2. 使用快照ID保存候选评分
        conn = self.db.get_connection()
        cursor = conn.cursor()
        item = {"itemId": f"{batch_id}_1"}
        candidate_data = {
            "name": "关联测试商品",
            "spec": "10mg",
            "manufacturer": "厂家",
            "supplier": "供应商",
            "price": "10.0",
            "score": 85,
            "detail": {},
            "reason": ""
        }
        adapter_item = {"name": "关联测试商品", "max_allowed_price": "15.0"}

        self.service._save_single_candidate_score(
            cursor=cursor,
            batch_id=batch_id,
            item=item,
            candidate_data=candidate_data,
            adapter_item=adapter_item,
            purchase_status="success",
            candidate_rank=1,
            is_selected=True,
            rule_snapshot_id=snapshot_id
        )
        conn.commit()

        # 3. 验证快照存在且非fallback
        snapshot = self.snapshot_service.get_rule_snapshot(snapshot_id)
        assert snapshot is not None, "快照应存在"
        assert snapshot["fallback_used"] == 0, "快照不应使用fallback"

        # 4. 验证候选评分记录关联了正确的快照ID
        cursor.execute(
            "SELECT rule_snapshot_id FROM purchase_candidate_scores WHERE purchase_batch_id = ?",
            (batch_id,)
        )
        pcs_row = cursor.fetchone()
        assert pcs_row["rule_snapshot_id"] == snapshot_id, \
            f"purchase_candidate_scores 应关联快照 {snapshot_id}"

        cursor.execute(
            "SELECT rule_snapshot_id FROM smart_purchase_candidates WHERE purchase_batch_id = ?",
            (batch_id,)
        )
        spc_row = cursor.fetchone()
        assert spc_row["rule_snapshot_id"] == snapshot_id, \
            f"smart_purchase_candidates 应关联快照 {snapshot_id}"

    def test_snapshot_and_failure_use_same_snapshot_id(self):
        """失败原因和候选评分使用同一个快照ID"""
        batch_id = "batch_r6_fail_assoc"
        snapshot_id, _ = self.snapshot_service.generate_rule_snapshot(batch_id)
        assert snapshot_id

        # 保存失败原因
        failure_service = FailureReasonService(self.db)
        failure_service.save_failure_reason(
            batch_id=batch_id,
            item_id=f"{batch_id}_1",
            row_number=1,
            failure_stage="candidate_score",
            failure_code="SCORE_BELOW_THRESHOLD",
            failure_message="候选综合分低于规则阈值",
            failure_detail="候选分数: 55，规则阈值: 60",
            suggestion="请检查评分规则阈值设置。",
            raw_reason="候选综合分低于规则阈值",
            rule_set_code="default_v1",
            rule_snapshot_id=snapshot_id
        )

        # 保存候选评分
        conn = self.db.get_connection()
        cursor = conn.cursor()
        item = {"itemId": f"{batch_id}_1"}
        candidate_data = {
            "name": "低分候选",
            "spec": "10mg",
            "manufacturer": "厂家",
            "supplier": "供应商",
            "price": "10.0",
            "score": 55,
            "detail": {},
            "reason": "分数不足"
        }
        adapter_item = {"name": "低分候选", "max_allowed_price": "15.0"}
        self.service._save_single_candidate_score(
            cursor=cursor,
            batch_id=batch_id,
            item=item,
            candidate_data=candidate_data,
            adapter_item=adapter_item,
            purchase_status="failed",
            candidate_rank=1,
            is_selected=False,
            rule_snapshot_id=snapshot_id
        )
        conn.commit()

        # 验证失败原因和候选评分使用同一个快照ID
        cursor.execute(
            "SELECT rule_snapshot_id FROM smart_purchase_failure_reasons WHERE batch_id = ?",
            (batch_id,)
        )
        failure_row = cursor.fetchone()
        assert failure_row["rule_snapshot_id"] == snapshot_id, \
            f"失败原因应关联快照 {snapshot_id}"

        cursor.execute(
            "SELECT rule_snapshot_id FROM purchase_candidate_scores WHERE purchase_batch_id = ?",
            (batch_id,)
        )
        pcs_row = cursor.fetchone()
        assert pcs_row["rule_snapshot_id"] == snapshot_id, \
            f"候选评分应关联快照 {snapshot_id}"


# ═══════════════════════════════════════════════════════════════
# 测试6: 数据库副本验证（替代直接操作真实库）
# ═══════════════════════════════════════════════════════════════

class TestDatabaseCopyVerification:
    """使用数据库副本验证，不直接操作真实 data/app.db"""

    REAL_DB_PATH = Path(r"d:\project\RPA\data\app.db")

    @pytest.fixture(autouse=True)
    def check_db_exists(self):
        if not self.REAL_DB_PATH.exists():
            pytest.skip("真实库 data/app.db 不存在")

    def _get_copy_db(self):
        """创建真实库的副本用于测试，不修改原库"""
        copy_dir = tempfile.mkdtemp()
        copy_path = Path(copy_dir) / "app_copy_r6.db"
        shutil.copy2(str(self.REAL_DB_PATH), str(copy_path))
        db = Database(str(copy_path))
        db.initialize()  # 触发迁移
        return db, db.get_connection(), copy_dir

    def test_copy_db_version_number_exists(self):
        """P0-2: 副本库smart_match_rule_sets.version_number存在"""
        db, conn, copy_dir = self._get_copy_db()
        try:
            cursor = conn.cursor()
            cursor.execute("PRAGMA table_info(smart_match_rule_sets)")
            columns = {row["name"] for row in cursor.fetchall()}
            assert "version_number" in columns, "副本库应有version_number字段"
        finally:
            db.close()
            shutil.rmtree(copy_dir, ignore_errors=True)

    def test_copy_db_snapshot_not_fallback(self):
        """P0-3: 副本库最新快照不使用fallback"""
        db, conn, copy_dir = self._get_copy_db()
        try:
            snapshot_service = RuleSnapshotService(db)
            snapshot_id, error = snapshot_service.generate_rule_snapshot("batch_r6_copy_test")
            assert snapshot_id, f"快照生成失败: {error}"
            snapshot = snapshot_service.get_rule_snapshot(snapshot_id)
            assert snapshot["fallback_used"] == 0, "副本库快照不应使用fallback"
        finally:
            db.close()
            shutil.rmtree(copy_dir, ignore_errors=True)

    def test_copy_db_candidate_scores_have_snapshot_id(self):
        """P0: 副本库候选评分保存后purchase_candidate_scores有rule_snapshot_id"""
        db, conn, copy_dir = self._get_copy_db()
        try:
            snapshot_service = RuleSnapshotService(db)
            service = SmartPurchaseService(db)

            snapshot_id, _ = snapshot_service.generate_rule_snapshot("batch_r6_copy_cand")
            assert snapshot_id

            cursor = conn.cursor()
            item = {"itemId": "item_copy_1"}
            candidate_data = {
                "name": "副本测试商品",
                "spec": "10mg",
                "manufacturer": "厂家",
                "supplier": "供应商",
                "price": "10.0",
                "score": 85,
                "detail": {},
                "reason": ""
            }
            adapter_item = {"name": "副本测试商品", "max_allowed_price": "15.0"}

            service._save_single_candidate_score(
                cursor=cursor,
                batch_id="batch_r6_copy_cand",
                item=item,
                candidate_data=candidate_data,
                adapter_item=adapter_item,
                purchase_status="success",
                candidate_rank=1,
                is_selected=True,
                rule_snapshot_id=snapshot_id
            )
            conn.commit()

            cursor.execute(
                "SELECT rule_snapshot_id FROM purchase_candidate_scores WHERE purchase_batch_id = 'batch_r6_copy_cand'"
            )
            row = cursor.fetchone()
            assert row is not None, "副本库purchase_candidate_scores应有记录"
            assert row["rule_snapshot_id"] == snapshot_id, \
                f"副本库 purchase_candidate_scores.rule_snapshot_id 应为 {snapshot_id}，实际为 {row['rule_snapshot_id']}"

            cursor.execute(
                "SELECT rule_snapshot_id FROM smart_purchase_candidates WHERE purchase_batch_id = 'batch_r6_copy_cand'"
            )
            row2 = cursor.fetchone()
            assert row2 is not None, "副本库smart_purchase_candidates应有记录"
            assert row2["rule_snapshot_id"] == snapshot_id, \
                f"副本库 smart_purchase_candidates.rule_snapshot_id 应为 {snapshot_id}，实际为 {row2['rule_snapshot_id']}"
        finally:
            db.close()
            shutil.rmtree(copy_dir, ignore_errors=True)

    def test_copy_db_dual_table_snapshot_ids_match(self):
        """P0: 副本库两张候选表的rule_snapshot_id完全一致"""
        db, conn, copy_dir = self._get_copy_db()
        try:
            snapshot_service = RuleSnapshotService(db)
            service = SmartPurchaseService(db)

            snapshot_id, _ = snapshot_service.generate_rule_snapshot("batch_r6_copy_match")
            cursor = conn.cursor()
            item = {"itemId": "item_copy_match_1"}
            adapter_item = {"name": "测试商品", "max_allowed_price": "20.0"}
            result = {
                "status": "failed",
                "candidates": [
                    {"name": "候选1", "spec": "10mg", "manufacturer": "厂家", "supplier": "供应商",
                     "price": "10.0", "score": 55, "detail": {}, "reason": "分数不足"},
                    {"name": "候选2", "spec": "20mg", "manufacturer": "厂家", "supplier": "供应商",
                     "price": "12.0", "score": 45, "detail": {}, "reason": "分数不足"},
                ]
            }

            service._save_candidate_scores(
                batch_id="batch_r6_copy_match",
                item=item,
                result=result,
                adapter_item=adapter_item,
                rule_snapshot_id=snapshot_id
            )

            cursor.execute(
                "SELECT rule_snapshot_id FROM purchase_candidate_scores WHERE purchase_batch_id = 'batch_r6_copy_match'"
            )
            pcs_rows = cursor.fetchall()
            cursor.execute(
                "SELECT rule_snapshot_id FROM smart_purchase_candidates WHERE purchase_batch_id = 'batch_r6_copy_match'"
            )
            spc_rows = cursor.fetchall()

            assert len(pcs_rows) == len(spc_rows) == 2, \
                f"双表记录数应均为2: pcs={len(pcs_rows)}, spc={len(spc_rows)}"

            for row in pcs_rows:
                assert row["rule_snapshot_id"] == snapshot_id, \
                    f"purchase_candidate_scores.rule_snapshot_id 不一致: {row['rule_snapshot_id']}"
            for row in spc_rows:
                assert row["rule_snapshot_id"] == snapshot_id, \
                    f"smart_purchase_candidates.rule_snapshot_id 不一致: {row['rule_snapshot_id']}"
        finally:
            db.close()
            shutil.rmtree(copy_dir, ignore_errors=True)


# ═══════════════════════════════════════════════════════════════
# 测试7: 第五轮已通过项回归验证
# ═══════════════════════════════════════════════════════════════

class TestRound5Regression:
    """第五轮已通过项的回归验证"""

    @pytest.fixture(autouse=True)
    def setup(self):
        self.temp_dir = tempfile.mkdtemp()
        self.db_path = Path(self.temp_dir) / "test_r6_regression.db"
        self.db = Database(str(self.db_path))
        self.db.initialize()
        self.failure_service = FailureReasonService(self.db)

    def teardown_method(self):
        try:
            if hasattr(self, 'db'):
                self.db.close()
        except:
            pass

    def test_cart_quantity_not_reached_classification(self):
        """P1-2回归：购物车数量校验失败精确分类"""
        result = self.failure_service._classify_raw_reason(
            "加购后购物车数量未达到要求（要求数量: 10，实际购物车数量: 0）"
        )
        assert result["code"] == "CART_QUANTITY_NOT_REACHED"
        assert result["stage"] == "cart_verify"

    def test_no_candidate_found_classification(self):
        """P1-3回归：未找到候选商品精确分类"""
        result = self.failure_service._classify_raw_reason(
            "未找到满足供应商、品种、规格、厂家/批准文号、价格、起购数量的候选"
        )
        assert result["code"] == "NO_CANDIDATE_FOUND"
        assert result["stage"] == "candidate_search"

    def test_failure_reason_completeness(self):
        """P1-1回归：结构化失败记录完整性"""
        self.failure_service.save_failure_reason(
            batch_id="batch_r6_reg",
            item_id="batch_r6_reg_3",
            row_number=3,
            failure_stage="candidate_score",
            failure_code="SCORE_BELOW_THRESHOLD",
            failure_message="候选综合分低于规则阈值",
            failure_detail="候选分数: 55，规则阈值: 60",
            suggestion="请检查评分规则阈值设置。",
            raw_reason="候选综合分低于规则阈值",
            rule_set_code="default_v1",
            rule_snapshot_id="snap_r6_reg"
        )
        reasons = self.failure_service.get_failure_reasons_by_batch("batch_r6_reg")
        assert len(reasons) == 1
        assert reasons[0]["row_number"] == 3
        assert reasons[0]["failure_detail"] != ""
        assert reasons[0]["suggestion"] != ""
        assert reasons[0]["rule_snapshot_id"] == "snap_r6_reg"

    def test_version_number_migration(self):
        """P0-2回归：version_number字段迁移"""
        conn = self.db.get_connection()
        cursor = conn.cursor()
        cursor.execute("PRAGMA table_info(smart_match_rule_sets)")
        columns = {row["name"] for row in cursor.fetchall()}
        assert "version_number" in columns

    def test_snapshot_not_fallback(self):
        """P0-3回归：规则快照不使用fallback"""
        snapshot_service = RuleSnapshotService(self.db)
        snapshot_id, error = snapshot_service.generate_rule_snapshot("batch_r6_reg_snap")
        assert snapshot_id, f"快照生成失败: {error}"
        snapshot = snapshot_service.get_rule_snapshot(snapshot_id)
        assert snapshot["fallback_used"] == 0
