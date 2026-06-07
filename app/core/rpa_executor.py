import logging
import time
import uuid
from datetime import datetime
from typing import Dict, List, Tuple, Optional
from pathlib import Path

from app.core.rpa_action_model import ActionStep, ActionResult, ActionType, ErrorHandling
from app.core.rpa_control_locator import ControlLocator
from app.storage.database import Database


class RpaExecutor:
    
    def __init__(self, db: Database):
        self.db = db
        self.locator = ControlLocator()
        self.current_row_data = {}
        self.action_results = {}
        self.task_id = ""
        self.task_dir = ""
        
    def execute_workflow(self, workflow_steps: List[ActionStep], row_data: Dict,
                        task_id: str, screenshot_dir: str) -> Tuple[bool, Dict]:
        self.current_row_data = row_data
        self.action_results = {}
        self.task_id = task_id
        self.task_dir = screenshot_dir
        
        all_results = []
        
        for step_idx, step in enumerate(workflow_steps):
            logging.info(f"执行步骤{step_idx+1}: {step.description}")
            
            result = self._execute_single_action(step)
            all_results.append(result)
            
            if step.save_result_to:
                self.action_results[step.save_result_to] = result.result_value
            
            if not result.success:
                if step.on_error == ErrorHandling.STOP:
                    logging.error(f"步骤{step_idx+1}失败，停止执行: {result.error_message}")
                    return False, {
                        'success': False,
                        'error_message': result.error_message,
                        'screenshot_path': result.screenshot_path,
                        'action_results': all_results
                    }
                elif step.on_error == ErrorHandling.SKIP:
                    logging.warning(f"步骤{step_idx+1}失败，跳过继续: {result.error_message}")
                    continue
                elif step.on_error == ErrorHandling.RETRY:
                    for retry in range(step.retry_count):
                        logging.info(f"步骤{step_idx+1}重试{retry+1}/{step.retry_count}")
                        result = self._execute_single_action(step)
                        if result.success:
                            all_results[-1] = result
                            if step.save_result_to:
                                self.action_results[step.save_result_to] = result.result_value
                            break
                    
                    if not result.success:
                        logging.error(f"步骤{step_idx+1}重试失败: {result.error_message}")
                        return False, {
                            'success': False,
                            'error_message': result.error_message,
                            'screenshot_path': result.screenshot_path,
                            'action_results': all_results
                        }
        
        return True, {
            'success': True,
            'action_results': all_results,
            'saved_values': self.action_results
        }
    
    def _execute_single_action(self, step: ActionStep) -> ActionResult:
        start_time = time.time()
        
        try:
            if step.action_type == ActionType.CLICK:
                success, message = self._execute_click(step)
            elif step.action_type == ActionType.INPUT:
                success, message = self._execute_input(step)
            elif step.action_type == ActionType.CLEAR_INPUT:
                success, message = self._execute_clear_input(step)
            elif step.action_type == ActionType.WAIT_WINDOW:
                success, message = self._execute_wait_window(step)
            elif step.action_type == ActionType.WAIT_CONTROL:
                success, message = self._execute_wait_control(step)
            elif step.action_type == ActionType.READ_TEXT:
                success, message = self._execute_read_text(step)
            elif step.action_type == ActionType.DELAY:
                success, message = self._execute_delay(step)
            elif step.action_type == ActionType.SCREENSHOT:
                success, message = self._execute_screenshot(step)
            elif step.action_type == ActionType.HOTKEY:
                success, message = self._execute_hotkey(step)
            else:
                success = False
                message = f"未支持的动作类型: {step.action_type}"
            
            execution_time = time.time() - start_time
            
            return ActionResult(
                success=success,
                action_type=step.action_type,
                result_value=message if success else "",
                error_message=message if not success else "",
                execution_time=execution_time
            )
            
        except Exception as e:
            execution_time = time.time() - start_time
            logging.error(f"执行动作异常: {e}")
            
            screenshot_path = ""
            if self.task_dir:
                screenshot_path = self._take_failure_screenshot()
            
            return ActionResult(
                success=False,
                action_type=step.action_type,
                error_message=str(e),
                screenshot_path=screenshot_path,
                execution_time=execution_time
            )
    
    def _execute_click(self, step: ActionStep) -> Tuple[bool, str]:
        control, message = self.locator.find_control(step.target, step.timeout)
        if not control:
            return False, f"未找到控件: {message}"
        
        return self.locator.click_control(control)
    
    def _execute_input(self, step: ActionStep) -> Tuple[bool, str]:
        control, message = self.locator.find_control(step.target, step.timeout)
        if not control:
            return False, f"未找到控件: {message}"
        
        text = self._get_input_value(step)
        return self.locator.input_text(control, text, clear_first=True)
    
    def _execute_clear_input(self, step: ActionStep) -> Tuple[bool, str]:
        control, message = self.locator.find_control(step.target, step.timeout)
        if not control:
            return False, f"未找到控件: {message}"
        
        return self.locator.input_text(control, "", clear_first=True)
    
    def _execute_wait_window(self, step: ActionStep) -> Tuple[bool, str]:
        window_title = step.target.get('window_title', '')
        if not window_title:
            return False, "缺少window_title参数"
        
        return self.locator.wait_window(window_title, step.timeout)
    
    def _execute_wait_control(self, step: ActionStep) -> Tuple[bool, str]:
        control, message = self.locator.find_control(step.target, step.timeout)
        if control:
            return True, ""
        return False, f"等待控件超时: {message}"
    
    def _execute_read_text(self, step: ActionStep) -> Tuple[bool, str]:
        control, message = self.locator.find_control(step.target, step.timeout)
        if not control:
            return False, f"未找到控件: {message}"
        
        text, error = self.locator.read_text(control)
        if error:
            return False, error
        
        return True, text
    
    def _execute_delay(self, step: ActionStep) -> Tuple[bool, str]:
        delay_seconds = float(step.value) if step.value else 1.0
        time.sleep(delay_seconds)
        return True, f"延时{delay_seconds}秒"
    
    def _execute_screenshot(self, step: ActionStep) -> Tuple[bool, str]:
        if not self.task_dir:
            return False, "未设置截图目录"
        
        screenshot_name = f"{datetime.now().strftime('%H%M%S')}_{step.description}.png"
        screenshot_path = Path(self.task_dir) / screenshot_name
        
        return self.locator.take_screenshot(str(screenshot_path))
    
    def _execute_hotkey(self, step: ActionStep) -> Tuple[bool, str]:
        try:
            import pywinauto.keyboard as keyboard
            
            hotkey = step.value
            keyboard.send_keys(hotkey)
            return True, f"发送快捷键: {hotkey}"
        except Exception as e:
            return False, f"发送快捷键失败: {e}"
    
    def _get_input_value(self, step: ActionStep) -> str:
        if step.value_source == "constant":
            return step.value
        elif step.value_source == "system_field":
            return self.current_row_data.get(step.value_field, "")
        elif step.value_source == "previous_result":
            return self.action_results.get(step.value_field, "")
        else:
            return step.value
    
    def _take_failure_screenshot(self) -> str:
        try:
            screenshot_name = f"{datetime.now().strftime('%H%M%S')}_失败.png"
            screenshot_path = Path(self.task_dir) / screenshot_name
            
            success, path = self.locator.take_screenshot(str(screenshot_path))
            if success:
                return path
            return ""
        except:
            return ""
    
    def save_task_result(self, row_id: str, success: bool, system_no: str = "",
                        system_message: str = "", error_message: str = "",
                        screenshot_path: str = "") -> Tuple[bool, str]:
        try:
            conn = self.db.get_connection()
            cursor = conn.cursor()
            now = datetime.now().isoformat()
            
            status = "成功" if success else "失败"
            
            cursor.execute('''
                UPDATE rpa_task_rows
                SET status = ?, system_no = ?, system_message = ?,
                    error_message = ?, screenshot_path = ?, finished_at = ?
                WHERE row_id = ?
            ''', (status, system_no, system_message, error_message, screenshot_path, now, row_id))
            
            cursor.execute('''
                UPDATE rpa_import_details
                SET rpa_status = ?, target_system_no = ?, target_system_message = ?,
                    last_executed_at = ?, execute_count = execute_count + 1
                WHERE import_row_id = (
                    SELECT import_row_id FROM rpa_task_rows WHERE row_id = ?
                )
            ''', (status, system_no, system_message, now, row_id))
            
            conn.commit()
            return True, ""
            
        except Exception as e:
            logging.error(f"保存任务结果失败: {e}")
            return False, str(e)