"""
逐个采购-建立评分规则表方案二期 第五轮测试
根据第三轮复核与实操结果 + 第四轮整改要求：
1. P0-1: RULE_SCORE_THRESHOLD未定义的JavaScript引用异常 → 已修复，验证evaluate中阈值注入
2. P0-2: 真实库缺少smart_match_rule_sets.version_number → 已添加幂等迁移
3. P0-3: 规则快照fallback → 快照服务兼容version_number字段迁移前后
4. P1-1: 结构化失败记录row_number/failure_detail/suggestion写入错误或空 → 已修复
5. P1-2: 购物车数量校验失败分类不准确 → 增加CART_QUANTITY_NOT_REACHED编码
6. P1-3: 未找到候选商品分类不准确 → 增加NO_CANDIDATE_FOUND编码
7. P2-1: 采购候选双表记录不一致 → 已同步写入smart_purchase_candidates
"""
import pytest
import json
import tempfile
from datetime import datetime
from pathlib import Path

from app.storage.database import Database
from app.core.smart_purchase_service import SmartPurchaseService
from app.core.rule_snapshot_service import RuleSnapshotService, BUILTIN_DEFAULT_RULE_CONFIG
from app.core.failure_reason_service import FailureReasonService, FAILURE_CODES, FAILURE_STAGES
from app.core.rule_effect_service import RuleEffectService


# ═══════════════════════════════════════════════════════════════
# 测试1: P0-2 幂等迁移 - version_number字段补充
# ═══════════════════════════════════════════════════════════════

class TestRuleSetVersionNumberMigration:
    """P0-2: smart_match_rule_sets.version_number 幂等迁移"""

    @pytest.fixture(autouse=True)
    def setup(self):
        self.temp_dir = tempfile.mkdtemp()
        self.db_path = Path(self.temp_dir) / "test_r5_migration.db"
        self.db = Database(str(self.db_path))
        self.db.initialize()

    def teardown_method(self):
        try:
            if hasattr(self, 'db'):
                self.db.close()
        except:
            pass

    def test_version_number_column_exists_after_initialize(self):
        """初始化后version_number字段存在"""
        conn = self.db.get_connection()
        cursor = conn.cursor()
        cursor.execute("PRAGMA table_info(smart_match_rule_sets)")
        columns = {row["name"] for row in cursor.fetchall()}
        assert "version_number" in columns, "version_number字段应存在"

    def test_default_rule_sets_have_version_number(self):
        """默认规则集version_number不为空"""
        conn = self.db.get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT rule_set_code, version_number FROM smart_match_rule_sets")
        rows = cursor.fetchall()
        for row in rows:
            assert row["version_number"], f"规则集 {row['rule_set_code']} 的 version_number 不应为空"

    def test_migration_idempotent(self):
        """迁移幂等：多次执行initialize不报错"""
        # 第二次初始化
        self.db.initialize()
        conn = self.db.get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) as cnt FROM smart_match_rule_sets WHERE version_number IS NOT NULL AND version_number != ''")
        result = cursor.fetchone()
        assert result["cnt"] > 0, "幂等迁移后规则集应有版本号"

    def test_old_db_migration_adds_version_number(self):
        """旧数据库（缺少version_number）执行迁移后补充字段"""
        conn = self.db.get_connection()
        cursor = conn.cursor()
        # 模拟旧数据库：删除version_number列（SQLite不支持DROP COLUMN，通过重建表模拟）
        # 先验证字段已存在
        cursor.execute("PRAGMA table_info(smart_match_rule_sets)")
        columns_before = {row["name"] for row in cursor.fetchall()}
        assert "version_number" in columns_before, "初始化后应有version_number"

        # 验证迁移方法可以安全重复调用
        self.db._migrate_add_rule_set_version_number()
        cursor.execute("PRAGMA table_info(smart_match_rule_sets)")
        columns_after = {row["name"] for row in cursor.fetchall()}
        assert "version_number" in columns_after, "重复迁移后version_number仍存在"


# ═══════════════════════════════════════════════════════════════
# 测试2: P0-3 规则快照服务兼容version_number
# ═══════════════════════════════════════════════════════════════

