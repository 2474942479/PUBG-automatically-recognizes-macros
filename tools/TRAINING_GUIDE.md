# MobileNetV3 模型训练完整指南（新手版）

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
8. [识别引擎开关（A/B 对比）](#识别引擎开关ab-对比)
9. [参数调优建议](#参数调优建议)
10. [常见问题 FAQ](#常见问题-faq)
11. [名词解释](#名词解释)

---

## 整体流程概览

```
┌──────────┐    ┌──────────┐    ┌──────────┐    ┌──────────┐    ┌──────────┐
│  收集数据  │ →  │  检查质量  │ →  │  整理数据  │ →  │  训练模型  │ →  │  部署使用  │
│ (游戏中)  │    │ (抽检图片) │    │ (拆分集)  │    │ (一条命令) │    │ (自动生效) │
└──────────┘    └──────────┘    └──────────┘    └──────────┘    └──────────┘
```

- **总耗时估计**：数据收集 2-3 天 + 训练 10 分钟~2 小时（取决于有无 GPU）
- **所需磁盘空间**：约 2-5 GB（含 PyTorch 依赖）
- **模型骨干**：MobileNetV3-Small（轻量高效，ONNX 模型仅 ~2.5MB/个）
- **难度**：复制粘贴命令即可，不需要写代码

---

## 环境准备

### 1. 确认 Python 版本

```bash
python3 --version
# 要求 Python 3.9 或更高版本
```

### 2. 安装训练依赖

训练需要 PyTorch 和 torchvision。**运行程序时不需要这些，只在训练时安装。**

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

1. 以 **debug 模式** 启动程序（F9 或界面「调试」按钮）
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

### 自动验证（可选）

`prepare_dataset.py` 支持 `--verify` 参数，会用模板匹配反向验证每张图片，自动跳过识别不一致的样本：

```bash
python tools/prepare_dataset.py --verify
```

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
| `--verify` | 自动验证，跳过识别错误的图片 | 不加则全部保留 |

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

### 输出目录结构

```
datasets/
├── Name/
│   ├── train/              ← 训练集
│   │   ├── akm/
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
python tools/train_mobilenet.py --epochs 30
```

### 常用命令

```bash
# 只训练某一个类别（想先试试水）
python tools/train_mobilenet.py --category Name --epochs 30

# 数据量较多时增加训练轮数
python tools/train_mobilenet.py --epochs 50

# 使用 GPU 训练（有 NVIDIA 显卡时，速度快 10 倍以上）
python tools/train_mobilenet.py --epochs 30 --device cuda:0

# 显存不足时减小批大小
python tools/train_mobilenet.py --epochs 30 --batch 8

# 调整冻结轮数（默认前 5 轮冻结骨干只训练分类头）
python tools/train_mobilenet.py --epochs 30 --freeze-epochs 10

# 同时指定多个参数
python tools/train_mobilenet.py --category Name --epochs 50 --batch 8 --device cuda:0
```

### 参数说明

| 参数 | 含义 | 默认值 | 建议 |
|------|------|--------|------|
| `--data-root` | 数据集目录 | `datasets` | 一般不用改 |
| `--export-root` | 模型导出目录 | `models_export` | 一般不用改 |
| `--category` | 指定类别 | 空（全部训练） | 测试时指定一个 |
| `--epochs` | 训练轮数 | `30` | 数据少用 20，数据多用 50 |
| `--freeze-epochs` | 前 N 轮冻结骨干 | `5` | 数据很少时可增到 10 |
| `--batch` | 每批图片数量 | `16` | 显存不足时改 8 |
| `--device` | 训练设备 | `cpu` | `cuda:0`(GPU 0) |

### 训练过程说明

运行后你会看到类似输出：

```
训练计划: ['Name', 'Scope', 'Muzzle', 'Grip', 'Stock', 'gun', 'zishi']
数据目录: /path/to/datasets
导出目录: /path/to/models_export
设备:     cpu

=======================================================
[MobileNetV3-Small] 类别: Name
  模型前缀:   name_cls
  输入尺寸:   224x224
  子类数:     30
  训练图片:   6000 张
  验证图片:   1500 张
  训练轮数:   30（前 5 轮冻结骨干）
  批大小:     16
  设备:       cpu
=======================================================
  [冻结] epoch   1/30  loss=2.3400  train_acc=15.2%  val_acc=22.1%   ← 刚开始，很差是正常的
  [冻结] epoch   2/30  loss=1.8900  train_acc=32.5%  val_acc=40.3%
  [冻结] epoch   5/30  loss=1.1200  train_acc=55.0%  val_acc=60.8%
  [epoch 6] 解冻全网络，lr=1e-4                                     ← 第 6 轮开始全网络微调
  [微调] epoch   6/30  loss=0.8500  train_acc=68.2%  val_acc=72.1%
  [微调] epoch  10/30  loss=0.4200  train_acc=85.3%  val_acc=88.5%
  [微调] epoch  20/30  loss=0.1800  train_acc=94.1%  val_acc=93.7%
  [微调] epoch  30/30  loss=0.0900  train_acc=97.5%  val_acc=96.2%   ← 最终结果

=======================================================
[完成] Name 训练成功!
  ONNX 模型:  models_export/name_cls/name_cls.onnx
  标签文件:   models_export/name_cls/name_cls_labels.json
  类别列表:   ['akm', 'm416', 'sks', ...]
  最佳验证准确率: 96.2%
  已自动复制到 _internal/models/，重启程序即可生效
=======================================================
```

### 两阶段训练说明

MobileNetV3 采用**两阶段训练**策略，比直接训练效果更好：

| 阶段 | 轮次 | 学习率 | 说明 |
|------|------|--------|------|
| **冻结（freeze）** | 前 5 轮 | 1e-3 | 骨干网络锁定，只训练分类头，快速收敛 |
| **微调（finetune）** | 后 25 轮 | 1e-4 | 解冻全网络，用更低学习率精细调整 |

### 关键指标说明

| 指标 | 含义 | 理想值 |
|------|------|--------|
| **loss** | 损失值，越小越好 | < 0.2 |
| **train_acc** | 训练集准确率 | > 95% |
| **val_acc** | 验证集准确率（最重要！） | > 93% |

### 训练时间参考

| 设备 | 数据量 | 训练 30 轮 |
|------|--------|-----------|
| 纯 CPU | 5000 张 | 1-2 小时 |
| GTX 1060 | 5000 张 | 5-10 分钟 |
| RTX 3060 | 5000 张 | 3-5 分钟 |
| RTX 4090 | 5000 张 | 1-2 分钟 |

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
├── name_cls.onnx              ← ONNX 模型文件（~2.5MB）
├── name_cls_labels.json       ← 类别标签（["akm", "m416", ...]）
├── name_cls_meta.json         ← 训练参数（{"imgsz": 224, "normalize": true, ...}）
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

**ONNX 识别成功的日志（auto/onnx 模式下）：**
```
[引擎=auto][ONNX] Name_01=m416 (置信度=0.9823)
[引擎=auto][ONNX][枪械图标] Gun_1=akm (置信度=0.9567)
```

**ONNX 回退模板匹配的日志（auto 模式下）：**
```
[ONNX] Name_01=m416 置信度 0.5432 低于阈值    ← 说明需要更多数据
[引擎=auto] Name_01 进入 OpenCV 模板匹配       ← 自动回退
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

## 识别引擎开关（A/B 对比）

为了方便对比 MobileNet 模型和 OpenCV 模板匹配的准确率，程序提供了识别引擎开关。

### 三种模式

| 模式 | 行为 | 适用场景 |
|------|------|----------|
| `auto` | ONNX 优先，置信度不足时回退 OpenCV 模板匹配 | **日常使用（默认）** |
| `opencv` | 强制只走 OpenCV 模板匹配，完全跳过 ONNX | 对比基线准确率 |
| `onnx` | 强制只走 ONNX 分类，不回退模板匹配 | 测试模型独立准确率 |

### 配置方式

在 `Config/config.json` 中添加或修改：

```json
{
  "resolution": "3840x2160",
  "recognize_engine": "auto"
}
```

将 `"auto"` 改为 `"opencv"` 或 `"onnx"` 即可切换引擎。

### A/B 对比调试流程

1. **先用 opencv 模式跑一段时间，观察日志中的识别结果**
   ```json
   "recognize_engine": "opencv"
   ```
   日志示例：
   ```
   [引擎=opencv] Name_01 进入 OpenCV 模板匹配
   ```

2. **再用 onnx 模式跑同样的场景，对比结果**
   ```json
   "recognize_engine": "onnx"
   ```
   日志示例：
   ```
   [引擎=onnx][ONNX] Name_01=m416 (置信度=0.9823)
   ```

3. **对比满意后切回 auto 模式（日常使用）**
   ```json
   "recognize_engine": "auto"
   ```

### 日志对比要点

开启 debug 模式（F9）后，日志会带 `[引擎=xxx]` 前缀，便于筛选对比：

```
# opencv 模式下的典型日志
[引擎=opencv] Name_01 进入 OpenCV 模板匹配
[TM] Name_01: 最佳=m416 (0.8734)

# onnx 模式下的典型日志
[引擎=onnx][ONNX] Name_01=m416 (置信度=0.9823)

# auto 模式下 ONNX 命中
[引擎=auto][ONNX] Name_01=m416 (置信度=0.9823)

# auto 模式下 ONNX 未命中，自动回退
[引擎=auto] Name_01 进入 OpenCV 模板匹配
```

---

## 参数调优建议

### 训练效果不好怎么办？

| 症状 | 可能原因 | 解决方案 |
|------|---------|---------|
| val_acc < 80% | 数据量太少 | 多玩几天游戏收集数据 |
| val_acc 80-90% | 训练轮数不够或数据质量差 | 增加 `--epochs 50` 并抽检清理数据 |
| val_acc 90-95% | 部分类别数据不均衡 | 补充少数类的数据 |
| train_acc 高但 val_acc 低 | 过拟合 | 增加 `--freeze-epochs 10` 或减少 `--epochs` |
| loss 不下降 | 数据标注有大量错误 | 重新抽检并清理数据 |
| loss 震荡不稳定 | batch 太大 | 尝试 `--batch 8` |

### 推荐训练策略

1. **首先只训练一个类别测试流程**
   ```bash
   python tools/train_mobilenet.py --category zishi --epochs 20
   ```
   姿势只有 3 个子类，最容易训练成功。

2. **确认流程通畅后训练全部类别**
   ```bash
   python tools/train_mobilenet.py --epochs 30
   ```

3. **如果某个类别效果不好，单独重新训练**
   ```bash
   # 补充数据后重新训练
   python tools/prepare_dataset.py
   python tools/train_mobilenet.py --category Name --epochs 50
   ```

4. **用引擎开关 A/B 对比**
   - 修改 `config.json` 中 `recognize_engine` 为 `onnx`，只用模型
   - 游戏中观察是否比模板匹配更准确
   - 确认后切回 `auto` 模式日常使用

---

## 常见问题 FAQ

### Q: 报错 `No module named 'torch'`
**A:** 没有安装训练依赖。运行：
```bash
pip install -r requirements_train.txt
```

### Q: 报错 `CUDA out of memory`
**A:** GPU 显存不足。解决方案：
```bash
# 方案 1：减小批大小
python tools/train_mobilenet.py --batch 8

# 方案 2：使用 CPU 训练（慢但一定能跑）
python tools/train_mobilenet.py --device cpu
```

### Q: 训练中途断了怎么办？
**A:** 直接重新运行命令即可。数据不会丢失。

### Q: 准确率只有 70-80% 达不到 95%
**A:** 三个可能原因：
1. 数据量不够 → 继续收集
2. 数据标注有误 → 用 `--verify` 参数清理或手动抽检
3. 训练轮数不够 → 增加 `--epochs 50`

### Q: 我只有 CPU 没有显卡，能训练吗？
**A:** 完全可以，只是慢一些（1-2 小时而非几分钟）。脚本默认使用 CPU。

### Q: 怎么更新/重新训练模型？
**A:** 直接重新运行训练脚本，会自动覆盖旧模型。重启程序即可生效。

### Q: `logs/training_data/` 会不会被清空？
**A:** 不会。程序启动时清理日志目录，但 `training_data` 子目录已被排除。

### Q: 模型文件有多大？
**A:** MobileNetV3-Small 的 ONNX 模型约 **2-3 MB/个**，7 个类别总共约 **15-20 MB**。比旧版 YOLOv8-cls 小一半以上。

### Q: 如何恢复到纯模板匹配（不用模型）？
**A:** 两种方式任选：
- 在 `config.json` 中设置 `"recognize_engine": "opencv"`（推荐，随时可切回）
- 删除 `_internal/models/` 目录下的 `.onnx` 文件（永久禁用）

### Q: 旧版 YOLOv8 训练的模型还能用吗？
**A:** 能用。`classifier.py` 对 ONNX 格式向后兼容。旧模型的 meta.json 没有 `normalize` 字段，推理时不会额外归一化，行为与以前一致。但建议用 MobileNet 重新训练以获得更好的效果。

### Q: auto 模式和 onnx 模式有什么区别？
**A:**
- `auto`：ONNX 模型优先，如果模型不存在或置信度低于阈值，自动回退到 OpenCV 模板匹配。最稳妥。
- `onnx`：只用 ONNX 模型，即使置信度低也不回退。如果模型缺失则返回 "none"。适合测试模型纯准确率。

---

## 名词解释

| 术语 | 解释 |
|------|------|
| **MobileNetV3** | 谷歌出品的轻量级卷积神经网络，专为移动端设计，体积小、推理快 |
| **迁移学习** | 用在大数据集（ImageNet）上预训练好的模型为基础，在你的小数据集上微调 |
| **冻结/解冻** | 冻结=锁定骨干网络参数不更新；解冻=允许全网络参数更新 |
| **ONNX** | 开放神经网络交换格式，可以跨平台运行训练好的模型 |
| **onnxruntime** | 微软出品的 ONNX 推理引擎，速度快，不需要安装 PyTorch |
| **ImageNet 归一化** | 用 ImageNet 数据集的均值和方差标准化输入图片，提升预训练模型表现 |
| **epoch（轮）** | 模型把所有训练数据看一遍叫一轮，通常需要几十轮 |
| **batch（批）** | 每次喂给模型多少张图片，越大训练越快但占显存越多 |
| **loss（损失）** | 衡量模型预测错误程度的数值，越小越好 |
| **train_acc / val_acc** | 训练集/验证集准确率，val_acc 更重要（检测泛化能力） |
| **train/val** | 训练集用来学习，验证集用来检测效果（防止"死记硬背"） |
| **过拟合** | 模型在训练集上很准但验证集上很差，说明"死记硬背"了 |
| **ROI** | Region of Interest，感兴趣区域，即屏幕上需要识别的那一小块 |
| **置信度** | 模型对自己预测结果的确信程度，0~1 之间 |
| **识别引擎** | opencv=模板匹配，onnx=MobileNet 模型分类，auto=模型优先+模板兜底 |
