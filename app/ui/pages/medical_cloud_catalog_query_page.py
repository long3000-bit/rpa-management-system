"""云药店商品信息查询页面"""

from app.storage.database import Database
from app.ui.pages.medical_data_query_page import MedicalDataQueryPage


class MedicalCloudCatalogQueryPage(MedicalDataQueryPage):
    """云药店商品信息查询页面"""
    
    def __init__(self, db: Database, user: dict):
        super().__init__(
            db=db,
            user=user,
            table_name="cloud_pharmacy_catalog",
            title="云药店商品信息查询",
            batch_type="cloud_pharmacy_catalog",
            search_fields=[
                ("商品名称", "商品名称"),
                ("商品编码", "商品编码"),
                ("生产厂家", "生产厂家"),
                ("医保编码", "医保编码"),
            ],
            display_columns=[
                ("商品编码", "商品编码"),
                ("旧商品编码", "旧商品编码"),
                ("商品名称", "商品名称"),
                ("通用名", "通用名"),
                ("规格", "规格"),
                ("剂型", "剂型"),
                ("包装规格", "包装规格"),
                ("单位", "单位"),
                ("生产厂家", "生产厂家"),
                ("批准文号", "批准文号"),
                ("医保编码", "医保编码"),
                ("医保类型", "医保类型"),
                ("商品状态", "商品状态"),
            ]
        )
        
        # 加载批次
        self._load_batches()