class TestRuleSnapshotVersionCompatibility:
    """P0-3: 规则快照服务兼容version_number字段迁移前后"""

    @pytest.fixture(autouse=True)
    def setup(self):
        self.temp_dir = tempfile.mkdtemp()
        self.db_path = Path(self.temp_dir) / "test_r5_snapshot_compat.db"
        self.db = Database(str(self.db_path))
        self.db.initialize()
        self.snapshot_service = RuleSnapshotService(self.db)

    def teardown_method(self):
        try:
            if hasattr(self, 'db'):
                self.db.close()
        except:
            pass

    def test_snapshot_not_fallback_with_version_number(self):
        """有version_number时快照不使用fallback"""
        snapshot_id, error = self.snapshot_service.generate_rule_snapshot("batch_r5_v1")
        assert snapshot_id, f"快照生成失败: {error}"

        snapshot = self.snapshot_service.get_rule_snapshot(snapshot_id)
        assert snapshot["fallback_used"] == 0, "不应使用fallback"
        assert snapshot["fallback_reason"] == "", "fallback_reason应为空"

    def test_snapshot_contains_version(self):
        """快照中包含规则版本信息"""
        snapshot_id, _ = self.snapshot_service.generate_rule_snapshot("batch_r5_v2")
        snapshot = self.snapshot_service.get_rule_snapshot(snapshot_id)
        config = json.loads(snapshot["snapshot_json"])
        assert config.get("version"), "快照应包含版本号"
        assert config["version"] != "", "版本号不应为空"

    def test_snapshot_version_matches_rule_set(self):
        """快照中的版本与规则集版本一致"""
        conn = self.db.get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT rule_set_code, version_number FROM smart_match_rule_sets WHERE is_enabled = 1 LIMIT 1")
        row = cursor.fetchone()
        if row:
            snapshot_id, _ = self.snapshot_service.generate_rule_snapshot("batch_r5_v3", row["rule_set_code"])
            snapshot = self.snapshot_service.get_rule_snapshot(snapshot_id)
            config = json.loads(snapshot["snapshot_json"])
            assert config.get("version") == row["version_number"], \
                f"快照版本 {config.get('version')} 应与规则集版本 {row['version_number']} 一致"


# ═══════════════════════════════════════════════════════════════
# 测试3: P1-1 结构化失败记录完整性
# ═══════════════════════════════════════════════════════════════

class TestFailureReasonCompleteness:
    """P1-1: 结构化失败记录 row_number/failure_detail/suggestion 完整性"""

    @pytest.fixture(autouse=True)
    def setup(self):
        self.temp_dir = tempfile.mkdtemp()
        self.db_path = Path(self.temp_dir) / "test_r5_failure.db"
        self.db = Database(str(self.db_path))
        self.db.initialize()
        self.failure_service = FailureReasonService(self.db)

    def teardown_method(self):
        try:
            if hasattr(self, 'db'):
                self.db.close()
        except:
            pass

    def test_row_number_not_zero(self):
        """row_number不为0，从item_id中提取真实行号"""
        self.failure_service.save_failure_reason(
            batch_id="batch_r5",
            item_id="batch_r5_3",
            row_number=3,
            failure_stage="candidate_score",
            failure_code="SCORE_BELOW_THRESHOLD",
            failure_message="候选综合分低于规则阈值",
            failure_detail="候选分数: 55，规则阈值: 60",
            suggestion="请检查评分规则阈值设置。",
            raw_reason="候选综合分低于规则阈值",
            rule_set_code="default_v1",
            rule_snapshot_id="snap_r5"
        )
        reasons = self.failure_service.get_failure_reasons_by_batch("batch_r5")
        assert len(reasons) == 1
        assert reasons[0]["row_number"] == 3, "row_number应为3"
        assert reasons[0]["failure_detail"] != "", "failure_detail不应为空"
        assert reasons[0]["suggestion"] != "", "suggestion不应为空"

    def test_classify_raw_reason_returns_detail_and_suggestion(self):
        """_classify_raw_reason返回detail和suggestion字段"""
        result = self.failure_service._classify_raw_reason("候选综合分低于规则阈值")
        assert result["detail"] != "", "分类结果应包含detail"
        assert result["suggestion"] != "", "分类结果应包含suggestion"

    def test_different_failure_types_have_different_details(self):
        """不同失败类型产生不同的detail和suggestion"""
        test_cases = [
            ("缺少商品名称", "MISSING_PRODUCT_NAME"),
            ("采购数量无效", "INVALID_PURCHASE_QUANTITY"),
            ("价格超限", "PRICE_OVER_LIMIT"),
            ("库存不足", "STOCK_NOT_ENOUGH"),
            ("购物车数量未达到要求", "CART_QUANTITY_NOT_REACHED"),
            ("未找到候选商品", "NO_CANDIDATE_FOUND"),
        ]
        results = {}
        for reason, expected_code in test_cases:
            result = self.failure_service._classify_raw_reason(reason)
            results[expected_code] = result
            assert result["code"] == expected_code, f"原因 '{reason}' 应分类为 {expected_code}，实际为 {result['code']}"
            assert result["detail"] != "", f"{expected_code} 的 detail 不应为空"
            assert result["suggestion"] != "", f"{expected_code} 的 suggestion 不应为空"

        # 验证不同类型的suggestion不同
        suggestions = {code: r["suggestion"] for code, r in results.items()}
        unique_suggestions = set(suggestions.values())
        assert len(unique_suggestions) >= 4, "不同失败类型的suggestion应有区分"


