"""
第四阶段：数据权限扩展 测试脚本

测试内容：
1. 数据范围字段添加
2. 数据过滤逻辑 - 店长只能查看自己创建的数据，管理员可以查看所有数据
3. 数据创建人正确记录
"""
import pytest
from datetime import datetime
import uuid
from pathlib import Path

from app.storage.database import Database
from app.core.data_permission_service import DataPermissionService
from app.core.auth_service import AuthService
from app.core.password_service import PasswordService


@pytest.fixture
def db():
    """创建测试数据库"""
    test_db_path = Path("test_phase4.db")
    if test_db_path.exists():
        test_db_path.unlink()
    
    database = Database(test_db_path)
    database.initialize()
    
    yield database
    
    # 清理
    database.close()
    if test_db_path.exists():
        test_db_path.unlink()


@pytest.fixture
def data_permission_service(db):
    """创建数据权限服务"""
    return DataPermissionService(db)


@pytest.fixture
def auth_service(db):
    """创建认证服务"""
    return AuthService(db)


class TestDataPermissionService:
    """测试数据权限服务"""
    
    def test_is_system_admin(self, data_permission_service):
        """测试系统管理员判断"""
        # 系统管理员
        assert data_permission_service.is_system_admin('system_admin') == True
        
        # 店长
        assert data_permission_service.is_system_admin('store_manager') == False
        
        # 其他角色
        assert data_permission_service.is_system_admin('other_role') == False
    
    def test_get_data_filter_condition_system_admin(self, data_permission_service):
        """测试系统管理员数据过滤条件"""
        result = data_permission_service.get_data_filter_condition(
            'yys_import_batch', 'system_admin', 'admin'
        )
        
        # 系统管理员不需要过滤
        assert result['needs_filter'] == False
        assert result['filter_sql'] == ''
        assert result['filter_params'] == []
    
    def test_get_data_filter_condition_store_manager(self, data_permission_service):
        """测试店长数据过滤条件"""
        result = data_permission_service.get_data_filter_condition(
            'yys_import_batch', 'store_manager', 'store_user1'
        )
        
        # 店长需要过滤
        assert result['needs_filter'] == True
        assert result['filter_sql'] == 'imported_by = ?'
        assert result['filter_params'] == ['store_user1']
    
    def test_get_data_filter_condition_unknown_table(self, data_permission_service):
        """测试未知表的数据过滤条件"""
        result = data_permission_service.get_data_filter_condition(
            'unknown_table', 'store_manager', 'store_user1'
        )
        
        # 未知表不需要过滤
        assert result['needs_filter'] == False
    
    def test_apply_data_filter_to_query(self, data_permission_service):
        """测试将数据过滤条件应用到查询"""
        base_query = "SELECT * FROM yys_import_batch"
        
        # 系统管理员
        modified_query, params = data_permission_service.apply_data_filter_to_query(
            base_query, 'yys_import_batch', 'system_admin', 'admin'
        )
        assert modified_query == base_query
        assert params == []
        
        # 店长
        modified_query, params = data_permission_service.apply_data_filter_to_query(
            base_query, 'yys_import_batch', 'store_manager', 'store_user1'
        )
        assert modified_query == "SELECT * FROM yys_import_batch WHERE imported_by = ?"
        assert params == ['store_user1']
        
        # 已有WHERE条件
        base_query_with_where = "SELECT * FROM yys_import_batch WHERE status = 'success'"
        modified_query, params = data_permission_service.apply_data_filter_to_query(
            base_query_with_where, 'yys_import_batch', 'store_manager', 'store_user1',
            existing_where=True
        )
        assert modified_query == "SELECT * FROM yys_import_batch WHERE status = 'success' AND imported_by = ?"
        assert params == ['store_user1']


