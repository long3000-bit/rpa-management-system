"""
权限检查工具模块
提供权限检查装饰器和工具函数
"""
import logging
from functools import wraps
from typing import Callable, Optional

from PySide6.QtWidgets import QMessageBox, QWidget

from app.core.permission_service import PermissionService
from app.storage.database import Database


class PermissionChecker:
    """权限检查器"""
    
    def __init__(self, db: Database, username: str):
        self.db = db
        self.username = username
        self.permission_service = PermissionService(db)
    
    def check_permission(self, permission_code: str, parent_widget: QWidget = None) -> bool:
        """
        检查权限并显示提示
        
        Args:
            permission_code: 权限编码
            parent_widget: 父窗口（用于显示提示框）
        
        Returns:
            bool: 是否有权限
        """
        has_perm = self.permission_service.has_permission(self.username, permission_code)
        
        if not has_perm:
            # 记录无权限操作日志
            self.permission_service.log_operation(
                username=self.username,
                operation_type='permission_denied',
                operation_desc=f'尝试执行无权限操作: {permission_code}',
                target_type='permission',
                target_id=permission_code,
                detail={'permission_code': permission_code},
                permission_code=permission_code,
                result='denied'
            )
            
            # 显示提示
            if parent_widget:
                QMessageBox.warning(
                    parent_widget,
                    "权限不足",
                    f"您没有权限执行此操作\n权限编码: {permission_code}"
                )
            
            return False
        
        return True
    
    def check_permission_silent(self, permission_code: str) -> bool:
        """
        静默检查权限（不显示提示）
        
        Args:
            permission_code: 权限编码
        
        Returns:
            bool: 是否有权限
        """
        return self.permission_service.has_permission(self.username, permission_code)
    
    def require_permission(self, permission_code: str, parent_widget: QWidget = None) -> tuple:
        """
        检查权限并返回结果
        
        Args:
            permission_code: 权限编码
            parent_widget: 父窗口
        
        Returns:
            tuple: (success: bool, message: str)
        """
        success = self.check_permission(permission_code, parent_widget)
        message = "权限验证通过" if success else "无权限执行此操作"
        return success, message


