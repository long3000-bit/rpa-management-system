"""
规则参数校验服务 - 三期阶段4
验证规则集参数的合理性，包括：
1. 权重范围校验（权重总和应为1，各权重应在0-1之间）
2. 阈值合理性校验（分数阈值应在合理范围内）
3. 必填参数校验
4. 类型校验
"""
import logging
from typing import Dict, List, Tuple

from app.storage.database import Database


class RuleValidationService:
    """规则参数校验服务"""

    # 权重参数列表
    WEIGHT_PARAMS = ["name_weight", "spec_weight", "maker_weight"]

    # 分数阈值参数列表
    SCORE_THRESHOLD_PARAMS = [
        "auto_pass_score", "suspect_score", "min_purchase_score",
        "cart_backfill_min_score", "name_core_min_score",
        "spec_similar_min_score", "factory_similar_min_score",
        "cart_existing_same_product_min_score"
    ]

    # 价格参数列表
    PRICE_PARAMS = ["price_compare_discount", "price_upper_rate", "price_upper_plus"]

    # 必填参数列表
    REQUIRED_PARAMS = WEIGHT_PARAMS + ["min_purchase_score"]

    # 参数范围定义
    PARAM_RANGES = {
        # 权重：0-1
        "name_weight": (0, 1, "名称权重应在0-1之间"),
        "spec_weight": (0, 1, "规格权重应在0-1之间"),
        "maker_weight": (0, 1, "厂家权重应在0-1之间"),
        # 分数阈值：0-100
        "auto_pass_score": (0, 100, "自动通过分数应在0-100之间"),
        "suspect_score": (0, 100, "可疑分数应在0-100之间"),
        "min_purchase_score": (0, 100, "最低采购分数应在0-100之间"),
        "cart_backfill_min_score": (0, 100, "购物车反写最低分数应在0-100之间"),
        "name_core_min_score": (0, 100, "名称核心最低分数应在0-100之间"),
        "spec_similar_min_score": (0, 100, "规格相似最低分数应在0-100之间"),
        "factory_similar_min_score": (0, 100, "厂家相似最低分数应在0-100之间"),
        "cart_existing_same_product_min_score": (0, 100, "购物车已有同品最低分数应在0-100之间"),
        # 价格参数：特殊范围
        "price_compare_discount": (0.5, 1.5, "价格比较折扣应在0.5-1.5之间"),
        "price_upper_rate": (1.0, 2.0, "价格上限比率应在1.0-2.0之间"),
        "price_upper_plus": (0, 10, "价格上限加值应在0-10之间"),
    }

    def __init__(self, db: Database):
        self.db = db

    def validate_rule_set(self, rule_set_code: str) -> Tuple[bool, List[str]]:
        """
        验证规则集参数。
        返回 (is_valid, error_messages)
        """
        errors = []

        try:
            conn = self.db.get_connection()
            cursor = conn.cursor()

            # 获取规则集的所有配置项
            cursor.execute(
                "SELECT rule_key, rule_value, rule_type FROM smart_match_rule_configs "
                "WHERE rule_set_code = ? AND is_enabled = 1",
                (rule_set_code,)
            )
            configs = cursor.fetchall()

            if not configs:
                return False, ["规则集无有效配置项"]

            # 构建参数字典
            params = {}
            for row in configs:
                rule_key = row["rule_key"]
                rule_value = row["rule_value"]
                rule_type = row["rule_type"]
                params[rule_key] = self._parse_value(rule_value, rule_type)

            # 1. 必填参数校验
            missing_errors = self._validate_required_params(params)
            errors.extend(missing_errors)

            # 2. 参数范围校验
            range_errors = self._validate_param_ranges(params)
            errors.extend(range_errors)

            # 3. 权重总和校验
            weight_errors = self._validate_weight_sum(params)
            errors.extend(weight_errors)

            # 4. 分数阈值逻辑校验
            threshold_errors = self._validate_threshold_logic(params)
            errors.extend(threshold_errors)

            # 5. 类型校验
            type_errors = self._validate_param_types(params, configs)
            errors.extend(type_errors)

            return len(errors) == 0, errors

        except Exception as e:
            return False, [f"验证异常: {e}"]

    def validate_and_report(self, rule_set_code: str) -> Dict:
        """
        验证规则集并返回详细报告。
        """
        is_valid, errors = self.validate_rule_set(rule_set_code)

        conn = self.db.get_connection()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT rule_key, rule_value, rule_name FROM smart_match_rule_configs "
            "WHERE rule_set_code = ? AND is_enabled = 1",
            (rule_set_code,)
        )
        configs = cursor.fetchall()

        report = {
            "rule_set_code": rule_set_code,
            "is_valid": is_valid,
            "errors": errors,
            "warnings": [],
            "params": {},
            "checks": {
                "required_params": "pass",
                "param_ranges": "pass",
                "weight_sum": "pass",
                "threshold_logic": "pass",
                "param_types": "pass",
            }
        }

        # 详细参数信息
        for row in configs:
            report["params"][row["rule_key"]] = {
                "value": row["rule_value"],
                "name": row["rule_name"],
            }

        # 分类错误到各检查项
        for error in errors:
            if "缺少必填" in error or "未配置" in error:
                report["checks"]["required_params"] = "fail"
            elif "应在" in error or "超出范围" in error:
                report["checks"]["param_ranges"] = "fail"
            elif "权重总和" in error:
                report["checks"]["weight_sum"] = "fail"
            elif "阈值逻辑" in error or "不应大于" in error:
                report["checks"]["threshold_logic"] = "fail"
            elif "类型错误" in error:
                report["checks"]["param_types"] = "fail"

        # 添加警告（非错误但值得注意）
        warnings = self._generate_warnings(report["params"])
        report["warnings"] = warnings

        return report

    def _parse_value(self, value: str, rule_type: str):
        """解析参数值"""
        if rule_type in ("number", "weight", "threshold"):
            try:
                return float(value)
            except (ValueError, TypeError):
                return None
        elif rule_type == "boolean":
            if value in ("1", "true", "True", "yes"):
                return True
            elif value in ("0", "false", "False", "no"):
                return False
            return None
        elif rule_type == "json":
            try:
                import json
                return json.loads(value)
            except:
                return None
        return value

    def _validate_required_params(self, params: Dict) -> List[str]:
        """必填参数校验"""
        errors = []
        for param in self.REQUIRED_PARAMS:
            if param not in params or params[param] is None:
                errors.append(f"缺少必填参数: {param}")
        return errors

    def _validate_param_ranges(self, params: Dict) -> List[str]:
        """参数范围校验"""
        errors = []
        for param, (min_val, max_val, msg) in self.PARAM_RANGES.items():
            if param in params and params[param] is not None:
                value = params[param]
                if isinstance(value, (int, float)):
                    if value < min_val or value > max_val:
                        errors.append(f"{param}={value} {msg}")
        return errors

    def _validate_weight_sum(self, params: Dict) -> List[str]:
        """权重总和校验"""
        errors = []
        weight_sum = 0
        has_weights = False

        for param in self.WEIGHT_PARAMS:
            if param in params and params[param] is not None:
                weight_sum += params[param]
                has_weights = True

        if has_weights:
            # 权重总和应接近1（允许0.01误差）
            if abs(weight_sum - 1) > 0.01:
                errors.append(
                    f"权重总和={weight_sum:.2f}，应为1.00 "
                    f"(name_weight={params.get('name_weight', 0):.2f}, "
                    f"spec_weight={params.get('spec_weight', 0):.2f}, "
                    f"maker_weight={params.get('maker_weight', 0):.2f})"
                )

        return errors

    def _validate_threshold_logic(self, params: Dict) -> List[str]:
        """分数阈值逻辑校验"""
        errors = []

        # min_purchase_score 不应大于 auto_pass_score
        min_score = params.get("min_purchase_score")
        auto_pass = params.get("auto_pass_score")

        if min_score is not None and auto_pass is not None:
            if min_score > auto_pass:
                errors.append(
                    f"阈值逻辑错误: min_purchase_score={min_score} 不应大于 auto_pass_score={auto_pass}"
                )

        # suspect_score 应小于 min_purchase_score
        suspect = params.get("suspect_score")
        if suspect is not None and min_score is not None:
            if suspect >= min_score:
                errors.append(
                    f"阈值逻辑错误: suspect_score={suspect} 应小于 min_purchase_score={min_score}"
                )

        return errors

    def _validate_param_types(self, params: Dict, configs: List) -> List[str]:
        """类型校验"""
        errors = []

        for row in configs:
            rule_key = row["rule_key"]
            rule_value = row["rule_value"]
            rule_type = row["rule_type"]

            if rule_type in ("number", "weight", "threshold"):
                try:
                    float(rule_value)
                except (ValueError, TypeError):
                    errors.append(f"{rule_key} 类型错误: '{rule_value}' 不是有效数字")
            elif rule_type == "boolean":
                if rule_value not in ("0", "1", "true", "false", "True", "False"):
                    errors.append(f"{rule_key} 类型错误: '{rule_value}' 不是有效布尔值")

        return errors

    def _generate_warnings(self, params: Dict) -> List[str]:
        """生成警告信息"""
        warnings = []

        # 权重过于极端
        for param in self.WEIGHT_PARAMS:
            if param in params:
                param_info = params[param]
                # param_info 可能是字典（validate_and_report）或数值（validate_rule_set）
                if isinstance(param_info, dict):
                    value_str = param_info.get("value", "")
                else:
                    value_str = param_info
                try:
                    value = float(value_str)
                    if value > 0.8:
                        warnings.append(f"{param}={value:.2f} 占比过高，建议均衡权重")
                    elif value < 0.1:
                        warnings.append(f"{param}={value:.2f} 占比过低，可能影响匹配效果")
                except (ValueError, TypeError):
                    pass

        # 分数阈值过于宽松或严格
        if "min_purchase_score" in params:
            param_info = params["min_purchase_score"]
            if isinstance(param_info, dict):
                value_str = param_info.get("value", "")
            else:
                value_str = param_info
            try:
                min_score = float(value_str)
                if min_score < 50:
                    warnings.append(f"min_purchase_score={min_score} 过低，可能匹配不合适商品")
                elif min_score > 85:
                    warnings.append(f"min_purchase_score={min_score} 过高，可能难以找到匹配商品")
            except (ValueError, TypeError):
                pass

        return warnings

    def quick_validate(self, rule_set_code: str) -> Tuple[bool, str]:
        """快速验证，返回简短结果"""
        is_valid, errors = self.validate_rule_set(rule_set_code)
        if is_valid:
            return True, "规则集参数有效"
        else:
            return False, "; ".join(errors[:3])  # 只返回前3个错误