#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
code_merge.py
-------------
递归扫描目标项目目录，将主流编程语言、配置文件、脚本文件等
按照相对路径依次汇总到一个 TXT 文件中。

特点：
1. 支持 Java / JavaScript / TypeScript / Python / C / C++ / C# / Go /
   Rust / PHP / Ruby / Kotlin / Swift / Scala / Dart / R / Shell /
   PowerShell / SQL / Vue / HTML / CSS / JSON / YAML / XML / Markdown 等。
2. 自动排除 exe、dll、jar、class、图片、视频、压缩包等二进制文件。
3. 自动跳过 node_modules、.git、target、dist、build、venv 等目录。
4. 保留项目中的相对路径。
5. 自动排除输出文件本身，避免重复汇总。
6. 无需安装任何第三方库。
7. 支持命令行运行，也支持直接双击后输入目录。
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from typing import Iterable


# ============================================================
# 1. 支持的源码 / 文本文件扩展名
# ============================================================

SUPPORTED_EXTENSIONS = {
    # Java / JVM
    ".java", ".kt", ".kts", ".scala", ".groovy", ".gradle",

    # Python
    ".py", ".pyw", ".pyi",

    # JavaScript / TypeScript / Web
    ".js", ".mjs", ".cjs", ".jsx",
    ".ts", ".mts", ".cts", ".tsx",
    ".vue", ".svelte",
    ".html", ".htm", ".xhtml",
    ".css", ".scss", ".sass", ".less",

    # C / C++
    ".c", ".h", ".cc", ".cpp", ".cxx", ".hpp", ".hh", ".hxx",

    # C#
    ".cs", ".csx",

    # Go / Rust
    ".go", ".rs",

    # PHP / Ruby / Perl
    ".php", ".phtml",
    ".rb", ".rake",
    ".pl", ".pm",

    # Apple / Mobile
    ".swift", ".m", ".mm",
    ".dart",

    # Data / scientific
    ".r", ".rmd", ".jl", ".lua",

    # Shell / command / PowerShell
    ".sh", ".bash", ".zsh", ".fish",
    ".bat", ".cmd",
    ".ps1", ".psm1", ".psd1",

    # SQL / database
    ".sql", ".ddl", ".dml",

    # Configuration / data
    ".json", ".jsonc", ".json5",
    ".yaml", ".yml",
    ".xml",
    ".toml",
    ".ini", ".cfg", ".conf", ".config",
    ".properties",
    ".env",
    ".editorconfig",

    # Documentation / text
    ".md", ".markdown", ".txt", ".rst", ".adoc",

    # Template files
    ".jinja", ".jinja2", ".j2",
    ".twig",
    ".mustache", ".hbs", ".handlebars",
    ".ejs",

    # Build / project formats
    ".cmake",
    ".sln", ".csproj", ".fsproj", ".vbproj",
    ".vcxproj",
    ".pom",
    ".proto",
    ".graphql", ".gql",

    # Other languages
    ".fs", ".fsx", ".fsi",
    ".vb",
    ".hs", ".lhs",
    ".clj", ".cljs", ".cljc", ".edn",
    ".ex", ".exs",
    ".erl", ".hrl",
    ".sol",
    ".asm", ".s",
    ".v", ".sv", ".vhd", ".vhdl",
    ".tex",
}


# ============================================================
# 2. 无扩展名但常见的源码 / 配置文件
# ============================================================

SUPPORTED_FILENAMES = {
    "Dockerfile",
    "Containerfile",
    "Makefile",
    "GNUmakefile",
    "CMakeLists.txt",
    "Jenkinsfile",
    "Procfile",
    "Vagrantfile",
    "Gemfile",
    "Rakefile",
    "Podfile",
    "Fastfile",

    ".gitignore",
    ".gitattributes",
    ".dockerignore",
    ".npmignore",
    ".eslintignore",
    ".prettierignore",
    ".prettierrc",
    ".eslintrc",
    ".babelrc",
    ".nvmrc",
    ".npmrc",
    ".yarnrc",
    ".yarnrc.yml",
    ".editorconfig",
}


