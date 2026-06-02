# PUBG 战术按键宏系统 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 实现 4 个战术按键宏（闪身/Q弹反/滑步/大跳）+ UI 配置面板，按 spec 文档 `docs/superpowers/specs/2026-06-02-pubg-macros-design.md` 中定义的状态机时序与配置 schema。

**Architecture:** 新建 `input/macros.py` 统一管理宏状态机，通过 `ghub_device` 注入键鼠事件；`MacroDispatcher` 持 4 个宏实例并执行全局互斥；listener 仅在末尾各加一行转发；UI 在齿轮菜单加 `MacroConfigDialog`，热重载到 dispatcher。

**Tech Stack:** Python 3.10+ / PyQt5 / pynput / keyboard / pytest（新增）/ GHUB DLL（已存在）

**Spec 偏离说明：** spec 写的是"MacroDispatcher 单例 + `.instance()` 访问"。为了可测试性，本计划使用**常规类**：`main.py` 创建一个实例并挂到 `PC.macro_dispatcher`，listener 通过 `self.PC.macro_dispatcher` 访问。语义等价、不影响外部行为。

---

## File Structure

| 文件 | 责任 | 大小估计 |
| --- | --- | --- |
| `tests/conftest.py` (新) | 提供 `FakeGhubDevice`、`FakeSleep` fixture | ~50 行 |
| `tests/test_macros.py` (新) | 4 个宏 + Dispatcher 单测 | ~250 行 |
| `input/macros.py` (新) | `BaseMacro` + 4 个宏 + `MacroDispatcher` | ~350 行 |
| `core/process.py` (改) | `DEFAULT_CONFIG` 加 `macros`、`get_config_data('macros')`、`save_config_data('macros', dict)` | +25 行 |
| `input/key_listener.py` (改) | F7 hotkey + dispatcher 转发（在 on_key_pressed/release 末尾） | +12 行 |
| `input/mouse_listener.py` (改) | dispatcher 转发（在 on_button_click 末尾） | +5 行 |
| `ui/pubg_ui.py` (改) | 齿轮菜单加 `actionMacroConfig` | +2 行 |
| `main.py` (改) | 创建 dispatcher、连接 F7 信号、`open_macro_config()` 槽 | +30 行 |
| `ui/macro_config_dialog.py` (新) | `MacroConfigDialog` + `HotkeyCaptureLineEdit` | ~400 行 |
| `requirements.txt` (改) | 加 `pytest>=7` | +1 行 |

---

## Task 1: 测试基础设施

**Files:**
- Create: `tests/__init__.py`
- Create: `tests/conftest.py`
- Modify: `requirements.txt`（追加 `pytest>=7.4`）

- [ ] **Step 1: 添加 pytest 到开发依赖**

修改 `requirements.txt`，在末尾追加一行：
```
pytest>=7.4
```

- [ ] **Step 2: 安装 pytest**

```bash
pip install "pytest>=7.4"
```
预期：成功安装。

- [ ] **Step 3: 创建 tests 目录和 __init__.py**

```bash
mkdir -p tests
touch tests/__init__.py
```

- [ ] **Step 4: 写 conftest.py**

```python
# tests/conftest.py
"""共享 fixture：用于宏单测的假 ghub_device 与假 sleep。"""
import pytest


class FakeGhubDevice:
    """记录所有 key/mouse 调用，不真正注入。"""
    def __init__(self):
        self.calls = []

    def key_down(self, key):
        self.calls.append(("key_down", key))

    def key_up(self, key):
        self.calls.append(("key_up", key))

    def mouse_down(self, btn=1):
        self.calls.append(("mouse_down", int(btn)))

    def mouse_up(self, btn=1):
        self.calls.append(("mouse_up", int(btn)))


class FakeSleep:
    """记录每次 sleep 的秒数，立即返回。"""
    def __init__(self):
        self.durations = []

    def __call__(self, seconds):
        self.durations.append(seconds)


@pytest.fixture
def gh():
    return FakeGhubDevice()


@pytest.fixture
def fake_sleep():
    return FakeSleep()
```

- [ ] **Step 5: 运行 pytest 验证空收集成功**

```bash
pytest tests/ -v
```
预期：`no tests ran` 或 `collected 0 items`，无错误。

- [ ] **Step 6: 提交**

```bash
git add requirements.txt tests/__init__.py tests/conftest.py
git commit -m "test: 加入 pytest + 宏单测 fixture"
```

---

## Task 2: BaseMacro 抽象基类

**Files:**
- Create: `input/macros.py`
- Test: `tests/test_macros.py`

- [ ] **Step 1: 写 BaseMacro 的失败测试**

```python
# tests/test_macros.py
"""4 个宏 + Dispatcher 的单测。"""
from input.macros import BaseMacro


class _DummyMacro(BaseMacro):
    name = "dummy"

    def _execute(self, *args, **kwargs):
        self.gh.key_down("x")
        self._sleep(0.05)
        self.gh.key_up("x")


def test_basemacro_executes_synchronously(gh, fake_sleep):
    """_execute 直接调用应记录所有 gh 调用与 sleep。"""
    macro = _DummyMacro(gh=gh, sleep_fn=fake_sleep)
    macro._execute()
    assert gh.calls == [("key_down", "x"), ("key_up", "x")]
    assert fake_sleep.durations == [0.05]


def test_basemacro_running_flag(gh, fake_sleep):
    """trigger 后 is_running 应为 True，结束后为 False。"""
    import time
    macro = _DummyMacro(gh=gh, sleep_fn=fake_sleep)
    assert not macro.is_running()
    started = macro.trigger()
    assert started is True
    # 等线程结束（sleep_fn 是 fake，应当极快）
    for _ in range(100):
        if not macro.is_running():
            break
        time.sleep(0.01)
    assert not macro.is_running()


def test_basemacro_rejects_concurrent_trigger(gh):
    """已在运行时再次 trigger 应返回 False。"""
    import threading
    started_event = threading.Event()
    finish_event = threading.Event()

    class _BlockingMacro(BaseMacro):
        name = "blocking"

        def _execute(self):
            started_event.set()
            finish_event.wait(2)

    macro = _BlockingMacro(gh=gh)
    assert macro.trigger() is True
    started_event.wait(1)
    assert macro.trigger() is False  # 第二次被拒绝
    finish_event.set()
```

