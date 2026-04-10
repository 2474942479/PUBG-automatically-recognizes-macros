#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
弹痕分析工具 GUI (v3 重构)
═══════════════════════════
交互式弹痕标注 + 实时对比分析 + 迭代修正 + 多组比对

用法: python -m calibration.calibrate_gui
"""

import sys, os, json, time, copy, cv2, numpy as np
from pathlib import Path
from datetime import datetime
from PyQt5.QtCore import Qt, pyqtSignal, QPointF, QRectF, QTimer
from PyQt5.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QComboBox, QPushButton, QFileDialog,
    QMessageBox, QTextEdit, QMenu, QSplitter, QScrollArea,
    QDialog, QDialogButtonBox, QListWidget, QListWidgetItem, QGridLayout,
    QGroupBox, QInputDialog,
)
from PyQt5.QtGui import QPixmap, QImage, QFont, QPainter, QColor, QPen, QBrush

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from data.fire_data import KEY_DATA
from calibration.bullet_analysis import (
    BulletDetector, BulletSorter, BulletComparator, BulletVisualizer,
    ParameterCorrector, ProjectData, IterativeCorrector,
    BulletParamGenerator, _find_gun_data_dir, _load_sensitivity_config,
)
from calibration.video_calibrator import VideoCalibrator

MUZZLE_CN = {
    'none': '无', 'eliuquan': '扼流圈', 'yazuiqiangkou': '鸭嘴枪口',
    'jujiqiangbuchang': '狙击补偿', 'jujiqiangxiaoyan': '狙击消焰',
    'buqiangbuchang': '步枪补偿', 'buqiangxiaoyan': '步枪消焰', 'xiaoyin': '消音器',
    'chongfengqiangxiaoyan': '冲锋枪消焰', 'chongfengqiangbuchang': '冲锋枪补偿',
}
GRIP_CN = {'none': '无', 'banjieshi': '半截式', 'muzhi': '拇指', 'zhijiao': '直角', 'chuizhi': '垂直'}
STOCK_CN = {
    'none': '无', 'zhanshuqiangtuo': '战术枪托', 'zhongxinqiangtuo': '重型枪托',
    'tuosaiban': '托腮板', 'zidandai': '子弹袋', 'zhedieshiqiangtuo': '折叠式枪托',
}
POSE_CN = {'none': ('站立', 1.0), 'c': ('蹲下', None), 'z': ('趴下', None)}
SCOPE_CN = {
    'none': ('机瞄', None), 'hongdian': ('红点', None), 'quanxi': ('全息', None),
    '2bei': ('2倍', None), '3bei': ('3倍', None), '4bei': ('4倍', None),
    '6bei': ('6倍', None), '8bei': ('8倍', None), '15bei': ('15倍', None),
}


# ═══════════════════════════════════════════
# 交互式画布
# ═══════════════════════════════════════════

class BulletCanvas(QWidget):
    """可缩放/拖拽的弹孔标注画布

    操作说明:
      左键空白  — 添加弹孔
      左键弹孔  — 选中并拖动
      右键弹孔  — 删除弹孔
      Shift+左键拖 — 框选批量删除
      Delete键  — 删除选中弹孔
      滚轮     — 缩放
      中键拖   — 平移画布
    """
    holes_changed = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._pixmap = None
        self._holes = []
        self._zoom = 1.0
        self._offset = QPointF(0, 0)
        self._pan_start = None
        self._selected = -1
        self._drag_start = None
        self._just_added = False

        # ROI 选区
        self._roi_mode = False
        self._roi = None
        self._roi_draw_start = None

        # 框选删除
        self._box_del_start = None
        self._box_del_rect = None

        # 标注参数 (按标注顺序编号, 不再按Y坐标排序)
        self._start_shot = 1

        self.setMinimumSize(400, 400)
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.ClickFocus)

    def set_image(self, pixmap):
        self._pixmap = pixmap
        self._roi = None
        self._selected = -1
        self._zoom = 1.0
        self._offset = QPointF(0, 0)
        self.update()

    def set_data(self, holes, pixmap=None):
        self._holes = list(holes) if holes else []
        self._selected = -1
        self._box_del_start = None
        self._box_del_rect = None
        if pixmap is not None:
            self._pixmap = pixmap
            self._zoom = min(self.width() / max(1, pixmap.width()),
                             self.height() / max(1, pixmap.height())) if pixmap.width() > 0 else 1.0
            self._offset = QPointF(0, 0)
        self.update()

    def get_holes(self):
        return self._holes

    def _assign_shot_nums(self):
        """按列表顺序 (即标注顺序) 分配发数编号"""
        for i, h in enumerate(self._holes):
            h['shot_num'] = self._start_shot + i

    def set_start_shot(self, n):
        self._start_shot = max(1, n)
        if self._holes:
            self._assign_shot_nums()
            self.holes_changed.emit()
            self.update()

    def set_roi_mode(self, enabled):
        self._roi_mode = enabled
        self._roi_draw_start = None

    def get_roi(self):
        return self._roi

    def clear_roi(self):
        self._roi = None
        self.update()

    def save_annotation_image(self, path):
        if self._pixmap is None:
            return False
        pm = self._pixmap.copy()
        p = QPainter(pm)
        p.setRenderHint(QPainter.Antialiasing)
        for h in self._holes:
            n = h.get('shot_num', 0)
            col = QColor(255, 0, 0) if n <= 5 else QColor(255, 165, 0) if n <= 15 else QColor(0, 200, 0)
            p.setPen(QPen(col, 2))
            p.drawEllipse(QPointF(h['x'], h['y']), 5, 5)
            p.setPen(QPen(Qt.white, 1))
            fnt = p.font()
            fnt.setPointSize(8)
            p.setFont(fnt)
            p.drawText(h['x'] + 8, h['y'] - 6, str(n))
        p.end()
        return pm.save(str(path))

    # ─── 坐标转换 ───

    def _to_widget(self, ix, iy):
        return QPointF(ix * self._zoom + self._offset.x(), iy * self._zoom + self._offset.y())

    def _to_image(self, wx, wy):
        return ((wx - self._offset.x()) / self._zoom, (wy - self._offset.y()) / self._zoom)

    def _find_hole_at(self, wx, wy, radius=8):
        for i, h in enumerate(self._holes):
            wp = self._to_widget(h['x'], h['y'])
            if (wp.x() - wx) ** 2 + (wp.y() - wy) ** 2 < (radius * self._zoom + 4) ** 2:
                return i
        return -1

    # ─── 事件处理 ───

    def paintEvent(self, e):
        p = QPainter(self)
        p.fillRect(self.rect(), QColor(30, 30, 30))
        if self._pixmap is None:
            p.setPen(Qt.white)
            p.drawText(self.rect(), Qt.AlignCenter,
                       "加载弹痕截图后在此标注\n"
                       "左键: 添加弹孔    右键: 删除弹孔\n"
                       "Shift+拖拽: 框选删除    Delete: 删除选中\n"
                       "滚轮: 缩放    中键拖: 平移")
            return

        p.setRenderHint(QPainter.SmoothPixmapTransform)
        tgt = QRectF(self._offset.x(), self._offset.y(),
                     self._pixmap.width() * self._zoom, self._pixmap.height() * self._zoom)
        p.drawPixmap(tgt, self._pixmap, QRectF(self._pixmap.rect()))

        # 绘制弹孔 (小尺寸, 适合紧密标注)
        for i, h in enumerate(self._holes):
            wp = self._to_widget(h['x'], h['y'])
            n = h.get('shot_num', 0)
            col = QColor(255, 0, 0) if n <= 5 else QColor(255, 165, 0) if n <= 15 else QColor(0, 200, 0)
            pen = QPen(col, 2 if i != self._selected else 3)
            p.setPen(pen)
            r = 5 * self._zoom
            p.drawEllipse(wp, r, r)
            p.setBrush(col)
            p.drawEllipse(wp, 1.5 * self._zoom, 1.5 * self._zoom)
            p.setBrush(Qt.NoBrush)

            if i == self._selected:
                p.setPen(QPen(QColor(255, 255, 0), 1, Qt.DashLine))
                p.drawEllipse(wp, r + 3, r + 3)

            p.setPen(QPen(Qt.white, 1))
            fnt = QFont("Arial", max(7, int(8 * self._zoom)))
            p.setFont(fnt)
            p.drawText(int(wp.x() + 8 * self._zoom), int(wp.y() - 6 * self._zoom), str(n))

        # 绘制连线
        if len(self._holes) >= 2:
            s = sorted(self._holes, key=lambda h: h.get('shot_num', 0))
            for i in range(len(s) - 1):
                p.setPen(QPen(QColor(100, 200, 255, 120), 1, Qt.DashLine))
                p.drawLine(self._to_widget(s[i]['x'], s[i]['y']),
                           self._to_widget(s[i + 1]['x'], s[i + 1]['y']))

        # 绘制 ROI
        if self._roi:
            x, y, rw, rh = self._roi
            tl = self._to_widget(x, y)
            br = self._to_widget(x + rw, y + rh)
            p.setPen(QPen(QColor(0, 255, 0), 2, Qt.DashLine))
            p.drawRect(QRectF(tl, br))

        # 绘制框选删除区域
        if self._box_del_rect:
            bx, by, bw, bh = self._box_del_rect
            tl = self._to_widget(bx, by)
            br = self._to_widget(bx + bw, by + bh)
            p.setPen(QPen(QColor(255, 50, 50), 2, Qt.DashLine))
            p.setBrush(QBrush(QColor(255, 0, 0, 40)))
            p.drawRect(QRectF(tl, br))
            p.setBrush(Qt.NoBrush)

        # 模式提示
        if self._roi_mode:
            p.setPen(QColor(0, 255, 0))
            p.drawText(10, 20, "选区模式: 左键拖画框, 右键取消")
        elif self._box_del_start:
            p.setPen(QColor(255, 50, 50))
            p.drawText(10, 20, "框选删除: 松开鼠标删除框内弹孔")

    def wheelEvent(self, e):
        old_zoom = self._zoom
        factor = 1.15 if e.angleDelta().y() > 0 else 1 / 1.15
        self._zoom = max(0.1, min(10, self._zoom * factor))
        mx, my = e.pos().x(), e.pos().y()
        self._offset = QPointF(
            mx - (mx - self._offset.x()) * self._zoom / old_zoom,
            my - (my - self._offset.y()) * self._zoom / old_zoom,
        )
        self.update()

    def mousePressEvent(self, e):
        if e.button() == Qt.MiddleButton:
            self._pan_start = e.pos()
            return

        if self._pixmap is None:
            return

        ix, iy = self._to_image(e.x(), e.y())

        if e.button() == Qt.LeftButton:
            if self._roi_mode:
                self._roi_draw_start = (int(ix), int(iy))
                self._roi = None
                return

            if e.modifiers() & Qt.ShiftModifier:
                self._box_del_start = (int(ix), int(iy))
                self._box_del_rect = None
                return

            idx = self._find_hole_at(e.x(), e.y())
            if idx >= 0:
                self._selected = idx
                self._drag_start = (e.x(), e.y())
                self._just_added = False
            else:
                new_hole = {'x': int(ix), 'y': int(iy), 'area': 100,
                            'circularity': 1.0, 'color_diff': 50,
                            'shot_num': self._start_shot + len(self._holes)}
                self._holes.append(new_hole)
                self._selected = -1
                self._just_added = True
                self.holes_changed.emit()
            self.update()

        elif e.button() == Qt.RightButton:
            if self._roi_mode:
                self._roi = None
                self.update()
                return

            idx = self._find_hole_at(e.x(), e.y())
            if idx >= 0:
                self._holes.pop(idx)
                self._selected = -1
                self._assign_shot_nums()
                self.holes_changed.emit()
                self.update()
            else:
                menu = QMenu(self)
                clear_act = menu.addAction("清除所有弹孔")
                act = menu.exec_(e.globalPos())
                if act == clear_act:
                    self._holes.clear()
                    self._selected = -1
                    self.holes_changed.emit()
                    self.update()

    def mouseMoveEvent(self, e):
        if self._pan_start:
            delta = e.pos() - self._pan_start
            self._offset += QPointF(delta)
            self._pan_start = e.pos()
            self.update()
            return

        if self._roi_mode and self._roi_draw_start:
            ix, iy = self._to_image(e.x(), e.y())
            sx, sy = self._roi_draw_start
            self._roi = (min(sx, int(ix)), min(sy, int(iy)),
                         abs(int(ix) - sx), abs(int(iy) - sy))
            self.update()
            return

        if self._box_del_start:
            ix, iy = self._to_image(e.x(), e.y())
            sx, sy = self._box_del_start
            self._box_del_rect = (min(sx, int(ix)), min(sy, int(iy)),
                                  abs(int(ix) - sx), abs(int(iy) - sy))
            self.update()
            return

        if self._drag_start and self._selected >= 0:
            ix, iy = self._to_image(e.x(), e.y())
            self._holes[self._selected]['x'] = int(ix)
            self._holes[self._selected]['y'] = int(iy)
            self.update()

    def mouseReleaseEvent(self, e):
        if e.button() == Qt.MiddleButton:
            self._pan_start = None
        elif e.button() == Qt.LeftButton:
            if self._roi_mode and self._roi_draw_start:
                self._roi_draw_start = None
                self._roi_mode = False
                self.update()
            elif self._box_del_start:
                if self._box_del_rect:
                    bx, by, bw, bh = self._box_del_rect
                    before = len(self._holes)
                    self._holes = [h for h in self._holes
                                   if not (bx <= h['x'] <= bx + bw and by <= h['y'] <= by + bh)]
                    if len(self._holes) < before:
                        self._assign_shot_nums()
                        self.holes_changed.emit()
                self._box_del_start = None
                self._box_del_rect = None
                self.update()
            elif self._drag_start and self._selected >= 0:
                self._drag_start = None
                self.holes_changed.emit()
                self.update()

    def keyPressEvent(self, e):
        if e.key() in (Qt.Key_Delete, Qt.Key_Backspace) and self._selected >= 0:
            self._holes.pop(self._selected)
            self._selected = -1
            self._assign_shot_nums()
            self.holes_changed.emit()
            self.update()


# ═══════════════════════════════════════════
# 可视化曲线编辑器
# ═══════════════════════════════════════════

class RecoilCurveEditor(QWidget):
    """可拖拽的后坐力补偿曲线编辑器

    以 chunk 为单位展示 GunData 数组, 每个 chunk 的 sum 对应一发子弹的补偿量。
    用户可拖动节点调整每发的补偿值, 实时更新底层数组。
    支持自动识别异常值（反向、突变）。
    """
    data_changed = pyqtSignal(list)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._values = []
        self._chunk_f = 10.0
        self._chunk_sums = []
        self._dragging = -1
        self._hover = -1
        self._modified = set()
        self._anomalies = []  # 异常值索引列表 [(idx, type, desc)]
        self._show_anomalies = True  # 是否显示异常标记
        self.setMinimumHeight(250)
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.ClickFocus)

    def set_data(self, values, chunk_f):
        self._values = list(values)
        self._chunk_f = max(1, chunk_f)
        self._compute_chunks()
        self._modified.clear()
        self.update()

    def get_values(self):
        return list(self._values)

    def get_modified_indices(self):
        return sorted(self._modified)

    def _compute_chunks(self):
        self._chunk_sums = []
        n = len(self._values)
        i = 0
        while i < n:
            end = min(int(round(i + self._chunk_f)), n)
            s = sum(self._values[i:end])
            self._chunk_sums.append({'start': i, 'end': end, 'sum': s})
            i = end
        
        # 检测异常值
        self._detect_anomalies()

    def _chart_rect(self):
        m = 40
        return QRectF(m, 20, self.width() - m * 2, self.height() - 50)

    def _value_to_pos(self, idx, val):
        r = self._chart_rect()
        n = max(1, len(self._chunk_sums))
        x = r.left() + (idx + 0.5) / n * r.width()
        if not self._chunk_sums:
            return QPointF(x, r.center().y())
        max_v = max(abs(c['sum']) for c in self._chunk_sums) * 1.3
        max_v = max(max_v, 1)
        y = r.bottom() - (val / max_v) * r.height()
        return QPointF(x, y)

    def _pos_to_value(self, pos):
        r = self._chart_rect()
        n = max(1, len(self._chunk_sums))
        idx = int((pos.x() - r.left()) / r.width() * n)
        idx = max(0, min(n - 1, idx))
        max_v = max(abs(c['sum']) for c in self._chunk_sums) * 1.3
        max_v = max(max_v, 1)
        val = (r.bottom() - pos.y()) / r.height() * max_v
        return idx, val

    def _detect_anomalies(self):
        """检测异常值：反向、突变"""
        self._anomalies = []
        if len(self._chunk_sums) < 3:
            return
        
        sums = [c['sum'] for c in self._chunk_sums]
        
        # 计算统计信息
        mean_val = sum(sums) / len(sums)
        std_val = (sum((x - mean_val) ** 2 for x in sums) / len(sums)) ** 0.5 if len(sums) > 1 else 0
        
        for i in range(len(self._chunk_sums)):
            current_sum = sums[i]
            
            # 1. 检测反向值（与整体趋势相反）
            if i > 0 and i < len(sums) - 1:
                prev_sum = sums[i - 1]
                next_sum = sums[i + 1]
                avg_neighbor = (prev_sum + next_sum) / 2
                
                # 如果当前值与邻居平均值符号相反且绝对值较大
                if current_sum * avg_neighbor < 0 and abs(current_sum) > 2:
                    self._anomalies.append({
                        'index': i,
                        'type': 'reverse',
                        'desc': f'反向: {current_sum:.2f} vs 邻居{avg_neighbor:.2f}',
                        'severity': 'high'
                    })
                    continue
            
            # 2. 检测突变（偏离均值超过2倍标准差）
            if std_val > 0 and abs(current_sum - mean_val) > 2.5 * std_val:
                deviation = abs(current_sum - mean_val) / std_val
                severity = 'high' if deviation > 4 else 'medium'
                self._anomalies.append({
                    'index': i,
                    'type': 'spike',
                    'desc': f'突变: {current_sum:.2f} (偏离{deviation:.1f}σ)',
                    'severity': severity
                })
            
            # 3. 检测零值簇（连续多个零可能表示数据缺失）
            if current_sum == 0 and i > 0 and i < len(sums) - 1:
                if sums[i-1] != 0 or sums[i+1] != 0:
                    # 孤立零值
                    self._anomalies.append({
                        'index': i,
                        'type': 'zero',
                        'desc': f'孤立零值',
                        'severity': 'low'
                    })
    
    def get_anomaly_info(self):
        """获取异常值信息"""
        return list(self._anomalies)
    
    def toggle_anomaly_display(self):
        """切换异常值显示"""
        self._show_anomalies = not self._show_anomalies
        self.update()
    
    def _find_node(self, pos, threshold=12):
        for i, c in enumerate(self._chunk_sums):
            pt = self._value_to_pos(i, c['sum'])
            if (pt.x() - pos.x())**2 + (pt.y() - pos.y())**2 < threshold**2:
                return i
        return -1

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.fillRect(self.rect(), QColor(25, 25, 30))

        r = self._chart_rect()
        if not self._chunk_sums:
            p.setPen(Qt.white)
            p.drawText(r, Qt.AlignCenter, "无数据\n分析参数或迭代修正后显示曲线")
            return

        # 坐标轴
        p.setPen(QPen(QColor(80, 80, 80), 1))
        p.drawLine(int(r.left()), int(r.bottom()), int(r.right()), int(r.bottom()))
        p.drawLine(int(r.left()), int(r.top()), int(r.left()), int(r.bottom()))

        max_v = max(abs(c['sum']) for c in self._chunk_sums) * 1.3
        max_v = max(max_v, 1)
        p.setPen(QPen(QColor(60, 60, 60), 1, Qt.DashLine))
        for frac in [0.25, 0.5, 0.75, 1.0]:
            y = int(r.bottom() - frac * r.height())
            p.drawLine(int(r.left()), y, int(r.right()), y)
            p.setPen(QColor(100, 100, 100))
            p.drawText(2, y + 4, f"{frac * max_v:.1f}")
            p.setPen(QPen(QColor(60, 60, 60), 1, Qt.DashLine))
        
        # 绘制零线
        zero_y = int(r.bottom() - (0 - (-max_v)) / (2 * max_v) * r.height())
        p.setPen(QPen(QColor(100, 100, 100, 150), 1, Qt.DashLine))
        p.drawLine(int(r.left()), zero_y, int(r.right()), zero_y)

        # 连线
        n = len(self._chunk_sums)
        for i in range(n - 1):
            p1 = self._value_to_pos(i, self._chunk_sums[i]['sum'])
            p2 = self._value_to_pos(i + 1, self._chunk_sums[i + 1]['sum'])
            
            # 检查是否是异常区间
            is_anomaly_line = False
            if self._show_anomalies:
                anomaly_indices = {a['index'] for a in self._anomalies}
                if i in anomaly_indices or (i + 1) in anomaly_indices:
                    is_anomaly_line = True
            
            if is_anomaly_line:
                p.setPen(QPen(QColor(255, 80, 80, 180), 2, Qt.DashLine))
            else:
                p.setPen(QPen(QColor(100, 200, 255), 2))
            p.drawLine(p1, p2)

        # 节点
        anomaly_indices = {a['index']: a for a in self._anomalies} if self._show_anomalies else {}
        
        for i, c in enumerate(self._chunk_sums):
            pt = self._value_to_pos(i, c['sum'])
            
            # 确定节点颜色
            if i in self._modified:
                col = QColor(255, 200, 50)  # 黄色：已修改
            elif i in anomaly_indices:
                anomaly = anomaly_indices[i]
                if anomaly['severity'] == 'high':
                    col = QColor(255, 50, 50)  # 红色：严重异常
                elif anomaly['severity'] == 'medium':
                    col = QColor(255, 150, 50)  # 橙色：中等异常
                else:
                    col = QColor(255, 255, 100)  # 浅黄：轻微异常
            elif i == self._hover:
                col = QColor(200, 255, 200)  # 绿色：悬停
            else:
                col = QColor(100, 200, 255)  # 蓝色：正常
            
            radius = 7 if i == self._dragging else 6 if i == self._hover or i in anomaly_indices else 4
            p.setPen(QPen(col, 2))
            p.setBrush(QBrush(col))
            p.drawEllipse(pt, radius, radius)

            # 发数标签
            if n <= 30 or i % max(1, n // 20) == 0:
                p.setPen(QColor(160, 160, 160))
                p.setFont(QFont("Arial", 7))
                p.drawText(int(pt.x()) - 8, int(r.bottom()) + 14, str(i + 1))
            
            # 异常标记图标
            if i in anomaly_indices and self._show_anomalies:
                anomaly = anomaly_indices[i]
                p.setPen(QPen(Qt.white, 1))
                p.setFont(QFont("Arial", 8))
                if anomaly['type'] == 'reverse':
                    symbol = '↕'
                elif anomaly['type'] == 'spike':
                    symbol = '▲'
                else:
                    symbol = '○'
                p.drawText(int(pt.x()) - 4, int(pt.y()) - radius - 5, symbol)

        # Hover tooltip
        if 0 <= self._hover < n:
            c = self._chunk_sums[self._hover]
            pt = self._value_to_pos(self._hover, c['sum'])
            tip = f"第{self._hover+1}发: sum={int(c['sum'])} [{c['start']}:{c['end']}]"
            
            # 如果有异常，添加异常信息
            if self._hover in anomaly_indices:
                anomaly = anomaly_indices[self._hover]
                tip += f"\n⚠ {anomaly['desc']}"
            
            p.setPen(QColor(255, 255, 200))
            p.setFont(QFont("Arial", 9))
            p.drawText(int(pt.x()) - 40, int(pt.y()) - 12, tip)

        p.setBrush(Qt.NoBrush)

    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton:
            self._dragging = self._find_node(e.pos())

    def mouseMoveEvent(self, e):
        if self._dragging >= 0 and self._dragging < len(self._chunk_sums):
            _, new_val = self._pos_to_value(e.pos())
            c = self._chunk_sums[self._dragging]
            old_sum = c['sum']
            if abs(old_sum) > 0.01:
                ratio = new_val / old_sum
            else:
                ratio = 1.0
            for j in range(c['start'], c['end']):
                if j < len(self._values):
                    self._values[j] = int(round(self._values[j] * ratio))  # 使用整数
                    self._modified.add(j)
            self._compute_chunks()
            self.update()
        else:
            old_hover = self._hover
            self._hover = self._find_node(e.pos())
            if self._hover != old_hover:
                self.update()

    def mouseReleaseEvent(self, e):
        if e.button() == Qt.LeftButton and self._dragging >= 0:
            self._dragging = -1
            self.data_changed.emit(self._values)
            self.update()


# ═══════════════════════════════════════════
# 检测调试对话框
# ═══════════════════════════════════════════

class DebugDialog(QDialog):
    def __init__(self, debug_info, debug_images, parent=None):
        super().__init__(parent)
        self.setWindowTitle("检测过程 (Debug)")
        self.resize(900, 600)
        layout = QVBoxLayout(self)

        info_text = QTextEdit()
        info_text.setReadOnly(True)
        lines = ["<h3>检测参数</h3><pre>"]
        for k, v in debug_info.items():
            if k in ('blob_params',):
                lines.append(f"  {k}: {json.dumps(v)}")
            else:
                lines.append(f"  {k}: {v}")
        lines.append("</pre>")
        info_text.setHtml("\n".join(lines))
        layout.addWidget(QLabel("参数信息:"))
        layout.addWidget(info_text, 1)

        if debug_images:
            layout.addWidget(QLabel("中间图像:"))
            scroll = QScrollArea()
            container = QWidget()
            grid = QGridLayout(container)
            for i, (name, img) in enumerate(debug_images.items()):
                lbl = QLabel(name)
                lbl.setStyleSheet("color: white; font-weight: bold;")
                pm = _cv2_to_pixmap(img)
                if pm:
                    pm = pm.scaledToWidth(min(350, pm.width()), Qt.SmoothTransformation)
                    img_lbl = QLabel()
                    img_lbl.setPixmap(pm)
                    grid.addWidget(lbl, i // 3, (i % 3) * 2)
                    grid.addWidget(img_lbl, i // 3, (i % 3) * 2 + 1)
            scroll.setWidget(container)
            layout.addWidget(scroll, 2)


# ═══════════════════════════════════════════
# 帮助对话框
# ═══════════════════════════════════════════

class HelpDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("使用帮助")
        self.resize(800, 700)
        layout = QVBoxLayout(self)
        text = QTextEdit()
        text.setReadOnly(True)
        text.setHtml("""
