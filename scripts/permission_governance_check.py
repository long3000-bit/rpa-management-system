"""
权限治理与发布前一致性检查脚本
第六阶段：权限治理与发布前一致性检查

功能：
1. 权限编码一致性清单
2. 权限常量残留扫描
3. 数据库权限落库检查
4. 数据权限历史归属检查
5. 操作日志质量检查
"""

import os
import re
import sqlite3
import sys
import io
from pathlib import Path
from datetime import datetime

# 设置标准输出编码为 UTF-8（兼容 Windows GBK 控制台）
if sys.stdout.encoding != 'utf-8':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

# 项目根目录
PROJECT_ROOT = Path(__file__).parent.parent
DB_PATH = PROJECT_ROOT / "data" / "app.db"

# 如果 app.db 不存在，尝试 rpa.db
if not DB_PATH.exists():
    DB_PATH = PROJECT_ROOT / "data" / "rpa.db"


class PermissionGovernanceChecker:
    """权限治理检查器"""
    
    def __init__(self):
        self.results = {
            "permission_codes": [],
            "permission_residuals": [],
            "database_permissions": [],
            "data_permissions": [],
            "operation_logs": [],
        }
        self.errors = []
        self.warnings = []
        
    def run_all_checks(self):
        """运行所有检查"""
        print("=" * 60)
        print("权限治理与发布前一致性检查")
        print("=" * 60)
        print(f"检查时间: {datetime.now().isoformat()}")
        print()
        
        # 1. 权限编码一致性清单
        self.check_permission_codes_consistency()
        
        # 2. 权限常量残留扫描
        self.scan_permission_residuals()
        
        # 3. 数据库权限落库检查
        self.check_database_permissions()
        
        # 4. 数据权限历史归属检查
        self.check_data_permission_ownership()
        
        # 5. 操作日志质量检查
        self.check_operation_log_quality()
        
        # 输出结果
        self.print_summary()
        
        return len(self.errors) == 0
    
    def check_permission_codes_consistency(self):
        """检查权限编码一致性"""
        print("\n[1] 权限编码一致性清单")
        print("-" * 40)
        
        # 从 PermissionCodes 类提取权限编码
        permission_checker_path = PROJECT_ROOT / "app" / "core" / "permission_checker.py"
        if not permission_checker_path.exists():
            self.errors.append("permission_checker.py 文件不存在")
            return
        
        with open(permission_checker_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # 提取权限常量
        pattern = r'(\w+)\s*=\s*["\']([^"\']+)["\']'
        matches = re.findall(pattern, content)
        
        permission_codes = {}
        for name, code in matches:
            if code.startswith('menu.') or code.startswith('operation.') or code.startswith('data.'):
                permission_codes[name] = code
        
        print(f"PermissionCodes 中定义的权限数量: {len(permission_codes)}")
        
        # 分类统计
        menu_perms = {k: v for k, v in permission_codes.items() if v.startswith('menu.')}
        operation_perms = {k: v for k, v in permission_codes.items() if v.startswith('operation.')}
        data_perms = {k: v for k, v in permission_codes.items() if v.startswith('data.')}
        
        print(f"  - 菜单权限 (menu.*): {len(menu_perms)}")
        print(f"  - 操作权限 (operation.*): {len(operation_perms)}")
        print(f"  - 数据权限 (data.*): {len(data_perms)}")
        
        # 输出清单
        print("\n权限编码清单:")
        print("| 常量名 | 权限编码 | 类型 |")
        print("|--------|----------|------|")
        for name, code in sorted(permission_codes.items(), key=lambda x: x[1]):
            perm_type = "菜单" if code.startswith('menu.') else "操作" if code.startswith('operation.') else "数据"
            print(f"| {name} | {code} | {perm_type} |")
        
        self.results["permission_codes"] = permission_codes
        
    def scan_permission_residuals(self):
        """扫描权限常量残留"""
        print("\n[2] 权限常量残留扫描")
        print("-" * 40)
        
        # 已知的旧常量名（需要替换的）
        old_constants = [
            'USER_CREATE',
            'USER_EDIT',
            'USER_DISABLE',
            'USER_RESET_PASSWORD',
            'USER_UNLOCK',
            'ROLE_PERMISSION_UPDATE',
            'CONFIG_SAVE',
            'LOG_EXPORT',
            'LOG_DELETE',
        ]
        
        # 扫描 UI 页面文件
        ui_pages_dir = PROJECT_ROOT / "app" / "ui" / "pages"
        if not ui_pages_dir.exists():
            self.errors.append("UI 页面目录不存在")
            return
        
        residuals = []
        
        for py_file in ui_pages_dir.glob("*.py"):
            with open(py_file, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # 检查旧常量引用
            for old_const in old_constants:
                pattern = f'PermissionCodes\\.{old_const}'
                if re.search(pattern, content):
                    residuals.append({
                        "file": py_file.name,
                        "constant": old_const,
                        "type": "旧常量残留"
                    })
                    self.errors.append(f"{py_file.name}: 发现旧常量 PermissionCodes.{old_const}")
            
            # 检查手写权限编码字符串
            handwritten_patterns = [
                r'["\']menu\.[^"\']+["\']',
                r'["\']operation\.[^"\']+["\']',
                r'["\']data\.[^"\']+["\']',
            ]
            for pattern in handwritten_patterns:
                matches = re.findall(pattern, content)
                for match in matches:
                    # 排除数据库初始化中的字符串
                    if 'database.py' not in str(py_file):
                        residuals.append({
                            "file": py_file.name,
                            "constant": match,
                            "type": "手写权限编码"
                        })
                        self.warnings.append(f"{py_file.name}: 发现手写权限编码 {match}")
        
        print(f"扫描文件数: {len(list(ui_pages_dir.glob('*.py')))}")
        print(f"发现残留数: {len(residuals)}")
        
        if residuals:
            print("\n残留详情:")
            print("| 文件 | 常量/编码 | 类型 |")
            print("|------|-----------|------|")
            for r in residuals:
                print(f"| {r['file']} | {r['constant']} | {r['type']} |")
        else:
            print("✅ 未发现权限常量残留")
        
        self.results["permission_residuals"] = residuals
        
    def check_database_permissions(self):
        """检查数据库权限落库"""
        print("\n[3] 数据库权限落库检查")
        print("-" * 40)
        
        if not DB_PATH.exists():
            self.errors.append(f"数据库文件不存在: {DB_PATH}")
            return
        
        conn = sqlite3.connect(str(DB_PATH))
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        # 检查 permissions 表
        cursor.execute("SELECT COUNT(*) as count FROM permissions")
        perm_count = cursor.fetchone()['count']
        print(f"permissions 表权限点数量: {perm_count}")
        
        # 检查 role_permissions 表
        cursor.execute("SELECT COUNT(*) as count FROM role_permissions")
        role_perm_count = cursor.fetchone()['count']
        print(f"role_permissions 表授权数量: {role_perm_count}")
        
        # 检查 system_admin 是否拥有全部权限
        cursor.execute("""
            SELECT r.role_code, COUNT(rp.permission_code) as perm_count
            FROM roles r
            LEFT JOIN role_permissions rp ON r.role_code = rp.role_code
            GROUP BY r.role_code
        """)
        role_perms = cursor.fetchall()
        
        print("\n角色授权统计:")
        print("| 角色 | 权限数量 |")
        print("|------|----------|")
        for row in role_perms:
            print(f"| {row['role_code']} | {row['perm_count']} |")
        
        # 检查高风险权限是否误授给店长
        high_risk_perms = [
            'operation.user.unlock',
            'operation.db.import_restore',
            'operation.config.save_database',
            'operation.config.save_yys_api',
            'operation.log.export',
            'operation.log.delete',
            'operation.role.assign_permissions',
        ]
        
        cursor.execute("""
            SELECT rp.role_code, rp.permission_code
            FROM role_permissions rp
            WHERE rp.role_code = 'store_manager'
            AND rp.permission_code IN (?, ?, ?, ?, ?, ?, ?)
        """, high_risk_perms)
        
        risky_grants = cursor.fetchall()
        
        if risky_grants:
            print("\n⚠️ 高风险权限误授警告:")
            print("| 角色 | 权限编码 |")
            print("|------|----------|")
            for row in risky_grants:
                print(f"| {row['role_code']} | {row['permission_code']} |")
                self.errors.append(f"高风险权限 {row['permission_code']} 误授给 store_manager")
        else:
            print("✅ 高风险权限未误授给店长")
        
        # 检查权限点是否全部落库
        cursor.execute("SELECT permission_code FROM permissions")
        db_perms = set(row['permission_code'] for row in cursor.fetchall())
        
        # 从 PermissionCodes 获取的权限编码
        code_perms = set(self.results["permission_codes"].values())
        
        missing_in_db = code_perms - db_perms
        if missing_in_db:
            print("\n⚠️ 权限点未落库:")
            for perm in missing_in_db:
                print(f"  - {perm}")
                self.errors.append(f"权限点 {perm} 未在数据库中落库")
        else:
            print("✅ 所有权限点已落库")
        
        conn.close()
        
        self.results["database_permissions"] = {
            "perm_count": perm_count,
            "role_perm_count": role_perm_count,
            "role_perms": [dict(row) for row in role_perms],
            "risky_grants": [dict(row) for row in risky_grants],
            "missing_in_db": list(missing_in_db),
        }
        
    def check_data_permission_ownership(self):
        """检查数据权限历史归属"""
        print("\n[4] 数据权限历史归属检查")
        print("-" * 40)
        
        if not DB_PATH.exists():
            return
        
        conn = sqlite3.connect(str(DB_PATH))
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        # 需要检查的表和字段
        tables_to_check = [
            ("reconciliation_tasks", "created_by"),
            ("stock_compare_result", "created_by"),
            ("yys_import_batch", "imported_by"),
            ("smart_purchase_batches", "created_by"),
            ("rpa_import_batches", "imported_by"),
            ("rpa_tasks", "created_by"),
            ("yys_sync_task", "created_by"),
        ]
        
        print("历史归属检查结果:")
        print("| 表名 | 字段 | 总数 | 空值数 | 空值比例 |")
        print("|------|------|------|--------|----------|")
        
        empty_tables = []
        
        for table, field in tables_to_check:
            try:
                cursor.execute(f"SELECT COUNT(*) as total FROM {table}")
                total = cursor.fetchone()['total']
                
                cursor.execute(f"SELECT COUNT(*) as empty FROM {table} WHERE {field} IS NULL OR {field} = ''")
                empty = cursor.fetchone()['empty']
                
                ratio = f"{empty}/{total}" if total > 0 else "0/0"
                percent = f"{(empty/total*100):.1f}%" if total > 0 else "0%"
                
                print(f"| {table} | {field} | {total} | {empty} | {percent} |")
                
                if empty > 0 and total > 0:
                    empty_tables.append({
                        "table": table,
                        "field": field,
                        "total": total,
                        "empty": empty,
                    })
                    if empty == total:
                        self.errors.append(f"{table}.{field} 全部为空 ({empty}/{total})")
                    else:
                        self.warnings.append(f"{table}.{field} 存在空值 ({empty}/{total})")
                        
            except sqlite3.OperationalError as e:
                print(f"| {table} | {field} | 表不存在 | - | - |")
                self.warnings.append(f"表 {table} 不存在或字段 {field} 不存在")
        
        if empty_tables:
            print("\n⚠️ 存在空归属的表:")
            for t in empty_tables:
                print(f"  - {t['table']}.{t['field']}: {t['empty']}/{t['total']} 空值")
        else:
            print("✅ 所有数据权限表归属字段已填充")
        
        conn.close()
        
        self.results["data_permissions"] = empty_tables
        
    def check_operation_log_quality(self):
        """检查操作日志质量"""
        print("\n[5] 操作日志质量检查")
        print("-" * 40)
        
        if not DB_PATH.exists():
            return
        
        conn = sqlite3.connect(str(DB_PATH))
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        # 检查最近100条日志
        cursor.execute("""
            SELECT id, username, operation_type, permission_code, result, 
                   target_type, target_id, detail, created_at
            FROM operation_logs
            ORDER BY created_at DESC
            LIMIT 100
        """)
        
        logs = cursor.fetchall()
        
        if not logs:
            print("操作日志表为空")
            conn.close()
            return
        
        print(f"最近100条日志检查:")
        
        # 检查字段质量
        missing_permission_code = 0
        missing_result = 0
        denied_logs = 0
        
        for log in logs:
            if not log['permission_code']:
                missing_permission_code += 1
            if not log['result']:
                missing_result += 1
            if log['result'] == 'denied':
                denied_logs += 1
        
        print(f"  - 缺少 permission_code: {missing_permission_code}")
        print(f"  - 缺少 result: {missing_result}")
        print(f"  - 权限拒绝日志数: {denied_logs}")
        
        if missing_permission_code > 0:
            self.warnings.append(f"最近100条日志中有 {missing_permission_code} 条缺少 permission_code")
        if missing_result > 0:
            self.warnings.append(f"最近100条日志中有 {missing_result} 条缺少 result")
        
        # 检查是否有敏感信息
        cursor.execute("""
            SELECT id, detail FROM operation_logs
            WHERE detail LIKE '%appsecret%' OR detail LIKE '%password%' OR detail LIKE '%secret%'
            LIMIT 10
        """)
        
        sensitive_logs = cursor.fetchall()
        if sensitive_logs:
            print("\n⚠️ 发现可能包含敏感信息的日志:")
            for log in sensitive_logs:
                print(f"  - id: {log['id']}")
                self.warnings.append(f"日志 {log['id']} 可能包含敏感信息")
        else:
            print("✅ 未发现敏感信息泄露")
        
        conn.close()
        
        self.results["operation_logs"] = {
            "total_checked": len(logs),
            "missing_permission_code": missing_permission_code,
            "missing_result": missing_result,
            "denied_logs": denied_logs,
            "sensitive_logs": len(sensitive_logs),
        }
        
    def print_summary(self):
        """输出检查总结"""
        print("\n" + "=" * 60)
        print("检查总结")
        print("=" * 60)
        
        print(f"\n错误数: {len(self.errors)}")
        if self.errors:
            print("错误详情:")
            for err in self.errors:
                print(f"  ❌ {err}")
        
        print(f"\n警告数: {len(self.warnings)}")
        if self.warnings:
            print("警告详情:")
            for warn in self.warnings:
                print(f"  ⚠️ {warn}")
        
        print("\n验收结论:")
        if len(self.errors) == 0:
            print("✅ 通过 - 所有检查项无阻塞错误")
        else:
            print("❌ 未通过 - 存在阻塞错误，需要修复")
        
        print("\n建议:")
        if self.errors:
            print("  1. 修复所有阻塞错误")
            print("  2. 重新运行检查脚本")
            print("  3. 更新 Notion 测试记录")
        else:
            print("  1. 检查警告项是否需要处理")
            print("  2. 更新 Notion 状态为已完成")


def main():
    """主函数"""
    checker = PermissionGovernanceChecker()
    success = checker.run_all_checks()
    
    # 返回退出码
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()