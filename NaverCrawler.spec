# -*- mode: python ; coding: utf-8 -*-
# PyInstaller 설정: build.bat 이 이 파일로 dist\NaverCrawler.exe 한 개를 만든다.
import sys

from PyInstaller.utils.hooks import collect_data_files, collect_submodules

# Selenium Manager(크롬 드라이버 자동 설치 도구)는 실행 중인 OS 것만 넣는다
PLATFORM_DIR = {"win32": "windows", "darwin": "macos"}.get(sys.platform, "linux")


def keep_data(dest: str) -> bool:
    path = dest.replace("\\", "/")
    if "selenium/webdriver/common/" in path and "selenium-manager" in path.rsplit("/", 1)[-1]:
        return f"/{PLATFORM_DIR}" in path
    return True


a = Analysis(
    ["run_app.py"],
    pathex=[],
    binaries=[],
    datas=collect_data_files("selenium"),
    # Selenium 4.3x+ 는 webdriver.Chrome 등을 지연 import 해서 정적 분석이 놓친다
    hiddenimports=collect_submodules("selenium"),
    excludes=["tkinter", "PySide6.QtWebEngineCore", "PySide6.QtWebEngineWidgets", "PySide6.Qt3DCore", "PySide6.QtQuick", "PySide6.QtQml"],
    noarchive=False,
)
a.datas = [d for d in a.datas if keep_data(d[0])]
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="NaverCrawler",
    debug=False,
    strip=False,
    upx=False,
    console=False,
    icon="assets/app.ico",
)
