"""通用 ROI 配置对话框 - 集成到主 UI"""
import sys
import os
import json
import cv2
import numpy as np

from PyQt5.QtCore import Qt, QRect, QPoint, pyqtSignal
from PyQt5.QtWidgets import (
    QApplication, QDialog, QLabel, QMessageBox, QScrollArea, 
    QVBoxLayout, QHBoxLayout, QPushButton, QComboBox, QDialogButtonBox
)
from PyQt5.QtGui import QPixmap, QPainter, QPen, QColor, QFont, QImage

try:
    import mss
    HAS_MSS = True
except ImportError:
    HAS_MSS = False

try:
    from PIL import ImageGrab
    HAS_PIL = True
except ImportError:
    HAS_PIL = False


def capture_screenshot():
    """全屏截图，返回 QPixmap。"""
    if HAS_MSS:
        with mss.mss() as sct:
            monitor = sct.monitors[1]
            shot = sct.grab(monitor)
            img = QImage(
                shot.rgb, shot.width, shot.height,
                shot.width * 3, QImage.Format_RGB888
            ).rgbSwapped()
            return QPixmap.fromImage(img)
    elif HAS_PIL:
        pil_img = ImageGrab.grab()
        data = pil_img.tobytes("raw", "BGRX")
        img = QImage(data, pil_img.width, pil_img.height, QImage.Format_RGB32)
        return QPixmap.fromImage(img)
    else:
        raise RuntimeError("需要安装 mss 或 Pillow 才能截图")


