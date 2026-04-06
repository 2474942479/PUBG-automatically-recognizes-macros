#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
弹痕分析工具 (GUI) — 单图/模板检测 + 交互式标注 + 多组比对 + 迭代修正
用法: python -m calibration.calibrate_gui
"""

import sys, os, json, time, copy, cv2, numpy as np
from pathlib import Path
from PyQt5.QtCore import Qt, pyqtSignal, QPointF, QRectF
from PyQt5.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QComboBox, QPushButton, QFileDialog,
    QMessageBox, QTextEdit, QMenu, QSplitter,
    QDialog, QDialogButtonBox, QListWidget,
)
from PyQt5.QtGui import QPixmap, QImage, QFont, QPainter, QColor, QPen, QBrush

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from data.fire_data import KEY_DATA
from calibration.bullet_analysis import (
    BulletDetector, BulletSorter, BulletComparator, BulletVisualizer,
    ParameterCorrector, MultiGroupAnalyzer, AnnotationData, IterativeCorrector,
    _find_gun_data_dir, _load_sensitivity_config,
)

MUZZLE_CN = {
    'none': '无', 'eliuquan': '扼流圈', 'yazuiqiangkou': '鸭嘴枪口',
    'jujiqiangbuchang': '狙击补偿', 'jujiqiangxiaoyan': '狙击消焰',
    'buqiangbuchang': '步枪补偿', 'buqiangxiaoyan': '步枪消焰', 'xiaoyin': '消音器',
    'chongfengqiangxiaoyan': '冲锋消焰', 'chongfengqiangbuchang': '冲锋补偿',
}
GRIP_CN = {'none': '无', 'banjieshi': '半截式', 'muzhi': '拇指', 'zhijiao': '直角', 'chuizhi': '垂直'}
STOCK_CN = {
    'none': '无', 'zhanshuqiangtuo': '战术枪托', 'zhongxinqiangtuo': '重型枪托',
    'tuosaiban': '托腮板', 'zidandai': '子弹袋', 'zhedieshiqiangtuo': '折叠枪托',
}

SAVE_DIR = Path("./calibration_results")
SAVE_DIR.mkdir(exist_ok=True)


# ══════════════════════════════════════════════════════════
# 交互式弹痕画布
# ══════════════════════════════════════════════════════════

class BulletCanvas(QWidget):
    holesChanged = pyqtSignal()
    HOLE_RADIUS, HIT_RADIUS = 12, 18
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
        self._zoom, self._pan = 1.0, QPointF(0, 0)
        self.update()

    def get_holes(self):
        return copy.deepcopy(self._holes)

    def reset_view(self):
        self._zoom, self._pan = 1.0, QPointF(0, 0)
        self.update()

    def save_annotation_image(self, path):
        if self._bg_img is None or not self._holes:
            return False
        vis = BulletVisualizer.draw_holes(self._bg_img, self._holes)
        cv2.imwrite(str(path), vis)
        AnnotationData.save(path, self._holes)
        return True

    def _base_rect(self):
        if not self._bg_pixmap:
            return QRectF()
        pw, ph = self._bg_pixmap.width(), self._bg_pixmap.height()
        ww, wh = self.width(), self.height()
        s = min(ww / pw, wh / ph)
        return QRectF((ww - pw * s) / 2, (wh - ph * s) / 2, pw * s, ph * s)

    def _img_rect(self):
        b = self._base_rect()
        if b.isEmpty():
            return b
        cx, cy = b.center().x() + self._pan.x(), b.center().y() + self._pan.y()
        w, h = b.width() * self._zoom, b.height() * self._zoom
        return QRectF(cx - w / 2, cy - h / 2, w, h)

    def _i2w(self, ix, iy):
        r = self._img_rect()
        if r.isEmpty() or not self._bg_pixmap:
            return QPointF(ix, iy)
        pw, ph = self._bg_pixmap.width(), self._bg_pixmap.height()
        return QPointF(r.x() + ix / pw * r.width(), r.y() + iy / ph * r.height())

    def _w2i(self, wx, wy):
        r = self._img_rect()
        if r.isEmpty() or not self._bg_pixmap:
            return (int(wx), int(wy))
        pw, ph = self._bg_pixmap.width(), self._bg_pixmap.height()
        return (int(max(0, min(pw - 1, (wx - r.x()) / r.width() * pw))),
                int(max(0, min(ph - 1, (wy - r.y()) / r.height() * ph))))

    def _find_hole(self, pos):
        r = self._img_rect()
        if r.isEmpty():
            return -1
        sc = r.width() / self._bg_pixmap.width() if self._bg_pixmap else 1
        hit = self.HIT_RADIUS * max(1.0, sc)
        for i, h in enumerate(self._holes):
            if (pos - self._i2w(h['x'], h['y'])).manhattanLength() < hit:
                return i
        return -1

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.fillRect(self.rect(), QColor(20, 20, 20))
        r = self._img_rect()
        if self._bg_pixmap and not r.isEmpty():
            p.drawPixmap(r.toRect(), self._bg_pixmap)
        if not self._holes:
            if not self._bg_pixmap:
                p.setPen(QPen(QColor(100, 100, 100)))
                p.setFont(QFont('Microsoft YaHei', 11))
                p.drawText(self.rect(), Qt.AlignCenter,
                           '选择弹痕图 → 开始分析\n或 加载已有标注\n\n滚轮缩放 | 中键平移 | 右键双击重置')
            p.end()
            return

        sc = r.width() / self._bg_pixmap.width() if self._bg_pixmap and r.width() > 0 else 1
        rad = max(6, int(self.HOLE_RADIUS * sc))
        fs = max(8, int(10 * sc))
        s = sorted(self._holes, key=lambda h: h.get('shot_num', 0))

        for i in range(len(s) - 1):
            p1, p2 = self._i2w(s[i]['x'], s[i]['y']), self._i2w(s[i + 1]['x'], s[i + 1]['y'])
            p.setPen(QPen(QColor(100, 255, 100, 150), 2))
            p.drawLine(p1, p2)
            dy, dx = abs(s[i]['y'] - s[i + 1]['y']), s[i + 1]['x'] - s[i]['x']
            mid = (p1 + p2) / 2
            p.setFont(QFont('Microsoft YaHei', max(7, fs - 2)))
            p.setPen(QPen(QColor(200, 200, 200, 180)))
            p.drawText(mid.x() + 8, mid.y(), f'↕{dy} →{dx:+d}')

        for i, hv in enumerate(s):
            wp = self._i2w(hv['x'], hv['y'])
            n = hv.get('shot_num', i + 1)
            sel = (i == self._selected or (0 <= self._selected < len(self._holes) and self._holes[self._selected] is hv))
            col = QColor(255, 60, 60) if n <= 5 else QColor(255, 165, 0) if n <= 15 else QColor(80, 255, 80)
            if sel:
                p.setPen(QPen(QColor(255, 255, 0), 3)); p.setBrush(QBrush(col)); p.drawEllipse(wp, rad + 3, rad + 3)
            else:
                p.setPen(QPen(QColor(255, 255, 255, 200), 2)); p.setBrush(QBrush(col)); p.drawEllipse(wp, rad, rad)
            p.setFont(QFont('Microsoft YaHei', fs, QFont.Bold))
            p.setPen(QPen(QColor(255, 255, 255)))
            p.drawText(int(wp.x() + rad + 4), int(wp.y() - rad + 2), str(n))

        p.setFont(QFont('Microsoft YaHei', 9))
        p.setPen(QPen(QColor(255, 186, 8)))
        p.drawText(8, self.height() - 8, f'弹孔: {len(self._holes)} | 缩放: {int(self._zoom * 100)}%')
        p.end()

    def wheelEvent(self, e):
        if not self._bg_pixmap:
            return
        d = e.angleDelta().y()
        if d == 0:
            return
        oz = self._zoom
        self._zoom = min(self.ZOOM_MAX, self._zoom * self.ZOOM_STEP) if d > 0 else max(self.ZOOM_MIN, self._zoom / self.ZOOM_STEP)
        mp = QPointF(e.pos())
        bc = self._base_rect().center()
        self._pan = mp - (mp - bc - self._pan) * (self._zoom / oz) - bc
        self.update()

    def mousePressEvent(self, e):
        if e.button() == Qt.MiddleButton:
            self._panning, self._pan_start = True, QPointF(e.pos())
            self.setCursor(Qt.ClosedHandCursor)
            return
        if e.button() == Qt.LeftButton:
            idx = self._find_hole(QPointF(e.pos()))
            if idx >= 0:
                self._selected, self._dragging = idx, True
                self._drag_offset = QPointF(e.pos()) - self._i2w(self._holes[idx]['x'], self._holes[idx]['y'])
            else:
                self._selected = -1
            self.update()
        elif e.button() == Qt.RightButton:
            idx = self._find_hole(QPointF(e.pos()))
            if idx >= 0:
                menu = QMenu(self)
                menu.setStyleSheet("QMenu{background:#2a2a2a;color:#FFF;border:1px solid #555;}QMenu::item:selected{background:#FFBA08;color:#000;}")
                da = menu.addAction(f"删除弹孔 #{self._holes[idx].get('shot_num', idx + 1)}")
                if menu.exec_(e.globalPos()) == da:
                    self._holes.pop(idx); self._selected = -1; BulletSorter.sort(self._holes); self.update(); self.holesChanged.emit()
            else:
                self._panning, self._pan_start = True, QPointF(e.pos())
                self.setCursor(Qt.ClosedHandCursor)

    def mouseMoveEvent(self, e):
        if self._panning:
            self._pan += QPointF(e.pos()) - self._pan_start; self._pan_start = QPointF(e.pos()); self.update()
        elif self._dragging and self._selected >= 0:
            ix, iy = self._w2i(*(QPointF(e.pos()) - self._drag_offset).toTuple())
            self._holes[self._selected]['x'], self._holes[self._selected]['y'] = ix, iy
            self.update()

    def mouseReleaseEvent(self, e):
        if e.button() in (Qt.MiddleButton, Qt.RightButton) and self._panning:
            self._panning = False; self.setCursor(Qt.CrossCursor); return
        if self._dragging:
            self._dragging = False; BulletSorter.sort(self._holes); self.update(); self.holesChanged.emit()

    def mouseDoubleClickEvent(self, e):
        if e.button() == Qt.RightButton:
            self.reset_view(); return
        if e.button() == Qt.LeftButton:
            r = self._img_rect()
            pos = QPointF(e.pos())
            if r.contains(pos):
                ix, iy = self._w2i(pos.x(), pos.y())
                self._holes.append({'x': ix, 'y': iy, 'area': 100, 'circularity': 1.0, 'color_diff': 50})
                BulletSorter.sort(self._holes); self._selected = -1; self.update(); self.holesChanged.emit()


# ══════════════════════════════════════════════════════════
# 帮助对话框
# ══════════════════════════════════════════════════════════

class HelpDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("使用说明")
        self.setMinimumSize(620, 520)
        self.setStyleSheet("background:#1e1e1e;color:#EEE;font-family:'Microsoft YaHei';")
        layout = QVBoxLayout(self)
        t = QTextEdit()
        t.setReadOnly(True)
        t.setStyleSheet("background:#111;border:1px solid #333;border-radius:6px;padding:12px;font-size:13px;")
        t.setHtml("""
