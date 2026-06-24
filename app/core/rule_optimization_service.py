"""
规则可持续优化服务（二期）
实现规则参数调整、测试、验证等功能
"""

import logging
import uuid
import json
from datetime import datetime
from typing import Dict, List, Optional, Tuple
from app.storage.database import Database


class RuleOptimizationService:
    """规则可持续优化服务"""

    def __init__(self, db: Database):
        self.db = db
        self.logger = logging.getLogger(__name__)

    def adjust_rule_params(self, rule_set_code: str, params: Dict, user_id: str) -> Tuple[str, str]:
        """
        调整规则参数
        
        Args:
            rule_set_code: 规则集编码
            params: 参数调整，包含：
                - adjustment_type: 调整类型（weight、threshold、combination）
                - new_params: 新参数配置
                - adjustment_reason: 调整原因
            user_id: 创建人ID
        
        Returns:
            (adjustment_id, error_msg): 调整ID和错误消息
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
                return "", f"规则集不存在：{rule_set_code}"

            # 获取当前参数配置
            cursor.execute('''
                SELECT rule_key, rule_value FROM smart_match_rule_configs
                WHERE rule_set_code = ?
            ''', (rule_set_code,))

            old_params = {}
            for config_row in cursor.fetchall():
                old_params[config_row["rule_key"]] = config_row["rule_value"]

            adjustment_type = params.get("adjustment_type", "weight")
            new_params = params.get("new_params", {})
            adjustment_reason = params.get("adjustment_reason", "")

            now = datetime.now().isoformat()

            # 创建调整记录
            adjustment_id = str(uuid.uuid4())
            cursor.execute('''
                INSERT INTO smart_rule_param_adjustments (
                    adjustment_id, rule_set_code, adjustment_type,
                    old_params, new_params, adjustment_reason,
                    test_status, created_by, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                adjustment_id, rule_set_code, adjustment_type,
                json.dumps(old_params), json.dumps(new_params), adjustment_reason,
                "pending", user_id, now, now
            ))

            conn.commit()
            self.logger.info(f"创建规则参数调整记录成功：{adjustment_id}")
            return adjustment_id, ""

        except Exception as e:
            conn.rollback()
            self.logger.error(f"创建规则参数调整记录失败：{str(e)}")
            return "", f"创建规则参数调整记录失败：{str(e)}"

    def test_rule_adjustment(self, adjustment_id: str, test_data: Dict) -> Tuple[Dict, str]:
        """
        测试规则调整
        
        Args:
            adjustment_id: 调整ID
            test_data: 测试数据，包含：
                - test_items: 测试商品列表
                - test_batch_id: 测试批次ID
        
        Returns:
            (test_result, error_msg): 测试结果和错误消息
        """
        conn = self.db.get_connection()
        cursor = conn.cursor()

        try:
            # 获取调整记录
            cursor.execute('''
                SELECT adjustment_id, rule_set_code, adjustment_type,
                       old_params, new_params, test_status
                FROM smart_rule_param_adjustments
                WHERE adjustment_id = ?
            ''', (adjustment_id,))

            row = cursor.fetchone()
            if not row:
                return {}, f"调整记录不存在：{adjustment_id}"

            if row["test_status"] != "pending":
                return {}, f"调整记录已测试：{row['test_status']}"

            rule_set_code = row["rule_set_code"]
            old_params = json.loads(row["old_params"] or "{}")
            new_params = json.loads(row["new_params"] or "{}")

            # 执行测试（这里只是模拟测试，实际需要调用评分逻辑）
            test_items = test_data.get("test_items", [])
            test_results = []

            for item in test_items:
                # 使用新参数计算评分
                # TODO: 实际调用评分逻辑
                new_score = self._calculate_score_with_params(item, new_params)
                old_score = self._calculate_score_with_params(item, old_params)

                test_results.append({
                    "item": item,
                    "old_score": old_score,
                    "new_score": new_score,
                    "score_diff": new_score - old_score
                })

            # 统计测试结果
            avg_old_score = sum(r["old_score"] for r in test_results) / len(test_results) if test_results else 0
            avg_new_score = sum(r["new_score"] for r in test_results) / len(test_results) if test_results else 0

            test_result = {
                "adjustment_id": adjustment_id,
                "test_items_count": len(test_items),
                "avg_old_score": avg_old_score,
                "avg_new_score": avg_new_score,
                "score_improvement": avg_new_score - avg_old_score,
                "test_results": test_results
            }

            # 更新调整记录
            now = datetime.now().isoformat()
            cursor.execute('''
                UPDATE smart_rule_param_adjustments SET
                    test_status = 'completed', test_result = ?, updated_at = ?
                WHERE adjustment_id = ?
            ''', (
                json.dumps(test_result), now, adjustment_id
            ))

            conn.commit()
            self.logger.info(f"测试规则调整成功：{adjustment_id}")
            return test_result, ""

        except Exception as e:
            conn.rollback()
            self.logger.error(f"测试规则调整失败：{str(e)}")
            return {}, f"测试规则调整失败：{str(e)}"

    def verify_rule_adjustment(self, adjustment_id: str) -> Tuple[bool, str]:
        """
        验证规则调整
        
        Args:
            adjustment_id: 调整ID
        
        Returns:
            (success, error_msg): 是否成功和错误消息
        """
        conn = self.db.get_connection()
        cursor = conn.cursor()

        try:
            # 获取调整记录
            cursor.execute('''
                SELECT adjustment_id, rule_set_code, test_status, verify_status, new_params
                FROM smart_rule_param_adjustments
                WHERE adjustment_id = ?
            ''', (adjustment_id,))

            row = cursor.fetchone()
            if not row:
                return False, f"调整记录不存在：{adjustment_id}"

            if row["test_status"] != "completed":
                return False, f"调整记录未测试：{row['test_status']}"

            if row["verify_status"] != "pending":
                return False, f"调整记录已验证：{row['verify_status']}"

            # 验证调整结果（这里只是模拟验证）
            # TODO: 实际验证逻辑
            verify_result = {
                "adjustment_id": adjustment_id,
                "verify_status": "approved",
                "verify_comment": "验证通过"
            }

            # 更新调整记录
            now = datetime.now().isoformat()
            cursor.execute('''
                UPDATE smart_rule_param_adjustments SET
                    verify_status = 'approved', verify_result = ?, updated_at = ?
                WHERE adjustment_id = ?
            ''', (
                json.dumps(verify_result), now, adjustment_id
            ))

            conn.commit()
            self.logger.info(f"验证规则调整成功：{adjustment_id}")
            return True, ""

        except Exception as e:
            conn.rollback()
            self.logger.error(f"验证规则调整失败：{str(e)}")
            return False, f"验证规则调整失败：{str(e)}"

    def apply_rule_adjustment(self, adjustment_id: str, user_id: str) -> Tuple[bool, str]:
        """
        应用规则调整
        
        Args:
            adjustment_id: 调整ID
            user_id: 应用人ID
        
        Returns:
            (success, error_msg): 是否成功和错误消息
        """
        conn = self.db.get_connection()
        cursor = conn.cursor()

        try:
            # 获取调整记录
            cursor.execute('''
                SELECT adjustment_id, rule_set_code, verify_status, new_params
                FROM smart_rule_param_adjustments
                WHERE adjustment_id = ?
            ''', (adjustment_id,))

            row = cursor.fetchone()
            if not row:
                return False, f"调整记录不存在：{adjustment_id}"

            if row["verify_status"] != "approved":
                return False, f"调整记录未验证通过：{row['verify_status']}"

            rule_set_code = row["rule_set_code"]
            new_params = json.loads(row["new_params"] or "{}")

            # 应用新参数到规则配置
            now = datetime.now().isoformat()
            for rule_key, rule_value in new_params.items():
                cursor.execute('''
                    UPDATE smart_match_rule_configs SET
                        rule_value = ?, updated_at = ?
                    WHERE rule_set_code = ? AND rule_key = ?
                ''', (
                    rule_value, now, rule_set_code, rule_key
                ))

            # 更新规则集版本号
            cursor.execute('''
                SELECT version_number FROM smart_match_rule_sets WHERE rule_set_code = ?
            ''', (rule_set_code,))

            version_row = cursor.fetchone()
            old_version = version_row["version_number"] if version_row else "v1.0.0"

            # 解析版本号并升级
            version_parts = old_version.split(".")
            if len(version_parts) >= 3:
                new_version = f"{version_parts[0]}.{version_parts[1]}.{int(version_parts[2]) + 1}"
            else:
                new_version = f"{old_version}.1"

            cursor.execute('''
                UPDATE smart_match_rule_sets SET
                    version_number = ?, updated_by = ?, updated_at = ?
                WHERE rule_set_code = ?
            ''', (
                new_version, user_id, now, rule_set_code
            ))

            conn.commit()
            self.logger.info(f"应用规则调整成功：{adjustment_id} -> {rule_set_code} {new_version}")
            return True, ""

        except Exception as e:
            conn.rollback()
            self.logger.error(f"应用规则调整失败：{str(e)}")
            return False, f"应用规则调整失败：{str(e)}"

    def get_adjustment_history(self, rule_set_code: str) -> Tuple[List[Dict], str]:
        """
        获取调整历史
        
        Args:
            rule_set_code: 规则集编码
        
        Returns:
            (history_list, error_msg): 历史列表和错误消息
        """
        conn = self.db.get_connection()
        cursor = conn.cursor()

        try:
            cursor.execute('''
                SELECT adjustment_id, rule_set_code, adjustment_type,
                       old_params, new_params, adjustment_reason,
                       test_status, test_result, verify_status, verify_result,
                       created_by, created_at
                FROM smart_rule_param_adjustments
                WHERE rule_set_code = ?
                ORDER BY created_at DESC
            ''', (rule_set_code,))

            history_list = []
            for row in cursor.fetchall():
                history_data = dict(row)
                history_data["old_params"] = json.loads(history_data["old_params"] or "{}")
                history_data["new_params"] = json.loads(history_data["new_params"] or "{}")
                history_data["test_result"] = json.loads(history_data["test_result"] or "{}")
                history_data["verify_result"] = json.loads(history_data["verify_result"] or "{}")
                history_list.append(history_data)

            return history_list, ""

        except Exception as e:
            self.logger.error(f"获取调整历史失败：{str(e)}")
            return [], f"获取调整历史失败：{str(e)}"

    def rollback_adjustment(self, adjustment_id: str, user_id: str) -> Tuple[bool, str]:
        """
        回滚调整
        
        Args:
            adjustment_id: 调整ID
            user_id: 回滚人ID
        
        Returns:
            (success, error_msg): 是否成功和错误消息
        """
        conn = self.db.get_connection()
        cursor = conn.cursor()

        try:
            # 获取调整记录
            cursor.execute('''
                SELECT adjustment_id, rule_set_code, old_params, verify_status
                FROM smart_rule_param_adjustments
                WHERE adjustment_id = ?
            ''', (adjustment_id,))

            row = cursor.fetchone()
            if not row:
                return False, f"调整记录不存在：{adjustment_id}"

            if row["verify_status"] != "approved":
                return False, f"调整记录未应用：{row['verify_status']}"

            rule_set_code = row["rule_set_code"]
            old_params = json.loads(row["old_params"] or "{}")

            # 回滚到旧参数
            now = datetime.now().isoformat()
            for rule_key, rule_value in old_params.items():
                cursor.execute('''
                    UPDATE smart_match_rule_configs SET
                        rule_value = ?, updated_at = ?
                    WHERE rule_set_code = ? AND rule_key = ?
                ''', (
                    rule_value, now, rule_set_code, rule_key
                ))

            # 更新规则集版本号
            cursor.execute('''
                SELECT version_number FROM smart_match_rule_sets WHERE rule_set_code = ?
            ''', (rule_set_code,))

            version_row = cursor.fetchone()
            old_version = version_row["version_number"] if version_row else "v1.0.0"

            # 解析版本号并升级（回滚也算版本升级）
            version_parts = old_version.split(".")
            if len(version_parts) >= 3:
                new_version = f"{version_parts[0]}.{version_parts[1]}.{int(version_parts[2]) + 1}"
            else:
                new_version = f"{old_version}.1"

            cursor.execute('''
                UPDATE smart_match_rule_sets SET
                    version_number = ?, updated_by = ?, updated_at = ?
                WHERE rule_set_code = ?
            ''', (
                new_version, user_id, now, rule_set_code
            ))

            conn.commit()
            self.logger.info(f"回滚调整成功：{adjustment_id} -> {rule_set_code} {new_version}")
            return True, ""

        except Exception as e:
            conn.rollback()
            self.logger.error(f"回滚调整失败：{str(e)}")
            return False, f"回滚调整失败：{str(e)}"

    def _calculate_score_with_params(self, item: Dict, params: Dict) -> int:
        """
        使用指定参数计算评分
        
        Args:
            item: 商品信息
            params: 参数配置
        
        Returns:
            score: 评分
        """
        # 这里只是模拟评分计算，实际需要调用评分逻辑
        # TODO: 实际评分逻辑

        name_weight = float(params.get("name_weight", 0.62))
        spec_weight = float(params.get("spec_weight", 0.20))
        maker_weight = float(params.get("maker_weight", 0.18))

        # 模拟评分
        name_score = 80
        spec_score = 90
        maker_score = 85

        total_score = int(name_score * name_weight + spec_score * spec_weight + maker_score * maker_weight)

        return total_score