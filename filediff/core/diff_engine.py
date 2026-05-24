# -*- coding: utf-8 -*-
"""
核心比较引擎
包含 DiffThread（后台比较线程）和 DiffResult（比较结果数据类）
"""

import os
import hashlib
import difflib
from enum import Enum
from dataclasses import dataclass, field
from typing import List, Optional, Tuple

from PyQt5.QtCore import QThread, pyqtSignal


class DiffStatus(Enum):
    """文件/文件夹差异状态"""
    IDENTICAL = "identical"       # 完全相同
    MODIFIED = "modified"         # 内容不同
    LEFT_ONLY = "left_only"       # 仅左侧有
    RIGHT_ONLY = "right_only"     # 仅右侧有
    TYPE_CHANGED = "type_changed" # 类型改变（文件变文件夹等）


@dataclass
class DiffNode:
    """差异树节点"""
    name: str
    rel_path: str                          # 相对路径
    left_path: Optional[str] = None
    right_path: Optional[str] = None
    status: DiffStatus = DiffStatus.IDENTICAL
    is_dir: bool = False
    children: List["DiffNode"] = field(default_factory=list)
    size_left: int = 0
    size_right: int = 0

    def has_differences(self) -> bool:
        return self.status != DiffStatus.IDENTICAL

    def recursive_has_diff(self) -> bool:
        if self.has_differences():
            return True
        return any(c.recursive_has_diff() for c in self.children)


@dataclass
class LineDiff:
    """单行差异"""
    line_num_left: Optional[int]
    line_num_right: Optional[int]
    content_left: str
    content_right: str
    tag: str  # 'equal', 'replace', 'insert', 'delete'


class DiffThread(QThread):
    """
    后台比较线程，避免UI阻塞。
    发出信号：
        progress(int)       - 进度 0-100
        status_msg(str)     - 状态消息
        result(list)        - 根节点列表 List[DiffNode]
        error(str)          - 错误消息
        finished_ok()       - 成功完成
    """
    progress = pyqtSignal(int)
    status_msg = pyqtSignal(str)
    result = pyqtSignal(list)
    error = pyqtSignal(str)
    finished_ok = pyqtSignal()

    def __init__(self, left_path: str, right_path: str, parent=None):
        super().__init__(parent)
        self.left_path = left_path
        self.right_path = right_path
        self._abort = False
        self._total = 0
        self._done = 0

    def abort(self):
        self._abort = True

    def run(self):
        try:
            left = self.left_path
            right = self.right_path

            if os.path.isfile(left) and os.path.isfile(right):
                # 单文件比较
                self.status_msg.emit("正在比较文件…")
                node = self._compare_files(
                    os.path.basename(left), "", left, right
                )
                self.result.emit([node])
            elif os.path.isdir(left) and os.path.isdir(right):
                # 文件夹比较
                self.status_msg.emit("正在扫描目录…")
                # 预先统计文件数
                self._total = sum(
                    len(files)
                    for _, _, files in os.walk(left)
                ) + sum(
                    len(files)
                    for _, _, files in os.walk(right)
                )
                nodes = self._compare_dirs("", left, right)
                self.result.emit(nodes)
            else:
                # 类型不匹配：一个是文件一个是文件夹
                node = DiffNode(
                    name=os.path.basename(left),
                    rel_path="",
                    left_path=left,
                    right_path=right,
                    status=DiffStatus.TYPE_CHANGED,
                    is_dir=os.path.isdir(left),
                )
                self.result.emit([node])

            if not self._abort:
                self.progress.emit(100)
                self.finished_ok.emit()
        except Exception as e:
            self.error.emit(str(e))

    def _compare_dirs(
        self, rel_base: str, left_dir: str, right_dir: str
    ) -> List[DiffNode]:
        """递归比较两个目录，返回 DiffNode 列表"""
        if self._abort:
            return []

        left_entries: dict = {}
        right_entries: dict = {}

        if os.path.isdir(left_dir):
            for name in os.listdir(left_dir):
                left_entries[name] = os.path.join(left_dir, name)

        if os.path.isdir(right_dir):
            for name in os.listdir(right_dir):
                right_entries[name] = os.path.join(right_dir, name)

        all_names = sorted(set(left_entries) | set(right_entries))
        nodes: List[DiffNode] = []

        for name in all_names:
            if self._abort:
                break

            rel_path = os.path.join(rel_base, name) if rel_base else name
            lp = left_entries.get(name)
            rp = right_entries.get(name)

            self.status_msg.emit(f"比较: {rel_path}")

            if lp and not rp:
                node = DiffNode(
                    name=name, rel_path=rel_path,
                    left_path=lp, right_path=None,
                    status=DiffStatus.LEFT_ONLY,
                    is_dir=os.path.isdir(lp),
                )
                if node.is_dir:
                    node.children = self._collect_dir(rel_path, lp, "left")
            elif rp and not lp:
                node = DiffNode(
                    name=name, rel_path=rel_path,
                    left_path=None, right_path=rp,
                    status=DiffStatus.RIGHT_ONLY,
                    is_dir=os.path.isdir(rp),
                )
                if node.is_dir:
                    node.children = self._collect_dir(rel_path, rp, "right")
            else:
                # 两侧都有
                l_is_dir = os.path.isdir(lp)
                r_is_dir = os.path.isdir(rp)

                if l_is_dir and r_is_dir:
                    node = DiffNode(
                        name=name, rel_path=rel_path,
                        left_path=lp, right_path=rp,
                        is_dir=True,
                    )
                    node.children = self._compare_dirs(rel_path, lp, rp)
                    # 如果子节点有差异，本节点也标记
                    if any(c.recursive_has_diff() for c in node.children):
                        node.status = DiffStatus.MODIFIED
                    else:
                        node.status = DiffStatus.IDENTICAL
                elif not l_is_dir and not r_is_dir:
                    node = self._compare_files(name, rel_path, lp, rp)
                else:
                    node = DiffNode(
                        name=name, rel_path=rel_path,
                        left_path=lp, right_path=rp,
                        status=DiffStatus.TYPE_CHANGED,
                        is_dir=l_is_dir,
                    )

            nodes.append(node)

        return nodes

    def _compare_files(
        self, name: str, rel_path: str, left_path: str, right_path: str
    ) -> DiffNode:
        """比较两个文件，返回 DiffNode"""
        self._done += 1
        if self._total > 0:
            self.progress.emit(min(99, int(self._done / self._total * 100)))

        node = DiffNode(
            name=name, rel_path=rel_path,
            left_path=left_path, right_path=right_path,
            is_dir=False,
        )
        try:
            node.size_left = os.path.getsize(left_path)
            node.size_right = os.path.getsize(right_path)

            # 快速哈希比较
            if self._hash_file(left_path) == self._hash_file(right_path):
                node.status = DiffStatus.IDENTICAL
            else:
                node.status = DiffStatus.MODIFIED
        except (OSError, PermissionError):
            node.status = DiffStatus.MODIFIED

        return node

    def _collect_dir(
        self, rel_base: str, dir_path: str, side: str
    ) -> List[DiffNode]:
        """将单侧目录的所有内容收集为 DiffNode（仅有一侧）"""
        nodes = []
        try:
            for name in sorted(os.listdir(dir_path)):
                full = os.path.join(dir_path, name)
                rel = os.path.join(rel_base, name)
                status = (
                    DiffStatus.LEFT_ONLY if side == "left"
                    else DiffStatus.RIGHT_ONLY
                )
                is_dir = os.path.isdir(full)
                node = DiffNode(
                    name=name, rel_path=rel,
                    left_path=full if side == "left" else None,
                    right_path=full if side == "right" else None,
                    status=status, is_dir=is_dir,
                )
                if is_dir:
                    node.children = self._collect_dir(rel, full, side)
                nodes.append(node)
        except (OSError, PermissionError):
            pass
        return nodes

    @staticmethod
    def _hash_file(path: str) -> str:
        h = hashlib.md5()
        try:
            with open(path, "rb") as f:
                for chunk in iter(lambda: f.read(65536), b""):
                    h.update(chunk)
        except (OSError, PermissionError):
            return ""
        return h.hexdigest()


