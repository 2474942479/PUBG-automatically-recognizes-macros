# -*- coding: utf-8 -*-
"""
迁移脚本：将 data.txt (Lua aweapon.lua 格式) 完整迁移为 Python 项目 v3 格式的 GunData JSON。

v3 格式核心设计——完全对齐 Lua 脚本的压枪体系：
  1. recoil key 使用 ABCD 4位码（含镜组 A 位），与 data.txt / Lua 脚本完全一致
  2. 数据为 per-tick（来自 data.txt 的 {x,y,d} 条目），不再是 per-shot
  3. 每把枪有独立的 gun_ratio（来自 Lua 脚本的 xxx_ratio），不再全局统一
  4. 倍镜系数使用 scope_map（来自 Lua 脚本的 ratiobj 计算），替代 config.json 中的灵敏度
  5. 姿态系数使用 posture_map（来自 Lua 脚本的 dra/zhan 处理）

Lua 压枪公式：
  ymove = ceil(ditu * all_ratio * GunRatio[noweapon] * ratiobj * dra * data.y)
  简化后（ditu=1, all_ratio=1）：
  ymove = ceil(gun_ratio * scope_factor * posture_factor * y)

data.txt 格式说明:
  每行: WEAPON_ABCD={{x=0,y=N,d=M},{x=0,y=N,d=M},...}
  ABCD 4位配件码（来自 Lua 脚本注释）:
    A(千位)=镜组: 1=机瞄/红点/全息, 2=2倍镜及以上
    B(百位)=枪口: 0=无, 1=补偿器, 2=消焰器, 3=消音器, 4=制退器(扼流圈/鸭嘴)
    C(十位)=握把: 0=无, 1=垂直, 2=直角, 3=半截式, 4=拇指
    D(个位)=枪托: 0=无, 1=战术枪托/托腮板, 2=子弹袋
  每条 {x,y,d} 是 per-tick 数据:
    y = 本 tick 垂直补偿量（原始值，需乘以 gun_ratio * scope * posture）
    x = 本 tick 水平补偿量
    d = tick 间隔(毫秒)

用法:
  python tools/migrate_from_datatxt.py
"""

import re
import os
import json
import shutil
from collections import Counter

# ───────────────────────────────────────────
# 配置
# ───────────────────────────────────────────
DATA_TXT_PATH = "./_internal/data.txt"
GUNDATA_DIR = "./_internal/GunData"
GUNDATA_BACKUP_DIR = "./_internal/GunData_v2_backup"
OUTPUT_DIR = "./_internal/GunData"

# data.txt 武器名 → Python 项目枪械文件名
WEAPON_NAME_MAP = {
    "ACE32": "ace32", "AKM": "akm", "AUG": "aug",
    "BIZON": "pp19", "DELA": "delagongnuofu",
    "DP28": "dp28", "FAMAS": "famas",
    "G36C": "g36c", "Groza": "groza",
    "JS9": "js9", "K2": "k2",
    "M249": "m249", "M416": "m416",
    "M762": "m762", "MG3": "mg3",
    "MINI": "mini14", "MK12": "mk12",
    "MK14": "mk14", "MK47": "mk47",
    "MP5K": "mp5k", "MP9": "mp9",
    "P90": "p90", "QBU": "qbu",
    "QBZ": "qbz", "SCARL": "scar-l",
    "SKS": "sks", "Thompson": "tangmuxunchongfengqiang",
    "UMP45": "ump45", "UZI": "uzi",
    "VSS": "vss", "Vector": "vector",
    "ZIDONG": "zidongzhuangtianbuqiang",
}

# 各武器独立压枪系数（来自 Lua 脚本的 xxx_ratio 变量）
# 这些值经过实际测试调整，使弹道尽量集中在一个点
GUN_RATIO = {
    "AKM": 1.0,
    "M762": 0.92,
    "G36C": 0.88,
    "M416": 0.84,
    "SCARL": 0.94,
    "QBZ": 0.88,
    "AUG": 0.85,
    "Groza": 0.84,
    "ACE32": 0.89,
    "K2": 0.88,       # Lua 中未单独定义，使用默认值
    "BIZON": 0.88,    # Bizon PP-19，Lua 中未单独定义
    "Thompson": 0.83,
    "UMP45": 1.0,
    "UZI": 0.7,
    "Vector": 0.9,
    "MP5K": 0.9,
    "P90": 1.0,
    "JS9": 1.2,
    "M249": 0.93,
    "MG3": 1.0,
    "MK14": 0.8,
    "FAMAS": 1.0,
    "MP9": 1.0,
    "VSS": 1.2,
    "DP28": 1.0,
    "MK47": 0.35,
    "ZIDONG": 0.6,
    "DELA": 0.6,
    "QBU": 0.6,
    "MK12": 0.6,
    "MINI": 0.6,
    "SKS": 0.5,
}

