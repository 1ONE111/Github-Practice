"""수집 작업 정의.

각 항목은 여러 방법을 순서대로 시도한다.
  1) 화면 요소(선택자)            - 원래 프로그램과 같은 방식
  2) 페이지가 내부적으로 받은 JSON - 화면 구조가 바뀌어도 잘 안 깨짐
  3) 네이버 API 직접 호출          - 브라우저 로그인 쿠키 공유
  4) 본문 텍스트 정규식            - 최후 수단
"""

from __future__ import annotations

import datetime as dt
import threading
from urllib.parse import urlparse
from dataclasses import dataclass, field
from typing import Any, Callable

from selenium.common.exceptions import WebDriverException

from naver_crawler.browser import BrowserManager, CapturedResponse, Page
from naver_crawler.config import Settings, debug_dir
from naver_crawler.http import NaverHttp
from naver_crawler.parsing import (
    BlogRef,
    CafeRef,
    buddy_count_from_text,
    club_id_from_html,
    find_dict,
    find_key,
    parse_blog_url,
    parse_cafe_url,
    parse_count,
    parse_visitor_counts,
    regex_count,
    strip_suffixes,
    walk_dicts,
)

CAFE_TITLE_SUFFIXES = [": 네이버 카페", ":네이버 카페", "- 네이버 카페", "네이버 카페"]
BLOG_TITLE_SUFFIXES = [": 네이버 블로그", ":네이버 블로그", "- 네이버 블로그", "네이버 블로그"]
KIN_TITLE_SUFFIXES = [": 지식iN", ":지식iN", "- 지식iN", " : 네이버 지식iN"]

STATUS_OK = "완료"
STATUS_PARTIAL = "일부 누락"
STATUS_FAIL = "실패"
STATUS_WAIT = "대기"
STATUS_RUNNING = "수집 중"
STATUS_CANCELLED = "중지됨"
STATUS_NO_WIDGET = "위젯없음"     # 방문자 위젯을 꺼둔 블로그. 엑셀 본 시트에서 자동 제외
EXCLUDED_STATUSES = (STATUS_NO_WIDGET,)


@dataclass(frozen=True)
class Column:
    key: str
    header: str
    kind: str = "text"      # text | int
    width: int = 14         # 엑셀 기본 열 너비
    required: bool = False  # 빠지면 '일부 누락' 처리


@dataclass
class RowResult:
    values: dict[str, Any] = field(default_factory=dict)
    status: str = STATUS_WAIT
    message: str = ""


@dataclass(frozen=True)
class TaskSpec:
    id: str
    title: str
    description: str
    placeholder: str
    columns: tuple[Column, ...]
    run: Callable[["Context", str], RowResult]
    notes: tuple[str, ...] = ()  # 엑셀 표 아래 '*' 주석
    sort_desc: str | None = None  # 이 열 기준 내림차순 정렬 (엑셀 · 수집 완료 후 표)


class Context:
    """한 번의 수집 작업 동안 공유되는 자원."""

    def __init__(
        self,
        browser: BrowserManager,
        http: NaverHttp,
        settings: Settings,
        selectors: dict,
        stop: threading.Event,
        log: Callable[[str], None] = lambda msg: None,
    ):
        self.browser = browser
        self.http = http
        self.settings = settings
        self.selectors = selectors
        self.stop = stop
        self.log = log
        self._cookies_synced = False

    def page(self) -> Page:
        return Page(self.browser.driver(), self.stop, self.settings.page_timeout)

    def api_json(self, url: str, referer: str):
        if not self._cookies_synced and self.browser.is_running():
            self.http.load_cookies(self.browser.naver_cookies())
            self._cookies_synced = True
        return self.http.get_json(url, referer)

    def expand(self, url: str) -> str:
        """naver.me 단축 링크면 실제 주소로 바꾼다 (요청 → 안 되면 브라우저로)."""
        if not urlparse(url).netloc.lower().endswith("naver.me"):
            return url
        final = self.http.resolve(url)
        if not final:
            page = self.page()
            page.open(url, [])
            page.wait_until(lambda: "naver.me" not in page.driver.current_url, timeout=8)
            final = page.driver.current_url
        if final and final != url:
            self.log(f"단축 링크 → {final}")
            return final
        return url

    def api_text(self, url: str, referer: str):
        if not self._cookies_synced and self.browser.is_running():
            self.http.load_cookies(self.browser.naver_cookies())
            self._cookies_synced = True
        return self.http.get_text(url, referer)