<h2>弹痕分析工具 v3 使用指南</h2>

<h3>一、截图要求</h3>
<ul>
  <li>找一面<b>干净平整</b>的墙壁 (颜色浅、纹理少)</li>
  <li>站在适当距离, 整个弹匣打完后截图</li>
  <li>截图分辨率应与游戏分辨率一致 (工具自动适配任意分辨率)</li>
</ul>

<h3>二、首次分析 (Round 1: 不开宏)</h3>
<ol>
  <li>不开启宏, 正常射击一整个弹匣</li>
  <li>截图保存为 PNG</li>
  <li>打开本工具 → 选择枪械/配件/倍镜/姿势</li>
  <li>点击"加载弹痕图"</li>
  <li><b>推荐</b>: 点击"框选区域"用鼠标框出弹痕所在区域, 过滤无关干扰</li>
  <li>点击"分析" → 自动检测弹孔</li>
  <li>如果检测不准: 右键手动添加/删除弹孔, 左键拖动调整位置</li>
  <li>确认标注后, 右侧面板显示对比结果和修正参数</li>
  <li>点击"保存项目"保存 .calibration.json</li>
  <li>复制修正参数 → 粘贴到对应 GunData JSON</li>
</ol>

<h3>三、迭代修正 (Round 2+: 开宏后微调)</h3>
<ol>
  <li>使用 Round 1 的修正参数开启宏</li>
  <li>用同样的枪/配件/倍镜/姿势射击一整个弹匣, 截图</li>
  <li>点击"迭代修正" → 选择上一轮保存的 .calibration.json</li>
  <li>再选择本轮截图 → 自动检测 + 计算残差 → 输出微调后参数</li>