class TestDataScopeFields:
    """测试数据范围字段"""
    
    def test_reconciliation_tasks_has_created_by(self, db):
        """测试对账任务表有created_by字段"""
        conn = db.get_connection()
        cursor = conn.cursor()
        
        cursor.execute("PRAGMA table_info(reconciliation_tasks)")
        columns = [row['name'] for row in cursor.fetchall()]
        
        assert 'created_by' in columns
    
    def test_stock_compare_result_has_created_by(self, db):
        """测试库存比对结果表有created_by字段"""
        conn = db.get_connection()
        cursor = conn.cursor()
        
        cursor.execute("PRAGMA table_info(stock_compare_result)")
        columns = [row['name'] for row in cursor.fetchall()]
        
        assert 'created_by' in columns
    
    def test_yys_sync_task_has_created_by(self, db):
        """测试YYS同步任务表有created_by字段"""
        conn = db.get_connection()
        cursor = conn.cursor()
        
        cursor.execute("PRAGMA table_info(yys_sync_task)")
        columns = [row['name'] for row in cursor.fetchall()]
        
        assert 'created_by' in columns
    
    def test_yys_import_batch_has_imported_by(self, db):
        """测试YYS导入批次表有imported_by字段"""
        conn = db.get_connection()
        cursor = conn.cursor()
        
        cursor.execute("PRAGMA table_info(yys_import_batch)")
        columns = [row['name'] for row in cursor.fetchall()]
        
        assert 'imported_by' in columns
    
    def test_rpa_import_batches_has_imported_by(self, db):
        """测试RPA导入批次表有imported_by字段"""
        conn = db.get_connection()
        cursor = conn.cursor()
        
        cursor.execute("PRAGMA table_info(rpa_import_batches)")
        columns = [row['name'] for row in cursor.fetchall()]
        
        assert 'imported_by' in columns
    
    def test_rpa_tasks_has_created_by(self, db):
        """测试RPA任务表有created_by字段"""
        conn = db.get_connection()
        cursor = conn.cursor()
        
        cursor.execute("PRAGMA table_info(rpa_tasks)")
        columns = [row['name'] for row in cursor.fetchall()]
        
        assert 'created_by' in columns


