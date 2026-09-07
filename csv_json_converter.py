#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
csv_json_converter.py
======================
一个简单实用的 CSV / JSON 批量互转命令行工具。

功能：
1. 单文件转换：CSV -> JSON，或 JSON -> CSV（自动根据后缀判断方向，也可手动指定）。
2. 批量转换：给定一个文件夹，自动转换其中所有 .csv 或 .json 文件。
3. 支持自定义分隔符（如 CSV 用 ; 或 \t 分隔）。
4. 支持 JSON 数组套对象（最常见结构） <-> CSV 表格 的互转。
5. 支持嵌套 JSON 字段（转 CSV 时自动展开为 a.b.c 形式的列名）。
6. 自动处理常见编码问题（默认 UTF-8，支持 UTF-8-SIG / GBK 等，出错自动尝试兜底）。

用法示例：
    # 单文件：CSV 转 JSON
    python csv_json_converter.py convert data.csv

    # 单文件：JSON 转 CSV
    python csv_json_converter.py convert data.json

    # 指定输出文件名
    python csv_json_converter.py convert data.csv -o result.json

    # 批量转换整个文件夹（把该文件夹里所有 csv 转成 json，所有 json 转成 csv）
    python csv_json_converter.py batch ./data_folder

    # 批量转换，只处理 csv -> json，输出到指定目录
    python csv_json_converter.py batch ./data_folder -o ./output_folder --direction csv2json

    # 自定义 CSV 分隔符（例如分号分隔）
    python csv_json_converter.py convert data.csv --delimiter ";"

