"""UI 와 분리된 수집 실행기. 화면 없이 CLI/테스트에서도 그대로 쓴다."""

from __future__ import annotations

import threading
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Callable, Hashable, Iterable

from naver_crawler.browser import BrowserError, BrowserManager, CrawlCancelled, friendly_error
from naver_crawler.config import Settings
from naver_crawler.crawlers import (
    STATUS_CANCELLED,
    STATUS_FAIL,
    STATUS_PARTIAL,
    Context,
    RowResult,
    TaskSpec,
    merge_results,
)
from naver_crawler.http import NaverHttp
from naver_crawler.selectors import load_selectors

Runner = Callable[[Context, str, Hashable], RowResult]


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
        """items 를 수집한다. 중지되면 False.

        크롬 없이 되는 작업(task.fast)은 여러 개를 동시에 처리하고, 빈 값이 남은 것만 크롬으로 다시 확인한다.
        """
        ctx = Context(self.browser, self.http, self.settings, selectors or load_selectors(), stop, self._log)
        items = list(items)
        if task.fast is not None:
            return self._run_fast(task, items, ctx, stop, on_start, on_result)
        return self._run_browser(lambda c, url, key: task.run(c, url), items, ctx, stop, on_start, on_result)

    # ------------------------------------------------------------ 크롬으로 하나씩
    def _run_browser(self, runner: Runner, items, ctx: Context, stop, on_start, on_result) -> bool:
        for index, (key, url) in enumerate(items):
            if stop.is_set():
                return False
            on_start(key)
            started = time.monotonic()
            try:
                result = runner(ctx, ctx.expand(url), key)
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
            self._log_result(url, result, started)
            if index < len(items) - 1 and not _sleep(self.settings.request_delay, stop):
                return False
        return True

    # ------------------------------------------------------------ 크롬 없이 동시에
    def _run_fast(self, task: TaskSpec, items, ctx: Context, stop, on_start, on_result) -> bool:
        workers = max(1, min(16, int(self.settings.workers)))
        self._log(f"빠른 수집: 크롬 없이 {workers}개씩 동시에 처리합니다")
        retry: list[tuple[Hashable, str, RowResult]] = []
        lock = threading.Lock()

        def one(key: Hashable, url: str) -> None:
            if stop.is_set():
                return
            on_start(key)
            started = time.monotonic()
            try:
                result = task.fast(ctx, ctx.expand(url, allow_browser=False))
            except Exception as exc:  # noqa: BLE001
                result = RowResult({}, STATUS_FAIL, friendly_error(exc))
            if result.status in (STATUS_PARTIAL, STATUS_FAIL) and self.settings.browser_fallback:
                with lock:
                    retry.append((key, url, result))
            on_result(key, result)
            self._log_result(url, result, started)
            _sleep(self.settings.request_delay, stop)

        with ThreadPoolExecutor(max_workers=workers, thread_name_prefix="fast") as pool:
            for future in [pool.submit(one, key, url) for key, url in items]:
                future.result()
        if stop.is_set():
            return False
        if not retry:
            return True

        order = {key: i for i, (key, _url) in enumerate(items)}
        retry.sort(key=lambda r: order[r[0]])
        previous = {key: result for key, _url, result in retry}
        self._log(f"빈 값이 있는 {len(retry)}건은 크롬으로 다시 확인합니다")

        def recheck(c: Context, url: str, key: Hashable) -> RowResult:
            return merge_results(task, previous[key], task.run(c, url))

        return self._run_browser(recheck, [(key, url) for key, url, _r in retry], ctx, stop, on_start, on_result)

    def _log_result(self, url: str, result: RowResult, started: float) -> None:
        elapsed = time.monotonic() - started
        self._log(f"[{result.status}] {url} ({elapsed:.1f}초){' - ' + result.message if result.message else ''}")

    def open_login(self) -> None:
        from naver_crawler.browser import LOGIN_URL

        drv = self.browser.driver(force_visible=True)
        drv.switch_to.default_content()
        drv.get(LOGIN_URL)

    def shutdown(self) -> None:
        self.browser.quit()


def _sleep(seconds: float, stop: threading.Event) -> bool:
    return not stop.wait(max(0.0, float(seconds)))
