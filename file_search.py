#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""
file_search.py
===============
一个多维度文件搜索命令行工具，效果类似简化版的 everything / find。

功能：
1. 按文件名搜索：支持通配符（如 "invoice*"）、纯子串匹配、或正则表达式。
2. 按扩展名过滤：如只搜索 .xlsx / .pdf。
3. 按文件大小过滤：--min-size / --max-size，支持 "10KB" "5MB" "1GB" 这样的写法。
4. 按修改时间过滤：--modified-after / --modified-before，支持 "2025-01-01" 或 "7d"（最近7天）这样的写法。
5. 按文件内容搜索（文本文件）：--content "关键词"，命中时会打印所在行号和预览。
6. 支持排除目录（如 .git、node_modules、__pycache__ 等，有合理默认值）。
7. 结果可按名称/大小/修改时间排序，也可直接导出为 JSON / CSV 结果清单。
8. 大小写敏感开关、正则开关、递归深度限制。

用法示例：
    # 按文件名子串搜索（默认不区分大小写），在 D:\ 全盘搜索 invoice
    python file_search.py search "D:\\" --name invoice

    # 按通配符搜索，只看 xlsx 和 pdf
    python file_search.py search "D:\\" --name "invoice*" --ext .xlsx,.pdf

    # 正则搜索文件名
    python file_search.py search "D:\\" --name "invoice-20\\d{2}" --regex

    # 搜索最近7天内修改过、且内容包含"合同编号"的 txt/docx 文件
    python file_search.py search "D:\\Contracts" --ext .txt,.docx --content "合同编号" --modified-after 7d

    # 搜索大于 5MB 的视频文件，按大小从大到小排序
    python file_search.py search "D:\\Videos" --ext .mp4,.mkv --min-size 5MB --sort size --desc

    # 把结果导出成 JSON，方便后续处理
    python file_search.py search "D:\\" --name invoice --export results.json

