"""네이버 화면 구조를 흉내 낸 로컬 HTTPS 서버 (통합 테스트용).

크롬의 --host-resolver-rules 로 *.naver.com 을 이 서버로 돌린다.
"""

from __future__ import annotations

import json
import ssl
import subprocess
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

HTML = "text/html; charset=utf-8"
JSON = "application/json; charset=utf-8"
XML = "text/xml; charset=utf-8"


def page(title: str, body: str) -> str:
    return f"<!doctype html><html><head><meta charset='utf-8'><title>{title}</title></head><body>{body}</body></html>"


ROUTES: dict[tuple[str, str], tuple[str, str]] = {
    # ---- 카페 메인 (구 화면)
    ("cafe.naver.com", "/testcafe"): (HTML, page(
        "테스트카페 : 네이버 카페",
        """<h1>테스트카페</h1>
        <script>var g_sClubId = "111";</script>
        <div id="cafe-info-data"><div class="box-g"><div class="ia-info-data2"><ul>
          <li class="mem-cnt-info"><a>멤버</a><a><em>12,345</em></a></li>
        </ul></div></div></div>
        <iframe id="cafe_main" name="cafe_main" src="/MyCafeIntro.nhn?clubid=111"></iframe>""",
    )),
    ("cafe.naver.com", "/MyCafeIntro.nhn"): (HTML, page("intro", "<p>카페 소개</p>")),
    # ---- 카페 게시글 (구 화면: cafe_main iframe, 좋아요는 늦게 표시)
    ("cafe.naver.com", "/testcafe/123"): (HTML, page(
        "첫 글 : 네이버 카페",
        '<iframe id="cafe_main" name="cafe_main" src="/ArticleRead.nhn?clubid=111&articleid=123"></iframe>',
    )),
    ("cafe.naver.com", "/ArticleRead.nhn"): (HTML, page(
        "article",
        """<div id="app"><div><div><div class="ArticleContentBox">
          <div class="article_header"><div class="ArticleTitle"><h3 class="title_text">첫 글</h3></div>
            <div class="WriterInfo"><div class="profile_area">
              <div class="profile_info"><div class="nick_box"><button class="nickname">요리왕</button></div></div>
              <div class="article_info">
              <span class="date">2026.10.01. 12:00</span><span class="count">조회 1,234</span>
            </div></div></div></div>
          <div class="article_container"><div class="ReplyBox"><div class="box_left">
            <div class="like_article"><div><a><em class="u_cnt _count" id="like"></em></a></div></div>
            <a class="button_comment">댓글 <strong>5</strong></a>
          </div></div></div>
        </div></div></div></div>
        <script>setTimeout(function(){document.getElementById('like').textContent='7';}, 1200);</script>""",
    )),
    # ---- 카페 게시글 (신 화면: DOM 에 숫자 없음, 내부 API JSON 으로만 전달)
    ("cafe.naver.com", "/f-e/cafes/111/articles/456"): (HTML, page(
        "신규 글 : 네이버 카페",
        """<div id="root">불러오는 중</div>
        <script>
        fetch('https://apis.naver.com/cafe-web/cafe-articleapi/v3/cafes/111/articles/456')
          .then(r => r.json()).then(d => {
            document.getElementById('root').innerHTML =
              '<h3>' + d.result.article.subject + '</h3><div class="x">좋아요 9</div>';
          });
        </script>""",
    )),
    ("apis.naver.com", "/cafe-web/cafe-articleapi/v3/cafes/111/articles/456"): (JSON, json.dumps({
        "result": {
            "article": {"id": 456, "subject": "신규 글", "readCount": 77, "commentCount": 3, "writer": {"nick": "신규작성자"}},
            "otherArticles": [{"id": 1, "readCount": 99999}],
        }
    })),
    # ---- 카페 목록 (평균 조회수, 브라우저 경로)
    ("cafe.naver.com", "/f-e/cafes/222/menus/0"): (HTML, page(
        "목록",
        """<div id="main-area">
          <div class="article-board" id="upperArticleList"><table><tbody>
            <tr class="board-notice"><td class="td_view">99,999</td></tr>
          </tbody></table></div>
          <div class="article-board"><table><tbody>
            <tr><td class="td_view">100</td></tr><tr><td class="td_view">200</td></tr>
            <tr><td class="td_view">1,200</td></tr>
          </tbody></table></div>
          <div class="prev-next"><a>9</a><a class="on">10</a><a>11</a></div>
        </div>""",
    )),
    # ---- 블로그 메인 (mainFrame 안에 닉네임)
    ("blog.naver.com", "/tester"): (HTML, page(
        "테스트 블로그 : 네이버 블로그",
        '<iframe id="mainFrame" name="mainFrame" src="/PostList.naver?blogId=tester"></iframe>',
    )),
    ("blog.naver.com", "/nowidget"): (HTML, page(
        "위젯 없는 블로그 : 네이버 블로그",
        '<iframe id="mainFrame" name="mainFrame" src="/PostList.naver?blogId=nowidget"></iframe>',
    )),
    ("blog.naver.com", "/PostList.naver"): (HTML, page("list", '<strong id="nickNameArea">테스터</strong>')),
    ("blog.naver.com", "/PostList.naver?blogId=tester"): (HTML, page(
        "list", '<strong id="nickNameArea">테스터</strong><p>서로이웃 23명</p><p>이웃 1,234명</p>')),
    ("blog.naver.com", "/apiblog"): (HTML, page(
        "API 블로그 : 네이버 블로그", '<iframe id="mainFrame" name="mainFrame" src="/PostList.naver?blogId=apiblog"></iframe>')),
    ("blog.naver.com", "/mobileblog"): (HTML, page(
        "모바일 블로그 : 네이버 블로그", '<iframe id="mainFrame" name="mainFrame" src="/PostList.naver?blogId=mobileblog"></iframe>')),
    ("m.blog.naver.com", "/mobileblog"): (HTML, page("모바일", "<div>모바일 블로그</div><p>31.9만명의 이웃</p>")),
    ("m.blog.naver.com", "/nowidget"): (HTML, page("모바일", "<p>12명의 이웃</p>")),
    # ---- 블로그 포스팅
    ("blog.naver.com", "/PostView.naver"): (HTML, page(
        "포스팅 제목 : 네이버 블로그",
        """<div class="blog2_container"><span class="writer"><span class="nick"><a>포스팅작성자</a></span></span></div>
        <div class="se-title-text"><span>포스팅 제목</span></div>
        <span class="se_publishDate">2026. 10. 2. 9:00</span>
        <div class="area_sympathy"><div class="u_likeit_list_module"><a><em class="u_cnt _count" id="lk"></em></a></div></div>
        <a class="btn_comment">댓글 <em id="commentCount">4</em></a>
        <script>setTimeout(function(){document.getElementById('lk').textContent='21';}, 800);</script>""",
    )),
    # ---- 방문자 위젯 API (브라우저 대체 경로)
    ("blog.naver.com", "/NVisitorgp4Ajax.nhn"): (XML, "<visitorcnts></visitorcnts>"),
    # ---- 지식iN
    ("kin.naver.com", "/qna/detail.naver"): (HTML, page(
        "질문 제목 : 지식iN",
        """<div id="content"><div class="question-content"><div>
          <div class="c-heading__title"><div class="c-heading__title-inner"><div class="title">질문 제목</div></div></div>
          <div class="c-userinfo"><div class="c-userinfo__left">
            <span>작성자</span><span class="c-userinfo__info">작성일 2026.10.01.</span><span class="c-userinfo__info">조회수 5,678</span>
          </div></div>
        </div></div></div>""",
    )),
}