作者：Claude
"""

import argparse
import csv
import json
import sys
from pathlib import Path


# ---------------------------------------------------------------------------
# 核心转换函数
# ---------------------------------------------------------------------------

def flatten_dict(d, parent_key="", sep="."):
    """
    将嵌套字典展开为单层字典，键名用 sep 连接。
    例如 {"a": {"b": 1}} -> {"a.b": 1}
    列表会被转成 JSON 字符串保存，避免破坏表格结构。
    """
    items = {}
    for k, v in d.items():
        new_key = f"{parent_key}{sep}{k}" if parent_key else str(k)
        if isinstance(v, dict):
            items.update(flatten_dict(v, new_key, sep=sep))
        elif isinstance(v, list):
            items[new_key] = json.dumps(v, ensure_ascii=False)
        else:
            items[new_key] = v
    return items


def unflatten_dict(d, sep="."):
    """
    将 flatten_dict 展开的单层字典还原为嵌套字典。
    例如 {"a.b": 1} -> {"a": {"b": 1}}
    """
    result = {}
    for compound_key, value in d.items():
        keys = compound_key.split(sep)
        cursor = result
        for key in keys[:-1]:
            cursor = cursor.setdefault(key, {})
        cursor[keys[-1]] = value
    return result


def read_text_with_fallback(path):
    """尝试用常见编码读取文件，优先 utf-8-sig（可处理 BOM），失败则尝试 gbk。"""
    encodings = ["utf-8-sig", "utf-8", "gbk"]
    last_err = None
    for enc in encodings:
        try:
            with open(path, "r", encoding=enc, newline="") as f:
                return f.read(), enc
        except (UnicodeDecodeError, UnicodeError) as e:
            last_err = e
            continue
    raise last_err


def csv_to_json(csv_path, json_path, delimiter=",", indent=2, nested=True):
    """
    读取 CSV 文件，转换为 JSON 文件（列表套字典的结构）。
    如果 nested=True，会尝试把形如 "a.b" 的列名还原成嵌套结构。
    """
    raw_text, used_encoding = read_text_with_fallback(csv_path)
    reader = csv.DictReader(raw_text.splitlines(), delimiter=delimiter)

    records = []
    for row in reader:
        cleaned = {}
        for k, v in row.items():
            if v is None:
                cleaned[k] = None
                continue
            # 尝试把看起来像数字 / 布尔值的字符串还原为对应类型
            cleaned[k] = _infer_type(v)
        if nested:
            cleaned = unflatten_dict(cleaned)
        records.append(cleaned)

    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(records, f, ensure_ascii=False, indent=indent)

    return len(records), used_encoding


def json_to_csv(json_path, csv_path, delimiter=",", nested=True):
    """
    读取 JSON 文件（须为列表套字典，或单个字典也会自动包装成列表），转换为 CSV。
    嵌套字段会被展开为 "a.b" 形式的列名。
    """
    raw_text, used_encoding = read_text_with_fallback(json_path)
    data = json.loads(raw_text)

    if isinstance(data, dict):
        data = [data]
    if not isinstance(data, list):
        raise ValueError("JSON 顶层结构必须是对象数组（list of dict）或单个对象（dict）")

    if len(data) == 0:
        # 空数据也生成一个空 CSV，避免报错
        with open(csv_path, "w", newline="", encoding="utf-8-sig") as f:
            f.write("")
        return 0, used_encoding

    flat_rows = []
    fieldnames = []
    for item in data:
        if not isinstance(item, dict):
            raise ValueError("JSON 数组中的每一项都必须是对象（dict），无法转换为表格行")
        flat = flatten_dict(item) if nested else item
        flat_rows.append(flat)
        for key in flat.keys():
            if key not in fieldnames:
                fieldnames.append(key)

    # 用 utf-8-sig 写出，方便 Excel 直接打开不乱码
    with open(csv_path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, delimiter=delimiter, extrasaction="ignore")
        writer.writeheader()
        for row in flat_rows:
            writer.writerow(row)

    return len(flat_rows), used_encoding


def _infer_type(value):
    """把 CSV 里的字符串尽量还原成 int / float / bool / None，其余保持字符串。"""
    if value == "":
        return ""
    if value.lower() == "true":
        return True
    if value.lower() == "false":
        return False
    if value.lower() in ("null", "none"):
        return None
    try:
        if "." in value or "e" in value.lower():
            return float(value)
        return int(value)
    except ValueError:
        return value


# ---------------------------------------------------------------------------
# 单文件转换入口
# ---------------------------------------------------------------------------

def convert_single_file(input_path, output_path=None, direction=None,
                         delimiter=",", nested=True):
    input_path = Path(input_path)
    if not input_path.exists():
        raise FileNotFoundError(f"找不到文件: {input_path}")

    suffix = input_path.suffix.lower()
    if direction is None:
        if suffix == ".csv":
            direction = "csv2json"
        elif suffix == ".json":
            direction = "json2csv"
        else:
            raise ValueError(f"无法从后缀 '{suffix}' 判断转换方向，请用 --direction 手动指定 csv2json 或 json2csv")

    if direction == "csv2json":
        out_path = Path(output_path) if output_path else input_path.with_suffix(".json")
        count, enc = csv_to_json(input_path, out_path, delimiter=delimiter, nested=nested)
        print(f"[OK] CSV -> JSON  {input_path.name} -> {out_path.name}  "
              f"(共 {count} 条记录, 读取编码: {enc})")
    elif direction == "json2csv":
        out_path = Path(output_path) if output_path else input_path.with_suffix(".csv")
        count, enc = json_to_csv(input_path, out_path, delimiter=delimiter, nested=nested)
        print(f"[OK] JSON -> CSV  {input_path.name} -> {out_path.name}  "
              f"(共 {count} 行, 读取编码: {enc})")
    else:
        raise ValueError("direction 必须是 'csv2json' 或 'json2csv'")

    return out_path


# ---------------------------------------------------------------------------
# 批量转换入口
# ---------------------------------------------------------------------------

def convert_batch(input_dir, output_dir=None, direction="both",
                   delimiter=",", nested=True):
    input_dir = Path(input_dir)
    if not input_dir.is_dir():
        raise NotADirectoryError(f"不是一个有效的文件夹: {input_dir}")

    output_dir = Path(output_dir) if output_dir else input_dir
    output_dir.mkdir(parents=True, exist_ok=True)

    targets = []
    if direction in ("both", "csv2json"):
        targets += [(p, "csv2json") for p in sorted(input_dir.glob("*.csv"))]
    if direction in ("both", "json2csv"):
        targets += [(p, "json2csv") for p in sorted(input_dir.glob("*.json"))]

    if not targets:
        print("未找到任何待转换的 .csv / .json 文件。")
        return

    success, failed = 0, []
    for path, dir_ in targets:
        out_ext = ".json" if dir_ == "csv2json" else ".csv"
        out_path = output_dir / (path.stem + out_ext)
        try:
            convert_single_file(path, out_path, direction=dir_,
                                 delimiter=delimiter, nested=nested)
            success += 1
        except Exception as e:
            failed.append((path.name, str(e)))
            print(f"[FAIL] {path.name}: {e}")

    print(f"\n批量转换完成：成功 {success} 个，失败 {len(failed)} 个。")
    if failed:
        print("失败列表：")
        for name, err in failed:
            print(f"  - {name}: {err}")


# ---------------------------------------------------------------------------
# 命令行入口
# ---------------------------------------------------------------------------

def build_arg_parser():
    parser = argparse.ArgumentParser(
        description="CSV / JSON 批量互转工具",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sub = parser.add_subparsers(dest="command", required=True)

    # convert 子命令：单文件转换
    p_convert = sub.add_parser("convert", help="转换单个文件")
    p_convert.add_argument("input", help="输入文件路径（.csv 或 .json）")
    p_convert.add_argument("-o", "--output", help="输出文件路径（不指定则自动生成）")
    p_convert.add_argument("--direction", choices=["csv2json", "json2csv"],
                            default=None, help="转换方向，不指定则根据文件后缀自动判断")
    p_convert.add_argument("--delimiter", default=",", help="CSV 分隔符，默认为逗号")
    p_convert.add_argument("--no-nested", action="store_true",
                            help="关闭嵌套字段展开/还原（默认开启）")

    # batch 子命令：批量转换文件夹
    p_batch = sub.add_parser("batch", help="批量转换整个文件夹")
    p_batch.add_argument("input_dir", help="输入文件夹路径")
    p_batch.add_argument("-o", "--output", dest="output_dir", default=None,
                          help="输出文件夹路径（不指定则输出到原文件夹）")
    p_batch.add_argument("--direction", choices=["both", "csv2json", "json2csv"],
                          default="both", help="批量转换方向，默认双向都转")
    p_batch.add_argument("--delimiter", default=",", help="CSV 分隔符，默认为逗号")
    p_batch.add_argument("--no-nested", action="store_true",
                          help="关闭嵌套字段展开/还原（默认开启）")

    return parser


def main():
    parser = build_arg_parser()
    args = parser.parse_args()

    nested = not getattr(args, "no_nested", False)

    try:
        if args.command == "convert":
            convert_single_file(
                args.input,
                output_path=args.output,
                direction=args.direction,
                delimiter=args.delimiter,
                nested=nested,
            )
        elif args.command == "batch":
            convert_batch(
                args.input_dir,
                output_dir=args.output_dir,
                direction=args.direction,
                delimiter=args.delimiter,
                nested=nested,
            )
    except Exception as e:
        print(f"错误: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
