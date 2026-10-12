"""계정 하나 수집 + 목록 순서대로 실행 (UI 와 분리 - 테스트 · CLI 에서 그대로 쓴다)."""

from __future__ import annotations

import random
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Hashable, Iterable

from insta_crawler.client import InstaClient, InstaError, LoginRequired, RateLimited
from insta_crawler.config import Settings
from insta_crawler.parsing import (
    Target,
    posts_from_feed,
    posts_from_profile,
    profile_url,
    recent_posts,
    shortcode_to_media_id,
    summarize,
    to_count,
)

STATUS_OK = "완료"
STATUS_PARTIAL = "일부 누락"
STATUS_PRIVATE = "비공개"
STATUS_FAIL = "실패"
STATUS_WAIT = "대기"
STATUS_RUNNING = "수집 중"
STATUS_CANCELLED = "중지됨"
RETRY_STATUSES = (STATUS_FAIL, STATUS_PARTIAL, STATUS_CANCELLED, STATUS_WAIT)


@dataclass(frozen=True)
class Column:
    key: str
    header: str
    kind: str = "text"  # text | int
    width: int = 12


COLUMNS: tuple[Column, ...] = (
    Column("username", "아이디", width=18),
    Column("name", "이름", width=18),
    Column("url", "프로필 링크", width=34),
    Column("followers", "팔로워", "int", width=11),
    Column("avg_likes", "평균 좋아요", "int", width=11),
    Column("avg_comments", "평균 댓글", "int", width=10),
    Column("avg_views", "평균 조회수", "int", width=11),
    Column("videos", "영상 수", "int", width=8),
)


def notes(posts: int) -> tuple[str, ...]:
    return (
        f"* 평균 좋아요 · 댓글: 올린 날짜 최신순 {posts}개 게시물 평균 (상단 고정 게시물도 날짜순으로만 포함)",
        f"* 평균 조회수: 최신 {posts}개 중 영상(릴스)만의 평균, 영상 수 = 조회수 평균에 쓴 게시물 수",
        "* 사진 게시물 조회수는 인스타가 공개하지 않아 제외",
    )


@dataclass
class RowResult:
    values: dict[str, Any] = field(default_factory=dict)
    status: str = STATUS_WAIT
    message: str = ""


class StopRun(Exception):
    """남은 계정도 같은 이유로 실패할 것이므로 실행을 멈춘다 (로그인 필요, 요청 제한 지속)."""


def collect(client: InstaClient, username: str, n_posts: int, log: Callable[[str], None] = lambda m: None) -> RowResult:
    user = client.profile(username)
    username = user.get("username") or username
    media_total = to_count(user.get("edge_owner_to_timeline_media"))
    values: dict[str, Any] = {
        "username": username,
        "name": user.get("full_name") or None,
        "url": profile_url(username),
        "followers": to_count(user.get("edge_followed_by")),
        "avg_likes": None,
        "avg_comments": None,
        "avg_views": None,
        "videos": None,
    }
    if values["followers"] is None:
        values["followers"] = to_count(user.get("follower_count"))

    posts = []
    if client.logged_in and user.get("id") and not user.get("is_private"):
        try:
            posts = posts_from_feed(client.feed(str(user["id"]), username))
        except (RateLimited, LoginRequired):
            raise
        except InstaError as exc:
            log(f"@{username}: 게시물 목록 API 실패, 프로필 응답의 게시물로 계산 ({exc})")
    if not posts:
        posts = posts_from_profile(user)

    if user.get("is_private") and not posts:
        return RowResult(values, STATUS_PRIVATE, "비공개 계정 - 게시물 지표 없음")
    if not posts:
        if media_total == 0:
            return RowResult(values, STATUS_OK, "게시물 없음")
        return RowResult(values, STATUS_PARTIAL, "게시물 정보를 받지 못했습니다 (인스타 로그인 후 다시 시도하면 대부분 해결)")

    summary = summarize(recent_posts(posts, n_posts))
    values.update(avg_likes=summary.avg_likes, avg_comments=summary.avg_comments,
                  avg_views=summary.avg_views, videos=summary.videos)
    remarks = []
    if summary.samples < n_posts:
        remarks.append(f"게시물 {summary.samples}개 기준")
    if summary.hidden_likes:
        remarks.append(f"좋아요 숨김 {summary.hidden_likes}개 제외")
    if summary.videos == 0:
        remarks.append(f"최근 {summary.samples}개 중 영상 없음")
    elif summary.avg_views is None:
        remarks.append("조회수 비공개")
    if values["followers"] is None:
        return RowResult(values, STATUS_PARTIAL, " · ".join(["누락: 팔로워", *remarks]))
    return RowResult(values, STATUS_OK, " · ".join(remarks))


