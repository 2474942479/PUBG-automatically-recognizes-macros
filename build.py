"""
PUBG 宏识别工具 — Nuitka 一键构建脚本

使用方式:
    python build.py              # 完整构建 (Cython预编译 + Nuitka编译 + zip打包)
    python build.py --skip-cython # 跳过Cython预编译，直接Nuitka编译
    python build.py --zip-only    # 仅打包已有构建产物为zip

前置依赖 (在构建机器上安装):
    pip install nuitka cython
    需要安装 C 编译器:
      - Windows: Visual Studio Build Tools 2019+ (勾选 "C++ 桌面开发")
      - 或 MinGW-w64 (nuitka 可自动下载)

构建产物:
    dist/PUBG宏识别工具/                 # 发布根（启动.bat、使用说明）
    dist/PUBG宏识别工具/runtime/         # exe、Config、logs、_internal、依赖（全部在一起）
    dist/PUBG宏识别工具-v{版本}.zip      # 整包 zip
"""

import os
import sys
import platform
import shutil
import subprocess
import argparse
import zipfile
from pathlib import Path

IS_WINDOWS = platform.system() == "Windows"

VERSION = "1.0.0"
APP_NAME = "PUBG_MacroTool"
ENTRY_SCRIPT = "main.py"

PROJECT_ROOT = Path(__file__).parent.resolve()
DIST_DIR = PROJECT_ROOT / "dist"
BUILD_DIR = PROJECT_ROOT / "build"
# 发布根目录：与 启动.bat 同级；可执行体在 OUTPUT_DIR / "runtime"
OUTPUT_DIR = DIST_DIR / APP_NAME
RUNTIME_DIR = OUTPUT_DIR / "runtime"

CORE_MODULES_FOR_CYTHON = [
    "core/process.py",
    "core/recognition.py",
    "data/fire_data.py"
]

EXCLUDE_MODULES = [
    "calibration",
    "tools",
]

INCLUDE_DATA_DIRS = [
    ("Config", "Config"),
    # 含 _internal/data/firearms、_internal/models(ONNX 可选) 等
    ("_internal", "_internal"),
]

# Nuitka 需要但发布包中不需要的文件（在构建后删除）
EXCLUDE_DATA_FILES = [
    "_internal/data.txt",
    "_internal/(0626)导入我到罗技GHUB驱动中.lua"
]

EXCLUDE_DATA_DIRS = [
    ".idea",
    "__pycache__",
    ".qoder"
]

# Nuitka 不需要但项目中引用的 stdlib / 冗余包
NOFOLLOW_STDLIB = [
    "tkinter",
    "unittest",
    "test",
    "distutils",
    "ensurepip",
    "venv",
]


def log(msg):
    print(f"[BUILD] {msg}")


def run_cmd(cmd, cwd=None):
    """执行外部命令，失败时退出。"""
    log(f"$ {cmd}")
    result = subprocess.run(cmd, shell=True, cwd=cwd or PROJECT_ROOT)
    if result.returncode != 0:
        log(f"命令执行失败 (exit {result.returncode}): {cmd}")
        sys.exit(1)


def step_cython():
    """使用 Cython 将核心模块预编译为 .pyd。"""
    log("=" * 60)
    log("Step 1: Cython 预编译核心模块")
    log("=" * 60)

    setup_script = PROJECT_ROOT / "setup_cython.py"
    if not setup_script.exists():
        log("setup_cython.py 不存在，跳过 Cython 预编译")
        return

    run_cmd(f'"{sys.executable}" setup_cython.py build_ext --inplace')

    for mod_path in CORE_MODULES_FOR_CYTHON:
        pyd_pattern = Path(mod_path).stem + "*.pyd"
        mod_dir = PROJECT_ROOT / Path(mod_path).parent
        found = list(mod_dir.glob(pyd_pattern))
        if found:
            log(f"  编译成功: {found[0].name}")
        else:
            log(f"  警告: 未找到 {mod_path} 的 .pyd 产物")


def step_nuitka():
    """使用 Nuitka 编译为独立可执行文件。"""
    log("=" * 60)
    log("Step 2: Nuitka 编译")
    log("=" * 60)

    exe_suffix = ".exe" if IS_WINDOWS else ""
    cmd_parts = [
        f'"{sys.executable}" -m nuitka',
        "--standalone",
        f"--output-dir={DIST_DIR}",
        f'--output-filename="{APP_NAME}{exe_suffix}"',
        "--enable-plugin=pyqt5",
        "--assume-yes-for-downloads",
        "--remove-output",
        "--include-package=input",
        "--include-package=ui",
        "--include-package=data",
        "--include-package=core"
    ]

    if IS_WINDOWS:
        cmd_parts.append("--windows-console-mode=disable")
        icon_path = PROJECT_ROOT / "icon.ico"
        if icon_path.exists():
            cmd_parts.append(f"--windows-icon-from-ico={icon_path}")

    for src_rel, dst_rel in INCLUDE_DATA_DIRS:
        src_abs = PROJECT_ROOT / src_rel
        if src_abs.exists():
            cmd_parts.append(f"--include-data-dir={src_abs}={dst_rel}")

    for mod in EXCLUDE_MODULES:
        cmd_parts.append(f"--nofollow-import-to={mod}")

    for mod in NOFOLLOW_STDLIB:
        cmd_parts.append(f"--nofollow-import-to={mod}")

    cmd_parts.append(str(PROJECT_ROOT / ENTRY_SCRIPT))
    cmd = " ".join(cmd_parts)

    run_cmd(cmd)

    nuitka_out = DIST_DIR / "main.dist"
    if not nuitka_out.exists():
        log(f"Nuitka 未生成 main.dist: {nuitka_out}")
        sys.exit(1)
    if OUTPUT_DIR.exists():
        shutil.rmtree(OUTPUT_DIR)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    nuitka_out.rename(RUNTIME_DIR)
    log(f"运行库目录: {RUNTIME_DIR}")


