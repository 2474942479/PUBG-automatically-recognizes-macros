ACCESSORIES_CH = {
    "Name": {
        "none": "未知",
        "zidongzhuangtianbuqiang": "自动装填步枪",
        "tangmuxunchongfengqiang": "汤姆逊冲锋枪",
        "paijipao": '迫击炮',
        "delagongnuofu": "德拉贡诺夫",
        "moxinnaganbuqiang": "莫辛纳甘步枪",
        "shizilv": "十字弩",
        "micro_uzi": "uzi",
        "mosin_nagant": "莫辛纳甘步枪",
        "Tommy_gun": "汤姆逊冲锋枪"
    },
    "Muzzle": {
        "zhituiqi": "制退器",
        "eliuquan": "扼流圈",
        "yazuiqiangkou": "鸭嘴枪口",
        "jujiqiangbuchang": "狙击枪补偿",
        "jujiqiangxiaoyan": "狙击枪消焰",
        "buqiangbuchang": "步枪补偿",
        "buqiangxiaoyan": "步枪消焰",
        "chongfengqiangxiaoyan": "冲锋枪消焰",
        "chongfengqiangbuchang": "冲锋枪补偿",
        "xiaoyin": "消音器",
        "none": "未知"
    },
    "Scope": {
        "none": "未知",
        "hongdian": "红点",
        "quanxi": "全息",
        "2bei": "2倍",
        "3bei": "3倍",
        "4bei": "4倍",
        "renchengxiang4bei": "热成像4倍",
        "duobei1": "多倍镜(低倍)",
        "duobei4": "多倍镜(高倍)",
        "6bei": "6倍",
        "8bei": "8倍",
        "15bei": "15倍"
    },
    "Grip": {
        "none": "未知",
        "banjieshi": "半截式握把",
        "muzhi": "拇指握把",
        "zhijiao": "直角握把",
        "chuizhi": "垂直握把",
        "xiexiang" : "斜向握把"
    },
    "Stock": {
        "none": "未知",
        "zhanshuqiangtuo": "战术枪托",
        "zhongxinqiangtuo": "重型枪托",
        "tuosaiban": "托腮板",
        "zidandai": "子弹袋",
        "zhedieshiqiangtuo": "折叠式枪托"
    }
}

# ═══════════════════════════════════════════════════════════
# v3 格式配件编码（ABCD 4位码，含镜组）
#   来自 Lua 脚本和 data.txt 的编码规则：
#   A(千位)=镜组: 1=机瞄/红点/全息, 2=2倍镜及以上
#   B(百位)=枪口: 0=无, 1=补偿器, 2=消焰器, 3=消音器, 4=制退器(扼流圈/鸭嘴/制退器)
#   C(十位)=握把: 0=无, 1=垂直, 2=直角, 3=半截式, 4=拇指
#   D(个位)=枪托: 0=无, 1=战术枪托/托腮板, 2=子弹袋
#
#   注意：Lua 脚本中的编码与 v2 的 A*B*C* 完全不同！
#   - v2 区分步枪/冲锋枪/狙击枪的具体枪口（5种补偿器编号不同）
#   - v3(Lua) 只按功能分类（所有补偿器都是 B=1）
# ═══════════════════════════════════════════════════════════
KEY_DATA_V3 = {
    "Scope": {
        # A 位：1=低倍镜(机瞄/红点/全息), 2=高倍镜(2倍及以上)
        "none": "1",                # 机瞄 → A=1
        "hongdian": "1",            # 红点   → A=1
        "quanxi": "1",              # 全息   → A=1
        "duobei1":"1",              # 多倍镜(红点) → A=1
        "duobei4":"2",              # 多倍镜(高倍) → A=2
        "2bei": "2",                # 2倍    → A=2
        "3bei": "2",                # 3倍    → A=2
        "4bei": "2",                # 4倍    → A=2
        "renchengxiang4bei": "2",   # 热成像4倍 → A=2
        "6bei": "2",                # 6倍    → A=2
        "8bei": "2",                # 8倍    → A=2
        "15bei": "2",               # 15倍   → A=2
    },
    "Muzzle": {
        # B 位：0=无, 1=补偿器, 2=消焰器, 3=消音器, 4=制退器(扼流圈/鸭嘴)
        # Lua 脚本不区分武器类型的枪口变种，只按功能大类
        "none": "0",
        "buqiangbuchang": "1",          # 步枪补偿 → B=1(补偿器)
        "chongfengqiangbuchang": "1",   # 冲锋枪补偿 → B=1(补偿器)
        "jujiqiangbuchang": "1",        # 狙击补偿 → B=1(补偿器)
        "buqiangxiaoyan": "2",          # 步枪消焰 → B=2(消焰器)
        "chongfengqiangxiaoyan": "2",   # 冲锋枪消焰 → B=2(消焰器)
        "jujiqiangxiaoyan": "2",        # 狙击消焰 → B=2(消焰器)
        "xiaoyin": "3",                 # 消音器   → B=3(消音器)
        "zhituiqi": "4",                # 制退器   → B=4(制退器)
        "eliuquan": "4",                # 扼流圈   → B=4(制退器)
        "yazuiqiangkou": "4",           # 鸭嘴枪口 → B=4(制退器)
    },
    "Grip": {
        # C 位：0=无, 1=垂直, 2=直角, 3=半截式, 4=拇指, 5=斜向
        # 注意：与 v2 的握把编码不同！v2: 1=半截式,2=拇指,3=直角,4=垂直
        "none": "0",
        "chuizhi": "1",         # 垂直握把 → C=1
        "zhijiao": "2",         # 直角握把 → C=2
        "banjieshi": "3",       # 半截式握把 → C=3
        "muzhi": "4",           # 拇指握把 → C=4
        "xiexiang": "5",        # 斜向握把 → C=5 (参考直角握把数据)
    },
    "Stock": {
        # D 位：0=无, 1=战术枪托/托腮板, 2=子弹袋
        "none": "0",
        "zhanshuqiangtuo": "1",     # 战术枪托 → D=1
        "zhongxinqiangtuo": "1",    # 重型枪托 → D=1 (Lua中归为同一类)
        "tuosaiban": "1",           # 托腮板   → D=1 (Lua: 战术枪托/托腮板)
        "zhedieshiqiangtuo": "1",   # 折叠式枪托 → D=1
        "zidandai": "2",            # 子弹袋   → D=2
    }
}

