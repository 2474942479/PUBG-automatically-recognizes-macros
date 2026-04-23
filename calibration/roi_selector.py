"""ROI 框选校准工具 — 辅助配置枪械/配件识别坐标

使用方式:
    python -m calibration.roi_selector
    python -m calibration.roi_selector --resolution 1920x1080

功能:
    1. 全屏截图后展示，用户可以在上面框选 ROI 区域
    2. 实时显示当前框选的像素坐标 (left, top, right, bottom)
    3. 支持为每个 ROI 命名（如 Name_1, Scope_1 等）
    4. 最终输出 Python 字典格式，可直接粘贴到 data/resolution_setting.py

快捷键:
    鼠标左键拖动 — 框选 ROI
    Enter        — 确认当前选框并命名
    Z            — 撤销上一个 ROI
    S            — 保存所有 ROI 到文件并退出
    Esc / Q      — 退出不保存
    滚轮         — 缩放视图
"""
import sys
import os
import json
import time
import argparse
from datetime import datetime

from PyQt5.QtCore import Qt, QRect, QPoint, QRectF
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QLabel, QInputDialog,
    QMessageBox, QScrollArea, QWidget, QVBoxLayout
)
from PyQt5.QtGui import (
    QPixmap, QPainter, QPen, QColor, QFont, QBrush, QImage, QTransform
)

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

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


ROI_TEMPLATES = {
    "guns": [
        "Name_1", "Scope_1", "Muzzle_1", "Grip_1", "Stock_1",
        "Name_2", "Scope_2", "Muzzle_2", "Grip_2", "Stock_2",
    ],
    "guns_area": ["guns_area"],
    "click_pos": ["click_pos"],
}


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
        self._rois = []
        self._current_rect = None
        self._start_pos = None
        self._colors = [
            QColor(255, 186, 8, 180),
            QColor(74, 229, 74, 180),
            QColor(255, 68, 68, 180),
            QColor(74, 158, 255, 180),
            QColor(224, 160, 64, 180),
            QColor(180, 80, 255, 180),
        ]
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

        for i, (name, rect) in enumerate(self._rois):
            color = self._colors[i % len(self._colors)]
            pen = QPen(color, 2)
            painter.setPen(pen)
            scaled_rect = QRect(
                int(rect.x() * self._scale), int(rect.y() * self._scale),
                int(rect.width() * self._scale), int(rect.height() * self._scale)
            )
            painter.drawRect(scaled_rect)

            bg_brush = QBrush(QColor(0, 0, 0, 160))
            label_text = f"{name} ({rect.x()},{rect.y()},{rect.right()},{rect.bottom()})"
            fm = painter.fontMetrics()
            text_rect = fm.boundingRect(label_text)
            bg_rect = QRect(
                scaled_rect.x(), scaled_rect.y() - text_rect.height() - 4,
                text_rect.width() + 8, text_rect.height() + 4
            )
            painter.fillRect(bg_rect, bg_brush)
            painter.setPen(QPen(color))
            painter.drawText(bg_rect.adjusted(4, 2, 0, 0), Qt.AlignLeft, label_text)

        if self._current_rect:
            pen = QPen(QColor(255, 255, 255, 200), 2, Qt.DashLine)
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
            painter.setPen(QPen(QColor(255, 255, 255)))
            painter.drawText(scaled_rect.bottomLeft() + QPoint(4, 16), coord_text)

        pos = self._to_image_coords(self._mouse_pos)
        cursor_text = f"X:{pos.x()} Y:{pos.y()}"
        painter.setPen(QPen(QColor(200, 200, 200, 180)))
        painter.drawText(10, int(20 * self._scale), cursor_text)

        painter.end()
        self.setPixmap(canvas)
        self.setFixedSize(canvas.size())

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._start_pos = self._to_image_coords(event.pos())
            self._current_rect = QRect(self._start_pos, self._start_pos)
            self._update_display()

    def mouseMoveEvent(self, event):
        self._mouse_pos = event.pos()
        if self._start_pos is not None:
            end = self._to_image_coords(event.pos())
            self._current_rect = QRect(self._start_pos, end).normalized()
            self._update_display()
        else:
            pos = self._to_image_coords(event.pos())
            self.window().statusBar().showMessage(
                f"像素坐标: ({pos.x()}, {pos.y()})  |  "
                f"已标注 {len(self._rois)} 个 ROI  |  "
                f"缩放: {self._scale:.0%}"
            )

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton and self._current_rect:
            if self._current_rect.width() > 3 and self._current_rect.height() > 3:
                pass
            else:
                self._current_rect = None
                self._start_pos = None
            self._update_display()

    def confirm_current_roi(self, suggested_name=""):
        """确认当前框选并命名。"""
        if not self._current_rect:
            return False
        name, ok = QInputDialog.getText(
            self, "命名 ROI", "请输入此区域的名称:",
            text=suggested_name
        )
        if ok and name:
            self._rois.append((name, QRect(self._current_rect)))
            self._current_rect = None
            self._start_pos = None
            self._update_display()
            return True
        return False

    def undo_last_roi(self):
        if self._rois:
            self._rois.pop()
            self._update_display()

    def get_rois(self):
        return [(name, (r.x(), r.y(), r.right(), r.bottom())) for name, r in self._rois]

    def clear_current(self):
        self._current_rect = None
        self._start_pos = None
        self._update_display()


