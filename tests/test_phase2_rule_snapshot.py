"""
逐个采购-建立评分规则表方案二期整改自动化测试
根据第一轮测试结果与调整方案（2026-06-19）要求
"""
import pytest
import tempfile
import json
from datetime import datetime
from pathlib import Path

from app.storage.database import Database
from app.core.smart_purchase_service import SmartPurchaseService
from app.core.rule_snapshot_service import RuleSnapshotService
from app.core.failure_reason_service import FailureReasonService


class TestRuleSnapshot:
    """P0-1: 规则运行快照表和生成逻辑"""

    @pytest.fixture(autouse=True)
    def setup(self):
        self.temp_dir = tempfile.mkdtemp()
        self.db_path = Path(self.temp_dir) / "test_rule_snapshot.db"
        self.db = Database(str(self.db_path))
        self.db.initialize()
        self.snapshot_service = RuleSnapshotService(self.db)

    def teardown(self):
        try:
            if hasattr(self, 'db'):
                self.db.close()
        except:
            pass

    def test_snapshot_table_exists(self):
        """smart_match_rule_snapshots 表存在"""
        conn = self.db.get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='smart_match_rule_snapshots'")
        assert cursor.fetchone() is not None

    def test_generate_snapshot_success(self):
        """生成规则快照成功，返回有效 snapshot_id"""
        snapshot_id, error = self.snapshot_service.generate_rule_snapshot("batch_001")
        assert snapshot_id != "", f"生成快照失败: {error}"
        assert snapshot_id.startswith("snapshot_batch_001_")

    def test_snapshot_saved_to_db(self):
        """快照数据正确落库"""
        snapshot_id, _ = self.snapshot_service.generate_rule_snapshot("batch_002")
        conn = self.db.get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT snapshot_id, batch_id, snapshot_json FROM smart_match_rule_snapshots WHERE snapshot_id=?", (snapshot_id,))
        row = cursor.fetchone()
        assert row is not None
        assert row["batch_id"] == "batch_002"
        snapshot_json = json.loads(row["snapshot_json"])
        assert "thresholds" in snapshot_json
        assert "ruleSetCode" in snapshot_json

    def test_snapshot_fallback_on_missing_rule_set(self):
        """规则集不存在时使用 fallback 快照"""
        snapshot_id, error = self.snapshot_service.generate_rule_snapshot("batch_003", "nonexistent_rule_set")
        assert snapshot_id != "", f"fallback快照生成失败: {error}"
        conn = self.db.get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT fallback_used, fallback_reason FROM smart_match_rule_snapshots WHERE snapshot_id=?", (snapshot_id,))
        row = cursor.fetchone()
        assert row["fallback_used"] == 1
        assert row["fallback_reason"] != ""

    def test_get_rule_config_for_node(self):
        """获取供 Node 使用的规则配置"""
        snapshot_id, _ = self.snapshot_service.generate_rule_snapshot("batch_004")
        config = self.snapshot_service.get_rule_config_for_node(snapshot_id)
        assert "ruleSetCode" in config
        assert "ruleSnapshotId" in config
        assert config["ruleSnapshotId"] == snapshot_id
        assert "nameWeight" in config
        assert "specWeight" in config
        assert "makerWeight" in config
        assert "priceCompareDiscount" in config

    def test_get_batch_snapshot(self):
        """按批次获取最新快照"""
        self.snapshot_service.generate_rule_snapshot("batch_005")
        snapshot = self.snapshot_service.get_batch_snapshot("batch_005")
        assert snapshot != {}
        assert snapshot["batch_id"] == "batch_005"

    def test_snapshot_json_contains_failure_codes(self):
        """快照 JSON 包含 failureCodes 列表"""
        snapshot_id, _ = self.snapshot_service.generate_rule_snapshot("batch_006")
        snapshot = self.snapshot_service.get_rule_snapshot(snapshot_id)
        config = json.loads(snapshot["snapshot_json"])
        assert "failureCodes" in config
        assert len(config["failureCodes"]) > 0
        assert "SPEC_CONFLICT" in config["failureCodes"]
        assert "PRICE_OVER_LIMIT" in config["failureCodes"]