# ═══════════════════════════════════════════════════════════
# 倍镜灵敏度系数（来自 Lua 脚本的 ratiobj 计算）
# 与 v2 config.json 中的 sensitivity 不同！
# Lua 公式: ratiobj = 倍镜倍数 × 经验系数
# ═══════════════════════════════════════════════════════════
SCOPE_FACTOR = {
    "none": 1.0,            # 机瞄
    "hongdian": 1.0,        # 红点
    "quanxi": 1.0,          # 全息
    "duobei1": 1.0,         # 多倍镜(低倍模式/红点)
    "2bei": 1.76,           # 2倍: 2 × 0.88
    "3bei": 2.8,            # 3倍: 3 × 0.93
    "4bei": 4.0,            # 4倍: 4 × 1.0
    "renchengxiang4bei": 4.0,  # 热成像4倍
    "duobei4": 4.0,         # 多倍镜(高倍模式/4倍)
    "6bei": 5.76,           # 6倍: 6 × 0.96
    "8bei": 5.76,           # 8倍: 无Lua定义，使用6倍值
    "15bei": 5.76,          # 15倍: 无Lua定义，使用6倍值
}

# ═══════════════════════════════════════════════════════════
# 倍镜名 → data.txt A 位编码
# ═══════════════════════════════════════════════════════════
SCOPE_TO_A_CODE = KEY_DATA_V3["Scope"]

# ═══════════════════════════════════════════════════════════
# 枪械-配件限制映射（完整版）
#   槽位级：每把枪支持的配件槽位 (Scope 全部支持，已省略)
#   类型级：枪口/握把/枪托的模板限制
#   未列入的枪械默认检测所有配件槽位
# ═══════════════════════════════════════════════════════════

# 枪口模板分类（步枪/冲锋枪/狙击枪）
MUZZLE_RIFLE = {"buqiangbuchang", "buqiangxiaoyan", "xiaoyin"}
MUZZLE_SMG = {"chongfengqiangbuchang", "chongfengqiangxiaoyan", "xiaoyin"}
MUZZLE_SNIPER = {"jujiqiangbuchang", "jujiqiangxiaoyan", "xiaoyin"}

# 握把模板（所有支持握把的枪都相同）
GRIP_ALL = {"chuizhi", "banjieshi", "muzhi", "xiexiang"}

# 枪托模板分类（步枪枪托/狙击枪托/冲锋枪枪托/子弹袋/折叠式）
STOCK_RIFLE = {"zhanshuqiangtuo", "zhongxinqiangtuo"}  # 步枪/冲锋枪通用的战术枪托、重型枪托
STOCK_SNIPER = {"tuosaiban"}  # 狙击枪专用托腮板
STOCK_FOLDING = {"zhedieshiqiangtuo"}  # 折叠式枪托（仅UZI）
STOCK_BULLET_BAG = {"zidandai"}  # 子弹袋（仅S1897、98K）

