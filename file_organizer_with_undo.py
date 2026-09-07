from pathlib import Path
import json
import shutil
from datetime import datetime


# =========================
# 文件分类规则
# =========================
CATEGORIES = {
    "Images": [
        ".jpg", ".jpeg", ".png", ".gif", ".webp",
        ".bmp", ".svg", ".ico", ".tiff"
    ],
    "Videos": [
        ".mp4", ".avi", ".mkv", ".mov",
        ".wmv", ".flv", ".webm", ".m4v"
    ],
    "Documents": [
        ".pdf", ".doc", ".docx",
        ".txt", ".xlsx", ".xls",
        ".ppt", ".pptx",
        ".csv", ".md"
    ],
    "Archives": [
        ".zip", ".rar", ".7z",
        ".tar", ".gz", ".bz2"
    ],
    "Programs": [
        ".exe", ".msi",
        ".bat", ".cmd"
    ],
    "Audio": [
        ".mp3", ".wav", ".flac",
        ".aac", ".m4a", ".ogg"
    ],
    "Code": [
        ".py", ".js", ".ts",
        ".vue", ".jsx", ".tsx",
        ".html", ".css",
        ".java", ".cpp", ".c",
        ".json", ".xml", ".sql"
    ],
}


# 整理历史记录文件名
HISTORY_FILE_NAME = ".file_organizer_history.json"


def get_category(extension: str) -> str:
    """根据扩展名获取分类名称，未匹配则归入 Others。"""
    extension = extension.lower()

    for category, extensions in CATEGORIES.items():
        if extension in extensions:
            return category

    return "Others"


def get_unique_path(target_path: Path) -> Path:
    """
    如果目标文件已存在，则自动生成：
    file.txt
    file (1).txt
    file (2).txt
    ...
    防止覆盖已有文件。
    """
    if not target_path.exists():
        return target_path

    parent = target_path.parent
    stem = target_path.stem
    suffix = target_path.suffix

    index = 1

    while True:
        new_path = parent / f"{stem} ({index}){suffix}"

        if not new_path.exists():
            return new_path

        index += 1


def get_history_path(folder: Path) -> Path:
    """返回当前整理目录对应的历史记录文件路径。"""
    return folder / HISTORY_FILE_NAME