def finish(task: TaskSpec, values: dict, ctx: Context | None = None, page: Page | None = None, note: str = "") -> RowResult:
    required = [c for c in task.columns if c.required]
    missing = [c.header for c in required if values.get(c.key) in (None, "")]
    if required and len(missing) == len(required):
        status = STATUS_FAIL
        message = note or "값을 찾지 못했습니다 (로그인이 필요한 글이거나 화면 구조가 바뀌었을 수 있음)"
    elif missing:
        status = STATUS_PARTIAL
        message = "누락: " + ", ".join(missing) + (f" · {note}" if note else "")
    else:
        status = STATUS_OK
        message = note
    if status != STATUS_OK and ctx and page and ctx.settings.save_debug_html:
        saved = page.save_debug(debug_dir(), task.id)
        if saved:
            message += f" [HTML 저장: {saved.name}]"
    return RowResult(values, status, message)


def _first(*values):
    for v in values:
        if v not in (None, ""):
            return v
    return None


VIEW_LABELS = ["조회수", "조회"]
COMMENT_LABELS = ["댓글수", "댓글"]
LIKE_LABELS = ["좋아요", "공감"]
MEMBER_LABELS = ["멤버수", "회원수", "멤버", "회원"]


def _count(text: str | None, labels: list[str]) -> int | None:
    """'작성일 2024.10.07 조회수 123' 처럼 숫자가 여러 개면 라벨 옆 숫자를 우선한다."""
    return _first(regex_count(text, labels), parse_count(text))


def _format_ts(value) -> str | None:
    if value in (None, ""):
        return None
    if isinstance(value, (int, float)) or (isinstance(value, str) and value.isdigit()):
        num = float(value)
        if num > 1e12:
            num /= 1000
        try:
            return dt.datetime.fromtimestamp(num).strftime("%Y.%m.%d %H:%M")
        except (OverflowError, OSError, ValueError):
            return None
    return str(value)


# ================================================================ 카페 공통


def _pick_cafe_dict(responses: list[CapturedResponse], ref: CafeRef, need: str) -> dict | None:
    candidates = []
    for resp in responses:
        for d in walk_dicts(resp.data):
            if need in d:
                candidates.append(d)
    for d in candidates:
        ids = {str(d.get(k)) for k in ("cafeId", "clubId", "clubid", "id") if d.get(k) is not None}
        urls = {str(d.get(k)).lower() for k in ("cafeUrl", "clubUrl", "url", "cluburl") if d.get(k)}
        if (ref.club_id and ref.club_id in ids) or (ref.slug and ref.slug.lower() in urls):
            return d
    return candidates[0] if len(candidates) == 1 else None


def _cafe_api_info(ctx: Context, ref: CafeRef) -> dict | None:
    urls = []
    if ref.slug:
        urls.append(f"https://apis.naver.com/cafe-web/cafe2/CafeGateInfo.json?cluburl={ref.slug}")
    if ref.club_id:
        urls.append(f"https://apis.naver.com/cafe-web/cafe2/CafeGateInfo.json?clubid={ref.club_id}")
    for url in urls:
        data = ctx.api_json(url, "https://cafe.naver.com/")
        if data is None:
            continue
        found = _pick_cafe_dict([CapturedResponse(url, data)], ref, "cafeId") or _pick_cafe_dict(
            [CapturedResponse(url, data)], ref, "memberCount"
        )
        if found:
            return found
    return None


