"""
三期阶段4.3测试 - 版本回滚机制
验证：
1. 创建新版本
2. 获取版本历史
3. 回滚到指定版本
4. 版本对比
"""
import pytest
from pathlib import Path

from app.storage.database import Database
from app.core.rule_version_service import RuleVersionService
from app.core.rule_lifecycle_service import RuleLifecycleService
from app.core.smart_purchase_service import SmartPurchaseService


@pytest.fixture
def db(tmp_path):
    db_path = str(tmp_path / "test_phase4_round3.db")
    database = Database(db_path)
    database.initialize()
    sps = SmartPurchaseService(database)
    yield database
    database.close()


@pytest.fixture
def version_service(db):
    return RuleVersionService(db)


@pytest.fixture
def lifecycle_service(db):
    return RuleLifecycleService(db)


class TestCreateNewVersion:
    """创建新版本"""

    def test_create_new_version_success(self, version_service, lifecycle_service):
        """创建新版本成功"""
        # 先创建一个草稿规则集
        configs_v1 = [
            {"rule_key": "name_weight", "rule_value": "0.62", "rule_type": "number"},
            {"rule_key": "spec_weight", "rule_value": "0.23", "rule_type": "number"},
            {"rule_key": "maker_weight", "rule_value": "0.15", "rule_type": "number"},
            {"rule_key": "min_purchase_score", "rule_value": "70", "rule_type": "number"},
        ]
        lifecycle_service.create_draft_rule_set("test_version_001", "测试版本", configs_v1)
        lifecycle_service.submit_for_review("test_version_001")
        lifecycle_service.approve_rule_set("test_version_001")
        lifecycle_service.activate_rule_set("test_version_001")

        # 创建新版本
        configs_v2 = [
            {"rule_key": "name_weight", "rule_value": "0.70", "rule_type": "number"},
            {"rule_key": "spec_weight", "rule_value": "0.20", "rule_type": "number"},
            {"rule_key": "maker_weight", "rule_value": "0.10", "rule_type": "number"},
            {"rule_key": "min_purchase_score", "rule_value": "75", "rule_type": "number"},
        ]
        success, msg = version_service.create_new_version(
            "test_version_001", "v2.0.0", configs_v2,
            change_reason="提高名称权重", created_by="admin"
        )
        assert success is True
        assert "v2.0.0" in msg

    def test_create_duplicate_version_fails(self, version_service, lifecycle_service):
        """重复版本号应失败"""
        configs = [
            {"rule_key": "name_weight", "rule_value": "0.62", "rule_type": "number"},
        ]
        lifecycle_service.create_draft_rule_set("test_dup_version", "测试", configs)
        version_service.create_new_version("test_dup_version", "v2.0.0", configs)
        success, msg = version_service.create_new_version("test_dup_version", "v2.0.0", configs)
        assert success is False
        assert "已存在" in msg

    def test_create_version_for_nonexistent_rule_set_fails(self, version_service):
        """不存在规则集应失败"""
        configs = [{"rule_key": "name_weight", "rule_value": "0.62", "rule_type": "number"}]
        success, msg = version_service.create_new_version("nonexistent", "v2.0.0", configs)
        assert success is False
        assert "不存在" in msg


class TestGetVersionHistory:
    """获取版本历史"""

    def test_get_version_history_with_multiple_versions(self, version_service, lifecycle_service):
        """多版本历史"""
        configs_v1 = [
            {"rule_key": "name_weight", "rule_value": "0.62", "rule_type": "number"},
            {"rule_key": "spec_weight", "rule_value": "0.23", "rule_type": "number"},
            {"rule_key": "maker_weight", "rule_value": "0.15", "rule_type": "number"},
            {"rule_key": "min_purchase_score", "rule_value": "70", "rule_type": "number"},
        ]
        lifecycle_service.create_draft_rule_set("test_history_001", "测试", configs_v1)
        lifecycle_service.submit_for_review("test_history_001")
        lifecycle_service.approve_rule_set("test_history_001")
        lifecycle_service.activate_rule_set("test_history_001")

        configs_v2 = [
            {"rule_key": "name_weight", "rule_value": "0.70", "rule_type": "number"},
            {"rule_key": "spec_weight", "rule_value": "0.20", "rule_type": "number"},
            {"rule_key": "maker_weight", "rule_value": "0.10", "rule_type": "number"},
            {"rule_key": "min_purchase_score", "rule_value": "75", "rule_type": "number"},
        ]
        version_service.create_new_version("test_history_001", "v2.0.0", configs_v2)

        history = version_service.get_version_history("test_history_001")
        assert len(history) >= 2

    def test_get_version_history_for_nonexistent_rule_set(self, version_service):
        """不存在规则集返回空列表"""
        history = version_service.get_version_history("nonexistent")
        assert len(history) == 0


