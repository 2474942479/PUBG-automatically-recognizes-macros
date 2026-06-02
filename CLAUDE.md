# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 项目概述

PUBG 自动识别压枪工具 — 基于 PyQt5 的 Windows 桌面应用。核心流程：截取游戏内背包画面 → 识别当前枪械与配件（枪名/倍镜/枪口/握把/枪托）→ 调用罗技 GHUB 驱动 DLL 在玩家开火时补偿后坐力。整个程序以 `Tab` 键（打开背包 → 触发识别）和鼠标右键（开镜 → 进入开火控制）作为主入口。

源码注释、UI 文本与文档均为中文，编辑时请保持这一约定。

## 运行平台

- 目标运行环境是 **Windows 10/11**，需安装罗技 GHUB 驱动，且 `_internal/ghub_device_GHUB.dll` 可达。`core/ghub.py` 在非 Windows 平台会退化为 no-op，因此在 macOS/Linux 上可以启动以便阅读代码，但压枪功能不工作。
- Python ≥ 3.8（发布构建使用 3.10/3.11 — `_internal/sift.cp310-win_amd64.pyd` 的 Cython 产物锁定到 3.10）。

## 常用命令

```bash
# 安装运行时依赖（玩家机器）
pip install -r requirements_runtime.txt     # 构建管线使用的精简依赖
pip install -r requirements.txt              # 完整开发依赖（含 pyinstaller/cython）

# 运行程序
python main.py

# 可选：ONNX 分类器训练（独立大型依赖 — torch/torchvision）
pip install -r requirements_train.txt
python tools/prepare_dataset.py              # 将 logs/training_data 切分为 datasets/（--verify 可剔除识别错误样本）
python tools/train_mobilenet.py --epochs 30  # 训练所有类别，*.onnx 自动复制到 _internal/models/
python tools/train_mobilenet.py --category Name --epochs 30 --device cuda:0  # 单类别 GPU 训练

# 打包发布（仅 Windows — Nuitka + Cython）
python build.py                              # 完整流程：Cython 预编译 → Nuitka standalone → zip
python build.py --skip-cython                # 跳过源码保护步骤
python build.py --zip-only                   # 仅对已有 dist/ 重新打包
python setup_cython.py build_ext --inplace   # 仅把 core/process、core/recognition、data/fire_data 编译为 .pyd
```

仓库中没有配置测试套件、Linter 或格式化工具。

## 架构

### 单一状态源：`ProcessClass`（core/process.py）
线程安全的单例，持有全部运行时状态 — 当前分辨率、当前枪槽（`Current_firearms` ∈ {1,2}）、姿势、倍镜模式、各枪识别结果（`_Result1` / `_Result2`）、调试开关、GHUB 设备句柄。`main.py` 只构造一次；`input/key_listener.py`、`input/mouse_listener.py`、识别线程、HUD 全部通过这同一个实例读写。**绝对不要再实例化第二个** — `_initialized` 守卫会阻止重复 `__init__`，但新调用方仍应通过单例访问。

### Tab → 识别 → 开火 主管线
1. **按 Tab**（`input/key_listener.py`）→ 翻转 `PC.TabKey`。关闭背包时触发识别。
2. **识别**（`core/recognition.py::capture_all_positions_thread`，async）：用 `mss` 截取整个背包大图，再按 `Config/roi_config.json` 中的坐标用 numpy 切片裁出各 ROI 做分类。多帧投票（`MULTI_FRAME_COUNT=3` 帧、间隔 40ms、至少 2 票一致）压制单帧噪声。
3. **单 ROI 分类** 有两套引擎，由 `Config/config.json` 的 `recognize_engine` 控制：
   - `opencv` — SIFT/FLANN + 多方法模板匹配，对 `_internal/data/firearms/<分辨率>/<类别>/*.png`。
   - `onnx` — `core/classifier.py` 用 onnxruntime 加载 `_internal/models/{name,scope,muzzle,grip,stock,gun_hud,posture}_cls.onnx`，置信度 ≥ `PUBG_ONNX_CONF`（环境变量，默认 0.8）时返回 `(label, conf)`。
   - `auto`（默认）— 先走 ONNX，未命中或低置信度时回退 OpenCV。
4. **HUD 枪械图标识别**（`capture_gun_icons`）独立运行 — 见 `process.py:111` 处「双源识别策略」注释。背包是权威来源；HUD 仅写 `Name_hud` 作为旁证，除非背包尚未识别到枪。
5. **开火控制**（`process.FIRE_v3` / `_fire_start_v3`）：从 `_internal/GunData/<gun>.json` 读取弹道（`recoil["1000"]` 索引出逐发 `y` 偏移，`tick_ms` 决定节奏）。每 tick 移动量 = `recoil_y × scope_factor × posture_factor × all_ratio × gun_ratio × shift_factor`，通过 `core.ghub.ghub_device.mouse_R` 下发。`mouse_listener` 监听左键按下/抬起 + 右键来判定开火与开镜状态。

