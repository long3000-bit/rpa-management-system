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
        logging.info(f"鏁版嵁搴撹繛鎺?- 鑾峰彇杩炴帴璇锋眰, 褰撳墠杩炴帴鐘舵€? {self.conn is not None}")
        
        if self.conn is not None:
            try:
                logging.info("Database log message")
                self.conn.execute("SELECT 1")
                logging.info(f"鏁版嵁搴撹繛鎺?- 鐜版湁杩炴帴鏈夋晥")
                return self.conn
            except Exception as e:
                logging.warning("Database log message")
                try:
                    self.conn.close()
                    logging.info("Database log message")
                except Exception as close_error:
                    logging.warning(f"鏁版嵁搴撹繛鎺?- 鍏抽棴杩炴帴鏃跺嚭閿? {str(close_error)}")
                self.conn = None
        
        if self.conn is None:
            logging.info(f"鏁版嵁搴撹繛鎺?- 鍒涘缓鏂拌繛鎺? 鏁版嵁搴撹矾寰? {self.db_path}")
            self.conn = sqlite3.connect(self.db_path, timeout=30.0)
            self.conn.row_factory = sqlite3.Row
            logging.info(f"鏁版嵁搴撹繛鎺?- 鏂拌繛鎺ュ垱寤烘垚鍔? 杩炴帴瀵硅薄: {self.conn}")
        
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
                国家药品代码 TEXT,
                甲乙类 TEXT,
                药品名称 TEXT,
                英文名称 TEXT,
                剂型 TEXT,
                规格 TEXT,
                包装规格 TEXT,
                计价单位 TEXT,
                计价规格 TEXT,
                最小包装单位 TEXT,
                最小包装数量 TEXT,
                转换比 TEXT,
                企业名称 TEXT,
                质量层次 TEXT,
                备注 TEXT,
                限制使用范围 TEXT,
                医保基础价格 TEXT,
                医保支付标准 TEXT,
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
                国家药品代码 TEXT,
                甲乙类 TEXT,
                药品名称 TEXT,
                英文名称 TEXT,
                剂型 TEXT,
                规格 TEXT,
                包装规格 TEXT,
                计价单位 TEXT,
                计价规格 TEXT,
                最小包装单位 TEXT,
                最小包装数量 TEXT,
                转换比 TEXT,
                企业名称 TEXT,
                质量层次 TEXT,
                备注 TEXT,
                限制使用范围 TEXT,
                医保基础价格 TEXT,
                医保支付标准 TEXT,
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
                医保编码 TEXT,
                药品名称 TEXT,
                剂型 TEXT,
                规格 TEXT,
                包装规格 TEXT,
                计价单位 TEXT,
                企业名称 TEXT,
                医保价格上限 TEXT,
                价格生效日期 TEXT,
                备注 TEXT,
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
                价格类型 TEXT,
                价格更新时间 TEXT,
                抓取状态 TEXT DEFAULT 'success',
                原始数据 TEXT,
                created_at TEXT NOT NULL
            )
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
                国家药品代码 TEXT,
                商品编码 TEXT,
                旧商品编码 TEXT,
                商品名称 TEXT,
                规格 TEXT,
                生产厂家 TEXT,
                医保基础价格 TEXT,
                医保价格上限 TEXT,
                君元销售价 TEXT,
                君元包装价 TEXT,
                君元单片价 TEXT,
                异常等级 TEXT,
                超基础金额 TEXT,
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
        
        self._create_default_admin_if_not_exists()
        self._init_app_settings()
        self._init_default_roles_and_permissions()
        
        logging.info("鏁版嵁搴撳垵濮嬪寲瀹屾垚")
    
    def _migrate_add_raw_data_columns(self):
        conn = self.get_connection()
        cursor = conn.cursor()
        
        try:
            cursor.execute("PRAGMA table_info(ysb_detail_data)")
            columns = [row['name'] for row in cursor.fetchall()]
            
            if 'raw_data' not in columns:
                cursor.execute("ALTER TABLE ysb_detail_data ADD COLUMN raw_data TEXT")
                logging.info("鉁?涓?ysb_detail_data 琛ㄦ坊鍔?raw_data 瀛楁")
            
            conn.commit()
        except Exception as e:
            logging.warning(f"Failed to migrate raw_data column: {e}")
            conn.rollback()

    def _migrate_add_role_code_column(self):
        """涓簎sers琛ㄦ坊鍔爎ole_code瀛楁"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        try:
            cursor.execute("PRAGMA table_info(users)")
            columns = [row['name'] for row in cursor.fetchall()]
            
            if 'role_code' not in columns:
                cursor.execute("ALTER TABLE users ADD COLUMN role_code TEXT")
                logging.info("鉁?涓?users 琛ㄦ坊鍔?role_code 瀛楁")
                
                # 灏嗙幇鏈夌敤鎴风殑role瀛楁鍊艰縼绉诲埌role_code瀛楁
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
            logging.warning(f"杩佺移role_code字段时出错: {e}")
    
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
            'operation.config.save_supplier_scope',
        ]
        
        for permission_code in store_manager_permissions:
            cursor.execute('''
                INSERT OR IGNORE INTO role_permissions (role_code, permission_code, created_at)
                VALUES (?, ?, ?)
            ''', ('store_manager', permission_code, now))
        
        conn.commit()
        logging.info("Database log message")
    
    def _migrate_add_raw_data_columns_full(self):
        """Migrate raw_data related columns."""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        try:
            cursor.execute("PRAGMA table_info(ysb_detail_data)")
            columns = [row['name'] for row in cursor.fetchall()]
            
            if 'raw_data' not in columns:
                cursor.execute("ALTER TABLE ysb_detail_data ADD COLUMN raw_data TEXT")
                logging.info("鉁?涓?ysb_detail_data 琛ㄦ坊鍔?raw_data 瀛楁")
            
            cursor.execute("PRAGMA table_info(ysb_supplier_summary)")
            columns = [row['name'] for row in cursor.fetchall()]
            
            if 'raw_data' not in columns:
                cursor.execute("ALTER TABLE ysb_supplier_summary ADD COLUMN raw_data TEXT")
                logging.info("鉁?涓?ysb_supplier_summary 琛ㄦ坊鍔?raw_data 瀛楁")
            
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
                    logging.info(f"鉁?涓?reconciliation_tasks 琛ㄦ坊鍔?{field_name} 瀛楁")
            
            cursor.execute("PRAGMA table_info(ysb_import_batches)")
            columns = [row['name'] for row in cursor.fetchall()]
            
            ysb_batch_fields = [
                ('account_year', 'INTEGER'),
                ('account_month', 'INTEGER'),
            ]
            
            for field_name, field_type in ysb_batch_fields:
                if field_name not in columns:
                    cursor.execute(f"ALTER TABLE ysb_import_batches ADD COLUMN {field_name} {field_type}")
                    logging.info(f"鉁?涓?ysb_import_batches 琛ㄦ坊鍔?{field_name} 瀛楁")
            
            cursor.execute("PRAGMA table_info(yys_import_detail)")
            columns = [row['name'] for row in cursor.fetchall()]
            
            yys_detail_fields = [
                ('warehouse', 'TEXT'),
                ('productno', 'TEXT'),
            ]
            
            for field_name, field_type in yys_detail_fields:
                if field_name not in columns:
                    cursor.execute(f"ALTER TABLE yys_import_detail ADD COLUMN {field_name} {field_type}")
                    logging.info(f"鉁?涓?yys_import_detail 琛ㄦ坊鍔?{field_name} 瀛楁")
            
            # 涓?jy_stock_query 琛ㄦ坊鍔犲瓧娈?            cursor.execute("PRAGMA table_info(jy_stock_query)")
            jy_columns = [row['name'] for row in cursor.fetchall()]
            
            jy_fields = [
                ('specification', 'TEXT'),
                ('approval_number', 'TEXT'),
            ]
            
            for field_name, field_type in jy_fields:
                if field_name not in jy_columns:
                    cursor.execute(f"ALTER TABLE jy_stock_query ADD COLUMN {field_name} {field_type}")
                    logging.info(f"鉁?涓?jy_stock_query 琛ㄦ坊鍔?{field_name} 瀛楁")
            
            conn.commit()
        except Exception as e:
            logging.warning(f"鏁版嵁搴撹縼绉诲け璐ワ紙瀛楁鍙兘宸插瓨鍦級: {e}")
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