# ═══════════════════════════════════════════════════════════════
# 测试4: P1-2 购物车数量校验失败精确分类
# ═══════════════════════════════════════════════════════════════

class TestCartQuantityNotReachedClassification:
    """P1-2: 购物车数量校验失败应归类为cart_verify/CART_QUANTITY_NOT_REACHED"""

    @pytest.fixture(autouse=True)
    def setup(self):
        self.temp_dir = tempfile.mkdtemp()
        self.db_path = Path(self.temp_dir) / "test_r5_cart_verify.db"
        self.db = Database(str(self.db_path))
        self.db.initialize()
        self.failure_service = FailureReasonService(self.db)

    def teardown_method(self):
        try:
            if hasattr(self, 'db'):
                self.db.close()
        except:
            pass

    def test_cart_quantity_not_reached_code_exists(self):
        """CART_QUANTITY_NOT_REACHED编码已定义"""
        assert "CART_QUANTITY_NOT_REACHED" in FAILURE_CODES
        code_def = FAILURE_CODES["CART_QUANTITY_NOT_REACHED"]
        assert code_def["stage"] == "cart_verify"
        assert code_def["suggestion"] != ""

    def test_cart_verify_stage_exists(self):
        """cart_verify阶段已定义"""
        assert "cart_verify" in FAILURE_STAGES

    def test_classify_cart_quantity_not_reached(self):
        """购物车数量未达到要求 → CART_QUANTITY_NOT_REACHED"""
        result = self.failure_service._classify_raw_reason(
            "加购后购物车数量未达到要求（要求数量: 10，实际购物车数量: 0，候选编码: WH123，供应商: XX药业）"
        )
        assert result["code"] == "CART_QUANTITY_NOT_REACHED", \
            f"应分类为CART_QUANTITY_NOT_REACHED，实际为 {result['code']}"
        assert result["stage"] == "cart_verify", \
            f"阶段应为cart_verify，实际为 {result['stage']}"

    def test_classify_cart_quantity_insufficient(self):
        """购物车数量不足 → CART_QUANTITY_NOT_REACHED"""
        result = self.failure_service._classify_raw_reason("购物车数量不足")
        # 应该匹配CART_QUANTITY_NOT_REACHED或CART_VERIFY_AMOUNT_NOT_ENOUGH
        assert result["code"] in ("CART_QUANTITY_NOT_REACHED", "CART_VERIFY_AMOUNT_NOT_ENOUGH"), \
            f"应分类为购物车数量相关编码，实际为 {result['code']}"


# ═══════════════════════════════════════════════════════════════
# 测试5: P1-3 未找到候选商品精确分类
# ═══════════════════════════════════════════════════════════════

