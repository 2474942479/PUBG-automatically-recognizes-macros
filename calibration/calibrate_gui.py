#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
弹痕分析工具 (GUI) — 交互式标注 + 多组比对 + 缩放
用法: python -m calibration.calibrate_gui
"""

import sys, os, json, time, copy, cv2, numpy as np
from pathlib import Path
from PyQt5.QtCore import Qt, pyqtSignal, QPointF, QRectF
from PyQt5.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QComboBox, QPushButton, QFileDialog,
    QMessageBox, QTextEdit, QMenu, QSplitter,
    QDialog, QDialogButtonBox, QListWidget, QListWidgetItem,
)
from PyQt5.QtGui import QPixmap, QImage, QFont, QPainter, QColor, QPen, QBrush

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from data.fire_data import KEY_DATA
from calibration.bullet_analysis import (
    BulletDetector, BulletSorter, BulletComparator, BulletVisualizer,
    ParameterCorrector, MultiGroupAnalyzer,
    _find_gun_data_dir, _load_sensitivity_config,
)

MUZZLE_CN = {
    'none': '无', 'eliuquan': '扼流圈', 'yazuiqiangkou': '鸭嘴枪口',
    'jujiqiangbuchang': '狙击补偿', 'jujiqiangxiaoyan': '狙击消焰',
    'buqiangbuchang': '步枪补偿', 'buqiangxiaoyan': '步枪消焰', 'xiaoyin': '消音器',
    'chongfengqiangxiaoyan': '冲锋消焰', 'chongfengqiangbuchang': '冲锋补偿',
}
GRIP_CN = {
    'none': '无', 'banjieshi': '半截式', 'muzhi': '拇指', 'zhijiao': '直角', 'chuizhi': '垂直',
}
STOCK_CN = {
    'none': '无', 'zhanshuqiangtuo': '战术枪托', 'zhongxinqiangtuo': '重型枪托',
    'tuosaiban': '托腮板', 'zidandai': '子弹袋', 'zhedieshiqiangtuo': '折叠枪托',
}

SAVE_DIR = Path("./calibration_results")
SAVE_DIR.mkdir(exist_ok=True)


# ══════════════════════════════════════════════════════════
# 交互式弹痕画布（带缩放平移）
# ══════════════════════════════════════════════════════════

class BulletCanvas(QWidget):
    holesChanged = pyqtSignal()

    HOLE_RADIUS = 12
    HIT_RADIUS = 18
    ZOOM_MIN, ZOOM_MAX, ZOOM_STEP = 0.2, 10.0, 1.15

    def __init__(self, parent=None):
        super().__init__(parent)
        self._bg_img = None
        self._bg_pixmap = None
        self._holes = []
        self._selected = -1
        self._dragging = self._panning = False
        self._drag_offset = QPointF()
        self._pan_start = QPointF()
        self._zoom = 1.0
        self._pan = QPointF(0, 0)
        self.setMinimumSize(400, 300)
        self.setMouseTracking(True)
        self.setCursor(Qt.CrossCursor)

    def set_data(self, cv_img, holes):
        self._bg_img = cv_img.copy()
        self._holes = copy.deepcopy(holes)
        BulletSorter.sort(self._holes)
        h, w = cv_img.shape[:2]
        fmt = QImage.Format_BGR888 if cv_img.ndim == 3 and cv_img.shape[2] == 3 else QImage.Format_Grayscale8
        qimg = QImage(cv_img.data, w, h, cv_img.strides[0], fmt)
        self._bg_pixmap = QPixmap.fromImage(qimg)
        self._zoom = 1.0
        self._pan = QPointF(0, 0)
        self.update()

    def get_holes(self):
        return copy.deepcopy(self._holes)

    def reset_view(self):
        self._zoom = 1.0
        self._pan = QPointF(0, 0)
        self.update()

    def save_annotation_image(self, path):
        """保存标注图到文件（使用 OpenCV 全分辨率渲染）"""
        if self._bg_img is None or not self._holes:
            return False
        vis = BulletVisualizer.draw_holes(self._bg_img, self._holes)
        cv2.imwrite(str(path), vis)
        return True

    def _base_img_rect(self):
        if self._bg_pixmap is None:
            return QRectF()
        pw, ph = self._bg_pixmap.width(), self._bg_pixmap.height()
        ww, wh = self.width(), self.height()
        scale = min(ww / pw, wh / ph)
        return QRectF((ww - pw * scale) / 2, (wh - ph * scale) / 2, pw * scale, ph * scale)

    def _img_rect(self):
        base = self._base_img_rect()
        if base.isEmpty():
            return base
        cx = base.center().x() + self._pan.x()
        cy = base.center().y() + self._pan.y()
        w, h = base.width() * self._zoom, base.height() * self._zoom
        return QRectF(cx - w / 2, cy - h / 2, w, h)

    def _img_to_widget(self, ix, iy):
        r = self._img_rect()
        if r.isEmpty() or not self._bg_pixmap:
            return QPointF(ix, iy)
        pw, ph = self._bg_pixmap.width(), self._bg_pixmap.height()
        return QPointF(r.x() + ix / pw * r.width(), r.y() + iy / ph * r.height())

    def _widget_to_img(self, wx, wy):
        r = self._img_rect()
        if r.isEmpty() or not self._bg_pixmap:
            return (int(wx), int(wy))
        pw, ph = self._bg_pixmap.width(), self._bg_pixmap.height()
        ix = (wx - r.x()) / r.width() * pw
        iy = (wy - r.y()) / r.height() * ph
        return (int(max(0, min(pw - 1, ix))), int(max(0, min(ph - 1, iy))))

    def _find_hole(self, pos):
        r = self._img_rect()
        if r.isEmpty():
            return -1
        scale = r.width() / self._bg_pixmap.width() if self._bg_pixmap else 1
        hit = self.HIT_RADIUS * max(1.0, scale)
        for i, h in enumerate(self._holes):
            wp = self._img_to_widget(h['x'], h['y'])
            if (pos - wp).manhattanLength() < hit:
                return i
        return -1

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.fillRect(self.rect(), QColor(20, 20, 20))
        r = self._img_rect()
        if self._bg_pixmap and not r.isEmpty():
            p.drawPixmap(r.toRect(), self._bg_pixmap)

        if not self._holes:
            if not self._bg_pixmap:
                p.setPen(QPen(QColor(100, 100, 100)))
                p.setFont(QFont('Microsoft YaHei', 12))
                p.drawText(self.rect(), Qt.AlignCenter,
                           '点击"开始分析"后弹痕显示在此\n\n'
                           '滚轮缩放 | 中键/右键空白拖动 | 右键双击重置')
            p.end()
            return

        scale = r.width() / self._bg_pixmap.width() if self._bg_pixmap and r.width() > 0 else 1
        rad = max(6, int(self.HOLE_RADIUS * scale))
        font_size = max(8, int(10 * scale))
        s = sorted(self._holes, key=lambda h: h.get('shot_num', 0))

        for i in range(len(s) - 1):
            p1 = self._img_to_widget(s[i]['x'], s[i]['y'])
            p2 = self._img_to_widget(s[i + 1]['x'], s[i + 1]['y'])
            p.setPen(QPen(QColor(100, 255, 100, 150), 2))
            p.drawLine(p1, p2)
            dy = abs(s[i]['y'] - s[i + 1]['y'])
            dx = s[i + 1]['x'] - s[i]['x']
            mid = (p1 + p2) / 2
            p.setFont(QFont('Microsoft YaHei', max(7, font_size - 2)))
            p.setPen(QPen(QColor(200, 200, 200, 180)))
            p.drawText(mid.x() + 8, mid.y(), f'↕{dy} →{dx:+d}')

        for i, hv in enumerate(s):
            wp = self._img_to_widget(hv['x'], hv['y'])
            n = hv.get('shot_num', i + 1)
            is_sel = (i == self._selected or
                      (0 <= self._selected < len(self._holes) and self._holes[self._selected] is hv))
            col = QColor(255, 60, 60) if n <= 5 else QColor(255, 165, 0) if n <= 15 else QColor(80, 255, 80)
            if is_sel:
                p.setPen(QPen(QColor(255, 255, 0), 3))
                p.setBrush(QBrush(col))
                p.drawEllipse(wp, rad + 3, rad + 3)
            else:
                p.setPen(QPen(QColor(255, 255, 255, 200), 2))
                p.setBrush(QBrush(col))
                p.drawEllipse(wp, rad, rad)
            p.setFont(QFont('Microsoft YaHei', font_size, QFont.Bold))
            p.setPen(QPen(QColor(255, 255, 255)))
            p.drawText(int(wp.x() + rad + 4), int(wp.y() - rad + 2), str(n))

        p.setFont(QFont('Microsoft YaHei', 9))
        p.setPen(QPen(QColor(255, 186, 8)))
        p.drawText(8, self.height() - 8,
                   f'弹孔: {len(self._holes)} | 缩放: {int(self._zoom * 100)}%')
        p.end()

    def wheelEvent(self, event):
        if not self._bg_pixmap:
            return
        delta = event.angleDelta().y()
        if delta == 0:
            return
        old_zoom = self._zoom
        self._zoom = min(self.ZOOM_MAX, self._zoom * self.ZOOM_STEP) if delta > 0 \
            else max(self.ZOOM_MIN, self._zoom / self.ZOOM_STEP)
        mouse_pos = QPointF(event.pos())
        base_center = self._base_img_rect().center()
        center = base_center + self._pan
        ratio = self._zoom / old_zoom
        self._pan = mouse_pos - (mouse_pos - center) * ratio - base_center
        self.update()

    def mousePressEvent(self, event):
        if event.button() == Qt.MiddleButton:
            self._panning = True
            self._pan_start = QPointF(event.pos())
            self.setCursor(Qt.ClosedHandCursor)
            return
        if event.button() == Qt.LeftButton:
            idx = self._find_hole(QPointF(event.pos()))
            if idx >= 0:
                self._selected = idx
                self._dragging = True
                wp = self._img_to_widget(self._holes[idx]['x'], self._holes[idx]['y'])
                self._drag_offset = QPointF(event.pos()) - wp
            else:
                self._selected = -1
            self.update()
        elif event.button() == Qt.RightButton:
            idx = self._find_hole(QPointF(event.pos()))
            if idx >= 0:
                menu = QMenu(self)
                menu.setStyleSheet("QMenu{background:#2a2a2a;color:#FFF;border:1px solid #555;}"
                                   "QMenu::item:selected{background:#FFBA08;color:#000;}")
                del_act = menu.addAction(f"删除弹孔 #{self._holes[idx].get('shot_num', idx + 1)}")
                if menu.exec_(event.globalPos()) == del_act:
                    self._holes.pop(idx)
                    self._selected = -1
                    BulletSorter.sort(self._holes)
                    self.update()
                    self.holesChanged.emit()
            else:
                self._panning = True
                self._pan_start = QPointF(event.pos())
                self.setCursor(Qt.ClosedHandCursor)

    def mouseMoveEvent(self, event):
        if self._panning:
            delta = QPointF(event.pos()) - self._pan_start
            self._pan += delta
            self._pan_start = QPointF(event.pos())
            self.update()
        elif self._dragging and self._selected >= 0:
            pos = QPointF(event.pos()) - self._drag_offset
            ix, iy = self._widget_to_img(pos.x(), pos.y())
            self._holes[self._selected]['x'] = ix
            self._holes[self._selected]['y'] = iy
            self.update()

    def mouseReleaseEvent(self, event):
        if event.button() in (Qt.MiddleButton, Qt.RightButton) and self._panning:
            self._panning = False
            self.setCursor(Qt.CrossCursor)
            return
        if self._dragging:
            self._dragging = False
            BulletSorter.sort(self._holes)
            self.update()
            self.holesChanged.emit()

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.RightButton:
            self.reset_view()
            return
        if event.button() == Qt.LeftButton:
            r = self._img_rect()
            pos = QPointF(event.pos())
            if r.contains(pos):
                ix, iy = self._widget_to_img(pos.x(), pos.y())
                self._holes.append({'x': ix, 'y': iy, 'area': 100, 'circularity': 1.0, 'color_diff': 50})
                BulletSorter.sort(self._holes)
                self._selected = -1
                self.update()
                self.holesChanged.emit()


# ══════════════════════════════════════════════════════════
# 帮助对话框
# ══════════════════════════════════════════════════════════

class HelpDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("使用说明")
        self.setMinimumSize(600, 500)
        self.setStyleSheet("background:#1e1e1e;color:#EEE;font-family:'Microsoft YaHei';")
        layout = QVBoxLayout(self)
        text = QTextEdit()
        text.setReadOnly(True)
        text.setStyleSheet("background:#111;border:1px solid #333;border-radius:6px;padding:12px;font-size:13px;")
        text.setHtml("""