# ============================================================
# 3. 默认排除目录
# ============================================================

EXCLUDED_DIR_NAMES = {
    # Version control
    ".git", ".svn", ".hg",

    # IDE / editor
    ".idea", ".vscode",
    ".vs",

    # Java / JVM
    "target",
    ".gradle",
    ".mvn",

    # JavaScript / frontend
    "node_modules",
    "bower_components",
    ".next",
    ".nuxt",
    ".output",
    ".cache",
    ".parcel-cache",

    # Python
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    ".tox",
    ".nox",
    "venv",
    ".venv",
    "env",
    ".env",
    "site-packages",

    # Build outputs
    "dist",
    "build",
    "out",
    "bin",
    "obj",
    "coverage",
    ".coverage",
    "release",
    "debug",

    # Misc
    ".DS_Store",
}


# ============================================================
# 4. 明确不应该读取的二进制 / 资源扩展名
# ============================================================

BINARY_EXTENSIONS = {
    # Executables / libraries
    ".exe", ".dll", ".so", ".dylib", ".bin",
    ".class", ".jar", ".war", ".ear",
    ".o", ".obj", ".a", ".lib",
    ".pdb",

    # Archives
    ".zip", ".rar", ".7z", ".tar", ".gz", ".bz2", ".xz",
    ".tgz", ".apk", ".ipa",

    # Images
    ".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp",
    ".ico", ".tif", ".tiff", ".psd", ".ai",

    # Audio / video
    ".mp3", ".wav", ".flac", ".aac", ".ogg",
    ".mp4", ".avi", ".mov", ".mkv", ".wmv", ".webm",

    # Documents / binary office formats
    ".pdf", ".doc", ".docx", ".xls", ".xlsx",
    ".ppt", ".pptx",

    # Fonts
    ".ttf", ".otf", ".woff", ".woff2", ".eot",

    # Databases / compiled data
    ".db", ".sqlite", ".sqlite3",
    ".pyc", ".pyo",
    ".pickle", ".pkl",

    # Misc
    ".iso", ".dmg",
}


SEPARATOR = "=" * 88


def normalize_path(path: Path) -> str:
    """将路径统一显示为正斜杠形式，便于跨平台阅读。"""
    return path.as_posix()


def is_probably_binary(file_path: Path, sample_size: int = 8192) -> bool:
    """
    简单判断文件是否可能为二进制文件。
    如果样本中存在 NUL 字节，则基本可判断为二进制。
    """
    try:
        with file_path.open("rb") as f:
            sample = f.read(sample_size)
        return b"\x00" in sample
    except OSError:
        return True


def read_text_file(file_path: Path) -> tuple[str | None, str | None]:
    """
    尝试用常见编码读取文本文件。

    返回:
        (文本内容, 使用的编码)

    读取失败:
        (None, None)
    """
    encodings = (
        "utf-8-sig",
        "utf-8",
        "gb18030",
        "big5",
        "shift_jis",
    )

    for encoding in encodings:
        try:
            return file_path.read_text(encoding=encoding), encoding
        except UnicodeDecodeError:
            continue
        except OSError:
            return None, None

    # 最后的宽容模式：
    # latin-1 可以映射任意单字节内容，但只有在前面确认不是二进制后才使用。
    try:
        return file_path.read_text(encoding="latin-1"), "latin-1"
    except OSError:
        return None, None


def is_supported_file(
    file_path: Path,
    include_unknown_text: bool = False,
) -> bool:
    """判断一个文件是否应该被纳入汇总。"""

    if not file_path.is_file():
        return False

    suffix = file_path.suffix.lower()

    if suffix in BINARY_EXTENSIONS:
        return False

    if file_path.name in SUPPORTED_FILENAMES:
        return True

    if suffix in SUPPORTED_EXTENSIONS:
        return True

    if include_unknown_text:
        return not is_probably_binary(file_path)

    return False