def save_history(folder: Path, moved_items: list[dict]) -> None:
    """
    保存最近一次成功整理的移动记录。
    记录 source / target，供撤销功能使用。
    """
    history_path = get_history_path(folder)

    data = {
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "folder": str(folder),
        "moves": [
            {
                "source": str(item["source"]),
                "target": str(item["target"]),
            }
            for item in moved_items
        ],
    }

    with history_path.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def load_history(folder: Path):
    """读取最近一次整理历史。"""
    history_path = get_history_path(folder)

    if not history_path.exists():
        return None

    try:
        with history_path.open("r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return None


def delete_history(folder: Path) -> None:
    """撤销成功后删除历史记录。"""
    history_path = get_history_path(folder)

    try:
        if history_path.exists():
            history_path.unlink()
    except OSError:
        pass


def build_move_plan(folder: Path) -> list[dict]:
    """
    扫描当前目录并生成移动计划。
    注意：
    - 不递归扫描子文件夹
    - 不处理整理器脚本自身
    - 不处理历史记录文件
    """
    move_plan = []

    try:
        current_script = Path(__file__).resolve()
    except NameError:
        current_script = None

    history_path = get_history_path(folder).resolve()

    for file_path in folder.iterdir():

        if not file_path.is_file():
            continue

        try:
            resolved = file_path.resolve()

            if current_script and resolved == current_script:
                continue

            if resolved == history_path:
                continue

        except OSError:
            pass

        category = get_category(file_path.suffix.lower())

        target_folder = folder / category
        target_path = target_folder / file_path.name
        target_path = get_unique_path(target_path)

        move_plan.append({
            "source": file_path,
            "target": target_path,
            "category": category,
        })

    return move_plan


def preview_move_plan(move_plan: list[dict]) -> None:
    """显示整理预览。"""
    if not move_plan:
        print("\n没有发现需要整理的文件。")
        return

    print("\n" + "=" * 72)
    print("文件整理预览")
    print("=" * 72)

    category_count = {}

    for index, item in enumerate(move_plan, start=1):
        source = item["source"]
        target = item["target"]
        category = item["category"]

        category_count[category] = category_count.get(category, 0) + 1

        print(f"{index:>3}. {source.name}")
        print(f"     → {category}/{target.name}")

    print("\n" + "-" * 72)
    print(f"预计移动文件：{len(move_plan)} 个")

    print("\n分类统计：")
    for category, count in sorted(category_count.items()):
        print(f"  {category:<12} {count} 个")

    print("=" * 72)


def execute_move_plan(folder: Path, move_plan: list[dict]) -> None:
    """
    正式执行整理，并记录实际成功移动的文件。
    """
    moved_items = []
    failed_count = 0

    print("\n开始整理文件...\n")

    for item in move_plan:
        source = item["source"]
        target = item["target"]
        category = item["category"]

        try:
            if not source.exists():
                print(f"⚠ 文件不存在，跳过：{source.name}")
                failed_count += 1
                continue

            target.parent.mkdir(parents=True, exist_ok=True)

            # 执行前再次防止同名覆盖
            final_target = get_unique_path(target)

            shutil.move(str(source), str(final_target))

            moved_items.append({
                "source": source,
                "target": final_target,
            })

            print(f"✔ {source.name}  →  {category}/{final_target.name}")

        except Exception as e:
            print(f"❌ 移动失败：{source.name}")
            print(f"   原因：{e}")
            failed_count += 1

    if moved_items:
        try:
            save_history(folder, moved_items)
        except Exception as e:
            print("\n⚠ 文件已整理成功，但历史记录保存失败。")
            print(f"   原因：{e}")
            print("   本次整理可能无法使用自动撤销功能。")

    print("\n" + "=" * 50)
    print("整理完成")
    print(f"成功移动：{len(moved_items)} 个")
    print(f"失败/跳过：{failed_count} 个")

    if moved_items:
        print("已保存“最近一次整理”记录，可从菜单执行撤销。")

    print("=" * 50)


def organize_files(folder: Path) -> None:
    """整理文件主流程：扫描 → 预览 → 确认 → 执行。"""
    move_plan = build_move_plan(folder)

    preview_move_plan(move_plan)

    if not move_plan:
        return

    print("\n以上仅为预览，目前尚未移动任何文件。")

    answer = input("\n确认执行整理？[y/N]：").strip().lower()

    if answer not in ("y", "yes"):
        print("\n已取消，没有修改任何文件。")
        return

    execute_move_plan(folder, move_plan)


def build_undo_plan(folder: Path):
    """
    根据最近一次历史记录生成撤销计划。

    返回：
        undo_plan: 可撤销项目
        warnings: 无法直接撤销的项目
        history: 历史记录
    """
    history = load_history(folder)

    if not history or not history.get("moves"):
        return [], ["没有找到可用的最近一次整理记录。"], history

    undo_plan = []
    warnings = []

    for item in history["moves"]:
        original_path = Path(item["source"])
        current_path = Path(item["target"])

        if not current_path.exists():
            warnings.append(
                f"文件已不存在，无法撤销：{current_path}"
            )
            continue

        # 原位置已经重新出现同名文件时，不覆盖
        if original_path.exists():
            warnings.append(
                f"原位置已有同名文件，跳过撤销：{original_path}"
            )
            continue

        undo_plan.append({
            "source": current_path,
            "target": original_path,
        })

    return undo_plan, warnings, history


def preview_undo_plan(folder: Path):
    """预览撤销操作。"""
    undo_plan, warnings, history = build_undo_plan(folder)

    print("\n" + "=" * 72)
    print("撤销预览")
    print("=" * 72)

    if history:
        created_at = history.get("created_at", "未知时间")
        print(f"最近一次整理时间：{created_at}\n")

    if undo_plan:
        for index, item in enumerate(undo_plan, start=1):
            print(f"{index:>3}. {item['source']}")
            print(f"     → {item['target']}")

        print(f"\n预计恢复文件：{len(undo_plan)} 个")
    else:
        print("没有可直接撤销的文件。")

    if warnings:
        print("\n注意：")
        for warning in warnings:
            print(f"  ⚠ {warning}")

    print("=" * 72)

    return undo_plan, warnings, history


def cleanup_empty_category_folders(folder: Path) -> None:
    """
    撤销后尝试删除空的分类文件夹。
    仅删除本脚本定义的分类目录以及 Others。
    """
    category_names = set(CATEGORIES.keys()) | {"Others"}

    for category in category_names:
        category_folder = folder / category

        try:
            if category_folder.exists() and category_folder.is_dir():
                if not any(category_folder.iterdir()):
                    category_folder.rmdir()
        except OSError:
            pass


def undo_last_organization(folder: Path) -> None:
    """
    撤销最近一次整理。

    安全策略：
    - 先预览
    - 不覆盖原位置已有同名文件
    - 只撤销历史记录中实际成功移动的文件
    """
    undo_plan, warnings, history = preview_undo_plan(folder)

    if not history:
        return

    if not undo_plan:
        print("\n没有可执行的撤销项目。")
        return

    print("\n以上仅为撤销预览，目前尚未移动任何文件。")

    answer = input("\n确认撤销最近一次整理？[y/N]：").strip().lower()

    if answer not in ("y", "yes"):
        print("\n已取消撤销，没有修改任何文件。")
        return

    success_count = 0
    failed_count = 0

    print("\n开始撤销...\n")

    for item in reversed(undo_plan):
        source = item["source"]
        target = item["target"]

        try:
            if not source.exists():
                print(f"⚠ 文件不存在，跳过：{source}")
                failed_count += 1
                continue

            if target.exists():
                print(f"⚠ 原位置已有同名文件，跳过：{target}")
                failed_count += 1
                continue

            target.parent.mkdir(parents=True, exist_ok=True)

            shutil.move(str(source), str(target))

            print(f"✔ {source.name}  →  {target}")
            success_count += 1

        except Exception as e:
            print(f"❌ 撤销失败：{source}")
            print(f"   原因：{e}")
            failed_count += 1

    cleanup_empty_category_folders(folder)

    # 只有所有历史记录里的移动都成功恢复，才删除历史。
    total_history_moves = len(history.get("moves", []))

    if success_count == total_history_moves:
        delete_history(folder)
        history_status = "最近一次整理记录已清除。"
    else:
        history_status = (
            "由于部分文件未能恢复，历史记录已保留，"
            "便于你检查后再次尝试。"
        )

    print("\n" + "=" * 50)
    print("撤销完成")
    print(f"成功恢复：{success_count} 个")
    print(f"失败/跳过：{failed_count + len(warnings)} 个")
    print(history_status)
    print("=" * 50)


def validate_folder(folder_path: str):
    """校验用户输入的目录路径。"""
    folder_path = folder_path.strip().strip('"').strip("'")

    if not folder_path:
        print("\n❌ 未输入文件夹路径。")
        return None

    folder = Path(folder_path).expanduser().resolve()

    if not folder.exists():
        print(f"\n❌ 文件夹不存在：{folder}")
        return None

    if not folder.is_dir():
        print(f"\n❌ 目标不是文件夹：{folder}")
        return None

    return folder


def main():
    print("=" * 56)
    print("Python 文件归类整理器")
    print("支持：预览整理 / 防覆盖 / 撤销最近一次整理")
    print("=" * 56)

    folder_path = input(
        "\n请输入需要整理的文件夹路径：\n> "
    )

    folder = validate_folder(folder_path)

    if folder is None:
        input("\n按 Enter 键退出...")
        return

    while True:
        print("\n当前目录：")
        print(folder)

        print("\n请选择操作：")
        print("  1. 预览并整理文件")
        print("  2. 撤销最近一次整理")
        print("  3. 退出")

        choice = input("\n请输入选项 [1/2/3]：").strip()

        if choice == "1":
            organize_files(folder)

        elif choice == "2":
            undo_last_organization(folder)

        elif choice == "3":
            print("\n已退出。")
            break

        else:
            print("\n❌ 无效选项，请输入 1、2 或 3。")


if __name__ == "__main__":
    main()
