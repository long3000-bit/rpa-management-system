import platform
import logging
from datetime import datetime, timedelta
from typing import Optional
from dataclasses import dataclass

from app.storage.database import Database
from app.core.password_service import PasswordService


@dataclass
class LoginResult:
    success: bool
    message: str
    user: Optional[dict] = None
    must_change_password: bool = False


class AuthService:
    
    # 登录失败次数限制
    MAX_FAILED_LOGIN_COUNT = 5
    # 账号锁定时长（分钟）
    LOCK_DURATION_MINUTES = 30
    
    def __init__(self, db: Database):
        self.db = db
    
    def login(self, username: str, password: str) -> LoginResult:
        if not username:
            return LoginResult(False, "用户名不能为空")
        
        if not password:
            return LoginResult(False, "密码不能为空")
        
        user = self.db.get_user_by_username(username)
        
        if not user:
            self._log_login(username, False, "用户名不存在")
            return LoginResult(False, "用户名或密码错误")
        
        # 检查账号是否被锁定
        if self._is_account_locked(user):
            locked_until = user['locked_until']
            remaining_minutes = self._get_remaining_lock_minutes(locked_until)
            return LoginResult(False, f"账号已被锁定，请等待 {remaining_minutes} 分钟后再试")
        
        if user['status'] != 'active':
            self._log_login(username, False, "账号已被禁用")
            return LoginResult(False, "当前账号已被禁用")
        
        if not PasswordService.verify_password(
            password, 
            user['password_hash'], 
            user['salt'],
            user['hash_iterations']
        ):
            # 登录失败，增加失败次数
            self._increment_failed_login_count(username)
            failed_count = user['failed_login_count'] + 1
            
            # 检查是否需要锁定账号
            if failed_count >= self.MAX_FAILED_LOGIN_COUNT:
                self._lock_account(username)
                self._log_login(username, False, "密码错误，账号已被锁定")
                return LoginResult(False, f"密码错误次数过多，账号已被锁定 {self.LOCK_DURATION_MINUTES} 分钟")
            
            remaining_attempts = self.MAX_FAILED_LOGIN_COUNT - failed_count
            self._log_login(username, False, f"密码错误（剩余尝试次数：{remaining_attempts}）")
            return LoginResult(False, f"用户名或密码错误（剩余尝试次数：{remaining_attempts}）")
        
        # 登录成功，清零失败次数
        self._clear_failed_login_count(username)
        
        self.db.update_last_login(username)
        self._log_login(username, True, "登录成功")
        
        logging.info(f"用户 {username} 登录成功")
        
        # 检查是否需要强制修改密码
        must_change_password = user.get('must_change_password', 0) == 1
        
        return LoginResult(True, "登录成功", user, must_change_password)
    
    def _is_account_locked(self, user: dict) -> bool:
        """检查账号是否被锁定"""
        locked_until = user.get('locked_until')
        if not locked_until:
            return False
        
        # 检查锁定时间是否已过期
        try:
            lock_time = datetime.fromisoformat(locked_until)
            if datetime.now() > lock_time:
                # 锁定已过期，解锁账号
                self._unlock_account(user['username'])
                return False
            return True
        except:
            return False
    
    def _get_remaining_lock_minutes(self, locked_until: str) -> int:
        """获取剩余锁定分钟数"""
        try:
            lock_time = datetime.fromisoformat(locked_until)
            remaining = lock_time - datetime.now()
            return max(0, int(remaining.total_seconds() / 60))
        except:
            return self.LOCK_DURATION_MINUTES
    
    def _increment_failed_login_count(self, username: str):
        """增加登录失败次数"""
        try:
            conn = self.db.get_connection()
            cursor = conn.cursor()
            
            cursor.execute('''
                UPDATE users 
                SET failed_login_count = failed_login_count + 1, updated_at = ?
                WHERE username = ?
            ''', (datetime.now().isoformat(), username))
            
            conn.commit()
        except Exception as e:
            logging.error(f"增加登录失败次数失败: {e}")
    
    def _clear_failed_login_count(self, username: str):
        """清零登录失败次数"""
        try:
            conn = self.db.get_connection()
            cursor = conn.cursor()
            
            cursor.execute('''
                UPDATE users 
                SET failed_login_count = 0, locked_until = NULL, updated_at = ?
                WHERE username = ?
            ''', (datetime.now().isoformat(), username))
            
            conn.commit()
        except Exception as e:
            logging.error(f"清零登录失败次数失败: {e}")
    
    def _lock_account(self, username: str):
        """锁定账号"""
        try:
            conn = self.db.get_connection()
            cursor = conn.cursor()
            
            locked_until = datetime.now() + timedelta(minutes=self.LOCK_DURATION_MINUTES)
            
            cursor.execute('''
                UPDATE users 
                SET locked_until = ?, updated_at = ?
                WHERE username = ?
            ''', (locked_until.isoformat(), datetime.now().isoformat(), username))
            
            conn.commit()
            logging.warning(f"账号 {username} 已被锁定，锁定时长：{self.LOCK_DURATION_MINUTES} 分钟")
        except Exception as e:
            logging.error(f"锁定账号失败: {e}")
    
    def _unlock_account(self, username: str):
        """解锁账号"""
        try:
            conn = self.db.get_connection()
            cursor = conn.cursor()
            
            cursor.execute('''
                UPDATE users 
                SET failed_login_count = 0, locked_until = NULL, updated_at = ?
                WHERE username = ?
            ''', (datetime.now().isoformat(), username))
            
            conn.commit()
            logging.info(f"账号 {username} 已解锁")
        except Exception as e:
            logging.error(f"解锁账号失败: {e}")
    
    def unlock_account_by_admin(self, username: str) -> tuple[bool, str]:
        """管理员解锁账号"""
        user = self.db.get_user_by_username(username)
        if not user:
            return False, "用户不存在"
        
        self._unlock_account(username)
        return True, f"账号 {username} 已解锁"
    
    def _log_login(self, username: str, success: bool, message: str):
        machine_name = platform.node()
        self.db.add_login_log(username, success, message, machine_name)
    
    def change_password(self, username: str, old_password: str, new_password: str) -> tuple[bool, str]:
        user = self.db.get_user_by_username(username)
        if not user:
            return False, "用户不存在"
        
        if not PasswordService.verify_password(
            old_password,
            user['password_hash'],
            user['salt'],
            user['hash_iterations']
        ):
            return False, "当前密码错误"
        
        valid, msg = PasswordService.validate_password(new_password)
        if not valid:
            return False, msg
        
        password_data = PasswordService.create_password_hash(new_password)
        self.db.update_password(
            username,
            password_data['password_hash'],
            password_data['salt'],
            password_data['hash_iterations']
        )
        
        logging.info(f"用户 {username} 修改密码成功")
        return True, "密码修改成功"
    
    def get_remembered_username(self) -> str:
        return self.db.get_setting('remembered_username') or ''
    
    def set_remembered_username(self, username: str):
        self.db.set_setting('remembered_username', username)
    
    def get_display_name(self, username: str) -> str:
        user = self.db.get_user_by_username(username)
        if user and user['display_name']:
            return user['display_name']
        return username
