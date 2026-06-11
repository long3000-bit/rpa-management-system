"""
医保价格管控 - 表间关联与价格比对服务

阶段3：表间关联与数据校验
阶段4：价格比对与异常分级
"""

import logging
import json
import uuid
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Optional, Dict, List, Any, Tuple
from dataclasses import dataclass, field

from app.storage.database import Database


@dataclass
class CompareResult:
    """比对结果"""
    batch_id: str
    total_count: int = 0
    normal_count: int = 0
    abnormal_count: int = 0
    severe_count: int = 0
    missing_price_count: int = 0
    missing_code_count: int = 0
    pending_count: int = 0
    compare_status: str = "pending"
    error_message: str = ""


class MedicalPriceCompareService:
    """医保价格比对服务"""
    
    # 异常等级定义
    ABNORMAL_LEVELS = {
        "正常": "销售价 <= 医保基础价格",
        "异常": "销售价 > 医保基础价格 且 销售价 <= 医保价格上限",
        "严重异常": "销售价 > 医保价格上限",
        "待补价格": "医保价格上限缺失",
        "待补编码": "医保编码缺失",
        "待确认": "关联失败或数据异常",
    }
    
    def __init__(self, db: Database):
        self.db = db
    
    def generate_batch_id(self) -> str:
        """生成比对批次ID"""
        return f"COMPARE_{datetime.now().strftime('%Y%m%d%H%M%S')}_{uuid.uuid4().hex[:8]}"
    
    def run_compare(
        self,
        medical_catalog_batch: str = None,
        medical_price_limit_batch: str = None,
        cloud_pharmacy_batch: str = None,
        junyuan_price_batch: str = None,
        compare_by: str = "admin"
    ) -> CompareResult:
        """执行价格比对
        
        Args:
            medical_catalog_batch: 医保目录批次ID，可以是单个批次ID或批次ID列表（支持多选）
            medical_price_limit_batch: 医保价格上限批次ID
            cloud_pharmacy_batch: 云药店商品目录批次ID
            junyuan_price_batch: 君元销售价格批次ID
            compare_by: 比对执行人
        """
        batch_id = self.generate_batch_id()
        result = CompareResult(batch_id=batch_id)
        
        try:
            conn = self.db.get_connection()
            cursor = conn.cursor()
            now = datetime.now().isoformat()
            
            # 1. 获取各数据源的批次（如果没有指定，使用最新批次）
            # 处理医保目录批次（支持多选）
            medical_catalog_batches = []
            if medical_catalog_batch:
                if isinstance(medical_catalog_batch, list):
                    medical_catalog_batches = medical_catalog_batch
                else:
                    medical_catalog_batches = [medical_catalog_batch]
            
            if not medical_catalog_batches:
                # 自动选择所有最新的西药和中成药目录批次
                cursor.execute('''
                    SELECT batch_id FROM medical_import_batches
                    WHERE batch_type IN ('medical_catalog_western', 'medical_catalog_chinese')
                    AND import_status = 'success'
                    ORDER BY created_at DESC
                ''')
                rows = cursor.fetchall()
                medical_catalog_batches = [row['batch_id'] for row in rows]
            
            if not medical_price_limit_batch:
                cursor.execute('''
                    SELECT batch_id FROM medical_import_batches
                    WHERE batch_type = 'medical_price_limit' AND import_status = 'success'
                    ORDER BY created_at DESC LIMIT 1
                ''')
                row = cursor.fetchone()
                medical_price_limit_batch = row['batch_id'] if row else None
            
            if not cloud_pharmacy_batch:
                cursor.execute('''
                    SELECT batch_id FROM medical_import_batches
                    WHERE batch_type = 'cloud_pharmacy_catalog' AND import_status = 'success'
                    ORDER BY created_at DESC LIMIT 1
                ''')
                row = cursor.fetchone()
                cloud_pharmacy_batch = row['batch_id'] if row else None
            
            if not junyuan_price_batch:
                cursor.execute('''
                    SELECT batch_id FROM medical_import_batches
                    WHERE batch_type = 'junyuan_sales_price' AND import_status = 'success'
                    ORDER BY created_at DESC LIMIT 1
                ''')
                row = cursor.fetchone()
                junyuan_price_batch = row['batch_id'] if row else None
            
            # 2. 执行表间关联
            # 医保侧关联：国家药品代码 = 医保编码（支持多个批次）
            # 君元侧关联：旧商品编码 = 商品编码
            
            # 构建医保目录批次IN条件
            medical_batch_placeholders = ','.join(['?' for _ in medical_catalog_batches])
            
            # 构建关联查询（支持多个医保目录批次）
            query = f'''
                SELECT 
                    cpc.商品编码,
                    cpc.旧商品编码,
                    cpc.商品名称,
                    cpc.规格,
                    cpc.生产厂家,
                    cpc.医保编码,
                    jy.销售价,
                    jy.包装价,
                    jy.单片价,
                    mpl.医保价格上限,
                    mcw.医保基础价格,
                    mcc.医保基础价格 as 医保基础价格_中成药
                FROM cloud_pharmacy_catalog cpc
                LEFT JOIN junyuan_sales_price jy 
                    ON cpc.旧商品编码 = jy.商品编码 AND jy.batch_id = ?
                LEFT JOIN medical_price_limit mpl 
                    ON cpc.医保编码 = mpl.医保编码 AND mpl.batch_id = ?
                LEFT JOIN medical_catalog_western mcw 
                    ON cpc.医保编码 = mcw.国家药品代码 AND mcw.batch_id IN ({medical_batch_placeholders})
                LEFT JOIN medical_catalog_chinese mcc 
                    ON cpc.医保编码 = mcc.国家药品代码 AND mcc.batch_id IN ({medical_batch_placeholders})
                WHERE cpc.batch_id = ?
            '''
            
            # 构建参数列表
            params = [
                junyuan_price_batch,
                medical_price_limit_batch,
            ]
            params.extend(medical_catalog_batches)  # 西药目录批次
            params.extend(medical_catalog_batches)  # 中成药目录批次
            params.append(cloud_pharmacy_batch)
            
            cursor.execute(query, params)
            
            linked_data = cursor.fetchall()
            
            # 3. 执行价格比对并保存结果
            for row in linked_data:
                try:
                    # 判断异常等级
                    abnormal_level = self._determine_abnormal_level(row)
                    
                    # 计算超额金额
                    base_price = self._parse_decimal(row.get('医保基础价格') or row.get('医保基础价格_中成药'))
                    limit_price = self._parse_decimal(row.get('医保价格上限'))
                    sales_price = self._parse_decimal(row.get('销售价'))
                    
                    over_base_amount = ""
                    over_limit_amount = ""
                    
                    if base_price and sales_price and sales_price > base_price:
                        over_base_amount = str(sales_price - base_price)
                    
                    if limit_price and sales_price and sales_price > limit_price:
                        over_limit_amount = str(sales_price - limit_price)
                    
                    # 构建关联详情
                    link_detail = {
                        "医保编码": row.get('医保编码', ''),
                        "国家药品代码": row.get('医保编码', ''),
                        "旧商品编码": row.get('旧商品编码', ''),
                        "商品编码": row.get('商品编码', ''),
                        "医保目录来源": "western" if row.get('医保基础价格') else ("chinese" if row.get('医保基础价格_中成药') else ""),
                        "医保价格上限来源": "yes" if row.get('医保价格上限') else "no",
                        "云药店目录来源": "yes",
                        "君元价格来源": "yes" if row.get('销售价') else "no",
                    }
                    
                    # 插入比对结果
                    cursor.execute('''
                        INSERT INTO medical_price_compare_result (
                            compare_batch_id, 医保编码, 国家药品代码, 商品编码, 旧商品编码,
                            商品名称, 规格, 生产厂家, 医保基础价格, 医保价格上限,
                            君元销售价, 君元包装价, 君元单片价, 异常等级, 超基础金额,
                            超上限金额, 处理状态, 关联详情, created_at, updated_at
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ''', (
                        batch_id,
                        row.get('医保编码', ''),
                        row.get('医保编码', ''),
                        row.get('商品编码', ''),
                        row.get('旧商品编码', ''),
                        row.get('商品名称', ''),
                        row.get('规格', ''),
                        row.get('生产厂家', ''),
                        str(base_price) if base_price else "",
                        str(limit_price) if limit_price else "",
                        str(sales_price) if sales_price else "",
                        row.get('包装价', ''),
                        row.get('单片价', ''),
                        abnormal_level,
                        over_base_amount,
                        over_limit_amount,
                        "未处理",
                        json.dumps(link_detail, ensure_ascii=False),
                        now,
                        now
                    ))
                    
                    # 统计数量
                    result.total_count += 1
                    if abnormal_level == "正常":
                        result.normal_count += 1
                    elif abnormal_level == "异常":
                        result.abnormal_count += 1
                    elif abnormal_level == "严重异常":
                        result.severe_count += 1
                    elif abnormal_level == "待补价格":
                        result.missing_price_count += 1
                    elif abnormal_level == "待补编码":
                        result.missing_code_count += 1
                    else:
                        result.pending_count += 1
                        
                except Exception as e:
                    logging.warning(f"处理比对行失败: {e}")
                    result.pending_count += 1
            
            # 4. 保存比对批次记录
            cursor.execute('''
                INSERT INTO medical_compare_batches (
                    batch_id, 医保目录批次, 医保价格上限批次, 云药店目录批次, 君元价格批次,
                    正常数量, 异常数量, 严重异常数量, 待补价格数量, 待补编码数量, 待确认数量,
                    总数量, 比对状态, 比对人, 比对时间, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                batch_id,
                medical_catalog_batch,
                medical_price_limit_batch,
                cloud_pharmacy_batch,
                junyuan_price_batch,
                result.normal_count,
                result.abnormal_count,
                result.severe_count,
                result.missing_price_count,
                result.missing_code_count,
                result.pending_count,
                result.total_count,
                "completed",
                compare_by,
                now,
                now
            ))
            
            conn.commit()
            result.compare_status = "completed"
            
            logging.info(f"价格比对完成: 总数 {result.total_count}, 正常 {result.normal_count}, 异常 {result.abnormal_count}, 严重 {result.severe_count}")
            
        except Exception as e:
            result.compare_status = "failed"
            result.error_message = str(e)
            logging.error(f"价格比对失败: {e}")
        
        return result
    
    def _determine_abnormal_level(self, row: Dict) -> str:
        """判断异常等级"""
        medical_code = row.get('医保编码', '')
        old_product_code = row.get('旧商品编码', '')
        sales_price = self._parse_decimal(row.get('销售价'))
        base_price = self._parse_decimal(row.get('医保基础价格') or row.get('医保基础价格_中成药'))
        limit_price = self._parse_decimal(row.get('医保价格上限'))
        
        # 医保编码缺失
        if not medical_code:
            return "待补编码"
        
        # 君元价格缺失（关联失败）
        if not sales_price:
            return "待确认"
        
        # 医保价格上限缺失
        if not limit_price:
            return "待补价格"
        
        # 医保基础价格缺失
        if not base_price:
            return "待补价格"
        
        # 价格比对
        if sales_price > limit_price:
            return "严重异常"
        elif sales_price > base_price:
            return "异常"
        else:
            return "正常"
    
    def _parse_decimal(self, value: Any) -> Optional[Decimal]:
        """解析数值"""
        if value is None:
            return None
        try:
            str_value = str(value).strip()
            if not str_value:
                return None
            return Decimal(str_value)
        except (InvalidOperation, ValueError):
            return None
    
    def get_compare_batches(self, limit: int = 20) -> List[Dict]:
        """获取比对批次列表"""
        conn = self.db.get_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT * FROM medical_compare_batches
            ORDER BY created_at DESC
            LIMIT ?
        ''', (limit,))
        
        return [dict(row) for row in cursor.fetchall()]
    
    def get_compare_results(
        self,
        batch_id: str,
        abnormal_level: str = None,
        handle_status: str = None,
        search_keyword: str = None,
        limit: int = 100
    ) -> List[Dict]:
        """获取比对结果"""
        conn = self.db.get_connection()
        cursor = conn.cursor()
        
        query = "SELECT * FROM medical_price_compare_result WHERE compare_batch_id = ?"
        params = [batch_id]
        
        if abnormal_level:
            query += " AND 异常等级 = ?"
            params.append(abnormal_level)
        
        if handle_status:
            query += " AND 处理状态 = ?"
            params.append(handle_status)
        
        if search_keyword:
            query += " AND (商品名称 LIKE ? OR 商品编码 LIKE ? OR 旧商品编码 LIKE ? OR 医保编码 LIKE ?)"
            keyword = f"%{search_keyword}%"
            params.extend([keyword, keyword, keyword, keyword])
        
        query += " ORDER BY id DESC LIMIT ?"
        params.append(limit)
        
        cursor.execute(query, params)
        
        return [dict(row) for row in cursor.fetchall()]
    
    def update_handle_status(
        self,
        result_id: int,
        handle_status: str,
        handle_remark: str,
        handle_by: str
    ) -> bool:
        """更新处理状态"""
        conn = self.db.get_connection()
        cursor = conn.cursor()
        now = datetime.now().isoformat()
        
        try:
            cursor.execute('''
                UPDATE medical_price_compare_result
                SET 处理状态 = ?, 处理备注 = ?, 处理人 = ?, 处理时间 = ?, updated_at = ?
                WHERE id = ?
            ''', (handle_status, handle_remark, handle_by, now, now, result_id))
            
            conn.commit()
            return True
        except Exception as e:
            logging.error(f"更新处理状态失败: {e}")
            return False
    
    def get_abnormal_statistics(self, batch_id: str) -> Dict:
        """获取异常统计"""
        conn = self.db.get_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT 
                异常等级,
                COUNT(*) as count
            FROM medical_price_compare_result
            WHERE compare_batch_id = ?
            GROUP BY 异常等级
        ''', (batch_id,))
        
        stats = {}
        for row in cursor.fetchall():
            stats[row['异常等级']] = row['count']
        
        return stats
    
    def export_compare_results(
        self,
        batch_id: str,
        abnormal_level: str = None,
        handle_status: str = None
    ) -> List[Dict]:
        """导出比对结果"""
        return self.get_compare_results(
            batch_id=batch_id,
            abnormal_level=abnormal_level,
            handle_status=handle_status,
            limit=10000
        )