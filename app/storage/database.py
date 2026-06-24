import sqlite3
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional

from app.config import (
    DATABASE_PATH, 
    DEFAULT_ADMIN_USERNAME, 
    DEFAULT_ADMIN_PASSWORD,
    APP_VERSION
)
from app.core.password_service import PasswordService


class Database:
    
    def __init__(self, db_path: Path = DATABASE_PATH):
        self.db_path = db_path
        self.conn: Optional[sqlite3.Connection] = None
    
    def get_connection(self) -> sqlite3.Connection:
        logging.info(f"数据库连接 - 获取连接请求, 当前连接状态: {self.conn is not None}")
        
        if self.conn is not None:
            try:
                logging.info("数据库连接 - 检查现有连接")
                self.conn.execute("SELECT 1")
                logging.info(f"数据库连接 - 现有连接有效")
                return self.conn
            except Exception as e:
                logging.warning(f"数据库连接 - 现有连接失效: {e}")
                try:
                    self.conn.close()
                    logging.info("数据库连接 - 关闭失效连接")
                except Exception as close_error:
                    logging.warning(f"数据库连接 - 关闭连接时出错: {str(close_error)}")
                self.conn = None
        
        if self.conn is None:
            logging.info(f"数据库连接 - 创建新连接, 数据库路径: {self.db_path}")
            self.conn = sqlite3.connect(self.db_path, timeout=30.0)
            self.conn.row_factory = sqlite3.Row
            logging.info(f"数据库连接 - 新连接创建成功, 连接对象: {self.conn}")
        
        return self.conn
    
    def close(self):
        if self.conn:
            self.conn.close()
            self.conn = None
    
    def initialize(self):
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                salt TEXT NOT NULL,
                hash_iterations INTEGER NOT NULL,
                display_name TEXT,
                role TEXT DEFAULT 'admin',
                status TEXT DEFAULT 'active',
                last_login_at TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
        ''')
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS login_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL,
                success INTEGER NOT NULL,
                message TEXT,
                login_at TEXT NOT NULL,
                machine_name TEXT
            )
        ''')
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS app_settings (
                key TEXT PRIMARY KEY,
                value TEXT,
                updated_at TEXT NOT NULL
            )
        ''')
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS database_configs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                host TEXT NOT NULL,
                port INTEGER NOT NULL DEFAULT 3306,
                username TEXT NOT NULL,
                password TEXT NOT NULL,
                database_name TEXT NOT NULL,
                inbound_sql TEXT DEFAULT '',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
        ''')
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS reconciliation_tasks (
                task_id TEXT PRIMARY KEY,
                task_type TEXT DEFAULT 'all',
                ysb_file TEXT,
                account_period_start TEXT,
                account_period_end TEXT,
                inbound_query_start TEXT,
                inbound_query_end TEXT,
                db_config_id INTEGER,
                status TEXT DEFAULT 'pending',
                result_file TEXT,
                ysb_row_count INTEGER DEFAULT 0,
                inbound_row_count INTEGER DEFAULT 0,
                matched_count INTEGER DEFAULT 0,
                diff_count INTEGER DEFAULT 0,
                supplier_match_count INTEGER DEFAULT 0,
                supplier_diff_count INTEGER DEFAULT 0,
                detail_matched_count INTEGER DEFAULT 0,
                detail_suspected_count INTEGER DEFAULT 0,
                detail_unmatched_count INTEGER DEFAULT 0,
                product_match_count INTEGER DEFAULT 0,
                product_diff_count INTEGER DEFAULT 0,
                started_at TEXT,
                finished_at TEXT,
                error_message TEXT,
                created_at TEXT NOT NULL
            )
        ''')
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS supplier_reconciliation_results (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                task_id TEXT NOT NULL,
                status TEXT,
                diff_type TEXT,
                ysb_supplier TEXT,
                inbound_supplier TEXT,
                ysb_amount TEXT,
                inbound_amount TEXT,
                amount_diff TEXT,
                ysb_count INTEGER,
                inbound_count INTEGER,
                match_method TEXT,
                remark TEXT,
                created_at TEXT NOT NULL
            )
        ''')
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS product_reconciliation_results (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                task_id TEXT NOT NULL,
                status TEXT,
                diff_type TEXT,
                supplier TEXT,
                product_code TEXT,
                product_name TEXT,
                spec TEXT,
                manufacturer TEXT,
                ysb_amount TEXT,
                inbound_amount TEXT,
                amount_diff TEXT,
                ysb_quantity TEXT,
                inbound_quantity TEXT,
                quantity_diff TEXT,
                ysb_supplier TEXT,
                inbound_supplier TEXT,
                ysb_purchase_time TEXT,
                inbound_date TEXT,
                remark TEXT,
                created_at TEXT NOT NULL
            )
        ''')
        
        try:
            cursor.execute('ALTER TABLE product_reconciliation_results ADD COLUMN ysb_purchase_time TEXT')
        except:
            pass
        
        try:
            cursor.execute('ALTER TABLE product_reconciliation_results ADD COLUMN inbound_date TEXT')
        except:
            pass
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS ysb_import_batches (
                batch_id TEXT PRIMARY KEY,
                file_name TEXT NOT NULL,
                file_path TEXT,
                sheet_type TEXT,
                sheet_name TEXT,
                total_rows INTEGER DEFAULT 0,
                import_status TEXT DEFAULT 'success',
                account_year INTEGER,
                account_month INTEGER,
                imported_at TEXT NOT NULL,
                imported_by TEXT
            )
        ''')
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS ysb_detail_data (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                import_batch_id TEXT NOT NULL,
                file_name TEXT NOT NULL,
                sheet_name TEXT,
                ysb_order_no TEXT,
                order_type TEXT,
                purchase_time TEXT,
                ysb_store_name TEXT,
                ysb_supplier_name TEXT,
                ysb_company_name TEXT,
                product_name TEXT,
                manufacturer TEXT,
                spec TEXT,
                unit TEXT,
                approval_number TEXT,
                barcode TEXT,
                batch_no TEXT,
                production_date TEXT,
                expiry_date TEXT,
                unit_price TEXT,
                discount_price TEXT,
                quantity TEXT,
                order_quantity TEXT,
                refund_quantity TEXT,
                total_amount TEXT,
                discount_amount TEXT,
                actual_payment_amount TEXT,
                freight TEXT,
                discount_amount_total TEXT,
                raw_row_index INTEGER,
                raw_data TEXT,
                imported_at TEXT NOT NULL
            )
        ''')
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS ysb_supplier_summary (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                import_batch_id TEXT NOT NULL,
                file_name TEXT NOT NULL,
                sheet_name TEXT,
                ysb_supplier_name TEXT,
                ysb_company_name TEXT,
                actual_payment_amount TEXT,
                order_count INTEGER,
                raw_row_index INTEGER,
                raw_data TEXT,
                imported_at TEXT NOT NULL
            )
        ''')
        
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_ysb_detail_batch 
            ON ysb_detail_data(import_batch_id)
        ''')
        
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_ysb_supplier_batch 
            ON ysb_supplier_summary(import_batch_id)
        ''')
        
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_ysb_detail_barcode 
            ON ysb_detail_data(barcode)
        ''')
        
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_ysb_detail_company 
            ON ysb_detail_data(ysb_company_name)
        ''')
        
        cursor.execute('''
            CREATE UNIQUE INDEX IF NOT EXISTS idx_ysb_detail_unique
            ON ysb_detail_data(import_batch_id, ysb_order_no, product_name, spec, manufacturer)
        ''')
        
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_ysb_supplier_company
            ON ysb_supplier_summary(import_batch_id, ysb_company_name)
        ''')
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS rpa_templates (
                template_id TEXT PRIMARY KEY,
                template_name TEXT NOT NULL,
                template_type TEXT NOT NULL,
                description TEXT,
                import_field_mapping TEXT,
                field_mapping TEXT,
                workflow_steps TEXT,
                success_rule TEXT,
                duplicate_rule TEXT,
                exe_config_id TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                enabled INTEGER DEFAULT 1
            )
        ''')
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS rpa_exe_configs (
                config_id TEXT PRIMARY KEY,
                config_name TEXT NOT NULL,
                exe_path TEXT NOT NULL,
                process_name TEXT,
                main_window_title TEXT,
                login_window_title TEXT,
                username TEXT,
                password TEXT,
                login_success_rule TEXT,
                default_wait_time INTEGER DEFAULT 5,
                operation_timeout INTEGER DEFAULT 30,
                close_old_process INTEGER DEFAULT 1,
                auto_login INTEGER DEFAULT 1,
                enabled INTEGER DEFAULT 1,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
        ''')
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS rpa_import_batches (
                import_batch_id TEXT PRIMARY KEY,
                import_name TEXT NOT NULL,
                template_id TEXT,
                source_file TEXT NOT NULL,
                sheet_name TEXT,
                total_count INTEGER DEFAULT 0,
                valid_count INTEGER DEFAULT 0,
                invalid_count INTEGER DEFAULT 0,
                duplicate_count INTEGER DEFAULT 0,
                status TEXT DEFAULT 'pending',
                imported_by TEXT,
                imported_at TEXT NOT NULL,
                error_message TEXT
            )
        ''')
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS rpa_import_details (
                import_row_id TEXT PRIMARY KEY,
                import_batch_id TEXT NOT NULL,
                excel_row_number INTEGER NOT NULL,
                business_key TEXT,
                raw_data TEXT,
                normalized_data TEXT,
                data_status TEXT DEFAULT 'valid',
                business_status TEXT DEFAULT 'pending',
                target_system_no TEXT,
                target_system_message TEXT,
                processed_at TEXT,
                last_task_id TEXT,
                last_executed_by TEXT,
                last_executed_at TEXT,
                execute_count INTEGER DEFAULT 0,
                can_retry INTEGER DEFAULT 1,
                validation_message TEXT,
                rpa_status TEXT DEFAULT 'pending',
                rpa_error_message TEXT,
                rpa_system_no TEXT,
                rpa_screenshot_path TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
        ''')
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS rpa_tasks (
                task_id TEXT PRIMARY KEY,
                task_name TEXT NOT NULL,
                task_type TEXT NOT NULL,
                template_id TEXT,
                import_batch_id TEXT,
                source_file TEXT,
                result_file TEXT,
                exe_config_id TEXT,
                status TEXT DEFAULT 'pending',
                total_count INTEGER DEFAULT 0,
                success_count INTEGER DEFAULT 0,
                failed_count INTEGER DEFAULT 0,
                skipped_count INTEGER DEFAULT 0,
                duplicate_count INTEGER DEFAULT 0,
                started_at TEXT,
                finished_at TEXT,
                created_by TEXT,
                error_message TEXT,
                created_at TEXT NOT NULL
            )
        ''')
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS rpa_task_rows (
                row_id TEXT PRIMARY KEY,
                task_id TEXT NOT NULL,
                import_row_id TEXT NOT NULL,
                excel_row_number INTEGER NOT NULL,
                business_key TEXT,
                status TEXT DEFAULT 'pending',
                retry_count INTEGER DEFAULT 0,
                system_no TEXT,
                system_message TEXT,
                business_update_status TEXT,
                error_message TEXT,
                screenshot_path TEXT,
                started_at TEXT,
                finished_at TEXT,
                created_at TEXT NOT NULL
            )
        ''')
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS yys_import_batch (
                batch_id TEXT PRIMARY KEY,
                batch_name TEXT,
                source_file TEXT,
                sheet_name TEXT,
                total_count INTEGER,
                valid_count INTEGER,
                invalid_count INTEGER,
                status TEXT,
                imported_by TEXT,
                imported_at TEXT,
                created_at TEXT
            )
        ''')
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS yys_import_detail (
                detail_id TEXT PRIMARY KEY,
                batch_id TEXT,
                row_number INTEGER,
                productno TEXT,
                oldproductno TEXT,
                productname TEXT,
                lotno TEXT,
                yys_quantity DECIMAL,
                warehouse TEXT,
                specification TEXT,
                unit TEXT,
                manufacturer TEXT,
                supplier TEXT,
                valid_date TEXT,
                production_date TEXT,
                retail_price DECIMAL,
                batch_price DECIMAL,
                amount DECIMAL,
                tax_rate TEXT,
                gross_profit DECIMAL,
                gross_profit_rate TEXT,
                stock_status TEXT,
                barcode TEXT,
                approval_number TEXT,
                chinese_medicine_flag TEXT,
                inbound_time TEXT,
                raw_data TEXT,
                import_status TEXT,
                created_at TEXT
            )
        ''')
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS jy_stock_query (
                query_id TEXT PRIMARY KEY,
                batch_id TEXT,
                oldproductno TEXT,
                productname TEXT,
                lotno TEXT,
                jy_quantity DECIMAL,
                warehouse TEXT,
                valid_date TEXT,
                specification TEXT,
                approval_number TEXT,
                query_time TEXT,
                created_at TEXT
            )
        ''')
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS stock_compare_result (
                result_id TEXT PRIMARY KEY,
                batch_id TEXT,
                oldproductno TEXT,
                productname TEXT,
                lotno TEXT,
                yys_quantity DECIMAL,
                jy_quantity DECIMAL,
                diff_quantity DECIMAL,
                compare_status TEXT,
                sync_status TEXT,
                sync_time TEXT,
                sync_message TEXT,
                api_response TEXT,
                created_at TEXT,
                updated_at TEXT
            )
        ''')
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS yys_api_config (
                config_id TEXT PRIMARY KEY,
                config_name TEXT,
                host TEXT,
                appkey TEXT,
                appsecret TEXT,
                orgcode TEXT,
                timeout INTEGER,
                enabled INTEGER,
                created_at TEXT,
                updated_at TEXT
            )
        ''')
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS yys_sync_task (
                task_id TEXT PRIMARY KEY,
                batch_id TEXT,
                api_config_id TEXT,
                total_count INTEGER,
                success_count INTEGER,
                failed_count INTEGER,
                skipped_count INTEGER,
                status TEXT,
                started_at TEXT,
                finished_at TEXT,
                created_at TEXT
            )
        ''')
        
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_rpa_import_batch
            ON rpa_import_details(import_batch_id)
        ''')
        
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_rpa_task_batch
            ON rpa_task_rows(task_id)
        ''')
        
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_rpa_import_row
            ON rpa_task_rows(import_row_id)
        ''')
        
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_yys_import_batch
            ON yys_import_detail(batch_id)
        ''')
        
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_jy_stock_batch
            ON jy_stock_query(batch_id)
        ''')
        
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_compare_batch
            ON stock_compare_result(batch_id)
        ''')
        
        # Permission management tables
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS roles (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                role_code TEXT UNIQUE NOT NULL,
                role_name TEXT NOT NULL,
                description TEXT,
                is_system_role INTEGER DEFAULT 0,
                status TEXT DEFAULT 'active',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
        ''')
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS permissions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                permission_code TEXT UNIQUE NOT NULL,
                permission_name TEXT NOT NULL,
                permission_type TEXT NOT NULL,
                parent_code TEXT,
                description TEXT,
                sort_order INTEGER DEFAULT 0,
                created_at TEXT NOT NULL
            )
        ''')
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS role_permissions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                role_code TEXT NOT NULL,
                permission_code TEXT NOT NULL,
                created_at TEXT NOT NULL,
                UNIQUE(role_code, permission_code)
            )
        ''')
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS user_roles (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL,
                role_code TEXT NOT NULL,
                created_at TEXT NOT NULL,
                UNIQUE(username, role_code)
            )
        ''')
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS operation_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL,
                operation_type TEXT NOT NULL,
                operation_desc TEXT,
                target_type TEXT,
                target_id TEXT,
                detail TEXT,
                ip_address TEXT,
                machine_name TEXT,
                created_at TEXT NOT NULL
            )
        ''')
        
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_operation_logs_username
            ON operation_logs(username)
        ''')
        
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_operation_logs_type
            ON operation_logs(operation_type)
        ''')
        
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_operation_logs_time
            ON operation_logs(created_at)
        ''')
        
        # ========== 医保价格管控相关表 ==========
        
        # 导入批次记录表
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS medical_import_batches (
                batch_id TEXT PRIMARY KEY,
                batch_type TEXT NOT NULL,
                file_name TEXT NOT NULL,
                file_path TEXT,
                sheet_name TEXT,
                total_rows INTEGER DEFAULT 0,
                success_rows INTEGER DEFAULT 0,
                failed_rows INTEGER DEFAULT 0,
                import_status TEXT DEFAULT 'pending',
                imported_by TEXT,
                imported_at TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
        ''')
        
        # 导入失败明细表
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS medical_import_failures (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                batch_id TEXT NOT NULL,
                row_index INTEGER,
                raw_data TEXT,
                failure_reason TEXT,
                created_at TEXT NOT NULL
            )
        ''')
        
        # 医保目录-西药原始导入表
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS medical_catalog_western (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                batch_id TEXT NOT NULL,
                sheet_type TEXT NOT NULL,
                row_index INTEGER,
                序号 TEXT,
                分类编码 TEXT,
                药品通用名编码 TEXT,
                医保药品名称 TEXT,
                医保支付类别 TEXT,
                医保剂型 TEXT,
                产品名编码 TEXT,
                注册名称 TEXT,
                商品名称 TEXT,
                实际剂型 TEXT,
                实际规格 TEXT,
                包装材质 TEXT,
                最小包装数量 TEXT,
                最小计价单位 TEXT,
                单位 TEXT,
                政府定价元 TEXT,
                省集中采购上限价含企业承诺价 TEXT,
                医保支付标准 TEXT,
                批准文号 TEXT,
                药品企业 TEXT,
                医保限定支付范围 TEXT,
                编号 TEXT,
                招标申报编号 TEXT,
                备注 TEXT,
                国家药品代码 TEXT,
                变更类型 TEXT,
                变更原因 TEXT,
                原始数据 TEXT,
                created_at TEXT NOT NULL
            )
        ''')
        
        # 医保目录-中成药原始导入表
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS medical_catalog_chinese (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                batch_id TEXT NOT NULL,
                sheet_type TEXT NOT NULL,
                row_index INTEGER,
                序号 TEXT,
                分类编码 TEXT,
                药品通用名编码 TEXT,
                医保药品名称 TEXT,
                医保支付类别 TEXT,
                产品名编码 TEXT,
                注册名称 TEXT,
                商品名称 TEXT,
                实际剂型 TEXT,
                实际规格 TEXT,
                包装材质 TEXT,
                最小包装数量 TEXT,
                最小计价单位 TEXT,
                单位 TEXT,
                国家药品代码 TEXT,
                政府定价元 TEXT,
                省集中采购上限价含企业承诺价 TEXT,
                医保支付标准 TEXT,
                批准文号 TEXT,
                药品企业 TEXT,
                医保限定支付范围 TEXT,
                编号 TEXT,
                招标申报编号 TEXT,
                备注 TEXT,
                国家药品代码2 TEXT,
                变更类型 TEXT,
                变更原因 TEXT,
                原始数据 TEXT,
                created_at TEXT NOT NULL
            )
        ''')
        
        # 医保价格上限原始导入表
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS medical_price_limit (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                batch_id TEXT NOT NULL,
                row_index INTEGER,
                分组名称 TEXT,
                三同药品挂网最低单片价 TEXT,
                医保编码 TEXT,
                药品名称 TEXT,
                通用名 TEXT,
                剂型 TEXT,
                规格 TEXT,
                生产企业 TEXT,
                转换比 TEXT,
                三同药品参比价 TEXT,
                数据时间 TEXT,
                原始数据 TEXT,
                created_at TEXT NOT NULL
            )
        ''')
        
        # 云药店商品目录原始导入表
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS cloud_pharmacy_catalog (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                batch_id TEXT NOT NULL,
                row_index INTEGER,
                商品编码 TEXT,
                旧商品编码 TEXT,
                商品名称 TEXT,
                通用名 TEXT,
                规格 TEXT,
                剂型 TEXT,
                包装规格 TEXT,
                单位 TEXT,
                生产厂家 TEXT,
                批准文号 TEXT,
                医保编码 TEXT,
                医保类型 TEXT,
                商品状态 TEXT,
                创建时间 TEXT,
                更新时间 TEXT,
                原始数据 TEXT,
                created_at TEXT NOT NULL
            )
        ''')
        
        # 君元销售价格抓取表
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS junyuan_sales_price (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                batch_id TEXT NOT NULL,
                商品编码 TEXT,
                商品名称 TEXT,
                规格 TEXT,
                剂型 TEXT,
                包装规格 TEXT,
                生产厂家 TEXT,
                销售价 TEXT,
                包装价 TEXT,
                单片价 TEXT,
                拆零价 TEXT,
                库存数量 TEXT,
                三月销量 TEXT,
                价格类型 TEXT,
                价格更新时间 TEXT,
                抓取状态 TEXT DEFAULT 'success',
                原始数据 TEXT,
                created_at TEXT NOT NULL
            )
        ''')
        
        # 自定义SQL配置表
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS custom_sql_configs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                config_key TEXT NOT NULL UNIQUE,
                config_name TEXT NOT NULL,
                sql_content TEXT NOT NULL,
                description TEXT,
                created_by TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
        ''')
        
        # 创建索引
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_custom_sql_config_key 
            ON custom_sql_configs(config_key)
        ''')
        
        # 表间关联结果表
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS medical_price_link_result (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                compare_batch_id TEXT NOT NULL,
                医保编码 TEXT,
                国家药品代码 TEXT,
                旧商品编码 TEXT,
                商品编码 TEXT,
                医保目录来源 TEXT,
                医保价格上限来源 TEXT,
                云药店目录来源 TEXT,
                君元价格来源 TEXT,
                匹配状态 TEXT,
                医保编码缺失 INTEGER DEFAULT 0,
                旧商品编码缺失 INTEGER DEFAULT 0,
                医保编码重复 INTEGER DEFAULT 0,
                旧商品编码重复 INTEGER DEFAULT 0,
                关联失败原因 TEXT,
                created_at TEXT NOT NULL
            )
        ''')
        
        # 价格比对结果表
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS medical_price_compare_result (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                compare_batch_id TEXT NOT NULL,
                医保编码 TEXT,
                西药医保编码 TEXT,
                中成药医保编码 TEXT,
                三同医保编码 TEXT,
                国家药品代码 TEXT,
                商品编码 TEXT,
                旧商品编码 TEXT,
                商品名称 TEXT,
                规格 TEXT,
                生产厂家 TEXT,
                君元商品编码 TEXT,
                君元商品名称 TEXT,
                君元规格 TEXT,
                君元生产厂家 TEXT,
                君元库存数量 TEXT,
                三同药品参比价 TEXT,
                医保基础价格 TEXT,
                医保基础价格_中成药 TEXT,
                医保价格上限 TEXT,
                君元销售价 TEXT,
                君元包装价 TEXT,
                君元单片价 TEXT,
                异常等级 TEXT,
                超基础金额 TEXT,
                超基础金额_中成药 TEXT,
                超上限金额 TEXT,
                处理状态 TEXT DEFAULT '未处理',
                处理备注 TEXT,
                处理人 TEXT,
                处理时间 TEXT,
                关联详情 TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
        ''')
        
        # 比对批次记录表
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS medical_compare_batches (
                batch_id TEXT PRIMARY KEY,
                医保目录批次 TEXT,
                医保价格上限批次 TEXT,
                云药店目录批次 TEXT,
                君元价格批次 TEXT,
                正常数量 INTEGER DEFAULT 0,
                异常数量 INTEGER DEFAULT 0,
                严重异常数量 INTEGER DEFAULT 0,
                待补价格数量 INTEGER DEFAULT 0,
                待补编码数量 INTEGER DEFAULT 0,
                待确认数量 INTEGER DEFAULT 0,
                总数量 INTEGER DEFAULT 0,
                比对状态 TEXT DEFAULT 'pending',
                比对人 TEXT,
                比对时间 TEXT,
                created_at TEXT NOT NULL
            )
        ''')
        
        # 采购候选评分表（一期落库）
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS purchase_candidate_scores (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                purchase_batch_id TEXT NOT NULL,
                purchase_detail_id TEXT NOT NULL,
                purchase_status TEXT,
                rule_set_code TEXT,
                search_keyword TEXT,
                candidate_rank INTEGER,
                candidate_name TEXT,
                candidate_spec TEXT,
                candidate_maker TEXT,
                candidate_supplier TEXT,
                candidate_supplier_full TEXT,
                candidate_price TEXT,
                compare_price TEXT,
                max_allowed_price TEXT,
                min_purchase_quantity TEXT,
                candidate_stock TEXT,
                name_score INTEGER,
                spec_score INTEGER,
                maker_score INTEGER,
                total_score INTEGER,
                identity_pass INTEGER,
                spec_conflict INTEGER,
                spec_pass INTEGER,
                maker_pass INTEGER,
                supplier_pass INTEGER,
                price_pass INTEGER,
                qty_pass INTEGER,
                stock_pass INTEGER,
                final_pass INTEGER,
                selected INTEGER,
                reject_reason TEXT,
                raw_data TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
        ''')
        
        # 创建索引
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_medical_import_batch_type
            ON medical_import_batches(batch_type)
        ''')
        
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_medical_catalog_western_batch
            ON medical_catalog_western(batch_id)
        ''')
        
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_medical_catalog_chinese_batch
            ON medical_catalog_chinese(batch_id)
        ''')
        
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_medical_price_limit_batch
            ON medical_price_limit(batch_id)
        ''')
        
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_cloud_pharmacy_catalog_batch
            ON cloud_pharmacy_catalog(batch_id)
        ''')
        
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_junyuan_sales_price_batch
            ON junyuan_sales_price(batch_id)
        ''')
        
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_medical_price_compare_batch
            ON medical_price_compare_result(compare_batch_id)
        ''')
        
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_medical_price_compare_status
            ON medical_price_compare_result(异常等级)
        ''')
        
        # 采购候选评分表索引
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_purchase_candidate_batch
            ON purchase_candidate_scores(purchase_batch_id)
        ''')
        
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_purchase_candidate_detail
            ON purchase_candidate_scores(purchase_detail_id)
        ''')
        
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_purchase_candidate_total_score
            ON purchase_candidate_scores(total_score)
        ''')
        
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_purchase_candidate_final_pass
            ON purchase_candidate_scores(final_pass)
        ''')
        
        # ========== 智能采购相关表（smart_*系列表）==========
        
        # 规则集表
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS smart_match_rule_sets (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                rule_set_code TEXT UNIQUE NOT NULL,
                rule_set_name TEXT NOT NULL,
                description TEXT,
                is_default INTEGER DEFAULT 0,
                is_enabled INTEGER DEFAULT 1,
                created_by TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                -- 二期新增字段：规则版本管理
                version_number TEXT DEFAULT 'v1.0.0',
                version_status TEXT DEFAULT 'active',
                release_date TEXT,
                deprecation_date TEXT,
                change_reason TEXT,
                change_type TEXT DEFAULT 'new',
                audit_status TEXT DEFAULT 'approved',
                audit_by TEXT,
                audit_at TEXT,
                audit_comment TEXT,
                gray_release_scope TEXT,
                gray_release_ratio INTEGER DEFAULT 0,
                gray_release_status TEXT DEFAULT 'none',
                updated_by TEXT
            )
        ''')
        
        # 规则配置表
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS smart_match_rule_configs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                rule_set_code TEXT NOT NULL,
                rule_key TEXT NOT NULL,
                rule_name TEXT NOT NULL,
                rule_value TEXT NOT NULL,
                rule_type TEXT NOT NULL,
                description TEXT,
                sort_order INTEGER DEFAULT 0,
                is_enabled INTEGER DEFAULT 1,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                UNIQUE(rule_set_code, rule_key)
            )
        ''')

        # 三期新增：规则版本历史表
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS smart_match_rule_set_versions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                rule_set_code TEXT NOT NULL,
                version_number TEXT NOT NULL,
                version_name TEXT,
                configs_json TEXT NOT NULL,
                change_reason TEXT,
                change_type TEXT DEFAULT 'update',
                created_by TEXT,
                created_at TEXT NOT NULL,
                is_active INTEGER DEFAULT 0,
                UNIQUE(rule_set_code, version_number)
            )
        ''')

        # 候选过程表
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS smart_purchase_candidates (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                purchase_batch_id TEXT NOT NULL,
                purchase_detail_id TEXT NOT NULL,
                rule_set_code TEXT NOT NULL,
                search_keyword TEXT NOT NULL,
                candidate_rank INTEGER NOT NULL,
                candidate_name TEXT,
                candidate_spec TEXT,
                candidate_maker TEXT,
                candidate_supplier TEXT,
                candidate_supplier_full TEXT,
                candidate_price TEXT,
                compare_price TEXT,
                max_allowed_price TEXT,
                min_purchase_quantity TEXT,
                candidate_stock TEXT,
                name_score INTEGER,
                spec_score INTEGER,
                maker_score INTEGER,
                total_score INTEGER,
                identity_pass INTEGER,
                spec_conflict INTEGER,
                spec_pass INTEGER,
                maker_pass INTEGER,
                supplier_pass INTEGER,
                price_pass INTEGER,
                qty_pass INTEGER,
                stock_pass INTEGER,
                final_pass INTEGER,
                selected INTEGER,
                reject_reason TEXT,
                raw_data TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
        ''')
        
        # 购物车快照表
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS smart_cart_snapshots (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                snapshot_batch_id TEXT UNIQUE NOT NULL,
                snapshot_type TEXT NOT NULL,
                total_items INTEGER DEFAULT 0,
                matched_items INTEGER DEFAULT 0,
                unmatched_items INTEGER DEFAULT 0,
                snapshot_status TEXT DEFAULT 'pending',
                snapshot_time TEXT NOT NULL,
                created_by TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
        ''')
        
        # 购物车快照明细表
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS smart_cart_snapshot_items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                snapshot_batch_id TEXT NOT NULL,
                item_index INTEGER NOT NULL,
                item_name TEXT,
                item_spec TEXT,
                item_maker TEXT,
                item_supplier TEXT,
                item_price TEXT,
                item_quantity TEXT,
                item_stock TEXT,
                match_status TEXT DEFAULT 'pending',
                match_detail TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
        ''')
        
        # 购物车反写匹配表
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS smart_cart_backfill_matches (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                snapshot_batch_id TEXT NOT NULL,
                snapshot_item_id TEXT NOT NULL,
                purchase_batch_id TEXT NOT NULL,
                purchase_detail_id TEXT NOT NULL,
                match_type TEXT NOT NULL,
                match_score INTEGER,
                match_status TEXT DEFAULT 'pending',
                match_detail TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
        ''')
        
        # ========== 智能采购规则辅助表（smart_*系列表）==========
        
        # 规格单位别名表
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS smart_spec_unit_aliases (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                unit_alias TEXT UNIQUE NOT NULL,
                unit_standard TEXT NOT NULL,
                description TEXT,
                is_enabled INTEGER DEFAULT 1,
                created_by TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
        ''')
        
        # 规格解析规则表
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS smart_spec_parse_rules (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                rule_code TEXT UNIQUE NOT NULL,
                rule_name TEXT NOT NULL,
                parse_pattern TEXT NOT NULL,
                extract_fields TEXT NOT NULL,
                description TEXT,
                sort_order INTEGER DEFAULT 0,
                is_enabled INTEGER DEFAULT 1,
                created_by TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
        ''')
        
        # 匹配阈值表
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS smart_match_thresholds (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                threshold_code TEXT UNIQUE NOT NULL,
                threshold_name TEXT NOT NULL,
                threshold_value TEXT NOT NULL,
                threshold_type TEXT NOT NULL,
                description TEXT,
                is_enabled INTEGER DEFAULT 1,
                created_by TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
        ''')
        
        # ========== 二期新增：规则变更审核记录表 ==========
        
        # 规则变更审核记录表
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS smart_rule_audit_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                audit_id TEXT UNIQUE NOT NULL,
                rule_set_code TEXT NOT NULL,
                change_type TEXT NOT NULL,
                change_reason TEXT,
                old_version TEXT,
                new_version TEXT,
                old_config TEXT,
                new_config TEXT,
                audit_status TEXT NOT NULL DEFAULT 'pending',
                audit_by TEXT,
                audit_at TEXT,
                audit_comment TEXT,
                created_by TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
        ''')
        
        # 规则灰度发布记录表
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS smart_rule_gray_release_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                release_id TEXT UNIQUE NOT NULL,
                rule_set_code TEXT NOT NULL,
                gray_type TEXT NOT NULL,
                gray_scope TEXT,
                gray_ratio INTEGER DEFAULT 0,
                gray_status TEXT NOT NULL DEFAULT 'testing',
                start_time TEXT NOT NULL,
                end_time TEXT,
                monitoring_metrics TEXT,
                rollback_threshold TEXT,
                rollback_reason TEXT,
                created_by TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
        ''')
        
        # 规则效果统计表
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS smart_rule_effect_stats (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                stat_id TEXT UNIQUE NOT NULL,
                rule_set_code TEXT NOT NULL,
                stat_date TEXT NOT NULL,
                total_batches INTEGER DEFAULT 0,
                total_items INTEGER DEFAULT 0,
                matched_items INTEGER DEFAULT 0,
                purchased_items INTEGER DEFAULT 0,
                failed_items INTEGER DEFAULT 0,
                match_success_rate REAL DEFAULT 0,
                purchase_success_rate REAL DEFAULT 0,
                avg_match_score REAL DEFAULT 0,
                avg_purchase_price REAL DEFAULT 0,
                failure_reason_distribution TEXT,
                score_distribution TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
        ''')
        
        # 规则生效范围配置表（二期阶段三）
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS smart_rule_scope_configs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                scope_id TEXT UNIQUE NOT NULL,
                rule_set_code TEXT NOT NULL,
                scope_type TEXT NOT NULL,
                scope_value TEXT NOT NULL,
                scope_priority INTEGER DEFAULT 0,
                scope_status TEXT NOT NULL DEFAULT 'active',
                created_by TEXT,
                updated_by TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
        ''')
        
        # 规则参数调整记录表（二期阶段六）
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS smart_rule_param_adjustments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                adjustment_id TEXT UNIQUE NOT NULL,
                rule_set_code TEXT NOT NULL,
                adjustment_type TEXT NOT NULL,
                old_params TEXT,
                new_params TEXT NOT NULL,
                adjustment_reason TEXT,
                test_status TEXT DEFAULT 'pending',
                test_result TEXT,
                verify_status TEXT DEFAULT 'pending',
                verify_result TEXT,
                created_by TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
        ''')
        
        # 名称别名表
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS smart_name_aliases (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name_alias TEXT UNIQUE NOT NULL,
                name_standard TEXT NOT NULL,
                description TEXT,
                is_enabled INTEGER DEFAULT 1,
                created_by TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
        ''')

        # ========== 二期第一轮整改：规则运行快照表 ==========
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS smart_match_rule_snapshots (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                snapshot_id TEXT NOT NULL UNIQUE,
                batch_id TEXT NOT NULL,
                rule_set_code TEXT NOT NULL,
                rule_set_version TEXT,
                snapshot_json TEXT NOT NULL,
                fallback_used INTEGER DEFAULT 0,
                fallback_reason TEXT,
                source TEXT DEFAULT 'smart_purchase',
                created_at TEXT NOT NULL
            )
        ''')

        # ========== 二期第一轮整改：失败原因结构化表 ==========
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS smart_purchase_failure_reasons (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                batch_id TEXT NOT NULL,
                item_id TEXT NOT NULL,
                row_number INTEGER,
                rule_set_code TEXT,
                rule_snapshot_id TEXT,
                failure_stage TEXT,
                failure_code TEXT,
                failure_message TEXT,
                failure_detail TEXT,
                suggestion TEXT,
                raw_reason TEXT,
                created_at TEXT NOT NULL
            )
        ''')

        # ========== 二期第一轮整改：规则变更日志表 ==========
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS smart_match_rule_change_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                rule_set_code TEXT NOT NULL,
                change_type TEXT NOT NULL,
                field_path TEXT,
                old_value TEXT,
                new_value TEXT,
                change_reason TEXT,
                changed_by TEXT,
                changed_at TEXT NOT NULL
            )
        ''')

        # ========== 二期第一轮整改：规则发布日志表 ==========
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS smart_match_rule_publish_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                rule_set_code TEXT NOT NULL,
                version_no TEXT,
                publish_status TEXT NOT NULL,
                publish_summary TEXT,
                test_result_json TEXT,
                published_by TEXT,
                published_at TEXT NOT NULL
            )
        ''')
        
        # 创建索引
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_smart_rule_sets_code
            ON smart_match_rule_sets(rule_set_code)
        ''')
        
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_smart_rule_configs_set
            ON smart_match_rule_configs(rule_set_code)
        ''')
        
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_smart_purchase_candidates_batch
            ON smart_purchase_candidates(purchase_batch_id)
        ''')
        
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_smart_purchase_candidates_detail
            ON smart_purchase_candidates(purchase_detail_id)
        ''')
        
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_smart_cart_snapshots_batch
            ON smart_cart_snapshots(snapshot_batch_id)
        ''')
        
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_smart_cart_snapshot_items_batch
            ON smart_cart_snapshot_items(snapshot_batch_id)
        ''')
        
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_smart_cart_backfill_matches_batch
            ON smart_cart_backfill_matches(snapshot_batch_id)
        ''')
        
        # ========== 二期新增表索引 ==========
        
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_smart_rule_audit_logs_rule
            ON smart_rule_audit_logs(rule_set_code)
        ''')
        
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_smart_rule_audit_logs_status
            ON smart_rule_audit_logs(audit_status)
        ''')
        
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_smart_rule_gray_release_logs_rule
            ON smart_rule_gray_release_logs(rule_set_code)
        ''')
        
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_smart_rule_gray_release_logs_status
            ON smart_rule_gray_release_logs(gray_status)
        ''')
        
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_smart_rule_effect_stats_rule
            ON smart_rule_effect_stats(rule_set_code)
        ''')
        
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_smart_rule_effect_stats_date
            ON smart_rule_effect_stats(stat_date)
        ''')
        
        # 规则生效范围配置表索引
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_smart_rule_scope_configs_rule
            ON smart_rule_scope_configs(rule_set_code)
        ''')
        
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_smart_rule_scope_configs_type
            ON smart_rule_scope_configs(scope_type)
        ''')
        
        # 规则参数调整记录表索引
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_smart_rule_param_adjustments_rule
            ON smart_rule_param_adjustments(rule_set_code)
        ''')
        
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_smart_rule_param_adjustments_status
            ON smart_rule_param_adjustments(test_status)
        ''')

        # ========== 二期第一轮整改：新表索引 ==========
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_smart_match_rule_snapshots_batch
            ON smart_match_rule_snapshots(batch_id)
        ''')

        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_smart_match_rule_snapshots_code
            ON smart_match_rule_snapshots(rule_set_code)
        ''')

        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_smart_purchase_failure_reasons_batch
            ON smart_purchase_failure_reasons(batch_id)
        ''')

        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_smart_purchase_failure_reasons_code
            ON smart_purchase_failure_reasons(failure_code)
        ''')

        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_smart_purchase_failure_reasons_stage
            ON smart_purchase_failure_reasons(failure_stage)
        ''')

        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_smart_purchase_failure_reasons_snapshot
            ON smart_purchase_failure_reasons(rule_snapshot_id)
        ''')

        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_smart_match_rule_change_logs_code
            ON smart_match_rule_change_logs(rule_set_code)
        ''')

        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_smart_match_rule_publish_logs_code
            ON smart_match_rule_publish_logs(rule_set_code)
        ''')

        conn.commit()
        
        self._migrate_add_raw_data_columns()
        self._migrate_add_role_code_column()
        self._migrate_add_users_security_fields()
        self._migrate_add_operation_logs_fields()
        self._migrate_add_created_by_fields()
        self._migrate_update_permission_names_to_chinese()
        self._migrate_update_permission_names_for_consistency()
        self._migrate_fill_created_by_for_historical_data()
        self._migrate_user_roles_from_single_role()
        self._migrate_add_raw_data_columns_full()
        self._migrate_add_rule_snapshot_id_columns()
        self._migrate_add_failure_code_columns()
        self._migrate_add_rule_set_version_number()
        self._migrate_canonical_rule_keys()
        self._migrate_add_batch_rule_fields()
        
        self._create_default_admin_if_not_exists()
        self._init_app_settings()
        self._init_default_roles_and_permissions()
        self._init_default_rule_sets()
        
        logging.info("数据库初始化完成")
    
    def _migrate_add_raw_data_columns(self):
        conn = self.get_connection()
        cursor = conn.cursor()
        
        try:
            cursor.execute("PRAGMA table_info(ysb_detail_data)")
            columns = [row['name'] for row in cursor.fetchall()]
            
            if 'raw_data' not in columns:
                cursor.execute("ALTER TABLE ysb_detail_data ADD COLUMN raw_data TEXT")
                logging.info("✓ 为 ysb_detail_data 表添加 raw_data 字段")
            
            conn.commit()
        except Exception as e:
            logging.warning(f"Failed to migrate raw_data column: {e}")
            conn.rollback()

    def _migrate_add_role_code_column(self):
        """为users表添加role_code字段"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        try:
            cursor.execute("PRAGMA table_info(users)")
            columns = [row['name'] for row in cursor.fetchall()]
            
            if 'role_code' not in columns:
                cursor.execute("ALTER TABLE users ADD COLUMN role_code TEXT")
                logging.info("✓ 为 users 表添加 role_code 字段")
                
                # 将现有用户的role字段值迁移到role_code字段
            cursor.execute('''
                UPDATE users
                SET role_code = CASE
                    WHEN lower(COALESCE(role, '')) IN ('admin', 'administrator', 'system_admin') THEN 'system_admin'
                    WHEN lower(COALESCE(role, '')) IN ('manager', 'store_manager') THEN 'store_manager'
                    WHEN role_code IN ('system_admin', 'store_manager') THEN role_code
                    ELSE 'store_manager'
                END
                WHERE role_code IS NULL OR role_code = '' OR role_code NOT IN ('system_admin', 'store_manager')
            ''')
            cursor.execute(
                "UPDATE users SET role_code = 'system_admin' WHERE username = ?",
                (DEFAULT_ADMIN_USERNAME,)
            )
            conn.commit()
            logging.info("Migrated users.role to users.role_code")
        except Exception as e:
            logging.warning(f"迁移role_code字段时出错: {e}")
    
    def _migrate_add_users_security_fields(self):
        """为users表添加安全字段"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        try:
            cursor.execute("PRAGMA table_info(users)")
            columns = [row['name'] for row in cursor.fetchall()]
            
            security_fields = [
                ('must_change_password', 'INTEGER DEFAULT 0'),
                ('failed_login_count', 'INTEGER DEFAULT 0'),
                ('locked_until', 'TEXT'),
            ]
            
            for field_name, field_type in security_fields:
                if field_name not in columns:
                    cursor.execute(f"ALTER TABLE users ADD COLUMN {field_name} {field_type}")
                    logging.info(f"Added {field_name} field to users table")
            
            conn.commit()
            logging.info("Users security fields migration completed")
        except Exception as e:
            logging.warning(f"Failed to migrate users security fields: {e}")
            conn.rollback()
    
    def _migrate_add_operation_logs_fields(self):
        """为operation_logs表添加字段"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        try:
            cursor.execute("PRAGMA table_info(operation_logs)")
            columns = [row['name'] for row in cursor.fetchall()]
            
            new_fields = [
                ('permission_code', 'TEXT'),
                ('result', 'TEXT'),
            ]
            
            for field_name, field_type in new_fields:
                if field_name not in columns:
                    cursor.execute(f"ALTER TABLE operation_logs ADD COLUMN {field_name} {field_type}")
                    logging.info(f"Added {field_name} field to operation_logs table")
            
            conn.commit()
            logging.info("Operation logs fields migration completed")
        except Exception as e:
            logging.warning(f"Failed to migrate operation_logs fields: {e}")
            conn.rollback()
    
    def _migrate_add_created_by_fields(self):
        """为数据表添加created_by字段（第四阶段：数据权限扩展）"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        try:
            # reconciliation_tasks 表
            cursor.execute("PRAGMA table_info(reconciliation_tasks)")
            columns = [row['name'] for row in cursor.fetchall()]
            if 'created_by' not in columns:
                cursor.execute("ALTER TABLE reconciliation_tasks ADD COLUMN created_by TEXT")
                logging.info("Added created_by field to reconciliation_tasks table")
            
            # stock_compare_result 表
            cursor.execute("PRAGMA table_info(stock_compare_result)")
            columns = [row['name'] for row in cursor.fetchall()]
            if 'created_by' not in columns:
                cursor.execute("ALTER TABLE stock_compare_result ADD COLUMN created_by TEXT")
                logging.info("Added created_by field to stock_compare_result table")
            
            # yys_sync_task 表
            cursor.execute("PRAGMA table_info(yys_sync_task)")
            columns = [row['name'] for row in cursor.fetchall()]
            if 'created_by' not in columns:
                cursor.execute("ALTER TABLE yys_sync_task ADD COLUMN created_by TEXT")
                logging.info("Added created_by field to yys_sync_task table")
            
            conn.commit()
            logging.info("Created_by fields migration completed")
        except Exception as e:
            logging.warning(f"Failed to migrate created_by fields: {e}")
            conn.rollback()
    
    def _migrate_update_permission_names_to_chinese(self):
        """将权限名称更新为中文"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        try:
            # 权限名称映射（英文 -> 中文）
            permission_names_map = {
                'menu.home': '首页',
                'menu.rpa_robot': 'RPA机器人',
                'menu.smart_purchase': '智能采购',
                'menu.yys_stock': 'YYS库存',
                'menu.jy_stock': 'JY库存',
                'menu.stock_compare': '库存对比',
                'menu.ysb_reconcile': 'YSB对账',
                'menu.reconciliation': '对账记录',
                'menu.task_record': '任务记录',
                'menu.config_center': '配置中心',
                'menu.settings': '系统设置',
                'menu.db_import': '数据库导入',
                'menu.exe_config': 'EXE配置',
                'menu.user_manage': '用户管理',
                'menu.role_permission': '角色权限',
                'menu.operation_logs': '操作日志',
                'menu.logs': '日志查看',
                'operation.user.create': '创建用户',
                'operation.user.update': '编辑用户',
                'operation.user.disable': '禁用用户',
                'operation.user.reset_password': '重置密码',
                'operation.user.unlock': '解锁用户',
                'operation.role.assign_permissions': '分配角色权限',
                'operation.config.save_database': '保存数据库配置',
                'operation.config.save_yys_api': '保存YYS API配置',
                'operation.config.save_supplier_scope': '保存供应商范围',
                'operation.db.import_restore': '导入或恢复数据库',
                'operation.rpa.execute': '执行RPA任务',
                'operation.smart_purchase.import_excel': '导入采购Excel',
                'operation.smart_purchase.run_one_by_one': '逐条执行采购',
                'operation.smart_purchase.retry_failed': '重试失败采购',
                'operation.smart_purchase.cart_backfill': '购物车回填',
                'operation.smart_purchase.export_result': '导出采购结果',
                'operation.ysb_reconcile.import_excel': '导入YSB Excel',
                'operation.ysb_reconcile.supplier_reconcile': '供应商对账',
                'operation.ysb_reconcile.supplier_product_reconcile': '供应商商品对账',
                'operation.ysb_reconcile.export_result': '导出对账结果',
                'operation.yys_stock.import_excel': '导入YYS库存Excel',
                'operation.yys_stock.query_jy_stock': '查询JY库存',
                'operation.yys_stock.compare_stock': '对比库存',
                'operation.yys_stock.test_api_sync': '测试API同步',
                'operation.yys_stock.sync_diff': '同步差异库存',
                'operation.yys_stock.export_result': '导出对比结果',
                'operation.operation_logs.view': '查看操作日志',
                'operation.log.delete': '删除操作日志',
                'operation.log.export': '导出操作日志',
            }
            
            for permission_code, chinese_name in permission_names_map.items():
                cursor.execute('''
                    UPDATE permissions SET permission_name = ? WHERE permission_code = ?
                ''', (chinese_name, permission_code))
            
            conn.commit()
            logging.info("Permission names updated to Chinese")
        except Exception as e:
            logging.warning(f"Failed to update permission names to Chinese: {e}")
            conn.rollback()
    
    def _migrate_update_permission_names_for_consistency(self):
        """更新权限名称以与菜单名称保持一致"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        try:
            # 权限名称修正映射（与菜单显示名称一致）
            permission_names_fix_map = {
                'menu.exe_config': 'EXE配置管理',
                'menu.smart_purchase': '药师帮智能采购',
                'menu.yys_stock': '云药店库存查询',
                'menu.jy_stock': '君元库存查询',
                'menu.task_record': '执行记录',
                'menu.role_permission': '角色权限管理',
                'menu.operation_logs': '日志与截图',
            }
            
            for permission_code, correct_name in permission_names_fix_map.items():
                cursor.execute('''
                    UPDATE permissions SET permission_name = ? WHERE permission_code = ?
                ''', (correct_name, permission_code))
            
            conn.commit()
            logging.info("Permission names updated for consistency with menu names")
        except Exception as e:
            logging.warning(f"Failed to update permission names for consistency: {e}")
            conn.rollback()
    
    def _migrate_fill_created_by_for_historical_data(self):
        """为历史数据填充创建人字段（默认为admin）"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        try:
            # reconciliation_tasks 表
            cursor.execute('''
                UPDATE reconciliation_tasks SET created_by = ? WHERE created_by IS NULL OR created_by = ?
            ''', ('admin', ''))
            cursor.execute('''
                SELECT COUNT(*) as count FROM reconciliation_tasks WHERE created_by IS NULL OR created_by = ?
            ''', ('',))
            result = cursor.fetchone()
            logging.info(f"Filled created_by for reconciliation_tasks: {result['count']} remaining empty")
            
            # stock_compare_result 表
            cursor.execute('''
                UPDATE stock_compare_result SET created_by = ? WHERE created_by IS NULL OR created_by = ?
            ''', ('admin', ''))
            cursor.execute('''
                SELECT COUNT(*) as count FROM stock_compare_result WHERE created_by IS NULL OR created_by = ?
            ''', ('',))
            result = cursor.fetchone()
            logging.info(f"Filled created_by for stock_compare_result: {result['count']} remaining empty")
            
            # yys_import_batch 表
            cursor.execute('''
                UPDATE yys_import_batch SET imported_by = ? WHERE imported_by IS NULL OR imported_by = ?
            ''', ('admin', ''))
            cursor.execute('''
                SELECT COUNT(*) as count FROM yys_import_batch WHERE imported_by IS NULL OR imported_by = ?
            ''', ('',))
            result = cursor.fetchone()
            logging.info(f"Filled imported_by for yys_import_batch: {result['count']} remaining empty")
            
            # yys_sync_task 表
            cursor.execute('''
                UPDATE yys_sync_task SET created_by = ? WHERE created_by IS NULL OR created_by = ?
            ''', ('admin', ''))
            cursor.execute('''
                SELECT COUNT(*) as count FROM yys_sync_task WHERE created_by IS NULL OR created_by = ?
            ''', ('',))
            result = cursor.fetchone()
            logging.info(f"Filled created_by for yys_sync_task: {result['count']} remaining empty")
            
            conn.commit()
            logging.info("Historical data created_by fields filled with default 'admin'")
        except Exception as e:
            logging.warning(f"Failed to fill created_by for historical data: {e}")
            conn.rollback()
    
    def _migrate_user_roles_from_single_role(self):
        """将旧的单角色数据迁移到 user_roles 表"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        try:
            # 检查 user_roles 表是否存在
            cursor.execute('SELECT name FROM sqlite_master WHERE type="table" AND name="user_roles"')
            if not cursor.fetchone():
                logging.warning("user_roles table does not exist")
                return
            
            # 获取所有用户的单角色数据
            cursor.execute('SELECT username, role_code FROM users WHERE role_code IS NOT NULL AND role_code != ""')
            users = cursor.fetchall()
            
            now = datetime.now().isoformat()
            
            for user in users:
                username = user['username']
                role_code = user['role_code']
                
                # 检查是否已存在该关联
                cursor.execute('SELECT id FROM user_roles WHERE username = ? AND role_code = ?', (username, role_code))
                if not cursor.fetchone():
                    cursor.execute('''
                        INSERT INTO user_roles (username, role_code, created_at)
                        VALUES (?, ?, ?)
                    ''', (username, role_code, now))
                    logging.info(f"Migrated user role: {username} -> {role_code}")
            
            conn.commit()
            logging.info("User roles migration completed")
            
        except Exception as e:
            logging.warning(f"Failed to migrate user roles: {e}")
            conn.rollback()
    
    def _init_default_roles_and_permissions(self):
        """鍒濆鍖栭粯璁よ鑹插拰鏉冮檺鏁版嵁"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        now = datetime.now().isoformat()
        
        roles_data = [
            ('system_admin', '系统管理员', '拥有系统全部权限', 1, 'active'),
            ('store_manager', '店长', '日常业务操作权限', 1, 'active'),
        ]
        
        for role_code, role_name, description, is_system_role, status in roles_data:
            cursor.execute('''
                INSERT OR IGNORE INTO roles (role_code, role_name, description, is_system_role, status, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', (role_code, role_name, description, is_system_role, status, now, now))
            
            # 更新已存在的角色名称为中文
            cursor.execute('''
                UPDATE roles SET role_name = ?, description = ?, updated_at = ?
                WHERE role_code = ?
            ''', (role_name, description, now, role_code))
        
        # 鍒濆鍖栨潈闄愮偣
        permissions_data = [
            ('menu.home', '首页', 'menu', None, '首页菜单', 1),
            ('menu.rpa_robot', 'RPA机器人', 'menu', None, 'RPA机器人菜单', 2),
            ('menu.smart_purchase', '智能采购', 'menu', None, '智能采购菜单', 3),
            ('menu.yys_stock', 'YYS库存', 'menu', None, 'YYS库存菜单', 4),
            ('menu.jy_stock', 'JY库存', 'menu', None, 'JY库存菜单', 5),
            ('menu.stock_compare', '库存对比', 'menu', None, '库存对比菜单', 6),
            ('menu.ysb_reconcile', 'YSB对账', 'menu', None, 'YSB对账菜单', 7),
            ('menu.reconciliation', '对账记录', 'menu', None, '对账记录菜单', 8),
            ('menu.task_record', '任务记录', 'menu', None, '任务记录菜单', 9),
            ('menu.config_center', '配置中心', 'menu', None, '配置中心菜单', 10),
            ('menu.settings', '系统设置', 'menu', None, '系统设置菜单', 11),
            ('menu.db_import', '数据库导入', 'menu', None, '数据库导入菜单', 12),
            ('menu.exe_config', 'EXE配置', 'menu', None, 'EXE配置菜单', 13),
            ('menu.user_manage', '用户管理', 'menu', None, '用户管理菜单', 14),
            ('menu.role_permission', '角色权限', 'menu', None, '角色权限菜单', 15),
            ('menu.operation_logs', '操作日志', 'menu', None, '操作日志菜单', 16),
            ('menu.logs', '日志查看', 'menu', None, '日志查看菜单', 17),
            ('operation.user.create', '创建用户', 'operation', 'menu.user_manage', '创建新用户', 101),
            ('operation.user.update', '编辑用户', 'operation', 'menu.user_manage', '编辑用户信息', 102),
            ('operation.user.disable', '禁用用户', 'operation', 'menu.user_manage', '禁用用户账号', 103),
            ('operation.user.reset_password', '重置密码', 'operation', 'menu.user_manage', '重置用户密码', 104),
            ('operation.user.unlock', '解锁用户', 'operation', 'menu.user_manage', '解锁用户账号', 105),
            ('operation.role.assign_permissions', '分配角色权限', 'operation', 'menu.role_permission', '分配角色权限', 111),
            ('operation.config.save_database', '保存数据库配置', 'operation', 'menu.config_center', '保存数据库配置', 121),
            ('operation.config.save_yys_api', '保存YYS API配置', 'operation', 'menu.config_center', '保存YYS API配置', 122),
            ('operation.config.save_supplier_scope', '保存供应商范围', 'operation', 'menu.smart_purchase', '保存供应商范围', 123),
            ('operation.db.import_restore', '导入或恢复数据库', 'operation', 'menu.db_import', '导入或恢复数据库', 131),
            ('operation.rpa.execute', '执行RPA任务', 'operation', 'menu.rpa_robot', '执行RPA任务', 141),
            ('operation.smart_purchase.import_excel', '导入采购Excel', 'operation', 'menu.smart_purchase', '导入采购Excel文件', 151),
            ('operation.smart_purchase.run_one_by_one', '逐条执行采购', 'operation', 'menu.smart_purchase', '逐条执行采购任务', 152),
            ('operation.smart_purchase.retry_failed', '重试失败采购', 'operation', 'menu.smart_purchase', '重试失败的采购任务', 153),
            ('operation.smart_purchase.cart_backfill', '购物车回填', 'operation', 'menu.smart_purchase', '购物车回填', 154),
            ('operation.smart_purchase.export_result', '导出采购结果', 'operation', 'menu.smart_purchase', '导出采购结果', 155),
            ('operation.ysb_reconcile.import_excel', '导入YSB Excel', 'operation', 'menu.ysb_reconcile', '导入YSB Excel文件', 161),
            ('operation.ysb_reconcile.supplier_reconcile', '供应商对账', 'operation', 'menu.ysb_reconcile', '供应商对账', 162),
            ('operation.ysb_reconcile.supplier_product_reconcile', '供应商商品对账', 'operation', 'menu.ysb_reconcile', '供应商商品对账', 163),
            ('operation.ysb_reconcile.export_result', '导出对账结果', 'operation', 'menu.ysb_reconcile', '导出对账结果', 164),
            ('operation.yys_stock.import_excel', '导入YYS库存Excel', 'operation', 'menu.yys_stock', '导入YYS库存Excel文件', 171),
            ('operation.yys_stock.query_jy_stock', '查询JY库存', 'operation', 'menu.jy_stock', '查询JY库存', 172),
            ('operation.yys_stock.compare_stock', '对比库存', 'operation', 'menu.stock_compare', '对比库存', 173),
            ('operation.yys_stock.test_api_sync', '测试API同步', 'operation', 'menu.stock_compare', '测试API同步', 174),
            ('operation.yys_stock.sync_diff', '同步差异库存', 'operation', 'menu.stock_compare', '同步差异库存', 175),
            ('operation.yys_stock.export_result', '导出对比结果', 'operation', 'menu.stock_compare', '导出库存对比结果', 176),
            ('operation.operation_logs.view', '查看操作日志', 'operation', 'menu.operation_logs', '查看操作日志', 181),
            ('operation.log.delete', '删除操作日志', 'operation', 'menu.operation_logs', '删除操作日志', 182),
            ('operation.log.export', '导出操作日志', 'operation', 'menu.operation_logs', '导出操作日志', 183),
            ('menu.medical_price_control', '医保价格管控', 'menu', None, '医保价格管控菜单', 190),
            ('operation.medical_price.import_catalog', '导入医保目录', 'operation', 'menu.medical_price_control', '导入医保目录Excel文件', 191),
            ('operation.medical_price.import_price_limit', '导入价格上限', 'operation', 'menu.medical_price_control', '导入医保价格上限Excel文件', 192),
            ('operation.medical_price.import_cloud_catalog', '导入商品目录', 'operation', 'menu.medical_price_control', '导入云药店商品目录Excel文件', 193),
            ('operation.medical_price.fetch_junyuan_price', '抓取君元价格', 'operation', 'menu.medical_price_control', '从君元数据库抓取销售价格', 194),
            ('operation.medical_price.run_compare', '执行价格比对', 'operation', 'menu.medical_price_control', '执行医保价格比对', 195),
            ('operation.medical_price.handle_result', '处理比对结果', 'operation', 'menu.medical_price_control', '处理价格比对异常结果', 196),
            ('operation.medical_price.export_result', '导出比对结果', 'operation', 'menu.medical_price_control', '导出价格比对结果', 197),
            ('menu.medical_price_compare', '价格比对', 'menu', 'menu.medical_price_control', '价格比对菜单', 198),
            ('menu.medical_compare_result_query', '比对结果查询', 'menu', 'menu.medical_price_control', '比对结果查询菜单', 199),
            ('menu.medical_western_query', '医保西药查询', 'menu', 'menu.medical_price_control', '医保西药目录查询菜单', 200),
            ('menu.medical_chinese_query', '医保中成药查询', 'menu', 'menu.medical_price_control', '医保中成药目录查询菜单', 201),
            ('menu.medical_price_limit_query', '价格上限查询', 'menu', 'menu.medical_price_control', '医保价格上限查询菜单', 202),
            ('menu.medical_cloud_catalog_query', '商品信息查询', 'menu', 'menu.medical_price_control', '云药店商品信息查询菜单', 203),
            ('menu.system_management', '系统管理', 'menu', None, '系统管理菜单', 220),
            ('menu.tts', '文本转语音', 'menu', 'menu.system_management', '文本转语音菜单', 221),
            ('operation.tts.generate', '生成语音', 'operation', 'menu.tts', '生成文本转语音', 222),
            ('operation.tts.download', '下载音频', 'operation', 'menu.tts', '下载生成的音频文件', 223),
        ]
        
        for permission_code, permission_name, permission_type, parent_code, description, sort_order in permissions_data:
            cursor.execute('''
                INSERT OR IGNORE INTO permissions (permission_code, permission_name, permission_type, parent_code, description, sort_order, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', (permission_code, permission_name, permission_type, parent_code, description, sort_order, now))
        
        cursor.execute('SELECT permission_code FROM permissions')
        all_permissions = [row['permission_code'] for row in cursor.fetchall()]
        
        for permission_code in all_permissions:
            cursor.execute('''
                INSERT OR IGNORE INTO role_permissions (role_code, permission_code, created_at)
                VALUES (?, ?, ?)
            ''', ('system_admin', permission_code, now))
        
        # 鍒濆鍖栬鑹叉潈闄愬叧鑱?- 搴楅暱鎷ユ湁涓氬姟鏉冮檺
        store_manager_permissions = [
            'menu.home', 'menu.rpa_robot', 'menu.smart_purchase', 'menu.yys_stock',
            'menu.jy_stock', 'menu.stock_compare', 'menu.ysb_reconcile',
            'menu.reconciliation', 'menu.task_record', 'menu.medical_price_control',
            'operation.rpa.execute',
            'operation.smart_purchase.import_excel',
            'operation.smart_purchase.run_one_by_one',
            'operation.smart_purchase.retry_failed',
            'operation.smart_purchase.cart_backfill',
            'operation.smart_purchase.export_result',
            'operation.ysb_reconcile.import_excel',
            'operation.ysb_reconcile.supplier_reconcile',
            'operation.ysb_reconcile.supplier_product_reconcile',
            'operation.ysb_reconcile.export_result',
            'operation.yys_stock.import_excel',
            'operation.yys_stock.query_jy_stock',
            'operation.yys_stock.compare_stock',
            'operation.yys_stock.test_api_sync',
            'operation.yys_stock.sync_diff',
            'operation.medical_price.import_catalog',
            'operation.medical_price.import_price_limit',
            'operation.medical_price.import_cloud_catalog',
            'operation.medical_price.fetch_junyuan_price',
            'operation.medical_price.run_compare',
            'operation.medical_price.handle_result',
            'operation.medical_price.export_result',
            'menu.medical_price_compare',
            'menu.medical_compare_result_query',
            'menu.medical_western_query',
            'menu.medical_chinese_query',
            'menu.medical_price_limit_query',
            'menu.medical_cloud_catalog_query',
            'menu.system_management',
            'menu.tts',
            'operation.tts.generate',
            'operation.tts.download',
            'operation.config.save_supplier_scope',
        ]
        
        for permission_code in store_manager_permissions:
            cursor.execute('''
                INSERT OR IGNORE INTO role_permissions (role_code, permission_code, created_at)
                VALUES (?, ?, ?)
            ''', ('store_manager', permission_code, now))
        
        conn.commit()
        logging.info("Database log message")
    
    def _init_default_rule_sets(self):
        """初始化默认规则集"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        now = datetime.now().isoformat()
        
        # 初始化规则集
        rule_sets_data = [
            ('default_v1', '默认规则集v1', '默认的智能采购匹配规则集', 1, 1, 'system', now, now),
            ('strict_spec_v1', '严格规格规则集v1', '严格规格匹配的智能采购规则集', 0, 1, 'system', now, now),
        ]
        
        for rule_set_code, rule_set_name, description, is_default, is_enabled, created_by, created_at, updated_at in rule_sets_data:
            cursor.execute('''
                INSERT OR IGNORE INTO smart_match_rule_sets (rule_set_code, rule_set_name, description, is_default, is_enabled, created_by, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ''', (rule_set_code, rule_set_name, description, is_default, is_enabled, created_by, created_at, updated_at))
        
        # 初始化规则配置 - default_v1
        default_v1_configs = [
            # 三期 canonical 键
            ('default_v1', 'name_weight', '名称权重', '0.62', 'number', '名称匹配的权重', 1, 1, now, now),
            ('default_v1', 'spec_weight', '规格权重', '0.20', 'number', '规格匹配的权重', 2, 1, now, now),
            ('default_v1', 'maker_weight', '厂家权重', '0.18', 'number', '厂家匹配的权重', 3, 1, now, now),
            ('default_v1', 'min_purchase_score', '候选采购最低总分', '70', 'number', '总分达到此阈值才合格', 4, 1, now, now),
            ('default_v1', 'cart_backfill_min_score', '购物车反写最低分', '60', 'number', '购物车反写最低分', 5, 1, now, now),
            ('default_v1', 'spec_conflict_block', '规格冲突是否阻断', '0', 'boolean', '规格冲突是否阻断采购', 6, 1, now, now),
            ('default_v1', 'maker_strict', '厂家严格匹配', '0', 'boolean', '是否严格匹配厂家', 7, 1, now, now),
            ('default_v1', 'supplier_scope_required', '是否必须命中供应商范围', '0', 'boolean', '是否必须命中供应商范围', 8, 1, now, now),
            ('default_v1', 'price_check_enabled', '是否启用价格校验', '1', 'boolean', '是否启用价格校验', 9, 1, now, now),
            ('default_v1', 'price_compare_discount', '候选价格折算系数', '0.97', 'number', '候选价格折算系数', 10, 1, now, now),
            ('default_v1', 'price_upper_rate', '最高允许价比例', '1.05', 'number', '最高允许价比例', 11, 1, now, now),
            ('default_v1', 'price_upper_plus', '最高允许价固定增量', '1', 'number', '最高允许价固定增量', 12, 1, now, now),
            ('default_v1', 'name_core_min_score', '名称核心相似最低分', '70', 'number', '名称核心相似最低分', 13, 1, now, now),
            ('default_v1', 'spec_similar_min_score', '规格相似最低分', '70', 'number', '规格相似最低分', 14, 1, now, now),
            ('default_v1', 'factory_similar_min_score', '厂家筛选相似最低分', '70', 'number', '厂家筛选相似最低分', 15, 1, now, now),
            ('default_v1', 'cart_existing_same_product_min_score', '购物车同品种识别最低分', '70', 'number', '购物车同品种识别最低分', 16, 1, now, now),
        ]
        
        for rule_set_code, rule_key, rule_name, rule_value, rule_type, description, sort_order, is_enabled, created_at, updated_at in default_v1_configs:
            cursor.execute('''
                INSERT OR IGNORE INTO smart_match_rule_configs (rule_set_code, rule_key, rule_name, rule_value, rule_type, description, sort_order, is_enabled, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (rule_set_code, rule_key, rule_name, rule_value, rule_type, description, sort_order, is_enabled, created_at, updated_at))
        
        # 初始化规则配置 - strict_spec_v1
        strict_spec_v1_configs = [
            # 三期 canonical 键
            ('strict_spec_v1', 'name_weight', '名称权重', '0.62', 'number', '名称匹配的权重', 1, 1, now, now),
            ('strict_spec_v1', 'spec_weight', '规格权重', '0.20', 'number', '规格匹配的权重', 2, 1, now, now),
            ('strict_spec_v1', 'maker_weight', '厂家权重', '0.18', 'number', '厂家匹配的权重', 3, 1, now, now),
            ('strict_spec_v1', 'min_purchase_score', '候选采购最低总分', '70', 'number', '总分达到此阈值才合格', 4, 1, now, now),
            ('strict_spec_v1', 'cart_backfill_min_score', '购物车反写最低分', '60', 'number', '购物车反写最低分', 5, 1, now, now),
            ('strict_spec_v1', 'spec_conflict_block', '规格冲突是否阻断', '1', 'boolean', '规格冲突是否阻断采购', 6, 1, now, now),
            ('strict_spec_v1', 'maker_strict', '厂家严格匹配', '0', 'boolean', '是否严格匹配厂家', 7, 1, now, now),
            ('strict_spec_v1', 'supplier_scope_required', '是否必须命中供应商范围', '0', 'boolean', '是否必须命中供应商范围', 8, 1, now, now),
            ('strict_spec_v1', 'price_check_enabled', '是否启用价格校验', '1', 'boolean', '是否启用价格校验', 9, 1, now, now),
            ('strict_spec_v1', 'price_compare_discount', '候选价格折算系数', '0.97', 'number', '候选价格折算系数', 10, 1, now, now),
            ('strict_spec_v1', 'price_upper_rate', '最高允许价比例', '1.05', 'number', '最高允许价比例', 11, 1, now, now),
            ('strict_spec_v1', 'price_upper_plus', '最高允许价固定增量', '1', 'number', '最高允许价固定增量', 12, 1, now, now),
            ('strict_spec_v1', 'name_core_min_score', '名称核心相似最低分', '70', 'number', '名称核心相似最低分', 13, 1, now, now),
            ('strict_spec_v1', 'spec_similar_min_score', '规格相似最低分', '70', 'number', '规格相似最低分', 14, 1, now, now),
            ('strict_spec_v1', 'factory_similar_min_score', '厂家筛选相似最低分', '70', 'number', '厂家筛选相似最低分', 15, 1, now, now),
            ('strict_spec_v1', 'cart_existing_same_product_min_score', '购物车同品种识别最低分', '70', 'number', '购物车同品种识别最低分', 16, 1, now, now),
        ]
        
        for rule_set_code, rule_key, rule_name, rule_value, rule_type, description, sort_order, is_enabled, created_at, updated_at in strict_spec_v1_configs:
            cursor.execute('''
                INSERT OR IGNORE INTO smart_match_rule_configs (rule_set_code, rule_key, rule_name, rule_value, rule_type, description, sort_order, is_enabled, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (rule_set_code, rule_key, rule_name, rule_value, rule_type, description, sort_order, is_enabled, created_at, updated_at))
        
        conn.commit()
        logging.info("默认规则集初始化完成")
    
    def _migrate_add_raw_data_columns_full(self):
        """Migrate raw_data related columns."""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        try:
            cursor.execute("PRAGMA table_info(ysb_detail_data)")
            columns = [row['name'] for row in cursor.fetchall()]
            
            if 'raw_data' not in columns:
                cursor.execute("ALTER TABLE ysb_detail_data ADD COLUMN raw_data TEXT")
                logging.info("✓ 为 ysb_detail_data 表添加 raw_data 字段")
            
            cursor.execute("PRAGMA table_info(ysb_supplier_summary)")
            columns = [row['name'] for row in cursor.fetchall()]
            
            if 'raw_data' not in columns:
                cursor.execute("ALTER TABLE ysb_supplier_summary ADD COLUMN raw_data TEXT")
                logging.info("✓ 为 ysb_supplier_summary 表添加 raw_data 字段")
            
            cursor.execute("DROP INDEX IF EXISTS idx_ysb_supplier_unique")
            cursor.execute('''
                CREATE INDEX IF NOT EXISTS idx_ysb_supplier_company
                ON ysb_supplier_summary(import_batch_id, ysb_company_name)
            ''')
            
            cursor.execute("PRAGMA table_info(reconciliation_tasks)")
            columns = [row['name'] for row in cursor.fetchall()]
            
            fields_to_add = [
                ('task_type', 'TEXT DEFAULT "all"'),
                ('supplier_match_count', 'INTEGER DEFAULT 0'),
                ('supplier_diff_count', 'INTEGER DEFAULT 0'),
                ('product_match_count', 'INTEGER DEFAULT 0'),
                ('product_diff_count', 'INTEGER DEFAULT 0'),
            ]
            
            for field_name, field_type in fields_to_add:
                if field_name not in columns:
                    cursor.execute(f"ALTER TABLE reconciliation_tasks ADD COLUMN {field_name} {field_type}")
                    logging.info(f"✓ 为 reconciliation_tasks 表添加 {field_name} 字段")
            
            cursor.execute("PRAGMA table_info(ysb_import_batches)")
            columns = [row['name'] for row in cursor.fetchall()]
            
            ysb_batch_fields = [
                ('account_year', 'INTEGER'),
                ('account_month', 'INTEGER'),
            ]
            
            for field_name, field_type in ysb_batch_fields:
                if field_name not in columns:
                    cursor.execute(f"ALTER TABLE ysb_import_batches ADD COLUMN {field_name} {field_type}")
                    logging.info(f"✓ 为 ysb_import_batches 表添加 {field_name} 字段")
            
            cursor.execute("PRAGMA table_info(yys_import_detail)")
            columns = [row['name'] for row in cursor.fetchall()]
            
            yys_detail_fields = [
                ('warehouse', 'TEXT'),
                ('productno', 'TEXT'),
            ]
            
            for field_name, field_type in yys_detail_fields:
                if field_name not in columns:
                    cursor.execute(f"ALTER TABLE yys_import_detail ADD COLUMN {field_name} {field_type}")
                    logging.info(f"✓ 为 yys_import_detail 表添加 {field_name} 字段")
            
            # 为 jy_stock_query 表添加字段
            cursor.execute("PRAGMA table_info(jy_stock_query)")
            jy_columns = [row['name'] for row in cursor.fetchall()]
            
            jy_fields = [
                ('specification', 'TEXT'),
                ('approval_number', 'TEXT'),
            ]
            
            for field_name, field_type in jy_fields:
                if field_name not in jy_columns:
                    cursor.execute(f"ALTER TABLE jy_stock_query ADD COLUMN {field_name} {field_type}")
                    logging.info(f"✓ 为 jy_stock_query 表添加 {field_name} 字段")
            
            # 为 junyuan_sales_price 表添加库存数量字段
            cursor.execute("PRAGMA table_info(junyuan_sales_price)")
            jy_sales_columns = [row['name'] for row in cursor.fetchall()]
            
            jy_sales_fields = [
                ('库存数量', 'TEXT'),
                ('三月销量', 'TEXT'),
            ]
            
            for field_name, field_type in jy_sales_fields:
                if field_name not in jy_sales_columns:
                    cursor.execute(f"ALTER TABLE junyuan_sales_price ADD COLUMN {field_name} {field_type}")
                    logging.info(f"✓ 为 junyuan_sales_price 表添加 {field_name} 字段")
            
            # 为 medical_price_compare_result 表添加君元商品字段
            cursor.execute("PRAGMA table_info(medical_price_compare_result)")
            medical_columns = [row['name'] for row in cursor.fetchall()]
            
            medical_fields = [
                ('君元商品编码', 'TEXT'),
                ('君元商品名称', 'TEXT'),
                ('君元规格', 'TEXT'),
                ('君元生产厂家', 'TEXT'),
                ('君元库存数量', 'TEXT'),
                ('三同药品参比价', 'TEXT'),
                ('医保基础价格_中成药', 'TEXT'),
                ('西药医保编码', 'TEXT'),
                ('中成药医保编码', 'TEXT'),
                ('三同医保编码', 'TEXT'),
                ('超基础金额_中成药', 'TEXT'),
            ]
            
            for field_name, field_type in medical_fields:
                if field_name not in medical_columns:
                    cursor.execute(f"ALTER TABLE medical_price_compare_result ADD COLUMN {field_name} {field_type}")
                    logging.info(f"✓ 为 medical_price_compare_result 表添加 {field_name} 字段")
            
            conn.commit()
        except Exception as e:
            logging.warning(f"数据库迁移失败（字段可能已存在）: {e}")
            conn.rollback()

    def _migrate_add_rule_snapshot_id_columns(self):
        """为候选表和反写表添加 rule_snapshot_id 字段"""
        conn = self.get_connection()
        cursor = conn.cursor()
        try:
            # smart_purchase_candidates 添加 rule_snapshot_id
            cursor.execute("PRAGMA table_info(smart_purchase_candidates)")
            columns = [row['name'] for row in cursor.fetchall()]
            if 'rule_snapshot_id' not in columns:
                cursor.execute("ALTER TABLE smart_purchase_candidates ADD COLUMN rule_snapshot_id TEXT")
                logging.info("✓ 为 smart_purchase_candidates 表添加 rule_snapshot_id 字段")

            # smart_cart_backfill_matches 添加 rule_snapshot_id
            cursor.execute("PRAGMA table_info(smart_cart_backfill_matches)")
            columns = [row['name'] for row in cursor.fetchall()]
            if 'rule_snapshot_id' not in columns:
                cursor.execute("ALTER TABLE smart_cart_backfill_matches ADD COLUMN rule_snapshot_id TEXT")
                logging.info("✓ 为 smart_cart_backfill_matches 表添加 rule_snapshot_id 字段")

            # purchase_candidate_scores 添加 rule_snapshot_id
            cursor.execute("PRAGMA table_info(purchase_candidate_scores)")
            columns = [row['name'] for row in cursor.fetchall()]
            if 'rule_snapshot_id' not in columns:
                cursor.execute("ALTER TABLE purchase_candidate_scores ADD COLUMN rule_snapshot_id TEXT")
                logging.info("✓ 为 purchase_candidate_scores 表添加 rule_snapshot_id 字段")

            conn.commit()
        except Exception as e:
            logging.warning(f"添加 rule_snapshot_id 字段迁移失败: {e}")
            conn.rollback()

    def _migrate_add_failure_code_columns(self):
        """为采购明细表添加 failure_stage 和 failure_code 字段"""
        conn = self.get_connection()
        cursor = conn.cursor()
        try:
            # 先检查表是否存在
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='smart_purchase_items'")
            if not cursor.fetchone():
                return
            cursor.execute("PRAGMA table_info(smart_purchase_items)")
            columns = [row['name'] for row in cursor.fetchall()]
            if 'failure_stage' not in columns:
                cursor.execute("ALTER TABLE smart_purchase_items ADD COLUMN failure_stage TEXT")
                logging.info("✓ 为 smart_purchase_items 表添加 failure_stage 字段")
            if 'failure_code' not in columns:
                cursor.execute("ALTER TABLE smart_purchase_items ADD COLUMN failure_code TEXT")
                logging.info("✓ 为 smart_purchase_items 表添加 failure_code 字段")
            conn.commit()
        except Exception as e:
            logging.warning(f"添加 failure_code 字段迁移失败: {e}")
            conn.rollback()

    def _migrate_add_rule_set_version_number(self):
        """为历史数据库的 smart_match_rule_sets 表补充 version_number 等二期字段"""
        conn = self.get_connection()
        cursor = conn.cursor()
        try:
            # 检查表是否存在
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='smart_match_rule_sets'")
            if not cursor.fetchone():
                return

            cursor.execute("PRAGMA table_info(smart_match_rule_sets)")
            columns = [row['name'] for row in cursor.fetchall()]

            # 逐个添加缺失的二期字段（幂等：已存在则跳过）
            new_columns = [
                ("version_number", "TEXT DEFAULT 'v1.0.0'"),
                ("version_status", "TEXT DEFAULT 'active'"),
                ("release_date", "TEXT"),
                ("deprecation_date", "TEXT"),
                ("change_reason", "TEXT"),
                ("change_type", "TEXT DEFAULT 'new'"),
                ("audit_status", "TEXT DEFAULT 'approved'"),
                ("audit_by", "TEXT"),
                ("audit_at", "TEXT"),
                ("audit_comment", "TEXT"),
                ("gray_release_scope", "TEXT"),
                ("gray_release_ratio", "INTEGER DEFAULT 0"),
                ("gray_release_status", "TEXT DEFAULT 'none'"),
                ("updated_by", "TEXT"),
            ]

            for col_name, col_def in new_columns:
                if col_name not in columns:
                    cursor.execute(f"ALTER TABLE smart_match_rule_sets ADD COLUMN {col_name} {col_def}")
                    logging.info(f"✓ 为 smart_match_rule_sets 表添加 {col_name} 字段")

            # 为现有规则集填充默认版本号（仅当 version_number 为空时）
            cursor.execute(
                "UPDATE smart_match_rule_sets SET version_number = 'v1.0.0' WHERE version_number IS NULL OR version_number = ''"
            )

            conn.commit()
        except Exception as e:
            logging.warning(f"添加 rule_set version_number 字段迁移失败: {e}")
            conn.rollback()

    def _migrate_canonical_rule_keys(self):
        """三期迁移：将旧规则键迁移为 canonical 键，并补充缺失的 canonical 配置项"""
        conn = self.get_connection()
        cursor = conn.cursor()
        try:
            # 检查表是否存在
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='smart_match_rule_configs'")
            if not cursor.fetchone():
                return

            # 旧键到 canonical 键的映射
            key_mapping = {
                "total_score_threshold": "min_purchase_score",
                "price_tolerance": "price_compare_discount",
                "spec_strict": "spec_conflict_block",
            }

            for old_key, new_key in key_mapping.items():
                # 检查旧键是否存在
                cursor.execute(
                    "SELECT rule_set_code, rule_value, rule_type FROM smart_match_rule_configs WHERE rule_key = ?",
                    (old_key,)
                )
                old_rows = cursor.fetchall()

                for row in old_rows:
                    rule_set_code = row["rule_set_code"]
                    rule_value = row["rule_value"]
                    rule_type = row["rule_type"]

                    # 检查 canonical 键是否已存在
                    cursor.execute(
                        "SELECT id FROM smart_match_rule_configs WHERE rule_set_code = ? AND rule_key = ?",
                        (rule_set_code, new_key)
                    )
                    existing = cursor.fetchone()

                    if existing:
                        # canonical 键已存在，删除旧键
                        cursor.execute(
                            "DELETE FROM smart_match_rule_configs WHERE rule_set_code = ? AND rule_key = ?",
                            (rule_set_code, old_key)
                        )
                        logging.info(f"✓ 删除旧键 {old_key}（canonical 键 {new_key} 已存在）: {rule_set_code}")
                    else:
                        # canonical 键不存在，将旧键重命名为 canonical 键
                        cursor.execute(
                            "UPDATE smart_match_rule_configs SET rule_key = ? WHERE rule_set_code = ? AND rule_key = ?",
                            (new_key, rule_set_code, old_key)
                        )
                        logging.info(f"✓ 迁移旧键 {old_key} → {new_key}: {rule_set_code}")

            # 补充缺失的 canonical 配置项
            now = datetime.now().isoformat()
            canonical_configs = {
                "default_v1": [
                    ("cart_backfill_min_score", "购物车反写最低分", "60", "number", "购物车反写最低分", 5),
                    ("supplier_scope_required", "是否必须命中供应商范围", "0", "boolean", "是否必须命中供应商范围", 8),
                    ("price_check_enabled", "是否启用价格校验", "1", "boolean", "是否启用价格校验", 9),
                    ("price_upper_rate", "最高允许价比例", "1.05", "number", "最高允许价比例", 11),
                    ("price_upper_plus", "最高允许价固定增量", "1", "number", "最高允许价固定增量", 12),
                    ("name_core_min_score", "名称核心相似最低分", "70", "number", "名称核心相似最低分", 13),
                    ("spec_similar_min_score", "规格相似最低分", "70", "number", "规格相似最低分", 14),
                    ("factory_similar_min_score", "厂家筛选相似最低分", "70", "number", "厂家筛选相似最低分", 15),
                    ("cart_existing_same_product_min_score", "购物车同品种识别最低分", "70", "number", "购物车同品种识别最低分", 16),
                ],
                "strict_spec_v1": [
                    ("cart_backfill_min_score", "购物车反写最低分", "60", "number", "购物车反写最低分", 5),
                    ("supplier_scope_required", "是否必须命中供应商范围", "0", "boolean", "是否必须命中供应商范围", 8),
                    ("price_check_enabled", "是否启用价格校验", "1", "boolean", "是否启用价格校验", 9),
                    ("price_upper_rate", "最高允许价比例", "1.05", "number", "最高允许价比例", 11),
                    ("price_upper_plus", "最高允许价固定增量", "1", "number", "最高允许价固定增量", 12),
                    ("name_core_min_score", "名称核心相似最低分", "70", "number", "名称核心相似最低分", 13),
                    ("spec_similar_min_score", "规格相似最低分", "70", "number", "规格相似最低分", 14),
                    ("factory_similar_min_score", "厂家筛选相似最低分", "70", "number", "厂家筛选相似最低分", 15),
                    ("cart_existing_same_product_min_score", "购物车同品种识别最低分", "70", "number", "购物车同品种识别最低分", 16),
                ],
            }

            for rule_set_code, configs in canonical_configs.items():
                for rule_key, rule_name, rule_value, rule_type, description, sort_order in configs:
                    cursor.execute(
                        "SELECT id FROM smart_match_rule_configs WHERE rule_set_code = ? AND rule_key = ?",
                        (rule_set_code, rule_key)
                    )
                    if not cursor.fetchone():
                        cursor.execute('''
                            INSERT INTO smart_match_rule_configs (rule_set_code, rule_key, rule_name, rule_value, rule_type, description, sort_order, is_enabled, created_at, updated_at)
                            VALUES (?, ?, ?, ?, ?, ?, ?, 1, ?, ?)
                        ''', (rule_set_code, rule_key, rule_name, rule_value, rule_type, description, sort_order, now, now))
                        logging.info(f"✓ 补充 canonical 键 {rule_key}: {rule_set_code}")

            conn.commit()
            logging.info("三期 canonical 键迁移完成")
        except Exception as e:
            logging.warning(f"三期 canonical 键迁移失败: {e}")
            conn.rollback()

    def _migrate_add_batch_rule_fields(self):
        """三期迁移：为 smart_purchase_batches 表补充规则选择字段"""
        conn = self.get_connection()
        cursor = conn.cursor()
        try:
            # 检查表是否存在
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='smart_purchase_batches'")
            if not cursor.fetchone():
                return

            cursor.execute("PRAGMA table_info(smart_purchase_batches)")
            columns = [row['name'] for row in cursor.fetchall()]

            new_columns = [
                ("rule_set_code", "TEXT"),
                ("rule_set_version", "TEXT"),
                ("rule_select_mode", "TEXT DEFAULT 'default'"),
                ("rule_select_reason", "TEXT"),
                ("rule_snapshot_id", "TEXT"),
                ("rule_selected_by", "TEXT"),
                ("rule_selected_at", "TEXT"),
            ]

            for col_name, col_def in new_columns:
                if col_name not in columns:
                    cursor.execute(f"ALTER TABLE smart_purchase_batches ADD COLUMN {col_name} {col_def}")
                    logging.info(f"✓ 为 smart_purchase_batches 表添加 {col_name} 字段")

            conn.commit()
        except Exception as e:
            logging.warning(f"添加批次规则字段迁移失败: {e}")
            conn.rollback()

    def _create_default_admin_if_not_exists(self):
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cursor.execute("SELECT COUNT(*) as count FROM users")
        result = cursor.fetchone()
        
        if result['count'] == 0:
            password_data = PasswordService.create_password_hash(DEFAULT_ADMIN_PASSWORD)
            now = datetime.now().isoformat()
            
            cursor.execute('''
                INSERT INTO users (username, password_hash, salt, hash_iterations, 
                                   display_name, role, role_code, status, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                DEFAULT_ADMIN_USERNAME,
                password_data['password_hash'],
                password_data['salt'],
                password_data['hash_iterations'],
                'System Admin',
                'admin',
                'system_admin',
                'active',
                now,
                now
            ))
            conn.commit()
            logging.info(f"宸插垱寤洪粯璁ょ鐞嗗憳璐﹀彿: {DEFAULT_ADMIN_USERNAME}")
    
    def _init_app_settings(self):
        conn = self.get_connection()
        cursor = conn.cursor()
        now = datetime.now().isoformat()
        
        default_settings = {
            'app_version': APP_VERSION,
            'first_run_completed': 'false',
            'remembered_username': '',
            'last_login_user': ''
        }
        
        for key, value in default_settings.items():
            cursor.execute('''
                INSERT OR IGNORE INTO app_settings (key, value, updated_at)
                VALUES (?, ?, ?)
            ''', (key, value, now))
        
        conn.commit()
    
    def get_user_by_username(self, username: str) -> Optional[dict]:
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM users WHERE username = ?", (username,))
        row = cursor.fetchone()
        return dict(row) if row else None
    
    def update_last_login(self, username: str):
        conn = self.get_connection()
        cursor = conn.cursor()
        now = datetime.now().isoformat()
        cursor.execute(
            "UPDATE users SET last_login_at = ?, updated_at = ? WHERE username = ?",
            (now, now, username)
        )
        conn.commit()
    
    def update_password(self, username: str, password_hash: str, salt: str, iterations: int):
        conn = self.get_connection()
        cursor = conn.cursor()
        now = datetime.now().isoformat()
        cursor.execute('''
            UPDATE users 
            SET password_hash = ?, salt = ?, hash_iterations = ?, updated_at = ?
            WHERE username = ?
        ''', (password_hash, salt, iterations, now, username))
        conn.commit()
    
    def add_login_log(self, username: str, success: bool, message: str, machine_name: str = ""):
        conn = self.get_connection()
        cursor = conn.cursor()
        now = datetime.now().isoformat()
        cursor.execute('''
            INSERT INTO login_logs (username, success, message, login_at, machine_name)
            VALUES (?, ?, ?, ?, ?)
        ''', (username, 1 if success else 0, message, now, machine_name))
        conn.commit()
    
    def get_setting(self, key: str) -> Optional[str]:
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT value FROM app_settings WHERE key = ?", (key,))
        row = cursor.fetchone()
        return row['value'] if row else None
    
    def set_setting(self, key: str, value: str):
        conn = self.get_connection()
        cursor = conn.cursor()
        now = datetime.now().isoformat()
        cursor.execute('''
            INSERT OR REPLACE INTO app_settings (key, value, updated_at)
            VALUES (?, ?, ?)
        ''', (key, value, now))
        conn.commit()