class ROISelectorWindow(QMainWindow):
    """ROI 框选主窗口。"""

    def __init__(self, resolution="unknown"):
        super().__init__()
        self._resolution = resolution
        self._template_idx = 0
        self._template_keys = ROI_TEMPLATES.get("guns", [])

        self.setWindowTitle(f"ROI 校准工具 — {resolution}")
        self.setMinimumSize(800, 600)

        print("正在截取屏幕...")
        pixmap = capture_screenshot()
        print(f"截图完成: {pixmap.width()}x{pixmap.height()}")

        scroll_area = QScrollArea(self)
        scroll_area.setWidgetResizable(False)
        scroll_area.setAlignment(Qt.AlignCenter)
        self.setCentralWidget(scroll_area)

        self._roi_label = ROILabel(pixmap, self)
        scroll_area.setWidget(self._roi_label)

        screen = QApplication.primaryScreen().geometry()
        fit_scale = min(
            (screen.width() - 100) / pixmap.width(),
            (screen.height() - 100) / pixmap.height(),
            1.0
        )
        self._roi_label.set_scale(fit_scale)

        self.statusBar().showMessage(
            "拖动框选 ROI → Enter 确认 → S 保存 | Z 撤销 | Esc 退出 | 滚轮缩放"
        )

    def keyPressEvent(self, event):
        key = event.key()

        if key in (Qt.Key_Return, Qt.Key_Enter):
            suggested = ""
            if self._template_idx < len(self._template_keys):
                suggested = self._template_keys[self._template_idx]
            if self._roi_label.confirm_current_roi(suggested):
                self._template_idx += 1
                remaining = len(self._template_keys) - self._template_idx
                if remaining > 0:
                    self.statusBar().showMessage(
                        f"已确认。下一个建议: {self._template_keys[self._template_idx]}  "
                        f"(剩余 {remaining} 个)"
                    )
                else:
                    self.statusBar().showMessage("所有预设 ROI 已完成，按 S 保存")

        elif key == Qt.Key_Z:
            self._roi_label.undo_last_roi()
            self._template_idx = max(0, self._template_idx - 1)
            self.statusBar().showMessage("已撤销上一个 ROI")

        elif key == Qt.Key_S:
            self._save_rois()

        elif key in (Qt.Key_Escape, Qt.Key_Q):
            self.close()

        elif key == Qt.Key_C:
            self._roi_label.clear_current()

        else:
            super().keyPressEvent(event)

    def wheelEvent(self, event):
        delta = event.angleDelta().y()
        current = self._roi_label._scale
        if delta > 0:
            self._roi_label.set_scale(current + 0.1)
        else:
            self._roi_label.set_scale(current - 0.1)
        self.statusBar().showMessage(f"缩放: {self._roi_label._scale:.0%}")

    def _save_rois(self):
        rois = self._roi_label.get_rois()
        if not rois:
            QMessageBox.warning(self, "提示", "没有标注任何 ROI")
            return

        save_dir = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "calibration", "roi_output"
        )
        os.makedirs(save_dir, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"roi_{self._resolution}_{timestamp}.json"
        filepath = os.path.join(save_dir, filename)

        roi_dict = {}
        for name, coords in rois:
            roi_dict[name] = coords

        output = {
            "resolution": self._resolution,
            "timestamp": timestamp,
            "rois": roi_dict,
        }

        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(output, f, indent=4, ensure_ascii=False)

        py_lines = [f"    '{self._resolution}': {{"]
        for name, (x1, y1, x2, y2) in rois:
            py_lines.append(f"        '{name}': ({x1}, {y1}, {x2}, {y2}),")
        py_lines.append("    },")
        py_code = "\n".join(py_lines)

        py_filepath = os.path.join(save_dir, f"roi_{self._resolution}_{timestamp}.py")
        with open(py_filepath, "w", encoding="utf-8") as f:
            f.write(f"# 自动生成 — {self._resolution} ROI 坐标\n")
            f.write(f"# 生成时间: {timestamp}\n")
            f.write(f"# 可直接粘贴到 data/resolution_setting.py 的 RESOLUTION_SETTINGS\n\n")
            f.write(py_code + "\n")

        print(f"\n{'='*50}")
        print(f"ROI 已保存:")
        print(f"  JSON: {filepath}")
        print(f"  Python: {py_filepath}")
        print(f"{'='*50}")
        print(f"\n可粘贴到 RESOLUTION_SETTINGS 的代码:\n")
        print(py_code)
        print()

        QMessageBox.information(
            self, "保存成功",
            f"ROI 坐标已保存到:\n{filepath}\n\n"
            f"Python 格式:\n{py_filepath}\n\n"
            f"共 {len(rois)} 个 ROI"
        )
        self.close()


def main():
    parser = argparse.ArgumentParser(description="ROI 框选校准工具")
    parser.add_argument(
        "--resolution", "-r", default="unknown",
        help="当前屏幕分辨率标记 (如 1920x1080)"
    )
    parser.add_argument(
        "--template", "-t", default="guns",
        choices=list(ROI_TEMPLATES.keys()),
        help="ROI 命名模板"
    )
    args = parser.parse_args()

    app = QApplication(sys.argv)
    app.setStyle("Fusion")

    window = ROISelectorWindow(args.resolution)
    window._template_keys = ROI_TEMPLATES.get(args.template, [])
    window.showMaximized()

    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
