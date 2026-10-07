"""requests 세션. 브라우저 로그인 쿠키를 공유해 네이버 내부 API 를 직접 호출한다."""

from __future__ import annotations

import requests

from naver_crawler.parsing import load_json_loose

DEFAULT_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/155.0.0.0 Safari/537.36"
)


class NaverHttp:
    def __init__(self, timeout: float = 10.0):
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": DEFAULT_UA, "Accept-Language": "ko-KR,ko;q=0.9"})

    def set_user_agent(self, ua: str | None) -> None:
        if ua:
            self.session.headers["User-Agent"] = ua

    def load_cookies(self, cookies: list[dict]) -> None:
        for c in cookies:
            try:
                self.session.cookies.set(c["name"], c["value"], domain=c.get("domain"), path=c.get("path", "/"))
            except (KeyError, TypeError):
                continue

    def get_text(self, url: str, referer: str | None = None) -> str | None:
        headers = {"Referer": referer} if referer else {}
        try:
            resp = self.session.get(url, headers=headers, timeout=self.timeout)
        except requests.RequestException:
            return None
        if resp.status_code != 200:
            return None
        resp.encoding = resp.encoding or "utf-8"
        return resp.text

    def resolve(self, url: str) -> str | None:
        """naver.me 같은 단축 링크의 최종 주소."""
        try:
            resp = self.session.get(url, timeout=self.timeout, allow_redirects=True, stream=True)
            resp.close()
        except requests.RequestException:
            return None
        return resp.url if resp.url and resp.url != url else None

    def get_json(self, url: str, referer: str | None = None):
        return load_json_loose(self.get_text(url, referer))
