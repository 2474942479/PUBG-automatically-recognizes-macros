import logging
import os
import sys
import time
import traceback
from logging.handlers import RotatingFileHandler

from data import fire_data
from core import process as Process
from core.paths import res_path
from PyQt5.QtCore import QThread, Qt, pyqtSignal, QEvent
from PyQt5.QtWidgets import QApplication, QWidget, QMessageBox, QMainWindow, QDialog
from ui.pubg_ui import Ui_PUBG
from input.mouse_listener import AppMainMouseListener
from input.key_listener import AppMainKeyListener
from ui.overlay_hud import GameHUD
from ui.roi_config_dialog import ROIConfigDialog
import os

VERSION = "1.0.0"
# 唯一官方发布页（用于启动时醒目标识，减少倒卖与二改包）
OFFICIAL_GITHUB_URL = "https://github.com/2474942479/PUBG-automatically-recognizes-macros"
OFFICIAL_TAGLINE = "非本仓库/作者渠道获取的版本无保障；禁止商用倒卖与技术盗窃。"
logger = logging.getLogger(__name__)
PC = None  # 全局 ProcessClass 实例
DEBUG_MODE = False  # Nuitka 编译需要模块级声明，默认关闭


def setup_logging():
    log_dir = res_path('logs')
    os.makedirs(log_dir, exist_ok=True)
    
    # ✅ 按天存储日志：每次启动不清空，而是按日期创建新文件
    # 删除 7 天前的旧日志（避免无限增长）
    from datetime import datetime, timedelta
    today = datetime.now().strftime('%Y-%m-%d')
    cutoff_date = datetime.now() - timedelta(days=7)
    
    # 清理 7 天前的日志文件
    try:
        for entry in os.listdir(log_dir):
            if entry == 'training_data':
                continue
            entry_path = os.path.join(log_dir, entry)
            if os.path.isfile(entry_path):
                # 从文件名提取日期（如 app_2026-04-28.log）
                import re
                date_match = re.search(r'(\d{4}-\d{2}-\d{2})', entry)
                if date_match:
                    file_date = datetime.strptime(date_match.group(1), '%Y-%m-%d')
                    if file_date < cutoff_date:
                        try:
                            os.remove(entry_path)
                        except Exception:
                            pass
    except Exception:
        pass
    
    # ✅ 通用日志：按天存储 app_YYYY-MM-DD.log
    log_filename = f'app_{today}.log'
    app_handler = RotatingFileHandler(
        os.path.join(log_dir, log_filename),
        mode='a',  # 追加模式
        maxBytes=5 * 1024 * 1024,
        backupCount=3,
        encoding='utf-8'
    )
    app_handler.setFormatter(logging.Formatter(
        '%(asctime)s [%(levelname)s] %(name)s: %(message)s'
    ))
    
    # ✅ 背包配件识别日志：按天存储
    backpack_filename = f'backpack_recognition_{today}.log'
    backpack_handler = RotatingFileHandler(
        os.path.join(log_dir, backpack_filename),
        mode='a',
        maxBytes=5 * 1024 * 1024,
        backupCount=3,
        encoding='utf-8'
    )
    backpack_handler.setFormatter(logging.Formatter(
        '%(asctime)s [%(levelname)s] %(message)s'
    ))
    backpack_handler.addFilter(_BackpackLogFilter())
    
    # ✅ HUD 枪械识别日志：按天存储
    hud_filename = f'hud_recognition_{today}.log'
    hud_handler = RotatingFileHandler(
        os.path.join(log_dir, hud_filename),
        mode='a',
        maxBytes=5 * 1024 * 1024,
        backupCount=3,
        encoding='utf-8'
    )
    hud_handler.setFormatter(logging.Formatter(
        '%(asctime)s [%(levelname)s] %(message)s'
    ))
    hud_handler.addFilter(_HUDLogFilter())
    
    # ✅ ONNX/YOLO 模型识别日志：按天存储
    onnx_filename = f'onnx_recognition_{today}.log'
    onnx_handler = RotatingFileHandler(
        os.path.join(log_dir, onnx_filename),
        mode='a',
        maxBytes=5 * 1024 * 1024,
        backupCount=3,
        encoding='utf-8'
    )
    onnx_handler.setFormatter(logging.Formatter(
        '%(asctime)s [%(levelname)s] %(message)s'
    ))
    onnx_handler.addFilter(_ONNXLogFilter())
    
    root = logging.getLogger()
    root.setLevel(logging.INFO)  # ✅ 默认 INFO 级别
    root.addHandler(app_handler)
    root.addHandler(backpack_handler)
    root.addHandler(hud_handler)
    root.addHandler(onnx_handler)


class _BackpackLogFilter(logging.Filter):
    """背包配件识别日志过滤器：记录 core.recognition 中所有非 HUD 枪械图标的日志"""
    def filter(self, record):
        # 只接受来自 core.recognition 模块的日志
        if record.name != 'core.recognition':
            return False
        # 排除 HUD 枪械图标识别的日志（由 hud_recognition.log 负责）
        return '[枪械图标]' not in record.getMessage()


class _HUDLogFilter(logging.Filter):
    """HUD 枪械识别日志过滤器：只记录含 [枪械图标] 标签的日志"""
    def filter(self, record):
        return '[枪械图标]' in record.getMessage()


class _ONNXLogFilter(logging.Filter):
    """ONNX/YOLO 模型识别日志过滤器：只记录含 [ONNX] 标签的日志"""
    def filter(self, record):
        return '[ONNX]' in record.getMessage()


