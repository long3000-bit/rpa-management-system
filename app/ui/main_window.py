from PySide6.QtWidgets import (
    QWidget, QLabel, QVBoxLayout, QHBoxLayout,
    QPushButton, QTabWidget, QTabBar, QFrame, QMenu
)
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QAction

from app.config import APP_NAME
from app.core.auth_service import AuthService
from app.core.permission_service import PermissionService
from app.ui.pages.home_page import HomePage
from app.ui.pages.rpa_robot_page import RpaRobotPage
from app.ui.pages.rpa_exe_config_page import RpaExeConfigPage
from app.ui.pages.reconciliation_page import ReconciliationPage
from app.ui.pages.ysb_data_query_page import YsbDataQueryPage
from app.ui.pages.inbound_query_page import InboundQueryPage
from app.ui.pages.reconciliation_result_page import ReconciliationResultPage
from app.ui.pages.task_record_page import TaskRecordPage
from app.ui.pages.settings_page import SettingsPage
from app.ui.pages.log_page import LogPage
from app.ui.pages.operation_log_page import OperationLogPage
from app.ui.pages.db_import_page import DbImportPage
from app.ui.pages.smart_purchase_page import SmartPurchasePage
from app.ui.pages.rule_manage_page import RuleManagePage
from app.ui.pages.stock_compare_page import StockComparePage
from app.ui.pages.yys_stock_query_page import YysStockQueryPage
from app.ui.pages.jy_stock_query_page import JyStockQueryPage
from app.ui.pages.yys_api_config_page import YysApiConfigPage
from app.ui.pages.user_manage_page import UserManagePage
from app.ui.pages.role_permission_page import RolePermissionPage
from app.ui.pages.medical_price_control_page import MedicalPriceControlPage
from app.ui.pages.medical_western_query_page import MedicalWesternQueryPage
from app.ui.pages.medical_chinese_query_page import MedicalChineseQueryPage
from app.ui.pages.medical_price_limit_query_page import MedicalPriceLimitQueryPage
from app.ui.pages.medical_cloud_catalog_query_page import MedicalCloudCatalogQueryPage
from app.ui.pages.medical_compare_result_query_page import MedicalCompareResultQueryPage
from app.ui.pages.tts_page import TTSPage
from app.ui.change_password_dialog import ChangePasswordDialog


