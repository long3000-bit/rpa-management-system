"""医保西药查询页面"""

from app.storage.database import Database
from app.ui.pages.medical_data_query_page import MedicalDataQueryPage


class MedicalWesternQueryPage(MedicalDataQueryPage):
    """医保西药查询页面"""
    
    def __init__(self, db: Database, user: dict):
        super().__init__(
            db=db,
            user=user,
            table_name="medical_catalog_western",
            title="医保西药目录查询",
            batch_type="medical_catalog_western",
            search_fields=[
                ("医保药品名称", "药品名称"),
                ("国家药品代码", "国家药品代码"),
                ("药品企业", "生产企业"),
                ("实际规格", "规格"),
            ],
            display_columns=[
                ("国家药品代码", "国家药品代码"),
                ("医保药品名称", "药品名称"),
                ("注册名称", "注册名称"),
                ("医保剂型", "剂型"),
                ("实际规格", "规格"),
                ("包装材质", "包装材质"),
                ("最小计价单位", "计价单位"),
                ("药品企业", "生产企业"),
                ("医保支付类别", "甲乙类"),
                ("政府定价元", "政府定价"),
                ("医保支付标准", "医保支付标准"),
                ("医保限定支付范围", "限制使用范围"),
                ("备注", "备注"),
            ]
        )
        
        # 加载批次
        self._load_batches()