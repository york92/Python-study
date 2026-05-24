# -*- coding: utf-8 -*-
"""
主窗口 v2
改动：
  1. PathSelector 支持拖拽、输入框变高、字体与菜单统一
  2. 单文件比较 → 比较完成后直接内嵌并排 DiffPanel（无需双击）
     目录比较 → 左侧树 + 右侧内嵌预览，点击差异行即时预览
"""

import os
from PyQt5.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLineEdit, QLabel, QFileDialog,
    QSplitter, QStatusBar, QProgressBar,
    QAction, QCheckBox, QMenu, QMessageBox,
    QFrame, QSizePolicy, QStackedWidget, QTextEdit
)
from PyQt5.QtCore import Qt, QSettings, QMimeData, pyqtSignal
from PyQt5.QtGui import QFont, QDragEnterEvent, QDropEvent

from core.diff_engine import DiffThread, DiffNode, DiffStatus
from ui.diff_tree import DiffTreeWidget
from ui.diff_viewer import DiffViewerWindow, DiffPanel   # DiffPanel: 新增可嵌入组件


# ─────────────────────────── 样式表 ───────────────────────────
DARK_QSS = """
QMainWindow, QWidget#central {
    background-color: #1e1e1e;
    color: #d4d4d4;
}
QMenuBar {
    background-color: #252526;
    color: #cccccc;
    font-size: 13px;
    border-bottom: 1px solid #3c3c3c;
}
QMenuBar::item { padding: 4px 10px; }
QMenuBar::item:selected { background-color: #094771; }
QMenu {
    background-color: #252526;
    color: #cccccc;
    font-size: 13px;
    border: 1px solid #454545;
}
QMenu::item { padding: 5px 24px; }
QMenu::item:selected { background-color: #094771; }

/* ── 路径输入框 ── */
QTextEdit#path_edit {
    background-color: #2d2d2d;
    color: #d4d4d4;
    border: 1px solid #555;
    padding: 6px 10px;
    border-radius: 4px;
    font-family: Consolas, "Courier New", monospace;
    font-size: 13px;
}
QTextEdit#path_edit:focus { border-color: #007acc; }

/* ── 通用按钮 ── */
QPushButton {
    background-color: #0e639c;
    color: white;
    border: none;
    padding: 6px 16px;
    border-radius: 3px;
    font-size: 13px;
    font-weight: bold;
}
QPushButton:hover  { background-color: #1177bb; }
QPushButton:pressed{ background-color: #0a4f7e; }
QPushButton:disabled{ background-color: #3c3c3c; color: #666; }

QPushButton#browse {
    background-color: #3a3d41;
    color: #d4d4d4;
    padding: 6px 12px;
    font-size: 13px;
    font-weight: normal;
}
QPushButton#browse:hover { background-color: #505357; }

QPushButton#compare_btn {
    background-color: #16825d;
    font-size: 14px;
    padding: 9px 32px;
    min-width: 130px;
}
QPushButton#compare_btn:hover { background-color: #1d9e72; }

QPushButton#stop_btn {
    background-color: #6b2020;
    font-size: 13px;
}
QPushButton#stop_btn:hover { background-color: #8b3030; }

/* ── 标签 ── */
QLabel#section_label {
    color: #9cdcfe;
    font-weight: bold;
    font-size: 13px;
    padding: 2px 0 4px 0;
}
QLabel#drop_hint {
    color: #666;
    font-size: 11px;
    padding: 0;
}

/* ── 进度条 ── */
QProgressBar {
    background-color: #3c3c3c;
    border: none;
    height: 4px;
}
QProgressBar::chunk { background-color: #007acc; }

/* ── 状态栏 ── */
QStatusBar {
    background-color: #007acc;
    color: white;
    font-size: 13px;
}
QStatusBar QLabel { color: white; }

/* ── 复选框 ── */
QCheckBox { color: #d4d4d4; font-size: 13px; }
QCheckBox::indicator {
    width: 14px; height: 14px;
    background-color: #3c3c3c;
    border: 1px solid #555;
    border-radius: 2px;
}
QCheckBox::indicator:checked { background-color: #007acc; border-color: #007acc; }

/* ── 分隔线 ── */
QFrame#hsep {
    background-color: #3c3c3c;
    max-height: 1px;
}

/* ── 空白提示区 ── */
QLabel#empty_hint {
    color: #444;
    font-size: 20px;
    qproperty-alignment: AlignCenter;
}
"""


