import uuid
import logging
import json
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Optional, List, Dict, Any

from app.storage.database import Database
from app.core.ysb_excel_reader import YsbExcelReader


class YsbDataImportService:
    
    def __init__(self, db: Database):
        self.db = db
    
    def check_existing_batch(
        self,
        file_path: str,
        sheet_name: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        conn = self.db.get_connection()
        cursor = conn.cursor()
        
        file_name = Path(file_path).name
        
        if sheet_name:
            cursor.execute('''
                SELECT batch_id, file_name, sheet_name, total_rows, imported_at
                FROM ysb_import_batches
                WHERE file_name = ? AND sheet_name = ? AND import_status = 'success'
                ORDER BY imported_at DESC
                LIMIT 1
            ''', (file_name, sheet_name))
        else:
            cursor.execute('''
                SELECT batch_id, file_name, sheet_name, total_rows, imported_at
                FROM ysb_import_batches
                WHERE file_name = ? AND import_status = 'success'
                ORDER BY imported_at DESC
                LIMIT 1
            ''', (file_name,))
        
        row = cursor.fetchone()
        
        if row:
            return {
                'batch_id': row['batch_id'],
                'file_name': row['file_name'],
                'sheet_name': row['sheet_name'],
                'total_rows': row['total_rows'],
                'imported_at': row['imported_at']
            }
        
        return None
    
    def import_from_excel(
        self,
        file_path: str,
        sheet_type: str = "auto",
        sheet_name: Optional[str] = None,
        imported_by: str = "admin",
        allow_duplicate: bool = False,
        account_year: Optional[int] = None,
        account_month: Optional[int] = None,
        progress_callback: Optional[callable] = None
    ) -> Dict[str, Any]:
        logging.info(f"===========================================")
        logging.info(f"开始导入药师帮数据到数据库")
        logging.info(f"  文件路径: {file_path}")
        logging.info(f"  工作表类型: {sheet_type}")
        logging.info(f"  工作表名称: {sheet_name}")
        logging.info(f"  核算年: {account_year}")
        logging.info(f"  核算月: {account_month}")
        logging.info(f"===========================================")
        
        if progress_callback:
            progress_callback(5, "检查重复导入...")
        
        if not allow_duplicate:
            existing = self.check_existing_batch(file_path, sheet_name)
            if existing:
                logging.warning(f"⚠️ 检测到重复导入")
                logging.warning(f"  已存在批次: {existing['batch_id']}")
                logging.warning(f"  导入时间: {existing['imported_at']}")
                return {
                    'success': False,
                    'error': 'duplicate',
                    'error_message': f"该文件已导入过（批次ID: {existing['batch_id'][:8]}...，导入时间: {existing['imported_at']}）",
                    'existing_batch': existing
                }
        
        if progress_callback:
            progress_callback(10, "读取Excel文件...")
        
        reader = YsbExcelReader(file_path, sheet_type=sheet_type, sheet_name=sheet_name)
        ysb_data = reader.read()
        
        if ysb_data.error_message:
            logging.error(f"❌ 读取Excel失败: {ysb_data.error_message}")
            return {
                'success': False,
                'error': ysb_data.error_message,
                'batch_id': None
            }
        
        batch_id = str(uuid.uuid4())
        file_name = Path(file_path).name
        now = datetime.now().isoformat()
        
        conn = self.db.get_connection()
        cursor = conn.cursor()
        
        try:
            if progress_callback:
                progress_callback(15, "删除旧数据...")
            
            if account_year and account_month:
                self._delete_old_data_by_account_period(cursor, account_year, account_month, sheet_type)
                logging.info(f"✓ 已删除核算年 {account_year} 核算月 {account_month} 的旧数据")
            
            if progress_callback:
                progress_callback(20, "创建导入批次...")
            
            cursor.execute('''
                INSERT INTO ysb_import_batches 
                (batch_id, file_name, file_path, sheet_type, sheet_name, 
                 total_rows, import_status, account_year, account_month, imported_at, imported_by)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                batch_id,
                file_name,
                file_path,
                ysb_data.sheet_type,
                ysb_data.sheet_name,
                len(ysb_data.items) if ysb_data.items else len(ysb_data.supplier_summaries) if ysb_data.supplier_summaries else 0,
                'importing',
                account_year,
                account_month,
                now,
                imported_by
            ))
            
            if ysb_data.items and len(ysb_data.items) > 0:
                detail_count = self._import_detail_data(
                    cursor, batch_id, file_name, ysb_data.sheet_name, 
                    ysb_data.items, now, progress_callback
                )
                logging.info(f"✓ 导入明细数据: {detail_count} 条")
            
            if ysb_data.supplier_summaries and len(ysb_data.supplier_summaries) > 0:
                supplier_count = self._import_supplier_summary(
                    cursor, batch_id, file_name, ysb_data.sheet_name,
                    ysb_data.supplier_summaries, now, progress_callback
                )
                logging.info(f"✓ 导入供应商汇总: {supplier_count} 条")
            
            if progress_callback:
                progress_callback(95, "提交数据...")
            
            cursor.execute('''
                UPDATE ysb_import_batches 
                SET import_status = 'success'
                WHERE batch_id = ?
            ''', (batch_id,))
            
            conn.commit()
            
            if progress_callback:
                progress_callback(100, "导入完成")
            
            logging.info(f"===========================================")
            logging.info(f"✓ 药师帮数据导入成功")
            logging.info(f"  批次ID: {batch_id}")
            logging.info(f"  文件名: {file_name}")
            logging.info(f"  工作表: {ysb_data.sheet_name}")
            logging.info(f"===========================================")
            
            return {
                'success': True,
                'batch_id': batch_id,
                'file_name': file_name,
                'sheet_name': ysb_data.sheet_name,
                'sheet_type': ysb_data.sheet_type,
                'total_rows': len(ysb_data.items) if ysb_data.items else len(ysb_data.supplier_summaries) if ysb_data.supplier_summaries else 0
            }
            
        except Exception as e:
            conn.rollback()
            logging.error(f"❌ 导入数据失败: {e}")
            import traceback
            logging.error(traceback.format_exc())
            
            return {
                'success': False,
                'error': str(e),
                'batch_id': batch_id
            }
    
    def _import_detail_data(
        self,
        cursor,
        batch_id: str,
        file_name: str,
        sheet_name: str,
        items: list,
        imported_at: str,
        progress_callback: Optional[callable] = None
    ) -> int:
        count = 0
        total = len(items)
        batch_size = 100
        
        for i, item in enumerate(items):
            raw_data_json = json.dumps(getattr(item, 'raw_data', {}), ensure_ascii=False) if hasattr(item, 'raw_data') else '{}'
            
            cursor.execute('''
                INSERT OR REPLACE INTO ysb_detail_data 
                (import_batch_id, file_name, sheet_name,
                 ysb_order_no, order_type, purchase_time,
                 ysb_store_name, ysb_supplier_name, ysb_company_name,
                 product_name, manufacturer, spec, unit,
                 approval_number, barcode, batch_no,
                 production_date, expiry_date,
                 unit_price, discount_price,
                 quantity, order_quantity, refund_quantity,
                 total_amount, discount_amount, actual_payment_amount, freight,
                 discount_amount_total,
                 raw_row_index, raw_data, imported_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                batch_id,
                file_name,
                sheet_name,
                getattr(item, 'ysb_order_no', ''),
                getattr(item, 'order_type', ''),
                str(getattr(item, 'purchase_time', '')),
                getattr(item, 'ysb_store_name', ''),
                getattr(item, 'ysb_supplier_name', ''),
                getattr(item, 'ysb_company_name', ''),
                getattr(item, 'product_name', ''),
                getattr(item, 'manufacturer', ''),
                getattr(item, 'spec', ''),
                getattr(item, 'unit', ''),
                getattr(item, 'approval_number', ''),
                getattr(item, 'barcode', ''),
                getattr(item, 'batch_no', ''),
                str(getattr(item, 'production_date', '')),
                str(getattr(item, 'expiry_date', '')),
                str(getattr(item, 'unit_price', Decimal("0"))),
                str(getattr(item, 'discount_price', Decimal("0"))),
                str(getattr(item, 'quantity', Decimal("0"))),
                str(getattr(item, 'order_quantity', Decimal("0"))),
                str(getattr(item, 'refund_quantity', Decimal("0"))),
                str(getattr(item, 'total_amount', Decimal("0"))),
                str(getattr(item, 'discount_amount', Decimal("0"))),
                str(getattr(item, 'actual_payment_amount', Decimal("0"))),
                str(getattr(item, 'freight', Decimal("0"))),
                str(getattr(item, 'discount_amount_total', Decimal("0"))),
                getattr(item, 'raw_row_index', 0),
                raw_data_json,
                imported_at
            ))
            count += 1
            
            if progress_callback and (i + 1) % batch_size == 0:
                progress = 20 + (i + 1) / total * 70
                progress_callback(int(progress), f"导入明细数据 {i+1}/{total}...")
        
        return count
    
    def _import_supplier_summary(
        self,
        cursor,
        batch_id: str,
        file_name: str,
        sheet_name: str,
        items: list,
        imported_at: str,
        progress_callback: Optional[callable] = None
    ) -> int:
        count = 0
        total = len(items)
        
        for i, item in enumerate(items):
            raw_data_json = json.dumps(getattr(item, 'raw_data', {}), ensure_ascii=False) if hasattr(item, 'raw_data') else '{}'
            
            cursor.execute('''
                INSERT INTO ysb_supplier_summary 
                (import_batch_id, file_name, sheet_name,
                 ysb_supplier_name, ysb_company_name,
                 actual_payment_amount, order_count,
                 raw_row_index, raw_data, imported_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                batch_id,
                file_name,
                sheet_name,
                getattr(item, 'ysb_supplier_name', ''),
                getattr(item, 'ysb_company_name', ''),
                str(getattr(item, 'actual_payment_amount', Decimal("0"))),
                getattr(item, 'order_count', 1),
                getattr(item, 'raw_row_index', 0),
                raw_data_json,
                imported_at
            ))
            count += 1
            
            if progress_callback and (i + 1) % 10 == 0:
                progress = 20 + (i + 1) / total * 70
                progress_callback(int(progress), f"导入供应商汇总 {i+1}/{total}...")
        
        return count
    
    def get_import_batches(self, limit: int = 20) -> List[Dict]:
        conn = self.db.get_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT batch_id, file_name, sheet_type, sheet_name, 
                   total_rows, import_status, imported_at, imported_by
            FROM ysb_import_batches
            ORDER BY imported_at DESC
            LIMIT ?
        ''', (limit,))
        
        rows = cursor.fetchall()
        return [dict(row) for row in rows]
    
    def get_batch_detail_count(self, batch_id: str) -> int:
        conn = self.db.get_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT COUNT(*) as count
            FROM ysb_detail_data
            WHERE import_batch_id = ?
        ''', (batch_id,))
        
        result = cursor.fetchone()
        return result['count'] if result else 0
    
    def get_batch_supplier_count(self, batch_id: str) -> int:
        conn = self.db.get_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT COUNT(*) as count
            FROM ysb_supplier_summary
            WHERE import_batch_id = ?
        ''', (batch_id,))
        
        result = cursor.fetchone()
        return result['count'] if result else 0
    
    def delete_batch(self, batch_id: str) -> bool:
        conn = self.db.get_connection()
        cursor = conn.cursor()
        
        try:
            cursor.execute('''
                DELETE FROM ysb_detail_data
                WHERE import_batch_id = ?
            ''', (batch_id,))
            
            cursor.execute('''
                DELETE FROM ysb_supplier_summary
                WHERE import_batch_id = ?
            ''', (batch_id,))
            
            cursor.execute('''
                DELETE FROM ysb_import_batches
                WHERE batch_id = ?
            ''', (batch_id,))
            
            conn.commit()
            
            logging.info(f"✓ 删除批次数据成功: {batch_id}")
            return True
            
        except Exception as e:
            conn.rollback()
            logging.error(f"❌ 删除批次数据失败: {e}")
            return False
    
    def get_latest_batch(self) -> Optional[Dict]:
        conn = self.db.get_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT batch_id, file_name, sheet_type, sheet_name, 
                   total_rows, import_status, imported_at
            FROM ysb_import_batches
            WHERE import_status = 'success'
            ORDER BY imported_at DESC
            LIMIT 1
        ''')
        
        row = cursor.fetchone()
        return dict(row) if row else None
    
    def _delete_old_data_by_account_period(
        self,
        cursor,
        account_year: int,
        account_month: int,
        sheet_type: str
    ):
        cursor.execute('''
            SELECT batch_id
            FROM ysb_import_batches
            WHERE account_year = ? AND account_month = ? AND sheet_type = ?
        ''', (account_year, account_month, sheet_type))
        
        old_batches = cursor.fetchall()
        
        for batch in old_batches:
            old_batch_id = batch['batch_id']
            
            cursor.execute('''
                DELETE FROM ysb_detail_data
                WHERE import_batch_id = ?
            ''', (old_batch_id,))
            
            cursor.execute('''
                DELETE FROM ysb_supplier_summary
                WHERE import_batch_id = ?
            ''', (old_batch_id,))
            
            cursor.execute('''
                DELETE FROM ysb_import_batches
                WHERE batch_id = ?
            ''', (old_batch_id,))
            
            logging.info(f"✓ 删除旧批次数据: {old_batch_id}")
    
    def check_account_period_exists(
        self,
        account_year: int,
        account_month: int,
        sheet_type: str
    ) -> Optional[Dict]:
        conn = self.db.get_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT batch_id, file_name, sheet_name, total_rows, imported_at
            FROM ysb_import_batches
            WHERE account_year = ? AND account_month = ? AND sheet_type = ? AND import_status = 'success'
            ORDER BY imported_at DESC
            LIMIT 1
        ''', (account_year, account_month, sheet_type))
        
        row = cursor.fetchone()
        
        if row:
            return {
                'batch_id': row['batch_id'],
                'file_name': row['file_name'],
                'sheet_name': row['sheet_name'],
                'total_rows': row['total_rows'],
                'imported_at': row['imported_at']
            }
        
        return None