- [ ] **Step 2: 运行测试确认失败**

```bash
pytest tests/test_macros.py -v
```
预期：FAIL（`ModuleNotFoundError: No module named 'input.macros'`）。

- [ ] **Step 3: 实现 BaseMacro**

```python
# input/macros.py
"""战术按键宏：闪身、Q 弹反、滑步、大跳。

所有宏的键鼠注入都通过 ghub_device，状态机执行用 threading.Thread。
对外接口：MacroDispatcher.on_key_event() / on_mouse_event()，由 listener 转发。
"""
import logging
import threading
import time

logger = logging.getLogger(__name__)


class BaseMacro:
    """宏基类：统一 trigger（防重入）、_execute（子类实现）、_cleanup（异常清理）。

    子类可注入 sleep_fn 用于测试（替换 time.sleep 为 no-op fake）。
    """

    name = ""  # 子类覆盖，用于日志和 dispatcher 识别

    def __init__(self, gh, sleep_fn=time.sleep):
        self.gh = gh
        self._sleep = sleep_fn
        self._state_lock = threading.Lock()
        self._running = False

    def is_running(self):
        return self._running

    def trigger(self, *args, **kwargs):
        """启动宏。已在运行时返回 False，否则在新线程跑 _execute 并返回 True。"""
        with self._state_lock:
            if self._running:
                logger.debug("%s: 已在运行中，忽略触发", self.name)
                return False
            self._running = True

        def _wrap():
            try:
                self._execute(*args, **kwargs)
            except Exception as e:
                logger.error("%s 执行异常: %s", self.name, e, exc_info=True)
            finally:
                try:
                    self._cleanup()
                except Exception as e:
                    logger.error("%s 清理异常: %s", self.name, e, exc_info=True)
                self._running = False

        threading.Thread(target=_wrap, daemon=True, name=f"macro-{self.name}").start()
        return True

    def _execute(self, *args, **kwargs):
        raise NotImplementedError

    def _cleanup(self):
        """异常清理钩子：子类覆盖以确保所有 key_down 都有匹配 key_up。"""
        pass
```

- [ ] **Step 4: 运行测试验证通过**

```bash
pytest tests/test_macros.py -v
```
预期：3 PASS。

- [ ] **Step 5: 提交**

```bash
git add input/macros.py tests/test_macros.py
git commit -m "feat(macros): BaseMacro 抽象基类与防重入 trigger"
```

---

## Task 3: QuickPeekMacro（闪身宏）

**Files:**
- Modify: `input/macros.py`
- Test: `tests/test_macros.py`

- [ ] **Step 1: 写 QuickPeekMacro 的失败测试**

追加到 `tests/test_macros.py`：

```python
from input.macros import QuickPeekMacro


def test_quick_peek_simultaneous_keys(gh, fake_sleep):
    """ads_wait_ms=0 时 Q 与右键同时按下；时序符合 spec §2 ①。"""
    macro = QuickPeekMacro(
        gh=gh, sleep_fn=fake_sleep,
        ads_wait_ms=0, peek_hold_ms=300, release_delay_ms=50, cooldown_ms=100,
    )
    macro._execute(primary="q", mirror="e")

    assert gh.calls == [
        ("key_down", "q"), ("mouse_down", 2),
        ("key_down", "e"), ("key_up", "e"),
        ("key_up", "q"),
        ("mouse_up", 2),
    ]
    # 时序：peek_hold 0.3 → reverse_tap 默认 0.01 → release_delay 0.05 → cooldown 0.1
    assert fake_sleep.durations == [0.3, 0.01, 0.05, 0.1]


def test_quick_peek_with_ads_delay(gh, fake_sleep):
    """ads_wait_ms>0 时先按右键，等待后再按 Q。"""
    macro = QuickPeekMacro(
        gh=gh, sleep_fn=fake_sleep,
        ads_wait_ms=100, peek_hold_ms=300, release_delay_ms=50, cooldown_ms=100,
    )
    macro._execute(primary="q", mirror="e")

    assert gh.calls[:3] == [
        ("mouse_down", 2),
        ("key_down", "q"),
        # ↑ 这两个之间有 ads_wait 的 sleep
    ] or gh.calls[:2] == [("mouse_down", 2), ("key_down", "q")]
    # 第一个 sleep 是 ads_wait
    assert fake_sleep.durations[0] == 0.1


def test_quick_peek_mirror_e(gh, fake_sleep):
    """primary=e 时 mirror 应为 q。"""
    macro = QuickPeekMacro(gh=gh, sleep_fn=fake_sleep, ads_wait_ms=0, peek_hold_ms=300)
    macro._execute(primary="e", mirror="q")
    # 关键：探头键是 e，反向 tap 是 q
    assert ("key_down", "e") in gh.calls
    assert ("key_down", "q") in gh.calls
    # e 在 q 之前
    assert gh.calls.index(("key_down", "e")) < gh.calls.index(("key_down", "q"))


def test_quick_peek_cleanup_releases_all_keys(gh, fake_sleep):
    """_execute 中途异常时 cleanup 应释放所有注入的键。"""
    macro = QuickPeekMacro(gh=gh, sleep_fn=fake_sleep, ads_wait_ms=0, peek_hold_ms=300)
    macro._held_keys = {"q", "mouse_right"}  # 模拟注入了但未释放
    macro._cleanup()
    assert ("key_up", "q") in gh.calls
    assert ("mouse_up", 2) in gh.calls
```

- [ ] **Step 2: 运行测试确认失败**

```bash
pytest tests/test_macros.py::test_quick_peek_simultaneous_keys -v
```
预期：FAIL（`ImportError: cannot import name 'QuickPeekMacro'`）。

- [ ] **Step 3: 实现 QuickPeekMacro**

追加到 `input/macros.py`：