def setup_exception_handler():
    def handler(exc_type, exc_value, exc_tb):
        error_msg = ''.join(traceback.format_exception(exc_type, exc_value, exc_tb))
        logger.critical("未处理异常:\n%s", error_msg)
        crash_file = res_path('logs', f'crash_{int(time.time())}.log')
        try:
            with open(crash_file, 'w', encoding='utf-8') as f:
                f.write(error_msg)
        except Exception:
            pass
        msg = QMessageBox()
        msg.setIcon(QMessageBox.Critical)
        msg.setWindowTitle("程序异常")
        msg.setText(f"程序遇到了一个错误，即将退出。\n\n错误日志已保存到:\n{crash_file}")
        msg.setDetailedText(error_msg)
        msg.setWindowFlags(msg.windowFlags() | Qt.WindowStaysOnTopHint)
        msg.exec_()
    sys.excepthook = handler


def _apply_debug_state_to_logging():
    """根据全局 DEBUG_MODE 设置 root 日志级别（不与 PC 写盘混用，供启动对齐）。"""
    root = logging.getLogger()
    root.setLevel(logging.DEBUG if DEBUG_MODE else logging.INFO)


def sync_debug_mode_from_config():
    """启动时：以 config 中的 debug_mode 为准，同步 DEBUG_MODE + root 级别。"""
    global DEBUG_MODE
    try:
        from core.process import ProcessClass
        pc = ProcessClass()
        DEBUG_MODE = bool(getattr(pc, "debug_input_trace", False))
    except Exception:
        DEBUG_MODE = False
    _apply_debug_state_to_logging()


def toggle_debug_mode():
    """
    调试总开关（热键 F9，唯一）：
    - 全量日志级别 DEBUG/INFO
    - [INPUT_TRACE] 行（Tab/开镜等）
    - 开镜姿势识别存图 logs/posture_debug/（与 PC.debug_input_trace 一致）
    - 仅在程序生命周期内有效，不持久化到配置
    """
    global DEBUG_MODE
    from core.process import ProcessClass
    DEBUG_MODE = not DEBUG_MODE
    _apply_debug_state_to_logging()
    try:
        pc = ProcessClass()
        pc.debug_input_trace = DEBUG_MODE
        # ✅ 不再保存到 config.json，仅在程序生命周期内有效
    except Exception as e:
        logger.warning("切换调试模式失败: %s", e)
    if DEBUG_MODE:
        logger.info(
            "调试总开关: ON (F9 关) — DEBUG + INPUT_TRACE + 姿势调试图，见 logs/app.log / posture_debug/"
        )
    else:
        logger.info("调试总开关: OFF (F9 开)")
    try:
        pc = ProcessClass()
        if getattr(pc, "_ui_log_callback", None):
            pc._ui_log_callback(
                "📝 调试: %s (F9/界面按钮) 日志+INPUT_TRACE+姿势图" % ("ON" if DEBUG_MODE else "OFF")
            )
    except Exception:
        pass
    try:
        pc = ProcessClass()
        cb = getattr(pc, "_on_debug_mode_changed", None)
        if callable(cb):
            cb()
    except Exception:
        pass


def debug_hotkey_f9(key_listener):
    """
    F9 与主界面「调试」按钮共用：仅切换调试开关
    - 全量日志级别 DEBUG/INFO
    - [INPUT_TRACE] 行（Tab/开镜等）
    - 开镜姿势识别存图 logs/posture_debug/（与 PC.debug_input_trace 一致）
    - 仅在程序生命周期内有效，不持久化到配置
    """
    toggle_debug_mode()


