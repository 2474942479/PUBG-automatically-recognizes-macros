# 商业化发布前 — Bug 修复与优化清单

> 按优先级排序，标注 `[必修]` 的为打包前必须修复的阻塞项，`[建议]` 为体验优化项。

---

## 一、必须修复的 Bug

### 1.1 `[必修]` MSS_Img 返回值与调用方不匹配

**文件**: `core/recognition.py`

**问题**: `MSS_Img()` 函数 (第 10-24 行) 只返回 `img_gray` 一个值，但多处调用解包了两个值，运行时会抛出 `ValueError: not enough values to unpack`：

```python
# 第 146 行
prev_img_gray, _ = MSS_Img(zishi_img)  # ❌ MSS_Img 只返回一个值

# 第 190 行
initial_img_gray, _ = MSS_Img(zishi_img)  # ❌

# 第 235 行
img_gray, img_color = MSS_Img(zishi_img)  # ❌

# 第 343 行
img_gray, img_color = MSS_Img(zishi_img)  # ❌

# 第 409 行
img_gray, img_color = MSS_Img(zishi_img)  # ❌

# 第 453 行
img_gray, img_color = MSS_Img(zishi_img)  # ❌
```

**修复方案**: 修改 `MSS_Img` 返回元组 `(img_gray, img_np)`：

```python
def MSS_Img(Values):
    x1, y1, x2, y2 = Values
    with mss.mss() as sct:
        monitor = {"top": x1, "left": y1, "width": x2, "height": y2}
        img = sct.grab(monitor)
        img_np = np.array(img)
        img_gray = cv2.cvtColor(img_np, cv2.COLOR_BGR2GRAY)
    return img_gray, img_np  # 返回元组
```

---

### 1.2 `[必修]` capture_zishi_positions_thread 重复定义

**文件**: `core/recognition.py`

**问题**: `capture_zishi_positions_thread` 函数定义了两次：
- 第一次: 第 211 行 (简单版本)
- 第二次: 第 365 行 (带模板匹配的版本)

Python 中第二个定义会覆盖第一个，**第一个版本是死代码**，永远不会执行。

**修复方案**: 删除第 211-248 行的第一个版本，保留第 365 行的第二个版本（功能更完整）。

---

### 1.3 `[必修]` pyopdll 未声明依赖 — 启动即崩溃

**文件**: `core/process.py`

**问题**: 第 11 行 `from pyopdll import OP` 和第 51 行 `self.op = OP()`：
- `pyopdll` 不在 `requirements.txt` 中
- 在未安装此包的机器上直接 `ImportError` 崩溃
- **`self.op` 在整个项目中从未被调用，是死代码**

**修复方案**: 直接删除这两行：

```python
# 删除第 11 行
from pyopdll import OP  # ← 删除

# 删除第 51 行
self.op = OP()  # ← 删除
```

---

### 1.4 `[必修]` 调试截图泄露用户隐私

**文件**: `core/recognition.py`

**问题**: 多处代码在运行时将游戏截图保存到 `test/` 目录，商业发布版不应保存任何用户截图：

```python
# 第 238-242 行
if not os.path.exists('test'):
    os.makedirs('test')
debug_filename = f"test/zishi_capture_{time.time()}.png"
cv2.imwrite(debug_filename, img_color)

# 第 387-391 行 (类似)
# 第 414-416 行 (类似)
```

**修复方案**: 删除所有 `test/` 相关的截图保存代码，或改为受 `DEBUG` 环境变量控制：

```python
import logging
logger = logging.getLogger(__name__)

# 替换为:
if os.environ.get("PUBG_DEBUG"):
    if not os.path.exists('test'):
        os.makedirs('test')
    cv2.imwrite(f"test/zishi_{time.time()}.png", img_color)
```

---

## 二、架构优化 (影响打包和稳定性)

### 2.1 `[必修]` 路径解析 — 使用基于 exe 目录的绝对路径

