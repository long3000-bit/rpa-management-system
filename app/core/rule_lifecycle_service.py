"""
规则生命周期服务 - 三期阶段4.2
管理规则集的状态流转：
- draft: 草稿状态，新创建的规则集
- pending_review: 待审核状态，已提交审核
- approved: 审核通过状态，可用于采购
- rejected: 审核拒绝状态，需要修改后重新提交
- active: 活跃状态，正在使用
- inactive: 停用状态，不可用于采购

状态流转：
- draft → pending_review → approved → active → inactive
- approved → rejected → draft
- inactive → active（重新启用）
"""
import logging
from datetime import datetime
from typing import Dict, List, Tuple

from app.storage.database import Database
from app.core.rule_validation_service import RuleValidationService


class RuleLifecycleService:
    """规则生命周期服务"""

    # 状态定义
    STATUS_DRAFT = "draft"
    STATUS_PENDING_REVIEW = "pending_review"
    STATUS_APPROVED = "approved"
    STATUS_REJECTED = "rejected"
    STATUS_ACTIVE = "active"
    STATUS_INACTIVE = "inactive"

    # 允许的状态流转
    ALLOWED_TRANSITIONS = {
        STATUS_DRAFT: [STATUS_PENDING_REVIEW],
        STATUS_PENDING_REVIEW: [STATUS_APPROVED, STATUS_REJECTED],
        STATUS_APPROVED: [STATUS_ACTIVE, STATUS_REJECTED],
        STATUS_REJECTED: [STATUS_DRAFT],
        STATUS_ACTIVE: [STATUS_INACTIVE],
        STATUS_INACTIVE: [STATUS_ACTIVE],
    }

    def __init__(self, db: Database):
        self.db = db
        self._validation_service = RuleValidationService(db)

    def create_draft_rule_set(self, rule_set_code: str, rule_set_name: str,
                               configs: List[Dict], created_by: str = "") -> Tuple[bool, str]:
        """
        创建草稿规则集。

        Args:
            rule_set_code: 规则集代码
            rule_set_name: 规则集名称
            configs: 配置项列表 [{"rule_key": ..., "rule_value": ..., "rule_type": ...}]
            created_by: 创建人

        Returns:
            (success, message)
        """
        try:
            conn = self.db.get_connection()
            cursor = conn.cursor()

            # 检查是否已存在
            cursor.execute(
                "SELECT rule_set_code FROM smart_match_rule_sets WHERE rule_set_code = ?",
                (rule_set_code,)
            )
            if cursor.fetchone():
                return False, f"规则集 {rule_set_code} 已存在"

            # 检查表结构是否有 version_status 字段
            cursor.execute("PRAGMA table_info(smart_match_rule_sets)")
            columns = {row["name"] for row in cursor.fetchall()}

            now = datetime.now().isoformat()

            # 插入规则集
            if "version_status" in columns and "audit_status" in columns:
                cursor.execute('''
                    INSERT INTO smart_match_rule_sets (
                        rule_set_code, rule_set_name, is_enabled, is_default,
                        version_number, version_status, audit_status,
                        created_by, created_at, updated_at
                    ) VALUES (?, ?, 1, 0, 'v1.0.0', ?, ?, ?, ?, ?)
                ''', (rule_set_code, rule_set_name, self.STATUS_DRAFT, self.STATUS_DRAFT,
                      created_by, now, now))
            else:
                cursor.execute('''
                    INSERT INTO smart_match_rule_sets (
                        rule_set_code, rule_set_name, is_enabled, is_default,
                        created_at, updated_at
                    ) VALUES (?, ?, 1, 0, ?, ?)
                ''', (rule_set_code, rule_set_name, now, now))

            # 插入配置项
            for i, config in enumerate(configs):
                cursor.execute('''
                    INSERT INTO smart_match_rule_configs (
                        rule_set_code, rule_key, rule_name, rule_value, rule_type,
                        description, sort_order, is_enabled, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, 1, ?, ?)
                ''', (
                    rule_set_code,
                    config.get("rule_key", ""),
                    config.get("rule_name", config.get("rule_key", "")),
                    config.get("rule_value", ""),
                    config.get("rule_type", "number"),
                    config.get("description", ""),
                    i + 1,
                    now,
                    now
                ))

            conn.commit()
            logging.info(f"创建草稿规则集: {rule_set_code} by {created_by}")
            return True, f"草稿规则集 {rule_set_code} 已创建"

        except Exception as e:
            logging.error(f"创建草稿规则集失败: {e}")
            return False, f"创建失败: {e}"

    def submit_for_review(self, rule_set_code: str, submitted_by: str = "") -> Tuple[bool, str]:
        """
        提交规则集审核。

        Args:
            rule_set_code: 规则集代码
            submitted_by: 提交人

        Returns:
            (success, message)
        """
        try:
            conn = self.db.get_connection()
            cursor = conn.cursor()

            # 获取当前状态
            cursor.execute("PRAGMA table_info(smart_match_rule_sets)")
            columns = {row["name"] for row in cursor.fetchall()}

            if "version_status" not in columns:
                return False, "数据库不支持状态流转（缺少 version_status 字段）"

            cursor.execute(
                "SELECT version_status, audit_status FROM smart_match_rule_sets WHERE rule_set_code = ?",
                (rule_set_code,)
            )
            row = cursor.fetchone()
            if not row:
                return False, f"规则集 {rule_set_code} 不存在"

            current_status = row["version_status"] or row["audit_status"]

            # 检查是否允许流转
            if current_status not in self.ALLOWED_TRANSITIONS:
                return False, f"当前状态 {current_status} 不允许流转"

            if self.STATUS_PENDING_REVIEW not in self.ALLOWED_TRANSITIONS.get(current_status, []):
                return False, f"状态 {current_status} 不能提交审核"

            # 参数校验
            is_valid, errors = self._validation_service.validate_rule_set(rule_set_code)
            if not is_valid:
                return False, f"参数校验失败: {errors[0]}"

            # 更新状态
            now = datetime.now().isoformat()
            cursor.execute('''
                UPDATE smart_match_rule_sets
                SET version_status = ?, audit_status = ?, updated_at = ?
                WHERE rule_set_code = ?
            ''', (self.STATUS_PENDING_REVIEW, self.STATUS_PENDING_REVIEW, now, rule_set_code))

            conn.commit()
            logging.info(f"提交规则集审核: {rule_set_code} by {submitted_by}")
            return True, f"规则集 {rule_set_code} 已提交审核"

        except Exception as e:
            logging.error(f"提交审核失败: {e}")
            return False, f"提交失败: {e}"

    def approve_rule_set(self, rule_set_code: str, reviewed_by: str = "",
                         review_comment: str = "") -> Tuple[bool, str]:
        """
        审核通过规则集。

        Args:
            rule_set_code: 规则集代码
            reviewed_by: 审核人
            review_comment: 审核意见

        Returns:
            (success, message)
        """
        try:
            conn = self.db.get_connection()
            cursor = conn.cursor()

            cursor.execute("PRAGMA table_info(smart_match_rule_sets)")
            columns = {row["name"] for row in cursor.fetchall()}

            if "version_status" not in columns:
                return False, "数据库不支持状态流转"

            cursor.execute(
                "SELECT version_status, audit_status FROM smart_match_rule_sets WHERE rule_set_code = ?",
                (rule_set_code,)
            )
            row = cursor.fetchone()
            if not row:
                return False, f"规则集 {rule_set_code} 不存在"

            current_status = row["version_status"] or row["audit_status"]

            if current_status != self.STATUS_PENDING_REVIEW:
                return False, f"规则集状态为 {current_status}，不能审核通过"

            now = datetime.now().isoformat()
            cursor.execute('''
                UPDATE smart_match_rule_sets
                SET version_status = ?, audit_status = ?, updated_at = ?
                WHERE rule_set_code = ?
            ''', (self.STATUS_APPROVED, self.STATUS_APPROVED, now, rule_set_code))

            conn.commit()
            logging.info(f"审核通过规则集: {rule_set_code} by {reviewed_by}")
            return True, f"规则集 {rule_set_code} 已审核通过"

        except Exception as e:
            logging.error(f"审核通过失败: {e}")
            return False, f"审核失败: {e}"

    def reject_rule_set(self, rule_set_code: str, reviewed_by: str = "",
                        review_comment: str = "") -> Tuple[bool, str]:
        """
        审核拒绝规则集。

        Args:
            rule_set_code: 规则集代码
            reviewed_by: 审核人
            review_comment: 审核意见（拒绝原因）

        Returns:
            (success, message)
        """
        try:
            conn = self.db.get_connection()
            cursor = conn.cursor()

            cursor.execute("PRAGMA table_info(smart_match_rule_sets)")
            columns = {row["name"] for row in cursor.fetchall()}

            if "version_status" not in columns:
                return False, "数据库不支持状态流转"

            cursor.execute(
                "SELECT version_status, audit_status FROM smart_match_rule_sets WHERE rule_set_code = ?",
                (rule_set_code,)
            )
            row = cursor.fetchone()
            if not row:
                return False, f"规则集 {rule_set_code} 不存在"

            current_status = row["version_status"] or row["audit_status"]

            if current_status not in [self.STATUS_PENDING_REVIEW, self.STATUS_APPROVED]:
                return False, f"规则集状态为 {current_status}，不能审核拒绝"

            now = datetime.now().isoformat()
            cursor.execute('''
                UPDATE smart_match_rule_sets
                SET version_status = ?, audit_status = ?, updated_at = ?
                WHERE rule_set_code = ?
            ''', (self.STATUS_REJECTED, self.STATUS_REJECTED, now, rule_set_code))

            conn.commit()
            logging.info(f"审核拒绝规则集: {rule_set_code} by {reviewed_by}: {review_comment}")
            return True, f"规则集 {rule_set_code} 已审核拒绝"

        except Exception as e:
            logging.error(f"审核拒绝失败: {e}")
            return False, f"审核失败: {e}"

    def activate_rule_set(self, rule_set_code: str, activated_by: str = "") -> Tuple[bool, str]:
        """
        激活规则集（发布或重新启用）。

        Args:
            rule_set_code: 规则集代码
            activated_by: 操作人

        Returns:
            (success, message)
        """
        try:
            conn = self.db.get_connection()
            cursor = conn.cursor()

            cursor.execute("PRAGMA table_info(smart_match_rule_sets)")
            columns = {row["name"] for row in cursor.fetchall()}

            if "version_status" not in columns:
                return False, "数据库不支持状态流转"

            cursor.execute(
                "SELECT version_status, audit_status, is_enabled FROM smart_match_rule_sets "
                "WHERE rule_set_code = ?",
                (rule_set_code,)
            )
            row = cursor.fetchone()
            if not row:
                return False, f"规则集 {rule_set_code} 不存在"

            current_status = row["version_status"] or row["audit_status"]

            if current_status not in [self.STATUS_APPROVED, self.STATUS_INACTIVE]:
                return False, f"规则集状态为 {current_status}，不能激活"

            now = datetime.now().isoformat()
            cursor.execute('''
                UPDATE smart_match_rule_sets
                SET version_status = ?, audit_status = ?, is_enabled = 1, updated_at = ?
                WHERE rule_set_code = ?
            ''', (self.STATUS_ACTIVE, self.STATUS_ACTIVE, now, rule_set_code))

            conn.commit()
            logging.info(f"激活规则集: {rule_set_code} by {activated_by}")
            return True, f"规则集 {rule_set_code} 已激活"

        except Exception as e:
            logging.error(f"激活规则集失败: {e}")
            return False, f"激活失败: {e}"

    def deactivate_rule_set(self, rule_set_code: str, deactivated_by: str = "",
                            reason: str = "") -> Tuple[bool, str]:
        """
        停用规则集。

        Args:
            rule_set_code: 规则集代码
            deactivated_by: 操作人
            reason: 停用原因

        Returns:
            (success, message)
        """
        try:
            conn = self.db.get_connection()
            cursor = conn.cursor()

            cursor.execute("PRAGMA table_info(smart_match_rule_sets)")
            columns = {row["name"] for row in cursor.fetchall()}

            if "version_status" not in columns:
                return False, "数据库不支持状态流转"

            cursor.execute(
                "SELECT version_status, audit_status FROM smart_match_rule_sets WHERE rule_set_code = ?",
                (rule_set_code,)
            )
            row = cursor.fetchone()
            if not row:
                return False, f"规则集 {rule_set_code} 不存在"

            current_status = row["version_status"] or row["audit_status"]

            if current_status != self.STATUS_ACTIVE:
                return False, f"规则集状态为 {current_status}，不能停用"

            now = datetime.now().isoformat()
            cursor.execute('''
                UPDATE smart_match_rule_sets
                SET version_status = ?, audit_status = ?, is_enabled = 0, updated_at = ?
                WHERE rule_set_code = ?
            ''', (self.STATUS_INACTIVE, self.STATUS_INACTIVE, now, rule_set_code))

            conn.commit()
            logging.info(f"停用规则集: {rule_set_code} by {deactivated_by}: {reason}")
            return True, f"规则集 {rule_set_code} 已停用"

        except Exception as e:
            logging.error(f"停用规则集失败: {e}")
            return False, f"停用失败: {e}"

    def get_rule_set_status(self, rule_set_code: str) -> Dict:
        """
        获取规则集状态信息。

        Returns:
            {
                "rule_set_code": str,
                "status": str,
                "is_enabled": bool,
                "allowed_transitions": list,
            }
        """
        try:
            conn = self.db.get_connection()
            cursor = conn.cursor()

            cursor.execute("PRAGMA table_info(smart_match_rule_sets)")
            columns = {row["name"] for row in cursor.fetchall()}

            cursor.execute(
                "SELECT rule_set_code, is_enabled, version_status, audit_status "
                "FROM smart_match_rule_sets WHERE rule_set_code = ?",
                (rule_set_code,)
            )
            row = cursor.fetchone()
            if not row:
                return {"rule_set_code": rule_set_code, "status": "not_found", "allowed_transitions": []}

            status = row["version_status"] or row["audit_status"] or "unknown"
            allowed = self.ALLOWED_TRANSITIONS.get(status, [])

            return {
                "rule_set_code": rule_set_code,
                "status": status,
                "is_enabled": bool(row["is_enabled"]),
                "allowed_transitions": allowed,
            }

        except Exception as e:
            return {"rule_set_code": rule_set_code, "status": "error", "error": str(e)}

    def get_all_rule_sets_with_status(self) -> List[Dict]:
        """
        获取所有规则集及其状态。
        """
        try:
            conn = self.db.get_connection()
            cursor = conn.cursor()

            cursor.execute("PRAGMA table_info(smart_match_rule_sets)")
            columns = {row["name"] for row in cursor.fetchall()}

            if "version_status" in columns:
                cursor.execute('''
                    SELECT rule_set_code, rule_set_name, is_enabled, is_default,
                           version_status, audit_status, version_number
                    FROM smart_match_rule_sets
                    ORDER BY is_default DESC, rule_set_code
                ''')
            else:
                cursor.execute('''
                    SELECT rule_set_code, rule_set_name, is_enabled, is_default
                    FROM smart_match_rule_sets
                    ORDER BY is_default DESC, rule_set_code
                ''')

            rows = cursor.fetchall()
            result = []
            for row in rows:
                # sqlite3.Row 不支持 .get()，需要用索引访问
                try:
                    status = row["version_status"] or row["audit_status"] or "legacy"
                except (KeyError, IndexError):
                    status = "legacy"
                try:
                    version_number = row["version_number"]
                except (KeyError, IndexError):
                    version_number = "v1.0.0"

                result.append({
                    "rule_set_code": row["rule_set_code"],
                    "rule_set_name": row["rule_set_name"],
                    "is_enabled": bool(row["is_enabled"]),
                    "is_default": bool(row["is_default"]),
                    "status": status,
                    "version_number": version_number,
                    "allowed_transitions": self.ALLOWED_TRANSITIONS.get(status, []),
                })

            return result

        except Exception as e:
            logging.error(f"获取规则集列表失败: {e}")
            return []