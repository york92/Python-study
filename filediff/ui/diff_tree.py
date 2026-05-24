# -*- coding: utf-8 -*-
"""
差异结果树形控件 v2
- 右键菜单补充"在新窗口打开差异"
- 单击差异文件触发内嵌预览（item_clicked 信号）
- 双击仍可触发（兼容旧逻辑）
"""

from PyQt5.QtWidgets import (
    QTreeWidget, QTreeWidgetItem, QAbstractItemView,
    QMenu, QAction, QMessageBox, QInputDialog
)
from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtGui import QColor, QBrush, QFont

from core.diff_engine import DiffNode, DiffStatus
from core.sync_ops import (
    copy_left_to_right, copy_right_to_left,
    delete_file, rename_file, SyncError
)

# ── 颜色 / 标签 / 图标 ──────────────────────────────────────────
STATUS_COLORS = {
    DiffStatus.IDENTICAL:    ("#4ec9b0", "#4ec9b0"),
    DiffStatus.MODIFIED:     ("#ffd700", "#ffd700"),
    DiffStatus.LEFT_ONLY:    ("#569cd6", "#4a4a4a"),
    DiffStatus.RIGHT_ONLY:   ("#4a4a4a", "#569cd6"),
    DiffStatus.TYPE_CHANGED: ("#ce9178", "#ce9178"),
}
STATUS_LABELS = {
    DiffStatus.IDENTICAL:    "相同",
    DiffStatus.MODIFIED:     "不同",
    DiffStatus.LEFT_ONLY:    "仅左侧",
    DiffStatus.RIGHT_ONLY:   "仅右侧",
    DiffStatus.TYPE_CHANGED: "类型变",
}
STATUS_ICONS = {
    DiffStatus.IDENTICAL:    "✓",
    DiffStatus.MODIFIED:     "≠",
    DiffStatus.LEFT_ONLY:    "←",
    DiffStatus.RIGHT_ONLY:   "→",
    DiffStatus.TYPE_CHANGED: "⚠",
}

COL_NAME, COL_STATUS, COL_LEFT, COL_RIGHT = 0, 1, 2, 3

MENU_QSS = """
QMenu {
    background-color: #252526;
    color: #d4d4d4;
    border: 1px solid #454545;
    font-size: 13px;
    padding: 4px 0;
}
QMenu::item { padding: 5px 24px 5px 12px; }
QMenu::item:selected { background-color: #094771; }
QMenu::separator {
    background-color: #3c3c3c;
    height: 1px;
    margin: 4px 0;
}
"""


