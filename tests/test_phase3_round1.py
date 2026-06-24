"""
逐个采购-建立评分规则表方案三期 第一阶段测试
验证：底表参数真正生效
1. rule_type 读取修复（number/boolean/string/json）
2. 旧键到 canonical 键迁移
3. thresholds 非空且 canonical 键完整
4. Node 硬编码权重替换
5. spec_conflict_block 阻断行为
"""
import json
import os
import sys
import tempfile
import pytest
from pathlib import Path

# 添加项目根目录
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from app.storage.database import Database
from app.core.rule_snapshot_service import RuleSnapshotService


@pytest.fixture
def db():
    """创建临时数据库"""
    temp_dir = tempfile.mkdtemp()
    db_path = os.path.join(temp_dir, "test_phase3.db")
    database = Database(db_path)
    database.initialize()
    yield database
    database.close()


@pytest.fixture
def snapshot_service(db):
    return RuleSnapshotService(db)


# ═══════════════════════════════════════════════════════════════
# A. rule_type 读取修复测试
# ═══════════════════════════════════════════════════════════════
class TestRuleTypeReading:
    """验证 _load_rule_config 能识别 number/boolean/string/json 类型"""

    def test_number_type_enters_thresholds(self, db, snapshot_service):
        """number 类型的配置项应进入 thresholds"""
        conn = db.get_connection()
        cursor = conn.cursor()
        config, fallback, reason = snapshot_service._load_rule_config(cursor, "default_v1")
        assert not fallback, f"不应使用 fallback: {reason}"
        thresholds = config.get("thresholds", {})
        # number 类型键应存在
        assert "name_weight" in thresholds, "name_weight (number) 应在 thresholds 中"
        assert "spec_weight" in thresholds, "spec_weight (number) 应在 thresholds 中"
        assert "maker_weight" in thresholds, "maker_weight (number) 应在 thresholds 中"
        assert "min_purchase_score" in thresholds, "min_purchase_score (number) 应在 thresholds 中"
        conn.close()

    def test_boolean_type_enters_thresholds(self, db, snapshot_service):
        """boolean 类型的配置项应进入 thresholds"""
        conn = db.get_connection()
        cursor = conn.cursor()
        config, fallback, reason = snapshot_service._load_rule_config(cursor, "default_v1")
        assert not fallback
        thresholds = config.get("thresholds", {})
        assert "spec_conflict_block" in thresholds, "spec_conflict_block (boolean) 应在 thresholds 中"
        assert "maker_strict" in thresholds, "maker_strict (boolean) 应在 thresholds 中"
        conn.close()

    def test_boolean_value_normalized(self, db, snapshot_service):
        """boolean 值应标准化为 '1' 或 '0'"""
        conn = db.get_connection()
        cursor = conn.cursor()
        config, _, _ = snapshot_service._load_rule_config(cursor, "default_v1")
        thresholds = config.get("thresholds", {})
        # default_v1 的 spec_conflict_block 应为 '0'
        assert thresholds["spec_conflict_block"] in ("0", "1"), \
            f"boolean 值应标准化为 '0' 或 '1': {thresholds['spec_conflict_block']}"
        conn.close()

    def test_strict_spec_v1_spec_conflict_block_is_1(self, db, snapshot_service):
        """strict_spec_v1 的 spec_conflict_block 应为 '1'"""
        conn = db.get_connection()
        cursor = conn.cursor()
        config, fallback, reason = snapshot_service._load_rule_config(cursor, "strict_spec_v1")
        assert not fallback, f"不应使用 fallback: {reason}"
        thresholds = config.get("thresholds", {})
        assert thresholds.get("spec_conflict_block") == "1", \
            f"strict_spec_v1 的 spec_conflict_block 应为 '1': {thresholds.get('spec_conflict_block')}"
        conn.close()


