#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
PUBG 弹孔 YOLO 模型训练工具
═══════════════════════════════
截图收集 → Roboflow 标注 → 本地训练 → 导出模型

用法:
  1. 收集截图:   python tools/train_yolo.py capture --gun m416
  2. 训练模型:   python tools/train_yolo.py train --data dataset/data.yaml
  3. 验证模型:   python tools/train_yolo.py test --model models/best.pt --image test.png
"""

import argparse
import cv2
import logging
import sys
import time
from pathlib import Path

log = logging.getLogger("train_yolo")


def cmd_capture(args):
    """对墙射击截图收集 — 按空格截图, 按 q 退出。"""
    import mss
    import numpy as np

    out_dir = Path(args.output)
    out_dir.mkdir(parents=True, exist_ok=True)

    print(f"\n{'='*50}")
    print("  PUBG 弹孔截图收集工具")
    print(f"  保存到: {out_dir.resolve()}")
    print(f"{'='*50}")
    print("\n  操作步骤:")
    print("  1. 进入 PUBG 训练场, 面对干净/脏的墙面")
    print("  2. 射击一梭子弹 (不同枪/不同墙/不同距离)")
    print("  3. 按 F8 截图保存")
    print("  4. 换一面墙/换一把枪, 重复")
    print("  5. 建议收集 80-200 张 (包含各种墙面纹理)")
    print("  6. 按 Ctrl+C 退出\n")

    sct = mss.mss()
    mon = sct.monitors[1]
    idx = len(list(out_dir.glob("*.png")))

    from pynput import keyboard as kb
    from pynput.keyboard import Key

    def _on_press(key):
        nonlocal idx
        if key == Key.f8:
            raw = sct.grab(mon)
            img = np.array(raw)[:, :, :3]
            fname = f"shot_{idx:04d}.png"
            cv2.imwrite(str(out_dir / fname), img)
            idx += 1
            print(f"  [{idx}] 已保存: {fname}")

    listener = kb.Listener(on_press=_on_press)
    listener.start()
    print("  按 F8 截图 | Ctrl+C 退出\n")
    try:
        while True:
            time.sleep(0.5)
    except KeyboardInterrupt:
        print(f"\n  共保存 {idx} 张截图到 {out_dir.resolve()}")
    finally:
        listener.stop()


def cmd_train(args):
    """使用 Ultralytics YOLOv8 训练弹孔检测模型。"""
    try:
        from ultralytics import YOLO
    except ImportError:
        print("请先安装: pip install ultralytics")
        sys.exit(1)

    data_yaml = args.data
    if not Path(data_yaml).exists():
        print(f"找不到数据集配置: {data_yaml}")
        print("\n请按照以下步骤准备数据集:")
        print("  1. 在 Roboflow (roboflow.com) 创建项目")
        print("  2. 上传截图, 用矩形框标注每个弹孔")
        print("  3. 导出为 YOLOv8 格式")
        print("  4. 解压到 dataset/ 目录")
        print(f"  5. 确保 {data_yaml} 存在")
        sys.exit(1)

    model_size = args.model_size
    epochs = args.epochs
    imgsz = args.imgsz
    batch = args.batch

    print(f"\n{'='*50}")
    print(f"  训练 YOLOv8{model_size} 弹孔检测模型")
    print(f"  数据集: {data_yaml}")
    print(f"  轮次: {epochs}  图像: {imgsz}  批次: {batch}")
    print(f"{'='*50}\n")

    base_model = f"yolov8{model_size}.pt"
    model = YOLO(base_model)

    results = model.train(
        data=data_yaml,
        epochs=epochs,
        imgsz=imgsz,
        batch=batch,
        name="bullet_hole",
        project="runs/detect",
        patience=20,
        lr0=0.01,
        lrf=0.01,
        mosaic=1.0,
        flipud=0.5,
        fliplr=0.5,
        degrees=10,
        translate=0.1,
        scale=0.5,
    )

    best_pt = Path("runs/detect/bullet_hole/weights/best.pt")
    if best_pt.exists():
        out = Path("models")
        out.mkdir(exist_ok=True)
        dest = out / "bullet_hole_best.pt"
        import shutil
        shutil.copy2(best_pt, dest)
        print(f"\n  模型已导出: {dest.resolve()}")
        print(f"  在视频校准中使用: --model {dest}")
    else:
        print(f"\n  训练完成, 请在 runs/detect/bullet_hole/weights/ 查找 best.pt")


def cmd_test(args):
    """测试已训练的 YOLO 模型。"""
    try:
        from ultralytics import YOLO
    except ImportError:
        print("请先安装: pip install ultralytics")
        sys.exit(1)

    model = YOLO(args.model)
    img = cv2.imread(args.image)
    if img is None:
        print(f"无法读取图片: {args.image}")
        sys.exit(1)

    results = model(img, conf=args.conf, verbose=True)

    n = 0
    for r in results:
        for box in r.boxes:
            x1, y1, x2, y2 = box.xyxy[0].tolist()
            conf = float(box.conf[0])
            cx, cy = int((x1+x2)/2), int((y1+y2)/2)
            print(f"  弹孔 #{n+1}: ({cx}, {cy}) conf={conf:.1%}")
            cv2.rectangle(img, (int(x1), int(y1)), (int(x2), int(y2)),
                          (0, 255, 0), 2)
            cv2.putText(img, f"{n+1} {conf:.0%}", (int(x1), int(y1)-5),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 1)
            n += 1

    print(f"\n  共检测 {n} 个弹孔")

    out_path = Path(args.image).stem + "_detected.png"
    cv2.imwrite(out_path, img)
    print(f"  标注图: {out_path}")


def cmd_create_yaml(args):
    """生成 dataset/data.yaml 模板。"""
    out = Path(args.output)
    out.mkdir(parents=True, exist_ok=True)
    for sub in ("images/train", "images/val", "labels/train", "labels/val"):
        (out / sub).mkdir(parents=True, exist_ok=True)

    yaml_content = f"""# PUBG 弹孔检测数据集
