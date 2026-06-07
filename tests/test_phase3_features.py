"""
第三阶段功能测试脚本
测试内容：
1. 登录失败次数限制
2. 账号锁定功能
3. 密码复杂度验证
4. 临时密码强制修改
5. 操作日志记录
6. 用户管理锁定状态显示
7. 解锁账号功能
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from datetime import datetime, timedelta
from app.storage.database import Database
from app.core.auth_service import AuthService
from app.core.password_service import PasswordService
from app.core.permission_service import PermissionService


def test_login_failed_count_limit():
    """测试登录失败次数限制"""
    print("\n=== 测试1：登录失败次数限制 ===")
    
    db = Database()
    auth_service = AuthService(db)
    
    # 创建测试用户
    test_username = "test_failed_login"
    
    # 先删除测试用户（如果存在）
    try:
        conn = db.get_connection()
        cursor = conn.cursor()
        cursor.execute('DELETE FROM users WHERE username = ?', (test_username,))
        conn.commit()
    except:
        pass
    
    # 创建测试用户
    password_result = PasswordService.create_password_hash("Test1234")
    conn = db.get_connection()
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO users 
        (username, password_hash, salt, hash_iterations, display_name, role_code, status, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (
        test_username,
        password_result['password_hash'],
        password_result['salt'],
        password_result['hash_iterations'],
        '测试用户',
        'store_manager',
        'active',
        datetime.now().isoformat(),
        datetime.now().isoformat()
    ))
    conn.commit()
    
    print(f"创建测试用户: {test_username}")
    
    # 测试连续登录失败
    for i in range(6):
        result = auth_service.login(test_username, "wrong_password")
        print(f"第{i+1}次登录失败: {result.message}")
        
        if i == 4:
            # 第5次失败应该锁定账号
            assert "账号已被锁定" in result.message, f"第5次失败应该锁定账号，实际消息: {result.message}"
            print("✓ 第5次失败后账号被锁定")
        
        if i == 5:
            # 第6次失败应该提示账号已锁定
            assert "账号已被锁定" in result.message, f"账号锁定后应提示已锁定，实际消息: {result.message}"
            print("✓ 账号锁定后登录提示正确")
    
    # 验证失败次数
    cursor.execute('SELECT failed_login_count, locked_until FROM users WHERE username = ?', (test_username,))
    row = cursor.fetchone()
    assert row['failed_login_count'] == 5, f"失败次数应为5，实际: {row['failed_login_count']}"
    assert row['locked_until'] is not None, "账号应被锁定"
    print(f"✓ 失败次数记录正确: {row['failed_login_count']}")
    print(f"✓ 账号锁定时间: {row['locked_until']}")
    
    # 清理测试用户
    cursor.execute('DELETE FROM users WHERE username = ?', (test_username,))
    conn.commit()
    db.close()
    
    print("测试1完成：登录失败次数限制功能正常")


def test_password_complexity():
    """测试密码复杂度验证"""
    print("\n=== 测试2：密码复杂度验证 ===")
    
    # 测试各种密码
    test_cases = [
        ("", False, "密码不能为空"),
        ("123", False, "密码长度不能少于8位"),
        ("abcdefg", False, "密码长度不能少于8位"),
        ("12345678", False, "密码必须包含字母"),
        ("abcdefgh", False, "密码必须包含数字"),
        ("abc12345", True, ""),
        ("Test1234", True, ""),
        ("ComplexPass123", True, ""),
    ]
    
    for password, expected_valid, expected_msg in test_cases:
        valid, msg = PasswordService.validate_password(password)
        assert valid == expected_valid, f"密码 '{password}' 验证结果应为 {expected_valid}，实际为 {valid}"
        if not expected_valid:
            assert expected_msg in msg, f"密码 '{password}' 错误消息应包含 '{expected_msg}'，实际为 '{msg}'"
        
        status = "✓" if valid else "✗"
        print(f"{status} 密码 '{password}': {msg if msg else '有效'}")
    
    print("测试2完成：密码复杂度验证功能正常")


def test_must_change_password():
    """测试临时密码强制修改"""
    print("\n=== 测试3：临时密码强制修改 ===")
    
    db = Database()
    auth_service = AuthService(db)
    
    # 创建测试用户（需要强制修改密码）
    test_username = "test_must_change_pwd"
    
    # 先删除测试用户（如果存在）
    try:
        conn = db.get_connection()
        cursor = conn.cursor()
        cursor.execute('DELETE FROM users WHERE username = ?', (test_username,))
        conn.commit()
    except:
        pass
    
    # 创建测试用户（设置must_change_password=1）
    password_result = PasswordService.create_password_hash("TempPass123")
    conn = db.get_connection()
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO users 
        (username, password_hash, salt, hash_iterations, display_name, role_code, status, must_change_password, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (
        test_username,
        password_result['password_hash'],
        password_result['salt'],
        password_result['hash_iterations'],
        '临时密码测试用户',
        'store_manager',
        'active',
        1,  # must_change_password
        datetime.now().isoformat(),
        datetime.now().isoformat()
    ))
    conn.commit()
    
    print(f"创建测试用户: {test_username} (must_change_password=1)")
    
    # 测试登录
    result = auth_service.login(test_username, "TempPass123")
    assert result.success, f"登录应该成功，实际消息: {result.message}"
    assert result.must_change_password, "登录结果应标记需要强制修改密码"
    
    print(f"✓ 登录成功: {result.message}")
    print(f"✓ 需要强制修改密码: {result.must_change_password}")
    
    # 清理测试用户
    cursor.execute('DELETE FROM users WHERE username = ?', (test_username,))
    conn.commit()
    db.close()
    
    print("测试3完成：临时密码强制修改功能正常")


def test_operation_log():
    """测试操作日志记录"""
    print("\n=== 测试4：操作日志记录 ===")
    
    db = Database()
    permission_service = PermissionService(db)
    
    # 记录测试日志
    test_username = "test_log_user"
    
    # 记录各种操作日志
    operations = [
        ('config_create', '新增云药店API配置', 'yys_api_config', 'new'),
        ('config_edit', '编辑云药店API配置', 'yys_api_config', 'test_id'),
        ('config_delete', '删除云药店API配置', 'yys_api_config', 'test_id'),
        ('user_create', '创建用户', 'user', 'test_user'),
        ('user_edit', '编辑用户', 'user', 'test_user'),
        ('user_unlock', '解锁用户账号', 'user', 'test_user'),
        ('role_permission_update', '更新角色权限', 'role', 'store_manager'),
    ]
    
    for op_type, op_desc, target_type, target_id in operations:
        permission_service.log_operation(
            username=test_username,
            operation_type=op_type,
            operation_desc=op_desc,
            target_type=target_type,
            target_id=target_id
        )
        print(f"✓ 记录日志: {op_desc}")
    
    # 查询日志
    logs = permission_service.get_operation_logs(username=test_username, limit=10)
    assert len(logs) >= len(operations), f"应至少有{len(operations)}条日志，实际: {len(logs)}"
    
    print(f"✓ 查询到 {len(logs)} 条日志")
    
    # 验证日志字段
    for log in logs:
        assert 'permission_code' in log, "日志应包含permission_code字段"
        assert 'result' in log, "日志应包含result字段"
        print(f"  - {log['operation_desc']}: permission_code={log['permission_code']}, result={log['result']}")
    
    # 清理测试日志
    deleted_count = permission_service.delete_operation_logs(username=test_username)
    print(f"✓ 清理测试日志: {deleted_count} 条")
    
    db.close()
    
    print("测试4完成：操作日志记录功能正常")


def test_account_unlock():
    """测试解锁账号功能"""
    print("\n=== 测试5：解锁账号功能 ===")
    
    db = Database()
    auth_service = AuthService(db)
    
    # 创建测试用户并锁定
    test_username = "test_unlock_user"
    
    # 先删除测试用户（如果存在）
    try:
        conn = db.get_connection()
        cursor = conn.cursor()
        cursor.execute('DELETE FROM users WHERE username = ?', (test_username,))
        conn.commit()
    except:
        pass
    
    # 创建测试用户
    password_result = PasswordService.create_password_hash("Test1234")
    conn = db.get_connection()
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO users 
        (username, password_hash, salt, hash_iterations, display_name, role_code, status, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (
        test_username,
        password_result['password_hash'],
        password_result['salt'],
        password_result['hash_iterations'],
        '解锁测试用户',
        'store_manager',
        'active',
        datetime.now().isoformat(),
        datetime.now().isoformat()
    ))
    conn.commit()
    
    # 手动锁定账号
    locked_until = datetime.now() + timedelta(minutes=30)
    cursor.execute('''
        UPDATE users 
        SET failed_login_count = 5, locked_until = ?
        WHERE username = ?
    ''', (locked_until.isoformat(), test_username))
    conn.commit()
    
    print(f"创建并锁定测试用户: {test_username}")
    
    # 验证账号已锁定
    cursor.execute('SELECT failed_login_count, locked_until FROM users WHERE username = ?', (test_username,))
    row = cursor.fetchone()
    assert row['failed_login_count'] == 5, f"失败次数应为5，实际: {row['failed_login_count']}"
    assert row['locked_until'] is not None, "账号应被锁定"
    print(f"✓ 账号已锁定: failed_count={row['failed_login_count']}, locked_until={row['locked_until']}")
    
    # 解锁账号
    success, msg = auth_service.unlock_account_by_admin(test_username)
    assert success, f"解锁应该成功，实际消息: {msg}"
    print(f"✓ 解锁账号: {msg}")
    
    # 验证账号已解锁
    cursor.execute('SELECT failed_login_count, locked_until FROM users WHERE username = ?', (test_username,))
    row = cursor.fetchone()
    assert row['failed_login_count'] == 0, f"失败次数应为0，实际: {row['failed_login_count']}"
    assert row['locked_until'] is None, "账号应已解锁"
    print(f"✓ 账号已解锁: failed_count={row['failed_login_count']}, locked_until={row['locked_until']}")
    
    # 测试登录
    result = auth_service.login(test_username, "Test1234")
    assert result.success, f"解锁后登录应该成功，实际消息: {result.message}"
    print(f"✓ 解锁后登录成功: {result.message}")
    
    # 清理测试用户
    cursor.execute('DELETE FROM users WHERE username = ?', (test_username,))
    conn.commit()
    db.close()
    
    print("测试5完成：解锁账号功能正常")


def run_all_tests():
    """运行所有测试"""
    print("=" * 60)
    print("第三阶段功能测试")
    print("=" * 60)
    
    try:
        test_login_failed_count_limit()
        test_password_complexity()
        test_must_change_password()
        test_operation_log()
        test_account_unlock()
        
        print("\n" + "=" * 60)
        print("所有测试通过！第三阶段功能正常")
        print("=" * 60)
        
    except Exception as e:
        print(f"\n测试失败: {e}")
        import traceback
        traceback.print_exc()


if __name__ == '__main__':
    run_all_tests()