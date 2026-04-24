"""
输入/识别路径 [INPUT_TRACE]：与 F9 总开关、config「debug_mode」一致（另含全量 DEBUG、姿势调试图等）。
"""
import logging

_logger = logging.getLogger("input_trace")


def is_enabled():
    try:
        from core import process
        inst = getattr(process.ProcessClass, "_instance", None)
        return inst is not None and bool(getattr(inst, "debug_input_trace", False))
    except Exception:
        return False


def log(msg, *args):
    if not is_enabled():
        return
    try:
        if args:
            _logger.info("[INPUT_TRACE] " + (msg % args))
        else:
            _logger.info("[INPUT_TRACE] " + str(msg))
    except Exception:
        pass
