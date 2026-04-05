# -*- coding: utf-8 -*-
"""游戏内 HUD 悬浮窗 — PUBG 官方风格（4K 27寸优化）
用法：from overlay_hud import GameHUD; hud = GameHUD(PC); hud.show_hud()
"""
import sys, ctypes
from ctypes import wintypes
from PyQt5.QtCore import Qt, QTimer, QThread, pyqtSignal
from PyQt5.QtWidgets import QApplication, QWidget, QLabel, QVBoxLayout, QHBoxLayout
from PyQt5.QtGui import QPainter, QColor, QPen, QBrush
from pynput import keyboard
from pynput.keyboard import Key

# ── DPI 感知（Windows）──
try:
    ctypes.windll.shcore.SetProcessDpiAwareness(2)
except Exception:
    pass


# ── Win32 穿透 ──
GWL_EXSTYLE = -20
WS_EX_TRANSPARENT = 0x00000020
WS_EX_LAYERED     = 0x00080000
WS_EX_NOACTIVATE  = 0x08000000
user32 = ctypes.windll.user32
SetWindowLongW = user32.SetWindowLongW
GetWindowLongW = user32.GetWindowLongW
SetWindowLongW.restype  = wintypes.LONG
SetWindowLongW.argtypes = [wintypes.HWND, ctypes.c_int, wintypes.LONG]
GetWindowLongW.restype  = wintypes.LONG
GetWindowLongW.argtypes = [wintypes.HWND, ctypes.c_int]

def _make_click_through(hwnd):
    """设置窗口鼠标穿透 + 不抢焦点"""
    ex = GetWindowLongW(hwnd, GWL_EXSTYLE)
    SetWindowLongW(hwnd, GWL_EXSTYLE, ex | WS_EX_TRANSPARENT | WS_EX_LAYERED | WS_EX_NOACTIVATE)

# ── 中文映射 ──
GUN_CN = {
    'm416':'M416','akm':'AKM','scar_l':'SCAR-L','m762':'M762','groza':'GROZA',
    'aug':'AUG','m16a4':'M16A4','mk47':'MK47','mk12':'MK12','qbu':'QBU',
    'mini14':'Mini14','sks':'SKS','dp28':'DP-28','m249':'M249','mp5k':'MP5K',
    'vector':'Vector','bizon':'Bizon','ump45':'UMP45','pp19':'PP-19','p90':'P90',
    'mg3':'MG3','pkm':'PKM','micro_uzi':'UZI','tommy_gun':'汤姆逊',
    'mosin_nagant':'莫辛纳甘','kar98k':'Kar98k','m24':'M24','awm':'AWM',
}
ATTACH_CN = {
    'none':'—','eliuquan':'扼流圈','yazuiqiangkou':'鸭嘴枪口',
    'jujiqiangbuchang':'狙击补偿','jujiqiangxiaoyan':'狙击消焰',
    'buqiangbuchang':'步枪补偿','buqiangxiaoyan':'步枪消焰','xiaoyin':'消音器',
    'chongfengqiangxiaoyan':'冲锋消焰','chongfengqiangbuchang':'冲锋补偿',
    'hongdian':'红点','quanxi':'全息','2bei':'2x','3bei':'3x','4bei':'4x',
    '6bei':'6x','8bei':'8x','15bei':'15x','renchengxiang4bei':'热成像4x',
    'banjieshi':'半截式','muzhi':'拇指','zhijiao':'直角','chuizhi':'垂直',
    'zhanshuqiangtuo':'战术枪托','zhongxinqiangtuo':'重型枪托',
    'tuosaiban':'托腮板','zidandai':'子弹袋','zhedieshiqiangtuo':'折叠枪托',
}
POSTURE_CN = {'None':'站立','space':'站立','z':'卧倒','c':'蹲下'}

def _cn(name):
    if not name or str(name).lower()=='none': return '—'
    return ATTACH_CN.get(str(name).lower(), GUN_CN.get(str(name).lower(), str(name)))

# ── Tab 监听 ──
class _TabListener(QThread):
    sig_toggle = pyqtSignal()
    def run(self):
        def on_press(key):
            try: k = key.name if isinstance(key, Key) else key.char
            except AttributeError: return
            if k == 'tab': self.sig_toggle.emit()
        listener = keyboard.Listener(on_press=on_press)
        listener.start(); listener.join()