def resolve_club_id(ctx: Context, ref: CafeRef, page: Page | None = None) -> str | None:
    if ref.club_id:
        return ref.club_id
    if page is not None:
        d = _pick_cafe_dict(page.captured_json(), ref, "cafeId")
        if d and d.get("cafeId"):
            return str(d["cafeId"])
        found = club_id_from_html(page.all_sources())
        if found:
            return found
    info = _cafe_api_info(ctx, ref)
    if info:
        return str(_first(info.get("cafeId"), info.get("clubId"), info.get("clubid")) or "") or None
    return None


# ================================================================ 1. 카페 정보


def crawl_cafe_info(ctx: Context, url: str) -> RowResult:
    task = TASK_BY_ID["cafe_info"]
    sel = ctx.selectors["cafe_info"]
    ref = parse_cafe_url(url)
    page = ctx.page()
    page.open(url, sel.get("frames", []))

    def from_json():
        return _pick_cafe_dict(page.captured_json(), ref, "memberCount")

    page.wait_until(lambda: page.text(sel["members"]) is not None or from_json() is not None)

    note = ""
    raw_members = page.text(sel["members"])
    members = _count(raw_members, MEMBER_LABELS)
    if raw_members and "비공개" in raw_members:
        note = "회원수 비공개 카페"
    name = page.text(sel["name"])

    info = from_json()
    if info:
        members = _first(members, parse_count(info.get("memberCount")))
        name = _first(name, info.get("cafeName"), info.get("clubName"), info.get("name"))
    club_id = resolve_club_id(ctx, ref, page)
    if (members is None and not note) or not name:
        api = _cafe_api_info(ctx, CafeRef(ref.slug, club_id))
        if api:
            members = _first(members, parse_count(api.get("memberCount")))
            name = _first(name, api.get("cafeName"), api.get("clubName"))
    if members is None and not note:
        members = regex_count(page.body_text(), MEMBER_LABELS)
    name = _first(name, strip_suffixes(page.top_title(), CAFE_TITLE_SUFFIXES))
    return finish(task, {"name": name, "members": members, "club_id": club_id}, ctx, page, note)


# ================================================================ 2. 카페 게시글


