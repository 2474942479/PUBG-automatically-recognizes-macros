# CNN 训练数据采集说明

开启 **调试模式**（F9 或界面「调试」按钮）后，识别结果会自动写入 `logs/training_data/`，启动程序时 **不会清空** 该目录（其余 logs 仍会清空）。

## 目录结构（采集结果）

按类别与标签名存放灰度或彩色 ROI：

| 来源 | 路径示例 |
|------|---------|
| Tab 背包（配件等） | `logs/training_data/{Name,Muzzle,Grip,Stock,Scope}/<标签>/` |
| HUD 枪械图标 | `logs/training_data/gun/<标签>/` |
| 姿势（开镜识别） | `logs/training_data/zishi/<None\|c\|z>/` |

标签来自当前识别引擎的识别结果；请定期 **抽检约 10%** 样本，修正错误文件夹中的图片。

## 识别引擎开关

在 `Config/config.json` 中可配置识别引擎，影响数据采集来源：

| `recognize_engine` | 含义 | 采集时推荐 |
|---------------------|------|-----------|
| `"auto"` | ONNX 优先，不足时回退 OpenCV（默认） | 已有训练好的模型时 |
| `"opencv"` | 强制 OpenCV 模板匹配 | 首次采集（无模型时） |
| `"onnx"` | 强制 ONNX 模型分类 | 用模型结果采集新数据 |

首次采集数据时建议使用 `"opencv"` 模式（此时还没有训练好的模型）。

## 下一步

1. 采集足够样本后运行：
   ```bash
   python tools/prepare_dataset.py --src logs/training_data --out datasets
   ```
   加 `--verify` 可自动过滤识别错误的样本。

2. 训练 MobileNetV3 模型：
   ```bash
   python tools/train_mobilenet.py --epochs 30
   ```

3. 训练脚本会自动复制到 `_internal/models/`；运行时需 `pip install onnxruntime`（已在 `requirements.txt`）

4. 重启程序后，在 `config.json` 中设置 `"recognize_engine": "onnx"` 测试模型效果，满意后切为 `"auto"` 日常使用

详细步骤参见 [TRAINING_GUIDE.md](./TRAINING_GUIDE.md)。