```python
class QuickPeekMacro(BaseMacro):
    """闪身宏：侧键(X1) + Q/E 触发 → 自动 ADS + 探头 + 反向取消。

    时序（默认 ads_wait_ms=0，即同时按下）：
      t=0       key_down(primary) + mouse_down(2)
      t=peek_hold key_down(mirror); sleep(reverse_tap_ms); key_up(mirror)
                key_up(primary)
      t=peek_hold+release_delay mouse_up(2)
      t=peek_hold+release_delay+cooldown 结束
    """

    name = "quick_peek"

    def __init__(self, gh, sleep_fn=time.sleep,
                 ads_wait_ms=0, peek_hold_ms=300, release_delay_ms=50,
                 reverse_tap_ms=10, cooldown_ms=100):
        super().__init__(gh, sleep_fn)
        self.ads_wait_ms = ads_wait_ms
        self.peek_hold_ms = peek_hold_ms
        self.release_delay_ms = release_delay_ms
        self.reverse_tap_ms = reverse_tap_ms
        self.cooldown_ms = cooldown_ms
        self._held_keys = set()  # 记录注入但未释放的键，用于 cleanup

    def _execute(self, primary="q", mirror="e"):
        try:
            if self.ads_wait_ms > 0:
                self.gh.mouse_down(2)
                self._held_keys.add("mouse_right")
                self._sleep(self.ads_wait_ms / 1000.0)
                self.gh.key_down(primary)
                self._held_keys.add(primary)
            else:
                self.gh.key_down(primary)
                self._held_keys.add(primary)
                self.gh.mouse_down(2)
                self._held_keys.add("mouse_right")

            self._sleep(self.peek_hold_ms / 1000.0)

            self.gh.key_down(mirror)
            self._sleep(self.reverse_tap_ms / 1000.0)
            self.gh.key_up(mirror)

            self.gh.key_up(primary)
            self._held_keys.discard(primary)

            self._sleep(self.release_delay_ms / 1000.0)
            self.gh.mouse_up(2)
            self._held_keys.discard("mouse_right")

            self._sleep(self.cooldown_ms / 1000.0)
        finally:
            # 正常路径已 discard 完，此处仅在异常时兜底
            self._cleanup()

    def _cleanup(self):
        # 异常或被中止时确保释放
        if "mouse_right" in self._held_keys:
            self.gh.mouse_up(2)
            self._held_keys.discard("mouse_right")
        for key in list(self._held_keys):
            self.gh.key_up(key)
            self._held_keys.discard(key)
```

- [ ] **Step 4: 运行测试验证通过**

```bash
pytest tests/test_macros.py -v
```
预期：所有测试 PASS（含之前的 BaseMacro 测试）。

- [ ] **Step 5: 提交**

```bash
git add input/macros.py tests/test_macros.py
git commit -m "feat(macros): 闪身宏 QuickPeekMacro 状态机"
```

---

## Task 4: PeekFakeMacro（Q 弹反）

**Files:**
- Modify: `input/macros.py`
- Test: `tests/test_macros.py`

- [ ] **Step 1: 写测试**

追加：

```python
from input.macros import PeekFakeMacro


def test_peek_fake_does_not_touch_mouse(gh, fake_sleep):
    """Q 弹反：用户已开镜，宏不应注入或释放右键。"""
    macro = PeekFakeMacro(
        gh=gh, sleep_fn=fake_sleep,
        peek_hold_ms=120, reverse_tap_ms=10, cooldown_ms=100,
    )
    macro._execute(primary="q", mirror="e")

    mouse_calls = [c for c in gh.calls if c[0] in ("mouse_down", "mouse_up")]
    assert mouse_calls == []  # 不碰右键


def test_peek_fake_sequence(gh, fake_sleep):
    macro = PeekFakeMacro(
        gh=gh, sleep_fn=fake_sleep,
        peek_hold_ms=120, reverse_tap_ms=10, cooldown_ms=100,
    )
    macro._execute(primary="q", mirror="e")

    assert gh.calls == [
        ("key_down", "q"),
        ("key_down", "e"), ("key_up", "e"),
        ("key_up", "q"),
    ]
    assert fake_sleep.durations == [0.12, 0.01, 0.1]
```

- [ ] **Step 2: 运行测试确认失败**

```bash
pytest tests/test_macros.py -v -k peek_fake
```
预期：FAIL（`ImportError`）。

- [ ] **Step 3: 实现**

追加到 `input/macros.py`：

```python
class PeekFakeMacro(BaseMacro):
    """Q 弹反：用户右键已按住开镜中 + Q/E → 探头 + 反向取消，不开枪不释放右键。"""

    name = "peek_fake"

    def __init__(self, gh, sleep_fn=time.sleep,
                 peek_hold_ms=120, reverse_tap_ms=10, cooldown_ms=100):
        super().__init__(gh, sleep_fn)
        self.peek_hold_ms = peek_hold_ms
        self.reverse_tap_ms = reverse_tap_ms
        self.cooldown_ms = cooldown_ms
        self._held_keys = set()

    def _execute(self, primary="q", mirror="e"):
        try:
            self.gh.key_down(primary)
            self._held_keys.add(primary)
            self._sleep(self.peek_hold_ms / 1000.0)

            self.gh.key_down(mirror)
            self._sleep(self.reverse_tap_ms / 1000.0)
            self.gh.key_up(mirror)

            self.gh.key_up(primary)
            self._held_keys.discard(primary)

            self._sleep(self.cooldown_ms / 1000.0)
        finally:
            self._cleanup()

    def _cleanup(self):
        for key in list(self._held_keys):
            self.gh.key_up(key)
            self._held_keys.discard(key)
```

- [ ] **Step 4: 运行测试验证通过**

```bash
pytest tests/test_macros.py -v
```
预期：所有 PASS。

- [ ] **Step 5: 提交**

```bash
git add input/macros.py tests/test_macros.py
git commit -m "feat(macros): Q 弹反 PeekFakeMacro 状态机"
```

---

## Task 5: SlideStepMacro（滑步循环）

**Files:**
- Modify: `input/macros.py`
- Test: `tests/test_macros.py`

- [ ] **Step 1: 写测试**

追加：

