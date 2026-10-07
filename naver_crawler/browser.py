"""크롬 실행/관리와 페이지 조회 도우미.

Selenium 4.6+ 에 내장된 Selenium Manager 가 설치된 크롬 버전(예: 155.0.8059.40)에
맞는 ChromeDriver 를 자동으로 내려받으므로 webdriver_manager 가 더 이상 필요 없다.
"""

from __future__ import annotations

import json
import os
import shlex
import subprocess
import sys
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable

from selenium.common.exceptions import (
    NoSuchDriverException,
    SessionNotCreatedException,
    WebDriverException,
)
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.webdriver import WebDriver as Chrome  # 직접 import: exe 빌드에서 빠지지 않게
from selenium.webdriver.common.by import By

from naver_crawler.config import Settings, chrome_profile_dir
from naver_crawler.parsing import load_json_loose

LOGIN_URL = "https://nid.naver.com/nidlogin.login"


class CrawlCancelled(Exception):
    pass


class BrowserError(RuntimeError):
    pass


@dataclass
class CapturedResponse:
    url: str
    data: object


def friendly_error(exc: BaseException) -> str:
    text = str(exc)
    if isinstance(exc, NoSuchDriverException) or "Unable to obtain driver" in text:
        return (
            "ChromeDriver 를 준비하지 못했습니다. 인터넷 연결을 확인하거나 "
            "설정에서 chromedriver.exe 경로를 직접 지정하세요."
        )
    if "user data directory is already in use" in text:
        return (
            "크롤러 전용 크롬 프로필이 이미 사용 중입니다. 이전에 열린 크롤러 크롬 창을 모두 닫고 다시 시도하세요."
        )
    if "cannot find Chrome binary" in text or "no chrome binary" in text.lower():
        return "크롬이 설치되어 있지 않거나 찾을 수 없습니다. 설정에서 chrome.exe 경로를 지정하세요."
    if isinstance(exc, SessionNotCreatedException):
        first = text.strip().splitlines()[0] if text.strip() else ""
        return f"크롬을 시작하지 못했습니다: {first}"
    return text.strip().splitlines()[0] if text.strip() else exc.__class__.__name__


class BrowserManager:
    """크롬 한 개를 띄워 여러 작업에서 재사용한다. 한 번에 한 스레드만 사용해야 한다."""

    def __init__(self, settings: Settings, log: Callable[[str], None] | None = None):
        self.settings = settings
        self.log = log or (lambda msg: None)
        self._driver: Chrome | None = None
        self._headless: bool | None = None
        self._lock = threading.Lock()
        self.version_text = ""

    # ------------------------------------------------------------ 생명주기
    def driver(self, force_visible: bool = False) -> Chrome:
        want_headless = bool(self.settings.headless) and not force_visible
        with self._lock:
            if self._driver is not None:
                if self._headless == want_headless and self._is_alive():
                    return self._driver
                self._quit_locked()
            self._driver = self._create(want_headless)
            self._headless = want_headless
            return self._driver

    def is_running(self) -> bool:
        return self._driver is not None

    def quit(self) -> None:
        with self._lock:
            self._quit_locked()

    def _quit_locked(self) -> None:
        if self._driver is not None:
            try:
                self._driver.quit()
            except Exception:  # noqa: BLE001 - 종료 중 오류는 무시
                pass
        self._driver = None
        self._headless = None

    def _is_alive(self) -> bool:
        try:
            _ = self._driver.window_handles  # type: ignore[union-attr]
            return True
        except Exception:  # noqa: BLE001
            return False

    def _create(self, headless: bool) -> Chrome:
        opts = Options()
        if headless:
            opts.add_argument("--headless=new")
        opts.add_argument("--window-size=1400,1000")
        opts.add_argument("--lang=ko-KR")
        opts.add_argument("--disable-notifications")
        opts.add_argument("--no-first-run")
        opts.add_argument("--no-default-browser-check")
        opts.add_experimental_option("excludeSwitches", ["enable-logging", "enable-automation"])
        opts.add_experimental_option("prefs", {"intl.accept_languages": "ko-KR,ko"})
        opts.set_capability("goog:loggingPrefs", {"performance": "ALL"})
        opts.page_load_strategy = "eager"
        if self.settings.keep_login:
            profile = chrome_profile_dir()
            profile.mkdir(parents=True, exist_ok=True)
            opts.add_argument(f"--user-data-dir={profile}")
        if self.settings.chrome_binary:
            opts.binary_location = self.settings.chrome_binary
        for arg in shlex.split(os.environ.get("NAVER_CRAWLER_CHROME_ARGS", "")):
            opts.add_argument(arg)  # 고급: 프록시 등 추가 크롬 옵션

        popen_kw = {}
        if sys.platform == "win32":
            popen_kw["creation_flags"] = subprocess.CREATE_NO_WINDOW  # 검은 콘솔 창 숨김
        service = Service(executable_path=self.settings.chromedriver_path or None, popen_kw=popen_kw)

        self.log("크롬을 시작합니다" + (" (창 숨김)" if headless else "") + "…")
        try:
            drv = Chrome(service=service, options=opts)
        except Exception as exc:  # noqa: BLE001 - 크롬을 못 띄우면 어떤 오류든 작업 전체를 멈춘다
            raise BrowserError(friendly_error(exc)) from exc
        drv.set_page_load_timeout(max(30, self.settings.page_timeout + 15))
        caps = drv.capabilities
        chrome_ver = caps.get("browserVersion", "?")
        driver_ver = str(caps.get("chrome", {}).get("chromedriverVersion", "?")).split(" ")[0]
        self.version_text = f"Chrome {chrome_ver} · Driver {driver_ver}"
        self.log(f"크롬 준비 완료: {self.version_text}")
        return drv

    # ------------------------------------------------------------ 쿠키
    def naver_cookies(self) -> list[dict]:
        drv = self._driver
        if drv is None:
            return []
        try:
            data = drv.execute_cdp_cmd("Network.getAllCookies", {})
            cookies = data.get("cookies", [])
        except Exception:  # noqa: BLE001
            try:
                cookies = drv.get_cookies()
            except Exception:  # noqa: BLE001
                return []
        return [c for c in cookies if "naver.com" in str(c.get("domain", ""))]

    def is_logged_in(self) -> bool:
        return any(c.get("name") == "NID_AUT" for c in self.naver_cookies())


