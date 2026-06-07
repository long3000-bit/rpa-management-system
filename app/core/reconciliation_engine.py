from dataclasses import dataclass, field
from decimal import Decimal
from typing import Optional
from collections import defaultdict
import logging


def safe_decimal(value) -> Decimal:
    if value is None:
        return Decimal("0")
    
    if isinstance(value, Decimal):
        return value
    
    if isinstance(value, str):
        try:
            return Decimal(value)
        except:
            return Decimal("0")
    
    if isinstance(value, (int, float)):
        try:
            return Decimal(str(value))
        except:
            return Decimal("0")
    
    return Decimal("0")


@dataclass
class InboundItem:
    raw_row_index: int
    inbound_no: str = ""
    inbound_date: str = ""
    product_name: str = ""
    manufacturer: str = ""
    spec: str = ""
    quantity: Decimal = Decimal("0")
    unit_price: Decimal = Decimal("0")
    amount: Decimal = Decimal("0")
    supplier_code: str = ""
    supplier_name: str = ""
    product_code: str = ""
    ysb_code: str = ""
    barcode: str = ""
    batch_no: str = ""
    expiry_date: str = ""
    document_status: str = ""


@dataclass
class SupplierReconResult:
    status: str = ""
    diff_type: str = ""
    ysb_supplier: str = ""
    inbound_supplier: str = ""
    ysb_amount: Decimal = Decimal("0")
    inbound_amount: Decimal = Decimal("0")
    amount_diff: Decimal = Decimal("0")
    ysb_count: int = 0
    inbound_count: int = 0
    match_method: str = ""
    remark: str = ""


@dataclass
class DetailMatchResult:
    raw_row_index: int = 0
    ysb_order_no: str = ""
    ysb_supplier: str = ""
    product_name: str = ""
    spec: str = ""
    manufacturer: str = ""
    barcode: str = ""
    ysb_quantity: Decimal = Decimal("0")
    ysb_amount: Decimal = Decimal("0")
    ysb_purchase_time: str = ""
    
    matched_product_code: str = ""
    matched_supplier_name: str = ""
    matched_product_name: str = ""
    matched_spec: str = ""
    matched_manufacturer: str = ""
    match_method: str = ""
    match_score: float = 0.0
    match_status: str = ""
    match_remark: str = ""


@dataclass
class ProductReconResult:
    status: str = ""
    diff_type: str = ""
    supplier: str = ""
    product_code: str = ""
    product_name: str = ""
    spec: str = ""
    manufacturer: str = ""
    ysb_amount: Decimal = Decimal("0")
    inbound_amount: Decimal = Decimal("0")
    amount_diff: Decimal = Decimal("0")
    ysb_quantity: Decimal = Decimal("0")
    inbound_quantity: Decimal = Decimal("0")
    quantity_diff: Decimal = Decimal("0")
    ysb_supplier: str = ""
    inbound_supplier: str = ""
    ysb_purchase_time: str = ""
    inbound_date: str = ""
    remark: str = ""


@dataclass
class ReconciliationSummary:
    ysb_row_count: int = 0
    inbound_row_count: int = 0
    
    ysb_supplier_count: int = 0
    inbound_supplier_count: int = 0
    supplier_match_count: int = 0
    supplier_diff_count: int = 0
    
    detail_matched_count: int = 0
    detail_suspected_count: int = 0
    detail_unmatched_count: int = 0
    
    product_match_count: int = 0
    product_diff_count: int = 0
    
    ysb_total_amount: Decimal = Decimal("0")
    inbound_total_amount: Decimal = Decimal("0")