```python
from input.macros import SlideStepMacro


def test_slide_step_loop_runs_until_should_continue_returns_false(gh, fake_sleep):
    """循环：startup_delay → (key_down c, sleep, key_up c, sleep) × N。"""
    iterations = [0]

    def cont():
        iterations[0] += 1
        return iterations[0] <= 3  # 跑 3 个完整循环

    macro = SlideStepMacro(
        gh=gh, sleep_fn=fake_sleep,
        startup_delay_ms=200, crouch_hold_ms=50, crouch_interval_ms=300,
    )
    macro._execute(should_continue=cont)

    expected_gh = [
        ("key_down", "c"), ("key_up", "c"),
        ("key_down", "c"), ("key_up", "c"),
        ("key_down", "c"), ("key_up", "c"),
    ]
    assert gh.calls == expected_gh
    # 启动延迟 200ms + 3 × (50ms hold + 300ms interval)
    assert fake_sleep.durations == [0.2, 0.05, 0.3, 0.05, 0.3, 0.05, 0.3]


def test_slide_step_immediate_stop_skips_loop(gh, fake_sleep):
    """should_continue 立刻返回 False，循环不执行。"""
    macro = SlideStepMacro(
        gh=gh, sleep_fn=fake_sleep,
        startup_delay_ms=200, crouch_hold_ms=50, crouch_interval_ms=300,
    )
    macro._execute(should_continue=lambda: False)
    assert gh.calls == []
    # 启动延迟仍执行一次
    assert fake_sleep.durations == [0.2]


def test_slide_step_max_loop_safety(gh, fake_sleep):
    """超过 30 秒（real time）兜底退出 — 这里用大 max_iterations 验证不会无限循环。"""
    macro = SlideStepMacro(
        gh=gh, sleep_fn=fake_sleep,
        startup_delay_ms=0, crouch_hold_ms=10, crouch_interval_ms=10,
        max_iterations=5,  # 测试专用兜底
    )
    macro._execute(should_continue=lambda: True)
    # 5 次循环 = 10 个 c 键调用
    crouch_downs = [c for c in gh.calls if c == ("key_down", "c")]
    assert len(crouch_downs) == 5
```

- [ ] **Step 2: 运行测试确认失败**

```bash
pytest tests/test_macros.py -v -k slide_step
```
预期：FAIL。

- [ ] **Step 3: 实现**

追加到 `input/macros.py`：

```python
class SlideStepMacro(BaseMacro):
    """滑步循环：Shift+W 同时按下并保持 → 循环 C tap 直到任一键释放。"""

    name = "slide_step"

    def __init__(self, gh, sleep_fn=time.sleep,
                 startup_delay_ms=200, crouch_hold_ms=50, crouch_interval_ms=300,
                 max_iterations=200):
        super().__init__(gh, sleep_fn)
        self.startup_delay_ms = startup_delay_ms
        self.crouch_hold_ms = crouch_hold_ms
        self.crouch_interval_ms = crouch_interval_ms
        self.max_iterations = max_iterations  # 兜底：30 秒在 300ms 间隔下约 100 次
        self._held_keys = set()

    def _execute(self, should_continue=None):
        if should_continue is None:
            should_continue = lambda: True

        try:
            self._sleep(self.startup_delay_ms / 1000.0)
            count = 0
            while count < self.max_iterations and should_continue():
                self.gh.key_down("c")
                self._held_keys.add("c")
                self._sleep(self.crouch_hold_ms / 1000.0)
                self.gh.key_up("c")
                self._held_keys.discard("c")
                if count + 1 >= self.max_iterations:
                    logger.warning("滑步循环达上限 %d，强制退出", self.max_iterations)
                    break
                self._sleep(self.crouch_interval_ms / 1000.0)
                count += 1
        finally:
            self._cleanup()

    def _cleanup(self):
        if "c" in self._held_keys:
            self.gh.key_up("c")
            self._held_keys.discard("c")
```

- [ ] **Step 4: 运行测试验证通过**

```bash
pytest tests/test_macros.py -v
```
预期：所有 PASS。

- [ ] **Step 5: 提交**

```bash
git add input/macros.py tests/test_macros.py
git commit -m "feat(macros): 滑步循环 SlideStepMacro 状态机"
```

---

## Task 6: BigJumpMacro（大跳）

**Files:**
- Modify: `input/macros.py`
- Test: `tests/test_macros.py`

- [ ] **Step 1: 写测试**

追加：

```python
from input.macros import BigJumpMacro


def test_big_jump_only_taps_crouch_after_delay(gh, fake_sleep):
    """大跳：不注入 Space（用户自己按）；延迟后注入 C tap。"""
    macro = BigJumpMacro(
        gh=gh, sleep_fn=fake_sleep,
        crouch_delay_ms=180, crouch_hold_ms=80, cooldown_ms=300,
    )
    macro._execute()

    assert gh.calls == [("key_down", "c"), ("key_up", "c")]
    # 第一个 sleep 是 crouch_delay；第二个是 hold；第三个是 cooldown
    assert fake_sleep.durations == [0.18, 0.08, 0.3]


def test_big_jump_does_not_inject_space(gh, fake_sleep):
    macro = BigJumpMacro(gh=gh, sleep_fn=fake_sleep)
    macro._execute()
    space_calls = [c for c in gh.calls if c[1] == "space"]
    assert space_calls == []
```

- [ ] **Step 2: 运行测试确认失败**

```bash
pytest tests/test_macros.py -v -k big_jump
```
预期：FAIL。

- [ ] **Step 3: 实现**

追加到 `input/macros.py`：

```python
class BigJumpMacro(BaseMacro):
    """大跳：Shift+Space 触发 → 延迟后注入一次 C tap，让人物空中蹲。

    注意：不注入 Space，让用户原本的 Space 自然到达游戏。
    """

    name = "big_jump"

    def __init__(self, gh, sleep_fn=time.sleep,
                 crouch_delay_ms=180, crouch_hold_ms=80, cooldown_ms=300):
        super().__init__(gh, sleep_fn)
        self.crouch_delay_ms = crouch_delay_ms
        self.crouch_hold_ms = crouch_hold_ms
        self.cooldown_ms = cooldown_ms
        self._held_keys = set()

    def _execute(self):
        try:
            self._sleep(self.crouch_delay_ms / 1000.0)
            self.gh.key_down("c")
            self._held_keys.add("c")
            self._sleep(self.crouch_hold_ms / 1000.0)
            self.gh.key_up("c")
            self._held_keys.discard("c")
            self._sleep(self.cooldown_ms / 1000.0)
        finally:
            self._cleanup()

    def _cleanup(self):
        if "c" in self._held_keys:
            self.gh.key_up("c")
            self._held_keys.discard("c")
```

