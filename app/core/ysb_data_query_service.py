import logging
import json
from datetime import datetime
from decimal import Decimal
from typing import Optional, List
from dataclasses import dataclass

from app.storage.database import Database
from app.core.ysb_excel_reader import YsbExcelData, YsbDetailItem, YsbSupplierSummary


class YsbDataQueryService:
    
    def __init__(self, db: Database):
        self.db = db
    
    def get_latest_batch_data(self) -> Optional[YsbExcelData]:
        conn = self.db.get_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT file_name
            FROM ysb_import_batches
            WHERE import_status = 'success'
            ORDER BY imported_at DESC
            LIMIT 1
        ''')
        
        latest_file_row = cursor.fetchone()
        if not latest_file_row:
            logging.info("数据库中没有找到导入的药师帮数据")
            return None
        
        latest_file_name = latest_file_row['file_name']
        
        cursor.execute('''
            SELECT batch_id, file_name, sheet_name, sheet_type, total_rows
            FROM ysb_import_batches
            WHERE import_status = 'success' AND file_name = ?
            ORDER BY imported_at DESC
        ''', (latest_file_name,))
        
        batch_rows = cursor.fetchall()
        if not batch_rows:
            logging.info("数据库中没有找到导入的药师帮数据")
            return None
        
        logging.info(f"===========================================")
        logging.info(f"从数据库读取药师帮数据")
        logging.info(f"  文件名: {latest_file_name}")
        logging.info(f"  批次数量: {len(batch_rows)}")
        logging.info(f"===========================================")
        
        ysb_data = YsbExcelData(file_path="")
        ysb_data.sheet_name = batch_rows[0]['sheet_name']
        ysb_data.sheet_type = "auto"
        ysb_data.total_rows = 0
        
        for batch_row in batch_rows:
            batch_id = batch_row['batch_id']
            sheet_name = batch_row['sheet_name']
            
            logging.info(f"处理批次: {batch_id} (工作表: {sheet_name})")
            
            cursor.execute('''
                SELECT COUNT(*) as count
                FROM ysb_detail_data
                WHERE import_batch_id = ?
            ''', (batch_id,))
            
            detail_count = cursor.fetchone()['count']
            
            if detail_count > 0:
                items = self._load_detail_items(cursor, batch_id)
                ysb_data.items.extend(items)
                logging.info(f"✓ 加载明细数据: {len(items)} 条 (来自 {sheet_name})")
            
            cursor.execute('''
                SELECT COUNT(*) as count
                FROM ysb_supplier_summary
                WHERE import_batch_id = ?
            ''', (batch_id,))
            
            supplier_count = cursor.fetchone()['count']
            
            if supplier_count > 0:
                summaries = self._load_supplier_summaries(cursor, batch_id)
                ysb_data.supplier_summaries.extend(summaries)
                logging.info(f"✓ 加载供应商汇总: {len(summaries)} 条 (来自 {sheet_name})")
        
        ysb_data.total_rows = len(ysb_data.items) + len(ysb_data.supplier_summaries)
        logging.info(f"===========================================")
        logging.info(f"数据汇总:")
        logging.info(f"  明细数据总计: {len(ysb_data.items)} 条")
        logging.info(f"  供应商汇总总计: {len(ysb_data.supplier_summaries)} 条")
        logging.info(f"===========================================")
        
        return ysb_data
    
    def get_detail_data_with_supplier_summary(self) -> Optional[YsbExcelData]:
        conn = self.db.get_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT batch_id, file_name, sheet_name, sheet_type, total_rows, imported_at
            FROM ysb_import_batches
            WHERE import_status = 'success'
            ORDER BY imported_at DESC
            LIMIT 1
        ''')
        
        batch_row = cursor.fetchone()
        if not batch_row:
            logging.info("数据库中没有找到导入的药师帮数据")
            return None
        
        batch_id = batch_row['batch_id']
        
        logging.info(f"===========================================")
        logging.info(f"从订单明细数据动态汇总供应商金额")
        logging.info(f"  批次ID: {batch_id}")
        logging.info(f"===========================================")
        
        ysb_data = YsbExcelData(file_path="")
        ysb_data.sheet_name = batch_row['sheet_name']
        ysb_data.sheet_type = batch_row['sheet_type']
        
        items = self._load_detail_items(cursor, batch_id)
        ysb_data.items = items
        logging.info(f"✓ 加载订单明细数据: {len(items)} 条")
        
        summaries = self._aggregate_supplier_from_details(cursor, batch_id)
        ysb_data.supplier_summaries = summaries
        logging.info(f"✓ 动态汇总供应商: {len(summaries)} 条")
        
        ysb_data.total_rows = len(ysb_data.items)
        
        total_amount = sum(s.actual_payment_amount for s in summaries)
        logging.info(f"===========================================")
        logging.info(f"数据汇总:")
        logging.info(f"  订单明细总计: {len(ysb_data.items)} 条")
        logging.info(f"  供应商汇总总计: {len(ysb_data.supplier_summaries)} 条")
        logging.info(f"  供应商总金额: {total_amount}")
        logging.info(f"===========================================")
        
        return ysb_data
    
    def _aggregate_supplier_from_details(self, cursor, batch_id: str) -> List[YsbSupplierSummary]:
        cursor.execute('''
            SELECT 
                ysb_company_name,
                ysb_supplier_name,
                SUM(CAST(actual_payment_amount AS REAL)) as total_amount,
                COUNT(*) as order_count
            FROM ysb_detail_data
            WHERE import_batch_id = ?
            AND ysb_company_name IS NOT NULL AND ysb_company_name != ''
            GROUP BY ysb_company_name
            ORDER BY total_amount DESC
        ''', (batch_id,))
        
        rows = cursor.fetchall()
        summaries = []
        
        for idx, row in enumerate(rows):
            summary = YsbSupplierSummary(raw_row_index=idx)
            summary.ysb_company_name = row['ysb_company_name'] or ''
            summary.ysb_supplier_name = row['ysb_supplier_name'] or ''
            summary.actual_payment_amount = self._parse_decimal(row['total_amount'])
            summary.order_count = row['order_count'] or 1
            summaries.append(summary)
        
        return summaries
    
    def get_data_by_import_date_range(
        self,
        start_date: str,
        end_date: str,
        data_type: str = "supplier"
    ) -> Optional[YsbExcelData]:
        conn = self.db.get_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT batch_id, file_name, sheet_name, sheet_type, total_rows, imported_at
            FROM ysb_import_batches
            WHERE import_status = 'success'
            AND imported_at >= ? AND imported_at <= ?
            ORDER BY imported_at DESC
        ''', (f"{start_date}T00:00:00", f"{end_date}T23:59:59"))
        
        batch_rows = cursor.fetchall()
        if not batch_rows:
            logging.info(f"数据库中没有找到导入日期范围 {start_date} ~ {end_date} 的数据")
            return None
        
        logging.info(f"===========================================")
        logging.info(f"从数据库读取药师帮数据 (导入日期范围: {start_date} ~ {end_date})")
        logging.info(f"  批次数量: {len(batch_rows)}")
        logging.info(f"===========================================")
        
        ysb_data = YsbExcelData(file_path="")
        ysb_data.sheet_name = batch_rows[0]['sheet_name']
        ysb_data.sheet_type = "auto"
        ysb_data.total_rows = 0
        
        for batch_row in batch_rows:
            batch_id = batch_row['batch_id']
            sheet_name = batch_row['sheet_name']
            sheet_type = batch_row['sheet_type']
            
            logging.info(f"处理批次: {batch_id} (工作表: {sheet_name}, 类型: {sheet_type})")
            
            if data_type in ["auto", "detail"] and sheet_type in ["detail", "auto"]:
                items = self._load_detail_items(cursor, batch_id)
                ysb_data.items.extend(items)
                logging.info(f"✓ 加载明细数据: {len(items)} 条")
            
            if data_type in ["auto", "supplier"] and sheet_type in ["supplier", "auto"]:
                summaries = self._load_supplier_summaries(cursor, batch_id)
                ysb_data.supplier_summaries.extend(summaries)
                logging.info(f"✓ 加载供应商汇总: {len(summaries)} 条")
        
        ysb_data.total_rows = len(ysb_data.items) + len(ysb_data.supplier_summaries)
        logging.info(f"===========================================")
        logging.info(f"数据汇总:")
        logging.info(f"  明细数据总计: {len(ysb_data.items)} 条")
        logging.info(f"  供应商汇总总计: {len(ysb_data.supplier_summaries)} 条")
        logging.info(f"===========================================")
        
        return ysb_data
    
    def get_data_by_business_date_range(
        self,
        start_date: str,
        end_date: str,
        data_type: str = "supplier"
    ) -> Optional[YsbExcelData]:
        conn = self.db.get_connection()
        cursor = conn.cursor()
        
        start_dt = self._parse_datetime(f"{start_date} 00:00:00")
        end_dt = self._parse_datetime(f"{end_date} 23:59:59")
        if not start_dt or not end_dt:
            logging.error(f"无效账期日期范围: {start_date} ~ {end_date}")
            return None
        
        cursor.execute('''
            SELECT batch_id, file_name, sheet_name, sheet_type, total_rows, imported_at
            FROM ysb_import_batches
            WHERE import_status = 'success'
            ORDER BY imported_at DESC
        ''')
        
        batch_rows = cursor.fetchall()
        if not batch_rows:
            logging.info("数据库中没有找到导入的药师帮数据")
            return None
        
        logging.info(f"===========================================")
        logging.info(f"从数据库读取药师帮数据 (业务账期: {start_date} ~ {end_date})")
        logging.info(f"  数据类型: {data_type}")
        logging.info(f"  批次数量: {len(batch_rows)}")
        logging.info(f"===========================================")
        
        ysb_data = YsbExcelData(file_path="")
        ysb_data.sheet_type = data_type
        ysb_data.total_rows = 0
        
        for batch_row in batch_rows:
            batch_id = batch_row['batch_id']
            sheet_name = batch_row['sheet_name']
            sheet_type = batch_row['sheet_type']
            
            if data_type in ["auto", "detail"] and sheet_type in ["detail", "auto"]:
                items = self._load_detail_items(cursor, batch_id)
                filtered_items = [
                    item for item in items
                    if self._is_detail_item_in_date_range(item, start_dt, end_dt)
                ]
                ysb_data.items.extend(filtered_items)
                if not ysb_data.sheet_name and filtered_items:
                    ysb_data.sheet_name = sheet_name
                logging.info(f"✓ 加载明细数据: {len(filtered_items)}/{len(items)} 条 (来自 {sheet_name})")
            
            if data_type in ["auto", "supplier"] and sheet_type in ["supplier", "auto"]:
                summaries = self._load_supplier_summaries(cursor, batch_id)
                filtered_summaries = [
                    item for item in summaries
                    if self._is_supplier_summary_in_date_range(item, start_dt, end_dt)
                ]
                ysb_data.supplier_summaries.extend(filtered_summaries)
                if not ysb_data.sheet_name and filtered_summaries:
                    ysb_data.sheet_name = sheet_name
                logging.info(f"✓ 加载本月支付订单: {len(filtered_summaries)}/{len(summaries)} 条 (来自 {sheet_name})")
        
        ysb_data.total_rows = len(ysb_data.items) + len(ysb_data.supplier_summaries)
        logging.info(f"===========================================")
        logging.info(f"业务账期数据汇总:")
        logging.info(f"  明细数据总计: {len(ysb_data.items)} 条")
        logging.info(f"  本月支付订单总计: {len(ysb_data.supplier_summaries)} 条")
        logging.info(f"===========================================")
        
        return ysb_data if ysb_data.total_rows > 0 else None
    
    def _load_detail_items(self, cursor, batch_id: str) -> List[YsbDetailItem]:
        cursor.execute('''
            SELECT 
                import_batch_id, file_name, sheet_name, ysb_order_no, order_type,
                purchase_time, ysb_store_name, ysb_supplier_name, ysb_company_name,
                product_name, manufacturer, spec, unit, approval_number, barcode,
                batch_no, production_date, expiry_date, unit_price, discount_price,
                quantity, order_quantity, refund_quantity, total_amount, discount_amount,
                actual_payment_amount, freight, discount_amount_total, raw_row_index, raw_data
            FROM ysb_detail_data
            WHERE import_batch_id = ?
            ORDER BY raw_row_index
        ''', (batch_id,))
        
        rows = cursor.fetchall()
        items = []
        
        for row in rows:
            item = YsbDetailItem(raw_row_index=row['raw_row_index'] or 0)
            
            item.ysb_order_no = row['ysb_order_no'] or ''
            item.order_type = row['order_type'] or ''
            item.purchase_time = self._parse_datetime(row['purchase_time'])
            item.ysb_store_name = row['ysb_store_name'] or ''
            item.ysb_supplier_name = row['ysb_supplier_name'] or ''
            item.ysb_company_name = row['ysb_company_name'] or ''
            item.product_name = row['product_name'] or ''
            item.manufacturer = row['manufacturer'] or ''
            item.spec = row['spec'] or ''
            item.unit = row['unit'] or ''
            item.approval_number = row['approval_number'] or ''
            item.barcode = row['barcode'] or ''
            item.batch_no = row['batch_no'] or ''
            item.production_date = self._parse_datetime(row['production_date'])
            item.expiry_date = self._parse_datetime(row['expiry_date'])
            
            item.unit_price = self._parse_decimal(row['unit_price'])
            item.discount_price = self._parse_decimal(row['discount_price'])
            item.quantity = self._parse_decimal(row['quantity'])
            item.order_quantity = self._parse_decimal(row['order_quantity'])
            item.refund_quantity = self._parse_decimal(row['refund_quantity'])
            item.total_amount = self._parse_decimal(row['total_amount'])
            item.discount_amount = self._parse_decimal(row['discount_amount'])
            item.actual_payment_amount = self._parse_decimal(row['actual_payment_amount'])
            item.freight = self._parse_decimal(row['freight'])
            item.discount_amount_total = self._parse_decimal(row['discount_amount_total'])
            try:
                item.raw_data = json.loads(row['raw_data']) if row['raw_data'] else {}
            except Exception:
                item.raw_data = {}
            
            items.append(item)
        
        return items
    
    def _load_supplier_summaries(self, cursor, batch_id: str) -> List[YsbSupplierSummary]:
        cursor.execute('''
            SELECT 
                import_batch_id, file_name, sheet_name, ysb_supplier_name, ysb_company_name,
                actual_payment_amount, order_count, raw_row_index, raw_data
            FROM ysb_supplier_summary
            WHERE import_batch_id = ?
            ORDER BY raw_row_index
        ''', (batch_id,))
        
        rows = cursor.fetchall()
        items = []
        
        for row in rows:
            item = YsbSupplierSummary(raw_row_index=row['raw_row_index'] or 0)
            
            item.ysb_supplier_name = row['ysb_supplier_name'] or ''
            item.ysb_company_name = row['ysb_company_name'] or ''
            item.actual_payment_amount = self._parse_decimal(row['actual_payment_amount'])
            item.order_count = row['order_count'] or 1
            try:
                item.raw_data = json.loads(row['raw_data']) if row['raw_data'] else {}
            except Exception:
                item.raw_data = {}
            
            items.append(item)
        
        return items
    
    def _is_supplier_summary_in_date_range(
        self,
        item: YsbSupplierSummary,
        start_dt: datetime,
        end_dt: datetime
    ) -> bool:
        raw_data = getattr(item, 'raw_data', {}) or {}
        purchase_time = (
            raw_data.get("采购时间")
            or raw_data.get("下单时间")
            or raw_data.get("支付时间")
            or raw_data.get("订单时间")
        )
        parsed_time = self._parse_datetime(purchase_time)
        return bool(parsed_time and start_dt <= parsed_time <= end_dt)
    
    def _is_detail_item_in_date_range(
        self,
        item: YsbDetailItem,
        start_dt: datetime,
        end_dt: datetime
    ) -> bool:
        parsed_time = item.purchase_time
        if not parsed_time:
            raw_data = getattr(item, 'raw_data', {}) or {}
            parsed_time = self._parse_datetime(
                raw_data.get("采购时间")
                or raw_data.get("下单时间")
                or raw_data.get("支付时间")
                or raw_data.get("订单时间")
            )
        return bool(parsed_time and start_dt <= parsed_time <= end_dt)
    
    def _parse_decimal(self, value) -> Decimal:
        if value is None or value == '':
            return Decimal("0")
        
        try:
            return Decimal(str(value))
        except:
            return Decimal("0")
    
    def _parse_datetime(self, value):
        if not value or value == '':
            return None
        
        try:
            return datetime.fromisoformat(str(value))
        except:
            pass
        
        for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d", "%Y/%m/%d %H:%M:%S", "%Y/%m/%d"):
            try:
                return datetime.strptime(str(value), fmt)
            except:
                continue
        
        return None
    
    def get_batch_list(self, limit: int = 10) -> List[dict]:
        conn = self.db.get_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT 
                b.batch_id,
                b.file_name,
                b.sheet_name,
                b.sheet_type,
                b.total_rows,
                b.imported_at,
                (SELECT COUNT(*) FROM ysb_detail_data WHERE import_batch_id = b.batch_id) as detail_count,
                (SELECT COUNT(*) FROM ysb_supplier_summary WHERE import_batch_id = b.batch_id) as supplier_count
            FROM ysb_import_batches b
            WHERE b.import_status = 'success'
            ORDER BY b.imported_at DESC
            LIMIT ?
        ''', (limit,))
        
        rows = cursor.fetchall()
        return [dict(row) for row in rows]
    
    def get_data_by_account_period(
        self,
        account_year: int,
        account_month: int,
        data_type: str = "supplier"
    ) -> Optional[YsbExcelData]:
        conn = self.db.get_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT batch_id, file_name, sheet_name, sheet_type, total_rows, imported_at
            FROM ysb_import_batches
            WHERE import_status = 'success'
            AND account_year = ? AND account_month = ?
            ORDER BY imported_at DESC
        ''', (account_year, account_month))
        
        batch_rows = cursor.fetchall()
        if not batch_rows:
            logging.info(f"数据库中没有找到核算年 {account_year} 月 {account_month} 的数据")
            return None
        
        logging.info(f"===========================================")
        logging.info(f"从数据库读取药师帮数据 (核算年月: {account_year}年{account_month}月)")
        logging.info(f"  批次数量: {len(batch_rows)}")
        logging.info(f"===========================================")
        
        ysb_data = YsbExcelData(file_path="")
        ysb_data.sheet_name = batch_rows[0]['sheet_name']
        ysb_data.sheet_type = "auto"
        ysb_data.total_rows = 0
        
        for batch_row in batch_rows:
            batch_id = batch_row['batch_id']
            sheet_name = batch_row['sheet_name']
            sheet_type = batch_row['sheet_type']
            
            logging.info(f"处理批次: {batch_id} (工作表: {sheet_name}, 类型: {sheet_type})")
            
            if data_type in ["auto", "detail"] and sheet_type in ["detail", "auto"]:
                items = self._load_detail_items(cursor, batch_id)
                ysb_data.items.extend(items)
                logging.info(f"✓ 加载明细数据: {len(items)} 条")
            
            if data_type in ["auto", "supplier"] and sheet_type in ["supplier", "auto"]:
                summaries = self._load_supplier_summaries(cursor, batch_id)
                ysb_data.supplier_summaries.extend(summaries)
                logging.info(f"✓ 加载供应商汇总: {len(summaries)} 条")
        
        ysb_data.total_rows = len(ysb_data.items) + len(ysb_data.supplier_summaries)
        logging.info(f"===========================================")
        logging.info(f"数据汇总:")
        logging.info(f"  明细数据总计: {len(ysb_data.items)} 条")
        logging.info(f"  供应商汇总总计: {len(ysb_data.supplier_summaries)} 条")
        logging.info(f"===========================================")
        
        return ysb_data
