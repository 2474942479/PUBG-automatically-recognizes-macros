from PyQt5 import QtCore, QtGui, QtWidgets
import os

class Ui_ModernPUBG(object):
    def setupUi(self, PUBG):
        PUBG.setObjectName("PUBG")
        PUBG.setWindowModality(QtCore.Qt.ApplicationModal)
        PUBG.resize(800, 600)
        icon = QtGui.QIcon()
        icon.addPixmap(QtGui.QPixmap("./_internal/GHUB.ico"), QtGui.QIcon.Normal, QtGui.QIcon.Off)
        PUBG.setWindowIcon(icon)
        PUBG.setWindowFilePath("")
        PUBG.setStyleSheet("""
            QWidget {
                font-family: 'Microsoft YaHei', 'Segoe UI', sans-serif;
                font-size: 10pt;
            }
            QTabWidget::pane {
                border: 1px solid #ddd;
                border-radius: 4px;
                padding: 5px;
            }
            QTabBar::tab {
                background-color: #f8f9fa;
                border: 1px solid #ddd;
                border-bottom: none;
                border-top-left-radius: 4px;
                border-top-right-radius: 4px;
                padding: 8px 12px;
                margin-right: 2px;
            }
            QTabBar::tab:selected {
                background-color: white;
                border-bottom: 1px solid white;
            }
            QTabBar::tab:hover:!selected {
                background-color: #e9ecef;
            }
            QGroupBox {
                border: 1px solid #ddd;
                border-radius: 4px;
                margin-top: 10px;
                padding-top: 15px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                subcontrol-position: top left;
                padding: 0 5px;
                color: #495057;
            }
            QPushButton {
                background-color: #3498db;
                color: white;
                border: none;
                border-radius: 4px;
                padding: 8px 12px;
            }
            QPushButton:hover {
                background-color: #2980b9;
            }
            QPushButton:disabled {
                background-color: #bdc3c7;
            }
            QLineEdit, QComboBox {
                border: 1px solid #ddd;
                border-radius: 4px;
                padding: 5px;
            }
            QSlider::groove:horizontal {
                border: 1px solid #bdc3c7;
                height: 6px;
                background: #e9ecef;
                margin: 0px;
                border-radius: 3px;
            }
            QSlider::handle:horizontal {
                background: #3498db;
                border: 1px solid #3498db;
                width: 18px;
                height: 18px;
                margin: -6px 0;
                border-radius: 9px;
            }
            QSlider::handle:horizontal:hover {
                background: #2980b9;
            }
            QRadioButton::indicator {
                width: 15px;
                height: 15px;
            }
            QStatusBar {
                background-color: #f8f9fa;
                color: #495057;
            }
        """)
        
        # Main layout
        self.mainLayout = QtWidgets.QVBoxLayout(PUBG)
        self.mainLayout.setContentsMargins(10, 10, 10, 10)
        self.mainLayout.setSpacing(10)
        self.mainLayout.setObjectName("mainLayout")
        
        # Status indicator
        self.statusIndicator = QtWidgets.QWidget(PUBG)
        self.statusIndicator.setMaximumHeight(40)
        self.statusIndicator.setObjectName("statusIndicator")
        self.statusLayout = QtWidgets.QHBoxLayout(self.statusIndicator)
        self.statusLayout.setContentsMargins(5, 5, 5, 5)
        self.statusLayout.setSpacing(10)
        
        self.statusDot = QtWidgets.QLabel(self.statusIndicator)
        self.statusDot.setMinimumSize(QtCore.QSize(12, 12))
        self.statusDot.setMaximumSize(QtCore.QSize(12, 12))
        self.statusDot.setStyleSheet("background-color: #e74c3c; border-radius: 6px;")
        self.statusDot.setText("")
        self.statusLayout.addWidget(self.statusDot)
        
        self.statusText = QtWidgets.QLabel(self.statusIndicator)
        self.statusText.setText("系统未运行")
        self.statusLayout.addWidget(self.statusText)
        
        self.statusLayout.addStretch()
        
        self.startBtn = QtWidgets.QPushButton(self.statusIndicator)
        self.startBtn.setText("启动")
        self.startBtn.setMinimumWidth(80)
        self.statusLayout.addWidget(self.startBtn)
        
        self.stopBtn = QtWidgets.QPushButton(self.statusIndicator)
        self.stopBtn.setText("停止")
        self.stopBtn.setEnabled(False)
        self.stopBtn.setMinimumWidth(80)
        self.stopBtn.setStyleSheet("background-color: #e74c3c;")
        self.statusLayout.addWidget(self.stopBtn)
        
        self.mainLayout.addWidget(self.statusIndicator)
        
        # Tab widget
        self.tabWidget = QtWidgets.QTabWidget(PUBG)
        self.tabWidget.setObjectName("tabWidget")
        
        # Basic settings tab
        self.basicTab = QtWidgets.QWidget()
        self.basicTab.setObjectName("basicTab")
        self.basicLayout = QtWidgets.QVBoxLayout(self.basicTab)
        
        # Resolution settings
        self.resolutionGroup = QtWidgets.QGroupBox(self.basicTab)
        self.resolutionGroup.setTitle("分辨率设置")
        self.resolutionLayout = QtWidgets.QHBoxLayout(self.resolutionGroup)
        
        self.resolutionLabel = QtWidgets.QLabel(self.resolutionGroup)
        self.resolutionLabel.setText("当前分辨率：")
        self.resolutionLayout.addWidget(self.resolutionLabel)
        
        self.resolutionSelect = QtWidgets.QComboBox(self.resolutionGroup)
        self.resolutionSelect.addItem("1920x1080")
        self.resolutionSelect.addItem("1728x1080")
        self.resolutionSelect.addItem("2560x1080")
        self.resolutionSelect.addItem("2560x1440")
        self.resolutionSelect.addItem("2560x1600")
        self.resolutionSelect.addItem("3440x1440")
        self.resolutionSelect.addItem("3840x2160")
        self.resolutionLayout.addWidget(self.resolutionSelect)
        
        self.resolutionBtn = QtWidgets.QPushButton(self.resolutionGroup)
        self.resolutionBtn.setText("保存设置")
        self.resolutionLayout.addWidget(self.resolutionBtn)
        
        self.basicLayout.addWidget(self.resolutionGroup)
        
        # Scope mode settings
        self.scopeModeGroup = QtWidgets.QGroupBox(self.basicTab)
        self.scopeModeGroup.setTitle("开镜模式")
        self.scopeModeLayout = QtWidgets.QHBoxLayout(self.scopeModeGroup)
        
        self.longPress = QtWidgets.QRadioButton(self.scopeModeGroup)
        self.longPress.setText("长按")
        self.longPress.setChecked(True)
        self.scopeModeLayout.addWidget(self.longPress)
        
        self.clickPress = QtWidgets.QRadioButton(self.scopeModeGroup)
        self.clickPress.setText("单击")
        self.scopeModeLayout.addWidget(self.clickPress)
        
        self.basicLayout.addWidget(self.scopeModeGroup)
        
        # Sensitivity settings
        self.sensitivityGroup = QtWidgets.QGroupBox(self.basicTab)
        self.sensitivityGroup.setTitle("灵敏度设置")
        self.sensitivityLayout = QtWidgets.QVBoxLayout(self.sensitivityGroup)
        
        # Base sensitivity
        self.baseSensitivityWidget = QtWidgets.QWidget(self.sensitivityGroup)
        self.baseSensitivityLayout = QtWidgets.QVBoxLayout(self.baseSensitivityWidget)
        self.baseSensitivityLayout.setContentsMargins(0, 0, 0, 0)
        
        self.baseSensitivityLabel = QtWidgets.QLabel(self.baseSensitivityWidget)
        self.baseSensitivityLabel.setText("基础灵敏度")
        self.baseSensitivityLayout.addWidget(self.baseSensitivityLabel)
        
        self.baseSensitivitySliderWidget = QtWidgets.QWidget(self.baseSensitivityWidget)
        self.baseSensitivitySliderLayout = QtWidgets.QHBoxLayout(self.baseSensitivitySliderWidget)
        self.baseSensitivitySliderLayout.setContentsMargins(0, 0, 0, 0)
        
        self.baseSensitivitySlider = QtWidgets.QSlider(self.baseSensitivitySliderWidget)
        self.baseSensitivitySlider.setOrientation(QtCore.Qt.Horizontal)
        self.baseSensitivitySlider.setMinimum(1)
        self.baseSensitivitySlider.setMaximum(100)
        self.baseSensitivitySlider.setValue(50)
        self.baseSensitivitySliderLayout.addWidget(self.baseSensitivitySlider)
        
        self.baseSensitivityValue = QtWidgets.QLabel(self.baseSensitivitySliderWidget)
        self.baseSensitivityValue.setText("50")
        self.baseSensitivityValue.setMinimumWidth(30)
        self.baseSensitivitySliderLayout.addWidget(self.baseSensitivityValue)
        
        self.baseSensitivityLayout.addWidget(self.baseSensitivitySliderWidget)
        self.sensitivityLayout.addWidget(self.baseSensitivityWidget)
        
        # Red dot sensitivity
        self.redDotSensitivityWidget = QtWidgets.QWidget(self.sensitivityGroup)
        self.redDotSensitivityLayout = QtWidgets.QVBoxLayout(self.redDotSensitivityWidget)
        self.redDotSensitivityLayout.setContentsMargins(0, 0, 0, 0)
        
        self.redDotSensitivityLabel = QtWidgets.QLabel(self.redDotSensitivityWidget)
        self.redDotSensitivityLabel.setText("红点灵敏度")
        self.redDotSensitivityLayout.addWidget(self.redDotSensitivityLabel)
        
        self.redDotSensitivitySliderWidget = QtWidgets.QWidget(self.redDotSensitivityWidget)
        self.redDotSensitivitySliderLayout = QtWidgets.QHBoxLayout(self.redDotSensitivitySliderWidget)
        self.redDotSensitivitySliderLayout.setContentsMargins(0, 0, 0, 0)
        
        self.redDotSensitivitySlider = QtWidgets.QSlider(self.redDotSensitivitySliderWidget)
        self.redDotSensitivitySlider.setOrientation(QtCore.Qt.Horizontal)
        self.redDotSensitivitySlider.setMinimum(1)
        self.redDotSensitivitySlider.setMaximum(100)
        self.redDotSensitivitySlider.setValue(40)
        self.redDotSensitivitySliderLayout.addWidget(self.redDotSensitivitySlider)
        
        self.redDotSensitivityValue = QtWidgets.QLabel(self.redDotSensitivitySliderWidget)
        self.redDotSensitivityValue.setText("40")
        self.redDotSensitivityValue.setMinimumWidth(30)
        self.redDotSensitivitySliderLayout.addWidget(self.redDotSensitivityValue)
        
        self.redDotSensitivityLayout.addWidget(self.redDotSensitivitySliderWidget)
        self.sensitivityLayout.addWidget(self.redDotSensitivityWidget)
        
        # 2x scope sensitivity
        self.scope2xSensitivityWidget = QtWidgets.QWidget(self.sensitivityGroup)
        self.scope2xSensitivityLayout = QtWidgets.QVBoxLayout(self.scope2xSensitivityWidget)
        self.scope2xSensitivityLayout.setContentsMargins(0, 0, 0, 0)
        
        self.scope2xSensitivityLabel = QtWidgets.QLabel(self.scope2xSensitivityWidget)
        self.scope2xSensitivityLabel.setText("2倍镜灵敏度")
        self.scope2xSensitivityLayout.addWidget(self.scope2xSensitivityLabel)
        
        self.scope2xSensitivitySliderWidget = QtWidgets.QWidget(self.scope2xSensitivityWidget)
        self.scope2xSensitivitySliderLayout = QtWidgets.QHBoxLayout(self.scope2xSensitivitySliderWidget)
        self.scope2xSensitivitySliderLayout.setContentsMargins(0, 0, 0, 0)
        
        self.scope2xSensitivitySlider = QtWidgets.QSlider(self.scope2xSensitivitySliderWidget)
        self.scope2xSensitivitySlider.setOrientation(QtCore.Qt.Horizontal)
        self.scope2xSensitivitySlider.setMinimum(1)
        self.scope2xSensitivitySlider.setMaximum(100)
        self.scope2xSensitivitySlider.setValue(30)
        self.scope2xSensitivitySliderLayout.addWidget(self.scope2xSensitivitySlider)
        
        self.scope2xSensitivityValue = QtWidgets.QLabel(self.scope2xSensitivitySliderWidget)
        self.scope2xSensitivityValue.setText("30")
        self.scope2xSensitivityValue.setMinimumWidth(30)
        self.scope2xSensitivitySliderLayout.addWidget(self.scope2xSensitivityValue)
        
        self.scope2xSensitivityLayout.addWidget(self.scope2xSensitivitySliderWidget)
        self.sensitivityLayout.addWidget(self.scope2xSensitivityWidget)
        
        # 4x scope sensitivity
        self.scope4xSensitivityWidget = QtWidgets.QWidget(self.sensitivityGroup)
        self.scope4xSensitivityLayout = QtWidgets.QVBoxLayout(self.scope4xSensitivityWidget)
        self.scope4xSensitivityLayout.setContentsMargins(0, 0, 0, 0)
        
        self.scope4xSensitivityLabel = QtWidgets.QLabel(self.scope4xSensitivityWidget)
        self.scope4xSensitivityLabel.setText("4倍镜灵敏度")
        self.scope4xSensitivityLayout.addWidget(self.scope4xSensitivityLabel)
        
        self.scope4xSensitivitySliderWidget = QtWidgets.QWidget(self.scope4xSensitivityWidget)
        self.scope4xSensitivitySliderLayout = QtWidgets.QHBoxLayout(self.scope4xSensitivitySliderWidget)
        self.scope4xSensitivitySliderLayout.setContentsMargins(0, 0, 0, 0)
        
        self.scope4xSensitivitySlider = QtWidgets.QSlider(self.scope4xSensitivitySliderWidget)
        self.scope4xSensitivitySlider.setOrientation(QtCore.Qt.Horizontal)
        self.scope4xSensitivitySlider.setMinimum(1)
        self.scope4xSensitivitySlider.setMaximum(100)
        self.scope4xSensitivitySlider.setValue(20)
        self.scope4xSensitivitySliderLayout.addWidget(self.scope4xSensitivitySlider)
        
        self.scope4xSensitivityValue = QtWidgets.QLabel(self.scope4xSensitivitySliderWidget)
        self.scope4xSensitivityValue.setText("20")
        self.scope4xSensitivityValue.setMinimumWidth(30)
        self.scope4xSensitivitySliderLayout.addWidget(self.scope4xSensitivityValue)
        
        self.scope4xSensitivityLayout.addWidget(self.scope4xSensitivitySliderWidget)
        self.sensitivityLayout.addWidget(self.scope4xSensitivityWidget)
        
        # Save sensitivity button
        self.saveSensitivityBtn = QtWidgets.QPushButton(self.sensitivityGroup)
        self.saveSensitivityBtn.setText("保存灵敏度设置")
        self.sensitivityLayout.addWidget(self.saveSensitivityBtn)
        
        self.basicLayout.addWidget(self.sensitivityGroup)
        
        # Config management
        self.configGroup = QtWidgets.QGroupBox(self.basicTab)
        self.configGroup.setTitle("配置文件管理")
        self.configLayout = QtWidgets.QVBoxLayout(self.configGroup)
        
        # Config list
        self.configListWidget = QtWidgets.QListWidget(self.configGroup)
        self.configListWidget.setMaximumHeight(120)
        self.configListWidget.addItem("默认配置")
        self.configListWidget.addItem("竞技模式")
        self.configListWidget.addItem("休闲模式")
        self.configLayout.addWidget(self.configListWidget)
        
        # Config actions
        self.configActionsWidget = QtWidgets.QWidget(self.configGroup)
        self.configActionsLayout = QtWidgets.QHBoxLayout(self.configActionsWidget)
        self.configActionsLayout.setContentsMargins(0, 0, 0, 0)
        
        self.loadConfigBtn = QtWidgets.QPushButton(self.configActionsWidget)
        self.loadConfigBtn.setText("加载配置")
        self.configActionsLayout.addWidget(self.loadConfigBtn)
        
        self.deleteConfigBtn = QtWidgets.QPushButton(self.configActionsWidget)
        self.deleteConfigBtn.setText("删除配置")
        self.deleteConfigBtn.setStyleSheet("background-color: #e74c3c;")
        self.configActionsLayout.addWidget(self.deleteConfigBtn)
        
        self.configLayout.addWidget(self.configActionsWidget)
        
        # New config
        self.newConfigWidget = QtWidgets.QWidget(self.configGroup)
        self.newConfigLayout = QtWidgets.QHBoxLayout(self.newConfigWidget)
        self.newConfigLayout.setContentsMargins(0, 0, 0, 0)
        
        self.newConfigName = QtWidgets.QLineEdit(self.newConfigWidget)
        self.newConfigName.setPlaceholderText("输入新配置名称")
        self.newConfigLayout.addWidget(self.newConfigName)
        
        self.saveConfigBtn = QtWidgets.QPushButton(self.newConfigWidget)
        self.saveConfigBtn.setText("保存为新配置")
        self.newConfigLayout.addWidget(self.saveConfigBtn)
        
        self.configLayout.addWidget(self.newConfigWidget)
        
        # Import/Export
        self.importExportWidget = QtWidgets.QWidget(self.configGroup)
        self.importExportLayout = QtWidgets.QHBoxLayout(self.importExportWidget)
        self.importExportLayout.setContentsMargins(0, 0, 0, 0)
        
        self.importConfigBtn = QtWidgets.QPushButton(self.importExportWidget)
        self.importConfigBtn.setText("导入配置")
        self.importExportLayout.addWidget(self.importConfigBtn)
        
        self.exportConfigBtn = QtWidgets.QPushButton(self.importExportWidget)
        self.exportConfigBtn.setText("导出配置")
        self.importExportLayout.addWidget(self.exportConfigBtn)
        
        self.configLayout.addWidget(self.importExportWidget)
        
        self.basicLayout.addWidget(self.configGroup)
        
        # Add basic tab to tab widget
        self.tabWidget.addTab(self.basicTab, "基本设置")
        
        # Weapon recognition tab
        self.weaponTab = QtWidgets.QWidget()
        self.weaponTab.setObjectName("weaponTab")
        self.weaponLayout = QtWidgets.QVBoxLayout(self.weaponTab)
        
        # Weapon recognition
        self.weaponRecognitionGroup = QtWidgets.QGroupBox(self.weaponTab)
        self.weaponRecognitionGroup.setTitle("枪械识别")
        self.weaponRecognitionLayout = QtWidgets.QHBoxLayout(self.weaponRecognitionGroup)
        
        # First weapon
        self.firstWeaponGroup = QtWidgets.QGroupBox(self.weaponRecognitionGroup)
        self.firstWeaponGroup.setTitle("一号枪")
        self.firstWeaponLayout = QtWidgets.QVBoxLayout(self.firstWeaponGroup)
        
        self.firstWeaponNameWidget = QtWidgets.QWidget(self.firstWeaponGroup)
        self.firstWeaponNameLayout = QtWidgets.QHBoxLayout(self.firstWeaponNameWidget)
        self.firstWeaponNameLayout.setContentsMargins(0, 0, 0, 0)
        
        self.firstWeaponNameLabel = QtWidgets.QLabel(self.firstWeaponNameWidget)
        self.firstWeaponNameLabel.setText("名称：")
        self.firstWeaponNameLayout.addWidget(self.firstWeaponNameLabel)
        
        self.firstWeaponName = QtWidgets.QLabel(self.firstWeaponNameWidget)
        self.firstWeaponName.setText("")
        self.firstWeaponName.setStyleSheet("color: #2c3e50; font-weight: bold;")
        self.firstWeaponNameLayout.addWidget(self.firstWeaponName)
        
        self.firstWeaponLayout.addWidget(self.firstWeaponNameWidget)
        
        self.firstWeaponMuzzleWidget = QtWidgets.QWidget(self.firstWeaponGroup)
        self.firstWeaponMuzzleLayout = QtWidgets.QHBoxLayout(self.firstWeaponMuzzleWidget)
        self.firstWeaponMuzzleLayout.setContentsMargins(0, 0, 0, 0)
        
        self.firstWeaponMuzzleLabel = QtWidgets.QLabel(self.firstWeaponMuzzleWidget)
        self.firstWeaponMuzzleLabel.setText("枪口：")
        self.firstWeaponMuzzleLayout.addWidget(self.firstWeaponMuzzleLabel)
        
        self.firstWeaponMuzzle = QtWidgets.QLabel(self.firstWeaponMuzzleWidget)
        self.firstWeaponMuzzle.setText("")
        self.firstWeaponMuzzle.setStyleSheet("color: #27ae60;")
        self.firstWeaponMuzzleLayout.addWidget(self.firstWeaponMuzzle)
        
        self.firstWeaponLayout.addWidget(self.firstWeaponMuzzleWidget)
        
        self.firstWeaponScopeWidget = QtWidgets.QWidget(self.firstWeaponGroup)
        self.firstWeaponScopeLayout = QtWidgets.QHBoxLayout(self.firstWeaponScopeWidget)
        self.firstWeaponScopeLayout.setContentsMargins(0, 0, 0, 0)
        
        self.firstWeaponScopeLabel = QtWidgets.QLabel(self.firstWeaponScopeWidget)
        self.firstWeaponScopeLabel.setText("倍镜：")
        self.firstWeaponScopeLayout.addWidget(self.firstWeaponScopeLabel)
        
        self.firstWeaponScope = QtWidgets.QLabel(self.firstWeaponScopeWidget)
        self.firstWeaponScope.setText("")
        self.firstWeaponScope.setStyleSheet("color: #e74c3c;")
        self.firstWeaponScopeLayout.addWidget(self.firstWeaponScope)
        
        self.firstWeaponLayout.addWidget(self.firstWeaponScopeWidget)
        
        self.firstWeaponGripWidget = QtWidgets.QWidget(self.firstWeaponGroup)
        self.firstWeaponGripLayout = QtWidgets.QHBoxLayout(self.firstWeaponGripWidget)
        self.firstWeaponGripLayout.setContentsMargins(0, 0, 0, 0)
        
        self.firstWeaponGripLabel = QtWidgets.QLabel(self.firstWeaponGripWidget)
        self.firstWeaponGripLabel.setText("握把：")
        self.firstWeaponGripLayout.addWidget(self.firstWeaponGripLabel)
        
        self.firstWeaponGrip = QtWidgets.QLabel(self.firstWeaponGripWidget)
        self.firstWeaponGrip.setText("")
        self.firstWeaponGrip.setStyleSheet("color: #d35400;")
        self.firstWeaponGripLayout.addWidget(self.firstWeaponGrip)
        
        self.firstWeaponLayout.addWidget(self.firstWeaponGripWidget)
        
        self.firstWeaponButtWidget = QtWidgets.QWidget(self.firstWeaponGroup)
        self.firstWeaponButtLayout = QtWidgets.QHBoxLayout(self.firstWeaponButtWidget)
        self.firstWeaponButtLayout.setContentsMargins(0, 0, 0, 0)
        
        self.firstWeaponButtLabel = QtWidgets.QLabel(self.firstWeaponButtWidget)
        self.firstWeaponButtLabel.setText("枪托：")
        self.firstWeaponButtLayout.addWidget(self.firstWeaponButtLabel)
        
        self.firstWeaponButt = QtWidgets.QLabel(self.firstWeaponButtWidget)
        self.firstWeaponButt.setText("")
        self.firstWeaponButt.setStyleSheet("color: #3498db;")
        self.firstWeaponButtLayout.addWidget(self.firstWeaponButt)
        
        self.firstWeaponLayout.addWidget(self.firstWeaponButtWidget)
        
        self.weaponRecognitionLayout.addWidget(self.firstWeaponGroup)
        
        # Second weapon
        self.secondWeaponGroup = QtWidgets.QGroupBox(self.weaponRecognitionGroup)
        self.secondWeaponGroup.setTitle("二号枪")
        self.secondWeaponLayout = QtWidgets.QVBoxLayout(self.secondWeaponGroup)
        
        self.secondWeaponNameWidget = QtWidgets.QWidget(self.secondWeaponGroup)
        self.secondWeaponNameLayout = QtWidgets.QHBoxLayout(self.secondWeaponNameWidget)
        self.secondWeaponNameLayout.setContentsMargins(0, 0, 0, 0)
        
        self.secondWeaponNameLabel = QtWidgets.QLabel(self.secondWeaponNameWidget)
        self.secondWeaponNameLabel.setText("名称：")
        self.secondWeaponNameLayout.addWidget(self.secondWeaponNameLabel)
        
        self.secondWeaponName = QtWidgets.QLabel(self.secondWeaponNameWidget)
        self.secondWeaponName.setText("")
        self.secondWeaponName.setStyleSheet("color: #2c3e50; font-weight: bold;")
        self.secondWeaponNameLayout.addWidget(self.secondWeaponName)
        
        self.secondWeaponLayout.addWidget(self.secondWeaponNameWidget)
        
        self.secondWeaponMuzzleWidget = QtWidgets.QWidget(self.secondWeaponGroup)
        self.secondWeaponMuzzleLayout = QtWidgets.QHBoxLayout(self.secondWeaponMuzzleWidget)
        self.secondWeaponMuzzleLayout.setContentsMargins(0, 0, 0, 0)
        
        self.secondWeaponMuzzleLabel = QtWidgets.QLabel(self.secondWeaponMuzzleWidget)
        self.secondWeaponMuzzleLabel.setText("枪口：")
        self.secondWeaponMuzzleLayout.addWidget(self.secondWeaponMuzzleLabel)
        
        self.secondWeaponMuzzle = QtWidgets.QLabel(self.secondWeaponMuzzleWidget)
        self.secondWeaponMuzzle.setText("")
        self.secondWeaponMuzzle.setStyleSheet("color: #27ae60;")
        self.secondWeaponMuzzleLayout.addWidget(self.secondWeaponMuzzle)
        
        self.secondWeaponLayout.addWidget(self.secondWeaponMuzzleWidget)
        
        self.secondWeaponScopeWidget = QtWidgets.QWidget(self.secondWeaponGroup)
        self.secondWeaponScopeLayout = QtWidgets.QHBoxLayout(self.secondWeaponScopeWidget)
        self.secondWeaponScopeLayout.setContentsMargins(0, 0, 0, 0)
        
        self.secondWeaponScopeLabel = QtWidgets.QLabel(self.secondWeaponScopeWidget)
        self.secondWeaponScopeLabel.setText("倍镜：")
        self.secondWeaponScopeLayout.addWidget(self.secondWeaponScopeLabel)
        
        self.secondWeaponScope = QtWidgets.QLabel(self.secondWeaponScopeWidget)
        self.secondWeaponScope.setText("")
        self.secondWeaponScope.setStyleSheet("color: #e74c3c;")
        self.secondWeaponScopeLayout.addWidget(self.secondWeaponScope)
        
        self.secondWeaponLayout.addWidget(self.secondWeaponScopeWidget)
        
        self.secondWeaponGripWidget = QtWidgets.QWidget(self.secondWeaponGroup)
        self.secondWeaponGripLayout = QtWidgets.QHBoxLayout(self.secondWeaponGripWidget)
        self.secondWeaponGripLayout.setContentsMargins(0, 0, 0, 0)
        
        self.secondWeaponGripLabel = QtWidgets.QLabel(self.secondWeaponGripWidget)
        self.secondWeaponGripLabel.setText("握把：")
        self.secondWeaponGripLayout.addWidget(self.secondWeaponGripLabel)
        
        self.secondWeaponGrip = QtWidgets.QLabel(self.secondWeaponGripWidget)
        self.secondWeaponGrip.setText("")
        self.secondWeaponGrip.setStyleSheet("color: #d35400;")
        self.secondWeaponGripLayout.addWidget(self.secondWeaponGrip)
        
        self.secondWeaponLayout.addWidget(self.secondWeaponGripWidget)
        
        self.secondWeaponButtWidget = QtWidgets.QWidget(self.secondWeaponGroup)
        self.secondWeaponButtLayout = QtWidgets.QHBoxLayout(self.secondWeaponButtWidget)
        self.secondWeaponButtLayout.setContentsMargins(0, 0, 0, 0)
        
        self.secondWeaponButtLabel = QtWidgets.QLabel(self.secondWeaponButtWidget)
        self.secondWeaponButtLabel.setText("枪托：")
        self.secondWeaponButtLayout.addWidget(self.secondWeaponButtLabel)
        
        self.secondWeaponButt = QtWidgets.QLabel(self.secondWeaponButtWidget)
        self.secondWeaponButt.setText("")
        self.secondWeaponButt.setStyleSheet("color: #3498db;")
        self.secondWeaponButtLayout.addWidget(self.secondWeaponButt)
        
        self.secondWeaponLayout.addWidget(self.secondWeaponButtWidget)
        
        self.weaponRecognitionLayout.addWidget(self.secondWeaponGroup)
        
        self.weaponLayout.addWidget(self.weaponRecognitionGroup)
        
        # Pose settings
        self.poseGroup = QtWidgets.QGroupBox(self.weaponTab)
        self.poseGroup.setTitle("姿态设置")
        self.poseLayout = QtWidgets.QHBoxLayout(self.poseGroup)
        
        self.standRadio = QtWidgets.QRadioButton(self.poseGroup)
        self.standRadio.setText("站立")
        self.standRadio.setChecked(True)
        self.poseLayout.addWidget(self.standRadio)
        
        self.squatRadio = QtWidgets.QRadioButton(self.poseGroup)
        self.squatRadio.setText("下蹲")
        self.poseLayout.addWidget(self.squatRadio)
        
        self.proneRadio = QtWidgets.QRadioButton(self.poseGroup)
        self.proneRadio.setText("趴下")
        self.poseLayout.addWidget(self.proneRadio)
        
        self.weaponLayout.addWidget(self.poseGroup)
        
        # Recoil strength adjustment
        self.recoilGroup = QtWidgets.QGroupBox(self.weaponTab)
        self.recoilGroup.setTitle("压枪强度调整")
        self.recoilLayout = QtWidgets.QVBoxLayout(self.recoilGroup)
        
        self.recoilSliderWidget = QtWidgets.QWidget(self.recoilGroup)
        self.recoilSliderLayout = QtWidgets.QHBoxLayout(self.recoilSliderWidget)
        self.recoilSliderLayout.setContentsMargins(0, 0, 0, 0)
        
        self.recoilSlider = QtWidgets.QSlider(self.recoilSliderWidget)
        self.recoilSlider.setOrientation(QtCore.Qt.Horizontal)
        self.recoilSlider.setMinimum(1)
        self.recoilSlider.setMaximum(100)
        self.recoilSlider.setValue(70)
        self.recoilSliderLayout.addWidget(self.recoilSlider)
        
        self.recoilValue = QtWidgets.QLabel(self.recoilSliderWidget)
        self.recoilValue.setText("70")
        self.recoilValue.setMinimumWidth(30)
        self.recoilSliderLayout.addWidget(self.recoilValue)
        
        self.recoilLayout.addWidget(self.recoilSliderWidget)
        
        self.applyRecoilBtn = QtWidgets.QPushButton(self.recoilGroup)
        self.applyRecoilBtn.setText("应用设置")
        self.recoilLayout.addWidget(self.applyRecoilBtn)
        
        self.weaponLayout.addWidget(self.recoilGroup)
        
        # Hotkey settings
        self.hotkeyGroup = QtWidgets.QGroupBox(self.weaponTab)
        self.hotkeyGroup.setTitle("快捷键设置")
        self.hotkeyLayout = QtWidgets.QGridLayout(self.hotkeyGroup)
        
        self.screenshotHotkeyLabel = QtWidgets.QLabel(self.hotkeyGroup)
        self.screenshotHotkeyLabel.setText("截图识别：")
        self.hotkeyLayout.addWidget(self.screenshotHotkeyLabel, 0, 0)
        
        self.screenshotHotkey = QtWidgets.QLineEdit(self.hotkeyGroup)
        self.screenshotHotkey.setText("Tab")
        self.screenshotHotkey.setReadOnly(True)
        self.hotkeyLayout.addWidget(self.screenshotHotkey, 0, 1)
        
        self.changeScreenshotHotkeyBtn = QtWidgets.QPushButton(self.hotkeyGroup)
        self.changeScreenshotHotkeyBtn.setText("更改")
        self.hotkeyLayout.addWidget(self.changeScreenshotHotkeyBtn, 0, 2)
        
        self.weapon1HotkeyLabel = QtWidgets.QLabel(self.hotkeyGroup)
        self.weapon1HotkeyLabel.setText("切换1号枪：")
        self.hotkeyLayout.addWidget(self.weapon1HotkeyLabel, 1, 0)
        
        self.weapon1Hotkey = QtWidgets.QLineEdit(self.hotkeyGroup)
        self.weapon1Hotkey.setText("1")
        self.weapon1Hotkey.setReadOnly(True)
        self.hotkeyLayout.addWidget(self.weapon1Hotkey, 1, 1)
        
        self.changeWeapon1HotkeyBtn = QtWidgets.QPushButton(self.hotkeyGroup)
        self.changeWeapon1HotkeyBtn.setText("更改")
        self.hotkeyLayout.addWidget(self.changeWeapon1HotkeyBtn, 1, 2)
        
        self.weapon2HotkeyLabel = QtWidgets.QLabel(self.hotkeyGroup)
        self.weapon2HotkeyLabel.setText("切换2号枪：")
        self.hotkeyLayout.addWidget(self.weapon2HotkeyLabel, 2, 0)
        
        self.weapon2Hotkey = QtWidgets.QLineEdit(self.hotkeyGroup)
        self.weapon2Hotkey.setText("2")
        self.weapon2Hotkey.setReadOnly(True)
        self.hotkeyLayout.addWidget(self.weapon2Hotkey, 2, 1)
        
        self.changeWeapon2HotkeyBtn = QtWidgets.QPushButton(self.hotkeyGroup)
        self.changeWeapon2HotkeyBtn.setText("更改")
        self.hotkeyLayout.addWidget(self.changeWeapon2HotkeyBtn, 2, 2)
        
        self.toggleDisplayHotkeyLabel = QtWidgets.QLabel(self.hotkeyGroup)
        self.toggleDisplayHotkeyLabel.setText("显示/隐藏游戏内信息：")
        self.hotkeyLayout.addWidget(self.toggleDisplayHotkeyLabel, 3, 0)
        
        self.toggleDisplayHotkey = QtWidgets.QLineEdit(self.hotkeyGroup)
        self.toggleDisplayHotkey.setText("F10")
        self.toggleDisplayHotkey.setReadOnly(True)
        self.hotkeyLayout.addWidget(self.toggleDisplayHotkey, 3, 1)
        
        self.changeToggleDisplayHotkeyBtn = QtWidgets.QPushButton(self.hotkeyGroup)
        self.changeToggleDisplayHotkeyBtn.setText("更改")
        self.hotkeyLayout.addWidget(self.changeToggleDisplayHotkeyBtn, 3, 2)
        
        self.weaponLayout.addWidget(self.hotkeyGroup)
        
        # Log output
        self.logGroup = QtWidgets.QGroupBox(self.weaponTab)
        self.logGroup.setTitle("日志输出")
        self.logLayout = QtWidgets.QVBoxLayout(self.logGroup)
        
        self.logOutput = QtWidgets.QTextEdit(self.logGroup)
        self.logOutput.setReadOnly(True)
        self.logOutput.setMaximumHeight(150)
        self.logLayout.addWidget(self.logOutput)
        
        self.weaponLayout.addWidget(self.logGroup)
        
        # Add weapon tab to tab widget
        self.tabWidget.addTab(self.weaponTab, "枪械识别")
        
        # Advanced settings tab
        self.advancedTab = QtWidgets.QWidget()
        self.advancedTab.setObjectName("advancedTab")
        self.tabWidget.addTab(self.advancedTab, "高级设置")
        
        # Statistics tab
        self.statsTab = QtWidgets.QWidget()
        self.statsTab.setObjectName("statsTab")
        self.tabWidget.addTab(self.statsTab, "数据统计")
        
        # Help tab
        self.helpTab = QtWidgets.QWidget()
        self.helpTab.setObjectName("helpTab")
        self.tabWidget.addTab(self.helpTab, "帮助")
        
        self.mainLayout.addWidget(self.tabWidget)
        
        # Status bar
        self.statusBar = QtWidgets.QStatusBar(PUBG)
        self.statusBar.setObjectName("statusBar")
        self.statusBar.showMessage("准备就绪")
        
        # Resource usage
        self.resourceWidget = QtWidgets.QWidget(self.statusBar)
        self.resourceLayout = QtWidgets.QHBoxLayout(self.resourceWidget)
        self.resourceLayout.setContentsMargins(0, 0, 0, 0)
        self.resourceLayout.setSpacing(15)
        
        self.cpuUsage = QtWidgets.QLabel(self.resourceWidget)
        self.cpuUsage.setText("CPU: 5%")
        self.resourceLayout.addWidget(self.cpuUsage)
        
        self.memoryUsage = QtWidgets.QLabel(self.resourceWidget)
        self.memoryUsage.setText("内存: 120MB")
        self.resourceLayout.addWidget(self.memoryUsage)
        
        self.statusBar.addPermanentWidget(self.resourceWidget)
        
        self.mainLayout.addWidget(self.statusBar)
        
        # Connect signals
        self.baseSensitivitySlider.valueChanged.connect(lambda value: self.baseSensitivityValue.setText(str(value)))
        self.redDotSensitivitySlider.valueChanged.connect(lambda value: self.redDotSensitivityValue.setText(str(value)))
        self.scope2xSensitivitySlider.valueChanged.connect(lambda value: self.scope2xSensitivityValue.setText(str(value)))
        self.scope4xSensitivitySlider.valueChanged.connect(lambda value: self.scope4xSensitivityValue.setText(str(value)))
        self.recoilSlider.valueChanged.connect(lambda value: self.recoilValue.setText(str(value)))
        
        self.startBtn.clicked.connect(self.onStartClicked)
        self.stopBtn.clicked.connect(self.onStopClicked)
        
    def onStartClicked(self):
        self.statusDot.setStyleSheet("background-color: #2ecc71; border-radius: 6px;")
        self.statusText.setText("系统运行中")
        self.startBtn.setEnabled(False)
        self.stopBtn.setEnabled(True)
        self.statusBar.showMessage("系统已启动")
        
    def onStopClicked(self):
        self.statusDot.setStyleSheet("background-color: #e74c3c; border-radius: 6px;")
        self.statusText.setText("系统未运行")
        self.startBtn.setEnabled(True)
        self.stopBtn.setEnabled(False)
        self.statusBar.showMessage("系统已停止")
