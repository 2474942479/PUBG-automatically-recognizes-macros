# PUBG 战术按键宏系统 设计文档

**日期**：2026-06-02
**状态**：设计阶段（已通过用户分段确认，等待复核）
**作者**：与用户在 brainstorming 中共同推导

## 背景与目标

现有项目专注枪械识别 + 后坐力补偿，开火相关的鼠标移动已通过 GHUB 驱动注入。本次新增**战术按键宏系统**，覆盖 4 类常用动作，开枪仍由用户手控：

| 宏 | 触发 | 用途 |
| --- | --- | --- |
| 闪身宏 | `X1（腰射侧键）+ Q/E` | 自动 ADS + 探头 + 反向取消，留 300ms 开枪窗口 |
| Q 弹反 | `鼠标右键（开镜中）+ Q/E` | 探头后立即反向回正、不开枪，诱骗对手交火 |
| 滑步循环 | `Shift + W 同时按下并保持` | 跑动中循环 C tap 触发滑铲 |
| 大跳 | `Shift + Space` | 跳起后空中蹲，跨越较高障碍 |

所有宏的按键、时序、启用状态均**通过 UI 配置面板编辑**，参考主流软件的热键编辑器交互。

## 技术约束与既有现状

- 项目已使用 `core/ghub.py` 通过罗技 GHUB DLL 注入鼠标事件（`mouse_R`、`mouse_down/up`）；DLL 同样导出 `key_down(key: bytes)` 和 `key_up(key: bytes)`，本设计直接复用
- 键鼠监听已分别由 `input/key_listener.py`（基于 `keyboard` 库）、`input/mouse_listener.py`（基于 `pynput`）作为 QThread 持有；监听是**被动观察、不拦截**
- `core/process.py` 是单例 `ProcessClass`，持全部运行时状态（含背包打开标志 `TabKey`）
- 配置已有写盘机制（`scope_factor_v3` 等都在 `Config/config.json`）

## 架构

### 模块布局

```
input/
├── key_listener.py      ← 现有；末尾增加 dispatcher.on_key_event()
├── mouse_listener.py    ← 现有；末尾增加 dispatcher.on_mouse_event()
└── macros.py            ← 新增
    ├── MacroDispatcher       单例，管 4 个宏的状态、互斥、热重载
    ├── BaseMacro             抽象基类，封装"获取/释放 active 锁"、try/finally key_up 清理
    ├── QuickPeekMacro        闪身宏
    ├── PeekFakeMacro         Q 弹反
    ├── SlideStepMacro        滑步循环
    └── BigJumpMacro          大跳

ui/
├── pubg_ui.py                ← 现有；齿轮菜单加 "宏配置 (F7)"
└── macro_config_dialog.py    ← 新增；QDialog
```

### 设计原则

1. **键鼠注入只走 `core.ghub.ghub_device`** —— `key_down/key_up/mouse_down/mouse_up` 调用集中在 `input/macros.py`
2. **同步定时用 `threading.Timer` + `threading.Event`** —— 不引入 asyncio，跟现有 `Thread` 风格一致
3. **全局互斥** —— Dispatcher 维护 `_active_macro_name`，同一时刻只一个宏运行；冲突触发被忽略并打日志
4. **背包打开时整体禁用** —— Dispatcher 入口检查 `PC.TabKey == True` 即 early return
5. **listener 接线点最小化** —— 每个 listener 只在末尾加一行 `dispatcher.on_*()`，不影响现有 emit / 识别 / 压枪逻辑
6. **try/finally 保证清理** —— 每个宏的执行函数用 `try/finally`，确保所有 `key_down` 都有匹配的 `key_up`（防止异常时 Q/E/右键卡死）
7. **热重载** —— UI 保存配置后调 `dispatcher.reload_config()`，无需重启

## 4 个宏的状态机与时序

### ① 闪身宏 `QuickPeekMacro`

**触发**：`mouse_x1`（X1 后侧键）当前已按下 + 检测到 `q` 或 `e` 的 key_down 事件
**状态机**：`IDLE → PEEK_HOLD → CANCELING → COOLDOWN → IDLE`

