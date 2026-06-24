"""
规则快照服务 - 二期第一轮整改
每次逐个采购任务启动时，生成规则运行快照，保存本次实际使用的规则JSON。
"""

import json
import logging
import uuid
from datetime import datetime
from typing import Dict, Tuple

from app.storage.database import Database


# 内置默认规则配置（当规则读取失败时使用）
BUILTIN_DEFAULT_RULE_CONFIG = {
    "ruleSetCode": "default_v1",
    "version": 1,
    "thresholds": {
        "name_weight": "0.62",
        "spec_weight": "0.20",
        "maker_weight": "0.18",
        "auto_pass_score": "80",
        "suspect_score": "60",
        "min_purchase_score": "60",
        "cart_backfill_min_score": "60",
        "spec_conflict_block": "1",
        "supplier_scope_required": "0",
        "price_check_enabled": "1",
        "price_compare_discount": "0.97",
        "price_upper_rate": "1.05",
        "price_upper_plus": "1",
        # 二期整改：内部模糊匹配阈值
        "name_core_min_score": "70",
        "spec_similar_min_score": "70",
        "factory_similar_min_score": "70",
        "cart_existing_same_product_min_score": "70",
    },
    "unitAliases": [
        {"alias": "s", "standard": "片"},
        {"alias": "片装", "standard": "片"},
        {"alias": "粒装", "standard": "粒"},
        {"alias": "板", "standard": "板"},
        {"alias": "盒", "standard": "盒"},
        {"alias": "袋", "standard": "袋"},
        {"alias": "支", "standard": "支"},
        {"alias": "瓶", "standard": "瓶"},
        {"alias": "贴", "standard": "贴"},
        {"alias": "丸", "standard": "丸"},
    ],
    "nameAliases": [],
    "specParseRules": {
        "parse_36s_as_36pian": True,
        "parse_12pian_3ban_as_36pian": True,
        "parse_7pian_4ban_as_28pian": True,
        "enable_package_total_conflict_block": True,
        "ignore_marketing_noise": True,
    },
    "failureCodes": [
        "MISSING_PRODUCT_NAME",
        "INVALID_PURCHASE_QUANTITY",
        "SUPPLIER_SCOPE_EMPTY",
        "SUPPLIER_NOT_ALLOWED",
        "FACTORY_FILTER_NOT_FOUND",
        "FACTORY_FILTER_NOT_EFFECTIVE",
        "NO_SEARCH_RESULT",
        "SCORE_BELOW_THRESHOLD",
        "SPEC_CONFLICT",
        "MAKER_NOT_MATCHED",
        "PRICE_OVER_LIMIT",
        "MIN_QTY_OVER_PURCHASE_QTY",
        "STOCK_NOT_ENOUGH",
        "CART_EXISTING_SAME_PRODUCT",
        "ADD_API_ERROR",
        "CART_VERIFY_AMOUNT_NOT_ENOUGH",
        "CART_BACKFILL_NOT_MATCHED",
        "BROWSER_NOT_FOUND",
        "LOGIN_NOT_CONFIRMED",
        "PAGE_CLOSED",
        "EXECUTION_TIMEOUT",
        "SYSTEM_REFERENCE_ERROR",
        "UNKNOWN_SYSTEM_EXCEPTION",
    ],
    "createdAt": "",
}


