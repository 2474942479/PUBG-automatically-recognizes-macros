    # -*- coding: utf-8 -*-
"""游戏内 HUD 悬浮窗 — 三档可切换 + 可配置 + 可拖动
用法：from ui.overlay_hud import GameHUD; hud = GameHUD(PC); hud.show_hud()
Tab  → 临时隐藏/恢复（配合背包识别）
F9   → 循环切换显示模式：极简 → 紧凑 → 完整
F10  → 切换拖动模式（解除/恢复鼠标穿透，方便拖动位置）
配置文件：Config/hud_config.json
"""
import sys, os, json, ctypes
from pathlib import Path
from ctypes import wintypes
from PyQt5.QtCore import Qt, QTimer, QThread, pyqtSignal, QRectF, QPoint
from PyQt5.QtWidgets import QApplication, QWidget
from PyQt5.QtGui import QPainter, QColor, QPen, QBrush, QFont, QFontMetrics, QLinearGradient
from pynput import keyboard
from pynput.keyboard import Key, KeyCode

try:
    ctypes.windll.shcore.SetProcessDpiAwareness(2)
except Exception:
    pass

GWL_EXSTYLE = -20
WS_EX_TRANSPARENT = 0x00000020
WS_EX_LAYERED = 0x00080000
WS_EX_NOACTIVATE = 0x08000000

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
    _HAS_WIN32 = False


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
# 配置加载
# ──────────────────────────────────────────────

_CONFIG_PATH = Path(__file__).resolve().parent.parent / 'Config' / 'hud_config.json'
_CONFIG_CANDIDATES = [
    _CONFIG_PATH,
    Path('./Config/hud_config.json'),
    Path('../Config/hud_config.json'),
]

_DEFAULT_CONFIG = {
    "position": {"x": -1, "y": 20, "anchor": "top-right", "margin_right": 20},
    "default_mode": "minimal",
    "font_family": "Microsoft YaHei",
    "font_size": {"minimal": 10, "compact_header": 9, "compact_body": 9,
                  "full_header": 9, "full_body": 9, "hint": 7},
    "colors": {
        "background": [12, 12, 12, 220], "border": [255, 186, 8, 100],
        "gold": [255, 186, 8, 255], "green": [74, 229, 74, 255],
        "red": [255, 68, 68, 255], "yellow": [255, 215, 0, 255],
        "white": [255, 255, 255, 255], "gray": [140, 140, 140, 255],
        "dim": [80, 80, 80, 255],
    },
    "size": {"minimal": [290, 30], "compact": [260, 140], "full": [300, 260]},
    "opacity": 0.9,
    "refresh_ms": 250,
    "hotkey_mode_switch": "F9",
}


def _load_config():
    for p in _CONFIG_CANDIDATES:
        if p.is_file():
            try:
                with open(p, encoding='utf-8') as f:
                    user_cfg = json.load(f)
                cfg = json.loads(json.dumps(_DEFAULT_CONFIG))
                _deep_merge(cfg, user_cfg)
                cfg['_path'] = str(p.resolve())
                return cfg
            except Exception:
                pass
    return dict(_DEFAULT_CONFIG)


def _deep_merge(base, override):
    for k, v in override.items():
        if isinstance(v, dict) and isinstance(base.get(k), dict):
            _deep_merge(base[k], v)
        else:
            base[k] = v