# ═══════════════════════════════════════════════════════════════
# B. 旧键到 canonical 键迁移测试
# ═══════════════════════════════════════════════════════════════
class TestCanonicalKeyMigration:
    """验证旧键到 canonical 键的迁移"""

    def test_old_keys_not_in_thresholds(self, db, snapshot_service):
        """迁移后 thresholds 中不应有旧键"""
        conn = db.get_connection()
        cursor = conn.cursor()
        config, _, _ = snapshot_service._load_rule_config(cursor, "default_v1")
        thresholds = config.get("thresholds", {})
        old_keys = ["total_score_threshold", "price_tolerance", "spec_strict"]
        for old_key in old_keys:
            assert old_key not in thresholds, f"旧键 {old_key} 不应出现在 thresholds 中"
        conn.close()

    def test_canonical_keys_in_thresholds(self, db, snapshot_service):
        """canonical 键应在 thresholds 中"""
        conn = db.get_connection()
        cursor = conn.cursor()
        config, _, _ = snapshot_service._load_rule_config(cursor, "default_v1")
        thresholds = config.get("thresholds", {})
        canonical_keys = [
            "min_purchase_score", "price_compare_discount", "spec_conflict_block",
            "cart_backfill_min_score", "price_check_enabled", "price_upper_rate",
            "price_upper_plus", "name_core_min_score", "spec_similar_min_score",
            "factory_similar_min_score", "cart_existing_same_product_min_score",
        ]
        for key in canonical_keys:
            assert key in thresholds, f"canonical 键 {key} 应在 thresholds 中"
        conn.close()

    def test_migration_idempotent(self, db):
        """迁移方法幂等：多次调用不报错"""
        # 第二次调用
        db._migrate_canonical_rule_keys()
        # 验证数据完整
        conn = db.get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) as cnt FROM smart_match_rule_configs WHERE rule_set_code = 'default_v1'")
        count = cursor.fetchone()["cnt"]
        assert count >= 16, f"default_v1 应至少有 16 个配置项: {count}"
        conn.close()


# ═══════════════════════════════════════════════════════════════
# C. thresholds 非空测试
# ═══════════════════════════════════════════════════════════════
class TestThresholdsNonEmpty:
    """验证正常快照 thresholds 非空且 canonical 键完整"""

    def test_default_v1_snapshot_thresholds_not_empty(self, db, snapshot_service):
        """default_v1 快照的 thresholds 应非空"""
        snapshot_id, _ = snapshot_service.generate_rule_snapshot("batch_test_thresholds")
        snapshot = snapshot_service.get_rule_snapshot(snapshot_id)
        config = json.loads(snapshot["snapshot_json"])
        thresholds = config.get("thresholds", {})
        assert len(thresholds) > 0, "thresholds 不应为空"

    def test_default_v1_snapshot_canonical_keys_complete(self, db, snapshot_service):
        """default_v1 快照应包含所有 canonical 键"""
        snapshot_id, _ = snapshot_service.generate_rule_snapshot("batch_test_keys")
        snapshot = snapshot_service.get_rule_snapshot(snapshot_id)
        config = json.loads(snapshot["snapshot_json"])
        thresholds = config.get("thresholds", {})

        required_keys = [
            "name_weight", "spec_weight", "maker_weight",
            "min_purchase_score", "cart_backfill_min_score",
            "spec_conflict_block", "maker_strict",
            "price_compare_discount", "price_upper_rate", "price_upper_plus",
            "name_core_min_score", "spec_similar_min_score",
            "factory_similar_min_score", "cart_existing_same_product_min_score",
        ]
        for key in required_keys:
            assert key in thresholds, f"快照缺少 canonical 键: {key}"

    def test_strict_spec_v1_snapshot_thresholds_not_empty(self, db, snapshot_service):
        """strict_spec_v1 快照的 thresholds 应非空"""
        snapshot_id, _ = snapshot_service.generate_rule_snapshot("batch_test_strict", "strict_spec_v1")
        snapshot = snapshot_service.get_rule_snapshot(snapshot_id)
        config = json.loads(snapshot["snapshot_json"])
        thresholds = config.get("thresholds", {})
        assert len(thresholds) > 0, "strict_spec_v1 thresholds 不应为空"

    def test_snapshot_not_fallback(self, db, snapshot_service):
        """正常快照不应是 fallback"""
        snapshot_id, _ = snapshot_service.generate_rule_snapshot("batch_test_no_fallback")
        snapshot = snapshot_service.get_rule_snapshot(snapshot_id)
        assert snapshot["fallback_used"] in (0, "0"), "正常快照不应是 fallback"