# 倍镜系数映射（来自 Lua 脚本的 ratiobj 计算）
# jz=1(机瞄/红点/全息) → ratiobj=1
# jz=2 → ratiobj=1.76
# jz=3 → ratiobj=2.8
# jz=4 → ratiobj=4
# jz=6 → ratiobj=5.76
SCOPE_MAP = {
    "none": 1.0,            # 机瞄
    "hongdian": 1.0,        # 红点
    "quanxi": 1.0,          # 全息
    "2bei": 1.76,           # 2倍
    "3bei": 2.8,            # 3倍
    "4bei": 4.0,            # 4倍
    "renchengxiang4bei": 4.0,  # 热成像4倍
    "6bei": 5.76,           # 6倍
    "8bei": 5.76,           # 8倍 (Lua无8倍定义，使用6倍值)
    "15bei": 5.76,          # 15倍 (Lua无15倍定义，使用6倍值)
}

# data.txt 中 A 位(镜组)对应的 Python 识别结果
# A=1 → 机瞄/红点/全息 (scope_factor 从 scope_map 查)
# A=2 → 2倍及以上 (scope_factor 从 scope_map 查)
# 运行时：识别到的倍镜名 → scope_map[倍镜名] 得到 scope_factor

# 姿态系数（来自 Lua 脚本的 dra 和 zhan 处理）
# Lua: 蹲下(zhan==97) → dra=0.7; 趴下(zhan==0) → ratio_zong=0.8
POSTURE_MAP = {
    "none": 1.0,    # 站立
    "c": 0.7,       # 蹲下 (Lua: dra=0.7 when zhan==97)
    "z": 0.8,       # 趴下 (Lua: ratio_zong=0.8 when zhan==0)
}

# 半自动武器（需要逐发点击）
SEMI_AUTO_WEAPONS = {"MINI", "SKS", "MK12", "QBU", "MK47", "DELA", "ZIDONG", "VSS"}

# 武器 RPM
WEAPON_RPM = {
    "ACE32": 600, "AKM": 600, "AUG": 700, "FAMAS": 750,
    "G36C": 700, "Groza": 750, "K2": 700, "M416": 700,
    "M762": 680, "MK47": 600, "QBZ": 700, "SCARL": 700,
    "MINI": 700, "MK12": 750, "MK14": 625, "SKS": 625,
    "QBU": 700, "DELA": 700,
    "BIZON": 750, "JS9": 750, "MP5K": 900, "MP9": 900,
    "P90": 900, "UMP45": 650, "UZI": 1000, "Vector": 1050,
    "DP28": 550, "M249": 750, "MG3": 990,
    "VSS": 700, "Thompson": 600, "ZIDONG": 700,
}

# 武器弹匣容量
WEAPON_MAGAZINE = {
    "ACE32": 30, "AKM": 30, "AUG": 30, "FAMAS": 25,
    "G36C": 30, "Groza": 30, "K2": 30, "M416": 30,
    "M762": 30, "MK47": 30, "QBZ": 30, "SCARL": 30,
    "MINI": 20, "MK12": 20, "MK14": 10, "SKS": 10,
    "QBU": 10, "DELA": 10,
    "BIZON": 53, "JS9": 30, "MP5K": 30, "MP9": 30,
    "P90": 50, "UMP45": 25, "UZI": 25, "Vector": 19,
    "DP28": 47, "M249": 75, "MG3": 75,
    "VSS": 10, "Thompson": 30, "ZIDONG": 10,
}