**涉及文件**: `core/process.py`, `core/ghub.py`, `core/recognition.py`

**问题**: 全项目使用相对路径 (`./Config/config.json`, `./_internal/...`)，Nuitka 编译后如果用户从非 exe 目录启动 (如右键→发送到桌面快捷方式)，所有文件读取都会失败。

**修复方案**: 创建一个路径工具函数，所有文件引用改为调用它：

```python
# 在 core/__init__.py 或新建 core/paths.py 中:
import os
import sys

def get_base_dir():
    """获取程序根目录，兼容开发模式和 Nuitka 编译后。"""
    if getattr(sys, "frozen", False):
        # Nuitka standalone 模式
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

BASE_DIR = get_base_dir()

def res_path(*parts):
    """拼接资源路径。如 res_path('Config', 'config.json')"""
    return os.path.join(BASE_DIR, *parts)
```

需要替换的位置：

| 文件 | 行号 | 原始路径 | 替换为 |
|------|------|---------|--------|
| `core/process.py` | 62, 93 | `'./Config/config.json'` | `res_path('Config', 'config.json')` |
| `core/process.py` | 114 | `'./_internal/GunData_v2_backup/{}'` | `res_path('_internal', 'GunData_v2_backup', f'{fileName}.json')` |
| `core/process.py` | 116 | `'./_internal/GunData/{}'` | `res_path('_internal', 'GunData', f'{fileName}.json')` |
| `core/ghub.py` | 10 | `'./_internal/ghub_device_GHUB.dll'` | `res_path('_internal', 'ghub_device_GHUB.dll')` |
| `core/recognition.py` | 86 | `'_internal/data/firearms/{}'` | `res_path('_internal', 'data', 'firearms', ...)` |
| `core/recognition.py` | 263 | `'_internal/data/pose_templates/'` | `res_path('_internal', 'data', 'pose_templates')` |

---

### 2.2 `[必修]` 配置文件健壮性加固

**文件**: `core/process.py` — `get_config_data()` (第 61-77 行)

**问题**: JSON 文件损坏、不存在、或字段缺失时直接崩溃，无恢复能力。

**修复方案**:

```python
import logging
logger = logging.getLogger(__name__)

DEFAULT_CONFIG = {
    "resolution": "1920x1080",
    "recoil_version": 3,
    "sensitivity": {"none": 1, "hongdian": 1, "quanxi": 2, "2bei": 1.7,
                     "3bei": 5.5, "4bei": 11.5, "6bei": 5, "8bei": 5.7,
                     "15bei": 10, "shift": 1.5},
    "scope_factor_v3": {},
    "posture_v3": {},
    "gun_ratio_v3": {},
}

def get_config_data(self, mode='r'):
    config_path = res_path('Config', 'config.json')
    try:
        with open(config_path, "r", encoding='utf-8') as f:
            Config_data = json.loads(f.read())
    except (FileNotFoundError, json.JSONDecodeError) as e:
        logger.warning(f"配置文件读取失败，使用默认配置: {e}")
        Config_data = DEFAULT_CONFIG.copy()
        # 自动恢复
        os.makedirs(os.path.dirname(config_path), exist_ok=True)
        with open(config_path, "w", encoding='utf-8') as f:
            f.write(json.dumps(Config_data, ensure_ascii=False, indent=2))
    # ... 后续逻辑不变
```

---

### 2.3 `[建议]` print 全部替换为 logging

**涉及文件**: 全项目

**问题**: 约 50+ 处 `print()` 调用，商业版中：
- 无法分级控制输出
- 无法持久化日志
- 控制台被隐藏后信息丢失

**修复方案**: 在 `main.py` 入口配置 logging，各模块使用 `logger = logging.getLogger(__name__)`：

