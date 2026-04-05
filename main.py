import sys
from data import fire_data
from core import process as Process
from PyQt5.QtCore import QThread, Qt, pyqtSignal, QEvent
from PyQt5.QtWidgets import QApplication, QWidget, QMessageBox, QMainWindow
from ui.pubg_ui import Ui_PUBG
from input.mouse_listener import AppMainMouseListener
from input.key_listener import AppMainKeyListener
from ui.overlay_hud import GameHUD

class AppManager(QWidget, Ui_PUBG):  # 定义主应用管理类，继承自QWidget和UI类
    def __init__(self):  # 初始化方法
        super().__init__()  # 调用父类的初始化方法
        self.isHidden = None  # 初始化窗口隐藏状态
        self.my_mouse_thread = None  # 初始化鼠标线程
        self.my_key_thread = None  # 初始化键盘线程
        self.pauses = True  # 初始化暂停状态
        self.TextValue = {'无': 'none', '红点': 'hongdian', '全息': "quanxi", '2倍': '2bei',  # 定义文本值映射
                          '3倍': '3bei', '4倍': "4bei", '6倍': '6bei', '8倍': '8bei', '15倍': '15bei', 'shift': 'shift'}
        self.init_ui()  # 调用初始化UI方法

    def init_ui(self):  # 初始化UI方法
        self.setupUi(self)  # 设置UI
        self.setWindowFlags(Qt.WindowStaysOnTopHint)  # 设置窗口始终置顶
        self.Init_UI_LOG("程序初始化中.....")  # 初始化日志
        self.Init_UI_LOG(PC.ghub_device_info)  # 初始化日志，显示设备信息
        # self.Init_UI_Win()  # 初始化窗口信息
        self.Init_UI_Equip(PC.Current_firearms)  # 初始化枪械信息
        self.Init_UI_Posture(PC.Current_posture)  # 初始化姿态信息
        self.Init_UI_ScopeMode(PC.RightClick)  # 初始化开镜模式
        self.Init_UI_ScopeOpen(PC.StartFire)  # 初始化是否开镜
        self.Init_UI_GunsData()  # 初始化枪械数据
        self.ResolutionSelect.setCurrentText(PC.Monitor)  # 设置分辨率选择
        self.Init_UI_Sensitivity()  # 初始化灵敏度
        self.Init_UI_Btn()  # 初始化按钮
        self.Init_UI_LOG("程序初始化完成.....")  # 初始化完成日志
        # 初始化 HUD 浮窗
        self._hud = GameHUD(PC)
    
    def Init_UI_Btn(self):  # 初始化按钮事件
        self.Startbtn.clicked.connect(self.start)  # 绑定开始按钮事件
        self.Stopbtn.clicked.connect(self.stop)  # 绑定停止按钮事件
        self.Pausebtn.clicked.connect(self.pause)  # 绑定暂停按钮事件
        self.ResolutionBtn.clicked.connect(self.Save_Config_Resolution)  # 绑定分辨率保存按钮事件
        self.SensitivityBtn.clicked.connect(self.Save_Config_Sensitivity)  # 绑定灵敏度保存按钮事件
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
        if Open:  # 如果开镜
            self.OpenScope.setChecked(True)  # 设置开镜按钮选中
        else:  # 如果不开镜
            self.CloseScope.setChecked(True)  # 设置关镜按钮选中

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
        for idx, result in enumerate(results, start=1):  # 遍历结果
            if result:  # 如果有结果
                self.__getattribute__(f"Name{idx}Name").setText(self.Get_GUNS_CH(result["Name"], "Name"))  # 设置枪械名称
                self.__getattribute__(f"Scope{idx}Name").setText(self.Get_GUNS_CH(result["Scope"], "Scope"))  # 设置镜类型
                self.__getattribute__(f"Muzzle{idx}Name").setText(self.Get_GUNS_CH(result["Muzzle"], "Muzzle"))  # 设置枪口类型
                self.__getattribute__(f"Grip{idx}Name").setText(self.Get_GUNS_CH(result["Grip"], "Grip"))  # 设置握把类型
                self.__getattribute__(f"Butt{idx}Name").setText(self.Get_GUNS_CH(result["Stock"], "Stock"))  # 设置枪托类型
    
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
    
    def Change_Sensitivity_label(self, SelectValue):  # 更新灵敏度标签
        Text = self.TextValue  # 获取文本值映射
        Select = PC.ScopeData.get(Text[SelectValue], '1')  # 获取灵敏度值
        self.SensitivityText.setText(str(Select))  # 设置灵敏度标签
    
    def Save_Config_Resolution(self):  # 保存分辨率设置
        PC.Monitor = self.ResolutionSelect.currentText()  # 获取当前选择的分辨率
        PC.save_config_data(True, PC.Monitor)  # 保存配置
        self.message_Info("保存分辨率设置成功！！")  # 显示成功消息
    
    def Save_Config_Sensitivity(self):  # 保存灵敏度设置
        SensitivityText = self.SensitivityText.text()  # 获取灵敏度输入
        SensitivityText = self.is_numeric(SensitivityText)  # 检查是否为数字
        if not SensitivityText:  # 如果不是数字
            self.message_Info("输入框只能输入数字！！", '警告')  # 显示警告
            return
        
        SensitivitySelect = self.SensitivitySelect.currentText()  # 获取当前选择的灵敏度类型
        Text = self.TextValue[SensitivitySelect]  # 获取文本值
        PC.ScopeData[Text] = SensitivityText  # 更新灵敏度数据
        PC.save_config_data(0, PC.ScopeData)  # 保存配置
        self.message_Info("保存灵敏度设置成功！！")  # 显示成功消息
    
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
        self.my_key_thread.start()  # 启动键盘监听线程
        self.my_mouse_thread.start()  # 启动鼠标监听线程
        
        self.my_key_thread.keyInfo.connect(self.onKeyPressed)  # 绑定键盘事件
        self.my_mouse_thread.mouseClicked.connect(self.onKeyPressed)  # 绑定鼠标事件
        
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

if __name__ == '__main__':  # 程序入口
    app = QApplication([])  # 创建应用程序
    PC = Process.ProcessClass()  # 创建核心处理类实例
    Main = AppManager()  # 创建主应用管理类实例
    # 展示窗口
    Main.show()  # 显示窗口
    sys.exit(app.exec_())  # 运行应用程序并退出
