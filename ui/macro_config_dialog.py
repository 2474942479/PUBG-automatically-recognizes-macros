"""宏配置对话框：编辑 4 个宏的触发键、镜像键、时序参数；保存后热重载。"""
import logging
from PyQt5 import QtCore, QtGui, QtWidgets

logger = logging.getLogger(__name__)

KEYBOARD_DISPLAY = {
    "q": "Q", "e": "E", "w": "W", "shift": "Shift", "ctrl": "Ctrl",
    "alt": "Alt", "space": "Space", "tab": "Tab",
}
MOUSE_DISPLAY = {
    "mouse_left": "鼠标左键", "mouse_right": "鼠标右键",
    "mouse_x1": "X1 后侧键", "mouse_x2": "X2 前侧键",
}


def _key_display(internal):
    if internal in MOUSE_DISPLAY:
        return MOUSE_DISPLAY[internal]
    return KEYBOARD_DISPLAY.get(internal, internal.upper() if internal else "")


class HotkeyCaptureLineEdit(QtWidgets.QLineEdit):
    """点击后捕获下一个键盘/鼠标按下事件作为热键。

    Esc 取消捕获、保留原值。
    内部存值用 internal_key（小写）；显示用 _key_display。
    """

    keyChanged = QtCore.pyqtSignal(str)

    def __init__(self, internal_key="", allow_mouse=True, parent=None):
        super().__init__(parent)
        self._internal = internal_key
        self._allow_mouse = allow_mouse
        self._capturing = False
        self.setReadOnly(True)
        self.setText(_key_display(internal_key))
        self.setCursor(QtCore.Qt.PointingHandCursor)
        self.setStyleSheet("QLineEdit { padding: 4px; }")

    def internal_key(self):
        return self._internal

    def set_internal_key(self, internal):
        self._internal = internal
        self.setText(_key_display(internal))

    def mousePressEvent(self, event):
        if not self._capturing:
            self._start_capture()
            event.accept()
            return
        if self._allow_mouse:
            mapping = {
                QtCore.Qt.LeftButton: "mouse_left",
                QtCore.Qt.RightButton: "mouse_right",
                QtCore.Qt.XButton1: "mouse_x1",
                QtCore.Qt.XButton2: "mouse_x2",
            }
            internal = mapping.get(event.button())
            if internal:
                self._finish_capture(internal)
                event.accept()
                return
        super().mousePressEvent(event)

    def keyPressEvent(self, event):
        if not self._capturing:
            super().keyPressEvent(event)
            return
        if event.key() == QtCore.Qt.Key_Escape:
            self._finish_capture(None)
            return
        internal = self._qt_key_to_internal(event)
        if internal:
            self._finish_capture(internal)

    def _start_capture(self):
        self._capturing = True
        self.setText("按下任意键... (Esc 取消)")
        self.setStyleSheet("QLineEdit { background: #fffaaa; padding: 4px; }")
        self.setFocus()

    def _finish_capture(self, new_internal):
        self._capturing = False
        self.setStyleSheet("QLineEdit { padding: 4px; }")
        if new_internal is not None:
            self._internal = new_internal
            self.keyChanged.emit(new_internal)
        self.setText(_key_display(self._internal))

    @staticmethod
    def _qt_key_to_internal(event):
        k = event.key()
        if QtCore.Qt.Key_A <= k <= QtCore.Qt.Key_Z:
            return chr(k).lower()
        if QtCore.Qt.Key_0 <= k <= QtCore.Qt.Key_9:
            return chr(k)
        special = {
            QtCore.Qt.Key_Shift: "shift", QtCore.Qt.Key_Control: "ctrl",
            QtCore.Qt.Key_Alt: "alt", QtCore.Qt.Key_Space: "space",
            QtCore.Qt.Key_Tab: "tab",
        }
        return special.get(k)