def crawl_cafe_article(ctx: Context, url: str) -> RowResult:
    task = TASK_BY_ID["cafe_article"]
    sel = ctx.selectors["cafe_article"]
    ref = parse_cafe_url(url)
    page = ctx.page()
    page.open(url, sel.get("frames", ["cafe_main"]))

    def from_json() -> dict | None:
        if not ref.article_id:
            return None
        for resp in page.captured_json():
            d = find_dict(resp.data, {"articleId": ref.article_id}, ["readCount"]) or find_dict(
                resp.data, {"id": ref.article_id}, ["readCount"]
            )
            if d is None and f"/articles/{ref.article_id}" in resp.url:
                d = find_dict(resp.data, {}, ["readCount"])
            if d:
                return d
        return None

    page.wait_until(lambda: page.text(sel["views"], need_digit=True) is not None or from_json() is not None)
    # 좋아요 숫자는 늦게 붙으므로 잠깐 더 기다린다
    page.wait_until(lambda: page.text(sel["likes"], need_digit=True) is not None, timeout=4)

    values = {
        "title": page.text(sel["title"]),
        "views": _count(page.text(sel["views"], need_digit=True), VIEW_LABELS),
        "comments": _count(page.text(sel["comments"], need_digit=True), COMMENT_LABELS),
        "likes": _count(page.text(sel["likes"], need_digit=True), LIKE_LABELS),
        "date": page.text(sel["date"], need_digit=True),
        "nickname": page.text(sel.get("nickname", [])),
    }

    def merge(d: dict | None):
        if not d:
            return
        writer = d.get("writer") if isinstance(d.get("writer"), dict) else {}
        values["nickname"] = _first(
            values["nickname"], writer.get("nick"), writer.get("nickname"), writer.get("nickName"),
            d.get("writerNickname"), d.get("nickname"),
        )
        values["title"] = _first(values["title"], d.get("subject"), d.get("title"))
        values["views"] = _first(values["views"], parse_count(d.get("readCount")))
        values["comments"] = _first(values["comments"], parse_count(d.get("commentCount")))
        values["likes"] = _first(
            values["likes"], parse_count(_first(d.get("likeItCount"), d.get("likeCount"), d.get("sympathyCount")))
        )
        values["date"] = _first(values["date"], _format_ts(_first(d.get("writeDateTimestamp"), d.get("writeDate"))))

    merge(from_json())
    if any(values[k] is None for k in ("views", "comments", "likes")) and ref.article_id:
        club_id = resolve_club_id(ctx, ref, page)
        if club_id:
            data = ctx.api_json(
                f"https://apis.naver.com/cafe-web/cafe-articleapi/v2.1/cafes/{club_id}/articles/{ref.article_id}"
                "?query=&useCafeId=true&requestFrom=A",
                "https://cafe.naver.com/",
            )
            merge(find_dict(data, {}, ["readCount"]) if data else None)
            if values["likes"] is None and data is not None:
                values["likes"] = parse_count(find_key(data, ["likeItCount", "likeCount"]))

    if any(values[k] is None for k in ("views", "comments", "likes")):
        body = page.body_text()
        values["views"] = _first(values["views"], regex_count(body, VIEW_LABELS))
        values["comments"] = _first(values["comments"], regex_count(body, COMMENT_LABELS))
        values["likes"] = _first(values["likes"], regex_count(body, ["좋아요"]))
    values["title"] = _first(values["title"], strip_suffixes(page.top_title(), CAFE_TITLE_SUFFIXES))
    return finish(task, values, ctx, page)


# ================================================================ 3. 카페 N페이지 평균 조회수


def extract_read_counts(data: Any) -> list[int]:
    """게시글 목록 JSON 에서 공지를 뺀 readCount 목록을 꺼낸다 (가장 긴 목록 기준)."""
    best: list[int] = []
    stack = [data]
    while stack:
        item = stack.pop()
        if isinstance(item, dict):
            stack.extend(item.values())
        elif isinstance(item, list):
            counts = []
            for el in item:
                if not isinstance(el, dict):
                    continue
                body = el.get("item") if isinstance(el.get("item"), dict) else el
                kind = str(el.get("type", "") or body.get("type", "")).upper()
                if "NOTICE" in kind or body.get("isNotice") is True or body.get("notice") is True:
                    continue
                if "readCount" in body:
                    count = parse_count(body.get("readCount"))
                    if count is not None:
                        counts.append(count)
            if len(counts) > len(best):
                best = counts
            stack.extend(item)
    return best


