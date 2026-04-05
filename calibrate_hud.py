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
user32 = ctypes.windll.user32

def set_no_activate(hwnd):
    try:
        ex = user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
        user32.SetWindowLongW(hwnd, GWL_EXSTYLE,
            ex | WS_EX_TRANSPARENT | WS_EX_LAYERED | WS_EX_NOACTIVATE)
    except Exception:
        pass

def allow_click(hwnd):
    """允许鼠标点击（编辑模式）"""
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
        if not (20 < area < 800): continue
        peri = cv2.arcLength(cnt, True)
        if peri == 0: continue
        circ = 4 * np.pi * (area / (peri * peri))
        if circ < 0.25: continue
        M = cv2.moments(cnt)
        if M["m00"] == 0: continue
        cx, cy = int(M["m10"]/M["m00"]), int(M["m01"]/M["m00"])
        mask = np.zeros(bg.shape[:2], dtype=np.uint8)
        cv2.drawContours(mask, [cnt], -1, 255, -1)
        cd = abs(cv2.mean(bg, mask=mask)[0] - cv2.mean(rg, mask=mask)[0])
        if cd < 15: continue
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

    avg = np.mean(ratios)
    std = np.std(ratios)
    suggested = round(gr['scope_val'] * avg, 2)

    return {
        'avg_ratio': round(float(avg), 3),
        'std_ratio': round(float(std), 3),
        'suggested_scope': suggested,
        'current_scope': gr['scope_val'],
        'shot_count': len(av)+1,
    }

# ═══════════ 保存目录 ═══════════

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

# ═══════════ 样式常量 ═══════════

PUBG_BG = "rgba(18, 18, 18, 0.92)"
PUBG_BORDER = "rgba(255, 186, 8, 0.6)"
PUBG_GREEN = "#4AE54A"
PUBG_GOLD = "#FFBA08"
PUBG_RED = "#FF4444"
PUBG_GRAY = "#999"
PUBG_WHITE = "#FFFFFF"

def qfont(size, bold=False):
    """返回 Qt 字体"""
    f = QFont("Microsoft YaHei", size)
    f.setBold(bold)
    return f

# ═══════════ 校准 HUD 主窗口 ═══════════

