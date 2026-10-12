"""인스타그램 웹이 내부적으로 쓰는 JSON API 를 requests 로 호출한다 (크롬 없이).

로그인하지 않아도 프로필 정보와 최근 12개 게시물이 오지만, 많이 요청하면 인스타가 잠시 막는다.
로그인 쿠키가 있으면 같은 요청을 로그인 상태로 보내고, 릴스는 앱에 보이는 재생수까지 받는다.
"""

from __future__ import annotations

import json

import requests

IG_APP_ID = "936619743392459"  # instagram.com 웹 앱 ID (웹 페이지가 API 호출에 붙이는 값)
DEFAULT_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/155.0.0.0 Safari/537.36"
)
BASE = "https://www.instagram.com"


class InstaError(Exception):
    """한 계정 수집 실패. 메시지는 화면 · 엑셀 비고에 그대로 쓴다."""


class NotFound(InstaError):
    pass


class RateLimited(InstaError):
    """요청이 너무 잦아 인스타가 잠시 막음. 기다렸다 다시 하면 된다."""


class LoginRequired(InstaError):
    """로그인(또는 계정 보안 확인)이 있어야 진행할 수 있음. 나머지 계정도 같은 이유로 실패하므로 전체를 멈춘다."""


_WAIT_WORDS = ("wait a few minutes", "please wait", "rate limit", "try again later", "spam")
_LOGIN_WORDS = ("login_required", "require_login", "not-logged-in", "checkpoint", "challenge")


class InstaClient:
    def __init__(self, cookies: list[dict] | None = None, timeout: float = 15.0):
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": DEFAULT_UA,
            "Accept": "*/*",
            "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8",
            "X-IG-App-ID": IG_APP_ID,
            "X-Requested-With": "XMLHttpRequest",
        })
        for c in cookies or []:
            try:
                self.session.cookies.set(c["name"], c["value"], domain=c.get("domain") or ".instagram.com",
                                         path=c.get("path") or "/")
            except (KeyError, TypeError):
                continue

    @property
    def logged_in(self) -> bool:
        return bool(self.session.cookies.get("sessionid"))

    # ------------------------------------------------------------ 요청
    def get_json(self, path: str, referer: str, form: dict | None = None) -> dict:
        """form 이 있으면 POST (릴스 목록처럼 웹이 POST 로 부르는 API)."""
        headers = {"Referer": referer}
        csrf = self.session.cookies.get("csrftoken")
        if csrf:
            headers["X-CSRFToken"] = csrf
        try:
            if form is None:
                resp = self.session.get(BASE + path, headers=headers, timeout=self.timeout, allow_redirects=False)
            else:
                resp = self.session.post(BASE + path, data=form, headers=headers, timeout=self.timeout,
                                         allow_redirects=False)
        except requests.RequestException as exc:
            raise InstaError(f"인스타에 연결하지 못했습니다 ({exc.__class__.__name__}). 인터넷 연결을 확인하세요.") from exc
        return self._check(resp)

    def _check(self, resp) -> dict:
        status = resp.status_code
        text = resp.text or ""
        try:
            data = json.loads(text)
        except ValueError:
            data = None
        if status == 200 and isinstance(data, dict) and data.get("status", "ok") != "fail":
            return data

        # 여기부터는 오류 응답만 본다 (정상 응답의 소개글 글자에 반응하지 않도록)
        lowered = text[:2000].lower()
        location = (resp.headers.get("Location") or "").lower()
        if status == 404:
            raise NotFound("계정을 찾을 수 없습니다 (아이디 확인)")
        if status == 429 or any(w in lowered for w in _WAIT_WORDS):
            raise RateLimited("인스타 요청 제한에 걸렸습니다")
        to_login = 300 <= status < 400 and ("login" in location or "challenge" in location)
        if to_login or any(w in lowered for w in _LOGIN_WORDS) or (status == 200 and data is None):
            if self.logged_in:
                raise LoginRequired("인스타가 로그인 확인을 요구합니다. 크롬에서 인스타를 열어 보안 확인 후 다시 로그인하세요.")
            raise LoginRequired("인스타가 로그인을 요구합니다. 오른쪽 위 '인스타 로그인' 후 다시 시도하세요.")
        if status in (401, 403):
            raise RateLimited(f"인스타가 요청을 거절했습니다 (HTTP {status})")
        raise InstaError(f"인스타 응답을 읽지 못했습니다 (HTTP {status})")

    # ------------------------------------------------------------ API
    def profile(self, username: str) -> dict:
        """프로필 + 최근 12개 게시물 (graphql 모양)."""
        data = self.get_json(f"/api/v1/users/web_profile_info/?username={username}", f"{BASE}/{username}/")
        user = (data.get("data") or {}).get("user")
        if not isinstance(user, dict):
            raise NotFound("계정을 찾을 수 없습니다 (아이디 확인)")
        return user

    def feed(self, user_id: str, username: str, count: int = 12) -> dict:
        """로그인 필요. 게시물 목록 (릴스 재생수 포함)."""
        return self.get_json(f"/api/v1/feed/user/{user_id}/?count={count}", f"{BASE}/{username}/")

    def clips(self, user_id: str, username: str, count: int = 12) -> dict:
        """로그인 필요. 프로필 릴스 탭 목록 (피드에 안 올린 릴스 포함, 재생수 포함)."""
        form = {"target_user_id": user_id, "page_size": str(count), "include_feed_video": "true"}
        return self.get_json("/api/v1/clips/user/", f"{BASE}/{username}/reels/", form)

    def media_owner(self, media_id: str) -> str | None:
        """로그인 필요. 게시물 · 릴스 ID → 올린 계정 아이디."""
        data = self.get_json(f"/api/v1/media/{media_id}/info/", f"{BASE}/")
        items = data.get("items") or []
        user = items[0].get("user") if items and isinstance(items[0], dict) else None
        return (user or {}).get("username")
