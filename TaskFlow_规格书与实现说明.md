# TaskFlow 全屏应用 —— 规格书与实现说明

> 版本 1.0.0 ｜ 单文件 `taskflow.py` ｜ Python ≥ 3.9 ｜ 唯一依赖 `textual`
> 测试环境：Python 3.12 + Textual 8.2.8（无头自动化测试 40+ 断言全部通过）

---

# 第一部分：规格书

## 1. 目标

用一个**完整的全屏应用**演示 Textual 构建“真实产品”所需的全部要素：多页面导航、多种组件、带校验的表单、模态对话框、数据持久化、主题与设置。业务载体选用任务管理，因为它天然覆盖列表、看板、统计、表单等典型界面。

## 2. 运行

```bash
pip install textual
python taskflow.py                  # 数据保存在 ~/.taskflow/data.json（首次自动写入演示数据）
python taskflow.py --data ./my.json # 指定数据文件
python taskflow.py --demo           # 内存演示，不读写磁盘
```

## 3. 页面清单

| 页面 | 类 | 进入方式 | 主要组件 |
|---|---|---|---|
| 仪表盘 | `DashboardScreen` | `1` | Grid 统计卡片、`Digits`、`ProgressBar`、`Sparkline`、`DataTable`、`Static` |
| 任务列表 | `TasksScreen` | `2` | `Input` 搜索、`Select` ×2 筛选、可排序 `DataTable`、`Markdown` 详情 |
| 看板 | `BoardScreen` | `3` | 3 × `ListView`、自定义 `CardItem`、`border_title` 计数 |
| 设置 | `SettingsScreen` | `4` | `TabbedContent`/`TabPane`、`Select`、`Switch`、`Input`、`Button`、`Markdown` |
| 任务表单 | `TaskFormScreen` | `n` / 回车编辑 | `Input`（含校验）、`TextArea`、`RadioSet`、`Select`、`Switch`、`Checkbox`、`Button` |
| 确认框 | `ConfirmScreen` | 删除/重置/放弃修改 | `ModalScreen[bool]` |
| 帮助 | `HelpScreen` | `?` | `Markdown` 表格 |

页面共用 `Sidebar`（导航 + 未完成/逾期统计），由 `PageScreen` 基类统一装配。

## 4. 数据模型

**Task**

| 字段 | 类型 | 说明 |
|---|---|---|
| id | str | 8 位随机十六进制 |
| title | str | 必填，≤120 字符 |
| desc | str | 描述（Markdown） |
| status | `todo` / `doing` / `done` | 待办 / 进行中 / 已完成 |
| priority | `low` / `medium` / `high` / `urgent` | 低 / 中 / 高 / 紧急 |
| due | str | `YYYY-MM-DD` 或空 |
| tags | list[str] | 逗号分隔输入，自动去重、去 `#` |
| estimate | int | 预估工时 0–999 小时 |
| remind | bool | 到期提醒标记 |
| created / updated / done_at | ISO 时间 | 完成时自动写入 `done_at`，回退状态则清空 |

**Settings**：`theme`、`username`、`compact`、`default_priority`、`confirm_delete`、`hide_done`。

**存储**：单个 JSON `{version, settings, tasks, activity}`，动态记录最多保留 200 条。

## 5. 功能需求

### 5.1 全局
| 编号 | 需求 |
|---|---|
| G-01 | `1`–`4` 切换页面，**各页面状态独立保留**（如任务页的搜索词、排序） |
| G-02 | `n` 在任意页面新建任务；看板页按当前列预选状态 |
| G-03 | `?` 帮助；`Ctrl+P` 命令面板（可切换主题）；`q`/`Ctrl+Q` 退出 |
| G-04 | 表单、弹窗打开时，`q`、数字键、`n` 不得触发退出/切页/再开表单（防止丢失输入） |
| G-05 | 主题切换立即生效并持久化，下次启动自动恢复 |

