# FileDiff Pro — 文件差异比较与合并工具

类似 Beyond Compare 的轻量级文件/文件夹差异比较工具，基于 Python + PyQt5 + difflib 开发。

---

## 功能特性

| 功能 | 说明 |
|------|------|
| 📁 文件夹比较 | 递归比较两个目录，树形展示差异 |
| 📄 文件比较 | 直接比较两个单文件 |
| 🎨 差异高亮 | 行级差异高亮（新增/删除/修改） |
| 🔄 同步操作 | 左→右 / 右→左 复制、删除、重命名 |
| ✂ 合并操作 | 选中右侧差异行，一键合并到左侧 |
| 🔍 过滤显示 | 可选择隐藏相同文件，专注差异 |
| ⏩ 差异导航 | 上一处/下一处差异快速跳转 |
| 🔀 同步滚动 | 左右面板同步滚动对比 |
| 💾 编码支持 | 自动检测 UTF-8 / GBK / Latin-1 |
| ⚙ 设置记忆 | 自动记住上次比较路径 |

---

## 快速开始

### 1. 安装依赖

```bash
pip install -r requirements.txt
```

### 2. 启动工具

```bash
python main.py
```

---

## 目录结构

```
filediff/
├── main.py                 # 程序入口
├── requirements.txt        # 依赖声明
├── README.md               # 本文档
├── core/
│   ├── __init__.py
│   ├── diff_engine.py      # DiffThread + 差异算法
│   └── sync_ops.py         # 同步/合并操作
└── ui/
    ├── __init__.py
    ├── main_window.py      # 主窗口
    ├── diff_tree.py        # 差异结果树
    ├── diff_viewer.py      # 并排文本查看器
    └── highlighter.py      # DiffHighlighter
```

---

## 主要类说明

### `DiffThread` (core/diff_engine.py)
- 继承 `QThread`，在后台递归比较文件/目录
- 发出信号：`progress(int)`, `status_msg(str)`, `result(list)`, `error(str)`, `finished_ok()`
- 使用 MD5 哈希快速判断文件是否相同

### `DiffHighlighter` (ui/highlighter.py)
- 继承 `QSyntaxHighlighter`
- 根据行标签（`add`/`del`/`chg`/`eq`）对文本行着色高亮
- 通过 `set_line_tags(tags)` 外部设置标签列表

### `DiffTreeWidget` (ui/diff_tree.py)
- 继承 `QTreeWidget`，树形展示 `DiffNode` 差异结果
- 右键菜单支持：复制、删除、重命名等同步操作
- 双击文件触发打开差异查看器

### `DiffViewerWindow` (ui/diff_viewer.py)
- 并排双面板文本差异查看窗口
- 支持同步滚动、差异导航、保存、合并操作

---

## 操作说明

1. **选择路径**：分别点击左/右侧的"📄 文件"或"📁 文件夹"按钮选择路径
2. **开始比较**：点击绿色"▶ 开始比较"按钮
3. **查看差异**：在树中**双击**一个差异文件，打开并排对比窗口
4. **同步文件**：在树中右键任意节点，选择同步方向
5. **合并行**：在对比窗口右侧选中差异行，点击"⇒ 合并右侧选中行到左侧"

---

## 颜色说明

| 颜色 | 含义 |
|------|------|
| 🟡 黄色 | 内容不同（Modified） |
| 🔵 蓝色 | 仅左侧存在（Left Only） |
| ⚫ 灰色 | 仅右侧存在（Right Only） |
| 🟢 绿色 | 完全相同（Identical） |
| 🟠 橙色 | 类型变化（Type Changed） |

在文本对比窗口：

| 背景色 | 含义 |
|--------|------|
| 深绿 | 新增行（仅右侧有） |
| 深红 | 删除行（仅左侧有） |
| 深黄 | 修改行 |
| 默认 | 相同行 |
