# CNN 训练数据采集说明

开启 **调试模式**（F9 或界面「调试」按钮）后，识别结果会自动写入 `logs/training_data/`，启动程序时 **不会清空** 该目录（其余 logs 仍会清空）。

## 目录结构（采集结果）

按类别与标签名存放灰度或彩色 ROI：

| 来源 | 路径示例 |
|------|---------|
| Tab 背包（配件等） | `logs/training_data/{Name,Muzzle,Grip,Stock,Scope}/<标签>/` |
| HUD 枪械图标 | `logs/training_data/gun/<标签>/` |
| 姿势（开镜识别） | `logs/training_data/zishi/<None\|c\|z>/` |

标签来自当前模板匹配的识别结果；请定期 **抽检约 10%** 样本，修正错误文件夹中的图片。

## 下一步

1. 采集足够样本后运行：`python tools/prepare_dataset.py --src logs/training_data --out datasets`
2. 训练：`python tools/train_classifier.py --data-root datasets --epochs 50`
3. 训练脚本会自动复制到 `_internal/models/`；运行时需 `pip install onnxruntime`（已在 `requirements.txt`）