作者：Claude
"""

import argparse
import csv
import fnmatch
import json
import re
import sys
from datetime import datetime, timedelta
from pathlib import Path


# ---------------------------------------------------------------------------
# 默认排除的目录（常见的无需搜索的系统/构建/缓存目录）
# ---------------------------------------------------------------------------

DEFAULT_EXCLUDE_DIRS = {
    ".git", ".svn", "__pycache__", "node_modules", ".venv", "venv",
    "$RECYCLE.BIN", "System Volume Information", ".Trash",
}

# 判定为"文本文件"从而可以做内容搜索的常见扩展名
TEXT_LIKE_EXTENSIONS = {
    ".txt", ".md", ".csv", ".json", ".xml", ".log", ".py", ".js", ".ts",
    ".java", ".c", ".cpp", ".h", ".html", ".css", ".yaml", ".yml", ".ini",
    ".cfg", ".sh", ".bat", ".sql",
}


# ---------------------------------------------------------------------------
# 大小 / 时间 解析辅助函数
# ---------------------------------------------------------------------------

SIZE_UNITS = {"B": 1, "KB": 1024, "MB": 1024**2, "GB": 1024**3, "TB": 1024**4}


def parse_size(size_str):
    """把 '10KB' '5MB' '1.5GB' '2048' 这样的字符串解析成字节数（int）。"""
    if size_str is None:
        return None
    s = size_str.strip().upper()
    match = re.match(r"^([\d.]+)\s*(B|KB|MB|GB|TB)?$", s)
    if not match:
        raise ValueError(f"无法解析大小: '{size_str}'，请用类似 '10KB' '5MB' '1GB' 的格式")
    number, unit = match.groups()
    unit = unit or "B"
    return int(float(number) * SIZE_UNITS[unit])


def format_size(num_bytes):
    """把字节数格式化成人类可读的字符串。"""
    size = float(num_bytes)
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if size < 1024 or unit == "TB":
            return f"{size:.1f}{unit}" if unit != "B" else f"{int(size)}B"
        size /= 1024


def parse_date(date_str):
    """
    把日期字符串解析成 datetime。
    支持两种格式：
      - 绝对日期 'YYYY-MM-DD'（可选 'YYYY-MM-DD HH:MM'）
      - 相对天数 '7d'（表示 7 天前）、'2h'（2 小时前）
    """
    if date_str is None:
        return None
    s = date_str.strip()

    relative_match = re.match(r"^(\d+)\s*([dh])$", s.lower())
    if relative_match:
        amount, unit = relative_match.groups()
        amount = int(amount)
        delta = timedelta(days=amount) if unit == "d" else timedelta(hours=amount)
        return datetime.now() - delta

    for fmt in ("%Y-%m-%d %H:%M", "%Y-%m-%d"):
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            continue

    raise ValueError(f"无法解析日期: '{date_str}'，请用 'YYYY-MM-DD' 或相对格式如 '7d'")


# ---------------------------------------------------------------------------
# 匹配逻辑
# ---------------------------------------------------------------------------

def build_name_matcher(pattern, use_regex, case_sensitive):
    """
    根据 --name 参数构造一个 matcher(filename) -> bool 函数。
    - 如果 use_regex，则当作正则表达式匹配（search，不要求全匹配）。
    - 否则，如果 pattern 含通配符 * ?，用 fnmatch 做通配符匹配。
    - 否则，做简单子串匹配。
    """
    if pattern is None:
        return lambda name: True

    flags = 0 if case_sensitive else re.IGNORECASE

    if use_regex:
        compiled = re.compile(pattern, flags)
        return lambda name: compiled.search(name) is not None

    if any(ch in pattern for ch in "*?[]"):
        cmp_pattern = pattern if case_sensitive else pattern.lower()
        return lambda name: fnmatch.fnmatch(name if case_sensitive else name.lower(), cmp_pattern)

    cmp_pattern = pattern if case_sensitive else pattern.lower()
    return lambda name: cmp_pattern in (name if case_sensitive else name.lower())


def search_file_content(path, keyword, case_sensitive, max_matches=3, max_bytes=5 * 1024 * 1024):
    """
    在单个文本文件中搜索关键词，返回命中的 (行号, 行内容预览) 列表（最多 max_matches 条）。
    过大或非文本文件会被跳过（返回 None 表示未搜索/不适用）。
    """
    try:
        if path.stat().st_size > max_bytes:
            return None  # 文件太大，跳过内容搜索，避免卡住
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            text = keyword if case_sensitive else keyword.lower()
            hits = []
            for line_no, line in enumerate(f, start=1):
                haystack = line if case_sensitive else line.lower()
                if text in haystack:
                    preview = line.strip()
                    if len(preview) > 100:
                        preview = preview[:100] + "..."
                    hits.append((line_no, preview))
                    if len(hits) >= max_matches:
                        break
            return hits
    except (OSError, UnicodeDecodeError):
        return None


# ---------------------------------------------------------------------------
# 主搜索流程
# ---------------------------------------------------------------------------

def iter_candidate_files(root_dir, exclude_dirs, max_depth=None):
    """遍历目录树，按需跳过排除目录和超出深度限制的部分。"""
    root_dir = Path(root_dir)
    root_depth = len(root_dir.parts)

    for current_dir, dirnames, filenames in _walk(root_dir):
        # 原地过滤子目录，阻止 os.walk 继续往里走
        dirnames[:] = [d for d in dirnames if d not in exclude_dirs]

        if max_depth is not None:
            depth = len(Path(current_dir).parts) - root_depth
            if depth >= max_depth:
                dirnames[:] = []  # 不再往下钻

        for name in filenames:
            yield Path(current_dir) / name


def _walk(root_dir):
    """对 os.walk 的简单封装，方便未来替换实现或加日志。"""
    import os
    yield from os.walk(root_dir)


def search_files(root_dir, name_pattern=None, use_regex=False, case_sensitive=False,
                  extensions=None, min_size=None, max_size=None,
                  modified_after=None, modified_before=None,
                  content_keyword=None, exclude_dirs=None, max_depth=None):
    """
    执行搜索，返回结果列表，每项是一个 dict：
      { path, size, modified, content_matches }
    """
    root_dir = Path(root_dir)
    if not root_dir.exists():
        raise FileNotFoundError(f"路径不存在: {root_dir}")

    exclude_dirs = exclude_dirs if exclude_dirs is not None else DEFAULT_EXCLUDE_DIRS
    name_matcher = build_name_matcher(name_pattern, use_regex, case_sensitive)
    ext_set = {e.lower() if e.startswith(".") else f".{e.lower()}" for e in extensions} if extensions else None

    results = []
    scanned, matched_name = 0, 0

    for file_path in iter_candidate_files(root_dir, exclude_dirs, max_depth):
        scanned += 1
        try:
            if not name_matcher(file_path.name):
                continue
            if ext_set is not None and file_path.suffix.lower() not in ext_set:
                continue

            stat = file_path.stat()
            if min_size is not None and stat.st_size < min_size:
                continue
            if max_size is not None and stat.st_size > max_size:
                continue

            mtime = datetime.fromtimestamp(stat.st_mtime)
            if modified_after is not None and mtime < modified_after:
                continue
            if modified_before is not None and mtime > modified_before:
                continue

            matched_name += 1

            content_matches = None
            if content_keyword:
                is_text_like = file_path.suffix.lower() in TEXT_LIKE_EXTENSIONS
                if not is_text_like:
                    continue  # 内容搜索只对文本类文件生效，非文本类直接跳过
                content_matches = search_file_content(file_path, content_keyword, case_sensitive)
                if not content_matches:
                    continue  # 未命中内容关键词

            results.append({
                "path": str(file_path),
                "size": stat.st_size,
                "modified": mtime.isoformat(timespec="seconds"),
                "content_matches": content_matches,
            })
        except (OSError, PermissionError):
            continue  # 跳过无权限访问的文件

    return results, scanned


# ---------------------------------------------------------------------------
# 输出
# ---------------------------------------------------------------------------

def sort_results(results, sort_by, descending):
    key_map = {
        "name": lambda r: Path(r["path"]).name.lower(),
        "size": lambda r: r["size"],
        "modified": lambda r: r["modified"],
        "path": lambda r: r["path"].lower(),
    }
    key_func = key_map.get(sort_by, key_map["path"])
    return sorted(results, key=key_func, reverse=descending)


def print_results(results):
    if not results:
        print("未找到匹配的文件。")
        return

    for r in results:
        print(r["path"])
        if r.get("content_matches"):
            for line_no, preview in r["content_matches"]:
                print(f"    第 {line_no} 行: {preview}")

    total_size = sum(r["size"] for r in results)
    print(f"\n共找到 {len(results)} 个文件，总大小 {format_size(total_size)}")


def export_results(results, export_path):
    export_path = Path(export_path)
    if export_path.suffix.lower() == ".csv":
        with open(export_path, "w", newline="", encoding="utf-8-sig") as f:
            writer = csv.writer(f)
            writer.writerow(["path", "size_bytes", "modified", "content_match_lines"])
            for r in results:
                lines = ";".join(str(m[0]) for m in r["content_matches"]) if r.get("content_matches") else ""
                writer.writerow([r["path"], r["size"], r["modified"], lines])
    else:
        with open(export_path, "w", encoding="utf-8") as f:
            json.dump(results, f, ensure_ascii=False, indent=2)
    print(f"\n结果已导出到: {export_path}")


# ---------------------------------------------------------------------------
# 命令行入口
# ---------------------------------------------------------------------------

def cmd_search(args):
    min_size = parse_size(args.min_size) if args.min_size else None
    max_size = parse_size(args.max_size) if args.max_size else None
    modified_after = parse_date(args.modified_after) if args.modified_after else None
    modified_before = parse_date(args.modified_before) if args.modified_before else None
    extensions = [e.strip() for e in args.ext.split(",")] if args.ext else None

    exclude_dirs = set(DEFAULT_EXCLUDE_DIRS)
    if args.exclude_dir:
        exclude_dirs.update(args.exclude_dir)
    if args.no_default_excludes:
        exclude_dirs = set(args.exclude_dir) if args.exclude_dir else set()

    results, scanned = search_files(
        root_dir=args.directory,
        name_pattern=args.name,
        use_regex=args.regex,
        case_sensitive=args.case_sensitive,
        extensions=extensions,
        min_size=min_size,
        max_size=max_size,
        modified_after=modified_after,
        modified_before=modified_before,
        content_keyword=args.content,
        exclude_dirs=exclude_dirs,
        max_depth=args.max_depth,
    )

    results = sort_results(results, args.sort, args.desc)

    print(f"扫描了 {scanned} 个文件，匹配 {len(results)} 个\n")
    print_results(results)

    if args.export:
        export_results(results, args.export)


def build_arg_parser():
    parser = argparse.ArgumentParser(
        description="多维度文件搜索工具（按文件名/扩展名/大小/修改时间/文件内容搜索）",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_search = sub.add_parser("search", help="执行搜索")
    p_search.add_argument("directory", help="要搜索的根目录")
    p_search.add_argument("--name", default=None,
                           help="按文件名匹配：子串 / 通配符（如 'invoice*'）/ 正则（配合 --regex）")
    p_search.add_argument("--regex", action="store_true", help="把 --name 当作正则表达式")
    p_search.add_argument("--case-sensitive", action="store_true", help="文件名/内容匹配区分大小写")
    p_search.add_argument("--ext", default=None, help="按扩展名过滤，逗号分隔，如 '.xlsx,.pdf'")
    p_search.add_argument("--min-size", default=None, help="最小文件大小，如 '10KB' '5MB'")
    p_search.add_argument("--max-size", default=None, help="最大文件大小，如 '1GB'")
    p_search.add_argument("--modified-after", default=None,
                           help="只要此时间之后修改过的文件，如 '2025-01-01' 或 '7d'（最近7天）")
    p_search.add_argument("--modified-before", default=None,
                           help="只要此时间之前修改过的文件，如 '2025-01-01'")
    p_search.add_argument("--content", default=None,
                           help="搜索文本类文件内容中包含的关键词（仅对文本类扩展名生效）")
    p_search.add_argument("--exclude-dir", action="append", default=[],
                           help="额外排除的目录名，可重复使用多次")
    p_search.add_argument("--no-default-excludes", action="store_true",
                           help="不使用默认排除目录列表（.git/node_modules 等）")
    p_search.add_argument("--max-depth", type=int, default=None,
                           help="限制递归深度（0 表示只看根目录本身）")
    p_search.add_argument("--sort", choices=["name", "size", "modified", "path"], default="path",
                           help="排序方式，默认按路径")
    p_search.add_argument("--desc", action="store_true", help="降序排列")
    p_search.add_argument("--export", default=None,
                           help="把结果导出为文件，后缀 .json 或 .csv 决定格式")

    return parser


def main():
    parser = build_arg_parser()
    args = parser.parse_args()

    try:
        if args.command == "search":
            cmd_search(args)
    except Exception as e:
        print(f"错误: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
