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


# ═══════════════════════════════════════════════════════════════
# QuickPeekMacro
# ═══════════════════════════════════════════════════════════════
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
    assert fake_sleep.durations == [0.3, 0.01, 0.05, 0.1]


def test_quick_peek_with_ads_delay(gh, fake_sleep):
    """ads_wait_ms>0 时先按右键，等待后再按 Q。"""
    macro = QuickPeekMacro(
        gh=gh, sleep_fn=fake_sleep,
        ads_wait_ms=100, peek_hold_ms=300, release_delay_ms=50, cooldown_ms=100,
    )
    macro._execute(primary="q", mirror="e")

    assert gh.calls[0] == ("mouse_down", 2)
    assert gh.calls[1] == ("key_down", "q")
    assert fake_sleep.durations[0] == 0.1


def test_quick_peek_mirror_e(gh, fake_sleep):
    """primary=e 时 mirror 应为 q。"""
    macro = QuickPeekMacro(gh=gh, sleep_fn=fake_sleep, ads_wait_ms=0, peek_hold_ms=300)
    macro._execute(primary="e", mirror="q")
    assert ("key_down", "e") in gh.calls
    assert ("key_down", "q") in gh.calls
    assert gh.calls.index(("key_down", "e")) < gh.calls.index(("key_down", "q"))


def test_quick_peek_cleanup_releases_all_keys(gh, fake_sleep):
    """_execute 中途异常时 cleanup 应释放所有注入的键。"""
    macro = QuickPeekMacro(gh=gh, sleep_fn=fake_sleep, ads_wait_ms=0, peek_hold_ms=300)
    macro._held_keys = {"q", "mouse_right"}
    macro._cleanup()
    assert ("key_up", "q") in gh.calls
    assert ("mouse_up", 2) in gh.calls


# ═══════════════════════════════════════════════════════════════
# PeekFakeMacro
# ═══════════════════════════════════════════════════════════════
from input.macros import PeekFakeMacro


def test_peek_fake_does_not_touch_mouse(gh, fake_sleep):
    """Q 弹反：用户已开镜，宏不应注入或释放右键。"""
    macro = PeekFakeMacro(
        gh=gh, sleep_fn=fake_sleep,
        peek_hold_ms=120, reverse_tap_ms=10, cooldown_ms=100,
    )
    macro._execute(primary="q", mirror="e")

    mouse_calls = [c for c in gh.calls if c[0] in ("mouse_down", "mouse_up")]
    assert mouse_calls == []


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


# ═══════════════════════════════════════════════════════════════
# SlideStepMacro
# ═══════════════════════════════════════════════════════════════
from input.macros import SlideStepMacro


def test_slide_step_loop_runs_until_should_continue_returns_false(gh, fake_sleep):
    """循环：startup_delay → (key_down c, sleep, key_up c, sleep) × N。"""
    iterations = [0]

    def cont():
        iterations[0] += 1
        return iterations[0] <= 3

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
    assert fake_sleep.durations == [0.2, 0.05, 0.3, 0.05, 0.3, 0.05, 0.3]


def test_slide_step_immediate_stop_skips_loop(gh, fake_sleep):
    """should_continue 立刻返回 False，循环不执行。"""
    macro = SlideStepMacro(
        gh=gh, sleep_fn=fake_sleep,
        startup_delay_ms=200, crouch_hold_ms=50, crouch_interval_ms=300,
    )
    macro._execute(should_continue=lambda: False)
    assert gh.calls == []
    assert fake_sleep.durations == [0.2]


def test_slide_step_max_loop_safety(gh, fake_sleep):
    """超过 max_iterations 兜底退出。"""
    macro = SlideStepMacro(
        gh=gh, sleep_fn=fake_sleep,
        startup_delay_ms=0, crouch_hold_ms=10, crouch_interval_ms=10,
        max_iterations=5,
    )
    macro._execute(should_continue=lambda: True)
    crouch_downs = [c for c in gh.calls if c == ("key_down", "c")]
    assert len(crouch_downs) == 5


# ═══════════════════════════════════════════════════════════════
# BigJumpMacro
# ═══════════════════════════════════════════════════════════════
from input.macros import BigJumpMacro


def test_big_jump_only_taps_crouch_after_delay(gh, fake_sleep):
    """大跳：不注入 Space（用户自己按）；延迟后注入 C tap。"""
    macro = BigJumpMacro(
        gh=gh, sleep_fn=fake_sleep,
        crouch_delay_ms=180, crouch_hold_ms=80, cooldown_ms=300,
    )
    macro._execute()

    assert gh.calls == [("key_down", "c"), ("key_up", "c")]
    assert fake_sleep.durations == [0.18, 0.08, 0.3]


def test_big_jump_does_not_inject_space(gh, fake_sleep):
    macro = BigJumpMacro(gh=gh, sleep_fn=fake_sleep)
    macro._execute()
    space_calls = [c for c in gh.calls if c[1] == "space"]
    assert space_calls == []
