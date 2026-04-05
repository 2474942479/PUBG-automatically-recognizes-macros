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

class AppMainMouseListener(QThread):  # 定义鼠标监听器类，继承自QThread
    mouseClicked = pyqtSignal(str, tuple)  # 定义信号，用于发送鼠标事件信息

    def __init__(self, PCdata):  # 初始化方法
        super().__init__()  # 调用父类的初始化方法
        self.listener = None  # 初始化鼠标监听器
        self.data = []  # 初始化数据列表
        self.PC = PCdata  # 保存PC对象引用
        self.count = 1  # 初始化计数器

    def on_button_click(self, x, y, button, pressed):  # 鼠标点击事件处理方法
        if button == mouse.Button.left:  # 如果是左键点击
            self.PC.mouse_one = pressed  # 更新鼠标状态
            if pressed and self.PC.StartFire:  # 如果按下且开镜状态为True
                self.mouseClicked.emit('l', (f"开始第{self.count}次压枪",))  # 发送压枪信号
                Thread(target=self.PC.FIRE_Start, args=(self.mouseClicked.emit,)).start()  # 启动压枪线程
                self.count += 1  # 计数器加1
        elif button == mouse.Button.right:  # 如果是右键点击
            if not self.PC.TabKey:  # 如果Tab键未按下
                if self.PC.RightClick:  # 如果右键开镜模式为True
                    if pressed:  # 如果按下
                        self.PC.StartFire = True  # 设置开镜状态为True
                        # 第一人称识别姿势
                        if self.PC.firstPerson:
                            Thread(target=self.PC.recognize_zishi_info).start()
                            self.mouseClicked.emit('p', (self.PC.Current_posture,))  # 发送姿态信息信号
                    else:  # 如果释放
                        self.PC.StartFire = False  # 设置开镜状态为False
                else:  # 如果右键开镜模式为False
                    if pressed:  # 如果按下
                        Thread(target=self.PC.IF_Open_Lens).start()  # 启动开镜线程
                self.mouseClicked.emit('s', (self.PC.StartFire,))  # 发送开镜状态信号
        elif button == mouse.Button.x1 or button == mouse.Button.x2:  # 如果是X1或X2键点击
            if pressed:  # 如果按下
                self.PC.StartFire = False  # 设置开镜状态为False
            else:  # 如果释放
                self.PC.StartFire = False  # 设置开镜状态为False
            self.mouseClicked.emit('s', (self.PC.StartFire,))  # 发送开镜状态信号

    def run(self):  # 线程运行方法
        self.rerun()  # 调用rerun方法

    def rerun(self):  # 重新启动鼠标监听
        self.listener = mouse.Listener(on_click=self.on_button_click)  # 创建鼠标监听器
        self.listener.start()  # 启动鼠标监听器
        self.mouseClicked.emit("l", ("鼠标监听已启动...",))  # 发送启动信号

    def stop_listener(self):  # 停止鼠标监听
        if self.listener:  # 如果鼠标监听器存在
            self.listener.stop()  # 停止鼠标监听器
            self.listener = None  # 清除鼠标监听器
            self.mouseClicked.emit("l", ("鼠标监听已结束...",))  # 发送停止信号