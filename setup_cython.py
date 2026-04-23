"""
Cython 预编译脚本 — 将核心 Python 模块编译为 .pyd (Windows DLL)

使用方式:
    python setup_cython.py build_ext --inplace

编译完成后，同目录下会生成 .pyd 文件 (如 process.cp311-win_amd64.pyd)，
Python 导入时会优先加载 .pyd 而非 .py，从而实现源码保护。

前置依赖:
    pip install cython
    需要 C 编译器 (Visual Studio Build Tools 2019+)
"""

from setuptools import setup, Extension
from Cython.Build import cythonize
import numpy as np

CORE_MODULES = [
    Extension(
        "core.process",
        sources=["core/process.py"],
        include_dirs=[np.get_include()],
    ),
    Extension(
        "core.recognition",
        sources=["core/recognition.py"],
        include_dirs=[np.get_include()],
    ),
    Extension(
        "data.fire_data",
        sources=["data/fire_data.py"],
    ),
]

setup(
    name="pubg_macro_core",
    ext_modules=cythonize(
        CORE_MODULES,
        compiler_directives={
            "language_level": "3",
            "boundscheck": False,
            "wraparound": False,
        },
    ),
)
