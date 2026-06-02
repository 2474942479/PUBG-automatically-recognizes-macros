# PUBG 自动识别压枪工具

> **声明**：此源码仅供学习交流使用，用于其他用途与本人无关。如使用了本项目源码请标明出处。

利用 OpenCV SIFT 算法自动识别枪械与配件，实现一套素材即可匹配所有分辨率，无需为每种分辨率单独制作模板。

## 核心功能

- **SIFT 枪械识别** — 按 Tab 截图，自动识别枪名、倍镜、枪口、握把、枪托
- **智能压枪** — 根据弹道数据 + 配件组合 + 姿势系数 + 灵敏度自动计算后坐力补偿
- **开火状态检测** — 像素取色判定是否开镜，自动启停压枪
- **姿势识别** — 图标识别 + 键盘追踪双策略
- **三档游戏内 HUD** — Tab 循环切换：极简 → 紧凑 → 完整 → 隐藏
- **弹痕校准工具** — GUI / CLI / 游戏内 HUD 三种模式，支持交互式标注修正

## 环境要求

- Python ≥ 3.8
- Windows 10/11（依赖 Win32 API + Logitech GHUB 驱动）
- 安装依赖：`pip install -r requirements.txt`
- **可选：ONNX 分类器** — 将训练好的 `*.onnx` 放入 `_internal/models/`（见该目录 README），可提高识别准确率；未放置时自动使用原有 OpenCV 模板匹配。

训练流程：`tools/TRAINING_DATA.md`、`tools/prepare_dataset.py`、`tools/train_classifier.py`（训练需 `pip install -r requirements_train.txt`）。

## 项目结构

```
project_root/
├── main.py                  # 主入口
├── main_new.py              # 备选入口（现代 UI）
├── requirements.txt         # Python 依赖
├── README.md
│
├── core/                    # 核心逻辑
│   ├── process.py           # 数据加载、开火控制、压枪计算
│   ├── ghub.py              # Logitech GHUB 驱动封装
│   ├── recognition.py       # SIFT / 模板匹配 / ONNX 分类
│   └── classifier.py        # ONNXRuntime 推理（可选）
│
├── data/                    # 数据定义
│   ├── fire_data.py         # 配件映射 & 按键编码
│   ├── bullet_data.py       # 枪械弹道原始数据
│   └── resolution_setting.py # 分辨率截图区域配置
│
├── input/                   # 输入监听
│   ├── mouse_listener.py    # 鼠标事件（开镜/开火/姿势识别）
│   └── key_listener.py      # 键盘事件（Tab/切枪/姿势/视角）
│
├── ui/                      # 界面
│   ├── overlay_hud.py       # 游戏内三档 HUD 浮窗
│   ├── ingame_display.py    # 游戏内信息展示组件
│   ├── pubg_ui.py           # 主窗口 UI（PyQt5 生成）
│   ├── modern_ui.py         # 现代风格 UI（PyQt5 生成）
│   └── designer/            # Qt Designer 源文件
│       ├── PUBG.ui
│       └── Card.ui
│
├── calibration/             # 弹痕校准工具
│   ├── bullet_analysis.py   # 弹痕检测/排序/对比/可视化/参数修正
│   ├── calibrate.py         # CLI 校准工具
│   ├── calibrate_gui.py     # GUI 校准工具（交互式标注）
│   └── calibrate_hud.py     # 游戏内校准 HUD
│
├── Config/
│   └── config.json          # 用户配置（分辨率、灵敏度）
│
├── tools/                   # 数据集划分与 YOLOv8-cls 训练脚本
└── _internal/               # 运行时资源（打包时整体复制）
    ├── GunData/*.json        # 各枪械弹道数据
    ├── data/firearms/...     # SIFT 模板图片
    ├── models/               # 可选 ONNX 分类模型（*.onnx + *_labels.json）
    └── ghub_device_GHUB.dll  # GHUB 驱动 DLL
```

## 快速开始

```bash
# 1. 安装依赖
pip install -r requirements.txt

# 2. 启动主程序
python main.py
```

1. 在 GUI 中选择你的屏幕分辨率，点击"保存"
2. 选择开镜模式（长按/点击），点击"启动"
3. 游戏中按 **Tab** 打开背包进行截图识别
4. 按 **1** / **2** 切换枪械，右键开镜后自动压枪
5. 游戏内 HUD 会自动显示，按 **Tab** 切换显示模式

## 配置说明

### config.json

```json
{
  "resolution": "1920x1080",
  "sensitivity": {
    "none": 3.4,
    "hongdian": 2.0,
    "quanxi": 2.0,
    "2bei": 6.0,
    "3bei": 8.0,
    "4bei": 11.5,
    "6bei": 5.0,
    "8bei": 5.7,
    "15bei": 10.0
  }
}
```

- `resolution` — 屏幕分辨率，支持 `3840x2160` / `2560x1440` / `1920x1080`
- `sensitivity` — 各倍镜灵敏度系数
  - 压过头 → 调低数值；压不住 → 调高数值
  - 修改后需在 GUI 中点击"保存"生效

### 分辨率适配

如果识别不准确，编辑 `data/resolution_setting.py` 调整截图区域坐标。
可以取消 `core/recognition.py` 中的调试截图注释，在 `test/` 目录查看截图效果。

## 弹痕校准工具

三种使用方式：

| 模式 | 启动命令 | 说明 |
|------|---------|------|
| GUI | `python -m calibration.calibrate_gui` | 可视化界面，支持交互标注修正 |
| CLI | `python -m calibration.calibrate` | 命令行模式，快捷键 F5/F6/F7 |
| HUD | `python -m calibration.calibrate_hud` | 游戏内悬浮窗，边打边校准 |

### 校准流程

1. 对准一面白墙，开镜
2. 截取空白墙面（基线图）
3. 射击若干发
4. 截取弹痕墙面（结果图）
5. 工具自动检测弹痕，与 JSON 理论数据对比
6. 可交互修正弹痕标注，输出修正后的压枪参数

## 支持的枪械

**步枪**: M416, AKM, SCAR-L, M762, Groza, AUG, M16A4, QBZ, G36C, ACE32, FAMAS, K2

**狙击/射手**: Mini14, SKS, MK12, MK14, MK47, QBU, VSS

**冲锋枪**: UZI, Vector, MP5K, UMP45, PP-19, P90, JS9

**机枪**: DP-28, M249, MG3

## 打包

```bash
pyinstaller main.spec
```

生成的 exe 位于 `dist/` 目录。

## 战术按键宏

通过齿轮菜单"宏配置 (F7)"可启用并自定义：

- **闪身宏**：X1 + Q/E → 自动开镜探头 + 反向取消，留 300ms 开枪窗口
- **Q 弹反**：右键开镜中 + Q/E → 快速探头回正，诱骗对手交火
- **滑步**：Shift+W 持续按下 → 自动循环 C tap 触发滑铲
- **大跳**：Shift+Space → 跳起后空中蹲，跨越较高障碍

每个宏可单独开关、可自定义修饰键 / 触发键 / 镜像键 / 时序参数；
全局开关与背包打开（按 Tab 时）自动屏蔽。详细时序与字段说明见
`docs/superpowers/specs/2026-06-02-pubg-macros-design.md`。