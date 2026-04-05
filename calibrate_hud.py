#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
校准 HUD — 游戏内悬浮窗
═══════════════════════
F12  切换编辑/穿透模式
F5    拍基线（空白墙）
F6    拍结果（打完枪）
F7    开始分析
F10   隐藏/显示 HUD

右键拖拽移动位置
"""

import sys, os, json, time, ctypes
from pathlib import Path
from ctypes import wintypes

# ── PyQt5 ──
from PyQt5.QtCore import Qt, QTimer, QRect, QPoint, pyqtSignal
from PyQt5.QtWidgets import (
    QApplication, QWidget, QLabel, QVBoxLayout, QHBoxLayout,
    QComboBox, QPushButton, QFrame, QMessageBox, QSizePolicy
)
from PyQt5.QtGui import QPainter, QColor, QPen, QFont, QFontDatabase, QBrush, QScreen

# ── 外部依赖 ──
import mss
import numpy as np
import cv2

# ── 项目模块 ──
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from Process import ProcessClass
from fire_data import KEY_DATA
from resolution_setting import RESOLUTION_SETTINGS, Zishi

try:
    import keyboard
    HAS_KB = True
except ImportError:
    HAS_KB = False

# ═══════════ Win32 穿透 ═══════════
GWL_EXSTYLE = -20
WS_EX_TRANSPARENT = 0x020
WS_EX_LAYERED     = 0x080000
WS_EX_NOACTIVATE  = 0x08000000
user32 = ctypes.windll.User32

def set_no_activate(hwnd):
    try:
        ex = user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
        user32.SetWindowLongW(hwnd, GWL_EXSTYLE,
            ex | WS_EX_TRANSPARENT | WS_EX_LAYERED | WS_EX_NOACTIVATE)
    except Exception:
        pass

def allow_click(hwnd):
    try:
        ex = user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
        ex &= ~(WS_EX_TRANSPARENT)
        user32.SetWindowLongW(hwnd, GWL_EXSTYLE, ex)
    except Exception:
        pass

# ═══════════ 屏幕捕获 ═══════════
WALL_ROI = {
    "3840x2160": (0, 0, 1920, 1080),
    "2560x1440": (0, 0, 1920, 1080),
    "1920x1080": (0, 0, 1920, 1080),
}

class ScreenCapture:
    def __init__(self, resolution="3840x2160"):
        self.resolution = resolution
        self.roi = WALL_ROI.get(resolution, WALL_ROI["3840x2160"])

    def grab(self):
        x, y, w, h = self.roi
        with mss.mss() as sct:
            monitor = {"left": x, "top": y, "width": w, "height": h}
            return np.array(sct.grab(monitor))

# ═══════════ 弹痕检测 ═══════════
MIN_AREA, MAX_AREA, MIN_CIRC, COLOR_TH = 20, 800, 0.25, 15

def detect_holes(base, result):
    bg = cv2.cvtColor(base, cv2.COLOR_BGR2GRAY)
    rg = cv2.cvtColor(result, cv2.COLOR_BGR2GRAY)
    diff = cv2.absdiff(bg, rg)
    _, thresh = cv2.threshold(diff, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    k = np.ones((5, 5), np.uint8)
    thresh = cv2.morphologyEx(thresh, cv2.MORPH_CLOSE, k, iterations=2)
    thresh = cv2.dilate(thresh, k, iterations=2)
    contours, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    holes = []
    for cnt in contours:
        area = cv2.contourArea(cnt)
        if not (MIN_AREA < area < MAX_AREA): continue
        peri = cv2.arcLength(cnt, True)
        if peri == 0: continue
        circ = 4 * np.pi * (area / (peri * peri))
        if circ < MIN_CIRC: continue
        M = cv2.moments(cnt)
        if M["m00"] == 0: continue
        cx, cy = int(M["m10"]/M["m00"]), int(M["m01"]/M["m00"])
        mask = np.zeros(bg.shape[:2], dtype=np.uint8)
        cv2.drawContours(mask, [cnt], -1, 255, -1)
        cd = abs(cv2.mean(bg, mask=mask)[0] - cv2.mean(rg, mask=mask)[0])
        if cd < COLOR_TH: continue
        holes.append({'x': cx, 'y': cy, 'area': area, 'circularity': circ})
    return holes

def sort_holes(holes):
    if not holes: return holes
    s = sorted(holes, key=lambda h: (h['y'], h['x']))
    if len(s) > 1:
        mid = len(s) // 2
        if np.mean([h['y'] for h in s[mid:]]) < np.mean([h['y'] for h in s[:mid]]):
            s = s[::-1]
    for i, h in enumerate(s): h['shot_num'] = i + 1
    return s

def compare_with_json(holes, gr):
    if len(holes) < 2: return None
    s = sorted(holes, key=lambda h: h['shot_num'])
    gp = Path(f"./_internal/GunData/{gr['gun_name']}.json")
    if not gp.exists(): return None
    with open(gp, encoding='utf-8') as f:
        gun = json.load(f)
    raw = gun.get(gr['acc_code'], gun.get("A0B0C0", []))
    if not raw: return None
    actual = [s[i]['y']-s[i-1]['y'] for i in range(1, len(s))]
    jd = [raw[j] for j in range(0, min(len(actual)*2, len(raw)), 2)]
    theory = [j*gr['scope_val']*gr['posture_val'] for j in jd if j != 0]
    av = [d for d in actual if d > 0]
    ratios = []
    for i in range(min(len(av), len(theory))):
        if theory[i] > 0: ratios.append(av[i]/theory[i])
    if not ratios: return None
    avg, std = np.mean(ratios), np.std(ratios)
    suggested = round(gr['scope_val'] * avg, 2)
    return {
        'avg_ratio': round(float(avg), 3),
        'std_ratio': round(float(std), 3),
        'suggested_scope': suggested,
        'current_scope': gr['scope_val'],
        'shot_count': len(av)+1,
    }

def get_save_dir():
    d = Path("./calibration_results")
    d.mkdir(exist_ok=True)
    return d

def save_image(name, img):
    from datetime import datetime
    ts = datetime.now().strftime('%Y%m%d_%H%M%S')
    path = get_save_dir() / f"{ts}_{name}.png"
    cv2.imwrite(str(path), img)
    return path

def save_json(data):
    from datetime import datetime
    ts = datetime.now().strftime('%Y%m%d_%H%M%S')
    path = get_save_dir() / f"{ts}_result.json"
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    return path

# ═══════════ 样式 ═══════════
PUBG_BG = "rgba(18, 18, 18, 0.92)"
PUBG_BORDER = "rgba(255, 186, 8, 0.6)"
PUBG_GREEN = "#4AE54A"
PUBG_GOLD = "#FFBA08"
PUBG_RED = "#FF4444"
PUBG_GRAY = "#999"
PUBG_WHITE = "#FFFFFF"
QFONT = lambda s, b=False: QFont("Microsoft YaHei", s, QFont.Bold if b else QFont.Normal)

# ═══════════ 校准 HUD ═══════════
class CalibrateHUD(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.edit_mode = False
        self.hidden = False
        self.dragging = False
        self.drag_pos = QPoint()
        self.step = 0
        self.base_image = None
        self.result_image = None
        self.shot_count = 10

        self.PC = ProcessClass()
        self.capture = ScreenCapture(self.PC.Monitor)
        self.gun = {
            'gun_name': 'm762', 'scope_name': 'none', 'scope_val': 1.0,
            'posture': 'none', 'posture_val': 1.0,
            '_muzzle': 'none', '_grip': 'none', '_stock': 'none',
            'acc_code': 'A0B0C0',
        }
        self._build_ui()
        self._position()
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._tick)
        self.timer.start(1000)

    def _build_ui(self):
        self.setFixedWidth(400)
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        root.addWidget(self._make_bar())
        root.addWidget(self._make_step_bar())
        main = QVBoxLayout()
        main.setContentsMargins(12, 8, 12, 8)
        main.setSpacing(6)
        main.addWidget(self._make_gun_section())
        main.addWidget(self._make_action_section())
        self.result_box = self._make_result_section()
        main.addWidget(self.result_box)
        self.result_box.setVisible(False)
        root.addLayout(main)
        root.addWidget(self._make_footer())

    def _make_bar(self):
        bar = QFrame()
        bar.setStyleSheet(f"background:{PUBG_BG};border-top-left-radius:6px;border-top-right-radius:6px;border:1px solid {PUBG_BORDER};")
        bar.setFixedHeight(36)
        bl = QHBoxLayout(bar)
        bl.setContentsMargins(12, 0, 12, 0)
        t = QLabel("🎯 弹痕校准")
        t.setStyleSheet(f"color:{PUBG_GOLD};font-size:16px;font-weight:bold;")
        self.status_dot = QLabel("● 就绪")
        self.status_dot.setStyleSheet(f"color:{PUBG_GREEN};font-size:14px;")
        bl.addWidget(t); bl.addStretch(); bl.addWidget(self.status_dot)
        return bar

    def _make_step_bar(self):
        bar = QFrame()
        bar.setStyleSheet(f"background:rgba(10,10,10,0.95);border-bottom:1px solid {PUBG_BORDER};")
        bar.setFixedHeight(28)
        bl = QHBoxLayout(bar); bl.setContentsMargins(8, 4, 8, 4); bl.setSpacing(4)
        self.step_labels = []
        steps = [("①识别", "未识别"), ("②基线", "待截图"), ("③打枪", "待结果"), ("④分析", "待分析")]
        for text, sub in steps:
            v = QVBoxLayout(); v.setContentsMargins(0,0,0,0); v.setSpacing(0)
            l = QLabel(text); l.setStyleSheet(f"color:{PUBG_GRAY};font-size:12px;"); l.setAlignment(Qt.AlignCenter)
            s = QLabel(sub); s.setStyleSheet(f"color:{PUBG_GRAY};font-size:10px;"); s.setAlignment(Qt.AlignCenter)
            v.addWidget(l); v.addWidget(s); bl.addLayout(v, 1)
            self.step_labels.append((l, s))
        return bar

    def _update_steps(self):
        AS = f"color:{PUBG_GOLD};font-size:12px;font-weight:bold;"
        DS = f"color:{PUBG_GREEN};font-size:12px;font-weight:bold;"
        IS = f"color:{PUBG_GRAY};font-size:12px;"
        for i, (l, s) in enumerate(self.step_labels):
            l.setStyleSheet(DS if i < self.step else AS if i == self.step else IS)
        if self.step >= 1: self.step_labels[0][1].setText(f"✅ {self.gun['gun_name']}")
        if self.step >= 1: self.step_labels[1][1].setText("✅ 已拍摄")
        if self.step >= 2: self.step_labels[2][1].setText(f"✅ {self.shot_count}发")
        if self.step >= 3: self.step_labels[3][1].setText("✅ 完成")

    def _make_gun_section(self):
        box = QFrame()
        box.setStyleSheet(f"background:rgba(30,30,30,0.85);border:1px solid rgba(255,255,255,0.1);border-radius:4px;")
        v = QVBoxLayout(box); v.setContentsMargins(8, 4, 8, 4); v.setSpacing(4)
        v.addWidget(QLabel(" 📋 枪械信息"))

        row1 = QHBoxLayout()
        self.combo_gun = self._make_combo()
        self._fill(self.combo_gun, self._guns(), self.gun['gun_name'])
        row1.addWidget(QLabel("枪:")); row1.addWidget(self.combo_gun)
        self.combo_scope = self._make_combo()
        self._fill(self.combo_scope, self._scopes(), self.gun['scope_name'])
        row1.addWidget(QLabel("镜:")); row1.addWidget(self.combo_scope)
        v.addLayout(row1)

        row2 = QHBoxLayout()
        self.combo_muzzle = self._make_combo()
        self._fill(self.combo_muzzle, self._list("Muzzle"), self.gun['_muzzle'])
        row2.addWidget(QLabel("口:")); row2.addWidget(self.combo_muzzle)
        self.combo_grip = self._make_combo()
        self._fill(self.combo_grip, self._list("Grip"), self.gun['_grip'])
        row2.addWidget(QLabel("握:")); row2.addWidget(self.combo_grip)
        self.combo_stock = self._make_combo()
        self._fill(self.combo_stock, self._list("Stock"), self.gun['_stock'])
        row2.addWidget(QLabel("托:")); row2.addWidget(self.combo_stock)
        v.addLayout(row2)

        row3 = QHBoxLayout()
        self.combo_pose = self._make_combo()
        self._fill(self.combo_pose, {"none":"站立","c":"蹲下","z":"趴下"}, self.gun['posture'])
        row3.addWidget(QLabel("姿:")); row3.addWidget(self.combo_pose)
        self.shot_spin = QComboBox()
        for n in range(5, 41): self.shot_spin.addItem(str(n))
        self.shot_spin.setCurrentIndex(5)
        self._style_combo(self.shot_spin)
        self.shot_spin.setFixedWidth(60)
        row3.addWidget(QLabel("发数:")); row3.addWidget(self.shot_spin); row3.addStretch()
        v.addLayout(row3)

        self.acc_label = QLabel(f"配件码: {self.gun['acc_code']}")
        self.acc_label.setStyleSheet(f"color:{PUBG_GOLD};font-size:11px;")
        v.addWidget(self.acc_label)

        self.combo_gun.currentIndexChanged.connect(self._on_gun)
        self.combo_scope.currentIndexChanged.connect(self._on_scope)
        self.combo_muzzle.currentIndexChanged.connect(self._on_acc)
        self.combo_grip.currentIndexChanged.connect(self._on_acc)
        self.combo_stock.currentIndexChanged.connect(self._on_acc)
        self.combo_pose.currentIndexChanged.connect(self._on_pose)
        return box

    def _style_combo(self, c):
        c.setStyleSheet("color:#FFFFFF;background:rgba(40,40,40,0.9);border:1px solid rgba(255,255,255,0.2);border-radius:3px;padding:2px 6px;font-size:12px;")
    def _make_combo(self):
        c = QComboBox(); self._style_combo(c); c.setFixedHeight(26); return c
    def _fill(self, combo, items, cur):
        combo.clear()
        for k, v in items.items(): combo.addItem(v, userData=k)
        idx = combo.findData(cur)
        if idx >= 0: combo.setCurrentIndex(idx)
    def _combo_key(self, c): return c.itemData(c.currentIndex()) or c.currentText().lower()

    def _make_action_section(self):
        box = QFrame()
        box.setStyleSheet(f"background:rgba(30,30,30,0.85);border:1px solid rgba(255,255,255,0.1);border-radius:4px;")
        v = QVBoxLayout(box); v.setContentsMargins(8, 6, 8, 8); v.setSpacing(4)
        hint = QLabel("🖱 F5=拍基线  F6=拍结果  F7=分析  F12=编辑模式  F10=隐藏")
        hint.setStyleSheet(f"color:{PUBG_GRAY};font-size:11px;")
        v.addWidget(hint)
        btn_row = QHBoxLayout(); btn_row.setSpacing(6)
        self.btn_base = self._make_btn("📸 拍基线 [F5]", PUBG_GREEN); self.btn_base.clicked.connect(self.do_capture_base); btn_row.addWidget(self.btn_base)
        self.btn_result = self._make_btn("📸 拍结果 [F6]", PUBG_GOLD); self.btn_result.clicked.connect(self.do_capture_result); btn_row.addWidget(self.btn_result)
        self.btn_analyze = self._make_btn("📊 分析 [F7]", "#4A90D9"); self.btn_analyze.clicked.connect(self.do_analyze); btn_row.addWidget(self.btn_analyze)
        v.addLayout(btn_row)
        mode_row = QHBoxLayout()
        self.btn_edit = self._make_btn("🔒 穿透模式", PUBG_GRAY); self.btn_edit.clicked.connect(self.toggle_mode); mode_row.addWidget(self.btn_edit)
        mode_row.addStretch()
        self.rec_btn = self._make_btn("🔄 重新识别", "#8B5CF6"); self.rec_btn.clicked.connect(self.do_recognize); mode_row.addWidget(self.rec_btn)
        v.addLayout(mode_row)
        return box

    def _make_btn(self, text, color):
        b = QPushButton(text)
        b.setStyleSheet(f"color:#FFFFFF;background:{PUBG_BG};border:1px solid {color};border-radius:4px;padding:5px 12px;font-size:13px;")
        b.setFixedHeight(30)
        return b

    def _make_result_section(self):
        box = QFrame()
        box.setStyleSheet(f"background:rgba(30,30,30,0.85);border:1px solid {PUBG_GREEN};border-radius:4px;")
        v = QVBoxLayout(box); v.setContentsMargins(8, 6, 8, 8); v.setSpacing(4)
        v.addWidget(QLabel("📊 分析结果"))
        self.rlbl = {}
        for k, t in [('shots','检测弹痕'),('avg','平均比值'),('std','标准差'),('suggested','建议系数'),('current','当前系数'),('delta','差值')]:
            r = QHBoxLayout()
            lb = QLabel(f"{t}:"); lb.setStyleSheet(f"color:{PUBG_WHITE};font-size:13px;"); lb.setFixedWidth(110)
            val = QLabel("—"); val.setStyleSheet(f"color:{PUBG_GREEN};font-size:13px;font-weight:bold;")
            r.addWidget(lb); r.addWidget(val); r.addStretch()
            v.addLayout(r); self.rlbl[k] = val
        return box

    def _make_footer(self):
        foot = QFrame()
        foot.setStyleSheet(f"background:{PUBG_BG};border-bottom-left-radius:6px;border-bottom-right-radius:6px;border:1px solid {PUBG_BORDER};")
        foot.setFixedHeight(24)
        fl = QHBoxLayout(foot); fl.setContentsMargins(10,0,10,0)
        self.mode_lb = QLabel("穿透模式 (F12切换)")
        self.mode_lb.setStyleSheet(f"color:{PUBG_GRAY};font-size:11px;")
        fl.addWidget(self.mode_lb); fl.addStretch()
        self.res_lb = QLabel(f"分辨率: {self.PC.Monitor}")
        self.res_lb.setStyleSheet(f"color:{PUBG_GRAY};font-size:11px;")
        fl.addWidget(self.res_lb)
        return foot

    def _position(self):
        s = QApplication.primaryScreen()
        if s:
            g = s.geometry(); x = g.width() - self.width() - 30; y = 30
            self.move(x, y)

    # ── 事件 ──
    def toggle_mode(self):
        self.edit_mode = not self.edit_mode
        if self.edit_mode:
            allow_click(int(self.winId()))
            self.setAttribute(Qt.WA_TransparentForMouseEvents, False)
            self.mode_lb.setText("✏ 编辑模式 (F12切换)"); self.mode_lb.setStyleSheet(f"color:{PUBG_GOLD};font-size:11px;")
        else:
            set_no_activate(int(self.winId()))
            self.setAttribute(Qt.WA_TransparentForMouseEvents, True)
            self.mode_lb.setText("🔒 穿透模式 (F12切换)"); self.mode_lb.setStyleSheet(f"color:{PUBG_GRAY};font-size:11px;")
        self.btn_edit.setText("✏ 编辑模式" if self.edit_mode else "🔒 穿透模式")

    def toggle_visible(self):
        if self.hidden: self.show(); self.hidden = False
        else: self.hide(); self.hidden = True

    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton and self.edit_mode:
            self.dragging = True; self.drag_pos = e.globalPos() - self.frameGeometry().topLeft(); e.accept()
    def mouseMoveEvent(self, e):
        if self.dragging and self.edit_mode: self.move(e.globalPos() - self.drag_pos); e.accept()
    def mouseReleaseEvent(self, e): self.dragging = False

    # ── 数据 ──
    def _acc_code(self):
        m = KEY_DATA['Muzzle'].get(self.gun['_muzzle'], '0')
        g = KEY_DATA['Grip'].get(self.gun['_grip'], '0')
        s = KEY_DATA['Stock'].get(self.gun['_stock'], '0')
        return f"A{m}B{g}C{s}"

    def _load_scope_val(self):
        try:
            c = self.PC.get_config_data('a')
            self.gun['scope_val'] = c.get('sensitivity', {}).get(self.gun['scope_name'], 1.0)
        except Exception: self.gun['scope_val'] = 1.0

    def _load_pose_val(self):
        gp = Path(f"./_internal/GunData/{self.gun['gun_name']}.json")
        if gp.exists():
            with open(gp, encoding='utf-8') as f:
                self.gun['posture_val'] = json.load(f).get(self.gun['posture'], 1)

    def _on_gun(self, i):
        k = self._combo_key(self.combo_gun); self.gun['gun_name'] = k; self._load_pose_val()
    def _on_scope(self, i):
        k = self._combo_key(self.combo_scope); self.gun['scope_name'] = k; self._load_scope_val()
    def _on_acc(self, i):
        sender = self.sender()
        if sender is self.combo_muzzle: self.gun['_muzzle'] = self._combo_key(self.combo_muzzle)
        elif sender is self.combo_grip: self.gun['_grip'] = self._combo_key(self.combo_grip)
        elif sender is self.combo_stock: self.gun['_stock'] = self._combo_key(self.combo_stock)
        self.gun['acc_code'] = self._acc_code()
        self.acc_label.setText(f"配件码: {self.gun['acc_code']}")
    def _on_pose(self, i):
        k = self._combo_key(self.combo_pose); self.gun['posture'] = k; self._load_pose_val()

    def _guns(self):
        return {"m762":"M762","akm":"AKM","m416":"M416","scar-l":"SCAR-L","aug":"AUG",
            "groza":"Groza","dp28":"DP28","m249":"M249","uzi":"UZI","vector":"Vector",
            "mp5k":"MP5K","ump45":"UMP45","mini14":"Mini14","sks":"SKS","qbz":"QBZ",
            "g36c":"G36C","mk12":"MK12","mk14":"MK14","mk47":"MK47","qbu":"QBU",
            "vss":"VSS","mg3":"MG3","js9":"JS9","k2":"K2","p90":"P90","pp19":"PP-19",
            "famas":"FAMAS","ace32":"ACE32"}
    def _scopes(self):
        return {"none":"机瞄","hongdian":"红点","quanxi":"全息","2bei":"2倍","3bei":"3倍",
            "4bei":"4倍","6bei":"6倍","8bei":"8倍","15bei":"15倍","renchengxiang4bei":"热成像4x"}
    def _list(self, k): return dict(KEY_DATA.get(k, {}))

    # ── 操作 ──
    def do_recognize(self):
        self.status_dot.setText("● 识别中..."); self.status_dot.setStyleSheet(f"color:{PUBG_GOLD};font-size:14px;")
        self.PC.recognize_all_guns_info(lambda ev, data: None)
        time.sleep(0.3)
        if HAS_KB: keyboard.press('tab'); keyboard.release('tab')
        else:
            u = ctypes.windll.user32; u.keybd_event(0x09,0,0,0); time.sleep(0.1); u.keybd_event(0x09,0,2,0)
        guns = self.PC.get_guns_info() or {}
        name = guns.get("Name", "")
        if name and name.lower() not in ("none", ""):
            self.gun['gun_name'] = name.lower()
            self.gun['scope_name'] = guns.get("Scope","none").lower()
            self.gun['_muzzle'] = guns.get("Muzzle","none").lower()
            self.gun['_grip'] = guns.get("Grip","none").lower()
            self.gun['_stock'] = guns.get("Stock","none").lower()
            self._fill(self.combo_gun, self._guns(), self.gun['gun_name'])
            self._fill(self.combo_scope, self._scopes(), self.gun['scope_name'])
            self._fill(self.combo_muzzle, self._list("Muzzle"), self.gun['_muzzle'])
            self._fill(self.combo_grip, self._list("Grip"), self.gun['_grip'])
            self._fill(self.combo_stock, self._list("Stock"), self.gun['_stock'])
            self._load_scope_val(); self._load_pose_val()
            self.gun['acc_code'] = self._acc_code()
            self.acc_label.setText(f"配件码: {self.gun['acc_code']}")
            self.step = 1
        self.status_dot.setText("● 就绪"); self.status_dot.setStyleSheet(f"color:{PUBG_GREEN};font-size:14px;")
        self._update_steps()

    def do_capture_base(self):
        self.status_dot.setText("● 截图中...")
        self.base_image = self.capture.grab()
        save_image("base_wall", self.base_image)
        self.step = 1; self._update_steps()
        self.status_dot.setText("● 基线 ✓"); self.status_dot.setStyleSheet(f"color:{PUBG_GREEN};font-size:14px;")

    def do_capture_result(self):
        if self.base_image is None:
            self.status_dot.setText("⚠ 先拍基线!"); self.status_dot.setStyleSheet(f"color:{PUBG_RED};font-size:14px;")
            return
        self.shot_count = int(self.shot_spin.currentText())
        self.result_image = self.capture.grab()
        save_image("result_wall", self.result_image)
        self.step = 2; self._update_steps()
        self.status_dot.setText(f"● {self.shot_count}发 ✓"); self.status_dot.setStyleSheet(f"color:{PUBG_GREEN};font-size:14px;")

    def do_analyze(self):
        if self.base_image is None or self.result_image is None:
            self.status_dot.setText("⚠ 先拍基线和结果!"); self.status_dot.setStyleSheet(f"color:{PUBG_RED};font-size:14px;")
            return
        self.status_dot.setText("● 分析中..."); self.status_dot.setStyleSheet(f"color:{PUBG_GOLD};font-size:14px;")
        holes = detect_holes(self.base_image, self.result_image)
        if not holes:
            self.status_dot.setText("✗ 无弹痕"); self.status_dot.setStyleSheet(f"color:{PUBG_RED};font-size:14px;")
            return
        s = sort_holes(holes); self.step = 3
        vis = self.result_image.copy()
        for hv in s:
            n = hv['shot_num']
            c = (0,0,255) if n<=5 else (0,165,255) if n<=15 else (0,255,0)
            cv2.circle(vis, (hv['x'],hv['y']), 8, c, 2)
            cv2.circle(vis, (hv['x'],hv['y']), 3, c, -1)
            cv2.putText(vis, str(n), (hv['x']+12,hv['y']-8), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255,255,255), 2)
        save_image("bullet_analysis", vis)
        result = compare_with_json(s, self.gun)
        if result:
            self.result_box.setVisible(True)
            self.rlbl['shots'].setText(f"{result['shot_count']} 发")
            self.rlbl['avg'].setText(f"{result['avg_ratio']:.3f}")
            self.rlbl['std'].setText(f"{result['std_ratio']:.3f}")
            self.rlbl['suggested'].setText(f"{result['suggested_scope']}")
            self.rlbl['current'].setText(f"{result['current_scope']}")
            delta = result['suggested_scope'] - result['current_scope']
            sign = "+" if delta >= 0 else ""
            self.rlbl['delta'].setText(f"{sign}{delta:.2f}")
            self.rlbl['delta'].setStyleSheet(f"color:{PUBG_RED if abs(delta)>0.1 else PUBG_GREEN};font-size:13px;font-weight:bold;")
            save_json({**self.gun, **result, 'timestamp': time.strftime('%Y-%m-%d %H:%M:%S')})
            self.status_dot.setText("✅ 分析完成"); self.status_dot.setStyleSheet(f"color:{PUBG_GREEN};font-size:14px;")
        else:
            self.status_dot.setText("⚠ 无理论数据"); self.status_dot.setStyleSheet(f"color:{PUBG_GOLD};font-size:14px;")
        self._update_steps()

    def _tick(self): pass
    def closeEvent(self, e): self.timer.stop(); e.accept()


# ═══════════ RegisterHotKey 快捷键 ═══════════
def setup_hotkeys(hud):
    """
    Win32 RegisterHotKey — 系统级注册热键
    通过无窗口消息循环监听，优先级高于键盘钩子
    全屏游戏也能捕获
    """
    import threading

    user32 = ctypes.windll.User32
    WM_HOTKEY = 0x0312
    MOD_NOREPEAT = 0x4000
    HWND_MESSAGE = -3

    # 创建消息窗口
    hwnd = user32.CreateWindowExW(0, "Static", "CalHotkeys", 0, 0, 0, 0, 0, HWND_MESSAGE, None, None, None)
    if not hwnd:
        print("⚠ 热键消息窗口创建失败")
        return

    VK_F5, VK_F6, VK_F7, VK_F10, VK_F12 = 0x74, 0x75, 0x76, 0x79, 0x7B
    pairs = [
        (1, VK_F5,  hud.do_capture_base,   "F5"),
        (2, VK_F6,  hud.do_capture_result,  "F6"),
        (3, VK_F7,  hud.do_analyze,         "F7"),
        (4, VK_F10, hud.toggle_visible,     "F10"),
        (5, VK_F12, hud.toggle_mode,        "F12"),
    ]

    for hid, vk, func, desc in pairs:
        ok = user32.RegisterHotKey(hwnd, hid, MOD_NOREPEAT, vk)
        if ok:
            print(f"✅ 热键已注册: {desc}")
        else:
            print(f"⚠ 热键注册失败: {desc} (可能被占用)")

    def msg_loop():
        msg = wintypes.MSG()
        while True:
            ret = user32.GetMessageW(ctypes.byref(msg), hwnd, 0, 0)
            if ret <= 0: break
            if msg.message == WM_HOTKEY:
                vk = msg.lParam & 0xFFFF
                for h, k, func, _ in pairs:
                    if k == vk:
                        func()
                        break
            user32.TranslateMessage(ctypes.byref(msg))
            user32.DispatchMessageW(ctypes.byref(msg))

    t = threading.Thread(target=msg_loop, daemon=True)
    t.start()


# ═══════════ 入口 ═══════════
def main():
    app = QApplication(sys.argv)
    try: ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except Exception: pass
    try: QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
    except Exception: pass

    hud = CalibrateHUD()
    hud.show()
    setup_hotkeys(hud)
    hud.toggle_mode()  # 默认穿透
    sys.exit(app.exec_())

if __name__ == '__main__':
    main()
