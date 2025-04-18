from threading import Thread  # 导入线程模块，用于多线程操作
from PyQt5.QtCore import QThread, pyqtSignal  # 导入PyQt5的线程和信号模块
from pynput import keyboard  # 导入pynput键盘模块，用于监听键盘事件
from pynput.keyboard import Key  # 导入pynput键盘模块中的Key类，用于处理特殊按键

class AppMainKeyListener(QThread):  # 定义键盘监听器类，继承自QThread
    keyInfo = pyqtSignal(str, tuple)  # 定义信号，用于发送键盘事件信息

    def __init__(self, PCdata):  # 初始化方法
        super().__init__()  # 调用父类的初始化方法
        self.KeyHook = None  # 初始化键盘钩子
        self.PC = PCdata  # 保存PC对象引用

    def on_key_pressed(self, key):  # 键盘按下事件处理方法
        Keys = str(key.name if isinstance(key, Key) else key.char)  # 获取按键名称
        if Keys == "tab":  # 如果按下Tab键
            self.PC.StartFire = False  # 设置开镜状态为False
            Thread(target=self.PC.recognize_all_guns_info, args=(self.keyInfo.emit,)).start()  # 启动枪械识别线程
            self.keyInfo.emit('s', (self.PC.StartFire,))  # 发送开镜状态信号
        elif Keys in "12":  # 如果按下1或2键
            self.PC.StartFire = False  # 设置开镜状态为False
            self.keyInfo.emit('s', (self.PC.StartFire,))  # 发送开镜状态信号
            self.PC.Change_firearms(Keys)  # 更改枪械
            self.keyInfo.emit('e', (self.PC.Current_firearms,))  # 发送枪械信息信号
        elif Keys in "345gx":  # 如果按下3、4、5、g或x键
            self.PC.StartFire = False  # 设置开镜状态为False
            self.keyInfo.emit('s', (self.PC.StartFire,))  # 发送开镜状态信号
        elif Keys in "~":  # 如果按下波浪号键
            self.PC.StartFire = False  # 设置开镜状态为False
            self.keyInfo.emit('s', (self.PC.StartFire,))  # 发送开镜状态信号
        elif Keys in "zc" or Keys == "space":  # 如果按下z、c或空格键
            self.PC.Change_posture(Keys)  # 更改姿态
            self.keyInfo.emit('p', (self.PC.Current_posture,))  # 发送姿态信息信号
        elif Keys == "insert":  # 如果按下Insert键
            self.PC.reduction_data()  # 重置数据
            self.keyInfo.emit('c', (None,))  # 发送重置数据信号
        elif Keys == "home":  # 如果按下Home键
            self.keyInfo.emit('t', (None,))  # 发送切换窗口信号
        elif Keys == "ctrl_l":  # 如果按下左Ctrl键
            self.PC.Current_posture = "c"  # 设置姿态为趴下
            self.keyInfo.emit('p', (self.PC.Current_posture,))  # 发送姿态信息信号
        elif Keys == "shift":  # 如果按下Shift键
            self.PC.on_shift_pressed()  # 处理Shift按下事件
            self.keyInfo.emit('e', (self.PC.Current_firearms,))  # 发送枪械信息信号

    def on_key_release(self, key):  # 键盘释放事件处理方法
        Keys = str(key.name if isinstance(key, Key) else key.char)  # 获取按键名称
        if Keys == "ctrl_l":  # 如果释放左Ctrl键
            self.PC.Current_posture = "None"  # 设置姿态为站立
            self.keyInfo.emit('p', (self.PC.Current_posture,))  # 发送姿态信息信号
        elif Keys == "shift":  # 如果释放Shift键
            self.PC.on_shift_released()  # 处理Shift释放事件
            self.keyInfo.emit('e', (self.PC.Current_firearms,))  # 发送枪械信息信号

    def run(self):  # 线程运行方法
        self.rerun()  # 调用rerun方法

    def rerun(self):  # 重新启动键盘监听
        self.KeyHook = keyboard.Listener(on_press=self.on_key_pressed, on_release=self.on_key_release)  # 创建键盘监听器
        self.KeyHook.start()  # 启动键盘监听器
        self.keyInfo.emit('l', ("键盘监听已启动...",))  # 发送启动信号

    def stop_listener(self):  # 停止键盘监听
        if self.KeyHook:  # 如果键盘钩子存在
            self.KeyHook.stop()  # 停止键盘监听器
            self.KeyHook = None  # 清除键盘钩子
            self.keyInfo.emit('l', ("键盘监听已停止.....",))  # 发送停止信号