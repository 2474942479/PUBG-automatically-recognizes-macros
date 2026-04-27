# YOLOv8-cls 模型训练完整指南（新手版）

> 本指南面向**零基础**用户，手把手教你从数据收集到模型部署的全流程。
> 不需要写任何代码，全部通过命令行完成。

---

## 目录

1. [整体流程概览](#整体流程概览)
2. [环境准备](#环境准备)
3. [第 1 步：收集训练数据](#第-1-步收集训练数据)
4. [第 2 步：数据质量检查](#第-2-步数据质量检查)
5. [第 3 步：整理数据集（拆分 train/val）](#第-3-步整理数据集拆分-trainval)
6. [第 4 步：训练模型](#第-4-步训练模型)
7. [第 5 步：部署与验证](#第-5-步部署与验证)
8. [参数调优建议](#参数调优建议)
9. [常见问题 FAQ](#常见问题-faq)
10. [名词解释](#名词解释)

---

## 整体流程概览

```
┌──────────┐    ┌──────────┐    ┌──────────┐    ┌──────────┐    ┌──────────┐
│  收集数据  │ →  │  检查质量  │ →  │  整理数据  │ →  │  训练模型  │ →  │  部署使用  │
│ (游戏中)  │    │ (抽检图片) │    │ (拆分集)  │    │ (一条命令) │    │ (自动生效) │
└──────────┘    └──────────┘    └──────────┘    └──────────┘    └──────────┘
```

- **总耗时估计**：数据收集 2-3 天 + 训练 10 分钟~4 小时（取决于有无 GPU）
- **所需磁盘空间**：约 2-5 GB（含 PyTorch 依赖）
- **难度**：复制粘贴命令即可，不需要写代码

---

## 环境准备

### 1. 确认 Python 版本

```bash
python3 --version
# 要求 Python 3.9 或更高版本
```

### 2. 安装训练依赖

训练需要 PyTorch 和 Ultralytics 库。**运行程序时不需要这些，只在训练时安装。**

```bash
# 进入项目目录
cd /path/to/PUBG-automatically-recognizes-macros

# 安装训练依赖（首次约 5-10 分钟，会下载 PyTorch ~2GB）
pip install -r requirements_train.txt
```

> **下载太慢？** 使用清华镜像加速：
> ```bash
> pip install -r requirements_train.txt -i https://pypi.tuna.tsinghua.edu.cn/simple
> ```

> **有 NVIDIA 显卡？** 建议去 [pytorch.org](https://pytorch.org/get-started/locally/) 安装带 CUDA 的版本，训练速度提升 10 倍以上。

### 3. 安装运行时依赖

训练完成后，程序运行时需要 `onnxruntime` 来加载模型：

```bash
pip install -r requirements.txt
# 其中包含 onnxruntime>=1.17.0
```

---

## 第 1 步：收集训练数据

### 原理

程序在 **debug 模式** 下运行时，每次识别都会自动把 ROI 截图保存到 `logs/training_data/` 目录，按 `类别/标签` 分文件夹存放。

### 操作步骤

1. 以 **debug 模式** 启动程序
2. 正常游戏，尽量覆盖各种场景：

| 场景 | 目的 |
|------|------|
| 拿不同的枪（M416、AKM、SKS、UMP 等） | 收集枪械名称和 HUD 图标数据 |
| 安装各种配件（倍镜、握把、枪口、枪托） | 收集配件图标数据 |
| 频繁切换站/蹲/趴姿势 | 收集姿势图标数据 |
| 在不同地图、不同光照条件下游戏 | 增加数据多样性 |
| 打开背包查看物品 | 收集背包界面数据 |

3. **建议游戏 2-3 天**，确保每个子类有足够数据

### 查看收集结果

```bash
# 查看有哪些类别
ls logs/training_data/
# 预期输出: Name/  Scope/  Muzzle/  Grip/  Stock/  gun/  zishi/

# 查看某个类别的子类
ls logs/training_data/Name/
# 预期输出: akm/  m416/  sks/  ump45/  ...

# 统计某个类别的图片总数
find logs/training_data/Name -name "*.png" | wc -l
```

### 数据量要求

| 类别 | 说明 | 每个子类最低 | 推荐数量 |
|------|------|------------|----------|
| Name | 枪械名称（背包文字） | 50 张 | 200+ 张 |
| Scope | 倍镜图标 | 30 张 | 100+ 张 |
| Muzzle | 枪口图标 | 30 张 | 100+ 张 |
| Grip | 握把图标 | 30 张 | 100+ 张 |
| Stock | 枪托图标 | 30 张 | 100+ 张 |
| gun | HUD 武器图标 | 50 张 | 200+ 张 |
| zishi | 姿势图标（站/蹲/趴） | 50 张 | 200+ 张 |

> **数据越多，模型越准。** 但也不要为了数量牺牲质量——标注错误的数据比没有数据更糟。

### 自动保存的目录结构

```
logs/training_data/
├── Name/                  ← 枪械名称
│   ├── akm/
│   │   ├── akm_2026-04-27_14-30-22_123.png
│   │   ├── akm_2026-04-27_14-31-05_456.png
│   │   └── ...
│   ├── m416/
│   └── ...
├── Scope/                 ← 倍镜
│   ├── red_dot/
│   ├── 2x/
│   └── ...
├── Muzzle/                ← 枪口
├── Grip/                  ← 握把
├── Stock/                 ← 枪托
├── gun/                   ← HUD 武器图标
│   ├── akm/
│   ├── m416/
│   └── ...
└── zishi/                 ← 姿势
    ├── None/              ← 站立
    ├── c/                 ← 蹲下
    └── z/                 ← 趴下
```

---

## 第 2 步：数据质量检查

**这一步非常重要！** 模型的准确率直接取决于训练数据的质量。

### 为什么需要检查

数据标签来自当前的模板匹配结果，模板匹配本身并非 100% 准确，所以会有少量图片被放错文件夹。

### 检查方法

1. 随机打开每个子类文件夹，浏览图片
2. 重点检查图片内容是否和文件夹名一致
3. **抽检比例：每个子类约 10% 的图片**

### 发现错误怎么办

- **分类错误**：把图片移动到正确的文件夹（例如把 `Name/akm/` 里的 M416 图片移到 `Name/m416/`）
- **图片损坏/异常**：直接删除
- **完全无法辨认**：直接删除

---

## 第 3 步：整理数据集（拆分 train/val）

训练模型需要两组数据：
- **训练集（train）**：模型用来学习的数据（80%）
- **验证集（val）**：用来检测模型学得怎么样的数据（20%）

### 运行拆分脚本

```bash
python tools/prepare_dataset.py
```

就这一条命令，默认参数就够了。

### 完整参数

```bash
python tools/prepare_dataset.py \
    --src logs/training_data \
    --out datasets \
    --val-ratio 0.2 \
    --seed 42
```

| 参数 | 含义 | 默认值 |
|------|------|--------|
| `--src` | 原始数据目录 | `logs/training_data` |
| `--out` | 输出目录 | `datasets` |
| `--val-ratio` | 验证集比例 | `0.2`（即 20%） |
| `--seed` | 随机种子（保证可复现） | `42` |
| `--move` | 移动文件而非复制（节省磁盘空间） | 不加则复制 |

### 预期输出

```
类别 [Name]: 共 30 个子类
  akm: train=160, val=40
  m416: train=180, val=45
  sks: train=120, val=30
  ...

类别 [Scope]: 共 8 个子类
  red_dot: train=80, val=20
  2x: train=90, val=22
  ...

完成! 训练集=3200 张, 验证集=800 张
输出目录: /path/to/datasets
```

### 输出目录结构（YOLOv8-cls 要求的格式）

```
datasets/
├── Name/
│   ├── train/              ← 训练集
│   │   ├── akm/            ← 每个子类一个文件夹
│   │   │   ├── akm_xxx.png
│   │   │   └── ...
│   │   ├── m416/
│   │   └── ...
│   └── val/                ← 验证集
│       ├── akm/
│       ├── m416/
│       └── ...
├── Scope/
│   ├── train/
│   └── val/
├── Muzzle/
│   ├── train/
│   └── val/
└── ...
```

---

## 第 4 步：训练模型

### 基本用法（推荐）

```bash
# 训练全部类别（一次搞定）
python tools/train_classifier.py --epochs 50
```

### 常用命令

```bash
# 只训练某一个类别（想先试试水）
python tools/train_classifier.py --category Name --epochs 50

# 数据量较少时减少训练轮数
python tools/train_classifier.py --epochs 30

# 使用 GPU 训练（有 NVIDIA 显卡时）
python tools/train_classifier.py --epochs 50 --device 0

# 显存不足时减小批大小
python tools/train_classifier.py --epochs 50 --batch 16

# 同时指定多个参数
python tools/train_classifier.py --category Name --epochs 80 --batch 16 --device 0
```

### 参数说明

| 参数 | 含义 | 默认值 | 建议 |
|------|------|--------|------|
| `--data-root` | 数据集目录 | `datasets` | 一般不用改 |
| `--export-root` | 模型导出目录 | `models_export` | 一般不用改 |
| `--category` | 指定类别 | 空（全部训练） | 测试时指定一个 |
| `--epochs` | 训练轮数 | `50` | 数据少用 30，数据多用 80-100 |
| `--batch` | 每批图片数量 | `32` | 显存不足时改 16 或 8 |
| `--device` | 训练设备 | 自动检测 | `cpu` / `0`(GPU 0) |

### 训练过程说明

运行后你会看到类似输出：

```
训练计划: ['Name', 'Scope', 'Muzzle', 'Grip', 'Stock', 'gun', 'zishi']
数据目录: /path/to/datasets
导出目录: /path/to/models_export

==================================================
[开始训练] 类别: Name
  模型前缀: name_cls
  输入尺寸: 224x224
  训练轮数: 50
  批大小:   32
  子类数:   30
  训练图片: ~6000 张
  数据目录: /path/to/datasets/Name
==================================================

开始训练 Name...
训练过程中会显示每轮的 loss 和准确率，请耐心等待。

Epoch  1/50:  loss=2.34  top1_acc=0.15  top5_acc=0.45    ← 刚开始，很差是正常的
Epoch  2/50:  loss=1.89  top1_acc=0.32  top5_acc=0.67
Epoch  5/50:  loss=1.12  top1_acc=0.55  top5_acc=0.82
Epoch 10/50:  loss=0.65  top1_acc=0.78  top5_acc=0.93
Epoch 20/50:  loss=0.32  top1_acc=0.89  top5_acc=0.97
Epoch 30/50:  loss=0.18  top1_acc=0.94  top5_acc=0.99
Epoch 40/50:  loss=0.14  top1_acc=0.96  top5_acc=0.99
Epoch 50/50:  loss=0.12  top1_acc=0.97  top5_acc=0.99    ← 最终结果

找到最佳权重: .../best.pt
正在导出 ONNX 模型...

==================================================
[完成] Name 训练成功!
  ONNX 模型:  models_export/name_cls/name_cls.onnx
  标签文件:   models_export/name_cls/name_cls_labels.json
  类别列表:   ['akm', 'm416', 'sks', ...]
  已自动复制到 _internal/models/，重启程序即可生效
==================================================
```

### 关键指标说明

| 指标 | 含义 | 理想值 |
|------|------|--------|
| **loss** | 损失值，越小越好 | < 0.3 |
| **top1_acc** | 准确率（最重要！） | > 0.95 (95%) |
| **top5_acc** | 前 5 名包含正确答案的比例 | > 0.99 (99%) |

### 训练时间参考

| 设备 | 数据量 | 训练 50 轮 |
|------|--------|-----------|
| 纯 CPU | 5000 张 | 2-4 小时 |
| GTX 1060 | 5000 张 | 10-20 分钟 |
| RTX 3060 | 5000 张 | 5-10 分钟 |
| RTX 4090 | 5000 张 | 2-5 分钟 |

---

## 第 5 步：部署与验证

### 模型自动部署

训练脚本会自动将模型文件复制到 `_internal/models/` 目录，**无需手动操作**。

### 确认文件就位

```bash
ls _internal/models/
```

每个类别应有 3 个文件：

```
_internal/models/
├── name_cls.onnx              ← ONNX 模型文件
├── name_cls_labels.json       ← 类别标签（["akm", "m416", ...]）
├── name_cls_meta.json         ← 训练参数（{"imgsz": 224, ...}）
├── scope_cls.onnx
├── scope_cls_labels.json
├── scope_cls_meta.json
├── muzzle_cls.onnx
├── muzzle_cls_labels.json
├── muzzle_cls_meta.json
├── grip_cls.onnx
├── grip_cls_labels.json
├── grip_cls_meta.json
├── stock_cls.onnx
├── stock_cls_labels.json
├── stock_cls_meta.json
├── gun_hud_cls.onnx
├── gun_hud_cls_labels.json
├── gun_hud_cls_meta.json
├── posture_cls.onnx
├── posture_cls_labels.json
└── posture_cls_meta.json
```

### 验证模型是否生效

重启程序后观察日志：

**成功加载的日志：**
```
[ONNX] 已加载模型: .../name_cls.onnx
[ONNX] 已加载标签 name_cls: 30 类
```

**ONNX 识别成功的日志：**
```
[ONNX] Name_01=m416 (置信度=0.9823)           ← 高置信度，直接采信
[ONNX][枪械图标] Gun_1=akm (置信度=0.9567)
[ONNX] 姿势识别: c (置信度=0.9912)             ← c=蹲下
```

**ONNX 回退模板匹配的日志：**
```
[ONNX] Name_01=m416 置信度 0.5432 低于阈值，回退模板匹配   ← 说明需要更多数据
[ONNX] onnxruntime 未安装，全部使用模板匹配                ← 需要 pip install onnxruntime
[ONNX] 模型文件不存在: .../name_cls.onnx                  ← 还没训练或文件缺失
```

### 调整置信度阈值

默认置信度阈值是 **0.8**（80%）。可通过环境变量调整：

```bash
# 降低阈值（更多地使用 ONNX 模型，适合模型训练充分时）
export PUBG_ONNX_CONF=0.7

# 提高阈值（更谨慎，不太确定时回退模板匹配）
export PUBG_ONNX_CONF=0.9
```

---

## 参数调优建议

### 训练效果不好怎么办？

| 症状 | 可能原因 | 解决方案 |
|------|---------|---------|
| top1_acc < 80% | 数据量太少 | 多玩几天游戏收集数据 |
| top1_acc 80-90% | 训练轮数不够 | 增加 `--epochs 100` |
| top1_acc 90-95% | 部分类别数据不均衡 | 补充少数类的数据 |
| loss 不下降 | 数据标注有大量错误 | 重新抽检并清理数据 |
| loss 震荡不稳定 | batch 太大或学习率问题 | 尝试 `--batch 16` |

### 推荐训练策略

1. **首先只训练一个类别测试流程**
   ```bash
   python tools/train_classifier.py --category zishi --epochs 30
   ```
   姿势只有 3 个子类，最容易训练成功。

2. **确认流程通畅后训练全部类别**
   ```bash
   python tools/train_classifier.py --epochs 50
   ```

3. **如果某个类别效果不好，单独重新训练**
   ```bash
   # 补充数据后重新训练
   python tools/prepare_dataset.py
   python tools/train_classifier.py --category Name --epochs 80
   ```

---

## 常见问题 FAQ

### Q: 报错 `No module named 'ultralytics'`
**A:** 没有安装训练依赖。运行：
```bash
pip install -r requirements_train.txt
```

### Q: 报错 `CUDA out of memory`
**A:** GPU 显存不足。解决方案：
```bash
# 方案 1：减小批大小
python tools/train_classifier.py --batch 16
# 如果还不够，继续减小
python tools/train_classifier.py --batch 8

# 方案 2：使用 CPU 训练（慢但一定能跑）
python tools/train_classifier.py --device cpu
```

### Q: 训练中途断了怎么办？
**A:** 直接重新运行命令即可，`exist_ok=True` 会覆盖上次的结果。数据不会丢失。

### Q: 准确率只有 70-80% 达不到 95%
**A:** 三个可能原因：
1. 数据量不够 → 继续收集
2. 数据标注有误 → 抽检清理
3. 训练轮数不够 → 增加 `--epochs 80` 或 `--epochs 100`

### Q: 我只有 CPU 没有显卡，能训练吗？
**A:** 完全可以，只是慢一些（几小时而非几分钟）。脚本默认自动检测设备。

### Q: 怎么更新/重新训练模型？
**A:** 直接重新运行训练脚本，会自动覆盖旧模型。重启程序即可生效。

### Q: `logs/training_data/` 会不会被清空？
**A:** 不会。`main.py` 启动时清理日志目录，但 `training_data` 子目录已被排除。

### Q: 模型文件有多大？
**A:** 每个 ONNX 模型约 5-10 MB，7 个类别总共约 50-70 MB。

### Q: 如何恢复到纯模板匹配（不用 ONNX）？
**A:** 删除 `_internal/models/` 目录下的 `.onnx` 文件即可，程序会自动回退到模板匹配。

---

## 名词解释

| 术语 | 解释 |
|------|------|
| **YOLOv8-cls** | YOLO v8 的分类模式，用于图像分类（判断图片属于哪一类） |
| **ONNX** | 开放神经网络交换格式，可以跨平台运行训练好的模型 |
| **onnxruntime** | 微软出品的 ONNX 推理引擎，速度快，不需要安装 PyTorch |
| **epoch（轮）** | 模型把所有训练数据看一遍叫一轮，通常需要几十轮 |
| **batch（批）** | 每次喂给模型多少张图片，越大训练越快但占显存越多 |
| **loss（损失）** | 衡量模型预测错误程度的数值，越小越好 |
| **top1_acc** | 模型预测最可能的类别就是正确答案的比例 |
| **train/val** | 训练集用来学习，验证集用来检测效果（防止"死记硬背"） |
| **ROI** | Region of Interest，感兴趣区域，即屏幕上需要识别的那一小块 |
| **置信度** | 模型对自己预测结果的确信程度，0~1 之间 |
| **回退/兜底** | ONNX 模型不可用或不确定时，自动切换到模板匹配方法 |
| **debug 模式** | 调试模式，开启后会保存更多日志和截图用于问题排查 |