# 枪械配件支持表（完整版）
# 格式: gun_name -> {
#   "slots": {支持的槽位},
#   "muzzle": 枪口模板集合或None,
#   "grip": 握把模板集合或None,
#   "stock": 枪托模板集合或None,
# }
# slots 不含 Scope（所有枪械均支持 Scope）
# None 表示不限制该配件类型（使用目录下的所有模板）
# 未列入的枪械 → 默认检测所有配件槽位和所有模板（向后兼容）
GUN_ACCESSORIES = {
    # === 突击步枪 AR ===
    "m416":   {"slots": {"Muzzle", "Grip", "Stock"},  "muzzle": MUZZLE_RIFLE,  "grip": GRIP_ALL,   "stock": STOCK_RIFLE},
    "akm":    {"slots": {"Muzzle"},                   "muzzle": MUZZLE_RIFLE,  "grip": None,       "stock": None},
    "m762":   {"slots": {"Muzzle", "Grip"},           "muzzle": MUZZLE_RIFLE,  "grip": GRIP_ALL,   "stock": None},
    "scar-l": {"slots": {"Muzzle", "Grip"},           "muzzle": MUZZLE_RIFLE,  "grip": GRIP_ALL,   "stock": None},
    "aug":    {"slots": {"Muzzle", "Grip"},           "muzzle": MUZZLE_RIFLE,  "grip": GRIP_ALL,   "stock": None},
    "qbz":    {"slots": {"Muzzle", "Grip"},           "muzzle": MUZZLE_RIFLE,  "grip": GRIP_ALL,   "stock": None},
    "g36c":   {"slots": {"Muzzle", "Grip"},           "muzzle": MUZZLE_RIFLE,  "grip": GRIP_ALL,   "stock": None},
    "ace32":  {"slots": {"Muzzle", "Grip"},           "muzzle": MUZZLE_RIFLE,  "grip": GRIP_ALL,   "stock": None},
    "k2":     {"slots": {"Muzzle", "Grip"},           "muzzle": MUZZLE_RIFLE,  "grip": GRIP_ALL,   "stock": None},
    "mk47":   {"slots": {"Muzzle", "Grip", "Stock"},  "muzzle": MUZZLE_RIFLE,  "grip": GRIP_ALL,   "stock": STOCK_RIFLE},
    "famas":  {"slots": {"Muzzle"},                   "muzzle": MUZZLE_RIFLE,  "grip": None,       "stock": None},
    "groza":  {"slots": {"Muzzle"},                   "muzzle": MUZZLE_RIFLE,  "grip": None,       "stock": None},
    "m16a4":  {"slots": {"Muzzle", "Stock"},          "muzzle": MUZZLE_RIFLE,  "grip": None,       "stock": STOCK_RIFLE},

    # === 冲锋枪 SMG ===
    "ump45":  {"slots": {"Muzzle", "Grip"},           "muzzle": MUZZLE_SMG,    "grip": GRIP_ALL,   "stock": None},
    "vector": {"slots": {"Muzzle", "Grip", "Stock"},  "muzzle": MUZZLE_SMG,    "grip": GRIP_ALL,   "stock": STOCK_RIFLE},
    "mp5k":   {"slots": {"Muzzle", "Grip", "Stock"},  "muzzle": MUZZLE_SMG,    "grip": GRIP_ALL,   "stock": STOCK_RIFLE},
    "uzi":    {"slots": {"Muzzle", "Stock"},          "muzzle": MUZZLE_SMG,    "grip": None,       "stock": STOCK_FOLDING},
    "pp19":   {"slots": {"Muzzle"},                   "muzzle": MUZZLE_SMG,    "grip": None,       "stock": None},
    "mp9":    {"slots": {"Muzzle"},                   "muzzle": MUZZLE_SMG,    "grip": None,       "stock": None},
    "js9":    {"slots": {"Muzzle", "Grip"},           "muzzle": MUZZLE_SMG,    "grip": GRIP_ALL,   "stock": None},
    "tangmuxunchongfengqiang": {"slots": {"Muzzle", "Grip"},    "muzzle": MUZZLE_SMG,    "grip": GRIP_ALL,   "stock": None},
    "p90":    {"slots": set(),                        "muzzle": None,          "grip": None,       "stock": None},

    # === 射手步枪 DMR ===
    "mini14": {"slots": {"Muzzle"},                   "muzzle": MUZZLE_RIFLE,  "grip": None,       "stock": None},
    "sks":    {"slots": {"Muzzle", "Grip", "Stock"},  "muzzle": MUZZLE_RIFLE,  "grip": GRIP_ALL,   "stock": STOCK_RIFLE},
    "mk12":   {"slots": {"Muzzle", "Grip"},           "muzzle": MUZZLE_RIFLE,  "grip": GRIP_ALL,   "stock": None},
    "mk14":   {"slots": {"Muzzle", "Stock"},          "muzzle": MUZZLE_SNIPER, "grip": None,       "stock": STOCK_SNIPER},
    "qbu":    {"slots": {"Muzzle"},                   "muzzle": MUZZLE_RIFLE,  "grip": None,       "stock": None},
    "vss":    {"slots": {"Stock"},                    "muzzle": None,          "grip": None,       "stock": STOCK_SNIPER},
    "delagongnuofu": {"slots": {"Muzzle", "Stock"},   "muzzle": MUZZLE_SNIPER, "grip": None,       "stock": STOCK_SNIPER},

    # === 轻机枪 LMG ===
    "m249":   {"slots": {"Stock"},                     "muzzle": None,          "grip": None,       "stock": STOCK_RIFLE},
    "dp28":   {"slots": set(),                         "muzzle": None,          "grip": None,       "stock": None},
    "mg3":    {"slots": set(),                         "muzzle": None,          "grip": None,       "stock": None},

    # === 狙击枪 SR ===
    "m24":    {"slots": {"Muzzle", "Stock"},          "muzzle": MUZZLE_SNIPER, "grip": None,       "stock": STOCK_SNIPER},
    "98k":    {"slots": {"Muzzle", "Stock"},          "muzzle": MUZZLE_SNIPER, "grip": None,       "stock": STOCK_SNIPER},
    "kar98k": {"slots": {"Muzzle", "Stock"},          "muzzle": MUZZLE_SNIPER, "grip": None,       "stock": STOCK_SNIPER},
    "awm":    {"slots": {"Muzzle", "Stock"},          "muzzle": MUZZLE_SNIPER, "grip": None,       "stock": STOCK_SNIPER},
    "win94":  {"slots": set(),                         "muzzle": None,          "grip": None,       "stock": None},
    "s1897":  {"slots": {"Stock"},                      "muzzle": None,          "grip": None,       "stock": STOCK_BULLET_BAG},
    "s686":   {"slots": set(),                         "muzzle": None,          "grip": None,       "stock": None},
    "s12k":   {"slots": {"Muzzle", "Grip"},           "muzzle": MUZZLE_RIFLE,  "grip": GRIP_ALL,   "stock": None},
    "dbS":    {"slots": set(),                         "muzzle": None,          "grip": None,       "stock": None},
    "012":    {"slots": set(),                         "muzzle": None,          "grip": None,       "stock": None},
    "amr":    {"slots": {"Muzzle", "Stock"},          "muzzle": MUZZLE_SNIPER, "grip": None,       "stock": STOCK_SNIPER},
    "crossbow": {"slots": set(),                       "muzzle": None,          "grip": None,       "stock": None},

    # === 特殊 ===
    "zidongzhuangtianbuqiang": {"slots": {"Muzzle", "Stock"},        "muzzle": MUZZLE_RIFLE,          "grip": None,       "stock": STOCK_SNIPER},
}


