"""
规则版本管理服务（二期）
实现规则版本管理、灰度发布、审核等功能
"""

import logging
import uuid
import json
from datetime import datetime
from typing import Dict, List, Optional, Tuple
from app.storage.database import Database


class SmartRuleVersionService:
    """规则版本管理服务"""

    def __init__(self, db: Database):
        self.db = db
        self.logger = logging.getLogger(__name__)

    def create_rule_version(self, rule_data: Dict, user_id: str) -> Tuple[str, str]:
        """
        创建新规则版本
        
        Args:
            rule_data: 规则数据，包含：
                - rule_set_code: 规则集编码
                - rule_set_name: 规则集名称
                - description: 描述
                - version_number: 版本号
                - change_reason: 变更原因
                - change_type: 变更类型（new、update、rollback）
                - configs: 规则配置列表
            user_id: 创建人ID
        
        Returns:
            (rule_set_id, error_msg): 规则集ID和错误消息
        """
        conn = self.db.get_connection()
        cursor = conn.cursor()

        try:
            # 生成规则集ID
            rule_set_id = str(uuid.uuid4())
            rule_set_code = rule_data.get("rule_set_code")
            rule_set_name = rule_data.get("rule_set_name")
            description = rule_data.get("description", "")
            version_number = rule_data.get("version_number", "v1.0.0")
            change_reason = rule_data.get("change_reason", "")
            change_type = rule_data.get("change_type", "new")
            configs = rule_data.get("configs", [])
            
            # 检查规则集编码是否已存在
            cursor.execute(
                "SELECT rule_set_code FROM smart_match_rule_sets WHERE rule_set_code = ?",
                (rule_set_code,)
            )
            if cursor.fetchone():
                return "", f"规则集编码已存在：{rule_set_code}"

            # 插入规则集
            now = datetime.now().isoformat()
            cursor.execute('''
                INSERT INTO smart_match_rule_sets (
                    rule_set_code, rule_set_name, description,
                    version_number, version_status, change_reason, change_type,
                    audit_status, created_by, created_at, updated_at, updated_by
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                rule_set_code, rule_set_name, description,
                version_number, "draft", change_reason, change_type,
                "pending", user_id, now, now, user_id
            ))

            # 插入规则配置
            for config in configs:
                rule_key = config.get("rule_key")
                rule_name = config.get("rule_name")
                rule_value = config.get("rule_value")
                rule_type = config.get("rule_type")
                config_description = config.get("description", "")
                sort_order = config.get("sort_order", 0)

                cursor.execute('''
                    INSERT INTO smart_match_rule_configs (
                        rule_set_code, rule_key, rule_name, rule_value, rule_type,
                        description, sort_order, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (
                    rule_set_code, rule_key, rule_name, rule_value, rule_type,
                    config_description, sort_order, now, now
                ))

            # 创建审核记录
            audit_id = str(uuid.uuid4())
            cursor.execute('''
                INSERT INTO smart_rule_audit_logs (
                    audit_id, rule_set_code, change_type, change_reason,
                    new_version, audit_status, created_by, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                audit_id, rule_set_code, change_type, change_reason,
                version_number, "pending", user_id, now, now
            ))

            conn.commit()
            self.logger.info(f"创建规则版本成功：{rule_set_code} v{version_number}")
            return rule_set_id, ""

        except Exception as e:
            conn.rollback()
            self.logger.error(f"创建规则版本失败：{str(e)}")
            return "", f"创建规则版本失败：{str(e)}"

    def update_rule_version(self, rule_set_code: str, rule_data: Dict, user_id: str) -> Tuple[bool, str]:
        """
        更新规则版本
        
        Args:
            rule_set_code: 规则集编码
            rule_data: 规则数据，包含：
                - rule_set_name: 规则集名称
                - description: 描述
                - version_number: 版本号
                - change_reason: 变更原因
                - configs: 规则配置列表
            user_id: 更新人ID
        
        Returns:
            (success, error_msg): 是否成功和错误消息
        """
        conn = self.db.get_connection()
        cursor = conn.cursor()

        try:
            # 检查规则集是否存在
            cursor.execute(
                "SELECT id, version_number FROM smart_match_rule_sets WHERE rule_set_code = ?",
                (rule_set_code,)
            )
            row = cursor.fetchone()
            if not row:
                return False, f"规则集不存在：{rule_set_code}"

            old_version = row["version_number"]
            rule_set_name = rule_data.get("rule_set_name")
            description = rule_data.get("description", "")
            version_number = rule_data.get("version_number", old_version)
            change_reason = rule_data.get("change_reason", "")
            configs = rule_data.get("configs", [])

            # 更新规则集
            now = datetime.now().isoformat()
            cursor.execute('''
                UPDATE smart_match_rule_sets SET
                    rule_set_name = ?, description = ?, version_number = ?,
                    change_reason = ?, change_type = 'update',
                    audit_status = 'pending', updated_by = ?, updated_at = ?
                WHERE rule_set_code = ?
            ''', (
                rule_set_name, description, version_number,
                change_reason, user_id, now, rule_set_code
            ))

            # 删除旧配置
            cursor.execute(
                "DELETE FROM smart_match_rule_configs WHERE rule_set_code = ?",
                (rule_set_code,)
            )

            # 插入新配置
            for config in configs:
                rule_key = config.get("rule_key")
                rule_name = config.get("rule_name")
                rule_value = config.get("rule_value")
                rule_type = config.get("rule_type")
                config_description = config.get("description", "")
                sort_order = config.get("sort_order", 0)

                cursor.execute('''
                    INSERT INTO smart_match_rule_configs (
                        rule_set_code, rule_key, rule_name, rule_value, rule_type,
                        description, sort_order, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (
                    rule_set_code, rule_key, rule_name, rule_value, rule_type,
                    config_description, sort_order, now, now
                ))

            # 创建审核记录
            audit_id = str(uuid.uuid4())
            cursor.execute('''
                INSERT INTO smart_rule_audit_logs (
                    audit_id, rule_set_code, change_type, change_reason,
                    old_version, new_version, audit_status, created_by, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                audit_id, rule_set_code, "update", change_reason,
                old_version, version_number, "pending", user_id, now, now
            ))

            conn.commit()
            self.logger.info(f"更新规则版本成功：{rule_set_code} v{version_number}")
            return True, ""

        except Exception as e:
            conn.rollback()
            self.logger.error(f"更新规则版本失败：{str(e)}")
            return False, f"更新规则版本失败：{str(e)}"

    def audit_rule_version(self, audit_id: str, audit_status: str, audit_by: str, audit_comment: str = "") -> Tuple[bool, str]:
        """
        审核规则版本
        
        Args:
            audit_id: 审核记录ID
            audit_status: 审核状态（approved、rejected）
            audit_by: 审核人ID
            audit_comment: 审核备注
        
        Returns:
            (success, error_msg): 是否成功和错误消息
        """
        conn = self.db.get_connection()
        cursor = conn.cursor()

        try:
            # 检查审核记录是否存在
            cursor.execute(
                "SELECT audit_id, rule_set_code, audit_status FROM smart_rule_audit_logs WHERE audit_id = ?",
                (audit_id,)
            )
            row = cursor.fetchone()
            if not row:
                return False, f"审核记录不存在：{audit_id}"

            if row["audit_status"] != "pending":
                return False, f"审核记录已处理：{row['audit_status']}"

            rule_set_code = row["rule_set_code"]
            now = datetime.now().isoformat()

            # 更新审核记录
            cursor.execute('''
                UPDATE smart_rule_audit_logs SET
                    audit_status = ?, audit_by = ?, audit_at = ?, audit_comment = ?, updated_at = ?
                WHERE audit_id = ?
            ''', (
                audit_status, audit_by, now, audit_comment, now, audit_id
            ))

            # 如果审核通过，更新规则集状态
            if audit_status == "approved":
                cursor.execute('''
                    UPDATE smart_match_rule_sets SET
                        version_status = 'testing', audit_status = 'approved',
                        audit_by = ?, audit_at = ?, audit_comment = ?, updated_at = ?
                    WHERE rule_set_code = ?
                ''', (
                    audit_by, now, audit_comment, now, rule_set_code
                ))

            conn.commit()
            self.logger.info(f"审核规则版本成功：{audit_id} {audit_status}")
            return True, ""

        except Exception as e:
            conn.rollback()
            self.logger.error(f"审核规则版本失败：{str(e)}")
            return False, f"审核规则版本失败：{str(e)}"

    def release_rule_version(self, rule_set_code: str, release_type: str, gray_config: Dict = None) -> Tuple[bool, str]:
        """
        发布规则版本
        
        Args:
            rule_set_code: 规则集编码
            release_type: 发布类型（testing、gray、full）
            gray_config: 灰度配置（可选），包含：
                - gray_type: 灰度类型（batch、user、product_scope、ratio）
                - gray_scope: 灰度范围配置
                - gray_ratio: 灰度比例（0-100）
        
        Returns:
            (success, error_msg): 是否成功和错误消息
        """
        conn = self.db.get_connection()
        cursor = conn.cursor()

        try:
            # 检查规则集是否存在
            cursor.execute(
                "SELECT id, version_status, audit_status FROM smart_match_rule_sets WHERE rule_set_code = ?",
                (rule_set_code,)
            )
            row = cursor.fetchone()
            if not row:
                return False, f"规则集不存在：{rule_set_code}"

            if row["audit_status"] != "approved":
                return False, f"规则集未审核通过：{row['audit_status']}"

            now = datetime.now().isoformat()

            if release_type == "testing":
                # 测试发布
                cursor.execute('''
                    UPDATE smart_match_rule_sets SET
                        version_status = 'testing', release_date = ?, updated_at = ?
                    WHERE rule_set_code = ?
                ''', (
                    now, now, rule_set_code
                ))

            elif release_type == "gray":
                # 灰度发布
                gray_type = gray_config.get("gray_type", "ratio")
                gray_scope = json.dumps(gray_config.get("gray_scope", {}))
                gray_ratio = gray_config.get("gray_ratio", 0)

                cursor.execute('''
                    UPDATE smart_match_rule_sets SET
                        version_status = 'active', gray_release_scope = ?, gray_release_ratio = ?,
                        gray_release_status = 'testing', release_date = ?, updated_at = ?
                    WHERE rule_set_code = ?
                ''', (
                    gray_scope, gray_ratio, now, now, rule_set_code
                ))

                # 创建灰度发布记录
                release_id = str(uuid.uuid4())
                cursor.execute('''
                    INSERT INTO smart_rule_gray_release_logs (
                        release_id, rule_set_code, gray_type, gray_scope, gray_ratio,
                        gray_status, start_time, created_by, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (
                    release_id, rule_set_code, gray_type, gray_scope, gray_ratio,
                    "testing", now, "system", now, now
                ))

            elif release_type == "full":
                # 全量发布
                cursor.execute('''
                    UPDATE smart_match_rule_sets SET
                        version_status = 'active', gray_release_status = 'full',
                        release_date = ?, updated_at = ?
                    WHERE rule_set_code = ?
                ''', (
                    now, now, rule_set_code
                ))

                # 将其他同规则集的版本设置为deprecated
                cursor.execute('''
                    UPDATE smart_match_rule_sets SET
                        version_status = 'deprecated', deprecation_date = ?, updated_at = ?
                    WHERE rule_set_code = ? AND version_status = 'active' AND rule_set_code != ?
                ''', (
                    now, now, rule_set_code, rule_set_code
                ))

            conn.commit()
            self.logger.info(f"发布规则版本成功：{rule_set_code} {release_type}")
            return True, ""

        except Exception as e:
            conn.rollback()
            self.logger.error(f"发布规则版本失败：{str(e)}")
            return False, f"发布规则版本失败：{str(e)}"

    def rollback_rule_version(self, rule_set_code: str, rollback_to_version: str) -> Tuple[bool, str]:
        """
        回滚规则版本
        
        Args:
            rule_set_code: 规则集编码
            rollback_to_version: 回滚到的版本号
        
        Returns:
            (success, error_msg): 是否成功和错误消息
        """
        conn = self.db.get_connection()
        cursor = conn.cursor()

        try:
            # 检查当前版本
            cursor.execute(
                "SELECT id, version_number FROM smart_match_rule_sets WHERE rule_set_code = ? AND version_status = 'active'",
                (rule_set_code,)
            )
            current_row = cursor.fetchone()
            if not current_row:
                return False, f"当前没有活跃版本：{rule_set_code}"

            current_version = current_row["version_number"]

            # 检查目标版本
            cursor.execute(
                "SELECT id, version_number, version_status FROM smart_match_rule_sets WHERE rule_set_code = ? AND version_number = ?",
                (rule_set_code, rollback_to_version)
            )
            target_row = cursor.fetchone()
            if not target_row:
                return False, f"目标版本不存在：{rollback_to_version}"

            now = datetime.now().isoformat()

            # 将当前版本设置为deprecated
            cursor.execute('''
                UPDATE smart_match_rule_sets SET
                    version_status = 'deprecated', deprecation_date = ?, updated_at = ?
                WHERE rule_set_code = ? AND version_number = ?
            ''', (
                now, now, rule_set_code, current_version
            ))

            # 将目标版本设置为active
            cursor.execute('''
                UPDATE smart_match_rule_sets SET
                    version_status = 'active', change_type = 'rollback',
                    change_reason = '回滚到版本 ' + ?,
                    updated_at = ?
                WHERE rule_set_code = ? AND version_number = ?
            ''', (
                rollback_to_version, now, rule_set_code, rollback_to_version
            ))

            # 创建审核记录
            audit_id = str(uuid.uuid4())
            cursor.execute('''
                INSERT INTO smart_rule_audit_logs (
                    audit_id, rule_set_code, change_type, change_reason,
                    old_version, new_version, audit_status, audit_by, audit_at, created_by, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                audit_id, rule_set_code, "rollback", f"回滚到版本 {rollback_to_version}",
                current_version, rollback_to_version, "approved", "system", now, "system", now, now
            ))

            conn.commit()
            self.logger.info(f"回滚规则版本成功：{rule_set_code} {current_version} -> {rollback_to_version}")
            return True, ""

        except Exception as e:
            conn.rollback()
            self.logger.error(f"回滚规则版本失败：{str(e)}")
            return False, f"回滚规则版本失败：{str(e)}"

    def compare_rule_versions(self, version1: str, version2: str) -> Tuple[Dict, str]:
        """
        对比规则版本
        
        Args:
            version1: 版本1的规则集编码和版本号（格式：rule_set_code@version_number）
            version2: 版本2的规则集编码和版本号
        
        Returns:
            (comparison_result, error_msg): 对比结果和错误消息
        """
        conn = self.db.get_connection()
        cursor = conn.cursor()

        try:
            # 解析版本信息
            v1_parts = version1.split("@")
            v2_parts = version2.split("@")

            if len(v1_parts) != 2 or len(v2_parts) != 2:
                return {}, "版本格式错误，应为：rule_set_code@version_number"

            v1_rule_set_code, v1_version_number = v1_parts
            v2_rule_set_code, v2_version_number = v2_parts

            # 获取版本1的配置
            cursor.execute('''
                SELECT rule_key, rule_name, rule_value, rule_type, description
                FROM smart_match_rule_configs
                WHERE rule_set_code = ?
            ''', (v1_rule_set_code,))
            v1_configs = cursor.fetchall()

            # 获取版本2的配置
            cursor.execute('''
                SELECT rule_key, rule_name, rule_value, rule_type, description
                FROM smart_match_rule_configs
                WHERE rule_set_code = ?
            ''', (v2_rule_set_code,))
            v2_configs = cursor.fetchall()

            # 构建对比结果
            comparison_result = {
                "version1": {
                    "rule_set_code": v1_rule_set_code,
                    "version_number": v1_version_number,
                    "configs": [dict(row) for row in v1_configs]
                },
                "version2": {
                    "rule_set_code": v2_rule_set_code,
                    "version_number": v2_version_number,
                    "configs": [dict(row) for row in v2_configs]
                },
                "differences": []
            }

            # 对比配置差异
            v1_config_map = {row["rule_key"]: row for row in v1_configs}
            v2_config_map = {row["rule_key"]: row for row in v2_configs}

            all_keys = set(v1_config_map.keys()) | set(v2_config_map.keys())

            for key in all_keys:
                v1_config = v1_config_map.get(key)
                v2_config = v2_config_map.get(key)

                if v1_config and v2_config:
                    # 两个版本都有这个配置
                    if v1_config["rule_value"] != v2_config["rule_value"]:
                        comparison_result["differences"].append({
                            "rule_key": key,
                            "change_type": "modified",
                            "old_value": v1_config["rule_value"],
                            "new_value": v2_config["rule_value"]
                        })
                elif v1_config and not v2_config:
                    # 版本1有，版本2没有
                    comparison_result["differences"].append({
                        "rule_key": key,
                        "change_type": "removed",
                        "old_value": v1_config["rule_value"],
                        "new_value": None
                    })
                elif not v1_config and v2_config:
                    # 版本1没有，版本2有
                    comparison_result["differences"].append({
                        "rule_key": key,
                        "change_type": "added",
                        "old_value": None,
                        "new_value": v2_config["rule_value"]
                    })

            return comparison_result, ""

        except Exception as e:
            self.logger.error(f"对比规则版本失败：{str(e)}")
            return {}, f"对比规则版本失败：{str(e)}"

    def get_rule_version_history(self, rule_set_code: str) -> Tuple[List[Dict], str]:
        """
        获取规则版本历史
        
        Args:
            rule_set_code: 规则集编码
        
        Returns:
            (history_list, error_msg): 历史记录列表和错误消息
        """
        conn = self.db.get_connection()
        cursor = conn.cursor()

        try:
            # 获取审核记录
            cursor.execute('''
                SELECT audit_id, rule_set_code, change_type, change_reason,
                       old_version, new_version, audit_status, audit_by, audit_at,
                       audit_comment, created_by, created_at
                FROM smart_rule_audit_logs
                WHERE rule_set_code = ?
                ORDER BY created_at DESC
            ''', (rule_set_code,))

            history_list = [dict(row) for row in cursor.fetchall()]
            return history_list, ""

        except Exception as e:
            self.logger.error(f"获取规则版本历史失败：{str(e)}")
            return [], f"获取规则版本历史失败：{str(e)}"

    def get_active_rule_version(self, rule_set_code: str) -> Tuple[Dict, str]:
        """
        获取当前活跃的规则版本
        
        Args:
            rule_set_code: 规则集编码
        
        Returns:
            (rule_data, error_msg): 规则数据和错误消息
        """
        conn = self.db.get_connection()
        cursor = conn.cursor()

        try:
            # 获取规则集
            cursor.execute('''
                SELECT rule_set_code, rule_set_name, description, version_number,
                       version_status, change_reason, change_type, audit_status,
                       gray_release_scope, gray_release_ratio, gray_release_status
                FROM smart_match_rule_sets
                WHERE rule_set_code = ? AND version_status = 'active'
            ''', (rule_set_code,))

            row = cursor.fetchone()
            if not row:
                return {}, f"没有活跃的规则版本：{rule_set_code}"

            rule_data = dict(row)

            # 获取规则配置
            cursor.execute('''
                SELECT rule_key, rule_name, rule_value, rule_type, description, sort_order
                FROM smart_match_rule_configs
                WHERE rule_set_code = ?
                ORDER BY sort_order
            ''', (rule_set_code,))

            rule_data["configs"] = [dict(row) for row in cursor.fetchall()]
            return rule_data, ""

        except Exception as e:
            self.logger.error(f"获取活跃规则版本失败：{str(e)}")
            return {}, f"获取活跃规则版本失败：{str(e)}"