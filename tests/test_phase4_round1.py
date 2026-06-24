"""
三期阶段4.1测试 - 规则参数校验服务
验证：
1. 权重范围校验
2. 阈值合理性校验
3. 必填参数校验
4. 类型校验
5. 权重总和校验
"""
import pytest
from pathlib import Path

from app.storage.database import Database
from app.core.rule_validation_service import RuleValidationService
from app.core.smart_purchase_service import SmartPurchaseService


@pytest.fixture
def db(tmp_path):
    db_path = str(tmp_path / "test_phase4_round1.db")
    database = Database(db_path)
    database.initialize()
    sps = SmartPurchaseService(database)
    yield database
    database.close()


@pytest.fixture
def validation_service(db):
    return RuleValidationService(db)


class TestRequiredParamsValidation:
    """必填参数校验"""

    def test_default_v1_has_required_params(self, validation_service):
        """default_v1 应包含所有必填参数"""
        is_valid, errors = validation_service.validate_rule_set("default_v1")
        # 不应有"缺少必填参数"错误
        for error in errors:
            assert "缺少必填" not in error

    def test_strict_spec_v1_has_required_params(self, validation_service):
        """strict_spec_v1 应包含所有必填参数"""
        is_valid, errors = validation_service.validate_rule_set("strict_spec_v1")
        for error in errors:
            assert "缺少必填" not in error

    def test_missing_weight_detected(self, validation_service, db):
        """缺少权重参数应被检测"""
        conn = db.get_connection()
        cursor = conn.cursor()
        # 创建一个缺少权重的规则集
        cursor.execute('''
            INSERT INTO smart_match_rule_sets (
                rule_set_code, rule_set_name, is_enabled, is_default, created_at, updated_at
            ) VALUES (?, ?, 1, 0, ?, ?)
        ''', ("test_missing_weight", "测试缺少权重", "2026-01-01T00:00:00", "2026-01-01T00:00:00"))
        # 只添加一个配置项
        cursor.execute('''
            INSERT INTO smart_match_rule_configs (
                rule_set_code, rule_key, rule_name, rule_value, rule_type, description,
                sort_order, is_enabled, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', ("test_missing_weight", "min_purchase_score", "最低分数", "70", "number", "测试", 1, 1,
              "2026-01-01T00:00:00", "2026-01-01T00:00:00"))
        conn.commit()

        is_valid, errors = validation_service.validate_rule_set("test_missing_weight")
        assert is_valid is False
        assert any("缺少必填" in e for e in errors)


class TestParamRangesValidation:
    """参数范围校验"""

    def test_weight_in_valid_range(self, validation_service):
        """权重应在0-1之间"""
        is_valid, errors = validation_service.validate_rule_set("default_v1")
        for error in errors:
            assert "应在0-1之间" not in error or "权重" not in error

    def test_score_in_valid_range(self, validation_service):
        """分数阈值应在0-100之间"""
        is_valid, errors = validation_service.validate_rule_set("default_v1")
        for error in errors:
            assert "应在0-100之间" not in error

    def test_invalid_weight_detected(self, validation_service, db):
        """无效权重值应被检测"""
        conn = db.get_connection()
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO smart_match_rule_sets (
                rule_set_code, rule_set_name, is_enabled, is_default, created_at, updated_at
            ) VALUES (?, ?, 1, 0, ?, ?)
        ''', ("test_invalid_weight", "测试无效权重", "2026-01-01T00:00:00", "2026-01-01T00:00:00"))
        # 添加超出范围的权重
        cursor.execute('''
            INSERT INTO smart_match_rule_configs (
                rule_set_code, rule_key, rule_name, rule_value, rule_type, description,
                sort_order, is_enabled, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', ("test_invalid_weight", "name_weight", "名称权重", "1.5", "number", "超出范围", 1, 1,
              "2026-01-01T00:00:00", "2026-01-01T00:00:00"))
        conn.commit()

        is_valid, errors = validation_service.validate_rule_set("test_invalid_weight")
        assert any("应在0-1之间" in e for e in errors)


class TestWeightSumValidation:
    """权重总和校验"""

    def test_default_v1_weight_sum_is_one(self, validation_service):
        """default_v1 权重总和应为1"""
        is_valid, errors = validation_service.validate_rule_set("default_v1")
        for error in errors:
            assert "权重总和" not in error

    def test_strict_spec_v1_weight_sum_is_one(self, validation_service):
        """strict_spec_v1 权重总和应为1"""
        is_valid, errors = validation_service.validate_rule_set("strict_spec_v1")
        for error in errors:
            assert "权重总和" not in error

    def test_weight_sum_not_one_detected(self, validation_service, db):
        """权重总和不为1应被检测"""
        conn = db.get_connection()
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO smart_match_rule_sets (
                rule_set_code, rule_set_name, is_enabled, is_default, created_at, updated_at
            ) VALUES (?, ?, 1, 0, ?, ?)
        ''', ("test_weight_sum", "测试权重总和", "2026-01-01T00:00:00", "2026-01-01T00:00:00"))
        # 权重总和为0.5
        for key, val in [("name_weight", "0.30"), ("spec_weight", "0.10"), ("maker_weight", "0.10")]:
            cursor.execute('''
                INSERT INTO smart_match_rule_configs (
                    rule_set_code, rule_key, rule_name, rule_value, rule_type, description,
                    sort_order, is_enabled, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', ("test_weight_sum", key, key, val, "number", "测试", 1, 1,
                  "2026-01-01T00:00:00", "2026-01-01T00:00:00"))
        conn.commit()

        is_valid, errors = validation_service.validate_rule_set("test_weight_sum")
        assert any("权重总和" in e for e in errors)


class TestThresholdLogicValidation:
    """分数阈值逻辑校验"""

    def test_min_score_not_greater_than_auto_pass(self, validation_service):
        """最低分数不应大于自动通过分数"""
        is_valid, errors = validation_service.validate_rule_set("default_v1")
        for error in errors:
            assert "不应大于 auto_pass_score" not in error

    def test_invalid_threshold_logic_detected(self, validation_service, db):
        """无效阈值逻辑应被检测"""
        conn = db.get_connection()
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO smart_match_rule_sets (
                rule_set_code, rule_set_name, is_enabled, is_default, created_at, updated_at
            ) VALUES (?, ?, 1, 0, ?, ?)
        ''', ("test_threshold_logic", "测试阈值逻辑", "2026-01-01T00:00:00", "2026-01-01T00:00:00"))
        # min_purchase_score > auto_pass_score
        for key, val in [("name_weight", "0.62"), ("spec_weight", "0.20"), ("maker_weight", "0.18"),
                         ("min_purchase_score", "90"), ("auto_pass_score", "80")]:
            cursor.execute('''
                INSERT INTO smart_match_rule_configs (
                    rule_set_code, rule_key, rule_name, rule_value, rule_type, description,
                    sort_order, is_enabled, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', ("test_threshold_logic", key, key, val, "number", "测试", 1, 1,
                  "2026-01-01T00:00:00", "2026-01-01T00:00:00"))
        conn.commit()

        is_valid, errors = validation_service.validate_rule_set("test_threshold_logic")
        assert any("不应大于" in e for e in errors)


class TestParamTypeValidation:
    """类型校验"""

    def test_number_type_valid(self, validation_service):
        """数字类型参数应有效"""
        is_valid, errors = validation_service.validate_rule_set("default_v1")
        for error in errors:
            assert "不是有效数字" not in error

    def test_invalid_number_type_detected(self, validation_service, db):
        """无效数字类型应被检测"""
        conn = db.get_connection()
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO smart_match_rule_sets (
                rule_set_code, rule_set_name, is_enabled, is_default, created_at, updated_at
            ) VALUES (?, ?, 1, 0, ?, ?)
        ''', ("test_invalid_type", "测试无效类型", "2026-01-01T00:00:00", "2026-01-01T00:00:00"))
        # 添加非数字值到数字类型参数
        cursor.execute('''
            INSERT INTO smart_match_rule_configs (
                rule_set_code, rule_key, rule_name, rule_value, rule_type, description,
                sort_order, is_enabled, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', ("test_invalid_type", "name_weight", "名称权重", "abc", "number", "无效", 1, 1,
              "2026-01-01T00:00:00", "2026-01-01T00:00:00"))
        conn.commit()

        is_valid, errors = validation_service.validate_rule_set("test_invalid_type")
        assert any("不是有效数字" in e for e in errors)


class TestValidateAndReport:
    """详细报告"""

    def test_report_contains_all_checks(self, validation_service):
        """报告应包含所有检查项"""
        report = validation_service.validate_and_report("default_v1")

        assert "rule_set_code" in report
        assert "is_valid" in report
        assert "errors" in report
        assert "warnings" in report
        assert "params" in report
        assert "checks" in report

        assert "required_params" in report["checks"]
        assert "param_ranges" in report["checks"]
        assert "weight_sum" in report["checks"]
        assert "threshold_logic" in report["checks"]
        assert "param_types" in report["checks"]

    def test_report_shows_param_values(self, validation_service):
        """报告应显示参数值"""
        report = validation_service.validate_and_report("default_v1")

        assert "name_weight" in report["params"]
        assert "value" in report["params"]["name_weight"]
        assert "name" in report["params"]["name_weight"]

    def test_report_generates_warnings(self, validation_service, db):
        """报告应生成警告"""
        conn = db.get_connection()
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO smart_match_rule_sets (
                rule_set_code, rule_set_name, is_enabled, is_default, created_at, updated_at
            ) VALUES (?, ?, 1, 0, ?, ?)
        ''', ("test_warnings", "测试警告", "2026-01-01T00:00:00", "2026-01-01T00:00:00"))
        # 添加极端权重
        for key, val in [("name_weight", "0.90"), ("spec_weight", "0.05"), ("maker_weight", "0.05"),
                         ("min_purchase_score", "40")]:
            cursor.execute('''
                INSERT INTO smart_match_rule_configs (
                    rule_set_code, rule_key, rule_name, rule_value, rule_type, description,
                    sort_order, is_enabled, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', ("test_warnings", key, key, val, "number", "测试", 1, 1,
                  "2026-01-01T00:00:00", "2026-01-01T00:00:00"))
        conn.commit()

        report = validation_service.validate_and_report("test_warnings")
        # 应有警告（权重过高、分数过低）
        assert len(report["warnings"]) > 0


class TestQuickValidate:
    """快速验证"""

    def test_quick_validate_returns_simple_result(self, validation_service):
        """快速验证返回简短结果"""
        is_valid, msg = validation_service.quick_validate("default_v1")
        assert isinstance(is_valid, bool)
        assert isinstance(msg, str)

    def test_quick_validate_truncates_errors(self, validation_service, db):
        """快速验证截断错误"""
        conn = db.get_connection()
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO smart_match_rule_sets (
                rule_set_code, rule_set_name, is_enabled, is_default, created_at, updated_at
            ) VALUES (?, ?, 1, 0, ?, ?)
        ''', ("test_quick", "测试快速", "2026-01-01T00:00:00", "2026-01-01T00:00:00"))
        # 添加多个错误配置
        for key, val in [("name_weight", "2.0"), ("spec_weight", "2.0"), ("maker_weight", "2.0")]:
            cursor.execute('''
                INSERT INTO smart_match_rule_configs (
                    rule_set_code, rule_key, rule_name, rule_value, rule_type, description,
                    sort_order, is_enabled, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', ("test_quick", key, key, val, "number", "测试", 1, 1,
                  "2026-01-01T00:00:00", "2026-01-01T00:00:00"))
        conn.commit()

        is_valid, msg = validation_service.quick_validate("test_quick")
        assert is_valid is False
        # 消息应简短（最多3个错误）
        assert len(msg.split(";")) <= 3


class TestPhase3Regression:
    """三期回归"""

    def test_default_v1_is_valid(self, validation_service):
        """default_v1 应有效"""
        is_valid, errors = validation_service.validate_rule_set("default_v1")
        assert is_valid is True
        assert len(errors) == 0

    def test_strict_spec_v1_is_valid(self, validation_service):
        """strict_spec_v1 应有效"""
        is_valid, errors = validation_service.validate_rule_set("strict_spec_v1")
        assert is_valid is True
        assert len(errors) == 0