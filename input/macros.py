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

    name = ""

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
        self._held_keys = set()

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
            self._cleanup()

    def _cleanup(self):
        if "mouse_right" in self._held_keys:
            self.gh.mouse_up(2)
            self._held_keys.discard("mouse_right")
        for key in list(self._held_keys):
            self.gh.key_up(key)
            self._held_keys.discard(key)


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
        self.max_iterations = max_iterations
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
