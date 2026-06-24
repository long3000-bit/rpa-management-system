"""
逐个采购-建立评分规则表方案级自动化测试
根据第六轮后整改方案要求，新增方案级pytest测试
"""
import pytest
import tempfile
import json
from datetime import datetime
from pathlib import Path

from app.storage.database import Database
from app.core.smart_purchase_service import SmartPurchaseService


class TestSmartPurchaseSchema:
    """测试smart_*表结构和默认规则集初始化"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """每个测试前创建临时数据库"""
        self.temp_dir = tempfile.mkdtemp()
        self.db_path = Path(self.temp_dir) / "test_smart_purchase.db"
        self.db = Database(str(self.db_path))
        self.db.initialize()  # 初始化数据库，创建所有表
        self.service = SmartPurchaseService(self.db)
        
    def teardown(self):
        """每个测试后清理临时数据库"""
        try:
            if hasattr(self, 'db'):
                self.db.close()
        except:
            pass
    
    def test_smart_tables_exist(self):
        """测试1：数据库初始化后 smart_* 表全部存在"""
        conn = self.db.get_connection()
        cursor = conn.cursor()
        
        # 检查所有smart_*表是否存在
        smart_tables = [
            'smart_match_rule_sets',
            'smart_match_rule_configs',
            'smart_spec_unit_aliases',
            'smart_spec_parse_rules',
            'smart_match_thresholds',
            'smart_name_aliases',
            'smart_purchase_candidates',
            'smart_cart_snapshots',
            'smart_cart_snapshot_items',
            'smart_cart_backfill_matches',
        ]
        
        for table in smart_tables:
            cursor.execute(f"SELECT name FROM sqlite_master WHERE type='table' AND name='{table}'")
            result = cursor.fetchone()
            assert result is not None, f"表 {table} 应该存在"
    
    def test_default_rule_sets_initialized(self):
        """测试2：default_v1 / strict_spec_v1 自动初始化"""
        conn = self.db.get_connection()
        cursor = conn.cursor()
        
        # 检查default_v1规则集是否存在且is_default=1
        cursor.execute("SELECT COUNT(*) FROM smart_match_rule_sets WHERE rule_set_code='default_v1' AND is_default=1")
        default_v1_count = cursor.fetchone()[0]
        assert default_v1_count == 1, "default_v1规则集应该存在且is_default=1"
        
        # 检查strict_spec_v1规则集是否存在
        cursor.execute("SELECT COUNT(*) FROM smart_match_rule_sets WHERE rule_set_code='strict_spec_v1'")
        strict_spec_v1_count = cursor.fetchone()[0]
        assert strict_spec_v1_count == 1, "strict_spec_v1规则集应该存在"
        
        # 检查规则配置数量
        cursor.execute("SELECT COUNT(*) FROM smart_match_rule_configs")
        rule_config_count = cursor.fetchone()[0]
        assert rule_config_count >= 14, "规则配置数量应该至少14条"


class TestCandidateScores:
    """测试候选评分落库"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """每个测试前创建临时数据库"""
        self.temp_dir = tempfile.mkdtemp()
        self.db_path = Path(self.temp_dir) / "test_candidate_scores.db"
        self.db = Database(str(self.db_path))
        self.db.initialize()  # 初始化数据库，创建所有表
        self.service = SmartPurchaseService(self.db)
        
    def teardown(self):
        """每个测试后清理临时数据库"""
        try:
            if hasattr(self, 'db'):
                self.db.close()
        except:
            pass
    
    def test_candidate_scores_insert_no_field_error(self):
        """测试6：smart_purchase_candidates INSERT 不出现字段数错误"""
        conn = self.db.get_connection()
        cursor = conn.cursor()
        
        # 模拟候选数据
        candidate_data = {
            "name": "测试商品",
            "spec": "10mg*10片",
            "manufacturer": "测试厂家",
            "supplier": "测试供应商",
            "supplierFull": "测试供应商全称",
            "price": "10.5",
            "minAmount": "10",
            "stock": "100",
            "score": 85,
            "detail": {
                "nameScore": 90,
                "specScore": 80,
                "makerScore": 75,
            },
            "specOk": True,
            "manufacturerOk": True,
            "supplierOk": True,
            "priceOk": True,
            "qtyOk": True,
            "stockOk": True,
            "isSelected": True,
            "reason": "",
        }
        
        # 模拟采购商品数据
        item = {
            "itemId": "test_item_001",
        }
        
        # 模拟适配器商品数据
        adapter_item = {
            "name": "测试商品",
            "max_allowed_price": "12.0",
        }
        
        # 调用_save_single_candidate_score函数
        try:
            self.service._save_single_candidate_score(
                cursor,
                "test_batch_001",
                item,
                candidate_data,
                adapter_item,
                "success",
                1,
                True
            )
            conn.commit()
            
            # 检查purchase_candidate_scores表是否有数据
            cursor.execute("SELECT COUNT(*) FROM purchase_candidate_scores")
            purchase_count = cursor.fetchone()[0]
            assert purchase_count == 1, "purchase_candidate_scores表应该有1条数据"
            
            # 检查smart_purchase_candidates表是否有数据
            cursor.execute("SELECT COUNT(*) FROM smart_purchase_candidates")
            smart_count = cursor.fetchone()[0]
            assert smart_count == 1, "smart_purchase_candidates表应该有1条数据"
            
        except Exception as e:
            pytest.fail(f"INSERT操作失败: {e}")
    
    def test_selected_candidate_accuracy(self):
        """测试4：isSelected=true 的候选准确 selected=1/final_pass=1"""
        conn = self.db.get_connection()
        cursor = conn.cursor()
        
        # 模拟候选数据（isSelected=true）
        candidate_data_selected = {
            "name": "选中商品",
            "spec": "10mg*10片",
            "manufacturer": "测试厂家",
            "supplier": "测试供应商",
            "price": "10.5",
            "score": 85,
            "detail": {},
            "isSelected": True,
        }
        
        # 模拟候选数据（isSelected=false）
        candidate_data_not_selected = {
            "name": "未选中商品",
            "spec": "10mg*20片",
            "manufacturer": "测试厂家",
            "supplier": "测试供应商",
            "price": "15.5",
            "score": 75,
            "detail": {},
            "isSelected": False,
        }
        
        item = {"itemId": "test_item_002"}
        adapter_item = {"name": "测试商品"}
        
        # 保存选中候选
        self.service._save_single_candidate_score(
            cursor, "test_batch_002", item, candidate_data_selected, adapter_item, "success", 1, True
        )
        
        # 保存未选中候选
        self.service._save_single_candidate_score(
            cursor, "test_batch_002", item, candidate_data_not_selected, adapter_item, "success", 2, False
        )
        
        conn.commit()
        
        # 检查选中候选的selected和final_pass
        cursor.execute("SELECT selected, final_pass FROM purchase_candidate_scores WHERE candidate_rank=1")
        selected_result = cursor.fetchone()
        assert selected_result[0] == 1, "选中候选的selected应该为1"
        assert selected_result[1] == 1, "选中候选的final_pass应该为1"
        
        # 检查未选中候选的selected和final_pass
        cursor.execute("SELECT selected, final_pass FROM purchase_candidate_scores WHERE candidate_rank=2")
        not_selected_result = cursor.fetchone()
        assert not_selected_result[0] == 0, "未选中候选的selected应该为0"
        assert not_selected_result[1] == 0, "未选中候选的final_pass应该为0"
    
    def test_reject_reason_can_save(self):
        """测试10：reject_reason 可落库并可查询"""
        conn = self.db.get_connection()
        cursor = conn.cursor()
        
        # 模拟候选数据（有reject_reason）
        candidate_data = {
            "name": "拒绝商品",
            "spec": "10mg*10片",
            "manufacturer": "测试厂家",
            "supplier": "测试供应商",
            "price": "20.5",
            "score": 65,
            "detail": {},
            "isSelected": False,
            "reason": "价格超过最高允许价",
        }
        
        item = {"itemId": "test_item_003"}
        adapter_item = {"name": "测试商品"}
        
        # 保存候选
        self.service._save_single_candidate_score(
            cursor, "test_batch_003", item, candidate_data, adapter_item, "failed", 1, False
        )
        
        conn.commit()
        
        # 检查reject_reason是否正确保存
        cursor.execute("SELECT reject_reason FROM purchase_candidate_scores WHERE candidate_rank=1")
        reject_reason_result = cursor.fetchone()
        assert reject_reason_result[0] == "价格超过最高允许价", "reject_reason应该正确保存"


class TestCartSnapshot:
    """测试购物车快照落库"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """每个测试前创建临时数据库"""
        self.temp_dir = tempfile.mkdtemp()
        self.db_path = Path(self.temp_dir) / "test_cart_snapshot.db"
        self.db = Database(str(self.db_path))
        self.db.initialize()  # 初始化数据库，创建所有表
        self.service = SmartPurchaseService(self.db)
        
    def teardown(self):
        """每个测试后清理临时数据库"""
        try:
            if hasattr(self, 'db'):
                self.db.close()
        except:
            pass
    
    def test_empty_cart_snapshot(self):
        """测试7：购物车快照空车也落库"""
        conn = self.db.get_connection()
        cursor = conn.cursor()
        
        # 模拟空购物车
        cart_items = []
        
        # 调用_save_cart_snapshot函数
        self.service._save_cart_snapshot("test_batch_004", cart_items)
        
        # 检查smart_cart_snapshots表是否有数据
        cursor.execute("SELECT COUNT(*) FROM smart_cart_snapshots")
        snapshot_count = cursor.fetchone()[0]
        assert snapshot_count == 1, "smart_cart_snapshots表应该有1条数据（空车快照）"
        
        # 检查快照状态是否为empty
        cursor.execute("SELECT snapshot_status, total_items FROM smart_cart_snapshots")
        snapshot_result = cursor.fetchone()
        assert snapshot_result[0] == "empty", "空车快照状态应该为empty"
        assert snapshot_result[1] == 0, "空车快照total_items应该为0"
        
        # 检查smart_cart_snapshot_items表是否没有数据
        cursor.execute("SELECT COUNT(*) FROM smart_cart_snapshot_items")
        items_count = cursor.fetchone()[0]
        assert items_count == 0, "空车快照应该没有明细数据"
    
    def test_cart_snapshot_with_items(self):
        """测试8：购物车快照有商品时明细数量正确"""
        conn = self.db.get_connection()
        cursor = conn.cursor()
        
        # 模拟购物车商品（3个商品）
        cart_items = [
            {"name": "商品1", "spec": "10mg*10片", "manufacturer": "厂家1", "supplier": "供应商1", "price": "10.5", "quantity": "10", "stock": "100"},
            {"name": "商品2", "spec": "20mg*20片", "manufacturer": "厂家2", "supplier": "供应商2", "price": "20.5", "quantity": "20", "stock": "200"},
            {"name": "商品3", "spec": "30mg*30片", "manufacturer": "厂家3", "supplier": "供应商3", "price": "30.5", "quantity": "30", "stock": "300"},
        ]
        
        # 调用_save_cart_snapshot函数
        self.service._save_cart_snapshot("test_batch_005", cart_items)
        
        # 检查smart_cart_snapshots表是否有数据
        cursor.execute("SELECT COUNT(*) FROM smart_cart_snapshots")
        snapshot_count = cursor.fetchone()[0]
        assert snapshot_count == 1, "smart_cart_snapshots表应该有1条数据"
        
        # 检查快照状态是否为completed
        cursor.execute("SELECT snapshot_status, total_items FROM smart_cart_snapshots")
        snapshot_result = cursor.fetchone()
        assert snapshot_result[0] == "completed", "有商品快照状态应该为completed"
        assert snapshot_result[1] == 3, "有商品快照total_items应该为3"
        
        # 检查smart_cart_snapshot_items表是否有3条数据
        cursor.execute("SELECT COUNT(*) FROM smart_cart_snapshot_items")
        items_count = cursor.fetchone()[0]
        assert items_count == 3, "smart_cart_snapshot_items表应该有3条数据"


class TestCartBackfillMatch:
    """测试购物车反写匹配落库"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """每个测试前创建临时数据库"""
        self.temp_dir = tempfile.mkdtemp()
        self.db_path = Path(self.temp_dir) / "test_cart_backfill.db"
        self.db = Database(str(self.db_path))
        self.db.initialize()  # 初始化数据库，创建所有表
        self.service = SmartPurchaseService(self.db)
        
    def teardown(self):
        """每个测试后清理临时数据库"""
        try:
            if hasattr(self, 'db'):
                self.db.close()
        except:
            pass
    
    def test_cart_backfill_match_can_save(self):
        """测试9：购物车反写匹配过程可落库"""
        conn = self.db.get_connection()
        cursor = conn.cursor()
        
        # 模拟匹配数据
        match_status = "matched"
        match_type = "wholesaleId"
        match_score = 100
        match_detail = {
            "score": 100,
            "reason": "wholesaleId",
            "adapter_item": {"name": "测试商品"},
            "cart_item": {"name": "测试商品", "wholesaleId": "12345"},
        }
        
        # 使用统一的 snapshot_batch_id
        snapshot_batch_id = "snapshot_test_batch_006_20260618120000"
        
        # 调用_save_cart_backfill_match函数
        self.service._save_cart_backfill_match(
            "test_batch_006",
            "test_detail_001",
            match_status,
            match_type,
            match_score,
            match_detail,
            snapshot_batch_id
        )
        
        # 检查smart_cart_backfill_matches表是否有数据
        cursor.execute("SELECT COUNT(*) FROM smart_cart_backfill_matches")
        match_count = cursor.fetchone()[0]
        assert match_count == 1, "smart_cart_backfill_matches表应该有1条数据"
        
        # 检查匹配状态和匹配方式
        cursor.execute("SELECT match_status, match_type, match_score, snapshot_batch_id FROM smart_cart_backfill_matches")
        match_result = cursor.fetchone()
        assert match_result[0] == "matched", "匹配状态应该为matched"
        assert match_result[1] == "wholesaleId", "匹配方式应该为wholesaleId"
        assert match_result[2] == 100, "匹配分数应该为100"
        assert match_result[3] == snapshot_batch_id, "snapshot_batch_id应该正确保存"
    
    def test_cart_snapshot_and_backfill_match_association(self):
        """测试11：购物车快照与反写匹配的 snapshot_batch_id 可关联"""
        conn = self.db.get_connection()
        cursor = conn.cursor()
        
        # 使用统一的 snapshot_batch_id
        snapshot_batch_id = "snapshot_test_batch_007_20260618120000"
        
        # 保存购物车快照
        cart_items = [
            {"name": "商品1", "spec": "10mg*10片", "manufacturer": "厂家1", "supplier": "供应商1", "price": "10.5", "quantity": "10", "stock": "100"},
        ]
        self.service._save_cart_snapshot("test_batch_007", cart_items, snapshot_batch_id)
        
        # 保存购物车反写匹配
        match_status = "matched"
        match_type = "wholesaleId"
        match_score = 100
        match_detail = {
            "score": 100,
            "reason": "wholesaleId",
            "adapter_item": {"name": "商品1"},
            "cart_item": {"name": "商品1", "wholesaleId": "12345"},
        }
        self.service._save_cart_backfill_match(
            "test_batch_007",
            "test_detail_001",
            match_status,
            match_type,
            match_score,
            match_detail,
            snapshot_batch_id
        )
        
        # 检查购物车快照的 snapshot_batch_id
        cursor.execute("SELECT snapshot_batch_id FROM smart_cart_snapshots WHERE snapshot_batch_id=?", (snapshot_batch_id,))
        snapshot_result = cursor.fetchone()
        assert snapshot_result is not None, "购物车快照应该存在"
        assert snapshot_result[0] == snapshot_batch_id, "购物车快照的 snapshot_batch_id 应该正确"
        
        # 检查购物车反写匹配的 snapshot_batch_id
        cursor.execute("SELECT snapshot_batch_id FROM smart_cart_backfill_matches WHERE snapshot_batch_id=?", (snapshot_batch_id,))
        backfill_result = cursor.fetchone()
        assert backfill_result is not None, "购物车反写匹配应该存在"
        assert backfill_result[0] == snapshot_batch_id, "购物车反写匹配的 snapshot_batch_id 应该正确"
        
        # 检查两个表的 snapshot_batch_id 是否一致
        assert snapshot_result[0] == backfill_result[0], "购物车快照和反写匹配的 snapshot_batch_id 应该一致"
    
    def test_cart_snapshot_and_backfill_match_extended_scenarios(self):
        """测试12：购物车快照与反写匹配扩展场景"""
        conn = self.db.get_connection()
        cursor = conn.cursor()
        
        # 使用统一的 snapshot_batch_id
        snapshot_batch_id = "snapshot_test_batch_008_20260618120000"
        
        # 场景1：空购物车快照 + 无匹配记录
        self.service._save_cart_snapshot("test_batch_008", [], snapshot_batch_id)
        
        # 检查空购物车快照
        cursor.execute("SELECT snapshot_status, total_items FROM smart_cart_snapshots WHERE snapshot_batch_id=?", (snapshot_batch_id,))
        empty_snapshot_result = cursor.fetchone()
        assert empty_snapshot_result[0] == "empty", "空购物车快照状态应该为empty"
        assert empty_snapshot_result[1] == 0, "空购物车快照total_items应该为0"
        
        # 场景2：有商品购物车快照 + 匹配成功记录
        snapshot_batch_id_2 = "snapshot_test_batch_009_20260618120000"
        cart_items = [
            {"name": "商品1", "spec": "10mg*10片", "manufacturer": "厂家1", "supplier": "供应商1", "price": "10.5", "quantity": "10", "stock": "100"},
        ]
        self.service._save_cart_snapshot("test_batch_009", cart_items, snapshot_batch_id_2)
        
        # 保存匹配成功记录
        match_status = "matched"
        match_type = "wholesaleId"
        match_score = 100
        match_detail = {
            "score": 100,
            "reason": "wholesaleId",
            "adapter_item": {"name": "商品1"},
            "cart_item": {"name": "商品1", "wholesaleId": "12345"},
        }
        self.service._save_cart_backfill_match(
            "test_batch_009",
            "test_detail_001",
            match_status,
            match_type,
            match_score,
            match_detail,
            snapshot_batch_id_2
        )
        
        # 检查有商品购物车快照
        cursor.execute("SELECT snapshot_status, total_items FROM smart_cart_snapshots WHERE snapshot_batch_id=?", (snapshot_batch_id_2,))
        items_snapshot_result = cursor.fetchone()
        assert items_snapshot_result[0] == "completed", "有商品购物车快照状态应该为completed"
        assert items_snapshot_result[1] == 1, "有商品购物车快照total_items应该为1"
        
        # 检查匹配成功记录
        cursor.execute("SELECT match_status FROM smart_cart_backfill_matches WHERE snapshot_batch_id=?", (snapshot_batch_id_2,))
        match_result = cursor.fetchone()
        assert match_result[0] == "matched", "匹配状态应该为matched"
        
        # 场景3：有商品购物车快照 + 匹配失败记录
        snapshot_batch_id_3 = "snapshot_test_batch_010_20260618120000"
        self.service._save_cart_snapshot("test_batch_010", cart_items, snapshot_batch_id_3)
        
        # 保存匹配失败记录
        match_status_failed = "unmatched"
        match_type_failed = "name_spec_manufacturer"
        match_score_failed = 0
        match_detail_failed = {
            "score": 0,
            "reason": "name_spec_manufacturer",
            "adapter_item": {"name": "商品2"},
            "cart_item": {},
        }
        self.service._save_cart_backfill_match(
            "test_batch_010",
            "test_detail_002",
            match_status_failed,
            match_type_failed,
            match_score_failed,
            match_detail_failed,
            snapshot_batch_id_3
        )
        
        # 检查匹配失败记录
        cursor.execute("SELECT match_status FROM smart_cart_backfill_matches WHERE snapshot_batch_id=?", (snapshot_batch_id_3,))
        match_result_failed = cursor.fetchone()
        assert match_result_failed[0] == "unmatched", "匹配状态应该为unmatched"
        
        # 场景4：同一 batch 下多采购明细匹配同一 snapshot_batch_id
        snapshot_batch_id_4 = "snapshot_test_batch_011_20260618120000"
        self.service._save_cart_snapshot("test_batch_011", cart_items, snapshot_batch_id_4)
        
        # 保存多个匹配记录（同一 snapshot_batch_id）
        for i in range(3):
            self.service._save_cart_backfill_match(
                "test_batch_011",
                f"test_detail_{i+1}",
                "matched",
                "wholesaleId",
                100,
                match_detail,
                snapshot_batch_id_4
            )
        
        # 检查同一 snapshot_batch_id 下有多个匹配记录
        cursor.execute("SELECT COUNT(*) FROM smart_cart_backfill_matches WHERE snapshot_batch_id=?", (snapshot_batch_id_4,))
        match_count = cursor.fetchone()[0]
        assert match_count == 3, "同一 snapshot_batch_id 下应该有3个匹配记录"
        
        # 场景5：反写匹配记录的 snapshot_batch_id 必须能在 smart_cart_snapshots 中找到
        cursor.execute("SELECT COUNT(*) FROM smart_cart_backfill_matches WHERE snapshot_batch_id NOT IN (SELECT snapshot_batch_id FROM smart_cart_snapshots)")
        orphan_count = cursor.fetchone()[0]
        assert orphan_count == 0, "不应该存在孤立的 snapshot_batch_id"


class TestCandidateDualTables:
    """测试候选双表长期口径"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """每个测试前创建临时数据库"""
        self.temp_dir = tempfile.mkdtemp()
        self.db_path = Path(self.temp_dir) / "test_candidate_dual_tables.db"
        self.db = Database(str(self.db_path))
        self.db.initialize()  # 初始化数据库，创建所有表
        self.service = SmartPurchaseService(self.db)
        
    def teardown(self):
        """每个测试后清理临时数据库"""
        try:
            if hasattr(self, 'db'):
                self.db.close()
        except:
            pass
    
    def test_candidate_dual_tables_count_consistency(self):
        """测试13：候选双表写入数量一致"""
        conn = self.db.get_connection()
        cursor = conn.cursor()
        
        # 模拟候选数据（3个候选）
        candidates = [
            {"name": "候选1", "spec": "10mg*10片", "manufacturer": "厂家1", "supplier": "供应商1", "price": "10.5", "score": 85, "detail": {}, "isSelected": True},
            {"name": "候选2", "spec": "10mg*20片", "manufacturer": "厂家2", "supplier": "供应商2", "price": "15.5", "score": 75, "detail": {}, "isSelected": False},
            {"name": "候选3", "spec": "10mg*30片", "manufacturer": "厂家3", "supplier": "供应商3", "price": "20.5", "score": 65, "detail": {}, "isSelected": False},
        ]
        
        item = {"itemId": "test_item_dual_001"}
        adapter_item = {"name": "测试商品"}
        
        # 保存候选数据
        for i, candidate in enumerate(candidates):
            is_selected = candidate.get("isSelected") is True
            self.service._save_single_candidate_score(
                cursor, "test_batch_dual_001", item, candidate, adapter_item, "success", i + 1, is_selected
            )
        
        conn.commit()
        
        # 检查 purchase_candidate_scores 表数量
        cursor.execute("SELECT COUNT(*) FROM purchase_candidate_scores")
        purchase_count = cursor.fetchone()[0]
        assert purchase_count == 3, "purchase_candidate_scores 表应该有3条数据"
        
        # 检查 smart_purchase_candidates 表数量
        cursor.execute("SELECT COUNT(*) FROM smart_purchase_candidates")
        smart_count = cursor.fetchone()[0]
        assert smart_count == 3, "smart_purchase_candidates 表应该有3条数据"
        
        # 检查两表数量一致
        assert purchase_count == smart_count, "两表写入数量应该一致"
    
    def test_candidate_dual_tables_selected_consistency(self):
        """测试14：候选双表 selected 候选一致"""
        conn = self.db.get_connection()
        cursor = conn.cursor()
        
        # 模拟候选数据（第2个候选 isSelected=true）
        candidates = [
            {"name": "候选1", "spec": "10mg*10片", "manufacturer": "厂家1", "supplier": "供应商1", "price": "10.5", "score": 85, "detail": {}, "isSelected": False},
            {"name": "候选2", "spec": "10mg*20片", "manufacturer": "厂家2", "supplier": "供应商2", "price": "15.5", "score": 75, "detail": {}, "isSelected": True},
            {"name": "候选3", "spec": "10mg*30片", "manufacturer": "厂家3", "supplier": "供应商3", "price": "20.5", "score": 65, "detail": {}, "isSelected": False},
        ]
        
        item = {"itemId": "test_item_dual_002"}
        adapter_item = {"name": "测试商品"}
        
        # 保存候选数据
        for i, candidate in enumerate(candidates):
            is_selected = candidate.get("isSelected") is True
            self.service._save_single_candidate_score(
                cursor, "test_batch_dual_002", item, candidate, adapter_item, "success", i + 1, is_selected
            )
        
        conn.commit()
        
        # 检查 purchase_candidate_scores 表中 selected=1 的候选
        cursor.execute("SELECT candidate_rank FROM purchase_candidate_scores WHERE selected=1")
        purchase_selected = cursor.fetchone()
        assert purchase_selected[0] == 2, "purchase_candidate_scores 表中第2个候选应该 selected=1"
        
        # 检查 smart_purchase_candidates 表中 selected=1 的候选
        cursor.execute("SELECT candidate_rank FROM smart_purchase_candidates WHERE selected=1")
        smart_selected = cursor.fetchone()
        assert smart_selected[0] == 2, "smart_purchase_candidates 表中第2个候选应该 selected=1"
        
        # 检查两表 selected 候选一致
        assert purchase_selected[0] == smart_selected[0], "两表 selected 候选应该一致"
    
    def test_candidate_dual_tables_final_pass_consistency(self):
        """测试15：候选双表 final_pass 候选一致"""
        conn = self.db.get_connection()
        cursor = conn.cursor()
        
        # 模拟候选数据（第2个候选 isSelected=true，final_pass=1）
        candidates = [
            {"name": "候选1", "spec": "10mg*10片", "manufacturer": "厂家1", "supplier": "供应商1", "price": "10.5", "score": 85, "detail": {}, "isSelected": False},
            {"name": "候选2", "spec": "10mg*20片", "manufacturer": "厂家2", "supplier": "供应商2", "price": "15.5", "score": 75, "detail": {}, "isSelected": True},
            {"name": "候选3", "spec": "10mg*30片", "manufacturer": "厂家3", "supplier": "供应商3", "price": "20.5", "score": 65, "detail": {}, "isSelected": False},
        ]
        
        item = {"itemId": "test_item_dual_003"}
        adapter_item = {"name": "测试商品"}
        
        # 保存候选数据
        for i, candidate in enumerate(candidates):
            is_selected = candidate.get("isSelected") is True
            self.service._save_single_candidate_score(
                cursor, "test_batch_dual_003", item, candidate, adapter_item, "success", i + 1, is_selected
            )
        
        conn.commit()
        
        # 检查 purchase_candidate_scores 表中 final_pass=1 的候选
        cursor.execute("SELECT candidate_rank FROM purchase_candidate_scores WHERE final_pass=1")
        purchase_final_pass = cursor.fetchone()
        assert purchase_final_pass[0] == 2, "purchase_candidate_scores 表中第2个候选应该 final_pass=1"
        
        # 检查 smart_purchase_candidates 表中 final_pass=1 的候选
        cursor.execute("SELECT candidate_rank FROM smart_purchase_candidates WHERE final_pass=1")
        smart_final_pass = cursor.fetchone()
        assert smart_final_pass[0] == 2, "smart_purchase_candidates 表中第2个候选应该 final_pass=1"
        
        # 检查两表 final_pass 候选一致
        assert purchase_final_pass[0] == smart_final_pass[0], "两表 final_pass 候选应该一致"


class TestCurrentSchemaFields:
    """测试当前实现字段口径（第九轮整改方案P0）"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """每个测试前创建临时数据库"""
        self.temp_dir = tempfile.mkdtemp()
        self.db_path = Path(self.temp_dir) / "test_current_schema.db"
        self.db = Database(str(self.db_path))
        self.db.initialize()  # 初始化数据库，创建所有表
        
    def teardown(self):
        """每个测试后清理临时数据库"""
        try:
            if hasattr(self, 'db'):
                self.db.close()
        except:
            pass
    
    def test_current_smart_spec_unit_aliases_schema(self):
        """测试1：验证smart_spec_unit_aliases当前有效字段"""
        conn = self.db.get_connection()
        cursor = conn.cursor()
        
        # 读取表结构
        cursor.execute("PRAGMA table_info(smart_spec_unit_aliases)")
        columns = cursor.fetchall()
        column_names = [col[1] for col in columns]
        
        # 验证当前有效字段存在（第九轮整改方案要求）
        current_fields = ['unit_alias', 'unit_standard', 'description', 'is_enabled']
        for field in current_fields:
            assert field in column_names, f"smart_spec_unit_aliases应该包含字段: {field}"
        
        # 不要求旧草案字段存在（rule_set_id, alias, normalized_unit, unit_type, is_count_unit, is_multiplier）
        print(f"✓ smart_spec_unit_aliases当前有效字段验证通过")
    
    def test_current_smart_spec_parse_rules_schema(self):
        """测试2：验证smart_spec_parse_rules当前有效字段"""
        conn = self.db.get_connection()
        cursor = conn.cursor()
        
        # 读取表结构
        cursor.execute("PRAGMA table_info(smart_spec_parse_rules)")
        columns = cursor.fetchall()
        column_names = [col[1] for col in columns]
        
        # 验证当前有效字段存在（第九轮整改方案要求）
        current_fields = ['rule_code', 'rule_name', 'parse_pattern', 'extract_fields', 'sort_order']
        for field in current_fields:
            assert field in column_names, f"smart_spec_parse_rules应该包含字段: {field}"
        
        # 不要求旧草案字段存在（rule_set_id, rule_type, pattern, priority）
        print(f"✓ smart_spec_parse_rules当前有效字段验证通过")
    
    def test_current_smart_match_thresholds_schema(self):
        """测试3：验证smart_match_thresholds当前有效字段"""
        conn = self.db.get_connection()
        cursor = conn.cursor()
        
        # 读取表结构
        cursor.execute("PRAGMA table_info(smart_match_thresholds)")
        columns = cursor.fetchall()
        column_names = [col[1] for col in columns]
        
        # 验证当前有效字段存在（第九轮整改方案要求）
        current_fields = ['threshold_code', 'threshold_name', 'threshold_value', 'threshold_type']
        for field in current_fields:
            assert field in column_names, f"smart_match_thresholds应该包含字段: {field}"
        
        # 不要求旧草案字段存在（name_weight, spec_weight, maker_weight等独立列）
        print(f"✓ smart_match_thresholds当前有效字段验证通过")
    
    def test_current_smart_name_aliases_schema(self):
        """测试4：验证smart_name_aliases当前有效字段"""
        conn = self.db.get_connection()
        cursor = conn.cursor()
        
        # 读取表结构
        cursor.execute("PRAGMA table_info(smart_name_aliases)")
        columns = cursor.fetchall()
        column_names = [col[1] for col in columns]
        
        # 验证当前有效字段存在（第九轮整改方案要求）
        current_fields = ['name_alias', 'name_standard', 'description', 'is_enabled']
        for field in current_fields:
            assert field in column_names, f"smart_name_aliases应该包含字段: {field}"
        
        # 不要求旧草案字段存在（rule_set_id, alias_type, alias, normalized_value）
        print(f"✓ smart_name_aliases当前有效字段验证通过")
    
    def test_current_cart_snapshot_schema(self):
        """测试5：验证smart_cart_snapshots当前有效字段"""
        conn = self.db.get_connection()
        cursor = conn.cursor()
        
        # 读取表结构
        cursor.execute("PRAGMA table_info(smart_cart_snapshots)")
        columns = cursor.fetchall()
        column_names = [col[1] for col in columns]
        
        # 验证当前有效字段存在（第九轮整改方案要求）
        current_fields = ['snapshot_batch_id', 'snapshot_type', 'total_items', 'snapshot_status', 'snapshot_time']
        for field in current_fields:
            assert field in column_names, f"smart_cart_snapshots应该包含字段: {field}"
        
        print(f"✓ smart_cart_snapshots当前有效字段验证通过")
    
    def test_current_cart_snapshot_items_schema(self):
        """测试6：验证smart_cart_snapshot_items当前有效字段"""
        conn = self.db.get_connection()
        cursor = conn.cursor()
        
        # 读取表结构
        cursor.execute("PRAGMA table_info(smart_cart_snapshot_items)")
        columns = cursor.fetchall()
        column_names = [col[1] for col in columns]
        
        # 验证当前有效字段存在（第九轮整改方案要求）
        current_fields = ['snapshot_batch_id', 'item_name', 'item_spec', 'item_maker', 'item_supplier', 'match_detail']
        for field in current_fields:
            assert field in column_names, f"smart_cart_snapshot_items应该包含字段: {field}"
        
        print(f"✓ smart_cart_snapshot_items当前有效字段验证通过")
    
    def test_current_cart_backfill_matches_schema(self):
        """测试7：验证smart_cart_backfill_matches当前有效字段"""
        conn = self.db.get_connection()
        cursor = conn.cursor()
        
        # 读取表结构
        cursor.execute("PRAGMA table_info(smart_cart_backfill_matches)")
        columns = cursor.fetchall()
        column_names = [col[1] for col in columns]
        
        # 验证当前有效字段存在（第九轮整改方案要求）
        current_fields = ['snapshot_batch_id', 'purchase_batch_id', 'purchase_detail_id', 'match_type', 'match_score', 'match_status', 'match_detail']
        for field in current_fields:
            assert field in column_names, f"smart_cart_backfill_matches应该包含字段: {field}"
        
        print(f"✓ smart_cart_backfill_matches当前有效字段验证通过")


class TestCartWritebackState:
    """购物车执行信息不得覆盖采购原因。"""

    @pytest.fixture(autouse=True)
    def setup(self):
        self.temp_dir = tempfile.mkdtemp()
        self.db_path = Path(self.temp_dir) / "test_cart_writeback_state.db"
        self.db = Database(str(self.db_path))
        self.db.initialize()
        self.service = SmartPurchaseService(self.db)

    def teardown(self):
        self.db.close()

    def test_cart_writeback_columns_exist(self):
        cursor = self.db.get_connection().cursor()
        cursor.execute("PRAGMA table_info(smart_purchase_items)")
        columns = {row[1] for row in cursor.fetchall()}
        assert {
            "cart_write_status", "cart_write_time", "cart_write_message",
            "cart_item_id", "cart_write_attempts",
        }.issubset(columns)

    def test_batch_item_query_returns_cart_writeback_fields(self):
        conn = self.db.get_connection()
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO smart_purchase_items "
            "(item_id, batch_id, row_number, source_name, cart_write_status, "
            "cart_write_time, cart_write_message, cart_item_id, cart_write_attempts) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                "item_query",
                "batch_query",
                1,
                "测试商品",
                "ALREADY_EXISTS",
                "2026-06-23T13:16:18",
                "购物车反写成功",
                "YSB_QUERY_1",
                1,
            ),
        )
        conn.commit()

        rows = self.service.get_batch_items("batch_query")

        assert len(rows) == 1
        assert rows[0]["cart_write_status"] == "ALREADY_EXISTS"
        assert rows[0]["cart_write_message"] == "购物车反写成功"
        assert rows[0]["cart_item_id"] == "YSB_QUERY_1"
        assert rows[0]["cart_write_attempts"] == 1

    def test_adapter_result_preserves_reason_and_persists_writeback(self):
        conn = self.db.get_connection()
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO smart_purchase_items "
            "(item_id, batch_id, row_number, source_name, purchase_reason, purchase_status) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            ("item_1", "batch_1", 1, "测试商品", "原始采购原因", "pending"),
        )
        conn.commit()

        merged = self.service._merge_cart_adapter_result(
            {"purchase_status": "pending", "purchase_reason": "原始采购原因"},
            {
                "status": "failed",
                "reason": "Runtime.evaluate timeout after 30000ms",
                "cartWriteStatus": "FAILED_RETRYABLE",
                "cartWriteAttempts": 2,
                "wholesaleId": "YSB001",
            },
        )
        assert merged["purchase_reason"] == "原始采购原因"
        assert merged["failure_category"] == "TECHNICAL_RETRYABLE"
        assert self.service._result_display_reason(merged) == "Runtime.evaluate timeout after 30000ms"
        assert merged["cart_write_status"] == "FAILED_RETRYABLE"
        assert "timeout" in merged["cart_write_message"]

        self.service._save_purchase_result("item_1", merged)
        cursor.execute(
            "SELECT purchase_reason, cart_write_status, cart_write_message, "
            "cart_item_id, cart_write_attempts FROM smart_purchase_items WHERE item_id = ?",
            ("item_1",),
        )
        saved = cursor.fetchone()
        assert saved[0] == "原始采购原因"
        assert saved[1] == "FAILED_RETRYABLE"
        assert "timeout" in saved[2]
        assert saved[3] == "YSB001"
        assert saved[4] == 2

    def test_business_rejection_updates_purchase_reason(self):
        merged = self.service._merge_cart_adapter_result(
            {"purchase_status": "pending", "purchase_reason": "已通过基础校验"},
            {
                "status": "failed",
                "reason": "候选综合分低于规则阈值",
                "failureCategory": "BUSINESS_REJECTED",
                "failureStage": "precheck",
                "failureCode": "SCORE_LOW",
            },
        )
        assert merged["purchase_reason"] == "候选综合分低于规则阈值"
        assert merged["cart_write_message"] == "候选综合分低于规则阈值"
        assert self.service._result_display_reason(merged) == "候选综合分低于规则阈值"

    def test_web_error_cancel_aborts_batch(self):
        item = {"itemId": "item_web", "rowNumber": 1, "name": "测试商品"}
        results, aborted, reason = self.service._handle_web_error_retry(
            "batch_web",
            [item],
            [{**item, "status": "web_error", "reason": "药师帮页面未确认登录"}],
            "",
            web_error_callback=lambda _message: False,
        )
        assert aborted is True
        assert "用户取消继续执行" in reason
        assert results[0]["status"] == "web_error"

    def test_two_consecutive_web_errors_trip_circuit_breaker(self, monkeypatch):
        item = {"itemId": "item_web", "rowNumber": 1, "name": "测试商品"}
        callback_count = 0
        retry_count = 0

        def continue_once(_message):
            nonlocal callback_count
            callback_count += 1
            return True

        def retry_with_same_error(*_args, **_kwargs):
            nonlocal retry_count
            retry_count += 1
            return [{**item, "status": "web_error", "reason": "fetch failed"}]

        monkeypatch.setattr(self.service, "_run_cart_adapter_batch", retry_with_same_error)
        results, aborted, reason = self.service._handle_web_error_retry(
            "batch_web",
            [item],
            [{**item, "status": "web_error", "reason": "fetch failed"}],
            "",
            web_error_callback=continue_once,
        )
        assert aborted is True
        assert "连续 2 次" in reason
        assert callback_count == 1
        assert retry_count == 1
        assert results[0]["reason"] == "fetch failed"

    def test_final_cart_reconcile_runs_one_snapshot(self, monkeypatch):
        snapshot_calls = []
        saved_states = []
        cart_item = {
            "wholesaleId": "YSB_FINAL_1",
            "name": "测试商品",
            "spec": "10mg*10片",
            "manufacturer": "测试厂家",
        }

        def snapshot(*args, **kwargs):
            snapshot_calls.append((args, kwargs))
            return [cart_item]

        def save_state(*args, **kwargs):
            saved_states.append((args, kwargs))

        monkeypatch.setattr(self.service, "_run_cart_snapshot", snapshot)
        monkeypatch.setattr(self.service, "_save_cart_writeback_state", save_state)
        self.service._reconcile_successful_cart_results(
            "batch_final",
            [
                (
                    "item_final",
                    {
                        "wholesaleId": "YSB_FINAL_1",
                        "name": "测试商品",
                        "spec": "10mg*10片",
                        "manufacturer": "测试厂家",
                    },
                    {"status": "success"},
                    {
                        "purchase_status": "success",
                        "actual_ysb_code": "YSB_FINAL_1",
                        "cart_write_status": "WRITTEN",
                    },
                )
            ],
            "",
        )
        assert len(snapshot_calls) == 1
        assert len(saved_states) == 1
        assert saved_states[0][0][1] == "WRITTEN"

    def test_node_adapter_syntax_preflight(self):
        assert self.service._check_cart_adapter_syntax() == ""

    def test_success_writeback_persists_without_changing_reason(self):
        conn = self.db.get_connection()
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO smart_purchase_items "
            "(item_id, batch_id, row_number, source_name, purchase_reason, purchase_status) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            ("item_2", "batch_1", 2, "测试商品2", "原始成功原因", "pending"),
        )
        conn.commit()
        merged = self.service._merge_cart_adapter_result(
            {"purchase_status": "pending", "purchase_reason": "原始成功原因"},
            {
                "status": "success",
                "reason": "已加入购物车并验证存在",
                "cartWriteStatus": "WRITTEN",
                "verifiedAmount": 3,
                "wholesaleId": "YSB002",
            },
        )
        self.service._save_purchase_result("item_2", merged)
        cursor.execute(
            "SELECT purchase_reason, cart_write_status, cart_item_id "
            "FROM smart_purchase_items WHERE item_id = ?",
            ("item_2",),
        )
        saved = cursor.fetchone()
        assert tuple(saved) == ("原始成功原因", "WRITTEN", "YSB002")

    def test_cart_backfill_reset_preserves_purchase_result(self):
        conn = self.db.get_connection()
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO smart_purchase_items "
            "(item_id, batch_id, row_number, source_name, purchase_reason, purchase_status, "
            "cart_write_status, cart_write_message) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                "item_reset",
                "batch_reset",
                1,
                "测试商品",
                "原始采购原因",
                "failed",
                "FAILED_MANUAL",
                "旧反写信息",
            ),
        )
        conn.commit()

        self.service._clear_purchase_backfill_history(
            "batch_reset",
            remove_cart_extra=False,
            preserve_purchase_result=True,
        )

        cursor.execute(
            "SELECT purchase_reason, purchase_status, cart_write_status, cart_write_message "
            "FROM smart_purchase_items WHERE item_id = ?",
            ("item_reset",),
        )
        saved = cursor.fetchone()
        assert tuple(saved) == ("原始采购原因", "failed", "NOT_STARTED", "")

    def test_cart_state_update_does_not_change_purchase_reason(self):
        conn = self.db.get_connection()
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO smart_purchase_items "
            "(item_id, batch_id, row_number, source_name, purchase_reason, purchase_status) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            ("item_state", "batch_state", 1, "测试商品", "原始原因", "success"),
        )
        conn.commit()

        self.service._save_cart_writeback_state(
            "item_state",
            "NOT_FOUND",
            "未匹配到购物车商品",
            attempts=1,
        )

        cursor.execute(
            "SELECT purchase_reason, purchase_status, cart_write_status, "
            "cart_write_message, cart_write_attempts FROM smart_purchase_items WHERE item_id = ?",
            ("item_state",),
        )
        saved = cursor.fetchone()
        assert tuple(saved) == (
            "原始原因",
            "success",
            "NOT_FOUND",
            "未匹配到购物车商品",
            1,
        )

    def test_purchase_result_save_can_explicitly_preserve_reason(self):
        conn = self.db.get_connection()
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO smart_purchase_items "
            "(item_id, batch_id, row_number, source_name, purchase_reason, purchase_status) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            ("item_preserve", "batch_preserve", 1, "测试商品", "数据库原始原因", "failed"),
        )
        conn.commit()

        self.service._save_purchase_result(
            "item_preserve",
            {
                "purchase_status": "success",
                "purchase_reason": "这段反写文本不得覆盖原因",
                "cart_write_status": "ALREADY_EXISTS",
                "cart_write_message": "购物车匹配成功",
            },
            preserve_purchase_reason=True,
        )

        cursor.execute(
            "SELECT purchase_reason, cart_write_status, cart_write_message "
            "FROM smart_purchase_items WHERE item_id = ?",
            ("item_preserve",),
        )
        assert tuple(cursor.fetchone()) == (
            "数据库原始原因",
            "ALREADY_EXISTS",
            "购物车匹配成功",
        )

    def test_cart_extra_uses_writeback_fields_instead_of_reason(self):
        cart_item = {
            "name": "购物车额外商品",
            "spec": "10mg*10片",
            "manufacturer": "测试厂家",
            "supplier": "测试供应商",
            "amount": 2,
            "price": 12.5,
            "wholesaleId": "YSB_EXTRA_1",
        }

        self.service._upsert_cart_extra_item("batch_extra", cart_item)

        conn = self.db.get_connection()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT purchase_reason, cart_write_status, cart_write_message, cart_item_id "
            "FROM smart_purchase_items WHERE batch_id = ? AND activity_type = 'cart_extra'",
            ("batch_extra",),
        )
        saved = cursor.fetchone()
        assert tuple(saved) == (
            "",
            "ALREADY_EXISTS",
            "购物车额外商品已登记",
            "YSB_EXTRA_1",
        )


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
