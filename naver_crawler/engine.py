"""UI 와 분리된 수집 실행기. 화면 없이 CLI/테스트에서도 그대로 쓴다."""

from __future__ import annotations

import threading
import time
from typing import Callable, Hashable, Iterable

from naver_crawler.browser import BrowserError, BrowserManager, CrawlCancelled, friendly_error
from naver_crawler.config import Settings
from naver_crawler.crawlers import STATUS_CANCELLED, STATUS_FAIL, Context, RowResult, TaskSpec
from naver_crawler.http import NaverHttp
from naver_crawler.selectors import load_selectors


class Engine:
    def __init__(self, settings: Settings, log: Callable[[str], None] | None = None):
        self.settings = settings
        self.log = log or (lambda msg: None)
        self.browser = BrowserManager(settings, self._log)
        self.http = NaverHttp()

    def _log(self, msg: str) -> None:
        self.log(msg)

    def run(
        self,
        task: TaskSpec,
        items: Iterable[tuple[Hashable, str]],
        stop: threading.Event,
        on_start: Callable[[Hashable], None] = lambda key: None,
        on_result: Callable[[Hashable, RowResult], None] = lambda key, res: None,
        selectors: dict | None = None,
    ) -> bool:
        """items 를 차례로 수집한다. 중지되면 False."""
        ctx = Context(self.browser, self.http, self.settings, selectors or load_selectors(), stop, self._log)
        items = list(items)
        for index, (key, url) in enumerate(items):
            if stop.is_set():
                return False
            on_start(key)
            started = time.monotonic()
            try:
                result = task.run(ctx, ctx.expand(url))
            except CrawlCancelled:
                on_result(key, RowResult({}, STATUS_CANCELLED, "사용자가 중지했습니다"))
                return False
            except BrowserError as exc:
                on_result(key, RowResult({}, STATUS_FAIL, str(exc)))
                self._log(f"[오류] {exc}")
                raise  # 크롬을 못 띄우면 나머지 URL 도 전부 실패하므로 바로 멈추고 알린다
            except Exception as exc:  # noqa: BLE001 - 한 URL 실패가 전체를 멈추지 않게
                result = RowResult({}, STATUS_FAIL, friendly_error(exc))
            on_result(key, result)
            elapsed = time.monotonic() - started
            self._log(f"[{result.status}] {url} ({elapsed:.1f}초){' - ' + result.message if result.message else ''}")
            if index < len(items) - 1 and not _sleep(self.settings.request_delay, stop):
                return False
        return True

    def open_login(self) -> None:
        from naver_crawler.browser import LOGIN_URL

        drv = self.browser.driver(force_visible=True)
        drv.switch_to.default_content()
        drv.get(LOGIN_URL)

    def shutdown(self) -> None:
        self.browser.quit()


def _sleep(seconds: float, stop: threading.Event) -> bool:
    return not stop.wait(max(0.0, float(seconds)))
