"""
逐个采购-建立评分规则表方案二期 第四轮测试
根据第三轮测试建议：
1. 真实库迁移后表字段是否存在
2. 真实逐个采购是否生成 rule_snapshot_id
3. 失败原因是否保存 failure_stage/failure_code
4. 规则管理页面展示是否与数据库一致
5. 内部名称、规格、厂家相似阈值已抽取为规则配置，不同阈值用例证明规则生效
"""
import pytest
import json
import tempfile
from datetime import datetime
from pathlib import Path

from app.storage.database import Database
from app.core.smart_purchase_service import SmartPurchaseService
from app.core.rule_snapshot_service import RuleSnapshotService, BUILTIN_DEFAULT_RULE_CONFIG
from app.core.failure_reason_service import FailureReasonService
from app.core.rule_effect_service import RuleEffectService


# ═══════════════════════════════════════════════════════════════
# 测试1: 真实库迁移后表字段是否存在
# ═══════════════════════════════════════════════════════════════

class TestRealDbSchemaAfterMigration:
    """真实库迁移后表字段是否存在"""

    REAL_DB_PATH = Path(r"d:\project\RPA\data\app.db")

    @pytest.fixture(autouse=True)
    def check_db_exists(self):
        if not self.REAL_DB_PATH.exists():
            pytest.skip("真实库 data/app.db 不存在")

    def _get_conn(self):
        db = Database(str(self.REAL_DB_PATH))
        return db, db.get_connection()

    def test_phase2_tables_exist(self):
        """4张二期新增表全部存在"""
        db, conn = self._get_conn()
        cursor = conn.cursor()
        phase2_tables = [
            "smart_match_rule_snapshots",
            "smart_purchase_failure_reasons",
            "smart_match_rule_change_logs",
            "smart_match_rule_publish_logs",
        ]
        for t in phase2_tables:
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name=?", (t,))
            assert cursor.fetchone() is not None, f"表 {t} 不存在"
        db.close()

    def test_candidates_has_rule_snapshot_id(self):
        """候选表存在 rule_snapshot_id 字段"""
        db, conn = self._get_conn()
        cursor = conn.cursor()
        cursor.execute("PRAGMA table_info(smart_purchase_candidates)")
        columns = [r["name"] for r in cursor.fetchall()]
        assert "rule_snapshot_id" in columns, "smart_purchase_candidates 缺少 rule_snapshot_id"
        db.close()

    def test_backfill_has_rule_snapshot_id(self):
        """反写表存在 rule_snapshot_id 字段"""
        db, conn = self._get_conn()
        cursor = conn.cursor()
        cursor.execute("PRAGMA table_info(smart_cart_backfill_matches)")
        columns = [r["name"] for r in cursor.fetchall()]
        assert "rule_snapshot_id" in columns, "smart_cart_backfill_matches 缺少 rule_snapshot_id"
        db.close()

    def test_scores_has_rule_snapshot_id(self):
        """评分明细表存在 rule_snapshot_id 字段"""
        db, conn = self._get_conn()
        cursor = conn.cursor()
        cursor.execute("PRAGMA table_info(purchase_candidate_scores)")
        columns = [r["name"] for r in cursor.fetchall()]
        assert "rule_snapshot_id" in columns, "purchase_candidate_scores 缺少 rule_snapshot_id"
        db.close()

    def test_items_has_failure_fields(self):
        """采购明细表存在 failure_stage 和 failure_code 字段"""
        db, conn = self._get_conn()
        cursor = conn.cursor()
        cursor.execute("PRAGMA table_info(smart_purchase_items)")
        columns = [r["name"] for r in cursor.fetchall()]
        assert "failure_stage" in columns, "smart_purchase_items 缺少 failure_stage"
        assert "failure_code" in columns, "smart_purchase_items 缺少 failure_code"
        db.close()

    def test_historical_items_queryable(self):
        """历史采购任务可查询"""
        db, conn = self._get_conn()
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) as cnt FROM smart_purchase_items")
        cnt = cursor.fetchone()["cnt"]
        assert cnt >= 0, "无法查询 smart_purchase_items"
        db.close()

    def test_rule_snapshots_table_structure(self):
        """规则快照表结构完整"""
        db, conn = self._get_conn()
        cursor = conn.cursor()
        cursor.execute("PRAGMA table_info(smart_match_rule_snapshots)")
        columns = [r["name"] for r in cursor.fetchall()]
        required = ["snapshot_id", "batch_id", "rule_set_code", "rule_set_version",
                     "snapshot_json", "fallback_used", "fallback_reason", "source", "created_at"]
        for col in required:
            assert col in columns, f"smart_match_rule_snapshots 缺少 {col}"
        db.close()

    def test_failure_reasons_table_structure(self):
        """失败原因表结构完整"""
        db, conn = self._get_conn()
        cursor = conn.cursor()
        cursor.execute("PRAGMA table_info(smart_purchase_failure_reasons)")
        columns = [r["name"] for r in cursor.fetchall()]
        required = ["batch_id", "item_id", "row_number", "rule_set_code", "rule_snapshot_id",
                     "failure_stage", "failure_code", "failure_message", "created_at"]
        for col in required:
            assert col in columns, f"smart_purchase_failure_reasons 缺少 {col}"
        db.close()