```python
# main.py 顶部添加:
import logging
from logging.handlers import RotatingFileHandler

def setup_logging():
    log_dir = res_path('logs')
    os.makedirs(log_dir, exist_ok=True)
    
    handler = RotatingFileHandler(
        os.path.join(log_dir, 'app.log'),
        maxBytes=5*1024*1024,  # 5MB
        backupCount=3,
        encoding='utf-8'
    )
    handler.setFormatter(logging.Formatter(
        '%(asctime)s [%(levelname)s] %(name)s: %(message)s'
    ))
    
    root = logging.getLogger()
    root.setLevel(logging.INFO)  # 发布版用 WARNING
    root.addHandler(handler)
```

然后在各文件中将 `print(...)` 替换为 `logger.info(...)` 或 `logger.debug(...)`。

---

### 2.4 `[必修]` 精简 requirements.txt

**问题**: 当前 `requirements.txt` 包含多个不必要的包：

| 包名 | 状态 | 原因 |
|------|------|------|
| `pyinstaller~=6.5.0` | 移除 | 构建工具，非运行时依赖 |
| `setuptools==68.2.2` | 移除 | 构建工具 |
| `pip~=24.0` | 移除 | 包管理器本身 |
| `pefile~=2023.2.7` | 移除 | PyInstaller 依赖 |
| `altgraph~=0.17.4` | 移除 | PyInstaller 依赖 |
| `asyncio~=3.4.3` | 移除 | Python 3 标准库 |
| `configparser~=6.0.1` | 移除 | Python 3 标准库 |
| `requests~=2.31.0` | 移除 | 项目中未使用 |
| `platformdirs~=4.2.0` | 移除 | 项目中未使用 |
| `six~=1.16.0` | 移除 | 项目中未使用 |
| `llvmlite~=0.41.1` | 移除 | 项目中未使用 |
| `MouseInfo~=0.1.3` | 移除 | pyautogui 可选依赖 |
| `packaging~=23.2` | 移除 | 项目中未使用 |

已创建精简版文件: `requirements_runtime.txt`

---

## 三、用户体验优化

### 3.1 `[建议]` 首次运行引导 — GHUB 驱动检测

**文件**: `main.py` 的 `AppManager.init_ui()`

**问题**: 驱动未安装时只在日志区显示文字 "未安装ghub或者lgs驱动!!!"，用户可能注意不到。

**修复方案**: 启动时检测 `ghub_device_info`，如果失败弹出醒目对话框：

```python
def init_ui(self):
    self.setupUi(self)
    # ... 其他初始化 ...
    
    if "失败" in PC.ghub_device_info or "缺失" in PC.ghub_device_info:
        QMessageBox.critical(
            self, "驱动检测失败",
            "未检测到罗技 G HUB 驱动！\n\n"
            "请先安装 G HUB: https://www.logitechg.com/zh-cn/innovation/g-hub.html\n"
            "安装完成后重启电脑，再运行本工具。",
            QMessageBox.Ok
        )
```

---

### 3.2 `[建议]` 自动检测屏幕分辨率

**文件**: `main.py` 的 `AppManager.init_ui()`

**问题**: 用户每次需要手动选择分辨率，容易选错。

**修复方案**:

```python
from screeninfo import get_monitors

def detect_resolution():
    """自动检测主显示器分辨率并返回匹配的配置键。"""
    try:
        monitor = get_monitors()[0]
        res_str = f"{monitor.width}x{monitor.height}"
        return res_str
    except Exception:
        return None
```

---

### 3.3 `[建议]` 全局异常处理器

**文件**: `main.py`

**问题**: 任何未处理异常都会导致程序静默崩溃 (控制台模式被隐藏后)。

**修复方案**:

