import logging
import time
from typing import Dict, Tuple, Optional
from datetime import datetime

from app.core.rpa_action_model import ActionStep, ActionType, ValueSource
from app.core.rpa_control_locator import ControlLocator
from app.storage.database import Database


class RpaAutoLogin:
    
    def __init__(self, db: Database):
        self.db = db
        self.locator = ControlLocator()
        
    def auto_login(self, exe_config: Dict) -> Tuple[bool, str]:
        exe_path = exe_config.get('exe_path', '')
        process_name = exe_config.get('process_name', '')
        main_window_title = exe_config.get('main_window_title', '')
        login_window_title = exe_config.get('login_window_title', '')
        username = exe_config.get('username', '')
        password = exe_config.get('password', '')
        login_success_rule = exe_config.get('login_success_rule', '')
        auto_login = exe_config.get('auto_login', 1)
        
        if not auto_login:
            logging.info("配置为不自动登录，跳过登录步骤")
            return True, "不自动登录"
        
        if not username or not password:
            logging.warning("缺少登录账号或密码")
            return False, "缺少登录账号或密码"
        
        logging.info(f"开始自动登录流程")
        
        success, message = self._connect_or_launch(exe_path, process_name, main_window_title)
        if not success:
            return False, message
        
        success, message = self._wait_for_login_window(login_window_title, main_window_title)
        if not success:
            if "已登录" in message:
                return True, message
            return False, message
        
        success, message = self._input_credentials(username, password)
        if not success:
            return False, message
        
        success, message = self._click_login_button()
        if not success:
            return False, message
        
        success, message = self._verify_login_success(main_window_title, login_success_rule)
        if not success:
            return False, message
        
        logging.info(f"自动登录成功")
        return True, "自动登录成功"
    
    def _connect_or_launch(self, exe_path: str, process_name: str,
                          main_window_title: str) -> Tuple[bool, str]:
        if process_name:
            success, message = self.locator.connect_application(process_name=process_name)
            if success:
                logging.info(f"已连接现有进程: {process_name}")
                return True, message
        
        if exe_path:
            success, message = self.locator.launch_application(exe_path)
            if success:
                logging.info(f"已启动新进程: {exe_path}")
                return True, message
        
        if main_window_title:
            success, message = self.locator.connect_application(window_title=main_window_title)
            if success:
                logging.info(f"已连接现有窗口: {main_window_title}")
                return True, message
        
        return False, "无法连接或启动应用程序"
    
    def _wait_for_login_window(self, login_window_title: str,
                               main_window_title: str) -> Tuple[bool, str]:
        if main_window_title:
            success, message = self.locator.wait_window(main_window_title, timeout=3)
            if success:
                logging.info(f"检测到主窗口，可能已登录")
                return True, "已登录，检测到主窗口"
        
        if login_window_title:
            success, message = self.locator.wait_window(login_window_title, timeout=10)
            if success:
                logging.info(f"检测到登录窗口")
                return True, "检测到登录窗口"
        
        return False, "未检测到登录窗口或主窗口"
    
    def _input_credentials(self, username: str, password: str) -> Tuple[bool, str]:
        username_locator = {
            'locator_type': 'uia',
            'control_type': 'Edit',
            'name': '用户名'
        }
        
        control, message = self.locator.find_control(username_locator, timeout=5)
        if control:
            success, message = self.locator.input_text(control, username, clear_first=True)
            if not success:
                logging.warning(f"输入用户名失败，尝试其他定位方式: {message}")
        
        if not control:
            username_locator2 = {
                'locator_type': 'uia',
                'control_type': 'Edit',
                'automation_id': 'username'
            }
            control, message = self.locator.find_control(username_locator2, timeout=5)
            if control:
                self.locator.input_text(control, username, clear_first=True)
        
        if not control:
            username_locator3 = {
                'locator_type': 'control_type',
                'control_type': 'Edit'
            }
            controls = self.locator.current_window.children()
            edit_controls = [c for c in controls if c.element_info.control_type == 'Edit']
            if len(edit_controls) >= 1:
                self.locator.input_text(edit_controls[0], username, clear_first=True)
        
        password_locator = {
            'locator_type': 'uia',
            'control_type': 'Edit',
            'name': '密码'
        }
        
        control, message = self.locator.find_control(password_locator, timeout=5)
        if control:
            success, message = self.locator.input_text(control, password, clear_first=True)
            if not success:
                logging.warning(f"输入密码失败，尝试其他定位方式: {message}")
        
        if not control:
            password_locator2 = {
                'locator_type': 'uia',
                'control_type': 'Edit',
                'automation_id': 'password'
            }
            control, message = self.locator.find_control(password_locator2, timeout=5)
            if control:
                self.locator.input_text(control, password, clear_first=True)
        
        if not control:
            controls = self.locator.current_window.children()
            edit_controls = [c for c in controls if c.element_info.control_type == 'Edit']
            if len(edit_controls) >= 2:
                self.locator.input_text(edit_controls[1], password, clear_first=True)
        
        logging.info(f"已输入用户名和密码")
        return True, "已输入用户名和密码"
    
    def _click_login_button(self) -> Tuple[bool, str]:
        login_button_locator = {
            'locator_type': 'uia',
            'control_type': 'Button',
            'name': '登录'
        }
        
        control, message = self.locator.find_control(login_button_locator, timeout=5)
        if control:
            success, message = self.locator.click_control(control)
            if success:
                logging.info(f"点击登录按钮成功")
                return True, "点击登录按钮成功"
        
        login_button_locator2 = {
            'locator_type': 'uia',
            'control_type': 'Button',
            'automation_id': 'login'
        }
        
        control, message = self.locator.find_control(login_button_locator2, timeout=5)
        if control:
            success, message = self.locator.click_control(control)
            if success:
                logging.info(f"点击登录按钮成功")
                return True, "点击登录按钮成功"
        
        try:
            import pywinauto.keyboard as keyboard
            keyboard.send_keys('{ENTER}')
            logging.info(f"使用Enter键登录")
            return True, "使用Enter键登录"
        except:
            pass
        
        return False, "未找到登录按钮"
    
    def _verify_login_success(self, main_window_title: str,
                              login_success_rule: str) -> Tuple[bool, str]:
        time.sleep(3)
        
        if main_window_title:
            success, message = self.locator.wait_window(main_window_title, timeout=10)
            if success:
                logging.info(f"登录成功，检测到主窗口: {main_window_title}")
                return True, "登录成功"
        
        if login_success_rule:
            if "窗口标题包含" in login_success_rule:
                keyword = login_success_rule.replace("窗口标题包含", "").strip().strip("'\"")
                current_title = self.locator.current_window.window_text()
                if keyword in current_title:
                    logging.info(f"登录成功，窗口标题包含: {keyword}")
                    return True, "登录成功"
        
        error_locator = {
            'locator_type': 'uia',
            'control_type': 'Text',
        }
        
        control, message = self.locator.find_control(error_locator, timeout=2)
        if control:
            text, _ = self.locator.read_text(control)
            if "错误" in text or "失败" in text or "密码" in text:
                logging.error(f"登录失败，检测到错误提示: {text}")
                return False, f"登录失败: {text}"
        
        return False, "登录验证失败"
    
    def test_login(self, exe_config_id: str) -> Tuple[bool, str]:
        try:
            conn = self.db.get_connection()
            cursor = conn.cursor()
            
            cursor.execute('''
                SELECT config_id, config_name, exe_path, process_name,
                       main_window_title, login_window_title, username,
                       password, login_success_rule, auto_login
                FROM rpa_exe_configs
                WHERE config_id = ?
            ''', (exe_config_id,))
            
            row = cursor.fetchone()
            if not row:
                return False, "配置不存在"
            
            exe_config = dict(row)
            
            return self.auto_login(exe_config)
            
        except Exception as e:
            logging.error(f"测试登录失败: {e}")
            return False, str(e)