def crawl_cafe_avg(ctx: Context, url: str) -> RowResult:
    task = TASK_BY_ID["cafe_avg"]
    sel = ctx.selectors["cafe_list"]
    page_no = max(1, int(ctx.settings.avg_page))
    per = max(1, int(ctx.settings.avg_per_page))
    ref = parse_cafe_url(url)
    values: dict[str, Any] = {"avg": None, "samples": None, "page": page_no, "club_id": None}
    page: Page | None = None
    note = ""

    club_id = ref.club_id
    if not club_id:
        page = ctx.page()
        page.open(url, [])
        page.wait_until(lambda: club_id_from_html(page.all_sources()) is not None, timeout=min(10, ctx.settings.page_timeout))
        club_id = resolve_club_id(ctx, ref, page)
    if not club_id:
        return RowResult(values, STATUS_FAIL, "카페 ID 를 찾지 못했습니다. 카페 메인 주소가 맞는지 확인하세요.")
    values["club_id"] = club_id

    counts: list[int] = []
    page = page or ctx.page()  # 로그인 쿠키를 API 호출에 쓰기 위해 먼저 띄운다
    # (1) 페이지 번호가 명시되는 목록 API
    for api in (
        f"https://apis.naver.com/cafe-web/cafe2/ArticleListV2dot1.json?search.clubid={club_id}"
        f"&search.queryType=lastArticle&search.page={page_no}&search.perPage={per}&search.boardtype=L&ad=false",
        f"https://apis.naver.com/cafe-web/cafe-boardlist-api/v1/cafes/{club_id}/menus/0/articles"
        f"?page={page_no}&pageSize={per}&sortBy=TIME&viewType=L",
    ):
        data = ctx.api_json(api, f"https://cafe.naver.com/f-e/cafes/{club_id}/menus/0")
        counts = extract_read_counts(data) if data is not None else []
        if counts:
            break

    # (2) 브라우저로 목록 화면을 열어 확인
    if not counts:
        page_marks = (f"page={page_no}&", f"page={page_no}", f"page%3D{page_no}")
        for list_url in (
            f"https://cafe.naver.com/f-e/cafes/{club_id}/menus/0?viewType=L&page={page_no}&size={per}",
            f"https://cafe.naver.com/ArticleList.nhn?search.clubid={club_id}&search.boardtype=L"
            f"&search.page={page_no}&userDisplay={per}",
        ):
            page.open(list_url, sel.get("frames", ["cafe_main"]))

            def page_json() -> list[int]:
                for resp in page.captured_json(lambda u: any(m in u for m in page_marks)):
                    found = extract_read_counts(resp.data)
                    if found:
                        return found
                return []

            page.wait_until(lambda: bool(page.list_view_texts(sel["rows"], sel["view_cell"])) or bool(page_json()))
            counts = page_json()
            if not counts:
                current = page.text(
                    [".prev-next a.on", "[aria-current='page']", "[aria-pressed='true']", "[class*='Pagination'] [class*='active']"],
                    need_digit=True,
                )
                if current and parse_count(current) not in (None, page_no):
                    continue  # 다른 페이지가 열렸으므로 믿을 수 없음
                counts = [c for c in (parse_count(t) for t in page.list_view_texts(sel["rows"], sel["view_cell"])) if c is not None]
                if counts and not current:
                    note = "페이지 번호 확인 불가"
            if counts:
                break

    if not counts:
        return finish(task, values, ctx, page, "게시글 목록을 읽지 못했습니다 (가입/로그인이 필요한 카페일 수 있음)")
    counts = counts[:per]
    values["avg"] = int(sum(counts) / len(counts))
    values["samples"] = len(counts)
    return finish(task, values, ctx, page, note)


# ================================================================ 4. 블로그 정보


def _visitor_counts(ctx: Context, blog_id: str, page: Page | None) -> list[tuple[str, int]]:
    """방문자 위젯이 꺼진 블로그는 빈 목록을 돌려준다 (예외로 전체 작업이 멈추지 않게)."""
    url = f"https://blog.naver.com/NVisitorgp4Ajax.nhn?blogId={blog_id}"
    counts = parse_visitor_counts(ctx.api_text(url, f"https://blog.naver.com/{blog_id}"))
    if not counts and page is not None:
        try:
            page.open(url, [])
            counts = parse_visitor_counts(page.source())
        except WebDriverException:
            counts = []
    return counts


BUDDY_KEYS = ["subscriberCount", "buddyCount", "neighborCount", "followerCount"]
MOBILE_BLOG_APIS = (
    "https://m.blog.naver.com/api/blogs/{blog_id}",
    "https://m.blog.naver.com/rego/BlogInfo.naver?blogId={blog_id}",
)