class TestRuleSnapshotAssociation:
    """P0-2: 候选/反写表关联 rule_snapshot_id"""

    @pytest.fixture(autouse=True)
    def setup(self):
        self.temp_dir = tempfile.mkdtemp()
        self.db_path = Path(self.temp_dir) / "test_snapshot_assoc.db"
        self.db = Database(str(self.db_path))
        self.db.initialize()
        self.service = SmartPurchaseService(self.db)

    def teardown(self):
        try:
            if hasattr(self, 'db'):
                self.db.close()
        except:
            pass

    def test_candidates_has_rule_snapshot_id_column(self):
        """smart_purchase_candidates 表有 rule_snapshot_id 字段"""
        conn = self.db.get_connection()
        cursor = conn.cursor()
        cursor.execute("PRAGMA table_info(smart_purchase_candidates)")
        columns = [row["name"] for row in cursor.fetchall()]
        assert "rule_snapshot_id" in columns

    def test_backfill_matches_has_rule_snapshot_id_column(self):
        """smart_cart_backfill_matches 表有 rule_snapshot_id 字段"""
        conn = self.db.get_connection()
        cursor = conn.cursor()
        cursor.execute("PRAGMA table_info(smart_cart_backfill_matches)")
        columns = [row["name"] for row in cursor.fetchall()]
        assert "rule_snapshot_id" in columns

    def test_candidate_save_with_snapshot_id(self):
        """候选评分保存时写入 rule_snapshot_id"""
        conn = self.db.get_connection()
        cursor = conn.cursor()
        candidate_data = {
            "name": "测试商品", "spec": "10mg", "manufacturer": "厂家",
            "supplier": "供应商", "supplierFull": "供应商全称",
            "price": "10", "minAmount": "1", "stock": "100",
            "score": 85, "detail": {}, "isSelected": True, "reason": "",
        }
        item = {"itemId": "item_001"}
        adapter_item = {"name": "测试商品", "max_allowed_price": "12"}
        self.service._save_single_candidate_score(
            cursor, "batch_001", item, candidate_data, adapter_item, "success", 1, True,
            rule_snapshot_id="snapshot_test_001"
        )
        conn.commit()
        cursor.execute("SELECT rule_snapshot_id FROM smart_purchase_candidates WHERE candidate_rank=1")
        row = cursor.fetchone()
        assert row is not None
        assert row["rule_snapshot_id"] == "snapshot_test_001"

    def test_backfill_save_with_snapshot_id(self):
        """反写匹配保存时写入 rule_snapshot_id"""
        self.service._save_cart_backfill_match(
            "batch_002", "detail_001", "matched", "wholesaleId", 100,
            {"score": 100, "reason": "wholesaleId"},
            snapshot_batch_id="snap_batch_002",
            rule_snapshot_id="snapshot_test_002"
        )
        conn = self.db.get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT rule_snapshot_id FROM smart_cart_backfill_matches WHERE purchase_batch_id='batch_002'")
        row = cursor.fetchone()
        assert row is not None
        assert row["rule_snapshot_id"] == "snapshot_test_002"