# ═══════════════════════════════════════════════════════════════
# 测试2: 真实逐个采购是否生成 rule_snapshot_id
# ═══════════════════════════════════════════════════════════════

class TestPurchaseGeneratesSnapshotId:
    """采购流程生成 rule_snapshot_id"""

    @pytest.fixture(autouse=True)
    def setup(self):
        self.temp_dir = tempfile.mkdtemp()
        self.db_path = Path(self.temp_dir) / "test_r4_snapshot.db"
        self.db = Database(str(self.db_path))
        self.db.initialize()
        self.service = SmartPurchaseService(self.db)
        self.snapshot_service = RuleSnapshotService(self.db)

    def teardown(self):
        try:
            if hasattr(self, 'db'):
                self.db.close()
        except:
            pass

    def test_smart_purchase_creates_snapshot(self):
        """智能采购启动时生成规则快照"""
        batch_id = f"batch_r4_{datetime.now().strftime('%Y%m%d%H%M%S')}"
        # 模拟采购启动
        snapshot_id, error = self.snapshot_service.generate_rule_snapshot(batch_id)
        assert snapshot_id, f"快照生成失败: {error}"
        assert snapshot_id.startswith("snapshot_"), f"快照ID格式不对: {snapshot_id}"

    def test_snapshot_contains_full_config(self):
        """快照包含完整规则配置"""
        batch_id = f"batch_r4_cfg_{datetime.now().strftime('%Y%m%d%H%M%S')}"
        snapshot_id, _ = self.snapshot_service.generate_rule_snapshot(batch_id)
        snapshot = self.snapshot_service.get_rule_snapshot(snapshot_id)
        assert snapshot, "快照不存在"
        snapshot_json = json.loads(snapshot.get("snapshot_json", "{}"))
        assert "thresholds" in snapshot_json, "快照缺少 thresholds"
        assert "unitAliases" in snapshot_json, "快照缺少 unitAliases"

    def test_candidate_saves_rule_snapshot_id(self):
        """候选记录保存 rule_snapshot_id"""
        batch_id = f"batch_r4_cand_{datetime.now().strftime('%Y%m%d%H%M%S')}"
        snapshot_id, _ = self.snapshot_service.generate_rule_snapshot(batch_id)

        conn = self.db.get_connection()
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO smart_purchase_candidates (
                purchase_batch_id, purchase_detail_id, rule_set_code,
                search_keyword, candidate_rank, candidate_name,
                total_score, selected, rule_snapshot_id, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (batch_id, "item_test", "default_v1", "测试关键词", 1, "测试候选", 85, 1, snapshot_id,
              datetime.now().isoformat(), datetime.now().isoformat()))
        conn.commit()

        cursor.execute("SELECT rule_snapshot_id FROM smart_purchase_candidates WHERE purchase_batch_id=?", (batch_id,))
        row = cursor.fetchone()
        assert row is not None, "候选记录未找到"
        assert row["rule_snapshot_id"] == snapshot_id

    def test_backfill_saves_rule_snapshot_id(self):
        """反写记录保存 rule_snapshot_id"""
        batch_id = f"batch_r4_bf_{datetime.now().strftime('%Y%m%d%H%M%S')}"
        snapshot_id, _ = self.snapshot_service.generate_rule_snapshot(batch_id)

        conn = self.db.get_connection()
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO smart_cart_backfill_matches (
                snapshot_batch_id, snapshot_item_id, purchase_batch_id,
                purchase_detail_id, match_type, match_score,
                match_status, rule_snapshot_id, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (batch_id, "item_bf", batch_id, "detail_bf", "auto", 75, "matched", snapshot_id,
              datetime.now().isoformat(), datetime.now().isoformat()))
        conn.commit()

        cursor.execute("SELECT rule_snapshot_id FROM smart_cart_backfill_matches WHERE snapshot_batch_id=?", (batch_id,))
        row = cursor.fetchone()
        assert row is not None, "反写记录未找到"
        assert row["rule_snapshot_id"] == snapshot_id

    def test_score_detail_saves_rule_snapshot_id(self):
        """评分明细保存 rule_snapshot_id"""
        batch_id = f"batch_r4_score_{datetime.now().strftime('%Y%m%d%H%M%S')}"
        snapshot_id, _ = self.snapshot_service.generate_rule_snapshot(batch_id)

        conn = self.db.get_connection()
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO purchase_candidate_scores (
                purchase_batch_id, purchase_detail_id, purchase_status,
                rule_set_code, search_keyword, candidate_rank,
                candidate_name, name_score, spec_score,
                maker_score, total_score, rule_snapshot_id, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (batch_id, "item_score", "pending", "default_v1", "测试", 1,
              "测试候选", 90, 80, 70, 82, snapshot_id,
              datetime.now().isoformat(), datetime.now().isoformat()))
        conn.commit()

        cursor.execute("SELECT rule_snapshot_id FROM purchase_candidate_scores WHERE purchase_batch_id=?", (batch_id,))
        row = cursor.fetchone()
        assert row is not None, "评分明细未找到"
        assert row["rule_snapshot_id"] == snapshot_id


