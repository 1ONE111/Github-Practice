"""네트워크 없이 테스트할 수 있는 순수 함수: 링크 → 아이디, 인스타 응답 → 게시물 지표."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Iterable
from urllib.parse import unquote, urlparse

# ---------------------------------------------------------------- 입력 → 대상

_USERNAME_RE = re.compile(r"[A-Za-z0-9._]{1,30}")
_LINK_RE = re.compile(r"(?<![\w.@-])(?:https?://)?(?:[a-z0-9-]+\.)?(?:instagram\.com|instagr\.am)(?:/[^\s<>\"'`]*)?", re.I)
_MENTION_RE = re.compile(r"(?<![\w.@/])@([A-Za-z0-9._]{1,30})")
_LINK_TRAIL = ".,;:!?…·~)]}>'\""

# 아이디가 아닌 인스타 주소 첫 칸
_RESERVED = {
    "accounts", "about", "api", "challenge", "developer", "direct", "directory", "explore", "graphql",
    "legal", "locations", "oauth", "privacy", "session", "static", "terms", "topics", "web",
}
_POST_PATHS = {"p", "reel", "reels", "tv"}  # 게시물 · 릴스 단건 주소


@dataclass(frozen=True)
class Target:
    raw: str                      # 사용자가 넣은 그대로 (표 · 엑셀 링크 칸)
    username: str | None = None   # 프로필 아이디
    shortcode: str | None = None  # 게시물 · 릴스 링크면 그 코드 (로그인 시 작성자 아이디로 바꾼다)

    @property
    def label(self) -> str:
        if self.username:
            return f"@{self.username}"
        return self.raw


def valid_username(name: str | None) -> bool:
    if not name or not _USERNAME_RE.fullmatch(name):
        return False
    return not (name.startswith(".") or name.endswith(".") or ".." in name)


def parse_link(link: str) -> Target:
    """인스타 주소 하나를 Target 으로. 아이디를 못 찾으면 username/shortcode 가 모두 None."""
    raw = link.strip().rstrip(_LINK_TRAIL)
    text = raw if re.match(r"^https?://", raw, re.I) else "https://" + raw
    segs = [unquote(s) for s in urlparse(text).path.split("/") if s]
    if not segs:
        return Target(raw)
    first = segs[0].lower()
    if first in _POST_PATHS:
        if len(segs) >= 2 and re.fullmatch(r"[A-Za-z0-9_-]+", segs[1]):
            return Target(raw, shortcode=segs[1])
        return Target(raw)
    if first in ("stories", "_u", "_n") and len(segs) >= 2:
        segs = segs[1:]
        first = segs[0].lower()
    name = segs[0].lstrip("@")
    if first in _RESERVED or not valid_username(name):
        return Target(raw)
    # instagram.com/아이디/p/코드 처럼 아이디 뒤에 게시물이 붙어도 아이디만 쓴다
    return Target(raw, username=name.lower())


def parse_targets(text: str | None) -> list[Target]:
    """글이 섞인 텍스트에서 인스타 링크 · @아이디 · 아이디만 있는 줄을 순서대로 뽑는다.

    '#' 으로 시작하는 줄은 메모로 무시한다.
    """
    out: list[Target] = []
    for line in (text or "").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        links = [m.group(0) for m in _LINK_RE.finditer(stripped)]
        if links:
            out += [parse_link(link) for link in links]
            continue
        mentions = _MENTION_RE.findall(stripped)
        if mentions:
            out += [Target(f"@{m}", username=m.lower()) for m in mentions if valid_username(m)]
            continue
        bare = stripped.strip("\"'<>,;")
        if valid_username(bare.lstrip("@")):
            out.append(Target(bare, username=bare.lstrip("@").lower()))
    return out


def profile_url(username: str) -> str:
    return f"https://www.instagram.com/{username}/"


def reels_url(username: str) -> str:
    return f"https://www.instagram.com/{username}/reels/"


_SHORTCODE_ALPHABET = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_"


def shortcode_to_media_id(code: str) -> str | None:
    """게시물 코드(DAbC12xyz) → 숫자 미디어 ID. 비공개 게시물 링크의 긴 코드는 앞 11자만 쓴다."""
    value = 0
    for ch in code[:11]:
        index = _SHORTCODE_ALPHABET.find(ch)
        if index < 0:
            return None
        value = value * 64 + index
    return str(value) if value else None


# ---------------------------------------------------------------- 응답 → 지표


@dataclass(frozen=True)
class Post:
    code: str | None
    taken_at: int | None
    likes: int | None
    comments: int | None
    views: int | None
    is_video: bool


def to_count(value: Any) -> int | None:
    """숫자 또는 {'count': n} → n. 음수(숨김 표시)나 숫자가 아니면 None."""
    if isinstance(value, dict):
        value = value.get("count")
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (int, float)):
        return int(value) if value >= 0 else None
    text = str(value).replace(",", "").strip()
    return int(text) if text.isdigit() else None


def first_count(*values: Any) -> int | None:
    """값들 중 처음으로 숫자로 읽히는 것."""
    for value in values:
        count = to_count(value)
        if count is not None:
            return count
    return None


def posts_from_profile(user: dict) -> list[Post]:
    """web_profile_info 의 user.edge_owner_to_timeline_media (최근 12개, 고정 게시물 포함)."""
    media = user.get("edge_owner_to_timeline_media") or {}
    posts = []
    for edge in media.get("edges") or []:
        node = edge.get("node") if isinstance(edge, dict) else None
        if not isinstance(node, dict):
            continue
        is_video = bool(node.get("is_video")) or node.get("product_type") == "clips"
        posts.append(Post(
            code=node.get("shortcode"),
            taken_at=to_count(node.get("taken_at_timestamp")),
            likes=first_count(node.get("edge_liked_by"), node.get("edge_media_preview_like"), node.get("like_count")),
            comments=first_count(node.get("edge_media_to_comment"), node.get("edge_media_preview_comment"),
                            node.get("comment_count")),
            views=first_count(node.get("video_play_count"), node.get("video_view_count")) if is_video else None,
            is_video=is_video,
        ))
    return posts


def posts_from_feed(data: dict) -> list[Post]:
    """로그인 상태의 피드(/feed/user/{id}/) 또는 릴스 탭(/clips/user/, items[].media) 응답.
    릴스는 앱에 보이는 재생수(play_count)가 들어 있다."""
    posts = []
    for item in data.get("items") or []:
        if isinstance(item, dict) and isinstance(item.get("media"), dict):
            item = item["media"]
        if not isinstance(item, dict):
            continue
        is_video = item.get("media_type") == 2 or item.get("product_type") in ("clips", "igtv")
        posts.append(Post(
            code=item.get("code"),
            taken_at=to_count(item.get("taken_at")),
            likes=to_count(item.get("like_count")),
            comments=to_count(item.get("comment_count")),
            views=first_count(item.get("play_count"), item.get("ig_play_count"), item.get("view_count"),
                         item.get("video_view_count")) if is_video else None,
            is_video=is_video,
        ))
    return posts


def recent_posts(posts: Iterable[Post], n: int) -> list[Post]:
    """올린 날짜 최신순 n개. 상단 고정 게시물은 날짜순으로 밀려나므로 따로 빼지 않아도 된다."""
    ordered = sorted(posts, key=lambda p: p.taken_at or 0, reverse=True)
    return ordered[: max(0, n)]


def _avg(values: list[int]) -> int | None:
    return int(sum(values) / len(values) + 0.5) if values else None


@dataclass(frozen=True)
class Summary:
    samples: int             # 평균에 쓴 게시물 수
    videos: int              # 그중 영상(릴스) 수 = 조회수 평균의 표본
    avg_likes: int | None
    avg_comments: int | None
    avg_views: int | None
    hidden_likes: int        # 좋아요 수를 숨긴 게시물 수


def summarize(posts: list[Post]) -> Summary:
    likes = [p.likes for p in posts if p.likes is not None]
    return Summary(
        samples=len(posts),
        videos=sum(1 for p in posts if p.is_video),
        avg_likes=_avg(likes),
        avg_comments=_avg([p.comments for p in posts if p.comments is not None]),
        avg_views=_avg([p.views for p in posts if p.views is not None]),
        hidden_likes=len(posts) - len(likes),
    )