### 5.2 仪表盘
| 编号 | 需求 |
|---|---|
| D-01 | 4 张统计卡：总任务 / 进行中 / 已完成 / 已逾期；逾期>0 时卡片变红加粗边框 |
| D-02 | 总体完成度进度条；近 14 天每日完成数趋势（Sparkline） |
| D-03 | 未完成任务按优先级分布的条形图 |
| D-04 | “即将到期（≤7 天）与已逾期”表，回车直接进入编辑 |
| D-05 | 最近 7 条动态；按时段与用户称呼显示问候语 |

### 5.3 任务列表
| 编号 | 需求 |
|---|---|
| T-01 | 搜索：空格分隔多个词，全部命中（匹配标题/描述/标签，忽略大小写） |
| T-02 | 状态、优先级下拉筛选，与搜索叠加；设置中“隐藏已完成”仅在状态=全部时生效 |
| T-03 | 点击表头排序，再点反向，表头显示 ▲/▼；默认按截止日期升序 |
| T-04 | 刷新数据后光标保持在原任务上；右侧详情随光标实时更新 |
| T-05 | `空格` 切换完成；`]` `[` 状态前进/后退；`e`/回车编辑；`d` 删除（可配置是否确认） |
| T-06 | 搜索框回车 = 确认并回到表格；`Esc` 同样回到表格 |

### 5.4 看板
| 编号 | 需求 |
|---|---|
| B-01 | 三列按状态分组，列标题显示数量；列内按优先级、截止日期排序 |
| B-02 | `h`/`l`（或方向键）切换列；`H`/`L`（或 Shift+方向键）移动卡片，焦点跟随卡片 |
| B-03 | 卡片显示优先级色点、标题、到期标签、标签、工时；已完成卡片删除线弱化 |

### 5.5 表单
| 编号 | 需求 |
|---|---|
| F-01 | 标题必填；日期格式校验；工时 0–999 整数。错误**实时**显示在字段下方，初始状态不报错 |
| F-02 | 保存时统一校验，失败则聚焦到第一个错误字段并提示 |
| F-03 | 日期快捷按钮：今天 / 明天 / 下周 / 清除 |
| F-04 | `Ctrl+S` 保存；`Esc` 取消——**有未保存修改时弹出确认** |
| F-05 | 新建时可勾选“保存后继续新建”，保存后清空表单并回到标题框 |
| F-06 | 编辑时提供“删除”按钮（走确认流程） |

### 5.6 设置
主题（实时预览）、紧凑模式、称呼、默认优先级、删除确认、默认隐藏已完成；数据页可导出 CSV（UTF-8 BOM，Excel 直接打开不乱码）/JSON、追加演示数据、清除已完成、重置全部（后两者需确认）。**所有设置修改即时保存。**

## 6. 非功能需求

| 项 | 要求 |
|---|---|
| 数据安全 | 写入采用“临时文件 + `os.replace`”原子替换，崩溃不会留下半个文件 |
| 容错 | 数据文件损坏：自动备份为 `data.json.corrupt-<时间>`，重新开始并提示；未知字段忽略；非法状态/优先级回退默认值 |
| 错误反馈 | 保存/导出失败用通知提示，不抛异常退出 |
| 响应 | 数百条任务下刷新无感；表格与列表均整体重建（简单可靠） |
| 兼容 | Linux / macOS / Windows Terminal；推荐终端 ≥ 120×36（小终端可开紧凑模式） |

## 7. 快捷键

| 范围 | 按键 | 功能 |
|---|---|---|
| 全局 | `1` `2` `3` `4` | 仪表盘 / 任务 / 看板 / 设置 |
| | `n` | 新建任务 |
| | `?` / `Ctrl+P` | 帮助 / 命令面板 |
| | `q` / `Ctrl+Q` | 退出 |
| 任务 | `/` `Esc` `Enter` | 聚焦搜索 / 回表格 / 确认搜索或编辑 |
| | `空格` `]` `[` | 完成切换 / 状态前进 / 后退 |
| | `e` `d` | 编辑 / 删除 |
| 看板 | `h` `l` `H` `L` | 切列 / 移动卡片 |
| 表单 | `Ctrl+S` `Esc` `Tab` | 保存 / 取消 / 下一字段 |
| 弹窗 | `y` `n` `Esc` | 确认 / 取消 / 取消 |