class MainWindow(QWidget):
    
    logout_signal = Signal()
    
    def __init__(self, db, user: dict):
        super().__init__()
        self.db = db
        self.user = user
        self.auth_service = AuthService(db)
        self.permission_service = PermissionService(db)
        
        # 加载用户权限
        self.user_permissions = self.permission_service.get_user_permissions(user['username'])
        
        self._init_ui()
    
    def _init_ui(self):
        self.setWindowTitle(APP_NAME)
        self.setMinimumSize(1200, 800)
        self.setStyleSheet(self._get_stylesheet())
        
        main_layout = QHBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)
        
        sidebar = self._create_sidebar()
        main_layout.addWidget(sidebar)
        
        content_area = self._create_content_area()
        main_layout.addWidget(content_area, 1)
    
    def _create_sidebar(self) -> QWidget:
        sidebar = QFrame()
        sidebar.setObjectName("sidebar")
        sidebar.setFixedWidth(200)
        
        layout = QVBoxLayout(sidebar)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        
        header = QLabel(APP_NAME)
        header.setObjectName("sidebarHeader")
        header.setAlignment(Qt.AlignCenter)
        header.setFixedHeight(60)
        layout.addWidget(header)
        
        self.menu_buttons = []
        self.menu_groups = {}
        
        # 定义菜单项及其权限编码
        menu_items = [
            ("首页", "home", "menu.home"),
            {
                "text": "智能工具",
                "group_id": "smart_tools_group",
                "children": [
                    ("RPA机器人", "rpa", "menu.rpa_robot"),
                    ("EXE配置管理", "exe_config", "menu.exe_config"),
                    ("文本转语音", "tts", "menu.tts"),
                ],
            },
            {
                "text": "智能采购",
                "group_id": "smart_purchase_group",
                "children": [
                    ("药师帮智能采购", "smart_purchase", "menu.smart_purchase"),
                    ("评分规则管理", "rule_manage", "menu.smart_purchase"),
                ],
            },
            {
                "text": "云药店库存同步",
                "group_id": "yys_stock_sync",
                "children": [
                    ("库存对比", "stock_compare", "menu.stock_compare"),
                    ("云药店库存查询", "yys_stock_query", "menu.yys_stock"),
                    ("君元库存查询", "jy_stock_query", "menu.jy_stock"),
                    ("API配置管理", "yys_api_config", "menu.config_center"),
                ],
            },
            {
                "text": "药师帮对账",
                "group_id": "ysb_reconciliation",
                "children": [
                    ("入库对账", "reconciliation", "menu.ysb_reconcile"),
                    ("对账结果查询", "recon_result", "menu.ysb_reconcile"),
                    ("药师帮数据查询", "ysb_query", "menu.ysb_reconcile"),
                    ("入库单查询", "inbound_query", "menu.ysb_reconcile"),
                    ("数据库导入", "db_import", "menu.db_import"),
                    ("执行记录", "task_record", "menu.task_record"),
                ],
            },
            {
                "text": "医保价格管控",
                "group_id": "medical_price_group",
                "children": [
                    ("价格比对", "medical_price_compare", "menu.medical_price_compare"),
                    ("比对结果查询", "medical_compare_result_query", "menu.medical_compare_result_query"),
                    ("医保西药查询", "medical_western_query", "menu.medical_western_query"),
                    ("医保中成药查询", "medical_chinese_query", "menu.medical_chinese_query"),
                    ("价格上限查询", "medical_price_limit_query", "menu.medical_price_limit_query"),
                    ("商品信息查询", "medical_cloud_catalog_query", "menu.medical_cloud_catalog_query"),
                ],
            },
            {
                "text": "系统管理",
                "group_id": "system_management",
                "children": [
                    ("配置中心", "settings", "menu.config_center"),
                    ("用户管理", "user_manage", "menu.user_manage"),
                    ("角色权限管理", "role_permission", "menu.role_permission"),
                    ("日志与截图", "log", "menu.operation_logs"),
                ],
            },
        ]
        
        # 根据权限过滤菜单项
        for item in menu_items:
            if isinstance(item, dict):
                group_id = item["group_id"]
                
                # 过滤子菜单
                visible_children = []
                for text, page_id, perm_code in item["children"]:
                    if perm_code in self.user_permissions:
                        visible_children.append((text, page_id, perm_code))
                
                # 如果没有可见的子菜单，跳过整个分组
                if not visible_children:
                    continue
                
                group_btn = QPushButton(item["text"])
                group_btn.setObjectName("menuGroupBtn")
                group_btn.setProperty("group_id", group_id)
                group_btn.clicked.connect(lambda checked, gid=group_id: self._toggle_menu_group(gid))
                layout.addWidget(group_btn)
                
                child_buttons = []
                for text, page_id, perm_code in visible_children:
                    btn = QPushButton(text)
                    btn.setObjectName("submenuBtn")
                    btn.setProperty("page_id", page_id)
                    btn.setProperty("group_id", group_id)
                    btn.clicked.connect(lambda checked, pid=page_id: self._switch_page(pid))
                    btn.setVisible(False)  # 默认不显示子菜单
                    layout.addWidget(btn)
                    self.menu_buttons.append(btn)
                    child_buttons.append(btn)
                
                self.menu_groups[group_id] = {
                    "button": group_btn,
                    "children": child_buttons,
                    "expanded": False,  # 默认不展开
                    "text": item["text"],
                }
                continue
            
            text, page_id, perm_code = item
            
            # 检查权限
            if perm_code not in self.user_permissions:
                continue
            
            btn = QPushButton(text)
            btn.setObjectName("menuBtn")
            btn.setProperty("page_id", page_id)
            btn.clicked.connect(lambda checked, pid=page_id: self._switch_page(pid))
            layout.addWidget(btn)
            self.menu_buttons.append(btn)
        
        layout.addStretch()
        
        return sidebar
    
    def _toggle_menu_group(self, group_id: str):
        group = self.menu_groups.get(group_id)
        if not group:
            return
        
        expanded = not group["expanded"]
        group["expanded"] = expanded
        for child in group["children"]:
            child.setVisible(expanded)
        
        group["button"].setText(group.get("text", group_id))
    
    def _create_content_area(self) -> QWidget:
        content = QFrame()
        content.setObjectName("contentArea")
        
        layout = QVBoxLayout(content)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        
        topbar = self._create_topbar()
        layout.addWidget(topbar)
        
        self.page_titles = {
            "home": "首页",
            "rpa": "RPA机器人",
            "exe_config": "EXE配置管理",
            "smart_purchase": "智能采购 / 药师帮智能采购",
            "rule_manage": "智能采购 / 评分规则管理",
            "stock_compare": "云药店库存同步 / 库存对比",
            "yys_stock_query": "云药店库存同步 / 云药店库存查询",
            "jy_stock_query": "云药店库存同步 / 君元库存查询",
            "yys_api_config": "云药店库存同步 / API配置管理",
            "reconciliation": "药师帮对账 / 入库对账",
            "recon_result": "药师帮对账 / 对账结果查询",
            "ysb_query": "药师帮对账 / 药师帮数据查询",
            "inbound_query": "药师帮对账 / 入库单查询",
            "db_import": "药师帮对账 / 数据库导入",
            "task_record": "药师帮对账 / 执行记录",
            "medical_price_compare": "医保价格管控 / 价格比对",
            "medical_compare_result_query": "医保价格管控 / 比对结果查询",
            "medical_western_query": "医保价格管控 / 医保西药查询",
            "medical_chinese_query": "医保价格管控 / 医保中成药查询",
            "medical_price_limit_query": "医保价格管控 / 价格上限查询",
            "medical_cloud_catalog_query": "医保价格管控 / 商品信息查询",
            "settings": "系统管理 / 配置中心",
            "tts": "系统管理 / 文本转语音",
            "user_manage": "系统管理 / 用户管理",
            "role_permission": "系统管理 / 角色权限管理",
            "log": "系统管理 / 日志与截图",
        }
        self.page_tab_titles = {
            "home": "首页",
            "rpa": "RPA机器人",
            "exe_config": "EXE配置",
            "smart_purchase": "智能采购",
            "rule_manage": "评分规则",
            "stock_compare": "库存对比",
            "yys_stock_query": "云药店库存",
            "jy_stock_query": "君元库存",
            "yys_api_config": "API配置",
            "reconciliation": "入库对账",
            "recon_result": "结果查询",
            "ysb_query": "药师帮数据",
            "inbound_query": "入库单查询",
            "db_import": "数据库导入",
            "task_record": "执行记录",
            "settings": "配置中心",
            "medical_price_compare": "价格比对",
            "medical_compare_result_query": "比对结果",
            "medical_western_query": "医保西药",
            "medical_chinese_query": "医保中成药",
            "medical_price_limit_query": "价格上限",
            "medical_cloud_catalog_query": "商品信息",
            "tts": "文本转语音",
            "user_manage": "用户管理",
            "role_permission": "角色权限",
            "log": "日志",
        }
        # 页面字典 - 延迟加载，只创建首页
        self.pages = {
            "home": HomePage(),
        }
        # 其他页面在首次访问时创建
        self._page_classes = {
            "rpa": lambda: RpaRobotPage(self.db, self.user['username'], self.user.get('role_code', 'store_manager')),
            "exe_config": lambda: RpaExeConfigPage(self.db),
            "smart_purchase": lambda: SmartPurchasePage(self.db, self.user['username'], self.user.get('role_code', 'store_manager')),
            "rule_manage": lambda: RuleManagePage(self.db, self.user['username'], self.user.get('role_code', 'store_manager')),
            "stock_compare": lambda: StockComparePage(self.db, self.user['username'], self.user.get('role_code', 'store_manager')),
            "yys_stock_query": lambda: YysStockQueryPage(self.db, self.user['username'], self.user.get('role_code', 'store_manager')),
            "jy_stock_query": lambda: JyStockQueryPage(self.db),
            "yys_api_config": lambda: YysApiConfigPage(self.db, self.user['username']),
            "reconciliation": lambda: ReconciliationPage(self.db, self.user['username'], self.user.get('role_code', 'store_manager')),
            "recon_result": lambda: ReconciliationResultPage(self.db),
            "ysb_query": lambda: YsbDataQueryPage(self.db),
            "inbound_query": lambda: InboundQueryPage(self.db),
            "db_import": lambda: DbImportPage(self.db, self.user['username']),
            "task_record": lambda: TaskRecordPage(self.db, self.user['username'], self.user.get('role_code', 'store_manager')),
            "settings": lambda: SettingsPage(self.db, self.user['username']),
            "medical_price_compare": lambda: MedicalPriceControlPage(self.db, self.user['username'], self.user.get('role_code', 'store_manager')),
            "medical_compare_result_query": lambda: MedicalCompareResultQueryPage(self.db, self.user),
            "medical_western_query": lambda: MedicalWesternQueryPage(self.db, self.user),
            "medical_chinese_query": lambda: MedicalChineseQueryPage(self.db, self.user),
            "medical_price_limit_query": lambda: MedicalPriceLimitQueryPage(self.db, self.user),
            "medical_cloud_catalog_query": lambda: MedicalCloudCatalogQueryPage(self.db, self.user),
            "tts": lambda: TTSPage(self.db, self.user),
            "user_manage": lambda: UserManagePage(self.db, self.user['username']),
            "role_permission": lambda: RolePermissionPage(self.db, self.user['username']),
            "log": lambda: OperationLogPage(self.db, self.user['username']),
        }
        
        self.page_tabs = QTabWidget()
        self.page_tabs.setObjectName("pageTabs")
        self.page_tabs.setTabsClosable(True)
        self.page_tabs.setMovable(True)
        self.page_tabs.tabCloseRequested.connect(self._close_page_tab)
        self.page_tabs.currentChanged.connect(self._on_current_tab_changed)
        self.page_tabs.tabBar().tabMoved.connect(lambda _from, _to: self._rebuild_opened_tab_indexes())
        self.opened_tabs = {}
        self._switch_page("home")
        layout.addWidget(self.page_tabs, 1)
        
        return content
    
    def _create_topbar(self) -> QWidget:
        topbar = QFrame()
        topbar.setObjectName("topbar")
        topbar.setFixedHeight(50)
        
        layout = QHBoxLayout(topbar)
        layout.setContentsMargins(20, 0, 20, 0)
        
        self.page_title = QLabel("首页")
        self.page_title.setObjectName("pageTitle")
        layout.addWidget(self.page_title)
        
        layout.addStretch()
        
        display_name = self.auth_service.get_display_name(self.user['username'])
        user_label = QLabel(f"当前用户: {display_name}")
        user_label.setObjectName("userLabel")
        layout.addWidget(user_label)
        
        user_menu_btn = QPushButton("账号")
        user_menu_btn.setObjectName("userMenuBtn")
        
        menu = QMenu(user_menu_btn)
        change_pwd_action = QAction("修改密码", menu)
        change_pwd_action.triggered.connect(self._show_change_password)
        menu.addAction(change_pwd_action)
        
        menu.addSeparator()
        
        logout_action = QAction("退出登录", menu)
        logout_action.triggered.connect(self._logout)
        menu.addAction(logout_action)
        
        user_menu_btn.setMenu(menu)
        layout.addWidget(user_menu_btn)
        
        return topbar
    
    def _switch_page(self, page_id: str):
        # 检查页面权限
        page_permission_map = {
            "home": "menu.home",
            "rpa": "menu.rpa_robot",
            "exe_config": "menu.exe_config",
            "smart_purchase": "menu.smart_purchase",
            "rule_manage": "menu.smart_purchase",
            "stock_compare": "menu.stock_compare",
            "yys_stock_query": "menu.yys_stock",
            "jy_stock_query": "menu.jy_stock",
            "yys_api_config": "menu.config_center",
            "reconciliation": "menu.ysb_reconcile",
            "recon_result": "menu.ysb_reconcile",
            "ysb_query": "menu.ysb_reconcile",
            "inbound_query": "menu.ysb_reconcile",
            "db_import": "menu.db_import",
            "task_record": "menu.task_record",
            "settings": "menu.config_center",
            "medical_price": "menu.medical_price_control",
            "user_manage": "menu.user_manage",
            "role_permission": "menu.role_permission",
            "log": "menu.operation_logs",
        }
        
        required_permission = page_permission_map.get(page_id)
        if required_permission and required_permission not in self.user_permissions:
            from PySide6.QtWidgets import QMessageBox
            QMessageBox.warning(self, "权限不足", f"您没有权限访问此页面")
            return
        
        page = self.pages.get(page_id)
        if not page:
            # 延迟创建页面 - 首次访问时才创建
            if page_id in self._page_classes:
                page = self._page_classes[page_id]()
                self.pages[page_id] = page
            else:
                return
        
        if page_id not in self.opened_tabs:
            tab_index = self.page_tabs.addTab(page, self.page_tab_titles.get(page_id, self.page_titles.get(page_id, "")))
            if page_id == "home":
                self.page_tabs.tabBar().setTabButton(tab_index, QTabBar.RightSide, None)
            self.opened_tabs[page_id] = tab_index
        else:
            tab_index = self.page_tabs.indexOf(page)
            if tab_index < 0:
                tab_index = self.page_tabs.addTab(page, self.page_tab_titles.get(page_id, self.page_titles.get(page_id, "")))
                if page_id == "home":
                    self.page_tabs.tabBar().setTabButton(tab_index, QTabBar.RightSide, None)
            self.opened_tabs[page_id] = tab_index
        
        self.page_tabs.setCurrentIndex(tab_index)
        self._activate_page(page_id)
    
    def _close_page_tab(self, index: int):
        page_id = self._page_id_by_tab_index(index)
        if page_id == "home":
            return
        
        self.page_tabs.removeTab(index)
        if page_id:
            self.opened_tabs.pop(page_id, None)
        
        self._rebuild_opened_tab_indexes()
        current_page_id = self._page_id_by_tab_index(self.page_tabs.currentIndex())
        if current_page_id:
            self._activate_page(current_page_id)
    
    def _on_current_tab_changed(self, index: int):
        page_id = self._page_id_by_tab_index(index)
        if page_id:
            self._activate_page(page_id)
    
    def _page_id_by_tab_index(self, index: int) -> str:
        if index < 0:
            return ""
        
        widget = self.page_tabs.widget(index)
        for page_id, page in self.pages.items():
            if page is widget:
                return page_id
        return ""
    
    def _rebuild_opened_tab_indexes(self):
        self.opened_tabs = {}
        for index in range(self.page_tabs.count()):
            page_id = self._page_id_by_tab_index(index)
            if page_id:
                self.opened_tabs[page_id] = index
    
    def _activate_page(self, page_id: str):
        page = self.pages.get(page_id)
        if not page:
            return
        
        self.page_title.setText(self.page_titles.get(page_id, ""))
        
        if page_id == "recon_result":
            if hasattr(page, '_load_tasks'):
                page._load_tasks()
        
        if page_id == "ysb_query":
            if hasattr(page, '_load_batches'):
                page._load_batches()
        
        if page_id == "inbound_query":
            if hasattr(page, '_load_db_configs'):
                page._load_db_configs()
        
        for btn in self.menu_buttons:
            if btn.property("page_id") == page_id:
                btn.setProperty("active", True)
            else:
                btn.setProperty("active", False)
            btn.style().unpolish(btn)
            btn.style().polish(btn)
        
        for group in self.menu_groups.values():
            group_page_ids = [child.property("page_id") for child in group["children"]]
            group["button"].setProperty("active", page_id in group_page_ids)
            group["button"].style().unpolish(group["button"])
            group["button"].style().polish(group["button"])
    
    def _show_change_password(self):
        dialog = ChangePasswordDialog(self.db, self.user['username'], self)
        dialog.exec()
    
    def _logout(self):
        from app.ui.login_window import LoginWindow
        self.close()
        self.login_window = LoginWindow(self.db)
        self.login_window.show()
    
    def _get_stylesheet(self):
        return """
            QFrame#sidebar {
                background-color: #2c3e50;
            }
            
            QLabel#sidebarHeader {
                color: white;
                font-size: 16px;
                font-weight: bold;
                background-color: #1a252f;
            }
            
            QPushButton#menuBtn {
                padding: 15px 20px;
                text-align: left;
                background-color: transparent;
                color: #bdc3c7;
                border: none;
                font-size: 14px;
            }
            
            QPushButton#menuBtn:hover {
                background-color: #34495e;
                color: white;
            }
            
            QPushButton#menuBtn[active="true"] {
                background-color: #3498db;
                color: white;
            }
            
            QPushButton#menuGroupBtn {
                padding: 14px 20px;
                text-align: left;
                background-color: #243443;
                color: #ecf0f1;
                border: none;
                font-size: 14px;
                font-weight: bold;
            }
            
            QPushButton#menuGroupBtn:hover {
                background-color: #34495e;
                color: white;
            }
            
            QPushButton#menuGroupBtn[active="true"] {
                background-color: #2d7fb8;
                color: white;
            }
            
            QPushButton#submenuBtn {
                padding: 12px 20px 12px 36px;
                text-align: left;
                background-color: transparent;
                color: #bdc3c7;
                border: none;
                font-size: 13px;
            }
            
            QPushButton#submenuBtn:hover {
                background-color: #34495e;
                color: white;
            }
            
            QPushButton#submenuBtn[active="true"] {
                background-color: #3498db;
                color: white;
            }
            
            QFrame#contentArea {
                background-color: #ecf0f1;
            }
            
            QTabWidget#pageTabs::pane {
                border: none;
                background-color: #ecf0f1;
            }
            
            QTabWidget#pageTabs QTabBar::tab {
                padding: 8px 18px;
                margin: 0 2px 0 0;
                background-color: #dfe6e9;
                color: #555;
                border: 1px solid #cfd8dc;
                border-bottom: none;
                min-width: 86px;
                font-size: 13px;
            }
            
            QTabWidget#pageTabs QTabBar::tab:selected {
                background-color: white;
                color: #222;
                font-weight: bold;
            }
            
            QTabWidget#pageTabs QTabBar::tab:hover {
                background-color: #eef3f5;
                color: #222;
            }
            
            QFrame#topbar {
                background-color: white;
                border-bottom: 1px solid #ddd;
            }
            
            QLabel#pageTitle {
                font-size: 16px;
                font-weight: bold;
                color: #333;
            }
            
            QLabel#userLabel {
                color: #666;
                font-size: 13px;
            }
            
            QPushButton#userMenuBtn {
                padding: 8px 15px;
                background-color: #3498db;
                color: white;
                border: none;
                border-radius: 4px;
                font-size: 13px;
            }
            
            QPushButton#userMenuBtn:hover {
                background-color: #2980b9;
            }
        """