# ---------------------------------------------------------------- 페이지 도우미

_JS_FIND_TEXT = r"""
const sels = arguments[0], needDigit = arguments[1], contains = arguments[2];
for (const s of sels) {
  let els;
  try { els = document.querySelectorAll(s); } catch (e) { continue; }
  for (const el of els) {
    const t = ((el.innerText || '').trim() || (el.textContent || '').trim()).replace(/\s+/g, ' ');
    if (!t) continue;
    if (needDigit && !/\d/.test(t)) continue;
    if (contains && !contains.some(c => t.includes(c))) continue;
    return t;
  }
}
return null;
"""

_JS_COUNT = r"""
const sels = arguments[0];
for (const s of sels) {
  try { const n = document.querySelectorAll(s).length; if (n) return n; } catch (e) {}
}
return 0;
"""

_JS_LIST_VIEWS = r"""
const rowSels = arguments[0], cellSels = arguments[1];
for (const rs of rowSels) {
  let rows;
  try { rows = Array.from(document.querySelectorAll(rs)); } catch (e) { continue; }
  const out = [];
  for (const tr of rows) {
    const cls = (tr.className || '') + ' ' + ((tr.closest('[id]') || {}).id || '');
    if (/notice|upperArticleList/i.test(cls)) continue;
    let cell = null;
    for (const cs of cellSels) { try { cell = tr.querySelector(cs); } catch (e) {} if (cell) break; }
    if (!cell) continue;
    const t = (cell.innerText || cell.textContent || '').trim();
    if (/\d/.test(t)) out.push(t);
  }
  if (out.length) return out;
}
return [];
"""


