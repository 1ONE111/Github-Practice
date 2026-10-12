"""실제 네이버 응답 진단 (GitHub Actions 'Diagnose' 워크플로에서 실행).

    python tools/diagnose.py <블로그ID 또는 포스팅 URL> ...

1) 크롬 없이 요청했을 때 각 주소가 무엇을 돌려주는지 (상태 코드, 핵심 키 주변 글자)
2) 실제 크롤러로 블로그 정보 / 블로그 포스팅을 수집한 결과
"""

import re
import sys
import threading
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from naver_crawler.config import Settings  # noqa: E402
from naver_crawler.crawlers import TASK_BY_ID  # noqa: E402
from naver_crawler.engine import Engine  # noqa: E402
from naver_crawler.http import DEFAULT_UA  # noqa: E402
from naver_crawler.parsing import find_key, load_json_loose, parse_blog_url  # noqa: E402

PATTERNS = [
    r'"(?:subscriberCount|buddyCount|neighborCount|followerCount|nickName|nickname|blogName|displayNickName|dayVisitorCount|totalVisitorCount)"\s*:\s*"?[^,"}]{0,40}',
    r"nickNameArea[^<]{0,80}<?[^<]{0,80}",
    r".{0,60}(?:이웃|구독자).{0,60}",
    r"visitorcnt[^>]{0,60}",
]


POST_PATTERNS = [
    r'"(?:sympathyCount|likeItCount|likeCount|commentCount|replyCount|commentCnt|sympathyCnt|blogNo|isSympathyAllowed|commentOpen|isCommentAllowed|allowComment)"\s*:\s*"?[^,"}]{0,40}',
    r'id="(?:commentCount|Comi\d+|Sympathy\d+)"[^>]{0,120}>[^<]{0,30}',
    r'class="[^"]*(?:u_cnt|_count|_commentCount|btn_comment|area_sympathy|u_likeit)[^"]*"[^>]{0,80}>[^<]{0,30}',
    r'.{0,40}(?:공감|댓글)\s*<?[^>]{0,40}>?\s*\d[\d,]*.{0,20}',
    r'(?:sympathy|commentCount|replyCount)[A-Za-z]*\s*[=:]\s*["\']?\d+',
    # 작성일
    r'class="[^"]*(?:publishDate|blog_date|se_date|_postAddDate|date)[^"]*"[^>]{0,80}>[^<]{0,40}',
    r'"(?:addDate|publishDate|writeDate|postDate|logDate|addTimestamp)"\s*:\s*"?[^,"}]{0,40}',
]


def show(session: requests.Session, name: str, url: str, referer: str | None = None,
         patterns: list[str] | None = None, raw: bool = False) -> str:
    try:
        r = session.get(url, headers={"Referer": referer} if referer else {}, timeout=15)
    except requests.RequestException as exc:
        print(f"  [{name}] ERROR {exc}")
        return ""
    body = r.text
    print(f"  [{name}] {r.status_code} {r.headers.get('content-type', '')} len={len(body)} -> {r.url}")
    if raw:
        print("      " + re.sub(r"\s+", " ", body[:900]))
        return body
    hits = []
    for pattern in patterns or PATTERNS:
        for m in re.finditer(pattern, body):
            snippet = re.sub(r"\s+", " ", m.group(0))[:160]
            if snippet not in hits:
                hits.append(snippet)
            if len(hits) >= 12:
                break
    for h in hits[:12]:
        print(f"      · {h}")
    if not hits:
        print("      (키 없음) " + re.sub(r"\s+", " ", body[:300]))
    return body


def show_dates(name: str, body: str) -> None:
    """작성일이 들어 있을 만한 곳 (태그 포함 앞뒤 글자)."""
    rx = r'(?:publishDate|blog_date|se_date|_postAddDate|addDate|"date")'
    found = 0
    for m in re.finditer(rx, body):
        print(f"      [{name} 작성일] " + re.sub(r"\s+", " ", body[max(0, m.start() - 60):m.end() + 240]))
        found += 1
        if found >= 4:
            break
    for m in list(re.finditer(r"20\d\d\.\s?\d{1,2}\.\s?\d{1,2}\.?\s?\d{1,2}:\d{2}", body))[:3]:
        print(f"      [{name} 날짜형식] " + re.sub(r"\s+", " ", body[max(0, m.start() - 120):m.end() + 20]))


