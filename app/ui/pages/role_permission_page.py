import logging
from typing import Dict, List

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTableWidget, QTableWidgetItem,
    QPushButton, QMessageBox, QHeaderView, QLabel, QGroupBox, QTreeWidget,
    QTreeWidgetItem, QSplitter, QDialog, QFormLayout, QLineEdit, QComboBox
)
from PySide6.QtCore import Qt

from app.storage.database import Database
from app.core.permission_service import PermissionService
from app.core.permission_checker import PermissionChecker, PermissionCodes


class RolePermissionPage(QWidget):
    """角色权限管理页面"""
    
    def __init__(self, db: Database, current_username: str):
        super().__init__()
        self.db = db
        self.current_username = current_username
        self.permission_service = PermissionService(db)
        self.permission_checker = PermissionChecker(db, current_username)
        
        self.current_role_code = None
        
        self.init_ui()
        self.load_roles()
    
    def init_ui(self):
        layout = QVBoxLayout(self)
        
        # 使用分割器将角色列表和权限树分开
        splitter = QSplitter(Qt.Horizontal)
        
        # 左侧：角色列表
        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)
        
        role_group = QGroupBox("角色列表")
        role_layout = QVBoxLayout(role_group)
        
        self.role_table = QTableWidget()
        self.role_table.setColumnCount(3)
        self.role_table.setHorizontalHeaderLabels(["角色名称", "角色编码", "状态"])
        
        header = self.role_table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.Stretch)
        
        self.role_table.setSelectionMode(QTableWidget.SingleSelection)
        self.role_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.role_table.itemSelectionChanged.connect(self.on_role_selected)
        
        role_layout.addWidget(self.role_table)
        
        # 角色操作按钮
        role_btn_layout = QHBoxLayout()
        
        self.add_role_btn = QPushButton("新增角色")
        self.add_role_btn.clicked.connect(self.add_role)
        role_btn_layout.addWidget(self.add_role_btn)
        
        self.edit_role_info_btn = QPushButton("编辑角色")
        self.edit_role_info_btn.clicked.connect(self.edit_role_info)
        role_btn_layout.addWidget(self.edit_role_info_btn)
        
        self.toggle_role_btn = QPushButton("停用/启用")
        self.toggle_role_btn.clicked.connect(self.toggle_role_status)
        role_btn_layout.addWidget(self.toggle_role_btn)
        
        self.edit_role_btn = QPushButton("编辑权限")
        self.edit_role_btn.clicked.connect(self.edit_role_permissions)
        role_btn_layout.addWidget(self.edit_role_btn)
        
        self.refresh_role_btn = QPushButton("刷新")
        self.refresh_role_btn.clicked.connect(self.load_roles)
        role_btn_layout.addWidget(self.refresh_role_btn)
        
        role_btn_layout.addStretch()
        role_layout.addLayout(role_btn_layout)
        
        left_layout.addWidget(role_group)
        
        # 右侧：权限树
        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)
        
        perm_group = QGroupBox("权限配置")
        perm_layout = QVBoxLayout(perm_group)
        
        self.perm_tree = QTreeWidget()
        self.perm_tree.setHeaderLabels(["权限名称", "权限编码"])
        self.perm_tree.setColumnCount(2)
        
        # 设置列宽：权限名称列更宽，权限编码列适中
        header = self.perm_tree.header()
        header.setSectionResizeMode(0, QHeaderView.Stretch)  # 权限名称列自适应拉伸
        header.setSectionResizeMode(1, QHeaderView.Interactive)  # 权限编码列可调整
        self.perm_tree.setColumnWidth(0, 300)  # 权限名称列默认宽度
        self.perm_tree.setColumnWidth(1, 200)  # 权限编码列默认宽度
        
        # 设置复选框
        self.perm_tree.setItemsExpandable(True)
        
        # 添加悬浮提示功能
        self.perm_tree.setMouseTracking(True)
        self.perm_tree.itemEntered.connect(self.on_item_hover)
        
        perm_layout.addWidget(self.perm_tree)
        
        # 权限操作按钮
        perm_btn_layout = QHBoxLayout()
        
        self.save_perm_btn = QPushButton("保存权限")
        self.save_perm_btn.clicked.connect(self.save_permissions)
        perm_btn_layout.addWidget(self.save_perm_btn)
        
        self.expand_btn = QPushButton("展开全部")
        self.expand_btn.clicked.connect(self.perm_tree.expandAll)
        perm_btn_layout.addWidget(self.expand_btn)
        
        self.collapse_btn = QPushButton("折叠全部")
        self.collapse_btn.clicked.connect(self.perm_tree.collapseAll)
        perm_btn_layout.addWidget(self.collapse_btn)
        
        perm_btn_layout.addStretch()
        perm_layout.addLayout(perm_btn_layout)
        
        right_layout.addWidget(perm_group)
        
        # 添加到分割器
        splitter.addWidget(left_widget)
        splitter.addWidget(right_widget)
        
        # 设置分割比例
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 2)
        
        layout.addWidget(splitter)
    
    def load_roles(self):
        """加载角色列表"""
        try:
            roles = self.permission_service.get_all_roles()
            
            self.role_table.setRowCount(len(roles))
            
            for i, role in enumerate(roles):
                self.role_table.setItem(i, 0, QTableWidgetItem(role['role_name']))
                self.role_table.setItem(i, 1, QTableWidgetItem(role['role_code']))
                
                status = role['status'] or 'active'
                status_text = "启用" if status == 'active' else "禁用"
                status_item = QTableWidgetItem(status_text)
                if status == 'disabled':
                    status_item.setForeground(Qt.red)
                self.role_table.setItem(i, 2, status_item)
            
        except Exception as e:
            logging.error(f"加载角色列表失败: {e}")
            QMessageBox.warning(self, "错误", f"加载角色列表失败: {e}")
    
    def on_item_hover(self, item: QTreeWidgetItem):
        """悬浮提示：显示完整的权限名称和权限编码"""
        perm_name = item.text(0)
        perm_code = item.text(1)
        tooltip = f"权限名称: {perm_name}\n权限编码: {perm_code}"
        item.setToolTip(0, tooltip)
        item.setToolTip(1, tooltip)
    
    def on_role_selected(self):
        """角色选择变化时加载权限"""
        selected_rows = self.role_table.selectedItems()
        if not selected_rows:
            return
        
        row = selected_rows[0].row()
        role_code_item = self.role_table.item(row, 1)
        self.current_role_code = role_code_item.text() if role_code_item else None
        
        if self.current_role_code:
            self.load_permissions(self.current_role_code)
    
    def load_permissions(self, role_code: str):
        """加载角色的权限"""
        try:
            # 清空权限树
            self.perm_tree.clear()
            
            # 获取权限树结构
            permission_tree = self.permission_service.get_permission_tree()
            
            # 获取角色已有的权限
            role_permissions = set(self.permission_service.get_role_permissions(role_code))
            
            # 构建权限树
            for menu_node in permission_tree:
                menu_item = QTreeWidgetItem(self.perm_tree)
                menu_item.setText(0, menu_node['name'])
                menu_item.setText(1, menu_node['code'])
                menu_item.setCheckState(0, Qt.Checked if menu_node['code'] in role_permissions else Qt.Unchecked)
                
                # 添加悬浮提示
                tooltip = f"权限名称: {menu_node['name']}\n权限编码: {menu_node['code']}"
                menu_item.setToolTip(0, tooltip)
                menu_item.setToolTip(1, tooltip)
                
                # 添加操作权限子节点
                for op_node in menu_node.get('children', []):
                    op_item = QTreeWidgetItem(menu_item)
                    op_item.setText(0, op_node['name'])
                    op_item.setText(1, op_node['code'])
                    op_item.setCheckState(0, Qt.Checked if op_node['code'] in role_permissions else Qt.Unchecked)
                    
                    # 添加悬浮提示
                    op_tooltip = f"权限名称: {op_node['name']}\n权限编码: {op_node['code']}"
                    op_item.setToolTip(0, op_tooltip)
                    op_item.setToolTip(1, op_tooltip)
            
            self.perm_tree.expandAll()
            
        except Exception as e:
            logging.error(f"加载权限失败: {e}")
            QMessageBox.warning(self, "错误", f"加载权限失败: {e}")
    
    def edit_role_permissions(self):
        """编辑角色权限"""
        if not self.current_role_code:
            QMessageBox.warning(self, "提示", "请先选择要编辑的角色")
            return
        
        # 权限检查
        if not self.permission_checker.check_permission(PermissionCodes.OP_ROLE_ASSIGN_PERMISSIONS, self):
            return
        
        # 检查是否是系统内置角色
        roles = self.permission_service.get_all_roles()
        for role in roles:
            if role['role_code'] == self.current_role_code and role['is_system_role'] == 1:
                QMessageBox.warning(self, "提示", "系统内置角色权限不可修改")
                return
        
        # 权限树已经加载，用户可以勾选权限
        QMessageBox.information(self, "提示", "请在右侧权限树中勾选需要的权限，然后点击保存")
    
    def save_permissions(self):
        """保存权限配置"""
        if not self.current_role_code:
            QMessageBox.warning(self, "提示", "请先选择角色")
            return
        
        # 权限检查
        if not self.permission_checker.check_permission(PermissionCodes.OP_ROLE_ASSIGN_PERMISSIONS, self):
            return
        
        # 检查是否是系统内置角色
        roles = self.permission_service.get_all_roles()
        for role in roles:
            if role['role_code'] == self.current_role_code and role['is_system_role'] == 1:
                QMessageBox.warning(self, "提示", "系统内置角色权限不可修改")
                return
        
        # 获取原有权限（用于对比）
        old_permissions = set(self.permission_service.get_role_permissions(self.current_role_code))
        
        # 收集勾选的权限
        selected_permissions = []
        
        root = self.perm_tree.invisibleRootItem()
        for i in range(root.childCount()):
            menu_item = root.child(i)
            
            # 如果菜单勾选，添加菜单权限
            if menu_item.checkState(0) == Qt.Checked:
                selected_permissions.append(menu_item.text(1))
            
            # 检查操作权限
            for j in range(menu_item.childCount()):
                op_item = menu_item.child(j)
                if op_item.checkState(0) == Qt.Checked:
                    selected_permissions.append(op_item.text(1))
        
        new_permissions = set(selected_permissions)
        
        # 计算变更
        added_permissions = list(new_permissions - old_permissions)
        removed_permissions = list(old_permissions - new_permissions)
        
        try:
            # 更新角色权限
            success = self.permission_service.update_role_permissions(
                self.current_role_code,
                selected_permissions
            )
            
            if success:
                # 记录详细操作日志（包含变更前后对比）
                self.permission_service.log_operation(
                    username=self.current_username,
                    operation_type='role_permission_update',
                    operation_desc=f'更新角色权限: {self.current_role_code}',
                    target_type='role',
                    target_id=self.current_role_code,
                    detail={
                        'old_permissions': list(old_permissions),
                        'new_permissions': selected_permissions,
                        'added_permissions': added_permissions,
                        'removed_permissions': removed_permissions,
                        'total_count': len(selected_permissions)
                    },
                    permission_code=PermissionCodes.OP_ROLE_ASSIGN_PERMISSIONS,
                    result='success'
                )
                
                QMessageBox.information(self, "成功", "权限配置已保存")
            else:
                # 记录失败日志
                self.permission_service.log_operation(
                    username=self.current_username,
                    operation_type='role_permission_update',
                    operation_desc=f'更新角色权限失败: {self.current_role_code}',
                    target_type='role',
                    target_id=self.current_role_code,
                    detail={'error': '数据库更新失败'},
                    permission_code=PermissionCodes.OP_ROLE_ASSIGN_PERMISSIONS,
                    result='fail'
                )
                QMessageBox.warning(self, "错误", "保存权限配置失败")
            
        except Exception as e:
            logging.error(f"保存权限失败: {e}")
            # 记录失败日志
            self.permission_service.log_operation(
                username=self.current_username,
                operation_type='role_permission_update',
                operation_desc=f'更新角色权限失败: {self.current_role_code}',
                target_type='role',
                target_id=self.current_role_code,
                detail={'error': str(e)},
                permission_code=PermissionCodes.OP_ROLE_ASSIGN_PERMISSIONS,
                result='fail'
            )
            QMessageBox.warning(self, "错误", f"保存权限失败: {e}")
    
    def add_role(self):
        """新增角色"""
        # 权限检查
        if not self.permission_checker.check_permission(PermissionCodes.OP_ROLE_ASSIGN_PERMISSIONS, self):
            return
        
        dialog = RoleEditDialog(self, None)
        if dialog.exec() == QDialog.Accepted:
            role_code, role_name, description = dialog.get_data()
            
            if self.permission_service.create_role(role_code, role_name, description):
                self.permission_service.log_operation(
                    username=self.current_username,
                    operation_type='role_create',
                    operation_desc=f'创建角色: {role_name}',
                    target_type='role',
                    target_id=role_code,
                    detail={'role_name': role_name, 'description': description},
                    permission_code=PermissionCodes.OP_ROLE_ASSIGN_PERMISSIONS,
                    result='success'
                )
                QMessageBox.information(self, "成功", "角色创建成功")
                self.load_roles()
            else:
                QMessageBox.warning(self, "错误", "角色创建失败，可能角色编码已存在")
    
    def edit_role_info(self):
        """编辑角色信息"""
        if not self.current_role_code:
            QMessageBox.warning(self, "提示", "请先选择要编辑的角色")
            return
        
        # 权限检查
        if not self.permission_checker.check_permission(PermissionCodes.OP_ROLE_ASSIGN_PERMISSIONS, self):
            return
        
        # 获取当前角色信息
        roles = self.permission_service.get_all_roles()
        current_role = None
        for role in roles:
            if role['role_code'] == self.current_role_code:
                current_role = role
                break
        
        if not current_role:
            QMessageBox.warning(self, "错误", "未找到角色信息")
            return
        
        # 检查是否是系统内置角色
        if current_role['is_system_role'] == 1:
            QMessageBox.warning(self, "提示", "系统内置角色信息不可修改")
            return
        
        dialog = RoleEditDialog(self, current_role)
        if dialog.exec() == QDialog.Accepted:
            role_code, role_name, description = dialog.get_data()
            
            if self.permission_service.update_role(role_code, role_name, description):
                self.permission_service.log_operation(
                    username=self.current_username,
                    operation_type='role_update',
                    operation_desc=f'更新角色信息: {role_name}',
                    target_type='role',
                    target_id=role_code,
                    detail={'role_name': role_name, 'description': description},
                    permission_code=PermissionCodes.OP_ROLE_ASSIGN_PERMISSIONS,
                    result='success'
                )
                QMessageBox.information(self, "成功", "角色信息更新成功")
                self.load_roles()
            else:
                QMessageBox.warning(self, "错误", "角色信息更新失败")
    
    def toggle_role_status(self):
        """停用/启用角色"""
        if not self.current_role_code:
            QMessageBox.warning(self, "提示", "请先选择要操作的角色")
            return
        
        # 权限检查
        if not self.permission_checker.check_permission(PermissionCodes.OP_ROLE_ASSIGN_PERMISSIONS, self):
            return
        
        # 获取当前角色信息
        roles = self.permission_service.get_all_roles()
        current_role = None
        for role in roles:
            if role['role_code'] == self.current_role_code:
                current_role = role
                break
        
        if not current_role:
            QMessageBox.warning(self, "错误", "未找到角色信息")
            return
        
        current_status = current_role['status'] or 'active'
        
        if current_status == 'active':
            # 停用角色
            reply = QMessageBox.question(
                self, "确认", f"确定要停用角色 {current_role['role_name']}？\n停用后，拥有该角色的用户将不再获得该角色权限。",
                QMessageBox.Yes | QMessageBox.No
            )
            if reply == QMessageBox.Yes:
                if self.permission_service.disable_role(self.current_role_code):
                    self.permission_service.log_operation(
                        username=self.current_username,
                        operation_type='role_disable',
                        operation_desc=f'停用角色: {current_role["role_name"]}',
                        target_type='role',
                        target_id=self.current_role_code,
                        detail={'role_name': current_role['role_name']},
                        permission_code=PermissionCodes.OP_ROLE_ASSIGN_PERMISSIONS,
                        result='success'
                    )
                    QMessageBox.information(self, "成功", "角色已停用")
                    self.load_roles()
                else:
                    QMessageBox.warning(self, "错误", "角色停用失败，可能是系统内置角色")
        else:
            # 启用角色
            if self.permission_service.enable_role(self.current_role_code):
                self.permission_service.log_operation(
                    username=self.current_username,
                    operation_type='role_enable',
                    operation_desc=f'启用角色: {current_role["role_name"]}',
                    target_type='role',
                    target_id=self.current_role_code,
                    detail={'role_name': current_role['role_name']},
                    permission_code=PermissionCodes.OP_ROLE_ASSIGN_PERMISSIONS,
                    result='success'
                )
                QMessageBox.information(self, "成功", "角色已启用")
                self.load_roles()
            else:
                QMessageBox.warning(self, "错误", "角色启用失败")