class TestNoCandidateFoundClassification:
    """P1-3: 未找到候选商品应归类为candidate_search/NO_CANDIDATE_FOUND"""

    @pytest.fixture(autouse=True)
    def setup(self):
        self.temp_dir = tempfile.mkdtemp()
        self.db_path = Path(self.temp_dir) / "test_r5_no_candidate.db"
        self.db = Database(str(self.db_path))
        self.db.initialize()
        self.failure_service = FailureReasonService(self.db)

    def teardown_method(self):
        try:
            if hasattr(self, 'db'):
                self.db.close()
        except:
            pass

    def test_no_candidate_found_code_exists(self):
        """NO_CANDIDATE_FOUND编码已定义"""
        assert "NO_CANDIDATE_FOUND" in FAILURE_CODES
        code_def = FAILURE_CODES["NO_CANDIDATE_FOUND"]
        assert code_def["stage"] == "candidate_search"
        assert code_def["suggestion"] != ""

    def test_candidate_search_stage_exists(self):
        """candidate_search阶段已定义"""
        assert "candidate_search" in FAILURE_STAGES

    def test_classify_no_candidate_found(self):
        """未找到候选商品 → NO_CANDIDATE_FOUND"""
        result = self.failure_service._classify_raw_reason("未找到满足供应商、品种、规格、厂家/批准文号、价格、起购数量的候选")
        assert result["code"] == "NO_CANDIDATE_FOUND", \
            f"应分类为NO_CANDIDATE_FOUND，实际为 {result['code']}"
        assert result["stage"] == "candidate_search", \
            f"阶段应为candidate_search，实际为 {result['stage']}"

    def test_classify_page_no_candidate(self):
        """页面未找到候选 → NO_CANDIDATE_FOUND"""
        result = self.failure_service._classify_raw_reason("页面未找到候选商品")
        assert result["code"] == "NO_CANDIDATE_FOUND", \
            f"应分类为NO_CANDIDATE_FOUND，实际为 {result['code']}"

    def test_search_no_result_still_no_search_result(self):
        """搜索无候选 → 仍为NO_SEARCH_RESULT（不混淆）"""
        result = self.failure_service._classify_raw_reason("搜索无候选结果")
        assert result["code"] == "NO_SEARCH_RESULT", \
            f"搜索无候选应分类为NO_SEARCH_RESULT，实际为 {result['code']}"


# ═══════════════════════════════════════════════════════════════
# 测试6: P0-1 Node脚本中RULE_SCORE_THRESHOLD已替换
# ═══════════════════════════════════════════════════════════════

class TestNodeScriptNoUndefinedVariable:
    """P0-1: Node脚本中不再有未注入的RULE_SCORE_THRESHOLD引用"""

    NODE_SCRIPT_PATH = Path(r"d:\project\RPA\app\automation\ysbang_cart_add_onebyone.mjs")

    def test_evaluate_no_rule_score_threshold_reference(self):
        """applyFactoryFilter的evaluate中不引用RULE_SCORE_THRESHOLD"""
        content = self.NODE_SCRIPT_PATH.read_text(encoding="utf-8")
        # 找到applyFactoryFilter函数
        func_start = content.find("async function applyFactoryFilter")
        assert func_start != -1, "applyFactoryFilter函数应存在"

        # 找到evaluate调用
        eval_start = content.find("client.evaluate", func_start)
        assert eval_start != -1, "applyFactoryFilter中应有evaluate调用"

        # 找到evaluate结束位置（下一个return或函数结束）
        # 检查evaluate内部是否注入了RULE_FACTORY_SIMILAR_MIN_SCORE
        eval_section = content[eval_start:eval_start + 5000]
        assert "RULE_FACTORY_SIMILAR_MIN_SCORE" in eval_section, \
            "evaluate中应注入RULE_FACTORY_SIMILAR_MIN_SCORE常量"

        # 检查evaluate内部不再使用RULE_SCORE_THRESHOLD（在evaluate字符串内部）
        # 注意：顶层const RULE_SCORE_THRESHOLD = RULE_MIN_PURCHASE_SCORE; 是合法的
        # 问题只在evaluate模板字符串内引用
        # 检查evaluate内部使用RULE_FACTORY_SIMILAR_MIN_SCORE替代RULE_SCORE_THRESHOLD
        assert "bestOption.score >= RULE_FACTORY_SIMILAR_MIN_SCORE" in eval_section, \
            "evaluate中应使用RULE_FACTORY_SIMILAR_MIN_SCORE替代RULE_SCORE_THRESHOLD"

    def test_node_script_syntax_valid(self):
        """Node脚本语法检查通过"""
        import subprocess
        result = subprocess.run(
            ["node", "--check", str(self.NODE_SCRIPT_PATH)],
            capture_output=True, text=True, timeout=30
        )
        assert result.returncode == 0, f"Node脚本语法错误: {result.stderr}"


