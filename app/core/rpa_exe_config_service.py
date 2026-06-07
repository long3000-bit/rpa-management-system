import logging
import uuid
import subprocess
import psutil
from datetime import datetime
from typing import Optional, List, Dict, Tuple
from pathlib import Path

from app.storage.database import Database


class RpaExeConfigService:
    
    def __init__(self, db: Database):
        self.db = db
    
    def get_all_configs(self) -> Tuple[List[Dict], str]:
        try:
            conn = self.db.get_connection()
            cursor = conn.cursor()
            
            cursor.execute('''
                SELECT config_id, config_name, exe_path, process_name,
                       main_window_title, login_window_title, username,
                       login_success_rule, default_wait_time, operation_timeout,
                       close_old_process, auto_login, enabled,
                       created_at, updated_at
                FROM rpa_exe_configs
                WHERE enabled = 1
                ORDER BY created_at DESC
            ''')
            
            rows = cursor.fetchall()
            configs = [dict(row) for row in rows]
            
            for config in configs:
                config.pop('password', None)
            
            return configs, ""
            
        except Exception as e:
            logging.error(f"获取EXE配置列表失败: {e}")
            return [], str(e)
    
    def get_config(self, config_id: str) -> Tuple[Dict, str]:
        try:
            conn = self.db.get_connection()
            cursor = conn.cursor()
            
            cursor.execute('''
                SELECT config_id, config_name, exe_path, process_name,
                       main_window_title, login_window_title, username,
                       password, login_success_rule, default_wait_time,
                       operation_timeout, close_old_process, auto_login,
                       enabled, created_at, updated_at
                FROM rpa_exe_configs
                WHERE config_id = ?
            ''', (config_id,))
            
            row = cursor.fetchone()
            if not row:
                return {}, "配置不存在"
            
            return dict(row), ""
            
        except Exception as e:
            logging.error(f"获取EXE配置失败: {e}")
            return {}, str(e)
    
    def save_config(self, config_data: Dict) -> Tuple[str, str]:
        try:
            conn = self.db.get_connection()
            cursor = conn.cursor()
            now = datetime.now().isoformat()
            
            config_id = config_data.get('config_id', '')
            
            if config_id:
                cursor.execute('''
                    UPDATE rpa_exe_configs
                    SET config_name = ?, exe_path = ?, process_name = ?,
                        main_window_title = ?, login_window_title = ?,
                        username = ?, password = ?, login_success_rule = ?,
                        default_wait_time = ?, operation_timeout = ?,
                        close_old_process = ?, auto_login = ?, updated_at = ?
                    WHERE config_id = ?
                ''', (
                    config_data['config_name'],
                    config_data['exe_path'],
                    config_data.get('process_name', ''),
                    config_data.get('main_window_title', ''),
                    config_data.get('login_window_title', ''),
                    config_data.get('username', ''),
                    config_data.get('password', ''),
                    config_data.get('login_success_rule', ''),
                    config_data.get('default_wait_time', 5),
                    config_data.get('operation_timeout', 30),
                    config_data.get('close_old_process', 1),
                    config_data.get('auto_login', 1),
                    now,
                    config_id
                ))
            else:
                config_id = f"EXE{datetime.now().strftime('%Y%m%d%H%M%S')}{uuid.uuid4().hex[:4]}"
                
                cursor.execute('''
                    INSERT INTO rpa_exe_configs
                    (config_id, config_name, exe_path, process_name,
                     main_window_title, login_window_title, username, password,
                     login_success_rule, default_wait_time, operation_timeout,
                     close_old_process, auto_login, enabled, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?)
                ''', (
                    config_id,
                    config_data['config_name'],
                    config_data['exe_path'],
                    config_data.get('process_name', ''),
                    config_data.get('main_window_title', ''),
                    config_data.get('login_window_title', ''),
                    config_data.get('username', ''),
                    config_data.get('password', ''),
                    config_data.get('login_success_rule', ''),
                    config_data.get('default_wait_time', 5),
                    config_data.get('operation_timeout', 30),
                    config_data.get('close_old_process', 1),
                    config_data.get('auto_login', 1),
                    now,
                    now
                ))
            
            conn.commit()
            
            logging.info(f"保存EXE配置成功: {config_id}")
            
            return config_id, ""
            
        except Exception as e:
            conn.rollback()
            logging.error(f"保存EXE配置失败: {e}")
            return "", str(e)
    
    def delete_config(self, config_id: str) -> Tuple[bool, str]:
        try:
            conn = self.db.get_connection()
            cursor = conn.cursor()
            
            cursor.execute('''
                UPDATE rpa_exe_configs SET enabled = 0 WHERE config_id = ?
            ''', (config_id,))
            
            conn.commit()
            
            return True, ""
            
        except Exception as e:
            conn.rollback()
            logging.error(f"删除EXE配置失败: {e}")
            return False, str(e)
    
    def test_launch(self, config_id: str) -> Tuple[bool, str]:
        try:
            config, error = self.get_config(config_id)
            if error:
                return False, error
            
            exe_path = config.get('exe_path', '')
            if not exe_path:
                return False, "EXE路径为空"
            
            if not Path(exe_path).exists():
                return False, f"EXE文件不存在: {exe_path}"
            
            process_name = config.get('process_name', '')
            if config.get('close_old_process', 0):
                self._close_old_process(process_name or Path(exe_path).stem)
            
            subprocess.Popen([exe_path], shell=True)
            
            logging.info(f"启动EXE成功: {exe_path}")
            
            return True, "启动成功"
            
        except Exception as e:
            logging.error(f"启动EXE失败: {e}")
            return False, str(e)
    
    def test_connection(self, config_id: str) -> Tuple[bool, str]:
        try:
            config, error = self.get_config(config_id)
            if error:
                return False, error
            
            process_name = config.get('process_name', '')
            if not process_name:
                process_name = Path(config.get('exe_path', '')).stem
            
            found = False
            for proc in psutil.process_iter(['name', 'pid']):
                try:
                    if proc.info['name'].lower() == process_name.lower():
                        found = True
                        break
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    continue
            
            if found:
                return True, f"进程 {process_name} 正在运行"
            else:
                return False, f"未找到进程 {process_name}"
            
        except Exception as e:
            logging.error(f"测试连接失败: {e}")
            return False, str(e)
    
    def _close_old_process(self, process_name: str):
        try:
            for proc in psutil.process_iter(['name', 'pid']):
                try:
                    if proc.info['name'].lower() == process_name.lower():
                        proc.kill()
                        logging.info(f"关闭旧进程: {process_name} (PID: {proc.info['pid']})")
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    continue
        except Exception as e:
            logging.warning(f"关闭旧进程失败: {e}")
    
    def get_process_list(self) -> Tuple[List[Dict], str]:
        try:
            processes = []
            seen = set()
            
            for proc in psutil.process_iter(['name', 'pid', 'exe']):
                try:
                    name = proc.info['name']
                    if name and name not in seen:
                        seen.add(name)
                        processes.append({
                            'name': name,
                            'pid': proc.info['pid'],
                            'exe': proc.info.get('exe', '')
                        })
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    continue
            
            processes.sort(key=lambda x: x['name'].lower())
            
            return processes, ""
            
        except Exception as e:
            logging.error(f"获取进程列表失败: {e}")
            return [], str(e)