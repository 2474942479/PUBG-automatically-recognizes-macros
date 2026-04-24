"""统一路径解析 — 兼容开发模式和 Nuitka 编译后。"""
import os
import sys


def get_base_dir():
    """可执行文件所在目录（发布包在 runtime/ 下时为该目录）。"""
    if getattr(sys, "frozen", False):
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _release_root_dir():
    """
    与「启动.bat」同级的发布根目录。
    当 exe 位于 .../发布包/runtime/xxx.exe 时，根目录为 runtime 的上一级；
    旧布局（exe 与 bat 同层）时与 get_base_dir() 相同。
    """
    b = get_base_dir()
    if getattr(sys, "frozen", False) and os.path.basename(b).lower() == "runtime":
        return os.path.dirname(b)
    return b


BASE_DIR = get_base_dir()


def res_path(*parts):
    """
    拼接资源路径。如 res_path('Config', 'config.json')、res_path('_internal', ...)。

    发布包分两层时：_internal 等在 runtime 下；Config、logs 在发布根（与 .bat 同级）便于用户修改。
    """
    if not parts:
        return BASE_DIR
    if parts[0] in ("Config", "logs"):
        return os.path.join(_release_root_dir(), *parts)
    return os.path.join(BASE_DIR, *parts)