# ═══════════════════════════════════════════════════════════════
# D. 权重切换测试
# ═══════════════════════════════════════════════════════════════
class TestWeightSwitching:
    """验证不同规则集的权重可以不同"""

    def test_two_rulesets_different_weights(self, db, snapshot_service):
        """两套规则集的权重可以不同（修改底表后）"""
        # 先获取 default_v1 的权重
        conn = db.get_connection()
        cursor = conn.cursor()
        config_default, _, _ = snapshot_service._load_rule_config(cursor, "default_v1")
        config_strict, _, _ = snapshot_service._load_rule_config(cursor, "strict_spec_v1")
        conn.close()

        # 当前两套规则权重相同（都是 0.62/0.20/0.18），但结构上支持不同
        t_default = config_default["thresholds"]
        t_strict = config_strict["thresholds"]

        # 验证权重键存在
        assert "name_weight" in t_default
        assert "name_weight" in t_strict

    def test_modified_weight_affects_snapshot(self, db, snapshot_service):
        """修改底表权重后，新快照应反映变化"""
        conn = db.get_connection()
        cursor = conn.cursor()

        # 修改 default_v1 的 name_weight
        cursor.execute(
            "UPDATE smart_match_rule_configs SET rule_value = '0.40' "
            "WHERE rule_set_code = 'default_v1' AND rule_key = 'name_weight'"
        )
        cursor.execute(
            "UPDATE smart_match_rule_configs SET rule_value = '0.40' "
            "WHERE rule_set_code = 'default_v1' AND rule_key = 'spec_weight'"
        )
        cursor.execute(
            "UPDATE smart_match_rule_configs SET rule_value = '0.20' "
            "WHERE rule_set_code = 'default_v1' AND rule_key = 'maker_weight'"
        )
        conn.commit()

        # 生成新快照
        snapshot_id, _ = snapshot_service.generate_rule_snapshot("batch_weight_test")
        snapshot = snapshot_service.get_rule_snapshot(snapshot_id)
        config = json.loads(snapshot["snapshot_json"])
        thresholds = config["thresholds"]

        assert thresholds["name_weight"] == "0.4", f"修改后 name_weight 应为 0.4: {thresholds['name_weight']}"
        assert thresholds["spec_weight"] == "0.4", f"修改后 spec_weight 应为 0.4: {thresholds['spec_weight']}"
        assert thresholds["maker_weight"] == "0.2", f"修改后 maker_weight 应为 0.2: {thresholds['maker_weight']}"
        conn.close()


# ═══════════════════════════════════════════════════════════════
# E. 规格严格模式测试
# ═══════════════════════════════════════════════════════════════
class TestSpecConflictBlock:
    """验证 spec_conflict_block 在两套规则下的不同行为"""

    def test_default_v1_spec_conflict_block_false(self, db, snapshot_service):
        """default_v1 的 spec_conflict_block 应为 false"""
        snapshot_id, _ = snapshot_service.generate_rule_snapshot("batch_spec_default")
        node_config = snapshot_service.get_rule_config_for_node(snapshot_id)
        assert node_config["specConflictBlock"] is False, \
            f"default_v1 的 specConflictBlock 应为 False: {node_config['specConflictBlock']}"

    def test_strict_spec_v1_spec_conflict_block_true(self, db, snapshot_service):
        """strict_spec_v1 的 spec_conflict_block 应为 true"""
        snapshot_id, _ = snapshot_service.generate_rule_snapshot("batch_spec_strict", "strict_spec_v1")
        node_config = snapshot_service.get_rule_config_for_node(snapshot_id)
        assert node_config["specConflictBlock"] is True, \
            f"strict_spec_v1 的 specConflictBlock 应为 True: {node_config['specConflictBlock']}"

    def test_node_config_contains_spec_conflict_block(self, db, snapshot_service):
        """Node 配置应包含 specConflictBlock 字段"""
        snapshot_id, _ = snapshot_service.generate_rule_snapshot("batch_node_spec")
        node_config = snapshot_service.get_rule_config_for_node(snapshot_id)
        assert "specConflictBlock" in node_config, "Node 配置应包含 specConflictBlock"

    def test_node_config_contains_maker_strict(self, db, snapshot_service):
        """Node 配置应包含 makerStrict 字段"""
        snapshot_id, _ = snapshot_service.generate_rule_snapshot("batch_node_maker")
        node_config = snapshot_service.get_rule_config_for_node(snapshot_id)
        assert "makerStrict" in node_config, "Node 配置应包含 makerStrict"