def should_skip_directory(dir_name: str, extra_excludes: set[str]) -> bool:
    """判断目录是否应该跳过。"""
    return dir_name in EXCLUDED_DIR_NAMES or dir_name in extra_excludes


def collect_files(
    root: Path,
    output_file: Path,
    include_unknown_text: bool,
    extra_excludes: set[str],
) -> list[Path]:
    """
    遍历目标目录并收集需要汇总的文件。
    """
    files: list[Path] = []

    # resolve(strict=False) 可以处理尚不存在的输出文件。
    output_resolved = output_file.resolve(strict=False)

    for current_root, dir_names, file_names in os.walk(root):
        current_path = Path(current_root)

        # 原地修改 dir_names，阻止 os.walk 进入排除目录
        dir_names[:] = sorted(
            d
            for d in dir_names
            if not should_skip_directory(d, extra_excludes)
        )

        for file_name in sorted(file_names):
            file_path = current_path / file_name

            try:
                if file_path.resolve(strict=False) == output_resolved:
                    continue
            except OSError:
                pass

            if is_supported_file(file_path, include_unknown_text):
                files.append(file_path)

    # 按相对于项目根目录的路径排序
    files.sort(key=lambda p: normalize_path(p.relative_to(root)).lower())
    return files


def write_merged_file(
    root: Path,
    files: Iterable[Path],
    output_file: Path,
    max_file_size_mb: float,
) -> tuple[int, int, list[str]]:
    """
    将源码文件写入最终 TXT。

    返回:
        成功文件数量,
        跳过文件数量,
        跳过原因列表
    """
    success_count = 0
    skipped_count = 0
    skipped_messages: list[str] = []

    max_bytes = int(max_file_size_mb * 1024 * 1024)

    output_file.parent.mkdir(parents=True, exist_ok=True)

    with output_file.open("w", encoding="utf-8", newline="\n") as out:
        out.write("PROJECT CODE MERGED FILE\n")
        out.write(f"Root: {root}\n")
        out.write(f"Generated by: code_merge.py\n")
        out.write(SEPARATOR + "\n\n")

        for file_path in files:
            relative_path = file_path.relative_to(root)
            relative_display = normalize_path(relative_path)

            try:
                size = file_path.stat().st_size
            except OSError as exc:
                skipped_count += 1
                skipped_messages.append(
                    f"{relative_display} -> 无法读取文件信息: {exc}"
                )
                continue

            if size > max_bytes:
                skipped_count += 1
                skipped_messages.append(
                    f"{relative_display} -> 文件过大 "
                    f"({size / 1024 / 1024:.2f} MB > {max_file_size_mb:.2f} MB)"
                )
                continue

            if is_probably_binary(file_path):
                skipped_count += 1
                skipped_messages.append(
                    f"{relative_display} -> 检测为二进制文件"
                )
                continue

            content, encoding = read_text_file(file_path)

            if content is None:
                skipped_count += 1
                skipped_messages.append(
                    f"{relative_display} -> 文本读取失败"
                )
                continue

            out.write(SEPARATOR + "\n")
            out.write(f"FILE: {relative_display}\n")
            out.write(f"ENCODING: {encoding}\n")
            out.write(SEPARATOR + "\n\n")

            out.write(content)

            # 保证文件内容之后至少有一个换行
            if content and not content.endswith(("\n", "\r")):
                out.write("\n")

            out.write("\n\n")
            success_count += 1

        out.write(SEPARATOR + "\n")
        out.write("MERGE SUMMARY\n")
        out.write(SEPARATOR + "\n")
        out.write(f"Included files: {success_count}\n")
        out.write(f"Skipped files:  {skipped_count}\n")

        if skipped_messages:
            out.write("\nSkipped details:\n")
            for msg in skipped_messages:
                out.write(f"- {msg}\n")

    return success_count, skipped_count, skipped_messages


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "递归汇总项目源码到一个 TXT 文件中。"
            "默认只读取主流源码、脚本、配置和文本文件。"
        )
    )

    parser.add_argument(
        "folder",
        nargs="?",
        help="需要扫描的目标项目目录。省略时进入交互输入模式。",
    )

    parser.add_argument(
        "-o",
        "--output",
        default="result.txt",
        help=(
            "输出文件路径。默认: result.txt。"
            "若为相对路径，则默认生成在目标项目根目录下。"
        ),
    )

    parser.add_argument(
        "--max-size",
        type=float,
        default=5.0,
        help="单个文件最大读取大小，单位 MB。默认: 5 MB。",
    )

    parser.add_argument(
        "--include-unknown-text",
        action="store_true",
        help=(
            "同时收录未知扩展名、但检测后属于文本的文件。"
            "默认关闭，以减少无关文件。"
        ),
    )

    parser.add_argument(
        "--exclude-dir",
        action="append",
        default=[],
        help=(
            "额外排除某个目录名称，可重复使用。"
            "例如: --exclude-dir logs --exclude-dir temp"
        ),
    )

    return parser.parse_args()


