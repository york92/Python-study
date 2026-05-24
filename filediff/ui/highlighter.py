# -*- coding: utf-8 -*-
"""
DiffHighlighter - QSyntaxHighlighter 子类
用于在 QTextEdit 中高亮差异行
"""

from PyQt5.QtGui import (
    QSyntaxHighlighter, QTextCharFormat, QColor, QFont, QTextDocument
)
from PyQt5.QtCore import Qt


# 颜色主题
COLORS = {
    "added_bg":    QColor("#1a4a2e"),   # 深绿背景（新增行）
    "added_fg":    QColor("#73d997"),   # 亮绿前景
    "deleted_bg":  QColor("#4a1a1a"),   # 深红背景（删除行）
    "deleted_fg":  QColor("#f28b82"),   # 亮红前景
    "changed_bg":  QColor("#3a3000"),   # 深黄背景（修改行）
    "changed_fg":  QColor("#ffd966"),   # 亮黄前景
    "equal_bg":    QColor("transparent"),
    "equal_fg":    QColor("#d4d4d4"),
    "lineno_fg":   QColor("#858585"),
}


class DiffHighlighter(QSyntaxHighlighter):
    """
    根据行标签（'add'/'del'/'chg'/'eq'）高亮文本。
    外部通过 set_line_tags(tags: list[str]) 传入每行的标签。
    """

    def __init__(self, document: QTextDocument):
        super().__init__(document)
        self._line_tags: list = []

        # 预建格式
        self._fmt_add = self._make_fmt(COLORS["added_bg"], COLORS["added_fg"])
        self._fmt_del = self._make_fmt(COLORS["deleted_bg"], COLORS["deleted_fg"])
        self._fmt_chg = self._make_fmt(COLORS["changed_bg"], COLORS["changed_fg"])
        self._fmt_eq = self._make_fmt(None, COLORS["equal_fg"])

    @staticmethod
    def _make_fmt(bg: QColor | None, fg: QColor) -> QTextCharFormat:
        fmt = QTextCharFormat()
        fmt.setForeground(fg)
        if bg and bg != QColor("transparent"):
            fmt.setBackground(bg)
        return fmt

    def set_line_tags(self, tags: list):
        """tags: list of 'add' | 'del' | 'chg' | 'eq' per line"""
        self._line_tags = tags
        self.rehighlight()

    def highlightBlock(self, text: str):
        block_num = self.currentBlock().blockNumber()
        if block_num >= len(self._line_tags):
            return
        tag = self._line_tags[block_num]
        fmt_map = {
            "add": self._fmt_add,
            "del": self._fmt_del,
            "chg": self._fmt_chg,
            "eq":  self._fmt_eq,
        }
        fmt = fmt_map.get(tag, self._fmt_eq)
        self.setFormat(0, len(text), fmt)


class LineNumberArea:
    """辅助：生成带行号前缀的文本"""

    @staticmethod
    def prefix_lines(lines: list, line_numbers: list) -> str:
        """生成带行号的文本内容，行号不足4位用空格对齐"""
        result = []
        for ln, line in zip(line_numbers, lines):
            num_str = str(ln).rjust(4) if ln is not None else "    "
            result.append(f"{num_str}  {line}")
        return "".join(result)
