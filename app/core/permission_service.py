import json
import logging
from datetime import datetime
from typing import Dict, List, Optional, Set

from app.storage.database import Database


class PermissionService:
    """权限服务类"""
    
    def __init__(self, db: Database):
        self.db = db
        # 用户权限缓存
        self._permission_cache: Dict[str, Set[str]] = {}
    
    def get_user_role(self, username: str) -> Optional[str]:
        """获取用户角色编码"""
        try:
            conn = self.db.get_connection()
            cursor = conn.cursor()
            
            cursor.execute('''
                SELECT role_code FROM users WHERE username = ?
            ''', (username,))
            
            row = cursor.fetchone()
            if row:
                return row['role_code']
            
            return None
            
        except Exception as e:
            logging.error(f"获取用户角色失败: {e}")
            return None
    
    def get_user_permissions(self, username: str) -> Set[str]:
        """获取用户全部权限编码（支持多角色）"""
        # 检查缓存
        if username in self._permission_cache:
            return self._permission_cache[username]
        
        try:
            conn = self.db.get_connection()
            cursor = conn.cursor()
            
            # 获取用户的所有角色（从 user_roles 表）
            cursor.execute('''
                SELECT ur.role_code FROM user_roles ur
                JOIN roles r ON ur.role_code = r.role_code
                WHERE ur.username = ? AND r.status = 'active'
            ''', (username,))
            
            role_codes = [row['role_code'] for row in cursor.fetchall()]
            
            # 如果 user_roles 表没有数据，尝试从 users 表获取单角色（兼容旧数据）
            if not role_codes:
                cursor.execute('''
                    SELECT role_code FROM users WHERE username = ?
                ''', (username,))
                
                row = cursor.fetchone()
                if row and row['role_code']:
                    role_codes = [row['role_code']]
            
            permissions = set()
            
            # 获取所有角色的权限（合集）
            for role_code in role_codes:
                cursor.execute('''
                    SELECT permission_code FROM role_permissions WHERE role_code = ?
                ''', (role_code,))
                
                for row in cursor.fetchall():
                    permissions.add(row['permission_code'])
            
            # 缓存权限
            self._permission_cache[username] = permissions
            
            return permissions
            
        except Exception as e:
            logging.error(f"获取用户权限失败: {e}")
            return set()
    
    def has_permission(self, username: str, permission_code: str) -> bool:
        """判断单个权限"""
        permissions = self.get_user_permissions(username)
        return permission_code in permissions
    
    def has_any_permission(self, username: str, permission_codes: List[str]) -> bool:
        """判断任一权限"""
        permissions = self.get_user_permissions(username)
        return any(code in permissions for code in permission_codes)
    
    def has_all_permissions(self, username: str, permission_codes: List[str]) -> bool:
        """判断全部权限"""
        permissions = self.get_user_permissions(username)
        return all(code in permissions for code in permission_codes)
    
    def get_accessible_menus(self, username: str) -> List[str]:
        """返回可见菜单列表"""
        permissions = self.get_user_permissions(username)
        
        # 过滤出菜单权限
        menus = [p for p in permissions if p.startswith('menu.')]
        
        return sorted(menus)
    
    def require_permission(self, username: str, permission_code: str) -> tuple:
        """
        检查权限，无权限返回失败信息
        返回: (success: bool, message: str)
        """
        if not self.has_permission(username, permission_code):
            # 记录无权限操作日志
            self.log_operation(
                username=username,
                operation_type='permission_denied',
                operation_desc=f'尝试执行无权限操作: {permission_code}',
                target_type='permission',
                target_id=permission_code
            )
            return False, f"无权限执行此操作: {permission_code}"
        
        return True, "权限验证通过"
    
    def clear_cache(self, username: str = None):
        """清除权限缓存"""
        if username:
            if username in self._permission_cache:
                del self._permission_cache[username]
        else:
            self._permission_cache.clear()
    
    def log_operation(
        self,
        username: str,
        operation_type: str,
        operation_desc: str = None,
        target_type: str = None,
        target_id: str = None,
        detail: dict = None,
        permission_code: str = None,
        result: str = None
    ):
        """记录操作日志"""
        try:
            conn = self.db.get_connection()
            cursor = conn.cursor()
            
            now = datetime.now().isoformat()
            
            cursor.execute('''
                INSERT INTO operation_logs 
                (username, operation_type, operation_desc, target_type, target_id, detail, created_at, permission_code, result)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                username,
                operation_type,
                operation_desc,
                target_type,
                target_id,
                json.dumps(detail or {}, ensure_ascii=False),
                now,
                permission_code,
                result
            ))
            
            conn.commit()
            
        except Exception as e:
            logging.error(f"记录操作日志失败: {e}")
    
    def get_all_roles(self) -> List[Dict]:
        """获取所有角色列表"""
        try:
            conn = self.db.get_connection()
            cursor = conn.cursor()
            
            cursor.execute('''
                SELECT role_code, role_name, description, is_system_role, status, created_at, updated_at
                FROM roles
                ORDER BY id
            ''')
            
            rows = cursor.fetchall()
            return [dict(row) for row in rows]
            
        except Exception as e:
            logging.error(f"获取角色列表失败: {e}")
            return []
    
    def get_role_permissions(self, role_code: str) -> List[str]:
        """获取角色的权限列表"""
        try:
            conn = self.db.get_connection()
            cursor = conn.cursor()
            
            cursor.execute('''
                SELECT permission_code FROM role_permissions WHERE role_code = ?
            ''', (role_code,))
            
            return [row['permission_code'] for row in cursor.fetchall()]
            
        except Exception as e:
            logging.error(f"获取角色权限失败: {e}")
            return []
    
    def update_role_permissions(self, role_code: str, permission_codes: List[str]) -> bool:
        """更新角色权限"""
        try:
            conn = self.db.get_connection()
            cursor = conn.cursor()
            
            now = datetime.now().isoformat()
            
            # 删除旧权限
            cursor.execute('DELETE FROM role_permissions WHERE role_code = ?', (role_code,))
            
            # 添加新权限
            for permission_code in permission_codes:
                cursor.execute('''
                    INSERT INTO role_permissions (role_code, permission_code, created_at)
                    VALUES (?, ?, ?)
                ''', (role_code, permission_code, now))
            
            conn.commit()
            
            # 清除所有用户的权限缓存
            self.clear_cache()
            
            logging.info(f"已更新角色 {role_code} 的权限")
            return True
            
        except Exception as e:
            logging.error(f"更新角色权限失败: {e}")
            return False
    
    def create_role(self, role_code: str, role_name: str, description: str = None) -> bool:
        """创建新角色"""
        try:
            conn = self.db.get_connection()
            cursor = conn.cursor()
            
            now = datetime.now().isoformat()
            
            # 检查角色编码是否已存在
            cursor.execute('SELECT role_code FROM roles WHERE role_code = ?', (role_code,))
            if cursor.fetchone():
                logging.warning(f"角色编码 {role_code} 已存在")
                return False
            
            cursor.execute('''
                INSERT INTO roles (role_code, role_name, description, is_system_role, status, created_at, updated_at)
                VALUES (?, ?, ?, 0, 'active', ?, ?)
            ''', (role_code, role_name, description, now, now))
            
            conn.commit()
            
            logging.info(f"已创建角色 {role_code}")
            return True
            
        except Exception as e:
            logging.error(f"创建角色失败: {e}")
            return False
    
    def update_role(self, role_code: str, role_name: str, description: str = None, status: str = None) -> bool:
        """更新角色信息"""
        try:
            conn = self.db.get_connection()
            cursor = conn.cursor()
            
            now = datetime.now().isoformat()
            
            # 检查是否是系统内置角色
            cursor.execute('SELECT is_system_role FROM roles WHERE role_code = ?', (role_code,))
            row = cursor.fetchone()
            if row and row['is_system_role'] == 1:
                logging.warning(f"系统内置角色 {role_code} 不允许修改")
                return False
            
            # 构建更新语句
            update_fields = []
            params = []
            
            if role_name:
                update_fields.append('role_name = ?')
                params.append(role_name)
            
            if description:
                update_fields.append('description = ?')
                params.append(description)
            
            if status:
                update_fields.append('status = ?')
                params.append(status)
            
            update_fields.append('updated_at = ?')
            params.append(now)
            
            params.append(role_code)
            
            cursor.execute(f'''
                UPDATE roles SET {', '.join(update_fields)} WHERE role_code = ?
            ''', params)
            
            conn.commit()
            
            logging.info(f"已更新角色 {role_code}")
            return True
            
        except Exception as e:
            logging.error(f"更新角色失败: {e}")
            return False
    
    def disable_role(self, role_code: str) -> bool:
        """停用角色"""
        try:
            conn = self.db.get_connection()
            cursor = conn.cursor()
            
            # 检查是否是系统内置角色
            cursor.execute('SELECT is_system_role FROM roles WHERE role_code = ?', (role_code,))
            row = cursor.fetchone()
            if row and row['is_system_role'] == 1:
                logging.warning(f"系统内置角色 {role_code} 不允许停用")
                return False
            
            # 检查是否是最后一个系统管理员角色
            cursor.execute('''
                SELECT COUNT(*) as count FROM roles WHERE role_code = 'system_admin' AND status = 'active'
            ''')
            admin_count = cursor.fetchone()['count']
            
            if role_code == 'system_admin' and admin_count <= 1:
                logging.warning("不允许停用最后一个系统管理员角色")
                return False
            
            now = datetime.now().isoformat()
            
            cursor.execute('''
                UPDATE roles SET status = 'disabled', updated_at = ? WHERE role_code = ?
            ''', (now, role_code))
            
            conn.commit()
            
            # 清除所有用户的权限缓存
            self.clear_cache()
            
            logging.info(f"已停用角色 {role_code}")
            return True
            
        except Exception as e:
            logging.error(f"停用角色失败: {e}")
            return False
    
    def enable_role(self, role_code: str) -> bool:
        """启用角色"""
        try:
            conn = self.db.get_connection()
            cursor = conn.cursor()
            
            now = datetime.now().isoformat()
            
            cursor.execute('''
                UPDATE roles SET status = 'active', updated_at = ? WHERE role_code = ?
            ''', (now, role_code))
            
            conn.commit()
            
            # 清除所有用户的权限缓存
            self.clear_cache()
            
            logging.info(f"已启用角色 {role_code}")
            return True
            
        except Exception as e:
            logging.error(f"启用角色失败: {e}")
            return False
    
    def delete_role(self, role_code: str) -> bool:
        """删除角色（仅非系统角色）"""
        try:
            conn = self.db.get_connection()
            cursor = conn.cursor()
            
            # 检查是否是系统内置角色
            cursor.execute('SELECT is_system_role FROM roles WHERE role_code = ?', (role_code,))
            row = cursor.fetchone()
            if row and row['is_system_role'] == 1:
                logging.warning(f"系统内置角色 {role_code} 不允许删除")
                return False
            
            # 检查是否有用户关联该角色（users 表）
            cursor.execute('SELECT COUNT(*) as count FROM users WHERE role_code = ?', (role_code,))
            user_count = cursor.fetchone()['count']
            
            # 检查是否有用户关联该角色（user_roles 表）
            cursor.execute('SELECT COUNT(*) as count FROM user_roles WHERE role_code = ?', (role_code,))
            user_roles_count = cursor.fetchone()['count']
            
            total_user_count = user_count + user_roles_count
            if total_user_count > 0:
                logging.warning(f"角色 {role_code} 还有 {total_user_count} 个用户关联，不允许删除")
                return False
            
            # 删除角色权限
            cursor.execute('DELETE FROM role_permissions WHERE role_code = ?', (role_code,))
            
            # 删除用户角色关联（如果有残留数据）
            cursor.execute('DELETE FROM user_roles WHERE role_code = ?', (role_code,))
            
            # 删除角色
            cursor.execute('DELETE FROM roles WHERE role_code = ?', (role_code,))
            
            conn.commit()
            
            logging.info(f"已删除角色 {role_code}")
            return True
            
        except Exception as e:
            logging.error(f"删除角色失败: {e}")
            return False
    
    def get_user_roles(self, username: str) -> List[Dict]:
        """获取用户的所有角色"""
        try:
            conn = self.db.get_connection()
            cursor = conn.cursor()
            
            cursor.execute('''
                SELECT r.role_code, r.role_name, r.description, r.is_system_role, r.status, ur.created_at
                FROM user_roles ur
                JOIN roles r ON ur.role_code = r.role_code
                WHERE ur.username = ?
                ORDER BY r.is_system_role DESC, r.role_name
            ''', (username,))
            
            rows = cursor.fetchall()
            
            # 如果 user_roles 表没有数据，尝试从 users 表获取单角色（兼容旧数据）
            if not rows:
                cursor.execute('''
                    SELECT u.role_code, r.role_name, r.description, r.is_system_role, r.status
                    FROM users u
                    JOIN roles r ON u.role_code = r.role_code
                    WHERE u.username = ?
                ''', (username,))
                
                rows = cursor.fetchall()
            
            return [dict(row) for row in rows]
            
        except Exception as e:
            logging.error(f"获取用户角色失败: {e}")
            return []
    
    def assign_user_roles(self, username: str, role_codes: List[str]) -> bool:
        """分配用户角色"""
        try:
            conn = self.db.get_connection()
            cursor = conn.cursor()
            
            now = datetime.now().isoformat()
            
            # 获取当前角色
            cursor.execute('SELECT role_code FROM user_roles WHERE username = ?', (username,))
            current_roles = set(row['role_code'] for row in cursor.fetchall())
            
            # 计算新增和移除的角色
            new_roles = set(role_codes)
            added_roles = new_roles - current_roles
            removed_roles = current_roles - new_roles
            
            # 添加新角色
            for role_code in added_roles:
                cursor.execute('''
                    INSERT INTO user_roles (username, role_code, created_at)
                    VALUES (?, ?, ?)
                ''', (username, role_code, now))
            
            # 移除旧角色
            for role_code in removed_roles:
                cursor.execute('''
                    DELETE FROM user_roles WHERE username = ? AND role_code = ?
                ''', (username, role_code))
            
            # 更新 users 表的 role_code 字段（兼容旧逻辑）
            if role_codes:
                cursor.execute('''
                    UPDATE users SET role_code = ? WHERE username = ?
                ''', (role_codes[0], username))
            
            conn.commit()
            
            # 清除用户权限缓存
            self.clear_cache()
            
            logging.info(f"已分配用户 {username} 的角色: {role_codes}")
            return True
            
        except Exception as e:
            logging.error(f"分配用户角色失败: {e}")
            return False
    
    def add_user_role(self, username: str, role_code: str) -> bool:
        """添加用户单个角色"""
        try:
            conn = self.db.get_connection()
            cursor = conn.cursor()
            
            # 检查角色是否存在且启用
            cursor.execute('SELECT status FROM roles WHERE role_code = ?', (role_code,))
            row = cursor.fetchone()
            if not row or row['status'] != 'active':
                logging.warning(f"角色 {role_code} 不存在或已停用")
                return False
            
            now = datetime.now().isoformat()
            
            cursor.execute('''
                INSERT OR IGNORE INTO user_roles (username, role_code, created_at)
                VALUES (?, ?, ?)
            ''', (username, role_code, now))
            
            conn.commit()
            
            # 清除用户权限缓存
            self.clear_cache()
            
            logging.info(f"已为用户 {username} 添加角色 {role_code}")
            return True
            
        except Exception as e:
            logging.error(f"添加用户角色失败: {e}")
            return False
    
    def remove_user_role(self, username: str, role_code: str) -> bool:
        """移除用户单个角色"""
        try:
            conn = self.db.get_connection()
            cursor = conn.cursor()
            
            # 检查是否是最后一个系统管理员角色
            cursor.execute('''
                SELECT COUNT(*) as count FROM user_roles ur
                JOIN roles r ON ur.role_code = r.role_code
                WHERE ur.role_code = 'system_admin' AND r.status = 'active'
            ''', ())
            admin_count = cursor.fetchone()['count']
            
            if role_code == 'system_admin' and admin_count <= 1:
                logging.warning("不允许移除最后一个系统管理员角色")
                return False
            
            cursor.execute('''
                DELETE FROM user_roles WHERE username = ? AND role_code = ?
            ''', (username, role_code))
            
            conn.commit()
            
            # 清除用户权限缓存
            self.clear_cache()
            
            logging.info(f"已为用户 {username} 移除角色 {role_code}")
            return True
            
        except Exception as e:
            logging.error(f"移除用户角色失败: {e}")
            return False
    
    def get_all_permissions(self) -> List[Dict]:
        """获取所有权限列表"""
        try:
            conn = self.db.get_connection()
            cursor = conn.cursor()
            
            cursor.execute('''
                SELECT permission_code, permission_name, permission_type, parent_code, description, sort_order
                FROM permissions
                ORDER BY sort_order
            ''')
            
            rows = cursor.fetchall()
            return [dict(row) for row in rows]
            
        except Exception as e:
            logging.error(f"获取权限列表失败: {e}")
            return []
    
    def get_permission_tree(self) -> List[Dict]:
        """获取权限树结构"""
        permissions = self.get_all_permissions()
        
        # 构建树结构
        tree = []
        menu_perms = [p for p in permissions if p['permission_type'] == 'menu']
        
        for menu in menu_perms:
            menu_node = {
                'code': menu['permission_code'],
                'name': menu['permission_name'],
                'type': 'menu',
                'children': []
            }
            
            # 添加该菜单下的操作权限
            operations = [p for p in permissions if p['parent_code'] == menu['permission_code']]
            for op in operations:
                menu_node['children'].append({
                    'code': op['permission_code'],
                    'name': op['permission_name'],
                    'type': 'operation'
                })
            
            tree.append(menu_node)
        
        return tree
    
    def get_operation_logs(
        self,
        username: str = None,
        operation_type: str = None,
        start_time: str = None,
        end_time: str = None,
        limit: int = 100,
        offset: int = 0
    ) -> List[Dict]:
        """查询操作日志
        
        Args:
            username: 用户名筛选
            operation_type: 操作类型筛选
            start_time: 开始时间筛选
            end_time: 结束时间筛选
            limit: 返回数量限制
            offset: 偏移量
        
        Returns:
            操作日志列表
        """
        try:
            conn = self.db.get_connection()
            cursor = conn.cursor()
            
            # 构建查询条件
            conditions = []
            params = []
            
            if username:
                conditions.append('username = ?')
                params.append(username)
            
            if operation_type:
                conditions.append('operation_type = ?')
                params.append(operation_type)
            
            if start_time:
                conditions.append('created_at >= ?')
                params.append(start_time)
            
            if end_time:
                conditions.append('created_at <= ?')
                params.append(end_time)
            
            where_clause = ' AND '.join(conditions) if conditions else '1=1'
            
            # 查询日志
            query = f'''
                SELECT id, username, operation_type, operation_desc, target_type, target_id, 
                       detail, ip_address, machine_name, created_at, permission_code, result
                FROM operation_logs
                WHERE {where_clause}
                ORDER BY created_at DESC
                LIMIT ? OFFSET ?
            '''
            
            params.extend([limit, offset])
            
            cursor.execute(query, params)
            
            rows = cursor.fetchall()
            logs = []
            
            for row in rows:
                log = dict(row)
                # 解析detail字段
                if log['detail']:
                    try:
                        log['detail'] = json.loads(log['detail'])
                    except:
                        log['detail'] = {}
                else:
                    log['detail'] = {}
                logs.append(log)
            
            return logs
            
        except Exception as e:
            logging.error(f"查询操作日志失败: {e}")
            return []
    
    def get_operation_log_count(
        self,
        username: str = None,
        operation_type: str = None,
        start_time: str = None,
        end_time: str = None
    ) -> int:
        """查询操作日志数量
        
        Args:
            username: 用户名筛选
            operation_type: 操作类型筛选
            start_time: 开始时间筛选
            end_time: 结束时间筛选
        
        Returns:
            日志数量
        """
        try:
            conn = self.db.get_connection()
            cursor = conn.cursor()
            
            # 构建查询条件
            conditions = []
            params = []
            
            if username:
                conditions.append('username = ?')
                params.append(username)
            
            if operation_type:
                conditions.append('operation_type = ?')
                params.append(operation_type)
            
            if start_time:
                conditions.append('created_at >= ?')
                params.append(start_time)
            
            if end_time:
                conditions.append('created_at <= ?')
                params.append(end_time)
            
            where_clause = ' AND '.join(conditions) if conditions else '1=1'
            
            query = f'SELECT COUNT(*) as count FROM operation_logs WHERE {where_clause}'
            
            cursor.execute(query, params)
            
            row = cursor.fetchone()
            return row['count'] if row else 0
            
        except Exception as e:
            logging.error(f"查询操作日志数量失败: {e}")
            return 0
    
    def delete_operation_logs(
        self,
        username: str = None,
        operation_type: str = None,
        start_time: str = None,
        end_time: str = None
    ) -> int:
        """删除操作日志
        
        Args:
            username: 用户名筛选
            operation_type: 操作类型筛选
            start_time: 开始时间筛选
            end_time: 结束时间筛选
        
        Returns:
            删除的日志数量
        """
        try:
            conn = self.db.get_connection()
            cursor = conn.cursor()
            
            # 构建删除条件
            conditions = []
            params = []
            
            if username:
                conditions.append('username = ?')
                params.append(username)
            
            if operation_type:
                conditions.append('operation_type = ?')
                params.append(operation_type)
            
            if start_time:
                conditions.append('created_at >= ?')
                params.append(start_time)
            
            if end_time:
                conditions.append('created_at <= ?')
                params.append(end_time)
            
            where_clause = ' AND '.join(conditions) if conditions else '1=1'
            
            # 先查询要删除的数量
            count_query = f'SELECT COUNT(*) as count FROM operation_logs WHERE {where_clause}'
            cursor.execute(count_query, params)
            count = cursor.fetchone()['count']
            
            # 删除日志
            delete_query = f'DELETE FROM operation_logs WHERE {where_clause}'
            cursor.execute(delete_query, params)
            
            conn.commit()
            
            logging.info(f"已删除 {count} 条操作日志")
            return count
            
        except Exception as e:
            logging.error(f"删除操作日志失败: {e}")
            return 0
    
    def get_all_users(self) -> List[Dict]:
        """获取所有用户列表"""
        try:
            conn = self.db.get_connection()
            cursor = conn.cursor()
            
            cursor.execute('''
                SELECT username, display_name, role_code, status, last_login_at, created_at
                FROM users
                ORDER BY created_at DESC
            ''')
            
            rows = cursor.fetchall()
            return [dict(row) for row in rows]
            
        except Exception as e:
            logging.error(f"获取用户列表失败: {e}")
            return []
    
    def get_operation_types(self) -> List[str]:
        """获取所有操作类型列表"""
        try:
            conn = self.db.get_connection()
            cursor = conn.cursor()
            
            cursor.execute('''
                SELECT DISTINCT operation_type FROM operation_logs
                ORDER BY operation_type
            ''')
            
            return [row['operation_type'] for row in cursor.fetchall()]
            
        except Exception as e:
            logging.error(f"获取操作类型列表失败: {e}")
            return []