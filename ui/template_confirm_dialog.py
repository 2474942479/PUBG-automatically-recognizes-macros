"""批量模板生成 — 确认保存对话框"""

import cv2
import numpy as np
from PyQt5 import QtCore, QtGui, QtWidgets


def _array_to_pixmap(gray, max_w=80, max_h=40):
    """将 OpenCV 灰度图转为 QPixmap 缩略图。"""
    h, w = gray.shape[:2]
    if w == 0 or h == 0:
        return QtGui.QPixmap(max_w, max_h)
    scale = min(max_w / w, max_h / h, 1.0)
    if scale < 1.0:
        nw, nh = int(w * scale), int(h * scale)
        img = cv2.resize(gray, (nw, nh), interpolation=cv2.INTER_AREA)
    else:
        img = gray
        nw, nh = w, h
    img = np.ascontiguousarray(img)
    buf = QtGui.QImage(img.data, nw, nh, nw, QtGui.QImage.Format_Grayscale8)
    return QtGui.QPixmap.fromImage(buf)


def _short_path(path, max_len=55):
    """截断路径显示，保留末尾关键部分。"""
    if not path:
        return ""
    if len(path) <= max_len:
        return path
    # 保留最后 max_len 字符，前面加 …
    return "…" + path[-(max_len - 1):]


