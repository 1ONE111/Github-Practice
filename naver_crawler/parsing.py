"""브라우저 없이 테스트할 수 있는 순수 파싱 함수 모음."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any, Iterable, Iterator
from urllib.parse import parse_qs, unquote, urlparse

_NUM_RE = re.compile(r"(\d[\d,]*(?:\.\d+)?)\s*(만|천)?")
_UNITS = {"만": 10_000, "천": 1_000}


def parse_count(value: Any) -> int | None:
    """'조회 1,234' -> 1234, '1.2만' -> 12000, '999+' -> 999, '비공개' -> None."""
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    match = _NUM_RE.search(str(value))
    if not match:
        return None
    number = float(match.group(1).replace(",", ""))
    return int(round(number * _UNITS.get(match.group(2) or "", 1)))


def regex_count(text: str | None, labels: Iterable[str]) -> int | None:
    """본문 텍스트에서 '라벨 숫자' 패턴을 찾는다. 예: labels=['조회수', '조회']."""
    if not text:
        return None
    for label in labels:
        match = re.search(rf"{re.escape(label)}\s*[:：]?\s*(\d[\d,]*(?:\.\d+)?\s*(?:만|천)?)", text)
        if match:
            return parse_count(match.group(1))
    return None


_BUDDY_PATTERNS = (
    re.compile(r"(\d[\d,]*(?:\.\d+)?\s*만?)\s*명의\s*이웃"),            # 31.9만명의 이웃
    re.compile(r"(?<!서로)이웃\s*수?\s*[:：]?\s*(\d[\d,]*(?:\.\d+)?\s*만?)\s*명"),  # 이웃 1,234명
)


def buddy_count_from_text(text: str | None) -> int | None:
    """블로그 화면 글자에서 이웃수를 읽는다. '서로이웃' 숫자는 무시."""
    for pattern in _BUDDY_PATTERNS:
        match = pattern.search(text or "")
        if match:
            return parse_count(match.group(1))
    return None


def normalize_url(raw: str) -> str | None:
    text = raw.strip().strip("\"'<>")
    if not text or text.startswith("#"):
        return None
    if not re.match(r"^https?://", text, re.I):
        text = "https://" + text.lstrip("/")
    host = urlparse(text).netloc
    if "." not in host:
        return None
    return text


_URL_STOP = r"\s<>\"'`\[\](){}，、。「」『』|\\^"
_URL_RE = re.compile(
    rf"https?://[^{_URL_STOP}]+"
    rf"|(?<![\w./@-])(?:[a-z0-9-]+\.)*(?:naver\.com|naver\.me|blog\.me)(?:/[^{_URL_STOP}]*)?",
    re.I,
)
_URL_TRAIL = ".,;:!?…·~'\""


def extract_urls(text: str | None) -> list[str]:
    """아무 글이 섞인 텍스트에서 링크만 순서대로 뽑는다.

    'https://…' 형태와 'blog.naver.com/…' 처럼 앞부분이 빠진 네이버 주소를 모두 잡고,
    이메일(아이디@naver.com)은 링크로 보지 않는다. '#' 으로 시작하는 줄은 메모로 무시.
    """
    urls = []
    for line in (text or "").splitlines():
        if line.strip().startswith("#"):
            continue
        for match in _URL_RE.finditer(line):
            url = normalize_url(match.group(0).rstrip(_URL_TRAIL))
            if url:
                urls.append(url)
    return urls


def split_urls(text: str) -> list[str]:
    return extract_urls(text)


def strip_suffixes(title: str | None, suffixes: Iterable[str]) -> str | None:
    if not title:
        return None
    text = title.strip()
    for suffix in suffixes:
        if text.endswith(suffix):
            text = text[: -len(suffix)].rstrip()
    return text or None


# ---------------------------------------------------------------- JSON 탐색


def walk_dicts(obj: Any) -> Iterator[dict]:
    stack = [obj]
    while stack:
        item = stack.pop(0)
        if isinstance(item, dict):
            yield item
            stack.extend(item.values())
        elif isinstance(item, list):
            stack.extend(item)


def find_key(obj: Any, keys: Iterable[str]) -> Any:
    """중첩 JSON 에서 keys 중 하나를 가진 첫 값을 너비 우선으로 찾는다."""
    keys = list(keys)
    for d in walk_dicts(obj):
        for key in keys:
            if key in d and d[key] not in (None, ""):
                return d[key]
    return None


def find_dict(obj: Any, match: dict[str, Any], require: Iterable[str]) -> dict | None:
    """match 의 키/값이 일치하고 require 키를 모두 가진 dict 를 찾는다 (값은 문자열로 비교)."""
    require = list(require)
    for d in walk_dicts(obj):
        if all(k in d for k in require) and all(str(d.get(k)) == str(v) for k, v in match.items()):
            return d
    return None


def load_json_loose(text: str | None) -> Any:
    """JSON 또는 JSONP(callback({...})) 문자열을 파싱한다."""
    if not text:
        return None
    body = text.strip()
    if body.startswith(")]}'"):
        body = body.split("\n", 1)[-1]
    try:
        return json.loads(body)
    except ValueError:
        pass
    start, end = body.find("("), body.rfind(")")
    if 0 <= start < end:
        try:
            return json.loads(body[start + 1 : end])
        except ValueError:
            return None
    return None


# ---------------------------------------------------------------- 카페 URL

_CAFE_RESERVED = {"ca-fe", "f-e", "cafes", "web", "storyphoto", "mycafelist", "joincafe", "section"}


@dataclass
class CafeRef:
    slug: str | None = None        # cafe.naver.com/{slug}
    club_id: str | None = None     # 숫자 카페 ID
    article_id: str | None = None


def parse_cafe_url(url: str) -> CafeRef:
    ref = CafeRef()
    decoded = url
    for _ in range(3):
        nxt = unquote(decoded)
        if nxt == decoded:
            break
        decoded = nxt

    m = re.search(r"(?:clubid|cafeId)=(\d+)", decoded, re.I)
    if m:
        ref.club_id = m.group(1)
    m = re.search(r"articleid=(\d+)", decoded, re.I) or re.search(r"/articles/(\d+)", decoded)
    if m:
        ref.article_id = m.group(1)
    m = re.search(r"/cafes/([^/?#&]+)", decoded)
    if m:
        if m.group(1).isdigit():
            ref.club_id = ref.club_id or m.group(1)
        else:
            ref.slug = m.group(1)

    parsed = urlparse(url)
    segs = [s for s in parsed.path.split("/") if s]
    if not ref.slug and segs:
        first = segs[0]
        if (
            first.lower() not in _CAFE_RESERVED
            and not first.lower().endswith((".nhn", ".naver"))
            and not first.isdigit()
            and re.fullmatch(r"[A-Za-z0-9_\-]+", first)
        ):
            ref.slug = first
            if not ref.article_id and len(segs) >= 2 and segs[1].isdigit():
                ref.article_id = segs[1]
    return ref


_CLUB_ID_PATTERNS = [
    r"g_sClubId\s*=\s*[\"']?(\d+)",
    r"[\"']?(?:clubid|clubId|cafeId)[\"']?\s*[:=]\s*[\"']?(\d{3,})",
    r"search\.clubid=(\d+)",
    r"/cafes/(\d{3,})",
]


def club_id_from_html(html: str | None) -> str | None:
    if not html:
        return None
    for pattern in _CLUB_ID_PATTERNS:
        m = re.search(pattern, html)
        if m:
            return m.group(1)
    return None


# ---------------------------------------------------------------- 블로그 URL

_BLOG_RESERVED = {"postview", "postlist", "prologue", "guestbook", "profile", "market", "nvisitorgp4ajax"}


@dataclass
class BlogRef:
    blog_id: str | None = None
    log_no: str | None = None


def parse_blog_url(url: str) -> BlogRef:
    parsed = urlparse(url)
    query = parse_qs(parsed.query)
    ref = BlogRef(
        blog_id=(query.get("blogId") or [None])[0],
        log_no=(query.get("logNo") or [None])[0],
    )
    host = parsed.netloc.lower()
    segs = [s for s in parsed.path.split("/") if s]
    if host.endswith(".blog.me"):
        ref.blog_id = ref.blog_id or host.split(".")[0]
        if segs and segs[0].isdigit():
            ref.log_no = ref.log_no or segs[0]
    elif "blog.naver.com" in host and segs:
        first = segs[0]
        base = first.lower().rsplit(".", 1)[0]
        if base not in _BLOG_RESERVED and not first.lower().endswith((".naver", ".nhn")):
            ref.blog_id = ref.blog_id or first
            if len(segs) >= 2 and segs[1].isdigit():
                ref.log_no = ref.log_no or segs[1]
    if ref.blog_id and not re.fullmatch(r"[A-Za-z0-9_\-]+", ref.blog_id):
        ref.blog_id = None
    return ref


def parse_visitor_counts(xml_text: str | None) -> list[tuple[str, int]]:
    """NVisitorgp4Ajax 응답(<visitorcnt id="20261003" cnt="123"/>)을 (날짜, 방문자수) 목록으로."""
    if not xml_text:
        return []
    result = []
    for tag in re.findall(r"<visitorcnt\b[^>]*>", xml_text, re.I):
        day = re.search(r"\bid=\"(\d+)\"", tag)
        cnt = re.search(r"\bcnt=\"(\d+)\"", tag)
        if cnt:
            result.append((day.group(1) if day else "", int(cnt.group(1))))
    return result
