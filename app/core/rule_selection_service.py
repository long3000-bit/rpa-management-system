"""
规则选择服务 - 三期核心
负责根据批次配置解析实际使用的规则集。
选择优先级：
1. 批次手工指定规则
2. 范围规则自动匹配（二期预留，暂不实现）
3. 系统默认规则（is_default=1 AND is_enabled=1 AND version_status='active'）
4. 内置应急规则（仅用于数据库异常或无有效规则，生成 fallback 快照）
"""
import logging
from datetime import datetime
from typing import Dict, Optional, Tuple

from app.storage.database import Database


class RuleSelectionService:
    """规则选择服务：根据批次配置解析实际使用的规则集"""

    def __init__(self, db: Database):
        self.db = db

    def resolve_rule_set(self, batch_id: str, manual_rule_set_code: str = None) -> Dict:
        """
        解析批次应使用的规则集。

        Args:
            batch_id: 采购批次ID
            manual_rule_set_code: 手工指定的规则集代码（可选）

        Returns:
            {
                "rule_set_code": str,
                "rule_set_version": str,
                "rule_select_mode": "manual"|"scope"|"default"|"fallback",
                "rule_select_reason": str,
                "resolved": bool,
            }
        """
        # 1. 批次手工指定规则
        if manual_rule_set_code:
            result = self._validate_and_resolve(manual_rule_set_code, "manual",
                                                f"批次 {batch_id} 手工指定规则集 {manual_rule_set_code}")
            if result["resolved"]:
                return result
            # 手工指定无效，继续尝试默认规则
            logging.warning(f"手工指定规则集 {manual_rule_set_code} 无效: {result['rule_select_reason']}")

        # 2. 范围规则自动匹配（暂不实现，跳过）

        # 3. 系统默认规则
        default_result = self._resolve_default_rule()
        if default_result["resolved"]:
            return default_result

        # 4. 内置应急规则（fallback）
        return {
            "rule_set_code": "default_v1",
            "rule_set_version": "v1.0.0",
            "rule_select_mode": "fallback",
            "rule_select_reason": f"无有效默认规则: {default_result['rule_select_reason']}",
            "resolved": False,
        }

    def save_rule_selection_to_batch(self, batch_id: str, selection: Dict,
                                      selected_by: str = "") -> bool:
        """
        将规则选择结果保存到批次表。

        Args:
            batch_id: 采购批次ID
            selection: resolve_rule_set 返回的选择结果
            selected_by: 操作人
        """
        try:
            conn = self.db.get_connection()
            cursor = conn.cursor()
            cursor.execute('''
                UPDATE smart_purchase_batches
                SET rule_set_code = ?,
                    rule_set_version = ?,
                    rule_select_mode = ?,
                    rule_select_reason = ?,
                    rule_selected_by = ?,
                    rule_selected_at = ?
                WHERE batch_id = ?
            ''', (
                selection["rule_set_code"],
                selection["rule_set_version"],
                selection["rule_select_mode"],
                selection["rule_select_reason"],
                selected_by,
                datetime.now().isoformat(),
                batch_id,
            ))
            conn.commit()
            return True
        except Exception as e:
            logging.error(f"保存规则选择到批次失败: {e}")
            return False

    def get_batch_rule_set_code(self, batch_id: str) -> Optional[str]:
        """获取批次已保存的规则集代码"""
        try:
            conn = self.db.get_connection()
            cursor = conn.cursor()
            cursor.execute(
                "SELECT rule_set_code FROM smart_purchase_batches WHERE batch_id = ?",
                (batch_id,)
            )
            row = cursor.fetchone()
            if row and row["rule_set_code"]:
                return row["rule_set_code"]
            return None
        except Exception:
            return None

    def get_available_rule_sets(self) -> list:
        """获取可用的规则集列表（已启用、已审核、active）"""
        try:
            conn = self.db.get_connection()
            cursor = conn.cursor()

            # 检查是否有 audit_status 和 version_status 字段
            cursor.execute("PRAGMA table_info(smart_match_rule_sets)")
            columns = {row["name"] for row in cursor.fetchall()}

            if "audit_status" in columns and "version_status" in columns:
                cursor.execute('''
                    SELECT rule_set_code, rule_set_name, version_number, is_default,
                           audit_status, version_status, is_enabled
                    FROM smart_match_rule_sets
                    WHERE is_enabled = 1
                    ORDER BY is_default DESC, rule_set_code
                ''')
            else:
                cursor.execute('''
                    SELECT rule_set_code, rule_set_name, version_number, is_default,
                           is_enabled
                    FROM smart_match_rule_sets
                    WHERE is_enabled = 1
                    ORDER BY is_default DESC, rule_set_code
                ''')

            rows = cursor.fetchall()
            result = []
            for row in rows:
                item = {
                    "rule_set_code": row["rule_set_code"],
                    "rule_set_name": row["rule_set_name"],
                    "version_number": row["version_number"] or "v1.0.0",
                    "is_default": bool(row["is_default"]),
                }
                # 如果有审核和版本状态字段，检查是否可用
                if "audit_status" in row.keys():
                    item["audit_status"] = row["audit_status"]
                    item["version_status"] = row["version_status"]
                    # 只展示已审核、active的规则
                    if row["audit_status"] == "approved" and row["version_status"] == "active":
                        item["available_for_purchase"] = True
                    else:
                        item["available_for_purchase"] = False
                else:
                    # 旧数据库没有审核字段，默认可用
                    item["available_for_purchase"] = True

                result.append(item)

            return result
        except Exception as e:
            logging.error(f"获取可用规则集列表失败: {e}")
            return []

    def _validate_and_resolve(self, rule_set_code: str, mode: str, reason: str) -> Dict:
        """验证并解析指定规则集"""
        try:
            conn = self.db.get_connection()
            cursor = conn.cursor()

            # 检查规则集是否存在且启用
            cursor.execute("PRAGMA table_info(smart_match_rule_sets)")
            columns = {row["name"] for row in cursor.fetchall()}

            if "audit_status" in columns and "version_status" in columns:
                cursor.execute('''
                    SELECT rule_set_code, version_number, is_enabled,
                           audit_status, version_status
                    FROM smart_match_rule_sets
                    WHERE rule_set_code = ?
                ''', (rule_set_code,))
            else:
                cursor.execute('''
                    SELECT rule_set_code, version_number, is_enabled
                    FROM smart_match_rule_sets
                    WHERE rule_set_code = ?
                ''', (rule_set_code,))

            row = cursor.fetchone()
            if not row:
                return {
                    "rule_set_code": rule_set_code,
                    "rule_set_version": "",
                    "rule_select_mode": mode,
                    "rule_select_reason": f"规则集 {rule_set_code} 不存在",
                    "resolved": False,
                }

            if not row["is_enabled"]:
                return {
                    "rule_set_code": rule_set_code,
                    "rule_set_version": row["version_number"] or "v1.0.0",
                    "rule_select_mode": mode,
                    "rule_select_reason": f"规则集 {rule_set_code} 已停用",
                    "resolved": False,
                }

            # 检查审核和版本状态
            if "audit_status" in row.keys():
                if row["audit_status"] != "approved":
                    return {
                        "rule_set_code": rule_set_code,
                        "rule_set_version": row["version_number"] or "v1.0.0",
                        "rule_select_mode": mode,
                        "rule_select_reason": f"规则集 {rule_set_code} 未审核（状态: {row['audit_status']}）",
                        "resolved": False,
                    }
                if row["version_status"] != "active":
                    return {
                        "rule_set_code": rule_set_code,
                        "rule_set_version": row["version_number"] or "v1.0.0",
                        "rule_select_mode": mode,
                        "rule_select_reason": f"规则集 {rule_set_code} 非活跃状态（状态: {row['version_status']}）",
                        "resolved": False,
                    }

            # 检查配置项是否完整
            cursor.execute(
                "SELECT COUNT(*) as cnt FROM smart_match_rule_configs "
                "WHERE rule_set_code = ? AND is_enabled = 1",
                (rule_set_code,)
            )
            config_count = cursor.fetchone()["cnt"]
            if config_count == 0:
                return {
                    "rule_set_code": rule_set_code,
                    "rule_set_version": row["version_number"] or "v1.0.0",
                    "rule_select_mode": mode,
                    "rule_select_reason": f"规则集 {rule_set_code} 无有效配置项",
                    "resolved": False,
                }

            return {
                "rule_set_code": rule_set_code,
                "rule_set_version": row["version_number"] or "v1.0.0",
                "rule_select_mode": mode,
                "rule_select_reason": reason,
                "resolved": True,
            }
        except Exception as e:
            return {
                "rule_set_code": rule_set_code,
                "rule_set_version": "",
                "rule_select_mode": mode,
                "rule_select_reason": f"验证规则集异常: {e}",
                "resolved": False,
            }

    def _resolve_default_rule(self) -> Dict:
        """解析系统默认规则"""
        try:
            conn = self.db.get_connection()
            cursor = conn.cursor()

            # 查找默认规则集
            cursor.execute("PRAGMA table_info(smart_match_rule_sets)")
            columns = {row["name"] for row in cursor.fetchall()}

            if "audit_status" in columns and "version_status" in columns:
                cursor.execute('''
                    SELECT rule_set_code, version_number
                    FROM smart_match_rule_sets
                    WHERE is_default = 1 AND is_enabled = 1
                      AND audit_status = 'approved' AND version_status = 'active'
                ''')
            else:
                cursor.execute('''
                    SELECT rule_set_code, version_number
                    FROM smart_match_rule_sets
                    WHERE is_default = 1 AND is_enabled = 1
                ''')

            rows = cursor.fetchall()

            if len(rows) == 0:
                return {
                    "rule_set_code": "",
                    "rule_set_version": "",
                    "rule_select_mode": "default",
                    "rule_select_reason": "无默认规则集",
                    "resolved": False,
                }

            if len(rows) > 1:
                codes = [r["rule_set_code"] for r in rows]
                return {
                    "rule_set_code": "",
                    "rule_set_version": "",
                    "rule_select_mode": "default",
                    "rule_select_reason": f"存在多个默认规则集: {codes}，请检查配置",
                    "resolved": False,
                }

            row = rows[0]
            return {
                "rule_set_code": row["rule_set_code"],
                "rule_set_version": row["version_number"] or "v1.0.0",
                "rule_select_mode": "default",
                "rule_select_reason": f"使用系统默认规则集 {row['rule_set_code']}",
                "resolved": True,
            }
        except Exception as e:
            return {
                "rule_set_code": "",
                "rule_set_version": "",
                "rule_select_mode": "default",
                "rule_select_reason": f"查询默认规则异常: {e}",
                "resolved": False,
            }
