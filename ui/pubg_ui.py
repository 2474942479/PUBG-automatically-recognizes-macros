"""PUBG 宏识别工具 — 现代暗色主题 UI"""
from PyQt5 import QtCore, QtGui, QtWidgets
from core.paths import res_path

# ═══════════════════════════════════════════════════════════
# 全局暗色主题 QSS
# ═══════════════════════════════════════════════════════════

DARK_STYLE = """
/* ── 全局 ── */
QWidget {
    background-color: #1a1a2e;
    color: #e0e0e0;
    font-family: "Microsoft YaHei", "Segoe UI", sans-serif;
    font-size: 10pt;
}
QWidget#Container {
    background-color: #1a1a2e;
    border-radius: 8px;
}

/* ── 自定义标题栏 ── */
QWidget#TitleBar {
    background-color: #16213e;
    border-top-left-radius: 8px;
    border-top-right-radius: 8px;
    min-height: 32px;
}
QLabel#TitleLabel {
    color: #ffba08;
    font-size: 12pt;
    font-weight: bold;
    padding-left: 8px;
}
QLabel#VersionLabel {
    color: #7a7a9a;
    font-size: 8pt;
    padding-right: 8px;
}

/* ── GroupBox ── */
QGroupBox {
    border: 1px solid #2a2a4a;
    border-radius: 6px;
    margin-top: 12px;
    padding: 6px 4px 4px 4px;
    font-weight: bold;
    color: #c0c0d0;
}
QGroupBox::title {
    subcontrol-origin: margin;
    subcontrol-position: top left;
    padding: 0 6px;
    color: #ffba08;
    font-size: 9pt;
}

/* ── 按钮 ── */
QPushButton {
    background-color: #2a2a4a;
    color: #e0e0e0;
    border: 1px solid #3a3a5a;
    border-radius: 4px;
    padding: 5px 12px;
    font-weight: bold;
    min-height: 22px;
}
QPushButton:hover {
    background-color: #3a3a5a;
    border-color: #ffba08;
}
QPushButton:pressed {
    background-color: #ffba08;
    color: #1a1a2e;
}
QPushButton:disabled {
    background-color: #1a1a2e;
    color: #4a4a5a;
    border-color: #2a2a3a;
}
QPushButton#Startbtn {
    background-color: #0f7b3f;
    border-color: #0f7b3f;
    color: #ffffff;
}
QPushButton#Startbtn:hover {
    background-color: #14a050;
}
QPushButton#Startbtn:disabled {
    background-color: #1a1a2e;
    color: #4a4a5a;
    border-color: #2a2a3a;
}
QPushButton#Stopbtn {
    background-color: #8b1a1a;
    border-color: #8b1a1a;
    color: #ffffff;
}
QPushButton#Stopbtn:hover {
    background-color: #b22222;
}
QPushButton#Stopbtn:disabled {
    background-color: #1a1a2e;
    color: #4a4a5a;
    border-color: #2a2a3a;
}

/* ── 标题栏齿轮工具按钮 ── */
QToolButton#ToolsBtn {
    background-color: transparent;
    color: #7a7a9a;
    border: none;
    font-size: 16pt;
    padding: 2px 6px;
    border-radius: 3px;
}
QToolButton#ToolsBtn:hover {
    background-color: #2a2a4a;
    color: #ffba08;
}
QToolButton#ToolsBtn::menu-indicator {
    image: none;
}
QMenu#ToolsMenu {
    background-color: #1a1a2e;
    border: 1px solid #3a3a5a;
    border-radius: 4px;
    padding: 4px;
}
QMenu#ToolsMenu::item {
    padding: 6px 20px;
    color: #e0e0e0;
    border-radius: 3px;
}
QMenu#ToolsMenu::item:selected {
    background-color: #ffba08;
    color: #1a1a2e;
}

/* ── RadioButton ── */
QRadioButton {
    spacing: 4px;
    color: #c0c0d0;
    font-size: 9pt;
}
QRadioButton::indicator {
    width: 14px;
    height: 14px;
    border-radius: 7px;
    border: 2px solid #4a4a6a;
    background-color: #1a1a2e;
}
QRadioButton::indicator:checked {
    background-color: #ffba08;
    border-color: #ffba08;
}
QRadioButton::indicator:hover {
    border-color: #ffba08;
}

/* ── ComboBox ── */
QComboBox {
    background-color: #2a2a4a;
    color: #e0e0e0;
    border: 1px solid #3a3a5a;
    border-radius: 4px;
    padding: 3px 8px;
    min-height: 20px;
}
QComboBox:hover {
    border-color: #ffba08;
}
QComboBox::drop-down {
    border: none;
    width: 20px;
}
QComboBox::down-arrow {
    image: none;
    border-left: 4px solid transparent;
    border-right: 4px solid transparent;
    border-top: 6px solid #c0c0d0;
    margin-right: 6px;
}
QComboBox QAbstractItemView {
    background-color: #2a2a4a;
    color: #e0e0e0;
    selection-background-color: #ffba08;
    selection-color: #1a1a2e;
    border: 1px solid #3a3a5a;
}

/* ── LineEdit ── */
QLineEdit {
    background-color: #2a2a4a;
    color: #e0e0e0;
    border: 1px solid #3a3a5a;
    border-radius: 4px;
    padding: 3px 8px;
    min-height: 20px;
}
QLineEdit:focus {
    border-color: #ffba08;
}
QLineEdit:read-only {
    background-color: #1a1a2e;
    color: #a0a0b0;
    border-color: #2a2a3a;
}

/* ── TextEdit (日志) ── */
QTextEdit {
    background-color: #0f0f1a;
    color: #a0e0a0;
    border: 1px solid #2a2a4a;
    border-radius: 4px;
    padding: 4px;
    font-family: "Consolas", "Courier New", monospace;
    font-size: 9pt;
}

/* ── 枪械信息标签 ── */
QLabel {
    color: #c0c0d0;
}
QLabel.gun-name {
    color: #ffba08;
    font-size: 11pt;
    font-weight: bold;
}
QLabel.accessory-scope {
    color: #ff4444;
    font-weight: bold;
}
QLabel.accessory-muzzle {
    color: #4ae04a;
    font-weight: bold;
}
QLabel.accessory-grip {
    color: #e0a040;
    font-weight: bold;
}
QLabel.accessory-stock {
    color: #4a9eff;
    font-weight: bold;
}

/* ── StatusInfo ── */
QLineEdit#StatusInfo {
    background-color: #0f0f1a;
    color: #ffba08;
    border: 1px solid #2a2a4a;
    font-weight: bold;
    font-size: 9pt;
}
"""


