import base64
import hashlib
import json
import logging
import random
import time
import uuid
from datetime import datetime
from typing import Dict, Optional, Tuple

import requests

from app.storage.database import Database


class YysApiService:

    def __init__(self, db: Database):
        self.db = db

    def get_config(self, config_id: str) -> Optional[Dict]:
        try:
            conn = self.db.get_connection()
            cursor = conn.cursor()

            cursor.execute('''
                SELECT config_id, config_name, host, appkey, appsecret, orgcode, timeout, enabled
                FROM yys_api_config
                WHERE config_id = ? AND enabled = 1
            ''', (config_id,))

            row = cursor.fetchone()
            if row:
                return dict(row)

            return None

        except Exception as e:
            logging.error(f"获取API配置失败: {e}")
            return None

    def _generate_signature(self, appsecret: str, nonce: str, timestamp: str) -> str:
        raw = f"{appsecret}{nonce}{timestamp}"
        return hashlib.md5(raw.encode("utf-8")).hexdigest()

    def _build_sync_url(self, host: str) -> str:
        base_url = (host or "").strip()
        if base_url.endswith("/router"):
            base_url = base_url[:-7]
        return base_url.rstrip("/") + "/public/syncstock"

    def _build_headers(self, config: Dict) -> Dict:
        nonce = uuid.uuid4().hex[:8]
        timestamp = str(int(time.time() * 1000))
        return {
            "Content-Type": "application/json;charset=utf-8",
            "appkey": config["appkey"],
            "nonce": nonce,
            "timestamp": timestamp,
            "sign": self._generate_signature(config["appsecret"], nonce, timestamp),
        }

    def _build_sync_item(
        self,
        config: Dict,
        oldproductno: str,
        lotno: str,
        quantity: float,
        oldproductname: str = "",
        purprice: float = 0.0,
        memo: str = "",
    ) -> Dict:
        return {
            "synctype": 2,
            "freightbillno": "库存同步",
            "orgcode": config["orgcode"],
            "oldproductno": oldproductno,
            "oldproductname": oldproductname or "",
            "productqty": float(quantity),
            "lotno": lotno,
            "stockstatus": 1,
            "memo": memo or "",
            "createdate": int(time.time() * 1000),
            "purprice": float(purprice or 0),
        }

    def _write_sync_status(
        self,
        result_id: str,
        sync_status: str,
        sync_message: str = "",
        api_response: Dict = None,
    ):
        if not result_id:
            return

        try:
            conn = self.db.get_connection()
            cursor = conn.cursor()
            now = datetime.now().isoformat()

            cursor.execute('''
                UPDATE stock_compare_result
                SET sync_status = ?, sync_time = ?, sync_message = ?, api_response = ?, updated_at = ?
                WHERE result_id = ?
            ''', (
                sync_status,
                now,
                sync_message,
                json.dumps(api_response or {}, ensure_ascii=False),
                now,
                result_id,
            ))

            conn.commit()

        except Exception as e:
            logging.error(f"更新库存同步状态失败: {e}")

    def update_stock(
        self,
        config_id: str,
        oldproductno: str,
        lotno: str,
        quantity: float,
        operation: str = None,
        oldproductname: str = "",
        purprice: float = 0.0,
        memo: str = "",
    ) -> Tuple[bool, str, Dict]:
        config = self.get_config(config_id)

        if not config:
            return False, "API配置不存在或已禁用", {}

        if not oldproductno:
            return False, "缺少本地药品编码", {}

        if not lotno:
            return False, "缺少批号", {}

        try:
            sync_item = self._build_sync_item(
                config,
                oldproductno,
                lotno,
                quantity,
                oldproductname=oldproductname,
                purprice=purprice,
                memo=memo,
            )
            body_json = json.dumps([sync_item], ensure_ascii=False, separators=(",", ":"))
            body = base64.b64encode(body_json.encode("utf-8")).decode("ascii")

            response = requests.post(
                self._build_sync_url(config["host"]),
                data=body,
                timeout=config["timeout"] or 30,
                headers=self._build_headers(config),
            )
            result = response.json()

            if str(result.get("code")) == "200":
                return True, result.get("message", "处理成功"), result
            return False, result.get("message", "未知错误"), result

        except requests.exceptions.Timeout:
            return False, "请求超时", {}
        except requests.exceptions.ConnectionError:
            return False, "连接失败", {}
        except Exception as e:
            logging.error(f"调用云药店库存同步接口失败: {e}")
            return False, str(e), {}

    def test_connection(self, config_id: str) -> Tuple[bool, str]:
        config = self.get_config(config_id)

        if not config:
            return False, "API配置不存在或已禁用"

        missing = [
            name for name in ("host", "appkey", "appsecret", "orgcode")
            if not config.get(name)
        ]
        if missing:
            return False, f"API配置不完整: {', '.join(missing)}"

        url = self._build_sync_url(config["host"])
        return True, f"配置校验通过；库存查询接口已关闭，未调用checkstock。同步接口: {url}"

    def batch_update_stock(self, config_id: str, items: list, progress_callback=None) -> Tuple[int, int, int]:
        success_count = 0
        failed_count = 0
        skipped_count = 0

        total = len(items)

        for idx, item in enumerate(items):
            oldproductno = item.get("oldproductno")
            lotno = item.get("lotno")
            diff_quantity = float(item.get("diff_quantity") or 0)

            if abs(diff_quantity) <= 0.01:
                skipped_count += 1
                self._write_sync_status(item.get("result_id"), "skipped", "无差异")
                if progress_callback:
                    progress_callback(idx + 1, total, "skipped", "无差异")
                continue

            success, message, response = self.update_stock(
                config_id,
                oldproductno,
                lotno,
                diff_quantity,
                oldproductname=item.get("productname") or "",
                memo=f"库存差异同步:{item.get('result_id', '')}",
            )

            if success:
                success_count += 1
                self._write_sync_status(item.get("result_id"), "success", message, response)
                if progress_callback:
                    progress_callback(idx + 1, total, "success", message)
            else:
                failed_count += 1
                self._write_sync_status(item.get("result_id"), "failed", message, response)
                if progress_callback:
                    progress_callback(idx + 1, total, "failed", message)

            if idx < total - 1:
                time.sleep(random.uniform(10, 15))

        return success_count, failed_count, skipped_count