class TestFailureReasonStructured:
    """P0-3: 失败原因结构化落库"""

    @pytest.fixture(autouse=True)
    def setup(self):
        self.temp_dir = tempfile.mkdtemp()
        self.db_path = Path(self.temp_dir) / "test_failure_reason.db"
        self.db = Database(str(self.db_path))
        self.db.initialize()
        self.failure_service = FailureReasonService(self.db)

    def teardown(self):
        try:
            if hasattr(self, 'db'):
                self.db.close()
        except:
            pass

    def test_failure_reasons_table_exists(self):
        """smart_purchase_failure_reasons 表存在"""
        conn = self.db.get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='smart_purchase_failure_reasons'")
        assert cursor.fetchone() is not None

    def test_save_failure_reason(self):
        """保存结构化失败原因"""
        self.failure_service.save_failure_reason(
            batch_id="batch_001",
            item_id="item_001",
            row_number=1,
            failure_stage="price_check",
            failure_code="PRICE_OVER_LIMIT",
            failure_message="价格超限",
            failure_detail="候选价15.5 > 最高允许价12.0",
            suggestion="请检查价格上限设置",
            raw_reason="价格超限: 候选价15.5 > 最高允许价12.0",
            rule_set_code="default_v1",
            rule_snapshot_id="snapshot_001"
        )
        conn = self.db.get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM smart_purchase_failure_reasons WHERE batch_id='batch_001'")
        row = cursor.fetchone()
        assert row is not None
        assert row["failure_code"] == "PRICE_OVER_LIMIT"
        assert row["failure_stage"] == "price_check"
        assert row["rule_snapshot_id"] == "snapshot_001"

    def test_classify_raw_reason_price(self):
        """分类原始原因 - 价格超限"""
        result = self.failure_service._classify_raw_reason("价格超限: 候选价15.5 > 最高允许价12.0")
        assert result["code"] == "PRICE_OVER_LIMIT"
        assert result["stage"] == "price_check"

    def test_classify_raw_reason_spec_conflict(self):
        """分类原始原因 - 规格冲突"""
        result = self.failure_service._classify_raw_reason("规格冲突: 包装总数不一致")
        assert result["code"] == "SPEC_CONFLICT"
        assert result["stage"] == "candidate_score"

    def test_classify_raw_reason_no_search(self):
        """分类原始原因 - 搜索无候选"""
        result = self.failure_service._classify_raw_reason("搜索无候选结果")
        assert result["code"] == "NO_SEARCH_RESULT"
        assert result["stage"] == "search_match"

    def test_classify_raw_reason_supplier(self):
        """分类原始原因 - 供应商不在允许范围"""
        result = self.failure_service._classify_raw_reason("供应商不在允许范围内")
        assert result["code"] == "SUPPLIER_NOT_ALLOWED"
        assert result["stage"] == "precheck"

    def test_classify_raw_reason_stock(self):
        """分类原始原因 - 库存不足"""
        result = self.failure_service._classify_raw_reason("库存不足")
        assert result["code"] == "STOCK_NOT_ENOUGH"
        assert result["stage"] == "quantity_check"

    def test_classify_raw_reason_browser(self):
        """分类原始原因 - 浏览器异常"""
        result = self.failure_service._classify_raw_reason("浏览器未找到")
        assert result["code"] == "BROWSER_NOT_FOUND"
        assert result["stage"] == "system_exception"

    def test_classify_raw_reason_unknown(self):
        """分类原始原因 - 未知异常"""
        result = self.failure_service._classify_raw_reason("某种未知的奇怪错误")
        assert result["code"] == "UNKNOWN_SYSTEM_EXCEPTION"
        assert result["stage"] == "system_exception"

    def test_classify_and_save_failure(self):
        """分类并保存失败原因"""
        result = self.failure_service.classify_and_save_failure(
            batch_id="batch_002",
            item_id="item_002",
            row_number=2,
            raw_reason="价格超限: 候选价20.0 > 最高允许价15.0",
            rule_set_code="default_v1",
            rule_snapshot_id="snapshot_002"
        )
        assert result["code"] == "PRICE_OVER_LIMIT"
        conn = self.db.get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM smart_purchase_failure_reasons WHERE batch_id='batch_002'")
        row = cursor.fetchone()
        assert row is not None
        assert row["failure_code"] == "PRICE_OVER_LIMIT"

    def test_failure_stats_by_code(self):
        """按失败编码聚合统计"""
        self.failure_service.save_failure_reason(
            "batch_003", "item_001", 1, "price_check", "PRICE_OVER_LIMIT", "价格超限"
        )
        self.failure_service.save_failure_reason(
            "batch_003", "item_002", 2, "price_check", "PRICE_OVER_LIMIT", "价格超限"
        )
        self.failure_service.save_failure_reason(
            "batch_003", "item_003", 3, "candidate_score", "SPEC_CONFLICT", "规格冲突"
        )
        stats = self.failure_service.get_failure_stats_by_code(batch_id="batch_003")
        assert len(stats) == 2
        price_stat = next(s for s in stats if s["failure_code"] == "PRICE_OVER_LIMIT")
        assert price_stat["count"] == 2
        spec_stat = next(s for s in stats if s["failure_code"] == "SPEC_CONFLICT")
        assert spec_stat["count"] == 1

    def test_items_table_has_failure_columns(self):
        """smart_purchase_items 表有 failure_stage 和 failure_code 字段"""
        # 需要SmartPurchaseService来创建smart_purchase_items表
        service = SmartPurchaseService(self.db)
        conn = self.db.get_connection()
        cursor = conn.cursor()
        cursor.execute("PRAGMA table_info(smart_purchase_items)")
        columns = [row["name"] for row in cursor.fetchall()]
        assert "failure_stage" in columns
        assert "failure_code" in columns