class _BlogApi:
    """모바일 블로그 정보 API 응답 (필요할 때 한 번만 요청)."""

    def __init__(self, ctx: Context, blog_id: str):
        self.ctx, self.blog_id = ctx, blog_id
        self._data: list | None = None

    def data(self) -> list:
        if self._data is None:
            self._data = []
            for api in MOBILE_BLOG_APIS:
                found = self.ctx.api_json(api.format(blog_id=self.blog_id), f"https://m.blog.naver.com/{self.blog_id}")
                if found is not None:
                    self._data.append(found)
        return self._data

    def find(self, keys: list[str]):
        for data in self.data():
            value = find_key(data, keys)
            if value not in (None, ""):
                return value
        return None


def _blog_profile_api(ctx: Context, blog_id: str) -> tuple[str | None, str | None]:
    """(블로그명, 닉네임) - 화면에서 못 찾았을 때 모바일 API 로."""
    api = _BlogApi(ctx, blog_id)
    return api.find(["blogName"]), api.find(["nickName", "nickname"])


def _buddy_count(ctx: Context, page: Page, sel: dict, api: _BlogApi) -> int | None:
    """이웃수: PC 화면 → 페이지 내부 JSON → 화면 글자 → 모바일 API → 모바일 블로그 화면."""
    buddies = _count(page.text(sel.get("buddies", []), need_digit=True), ["이웃"])
    if buddies is None:
        for resp in page.captured_json():
            buddies = _first(buddies, parse_count(find_key(resp.data, BUDDY_KEYS)))
    if buddies is None:
        buddies = _first(buddy_count_from_text(page.body_text()), buddy_count_from_text(page.top_body_text()))
    if buddies is None:
        buddies = parse_count(api.find(BUDDY_KEYS))
    if buddies is None:
        page.open(f"https://m.blog.naver.com/{api.blog_id}", [])

        def mobile() -> int | None:
            for resp in page.captured_json():
                found = parse_count(find_key(resp.data, BUDDY_KEYS))
                if found is not None:
                    return found
            return buddy_count_from_text(page.body_text())

        page.wait_until(lambda: mobile() is not None, timeout=min(8, ctx.settings.page_timeout))
        buddies = mobile()
    return buddies


def crawl_blog_info(ctx: Context, url: str) -> RowResult:
    task = TASK_BY_ID["blog_info"]
    sel = ctx.selectors["blog_info"]
    ref: BlogRef = parse_blog_url(url)
    if not ref.blog_id:
        return RowResult({}, STATUS_FAIL, "주소에서 블로그 ID 를 찾지 못했습니다.")
    blog_id = ref.blog_id
    api = _BlogApi(ctx, blog_id)
    page = ctx.page()
    page.open(f"https://blog.naver.com/{blog_id}", sel.get("frames", ["mainFrame"]))
    # 프로필 위젯이 없는 블로그도 있으므로 오래 붙잡지 않는다
    page.wait_until(lambda: page.text(sel["nickname"]) is not None, timeout=min(8, ctx.settings.page_timeout))

    nickname = page.text(sel["nickname"])
    name = _first(strip_suffixes(page.top_title(), BLOG_TITLE_SUFFIXES), page.text(sel["name"]))
    if not nickname or not name:
        for resp in page.captured_json():
            nickname = _first(nickname, find_key(resp.data, ["nickName", "nickname"]))
            name = _first(name, find_key(resp.data, ["blogName"]))
    if not nickname or not name:
        nickname = _first(nickname, api.find(["nickName", "nickname"]))
        name = _first(name, api.find(["blogName"]))

    buddies = _buddy_count(ctx, page, sel, api)
    counts = _visitor_counts(ctx, blog_id, page)[-5:]  # 최근 5일
    values = {
        "name": name,
        "nickname": nickname,
        "avg": int(sum(c for _, c in counts) / len(counts)) if counts else None,
        "buddies": buddies,
    }
    if not counts and (name or nickname):
        return RowResult(values, STATUS_NO_WIDGET, "방문자 위젯이 없는 블로그 (엑셀 저장 시 자동 제외)")
    return finish(task, values, ctx, page)


