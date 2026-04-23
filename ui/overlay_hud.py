    # -*- coding: utf-8 -*-
"""游戏内 HUD 悬浮窗 — 极简模式 + 可拖动 + 分辨率位置预设
用法：from ui.overlay_hud import GameHUD; hud = GameHUD(PC); hud.show_hud()
Tab  → 临时隐藏/恢复（配合背包识别）
F10  → 切换拖动模式（解除/恢复鼠标穿透，方便拖动位置）
配置文件：Config/hud_config.json
"""
import logging
import platform
import sys, os, json, ctypes
from pathlib import Path
from core.paths import res_path

logger = logging.getLogger(__name__)

IS_WINDOWS = platform.system() == "Windows"

if IS_WINDOWS:
    from ctypes import wintypes

from PyQt5.QtCore import Qt, QTimer, QThread, pyqtSignal, QRectF, QPoint
from PyQt5.QtWidgets import QApplication, QWidget
from PyQt5.QtGui import QPainter, QColor, QPen, QBrush, QFont, QFontMetrics, QLinearGradient
from pynput import keyboard
from pynput.keyboard import Key, KeyCode

try:
    if IS_WINDOWS:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
except Exception:
    pass

GWL_EXSTYLE = -20
WS_EX_TRANSPARENT = 0x00000020
WS_EX_LAYERED = 0x00080000
WS_EX_NOACTIVATE = 0x08000000

_HAS_WIN32 = False
if IS_WINDOWS:
    try:
        user32 = ctypes.windll.user32
        _SetWindowLongW = user32.SetWindowLongW
        _GetWindowLongW = user32.GetWindowLongW
        _SetWindowLongW.restype = wintypes.LONG
        _SetWindowLongW.argtypes = [wintypes.HWND, ctypes.c_int, wintypes.LONG]
        _GetWindowLongW.restype = wintypes.LONG
        _GetWindowLongW.argtypes = [wintypes.HWND, ctypes.c_int]
        _HAS_WIN32 = True
    except Exception:
        pass


def _make_click_through(hwnd):
    if not _HAS_WIN32:
        return
    ex = _GetWindowLongW(hwnd, GWL_EXSTYLE)
    _SetWindowLongW(hwnd, GWL_EXSTYLE,
                    ex | WS_EX_TRANSPARENT | WS_EX_LAYERED | WS_EX_NOACTIVATE)


def _remove_click_through(hwnd):
    if not _HAS_WIN32:
        return
    ex = _GetWindowLongW(hwnd, GWL_EXSTYLE)
    _SetWindowLongW(hwnd, GWL_EXSTYLE,
                    ex & ~WS_EX_TRANSPARENT)


# ──────────────────────────────────────────────
# 分辨率位置预设
# ──────────────────────────────────────────────

RESOLUTION_PRESETS = {
    "1920x1080":  {"x": 1600, "y": 20},
    "1728x1080":  {"x": 1410, "y": 20},
    "2560x1440":  {"x": 2240, "y": 25},
    "2560x1080":  {"x": 2240, "y": 20},
    "2560x1600":  {"x": 2240, "y": 25},
    "3440x1440":  {"x": 3120, "y": 25},
    "3840x2160":  {"x": 3500, "y": 30},
}


# ──────────────────────────────────────────────
# 配置加载
# ──────────────────────────────────────────────

_CONFIG_PATH = Path(res_path('Config', 'hud_config.json'))

_DEFAULT_CONFIG = {
    "position": {"x": -1, "y": 20, "anchor": "top-right", "margin_right": 20},
    "font_family": "Microsoft YaHei",
    "font_size": {"main": 10, "hint": 7},
    "colors": {
        "background": [12, 12, 12, 220], "border": [255, 186, 8, 100],
        "gold": [255, 186, 8, 255], "green": [74, 229, 74, 255],
        "red": [255, 68, 68, 255], "yellow": [255, 215, 0, 255],
        "white": [255, 255, 255, 255], "gray": [140, 140, 140, 255],
        "dim": [80, 80, 80, 255],
    },
    "size": [290, 30],
    "opacity": 0.9,
    "refresh_ms": 250,
}


def _load_config():
    if _CONFIG_PATH.is_file():
        try:
            with open(_CONFIG_PATH, encoding='utf-8') as f:
                user_cfg = json.load(f)
            cfg = json.loads(json.dumps(_DEFAULT_CONFIG))
            _deep_merge(cfg, user_cfg)
            cfg['_path'] = str(_CONFIG_PATH)
            return cfg
        except Exception as e:
            logger.warning("HUD 配置加载失败: %s", e)
    return dict(_DEFAULT_CONFIG)


