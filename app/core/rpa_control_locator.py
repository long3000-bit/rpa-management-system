import logging
import time
from typing import Optional, Dict, Any, Tuple
from pathlib import Path
from enum import Enum

try:
    import pywinauto
    from pywinauto import Application, findwindows
    from pywinauto.controls.uiawrapper import UIAWrapper
    PYWINAUTO_AVAILABLE = True
except ImportError:
    PYWINAUTO_AVAILABLE = False
    logging.warning("pywinauto未安装，控件定位功能将受限")

try:
    import uiautomation as auto
    UIAUTOMATION_AVAILABLE = True
except ImportError:
    UIAUTOMATION_AVAILABLE = False
    logging.warning("uiautomation未安装，控件定位功能将受限")


class LocatorType(Enum):
    UIA = "uia"
    PYWINAUTO = "pywinauto"
    NAME = "name"
    CONTROL_TYPE = "control_type"
    AUTOMATION_ID = "automation_id"
    CLASS_NAME = "class_name"
    TITLE = "title"
    COORDINATE = "coordinate"


class ControlLocator:
    
    def __init__(self):
        self.app = None
        self.main_window = None
        self.current_window = None
        
    def connect_application(self, exe_path: str = None, process_name: str = None,
                           window_title: str = None) -> Tuple[bool, str]:
        if not PYWINAUTO_AVAILABLE:
            return False, "pywinauto未安装，无法连接应用程序"
        
        try:
            if process_name:
                self.app = Application(backend="uia").connect(process=process_name)
            elif window_title:
                self.app = Application(backend="uia").connect(title_re=window_title)
            elif exe_path:
                self.app = Application(backend="uia").connect(path=exe_path)
            else:
                return False, "必须提供exe_path、process_name或window_title"
            
            self.main_window = self.app.top_window()
            self.current_window = self.main_window
            
            logging.info(f"成功连接应用程序: {self.main_window.window_text()}")
            return True, f"成功连接: {self.main_window.window_text()}"
            
        except Exception as e:
            logging.error(f"连接应用程序失败: {e}")
            return False, str(e)
    
    def launch_application(self, exe_path: str, timeout: int = 10) -> Tuple[bool, str]:
        if not PYWINAUTO_AVAILABLE:
            return False, "pywinauto未安装，无法启动应用程序"
        
        try:
            self.app = Application(backend="uia").start(exe_path)
            
            time.sleep(2)
            
            for i in range(timeout):
                try:
                    self.main_window = self.app.top_window()
                    if self.main_window:
                        self.current_window = self.main_window
                        logging.info(f"成功启动应用程序: {exe_path}")
                        return True, f"成功启动: {exe_path}"
                except:
                    time.sleep(1)
            
            return False, f"启动超时: {exe_path}"
            
        except Exception as e:
            logging.error(f"启动应用程序失败: {e}")
            return False, str(e)
    
    def find_control(self, locator_config: Dict, timeout: int = 10) -> Tuple[Optional[Any], str]:
        if not PYWINAUTO_AVAILABLE:
            return None, "pywinauto未安装"
        
        try:
            locator_type = locator_config.get('locator_type', 'uia')
            
            for retry in range(timeout):
                try:
                    control = None
                    
                    if locator_type == LocatorType.UIA.value:
                        control = self._find_by_uia(locator_config)
                    elif locator_type == LocatorType.NAME.value:
                        control = self._find_by_name(locator_config)
                    elif locator_type == LocatorType.CONTROL_TYPE.value:
                        control = self._find_by_control_type(locator_config)
                    elif locator_type == LocatorType.AUTOMATION_ID.value:
                        control = self._find_by_automation_id(locator_config)
                    
                    if control:
                        return control, ""
                    
                except Exception as e:
                    logging.debug(f"查找控件失败(尝试{retry+1}): {e}")
                    time.sleep(1)
            
            return None, f"未找到控件: {locator_config}"
            
        except Exception as e:
            logging.error(f"查找控件异常: {e}")
            return None, str(e)
    
    def _find_by_uia(self, locator_config: Dict) -> Optional[Any]:
        control_type = locator_config.get('control_type', '')
        name = locator_config.get('name', '')
        automation_id = locator_config.get('automation_id', '')
        class_name = locator_config.get('class_name', '')
        
        criteria = {}
        if control_type:
            criteria['control_type'] = control_type
        if name:
            criteria['title'] = name
        if automation_id:
            criteria['automation_id'] = automation_id
        if class_name:
            criteria['class_name'] = class_name
        
        if not criteria:
            return None
        
        return self.current_window.child_window(**criteria)
    
    def _find_by_name(self, locator_config: Dict) -> Optional[Any]:
        name = locator_config.get('name', '')
        if not name:
            return None
        
        return self.current_window.child_window(title=name)
    
    def _find_by_control_type(self, locator_config: Dict) -> Optional[Any]:
        control_type = locator_config.get('control_type', '')
        if not control_type:
            return None
        
        return self.current_window.child_window(control_type=control_type)
    
    def _find_by_automation_id(self, locator_config: Dict) -> Optional[Any]:
        automation_id = locator_config.get('automation_id', '')
        if not automation_id:
            return None
        
        return self.current_window.child_window(automation_id=automation_id)
    
    def click_control(self, control: Any) -> Tuple[bool, str]:
        try:
            control.click()
            logging.info(f"点击控件成功")
            return True, ""
        except Exception as e:
            logging.error(f"点击控件失败: {e}")
            return False, str(e)
    
    def input_text(self, control: Any, text: str, clear_first: bool = True) -> Tuple[bool, str]:
        try:
            if clear_first:
                control.set_text("")
            control.set_text(text)
            logging.info(f"输入文本成功: {text}")
            return True, ""
        except Exception as e:
            logging.error(f"输入文本失败: {e}")
            return False, str(e)
    
    def read_text(self, control: Any) -> Tuple[str, str]:
        try:
            text = control.window_text()
            logging.info(f"读取文本成功: {text}")
            return text, ""
        except Exception as e:
            logging.error(f"读取文本失败: {e}")
            return "", str(e)
    
    def wait_window(self, window_title: str, timeout: int = 10) -> Tuple[bool, str]:
        try:
            for i in range(timeout):
                try:
                    window = self.app.window(title_re=window_title)
                    if window.exists():
                        self.current_window = window
                        logging.info(f"等待窗口成功: {window_title}")
                        return True, ""
                except:
                    time.sleep(1)
            
            return False, f"等待窗口超时: {window_title}"
            
        except Exception as e:
            logging.error(f"等待窗口失败: {e}")
            return False, str(e)
    
    def take_screenshot(self, save_path: str) -> Tuple[bool, str]:
        try:
            if self.current_window:
                self.current_window.capture_as_image().save(save_path)
                logging.info(f"截图成功: {save_path}")
                return True, save_path
            return False, "没有当前窗口"
        except Exception as e:
            logging.error(f"截图失败: {e}")
            return False, str(e)


from enum import Enum