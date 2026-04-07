import simplejson as json
import os
import sys
import threading
import time
from core.ghub import ghub_device
from core.recognition import capture_all_positions_thread, recogniseif_firearm, capture_zishi_positions_thread
from data.fire_data import KEY_DATA
import asyncio
import numpy as np
from pyopdll import OP

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
        self.GunsName = None
        self.added = False
        self.op = OP()

    def move_mouse(self, x, y):
        self._gd.mouse_R(x, y)

    def get_config_data(self, mode='r'):
        with open('./Config/config.json', "r", encoding='utf-8') as Config:
            Config_data = json.loads(Config.read())
            if mode == 'r':
                return Config_data["resolution"]
            elif mode == 's':
                return Config_data['sensitivity']
            elif mode == 'a':
                return Config_data

    def save_config_data(self, mode, data):
        save_data = self.get_config_data('a')
        if mode:
            save_data['resolution'] = data
        else:
            save_data['sensitivity'] = data
        with open('./Config/config.json', "w", encoding='utf-8') as Config:
            Config.write(json.dumps(save_data))

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
        if not os.path.exists(f'./_internal/GunData/{fileName}.json'):
            return
        with open(f'./_internal/GunData/{fileName}.json', "r", encoding='utf-8') as GUNS:
            GUNS_data = json.loads(GUNS.read())
            return GUNS_data

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
        else:
            self.Current_firearms = int(keyWord)

    def IF_Open_Lens(self):
        self.StartFire = recogniseif_firearm(self.Monitor)

    def recognize_zishi_info(self):
        """
        姿势识别
        :return:
        """

        Data = asyncio.run(capture_zishi_positions_thread(self.Monitor, self.firstPerson))
        self.Current_posture = Data[0].get("zishi", "None")


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
        注意: 最终整数鼠标步长由 ``FIRE`` / ``FIRE1`` 中的 remainder 累加后再 ``int(round)``，此处仅负责单 tick 浮点合成。
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
        压枪宏入口：串联「能否压枪」→「读枪与弹道」→「姿态/倍镜」→「全自动或半自动开火循环」。

        流水线概要:
        1. 前置条件: 已开镜 (``StartFire``)、已选 1/2 号槽 (``Current_firearms``)、两侧槽位识别结果非空；
           否则直接 ``Emit`` 日志并返回，避免无数据空跑。
        2. ``get_guns_info()`` 取当前槽位识别结果 → 枪名 ``gunsName`` → ``read_gun_data`` 加载 ``_internal/GunData/<枪>.json``。
        3. ``get_accessories_nameCode`` 将枪口/握把/枪托映射为 ``A*B*C*`` 码，从 JSON 中取对应弹道列表 ``ballistic``；
           ``Posture``、``Scope`` 分别为当前姿态键与当前镜型的灵敏度倍率。
        4. 若枪属于 ``Not_Guns``（半自动等），走 ``FIRE1``（tick 间隔约 100ms）；否则 ``FIRE``（约 9ms），与游戏内射速档位一致。

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

        # 获取配件码
        NameCode = self.get_accessories_nameCode(guns_info)
        # 获取弹道数据
        ballistic = gun.get(NameCode, [])
        # 获取姿态数据
        Posture = gun.get(self.Current_posture.lower(), 1)
        # 获取倍镜数据
        accessor_scope = guns_info.get("Scope", "None").lower()
        Scope = self.ScopeData.get(accessor_scope, 1)
        # 判断是否为非连点枪械
        Not_Guns = ["sks", "mini14", "delagongnuofu", "m16a4", "mk12", "mk47", "qbu", "zidongzhuangtianbuqiang"]
        if gunsName in Not_Guns:
            return self.FIRE1(Posture, Scope, ballistic, Emit)
        else:
            return self.FIRE(Posture, Scope, ballistic, Emit)

    def get_accessories_nameCode(self, guns_info):
        """
        获取配件名称
        :param guns_info:识别枪械的数据
        :return:
        """
        NameCode = ""
        type_dict = {"Muzzle": "A", "Grip": "B", "Stock": "C"}
        for name, value in type_dict.items():
            accessories = guns_info.get(name, "None").lower()
            code_num = KEY_DATA[name][accessories]
            NameCode += value + code_num
        return NameCode

    def Computation_latency(self, latency):
        if self.window_version:
            return (latency - 0) / 1000
        return latency / 1000

    def FIRE(self, posture, scope, ballistic, Emit):
        """
        全自动压枪：按 ``ballistic`` 每个元素执行一次下移，tick 间隔约 9ms（经 ``Computation_latency`` 微调）。

        注意: ballistic 数组中的值已经是整数，直接下发即可。
        remainder 机制保留用于处理 posture/scope 计算时的亚像素误差。
        """
        recoil_list = []
        remainder = 0.0
        for i in ballistic:
            if not self.mouse_one:
                break
            Emit('x', (True,))
            recoil = self.calculate_the_recoil(i, posture, scope)  # 返回整数
            recoil_list.append(recoil)
            # 整数 + 余数，然后取整
            exact = recoil + remainder
            move = int(round(exact))
            remainder = exact - move
            self._gd.mouse_R(0, move)
            latency = self.Computation_latency(9)
            time.sleep(latency)
        Emit('x', (False,))
        return recoil_list

    def FIRE1(self, posture, scope, ballistic, Emit):
        """
        半自动/低射速档压枪：逻辑与 ``FIRE`` 相同（同一 remainder 亚像素累加），仅 sleep 基准改为 100ms，
        与 ``FIRE_Start`` 中对 ``Not_Guns`` 的分支一致，避免过快连发与游戏内半自动节奏不符。
        """
        recoil_list = []
        remainder = 0.0
        for i in ballistic:
            if not self.mouse_one:
                break
            Emit('x', (True,))
            recoil = self.calculate_the_recoil(i, posture, scope)
            recoil_list.append(recoil)
            exact = recoil + remainder
            move = int(round(exact))
            remainder = exact - move
            self._gd.mouse_R(0, move)
            latency = self.Computation_latency(100)
            time.sleep(latency)
        Emit('x', (False,))
        return recoil_list