class DiffTreeWidget(QTreeWidget):
    """差异结果树"""
    item_double_clicked = pyqtSignal(object)   # DiffNode — 双击（内嵌预览）
    item_open_window    = pyqtSignal(object)   # DiffNode — 右键"新窗口打开"
    tree_changed        = pyqtSignal()         # 同步操作后需要重新比较

    def __init__(self, parent=None):
        super().__init__(parent)
        self._build_ui()

    def _build_ui(self):
        self.setColumnCount(4)
        self.setHeaderLabels(["名称", "状态", "左侧路径", "右侧路径"])
        self.setAlternatingRowColors(True)
        self.setSelectionMode(QAbstractItemView.SingleSelection)
        self.setExpandsOnDoubleClick(False)
        self.setContextMenuPolicy(Qt.CustomContextMenu)
        self.customContextMenuRequested.connect(self._show_context_menu)
        self.itemDoubleClicked.connect(self._on_double_click)

        self.setColumnWidth(COL_NAME,   220)
        self.setColumnWidth(COL_STATUS, 72)
        self.setColumnWidth(COL_LEFT,   240)
        self.setColumnWidth(COL_RIGHT,  240)

        self.setStyleSheet("""
            QTreeWidget {
                background-color: #1e1e1e;
                color: #d4d4d4;
                border: none;
                border-right: 1px solid #3c3c3c;
                font-family: Consolas, 'Courier New', monospace;
                font-size: 13px;
                outline: none;
            }
            QTreeWidget::item {
                padding: 3px 4px;
                border-bottom: 1px solid #252526;
            }
            QTreeWidget::item:selected {
                background-color: #094771;
                color: #ffffff;
            }
            QTreeWidget::item:hover:!selected {
                background-color: #2a2d2e;
            }
            QHeaderView::section {
                background-color: #252526;
                color: #aaaaaa;
                padding: 5px 8px;
                border: none;
                border-right: 1px solid #3c3c3c;
                border-bottom: 1px solid #3c3c3c;
                font-size: 12px;
                font-weight: bold;
            }
        """)

    # ── 加载节点 ────────────────────────────────────────────────────
    def load_nodes(self, nodes: list, show_identical: bool = False):
        self.clear()
        for node in nodes:
            item = self._make_item(node, show_identical)
            if item:
                self.addTopLevelItem(item)
        self.expandAll()

    def _make_item(self, node: DiffNode, show_identical: bool):
        # 过滤相同项
        if not show_identical:
            if not node.is_dir and node.status == DiffStatus.IDENTICAL:
                return None
            if (node.is_dir
                    and node.status == DiffStatus.IDENTICAL
                    and not any(c.recursive_has_diff() for c in node.children)):
                return None

        item = QTreeWidgetItem()
        item.setData(COL_NAME, Qt.UserRole, node)

        # 名称
        icon = "📁 " if node.is_dir else "📄 "
        item.setText(COL_NAME, icon + node.name)

        # 状态
        si = STATUS_ICONS.get(node.status, "?")
        sl = STATUS_LABELS.get(node.status, "")
        item.setText(COL_STATUS, f"{si}  {sl}")

        # 路径
        item.setText(COL_LEFT,  node.left_path  or "—")
        item.setText(COL_RIGHT, node.right_path or "—")

        # 颜色
        lc, rc = STATUS_COLORS.get(node.status, ("#d4d4d4", "#d4d4d4"))
        for col in (COL_NAME, COL_STATUS, COL_LEFT):
            item.setForeground(col, QBrush(QColor(lc)))
        item.setForeground(COL_RIGHT, QBrush(QColor(rc)))

        # 目录加粗
        if node.is_dir:
            f = item.font(COL_NAME)
            f.setBold(True)
            item.setFont(COL_NAME, f)

        # 子节点
        for child in node.children:
            ci = self._make_item(child, show_identical)
            if ci:
                item.addChild(ci)

        return item

    # ── 点击事件 ────────────────────────────────────────────────────
    def _on_double_click(self, item: QTreeWidgetItem, _col: int):
        node: DiffNode = item.data(COL_NAME, Qt.UserRole)
        if node and not node.is_dir:
            self.item_double_clicked.emit(node)

    def _selected_node(self) -> DiffNode | None:
        items = self.selectedItems()
        return items[0].data(COL_NAME, Qt.UserRole) if items else None

    # ── 右键菜单 ────────────────────────────────────────────────────
    def _show_context_menu(self, pos):
        node = self._selected_node()
        if not node:
            return

        menu = QMenu(self)
        menu.setStyleSheet(MENU_QSS)

        # ── 查看差异（文件才有）──
        if not node.is_dir and node.status != DiffStatus.IDENTICAL:
            act_view = QAction("🔍  在新窗口查看差异", self)
            act_view.triggered.connect(lambda: self.item_open_window.emit(node))
            menu.addAction(act_view)
            menu.addSeparator()

        # ── 同步操作 ──
        if node.left_path and node.right_path:
            a1 = QAction("▶  左侧 → 右侧（覆盖）", self)
            a2 = QAction("◀  右侧 → 左侧（覆盖）", self)
            a1.triggered.connect(lambda: self._sync(node, "l2r"))
            a2.triggered.connect(lambda: self._sync(node, "r2l"))
            menu.addActions([a1, a2])

        elif node.left_path and not node.right_path:
            ac = QAction("▶  复制到右侧", self)
            ad = QAction("🗑  删除左侧文件", self)
            ac.triggered.connect(lambda: self._sync(node, "l2r"))
            ad.triggered.connect(lambda: self._delete(node, "left"))
            menu.addActions([ac, ad])

        elif node.right_path and not node.left_path:
            ac = QAction("◀  复制到左侧", self)
            ad = QAction("🗑  删除右侧文件", self)
            ac.triggered.connect(lambda: self._sync(node, "r2l"))
            ad.triggered.connect(lambda: self._delete(node, "right"))
            menu.addActions([ac, ad])

        menu.addSeparator()

        # ── 重命名 ──
        if node.left_path:
            ar = QAction("✏  重命名左侧", self)
            ar.triggered.connect(lambda: self._rename(node, "left"))
            menu.addAction(ar)
        if node.right_path:
            ar2 = QAction("✏  重命名右侧", self)
            ar2.triggered.connect(lambda: self._rename(node, "right"))
            menu.addAction(ar2)

        menu.exec_(self.mapToGlobal(pos))

    # ── 同步 / 删除 / 重命名 ────────────────────────────────────────
    def _sync(self, node: DiffNode, direction: str):
        try:
            if direction == "l2r":
                target = node.right_path or self._infer_path(node, "right")
                if not target:
                    QMessageBox.warning(self, "警告", "无法确定右侧目标路径"); return
                copy_left_to_right(node.left_path, target)
            else:
                target = node.left_path or self._infer_path(node, "left")
                if not target:
                    QMessageBox.warning(self, "警告", "无法确定左侧目标路径"); return
                copy_right_to_left(node.right_path, target)
            QMessageBox.information(self, "完成", "同步成功！")
            self.tree_changed.emit()
        except SyncError as e:
            QMessageBox.critical(self, "错误", str(e))

    def _delete(self, node: DiffNode, side: str):
        path = node.left_path if side == "left" else node.right_path
        label = "文件" if not node.is_dir else "目录"
        if QMessageBox.question(
            self, "确认删除", f"确定删除{label}？\n{path}",
            QMessageBox.Yes | QMessageBox.No
        ) == QMessageBox.Yes:
            try:
                delete_file(path)
                self.tree_changed.emit()
            except SyncError as e:
                QMessageBox.critical(self, "错误", str(e))

    def _rename(self, node: DiffNode, side: str):
        path = node.left_path if side == "left" else node.right_path
        new_name, ok = QInputDialog.getText(self, "重命名", "新名称:", text=node.name)
        if ok and new_name.strip():
            try:
                rename_file(path, new_name.strip())
                self.tree_changed.emit()
            except SyncError as e:
                QMessageBox.critical(self, "错误", str(e))

    def _infer_path(self, node: DiffNode, side: str) -> str | None:
        """仅一侧存在时，从父节点推算另一侧路径"""
        parent_item = None
        it = self.invisibleRootItem()
        def find_parent(container, target_node):
            for i in range(container.childCount()):
                child = container.child(i)
                if child.data(COL_NAME, Qt.UserRole) is target_node:
                    return container
                found = find_parent(child, target_node)
                if found:
                    return found
            return None
        parent_item = find_parent(self.invisibleRootItem(), node)
        if parent_item and parent_item is not self.invisibleRootItem():
            pnode: DiffNode = parent_item.data(COL_NAME, Qt.UserRole)
            base = pnode.left_path if side == "left" else pnode.right_path
            if base:
                import os
                return os.path.join(base, node.name)
        return None