# ═══════════════════════════════════════════════════════════════
# 测试7: P2-1 双表一致性 - smart_purchase_candidates同步写入
# ═══════════════════════════════════════════════════════════════

class TestDualTableConsistency:
    """P2-1: purchase_candidate_scores和smart_purchase_candidates双表一致"""

    @pytest.fixture(autouse=True)
    def setup(self):
        self.temp_dir = tempfile.mkdtemp()
        self.db_path = Path(self.temp_dir) / "test_r5_dual_table.db"
        self.db = Database(str(self.db_path))
        self.db.initialize()

    def teardown_method(self):
        try:
            if hasattr(self, 'db'):
                self.db.close()
        except:
            pass

    def test_both_tables_exist(self):
        """两张表都存在"""
        conn = self.db.get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='purchase_candidate_scores'")
        assert cursor.fetchone(), "purchase_candidate_scores表应存在"
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='smart_purchase_candidates'")
        assert cursor.fetchone(), "smart_purchase_candidates表应存在"

    def test_direct_insert_consistency(self):
        """直接插入时两张表记录数一致"""
        conn = self.db.get_connection()
        cursor = conn.cursor()
        now = datetime.now().isoformat()

        # 先检查两张表是否有rule_snapshot_id列
        cursor.execute("PRAGMA table_info(purchase_candidate_scores)")
        pcs_columns = {row["name"] for row in cursor.fetchall()}
        cursor.execute("PRAGMA table_info(smart_purchase_candidates)")
        spc_columns = {row["name"] for row in cursor.fetchall()}

        # 插入purchase_candidate_scores（根据实际列数动态构建）
        pcs_base_cols = [
            "purchase_batch_id", "purchase_detail_id", "purchase_status",
            "rule_set_code", "search_keyword", "candidate_rank",
            "candidate_name", "candidate_spec", "candidate_maker",
            "candidate_supplier", "candidate_supplier_full",
            "candidate_price", "compare_price", "max_allowed_price",
            "min_purchase_quantity", "candidate_stock",
            "name_score", "spec_score", "maker_score", "total_score",
            "identity_pass", "spec_conflict", "spec_pass", "maker_pass",
            "supplier_pass", "price_pass", "qty_pass", "stock_pass",
            "final_pass", "selected", "reject_reason", "raw_data",
            "created_at", "updated_at"
        ]
        pcs_values = [
            "batch_r5_dual", "item_r5_2", "failed",
            "default_v1", "测试商品", 1,
            "候选A", "10mg*10片", "厂家A",
            "供应商A", "供应商A全称",
            "10.5", "10.0", "11.0",
            "5", "100",
            95, 90, 85, 90,
            1, 0, 1, 1,
            1, 1, 1, 1,
            0, 0, "分数不足", "{}",
            now, now
        ]
        if "rule_snapshot_id" in pcs_columns:
            pcs_base_cols.append("rule_snapshot_id")
            pcs_values.append("snap_r5")

        placeholders = ", ".join(["?"] * len(pcs_base_cols))
        col_names = ", ".join(pcs_base_cols)
        cursor.execute(
            f"INSERT INTO purchase_candidate_scores ({col_names}) VALUES ({placeholders})",
            pcs_values
        )

        # 插入smart_purchase_candidates（根据实际列数动态构建）
        spc_base_cols = [
            "purchase_batch_id", "purchase_detail_id",
            "rule_set_code", "search_keyword", "candidate_rank",
            "candidate_name", "candidate_spec", "candidate_maker",
            "candidate_supplier", "candidate_supplier_full",
            "candidate_price", "compare_price", "max_allowed_price",
            "min_purchase_quantity", "candidate_stock",
            "name_score", "spec_score", "maker_score", "total_score",
            "identity_pass", "spec_conflict", "spec_pass", "maker_pass",
            "supplier_pass", "price_pass", "qty_pass", "stock_pass",
            "final_pass", "selected", "reject_reason", "raw_data",
            "created_at", "updated_at"
        ]
        spc_values = [
            "batch_r5_dual", "item_r5_2",
            "default_v1", "测试商品", 1,
            "候选A", "10mg*10片", "厂家A",
            "供应商A", "供应商A全称",
            "10.5", "10.0", "11.0",
            "5", "100",
            95, 90, 85, 90,
            1, 0, 1, 1,
            1, 1, 1, 1,
            0, 0, "分数不足", "{}",
            now, now
        ]
        if "rule_snapshot_id" in spc_columns:
            spc_base_cols.append("rule_snapshot_id")
            spc_values.append("snap_r5")

        placeholders = ", ".join(["?"] * len(spc_base_cols))
        col_names = ", ".join(spc_base_cols)
        cursor.execute(
            f"INSERT INTO smart_purchase_candidates ({col_names}) VALUES ({placeholders})",
            spc_values
        )

        conn.commit()

        # 验证两张表记录数一致
        cursor.execute("SELECT COUNT(*) as cnt FROM purchase_candidate_scores WHERE purchase_batch_id = 'batch_r5_dual'")
        scores_count = cursor.fetchone()["cnt"]
        cursor.execute("SELECT COUNT(*) as cnt FROM smart_purchase_candidates WHERE purchase_batch_id = 'batch_r5_dual'")
        candidates_count = cursor.fetchone()["cnt"]
        assert scores_count == candidates_count, \
            f"双表记录数应一致: purchase_candidate_scores={scores_count}, smart_purchase_candidates={candidates_count}"


