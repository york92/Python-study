#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
FileDiff Pro - 文件差异比较与合并工具
主入口文件
"""

import sys
from PyQt5.QtWidgets import QApplication
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QFont
from ui.main_window import MainWindow


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("FileDiff Pro")
    app.setApplicationVersion("1.0.0")
    app.setOrganizationName("FileDiff")

    # 设置全局字体
    font = QFont("Consolas", 10)
    app.setFont(font)

    # 设置高DPI支持
    app.setAttribute(Qt.AA_EnableHighDpiScaling, True)
    app.setAttribute(Qt.AA_UseHighDpiPixmaps, True)

    window = MainWindow()
    window.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