# ─────────────────────────── 拖拽路径输入框 ───────────────────────────
class DropPathEdit(QTextEdit):
    """
    支持拖拽文件/文件夹的多行路径输入框。
    单行显示，高度固定，但支持水平滚动长路径。
    """
    path_changed = pyqtSignal(str)

    def __init__(self, placeholder: str = "", parent=None):
        super().__init__(parent)
        self.setObjectName("path_edit")
        self.setPlaceholderText(placeholder)
        self.setAcceptDrops(True)
        self.setLineWrapMode(QTextEdit.NoWrap)
        self.setFixedHeight(42)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.document().contentsChanged.connect(
            lambda: self.path_changed.emit(self.get_path())
        )

    def get_path(self) -> str:
        return self.toPlainText().strip()

    def set_path(self, path: str):
        self.setPlainText(path)
        # 光标移到末尾
        cur = self.textCursor()
        cur.movePosition(cur.End)
        self.setTextCursor(cur)

    # ── 拖拽支持 ──
    def dragEnterEvent(self, e: QDragEnterEvent):
        if e.mimeData().hasUrls():
            e.acceptProposedAction()
        else:
            super().dragEnterEvent(e)

    def dragMoveEvent(self, e):
        if e.mimeData().hasUrls():
            e.acceptProposedAction()

    def dropEvent(self, e: QDropEvent):
        urls = e.mimeData().urls()
        if urls:
            path = urls[0].toLocalFile()
            self.set_path(path)
            self.path_changed.emit(path)
            e.acceptProposedAction()
        else:
            super().dropEvent(e)


