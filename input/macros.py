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