class TemplateConfirmDialog(QtWidgets.QDialog):
    """确认哪些 ROI 要保存为模板的对话框。"""

    def __init__(self, candidates, parent=None):
        super().__init__(parent)
        self.candidates = candidates
        self.selected_indices = []
        self.name_overrides = {}  # {idx: edited_name}
        self._checkboxes = []
        self._name_inputs = {}    # {idx: QLineEdit}

        self.setWindowTitle("确认模板保存")
        self.setMinimumSize(660, 460)
        self.setStyleSheet(self._style())

        layout = QtWidgets.QVBoxLayout(self)
        layout.setSpacing(4)

        # 标题提示
        tip = QtWidgets.QLabel(
            "以下是从当前截图识别到的背包配件，请勾选需要保存为模板的项：\n"
            "未识别的项可手动输入名称后再勾选保存。"
        )
        tip.setWordWrap(True)
        layout.addWidget(tip)

        # 滚动区域 — 候选列表
        scroll = QtWidgets.QScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QtWidgets.QFrame.NoFrame)

        list_widget = QtWidgets.QWidget()
        self._list_layout = QtWidgets.QVBoxLayout(list_widget)
        self._list_layout.setSpacing(4)
        self._list_layout.setContentsMargins(0, 0, 0, 0)

        for i, c in enumerate(self.candidates):
            frame = self._build_item_row(i, c)
            self._list_layout.addWidget(frame)

        self._list_layout.addStretch()
        scroll.setWidget(list_widget)
        layout.addWidget(scroll, 1)

        # 按钮行
        btn_row = QtWidgets.QHBoxLayout()
        self._select_all_btn = QtWidgets.QPushButton("全选")
        self._select_all_btn.clicked.connect(self._on_select_all)
        btn_row.addWidget(self._select_all_btn)

        self._deselect_all_btn = QtWidgets.QPushButton("取消全选")
        self._deselect_all_btn.clicked.connect(self._on_deselect_all)
        btn_row.addWidget(self._deselect_all_btn)

        btn_row.addStretch()

        save_btn = QtWidgets.QPushButton("✓ 保存选中项")
        save_btn.setObjectName("SaveBtn")
        save_btn.clicked.connect(self._on_save)
        btn_row.addWidget(save_btn)

        cancel_btn = QtWidgets.QPushButton("✗ 取消")
        cancel_btn.clicked.connect(self.reject)
        btn_row.addWidget(cancel_btn)

        layout.addLayout(btn_row)

        # 初始选中状态：识别到的默认勾选，未识别的默认不勾选
        for i, c in enumerate(self.candidates):
            self._checkboxes[i].setChecked(c.get('recognized', False))

    # ── 构建单行 ──

    def _build_item_row(self, idx, c):
        frame = QtWidgets.QFrame(self)
        frame.setObjectName("ItemFrame")
        frame.setFrameShape(QtWidgets.QFrame.StyledPanel)
        hl = QtWidgets.QHBoxLayout(frame)
        hl.setContentsMargins(6, 4, 6, 4)
        hl.setSpacing(8)

        # 复选框
        cb = QtWidgets.QCheckBox()
        self._checkboxes.append(cb)
        hl.addWidget(cb)

        # 缩略图
        thumb = _array_to_pixmap(c['roi_image'])
        thumb_label = QtWidgets.QLabel()
        thumb_label.setPixmap(thumb)
        thumb_label.setFixedSize(thumb.width(), thumb.height())
        thumb_label.setStyleSheet("border: 1px solid #3a3a5a; border-radius: 2px;")
        hl.addWidget(thumb_label)

        # 右侧信息区域（垂直）
        vbox = QtWidgets.QVBoxLayout()
        vbox.setSpacing(2)

        # 第一行：ROI类型 + 置信度 + 尺寸
        recognized = c.get('recognized', False)
        conf_text = f"{c['confidence']:.1%}" if recognized else "—"
        top_line = QtWidgets.QLabel(
            f"<b>{c['roi_type']}</b> &nbsp;({c['category_label']})"
            f" &nbsp;置信度: {conf_text} &nbsp;尺寸: {c['w']}×{c['h']}"
        )
        vbox.addWidget(top_line)

        # 第二行：名称（已识别显示文本，未识别显示输入框）
        name_row = QtWidgets.QHBoxLayout()
        name_row.setSpacing(6)
        name_label = QtWidgets.QLabel("名称:")
        name_label.setStyleSheet("color: #a0a0b0;")
        name_row.addWidget(name_label)

        if recognized:
            name_input = QtWidgets.QLineEdit(c['name'])
            name_input.setStyleSheet(
                "background-color: #2a2a4a; color: #4ae04a; border: 1px solid #3a3a5a; "
                "border-radius: 3px; padding: 2px 6px;"
            )
        else:
            name_input = QtWidgets.QLineEdit()
            name_input.setPlaceholderText("输入模板名称（如 m416）")
            name_input.setStyleSheet(
                "background-color: #2a2a4a; color: #ffba08; border: 1px solid #ffba08; "
                "border-radius: 3px; padding: 2px 6px;"
            )
        name_input.textChanged.connect(
            lambda text, i=idx: self._on_name_edited(i, text)
        )
        self._name_inputs[idx] = name_input
        name_row.addWidget(name_input, 1)
        vbox.addLayout(name_row)

        # 第三行：匹配来源路径（如果有）
        source = c.get('match_source')
        if source:
            path_text = _short_path(source)
            source_label = QtWidgets.QLabel(
                f"<span style='color:#7a7a9a; font-size:8pt;'>匹配来源: {path_text}</span>"
            )
            source_label.setWordWrap(True)
            vbox.addWidget(source_label)

        hl.addLayout(vbox, 1)

        return frame

    # ── 槽函数 ──

    def _on_select_all(self):
        for cb in self._checkboxes:
            cb.setChecked(True)

    def _on_deselect_all(self):
        for cb in self._checkboxes:
            cb.setChecked(False)

    def _on_name_edited(self, idx, text):
        """用户编辑了名称输入框。"""
        text = text.strip()
        if text:
            self.name_overrides[idx] = text
        else:
            self.name_overrides.pop(idx, None)

    def _on_save(self):
        self.selected_indices = [
            i for i, cb in enumerate(self._checkboxes) if cb.isChecked()
        ]
        if not self.selected_indices:
            QtWidgets.QMessageBox.warning(self, "提示", "请至少勾选一个要保存的项")
            return

        # 检查勾选的项是否都有名称
        no_name = []
        for i in self.selected_indices:
            c = self.candidates[i]
            name = self.name_overrides.get(i) or c.get('name', '')
            if not name or name == '无法识别':
                no_name.append(c['roi_type'])
        if no_name:
            QtWidgets.QMessageBox.warning(
                self, "提示",
                f"以下项目还未输入有效名称：\n{', '.join(no_name)}\n\n"
                "请先输入名称或取消勾选。"
            )
            return

        self.accept()

    @staticmethod
    def _style():
        return """
        QFrame#ItemFrame {
            background-color: #1e1e36;
            border: 1px solid #2a2a4a;
            border-radius: 4px;
        }
        QFrame#ItemFrame:hover {
            border-color: #ffba08;
            background-color: #262642;
        }
        QPushButton#SaveBtn {
            background-color: #0f7b3f;
            border-color: #0f7b3f;
            color: #ffffff;
            font-weight: bold;
            padding: 6px 18px;
        }
        QPushButton#SaveBtn:hover { background-color: #14a050; }
        """
