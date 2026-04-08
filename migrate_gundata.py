"""
GunData v1 → v2 迁移工具

v1 格式: 每个元素 = 1 tick (9ms) 的鼠标位移, 仅垂直方向
v2 格式: 每个元素 = 1 发子弹的总鼠标位移(float), 支持水平方向, 运行时平滑展开

用法: python migrate_gundata.py
"""

import json
import os
import re
import shutil

GUNDATA_DIR = "./_internal/GunData"
BACKUP_DIR = "./_internal/GunData_v1_backup"
TICK_MS = 9

POSTURE_KEYS = {"none", "c", "z"}
ACC_PATTERN = re.compile(r'^A\d+B\d+C\d+$')

SEMI_AUTO_WEAPONS = {
    "sks", "mini14", "delagongnuofu", "m16a4",
    "mk12", "mk47", "qbu", "zidongzhuangtianbuqiang",
}

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


def trim_trailing_zeros(arr):
    """去除数组尾部连续零值"""
    i = len(arr) - 1
    while i >= 0 and arr[i] == 0:
        i -= 1
    return arr[:max(1, i + 1)]


def is_uncalibrated(arr):
    """判断是否为未校准数据 (全零或极短全零数组)"""
    return all(v == 0 for v in arr)


def convert_fullato_array(arr, ticks_per_shot):
    """全自动: per-tick → per-shot, 按 ticks_per_shot 分块求和"""
    trimmed = trim_trailing_zeros(arr)
    if is_uncalibrated(trimmed):
        return [0.0]

    per_shot = []
    for i in range(0, len(trimmed), ticks_per_shot):
        chunk = trimmed[i:i + ticks_per_shot]
        per_shot.append(round(sum(chunk), 2))
    return per_shot


def convert_semiauto_array(arr):
    """半自动: v1 中每个元素已对应 1 发, 直接转为 float"""
    trimmed = trim_trailing_zeros(arr)
    if is_uncalibrated(trimmed):
        return [0.0]
    return [round(float(v), 2) for v in trimmed]


def migrate_one_weapon(weapon_name, v1_data):
    """将一个武器的 v1 JSON 数据转换为 v2 格式"""
    meta = GUN_META.get(weapon_name.lower())
    if meta is None:
        print(f"  [跳过] {weapon_name}: 未在 GUN_META 中找到元数据")
        return None

    fire_interval_ms = meta["fire_interval"] * 1000
    magazine = meta["mag"]
    is_semi = weapon_name.lower() in SEMI_AUTO_WEAPONS

    if is_semi:
        ticks_per_shot = round(fire_interval_ms / TICK_MS)
    else:
        ticks_per_shot = round(fire_interval_ms / TICK_MS)

    rpm = round(60.0 / meta["fire_interval"])

    posture = {}
    for k in POSTURE_KEYS:
        if k in v1_data:
            posture[k] = v1_data[k]

    recoil = {}
    for key, value in v1_data.items():
        if not ACC_PATTERN.match(key):
            continue
        if not isinstance(value, list):
            continue

        if is_semi:
            y_per_shot = convert_semiauto_array(value)
        else:
            y_per_shot = convert_fullato_array(value, ticks_per_shot)

        x_per_shot = [0.0] * len(y_per_shot)
        recoil[key] = {"y": y_per_shot, "x": x_per_shot}

    v2 = {
        "version": 2,
        "weapon": weapon_name,
        "rpm": rpm,
        "fire_interval_ms": round(fire_interval_ms, 3),
        "tick_ms": TICK_MS,
        "ticks_per_shot": ticks_per_shot,
        "magazine": magazine,
        "posture": posture,
        "recoil": recoil,
    }
    return v2


def main():
    if not os.path.isdir(GUNDATA_DIR):
        print(f"错误: GunData 目录不存在: {GUNDATA_DIR}")
        return

    os.makedirs(BACKUP_DIR, exist_ok=True)
    print(f"备份目录: {BACKUP_DIR}")

    json_files = [f for f in os.listdir(GUNDATA_DIR) if f.endswith(".json")]
    print(f"发现 {len(json_files)} 个 JSON 文件\n")

    migrated = 0
    skipped = 0

    for fname in sorted(json_files):
        weapon_name = fname.replace(".json", "")
        src_path = os.path.join(GUNDATA_DIR, fname)

        with open(src_path, "r", encoding="utf-8") as f:
            v1_data = json.load(f)

        if v1_data.get("version") == 2:
            print(f"  [已是v2] {fname}")
            skipped += 1
            continue

        backup_path = os.path.join(BACKUP_DIR, fname)
        shutil.copy2(src_path, backup_path)

        v2_data = migrate_one_weapon(weapon_name, v1_data)
        if v2_data is None:
            skipped += 1
            continue

        with open(src_path, "w", encoding="utf-8") as f:
            json.dump(v2_data, f, ensure_ascii=False, indent=4)

        n_recoil = len(v2_data["recoil"])
        calibrated = sum(1 for v in v2_data["recoil"].values()
                         if not is_uncalibrated(v["y"]))
        print(f"  [迁移完成] {fname}: "
              f"tps={v2_data['ticks_per_shot']}, "
              f"配件组合={n_recoil}, 已校准={calibrated}")
        migrated += 1

    print(f"\n完成: 迁移 {migrated} 个, 跳过 {skipped} 个")
    print(f"原始文件已备份至: {BACKUP_DIR}")


if __name__ == "__main__":
    main()
