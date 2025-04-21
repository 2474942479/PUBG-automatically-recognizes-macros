import sys
import os
from PyQt5 import QtCore, QtGui, QtWidgets

import Process
from modern_ui import Ui_ModernPUBG
from ingame_display import IngameDisplayManager

class ModernPUBGApp(QtWidgets.QWidget):
    def __init__(self):
        super().__init__()
        self.ui = Ui_ModernPUBG()
        self.ui.setupUi(self)
        
        # 初始化游戏内显示管理器
        self.display_manager = IngameDisplayManager()
        self.display_manager.initialize()
        
        # 连接信号
        self.connectSignals()
        
        # 设置窗口标题
        self.setWindowTitle("PUBG 自动识别宏 - 现代界面")
        
    def connectSignals(self):
        # 连接游戏内显示相关信号
        self.ui.toggleDisplayHotkey.textChanged.connect(self.updateDisplayHotkey)
        self.ui.changeToggleDisplayHotkeyBtn.clicked.connect(self.changeDisplayHotkey)
        
        # 测试游戏内显示功能
        self.ui.startBtn.clicked.connect(self.testIngameDisplay)
        self.ui.stopBtn.clicked.connect(self.stopIngameDisplay)
        
    def updateDisplayHotkey(self, text):
        if text:
            self.display_manager.config.hotkey = text
            
    def changeDisplayHotkey(self):
        # 实际应用中应该有一个对话框来捕获按键
        self.ui.toggleDisplayHotkey.setText("F10")
        self.updateDisplayHotkey("F10")
        
    def testIngameDisplay(self):
        # 更新武器信息
        weapon_name = "M416" if not self.ui.firstWeaponName.text() else self.ui.firstWeaponName.text()
        
        attachments = []
        if self.ui.firstWeaponScope.text():
            attachments.append(self.ui.firstWeaponScope.text())
        if self.ui.firstWeaponMuzzle.text():
            attachments.append(self.ui.firstWeaponMuzzle.text())
        if self.ui.firstWeaponGrip.text():
            attachments.append(self.ui.firstWeaponGrip.text())
        if self.ui.firstWeaponButt.text():
            attachments.append(self.ui.firstWeaponButt.text())
            
        if not attachments:
            attachments = ["红点", "补偿器", "直角握把", "战术枪托"]
            
        recoil_enabled = True
        recoil_effect = self.ui.recoilSlider.value()
        
        self.display_manager.updateWeaponInfo(
            weapon_name, 
            attachments, 
            recoil_enabled, 
            recoil_effect
        )
        
        # 更新专业信息
        pose = "站立"
        if self.ui.squatRadio.isChecked():
            pose = "下蹲"
        elif self.ui.proneRadio.isChecked():
            pose = "趴下"
            
        self.display_manager.updateProfessionalInfo(
            41,  # 伤害
            0.086,  # 射速
            "高",  # 精度
            400,  # 有效射程
            95,  # 识别可信度
            pose,  # 姿态
            1.5,  # 压枪参数
            45  # 系统延迟
        )
        
        # 显示游戏内窗口
        self.display_manager.show()
        
        # 更新UI状态
        self.ui.logOutput.append("游戏内显示已启动")
        
    def stopIngameDisplay(self):
        # 隐藏游戏内窗口
        self.display_manager.hide()
        
        # 更新UI状态
        self.ui.logOutput.append("游戏内显示已停止")
        
    def closeEvent(self, event):
        # 确保关闭主窗口时也关闭游戏内显示
        self.display_manager.hide()
        event.accept()

if __name__ == "__main__":
    app = QtWidgets.QApplication(sys.argv)
    PC = Process.ProcessClass()
    window = ModernPUBGApp()
    window.show()
    sys.exit(app.exec_())
