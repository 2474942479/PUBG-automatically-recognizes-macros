# PUBG 弹孔 YOLO 模型训练完整指南

## 为什么需要 YOLO？

当前的传统 CV 方法 (帧差分、暗点检测、SimpleBlobDetector) 在以下场景完全失效：

| 场景 | 传统 CV | YOLO |
|------|---------|------|
| 脏墙 / 纹理墙 | ❌ 误检大量墙面纹理 | ✅ 只识别弹孔 |
| 弹孔重叠 | ❌ 无法分辨 | ✅ 可区分 |
| 光照变化 | ❌ 差分噪声大 | ✅ 不受影响 |
| 远距离小弹孔 | ❌ 面积过滤不准 | ✅ 学习到特征 |

**学术验证**：YOLOv8 在射击靶纸弹孔检测中 mAP50 达到 **96.7%** ([论文链接](https://www.mdpi.com/2673-2688/5/1/5))。

---

## 一、环境安装

```bash
# 基础依赖
pip install ultralytics opencv-python numpy

# 验证安装
python -c "from ultralytics import YOLO; print('OK')"
```

> **GPU 推荐**：NVIDIA GPU + CUDA 可大幅加速训练 (10x)。没有 GPU 也能训练，只是慢。
> 如果没有本地 GPU，可以用 Google Colab (免费 T4 GPU)。

---

## 二、数据收集 (50-200 张截图)

### 2.1 使用项目工具截图

```bash
python tools/train_yolo.py capture --output dataset/raw
```

按 **F8** 截屏。

### 2.2 截图策略（重要！质量比数量重要）

| 维度 | 建议 | 数量 |
|------|------|------|
| 干净水泥墙 | 近距离, 弹孔清晰 | 20 张 |
| 粗糙/脏墙 | 有裂缝、纹理、涂鸦 | 30 张 |
| 木板/木墙 | 纹理重 | 20 张 |
| 金属面 | 高光反射 | 15 张 |
| 远距离 (50-100m) | 弹孔小 | 20 张 |
| 混合 | 有+无弹孔的墙 | 15 张 |
| 不同枪械 | M416, AKM, SCAR, UMP 等 | 分散 |
| 不同姿态 | 站/蹲/趴 | 分散 |

**关键技巧**：
- 每张图尽量包含 5-40 个弹孔
- 包含一些 **没有弹孔的纯墙面** 图片 (作为负样本，约 10%)
- 包含 **弹孔密集重叠** 的场景
- 同一墙面不同角度/距离多拍几张

---

## 三、数据标注 (使用 Roboflow — 免费)

### 3.1 创建项目

1. 注册 [Roboflow](https://roboflow.com) (免费账户支持 1000 张图)
2. 点击 "Create New Project"
3. 项目类型选 **Object Detection**
4. 类别名写 `bullet_hole`

### 3.2 上传图片

- 将 `dataset/raw/` 下的截图批量上传
- Roboflow 会自动分配 train/val/test 比例

### 3.3 标注

- 选择一张图，用 **矩形框** 紧贴每个弹孔画框
- 标签选 `bullet_hole`
- **标注所有弹孔**，包括模糊的、重叠的
- 如果弹孔太小，Roboflow 支持放大查看
- 每张图标注完点 Save

![标注示例](https://blog.roboflow.com/content/images/size/w1200/2023/01/image-16.png)

> **技巧**: Roboflow 有 AI 辅助标注 (Label Assist)，标注几张后会自动预测标注。

### 3.4 导出数据集

1. 标注完所有图片后，点击 "Generate" 创建版本
2. 数据增强推荐：
   - Flip: Horizontal + Vertical
   - 90° Rotate
   - Brightness: -15% ~ +15%
   - Blur: Up to 1px
3. 导出格式选 **YOLOv8**
4. 选择 "Download zip to computer"
5. 解压到项目的 `dataset/` 目录

解压后的目录结构:
```
dataset/
  data.yaml          ← YOLOv8 配置
  train/
    images/           ← 训练图片
    labels/           ← 训练标签 (每行: 0 x y w h)
  valid/
    images/
    labels/
```

**或者**用工具创建空模板:
```bash
python tools/train_yolo.py init --output dataset
```

### 3.5 标签格式说明

每个 `.txt` 标签文件中，一行对应一个弹孔：

```
0 0.456 0.312 0.025 0.030
0 0.523 0.428 0.020 0.025
```

格式: `class_id x_center y_center width height` (均为 0~1 归一化值)

---

## 四、模型训练

### 4.1 本地训练

```bash
# 推荐 nano 模型 (最快，精度够用)
python tools/train_yolo.py train --data dataset/data.yaml --model-size n --epochs 100

# 如果精度不够，用 small 模型
python tools/train_yolo.py train --data dataset/data.yaml --model-size s --epochs 150
```

**或者直接用 Python:**

```python
from ultralytics import YOLO

model = YOLO("yolov8n.pt")  # n=nano(最快) s=small m=medium l=large
results = model.train(
    data="dataset/data.yaml",
    epochs=100,
    imgsz=640,
    batch=16,
    name="bullet_hole",
)
```

### 4.2 Google Colab 训练 (免费 GPU)

如果没有 NVIDIA GPU，在 [Google Colab](https://colab.research.google.com) 中:

```python
# Cell 1: 安装
!pip install ultralytics

# Cell 2: 上传数据集 (或从 Roboflow API 下载)
from roboflow import Roboflow
rf = Roboflow(api_key="YOUR_API_KEY")
project = rf.workspace().project("your-project")
dataset = project.version(1).download("yolov8")

# Cell 3: 训练
from ultralytics import YOLO
model = YOLO("yolov8n.pt")
model.train(data=f"{dataset.location}/data.yaml", epochs=100, imgsz=640)

# Cell 4: 下载模型
from google.colab import files
files.download("runs/detect/train/weights/best.pt")
```

### 4.3 训练参数说明

| 参数 | 推荐值 | 说明 |
|------|--------|------|
| model-size | `n` | nano 足够, 推理仅需 2ms |
| epochs | 100-200 | 过少欠拟合, 有 early stop |
| imgsz | 640 | 标准分辨率 |
| batch | 8-32 | 显存不够就减小 |
| patience | 20 | 20 轮无提升自动停止 |

### 4.4 查看训练结果

训练完成后，查看 `runs/detect/bullet_hole/` 下的：
- `results.png` — 训练曲线 (loss, mAP)
- `confusion_matrix.png` — 混淆矩阵
- `val_batch0_pred.png` — 验证集预测效果

**关注指标**:
- **mAP50 > 90%** = 良好
- **mAP50 > 95%** = 优秀
- **Precision > 90%** = 误报率低
- **Recall > 90%** = 漏检率低

---

## 五、使用模型

### 5.1 放置模型

训练完成后，模型自动复制到 `models/bullet_hole_best.pt`。

或手动复制:
```bash
cp runs/detect/bullet_hole/weights/best.pt models/bullet_hole_best.pt
```

### 5.2 测试模型

```bash
python tools/train_yolo.py test --model models/bullet_hole_best.pt --image test_screenshot.png
```

### 5.3 在视频校准中使用

1. 打开主 GUI → 点击 "视频校准"
2. 在检测后端区域选择 "YOLO 模型"
3. 点击 "选择模型 (.pt)" → 选择你的 `best.pt`
4. 录屏或加载视频 → 自动使用 YOLO 检测弹孔

**CLI 方式:**
```bash
python -m calibration.video_calibrator m416 \
    --backend yolo \
    --model models/bullet_hole_best.pt \
    --video recording.avi
```

---

## 六、模型优化技巧

### 6.1 检测效果不好？

| 问题 | 解决方案 |
|------|----------|
| 漏检（弹孔没检出） | 增加训练数据 + 降低 conf 阈值 (0.15) |
| 误检（非弹孔被检出） | 增加负样本 (无弹孔图) + 提高 conf |
| 小弹孔检不到 | 增加远距离训练图 + 用 `imgsz=1280` |
| 特定墙面效果差 | 增加该墙面类型的训练数据 |

### 6.2 持续优化循环

1. 用当前模型检测 → 找到检测失败的截图
2. 标注这些失败案例 → 加入训练集
3. 重新训练 → 模型逐步提升

---

## 七、学习资源

### 入门教程
- [Ultralytics YOLOv8 官方文档](https://docs.ultralytics.com/)
- [Roboflow 训练 YOLOv8 教程](https://blog.roboflow.com/how-to-train-yolov8-on-a-custom-dataset/)
- [DigitalOcean YOLOv8 训练教程](https://digitalocean.com/community/tutorials/yolov8)

### 学术论文
- [YOLOv8 弹孔检测论文](https://www.mdpi.com/2673-2688/5/1/5) — 与本项目完全一致的应用
- [迭代弹孔追踪校准论文](https://arxiv.org/html/2601.17062v1) — 弹孔追踪 + 校准

### 视频教程
- YouTube 搜索 "YOLOv8 custom training tutorial"
- B站 搜索 "YOLOv8 自定义训练"

### 进阶
- [SAM 2 (Segment Anything Model)](https://github.com/facebookresearch/sam2) — 零样本分割
- [Grounding DINO](https://github.com/IDEA-Research/GroundingDINO) — 文本提示检测

---

## 八、常见问题

**Q: 需要多少张图才能训练？**
A: 最低 50 张 (含标注)，推荐 100-200 张。质量比数量重要——确保覆盖各种墙面纹理和距离。

**Q: 训练要多久？**
A: GPU: 10-30 分钟 | CPU: 2-6 小时 | Colab: 15-45 分钟

**Q: 没有 GPU 能训练吗？**
A: 能，但慢。推荐用 Google Colab 免费 GPU 或 nano 模型 + 少量 epochs。

**Q: YOLO 模型文件多大？**
A: YOLOv8n: ~6MB | YOLOv8s: ~22MB | 推理速度: 2-6ms/帧

**Q: 能识别不同枪械的弹孔吗？**
A: 可以。不同枪械的弹孔外观差异不大，一个模型可以覆盖所有枪械。

**Q: 如何区分新旧弹孔？**
A: YOLO 检测所有弹孔，时序排序由 "YOLO + 时序" 模式完成（对比前后帧发现新弹孔）。