class RuleSnapshotService:
    """规则快照服务"""

    def __init__(self, db: Database):
        self.db = db

    def _resolve_default_rule_set_code(self) -> str:
        """解析默认规则集代码，优先使用 is_default=1 的规则集"""
        try:
            conn = self.db.get_connection()
            cursor = conn.cursor()
            cursor.execute(
                "SELECT rule_set_code FROM smart_match_rule_sets "
                "WHERE is_default = 1 AND is_enabled = 1 LIMIT 1"
            )
            row = cursor.fetchone()
            if row:
                return row["rule_set_code"]
        except Exception:
            pass
        return "default_v1"

    def generate_rule_snapshot(self, batch_id: str, rule_set_code: str = None) -> Tuple[str, str]:
        """
        为采购批次生成规则快照。
        返回 (snapshot_id, error_msg)，snapshot_id为空表示失败。
        三期整改：rule_set_code 由 RuleSelectionService 传入，不再硬编码 default_v1。
        """
        # 如果未指定规则集，使用默认规则集
        if not rule_set_code:
            rule_set_code = self._resolve_default_rule_set_code()
        conn = self.db.get_connection()
        cursor = conn.cursor()

        try:
            # 1. 读取规则集配置
            rule_config, fallback_used, fallback_reason = self._load_rule_config(cursor, rule_set_code)

            # 2. 生成快照ID
            snapshot_id = f"snapshot_{batch_id}_{datetime.now().strftime('%Y%m%d%H%M%S')}_{uuid.uuid4().hex[:8]}"

            # 3. 获取规则集版本
            rule_set_version = rule_config.get("version", 1)
            if isinstance(rule_set_version, int):
                rule_set_version = f"v{rule_set_version}.0.0"

            # 4. 设置创建时间
            rule_config["createdAt"] = datetime.now().isoformat()

            # 5. 保存快照
            cursor.execute('''
                INSERT INTO smart_match_rule_snapshots (
                    snapshot_id, batch_id, rule_set_code, rule_set_version,
                    snapshot_json, fallback_used, fallback_reason, source, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                snapshot_id,
                batch_id,
                rule_set_code,
                str(rule_set_version),
                json.dumps(rule_config, ensure_ascii=False, indent=2),
                1 if fallback_used else 0,
                fallback_reason or "",
                "smart_purchase",
                datetime.now().isoformat()
            ))

            conn.commit()
            logging.info(f"规则快照已生成: snapshot_id={snapshot_id}, batch_id={batch_id}, "
                         f"rule_set_code={rule_set_code}, fallback={fallback_used}")
            return snapshot_id, ""

        except Exception as e:
            conn.rollback()
            logging.error(f"生成规则快照失败: {e}")

            # 尝试生成fallback快照
            try:
                return self._generate_fallback_snapshot(cursor, conn, batch_id, str(e))
            except Exception as fallback_error:
                logging.error(f"生成fallback快照也失败: {fallback_error}")
                return "", f"生成规则快照失败: {e}"

    def _load_rule_config(self, cursor, rule_set_code: str) -> Tuple[Dict, bool, str]:
        """
        从数据库加载规则集配置，构造完整的规则JSON。
        返回 (rule_config, fallback_used, fallback_reason)
        兼容 version_number 字段迁移前后的数据库状态。
        """
        # 先检查表有哪些列，兼容旧数据库可能缺少 version_number 的情况
        cursor.execute("PRAGMA table_info(smart_match_rule_sets)")
        existing_columns = {row["name"] for row in cursor.fetchall()}

        if "version_number" in existing_columns:
            cursor.execute(
                "SELECT rule_set_code, version_number FROM smart_match_rule_sets WHERE rule_set_code = ? AND is_enabled = 1",
                (rule_set_code,)
            )
        else:
            # 旧数据库没有 version_number 字段，使用 SELECT * 兼容
            cursor.execute(
                "SELECT * FROM smart_match_rule_sets WHERE rule_set_code = ? AND is_enabled = 1",
                (rule_set_code,)
            )
        rule_set_row = cursor.fetchone()

        if not rule_set_row:
            # 规则集不存在，使用内置默认配置
            config = dict(BUILTIN_DEFAULT_RULE_CONFIG)
            config["ruleSetCode"] = rule_set_code
            return config, True, f"规则集 {rule_set_code} 不存在或已停用，使用内置默认配置"

        # 读取规则配置项
        cursor.execute(
            "SELECT rule_key, rule_name, rule_value, rule_type FROM smart_match_rule_configs "
            "WHERE rule_set_code = ? AND is_enabled = 1 ORDER BY sort_order",
            (rule_set_code,)
        )
        config_rows = cursor.fetchall()

        if not config_rows:
            # 没有配置项，使用内置默认配置
            config = dict(BUILTIN_DEFAULT_RULE_CONFIG)
            config["ruleSetCode"] = rule_set_code
            return config, True, f"规则集 {rule_set_code} 无有效配置项，使用内置默认配置"

        # 构造规则配置
        # 三期：旧键到 canonical 键的兼容映射
        OLD_TO_CANONICAL = {
            "total_score_threshold": "min_purchase_score",
            "price_tolerance": "price_compare_discount",
            "spec_strict": "spec_conflict_block",
        }

        thresholds = {}
        for row in config_rows:
            rule_key = row["rule_key"]
            rule_value = row["rule_value"]
            rule_type = row["rule_type"]

            # 旧键映射为 canonical 键（如果 canonical 键已存在则跳过旧键）
            canonical_key = OLD_TO_CANONICAL.get(rule_key, rule_key)
            if canonical_key != rule_key and canonical_key in thresholds:
                continue  # canonical 键已存在，跳过旧键

            # 三期整改：识别所有规则类型，不再只识别 weight/threshold
            if rule_type in ("weight", "threshold", "number", "boolean", "string", "json"):
                # 类型转换：将字符串值转为对应类型
                if rule_type in ("weight", "threshold", "number"):
                    try:
                        val = float(rule_value)
                        if val == int(val):
                            val = int(val)
                        thresholds[canonical_key] = str(val)
                    except (ValueError, TypeError):
                        thresholds[canonical_key] = rule_value
                elif rule_type == "boolean":
                    thresholds[canonical_key] = "1" if rule_value in ("1", "true", "True", "yes") else "0"
                else:
                    thresholds[canonical_key] = rule_value

        # 读取单位别名
        unit_aliases = self._load_unit_aliases(cursor)

        # 读取名称别名
        name_aliases = self._load_name_aliases(cursor, rule_set_code)

        # 构造完整配置
        # 兼容旧数据库：version_number 字段可能不存在
        try:
            version_number = rule_set_row["version_number"] or "v1.0.0"
        except (KeyError, IndexError):
            version_number = "v1.0.0"

        rule_config = {
            "ruleSetCode": rule_set_code,
            "version": version_number,
            "thresholds": thresholds,
            "unitAliases": unit_aliases,
            "nameAliases": name_aliases,
            "specParseRules": BUILTIN_DEFAULT_RULE_CONFIG["specParseRules"],
            "failureCodes": BUILTIN_DEFAULT_RULE_CONFIG["failureCodes"],
            "createdAt": "",
        }

        return rule_config, False, ""

    def _load_unit_aliases(self, cursor) -> list:
        """加载单位别名"""
        try:
            cursor.execute(
                "SELECT unit_alias, unit_standard FROM smart_spec_unit_aliases WHERE is_enabled = 1"
            )
            rows = cursor.fetchall()
            return [{"alias": row["unit_alias"], "standard": row["unit_standard"]} for row in rows]
        except Exception:
            return BUILTIN_DEFAULT_RULE_CONFIG["unitAliases"]

    def _load_name_aliases(self, cursor, rule_set_code: str) -> list:
        """加载名称/品牌/厂家别名"""
        try:
            cursor.execute(
                "SELECT name_alias, name_standard FROM smart_name_aliases WHERE is_enabled = 1"
            )
            rows = cursor.fetchall()
            return [{"alias": row["name_alias"], "standard": row["name_standard"]} for row in rows]
        except Exception:
            return []

    def _generate_fallback_snapshot(self, cursor, conn, batch_id: str, reason: str) -> Tuple[str, str]:
        """生成fallback快照（规则读取失败时使用内置默认规则继续执行）"""
        snapshot_id = f"snapshot_{batch_id}_{datetime.now().strftime('%Y%m%d%H%M%S')}_fallback_{uuid.uuid4().hex[:8]}"
        config = dict(BUILTIN_DEFAULT_RULE_CONFIG)
        config["createdAt"] = datetime.now().isoformat()

        cursor.execute('''
            INSERT INTO smart_match_rule_snapshots (
                snapshot_id, batch_id, rule_set_code, rule_set_version,
                snapshot_json, fallback_used, fallback_reason, source, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            snapshot_id,
            batch_id,
            "default_v1",
            "v1.0.0",
            json.dumps(config, ensure_ascii=False, indent=2),
            1,
            reason,
            "smart_purchase",
            datetime.now().isoformat()
        ))

        conn.commit()
        logging.info(f"fallback规则快照已生成: snapshot_id={snapshot_id}, batch_id={batch_id}, reason={reason}")
        return snapshot_id, ""

    def get_rule_snapshot(self, snapshot_id: str) -> Dict:
        """获取规则快照"""
        conn = self.db.get_connection()
        cursor = conn.cursor()

        cursor.execute(
            "SELECT * FROM smart_match_rule_snapshots WHERE snapshot_id = ?",
            (snapshot_id,)
        )
        row = cursor.fetchone()
        if not row:
            return {}

        result = dict(row)
        try:
            result["snapshot_json_parsed"] = json.loads(result.get("snapshot_json", "{}"))
        except (json.JSONDecodeError, TypeError):
            result["snapshot_json_parsed"] = {}

        return result

    def get_batch_snapshot(self, batch_id: str) -> Dict:
        """获取采购批次的规则快照"""
        conn = self.db.get_connection()
        cursor = conn.cursor()

        cursor.execute(
            "SELECT * FROM smart_match_rule_snapshots WHERE batch_id = ? ORDER BY created_at DESC LIMIT 1",
            (batch_id,)
        )
        row = cursor.fetchone()
        if not row:
            return {}

        result = dict(row)
        try:
            result["snapshot_json_parsed"] = json.loads(result.get("snapshot_json", "{}"))
        except (json.JSONDecodeError, TypeError):
            result["snapshot_json_parsed"] = {}

        return result

    def get_rule_config_for_node(self, snapshot_id: str) -> Dict:
        """
        获取规则快照中供Node使用的配置。
        返回可直接传给Node的ruleConfig对象。
        """
        snapshot = self.get_rule_snapshot(snapshot_id)
        if not snapshot:
            return dict(BUILTIN_DEFAULT_RULE_CONFIG)

        try:
            config = json.loads(snapshot.get("snapshot_json", "{}"))
        except (json.JSONDecodeError, TypeError):
            config = dict(BUILTIN_DEFAULT_RULE_CONFIG)

        # 构造Node需要的格式
        thresholds = config.get("thresholds", {})
        node_config = {
            "ruleSetCode": config.get("ruleSetCode", "default_v1"),
            "version": config.get("version", "v1.0.0"),
            "ruleSnapshotId": snapshot_id,
            "minPurchaseScore": int(float(thresholds.get("min_purchase_score", 60))),
            "cartBackfillMinScore": int(float(thresholds.get("cart_backfill_min_score", 60))),
            "specConflictBlock": thresholds.get("spec_conflict_block", "0") == "1",
            "makerStrict": thresholds.get("maker_strict", "0") == "1",
            "supplierScopeRequired": thresholds.get("supplier_scope_required", "0") == "1",
            "priceCheckEnabled": thresholds.get("price_check_enabled", "1") == "1",
            "priceCompareDiscount": float(thresholds.get("price_compare_discount", 0.97)),
            "priceUpperRate": float(thresholds.get("price_upper_rate", 1.05)),
            "priceUpperPlus": float(thresholds.get("price_upper_plus", 1)),
            "nameWeight": float(thresholds.get("name_weight", 0.62)),
            "specWeight": float(thresholds.get("spec_weight", 0.20)),
            "makerWeight": float(thresholds.get("maker_weight", 0.18)),
            # 二期整改：内部模糊匹配阈值
            "nameCoreMinScore": int(float(thresholds.get("name_core_min_score", 70))),
            "specSimilarMinScore": int(float(thresholds.get("spec_similar_min_score", 70))),
            "factorySimilarMinScore": int(float(thresholds.get("factory_similar_min_score", 70))),
            "cartExistingSameProductMinScore": int(float(thresholds.get("cart_existing_same_product_min_score", 70))),
            "unitAliases": config.get("unitAliases", []),
            "nameAliases": config.get("nameAliases", []),
        }

        # 三期整改：校验关键配置项是否来自快照（非代码默认值）
        is_fallback = snapshot.get("fallback_used", 0) in (1, "1")
        if not is_fallback:
            missing_keys = []
            for key in ("name_weight", "spec_weight", "maker_weight", "min_purchase_score"):
                if key not in thresholds:
                    missing_keys.append(key)
            if missing_keys:
                logging.warning(
                    f"正常快照 {snapshot_id} 缺少关键配置项: {missing_keys}，"
                    f"将使用代码默认值，建议检查规则配置"
                )

        return node_config

    def get_cart_backfill_threshold(self, snapshot_id: str) -> int:
        """获取购物车反写最低分阈值"""
        config = self.get_rule_config_for_node(snapshot_id)
        return config.get("cartBackfillMinScore", 60)

    def get_min_purchase_score(self, snapshot_id: str) -> int:
        """获取采购最低通过分阈值"""
        config = self.get_rule_config_for_node(snapshot_id)
        return config.get("minPurchaseScore", 60)
