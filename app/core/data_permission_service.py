"""
数据权限服务（第四阶段：数据权限扩展）

实现数据过滤逻辑：
- 店长只能查看自己创建的数据
- 系统管理员可以查看所有数据
"""
import logging
from typing import Optional, List, Dict, Any
from app.storage.database import Database


class DataPermissionService:
    """数据权限服务"""
    
    # 系统管理员角色代码
    SYSTEM_ADMIN_ROLE = 'system_admin'
    
    # 需要数据过滤的表及其创建人字段
    DATA_FILTER_TABLES = {
        'ysb_import_batches': 'imported_by',
        'reconciliation_tasks': 'created_by',
        'rpa_import_batches': 'imported_by',
        'rpa_tasks': 'created_by',
        'yys_import_batch': 'imported_by',
        'stock_compare_result': 'created_by',
        'yys_sync_task': 'created_by',
        'smart_purchase_batches': 'created_by',
    }
    
    # 各表的默认排序字段
    DEFAULT_ORDER_FIELDS = {
        'ysb_import_batches': 'imported_at DESC',
        'reconciliation_tasks': 'created_at DESC',
        'rpa_import_batches': 'imported_at DESC',
        'rpa_tasks': 'created_at DESC',
        'yys_import_batch': 'imported_at DESC',
        'stock_compare_result': 'created_at DESC',
        'yys_sync_task': 'created_at DESC',
        'smart_purchase_batches': 'imported_at DESC',
    }
    
    def __init__(self, db: Database):
        self.db = db
    
    def is_system_admin(self, role_code: str) -> bool:
        """检查是否为系统管理员"""
        return role_code == self.SYSTEM_ADMIN_ROLE
    
    def get_data_filter_condition(self, table_name: str, role_code: str, username: str) -> Dict[str, Any]:
        """
        获取数据过滤条件
        
        Args:
            table_name: 表名
            role_code: 用户角色代码
            username: 用户名
            
        Returns:
            Dict包含:
            - filter_sql: SQL过滤条件（如 "created_by = ?" 或 ""）
            - filter_params: 过滤参数列表
            - needs_filter: 是否需要过滤
        """
        # 系统管理员不需要过滤
        if self.is_system_admin(role_code):
            return {
                'filter_sql': '',
                'filter_params': [],
                'needs_filter': False
            }
        
        # 检查表是否需要过滤
        creator_field = self.DATA_FILTER_TABLES.get(table_name)
        if not creator_field:
            return {
                'filter_sql': '',
                'filter_params': [],
                'needs_filter': False
            }
        
        # 店长只能查看自己创建的数据
        return {
            'filter_sql': f"{creator_field} = ?",
            'filter_params': [username],
            'needs_filter': True
        }
    
    def apply_data_filter_to_query(
        self, 
        base_query: str, 
        table_name: str, 
        role_code: str, 
        username: str,
        existing_where: bool = False
    ) -> tuple:
        """
        将数据过滤条件应用到查询
        
        Args:
            base_query: 基础SQL查询
            table_name: 表名
            role_code: 用户角色代码
            username: 用户名
            existing_where: 是否已有WHERE条件
            
        Returns:
            tuple: (修改后的查询, 参数列表)
        """
        filter_info = self.get_data_filter_condition(table_name, role_code, username)
        
        if not filter_info['needs_filter']:
            return base_query, []
        
        # 添加过滤条件到查询
        if existing_where:
            modified_query = f"{base_query} AND {filter_info['filter_sql']}"
        else:
            modified_query = f"{base_query} WHERE {filter_info['filter_sql']}"
        
        return modified_query, filter_info['filter_params']
    
    def get_filtered_batches(
        self, 
        table_name: str, 
        role_code: str, 
        username: str,
        additional_conditions: str = "",
        order_by: str = None
    ) -> List[Dict]:
        """
        获取过滤后的批次数据
        
        Args:
            table_name: 表名
            role_code: 用户角色代码
            username: 用户名
            additional_conditions: 额外的WHERE条件
            order_by: 排序条件（如果为None，使用表的默认排序）
            
        Returns:
            List[Dict]: 过滤后的数据列表
        """
        conn = self.db.get_connection()
        cursor = conn.cursor()
        
        # 使用默认排序字段（如果未指定）
        if order_by is None:
            order_by = self.DEFAULT_ORDER_FIELDS.get(table_name, 'created_at DESC')
        
        # 构建基础查询
        query = f"SELECT * FROM {table_name}"
        params = []
        
        # 应用数据权限过滤
        has_additional = additional_conditions.strip() != ""
        query, filter_params = self.apply_data_filter_to_query(
            query, table_name, role_code, username, has_additional
        )
        params.extend(filter_params)
        
        # 添加额外条件
        if has_additional:
            if filter_params:
                query = f"{query} AND {additional_conditions}"
            else:
                query = f"{query} WHERE {additional_conditions}"
        
        # 添加排序
        query = f"{query} ORDER BY {order_by}"
        
        cursor.execute(query, params)
        rows = cursor.fetchall()
        
        return [dict(row) for row in rows]
    
    def get_batch_count(
        self, 
        table_name: str, 
        role_code: str, 
        username: str,
        additional_conditions: str = ""
    ) -> int:
        """
        获取过滤后的批次数量
        
        Args:
            table_name: 表名
            role_code: 用户角色代码
            username: 用户名
            additional_conditions: 额外的WHERE条件
            
        Returns:
            int: 数据数量
        """
        conn = self.db.get_connection()
        cursor = conn.cursor()
        
        # 构建基础查询
        query = f"SELECT COUNT(*) as count FROM {table_name}"
        params = []
        
        # 应用数据权限过滤
        has_additional = additional_conditions.strip() != ""
        query, filter_params = self.apply_data_filter_to_query(
            query, table_name, role_code, username, has_additional
        )
        params.extend(filter_params)
        
        # 添加额外条件
        if has_additional:
            if filter_params:
                query = f"{query} AND {additional_conditions}"
            else:
                query = f"{query} WHERE {additional_conditions}"
        
        cursor.execute(query, params)
        result = cursor.fetchone()
        
        return result['count'] if result else 0
    
    def can_access_batch(
        self, 
        table_name: str, 
        batch_id: str, 
        role_code: str, 
        username: str
    ) -> bool:
        """
        检查用户是否可以访问特定批次
        
        Args:
            table_name: 表名
            batch_id: 批次ID
            role_code: 用户角色代码
            username: 用户名
            
        Returns:
            bool: 是否可以访问
        """
        # 系统管理员可以访问所有数据
        if self.is_system_admin(role_code):
            return True
        
        conn = self.db.get_connection()
        cursor = conn.cursor()
        
        # 获取批次的创建人字段
        creator_field = self.DATA_FILTER_TABLES.get(table_name)
        if not creator_field:
            return True
        
        # 获取批次的主键字段
        pk_field = self._get_primary_key_field(table_name)
        
        # 查询批次的创建人
        cursor.execute(
            f"SELECT {creator_field} FROM {table_name} WHERE {pk_field} = ?",
            (batch_id,)
        )
        row = cursor.fetchone()
        
        if not row:
            return False
        
        # 检查创建人是否为当前用户
        return row[creator_field] == username
    
    def _get_primary_key_field(self, table_name: str) -> str:
        """获取表的主键字段名"""
        pk_fields = {
            'ysb_import_batches': 'batch_id',
            'reconciliation_tasks': 'task_id',
            'rpa_import_batches': 'import_batch_id',
            'rpa_tasks': 'task_id',
            'yys_import_batch': 'batch_id',
            'stock_compare_result': 'result_id',
            'yys_sync_task': 'task_id',
            'smart_purchase_batches': 'batch_id',
        }
        return pk_fields.get(table_name, 'id')
    
    def set_batch_creator(
        self, 
        table_name: str, 
        batch_id: str, 
        username: str
    ) -> bool:
        """
        设置批次的创建人
        
        Args:
            table_name: 表名
            batch_id: 批次ID
            username: 创建人用户名
            
        Returns:
            bool: 是否成功
        """
        conn = self.db.get_connection()
        cursor = conn.cursor()
        
        creator_field = self.DATA_FILTER_TABLES.get(table_name)
        if not creator_field:
            return False
        
        pk_field = self._get_primary_key_field(table_name)
        
        try:
            cursor.execute(
                f"UPDATE {table_name} SET {creator_field} = ? WHERE {pk_field} = ?",
                (username, batch_id)
            )
            conn.commit()
            return True
        except Exception as e:
            logging.error(f"Failed to set batch creator: {e}")
            conn.rollback()
            return False