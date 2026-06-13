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
            
            # 从数据库查询批次类型，分离西药和中成药批次
            western_batches = []
            chinese_batches = []
            
            for batch_id in medical_catalog_batches:
                cursor.execute('''
                    SELECT batch_type FROM medical_import_batches WHERE batch_id = ?
                ''', (batch_id,))
                row = cursor.fetchone()
                if row:
                    if row['batch_type'] == 'medical_catalog_western':
                        western_batches.append(batch_id)
                    elif row['batch_type'] == 'medical_catalog_chinese':
                        chinese_batches.append(batch_id)
            
            # 如果没有明确区分，使用全部批次（兼容旧逻辑）
            if not western_batches and not chinese_batches:
                western_batches = medical_catalog_batches
                chinese_batches = medical_catalog_batches
            
            # 构建批次IN条件（处理空批次情况）
            if western_batches:
                western_placeholders = ','.join(['?' for _ in western_batches])
                western_condition = f"mcw.batch_id IN ({western_placeholders})"
            else:
                western_condition = "mcw.batch_id IS NULL"
            
            if chinese_batches:
                chinese_placeholders = ','.join(['?' for _ in chinese_batches])
                chinese_condition = f"mcc.batch_id IN ({chinese_placeholders})"
            else:
                chinese_condition = "mcc.batch_id IS NULL"
            
            # 构建关联查询（以君元销售价格为主表）
            # 价格优先级：医保支付标准 > 省集中采购上限价含企业承诺价 > 政府定价元
            query = f'''
                SELECT 
                    cpc.商品编码,
                    cpc.旧商品编码,
                    cpc.商品名称,
                    cpc.规格,
                    cpc.生产厂家,
                    cpc.医保编码,
                    mpl.医保编码 as 三同医保编码,
                    mcw.国家药品代码 as 西药医保编码,
                    mcc.国家药品代码 as 中成药医保编码,
                    jy.商品编码 as 君元商品编码,
                    jy.商品名称 as 君元商品名称,
                    jy.规格 as 君元规格,
                    jy.生产厂家 as 君元生产厂家,
                    jy.库存数量 as 君元库存数量,
                    jy.销售价,
                    jy.包装价,
                    jy.单片价,
                    mpl.三同药品参比价 as 医保价格上限,
                    COALESCE(
                        NULLIF(mcw.医保支付标准, ''),
                        NULLIF(mcw.省集中采购上限价含企业承诺价, ''),
                        NULLIF(mcw.政府定价元, '')
                    ) as 医保基础价格,
                    COALESCE(
                        NULLIF(mcc.医保支付标准, ''),
                        NULLIF(mcc.省集中采购上限价含企业承诺价, ''),
                        NULLIF(mcc.政府定价元, '')
                    ) as 医保基础价格_中成药
                FROM junyuan_sales_price jy
                LEFT JOIN cloud_pharmacy_catalog cpc 
                    ON jy.商品编码 = cpc.旧商品编码 AND cpc.batch_id = ?
                LEFT JOIN medical_price_limit mpl 
                    ON cpc.医保编码 = mpl.医保编码 AND mpl.batch_id = ?
                LEFT JOIN medical_catalog_western mcw 
                    ON cpc.医保编码 = mcw.国家药品代码 AND {western_condition}
                LEFT JOIN medical_catalog_chinese mcc 
                    ON cpc.医保编码 = mcc.国家药品代码 AND {chinese_condition}
                WHERE jy.batch_id = ?
            '''
            
            # 构建参数列表
            params = [
                cloud_pharmacy_batch,
                medical_price_limit_batch,
            ]
            params.extend(western_batches)  # 西药目录批次
            params.extend(chinese_batches)  # 中成药目录批次
            params.append(junyuan_price_batch)
            
            cursor.execute(query, params)
            
            linked_data = cursor.fetchall()
            
            # 将Row对象转换为字典
            linked_data = [dict(row) for row in linked_data]
            
            # 3. 执行价格比对并保存结果（批量处理）
            batch_insert_data = []
            
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
                        "云药店目录来源": "yes" if row.get('商品编码') else "no",
                        "君元价格来源": "yes",
                    }
                    
                    # 收集批量插入数据
                    batch_insert_data.append((
                        batch_id,
                        row.get('医保编码', ''),
                        row.get('西药医保编码', ''),
                        row.get('中成药医保编码', ''),
                        row.get('三同医保编码', ''),
                        row.get('医保编码', ''),  # 国家药品代码（使用医保编码）
                        row.get('商品编码', ''),
                        row.get('旧商品编码', ''),
                        row.get('商品名称', ''),
                        row.get('规格', ''),
                        row.get('生产厂家', ''),
                        row.get('君元商品编码', ''),
                        row.get('君元商品名称', ''),
                        row.get('君元规格', ''),
                        row.get('君元生产厂家', ''),
                        row.get('君元库存数量', ''),
                        str(base_price) if base_price else "",
                        row.get('医保基础价格_中成药', ''),
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
                    print(f"[DEBUG] 处理比对行失败: {e}, row={row}")
                    logging.warning(f"处理比对行失败: {e}")
                    result.pending_count += 1
            
            # 批量插入比对结果
            print(f"[DEBUG] 批量插入数据: {len(batch_insert_data)} 条")
            if batch_insert_data:
                # 先删除已存在的比对结果（如果有）
                cursor.execute("DELETE FROM medical_price_compare_result WHERE compare_batch_id = ?", (batch_id,))
                
                # 批量插入新的比对结果
                cursor.executemany('''
                    INSERT INTO medical_price_compare_result (
                        compare_batch_id, 医保编码, 西药医保编码, 中成药医保编码, 三同医保编码, 国家药品代码, 商品编码, 旧商品编码,
                        商品名称, 规格, 生产厂家, 君元商品编码, 君元商品名称,
                        君元规格, 君元生产厂家, 君元库存数量, 医保基础价格, 医保基础价格_中成药,
                        医保价格上限, 君元销售价, 君元包装价, 君元单片价, 异常等级,
                        超基础金额, 超上限金额, 处理状态, 关联详情, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', batch_insert_data)
            
            # 4. 保存比对批次记录
            # 将批次列表转换为字符串（逗号分隔）
            medical_catalog_batch_str = ','.join(medical_catalog_batches) if medical_catalog_batches else ''
            
            # 使用INSERT OR REPLACE避免唯一约束冲突
            cursor.execute('''
                INSERT OR REPLACE INTO medical_compare_batches (
                    batch_id, 医保目录批次, 医保价格上限批次, 云药店目录批次, 君元价格批次,
                    正常数量, 异常数量, 严重异常数量, 待补价格数量, 待补编码数量, 待确认数量,
                    总数量, 比对状态, 比对人, 比对时间, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                batch_id,
                medical_catalog_batch_str,
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
        """判断异常等级（以君元销售价格为主表）"""
        medical_code = row.get('医保编码', '')
        product_code = row.get('商品编码', '')  # 云药店商品编码
        old_product_code = row.get('旧商品编码', '')
        sales_price = self._parse_decimal(row.get('销售价'))
        
        # 获取三个价格字段，如果为null则默认为0
        base_price_western = self._parse_decimal(row.get('医保基础价格')) or Decimal('0')
        base_price_chinese = self._parse_decimal(row.get('医保基础价格_中成药')) or Decimal('0')
        limit_price = self._parse_decimal(row.get('医保价格上限')) or Decimal('0')
        
        # 未关联到云药店商品目录（商品编码缺失）
        if not product_code:
            return "待确认"
        
        # 医保编码缺失
        if not medical_code:
            return "待补编码"
        
        # 如果三个金额都为0，则判定为正常
        if limit_price == Decimal('0') and base_price_western == Decimal('0') and base_price_chinese == Decimal('0'):
            return "正常"
        
        # 价格比对（所有null价格默认为0）
        if sales_price > limit_price:
            return "严重异常"
        elif sales_price > base_price_western:
            return "异常"
        elif sales_price > base_price_chinese:
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
    
    def get_medical_catalog_batches(self, batch_type: str = None) -> List[Dict]:
        """获取医保目录批次列表
        
        Args:
            batch_type: 批次类型，可选值：'medical_catalog_western' 或 'medical_catalog_chinese'
                       如果为None，返回所有批次
        
        Returns:
            批次列表，包含batch_id, batch_type, file_name, created_at等字段
        """
        conn = self.db.get_connection()
        cursor = conn.cursor()
        
        if batch_type:
            cursor.execute('''
                SELECT batch_id, batch_type, file_name, total_rows, success_rows, created_at
                FROM medical_import_batches
                WHERE batch_type = ?
                ORDER BY created_at DESC
                LIMIT 20
            ''', (batch_type,))
        else:
            cursor.execute('''
                SELECT batch_id, batch_type, file_name, total_rows, success_rows, created_at
                FROM medical_import_batches
                WHERE batch_type IN ('medical_catalog_western', 'medical_catalog_chinese')
                ORDER BY created_at DESC
                LIMIT 20
            ''')
        
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