</ol>

<h3>四、多组比对</h3>
<ol>
  <li>可用"添加到比对组"按钮收集多组数据 (同一枪械/配件)</li>
  <li>或用"批量加载"加载多个 .calibration.json</li>
  <li>点击"交叉比对" → 统计分析, 给出最优参数</li>
</ol>

<h3>五、检测技巧</h3>
<ul>
  <li><b>灵敏度</b>: 高 = 检出多但可能误检, 低 = 精准但可能漏检</li>
  <li><b>模板</b>: 从截图中裁剪一个弹孔 (15~50px方形), 用作模板能显著提高准确率</li>
  <li><b>ROI选区</b>: 框选弹痕区域后分析, 大幅减少误检</li>
  <li><b>调试</b>: 检测不理想时点击"查看检测过程", 查看中间步骤</li>
</ul>

<h3>六、概念解释</h3>
<ul>
  <li><b>比值 (ratio)</b>: 实际弹孔间距 / 理论补偿间距; >1 表示补偿不足, &lt;1 表示补偿过多</li>
  <li><b>chunk_size</b>: 原始数组中每发子弹占的元素数; 自动从弹孔数反推</li>
  <li><b>scope_val</b>: 倍镜灵敏度系数, 来自 Config/config.json</li>
  <li><b>pose_val</b>: 姿势倍率 (来自 GunData 文件中的 none/c/z 值)</li>