class ROILabel(QLabel):
    """可在上面框选矩形的图片标签。"""

    def __init__(self, pixmap, parent=None):
        super().__init__(parent)
        self._base_pixmap = pixmap
        self._scale = 1.0
        self._current_rect = None
        self._current_roi = None  # 当前已配置的 ROI
        self._start_pos = None
        self._dragging_roi = False  # 是否正在拖动已有 ROI
        self._drag_offset = QPoint(0, 0)  # 拖动偏移量
        self._resizing_edge = None  # 正在调整大小的边: 'top', 'bottom', 'left', 'right'
        self._confidence_score = None  # 模板匹配置信度
        self._template_path = None  # 模板图片路径
        self.setMouseTracking(True)
        self._mouse_pos = QPoint(0, 0)
        self._update_display()

    def set_scale(self, scale):
        self._scale = max(0.2, min(3.0, scale))
        self._update_display()

    def _to_image_coords(self, widget_pos):
        """控件坐标 → 原图像素坐标。"""
        return QPoint(
            int(widget_pos.x() / self._scale),
            int(widget_pos.y() / self._scale)
        )
    
    def _get_edge_at_pos(self, pos, threshold=10):
        """
        检测鼠标位置是否在 ROI 框的边上
        :param pos: 图片坐标 QPoint
        :param threshold: 检测阈值（像素）
        :return: 'top', 'bottom', 'left', 'right' 或 None
        """
        if not self._current_roi:
            return None
        
        left, top, right, bottom = self._current_roi
        x, y = pos.x(), pos.y()
        
        # 检查是否在四个角附近（优先判断角）
        if abs(x - left) <= threshold and abs(y - top) <= threshold:
            return 'top-left'
        if abs(x - right) <= threshold and abs(y - top) <= threshold:
            return 'top-right'
        if abs(x - left) <= threshold and abs(y - bottom) <= threshold:
            return 'bottom-left'
        if abs(x - right) <= threshold and abs(y - bottom) <= threshold:
            return 'bottom-right'
        
        # 检查是否在四条边附近
        if abs(y - top) <= threshold and left <= x <= right:
            return 'top'
        if abs(y - bottom) <= threshold and left <= x <= right:
            return 'bottom'
        if abs(x - left) <= threshold and top <= y <= bottom:
            return 'left'
        if abs(x - right) <= threshold and top <= y <= bottom:
            return 'right'
        
        return None

    def calculate_confidence(self, roi_type, resolution):
        """
        计算当前 ROI 与模板的匹配置信度
        :param roi_type: ROI 类型 (如 'Name_1', 'Scope_1' 等)
        :param resolution: 分辨率字符串
        :return: 置信度分数 (0.0-1.0) 或 None
        """
        try:
            from core.paths import res_path
            
            # 获取当前 ROI 坐标
            if not self._current_roi:
                return None
            
            left, top, right, bottom = self._current_roi
            width = right - left
            height = bottom - top
            
            if width <= 0 or height <= 0:
                return None
            
            # 从截图中提取 ROI 区域
            roi_pixmap = self._base_pixmap.copy(
                int(left * self._scale),
                int(top * self._scale),
                int(width * self._scale),
                int(height * self._scale)
            )
            
            # 转换为 OpenCV 格式
            qimage = roi_pixmap.toImage()
            ptr = qimage.bits()
            ptr.setsize(qimage.byteCount())
            arr = np.array(ptr).reshape(qimage.height(), qimage.width(), 4)
            roi_cv = cv2.cvtColor(arr, cv2.COLOR_BGRA2BGR)
            roi_gray = cv2.cvtColor(roi_cv, cv2.COLOR_BGR2GRAY)
            
            # 根据 ROI 类型确定模板路径
            template_dir = None
            if 'Name' in roi_type:
                template_dir = res_path('_internal', 'data', 'firearms', 'Name')
            elif 'Scope' in roi_type:
                template_dir = res_path('_internal', 'data', 'firearms', 'Scope')
            elif 'Muzzle' in roi_type:
                template_dir = res_path('_internal', 'data', 'firearms', 'Muzzle')
            elif 'Grip' in roi_type:
                template_dir = res_path('_internal', 'data', 'firearms', 'Grip')
            elif 'Stock' in roi_type:
                template_dir = res_path('_internal', 'data', 'firearms', 'Stock')
            else:
                # 姿势识别没有模板
                return None
            
            if not template_dir or not os.path.exists(template_dir):
                return None
            
            # 遍历所有模板，找到最佳匹配
            best_score = 0.0
            best_template = None
            
            for template_file in os.listdir(template_dir):
                if not template_file.lower().endswith(('.png', '.jpg', '.jpeg')):
                    continue
                
                template_path = os.path.join(template_dir, template_file)
                template_img = cv2.imread(template_path, cv2.IMREAD_GRAYSCALE)
                
                if template_img is None:
                    continue
                
                # 使用模板匹配
                try:
                    result = cv2.matchTemplate(roi_gray, template_img, cv2.TM_CCOEFF_NORMED)
                    _, max_val, _, _ = cv2.minMaxLoc(result)
                    
                    if max_val > best_score:
                        best_score = max_val
                        best_template = template_file
                except Exception as e:
                    continue
            
            self._confidence_score = best_score
            self._template_path = best_template
            return best_score
            
        except Exception as e:
            import logging
            logger = logging.getLogger(__name__)
            logger.error(f"计算置信度失败: {e}")
            return None

    def _update_display(self):
        scaled = self._base_pixmap.scaled(
            int(self._base_pixmap.width() * self._scale),
            int(self._base_pixmap.height() * self._scale),
            Qt.KeepAspectRatio, Qt.SmoothTransformation
        )
        canvas = QPixmap(scaled)
        painter = QPainter(canvas)
        painter.setRenderHint(QPainter.Antialiasing)

        font = QFont("Microsoft YaHei", max(8, int(10 * self._scale)))
        painter.setFont(font)

        # 绘制提示文字
        hint_text = "请拖动鼠标框选区域"
        painter.setPen(QPen(QColor(255, 255, 255, 200)))
        painter.drawText(10, int(30 * self._scale), hint_text)

        # 绘制当前已配置的 ROI（如果有）
        if hasattr(self, '_current_roi') and self._current_roi:
            left, top, right, bottom = self._current_roi
            
            # 如果正在拖动或调整大小，使用实线；否则使用虚线
            pen = QPen(QColor(255, 165, 0, 220), 3)  # 橙色，更粗
            is_active = getattr(self, '_dragging_roi', False) or getattr(self, '_resizing_edge', None)
            if not is_active:
                pen.setStyle(Qt.DashLine)
            painter.setPen(pen)
            
            scaled_rect = QRect(
                int(left * self._scale),
                int(top * self._scale),
                int((right - left) * self._scale),
                int((bottom - top) * self._scale)
            )
            painter.drawRect(scaled_rect)
            
            # 添加标签
            painter.setPen(QPen(QColor(255, 165, 0)))
            label_text = "当前配置 (可拖动/调整)"
            painter.drawText(scaled_rect.topLeft() + QPoint(4, -4), label_text)
            
            # 显示置信度（如果有）
            if hasattr(self, '_confidence_score') and self._confidence_score is not None:
                conf_text = f"置信度: {self._confidence_score:.2%}"
                if self._template_path:
                    conf_text += f" ({self._template_path})"
                painter.setPen(QPen(QColor(0, 255, 0) if self._confidence_score > 0.7 else QColor(255, 165, 0)))
                painter.drawText(scaled_rect.bottomLeft() + QPoint(4, -4), conf_text)
            
            # 绘制8个调整手柄（四个角+四条边中点）
            handle_size = 6
            handles = [
                (left, top),  # 左上
                ((left + right) // 2, top),  # 上中
                (right, top),  # 右上
                (left, (top + bottom) // 2),  # 左中
                (right, (top + bottom) // 2),  # 右中
                (left, bottom),  # 左下
                ((left + right) // 2, bottom),  # 下中
                (right, bottom),  # 右下
            ]
            
            for hx, hy in handles:
                handle_rect = QRect(
                    int(hx * self._scale) - handle_size // 2,
                    int(hy * self._scale) - handle_size // 2,
                    handle_size,
                    handle_size
                )
                painter.fillRect(handle_rect, QColor(255, 165, 0))
                painter.setPen(QPen(Qt.white, 1))
                painter.drawRect(handle_rect)

        # 绘制正在框选的区域
        if self._current_rect:
            pen = QPen(QColor(0, 255, 0, 200), 3)
            painter.setPen(pen)
            scaled_rect = QRect(
                int(self._current_rect.x() * self._scale),
                int(self._current_rect.y() * self._scale),
                int(self._current_rect.width() * self._scale),
                int(self._current_rect.height() * self._scale)
            )
            painter.drawRect(scaled_rect)

            coord_text = (
                f"({self._current_rect.x()}, {self._current_rect.y()}, "
                f"{self._current_rect.right()}, {self._current_rect.bottom()}) "
                f"[{self._current_rect.width()}x{self._current_rect.height()}]"
            )
            painter.setPen(QPen(QColor(0, 255, 0)))
            painter.drawText(scaled_rect.bottomLeft() + QPoint(4, 20), coord_text)

        pos = self._to_image_coords(self._mouse_pos)
        cursor_text = f"X:{pos.x()} Y:{pos.y()}"
        painter.setPen(QPen(QColor(200, 200, 200, 180)))
        painter.drawText(10, int(50 * self._scale), cursor_text)

        painter.end()
        self.setPixmap(canvas)
        self.setFixedSize(canvas.size())

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            pos = self._to_image_coords(event.pos())
            
            # 检查是否在边框上（调整大小）
            edge = self._get_edge_at_pos(pos)
            if edge:
                self._resizing_edge = edge
                self._start_pos = pos
                return
            
            # 检查是否点击在已有 ROI 框内（用于拖动）
            if self._current_roi:
                left, top, right, bottom = self._current_roi
                if left <= pos.x() <= right and top <= pos.y() <= bottom:
                    # 开始拖动已有 ROI
                    self._dragging_roi = True
                    self._drag_offset = QPoint(pos.x() - left, pos.y() - top)
                    self._start_pos = pos
                    return
            
            # 否则开始框选新区域
            self._start_pos = pos
            self._current_rect = QRect(self._start_pos, self._start_pos)
            self._update_display()

    def mouseMoveEvent(self, event):
        self._mouse_pos = event.pos()
        pos = self._to_image_coords(event.pos())
        
        if self._resizing_edge and self._current_roi:
            # 调整 ROI 大小
            left, top, right, bottom = self._current_roi
            edge = self._resizing_edge
            
            # 根据拖动的边更新坐标
            if 'top' in edge:
                top = pos.y()
            if 'bottom' in edge:
                bottom = pos.y()
            if 'left' in edge:
                left = pos.x()
            if 'right' in edge:
                right = pos.x()
            
            # 确保 left < right, top < bottom
            if left > right:
                left, right = right, left
            if top > bottom:
                top, bottom = bottom, top
            
            # 最小尺寸限制
            if right - left < 20:
                if 'left' in edge:
                    left = right - 20
                else:
                    right = left + 20
            if bottom - top < 20:
                if 'top' in edge:
                    top = bottom - 20
                else:
                    bottom = top + 20
            
            self._current_roi = (left, top, right, bottom)
            self._update_display()
            
        elif self._dragging_roi and self._current_roi:
            # 拖动已有 ROI
            left = pos.x() - self._drag_offset.x()
            top = pos.y() - self._drag_offset.y()
            old_left, old_top, old_right, old_bottom = self._current_roi
            width = old_right - old_left
            height = old_bottom - old_top
            self._current_roi = (left, top, left + width, top + height)
            self._update_display()
        elif self._start_pos is not None:
            # 框选新区域
            end = pos
            self._current_rect = QRect(self._start_pos, end).normalized()
            self._update_display()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton:
            if self._resizing_edge:
                # 结束调整大小
                self._resizing_edge = None
                self._start_pos = None
                # 通知父窗口 ROI 已改变
                if hasattr(self.parent(), '_on_roi_dragged'):
                    self.parent()._on_roi_dragged(self._current_roi)
            elif self._dragging_roi:
                # 结束拖动
                self._dragging_roi = False
                self._start_pos = None
                # 通知父窗口 ROI 已改变
                if hasattr(self.parent(), '_on_roi_dragged'):
                    self.parent()._on_roi_dragged(self._current_roi)
            elif self._current_rect:
                # 结束框选
                if self._current_rect.width() > 10 and self._current_rect.height() > 10:
                    pass
                else:
                    self._current_rect = None
                    self._start_pos = None
            self._update_display()

    def get_roi(self):
        if self._current_rect:
            return (
                self._current_rect.x(),
                self._current_rect.y(),
                self._current_rect.right(),
                self._current_rect.bottom()
            )
        return None


class ROIConfigDialog(QDialog):
    """通用 ROI 配置对话框"""
    
    # 信号：ROI 保存成功
    roi_saved = pyqtSignal(str, tuple)  # (roi_type, roi_coords)
    
    # ROI 类型定义
    ROI_TYPES = {
        'posture_roi': '姿势识别区域',
        'Name_1': '1号枪-名称',
        'Scope_1': '1号枪-倍镜',
        'Muzzle_1': '1号枪-枪口',
        'Grip_1': '1号枪-握把',
        'Stock_1': '1号枪-枪托',
        'Name_2': '2号枪-名称',
        'Scope_2': '2号枪-倍镜',
        'Muzzle_2': '2号枪-枪口',
        'Grip_2': '2号枪-握把',
        'Stock_2': '2号枪-枪托',
    }
    
    def __init__(self, resolution, current_rois=None, parent=None):
        super().__init__(parent)
        self.resolution = resolution
        self.current_rois = current_rois or {}
        self.setWindowTitle("ROI 配置工具")
        self.setMinimumSize(900, 700)
        
        # ✅ 记录当前正在编辑的 ROI 类型（用于切换时自动保存）
        self._last_roi_type = None
        
        self._build_ui()
        self._load_screenshot()
    
    def _build_ui(self):
        """构建 UI"""
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(10, 10, 10, 10)
        
        # 顶部控制栏
        top_bar = QHBoxLayout()
        
        # ROI 类型选择
        top_bar.addWidget(QLabel("ROI 类型:"))
        self.roi_type_combo = QComboBox()
        for key, name in self.ROI_TYPES.items():
            self.roi_type_combo.addItem(name, key)
        self.roi_type_combo.currentIndexChanged.connect(self.roi_type_changed)
        top_bar.addWidget(self.roi_type_combo, 1)
        
        # 显示当前值
        self.current_value_label = QLabel("未设置")
        self.current_value_label.setStyleSheet("color: #ffba08; font-weight: bold;")
        top_bar.addWidget(self.current_value_label)
        
        # 置信度显示
        self.confidence_label = QLabel("")
        self.confidence_label.setStyleSheet("color: #00ff00; font-weight: bold;")
        top_bar.addWidget(self.confidence_label)
        
        # 计算置信度按钮
        self.calc_conf_btn = QPushButton("计算置信度")
        self.calc_conf_btn.clicked.connect(self._calculate_confidence)
        top_bar.addWidget(self.calc_conf_btn)
        
        # 缩放控制
        top_bar.addWidget(QLabel("缩放:"))
        self.zoom_in_btn = QPushButton("+")
        self.zoom_in_btn.setFixedWidth(30)
        self.zoom_in_btn.clicked.connect(lambda: self._roi_label.set_scale(self._roi_label._scale + 0.1))
        top_bar.addWidget(self.zoom_in_btn)
        
        self.zoom_out_btn = QPushButton("-")
        self.zoom_out_btn.setFixedWidth(30)
        self.zoom_out_btn.clicked.connect(lambda: self._roi_label.set_scale(self._roi_label._scale - 0.1))
        top_bar.addWidget(self.zoom_out_btn)
        
        main_layout.addLayout(top_bar)
        
        # 截图显示区域
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(False)
        self.scroll_area.setAlignment(Qt.AlignCenter)
        main_layout.addWidget(self.scroll_area, 1)
        
        # 底部按钮
        button_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        button_box.accepted.connect(self._on_save)
        button_box.rejected.connect(self.reject)
        main_layout.addWidget(button_box)
        
        # 状态栏
        self.status_label = QLabel("拖动框选区域 → 点击确定保存")
        self.status_label.setStyleSheet("color: #a0a0b0; padding: 5px;")
        main_layout.addWidget(self.status_label)
    
    def _load_screenshot(self):
        """加载截图"""
        try:
            print("正在截取屏幕...")
            pixmap = capture_screenshot()
            print(f"截图完成: {pixmap.width()}x{pixmap.height()}")
            
            self._roi_label = ROILabel(pixmap, self)
            self.scroll_area.setWidget(self._roi_label)
            
            # 自动适应窗口大小
            screen = QApplication.primaryScreen().geometry()
            fit_scale = min(
                (screen.width() - 200) / pixmap.width(),
                (screen.height() - 200) / pixmap.height(),
                1.0
            )
            self._roi_label.set_scale(fit_scale)
            
            # ✅ 初始化 _last_roi_type
            self._last_roi_type = self.roi_type_combo.currentData()
            
            # 更新当前值显示
            self._update_current_value()
            
        except Exception as e:
            QMessageBox.critical(self, "错误", f"截图失败: {e}")
            # 不要调用 reject()，只是关闭对话框
            self.close()
    
    def _update_current_value(self):
        """更新当前 ROI 值显示"""
        roi_type = self.roi_type_combo.currentData()
        current = self.current_rois.get(roi_type)
        
        if current:
            self.current_value_label.setText(f"当前: {current}")
            # 更新 ROI 标签上的显示
            if hasattr(self, '_roi_label'):
                self._roi_label._current_roi = current
                self._roi_label._update_display()
        else:
            self.current_value_label.setText("未设置")
            # 清除 ROI 标签上的显示
            if hasattr(self, '_roi_label'):
                self._roi_label._current_roi = None
                self._roi_label._update_display()
    
    def roi_type_changed(self):
        """ROI 类型改变时更新显示"""
        # ✅ 自动保存上一个 ROI 类型的调整结果
        if self._last_roi_type and hasattr(self, '_roi_label') and self._roi_label._current_roi:
            # 保存上一个类型的 ROI
            self.current_rois[self._last_roi_type] = list(self._roi_label._current_roi)
            import logging
            logger = logging.getLogger(__name__)
            logger.info(f"✅ 自动保存 {self._last_roi_type}: {self._roi_label._current_roi}")
        
        # 更新当前类型
        self._last_roi_type = self.roi_type_combo.currentData()
        
        # 更新显示（加载新类型的 ROI）
        self._update_current_value()
    
    def _on_roi_dragged(self, new_roi):
        """当用户拖动 ROI 框时调用"""
        if new_roi:
            # 更新当前值显示
            self.current_value_label.setText(f"当前: {new_roi}")
            # 同时更新 current_rois 中的数据
            roi_type = self.roi_type_combo.currentData()
            self.current_rois[roi_type] = list(new_roi)
            
            # 自动计算置信度
            self._calculate_confidence()
    
    def _calculate_confidence(self):
        """计算并显示置信度"""
        roi_type = self.roi_type_combo.currentData()
        
        # 姿势识别没有模板
        if roi_type == 'posture_roi':
            self.confidence_label.setText("姿势识别无模板")
            return
        
        # 计算置信度
        confidence = self._roi_label.calculate_confidence(roi_type, self.resolution)
        
        if confidence is not None:
            self._roi_label._confidence_score = confidence
            self._roi_label._update_display()
            
            # 更新标签显示
            color = "#00ff00" if confidence > 0.7 else "#ffba08" if confidence > 0.5 else "#ff4444"
            template_info = f" - {self._roi_label._template_path}" if self._roi_label._template_path else ""
            self.confidence_label.setText(f"置信度: {confidence:.2%}{template_info}")
            self.confidence_label.setStyleSheet(f"color: {color}; font-weight: bold;")
        else:
            self.confidence_label.setText("无法计算")
            self.confidence_label.setStyleSheet("color: #ff4444; font-weight: bold;")
    
    def _on_save(self):
        """保存 ROI"""
        # 优先使用拖动后的 ROI，如果没有则使用框选的
        roi = self._roi_label._current_roi if self._roi_label._current_roi else self._roi_label.get_roi()
        
        if not roi:
            QMessageBox.warning(self, "提示", "请先框选一个区域或拖动已有区域")
            return
        
        roi_type = self.roi_type_combo.currentData()
        roi_name = self.ROI_TYPES.get(roi_type, roi_type)
        
        # 发送保存信号
        self.roi_saved.emit(roi_type, roi)
        
        QMessageBox.information(
            self, "保存成功",
            f"ROI 已保存！\n\n"
            f"类型: {roi_name}\n"
            f"坐标: {roi}\n"
            f"分辨率: {self.resolution}"
        )
        
        self.accept()
    
    def wheelEvent(self, event):
        """滚轮缩放"""
        delta = event.angleDelta().y()
        current = self._roi_label._scale
        if delta > 0:
            self._roi_label.set_scale(current + 0.1)
        else:
            self._roi_label.set_scale(current - 0.1)
        self.status_label.setText(f"缩放: {self._roi_label._scale:.0%}")
    
    def keyPressEvent(self, event):
        """键盘事件"""
        key = event.key()
        
        if key in (Qt.Key_Return, Qt.Key_Enter):
            self._on_save()
        elif key in (Qt.Key_Escape, Qt.Key_Q):
            self.reject()
        else:
            super().keyPressEvent(event)
