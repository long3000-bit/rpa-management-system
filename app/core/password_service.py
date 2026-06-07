import os
import hashlib
import secrets
import re
from app.config import HASH_ITERATIONS, PASSWORD_MIN_LENGTH


class PasswordService:
    
    @staticmethod
    def generate_salt() -> str:
        return secrets.token_hex(16)
    
    @staticmethod
    def hash_password(password: str, salt: str, iterations: int = HASH_ITERATIONS) -> str:
        password_bytes = password.encode('utf-8')
        salt_bytes = salt.encode('utf-8')
        
        dk = hashlib.pbkdf2_hmac(
            'sha256',
            password_bytes,
            salt_bytes,
            iterations,
            dklen=32
        )
        return dk.hex()
    
    @staticmethod
    def verify_password(password: str, password_hash: str, salt: str, iterations: int = HASH_ITERATIONS) -> bool:
        computed_hash = PasswordService.hash_password(password, salt, iterations)
        return secrets.compare_digest(computed_hash, password_hash)
    
    @staticmethod
    def validate_password(password: str) -> tuple[bool, str]:
        """验证密码复杂度
        
        要求：
        - 至少8位
        - 包含数字和字母
        
        Args:
            password: 待验证的密码
        
        Returns:
            (是否有效, 错误消息)
        """
        if not password:
            return False, "密码不能为空"
        
        if len(password) < 8:
            return False, "密码长度不能少于8位"
        
        # 检查是否包含数字
        if not re.search(r'\d', password):
            return False, "密码必须包含数字"
        
        # 检查是否包含字母
        if not re.search(r'[a-zA-Z]', password):
            return False, "密码必须包含字母"
        
        return True, ""
    
    @staticmethod
    def create_password_hash(password: str) -> dict:
        salt = PasswordService.generate_salt()
        password_hash = PasswordService.hash_password(password, salt)
        return {
            'password_hash': password_hash,
            'salt': salt,
            'hash_iterations': HASH_ITERATIONS
        }
