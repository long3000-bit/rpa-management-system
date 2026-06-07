import logging
import uuid
from datetime import datetime
from typing import Dict, List, Tuple

from app.storage.database import Database


class StockCompareService:

    def __init__(self, db: Database):
        self.db = db

    def compare_stock(self, batch_id: str, username: str = None) -> Tuple[int, int, int, str]:
        try:
            conn = self.db.get_connection()
            cursor = conn.cursor()

            cursor.execute('''
                SELECT detail_id, oldproductno, productname, lotno, yys_quantity
                FROM yys_import_detail
                WHERE batch_id = ?
            ''', (batch_id,))
            yys_items = cursor.fetchall()

            cursor.execute('''
                SELECT query_id, oldproductno, productname, lotno, jy_quantity, warehouse, valid_date
                FROM jy_stock_query
                WHERE batch_id = ?
            ''', (batch_id,))
            jy_items = cursor.fetchall()

            def aggregate_items(items, quantity_field):
                grouped = {}
                for item in items:
                    oldproductno = str(item['oldproductno'] or '').strip()
                    lotno = str(item['lotno'] or '').strip()
                    if not oldproductno or not lotno:
                        continue

                    key = (oldproductno, lotno)
                    if key not in grouped:
                        grouped[key] = {
                            'oldproductno': oldproductno,
                            'productname': item['productname'] or '',
                            'lotno': lotno,
                            'quantity': 0.0,
                        }

                    grouped[key]['quantity'] += float(item[quantity_field] or 0)

                    if not grouped[key]['productname'] and item['productname']:
                        grouped[key]['productname'] = item['productname']

                return grouped

            yys_dict = aggregate_items(yys_items, 'yys_quantity')
            jy_dict = aggregate_items(jy_items, 'jy_quantity')

            now = datetime.now().isoformat()
            cursor.execute('DELETE FROM stock_compare_result WHERE batch_id = ?', (batch_id,))

            match_count = 0
            diff_count = 0
            yys_only_count = 0

            all_keys = sorted(set(yys_dict.keys()) | set(jy_dict.keys()))

            for key in all_keys:
                yys_item = yys_dict.get(key)
                jy_item = jy_dict.get(key)

                yys_quantity = yys_item['quantity'] if yys_item else 0.0
                jy_quantity = jy_item['quantity'] if jy_item else 0.0
                diff_quantity = jy_quantity - yys_quantity

                if yys_item and jy_item:
                    if abs(diff_quantity) < 0.01:
                        compare_status = 'match'
                        match_count += 1
                    else:
                        compare_status = 'diff'
                        diff_count += 1
                elif yys_item:
                    compare_status = 'yys_only'
                    yys_only_count += 1
                else:
                    compare_status = 'jy_only'

                sync_status = 'pending' if abs(diff_quantity) > 0.01 else 'skipped'
                productname = ''
                if yys_item and yys_item['productname']:
                    productname = yys_item['productname']
                elif jy_item:
                    productname = jy_item['productname']

                cursor.execute('''
                    INSERT INTO stock_compare_result
                    (result_id, batch_id, oldproductno, productname, lotno, yys_quantity, jy_quantity, diff_quantity, compare_status, sync_status, created_at, updated_at, created_by)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (
                    uuid.uuid4().hex,
                    batch_id,
                    key[0],
                    productname,
                    key[1],
                    yys_quantity,
                    jy_quantity,
                    diff_quantity,
                    compare_status,
                    sync_status,
                    now,
                    now,
                    username or 'admin',
                ))

            conn.commit()

            logging.info(
                "库存对比完成，批次号: %s, 匹配: %s, 差异: %s, 云药店独有: %s, 君元独有: %s",
                batch_id,
                match_count,
                diff_count,
                yys_only_count,
                sum(1 for key in jy_dict.keys() if key not in yys_dict),
            )

            return match_count, diff_count, yys_only_count, ""

        except Exception as e:
            logging.error(f"库存对比失败: {e}")
            return 0, 0, 0, str(e)

    def get_compare_results(
        self,
        batch_id: str,
        compare_status: str = None,
        sync_status: str = None,
        productno: str = None,
        productname: str = None,
        lotno: str = None,
    ) -> List[Dict]:
        try:
            conn = self.db.get_connection()
            cursor = conn.cursor()

            sql = '''
                SELECT result_id, oldproductno, productname, lotno, yys_quantity, jy_quantity, diff_quantity, compare_status, sync_status, sync_time, sync_message
                FROM stock_compare_result
                WHERE batch_id = ?
            '''
            params = [batch_id]

            if compare_status:
                sql += " AND compare_status = ?"
                params.append(compare_status)

            if sync_status:
                sql += " AND sync_status = ?"
                params.append(sync_status)

            if productno:
                sql += " AND oldproductno LIKE ?"
                params.append(f"%{productno}%")

            if productname:
                sql += " AND productname LIKE ?"
                params.append(f"%{productname}%")

            if lotno:
                sql += " AND lotno LIKE ?"
                params.append(f"%{lotno}%")

            sql += " ORDER BY oldproductno, lotno"
            cursor.execute(sql, params)

            return [dict(row) for row in cursor.fetchall()]

        except Exception as e:
            logging.error(f"获取对比结果失败: {e}")
            return []

    def get_diff_items(self, batch_id: str) -> List[Dict]:
        try:
            conn = self.db.get_connection()
            cursor = conn.cursor()

            cursor.execute('''
                SELECT result_id, oldproductno, productname, lotno, yys_quantity, jy_quantity, diff_quantity, compare_status, sync_status
                FROM stock_compare_result
                WHERE batch_id = ? AND ABS(diff_quantity) > 0.01 AND sync_status = 'pending'
                ORDER BY oldproductno, lotno
            ''', (batch_id,))

            return [dict(row) for row in cursor.fetchall()]

        except Exception as e:
            logging.error(f"获取差异项失败: {e}")
            return []

    def update_sync_status(
        self,
        result_id: str,
        sync_status: str,
        sync_message: str = "",
        api_response: str = "",
    ) -> Tuple[bool, str]:
        try:
            conn = self.db.get_connection()
            cursor = conn.cursor()

            now = datetime.now().isoformat()

            cursor.execute('''
                UPDATE stock_compare_result
                SET sync_status = ?, sync_time = ?, sync_message = ?, api_response = ?, updated_at = ?
                WHERE result_id = ?
            ''', (sync_status, now, sync_message, api_response, now, result_id))

            conn.commit()

            return True, ""

        except Exception as e:
            logging.error(f"更新同步状态失败: {e}")
            return False, str(e)

    def get_statistics(self, batch_id: str) -> Dict:
        try:
            conn = self.db.get_connection()
            cursor = conn.cursor()

            cursor.execute('''
                SELECT
                    COUNT(*) as total,
                    SUM(CASE WHEN compare_status = 'match' THEN 1 ELSE 0 END) as match_count,
                    SUM(CASE WHEN compare_status = 'diff' THEN 1 ELSE 0 END) as diff_count,
                    SUM(CASE WHEN compare_status = 'yys_only' THEN 1 ELSE 0 END) as yys_only_count,
                    SUM(CASE WHEN compare_status = 'jy_only' THEN 1 ELSE 0 END) as jy_only_count,
                    SUM(CASE WHEN sync_status = 'success' THEN 1 ELSE 0 END) as sync_success,
                    SUM(CASE WHEN sync_status = 'failed' THEN 1 ELSE 0 END) as sync_failed,
                    SUM(CASE WHEN sync_status = 'pending' THEN 1 ELSE 0 END) as sync_pending
                FROM stock_compare_result
                WHERE batch_id = ?
            ''', (batch_id,))

            row = cursor.fetchone()
            if row:
                return dict(row)

            return {}

        except Exception as e:
            logging.error(f"获取统计信息失败: {e}")
            return {}
