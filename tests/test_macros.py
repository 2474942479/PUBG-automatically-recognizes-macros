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
