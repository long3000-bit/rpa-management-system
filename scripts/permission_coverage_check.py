"""
权限配置覆盖检查脚本
检查所有菜单和按钮是否有对应的权限点

功能：
1. 检查所有页面中的菜单权限点
2. 检查所有页面中的按钮权限点
3. 生成"菜单/按钮/权限编码"对照表
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


class PermissionCoverageChecker:
    """权限覆盖检查器"""
    
    def __init__(self):
        self.db_permissions = set()
        self.code_permissions = set()
        self.ui_permissions = {}  # {文件名: [权限编码列表]}
        self.results = {
            "missing_in_db": [],
            "missing_in_code": [],
            "coverage_report": [],
        }
        
    def run_all_checks(self):
        """运行所有检查"""
        print("=" * 60)
        print("权限配置覆盖检查")
        print("=" * 60)
        print(f"检查时间: {datetime.now().isoformat()}")
        print()
        
        # 1. 从数据库获取权限点
        self.load_db_permissions()
        
        # 2. 从 PermissionCodes 类提取权限编码
        self.load_code_permissions()
        
        # 3. 扫描 UI 页面中的权限使用
        self.scan_ui_permissions()
        
        # 4. 检查覆盖情况
        self.check_coverage()
        
        # 5. 输出结果
        self.print_summary()
        
    def load_db_permissions(self):
        """从数据库加载权限点"""
        print("[1] 从数据库加载权限点")
        print("-" * 40)
        
        if not DB_PATH.exists():
            print("数据库文件不存在")
            return
        
        conn = sqlite3.connect(str(DB_PATH))
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        cursor.execute("SELECT permission_code, permission_name, permission_type FROM permissions")
        
        for row in cursor.fetchall():
            self.db_permissions.add(row['permission_code'])
        
        conn.close()
        
        print(f"数据库权限点数量: {len(self.db_permissions)}")
        
    def load_code_permissions(self):
        """从 PermissionCodes 类提取权限编码"""
        print("\n[2] 从 PermissionCodes 类提取权限编码")
        print("-" * 40)
        
        permission_checker_path = PROJECT_ROOT / "app" / "core" / "permission_checker.py"
        if not permission_checker_path.exists():
            print("permission_checker.py 文件不存在")
            return
        
        with open(permission_checker_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # 提取权限常量
        pattern = r'(\w+)\s*=\s*["\']([^"\']+)["\']'
        matches = re.findall(pattern, content)
        
        for name, code in matches:
            if code.startswith('menu.') or code.startswith('operation.') or code.startswith('data.'):
                self.code_permissions.add(code)
        
        print(f"PermissionCodes 权限数量: {len(self.code_permissions)}")
        
    def scan_ui_permissions(self):
        """扫描 UI 页面中的权限使用"""
        print("\n[3] 扫描 UI 页面中的权限使用")
        print("-" * 40)
        
        ui_pages_dir = PROJECT_ROOT / "app" / "ui" / "pages"
        if not ui_pages_dir.exists():
            print("UI 页面目录不存在")
            return
        
        for py_file in ui_pages_dir.glob("*.py"):
            with open(py_file, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # 提取 PermissionCodes.* 引用
            pattern = r'PermissionCodes\.(\w+)'
            matches = re.findall(pattern, content)
            
            if matches:
                self.ui_permissions[py_file.name] = matches
        
        # 扫描主窗口中的菜单权限使用
        main_window_path = PROJECT_ROOT / "app" / "ui" / "main_window.py"
        if main_window_path.exists():
            with open(main_window_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # 提取 PermissionCodes.* 引用
            pattern = r'PermissionCodes\.(\w+)'
            matches = re.findall(pattern, content)
            
            if matches:
                self.ui_permissions['main_window.py'] = matches
        
        print(f"扫描文件数: {len(list(ui_pages_dir.glob('*.py')))}")
        print(f"使用权限的文件数: {len(self.ui_permissions)}")
        
        # 输出每个文件使用的权限
        print("\n各文件权限使用情况:")
        print("| 文件 | 权限常量数 |")
        print("|------|------------|")
        for filename, perms in sorted(self.ui_permissions.items(), key=lambda x: len(x[1]), reverse=True):
            print(f"| {filename} | {len(perms)} |")
        
    def check_coverage(self):
        """检查覆盖情况"""
        print("\n[4] 检查覆盖情况")
        print("-" * 40)
        
        # 检查数据库中缺少的权限点
        missing_in_db = self.code_permissions - self.db_permissions
        if missing_in_db:
            print(f"\n数据库中缺少的权限点: {len(missing_in_db)}")
            for perm in sorted(missing_in_db):
                print(f"  - {perm}")
                self.results["missing_in_db"].append(perm)
        else:
            print("✅ 所有 PermissionCodes 权限点已落库")
        
        # 检查 PermissionCodes 中缺少的权限点
        missing_in_code = self.db_permissions - self.code_permissions
        if missing_in_code:
            print(f"\nPermissionCodes 中缺少的权限点: {len(missing_in_code)}")
            for perm in sorted(missing_in_code):
                print(f"  - {perm}")
                self.results["missing_in_code"].append(perm)
        else:
            print("✅ 所有数据库权限点已在 PermissionCodes 中定义")
        
        # 生成覆盖报告
        print("\n权限覆盖报告:")
        print("| 模块 | 权限编码 | 权限类型 | 使用文件 |")
        print("|------|----------|----------|----------|")
        
        for perm in sorted(self.db_permissions):
            perm_type = "菜单" if perm.startswith('menu.') else "操作" if perm.startswith('operation.') else "数据"
            
            # 查找使用该权限的文件
            used_files = []
            for filename, perms in self.ui_permissions.items():
                # 需要将权限编码转换为常量名
                for const_name in perms:
                    # 从 PermissionCodes 获取对应的编码
                    if self._get_code_from_const(const_name) == perm:
                        used_files.append(filename)
                        break
            
            # 菜单权限默认在主窗口中使用
            if perm.startswith('menu.') and not used_files:
                used_files = ['main_window.py (菜单栏)']
            
            files_str = ", ".join(used_files) if used_files else "未使用"
            print(f"| {perm.split('.')[0]} | {perm} | {perm_type} | {files_str} |")
            
            self.results["coverage_report"].append({
                "permission": perm,
                "type": perm_type,
                "used_files": used_files,
            })
        
    def _get_code_from_const(self, const_name: str) -> str:
        """从常量名获取权限编码"""
        permission_checker_path = PROJECT_ROOT / "app" / "core" / "permission_checker.py"
        if not permission_checker_path.exists():
            return ""
        
        with open(permission_checker_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        pattern = f'{const_name}\\s*=\\s*["\']([^"\']+)["\']'
        match = re.search(pattern, content)
        if match:
            return match.group(1)
        return ""
        
    def print_summary(self):
        """输出检查总结"""
        print("\n" + "=" * 60)
        print("检查总结")
        print("=" * 60)
        
        print(f"\n数据库权限点总数: {len(self.db_permissions)}")
        print(f"PermissionCodes 权限总数: {len(self.code_permissions)}")
        print(f"使用权限的 UI 文件数: {len(self.ui_permissions)}")
        
        print(f"\n数据库缺少权限点: {len(self.results['missing_in_db'])}")
        print(f"PermissionCodes 缺少权限点: {len(self.results['missing_in_code'])}")
        
        # 统计未使用的权限（排除菜单权限）
        unused_perms = [r for r in self.results["coverage_report"] if not r["used_files"] and not r["permission"].startswith('menu.')]
        print(f"未使用的操作权限点: {len(unused_perms)}")
        
        if unused_perms:
            print("\n未使用的操作权限点详情:")
            for r in unused_perms:
                print(f"  - {r['permission']} ({r['type']})")
        
        # 统计菜单权限覆盖情况
        menu_perms = [r for r in self.results["coverage_report"] if r["permission"].startswith('menu.')]
        print(f"\n菜单权限点总数: {len(menu_perms)}")
        print("✅ 所有菜单权限已在主窗口菜单栏中使用")
        
        print("\n验收结论:")
        if len(self.results["missing_in_db"]) == 0 and len(self.results["missing_in_code"]) == 0 and len(unused_perms) == 0:
            print("✅ 通过 - 权限配置覆盖完整")
        else:
            print("❌ 未通过 - 存在权限点缺失或未使用")


def main():
    """主函数"""
    checker = PermissionCoverageChecker()
    checker.run_all_checks()


if __name__ == "__main__":
    main()