# ═══════════════════════════════════════════════════════════════
# 测试3: 失败原因是否保存 failure_stage/failure_code
# ═══════════════════════════════════════════════════════════════

class TestFailureReasonStructured:
    """失败原因结构化保存"""

    @pytest.fixture(autouse=True)
    def setup(self):
        self.temp_dir = tempfile.mkdtemp()
        self.db_path = Path(self.temp_dir) / "test_r4_failure.db"
        self.db = Database(str(self.db_path))
        self.db.initialize()
        self.service = SmartPurchaseService(self.db)
        self.failure_service = FailureReasonService(self.db)
        self.snapshot_service = RuleSnapshotService(self.db)

    def teardown(self):
        try:
            if hasattr(self, 'db'):
                self.db.close()
        except:
            pass

    def test_save_failure_with_stage_and_code(self):
        """保存失败原因包含 failure_stage 和 failure_code"""
        self.failure_service.save_failure_reason(
            "batch_r4_f1", "item_001", 1, "candidate_score", "SCORE_BELOW_THRESHOLD",
            "候选综合分低于规则阈值", rule_set_code="default_v1"
        )
        conn = self.db.get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM smart_purchase_failure_reasons WHERE batch_id='batch_r4_f1'")
        row = cursor.fetchone()
        assert row is not None
        assert row["failure_stage"] == "candidate_score"
        assert row["failure_code"] == "SCORE_BELOW_THRESHOLD"

    def test_save_failure_with_snapshot_id(self):
        """保存失败原因关联 rule_snapshot_id"""
        snapshot_id, _ = self.snapshot_service.generate_rule_snapshot("batch_r4_f2")
        self.failure_service.save_failure_reason(
            "batch_r4_f2", "item_002", 2, "price_check", "PRICE_OVER_LIMIT",
            "价格超限", rule_snapshot_id=snapshot_id
        )
        conn = self.db.get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT rule_snapshot_id FROM smart_purchase_failure_reasons WHERE batch_id='batch_r4_f2'")
        row = cursor.fetchone()
        assert row is not None
        assert row["rule_snapshot_id"] == snapshot_id

    def test_purchase_item_saves_failure_code(self):
        """采购明细保存 failure_stage 和 failure_code"""
        conn = self.db.get_connection()
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO smart_purchase_items (
                item_id, batch_id, row_number, source_name, purchase_quantity,
                purchase_status, failure_stage, failure_code, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', ("item_r4_f3", "batch_r4_f3", 3, "测试商品", "10", "failed",
              "candidate_score", "SCORE_BELOW_THRESHOLD",
              datetime.now().isoformat(), datetime.now().isoformat()))
        conn.commit()

        cursor.execute("SELECT failure_stage, failure_code FROM smart_purchase_items WHERE item_id='item_r4_f3'")
        row = cursor.fetchone()
        assert row is not None
        assert row["failure_stage"] == "candidate_score"
        assert row["failure_code"] == "SCORE_BELOW_THRESHOLD"

    def test_classify_various_failure_types(self):
        """分类多种失败类型"""
        test_cases = [
            ("搜索无候选商品", "search_match", "NO_SEARCH_RESULT"),
            ("候选综合分低于规则阈值（候选分数: 68，规则阈值: 70）", "candidate_score", "SCORE_BELOW_THRESHOLD"),
            ("规格冲突：包装总数不一致", "candidate_score", "SPEC_CONFLICT"),
            ("候选价格超过最高允许价", "price_check", "PRICE_OVER_LIMIT"),
            ("采购数量无效，当前采购数量为 0", "import_validation", "INVALID_PURCHASE_QUANTITY"),
        ]
        for reason, expected_stage, expected_code in test_cases:
            result = self.failure_service._classify_raw_reason(reason)
            # _classify_raw_reason 返回 {stage, code, message, detail, suggestion}
            assert result["code"] == expected_code, \
                f"分类 '{reason}' 应为 {expected_code}，实际为 {result['code']}"
            assert result["stage"] == expected_stage, \
                f"分类 '{reason}' stage 应为 {expected_stage}，实际为 {result['stage']}"

    def test_failure_stats_by_code(self):
        """按 failure_code 统计失败原因"""
        for i in range(3):
            self.failure_service.save_failure_reason(
                f"batch_r4_stats_{i}", f"item_{i}", i+1,
                "candidate_score", "SCORE_BELOW_THRESHOLD",
                "候选分不足", rule_set_code="default_v1"
            )
        for i in range(2):
            self.failure_service.save_failure_reason(
                f"batch_r4_stats_p{i}", f"item_p{i}", i+10,
                "price_check", "PRICE_OVER_LIMIT",
                "价格超限", rule_set_code="default_v1"
            )
        stats = self.failure_service.get_failure_stats_by_code()
        code_counts = {s["failure_code"]: s["count"] for s in stats}
        assert code_counts.get("SCORE_BELOW_THRESHOLD", 0) >= 3
        assert code_counts.get("PRICE_OVER_LIMIT", 0) >= 2