def _save_config(cfg):
    path = cfg.get('_path')
    if not path:
        for p in _CONFIG_CANDIDATES:
            if p.parent.is_dir():
                path = str(p.resolve())
                break
    if not path:
        return
    save_cfg = {k: v for k, v in cfg.items() if k != '_path'}
    try:
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(save_cfg, f, indent=4, ensure_ascii=False)
    except Exception:
        pass


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
    'mk14': 'MK14', 'vss': 'VSS',
}
SCOPE_SHORT = {
    'none': '机瞄', 'hongdian': '红点', 'quanxi': '全息',
    '2bei': '2x', '3bei': '3x', '4bei': '4x',
    '6bei': '6x', '8bei': '8x', '15bei': '15x',
    'renchengxiang4bei': '热4x',
}
ATTACH_CN = {
    'none': '—', 'eliuquan': '扼流圈', 'yazuiqiangkou': '鸭嘴',
    'jujiqiangbuchang': '狙补偿', 'jujiqiangxiaoyan': '狙消焰',
    'buqiangbuchang': '步补偿', 'buqiangxiaoyan': '步消焰', 'xiaoyin': '消音',
    'chongfengqiangxiaoyan': '冲消焰', 'chongfengqiangbuchang': '冲补偿',
    'banjieshi': '半截', 'muzhi': '拇指', 'zhijiao': '直角', 'chuizhi': '垂直',
    'zhanshuqiangtuo': '战术托', 'zhongxinqiangtuo': '重型托',
    'tuosaiban': '托腮板', 'zidandai': '子弹袋', 'zhedieshiqiangtuo': '折叠托',
}
POSTURE_CN = {'None': '站', 'space': '站', 'z': '卧', 'c': '蹲'}
POSTURE_FULL = {'None': '站立', 'space': '站立', 'z': '卧倒', 'c': '蹲下'}


def _gun_cn(name):
    if not name or str(name).lower() == 'none':
        return '—'
    return GUN_CN.get(str(name).lower(), str(name).upper())


def _scope_cn(name):
    if not name or str(name).lower() == 'none':
        return '机瞄'
    return SCOPE_SHORT.get(str(name).lower(), str(name))


def _attach_cn(name):
    if not name or str(name).lower() == 'none':
        return '—'
    return ATTACH_CN.get(str(name).lower(), str(name))


MODE_MINIMAL, MODE_COMPACT, MODE_FULL, MODE_BAR = 0, 1, 2, 3
_MODE_NAMES = {MODE_MINIMAL: 'minimal', MODE_COMPACT: 'compact', MODE_FULL: 'full', MODE_BAR: 'bar'}