时序（Q 为例，E 镜像处理；下面是默认 `ads_wait_ms=0` 的同时注入路径）：

```
t=0       gh.key_down('q')                    # 同时注入 Q 与右键
          gh.mouse_down(2)
t=300ms   gh.key_down('e'); 等 10ms; gh.key_up('e')   # 反向键 tap，加速回正
          gh.key_up('q')
t=350ms   gh.mouse_up(2)                      # 释放右键
t=450ms   COOLDOWN 期结束（防连点）
```

- **开枪窗口**：t=0 ~ t=300ms 之间用户手按左键即可（即 `peek_hold_ms`）
- **配置参数**：
  - `ads_wait_ms`（默认 **0**）— Q 与右键之间的延迟。0 = 同时（用户选定）；>0 = 先按右键再等 N ms 才按 Q
  - `peek_hold_ms`（默认 300）— 探头保持时长 = 开枪窗口
  - `release_delay_ms`（默认 50）— 反向键收尾后到释放右键的间隔
  - `cooldown_ms`（默认 100）— 防连点
- **中止**：用户在执行期间松开 X1 → 立即跳到 CANCELING 阶段，依然要释放注入的所有键

**注**：当 `ads_wait_ms > 0` 时时序变为 `t=0 mouse_down → t=ads_wait_ms key_down('q') → t=ads_wait_ms+peek_hold_ms reverse...`。提供这个口子是因为 PUBG 不同分辨率/帧率下"开镜动画完成"的时机略有差异，留给玩家调。

### ② Q 弹反 `PeekFakeMacro`

**触发**：`mouse_right` 当前已按下 + 检测到 `q` 或 `e` 的 key_down 事件
**状态机**：`IDLE → PEEK_HOLD → CANCELING → COOLDOWN → IDLE`

时序：

```
t=0       gh.key_down('q')                    # 不碰右键，因为已经在开镜
t=120ms   gh.key_down('e'); 等 10ms; gh.key_up('e')   # 反向 tap
          gh.key_up('q')
t=170ms   COOLDOWN 结束
```

- **配置参数**：`peek_hold_ms`（120）、`reverse_tap_ms`（10）、`cooldown_ms`（100）
- **中止**：用户松开右键（取消开镜）→ 立即清理注入的 Q/E

### ③ 滑步循环 `SlideStepMacro`

**触发**：`shift` 与 `w` 都处于按下状态（边缘触发：进入"两键同时按下"那一刻启动）
**状态机**：`IDLE → STARTUP_DELAY → CROUCH_TAP → REST → CROUCH_TAP → ... → IDLE`

时序：

```
t=0       检测到 Shift+W 同时按下
t=200ms   循环开始（启动延迟，避免日常短跑误触）
循环：
  gh.key_down('c'); 等 50ms; gh.key_up('c')   # 蹲 tap
  等 300ms                                     # 间隔
直到 Shift 或 W 任一释放 → 立即 break，确保 C 不卡死
```

- **配置参数**：`startup_delay_ms`（200）、`crouch_hold_ms`（50）、`crouch_interval_ms`（300）
- **兜底**：循环总时长上限 30 秒，超时强制退出（防止 listener 漏掉 release 事件）

### ④ 大跳 `BigJumpMacro`

**触发**：`shift` + `space` 同时按下（要求 Shift 已按下、Space 边缘触发）
**状态机**：`IDLE → JUMPED → CROUCH_TAP → IDLE`

时序：

```
t=0       不拦截 Space —— 让游戏正常处理跳跃
t=180ms   gh.key_down('c'); 等 80ms; gh.key_up('c')   # 空中蹲（人物起跳后约 150-200ms 进入空中）
t=260ms   COOLDOWN 结束
```

- **配置参数**：`crouch_delay_ms`（180）、`crouch_hold_ms`（80）、`cooldown_ms`（300）
- **注**：Space 由用户自己按、不被宏注入。宏只在边缘触发后追加一次 C tap

## UI 配置面板

