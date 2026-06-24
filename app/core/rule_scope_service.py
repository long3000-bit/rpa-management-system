"""
规则生效范围控制服务（二期）
实现规则生效范围配置、管理、检查等功能
"""

import logging
import uuid
import json
from datetime import datetime
from typing import Dict, List, Optional, Tuple
from app.storage.database import Database


class RuleScopeService:
    """规则生效范围管理服务"""

    def __init__(self, db: Database):
        self.db = db
        self.logger = logging.getLogger(__name__)

    def set_rule_scope(self, rule_set_code: str, scope_config: Dict, user_id: str) -> Tuple[bool, str]:
        """
        设置规则生效范围
        
        Args:
            rule_set_code: 规则集编码
            scope_config: 范围配置，包含：
                - scope_type: 范围类型（batch、user、product_category、supplier_scope）
                - scope_value: 范围值列表
                - scope_priority: 范围优先级
                - scope_status: 范围状态（active、inactive）
            user_id: 创建人ID
        
        Returns:
            (success, error_msg): 是否成功和错误消息
        """
        conn = self.db.get_connection()
        cursor = conn.cursor()

        try:
            # 检查规则集是否存在
            cursor.execute(
                "SELECT id FROM smart_match_rule_sets WHERE rule_set_code = ?",
                (rule_set_code,)
            )
            row = cursor.fetchone()
            if not row:
                return False, f"规则集不存在：{rule_set_code}"

            scope_type = scope_config.get("scope_type", "batch")
            scope_value = json.dumps(scope_config.get("scope_value", []))
            scope_priority = scope_config.get("scope_priority", 0)
            scope_status = scope_config.get("scope_status", "active")

            now = datetime.now().isoformat()

            # 检查是否已有该类型的范围配置
            cursor.execute('''
                SELECT id FROM smart_rule_scope_configs
                WHERE rule_set_code = ? AND scope_type = ?
            ''', (rule_set_code, scope_type))

            existing_row = cursor.fetchone()

            if existing_row:
                # 更新现有配置
                cursor.execute('''
                    UPDATE smart_rule_scope_configs SET
                        scope_value = ?, scope_priority = ?, scope_status = ?,
                        updated_by = ?, updated_at = ?
                    WHERE rule_set_code = ? AND scope_type = ?
                ''', (
                    scope_value, scope_priority, scope_status,
                    user_id, now, rule_set_code, scope_type
                ))
            else:
                # 创建新配置
                scope_id = str(uuid.uuid4())
                cursor.execute('''
                    INSERT INTO smart_rule_scope_configs (
                        scope_id, rule_set_code, scope_type, scope_value,
                        scope_priority, scope_status, created_by, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (
                    scope_id, rule_set_code, scope_type, scope_value,
                    scope_priority, scope_status, user_id, now, now
                ))

            conn.commit()
            self.logger.info(f"设置规则生效范围成功：{rule_set_code} {scope_type}")
            return True, ""

        except Exception as e:
            conn.rollback()
            self.logger.error(f"设置规则生效范围失败：{str(e)}")
            return False, f"设置规则生效范围失败：{str(e)}"

    def get_rule_scope(self, rule_set_code: str) -> Tuple[List[Dict], str]:
        """
        获取规则生效范围
        
        Args:
            rule_set_code: 规则集编码
        
        Returns:
            (scope_list, error_msg): 范围列表和错误消息
        """
        conn = self.db.get_connection()
        cursor = conn.cursor()

        try:
            cursor.execute('''
                SELECT scope_id, rule_set_code, scope_type, scope_value,
                       scope_priority, scope_status, created_by, created_at, updated_at
                FROM smart_rule_scope_configs
                WHERE rule_set_code = ?
                ORDER BY scope_priority DESC
            ''', (rule_set_code,))

            scope_list = []
            for row in cursor.fetchall():
                scope_data = dict(row)
                scope_data["scope_value"] = json.loads(scope_data["scope_value"] or "[]")
                scope_list.append(scope_data)

            return scope_list, ""

        except Exception as e:
            self.logger.error(f"获取规则生效范围失败：{str(e)}")
            return [], f"获取规则生效范围失败：{str(e)}"

    def check_rule_scope(self, rule_set_code: str, batch_id: str, user_id: str, product_info: Dict) -> Tuple[bool, str]:
        """
        检查规则是否生效
        
        Args:
            rule_set_code: 规则集编码
            batch_id: 批次ID
            user_id: 用户ID
            product_info: 商品信息
        
        Returns:
            (is_effective, error_msg): 是否生效和错误消息
        """
        conn = self.db.get_connection()
        cursor = conn.cursor()

        try:
            # 获取规则集状态
            cursor.execute('''
                SELECT version_status, gray_release_status, gray_release_scope, gray_release_ratio
                FROM smart_match_rule_sets
                WHERE rule_set_code = ?
            ''', (rule_set_code,))

            row = cursor.fetchone()
            if not row:
                return False, f"规则集不存在：{rule_set_code}"

            # 检查版本状态
            if row["version_status"] != "active":
                return False, f"规则集未激活：{row['version_status']}"

            # 检查灰度发布状态
            gray_release_status = row["gray_release_status"]
            gray_release_scope = json.loads(row["gray_release_scope"] or "{}")
            gray_release_ratio = row["gray_release_ratio"]

            if gray_release_status == "testing":
                # 灰度发布中，需要检查是否符合灰度条件
                is_gray_eligible = self._check_gray_eligibility(
                    batch_id, user_id, product_info, gray_release_scope, gray_release_ratio
                )
                if not is_gray_eligible:
                    return False, "不符合灰度发布条件"

            # 获取规则生效范围配置
            cursor.execute('''
                SELECT scope_type, scope_value, scope_status
                FROM smart_rule_scope_configs
                WHERE rule_set_code = ? AND scope_status = 'active'
                ORDER BY scope_priority DESC
            ''', (rule_set_code,))

            scope_configs = cursor.fetchall()

            # 如果没有范围配置，默认对所有批次生效
            if not scope_configs:
                return True, ""

            # 检查是否符合任一范围配置
            for scope_config in scope_configs:
                scope_type = scope_config["scope_type"]
                scope_value = json.loads(scope_config["scope_value"] or "[]")

                if scope_type == "batch":
                    # 按批次范围检查
                    if batch_id in scope_value:
                        return True, ""

                elif scope_type == "user":
                    # 按用户范围检查
                    if user_id in scope_value:
                        return True, ""

                elif scope_type == "product_category":
                    # 按商品类别范围检查
                    product_category = product_info.get("category", "")
                    if product_category in scope_value:
                        return True, ""

                elif scope_type == "supplier_scope":
                    # 按供应商范围检查
                    supplier = product_info.get("supplier", "")
                    if supplier in scope_value:
                        return True, ""

            # 不符合任何范围配置
            return False, "不符合规则生效范围"

        except Exception as e:
            self.logger.error(f"检查规则生效范围失败：{str(e)}")
            return False, f"检查规则生效范围失败：{str(e)}"

    def _check_gray_eligibility(self, batch_id: str, user_id: str, product_info: Dict, gray_scope: Dict, gray_ratio: int) -> bool:
        """
        检查是否符合灰度发布条件
        
        Args:
            batch_id: 批次ID
            user_id: 用户ID
            product_info: 商品信息
            gray_scope: 灰度范围配置
            gray_ratio: 灰度比例
        
        Returns:
            is_eligible: 是否符合条件
        """
        # 根据灰度类型检查
        gray_type = gray_scope.get("gray_type", "ratio")

        if gray_type == "batch":
            # 按批次灰度
            gray_batches = gray_scope.get("gray_batches", [])
            return batch_id in gray_batches

        elif gray_type == "user":
            # 按用户灰度
            gray_users = gray_scope.get("gray_users", [])
            return user_id in gray_users

        elif gray_type == "product_scope":
            # 按商品范围灰度
            gray_categories = gray_scope.get("gray_categories", [])
            gray_suppliers = gray_scope.get("gray_suppliers", [])

            product_category = product_info.get("category", "")
            supplier = product_info.get("supplier", "")

            return product_category in gray_categories or supplier in gray_suppliers

        elif gray_type == "ratio":
            # 按比例灰度（使用批次ID哈希值）
            batch_hash = hash(batch_id)
            return batch_hash % 100 < gray_ratio

        return False

    def delete_rule_scope(self, rule_set_code: str, scope_type: str) -> Tuple[bool, str]:
        """
        删除规则生效范围
        
        Args:
            rule_set_code: 规则集编码
            scope_type: 范围类型
        
        Returns:
            (success, error_msg): 是否成功和错误消息
        """
        conn = self.db.get_connection()
        cursor = conn.cursor()

        try:
            cursor.execute('''
                DELETE FROM smart_rule_scope_configs
                WHERE rule_set_code = ? AND scope_type = ?
            ''', (rule_set_code, scope_type))

            conn.commit()
            self.logger.info(f"删除规则生效范围成功：{rule_set_code} {scope_type}")
            return True, ""

        except Exception as e:
            conn.rollback()
            self.logger.error(f"删除规则生效范围失败：{str(e)}")
            return False, f"删除规则生效范围失败：{str(e)}"

    def get_effective_rule_set(self, batch_id: str, user_id: str, product_info: Dict) -> Tuple[Dict, str]:
        """
        获取对指定批次生效的规则集
        
        Args:
            batch_id: 批次ID
            user_id: 用户ID
            product_info: 商品信息
        
        Returns:
            (rule_set_data, error_msg): 规则集数据和错误消息
        """
        conn = self.db.get_connection()
        cursor = conn.cursor()

        try:
            # 获取所有活跃的规则集
            cursor.execute('''
                SELECT rule_set_code, rule_set_name, version_number, version_status,
                       gray_release_status, gray_release_scope, gray_release_ratio
                FROM smart_match_rule_sets
                WHERE version_status = 'active'
                ORDER BY created_at DESC
            ''', (rule_set_code,))

            rule_sets = cursor.fetchall()

            # 检查每个规则集是否生效
            for rule_set in rule_sets:
                rule_set_code = rule_set["rule_set_code"]
                is_effective, _ = self.check_rule_scope(rule_set_code, batch_id, user_id, product_info)

                if is_effective:
                    # 返回生效的规则集
                    rule_set_data = dict(rule_set)
                    rule_set_data["gray_release_scope"] = json.loads(rule_set_data["gray_release_scope"] or "{}")
                    return rule_set_data, ""

            # 没有生效的规则集，返回默认规则集
            cursor.execute('''
                SELECT rule_set_code, rule_set_name, version_number
                FROM smart_match_rule_sets
                WHERE is_default = 1 AND is_enabled = 1
            ''', (rule_set_code,))

            default_row = cursor.fetchone()
            if default_row:
                return dict(default_row), ""

            return {}, "没有生效的规则集"

        except Exception as e:
            self.logger.error(f"获取生效规则集失败：{str(e)}")
            return {}, f"获取生效规则集失败：{str(e)}"