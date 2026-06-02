"""宏配置对话框：编辑 4 个宏的触发键、镜像键、时序参数；保存后热重载。"""
import logging
from PyQt5 import QtCore, QtWidgets

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


class MacroConfigDialog(QtWidgets.QDialog):
    """宏配置对话框：4 个宏的热键/时序编辑 + 保存触发热重载。"""

    def __init__(self, pc, parent=None):
        super().__init__(parent)
        self.PC = pc
        self.setWindowTitle("宏配置")
        self.setMinimumWidth(620)
        self._build_ui()
        self._load_from_config(self.PC.get_config_data("macros"))

    def _build_ui(self):
        root = QtWidgets.QVBoxLayout(self)

        self.global_enable = QtWidgets.QCheckBox("启用宏系统总开关", self)
        root.addWidget(self.global_enable)

        self.qp_box = self._make_quick_peek_group()
        self.pf_box = self._make_peek_fake_group()
        self.ss_box = self._make_slide_step_group()
        self.bj_box = self._make_big_jump_group()
        for b in (self.qp_box, self.pf_box, self.ss_box, self.bj_box):
            root.addWidget(b)

        btn_row = QtWidgets.QHBoxLayout()
        self.btn_default = QtWidgets.QPushButton("恢复默认", self)
        self.btn_cancel = QtWidgets.QPushButton("取消", self)
        self.btn_save = QtWidgets.QPushButton("保存", self)
        btn_row.addWidget(self.btn_default)
        btn_row.addStretch()
        btn_row.addWidget(self.btn_cancel)
        btn_row.addWidget(self.btn_save)
        root.addLayout(btn_row)

        self.btn_default.clicked.connect(self._on_restore_default)
        self.btn_cancel.clicked.connect(self.reject)
        self.btn_save.clicked.connect(self._on_save)

    def _make_quick_peek_group(self):
        box = QtWidgets.QGroupBox("闪身宏（修饰键 + 触发键）", self)
        layout = QtWidgets.QFormLayout(box)
        self.qp_enabled = QtWidgets.QCheckBox("启用", box)
        self.qp_modifier = HotkeyCaptureLineEdit("mouse_x1", parent=box)
        self.qp_primary = HotkeyCaptureLineEdit("q", parent=box)
        self.qp_mirror = HotkeyCaptureLineEdit("e", parent=box)
        self.qp_ads = QtWidgets.QSpinBox(box); self.qp_ads.setRange(0, 1000); self.qp_ads.setSuffix(" ms")
        self.qp_hold = QtWidgets.QSpinBox(box); self.qp_hold.setRange(50, 2000); self.qp_hold.setSuffix(" ms")
        self.qp_release = QtWidgets.QSpinBox(box); self.qp_release.setRange(0, 500); self.qp_release.setSuffix(" ms")
        self.qp_cd = QtWidgets.QSpinBox(box); self.qp_cd.setRange(0, 1000); self.qp_cd.setSuffix(" ms")

        layout.addRow(self.qp_enabled)
        layout.addRow("修饰键", self.qp_modifier)
        layout.addRow("触发键", self.qp_primary)
        layout.addRow("镜像键 (可选)", self.qp_mirror)
        layout.addRow("ADS 延迟", self.qp_ads)
        layout.addRow("探头保持", self.qp_hold)
        layout.addRow("释放延迟", self.qp_release)
        layout.addRow("冷却", self.qp_cd)
        return box

    def _make_peek_fake_group(self):
        box = QtWidgets.QGroupBox("Q 弹反", self)
        layout = QtWidgets.QFormLayout(box)
        self.pf_enabled = QtWidgets.QCheckBox("启用", box)
        self.pf_modifier = HotkeyCaptureLineEdit("mouse_right", parent=box)
        self.pf_primary = HotkeyCaptureLineEdit("q", parent=box)
        self.pf_mirror = HotkeyCaptureLineEdit("e", parent=box)
        self.pf_hold = QtWidgets.QSpinBox(box); self.pf_hold.setRange(50, 1000); self.pf_hold.setSuffix(" ms")
        self.pf_reverse = QtWidgets.QSpinBox(box); self.pf_reverse.setRange(0, 200); self.pf_reverse.setSuffix(" ms")
        self.pf_cd = QtWidgets.QSpinBox(box); self.pf_cd.setRange(0, 1000); self.pf_cd.setSuffix(" ms")

        layout.addRow(self.pf_enabled)
        layout.addRow("修饰键", self.pf_modifier)
        layout.addRow("触发键", self.pf_primary)
        layout.addRow("镜像键 (可选)", self.pf_mirror)
        layout.addRow("探头保持", self.pf_hold)
        layout.addRow("反向 tap", self.pf_reverse)
        layout.addRow("冷却", self.pf_cd)
        return box

    def _make_slide_step_group(self):
        box = QtWidgets.QGroupBox("滑步循环（组合键全部按下时触发）", self)
        layout = QtWidgets.QFormLayout(box)
        self.ss_enabled = QtWidgets.QCheckBox("启用", box)
        self.ss_combo_a = HotkeyCaptureLineEdit("shift", parent=box)
        self.ss_combo_b = HotkeyCaptureLineEdit("w", parent=box)
        self.ss_startup = QtWidgets.QSpinBox(box); self.ss_startup.setRange(0, 2000); self.ss_startup.setSuffix(" ms")
        self.ss_hold = QtWidgets.QSpinBox(box); self.ss_hold.setRange(10, 500); self.ss_hold.setSuffix(" ms")
        self.ss_interval = QtWidgets.QSpinBox(box); self.ss_interval.setRange(50, 2000); self.ss_interval.setSuffix(" ms")

        layout.addRow(self.ss_enabled)
        layout.addRow("组合键 A", self.ss_combo_a)
        layout.addRow("组合键 B", self.ss_combo_b)
        layout.addRow("启动延迟", self.ss_startup)
        layout.addRow("C 持续", self.ss_hold)
        layout.addRow("C 间隔", self.ss_interval)
        return box

    def _make_big_jump_group(self):
        box = QtWidgets.QGroupBox("大跳", self)
        layout = QtWidgets.QFormLayout(box)
        self.bj_enabled = QtWidgets.QCheckBox("启用", box)
        self.bj_combo_a = HotkeyCaptureLineEdit("shift", parent=box)
        self.bj_combo_b = HotkeyCaptureLineEdit("space", parent=box)
        self.bj_delay = QtWidgets.QSpinBox(box); self.bj_delay.setRange(0, 1000); self.bj_delay.setSuffix(" ms")
        self.bj_hold = QtWidgets.QSpinBox(box); self.bj_hold.setRange(10, 500); self.bj_hold.setSuffix(" ms")
        self.bj_cd = QtWidgets.QSpinBox(box); self.bj_cd.setRange(0, 2000); self.bj_cd.setSuffix(" ms")

        layout.addRow(self.bj_enabled)
        layout.addRow("组合键 A", self.bj_combo_a)
        layout.addRow("组合键 B", self.bj_combo_b)
        layout.addRow("空中蹲延迟", self.bj_delay)
        layout.addRow("C 持续", self.bj_hold)
        layout.addRow("冷却", self.bj_cd)
        return box

    def _load_from_config(self, cfg):
        self.global_enable.setChecked(cfg.get("enabled", True))

        qp = cfg.get("quick_peek", {})
        self.qp_enabled.setChecked(qp.get("enabled", True))
        self.qp_modifier.set_internal_key(qp.get("modifier", "mouse_x1"))
        self.qp_primary.set_internal_key(qp.get("primary_key", "q"))
        self.qp_mirror.set_internal_key(qp.get("mirror_key", "e") or "")
        self.qp_ads.setValue(qp.get("ads_wait_ms", 0))
        self.qp_hold.setValue(qp.get("peek_hold_ms", 300))
        self.qp_release.setValue(qp.get("release_delay_ms", 50))
        self.qp_cd.setValue(qp.get("cooldown_ms", 100))

        pf = cfg.get("peek_fake", {})
        self.pf_enabled.setChecked(pf.get("enabled", True))
        self.pf_modifier.set_internal_key(pf.get("modifier", "mouse_right"))
        self.pf_primary.set_internal_key(pf.get("primary_key", "q"))
        self.pf_mirror.set_internal_key(pf.get("mirror_key", "e") or "")
        self.pf_hold.setValue(pf.get("peek_hold_ms", 120))
        self.pf_reverse.setValue(pf.get("reverse_tap_ms", 10))
        self.pf_cd.setValue(pf.get("cooldown_ms", 100))

        ss = cfg.get("slide_step", {})
        self.ss_enabled.setChecked(ss.get("enabled", True))
        combo = ss.get("combo_keys", ["shift", "w"])
        self.ss_combo_a.set_internal_key(combo[0] if len(combo) > 0 else "shift")
        self.ss_combo_b.set_internal_key(combo[1] if len(combo) > 1 else "w")
        self.ss_startup.setValue(ss.get("startup_delay_ms", 200))
        self.ss_hold.setValue(ss.get("crouch_hold_ms", 50))
        self.ss_interval.setValue(ss.get("crouch_interval_ms", 300))

        bj = cfg.get("big_jump", {})
        self.bj_enabled.setChecked(bj.get("enabled", True))
        combo = bj.get("combo_keys", ["shift", "space"])
        self.bj_combo_a.set_internal_key(combo[0] if len(combo) > 0 else "shift")
        self.bj_combo_b.set_internal_key(combo[1] if len(combo) > 1 else "space")
        self.bj_delay.setValue(bj.get("crouch_delay_ms", 180))
        self.bj_hold.setValue(bj.get("crouch_hold_ms", 80))
        self.bj_cd.setValue(bj.get("cooldown_ms", 300))

    def _collect_to_config(self):
        return {
            "enabled": self.global_enable.isChecked(),
            "quick_peek": {
                "enabled": self.qp_enabled.isChecked(),
                "modifier": self.qp_modifier.internal_key(),
                "primary_key": self.qp_primary.internal_key(),
                "mirror_key": self.qp_mirror.internal_key() or None,
                "ads_wait_ms": self.qp_ads.value(),
                "peek_hold_ms": self.qp_hold.value(),
                "release_delay_ms": self.qp_release.value(),
                "reverse_tap_ms": 10,
                "cooldown_ms": self.qp_cd.value(),
            },
            "peek_fake": {
                "enabled": self.pf_enabled.isChecked(),
                "modifier": self.pf_modifier.internal_key(),
                "primary_key": self.pf_primary.internal_key(),
                "mirror_key": self.pf_mirror.internal_key() or None,
                "peek_hold_ms": self.pf_hold.value(),
                "reverse_tap_ms": self.pf_reverse.value(),
                "cooldown_ms": self.pf_cd.value(),
            },
            "slide_step": {
                "enabled": self.ss_enabled.isChecked(),
                "combo_keys": [self.ss_combo_a.internal_key(), self.ss_combo_b.internal_key()],
                "startup_delay_ms": self.ss_startup.value(),
                "crouch_hold_ms": self.ss_hold.value(),
                "crouch_interval_ms": self.ss_interval.value(),
            },
            "big_jump": {
                "enabled": self.bj_enabled.isChecked(),
                "combo_keys": [self.bj_combo_a.internal_key(), self.bj_combo_b.internal_key()],
                "crouch_delay_ms": self.bj_delay.value(),
                "crouch_hold_ms": self.bj_hold.value(),
                "cooldown_ms": self.bj_cd.value(),
            },
        }

    def _validate(self, cfg):
        """检查冲突。返回错误字符串列表（空 = 通过）。"""
        errors = []
        for sub_name, label in [
            ("quick_peek", "闪身宏"),
            ("peek_fake", "Q 弹反"),
        ]:
            sub = cfg[sub_name]
            keys = [sub["modifier"], sub["primary_key"]]
            if sub.get("mirror_key"):
                keys.append(sub["mirror_key"])
            if len(set(keys)) < len(keys):
                errors.append(f"{label}：修饰键、触发键、镜像键不能相同")
        for sub_name, label in [("slide_step", "滑步"), ("big_jump", "大跳")]:
            combo = cfg[sub_name]["combo_keys"]
            if combo[0] == combo[1] or not combo[0] or not combo[1]:
                errors.append(f"{label}：组合键 A 与 B 必须不同且都不能为空")
        return errors

    def _on_save(self):
        cfg = self._collect_to_config()
        errors = self._validate(cfg)
        if errors:
            QtWidgets.QMessageBox.warning(self, "配置错误", "\n".join(errors))
            return
        self.PC.save_config_data("macros", cfg)
        self.PC.macros_config = cfg
        self.PC.macro_dispatcher.reload_config(cfg)
        logger.info("宏配置已保存并热重载")
        self.accept()

    def _on_restore_default(self):
        from core.process import DEFAULT_MACROS_CONFIG
        self._load_from_config(DEFAULT_MACROS_CONFIG)