# ================================================================ 5. 블로그 포스팅


def _like_count_from(data: Any, cid: str | None) -> int | None:
    for d in walk_dicts(data):
        reactions = d.get("reactions")
        if not isinstance(reactions, list):
            continue
        if cid and d.get("contentsId") not in (None, cid):
            continue
        total = sum(parse_count(r.get("count")) or 0 for r in reactions if isinstance(r, dict))
        return total
    return None


def crawl_blog_post(ctx: Context, url: str) -> RowResult:
    task = TASK_BY_ID["blog_post"]
    sel = ctx.selectors["blog_post"]
    ref = parse_blog_url(url)
    target = url
    if ref.blog_id and ref.log_no:
        target = f"https://blog.naver.com/PostView.naver?blogId={ref.blog_id}&logNo={ref.log_no}"
    cid = f"{ref.blog_id}_{ref.log_no}" if ref.blog_id and ref.log_no else None

    page = ctx.page()
    page.open(target, sel.get("frames", ["mainFrame"]))
    page.wait_until(lambda: page.text(sel["title"]) is not None or page.text(sel["comments"], need_digit=True) is not None)
    page.wait_until(lambda: page.text(sel["likes"], need_digit=True) is not None, timeout=5)

    values = {
        "title": page.text(sel["title"]),
        "likes": _count(page.text(sel["likes"], need_digit=True), LIKE_LABELS),
        "comments": _count(page.text(sel["comments"], need_digit=True), COMMENT_LABELS),
        "date": page.text(sel["date"], need_digit=True),
        "nickname": page.text(sel.get("nickname", [])),
    }
    if values["nickname"] is None:
        for resp in page.captured_json():
            values["nickname"] = _first(values["nickname"], find_key(resp.data, ["nickName", "nickname"]))
    if values["nickname"] is None and ref.blog_id:
        values["nickname"] = _blog_profile_api(ctx, ref.blog_id)[1]
    if values["likes"] is None or values["comments"] is None:
        for resp in page.captured_json():
            if values["likes"] is None and "like.naver.com" in resp.url:
                values["likes"] = _like_count_from(resp.data, cid)
            if values["comments"] is None and "comment" in resp.url.lower():
                count = find_key(resp.data, ["count"])
                if isinstance(count, dict):
                    values["comments"] = parse_count(_first(count.get("comment"), count.get("total")))
    if values["likes"] is None and cid:
        data = ctx.api_json(
            f"https://blog.like.naver.com/v1/search/contents?suppress_response_codes=true&q=BLOG[{cid}]",
            f"https://blog.naver.com/{ref.blog_id}/{ref.log_no}",
        )
        values["likes"] = _like_count_from(data, cid) if data is not None else None
    values["title"] = _first(values["title"], strip_suffixes(page.top_title(), BLOG_TITLE_SUFFIXES))
    return finish(task, values, ctx, page)


# ================================================================ 6. 지식iN


def crawl_kin(ctx: Context, url: str) -> RowResult:
    task = TASK_BY_ID["kin"]
    sel = ctx.selectors["kin"]
    page = ctx.page()
    page.open(url, sel.get("frames", []))
    page.wait_until(lambda: page.text(sel["views"], need_digit=True, contains=["조회"]) is not None)

    views = _count(page.text(sel["views"], need_digit=True, contains=["조회"]), VIEW_LABELS)
    if views is None:
        views = regex_count(page.body_text(), VIEW_LABELS)
    title = _first(page.text(sel["title"]), strip_suffixes(page.top_title(), KIN_TITLE_SUFFIXES))
    return finish(task, {"title": title, "views": views}, ctx, page)


# ================================================================ 작업 목록

