#!/usr/bin/env python3
"""
数据集划分工具：将自动采集的 ROI 图像拆分为 train / val 两个子集。

==========  工作流程  ==========
1. 用 debug 模式运行程序 → 自动在 logs/training_data/ 下按类别/标签保存图片
2. 运行本脚本  → 将图片复制到 datasets/<Category>/train/ 和 val/ 目录
3. 运行 train_classifier.py  → 用整理好的数据训练 YOLOv8-cls 模型

输入结构示例（自动采集）:
    logs/training_data/
        Name/
            m416/  *.png
            akm/   *.png
        Scope/
            red_dot/ *.png
            ...

输出结构示例（YOLOv8-cls 要求）:
    datasets/
        Name/
            train/
                m416/  *.png
                akm/   *.png
            val/
                m416/  *.png
                akm/   *.png

用法:
    python tools/prepare_dataset.py                                # 默认参数
    python tools/prepare_dataset.py --src logs/training_data --out datasets --val-ratio 0.2
    python tools/prepare_dataset.py --move                         # 移动而非复制（节省磁盘）
"""

from __future__ import annotations

import argparse
import hashlib
import random
import shutil
from pathlib import Path
from typing import List, Set, Tuple

IMAGE_EXTS = {".png", ".bmp", ".jpg", ".jpeg", ".webp"}


def gather_images(class_dir: Path) -> List[Path]:
    """收集目录下所有支持格式的图片文件"""
    files = []
    for p in class_dir.iterdir():
        if p.is_file() and p.suffix.lower() in IMAGE_EXTS:
            files.append(p)
    return sorted(files)


def split_class(
    class_dir: Path,
    train_dest: Path,
    val_dest: Path,
    val_ratio: float,
    seed: int,
    copy: bool,
) -> Tuple[int, int]:
    """
    将一个子类目录的图片按比例分配到 train / val。

    :return: (训练集张数, 验证集张数)
    """
    imgs = gather_images(class_dir)
    if not imgs:
        return 0, 0

    # 用类名的哈希值混合随机种子，保证每个子类的洗牌独立但可复现
    h = int(hashlib.md5(class_dir.name.encode("utf-8")).hexdigest()[:8], 16)
    rng = random.Random((seed ^ h) % (2**31))
    rng.shuffle(imgs)

    # 至少保留 1 张验证集，只有 1 张时全给训练集
    n_val = max(1, int(len(imgs) * val_ratio)) if len(imgs) >= 2 else 0
    val_set: Set[Path] = set(imgs[-n_val:]) if n_val else set()

    nt, nv = 0, 0
    train_dest.mkdir(parents=True, exist_ok=True)
    val_dest.mkdir(parents=True, exist_ok=True)

    for p in imgs:
        dest_parent = val_dest if p in val_set else train_dest
        dest = dest_parent / p.name
        # 避免同名覆盖
        if dest.exists():
            stem, suf = dest.stem, dest.suffix
            k = 1
            while dest.exists():
                dest = dest_parent / f"{stem}_{k}{suf}"
                k += 1
        if copy:
            shutil.copy2(p, dest)
        else:
            shutil.move(str(p), str(dest))
        if p in val_set:
            nv += 1
        else:
            nt += 1
    return nt, nv


def main():
    ap = argparse.ArgumentParser(
        description="将 logs/training_data/ 按类别划分为 train/val 数据集"
    )
    ap.add_argument(
        "--src", type=str, default="logs/training_data",
        help="采集根目录（默认 logs/training_data）",
    )
    ap.add_argument(
        "--out", type=str, default="datasets",
        help="输出根目录（默认 datasets）",
    )
    ap.add_argument(
        "--val-ratio", type=float, default=0.2, dest="val_ratio",
        help="验证集占比，默认 0.2（即 80%% 训练 / 20%% 验证）",
    )
    ap.add_argument(
        "--seed", type=int, default=42,
        help="随机种子，保证每次运行结果一致",
    )
    ap.add_argument(
        "--move", action="store_true",
        help="移动文件而非复制（节省磁盘空间，但原始数据会被清空）",
    )
    args = ap.parse_args()

    src_root = Path(args.src).resolve()
    out_root = Path(args.out).resolve()
    if not src_root.is_dir():
        print(f"[错误] 数据目录不存在: {src_root}")
        print("请先用 debug 模式运行程序收集训练数据。")
        return 1

    categories = [
        d for d in src_root.iterdir()
        if d.is_dir() and not d.name.startswith(".")
    ]
    if not categories:
        print(f"[错误] {src_root} 下没有类别子目录")
        return 1

    total_train = total_val = 0
    for cat_dir in sorted(categories, key=lambda x: x.name):
        classes = [
            d for d in cat_dir.iterdir()
            if d.is_dir() and not d.name.startswith(".")
        ]
        if not classes:
            continue
        print(f"\n类别 [{cat_dir.name}]: 共 {len(classes)} 个子类")
        for cls_dir in sorted(classes, key=lambda x: x.name.lower()):
            train_dest = out_root / cat_dir.name / "train" / cls_dir.name
            val_dest = out_root / cat_dir.name / "val" / cls_dir.name
            nt, nv = split_class(
                cls_dir,
                train_dest,
                val_dest,
                args.val_ratio,
                args.seed,
                copy=not args.move,
            )
            total_train += nt
            total_val += nv
            if nt or nv:
                print(f"  {cls_dir.name}: train={nt}, val={nv}")

    print(f"\n完成! 训练集={total_train} 张, 验证集={total_val} 张")
    print(f"输出目录: {out_root}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
