"""
规则效果统计服务（二期）
实现规则效果统计、对比、趋势分析等功能
"""

import logging
import uuid
import json
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from app.storage.database import Database


class RuleEffectService:
    """规则效果统计服务"""

    def __init__(self, db: Database):
        self.db = db
        self.logger = logging.getLogger(__name__)

    def get_rule_effect_stats(self, rule_set_code: str, start_date: str, end_date: str) -> Tuple[Dict, str]:
        """
        获取规则效果统计
        
        Args:
            rule_set_code: 规则集编码
            start_date: 开始日期（YYYY-MM-DD）
            end_date: 结束日期（YYYY-MM-DD）
        
        Returns:
            (stats_data, error_msg): 统计数据和错误消息
        """
        conn = self.db.get_connection()
        cursor = conn.cursor()

        # 计算日期范围：start_date 当天 00:00:00 到 end_date 次日 00:00:00
        date_start = f"{start_date}T00:00:00"
        try:
            end_dt = datetime.strptime(end_date, "%Y-%m-%d") + timedelta(days=1)
            date_end = end_dt.strftime("%Y-%m-%d") + "T00:00:00"
        except Exception:
            date_end = f"{end_date}T23:59:59"

        try:
            # 统计匹配成功率（使用final_pass和selected代替purchase_status）
            cursor.execute('''
                SELECT COUNT(*) as total_items,
                       SUM(CASE WHEN total_score >= 60 THEN 1 ELSE 0 END) as matched_items,
                       SUM(CASE WHEN final_pass = 1 AND selected = 1 THEN 1 ELSE 0 END) as purchased_items,
                       SUM(CASE WHEN final_pass = 0 AND selected = 0 THEN 1 ELSE 0 END) as failed_items,
                       AVG(total_score) as avg_match_score
                FROM smart_purchase_candidates
                WHERE rule_set_code = ?
                  AND created_at >= ?
                  AND created_at < ?
            ''', (rule_set_code, date_start, date_end))

            row = cursor.fetchone()
            if not row:
                return {}, f"没有统计数据：{rule_set_code}"

            total_items = row["total_items"] or 0
            matched_items = row["matched_items"] or 0
            purchased_items = row["purchased_items"] or 0
            failed_items = row["failed_items"] or 0
            avg_match_score = row["avg_match_score"] or 0

            # 计算成功率
            match_success_rate = matched_items / total_items if total_items > 0 else 0
            purchase_success_rate = purchased_items / matched_items if matched_items > 0 else 0

            # 统计失败原因分布（使用reject_reason代替purchase_reason）
            cursor.execute('''
                SELECT reject_reason, COUNT(*) as count
                FROM smart_purchase_candidates
                WHERE rule_set_code = ?
                  AND final_pass = 0
                  AND created_at >= ?
                  AND created_at < ?
                GROUP BY reject_reason
                ORDER BY count DESC
            ''', (rule_set_code, date_start, date_end))

            failure_reason_distribution = {}
            for row in cursor.fetchall():
                reason = row["reject_reason"] or "未知原因"
                count = row["count"] or 0
                failure_reason_distribution[reason] = count

            # 二期整改：基于failure_code聚合统计失败原因
            failure_code_distribution = {}
            try:
                cursor.execute('''
                    SELECT failure_code, COUNT(*) as count
                    FROM smart_purchase_failure_reasons
                    WHERE rule_set_code = ?
                      AND created_at >= ?
                      AND created_at < ?
                    GROUP BY failure_code
                    ORDER BY count DESC
                ''', (rule_set_code, date_start, date_end))

                for row in cursor.fetchall():
                    code = row["failure_code"] or "UNKNOWN"
                    count = row["count"] or 0
                    failure_code_distribution[code] = count
            except Exception:
                # 表不存在时忽略
                pass

            # 统计评分分布
            cursor.execute('''
                SELECT
                    CASE
                        WHEN total_score >= 90 THEN '90-100'
                        WHEN total_score >= 80 THEN '80-89'
                        WHEN total_score >= 70 THEN '70-79'
                        WHEN total_score >= 60 THEN '60-69'
                        ELSE '<60'
                    END as score_range,
                    COUNT(*) as count
                FROM smart_purchase_candidates
                WHERE rule_set_code = ?
                  AND created_at >= ?
                  AND created_at < ?
                GROUP BY score_range
                ORDER BY score_range DESC
            ''', (rule_set_code, date_start, date_end))

            score_distribution = {}
            for row in cursor.fetchall():
                score_range = row["score_range"]
                count = row["count"] or 0
                score_distribution[score_range] = count

            stats_data = {
                "rule_set_code": rule_set_code,
                "start_date": start_date,
                "end_date": end_date,
                "total_items": total_items,
                "matched_items": matched_items,
                "purchased_items": purchased_items,
                "failed_items": failed_items,
                "match_success_rate": match_success_rate,
                "purchase_success_rate": purchase_success_rate,
                "avg_match_score": avg_match_score,
                "failure_reason_distribution": failure_reason_distribution,
                "failure_code_distribution": failure_code_distribution,
                "score_distribution": score_distribution
            }

            return stats_data, ""

        except Exception as e:
            self.logger.error(f"获取规则效果统计失败：{str(e)}")
            return {}, f"获取规则效果统计失败：{str(e)}"

    def compare_rule_effects(self, version1: str, version2: str) -> Tuple[Dict, str]:
        """
        对比规则效果
        
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

            # 获取版本1的统计数据（最近7天）
            end_date = datetime.now().strftime("%Y-%m-%d")
            start_date = (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d")

            v1_stats, v1_error = self.get_rule_effect_stats(v1_rule_set_code, start_date, end_date)
            if v1_error:
                return {}, v1_error

            # 获取版本2的统计数据（最近7天）
            v2_stats, v2_error = self.get_rule_effect_stats(v2_rule_set_code, start_date, end_date)
            if v2_error:
                return {}, v2_error

            # 构建对比结果
            comparison_result = {
                "version1": {
                    "rule_set_code": v1_rule_set_code,
                    "version_number": v1_version_number,
                    "stats": v1_stats
                },
                "version2": {
                    "rule_set_code": v2_rule_set_code,
                    "version_number": v2_version_number,
                    "stats": v2_stats
                },
                "comparison": {
                    "match_success_rate_diff": v2_stats["match_success_rate"] - v1_stats["match_success_rate"],
                    "purchase_success_rate_diff": v2_stats["purchase_success_rate"] - v1_stats["purchase_success_rate"],
                    "avg_match_score_diff": v2_stats["avg_match_score"] - v1_stats["avg_match_score"],
                    "total_items_diff": v2_stats["total_items"] - v1_stats["total_items"],
                    "matched_items_diff": v2_stats["matched_items"] - v1_stats["matched_items"],
                    "purchased_items_diff": v2_stats["purchased_items"] - v1_stats["purchased_items"],
                    "failed_items_diff": v2_stats["failed_items"] - v1_stats["failed_items"]
                }
            }

            return comparison_result, ""

        except Exception as e:
            self.logger.error(f"对比规则效果失败：{str(e)}")
            return {}, f"对比规则效果失败：{str(e)}"

    def get_rule_effect_trend(self, rule_set_code: str, days: int = 30) -> Tuple[List[Dict], str]:
        """
        获取规则效果趋势
        
        Args:
            rule_set_code: 规则集编码
            days: 统计天数
        
        Returns:
            (trend_list, error_msg): 趋势列表和错误消息
        """
        conn = self.db.get_connection()
        cursor = conn.cursor()

        try:
            trend_list = []
            end_date = datetime.now()

            for i in range(days):
                date = (end_date - timedelta(days=i)).strftime("%Y-%m-%d")
                next_date = (end_date - timedelta(days=i-1)).strftime("%Y-%m-%d")

                # 统计当天数据（使用final_pass和selected代替purchase_status）
                cursor.execute('''
                    SELECT COUNT(*) as total_items,
                           SUM(CASE WHEN total_score >= 60 THEN 1 ELSE 0 END) as matched_items,
                           SUM(CASE WHEN final_pass = 1 AND selected = 1 THEN 1 ELSE 0 END) as purchased_items,
                           AVG(total_score) as avg_match_score
                    FROM smart_purchase_candidates
                    WHERE rule_set_code = ?
                      AND created_at >= ?
                      AND created_at < ?
                ''', (rule_set_code, date, next_date))

                row = cursor.fetchone()
                if row:
                    total_items = row["total_items"] or 0
                    matched_items = row["matched_items"] or 0
                    purchased_items = row["purchased_items"] or 0
                    avg_match_score = row["avg_match_score"] or 0

                    match_success_rate = matched_items / total_items if total_items > 0 else 0
                    purchase_success_rate = purchased_items / matched_items if matched_items > 0 else 0

                    trend_list.append({
                        "date": date,
                        "total_items": total_items,
                        "matched_items": matched_items,
                        "purchased_items": purchased_items,
                        "match_success_rate": match_success_rate,
                        "purchase_success_rate": purchase_success_rate,
                        "avg_match_score": avg_match_score
                    })

            return trend_list, ""

        except Exception as e:
            self.logger.error(f"获取规则效果趋势失败：{str(e)}")
            return [], f"获取规则效果趋势失败：{str(e)}"

    def save_rule_effect_stats(self, rule_set_code: str, stat_date: str) -> Tuple[bool, str]:
        """
        保存规则效果统计
        
        Args:
            rule_set_code: 规则集编码
            stat_date: 统计日期（YYYY-MM-DD）
        
        Returns:
            (success, error_msg): 是否成功和错误消息
        """
        conn = self.db.get_connection()
        cursor = conn.cursor()

        try:
            # 获取统计数据
            stats_data, error = self.get_rule_effect_stats(rule_set_code, stat_date, stat_date)
            if error:
                return False, error

            # 生成统计ID
            stat_id = str(uuid.uuid4())
            now = datetime.now().isoformat()

            # 保存统计数据
            cursor.execute('''
                INSERT INTO smart_rule_effect_stats (
                    stat_id, rule_set_code, stat_date,
                    total_batches, total_items, matched_items, purchased_items, failed_items,
                    match_success_rate, purchase_success_rate, avg_match_score,
                    failure_reason_distribution, score_distribution,
                    created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                stat_id, rule_set_code, stat_date,
                0, stats_data["total_items"], stats_data["matched_items"],
                stats_data["purchased_items"], stats_data["failed_items"],
                stats_data["match_success_rate"], stats_data["purchase_success_rate"],
                stats_data["avg_match_score"],
                json.dumps(stats_data["failure_reason_distribution"]),
                json.dumps(stats_data["score_distribution"]),
                now, now
            ))

            conn.commit()
            self.logger.info(f"保存规则效果统计成功：{rule_set_code} {stat_date}")
            return True, ""

        except Exception as e:
            conn.rollback()
            self.logger.error(f"保存规则效果统计失败：{str(e)}")
            return False, f"保存规则效果统计失败：{str(e)}"

    def get_top_failure_reasons(self, rule_set_code: str, days: int = 7, top_n: int = 5) -> Tuple[List[Dict], str]:
        """
        获取Top N失败原因
        
        Args:
            rule_set_code: 规则集编码
            days: 统计天数
            top_n: Top N
        
        Returns:
            (top_reasons, error_msg): Top N失败原因列表和错误消息
        """
        conn = self.db.get_connection()
        cursor = conn.cursor()

        try:
            end_date = datetime.now().strftime("%Y-%m-%d")
            start_date = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
            date_start = f"{start_date}T00:00:00"
            end_dt = datetime.now() + timedelta(days=1)
            date_end = end_dt.strftime("%Y-%m-%d") + "T00:00:00"

            # 二期整改：优先使用failure_code聚合
            try:
                cursor.execute('''
                    SELECT failure_code, failure_stage, COUNT(*) as count
                    FROM smart_purchase_failure_reasons
                    WHERE rule_set_code = ?
                      AND created_at >= ?
                      AND created_at < ?
                    GROUP BY failure_code, failure_stage
                    ORDER BY count DESC
                    LIMIT ?
                ''', (rule_set_code, date_start, date_end, top_n))

                top_reasons = []
                for row in cursor.fetchall():
                    code = row["failure_code"] or "UNKNOWN"
                    stage = row["failure_stage"] or ""
                    count = row["count"] or 0
                    top_reasons.append({
                        "failure_code": code,
                        "failure_stage": stage,
                        "count": count
                    })

                if top_reasons:
                    return top_reasons, ""
            except Exception:
                pass

            # 降级：使用reject_reason
            cursor.execute('''
                SELECT reject_reason, COUNT(*) as count
                FROM smart_purchase_candidates
                WHERE rule_set_code = ?
                  AND final_pass = 0
                  AND created_at >= ?
                  AND created_at < ?
                GROUP BY reject_reason
                ORDER BY count DESC
                LIMIT ?
            ''', (rule_set_code, date_start, date_end, top_n))

            top_reasons = []
            for row in cursor.fetchall():
                reason = row["reject_reason"] or "未知原因"
                count = row["count"] or 0
                top_reasons.append({
                    "failure_code": reason,
                    "failure_stage": "",
                    "count": count
                })

            return top_reasons, ""

        except Exception as e:
            self.logger.error(f"获取Top N失败原因失败：{str(e)}")
            return [], f"获取Top N失败原因失败：{str(e)}"