# ── 圆角面板 ──
class _Panel(QWidget):
    def __init__(self, parent=None, r=5):
        super().__init__(parent); self._r = r
        self.setAttribute(Qt.WA_TransparentForMouseEvents, True)
    def paintEvent(self, e):
        p = QPainter(self); p.setRenderHint(QPainter.Antialiasing)
        p.setBrush(QBrush(QColor(8, 8, 8, 175)))
        p.setPen(QPen(QColor(255,255,255,22), 1))
        p.drawRoundedRect(self.rect().adjusted(1,1,-1,-1), self._r, self._r)
        p.end()

# ── HUD 主类 ──
class GameHUD(QWidget):
    def __init__(self, pc, parent=None):
        super().__init__(parent)
        self._pc = pc
        self._visible = True
        self._drag_pos = None
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setFixedWidth(480)
        self._build_ui()
        self._position_right()
        # Tab 监听
        self._tab_t = _TabListener()
        self._tab_t.sig_toggle.connect(self._on_tab_toggle)
        self._tab_t.start()
        # 定时刷新 250ms
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._refresh)
        self._timer.start(250)

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0,0,0,0); root.setSpacing(5)
        # ── 标题栏 ──
        bar = QWidget()
        bar.setFixedHeight(28)
        bar.setStyleSheet('background:rgba(8,8,8,185);border-top-left-radius:5px;border-top-right-radius:5px;border:1px solid rgba(255,255,255,20);')
        bl = QHBoxLayout(bar); bl.setContentsMargins(10,0,10,0)
        t = QLabel('HUD 信息'); t.setStyleSheet('color:#FFFFFF;font-size:28px;font-weight:bold;')
        self._dot = QLabel('● 就绪'); self._dot.setStyleSheet('color:#4AE54A;font-size:28px;')
        bl.addWidget(t); bl.addStretch(); bl.addWidget(self._dot)
        root.addWidget(bar)
        # ── 枪械面板 ×2 ──
        self._guns = []
        for i in range(2):
            g = self._make_gun_panel(i+1)
            root.addWidget(g); self._guns.append(g)
        # ── 状态面板 ──
        sp = QWidget()
        sp.setStyleSheet('background:rgba(25,25,25,165);border:1px solid rgba(255,255,255,20);border-radius:4px;')
        sl = QVBoxLayout(sp); sl.setContentsMargins(10,6,10,6); sl.setSpacing(2)
        st = QLabel('状态'); st.setStyleSheet('color:#FFFFFF;font-size:28px;font-weight:bold;')
        sl.addWidget(st)
        ssep = QWidget(); ssep.setFixedHeight(1); ssep.setStyleSheet('background:rgba(255,255,255,18);')
        sl.addWidget(ssep)
        self._status = {}
        for key, icon, lbl, default in [
            ('posture','🧍','姿态','站立'),('scope','◎','开镜','关闭'),
            ('view','👁','视角','第三人称'),('fire','🔥','开火','待机'),
        ]:
            r = QHBoxLayout(); r.setSpacing(6)
            ic = QLabel(icon); ic.setStyleSheet('font-size:28px;min-width:20px;max-width:20px;'); ic.setAlignment(Qt.AlignCenter)
            lb = QLabel(lbl); lb.setStyleSheet('color:#FFFFFF;font-size:28px;min-width:30px;'); lb.setFixedWidth(36)
            val = QLabel(default); val.setStyleSheet('color:#FFFFFF;font-size:28px;font-weight:bold;')
            r.addWidget(ic); r.addWidget(lb); r.addWidget(val); r.addStretch()
            sl.addLayout(r); self._status[key] = val
        root.addWidget(sp)
        # ── 灵敏度面板 ──
        ep = QWidget()
        ep.setStyleSheet('background:rgba(25,25,25,165);border:1px solid rgba(255,255,255,20);border-radius:4px;')
        el = QVBoxLayout(ep); el.setContentsMargins(10,6,10,6); el.setSpacing(2)
        et = QLabel('灵敏度'); et.setStyleSheet('color:#FFFFFF;font-size:28px;font-weight:bold;')
        el.addWidget(et)
        esep = QWidget(); esep.setFixedHeight(1); esep.setStyleSheet('background:rgba(255,255,255,18);')
        el.addWidget(esep)
        gw = QWidget(); gl = QHBoxLayout(gw); gl.setContentsMargins(0,2,0,0); gl.setSpacing(4)
        c1 = QVBoxLayout(); c2 = QVBoxLayout()
        self._sens = {}
        sk = [('none','机瞄'),('hongdian','红点'),('quanxi','全息'),('2bei','2x'),('3bei','3x'),('4bei','4x'),('6bei','6x'),('8bei','8x'),('15bei','15x')]
        for i,(k,cn) in enumerate(sk):
            r = QHBoxLayout(); r.setSpacing(4)
            lb = QLabel(cn); lb.setStyleSheet('color:#FFFFFF;font-size:28px;min-width:28px;'); lb.setFixedWidth(32)
            val = QLabel('—'); val.setStyleSheet('color:#FFFFFF;font-size:28px;font-weight:bold;')
            r.addWidget(lb); r.addWidget(val); r.addStretch()
            w = QWidget(); w.setLayout(r); w.setFixedHeight(20)
            self._sens[k] = val
            if i%2==0: c1.addWidget(w)
            else: c2.addWidget(w)
        gl.addLayout(c1); gl.addLayout(c2)
        el.addWidget(gw)
        root.addWidget(ep)
        # ── 底部提示 ──
        hint = QLabel('  右键拖动 | Tab 切换显示')
        hint.setStyleSheet('color:#FFFFFF;font-size:28px;padding:3px 0;background:rgba(8,8,8,185);border-bottom-left-radius:5px;border-bottom-right-radius:5px;border:1px solid rgba(255,255,255,20);border-top:1px solid rgba(255,255,255,20);')
        hint.setAlignment(Qt.AlignCenter)
        root.addWidget(hint)

    def _make_gun_panel(self, slot):
        p = QWidget()
        p.setStyleSheet('background:rgba(25,25,25,165);border:1px solid rgba(255,255,255,20);border-radius:4px;')
        v = QVBoxLayout(p); v.setContentsMargins(10,6,10,6); v.setSpacing(3)
        top = QHBoxLayout()
        tag = QLabel(f'武器{slot}'); tag.setStyleSheet('color:#FFFFFF;font-size:28px;')
        name = QLabel('— 未装备 —'); name.setStyleSheet('color:#FFFFFF;font-size:28px;font-weight:bold;')
        top.addWidget(tag); top.addStretch(); top.addWidget(name)
        v.addLayout(top)
        sep = QWidget(); sep.setFixedHeight(1); sep.setStyleSheet('background:rgba(255,255,255,18);')
        v.addWidget(sep)
        attach = {}
        for k, icon, lbl in [('Scope','◎','瞄具'),('Muzzle','◆','枪口'),('Grip','◆','握把'),('Stock','▲','枪托')]:
            r = QHBoxLayout(); r.setSpacing(6)
            ic = QLabel(icon); ic.setStyleSheet('color:#FFFFFF;font-size:28px;min-width:18px;max-width:18px;' if k=='Scope' else 'color:#FFFFFF;font-size:28px;min-width:18px;max-width:18px;'); ic.setAlignment(Qt.AlignCenter)
            lb = QLabel(lbl); lb.setStyleSheet('color:#FFFFFF;font-size:28px;min-width:28px;'); lb.setFixedWidth(32)
            val = QLabel('—'); val.setStyleSheet('color:#FFFFFF;font-size:28px;font-weight:bold;')
            r.addWidget(ic); r.addWidget(lb); r.addWidget(val); r.addStretch()
            v.addLayout(r); attach[k] = val
        p._name = name; p._attach = attach; p._slot = slot
        return p

    def _position_right(self):
        scr = QApplication.primaryScreen()
        if scr:
            g = scr.geometry()
            x = g.width() - self.width() - 30
            y = (g.height() - 550) // 2
            self.move(x, max(15, y))
        # Win32 鼠标穿透
        _make_click_through(int(self.winId()))

    def _on_tab_toggle(self):
        if self._visible:
            self.hide()
            self._timer.stop()
            self._visible = False
        else:
            self._visible = True
            self.show()
            self._refresh()
            self._timer.start()

    def _refresh(self):
        try:
            pc = self._pc
            results = pc.get_guns_result()
            for i, panel in enumerate(self._guns):
                res = results[i] if i < len(results) else {}
                if res and res.get('Name') and str(res['Name']).lower() != 'none':
                    gn = _cn(res['Name'])
                    if pc.Current_firearms == i+1:
                        panel._name.setText(f'► {gn}')
                        panel._name.setStyleSheet('color:#FFFFFF;font-size:28px;font-weight:bold;')
                    else:
                        panel._name.setText(gn)
                        panel._name.setStyleSheet('color:#FFFFFF;font-size:28px;font-weight:bold;')
                    for k in ('Scope','Muzzle','Grip','Stock'):
                        v = res.get(k, 'None')
                        cn = _cn(v)
                        panel._attach[k].setText(cn)
                        if str(v).lower() != 'none':
                            panel._attach[k].setStyleSheet('color:#4AE54A;font-size:28px;font-weight:bold;')
                        else:
                            panel._attach[k].setStyleSheet('color:#FFFFFF;font-size:28px;font-weight:bold;')
                else:
                    panel._name.setText('— 未装备 —')
                    panel._name.setStyleSheet('color:#FFFFFF;font-size:28px;font-weight:bold;')
                    for v in panel._attach.values():
                        v.setText('—'); v.setStyleSheet('color:#FFFFFF;font-size:28px;font-weight:bold;')
            # 状态
            pk = pc.Current_posture
            pl = POSTURE_CN.get(pk, '站立')
            self._status['posture'].setText(pl)
            self._status['posture'].setStyleSheet('color:#4AE54A;font-size:28px;font-weight:bold;' if pk != 'None' else 'color:#FFFFFF;font-size:28px;font-weight:bold;')
            if pc.StartFire:
                self._status['scope'].setText('已开镜')
                self._status['scope'].setStyleSheet('color:#4AE54A;font-size:28px;font-weight:bold;')
            else:
                self._status['scope'].setText('关闭')
                self._status['scope'].setStyleSheet('color:#FFFFFF;font-size:28px;font-weight:bold;')
            if pc.firstPerson:
                self._status['view'].setText('第一人称')
                self._status['view'].setStyleSheet('color:#FFFFFF;font-size:28px;font-weight:bold;')
            else:
                self._status['view'].setText('第三人称')
                self._status['view'].setStyleSheet('color:#FFFFFF;font-size:28px;font-weight:bold;')
            if getattr(pc, 'mouse_one', False):
                self._status['fire'].setText('开火中')
                self._status['fire'].setStyleSheet('color:#FF4444;font-size:28px;font-weight:bold;')
                self._dot.setText('● 开火中'); self._dot.setStyleSheet('color:#FF4444;font-size:28px;')
            elif pc.StartFire:
                self._status['fire'].setText('瞄准')
                self._status['fire'].setStyleSheet('color:#FFD700;font-size:28px;font-weight:bold;')
                self._dot.setText('● 瞄准'); self._dot.setStyleSheet('color:#FFD700;font-size:28px;')
            else:
                self._status['fire'].setText('待机')
                self._status['fire'].setStyleSheet('color:#FFFFFF;font-size:28px;font-weight:bold;')
                self._dot.setText('● 就绪'); self._dot.setStyleSheet('color:#4AE54A;font-size:28px;')
            # 灵敏度
            sd = getattr(pc, 'ScopeData', None)
            if sd:
                for k, lb in self._sens.items():
                    v = sd.get(k)
                    if v is not None:
                        lb.setText(f'{float(v):.1f}')
                        lb.setStyleSheet('color:#FFFFFF;font-size:28px;font-weight:bold;')
                    else:
                        lb.setText('—'); lb.setStyleSheet('color:#999;font-size:28px;font-weight:bold;')
        except Exception:
            pass

    def show_hud(self):
        self._visible = True; self.show(); self._refresh(); self._timer.start()
    def hide_hud(self):
        self._visible = False; self._timer.stop(); self.hide()
    def toggle(self):
        if self._visible: self.hide_hud()
        else: self.show_hud()
    def stop(self):
        self._timer.stop()
        if hasattr(self, '_tab_t') and self._tab_t.isRunning(): self._tab_t.terminate()
        self.close()


if __name__ == '__main__':
    class MockPC:
        Current_firearms = 1; Current_posture = 'z'; StartFire = True
        RightClick = True; firstPerson = False; mouse_one = False
        ScopeData = {'none':3.4,'hongdian':2.0,'quanxi':2.0,'2bei':6.0,'3bei':8.0,'4bei':11.5,'6bei':5.0,'8bei':5.7,'15bei':10.0}
        _R1 = {'Name':'m416','Scope':'4bei','Muzzle':'xiaoyin','Grip':'chuizhi','Stock':'zhanshuqiangtuo'}
        _R2 = {'Name':'kar98k','Scope':'8bei','Muzzle':'xiaoyin','Grip':'none','Stock':'tuosaiban'}
        def get_guns_result(self): return [self._R1, self._R2]
        def get_guns_info(self): return self._R1 if self.Current_firearms==1 else self._R2
    app = QApplication(sys.argv)
    if hasattr(Qt, 'AA_EnableHighDpiScaling'): QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
    hud = GameHUD(MockPC()); hud.show_hud(); sys.exit(app.exec_())



