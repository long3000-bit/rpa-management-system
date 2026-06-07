import pymysql
from pymysql.cursors import DictCursor
from typing import Optional
from dataclasses import dataclass
import re
import logging
from datetime import datetime


@dataclass
class DbConfig:
    id: int = 0
    name: str = ""
    db_type: str = "mysql"
    host: str = ""
    port: int = 3306
    database_name: str = ""
    username: str = ""
    password: str = ""
    charset: str = "utf8mb4"
    timeout: int = 30
    enabled: bool = True
    inbound_sql: str = ""
    stock_query_sql: str = ""
    created_at: str = ""
    updated_at: str = ""


class DatabaseConfigService:
    
    def __init__(self, db):
        self.db = db
        self._ensure_tables()
    
    def _ensure_tables(self):
        conn = self.db.get_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS db_configs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                db_type TEXT DEFAULT 'mysql',
                host TEXT NOT NULL,
                port INTEGER DEFAULT 3306,
                database_name TEXT NOT NULL,
                username TEXT NOT NULL,
                password TEXT,
                charset TEXT DEFAULT 'utf8mb4',
                timeout INTEGER DEFAULT 30,
                enabled INTEGER DEFAULT 1,
                inbound_sql TEXT,
                stock_query_sql TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
        ''')
        
        self._ensure_db_config_columns(cursor)
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS reconciliation_tasks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                task_id TEXT NOT NULL,
                ysb_file TEXT,
                account_period_start TEXT,
                account_period_end TEXT,
                inbound_query_start TEXT,
                inbound_query_end TEXT,
                db_config_id INTEGER,
                status TEXT DEFAULT 'pending',
                result_file TEXT,
                ysb_row_count INTEGER DEFAULT 0,
                inbound_row_count INTEGER DEFAULT 0,
                matched_count INTEGER DEFAULT 0,
                diff_count INTEGER DEFAULT 0,
                started_at TEXT,
                finished_at TEXT,
                error_message TEXT,
                created_at TEXT NOT NULL
            )
        ''')
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS reconciliation_rules (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                quantity_mode TEXT DEFAULT 'net',
                price_tolerance REAL DEFAULT 0.01,
                amount_tolerance REAL DEFAULT 0.01,
                match_priority TEXT DEFAULT 'barcode,code,name',
                check_supplier INTEGER DEFAULT 0,
                check_batch_no INTEGER DEFAULT 0,
                check_expiry_date INTEGER DEFAULT 0,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
        ''')
        
        conn.commit()
    
    def _ensure_db_config_columns(self, cursor):
        cursor.execute("PRAGMA table_info(db_configs)")
        columns = {row['name'] for row in cursor.fetchall()}
        
        fields_to_add = {
            'db_type': "TEXT DEFAULT 'mysql'",
            'password': "TEXT DEFAULT ''",
            'charset': "TEXT DEFAULT 'utf8mb4'",
            'timeout': "INTEGER DEFAULT 30",
            'enabled': "INTEGER DEFAULT 1",
            'inbound_sql': "TEXT DEFAULT ''",
            'stock_query_sql': "TEXT DEFAULT ''",
        }
        
        for field_name, field_type in fields_to_add.items():
            if field_name not in columns:
                cursor.execute(f"ALTER TABLE db_configs ADD COLUMN {field_name} {field_type}")
                logging.info(f"✓ 为 db_configs 表添加 {field_name} 字段")
    
    def get_all_configs(self) -> list[DbConfig]:
        conn = self.db.get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM db_configs WHERE enabled = 1 ORDER BY name")
        rows = cursor.fetchall()
        return [self._row_to_config(row) for row in rows]
    
    def get_config_by_id(self, config_id: int) -> Optional[DbConfig]:
        conn = self.db.get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM db_configs WHERE id = ?", (config_id,))
        row = cursor.fetchone()
        return self._row_to_config(row) if row else None
    
    def save_config(self, config: DbConfig) -> int:
        conn = self.db.get_connection()
        cursor = conn.cursor()
        now = datetime.now().isoformat()
        
        if config.id and config.id > 0:
            cursor.execute('''
                UPDATE db_configs SET 
                    name = ?, host = ?, port = ?, database_name = ?,
                    username = ?, password = ?, charset = ?, timeout = ?,
                    inbound_sql = ?, stock_query_sql = ?, updated_at = ?
                WHERE id = ?
            ''', (
                config.name, config.host, config.port, config.database_name,
                config.username, config.password, config.charset, config.timeout,
                config.inbound_sql, config.stock_query_sql, now, config.id
            ))
            conn.commit()
            return config.id
        else:
            cursor.execute('''
                INSERT INTO db_configs (name, db_type, host, port, database_name,
                    username, password, charset, timeout, enabled, inbound_sql, 
                    stock_query_sql, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?, ?, ?)
            ''', (
                config.name, config.db_type, config.host, config.port, 
                config.database_name, config.username, config.password,
                config.charset, config.timeout, config.inbound_sql, 
                config.stock_query_sql, now, now
            ))
            conn.commit()
            return cursor.lastrowid
    
    def delete_config(self, config_id: int):
        conn = self.db.get_connection()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM db_configs WHERE id = ?", (config_id,))
        conn.commit()
    
    def _row_to_config(self, row) -> DbConfig:
        row_keys = set(row.keys())
        
        def value(key, default=""):
            if key not in row_keys:
                return default
            return row[key] if row[key] is not None else default
        
        return DbConfig(
            id=value('id', 0),
            name=value('name', ''),
            db_type=value('db_type', 'mysql'),
            host=value('host', ''),
            port=value('port', 3306),
            database_name=value('database_name', ''),
            username=value('username', ''),
            password=value('password', ''),
            charset=value('charset', 'utf8mb4'),
            timeout=value('timeout', 30),
            enabled=bool(value('enabled', 1)),
            inbound_sql=value('inbound_sql', ''),
            stock_query_sql=value('stock_query_sql', ''),
            created_at=value('created_at', ''),
            updated_at=value('updated_at', '')
        )
    
    def test_connection(self, config: DbConfig) -> tuple[bool, str]:
        try:
            conn = pymysql.connect(
                host=config.host,
                port=config.port,
                user=config.username,
                password=config.password,
                database=config.database_name,
                charset=config.charset,
                connect_timeout=config.timeout,
                cursorclass=DictCursor
            )
            conn.close()
            return True, "连接成功"
        except pymysql.Error as e:
            return False, f"连接失败: {str(e)}"
        except Exception as e:
            return False, f"连接失败: {str(e)}"


class InboundQueryService:
    
    DANGEROUS_KEYWORDS = ['INSERT', 'UPDATE', 'DELETE', 'DROP', 'TRUNCATE', 'ALTER', 'CREATE']
    
    def __init__(self, db_config: DbConfig):
        self.db_config = db_config
        self.connection = None
    
    def validate_sql(self, sql: str) -> tuple[bool, str]:
        sql_upper = sql.upper().strip()
        
        if not sql_upper.startswith('SELECT'):
            return False, "SQL必须以SELECT开头"
        
        for keyword in self.DANGEROUS_KEYWORDS:
            if keyword in sql_upper:
                return False, f"SQL包含禁止的关键字: {keyword}"
        
        if ';' in sql.rstrip(';'):
            return False, "禁止执行多条SQL语句"
        
        return True, "SQL校验通过"
    
    def connect(self) -> tuple[bool, str]:
        try:
            self.connection = pymysql.connect(
                host=self.db_config.host,
                port=self.db_config.port,
                user=self.db_config.username,
                password=self.db_config.password,
                database=self.db_config.database_name,
                charset=self.db_config.charset,
                connect_timeout=self.db_config.timeout,
                cursorclass=DictCursor
            )
            return True, "连接成功"
        except Exception as e:
            return False, str(e)
    
    def close(self):
        if self.connection:
            self.connection.close()
            self.connection = None
    
    def preview(self, sql: str, start_date: str, end_date: str, limit: int = 20) -> tuple[list[dict], str]:
        valid, msg = self.validate_sql(sql)
        if not valid:
            return [], msg
        
        connected, conn_msg = self.connect()
        if not connected:
            return [], conn_msg
        
        try:
            cursor = self.connection.cursor()
            
            formatted_sql = sql.replace('{start_date}', start_date).replace('{end_date}', end_date)
            formatted_sql = formatted_sql.replace(':start_date', start_date).replace(':end_date', end_date)
            
            logging.info(f"===========================================")
            logging.info(f"SQL预览 - 查询参数:")
            logging.info(f"  开始日期: {start_date}")
            logging.info(f"  结束日期: {end_date}")
            logging.info(f"  显示模式: 全部数据 (无限制)")
            logging.info(f"执行预览SQL:\n{formatted_sql}")
            logging.info(f"===========================================")
            
            cursor.execute(formatted_sql)
            rows = cursor.fetchall()
            
            result_list = list(rows)
            
            date_fields = ['inbound_date', 'date_opr', 'purchase_time', '入库日期']
            filtered_list = []
            out_of_range_count = 0
            
            for row in result_list:
                is_in_range = False
                for field in date_fields:
                    if field in row and row[field]:
                        try:
                            row_date = str(row[field])[:10]
                            if start_date <= row_date <= end_date:
                                is_in_range = True
                            break
                        except:
                            pass
                
                if is_in_range:
                    filtered_list.append(row)
                else:
                    out_of_range_count += 1
            
            if out_of_range_count > 0:
                logging.warning(f"⚠️ 预览数据日期过滤: 原始 {len(result_list)} 条, 有效 {len(filtered_list)} 条 (移除 {out_of_range_count} 条)")
            
            final_result = filtered_list[:limit] if limit else filtered_list
            
            logging.info(f"✓ SQL预览完成: 返回 {len(final_result)} 条数据 (范围: {start_date} ~ {end_date})")
            return final_result, ""
        except Exception as e:
            logging.error(f"SQL预览失败: {e}")
            return [], str(e)
        finally:
            self.close()
    
    def query_all(self, sql: str, start_date: str, end_date: str) -> tuple[list[dict], str]:
        valid, msg = self.validate_sql(sql)
        if not valid:
            return [], msg
        
        connected, conn_msg = self.connect()
        if not connected:
            return [], conn_msg
        
        try:
            cursor = self.connection.cursor()
            
            formatted_sql = sql.replace('{start_date}', start_date).replace('{end_date}', end_date)
            formatted_sql = formatted_sql.replace(':start_date', start_date).replace(':end_date', end_date)
            
            logging.info(f"===========================================")
            logging.info(f"入库查询参数:")
            logging.info(f"  开始日期: {start_date}")
            logging.info(f"  结束日期: {end_date}")
            logging.info(f"执行入库查询SQL:\n{formatted_sql}")
            logging.info(f"===========================================")
            
            cursor.execute(formatted_sql)
            rows = cursor.fetchall()
            
            result_list = list(rows)
            original_count = len(result_list)
            
            date_fields = ['inbound_date', 'date_opr', 'purchase_time', '入库日期']
            filtered_list = []
            out_of_range_count = 0
            
            for row in result_list:
                is_in_range = False
                for field in date_fields:
                    if field in row and row[field]:
                        try:
                            row_date = str(row[field])[:10]
                            if start_date <= row_date <= end_date:
                                is_in_range = True
                            break
                        except:
                            pass
                
                if is_in_range:
                    filtered_list.append(row)
                else:
                    out_of_range_count += 1
            
            if out_of_range_count > 0:
                logging.warning(f"⚠️ 日期过滤: 原始数据 {original_count} 条, 过滤后 {len(filtered_list)} 条")
                logging.warning(f"⚠️ 移除 {out_of_range_count} 条不在 {start_date} 至 {end_date} 范围内的记录")
                
                if original_count == out_of_range_count:
                    logging.error("❌ 所有数据都被过滤掉了！请检查：")
                    logging.error("   1. SQL语句中是否包含正确的日期过滤条件")
                    logging.error("   2. 日期字段名是否正确（inbound_date/date_opr/purchase_time）")
                    logging.error("   3. 查询的数据库表中是否有该时间段的数据")
                else:
                    sample_out = [row for row in result_list[:3] if row not in filtered_list[:3]]
                    for idx, row in enumerate(sample_out[:2]):
                        for field in date_fields:
                            if field in row and row[field]:
                                logging.warning(f"   被过滤样例{idx+1}: {field}={row[field]}")
                                break
            
            logging.info(f"✓ 入库查询完成: 返回 {len(filtered_list)} 条有效数据 (范围: {start_date} ~ {end_date})")
            return filtered_list, ""
        except Exception as e:
            logging.error(f"入库查询失败: {e}")
            return [], str(e)
        finally:
            self.close()
