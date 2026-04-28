#!/usr/bin/env python3
"""
MobileNetV3-Small 分类模型训练 + ONNX 导出一键脚本。

==========  完整训练流程  ==========

第 1 步：安装训练依赖（只需一次）
    pip install -r requirements_train.txt

第 2 步：收集数据
    用 debug 模式运行程序，在游戏中操作（切枪、打开背包、切换姿势等）
    图片自动保存到 logs/training_data/<Category>/<Label>/ 下

第 3 步：准备数据集
    python tools/prepare_dataset.py

第 4 步：训练（即本脚本）
    python tools/train_mobilenet.py --epochs 30          # 训练全部类别
    python tools/train_mobilenet.py --category Name      # 只训练枪械名称
    python tools/train_mobilenet.py --device cuda:0      # 使用 GPU 0 训练

第 5 步：模型自动复制到 _internal/models/，重启程序即可使用

==========  与旧版 train_classifier.py (YOLOv8-cls) 的区别  ==========
- 骨干网络：MobileNetV3-Small（更轻量，ONNX ~2.5MB）
- 适度数据增强（ColorJitter + RandomAffine），防止小数据过拟合
- 两阶段训练：先冻结骨干训练分类头，再解冻全网络微调
- 导出 meta.json 中包含 "normalize": true，推理时自动应用 ImageNet 归一化
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
import os
from pathlib import Path
from typing import Dict, List, Optional, Tuple

PROJECT_ROOT = Path(__file__).resolve().parent.parent

CATEGORY_CONFIG: Dict[str, Tuple[str, int]] = {
    "Name":   ("name_cls",     224),
    "Scope":  ("scope_cls",    128),
    "Muzzle": ("muzzle_cls",   128),
    "Grip":   ("grip_cls",     128),
    "Stock":  ("stock_cls",    128),
    "gun":    ("gun_hud_cls",  128),
    "zishi":  ("posture_cls",  128),
}


def _collect_classes(train_dir: Path) -> List[str]:
    """收集 train/ 下所有子类名称（排序保证标签顺序稳定）"""
    return sorted([
        d.name for d in train_dir.iterdir()
        if d.is_dir() and not d.name.startswith(".")
    ])


def _count_images(root: Path) -> int:
    exts = {".png", ".jpg", ".jpeg", ".bmp", ".webp"}
    return sum(1 for f in root.rglob("*") if f.is_file() and f.suffix.lower() in exts)


def train_one(
    category: str,
    data_root: Path,
    export_root: Path,
    epochs: int,
    batch: int,
    device: str,
    freeze_epochs: int,
) -> bool:
    try:
        import torch
        import torch.nn as nn
        import torch.optim as optim
        from torch.utils.data import DataLoader
        from torchvision import datasets, transforms, models
    except ImportError:
        print("[错误] torch / torchvision 未安装！请运行:", file=sys.stderr)
        print("       pip install -r requirements_train.txt", file=sys.stderr)
        return False

    if category not in CATEGORY_CONFIG:
        print(f"[错误] 未知类别: {category}", file=sys.stderr)
        return False

    stem, imgsz = CATEGORY_CONFIG[category]

    dataset_dir = data_root / category
    train_dir = dataset_dir / "train"
    val_dir = dataset_dir / "val"
    if not train_dir.is_dir():
        print(f"[跳过] 缺少训练数据: {train_dir}", file=sys.stderr)
        return False

    classes = _collect_classes(train_dir)
    num_classes = len(classes)
    if num_classes < 2:
        print(f"[跳过] {category} 子类数不足 2（当前 {num_classes}），无法训练", file=sys.stderr)
        return False

    n_train = _count_images(train_dir)
    n_val = _count_images(val_dir) if val_dir.is_dir() else 0

    print(f"\n{'='*55}")
    print(f"[MobileNetV3-Small] 类别: {category}")
    print(f"  模型前缀:   {stem}")
    print(f"  输入尺寸:   {imgsz}x{imgsz}")
    print(f"  子类数:     {num_classes}")
    print(f"  训练图片:   {n_train} 张")
    print(f"  验证图片:   {n_val} 张")
    print(f"  训练轮数:   {epochs}（前 {freeze_epochs} 轮冻结骨干）")
    print(f"  批大小:     {batch}")
    print(f"  设备:       {device}")
    print(f"{'='*55}")

    # ── 数据增强 & 预处理 ──
    imagenet_mean = [0.485, 0.456, 0.406]
    imagenet_std  = [0.229, 0.224, 0.225]

    train_transform = transforms.Compose([
        transforms.Resize((imgsz, imgsz)),
        transforms.ColorJitter(brightness=0.3, contrast=0.3, saturation=0.1),
        transforms.RandomAffine(degrees=3, translate=(0.05, 0.05)),
        transforms.ToTensor(),
        transforms.Normalize(mean=imagenet_mean, std=imagenet_std),
    ])
    val_transform = transforms.Compose([
        transforms.Resize((imgsz, imgsz)),
        transforms.ToTensor(),
        transforms.Normalize(mean=imagenet_mean, std=imagenet_std),
    ])

    train_dataset = datasets.ImageFolder(str(train_dir), transform=train_transform)
    # 强制使用按字母排序的类名（与 _collect_classes 一致）
    train_dataset.class_to_idx = {c: i for i, c in enumerate(classes)}
    train_dataset.classes = classes
    # 重建 samples 以使用新的 class_to_idx
    train_dataset.samples = datasets.ImageFolder(str(train_dir)).make_dataset(
        str(train_dir), train_dataset.class_to_idx, extensions=(".png", ".jpg", ".jpeg", ".bmp", ".webp")
    )
    train_dataset.targets = [s[1] for s in train_dataset.samples]

    train_loader = DataLoader(
        train_dataset, batch_size=batch, shuffle=True,
        num_workers=0, pin_memory=(device != "cpu"),
    )

    val_loader = None
    if val_dir.is_dir() and n_val > 0:
        val_dataset = datasets.ImageFolder(str(val_dir), transform=val_transform)
        val_dataset.class_to_idx = {c: i for i, c in enumerate(classes)}
        val_dataset.classes = classes
        val_dataset.samples = datasets.ImageFolder(str(val_dir)).make_dataset(
            str(val_dir), val_dataset.class_to_idx, extensions=(".png", ".jpg", ".jpeg", ".bmp", ".webp")
        )
        val_dataset.targets = [s[1] for s in val_dataset.samples]
        val_loader = DataLoader(
            val_dataset, batch_size=batch, shuffle=False,
            num_workers=0, pin_memory=(device != "cpu"),
        )

    # ── 构建模型 ──
    model = models.mobilenet_v3_small(weights=models.MobileNet_V3_Small_Weights.IMAGENET1K_V1)
    in_features = model.classifier[-1].in_features
    model.classifier[-1] = nn.Linear(in_features, num_classes)

    dev = torch.device(device)
    model = model.to(dev)
    criterion = nn.CrossEntropyLoss()

    # ── 阶段 1：冻结骨干，只训练分类头 ──
    for param in model.features.parameters():
        param.requires_grad = False

    head_params = [p for p in model.parameters() if p.requires_grad]
    optimizer = optim.Adam(head_params, lr=1e-3)
    scheduler = optim.lr_scheduler.CosineAnnealingLR(optimizer, T_max=max(freeze_epochs, 1))

    best_val_acc = 0.0
    best_state = None

    for epoch in range(1, epochs + 1):
        # 阶段 2：解冻全网络
        if epoch == freeze_epochs + 1:
            for param in model.features.parameters():
                param.requires_grad = True
            optimizer = optim.Adam(model.parameters(), lr=1e-4)
            scheduler = optim.lr_scheduler.CosineAnnealingLR(
                optimizer, T_max=max(epochs - freeze_epochs, 1)
            )
            print(f"\n  [epoch {epoch}] 解冻全网络，lr=1e-4")

        # 训练
        model.train()
        running_loss = 0.0
        correct = 0
        total = 0
        for images, labels in train_loader:
            images, labels = images.to(dev), labels.to(dev)
            optimizer.zero_grad()
            outputs = model(images)
            loss = criterion(outputs, labels)
            loss.backward()
            optimizer.step()
            running_loss += loss.item() * images.size(0)
            _, predicted = outputs.max(1)
            total += labels.size(0)
            correct += predicted.eq(labels).sum().item()
        scheduler.step()

        train_loss = running_loss / max(total, 1)
        train_acc = correct / max(total, 1) * 100

        # 验证
        val_acc = 0.0
        if val_loader is not None:
            model.eval()
            v_correct = 0
            v_total = 0
            with torch.no_grad():
                for images, labels in val_loader:
                    images, labels = images.to(dev), labels.to(dev)
                    outputs = model(images)
                    _, predicted = outputs.max(1)
                    v_total += labels.size(0)
                    v_correct += predicted.eq(labels).sum().item()
            val_acc = v_correct / max(v_total, 1) * 100
            phase = "冻结" if epoch <= freeze_epochs else "微调"
            print(f"  [{phase}] epoch {epoch:3d}/{epochs}  loss={train_loss:.4f}  "
                  f"train_acc={train_acc:.1f}%  val_acc={val_acc:.1f}%")
            if val_acc >= best_val_acc:
                best_val_acc = val_acc
                best_state = {k: v.cpu().clone() for k, v in model.state_dict().items()}
        else:
            phase = "冻结" if epoch <= freeze_epochs else "微调"
            print(f"  [{phase}] epoch {epoch:3d}/{epochs}  loss={train_loss:.4f}  "
                  f"train_acc={train_acc:.1f}%")
            best_state = {k: v.cpu().clone() for k, v in model.state_dict().items()}

    # 加载最佳权重
    if best_state is not None:
        model.load_state_dict(best_state)
    model = model.to("cpu")
    model.eval()

    # ── 导出 ONNX ──
    out_dir = export_root / stem
    out_dir.mkdir(parents=True, exist_ok=True)

    onnx_path = out_dir / f"{stem}.onnx"
    dummy = torch.randn(1, 3, imgsz, imgsz)
    torch.onnx.export(
        model, dummy, str(onnx_path),
        input_names=["input"],
        output_names=["output"],
        opset_version=13,
        dynamic_axes={"input": {0: "batch"}, "output": {0: "batch"}},
    )

    # ── 保存标签 ──
    labels_path = out_dir / f"{stem}_labels.json"
    with open(labels_path, "w", encoding="utf-8") as f:
        json.dump(classes, f, ensure_ascii=False, indent=2)

    # ── 保存元数据 ──
    meta = {
        "imgsz": imgsz,
        "category": category,
        "stem": stem,
        "backbone": "mobilenet_v3_small",
        "normalize": True,
    }
    meta_path = out_dir / f"{stem}_meta.json"
    with open(meta_path, "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)

    # ── 复制到运行时目录 ──
    internal = PROJECT_ROOT / "_internal" / "models"
    internal.mkdir(parents=True, exist_ok=True)
    shutil.copy2(onnx_path, internal / f"{stem}.onnx")
    shutil.copy2(labels_path, internal / f"{stem}_labels.json")
    shutil.copy2(meta_path, internal / f"{stem}_meta.json")

    print(f"\n{'='*55}")
    print(f"[完成] {category} 训练成功!")
    print(f"  ONNX 模型:  {onnx_path}")
    print(f"  标签文件:   {labels_path}")
    print(f"  类别列表:   {classes}")
    if val_loader is not None:
        print(f"  最佳验证准确率: {best_val_acc:.1f}%")
    print(f"  已自动复制到 _internal/models/，重启程序即可生效")
    print(f"{'='*55}")
    return True


def main() -> int:
    ap = argparse.ArgumentParser(
        description="MobileNetV3-Small 分类模型训练并导出 ONNX"
    )
    ap.add_argument(
        "--data-root", type=str, default="datasets",
        help="数据集根目录（默认 datasets，由 prepare_dataset.py 生成）",
    )
    ap.add_argument(
        "--export-root", type=str, default="models_export",
        help="模型导出根目录（默认 models_export）",
    )
    ap.add_argument(
        "--category", type=str, default="",
        help="只训练指定类别（如 Name），默认训练全部类别",
    )
    ap.add_argument(
        "--epochs", type=int, default=30,
        help="训练轮数（默认 30）",
    )
    ap.add_argument(
        "--freeze-epochs", type=int, default=5,
        help="前 N 轮冻结骨干只训练分类头（默认 5）",
    )
    ap.add_argument(
        "--batch", type=int, default=16,
        help="批大小（默认 16，CPU 友好）",
    )
    ap.add_argument(
        "--device", type=str, default="cpu",
        help="训练设备：cpu（默认）/ cuda:0（需要 CUDA）",
    )
    args = ap.parse_args()

    data_root = (PROJECT_ROOT / args.data_root).resolve()
    export_root = (PROJECT_ROOT / args.export_root).resolve()

    cats = [args.category] if args.category else list(CATEGORY_CONFIG.keys())

    print(f"训练计划: {cats}")
    print(f"数据目录: {data_root}")
    print(f"导出目录: {export_root}")
    print(f"设备:     {args.device}")

    ok_all = True
    for cat in cats:
        if not train_one(cat, data_root, export_root, args.epochs, args.batch, args.device, args.freeze_epochs):
            ok_all = False

    if ok_all:
        print("\n全部训练完成! 重启程序即可使用 MobileNet ONNX 模型进行识别。")
        print("提示: 在 config.json 中设置 \"recognize_engine\": \"onnx\" 可强制使用模型分类")
        print("      设置 \"recognize_engine\": \"opencv\" 可强制使用模板匹配")
        print("      设置 \"recognize_engine\": \"auto\" 则模型优先、模板匹配兜底（默认）")
    else:
        print("\n部分类别训练失败，请检查上方错误信息。")

    return 0 if ok_all else 1


if __name__ == "__main__":
    raise SystemExit(main())
