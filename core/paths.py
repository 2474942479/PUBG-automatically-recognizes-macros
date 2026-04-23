"""统一路径解析 — 兼容开发模式和 Nuitka 编译后。"""
import os
import sys


def get_base_dir():
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


BASE_DIR = get_base_dir()


def res_path(*parts):
    """拼接资源路径。如 res_path('Config', 'config.json')"""
    return os.path.join(BASE_DIR, *parts)
