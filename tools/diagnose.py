"""실제 네이버 응답 진단 (GitHub Actions 'Diagnose' 워크플로에서 실행).

    python tools/diagnose.py <블로그ID> [<블로그ID> ...]

1) 크롬 없이 요청했을 때 각 주소가 무엇을 돌려주는지 (상태 코드, 핵심 키 주변 글자)
2) 실제 크롤러(창 없는 크롬)로 블로그 정보를 수집한 결과
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

PATTERNS = [
    r'"(?:subscriberCount|buddyCount|neighborCount|followerCount|nickName|nickname|blogName|displayNickName|dayVisitorCount|totalVisitorCount)"\s*:\s*"?[^,"}]{0,40}',
    r"nickNameArea[^<]{0,80}<?[^<]{0,80}",
    r".{0,60}(?:이웃|구독자).{0,60}",
    r"visitorcnt[^>]{0,60}",
]


def show(session: requests.Session, name: str, url: str, referer: str | None = None) -> None:
    try:
        r = session.get(url, headers={"Referer": referer} if referer else {}, timeout=15)
    except requests.RequestException as exc:
        print(f"  [{name}] ERROR {exc}")
        return
    body = r.text
    print(f"  [{name}] {r.status_code} {r.headers.get('content-type', '')} len={len(body)} -> {r.url}")
    hits = []
    for pattern in PATTERNS:
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


def main(ids: list[str]) -> None:
    s = requests.Session()
    s.headers.update({"User-Agent": DEFAULT_UA, "Accept-Language": "ko-KR,ko;q=0.9"})
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
