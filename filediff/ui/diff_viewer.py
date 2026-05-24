# -*- coding: utf-8 -*-
"""
diff_viewer.py v2

新增 DiffPanel —— 可嵌入主窗口的纯 QWidget 差异面板。
保留 DiffViewerWindow —— 独立弹窗（目录模式右键"在新窗口打开"用）。

结构：
    SyncedScrollEdit        可同步滚动的 QTextEdit
    DiffPanel(QWidget)      ★ 核心差异面板（可内嵌）
    DiffViewerWindow(QDialog) 包装 DiffPanel 的弹窗
"""

import os
from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QTextEdit,
    QLabel, QPushButton, QSplitter, QWidget,
    QToolBar, QAction, QStatusBar, QMessageBox,
    QCheckBox, QFrame, QSizePolicy
)
from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtGui import QFont, QTextCursor, QTextOption, QColor

from core.diff_engine import (
    DiffNode, LineDiff, compute_line_diffs,
    is_text_file, read_text_file
)
from core.sync_ops import save_text_file, SyncError
from ui.highlighter import DiffHighlighter


# ──────────────────────────────────────────────────────────────────
# 可同步滚动编辑器
# ──────────────────────────────────────────────────────────────────
class SyncedScrollEdit(QTextEdit):
    scroll_changed = pyqtSignal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.verticalScrollBar().valueChanged.connect(self.scroll_changed.emit)

    def set_scroll(self, value: int):
        self.verticalScrollBar().setValue(value)


# ──────────────────────────────────────────────────────────────────
# DiffPanel —— 可嵌入的核心差异面板
# ──────────────────────────────────────────────────────────────────
PANEL_QSS = """
QWidget#diff_panel {
    background-color: #1e1e1e;
}
/* 路径标题栏 */
QLabel#path_bar {
    color: #9cdcfe;
    font-family: Consolas, "Courier New", monospace;
    font-size: 12px;
    padding: 5px 12px;
    background-color: #252526;
    border-bottom: 2px solid #007acc;
}
/* 编辑器 */
QTextEdit {
    background-color: #1e1e1e;
    color: #d4d4d4;
    border: none;
    selection-background-color: #264f78;
    font-family: Consolas, "Courier New", monospace;
    font-size: 12px;
}
/* 工具栏 */
QToolBar {
    background-color: #252526;
    border-bottom: 1px solid #3c3c3c;
    spacing: 2px;
    padding: 3px 6px;
}
QToolBar QLabel {
    color: #9cdcfe;
    font-size: 12px;
    padding: 0 8px;
    background: transparent;
    border: none;
}
/* 操作按钮行 */
QWidget#btn_row {
    background-color: #252526;
    border-top: 1px solid #3c3c3c;
}
QPushButton {
    background-color: #0e639c;
    color: white;
    border: none;
    padding: 5px 14px;
    border-radius: 3px;
    font-size: 12px;
}
QPushButton:hover  { background-color: #1177bb; }
QPushButton:disabled { background-color: #3c3c3c; color: #555; }
QPushButton#danger { background-color: #6b2020; }
QPushButton#danger:hover { background-color: #8b3030; }
/* 状态栏 */
QStatusBar {
    background-color: #007acc;
    color: white;
    font-size: 12px;
}
QCheckBox { color: #d4d4d4; font-size: 12px; }
"""