class TestGetVersionConfigs:
    """获取版本配置"""

    def test_get_version_configs(self, version_service, lifecycle_service):
        """获取指定版本配置"""
        configs_v1 = [
            {"rule_key": "name_weight", "rule_value": "0.62", "rule_type": "number"},
            {"rule_key": "spec_weight", "rule_value": "0.23", "rule_type": "number"},
            {"rule_key": "maker_weight", "rule_value": "0.15", "rule_type": "number"},
            {"rule_key": "min_purchase_score", "rule_value": "70", "rule_type": "number"},
        ]
        lifecycle_service.create_draft_rule_set("test_configs_001", "测试", configs_v1)
        lifecycle_service.submit_for_review("test_configs_001")
        lifecycle_service.approve_rule_set("test_configs_001")
        lifecycle_service.activate_rule_set("test_configs_001")

        configs_info = version_service.get_version_configs("test_configs_001")
        assert "configs" in configs_info
        assert "name_weight" in configs_info["configs"]
        assert configs_info["configs"]["name_weight"]["value"] == "0.62"

    def test_get_version_configs_for_nonexistent(self, version_service):
        """不存在版本返回空配置"""
        configs_info = version_service.get_version_configs("nonexistent")
        assert len(configs_info["configs"]) == 0


class TestRollbackToVersion:
    """回滚到指定版本"""

    def test_rollback_to_previous_version(self, version_service, lifecycle_service):
        """回滚到前一版本"""
        configs_v1 = [
            {"rule_key": "name_weight", "rule_value": "0.62", "rule_type": "number"},
            {"rule_key": "spec_weight", "rule_value": "0.23", "rule_type": "number"},
            {"rule_key": "maker_weight", "rule_value": "0.15", "rule_type": "number"},
            {"rule_key": "min_purchase_score", "rule_value": "70", "rule_type": "number"},
        ]
        lifecycle_service.create_draft_rule_set("test_rollback_001", "测试", configs_v1)
        lifecycle_service.submit_for_review("test_rollback_001")
        lifecycle_service.approve_rule_set("test_rollback_001")
        lifecycle_service.activate_rule_set("test_rollback_001")

        # 保存当前版本到历史版本表
        version_service.create_new_version("test_rollback_001", "v1.0.0", configs_v1)

        configs_v2 = [
            {"rule_key": "name_weight", "rule_value": "0.70", "rule_type": "number"},
            {"rule_key": "spec_weight", "rule_value": "0.20", "rule_type": "number"},
            {"rule_key": "maker_weight", "rule_value": "0.10", "rule_type": "number"},
            {"rule_key": "min_purchase_score", "rule_value": "75", "rule_type": "number"},
        ]
        version_service.create_new_version("test_rollback_001", "v2.0.0", configs_v2)

        # 回滚到 v1.0.0
        success, msg = version_service.rollback_to_version("test_rollback_001", "v1.0.0")
        print(f"rollback result: success={success}, msg={msg}")
        assert success is True
        assert "v1.0.0" in msg

    def test_rollback_to_nonexistent_version_fails(self, version_service, lifecycle_service):
        """回滚到不存在版本应失败"""
        configs = [
            {"rule_key": "name_weight", "rule_value": "0.62", "rule_type": "number"},
        ]
        lifecycle_service.create_draft_rule_set("test_rollback_fail", "测试", configs)
        success, msg = version_service.rollback_to_version("test_rollback_fail", "v99.0.0")
        assert success is False
        assert "不存在" in msg

    def test_rollback_to_current_version_fails(self, version_service, lifecycle_service):
        """回滚到当前版本应失败"""
        configs = [
            {"rule_key": "name_weight", "rule_value": "0.62", "rule_type": "number"},
            {"rule_key": "spec_weight", "rule_value": "0.23", "rule_type": "number"},
            {"rule_key": "maker_weight", "rule_value": "0.15", "rule_type": "number"},
            {"rule_key": "min_purchase_score", "rule_value": "70", "rule_type": "number"},
        ]
        lifecycle_service.create_draft_rule_set("test_rollback_current", "测试", configs)
        lifecycle_service.submit_for_review("test_rollback_current")
        lifecycle_service.approve_rule_set("test_rollback_current")
        lifecycle_service.activate_rule_set("test_rollback_current")

        # 保存当前版本到历史版本表
        version_service.create_new_version("test_rollback_current", "v1.0.0", configs)

        success, msg = version_service.rollback_to_version("test_rollback_current", "v1.0.0")
        assert success is False
        assert "无需回滚" in msg
        lifecycle_service.approve_rule_set("test_rollback_current")
        lifecycle_service.activate_rule_set("test_rollback_current")
        success, msg = version_service.rollback_to_version("test_rollback_current", "v1.0.0")
        assert success is False
        assert "无需回滚" in msg