### 后坐力调参向量（全部为乘性系数，全部可由用户编辑）
| 字段 | 存储位置 | 用途 |
|---|---|---|
| `scope_factor_v3` | `Config/config.json` | 各倍镜灵敏度；对应游戏内灵敏度滑条 |
| `posture_v3` | `Config/config.json` | 蹲下/趴下倍率 |
| `gun_ratio_v3` | `Config/config.json` | 各枪最终倍率；覆盖 `GunData/<gun>.json` 中内置值 |
| `*_shift`（如 `hongdian_shift`） | `scope_factor_v3` | 仅在按住 Shift 时生效 |

调整压枪力度时编辑 `config.json` —`_internal/GunData/` 中的各枪 JSON 是权威弹道数据，不应该为了调灵敏度去改它。

### 分辨率与 ROI 处理
- 所有屏幕坐标存放在 **`Config/roi_config.json`** 中，按 `"3840x2160"` / `"2560x1440"` / `"1920x1080"` 分组。格式为 `[left, top, right, bottom]`（背包用屏幕绝对坐标，背包内部各 ROI 用相对坐标）。旧文档提到的 `data/resolution_setting.py` 已不再存在 — 坐标完全由 JSON 驱动，缓存 TTL 60 秒。
- 新增分辨率 / ROI 错位：启动程序后按 **F8** 打开应用内 ROI 校准器（`ui/roi_config_dialog.py`），逐类型框选，使用 1:1 像素显示 + 滚动条。

### 日志分流（在 `main.py` 中初始化）
每次运行都会清空 `logs/`（保留 `logs/training_data/`，用于 ML 数据采集），并将日志分流到：
- `app.log` — 全部
- `backpack_recognition.log` — `core.recognition` 中非 HUD 标签的记录
- `hud_recognition.log` — 含 `[枪械图标]` 的记录
- `onnx_recognition.log` — 含 `[ONNX]` 的记录

应用内按 **F9** 切换详细追踪（同时持久化到 `config.json` 的 `debug_mode`）。`core/input_trace.py` 是另一条通道，由 `PC.debug_input_trace` 控制。

### 训练数据流
调试模式开启后，每次识别都会把 ROI 截图写入 `logs/training_data/<类别>/<预测标签>/`。类别到 ONNX 前缀的映射定义在 `core/classifier.py::_CATEGORY_STEM_DEFAULT_IMGSZ`；训练管线（`tools/prepare_dataset.py` → `tools/train_mobilenet.py`）从同一目录树读取，并将 ONNX 输出写到应用下次启动时加载的位置。**新增类别时记得让 `_CATEGORY_STEM_DEFAULT_IMGSZ` 中的标签与训练脚本输出的前缀保持一致**。

### 打包流程细节
`build.py` 依次做三件事：
1. **Cython** 把 `core/process.py`、`core/recognition.py`、`data/fire_data.py` 编译为 `.pyd` 作为源码保护（定义在 `setup_cython.py`）。
2. **Nuitka** `--standalone` 打包所有内容；`calibration/` 和 `tools/` 通过 `--nofollow-import-to` 显式排除。
3. 运行时根目录为 `dist/PUBG_MacroTool/runtime/`（exe + `_internal/` + `Config/` + `logs/`）；启动器 `启动.bat` 在它的上一级。`Config/` 与 `logs/` 位于 `runtime/` **之内**，这样 `core.paths.res_path`（在 frozen 时取 `sys.executable` 所在目录）才能正确解析。

## 改动代码前需要知道的事

- `git status` 当前显示 `tools/train_classifier.py` 已被删除 — README 还在引用，但 `tools/train_mobilenet.py` 才是当前的训练脚本，不要恢复旧脚本。
- README 与 `COMMERCIAL_TODO.md` 描述的是历史结构（`main_new.py`、`data/bullet_data.py`、`data/resolution_setting.py`、`calibration/` 目录）。当前分支上这些都不存在，请以实际文件系统为准。
- 识别运行在 QThread worker 中 — UI 更新必须通过 `pyqtSignal`（如 `keyInfo`、`roi_config_requested`），不要直接调用 widget。
- `_internal/` 会随发布包一起分发；视为只读数据（模板、弹道 JSON、GHUB DLL、可选 ONNX 模型）。新增的运行时资源应放在这里。
