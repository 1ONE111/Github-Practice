"""프로그램 시작점.

    InstaCrawler.exe                 화면 실행
    InstaCrawler.exe --selftest      빌드 점검 (0 = 정상, 데이터 폴더 selftest.log)
    python -m insta_crawler --cli 아이디 [아이디 ...]   화면 없이 수집해 결과 출력 (점검용)
"""

from __future__ import annotations

import os
import sys
import threading

from insta_crawler import APP_ID, APP_NAME


def selftest() -> int:
    import importlib
    import traceback

    from insta_crawler.config import Settings, app_data_dir

    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    lines: list[str] = []
    try:
        from selenium.webdriver.common.selenium_manager import SeleniumManager

        for name in ("selenium.webdriver.chrome.webdriver", "selenium.webdriver.chrome.options",
                     "selenium.webdriver.chrome.service", "openpyxl", "requests"):
            importlib.import_module(name)
        lines.append(f"selenium-manager: {SeleniumManager._get_binary()}")
        from PySide6.QtWidgets import QApplication

        from insta_crawler.theme import setup_app
        from insta_crawler.ui import MainWindow

        app = QApplication([sys.argv[0]])
        setup_app(app)
        window = MainWindow(Settings())
        window.edit.setPlainText("https://www.instagram.com/instagram/\n@natgeo")
        assert window.count_chip.text() == "2개", window.count_chip.text()
        window.close()
        lines.append("ui: ok")
        code = 0
    except Exception:  # noqa: BLE001
        lines.append(traceback.format_exc())
        code = 1
    (app_data_dir() / "selftest.log").write_text("\n".join(lines), encoding="utf-8")
    print("\n".join(lines))
    return code


def cli(names: list[str]) -> int:
    from insta_crawler.client import InstaClient
    from insta_crawler.collector import Runner, StopRun
    from insta_crawler.config import Settings, load_session
    from insta_crawler.parsing import parse_targets

    targets = parse_targets("\n".join(names))
    runner = Runner(Settings.load(), InstaClient(load_session()), print)

    def show(key, result) -> None:
        print(f"{targets[key].label}: [{result.status}] {result.values} {result.message}")

    try:
        runner.run(list(enumerate(targets)), threading.Event(), on_result=show)
    except StopRun as exc:
        print(f"[멈춤] {exc}")
        return 1
    return 0


def main(argv: list[str] | None = None) -> int:
    argv = list(argv if argv is not None else sys.argv)
    if "--selftest" in argv:
        return selftest()
    if "--cli" in argv:
        return cli(argv[argv.index("--cli") + 1:])
    if sys.platform == "win32":
        try:  # 작업 표시줄에 파이썬 아이콘 대신 프로그램 아이콘
            import ctypes

            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(APP_ID)
        except Exception:  # noqa: BLE001
            pass

    from PySide6.QtWidgets import QApplication, QStyleFactory

    from insta_crawler.config import Settings
    from insta_crawler.theme import setup_app
    from insta_crawler.ui import MainWindow

    app = QApplication(argv)
    app.setApplicationName(APP_NAME)
    app.setStyle(QStyleFactory.create("Fusion"))
    setup_app(app)
    window = MainWindow(Settings.load())
    window.show()
    return app.exec()