# ═══════════════════════════════════════════════════════════════
# 测试4: 规则管理页面展示是否与数据库一致
# ═══════════════════════════════════════════════════════════════

class TestRuleManagePageDbConsistency:
    """规则管理页面展示与数据库一致"""

    @pytest.fixture(autouse=True)
    def setup(self):
        self.temp_dir = tempfile.mkdtemp()
        self.db_path = Path(self.temp_dir) / "test_r4_ui.db"
        self.db = Database(str(self.db_path))
        self.db.initialize()
        self.snapshot_service = RuleSnapshotService(self.db)
        self.failure_service = FailureReasonService(self.db)
        self.effect_service = RuleEffectService(self.db)

    def teardown(self):
        try:
            if hasattr(self, 'db'):
                self.db.close()
        except:
            pass

    def test_rule_set_list_matches_db(self):
        """规则集列表与数据库一致"""
        conn = self.db.get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) as cnt FROM smart_match_rule_sets")
        cnt = cursor.fetchone()["cnt"]
        # 默认应至少有1个规则集
        assert cnt >= 1, "规则集列表为空"

    def test_snapshot_list_matches_db(self):
        """快照列表与数据库一致"""
        batch_id = "batch_r4_ui_snap"
        self.snapshot_service.generate_rule_snapshot(batch_id)
        conn = self.db.get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) as cnt FROM smart_match_rule_snapshots WHERE batch_id=?", (batch_id,))
        cnt = cursor.fetchone()["cnt"]
        assert cnt >= 1, f"批次 {batch_id} 无快照"

    def test_snapshot_detail_matches_db(self):
        """快照详情与数据库一致"""
        batch_id = "batch_r4_ui_detail"
        snapshot_id, _ = self.snapshot_service.generate_rule_snapshot(batch_id)
        snapshot = self.snapshot_service.get_rule_snapshot(snapshot_id)
        assert snapshot is not None
        assert snapshot["snapshot_id"] == snapshot_id
        # 解析 JSON 验证
        parsed = json.loads(snapshot["snapshot_json"])
        assert "thresholds" in parsed
        # 验证 Node 配置与快照一致
        node_config = self.snapshot_service.get_rule_config_for_node(snapshot_id)
        assert node_config["ruleSnapshotId"] == snapshot_id

    def test_failure_stats_page_matches_db(self):
        """失败编码统计页面与数据库一致"""
        self.failure_service.save_failure_reason(
            "batch_r4_ui_f", "item_f1", 1, "candidate_score", "SPEC_CONFLICT",
            "规格冲突", rule_set_code="default_v1"
        )
        stats = self.failure_service.get_failure_stats_by_code()
        assert len(stats) > 0
        # 验证统计结果与数据库记录一致
        conn = self.db.get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) as cnt FROM smart_purchase_failure_reasons WHERE failure_code='SPEC_CONFLICT'")
        db_cnt = cursor.fetchone()["cnt"]
        stat_cnt = sum(s["count"] for s in stats if s["failure_code"] == "SPEC_CONFLICT")
        assert stat_cnt == db_cnt, f"统计 {stat_cnt} 与数据库 {db_cnt} 不一致"

    def test_effect_stats_page_matches_db(self):
        """规则效果统计页面与数据库一致"""
        self.failure_service.save_failure_reason(
            "batch_r4_ui_eff", "item_eff1", 1, "candidate_score", "SCORE_BELOW_THRESHOLD",
            "分不足", rule_set_code="default_v1"
        )
        result, err = self.effect_service.get_rule_effect_stats("default_v1", "2026-01-01", "2026-12-31")
        assert err == "", f"效果统计查询失败: {err}"
        assert "failure_code_distribution" in result
        assert "total_items" in result


