#!/usr/bin/env python3
"""
YOLOv8-cls 分类模型训练 + ONNX 导出一键脚本。

==========  完整训练流程  ==========

第 1 步：安装训练依赖（只需一次）
    pip install -r requirements_train.txt

第 2 步：收集数据
    用 debug 模式运行程序，在游戏中操作（切枪、打开背包、切换姿势等）
    图片自动保存到 logs/training_data/<Category>/<Label>/ 下

第 3 步：准备数据集
    python tools/prepare_dataset.py

第 4 步：训练（即本脚本）
    python tools/train_classifier.py --epochs 50          # 训练全部类别
    python tools/train_classifier.py --category Name      # 只训练枪械名称
    python tools/train_classifier.py --device 0           # 使用 GPU 0 训练（需要 CUDA）

第 5 步：模型自动复制到 _internal/models/，重启程序即可使用

==========  输出文件  ==========
    models_export/<stem>/
        <stem>.onnx             — ONNX 模型
        <stem>_labels.json      — 类别标签
        meta.json               — 训练参数
    _internal/models/           — 运行时模型目录（自动复制）
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path
from typing import Dict, Optional, Tuple

PROJECT_ROOT = Path(__file__).resolve().parent.parent

# 类别配置：(ONNX 文件名前缀, 训练输入尺寸)
# 与 core/classifier.py 中的 _CATEGORY_STEM_DEFAULT_IMGSZ 保持一致
CATEGORY_CONFIG: Dict[str, Tuple[str, int]] = {
    "Name":   ("name_cls",     224),   # 枪械名称（背包里的文字较小，用大尺寸）
    "Scope":  ("scope_cls",    128),   # 倍镜图标
    "Muzzle": ("muzzle_cls",   128),   # 枪口图标
    "Grip":   ("grip_cls",     128),   # 握把图标
    "Stock":  ("stock_cls",    128),   # 枪托图标
    "gun":    ("gun_hud_cls",  128),   # HUD 武器图标
    "zishi":  ("posture_cls",  128),   # 姿势图标（站/蹲/趴）
}


def train_one(
    category: str,
    data_root: Path,
    export_root: Path,
    epochs: int,
    batch: int,
    device: Optional[str],
) -> bool:
    """
    训练单个类别的分类模型。

    :param category:  类别名（如 "Name", "Scope"）
    :param data_root: 数据集根目录（包含 train/val 子目录）
    :param export_root: ONNX 导出目录
    :param epochs:    训练轮数
    :param batch:     批大小
    :param device:    训练设备（None=自动, "cpu", "0"=GPU 0）
    :return: 是否成功
    """
    # ---- 检查依赖 ----
    try:
        from ultralytics import YOLO
    except ImportError:
        print("[错误] ultralytics 未安装！请运行:", file=sys.stderr)
        print("       pip install -r requirements_train.txt", file=sys.stderr)
        return False

    if category not in CATEGORY_CONFIG:
        print(f"[错误] 未知类别: {category}", file=sys.stderr)
        print(f"       可选类别: {list(CATEGORY_CONFIG.keys())}", file=sys.stderr)
        return False

    stem, imgsz = CATEGORY_CONFIG[category]

    # ---- 检查训练数据 ----
    dataset = data_root / category
    train_dir = dataset / "train"
    if not train_dir.is_dir():
        print(f"[跳过] 缺少训练数据: {train_dir}", file=sys.stderr)
        print(f"       请先运行: python tools/prepare_dataset.py", file=sys.stderr)
        return False

    val_dir = dataset / "val"
    if not val_dir.is_dir():
        print(f"[警告] 无验证目录: {val_dir}", file=sys.stderr)
        print(f"       请先运行 tools/prepare_dataset.py 划分数据集", file=sys.stderr)

    # 统计训练数据量
    n_classes = len([d for d in train_dir.iterdir() if d.is_dir()])
    n_images = sum(1 for _ in train_dir.rglob("*") if _.is_file())
    print(f"\n{'='*50}")
    print(f"[开始训练] 类别: {category}")
    print(f"  模型前缀: {stem}")
    print(f"  输入尺寸: {imgsz}x{imgsz}")
    print(f"  训练轮数: {epochs}")
    print(f"  批大小:   {batch}")
    print(f"  子类数:   {n_classes}")
    print(f"  训练图片: ~{n_images} 张")
    print(f"  数据目录: {dataset}")
    print(f"{'='*50}")

    out_dir = export_root / stem
    out_dir.mkdir(parents=True, exist_ok=True)

    weights_dir = out_dir / "runs_train"
    weights_dir.mkdir(exist_ok=True)

    # ---- 加载预训练模型 ----
    # yolov8n-cls.pt 是 YOLOv8 nano 分类版，首次运行时自动下载（~6MB）
    model = YOLO("yolov8n-cls.pt")

    train_kw = dict(
        data=str(dataset),       # 数据集路径（包含 train/ 和 val/ 子目录）
        epochs=epochs,           # 训练轮数
        imgsz=imgsz,             # 输入图像缩放到此尺寸
        batch=batch,             # 批大小（显存不足时减小）
        project=str(weights_dir),
        name="train",
        exist_ok=True,           # 允许覆盖已有的训练结果
    )
    if device:
        train_kw["device"] = device

    # ---- 开始训练 ----
    print(f"\n开始训练 {category}...")
    print(f"训练过程中会显示每轮的 loss 和准确率，请耐心等待。\n")
    model.train(**train_kw)

    # ---- 查找最佳权重 ----
    best_pt = weights_dir / "train" / "weights" / "best.pt"
    if not best_pt.is_file():
        found = sorted(
            weights_dir.rglob("**/weights/best.pt"),
            key=lambda p: p.stat().st_mtime,
        )
        if found:
            best_pt = found[-1]
    if not best_pt.is_file():
        print(f"[错误] 未找到 best.pt，训练可能失败", file=sys.stderr)
        print(f"       请检查目录: {weights_dir}", file=sys.stderr)
        return False

    print(f"\n找到最佳权重: {best_pt}")

    # ---- 导出 ONNX ----
    print(f"正在导出 ONNX 模型...")
    model_final = YOLO(str(best_pt))
    onnx_path = model_final.export(format="onnx", imgsz=imgsz)

    onnx_path = Path(onnx_path)
    target_onnx = out_dir / f"{stem}.onnx"
    shutil.copy2(onnx_path, target_onnx)

    # ---- 保存标签文件 ----
    names = model_final.names
    if isinstance(names, dict):
        labels = [names[i] for i in range(len(names))]
    else:
        labels = list(names)

    labels_path = out_dir / f"{stem}_labels.json"
    with open(labels_path, "w", encoding="utf-8") as f:
        json.dump(labels, f, ensure_ascii=False, indent=2)

    meta = {"imgsz": imgsz, "category": category, "stem": stem}
    with open(out_dir / "meta.json", "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)

    # ---- 自动复制到运行时目录 ----
    internal = PROJECT_ROOT / "_internal" / "models"
    internal.mkdir(parents=True, exist_ok=True)
    shutil.copy2(target_onnx, internal / f"{stem}.onnx")
    shutil.copy2(labels_path, internal / f"{stem}_labels.json")
    shutil.copy2(out_dir / "meta.json", internal / f"{stem}_meta.json")

    print(f"\n{'='*50}")
    print(f"[完成] {category} 训练成功!")
    print(f"  ONNX 模型:  {target_onnx}")
    print(f"  标签文件:   {labels_path}")
    print(f"  类别列表:   {labels}")
    print(f"  已自动复制到 _internal/models/，重启程序即可生效")
    print(f"{'='*50}")
    return True


def main() -> int:
    ap = argparse.ArgumentParser(
        description="YOLOv8-cls 分类模型训练并导出 ONNX（新手友好版）"
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
        "--epochs", type=int, default=50,
        help="训练轮数（默认 50，数据量少时可减少到 30）",
    )
    ap.add_argument(
        "--batch", type=int, default=32,
        help="批大小（默认 32，显存不足时改为 16 或 8）",
    )
    ap.add_argument(
        "--device", type=str, default="",
        help="训练设备：空=自动, cpu=纯 CPU, 0=GPU 0（需要 CUDA）",
    )
    args = ap.parse_args()

    data_root = (PROJECT_ROOT / args.data_root).resolve()
    export_root = (PROJECT_ROOT / args.export_root).resolve()

    device = args.device.strip() or None

    # 决定训练哪些类别
    cats = (
        [args.category]
        if args.category
        else list(CATEGORY_CONFIG.keys())
    )

    print(f"训练计划: {cats}")
    print(f"数据目录: {data_root}")
    print(f"导出目录: {export_root}")

    ok_all = True
    for cat in cats:
        if not train_one(cat, data_root, export_root, args.epochs, args.batch, device):
            ok_all = False

    if ok_all:
        print("\n全部训练完成! 重启程序即可使用 ONNX 模型进行识别。")
    else:
        print("\n部分类别训练失败，请检查上方错误信息。")

    return 0 if ok_all else 1


if __name__ == "__main__":
    raise SystemExit(main())