```python
import traceback

def global_exception_handler(exc_type, exc_value, exc_tb):
    error_msg = ''.join(traceback.format_exception(exc_type, exc_value, exc_tb))
    logger.critical(f"未处理异常:\n{error_msg}")
    
    # 写入崩溃日志
    crash_file = res_path('logs', f'crash_{int(time.time())}.log')
    with open(crash_file, 'w', encoding='utf-8') as f:
        f.write(error_msg)
    
    # 弹出错误对话框
    msg = QMessageBox()
    msg.setIcon(QMessageBox.Critical)
    msg.setWindowTitle("程序异常")
    msg.setText("程序遇到了一个错误，即将退出。\n\n"
                f"错误日志已保存到:\n{crash_file}")
    msg.setDetailedText(error_msg)
    msg.exec_()

sys.excepthook = global_exception_handler
```

---

### 3.4 `[建议]` 添加版本号显示

**文件**: `main.py` 或 `ui/pubg_ui.py`

**问题**: 界面中没有任何版本标识，用户无法确认当前版本。

**修复方案**: 在窗口标题或界面底部添加版本号：

```python
VERSION = "1.0.0"

def init_ui(self):
    self.setupUi(self)
    self.setWindowTitle(f"PUBG 宏识别工具 v{VERSION}")
    # ...
```

---

### 3.5 `[建议]` DLL 加载失败的优雅处理

**文件**: `core/ghub.py`

**问题**: DLL 加载失败后 `gm_ok = 0`，所有 `mouse_R` 等调用静默返回 `None`，用户只看到"压枪没反应"但不知道原因。

**修复方案**: 在 `_mouse_event` 中添加明确的日志警告：

```python
def _mouse_event(self, fun, *args):
    if not self.gm_ok:
        logger.warning(f"驱动未就绪，跳过 {fun} 调用")
        return None
    # ...
```

---

## 四、代码集成提示 — GunData 加密

修复完以上问题后，在 `core/process.py` 的 `read_gun_data()` 方法中接入加密模块：

```python
# 将当前的 read_gun_data 替换为:
from crypto.gun_data_crypto import load_gun_data

def read_gun_data(self, fileName) -> dict:
    if self.recoil_version == 2:
        # v2 先尝试备份目录
        data = load_gun_data(fileName, res_path('_internal', 'GunData_v2_backup'))
        if data:
            return data
    return load_gun_data(fileName, res_path('_internal', 'GunData'))
```

构建前运行加密:
```bash
python -m crypto.gun_data_crypto encrypt
```

---

## 五、PyQt5 许可证注意

PyQt5 使用 GPL/Commercial 双许可证。如果商业闭源分发，有两个选择：
1. **购买 PyQt5 商业许可** (Riverbank Computing)
2. **迁移到 PySide6** (LGPL 许可，可免费商用) — API 几乎一致，迁移成本低

---

## 六、清单总览

| # | 类型 | 优先级 | 文件 | 描述 |
|---|------|--------|------|------|
| 1.1 | Bug | 必修 | `core/recognition.py` | MSS_Img 返回值修复 |
| 1.2 | Bug | 必修 | `core/recognition.py` | 删除重复的函数定义 |
| 1.3 | Bug | 必修 | `core/process.py` | 移除 pyopdll 死代码 |
| 1.4 | Bug | 必修 | `core/recognition.py` | 移除调试截图代码 |
| 2.1 | 架构 | 必修 | 多文件 | 路径解析改为绝对路径 |
| 2.2 | 架构 | 必修 | `core/process.py` | 配置文件健壮性 |
| 2.3 | 架构 | 建议 | 全项目 | print 替换为 logging |
| 2.4 | 架构 | 必修 | `requirements.txt` | 精简依赖列表 |
| 3.1 | 体验 | 建议 | `main.py` | GHUB 驱动检测提示 |
| 3.2 | 体验 | 建议 | `main.py` | 自动检测分辨率 |
| 3.3 | 体验 | 建议 | `main.py` | 全局异常处理器 |
| 3.4 | 体验 | 建议 | `main.py` | 版本号显示 |
| 3.5 | 体验 | 建议 | `core/ghub.py` | DLL 失败优雅处理 |
