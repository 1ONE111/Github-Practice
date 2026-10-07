"""프로그램 시작점."""

from __future__ import annotations

import os
import sys

from PySide6.QtWidgets import QApplication, QStyleFactory

from naver_crawler import APP_ID, APP_NAME
from naver_crawler.config import Settings
from naver_crawler.ui.main_window import MainWindow
from naver_crawler.ui.theme import STYLESHEET, app_font, app_icon, apply_palette


def selftest(with_browser: bool = False) -> int:
    """빌드된 exe 점검용 (0 = 정상). 결과는 데이터 폴더의 selftest.log 에도 남긴다.

    기본: 화면 구성, Selenium 모듈/Selenium Manager 포함 여부.
    --browser: 실제 크롬을 창 없이 띄워 페이지를 열고 내부 응답 수집까지 확인.
    """
    import importlib
    import threading
    from urllib.parse import quote
    import traceback

    from naver_crawler.config import app_data_dir

    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    log_path = app_data_dir() / "selftest.log"
    lines: list[str] = []
    try:
        from selenium.webdriver.common.selenium_manager import SeleniumManager

        for name in ("selenium.webdriver.chrome.webdriver", "selenium.webdriver.chromium.webdriver",
                     "selenium.webdriver.remote.webdriver", "selenium.webdriver.chrome.options"):
            importlib.import_module(name)
        lines.append(f"selenium-manager: {SeleniumManager._get_binary()}")
        app = QApplication([sys.argv[0]])
        apply_palette(app)
        app.setStyleSheet(STYLESHEET)
        window = MainWindow(Settings())
        assert len(window.pages) == 6
        window.close()
        lines.append("ui: ok")
        if with_browser:
            from naver_crawler.browser import BrowserManager, Page

            settings = Settings(headless=True, keep_login=False,
                                chromedriver_path=os.environ.get("NAVER_CRAWLER_DRIVER", ""),
                                chrome_binary=os.environ.get("NAVER_CRAWLER_CHROME", ""))
            browser = BrowserManager(settings, lines.append)
            try:
                page = Page(browser.driver(), threading.Event(), 10)
                html = "<meta charset='utf-8'><title>ok</title><p class='v'>조회 1,234</p>"
                page.open("data:text/html;charset=utf-8," + quote(html))
                assert page.text([".v"], need_digit=True) == "조회 1,234"
                page.captured_json()
                lines.append(f"browser: ok ({browser.version_text})")
            finally:
                browser.quit()
        code = 0
    except Exception:  # noqa: BLE001
        lines.append(traceback.format_exc())
        code = 1
    log_path.write_text("\n".join(lines), encoding="utf-8")
    print("\n".join(lines))
    return code


def main(argv: list[str] | None = None) -> int:
    argv = list(argv if argv is not None else sys.argv)
    if "--selftest" in argv:
        return selftest(with_browser="--browser" in argv)
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