def diagnose_posts(s: requests.Session, urls: list[str]) -> None:
    print("=== 포스팅: 크롬 없이 요청 ===")
    for url in urls:
        ref = parse_blog_url(url)
        bid, no = ref.blog_id, ref.log_no
        print(f"- {bid}/{no}")
        post_view = f"https://blog.naver.com/PostView.naver?blogId={bid}&logNo={no}"
        pc = show(s, "pc_postview", post_view, f"https://blog.naver.com/{bid}", POST_PATTERNS)
        show_dates("pc_postview", pc)
        mobile = show(s, "m_post", f"https://m.blog.naver.com/{bid}/{no}", None, POST_PATTERNS)
        show_dates("m_post", mobile)
        show(s, "like_api", f"https://blog.like.naver.com/v1/search/contents?suppress_response_codes=true"
             f"&q=BLOG%5B{bid}_{no}%5D&isDuplication=true", post_view, raw=True)
        info = load_json_loose(show(s, "rego", f"https://m.blog.naver.com/rego/BlogInfo.naver?blogId={bid}",
                                    f"https://m.blog.naver.com/{bid}", [r'"blogNo"\s*:\s*\d+']))
        blog_no = find_key(info, ["blogNo"]) if info else None
        if blog_no:
            show(s, "cbox", "https://apis.naver.com/commentBox/cbox/web_naver_list_jsonp.json?ticket=blog"
                 f"&templateId=default&pool=blogid&lang=ko&country=&objectId={blog_no}_201_{no}"
                 f"&pageSize=1&indexSize=10&groupId={blog_no}&listType=OBJECT&pageType=default&_callback=cb",
                 post_view, raw=True)
        show(s, "m_api_post", f"https://m.blog.naver.com/api/blogs/{bid}/posts/{no}", f"https://m.blog.naver.com/{bid}/{no}", raw=True)

    print("\n=== 포스팅: 크롤러 ===")
    settings = Settings(headless=True, keep_login=False, request_delay=0.5, page_timeout=15, save_debug_html=True)
    engine = Engine(settings, lambda msg: print(f"  log: {msg}"))
    results = {}
    try:
        engine.run(TASK_BY_ID["blog_post"], list(enumerate(urls)), threading.Event(),
                   on_result=lambda k, r: results.__setitem__(k, r))
    finally:
        engine.shutdown()
    for i, url in enumerate(urls):
        r = results.get(i)
        print(f"- {url}: {r.status if r else '-'} {r.values if r else ''} {r.message if r else ''}")


def main(args: list[str]) -> None:
    s = requests.Session()
    s.headers.update({"User-Agent": DEFAULT_UA, "Accept-Language": "ko-KR,ko;q=0.9"})
    posts = [a for a in args if a.startswith("http")]
    ids = [a for a in args if not a.startswith("http")]
    if posts:
        diagnose_posts(s, posts)
    if not ids:
        return
    print("=== 1) 크롬 없이 요청 ===")
    for blog_id in ids:
        print(f"- {blog_id}")
        show(s, "visitor", f"https://blog.naver.com/NVisitorgp4Ajax.nhn?blogId={blog_id}", f"https://blog.naver.com/{blog_id}")
        show(s, "rego", f"https://m.blog.naver.com/rego/BlogInfo.naver?blogId={blog_id}", f"https://m.blog.naver.com/{blog_id}")
        show(s, "api_blogs", f"https://m.blog.naver.com/api/blogs/{blog_id}", f"https://m.blog.naver.com/{blog_id}")
        show(s, "pc_main", f"https://blog.naver.com/{blog_id}")
        show(s, "pc_postlist", f"https://blog.naver.com/PostList.naver?blogId={blog_id}", f"https://blog.naver.com/{blog_id}")
        show(s, "m_main", f"https://m.blog.naver.com/{blog_id}")

    print("\n=== 2) 크롤러(창 없는 크롬) ===")
    settings = Settings(headless=True, keep_login=False, request_delay=0.5, page_timeout=15, save_debug_html=True)
    engine = Engine(settings, lambda msg: print(f"  log: {msg}"))
    results = {}
    try:
        engine.run(TASK_BY_ID["blog_info"], [(i, f"https://blog.naver.com/{b}") for i, b in enumerate(ids)],
                   threading.Event(), on_result=lambda k, r: results.__setitem__(k, r))
    finally:
        engine.shutdown()
    for i, blog_id in enumerate(ids):
        r = results.get(i)
        print(f"- {blog_id}: {r.status if r else '-'} {r.values if r else ''} {r.message if r else ''}")


if __name__ == "__main__":
    main(sys.argv[1:] or ["shriya"])