- [ ] **Step 4: 运行测试验证通过**

```bash
pytest tests/test_macros.py -v
```
预期：所有 PASS。

- [ ] **Step 5: 提交**

```bash
git add input/macros.py tests/test_macros.py
git commit -m "feat(macros): 大跳 BigJumpMacro 状态机"
```

---

## Task 7: MacroDispatcher（互斥 + 路由）

**Files:**
- Modify: `input/macros.py`
- Test: `tests/test_macros.py`

- [ ] **Step 1: 写 Dispatcher 测试**

追加：

```python
from input.macros import MacroDispatcher


class _FakePC:
    def __init__(self, tab_open=False):
        self.TabKey = tab_open


def _default_macros_config():
    return {
        "enabled": True,
        "quick_peek": {
            "enabled": True, "modifier": "mouse_x1",
            "primary_key": "q", "mirror_key": "e",
            "ads_wait_ms": 0, "peek_hold_ms": 300,
            "release_delay_ms": 50, "cooldown_ms": 100,
        },
        "peek_fake": {
            "enabled": True, "modifier": "mouse_right",
            "primary_key": "q", "mirror_key": "e",
            "peek_hold_ms": 120, "reverse_tap_ms": 10, "cooldown_ms": 100,
        },
        "slide_step": {
            "enabled": True, "combo_keys": ["shift", "w"],
            "startup_delay_ms": 200, "crouch_hold_ms": 50,
            "crouch_interval_ms": 300,
        },
        "big_jump": {
            "enabled": True, "combo_keys": ["shift", "space"],
            "crouch_delay_ms": 180, "crouch_hold_ms": 80,
            "cooldown_ms": 300,
        },
    }


def test_dispatcher_quick_peek_triggers_when_modifier_held(gh):
    pc = _FakePC()
    disp = MacroDispatcher(pc=pc, gh=gh, config=_default_macros_config())
    # 先按下 X1
    disp.on_mouse_event("mouse_x1", pressed=True)
    # 触发 Q
    fired = disp._handle_key_down("q")
    assert fired == "quick_peek"


def test_dispatcher_peek_fake_when_right_held_and_q_pressed(gh):
    pc = _FakePC()
    disp = MacroDispatcher(pc=pc, gh=gh, config=_default_macros_config())
    disp.on_mouse_event("mouse_right", pressed=True)
    fired = disp._handle_key_down("q")
    assert fired == "peek_fake"


def test_dispatcher_slide_step_when_shift_w_both_held(gh):
    pc = _FakePC()
    disp = MacroDispatcher(pc=pc, gh=gh, config=_default_macros_config())
    disp.on_key_event("shift", "down")
    fired = disp._handle_key_down("w")
    assert fired == "slide_step"


def test_dispatcher_disabled_when_tab_open(gh):
    pc = _FakePC(tab_open=True)
    disp = MacroDispatcher(pc=pc, gh=gh, config=_default_macros_config())
    disp.on_mouse_event("mouse_x1", pressed=True)
    fired = disp._handle_key_down("q")
    assert fired is None


def test_dispatcher_global_mutex(gh):
    """一个宏运行中时，第二个触发被忽略。"""
    import threading
    pc = _FakePC()
    cfg = _default_macros_config()
    cfg["quick_peek"]["peek_hold_ms"] = 50
    disp = MacroDispatcher(pc=pc, gh=gh, config=cfg)
    # 模拟阻塞：替换 sleep_fn 让它真的等
    block = threading.Event()
    for m in disp._macros.values():
        m._sleep = lambda s: block.wait(2)

    disp.on_mouse_event("mouse_x1", pressed=True)
    first = disp._handle_key_down("q")
    assert first == "quick_peek"
    # 等线程进入阻塞 sleep
    import time as _t
    _t.sleep(0.05)
    # 此时再次触发任何宏都应被全局互斥拒绝
    disp.on_mouse_event("mouse_right", pressed=True)
    second = disp._handle_key_down("q")
    assert second is None
    block.set()


def test_dispatcher_modifier_e_uses_mirror_q(gh):
    pc = _FakePC()
    disp = MacroDispatcher(pc=pc, gh=gh, config=_default_macros_config())
    disp.on_mouse_event("mouse_x1", pressed=True)
    fired = disp._handle_key_down("e")
    assert fired == "quick_peek"


def test_dispatcher_normalizes_modifier_key_variants(gh):
    """keyboard 库报 ctrl_l/alt_r/right shift 时应被规范化。"""
    pc = _FakePC()
    cfg = _default_macros_config()
    cfg["slide_step"]["combo_keys"] = ["ctrl", "w"]  # 改用 ctrl 作为组合键
    disp = MacroDispatcher(pc=pc, gh=gh, config=cfg)

    disp.on_key_event("ctrl_l", "down")  # keyboard 库的左 Ctrl 名
    fired = disp._handle_key_down("w")
    assert fired == "slide_step"
```

- [ ] **Step 2: 运行测试确认失败**

```bash
pytest tests/test_macros.py -v -k dispatcher
```
预期：FAIL（`ImportError`）。

- [ ] **Step 3: 实现 MacroDispatcher**

追加到 `input/macros.py`：