</ul>
""")
        layout.addWidget(text)


# ═══════════════════════════════════════════
# 工具函数
# ═══════════════════════════════════════════

def _cv2_to_pixmap(img):
    if img is None:
        return None
    if img.ndim == 2:
        h, w = img.shape
        return QPixmap.fromImage(QImage(img.data, w, h, w, QImage.Format_Grayscale8))
    h, w, c = img.shape
    rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
    return QPixmap.fromImage(QImage(rgb.data, w, h, w * c, QImage.Format_RGB888))


def _build_generation_html(gen_result, acc_code='A0B0C0'):
    """Round 1: 直接从弹痕生成压枪参数的结果展示"""
    if not gen_result:
        return "<p style='color:gray;'>无分析结果</p>"

    g = gen_result
    html = f"""
    <div style="margin:8px;">
      <h3 style="color:#44cc44; font-size:18px;">Round 1: 压枪参数生成</h3>
      <p>枪械: <b>{g['gun_name']}</b> | 配件码: {acc_code}</p>
      <p>弹孔: {g['n_shots']}个 → {g['n_intervals']}组间隔</p>
      <p>射速: {g.get('rpm', '?')}RPM ({g.get('fire_interval_ms', '?')}ms/发) |
         chunk_f: {g['chunk_f']} ({g['chunk_int']} ticks/发)</p>
      <p>平均弹痕间距: <b>{g['avg_pixel_dy']}px</b> | 总位移: {g['total_pixel_dy']}px</p>
    """

    # 逐发明细
    details = g.get('details', [])
    if details:
        html += """
        <h4 style="margin-top:8px;">逐发数据:</h4>
        <table style="border-collapse:collapse; font-size:13px;" width="100%">
          <tr style="background:#444; color:white;">
            <th style="padding:4px;">区间</th>
            <th>像素距离</th>
            <th>X漂移</th>
            <th>每tick值</th>
            <th>ticks</th>
            <th>数组范围</th>
          </tr>
        """
        for d in details:
            html += f"""
            <tr>
              <td style="padding:3px; text-align:center;">{d['shot_from']}→{d['shot_to']}</td>
              <td style="text-align:center;">{d['pixel_dy']:.2f}</td>
              <td style="text-align:center;">{d['pixel_dx']:.2f}</td>
              <td style="text-align:center; color:#8f8;"><b>{d['value_per_tick']}</b></td>
              <td style="text-align:center;">{d['n_ticks']}</td>
              <td style="text-align:center; color:#888;">{d['array_range']}</td>
            </tr>"""
        html += "</table>"

    # 计算公式
    html += f"""
    <h4 style="margin-top:12px;">计算公式:</h4>
    <div style="background:#222; padding:8px; font-size:12px; color:#bbb; line-height:1.8;">
      <p>① pixel_dy = |上一发.y − 下一发.y| (弹痕像素间距)</p>
      <p>② value_per_tick = pixel_dy ÷ chunk_f ÷ (scope × posture)</p>
      <p>   = pixel_dy ÷ {g['chunk_f']} ÷ ({g['scope_val']} × {g['posture_val']})</p>
      <p>③ 宏执行: 每 9ms 执行 mouse_R(0, round(posture × (value × scope)))</p>
      <p>④ 一发子弹内: {g['chunk_int']} ticks × value ≈ pixel_dy → 刚好补偿后坐力</p>
      <hr style="border-color:#444;">
      <p style="color:#aaa;">首次生成可能不完全精确 (像素≠鼠标单位), 用"迭代修正"微调</p>
    </div>
    """

    # 生成的数组
    arr = g.get('generated_array', [])
    if arr:
        arr_json = BulletParamGenerator.format_array_for_json(arr)
        html += f"""
        <h4 style="margin-top:12px;">生成的压枪数据:</h4>
        <p style="color:#aaa;">复制下方数据, 替换 GunData/{g['gun_name']}.json 中的 "{acc_code}" 数组</p>
        <pre style="background:#222; padding:8px; overflow-x:auto; font-size:11px; color:#8f8;">"{acc_code}": {arr_json}</pre>
        """

    html += "</div>"
    return html


def _build_result_html(comparison, correction):
    """生成直观的 HTML 结果展示"""
    if not comparison:
        return "<p style='color:gray;'>暂无分析结果</p>"

    avg = comparison.get('avg_ratio', 1.0)
    diff_pct = round(abs(avg - 1.0) * 100, 1)

    if avg > 1.05:
        verdict_color = '#ff4444'
        verdict = f'补偿偏弱 {diff_pct}%'
        advice = '实际后坐力大于宏的补偿量, 需要<b>增大</b>压枪参数'
    elif avg < 0.95:
        verdict_color = '#ff8800'
        verdict = f'补偿偏强 {diff_pct}%'
        advice = '宏的补偿量大于实际后坐力, 需要<b>减小</b>压枪参数'
    else:
        verdict_color = '#44cc44'
        verdict = f'补偿基本准确 (±{diff_pct}%)'
        advice = '参数已接近最优, 可微调或保持不变'

    chunk_info = f"chunk: {comparison.get('chunk_size_f', comparison.get('chunk_size', '?'))}"
    meta_parts = []
    mag = comparison.get('magazine_size', 0)
    if mag > 0:
        meta_parts.append(f"弹夹: {mag}发")
    rpm = comparison.get('rpm')
    fi_ms = comparison.get('fire_interval_ms')
    if rpm:
        meta_parts.append(f"射速: {rpm}RPM ({fi_ms}ms/发)")
    meta_info = (" | " + " | ".join(meta_parts)) if meta_parts else ""

    html = f"""
    <div style="margin:8px;">
      <h3 style="color:{verdict_color}; font-size:18px;">{verdict}</h3>
      <p>{advice}</p>
      <p>平均比值: <b>{avg:.4f}</b> | 偏差: {comparison.get('std_ratio', 0):.4f}</p>
      <p>弹孔数: {comparison.get('shot_count', 0)} | 有效对比: {comparison.get('valid_pairs', 0)} | {chunk_info}{meta_info}</p>
    """

    # 水平漂移
    avg_dx = comparison.get('avg_horizontal_drift', 0)
    max_dx = comparison.get('max_horizontal_drift', 0)
    std_dx = comparison.get('std_horizontal_drift', 0)
    html += f"""
      <p style="color:#aaa;">水平漂移: 均值{avg_dx:.2f} 最大{max_dx:.2f} 标准差{std_dx:.2f}
        {'(偏移较大, 可能需要水平补偿)' if abs(avg_dx) > 5 else '(正常)'}</p>
    """

    # 逐发明细表
    details = comparison.get('details', [])
    if details:
        html += """
        <table style="border-collapse:collapse; margin-top:8px; font-size:13px;" width="100%">
          <tr style="background:#444; color:white;">
            <th style="padding:4px;">发</th>
            <th>实际(px)</th>
            <th>理论(px)</th>
            <th>比值</th>
            <th>X漂移</th>
            <th>状态</th>
          </tr>
        """
        for d in details:
            ratio = d.get('ratio')
            if ratio and ratio > 1.1:
                row_color = '#ff444433'
                r_text = f'<span style="color:#ff4444">{ratio:.3f}</span>'
            elif ratio and ratio < 0.9:
                row_color = '#ff880033'
                r_text = f'<span style="color:#ff8800">{ratio:.3f}</span>'
            elif ratio:
                row_color = '#44cc4433'
                r_text = f'<span style="color:#44cc44">{ratio:.3f}</span>'
            else:
                row_color = '#ffffff11'
                r_text = 'N/A'
            html += f"""
            <tr style="background:{row_color};">
              <td style="padding:3px; text-align:center;">{d['shot']}</td>
              <td style="text-align:center;">{d['actual_dy']:.2f}</td>
              <td style="text-align:center;">{d['theory_dy']:.2f}</td>
              <td style="text-align:center;">{r_text}</td>
              <td style="text-align:center;">{d.get('x_drift', 0):.2f}</td>
              <td style="text-align:center;">{d['status']}</td>
            </tr>"""
        html += "</table>"

    # 计算公式展示
    chunk_f = comparison.get('chunk_size_f', '?')
    fi_ms = comparison.get('fire_interval_ms', '?')
    scope_v = comparison.get('scope_val', 1.0)
    pose_v = comparison.get('posture_val', 1.0)
    d0 = details[0] if details else {}

    html += f"""
    <h3 style="margin-top:12px;">计算过程 (px ↔ GunData 映射)</h3>
    <div style="background:#222; padding:8px; font-size:12px; color:#bbb; line-height:1.8;">
      <p><b>核心公式</b>: mouse_move = round(posture × (GunData值 × scope))</p>
      <p><b>宏运行方式</b>: 每 9ms 读取一个 GunData 数组元素, 移动鼠标</p>
      <hr style="border-color:#444;">
      <p>① <b>chunk_f</b> = 射击间隔 ÷ tick间隔 = {fi_ms}ms ÷ 9ms = <b>{chunk_f}</b> 个元素/发</p>
      <p>② <b>theory_dy</b> = Σ GunData[i×{chunk_f} : (i+1)×{chunk_f}] × scope({scope_v}) × posture({pose_v})</p>
      <p>③ <b>actual_dy</b> = 上一发弹孔.y − 下一发弹孔.y (像素, 正值=弹痕上移=后坐力)</p>
      <p>④ <b>ratio</b> = actual_dy ÷ theory_dy</p>
      <p style="margin-top:4px;">   ratio &gt; 1 → 实际后坐力 &gt; 宏的补偿量 → <span style="color:#ff4444;">补偿偏弱</span></p>
      <p>   ratio &lt; 1 → 实际后坐力 &lt; 宏的补偿量 → <span style="color:#ff8800;">补偿偏强</span></p>
      <p>⑤ <b>corrected[j]</b> = original[j] × avg_ratio({avg:.4f})</p>
    """

    if d0:
        html += f"""
      <hr style="border-color:#444;">
      <p><b>第1发示例</b>: actual_dy={d0.get('actual_dy', '?')}px, """
        html += f"raw_chunk_sum={d0.get('raw_chunk_sum', '?')}, "
        html += f"theory_dy={d0.get('raw_chunk_sum', 0)}×{scope_v}×{pose_v}={d0.get('theory_dy', '?')}px, "
        r0 = d0.get('ratio')
        html += f"ratio={r0:.3f}</p>" if r0 else "ratio=N/A</p>"

    html += f"""
      <hr style="border-color:#444;">
      <p style="color:#aaa;">scope=1.0 时, 修正后的 GunData 值已包含灵敏度因子, 可直接替换原始数据使用</p>
    </div>
    """

    # 修正参数
    if correction:
        patch = ParameterCorrector.generate_patch_json(correction, 'uniform')
        if patch:
            html += f"""
            <h3 style="margin-top:12px;">修正参数 (均匀模式)</h3>
            <p style="color:#aaa;">复制以下内容替换 GunData JSON 中对应条目:</p>
            <pre style="background:#222; padding:8px; overflow-x:auto; font-size:11px; color:#8f8;">{patch}</pre>
            """

    html += "</div>"
    return html


def _build_iteration_html(iter_result):
    """迭代修正结果 HTML (支持指定发数 + 高亮改动元素)"""
    if not iter_result:
        return "<p style='color:gray;'>迭代修正失败</p>"

    residuals = iter_result.get('residuals', [])
    avg_dy = iter_result.get('avg_residual_dy', 0)
    max_dy = iter_result.get('max_residual_dy', 0)
    avg_ratio = iter_result.get('avg_ratio', 1.0)
    original = iter_result.get('original_array', [])
    corrected = iter_result.get('corrected_uniform', [])
    chunk_f = iter_result.get('chunk_size_f', iter_result.get('chunk_size', 10))
    acc_code = iter_result.get('acc_code', 'A0B0C0')
    start_shot = iter_result.get('start_shot', 1)
    modified_indices = set(iter_result.get('modified_indices', []))
    n_traj = iter_result.get('n_trajectories_used', 1)

    if abs(avg_dy) < 3:
        color = '#44cc44'
        verdict = '残差极小, 参数已非常准确!'
    elif abs(avg_dy) < 8:
        color = '#ffcc00'
        verdict = '残差较小, 参数接近最优'
    else:
        color = '#ff4444'
        verdict = '残差较大, 建议继续迭代'

    traj_info = f" | 使用 {n_traj} 条轨迹取平均" if n_traj > 1 else ""
    shot_info = f" | 起始发数: 第{start_shot}发" if start_shot > 1 else ""

    html = f"""
    <div style="margin:8px;">
      <h3 style="color:{color}; font-size:18px;">迭代修正结果 (比例修正)</h3>
      <p>{verdict}</p>
      <p>平均残差: {avg_dy:.2f}px | 最大残差: {max_dy:.2f}px | 平均修正比例: ×{avg_ratio:.4f}{traj_info}{shot_info}</p>
      <p style="color:#aaa; font-size:12px;">
        修正原理: ratio = chunk_sum / (chunk_sum + |dy|), dy保留符号表示方向<br/>
        dy &lt; 0 → 没压住(下沉), 应用 1/ratio 增大补偿 | dy &gt; 0 → 压过了(上飘), 应用 ratio 减小补偿<br/>
        <span style="color:#ffcc00;">特殊处理:</span> chunk原值为0时, 直接将 |dy| 平均分配到每个元素
      </p>

      <h4 style="margin-top:8px;">逐发残差分析:</h4>
      <table style="border-collapse:collapse; font-size:13px;" width="100%">
        <tr style="background:#444; color:white;">
          <th style="padding:4px;">区间</th>
          <th>Y残差(px)</th>
          <th>X残差(px)</th>
          <th>chunk_sum</th>
          <th>修正比例</th>
          <th>数组范围</th>
          <th>判断</th>
        </tr>
    """
    for r in residuals:
        dy = r['dy']
        ratio = r.get('correction_ratio', 1.0)
        if abs(dy) < 3:
            judge = '<span style="color:#44cc44;">准确</span>'
        elif dy < 0:
            judge = '<span style="color:#ff4444;">没压住(上飘)</span>'
        else:
            judge = '<span style="color:#ff8800;">压过了(下沉)</span>'
        ratio_color = '#44cc44' if 0.9 <= ratio <= 1.1 else '#ffcc00' if 0.7 <= ratio <= 1.3 else '#ff4444'
        n_t = r.get('n_trajectories', 1)
        traj_note = f" ({n_t}条)" if n_t > 1 else ""
        html += f"""
        <tr>
          <td style="padding:3px; text-align:center;">{r.get('shot_from', r['shot'])}→{r.get('shot_to', r['shot']+1)}</td>
          <td style="text-align:center;">{int(dy)}{traj_note}</td>
          <td style="text-align:center;">{int(r['dx'])}</td>
          <td style="text-align:center;">{int(r.get('chunk_sum', 0))}</td>
          <td style="text-align:center; color:{ratio_color};"><b>×{ratio:.4f}</b></td>
          <td style="text-align:center; color:#888;">{r.get('array_range', '')}</td>
          <td style="text-align:center;">{judge}</td>
        </tr>"""
    html += "</table>"

    # 逐发对比表: 使用实际的 shot_from 标号
    html += """
      <h4 style="margin-top:12px;">逐发参数对比 (原值 × 比例 → 调整后):</h4>
      <table style="border-collapse:collapse; font-size:13px;" width="100%">
        <tr style="background:#444; color:white;">
          <th style="padding:4px;">区间</th>
          <th>原值(chunk sum)</th>
          <th>调整后(chunk sum)</th>
          <th>比例</th>
        </tr>
    """
    for r in residuals:
        arr_range = r.get('array_range', '')
        if arr_range:
            parts = arr_range.strip('[]').split(':')
            start, end = int(parts[0]), int(parts[1])
        else:
            continue
        orig_sum = int(round(sum(original[start:end]))) if end <= len(original) else 0
        corr_sum = int(round(sum(corrected[start:end]))) if end <= len(corrected) else 0
        ratio = round(corr_sum / orig_sum, 4) if orig_sum != 0 else 1.0
        ratio_color = '#44cc44' if 0.9 <= ratio <= 1.1 else '#ffcc00' if 0.7 <= ratio <= 1.3 else '#ff4444'
        html += f"""
        <tr>
          <td style="padding:3px; text-align:center;">{r.get('shot_from', '')}→{r.get('shot_to', '')}</td>
          <td style="text-align:center;">{orig_sum}</td>
          <td style="text-align:center; color:#8f8;"><b>{corr_sum}</b></td>
          <td style="text-align:center; color:{ratio_color};">×{ratio:.4f}</td>
        </tr>"""
    html += "</table>"

    # 输出完整数组, 高亮修改的元素
    if corrected:
        html += f"""
        <h4 style="margin-top:12px;">调整后的完整压枪数据 (直接替换):</h4>
        <p style="color:#aaa;">复制下方数据替换 GunData/{iter_result.get('gun_name', '')}.json 中的 "{acc_code}"</p>
        """
        if modified_indices:
            html += '<p style="color:#aaa; font-size:11px;"><span style="color:#8f8;">■ 绿色 = 已修改</span> | <span style="color:#888;">■ 灰色 = 未修改</span></p>'

        items_per_line = 36
        html += f'<pre style="background:#222; padding:8px; overflow-x:auto; font-size:11px; line-height:1.6;">"{acc_code}": [\n'
        for row_start in range(0, len(corrected), items_per_line):
            row_end = min(row_start + items_per_line, len(corrected))
            parts = []
            for idx in range(row_start, row_end):
                v = corrected[idx]
                if idx in modified_indices:
                    parts.append(f'<span style="color:#8f8; font-weight:bold;">{v}</span>')
                else:
                    parts.append(f'<span style="color:#666;">{v}</span>')
            line = "        " + ", ".join(parts)
            if row_end < len(corrected):
                line += ","
            html += line + "\n"
        html += '    ]</pre>'

    html += "</div>"
    return html


# ═══════════════════════════════════════════
# 视频校准对话框 (v2 — 透明化)
# ═══════════════════════════════════════════

class VideoCalibrationDialog(QDialog):
    """视频校准对话框 — 录屏 → 弹孔检测 → 预览标注图 → 加载到主画布手动调整。

    不再自动计算 per-shot / 修正值。
    分析结果加载到主窗口 BulletCanvas 后，由用户手动确认 → 分析参数/迭代修正。
    """

    def __init__(self, gun_name, acc_code, scope_val, posture_val,
                 gun_data_dir, parent=None):
        super().__init__(parent)
        self.setWindowTitle("视频校准 (v2)")
        self.resize(900, 700)
        self._vc = VideoCalibrator(
            gun_name, acc_code, scope_val, posture_val,
            gun_data_dir=gun_data_dir)
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)

        self.result_frame = None
        self.result_holes = None
        self._video_path = None
        self._annotated_path = None

        self._init_ui()

    def _init_ui(self):
        lo = QVBoxLayout(self)

        # ── 配置 ──
        info = QGroupBox("枪械配置")
        ig = QGridLayout(info)
        vc = self._vc
        ig.addWidget(QLabel(f"枪械: {vc.gun_name}"), 0, 0)
        ig.addWidget(QLabel(f"配件: {vc.acc_code}"), 0, 1)
        ig.addWidget(QLabel(f"倍镜: {vc.scope_val}"), 0, 2)
        ig.addWidget(QLabel(f"姿态: {vc.posture_val}"), 1, 0)
        ig.addWidget(QLabel(f"射速: {round(60/vc.fire_interval)} RPM"), 1, 1)
        ig.addWidget(QLabel(f"弹匣: {vc.magazine}"), 1, 2)
        lo.addWidget(info)

        # ── 模式选择 ──
        from PyQt5.QtWidgets import QRadioButton, QButtonGroup
        mode_box = QGroupBox("检测模式")
        mlo = QHBoxLayout(mode_box)
        self._bg = QButtonGroup(self)
        self._rb_init = QRadioButton("初始生成 — 帧差分时序 (无宏, 弹孔分散)")
        self._rb_refine = QRadioButton("迭代修正 — 静态检测 (有宏, 弹孔密集)")
        self._rb_init.setChecked(True)
        self._bg.addButton(self._rb_init)
        self._bg.addButton(self._rb_refine)
        mlo.addWidget(self._rb_init)
        mlo.addWidget(self._rb_refine)
        lo.addWidget(mode_box)

        # ── 录制控制 ──
        ctrl = QHBoxLayout()
        self._btn_start = QPushButton("开始录制 (F6)")
        self._btn_start.setStyleSheet(
            "background:#22aa44;color:white;padding:8px 20px;font-size:14px;")
        self._btn_stop = QPushButton("停止录制 (F7)")
        self._btn_stop.setStyleSheet(
            "background:#cc3333;color:white;padding:8px 20px;font-size:14px;")
        self._btn_stop.setEnabled(False)
        ctrl.addWidget(self._btn_start)
        ctrl.addWidget(self._btn_stop)
        lo.addLayout(ctrl)

        # ── 状态 ──
        self._lbl_status = QLabel("就绪 — 点击「开始录制」或按 F6，对墙射击后按 F7 停止")
        self._lbl_status.setStyleSheet(
            "font-size:13px;padding:6px;background:#222;color:#aaa;")
        self._lbl_status.setAlignment(Qt.AlignCenter)
        self._lbl_status.setWordWrap(True)
        lo.addWidget(self._lbl_status)

        # ── 预览图 + 弹孔列表 (水平分栏) ──
        preview_split = QSplitter(Qt.Horizontal)

        self._preview_label = QLabel("标注预览将在录制分析后显示")
        self._preview_label.setAlignment(Qt.AlignCenter)
        self._preview_label.setStyleSheet(
            "background:#111;color:#666;min-height:300px;")
        self._preview_label.setScaledContents(False)
        preview_split.addWidget(self._preview_label)

        right_panel = QWidget()
        rlo = QVBoxLayout(right_panel)
        rlo.setContentsMargins(0, 0, 0, 0)
        rlo.addWidget(QLabel("检测到的弹孔:"))
        self._hole_list = QTextEdit()
        self._hole_list.setReadOnly(True)
        self._hole_list.setStyleSheet("background:#1a1a1a;color:#ddd;font-size:12px;")
        rlo.addWidget(self._hole_list, 1)

        self._lbl_paths = QLabel("")
        self._lbl_paths.setWordWrap(True)
        self._lbl_paths.setStyleSheet("color:#888;font-size:11px;")
        rlo.addWidget(self._lbl_paths)
        preview_split.addWidget(right_panel)

        preview_split.setStretchFactor(0, 3)
        preview_split.setStretchFactor(1, 2)
        lo.addWidget(preview_split, 1)

        # ── 底部按钮 ──
        bot = QHBoxLayout()
        self._btn_load_canvas = QPushButton("加载到主画布 (手动审核)")
        self._btn_load_canvas.setStyleSheet(
            "font-weight:bold;background:#2266cc;color:white;padding:8px 16px;font-size:13px;")
        self._btn_load_canvas.setEnabled(False)
        self._btn_open_video = QPushButton("打开录屏文件")
        self._btn_open_video.setEnabled(False)
        self._btn_close = QPushButton("关闭")
        bot.addWidget(self._btn_load_canvas)
        bot.addWidget(self._btn_open_video)
        bot.addStretch()
        bot.addWidget(self._btn_close)
        lo.addLayout(bot)

        # ── 信号 ──
        self._btn_start.clicked.connect(self._on_start)
        self._btn_stop.clicked.connect(self._on_stop)
        self._btn_load_canvas.clicked.connect(self._on_load_canvas)
        self._btn_open_video.clicked.connect(self._on_open_video)
        self._btn_close.clicked.connect(self.reject)

        self._vc.enable_hotkeys(on_start=self._hotkey_start, on_stop=self._hotkey_stop)

    def _hotkey_start(self):
        QTimer.singleShot(0, self._on_start)

    def _hotkey_stop(self):
        QTimer.singleShot(0, self._on_stop)

    def _on_start(self):
        if self._vc.recorder.recording:
            return
        self._vc.start_recording()
        self._btn_start.setEnabled(False)
        self._btn_stop.setEnabled(True)
        self._btn_load_canvas.setEnabled(False)
        self._btn_open_video.setEnabled(False)
        self._lbl_status.setText("录制中 … 对墙射击，完毕后按 F7 停止")
        self._lbl_status.setStyleSheet(
            "font-size:13px;padding:6px;background:#442222;color:#ff6666;")
        self._timer.start(200)

    def _tick(self):
        n = self._vc.recorder.frame_count
        elapsed = ""
        if n > 1:
            dur = self._vc.recorder.frames[-1][0] - self._vc.recorder.frames[0][0]
            elapsed = f" ({dur:.1f}s)"
        self._lbl_status.setText(f"录制中 … {n} 帧{elapsed}")

    def _on_stop(self):
        if not self._vc.recorder.recording:
            return
        self._timer.stop()
        count = self._vc.stop_recording()
        self._btn_start.setEnabled(True)
        self._btn_stop.setEnabled(False)

        if count < 10:
            self._lbl_status.setText("帧数不足 (需 >10)，请重新录制")
            self._lbl_status.setStyleSheet(
                "font-size:13px;padding:6px;background:#222;color:#aaa;")
            return

        self._lbl_status.setText(f"录制 {count} 帧 — 保存视频 + 分析中 …")
        self._lbl_status.setStyleSheet(
            "font-size:13px;padding:6px;background:#222;color:#aaa;")
        QApplication.processEvents()

        self._video_path = self._vc.save_recording()

        mode = "initial" if self._rb_init.isChecked() else "refine"
        self.result_frame, self.result_holes = self._vc.detect_holes(mode=mode)

        if not self.result_holes:
            self._lbl_status.setText("未检测到弹孔，请重试 (换用另一模式 / 调整距离 / 重新射击)")
            self._preview_label.setText("未检测到弹孔")
            self._hole_list.setHtml("<p style='color:#ff6666;'>无结果</p>")
            self._btn_open_video.setEnabled(self._video_path is not None)
            self._update_paths()
            return

        self._annotated_path = self._vc.save_annotated_frame(self.result_holes)
        self._show_preview()

    def _show_preview(self):
        """显示标注预览图和弹孔列表。"""
        from calibration.video_calibrator import annotate_frame
        ann = self._vc.get_annotated_frame(self.result_holes)
        if ann is not None:
            pm = _cv2_to_pixmap(ann)
            if pm:
                scaled = pm.scaled(self._preview_label.size(),
                                   Qt.KeepAspectRatio, Qt.SmoothTransformation)
                self._preview_label.setPixmap(scaled)

        n = len(self.result_holes)
        html = f"<p style='color:#44cc44;'>检测到 <b>{n}</b> 个弹孔</p>"
        html += "<table style='border-collapse:collapse;font-size:12px;width:100%;'>"
        html += "<tr style='background:#333;color:white;'><th>#</th><th>X</th><th>Y</th></tr>"
        for h in sorted(self.result_holes, key=lambda x: x.get("shot_num", 0)):
            sn = h.get("shot_num", 0)
            html += (f"<tr><td style='text-align:center;'>{sn}</td>"
                     f"<td style='text-align:center;'>{h['x']}</td>"
                     f"<td style='text-align:center;'>{h['y']}</td></tr>")
        html += "</table>"
        self._hole_list.setHtml(html)

        mode_txt = "帧差分时序" if self._rb_init.isChecked() else "静态检测"
        self._lbl_status.setText(
            f"检测完成 ({mode_txt}): {n} 个弹孔 — 点击「加载到主画布」审核调整")
        self._lbl_status.setStyleSheet(
            "font-size:13px;padding:6px;background:#223322;color:#66cc66;")

        self._btn_load_canvas.setEnabled(True)
        self._btn_open_video.setEnabled(self._video_path is not None)
        self._update_paths()

    def _update_paths(self):
        parts = []
        if self._video_path:
            parts.append(f"录屏: {self._video_path}")
        if self._annotated_path:
            parts.append(f"标注图: {self._annotated_path}")
        self._lbl_paths.setText("\n".join(parts))

    def _on_load_canvas(self):
        """将检测结果传回主窗口 BulletCanvas，关闭对话框。"""
        if self.result_frame is not None and self.result_holes:
            self.accept()

    def _on_open_video(self):
        if self._video_path:
            import subprocess, sys
            if sys.platform == "darwin":
                subprocess.Popen(["open", self._video_path])
            elif sys.platform == "win32":
                os.startfile(self._video_path)
            else:
                subprocess.Popen(["xdg-open", self._video_path])

    def closeEvent(self, e):
        self._vc.disable_hotkeys()
        if self._vc.recorder.recording:
            self._vc.stop_recording()
        super().closeEvent(e)

    def reject(self):
        self._vc.disable_hotkeys()
        if self._vc.recorder.recording:
            self._vc.stop_recording()
        super().reject()


# ═══════════════════════════════════════════
# 主窗口
# ═══════════════════════════════════════════

class MainWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("PUBG 弹痕分析 v3")
        self.resize(1400, 900)

        self._gun_data_dir = _find_gun_data_dir()
        self._sens_cfg = _load_sensitivity_config()
        self._result_img = None
        self._result_path = None
        self._template_img = None
        self._template_path = None

        # 配置缓存
        self._gun_name = ''
        self._acc_code = 'A0B0C0'
        self._scope_key = 'none'
        self._scope_val = 1.0
        self._pose_key = 'none'
        self._pose_val = 1.0

        # 分析结果缓存
        self._last_comparison = None
        self._last_correction = None
        self._last_generation = None
        self._last_detector = None
        self._current_project_path = None

        # 多轨迹管理: [{name, holes, comparison, correction}]
        self._trajectories = [{'name': '轨迹1', 'holes': [], 'comparison': None, 'correction': None}]
        self._current_traj_idx = 0

        self._init_ui()
        self._connect_signals()
        self._read_config()

    # ═══ UI 构建 ═══

    def _init_ui(self):
        main = QHBoxLayout(self)

        # ─── 左侧: 画布 ───
        left = QVBoxLayout()

        # 轨迹管理栏
        traj_bar = QHBoxLayout()
        traj_bar.addWidget(QLabel("轨迹:"))
        self.traj_combo = QComboBox()
        self.traj_combo.setMinimumWidth(120)
        self.traj_combo.addItem("轨迹1")
        traj_bar.addWidget(self.traj_combo, 1)
        self.btn_add_traj = QPushButton("+新建")
        self.btn_add_traj.setMaximumWidth(60)
        self.btn_del_traj = QPushButton("-删除")
        self.btn_del_traj.setMaximumWidth(60)
        traj_bar.addWidget(self.btn_add_traj)
        traj_bar.addWidget(self.btn_del_traj)
        left.addLayout(traj_bar)

        # 画布
        self.canvas = BulletCanvas()
        left.addWidget(self.canvas, 1)

        # 画布按钮栏
        cv_bar = QHBoxLayout()
        self.btn_roi = QPushButton("框选区域")
        self.btn_roi.setCheckable(True)
        self.btn_clear_roi = QPushButton("清除选区")
        self.lbl_holes_count = QLabel("弹孔: 0")
        self.lbl_holes_count.setStyleSheet("color: #aaa;")
        cv_bar.addWidget(self.btn_roi)
        cv_bar.addWidget(self.btn_clear_roi)
        cv_bar.addStretch()
        cv_bar.addWidget(self.lbl_holes_count)
        left.addLayout(cv_bar)

        # ─── 右侧: 配置 + 结果 ───
        right = QVBoxLayout()

        # 枪械配置区
        cfg_group = QGroupBox("枪械配置")
        cfg_layout = QGridLayout(cfg_group)

        cfg_layout.addWidget(QLabel("枪械:"), 0, 0)
        self.c_gun = QComboBox()
        self._populate_guns()
        cfg_layout.addWidget(self.c_gun, 0, 1)

        cfg_layout.addWidget(QLabel("倍镜:"), 0, 2)
        self.c_scope = QComboBox()
        for k, (cn, _) in SCOPE_CN.items():
            self.c_scope.addItem(cn, k)
        cfg_layout.addWidget(self.c_scope, 0, 3)

        cfg_layout.addWidget(QLabel("枪口:"), 1, 0)
        self.c_muzzle = QComboBox()
        for k, cn in MUZZLE_CN.items():
            self.c_muzzle.addItem(cn, k)
        cfg_layout.addWidget(self.c_muzzle, 1, 1)

        cfg_layout.addWidget(QLabel("握把:"), 1, 2)
        self.c_grip = QComboBox()
        for k, cn in GRIP_CN.items():
            self.c_grip.addItem(cn, k)
        cfg_layout.addWidget(self.c_grip, 1, 3)

        cfg_layout.addWidget(QLabel("枪托:"), 2, 0)
        self.c_stock = QComboBox()
        for k, cn in STOCK_CN.items():
            self.c_stock.addItem(cn, k)
        cfg_layout.addWidget(self.c_stock, 2, 1)

        cfg_layout.addWidget(QLabel("姿势:"), 2, 2)
        self.c_pose = QComboBox()
        for k, (cn, _) in POSE_CN.items():
            self.c_pose.addItem(cn, k)
        cfg_layout.addWidget(self.c_pose, 2, 3)

        cfg_layout.addWidget(QLabel("起始发数:"), 3, 0)
        self.c_start_shot = QComboBox()
        for i in range(1, 51):
            self.c_start_shot.addItem(f"第{i}发", i)
        cfg_layout.addWidget(self.c_start_shot, 3, 1)

        self.lbl_direction_hint = QLabel("标注顺序 = 开火顺序")
        self.lbl_direction_hint.setStyleSheet("color: #888; font-size: 11px;")
        cfg_layout.addWidget(self.lbl_direction_hint, 3, 2, 1, 2)

        right.addWidget(cfg_group)

        # 操作按钮区
        btn_layout = QGridLayout()

        self.btn_load = QPushButton("加载弹痕图")
        self.btn_detect = QPushButton("检测弹孔")
        self.btn_detect.setStyleSheet("background:#2266aa; color:white; padding:6px;")
        self.btn_analyze = QPushButton("分析参数")
        self.btn_analyze.setStyleSheet("font-weight:bold; background:#22aa44; color:white; padding:6px;")

        self.btn_analyze_all = QPushButton("分析全部轨迹")
        self.btn_analyze_all.setStyleSheet("font-weight:bold; background:#22aa88; color:white; padding:6px;")

        btn_layout.addWidget(self.btn_load, 0, 0)
        btn_layout.addWidget(self.btn_detect, 0, 1)
        btn_layout.addWidget(self.btn_analyze, 0, 2)
        btn_layout.addWidget(self.btn_analyze_all, 0, 3)

        self.btn_save = QPushButton("保存项目")
        self.btn_load_proj = QPushButton("加载项目")
        self.btn_iterate = QPushButton("迭代修正")
        self.btn_iterate.setStyleSheet("background:#886622; color:white; padding:6px;")
        self.btn_debug = QPushButton("检测过程")

        btn_layout.addWidget(self.btn_save, 1, 0)
        btn_layout.addWidget(self.btn_load_proj, 1, 1)
        btn_layout.addWidget(self.btn_iterate, 1, 2)
        btn_layout.addWidget(self.btn_debug, 1, 3)

        self.btn_video_cal = QPushButton("视频校准 (F6/F7)")
        self.btn_video_cal.setStyleSheet(
            "font-weight:bold; background:#7733aa; color:white; padding:6px;")
        btn_layout.addWidget(self.btn_video_cal, 2, 0, 1, 4)

        right.addLayout(btn_layout)

        # 状态标签
        self.info_lb = QLabel("就绪")
        self.info_lb.setWordWrap(True)
        self.info_lb.setStyleSheet("color: #aaa; font-size: 12px; padding: 4px;")
        right.addWidget(self.info_lb)

        # 结果区
        self.result_text = QTextEdit()
        self.result_text.setReadOnly(True)
        self.result_text.setStyleSheet("background:#1a1a1a; color:#ddd; font-size:13px;")
        right.addWidget(self.result_text, 1)

        # 曲线编辑器
        curve_group = QGroupBox("曲线编辑器 (拖拽节点调整每发补偿量)")
        curve_layout = QVBoxLayout(curve_group)
        self.curve_editor = RecoilCurveEditor()
        self.curve_editor.setMinimumHeight(180)
        curve_layout.addWidget(self.curve_editor)
        curve_bar = QHBoxLayout()
        self.btn_curve_apply = QPushButton("应用曲线修改")
        self.btn_curve_apply.setStyleSheet("background:#886622; color:white;")
        self.btn_curve_reset = QPushButton("重置曲线")
        self.btn_toggle_anomalies = QPushButton("隐藏异常标记")
        self.btn_toggle_anomalies.setCheckable(True)
        self.btn_toggle_anomalies.setStyleSheet("background:#444; color:#aaa;")
        curve_bar.addWidget(self.btn_curve_apply)
        curve_bar.addWidget(self.btn_curve_reset)
        curve_bar.addWidget(self.btn_toggle_anomalies)
        curve_bar.addStretch()
        curve_layout.addLayout(curve_bar)
        
        # 异常值信息面板
        self.anomaly_info = QTextEdit()
        self.anomaly_info.setReadOnly(True)
        self.anomaly_info.setMaximumHeight(120)
        self.anomaly_info.setStyleSheet("background:#1a1a1a; color:#ddd; font-size:12px;")
        self.anomaly_info.setVisible(False)
        curve_layout.addWidget(self.anomaly_info)
        
        right.addWidget(curve_group)

        # 复制+帮助
        bot = QHBoxLayout()
        self.btn_copy = QPushButton("复制修正参数")
        self.btn_help = QPushButton("使用帮助")
        bot.addWidget(self.btn_copy)
        bot.addWidget(self.btn_help)
        right.addLayout(bot)

        # 组装
        splitter = QSplitter(Qt.Horizontal)
        lw = QWidget()
        lw.setLayout(left)
        rw = QWidget()
        rw.setLayout(right)
        splitter.addWidget(lw)
        splitter.addWidget(rw)
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 2)
        main.addWidget(splitter)

    def _populate_guns(self):
        gd = Path(self._gun_data_dir)
        guns = []
        if gd.is_dir():
            for f in sorted(gd.glob("*.json")):
                guns.append(f.stem)
        if not guns:
            guns = ["m762", "akm", "m416", "groza", "ump45"]
        for g in guns:
            self.c_gun.addItem(g, g)

    # ═══ 信号连接 ═══

    def _connect_signals(self):
        self.btn_load.clicked.connect(self._pick_result)
        self.btn_detect.clicked.connect(self._detect)
        self.btn_analyze.clicked.connect(self._analyze_only)
        self.btn_analyze_all.clicked.connect(self._analyze_all_trajectories)
        self.btn_save.clicked.connect(self._save_project)
        self.btn_load_proj.clicked.connect(self._load_project)
        self.btn_iterate.clicked.connect(self._iterate)
        self.btn_debug.clicked.connect(self._show_debug)
        self.btn_copy.clicked.connect(self._copy_output)
        self.btn_help.clicked.connect(lambda: HelpDialog(self).exec_())

        self.btn_video_cal.clicked.connect(self._open_video_calibration)
        self.btn_roi.toggled.connect(self.canvas.set_roi_mode)
        self.btn_clear_roi.clicked.connect(self._clear_roi)

        self.traj_combo.currentIndexChanged.connect(self._switch_trajectory)
        self.btn_add_traj.clicked.connect(self._add_trajectory)
        self.btn_del_traj.clicked.connect(self._del_trajectory)

        self.canvas.holes_changed.connect(self._on_holes_changed)

        self.btn_curve_apply.clicked.connect(self._apply_curve)
        self.btn_curve_reset.clicked.connect(self._reset_curve)
        self.btn_toggle_anomalies.toggled.connect(self._toggle_anomalies)
        self.curve_editor.data_changed.connect(self._on_curve_changed)

        self.c_start_shot.currentIndexChanged.connect(
            lambda: self.canvas.set_start_shot(self.c_start_shot.currentData()))

        for combo in [self.c_gun, self.c_scope, self.c_muzzle, self.c_grip, self.c_stock, self.c_pose]:
            combo.currentIndexChanged.connect(self._on_config_changed)

    def _on_config_changed(self):
        self._read_config()
        self._update_results()

    # ═══ 配置读取 ═══

    def _read_config(self):
        """从 UI combo 读取当前配置, 同步到成员变量"""
        self._gun_name = self.c_gun.currentData() or ''

        self._scope_key = self.c_scope.currentData() or 'none'
        self._scope_val = 1.0

        mk = self.c_muzzle.currentData() or 'none'
        gk = self.c_grip.currentData() or 'none'
        sk = self.c_stock.currentData() or 'none'
        m_code = KEY_DATA.get('Muzzle', {}).get(mk, '0')
        g_code = KEY_DATA.get('Grip', {}).get(gk, '0')
        s_code = KEY_DATA.get('Stock', {}).get(sk, '0')
        self._acc_code = f"A{m_code}B{g_code}C{s_code}"

        self._pose_key = self.c_pose.currentData() or 'none'
        self._pose_val = self._get_pose_val()

    def _get_pose_val(self):
        """从 GunData 文件读取当前姿势倍率"""
        if self._pose_key == 'none':
            return 1.0
        gp = Path(self._gun_data_dir) / f"{self._gun_name}.json"
        if not gp.exists():
            return 1.0
        try:
            with open(gp, encoding='utf-8') as f:
                data = json.load(f)
            return float(data.get(self._pose_key, 1.0))
        except Exception:
            return 1.0

    def _get_config_dict(self):
        """返回当前配置 dict (用于 ProjectData.save)"""
        return {
            'gun_name': self._gun_name, 'acc_code': self._acc_code,
            'scope_key': self._scope_key, 'scope_val': self._scope_val,
            'pose_key': self._pose_key, 'pose_val': self._pose_val,
            'muzzle_key': self.c_muzzle.currentData() or 'none',
            'grip_key': self.c_grip.currentData() or 'none',
            'stock_key': self.c_stock.currentData() or 'none',
        }

    def _sensitivity_name(self):
        return 'medium'

    # ═══ 图片加载 ═══

    def _pick_result(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "选择弹痕截图或项目文件", "",
            "所有支持格式 (*.png *.jpg *.bmp *.calibration.json);;图片 (*.png *.jpg *.bmp);;项目文件 (*.calibration.json)")
        if not path:
            return

        if path.endswith('.calibration.json') or path.endswith('.analysis.json'):
            self._load_project_file(path)
            return

        img = cv2.imread(path)
        if img is None:
            QMessageBox.warning(self, "错误", f"无法读取: {path}")
            return
        self._result_img = img
        self._result_path = path
        pm = _cv2_to_pixmap(img)
        # 保留当前轨迹的弹孔
        self.canvas.set_image(pm)
        h, w = img.shape[:2]
        self.info_lb.setText(f"已加载: {Path(path).name} ({w}x{h})")

    # ═══ 轨迹管理 ═══

    def _save_current_traj_holes(self):
        if 0 <= self._current_traj_idx < len(self._trajectories):
            self._trajectories[self._current_traj_idx]['holes'] = list(self.canvas.get_holes())

    def _switch_trajectory(self, idx):
        if idx == self._current_traj_idx or idx < 0 or idx >= len(self._trajectories):
            return
        self._save_current_traj_holes()
        self._current_traj_idx = idx
        traj = self._trajectories[idx]
        self.canvas._holes = list(traj['holes'])
        self.canvas._selected = -1
        self.canvas.update()
        self.lbl_holes_count.setText(f"弹孔: {len(traj['holes'])}")
        self.info_lb.setText(f"切换到 {traj['name']} ({len(traj['holes'])}个弹孔)")

    def _add_trajectory(self):
        self._save_current_traj_holes()
        n = len(self._trajectories) + 1
        name = f"轨迹{n}"
        self._trajectories.append({'name': name, 'holes': [], 'comparison': None, 'correction': None})
        self.traj_combo.blockSignals(True)
        self.traj_combo.addItem(name)
        self.traj_combo.blockSignals(False)
        new_idx = len(self._trajectories) - 1
        self.traj_combo.setCurrentIndex(new_idx)
        self._current_traj_idx = new_idx
        self.canvas._holes = []
        self.canvas._selected = -1
        self.canvas.update()
        self.lbl_holes_count.setText("弹孔: 0")
        self.info_lb.setText(f"已新建 {name}, 在图片上左键标注弹孔")

    def _del_trajectory(self):
        if len(self._trajectories) <= 1:
            QMessageBox.information(self, "提示", "至少保留一个轨迹")
            return
        self._trajectories.pop(self._current_traj_idx)
        self.traj_combo.blockSignals(True)
        self.traj_combo.removeItem(self._current_traj_idx)
        self.traj_combo.blockSignals(False)
        new_idx = min(self._current_traj_idx, len(self._trajectories) - 1)
        self._current_traj_idx = new_idx
        self.traj_combo.setCurrentIndex(new_idx)
        traj = self._trajectories[new_idx]
        self.canvas._holes = list(traj['holes'])
        self.canvas._selected = -1
        self.canvas.update()
        self.lbl_holes_count.setText(f"弹孔: {len(traj['holes'])}")

    def _analyze_all_trajectories(self):
        """Round 1: 分析所有轨迹, 对各轨迹生成的逐发值取平均, 输出综合压枪数组"""
        self._save_current_traj_holes()
        self._read_config()
        if not self._gun_name:
            QMessageBox.warning(self, "提示", "请先选择枪械")
            return

        gen_results = []
        for traj in self._trajectories:
            if len(traj['holes']) < 2:
                continue
            gen = BulletParamGenerator.generate(
                traj['holes'], self._gun_name, self._scope_val, self._pose_val)
            if gen:
                gen_results.append((traj['name'], gen))

        if not gen_results:
            QMessageBox.warning(self, "提示", "没有可分析的轨迹 (每条至少2个弹孔)")
            return

        if len(gen_results) == 1:
            name, gen = gen_results[0]
            self._last_generation = gen
            self._last_correction = {
                'gun_name': self._gun_name, 'acc_code': self._acc_code,
                'corrected_uniform': gen['generated_array'],
                'original_array': gen['generated_array'],
                'chunk_size': gen['chunk_int'], 'chunk_size_f': gen['chunk_f'],
            }
            self.result_text.setHtml(_build_generation_html(gen, self._acc_code))
        else:
            # 多轨迹: 对 pixel_dy 逐发取平均后重新生成
            html = "<h3 style='color:#44cc44;'>多轨迹综合分析 (Round 1)</h3>"
            all_dys = []
            for name, gen in gen_results:
                dys = [d['pixel_dy'] for d in gen['details']]
                all_dys.append(dys)
                html += f"<p><b>{name}</b>: {len(dys)}发, 平均间距 {gen['avg_pixel_dy']}px</p>"

            min_len = min(len(d) for d in all_dys)
            avg_dys = []
            for j in range(min_len):
                vals = [d[j] for d in all_dys if j < len(d)]
                avg_dys.append(round(sum(vals) / len(vals), 2))

            chunk_f = gen_results[0][1]['chunk_f']
            chunk_int = gen_results[0][1]['chunk_int']
            factor = max(0.01, self._scope_val * self._pose_val)

            combined_array = []
            html += "<h4>综合逐发数据 (多轨迹平均):</h4>"
            html += "<table style='border-collapse:collapse; font-size:13px;' width='100%'>"
            html += "<tr style='background:#444;color:white;'><th>发</th><th>平均间距</th><th>每tick值</th></tr>"
            for j, dy in enumerate(avg_dys):
                v = round(dy / chunk_f / factor, 2)
                for _ in range(chunk_int):
                    combined_array.append(v)
                html += f"<tr><td style='text-align:center;'>{j+1}→{j+2}</td>"
                html += f"<td style='text-align:center;'>{dy:.2f}px</td>"
                html += f"<td style='text-align:center;color:#8f8;'><b>{v}</b></td></tr>"
            html += "</table>"

            arr_json = BulletParamGenerator.format_array_for_json(combined_array)
            html += f"""
            <h4 style="margin-top:12px;">综合压枪数据:</h4>
            <pre style="background:#222; padding:8px; font-size:11px; color:#8f8;">"{self._acc_code}": {arr_json}</pre>
            """

            self._last_correction = {
                'gun_name': self._gun_name, 'acc_code': self._acc_code,
                'corrected_uniform': combined_array,
                'original_array': combined_array,
                'chunk_size': chunk_int, 'chunk_size_f': chunk_f,
            }
            self.result_text.setHtml(html)

        self.info_lb.setText(f"已分析 {len(gen_results)} 条轨迹")
        self._update_curve_editor()

    def _pick_template(self):
        path, _ = QFileDialog.getOpenFileName(self, "选择弹孔模板", "", "图片 (*.png *.jpg *.bmp)")
        if not path:
            return
        img = cv2.imread(path)
        if img is None:
            QMessageBox.warning(self, "错误", f"无法读取: {path}")
            return
        self._template_img = img
        self._template_path = path
        self.info_lb.setText(f"模板: {Path(path).name} ({img.shape[1]}x{img.shape[0]})")

    def _clear_template(self):
        self._template_img = None
        self._template_path = None
        self.info_lb.setText("模板已清除")

    def _clear_roi(self):
        self.canvas.clear_roi()
        self.btn_roi.setChecked(False)

    # ═══ 检测弹孔 (仅检测, 不分析) ═══

    def _detect(self):
        """在当前图片上自动检测弹孔位置, 不进行参数分析"""
        if self._result_img is None:
            QMessageBox.warning(self, "提示", "请先加载弹痕截图")
            return

        sens = self._sensitivity_name()
        detector = BulletDetector(sens)
        roi = self.canvas.get_roi()

        holes = detector.detect_single(self._result_img, roi=roi)
        self._last_detector = detector

        if not holes:
            self.canvas.set_data([], None)
            self.info_lb.setText("未检测到弹痕! 建议: ①调高灵敏度 ②框选弹痕区域 ③右键手动添加")
            self.result_text.setHtml(
                '<p style="color:#ff6666;">未检测到弹痕</p>'
                '<ul><li>检查灵敏度设置 (试试「高」)</li>'
                '<li>使用「框选区域」限定检测范围</li>'
                '<li>右键手动添加弹孔</li></ul>'
                '<p>点击「检测过程」查看中间步骤</p>')
            return

        start_shot = self.c_start_shot.currentData() or 1
        BulletSorter.sort(holes, 'bottom_up', start_shot)
        pm = _cv2_to_pixmap(self._result_img)
        self.canvas.set_data(holes, pm)

        n = len(holes)
        di = detector.debug_info
        self.info_lb.setText(
            f"检测完成 | 灵敏度:{sens} | "
            f"暗点:{di.get('dark_count', 0)} Blob:{di.get('blob_count', 0)} "
            f"中值:{di.get('median_count', 0)} → 最终:{n}个弹孔  "
            f"(确认无误后点击「分析参数」)")

    # ═══ 分析参数 (仅分析, 不检测) ═══

    def _analyze_only(self):
        """Round 1: 从无压枪弹痕直接生成压枪数组 (不加载已有 GunData)"""
        holes = self.canvas.get_holes()
        if len(holes) < 2:
            QMessageBox.warning(self, "提示", "至少需要标注 2 个弹孔")
            return
        self._read_config()
        if not self._gun_name:
            QMessageBox.warning(self, "提示", "请先选择枪械")
            return

        gen_result = BulletParamGenerator.generate(
            holes, self._gun_name, self._scope_val, self._pose_val)

        if not gen_result:
            self.result_text.setHtml("<p style='color:#ff6666;'>生成失败, 请检查弹孔标注</p>")
            return

        self._last_generation = gen_result
        self._last_correction = {
            'gun_name': self._gun_name,
            'acc_code': self._acc_code,
            'corrected_uniform': gen_result['generated_array'],
            'original_array': gen_result['generated_array'],
            'avg_ratio': 1.0,
            'chunk_size': gen_result['chunk_int'],
            'chunk_size_f': gen_result['chunk_f'],
            'scope_val': self._scope_val,
            'posture_val': self._pose_val,
        }

        html = _build_generation_html(gen_result, self._acc_code)
        self.result_text.setHtml(html)

        if 0 <= self._current_traj_idx < len(self._trajectories):
            self._trajectories[self._current_traj_idx]['correction'] = self._last_correction

        traj_name = self._trajectories[self._current_traj_idx]['name'] if self._current_traj_idx >= 0 else ''
        self.info_lb.setText(
            f"Round 1 生成完成 [{traj_name}] | {self._gun_name} {self._acc_code} | "
            f"{len(holes)}发 → {len(gen_result['generated_array'])}个数组元素")
        self._update_curve_editor()

    # ═══ 结果刷新 ═══

    def _on_holes_changed(self):
        holes = self.canvas.get_holes()
        self.lbl_holes_count.setText(f"弹孔: {len(holes)}")
        if 0 <= self._current_traj_idx < len(self._trajectories):
            self._trajectories[self._current_traj_idx]['holes'] = list(holes)
        self._update_results()

    def _update_results(self):
        """标注变化时更新弹孔计数, 不自动分析 (需手动点击分析/迭代)"""
        holes = self.canvas.get_holes()
        n = len(holes)
        if n < 2:
            self.result_text.setHtml(
                f"<p style='color:gray;'>已标注 {n} 个弹孔, 至少需要 2 个</p>"
                "<p style='color:#888;'>标注完成后点击「分析参数」生成压枪数据</p>")
        elif not self._gun_name:
            self.result_text.setHtml(
                f"<p style='color:gray;'>已标注 {n} 个弹孔, 请先选择枪械</p>")

    # ═══ 保存项目 ═══

    def _save_project(self):
        self._save_current_traj_holes()
        all_holes = []
        for t in self._trajectories:
            all_holes.extend(t.get('holes', []))
        if not all_holes:
            QMessageBox.warning(self, "提示", "无弹孔数据可保存")
            return

        default_name = f"{self._gun_name}_{self._acc_code}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.calibration.json"
        path, _ = QFileDialog.getSaveFileName(self, "保存项目", default_name,
                                               "项目文件 (*.calibration.json)")
        if not path:
            return

        img_size = None
        if self._result_img is not None:
            img_size = (self._result_img.shape[1], self._result_img.shape[0])

        saved = ProjectData.save(
            path, all_holes, self._get_config_dict(),
            comparison=self._last_comparison, correction=self._last_correction,
            image_path=self._result_path, image_size=img_size,
            trajectories=self._trajectories)
        self._current_project_path = saved

        img_save_path = Path(saved).with_suffix('.annotated.png')
        self.canvas.save_annotation_image(str(img_save_path))

        n_traj = len(self._trajectories)
        self.info_lb.setText(f"已保存: {Path(saved).name} ({n_traj}条轨迹, {len(all_holes)}个弹孔)")

    # ═══ 加载项目 ═══

    def _load_project(self):
        path, _ = QFileDialog.getOpenFileName(self, "加载项目", "",
                                               "项目文件 (*.calibration.json *.analysis.json *.json)")
        if not path:
            return
        self._load_project_file(path)

    def _load_project_file(self, path):
        data, err = ProjectData.load(path)
        if err:
            QMessageBox.warning(self, "加载失败", err)
            return

        cfg = data.get('config', {})
        self._set_combo(self.c_gun, cfg.get('gun_name', ''))
        self._set_combo(self.c_scope, cfg.get('scope_key', 'none'))
        self._set_combo(self.c_muzzle, cfg.get('muzzle_key', 'none'))
        self._set_combo(self.c_grip, cfg.get('grip_key', 'none'))
        self._set_combo(self.c_stock, cfg.get('stock_key', 'none'))
        self._set_combo(self.c_pose, cfg.get('pose_key', 'none'))
        self._read_config()

        # 多轨迹加载
        saved_trajectories = data.get('trajectories')
        if saved_trajectories and isinstance(saved_trajectories, list):
            self._trajectories = []
            self.traj_combo.blockSignals(True)
            self.traj_combo.clear()
            for t in saved_trajectories:
                self._trajectories.append({
                    'name': t.get('name', f"轨迹{len(self._trajectories)+1}"),
                    'holes': t.get('holes', []),
                    'comparison': t.get('comparison'),
                    'correction': t.get('correction'),
                })
                self.traj_combo.addItem(self._trajectories[-1]['name'])
            self.traj_combo.blockSignals(False)
            self._current_traj_idx = 0
            self.traj_combo.setCurrentIndex(0)
            holes = self._trajectories[0]['holes'] if self._trajectories else []
        else:
            holes = data.get('holes', [])

        if not all('shot_num' in h for h in holes):
            start_shot = self.c_start_shot.currentData() or 1
            BulletSorter.sort(holes, 'bottom_up', start_shot)

        # 尝试加载原图
        img_path = data.get('image_path')
        pm = None
        if img_path and Path(img_path).exists():
            img = cv2.imread(img_path)
            if img is not None:
                self._result_img = img
                self._result_path = img_path
                pm = _cv2_to_pixmap(img)
        if pm is None:
            found = ProjectData.find_image(path)
            if found:
                img = cv2.imread(found)
                if img is not None:
                    self._result_img = img
                    self._result_path = found
                    pm = _cv2_to_pixmap(img)

        # 无图片时: 根据保存的 image_size 创建空白画布, 保证弹孔仍可见
        if pm is None and holes:
            img_size = data.get('image_size')
            if img_size and len(img_size) == 2:
                w, h = int(img_size[0]), int(img_size[1])
            else:
                xs = [hole['x'] for hole in holes]
                ys = [hole['y'] for hole in holes]
                w = max(xs) + 200
                h = max(ys) + 200
            blank = np.zeros((h, w, 3), dtype=np.uint8)
            blank[:] = (40, 40, 40)
            self._result_img = blank
            self._result_path = None
            pm = _cv2_to_pixmap(blank)

        # 加载到当前轨迹
        if 0 <= self._current_traj_idx < len(self._trajectories):
            self._trajectories[self._current_traj_idx]['holes'] = list(holes)

        self.canvas.set_data(holes, pm)
        self._current_project_path = path
        self.lbl_holes_count.setText(f"弹孔: {len(holes)}")

        self._update_results()

        status_parts = [f"已加载项目: {Path(path).name} ({len(holes)}个弹孔)"]
        if self._result_path:
            status_parts.append(f"图片: {Path(self._result_path).name}")
        elif pm is not None:
            status_parts.append("(无原图, 使用空白画布)")
        self.info_lb.setText(" | ".join(status_parts))

    def _set_combo(self, combo, key):
        """安全设置 combo 选中项, 按 userData 匹配"""
        for i in range(combo.count()):
            if combo.itemData(i) == key:
                combo.setCurrentIndex(i)
                return

    # ═══ 迭代修正 (Phase 3) ═══

    def _iterate(self):
        """迭代修正: 基于所有轨迹标注 + 当前GunData实际参数 → 比例修正

        支持多轨迹: 自动收集所有轨迹的弹孔, 对比例取平均。
        支持指定发数: 只修改标注范围内的数组元素。
        """
        self._save_current_traj_holes()

        # 收集所有有效轨迹
        valid_trajs = []
        for t in self._trajectories:
            if len(t.get('holes', [])) >= 2:
                valid_trajs.append(t['holes'])
        if not valid_trajs:
            QMessageBox.warning(self, "提示", "请先标注开宏后的弹痕 (至少2个弹孔, 至少1条轨迹)")
            return

        holes = valid_trajs[0]

        self._read_config()
        if not self._gun_name:
            QMessageBox.warning(self, "提示", "请先选择枪械")
            return

        gp = Path(self._gun_data_dir) / f"{self._gun_name}.json"
        if not gp.exists():
            QMessageBox.warning(self, "错误", f"枪械数据文件不存在: {gp}")
            return
        try:
            with open(gp, encoding='utf-8') as f:
                gun_data = json.load(f)
        except (json.JSONDecodeError, IOError) as e:
            QMessageBox.warning(self, "错误", f"读取枪械数据失败: {e}")
            return

        current_array = gun_data.get(self._acc_code, gun_data.get("A0B0C0", []))
        if not current_array:
            QMessageBox.warning(self, "错误", f"未找到配件码 {self._acc_code} 的弹道数据")
            return

        from calibration.bullet_analysis import _get_fire_interval, _TICK_MS
        fire_interval = _get_fire_interval(self._gun_name)
        if fire_interval and fire_interval > 0:
            chunk_f = fire_interval * 1000 / _TICK_MS
        else:
            chunk_f = len(current_array) / max(1, len(holes) - 1)

        prev_correction = {
            'corrected_uniform': list(current_array),
            'chunk_size': max(1, int(round(chunk_f))),
            'chunk_size_f': round(chunk_f, 2),
            'acc_code': self._acc_code,
            'gun_name': self._gun_name,
        }

        multi_trajs = valid_trajs[1:] if len(valid_trajs) > 1 else None
        iter_result = IterativeCorrector.correct(
            holes, prev_correction, self._scope_val, self._pose_val,
            multi_trajectories=multi_trajs)
        if not iter_result:
            self.result_text.setHtml("<p style='color:#ff6666;'>迭代修正计算失败</p>")
            return

        self._last_correction = iter_result
        self._last_comparison = None
        self.result_text.setHtml(_build_iteration_html(iter_result))

        # 自动保存
        self._save_current_traj_holes()
        ts = datetime.now().strftime('%Y%m%d_%H%M%S')
        save_name = f"{self._gun_name}_iter_{ts}.calibration.json"
        save_dir = Path("calibration_project")
        save_dir.mkdir(exist_ok=True)
        save_path = save_dir / save_name
        all_holes = []
        for t in self._trajectories:
            all_holes.extend(t.get('holes', []))
        ProjectData.save(
            str(save_path), all_holes, self._get_config_dict(),
            correction=iter_result,
            image_path=self._result_path,
            image_size=(self._result_img.shape[1], self._result_img.shape[0]) if self._result_img is not None else None,
            trajectories=self._trajectories)
        self._current_project_path = str(save_path)
        self.info_lb.setText(
            f"迭代修正完成 | 基准: {self._gun_name}.json [{self._acc_code}] | 已保存: {save_name}")
        self._update_curve_editor()

    # ═══ Debug ═══

    def _show_debug(self):
        if self._last_detector is None:
            QMessageBox.information(self, "提示", "请先执行一次分析")
            return
        DebugDialog(self._last_detector.debug_info,
                    self._last_detector.debug_images, self).exec_()

    # ═══ 视频校准 ═══

    def _open_video_calibration(self):
        self._read_config()
        if not self._gun_name:
            QMessageBox.warning(self, "提示", "请先选择枪械")
            return
        dlg = VideoCalibrationDialog(
            self._gun_name, self._acc_code,
            self._scope_val, self._pose_val,
            self._gun_data_dir, parent=self)
        if dlg.exec_() == QDialog.Accepted:
            frame = dlg.result_frame
            holes = dlg.result_holes
            if frame is not None and holes:
                self._result_img = frame
                self._result_path = dlg._annotated_path
                pm = _cv2_to_pixmap(frame)
                self.canvas.set_data(holes, pm)
                self.lbl_holes_count.setText(f"弹孔: {len(holes)}")
                if 0 <= self._current_traj_idx < len(self._trajectories):
                    self._trajectories[self._current_traj_idx]['holes'] = list(holes)
                self.info_lb.setText(
                    f"视频校准: {len(holes)} 个弹孔已加载到画布 | "
                    f"请审核弹孔位置 (左键拖拽/右键删除/左键空白添加)，"
                    f"确认后点击「分析参数」或「迭代修正」")

    # ═══ 复制 ═══

    def _copy_output(self):
        corr = self._last_correction
        if not corr:
            QMessageBox.information(self, "提示", "暂无修正参数")
            return
        arr = corr.get('corrected_uniform', [])
        if not arr:
            QMessageBox.information(self, "提示", "暂无可复制的数组")
            return
        acc_code = corr.get('acc_code', 'A0B0C0')
        arr_json = BulletParamGenerator.format_array_for_json(arr)
        text = f'    "{acc_code}": {arr_json}'
        QApplication.clipboard().setText(text)
        self.info_lb.setText(f"已复制到剪贴板 ({len(arr)}个元素)")

    # ═══ 曲线编辑器 ═══

    def _update_curve_editor(self):
        """分析/迭代完成后刷新曲线编辑器"""
        corr = self._last_correction
        if not corr:
            return
        arr = corr.get('corrected_uniform', [])
        chunk_f = corr.get('chunk_size_f', corr.get('chunk_size', 10))
        if arr:
            self.curve_editor.set_data(arr, chunk_f)
            # 自动检测并显示异常值
            anomalies = self.curve_editor.get_anomaly_info()
            if anomalies:
                self.info_lb.setText(f"曲线已加载 | 检测到 {len(anomalies)} 个异常值 (点击'隐藏异常标记'查看详情)")
            else:
                self.info_lb.setText("曲线已加载 | 数据质量良好")

    def _on_curve_changed(self, new_values):
        """曲线编辑器拖拽后的实时回调"""
        pass

    def _apply_curve(self):
        """将曲线编辑器的修改应用到 _last_correction"""
        new_values = self.curve_editor.get_values()
        if not new_values or not self._last_correction:
            QMessageBox.information(self, "提示", "暂无可应用的数据")
            return
        modified = self.curve_editor.get_modified_indices()
        self._last_correction['corrected_uniform'] = new_values
        acc_code = self._last_correction.get('acc_code', 'A0B0C0')
        arr_json_parts = []
        items_per_line = 36
        for row_start in range(0, len(new_values), items_per_line):
            row_end = min(row_start + items_per_line, len(new_values))
            parts = []
            for idx in range(row_start, row_end):
                v = new_values[idx]
                if idx in modified:
                    parts.append(f'<span style="color:#ffcc33; font-weight:bold;">{v}</span>')
                else:
                    parts.append(f'<span style="color:#666;">{v}</span>')
            line = "        " + ", ".join(parts)
            if row_end < len(new_values):
                line += ","
            arr_json_parts.append(line)

        html = f"""<div style="margin:8px;">
        <h3 style="color:#ffcc33;">曲线编辑结果</h3>
        <p>已修改 {len(modified)} 个元素 (黄色高亮)</p>
        <pre style="background:#222; padding:8px; overflow-x:auto; font-size:11px; line-height:1.6;">"{acc_code}": [
{chr(10).join(arr_json_parts)}
    ]</pre></div>"""
        self.result_text.setHtml(html)
        self.info_lb.setText(f"曲线编辑已应用 ({len(modified)}个元素已修改)")

    def _reset_curve(self):
        """重置曲线编辑器到上次分析/迭代结果"""
        self._update_curve_editor()
        self.info_lb.setText("曲线已重置")
    
    def _toggle_anomalies(self, checked):
        """切换异常值显示"""
        self.curve_editor.toggle_anomaly_display()
        if checked:
            self.btn_toggle_anomalies.setText("显示异常标记")
            self.anomaly_info.setVisible(False)
        else:
            self.btn_toggle_anomalies.setText("隐藏异常标记")
            # 显示异常信息
            self._update_anomaly_info()
            self.anomaly_info.setVisible(True)
    
    def _update_anomaly_info(self):
        """更新异常值信息面板"""
        anomalies = self.curve_editor.get_anomaly_info()
        if not anomalies:
            html = "<p style='color:#44cc44;'>✓ 未检测到异常值，数据质量良好</p>"
        else:
            high_count = sum(1 for a in anomalies if a['severity'] == 'high')
            medium_count = sum(1 for a in anomalies if a['severity'] == 'medium')
            low_count = sum(1 for a in anomalies if a['severity'] == 'low')
            
            html = f"<h3 style='color:#ffaa00; margin:5px 0;'>⚠ 检测到 {len(anomalies)} 个异常值</h3>"
            html += f"<p style='margin:3px 0;'><span style='color:#ff4444;'>■ 严重: {high_count}</span> | "
            html += f"<span style='color:#ff9900;'>■ 中等: {medium_count}</span> | "
            html += f"<span style='color:#ffff66;'>■ 轻微: {low_count}</span></p>"
            html += "<table style='border-collapse:collapse; font-size:11px; width:100%;'>"
            html += "<tr style='background:#333; color:white;'><th style='padding:3px;'>发数</th><th>类型</th><th>描述</th></tr>"
            
            for a in anomalies:
                if a['severity'] == 'high':
                    color = '#ff4444'
                    icon = '🔴'
                elif a['severity'] == 'medium':
                    color = '#ff9900'
                    icon = '🟠'
                else:
                    color = '#ffff66'
                    icon = '🟡'
                
                type_cn = {'reverse': '反向', 'spike': '突变', 'zero': '零值'}.get(a['type'], a['type'])
                html += f"<tr style='color:{color};'>"
                html += f"<td style='padding:2px; text-align:center;'>{a['index']+1}</td>"
                html += f"<td>{icon} {type_cn}</td>"
                html += f"<td>{a['desc']}</td></tr>"
            
            html += "</table>"
            html += "<p style='color:#aaa; font-size:10px; margin-top:5px;'>提示: 拖拽节点可手动修正异常值</p>"
        
        self.anomaly_info.setHtml(html)


# ═══════════════════════════════════════════
# 入口
# ═══════════════════════════════════════════

def main():
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    palette = app.palette()
    palette.setColor(palette.Window, QColor(45, 45, 45))
    palette.setColor(palette.WindowText, QColor(220, 220, 220))
    palette.setColor(palette.Base, QColor(30, 30, 30))
    palette.setColor(palette.Text, QColor(220, 220, 220))
    palette.setColor(palette.Button, QColor(55, 55, 55))
    palette.setColor(palette.ButtonText, QColor(220, 220, 220))
    app.setPalette(palette)

    win = MainWindow()
    win.show()
    sys.exit(app.exec_())


if __name__ == '__main__':
    main()