path: {out.resolve()}
train: images/train
val: images/val

nc: 1
names:
  0: bullet_hole
"""
    yaml_path = out / "data.yaml"
    yaml_path.write_text(yaml_content)
    print(f"\n  数据集目录已创建: {out.resolve()}")
    print(f"  配置文件: {yaml_path}")
    print(f"\n  目录结构:")
    print(f"    {out}/")
    print(f"      data.yaml")
    print(f"      images/train/  ← 训练图片 (80%)")
    print(f"      images/val/    ← 验证图片 (20%)")
    print(f"      labels/train/  ← 训练标签")
    print(f"      labels/val/    ← 验证标签")
    print(f"\n  标签格式 (每行一个弹孔):")
    print(f"    0 <x_center> <y_center> <width> <height>")
    print(f"    (值为 0~1 的归一化坐标)")
    print(f"\n  推荐使用 Roboflow 在线标注后导出到此目录")


def main():
    parser = argparse.ArgumentParser(description="PUBG 弹孔 YOLO 训练工具")
    sub = parser.add_subparsers(dest="cmd", help="子命令")

    p_cap = sub.add_parser("capture", help="截图收集")
    p_cap.add_argument("--output", "-o", default="dataset/raw",
                        help="截图保存目录")

    p_train = sub.add_parser("train", help="训练模型")
    p_train.add_argument("--data", "-d", default="dataset/data.yaml",
                          help="数据集 YAML")
    p_train.add_argument("--model-size", "-s", default="n",
                          choices=["n", "s", "m", "l"],
                          help="模型大小: n(最快) s m l(最准)")
    p_train.add_argument("--epochs", "-e", type=int, default=100)
    p_train.add_argument("--imgsz", type=int, default=640)
    p_train.add_argument("--batch", "-b", type=int, default=16)

    p_test = sub.add_parser("test", help="测试模型")
    p_test.add_argument("--model", "-m", required=True, help=".pt 模型路径")
    p_test.add_argument("--image", "-i", required=True, help="测试图片")
    p_test.add_argument("--conf", type=float, default=0.25)

    p_yaml = sub.add_parser("init", help="创建数据集目录模板")
    p_yaml.add_argument("--output", "-o", default="dataset")

    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO)

    if args.cmd == "capture":
        cmd_capture(args)
    elif args.cmd == "train":
        cmd_train(args)
    elif args.cmd == "test":
        cmd_test(args)
    elif args.cmd == "init":
        cmd_create_yaml(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