def resolve(client: InstaClient, target: Target) -> str:
    """Target → 아이디. 게시물 · 릴스 링크는 로그인 상태에서만 작성자를 찾을 수 있다."""
    if target.username:
        return target.username
    if target.shortcode:
        media_id = shortcode_to_media_id(target.shortcode)
        if not client.logged_in:
            raise InstaError("게시물 링크는 인스타 로그인 후에만 작성자를 찾을 수 있습니다 (프로필 링크 권장)")
        owner = client.media_owner(media_id) if media_id else None
        if owner:
            return owner
        raise InstaError("게시물 작성자를 찾지 못했습니다 (삭제됐거나 비공개 게시물)")
    raise InstaError("링크에서 인스타 아이디를 찾지 못했습니다")


class Runner:
    def __init__(self, settings: Settings, client: InstaClient, log: Callable[[str], None] | None = None):
        self.settings = settings
        self.client = client
        self.log = log or (lambda msg: None)

    def run(
        self,
        items: Iterable[tuple[Hashable, Target]],
        stop: threading.Event,
        on_start: Callable[[Hashable], None] = lambda key: None,
        on_result: Callable[[Hashable, RowResult], None] = lambda key, res: None,
    ) -> bool:
        """순서대로 수집한다. 끝까지 하면 True, 중지되면 False. 계속할 수 없으면 StopRun."""
        items = list(items)
        n_posts = max(1, min(12, int(self.settings.posts)))
        self.log(f"{len(items)}건 수집 시작 ({'로그인' if self.client.logged_in else '비로그인'} · 최근 {n_posts}개 게시물)")
        for index, (key, target) in enumerate(items):
            if stop.is_set():
                return False
            on_start(key)
            started = time.monotonic()
            try:
                result = self._one(target, n_posts, stop)
            except StopRun as exc:
                on_result(key, RowResult({}, STATUS_FAIL, str(exc)))
                raise
            if result is None:  # 기다리는 중 중지
                on_result(key, RowResult({}, STATUS_CANCELLED, "사용자가 중지했습니다"))
                return False
            on_result(key, result)
            message = f" - {result.message}" if result.message else ""
            self.log(f"[{result.status}] {target.label} ({time.monotonic() - started:.1f}초){message}")
            if index < len(items) - 1 and not self._sleep(self.settings.request_delay, stop):
                return False
        return True

    def _one(self, target: Target, n_posts: int, stop: threading.Event) -> RowResult | None:
        waited = False
        while True:
            try:
                return collect(self.client, resolve(self.client, target), n_posts, self.log)
            except RateLimited as exc:
                if waited:
                    hint = "" if self.client.logged_in else " 또는 인스타 로그인 후"
                    raise StopRun(f"{exc} - 몇 분 뒤 '실패 재시도'{hint} 다시 하세요") from exc
                waited = True
                self.log(f"{exc}. {self.settings.cooldown}초 기다렸다 다시 시도합니다…")
                if not self._sleep(self.settings.cooldown, stop, jitter=False):
                    return None
            except LoginRequired as exc:
                raise StopRun(str(exc)) from exc
            except InstaError as exc:
                return RowResult({"url": profile_url(target.username) if target.username else None},
                                 STATUS_FAIL, str(exc))

    @staticmethod
    def _sleep(seconds: float, stop: threading.Event, jitter: bool = True) -> bool:
        """사람처럼 간격을 조금씩 흔든다 (±30%). 중지되면 False."""
        seconds = max(0.0, float(seconds))
        if jitter and seconds:
            seconds *= random.uniform(0.7, 1.3)
        return not stop.wait(seconds)