class AppManager(QWidget, Ui_PUBG):  # 定义主应用管理类，继承自QWidget和UI类
    def __init__(self):  # 初始化方法
        super().__init__()  # 调用父类的初始化方法
        self.isHidden = None  # 初始化窗口隐藏状态
        self.my_mouse_thread = None  # 初始化鼠标线程
        self.my_key_thread = None  # 初始化键盘线程
        self.pauses = True  # 初始化暂停状态
        self.TextValue = {'无': 'none', '红点': 'hongdian', '全息': "quanxi", '2倍': '2bei',  # 定义文本值映射
                          '3倍': '3bei', '4倍': "4bei", '6倍': '6bei', '8倍': '8bei', '15倍': '15bei',
                          '多倍低': 'duobei1', '多倍高': 'duobei4',
                          '红点(Shift)': 'hongdian_shift', '全息(Shift)': 'quanxi_shift',
                          '多倍低(Shift)': 'duobei1_shift', '2倍(Shift)': '2bei_shift',
                          '3倍(Shift)': '3bei_shift', '4倍(Shift)': '4bei_shift',
                          '多倍高(Shift)': 'duobei4_shift', '6倍(Shift)': '6bei_shift',
                          '8倍(Shift)': '8bei_shift', '15倍(Shift)': '15bei_shift',
                          'shift': 'shift'}
        self.init_ui()  # 调用初始化UI方法

    def closeEvent(self, event):
        """主窗口关闭事件处理 - 确保关闭主窗口时才退出程序"""
        # 确认是否真的要退出程序
        reply = QMessageBox.question(
            self, 
            '确认退出',
            '确定要退出PUBG宏识别工具吗？',
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )
        
        if reply == QMessageBox.Yes:
            # ✅ 关闭时关闭调试模式（不持久化）
            try:
                PC.debug_input_trace = False
                import main as m
                m.DEBUG_MODE = False
            except:
                pass
            
            # 停止所有后台线程和服务
            if hasattr(self, 'my_mouse_thread') and self.my_mouse_thread:
                try:
                    self.my_mouse_thread.stop()
                except:
                    pass
            if hasattr(self, 'my_key_thread') and self.my_key_thread:
                try:
                    self.my_key_thread.stop()
                except:
                    pass
            if hasattr(self, '_hud') and self._hud:
                try:
                    self._hud.close()
                except:
                    pass
            
            event.accept()
            # ✅ 真正退出应用程序
            QApplication.quit()
        else:
            event.ignore()

    def init_ui(self):
        self.setupUi(self)
        self.setWindowTitle(f"PUBG 宏识别工具 v{VERSION} | 作者 GitHub: {OFFICIAL_GITHUB_URL}")
        self.setWindowFlags(Qt.WindowStaysOnTopHint)
        self.Init_UI_LOG(f"程序初始化中... v{VERSION}")
        self.Init_UI_LOG(f"【官方仓库】{OFFICIAL_GITHUB_URL}")
        self.Init_UI_LOG(f"【声明】{OFFICIAL_TAGLINE}")
        self.Init_UI_LOG(PC.ghub_device_info)

        if PC.ghub_device_info and ("缺失" in PC.ghub_device_info or "未安装" in PC.ghub_device_info):
            QMessageBox.warning(
                self, "驱动检测",
                "未检测到罗技 G HUB 驱动！\n\n"
                "请先安装 G HUB 驱动，安装后重启电脑再运行本工具。\n"
                "下载地址: https://www.logitechg.com/zh-cn/innovation/g-hub.html"
            )

        self.Init_UI_Equip(PC.Current_firearms)
        self.Init_UI_Posture(PC.Current_posture)
        self.Init_UI_ScopeMode(PC.RightClick)
        self.Init_UI_ScopeOpen(PC.StartFire)
        self.Init_UI_GunsData()
        self.ResolutionSelect.setCurrentText(PC.Monitor)
        self.Init_UI_Sensitivity()
        self.Init_UI_PostureV3()
        self.Init_UI_GunRatioV3()
        self.Init_UI_Btn()
        self.Init_UI_LOG("程序初始化完成")
        
        # ═══ 设置 UI 日志回调 ═══
        PC._ui_log_callback = self.Init_UI_LOG
        PC._on_debug_mode_changed = self._refresh_debug_mode_button
        self._refresh_debug_mode_button()
        
        self._hud = GameHUD(PC)
    
    def _refresh_debug_mode_button(self):
        """与 F9、config.debug_mode 同步主界面「调试」按钮文字。"""
        import main as m
        on = m.DEBUG_MODE
        if hasattr(self, "DebugModeBtn"):
            self.DebugModeBtn.setText("调试: 开" if on else "调试: 关")

    def on_debug_mode_clicked(self):
        from main import debug_hotkey_f9
        debug_hotkey_f9(self.my_key_thread)
    
    def on_engine_changed(self, index):
        """识别引擎切换"""
        engine_map = {0: 'auto', 1: 'opencv', 2: 'onnx'}
        engine = engine_map.get(index, 'auto')
        PC.save_config_data('engine', engine)
        PC.recognize_engine = engine
        logger.info(f"识别引擎切换为: {engine}")

    def Init_UI_Btn(self):  # 初始化按钮事件
        self.Startbtn.clicked.connect(self.start)  # 绑定开始按钮事件
        self.Stopbtn.clicked.connect(self.stop)  # 绑定停止按钮事件
        self.Pausebtn.clicked.connect(self.pause)  # 绑定暂停按钮事件
        # ⚙️ 菜单工具按钮（齿轮图标，标题栏）
        self.actionROIConfig.triggered.connect(self.open_roi_config)  # ROI 配置
        self.actionBatchTemplate.triggered.connect(self.batch_generate_templates)  # 批量生成模板
        self.DebugModeBtn.clicked.connect(self.on_debug_mode_clicked)
        # ═══ 识别引擎切换 ═══
        if hasattr(self, "EngineSelector"):
            self.EngineSelector.currentIndexChanged.connect(self.on_engine_changed)
            # 加载当前配置
            engine = PC.get_config_data('engine')
            engine_map = {'auto': 0, 'opencv': 1, 'onnx': 2}
            self.EngineSelector.setCurrentIndex(engine_map.get(engine, 0))
        self.ResolutionBtn.clicked.connect(self.Save_Config_Resolution)  # 绑定分辨率保存按钮事件
        self.SensitivityBtn.clicked.connect(self.Save_Config_Sensitivity)  # 绑定灵敏度保存按钮事件
        self.PostureBtn.clicked.connect(self.Save_Config_PostureV3)  # 绑定姿态系数保存按钮事件
        self.PostureSelect.currentIndexChanged[int].connect(self.Change_Posture_label)  # 绑定姿态选择变化
        self.GunRatioBtn.clicked.connect(self.Save_Config_GunRatioV3)  # 绑定枪械系数保存按钮事件
        self.GunRatioSelect.currentIndexChanged[int].connect(self.Change_GunRatio_label)  # 绑定枪械选择变化
        self.OpenScope.clicked.connect(lambda: self.Btn_click("ScopeOpen", True))  # 绑定开镜按钮事件
        self.CloseScope.clicked.connect(lambda: self.Btn_click("ScopeOpen", False))  # 绑定关镜按钮事件
        self.TwoGuns.clicked.connect(lambda: self.Btn_click("Guns", 2))  # 绑定双枪按钮事件
        self.OneGuns.clicked.connect(lambda: self.Btn_click("Guns", 1))  # 绑定单枪按钮事件
        self.Orders.clicked.connect(lambda: self.Btn_click("Guns", "x"))  # 绑定其他枪械按钮事件
        self.Stand.clicked.connect(lambda: self.Btn_click("Posture", 'space'))  # 绑定站立姿态按钮事件
        self.GetDown.clicked.connect(lambda: self.Btn_click("Posture", 'z'))  # 绑定蹲下姿态按钮事件
        self.SquatDown.clicked.connect(lambda: self.Btn_click("Posture", 'c'))  # 绑定趴下姿态按钮事件
        self.LongPress.clicked.connect(lambda: self.Btn_click("ScopeMode", True))  # 绑定长按开镜按钮事件
        self.ClickPress.clicked.connect(lambda: self.Btn_click("ScopeMode", False))  # 绑定点击开镜按钮事件
        self.FirstPerson.clicked.connect(lambda: self.Btn_click("personView", True))   # 绑定第一人称按钮事件
        self.ThirdPerson.clicked.connect(lambda: self.Btn_click("personView", False))  # 绑定第一人称按钮事件
    def Init_UI_Win(self):  # 初始化窗口信息
        if PC.window_version:  # 判断操作系统版本
            version = "(Win11版)"  # 设置为Win11版本
        else:
            version = "(Win10版)"  # 设置为Win10版本
        
        self.WinVersion.setText(version)  # 显示版本信息
    
    def Btn_click(self, key, value):  # 按钮点击事件处理
        """
        按钮点击事件
        """
        if key == "Guns":  # 如果是枪械选择
            PC.Change_firearms(value)  # 更改枪械
        elif key == "Posture":  # 如果是姿态选择
            PC.Change_posture(value)  # 更改姿态
        elif key == "ScopeMode":  # 如果是开镜模式选择
            PC.RightClick = value  # 设置开镜模式
        elif key == "ScopeOpen":  # 如果是开镜状态选择
            PC.StartFire = value  # 设置开镜状态
        elif key == "personView": # 第一人称
            PC.firstPerson = value
    
    def toggle_window(self):  # 切换窗口显示状态
        if self.isHidden:  # 如果当前隐藏
            self.show()  # 显示窗口
            self.isHidden = False  # 更新状态
        else:  # 如果当前显示
            self.hide()  # 隐藏窗口
            self.isHidden = True  # 更新状态
    
    def Get_GUNS_CH(self, Name, Type):  # 获取枪械汉化名称
        """
        加载配件汉化文件
        :return:
        """
        CH_data = fire_data.ACCESSORIES_CH.get(Type, None)  # 获取汉化数据
        Default = Name if Type == "Name" else "未知"  # 设置默认值
        if CH_data:  # 如果有汉化数据
            return CH_data.get(Name.lower(), Default)  # 返回汉化名称
        else:  # 如果没有汉化数据
            return "未知"  # 返回未知
    
    def Init_UI_Equip(self, Current_firearms):  # 初始化UI枪械信息
        """
        修改UI当前枪械的数据
        :param Current_firearms: 当前枪械
        """
        if Current_firearms == 2:  # 如果是双枪
            self.TwoGuns.setChecked(True)  # 设置双枪按钮选中
        elif Current_firearms == 1:  # 如果是单枪
            self.OneGuns.setChecked(True)  # 设置单枪按钮选中
        else:  # 如果是其他枪械
            self.Orders.setChecked(True)  # 设置其他枪械按钮选中
    
    def Init_UI_Posture(self, Current_posture):  # 初始化UI姿态信息
        """
        修改UI当前姿态的数据
        :param Current_posture: 当前姿态
        """
        if Current_posture == "None":  # 如果是站立
            self.Stand.setChecked(True)  # 设置站立按钮选中
        
        elif Current_posture == "z":  # 如果是蹲下
            self.GetDown.setChecked(True)  # 设置蹲下按钮选中
        elif Current_posture == "c":  # 如果是趴下
            self.SquatDown.setChecked(True)  # 设置趴下按钮选中
    
    def Init_UI_ScopeMode(self, mode):  # 初始化UI开镜模式
        """
        修改UI当前开镜模式
        :param mode: 当前开镜模式
        """
        if mode:  # 如果是长按开镜
            self.LongPress.setChecked(True)  # 设置长按开镜按钮选中
        else:  # 如果是点击开镜
            self.ClickPress.setChecked(True)  # 设置点击开镜按钮选中
    
    def Init_UI_ScopeOpen(self, Open):  # 初始化UI开镜状态
        """
        修改UI当前是否开镜数据
        :param Open: 是否开镜数据
        """
        # ✅ 修复：必须同时设置两个按钮的状态，确保互斥
        if Open:  # 如果开镜
            self.OpenScope.setChecked(True)   # 设置开镜按钮选中
            self.CloseScope.setChecked(False)  # ✅ 取消关镜按钮选中
        else:  # 如果不开镜
            self.OpenScope.setChecked(False)   # ✅ 取消开镜按钮选中
            self.CloseScope.setChecked(True)   # 设置关镜按钮选中

    def Init_UI_firstPerson(self, model):
        if model:  # 如果是第一人称
            self.FirstPerson.setChecked(True)  # 设置第一人称按钮选中
            self.ThirdPerson.setChecked(False)
        else:  # 如果不是第一人称
            self.ThirdPerson.setChecked(True)  # 设置第三人称按钮选中
            self.FirstPerson.setChecked(False)
    
    def Init_UI_GunsData(self):  # 初始化UI枪械数据
        """
        修改UI 的识别结果
        :return:
        """
        results = PC.get_guns_result()  # 获取枪械识别结果
        logger.info(f"📊 UI 更新枪械数据: Result1={results[0]}, Result2={results[1]}")
        
        for idx, result in enumerate(results, start=1):  # 遍历结果
            # ✅ 修复：只要 result 不是 None 就更新 UI（包括包含 "None" 值的字典）
            if result is not None:  # 如果有结果（即使是空状态）
                name = result.get("Name", "None")
                scope = result.get("Scope", "none")
                muzzle = result.get("Muzzle", "none")
                grip = result.get("Grip", "none")
                stock = result.get("Stock", "none")
                
                logger.info(f"🔫 {idx}号枪: Name={name}, Scope={scope}, Muzzle={muzzle}, Grip={grip}, Stock={stock}")
                
                self.__getattribute__(f"Name{idx}Name").setText(self.Get_GUNS_CH(name, "Name"))  # 设置枪械名称
                self.__getattribute__(f"Scope{idx}Name").setText(self.Get_GUNS_CH(scope, "Scope"))  # 设置镜类型
                self.__getattribute__(f"Muzzle{idx}Name").setText(self.Get_GUNS_CH(muzzle, "Muzzle"))  # 设置枪口类型
                self.__getattribute__(f"Grip{idx}Name").setText(self.Get_GUNS_CH(grip, "Grip"))  # 设置握把类型
                self.__getattribute__(f"Butt{idx}Name").setText(self.Get_GUNS_CH(stock, "Stock"))  # 设置枪托类型
            else:
                logger.warning(f"⚠️ {idx}号枪识别结果为 None")
    
    def Init_UI_Sensitivity(self):  # 初始化UI灵敏度
        SelectValue = self.SensitivitySelect.currentText()  # 获取当前选择的灵敏度
        self.Change_Sensitivity_label(SelectValue)  # 更新灵敏度标签
        self.SensitivitySelect.currentIndexChanged[str].connect(self.Change_Sensitivity_label)  # 绑定灵敏度选择变化事件
    
    def Init_UI_ReductionData(self):  # 初始化UI所有数据
        self.Init_UI_Equip(PC.Current_firearms)  # 初始化枪械信息
        self.Init_UI_Posture(PC.Current_posture)  # 初始化姿态信息
        self.Init_UI_ScopeMode(PC.RightClick)  # 初始化开镜模式
        self.Init_UI_ScopeOpen(PC.StartFire)  # 初始化开镜状态
        self.Init_UI_GunsData()  # 初始化枪械数据
    
    def Init_UI_LOG(self, info):  # 初始化UI日志
        self.Info.append(info + "\n")  # 添加日志信息
    
    def Change_Sensitivity_label(self, SelectValue):
        Text = self.TextValue
        Select = PC.ScopeFactorV3.get(Text[SelectValue], '1')
        self.SensitivityText.setText(str(Select))
    
    def Save_Config_Resolution(self):  # 保存分辨率设置
        PC.Monitor = self.ResolutionSelect.currentText()  # 获取当前选择的分辨率
        PC.save_config_data('resolution', PC.Monitor)  # 保存配置
        self.message_Info("保存分辨率设置成功！！")  # 显示成功消息
    
    def Save_Config_Sensitivity(self):  # 保存灵敏度设置
        SensitivityText = self.SensitivityText.text()  # 获取灵敏度输入
        SensitivityText = self.is_numeric(SensitivityText)  # 检查是否为数字
        if not SensitivityText:  # 如果不是数字
            self.message_Info("输入框只能输入数字！！", '警告')  # 显示警告
            return
        
        SensitivitySelect = self.SensitivitySelect.currentText()  # 获取当前选择的灵敏度类型
        Text = self.TextValue[SensitivitySelect]  # 获取文本值

        PC.ScopeFactorV3[Text] = SensitivityText
        PC.save_config_data('scope_factor_v3', PC.ScopeFactorV3)
        self.message_Info("倍镜系数保存成功！")
    
    # ═══════════════════════════════════════════
    # 姿态系数 (v3) 配置
    # ═══════════════════════════════════════════

    # 姿态名 → config key 映射
    PostureKeyMap = {0: "c", 1: "z"}  # 0=蹲下, 1=趴下

    def Init_UI_PostureV3(self):  # 初始化姿态系数显示
        self.Change_Posture_label(self.PostureSelect.currentIndex())

    def Change_Posture_label(self, idx):  # 更新姿态系数标签
        key = self.PostureKeyMap.get(idx, "c")
        value = PC.PostureV3.get(key, 1.0)
        self.PostureText.setText(str(value))

    def Save_Config_PostureV3(self):  # 保存姿态系数设置
        PostureText = self.PostureText.text()  # 获取输入
        PostureText = self.is_numeric(PostureText)  # 检查是否为数字
        if not PostureText:
            self.message_Info("输入框只能输入数字！！", '警告')
            return
        idx = self.PostureSelect.currentIndex()
        key = self.PostureKeyMap.get(idx, "c")
        PC.PostureV3[key] = PostureText
        PC.save_config_data('posture_v3', PC.PostureV3)
        posture_name = "蹲下" if key == "c" else "趴下"
        self.message_Info(f"v3 姿态系数保存成功！{posture_name}={PostureText}")

    # ═══════════════════════════════════════════
    # 枪械独立压枪系数 (v3) 配置
    # ═══════════════════════════════════════════

    # 枪械中文名 → 武器文件名 映射
    GUN_NAME_MAP = {
        "AKM": "akm", "M762": "m762", "G36C": "g36c", "M416": "m416",
        "SCAR-L": "scar-l", "QBZ": "qbz", "AUG": "aug", "Groza": "groza",
        "ACE32": "ace32", "K2": "k2", "PP19": "pp19", "汤姆逊": "tangmuxunchongfengqiang",
        "UMP45": "ump45", "UZI": "uzi", "Vector": "vector", "MP5K": "mp5k",
        "P90": "p90", "JS9": "js9", "DP28": "dp28", "M249": "m249",
        "MG3": "mg3", "MK14": "mk14", "FAMAS": "famas", "MP9": "mp9",
        "VSS": "vss", "MK47": "mk47", "德拉贡诺夫": "delagongnuofu",
        "QBU": "qbu", "MK12": "mk12", "Mini14": "mini14", "SKS": "sks",
        "自动装填": "zidongzhuangtianbuqiang",
    }

    def Init_UI_GunRatioV3(self):  # 初始化枪械系数
        # 填充下拉框
        self.GunRatioSelect.clear()
        for cn_name in self.GUN_NAME_MAP:
            self.GunRatioSelect.addItem(cn_name)
        self.Change_GunRatio_label(self.GunRatioSelect.currentIndex())

    def Change_GunRatio_label(self, idx):  # 更新枪械系数标签
        cn_name = self.GunRatioSelect.currentText()
        weapon_key = self.GUN_NAME_MAP.get(cn_name, "")
        value = PC.GunRatioV3.get(weapon_key, 1.0)
        self.GunRatioText.setText(str(value))

    def Save_Config_GunRatioV3(self):  # 保存枪械系数设置
        GunRatioText = self.GunRatioText.text()  # 获取输入
        GunRatioText = self.is_numeric(GunRatioText)  # 检查是否为数字
        if not GunRatioText:
            self.message_Info("输入框只能输入数字！！", '警告')
            return
        cn_name = self.GunRatioSelect.currentText()
        weapon_key = self.GUN_NAME_MAP.get(cn_name, "")
        if not weapon_key:
            self.message_Info("未选择枪械！！", '警告')
            return
        PC.GunRatioV3[weapon_key] = GunRatioText
        PC.save_config_data('gun_ratio_v3', PC.GunRatioV3)
        self.message_Info(f"v3 枪械系数保存成功！{cn_name}={GunRatioText}")

    def message_Info(self, message, title="提示信息"):  # 显示消息框
        message_box = QMessageBox()  # 创建消息框
        message_box.setWindowTitle(title)  # 设置标题
        message_box.setText(message)  # 设置消息内容
        message_box.setIcon(QMessageBox.Information)  # 设置图标
        message_box.setWindowFlags(message_box.windowFlags() | Qt.WindowStaysOnTopHint)  # 设置窗口始终置顶
        message_box.exec()  # 显示消息框
    
    def is_numeric(self, string):  # 检查字符串是否为数字
        try:  # 尝试转换
            if '.' in string:  # 如果包含小数点
                return float(string)  # 转换为浮点数
            else:  # 如果不包含小数点
                return int(string)  # 转换为整数
        except ValueError:  # 如果转换失败
            return False  # 返回False
    
    def start(self):  # 开始程序
        self.my_key_thread = AppMainKeyListener(PC)  # 创建键盘监听线程
        self.my_mouse_thread = AppMainMouseListener(PC)  # 创建鼠标监听线程
        
        # 设置键盘监听器引用，用于Alt+右键检测
        self.my_mouse_thread.key_listener = self.my_key_thread
        # 设置鼠标监听器引用，用于调试模式切换
        PC.mouse_listener = self.my_mouse_thread
        
        self.my_key_thread.start()  # 启动键盘监听线程
        self.my_mouse_thread.start()  # 启动鼠标监听线程
        
        self.my_key_thread.keyInfo.connect(self.onKeyPressed)  # 绑定键盘事件
        self.my_mouse_thread.mouseClicked.connect(self.onKeyPressed)  # 绑定鼠标事件
        self.my_key_thread.roi_config_requested.connect(self.open_roi_config)  # 绑定 ROI 配置快捷键
        self.my_key_thread.batch_template_requested.connect(self.batch_generate_templates)  # 绑定批量生成模板快捷键 (Ctrl+Alt+F8)
        
        self.SetStatus()  # 设置状态
        self.StatusInfo.setText('程序运行中.....')  # 更新状态信息
        self._hud.show_hud()
    
    def SetStatus(self):  # 设置按钮状态
        self.Startbtn.setEnabled(False)  # 禁用开始按钮
        self.Pausebtn.setEnabled(True)  # 启用暂停按钮
        self.Stopbtn.setEnabled(True)  # 启用停止按钮
        self.EquipBox.setEnabled(True)  # 启用枪械选择框
        self.PoseBox.setEnabled(True)  # 启用姿态选择框
        self.IsScope.setEnabled(True)  # 启用开镜选择框
    
    def stop(self):  # 停止程序
        self.StatusInfo.setText('程序退出中....')  # 更新状态信息
        self._hud.stop()
        self.my_key_thread.stop_listener()  # 停止键盘监听
        self.my_mouse_thread.stop_listener()  # 停止鼠标监听
        self.my_key_thread.terminate()  # 终止键盘线程
        self.my_mouse_thread.terminate()  # 终止鼠标线程
        
        QApplication.quit()  # 退出应用程序
    
    def pause(self):  # 暂停或继续程序
        if self.pauses:  # 如果当前暂停
            self.my_key_thread.stop_listener()  # 停止键盘监听
            self.my_mouse_thread.stop_listener()  # 停止鼠标监听
            self.Pausebtn.setText("继续")  # 更新按钮文本
            self.StatusInfo.setText('程序暂停中....')  # 更新状态信息
            self._hud.hide_hud()
            self.pauses = False  # 更新暂停状态
        else:  # 如果当前继续
            self.my_key_thread.rerun()  # 重新启动键盘监听
            self.my_mouse_thread.rerun()  # 重新启动鼠标监听
            self.Pausebtn.setText("暂停")  # 更新按钮文本
            self.StatusInfo.setText('程序运行中....')  # 更新状态信息
            self._hud.show_hud()
            self.pauses = True  # 更新暂停状态
    
    def onKeyPressed(self, key, value):  # 处理按键事件
        values = value[0]  # 获取事件值
        actions = {  # 定义事件映射
            "l": (self.Init_UI_LOG, [values]),  # 日志事件
            "s": (self.Init_UI_ScopeOpen, [values]),  # 开镜状态事件
            "g": (self.Init_UI_GunsData, []),  # 枪械数据事件
            "e": (self.Init_UI_Equip, [values]),  # 枪械信息事件
            "p": (self.Init_UI_Posture, [values]),  # 姿态信息事件
            "c": (self.Init_UI_ReductionData, []),  # 所有数据事件
            "t": (self.toggle_window, []),  # 切换窗口事件
            "v": (self.Init_UI_firstPerson, [values]) # 切换视角
        }
        
        action, args = actions.get(key, (None, None))  # 获取事件处理函数和参数
        if action:  # 如果有处理函数
            action(*args)  # 调用处理函数
    
    def batch_generate_templates(self):
        """
        批量生成模板按钮回调。
        先截屏识别，弹出确认对话框让用户勾选，再写入文件。
        """
        try:
            import logging
            logger = logging.getLogger(__name__)

            # 1. 提示用户准备
            reply = QMessageBox.question(
                self,
                "批量生成模板",
                "即将从当前屏幕截取画面，批量处理所有背包 ROI 区域。\n\n"
                "【请先做好准备】\n"
                " 1. 确保游戏在前台运行\n"
                " 2. 按 Tab 打开背包\n"
                " 3. 切换到要制作模板的枪械（1号位或2号位）\n"
                " 4. 确保已用 ROI 工具配置好所有背包坐标\n\n"
                "点击「确定」后立即截图。\n"
                "截图完成后会弹出确认窗口，你可以勾选要保存的项。",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.Yes
            )

            if reply != QMessageBox.Yes:
                return

            # 2. 第一阶段：收集候选
            self.Init_UI_LOG("📸 正在截取并识别背包配件…")
            from PyQt5.QtWidgets import QApplication
            from core.template_batch import collect_candidates, save_selected
            import time
            resolution = PC.Monitor
            t0 = time.time()

            def _log_callback(msg):
                self.Init_UI_LOG(msg)
                QApplication.processEvents()

            candidates, error = collect_candidates(
                resolution, ui_log_callback=_log_callback
            )
            elapsed_phase1 = time.time() - t0

            if error:
                self.Init_UI_LOG(f"❌ {error}")
                return

            self.Init_UI_LOG(f"⏱️ 识别完成，耗时: {elapsed_phase1:.1f}秒")

            # 3. 弹出确认对话框
            from ui.template_confirm_dialog import TemplateConfirmDialog
            confirm = TemplateConfirmDialog(candidates, self)
            if confirm.exec_() != QDialog.Accepted:
                self.Init_UI_LOG("⏹️ 用户取消，未保存任何模板")
                return

            # 4. 第二阶段：保存选中项
            t1 = time.time()
            result = save_selected(
                candidates, confirm.selected_indices,
                resolution,
                name_overrides=getattr(confirm, 'name_overrides', None),
                ui_log_callback=_log_callback
            )
            elapsed_phase2 = time.time() - t1
            self.Init_UI_LOG(f"⏱️ 保存耗时: {elapsed_phase2:.1f}秒")
            self.Init_UI_LOG(f"⏱️ 总计耗时: {time.time() - t0:.1f}秒")

        except Exception as e:
            import traceback
            self.Init_UI_LOG(f"❌ 批量生成模板失败: {e}\n{traceback.format_exc()}")
    
    def open_roi_config(self):
        """打开 ROI 配置对话框"""
        try:
            logger.info("🔍 F8/按钮触发：开始打开 ROI 配置对话框")
            resolution = PC.Monitor
            logger.info(f"📊 当前分辨率: {resolution}")
            
            # ✅ 暂停自动姿势识别，避免在配置 ROI 时不断截图
            original_posture_roi = PC.posture_roi
            PC.posture_roi = None
            logger.info("已暂停自动姿势识别（ROI 配置中）")
            
            # ✅ 从 roi_config.json 加载阶段1需要的配置（不加载阶段2的枪械配件 ROI）
            import json
            from core.paths import res_path
            
            config_file = res_path('Config', 'roi_config.json')
            current_rois = {}
            
            if os.path.exists(config_file):
                with open(config_file, 'r', encoding='utf-8') as f:
                    full_config = json.load(f)
                
                # ✅ 只加载阶段1的特殊配置（背包区域、HUD 区域、姿势区域、开镜坐标）
                # 不加载分辨率下的枪械配件 ROI（Name_1、Scope_1 等）
                
                # 加载背包区域
                guns_backpack = full_config.get('_GUNS_REOLUTION_SETTINGS', {}).get(resolution)
                if guns_backpack:
                    current_rois['guns_backpack_roi'] = list(guns_backpack)
                    logger.info(f"📦 加载背包区域: {guns_backpack}")
                else:
                    logger.warning(f"⚠️ 未找到分辨率 {resolution} 的背包区域配置")
                
                # 加载 HUD 区域配置（类似背包区域）
                hud_settings = full_config.get('_GUN_HUD_SETTINGS', {}).get(resolution)
                if hud_settings:
                    current_rois['_GUN_HUD_SETTINGS'] = {resolution: list(hud_settings)}
                    logger.info(f"🎯 加载 HUD 枪械图标区域: {hud_settings}")
                else:
                    logger.warning(f"⚠️ 未找到分辨率 {resolution} 的 HUD 区域配置")
                
                # 加载姿势区域（如果有）
                if resolution in full_config and 'posture_roi' in full_config[resolution]:
                    current_rois['posture_roi'] = full_config[resolution]['posture_roi']
                    logger.info(f"🎭 加载姿势区域: {current_rois['posture_roi']}")
                
                # 加载开镜坐标（如果有）
                click_pos = full_config.get('_CLICK_POSITION', {}).get(resolution)
                if click_pos:
                    current_rois['right_click_pos'] = list(click_pos)
                    logger.info(f"🖱️ 加载开镜坐标: {click_pos}")
                
                logger.info(f"📋 从 roi_config.json 加载了 {len(current_rois)} 个阶段1配置")
            else:
                logger.warning(f"⚠️ ROI 配置文件不存在: {config_file}")
            
            # 创建对话框（不设置父窗口，使其成为独立窗口）
            logger.info("🛠️ 创建 ROIConfigDialog...")
            dialog = ROIConfigDialog(resolution, current_rois)
            logger.info("✅ ROIConfigDialog 创建成功")
            
            # ✅ 连接 roi_saved 信号：每次保存立即写入 roi_config.json
            def on_roi_saved(roi_type, roi_coords):
                try:
                    config_file = res_path('Config', 'roi_config.json')
                    config_data = {}
                    if os.path.exists(config_file):
                        with open(config_file, 'r', encoding='utf-8') as f:
                            config_data = json.load(f)
                    
                    if roi_type == 'guns_backpack_roi':
                        if '_GUNS_REOLUTION_SETTINGS' not in config_data:
                            config_data['_GUNS_REOLUTION_SETTINGS'] = {}
                        config_data['_GUNS_REOLUTION_SETTINGS'][resolution] = list(roi_coords)
                    elif roi_type == 'hud_gun_icons':
                        # HUD 区域配置保存到独立节点（类似背包区域）
                        if '_GUN_HUD_SETTINGS' not in config_data:
                            config_data['_GUN_HUD_SETTINGS'] = {}
                        config_data['_GUN_HUD_SETTINGS'][resolution] = list(roi_coords)
                    elif roi_type == 'right_click_pos':
                        if '_CLICK_POSITION' not in config_data:
                            config_data['_CLICK_POSITION'] = {}
                        config_data['_CLICK_POSITION'][resolution] = list(roi_coords)
                    else:
                        if resolution not in config_data:
                            config_data[resolution] = {}
                        config_data[resolution][roi_type] = list(roi_coords)
                    
                    with open(config_file, 'w', encoding='utf-8') as f:
                        json.dump(config_data, f, ensure_ascii=False, indent=2)
                    logger.info(f"💾 {roi_type} 已写入 roi_config.json")
                except Exception as ex:
                    logger.error(f"❌ 写入 ROI 配置失败: {ex}")
            
            dialog.roi_saved.connect(on_roi_saved)
                
            # 显示对话框（阻塞直到关闭）
            logger.info("📖 显示 ROI 配置对话框 (exec_)...")
            result = dialog.exec_()
            logger.info(f"📕 ROI 配置对话框关闭，返回码: {result}")
                
            # ✅ 恢复自动姿势识别（重新加载最新配置）
            PC._load_posture_roi_from_resolution()
            logger.info("已恢复自动姿势识别（重新加载配置）")
            
        except Exception as e:
            import traceback
            error_msg = traceback.format_exc()
            logger.error(f"❌ 打开 ROI 配置失败: {error_msg}")
            QMessageBox.critical(self, "错误", f"打开 ROI 配置失败:\n{e}")

if __name__ == '__main__':
    setup_logging()
    setup_exception_handler()
    logger.info("程序启动 v%s | 官方: %s", VERSION, OFFICIAL_GITHUB_URL)
    logger.info("%s", OFFICIAL_TAGLINE)

    app = QApplication([])
    # 设置退出策略：不自动退出，由我们控制
    app.setQuitOnLastWindowClosed(False)
    PC = Process.ProcessClass()
    
    # ✅ 调试模式默认关闭，仅在程序生命周期内有效，不从配置加载
    import main as m
    m.DEBUG_MODE = False
    _apply_debug_state_to_logging()
    logger.info("📝 调试模式: 关闭 (F9 开启，仅本次运行有效)")

    Main = AppManager()
    Main.show()
    sys.exit(app.exec_())
