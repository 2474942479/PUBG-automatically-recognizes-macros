# -*- coding: utf-8 -*-
"""
@Time : 2024/2/20 14:51
@Author : hsxisawd
@File : MouseListener.py
@Project : Code
@Des:
"""
from threading import Thread  # 导入线程模块，用于多线程操作
from PyQt5.QtCore import QThread, pyqtSignal  # 导入PyQt5的线程和信号模块
from pynput import mouse  # 导入pynput鼠标模块，用于监听鼠标事件
import ctypes  # 导入ctypes用于Windows API调用

# Windows API 常量
VK_LMENU = 0xA4  # 左 Alt 键虚拟键码
VK_RMENU = 0xA5  # 右 Alt 键虚拟键码

def is_alt_pressed():
    """实时检测 Alt 键是否按下（不依赖键盘监听器）"""
    try:
        return (ctypes.windll.user32.GetKeyState(VK_LMENU) & 0x8000 != 0 or 
                ctypes.windll.user32.GetKeyState(VK_RMENU) & 0x8000 != 0)
    except Exception:
        return False

class AppMainMouseListener(QThread):  # 定义鼠标监听器类，继承自QThread
    mouseClicked = pyqtSignal(str, tuple)  # 定义信号，用于发送鼠标事件信息

    def __init__(self, PCdata):  # 初始化方法
        super().__init__()  # 调用父类的初始化方法
        self.listener = None  # 初始化鼠标监听器
        self.data = []  # 初始化数据列表
        self.PC = PCdata  # 保存PC对象引用
        self.count = 1  # 初始化计数器
        self.key_listener = None  # 保存键盘监听器引用
        self.debug_mode = False  # 姿势识别调试模式
        
        # ✅ 姿势识别优化：不再使用防抖和缓存，每次开镜都强制更新
        # self._last_posture_recognize_time = 0  # 已废弃
        # self._posture_recognize_cooldown = 2.0  # 已废弃
        # self._last_recognized_posture = None  # 已废弃

    def on_button_click(self, x, y, button, pressed):  # 鼠标点击事件处理方法
        try:
            if button == mouse.Button.left:  # 如果是左键点击
                self.PC.mouse_one = pressed  # 更新鼠标状态
                if pressed and self.PC.StartFire:  # 如果按下且开镜状态为True
                    self.mouseClicked.emit('l', (f"开始第{self.count}次压枪",))  # 发送压枪信号
                    Thread(target=self.PC.FIRE_Start, args=(self.mouseClicked.emit,)).start()  # 启动压枪线程
                    self.count += 1  # 计数器加1
            elif button == mouse.Button.right:  # 如果是右键点击
                # ═══ 检测 Alt + 右键 组合键用于切换双模式倍镜 ═══
                # 使用 Windows API 实时检测 Alt 键状态，更可靠
                alt_pressed = is_alt_pressed()
                
                if pressed and alt_pressed:
                    # Alt + 右键按下：切换双模式倍镜
                    new_mode = self.PC.toggle_duobei_scope()
                    if new_mode:
                        mode_name = "高倍" if new_mode == "duobei4" else "低倍"
                        self.mouseClicked.emit('l', (f"倍镜已切换到{mode_name}模式",))
                        # 触发 UI 刷新，显示正确的倍镜模式
                        self.mouseClicked.emit('g', (None,))
                    return  # 不执行后续的右键逻辑
                
                if not self.PC.TabKey:  # 如果Tab键未按下
                    if self.PC.RightClick:  # 如果右键开镜模式为True
                        if pressed:  # 如果按下
                            self.PC.StartFire = True  # 设置开镜状态为True
                            
                            # ═══ 开镜后自动识别姿势 ═══
                            if self.PC.posture_roi:  # 如果配置了姿势 ROI
                                Thread(target=self._auto_recognize_posture).start()
                            
                            if self.PC.firstPerson:
                                self.mouseClicked.emit('p', (self.PC.Current_posture,))  # 同步当前手动姿态到 UI
                        else:  # 如果释放
                            self.PC.StartFire = False  # 设置开镜状态为False
                    else:  # 如果右键开镜模式为False
                        if pressed:  # 如果按下
                            Thread(target=self.PC.IF_Open_Lens).start()  # 启动开镜线程
                    
                    # ✅ 每次都发送开镜状态信号，确保 UI 更新
                    self.mouseClicked.emit('s', (self.PC.StartFire,))
            elif button == mouse.Button.x1 or button == mouse.Button.x2:  # 如果是X1或X2键点击
                if pressed:  # 如果按下
                    self.PC.StartFire = False  # 设置开镜状态为False
                else:  # 如果释放
                    self.PC.StartFire = False  # 设置开镜状态为False
                self.mouseClicked.emit('s', (self.PC.StartFire,))  # 发送开镜状态信号
        except Exception as e:
            # ✅ 异常处理：记录错误但不中断监听
            import logging
            logger = logging.getLogger(__name__)
            logger.error(f"鼠标事件处理异常: {e}", exc_info=True)
            self.mouseClicked.emit('l', (f"⚠️ 鼠标事件异常: {e}",))

    def run(self):  # 线程运行方法
        self.rerun()  # 调用rerun方法

    def rerun(self):  # 重新启动鼠标监听
        try:
            # 如果已有监听器，先停止
            if self.listener:
                try:
                    self.listener.stop()
                except:
                    pass
            
            # 创建新的监听器
            self.listener = mouse.Listener(on_click=self.on_button_click)
            self.listener.start()
            self.mouseClicked.emit("l", ("✅ 鼠标监听已启动...",))
        except Exception as e:
            import logging
            logger = logging.getLogger(__name__)
            logger.error(f"鼠标监听启动失败: {e}", exc_info=True)
            self.mouseClicked.emit("l", (f"❌ 鼠标监听启动失败: {e}",))
    
    def _auto_recognize_posture(self):
        """
        自动识别姿势（在独立线程中执行）
        ✅ 每次开镜都强制识别和更新，不跳过
        """
        import time
        
        # 等待开镜动画完成
        time.sleep(0.3)
        
        # 使用调试模式截取并识别姿势
        posture = self.PC.capture_and_recognize_posture(debug=self.debug_mode)
        
        if posture:
            # ✅ 每次都更新姿势，不跳过
            self.PC.Change_posture(posture)
            self.mouseClicked.emit('p', (posture,))
            mode_name = {"None": "站立", "c": "蹲下", "z": "趴下"}.get(posture, "未知")
            self.mouseClicked.emit('l', (f"🎯 姿势识别: {mode_name}",))
        else:
            if self.debug_mode:
                self.mouseClicked.emit('l', ("⚠️ 姿势识别失败，请查看 logs/posture_debug/ 目录中的截图",))

    def stop_listener(self):  # 停止鼠标监听
        if self.listener:  # 如果鼠标监听器存在
            self.listener.stop()  # 停止鼠标监听器
            self.listener = None  # 清除鼠标监听器
            self.mouseClicked.emit("l", ("鼠标监听已结束...",))  # 发送停止信号