class Page:
    """한 번의 페이지 방문 동안 프레임 전환, 요소 대기, 네트워크 응답 수집을 맡는다."""

    def __init__(self, driver: Chrome, stop: threading.Event, timeout: float):
        self.driver = driver
        self.stop = stop
        self.timeout = timeout
        self.frames: list[str] = []
        self.responses: list[CapturedResponse] = []

    def check_stop(self) -> None:
        if self.stop.is_set():
            raise CrawlCancelled()

    def open(self, url: str, frames: Iterable[str] = ()) -> None:
        self.check_stop()
        self.frames = list(frames)
        self.drain_network()
        self.responses = []
        try:
            self.driver.switch_to.default_content()
        except WebDriverException:
            pass
        try:
            self.driver.get(url)
        except WebDriverException as exc:
            if "timeout" not in str(exc).lower():
                raise
        self.enter_frame()

    def enter_frame(self) -> bool:
        """지정한 iframe(cafe_main, mainFrame 등)이 있으면 들어간다. 없으면 최상위 문서에 머문다."""
        try:
            self.driver.switch_to.default_content()
        except WebDriverException:
            return False
        for name in self.frames:
            found = self.driver.find_elements(By.CSS_SELECTOR, f"iframe#{name}, iframe[name='{name}']")
            if found:
                try:
                    self.driver.switch_to.frame(found[0])
                    return True
                except WebDriverException:
                    continue
        return False

    def wait_until(self, probe: Callable[[], bool], timeout: float | None = None) -> bool:
        deadline = time.monotonic() + (self.timeout if timeout is None else timeout)
        while True:
            self.check_stop()
            try:
                self.enter_frame()
                if probe():
                    return True
            except WebDriverException:
                pass
            if time.monotonic() >= deadline:
                return False
            time.sleep(0.4)

    def text(self, selectors: list[str], need_digit: bool = False, contains: list[str] | None = None) -> str | None:
        try:
            return self.driver.execute_script(_JS_FIND_TEXT, selectors, need_digit, contains)
        except WebDriverException:
            return None

    def count(self, selectors: list[str]) -> int:
        try:
            return int(self.driver.execute_script(_JS_COUNT, selectors) or 0)
        except WebDriverException:
            return 0

    def list_view_texts(self, row_selectors: list[str], cell_selectors: list[str]) -> list[str]:
        try:
            return list(self.driver.execute_script(_JS_LIST_VIEWS, row_selectors, cell_selectors) or [])
        except WebDriverException:
            return []

    def body_text(self) -> str:
        try:
            return self.driver.execute_script("return document.body ? document.body.innerText : ''") or ""
        except WebDriverException:
            return ""

    def top_body_text(self) -> str:
        try:
            self.driver.switch_to.default_content()
            return self.driver.execute_script("return document.body ? document.body.innerText : ''") or ""
        except WebDriverException:
            return ""
        finally:
            self.enter_frame()

    def title(self) -> str:
        try:
            return self.driver.execute_script("return document.title") or ""
        except WebDriverException:
            return ""

    def top_title(self) -> str:
        try:
            self.driver.switch_to.default_content()
            return self.driver.title or ""
        except WebDriverException:
            return ""
        finally:
            self.enter_frame()

    def source(self) -> str:
        try:
            return self.driver.page_source or ""
        except WebDriverException:
            return ""

    def all_sources(self) -> str:
        parts = []
        try:
            self.driver.switch_to.default_content()
            parts.append(self.driver.page_source or "")
            if self.enter_frame():
                parts.append(self.driver.page_source or "")
        except WebDriverException:
            pass
        return "\n<!-- frame -->\n".join(parts)

    # ------------------------------------------------------------ 네트워크
    def drain_network(self) -> None:
        try:
            self.driver.get_log("performance")
        except Exception:  # noqa: BLE001
            pass

    def captured_json(self, url_filter: Callable[[str], bool] | None = None) -> list[CapturedResponse]:
        """페이지가 내부적으로 호출한 JSON API 응답을 모은다 (화면 구조가 바뀌어도 데이터 키는 잘 안 바뀐다)."""
        try:
            entries = self.driver.get_log("performance")
        except Exception:  # noqa: BLE001
            entries = []
        for entry in entries:
            try:
                msg = json.loads(entry["message"])["message"]
            except (KeyError, ValueError, TypeError):
                continue
            if msg.get("method") != "Network.responseReceived":
                continue
            params = msg.get("params", {})
            resp = params.get("response", {})
            url = resp.get("url", "")
            mime = resp.get("mimeType", "")
            if "naver" not in url or not ("json" in mime or "javascript" in mime or "text/plain" in mime):
                continue
            try:
                body = self.driver.execute_cdp_cmd("Network.getResponseBody", {"requestId": params.get("requestId")})
            except Exception:  # noqa: BLE001
                continue
            data = load_json_loose(body.get("body", ""))
            if data is not None:
                self.responses.append(CapturedResponse(url, data))
        if url_filter is None:
            return list(self.responses)
        return [r for r in self.responses if url_filter(r.url)]

    def save_debug(self, folder: Path, name: str) -> Path | None:
        try:
            path = folder / f"{time.strftime('%Y%m%d_%H%M%S')}_{name}.html"
            path.write_text(self.all_sources(), encoding="utf-8")
            return path
        except OSError:
            return None