## 8. 已知限制与扩展方向

- 数据为单文件 JSON，不支持多人并发；规模很大时可替换 `Store` 为 SQLite（接口不变）。
- “到期提醒”仅为标记，未接入系统通知。
- 未实现撤销/重做、任务子项、拖拽排序。
- 扩展思路：子任务（Tree 组件）、日历视图、按标签筛选、撤销栈、导入 CSV。

---

# 第二部分：实现说明

## 1. 总体架构

```
┌──────────────────────── TaskFlowApp ────────────────────────┐
│  MODES: dashboard │ tasks │ board │ settings   (各自独立的屏幕栈) │
│  全局 BINDINGS、主题信号、edit_task() / delete_task() 业务入口   │
├───────────────────────────────────────────────────────────────┤
│  PageScreen 基类：Header + Sidebar + 内容区 + Footer            │
│    ├ DashboardScreen  ├ TasksScreen  ├ BoardScreen  ├ SettingsScreen
│  TaskFormScreen（Screen[bool]） ConfirmScreen（ModalScreen[bool]） HelpScreen
├───────────────────────────────────────────────────────────────┤
│  Store：tasks / activity / settings + JSON 原子持久化 + 统计     │
└───────────────────────────────────────────────────────────────┘
```

**依赖方向**：UI → `app.store`；`Store` 不依赖任何 UI，可单独导入测试。

## 2. 关键设计

### 2.1 多页面：用 `MODES` 而不是手动 push/pop
```python
MODES = {"dashboard": DashboardScreen, "tasks": TasksScreen, ...}
await self.switch_mode("tasks")
```
每个 Mode 维护**自己的屏幕栈**，切走再切回，页面实例与状态（搜索词、排序、滚动位置）原样保留。表单则用 `push_screen` 压在当前 Mode 的栈顶，关闭后回到原页面。

代价是：页面不会重新创建，所以数据变化后需要主动刷新。

### 2.2 刷新机制：`on_screen_resume` + `sync()`
页面每次**变为可见**（首次进入、从其他 Mode 切回、表单/弹窗关闭）都会触发 `ScreenResume`，`PageScreen` 在此调用 `sync()`：刷新本页数据 + 更新侧边栏统计。因此“在表单里保存 → 回到列表自动看到新数据”无需任何回调传递。

### 2.3 基类模板方法
`PageScreen.compose()` 固定装配 Header / Sidebar / Footer，子类只实现 `compose_page()`（内容）与 `refresh_data()`（刷新）。侧边栏、紧凑模式、统计更新全部在基类完成，新增页面只需约 30 行骨架。

### 2.4 表单：校验与脏检查
- **实时校验**：自定义 `Validator`（`RequiredText`/`DateText`/`HoursText`）挂在 `Input(validators=[...])` 上；`Input.Changed` 事件携带 `validation_result`，据此显示/隐藏错误标签。
- **初始不报错**：新建表单的标题为空，若立即校验会一打开就是红字。用 `_ready` 标志，等首次布局完成并拍下快照后才响应校验事件。
- **保存前统一校验**：`_validate_all()` 对三个字段调用 `inp.validate()`，失败则聚焦第一个错误字段。
- **脏检查**：`_collect()` 把表单收集成 dict，与打开时的快照 `_initial` 比较；不同则 `Esc` 弹确认框。

### 2.5 模态框与回调
`ConfirmScreen` 是 `ModalScreen[bool]`，通过 `dismiss(True/False)` 返回结果，调用方在 `push_screen(screen, callback)` 的回调里处理。危险操作默认聚焦“取消”，避免回车误删。删除逻辑集中在 `App.delete_task(id, after)`，任务页、看板页、表单页共用。

### 2.6 全局快捷键的“守卫”
`q`、`n`、`1`–`4` 是 App 级绑定，若不加限制，在表单的按钮上按 `q` 就会退出应用、丢失输入。所以相关 action 都先检查 `isinstance(self.screen, PageScreen)`，在表单/弹窗上直接忽略。

