需求：一个基于 PyQt 的上位机 GUI 软件，启动时读取本地 Excel 配置文件，动态渲染界面，并通过 Modbus 协议与设备进行通信（轮询读值 + 触发写值）。

一个示例配置 `device-config.xlsx` + 一个完整的 PyQt5 渲染程序。

---

## 实现说明

### 文件结构
```
your_folder/
├── device-config.xlsx   ← 配置文件
└── modbus_gui.py        ← 主程序
```

### 配置文件示例（3 个 Sheet）

| Sheet | 内容 |
|---|---|
| 电源参数 | 12 条：电压/电流/功率/模式等，混合 READONLY INPUT + READWRITE SELECT |
| 温度监控 | 9 条：各部件温度 + 告警阈值 + 冷却方式 |
| 通信配置 | 9 条：地址/波特率/停止位/校验等全部 READWRITE |

### 核心架构

**配置解析** — `load_config()` 读 xlsx，每行实例化一个 `ChannelConfig`，JSON options 自动解析，表头行自动跳过。

**渲染规则** — `SheetTab` 按 `ceil(N/4)` 行 × 4 列排列 `CellWidget`；每个 cell 根据 `widget_type` 渲染 `QLineEdit`（INPUT）或 `QComboBox`（SELECT），`READONLY` 自动禁用编辑。

**Modbus 预留** — `ModbusClient` 类已定义好 `connect / disconnect / read_register / write_register` 接口，当前是 Mock（随机值抖动）；接入真实 pymodbus 只需替换这一个类的方法体。

**轮询线程** — `PollingWorker` 跑在独立 `QThread`，读完一轮后等待 `poll_ms` 毫秒（设 0 则无间隔），通过信号 `values_ready` 回到主线程刷新 UI。

**写值触发** — INPUT 按回车、SELECT 选中后触发 `write_requested` 信号，`parse_value()` 反算小数位后写寄存器。