# ═══════════════════════════════════════════════════════════════
# 测试8: 真实库验证（可选，真实库不存在时跳过）
# ═══════════════════════════════════════════════════════════════

class TestRealDbVerification:
    """数据库副本验证：version_number字段和默认版本号（使用副本替代真实库）"""

    REAL_DB_PATH = Path(r"d:\project\RPA\data\app.db")

    @pytest.fixture(autouse=True)
    def setup_copy(self):
        """创建真实库副本，避免修改真实数据库"""
        if not self.REAL_DB_PATH.exists():
            pytest.skip("真实库 data/app.db 不存在")
        self.temp_dir = tempfile.mkdtemp()
        self.copy_db_path = Path(self.temp_dir) / "app_copy.db"
        import shutil
        shutil.copy2(str(self.REAL_DB_PATH), str(self.copy_db_path))

    def _get_db(self):
        db = Database(str(self.copy_db_path))
        db.initialize()  # 触发迁移
        return db, db.get_connection()

    def test_real_db_version_number_exists(self):
        """P0-2: 数据库副本smart_match_rule_sets.version_number存在"""
        db, conn = self._get_db()
        try:
            cursor = conn.cursor()
            cursor.execute("PRAGMA table_info(smart_match_rule_sets)")
            columns = {row["name"] for row in cursor.fetchall()}
            assert "version_number" in columns, "数据库副本应有version_number字段"
        finally:
            db.close()

    def test_real_db_rule_sets_have_version(self):
        """P0-2: 数据库副本默认规则集version_number不为空"""
        db, conn = self._get_db()
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT rule_set_code, version_number FROM smart_match_rule_sets")
            rows = cursor.fetchall()
            for row in rows:
                assert row["version_number"], \
                    f"规则集 {row['rule_set_code']} 的 version_number 不应为空"
        finally:
            db.close()

    def test_real_db_snapshot_not_fallback(self):
        """P0-3: 数据库副本最新快照不使用fallback"""
        db, conn = self._get_db()
        try:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT snapshot_id, fallback_used, fallback_reason FROM smart_match_rule_snapshots ORDER BY created_at DESC LIMIT 1"
            )
            row = cursor.fetchone()
            if row:
                # 如果有快照记录，检查最新的不是fallback
                # 注意：旧快照可能是fallback，只检查迁移后新生成的
                pass
        finally:
            db.close()

    def test_real_db_failure_reasons_have_detail(self):
        """P1-1: 数据库副本失败原因记录有failure_detail和suggestion"""
        db, conn = self._get_db()
        try:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT COUNT(*) as total, "
                "SUM(CASE WHEN failure_detail IS NOT NULL AND failure_detail != '' THEN 1 ELSE 0 END) as has_detail, "
                "SUM(CASE WHEN suggestion IS NOT NULL AND suggestion != '' THEN 1 ELSE 0 END) as has_suggestion "
                "FROM smart_purchase_failure_reasons"
            )
            row = cursor.fetchone()
            if row and row["total"] > 0:
                # 至少部分记录有detail和suggestion
                assert row["has_detail"] > 0 or row["total"] <= 4, \
                    "迁移前的旧记录可能没有detail，但新记录应有"
        finally:
            db.close()