def clean_input_path(value: str) -> str:
    """
    去掉用户在 Windows 中拖拽路径时可能携带的引号。
    """
    value = value.strip()

    if len(value) >= 2:
        if (
            (value.startswith('"') and value.endswith('"'))
            or (value.startswith("'") and value.endswith("'"))
        ):
            value = value[1:-1]

    return value.strip()


def interactive_folder_input() -> str:
    print()
    print("请输入需要汇总代码的项目文件夹路径。")
    print("也可以直接把文件夹拖到这个窗口中，然后按回车。")
    print()

    return clean_input_path(input("项目目录: "))


def main() -> int:
    args = parse_args()

    folder_value = clean_input_path(args.folder) if args.folder else interactive_folder_input()

    if not folder_value:
        print("[错误] 未提供目标目录。")
        return 1

    root = Path(folder_value).expanduser()

    if not root.exists():
        print(f"[错误] 目录不存在: {root}")
        return 1

    if not root.is_dir():
        print(f"[错误] 指定路径不是文件夹: {root}")
        return 1

    root = root.resolve()

    output_arg = Path(args.output).expanduser()

    if output_arg.is_absolute():
        output_file = output_arg.resolve(strict=False)
    else:
        output_file = (root / output_arg).resolve(strict=False)

    if args.max_size <= 0:
        print("[错误] --max-size 必须大于 0。")
        return 1

    extra_excludes = set(args.exclude_dir)

    print()
    print("正在扫描项目...")
    print(f"项目目录: {root}")
    print(f"输出文件: {output_file}")
    print()

    files = collect_files(
        root=root,
        output_file=output_file,
        include_unknown_text=args.include_unknown_text,
        extra_excludes=extra_excludes,
    )

    success_count, skipped_count, skipped_messages = write_merged_file(
        root=root,
        files=files,
        output_file=output_file,
        max_file_size_mb=args.max_size,
    )

    print(SEPARATOR)
    print("代码汇总完成")
    print(SEPARATOR)
    print(f"成功汇总: {success_count} 个文件")
    print(f"扫描后跳过: {skipped_count} 个文件")
    print(f"结果文件:   {output_file}")

    if skipped_messages:
        print()
        print("部分文件被跳过，详细原因已写入 result.txt 末尾。")

    print()

    # 双击运行时，Windows 控制台不要立即关闭。
    # 命令行带参数运行时则不暂停。
    if args.folder is None and sys.stdin.isatty():
        try:
            input("按回车键退出...")
        except EOFError:
            pass

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