def require_permission(permission_code: str):
    """
    权限检查装饰器
    
    使用示例:
        @require_permission('operation.user.create')
        def create_user(self):
            ...
    
    注意：此装饰器需要类有 self.permission_checker 属性
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(self, *args, **kwargs):
            # 检查是否有 permission_checker 属性
            if not hasattr(self, 'permission_checker'):
                logging.warning(f"{self.__class__.__name__} 没有 permission_checker 属性，跳过权限检查")
                return func(self, *args, **kwargs)
            
            # 检查权限
            checker = self.permission_checker
            if not checker.check_permission_silent(permission_code):
                # 记录日志
                checker.permission_service.log_operation(
                    username=checker.username,
                    operation_type='permission_denied',
                    operation_desc=f'尝试执行无权限操作: {permission_code}',
                    target_type='permission',
                    target_id=permission_code,
                    permission_code=permission_code,
                    result='denied'
                )
                
                # 显示提示
                QMessageBox.warning(
                    self if hasattr(self, 'show') else None,
                    "权限不足",
                    f"您没有权限执行此操作\n权限编码: {permission_code}"
                )
                return None
            
            # 执行原函数
            return func(self, *args, **kwargs)
        
        return wrapper
    
    return decorator


def check_and_execute(
    permission_checker: PermissionChecker,
    permission_code: str,
    callback: Callable,
    parent_widget: QWidget = None,
    *args,
    **kwargs
):
    """
    检查权限并执行回调函数
    
    Args:
        permission_checker: 权限检查器
        permission_code: 权限编码
        callback: 回调函数
        parent_widget: 父窗口
        *args: 回调函数参数
        **kwargs: 回调函数参数
    
    Returns:
        回调函数的返回值，或 None（无权限时）
    """
    if permission_checker.check_permission(permission_code, parent_widget):
        return callback(*args, **kwargs)
    return None


# 权限编码常量定义
class PermissionCodes:
    """权限编码常量"""
    
    # 菜单权限
    MENU_HOME = 'menu.home'
    MENU_RPA_ROBOT = 'menu.rpa_robot'
    MENU_SMART_PURCHASE = 'menu.smart_purchase'
    MENU_YYS_STOCK = 'menu.yys_stock'
    MENU_JY_STOCK = 'menu.jy_stock'
    MENU_STOCK_COMPARE = 'menu.stock_compare'
    MENU_YSB_RECONCILE = 'menu.ysb_reconcile'
    MENU_RECONCILIATION = 'menu.reconciliation'
    MENU_TASK_RECORD = 'menu.task_record'
    MENU_CONFIG_CENTER = 'menu.config_center'
    MENU_SETTINGS = 'menu.settings'
    MENU_DB_IMPORT = 'menu.db_import'
    MENU_EXE_CONFIG = 'menu.exe_config'
    MENU_USER_MANAGE = 'menu.user_manage'
    MENU_ROLE_PERMISSION = 'menu.role_permission'
    MENU_OPERATION_LOGS = 'menu.operation_logs'
    MENU_LOGS = 'menu.logs'
    
    # 用户管理操作权限
    OP_USER_CREATE = 'operation.user.create'
    OP_USER_UPDATE = 'operation.user.update'
    OP_USER_DISABLE = 'operation.user.disable'
    OP_USER_RESET_PASSWORD = 'operation.user.reset_password'
    OP_USER_UNLOCK = 'operation.user.unlock'
    
    # 角色管理操作权限
    OP_ROLE_ASSIGN_PERMISSIONS = 'operation.role.assign_permissions'
    
    # 配置管理操作权限
    OP_CONFIG_SAVE_DATABASE = 'operation.config.save_database'
    OP_CONFIG_SAVE_YYS_API = 'operation.config.save_yys_api'
    OP_CONFIG_SAVE_SUPPLIER_SCOPE = 'operation.config.save_supplier_scope'
    
    # 数据库导入操作权限
    OP_DB_IMPORT_RESTORE = 'operation.db.import_restore'
    
    # RPA执行操作权限
    OP_RPA_EXECUTE = 'operation.rpa.execute'
    
    # 智能采购操作权限
    OP_SMART_PURCHASE_IMPORT_EXCEL = 'operation.smart_purchase.import_excel'
    OP_SMART_PURCHASE_RUN_ONE_BY_ONE = 'operation.smart_purchase.run_one_by_one'
    OP_SMART_PURCHASE_RETRY_FAILED = 'operation.smart_purchase.retry_failed'
    OP_SMART_PURCHASE_CART_BACKFILL = 'operation.smart_purchase.cart_backfill'
    OP_SMART_PURCHASE_EXPORT_RESULT = 'operation.smart_purchase.export_result'
    
    # 药师帮对账操作权限
    OP_YSB_RECONCILE_IMPORT_EXCEL = 'operation.ysb_reconcile.import_excel'
    OP_YSB_RECONCILE_SUPPLIER_RECONCILE = 'operation.ysb_reconcile.supplier_reconcile'
    OP_YSB_RECONCILE_SUPPLIER_PRODUCT_RECONCILE = 'operation.ysb_reconcile.supplier_product_reconcile'
    OP_YSB_RECONCILE_EXPORT_RESULT = 'operation.ysb_reconcile.export_result'
    
    # 云药店库存同步操作权限
    OP_YYS_STOCK_IMPORT_EXCEL = 'operation.yys_stock.import_excel'
    OP_YYS_STOCK_QUERY_JY_STOCK = 'operation.yys_stock.query_jy_stock'
    OP_YYS_STOCK_COMPARE_STOCK = 'operation.yys_stock.compare_stock'
    OP_YYS_STOCK_TEST_API_SYNC = 'operation.yys_stock.test_api_sync'
    OP_YYS_STOCK_SYNC_DIFF = 'operation.yys_stock.sync_diff'
    
    # 操作日志查看权限
    OP_OPERATION_LOGS_VIEW = 'operation.operation_logs.view'
    
    # 操作日志管理权限
    OP_LOG_DELETE = 'operation.log.delete'
    OP_LOG_EXPORT = 'operation.log.export'
    
    # 库存对比导出权限
    OP_YYS_STOCK_EXPORT_RESULT = 'operation.yys_stock.export_result'