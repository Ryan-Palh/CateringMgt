# -*- coding: utf-8 -*-
"""
PyInstaller 打包脚本 — 餐饮综合管理系统 v5.0
用法: python build_exe.py
"""
import PyInstaller.__main__
import os
import sys

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# conda 环境下 _ctypes/_sqlite3 等依赖 Library/bin 中的 DLL，PyInstaller 不会自动收集
_conda_bin = os.path.join(sys.prefix, 'Library', 'bin')
_add_binaries = []
for _dll in ['ffi-8.dll', 'sqlite3.dll', 'libexpat.dll']:
    _path = os.path.join(_conda_bin, _dll)
    if os.path.isfile(_path):
        _add_binaries.append(f'--add-binary={_path}{os.pathsep}.')

PyInstaller.__main__.run([
    'main.py',
    '--name=餐饮综合管理系统',
    '--windowed',
    '--onefile',
    '--icon=assets/app_icon.ico',
    f'--add-data=assets{os.pathsep}assets',
    f'--add-data=config.ini{os.pathsep}.',
    f'--add-data=gui{os.pathsep}gui',
    f'--add-data=database{os.pathsep}database',
    f'--add-data=utils{os.pathsep}utils',
    '--hidden-import=PyQt5',
    '--hidden-import=PyQt5.QtCore',
    '--hidden-import=PyQt5.QtGui',
    '--hidden-import=PyQt5.QtWidgets',
    '--hidden-import=webdav4.client',
    '--hidden-import=webdav4.fsspec',
    '--hidden-import=bcrypt',
    '--hidden-import=cryptography.fernet',
    '--hidden-import=openpyxl',
    '--hidden-import=PIL',
    '--hidden-import=matplotlib',
    '--hidden-import=matplotlib.pyplot',
    '--hidden-import=matplotlib.backends.backend_qt5agg',
    '--hidden-import=numpy',
    *_add_binaries,
    '--exclude-module=PyQt5.QtQml',
    '--exclude-module=PyQt5.QtQuick',
    '--exclude-module=PyQt5.QtQmlModels',
    '--noconfirm',
    '--clean',
    f'--distpath={os.path.join(BASE_DIR, "dist")}',
    f'--workpath={os.path.join(BASE_DIR, "build")}',
    f'--specpath={BASE_DIR}',
])

print("\n打包完成！可执行文件位于 dist/ 目录")