class Ui_PUBG(object):

    # ── 自定义窗口拖动支持 ──

    _drag_pos = None

    def mousePressEvent(self, event):
        if event.button() == QtCore.Qt.LeftButton and event.y() < 36:
            self._drag_pos = event.globalPos() - self.frameGeometry().topLeft()
            event.accept()

    def mouseMoveEvent(self, event):
        if self._drag_pos is not None:
            self.move(event.globalPos() - self._drag_pos)
            event.accept()

    def mouseReleaseEvent(self, event):
        self._drag_pos = None

    # ── UI 构建 ──

    def setupUi(self, PUBG):
        PUBG.setObjectName("PUBG")
        PUBG.resize(620, 480)
        PUBG.setWindowFlags(
            QtCore.Qt.FramelessWindowHint | QtCore.Qt.WindowStaysOnTopHint
        )
        PUBG.setStyleSheet(DARK_STYLE)
        PUBG.setWindowOpacity(0.95)

        icon = QtGui.QIcon()
        ico_path = res_path('_internal', 'GHUB.ico')
        icon.addPixmap(QtGui.QPixmap(ico_path), QtGui.QIcon.Normal, QtGui.QIcon.Off)
        PUBG.setWindowIcon(icon)

        root_layout = QtWidgets.QVBoxLayout(PUBG)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        self.Container = QtWidgets.QWidget(PUBG)
        self.Container.setObjectName("Container")
        root_layout.addWidget(self.Container)

        main_layout = QtWidgets.QVBoxLayout(self.Container)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # ────── 自定义标题栏 ──────
        title_bar = QtWidgets.QWidget(self.Container)
        title_bar.setObjectName("TitleBar")
        title_bar.setFixedHeight(36)
        tb_layout = QtWidgets.QHBoxLayout(title_bar)
        tb_layout.setContentsMargins(10, 0, 10, 0)

        title_label = QtWidgets.QLabel("PUBG 宏识别工具", title_bar)
        title_label.setObjectName("TitleLabel")
        tb_layout.addWidget(title_label)

        tb_layout.addStretch()

        self._version_label = QtWidgets.QLabel("", title_bar)
        self._version_label.setObjectName("VersionLabel")
        tb_layout.addWidget(self._version_label)

        # ⚙️ 齿轮工具按钮（ROI 配置 + 批量生成模板）
        self.ToolsBtn = QtWidgets.QToolButton(title_bar)
        self.ToolsBtn.setObjectName("ToolsBtn")
        self.ToolsBtn.setText("⚙")
        self.ToolsBtn.setToolTip("工具（ROI 配置 / 批量生成模板）")
        self.ToolsBtn.setPopupMode(QtWidgets.QToolButton.InstantPopup)
        self.ToolsBtn.setArrowType(QtCore.Qt.NoArrow)

        self.ToolsMenu = QtWidgets.QMenu(self.ToolsBtn)
        self.ToolsMenu.setObjectName("ToolsMenu")
        self.actionROIConfig = self.ToolsMenu.addAction("ROI 配置 (F8)")
        self.actionBatchTemplate = self.ToolsMenu.addAction("批量生成模板 (Ctrl+Alt+F8)")
        self.ToolsBtn.setMenu(self.ToolsMenu)

        tb_layout.addWidget(self.ToolsBtn)

        main_layout.addWidget(title_bar)

        # ────── 内容区 ──────
        content = QtWidgets.QWidget(self.Container)
        content_layout = QtWidgets.QVBoxLayout(content)
        content_layout.setContentsMargins(8, 4, 8, 8)
        content_layout.setSpacing(4)

        # ═══ 枪械识别区 ═══
        guns_row = QtWidgets.QHBoxLayout()
        guns_row.setSpacing(8)

        self.OneGunsBox = self._build_gun_group(content, "1号枪", 1)
        self.TwoGunsBox = self._build_gun_group(content, "2号枪", 2)
        guns_row.addWidget(self.OneGunsBox)
        guns_row.addWidget(self.TwoGunsBox)
        content_layout.addLayout(guns_row)

        # ═══ 状态控制区 ═══
        ctrl_row = QtWidgets.QHBoxLayout()
        ctrl_row.setSpacing(6)

        # 当前装备
        self.EquipBox = QtWidgets.QGroupBox("当前装备", content)
        self.EquipBox.setEnabled(False)
        eq_layout = QtWidgets.QHBoxLayout(self.EquipBox)
        eq_layout.setContentsMargins(6, 2, 6, 2)
        self.OneGuns = QtWidgets.QRadioButton("1号枪", self.EquipBox)
        self.TwoGuns = QtWidgets.QRadioButton("2号枪", self.EquipBox)
        self.Orders = QtWidgets.QRadioButton("其他", self.EquipBox)
        eq_layout.addWidget(self.OneGuns)
        eq_layout.addWidget(self.TwoGuns)
        eq_layout.addWidget(self.Orders)
        ctrl_row.addWidget(self.EquipBox)

        # 当前姿势
        self.PoseBox = QtWidgets.QGroupBox("当前姿势", content)
        self.PoseBox.setEnabled(False)
        pose_layout = QtWidgets.QHBoxLayout(self.PoseBox)
        pose_layout.setContentsMargins(6, 2, 6, 2)
        self.SquatDown = QtWidgets.QRadioButton("下蹲", self.PoseBox)
        self.GetDown = QtWidgets.QRadioButton("趴下", self.PoseBox)
        self.Stand = QtWidgets.QRadioButton("站立", self.PoseBox)
        pose_layout.addWidget(self.SquatDown)
        pose_layout.addWidget(self.GetDown)
        pose_layout.addWidget(self.Stand)
        ctrl_row.addWidget(self.PoseBox)

        content_layout.addLayout(ctrl_row)

        # ═══ 开镜 & 视角 ═══
        scope_row = QtWidgets.QHBoxLayout()
        scope_row.setSpacing(6)

        # 开镜模式
        self.ScopeMode = QtWidgets.QGroupBox("开镜模式", content)
        sm_layout = QtWidgets.QHBoxLayout(self.ScopeMode)
        sm_layout.setContentsMargins(6, 2, 6, 2)
        self.LongPress = QtWidgets.QRadioButton("长按", self.ScopeMode)
        self.ClickPress = QtWidgets.QRadioButton("单击", self.ScopeMode)
        sm_layout.addWidget(self.LongPress)
        sm_layout.addWidget(self.ClickPress)
        scope_row.addWidget(self.ScopeMode)

        # 是否开镜
        self.IsScope = QtWidgets.QGroupBox("是否开镜", content)
        self.IsScope.setEnabled(False)
        is_layout = QtWidgets.QHBoxLayout(self.IsScope)
        is_layout.setContentsMargins(6, 2, 6, 2)
        self.OpenScope = QtWidgets.QRadioButton("开镜", self.IsScope)
        self.CloseScope = QtWidgets.QRadioButton("未开镜", self.IsScope)
        is_layout.addWidget(self.OpenScope)
        is_layout.addWidget(self.CloseScope)
        scope_row.addWidget(self.IsScope)

        # 视角选择
        self.ViewMode = QtWidgets.QGroupBox("视角选择", content)
        vm_layout = QtWidgets.QHBoxLayout(self.ViewMode)
        vm_layout.setContentsMargins(6, 2, 6, 2)
        self.FirstPerson = QtWidgets.QRadioButton("第一人称", self.ViewMode)
        self.ThirdPerson = QtWidgets.QRadioButton("第三人称", self.ViewMode)
        vm_layout.addWidget(self.FirstPerson)
        vm_layout.addWidget(self.ThirdPerson)
        scope_row.addWidget(self.ViewMode)

        content_layout.addLayout(scope_row)

        # ═══ 参数设置区 ═══
        param_row = QtWidgets.QHBoxLayout()
        param_row.setSpacing(6)

        # 分辨率
        res_group = QtWidgets.QGroupBox("分辨率", content)
        rg_layout = QtWidgets.QHBoxLayout(res_group)
        rg_layout.setContentsMargins(6, 2, 6, 2)
        self.ResolutionSelect = QtWidgets.QComboBox(res_group)
        for r in ["3840x2160", "3440x1440", "2560x1600", "2560x1440",
                   "2304x1440", "2560x1080", "1920x1080", "1728x1080"]:
            self.ResolutionSelect.addItem(r)
        rg_layout.addWidget(self.ResolutionSelect, 2)
        self.ResolutionBtn = QtWidgets.QPushButton("保存", res_group)
        rg_layout.addWidget(self.ResolutionBtn, 1)
        param_row.addWidget(res_group)

        # 倍镜系数
        sens_group = QtWidgets.QGroupBox("倍镜系数", content)
        sg_layout = QtWidgets.QHBoxLayout(sens_group)
        sg_layout.setContentsMargins(6, 2, 6, 2)
        self.SensitivitySelect = QtWidgets.QComboBox(sens_group)
        for s in ["无", "红点", "全息", "2倍", "3倍", "4倍", "6倍", "8倍", "15倍", "多倍低", "多倍高",
                  "红点(Shift)", "全息(Shift)", "2倍(Shift)", "3倍(Shift)", "4倍(Shift)",
                  "多倍低(Shift)", "多倍高(Shift)", "6倍(Shift)", "8倍(Shift)", "15倍(Shift)"]:
            self.SensitivitySelect.addItem(s)
        sg_layout.addWidget(self.SensitivitySelect, 1)
        self.SensitivityText = QtWidgets.QLineEdit(sens_group)
        sg_layout.addWidget(self.SensitivityText, 1)
        self.SensitivityBtn = QtWidgets.QPushButton("保存", sens_group)
        sg_layout.addWidget(self.SensitivityBtn, 1)
        param_row.addWidget(sens_group)

        content_layout.addLayout(param_row)

        # ═══ 高级参数 ═══
        adv_row = QtWidgets.QHBoxLayout()
        adv_row.setSpacing(6)

        # 姿态系数
        posture_group = QtWidgets.QGroupBox("姿态系数", content)
        pg_layout = QtWidgets.QHBoxLayout(posture_group)
        pg_layout.setContentsMargins(6, 2, 6, 2)
        self.PostureSelect = QtWidgets.QComboBox(posture_group)
        self.PostureSelect.addItem("蹲下")
        self.PostureSelect.addItem("趴下")
        pg_layout.addWidget(self.PostureSelect, 1)
        self.PostureText = QtWidgets.QLineEdit(posture_group)
        pg_layout.addWidget(self.PostureText, 1)
        self.PostureBtn = QtWidgets.QPushButton("保存", posture_group)
        pg_layout.addWidget(self.PostureBtn, 1)
        adv_row.addWidget(posture_group)

        # 枪械系数
        gun_ratio_group = QtWidgets.QGroupBox("枪械系数", content)
        gr_layout = QtWidgets.QHBoxLayout(gun_ratio_group)
        gr_layout.setContentsMargins(6, 2, 6, 2)
        self.GunRatioSelect = QtWidgets.QComboBox(gun_ratio_group)
        gr_layout.addWidget(self.GunRatioSelect, 2)
        self.GunRatioText = QtWidgets.QLineEdit(gun_ratio_group)
        gr_layout.addWidget(self.GunRatioText, 1)
        self.GunRatioBtn = QtWidgets.QPushButton("保存", gun_ratio_group)
        gr_layout.addWidget(self.GunRatioBtn, 1)
        adv_row.addWidget(gun_ratio_group)

        content_layout.addLayout(adv_row)

        # ═══ 日志区 ═══
        log_group = QtWidgets.QGroupBox("日志", content)
        log_layout = QtWidgets.QVBoxLayout(log_group)
        log_layout.setContentsMargins(4, 4, 4, 4)
        self.Info = QtWidgets.QTextEdit(log_group)
        self.Info.setReadOnly(True)
        # 移除最大高度限制，让日志框可以自适应拉伸
        # self.Info.setMaximumHeight(100)  # 已注释，允许自由拉伸
        self.Info.setMinimumHeight(80)  # 设置最小高度
        log_layout.addWidget(self.Info)
        content_layout.addWidget(log_group, 1)  # 添加 stretch=1，让日志区可以拉伸

        # ═══ 底部按钮 ═══
        btn_row = QtWidgets.QHBoxLayout()
        btn_row.setSpacing(8)

        self.StatusInfo = QtWidgets.QLineEdit(content)
        self.StatusInfo.setObjectName("StatusInfo")
        self.StatusInfo.setReadOnly(True)
        self.StatusInfo.setText("未启动...")
        btn_row.addWidget(self.StatusInfo, 3)

        self.DebugModeBtn = QtWidgets.QPushButton("调试: 关", content)
        self.DebugModeBtn.setToolTip("与 F9 相同：全量 DEBUG + INPUT_TRACE + 开镜姿势存图 logs/posture_debug/")
        btn_row.addWidget(self.DebugModeBtn, 1)

        self.Startbtn = QtWidgets.QPushButton("启动", content)
        self.Startbtn.setObjectName("Startbtn")
        btn_row.addWidget(self.Startbtn, 1)

        self.Pausebtn = QtWidgets.QPushButton("暂停", content)
        self.Pausebtn.setEnabled(False)
        btn_row.addWidget(self.Pausebtn, 1)

        self.Stopbtn = QtWidgets.QPushButton("退出", content)
        self.Stopbtn.setObjectName("Stopbtn")
        self.Stopbtn.setEnabled(False)
        btn_row.addWidget(self.Stopbtn, 1)

        content_layout.addLayout(btn_row)

        main_layout.addWidget(content, 1)

    # ── 枪械信息组构建 ──

    def _build_gun_group(self, parent, title, idx):
        group = QtWidgets.QGroupBox(title, parent)
        layout = QtWidgets.QGridLayout(group)
        layout.setContentsMargins(6, 6, 6, 4)
        layout.setVerticalSpacing(2)
        layout.setHorizontalSpacing(4)

        labels = [
            ("名称", "gun-name"),
            ("枪口", "accessory-muzzle"),
            ("倍镜", "accessory-scope"),
            ("握把", "accessory-grip"),
            ("枪托", "accessory-stock"),
        ]
        attrs = ["Name", "Muzzle", "Scope", "Grip", "Butt"]

        for row, ((text, css_class), attr) in enumerate(zip(labels, attrs)):
            lbl = QtWidgets.QLabel(f"{text}:", group)
            lbl.setAlignment(QtCore.Qt.AlignRight | QtCore.Qt.AlignVCenter)
            layout.addWidget(lbl, row, 0)

            val = QtWidgets.QLabel("", group)
            val.setProperty("class", css_class)
            val.setStyleSheet(self._accessory_style(css_class))
            layout.addWidget(val, row, 1)

            setattr(self, f"{attr}{idx}Lable" if attr != "Butt" else f"{attr}{idx}Label", lbl)
            setattr(self, f"{attr}{idx}Name", val)

        layout.setColumnStretch(0, 1)
        layout.setColumnStretch(1, 3)
        return group

    @staticmethod
    def _accessory_style(css_class):
        colors = {
            "gun-name": "#ffba08",
            "accessory-scope": "#ff4444",
            "accessory-muzzle": "#4ae04a",
            "accessory-grip": "#e0a040",
            "accessory-stock": "#4a9eff",
        }
        c = colors.get(css_class, "#c0c0d0")
        weight = "bold" if css_class == "gun-name" else "normal"
        size = "11pt" if css_class == "gun-name" else "10pt"
        return f"color: {c}; font-weight: {weight}; font-size: {size};"
