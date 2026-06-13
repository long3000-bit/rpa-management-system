"""
医保价格管控 - 君元销售价格SQL抓取服务

通过SQL查询获取君元当前销售价格数据
"""

import logging
import json
import uuid
from datetime import datetime
from typing import Optional, Dict, List, Any
from dataclasses import dataclass, field

import pymysql
from pymysql.cursors import DictCursor

from app.storage.database import Database
from app.core.database_config_service import DatabaseConfigService


@dataclass
class JunyuanPriceFetchResult:
    """价格抓取结果"""
    batch_id: str
    total_count: int = 0
    success_count: int = 0
    failed_count: int = 0
    fetch_status: str = "pending"
    error_message: str = ""
    fetch_time: str = ""


class JunyuanPriceFetchService:
    """君元销售价格抓取服务"""
    
    # 默认SQL查询语句
    DEFAULT_SQL_TEMPLATE = """
        SELECT 
            商品编码,
            商品名称,
            规格,
            剂型,
            包装规格,
            生产厂家,
            销售价,
            包装价,
            单片价,
            拆零价,
            库存数量,
            价格类型,
            价格更新时间
        FROM 商品价格表
        WHERE 商品状态 = '正常'
        ORDER BY 商品编码
    """
    
    def __init__(self, db: Database):
        self.db = db
        self.db_config_service = DatabaseConfigService(db)
    
    def generate_batch_id(self) -> str:
        """生成批次ID"""
        return f"JY_PRICE_{datetime.now().strftime('%Y%m%d%H%M%S')}_{uuid.uuid4().hex[:8]}"
    
    def fetch_junyuan_prices(
        self,
        db_config_id: int = None,
        custom_sql: str = None,
        imported_by: str = "admin"
    ) -> JunyuanPriceFetchResult:
        """抓取君元销售价格"""
        batch_id = self.generate_batch_id()
        result = JunyuanPriceFetchResult(
            batch_id=batch_id,
            fetch_time=datetime.now().isoformat()
        )
        
        try:
            # 获取数据库配置
            if db_config_id:
                db_config = self.db_config_service.get_config_by_id(db_config_id)
            else:
                # 使用默认配置（第一个配置）
                configs = self.db_config_service.get_all_configs()
                if not configs:
                    result.fetch_status = "failed"
                    result.error_message = "未找到数据库配置"
                    return result
                db_config = configs[0]
            
            # 连接数据库
            connection = pymysql.connect(
                host=db_config.host,
                port=db_config.port,
                user=db_config.username,
                password=db_config.password,
                database=db_config.database_name,
                charset='utf8mb4',
                cursorclass=DictCursor,
                connect_timeout=30
            )
            
            # 执行SQL查询
            sql = custom_sql or self.DEFAULT_SQL_TEMPLATE
            
            with connection.cursor() as cursor:
                cursor.execute(sql)
                rows = cursor.fetchall()
                
                # 保存抓取结果
                conn = self.db.get_connection()
                local_cursor = conn.cursor()
                now = datetime.now().isoformat()
                
                for row in rows:
                    try:
                        row_data = {k: str(v) if v is not None else "" for k, v in row.items()}
                        raw_data_json = json.dumps(row_data, ensure_ascii=False)
                        
                        local_cursor.execute('''
                            INSERT INTO junyuan_sales_price (
                                batch_id, 商品编码, 商品名称, 规格, 剂型, 包装规格,
                                生产厂家, 销售价, 包装价, 单片价, 拆零价, 库存数量, 价格类型,
                                价格更新时间, 抓取状态, 原始数据, created_at
                            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        ''', (
                            batch_id,
                            row_data.get("商品编码", ""),
                            row_data.get("商品名称", ""),
                            row_data.get("规格", ""),
                            row_data.get("剂型", ""),
                            row_data.get("包装规格", ""),
                            row_data.get("生产厂家", ""),
                            row_data.get("销售价", ""),
                            row_data.get("包装价", ""),
                            row_data.get("单片价", ""),
                            row_data.get("拆零价", ""),
                            row_data.get("库存数量", ""),
                            row_data.get("价格类型", ""),
                            row_data.get("价格更新时间", ""),
                            "success",
                            raw_data_json,
                            now
                        ))
                        
                        result.success_count += 1
                        
                    except Exception as e:
                        result.failed_count += 1
                        logging.warning(f"保存价格数据失败: {e}")
                
                conn.commit()
            
            connection.close()
            
            result.total_count = result.success_count + result.failed_count
            result.fetch_status = "success" if result.failed_count == 0 else "partial"
            
            # 记录批次
            self._save_batch_record(result, db_config_id, imported_by)
            
            logging.info(f"君元价格抓取完成: {result.success_count}/{result.total_count} 条")
            
        except Exception as e:
            result.fetch_status = "failed"
            result.error_message = str(e)
            logging.error(f"抓取君元价格失败: {e}")
        
        return result
    
    def _save_batch_record(
        self,
        result: JunyuanPriceFetchResult,
        db_config_id: int,
        imported_by: str
    ):
        """保存批次记录"""
        conn = self.db.get_connection()
        cursor = conn.cursor()
        now = datetime.now().isoformat()
        
        cursor.execute('''
            INSERT INTO medical_import_batches (
                batch_id, batch_type, file_name, total_rows, success_rows,
                failed_rows, import_status, imported_by, imported_at, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            result.batch_id,
            "junyuan_sales_price",
            f"SQL抓取_{result.fetch_time}",
            result.total_count,
            result.success_count,
            result.failed_count,
            result.fetch_status,
            imported_by,
            result.fetch_time,
            now
        ))
        
        conn.commit()
    
    def get_junyuan_price_batches(self, limit: int = 20) -> List[Dict]:
        """获取君元价格抓取批次列表"""
        conn = self.db.get_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT * FROM medical_import_batches
            WHERE batch_type = 'junyuan_sales_price'
            ORDER BY created_at DESC
            LIMIT ?
        ''', (limit,))
        
        return [dict(row) for row in cursor.fetchall()]
    
    def get_junyuan_prices_by_batch(self, batch_id: str) -> List[Dict]:
        """获取指定批次的价格数据"""
        conn = self.db.get_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT * FROM junyuan_sales_price
            WHERE batch_id = ?
            ORDER BY 商品编码
        ''', (batch_id,))
        
        return [dict(row) for row in cursor.fetchall()]
    
    def get_latest_junyuan_price_batch(self) -> Optional[Dict]:
        """获取最新的君元价格批次"""
        conn = self.db.get_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT * FROM medical_import_batches
            WHERE batch_type = 'junyuan_sales_price' AND import_status = 'success'
            ORDER BY created_at DESC
            LIMIT 1
        ''')
        
        row = cursor.fetchone()
        return dict(row) if row else None