class TestDataFiltering:
    """测试数据过滤功能"""
    
    def test_yys_import_batch_filtering(self, db, data_permission_service):
        """测试YYS导入批次数据过滤"""
        conn = db.get_connection()
        cursor = conn.cursor()
        
        # 创建测试数据 - 两个不同用户创建的批次
        now = datetime.now().isoformat()
        
        batch_id_1 = f"YYS{datetime.now().strftime('%Y%m%d%H%M%S')}{uuid.uuid4().hex[:4]}"
        cursor.execute('''
            INSERT INTO yys_import_batch
            (batch_id, batch_name, source_file, sheet_name, total_count, valid_count, invalid_count, status, imported_by, imported_at, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (batch_id_1, 'Batch1', 'file1.xlsx', 'Sheet1', 10, 8, 2, 'success', 'store_user1', now, now))
        
        batch_id_2 = f"YYS{datetime.now().strftime('%Y%m%d%H%M%S')}{uuid.uuid4().hex[:4]}"
        cursor.execute('''
            INSERT INTO yys_import_batch
            (batch_id, batch_name, source_file, sheet_name, total_count, valid_count, invalid_count, status, imported_by, imported_at, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (batch_id_2, 'Batch2', 'file2.xlsx', 'Sheet1', 20, 15, 5, 'success', 'store_user2', now, now))
        
        conn.commit()
        
        # 系统管理员应该能看到所有批次
        batches_admin = data_permission_service.get_filtered_batches(
            'yys_import_batch', 'system_admin', 'admin'
        )
        assert len(batches_admin) == 2
        
        # 店长store_user1应该只能看到自己创建的批次
        batches_user1 = data_permission_service.get_filtered_batches(
            'yys_import_batch', 'store_manager', 'store_user1'
        )
        assert len(batches_user1) == 1
        assert batches_user1[0]['imported_by'] == 'store_user1'
        
        # 店长store_user2应该只能看到自己创建的批次
        batches_user2 = data_permission_service.get_filtered_batches(
            'yys_import_batch', 'store_manager', 'store_user2'
        )
        assert len(batches_user2) == 1
        assert batches_user2[0]['imported_by'] == 'store_user2'
    
    def test_rpa_import_batches_filtering(self, db, data_permission_service):
        """测试RPA导入批次数据过滤"""
        conn = db.get_connection()
        cursor = conn.cursor()
        
        # 创建测试数据
        now = datetime.now().isoformat()
        
        import_batch_id_1 = f"RPA{datetime.now().strftime('%Y%m%d%H%M%S')}{uuid.uuid4().hex[:4]}"
        cursor.execute('''
            INSERT INTO rpa_import_batches
            (import_batch_id, import_name, template_id, source_file, sheet_name, total_count, valid_count, invalid_count, duplicate_count, status, imported_by, imported_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (import_batch_id_1, 'Import1', None, 'file1.xlsx', 'Sheet1', 10, 10, 0, 0, 'ready', 'store_user1', now))
        
        import_batch_id_2 = f"RPA{datetime.now().strftime('%Y%m%d%H%M%S')}{uuid.uuid4().hex[:4]}"
        cursor.execute('''
            INSERT INTO rpa_import_batches
            (import_batch_id, import_name, template_id, source_file, sheet_name, total_count, valid_count, invalid_count, duplicate_count, status, imported_by, imported_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (import_batch_id_2, 'Import2', None, 'file2.xlsx', 'Sheet1', 20, 20, 0, 0, 'ready', 'store_user2', now))
        
        conn.commit()
        
        # 系统管理员应该能看到所有批次
        batches_admin = data_permission_service.get_filtered_batches(
            'rpa_import_batches', 'system_admin', 'admin'
        )
        assert len(batches_admin) == 2
        
        # 店长store_user1应该只能看到自己创建的批次
        batches_user1 = data_permission_service.get_filtered_batches(
            'rpa_import_batches', 'store_manager', 'store_user1'
        )
        assert len(batches_user1) == 1
        assert batches_user1[0]['imported_by'] == 'store_user1'
    
    def test_reconciliation_tasks_filtering(self, db, data_permission_service):
        """测试对账任务数据过滤"""
        conn = db.get_connection()
        cursor = conn.cursor()
        
        # 创建测试数据
        now = datetime.now().isoformat()
        
        task_id_1 = f"TASK{datetime.now().strftime('%Y%m%d%H%M%S')}{uuid.uuid4().hex[:4]}"
        cursor.execute('''
            INSERT INTO reconciliation_tasks
            (task_id, task_type, status, created_by, created_at)
            VALUES (?, ?, ?, ?, ?)
        ''', (task_id_1, 'all', 'completed', 'store_user1', now))
        
        task_id_2 = f"TASK{datetime.now().strftime('%Y%m%d%H%M%S')}{uuid.uuid4().hex[:4]}"
        cursor.execute('''
            INSERT INTO reconciliation_tasks
            (task_id, task_type, status, created_by, created_at)
            VALUES (?, ?, ?, ?, ?)
        ''', (task_id_2, 'all', 'completed', 'store_user2', now))
        
        conn.commit()
        
        # 系统管理员应该能看到所有任务
        tasks_admin = data_permission_service.get_filtered_batches(
            'reconciliation_tasks', 'system_admin', 'admin'
        )
        assert len(tasks_admin) == 2
        
        # 店长store_user1应该只能看到自己创建的任务
        tasks_user1 = data_permission_service.get_filtered_batches(
            'reconciliation_tasks', 'store_manager', 'store_user1'
        )
        assert len(tasks_user1) == 1
        assert tasks_user1[0]['created_by'] == 'store_user1'
    
    def test_can_access_batch(self, db, data_permission_service):
        """测试批次访问权限检查"""
        conn = db.get_connection()
        cursor = conn.cursor()
        
        # 创建测试数据
        now = datetime.now().isoformat()
        batch_id = f"YYS{datetime.now().strftime('%Y%m%d%H%M%S')}{uuid.uuid4().hex[:4]}"
        
        cursor.execute('''
            INSERT INTO yys_import_batch
            (batch_id, batch_name, source_file, sheet_name, total_count, valid_count, invalid_count, status, imported_by, imported_at, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (batch_id, 'TestBatch', 'test.xlsx', 'Sheet1', 10, 10, 0, 'success', 'store_user1', now, now))
        
        conn.commit()
        
        # 系统管理员可以访问所有批次
        assert data_permission_service.can_access_batch(
            'yys_import_batch', batch_id, 'system_admin', 'admin'
        ) == True
        
        # 创建者可以访问自己的批次
        assert data_permission_service.can_access_batch(
            'yys_import_batch', batch_id, 'store_manager', 'store_user1'
        ) == True
        
        # 其他用户不能访问
        assert data_permission_service.can_access_batch(
            'yys_import_batch', batch_id, 'store_manager', 'store_user2'
        ) == False
    
    def test_set_batch_creator(self, db, data_permission_service):
        """测试设置批次创建人"""
        conn = db.get_connection()
        cursor = conn.cursor()
        
        # 创建测试数据（没有创建人）
        now = datetime.now().isoformat()
        batch_id = f"YYS{datetime.now().strftime('%Y%m%d%H%M%S')}{uuid.uuid4().hex[:4]}"
        
        cursor.execute('''
            INSERT INTO yys_import_batch
            (batch_id, batch_name, source_file, sheet_name, total_count, valid_count, invalid_count, status, imported_by, imported_at, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (batch_id, 'TestBatch', 'test.xlsx', 'Sheet1', 10, 10, 0, 'success', None, now, now))
        
        conn.commit()
        
        # 设置创建人
        result = data_permission_service.set_batch_creator(
            'yys_import_batch', batch_id, 'new_user'
        )
        assert result == True
        
        # 验证创建人已更新
        cursor.execute(
            "SELECT imported_by FROM yys_import_batch WHERE batch_id = ?",
            (batch_id,)
        )
        row = cursor.fetchone()
        assert row['imported_by'] == 'new_user'


class TestBatchCount:
    """测试批次计数功能"""
    
    def test_get_batch_count(self, db, data_permission_service):
        """测试获取过滤后的批次数量"""
        conn = db.get_connection()
        cursor = conn.cursor()
        
        # 创建测试数据
        now = datetime.now().isoformat()
        
        for i in range(5):
            batch_id = f"YYS{datetime.now().strftime('%Y%m%d%H%M%S')}{uuid.uuid4().hex[:4]}"
            cursor.execute('''
                INSERT INTO yys_import_batch
                (batch_id, batch_name, source_file, sheet_name, total_count, valid_count, invalid_count, status, imported_by, imported_at, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (batch_id, f'Batch{i}', f'file{i}.xlsx', 'Sheet1', 10, 10, 0, 'success', 'store_user1', now, now))
        
        for i in range(3):
            batch_id = f"YYS{datetime.now().strftime('%Y%m%d%H%M%S')}{uuid.uuid4().hex[:4]}"
            cursor.execute('''
                INSERT INTO yys_import_batch
                (batch_id, batch_name, source_file, sheet_name, total_count, valid_count, invalid_count, status, imported_by, imported_at, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (batch_id, f'Batch{i}', f'file{i}.xlsx', 'Sheet1', 10, 10, 0, 'success', 'store_user2', now, now))
        
        conn.commit()
        
        # 系统管理员应该能看到8个批次
        count_admin = data_permission_service.get_batch_count(
            'yys_import_batch', 'system_admin', 'admin'
        )
        assert count_admin == 8
        
        # 店长store_user1应该能看到5个批次
        count_user1 = data_permission_service.get_batch_count(
            'yys_import_batch', 'store_manager', 'store_user1'
        )
        assert count_user1 == 5
        
        # 店长store_user2应该能看到3个批次
        count_user2 = data_permission_service.get_batch_count(
            'yys_import_batch', 'store_manager', 'store_user2'
        )
        assert count_user2 == 3


def test_phase4_summary():
    """第四阶段测试总结"""
    print("\n" + "="*60)
    print("第四阶段：数据权限扩展 测试总结")
    print("="*60)
    print("\n已实现功能:")
    print("1. 数据范围字段添加:")
    print("   - reconciliation_tasks: created_by")
    print("   - stock_compare_result: created_by")
    print("   - yys_sync_task: created_by")
    print("   - yys_import_batch: imported_by (已有)")
    print("   - rpa_import_batches: imported_by (已有)")
    print("   - rpa_tasks: created_by (已有)")
    print("\n2. 数据过滤逻辑:")
    print("   - 系统管理员可以查看所有数据")
    print("   - 店长只能查看自己创建的数据")
    print("   - 数据创建人正确记录")
    print("\n3. 数据权限服务功能:")
    print("   - is_system_admin: 判断是否为系统管理员")
    print("   - get_data_filter_condition: 获取数据过滤条件")
    print("   - apply_data_filter_to_query: 将过滤条件应用到查询")
    print("   - get_filtered_batches: 获取过滤后的批次数据")
    print("   - get_batch_count: 获取过滤后的批次数量")
    print("   - can_access_batch: 检查用户是否可以访问特定批次")
    print("   - set_batch_creator: 设置批次的创建人")
    print("\n4. 页面集成:")
    print("   - TaskRecordPage: 对账任务记录页面")
    print("   - YysStockQueryPage: YYS库存查询页面")
    print("   - StockComparePage: 库存比对页面")
    print("   - ReconciliationPage: 对账页面")
    print("   - SmartPurchasePage: 智能采购页面")
    print("   - RpaRobotPage: RPA机器人页面")
    print("="*60)


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])