class ReconciliationEngine:
    
    def __init__(
        self,
        amount_tolerance: float = 0.01,
        quantity_tolerance: float = 0.01,
        auto_match_threshold: float = 80.0,
        suspected_match_threshold: float = 60.0
    ):
        self.amount_tolerance = Decimal(str(amount_tolerance))
        self.quantity_tolerance = Decimal(str(quantity_tolerance))
        self.auto_match_threshold = auto_match_threshold
        self.suspected_match_threshold = suspected_match_threshold
        
        self.supplier_results: list[SupplierReconResult] = []
        self.detail_results: list[DetailMatchResult] = []
        self.product_results: list[ProductReconResult] = []
        self.summary = ReconciliationSummary()
    
    def _calculate_actual_amount(self, item) -> Decimal:
        raw_data = getattr(item, 'raw_data', {}) or {}
        
        actual_payment_field = '实际支付金额(已减退款)'
        if actual_payment_field in raw_data:
            raw_value = raw_data[actual_payment_field]
            actual_amount = safe_decimal(raw_value) or Decimal("0")
            return actual_amount
        
        return Decimal("0")
    
    def reconcile(
        self,
        ysb_items: list,
        inbound_rows: list[dict]
    ) -> tuple[
        list[SupplierReconResult],
        list[DetailMatchResult],
        list[ProductReconResult],
        ReconciliationSummary
    ]:
        inbound_items = self._normalize_inbound_data(inbound_rows)
        
        self._supplier_reconciliation(ysb_items, inbound_items)
        
        self._detail_matching(ysb_items, inbound_items)
        
        self._product_reconciliation()
        
        self._calculate_summary(ysb_items, inbound_items)
        
        return (
            self.supplier_results,
            self.detail_results,
            self.product_results,
            self.summary
        )
    
    def supplier_reconciliation(
        self,
        ysb_summaries: list,
        inbound_rows: list[dict]
    ) -> tuple[
        list[SupplierReconResult],
        list[DetailMatchResult],
        list[ProductReconResult],
        ReconciliationSummary
    ]:
        self.inbound_items = self._normalize_inbound_data(inbound_rows)
        
        self._supplier_only_reconciliation(ysb_summaries)
        
        self._calculate_supplier_summary(ysb_summaries)
        
        return (
            self.supplier_results,
            self.detail_results,
            self.product_results,
            self.summary
        )
    
    def product_reconciliation(
        self,
        ysb_items: list,
        inbound_rows: list[dict]
    ) -> tuple[
        list[SupplierReconResult],
        list[DetailMatchResult],
        list[ProductReconResult],
        ReconciliationSummary
    ]:
        self.inbound_items = self._normalize_inbound_data(inbound_rows)
        
        self._detail_matching(ysb_items, self.inbound_items)
        
        self._product_reconciliation()
        
        self._calculate_product_summary(ysb_items)
        
        return (
            self.supplier_results,
            self.detail_results,
            self.product_results,
            self.summary
        )
    
    def product_reconciliation_by_suppliers(
        self,
        ysb_items: list,
        inbound_rows: list[dict],
        target_suppliers: list[str]
    ) -> tuple[
        list[SupplierReconResult],
        list[DetailMatchResult],
        list[ProductReconResult],
        ReconciliationSummary
    ]:
        self.inbound_items = self._normalize_inbound_data(inbound_rows)
        
        logging.info(f"===========================================")
        logging.info(f"按指定供应商核对商品 - 开始")
        logging.info(f"  目标供应商数: {len(target_suppliers)}")
        logging.info(f"  目标供应商: {target_suppliers}")
        logging.info(f"===========================================")
        
        filtered_ysb_items = []
        for item in ysb_items:
            supplier = getattr(item, 'ysb_company_name', '') or getattr(item, 'ysb_supplier_name', '')
            supplier = supplier.strip()
            supplier_norm = self._normalize_supplier_name(supplier)
            
            for target in target_suppliers:
                target_norm = self._normalize_supplier_name(target)
                if supplier_norm and target_norm and supplier_norm == target_norm:
                    filtered_ysb_items.append(item)
                    break
        
        logging.info(f"  筛选后药师帮商品数: {len(filtered_ysb_items)}")
        
        filtered_inbound_items = []
        for item in self.inbound_items:
            supplier = item.supplier_name.strip()
            supplier_norm = self._normalize_supplier_name(supplier)
            
            for target in target_suppliers:
                target_norm = self._normalize_supplier_name(target)
                if supplier_norm and target_norm and supplier_norm == target_norm:
                    filtered_inbound_items.append(item)
                    break
        
        logging.info(f"  筛选后入库商品数: {len(filtered_inbound_items)}")
        
        self._detail_matching(filtered_ysb_items, filtered_inbound_items)
        
        self._product_reconciliation()
        
        self._calculate_product_summary(filtered_ysb_items)
        
        return (
            self.supplier_results,
            self.detail_results,
            self.product_results,
            self.summary
        )
    
    def _supplier_only_reconciliation(self, ysb_summaries: list):
        logging.info(f"===========================================")
        logging.info(f"供应商对账（仅供应商）- 开始")
        logging.info(f"===========================================")
        
        if ysb_summaries:
            sample_item = ysb_summaries[0]
            logging.info(f"药师帮供应商数据样例类型: {type(sample_item).__name__}")
            logging.info(f"药师帮供应商数据样例字段: {vars(sample_item).keys() if hasattr(sample_item, '__dict__') else dir(sample_item)}")
            
            for idx, item in enumerate(ysb_summaries[:3]):
                actual_amount = self._calculate_actual_amount(item)
                supplier_name = getattr(item, 'ysb_company_name', '') or getattr(item, 'ysb_supplier_name', '')
                logging.info(f"  样例{idx+1}: supplier={supplier_name}, actual_amount={actual_amount}")
        
        ysb_by_supplier = defaultdict(list)
        for item in ysb_summaries:
            supplier = getattr(item, 'ysb_company_name', '') or getattr(item, 'ysb_supplier_name', '')
            supplier = supplier.strip()
            if supplier:
                ysb_by_supplier[supplier].append(item)
        
        inbound_by_supplier = defaultdict(list)
        for item in self.inbound_items:
            supplier = item.supplier_name.strip()
            if supplier:
                inbound_by_supplier[supplier].append(item)
        
        matched_suppliers = set()
        
        for ysb_supplier, ysb_list in ysb_by_supplier.items():
            ysb_amount = Decimal("0")
            amount_details = []
            
            for item in ysb_list:
                item_amount = self._calculate_actual_amount(item)
                ysb_amount += item_amount
                amount_details.append(str(item_amount))
                
                if len(amount_details) <= 2:
                    logging.info(f"    供应商[{ysb_supplier}] 记录: actual_amount={item_amount}")
            
            logging.info(f"供应商 [{ysb_supplier}]: 共{len(ysb_list)}条, 明细={amount_details}, 总金额={ysb_amount}")
            
            if ysb_supplier in inbound_by_supplier:
                inbound_list = inbound_by_supplier[ysb_supplier]
                inbound_amount = sum(safe_decimal(item.amount) for item in inbound_list)
                amount_diff = abs(ysb_amount - inbound_amount)
                
                result = SupplierReconResult()
                result.ysb_supplier = ysb_supplier
                result.inbound_supplier = ysb_supplier
                result.ysb_amount = ysb_amount
                result.inbound_amount = inbound_amount
                result.amount_diff = amount_diff
                result.ysb_count = len(ysb_list)
                result.inbound_count = len(inbound_list)
                result.match_method = "供应商名称完全匹配"
                
                if amount_diff <= self.amount_tolerance:
                    result.status = "一致"
                    result.diff_type = ""
                else:
                    result.status = "差异"
                    result.diff_type = "供应商金额不一致"
                    result.remark = f"金额差异: {amount_diff:.2f}"
                
                self.supplier_results.append(result)
                matched_suppliers.add(ysb_supplier)
            else:
                found = False
                ysb_norm = self._normalize_supplier_name(ysb_supplier)
                for inbound_supplier in inbound_by_supplier:
                    inbound_norm = self._normalize_supplier_name(inbound_supplier)
                    if ysb_norm and inbound_norm and ysb_norm == inbound_norm:
                        inbound_list = inbound_by_supplier[inbound_supplier]
                        inbound_amount = sum(safe_decimal(item.amount) for item in inbound_list)
                        amount_diff = abs(ysb_amount - inbound_amount)
                        
                        result = SupplierReconResult()
                        result.ysb_supplier = ysb_supplier
                        result.inbound_supplier = inbound_supplier
                        result.ysb_amount = ysb_amount
                        result.inbound_amount = inbound_amount
                        result.amount_diff = amount_diff
                        result.ysb_count = len(ysb_list)
                        result.inbound_count = len(inbound_list)
                        result.match_method = "供应商名称模糊匹配"
                        
                        if amount_diff <= self.amount_tolerance:
                            result.status = "一致"
                            result.diff_type = ""
                        else:
                            result.status = "差异"
                            result.diff_type = "供应商金额不一致"
                            result.remark = f"金额差异: {amount_diff:.2f}"
                        
                        self.supplier_results.append(result)
                        matched_suppliers.add(inbound_supplier)
                        found = True
                        break
                
                if not found:
                    if ysb_amount == Decimal("0"):
                        result = SupplierReconResult(
                            status="一致",
                            diff_type="",
                            ysb_supplier=ysb_supplier,
                            ysb_amount=ysb_amount,
                            ysb_count=len(ysb_list),
                            remark="无实际支付，无入库数据"
                        )
                    else:
                        result = SupplierReconResult(
                            status="差异",
                            diff_type="入库系统缺少供应商",
                            ysb_supplier=ysb_supplier,
                            ysb_amount=ysb_amount,
                            ysb_count=len(ysb_list),
                            remark="入库系统中未找到该供应商"
                        )
                    self.supplier_results.append(result)
        
        for inbound_supplier, inbound_list in inbound_by_supplier.items():
            if inbound_supplier not in matched_suppliers:
                inbound_amount = sum(safe_decimal(item.amount) for item in inbound_list)
                
                result = SupplierReconResult(
                    status="差异",
                    diff_type="药师帮缺少供应商",
                    inbound_supplier=inbound_supplier,
                    inbound_amount=inbound_amount,
                    inbound_count=len(inbound_list),
                    remark="药师帮对账单中未找到该供应商"
                )
                self.supplier_results.append(result)
    
    def _calculate_supplier_summary(self, ysb_summaries: list):
        self.summary.ysb_supplier_count = len(set(
            (getattr(item, 'ysb_company_name', '') or getattr(item, 'ysb_supplier_name', '')).strip()
            for item in ysb_summaries
            if (getattr(item, 'ysb_company_name', '') or getattr(item, 'ysb_supplier_name', '')).strip()
        ))
        self.summary.inbound_supplier_count = len(set(
            item.supplier_name.strip()
            for item in self.inbound_items
            if item.supplier_name.strip()
        ))
        
        for result in self.supplier_results:
            if result.status == "一致":
                self.summary.supplier_match_count += 1
            else:
                self.summary.supplier_diff_count += 1
        
        self.summary.ysb_total_amount = sum(
            self._calculate_actual_amount(item)
            for item in ysb_summaries
        )
        self.summary.inbound_total_amount = sum(
            item.amount for item in self.inbound_items
        )
    
    def _calculate_product_summary(self, ysb_items: list):
        self.summary.ysb_row_count = len(ysb_items)
        self.summary.inbound_row_count = len(self.inbound_items)
        self.summary.ysb_total_amount = sum(
            self._calculate_actual_amount(item)
            for item in ysb_items
        )
        self.summary.inbound_total_amount = sum(
            safe_decimal(item.amount)
            for item in self.inbound_items
        )
        self.summary.ysb_supplier_count = len(set(
            (getattr(item, 'ysb_company_name', '') or getattr(item, 'ysb_supplier_name', '')).strip()
            for item in ysb_items
            if (getattr(item, 'ysb_company_name', '') or getattr(item, 'ysb_supplier_name', '')).strip()
        ))
        self.summary.inbound_supplier_count = len(set(
            item.supplier_name.strip()
            for item in self.inbound_items
            if item.supplier_name.strip()
        ))
        
        for result in self.detail_results:
            if result.match_status == "自动匹配":
                self.summary.detail_matched_count += 1
            elif result.match_status == "疑似匹配":
                self.summary.detail_suspected_count += 1
            else:
                self.summary.detail_unmatched_count += 1
        
        for result in self.product_results:
            if result.status == "一致":
                self.summary.product_match_count += 1
            else:
                self.summary.product_diff_count += 1
    
    def save_results_to_db(self, db, task_id: str):
        from datetime import datetime
        
        conn = db.get_connection()
        cursor = conn.cursor()
        now = datetime.now().isoformat()
        
        try:
            for result in self.supplier_results:
                cursor.execute('''
                    INSERT INTO supplier_reconciliation_results 
                    (task_id, status, diff_type, ysb_supplier, inbound_supplier,
                     ysb_amount, inbound_amount, amount_diff, ysb_count, inbound_count,
                     match_method, remark, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (
                    task_id,
                    result.status,
                    result.diff_type,
                    result.ysb_supplier,
                    result.inbound_supplier,
                    str(result.ysb_amount),
                    str(result.inbound_amount),
                    str(result.amount_diff),
                    result.ysb_count,
                    result.inbound_count,
                    result.match_method,
                    result.remark,
                    now
                ))
            
            logging.info(f"✓ 保存供应商对账结果: {len(self.supplier_results)} 条")
            
            for result in self.product_results:
                cursor.execute('''
                    INSERT INTO product_reconciliation_results 
                    (task_id, status, diff_type, supplier, product_code, product_name,
                     spec, manufacturer, ysb_amount, inbound_amount, amount_diff,
                     ysb_quantity, inbound_quantity, quantity_diff, ysb_supplier, inbound_supplier,
                     ysb_purchase_time, inbound_date, remark, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (
                    task_id,
                    result.status,
                    result.diff_type,
                    result.supplier,
                    result.product_code,
                    result.product_name,
                    result.spec,
                    result.manufacturer,
                    str(result.ysb_amount),
                    str(result.inbound_amount),
                    str(result.amount_diff),
                    str(result.ysb_quantity),
                    str(result.inbound_quantity),
                    str(result.quantity_diff),
                    result.ysb_supplier,
                    result.inbound_supplier,
                    result.ysb_purchase_time,
                    result.inbound_date,
                    result.remark,
                    now
                ))
            
            logging.info(f"✓ 保存商品对账结果: {len(self.product_results)} 条")
            
            conn.commit()
            logging.info(f"✓ 对账结果保存成功")
            
        except Exception as e:
            conn.rollback()
            logging.error(f"❌ 保存对账结果失败: {e}")
            raise
        
        ysb_amounts = []
        for item in ysb_items:
            amount = self._calculate_actual_amount(item)
            if amount is None:
                amount = Decimal("0")
            elif isinstance(amount, str):
                try:
                    amount = Decimal(amount)
                except:
                    amount = Decimal("0")
            elif isinstance(amount, (int, float)):
                amount = Decimal(str(amount))
            elif not isinstance(amount, Decimal):
                amount = Decimal("0")
            
            ysb_amounts.append(amount)
        
        self.summary.ysb_total_amount = sum(ysb_amounts)
        
        inbound_amounts = []
        for item in self.inbound_items:
            amount = item.amount
            if amount is None:
                amount = Decimal("0")
            elif isinstance(amount, str):
                try:
                    amount = Decimal(amount)
                except:
                    amount = Decimal("0")
            elif isinstance(amount, (int, float)):
                amount = Decimal(str(amount))
            elif not isinstance(amount, Decimal):
                amount = Decimal("0")
            
            inbound_amounts.append(amount)
        
        self.summary.inbound_total_amount = sum(inbound_amounts)
    
    def _get_row_value(self, row: dict, *keys, default=""):
        if not row:
            return default
        
        normalized = {}
        for raw_key, value in row.items():
            key = str(raw_key).strip()
            normalized[key] = value
            normalized[key.lower()] = value
        
        for key in keys:
            key_text = str(key).strip()
            value = row.get(key, None)
            if value not in (None, ""):
                return value
            
            value = normalized.get(key_text, None)
            if value not in (None, ""):
                return value
            
            value = normalized.get(key_text.lower(), None)
            if value not in (None, ""):
                return value
        
        return default
    
    def _normalize_inbound_data(self, rows: list[dict]) -> list[InboundItem]:
        items = []
        
        if rows:
            sample_row = rows[0]
            logging.info(f"入库数据样例字段: {list(sample_row.keys())}")
            logging.info(f"入库数据样例值(前5条): {rows[:5] if len(rows) > 5 else rows}")
        
        for idx, row in enumerate(rows):
            item = InboundItem(raw_row_index=idx)
            
            item.inbound_no = str(self._get_row_value(
                row, 'inbound_no', '入库单号', 'ReceiveNo', 'VoucherID', 'voucherid', 'dpurinv_no'
            ))
            item.inbound_date = str(self._get_row_value(
                row, 'inbound_date', '入库日期', 'date_opr', 'purchase_time', 'PurchaseDate', 'VoucherDate'
            ))
            item.product_name = str(self._get_row_value(row, 'product_name', '商品名称', 'DrugName', 'drugname')).strip()
            item.manufacturer = str(self._get_row_value(row, 'manufacturer', '生产厂家', '厂家', 'Factory', 'factory')).strip()
            item.spec = str(self._get_row_value(row, 'spec', '规格', 'Spec', 'specification')).strip()
            
            amount_value = self._get_row_value(row, 'amount', 'dec_amt', '入库金额', default=0)
            item.quantity = self._to_decimal(self._get_row_value(row, 'quantity', 'dec_inv', '入库数量', default=0))
            item.unit_price = self._to_decimal(self._get_row_value(row, 'unit_price', 'dec_price', '入库单价', default=0))
            item.amount = self._to_decimal(amount_value)
            
            if idx < 3:
                logging.debug(f"入库行{idx}: amount={amount_value}, 解析后={item.amount}")
            
            item.supplier_code = str(self._get_row_value(
                row, 'supplier_code', '供应商编码', 'EnterpriseID', 'enterpriseid'
            ))
            item.supplier_name = str(self._get_row_value(
                row, 'supplier_name', '供应商名称', '供应商', 'enterprisename', 'EnterpriseName',
                'supplier', 'supplierName', 'SupplierName'
            )).strip()
            item.product_code = str(self._get_row_value(
                row, 'product_code', '商品编码', 'DrugCode', 'drugcode', 'id_item'
            ))
            item.ysb_code = str(self._get_row_value(row, 'ysb_code', '药师帮编码'))
            item.barcode = self._normalize_barcode(self._get_row_value(row, 'barcode', '条形码', '条码', 'BarCode'))
            item.batch_no = str(self._get_row_value(row, 'batch_no', '批号', 'batchno', 'BatchNo'))
            item.expiry_date = str(self._get_row_value(row, 'expiry_date', '有效期', 'date_exp', 'ExpiryDate'))
            
            if idx < 3:
                logging.debug(
                    f"入库行{idx}: supplier={item.supplier_name}, product_code={item.product_code}, "
                    f"amount={item.amount}"
                )
            
            items.append(item)
        
        total_amount = sum(safe_decimal(item.amount) for item in items)
        logging.info(f"入库数据解析完成: 共 {len(items)} 条, 总金额={total_amount}")
        
        return items
    
    def _to_decimal(self, value) -> Decimal:
        try:
            if value is None:
                return Decimal("0")
            return Decimal(str(value).replace(",", "").strip())
        except:
            return Decimal("0")
    
    def _normalize_barcode(self, value) -> str:
        if value is None:
            return ""
        if isinstance(value, float):
            return str(int(value))
        return str(value).strip()
    
    def _normalize_supplier_name(self, name: str) -> str:
        if not name:
            return ""
        name = name.strip()
        name = name.replace(" ", "")
        for suffix in ["有限公司", "有限责任公司", "公司", "（", "(", "）", ")"]:
            name = name.replace(suffix, "")
        return name.strip()
    
    def _prefer_same_supplier_candidates(
        self,
        candidates: list[InboundItem],
        ysb_supplier: str
    ) -> list[InboundItem]:
        if not candidates or not ysb_supplier:
            return candidates
        
        ysb_norm = self._normalize_supplier_name(ysb_supplier)
        if not ysb_norm:
            return candidates
        
        scoped = [
            item for item in candidates
            if self._normalize_supplier_name(item.supplier_name) == ysb_norm
        ]
        return scoped if scoped else candidates
    
    def _supplier_reconciliation(self, ysb_items: list, inbound_items: list[InboundItem]):
        logging.info(f"===========================================")
        logging.info(f"供应商对账 - 药师帮金额计算")
        logging.info(f"===========================================")
        
        if ysb_items:
            sample_item = ysb_items[0]
            logging.info(f"药师帮数据样例类型: {type(sample_item).__name__}")
            logging.info(f"药师帮数据样例字段: {vars(sample_item).keys() if hasattr(sample_item, '__dict__') else dir(sample_item)}")
            
            for idx, item in enumerate(ysb_items[:3]):
                actual_amount = self._calculate_actual_amount(item)
                discount = getattr(item, 'discount_amount', 'NOT_FOUND')
                logging.info(f"  样例{idx+1}: supplier={getattr(item, 'ysb_company_name', '') or getattr(item, 'ysb_supplier_name', '')}, "
                           f"actual_amount={actual_amount}, discount={discount}")
        
        ysb_by_supplier = defaultdict(list)
        for item in ysb_items:
            supplier = getattr(item, 'ysb_company_name', '') or getattr(item, 'ysb_supplier_name', '')
            supplier = supplier.strip()
            if supplier:
                ysb_by_supplier[supplier].append(item)
        
        inbound_by_supplier = defaultdict(list)
        for item in inbound_items:
            supplier = item.supplier_name.strip()
            if supplier:
                inbound_by_supplier[supplier].append(item)
        
        matched_suppliers = set()
        
        for ysb_supplier, ysb_list in ysb_by_supplier.items():
            ysb_amount_details = []
            ysb_amount = Decimal("0")
            
            for item in ysb_list:
                amount_to_add = self._calculate_actual_amount(item)
                source = "calculated"
                
                ysb_amount += amount_to_add
                ysb_amount_details.append(f"{amount_to_add}({source})")
                
                if len(ysb_amount_details) <= 2:
                    logging.debug(f"    {getattr(item, 'ysb_company_name', '') or getattr(item, 'ysb_supplier_name', '')}: "
                                 f"actual={actual_payment}, discount={discount_amt}, 使用={source}, 金额={amount_to_add}")
            
            logging.info(f"供应商 [{ysb_supplier}]: 共{len(ysb_list)}条记录, 总金额={ysb_amount}")
            logging.info(f"  明细: {' | '.join(ysb_amount_details)}")
            
            if ysb_supplier in inbound_by_supplier:
                inbound_list = inbound_by_supplier[ysb_supplier]
                inbound_amount = sum(safe_decimal(item.amount) for item in inbound_list)
                amount_diff = abs(ysb_amount - inbound_amount)
                
                result = SupplierReconResult()
                result.ysb_supplier = ysb_supplier
                result.inbound_supplier = ysb_supplier
                result.ysb_amount = ysb_amount
                result.inbound_amount = inbound_amount
                result.amount_diff = amount_diff
                result.ysb_count = len(ysb_list)
                result.inbound_count = len(inbound_list)
                result.match_method = "供应商名称完全匹配"
                
                if amount_diff <= self.amount_tolerance:
                    result.status = "一致"
                    result.diff_type = ""
                else:
                    result.status = "差异"
                    result.diff_type = "供应商金额不一致"
                    result.remark = f"金额差异: {amount_diff:.2f}"
                
                self.supplier_results.append(result)
                matched_suppliers.add(ysb_supplier)
            else:
                found = False
                ysb_norm = self._normalize_supplier_name(ysb_supplier)
                for inbound_supplier in inbound_by_supplier:
                    inbound_norm = self._normalize_supplier_name(inbound_supplier)
                    if ysb_norm and inbound_norm and ysb_norm == inbound_norm:
                        inbound_list = inbound_by_supplier[inbound_supplier]
                        inbound_amount = sum(safe_decimal(item.amount) for item in inbound_list)
                        amount_diff = abs(ysb_amount - inbound_amount)
                        
                        result = SupplierReconResult()
                        result.ysb_supplier = ysb_supplier
                        result.inbound_supplier = inbound_supplier
                        result.ysb_amount = ysb_amount
                        result.inbound_amount = inbound_amount
                        result.amount_diff = amount_diff
                        result.ysb_count = len(ysb_list)
                        result.inbound_count = len(inbound_list)
                        result.match_method = "供应商名称模糊匹配"
                        
                        if amount_diff <= self.amount_tolerance:
                            result.status = "一致"
                            result.diff_type = ""
                        else:
                            result.status = "差异"
                            result.diff_type = "供应商金额不一致"
                            result.remark = f"金额差异: {amount_diff:.2f}"
                        
                        self.supplier_results.append(result)
                        matched_suppliers.add(inbound_supplier)
                        found = True
                        break
                
                if not found:
                    result = SupplierReconResult(
                        status="差异",
                        diff_type="入库系统缺少供应商",
                        ysb_supplier=ysb_supplier,
                        ysb_amount=ysb_amount,
                        ysb_count=len(ysb_list),
                        remark="入库系统中未找到该供应商"
                    )
                    self.supplier_results.append(result)
        
        for inbound_supplier, inbound_list in inbound_by_supplier.items():
            if inbound_supplier not in matched_suppliers:
                inbound_amount = sum(safe_decimal(item.amount) for item in inbound_list)
                
                result = SupplierReconResult(
                    status="差异",
                    diff_type="药师帮缺少供应商",
                    inbound_supplier=inbound_supplier,
                    inbound_amount=inbound_amount,
                    inbound_count=len(inbound_list),
                    remark="药师帮对账单中未找到该供应商"
                )
                self.supplier_results.append(result)
    
    def _detail_matching(self, ysb_items: list, inbound_items: list[InboundItem]):
        inbound_by_barcode = defaultdict(list)
        inbound_by_name = defaultdict(list)
        inbound_by_name_only = defaultdict(list)
        inbound_by_name_spec = defaultdict(list)
        
        for item in inbound_items:
            if item.barcode:
                inbound_by_barcode[item.barcode].append(item)
            
            key = f"{item.product_name}|{item.spec}|{item.manufacturer}"
            if item.product_name:
                inbound_by_name[key].append(item)
                
                name_only_key = item.product_name.strip()
                inbound_by_name_only[name_only_key].append(item)
                
                name_spec_key = f"{item.product_name}|{item.spec}"
                inbound_by_name_spec[name_spec_key].append(item)
        
        unmatched_items = []
        
        for item in ysb_items:
            result = DetailMatchResult()
            result.raw_row_index = getattr(item, 'raw_row_index', 0)
            result.ysb_order_no = getattr(item, 'ysb_order_no', '')
            result.ysb_supplier = getattr(item, 'ysb_company_name', '') or getattr(item, 'ysb_supplier_name', '')
            result.product_name = getattr(item, 'product_name', '')
            result.spec = getattr(item, 'spec', '')
            result.manufacturer = getattr(item, 'manufacturer', '')
            result.barcode = getattr(item, 'barcode', '')
            result.ysb_quantity = getattr(item, 'quantity', Decimal("0"))
            result.ysb_amount = self._calculate_actual_amount(item)
            
            purchase_time = getattr(item, 'purchase_time', None)
            if purchase_time:
                result.ysb_purchase_time = str(purchase_time)
            
            ysb_barcode = result.barcode
            ysb_product_name = result.product_name.strip()
            ysb_spec = result.spec.strip()
            ysb_manufacturer = result.manufacturer.strip()
            scoped_inbound_items = self._prefer_same_supplier_candidates(inbound_items, result.ysb_supplier)
            
            matched_item = None
            match_score = 0.0
            match_method = ""
            
            if ysb_barcode and ysb_barcode in inbound_by_barcode:
                candidates = self._prefer_same_supplier_candidates(inbound_by_barcode[ysb_barcode], result.ysb_supplier)
                if len(candidates) == 1:
                    matched_item = candidates[0]
                    match_score = 100.0
                    match_method = "条形码精确匹配"
                else:
                    best_score = 0
                    best_item = None
                    for candidate in candidates:
                        score = self._calculate_match_score(
                            ysb_product_name, ysb_spec, ysb_manufacturer,
                            candidate.product_name, candidate.spec, candidate.manufacturer
                        )
                        if score > best_score:
                            best_score = score
                            best_item = candidate
                    
                    if best_item:
                        matched_item = best_item
                        match_score = 95.0 + best_score * 0.05
                        match_method = "条形码+名称匹配"
            
            if not matched_item and ysb_product_name:
                key = f"{ysb_product_name}|{ysb_spec}|{ysb_manufacturer}"
                if key in inbound_by_name:
                    candidates = self._prefer_same_supplier_candidates(inbound_by_name[key], result.ysb_supplier)
                    if len(candidates) == 1:
                        matched_item = candidates[0]
                        match_score = 90.0
                        match_method = "名称规格厂家精确匹配"
                    else:
                        best_score = 0
                        best_item = None
                        for candidate in candidates:
                            score = self._calculate_match_score(
                                ysb_product_name, ysb_spec, ysb_manufacturer,
                                candidate.product_name, candidate.spec, candidate.manufacturer
                            )
                            if score > best_score:
                                best_score = score
                                best_item = candidate
                        
                        if best_item:
                            matched_item = best_item
                            match_score = 80.0 + best_score * 0.2
                            match_method = "名称规格厂家模糊匹配"
            
            if not matched_item and ysb_product_name and ysb_spec:
                name_spec_key = f"{ysb_product_name}|{ysb_spec}"
                if name_spec_key in inbound_by_name_spec:
                    candidates = self._prefer_same_supplier_candidates(inbound_by_name_spec[name_spec_key], result.ysb_supplier)
                    if len(candidates) == 1:
                        matched_item = candidates[0]
                        match_score = 75.0
                        match_method = "名称规格精确匹配(忽略厂家)"
                    else:
                        best_score = 0
                        best_item = None
                        for candidate in candidates:
                            score = self._calculate_match_score(
                                ysb_product_name, ysb_spec, ysb_manufacturer,
                                candidate.product_name, candidate.spec, candidate.manufacturer
                            )
                            if score > best_score:
                                best_score = score
                                best_item = candidate
                        
                        if best_item:
                            matched_item = best_item
                            match_score = 65.0 + best_score * 0.15
                            match_method = "名称规格模糊匹配(忽略厂家)"
            
            if not matched_item and ysb_product_name:
                if ysb_product_name in inbound_by_name_only:
                    candidates = self._prefer_same_supplier_candidates(inbound_by_name_only[ysb_product_name], result.ysb_supplier)
                    if len(candidates) == 1:
                        matched_item = candidates[0]
                        match_score = 60.0
                        match_method = "仅名称精确匹配"
                    else:
                        best_score = 0
                        best_item = None
                        for candidate in candidates:
                            score = self._calculate_match_score(
                                ysb_product_name, ysb_spec, ysb_manufacturer,
                                candidate.product_name, candidate.spec, candidate.manufacturer
                            )
                            if score > best_score:
                                best_score = score
                                best_item = candidate
                        
                        if best_item:
                            matched_item = best_item
                            match_score = 50.0 + best_score * 0.2
                            match_method = "仅名称模糊匹配"
            
            if not matched_item and ysb_product_name:
                best_score = 0
                best_item = None
                best_method = ""
                
                for inbound_item in scoped_inbound_items:
                    if not inbound_item.product_name:
                        continue
                    
                    name_sim = self._string_similarity(ysb_product_name, inbound_item.product_name)
                    
                    if name_sim < 0.6:
                        continue
                    
                    score = name_sim * 50
                    
                    if ysb_spec and inbound_item.spec:
                        spec_sim = self._string_similarity(ysb_spec, inbound_item.spec)
                        score += spec_sim * 20
                    
                    if ysb_manufacturer and inbound_item.manufacturer:
                        mfr_sim = self._string_similarity(ysb_manufacturer, inbound_item.manufacturer)
                        score += mfr_sim * 15
                    
                    if score > best_score:
                        best_score = score
                        best_item = inbound_item
                        best_method = "全局名称模糊匹配"
                
                if best_item and best_score >= 40.0:
                    matched_item = best_item
                    match_score = best_score
                    match_method = best_method
            
            if matched_item:
                result.matched_product_code = matched_item.product_code
                result.matched_supplier_name = matched_item.supplier_name
                result.matched_product_name = matched_item.product_name
                result.matched_spec = matched_item.spec
                result.matched_manufacturer = matched_item.manufacturer
                result.match_method = match_method
                result.match_score = match_score
                
                if match_score >= self.auto_match_threshold:
                    result.match_status = "自动匹配"
                elif match_score >= self.suspected_match_threshold:
                    result.match_status = "疑似匹配"
                    result.match_remark = "需要人工确认"
                else:
                    result.match_status = "低分匹配"
                    result.match_remark = "匹配分数较低，建议人工确认"
            else:
                result.match_status = "未匹配"
                result.match_remark = "未找到匹配的入库商品"
                unmatched_items.append({
                    'supplier': result.ysb_supplier,
                    'name': ysb_product_name,
                    'spec': ysb_spec,
                    'manufacturer': ysb_manufacturer,
                    'barcode': ysb_barcode,
                    'order_no': result.ysb_order_no
                })
            
            self.detail_results.append(result)
        
        if unmatched_items:
            logging.warning(f"===========================================")
            logging.warning(f"未匹配商品统计: 共{len(unmatched_items)}条")
            logging.warning(f"===========================================")
            
            for idx, item in enumerate(unmatched_items[:10], 1):
                logging.warning(f"  未匹配{idx}:")
                logging.warning(f"    供应商: {item['supplier']}")
                logging.warning(f"    商品名: {item['name']}")
                logging.warning(f"    规格: {item['spec']}")
                logging.warning(f"    厂家: {item['manufacturer']}")
                logging.warning(f"    条码: {item['barcode']}")
                logging.warning(f"    订单号: {item['order_no']}")
            
            if len(unmatched_items) > 10:
                logging.warning(f"  ... 还有{len(unmatched_items) - 10}条未匹配商品")
            
            logging.warning(f"===========================================")
    
    def _calculate_match_score(
        self,
        name1: str, spec1: str, mfr1: str,
        name2: str, spec2: str, mfr2: str
    ) -> float:
        score = 0.0
        
        if name1 and name2:
            name_score = self._string_similarity(name1, name2)
            score += name_score * 40
        
        if spec1 and spec2:
            spec_score = self._string_similarity(spec1, spec2)
            score += spec_score * 25
        elif not spec1 and not spec2:
            score += 25
        
        if mfr1 and mfr2:
            mfr_score = self._string_similarity(mfr1, mfr2)
            score += mfr_score * 25
        elif not mfr1 and not mfr2:
            score += 25
        
        return score
    
    def _string_similarity(self, s1: str, s2: str) -> float:
        if not s1 or not s2:
            return 0.0
        
        s1 = s1.strip().lower()
        s2 = s2.strip().lower()
        
        if s1 == s2:
            return 1.0
        
        if s1 in s2 or s2 in s1:
            return 0.9
        
        len1, len2 = len(s1), len(s2)
        if len1 == 0 or len2 == 0:
            return 0.0
        
        max_len = max(len1, len2)
        min_len = min(len1, len2)
        
        match_count = 0
        for i in range(min_len):
            if s1[i] == s2[i]:
                match_count += 1
        
        position_score = match_count / max_len
        
        words1 = set(s1.replace('|', ' ').replace('/', ' ').replace('\\', ' ').replace('(', ' ').replace(')', ' ').replace('（', ' ').replace('）', ' ').split())
        words2 = set(s2.replace('|', ' ').replace('/', ' ').replace('\\', ' ').replace('(', ' ').replace(')', ' ').replace('（', ' ').replace('）', ' ').split())
        
        if words1 and words2:
            intersection = words1 & words2
            union = words1 | words2
            jaccard_score = len(intersection) / len(union) if union else 0.0
        else:
            jaccard_score = 0.0
        
        final_score = max(position_score, jaccard_score * 0.8)
        
        return final_score
    
    def _product_reconciliation(self):
        ysb_by_product = defaultdict(list)
        inbound_by_product = defaultdict(list)
        
        for result in self.detail_results:
            if result.matched_product_code and result.match_status == "自动匹配":
                key = (
                    self._normalize_supplier_name(result.ysb_supplier),
                    result.matched_product_code
                )
                ysb_by_product[key].append(result)
        
        for item in self.inbound_items:
            supplier_key = self._normalize_supplier_name(item.supplier_name)
            if supplier_key and item.product_code:
                inbound_by_product[(supplier_key, item.product_code)].append(item)
        
        all_keys = set(ysb_by_product.keys()) | set(inbound_by_product.keys())
        
        for key in sorted(all_keys):
            ysb_list = ysb_by_product.get(key, [])
            inbound_list = inbound_by_product.get(key, [])
            
            ysb_amount = sum(safe_decimal(r.ysb_amount) for r in ysb_list)
            ysb_quantity = sum(safe_decimal(r.ysb_quantity) for r in ysb_list)
            inbound_amount = sum(safe_decimal(item.amount) for item in inbound_list)
            inbound_quantity = sum(safe_decimal(item.quantity) for item in inbound_list)
            amount_diff = inbound_amount - ysb_amount
            quantity_diff = inbound_quantity - ysb_quantity
            
            result = ProductReconResult()
            result.product_code = key[1]
            result.ysb_amount = ysb_amount
            result.ysb_quantity = ysb_quantity
            result.inbound_amount = inbound_amount
            result.inbound_quantity = inbound_quantity
            result.amount_diff = amount_diff
            result.quantity_diff = quantity_diff
            
            if ysb_list:
                first_ysb = ysb_list[0]
                result.supplier = first_ysb.ysb_supplier
                result.ysb_supplier = first_ysb.ysb_supplier
                result.inbound_supplier = first_ysb.matched_supplier_name
                result.product_name = first_ysb.matched_product_name
                result.spec = first_ysb.matched_spec
                result.manufacturer = first_ysb.matched_manufacturer
                
                if hasattr(first_ysb, 'ysb_purchase_time') and first_ysb.ysb_purchase_time:
                    result.ysb_purchase_time = str(first_ysb.ysb_purchase_time)
            
            if inbound_list:
                first_inbound = inbound_list[0]
                if not result.supplier:
                    result.supplier = first_inbound.supplier_name
                if not result.inbound_supplier:
                    result.inbound_supplier = first_inbound.supplier_name
                if not result.product_name:
                    result.product_name = first_inbound.product_name
                if not result.spec:
                    result.spec = first_inbound.spec
                if not result.manufacturer:
                    result.manufacturer = first_inbound.manufacturer
                
                if first_inbound.inbound_date:
                    result.inbound_date = str(first_inbound.inbound_date)
            
            if not ysb_list:
                result.status = "差异"
                result.diff_type = "药师帮缺少供应商商品"
                result.remark = "入库系统存在该供应商商品，药师帮明细汇总中未找到"
            elif not inbound_list:
                result.status = "差异"
                result.diff_type = "入库系统缺少供应商商品"
                result.remark = "药师帮明细已匹配商品编码，但入库系统汇总中未找到"
            elif abs(amount_diff) > self.amount_tolerance:
                result.status = "差异"
                result.diff_type = "供应商商品金额不一致"
                result.remark = f"金额差异: {amount_diff:.2f}"
            elif abs(quantity_diff) > self.quantity_tolerance:
                result.status = "一致"
                result.diff_type = "供应商商品数量不一致"
                result.remark = f"数量差异仅提示: {quantity_diff:.2f}"
            else:
                result.status = "一致"
                result.diff_type = ""
            
            self.product_results.append(result)
        
        unmatched = [
            r for r in self.detail_results
            if not r.matched_product_code or r.match_status != "自动匹配"
        ]
        for result in unmatched:
            prod_result = ProductReconResult()
            prod_result.supplier = result.ysb_supplier
            prod_result.product_code = result.matched_product_code
            prod_result.product_name = result.product_name
            prod_result.spec = result.spec
            prod_result.manufacturer = result.manufacturer
            prod_result.ysb_supplier = result.ysb_supplier
            prod_result.inbound_supplier = result.matched_supplier_name
            prod_result.ysb_amount = result.ysb_amount
            prod_result.ysb_quantity = result.ysb_quantity
            prod_result.status = "差异"
            prod_result.diff_type = "明细未匹配商品编码" if not result.matched_product_code else "明细未确认商品编码"
            prod_result.remark = result.match_remark or result.match_status
            
            self.product_results.append(prod_result)
    
    def _calculate_summary(self, ysb_items: list, inbound_items: list[InboundItem]):
        self.summary.ysb_row_count = len(ysb_items)
        self.summary.inbound_row_count = len(inbound_items)
        
        ysb_suppliers = set()
        inbound_suppliers = set()
        
        for item in ysb_items:
            supplier = (getattr(item, 'ysb_company_name', '') or getattr(item, 'ysb_supplier_name', '')).strip()
            if supplier:
                ysb_suppliers.add(supplier)
            self.summary.ysb_total_amount += self._calculate_actual_amount(item)
        
        for item in inbound_items:
            if item.supplier_name.strip():
                inbound_suppliers.add(item.supplier_name.strip())
            self.summary.inbound_total_amount += item.amount
        
        self.summary.ysb_supplier_count = len(ysb_suppliers)
        self.summary.inbound_supplier_count = len(inbound_suppliers)
        
        for result in self.supplier_results:
            if result.status == "一致":
                self.summary.supplier_match_count += 1
            else:
                self.summary.supplier_diff_count += 1
        
        for result in self.detail_results:
            if result.match_status == "自动匹配":
                self.summary.detail_matched_count += 1
            elif result.match_status == "疑似匹配":
                self.summary.detail_suspected_count += 1
            else:
                self.summary.detail_unmatched_count += 1
        
        for result in self.product_results:
            if result.status == "一致":
                self.summary.product_match_count += 1
            else:
                self.summary.product_diff_count += 1