```python
class MacroDispatcher:
    """统一管理 4 个宏，处理触发匹配、全局互斥、热重载。

    - 由 listener 调 on_key_event / on_mouse_event 转发原始事件
    - 自身维护"当前按下键集合"以匹配修饰键 + 触发键的组合
    - 背包打开（PC.TabKey）或全局禁用（config.enabled=False）时一律不触发
    """

    def __init__(self, pc, gh, config):
        self.pc = pc
        self.gh = gh
        self._held_keys = set()       # 当前按下的键盘键
        self._held_mouse = set()      # 当前按下的鼠标键 (mouse_left/right/x1/x2)
        self.reload_config(config)

    def reload_config(self, config):
        self._config = config or {}
        self._macros = {}
        qp = self._config.get("quick_peek", {})
        if qp:
            self._macros["quick_peek"] = QuickPeekMacro(
                gh=self.gh,
                ads_wait_ms=qp.get("ads_wait_ms", 0),
                peek_hold_ms=qp.get("peek_hold_ms", 300),
                release_delay_ms=qp.get("release_delay_ms", 50),
                reverse_tap_ms=qp.get("reverse_tap_ms", 10),
                cooldown_ms=qp.get("cooldown_ms", 100),
            )
        pf = self._config.get("peek_fake", {})
        if pf:
            self._macros["peek_fake"] = PeekFakeMacro(
                gh=self.gh,
                peek_hold_ms=pf.get("peek_hold_ms", 120),
                reverse_tap_ms=pf.get("reverse_tap_ms", 10),
                cooldown_ms=pf.get("cooldown_ms", 100),
            )
        ss = self._config.get("slide_step", {})
        if ss:
            self._macros["slide_step"] = SlideStepMacro(
                gh=self.gh,
                startup_delay_ms=ss.get("startup_delay_ms", 200),
                crouch_hold_ms=ss.get("crouch_hold_ms", 50),
                crouch_interval_ms=ss.get("crouch_interval_ms", 300),
            )
        bj = self._config.get("big_jump", {})
        if bj:
            self._macros["big_jump"] = BigJumpMacro(
                gh=self.gh,
                crouch_delay_ms=bj.get("crouch_delay_ms", 180),
                crouch_hold_ms=bj.get("crouch_hold_ms", 80),
                cooldown_ms=bj.get("cooldown_ms", 300),
            )

    # ─── 状态跟踪：listener 转发 ───
    @staticmethod
    def _normalize_key(key):
        """规范化 keyboard 库的修饰键变体（ctrl_l/ctrl_r → ctrl 等）。"""
        k = (key or "").lower()
        if k in ("ctrl_l", "ctrl_r"):
            return "ctrl"
        if k in ("alt_l", "alt_r"):
            return "alt"
        if k in ("shift_l", "shift_r", "right shift", "left shift"):
            return "shift"
        return k

    def on_key_event(self, key, event_type):
        key = self._normalize_key(key)
        if event_type == "down":
            self._held_keys.add(key)
            self._handle_key_down(key)
        elif event_type == "up":
            self._held_keys.discard(key)

    def on_mouse_event(self, button, pressed):
        if pressed:
            self._held_mouse.add(button)
            self._handle_mouse_down(button)
        else:
            self._held_mouse.discard(button)

    # ─── 触发匹配 ───
    def _is_enabled(self, name):
        if not self._config.get("enabled", False):
            return False
        if getattr(self.pc, "TabKey", False):
            return False
        sub = self._config.get(name, {})
        return bool(sub.get("enabled", False))

    def _any_macro_running(self):
        return any(m.is_running() for m in self._macros.values())

    def _handle_key_down(self, key):
        """键按下事件：检查是否匹配某个宏的触发条件。返回触发的宏 name 或 None。

        注：直接调用时 key 也会被加入 self._held_keys（set add 幂等，
        on_key_event 已 add 过的情况下再加一次没副作用）。
        """
        self._held_keys.add(key)
        if self._any_macro_running():
            return None

        # ① 闪身宏：modifier 是鼠标键且当前按下，且 key 等于 primary 或 mirror
        if self._is_enabled("quick_peek"):
            qp_cfg = self._config["quick_peek"]
            if qp_cfg["modifier"] in self._held_mouse:
                primary = qp_cfg["primary_key"]
                mirror = qp_cfg.get("mirror_key") or ""
                if key == primary:
                    self._macros["quick_peek"].trigger(primary=primary, mirror=mirror or primary)
                    return "quick_peek"
                if mirror and key == mirror:
                    self._macros["quick_peek"].trigger(primary=mirror, mirror=primary)
                    return "quick_peek"

        # ② Q 弹反：modifier 是 mouse_right 且当前按下
        if self._is_enabled("peek_fake"):
            pf_cfg = self._config["peek_fake"]
            if pf_cfg["modifier"] in self._held_mouse:
                primary = pf_cfg["primary_key"]
                mirror = pf_cfg.get("mirror_key") or ""
                if key == primary:
                    self._macros["peek_fake"].trigger(primary=primary, mirror=mirror or primary)
                    return "peek_fake"
                if mirror and key == mirror:
                    self._macros["peek_fake"].trigger(primary=mirror, mirror=primary)
                    return "peek_fake"

        # ③ 滑步：组合键全部按下，且当前按下的 key 是组合中的最后一个
        if self._is_enabled("slide_step"):
            combo = self._config["slide_step"]["combo_keys"]
            if key in combo and all(k in self._held_keys for k in combo):
                m = self._macros["slide_step"]
                # should_continue: 当组合键不再全部按下时停止
                m.trigger(should_continue=lambda: all(k in self._held_keys for k in combo))
                return "slide_step"

        # ④ 大跳：同滑步逻辑
        if self._is_enabled("big_jump"):
            combo = self._config["big_jump"]["combo_keys"]
            if key in combo and all(k in self._held_keys for k in combo):
                self._macros["big_jump"].trigger()
                return "big_jump"

        return None

    def _handle_mouse_down(self, button):
        """鼠标键按下：仅更新状态，不直接触发宏（宏触发都在键盘 key_down 路径）。"""
        return None
```

- [ ] **Step 4: 运行所有测试验证通过**

```bash
pytest tests/test_macros.py -v
```
预期：所有 PASS（包括之前的宏测试）。

- [ ] **Step 5: 提交**

```bash
git add input/macros.py tests/test_macros.py
git commit -m "feat(macros): MacroDispatcher 互斥与触发路由"
```

---

## Task 8: ProcessClass 配置读写

**Files:**
- Modify: `core/process.py`

- [ ] **Step 1: 修改 DEFAULT_CONFIG**

把 `core/process.py` 第 18-24 行：

```python
DEFAULT_CONFIG = {
    "resolution": "1920x1080",
    "scope_factor_v3": {},
    "posture_v3": {},
    "gun_ratio_v3": {},
    "debug_mode": False,
}
```

改为：