新增 `ui/macro_config_dialog.py`（参考 `roi_config_dialog.py` 的 QDialog 风格），从齿轮菜单 `ToolsMenu.addAction("宏配置 (F7)")` 打开，也支持 F7 快捷键。

### 布局

```
┌─ 宏配置 ─────────────────────────────────────────────────┐
│  [✓] 启用宏系统总开关                                    │
│  ─────────────────────────────────────────────────────── │
│                                                          │
│  闪身宏        修饰键 [ X1 ▼]  +  触发键 [ Q ][捕获...]  │
│  [✓ 启用]      ADS 延迟=[0]ms  保持=[300]ms  释放=[50]ms │
│                镜像键 [ E ][捕获...]   冷却=[100]ms      │
│  ─────────────────────────────────────────────────────── │
│  Q 弹反        修饰键 [鼠标右键▼] + 触发键 [Q][捕获...]  │
│  [✓ 启用]      探头=[120]ms  反向 tap=[10]ms  冷却=100   │
│                镜像键 [ E ][捕获...]                     │
│  ─────────────────────────────────────────────────────── │
│  滑步          组合键 [Shift][捕获...] + [W][捕获...]    │
│  [✓ 启用]      启动延迟=[200]ms  C 间隔=[300]ms  持续=50 │
│  ─────────────────────────────────────────────────────── │
│  大跳          组合键 [Shift][捕获...] + [Space][捕获...]│
│  [✓ 启用]      空中蹲延迟=[180]ms  C 持续=[80]ms 冷却=300│
│  ─────────────────────────────────────────────────────── │
│                                                          │
│              [恢复默认]  [取消]   [保存]                 │
└──────────────────────────────────────────────────────────┘
```

### 热键捕获 UX

1. 点击 `[捕获...]` 按钮 → 按钮文字变为"按下任意键..."、其他控件 disable
2. 启动一次性 `keyboard.read_event()` / `pynput.mouse.Listener` 监听
3. 捕获到 key_down / mouse_down → 显示捕获到的键名（`X1`、`Q`、`Mouse4`、`Space`）→ 写回上方文本框
4. ESC 取消捕获、保留原值

### 校验规则

- **修饰键 ≠ 触发键 ≠ 镜像键**：UI 保存时三向校验冲突
- **镜像键可空**：用户可以只配主键、不配镜像
- **跨宏冲突**：允许（不同宏可以用同一组合键，比如闪身用 X1+Q、弹反用右键+Q）

### 时序参数暴露

按用户决定，**全部 ms 参数平铺暴露**（无折叠区），方便高级玩家调试。默认值在 UI 上以高亮（淡蓝/绿色）标记，提示"这是推荐值"。

### 键名规范化

- 键盘键统一小写（`q`、`shift`、`space`），跟 `keyboard` 库对齐
- 鼠标键用 `mouse_left`、`mouse_right`、`mouse_x1`、`mouse_x2`，跟 pynput 对齐
- 配置文件存上述字符串；UI 显示时翻译为中文（"鼠标右键"、"X1 后侧键"）

## 配置 schema

`Config/config.json` 新增 `macros` 块（与 `scope_factor_v3` 等并列）：

```json
{
  "macros": {
    "enabled": true,
    "quick_peek": {
      "enabled": true,
      "modifier": "mouse_x1",
      "primary_key": "q",
      "mirror_key": "e",
      "ads_wait_ms": 0,
      "peek_hold_ms": 300,
      "release_delay_ms": 50,
      "cooldown_ms": 100
    },
    "peek_fake": {
      "enabled": true,
      "modifier": "mouse_right",
      "primary_key": "q",
      "mirror_key": "e",
      "peek_hold_ms": 120,
      "reverse_tap_ms": 10,
      "cooldown_ms": 100
    },
    "slide_step": {
      "enabled": true,
      "combo_keys": ["shift", "w"],
      "startup_delay_ms": 200,
      "crouch_hold_ms": 50,
      "crouch_interval_ms": 300
    },
    "big_jump": {
      "enabled": true,
      "combo_keys": ["shift", "space"],
      "crouch_delay_ms": 180,
      "crouch_hold_ms": 80,
      "cooldown_ms": 300
    }
  }
}
```

