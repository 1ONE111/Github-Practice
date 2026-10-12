"""인스타 로그인: 전용 크롬 프로필로 창을 띄워 사용자가 직접 로그인 → 쿠키만 저장하고 크롬은 닫는다.

수집 자체는 크롬 없이 저장된 쿠키로 한다. 한 번 로그인하면 전용 프로필에 남아 다음 로그인은 바로 끝난다.
"""

from __future__ import annotations

import os
import shlex
import subprocess
import sys
import threading
import time
from typing import Callable

from insta_crawler.config import Settings, chrome_profile_dir

LOGIN_URL = "https://www.instagram.com/accounts/login/"


class LoginError(RuntimeError):
    pass


def friendly_error(exc: BaseException) -> str:
    text = str(exc)
    if "Unable to obtain driver" in text or exc.__class__.__name__ == "NoSuchDriverException":
        return "ChromeDriver 를 준비하지 못했습니다. 인터넷 연결을 확인하세요."
    if "user data directory is already in use" in text:
        return "로그인용 크롬 창이 이미 열려 있습니다. 그 창을 닫고 다시 시도하세요."
    if "cannot find Chrome binary" in text or "no chrome binary" in text.lower():
        return "크롬이 설치되어 있지 않거나 찾을 수 없습니다."
    first = text.strip().splitlines()[0] if text.strip() else exc.__class__.__name__
    return first


def _open_chrome(settings: Settings):
    from selenium.webdriver.chrome.options import Options
    from selenium.webdriver.chrome.service import Service
    from selenium.webdriver.chrome.webdriver import WebDriver as Chrome  # 직접 import: exe 빌드에서 빠지지 않게

    opts = Options()
    profile = chrome_profile_dir()
    profile.mkdir(parents=True, exist_ok=True)
    opts.add_argument(f"--user-data-dir={profile}")
    opts.add_argument("--window-size=480,820")
    opts.add_argument("--lang=ko-KR")
    opts.add_argument("--no-first-run")
    opts.add_argument("--no-default-browser-check")
    opts.add_experimental_option("excludeSwitches", ["enable-logging", "enable-automation"])
    if settings.chrome_binary:
        opts.binary_location = settings.chrome_binary
    for arg in shlex.split(os.environ.get("INSTA_CRAWLER_CHROME_ARGS", "")):
        opts.add_argument(arg)
    popen_kw = {}
    if sys.platform == "win32":
        popen_kw["creation_flags"] = subprocess.CREATE_NO_WINDOW  # 검은 콘솔 창 숨김
    service = Service(executable_path=settings.chromedriver_path or None, popen_kw=popen_kw)
    try:
        return Chrome(service=service, options=opts)
    except Exception as exc:  # noqa: BLE001
        raise LoginError(friendly_error(exc)) from exc


def browser_login(settings: Settings, stop: threading.Event, log: Callable[[str], None] = lambda m: None,
                  timeout: float = 600) -> list[dict]:
    """로그인이 끝나면(sessionid 쿠키가 생기면) 인스타 쿠키 목록을 돌려준다. 창을 닫거나 시간이 지나면 빈 목록."""
    log("로그인용 크롬을 엽니다…")
    drv = _open_chrome(settings)
    try:
        drv.get(LOGIN_URL)
        log("크롬 창에서 인스타에 로그인하세요. 로그인되면 창이 자동으로 닫힙니다.")
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline and not stop.is_set():
            try:
                cookies = [c for c in drv.get_cookies() if "instagram.com" in str(c.get("domain", ""))]
            except Exception:  # noqa: BLE001 - 사용자가 창을 닫음
                return []
            if any(c.get("name") == "sessionid" and c.get("value") for c in cookies):
                time.sleep(1.5)  # csrftoken 등 나머지 쿠키가 붙을 때까지
                try:
                    cookies = [c for c in drv.get_cookies() if "instagram.com" in str(c.get("domain", ""))]
                except Exception:  # noqa: BLE001
                    pass
                return cookies
            time.sleep(1)
        return []
    finally:
        try:
            drv.quit()
        except Exception:  # noqa: BLE001
            pass