```python
DEFAULT_MACROS_CONFIG = {
    "enabled": True,
    "quick_peek": {
        "enabled": True, "modifier": "mouse_x1",
        "primary_key": "q", "mirror_key": "e",
        "ads_wait_ms": 0, "peek_hold_ms": 300,
        "release_delay_ms": 50, "reverse_tap_ms": 10, "cooldown_ms": 100,
    },
    "peek_fake": {
        "enabled": True, "modifier": "mouse_right",
        "primary_key": "q", "mirror_key": "e",
        "peek_hold_ms": 120, "reverse_tap_ms": 10, "cooldown_ms": 100,
    },
    "slide_step": {
        "enabled": True, "combo_keys": ["shift", "w"],
        "startup_delay_ms": 200, "crouch_hold_ms": 50, "crouch_interval_ms": 300,
    },
    "big_jump": {
        "enabled": True, "combo_keys": ["shift", "space"],
        "crouch_delay_ms": 180, "crouch_hold_ms": 80, "cooldown_ms": 300,
    },
}

DEFAULT_CONFIG = {
    "resolution": "1920x1080",
    "scope_factor_v3": {},
    "posture_v3": {},
    "gun_ratio_v3": {},
    "debug_mode": False,
    "macros": DEFAULT_MACROS_CONFIG,
}


def build_macros_config(raw):
    """合并磁盘配置与默认值。Pure function，便于单元测试。

    缺失的子块/字段一律由 DEFAULT_MACROS_CONFIG 补齐。
    """
    if not isinstance(raw, dict):
        raw = {}
    merged = {**DEFAULT_MACROS_CONFIG, **raw}
    for sub_name in ("quick_peek", "peek_fake", "slide_step", "big_jump"):
        merged[sub_name] = {
            **DEFAULT_MACROS_CONFIG[sub_name],
            **(raw.get(sub_name) or {}),
        }
    return merged
```

- [ ] **Step 2: 在 get_config_data 增加 'macros' 模式**

在 `core/process.py` 第 138-142 行（`elif mode == 'engine':` 上方）添加：

```python
        elif mode == 'macros':
            return build_macros_config(Config_data.get('macros'))
```

- [ ] **Step 3: 在 save_config_data 增加 'macros' 模式**

在 `core/process.py` 第 156-158 行（`elif mode == 'engine':` 下方）添加：

```python
        elif mode == 'macros':
            if isinstance(data, dict):
                save_data['macros'] = data
```

- [ ] **Step 4: 写测试验证 build_macros_config**

追加到 `tests/test_macros.py`：

```python
def test_build_macros_config_returns_defaults_when_empty():
    from core.process import build_macros_config, DEFAULT_MACROS_CONFIG
    assert build_macros_config(None) == DEFAULT_MACROS_CONFIG
    assert build_macros_config({}) == DEFAULT_MACROS_CONFIG


def test_build_macros_config_overlays_partial_config():
    from core.process import build_macros_config
    raw = {"enabled": False, "quick_peek": {"peek_hold_ms": 999}}
    merged = build_macros_config(raw)
    assert merged["enabled"] is False
    # 覆盖的字段
    assert merged["quick_peek"]["peek_hold_ms"] == 999
    # 未覆盖的字段来自默认
    assert merged["quick_peek"]["primary_key"] == "q"
    assert merged["slide_step"]["combo_keys"] == ["shift", "w"]
```

- [ ] **Step 5: 运行测试**

```bash
pytest tests/test_macros.py -v -k macros_config
```
预期：PASS。

- [ ] **Step 6: 提交**

```bash
git add core/process.py tests/test_macros.py
git commit -m "feat(macros): ProcessClass 加载/保存 macros 配置块"
```

---

## Task 9: 创建 Dispatcher 实例并接到 Listener

**Files:**
- Modify: `core/process.py`（构造 dispatcher）
- Modify: `input/key_listener.py`（转发 + F7 信号）
- Modify: `input/mouse_listener.py`（转发）
- Modify: `main.py`（连接信号）
- Modify: `ui/pubg_ui.py`（菜单项）

- [ ] **Step 1: 在 ProcessClass.__init__ 末尾创建 dispatcher**

在 `core/process.py` `__init__` 方法末尾（第 110 行 `self._TAB_FAIL_THRESHOLD = 2` 下方）添加：

```python
        # ═══ 战术按键宏 ═══
        from input.macros import MacroDispatcher
        self.macros_config = self.get_config_data('macros')
        self.macro_dispatcher = MacroDispatcher(pc=self, gh=self._gd, config=self.macros_config)
```

- [ ] **Step 2: 在 key_listener 转发事件**

修改 `input/key_listener.py`：

在 `on_key_pressed` 方法末尾（return / 函数结束前），所有现有 `elif Keys ...` 之后追加：

```python
        # ═══ 转发给宏 dispatcher ═══
        try:
            self.PC.macro_dispatcher.on_key_event(Keys, "down")
        except AttributeError:
            pass  # 启动早期 dispatcher 还未就绪
```

在 `on_key_release` 末尾追加：

```python
        try:
            self.PC.macro_dispatcher.on_key_event(Keys, "up")
        except AttributeError:
            pass
```

也在 `AppMainKeyListener` 类顶部信号区添加：

```python
    macro_config_requested = pyqtSignal()  # 定义信号，用于打开宏配置
```

并在 `on_key_pressed` 中处理 F7（参考现有 F8 处理，第 106-114 行）：

```python
        elif Keys == "f7":
            self.macro_config_requested.emit()
```

把这段加到 `elif Keys == "f8":` 上方。

- [ ] **Step 3: 在 mouse_listener 转发事件**

修改 `input/mouse_listener.py`，在 `on_button_click` 方法末尾（`except Exception as e:` 之前）追加：

```python
            # ═══ 转发给宏 dispatcher ═══
            try:
                btn_name = {
                    mouse.Button.left: "mouse_left",
                    mouse.Button.right: "mouse_right",
                    mouse.Button.x1: "mouse_x1",
                    mouse.Button.x2: "mouse_x2",
                }.get(button)
                if btn_name:
                    self.PC.macro_dispatcher.on_mouse_event(btn_name, pressed)
            except AttributeError:
                pass
```

- [ ] **Step 4: 在 ui/pubg_ui.py 加菜单项**

在 `pubg_ui.py` 第 333 行（`self.actionBatchTemplate = ...` 下方）添加：

```python
        self.actionMacroConfig = self.ToolsMenu.addAction("宏配置 (F7)")
```

- [ ] **Step 5: 在 main.py 连接信号**

