from PySide6.QtWidgets import QTableWidget, QTableWidgetItem
from PySide6.QtGui import QColor, QBrush
from PySide6.QtCore import Qt


class TableHighlightHelper:
    
    HIGHLIGHT_ROW_COLOR = QColor("#E3F2FD")
    HIGHLIGHT_COL_COLOR = QColor("#FFF9C4")
    HIGHLIGHT_CELL_COLOR = QColor("#BBDEFB")
    
    def __init__(self, table: QTableWidget):
        self.table = table
        self.current_row = -1
        self.current_col = -1
        self._original_backgrounds = {}
        self._is_highlighting = False
        
        self.table.itemSelectionChanged.connect(self._on_selection_changed)
        self.table.currentItemChanged.connect(self._on_current_item_changed)
    
    def _on_selection_changed(self):
        if self._is_highlighting:
            return
        
        selected_items = self.table.selectedItems()
        if selected_items:
            item = selected_items[0]
            row = item.row()
            col = item.column()
            self._update_highlight(row, col)
    
    def _on_current_item_changed(self, current: QTableWidgetItem, previous: QTableWidgetItem):
        if self._is_highlighting:
            return
        
        if current:
            row = current.row()
            col = current.column()
            self._update_highlight(row, col)
    
    def _update_highlight(self, row: int, col: int):
        self._is_highlighting = True
        
        self._clear_previous_highlight()
        
        self.current_row = row
        self.current_col = col
        
        self._highlight_row(row)
        self._highlight_column(col)
        self._highlight_cell(row, col)
        
        self._is_highlighting = False
    
    def _clear_previous_highlight(self):
        if self.current_row < 0 or self.current_col < 0:
            return
        
        for col in range(self.table.columnCount()):
            item = self.table.item(self.current_row, col)
            if item:
                original_color = self._original_backgrounds.get((self.current_row, col))
                if original_color and original_color.isValid():
                    item.setBackground(QBrush(original_color))
                else:
                    item.setData(Qt.BackgroundRole, None)
        
        for row in range(self.table.rowCount()):
            item = self.table.item(row, self.current_col)
            if item:
                original_color = self._original_backgrounds.get((row, self.current_col))
                if original_color and original_color.isValid():
                    item.setBackground(QBrush(original_color))
                else:
                    item.setData(Qt.BackgroundRole, None)
        
        item = self.table.item(self.current_row, self.current_col)
        if item:
            original_color = self._original_backgrounds.get((self.current_row, self.current_col))
            if original_color and original_color.isValid():
                item.setBackground(QBrush(original_color))
            else:
                item.setData(Qt.BackgroundRole, None)
        
        self._original_backgrounds.clear()
    
    def _highlight_row(self, row: int):
        for col in range(self.table.columnCount()):
            item = self.table.item(row, col)
            if item:
                bg = item.background()
                original_color = bg.color() if bg.style() != Qt.NoBrush else QColor()
                self._original_backgrounds[(row, col)] = original_color
                item.setBackground(QBrush(self.HIGHLIGHT_ROW_COLOR))
    
    def _highlight_column(self, col: int):
        for row in range(self.table.rowCount()):
            item = self.table.item(row, col)
            if item:
                bg = item.background()
                original_color = bg.color() if bg.style() != Qt.NoBrush else QColor()
                self._original_backgrounds[(row, col)] = original_color
                item.setBackground(QBrush(self.HIGHLIGHT_COL_COLOR))
    
    def _highlight_cell(self, row: int, col: int):
        item = self.table.item(row, col)
        if item:
            bg = item.background()
            original_color = bg.color() if bg.style() != Qt.NoBrush else QColor()
            self._original_backgrounds[(row, col)] = original_color
            item.setBackground(QBrush(self.HIGHLIGHT_CELL_COLOR))
    
    def clear_highlight(self):
        self._clear_previous_highlight()
        self.current_row = -1
        self.current_col = -1


def enable_table_highlight(table: QTableWidget) -> TableHighlightHelper:
    return TableHighlightHelper(table)