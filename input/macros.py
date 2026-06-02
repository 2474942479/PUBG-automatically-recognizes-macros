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
        self.gh.key_down(primary)
        self._held_keys.add(primary)
        self._sleep(self.peek_hold_ms / 1000.0)

        self.gh.key_down(mirror)
        self._sleep(self.reverse_tap_ms / 1000.0)
        self.gh.key_up(mirror)

        self.gh.key_up(primary)
        self._held_keys.discard(primary)

        self._sleep(self.cooldown_ms / 1000.0)

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

        self._sleep(self.startup_delay_ms / 1000.0)
        count = 0
        while count < self.max_iterations and should_continue():
            self.gh.key_down("c")
            self._held_keys.add("c")
            self._sleep(self.crouch_hold_ms / 1000.0)
            self.gh.key_up("c")
            self._held_keys.discard("c")
            count += 1
            if count >= self.max_iterations:
                logger.warning("滑步循环达上限 %d，强制退出", self.max_iterations)
                break
            self._sleep(self.crouch_interval_ms / 1000.0)

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
        self._sleep(self.crouch_delay_ms / 1000.0)
        self.gh.key_down("c")
        self._held_keys.add("c")
        self._sleep(self.crouch_hold_ms / 1000.0)
        self.gh.key_up("c")
        self._held_keys.discard("c")
        self._sleep(self.cooldown_ms / 1000.0)

    def _cleanup(self):
        if "c" in self._held_keys:
            self.gh.key_up("c")
            self._held_keys.discard("c")


class MacroDispatcher:
    """统一管理 4 个宏，处理触发匹配、全局互斥、热重载。

    - 由 listener 调 on_key_event / on_mouse_event 转发原始事件
    - 自身维护"当前按下键集合"以匹配修饰键 + 触发键的组合
    - 背包打开（PC.TabKey）或全局禁用（config.enabled=False）时一律不触发
    """

    def __init__(self, pc, gh, config):
        self.pc = pc
        self.gh = gh
        # 线程安全说明：_held_keys / _held_mouse 由 listener 主线程写入，
        # should_continue lambda 在宏子线程中读取。Python GIL 保证单条字节码原子性，
        # set.add/discard/__contains__ 均为原子操作，因此无需额外加锁。
        self._held_keys = set()
        self._held_mouse = set()
        self._macros = {}  # 先初始化，供 reload_config 中 _any_macro_running 使用
        self.reload_config(config)

    def reload_config(self, config):
        """热重载配置。如有宏正在运行则拒绝重载，避免新实例与旧实例并发。"""
        if self._any_macro_running():
            logger.warning("有宏正在运行中，跳过配置热重载")
            return False
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
        return True

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

        注：直接调用时 key 也会被加入 self._held_keys（set add 幂等）。
        """
        self._held_keys.add(key)
        if self._any_macro_running():
            return None

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

        if self._is_enabled("slide_step"):
            combo = self._config["slide_step"]["combo_keys"]
            if key in combo and all(k in self._held_keys for k in combo):
                m = self._macros["slide_step"]
                m.trigger(should_continue=lambda: all(k in self._held_keys for k in combo))
                return "slide_step"

        if self._is_enabled("big_jump"):
            combo = self._config["big_jump"]["combo_keys"]
            if key in combo and all(k in self._held_keys for k in combo):
                self._macros["big_jump"].trigger()
                return "big_jump"

        return None

    def _handle_mouse_down(self, button):
        """鼠标键按下：仅更新状态，不直接触发宏（宏触发都在键盘 key_down 路径）。"""
        return None
