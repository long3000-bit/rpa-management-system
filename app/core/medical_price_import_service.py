"""
医保价格管控 - Excel导入服务

支持导入以下数据源：
1. 医保目录-西药（标准库药品发布信息、停用、新增、修改）
2. 医保目录-中成药（标准库药品发布信息、停用、新增、修改）
3. 医保价格上限
4. 云药店商品目录
"""

import logging
import json
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, List, Any
from dataclasses import dataclass, field

import openpyxl
from openpyxl.worksheet.worksheet import Worksheet

from app.storage.database import Database


@dataclass
class MedicalImportResult:
    """导入结果"""
    batch_id: str
    batch_type: str
    file_name: str
    sheet_name: str
    total_rows: int = 0
    success_rows: int = 0
    failed_rows: int = 0
    import_status: str = "pending"
    error_message: str = ""
    failures: List[Dict] = field(default_factory=list)


class MedicalPriceImportService:
    """医保价格管控导入服务"""
    
    # 数据源类型
    BATCH_TYPES = {
        "medical_catalog_western": "医保目录-西药",
        "medical_catalog_chinese": "医保目录-中成药",
        "medical_price_limit": "医保价格上限",
        "cloud_pharmacy_catalog": "云药店商品目录",
    }
    
    # 西药/中成药工作表配置
    MEDICAL_CATALOG_SHEETS = {
        "标准库药品发布信息（西药）": {"type": "main", "header_row": 2},
        "标准库药品发布信息(中成药)": {"type": "main", "header_row": 2},
        "停用": {"type": "stop", "header_row": 1},
        "新增": {"type": "add", "header_row": 1},
        "修改": {"type": "modify", "header_row": 1},
    }
    
    # 西药目录字段映射
    WESTERN_CATALOG_COLUMNS = [
        "国家药品代码", "甲乙类", "药品名称", "英文名称", "剂型", "规格",
        "包装规格", "计价单位", "计价规格", "最小包装单位", "最小包装数量",
        "转换比", "企业名称", "质量层次", "备注", "限制使用范围",
        "医保基础价格", "医保支付标准"
    ]
    
    # 中成药目录字段映射
    CHINESE_CATALOG_COLUMNS = [
        "国家药品代码", "甲乙类", "药品名称", "英文名称", "剂型", "规格",
        "包装规格", "计价单位", "计价规格", "最小包装单位", "最小包装数量",
        "转换比", "企业名称", "质量层次", "备注", "限制使用范围",
        "医保基础价格", "医保支付标准"
    ]
    
    # 医保价格上限字段映射
    PRICE_LIMIT_COLUMNS = [
        "医保编码", "药品名称", "剂型", "规格", "包装规格", "计价单位",
        "企业名称", "医保价格上限", "价格生效日期", "备注"
    ]
    
    # 云药店商品目录字段映射
    CLOUD_PHARMACY_COLUMNS = [
        "商品编码", "旧商品编码", "商品名称", "通用名", "规格", "剂型",
        "包装规格", "单位", "生产厂家", "批准文号", "医保编码", "医保类型",
        "商品状态", "创建时间", "更新时间"
    ]
    
    def __init__(self, db: Database):
        self.db = db
    
    def generate_batch_id(self) -> str:
        """生成批次ID"""
        return f"MED_{datetime.now().strftime('%Y%m%d%H%M%S')}_{uuid.uuid4().hex[:8]}"
    
    def import_medical_catalog_western(
        self, 
        file_path: str, 
        sheet_name: str = None,
        imported_by: str = "admin"
    ) -> MedicalImportResult:
        """导入医保目录-西药"""
        return self._import_medical_catalog(
            file_path=file_path,
            batch_type="medical_catalog_western",
            table_name="medical_catalog_western",
            sheet_name=sheet_name,
            imported_by=imported_by
        )
    
    def import_medical_catalog_chinese(
        self, 
        file_path: str, 
        sheet_name: str = None,
        imported_by: str = "admin"
    ) -> MedicalImportResult:
        """导入医保目录-中成药"""
        return self._import_medical_catalog(
            file_path=file_path,
            batch_type="medical_catalog_chinese",
            table_name="medical_catalog_chinese",
            sheet_name=sheet_name,
            imported_by=imported_by
        )
    
    def import_medical_price_limit(
        self, 
        file_path: str, 
        sheet_name: str = None,
        imported_by: str = "admin"
    ) -> MedicalImportResult:
        """导入医保价格上限"""
        batch_id = self.generate_batch_id()
        result = MedicalImportResult(
            batch_id=batch_id,
            batch_type="medical_price_limit",
            file_name=Path(file_path).name,
            sheet_name=sheet_name or "sheet"
        )
        
        try:
            workbook = openpyxl.load_workbook(file_path, read_only=True, data_only=True)
            
            # 获取工作表
            if sheet_name:
                ws = workbook[sheet_name]
            else:
                # 默认取第一个工作表
                ws = workbook.active
                result.sheet_name = ws.title
            
            # 读取表头（第1行）
            headers = []
            for cell in ws[1]:
                headers.append(str(cell.value or "").strip())
            
            # 导入数据
            conn = self.db.get_connection()
            cursor = conn.cursor()
            now = datetime.now().isoformat()
            
            for row_idx, row in enumerate(ws.iter_rows(min_row=2), start=2):
                try:
                    row_data = {}
                    for col_idx, cell in enumerate(row):
                        if col_idx < len(headers):
                            row_data[headers[col_idx]] = str(cell.value or "").strip()
                    
                    # 转换为JSON存储原始数据
                    raw_data_json = json.dumps(row_data, ensure_ascii=False)
                    
                    # 插入数据
                    cursor.execute('''
                        INSERT INTO medical_price_limit (
                            batch_id, row_index, 医保编码, 药品名称, 剂型, 规格,
                            包装规格, 计价单位, 企业名称, 医保价格上限, 价格生效日期,
                            备注, 原始数据, created_at
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ''', (
                        batch_id, row_idx,
                        row_data.get("医保编码", ""),
                        row_data.get("药品名称", ""),
                        row_data.get("剂型", ""),
                        row_data.get("规格", ""),
                        row_data.get("包装规格", ""),
                        row_data.get("计价单位", ""),
                        row_data.get("企业名称", ""),
                        row_data.get("医保价格上限", ""),
                        row_data.get("价格生效日期", ""),
                        row_data.get("备注", ""),
                        raw_data_json,
                        now
                    ))
                    
                    result.success_rows += 1
                    
                except Exception as e:
                    result.failed_rows += 1
                    result.failures.append({
                        "row_index": row_idx,
                        "raw_data": json.dumps(row_data, ensure_ascii=False),
                        "failure_reason": str(e)
                    })
                    logging.warning(f"导入行 {row_idx} 失败: {e}")
            
            result.total_rows = result.success_rows + result.failed_rows
            result.import_status = "success" if result.failed_rows == 0 else "partial"
            
            conn.commit()
            workbook.close()
            
            # 记录批次
            self._save_batch_record(result, file_path, imported_by)
            
            logging.info(f"医保价格上限导入完成: {result.success_rows}/{result.total_rows} 行")
            
        except Exception as e:
            result.import_status = "failed"
            result.error_message = str(e)
            logging.error(f"导入医保价格上限失败: {e}")
        
        return result
    
    def import_cloud_pharmacy_catalog(
        self, 
        file_path: str, 
        sheet_name: str = None,
        imported_by: str = "admin"
    ) -> MedicalImportResult:
        """导入云药店商品目录"""
        batch_id = self.generate_batch_id()
        result = MedicalImportResult(
            batch_id=batch_id,
            batch_type="cloud_pharmacy_catalog",
            file_name=Path(file_path).name,
            sheet_name=sheet_name or "商品信息维护"
        )
        
        try:
            # 使用pandas读取Excel文件（解决openpyxl read_only模式的问题）
            import pandas as pd
            
            # 读取Excel文件
            if sheet_name:
                df = pd.read_excel(file_path, sheet_name=sheet_name)
                result.sheet_name = sheet_name
            else:
                # 尝试查找"商品信息维护"工作表
                all_sheets = pd.read_excel(file_path, sheet_name=None)
                for sheet_title, sheet_df in all_sheets.items():
                    if "商品信息维护" in sheet_title:
                        df = sheet_df
                        result.sheet_name = sheet_title
                        break
                else:
                    # 使用第一个工作表
                    df = pd.read_excel(file_path, sheet_name=0)
                    result.sheet_name = list(all_sheets.keys())[0] if all_sheets else "sheet"
            
            # 列名映射（适配实际导出的列名）
            column_mapping = {
                "商品规格": "规格",
                "生产企业": "生产厂家",
                "商品编码": "商品编码",
                "旧商品编码": "旧商品编码",
                "商品名称": "商品名称",
                "通用名": "通用名",
                "剂型": "剂型",
                "包装规格": "包装规格",
                "单位": "单位",
                "批准文号": "批准文号",
                "医保编码": "医保编码",
                "医保类型": "医保类型",
                "商品状态": "商品状态",
                "创建时间": "创建时间",
                "更新时间": "更新时间"
            }
            
            # 导入数据
            conn = self.db.get_connection()
            cursor = conn.cursor()
            now = datetime.now().isoformat()
            
            for row_idx, row in df.iterrows():
                try:
                    # 转换行数据
                    row_data = {}
                    for col_name in df.columns:
                        value = row[col_name]
                        # 处理NaN值
                        if pd.isna(value):
                            row_data[col_name] = ""
                        else:
                            row_data[col_name] = str(value).strip()
                    
                    # 转换为JSON存储原始数据
                    raw_data_json = json.dumps(row_data, ensure_ascii=False)
                    
                    # 应用列名映射
                    mapped_data = {}
                    for col_name, value in row_data.items():
                        mapped_name = column_mapping.get(col_name, col_name)
                        mapped_data[mapped_name] = value
                    
                    # 插入数据
                    cursor.execute('''
                        INSERT INTO cloud_pharmacy_catalog (
                            batch_id, row_index, 商品编码, 旧商品编码, 商品名称, 通用名,
                            规格, 剂型, 包装规格, 单位, 生产厂家, 批准文号, 医保编码,
                            医保类型, 商品状态, 创建时间, 更新时间, 原始数据, created_at
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ''', (
                        batch_id, row_idx + 2,  # Excel行号从2开始（第1行是表头）
                        mapped_data.get("商品编码", ""),
                        mapped_data.get("旧商品编码", ""),
                        mapped_data.get("商品名称", ""),
                        mapped_data.get("通用名", ""),
                        mapped_data.get("规格", ""),
                        mapped_data.get("剂型", ""),
                        mapped_data.get("包装规格", ""),
                        mapped_data.get("单位", ""),
                        mapped_data.get("生产厂家", ""),
                        mapped_data.get("批准文号", ""),
                        mapped_data.get("医保编码", ""),
                        mapped_data.get("医保类型", ""),
                        mapped_data.get("商品状态", ""),
                        mapped_data.get("创建时间", ""),
                        mapped_data.get("更新时间", ""),
                        raw_data_json,
                        now
                    ))
                    
                    result.success_rows += 1
                    
                except Exception as e:
                    result.failed_rows += 1
                    result.failures.append({
                        "row_index": row_idx + 2,
                        "raw_data": json.dumps(row_data, ensure_ascii=False) if row_data else "",
                        "failure_reason": str(e)
                    })
                    logging.warning(f"导入行 {row_idx + 2} 失败: {e}")
            
            result.total_rows = result.success_rows + result.failed_rows
            result.import_status = "success" if result.failed_rows == 0 else "partial"
            
            conn.commit()
            
            # 记录批次
            self._save_batch_record(result, file_path, imported_by)
            
            logging.info(f"云药店商品目录导入完成: {result.success_rows}/{result.total_rows} 行")
            
        except Exception as e:
            result.import_status = "failed"
            result.error_message = str(e)
            logging.error(f"导入云药店商品目录失败: {e}")
        
        return result
    
    def _import_medical_catalog(
        self,
        file_path: str,
        batch_type: str,
        table_name: str,
        sheet_name: str = None,
        imported_by: str = "admin"
    ) -> MedicalImportResult:
        """导入医保目录（西药/中成药）"""
        batch_id = self.generate_batch_id()
        result = MedicalImportResult(
            batch_id=batch_id,
            batch_type=batch_type,
            file_name=Path(file_path).name,
            sheet_name=sheet_name or "全部"
        )
        
        try:
            workbook = openpyxl.load_workbook(file_path, read_only=True, data_only=True)
            
            # 确定要导入的工作表
            sheets_to_import = []
            
            if sheet_name:
                # 指定单个工作表
                sheets_to_import = [(sheet_name, self.MEDICAL_CATALOG_SHEETS.get(sheet_name, {"type": "unknown", "header_row": 1}))]
            else:
                # 导入所有相关工作表
                for sheet_title in workbook.sheetnames:
                    if sheet_title in self.MEDICAL_CATALOG_SHEETS:
                        sheets_to_import.append((sheet_title, self.MEDICAL_CATALOG_SHEETS[sheet_title]))
            
            conn = self.db.get_connection()
            cursor = conn.cursor()
            now = datetime.now().isoformat()
            
            for sheet_title, sheet_config in sheets_to_import:
                ws = workbook[sheet_title]
                sheet_type = sheet_config["type"]
                header_row = sheet_config["header_row"]
                
                # 读取表头
                headers = []
                for cell in ws[header_row]:
                    headers.append(str(cell.value or "").strip())
                
                # 导入数据
                for row_idx, row in enumerate(ws.iter_rows(min_row=header_row + 1), start=header_row + 1):
                    try:
                        row_data = {}
                        for col_idx, cell in enumerate(row):
                            if col_idx < len(headers):
                                row_data[headers[col_idx]] = str(cell.value or "").strip()
                        
                        # 转换为JSON存储原始数据
                        raw_data_json = json.dumps(row_data, ensure_ascii=False)
                        
                        # 构建插入语句
                        columns = [
                            "batch_id", "sheet_type", "row_index",
                            "国家药品代码", "甲乙类", "药品名称", "英文名称", "剂型", "规格",
                            "包装规格", "计价单位", "计价规格", "最小包装单位", "最小包装数量",
                            "转换比", "企业名称", "质量层次", "备注", "限制使用范围",
                            "医保基础价格", "医保支付标准", "原始数据", "created_at"
                        ]
                        
                        values = [
                            batch_id, sheet_type, row_idx,
                            row_data.get("国家药品代码", ""),
                            row_data.get("甲乙类", ""),
                            row_data.get("药品名称", ""),
                            row_data.get("英文名称", ""),
                            row_data.get("剂型", ""),
                            row_data.get("规格", ""),
                            row_data.get("包装规格", ""),
                            row_data.get("计价单位", ""),
                            row_data.get("计价规格", ""),
                            row_data.get("最小包装单位", ""),
                            row_data.get("最小包装数量", ""),
                            row_data.get("转换比", ""),
                            row_data.get("企业名称", ""),
                            row_data.get("质量层次", ""),
                            row_data.get("备注", ""),
                            row_data.get("限制使用范围", ""),
                            row_data.get("医保基础价格", ""),
                            row_data.get("医保支付标准", ""),
                            raw_data_json,
                            now
                        ]
                        
                        cursor.execute(f'''
                            INSERT INTO {table_name} (
                                {', '.join(columns)}
                            ) VALUES (
                                {', '.join(['?' for _ in columns])}
                            )
                        ''', values)
                        
                        result.success_rows += 1
                        
                    except Exception as e:
                        result.failed_rows += 1
                        result.failures.append({
                            "row_index": row_idx,
                            "sheet_name": sheet_title,
                            "raw_data": json.dumps(row_data, ensure_ascii=False),
                            "failure_reason": str(e)
                        })
                        logging.warning(f"导入 {sheet_title} 行 {row_idx} 失败: {e}")
            
            result.total_rows = result.success_rows + result.failed_rows
            result.import_status = "success" if result.failed_rows == 0 else "partial"
            
            conn.commit()
            workbook.close()
            
            # 记录批次
            self._save_batch_record(result, file_path, imported_by)
            
            logging.info(f"{self.BATCH_TYPES[batch_type]}导入完成: {result.success_rows}/{result.total_rows} 行")
            
        except Exception as e:
            result.import_status = "failed"
            result.error_message = str(e)
            logging.error(f"导入{self.BATCH_TYPES[batch_type]}失败: {e}")
        
        return result
    
    def _save_batch_record(
        self, 
        result: MedicalImportResult, 
        file_path: str, 
        imported_by: str
    ):
        """保存批次记录"""
        conn = self.db.get_connection()
        cursor = conn.cursor()
        now = datetime.now().isoformat()
        
        cursor.execute('''
            INSERT INTO medical_import_batches (
                batch_id, batch_type, file_name, file_path, sheet_name,
                total_rows, success_rows, failed_rows, import_status,
                imported_by, imported_at, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            result.batch_id,
            result.batch_type,
            result.file_name,
            file_path,
            result.sheet_name,
            result.total_rows,
            result.success_rows,
            result.failed_rows,
            result.import_status,
            imported_by,
            now,
            now
        ))
        
        # 保存失败明细
        for failure in result.failures:
            cursor.execute('''
                INSERT INTO medical_import_failures (
                    batch_id, row_index, raw_data, failure_reason, created_at
                ) VALUES (?, ?, ?, ?, ?)
            ''', (
                result.batch_id,
                failure.get("row_index", 0),
                failure.get("raw_data", ""),
                failure.get("failure_reason", ""),
                now
            ))
        
        conn.commit()
    
    def get_import_batches(
        self, 
        batch_type: str = None, 
        limit: int = 50
    ) -> List[Dict]:
        """获取导入批次列表"""
        conn = self.db.get_connection()
        cursor = conn.cursor()
        
        if batch_type:
            cursor.execute('''
                SELECT * FROM medical_import_batches 
                WHERE batch_type = ?
                ORDER BY created_at DESC
                LIMIT ?
            ''', (batch_type, limit))
        else:
            cursor.execute('''
                SELECT * FROM medical_import_batches 
                ORDER BY created_at DESC
                LIMIT ?
            ''', (limit,))
        
        return [dict(row) for row in cursor.fetchall()]
    
    def get_batch_detail(self, batch_id: str) -> Dict:
        """获取批次详情"""
        conn = self.db.get_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT * FROM medical_import_batches WHERE batch_id = ?
        ''', (batch_id,))
        
        batch = cursor.fetchone()
        if not batch:
            return None
        
        result = dict(batch)
        
        # 获取失败明细
        cursor.execute('''
            SELECT * FROM medical_import_failures WHERE batch_id = ?
        ''', (batch_id,))
        
        result["failures"] = [dict(row) for row in cursor.fetchall()]
        
        return result
    
    def get_available_batches_for_compare(self) -> Dict[str, List[Dict]]:
        """获取可用于比对的批次"""
        result = {
            "medical_catalog_western": [],
            "medical_catalog_chinese": [],
            "medical_price_limit": [],
            "cloud_pharmacy_catalog": [],
            "junyuan_sales_price": [],
        }
        
        conn = self.db.get_connection()
        cursor = conn.cursor()
        
        for batch_type in result.keys():
            if batch_type == "junyuan_sales_price":
                cursor.execute('''
                    SELECT batch_id, batch_type, file_name, imported_at, success_rows
                    FROM medical_import_batches
                    WHERE batch_type = ? AND import_status = 'success'
                    ORDER BY imported_at DESC
                    LIMIT 10
                ''', (batch_type,))
            else:
                cursor.execute('''
                    SELECT batch_id, batch_type, file_name, imported_at, success_rows
                    FROM medical_import_batches
                    WHERE batch_type = ? AND import_status = 'success'
                    ORDER BY imported_at DESC
                    LIMIT 10
                ''', (batch_type,))
            
            result[batch_type] = [dict(row) for row in cursor.fetchall()]
        
        return result
    
    def delete_batch(self, batch_id: str) -> bool:
        """删除导入批次及其关联数据
        
        Args:
            batch_id: 批次ID
            
        Returns:
            bool: 删除是否成功
        """
        try:
            conn = self.db.get_connection()
            cursor = conn.cursor()
            
            # 获取批次类型
            cursor.execute('''
                SELECT batch_type FROM medical_import_batches WHERE batch_id = ?
            ''', (batch_id,))
            
            row = cursor.fetchone()
            if not row:
                logging.warning(f"批次不存在: {batch_id}")
                return False
            
            batch_type = row['batch_type']
            
            # 根据批次类型删除关联数据
            table_map = {
                'medical_catalog_western': 'medical_catalog_western',
                'medical_catalog_chinese': 'medical_catalog_chinese',
                'medical_price_limit': 'medical_price_limit',
                'cloud_pharmacy_catalog': 'cloud_pharmacy_catalog',
                'junyuan_sales_price': 'junyuan_sales_price',
            }
            
            if batch_type in table_map:
                table_name = table_map[batch_type]
                cursor.execute(f'''
                    DELETE FROM {table_name} WHERE batch_id = ?
                ''', (batch_id,))
                logging.info(f"已删除 {table_name} 表中批次 {batch_id} 的数据")
            
            # 删除批次记录
            cursor.execute('''
                DELETE FROM medical_import_batches WHERE batch_id = ?
            ''', (batch_id,))
            
            conn.commit()
            logging.info(f"已删除批次: {batch_id}")
            
            return True
            
        except Exception as e:
            logging.error(f"删除批次失败: {e}")
            return False