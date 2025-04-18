import sys
import os
from PyQt5 import QtCore, QtGui, QtWidgets
from PyQt5.QtCore import Qt, QPoint, QTimer
from PyQt5.QtGui import QPainter, QColor, QPen, QFont, QBrush

class IngameDisplayConfig:
    def __init__(self):
        self.display_mode = "simple"  # "simple", "standard", "professional"
        self.position = "top_right"   # "top_left", "top_right", "bottom_left", "bottom_right"
        self.opacity = 0.8            # 0.1 to 1.0
        self.show_display = True
        self.hotkey = "F10"
        
        # 武器信息
        self.weapon_name = ""
        self.weapon_attachments = []
        self.recoil_enabled = False
        self.recoil_effect = 0
        
        # 专业模式额外信息
        self.weapon_damage = 0
        self.weapon_fire_rate = 0
        self.weapon_accuracy = ""
        self.weapon_range = 0
        self.recognition_confidence = 0
        self.current_pose = "站立"
        self.recoil_param = 0
        self.system_delay = 0

class IngameDisplayWindow(QtWidgets.QWidget):
    def __init__(self, config=None):
        super().__init__()
        
        if config is None:
            self.config = IngameDisplayConfig()
        else:
            self.config = config
            
        self.setWindowFlags(
            Qt.FramelessWindowHint | 
            Qt.WindowStaysOnTopHint | 
            Qt.Tool
        )
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setStyleSheet("background-color: transparent;")
        
        # 设置窗口大小
        self.updateSize()
        
        # 设置窗口位置
        self.updatePosition()
        
        # 设置透明度
        self.setWindowOpacity(self.config.opacity)
        
        # 拖动相关变量
        self.dragging = False
        self.drag_position = QPoint()
        
        # 定时刷新
        self.refresh_timer = QTimer(self)
        self.refresh_timer.timeout.connect(self.update)
        self.refresh_timer.start(100)  # 100ms刷新一次
        
    def updateSize(self):
        if self.config.display_mode == "simple":
            self.setFixedSize(250, 120)
        elif self.config.display_mode == "standard":
            self.setFixedSize(300, 180)
        else:  # professional
            self.setFixedSize(350, 250)
            
    def updatePosition(self):
        screen = QtWidgets.QDesktopWidget().screenGeometry()
        
        if self.config.position == "top_left":
            self.move(20, 20)
        elif self.config.position == "top_right":
            self.move(screen.width() - self.width() - 20, 20)
        elif self.config.position == "bottom_left":
            self.move(20, screen.height() - self.height() - 20)
        else:  # bottom_right
            self.move(screen.width() - self.width() - 20, screen.height() - self.height() - 20)
            
    def setDisplayMode(self, mode):
        if mode in ["simple", "standard", "professional"]:
            self.config.display_mode = mode
            self.updateSize()
            self.updatePosition()
            self.update()
            
    def setPosition(self, position):
        if position in ["top_left", "top_right", "bottom_left", "bottom_right"]:
            self.config.position = position
            self.updatePosition()
            
    def setOpacity(self, opacity):
        if 0.1 <= opacity <= 1.0:
            self.config.opacity = opacity
            self.setWindowOpacity(opacity)
            
    def toggleDisplay(self):
        self.config.show_display = not self.config.show_display
        self.setVisible(self.config.show_display)
        
    def updateWeaponInfo(self, name, attachments, recoil_enabled, recoil_effect=0):
        self.config.weapon_name = name
        self.config.weapon_attachments = attachments
        self.config.recoil_enabled = recoil_enabled
        self.config.recoil_effect = recoil_effect
        self.update()
        
    def updateProfessionalInfo(self, damage, fire_rate, accuracy, weapon_range, confidence, pose, recoil_param, delay):
        self.config.weapon_damage = damage
        self.config.weapon_fire_rate = fire_rate
        self.config.weapon_accuracy = accuracy
        self.config.weapon_range = weapon_range
        self.config.recognition_confidence = confidence
        self.config.current_pose = pose
        self.config.recoil_param = recoil_param
        self.config.system_delay = delay
        self.update()
        
    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.dragging = True
            self.drag_position = event.globalPos() - self.frameGeometry().topLeft()
            event.accept()
            
    def mouseMoveEvent(self, event):
        if event.buttons() == Qt.LeftButton and self.dragging:
            self.move(event.globalPos() - self.drag_position)
            event.accept()
            
    def mouseReleaseEvent(self, event):
        self.dragging = False
        
    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        
        # 绘制背景
        painter.setPen(Qt.NoPen)
        painter.setBrush(QBrush(QColor(0, 0, 0, 180)))
        painter.drawRoundedRect(self.rect(), 6, 6)
        
        # 绘制标题栏
        title_height = 30
        title_rect = QtCore.QRect(0, 0, self.width(), title_height)
        painter.setPen(Qt.NoPen)
        painter.setBrush(QBrush(QColor(40, 40, 40, 200)))
        painter.drawRoundedRect(title_rect, 6, 6)
        
        # 绘制标题
        painter.setPen(QPen(QColor(255, 255, 255)))
        painter.setFont(QFont("Microsoft YaHei", 10, QFont.Bold))
        
        title_text = "武器信息"
        if self.config.display_mode != "simple":
            title_text += f" ({self.config.display_mode}模式)"
            
        painter.drawText(title_rect, Qt.AlignCenter, title_text)
        
        # 绘制控制按钮
        button_size = 16
        button_margin = 5
        
        # 最小化按钮
        min_button_rect = QtCore.QRect(
            self.width() - 2 * button_size - 2 * button_margin, 
            (title_height - button_size) // 2, 
            button_size, 
            button_size
        )
        painter.setPen(QPen(QColor(200, 200, 200)))
        painter.setBrush(QBrush(QColor(60, 60, 60, 200)))
        painter.drawRect(min_button_rect)
        painter.drawLine(
            min_button_rect.left() + 4,
            min_button_rect.center().y(),
            min_button_rect.right() - 4,
            min_button_rect.center().y()
        )
        
        # 关闭按钮
        close_button_rect = QtCore.QRect(
            self.width() - button_size - button_margin, 
            (title_height - button_size) // 2, 
            button_size, 
            button_size
        )
        painter.setPen(QPen(QColor(200, 200, 200)))
        painter.setBrush(QBrush(QColor(60, 60, 60, 200)))
        painter.drawRect(close_button_rect)
        painter.drawLine(
            close_button_rect.left() + 4,
            close_button_rect.top() + 4,
            close_button_rect.right() - 4,
            close_button_rect.bottom() - 4
        )
        painter.drawLine(
            close_button_rect.left() + 4,
            close_button_rect.bottom() - 4,
            close_button_rect.right() - 4,
            close_button_rect.top() + 4
        )
        
        # 绘制内容
        content_y = title_height + 10
        
        # 绘制武器名称
        if self.config.weapon_name:
            painter.setPen(QPen(QColor(52, 152, 219)))
            painter.setFont(QFont("Microsoft YaHei", 12, QFont.Bold))
            painter.drawText(15, content_y, self.config.weapon_name)
            content_y += 25
        
        # 简洁模式只显示武器名称和配件
        if self.config.display_mode == "simple":
            # 绘制配件
            if self.config.weapon_attachments:
                painter.setPen(QPen(QColor(255, 255, 255)))
                painter.setFont(QFont("Microsoft YaHei", 9))
                
                attachment_x = 15
                attachment_y = content_y
                
                for attachment in self.config.weapon_attachments:
                    attachment_rect = QtCore.QRect(
                        attachment_x, 
                        attachment_y, 
                        painter.fontMetrics().width(attachment) + 10, 
                        20
                    )
                    
                    painter.setPen(Qt.NoPen)
                    painter.setBrush(QBrush(QColor(60, 60, 60, 180)))
                    painter.drawRoundedRect(attachment_rect, 3, 3)
                    
                    painter.setPen(QPen(QColor(255, 255, 255)))
                    painter.drawText(
                        attachment_rect, 
                        Qt.AlignCenter, 
                        attachment
                    )
                    
                    attachment_x += attachment_rect.width() + 5
                    if attachment_x > self.width() - 20:
                        attachment_x = 15
                        attachment_y += 25
                        
                content_y = attachment_y + 30
        
        # 标准模式显示武器属性和配件
        elif self.config.display_mode == "standard":
            # 绘制武器属性
            if self.config.weapon_damage > 0:
                painter.setPen(QPen(QColor(255, 255, 255)))
                painter.setFont(QFont("Microsoft YaHei", 9))
                
                # 伤害
                damage_text = f"伤害: {self.config.weapon_damage}"
                painter.drawText(15, content_y, damage_text)
                
                # 射速
                fire_rate_text = f"射速: {self.config.weapon_fire_rate}s"
                painter.drawText(100, content_y, fire_rate_text)
                
                # 精度
                accuracy_text = f"精度: {self.config.weapon_accuracy}"
                painter.drawText(200, content_y, accuracy_text)
                
                content_y += 25
            
            # 绘制配件
            if self.config.weapon_attachments:
                painter.setPen(QPen(QColor(255, 255, 255)))
                painter.setFont(QFont("Microsoft YaHei", 9))
                
                attachment_x = 15
                attachment_y = content_y
                
                for attachment in self.config.weapon_attachments:
                    attachment_rect = QtCore.QRect(
                        attachment_x, 
                        attachment_y, 
                        painter.fontMetrics().width(attachment) + 10, 
                        20
                    )
                    
                    painter.setPen(Qt.NoPen)
                    painter.setBrush(QBrush(QColor(60, 60, 60, 180)))
                    painter.drawRoundedRect(attachment_rect, 3, 3)
                    
                    painter.setPen(QPen(QColor(255, 255, 255)))
                    painter.drawText(
                        attachment_rect, 
                        Qt.AlignCenter, 
                        attachment
                    )
                    
                    attachment_x += attachment_rect.width() + 5
                    if attachment_x > self.width() - 20:
                        attachment_x = 15
                        attachment_y += 25
                        
                content_y = attachment_y + 30
        
        # 专业模式显示所有信息
        else:
            # 绘制武器属性
            if self.config.weapon_damage > 0:
                painter.setPen(QPen(QColor(255, 255, 255)))
                painter.setFont(QFont("Microsoft YaHei", 9))
                
                # 伤害
                damage_text = f"伤害: {self.config.weapon_damage}"
                painter.drawText(15, content_y, damage_text)
                
                # 射速
                fire_rate_text = f"射速: {self.config.weapon_fire_rate}s"
                painter.drawText(100, content_y, fire_rate_text)
                
                # 精度
                accuracy_text = f"精度: {self.config.weapon_accuracy}"
                painter.drawText(200, content_y, accuracy_text)
                
                content_y += 25
                
                # 有效射程和识别可信度
                range_text = f"有效射程: {self.config.weapon_range}m"
                confidence_text = f"识别可信度: {self.config.recognition_confidence}%"
                
                painter.drawText(15, content_y, range_text)
                painter.drawText(180, content_y, confidence_text)
                
                content_y += 25
            
            # 绘制配件
            if self.config.weapon_attachments:
                painter.setPen(QPen(QColor(255, 255, 255)))
                painter.setFont(QFont("Microsoft YaHei", 9))
                
                attachment_x = 15
                attachment_y = content_y
                
                for attachment in self.config.weapon_attachments:
                    attachment_rect = QtCore.QRect(
                        attachment_x, 
                        attachment_y, 
                        painter.fontMetrics().width(attachment) + 10, 
                        20
                    )
                    
                    painter.setPen(Qt.NoPen)
                    painter.setBrush(QBrush(QColor(60, 60, 60, 180)))
                    painter.drawRoundedRect(attachment_rect, 3, 3)
                    
                    painter.setPen(QPen(QColor(255, 255, 255)))
                    painter.drawText(
                        attachment_rect, 
                        Qt.AlignCenter, 
                        attachment
                    )
                    
                    attachment_x += attachment_rect.width() + 5
                    if attachment_x > self.width() - 20:
                        attachment_x = 15
                        attachment_y += 25
                        
                content_y = attachment_y + 30
                
                # 推荐配件
                painter.setPen(QPen(QColor(255, 255, 255)))
                painter.setFont(QFont("Microsoft YaHei", 9))
                painter.drawText(15, content_y, "推荐配件: 全息, 消音器")
                
                content_y += 25
            
            # 绘制姿态和压枪参数
            painter.setPen(QPen(QColor(255, 255, 255)))
            painter.setFont(QFont("Microsoft YaHei", 9))
            
            pose_text = f"当前姿态: {self.config.current_pose}"
            param_text = f"压枪参数: {self.config.recoil_param}x"
            
            painter.drawText(15, content_y, pose_text)
            painter.drawText(180, content_y, param_text)
            
            content_y += 25
            
            # 绘制压枪效果进度条
            progress_rect = QtCore.QRect(15, content_y, self.width() - 30, 5)
            
            painter.setPen(Qt.NoPen)
            painter.setBrush(QBrush(QColor(60, 60, 60, 180)))
            painter.drawRoundedRect(progress_rect, 2, 2)
            
            if self.config.recoil_effect > 0:
                effect_width = int(progress_rect.width() * self.config.recoil_effect / 100)
                effect_rect = QtCore.QRect(
                    progress_rect.left(), 
                    progress_rect.top(), 
                    effect_width, 
                    progress_rect.height()
                )
                
                painter.setBrush(QBrush(QColor(46, 204, 113)))
                painter.drawRoundedRect(effect_rect, 2, 2)
                
            content_y += 15
            
            # 绘制压枪效果和系统延迟
            painter.setPen(QPen(QColor(255, 255, 255)))
            painter.setFont(QFont("Microsoft YaHei", 8))
            
            effect_text = f"压枪效果: {self.config.recoil_effect}%"
            delay_text = f"系统延迟: {self.config.system_delay}ms"
            
            painter.drawText(15, content_y, effect_text)
            painter.drawText(self.width() - 15 - painter.fontMetrics().width(delay_text), content_y, delay_text)
            
            content_y += 20
        
        # 绘制分隔线
        painter.setPen(QPen(QColor(100, 100, 100, 150)))
        painter.drawLine(15, content_y, self.width() - 15, content_y)
        
        content_y += 15
        
        # 绘制压枪状态
        status_dot_size = 10
        status_dot_rect = QtCore.QRect(15, content_y - status_dot_size // 2, status_dot_size, status_dot_size)
        
        painter.setPen(Qt.NoPen)
        if self.config.recoil_enabled:
            painter.setBrush(QBrush(QColor(46, 204, 113)))
        else:
            painter.setBrush(QBrush(QColor(231, 76, 60)))
            
        painter.drawEllipse(status_dot_rect)
        
        painter.setPen(QPen(QColor(255, 255, 255)))
        painter.setFont(QFont("Microsoft YaHei", 9))
        
        status_text = "压枪已启用" if self.config.recoil_enabled else "压枪已禁用"
        if self.config.display_mode == "standard" and self.config.recoil_enabled:
            status_text += f" (效果: {self.config.recoil_effect}%)"
            
        painter.drawText(30, content_y + 5, status_text)
        
        # 绘制快捷键提示
        content_y = self.height() - 15
        
        painter.setPen(QPen(QColor(180, 180, 180)))
        painter.setFont(QFont("Microsoft YaHei", 8))
        
        hotkey_text = f"按 [{self.config.hotkey}] 隐藏/显示此窗口"
        if self.config.display_mode != "simple":
            hotkey_text += " | 按 [F11] 切换显示模式"
            
        if self.config.display_mode == "professional":
            hotkey_text += " | 按 [F12] 设置"
            
        painter.drawText(
            QtCore.QRect(10, content_y - 15, self.width() - 20, 20),
            Qt.AlignCenter,
            hotkey_text
        )

class IngameDisplayManager:
    def __init__(self):
        self.config = IngameDisplayConfig()
        self.display_window = None
        
    def initialize(self):
        if self.display_window is None:
            self.display_window = IngameDisplayWindow(self.config)
            
    def show(self):
        if self.display_window:
            self.display_window.show()
            
    def hide(self):
        if self.display_window:
            self.display_window.hide()
            
    def toggleDisplay(self):
        if self.display_window:
            self.display_window.toggleDisplay()
            
    def setDisplayMode(self, mode):
        if self.display_window:
            self.display_window.setDisplayMode(mode)
            
    def setPosition(self, position):
        if self.display_window:
            self.display_window.setPosition(position)
            
    def setOpacity(self, opacity):
        if self.display_window:
            self.display_window.setOpacity(opacity)
            
    def updateWeaponInfo(self, name, attachments, recoil_enabled, recoil_effect=0):
        if self.display_window:
            self.display_window.updateWeaponInfo(name, attachments, recoil_enabled, recoil_effect)
            
    def updateProfessionalInfo(self, damage, fire_rate, accuracy, weapon_range, confidence, pose, recoil_param, delay):
        if self.display_window:
            self.display_window.updateProfessionalInfo(
                damage, fire_rate, accuracy, weapon_range, confidence, pose, recoil_param, delay
            )
            
    def cycleDisplayMode(self):
        if self.config.display_mode == "simple":
            self.setDisplayMode("standard")
        elif self.config.display_mode == "standard":
            self.setDisplayMode("professional")
        else:
            self.setDisplayMode("simple")

# 测试代码
if __name__ == "__main__":
    app = QtWidgets.QApplication(sys.argv)
    
    display_manager = IngameDisplayManager()
    display_manager.initialize()
    
    # 设置测试数据
    display_manager.updateWeaponInfo(
        "M416", 
        ["红点", "补偿器", "直角握把", "战术枪托"], 
        True, 
        92
    )
    
    display_manager.updateProfessionalInfo(
        41, 0.086, "高", 400, 95, "站立", 1.5, 45
    )
    
    display_manager.show()
    
    # 测试切换显示模式
    timer = QTimer()
    mode_index = 0
    
    def change_mode():
        global mode_index
        modes = ["simple", "standard", "professional"]
        display_manager.setDisplayMode(modes[mode_index])
        mode_index = (mode_index + 1) % len(modes)
    
    timer.timeout.connect(change_mode)
    timer.start(3000)  # 每3秒切换一次模式
    
    sys.exit(app.exec_())