class TestNodeFailureClassification:
    """P1-1: Node 返回结构化失败编码"""

    def test_classify_node_failure_with_codes(self):
        """Node 结果中包含 failureCode 时直接使用"""
        db = Database(str(Path(tempfile.mkdtemp()) / "test_node_failure.db"))
        db.initialize()
        service = FailureReasonService(db)
        node_result = {
            "failureCode": "PRICE_OVER_LIMIT",
            "failureStage": "price_check",
            "failureDetail": "候选价20.0 > 最高允许价15.0",
            "suggestion": "请检查价格上限设置",
        }
        result = service.classify_node_failure(node_result)
        assert result["code"] == "PRICE_OVER_LIMIT"
        assert result["stage"] == "price_check"
        db.close()

    def test_classify_node_failure_from_reason(self):
        """Node 结果中无 failureCode 时从 reason 分类"""
        db = Database(str(Path(tempfile.mkdtemp()) / "test_node_failure2.db"))
        db.initialize()
        service = FailureReasonService(db)
        node_result = {
            "reason": "规格冲突: 包装总数不一致",
        }
        result = service.classify_node_failure(node_result)
        assert result["code"] == "SPEC_CONFLICT"
        db.close()


class TestPythonNodeRuleConfig:
    """P1-2: Python 调用 Node 时传入 ruleConfig/ruleSnapshot"""

    @pytest.fixture(autouse=True)
    def setup(self):
        self.temp_dir = tempfile.mkdtemp()
        self.db_path = Path(self.temp_dir) / "test_rule_config.db"
        self.db = Database(str(self.db_path))
        self.db.initialize()
        self.service = SmartPurchaseService(self.db)

    def teardown(self):
        try:
            if hasattr(self, 'db'):
                self.db.close()
        except:
            pass

    def test_build_cart_adapter_item_includes_rule_config(self):
        """_build_cart_adapter_item 包含 ruleConfig 和 ruleSnapshotId"""
        item = {
            "item_id": "item_001",
            "row_number": 1,
            "ysb_code": "12345",
            "source_name": "测试商品",
            "source_spec": "10mg",
            "smart_name": "智能商品",
            "smart_spec": "20mg",
            "actual_purchase_quantity": "10",
        }
        base_result = {"max_allowed_price": "15.0"}
        rule_config = {"ruleSetCode": "default_v1", "nameWeight": 0.62}
        adapter_item = self.service._build_cart_adapter_item(
            item, base_result, [],
            rule_config=rule_config, rule_snapshot_id="snapshot_001"
        )
        assert adapter_item["ruleConfig"] == rule_config
        assert adapter_item["ruleSnapshotId"] == "snapshot_001"

    def test_merge_cart_adapter_result_extracts_failure_info(self):
        """_merge_cart_adapter_result 提取 Node 返回的结构化失败编码"""
        base_result = {"purchase_status": "failed", "purchase_reason": ""}
        adapter_result = {
            "status": "failed",
            "reason": "价格超限",
            "failureStage": "price_check",
            "failureCode": "PRICE_OVER_LIMIT",
            "failureDetail": "候选价20.0 > 最高允许价15.0",
            "suggestion": "请检查价格上限设置",
            "ruleSnapshotId": "snapshot_001",
        }
        result = self.service._merge_cart_adapter_result(base_result, adapter_result)
        assert result["failure_stage"] == "price_check"
        assert result["failure_code"] == "PRICE_OVER_LIMIT"
        assert result["failure_detail"] == "候选价20.0 > 最高允许价15.0"
        assert result["suggestion"] == "请检查价格上限设置"
        assert result["rule_snapshot_id"] == "snapshot_001"