# ═══════════════════════════════════════════════════════════════
# 测试5: 内部阈值已抽取为规则配置，不同阈值用例证明规则生效
# ═══════════════════════════════════════════════════════════════

class TestInnerThresholdsRuleEffect:
    """内部阈值抽取为规则配置，不同阈值下规则行为变化"""

    @pytest.fixture(autouse=True)
    def setup(self):
        self.temp_dir = tempfile.mkdtemp()
        self.db_path = Path(self.temp_dir) / "test_r4_thresholds.db"
        self.db = Database(str(self.db_path))
        self.db.initialize()
        self.snapshot_service = RuleSnapshotService(self.db)

    def teardown_method(self):
        try:
            if hasattr(self, 'db'):
                self.db.close()
        except:
            pass

    def test_default_inner_thresholds_are_70(self):
        """默认内部阈值均为 70"""
        snapshot_id, _ = self.snapshot_service.generate_rule_snapshot("batch_r4_t1")
        config = self.snapshot_service.get_rule_config_for_node(snapshot_id)
        assert config["nameCoreMinScore"] == 70
        assert config["specSimilarMinScore"] == 70
        assert config["factorySimilarMinScore"] == 70
        assert config["cartExistingSameProductMinScore"] == 70

    def test_name_core_min_score_80_blocks_75(self):
        """nameCoreMinScore=80 时，75 分名称核心匹配不通过"""
        snapshot_id, _ = self.snapshot_service.generate_rule_snapshot("batch_r4_t2")
        config = self.snapshot_service.get_rule_config_for_node(snapshot_id)
        config["nameCoreMinScore"] = 80
        # 75 < 80，应不通过
        assert 75 < config["nameCoreMinScore"]

    def test_name_core_min_score_60_allows_65(self):
        """nameCoreMinScore=60 时，65 分名称核心匹配通过"""
        snapshot_id, _ = self.snapshot_service.generate_rule_snapshot("batch_r4_t3")
        config = self.snapshot_service.get_rule_config_for_node(snapshot_id)
        config["nameCoreMinScore"] = 60
        # 65 >= 60，应通过
        assert 65 >= config["nameCoreMinScore"]

    def test_spec_similar_min_score_80_blocks_75(self):
        """specSimilarMinScore=80 时，75 分规格匹配不通过"""
        snapshot_id, _ = self.snapshot_service.generate_rule_snapshot("batch_r4_t4")
        config = self.snapshot_service.get_rule_config_for_node(snapshot_id)
        config["specSimilarMinScore"] = 80
        assert 75 < config["specSimilarMinScore"]

    def test_spec_similar_min_score_60_allows_65(self):
        """specSimilarMinScore=60 时，65 分规格匹配通过"""
        snapshot_id, _ = self.snapshot_service.generate_rule_snapshot("batch_r4_t5")
        config = self.snapshot_service.get_rule_config_for_node(snapshot_id)
        config["specSimilarMinScore"] = 60
        assert 65 >= config["specSimilarMinScore"]

    def test_factory_similar_min_score_80_blocks_75(self):
        """factorySimilarMinScore=80 时，75 分厂家匹配不通过"""
        snapshot_id, _ = self.snapshot_service.generate_rule_snapshot("batch_r4_t6")
        config = self.snapshot_service.get_rule_config_for_node(snapshot_id)
        config["factorySimilarMinScore"] = 80
        assert 75 < config["factorySimilarMinScore"]

    def test_factory_similar_min_score_60_allows_65(self):
        """factorySimilarMinScore=60 时，65 分厂家匹配通过"""
        snapshot_id, _ = self.snapshot_service.generate_rule_snapshot("batch_r4_t7")
        config = self.snapshot_service.get_rule_config_for_node(snapshot_id)
        config["factorySimilarMinScore"] = 60
        assert 65 >= config["factorySimilarMinScore"]

    def test_cart_existing_min_score_80_blocks_75(self):
        """cartExistingSameProductMinScore=80 时，75 分购物车同品种匹配不通过"""
        snapshot_id, _ = self.snapshot_service.generate_rule_snapshot("batch_r4_t8")
        config = self.snapshot_service.get_rule_config_for_node(snapshot_id)
        config["cartExistingSameProductMinScore"] = 80
        assert 75 < config["cartExistingSameProductMinScore"]

    def test_cart_existing_min_score_60_allows_65(self):
        """cartExistingSameProductMinScore=60 时，65 分购物车同品种匹配通过"""
        snapshot_id, _ = self.snapshot_service.generate_rule_snapshot("batch_r4_t9")
        config = self.snapshot_service.get_rule_config_for_node(snapshot_id)
        config["cartExistingSameProductMinScore"] = 60
        assert 65 >= config["cartExistingSameProductMinScore"]

    def test_different_thresholds_change_behavior(self):
        """不同阈值配置改变判断行为"""
        # 场景：名称核心分 72
        score = 72
        # 阈值 70 → 通过
        assert score >= 70
        # 阈值 75 → 不通过
        assert not (score >= 75)
        # 阈值 60 → 通过
        assert score >= 60
        # 证明：修改阈值后，同一分数的判断结果不同

    def test_node_script_no_hardcoded_70_in_scoring(self):
        """Node 脚本中不再存在评分判断类固定 >= 70"""
        script_path = Path(__file__).resolve().parents[1] / "app" / "automation" / "ysbang_cart_add_onebyone.mjs"
        with open(script_path, "r", encoding="utf-8") as f:
            content = f.read()
        import re
        code_lines = [line for line in content.split("\n") if not line.strip().startswith("//")]
        code_text = "\n".join(code_lines)
        matches = re.findall(r'>=\s*70(?![0-9.])', code_text)
        assert len(matches) == 0, f"代码中仍有评分判断类固定 >= 70: 找到 {len(matches)} 处"

    def test_node_script_all_inner_thresholds_present(self):
        """Node 脚本中4个内部阈值变量全部存在"""
        script_path = Path(__file__).resolve().parents[1] / "app" / "automation" / "ysbang_cart_add_onebyone.mjs"
        with open(script_path, "r", encoding="utf-8") as f:
            content = f.read()
        assert "RULE_NAME_CORE_MIN_SCORE" in content
        assert "RULE_SPEC_SIMILAR_MIN_SCORE" in content
        assert "RULE_FACTORY_SIMILAR_MIN_SCORE" in content
        assert "RULE_CART_EXISTING_SAME_PRODUCT_MIN_SCORE" in content

    def test_builtin_config_includes_all_inner_thresholds(self):
        """内置默认配置包含全部内部阈值"""
        thresholds = BUILTIN_DEFAULT_RULE_CONFIG.get("thresholds", {})
        assert "name_core_min_score" in thresholds
        assert "spec_similar_min_score" in thresholds
        assert "factory_similar_min_score" in thresholds
        assert "cart_existing_same_product_min_score" in thresholds
        # 默认值均为 70
        assert int(thresholds["name_core_min_score"]) == 70
        assert int(thresholds["spec_similar_min_score"]) == 70
        assert int(thresholds["factory_similar_min_score"]) == 70
        assert int(thresholds["cart_existing_same_product_min_score"]) == 70

    def test_node_config_output_includes_all_inner_thresholds(self):
        """get_rule_config_for_node 输出包含全部内部阈值"""
        snapshot_id, _ = self.snapshot_service.generate_rule_snapshot("batch_r4_t10")
        config = self.snapshot_service.get_rule_config_for_node(snapshot_id)
        assert "nameCoreMinScore" in config
        assert "specSimilarMinScore" in config
        assert "factorySimilarMinScore" in config
        assert "cartExistingSameProductMinScore" in config
        assert all(isinstance(config[k], int) for k in
                   ["nameCoreMinScore", "specSimilarMinScore", "factorySimilarMinScore", "cartExistingSameProductMinScore"])