class DiffPanel(QWidget):
    """
    并排差异面板，可直接嵌入任意布局。
    加载 node 后自动渲染；支持同步滚动、差异导航、保存、合并。
    """

    def __init__(self, node: DiffNode, parent=None):
        super().__init__(parent)
        self.setObjectName("diff_panel")
        self.node = node
        self._diffs: list = []
        self._left_content = ""
        self._right_content = ""
        self._left_enc = "utf-8"
        self._right_enc = "utf-8"
        self._sync_scroll = True
        self._diff_line_indices: list = []
        self._current_diff_idx = -1

        self.setStyleSheet(PANEL_QSS)
        self._build_ui()
        self._load_content()

    # ── UI ──────────────────────────────────────────────────────────
    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # 工具栏
        layout.addWidget(self._build_toolbar())

        # 路径标题行（两列）
        hdr = QWidget()
        hdr.setFixedHeight(30)
        hdr.setStyleSheet("background:#252526;")
        hdr_l = QHBoxLayout(hdr)
        hdr_l.setContentsMargins(0, 0, 0, 0)
        hdr_l.setSpacing(0)

        lname = os.path.basename(self.node.left_path  or "") or "—"
        rname = os.path.basename(self.node.right_path or "") or "—"
        ldir  = os.path.dirname(self.node.left_path   or "")
        rdir  = os.path.dirname(self.node.right_path  or "")

        for txt in (
            f"  ◀  {lname}    {ldir}",
            f"  ▶  {rname}    {rdir}",
        ):
            lbl = QLabel(txt)
            lbl.setObjectName("path_bar")
            lbl.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
            hdr_l.addWidget(lbl)
        layout.addWidget(hdr)

        # 编辑区（水平 Splitter）
        splitter = QSplitter(Qt.Horizontal)
        splitter.setStyleSheet(
            "QSplitter::handle { background:#007acc; width:3px; }"
        )
        self.left_edit  = self._make_editor()
        self.right_edit = self._make_editor()
        splitter.addWidget(self.left_edit)
        splitter.addWidget(self.right_edit)
        splitter.setSizes([1, 1])
        layout.addWidget(splitter, 1)

        # 操作按钮行
        btn_row = QWidget()
        btn_row.setObjectName("btn_row")
        btn_l = QHBoxLayout(btn_row)
        btn_l.setContentsMargins(8, 5, 8, 5)
        btn_l.setSpacing(6)

        self.btn_save_left  = QPushButton("💾 保存左侧")
        self.btn_save_right = QPushButton("💾 保存右侧")
        self.btn_l2r        = QPushButton("▶ 左→右覆盖")
        self.btn_r2l        = QPushButton("◀ 右→左覆盖")
        self.btn_merge      = QPushButton("⇒ 合并右侧选中到左侧")

        for b in (self.btn_save_left, self.btn_save_right,
                  self.btn_l2r, self.btn_r2l, self.btn_merge):
            btn_l.addWidget(b)
        btn_l.addStretch()

        layout.addWidget(btn_row)

        # 状态栏
        self.status_bar = QStatusBar()
        layout.addWidget(self.status_bar)

        # 高亮器
        self._left_hl  = DiffHighlighter(self.left_edit.document())
        self._right_hl = DiffHighlighter(self.right_edit.document())

        # 信号
        self.left_edit.scroll_changed.connect(self._on_left_scroll)
        self.right_edit.scroll_changed.connect(self._on_right_scroll)
        self.btn_save_left.clicked.connect(self._save_left)
        self.btn_save_right.clicked.connect(self._save_right)
        self.btn_l2r.clicked.connect(self._copy_l2r)
        self.btn_r2l.clicked.connect(self._copy_r2l)
        self.btn_merge.clicked.connect(self._merge_to_left)

    def _build_toolbar(self) -> QToolBar:
        tb = QToolBar()
        tb.setMovable(False)

        chk = QCheckBox("同步滚动")
        chk.setChecked(True)
        chk.stateChanged.connect(lambda s: setattr(self, "_sync_scroll", bool(s)))
        tb.addWidget(chk)
        tb.addSeparator()

        a_prev = QAction("⬆  上一处差异", self)
        a_next = QAction("⬇  下一处差异", self)
        a_prev.triggered.connect(self._goto_prev)
        a_next.triggered.connect(self._goto_next)
        tb.addActions([a_prev, a_next])
        tb.addSeparator()

        self._count_lbl = QLabel("加载中…")
        tb.addWidget(self._count_lbl)
        return tb

    @staticmethod
    def _make_editor() -> SyncedScrollEdit:
        e = SyncedScrollEdit()
        e.setReadOnly(True)
        e.setFont(QFont("Consolas", 11))
        e.setLineWrapMode(QTextEdit.NoWrap)
        e.setWordWrapMode(QTextOption.NoWrap)
        return e

    # ── 数据加载 ────────────────────────────────────────────────────
    def _load_content(self):
        left_ok = right_ok = False

        if self.node.left_path and os.path.isfile(self.node.left_path):
            if is_text_file(self.node.left_path):
                self._left_content, self._left_enc = read_text_file(self.node.left_path)
                left_ok = True
            else:
                self._left_content = "[二进制文件，无法显示文本内容]"

        if self.node.right_path and os.path.isfile(self.node.right_path):
            if is_text_file(self.node.right_path):
                self._right_content, self._right_enc = read_text_file(self.node.right_path)
                right_ok = True
            else:
                self._right_content = "[二进制文件，无法显示文本内容]"

        if left_ok and right_ok:
            self._diffs = compute_line_diffs(self._left_content, self._right_content)
        else:
            self._diffs = []

        self._render()

    # ── 渲染 ────────────────────────────────────────────────────────
    def _render(self):
        TAG_MAP = {
            "equal":   ("eq",  "eq"),
            "replace": ("chg", "chg"),
            "delete":  ("del", "eq"),
            "insert":  ("eq",  "add"),
        }
        l_lines, r_lines = [], []
        l_nums,  r_nums  = [], []
        l_tags,  r_tags  = [], []

        for d in self._diffs:
            lt, rt = TAG_MAP.get(d.tag, ("eq", "eq"))
            l_lines.append(d.content_left);  r_lines.append(d.content_right)
            l_nums.append(d.line_num_left);   r_nums.append(d.line_num_right)
            l_tags.append(lt);               r_tags.append(rt)

        def build(lines, nums):
            parts = []
            for ln, line in zip(nums, lines):
                n = str(ln).rjust(5) if ln is not None else "     "
                parts.append(f"{n} │ {(line or '').rstrip(chr(13)+chr(10))}\n")
            return "".join(parts)

        self.left_edit.setPlainText(build(l_lines, l_nums))
        self.right_edit.setPlainText(build(r_lines, r_nums))
        self._left_hl.set_line_tags(l_tags)
        self._right_hl.set_line_tags(r_tags)

        diff_n = sum(1 for d in self._diffs if d.tag != "equal")
        total  = len(self._diffs)
        self._count_lbl.setText(f"  差异 {diff_n} 处 / 共 {total} 行  ")
        self.status_bar.showMessage(
            f"左侧编码: {self._left_enc}  ·  右侧编码: {self._right_enc}"
            f"  ·  差异 {diff_n} 处"
        )
        self._diff_line_indices = [i for i, d in enumerate(self._diffs) if d.tag != "equal"]
        self._current_diff_idx = -1

        # 自动跳到第一处差异
        if self._diff_line_indices:
            self._goto_next()

    # ── 滚动同步 ────────────────────────────────────────────────────
    def _on_left_scroll(self, v):
        if self._sync_scroll: self.right_edit.set_scroll(v)

    def _on_right_scroll(self, v):
        if self._sync_scroll: self.left_edit.set_scroll(v)

    # ── 差异导航 ────────────────────────────────────────────────────
    def _goto_next(self):
        if not self._diff_line_indices: return
        self._current_diff_idx = (self._current_diff_idx + 1) % len(self._diff_line_indices)
        self._jump(self._diff_line_indices[self._current_diff_idx])

    def _goto_prev(self):
        if not self._diff_line_indices: return
        self._current_diff_idx = (self._current_diff_idx - 1) % len(self._diff_line_indices)
        self._jump(self._diff_line_indices[self._current_diff_idx])

    def _jump(self, line_idx: int):
        for edit in (self.left_edit, self.right_edit):
            blk = edit.document().findBlockByLineNumber(line_idx)
            cur = edit.textCursor()
            cur.setPosition(blk.position())
            edit.setTextCursor(cur)
            edit.ensureCursorVisible()

    # ── 保存 / 同步 / 合并 ──────────────────────────────────────────
    def _save_left(self):
        if not self.node.left_path: return
        try:
            save_text_file(self.node.left_path, self._left_content, self._left_enc)
            self.status_bar.showMessage("左侧文件已保存", 3000)
        except SyncError as e:
            QMessageBox.critical(self, "保存失败", str(e))

    def _save_right(self):
        if not self.node.right_path: return
        try:
            save_text_file(self.node.right_path, self._right_content, self._right_enc)
            self.status_bar.showMessage("右侧文件已保存", 3000)
        except SyncError as e:
            QMessageBox.critical(self, "保存失败", str(e))

    def _copy_l2r(self):
        if not (self.node.left_path and self.node.right_path): return
        if QMessageBox.question(self, "确认", "将左侧内容覆盖右侧文件？",
                QMessageBox.Yes | QMessageBox.No) == QMessageBox.Yes:
            try:
                save_text_file(self.node.right_path, self._left_content, self._right_enc)
                self._right_content = self._left_content
                self._diffs = compute_line_diffs(self._left_content, self._right_content)
                self._render()
            except SyncError as e:
                QMessageBox.critical(self, "失败", str(e))

    def _copy_r2l(self):
        if not (self.node.left_path and self.node.right_path): return
        if QMessageBox.question(self, "确认", "将右侧内容覆盖左侧文件？",
                QMessageBox.Yes | QMessageBox.No) == QMessageBox.Yes:
            try:
                save_text_file(self.node.left_path, self._right_content, self._left_enc)
                self._left_content = self._right_content
                self._diffs = compute_line_diffs(self._left_content, self._right_content)
                self._render()
            except SyncError as e:
                QMessageBox.critical(self, "失败", str(e))

    def _merge_to_left(self):
        if not self.node.left_path:
            QMessageBox.warning(self, "提示", "没有左侧文件路径"); return

        cursor = self.right_edit.textCursor()
        doc = self.right_edit.document()
        sb = doc.findBlock(cursor.selectionStart()).blockNumber()
        eb = doc.findBlock(cursor.selectionEnd()).blockNumber()
        if sb == eb and not cursor.hasSelection():
            sb = eb = cursor.blockNumber()

        sel = [i for i in range(sb, eb + 1)
               if i < len(self._diffs) and self._diffs[i].tag != "equal"]
        if not sel:
            QMessageBox.information(self, "提示", "请先在右侧选中差异行（高亮行）后再合并")
            return

        left_lines = self._left_content.splitlines(keepends=True)
        new_lines  = list(left_lines)
        for idx in reversed(sel):
            d = self._diffs[idx]
            if d.line_num_left is not None and d.line_num_right is not None:
                new_lines[d.line_num_left - 1] = d.content_right
            elif d.line_num_right is not None:
                ins = len(new_lines)
                for pi in range(idx - 1, -1, -1):
                    if self._diffs[pi].line_num_left is not None:
                        ins = self._diffs[pi].line_num_left; break
                new_lines.insert(ins, d.content_right)

        self._left_content = "".join(new_lines)
        try:
            save_text_file(self.node.left_path, self._left_content, self._left_enc)
            self._diffs = compute_line_diffs(self._left_content, self._right_content)
            self._render()
            self.status_bar.showMessage(f"已合并 {len(sel)} 处更改到左侧", 3000)
        except SyncError as e:
            QMessageBox.critical(self, "合并失败", str(e))

    def reload(self, node: DiffNode):
        """切换到新节点时刷新"""
        self.node = node
        self._diffs = []
        self._left_content = self._right_content = ""
        self._left_enc = self._right_enc = "utf-8"
        self._load_content()