def _deep_merge(base, override):
    for k, v in override.items():
        if isinstance(v, dict) and isinstance(base.get(k), dict):
            _deep_merge(base[k], v)
        else:
            base[k] = v


def _save_config(cfg):
    path = cfg.get('_path', str(_CONFIG_PATH))
    save_cfg = {k: v for k, v in cfg.items() if k != '_path'}
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(save_cfg, f, indent=4, ensure_ascii=False)
    except Exception as e:
        logger.error("HUD 配置保存失败: %s", e)


def _qcolor(rgba):
    if isinstance(rgba, (list, tuple)):
        if len(rgba) >= 4:
            return QColor(rgba[0], rgba[1], rgba[2], rgba[3])
        return QColor(rgba[0], rgba[1], rgba[2])
    return QColor(rgba)


# ──────────────────────────────────────────────
# 翻译表
# ──────────────────────────────────────────────

GUN_CN = {
    'm416': 'M416', 'akm': 'AKM', 'scar_l': 'SCAR-L', 'scar-l': 'SCAR-L',
    'm762': 'M762', 'groza': 'GROZA', 'aug': 'AUG', 'm16a4': 'M16A4',
    'mk47': 'MK47', 'mk12': 'MK12', 'qbu': 'QBU', 'mini14': 'Mini14',
    'sks': 'SKS', 'dp28': 'DP-28', 'm249': 'M249', 'mp5k': 'MP5K',
    'vector': 'Vector', 'bizon': 'Bizon', 'ump45': 'UMP45', 'pp19': 'PP-19',
    'p90': 'P90', 'mg3': 'MG3', 'pkm': 'PKM', 'micro_uzi': 'UZI',
    'uzi': 'UZI', 'tommy_gun': '汤姆逊', 'js9': 'JS9', 'k2': 'K2',
    'ace32': 'ACE32', 'famas': 'FAMAS', 'qbz': 'QBZ', 'g36c': 'G36C',
    'mk14': 'MK14', 'vss': 'VSS', 'mp9': 'MP9',
    'tangmuxunchongfengqiang': '汤姆逊',
    'delagongnuofu': '德拉贡诺夫',
    'zidongzhuangtianbuqiang': '自动装填',
}
SCOPE_SHORT = {
    'none': '机瞄', 'hongdian': '红点', 'quanxi': '全息',
    '2bei': '2x', '3bei': '3x', '4bei': '4x',
    '6bei': '6x', '8bei': '8x', '15bei': '15x',
    'renchengxiang4bei': '热4x',
}
POSTURE_CN = {'None': '站', 'space': '站', 'z': '卧', 'c': '蹲'}


def _gun_cn(name):
    if not name or str(name).lower() == 'none':
        return '—'
    return GUN_CN.get(str(name).lower(), str(name).upper())


def _scope_cn(name):
    if not name or str(name).lower() == 'none':
        return '机瞄'
    return SCOPE_SHORT.get(str(name).lower(), str(name))


class _KeyListener(QThread):
    """监听 Tab（临时隐藏）、F10（切换拖动）"""
    sig_tab_press = pyqtSignal()
    sig_tab_release = pyqtSignal()
    sig_drag_toggle = pyqtSignal()

    def run(self):
        def _key_name(key):
            try:
                return key.name if isinstance(key, Key) else key.char
            except AttributeError:
                return None

        def on_press(key):
            k = _key_name(key)
            if k == 'tab':
                self.sig_tab_press.emit()
            elif k == 'f10':
                self.sig_drag_toggle.emit()

        def on_release(key):
            k = _key_name(key)
            if k == 'tab':
                self.sig_tab_release.emit()

        listener = keyboard.Listener(on_press=on_press, on_release=on_release)
        listener.start()
        listener.join()