def parse_data_txt(filepath):
    """解析 data.txt，返回 {WEAPON: {ABCD: {y:[], x:[], d:int, d_sequence:[]}}}
    
    d_sequence 保留每个 tick 的 d 值（支持变 d 值武器如 MK14）。
    过滤 d=-1 的 padding 条目。
    """
    weapons = {}
    with open(filepath, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            eq_pos = line.find("={")
            if eq_pos < 0:
                continue
            key_part = line[:eq_pos]
            data_part = line[eq_pos + 1:]

            # 解析 WEAPON_ABCD
            underscore_pos = key_part.find("_")
            if underscore_pos < 0:
                weapon_name = key_part
                accessories = "1000"
            else:
                weapon_name = key_part[:underscore_pos]
                accessories = key_part[underscore_pos + 1:]

            # 解析 {x=N,y=N,d=N}
            pattern = r'\{x=(-?\d+),y=(-?\d+),d=(-?\d+)\}'
            matches = re.findall(pattern, data_part)
            if not matches:
                continue

            y_values, x_values, d_values = [], [], []
            for mx, my, md in matches:
                x_val, y_val, d_val = int(mx), int(my), int(md)
                if d_val == -1:  # padding，跳过
                    continue
                y_values.append(y_val)
                x_values.append(x_val)
                d_values.append(d_val)

            if not y_values:
                continue

            if weapon_name not in weapons:
                weapons[weapon_name] = {}
            weapons[weapon_name][accessories] = {
                "y": y_values,
                "x": x_values,
                "d_sequence": d_values,
            }
    return weapons


def build_v3_json(weapon_name, weapon_data, existing_json=None):
    """构建 v3 JSON，key 使用 ABCD 4位码（与 data.txt/Lua 脚本完全一致）。"""
    python_name = WEAPON_NAME_MAP.get(weapon_name, weapon_name.lower())
    rpm = WEAPON_RPM.get(weapon_name, 600)
    magazine = WEAPON_MAGAZINE.get(weapon_name, 30)
    is_semi_auto = weapon_name in SEMI_AUTO_WEAPONS
    gun_ratio = GUN_RATIO.get(weapon_name, 1.0)

    # 使用 Lua 脚本的姿态系数（不从 v2 JSON 继承）
    posture = POSTURE_MAP.copy()

    # 构建 recoil 数据，key = ABCD（直接使用 data.txt 的编码）
    recoil = {}
    for abcd, data in weapon_data.items():
        # 验证 ABCD 格式
        if len(abcd) != 4:
            continue
        recoil[abcd] = {
            "y": data["y"],
            "x": data["x"],
        }

    # 确定 tick_ms：取所有 d_sequence 中出现最多的 d 值（主射击间隔）
    all_d = []
    for data in weapon_data.values():
        all_d.extend(data["d_sequence"])
    tick_ms = Counter(all_d).most_common(1)[0][0] if all_d else 28

    # 检查是否有变 d 值（如 MK14: 先 d=3 后 d=24）
    has_variable_d = False
    for data in weapon_data.values():
        d_set = set(data["d_sequence"])
        if len(d_set) > 1:
            has_variable_d = True
            break

    v3_json = {
        "version": 3,
        "weapon": python_name,
        "rpm": rpm,
        "magazine": magazine,
        "semi_auto": is_semi_auto,
        "gun_ratio": gun_ratio,
        "tick_ms": tick_ms,
        "has_variable_d": has_variable_d,
        "scope_map": SCOPE_MAP,
        "posture": posture,
        "recoil": recoil,
    }

    # 如果有变 d 值，保存 d_sequence 到每个 recoil 条目中
    if has_variable_d:
        for abcd in recoil:
            recoil[abcd]["d_sequence"] = weapon_data[abcd]["d_sequence"]

    return v3_json


def load_existing_json(weapon_name):
    """加载现有 v2 JSON（继承 posture 等元信息）。"""
    python_name = WEAPON_NAME_MAP.get(weapon_name, weapon_name.lower())
    json_path = os.path.join(GUNDATA_DIR, f"{python_name}.json")
    if not os.path.exists(json_path):
        return None
    try:
        with open(json_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def backup_gundata():
    """备份现有 GunData 目录。"""
    if os.path.exists(GUNDATA_BACKUP_DIR):
        print(f"  备份目录已存在: {GUNDATA_BACKUP_DIR}")
        return
    if not os.path.exists(GUNDATA_DIR):
        return
    shutil.copytree(GUNDATA_DIR, GUNDATA_BACKUP_DIR)
    print(f"  已备份 {GUNDATA_DIR} -> {GUNDATA_BACKUP_DIR}")


def main():
    print("=" * 60)
    print("data.txt -> v3 GunData JSON 完整迁移工具")
    print("  - key 使用 ABCD 4位码（与 Lua 脚本完全一致）")
    print("  - 数据为 per-tick（来自 data.txt）")
    print("  - 每把枪有独立 gun_ratio（来自 Lua 脚本）")
    print("  - 倍镜系数使用 scope_map（来自 Lua 脚本 ratiobj）")
    print("  - 姿态系数使用 posture_map（来自 Lua 脚本 dra/zhan）")
    print("  - 压枪公式: ymove = ceil(gun_ratio * scope_factor * posture_factor * y)")
    print("=" * 60)

    # 1. 解析 data.txt
    print("\n[1/4] 解析 data.txt ...")
    if not os.path.exists(DATA_TXT_PATH):
        print(f"  错误：找不到 {DATA_TXT_PATH}")
        return
    weapons = parse_data_txt(DATA_TXT_PATH)
    print(f"  解析完成：{len(weapons)} 种武器")
    for wname, combos in sorted(weapons.items()):
        print(f"    {wname}: {len(combos)} 种配件组合, gun_ratio={GUN_RATIO.get(wname, 1.0)}")

    # 2. 备份
    print("\n[2/4] 备份现有 GunData ...")
    backup_gundata()

    # 3. 生成 v3 JSON
    print("\n[3/4] 生成 v3 GunData JSON ...")
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    generated = 0

    for weapon_name in sorted(weapons.keys()):
        weapon_data = weapons[weapon_name]
        existing = load_existing_json(weapon_name)
        v3 = build_v3_json(weapon_name, weapon_data, existing)

        python_name = v3["weapon"]
        output_path = os.path.join(OUTPUT_DIR, f"{python_name}.json")
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(v3, f, ensure_ascii=False, indent=4)

        recoil_count = len(v3["recoil"])
        sample_key = list(v3["recoil"].keys())[0] if recoil_count > 0 else "N/A"
        sample_len = len(v3["recoil"][sample_key]["y"]) if recoil_count > 0 else 0
        print(f"    {python_name}: {recoil_count} 配件组合, "
              f"tick_ms={v3['tick_ms']}, rpm={v3['rpm']}, "
              f"gun_ratio={v3['gun_ratio']}, "
              f"示例key={sample_key}, {sample_len}ticks"
              f"{' [变d值]' if v3['has_variable_d'] else ''}")
        generated += 1

    # 4. 保留 data.txt 中没有的武器（不覆盖）
    print("\n[4/4] 检查遗漏武器 ...")
    existing_files = set(os.listdir(GUNDATA_BACKUP_DIR)) if os.path.exists(GUNDATA_BACKUP_DIR) else set()
    data_txt_weapons = set(WEAPON_NAME_MAP.get(w, w.lower()) + ".json" for w in weapons.keys())
    for fname in existing_files:
        if fname.endswith(".json") and fname not in data_txt_weapons and not os.path.exists(
                os.path.join(OUTPUT_DIR, fname)):
            src = os.path.join(GUNDATA_BACKUP_DIR, fname)
            dst = os.path.join(OUTPUT_DIR, fname)
            shutil.copy2(src, dst)
            print(f"    保留旧数据: {fname}")

    print(f"\n{'=' * 60}")
    print(f"迁移完成！生成 {generated} 个 v3 JSON 文件")
    print(f"  输出: {OUTPUT_DIR}/")
    print(f"  备份: {GUNDATA_BACKUP_DIR}/")
    print(f"\nv3 变更摘要:")
    print(f"  1. recoil key 改为 ABCD 4位码（含镜组 A 位）")
    print(f"  2. y/x 数组为 per-tick（来自 data.txt）")
    print(f"  3. 每把枪有独立 gun_ratio（来自 Lua 脚本）")
    print(f"  4. 倍镜系数 scope_map（来自 Lua 脚本 ratiobj）")
    print(f"  5. 姿态系数 posture（来自 Lua 脚本 dra/zhan）")
    print(f"  6. 压枪公式: ymove = ceil(gun_ratio * scope_factor * posture_factor * y)")
    print(f"  7. 支持变 d 值武器（如 MK14）")
    print(f"  8. 需更新 data/fire_data.py 和 core/process.py")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    main()
