"""统一路径解析 — 兼容开发模式和 Nuitka 编译后。"""
import os
import sys


def get_base_dir():
    """可执行文件所在目录（发布包在 runtime/ 下时为该目录）。"""
    if getattr(sys, "frozen", False):
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


BASE_DIR = get_base_dir()


def res_path(*parts):
    """拼接资源路径。如 res_path('Config', 'config.json')、res_path('_internal', ...)。"""
    if not parts:
        return BASE_DIR
    return os.path.join(BASE_DIR, *parts)
