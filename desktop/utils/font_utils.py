"""
字体工具 - 统一管理字体，解决打包后中文乱码
"""
from PyQt5.QtGui import QFont


def make_font(size=9, weight=QFont.Normal, bold=False):
    """创建带回退链的字体，避免PyInstaller打包后中文乱码"""
    f = QFont()
    f.setFamilies(["Microsoft YaHei UI", "Microsoft YaHei", "SimHei", "Arial", "sans-serif"])
    f.setPointSize(size)
    if bold:
        f.setWeight(QFont.Bold)
    elif weight != QFont.Normal:
        f.setWeight(weight)
    f.setStyleStrategy(QFont.PreferAntialias)
    return f
