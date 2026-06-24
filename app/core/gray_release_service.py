"""
灰度发布服务（二期）
实现规则灰度发布、监控、回滚等功能
"""

import logging
import uuid
import json
from datetime import datetime
from typing import Dict, List, Optional, Tuple
from app.storage.database import Database


class GrayReleaseService:
    """灰度发布服务"""

    def __init__(self, db: Database):
        self.db = db
        self.logger = logging.getLogger(__name__)

    def start_gray_release(self, rule_set_code: str, gray_config: Dict, user_id: str) -> Tuple[bool, str]:
        """
        启动灰度发布
        
        Args:
            rule_set_code: 规则集编码
            gray_config: 灰度配置，包含：
                - gray_type: 灰度类型（batch、user、product_scope、ratio）
                - gray_scope: 灰度范围配置
                - gray_ratio: 灰度比例（0-100）
                - monitoring_metrics: 监控指标列表
                - rollback_threshold: 回滚阈值配置
            user_id: 创建人ID
        
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

            gray_type = gray_config.get("gray_type", "ratio")
            gray_scope = json.dumps(gray_config.get("gray_scope", {}))
            gray_ratio = gray_config.get("gray_ratio", 0)
            monitoring_metrics = json.dumps(gray_config.get("monitoring_metrics", []))
            rollback_threshold = json.dumps(gray_config.get("rollback_threshold", {}))

            now = datetime.now().isoformat()

            # 更新规则集灰度状态
            cursor.execute('''
                UPDATE smart_match_rule_sets SET
                    gray_release_scope = ?, gray_release_ratio = ?, gray_release_status = 'testing',
                    updated_at = ?
                WHERE rule_set_code = ?
            ''', (
                gray_scope, gray_ratio, now, rule_set_code
            ))

            # 创建灰度发布记录
            release_id = str(uuid.uuid4())
            cursor.execute('''
                INSERT INTO smart_rule_gray_release_logs (
                    release_id, rule_set_code, gray_type, gray_scope, gray_ratio,
                    gray_status, start_time, monitoring_metrics, rollback_threshold,
                    created_by, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                release_id, rule_set_code, gray_type, gray_scope, gray_ratio,
                "testing", now, monitoring_metrics, rollback_threshold,
                user_id, now, now
            ))

            conn.commit()
            self.logger.info(f"启动灰度发布成功：{rule_set_code} {gray_type}")
            return True, ""

        except Exception as e:
            conn.rollback()
            self.logger.error(f"启动灰度发布失败：{str(e)}")
            return False, f"启动灰度发布失败：{str(e)}"

    def stop_gray_release(self, rule_set_code: str, user_id: str) -> Tuple[bool, str]:
        """
        停止灰度发布
        
        Args:
            rule_set_code: 规则集编码
            user_id: 操作人ID
        
        Returns:
            (success, error_msg): 是否成功和错误消息
        """
        conn = self.db.get_connection()
        cursor = conn.cursor()

        try:
            # 检查规则集是否存在
            cursor.execute(
                "SELECT id, gray_release_status FROM smart_match_rule_sets WHERE rule_set_code = ?",
                (rule_set_code,)
            )
            row = cursor.fetchone()
            if not row:
                return False, f"规则集不存在：{rule_set_code}"

            if row["gray_release_status"] != "testing":
                return False, f"规则集不在灰度发布状态：{row['gray_release_status']}"

            now = datetime.now().isoformat()

            # 更新规则集灰度状态
            cursor.execute('''
                UPDATE smart_match_rule_sets SET
                    gray_release_status = 'none', gray_release_ratio = 0, updated_at = ?
                WHERE rule_set_code = ?
            ''', (
                now, rule_set_code
            ))

            # 更新灰度发布记录
            cursor.execute('''
                UPDATE smart_rule_gray_release_logs SET
                    gray_status = 'stopped', end_time = ?, updated_at = ?
                WHERE rule_set_code = ? AND gray_status = 'testing'
            ''', (
                now, now, rule_set_code
            ))

            conn.commit()
            self.logger.info(f"停止灰度发布成功：{rule_set_code}")
            return True, ""

        except Exception as e:
            conn.rollback()
            self.logger.error(f"停止灰度发布失败：{str(e)}")
            return False, f"停止灰度发布失败：{str(e)}"

    def get_gray_release_status(self, rule_set_code: str) -> Tuple[Dict, str]:
        """
        获取灰度发布状态
        
        Args:
            rule_set_code: 规则集编码
        
        Returns:
            (status_data, error_msg): 状态数据和错误消息
        """
        conn = self.db.get_connection()
        cursor = conn.cursor()

        try:
            # 获取规则集灰度状态
            cursor.execute('''
                SELECT rule_set_code, rule_set_name, version_number,
                       gray_release_scope, gray_release_ratio, gray_release_status
                FROM smart_match_rule_sets
                WHERE rule_set_code = ?
            ''', (rule_set_code,))

            row = cursor.fetchone()
            if not row:
                return {}, f"规则集不存在：{rule_set_code}"

            status_data = dict(row)
            status_data["gray_release_scope"] = json.loads(status_data["gray_release_scope"] or "{}")

            # 获取灰度发布记录
            cursor.execute('''
                SELECT release_id, gray_type, gray_scope, gray_ratio, gray_status,
                       start_time, end_time, monitoring_metrics, rollback_threshold
                FROM smart_rule_gray_release_logs
                WHERE rule_set_code = ? AND gray_status = 'testing'
                ORDER BY created_at DESC
                LIMIT 1
            ''', (rule_set_code,))

            release_row = cursor.fetchone()
            if release_row:
                release_data = dict(release_row)
                release_data["gray_scope"] = json.loads(release_data["gray_scope"] or "{}")
                release_data["monitoring_metrics"] = json.loads(release_data["monitoring_metrics"] or "[]")
                release_data["rollback_threshold"] = json.loads(release_data["rollback_threshold"] or "{}")
                status_data["release_record"] = release_data

            return status_data, ""

        except Exception as e:
            self.logger.error(f"获取灰度发布状态失败：{str(e)}")
            return {}, f"获取灰度发布状态失败：{str(e)}"

    def monitor_gray_release(self, rule_set_code: str) -> Tuple[Dict, str]:
        """
        监控灰度发布
        
        Args:
            rule_set_code: 规则集编码
        
        Returns:
            (monitoring_data, error_msg): 监控数据和错误消息
        """
        conn = self.db.get_connection()
        cursor = conn.cursor()

        try:
            # 获取灰度发布记录
            cursor.execute('''
                SELECT release_id, gray_type, gray_scope, gray_ratio, monitoring_metrics, rollback_threshold
                FROM smart_rule_gray_release_logs
                WHERE rule_set_code = ? AND gray_status = 'testing'
                ORDER BY created_at DESC
                LIMIT 1
            ''', (rule_set_code,))

            release_row = cursor.fetchone()
            if not release_row:
                return {}, f"没有进行中的灰度发布：{rule_set_code}"

            release_data = dict(release_row)
            gray_scope = json.loads(release_data["gray_scope"] or "{}")
            monitoring_metrics = json.loads(release_data["monitoring_metrics"] or "[]")
            rollback_threshold = json.loads(release_data["rollback_threshold"] or "{}")

            # 统计灰度批次的执行情况
            # TODO: 根据gray_type和gray_scope统计相关批次的数据
            monitoring_data = {
                "release_id": release_data["release_id"],
                "gray_type": release_data["gray_type"],
                "gray_ratio": release_data["gray_ratio"],
                "monitoring_metrics": monitoring_metrics,
                "rollback_threshold": rollback_threshold,
                "statistics": {
                    "total_batches": 0,
                    "gray_batches": 0,
                    "matched_items": 0,
                    "purchased_items": 0,
                    "failed_items": 0,
                    "match_success_rate": 0.0,
                    "purchase_success_rate": 0.0
                }
            }

            return monitoring_data, ""

        except Exception as e:
            self.logger.error(f"监控灰度发布失败：{str(e)}")
            return {}, f"监控灰度发布失败：{str(e)}"

    def rollback_gray_release(self, rule_set_code: str, reason: str, user_id: str) -> Tuple[bool, str]:
        """
        回滚灰度发布
        
        Args:
            rule_set_code: 规则集编码
            reason: 回滚原因
            user_id: 操作人ID
        
        Returns:
            (success, error_msg): 是否成功和错误消息
        """
        conn = self.db.get_connection()
        cursor = conn.cursor()

        try:
            # 检查规则集是否存在
            cursor.execute(
                "SELECT id, gray_release_status FROM smart_match_rule_sets WHERE rule_set_code = ?",
                (rule_set_code,)
            )
            row = cursor.fetchone()
            if not row:
                return False, f"规则集不存在：{rule_set_code}"

            if row["gray_release_status"] != "testing":
                return False, f"规则集不在灰度发布状态：{row['gray_release_status']}"

            now = datetime.now().isoformat()

            # 更新规则集灰度状态
            cursor.execute('''
                UPDATE smart_match_rule_sets SET
                    gray_release_status = 'none', gray_release_ratio = 0, updated_at = ?
                WHERE rule_set_code = ?
            ''', (
                now, rule_set_code
            ))

            # 更新灰度发布记录
            cursor.execute('''
                UPDATE smart_rule_gray_release_logs SET
                    gray_status = 'rollback', end_time = ?, rollback_reason = ?, updated_at = ?
                WHERE rule_set_code = ? AND gray_status = 'testing'
            ''', (
                now, reason, now, rule_set_code
            ))

            conn.commit()
            self.logger.info(f"回滚灰度发布成功：{rule_set_code} 原因：{reason}")
            return True, ""

        except Exception as e:
            conn.rollback()
            self.logger.error(f"回滚灰度发布失败：{str(e)}")
            return False, f"回滚灰度发布失败：{str(e)}"

    def check_gray_release_eligibility(self, rule_set_code: str, batch_id: str, user_id: str, product_info: Dict) -> Tuple[bool, str]:
        """
        检查批次是否符合灰度发布条件
        
        Args:
            rule_set_code: 规则集编码
            batch_id: 批次ID
            user_id: 用户ID
            product_info: 商品信息
        
        Returns:
            (is_eligible, error_msg): 是否符合条件和错误消息
        """
        conn = self.db.get_connection()
        cursor = conn.cursor()

        try:
            # 获取规则集灰度配置
            cursor.execute('''
                SELECT gray_release_scope, gray_release_ratio, gray_release_status
                FROM smart_match_rule_sets
                WHERE rule_set_code = ?
            ''', (rule_set_code,))

            row = cursor.fetchone()
            if not row:
                return False, f"规则集不存在：{rule_set_code}"

            if row["gray_release_status"] != "testing":
                return False, f"规则集不在灰度发布状态：{row['gray_release_status']}"

            gray_scope = json.loads(row["gray_release_scope"] or "{}")
            gray_ratio = row["gray_release_ratio"]

            # 根据灰度类型检查
            # TODO: 实现具体的灰度检查逻辑
            # 这里暂时返回True，实际需要根据gray_scope和gray_ratio进行检查
            return True, ""

        except Exception as e:
            self.logger.error(f"检查灰度发布条件失败：{str(e)}")
            return False, f"检查灰度发布条件失败：{str(e)}"