import asyncio
import logging
import simplejson as json
import os
import sys
import threading
import time

import numpy as np
from core.ghub import ghub_device
from core.paths import res_path
from core.recognition import capture_all_positions_thread, recogniseif_firearm
from data.fire_data import KEY_DATA_V3, SCOPE_FACTOR

logger = logging.getLogger(__name__)

DEFAULT_CONFIG = {
    "resolution": "1920x1080",
    "sensitivity": {"none": 1, "hongdian": 1, "quanxi": 2, "2bei": 1.7,
                     "3bei": 5.5, "4bei": 11.5, "6bei": 5, "8bei": 5.7,
                     "15bei": 10, "shift": 1.5},
    "scope_factor_v3": {},
    "posture_v3": {},
    "gun_ratio_v3": {},
}

class ProcessClass:
    _instance_lock = threading.Lock()
    _Result1 = {}  # 1号枪的识别结果[]
    _Result2 = {}  # 2号枪的识别结果
    _gd = ghub_device()

    @classmethod
    def get_recognition_results(cls):
        return cls._Result1, cls._Result2

    def __new__(cls, *args, **kwargs):
        if not hasattr(ProcessClass, "_instance"):
            with ProcessClass._instance_lock:
                if not hasattr(ProcessClass, "_instance"):
                    # 类加括号就回去执行__new__方法，__new__方法会创建一个类实例：Singleton()
                    ProcessClass._instance = object.__new__(cls)  # 继承object类的__new__方法，类去调用方法，说明是函数，要手动传cls
        return ProcessClass._instance  # obj1

    def __init__(self):
        self.TabKey = False
        self.ghub_device_info = self._gd.info
        self.window_version = self.get_window_version()
        self.Monitor = self.get_config_data("r")
        self.mouse_one = False  # 是否开枪
        self.Current_firearms = None  # 当前枪械 1号枪2号枪
        self.Current_posture = "None"  # 当前姿态 None 站立 z 趴下 c 蹲下
        self.sensitivity = 1  # 瞄准灵敏度
        self.StartFire = False  # 是否开枪倍镜
        self.RightClick = True  # 右键按下模式 False 单击 True 长按
        self.clicking = False
        self.firstPerson = False # 是否第一人称
        self.shift_pressed = False  # 记录 Shift 键是否按下
        self.ScopeData = self.get_config_data('s')
        self.ScopeFactorV3 = self.get_config_data('sf3')  # v3 倍镜系数
        self.PostureV3 = self.get_config_data('p3')  # v3 姿态系数
        self.GunRatioV3 = self.get_config_data('gr3')  # v3 独立压枪系数
        self.GunsName = None
        self.added = False
        self.recoil_version = 3
        # 全局压枪系数（对应Lua的all_ratio）
        # 默认1.0，3号位武器时降为0.9
        self.all_ratio = 1.0

    def move_mouse(self, x, y):
        self._gd.mouse_R(x, y)

    def _config_path(self):
        return res_path('Config', 'config.json')

    def get_config_data(self, mode='r'):
        config_path = self._config_path()
        try:
            with open(config_path, "r", encoding='utf-8') as f:
                Config_data = json.loads(f.read())
        except (FileNotFoundError, json.JSONDecodeError) as e:
            logger.warning("配置文件读取失败，使用默认配置: %s", e)
            Config_data = DEFAULT_CONFIG.copy()
            os.makedirs(os.path.dirname(config_path), exist_ok=True)
            with open(config_path, "w", encoding='utf-8') as f:
                f.write(json.dumps(Config_data, ensure_ascii=False, indent=2))

        if mode == 'r':
            return Config_data.get("resolution", "1920x1080")
        elif mode == 's':
            return Config_data.get('sensitivity', DEFAULT_CONFIG['sensitivity'])
        elif mode == 'sf3':
            return Config_data.get('scope_factor_v3', {})
        elif mode == 'p3':
            return Config_data.get('posture_v3', {})
        elif mode == 'gr3':
            return Config_data.get('gun_ratio_v3', {})
        elif mode == 'a':
            return Config_data

    def save_config_data(self, mode, data):
        save_data = self.get_config_data('a')
        if mode == 'resolution':
            save_data['resolution'] = data
        elif mode == 'sensitivity':
            save_data['sensitivity'] = data
        elif mode == 'scope_factor_v3':
            save_data['scope_factor_v3'] = data
        elif mode == 'posture_v3':
            save_data['posture_v3'] = data
        elif mode == 'gun_ratio_v3':
            save_data['gun_ratio_v3'] = data
        try:
            with open(self._config_path(), "w", encoding='utf-8') as f:
                f.write(json.dumps(save_data, ensure_ascii=False, indent=2))
        except Exception as e:
            logger.error("保存配置失败: %s", e)

    def reduction_data(self):
        self.StartFire = False
        self.clicking = False
        self.sensitivity = 1
        self.Current_posture = "None"
        self.Current_firearms = None
        self.mouse_one = False
        self.TabKey = False
        self._Result1 = {}
        self._Result2 = {}

    def read_gun_data(self, fileName) -> dict:
        """读取 v3 枪械数据 JSON（_internal/GunData）。"""
        path = res_path('_internal', 'GunData', f'{fileName}.json')
        if not os.path.exists(path):
            return None
        with open(path, "r", encoding='utf-8') as f:
            return json.loads(f.read())

    def get_current_scope(self):
        result = self.get_guns_info()
        if result is None:
            return "none"
        else:
            return result["Scope"]

    def shift_multiplier(self):
        # 读取配置文件中的 shift 变量

        shift_scpoe = float(self.ScopeData.get('shift', 0))
        # 判断 Shift 键是否按下
        if self.shift_pressed and shift_scpoe:
            # 增加长按shift的倍率
            if self.Current_firearms and self.StartFire:
                if not self.added:
                    # 判断当前是否装备了枪械并且正在开镜
                    accessor_scope = self.get_current_scope()
                    if accessor_scope == 'hongdian':  # 如果当前是红点
                        self.ScopeData['hongdian'] += shift_scpoe  # 增加红点倍率
                    elif accessor_scope == 'quanxi':  # 如果当前是全息
                        self.ScopeData['quanxi'] += shift_scpoe  # 增加全息镜倍率
                    elif accessor_scope == 'none':  # 如果当前是机瞄
                        self.ScopeData['none'] += shift_scpoe  # 增加机瞄倍率
                    self.added=True

    def on_shift_pressed(self):
        self.shift_pressed = True
        self.shift_multiplier()

    def on_shift_released(self):
        self.shift_pressed = False
        sensitivity_data = self.get_config_data('s')
        self.ScopeData = sensitivity_data
        self.added=False
    def get_window_version(self):
        if not hasattr(sys, 'getwindowsversion'):
            return False
        windows_version = sys.getwindowsversion()
        if windows_version.build >= 22000:
            return True
        return False

    def get_guns_result(self):
        """
        获取枪械识别结果
        :return:
        """
        return [self._Result1, self._Result2]

    def recognize_all_guns_info(self, Emit):
        """
        枪械配件识别
        :return:
        """
        Data = asyncio.run(capture_all_positions_thread(self.Monitor))
        self._Result1 = Data[0]
        self._Result2 = Data[1]
        Emit('g', (None,))

    def Change_firearms(self, keyWord):
        """
        枪械切换
        :param keyWord:按键编码
        :return:
        """
        if keyWord == "x":
            self.Current_firearms = None
            self.all_ratio = 1.0  # 无武器时恢复默认
        else:
            self.Current_firearms = int(keyWord)
            # Lua: 3号位武器(wbflag=='3')时 all_ratio=0.9
            # 对应 Python 中 Current_firearms==3 (手枪位)
            self.all_ratio = 0.9 if self.Current_firearms == 3 else 1.0

    def IF_Open_Lens(self):
        self.StartFire = recogniseif_firearm(self.Monitor)

    def Change_posture(self, keyWord):
        """
        姿势切换
        :param keyWord:按键编码
        :return:
        """
        if keyWord == "space" or self.Current_posture == keyWord:
            self.Current_posture = "None"
        else:
            self.Current_posture = keyWord

    def calculate_the_recoil(self, recoil, posture, scope):
        """
        计算本 tick 应下发的垂直鼠标移动量（与 GunData 单元素含义一致）。

        合成公式: ``posture * (recoil * scope)``，乘法结合顺序与 ``recoil * scope * posture`` 等价。

        - ``recoil``: GunData 数组中当前 tick 的基准补偿值（无单位系数，相对表）。
        - ``scope``: 来自 ``ScopeData`` 的倍镜/机瞄灵敏度倍率；放大倍率越高，同等 ``recoil`` 需要更大的鼠标下移量。
        - ``posture``: 枪械 JSON 中站姿/蹲/趴等姿态系数；不同姿态后坐力表现不同，与 ``recoil`` 相乘体现姿态对补偿的缩放。

        三者相乘得到「本 tick 理论像素/驱动单位位移」，再 ``int(round(...))`` 取整为整数。
        """
        recoil_value = posture * (recoil * scope)
        return int(round(recoil_value))  # 返回整数

    def get_guns_info(self):
        if self.Current_firearms == 1:
            return self._Result1
        elif self.Current_firearms == 2:
            return self._Result2
        else:
            return None

    def FIRE_Start(self, Emit):
        """
        压枪宏入口 (v3)：校验状态 → 读枪 JSON → ``_fire_start_v3`` / ``FIRE_v3``。

        不在此函数内做识别；识别由其他线程/回调更新 ``_Result*``、``StartFire`` 等状态。
        """
        # 判断数据是否准确
        Judge_List = (self.StartFire, self.Current_firearms, self._Result1, self._Result2)
        LogInfo_List = ("当前没有开启倍镜，无需压枪", "当前没有装备枪械，无需压枪", "还未进行枪械识别，无需压枪",
                        "还未进行枪械识别，无需压枪")
        for i in range(len(Judge_List)):
            if not Judge_List[i]:
                return Emit("l", (LogInfo_List[i],))

        # 获取当前枪械识别情况数据
        guns_info = self.get_guns_info()
        if not guns_info:
            return Emit("l", ("当前装备不是枪械，无需压枪",))
        # 获取枪械名称
        gunsName = guns_info.get("Name", "None")
        if gunsName == "None" or not gunsName:
            return Emit("l", ("未检测到枪械",))
        # 获取枪械数据 枪械对应json数据
        gun = self.read_gun_data(gunsName)
        if not gun:
            return Emit("l", ("枪械数据不存在",))

        return self._fire_start_v3(gun, guns_info, Emit)

    def get_accessories_nameCode_v3(self, guns_info):
        """
        获取配件编码 (v3 格式: ABCD 4位码，含镜组)
        与 Lua 脚本 / data.txt 的编码完全一致:
          A=镜组(1=低倍镜,2=高倍镜), B=枪口, C=握把, D=枪托
        :param guns_info:识别枪械的数据
        :return: ABCD 4位字符串，如 "1231"
        """
        scope_name = guns_info.get("Scope", "None").lower()
        a_code = KEY_DATA_V3["Scope"].get(scope_name, "1")

        muzzle_name = guns_info.get("Muzzle", "None").lower()
        b_code = KEY_DATA_V3["Muzzle"].get(muzzle_name, "0")

        grip_name = guns_info.get("Grip", "None").lower()
        c_code = KEY_DATA_V3["Grip"].get(grip_name, "0")

        stock_name = guns_info.get("Stock", "None").lower()
        d_code = KEY_DATA_V3["Stock"].get(stock_name, "0")

        return a_code + b_code + c_code + d_code

    def Computation_latency(self, latency):
        if self.window_version:
            return (latency - 0) / 1000
        return latency / 1000

    # ═══════════════════════════════════════════
    # v3 开火路径：per-tick 直接下发 + ABCD key + Lua 公式
    # 完全对齐 Lua 脚本的压枪体系
    # ═══════════════════════════════════════════

    def _fire_start_v3(self, gun, guns_info, Emit):
        """v3 格式入口：使用 ABCD 4位码查找弹道数据，调用 FIRE_v3。

        v3 与 v2 的核心区别:
        - key 使用 ABCD 4位码（含镜组 A 位），与 data.txt/Lua 脚本一致
        - 每把枪有独立 gun_ratio（来自 Lua 脚本的 xxx_ratio）
        - scope 使用 scope_map（来自 Lua 脚本的 ratiobj），不再依赖 config.json
        - 姿态系数来自 Lua 脚本（蹲=0.7, 趴=0.8）
        - 公式: ymove = ceil(gun_ratio * scope_factor * posture_factor * y)
        """
        abcd_code = self.get_accessories_nameCode_v3(guns_info)
        recoil_data = gun.get("recoil", {}).get(abcd_code)

        # 降级匹配：先尝试去掉枪托(D→0)，再尝试裸枪(B0C0D0)
        if not recoil_data:
            fallback1 = abcd_code[:3] + "0"  # ABC0
            recoil_data = gun.get("recoil", {}).get(fallback1)
            if recoil_data:
                Emit("l", (f"配件 {abcd_code} 无精确弹道，降级使用 {fallback1}",))

        if not recoil_data:
            fallback2 = abcd_code[0] + "000"  # A000 裸枪
            recoil_data = gun.get("recoil", {}).get(fallback2)
            if recoil_data:
                Emit("l", (f"配件 {abcd_code} 无弹道数据，降级使用裸枪 {fallback2}",))

        # A=2 降级 A=1：如果高倍镜没有数据，用低倍镜的
        if not recoil_data and abcd_code[0] == "2":
            fallback3 = "1" + abcd_code[1:]
            recoil_data = gun.get("recoil", {}).get(fallback3)
            if recoil_data:
                Emit("l", (f"配件 {abcd_code} 无高倍镜数据，降级使用低倍镜 {fallback3}",))

        if not recoil_data:
            return Emit("l", (f"配件组合 {abcd_code} 无弹道数据",))

        y_array = recoil_data.get("y", [])
        x_array = recoil_data.get("x", [])
        d_sequence = recoil_data.get("d_sequence")
        if not y_array:
            return Emit("l", ("弹道数据为空",))

        # gun_ratio: 独立压枪系数
        # 优先使用 config.json 的 gun_ratio_v3（用户可在UI调整），
        # 否则使用 JSON 内的 gun_ratio（Lua 默认值）
        weapon_name = gun.get("weapon", "")
        if self.GunRatioV3 and weapon_name in self.GunRatioV3:
            gun_ratio = self.GunRatioV3[weapon_name]
        else:
            gun_ratio = gun.get("gun_ratio", 1.0)

        # scope_factor: 倍镜系数
        # 优先使用 config.json 的 scope_factor_v3（用户可在UI调整），
        # 否则使用 JSON 内的 scope_map（Lua 默认值），最后回退到 SCOPE_FACTOR
        scope_name = guns_info.get("Scope", "None").lower()
        if self.ScopeFactorV3 and scope_name in self.ScopeFactorV3:
            scope_factor = self.ScopeFactorV3[scope_name]
        else:
            scope_factor = gun.get("scope_map", SCOPE_FACTOR).get(scope_name, 1.0)

        # posture_factor: 姿态系数
        # 优先使用 config.json 的 posture_v3（用户可在UI调整），
        # 否则使用 JSON 内的 posture（Lua 默认值）
        posture_key = self.Current_posture.lower()
        if self.PostureV3 and posture_key in self.PostureV3:
            posture_factor = self.PostureV3[posture_key]
        else:
            posture_factor = gun.get("posture", {}).get(posture_key, 1.0)

        # tick_ms 和 has_variable_d
        tick_ms = gun.get("tick_ms", 28)
        has_variable_d = gun.get("has_variable_d", False)

        # 趴下判断：Lua 中趴下时 ratio_zong=0.8 是固定值，不含 gun_ratio 和 ratiobj
        # Current_posture: "None"=站立, "c"=蹲下, "z"=趴下
        prone = (posture_key == "z")

        return self.FIRE_v3(gun_ratio, scope_factor, posture_factor,
                            y_array, x_array, tick_ms, has_variable_d, d_sequence, Emit, prone,
                            self.all_ratio)

    def FIRE_v3(self, gun_ratio, scope_factor, posture_factor,
                y_array, x_array, tick_ms, has_variable_d=False,
                d_sequence=None, Emit=None, prone=False, all_ratio=1.0):
        """
        v3 压枪核心：per-tick 直接下发，完全对齐 Lua 脚本。

        Lua 压枪公式 (站立/蹲下):
          ratio_zong = lj * all_ratio * GunRatio[noweapon] * ratiobj * dra
          ymove = math.ceil(ditu * ratio_zong * data.y)
          简化后（ditu=1, lj=1, all_ratio=1）:
          ymove = ceil(gun_ratio * scope_factor * dra * y)

        Lua 压枪公式 (趴下):
          ratio_zong = 0.8  ← 固定值！不含 GunRatio、ratiobj、dra
          ymove = math.ceil(ditu * 0.8 * data.y)

        与 Lua 的精确对齐:
        - 无 remainder 累积（Lua 每 tick 独立 ceil，不做亚像素追踪）
        - 趴下时 ratio_zong=0.8 是固定值（不含 gun_ratio 和 scope_factor）
        - 取整统一使用 math.ceil（与 Lua 一致）
        - 水平补偿：纯随机 -1~1（Lua 模式2 不使用 data.x）
        - 支持变 d 值武器（如 MK14: 前7 tick d=3, 后续 d=24）
        """
        import math
        import random

        recoil_list = []

        for i in range(len(y_array)):
            if not self.mouse_one:
                break
            Emit('x', (True,))

            # ── 垂直补偿 ──
            # 趴下特殊处理：Lua 中趴下时 ratio_zong=0.8 是固定值
            # 不含 GunRatio、ratiobj（scope_factor），与站立/蹲下完全不同
            if prone:
                # Lua: if zhan==0 then ratio_zong = 0.8 end
                # ymove = ceil(ditu * 0.8 * data.y)
                y_move = math.ceil(0.8 * y_array[i])
            else:
                # Lua: ratio_zong = lj * all_ratio * GunRatio * ratiobj * dra
                # ymove = ceil(ditu * ratio_zong * data.y)
                # 无 remainder 累积！Lua 每 tick 独立 ceil
                y_move = math.ceil(all_ratio * gun_ratio * scope_factor * posture_factor * y_array[i])

            # ── 水平补偿 ──
            # Lua 模式2: MoveMouseRelative(math.random(-1,1), ymove)
            # data.txt 中的 x 数据在 Lua 压枪时被忽略，只用纯随机偏移
            x_move = random.randint(-1, 1)

            self._gd.mouse_R(x_move, y_move)
            recoil_list.append(y_move)

            # ── 延时 ──
            # Lua: 绝对时间同步 Sleep3(timestart)，Python 只能用相对 sleep
            if has_variable_d and d_sequence and i < len(d_sequence):
                latency = self.Computation_latency(d_sequence[i])
            else:
                latency = self.Computation_latency(tick_ms)
            time.sleep(latency)

        Emit('x', (False,))
        return recoil_list

