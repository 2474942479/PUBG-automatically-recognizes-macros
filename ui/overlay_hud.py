# -*- coding: utf-8 -*-
"""游戏内 HUD 悬浮窗 — 三档可切换（极简 / 紧凑 / 完整）
用法：from ui.overlay_hud import GameHUD; hud = GameHUD(PC); hud.show_hud()
Tab → 临时隐藏/恢复（配合背包识别）
F9  → 循环切换显示模式：极简 → 紧凑 → 完整
"""
import sys, ctypes
from ctypes import wintypes
from PyQt5.QtCore import Qt, QTimer, QThread, pyqtSignal, QRectF
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


MODE_MINIMAL, MODE_COMPACT, MODE_FULL = 0, 1, 2


class _KeyListener(QThread):
    """监听 Tab（临时隐藏）和 F9（切换模式）"""
    sig_tab_press = pyqtSignal()
    sig_tab_release = pyqtSignal()
    sig_mode_switch = pyqtSignal()

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
            elif key == Key.f9:
                self.sig_mode_switch.emit()

        def on_release(key):
            k = _key_name(key)
            if k == 'tab':
                self.sig_tab_release.emit()

        listener = keyboard.Listener(on_press=on_press, on_release=on_release)
        listener.start()
        listener.join()


class GameHUD(QWidget):
    """三档游戏内 HUD
    Tab  = 临时隐藏/恢复（背包识别期间不挡视线）
    F9   = 极简 → 紧凑 → 完整 → 极简
    """

    _COL_BG = QColor(12, 12, 12, 220)
    _COL_BORDER = QColor(255, 186, 8, 100)
    _COL_GOLD = QColor(255, 186, 8)
    _COL_GREEN = QColor(74, 229, 74)
    _COL_RED = QColor(255, 68, 68)
    _COL_YELLOW = QColor(255, 215, 0)
    _COL_WHITE = QColor(255, 255, 255)
    _COL_GRAY = QColor(140, 140, 140)
    _COL_DIM = QColor(80, 80, 80)

    def __init__(self, pc, parent=None):
        super().__init__(parent)
        self._pc = pc
        self._mode = MODE_MINIMAL
        self._visible = True
        self._tab_hidden = False
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self._apply_size()
        self._position_right()

        self._key_t = _KeyListener()
        self._key_t.sig_tab_press.connect(self._on_tab_press)
        self._key_t.sig_tab_release.connect(self._on_tab_release)
        self._key_t.sig_mode_switch.connect(self._on_mode_switch)
        self._key_t.start()

        self._timer = QTimer(self)
        self._timer.timeout.connect(self.update)
        self._timer.start(250)

    def _apply_size(self):
        if self._mode == MODE_MINIMAL:
            self.setFixedSize(290, 30)
        elif self._mode == MODE_COMPACT:
            self.setFixedSize(260, 140)
        else:
            self.setFixedSize(300, 260)

    def _position_right(self):
        scr = QApplication.primaryScreen()
        if scr:
            g = scr.geometry()
            self.move(g.width() - self.width() - 20, 20)
        _make_click_through(int(self.winId()))

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
        self._mode = (self._mode + 1) % 3
        self._apply_size()
        self._position_right()
        self.update()

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

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        if self._mode == MODE_MINIMAL:
            self._paint_minimal(p)
        elif self._mode == MODE_COMPACT:
            self._paint_compact(p)
        else:
            self._paint_full(p)
        p.end()

    def _paint_minimal(self, p):
        pc = self._pc
        w, h = self.width(), self.height()

        grad = QLinearGradient(0, 0, w, 0)
        grad.setColorAt(0, QColor(12, 12, 12, 210))
        grad.setColorAt(1, QColor(12, 12, 12, 160))
        p.setBrush(QBrush(grad))
        p.setPen(QPen(self._COL_BORDER, 1))
        p.drawRoundedRect(QRectF(0.5, 0.5, w - 1, h - 1), 4, 4)

        gun, slot = self._get_current_gun()
        gun_name = _gun_cn(gun.get('Name')) if gun else '—'
        scope = _scope_cn(gun.get('Scope')) if gun else '—'
        posture = POSTURE_CN.get(pc.Current_posture, '站')

        font = QFont('Microsoft YaHei', 10, QFont.Bold)
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

        hint_font = QFont('Microsoft YaHei', 7)
        p.setFont(hint_font)
        p.setPen(QPen(self._COL_DIM))
        hint = 'F9切换'
        p.drawText(w - QFontMetrics(hint_font).horizontalAdvance(hint) - 8, 20, hint)

    def _paint_compact(self, p):
        pc = self._pc
        w, h = self.width(), self.height()

        p.setBrush(QBrush(self._COL_BG))
        p.setPen(QPen(self._COL_BORDER, 1))
        p.drawRoundedRect(QRectF(0.5, 0.5, w - 1, h - 1), 6, 6)

        gun, slot = self._get_current_gun()

        hf = QFont('Microsoft YaHei', 9, QFont.Bold)
        bf = QFont('Microsoft YaHei', 9)
        sf = QFont('Microsoft YaHei', 7)

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
        p.drawText(w - QFontMetrics(sf).horizontalAdvance('F9切换') - 8, h - 6, 'F9切换')

    def _paint_full(self, p):
        pc = self._pc
        w, h = self.width(), self.height()

        p.setBrush(QBrush(self._COL_BG))
        p.setPen(QPen(self._COL_BORDER, 1))
        p.drawRoundedRect(QRectF(0.5, 0.5, w - 1, h - 1), 6, 6)

        hf = QFont('Microsoft YaHei', 9, QFont.Bold)
        bf = QFont('Microsoft YaHei', 9)
        sf = QFont('Microsoft YaHei', 7)

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
        p.drawText(w - QFontMetrics(sf).horizontalAdvance('F9切换') - 8, h - 6, 'F9切换')

    # ── Public API（向后兼容）──
    def show_hud(self):
        self._visible = True
        self._tab_hidden = False
        self._mode = MODE_MINIMAL
        self._apply_size()
        self._position_right()
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
