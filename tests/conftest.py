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

    def mouse_down(self, key=1):
        self.calls.append(("mouse_down", int(key)))

    def mouse_up(self, key=1):
        self.calls.append(("mouse_up", int(key)))


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
