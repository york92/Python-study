# -*- coding: utf-8 -*-
"""
文件同步操作模块
支持：复制、删除、重命名
"""

import os
import shutil
from typing import Optional


class SyncError(Exception):
    pass


def copy_left_to_right(left_path: str, right_path: str) -> None:
    """将左侧文件/目录复制到右侧"""
    try:
        if os.path.isdir(left_path):
            if os.path.exists(right_path):
                shutil.rmtree(right_path)
            shutil.copytree(left_path, right_path)
        else:
            os.makedirs(os.path.dirname(right_path) or ".", exist_ok=True)
            shutil.copy2(left_path, right_path)
    except Exception as e:
        raise SyncError(f"复制失败: {e}")


def copy_right_to_left(right_path: str, left_path: str) -> None:
    """将右侧文件/目录复制到左侧"""
    copy_left_to_right(right_path, left_path)


def delete_file(path: str) -> None:
    """删除文件或目录"""
    try:
        if os.path.isdir(path):
            shutil.rmtree(path)
        elif os.path.exists(path):
            os.remove(path)
    except Exception as e:
        raise SyncError(f"删除失败: {e}")


def rename_file(old_path: str, new_name: str) -> str:
    """重命名文件，返回新路径"""
    try:
        dir_part = os.path.dirname(old_path)
        new_path = os.path.join(dir_part, new_name)
        os.rename(old_path, new_path)
        return new_path
    except Exception as e:
        raise SyncError(f"重命名失败: {e}")


def merge_lines_into_left(
    left_path: str,
    right_path: str,
    line_indices: list,   # 右侧行索引列表（0-based）
    encoding: str = "utf-8",
) -> None:
    """
    将右侧指定行合并（追加/替换）到左侧文件。
    简单策略：将选中的右侧行追加到左侧文件末尾。
    """
    try:
        with open(right_path, "r", encoding=encoding, errors="replace") as f:
            right_lines = f.readlines()

        selected = [right_lines[i] for i in line_indices if i < len(right_lines)]

        with open(left_path, "a", encoding=encoding) as f:
            if selected:
                if not f.tell() == 0:
                    # 确保在新行追加
                    pass
                f.writelines(selected)
    except Exception as e:
        raise SyncError(f"合并失败: {e}")


def save_text_file(path: str, content: str, encoding: str = "utf-8") -> None:
    """保存文本内容到文件"""
    try:
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        with open(path, "w", encoding=encoding, newline="") as f:
            f.write(content)
    except Exception as e:
        raise SyncError(f"保存失败: {e}")