在 `main.py` 第 355-356 行（`self.actionROIConfig.triggered.connect...`）下方添加：

```python
        self.actionMacroConfig.triggered.connect(self.open_macro_config)  # 宏配置
```

在 `main.py` 第 652-653 行下方添加：

```python
        self.my_key_thread.macro_config_requested.connect(self.open_macro_config)  # F7
```

并在 `MainWindow` / 主类中添加方法（在 `open_roi_config` 方法附近）：

```python
    def open_macro_config(self):
        """打开宏配置对话框。"""
        from ui.macro_config_dialog import MacroConfigDialog
        dlg = MacroConfigDialog(self.PC, parent=self)
        dlg.exec_()
```

- [ ] **Step 6: 手动验证：启动程序，按 F7，应在终端日志看到错误（dialog 还未实现），但 dispatcher 已加载**

```bash
python main.py
```

按 F7。预期：弹出 import error 或 ModuleNotFoundError 提示 `ui.macro_config_dialog`。其他功能正常。

- [ ] **Step 7: 提交**

```bash
git add core/process.py input/key_listener.py input/mouse_listener.py main.py ui/pubg_ui.py
git commit -m "feat(macros): listener 转发事件给 MacroDispatcher、F7 打开配置"
```

---

## Task 10: HotkeyCaptureLineEdit 控件

**Files:**
- Create: `ui/macro_config_dialog.py`（先建文件，先实现单元控件）

- [ ] **Step 1: 创建文件骨架与 HotkeyCaptureLineEdit**

```python
# ui/macro_config_dialog.py
"""宏配置对话框：编辑 4 个宏的触发键、镜像键、时序参数；保存后热重载。"""
import logging
from PyQt5 import QtCore, QtGui, QtWidgets

logger = logging.getLogger(__name__)

# 显示名 → 内部 key
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

    keyChanged = QtCore.pyqtSignal(str)  # 新 internal_key

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
        # 把 Qt 键码映射回我们的内部 key 字符串
        internal = self._qt_key_to_internal(event)
        if internal:
            self._finish_capture(internal)
        # 否则忽略

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
```

- [ ] **Step 2: 手动 smoke test：启动 Python REPL 验证导入**

```bash
python -c "from ui.macro_config_dialog import HotkeyCaptureLineEdit; print(HotkeyCaptureLineEdit)"
```
预期：打印类对象，无错误。

- [ ] **Step 3: 提交**

```bash
git add ui/macro_config_dialog.py
git commit -m "feat(ui): 新增 HotkeyCaptureLineEdit 热键捕获控件"
```

---

## Task 11: MacroConfigDialog（4 个宏的编辑面板）

**Files:**
- Modify: `ui/macro_config_dialog.py`

- [ ] **Step 1: 追加 MacroConfigDialog 类**

在 `ui/macro_config_dialog.py` 末尾追加：

```python
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

        # 4 个宏分别一组
        self.qp_box = self._make_quick_peek_group()
        self.pf_box = self._make_peek_fake_group()
        self.ss_box = self._make_slide_step_group()
        self.bj_box = self._make_big_jump_group()
        for b in (self.qp_box, self.pf_box, self.ss_box, self.bj_box):
            root.addWidget(b)

        # 按钮区
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
```

- [ ] **Step 2: 手动 smoke test**

```bash
python main.py
```

按 F7（或齿轮 → 宏配置）。预期：对话框正确弹出，4 组宏全部展示，默认值显示正确，捕获按钮可点击。

- [ ] **Step 3: 验证保存可写入 config.json**

UI 中改一个值（比如把闪身宏触发键从 `Q` 改为 `q` 同义、或冷却时间从 100 改 150），点保存。

```bash
cat Config/config.json | grep -A 3 "quick_peek"
```
预期：`cooldown_ms` 等改动已写入。

- [ ] **Step 4: 验证校验**

把闪身宏的"修饰键"和"触发键"都设成 `Q`，点保存。预期：弹错误提示，不写入。

- [ ] **Step 5: 提交**

```bash
git add ui/macro_config_dialog.py
git commit -m "feat(ui): MacroConfigDialog 4 宏配置面板与保存校验"
```

---

## Task 12: 端到端冒烟与文档

**Files:**
- 无文件改动；只做手动验证 + 一份简短的使用说明追加

- [ ] **Step 1: 完整跑一次单测**

```bash
pytest tests/ -v
```
预期：全部 PASS。

- [ ] **Step 2: macOS / Linux 启动验证（GHUB 注入是 no-op，但 dispatcher 路径要走通）**

```bash
python main.py
```

按 F7 → 弹宏配置 → 改值保存 → 关闭。
预期：无 traceback。日志中应见 `宏配置已保存并热重载`。

- [ ] **Step 3: Windows + 游戏内手动验证（玩家本人在 Windows 上做）**

清单：
- 闪身宏：按住 X1 + Q → 角色应自动开镜 + 探头 300ms + 回正；左键应能在窗口期开火
- 闪身宏镜像：按住 X1 + E → 同上但向右
- Q 弹反：按住右键开镜 + 按 Q → 探头并立刻回正、不开枪
- 滑步：按住 Shift + W → 200ms 后开始连续蹲 tap；松任一键停止
- 大跳：按住 Shift + Space → 起跳后 180ms 注入 C tap

如有时序不合适，调 `Config/config.json` 的 `macros` 块对应字段。

- [ ] **Step 4: 简短记录到 README**

在 `README.md` 末尾追加（如已有"功能"段落则插到下面）：

```markdown
## 战术按键宏

通过齿轮菜单"宏配置 (F7)"可启用并自定义：
- **闪身宏**：X1 + Q/E → 自动开镜探头 + 反向取消，留 300ms 开枪窗口
- **Q 弹反**：右键开镜中 + Q/E → 快速探头回正，诱骗对手交火
- **滑步**：Shift+W 持续按下 → 自动循环 C tap 触发滑铲
- **大跳**：Shift+Space → 跳起后空中蹲，跨越较高障碍

详细时序与字段说明见 `docs/superpowers/specs/2026-06-02-pubg-macros-design.md`。
```

- [ ] **Step 5: 提交**

```bash
git add README.md
git commit -m "docs: README 加战术按键宏使用说明"
```
