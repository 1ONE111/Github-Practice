"""프로그램 시작점."""

from __future__ import annotations

import os
import sys

from PySide6.QtWidgets import QApplication, QStyleFactory

from naver_crawler import APP_ID, APP_NAME
from naver_crawler.config import Settings
from naver_crawler.ui.main_window import MainWindow
from naver_crawler.ui.theme import STYLESHEET, app_font, app_icon, apply_palette


def selftest() -> int:
    """빌드된 exe 점검용: 화면 구성과 Selenium Manager 포함 여부만 확인하고 종료 (0 = 정상)."""
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from selenium.webdriver.common.selenium_manager import SeleniumManager

    SeleniumManager._get_binary()  # 번들에 드라이버 관리자가 빠졌으면 예외
    app = QApplication([sys.argv[0]])
    apply_palette(app)
    app.setStyleSheet(STYLESHEET)
    window = MainWindow(Settings())
    ok = len(window.pages) == 6
    window.close()
    return 0 if ok else 1


def main(argv: list[str] | None = None) -> int:
    argv = list(argv if argv is not None else sys.argv)
    if "--selftest" in argv:
        return selftest()
    if sys.platform == "win32":
        try:  # 작업 표시줄에 파이썬 아이콘 대신 프로그램 아이콘이 보이게
            import ctypes

            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(APP_ID)
        except Exception:  # noqa: BLE001
            pass

    app = QApplication(argv)
    app.setApplicationName(APP_NAME)
    app.setStyle(QStyleFactory.create("Fusion"))
    apply_palette(app)
    app.setFont(app_font())
    app.setStyleSheet(STYLESHEET)
    app.setWindowIcon(app_icon())

    window = MainWindow(Settings.load())
    window.show()
    return app.exec()
