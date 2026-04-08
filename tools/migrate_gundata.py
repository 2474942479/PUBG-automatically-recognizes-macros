#!/usr/bin/env python3
"""
GunData v1 → v2 迁移工具
将 per-tick 整数数组格式转换为 per-shot 浮点数组格式，
支持水平补偿字段和元数据。

用法:
    python tools/migrate_gundata.py [--dry-run] [--backup]
    python tools/migrate_gundata.py --dir ./_internal/GunData --backup
"""

import json
import os
import re
import shutil
import argparse
from pathlib import Path

TICK_MS = 9

GUN_META = {
    "ace32":  {"fire_interval": 0.088235, "mag": 40},
    "akm":    {"fire_interval": 0.100,    "mag": 40},
    "aug":    {"fire_interval": 0.080,    "mag": 40},
    "famas":  {"fire_interval": 0.06666,  "mag": 35},
    "g36c":   {"fire_interval": 0.0857,   "mag": 40},
    "groza":  {"fire_interval": 0.080,    "mag": 40},
    "k2":     {"fire_interval": 0.0857,   "mag": 40},
    "m16a4":  {"fire_interval": 0.075,    "mag": 40},
    "m416":   {"fire_interval": 0.0857,   "mag": 40},
    "m762":   {"fire_interval": 0.085714, "mag": 40},
    "mk47":   {"fire_interval": 0.075,    "mag": 40},
    "qbz":    {"fire_interval": 0.0923,   "mag": 40},
    "scar-l": {"fire_interval": 0.096,    "mag": 40},
    "js9":    {"fire_interval": 0.0667,   "mag": 40},
    "mp5k":   {"fire_interval": 0.067,    "mag": 40},
    "p90":    {"fire_interval": 0.060,    "mag": 50},
    "pp19":   {"fire_interval": 0.086,    "mag": 53},
    "tangmuxunchongfengqiang": {"fire_interval": 0.080, "mag": 50},
    "ump45":  {"fire_interval": 0.090,    "mag": 35},
    "uzi":    {"fire_interval": 0.048,    "mag": 35},
    "vector": {"fire_interval": 0.0545,   "mag": 33},
    "dp28":   {"fire_interval": 0.109,    "mag": 47},
    "m249":   {"fire_interval": 0.075,    "mag": 75},
    "mg3":    {"fire_interval": 0.085714, "mag": 75},
    "delagongnuofu":           {"fire_interval": 0.100, "mag": 10},
    "mini14":                  {"fire_interval": 0.100, "mag": 30},
    "mk12":                    {"fire_interval": 0.100, "mag": 30},
    "mk14":                    {"fire_interval": 0.090, "mag": 20},
    "qbu":                     {"fire_interval": 0.100, "mag": 20},
    "sks":                     {"fire_interval": 0.100, "mag": 20},
    "vss":                     {"fire_interval": 0.0856, "mag": 20},
    "zidongzhuangtianbuqiang": {"fire_interval": 0.100, "mag": 20},
}

SEMI_AUTO_GUNS = {
    "sks", "mini14", "delagongnuofu", "m16a4",
    "mk12", "mk47", "qbu", "zidongzhuangtianbuqiang"
}

POSTURE_KEYS = {"none", "c", "z"}
ACC_RE = re.compile(r'^A\d+B\d+C\d+$')


def _trim_trailing_zeros(arr):
    i = len(arr) - 1
    while i >= 0 and arr[i] == 0:
        i -= 1
    return max(0, i + 1)


def _chunk_sum(arr, chunk_size):
    result = []
    for start in range(0, len(arr), chunk_size):
        chunk = arr[start:start + chunk_size]
        result.append(round(sum(float(v) for v in chunk), 2))
    return result


def migrate_one(filepath, dry_run=False):
    weapon = Path(filepath).stem

    with open(filepath, 'r', encoding='utf-8') as f:
        v1 = json.load(f)

    if v1.get("version") == 2:
        print(f"  [跳过] {weapon} 已是 v2 格式")
        return False

    meta = GUN_META.get(weapon.lower(), {})
    fire_interval = meta.get("fire_interval", 0.0857)
    magazine = meta.get("mag", 40)
    is_semi = weapon.lower() in SEMI_AUTO_GUNS

    fire_interval_ms = round(fire_interval * 1000, 3)
    ticks_per_shot = max(1, round(fire_interval_ms / TICK_MS))
    rpm = round(60.0 / fire_interval) if fire_interval > 0 else 0

    posture = {}
    for k in POSTURE_KEYS:
        if k in v1:
            posture[k] = float(v1[k])
    if not posture:
        posture = {"none": 1.0, "c": 0.8, "z": 0.55}

    recoil = {}
    for key, value in v1.items():
        if not ACC_RE.match(key):
            continue
        if not isinstance(value, list):
            continue

        eff_len = _trim_trailing_zeros(value)
        if eff_len == 0:
            recoil[key] = {"y": [], "x": []}
            continue

        effective = value[:eff_len]

        if is_semi:
            per_shot_y = [round(float(v), 2) for v in effective]
        else:
            per_shot_y = _chunk_sum(effective, ticks_per_shot)

        per_shot_x = [0.0] * len(per_shot_y)
        recoil[key] = {"y": per_shot_y, "x": per_shot_x}

    v2 = {
        "version": 2,
        "weapon": weapon,
        "rpm": rpm,
        "fire_interval_ms": fire_interval_ms,
        "tick_ms": TICK_MS,
        "ticks_per_shot": ticks_per_shot,
        "magazine": magazine,
        "semi_auto": is_semi,
        "posture": posture,
        "recoil": recoil
    }

    if not dry_run:
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(v2, f, ensure_ascii=False, indent=4)

    n_calibrated = sum(1 for r in recoil.values() if r.get("y"))
    n_total = len(recoil)
    print(f"  [{'预览' if dry_run else '转换'}] {weapon}: "
          f"{n_calibrated}/{n_total} 配件已校准, "
          f"RPM={rpm}, ticks/shot={ticks_per_shot}, "
          f"semi_auto={is_semi}")
    return True


def main():
    parser = argparse.ArgumentParser(description="GunData v1 → v2 迁移工具")
    parser.add_argument("--dry-run", action="store_true", help="仅预览，不修改文件")
    parser.add_argument("--backup", action="store_true", help="迁移前备份原始文件")
    parser.add_argument("--dir", default="./_internal/GunData",
                        help="GunData 目录路径 (默认: ./_internal/GunData)")
    args = parser.parse_args()

    gun_dir = Path(args.dir)
    if not gun_dir.exists():
        print(f"目录不存在: {gun_dir}")
        return

    if args.backup:
        backup_dir = gun_dir.parent / "GunData_v1_backup"
        if not backup_dir.exists():
            shutil.copytree(gun_dir, backup_dir)
            print(f"已备份至: {backup_dir}")
        else:
            print(f"备份目录已存在，跳过备份: {backup_dir}")

    json_files = sorted(gun_dir.glob("*.json"))
    print(f"找到 {len(json_files)} 个枪械数据文件\n")

    converted = 0
    for fp in json_files:
        try:
            if migrate_one(str(fp), dry_run=args.dry_run):
                converted += 1
        except Exception as e:
            print(f"  [错误] {fp.stem}: {e}")

    action = "预览" if args.dry_run else "转换"
    print(f"\n{action}完成: {converted}/{len(json_files)} 个文件")


if __name__ == "__main__":
    main()