class RoleEditDialog(QDialog):
    """角色编辑对话框"""
    
    def __init__(self, parent, role_data: Dict = None):
        super().__init__(parent)
        self.role_data = role_data
        self.setWindowTitle("角色编辑")
        self.setMinimumWidth(400)
        
        self.init_ui()
    
    def init_ui(self):
        layout = QFormLayout(self)
        
        # 角色编码
        self.role_code_edit = QLineEdit()
        if self.role_data:
            self.role_code_edit.setText(self.role_data['role_code'])
            self.role_code_edit.setReadOnly(True)  # 编辑时不允许修改角色编码
        layout.addRow("角色编码:", self.role_code_edit)
        
        # 角色名称
        self.role_name_edit = QLineEdit()
        if self.role_data:
            self.role_name_edit.setText(self.role_data['role_name'])
        layout.addRow("角色名称:", self.role_name_edit)
        
        # 角色说明
        self.description_edit = QLineEdit()
        if self.role_data and self.role_data['description']:
            self.description_edit.setText(self.role_data['description'])
        layout.addRow("角色说明:", self.description_edit)
        
        # 按钮
        btn_layout = QHBoxLayout()
        
        save_btn = QPushButton("保存")
        save_btn.clicked.connect(self.accept)
        btn_layout.addWidget(save_btn)
        
        cancel_btn = QPushButton("取消")
        cancel_btn.clicked.connect(self.reject)
        btn_layout.addWidget(cancel_btn)
        
        layout.addRow(btn_layout)
    
    def get_data(self) -> tuple:
        """获取对话框数据"""
        return (
            self.role_code_edit.text().strip(),
            self.role_name_edit.text().strip(),
            self.description_edit.text().strip()
        )
    
    def accept(self):
        """验证并接受"""
        role_code = self.role_code_edit.text().strip()
        role_name = self.role_name_edit.text().strip()
        
        if not role_code:
            QMessageBox.warning(self, "提示", "角色编码不能为空")
            return
        
        if not role_name:
            QMessageBox.warning(self, "提示", "角色名称不能为空")
            return
        
        # 角色编码格式检查
        if not role_code.replace('_', '').replace('-', '').isalnum():
            QMessageBox.warning(self, "提示", "角色编码只能包含字母、数字、下划线和横线")
            return
        
        super().accept()