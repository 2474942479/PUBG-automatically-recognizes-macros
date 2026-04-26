"""通用 ROI 配置对话框 - 集成到主 UI"""
import os
import cv2
import numpy as np

from PyQt5.QtCore import Qt, QRect, QPoint, pyqtSignal
from PyQt5.QtWidgets import (
    QDialog, QLabel, QMessageBox, QScrollArea, 
    QVBoxLayout, QHBoxLayout, QPushButton, QComboBox,
    QLineEdit, QInputDialog, QSpinBox
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

    def __init__(self, pixmap, parent=None, mode="fullscreen"):
        """
        :param pixmap: 原始截图（全屏或背包区域）
        :param parent: 父窗口
        :param mode: 框选模式 - 'fullscreen'（全屏截图）或 'backpack'（背包截图）
        """
        super().__init__(parent)
        self._base_pixmap = pixmap
        self._current_rect = None
        self._current_roi = None  # 当前已配置的 ROI
        self._start_pos = None
        self._dragging_roi = False  # 是否正在拖动已有 ROI
        self._drag_offset = QPoint(0, 0)  # 拖动偏移量
        self._resizing_edge = None  # 正在调整大小的边: 'top', 'bottom', 'left', 'right'
        self._confidence_score = None  # 模板匹配置信度
        self._template_path = None  # 模板图片路径
        self._mode = mode  # ✅ 新增：框选模式

        # ✅ 固定尺寸模式（阶段2：禁止调整大小，只允许拖动）
        self._fixed_size_mode = False
        self._fixed_w = 60
        self._fixed_h = 50

        self.setMouseTracking(True)
        self._mouse_pos = QPoint(0, 0)
        self._update_display()

    def set_fixed_size(self, w, h):
        """启用固定尺寸模式，设定固定宽高。"""
        self._fixed_size_mode = True
        self._fixed_w = w
        self._fixed_h = h

    def reset_to_center(self):
        """将当前 ROI 移动到图片中心（固定尺寸模式）。"""
        if not self._fixed_size_mode:
            return
        pw = self._base_pixmap.width()
        ph = self._base_pixmap.height()
        cx = pw // 2 - self._fixed_w // 2
        cy = ph // 2 - self._fixed_h // 2
        self._current_roi = (cx, cy, cx + self._fixed_w, cy + self._fixed_h)
        self._current_rect = None
        self._update_display()

    def _to_image_coords(self, widget_pos):
        """控件坐标 → 原图像素坐标（1:1 全屏截图，无缩放）。"""
        return QPoint(int(widget_pos.x()), int(widget_pos.y()))
    
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
            
            # 从截图中提取 ROI 区域（原图像素，与框选一致）
            roi_pixmap = self._base_pixmap.copy(
                int(left), int(top), int(width), int(height)
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
            elif roi_type == 'posture_roi':
                # ✅ 姿势识别也有模板，在 zishi 目录下
                template_dir = res_path('_internal', 'data', 'firearms', 'zishi')
            else:
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
                
                # 使用模板匹配（如果模板比截图大，缩小模板到截图尺寸）
                try:
                    from core.recognition import match_sift
                    th, tw = template_img.shape[:2]
                    rh, rw = roi_gray.shape[:2]
                    if th > rh or tw > rw:
                        template_img = cv2.resize(template_img, (rw, rh), interpolation=cv2.INTER_AREA)
                    max_val = match_sift(roi_gray, template_img)
                    
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
        # 1:1 原图绘制，避免缩放带来的亚像素偏差
        canvas = QPixmap(self._base_pixmap)
        painter = QPainter(canvas)
        painter.setRenderHint(QPainter.Antialiasing)

        font = QFont("Microsoft YaHei", 10)
        painter.setFont(font)

        # ✅ 绘制提示文字和分辨率信息
        screen_w = self._base_pixmap.width()
        screen_h = self._base_pixmap.height()
        hint_text = f"请拖动鼠标框选区域（1:1 全屏像素 {screen_w}x{screen_h}，可滚动查看）"
        painter.setPen(QPen(QColor(255, 255, 255, 200)))
        painter.drawText(10, 28, hint_text)

        # 绘制当前已配置的 ROI（如果有）
        if hasattr(self, '_current_roi') and self._current_roi:
            left, top, right, bottom = self._current_roi
            
            # 如果正在拖动或调整大小，使用实线；否则使用虚线
            pen = QPen(QColor(255, 165, 0, 220), 2)
            is_active = getattr(self, '_dragging_roi', False) or getattr(self, '_resizing_edge', None)
            if not is_active:
                pen.setStyle(Qt.DashLine)
            painter.setPen(pen)
            
            r = QRect(int(left), int(top), int(right - left), int(bottom - top))
            painter.drawRect(r)
            
            # 添加标签
            painter.setPen(QPen(QColor(255, 165, 0)))
            label_text = "当前配置 (可拖动/调整)"
            painter.drawText(r.topLeft() + QPoint(4, -4), label_text)
            
            # 显示置信度（如果有）
            if hasattr(self, '_confidence_score') and self._confidence_score is not None:
                conf_text = f"置信度: {self._confidence_score:.2%}"
                if self._template_path:
                    conf_text += f" ({self._template_path})"
                painter.setPen(QPen(QColor(0, 255, 0) if self._confidence_score > 0.7 else QColor(255, 165, 0)))
                painter.drawText(r.bottomLeft() + QPoint(4, -4), conf_text)
            
            # 绘制8个调整手柄（四个角+四条边中点）
            if not self._fixed_size_mode:
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
                        int(hx) - handle_size // 2,
                        int(hy) - handle_size // 2,
                        handle_size,
                        handle_size
                    )
                    painter.fillRect(handle_rect, QColor(255, 165, 0))
                    painter.setPen(QPen(Qt.white, 1))
                    painter.drawRect(handle_rect)

        # 绘制正在框选的区域
        if self._current_rect:
            pen = QPen(QColor(0, 255, 0, 200), 2)
            painter.setPen(pen)
            painter.drawRect(self._current_rect)

            coord_text = (
                f"✅ ROI: ({self._current_rect.x()}, {self._current_rect.y()}, "
                f"{self._current_rect.right()}, {self._current_rect.bottom()}) "
                f"[{self._current_rect.width()}x{self._current_rect.height()}px]"
            )
            painter.setPen(QPen(QColor(0, 255, 0)))
            painter.drawText(self._current_rect.bottomLeft() + QPoint(4, 18), coord_text)

        pos = self._to_image_coords(self._mouse_pos)
        cursor_text = f"📍 鼠标位置: X:{pos.x()} Y:{pos.y()} (真实屏幕坐标)"
        painter.setPen(QPen(QColor(200, 200, 200, 180)))
        painter.drawText(10, 48, cursor_text)

        painter.end()
        self.setPixmap(canvas)
        self.setFixedSize(canvas.size())

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            pos = self._to_image_coords(event.pos())
            
            # ✅ 固定尺寸模式：跳过边缘检测（边框即拖动区域）
            if not self._fixed_size_mode:
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
            
            # 开始框选新区域
            self._start_pos = pos
            if not self._fixed_size_mode:
                self._current_rect = QRect(self._start_pos, self._start_pos)
                self._update_display()

    def mouseMoveEvent(self, event):
        self._mouse_pos = event.pos()
        pos = self._to_image_coords(event.pos())
        
        if self._resizing_edge and self._current_roi:
            # 固定尺寸模式不允许调整大小
            if self._fixed_size_mode:
                self._resizing_edge = None
                return
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
                    # ✅ 将框选的矩形转换为 ROI 坐标
                    self._current_roi = (
                        self._current_rect.x(),
                        self._current_rect.y(),
                        self._current_rect.right(),
                        self._current_rect.bottom()
                    )
                    # 通知父窗口 ROI 已改变
                    if hasattr(self.parent(), '_on_roi_dragged'):
                        self.parent()._on_roi_dragged(self._current_roi)
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

    def cancel_ongoing(self):
        """取消正在画的新框、拖动/缩放手势；不关闭对话框。"""
        self._current_rect = None
        self._resizing_edge = None
        self._dragging_roi = False
        self._start_pos = None
        self._update_display()


class ROIConfigDialog(QDialog):
    """通用 ROI 配置对话框"""
    
    # 信号：ROI 保存成功
    roi_saved = pyqtSignal(str, tuple)  # (roi_type, roi_coords)
    
    # ROI 类型定义
    ROI_TYPES = {
        'posture_roi': '姿势识别区域',
        'Name_1': '1号枪-名称 (相对背包)',
        'Scope_1': '1号枪-倍镜 (相对背包)',
        'Muzzle_1': '1号枪-枪口 (相对背包)',
        'Grip_1': '1号枪-握把 (相对背包)',
        'Stock_1': '1号枪-枪托 (相对背包)',
        'Name_2': '2号枪-名称 (相对背包)',
        'Scope_2': '2号枪-倍镜 (相对背包)',
        'Muzzle_2': '2号枪-枪口 (相对背包)',
        'Grip_2': '2号枪-握把 (相对背包)',
        'Stock_2': '2号枪-枪托 (相对背包)',
        # ✅ 新增：背包截图区域和开镜点击坐标
        'guns_backpack_roi': '背包截图区域 (GUNS_REOLUTION_SETTINGS)',
        'right_click_pos': '右键开镜点击坐标 (Click)',
        # ✅ 新增：HUD 枪械图标区域（一次截图+裁剪）
        'hud_gun_icons': 'HUD 枪械图标区域（右下角）',
        'Gun_1': '1号枪图标 (相对 HUD)',
        'Gun_2': '2号枪图标 (相对 HUD)',
    }
    
    # ✅ 需要转换为相对坐标的ROI类型（相对于背包区域）
    RELATIVE_TO_BACKPACK = {
        'Name_1', 'Scope_1', 'Muzzle_1', 'Grip_1', 'Stock_1',
        'Name_2', 'Scope_2', 'Muzzle_2', 'Grip_2', 'Stock_2',
    }
    
    # ✅ 需要转换为相对坐标的ROI类型（相对于 HUD 区域）
    RELATIVE_TO_HUD = {
        'Gun_1', 'Gun_2',
    }
    
    def __init__(self, resolution, current_rois=None, parent=None):
        super().__init__(parent)
        self.resolution = resolution
        self.current_rois = {}
        if current_rois:
            for k, v in current_rois.items():
                self.current_rois[k] = list(v) if v is not None and isinstance(v, (list, tuple)) else v
        # 打开对话框时已存在配置（与「保存当前」写入磁盘）对齐的快照
        self._last_emitted = {}
        for k, v in self.current_rois.items():
            # ✅ 跳过特殊配置节点（_GUN_HUD_SETTINGS、_GUNS_REOLUTION_SETTINGS 等）
            if k.startswith('_'):
                continue
            if v is not None:
                self._last_emitted[k] = self._norm_roi(v)
        self._allow_close_without_prompt = False
        self.setWindowTitle("ROI 配置工具")
        self.setMinimumSize(900, 700)
        
        # ✅ 设置窗口标志：独立顶层窗口，始终在最前
        self.setWindowFlags(Qt.Dialog | Qt.WindowStaysOnTopHint)
        
        # ✅ 记录当前正在编辑的 ROI 类型（用于切换时自动保存）
        self._last_roi_type = None
        
        # ✅ 背包区域坐标（用于相对坐标转换）
        # 【格式规范】统一使用 (left, top, right, bottom) - 屏幕绝对坐标
        self.backpack_roi = None
        if current_rois and 'guns_backpack_roi' in current_rois:
            backpack_data = current_rois['guns_backpack_roi']
            # 确保是4个值的元组
            if len(backpack_data) == 4:
                self.backpack_roi = tuple(backpack_data)
                import logging
                logger = logging.getLogger(__name__)
                logger.info(f"✅ 加载背包区域（绝对坐标）: {self.backpack_roi}")
        
        # ✅ HUD 枪械图标区域坐标（用于相对坐标转换）
        # 【格式规范】统一使用 (left, top, right, bottom) - 屏幕绝对坐标，存储在 _GUN_HUD_SETTINGS 中
        self.hud_roi = None
        # 从 _GUN_HUD_SETTINGS 加载（类似 _GUNS_REOLUTION_SETTINGS）
        if current_rois and '_GUN_HUD_SETTINGS' in current_rois:
            hud_settings = current_rois['_GUN_HUD_SETTINGS']
            if isinstance(hud_settings, dict) and resolution in hud_settings:
                hud_data = hud_settings[resolution]
                if len(hud_data) == 4:
                    self.hud_roi = tuple(hud_data)
                    import logging
                    logger = logging.getLogger(__name__)
                    logger.info(f"✅ 加载 HUD 枪械图标区域（绝对坐标）: {self.hud_roi}")
        
        # ✅ 新增：两步流程状态管理
        self._phase = "backpack"  # 当前阶段: 'backpack' 或 'roi'
        self._backpack_pixmap = None  # 背包截图（用于阶段2）
        # 【格式规范】统一使用 (left, top, right, bottom) - 屏幕绝对坐标
        self._backpack_abs_coords = None
        self._fullscreen_pixmap = None  # 全屏截图（阶段1使用）
        
        self._build_ui()
        self._load_screenshot()
    
    def _update_roi_type_combo(self):
        """更新 ROI 类型下拉框（阶段1显示姿势/背包/开镜/HUD，阶段2只显示枪械配件）"""
        self.roi_type_combo.blockSignals(True)
        self.roi_type_combo.clear()
            
        if self._phase == "roi":
            # ✅ 阶段2：只显示枪械配件类型（姿势/背包/开镜/HUD不在这里配置）
            phase2_types = [
                'Name_1', 'Scope_1', 'Muzzle_1', 'Grip_1', 'Stock_1',
                'Name_2', 'Scope_2', 'Muzzle_2', 'Grip_2', 'Stock_2',
            ]
            for key in phase2_types:
                self.roi_type_combo.addItem(self.ROI_TYPES[key], key)
        else:
            # ✅ 阶段1：显示姿势/背包/开镜坐标 + HUD枪械图标区域
            phase1_types = [
                ('guns_backpack_roi', '背包截图区域 (GUNS_REOLUTION_SETTINGS)'),
                ('posture_roi',       '姿势识别区域'),
                ('right_click_pos',   '右键开镜点击坐标 (Click)'),
                ('hud_gun_icons',     'HUD 枪械图标区域（右下角）'),
            ]
            for key, name in phase1_types:
                self.roi_type_combo.addItem(name, key)
            
        self.roi_type_combo.blockSignals(False)
    
    def _build_ui(self):
        """构建 UI"""
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(10, 10, 10, 10)
        
        # 顶部控制栏
        top_bar = QHBoxLayout()
        
        # ✅ 显示当前截图分辨率
        self.resolution_label = QLabel(f"截图分辨率: 加载中...")
        self.resolution_label.setStyleSheet("color: #00ffff; font-weight: bold; font-size: 12px;")
        top_bar.addWidget(self.resolution_label)
        
        top_bar.addStretch()
        
        # ROI 类型选择
        top_bar.addWidget(QLabel("ROI 类型:"))
        self.roi_type_combo = QComboBox()
        
        # ✅ 初始只显示背包区域和开镜坐标（不显示枪械信息）
        self._update_roi_type_combo()
        
        self.roi_type_combo.currentIndexChanged.connect(self.roi_type_changed)
        top_bar.addWidget(self.roi_type_combo, 1)
        
        # 显示当前值
        self.current_value_label = QLabel("未设置")
        self.current_value_label.setStyleSheet("color: #ffba08; font-weight: bold;")
        top_bar.addWidget(self.current_value_label)

        # ✅ 固定尺寸配置（阶段2显示）
        self.roi_size_spin_w = QSpinBox()
        self.roi_size_spin_w.setRange(10, 999)
        self.roi_size_spin_w.setValue(60)
        self.roi_size_spin_w.setFixedWidth(50)
        self.roi_size_spin_h = QSpinBox()
        self.roi_size_spin_h.setRange(10, 999)
        self.roi_size_spin_h.setValue(50)
        self.roi_size_spin_h.setFixedWidth(50)
        self.roi_size_w_label = QLabel("宽:")
        self.roi_size_x_label = QLabel("×")
        self.roi_size_h_label = QLabel("高:")
        self.roi_size_w_label.setStyleSheet("color: #aaa;")
        self.roi_size_x_label.setStyleSheet("color: #aaa;")
        self.roi_size_h_label.setStyleSheet("color: #aaa;")
        for w in (self.roi_size_w_label, self.roi_size_x_label, self.roi_size_h_label):
            top_bar.addWidget(w)
            w.setVisible(False)
        for s in (self.roi_size_spin_w, self.roi_size_spin_h):
            top_bar.addWidget(s)
            s.setVisible(False)
        self.roi_size_spin_w.valueChanged.connect(self._on_fixed_size_changed)
        self.roi_size_spin_h.valueChanged.connect(self._on_fixed_size_changed)

        self.roi_size_fixed_label = QLabel("(固定尺寸)")
        self.roi_size_fixed_label.setStyleSheet("color: #4ae04a; font-weight: bold;")
        top_bar.addWidget(self.roi_size_fixed_label)
        self.roi_size_fixed_label.setVisible(False)
        top_bar.addSpacing(8)
        
        # 置信度显示
        self.confidence_label = QLabel("")
        self.confidence_label.setStyleSheet("color: #00ff00; font-weight: bold;")
        top_bar.addWidget(self.confidence_label)
        
        # 计算置信度按钮
        self.calc_conf_btn = QPushButton("计算置信度")
        self.calc_conf_btn.clicked.connect(self._calculate_confidence)
        top_bar.addWidget(self.calc_conf_btn)
        
        # ✅ 保存模板按钮（阶段2单独生成模板）
        self.save_template_btn = QPushButton("💾 保存模板")
        self.save_template_btn.setToolTip("从当前ROI区域截图，生成SIFT识别用的模板图片")
        self.save_template_btn.clicked.connect(self._on_save_template)
        self.save_template_btn.setStyleSheet("color: #00ff88; font-weight: bold;")
        self.save_template_btn.setVisible(False)  # 默认隐藏，阶段2才显示
        top_bar.addWidget(self.save_template_btn)
        
        # ✅ 重置位置按钮
        self.reset_btn = QPushButton("🔄 重置位置")
        self.reset_btn.setToolTip("清除当前 ROI，重新框选")
        self.reset_btn.clicked.connect(self._on_reset_position)
        self.reset_btn.setStyleSheet("color: #ffba08; font-weight: bold;")
        top_bar.addWidget(self.reset_btn)
        
        # ✅ 回退阶段按钮（仅在阶段2显示）
        self.back_btn = QPushButton("⬅️ 回退到阶段1")
        self.back_btn.setToolTip("重新调整背包区域（会重置所有枪械 ROI）")
        self.back_btn.clicked.connect(self._on_back_to_phase1)
        self.back_btn.setStyleSheet("color: #ff4444; font-weight: bold;")
        self.back_btn.setVisible(False)  # 默认隐藏，阶段2才显示
        top_bar.addWidget(self.back_btn)
        
        main_layout.addLayout(top_bar)
        
        # 截图显示区域
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(False)
        self.scroll_area.setAlignment(Qt.AlignCenter)
        # ✅ 设置背景色为深灰色，避免黑边
        self.scroll_area.setStyleSheet("QScrollArea { background-color: #2b2b2b; }")
        main_layout.addWidget(self.scroll_area, 1)
        
        # 底部按钮：保存仅写入当前类型，不关闭；关闭再结束
        btn_row = QHBoxLayout()
        btn_row.addStretch()
        self.save_btn = QPushButton("保存当前 ROI")
        self.save_btn.setDefault(True)
        self.save_btn.clicked.connect(self._on_save)
        self.close_btn = QPushButton("关闭")
        self.close_btn.clicked.connect(self._close_dialog)
        btn_row.addWidget(self.save_btn)
        btn_row.addWidget(self.close_btn)
        main_layout.addLayout(btn_row)
        
        # 状态栏
        self.status_label = QLabel(
            "✅ 1:1 全屏截图 | ✅ 框选坐标 = 真实屏幕坐标 | 🔄 枪械信息自动转换为相对背包坐标 | 📍 可拖动滚动条查看完整截图 | 💾 保存当前 ROI 写入一条，全部调好后点「关闭」"
        )
        self.status_label.setStyleSheet("color: #a0a0b0; padding: 5px; font-size: 11px;")
        main_layout.addWidget(self.status_label)
    
    def _load_screenshot(self):
        """加载截图（两步流程）"""
        try:
            print("正在截取屏幕...")
            self._fullscreen_pixmap = capture_screenshot()
            print(f"截图完成: {self._fullscreen_pixmap.width()}x{self._fullscreen_pixmap.height()}")
            
            # ✅ 更新分辨率显示
            if hasattr(self, 'resolution_label'):
                self.resolution_label.setText(f"📊 截图分辨率: {self._fullscreen_pixmap.width()}x{self._fullscreen_pixmap.height()}")
                        
            # ✅ 始终从阶段1开始，让用户自己选择配置什么（背包/姿势/开镜/HUD）
            # 不再自动提示进入背包二阶段，避免干扰只想配置 HUD 的用户
            print("✅ 从阶段1开始，用户可自由选择配置背包或 HUD")
            self._setup_phase1_backpack_selection()
            
        except Exception as e:
            QMessageBox.critical(self, "错误", f"截图失败: {e}")
            self.close()
    
    def _extract_backpack_from_fullscreen(self):
        """从全屏截图中提取背包区域"""
        import logging
        logger = logging.getLogger(__name__)
        
        if not self.backpack_roi or len(self.backpack_roi) != 4:
            logger.warning(f"⚠️ 背包区域配置无效: {self.backpack_roi}")
            return
        
        # 背包区域: (left, top, right, bottom) - 屏幕绝对坐标
        backpack_left, backpack_top, backpack_right, backpack_bottom = self.backpack_roi
        
        # 计算宽高
        backpack_width = backpack_right - backpack_left
        backpack_height = backpack_bottom - backpack_top
        
        logger.info(f"📦 开始提取背包区域:")
        logger.info(f"   背包配置（绝对坐标）: left={backpack_left}, top={backpack_top}, right={backpack_right}, bottom={backpack_bottom}")
        logger.info(f"   背包尺寸: width={backpack_width}, height={backpack_height}")
        logger.info(f"   全屏截图: {self._fullscreen_pixmap.width()}x{self._fullscreen_pixmap.height()}")
        
        # 检查坐标是否有效
        if backpack_left < 0 or backpack_top < 0:
            logger.error(f"❌ 背包坐标为负数: left={backpack_left}, top={backpack_top}")
            return
        
        if backpack_width <= 0 or backpack_height <= 0:
            logger.error(f"❌ 背包尺寸无效: width={backpack_width}, height={backpack_height}")
            return
        
        # 检查是否超出全屏范围
        if backpack_right > self._fullscreen_pixmap.width():
            logger.warning(f"⚠️ 背包右边界超出屏幕: {backpack_right} > {self._fullscreen_pixmap.width()}")
        if backpack_bottom > self._fullscreen_pixmap.height():
            logger.warning(f"⚠️ 背包下边界超出屏幕: {backpack_bottom} > {self._fullscreen_pixmap.height()}")
        
        # 从全屏截图中裁剪背包区域
        try:
            self._backpack_pixmap = self._fullscreen_pixmap.copy(
                int(backpack_left), int(backpack_top), 
                int(backpack_width), int(backpack_height)
            )
            
            logger.info(f"✅ 背包截图成功: {self._backpack_pixmap.width()}x{self._backpack_pixmap.height()}")
            
            # 保存背包绝对坐标（用于阶段2的坐标转换）
            self._backpack_abs_coords = (
                backpack_left, backpack_top,
                backpack_right, backpack_bottom
            )
            
            logger.info(f"✅ 背包绝对坐标: {self._backpack_abs_coords}")
            
        except Exception as e:
            logger.error(f"❌ 裁剪背包区域失败: {e}")
            logger.error(f"   参数: x={backpack_left}, y={backpack_top}, w={backpack_width}, h={backpack_height}")
    
    def _select_first_configured_roi(self):
        """自动选择第一个已配置的 ROI 类型"""
        import logging
        logger = logging.getLogger(__name__)
        
        # 优先级：Name_1 > Scope_1 > Muzzle_1 > ... > posture_roi
        priority_order = [
            'Name_1', 'Scope_1', 'Muzzle_1', 'Grip_1', 'Stock_1',
            'Name_2', 'Scope_2', 'Muzzle_2', 'Grip_2', 'Stock_2',
            'posture_roi'
        ]
        
        for roi_type in priority_order:
            if roi_type in self.current_rois and self.current_rois[roi_type]:
                # 找到第一个已配置的 ROI
                index = self.roi_type_combo.findData(roi_type)
                if index >= 0:
                    self.roi_type_combo.blockSignals(True)
                    self.roi_type_combo.setCurrentIndex(index)
                    self.roi_type_combo.blockSignals(False)
                    self._last_roi_type = roi_type
                    # ✅ combo 已跳转，同步更新画布显示（blockSignals 阻断了 roi_type_changed）
                    self._update_current_value()
                    logger.info(f"✅ 自动选择已配置的 ROI: {roi_type}")
                    return
        
        # 如果都没有配置，选择 Name_1
        index = self.roi_type_combo.findData('Name_1')
        if index >= 0:
            self.roi_type_combo.blockSignals(True)
            self.roi_type_combo.setCurrentIndex(index)
            self.roi_type_combo.blockSignals(False)
            self._last_roi_type = 'Name_1'
            self._update_current_value()
    
    def _select_first_configured_hud_roi(self):
        """自动选择第一个已配置的 HUD ROI 类型（Gun_1 或 Gun_2）"""
        import logging
        logger = logging.getLogger(__name__)
        
        # 优先级：Gun_1 > Gun_2
        priority_order = ['Gun_1', 'Gun_2']
        
        for roi_type in priority_order:
            if roi_type in self.current_rois and self.current_rois[roi_type]:
                # 找到第一个已配置的 HUD ROI
                index = self.roi_type_combo.findData(roi_type)
                if index >= 0:
                    self.roi_type_combo.blockSignals(True)
                    self.roi_type_combo.setCurrentIndex(index)
                    self.roi_type_combo.blockSignals(False)
                    self._last_roi_type = roi_type
                    self._update_current_value()
                    logger.info(f"✅ 自动选择已配置的 HUD ROI: {roi_type}")
                    return
        
        # 如果都没有配置，选择 Gun_1
        index = self.roi_type_combo.findData('Gun_1')
        if index >= 0:
            self.roi_type_combo.blockSignals(True)
            self.roi_type_combo.setCurrentIndex(index)
            self.roi_type_combo.blockSignals(False)
            self._last_roi_type = 'Gun_1'
            self._update_current_value()
            logger.info("✅ 默认选择 Gun_1")
    
    def _on_back_to_phase1(self):
        """回退到阶段1：重新调整背包区域"""
        import logging
        logger = logging.getLogger(__name__)
        
        # ✅ 弹出确认对话框
        reply = QMessageBox.question(
            self,
            "⚠️ 确认回退",
            "回退到阶段1会：\n"
            "1. 重新框选背包区域\n"
            "2. 清除所有枪械 ROI 配置\n"
            "3. 删除已保存的枪械模板\n\n"
            "确定要回退吗？",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )
        
        if reply != QMessageBox.Yes:
            logger.info("❌ 用户取消回退")
            return
        
        # ✅ 重置所有枪械 ROI 坐标为 0（但保留背包区域）
        reset_count = 0
        for roi_type in list(self.RELATIVE_TO_BACKPACK):
            if roi_type in self.current_rois:
                # 重置为 (0, 0, 0, 0)
                self.current_rois[roi_type] = [0, 0, 0, 0]
                reset_count += 1
            # ✅ 同时清除 _last_emitted 中的记录（避免提示未保存）
            if roi_type in self._last_emitted:
                del self._last_emitted[roi_type]
        
        # ✅ 也要清除背包区域的 _last_emitted（因为要重新框选）
        if 'guns_backpack_roi' in self._last_emitted:
            del self._last_emitted['guns_backpack_roi']
        
        logger.info(f"✅ 已重置 {reset_count} 个枪械 ROI 坐标")
        
        # ✅ 删除已保存的枪械模板（避免使用旧模板）
        self._delete_gun_templates()
        
        # ✅ 重置背包区域（允许重新框选）
        self.backpack_roi = None
        self._backpack_pixmap = None
        self._backpack_abs_coords = None
        
        # ✅ 清除 ROI 标签上的显示
        if hasattr(self, '_roi_label'):
            self._roi_label._current_roi = None
            self._roi_label._update_display()
        
        # ✅ 回到阶段1（_setup_phase1_backpack_selection 内部已刷新下拉框并选中背包）
        self._setup_phase1_backpack_selection()
                
        # 更新显示
        self._update_current_value()
        
        logger.info("✅ 已回退到阶段1，请重新框选背包区域")
        self.status_label.setText(
            "⚠️ 已回退到阶段1 | 所有枪械 ROI 已重置 | 请重新框选背包区域"
        )
    
    def _delete_gun_templates(self):
        """删除已保存的枪械模板（回退阶段时调用）"""
        import logging
        logger = logging.getLogger(__name__)
        from core.paths import res_path
        from core import recognition
        
        categories = ['Name', 'Scope', 'Muzzle', 'Grip', 'Stock']
        deleted_count = 0
        
        for category in categories:
            # 检查三个可能的目录（三级降级）
            template_dirs = [
                res_path('_internal', 'data', 'firearms', self.resolution, category),
                res_path('_internal', 'data', 'firearms', 'default', category),
                res_path('_internal', 'data', 'firearms', category),
            ]
            
            for template_dir in template_dirs:
                if not os.path.exists(template_dir):
                    continue
                
                # 删除 name_1.png, scope_1.png 等文件（由 ROI 工具自动保存的）
                for filename in os.listdir(template_dir):
                    if filename.lower().endswith('.png'):
                        # 只删除 ROI 工具自动保存的模板（name_1, scope_2 等）
                        parts = filename.lower().replace('.png', '').split('_')
                        if len(parts) == 2 and parts[1].isdigit():
                            try:
                                filepath = os.path.join(template_dir, filename)
                                os.remove(filepath)
                                
                                # 清除缓存
                                if filepath in recognition._template_cache:
                                    del recognition._template_cache[filepath]
                                
                                deleted_count += 1
                                logger.debug(f"🗑️ 已删除模板: {filepath}")
                            except Exception as e:
                                logger.warning(f"删除模板失败 {filename}: {e}")
        
        if deleted_count > 0:
            logger.info(f"✅ 已删除 {deleted_count} 个枪械模板")
    
    def _setup_phase1_backpack_selection(self):
        """阶段1：显示全屏截图，框选背包区域"""
        self._phase = "backpack"
        
        # ✅ 更新下拉框为阶段1选项（姿势/背包/开镓）
        self._update_roi_type_combo()
        # 默认选中背包区域
        index = self.roi_type_combo.findData('guns_backpack_roi')
        if index >= 0:
            self.roi_type_combo.blockSignals(True)
            self.roi_type_combo.setCurrentIndex(index)
            self.roi_type_combo.blockSignals(False)
            self._last_roi_type = 'guns_backpack_roi'
        
        # 创建 ROI 标签（全屏模式）
        self._roi_label = ROILabel(self._fullscreen_pixmap, self, mode="fullscreen")
        self.scroll_area.setWidget(self._roi_label)
        
        # ✅ 隐藏回退按钮（阶段1不需要）
        if hasattr(self, 'back_btn'):
            self.back_btn.setVisible(False)
        # ✅ 显示保存模板按钮（阶段1可保存姿势模板）
        if hasattr(self, 'save_template_btn'):
            self.save_template_btn.setVisible(True)

        # ✅ 隐藏固定尺寸配置（阶段1不需要）
        if hasattr(self, 'roi_size_spin_w'):
            for w in (self.roi_size_w_label, self.roi_size_x_label, self.roi_size_h_label, self.roi_size_fixed_label):
                w.setVisible(False)
            for s in (self.roi_size_spin_w, self.roi_size_spin_h):
                s.setVisible(False)
        
        # 更新状态栏
        self.status_label.setText(
            "✅ 【阶段1/2】请框选整个背包区域 → 保存后自动进入阶段2 | 📍 可拖动滚动条查看完整截图"
        )
    
    def _setup_phase2_roi_selection(self):
        """阶段2：显示背包截图，框选 ROI"""
        self._phase = "roi"
        
        # ✅ 阶段2：从 roi_config.json 加载分辨率下的枪械配件 ROI 配置
        import json
        import os
        from core.paths import res_path
        
        config_file = res_path('Config', 'roi_config.json')
        if os.path.exists(config_file):
            with open(config_file, 'r', encoding='utf-8') as f:
                full_config = json.load(f)
            
            # 加载分辨率下的枪械配件 ROI（Name_1、Scope_1 等）
            if self.resolution in full_config:
                res_config = full_config[self.resolution]
                for key, value in res_config.items():
                    # 跳过 posture_roi（已在阶段1处理）
                    if key == 'posture_roi':
                        continue
                    # 加载到 current_rois
                    if value is not None and isinstance(value, (list, tuple)):
                        self.current_rois[key] = list(value)
                
                import logging
                logger = logging.getLogger(__name__)
                logger.info(f"✅ 阶段2：加载了 {len([k for k in res_config.keys() if k != 'posture_roi'])} 个枪械配件 ROI 配置")
        
        # ✅ 切换下拉框为阶段2选项（仅枪械配件）
        self._update_roi_type_combo()
        
        # 移除旧的控件
        if hasattr(self, '_roi_label'):
            old_widget = self._roi_label
            self.scroll_area.setWidget(None)
            old_widget.deleteLater()
        
        # ✅ 创建 ROI 标签（背包模式）
        self._roi_label = ROILabel(self._backpack_pixmap, self, mode="backpack")
        self.scroll_area.setWidget(self._roi_label)

        # ✅ 启用固定尺寸模式，从当前所选ROI类型推断尺寸
        current_type = self.roi_type_combo.currentData()
        fw, fh = self._determine_fixed_size(current_type)
        self.roi_size_spin_w.setValue(fw)
        self.roi_size_spin_h.setValue(fh)
        self._roi_label.set_fixed_size(fw, fh)

        # ✅ 显示尺寸微调控件
        for w in (self.roi_size_w_label, self.roi_size_x_label, self.roi_size_h_label, self.roi_size_fixed_label):
            w.setVisible(True)
        for s in (self.roi_size_spin_w, self.roi_size_spin_h):
            s.setVisible(True)
        
        # ✅ 显示回退按钮和保存模板按钮（阶段2需要）
        if hasattr(self, 'back_btn'):
            self.back_btn.setVisible(True)
        if hasattr(self, 'save_template_btn'):
            self.save_template_btn.setVisible(True)
        
        # ✅ 加载当前 ROI 类型的坐标（如果有配置）
        self._update_current_value()

        # ✅ 如果当前没有配置，自动生成居中预览框
        roi_type = self.roi_type_combo.currentData()
        if roi_type not in self.current_rois or not self.current_rois.get(roi_type):
            self._roi_label.reset_to_center()
            if self._roi_label._current_roi:
                self.current_rois[roi_type] = list(self._roi_label._current_roi)
                self._last_emitted[roi_type] = self._norm_roi(self._roi_label._current_roi)
                self.current_value_label.setText(f"当前: {self._roi_label._current_roi}")
        
        # 更新状态栏
        self.status_label.setText(
            "✅ 【阶段2/2】在背包图上框选 ROI | 🔄 枪械信息自动保存为相对坐标 | 💾 保存当前 ROI 写入一条"
        )
    
    def _setup_hud_mode(self):
        """HUD 配置模式：显示 HUD 截图，框选 Gun_1 和 Gun_2"""
        # ✅ HUD 模式：从 roi_config.json 加载分辨率下的 Gun_1 和 Gun_2 配置
        import json
        import os
        from core.paths import res_path
        
        config_file = res_path('Config', 'roi_config.json')
        if os.path.exists(config_file):
            with open(config_file, 'r', encoding='utf-8') as f:
                full_config = json.load(f)
            
            # 加载分辨率下的 Gun_1 和 Gun_2
            if self.resolution in full_config:
                res_config = full_config[self.resolution]
                for key in ['Gun_1', 'Gun_2']:
                    if key in res_config and res_config[key] is not None:
                        self.current_rois[key] = list(res_config[key])
                
                import logging
                logger = logging.getLogger(__name__)
                logger.info(f"✅ HUD 模式：加载了 Gun_1={self.current_rois.get('Gun_1')}, Gun_2={self.current_rois.get('Gun_2')}")
        
        # 移除旧的控件
        if hasattr(self, '_roi_label'):
            old_widget = self._roi_label
            self.scroll_area.setWidget(None)
            old_widget.deleteLater()
        
        # ✅ 创建 ROI 标签（HUD 模式）
        self._roi_label = ROILabel(self._hud_pixmap, self, mode="hud")
        self.scroll_area.setWidget(self._roi_label)

        # ✅ 启用固定尺寸模式（枪械图标约 284x104）
        # 根据分辨率缩放（以 3840x2160 为基准）
        base_w, base_h = 284, 104
        current_w = self._hud_pixmap.width()
        scale = current_w / 3840.0
        
        # ✅ 优先使用已配置的 Gun_1 或 Gun_2 的框大小，如果没有则使用默认值
        fw, fh = None, None
        for key in ['Gun_1', 'Gun_2']:
            if key in self.current_rois and self.current_rois[key]:
                roi_data = self.current_rois[key]
                if len(roi_data) == 4:
                    l, t, r, b = roi_data
                    fw = r - l
                    fh = b - t
                    import logging
                    logger = logging.getLogger(__name__)
                    logger.info(f"✅ HUD 模式：使用已配置的 {key} 框大小: {fw}x{fh}")
                    break
        
        # 如果没有已配置的数据，使用默认值
        if fw is None or fh is None:
            fw = max(50, int(base_w * scale))
            fh = max(30, int(base_h * scale))
            import logging
            logger = logging.getLogger(__name__)
            logger.info(f"✅ HUD 模式：使用默认框大小: {fw}x{fh}")
        
        self.roi_size_spin_w.setValue(fw)
        self.roi_size_spin_h.setValue(fh)
        self._roi_label.set_fixed_size(fw, fh)

        # ✅ 显示尺寸微调控件
        for w in (self.roi_size_w_label, self.roi_size_x_label, self.roi_size_h_label, self.roi_size_fixed_label):
            w.setVisible(True)
        for s in (self.roi_size_spin_w, self.roi_size_spin_h):
            s.setVisible(True)
        
        # ✅ 隐藏回退按钮（HUD 配置不需要）
        if hasattr(self, 'back_btn'):
            self.back_btn.setVisible(False)
        # ✅ 显示保存模板按钮（HUD 配置需要保存枪械图标模板）
        if hasattr(self, 'save_template_btn'):
            self.save_template_btn.setVisible(True)
        
        # ✅ 更新下拉框为 HUD 选项（只显示 Gun_1 和 Gun_2）
        self.roi_type_combo.blockSignals(True)
        self.roi_type_combo.clear()
        hud_types = ['Gun_1', 'Gun_2']
        for key in hud_types:
            self.roi_type_combo.addItem(self.ROI_TYPES[key], key)
        self.roi_type_combo.blockSignals(False)
        
        # ✅ 加载当前 ROI 类型的坐标（如果有配置）
        self._update_current_value()

        # ✅ 如果当前没有配置，自动生成居中预览框
        roi_type = self.roi_type_combo.currentData()
        if roi_type in self.RELATIVE_TO_HUD:
            if roi_type not in self.current_rois or not self.current_rois.get(roi_type):
                self._roi_label.reset_to_center()
                if self._roi_label._current_roi:
                    self.current_rois[roi_type] = list(self._roi_label._current_roi)
                    self._last_emitted[roi_type] = self._norm_roi(self._roi_label._current_roi)
                    self.current_value_label.setText(f"相对HUD: {self._roi_label._current_roi}")
        
        # 更新状态栏
        self.status_label.setText(
            "✅ 【HUD 配置】在 HUD 截图中框选 Gun_1 和 Gun_2 | 🔄 坐标自动保存为相对 HUD 的坐标"
        )
        
        print(f"   ✅ 已切换到 HUD 配置模式")
    
    def _update_current_value(self):
        """更新当前 ROI 值显示"""
        roi_type = self.roi_type_combo.currentData()
        
        # ✅ 特殊处理：hud_gun_icons 从 self.hud_roi 读取（存储在 _GUN_HUD_SETTINGS 中）
        if roi_type == 'hud_gun_icons':
            current = self.hud_roi
        else:
            current = self.current_rois.get(roi_type)
        
        # ✅ 切换类型时先清空旧 ROI，避免残留显示上一次选择的类型的框
        if hasattr(self, '_roi_label') and self._roi_label:
            self._roi_label._current_roi = None

        import logging
        logger = logging.getLogger(__name__)
        logger.debug(f"🔄 _update_current_value: roi_type={roi_type}, current={current}")

        if current:
            # ✅ 显示当前配置的坐标
            self.current_value_label.setText(f"当前: {current}")
            
            # ✅ 根据 ROI 类型处理显示
            if roi_type == 'guns_backpack_roi':
                # 背包区域: (left, top, right, bottom) - 已经是绝对坐标，直接显示
                if len(current) == 4:
                    display_roi = tuple(current)
                    if hasattr(self, '_roi_label'):
                        self._roi_label._current_roi = display_roi
                        self._roi_label._update_display()
                else:
                    if hasattr(self, '_roi_label'):
                        self._roi_label._current_roi = None
                        self._roi_label._update_display()
                        
            elif roi_type == 'right_click_pos':
                # 开镜坐标: (x, y) -> 不显示框
                if hasattr(self, '_roi_label'):
                    self._roi_label._current_roi = None
                    self._roi_label._update_display()
            
            elif roi_type == 'hud_gun_icons':
                # HUD 区域: (left, top, right, bottom) - 已经是绝对坐标，直接显示
                if len(current) == 4:
                    display_roi = tuple(current)
                    if hasattr(self, '_roi_label'):
                        self._roi_label._current_roi = display_roi
                        self._roi_label._update_display()
                else:
                    if hasattr(self, '_roi_label'):
                        self._roi_label._current_roi = None
                        self._roi_label._update_display()
                    
            elif roi_type in self.RELATIVE_TO_HUD:
                # 枪械图标: 相对于 HUD 区域的坐标，直接在 HUD 截图上显示
                if hasattr(self, '_hud_pixmap') and self._hud_pixmap:
                    # 显示在 HUD 截图上（坐标已经是相对的）
                    if hasattr(self, '_roi_label'):
                        if self._roi_label._fixed_size_mode and len(current) == 4:
                            l, t, r, b = current
                            cx = (l + r) // 2
                            cy = (t + b) // 2
                            fw = self._roi_label._fixed_w
                            fh = self._roi_label._fixed_h
                            self._roi_label._current_roi = (
                                cx - fw // 2, cy - fh // 2,
                                cx + fw // 2, cy + fh // 2
                            )
                        else:
                            self._roi_label._current_roi = current
                        self._roi_label._update_display()
                    self.current_value_label.setText(f"相对HUD: {current}")
                else:
                    if hasattr(self, '_roi_label'):
                        self._roi_label._current_roi = None
                        self._roi_label._update_display()
                    
            elif roi_type in self.RELATIVE_TO_BACKPACK:
                # ✅ 枪械信息: 根据阶段决定如何显示
                if self._phase == "roi" and hasattr(self._roi_label, '_mode') and self._roi_label._mode == "backpack":
                    # 阶段2：坐标已经是相对坐标，直接显示
                    # 固定尺寸模式下，将已有 ROI 缩放到固定尺寸，保持中心
                    if hasattr(self, '_roi_label'):
                        if self._roi_label._fixed_size_mode and len(current) == 4:
                            l, t, r, b = current
                            cx = (l + r) // 2
                            cy = (t + b) // 2
                            fw = self._roi_label._fixed_w
                            fh = self._roi_label._fixed_h
                            self._roi_label._current_roi = (
                                cx - fw // 2, cy - fh // 2,
                                cx + fw // 2, cy + fh // 2
                            )
                        else:
                            self._roi_label._current_roi = current
                        self._roi_label._update_display()
                else:
                    # 阶段1：相对坐标 -> 转换为屏幕绝对坐标用于显示
                    if self.backpack_roi and len(self.backpack_roi) == 4 and len(current) == 4:
                        backpack_left, backpack_top, backpack_right, backpack_bottom = self.backpack_roi
                        rel_left, rel_top, rel_right, rel_bottom = current
                        
                        # 转换为绝对坐标
                        abs_left = backpack_left + rel_left
                        abs_top = backpack_top + rel_top
                        abs_right = backpack_left + rel_right
                        abs_bottom = backpack_top + rel_bottom
                        
                        display_roi = (abs_left, abs_top, abs_right, abs_bottom)
                        
                        import logging
                        logger = logging.getLogger(__name__)
                        logger.debug(f"🔄 显示转换: {roi_type} 相对{current} → 绝对{display_roi}")
                        
                        if hasattr(self, '_roi_label'):
                            self._roi_label._current_roi = display_roi
                            self._roi_label._update_display()
                    else:
                        # 没有背包区域，无法显示
                        if hasattr(self, '_roi_label'):
                            self._roi_label._current_roi = None
                            self._roi_label._update_display()
            else:
                # 标准 ROI 类型，在图片上显示框
                if hasattr(self, '_roi_label'):
                    self._roi_label._current_roi = current
                    self._roi_label._update_display()
        else:
            self.current_value_label.setText("未设置")
            # 清除 ROI 标签上的显示
            if hasattr(self, '_roi_label'):
                self._roi_label._current_roi = None
                self._roi_label._update_display()

    def _determine_fixed_size(self, roi_type):
        """根据 ROI 类型、分辨率和现有模板推断固定尺寸。返回 (w, h)。"""
        # ✅ 基准分辨率 2560x1440 的默认尺寸（已优化好的尺寸）
        base_name_default = (72, 30)
        base_other_default = (66, 50)  # Scope/Muzzle/Grip/Stock
        
        # ✅ 各分辨率相对于 2560x1440 的缩放比例（宽比例, 高比例）
        BASE_RES = (2560, 1440)
        SCALE_MAP = {
            "3840x2160": (3840/2560, 2160/1440),
            "3440x1440": (3440/2560, 1440/1440),
            "2560x1600": (2560/2560, 1600/1440),
            "2560x1440": (1.0, 1.0),
            "2304x1440": (2304/2560, 1440/1440),
            "2560x1080": (2560/2560, 1080/1440),
            "1920x1080": (1920/2560, 1080/1440),
            "1728x1080": (1728/2560, 1080/1440),
        }
        
        sx, sy = SCALE_MAP.get(self.resolution, (1.0, 1.0))
        if 'Name' in roi_type:
            default = (int(base_name_default[0] * sx), int(base_name_default[1] * sy))
        else:
            default = (int(base_other_default[0] * sx), int(base_other_default[1] * sy))

        # 从现有模板目录推断尺寸（模板尺寸优先级高于默认值）
        from core.paths import res_path
        category = None
        if 'Name' in roi_type:
            category = 'Name'
        elif 'Scope' in roi_type:
            category = 'Scope'
        elif 'Muzzle' in roi_type:
            category = 'Muzzle'
        elif 'Grip' in roi_type:
            category = 'Grip'
        elif 'Stock' in roi_type:
            category = 'Stock'

        if not category:
            return default

        # 优先从本分辨率模板目录读取
        template_dir = res_path('_internal', 'data', 'firearms', self.resolution, category)
        if not os.path.exists(template_dir):
            template_dir = res_path('_internal', 'data', 'firearms', category)
            if not os.path.exists(template_dir):
                return default

        import cv2
        sizes = []
        for fname in os.listdir(template_dir):
            if not fname.lower().endswith('.png'):
                continue
            fpath = os.path.join(template_dir, fname)
            img = cv2.imread(fpath, cv2.IMREAD_GRAYSCALE)
            if img is not None:
                h, w = img.shape[:2]
                sizes.append((w, h))

        if not sizes:
            return default

        # 取最常见尺寸（众数）
        from collections import Counter
        counter = Counter(sizes)
        most_common = counter.most_common(1)[0][0]
        return most_common

    def _on_fixed_size_changed(self):
        """固定尺寸微调框值改变时，更新 ROILabel 的固定尺寸。"""
        w = self.roi_size_spin_w.value()
        h = self.roi_size_spin_h.value()
        if hasattr(self, '_roi_label') and self._roi_label:
            # 如果已有 ROI，保持中心位置不变，只更新尺寸
            old_roi = self._roi_label._current_roi
            self._roi_label.set_fixed_size(w, h)
            if old_roi:
                l, t, r, b = old_roi
                cx = (l + r) // 2
                cy = (t + b) // 2
                new_l = cx - w // 2
                new_t = cy - h // 2
                self._roi_label._current_roi = (new_l, new_t, new_l + w, new_t + h)
                self._roi_label._update_display()
                if hasattr(self, '_on_roi_dragged'):
                    self._on_roi_dragged(self._roi_label._current_roi)
    
    def roi_type_changed(self):
        """ROI 类型改变时更新显示"""
        import logging
        logger = logging.getLogger(__name__)
        logger.debug(f"🔄 roi_type_changed: _last_roi_type={self._last_roi_type}, new={self.roi_type_combo.currentData()}")

        # ✅ 自动保存上一个 ROI 类型的调整结果
        if self._last_roi_type and hasattr(self, '_roi_label') and self._roi_label._current_roi:
            # 保存上一个类型的 ROI
            raw_roi = self._roi_label._current_roi
            
            # ✅ 只有标准 ROI 类型才从 _roi_label 获取并保存
            if self._last_roi_type not in ('guns_backpack_roi', 'right_click_pos'):
                # 如果是枪械信息，需要转换回屏幕坐标再保存（因为显示的是相对坐标）
                if self._last_roi_type in self.RELATIVE_TO_BACKPACK and self.backpack_roi:
                    # TODO: 如果需要反向转换，可以在这里实现
                    # 目前简单处理：直接保存当前值
                    self.current_rois[self._last_roi_type] = list(raw_roi)
                    
                else:
                    self.current_rois[self._last_roi_type] = list(raw_roi)
                
                logger.info(f"✅ 自动保存 {self._last_roi_type}: {raw_roi}")

            # ✅ 同步更新 _last_emitted，避免关闭时误报"未保存"
            if self._last_roi_type not in ('guns_backpack_roi', 'right_click_pos'):
                self._last_emitted[self._last_roi_type] = self._norm_roi(raw_roi)
        
        # 更新当前类型
        new_roi_type = self.roi_type_combo.currentData()
        
        # ✅ 如果选择背包区域且已配置，提示是否直接进入二阶段
        if new_roi_type == 'guns_backpack_roi' and self.backpack_roi and len(self.backpack_roi) == 4:
            reply = QMessageBox.question(
                self,
                "📦 检测到已配置的背包区域",
                f"背包区域已配置：\n"
                f"位置: ({self.backpack_roi[0]}, {self.backpack_roi[1]}, {self.backpack_roi[2]}, {self.backpack_roi[3]})\n\n"
                f"是否直接进入阶段2（调整枪械 ROI）？\n"
                f"• 是 → 进入阶段2\n"
                f"• 否 → 重新框选背包区域",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.Yes
            )
            
            if reply == QMessageBox.Yes:
                # 直接进入阶段2
                print("✅ 用户选择：直接进入背包阶段2")
                self._extract_backpack_from_fullscreen()
                self._setup_phase2_roi_selection()
                self._select_first_configured_roi()
                return
            else:
                # 用户选择重新框选，继续正常流程
                print("✅ 用户选择：重新框选背包区域")
        
        # ✅ 如果选择 HUD 区域且已配置，提示是否直接进入 HUD 配置模式
        if new_roi_type == 'hud_gun_icons' and self.hud_roi and len(self.hud_roi) == 4:
            reply = QMessageBox.question(
                self,
                "🎯 检测到已配置的 HUD 区域",
                f"HUD 枪械图标区域已配置：\n"
                f"位置: ({self.hud_roi[0]}, {self.hud_roi[1]}, {self.hud_roi[2]}, {self.hud_roi[3]})\n\n"
                f"是否直接进入 HUD 配置模式（调整 Gun_1 和 Gun_2）？\n"
                f"• 是 → 进入 HUD 配置\n"
                f"• 否 → 重新框选 HUD 区域",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.Yes
            )
            
            if reply == QMessageBox.Yes:
                # 直接进入 HUD 配置模式
                print("✅ 用户选择：直接进入 HUD 配置模式")
                # 裁剪 HUD 区域
                left, top, right, bottom = self.hud_roi
                width = right - left
                height = bottom - top
                self._hud_pixmap = self._fullscreen_pixmap.copy(
                    int(left), int(top), int(width), int(height)
                )
                # 切换到 HUD 模式
                self._setup_hud_mode()
                # 自动选择第一个已配置的 Gun
                self._select_first_configured_hud_roi()
                return
            else:
                # 用户选择重新框选，继续正常流程
                print("✅ 用户选择：重新框选 HUD 区域")
        
        # ✅ 如果切换到枪械信息类型，检查是否已配置背包区域
        if new_roi_type in self.RELATIVE_TO_BACKPACK and not self.backpack_roi:
            logger.warning(f"⚠️ 请先配置背包区域，否则 {new_roi_type} 无法正确转换坐标")
            
            # ✅ 弹出提示并自动切换回背包区域选项
            reply = QMessageBox.question(
                self,
                "⚠️ 需要先配置背包区域",
                f"在配置「{self.ROI_TYPES.get(new_roi_type)}」之前，\n"
                f"必须先配置「背包截图区域」！\n\n"
                f"是否现在切换到「背包截图区域」进行配置？",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.Yes
            )
            
            if reply == QMessageBox.Yes:
                # 自动切换到背包区域选项
                index = self.roi_type_combo.findData('guns_backpack_roi')
                if index >= 0:
                    self.roi_type_combo.blockSignals(True)  # 阻止信号循环
                    self.roi_type_combo.setCurrentIndex(index)
                    self.roi_type_combo.blockSignals(False)
                    self._last_roi_type = 'guns_backpack_roi'
                    logger.info("✅ 自动切换到背包区域配置")
                    # 更新显示
                    self._update_current_value()
                    return
            else:
                # 用户选择取消，保持原样但给出提示
                self.status_label.setText(
                    f"⚠️ 请先配置背包区域，再配置 {self.ROI_TYPES.get(new_roi_type)}"
                )
                return
        
        # ✅ 如果切换到 HUD 枪械图标类型，检查是否已配置 HUD 区域
        if new_roi_type in self.RELATIVE_TO_HUD and not self.hud_roi:
            logger.warning(f"⚠️ 请先配置 HUD 枪械图标区域，否则 {new_roi_type} 无法正确转换坐标")
            
            reply = QMessageBox.question(
                self,
                "⚠️ 需要先配置 HUD 区域",
                f"在配置「{self.ROI_TYPES.get(new_roi_type)}」之前，\n"
                f"必须先配置「HUD 枪械图标区域」！\n\n"
                f"是否现在切换到「HUD 枪械图标区域」进行配置？",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.Yes
            )
            
            if reply == QMessageBox.Yes:
                index = self.roi_type_combo.findData('hud_gun_icons')
                if index >= 0:
                    self.roi_type_combo.blockSignals(True)
                    self.roi_type_combo.setCurrentIndex(index)
                    self.roi_type_combo.blockSignals(False)
                    self._last_roi_type = 'hud_gun_icons'
                    logger.info("✅ 自动切换到 HUD 枪械图标区域配置")
                    self._update_current_value()
                    return
            else:
                self.status_label.setText(
                    f"⚠️ 请先配置 HUD 枪械图标区域，再配置 {self.ROI_TYPES.get(new_roi_type)}"
                )
                return
        
        self._last_roi_type = new_roi_type
        
        # ✅ 先更新固定尺寸（必须在 _update_current_value 之前，否则会用旧类型的尺寸显示新类型的框）
        if self._phase == "roi" and hasattr(self, '_roi_label') and self._roi_label._fixed_size_mode:
            if new_roi_type in self.RELATIVE_TO_BACKPACK or new_roi_type == 'posture_roi':
                fw, fh = self._determine_fixed_size(new_roi_type)
                self.roi_size_spin_w.blockSignals(True)
                self.roi_size_spin_h.blockSignals(True)
                self.roi_size_spin_w.setValue(fw)
                self.roi_size_spin_h.setValue(fh)
                self.roi_size_spin_w.blockSignals(False)
                self.roi_size_spin_h.blockSignals(False)
                self._roi_label.set_fixed_size(fw, fh)
        
        # ✅ 再加载新类型的 ROI 坐标（此时 _fixed_w/_fixed_h 已是新值）
        self._update_current_value()
        
        # ✅ 强制重绘
        if hasattr(self, '_roi_label'):
            self._roi_label.repaint()
    
    def _on_roi_dragged(self, new_roi):
        """当用户拖动 ROI 框时调用"""
        if new_roi:
            roi_type = self.roi_type_combo.currentData()
            
            # ✅ 特殊类型（背包区域、开镜坐标、HUD区域）不在图片上显示框，不处理拖动
            if roi_type in ('guns_backpack_roi', 'right_click_pos', 'hud_gun_icons'):
                return
            
            # ✅ 如果是枪械信息 ROI（相对于背包）
            if roi_type in self.RELATIVE_TO_BACKPACK:
                # 根据阶段决定如何处理坐标
                if self._phase == "roi" and hasattr(self._roi_label, '_mode') and self._roi_label._mode == "backpack":
                    # 阶段2：坐标已经是相对坐标，直接使用
                    relative_roi = new_roi
                    display_roi = relative_roi
                    self.current_value_label.setText(f"相对背包: {relative_roi}")
                else:
                    # 阶段1：需要转换
                    relative_roi = self._convert_to_relative(roi_type, new_roi)
                    display_roi = relative_roi
                    # 显示两种坐标：屏幕坐标 -> 相对坐标
                    self.current_value_label.setText(
                        f"屏幕: {new_roi} → 相对背包: {relative_roi}"
                    )
                
                # 同时更新 current_rois 中的相对坐标
                self.current_rois[roi_type] = list(relative_roi)
            
            # ✅ 如果是枪械图标 ROI（相对于 HUD）
            elif roi_type in self.RELATIVE_TO_HUD:
                # 坐标已经是相对于 HUD 大图的坐标，直接使用
                relative_roi = new_roi
                display_roi = relative_roi
                self.current_value_label.setText(f"相对HUD: {relative_roi}")
                self.current_rois[roi_type] = list(relative_roi)
            
            else:
                # 其他类型，直接显示
                display_roi = new_roi
                self.current_rois[roi_type] = list(new_roi)
                self.current_value_label.setText(f"当前: {new_roi}")
            
            # 自动计算置信度
            self._calculate_confidence()
    
    def _calculate_confidence(self):
        """计算并显示置信度"""
        roi_type = self.roi_type_combo.currentData()
        
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
    
    @staticmethod
    def _norm_roi(v):
        if v is None:
            return None
        t = v if isinstance(v, tuple) else tuple(v)
        return tuple(int(x) for x in t)
    
    def _convert_to_relative(self, roi_type, screen_coords):
        """
        将屏幕绝对坐标转换为相对于背包区域的坐标
        
        【坐标格式规范】
        - 输入：(left, top, right, bottom) 屏幕绝对坐标
        - 输出：(left, top, right, bottom) 相对于背包左上角的相对坐标
        
        :param roi_type: ROI 类型
        :param screen_coords: 屏幕绝对坐标 (left, top, right, bottom)
        :return: 相对坐标 (left, top, right, bottom)
        """
        if roi_type not in self.RELATIVE_TO_BACKPACK:
            return screen_coords
        
        if not self.backpack_roi or len(self.backpack_roi) != 4:
            # 如果没有背包区域信息，返回原始坐标
            import logging
            logger = logging.getLogger(__name__)
            logger.warning(f"⚠️ 未配置背包区域，无法转换 {roi_type} 为相对坐标")
            return screen_coords
        
        # 背包区域格式: (left, top, right, bottom) - 屏幕绝对坐标
        backpack_left, backpack_top, backpack_right, backpack_bottom = self.backpack_roi
        
        # 屏幕坐标: (left, top, right, bottom)
        screen_left, screen_top, screen_right, screen_bottom = screen_coords
        
        # 转换为相对坐标
        relative_left = screen_left - backpack_left
        relative_top = screen_top - backpack_top
        relative_right = screen_right - backpack_left
        relative_bottom = screen_bottom - backpack_top
        
        import logging
        logger = logging.getLogger(__name__)
        logger.info(f"🔄 坐标转换: {roi_type}")
        logger.info(f"   背包区域（绝对坐标）: left={backpack_left}, top={backpack_top}, right={backpack_right}, bottom={backpack_bottom}")
        logger.info(f"   屏幕坐标: {screen_coords}")
        logger.info(f"   相对坐标: ({relative_left}, {relative_top}, {relative_right}, {relative_bottom})")
        
        return (relative_left, relative_top, relative_right, relative_bottom)

    def _effective_rois(self):
        """与界面一致的 ROI 表（含当前类型下未点「保存」的编辑）。"""
        # ✅ 过滤掉特殊配置节点（_GUN_HUD_SETTINGS 等）
        eff = {k: v for k, v in self.current_rois.items() 
               if v is not None and not k.startswith('_')}
        t = self.roi_type_combo.currentData()
        if not hasattr(self, "_roi_label") or self._roi_label is None:
            return eff
        lb = self._roi_label
        if lb._current_roi is not None:
            eff[t] = list(lb._current_roi)
        else:
            gr = lb.get_roi()
            if gr:
                eff[t] = list(gr)
        return eff

    def _has_unsaved_changes(self):
        eff = self._effective_rois()
        for k, v in eff.items():
            cur = self._norm_roi(v)
            if k not in self._last_emitted or self._last_emitted[k] != cur:
                return True
        for k, last in self._last_emitted.items():
            if k not in eff and last is not None:
                return True
        return False

    def _ok_to_close(self):
        # ✅ 关闭时直接丢弃所有未保存的修改，不提示、不自动保存
        return True

    def _on_reset_position(self):
        """重置当前 ROI 位置，允许重新框选"""
        roi_type = self.roi_type_combo.currentData()
        roi_name = self.ROI_TYPES.get(roi_type, roi_type)
        
        # ✅ 阶段2固定尺寸模式：重置到居中位置（先刷新分辨率适配的固定尺寸）
        if self._phase == "roi" and hasattr(self, '_roi_label') and self._roi_label._fixed_size_mode:
            # ✅ 重新按当前分辨率计算固定尺寸，避免用旧尺寸重置
            if roi_type in self.RELATIVE_TO_BACKPACK or roi_type == 'posture_roi':
                fw, fh = self._determine_fixed_size(roi_type)
                self.roi_size_spin_w.blockSignals(True)
                self.roi_size_spin_h.blockSignals(True)
                self.roi_size_spin_w.setValue(fw)
                self.roi_size_spin_h.setValue(fh)
                self.roi_size_spin_w.blockSignals(False)
                self.roi_size_spin_h.blockSignals(False)
                self._roi_label.set_fixed_size(fw, fh)
            
            self._roi_label.reset_to_center()
            # 保存到 current_rois
            if self._roi_label._current_roi:
                self.current_rois[roi_type] = list(self._roi_label._current_roi)
                self._last_emitted[roi_type] = self._norm_roi(self._roi_label._current_roi)
                self.current_value_label.setText(f"当前: {self._roi_label._current_roi}")
                self.confidence_label.setText("")
                self.status_label.setText(f"已重置 {roi_name} 到居中位置")
            return
        
        # 清除当前 ROI
        if hasattr(self, '_roi_label'):
            self._roi_label._current_roi = None
            self._roi_label.cancel_ongoing()
            self._roi_label._update_display()
        
        # 从 current_rois 中移除
        if roi_type in self.current_rois:
            del self.current_rois[roi_type]
        
        # 更新显示
        self.current_value_label.setText("未设置（请重新框选）")
        self.confidence_label.setText("")
        
        # 提示用户
        self.status_label.setText(f"已重置 {roi_name}，请在截图上拖动鼠标重新框选")
        
        import logging
        logger = logging.getLogger(__name__)
        logger.info(f"✅ 已重置 {roi_type} 的 ROI 位置")
    
    def _on_save(self):
        """保存 ROI"""
        roi_type = self.roi_type_combo.currentData()
        
        # ✅ 如果是枪械信息 ROI，必须先配置背包区域
        if roi_type in self.RELATIVE_TO_BACKPACK:
            if not self.backpack_roi or len(self.backpack_roi) != 4:
                QMessageBox.warning(
                    self,
                    "⚠️ 需要先配置背包区域",
                    f"在配置「{self.ROI_TYPES.get(roi_type)}」之前，\n"
                    f"必须先配置「背包截图区域」！\n\n"
                    f"操作步骤：\n"
                    f"1. 在上方下拉框选择「背包截图区域 (GUNS_REOLUTION_SETTINGS)」\n"
                    f"2. 在全屏截图中框选整个背包区域\n"
                    f"3. 点击「保存当前 ROI」\n"
                    f"4. 然后再回来配置枪械信息 ROI"
                )
                return
        
        # ✅ 如果是枪械图标 ROI，必须先配置 HUD 区域
        if roi_type in self.RELATIVE_TO_HUD:
            if not self.hud_roi or len(self.hud_roi) != 4:
                QMessageBox.warning(
                    self,
                    "⚠️ 需要先配置 HUD 区域",
                    f"在配置「{self.ROI_TYPES.get(roi_type)}」之前，\n"
                    f"必须先配置「HUD 枪械图标区域」！\n\n"
                    f"操作步骤：\n"
                    f"1. 在上方下拉框选择「HUD 枪械图标区域（右下角）」\n"
                    f"2. 在全屏截图中框选 HUD 区域（包含两把枪图标）\n"
                    f"3. 点击「保存当前 ROI」\n"
                    f"4. 然后再回来配置 Gun_1 和 Gun_2"
                )
                return
        
        # 优先使用拖动后的 ROI，如果没有则使用框选的
        roi = self._roi_label._current_roi if self._roi_label._current_roi else self._roi_label.get_roi()
        
        if not roi:
            QMessageBox.warning(self, "提示", "请先框选一个区域或拖动已有区域")
            return
        
        roi_name = self.ROI_TYPES.get(roi_type, roi_type)
        roi_t = self._norm_roi(roi)
        
        # ✅ 根据 ROI 类型处理坐标
        saved_coords = None
        if roi_type == 'guns_backpack_roi':
            # 背包区域: 直接使用 (left, top, right, bottom) 格式（屏幕绝对坐标）
            left, top, right, bottom = roi_t
            backpack_coords = (left, top, right, bottom)
            
            self.current_rois[roi_type] = list(backpack_coords)
            # 发送保存信号（使用原始坐标）
            self.roi_saved.emit(roi_type, backpack_coords)
            self._last_emitted[roi_type] = self._norm_roi(backpack_coords)
            
            # 更新 backpack_roi（用于后续相对坐标转换）
            self.backpack_roi = backpack_coords
            saved_coords = backpack_coords
            
            import logging
            logger = logging.getLogger(__name__)
            logger.info(f"✅ 背包区域已保存: {backpack_coords}")
            
            # ✅ 裁剪背包区域，准备阶段2
            left, top, right, bottom = roi_t
            width = right - left
            height = bottom - top
            self._backpack_abs_coords = (left, top, right, bottom)
            self._backpack_pixmap = self._fullscreen_pixmap.copy(
                int(left), int(top), int(width), int(height)
            )
            
            print(f"\n✅ 背包区域已裁剪: {width}x{height}")
            print(f"   准备进入阶段2...")
            
            # ✅ 自动切换到阶段2（_setup_phase2_roi_selection 内部已刷新下拉框）
            self._setup_phase2_roi_selection()
            
            # 自动切换到第一个 ROI 类型
            index = self.roi_type_combo.findData('Name_1')
            if index >= 0:
                self.roi_type_combo.blockSignals(True)
                self.roi_type_combo.setCurrentIndex(index)
                self.roi_type_combo.blockSignals(False)
                self._last_roi_type = 'Name_1'
            # ✅ 切换类型后同步更新画布显示
            self._update_current_value()
            
        elif roi_type == 'right_click_pos':
            # 开镜坐标: 只取左上角点 (x, y)
            left, top, right, bottom = roi_t
            click_coords = (left, top)
            
            self.current_rois[roi_type] = list(click_coords)
            self.roi_saved.emit(roi_type, click_coords)
            self._last_emitted[roi_type] = click_coords
            saved_coords = click_coords
            
            import logging
            logger = logging.getLogger(__name__)
            logger.info(f"✅ 开镜坐标已保存: {click_coords}")
        
        elif roi_type == 'hud_gun_icons':
            # HUD 枪械图标区域: 使用屏幕绝对坐标 (left, top, right, bottom)
            left, top, right, bottom = roi_t
            hud_coords = (left, top, right, bottom)
            
            self.current_rois[roi_type] = list(hud_coords)
            self.roi_saved.emit(roi_type, hud_coords)
            self._last_emitted[roi_type] = self._norm_roi(hud_coords)
            
            # 更新 hud_roi（用于后续相对坐标转换）
            self.hud_roi = hud_coords
            saved_coords = hud_coords
            
            import logging
            logger = logging.getLogger(__name__)
            logger.info(f"✅ HUD 枪械图标区域已保存: {hud_coords}")
            
            # ✅ 裁剪 HUD 区域，用于后续配置 Gun_1 和 Gun_2
            left, top, right, bottom = roi_t
            width = right - left
            height = bottom - top
            self._hud_pixmap = self._fullscreen_pixmap.copy(
                int(left), int(top), int(width), int(height)
            )
            
            print(f"\n✅ HUD 枪械图标区域已裁剪: {width}x{height}")
            print(f"   准备进入 HUD 配置模式...")
            
            # ✅ 切换到 HUD 配置模式（类似阶段2）
            self._setup_hud_mode()
            
            # 自动切换到 Gun_1
            index = self.roi_type_combo.findData('Gun_1')
            if index >= 0:
                self.roi_type_combo.blockSignals(True)
                self.roi_type_combo.setCurrentIndex(index)
                self.roi_type_combo.blockSignals(False)
                self._last_roi_type = 'Gun_1'
            self._update_current_value()
        
        elif roi_type in self.RELATIVE_TO_HUD:
            # 枪械图标 ROI（相对于 HUD 区域）
            # 坐标已经是相对于 HUD 大图的坐标，直接使用
            relative_roi = roi_t
            
            self.current_rois[roi_type] = list(relative_roi)
            self.roi_saved.emit(roi_type, relative_roi)
            self._last_emitted[roi_type] = self._norm_roi(relative_roi)
            saved_coords = relative_roi
            
            import logging
            logger = logging.getLogger(__name__)
            logger.info(f"✅ {roi_type} 已保存 (相对HUD): {relative_roi}")
            
        elif roi_type in self.RELATIVE_TO_BACKPACK:
            # 枪械信息 ROI
            # ✅ 如果在阶段2（背包模式），坐标天然就是相对坐标，无需转换
            if self._phase == "roi" and hasattr(self._roi_label, '_mode') and self._roi_label._mode == "backpack":
                # 直接使用框选的坐标（已经是相对坐标）
                relative_roi = roi_t
                import logging
                logger = logging.getLogger(__name__)
                logger.info(f"✅ 阶段2框选: {roi_type} 直接使用相对坐标: {relative_roi}")
            else:
                # 阶段1（全屏模式），需要转换
                relative_roi = self._convert_to_relative(roi_type, roi_t)
            
            self.current_rois[roi_type] = list(relative_roi)
            # 发送保存信号（使用转换后的相对坐标）
            self.roi_saved.emit(roi_type, relative_roi)
            self._last_emitted[roi_type] = self._norm_roi(relative_roi)
            saved_coords = relative_roi
            
        else:
            # 其他 ROI 类型，直接保存
            self.current_rois[roi_type] = list(roi_t)
            # 发送保存信号
            self.roi_saved.emit(roi_type, roi_t)
            self._last_emitted[roi_type] = roi_t
            saved_coords = roi_t
        
        self.status_label.setText(
            f"已保存到配置: {roi_name} | {roi_t} | {self.resolution}（可继续调整其他类型）"
        )
        
        # ✅ 显示裁剪预览，让用户确认
        self._show_roi_preview(roi_type, roi_t, saved_coords)
    
    def _on_save_hud_gun_template(self, roi_type):
        """保存 HUD 枪械图标模板（Gun_1 或 Gun_2）"""
        import logging
        logger = logging.getLogger(__name__)
        from core.paths import res_path
        
        # 1. 获取当前 ROI 坐标
        roi = None
        if hasattr(self, '_roi_label') and self._roi_label:
            roi = self._roi_label._current_roi or self._roi_label.get_roi()
        
        if not roi:
            QMessageBox.warning(self, "提示", "请先在 HUD 截图中框选一个区域")
            return
        
        # 2. 扫描已有枪械图标模板名称
        existing_names = []
        search_dirs = [
            res_path('_internal', 'data', 'firearms', self.resolution, 'gun'),
            res_path('_internal', 'data', 'firearms', 'gun'),
        ]
        for d in search_dirs:
            if os.path.exists(d):
                for f in os.listdir(d):
                    if f.lower().endswith('.png'):
                        name = f[:-4]  # 去掉 .png
                        if name not in existing_names:
                            existing_names.append(name)
        
        # 排序：none 放最后
        if 'none' in existing_names:
            existing_names.remove('none')
            existing_names.sort()
            existing_names.append('none')
        else:
            existing_names.sort()
        
        # 添加自定义名称选项
        existing_names.append("——— 输入自定义名称 ———")
        
        # 3. 下拉对话框让用户选择模板名称
        selected, ok = QInputDialog.getItem(
            self,
            f"选择枪械图标模板 - {self.ROI_TYPES.get(roi_type)}",
            f"当前ROI坐标: {roi}\n"
            f"请选择或输入模板名称（可双击编辑自由输入）:\n"
            f"建议与游戏内枪械名称一致",
            existing_names,
            0,
            True  # 可编辑
        )
        
        if not ok or not selected.strip():
            logger.info(f"❌ 用户取消选择枪械图标模板: {roi_type}")
            return
        
        # 清理用户选择的名称
        selected_name = selected.strip()
        if selected_name == "——— 输入自定义名称 ———":
            # 用户选了输入自定义名称却没改文字，跳到输入框
            custom_name, ok2 = QInputDialog.getText(
                self,
                f"输入枪械图标模板名称 - {self.ROI_TYPES.get(roi_type)}",
                f"请输入模板名称（不包含扩展名）:\n"
                f"例如: m416, m762, kar98k\n"
                f"建议与游戏内枪械名称一致",
                QLineEdit.Normal,
                ""
            )
            if not ok2 or not custom_name.strip():
                logger.info(f"❌ 用户取消输入枪械图标模板名称: {roi_type}")
                return
            selected_name = custom_name.strip()
        
        logger.info(f"✅ 用户选择枪械图标模板名称: {selected_name} ({roi_type})")
        
        # 4. 用户确认是否生成
        roi_name = self.ROI_TYPES.get(roi_type, roi_type)
        reply = QMessageBox.question(
            self,
            "确认保存枪械图标模板",
            f"即将从当前「{roi_name}」截图生成枪械图标模板：\n"
            f"模板名称: {selected_name}.png\n"
            f"坐标: {roi}\n\n"
            f"如果存在同名文件，将会覆盖！\n\n"
            f"确定要生成吗？",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.Yes
        )
        
        if reply != QMessageBox.Yes:
            logger.info(f"❌ 用户取消保存枪械图标模板: {roi_type}")
            return
        
        # 5. 执行保存
        self._save_hud_gun_template_from_roi(roi_type, roi, selected_name)
        
        self.status_label.setText(f"✅ 枪械图标模板已保存: {selected_name}.png | 可继续调整其他类型")
        logger.info(f"✅ 用户手动保存枪械图标模板: {roi_type} -> {selected_name}.png")
    
    def _save_hud_gun_template_from_roi(self, roi_type, relative_roi, template_name):
        """
        从 HUD ROI 截图中保存枪械图标模板
        :param roi_type: ROI 类型 ('Gun_1' 或 'Gun_2')
        :param relative_roi: 相对 HUD 区域的坐标 (left, top, right, bottom)
        :param template_name: 模板名称（不含扩展名）
        """
        try:
            import logging
            logger = logging.getLogger(__name__)
            from core.paths import res_path
            
            # 1. 从 HUD 截图中裁剪 ROI
            if not hasattr(self, '_hud_pixmap') or self._hud_pixmap is None:
                logger.warning(f"⚠️ 无法保存枪械图标模板 {roi_type}: HUD 截图不存在")
                return
            
            rel_left, rel_top, rel_right, rel_bottom = relative_roi
            width = rel_right - rel_left
            height = rel_bottom - rel_top
            
            if width <= 0 or height <= 0:
                logger.warning(f"⚠️ 无法保存枪械图标模板 {roi_type}: ROI 尺寸无效")
                return
            
            # 从 HUD 截图中裁剪
            roi_pixmap = self._hud_pixmap.copy(
                int(rel_left), int(rel_top), int(width), int(height)
            )
            
            # 2. 转换为 OpenCV 格式
            qimage = roi_pixmap.toImage()
            ptr = qimage.bits()
            ptr.setsize(qimage.byteCount())
            arr = np.array(ptr).reshape(qimage.height(), qimage.width(), 4)
            roi_cv = cv2.cvtColor(arr, cv2.COLOR_BGRA2BGR)
            
            # 3. 确定保存路径（按分辨率存储）
            template_dir = res_path('_internal', 'data', 'firearms', self.resolution, 'gun')
            
            # 确保目录存在
            os.makedirs(template_dir, exist_ok=True)
            
            # 4. 保存模板图片（灰度图）
            roi_gray = cv2.cvtColor(roi_cv, cv2.COLOR_BGR2GRAY)
            
            # 5. 确定模板文件名
            tpl_name = template_name.strip()
            if not tpl_name.endswith('.png'):
                tpl_name = f"{tpl_name}.png"
            
            template_path = os.path.join(template_dir, tpl_name)
            
            # 如果文件已存在，备份旧文件
            if os.path.exists(template_path):
                backup_path = template_path + '.tmp'
                try:
                    import shutil
                    shutil.copy2(template_path, backup_path)
                    logger.info(f"📦 已备份旧模板: {backup_path}")
                except Exception as e:
                    logger.warning(f"备份旧模板失败: {e}")
            
            cv2.imwrite(template_path, roi_gray)
            
            logger.info(f"✅ 枪械图标模板已保存: {template_path} ({width}x{height})")
            
            # 6. 清除模板缓存（让识别模块重新加载）
            from core import recognition
            if template_path in recognition._template_cache:
                del recognition._template_cache[template_path]
                logger.debug(f"🔄 已清除枪械图标模板缓存: {template_path}")
            
        except Exception as e:
            import logging
            logger = logging.getLogger(__name__)
            logger.error(f"保存枪械图标模板失败 {roi_type}: {e}")
    
    def _on_save_template(self):
        """手动保存当前ROI的模板图片（用户自己选择模板名称）"""
        import logging
        logger = logging.getLogger(__name__)
        from core.paths import res_path
        
        roi_type = self.roi_type_combo.currentData()
        
        # ✅ HUD 枪械图标模板保存
        if roi_type in self.RELATIVE_TO_HUD:
            self._on_save_hud_gun_template(roi_type)
            return
        
        # 非枪械类型不支持模板
        if roi_type not in self.RELATIVE_TO_BACKPACK:
            if roi_type == 'posture_roi':
                # ✅ 姿势识别有固定模板名：None(站立), c(蹲下), z(趴下)
                # 不用扫描已有模板，直接提供三个固定选项
                pass  # 继续执行下面的姿势模板保存逻辑
            else:
                QMessageBox.information(
                    self, "提示",
                    "只有枪械配件类型（名称/倍镜/枪口/握把/枪托）和枪械图标才支持保存模板"
                )
                return
        
        # ✅ posture_roi 可以在阶段1（全屏模式）保存模板
        if self._phase != "roi" and roi_type != 'posture_roi':
            QMessageBox.information(
                self, "提示",
                "请先进入阶段2（框选背包区域）后再保存模板"
            )
            return
        
        # 获取当前 ROI 坐标
        roi = None
        if hasattr(self, '_roi_label') and self._roi_label:
            roi = self._roi_label._current_roi or self._roi_label.get_roi()
        
        if not roi:
            QMessageBox.warning(self, "提示", "请先在背包截图中框选一个区域")
            return
        
        # 确定模板类别
        category = None
        if 'Name' in roi_type:
            category = 'Name'
        elif 'Scope' in roi_type:
            category = 'Scope'
        elif 'Muzzle' in roi_type:
            category = 'Muzzle'
        elif 'Grip' in roi_type:
            category = 'Grip'
        elif 'Stock' in roi_type:
            category = 'Stock'
        elif roi_type == 'posture_roi':
            category = 'zishi'
        
        if not category:
            return
        
        if roi_type == 'posture_roi':
            # ✅ 姿势模板只有三个固定名称，简化流程
            existing_names = ['None (站立)', 'c (蹲下)', 'z (趴下)']
            # 跳过自动扫描和自动识别，直接显示选择框
            selected_name = None
            retry = True
            while retry:
                retry = False
                selected, ok = QInputDialog.getItem(
                    self,
                    f"选择姿势模板 - {self.ROI_TYPES.get(roi_type)}",
                    f"当前ROI坐标: {roi}\n"
                    f"请选择对应的姿势:",
                    existing_names,
                    0,
                    False  # 不可编辑，固定三个选项
                )
                if not ok or not selected.strip():
                    logger.info(f"❌ 用户取消保存姿势模板")
                    return
                
                # 提取实际文件名（去掉中文说明）
                name_map = {'None (站立)': 'None', 'c (蹲下)': 'c', 'z (趴下)': 'z'}
                selected_name = name_map.get(selected, selected)
                
                # 用户确认是否生成
                reply = QMessageBox.question(
                    self,
                    "确认保存姿势模板",
                    f"即将从当前位置截图生成姿势模板图片：\n"
                    f"模板名称: {selected_name}.png\n"
                    f"坐标: {roi}\n\n"
                    f"确定要生成吗？",
                    QMessageBox.Yes | QMessageBox.No,
                    QMessageBox.Yes
                )
                if reply == QMessageBox.Yes:
                    # 执行保存
                    self._save_template_from_roi(roi_type, roi, template_name=selected_name)
                    self.status_label.setText(f"✅ 姿势模板已保存: {selected_name}.png")
                    logger.info(f"✅ 用户保存姿势模板: {roi_type} -> {selected_name}.png")
                    return
                elif reply == QMessageBox.No:
                    retry = True  # 返回重新选择
            return
        
        # 扫描已有模板名称（三级目录优先）
        existing_names = []
        search_dirs = [
            res_path('_internal', 'data', 'firearms', self.resolution, category),
            res_path('_internal', 'data', 'firearms', 'default', category),
            res_path('_internal', 'data', 'firearms', category),
        ]
        for d in search_dirs:
            if os.path.exists(d):
                for f in os.listdir(d):
                    if f.lower().endswith('.png'):
                        name = f[:-4]  # 去掉 .png
                        if name not in existing_names:
                            existing_names.append(name)
        
        # 优先显示已有模板名，none 放在最后
        if 'none' in existing_names:
            existing_names.remove('none')
            existing_names.sort()
            existing_names.append('none')
        else:
            existing_names.sort()
        
        # 尝试自动识别最佳匹配作为默认建议
        # 先截取 ROI 图用于自动识别
        try:
            roi_norm = self._norm_roi(roi)
            rel_left, rel_top, rel_right, rel_bottom = roi_norm
            width = rel_right - rel_left
            height = rel_bottom - rel_top
            
            if hasattr(self, '_backpack_pixmap') and self._backpack_pixmap and width > 0 and height > 0:
                roi_pixmap = self._backpack_pixmap.copy(
                    int(rel_left), int(rel_top), int(width), int(height)
                )
                qimage = roi_pixmap.toImage()
                ptr = qimage.bits()
                ptr.setsize(qimage.byteCount())
                arr = np.array(ptr).reshape(qimage.height(), qimage.width(), 4)
                roi_cv = cv2.cvtColor(arr, cv2.COLOR_BGRA2BGR)
                roi_gray = cv2.cvtColor(roi_cv, cv2.COLOR_BGR2GRAY)
                auto_name, auto_conf = self._find_best_template_name(roi_gray, category)
            else:
                auto_name = None
                auto_conf = 0.0
        except Exception:
            auto_name = None
            auto_conf = 0.0
        
        # 构建选择列表：自动推荐的放最前面
        all_names = list(existing_names)
        if auto_name and auto_conf >= 0.3:
            # 把自动识别到的移到最前面，前面加 ⭐ 标识
            if auto_name in all_names:
                all_names.remove(auto_name)
            default_name = auto_name
            all_names.insert(0, f"⭐{auto_name} (推荐, {auto_conf:.0%})")
        else:
            default_name = None
        
        # 再添加一个「输入自定义名称」的占位选项
        all_names.append("——— 输入自定义名称 ———")
        
        # 下拉对话框让用户选择
        selected, ok = QInputDialog.getItem(
            self,
            f"选择模板名称 - {self.ROI_TYPES.get(roi_type)}",
            f"当前ROI坐标: {roi_norm}\n"
            f"请选择或输入模板名称（可双击编辑自由输入）:",
            all_names,
            0,  # 默认选中第一个
            True  # 可编辑，用户可自由输入
        )
        
        if not ok or not selected.strip():
            logger.info(f"❌ 用户取消选择模板名称: {roi_type}")
            return
        
        # 清理用户选择的名称
        selected_name = selected.strip()
        # 去掉 ⭐ 前缀和 (推荐, xx%) 后缀
        if selected_name.startswith('⭐'):
            # 格式: "⭐xxx (推荐, xx%)"
            end_idx = selected_name.find(' (推荐')
            if end_idx > 1:
                selected_name = selected_name[1:end_idx]
        if selected_name == "——— 输入自定义名称 ———":
            # 用户选了输入自定义名称却没改文字，跳到输入框
            custom_name, ok2 = QInputDialog.getText(
                self,
                f"输入模板名称 - {self.ROI_TYPES.get(roi_type)}",
                f"请输入模板名称（不包含扩展名）:\n"
                f"可以输入英文或数字，例如: xiexiang\n"
                f"建议与游戏内配件名称一致，SIFT 识别时根据文件名匹配",
                QLineEdit.Normal,
                ""
            )
            if not ok2 or not custom_name.strip():
                logger.info(f"❌ 用户取消输入模板名称: {roi_type}")
                return
            selected_name = custom_name.strip()
        
        logger.info(f"✅ 用户选择模板名称: {selected_name} ({roi_type})")
        
        # 用户确认是否生成
        roi_name = self.ROI_TYPES.get(roi_type, roi_type)
        reply = QMessageBox.question(
            self,
            "确认保存模板",
            f"即将从当前「{roi_name}」截图生成模板图片：\n"
            f"模板名称: {selected_name}.png\n"
            f"坐标: {roi_norm}\n\n"
            f"确定要生成吗？",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.Yes
        )
        
        if reply != QMessageBox.Yes:
            logger.info(f"❌ 用户取消保存模板: {roi_type}")
            return
        
        # 执行保存（传入用户指定的名称，跳过自动识别）
        self._save_template_from_roi(roi_type, roi_norm, template_name=selected_name)
        
        
        self.status_label.setText(f"✅ 模板已保存: {selected_name}.png | 可继续调整其他类型")
        logger.info(f"✅ 用户手动保存模板: {roi_type} -> {selected_name}.png")

    def _find_best_template_name(self, roi_gray, category):
        """
        使用模板匹配找到置信度最高的基础模板名称
        :param roi_gray: 裁剪后的 ROI 灰度图
        :param category: 模板类别 (Name/Scope/Muzzle/Grip/Stock)
        :return: (template_name, confidence) 或 (None, 0.0)
        """
        try:
            from core.paths import res_path
            
            # ✅ 三级搜索：分辨率目录 → default 目录 → 根目录
            search_dirs = [
                res_path('_internal', 'data', 'firearms', self.resolution, category),
                res_path('_internal', 'data', 'firearms', 'default', category),
                res_path('_internal', 'data', 'firearms', category),
            ]
            
            best_score = 0.0
            best_name = None
            
            for search_dir in search_dirs:
                if not os.path.exists(search_dir):
                    continue
                
                for template_file in os.listdir(search_dir):
                    if not template_file.lower().endswith(('.png', '.jpg', '.jpeg')):
                        continue
                    
                    template_path = os.path.join(search_dir, template_file)
                    template_img = cv2.imread(template_path, cv2.IMREAD_GRAYSCALE)
                    
                    if template_img is None:
                        continue
                    
                    try:
                        from core.recognition import match_sift
                        max_val = match_sift(roi_gray, template_img)
                        
                        if max_val > best_score:
                            best_score = max_val
                            # 去掉扩展名作为模板名称
                            best_name = os.path.splitext(template_file)[0]
                    except Exception:
                        continue
                
                # ✅ 如果在当前目录找到了高置信度匹配，不再继续降级搜索
                if best_score > 0.7:
                    break
            
            return (best_name, best_score) if best_name else (None, 0.0)
            
        except Exception as e:
            import logging
            logger = logging.getLogger(__name__)
            logger.error(f"查找最佳模板名失败: {e}")
            return (None, 0.0)
    
    def _save_template_from_roi(self, roi_type, relative_roi, template_name=None):
        """
        从当前 ROI 截图中保存模板图片
        :param roi_type: ROI 类型 (如 'Name_1', 'Scope_1')
        :param relative_roi: 相对坐标 (left, top, right, bottom)
        :param template_name: 手动指定的模板名称（不含扩展名），传入则跳过自动识别
        """
        try:
            import logging
            logger = logging.getLogger(__name__)
            from core.paths import res_path
            
            # 1. 确定模板类别 (Name/Scope/Muzzle/Grip/Stock/zishi)
            category = None
            if 'Name' in roi_type:
                category = 'Name'
            elif 'Scope' in roi_type:
                category = 'Scope'
            elif 'Muzzle' in roi_type:
                category = 'Muzzle'
            elif 'Grip' in roi_type:
                category = 'Grip'
            elif 'Stock' in roi_type:
                category = 'Stock'
            elif roi_type == 'posture_roi':
                category = 'zishi'
            
            if not category:
                return  # 不是枪械信息 ROI，不需要保存模板
            
            # 2. 从截图中裁剪 ROI
            is_posture = (category == 'zishi')
            
            if is_posture:
                # ✅ 姿势模板使用全屏截图（坐标是屏幕绝对坐标）
                if not hasattr(self, '_fullscreen_pixmap') or self._fullscreen_pixmap is None:
                    logger.warning(f"⚠️ 无法保存姿势模板 {roi_type}: 全屏截图不存在")
                    return
                src_pixmap = self._fullscreen_pixmap
            else:
                # ✅ 配件模板使用背包截图（坐标是相对背包坐标）
                if not hasattr(self, '_backpack_pixmap') or self._backpack_pixmap is None:
                    logger.warning(f"⚠️ 无法保存模板 {roi_type}: 背包截图不存在")
                    return
                src_pixmap = self._backpack_pixmap
            
            rel_left, rel_top, rel_right, rel_bottom = relative_roi
            width = rel_right - rel_left
            height = rel_bottom - rel_top
            
            if width <= 0 or height <= 0:
                logger.warning(f"⚠️ 无法保存模板 {roi_type}: ROI 尺寸无效")
                return
            
            # 从截图中裁剪
            roi_pixmap = src_pixmap.copy(
                int(rel_left), int(rel_top), int(width), int(height)
            )
            
            # 3. 转换为 OpenCV 格式
            qimage = roi_pixmap.toImage()
            ptr = qimage.bits()
            ptr.setsize(qimage.byteCount())
            arr = np.array(ptr).reshape(qimage.height(), qimage.width(), 4)
            roi_cv = cv2.cvtColor(arr, cv2.COLOR_BGRA2BGR)
            
            # 4. 确定保存路径（✅ 始终按分辨率存储，不存在则自动创建）
            template_dir = res_path('_internal', 'data', 'firearms', self.resolution, category)
            
            # ✅ 确保目录存在（不存在则自动创建）
            os.makedirs(template_dir, exist_ok=True)
            
            # 5. 保存模板图片（灰度图）
            roi_gray = cv2.cvtColor(roi_cv, cv2.COLOR_BGR2GRAY)
            
            # 6. ✅ 确定模板文件名
            if template_name and template_name.strip():
                # ✅ 用户手动指定名称，直接使用
                tpl_name = template_name.strip()
                if not tpl_name.endswith('.png'):
                    tpl_name = f"{tpl_name}.png"
                logger.info(f"🔍 {roi_type} 使用用户指定名称: {tpl_name}")
                template_filename = tpl_name
            else:
                # ✅ 自动识别最佳名称（降级方案）
                best_name, confidence = self._find_best_template_name(roi_gray, category)
                
                MATCH_NAME_THRESHOLD = 0.3  # 最低匹配置信度阈值
                if best_name and confidence >= MATCH_NAME_THRESHOLD:
                    template_filename = f"{best_name}.png"
                    logger.info(f"🔍 {roi_type} 最佳匹配: {best_name} (置信度: {confidence:.2%})")
                else:
                    # 降级：使用 ROI 类型作为文件名
                    template_filename = f"{roi_type.lower()}.png"
                    if best_name:
                        logger.info(f"⚠️ {roi_type} 最佳匹配 {best_name} 置信度 {confidence:.2%} < {MATCH_NAME_THRESHOLD}，使用默认名")
            
            template_path = os.path.join(template_dir, template_filename)
            cv2.imwrite(template_path, roi_gray)
            
            logger.info(f"✅ 模板已保存: {template_path} ({width}x{height})")
            
            # 7. 清除模板缓存（让识别模块重新加载）
            from core import recognition
            if template_path in recognition._template_cache:
                del recognition._template_cache[template_path]
                logger.debug(f"🔄 已清除模板缓存: {template_path}")
            
        except Exception as e:
            import logging
            logger = logging.getLogger(__name__)
            logger.error(f"保存模板失败 {roi_type}: {e}")
    
    def _show_roi_preview(self, roi_type, screen_coords, saved_coords):
        """
        显示 ROI 裁剪预览，让用户确认
        :param roi_type: ROI 类型
        :param screen_coords: 屏幕坐标 (left, top, right, bottom)
        :param saved_coords: 保存的坐标（可能是相对坐标或转换后的坐标）
        """
        try:
            from PIL import ImageGrab
            import cv2
            import numpy as np
            
            import logging
            logger = logging.getLogger(__name__)
            logger.info(f"🔍 预览调试: roi_type={roi_type}, screen_coords={screen_coords}, saved_coords={saved_coords}")
            
            # ✅ 根据 ROI 类型决定如何裁剪
            if roi_type == 'guns_backpack_roi':
                # 背包区域: saved_coords 是 (left, top, right, bottom)
                left, top, right, bottom = saved_coords
                bbox = (left, top, right, bottom)
                preview_title = f"📦 背包区域预览 - {self.resolution}"
                logger.info(f"📦 背包预览 bbox: {bbox}")
                
            elif roi_type == 'right_click_pos':
                # 开镜坐标: 只显示一个小区域
                x, y = saved_coords
                margin = 50  # 周围 50 像素
                bbox = (max(0, x - margin), max(0, y - margin), 
                       x + margin, y + margin)
                preview_title = f"🎯 开镜坐标预览 ({x}, {y})"
                logger.info(f"🎯 开镜预览 bbox: {bbox}")
                
            elif roi_type in self.RELATIVE_TO_BACKPACK:
                # 枪械信息: 需要从背包区域中裁剪
                if not self.backpack_roi or len(self.backpack_roi) != 4:
                    logger.warning(f"⚠️ 无法预览 {roi_type}: 未配置背包区域")
                    return  # 没有背包区域，无法预览
                
                backpack_left, backpack_top, backpack_right, backpack_bottom = self.backpack_roi
                logger.info(f"📦 背包区域: left={backpack_left}, top={backpack_top}, right={backpack_right}, bottom={backpack_bottom}")
                
                # saved_coords 应该是相对坐标 (left, top, right, bottom)
                rel_left, rel_top, rel_right, rel_bottom = saved_coords
                logger.info(f"🔄 相对坐标: ({rel_left}, {rel_top}, {rel_right}, {rel_bottom})")
                
                # 转换为绝对坐标
                abs_left = backpack_left + rel_left
                abs_top = backpack_top + rel_top
                abs_right = backpack_left + rel_right
                abs_bottom = backpack_top + rel_bottom
                
                bbox = (abs_left, abs_top, abs_right, abs_bottom)
                preview_title = f"🔫 {self.ROI_TYPES.get(roi_type)} 预览 - 相对背包"
                logger.info(f"✅ 绝对坐标 bbox: {bbox}")
                
            else:
                # 其他 ROI（如姿势识别）
                left, top, right, bottom = screen_coords
                bbox = (left, top, right, bottom)
                preview_title = f"📍 {self.ROI_TYPES.get(roi_type)} 预览"
                logger.info(f"📍 其他ROI bbox: {bbox}")
            
            # 截取 ROI 区域
            logger.info(f"📸 开始截图: bbox={bbox}")
            screenshot = ImageGrab.grab(bbox=bbox)
            img_np = np.array(screenshot)
            logger.info(f"✅ 截图成功: {img_np.shape}")
            
            # 转换为 OpenCV 格式 (BGR)
            img_bgr = cv2.cvtColor(img_np, cv2.COLOR_RGB2BGR)
            
            # 获取尺寸信息
            h, w = img_bgr.shape[:2]
            size_info = f"尺寸: {w}x{h} 像素"
            
            # 在图像上添加文字说明
            font = cv2.FONT_HERSHEY_SIMPLEX
            cv2.putText(img_bgr, preview_title, (5, 20), font, 0.5, (0, 255, 0), 1, cv2.LINE_AA)
            cv2.putText(img_bgr, size_info, (5, 40), font, 0.4, (200, 200, 200), 1, cv2.LINE_AA)
            
            # 如果是枪械信息，显示相对坐标
            if roi_type in self.RELATIVE_TO_BACKPACK:
                coord_info = f"相对坐标: {saved_coords}"
                cv2.putText(img_bgr, coord_info, (5, 60), font, 0.4, (0, 255, 255), 1, cv2.LINE_AA)
            
            # 调整图像大小（如果太大）
            max_display_size = 400
            if w > max_display_size or h > max_display_size:
                scale = min(max_display_size / w, max_display_size / h)
                new_w = int(w * scale)
                new_h = int(h * scale)
                img_bgr = cv2.resize(img_bgr, (new_w, new_h))
            
            # ✅ 使用 PyQt 对话框显示预览（更可靠）
            self._show_preview_dialog(img_bgr, preview_title, saved_coords, roi_type)
            
            import logging
            logger = logging.getLogger(__name__)
            logger.info(f"✅ 已显示 ROI 预览窗口: {preview_title}")
            
        except Exception as e:
            import logging
            logger = logging.getLogger(__name__)
            logger.error(f"显示 ROI 预览失败: {e}")
            import traceback
            logger.error(traceback.format_exc())
            # 不弹出错误提示，避免干扰用户
    
    def _show_preview_dialog(self, img_bgr, title, saved_coords, roi_type):
        """
        使用 PyQt 对话框显示 ROI 预览
        :param img_bgr: OpenCV 格式的图像 (BGR)
        :param title: 窗口标题
        :param saved_coords: 保存的坐标
        :param roi_type: ROI 类型
        """
        try:
            import cv2
            from PIL import Image
            import io
            
            # 转换 OpenCV (BGR) -> PIL (RGB)
            img_rgb = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2RGB)
            pil_img = Image.fromarray(img_rgb)
            
            # 转换为 QPixmap
            buffer = io.BytesIO()
            pil_img.save(buffer, format='PNG')
            buffer.seek(0)
            
            pixmap = QPixmap()
            pixmap.loadFromData(buffer.read())
            
            # 创建预览对话框
            dialog = QDialog(self)
            dialog.setWindowTitle(title)
            dialog.setModal(False)  # 非模态，允许继续操作
            
            layout = QVBoxLayout(dialog)
            
            # 显示图像
            label = QLabel()
            label.setPixmap(pixmap)
            label.setAlignment(Qt.AlignCenter)
            layout.addWidget(label)
            
            # 添加说明文字
            info_label = QLabel(
                f"✅ 已保存！\n"
                f"坐标: {saved_coords}\n"
                f"如果内容不正确，请重新框选并保存"
            )
            info_label.setAlignment(Qt.AlignCenter)
            info_label.setStyleSheet("color: #00ff00; font-weight: bold; padding: 10px;")
            layout.addWidget(info_label)
            
            # 关闭按钮
            close_btn = QPushButton("关闭预览")
            close_btn.clicked.connect(dialog.close)
            layout.addWidget(close_btn)
            
            dialog.setLayout(layout)
            dialog.show()
            
        except Exception as e:
            import logging
            logger = logging.getLogger(__name__)
            logger.error(f"显示 PyQt 预览失败: {e}")
    
    def _close_dialog(self):
        if not self._ok_to_close():
            return
        # ✅ 使用 close() 而不是 accept()，避免误触发程序退出
        self._allow_close_without_prompt = True
        self.close()

    def closeEvent(self, event):
        if self._allow_close_without_prompt:
            self._allow_close_without_prompt = False
            event.accept()
            return
        if not self._ok_to_close():
            event.ignore()
        else:
            event.accept()
    
    def keyPressEvent(self, event):
        """键盘事件"""
        key = event.key()
        
        if key in (Qt.Key_Return, Qt.Key_Enter):
            self._on_save()
        elif key in (Qt.Key_Escape, Qt.Key_Q):
            if hasattr(self, "_roi_label") and self._roi_label is not None:
                self._roi_label.cancel_ongoing()
            self.status_label.setText(
                "已取消当前画框/拖动手势（未关闭窗口）；保存请点「保存当前 ROI」"
            )
        else:
            super().keyPressEvent(event)