# ─────────────────────────── 路径选择组件 ───────────────────────────
class PathSelector(QWidget):
    """路径选择组件：标题 + 拖拽输入框 + 浏览按钮"""

    def __init__(self, label: str, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        title = QLabel(label)
        title.setObjectName("section_label")

        row = QHBoxLayout()
        row.setSpacing(6)

        self.path_edit = DropPathEdit("拖入文件/文件夹，或点击右侧按钮浏览…")

        btn_file   = QPushButton("📄 文件")
        btn_folder = QPushButton("📁 目录")
        for b in (btn_file, btn_folder):
            b.setObjectName("browse")
            b.setFixedHeight(42)
            b.setFixedWidth(80)

        row.addWidget(self.path_edit, 1)
        row.addWidget(btn_file)
        row.addWidget(btn_folder)

        layout.addWidget(title)
        layout.addLayout(row)

        btn_file.clicked.connect(self._browse_file)
        btn_folder.clicked.connect(self._browse_folder)

    def _browse_file(self):
        path, _ = QFileDialog.getOpenFileName(self, "选择文件")
        if path:
            self.path_edit.set_path(path)

    def _browse_folder(self):
        path = QFileDialog.getExistingDirectory(self, "选择文件夹")
        if path:
            self.path_edit.set_path(path)

    def get_path(self) -> str:
        return self.path_edit.get_path()

    def set_path(self, path: str):
        self.path_edit.set_path(path)


# ─────────────────────────── 空白提示页 ───────────────────────────
class EmptyHintWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        lbl = QLabel("选择路径后点击「开始比较」\n结果将在此处显示")
        lbl.setObjectName("empty_hint")
        layout.addWidget(lbl)
        self.setStyleSheet("background-color: #1a1a1a;")


# ─────────────────────────── 主窗口 ───────────────────────────
class MainWindow(QMainWindow):
    """FileDiff Pro 主窗口 v2"""

    def __init__(self):
        super().__init__()
        self.setWindowTitle("FileDiff Pro — 文件差异比较与合并工具")
        self.resize(1280, 800)
        self.setMinimumSize(900, 560)

        self._diff_thread: DiffThread | None = None
        self._settings = QSettings("FileDiff", "FileDiffPro")
        self._nodes: list = []
        self._inline_panel: DiffPanel | None = None   # 当前嵌入的 DiffPanel

        self.setStyleSheet(DARK_QSS)
        self._setup_menubar()
        self._setup_ui()
        self._restore_settings()

    # ── 菜单栏 ──────────────────────────────────────────────────────
    def _setup_menubar(self):
        mb = self.menuBar()

        file_menu = mb.addMenu("文件(&F)")
        act_swap  = QAction("⇄  交换左右路径", self)
        act_exit  = QAction("退出", self)
        act_swap.triggered.connect(self._swap_paths)
        act_exit.triggered.connect(self.close)
        file_menu.addAction(act_swap)
        file_menu.addSeparator()
        file_menu.addAction(act_exit)

        view_menu = mb.addMenu("视图(&V)")
        act_expand   = QAction("展开全部", self)
        act_collapse = QAction("折叠全部", self)
        act_expand.triggered.connect(
            lambda: self.diff_tree.expandAll() if hasattr(self, "diff_tree") else None
        )
        act_collapse.triggered.connect(
            lambda: self.diff_tree.collapseAll() if hasattr(self, "diff_tree") else None
        )
        view_menu.addActions([act_expand, act_collapse])

        help_menu = mb.addMenu("帮助(&H)")
        act_about = QAction("关于", self)
        act_about.triggered.connect(self._show_about)
        help_menu.addAction(act_about)

    # ── 界面构建 ─────────────────────────────────────────────────────
    def _setup_ui(self):
        central = QWidget()
        central.setObjectName("central")
        self.setCentralWidget(central)

        root = QVBoxLayout(central)
        root.setContentsMargins(12, 8, 12, 4)
        root.setSpacing(6)

        # ── 顶部：路径选择区 ──
        top = QWidget()
        top_layout = QVBoxLayout(top)
        top_layout.setContentsMargins(0, 0, 0, 0)
        top_layout.setSpacing(6)

        paths_row = QHBoxLayout()
        paths_row.setSpacing(8)
        self.left_sel  = PathSelector("◀  左侧  （基准）")
        self.right_sel = PathSelector("▶  右侧  （目标）")

        swap_btn = QPushButton("⇄")
        swap_btn.setObjectName("browse")
        swap_btn.setFixedSize(38, 42)
        swap_btn.setToolTip("交换左右路径")
        swap_btn.clicked.connect(self._swap_paths)

        paths_row.addWidget(self.left_sel, 1)
        paths_row.addWidget(swap_btn)
        paths_row.addWidget(self.right_sel, 1)
        top_layout.addLayout(paths_row)

        # 选项行
        ctrl_row = QHBoxLayout()
        self.chk_show_identical = QCheckBox("显示相同文件")
        self.chk_show_identical.setChecked(False)
        self.chk_show_identical.stateChanged.connect(self._on_filter_changed)

        self.compare_btn = QPushButton("▶  开始比较")
        self.compare_btn.setObjectName("compare_btn")
        self.compare_btn.clicked.connect(self._start_compare)

        self.stop_btn = QPushButton("■  停止")
        self.stop_btn.setObjectName("stop_btn")
        self.stop_btn.setEnabled(False)
        self.stop_btn.clicked.connect(self._stop_compare)

        ctrl_row.addWidget(self.chk_show_identical)
        ctrl_row.addStretch()
        ctrl_row.addWidget(self.stop_btn)
        ctrl_row.addWidget(self.compare_btn)
        top_layout.addLayout(ctrl_row)

        root.addWidget(top)

        # 分隔线
        sep = QFrame(); sep.setObjectName("hsep"); sep.setFrameShape(QFrame.HLine)
        root.addWidget(sep)

        # ── 主体：水平 Splitter（树 | 内容区）──
        self._body_splitter = QSplitter(Qt.Horizontal)
        self._body_splitter.setStyleSheet(
            "QSplitter::handle { background:#3c3c3c; width:3px; }"
        )

        # 左：差异树（目录模式时可见）
        self.diff_tree = DiffTreeWidget()
        self.diff_tree.item_double_clicked.connect(self._show_inline_diff)
        self.diff_tree.item_open_window.connect(self._open_diff_window)
        self.diff_tree.itemClicked.connect(self._on_tree_item_clicked)
        self.diff_tree.tree_changed.connect(self._start_compare)
        self.diff_tree.setMinimumWidth(220)

        # 右：内容区（Stacked：空白提示 / 内嵌 DiffPanel）
        self._content_stack = QStackedWidget()
        self._content_stack.addWidget(EmptyHintWidget())   # index 0: 空白

        self._body_splitter.addWidget(self.diff_tree)
        self._body_splitter.addWidget(self._content_stack)
        self._body_splitter.setSizes([300, 980])

        root.addWidget(self._body_splitter, 1)

        # 进度条
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        self.progress_bar.setFixedHeight(4)
        root.addWidget(self.progress_bar)

        # 状态栏
        self.status_bar = QStatusBar()
        self.status_bar.showMessage('就绪 — 选择路径后点击"开始比较"')
        self.setStatusBar(self.status_bar)

        self._stats_label = QLabel("")
        self._stats_label.setStyleSheet("color:white; font-size:12px; padding-right:8px;")
        self.status_bar.addPermanentWidget(self._stats_label)

    # ── 树节点点击（目录模式：即时预览）──────────────────────────────
    def _on_tree_item_clicked(self, item, col):
        node: DiffNode = item.data(0, Qt.UserRole)
        if node and not node.is_dir and node.status != DiffStatus.IDENTICAL:
            self._show_inline_diff(node)

    # ── 显示内嵌差异面板 ──────────────────────────────────────────────
    def _show_inline_diff(self, node: DiffNode):
        from core.diff_engine import is_text_file
        left_ok  = node.left_path  and os.path.isfile(node.left_path)
        right_ok = node.right_path and os.path.isfile(node.right_path)

        if left_ok and not is_text_file(node.left_path):
            left_ok = False
        if right_ok and not is_text_file(node.right_path):
            right_ok = False

        if not left_ok and not right_ok:
            self.status_bar.showMessage("二进制文件，无法显示文本差异")
            return

        # 移除旧面板
        self._remove_inline_panel()

        panel = DiffPanel(node, parent=None)
        self._inline_panel = panel
        self._content_stack.addWidget(panel)
        self._content_stack.setCurrentWidget(panel)

        # 目录模式时树依然可见；单文件模式树隐藏（已在 _on_finished 处理）

    def _remove_inline_panel(self):
        if self._inline_panel is not None:
            self._content_stack.removeWidget(self._inline_panel)
            self._inline_panel.deleteLater()
            self._inline_panel = None

    def _open_diff_window(self, node: DiffNode):
        """右键菜单：在独立弹窗中查看差异"""
        from core.diff_engine import is_text_file
        if (node.left_path and not is_text_file(node.left_path) and
                node.right_path and not is_text_file(node.right_path)):
            QMessageBox.information(self, "提示", "该文件为二进制，无法进行文本差异查看")
            return
        win = DiffViewerWindow(node, self)
        win.show()
        # 保持引用防止被 GC
        if not hasattr(self, "_open_windows"):
            self._open_windows = []
        self._open_windows = [w for w in self._open_windows if w.isVisible()]
        self._open_windows.append(win)

    # ── 比较逻辑 ─────────────────────────────────────────────────────
    def _start_compare(self):
        left  = self.left_sel.get_path()
        right = self.right_sel.get_path()

        if not left or not right:
            self.status_bar.showMessage("⚠ 请先填写左侧和右侧路径"); return
        if not os.path.exists(left):
            self.status_bar.showMessage(f"⚠ 左侧路径不存在: {left}"); return
        if not os.path.exists(right):
            self.status_bar.showMessage(f"⚠ 右侧路径不存在: {right}"); return

        if self._diff_thread and self._diff_thread.isRunning():
            self._diff_thread.abort()
            self._diff_thread.wait(2000)

        self._remove_inline_panel()
        self._content_stack.setCurrentIndex(0)   # 空白提示
        self.diff_tree.clear()
        self.progress_bar.setValue(0)
        self.progress_bar.setVisible(True)
        self.compare_btn.setEnabled(False)
        self.stop_btn.setEnabled(True)
        self._stats_label.setText("")
        self._nodes = []

        self._diff_thread = DiffThread(left, right, self)
        self._diff_thread.progress.connect(self.progress_bar.setValue)
        self._diff_thread.status_msg.connect(self.status_bar.showMessage)
        self._diff_thread.result.connect(self._on_result)
        self._diff_thread.error.connect(self._on_error)
        self._diff_thread.finished_ok.connect(self._on_finished)
        self._diff_thread.start()
        self._save_settings()

    def _stop_compare(self):
        if self._diff_thread:
            self._diff_thread.abort()
        self.compare_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
        self.progress_bar.setVisible(False)
        self.status_bar.showMessage("已停止")

    def _on_result(self, nodes: list):
        self._nodes = nodes
        show_ident = self.chk_show_identical.isChecked()
        self.diff_tree.load_nodes(nodes, show_identical=show_ident)

    def _on_error(self, msg: str):
        self.status_bar.showMessage(f"错误: {msg}")
        self.compare_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
        self.progress_bar.setVisible(False)

    def _on_finished(self):
        self.compare_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
        self.progress_bar.setVisible(False)

        left  = self.left_sel.get_path()
        right = self.right_sel.get_path()
        is_single_file = os.path.isfile(left) and os.path.isfile(right)

        if is_single_file:
            # ── 单文件：隐藏左侧树，直接显示差异面板 ──
            self.diff_tree.setVisible(False)
            self._body_splitter.setSizes([0, 1])
            if self._nodes:
                self._show_inline_diff(self._nodes[0])
        else:
            # ── 目录：树可见，右侧等待点击 ──
            self.diff_tree.setVisible(True)
            self._body_splitter.setSizes([300, 980])
            # 自动选中并预览第一个差异文件
            self._auto_preview_first_diff()

        # 统计
        total = modified = left_only = right_only = identical = 0
        def count(nl):
            nonlocal total, modified, left_only, right_only, identical
            for n in nl:
                if not n.is_dir:
                    total += 1
                    if   n.status == DiffStatus.MODIFIED:    modified  += 1
                    elif n.status == DiffStatus.LEFT_ONLY:   left_only  += 1
                    elif n.status == DiffStatus.RIGHT_ONLY:  right_only += 1
                    elif n.status == DiffStatus.IDENTICAL:   identical  += 1
                count(n.children)
        count(self._nodes)

        self.status_bar.showMessage("比较完成")
        self._stats_label.setText(
            f"共 {total} 文件  ·  不同 {modified}  仅左 {left_only}  "
            f"仅右 {right_only}  相同 {identical}"
        )

    def _auto_preview_first_diff(self):
        """目录模式：自动预览第一个差异文件"""
        def find_first(nodes):
            for n in nodes:
                if not n.is_dir and n.status != DiffStatus.IDENTICAL:
                    return n
                r = find_first(n.children)
                if r:
                    return r
            return None
        first = find_first(self._nodes)
        if first:
            self._show_inline_diff(first)

    def _on_filter_changed(self):
        if self._nodes:
            show_ident = self.chk_show_identical.isChecked()
            self.diff_tree.load_nodes(self._nodes, show_identical=show_ident)

    def _swap_paths(self):
        l, r = self.left_sel.get_path(), self.right_sel.get_path()
        self.left_sel.set_path(r)
        self.right_sel.set_path(l)

    def _save_settings(self):
        self._settings.setValue("left_path",  self.left_sel.get_path())
        self._settings.setValue("right_path", self.right_sel.get_path())

    def _restore_settings(self):
        l = self._settings.value("left_path",  "")
        r = self._settings.value("right_path", "")
        if l: self.left_sel.set_path(l)
        if r: self.right_sel.set_path(r)

    def _show_about(self):
        QMessageBox.about(self, "关于 FileDiff Pro",
            "<h2>FileDiff Pro v2.0</h2>"
            "<p>文件差异比较与合并工具 · Python + PyQt5 + difflib</p>"
            "<ul><li>拖拽文件/目录到路径框</li>"
            "<li>点击比较后直接内嵌显示差异</li>"
            "<li>目录模式点击树节点即时预览</li>"
            "<li>右键同步、合并操作</li></ul>")

    def closeEvent(self, event):
        if self._diff_thread and self._diff_thread.isRunning():
            self._diff_thread.abort()
            self._diff_thread.wait(3000)
        self._save_settings()
        event.accept()