def get_allowed_slots(gun_name):
    """
    获取枪械支持的配件槽位集合（用于两阶段识别：先识枪名，再裁剪允许的配件）
    :param gun_name: 枪械名称 (如 'm416')
    :return:
        - None: 未知枪械，不限制（识别所有槽位）
        - set: 支持的槽位集合，已自动包含 'Scope'（所有枪都支持）
    """
    if not gun_name or gun_name.lower() == "none":
        return None  # 未知枪械，不限制
    gun_info = GUN_ACCESSORIES.get(gun_name.lower())
    if not gun_info:
        return None  # 未列入的枪械，不限制（向后兼容）
    # slots 不含 Scope，这里补上
    return gun_info.get("slots", set()) | {"Scope"}


def get_allowed_templates(gun_name, slot_type):
    """
    获取枪械在指定槽位允许的模板名称集合（完整版）
    :param gun_name: 枪械名称 (如 'm416')
    :param slot_type: 槽位类型 ('Scope', 'Muzzle', 'Grip', 'Stock')
    :return: 
        - None: 不限制（使用目录下所有模板）
        - set(): 空集，表示不支持该槽位，直接跳过
        - {模板名...}: 只检测这些模板文件（不含扩展名）
    """
    if not gun_name or gun_name.lower() == "none":
        return None  # 未知枪械，不限制
    
    gun_info = GUN_ACCESSORIES.get(gun_name.lower())
    if not gun_info:
        return None  # 未列入的枪械，不限制（向后兼容）
    
    # Scope 所有枪械都支持，不限制模板类型
    if slot_type == "Scope":
        return None
    
    # 槽位级限制：该枪不支持这个槽位，直接跳过所有模板匹配
    if slot_type not in gun_info.get("slots", set()):
        return set()
    
    # 类型级限制：获取该枪对该配件类型的模板限制（可为 None 表示不限制）
    # 从枪的配置中读取对应 slot_type 的模板集合（小写键名）
    allowed = gun_info.get(slot_type.lower(), None)
    return allowed  # None = 不限制，set() = 指定模板列表
