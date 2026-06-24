"""
失败原因结构化服务 - 二期第一轮整改
将失败原因从纯文本升级为结构化字段（failure_stage / failure_code / failure_message / failure_detail / suggestion）。
"""

import json
import logging
import re
from datetime import datetime
from typing import Dict, List, Optional, Tuple

from app.storage.database import Database


# 失败阶段定义
FAILURE_STAGES = {
    "import_validation": "导入校验",
    "precheck": "采购前校验",
    "supplier_filter": "供应商筛选",
    "factory_filter": "厂家筛选",
    "search_match": "搜索匹配",
    "candidate_search": "候选搜索",
    "candidate_score": "候选评分",
    "price_check": "价格校验",
    "quantity_check": "起购/库存校验",
    "cart_before_check": "加购前购物车检查",
    "add_to_cart": "加购接口",
    "cart_verify": "购物车数量验证",
    "cart_after_verify": "加购后购物车验证",
    "cart_backfill": "购物车反写",
    "system_exception": "系统异常",
}

# 失败编码定义
FAILURE_CODES = {
    # 导入校验
    "MISSING_PRODUCT_NAME": {
        "stage": "import_validation",
        "message": "缺少商品名称",
        "suggestion": "请检查导入文件，确保每行都有商品名称字段。"
    },
    "INVALID_PURCHASE_QUANTITY": {
        "stage": "import_validation",
        "message": "采购数量无效",
        "suggestion": "请修改采购数量为大于0的数值。"
    },
    # 采购前校验
    "SUPPLIER_SCOPE_EMPTY": {
        "stage": "precheck",
        "message": "供应商范围为空",
        "suggestion": "请设置供应商范围或选择不限供应商。"
    },
    "SUPPLIER_NOT_ALLOWED": {
        "stage": "precheck",
        "message": "供应商不在允许范围内",
        "suggestion": "请检查供应商范围设置，或联系管理员添加该供应商。"
    },
    # 厂家筛选
    "FACTORY_FILTER_NOT_FOUND": {
        "stage": "factory_filter",
        "message": "厂家筛选未找到匹配项",
        "suggestion": "请检查厂家名称是否正确，或调整厂家筛选条件。"
    },
    "FACTORY_FILTER_NOT_EFFECTIVE": {
        "stage": "factory_filter",
        "message": "厂家筛选未生效",
        "suggestion": "请检查厂家筛选是否正确应用。"
    },
    # 搜索匹配
    "NO_SEARCH_RESULT": {
        "stage": "search_match",
        "message": "搜索无候选结果",
        "suggestion": "请检查商品名称是否正确，或尝试使用更通用的名称搜索。"
    },
    # 候选搜索（P1-3整改：精确分类未找到候选商品）
    "NO_CANDIDATE_FOUND": {
        "stage": "candidate_search",
        "message": "未找到候选商品",
        "suggestion": "请检查商品名称和搜索关键词，或尝试调整筛选条件。"
    },
    # 候选评分
    "SCORE_BELOW_THRESHOLD": {
        "stage": "candidate_score",
        "message": "候选评分低于阈值",
        "suggestion": "请检查评分规则阈值设置，或确认商品信息是否准确。"
    },
    "SPEC_CONFLICT": {
        "stage": "candidate_score",
        "message": "规格冲突",
        "suggestion": "请检查商品规格信息，确认包装数量是否一致。"
    },
    "MAKER_NOT_MATCHED": {
        "stage": "candidate_score",
        "message": "厂家不匹配",
        "suggestion": "请检查厂家名称是否正确，或考虑调整厂家匹配规则。"
    },
    # 价格校验
    "PRICE_OVER_LIMIT": {
        "stage": "price_check",
        "message": "价格超限",
        "suggestion": "请检查价格上限设置，或确认供应商报价是否合理。"
    },
    # 起购/库存校验
    "MIN_QTY_OVER_PURCHASE_QTY": {
        "stage": "quantity_check",
        "message": "起购数量大于采购数量",
        "suggestion": "请增加采购数量至起购数量以上，或选择起购数量更低的供应商。"
    },
    "STOCK_NOT_ENOUGH": {
        "stage": "quantity_check",
        "message": "库存不足",
        "suggestion": "请减少采购数量，或选择库存充足的供应商。"
    },
    # 购物车检查
    "CART_EXISTING_SAME_PRODUCT": {
        "stage": "cart_before_check",
        "message": "购物车已存在同品种",
        "suggestion": "如需更换供应商，请先从购物车移除同品种商品。"
    },
    # 加购接口
    "ADD_API_ERROR": {
        "stage": "add_to_cart",
        "message": "加购接口异常",
        "suggestion": "请检查网络连接，或稍后重试。"
    },
    # 加购后验证
    "CART_VERIFY_AMOUNT_NOT_ENOUGH": {
        "stage": "cart_after_verify",
        "message": "购物车验证数量不足",
        "suggestion": "请检查购物车状态，确认商品是否成功加入。"
    },
    # 购物车数量校验失败（P1-2整改：精确分类）
    "CART_QUANTITY_NOT_REACHED": {
        "stage": "cart_verify",
        "message": "购物车数量未达到要求",
        "suggestion": "请检查购物车状态，确认商品是否成功加入，或重试。"
    },
    # 购物车反写
    "CART_BACKFILL_NOT_MATCHED": {
        "stage": "cart_backfill",
        "message": "购物车反写未匹配",
        "suggestion": "请检查购物车商品信息，确认是否已加入购物车。"
    },
    # 系统异常
    "BROWSER_NOT_FOUND": {
        "stage": "system_exception",
        "message": "浏览器未找到",
        "suggestion": "请确保Chrome浏览器已启动并开启远程调试端口。"
    },
    "LOGIN_NOT_CONFIRMED": {
        "stage": "system_exception",
        "message": "登录未确认",
        "suggestion": "请确保药师帮网页已登录。"
    },
    "PAGE_CLOSED": {
        "stage": "system_exception",
        "message": "页面已关闭",
        "suggestion": "请确保药师帮网页未关闭。"
    },
    "EXECUTION_TIMEOUT": {
        "stage": "system_exception",
        "message": "执行超时",
        "suggestion": "请检查网络连接，或稍后重试。"
    },
    "SYSTEM_REFERENCE_ERROR": {
        "stage": "system_exception",
        "message": "系统引用错误",
        "suggestion": "请联系开发检查脚本变量作用域或配置传参后重试。"
    },
    "UNKNOWN_SYSTEM_EXCEPTION": {
        "stage": "system_exception",
        "message": "未知系统异常",
        "suggestion": "请联系开发排查问题。"
    },
}