class CalibrateHUD(QWidget):
    """游戏内校准悬浮窗"""

    # ── 构造 ──────────────────────────

    def __init__(self):
        super().__init__()
        # 无窗口装饰 + 置顶 + 工具窗口
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground)

        # 状态
        self.edit_mode = False      # True=可编辑 False=穿透
        self.hidden = False
        self.dragging = False
        self.drag_pos = QPoint()

        # 校准状态
        self.step = 0               # 0=未开始 1=已识别 2=已基线 3=已结果 4=已分析
        self.base_image = None
        self.result_image = None
        self.shot_count = 10

        # PC 实例
        self.PC = ProcessClass()
        self.capture = ScreenCapture(self.PC.Monitor)

        # 枪械信息字典
        self.gun = {
            'gun_name': 'm762',
            'scope_name': 'none',
            'scope_val': 1.0,
            'posture': 'none',
            'posture_val': 1.0,
            '_muzzle': 'none',
            '_grip': 'none',
            '_stock': 'none',
            'acc_code': 'A0B0C0',
        }

        self._build_ui()
        self._position()
        self._load_scope_data()

        # 刷新
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._tick)
        self.timer.start(1000)

    # ── UI 构建 ────────────────────────

    def _build_ui(self):
        self.setFixedWidth(400)
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # 标题栏
        bar = self._make_bar()
        root.addWidget(bar)

        # 步骤指示
        self.step_bar = self._make_step_bar()
        root.addWidget(self.step_bar)

        # 内容区
        self.content = QVBoxLayout()
        self.content.setContentsMargins(12, 8, 12, 8)
        self.content.setSpacing(6)

        # ── 枪械信息区 ──
        gun_box = self._make_gun_section()
        self.content.addWidget(gun_box)

        # ── 操作区（快捷键提示 + 按钮） ──
        act_box = self._make_action_section()
        self.content.addWidget(act_box)

        # ── 结果区 ──
        self.result_box = self._make_result_section()
        self.content.addWidget(self.result_box)
        self.result_box.setVisible(False)

        root.addLayout(self.content)

        # 底部状态条
        foot = self._make_footer()
        root.addWidget(foot)

    def _make_bar(self):
        """标题栏"""
        bar = QFrame()
        bar.setStyleSheet(
            f"background:{PUBG_BG};"
            f"border-top-left-radius:6px;border-top-right-radius:6px;"
            f"border:1px solid {PUBG_BORDER};"
        )
        bar.setFixedHeight(36)
        bl = QHBoxLayout(bar)
        bl.setContentsMargins(12, 0, 12, 0)

        t = QLabel("🎯 弹痕校准")
        t.setStyleSheet(f"color:{PUBG_GOLD};font-size:16px;font-weight:bold;")
        self.status_dot = QLabel("● 就绪")
        self.status_dot.setStyleSheet(f"color:{PUBG_GREEN};font-size:14px;")

        bl.addWidget(t)
        bl.addStretch()
        bl.addWidget(self.status_dot)
        return bar

    def _make_step_bar(self):
        """步骤指示条"""
        bar = QFrame()
        bar.setStyleSheet(f"background:rgba(10,10,10,0.95);border-bottom:1px solid {PUBG_BORDER};")
        bar.setFixedHeight(28)
        bl = QHBoxLayout(bar)
        bl.setContentsMargins(8, 4, 8, 4)
        bl.setSpacing(4)

        self.step_labels = []
        steps = [
            ("①识别", f"color:{PUBG_GOLD};font-size:12px;font-weight:bold;", "未识别"),
            ("②基线", f"color:{PUBG_GRAY};font-size:12px;", "待截图"),
            ("③打枪", f"color:{PUBG_GRAY};font-size:12px;", "待结果"),
            ("④分析", f"color:{PUBG_GRAY};font-size:12px;", "待分析"),
        ]
        for text, style, sub in steps:
            v = QVBoxLayout()
            v.setContentsMargins(0, 0, 0, 0)
            v.setSpacing(0)
            l = QLabel(text)
            l.setStyleSheet(style)
            l.setAlignment(Qt.AlignCenter)
            s = QLabel(sub)
            s.setStyleSheet(f"color:{PUBG_GRAY};font-size:10px;")
            s.setAlignment(Qt.AlignCenter)
            v.addWidget(l)
            v.addWidget(s)
            bl.addLayout(v, 1)
            self.step_labels.append((l, s))

        return bar

    def _update_steps(self):
        active_style = f"color:{PUBG_GOLD};font-size:12px;font-weight:bold;"
        done_style   = f"color:{PUBG_GREEN};font-size:12px;font-weight:bold;"
        idle_style   = f"color:{PUBG_GRAY};font-size:12px;"

        for i, (l, s) in enumerate(self.step_labels):
            if i < self.step:
                l.setStyleSheet(done_style)
            elif i == self.step:
                l.setStyleSheet(active_style)
            else:
                l.setStyleSheet(idle_style)

        if self.step >= 0: self.step_labels[0][1].setText(f"✅ {self.gun['gun_name']}")
        if self.step >= 1: self.step_labels[1][1].setText("✅ 已拍摄")
        if self.step >= 2: self.step_labels[2][1].setText(f"✅ {self.shot_count}发")
        if self.step >= 3: self.step_labels[3][1].setText("✅ 完成")

    def _make_gun_section(self):
        """枪械信息区域"""
        box = QFrame()
        box.setStyleSheet(f"background:rgba(30,30,30,0.85);border:1px solid rgba(255,255,255,0.1);border-radius:4px;")
        box.setContentsMargins(0, 6, 0, 6)
        v = QVBoxLayout(box)
        v.setContentsMargins(8, 4, 8, 4)
        v.setSpacing(4)

        title = QLabel(" 📋 枪械信息")
        title.setStyleSheet(f"color:{PUBG_WHITE};font-size:14px;font-weight:bold;")
        v.addWidget(title)

        # 一行两列
        row1 = QHBoxLayout()
        self.combo_gun = self._make_combo("枪械")
        self._fill_combo(self.combo_gun, self._gun_list(), self.gun['gun_name'])
        row1.addWidget(QLabel("枪:"))
        row1.addWidget(self.combo_gun)

        self.combo_scope = self._make_combo("倍镜")
        self._fill_combo(self.combo_scope, self._scope_list(), self.gun['scope_name'])
        row1.addWidget(QLabel("镜:"))
        row1.addWidget(self.combo_scope)
        v.addLayout(row1)

        row2 = QHBoxLayout()
        self.combo_muzzle = self._make_combo("枪口")
        self._fill_combo(self.combo_muzzle, self._muzzle_list(), self.gun['_muzzle'])
        row2.addWidget(QLabel("口:"))
        row2.addWidget(self.combo_muzzle)

        self.combo_grip = self._make_combo("握把")
        self._fill_combo(self.combo_grip, self._grip_list(), self.gun['_grip'])
        row2.addWidget(QLabel("握:"))
        row2.addWidget(self.combo_grip)

        self.combo_stock = self._make_combo("枪托")
        self._fill_combo(self.combo_stock, self._stock_list(), self.gun['_stock'])
        row2.addWidget(QLabel("托:"))
        row2.addWidget(self.combo_stock)
        v.addLayout(row2)

        row3 = QHBoxLayout()
        self.combo_posture = self._make_combo("姿势")
        self._fill_combo(self.combo_posture, {"none":"站立","c":"蹲下","z":"趴下"}, self.gun['posture'])
        row3.addWidget(QLabel("姿:"))
        row3.addWidget(self.combo_posture)

        self.shot_spin = QComboBox()
        for n in range(5, 41): self.shot_spin.addItem(str(n))
        self.shot_spin.setCurrentIndex(5)  # 默认 10 发（index=5）
        self.shot_spin.setStyleSheet("color:#FFFFFF;background:rgba(40,40,40,0.9);border:1px solid rgba(255,255,255,0.2);border-radius:3px;padding:2px 6px;font-size:13px;")
        self.shot_spin.setFixedWidth(60)
        row3.addWidget(QLabel("发数:"))
        row3.addWidget(self.shot_spin)
        row3.addStretch()
        v.addLayout(row3)

        # 配件码显示
        self.acc_label = QLabel(f"配件码: A0B0C0")
        self.acc_label.setStyleSheet(f"color:{PUBG_GOLD};font-size:11px;")
        v.addWidget(self.acc_label)

        # 连接信号
        self.combo_gun.currentTextChanged.connect(self._on_gun_change)
        self.combo_scope.currentTextChanged.connect(self._on_scope_change)
        self.combo_muzzle.currentTextChanged.connect(self._on_acc_change)
        self.combo_grip.currentTextChanged.connect(self._on_acc_change)
        self.combo_stock.currentTextChanged.connect(self._on_acc_change)
        self.combo_posture.currentTextChanged.connect(self._on_posture_change)

        return box

    def _make_combo(self, label_text):
        c = QComboBox()
        c.setStyleSheet(
            "color:#FFFFFF;background:rgba(40,40,40,0.9);"
            "border:1px solid rgba(255,255,255,0.2);border-radius:3px;"
            "padding:2px 6px;font-size:12px;"
        )
        c.setFixedHeight(26)
        return c

    def _fill_combo(self, combo, items, current_key):
        combo.clear()
        for key, label in items.items():
            combo.addItem(label, userData=key)
        idx = combo.findData(current_key)
        if idx >= 0: combo.setCurrentIndex(idx)

    def _make_action_section(self):
        """操作按钮区"""
        box = QFrame()
        box.setStyleSheet(f"background:rgba(30,30,30,0.85);border:1px solid rgba(255,255,255,0.1);border-radius:4px;")
        v = QVBoxLayout(box)
        v.setContentsMargins(8, 6, 8, 8)
        v.setSpacing(4)

        # 提示
        hint = QLabel("🖱 F5=拍基线  F6=拍结果  F7=分析  F12=编辑模式  F10=隐藏")
        hint.setStyleSheet(f"color:{PUBG_GRAY};font-size:11px;")
        v.addWidget(hint)

        # 按钮行
        btn_row = QHBoxLayout()
        btn_row.setSpacing(6)

        self.btn_base = self._make_btn("📸 拍基线 [F5]", PUBG_GREEN)
        self.btn_base.clicked.connect(self.do_capture_base)
        btn_row.addWidget(self.btn_base)

        self.btn_result = self._make_btn("📸 拍结果 [F6]", PUBG_GOLD)
        self.btn_result.clicked.connect(self.do_capture_result)
        btn_row.addWidget(self.btn_result)

        self.btn_analyze = self._make_btn("📊 分析 [F7]", "#4A90D9")
        self.btn_analyze.clicked.connect(self.do_analyze)
        btn_row.addWidget(self.btn_analyze)

        v.addLayout(btn_row)

        # 模式切换
        mode_row = QHBoxLayout()
        self.btn_edit = self._make_btn("✏ 穿透模式", PUBG_GRAY)
        self.btn_edit.clicked.connect(self.toggle_mode)
        mode_row.addWidget(self.btn_edit)
        mode_row.addStretch()
        self.recognize_btn = self._make_btn("🔄 重新识别", "#8B5CF6")
        self.recognize_btn.clicked.connect(self.do_recognize)
        mode_row.addWidget(self.recognize_btn)
        v.addLayout(mode_row)

        return box

    def _make_btn(self, text, color):
        b = QPushButton(text)
        b.setStyleSheet(
            f"color:#FFFFFF;background:{PUBG_BG};"
            f"border:1px solid {color};border-radius:4px;"
            f"padding:5px 12px;font-size:13px;"
        )
        b.setFixedHeight(30)
        b.setMinimumWidth(0)
        b.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        return b

    def _make_result_section(self):
        """结果展示区"""
        box = QFrame()
        box.setStyleSheet(f"background:rgba(30,30,30,0.85);border:1px solid {PUBG_GREEN};border-radius:4px;")
        v = QVBoxLayout(box)
        v.setContentsMargins(8, 6, 8, 8)
        v.setSpacing(4)

        title = QLabel("📊 分析结果")
        title.setStyleSheet(f"color:{PUBG_GOLD};font-size:14px;font-weight:bold;")
        v.addWidget(title)

        self.result_labels = {}
        for key, label in [
            ('shots', '检测弹痕'),
            ('avg', '平均比值'),
            ('std', '标准差'),
            ('suggested', f'建议倍镜系数'),
            ('current', f'当前倍镜系数'),
            ('delta', '差值'),
        ]:
            row = QHBoxLayout()
            lb = QLabel(f"{label}:")
            lb.setStyleSheet(f"color:{PUBG_WHITE};font-size:13px;")
            lb.setFixedWidth(110)
            val = QLabel("—")
            val.setStyleSheet(f"color:{PUBG_GREEN};font-size:13px;font-weight:bold;")
            row.addWidget(lb)
            row.addWidget(val)
            row.addStretch()
            v.addLayout(row)
            self.result_labels[key] = val

        return box

    def _make_footer(self):
        foot = QFrame()
        foot.setStyleSheet(
            f"background:{PUBG_BG};"
            f"border-bottom-left-radius:6px;border-bottom-right-radius:6px;"
            f"border:1px solid {PUBG_BORDER};"
        )
        foot.setFixedHeight(24)
        fl = QHBoxLayout(foot)
        fl.setContentsMargins(10, 0, 10, 0)
        self.mode_label = QLabel("穿透模式 (F12切换)")
        self.mode_label.setStyleSheet(f"color:{PUBG_GRAY};font-size:11px;")
        fl.addWidget(self.mode_label)
        fl.addStretch()
        self.res_label = QLabel(f"分辨率: {self.PC.Monitor}")
        self.res_label.setStyleSheet(f"color:{PUBG_GRAY};font-size:11px;")
        fl.addWidget(self.res_label)
        return foot

    def _position(self):
        # 右上角
        screen = QApplication.primaryScreen()
        if screen:
            g = screen.geometry()
            x = g.width() - self.width() - 30
            y = 30
            self.move(x, y)

    # ── 模式切换 ──────────────────────

    def toggle_mode(self):
        self.edit_mode = not self.edit_mode
        if self.edit_mode:
            set_no_activate(int(self.winId()))
            self.mode_label.setText("✏ 编辑模式 (F12切换)")
            self.mode_label.setStyleSheet(f"color:{PUBG_GOLD};font-size:11px;")
            # 启用内部控件点击
            allow_click(int(self.winId()))
            self.setAttribute(Qt.WA_TransparentForMouseEvents, False)
        else:
            set_no_activate(int(self.winId()))
            self.mode_label.setText("🔒 穿透模式 (F12切换)")
            self.mode_label.setStyleSheet(f"color:{PUBG_GRAY};font-size:11px;")
            self.setAttribute(Qt.WA_TransparentForMouseEvents, True)

        # 更新按钮
        label = "✏ 编辑模式" if self.edit_mode else "🔒 穿透模式"
        self.btn_edit.setText(label)

    def toggle_visible(self):
        if self.hidden:
            self.show()
            self.hidden = False
        else:
            self.hide()
            self.hidden = True

    # ── 鼠标拖拽 ─────────────────────

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton and self.edit_mode:
            self.dragging = True
            self.drag_pos = event.globalPos() - self.frameGeometry().topLeft()
            event.accept()

    def mouseMoveEvent(self, event):
        if self.dragging and self.edit_mode:
            self.move(event.globalPos() - self.drag_pos)
            event.accept()

    def mouseReleaseEvent(self, event):
        self.dragging = False

    # ── 数据加载 ─────────────────────

    def _load_scope_data(self):
        try:
            config = self.PC.get_config_data('a')
            sd = config.get('sensitivity', {})
            for k, v in sd.items():
                if k in KEY_DATA:  # 只保留有效的键
                    pass
        except Exception:
            pass

    def _acc_code(self):
        m = KEY_DATA['Muzzle'].get(self.gun['_muzzle'], '0')
        g = KEY_DATA['Grip'].get(self.gun['_grip'], '0')
        s = KEY_DATA['Stock'].get(self.gun['_stock'], '0')
        return f"A{m}B{g}C{s}"

    def _on_gun_change(self, display):
        idx = self.combo_gun.currentIndex()
        key = self.combo_gun.itemData(idx) or display.lower()
        self.gun['gun_name'] = key
        self._load_posture_val()

    def _on_scope_change(self, display):
        idx = self.combo_scope.currentIndex()
        key = self.combo_scope.itemData(idx) or display.lower()
        self.gun['scope_name'] = key
        try:
            config = self.PC.get_config_data('a')
            self.gun['scope_val'] = config.get('sensitivity', {}).get(key, 1.0)
        except Exception:
            self.gun['scope_val'] = 1.0

    def _on_acc_change(self, display):
        sender = self.sender()
        if sender is self.combo_muzzle:
            idx = self.combo_muzzle.currentIndex()
            self.gun['_muzzle'] = self.combo_muzzle.itemData(idx) or display.lower()
        elif sender is self.combo_grip:
            idx = self.combo_grip.currentIndex()
            self.gun['_grip'] = self.combo_grip.itemData(idx) or display.lower()
        elif sender is self.combo_stock:
            idx = self.combo_stock.currentIndex()
            self.gun['_stock'] = self.combo_stock.itemData(idx) or display.lower()
        self.gun['acc_code'] = self._acc_code()
        self.acc_label.setText(f"配件码: {self.gun['acc_code']}")

    def _on_posture_change(self, display):
        idx = self.combo_posture.currentIndex()
        key = self.combo_posture.itemData(idx) or display.lower()
        self.gun['posture'] = key
        self._load_posture_val()

    def _load_posture_val(self):
        gp = Path(f"./_internal/GunData/{self.gun['gun_name']}.json")
        if gp.exists():
            with open(gp, encoding='utf-8') as f:
                self.gun['posture_val'] = json.load(f).get(self.gun['posture'], 1)

    # ── 选项列表 ────────────────────

    def _gun_list(self):
        return {"m762":"M762","akm":"AKM","m416":"M416","scar-l":"SCAR-L",
                "aug":"AUG","groza":"Groza","dp28":"DP28","m249":"M249",
                "uzi":"UZI","vector":"Vector","mp5k":"MP5K",
                "ump45":"UMP45","mini14":"Mini14","sks":"SKS","qbz":"QBZ",
                "g36c":"G36C","mk12":"MK12","mk14":"MK14","mk47":"MK47",
                "qbu":"QBU","vss":"VSS","mg3":"MG3","js9":"JS9","k2":"K2",
                "p90":"P90","pp19":"PP-19","famas":"FAMAS","ace32":"ACE32"}

    def _scope_list(self):
        return {"none":"机瞄","hongdian":"红点","quanxi":"全息",
                "2bei":"2倍","3bei":"3倍","4bei":"4倍",
                "6bei":"6倍","8bei":"8倍","15bei":"15倍","renchengxiang4bei":"热成像4x"}

    def _muzzle_list(self):
        return dict(KEY_DATA.get("Muzzle", {}))

    def _grip_list(self):
        return dict(KEY_DATA.get("Grip", {}))

    def _stock_list(self):
        return dict(KEY_DATA.get("Stock", {}))

    # ── 操作 ─────────────────────────

    def do_recognize(self):
        """识别枪械"""
        self.status_dot.setText("● 识别中...")
        self.status_dot.setStyleSheet(f"color:{PUBG_GOLD};font-size:14px;")

        self.PC.recognize_all_guns_info(lambda ev, data: None)
        time.sleep(0.3)
        # 关背包
        if HAS_KB:
            keyboard.press('tab'); keyboard.release('tab')
        else:
            import ctypes; u = ctypes.windll.user32
            u.keybd_event(0x09,0,0,0); time.sleep(0.1); u.keybd_event(0x09,0,2,0)

        guns = self.PC.get_guns_info() or {}
        name = guns.get("Name", "")
        if name and name.lower() not in ("none", ""):
            self.gun['gun_name'] = name.lower()
            self.gun['scope_name'] = guns.get("Scope","none").lower()
            self.gun['_muzzle'] = guns.get("Muzzle","none").lower()
            self.gun['_grip'] = guns.get("Grip","none").lower()
            self.gun['_stock'] = guns.get("Stock","none").lower()

            # 刷新UI
            self._fill_combo(self.combo_gun, self._gun_list(), self.gun['gun_name'])
            self._fill_combo(self.combo_scope, self._scope_list(), self.gun['scope_name'])
            self._fill_combo(self.combo_muzzle, self._muzzle_list(), self.gun['_muzzle'])
            self._fill_combo(self.combo_grip, self._grip_list(), self.gun['_grip'])
            self._fill_combo(self.combo_stock, self._stock_list(), self.gun['_stock'])

            try:
                config = self.PC.get_config_data('a')
                self.gun['scope_val'] = config.get('sensitivity',{}).get(self.gun['scope_name'],1.0)
            except Exception:
                self.gun['scope_val'] = 1.0
            self._load_posture_val()
            self.gun['acc_code'] = self._acc_code()
            self.acc_label.setText(f"配件码: {self.gun['acc_code']}")
            self.step = 1

        self.status_dot.setText("● 就绪")
        self.status_dot.setStyleSheet(f"color:{PUBG_GREEN};font-size:14px;")
        self._update_steps()

    def do_capture_base(self):
        """拍基线"""
        self.status_dot.setText("● 截图...")
        self.status_dot.setStyleSheet(f"color:{PUBG_GOLD};font-size:14px;")
        self.base_image = self.capture.grab()
        save_image("base_wall", self.base_image)
        self.step = 1
        self._update_steps()
        self.status_dot.setText("● 基线已拍")
        self.status_dot.setStyleSheet(f"color:{PUBG_GREEN};font-size:14px;")

    def do_capture_result(self):
        """拍结果"""
        if self.base_image is None:
            QMessageBox.warning(self, "提示", "先拍基线（F5）！")
            return
        self.shot_count = int(self.shot_spin.currentText())
        self.result_image = self.capture.grab()
        save_image("result_wall", self.result_image)
        self.step = 2
        self._update_steps()
        self.status_dot.setText(f"● 结果已拍 {self.shot_count}发")
        self.status_dot.setStyleSheet(f"color:{PUBG_GREEN};font-size:14px;")

    def do_analyze(self):
        """分析弹痕"""
        if self.base_image is None or self.result_image is None:
            QMessageBox.warning(self, "提示", "需要先拍基线和结果！")
            return

        self.status_dot.setText("● 分析中...")
        self.status_dot.setStyleSheet(f"color:{PUBG_GOLD};font-size:14px;")

        holes = detect_holes(self.base_image, self.result_image)
        if not holes:
            QMessageBox.warning(self, "结果", "未检测到弹痕！")
            self.status_dot.setText("● 无弹痕")
            self.status_dot.setStyleSheet(f"color:{PUBG_RED};font-size:14px;")
            return

        s = sort_holes(holes)
        self.step = 3

        # 可视化
        vis = self.result_image.copy()
        for hv in s:
            n = hv['shot_num']
            color = (0,0,255) if n<=5 else (0,165,255) if n<=15 else (0,255,0)
            cv2.circle(vis, (hv['x'],hv['y']), 8, color, 2)
            cv2.circle(vis, (hv['x'],hv['y']), 3, color, -1)
            cv2.putText(vis, str(n), (hv['x']+12,hv['y']-8),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255,255,255), 2)
            if n > 1:
                prev = [h for h in s if h['shot_num']<n]
                if prev:
                    p = max(prev, key=lambda h: h['shot_num'])
                    cv2.line(vis, (p['x'],p['y']), (hv['x'],hv['y']),
                            color if n<=15 else (0,255,0), 2)

        save_image("bullet_analysis", vis)

        # 对比
        result = compare_with_json(s, self.gun)
        if result:
            self.result_box.setVisible(True)
            self.result_labels['shots'].setText(f"{result['shot_count']} 发")
            self.result_labels['avg'].setText(f"{result['avg_ratio']:.3f}")
            self.result_labels['std'].setText(f"{result['std_ratio']:.3f}")
            self.result_labels['suggested'].setText(f"{result['suggested_scope']}")
            self.result_labels['current'].setText(f"{result['current_scope']}")
            delta = result['suggested_scope'] - result['current_scope']
            sign = "+" if delta >= 0 else ""
            self.result_labels['delta'].setText(f"{sign}{delta:.2f}")
            self.result_labels['delta'].setStyleSheet(
                f"color:{PUBG_RED};font-size:13px;font-weight:bold;" if abs(delta)>0.1
                else f"color:{PUBG_GREEN};font-size:13px;font-weight:bold;"
            )
            # 保存JSON
            full = {**self.gun, **result, 'shot_count_hud': result['shot_count'],
                    'timestamp': time.strftime('%Y-%m-%d %H:%M:%S')}
            save_json(full)
            self.status_dot.setText("● 分析完成")
        else:
            self.status_dot.setText("● 无理论数据")
            self.status_dot.setStyleSheet(f"color:{PUBG_GOLD};font-size:14px;")

        self._update_steps()
        self.status_dot.setStyleSheet(f"color:{PUBG_GREEN};font-size:14px;")

    def _tick(self):
        pass

    def closeEvent(self, event):
        self.timer.stop()
        event.accept()


# ── 快捷键监听 ──

def setup_hotkeys(hud: CalibrateHUD):
    """设置全局快捷键"""
    import threading

    def hotkey_thread():
        if not HAS_KB:
            return

        def on_press(key):
            try:
                if key.name is None: return
                name = key.name.lower()
                if name == 'f5':
                    hud.do_capture_base()
                elif name == 'f6':
                    hud.do_capture_result()
                elif name == 'f7':
                    hud.do_analyze()
                elif name == 'f10':
                    hud.toggle_visible()
                elif name == 'f12':
                    hud.toggle_mode()
            except Exception:
                pass

        keyboard.on_press(on_press)
        keyboard.wait()

    t = threading.Thread(target=hotkey_thread, daemon=True)
    t.start()


# ═══════════ 主入口 ═══════════

def main():
    app = QApplication(sys.argv)

    # DPI
    try: ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except Exception: pass

    try:
        from PyQt5.QtCore import Qt
        QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
    except Exception:
        pass

    hud = CalibrateHUD()
    hud.show()
    setup_hotkeys(hud)

    # 初始穿透模式
    hud.toggle_mode()

    sys.exit(app.exec_())


if __name__ == '__main__':
    main()