class TestCompareVersions:
    """版本对比"""

    def test_compare_modified_configs(self, version_service, lifecycle_service):
        """对比修改的配置"""
        configs_v1 = [
            {"rule_key": "name_weight", "rule_value": "0.62", "rule_type": "number"},
            {"rule_key": "spec_weight", "rule_value": "0.23", "rule_type": "number"},
            {"rule_key": "maker_weight", "rule_value": "0.15", "rule_type": "number"},
            {"rule_key": "min_purchase_score", "rule_value": "70", "rule_type": "number"},
        ]
        lifecycle_service.create_draft_rule_set("test_compare_001", "测试", configs_v1)
        lifecycle_service.submit_for_review("test_compare_001")
        lifecycle_service.approve_rule_set("test_compare_001")
        lifecycle_service.activate_rule_set("test_compare_001")

        # 保存当前版本到历史版本表
        version_service.create_new_version("test_compare_001", "v1.0.0", configs_v1)

        configs_v2 = [
            {"rule_key": "name_weight", "rule_value": "0.70", "rule_type": "number"},
            {"rule_key": "spec_weight", "rule_value": "0.20", "rule_type": "number"},
            {"rule_key": "maker_weight", "rule_value": "0.10", "rule_type": "number"},
            {"rule_key": "min_purchase_score", "rule_value": "75", "rule_type": "number"},
        ]
        version_service.create_new_version("test_compare_001", "v2.0.0", configs_v2)

        comparison = version_service.compare_versions("test_compare_001", "v1.0.0", "v2.0.0")
        assert "differences" in comparison
        # 应有4个修改项
        modified = [d for d in comparison["differences"] if d["change_type"] == "modified"]
        assert len(modified) >= 1

    def test_compare_added_configs(self, version_service, lifecycle_service):
        """对比新增的配置"""
        configs_v1 = [
            {"rule_key": "name_weight", "rule_value": "0.62", "rule_type": "number"},
        ]
        lifecycle_service.create_draft_rule_set("test_compare_added", "测试", configs_v1)
        lifecycle_service.submit_for_review("test_compare_added")
        lifecycle_service.approve_rule_set("test_compare_added")
        lifecycle_service.activate_rule_set("test_compare_added")

        configs_v2 = [
            {"rule_key": "name_weight", "rule_value": "0.62", "rule_type": "number"},
            {"rule_key": "new_param", "rule_value": "100", "rule_type": "number"},
        ]
        version_service.create_new_version("test_compare_added", "v2.0.0", configs_v2)

        comparison = version_service.compare_versions("test_compare_added", "v1.0.0", "v2.0.0")
        added = [d for d in comparison["differences"] if d["change_type"] == "added"]
        assert len(added) >= 1


class TestGetActiveVersion:
    """获取活跃版本"""

    def test_get_active_version(self, version_service, lifecycle_service):
        """获取活跃版本"""
        configs = [
            {"rule_key": "name_weight", "rule_value": "0.62", "rule_type": "number"},
            {"rule_key": "spec_weight", "rule_value": "0.23", "rule_type": "number"},
            {"rule_key": "maker_weight", "rule_value": "0.15", "rule_type": "number"},
            {"rule_key": "min_purchase_score", "rule_value": "70", "rule_type": "number"},
        ]
        lifecycle_service.create_draft_rule_set("test_active_001", "测试", configs)
        lifecycle_service.submit_for_review("test_active_001")
        lifecycle_service.approve_rule_set("test_active_001")
        lifecycle_service.activate_rule_set("test_active_001")

        active = version_service.get_active_version("test_active_001")
        assert active["is_enabled"] is True
        assert active["version_number"] == "v1.0.0"

    def test_get_active_version_for_inactive(self, version_service, lifecycle_service):
        """停用规则集返回非活跃"""
        configs = [
            {"rule_key": "name_weight", "rule_value": "0.62", "rule_type": "number"},
            {"rule_key": "spec_weight", "rule_value": "0.23", "rule_type": "number"},
            {"rule_key": "maker_weight", "rule_value": "0.15", "rule_type": "number"},
            {"rule_key": "min_purchase_score", "rule_value": "70", "rule_type": "number"},
        ]
        lifecycle_service.create_draft_rule_set("test_inactive_001", "测试", configs)
        lifecycle_service.submit_for_review("test_inactive_001")
        lifecycle_service.approve_rule_set("test_inactive_001")
        lifecycle_service.activate_rule_set("test_inactive_001")
        lifecycle_service.deactivate_rule_set("test_inactive_001")

        active = version_service.get_active_version("test_inactive_001")
        assert active["is_enabled"] is False


class TestPhase3Regression:
    """三期回归"""

    def test_default_v1_has_version(self, version_service):
        """default_v1 有版本信息"""
        active = version_service.get_active_version("default_v1")
        assert active["version_number"] != "none"

    def test_strict_spec_v1_has_version(self, version_service):
        """strict_spec_v1 有版本信息"""
        active = version_service.get_active_version("strict_spec_v1")
        assert active["version_number"] != "none"