读写复用 `core/process.py` 现有的 `_load_config()` / `save_config()` 模式；新增方法 `save_macros_config(macros_dict)`。

## 与现有代码的接线

### `core/process.py`

- `__init__` 增加 `self.macros_config`（dict），从 config 读
- 新方法 `save_macros_config(macros_dict)` —— 复用现有 `save_config` 模式
- 新属性 `self._active_macro_name`（占位字符串，不动既有压枪状态）

### `input/key_listener.py`

- `on_key_pressed` 末尾加：`MacroDispatcher.instance().on_key_event(Keys, "down")`
- `on_key_release` 同步加：`MacroDispatcher.instance().on_key_event(Keys, "up")`
- 现有的 `z/c/space → Change_posture` 逻辑保留不动（避免破坏当前姿势识别管线）
- F7 hotkey：emit `macro_config_requested` 信号（与 F8 同模式）

### `input/mouse_listener.py`

- `on_button_click` 末尾加：`MacroDispatcher.instance().on_mouse_event(button, pressed)`

### `ui/pubg_ui.py` + `main.py`

- 齿轮菜单 `ToolsMenu.addAction("宏配置 (F7)")` → 新 `actionMacroConfig`
- `main.py` 接 signal 打开 `MacroConfigDialog`

### 新文件

- `input/macros.py` — Dispatcher + 4 个宏类（约 400 行）
- `ui/macro_config_dialog.py` — 配置对话框（约 300 行）

## 错误处理与边界

| 场景 | 处理 |
| --- | --- |
| 背包打开（`PC.TabKey == True`） | dispatcher.on_*() 第一行 early return |
| GHUB 驱动未初始化（`gm_ok == 0`） | 宏触发时打印一次警告、不执行注入 |
| 宏跑到一半程序退出 / 异常 | 宏类用 try/finally 确保所有 `key_down` 都有匹配 `key_up` |
| 滑步循环卡死（异常 / 漏 release） | 循环上限 30 秒兜底强制退出 |
| 用户配的修饰键和触发键相同 | UI 保存时校验拒绝；dispatcher 加载时也加防御性校验 |
| 宏注入的键和用户手按键冲突 | 接受现实 —— 游戏看到的是"键状态"、不区分来源。文档里说明 |
| 宏期间用户切枪（按 1/2） | 不影响切枪逻辑；闪身宏注入的键依然按计划走完 |
| 反 anti-cheat 检测 | 与现有压枪宏同样依赖 GHUB 驱动注入。本设计未引入新攻击面 |

## 测试策略

- **单元测试**（`tests/test_macros.py`，新建）：每个宏 mock 一个假 `gh_device` 收集 `key_down/key_up/mouse_down/mouse_up` 调用序列；用假时钟（`time.sleep` 替换为 `Event.wait`）验证时序正确
- **配置对话框**：手动 smoke test（项目无既有 UI 测试框架）
- **集成验证**：在 macOS / Linux 上启动主程序、打开宏配置对话框、保存配置（GHUB 注入路径在非 Windows 是 no-op，但状态机和 UI 仍可验证）

## YAGNI 排除项

明确**不**做的事，避免范围蔓延：

- 不做"通用状态机 + JSON 配置驱动"的元宏框架（4 个宏的体量撑不起这个抽象）
- 不做窗口聚焦检测（与现有压枪宏一致；用户切到桌面时宏会跑空，但不会误伤）
- 不做"自动开枪"类宏（用户明确"开枪我自己控"）
- 不做跨宏并发（已选全局互斥）
- 不做时序参数的"预设档位"切换（暴露 ms 数值即可）

## 未决事项 / 后续可扩展

- 用户在探索阶段没有勾选额外组合键（翻越自动趴 / bunny hop / 秒蹲扰动 / 三连点）。如果后续要加，可以复用 `BaseMacro` 抽象，新增宏类即可
- ROI 校准 / 模板生成 与本设计互不影响，沿用现有齿轮菜单
