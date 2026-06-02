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
