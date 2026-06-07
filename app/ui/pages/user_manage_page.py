import logging
from datetime import datetime
from typing import Dict, List, Optional

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTableWidget, QTableWidgetItem,
    QPushButton, QDialog, QFormLayout, QLineEdit, QComboBox, QMessageBox,
    QHeaderView, QLabel, QGroupBox, QListWidget, QListWidgetItem
)
from PySide6.QtCore import Qt

from app.storage.database import Database
from app.core.password_service import PasswordService
from app.core.permission_service import PermissionService
from app.core.auth_service import AuthService
from app.core.permission_checker import PermissionChecker, PermissionCodes


class UserManagePage(QWidget):
    """用户管理页面"""
    
    def __init__(self, db: Database, current_username: str):
        super().__init__()
        self.db = db
        self.current_username = current_username
        self.password_service = PasswordService()
        self.permission_service = PermissionService(db)
        self.auth_service = AuthService(db)
        self.permission_checker = PermissionChecker(db, current_username)
        
        self.init_ui()
        self.load_users()
    
    def init_ui(self):
        layout = QVBoxLayout(self)
        
        # 操作按钮区域
        btn_group = QGroupBox("操作")
        btn_layout = QHBoxLayout(btn_group)
        
        self.add_btn = QPushButton("新增用户")
        self.add_btn.clicked.connect(self.add_user)
        btn_layout.addWidget(self.add_btn)
        
        self.edit_btn = QPushButton("编辑用户")
        self.edit_btn.clicked.connect(self.edit_user)
        btn_layout.addWidget(self.edit_btn)
        
        self.reset_pwd_btn = QPushButton("重置密码")
        self.reset_pwd_btn.clicked.connect(self.reset_password)
        btn_layout.addWidget(self.reset_pwd_btn)
        
        self.disable_btn = QPushButton("禁用账号")
        self.disable_btn.clicked.connect(self.toggle_user_status)
        btn_layout.addWidget(self.disable_btn)
        
        self.unlock_btn = QPushButton("解锁账号")
        self.unlock_btn.clicked.connect(self.unlock_account)
        btn_layout.addWidget(self.unlock_btn)
        
        self.refresh_btn = QPushButton("刷新")
        self.refresh_btn.clicked.connect(self.load_users)
        btn_layout.addWidget(self.refresh_btn)
        
        btn_layout.addStretch()
        layout.addWidget(btn_group)
        
        # 用户列表
        self.table = QTableWidget()
        self.table.setColumnCount(8)
        self.table.setHorizontalHeaderLabels([
            "用户名", "显示名", "角色", "状态", "锁定状态", "失败次数", "最后登录时间", "创建时间"
        ])
        
        # 设置表头自适应
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.Stretch)
        
        # 设置选择模式
        self.table.setSelectionMode(QTableWidget.SingleSelection)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        
        layout.addWidget(self.table)
    
    def load_users(self):
        """加载用户列表"""
        try:
            conn = self.db.get_connection()
            cursor = conn.cursor()
            
            cursor.execute('''
                SELECT username, display_name, role_code, status, failed_login_count, locked_until, last_login_at, created_at
                FROM users
                ORDER BY created_at DESC
            ''')
            
            rows = cursor.fetchall()
            self.table.setRowCount(len(rows))
            
            for i, row in enumerate(rows):
                self.table.setItem(i, 0, QTableWidgetItem(row['username'] or ""))
                self.table.setItem(i, 1, QTableWidgetItem(row['display_name'] or ""))
                
                # 角色显示名称（多角色）
                user_roles = self.permission_service.get_user_roles(row['username'])
                if user_roles:
                    role_names = [r['role_name'] for r in user_roles]
                    role_display = ", ".join(role_names)
                else:
                    # 兼容旧数据
                    role_code = row['role_code'] or 'system_admin'
                    role_display = self.get_role_name(role_code)
                
                self.table.setItem(i, 2, QTableWidgetItem(role_display))
                
                # 状态显示
                status = row['status'] or 'active'
                status_text = "启用" if status == 'active' else "禁用"
                status_item = QTableWidgetItem(status_text)
                if status == 'disabled':
                    status_item.setForeground(Qt.red)
                self.table.setItem(i, 3, status_item)
                
                # 锁定状态显示
                locked_until = row['locked_until']
                if locked_until:
                    # 检查锁定是否过期
                    try:
                        lock_time = datetime.fromisoformat(locked_until)
                        if datetime.now() < lock_time:
                            remaining_minutes = int((lock_time - datetime.now()).total_seconds() / 60)
                            lock_text = f"已锁定({remaining_minutes}分钟)"
                            lock_item = QTableWidgetItem(lock_text)
                            lock_item.setForeground(Qt.red)
                        else:
                            lock_item = QTableWidgetItem("正常")
                    except:
                        lock_item = QTableWidgetItem("正常")
                else:
                    lock_item = QTableWidgetItem("正常")
                self.table.setItem(i, 4, lock_item)
                
                # 失败登录次数显示
                failed_count = row['failed_login_count'] or 0
                failed_item = QTableWidgetItem(str(failed_count))
                if failed_count >= 5:
                    failed_item.setForeground(Qt.red)
                self.table.setItem(i, 5, failed_item)
                
                self.table.setItem(i, 6, QTableWidgetItem(row['last_login_at'] or ""))
                self.table.setItem(i, 7, QTableWidgetItem(row['created_at'] or ""))
            
        except Exception as e:
            logging.error(f"加载用户列表失败: {e}")
            QMessageBox.warning(self, "错误", f"加载用户列表失败: {e}")
    
    def get_role_name(self, role_code: str) -> str:
        """获取角色显示名称"""
        roles = self.permission_service.get_all_roles()
        for role in roles:
            if role['role_code'] == role_code:
                return role['role_name']
        return role_code
    
    def get_selected_username(self) -> Optional[str]:
        """获取选中的用户名"""
        selected_rows = self.table.selectedItems()
        if not selected_rows:
            return None
        
        row = selected_rows[0].row()
        username_item = self.table.item(row, 0)
        return username_item.text() if username_item else None
    
    def add_user(self):
        """新增用户"""
        # 权限检查
        if not self.permission_checker.check_permission(PermissionCodes.OP_USER_CREATE, self):
            return
        
        dialog = UserDialog(self.db, self.permission_service, None)
        if dialog.exec() == QDialog.Accepted:
            user_data = dialog.get_user_data()
            
            # 验证至少选择一个角色
            if not user_data['role_codes']:
                QMessageBox.warning(self, "提示", "请至少选择一个角色")
                return
            
            try:
                # 生成密码哈希
                password_hash, salt, iterations = self.password_service.hash_password(user_data['password'])
                
                conn = self.db.get_connection()
                cursor = conn.cursor()
                
                now = datetime.now().isoformat()
                
                # 插入用户（role_code 使用第一个角色作为主角色）
                primary_role = user_data['role_codes'][0] if user_data['role_codes'] else None
                
                cursor.execute('''
                    INSERT INTO users 
                    (username, password_hash, salt, hash_iterations, display_name, role_code, status, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (
                    user_data['username'],
                    password_hash,
                    salt,
                    iterations,
                    user_data['display_name'],
                    primary_role,
                    'active',
                    now,
                    now
                ))
                
                # 分配用户角色（多角色）
                self.permission_service.assign_user_roles(user_data['username'], user_data['role_codes'])
                
                conn.commit()
                
                # 记录详细操作日志
                self.permission_service.log_operation(
                    username=self.current_username,
                    operation_type='user_create',
                    operation_desc=f'创建用户: {user_data["username"]} ({user_data["display_name"]})',
                    target_type='user',
                    target_id=user_data['username'],
                    detail={
                        'display_name': user_data['display_name'],
                        'role_codes': user_data['role_codes'],
                        'initial_password_set': True
                    },
                    permission_code=PermissionCodes.OP_USER_CREATE,
                    result='success'
                )
                
                QMessageBox.information(self, "成功", "用户创建成功")
                self.load_users()
                
            except Exception as e:
                logging.error(f"创建用户失败: {e}")
                # 记录失败日志
                self.permission_service.log_operation(
                    username=self.current_username,
                    operation_type='user_create',
                    operation_desc=f'创建用户失败: {user_data["username"]}',
                    target_type='user',
                    target_id=user_data['username'],
                    detail={'error': str(e)},
                    permission_code=PermissionCodes.OP_USER_CREATE,
                    result='fail'
                )
                QMessageBox.warning(self, "错误", f"创建用户失败: {e}")
    
    def edit_user(self):
        """编辑用户"""
        # 权限检查
        if not self.permission_checker.check_permission(PermissionCodes.OP_USER_UPDATE, self):
            return
        
        username = self.get_selected_username()
        if not username:
            QMessageBox.warning(self, "提示", "请先选择要编辑的用户")
            return
        
        # 获取用户信息
        try:
            conn = self.db.get_connection()
            cursor = conn.cursor()
            
            cursor.execute('''
                SELECT username, display_name, role_code, status
                FROM users WHERE username = ?
            ''', (username,))
            
            row = cursor.fetchone()
            if not row:
                QMessageBox.warning(self, "错误", "用户不存在")
                return
            
            user_info = dict(row)
            
            # 获取用户当前角色列表
            user_roles = self.permission_service.get_user_roles(username)
            old_role_codes = [r['role_code'] for r in user_roles]
            
            old_data = {
                'display_name': user_info['display_name'],
                'role_codes': old_role_codes,
                'status': user_info['status']
            }
            
        except Exception as e:
            logging.error(f"获取用户信息失败: {e}")
            QMessageBox.warning(self, "错误", f"获取用户信息失败: {e}")
            return
        
        dialog = UserDialog(self.db, self.permission_service, user_info)
        if dialog.exec() == QDialog.Accepted:
            user_data = dialog.get_user_data()
            
            # 验证至少选择一个角色
            if not user_data['role_codes']:
                QMessageBox.warning(self, "提示", "请至少选择一个角色")
                return
            
            try:
                conn = self.db.get_connection()
                cursor = conn.cursor()
                
                now = datetime.now().isoformat()
                
                # 更新用户基本信息
                primary_role = user_data['role_codes'][0] if user_data['role_codes'] else None
                
                cursor.execute('''
                    UPDATE users 
                    SET display_name = ?, role_code = ?, status = ?, updated_at = ?
                    WHERE username = ?
                ''', (
                    user_data['display_name'],
                    primary_role,
                    user_data['status'],
                    now,
                    username
                ))
                
                # 分配用户角色（多角色）
                self.permission_service.assign_user_roles(username, user_data['role_codes'])
                
                conn.commit()
                
                # 清除该用户的权限缓存
                self.permission_service.clear_cache(username)
                
                # 记录详细操作日志（包含变更前后对比）
                self.permission_service.log_operation(
                    username=self.current_username,
                    operation_type='user_edit',
                    operation_desc=f'编辑用户: {username}',
                    target_type='user',
                    target_id=username,
                    detail={
                        'old_data': old_data,
                        'new_data': user_data,
                        'changes': {
                            'display_name': old_data['display_name'] != user_data['display_name'],
                            'role_codes': old_role_codes != user_data['role_codes'],
                            'status': old_data['status'] != user_data['status']
                        }
                    },
                    permission_code=PermissionCodes.OP_USER_UPDATE,
                    result='success'
                )
                
                QMessageBox.information(self, "成功", "用户信息更新成功")
                self.load_users()
                
            except Exception as e:
                logging.error(f"更新用户失败: {e}")
                # 记录失败日志
                self.permission_service.log_operation(
                    username=self.current_username,
                    operation_type='user_edit',
                    operation_desc=f'编辑用户失败: {username}',
                    target_type='user',
                    target_id=username,
                    detail={'error': str(e)},
                    permission_code=PermissionCodes.OP_USER_UPDATE,
                    result='fail'
                )
                QMessageBox.warning(self, "错误", f"更新用户失败: {e}")
    
    def reset_password(self):
        """重置密码"""
        # 权限检查
        if not self.permission_checker.check_permission(PermissionCodes.OP_USER_RESET_PASSWORD, self):
            return
        
        username = self.get_selected_username()
        if not username:
            QMessageBox.warning(self, "提示", "请先选择要重置密码的用户")
            return
        
        dialog = ResetPasswordDialog(username)
        if dialog.exec() == QDialog.Accepted:
            new_password = dialog.get_password()
            
            try:
                # 生成密码哈希
                password_hash, salt, iterations = self.password_service.hash_password(new_password)
                
                conn = self.db.get_connection()
                cursor = conn.cursor()
                
                now = datetime.now().isoformat()
                
                cursor.execute('''
                    UPDATE users 
                    SET password_hash = ?, salt = ?, hash_iterations = ?, updated_at = ?, must_change_password = 1
                    WHERE username = ?
                ''', (password_hash, salt, iterations, now, username))
                
                conn.commit()
                
                # 记录详细操作日志
                self.permission_service.log_operation(
                    username=self.current_username,
                    operation_type='user_reset_password',
                    operation_desc=f'重置用户密码: {username}（用户需强制修改）',
                    target_type='user',
                    target_id=username,
                    detail={'must_change_password': True},
                    permission_code=PermissionCodes.OP_USER_RESET_PASSWORD,
                    result='success'
                )
                
                QMessageBox.information(self, "成功", f"用户 {username} 的密码已重置，用户登录后需强制修改密码")
                
            except Exception as e:
                logging.error(f"重置密码失败: {e}")
                # 记录失败日志
                self.permission_service.log_operation(
                    username=self.current_username,
                    operation_type='user_reset_password',
                    operation_desc=f'重置用户密码失败: {username}',
                    target_type='user',
                    target_id=username,
                    detail={'error': str(e)},
                    permission_code=PermissionCodes.OP_USER_RESET_PASSWORD,
                    result='fail'
                )
                QMessageBox.warning(self, "错误", f"重置密码失败: {e}")
    
    def toggle_user_status(self):
        """切换用户状态（启用/禁用）"""
        # 权限检查
        if not self.permission_checker.check_permission(PermissionCodes.OP_USER_DISABLE, self):
            return
        
        username = self.get_selected_username()
        if not username:
            QMessageBox.warning(self, "提示", "请先选择要操作的用户")
            return
        
        if username == self.current_username:
            QMessageBox.warning(self, "提示", "不能禁用自己的账号")
            return
        
        # 获取当前状态
        try:
            conn = self.db.get_connection()
            cursor = conn.cursor()
            
            cursor.execute('SELECT status FROM users WHERE username = ?', (username,))
            row = cursor.fetchone()
            if not row:
                return
            
            current_status = row['status']
            new_status = 'disabled' if current_status == 'active' else 'active'
            
            now = datetime.now().isoformat()
            
            cursor.execute('''
                UPDATE users SET status = ?, updated_at = ? WHERE username = ?
            ''', (new_status, now, username))
            
            conn.commit()
            
            # 记录详细操作日志
            self.permission_service.log_operation(
                username=self.current_username,
                operation_type='user_disable' if new_status == 'disabled' else 'user_enable',
                operation_desc=f'{("禁用" if new_status == "disabled" else "启用")}用户: {username}',
                target_type='user',
                target_id=username,
                detail={
                    'old_status': current_status,
                    'new_status': new_status
                },
                permission_code=PermissionCodes.OP_USER_DISABLE,
                result='success'
            )
            
            QMessageBox.information(self, "成功", f"用户 {username} 已{("禁用" if new_status == "disabled" else "启用")}")
            self.load_users()
            
        except Exception as e:
            logging.error(f"切换用户状态失败: {e}")
            # 记录失败日志
            self.permission_service.log_operation(
                username=self.current_username,
                operation_type='user_disable',
                operation_desc=f'切换用户状态失败: {username}',
                target_type='user',
                target_id=username,
                detail={'error': str(e)},
                permission_code=PermissionCodes.OP_USER_DISABLE,
                result='fail'
            )
            QMessageBox.warning(self, "错误", f"切换用户状态失败: {e}")
    
    def unlock_account(self):
        """解锁账号"""
        # 权限检查
        if not self.permission_checker.check_permission(PermissionCodes.OP_USER_UNLOCK, self):
            return
        
        username = self.get_selected_username()
        if not username:
            QMessageBox.warning(self, "提示", "请先选择要解锁的用户")
            return
        
        # 检查账号是否被锁定
        try:
            conn = self.db.get_connection()
            cursor = conn.cursor()
            
            cursor.execute('''
                SELECT failed_login_count, locked_until 
                FROM users WHERE username = ?
            ''', (username,))
            
            row = cursor.fetchone()
            if not row:
                QMessageBox.warning(self, "错误", "用户不存在")
                return
            
            failed_count = row['failed_login_count'] or 0
            locked_until = row['locked_until']
            
            if failed_count == 0 and not locked_until:
                QMessageBox.information(self, "提示", f"用户 {username} 未被锁定")
                return
            
            # 确认解锁
            reply = QMessageBox.question(
                self, "确认解锁",
                f"确定要解锁用户 {username} 的账号吗？\n"
                f"当前失败登录次数: {failed_count}\n"
                f"锁定状态: {'已锁定' if locked_until else '未锁定'}",
                QMessageBox.Yes | QMessageBox.No
            )
            
            if reply == QMessageBox.Yes:
                # 调用AuthService解锁
                success, msg = self.auth_service.unlock_account_by_admin(username)
                
                if success:
                    # 记录详细操作日志
                    self.permission_service.log_operation(
                        username=self.current_username,
                        operation_type='user_unlock',
                        operation_desc=f'解锁用户账号: {username}',
                        target_type='user',
                        target_id=username,
                        detail={
                            'failed_count_before': failed_count,
                            'locked_until_before': locked_until,
                            'failed_count_after': 0,
                            'locked_until_after': None
                        },
                        permission_code=PermissionCodes.OP_USER_UNLOCK,
                        result='success'
                    )
                    
                    QMessageBox.information(self, "成功", msg)
                    self.load_users()
                else:
                    # 记录失败日志
                    self.permission_service.log_operation(
                        username=self.current_username,
                        operation_type='user_unlock',
                        operation_desc=f'解锁用户账号失败: {username}',
                        target_type='user',
                        target_id=username,
                        detail={'error': msg},
                        permission_code=PermissionCodes.OP_USER_UNLOCK,
                        result='fail'
                    )
                    QMessageBox.warning(self, "错误", msg)
            
        except Exception as e:
            logging.error(f"解锁账号失败: {e}")
            # 记录失败日志
            self.permission_service.log_operation(
                username=self.current_username,
                operation_type='user_unlock',
                operation_desc=f'解锁用户账号失败: {username}',
                target_type='user',
                target_id=username,
                detail={'error': str(e)},
                permission_code=PermissionCodes.OP_USER_UNLOCK,
                result='fail'
            )
            QMessageBox.warning(self, "错误", f"解锁账号失败: {e}")


class UserDialog(QDialog):
    """用户编辑对话框"""
    
    def __init__(self, db: Database, permission_service: PermissionService, user_info: Optional[Dict] = None):
        super().__init__()
        self.db = db
        self.permission_service = permission_service
        self.user_info = user_info  # None表示新增，有值表示编辑
        
        self.setWindowTitle("新增用户" if not user_info else "编辑用户")
        self.setMinimumWidth(400)
        
        self.init_ui()
    
    def init_ui(self):
        layout = QFormLayout(self)
        
        # 用户名
        self.username_edit = QLineEdit()
        if self.user_info:
            self.username_edit.setText(self.user_info['username'])
            self.username_edit.setReadOnly(True)  # 编辑时不能修改用户名
        layout.addRow("用户名:", self.username_edit)
        
        # 显示名
        self.display_name_edit = QLineEdit()
        if self.user_info:
            self.display_name_edit.setText(self.user_info['display_name'] or "")
        layout.addRow("显示名:", self.display_name_edit)
        
        # 密码（新增时需要）
        if not self.user_info:
            self.password_edit = QLineEdit()
            self.password_edit.setEchoMode(QLineEdit.Password)
            layout.addRow("初始密码:", self.password_edit)
        
        # 角色（多选）
        self.role_list = QListWidget()
        self.role_list.setSelectionMode(QListWidget.MultiSelection)
        
        roles = self.permission_service.get_all_roles()
        for role in roles:
            item = QListWidgetItem(f"{role['role_name']} ({role['role_code']})")
            item.setData(Qt.UserRole, role['role_code'])
            self.role_list.addItem(item)
        
        if self.user_info:
            # 设置当前角色（从 user_roles 表获取）
            user_roles = self.permission_service.get_user_roles(self.user_info['username'])
            current_role_codes = [r['role_code'] for r in user_roles]
            
            for i in range(self.role_list.count()):
                item = self.role_list.item(i)
                if item.data(Qt.UserRole) in current_role_codes:
                    item.setSelected(True)
        
        layout.addRow("角色（可多选）:", self.role_list)
        
        # 状态（编辑时需要）
        if self.user_info:
            self.status_combo = QComboBox()
            self.status_combo.addItem("启用", "active")
            self.status_combo.addItem("禁用", "disabled")
            
            if self.user_info['status'] == 'disabled':
                self.status_combo.setCurrentIndex(1)
            
            layout.addRow("状态:", self.status_combo)
        
        # 按钮
        btn_layout = QHBoxLayout()
        
        ok_btn = QPushButton("确定")
        ok_btn.clicked.connect(self.accept)
        btn_layout.addWidget(ok_btn)
        
        cancel_btn = QPushButton("取消")
        cancel_btn.clicked.connect(self.reject)
        btn_layout.addWidget(cancel_btn)
        
        layout.addRow(btn_layout)
    
    def get_user_data(self) -> Dict:
        """获取用户数据"""
        # 获取选中的角色编码列表
        selected_roles = []
        for i in range(self.role_list.count()):
            item = self.role_list.item(i)
            if item.isSelected():
                selected_roles.append(item.data(Qt.UserRole))
        
        data = {
            'username': self.username_edit.text().strip(),
            'display_name': self.display_name_edit.text().strip(),
            'role_codes': selected_roles,  # 多角色列表
        }
        
        if not self.user_info:
            data['password'] = self.password_edit.text()
        else:
            data['status'] = self.status_combo.currentData()
        
        return data
    
    def accept(self):
        """验证并接受"""
        username = self.username_edit.text().strip()
        if not username:
            QMessageBox.warning(self, "提示", "用户名不能为空")
            return
        
        if not self.user_info:
            password = self.password_edit.text()
            if not password:
                QMessageBox.warning(self, "提示", "初始密码不能为空")
                return
            
            if len(password) < 6:
                QMessageBox.warning(self, "提示", "密码长度至少6位")
                return
            
            # 检查用户名是否已存在
            try:
                conn = self.db.get_connection()
                cursor = conn.cursor()
                cursor.execute('SELECT username FROM users WHERE username = ?', (username,))
                if cursor.fetchone():
                    QMessageBox.warning(self, "提示", "用户名已存在")
                    return
            except Exception as e:
                logging.error(f"检查用户名失败: {e}")
                return
        
        super().accept()


class ResetPasswordDialog(QDialog):
    """重置密码对话框"""
    
    def __init__(self, username: str):
        super().__init__()
        self.username = username
        
        self.setWindowTitle(f"重置密码 - {username}")
        self.setMinimumWidth(300)
        
        self.init_ui()
    
    def init_ui(self):
        layout = QFormLayout(self)
        
        layout.addRow(QLabel(f"为用户 {self.username} 设置新密码"))
        
        self.password_edit = QLineEdit()
        self.password_edit.setEchoMode(QLineEdit.Password)
        layout.addRow("新密码:", self.password_edit)
        
        self.confirm_edit = QLineEdit()
        self.confirm_edit.setEchoMode(QLineEdit.Password)
        layout.addRow("确认密码:", self.confirm_edit)
        
        # 按钮
        btn_layout = QHBoxLayout()
        
        ok_btn = QPushButton("确定")
        ok_btn.clicked.connect(self.accept)
        btn_layout.addWidget(ok_btn)
        
        cancel_btn = QPushButton("取消")
        cancel_btn.clicked.connect(self.reject)
        btn_layout.addWidget(cancel_btn)
        
        layout.addRow(btn_layout)
    
    def get_password(self) -> str:
        """获取新密码"""
        return self.password_edit.text()
    
    def accept(self):
        """验证并接受"""
        password = self.password_edit.text()
        confirm = self.confirm_edit.text()
        
        if not password:
            QMessageBox.warning(self, "提示", "密码不能为空")
            return
        
        if len(password) < 6:
            QMessageBox.warning(self, "提示", "密码长度至少6位")
            return
        
        if password != confirm:
            QMessageBox.warning(self, "提示", "两次输入的密码不一致")
            return
        
        super().accept()