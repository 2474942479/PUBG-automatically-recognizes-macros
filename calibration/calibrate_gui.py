#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
弹痕分析工具 (GUI) — 支持交互式手工标注
用法:
  python -m calibration.calibrate_gui
操作:
  1. 选择基线图和结果图 → 点"开始分析"自动检测弹痕
  2. 在画布上手动修正：
     - 左键拖拽 移动弹孔
     - 双击空白  添加弹孔
     - 右键弹孔  删除弹孔
  3. 修正后自动重新计算 → 点"导出修正参数"获取可替换的 JSON
"""

import sys, os, json, time, copy, cv2, numpy as np
from pathlib import Path
from PyQt5.QtCore import Qt, pyqtSignal, QPointF, QRectF
from PyQt5.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QComboBox, QPushButton, QFileDialog,
    QMessageBox, QSpinBox, QTextEdit, QScrollArea, QMenu, QAction,
    QSplitter, QFrame,
)
from PyQt5.QtGui import QPixmap, QImage, QFont, QPainter, QColor, QPen, QBrush

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from data.fire_data import KEY_DATA
from calibration.bullet_analysis import (
    BulletDetector, BulletSorter, BulletComparator,
    ParameterCorrector,
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
# 交互式弹痕画布
# ══════════════════════════════════════════════════════════

class BulletCanvas(QWidget):
    """
    可交互的弹痕标注画布。
    - 左键拖拽移动弹孔
    - 双击空白添加弹孔
    - 右键菜单删除弹孔
    - 修改后发出 holesChanged 信号
    """
    holesChanged = pyqtSignal()

    HOLE_RADIUS = 12
    HIT_RADIUS = 18

    def __init__(self, parent=None):
        super().__init__(parent)
        self._bg_img = None
        self._bg_pixmap = None
        self._holes = []
        self._selected = -1
        self._dragging = False
        self._drag_offset = QPointF()
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
        self.update()

    def get_holes(self):
        return copy.deepcopy(self._holes)

    def _img_rect(self):
        if self._bg_pixmap is None:
            return QRectF()
        pw, ph = self._bg_pixmap.width(), self._bg_pixmap.height()
        ww, wh = self.width(), self.height()
        scale = min(ww / pw, wh / ph)
        sw, sh = pw * scale, ph * scale
        x = (ww - sw) / 2
        y = (wh - sh) / 2
        return QRectF(x, y, sw, sh)

    def _img_to_widget(self, ix, iy):
        r = self._img_rect()
        if r.isEmpty() or self._bg_pixmap is None:
            return QPointF(ix, iy)
        pw, ph = self._bg_pixmap.width(), self._bg_pixmap.height()
        return QPointF(r.x() + ix / pw * r.width(), r.y() + iy / ph * r.height())

    def _widget_to_img(self, wx, wy):
        r = self._img_rect()
        if r.isEmpty() or self._bg_pixmap is None:
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
            if self._bg_pixmap is None:
                p.setPen(QPen(QColor(100, 100, 100)))
                p.setFont(QFont('Microsoft YaHei', 12))
                p.drawText(self.rect(), Qt.AlignCenter, '点击"开始分析"后弹痕会显示在此\n然后可以手动拖拽/添加/删除')
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
                      (self._selected >= 0 and self._selected < len(self._holes) and
                       self._holes[self._selected] is hv))

            if n <= 5:
                col = QColor(255, 60, 60)
            elif n <= 15:
                col = QColor(255, 165, 0)
            else:
                col = QColor(80, 255, 80)

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
        p.drawText(8, self.height() - 8, f'弹孔: {len(self._holes)} | 左键拖拽  双击添加  右键删除')
        p.end()

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            idx = self._find_hole(QPointF(event.pos()))
            if idx >= 0:
                self._selected = idx
                self._dragging = True
                wp = self._img_to_widget(self._holes[idx]['x'], self._holes[idx]['y'])
                self._drag_offset = QPointF(event.pos()) - wp
                self.update()
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
                action = menu.exec_(event.globalPos())
                if action == del_act:
                    self._holes.pop(idx)
                    self._selected = -1
                    BulletSorter.sort(self._holes)
                    self.update()
                    self.holesChanged.emit()

    def mouseMoveEvent(self, event):
        if self._dragging and self._selected >= 0:
            pos = QPointF(event.pos()) - self._drag_offset
            ix, iy = self._widget_to_img(pos.x(), pos.y())
            self._holes[self._selected]['x'] = ix
            self._holes[self._selected]['y'] = iy
            self.update()

    def mouseReleaseEvent(self, event):
        if self._dragging:
            self._dragging = False
            BulletSorter.sort(self._holes)
            self.update()
            self.holesChanged.emit()

    def mouseDoubleClickEvent(self, event):
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
# 主窗口
# ══════════════════════════════════════════════════════════

def _combo_style():
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
        self.base_path = None
        self.result_path = None
        self._result_img = None
        self._base_img = None
        self._gun_name = 'm762'
        self._acc_code = 'A0B0C0'
        self._scope_val = 1.0
        self._pose_val = 1.0

        self._build()
        self._find_defaults()

    def _build(self):
        root = QVBoxLayout(self)
        root.setSpacing(8)

        splitter = QSplitter(Qt.Vertical)
        splitter.setStyleSheet("QSplitter::handle{background:#333;height:4px;}")

        top = QWidget()
        top_layout = QVBoxLayout(top)
        top_layout.setContentsMargins(8, 8, 8, 4)
        top_layout.setSpacing(6)

        self._section(top_layout, "图片选择")
        img_row = QHBoxLayout()
        self.base_lb = QLabel("基线: 未选择")
        self.base_lb.setStyleSheet("color:#888;font-size:12px;")
        btn_base = _btn("选择基线图", "#4AE54A", 30)
        btn_base.clicked.connect(self._pick_base)
        self.result_lb = QLabel("结果: 未选择")
        self.result_lb.setStyleSheet("color:#888;font-size:12px;")
        btn_res = _btn("选择结果图", "#4AE54A", 30)
        btn_res.clicked.connect(self._pick_result)
        img_row.addWidget(self.base_lb)
        img_row.addWidget(btn_base)
        img_row.addSpacing(10)
        img_row.addWidget(self.result_lb)
        img_row.addWidget(btn_res)
        top_layout.addLayout(img_row)

        self._section(top_layout, "枪械配置")
        r1 = QHBoxLayout()
        self.c_gun = self._cbox({
            "m762": "M762", "akm": "AKM", "m416": "M416", "scar-l": "SCAR-L", "aug": "AUG",
            "groza": "Groza", "dp28": "DP28", "m249": "M249", "uzi": "UZI", "vector": "Vector",
            "mp5k": "MP5K", "ump45": "UMP45", "mini14": "Mini14", "sks": "SKS", "qbz": "QBZ",
            "g36c": "G36C", "mk12": "MK12", "mk14": "MK14", "mk47": "MK47", "qbu": "QBU",
            "vss": "VSS", "mg3": "MG3", "js9": "JS9", "k2": "K2", "p90": "P90",
            "pp19": "PP-19", "famas": "FAMAS", "ace32": "ACE32"})
        r1.addWidget(QLabel("枪:"))
        r1.addWidget(self.c_gun)
        self.c_scope = self._cbox({"none": "机瞄", "hongdian": "红点", "quanxi": "全息",
                                   "2bei": "2倍", "3bei": "3倍", "4bei": "4倍",
                                   "6bei": "6倍", "8bei": "8倍", "15bei": "15倍"})
        r1.addWidget(QLabel("镜:"))
        r1.addWidget(self.c_scope)
        self.c_muzz = self._cbox(MUZZLE_CN)
        r1.addWidget(QLabel("口:"))
        r1.addWidget(self.c_muzz)
        self.c_grip = self._cbox(GRIP_CN)
        r1.addWidget(QLabel("握:"))
        r1.addWidget(self.c_grip)
        self.c_stk = self._cbox(STOCK_CN)
        r1.addWidget(QLabel("托:"))
        r1.addWidget(self.c_stk)
        self.c_pose = self._cbox({"none": "站立", "c": "蹲下", "z": "趴下"})
        r1.addWidget(QLabel("姿:"))
        r1.addWidget(self.c_pose)
        top_layout.addLayout(r1)

        r2 = QHBoxLayout()
        self.acc_lb = QLabel("配件码: A0B0C0")
        self.acc_lb.setStyleSheet("color:#FFBA08;font-size:11px;")
        self.info_lb = QLabel("")
        self.info_lb.setStyleSheet("color:#888;font-size:11px;")
        r2.addWidget(self.acc_lb)
        r2.addStretch()
        r2.addWidget(self.info_lb)
        top_layout.addLayout(r2)

        btn_row = QHBoxLayout()
        self.btn_analyze = _btn("开始分析", "#FFBA08", 40)
        self.btn_analyze.clicked.connect(self._analyze)
        btn_row.addWidget(self.btn_analyze)
        self.btn_export = _btn("导出修正参数", "#4AE54A", 40)
        self.btn_export.clicked.connect(self._export)
        self.btn_export.setEnabled(False)
        btn_row.addWidget(self.btn_export)
        top_layout.addLayout(btn_row)

        splitter.addWidget(top)

        mid = QWidget()
        mid_layout = QVBoxLayout(mid)
        mid_layout.setContentsMargins(8, 4, 8, 4)
        self._section(mid_layout, "交互式弹痕标注  (左键拖拽 | 双击添加 | 右键删除)")
        self.canvas = BulletCanvas()
        self.canvas.holesChanged.connect(self._on_holes_changed)
        mid_layout.addWidget(self.canvas, 1)
        splitter.addWidget(mid)

        bot = QWidget()
        bot_layout = QVBoxLayout(bot)
        bot_layout.setContentsMargins(8, 4, 8, 8)
        self._section(bot_layout, "分析结果 / 修正参数")
        self.result_text = QTextEdit()
        self.result_text.setReadOnly(True)
        self.result_text.setStyleSheet("background:#111;color:#4AE54A;border:1px solid #333;"
                                       "border-radius:6px;font-size:12px;font-family:'Consolas','Microsoft YaHei';")
        bot_layout.addWidget(self.result_text, 1)

        copy_row = QHBoxLayout()
        self.btn_copy = _btn("复制到剪贴板", "#4A90D9", 30)
        self.btn_copy.clicked.connect(self._copy_output)
        self.btn_copy.setEnabled(False)
        copy_row.addStretch()
        copy_row.addWidget(self.btn_copy)
        bot_layout.addLayout(copy_row)

        splitter.addWidget(bot)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 3)
        splitter.setStretchFactor(2, 2)

        root.addWidget(splitter)
        self.resize(750, 900)

    def _section(self, layout, title):
        lb = QLabel(title)
        lb.setStyleSheet("color:#FFBA08;font-size:13px;font-weight:bold;padding:2px 0;")
        layout.addWidget(lb)

    def _cbox(self, items):
        c = QComboBox()
        for k, v in items.items():
            c.addItem(v, userData=k)
        c.setStyleSheet(_combo_style())
        c.setFixedHeight(28)
        return c

    def _ck(self, c):
        return c.itemData(c.currentIndex()) or c.currentText().lower()

    def _acc(self):
        m = KEY_DATA['Muzzle'].get(self._ck(self.c_muzz), '0')
        g = KEY_DATA['Grip'].get(self._ck(self.c_grip), '0')
        s = KEY_DATA['Stock'].get(self._ck(self.c_stk), '0')
        return f"A{m}B{g}C{s}"

    def _find_defaults(self):
        for pattern, setter in [("*base*", self._set_base), ("*result*", self._set_result)]:
            files = sorted(SAVE_DIR.glob(pattern), key=lambda f: f.stat().st_mtime, reverse=True)
            for f in files:
                if f.suffix.lower() in ('.png', '.jpg', '.bmp'):
                    setter(str(f))
                    break

    def _pick_base(self):
        f, _ = QFileDialog.getOpenFileName(self, "选择基线图", str(SAVE_DIR), "Images (*.png *.jpg *.bmp)")
        if f:
            self._set_base(f)

    def _pick_result(self):
        f, _ = QFileDialog.getOpenFileName(self, "选择结果图", str(SAVE_DIR), "Images (*.png *.jpg *.bmp)")
        if f:
            self._set_result(f)

    def _set_base(self, path):
        self.base_path = path
        self.base_lb.setText(f"基线: {os.path.basename(path)}")
        self.base_lb.setStyleSheet("color:#4AE54A;font-size:12px;")

    def _set_result(self, path):
        self.result_path = path
        self.result_lb.setText(f"结果: {os.path.basename(path)}")
        self.result_lb.setStyleSheet("color:#4AE54A;font-size:12px;")

    def _analyze(self):
        if not self.base_path or not self.result_path:
            QMessageBox.warning(self, "错误", "请先选择基线图和结果图")
            return

        self._base_img = cv2.imread(self.base_path)
        self._result_img = cv2.imread(self.result_path)
        if self._base_img is None or self._result_img is None:
            QMessageBox.warning(self, "错误", "图片加载失败，请检查路径")
            return

        self._gun_name = self._ck(self.c_gun)
        self._acc_code = self._acc()
        self.acc_lb.setText(f"配件码: {self._acc_code}")

        scope_name = self._ck(self.c_scope)
        pose = self._ck(self.c_pose)

        self._scope_val = 1.0
        try:
            from core.process import ProcessClass
            pc = ProcessClass()
            cfg = pc.get_config_data('a')
            self._scope_val = cfg.get('sensitivity', {}).get(scope_name, 1.0)
        except Exception:
            pass

        self._pose_val = 1.0
        gp = Path(f"./_internal/GunData/{self._gun_name}.json")
        if gp.exists():
            with open(gp, encoding='utf-8') as f:
                self._pose_val = json.load(f).get(pose, 1)

        self.info_lb.setText(f"倍镜={self._scope_val:.2f}  姿势={self._pose_val:.2f}")

        detector = BulletDetector()
        holes = detector.detect(self._base_img, self._result_img)
        if not holes:
            self.result_text.setStyleSheet("background:#111;color:#FF4444;border:1px solid #333;border-radius:6px;font-size:12px;")
            self.result_text.setText("未检测到弹痕。\n\n请检查:\n1. 两张图是否对准了同一面墙\n2. 弹痕是否清晰可见")
            return

        sorted_holes = BulletSorter.sort(holes)
        self.canvas.set_data(self._result_img, sorted_holes)
        self.info_lb.setText(f"倍镜={self._scope_val:.2f}  姿势={self._pose_val:.2f}  |  检测到 {len(sorted_holes)} 个弹痕")

        self._update_comparison()
        self.btn_export.setEnabled(True)

    def _on_holes_changed(self):
        self._update_comparison()

    def _update_comparison(self):
        holes = self.canvas.get_holes()
        if len(holes) < 2:
            self.result_text.setText(f"弹孔数量不足（当前 {len(holes)} 个，至少需要 2 个）")
            return

        comparator = BulletComparator()
        comp = comparator.compare(holes, self._gun_name, self._acc_code,
                                  self._scope_val, self._pose_val)

        text = f"{'=' * 50}\n"
        text += f"  弹痕分析结果  ({len(holes)} 个弹孔)\n"
        text += f"{'=' * 50}\n"
        text += f"  枪械: {self._gun_name}   配件码: {self._acc_code}\n"
        text += f"  倍镜系数: {self._scope_val:.2f}   姿势系数: {self._pose_val:.2f}\n\n"

        if comp:
            text += f"  {'发数':>4} {'实际':>8} {'理论':>8} {'比值':>8} {'状态'}\n"
            text += f"  {'-' * 48}\n"
            for d in comp['details']:
                ratio_str = f"{d['ratio']:.3f}" if d['ratio'] is not None else "  N/A"
                text += f"  {d['shot']:>4} {d['actual_dy']:>8.1f} {d['theory_dy']:>8.1f} {ratio_str:>8}  {d['status']}\n"
            text += f"  {'-' * 48}\n"
            text += f"  平均比值: {comp['avg_ratio']:.3f}   标准差: {comp['std_ratio']:.3f}\n"
            text += f"  建议倍镜系数: {comp['suggested_scope']}\n"
            text += f"  水平漂移: 平均{comp['avg_horizontal_drift']:+.1f}px  最大{comp['max_horizontal_drift']:.1f}px\n"
        else:
            text += f"  无可对比的理论数据\n"
            text += f"  (检查 _internal/GunData/{self._gun_name}.json 是否存在)\n"

        self.result_text.setStyleSheet("background:#111;color:#4AE54A;border:1px solid #333;border-radius:6px;font-size:12px;"
                                       "font-family:'Consolas','Microsoft YaHei';")
        self.result_text.setText(text)

    def _export(self):
        holes = self.canvas.get_holes()
        if len(holes) < 2:
            QMessageBox.warning(self, "提示", "弹孔不足，无法导出")
            return

        comparator = BulletComparator()
        comp = comparator.compare(holes, self._gun_name, self._acc_code,
                                  self._scope_val, self._pose_val)
        if not comp:
            QMessageBox.warning(self, "提示", "无理论数据，无法生成修正参数")
            return

        corrector = ParameterCorrector()
        correction = corrector.correct(comp, self._gun_name, self._acc_code)
        if not correction:
            QMessageBox.warning(self, "提示", "生成修正参数失败")
            return

        patch = corrector.generate_patch_json(correction)

        text = f"{'=' * 55}\n"
        text += f"  修正后压枪参数\n"
        text += f"{'=' * 55}\n"
        text += f"  枪械: {self._gun_name}\n"
        text += f"  配件码: {self._acc_code}\n"
        text += f"  校准比值: {correction['avg_ratio']:.3f}\n"
        text += f"  建议倍镜: {correction['suggested_scope']}\n\n"
        text += f"  === 复制下面内容替换到 {self._gun_name}.json 中 ===\n\n"
        text += patch + "\n"

        self.result_text.setStyleSheet("background:#111;color:#FFBA08;border:1px solid #555;border-radius:6px;font-size:12px;"
                                       "font-family:'Consolas','Microsoft YaHei';")
        self.result_text.setText(text)
        self.btn_copy.setEnabled(True)

        ts = time.strftime('%Y%m%d_%H%M%S')
        out_path = SAVE_DIR / f"{ts}_correction.json"
        with open(out_path, 'w', encoding='utf-8') as f:
            json.dump(correction, f, indent=2, ensure_ascii=False)
        self.info_lb.setText(f"修正参数已保存到 {out_path.name}")

    def _copy_output(self):
        text = self.result_text.toPlainText()
        QApplication.clipboard().setText(text)
        self.info_lb.setText("已复制到剪贴板")


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