<h2 style="color:#FFBA08">PUBG 弹痕分析工具</h2>
<h3 style="color:#4AE54A">▎三种检测模式</h3>
<table>
<tr><td style="color:#FFBA08;padding:2px 8px">单图自适应</td><td>只需弹痕图，自动生成虚拟基线（推荐）</td></tr>
<tr><td style="color:#FFBA08;padding:2px 8px">模板匹配</td><td>提供一个弹孔截图作为模板，多尺度匹配</td></tr>
<tr><td style="color:#FFBA08;padding:2px 8px">加载标注</td><td>加载之前保存的标注文件(.analysis.json)</td></tr>
</table>
<h3 style="color:#4AE54A">▎使用步骤</h3>
<ol><li>游戏中找干净墙壁，<b>不开宏</b>射击一梭子，截图</li>
<li>选择弹痕图 → 设置枪械/配件 → 开始分析</li>
<li>画布上修正弹孔 → 实时刷新结果和修正参数</li>
<li>保存标注图 → 下次可直接加载</li></ol>
<h3 style="color:#4AE54A">▎迭代修正</h3>
<p>第1轮：不开宏射击 → 分析 → 得到修正参数<br>
第2轮：<b>开宏</b>用修正参数射击 → 加载新弹痕图 → 加载上一轮参数JSON → 迭代修正<br>
原理：宏开启后弹孔应聚集，残余偏移=补偿误差 → 微调参数</p>
<h3 style="color:#4AE54A">▎画布操作</h3>
<p>左键拖拽移动 | 双击添加 | 右键删除 | 滚轮缩放 | 中键/右键空白平移 | 右键双击重置</p>
""")
        layout.addWidget(t)
        bb = QDialogButtonBox(QDialogButtonBox.Ok)
        bb.setStyleSheet("QPushButton{background:#FFBA08;color:#000;border:none;border-radius:4px;padding:8px 24px;font-weight:bold;}")
        bb.accepted.connect(self.accept)
        layout.addWidget(bb)


# ══════════════════════════════════════════════════════════
# 主窗口
# ══════════════════════════════════════════════════════════

def _cs():
    return "color:#FFF;background:#2a2a2a;border:1px solid #555;border-radius:4px;padding:4px 8px;font-size:13px;"

def _btn(text, color="#FFBA08", h=36):
    b = QPushButton(text)
    b.setStyleSheet(f"color:#FFF;background:#1a1a1a;border:1px solid {color};border-radius:6px;padding:6px 16px;font-size:13px;font-weight:bold;")
    b.setFixedHeight(h)
    return b


class MainWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("PUBG 弹痕分析 — 交互式标注")
        self.setStyleSheet("background:#1a1a1a;color:#FFF;font-family:'Microsoft YaHei';")
        self.result_path = self._template_path = None
        self._result_img = None
        self._gun_name = 'm762'
        self._acc_code = 'A0B0C0'
        self._scope_val = 1.0
        self._pose_val = 1.0
        self._gun_data_dir = _find_gun_data_dir()
        self._sensitivity_cfg = _load_sensitivity_config()
        self._multi = MultiGroupAnalyzer()
        self._last_correction = None
        self._build()

    def _build(self):
        root = QVBoxLayout(self)
        root.setSpacing(6)
        splitter = QSplitter(Qt.Vertical)
        splitter.setStyleSheet("QSplitter::handle{background:#333;height:4px;}")

        # ─── 顶部 ───
        top = QWidget()
        tl = QVBoxLayout(top)
        tl.setContentsMargins(8, 8, 8, 4)
        tl.setSpacing(5)

        tr = QHBoxLayout()
        lb = QLabel("PUBG 弹痕分析工具")
        lb.setStyleSheet("color:#FFBA08;font-size:15px;font-weight:bold;")
        tr.addWidget(lb); tr.addStretch()
        for t, c, cb in [("使用说明", "#4A90D9", self._show_help), ("重置视图", "#888", lambda: self.canvas.reset_view())]:
            b = _btn(t, c, 26); b.setFixedWidth(72); b.clicked.connect(cb); tr.addWidget(b)
        tl.addLayout(tr)

        # 图片选择
        ir = QHBoxLayout()
        self.result_lb = QLabel("弹痕图: 未选择")
        self.result_lb.setStyleSheet("color:#888;font-size:12px;")
        b1 = _btn("选择弹痕图", "#4AE54A", 28); b1.clicked.connect(self._pick_result)
        self.tmpl_lb = QLabel("模板: 无(可选)")
        self.tmpl_lb.setStyleSheet("color:#666;font-size:11px;")
        b2 = _btn("选模板", "#666", 26); b2.setFixedWidth(60); b2.clicked.connect(self._pick_template)
        b2c = _btn("清除", "#444", 26); b2c.setFixedWidth(42); b2c.clicked.connect(self._clear_template)
        ir.addWidget(self.result_lb); ir.addWidget(b1); ir.addSpacing(8)
        ir.addWidget(self.tmpl_lb); ir.addWidget(b2); ir.addWidget(b2c)
        tl.addLayout(ir)

        # 枪械配置
        cr = QHBoxLayout()
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
        for l, c in [("枪", self.c_gun), ("镜", self.c_scope), ("口", self.c_muzz),
                     ("握", self.c_grip), ("托", self.c_stk), ("姿", self.c_pose)]:
            cr.addWidget(QLabel(l)); cr.addWidget(c)
        tl.addLayout(cr)

        inr = QHBoxLayout()
        self.acc_lb = QLabel("配件码: A0B0C0")
        self.acc_lb.setStyleSheet("color:#FFBA08;font-size:11px;")
        self.info_lb = QLabel("")
        self.info_lb.setStyleSheet("color:#888;font-size:11px;")
        inr.addWidget(self.acc_lb); inr.addStretch(); inr.addWidget(self.info_lb)
        tl.addLayout(inr)

        # 操作按钮
        ar = QHBoxLayout()
        self.btn_analyze = _btn("开始分析", "#FFBA08", 34); self.btn_analyze.clicked.connect(self._analyze)
        self.btn_load = _btn("加载标注", "#4A90D9", 34); self.btn_load.clicked.connect(self._load_annotation)
        self.btn_iterate = _btn("迭代修正", "#FF8C00", 34); self.btn_iterate.clicked.connect(self._iterate)
        self.btn_save = _btn("保存标注图", "#4AE54A", 34); self.btn_save.clicked.connect(self._save_annotation)
        self.btn_save.setEnabled(False)
        ar.addWidget(self.btn_analyze); ar.addWidget(self.btn_load)
        ar.addWidget(self.btn_iterate); ar.addWidget(self.btn_save)
        tl.addLayout(ar)
        splitter.addWidget(top)

        # ─── 中部：画布 ───
        mid = QWidget()
        ml = QVBoxLayout(mid)
        ml.setContentsMargins(8, 4, 8, 4)
        ml.addWidget(QLabel("交互式弹痕标注  (左键拖 | 双击加 | 右键删 | 滚轮缩放 | 中键移)"))
        self.canvas = BulletCanvas()
        self.canvas.holesChanged.connect(self._on_holes_changed)
        ml.addWidget(self.canvas, 1)
        splitter.addWidget(mid)

        # ─── 底部：结果 + 多组 ───
        bot = QWidget()
        bl = QVBoxLayout(bot)
        bl.setContentsMargins(8, 4, 8, 8)
        bs = QSplitter(Qt.Horizontal)
        bs.setStyleSheet("QSplitter::handle{background:#333;width:4px;}")

        rw = QWidget()
        rl = QVBoxLayout(rw); rl.setContentsMargins(0, 0, 0, 0); rl.setSpacing(4)
        rl.addWidget(QLabel("分析结果 + 修正参数"))
        self.result_text = QTextEdit()
        self.result_text.setReadOnly(True)
        self.result_text.setStyleSheet("background:#111;color:#4AE54A;border:1px solid #333;border-radius:6px;font-size:12px;font-family:'Consolas','Microsoft YaHei';")
        rl.addWidget(self.result_text, 1)
        cpr = QHBoxLayout()
        self.btn_copy = _btn("复制修正参数", "#4A90D9", 28); self.btn_copy.clicked.connect(self._copy_output); self.btn_copy.setEnabled(False)
        cpr.addStretch(); cpr.addWidget(self.btn_copy)
        rl.addLayout(cpr)
        bs.addWidget(rw)

        gw = QWidget()
        gl = QVBoxLayout(gw); gl.setContentsMargins(0, 0, 0, 0); gl.setSpacing(4)
        gl.addWidget(QLabel("多组比对"))
        self.group_list = QListWidget()
        self.group_list.setStyleSheet("background:#111;color:#FFF;border:1px solid #333;border-radius:4px;font-size:11px;")
        self.group_list.setMaximumHeight(100)
        gl.addWidget(self.group_list)
        gr = QHBoxLayout()
        self.btn_add_g = _btn("添加当前", "#4AE54A", 24); self.btn_add_g.clicked.connect(self._add_to_group); self.btn_add_g.setEnabled(False)
        self.btn_del_g = _btn("删除", "#FF4444", 24); self.btn_del_g.clicked.connect(self._del_group)
        self.btn_cross = _btn("综合分析", "#FFBA08", 24); self.btn_cross.clicked.connect(self._cross_compare); self.btn_cross.setEnabled(False)
        self.btn_load_multi = _btn("批量加载", "#4A90D9", 24); self.btn_load_multi.clicked.connect(self._load_multi_annotations)
        gr.addWidget(self.btn_add_g); gr.addWidget(self.btn_del_g); gr.addWidget(self.btn_cross); gr.addWidget(self.btn_load_multi)
        gl.addLayout(gr)
        self.cross_text = QTextEdit()
        self.cross_text.setReadOnly(True)
        self.cross_text.setStyleSheet("background:#111;color:#FFBA08;border:1px solid #333;border-radius:6px;font-size:11px;font-family:'Consolas','Microsoft YaHei';")
        gl.addWidget(self.cross_text, 1)
        bs.addWidget(gw)
        bs.setStretchFactor(0, 3); bs.setStretchFactor(1, 2)
        bl.addWidget(bs)
        splitter.addWidget(bot)
        splitter.setStretchFactor(0, 0); splitter.setStretchFactor(1, 3); splitter.setStretchFactor(2, 3)
        root.addWidget(splitter)
        self.resize(920, 1000)

    def _cbox(self, items):
        c = QComboBox()
        for k, v in items.items():
            c.addItem(v, userData=k)
        c.setStyleSheet(_cs()); c.setFixedHeight(28); return c

    def _ck(self, c):
        return c.itemData(c.currentIndex()) or c.currentText().lower()

    def _acc(self):
        m = KEY_DATA['Muzzle'].get(self._ck(self.c_muzz), '0')
        g = KEY_DATA['Grip'].get(self._ck(self.c_grip), '0')
        s = KEY_DATA['Stock'].get(self._ck(self.c_stk), '0')
        return f"A{m}B{g}C{s}"

    def _show_help(self):
        HelpDialog(self).exec_()

    def _read_config(self):
        self._gun_name = self._ck(self.c_gun)
        self._acc_code = self._acc()
        self.acc_lb.setText(f"配件码: {self._acc_code}")
        self._scope_val = self._sensitivity_cfg.get(self._ck(self.c_scope), 1.0)
        self._pose_val = 1.0
        gp = Path(self._gun_data_dir) / f"{self._gun_name}.json"
        if gp.exists():
            try:
                with open(gp, encoding='utf-8') as f:
                    self._pose_val = json.load(f).get(self._ck(self.c_pose), 1)
            except Exception:
                pass
        self.info_lb.setText(f"灵敏度={self._scope_val}  姿势={self._pose_val}")

    # ── 图片选择 ──

    def _pick_result(self):
        f, _ = QFileDialog.getOpenFileName(self, "选择弹痕图", str(SAVE_DIR), "Images (*.png *.jpg *.bmp)")
        if f:
            self.result_path = f
            self.result_lb.setText(f"弹痕图: {os.path.basename(f)}")
            self.result_lb.setStyleSheet("color:#4AE54A;font-size:12px;")

    def _pick_template(self):
        f, _ = QFileDialog.getOpenFileName(self, "选择弹孔模板(小图)", str(SAVE_DIR), "Images (*.png *.jpg *.bmp)")
        if f:
            self._template_path = f
            self.tmpl_lb.setText(f"模板: {os.path.basename(f)}")
            self.tmpl_lb.setStyleSheet("color:#4AE54A;font-size:11px;")

    def _clear_template(self):
        self._template_path = None
        self.tmpl_lb.setText("模板: 无(可选)")
        self.tmpl_lb.setStyleSheet("color:#666;font-size:11px;")

    # ── 分析 ──

    def _analyze(self):
        if not self.result_path:
            QMessageBox.warning(self, "错误", "请先选择弹痕图")
            return
        self._result_img = cv2.imread(self.result_path)
        if self._result_img is None:
            QMessageBox.warning(self, "错误", "图片加载失败")
            return

        self._read_config()
        detector = BulletDetector()

        if self._template_path:
            tmpl = cv2.imread(self._template_path)
            if tmpl is None:
                QMessageBox.warning(self, "错误", "模板图加载失败")
                return
            holes = detector.detect_with_template(self._result_img, tmpl)
            mode = "模板匹配"
        else:
            holes = detector.detect_single(self._result_img)
            mode = "单图自适应"

        if not holes:
            self.result_text.setText(f"未检测到弹痕 ({mode})\n\n可能原因：\n1. 墙面纹理太重\n2. 弹痕不够清晰\n3. 尝试提供弹孔模板图")
            return

        sorted_holes = BulletSorter.sort(holes)
        self.canvas.set_data(self._result_img, sorted_holes)
        self.info_lb.setText(f"灵敏度={self._scope_val}  姿势={self._pose_val}  |  {mode} 检测到 {len(sorted_holes)} 个弹痕")
        self._update_results()
        self.btn_save.setEnabled(True)
        self.btn_add_g.setEnabled(True)

    # ── 加载已有标注 ──

    def _load_annotation(self):
        f, _ = QFileDialog.getOpenFileName(
            self, "加载标注文件", str(SAVE_DIR),
            "标注文件 (*.analysis.json);;图片文件 (*.png *.jpg *.bmp);;所有 (*)")
        if not f:
            return

        holes, meta = AnnotationData.load(f)
        if holes is None:
            QMessageBox.warning(self, "错误", "无法加载标注数据。\n请选择 .analysis.json 文件或对应的图片文件。")
            return

        # 查找对应图片
        if f.endswith('.json'):
            img_path = AnnotationData.find_image_for_json(f)
        else:
            img_path = f

        if img_path and os.path.exists(img_path):
            self._result_img = cv2.imread(img_path)
            self.result_path = img_path
            self.result_lb.setText(f"弹痕图: {os.path.basename(img_path)}")
            self.result_lb.setStyleSheet("color:#4AE54A;font-size:12px;")
        else:
            QMessageBox.warning(self, "提示", "找不到对应的原始图片，仅加载弹孔数据")

        # 恢复元数据中的配置
        if meta:
            for key, combo in [('gun', self.c_gun), ('scope', self.c_scope)]:
                val = meta.get(key)
                if val:
                    for i in range(combo.count()):
                        if combo.itemData(i) == val:
                            combo.setCurrentIndex(i)
                            break

        self._read_config()
        BulletSorter.sort(holes)
        if self._result_img is not None:
            self.canvas.set_data(self._result_img, holes)
        else:
            self.canvas._holes = copy.deepcopy(holes)
            self.canvas.update()

        self.info_lb.setText(f"加载了 {len(holes)} 个弹孔标注")
        self._update_results()
        self.btn_save.setEnabled(True)
        self.btn_add_g.setEnabled(True)

    # ── 批量加载多张标注 ──

    def _load_multi_annotations(self):
        files, _ = QFileDialog.getOpenFileNames(
            self, "批量加载标注文件", str(SAVE_DIR),
            "标注文件 (*.analysis.json);;所有 (*)")
        if not files:
            return

        self._read_config()
        loaded = 0
        for f in files:
            holes, meta = AnnotationData.load(f)
            if holes is None or len(holes) < 2:
                continue
            BulletSorter.sort(holes)
            comparator = BulletComparator(self._gun_data_dir)
            comp = comparator.compare(holes, self._gun_name, self._acc_code,
                                      self._scope_val, self._pose_val)
            if comp:
                label = f"#{self._multi.count + 1} {Path(f).stem} ({len(holes)}孔 r={comp['avg_ratio']:.3f})"
                self._multi.add_group(comp, label)
                self.group_list.addItem(label)
                loaded += 1

        self.btn_cross.setEnabled(self._multi.count >= 2)
        self.info_lb.setText(f"批量加载了 {loaded}/{len(files)} 个标注文件到比对组")

    # ── 迭代修正 ──

    def _iterate(self):
        # 步骤1: 加载新弹痕图
        img_f, _ = QFileDialog.getOpenFileName(self, "选择宏开启后的弹痕图", str(SAVE_DIR), "Images (*.png *.jpg *.bmp)")
        if not img_f:
            return
        img = cv2.imread(img_f)
        if img is None:
            QMessageBox.warning(self, "错误", "图片加载失败")
            return

        # 步骤2: 加载上一轮修正参数
        param_f, _ = QFileDialog.getOpenFileName(self, "选择上一轮修正参数 (JSON)", str(SAVE_DIR), "JSON (*.json)")
        if not param_f:
            return
        try:
            with open(param_f, encoding='utf-8') as f:
                prev_data = json.load(f)
        except Exception as e:
            QMessageBox.warning(self, "错误", f"JSON 加载失败: {e}")
            return

        prev_params = prev_data.get('corrected_uniform') or prev_data.get('corrected_per_shot') or prev_data.get('corrected_optimal')
        if not prev_params:
            QMessageBox.warning(self, "错误", "JSON 中找不到修正参数数组\n(需要 corrected_uniform / corrected_per_shot / corrected_optimal)")
            return

        self._read_config()

        # 检测弹痕
        detector = BulletDetector()
        holes = detector.detect_single(img)
        if not holes:
            QMessageBox.warning(self, "提示", "未检测到弹痕，尝试使用模板匹配")
            return

        sorted_holes = BulletSorter.sort(holes)
        self._result_img = img
        self.result_path = img_f
        self.canvas.set_data(img, sorted_holes)

        # 迭代修正
        chunk = prev_data.get('chunk_size', 12)
        correction = IterativeCorrector.correct(
            sorted_holes, prev_params, self._scope_val, self._pose_val, chunk)

        if not correction:
            self.result_text.setText("迭代修正失败：弹孔不足或参数无效")
            return

        text = f"{'═' * 55}\n"
        text += f"  迭代修正结果  ({len(sorted_holes)} 个弹孔)\n"
        text += f"{'═' * 55}\n"
        text += f"  平均残差: {correction['avg_residual_dy']:.1f}px  最大: {correction['max_residual_dy']:.1f}px\n\n"

        text += f"  {'发':>3} {'残差Y':>8} {'残差X':>8} {'调整px':>8} {'调整原值':>8}\n"
        text += f"  {'─' * 48}\n"
        for r in correction['residuals']:
            text += f"  {r['shot']:>3} {r['dy']:>8.1f} {r['dx']:>8.1f} {r['adjustment_px']:>8.1f} {r['adjustment_raw']:>8.2f}\n"

        text += f"\n  ═══ 迭代修正后参数 ═══\n\n"
        arr = correction['corrected_params']
        formatted = ParameterCorrector.format_array_for_json(arr)
        acc = prev_data.get('acc_code', self._acc_code)
        text += f'    "{acc}": {formatted}\n'

        self.result_text.setText(text)
        self._last_correction = {'corrected_uniform': arr, 'acc_code': acc, 'chunk_size': chunk}
        self.btn_copy.setEnabled(True)
        self.btn_save.setEnabled(True)

        # 保存迭代修正结果
        ts = time.strftime('%Y%m%d_%H%M%S')
        out = SAVE_DIR / f"{ts}_iteration.json"
        with open(out, 'w', encoding='utf-8') as f:
            json.dump(correction, f, indent=2, ensure_ascii=False)
        self.info_lb.setText(f"迭代修正完成，结果保存到 {out.name}")

    def _on_holes_changed(self):
        self._update_results()

    def _update_results(self):
        holes = self.canvas.get_holes()
        if len(holes) < 2:
            self.result_text.setText(f"弹孔不足（当前 {len(holes)} 个，至少 2 个）")
            self.btn_copy.setEnabled(False)
            return

        comparator = BulletComparator(self._gun_data_dir)
        comp = comparator.compare(holes, self._gun_name, self._acc_code,
                                  self._scope_val, self._pose_val)

        text = f"{'═' * 60}\n  弹痕分析 + 修正参数  ({len(holes)} 个弹孔)\n{'═' * 60}\n"
        text += f"  枪械: {self._gun_name}   配件码: {self._acc_code}\n"
        text += f"  灵敏度: {self._scope_val}   姿势系数: {self._pose_val}\n\n"

        if not comp:
            gp = Path(self._gun_data_dir) / f"{self._gun_name}.json"
            text += f"  ⚠ 无法对比理论数据\n  文件: {gp} ({'存在' if gp.exists() else '不存在'})\n"
            if gp.exists():
                try:
                    with open(gp, encoding='utf-8') as f:
                        data = json.load(f)
                    text += f"  可用配件码: {', '.join(k for k in data if k.startswith('A'))}\n"
                except Exception:
                    pass
            self.result_text.setText(text)
            self.btn_copy.setEnabled(False)
            return

        text += f"  {'发':>3} {'实际px':>8} {'理论px':>8} {'原值':>6} {'比值':>8} {'X漂':>5} {'状态'}\n"
        text += f"  {'─' * 56}\n"
        for d in comp['details']:
            r_s = f"{d['ratio']:.4f}" if d['ratio'] is not None else "  N/A"
            text += f"  {d['shot']:>3} {d['actual_dy']:>8.1f} {d['theory_dy']:>8.1f} {d['raw_chunk_sum']:>6.1f} {r_s:>8} {d['x_drift']:>+5.0f}  {d['status']}\n"
        text += f"  {'─' * 56}\n"
        text += f"  平均比值: {comp['avg_ratio']:.4f}   标准差: {comp['std_ratio']:.4f}\n"
        text += f"  建议灵敏度: {comp['suggested_scope']}\n\n"

        text += f"  ─── 水平漂移 ───\n"
        text += f"  均值: {comp['avg_horizontal_drift']:+.1f}px  σ: {comp['std_horizontal_drift']:.1f}px  最大: {comp['max_horizontal_drift']:.1f}px\n"
        std_dx, avg_dx = comp.get('std_horizontal_drift', 0), abs(comp.get('avg_horizontal_drift', 0))
        if std_dx > avg_dx * 1.5 and avg_dx < 3:
            text += f"  → 随机性为主(σ={std_dx:.1f})，不建议固定补偿\n\n"
        else:
            text += f"  → 系统性偏移({comp['avg_horizontal_drift']:+.1f}px)，可添加X补偿\n\n"

        corrector = ParameterCorrector(self._gun_data_dir)
        correction = corrector.correct(comp, self._gun_name, self._acc_code, use_float=True)
        if correction:
            text += f"  ═══ 修正参数 (r={correction['avg_ratio']:.4f}) ═══\n"
            text += f"  替换到 {self._gun_name}.json 的 \"{correction['acc_code']}\":\n\n"
            text += corrector.generate_patch_json(correction, 'uniform') + "\n"
            self._last_correction = correction
            self.btn_copy.setEnabled(True)
        else:
            self._last_correction = None
            self.btn_copy.setEnabled(False)

        self.result_text.setStyleSheet("background:#111;color:#4AE54A;border:1px solid #333;border-radius:6px;font-size:12px;font-family:'Consolas','Microsoft YaHei';")
        self.result_text.setText(text)

    def _save_annotation(self):
        path, _ = QFileDialog.getSaveFileName(self, "保存标注图", str(SAVE_DIR / "annotated.png"), "Images (*.png *.jpg)")
        if path:
            meta = {'gun': self._gun_name, 'acc': self._acc_code,
                    'scope': self._scope_val, 'posture': self._pose_val}
            if self.canvas.save_annotation_image(path):
                AnnotationData.save(path, self.canvas.get_holes(), meta)
                self.info_lb.setText(f"标注图+数据已保存: {os.path.basename(path)}")

    def _copy_output(self):
        if self._last_correction:
            patch = ParameterCorrector.generate_patch_json(self._last_correction, 'uniform')
            QApplication.clipboard().setText(patch)
            self.info_lb.setText("修正参数已复制")

    def _add_to_group(self):
        holes = self.canvas.get_holes()
        if len(holes) < 2:
            return
        comparator = BulletComparator(self._gun_data_dir)
        comp = comparator.compare(holes, self._gun_name, self._acc_code, self._scope_val, self._pose_val)
        if not comp:
            return
        label = f"#{self._multi.count + 1} {self._gun_name} {self._acc_code} ({len(holes)}孔 r={comp['avg_ratio']:.3f})"
        self._multi.add_group(comp, label)
        self.group_list.addItem(label)
        self.btn_cross.setEnabled(self._multi.count >= 2)
        self.info_lb.setText(f"已添加第 {self._multi.count} 组")

    def _del_group(self):
        row = self.group_list.currentRow()
        if row >= 0:
            self._multi.remove_group(row); self.group_list.takeItem(row)
            self.btn_cross.setEnabled(self._multi.count >= 2)

    def _cross_compare(self):
        if self._multi.count < 2:
            return
        analysis = self._multi.analyze()
        if not analysis:
            return

        text = f"{'═' * 50}\n  综合分析  ({analysis['n_groups']} 组)\n{'═' * 50}\n\n"
        text += f"  各组: " + "  ".join(f"{r:.4f}" for r in analysis['group_ratios']) + "\n"
        text += f"  最优: {analysis['overall_avg_ratio']:.4f}  σ={analysis['overall_std_ratio']:.4f}  [{analysis['confidence']}]\n\n"

        text += f"  {'发':>3} {'N':>3} {'均值':>8} {'σ':>8} {'X漂':>6}\n  {'─' * 36}\n"
        for s in analysis['interval_stats']:
            if s:
                text += f"  {s['interval']:>3} {s['n_groups']:>3} {s['avg_ratio']:>8.4f} {s['std_ratio']:>8.4f} {s['avg_x_drift']:>+5.1f}\n"

        optimal = self._multi.generate_optimal_correction(self._gun_name, self._acc_code, self._gun_data_dir)
        if optimal:
            arr = optimal['corrected_optimal']
            formatted = ParameterCorrector.format_array_for_json(arr)
            text += f"\n  ═══ 最优参数 ═══\n\n    \"{optimal['acc_code']}\": {formatted}\n"

        self.cross_text.setText(text)


if __name__ == '__main__':
    import traceback
    def excepthook(t, v, tb):
        err = ''.join(traceback.format_exception(t, v, tb))
        try:
            QMessageBox.critical(None, '崩溃', err)
        except Exception:
            print(err)
    sys.excepthook = excepthook
    app = QApplication(sys.argv)
    w = MainWindow()
    w.show()
    sys.exit(app.exec_())
