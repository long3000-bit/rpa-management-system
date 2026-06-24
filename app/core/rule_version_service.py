"""
规则版本管理服务 - 三期阶段4.3
管理规则集的版本历史和回滚：
1. 保存历史版本
2. 查看版本历史
3. 回滚到指定版本
4. 版本对比
"""
import json
import logging
from datetime import datetime
from typing import Dict, List, Tuple

from app.storage.database import Database


class RuleVersionService:
    """规则版本管理服务"""

    def __init__(self, db: Database):
        self.db = db

    def _ensure_version_table(self):
        """确保版本历史表存在"""
        conn = self.db.get_connection()
        cursor = conn.cursor()
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS smart_match_rule_set_versions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                rule_set_code TEXT NOT NULL,
                version_number TEXT NOT NULL,
                version_name TEXT,
                configs_json TEXT NOT NULL,
                change_reason TEXT,
                change_type TEXT DEFAULT 'update',
                created_by TEXT,
                created_at TEXT NOT NULL,
                is_active INTEGER DEFAULT 0,
                UNIQUE(rule_set_code, version_number)
            )
        ''')
        conn.commit()

    def create_new_version(self, rule_set_code: str, new_version_number: str,
                           configs: List[Dict], change_reason: str = "",
                           created_by: str = "") -> Tuple[bool, str]:
        """
        创建新版本规则集（保存到历史版本表）。

        Args:
            rule_set_code: 规则集代码
            new_version_number: 新版本号（如 v2.0.0）
            configs: 配置项列表
            change_reason: 变更原因
            created_by: 创建人

        Returns:
            (success, message)
        """
        try:
            self._ensure_version_table()
            conn = self.db.get_connection()
            cursor = conn.cursor()

            # 检查原规则集是否存在
            cursor.execute(
                "SELECT rule_set_code, version_number FROM smart_match_rule_sets "
                "WHERE rule_set_code = ?",
                (rule_set_code,)
            )
            original = cursor.fetchone()
            if not original:
                return False, f"规则集 {rule_set_code} 不存在"

            # 检查新版本号是否已存在
            cursor.execute(
                "SELECT id FROM smart_match_rule_set_versions "
                "WHERE rule_set_code = ? AND version_number = ?",
                (rule_set_code, new_version_number)
            )
            if cursor.fetchone():
                return False, f"版本 {new_version_number} 已存在"

            now = datetime.now().isoformat()
            configs_json = json.dumps(configs, ensure_ascii=False)

            # 保存到历史版本表
            cursor.execute('''
                INSERT INTO smart_match_rule_set_versions (
                    rule_set_code, version_number, version_name, configs_json,
                    change_reason, change_type, created_by, created_at, is_active
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0)
            ''', (rule_set_code, new_version_number, f"{rule_set_code} {new_version_number}",
                  configs_json, change_reason, "update", created_by, now))

            # 更新当前规则集的版本号和配置
            cursor.execute("PRAGMA table_info(smart_match_rule_sets)")
            columns = {row["name"] for row in cursor.fetchall()}

            if "version_number" in columns:
                cursor.execute('''
                    UPDATE smart_match_rule_sets
                    SET version_number = ?, updated_at = ?
                    WHERE rule_set_code = ?
                ''', (new_version_number, now, rule_set_code))

            # 更新配置项
            for config in configs:
                cursor.execute(
                    "UPDATE smart_match_rule_configs "
                    "SET rule_value = ?, updated_at = ? "
                    "WHERE rule_set_code = ? AND rule_key = ?",
                    (config.get("rule_value", ""), now, rule_set_code, config.get("rule_key", ""))
                )

            conn.commit()
            logging.info(f"创建新版本: {rule_set_code} {new_version_number} by {created_by}")
            return True, f"新版本 {new_version_number} 已创建"

        except Exception as e:
            logging.error(f"创建新版本失败: {e}")
            return False, f"创建失败: {e}"

    def get_version_history(self, rule_set_code: str) -> List[Dict]:
        """
        获取规则集的版本历史。

        Returns:
            [
                {
                    "rule_set_code": str,
                    "version_number": str,
                    "version_status": str,
                    "change_reason": str,
                    "change_type": str,
                    "created_at": str,
                    "updated_at": str,
                }
            ]
        """
        try:
            self._ensure_version_table()
            conn = self.db.get_connection()
            cursor = conn.cursor()

            result = []

            # 1. 获取当前活跃版本
            cursor.execute("PRAGMA table_info(smart_match_rule_sets)")
            columns = {row["name"] for row in cursor.fetchall()}

            if "version_number" in columns:
                cursor.execute('''
                    SELECT rule_set_code, rule_set_name, version_number, version_status,
                           change_reason, change_type, created_at, updated_at, is_enabled
                    FROM smart_match_rule_sets
                    WHERE rule_set_code = ?
                ''', (rule_set_code,))
            else:
                cursor.execute('''
                    SELECT rule_set_code, rule_set_name, created_at, updated_at, is_enabled
                    FROM smart_match_rule_sets
                    WHERE rule_set_code = ?
                ''', (rule_set_code,))

            row = cursor.fetchone()
            if row:
                try:
                    version_number = row["version_number"]
                except (KeyError, IndexError):
                    version_number = "v1.0.0"
                try:
                    version_status = row["version_status"]
                except (KeyError, IndexError):
                    version_status = "legacy"
                try:
                    change_reason = row["change_reason"]
                except (KeyError, IndexError):
                    change_reason = ""
                try:
                    change_type = row["change_type"]
                except (KeyError, IndexError):
                    change_type = "new"

                result.append({
                    "rule_set_code": row["rule_set_code"],
                    "rule_set_name": row["rule_set_name"],
                    "version_number": version_number,
                    "version_status": version_status,
                    "change_reason": change_reason,
                    "change_type": change_type,
                    "created_at": row["created_at"],
                    "updated_at": row["updated_at"],
                    "is_enabled": bool(row["is_enabled"]),
                    "is_current": True,
                })

            # 2. 获取历史版本
            cursor.execute('''
                SELECT rule_set_code, version_number, version_name, configs_json,
                       change_reason, change_type, created_by, created_at, is_active
                FROM smart_match_rule_set_versions
                WHERE rule_set_code = ?
                ORDER BY created_at DESC
            ''', (rule_set_code,))

            for row in cursor.fetchall():
                result.append({
                    "rule_set_code": row["rule_set_code"],
                    "rule_set_name": row["version_name"],
                    "version_number": row["version_number"],
                    "version_status": "archived",
                    "change_reason": row["change_reason"] or "",
                    "change_type": row["change_type"] or "update",
                    "created_at": row["created_at"],
                    "updated_at": row["created_at"],
                    "is_enabled": bool(row["is_active"]),
                    "is_current": False,
                })

            return result

        except Exception as e:
            logging.error(f"获取版本历史失败: {e}")
            return []

    def get_version_configs(self, rule_set_code: str, version_number: str = None) -> Dict:
        """
        获取指定版本的配置。

        Args:
            rule_set_code: 规则集代码
            version_number: 版本号（可选，默认取当前版本）

        Returns:
            {
                "rule_set_code": str,
                "version_number": str,
                "configs": {rule_key: {"value": str, "type": str}},
            }
        """
        try:
            self._ensure_version_table()
            conn = self.db.get_connection()
            cursor = conn.cursor()

            # 如果指定版本号，先检查历史版本表
            if version_number:
                cursor.execute(
                    "SELECT configs_json FROM smart_match_rule_set_versions "
                    "WHERE rule_set_code = ? AND version_number = ?",
                    (rule_set_code, version_number)
                )
                row = cursor.fetchone()
                if row:
                    configs_list = json.loads(row["configs_json"])
                    configs = {}
                    for config in configs_list:
                        configs[config["rule_key"]] = {
                            "value": config.get("rule_value", ""),
                            "type": config.get("rule_type", "number"),
                        }
                    return {
                        "rule_set_code": rule_set_code,
                        "version_number": version_number,
                        "configs": configs,
                    }

            # 获取当前版本的配置
            cursor.execute(
                "SELECT rule_set_code, version_number FROM smart_match_rule_sets "
                "WHERE rule_set_code = ?",
                (rule_set_code,)
            )
            row = cursor.fetchone()
            if not row:
                return {"rule_set_code": rule_set_code, "version_number": "unknown", "configs": {}}

            # 获取配置项
            cursor.execute(
                "SELECT rule_key, rule_value, rule_type FROM smart_match_rule_configs "
                "WHERE rule_set_code = ? AND is_enabled = 1",
                (rule_set_code,)
            )

            configs = {}
            for config_row in cursor.fetchall():
                configs[config_row["rule_key"]] = {
                    "value": config_row["rule_value"],
                    "type": config_row["rule_type"],
                }

            return {
                "rule_set_code": rule_set_code,
                "version_number": row["version_number"] or "v1.0.0",
                "configs": configs,
            }

        except Exception as e:
            logging.error(f"获取版本配置失败: {e}")
            return {"rule_set_code": rule_set_code, "version_number": "error", "configs": {}}

    def rollback_to_version(self, rule_set_code: str, target_version: str,
                            rolled_back_by: str = "") -> Tuple[bool, str]:
        """
        回滚到指定版本（从历史版本表恢复配置）。

        Args:
            rule_set_code: 规则集代码
            target_version: 目标版本号
            rolled_back_by: 操作人

        Returns:
            (success, message)
        """
        try:
            self._ensure_version_table()
            conn = self.db.get_connection()
            cursor = conn.cursor()

            # 检查目标版本是否存在
            cursor.execute(
                "SELECT configs_json FROM smart_match_rule_set_versions "
                "WHERE rule_set_code = ? AND version_number = ?",
                (rule_set_code, target_version)
            )
            target = cursor.fetchone()
            if not target:
                return False, f"目标版本 {target_version} 不存在"

            # 检查当前版本
            cursor.execute(
                "SELECT rule_set_code, version_number FROM smart_match_rule_sets "
                "WHERE rule_set_code = ?",
                (rule_set_code,)
            )
            current = cursor.fetchone()
            if not current:
                return False, f"规则集 {rule_set_code} 不存在"

            if current["version_number"] == target_version:
                return False, "当前已是目标版本，无需回滚"

            # 解析目标版本配置
            configs_list = json.loads(target["configs_json"])
            now = datetime.now().isoformat()

            # 更新当前规则集的配置
            for config in configs_list:
                cursor.execute(
                    "UPDATE smart_match_rule_configs "
                    "SET rule_value = ?, updated_at = ? "
                    "WHERE rule_set_code = ? AND rule_key = ?",
                    (config.get("rule_value", ""), now, rule_set_code, config.get("rule_key", ""))
                )

            # 更新版本号
            cursor.execute("PRAGMA table_info(smart_match_rule_sets)")
            columns = {row["name"] for row in cursor.fetchall()}

            if "version_number" in columns:
                cursor.execute('''
                    UPDATE smart_match_rule_sets
                    SET version_number = ?, updated_at = ?
                    WHERE rule_set_code = ?
                ''', (target_version, now, rule_set_code))

            conn.commit()
            logging.info(f"回滚版本: {rule_set_code} to {target_version} by {rolled_back_by}")
            return True, f"已回滚到版本 {target_version}"

        except Exception as e:
            logging.error(f"回滚版本失败: {e}")
            return False, f"回滚失败: {e}"

    def compare_versions(self, rule_set_code: str, version1: str, version2: str) -> Dict:
        """
        对比两个版本的配置差异。

        Returns:
            {
                "version1": str,
                "version2": str,
                "differences": [
                    {
                        "rule_key": str,
                        "version1_value": str,
                        "version2_value": str,
                        "change_type": "added" | "removed" | "modified",
                    }
                ],
            }
        """
        try:
            configs1 = self.get_version_configs(rule_set_code, version1)
            configs2 = self.get_version_configs(rule_set_code, version2)

            differences = []

            # 检查所有配置项
            all_keys = set(configs1["configs"].keys()) | set(configs2["configs"].keys())

            for key in all_keys:
                v1_val = configs1["configs"].get(key, {}).get("value", None)
                v2_val = configs2["configs"].get(key, {}).get("value", None)

                if v1_val is None and v2_val is not None:
                    differences.append({
                        "rule_key": key,
                        "version1_value": None,
                        "version2_value": v2_val,
                        "change_type": "added",
                    })
                elif v1_val is not None and v2_val is None:
                    differences.append({
                        "rule_key": key,
                        "version1_value": v1_val,
                        "version2_value": None,
                        "change_type": "removed",
                    })
                elif v1_val != v2_val:
                    differences.append({
                        "rule_key": key,
                        "version1_value": v1_val,
                        "version2_value": v2_val,
                        "change_type": "modified",
                    })

            return {
                "version1": version1,
                "version2": version2,
                "differences": differences,
            }

        except Exception as e:
            logging.error(f"对比版本失败: {e}")
            return {"version1": version1, "version2": version2, "differences": [], "error": str(e)}

    def get_active_version(self, rule_set_code: str) -> Dict:
        """
        获取当前活跃版本信息。

        Returns:
            {
                "rule_set_code": str,
                "version_number": str,
                "version_status": str,
                "is_enabled": bool,
            }
        """
        try:
            conn = self.db.get_connection()
            cursor = conn.cursor()

            cursor.execute("PRAGMA table_info(smart_match_rule_sets)")
            columns = {row["name"] for row in cursor.fetchall()}

            if "version_number" in columns:
                cursor.execute('''
                    SELECT rule_set_code, version_number, version_status, is_enabled
                    FROM smart_match_rule_sets
                    WHERE rule_set_code = ? AND is_enabled = 1
                    ORDER BY created_at DESC
                    LIMIT 1
                ''', (rule_set_code,))
            else:
                cursor.execute('''
                    SELECT rule_set_code, is_enabled
                    FROM smart_match_rule_sets
                    WHERE rule_set_code = ? AND is_enabled = 1
                    LIMIT 1
                ''', (rule_set_code,))

            row = cursor.fetchone()
            if not row:
                return {"rule_set_code": rule_set_code, "version_number": "none", "is_enabled": False}

            try:
                version_number = row["version_number"]
            except (KeyError, IndexError):
                version_number = "v1.0.0"
            try:
                version_status = row["version_status"]
            except (KeyError, IndexError):
                version_status = "legacy"

            return {
                "rule_set_code": row["rule_set_code"],
                "version_number": version_number,
                "version_status": version_status,
                "is_enabled": bool(row["is_enabled"]),
            }

        except Exception as e:
            logging.error(f"获取活跃版本失败: {e}")
            return {"rule_set_code": rule_set_code, "version_number": "error", "is_enabled": False}