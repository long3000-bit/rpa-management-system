"""三同口径文件查询页面"""

from app.storage.database import Database
from app.ui.pages.medical_data_query_page import MedicalDataQueryPage


class MedicalPriceLimitQueryPage(MedicalDataQueryPage):
    """三同口径文件查询页面"""
    
    def __init__(self, db: Database, user: dict):
        super().__init__(
            db=db,
            user=user,
            table_name="medical_price_limit",
            title="三同口径文件查询",
            batch_type="medical_price_limit",
            search_fields=[
                ("药品名称", "药品名称"),
                ("医保编码", "医保编码"),
                ("生产企业", "生产企业"),
                ("规格", "规格"),
            ],
            display_columns=[
                ("医保编码", "医保编码"),
                ("药品名称", "药品名称"),
                ("通用名", "通用名"),
                ("剂型", "剂型"),
                ("规格", "规格"),
                ("生产企业", "生产企业"),
                ("转换比", "转换比"),
                ("三同药品挂网最低单片价", "挂网最低价"),
                ("三同药品参比价", "参比价"),
                ("分组名称", "分组名称"),
                ("数据时间", "数据时间"),
            ]
        )
        
        # 加载批次
        self._load_batches()