class FailureReasonService:
    """失败原因结构化服务"""

    def __init__(self, db: Database):
        self.db = db

    def save_failure_reason(
        self,
        batch_id: str,
        item_id: str,
        row_number: int,
        failure_stage: str,
        failure_code: str,
        failure_message: str,
        failure_detail: str = "",
        suggestion: str = "",
        raw_reason: str = "",
        rule_set_code: str = "",
        rule_snapshot_id: str = ""
    ) -> None:
        """保存结构化失败原因"""
        try:
            conn = self.db.get_connection()
            cursor = conn.cursor()

            cursor.execute('''
                INSERT INTO smart_purchase_failure_reasons (
                    batch_id, item_id, row_number, rule_set_code, rule_snapshot_id,
                    failure_stage, failure_code, failure_message, failure_detail,
                    suggestion, raw_reason, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                batch_id,
                item_id,
                row_number,
                rule_set_code,
                rule_snapshot_id,
                failure_stage,
                failure_code,
                failure_message,
                failure_detail,
                suggestion,
                raw_reason,
                datetime.now().isoformat()
            ))

            conn.commit()
            logging.info(f"已保存失败原因: batch_id={batch_id}, item_id={item_id}, "
                         f"stage={failure_stage}, code={failure_code}")

        except Exception as e:
            logging.warning(f"保存失败原因失败: {e}")

    def classify_and_save_failure(
        self,
        batch_id: str,
        item_id: str,
        row_number: int,
        raw_reason: str,
        rule_set_code: str = "",
        rule_snapshot_id: str = ""
    ) -> Dict:
        """
        从原始失败原因文本中分类并保存结构化失败记录。
        返回分类结果字典。
        """
        result = self._classify_raw_reason(raw_reason)

        self.save_failure_reason(
            batch_id=batch_id,
            item_id=item_id,
            row_number=row_number,
            failure_stage=result["stage"],
            failure_code=result["code"],
            failure_message=result["message"],
            failure_detail=result["detail"],
            suggestion=result["suggestion"],
            raw_reason=raw_reason,
            rule_set_code=rule_set_code,
            rule_snapshot_id=rule_snapshot_id
        )

        return result

    def _classify_raw_reason(self, raw_reason: str) -> Dict:
        """
        从原始失败原因文本中分类失败编码。
        返回 {stage, code, message, detail, suggestion}
        """
        if not raw_reason:
            return {
                "stage": "system_exception",
                "code": "UNKNOWN_SYSTEM_EXCEPTION",
                "message": "未知失败原因",
                "detail": "",
                "suggestion": "请联系开发排查问题。"
            }

        reason_lower = raw_reason.lower()

        # 导入校验类
        if "缺少商品名称" in raw_reason or "缺少名称" in raw_reason:
            return self._make_result("MISSING_PRODUCT_NAME", raw_reason)

        if "采购数量无效" in raw_reason or "数量无效" in raw_reason:
            return self._make_result("INVALID_PURCHASE_QUANTITY", raw_reason)

        # 供应商校验类
        if "供应商不在" in raw_reason or "不在允许" in raw_reason or "供应商范围" in raw_reason:
            if "为空" in raw_reason or "未设置" in raw_reason:
                return self._make_result("SUPPLIER_SCOPE_EMPTY", raw_reason)
            return self._make_result("SUPPLIER_NOT_ALLOWED", raw_reason)

        # 厂家筛选类
        if "厂家筛选" in raw_reason:
            if "未找到" in raw_reason or "无匹配" in raw_reason:
                return self._make_result("FACTORY_FILTER_NOT_FOUND", raw_reason)
            if "未生效" in raw_reason:
                return self._make_result("FACTORY_FILTER_NOT_EFFECTIVE", raw_reason)

        # 搜索匹配类
        if "搜索无候选" in raw_reason or "无候选" in raw_reason or "搜索无结果" in raw_reason:
            return self._make_result("NO_SEARCH_RESULT", raw_reason)

        # 候选搜索类（P1-3整改：精确分类未找到候选商品）
        if "未找到" in raw_reason and "候选" in raw_reason:
            return self._make_result("NO_CANDIDATE_FOUND", raw_reason)
        if "未找到满足" in raw_reason or "无满足条件的候选" in raw_reason:
            return self._make_result("NO_CANDIDATE_FOUND", raw_reason)

        # 候选评分类
        if "分数" in raw_reason and ("低于" in raw_reason or "不够" in raw_reason or "不达标" in raw_reason):
            return self._make_result("SCORE_BELOW_THRESHOLD", raw_reason)

        if "规格冲突" in raw_reason or "规格不一致" in raw_reason or "包装总数冲突" in raw_reason:
            return self._make_result("SPEC_CONFLICT", raw_reason)

        if "厂家不匹配" in raw_reason or "厂家不一致" in raw_reason:
            return self._make_result("MAKER_NOT_MATCHED", raw_reason)

        # 价格校验类
        if "价格超限" in raw_reason or "价格过高" in raw_reason or "超过最高" in raw_reason or "价格超出" in raw_reason:
            return self._make_result("PRICE_OVER_LIMIT", raw_reason)

        # 起购/库存校验类
        if "起购" in raw_reason and ("大于" in raw_reason or "超过" in raw_reason):
            return self._make_result("MIN_QTY_OVER_PURCHASE_QTY", raw_reason)

        if "库存不足" in raw_reason:
            return self._make_result("STOCK_NOT_ENOUGH", raw_reason)

        # 购物车已存在同品种
        if "购物车已存在同品种" in raw_reason or "同品种" in raw_reason:
            return self._make_result("CART_EXISTING_SAME_PRODUCT", raw_reason)

        # 购物车数量校验失败（P1-2整改：精确分类）
        if "购物车数量未达到" in raw_reason or "加购后购物车数量" in raw_reason:
            return self._make_result("CART_QUANTITY_NOT_REACHED", raw_reason)

        # 加购接口类
        if "加购" in raw_reason and ("异常" in raw_reason or "失败" in raw_reason or "错误" in raw_reason):
            return self._make_result("ADD_API_ERROR", raw_reason)

        # 购物车验证类
        if "购物车" in raw_reason and ("数量不足" in raw_reason or "验证" in raw_reason):
            return self._make_result("CART_VERIFY_AMOUNT_NOT_ENOUGH", raw_reason)

        # 反写匹配类
        if "反写" in raw_reason and ("未匹配" in raw_reason or "失败" in raw_reason):
            return self._make_result("CART_BACKFILL_NOT_MATCHED", raw_reason)

        # 系统异常类
        if "浏览器" in raw_reason or "browser" in reason_lower:
            return self._make_result("BROWSER_NOT_FOUND", raw_reason)

        if "登录" in raw_reason or "login" in reason_lower:
            return self._make_result("LOGIN_NOT_CONFIRMED", raw_reason)

        if "页面已关闭" in raw_reason or "page" in reason_lower and "closed" in reason_lower:
            return self._make_result("PAGE_CLOSED", raw_reason)

        if "超时" in raw_reason or "timeout" in reason_lower:
            return self._make_result("EXECUTION_TIMEOUT", raw_reason)

        if "referenceerror" in reason_lower or "is not defined" in reason_lower or "factoryfilter" in reason_lower:
            return self._make_result("SYSTEM_REFERENCE_ERROR", raw_reason)

        # Node返回的结构化失败编码
        if "failureCode" in raw_reason or "failure_code" in raw_reason:
            # 尝试提取结构化编码
            code_match = re.search(r'failure_code["\s:=]+([A-Z_]+)', raw_reason)
            if code_match:
                code = code_match.group(1)
                if code in FAILURE_CODES:
                    return self._make_result(code, raw_reason)

        # 默认：未知系统异常
        return {
            "stage": "system_exception",
            "code": "UNKNOWN_SYSTEM_EXCEPTION",
            "message": f"未知异常: {raw_reason[:100]}",
            "detail": raw_reason,
            "suggestion": "请联系开发排查问题。"
        }

    def _make_result(self, code: str, raw_reason: str) -> Dict:
        """根据失败编码构造结果"""
        code_def = FAILURE_CODES.get(code, {})
        return {
            "stage": code_def.get("stage", "system_exception"),
            "code": code,
            "message": code_def.get("message", code),
            "detail": raw_reason,
            "suggestion": code_def.get("suggestion", "")
        }

    def get_failure_reasons_by_batch(self, batch_id: str) -> List[Dict]:
        """获取批次的失败原因列表"""
        conn = self.db.get_connection()
        cursor = conn.cursor()

        cursor.execute(
            "SELECT * FROM smart_purchase_failure_reasons WHERE batch_id = ? ORDER BY row_number",
            (batch_id,)
        )
        rows = cursor.fetchall()
        return [dict(row) for row in rows]

    def get_failure_stats_by_code(self, batch_id: str = "", rule_set_code: str = "",
                                   start_date: str = "", end_date: str = "") -> List[Dict]:
        """
        按失败编码聚合统计。
        返回 [{failure_code, failure_stage, count, example_message, example_suggestion}, ...]
        """
        conn = self.db.get_connection()
        cursor = conn.cursor()

        conditions = []
        params = []

        if batch_id:
            conditions.append("batch_id = ?")
            params.append(batch_id)

        if rule_set_code:
            conditions.append("rule_set_code = ?")
            params.append(rule_set_code)

        if start_date:
            conditions.append("created_at LIKE ? || '%'")
            params.append(start_date)

        if end_date:
            conditions.append("created_at LIKE ? || '%'")
            params.append(end_date)

        where_clause = " AND ".join(conditions) if conditions else "1=1"

        cursor.execute(f'''
            SELECT failure_code, failure_stage,
                   COUNT(*) as count,
                   failure_message,
                   suggestion
            FROM smart_purchase_failure_reasons
            WHERE {where_clause}
            GROUP BY failure_code, failure_stage
            ORDER BY count DESC
        ''', params)

        rows = cursor.fetchall()
        return [dict(row) for row in rows]

    def classify_node_failure(self, node_result: Dict) -> Dict:
        """
        从Node返回的结果中提取结构化失败信息。
        Node结果可能包含 failureStage / failureCode / failureDetail / suggestion 字段。
        """
        # 如果Node已经返回了结构化失败编码，直接使用
        failure_code = node_result.get("failureCode") or node_result.get("failure_code") or ""
        failure_stage = node_result.get("failureStage") or node_result.get("failure_stage") or ""
        failure_detail = node_result.get("failureDetail") or node_result.get("failure_detail") or ""
        suggestion = node_result.get("suggestion") or ""

        if failure_code and failure_code in FAILURE_CODES:
            code_def = FAILURE_CODES[failure_code]
            return {
                "stage": failure_stage or code_def.get("stage", ""),
                "code": failure_code,
                "message": code_def.get("message", failure_code),
                "detail": failure_detail,
                "suggestion": suggestion or code_def.get("suggestion", "")
            }

        # 如果没有结构化编码，从原始原因分类
        raw_reason = node_result.get("reason") or node_result.get("purchase_reason") or ""
        if raw_reason:
            return self._classify_raw_reason(raw_reason)

        return {
            "stage": "system_exception",
            "code": "UNKNOWN_SYSTEM_EXCEPTION",
            "message": "未知失败原因",
            "detail": "",
            "suggestion": "请联系开发排查问题。"
        }