class TestRuleSnapshotThresholds:
    """P1-3/P1-4: Node 和 Python 使用规则快照中的阈值"""

    @pytest.fixture(autouse=True)
    def setup(self):
        self.temp_dir = tempfile.mkdtemp()
        self.db_path = Path(self.temp_dir) / "test_thresholds.db"
        self.db = Database(str(self.db_path))
        self.db.initialize()
        self.snapshot_service = RuleSnapshotService(self.db)

    def teardown(self):
        try:
            if hasattr(self, 'db'):
                self.db.close()
        except:
            pass

    def test_get_cart_backfill_threshold(self):
        """获取购物车反写最低分阈值"""
        snapshot_id, _ = self.snapshot_service.generate_rule_snapshot("batch_001")
        threshold = self.snapshot_service.get_cart_backfill_threshold(snapshot_id)
        assert isinstance(threshold, int)
        assert threshold >= 0

    def test_get_min_purchase_score(self):
        """获取采购最低通过分阈值"""
        snapshot_id, _ = self.snapshot_service.generate_rule_snapshot("batch_002")
        score = self.snapshot_service.get_min_purchase_score(snapshot_id)
        assert isinstance(score, int)
        assert score >= 0

    def test_node_config_contains_price_params(self):
        """Node 配置包含价格参数"""
        snapshot_id, _ = self.snapshot_service.generate_rule_snapshot("batch_003")
        config = self.snapshot_service.get_rule_config_for_node(snapshot_id)
        assert "priceCompareDiscount" in config
        assert "priceUpperRate" in config
        assert "priceUpperPlus" in config
        assert config["priceCompareDiscount"] > 0
        assert config["priceUpperRate"] > 0

    def test_node_config_contains_weights(self):
        """Node 配置包含评分权重"""
        snapshot_id, _ = self.snapshot_service.generate_rule_snapshot("batch_004")
        config = self.snapshot_service.get_rule_config_for_node(snapshot_id)
        assert "nameWeight" in config
        assert "specWeight" in config
        assert "makerWeight" in config
        total = config["nameWeight"] + config["specWeight"] + config["makerWeight"]
        assert abs(total - 1.0) < 0.01, f"权重之和应接近1.0，实际为{total}"