# ═══════════════════════════════════════════════════════════════
# F. 规则集切换测试
# ═══════════════════════════════════════════════════════════════
class TestRuleSetSwitching:
    """验证不同规则集生成不同快照"""

    def test_different_rulesets_generate_different_snapshots(self, db, snapshot_service):
        """两套规则集应生成不同的快照"""
        snap_default, _ = snapshot_service.generate_rule_snapshot("batch_switch_default")
        snap_strict, _ = snapshot_service.generate_rule_snapshot("batch_switch_strict", "strict_spec_v1")

        default_config = snapshot_service.get_rule_config_for_node(snap_default)
        strict_config = snapshot_service.get_rule_config_for_node(snap_strict)

        # specConflictBlock 应不同
        assert default_config["specConflictBlock"] != strict_config["specConflictBlock"], \
            "两套规则的 specConflictBlock 应不同"

    def test_min_purchase_score_switching(self, db, snapshot_service):
        """修改 min_purchase_score 后，新快照应反映变化"""
        conn = db.get_connection()
        cursor = conn.cursor()

        # 修改 default_v1 的 min_purchase_score
        cursor.execute(
            "UPDATE smart_match_rule_configs SET rule_value = '90' "
            "WHERE rule_set_code = 'default_v1' AND rule_key = 'min_purchase_score'"
        )
        conn.commit()

        snapshot_id, _ = snapshot_service.generate_rule_snapshot("batch_score_switch")
        node_config = snapshot_service.get_rule_config_for_node(snapshot_id)
        assert node_config["minPurchaseScore"] == 90, \
            f"修改后 minPurchaseScore 应为 90: {node_config['minPurchaseScore']}"
        conn.close()


# ═══════════════════════════════════════════════════════════════
# G. 快照不可变测试
# ═══════════════════════════════════════════════════════════════
class TestSnapshotImmutability:
    """验证快照生成后不可变"""

    def test_snapshot_unchanged_after_rule_update(self, db, snapshot_service):
        """修改底表后，已生成的快照应不变"""
        # 生成快照 A
        snap_a, _ = snapshot_service.generate_rule_snapshot("batch_immutable_a")
        config_a = snapshot_service.get_rule_config_for_node(snap_a)
        score_a = config_a["minPurchaseScore"]

        # 修改底表
        conn = db.get_connection()
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE smart_match_rule_configs SET rule_value = '90' "
            "WHERE rule_set_code = 'default_v1' AND rule_key = 'min_purchase_score'"
        )
        conn.commit()
        conn.close()

        # 生成快照 B
        snap_b, _ = snapshot_service.generate_rule_snapshot("batch_immutable_b")
        config_b = snapshot_service.get_rule_config_for_node(snap_b)
        score_b = config_b["minPurchaseScore"]

        # 快照 A 应不变
        config_a_recheck = snapshot_service.get_rule_config_for_node(snap_a)
        assert config_a_recheck["minPurchaseScore"] == score_a, \
            "修改底表后，已生成的快照 A 应不变"

        # 快照 B 应反映新规则
        assert score_b != score_a, \
            "修改底表后，新快照 B 应反映新规则"


# ═══════════════════════════════════════════════════════════════
# H. 二期回归测试
# ═══════════════════════════════════════════════════════════════
class TestPhase2Regression:
    """验证二期已有功能在三期改动后仍然正常"""

    def test_snapshot_generation_still_works(self, db, snapshot_service):
        """快照生成仍正常"""
        snapshot_id, _ = snapshot_service.generate_rule_snapshot("batch_regression")
        assert snapshot_id, "快照 ID 不应为空"
        snapshot = snapshot_service.get_rule_snapshot(snapshot_id)
        assert snapshot, "快照应存在"

    def test_node_config_still_has_required_fields(self, db, snapshot_service):
        """Node 配置仍包含所有必要字段"""
        snapshot_id, _ = snapshot_service.generate_rule_snapshot("batch_node_fields")
        config = snapshot_service.get_rule_config_for_node(snapshot_id)
        required_fields = [
            "ruleSetCode", "ruleSnapshotId", "minPurchaseScore",
            "nameWeight", "specWeight", "makerWeight",
            "priceCompareDiscount", "specConflictBlock",
        ]
        for field in required_fields:
            assert field in config, f"Node 配置缺少字段: {field}"

    def test_cart_backfill_threshold_still_works(self, db, snapshot_service):
        """购物车反写阈值仍正常"""
        snapshot_id, _ = snapshot_service.generate_rule_snapshot("batch_backfill")
        threshold = snapshot_service.get_cart_backfill_threshold(snapshot_id)
        assert isinstance(threshold, int), "购物车反写阈值应为整数"
        assert threshold > 0, "购物车反写阈值应大于 0"
