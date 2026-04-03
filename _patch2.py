import re
p = r'D:\Pycharm\workspace\PUBG-automatically-recognizes-macros\overlay_hud.py'
c = open(p, encoding='utf-8').read()

# 1. Add pynput imports after existing imports
c = c.replace(
    'from PyQt5.QtWidgets import QApplication, QWidget, QLabel, QVBoxLayout, QHBoxLayout',
    'from PyQt5.QtWidgets import QApplication, QWidget, QLabel, QVBoxLayout, QHBoxLayout\nfrom pynput import keyboard\nfrom pynput.keyboard import Key'
)

# 2. Add TabListener class before GameHUD
tab_class = """
class _TabListener(QThread):
    \"\"\"全局 Tab 键监听线程 — 按下隐藏，松开显示\"\"\"
    sig_hide = pyqtSignal()\n    sig_show = pyqtSignal()\n\n    def run(self):\n        def on_press(key):\n            try:\n                k = key.name if isinstance(key, Key) else key.char\n            except AttributeError:\n                return\n            if k == 'tab':\n                self.sig_hide.emit()\n\n        def on_release(key):\n            try:\n                k = key.name if isinstance(key, Key) else key.char\n            except AttributeError:\n                return\n            if k == 'tab':\n                self.sig_show.emit()\n\n        listener = keyboard.Listener(on_press=on_press, on_release=on_release)\n        listener.start()\n        listener.join()\n
"""
c = c.replace('class GameHUD(QWidget):', tab_class + 'class GameHUD(QWidget):')

# 3. Resize window
c = c.replace('self.setFixedSize(420, 320)', 'self.setFixedSize(560, 420)')

# 4. Add Tab init before self._center_right()
c = c.replace(
    'self._center_right()\n',
    'self._center_right()\n        # Tab 键监听\n        self._tab_thread = _TabListener()\n        self._tab_thread.sig_hide.connect(self._on_tab_hide)\n        self._tab_thread.sig_show.connect(self._on_tab_show)\n        self._tab_thread.start()\n'
)

# 5. Add _on_tab_hide and _on_tab_show after _center_right method
hide_show = """\n    def _on_tab_hide(self):\n        \"\"\"Tab 按下 → 隐藏 HUD\"\"\"\n        if self._visible:\n            self.hide()\n            self._timer.stop()\n\n    def _on_tab_show(self):\n        \"\"\"Tab 松开 → 恢复 HUD\"\"\"\n        if self._visible:\n            self.show()\n            self._refresh()\n            self._timer.start()\n"""
c = c.replace('    def show_hud(self):', hide_show + '\n    def show_hud(self):')

# 6. Update stop() to terminate tab thread
c = c.replace(
    'self._timer.stop()\n        self.close()',
    'self._timer.stop()\n        if hasattr(self, "_tab_thread") and self._tab_thread.isRunning():\n            self._tab_thread.terminate()\n        self.close()'
)

# 7. Update hint text
c = c.replace("右键拖动", "右键拖动 | Tab 隐藏")

open(p, 'w', encoding='utf-8').write(c)
print('OK2', len(c))