class _Handler(BaseHTTPRequestHandler):
    def do_GET(self):  # noqa: N802
        host = (self.headers.get("Host") or "").split(":")[0]
        parsed = urlparse(self.path)
        found = ROUTES.get((host, f"{parsed.path}?{parsed.query}")) or ROUTES.get((host, parsed.path))
        if not found:
            self.send_response(404)
            self.end_headers()
            return
        ctype, body = found
        data = body.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, *args):
        pass


class FakeNaver:
    def __init__(self, workdir: Path):
        cert, key = workdir / "cert.pem", workdir / "key.pem"
        subprocess.run(
            ["openssl", "req", "-x509", "-newkey", "rsa:2048", "-nodes", "-days", "1",
             "-subj", "/CN=naver.com", "-keyout", str(key), "-out", str(cert)],
            check=True, capture_output=True,
        )
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        ctx.load_cert_chain(cert, key)
        self.server.socket = ctx.wrap_socket(self.server.socket, server_side=True)
        self.port = self.server.server_address[1]
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)

    def __enter__(self):
        self.thread.start()
        return self

    def __exit__(self, *exc):
        self.server.shutdown()

    def chrome_args(self) -> str:
        return (
            f'--host-resolver-rules="MAP *.naver.com 127.0.0.1:{self.port}, MAP naver.com 127.0.0.1:{self.port}" '
            "--ignore-certificate-errors --no-proxy-server --no-sandbox --disable-dev-shm-usage"
        )


class FakeHttp:
    """requests 대신 쓰는 가짜 HTTP. url 접두어 -> 응답 텍스트."""

    def __init__(self, responses: dict[str, str] | None = None):
        self.responses = responses or {}
        self.calls: list[str] = []

    def load_cookies(self, cookies):
        pass

    def get_text(self, url, referer=None):
        self.calls.append(url)
        for prefix, text in self.responses.items():
            if url.startswith(prefix):
                return text
        return None

    def resolve(self, url):
        return None

    def get_json(self, url, referer=None):
        from naver_crawler.parsing import load_json_loose

        return load_json_loose(self.get_text(url, referer))