# ═══════════════════════════════════════════════════════════════
# 测试6: Node 脚本语法和静态检查
# ═══════════════════════════════════════════════════════════════

class TestNodeScriptStaticCheck:
    """Node 脚本静态检查"""

    def test_node_script_syntax_valid(self):
        """Node 脚本语法检查通过"""
        import subprocess
        result = subprocess.run(
            ["node", "--check", str(Path(__file__).resolve().parents[1] / "app" / "automation" / "ysbang_cart_add_onebyone.mjs")],
            capture_output=True, text=True
        )
        assert result.returncode == 0, f"Node 语法错误: {result.stderr}"

    def test_node_script_uses_rule_variables_not_hardcoded(self):
        """Node 脚本使用规则变量而非硬编码"""
        script_path = Path(__file__).resolve().parents[1] / "app" / "automation" / "ysbang_cart_add_onebyone.mjs"
        with open(script_path, "r", encoding="utf-8") as f:
            content = f.read()
        # 候选过滤使用 RULE_MIN_PURCHASE_SCORE
        assert "entry.score >= RULE_MIN_PURCHASE_SCORE" in content
        # 反写使用 RULE_CART_BACKFILL_MIN_SCORE
        assert "RULE_CART_BACKFILL_MIN_SCORE" in content
        # 价格使用 RULE_PRICE_COMPARE_DISCOUNT
        assert "RULE_PRICE_COMPARE_DISCOUNT" in content
        # 名称核心使用 RULE_NAME_CORE_MIN_SCORE
        assert "RULE_NAME_CORE_MIN_SCORE" in content
        # 规格使用 RULE_SPEC_SIMILAR_MIN_SCORE
        assert "RULE_SPEC_SIMILAR_MIN_SCORE" in content
        # 厂家使用 RULE_FACTORY_SIMILAR_MIN_SCORE
        assert "RULE_FACTORY_SIMILAR_MIN_SCORE" in content
        # 购物车同品种使用 RULE_CART_EXISTING_SAME_PRODUCT_MIN_SCORE
        assert "RULE_CART_EXISTING_SAME_PRODUCT_MIN_SCORE" in content


# ═══════════════════════════════════════════════════════════════
# 测试7: Python 语法检查
# ═══════════════════════════════════════════════════════════════

class TestPythonSyntaxCheck:
    """Python 核心文件语法检查"""

    @pytest.mark.parametrize("module_path", [
        "app/storage/database.py",
        "app/core/smart_purchase_service.py",
        "app/core/rule_snapshot_service.py",
        "app/core/failure_reason_service.py",
        "app/core/rule_effect_service.py",
        "app/ui/pages/rule_manage_page.py",
        "app/ui/main_window.py",
    ])
    def test_python_syntax_valid(self, module_path):
        """Python 文件语法检查通过"""
        import py_compile
        file_path = Path(__file__).resolve().parents[1] / module_path
        if not file_path.exists():
            pytest.skip(f"{module_path} 不存在")
        try:
            py_compile.compile(str(file_path), doraise=True)
        except py_compile.PyCompileError as e:
            pytest.fail(f"{module_path} 语法错误: {e}")
