import logging
import uuid
from datetime import datetime
from typing import Dict, List, Tuple

import pymysql

from app.storage.database import Database


class JyStockQueryService:
    
    def __init__(self, db: Database):
        self.db = db
    
    def get_db_configs(self) -> List[Dict]:
        try:
            conn = self.db.get_connection()
            cursor = conn.cursor()
            
            cursor.execute('''
                SELECT id, name, host, port, username, password, database_name, stock_query_sql as inbound_sql
                FROM db_configs
                WHERE enabled = 1
                ORDER BY name
            ''')
            
            rows = cursor.fetchall()
            
            configs = []
            for row in rows:
                configs.append(dict(row))
            
            return configs
            
        except Exception as e:
            logging.error(f"获取数据库配置列表失败: {e}")
            return []
    
    def test_connection(self, config_id: int) -> Tuple[bool, str]:
        try:
            conn = self.db.get_connection()
            cursor = conn.cursor()
            
            cursor.execute('''
                SELECT host, port, username, password, database_name
                FROM db_configs
                WHERE id = ?
            ''', (config_id,))
            
            row = cursor.fetchone()
            if not row:
                return False, "数据库配置不存在"
            
            config = dict(row)
            
            mysql_conn = pymysql.connect(
                host=config['host'],
                port=config['port'],
                user=config['username'],
                password=config['password'],
                database=config['database_name'],
                charset='utf8mb4',
                connect_timeout=10
            )
            
            mysql_conn.close()
            
            return True, "连接成功"
            
        except Exception as e:
            logging.error(f"测试数据库连接失败: {e}")
            return False, str(e)
    
    def query_stock(self, config_id: int, batch_id: str, custom_sql: str = None) -> Tuple[int, int, str]:
        try:
            conn = self.db.get_connection()
            cursor = conn.cursor()
            
            cursor.execute('''
                SELECT host, port, username, password, database_name, stock_query_sql as inbound_sql
                FROM db_configs
                WHERE id = ?
            ''', (config_id,))
            
            row = cursor.fetchone()
            if not row:
                return 0, 0, "数据库配置不存在"
            
            config = dict(row)
            
            mysql_conn = pymysql.connect(
                host=config['host'],
                port=config['port'],
                user=config['username'],
                password=config['password'],
                database=config['database_name'],
                charset='utf8mb4',
                connect_timeout=30
            )
            mysql_cursor = mysql_conn.cursor()
            
            sql = custom_sql if custom_sql else config['inbound_sql']
            
            if not sql:
                mysql_conn.close()
                return 0, 0, "SQL查询语句为空"
            
            mysql_cursor.execute(sql)
            
            columns = [desc[0] for desc in mysql_cursor.description]
            
            now = datetime.now().isoformat()
            query_count = 0
            
            for row_data in mysql_cursor.fetchall():
                row_dict = dict(zip(columns, row_data))
                
                oldproductno = str(row_dict.get('药品编码', row_dict.get('oldproductno', ''))).strip()
                productname = str(row_dict.get('药品名称', row_dict.get('productname', ''))).strip()
                lotno = str(row_dict.get('批号', row_dict.get('lotno', ''))).strip()
                
                try:
                    jy_quantity = float(row_dict.get('库存数量', row_dict.get('jy_quantity', 0)))
                except (ValueError, TypeError):
                    jy_quantity = 0.0
                
                warehouse = str(row_dict.get('仓库', row_dict.get('warehouse', ''))).strip()
                valid_date = str(row_dict.get('有效期', row_dict.get('valid_date', ''))).strip()
                specification = str(row_dict.get('规格', row_dict.get('Specification', row_dict.get('specification', '')))).strip()
                approval_number = str(row_dict.get('批准文号', row_dict.get('ApprovalNo', row_dict.get('approval_number', '')))).strip()
                
                if not oldproductno:
                    continue
                
                query_id = uuid.uuid4().hex
                
                cursor.execute('''
                    INSERT INTO jy_stock_query
                    (query_id, batch_id, oldproductno, productname, lotno, jy_quantity, warehouse, valid_date, specification, approval_number, query_time, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (
                    query_id,
                    batch_id,
                    oldproductno,
                    productname,
                    lotno,
                    jy_quantity,
                    warehouse,
                    valid_date,
                    specification,
                    approval_number,
                    now,
                    now
                ))
                
                query_count += 1
            
            mysql_conn.close()
            
            conn.commit()
            
            logging.info(f"君元库存查询成功，批次号: {batch_id}, 查询记录数: {query_count}")
            
            return query_count, 0, ""
            
        except Exception as e:
            logging.error(f"查询君元库存失败: {e}")
            return 0, 0, str(e)
    
    def get_query_results(self, batch_id: str) -> List[Dict]:
        try:
            conn = self.db.get_connection()
            cursor = conn.cursor()
            
            cursor.execute('''
                SELECT query_id, oldproductno, productname, lotno, jy_quantity, warehouse, valid_date, specification, approval_number, query_time
                FROM jy_stock_query
                WHERE batch_id = ?
                ORDER BY oldproductno, lotno
            ''', (batch_id,))
            
            rows = cursor.fetchall()
            
            results = []
            for row in rows:
                results.append(dict(row))
            
            return results
            
        except Exception as e:
            logging.error(f"获取查询结果失败: {e}")
            return []
    
    def get_query_results_with_filter(self, batch_id: str, oldproductno: str = None, productname: str = None, lotno: str = None) -> List[Dict]:
        try:
            conn = self.db.get_connection()
            cursor = conn.cursor()
            
            sql = '''
                SELECT query_id, oldproductno, productname, lotno, jy_quantity, warehouse, valid_date, specification, approval_number, query_time
                FROM jy_stock_query
                WHERE batch_id = ?
            '''
            params = [batch_id]
            
            if oldproductno:
                sql += " AND oldproductno LIKE ?"
                params.append(f"%{oldproductno}%")
            
            if productname:
                sql += " AND productname LIKE ?"
                params.append(f"%{productname}%")
            
            if lotno:
                sql += " AND lotno LIKE ?"
                params.append(f"%{lotno}%")
            
            sql += " ORDER BY oldproductno, lotno"
            
            cursor.execute(sql, params)
            
            rows = cursor.fetchall()
            
            results = []
            for row in rows:
                results.append(dict(row))
            
            return results
            
        except Exception as e:
            logging.error(f"获取查询结果失败: {e}")
            return []
    
    def clear_query_results(self, batch_id: str) -> Tuple[bool, str]:
        try:
            conn = self.db.get_connection()
            cursor = conn.cursor()
            
            cursor.execute('DELETE FROM jy_stock_query WHERE batch_id = ?', (batch_id,))
            
            conn.commit()
            
            return True, ""
            
        except Exception as e:
            logging.error(f"清除查询结果失败: {e}")
            return False, str(e)