class TestSavePurchaseResultWithFailureCode:
    """_save_purchase_result 写入 failure_stage 和 failure_code"""

    @pytest.fixture(autouse=True)
    def setup(self):
        self.temp_dir = tempfile.mkdtemp()
        self.db_path = Path(self.temp_dir) / "test_save_result.db"
        self.db = Database(str(self.db_path))
        self.db.initialize()
        self.service = SmartPurchaseService(self.db)

    def teardown(self):
        try:
            if hasattr(self, 'db'):
                self.db.close()
        except:
            pass

    def _create_purchase_item(self, item_id="item_001", batch_id="batch_001"):
        """创建一条采购明细记录"""
        conn = self.db.get_connection()
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO smart_purchase_items (
                item_id, batch_id, row_number, source_name, purchase_quantity,
                purchase_status, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ''', (item_id, batch_id, 1, "测试商品", "10", "pending",
              datetime.now().isoformat(), datetime.now().isoformat()))
        conn.commit()

    def test_save_failed_result_with_failure_code(self):
        """保存失败结果时写入 failure_stage 和 failure_code"""
        self._create_purchase_item()
        result = {
            "purchase_status": "failed",
            "purchase_reason": "价格超限: 候选价20.0 > 最高允许价15.0",
            "failure_stage": "price_check",
            "failure_code": "PRICE_OVER_LIMIT",
        }
        self.service._save_purchase_result(
            "item_001", result, batch_id="batch_001",
            rule_snapshot_id="snapshot_001", rule_set_code="default_v1"
        )
        conn = self.db.get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT failure_stage, failure_code FROM smart_purchase_items WHERE item_id='item_001'")
        row = cursor.fetchone()
        assert row["failure_stage"] == "price_check"
        assert row["failure_code"] == "PRICE_OVER_LIMIT"

    def test_save_failed_result_auto_classify(self):
        """保存失败结果时自动分类失败编码"""
        self._create_purchase_item("item_002", "batch_002")
        result = {
            "purchase_status": "failed",
            "purchase_reason": "规格冲突: 包装总数不一致",
        }
        self.service._save_purchase_result(
            "item_002", result, batch_id="batch_002",
            rule_snapshot_id="snapshot_002", rule_set_code="default_v1"
        )
        conn = self.db.get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT failure_stage, failure_code FROM smart_purchase_items WHERE item_id='item_002'")
        row = cursor.fetchone()
        assert row["failure_code"] == "SPEC_CONFLICT"
        assert row["failure_stage"] == "candidate_score"

    def test_save_success_result_no_failure_code(self):
        """保存成功结果时无 failure_code"""
        self._create_purchase_item("item_003", "batch_003")
        result = {
            "purchase_status": "success",
            "purchase_reason": "",
            "purchase_supplier": "供应商",
            "purchase_product": "商品",
            "purchase_spec": "10mg",
            "purchase_maker": "厂家",
            "purchase_price": "10.0",
        }
        self.service._save_purchase_result(
            "item_003", result, batch_id="batch_003",
            rule_snapshot_id="snapshot_003", rule_set_code="default_v1"
        )
        conn = self.db.get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT failure_stage, failure_code FROM smart_purchase_items WHERE item_id='item_003'")
        row = cursor.fetchone()
        assert row["failure_stage"] == ""
        assert row["failure_code"] == ""

    def test_failure_reason_saved_to_dedicated_table(self):
        """失败原因同时保存到 smart_purchase_failure_reasons 表"""
        self._create_purchase_item("item_004", "batch_004")
        result = {
            "purchase_status": "failed",
            "purchase_reason": "库存不足",
        }
        self.service._save_purchase_result(
            "item_004", result, batch_id="batch_004",
            rule_snapshot_id="snapshot_004", rule_set_code="default_v1"
        )
        conn = self.db.get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM smart_purchase_failure_reasons WHERE batch_id='batch_004'")
        row = cursor.fetchone()
        assert row is not None
        assert row["failure_code"] == "STOCK_NOT_ENOUGH"
        assert row["rule_snapshot_id"] == "snapshot_004"


class TestEndToEndSnapshotFlow:
    """端到端快照流程验证"""

    @pytest.fixture(autouse=True)
    def setup(self):
        self.temp_dir = tempfile.mkdtemp()
        self.db_path = Path(self.temp_dir) / "test_e2e_snapshot.db"
        self.db = Database(str(self.db_path))
        self.db.initialize()
        self.snapshot_service = RuleSnapshotService(self.db)
        self.failure_service = FailureReasonService(self.db)

    def teardown(self):
        try:
            if hasattr(self, 'db'):
                self.db.close()
        except:
            pass

    def test_full_snapshot_flow(self):
        """完整快照流程：生成快照 -> 获取配置 -> 分类失败 -> 保存失败"""
        # 1. 生成快照
        snapshot_id, error = self.snapshot_service.generate_rule_snapshot("e2e_batch_001")
        assert snapshot_id != "", f"快照生成失败: {error}"

        # 2. 获取 Node 配置
        node_config = self.snapshot_service.get_rule_config_for_node(snapshot_id)
        assert "ruleSetCode" in node_config
        assert node_config["ruleSnapshotId"] == snapshot_id

        # 3. 分类失败原因
        classified = self.failure_service._classify_raw_reason("价格超限: 候选价20.0 > 最高允许价15.0")
        assert classified["code"] == "PRICE_OVER_LIMIT"

        # 4. 保存失败原因
        self.failure_service.save_failure_reason(
            batch_id="e2e_batch_001",
            item_id="item_001",
            row_number=1,
            failure_stage=classified["stage"],
            failure_code=classified["code"],
            failure_message=classified["message"],
            failure_detail=classified["detail"],
            suggestion=classified["suggestion"],
            raw_reason="价格超限: 候选价20.0 > 最高允许价15.0",
            rule_set_code="default_v1",
            rule_snapshot_id=snapshot_id
        )

        # 5. 验证失败原因已关联快照
        conn = self.db.get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM smart_purchase_failure_reasons WHERE batch_id='e2e_batch_001'")
        row = cursor.fetchone()
        assert row is not None
        assert row["failure_code"] == "PRICE_OVER_LIMIT"
        assert row["rule_snapshot_id"] == snapshot_id

        # 6. 验证按编码聚合统计
        stats = self.failure_service.get_failure_stats_by_code(batch_id="e2e_batch_001")
        assert len(stats) == 1
        assert stats[0]["failure_code"] == "PRICE_OVER_LIMIT"
        assert stats[0]["count"] == 1

    def test_snapshot_unique_per_batch(self):
        """每个批次生成唯一快照"""
        sid1, _ = self.snapshot_service.generate_rule_snapshot("e2e_batch_002")
        sid2, _ = self.snapshot_service.generate_rule_snapshot("e2e_batch_002")
        assert sid1 != sid2, "同一批次多次生成快照应产生不同snapshot_id"