<h2 style="color:#FFBA08">PUBG 弹痕分析工具</h2>
<h3 style="color:#4AE54A">▎使用步骤</h3>
<ol>
<li>游戏中找一面干净墙壁，<b>先截空白基线图</b>，然后<b>不开宏</b>对着墙射击，截结果图</li>
<li>选择图片 → 设置枪械/配件/瞄具 → 开始分析</li>
<li>画布上手动修正弹孔位置 → 结果实时刷新</li>
<li>确认无误后复制修正参数到 GunData JSON 文件</li>
</ol>
<h3 style="color:#4AE54A">▎画布操作</h3>
<table><tr><td style="color:#FFBA08;padding:2px 8px">左键拖拽</td><td>移动弹孔</td></tr>
<tr><td style="color:#FFBA08;padding:2px 8px">双击空白</td><td>添加弹孔</td></tr>
<tr><td style="color:#FFBA08;padding:2px 8px">右键弹孔</td><td>删除弹孔</td></tr>
<tr><td style="color:#FFBA08;padding:2px 8px">滚轮</td><td>缩放</td></tr>
<tr><td style="color:#FFBA08;padding:2px 8px">中键/右键空白拖动</td><td>平移</td></tr>
<tr><td style="color:#FFBA08;padding:2px 8px">右键双击</td><td>重置视图</td></tr></table>
<h3 style="color:#4AE54A">▎多组比对</h3>
<p>多次射击取样 → 每次分析后点"添加到比对组" → 点"综合分析"获取最优参数（去除离群值）。</p>
<h3 style="color:#4AE54A">▎数据说明</h3>
<p><b>实际(px)</b>: 弹孔间像素距离<br>
<b>理论(px)</b>: JSON数组分块求和 × 灵敏度 × 姿态 = 宏应补偿像素量<br>
<b>原值</b>: JSON数组分块求和（不含灵敏度倍率）<br>
<b>比值</b>: 实际/理论，≈1.0说明校准准确</p>
<h3 style="color:#4AE54A">▎水平漂移</h3>
<p>PUBG 水平后坐力含随机分量，无法完全通过固定值补偿。工具会分析：
<br>• 如果均值大、标准差小 → 可添加X轴固定补偿
<br>• 如果标准差大 → 随机性强，不建议固定补偿</p>
""")
        layout.addWidget(text)
        btn = QDialogButtonBox(QDialogButtonBox.Ok)
        btn.setStyleSheet("QPushButton{background:#FFBA08;color:#000;border:none;border-radius:4px;"
                          "padding:8px 24px;font-weight:bold;}")
        btn.accepted.connect(self.accept)
        layout.addWidget(btn)


# ══════════════════════════════════════════════════════════
# 主窗口
# ══════════════════════════════════════════════════════════

def _cs():
    return "color:#FFF;background:#2a2a2a;border:1px solid #555;border-radius:4px;padding:4px 8px;font-size:13px;"

def _btn(text, color="#FFBA08", h=36):
    b = QPushButton(text)
    b.setStyleSheet(f"color:#FFF;background:#1a1a1a;border:1px solid {color};"
                    f"border-radius:6px;padding:6px 16px;font-size:13px;font-weight:bold;")
    b.setFixedHeight(h)
    return b


class MainWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("PUBG 弹痕分析 — 交互式标注")
        self.setStyleSheet("background:#1a1a1a;color:#FFF;font-family:'Microsoft YaHei';")
        self.base_path = self.result_path = None
        self._result_img = self._base_img = None
        self._gun_name = 'm762'
        self._acc_code = 'A0B0C0'
        self._scope_val = 1.0
        self._pose_val = 1.0
        self._gun_data_dir = _find_gun_data_dir()
        self._sensitivity_cfg = _load_sensitivity_config()
        self._multi = MultiGroupAnalyzer()
        self._build()

    def _build(self):
        root = QVBoxLayout(self)
        root.setSpacing(6)

        splitter = QSplitter(Qt.Vertical)
        splitter.setStyleSheet("QSplitter::handle{background:#333;height:4px;}")

        # ─── 顶部：图片+配置 ───
        top = QWidget()
        tl = QVBoxLayout(top)
        tl.setContentsMargins(8, 8, 8, 4)
        tl.setSpacing(5)

        title_row = QHBoxLayout()
        lb = QLabel("PUBG 弹痕分析工具")
        lb.setStyleSheet("color:#FFBA08;font-size:15px;font-weight:bold;")
        title_row.addWidget(lb)
        title_row.addStretch()
        for text, color, cb in [
            ("使用说明", "#4A90D9", self._show_help),
            ("重置视图", "#888", lambda: self.canvas.reset_view()),
        ]:
            b = _btn(text, color, 26)
            b.setFixedWidth(72)
            b.clicked.connect(cb)
            title_row.addWidget(b)
        tl.addLayout(title_row)

        img_row = QHBoxLayout()
        self.base_lb = QLabel("基线: 未选择")
        self.base_lb.setStyleSheet("color:#888;font-size:12px;")
        b1 = _btn("选择基线图", "#4AE54A", 28)
        b1.clicked.connect(self._pick_base)
        self.result_lb = QLabel("结果: 未选择")
        self.result_lb.setStyleSheet("color:#888;font-size:12px;")
        b2 = _btn("选择结果图", "#4AE54A", 28)
        b2.clicked.connect(self._pick_result)
        for w in [self.base_lb, b1, self.result_lb, b2]:
            img_row.addWidget(w)
        tl.addLayout(img_row)

        cfg_row = QHBoxLayout()
        self.c_gun = self._cbox({
            "m762": "M762", "akm": "AKM", "m416": "M416", "scar-l": "SCAR-L", "aug": "AUG",
            "groza": "Groza", "dp28": "DP28", "m249": "M249", "uzi": "UZI", "vector": "Vector",
            "mp5k": "MP5K", "ump45": "UMP45", "mini14": "Mini14", "sks": "SKS", "qbz": "QBZ",
            "g36c": "G36C", "mk12": "MK12", "mk14": "MK14", "mk47": "MK47", "qbu": "QBU",
            "vss": "VSS", "mg3": "MG3", "js9": "JS9", "k2": "K2", "p90": "P90",
            "pp19": "PP-19", "famas": "FAMAS", "ace32": "ACE32"})
        self.c_scope = self._cbox({"none": "机瞄", "hongdian": "红点", "quanxi": "全息",
                                   "2bei": "2倍", "3bei": "3倍", "4bei": "4倍",
                                   "6bei": "6倍", "8bei": "8倍", "15bei": "15倍"})
        self.c_muzz = self._cbox(MUZZLE_CN)
        self.c_grip = self._cbox(GRIP_CN)
        self.c_stk = self._cbox(STOCK_CN)
        self.c_pose = self._cbox({"none": "站立", "c": "蹲下", "z": "趴下"})
        for label, combo in [("枪", self.c_gun), ("镜", self.c_scope), ("口", self.c_muzz),
                             ("握", self.c_grip), ("托", self.c_stk), ("姿", self.c_pose)]:
            cfg_row.addWidget(QLabel(label))
            cfg_row.addWidget(combo)
        tl.addLayout(cfg_row)

        info_row = QHBoxLayout()
        self.acc_lb = QLabel("配件码: A0B0C0")
        self.acc_lb.setStyleSheet("color:#FFBA08;font-size:11px;")
        self.info_lb = QLabel("")
        self.info_lb.setStyleSheet("color:#888;font-size:11px;")
        info_row.addWidget(self.acc_lb)
        info_row.addStretch()
        info_row.addWidget(self.info_lb)
        tl.addLayout(info_row)

        act_row = QHBoxLayout()
        self.btn_analyze = _btn("开始分析", "#FFBA08", 36)
        self.btn_analyze.clicked.connect(self._analyze)
        act_row.addWidget(self.btn_analyze)
        self.btn_save_img = _btn("保存标注图", "#4A90D9", 36)
        self.btn_save_img.clicked.connect(self._save_annotation)
        self.btn_save_img.setEnabled(False)
        act_row.addWidget(self.btn_save_img)
        tl.addLayout(act_row)

        splitter.addWidget(top)

        # ─── 中部：画布 ───
        mid = QWidget()
        ml = QVBoxLayout(mid)
        ml.setContentsMargins(8, 4, 8, 4)
        lbl = QLabel("交互式弹痕标注  (左键拖拽 | 双击添加 | 右键删除 | 滚轮缩放 | 中键平移)")
        lbl.setStyleSheet("color:#FFBA08;font-size:12px;font-weight:bold;")
        ml.addWidget(lbl)
        self.canvas = BulletCanvas()
        self.canvas.holesChanged.connect(self._on_holes_changed)
        ml.addWidget(self.canvas, 1)
        splitter.addWidget(mid)

        # ─── 底部：结果 + 多组 ───
        bot = QWidget()
        bl = QVBoxLayout(bot)
        bl.setContentsMargins(8, 4, 8, 8)

        bot_splitter = QSplitter(Qt.Horizontal)
        bot_splitter.setStyleSheet("QSplitter::handle{background:#333;width:4px;}")

        # 左：结果文本
        result_w = QWidget()
        rl = QVBoxLayout(result_w)
        rl.setContentsMargins(0, 0, 0, 0)
        rl.setSpacing(4)
        rl.addWidget(QLabel("分析结果 + 修正参数（标注修改后自动刷新）"))
        self.result_text = QTextEdit()
        self.result_text.setReadOnly(True)
        self.result_text.setStyleSheet("background:#111;color:#4AE54A;border:1px solid #333;"
                                       "border-radius:6px;font-size:12px;font-family:'Consolas','Microsoft YaHei';")
        rl.addWidget(self.result_text, 1)
        copy_row = QHBoxLayout()
        self.btn_copy = _btn("复制修正参数", "#4A90D9", 28)
        self.btn_copy.clicked.connect(self._copy_output)
        self.btn_copy.setEnabled(False)
        copy_row.addStretch()
        copy_row.addWidget(self.btn_copy)
        rl.addLayout(copy_row)
        bot_splitter.addWidget(result_w)

        # 右：多组比对
        group_w = QWidget()
        gl = QVBoxLayout(group_w)
        gl.setContentsMargins(0, 0, 0, 0)
        gl.setSpacing(4)
        gl.addWidget(QLabel("多组比对"))
        self.group_list = QListWidget()
        self.group_list.setStyleSheet("background:#111;color:#FFF;border:1px solid #333;border-radius:4px;font-size:11px;")
        self.group_list.setMaximumHeight(120)
        gl.addWidget(self.group_list)
        gr = QHBoxLayout()
        self.btn_add_group = _btn("添加当前", "#4AE54A", 26)
        self.btn_add_group.clicked.connect(self._add_to_group)
        self.btn_add_group.setEnabled(False)
        self.btn_del_group = _btn("删除", "#FF4444", 26)
        self.btn_del_group.clicked.connect(self._del_group)
        self.btn_cross = _btn("综合分析", "#FFBA08", 26)
        self.btn_cross.clicked.connect(self._cross_compare)
        self.btn_cross.setEnabled(False)
        gr.addWidget(self.btn_add_group)
        gr.addWidget(self.btn_del_group)
        gr.addWidget(self.btn_cross)
        gl.addLayout(gr)
        self.cross_text = QTextEdit()
        self.cross_text.setReadOnly(True)
        self.cross_text.setStyleSheet("background:#111;color:#FFBA08;border:1px solid #333;"
                                      "border-radius:6px;font-size:11px;font-family:'Consolas','Microsoft YaHei';")
        gl.addWidget(self.cross_text, 1)
        bot_splitter.addWidget(group_w)

        bot_splitter.setStretchFactor(0, 3)
        bot_splitter.setStretchFactor(1, 2)
        bl.addWidget(bot_splitter)
        splitter.addWidget(bot)

        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 3)
        splitter.setStretchFactor(2, 3)

        root.addWidget(splitter)
        self.resize(900, 1000)

    # ── 工具方法 ──

    def _cbox(self, items):
        c = QComboBox()
        for k, v in items.items():
            c.addItem(v, userData=k)
        c.setStyleSheet(_cs())
        c.setFixedHeight(28)
        return c

    def _ck(self, c):
        return c.itemData(c.currentIndex()) or c.currentText().lower()

    def _acc(self):
        m = KEY_DATA['Muzzle'].get(self._ck(self.c_muzz), '0')
        g = KEY_DATA['Grip'].get(self._ck(self.c_grip), '0')
        s = KEY_DATA['Stock'].get(self._ck(self.c_stk), '0')
        return f"A{m}B{g}C{s}"

    def _show_help(self):
        HelpDialog(self).exec_()

    # ── 图片选择 ──

    def _pick_base(self):
        f, _ = QFileDialog.getOpenFileName(self, "选择基线图", str(SAVE_DIR), "Images (*.png *.jpg *.bmp)")
        if f:
            self.base_path = f
            self.base_lb.setText(f"基线: {os.path.basename(f)}")
            self.base_lb.setStyleSheet("color:#4AE54A;font-size:12px;")

    def _pick_result(self):
        f, _ = QFileDialog.getOpenFileName(self, "选择结果图", str(SAVE_DIR), "Images (*.png *.jpg *.bmp)")
        if f:
            self.result_path = f
            self.result_lb.setText(f"结果: {os.path.basename(f)}")
            self.result_lb.setStyleSheet("color:#4AE54A;font-size:12px;")

    # ── 分析 ──

    def _analyze(self):
        if not self.base_path or not self.result_path:
            QMessageBox.warning(self, "错误", "请先选择基线图和结果图")
            return
        self._base_img = cv2.imread(self.base_path)
        self._result_img = cv2.imread(self.result_path)
        if self._base_img is None or self._result_img is None:
            QMessageBox.warning(self, "错误", "图片加载失败")
            return

        self._gun_name = self._ck(self.c_gun)
        self._acc_code = self._acc()
        self.acc_lb.setText(f"配件码: {self._acc_code}")

        scope_name = self._ck(self.c_scope)
        pose = self._ck(self.c_pose)

        # 从 config.json 读取灵敏度
        self._scope_val = self._sensitivity_cfg.get(scope_name, 1.0)

        # 从枪械 JSON 读取姿态系数
        self._pose_val = 1.0
        gp = Path(self._gun_data_dir) / f"{self._gun_name}.json"
        if gp.exists():
            try:
                with open(gp, encoding='utf-8') as f:
                    self._pose_val = json.load(f).get(pose, 1)
            except Exception:
                pass

        self.info_lb.setText(f"灵敏度={self._scope_val}  姿势={self._pose_val}")

        detector = BulletDetector()
        holes = detector.detect(self._base_img, self._result_img)
        if not holes:
            self.result_text.setStyleSheet("background:#111;color:#FF4444;border:1px solid #333;border-radius:6px;font-size:12px;")
            self.result_text.setText("未检测到弹痕。\n请检查：两张图是否对准同一面墙、弹痕是否清晰。")
            return

        sorted_holes = BulletSorter.sort(holes)
        self.canvas.set_data(self._result_img, sorted_holes)
        self.info_lb.setText(f"灵敏度={self._scope_val}  姿势={self._pose_val}  |  {len(sorted_holes)} 个弹痕")

        self._update_results()
        self.btn_save_img.setEnabled(True)
        self.btn_add_group.setEnabled(True)

    def _on_holes_changed(self):
        self._update_results()

    def _update_results(self):
        """统一更新分析结果 + 修正参数（合并展示）"""
        holes = self.canvas.get_holes()
        if len(holes) < 2:
            self.result_text.setText(f"弹孔不足（当前 {len(holes)} 个，至少 2 个）")
            self.btn_copy.setEnabled(False)
            return

        comparator = BulletComparator(self._gun_data_dir)
        comp = comparator.compare(holes, self._gun_name, self._acc_code,
                                  self._scope_val, self._pose_val)

        text = f"{'═' * 60}\n"
        text += f"  弹痕分析 + 修正参数  ({len(holes)} 个弹孔)\n"
        text += f"{'═' * 60}\n"
        text += f"  枪械: {self._gun_name}   配件码: {self._acc_code}\n"
        text += f"  灵敏度: {self._scope_val}   姿势系数: {self._pose_val}\n\n"

        if not comp:
            gp = Path(self._gun_data_dir) / f"{self._gun_name}.json"
            text += f"  ⚠ 无法对比理论数据\n\n"
            text += f"  数据目录: {self._gun_data_dir}\n"
            text += f"  文件: {gp}\n"
            text += f"  存在: {'✅' if gp.exists() else '❌'}\n"
            if gp.exists():
                try:
                    with open(gp, encoding='utf-8') as f:
                        data = json.load(f)
                    text += f"  可用配件码: {', '.join(k for k in data if k.startswith('A'))}\n"
                except Exception as e:
                    text += f"  读取失败: {e}\n"
            self.result_text.setText(text)
            self.btn_copy.setEnabled(False)
            return

        # ── 对比表 ──
        text += f"  {'发':>3} {'实际px':>8} {'理论px':>8} {'原值':>6} {'比值':>8} {'X漂':>5} {'状态'}\n"
        text += f"  {'─' * 56}\n"
        for d in comp['details']:
            r_str = f"{d['ratio']:.4f}" if d['ratio'] is not None else "  N/A"
            text += (f"  {d['shot']:>3} {d['actual_dy']:>8.1f} {d['theory_dy']:>8.1f} "
                     f"{d['raw_chunk_sum']:>6.1f} {r_str:>8} {d['x_drift']:>+5.0f}  {d['status']}\n")
        text += f"  {'─' * 56}\n"
        text += f"  平均比值: {comp['avg_ratio']:.4f}   标准差: {comp['std_ratio']:.4f}\n"
        text += f"  建议灵敏度: {comp['suggested_scope']}\n\n"

        # ── 水平漂移 ──
        text += f"  ─── 水平漂移分析 ───\n"
        text += f"  均值: {comp['avg_horizontal_drift']:+.1f}px  "
        text += f"标准差: {comp['std_horizontal_drift']:.1f}px  "
        text += f"最大: {comp['max_horizontal_drift']:.1f}px\n"
        std_dx = comp.get('std_horizontal_drift', 0)
        avg_dx = abs(comp.get('avg_horizontal_drift', 0))
        if std_dx > avg_dx * 1.5 and avg_dx < 3:
            text += f"  结论: 水平漂移以随机分量为主(σ={std_dx:.1f})，无法通过固定值补偿\n"
            text += f"  建议: 使用垂直握把/补偿器减少水平后坐力，或接受随机性\n"
        else:
            text += f"  结论: 存在系统性水平偏移({comp['avg_horizontal_drift']:+.1f}px)，可添加X补偿\n"
        text += "\n"

        # ── 修正参数 ──
        corrector = ParameterCorrector(self._gun_data_dir)
        correction = corrector.correct(comp, self._gun_name, self._acc_code, use_float=True)

        if correction:
            text += f"  ═══ 修正后压枪参数 (比值={correction['avg_ratio']:.4f}) ═══\n"
            text += f"  复制下方内容替换到 {self._gun_name}.json 的 \"{correction['acc_code']}\" 字段:\n\n"

            patch_uniform = corrector.generate_patch_json(correction, mode='uniform')
            text += f"  方案一（均匀修正，所有值×{correction['avg_ratio']:.4f}）:\n"
            text += patch_uniform + "\n\n"

            patch_per = corrector.generate_patch_json(correction, mode='per_shot')
            text += f"  方案二（逐发修正，每发用独立比值）:\n"
            text += patch_per + "\n"

            # X补偿建议
            xc = correction.get('x_compensation')
            if xc and xc['type'] == 'compensatable':
                text += f"\n  ─── X轴补偿建议 ───\n"
                text += f"  {xc['suggestion']}\n"
                text += f"  注意: 需修改 Process.py 的 mouse_R(0, recoil) 为 mouse_R(x, recoil)\n"

            self._last_correction = correction
            self.btn_copy.setEnabled(True)
        else:
            text += "  ⚠ 无法生成修正参数\n"
            self._last_correction = None
            self.btn_copy.setEnabled(False)

        self.result_text.setStyleSheet("background:#111;color:#4AE54A;border:1px solid #333;"
                                       "border-radius:6px;font-size:12px;font-family:'Consolas','Microsoft YaHei';")
        self.result_text.setText(text)

    # ── 保存标注图 ──

    def _save_annotation(self):
        path, _ = QFileDialog.getSaveFileName(
            self, "保存标注图", str(SAVE_DIR / "annotated.png"), "Images (*.png *.jpg *.bmp)")
        if path:
            if self.canvas.save_annotation_image(path):
                self.info_lb.setText(f"标注图已保存: {os.path.basename(path)}")
            else:
                QMessageBox.warning(self, "错误", "保存失败，画布无数据")

    # ── 复制参数 ──

    def _copy_output(self):
        if hasattr(self, '_last_correction') and self._last_correction:
            corrector = ParameterCorrector(self._gun_data_dir)
            patch = corrector.generate_patch_json(self._last_correction, mode='uniform')
            QApplication.clipboard().setText(patch)
            self.info_lb.setText("均匀修正参数已复制到剪贴板")

    # ── 多组比对 ──

    def _add_to_group(self):
        holes = self.canvas.get_holes()
        if len(holes) < 2:
            return

        comparator = BulletComparator(self._gun_data_dir)
        comp = comparator.compare(holes, self._gun_name, self._acc_code,
                                  self._scope_val, self._pose_val)
        if not comp:
            QMessageBox.warning(self, "提示", "当前无有效比对数据")
            return

        label = f"#{self._multi.count + 1} {self._gun_name} {self._acc_code} ({len(holes)}孔 r={comp['avg_ratio']:.3f})"
        self._multi.add_group(comp, label)
        self.group_list.addItem(label)
        self.btn_cross.setEnabled(self._multi.count >= 2)
        self.info_lb.setText(f"已添加第 {self._multi.count} 组数据")

    def _del_group(self):
        row = self.group_list.currentRow()
        if row >= 0:
            self._multi.remove_group(row)
            self.group_list.takeItem(row)
            self.btn_cross.setEnabled(self._multi.count >= 2)

    def _cross_compare(self):
        if self._multi.count < 2:
            return

        analysis = self._multi.analyze()
        if not analysis:
            return

        text = f"{'═' * 50}\n"
        text += f"  综合分析  ({analysis['n_groups']} 组数据)\n"
        text += f"{'═' * 50}\n\n"

        text += f"  各组比值: "
        for i, (label, ratio) in enumerate(zip(analysis['group_labels'], analysis['group_ratios'])):
            text += f"{ratio:.4f}  "
        text += "\n\n"

        text += f"  最优比值: {analysis['overall_avg_ratio']:.4f}  (去除{analysis['n_outliers_removed']}个离群值)\n"
        text += f"  标准差: {analysis['overall_std_ratio']:.4f}\n"
        text += f"  置信度: {analysis['confidence']}\n"
        text += f"  水平漂移: 均值{analysis['overall_avg_x_drift']:+.1f}  σ={analysis['overall_std_x_drift']:.1f}\n\n"

        text += f"  {'发':>3} {'N组':>4} {'均值':>8} {'σ':>8} {'最小':>8} {'最大':>8} {'X漂移':>7}\n"
        text += f"  {'─' * 52}\n"
        for s in analysis['interval_stats']:
            if s is None:
                continue
            text += (f"  {s['interval']:>3} {s['n_groups']:>4} {s['avg_ratio']:>8.4f} "
                     f"{s['std_ratio']:>8.4f} {s['min_ratio']:>8.4f} {s['max_ratio']:>8.4f} "
                     f"{s['avg_x_drift']:>+6.1f}\n")

        # 生成最优修正参数
        optimal = self._multi.generate_optimal_correction(
            self._gun_name, self._acc_code, self._gun_data_dir)
        if optimal:
            arr = optimal['corrected_optimal']
            key = optimal['acc_code']
            formatted = ParameterCorrector.format_array_for_json(arr)
            text += f"\n  ═══ 最优修正参数（基于{analysis['n_groups']}组逐发平均）═══\n\n"
            text += f'    "{key}": {formatted}\n'

        self.cross_text.setText(text)


if __name__ == '__main__':
    import traceback
    def excepthook(etype, value, tb):
        err = ''.join(traceback.format_exception(etype, value, tb))
        try:
            QMessageBox.critical(None, '程序崩溃', f'出错了:\n\n{err}')
        except Exception:
            print(err)
    sys.excepthook = excepthook
    app = QApplication(sys.argv)
    w = MainWindow()
    w.show()
    sys.exit(app.exec_())