### 2.7 主题持久化
`Select` 切换 → `app.theme = name`；命令面板切换也会改同一个属性。App 订阅 `theme_changed_signal`，**无论从哪里切换**都统一写回设置。设置页在每次显示时用 `with self.prevent(Select.Changed):` 同步下拉框，避免程序赋值触发回环。

### 2.8 数据持久化
```python
tmp.write_text(json.dumps(payload, ...)); os.replace(tmp, self.path)
```
先写临时文件再原子替换。加载失败（JSON 损坏/类型错误）时把原文件改名为 `.corrupt-<时间>` 并从演示数据重新开始，同时在界面通知用户。

## 3. 踩坑记录（实测发现并已修复）

| 问题 | 原因 | 修复 |
|---|---|---|
| 打开表单即崩溃 `assert self._task is not None` | `TaskFormScreen` 里用了 `self.task` 存放任务，与 Textual `MessagePump.task` 属性**重名** | 改名 `self.editing`。教训：自定义属性名别和框架内置属性撞（上一个项目的 `visible` 是同类问题） |
| `SUB_TITLE` 写成 `@property` 报错 | Screen 初始化时读取的是类变量 | 在 `__init__` 里赋值 `self.sub_title` |
| 任务表底部出现横向滚动条 | 列宽总和超过可用宽度 | 删除冗余 ✓ 列、收窄列宽，并调整详情面板比例 |
| 搜索框回车后按 `d` 变成输入文字 | 焦点仍在输入框 | `Input.Submitted` 时把焦点交给表格 |
| 仪表盘右侧面板比左侧高一行 | `#panel-due` 只写 `margin-left`，丢失 `.panel` 的上边距 | 显式 `margin: 1 0 0 1` |

## 4. 目录与代码导览

| 位置 | 内容 |
|---|---|
| 1 领域常量 | 状态/优先级枚举、颜色、`Task`/`Settings` 数据类、日期标签 |
| 2 `Store` | 加载/保存/统计/增删改/导出/演示数据 |
| 3 校验器 | `RequiredText`、`DateText`、`HoursText` |
| 4 通用组件 | `ConfirmScreen`、`HelpScreen`、`Sidebar`、`PageScreen` |
| 5–8 四个页面 | 仪表盘、任务列表、看板、设置 |
| 9 `TaskFormScreen` | 表单页 |
| 10 `TaskFlowApp` | CSS、全局绑定、业务入口 |
| 11 `main` | 命令行参数 |

## 5. 如何扩展

**新增一个页面**（例如“日历”）：
```python
class CalendarScreen(PageScreen):
    MODE = "calendar"; SUB_TITLE = "日历"
    def compose_page(self): yield Label("…")
    async def refresh_data(self): ...          # 从 self.app.store 取数据并更新组件
```
然后在 `Sidebar.PAGES` 加一行、`TaskFlowApp.MODES` 加一项、`BINDINGS` 加一个数字键即可。

**新增任务字段**（例如“负责人”）：`Task` 加字段（`from_dict` 自动兼容旧数据）→ 表单加 `Input` 与 `_collect()` 一项 → 列表/详情中显示。

**换存储后端**：保持 `Store` 的公开方法不变，内部改为 SQLite 即可，UI 无需改动。

## 6. 测试

使用 Textual 的 `app.run_test()` + `Pilot` 模拟真实按键，覆盖：

| 类别 | 内容 |
|---|---|
| 导航 | 4 个页面切换；弹窗/表单中页面键被忽略；`q` 不误退出 |
| 表单 | 空标题拦截、非法日期报错、快捷日期修复、字段保存与持久化、标签去重、脏检查与放弃/保留 |
| 任务页 | 搜索过滤、`空格` 完成/还原、`]` 前进、回车编辑、排序、删除确认 |
| 看板 | 列计数、`L` 移卡并焦点跟随、边界无操作、`h` 切列、`n` 预选列状态 |
| 设置 | 主题实时切换、紧凑模式、称呼、隐藏已完成、设置落盘 |
| 数据 | CSV/JSON 导出、重置确认与取消、重启后数据与主题恢复、损坏文件备份与恢复 |

可在自己的修改后沿用同样方式回归测试。