# ──────────────────────────────────────────────────────────────────
# DiffViewerWindow —— 独立弹窗（包装 DiffPanel）
# ──────────────────────────────────────────────────────────────────
class DiffViewerWindow(QDialog):
    """独立弹窗，目录模式右键"在新窗口打开"使用"""

    def __init__(self, node: DiffNode, parent=None):
        super().__init__(parent)
        self.setWindowTitle(
            f"差异查看 — {os.path.basename(node.left_path or '')} "
            f"vs {os.path.basename(node.right_path or '')}"
        )
        self.resize(1280, 780)
        self.setModal(False)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self.panel = DiffPanel(node, self)
        layout.addWidget(self.panel)

        # 关闭按钮
        btn_close = QPushButton("✕  关闭窗口")
        btn_close.setObjectName("danger")
        btn_close.setStyleSheet(
            "QPushButton{background:#6b2020;color:white;border:none;"
            "padding:6px 18px;font-size:13px;border-radius:3px;}"
            "QPushButton:hover{background:#8b3030;}"
        )
        btn_close.clicked.connect(self.close)

        footer = QWidget()
        footer.setStyleSheet("background:#252526;border-top:1px solid #3c3c3c;")
        fl = QHBoxLayout(footer)
        fl.setContentsMargins(8, 5, 8, 5)
        fl.addStretch()
        fl.addWidget(btn_close)
        layout.addWidget(footer)