def step_post_build():
    """构建后处理：复制 bat、README、空目录与版本号。Config 和 logs 保留在 runtime/ 内。"""
    log("=" * 60)
    log("Step 3: 构建后处理")
    log("=" * 60)

    # ✅ 删除发布包中不需要的文件（如 data.txt、GHUB Lua 脚本等）
    for rel_path in EXCLUDE_DATA_FILES:
        target = RUNTIME_DIR / rel_path
        if target.exists():
            target.unlink()
            log(f"已删除发布包内多余文件: {rel_path}")
        elif target.parent.exists():
            # 检查父目录下是否有同名文件（不同大小写等情况）
            for f in target.parent.iterdir():
                if f.is_file() and f.name.lower() == target.name.lower():
                    f.unlink()
                    log(f"已删除发布包内多余文件（模糊匹配）: {f.name}")
                    break

    # ✅ 删除发布包中不需要的整个目录（分辨率模板目录、缓存等）
    for rel_dir in EXCLUDE_DATA_DIRS:
        target = RUNTIME_DIR / rel_dir
        if target.exists() and target.is_dir():
            shutil.rmtree(target)
            log(f"已删除发布包内多余目录: {rel_dir}")

    # ✅ 确保 _internal 目录中的 .dll 和 .pyd 文件被正确复制
    src_internal = PROJECT_ROOT / "_internal"
    dst_internal = RUNTIME_DIR / "_internal"
    if src_internal.exists() and dst_internal.exists():
        for file in src_internal.iterdir():
            if file.is_file() and file.suffix in ['.dll', '.pyd']:
                dst_file = dst_internal / file.name
                if not dst_file.exists():
                    shutil.copy2(file, dst_file)
                    log(f"已复制缺失文件: {file.name}")

    bat_src = PROJECT_ROOT / "启动.bat"
    if bat_src.exists():
        shutil.copy2(bat_src, OUTPUT_DIR / "启动.bat")
        log("已复制 启动.bat")

    readme_src = PROJECT_ROOT / "使用指南.txt"
    if readme_src.exists():
        shutil.copy2(readme_src, OUTPUT_DIR / "使用说明.txt")
        log("已复制 使用说明.txt")

    config_dir = RUNTIME_DIR / "Config"
    config_dir.mkdir(exist_ok=True)

    logs_dir = RUNTIME_DIR / "logs"
    logs_dir.mkdir(exist_ok=True)
    log("已确保 Config/ 与 logs/ 在 runtime/ 内")

    version_file = RUNTIME_DIR / "version.txt"
    version_file.write_text(VERSION, encoding="utf-8")
    log(f"版本号: {VERSION}")


def step_zip():
    """将构建产物打为 zip 包。"""
    log("=" * 60)
    log("Step 5: 打包 ZIP")
    log("=" * 60)

    if not OUTPUT_DIR.exists():
        log(f"构建目录不存在: {OUTPUT_DIR}")
        sys.exit(1)

    zip_name = f"{APP_NAME}-v{VERSION}.zip"
    zip_path = DIST_DIR / zip_name

    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for file_path in OUTPUT_DIR.rglob("*"):
            if file_path.is_file():
                arcname = f"{APP_NAME}/{file_path.relative_to(OUTPUT_DIR)}"
                zf.write(file_path, arcname)

    size_mb = zip_path.stat().st_size / (1024 * 1024)
    log(f"ZIP 打包完成: {zip_path} ({size_mb:.1f} MB)")


def main():
    global VERSION
    
    parser = argparse.ArgumentParser(description=f"{APP_NAME} 构建脚本")
    parser.add_argument("--skip-cython", action="store_true", help="跳过 Cython 预编译")
    parser.add_argument("--zip-only", action="store_true", help="仅打包已有产物为 zip")
    parser.add_argument("--version", default=VERSION, help=f"版本号 (默认: {VERSION})")
    args = parser.parse_args()

    VERSION = args.version

    log(f"{APP_NAME} 构建开始 — v{VERSION}")
    log(f"项目根目录: {PROJECT_ROOT}")
    log(f"Python: {sys.executable} ({sys.version})")

    if args.zip_only:
        step_zip()
    else:
        if not args.skip_cython:
            step_cython()
        step_nuitka()
        step_post_build()
        step_zip()

    log("构建全部完成!")


if __name__ == "__main__":
    main()