TASKS: tuple[TaskSpec, ...] = (
    TaskSpec(
        "cafe_info",
        "카페 정보",
        "카페 주소를 넣으면 카페명과 회원수를 가져옵니다.",
        "https://cafe.naver.com/카페주소\n한 줄에 하나씩 입력",
        (
            Column("name", "카페명", width=26, required=True),
            Column("members", "회원수", "int", width=12, required=True),
            Column("club_id", "카페 ID", width=12),
        ),
        crawl_cafe_info,
    ),
    TaskSpec(
        "cafe_article",
        "카페 게시글",
        "게시글 주소로 작성자 닉네임 · 조회수 · 댓글수 · 좋아요를 가져옵니다.",
        "https://cafe.naver.com/카페주소/글번호\n한 줄에 하나씩 입력",
        (
            Column("title", "제목", width=36),
            Column("nickname", "닉네임", width=14),
            Column("views", "조회수", "int", width=11, required=True),
            Column("comments", "댓글수", "int", width=11, required=True),
            Column("likes", "좋아요", "int", width=11, required=True),
            Column("date", "작성일", width=15),
        ),
        crawl_cafe_article,
    ),
    TaskSpec(
        "cafe_avg",
        "카페 평균 조회수",
        "전체글보기 N페이지(기본 10페이지 · 15개) 글들의 평균 조회수를 계산합니다.",
        "https://cafe.naver.com/카페주소\n한 줄에 하나씩 입력",
        (
            Column("avg", "평균 조회수", "int", width=14, required=True),
            Column("samples", "표본 글 수", "int", width=11),
            Column("page", "페이지", "int", width=9),
            Column("club_id", "카페 ID", width=12),
        ),
        crawl_cafe_avg,
        ("* 평균 조회수: 전체글보기 해당 페이지 글(공지 제외)의 조회수 평균",),
    ),
    TaskSpec(
        "blog_info",
        "블로그 정보",
        "블로그 주소로 닉네임 · 블로그명 · 이웃수 · 일방문자수(5일 평균)를 가져옵니다. 이웃 많은 순 정렬.",
        "https://blog.naver.com/블로그아이디\n한 줄에 하나씩 입력",
        (
            Column("nickname", "닉네임", width=16, required=True),
            Column("name", "블로그명", width=26, required=True),
            Column("url", "블로그링크", width=34),
            Column("buddies", "이웃수", "int", width=9, required=True),
            Column("avg", "일방문자수(5일 평균)", "int", width=14, required=True),
        ),
        crawl_blog_info,
        (
            "* 이웃수: 수집 시점 네이버 블로그 표시 기준, 이웃 많은 순 정렬",
            "* 일방문자수(5일 평균): 네이버 블로그 방문자 위젯 기준 최근 5일 평균 (오늘 포함)",
        ),
        sort_desc="buddies",
    ),
    TaskSpec(
        "blog_post",
        "블로그 포스팅",
        "포스팅 주소로 작성자 닉네임 · 공감수 · 댓글수를 가져옵니다.",
        "https://blog.naver.com/블로그아이디/글번호\n한 줄에 하나씩 입력",
        (
            Column("title", "제목", width=36),
            Column("nickname", "닉네임", width=14),
            Column("likes", "공감수", "int", width=11, required=True),
            Column("comments", "댓글수", "int", width=11, required=True),
            Column("date", "작성일", width=15),
        ),
        crawl_blog_post,
    ),
    TaskSpec(
        "kin",
        "지식iN",
        "지식iN 질문 주소로 조회수를 가져옵니다.",
        "https://kin.naver.com/qna/detail.naver?d1id=…&docId=…\n한 줄에 하나씩 입력",
        (
            Column("title", "제목", width=40),
            Column("views", "조회수", "int", width=11, required=True),
        ),
        crawl_kin,
    ),
)

TASK_BY_ID: dict[str, TaskSpec] = {t.id: t for t in TASKS}