# ──────────────────────────────────────────────
# 文本内容比较工具函数
# ──────────────────────────────────────────────

def compute_line_diffs(left_text: str, right_text: str) -> List[LineDiff]:
    """
    使用 difflib.SequenceMatcher 计算行级差异。
    返回 LineDiff 列表，用于在编辑器中高亮。
    """
    left_lines = left_text.splitlines(keepends=True)
    right_lines = right_text.splitlines(keepends=True)

    matcher = difflib.SequenceMatcher(
        None, left_lines, right_lines, autojunk=False
    )
    diffs: List[LineDiff] = []

    ln_l = 0
    ln_r = 0

    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            for k in range(i2 - i1):
                diffs.append(LineDiff(
                    line_num_left=ln_l + k + 1,
                    line_num_right=ln_r + k + 1,
                    content_left=left_lines[i1 + k],
                    content_right=right_lines[j1 + k],
                    tag="equal",
                ))
            ln_l += i2 - i1
            ln_r += j2 - j1

        elif tag == "replace":
            left_chunk = left_lines[i1:i2]
            right_chunk = right_lines[j1:j2]
            max_len = max(len(left_chunk), len(right_chunk))
            for k in range(max_len):
                l_line = left_chunk[k] if k < len(left_chunk) else ""
                r_line = right_chunk[k] if k < len(right_chunk) else ""
                l_num = (ln_l + k + 1) if k < len(left_chunk) else None
                r_num = (ln_r + k + 1) if k < len(right_chunk) else None
                diffs.append(LineDiff(
                    line_num_left=l_num, line_num_right=r_num,
                    content_left=l_line, content_right=r_line,
                    tag="replace",
                ))
            ln_l += i2 - i1
            ln_r += j2 - j1

        elif tag == "delete":
            for k in range(i2 - i1):
                diffs.append(LineDiff(
                    line_num_left=ln_l + k + 1, line_num_right=None,
                    content_left=left_lines[i1 + k], content_right="",
                    tag="delete",
                ))
            ln_l += i2 - i1

        elif tag == "insert":
            for k in range(j2 - j1):
                diffs.append(LineDiff(
                    line_num_left=None, line_num_right=ln_r + k + 1,
                    content_left="", content_right=right_lines[j1 + k],
                    tag="insert",
                ))
            ln_r += j2 - j1

    return diffs


def is_text_file(path: str, sample_size: int = 8192) -> bool:
    """判断文件是否为文本文件"""
    try:
        with open(path, "rb") as f:
            chunk = f.read(sample_size)
        # 检测 null 字节
        if b"\x00" in chunk:
            return False
        # 尝试 UTF-8 解码
        try:
            chunk.decode("utf-8")
            return True
        except UnicodeDecodeError:
            pass
        # 尝试 GBK
        try:
            chunk.decode("gbk")
            return True
        except UnicodeDecodeError:
            pass
        return False
    except (OSError, PermissionError):
        return False


def read_text_file(path: str) -> Tuple[str, str]:
    """读取文本文件，返回 (内容, 编码)"""
    for enc in ("utf-8-sig", "utf-8", "gbk", "latin-1"):
        try:
            with open(path, "r", encoding=enc) as f:
                return f.read(), enc
        except (UnicodeDecodeError, OSError):
            continue
    return "", "unknown"
