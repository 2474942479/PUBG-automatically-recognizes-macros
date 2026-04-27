# ONNX 分类模型目录

将 `tools/train_classifier.py` 训练产物复制到此目录（与训练脚本自动复制规则一致）：

| 前缀 | 文件 |
|------|------|
| name_cls | `name_cls.onnx`, `name_cls_labels.json`, `name_cls_meta.json` |
| scope_cls | `scope_cls.onnx`, … |
| … | 其余类别见 `core/classifier.py` 中 `_CATEGORY_STEM_DEFAULT_IMGSZ` |

未放置模型时程序自动使用原有模板匹配，无需配置。