class GameHUD(QWidget):
    """极简游戏内 HUD — 可配置/可拖动
    Tab  = 临时隐藏/恢复（背包识别期间不挡视线）
    F10  = 切换拖动模式（拖动改位置后自动保存到配置）
    """

    def __init__(self, pc, parent=None):
        super().__init__(parent)
        self._pc = pc
        self._cfg = _load_config()
        self._visible = True
        self._tab_hidden = False
        self._drag_mode = False
        self._drag_pos = None

        self._load_colors()

        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self._apply_size()
        self._position_from_config()

        self._key_t = _KeyListener()
        self._key_t.sig_tab_press.connect(self._on_tab_press)
        self._key_t.sig_tab_release.connect(self._on_tab_release)
        self._key_t.sig_drag_toggle.connect(self._on_drag_toggle)
        self._key_t.start()

        refresh = max(50, self._cfg.get('refresh_ms', 250))
        self._timer = QTimer(self)
        self._timer.timeout.connect(self.update)
        self._timer.start(refresh)

    def _load_colors(self):
        c = self._cfg.get('colors', {})
        self._COL_BG = _qcolor(c.get('background', [12, 12, 12, 220]))
        self._COL_BORDER = _qcolor(c.get('border', [255, 186, 8, 100]))
        self._COL_GOLD = _qcolor(c.get('gold', [255, 186, 8, 255]))
        self._COL_GREEN = _qcolor(c.get('green', [74, 229, 74, 255]))
        self._COL_RED = _qcolor(c.get('red', [255, 68, 68, 255]))
        self._COL_YELLOW = _qcolor(c.get('yellow', [255, 215, 0, 255]))
        self._COL_WHITE = _qcolor(c.get('white', [255, 255, 255, 255]))
        self._COL_GRAY = _qcolor(c.get('gray', [140, 140, 140, 255]))
        self._COL_DIM = _qcolor(c.get('dim', [80, 80, 80, 255]))

    def _font(self, key='main', weight=QFont.Normal):
        family = self._cfg.get('font_family', 'Microsoft YaHei')
        sizes = self._cfg.get('font_size', {})
        fallback = {'main': 'minimal', 'hint': 'hint'}
        size = sizes.get(key, sizes.get(fallback.get(key, ''), 10))
        if not isinstance(size, (int, float)):
            size = 10
        return QFont(family, int(size), weight)

    def _apply_size(self):
        sz = self._cfg.get('size', [290, 30])
        if isinstance(sz, dict):
            sz = sz.get('minimal', [290, 30])
        self.setFixedSize(sz[0], sz[1])

    def _position_from_config(self):
        pos = self._cfg.get('position', {})
        anchor = pos.get('anchor', 'custom')
        scr = QApplication.primaryScreen()

        if not scr:
            return

        g = scr.geometry()
        hud_w, hud_h = self.width(), self.height()

        if anchor == 'top-right':
            margin_r = pos.get('margin_right', 20)
            x = g.width() - hud_w - margin_r
            y = pos.get('y', 20)
        elif anchor == 'custom':
            x = pos.get('x', -1)
            y = pos.get('y', 20)
            if x < 0:
                margin_r = pos.get('margin_right', 20)
                x = g.width() - hud_w - margin_r
        else:
            margin_r = pos.get('margin_right', 20)
            x = g.width() - hud_w - margin_r
            y = pos.get('y', 20)

        self.move(x, y)
        if not self._drag_mode:
            _make_click_through(int(self.winId()))

    def apply_resolution_preset(self, resolution: str):
        """根据分辨率应用预设位置。"""
        preset = RESOLUTION_PRESETS.get(resolution)
        if preset:
            self._cfg.setdefault('position', {})['x'] = preset['x']
            self._cfg['position']['y'] = preset['y']
            self._cfg['position']['anchor'] = 'custom'
            _save_config(self._cfg)
            self._position_from_config()

    def _save_position(self):
        p = self.pos()
        self._cfg.setdefault('position', {})['x'] = p.x()
        self._cfg['position']['y'] = p.y()
        self._cfg['position']['anchor'] = 'custom'
        _save_config(self._cfg)

    # ── 按键处理 ──

    def _on_tab_press(self):
        if self._visible:
            self._tab_hidden = True
            self.hide()
            self._timer.stop()

    def _on_tab_release(self):
        if self._tab_hidden:
            self._tab_hidden = False
            if self._visible:
                self.show()
                self._timer.start()

    def _on_drag_toggle(self):
        self._drag_mode = not self._drag_mode
        hwnd = int(self.winId())
        if self._drag_mode:
            _remove_click_through(hwnd)
            self.setCursor(Qt.SizeAllCursor)
        else:
            _make_click_through(hwnd)
            self.setCursor(Qt.ArrowCursor)
            self._save_position()
        self.update()

    # ── 拖动 ──

    def mousePressEvent(self, event):
        if self._drag_mode and event.button() == Qt.LeftButton:
            self._drag_pos = event.globalPos() - self.frameGeometry().topLeft()
            event.accept()

    def mouseMoveEvent(self, event):
        if self._drag_mode and self._drag_pos is not None:
            self.move(event.globalPos() - self._drag_pos)
            event.accept()

    def mouseReleaseEvent(self, event):
        if self._drag_mode:
            self._drag_pos = None
            self._save_position()
            event.accept()

    # ── 获取枪械信息 ──

    def _get_current_gun(self):
        pc = self._pc
        results = pc.get_guns_result()
        slot = pc.Current_firearms
        if slot == 1 and results[0]:
            return results[0], 1
        elif slot == 2 and results[1]:
            return results[1], 2
        elif results[0]:
            return results[0], 1
        elif results[1]:
            return results[1], 2
        return None, None

    # ── 绘制 ──

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        self._paint_minimal(p)
        p.end()

    def _paint_minimal(self, p):
        pc = self._pc
        w, h = self.width(), self.height()

        grad = QLinearGradient(0, 0, w, 0)
        grad.setColorAt(0, QColor(self._COL_BG.red(), self._COL_BG.green(), self._COL_BG.blue(), 210))
        grad.setColorAt(1, QColor(self._COL_BG.red(), self._COL_BG.green(), self._COL_BG.blue(), 160))
        p.setBrush(QBrush(grad))
        border_pen = QPen(self._COL_BORDER, 1)
        if self._drag_mode:
            border_pen = QPen(QColor(255, 100, 100), 2)
        p.setPen(border_pen)
        p.drawRoundedRect(QRectF(0.5, 0.5, w - 1, h - 1), 4, 4)

        gun, slot = self._get_current_gun()
        gun_name = _gun_cn(gun.get('Name')) if gun else '—'
        scope = _scope_cn(gun.get('Scope')) if gun else '—'
        posture = POSTURE_CN.get(pc.Current_posture, '站')

        font = self._font('main', QFont.Bold)
        p.setFont(font)
        fm = QFontMetrics(font)

        x = 10
        p.setPen(QPen(self._COL_GOLD))
        p.drawText(x, 20, gun_name)
        x += fm.horizontalAdvance(gun_name) + 6

        p.setPen(QPen(self._COL_DIM))
        p.drawText(x, 20, '|')
        x += 12

        p.setPen(QPen(self._COL_GREEN if scope != '机瞄' else self._COL_GRAY))
        p.drawText(x, 20, scope)
        x += fm.horizontalAdvance(scope) + 6

        p.setPen(QPen(self._COL_DIM))
        p.drawText(x, 20, '|')
        x += 12

        p.setPen(QPen(self._COL_WHITE))
        p.drawText(x, 20, posture)
        x += fm.horizontalAdvance(posture) + 8

        dot_color = self._COL_RED if getattr(pc, 'mouse_one', False) else \
            self._COL_YELLOW if pc.StartFire else self._COL_GREEN
        p.setBrush(QBrush(dot_color))
        p.setPen(Qt.NoPen)
        p.drawEllipse(x, 10, 10, 10)

        hint_font = self._font('hint')
        p.setFont(hint_font)
        p.setPen(QPen(self._COL_DIM))
        hint = '拖动中(F10锁定)' if self._drag_mode else 'F10拖动'
        p.drawText(w - QFontMetrics(hint_font).horizontalAdvance(hint) - 8, 20, hint)

    # ── Public API ──
    def show_hud(self):
        self._visible = True
        self._tab_hidden = False
        self._apply_size()
        self._position_from_config()
        self.show()
        self._timer.start()

    def hide_hud(self):
        self._visible = False
        self._tab_hidden = False
        self._timer.stop()
        self.hide()

    def toggle(self):
        if self._visible:
            self.hide_hud()
        else:
            self.show_hud()

    def reload_config(self):
        self._cfg = _load_config()
        self._load_colors()
        self._apply_size()
        self._position_from_config()
        self.update()

    def stop(self):
        self._timer.stop()
        if hasattr(self, '_key_t') and self._key_t.isRunning():
            self._key_t.terminate()
        self.close()


if __name__ == '__main__':
    class MockPC:
        Current_firearms = 1
        Current_posture = 'z'
        StartFire = True
        RightClick = True
        firstPerson = False
        mouse_one = False
        ScopeData = {'none': 3.4, 'hongdian': 2.0, 'quanxi': 2.0, '2bei': 6.0,
                     '3bei': 8.0, '4bei': 11.5, '6bei': 5.0, '8bei': 5.7, '15bei': 10.0}
        _R1 = {'Name': 'm416', 'Scope': '4bei', 'Muzzle': 'xiaoyin',
               'Grip': 'chuizhi', 'Stock': 'zhanshuqiangtuo'}
        _R2 = {'Name': 'kar98k', 'Scope': '8bei', 'Muzzle': 'xiaoyin',
               'Grip': 'none', 'Stock': 'tuosaiban'}

        def get_guns_result(self):
            return [self._R1, self._R2]

        def get_guns_info(self):
            return self._R1 if self.Current_firearms == 1 else self._R2

    app = QApplication(sys.argv)
    if hasattr(Qt, 'AA_EnableHighDpiScaling'):
        QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
    hud = GameHUD(MockPC())
    hud.show_hud()
    sys.exit(app.exec_())
