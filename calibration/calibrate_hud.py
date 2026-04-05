#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
校准 HUD - 游戏内悬浮窗
F12 切换编辑/穿透模式
F5  拍基线（空白墙）
F6  拍结果（打完枪）
F7  开始分析
F10 隐藏/显示 HUD
右键拖拽移动位置
"""

import sys, os, json, time, ctypes
from pathlib import Path
from ctypes import wintypes

from PyQt5.QtCore import Qt, QTimer, QPoint
from PyQt5.QtWidgets import (
    QApplication, QWidget, QLabel, QVBoxLayout, QHBoxLayout,
    QComboBox, QPushButton, QFrame, QSizePolicy
)
from PyQt5.QtGui import QFont

import mss
import numpy as np
import cv2

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from Process import ProcessClass
from fire_data import KEY_DATA

try:
    import keyboard as kb_lib
    HAS_KB = True
except ImportError:
    HAS_KB = False

# Win32
GWL_EXSTYLE = -20
WS_EX_TRANSPARENT = 0x020
WS_EX_LAYERED     = 0x080000
WS_EX_NOACTIVATE  = 0x08000000
u32 = ctypes.windll.User32

def set_no_activate(hwnd):
    try:
        ex = u32.GetWindowLongW(hwnd, GWL_EXSTYLE)
        u32.SetWindowLongW(hwnd, GWL_EXSTYLE,
            ex | WS_EX_TRANSPARENT | WS_EX_LAYERED | WS_EX_NOACTIVATE)
    except Exception: pass

def allow_click(hwnd):
    try:
        ex = u32.GetWindowLongW(hwnd, GWL_EXSTYLE)
        ex &= ~(WS_EX_TRANSPARENT)
        u32.SetWindowLongW(hwnd, GWL_EXSTYLE, ex)
    except Exception: pass

# Screen capture
WALL_ROI = {
    "3840x2160": (0, 0, 1920, 1080),
    "2560x1440": (0, 0, 1920, 1080),
    "1920x1080": (0, 0, 1920, 1080),
}

class ScreenCapture:
    def __init__(self, res="3840x2160"):
        self.res = res
        self.roi = WALL_ROI.get(res, WALL_ROI["3840x2160"])
    def grab(self):
        x, y, w, h = self.roi
        with mss.mss() as sct:
            return np.array(sct.grab({"left": x, "top": y, "width": w, "height": h}))

# Bullet detection
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
        if 4 * np.pi * (area / (peri * peri)) < MIN_CIRC: continue
        M = cv2.moments(cnt)
        if M["m00"] == 0: continue
        cx, cy = int(M["m10"]/M["m00"]), int(M["m01"]/M["m00"])
        mask = np.zeros(bg.shape[:2], dtype=np.uint8)
        cv2.drawContours(mask, [cnt], -1, 255, -1)
        cd = abs(cv2.mean(bg, mask=mask)[0] - cv2.mean(rg, mask=mask)[0])
        if cd < COLOR_TH: continue
        holes.append({'x': cx, 'y': cy, 'area': area})
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
    ratios = [av[i]/theory[i] for i in range(min(len(av), len(theory))) if theory[i] > 0]
    if not ratios: return None
    avg, std = float(np.mean(ratios)), float(np.std(ratios))
    return {
        'avg_ratio': round(avg, 3), 'std_ratio': round(std, 3),
        'suggested_scope': round(gr['scope_val'] * avg, 2),
        'current_scope': gr['scope_val'], 'shot_count': len(av)+1,
    }

def get_save_dir():
    d = Path("./calibration_results"); d.mkdir(exist_ok=True); return d

def save_image(name, img):
    ts = time.strftime('%Y%m%d_%H%M%S')
    p = get_save_dir() / f"{ts}_{name}.png"
    cv2.imwrite(str(p), img); return p

def save_json(data):
    ts = time.strftime('%Y%m%d_%H%M%S')
    p = get_save_dir() / f"{ts}_result.json"
    with open(p, 'w', encoding='utf-8') as f: json.dump(data, f, indent=2, ensure_ascii=False); return p

# Colors
PUBG_BG, PUBG_BORDER = "rgba(18,18,18,0.92)", "rgba(255,186,8,0.6)"
PUBG_GREEN, PUBG_GOLD = "#4AE54A", "#FFBA08"
PUBG_RED, PUBG_GRAY, PUBG_WHITE = "#FF4444", "#999", "#FFFFFF"

# Hotkey constants
WM_HOTKEY = 0x0312
MOD_NOREPEAT = 0x4000
VK_F5, VK_F6, VK_F7, VK_F10, VK_F12 = 0x74, 0x75, 0x76, 0x79, 0x7B

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
        self.cap = ScreenCapture(self.PC.Monitor)
        self.gun = {
            'gun_name': 'm762', 'scope_name': 'none', 'scope_val': 1.0,
            'posture': 'none', 'posture_val': 1.0,
            '_muzzle': 'none', '_grip': 'none', '_stock': 'none',
            'acc_code': 'A0B0C0',
        }
        self._hotkey_pairs = []
        self._build_ui()
        self._position()
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._tick)
        self.timer.start(1000)
        self._register_hotkeys()

    def _build_ui(self):
        self.setFixedWidth(400)
        root = QVBoxLayout(self)
        root.setContentsMargins(0,0,0,0); root.setSpacing(0)
        root.addWidget(self._make_bar())
        root.addWidget(self._make_step_bar())
        m = QVBoxLayout()
        m.setContentsMargins(12,8,12,8); m.setSpacing(6)
        m.addWidget(self._make_gun_section())
        m.addWidget(self._make_action_section())
        self.result_box = self._make_result_section()
        m.addWidget(self.result_box)
        self.result_box.setVisible(False)
        root.addLayout(m)
        root.addWidget(self._make_footer())

    def _make_bar(self):
        bar = QFrame()
        bar.setStyleSheet(f"background:{PUBG_BG};border-top-left-radius:6px;border-top-right-radius:6px;border:1px solid {PUBG_BORDER};")
        bar.setFixedHeight(36)
        bl = QHBoxLayout(bar); bl.setContentsMargins(12,0,12,0)
        bl.addWidget(QLabel("🎯 弹痕校准"))
        bl.addStretch()
        self.status_dot = QLabel("● 就绪")
        self.status_dot.setStyleSheet(f"color:{PUBG_GREEN};font-size:14px;")
        bl.addWidget(self.status_dot)
        return bar

    def _make_step_bar(self):
        bar = QFrame()
        bar.setStyleSheet(f"background:rgba(10,10,10,0.95);border-bottom:1px solid {PUBG_BORDER};")
        bar.setFixedHeight(28)
        bl = QHBoxLayout(bar); bl.setContentsMargins(8,4,8,4); bl.setSpacing(4)
        self.step_labels = []
        for txt, sub in [("①识别","未识别"),("②基线","待截图"),("③打枪","待结果"),("④分析","待分析")]:
            v = QVBoxLayout(); v.setContentsMargins(0,0,0,0); v.setSpacing(0)
            l = QLabel(txt); l.setStyleSheet(f"color:{PUBG_GRAY};font-size:12px;"); l.setAlignment(Qt.AlignCenter)
            s = QLabel(sub); s.setStyleSheet(f"color:{PUBG_GRAY};font-size:10px;"); s.setAlignment(Qt.AlignCenter)
            v.addWidget(l); v.addWidget(s); bl.addLayout(v, 1)
            self.step_labels.append((l,s))
        return bar

    def _update_steps(self):
        AS=f"color:{PUBG_GOLD};font-size:12px;font-weight:bold;"
        DS=f"color:{PUBG_GREEN};font-size:12px;font-weight:bold;"
        IS=f"color:{PUBG_GRAY};font-size:12px;"
        for i,(l,s) in enumerate(self.step_labels):
            l.setStyleSheet(DS if i<self.step else AS if i==self.step else IS)
        if self.step>=1: self.step_labels[0][1].setText(f"✅ {self.gun['gun_name']}")
        if self.step>=1: self.step_labels[1][1].setText("✅ 已拍摄")
        if self.step>=2: self.step_labels[2][1].setText(f"✅ {self.shot_count}发")
        if self.step>=3: self.step_labels[3][1].setText("✅ 完成")

    def _make_gun_section(self):
        box = QFrame()
        box.setStyleSheet(f"background:rgba(30,30,30,0.85);border:1px solid rgba(255,255,255,0.1);border-radius:4px;")
        v = QVBoxLayout(box); v.setContentsMargins(8,4,8,4); v.setSpacing(4)
        v.addWidget(QLabel(" 📋 枪械信息"))
        r1=QHBoxLayout()
        self.c_gun=self._combo(); self._fill(self.c_gun,self._guns(),self.gun['gun_name'])
        r1.addWidget(QLabel("枪:")); r1.addWidget(self.c_gun)
        self.c_scope=self._combo(); self._fill(self.c_scope,self._scopes(),self.gun['scope_name'])
        r1.addWidget(QLabel("镜:")); r1.addWidget(self.c_scope)
        v.addLayout(r1)
        r2=QHBoxLayout()
        self.c_muzz=self._combo(); self._fill(self.c_muzz,self._list("Muzzle"),self.gun['_muzzle'])
        r2.addWidget(QLabel("口:")); r2.addWidget(self.c_muzz)
        self.c_grip=self._combo(); self._fill(self.c_grip,self._list("Grip"),self.gun['_grip'])
        r2.addWidget(QLabel("握:")); r2.addWidget(self.c_grip)
        self.c_stk=self._combo(); self._fill(self.c_stk,self._list("Stock"),self.gun['_stock'])
        r2.addWidget(QLabel("托:")); r2.addWidget(self.c_stk)
        v.addLayout(r2)
        r3=QHBoxLayout()
        self.c_pose=self._combo(); self._fill(self.c_pose,{"none":"站立","c":"蹲下","z":"趴下"},self.gun['posture'])
        r3.addWidget(QLabel("姿:")); r3.addWidget(self.c_pose)
        self.shot_sp=QComboBox(); self._style_cmb(self.shot_sp)
        for n in range(5,41): self.shot_sp.addItem(str(n))
        self.shot_sp.setCurrentIndex(5); self.shot_sp.setFixedWidth(60)
        r3.addWidget(QLabel("发数:")); r3.addWidget(self.shot_sp); r3.addStretch()
        v.addLayout(r3)
        self.acc_lb=QLabel(f"配件码: {self.gun['acc_code']}")
        self.acc_lb.setStyleSheet(f"color:{PUBG_GOLD};font-size:11px;")
        v.addWidget(self.acc_lb)
        self.c_gun.currentIndexChanged.connect(self._on_gun)
        self.c_scope.currentIndexChanged.connect(self._on_scope)
        self.c_muzz.currentIndexChanged.connect(self._on_acc)
        self.c_grip.currentIndexChanged.connect(self._on_acc)
        self.c_stk.currentIndexChanged.connect(self._on_acc)
        self.c_pose.currentIndexChanged.connect(self._on_pose)
        return box

    def _style_cmb(self,c): c.setStyleSheet("color:#FFF;background:rgba(40,40,40,0.9);border:1px solid rgba(255,255,255,0.2);border-radius:3px;padding:2px 6px;font-size:12px;")
    def _combo(self): c=QComboBox(); self._style_cmb(c); c.setFixedHeight(26); return c
    def _fill(self, c, items, cur):
        c.clear()
        for k, v in items.items(): c.addItem(v, userData=k)
        i = c.findData(cur)
        if i >= 0: c.setCurrentIndex(i)
    def _ckey(self,c): return c.itemData(c.currentIndex()) or c.currentText().lower()

    def _make_action_section(self):
        box=QFrame()
        box.setStyleSheet(f"background:rgba(30,30,30,0.85);border:1px solid rgba(255,255,255,0.1);border-radius:4px;")
        v=QVBoxLayout(box); v.setContentsMargins(8,6,8,8); v.setSpacing(4)
        v.addWidget(QLabel("🖱 F5=拍基线  F6=拍结果  F7=分析  F12=编辑  F10=隐藏"))
        br=QHBoxLayout(); br.setSpacing(6)
        self.btn_b=self._btn("📸 拍基线 [F5]",PUBG_GREEN); self.btn_b.clicked.connect(self.do_capture_base); br.addWidget(self.btn_b)
        self.btn_r=self._btn("📸 拍结果 [F6]",PUBG_GOLD); self.btn_r.clicked.connect(self.do_capture_result); br.addWidget(self.btn_r)
        self.btn_a=self._btn("📊 分析 [F7]","#4A90D9"); self.btn_a.clicked.connect(self.do_analyze); br.addWidget(self.btn_a)
        v.addLayout(br)
        mr=QHBoxLayout()
        self.btn_e=self._btn("🔒 穿透模式",PUBG_GRAY); self.btn_e.clicked.connect(self.toggle_mode); mr.addWidget(self.btn_e)
        mr.addStretch()
        self.btn_rc=self._btn("🔄 重新识别","#8B5CF6"); self.btn_rc.clicked.connect(self.do_recognize); mr.addWidget(self.btn_rc)
        v.addLayout(mr)
        return box

    def _btn(self,t,c):
        b=QPushButton(t)
        b.setStyleSheet(f"color:#FFF;background:{PUBG_BG};border:1px solid {c};border-radius:4px;padding:5px 12px;font-size:13px;")
        b.setFixedHeight(30)
        return b

    def _make_result_section(self):
        box=QFrame()
        box.setStyleSheet(f"background:rgba(30,30,30,0.85);border:1px solid {PUBG_GREEN};border-radius:4px;")
        v=QVBoxLayout(box); v.setContentsMargins(8,6,8,8); v.setSpacing(4)
        v.addWidget(QLabel("📊 分析结果"))
        self.rlbl={}
        for k,t in [('shots','检测弹痕'),('avg','平均比值'),('std','标准差'),('suggested','建议系数'),('current','当前系数'),('delta','差值')]:
            r=QHBoxLayout()
            lb=QLabel(f"{t}:"); lb.setStyleSheet(f"color:{PUBG_WHITE};font-size:13px;"); lb.setFixedWidth(110)
            val=QLabel("—"); val.setStyleSheet(f"color:{PUBG_GREEN};font-size:13px;font-weight:bold;")
            r.addWidget(lb); r.addWidget(val); r.addStretch()
            v.addLayout(r); self.rlbl[k]=val
        return box

    def _make_footer(self):
        foot=QFrame()
        foot.setStyleSheet(f"background:{PUBG_BG};border-bottom-left-radius:6px;border-bottom-right-radius:6px;border:1px solid {PUBG_BORDER};")
        foot.setFixedHeight(24)
        fl=QHBoxLayout(foot); fl.setContentsMargins(10,0,10,0)
        self.mode_lb=QLabel("穿透模式 (F12切换)")
        self.mode_lb.setStyleSheet(f"color:{PUBG_GRAY};font-size:11px;")
        fl.addWidget(self.mode_lb); fl.addStretch()
        self.res_lb=QLabel(f"分辨率: {self.PC.Monitor}")
        self.res_lb.setStyleSheet(f"color:{PUBG_GRAY};font-size:11px;")
        fl.addWidget(self.res_lb)
        return foot

    def _position(self):
        s=QApplication.primaryScreen()
        if s:
            g=s.geometry(); self.move(g.width()-self.width()-30, 30)

    # Events
    def toggle_mode(self):
        self.edit_mode=not self.edit_mode
        if self.edit_mode:
            allow_click(int(self.winId())); self.setAttribute(Qt.WA_TransparentForMouseEvents,False)
            self.mode_lb.setText("✏ 编辑模式 (F12切换)"); self.mode_lb.setStyleSheet(f"color:{PUBG_GOLD};font-size:11px;")
        else:
            set_no_activate(int(self.winId())); self.setAttribute(Qt.WA_TransparentForMouseEvents,True)
            self.mode_lb.setText("🔒 穿透模式 (F12切换)"); self.mode_lb.setStyleSheet(f"color:{PUBG_GRAY};font-size:11px;")
        self.btn_e.setText("✏ 编辑模式" if self.edit_mode else "🔒 穿透模式")

    def toggle_visible(self):
        if self.hidden: self.show(); self.hidden=False
        else: self.hide(); self.hidden=True

    def mousePressEvent(self,e):
        if e.button()==Qt.LeftButton and self.edit_mode:
            self.dragging=True; self.drag_pos=e.globalPos()-self.frameGeometry().topLeft(); e.accept()
    def mouseMoveEvent(self,e):
        if self.dragging and self.edit_mode: self.move(e.globalPos()-self.drag_pos); e.accept()
    def mouseReleaseEvent(self,e): self.dragging=False

    def nativeEvent(self, eventType, message):
        if eventType == "windows_generic_MSG":
            msg = ctypes.cast(message, ctypes.POINTER(wintypes.MSG)).contents
            if msg.message == WM_HOTKEY:
                vk = msg.lParam & 0xFFFF
                for _, k, func in self._hotkey_pairs:
                    if k == vk: func(); break
                return True, 0
        return super().nativeEvent(eventType, message)

    def closeEvent(self, e):
        for hid,_,_ in self._hotkey_pairs:
            try: u32.UnregisterHotKey(int(self.winId()), hid)
            except: pass
        self.timer.stop(); e.accept()

    # Data
    def _acc(self):
        m=KEY_DATA['Muzzle'].get(self.gun['_muzzle'],'0')
        g=KEY_DATA['Grip'].get(self.gun['_grip'],'0')
        s=KEY_DATA['Stock'].get(self.gun['_stock'],'0')
        return f"A{m}B{g}C{s}"

    def _load_sv(self):
        try: c=self.PC.get_config_data('a'); self.gun['scope_val']=c.get('sensitivity',{}).get(self.gun['scope_name'],1.0)
        except: self.gun['scope_val']=1.0
    def _load_pv(self):
        gp=Path(f"./_internal/GunData/{self.gun['gun_name']}.json")
        if gp.exists():
            with open(gp,encoding='utf-8') as f: self.gun['posture_val']=json.load(f).get(self.gun['posture'],1)

    def _on_gun(self,i): self.gun['gun_name']=self._ckey(self.c_gun); self._load_pv()
    def _on_scope(self,i): self.gun['scope_name']=self._ckey(self.c_scope); self._load_sv()
    def _on_acc(self,i):
        s=self.sender()
        if s is self.c_muzz: self.gun['_muzzle']=self._ckey(self.c_muzz)
        elif s is self.c_grip: self.gun['_grip']=self._ckey(self.c_grip)
        elif s is self.c_stk: self.gun['_stock']=self._ckey(self.c_stk)
        self.gun['acc_code']=self._acc()
        self.acc_lb.setText(f"配件码: {self.gun['acc_code']}")
    def _on_pose(self,i): self.gun['posture']=self._ckey(self.c_pose); self._load_pv()

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
    def _list(self,k): return dict(KEY_DATA.get(k,{}))

    # Actions
    def do_recognize(self):
        self.status_dot.setText("● 识别中...")
        self.PC.recognize_all_guns_info(lambda ev,data:None)
        time.sleep(0.3)
        if HAS_KB: kb_lib.press('tab'); kb_lib.release('tab')
        else: u32.keybd_event(0x09,0,0,0); time.sleep(0.1); u32.keybd_event(0x09,0,2,0)
        guns=self.PC.get_guns_info() or {}
        name=guns.get("Name","")
        if name and name.lower() not in ("none",""):
            self.gun['gun_name']=name.lower()
            self.gun['scope_name']=guns.get("Scope","none").lower()
            self.gun['_muzzle']=guns.get("Muzzle","none").lower()
            self.gun['_grip']=guns.get("Grip","none").lower()
            self.gun['_stock']=guns.get("Stock","none").lower()
            self._fill(self.c_gun,self._guns(),self.gun['gun_name'])
            self._fill(self.c_scope,self._scopes(),self.gun['scope_name'])
            self._fill(self.c_muzz,self._list("Muzzle"),self.gun['_muzzle'])
            self._fill(self.c_grip,self._list("Grip"),self.gun['_grip'])
            self._fill(self.c_stk,self._list("Stock"),self.gun['_stock'])
            self._load_sv(); self._load_pv()
            self.gun['acc_code']=self._acc()
            self.acc_lb.setText(f"配件码: {self.gun['acc_code']}")
            self.step=1
        self.status_dot.setText("● 就绪")
        self._update_steps()

    def do_capture_base(self):
        self.status_dot.setText("● 截图中...")
        self.base_image=self.cap.grab()
        save_image("base_wall",self.base_image)
        self.step=1; self._update_steps()
        self.status_dot.setText("● 基线 ✓")

    def do_capture_result(self):
        if self.base_image is None:
            self.status_dot.setText("⚠ 先拍基线!")
            return
        self.shot_count=int(self.shot_sp.currentText())
        self.result_image=self.cap.grab()
        save_image("result_wall",self.result_image)
        self.step=2; self._update_steps()
        self.status_dot.setText(f"● {self.shot_count}发 ✓")

    def do_analyze(self):
        if self.base_image is None or self.result_image is None:
            self.status_dot.setText("⚠ 先拍基线和结果!")
            return
        self.status_dot.setText("● 分析中...")
        holes=detect_holes(self.base_image,self.result_image)
        if not holes:
            self.status_dot.setText("✗ 无弹痕"); return
        s=sort_holes(holes); self.step=3
        vis=self.result_image.copy()
        for hv in s:
            n=hv['shot_num']
            c=(0,0,255) if n<=5 else (0,165,255) if n<=15 else (0,255,0)
            cv2.circle(vis,(hv['x'],hv['y']),8,c,2)
            cv2.circle(vis,(hv['x'],hv['y']),3,c,-1)
            cv2.putText(vis,str(n),(hv['x']+12,hv['y']-8),cv2.FONT_HERSHEY_SIMPLEX,0.5,(255,255,255),2)
        save_image("bullet_analysis",vis)
        result=compare_with_json(s,self.gun)
        if result:
            self.result_box.setVisible(True)
            self.rlbl['shots'].setText(f"{result['shot_count']} 发")
            self.rlbl['avg'].setText(f"{result['avg_ratio']:.3f}")
            self.rlbl['std'].setText(f"{result['std_ratio']:.3f}")
            self.rlbl['suggested'].setText(f"{result['suggested_scope']}")
            self.rlbl['current'].setText(f"{result['current_scope']}")
            d=result['suggested_scope']-result['current_scope']
            self.rlbl['delta'].setText(f"{'+' if d>=0 else ''}{d:.2f}")
            self.rlbl['delta'].setStyleSheet(f"color:{PUBG_RED if abs(d)>0.1 else PUBG_GREEN};font-size:13px;font-weight:bold;")
            save_json({**self.gun,**result,'timestamp':time.strftime('%Y-%m-%d %H:%M:%S')})
            self.status_dot.setText("✅ 分析完成")
        else:
            self.status_dot.setText("⚠ 无理论数据")
        self._update_steps()

    def _tick(self): pass

    def _register_hotkeys(self):
        hwnd = int(self.winId())
        self._hotkey_pairs = [
            (1, VK_F5, self.do_capture_base),
            (2, VK_F6, self.do_capture_result),
            (3, VK_F7, self.do_analyze),
            (4, VK_F10, self.toggle_visible),
            (5, VK_F12, self.toggle_mode),
        ]
        descs = {VK_F5:"F5",VK_F6:"F6",VK_F7:"F7",VK_F10:"F10",VK_F12:"F12"}
        for hid, vk, func in self._hotkey_pairs:
            ok = u32.RegisterHotKey(hwnd, hid, MOD_NOREPEAT, vk)
            if ok: print(f"✅ {descs.get(vk,vk)}")
            else: print(f"❌ {descs.get(vk,vk)}")

def main():
    app = QApplication(sys.argv)
    try: ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except: pass
    try: QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
    except: pass
    hud = CalibrateHUD()
    hud.show()
    hud.toggle_mode()
    sys.exit(app.exec_())

if __name__ == '__main__':
    main()