class _KeyListener(QThread):
    """监听 Tab（临时隐藏）、F9（切换模式）、F10（切换拖动）"""
    sig_tab_press = pyqtSignal()
    sig_tab_release = pyqtSignal()
    sig_mode_switch = pyqtSignal()
    sig_drag_toggle = pyqtSignal()

    def __init__(self, mode_key='F9'):
        super().__init__()
        self._mode_key_name = mode_key.lower()

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
            elif k and k.lower() == self._mode_key_name:
                self.sig_mode_switch.emit()
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
    """四档游戏内 HUD — 可配置/可拖动
    Tab  = 临时隐藏/恢复（背包识别期间不挡视线）
    F9   = 极简 → 紧凑 → 横向白色 → 完整 → 极简
    F10  = 切换拖动模式（拖动改位置后自动保存到配置）
    """

    def __init__(self, pc, parent=None):
        super().__init__(parent)
        self._pc = pc
        self._cfg = _load_config()
        self._mode = {'minimal': MODE_MINIMAL, 'compact': MODE_COMPACT,
                      'full': MODE_FULL, 'bar': MODE_BAR}.get(self._cfg.get('default_mode', 'minimal'), MODE_MINIMAL)
        self._visible = True
        self._tab_hidden = False
        self._drag_mode = False
        self._drag_pos = None

        self._load_colors()

        # 使用Dialog而非Tool，确保鼠标事件正常（特别是在4K高分屏上）
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Dialog)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating, True)  # 显示时不激活，避免抢焦点
        self._apply_size()
        self._position_from_config()

        mode_key = self._cfg.get('hotkey_mode_switch', 'F9')
        self._key_t = _KeyListener(mode_key)
        self._key_t.sig_tab_press.connect(self._on_tab_press)
        self._key_t.sig_tab_release.connect(self._on_tab_release)
        self._key_t.sig_mode_switch.connect(self._on_mode_switch)
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

    def _font(self, key, weight=QFont.Normal):
        family = self._cfg.get('font_family', 'Microsoft YaHei')
        sizes = self._cfg.get('font_size', {})
        size = sizes.get(key, 9)
        return QFont(family, size, weight)

    def _apply_size(self):
        sizes = self._cfg.get('size', {})
        mode_name = _MODE_NAMES.get(self._mode, 'minimal')
        sz = sizes.get(mode_name, [290, 30])
        self.setFixedSize(sz[0], sz[1])

    def _position_from_config(self):
        pos = self._cfg.get('position', {})
        anchor = pos.get('anchor', 'custom')
        scr = QApplication.primaryScreen()
        
        if not scr:
            return
            
        g = scr.geometry()
        hud_w, hud_h = self.width(), self.height()
        
        # 根据锚点计算位置
        if anchor == 'bottom_left':
            margin_left = pos.get('margin_left', 20)
            margin_bottom = pos.get('margin_bottom', 30)
            x = margin_left
            y = g.height() - hud_h - margin_bottom
        elif anchor == 'top-right':
            margin_r = pos.get('margin_right', 20)
            x = g.width() - hud_w - margin_r
            y = pos.get('y', 20)
        elif anchor == 'custom':
            # 自定义绝对位置（拖动后保存的位置）
            x = pos.get('x', -1)
            y = pos.get('y', 20)
            if x < 0:
                margin_r = pos.get('margin_right', 20)
                x = g.width() - hud_w - margin_r
            # 确保坐标不超出屏幕范围（适配不同分辨率）
            x = max(0, min(x, g.width() - hud_w))
            y = max(0, min(y, g.height() - hud_h))
        else:
            # 默认右上角
            margin_r = pos.get('margin_right', 20)
            x = g.width() - hud_w - margin_r
            y = pos.get('y', 20)
        
        self.move(x, y)
        if not self._drag_mode:
            _make_click_through(int(self.winId()))

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

    def _on_mode_switch(self):
        if not self._visible:
            return
        self._mode = (self._mode + 1) % 4
        self._apply_size()
        
        # 根据锚点重新定位
        pos = self._cfg.get('position', {})
        anchor = pos.get('anchor', 'custom')
        scr = QApplication.primaryScreen()
        if scr:
            g = scr.geometry()
            hud_w, hud_h = self.width(), self.height()
            
            if anchor == 'bottom_left':
                margin_left = pos.get('margin_left', 20)
                margin_bottom = pos.get('margin_bottom', 30)
                x = margin_left
                y = g.height() - hud_h - margin_bottom
                self.move(x, y)
            elif anchor == 'top-right':
                margin_r = pos.get('margin_right', 20)
                self.move(g.width() - hud_w - margin_r, self.y())
        
        self.update()

    def _on_drag_toggle(self):
        self._drag_mode = not self._drag_mode
        hwnd = int(self.winId())
        if self._drag_mode:
            # 退出点击穿透模式，允许接收鼠标事件
            _remove_click_through(hwnd)
            self.setCursor(Qt.SizeAllCursor)
            # 进入拖动模式时，确保窗口可见且可交互
            self.raise_()
            self.activateWindow()
            # 强制更新窗口属性
            self.setWindowOpacity(self._cfg.get('opacity', 0.9))
        else:
            # 恢复点击穿透
            _make_click_through(hwnd)
            self.setCursor(Qt.ArrowCursor)
            self._save_position()
        self.update()

    # ── 拖动 ──

    def mousePressEvent(self, event):
        if self._drag_mode and event.button() == Qt.LeftButton:
            self._drag_pos = event.globalPos() - self.frameGeometry().topLeft()
            event.accept()
        else:
            super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._drag_mode and self._drag_pos is not None:
            new_pos = event.globalPos() - self._drag_pos
            # 限制窗口不拖出屏幕
            scr = QApplication.primaryScreen()
            if scr:
                g = scr.geometry()
                new_x = max(0, min(new_pos.x(), g.width() - self.width()))
                new_y = max(0, min(new_pos.y(), g.height() - self.height()))
                self.move(new_x, new_y)
            else:
                self.move(new_pos)
            event.accept()
        else:
            super().mouseMoveEvent(event)

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
        if self._mode == MODE_MINIMAL:
            self._paint_minimal(p)
        elif self._mode == MODE_COMPACT:
            self._paint_compact(p)
        elif self._mode == MODE_BAR:
            self._paint_bar(p)
        else:
            self._paint_full(p)
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

        font = self._font('minimal', QFont.Bold)
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
        mode_key = self._cfg.get('hotkey_mode_switch', 'F9')
        hint = f'拖动中' if self._drag_mode else f'{mode_key}切换'
        p.drawText(w - QFontMetrics(hint_font).horizontalAdvance(hint) - 8, 20, hint)

    def _paint_bar(self, p):
        """横向白色模式 - 显示枪械名字、姿势和配件信息，白色字体，无背景无边框"""
        pc = self._pc
        w, h = self.width(), self.height()

        # 不绘制背景，直接绘制文字

        gun, slot = self._get_current_gun()
        posture = POSTURE_CN.get(pc.Current_posture, '站')
        
        # 获取枪械信息
        gun_name = _gun_cn(gun.get('Name')) if gun else '—'
        scope = _scope_cn(gun.get('Scope')) if gun else '—'
        muzzle = _attach_cn(gun.get('Muzzle')) if gun else '—'
        grip = _attach_cn(gun.get('Grip')) if gun else '—'
        stock = _attach_cn(gun.get('Stock')) if gun else '—'

        font = self._font('minimal', QFont.Bold)
        p.setFont(font)
        fm = QFontMetrics(font)

        x = 10
        # 枪械名字 - 金色
        p.setPen(QPen(self._COL_GOLD))
        p.drawText(x, 20, gun_name)
        x += fm.horizontalAdvance(gun_name) + 8
        
        # 分隔符
        p.setPen(QPen(QColor(255, 255, 255, 100)))
        p.drawText(x, 20, '|')
        x += 12

        # 姿势 - 白色
        p.setPen(QPen(self._COL_WHITE))
        p.drawText(x, 20, posture)
        x += fm.horizontalAdvance(posture) + 8

        # 分隔符
        p.setPen(QPen(QColor(255, 255, 255, 100)))
        p.drawText(x, 20, '|')
        x += 12

        # 瞄具
        scope_color = self._COL_GREEN if (gun and gun.get('Scope', 'none').lower() != 'none') else self._COL_WHITE
        p.setPen(QPen(scope_color))
        p.drawText(x, 20, scope)
        x += fm.horizontalAdvance(scope) + 6

        # 枪口
        if gun and gun.get('Muzzle', 'none').lower() != 'none':
            p.setPen(QPen(QColor(255, 255, 255, 100)))
            p.drawText(x, 20, '|')
            x += 12
            p.setPen(QPen(self._COL_WHITE))
            p.drawText(x, 20, muzzle)
            x += fm.horizontalAdvance(muzzle) + 6

        # 握把
        if gun and gun.get('Grip', 'none').lower() != 'none':
            p.setPen(QPen(QColor(255, 255, 255, 100)))
            p.drawText(x, 20, '|')
            x += 12
            p.setPen(QPen(self._COL_WHITE))
            p.drawText(x, 20, grip)
            x += fm.horizontalAdvance(grip) + 6

        # 枪托
        if gun and gun.get('Stock', 'none').lower() != 'none':
            p.setPen(QPen(QColor(255, 255, 255, 100)))
            p.drawText(x, 20, '|')
            x += 12
            p.setPen(QPen(self._COL_WHITE))
            p.drawText(x, 20, stock)
            x += fm.horizontalAdvance(stock) + 6

        # 开镜状态
        p.setPen(QPen(QColor(255, 255, 255, 100)))
        p.drawText(x, 20, '|')
        x += 12
        p.setPen(QPen(self._COL_GREEN if pc.StartFire else self._COL_WHITE))
        p.drawText(x, 20, '开镜' if pc.StartFire else '未开镜')

        # 提示文字
        hint_font = self._font('hint')
        p.setFont(hint_font)
        p.setPen(QPen(QColor(255, 255, 255, 120)))
        mode_key = self._cfg.get('hotkey_mode_switch', 'F9')
        hint = f'拖动中' if self._drag_mode else f'{mode_key}切换'
        p.drawText(w - QFontMetrics(hint_font).horizontalAdvance(hint) - 8, 20, hint)

    def _paint_compact(self, p):
        pc = self._pc
        w, h = self.width(), self.height()

        p.setBrush(QBrush(self._COL_BG))
        border_pen = QPen(self._COL_BORDER, 1)
        if self._drag_mode:
            border_pen = QPen(QColor(255, 100, 100), 2)
        p.setPen(border_pen)
        p.drawRoundedRect(QRectF(0.5, 0.5, w - 1, h - 1), 6, 6)

        gun, slot = self._get_current_gun()

        hf = self._font('compact_header', QFont.Bold)
        bf = self._font('compact_body')
        sf = self._font('hint')

        p.setFont(hf)
        p.setPen(QPen(self._COL_GOLD))
        gun_name = _gun_cn(gun.get('Name')) if gun else '—'
        slot_text = f'武器{slot}' if slot else ''
        p.drawText(10, 18, f'{slot_text}  {gun_name}')

        p.setPen(QPen(QColor(255, 255, 255, 30)))
        p.drawLine(10, 24, w - 10, 24)

        y = 40
        p.setFont(bf)
        if gun:
            for label, val, has in [
                ('瞄具', _scope_cn(gun.get('Scope')), gun.get('Scope', 'none').lower() != 'none'),
                ('枪口', _attach_cn(gun.get('Muzzle')), gun.get('Muzzle', 'none').lower() != 'none'),
                ('握把', _attach_cn(gun.get('Grip')), gun.get('Grip', 'none').lower() != 'none'),
                ('枪托', _attach_cn(gun.get('Stock')), gun.get('Stock', 'none').lower() != 'none'),
            ]:
                p.setPen(QPen(self._COL_GRAY))
                p.drawText(14, y, label)
                p.setPen(QPen(self._COL_GREEN if has else self._COL_WHITE))
                p.drawText(56, y, val)
                y += 18
        else:
            p.setPen(QPen(self._COL_GRAY))
            p.drawText(14, y, '未装备武器')
            y += 18

        y += 2
        p.setPen(QPen(QColor(255, 255, 255, 30)))
        p.drawLine(10, y, w - 10, y)
        y += 14

        posture = POSTURE_CN.get(pc.Current_posture, '站')
        p.setFont(bf)
        p.setPen(QPen(self._COL_GRAY))
        p.drawText(14, y, posture)

        p.setPen(QPen(self._COL_GREEN if pc.StartFire else self._COL_GRAY))
        p.drawText(50, y, '开镜' if pc.StartFire else '—')

        if getattr(pc, 'mouse_one', False):
            p.setPen(QPen(self._COL_RED))
            p.drawText(100, y, '开火')

        p.setFont(sf)
        p.setPen(QPen(self._COL_DIM))
        mode_key = self._cfg.get('hotkey_mode_switch', 'F9')
        hint = f'拖动中(F10锁定)' if self._drag_mode else f'{mode_key}切换'
        p.drawText(w - QFontMetrics(sf).horizontalAdvance(hint) - 8, h - 6, hint)

    def _paint_full(self, p):
        pc = self._pc
        w, h = self.width(), self.height()

        p.setBrush(QBrush(self._COL_BG))
        border_pen = QPen(self._COL_BORDER, 1)
        if self._drag_mode:
            border_pen = QPen(QColor(255, 100, 100), 2)
        p.setPen(border_pen)
        p.drawRoundedRect(QRectF(0.5, 0.5, w - 1, h - 1), 6, 6)

        hf = self._font('full_header', QFont.Bold)
        bf = self._font('full_body')
        sf = self._font('hint')

        p.setFont(hf)
        p.setPen(QPen(self._COL_GOLD))
        p.drawText(10, 18, 'HUD 信息')

        dot_color = self._COL_RED if getattr(pc, 'mouse_one', False) else \
            self._COL_YELLOW if pc.StartFire else self._COL_GREEN
        p.setBrush(QBrush(dot_color))
        p.setPen(Qt.NoPen)
        p.drawEllipse(w - 20, 8, 10, 10)

        status_text = '开火中' if getattr(pc, 'mouse_one', False) else \
            '瞄准中' if pc.StartFire else '就绪'
        p.setFont(sf)
        p.setPen(QPen(dot_color))
        p.drawText(w - 24 - QFontMetrics(sf).horizontalAdvance(status_text), 18, status_text)

        p.setPen(QPen(QColor(255, 255, 255, 30)))
        p.drawLine(10, 24, w - 10, 24)

        results = pc.get_guns_result()
        y = 36

        for slot_idx in range(2):
            gun = results[slot_idx] if slot_idx < len(results) else {}
            is_active = pc.Current_firearms == slot_idx + 1
            gun_name = _gun_cn(gun.get('Name')) if gun and gun.get('Name') else '— 未装备 —'

            p.setFont(hf)
            if is_active:
                p.setPen(QPen(self._COL_GOLD))
                p.drawText(10, y, f'► 武器{slot_idx + 1}')
            else:
                p.setPen(QPen(self._COL_GRAY))
                p.drawText(10, y, f'  武器{slot_idx + 1}')

            p.setPen(QPen(self._COL_WHITE if is_active else self._COL_GRAY))
            p.drawText(70, y, gun_name)
            y += 16

            if gun and gun.get('Name') and str(gun['Name']).lower() != 'none':
                p.setFont(bf)
                col_w = (w - 24) // 2
                items_left = [('瞄', _scope_cn(gun.get('Scope')), gun.get('Scope', 'none').lower() != 'none'),
                              ('口', _attach_cn(gun.get('Muzzle')), gun.get('Muzzle', 'none').lower() != 'none')]
                items_right = [('握', _attach_cn(gun.get('Grip')), gun.get('Grip', 'none').lower() != 'none'),
                               ('托', _attach_cn(gun.get('Stock')), gun.get('Stock', 'none').lower() != 'none')]

                for row_items, x_off in [(items_left, 14), (items_right, 14 + col_w)]:
                    for lbl, val, has in row_items:
                        p.setPen(QPen(self._COL_DIM))
                        p.drawText(x_off, y, lbl)
                        p.setPen(QPen(self._COL_GREEN if has else self._COL_WHITE))
                        p.drawText(x_off + 22, y, val)
                        y += 15
                    y -= 15 * len(row_items)
                y += 15 * max(len(items_left), len(items_right))
            else:
                y += 6

            if slot_idx == 0:
                p.setPen(QPen(QColor(255, 255, 255, 20)))
                p.drawLine(10, y, w - 10, y)
                y += 6

        y += 4
        p.setPen(QPen(QColor(255, 255, 255, 30)))
        p.drawLine(10, y, w - 10, y)
        y += 14

        p.setFont(bf)
        posture = POSTURE_FULL.get(pc.Current_posture, '站立')
        p.setPen(QPen(self._COL_GRAY))
        p.drawText(14, y, '姿态')
        p.setPen(QPen(self._COL_WHITE))
        p.drawText(50, y, posture)

        p.setPen(QPen(self._COL_GRAY))
        p.drawText(110, y, '开镜')
        p.setPen(QPen(self._COL_GREEN if pc.StartFire else self._COL_GRAY))
        p.drawText(146, y, '已开镜' if pc.StartFire else '关闭')

        p.setPen(QPen(self._COL_GRAY))
        p.drawText(210, y, '视角')
        p.setPen(QPen(self._COL_WHITE))
        p.drawText(246, y, '第一人称' if pc.firstPerson else '第三人称')

        p.setFont(sf)
        p.setPen(QPen(self._COL_DIM))
        mode_key = self._cfg.get('hotkey_mode_switch', 'F9')
        hint = f'拖动中(F10锁定)' if self._drag_mode else f'{mode_key}切换 | F10拖动'
        p.drawText(w - QFontMetrics(sf).horizontalAdvance(hint) - 8, h - 6, hint)

    # ── Public API（向后兼容）──
    def show_hud(self):
        self._visible = True
        self._tab_hidden = False
        default_mode = self._cfg.get('default_mode', 'minimal')
        self._mode = {'minimal': MODE_MINIMAL, 'compact': MODE_COMPACT,
                      'full': MODE_FULL, 'bar': MODE_BAR}.get(default_mode, MODE_MINIMAL)
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
