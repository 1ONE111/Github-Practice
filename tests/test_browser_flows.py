"""실제 크롬으로 가짜 네이버 페이지를 열어 수집 흐름을 검증한다.

NC_TEST_CHROME (chrome 실행 파일), NC_TEST_DRIVER (chromedriver) 환경 변수가 있을 때만 실행.
"""

import os
import threading

import pytest

from naver_crawler.config import Settings
from naver_crawler.crawlers import TASK_BY_ID
from naver_crawler.engine import Engine
from tests.fake_naver import FakeHttp, FakeNaver

CHROME = os.environ.get("NC_TEST_CHROME")
DRIVER = os.environ.get("NC_TEST_DRIVER")
pytestmark = pytest.mark.skipif(not (CHROME and DRIVER), reason="NC_TEST_CHROME / NC_TEST_DRIVER 미설정")


@pytest.fixture(scope="module")
def engine(tmp_path_factory, monkeypatch_module):
    home = tmp_path_factory.mktemp("home")
    monkeypatch_module.setenv("NAVER_CRAWLER_HOME", str(home))
    with FakeNaver(tmp_path_factory.mktemp("cert")) as fake:
        monkeypatch_module.setenv("NAVER_CRAWLER_CHROME_ARGS", fake.chrome_args())
        settings = Settings(headless=True, keep_login=False, request_delay=0, page_timeout=5,
                            chromedriver_path=DRIVER, chrome_binary=CHROME)
        eng = Engine(settings)
        yield eng
        eng.shutdown()


@pytest.fixture(scope="module")
def monkeypatch_module():
    mp = pytest.MonkeyPatch()
    yield mp
    mp.undo()


def run(engine, task_id, urls, http=None):
    engine.http = http or FakeHttp()
    results = {}
    engine.run(TASK_BY_ID[task_id], list(enumerate(urls)), threading.Event(),
               on_result=lambda key, res: results.__setitem__(key, res))
    return [results[i] for i in range(len(urls))]


def test_cafe_info_old_layout(engine):
    (res,) = run(engine, "cafe_info", ["https://cafe.naver.com/testcafe"])
    assert res.status == "완료", res.message
    assert res.values["name"] == "테스트카페"
    assert res.values["members"] == 12345
    assert res.values["club_id"] == "111"


def test_cafe_article_iframe_and_late_like(engine):
    (res,) = run(engine, "cafe_article", ["https://cafe.naver.com/testcafe/123"])
    assert res.status == "완료", res.message
    assert res.values == {"title": "첫 글", "views": 1234, "comments": 5, "likes": 7,
                          "date": "2026.10.01. 12:00", "nickname": "요리왕"}


def test_cafe_article_new_layout_from_captured_json(engine):
    (res,) = run(engine, "cafe_article", ["https://cafe.naver.com/f-e/cafes/111/articles/456"])
    assert res.status == "완료", res.message
    assert res.values["views"] == 77  # 다른 글의 readCount(99999)를 잡으면 안 됨
    assert res.values["comments"] == 3
    assert res.values["likes"] == 9
    assert res.values["title"] == "신규 글"
    assert res.values["nickname"] == "신규작성자"


def test_cafe_avg_via_api(engine):
    api = '{"message":{"result":{"articleList":[{"articleId":1,"readCount":10},{"articleId":2,"readCount":30}]}}}'
    http = FakeHttp({"https://apis.naver.com/cafe-web/cafe2/ArticleListV2dot1.json": api})
    (res,) = run(engine, "cafe_avg", ["https://cafe.naver.com/f-e/cafes/333"], http)
    assert res.status == "완료", res.message
    assert (res.values["avg"], res.values["samples"], res.values["page"]) == (20, 2, 10)
    assert "search.page=10" in http.calls[0]


def test_cafe_avg_via_list_page_skips_notice(engine):
    (res,) = run(engine, "cafe_avg", ["https://cafe.naver.com/f-e/cafes/222"])
    assert res.status == "완료", res.message
    assert (res.values["avg"], res.values["samples"]) == (500, 3)


def test_blog_info_and_no_widget_does_not_stop(engine):
    visitors = "".join(f'<visitorcnt id="2026100{i}" cnt="{c}"/>' for i, c in enumerate([10, 20, 30, 40, 50], 1))
    http = FakeHttp({
        "https://blog.naver.com/NVisitorgp4Ajax.nhn?blogId=tester": f"<visitorcnts>{visitors}</visitorcnts>",
        "https://blog.naver.com/NVisitorgp4Ajax.nhn?blogId=nowidget": "<visitorcnts></visitorcnts>",
    })
    no_widget, ok = run(engine, "blog_info", ["https://blog.naver.com/nowidget", "https://blog.naver.com/tester"], http)
    assert no_widget.status == "위젯없음"
    assert no_widget.values["name"] == "위젯 없는 블로그"
    assert ok.status == "완료", ok.message
    # PC 화면의 '이웃 1,234명' (서로이웃 23명은 무시)
    assert ok.values == {"name": "테스트 블로그", "nickname": "테스터", "avg": 30, "buddies": 1234}


def test_blog_buddy_count_fallbacks(engine):
    visitors = '<visitorcnts><visitorcnt id="20261006" cnt="100"/><visitorcnt id="20261007" cnt="300"/></visitorcnts>'
    http = FakeHttp({
        "https://blog.naver.com/NVisitorgp4Ajax.nhn": visitors,
        "https://m.blog.naver.com/api/blogs/apiblog": '{"isSuccess": true, "result": {"subscriberCount": 5868}}',
    })
    from_api, from_mobile = run(engine, "blog_info",
                                ["https://blog.naver.com/apiblog", "https://blog.naver.com/mobileblog"], http)
    assert from_api.status == "완료", from_api.message
    assert from_api.values["buddies"] == 5868          # 모바일 블로그 API
    assert from_mobile.status == "완료", from_mobile.message
    assert from_mobile.values["buddies"] == 319000     # 모바일 화면 '31.9만명의 이웃'
    assert from_mobile.values["avg"] == 200


def test_blog_visitor_average_uses_last_five_days(engine):
    days = [10, 20, 30, 40, 50, 60, 70]
    xml = "".join(f'<visitorcnt id="2026100{i}" cnt="{c}"/>' for i, c in enumerate(days, 1))
    (res,) = run(engine, "blog_info", ["https://blog.naver.com/tester"],
                 FakeHttp({"https://blog.naver.com/NVisitorgp4Ajax.nhn": f"<visitorcnts>{xml}</visitorcnts>"}))
    assert res.values["avg"] == 50  # (30+40+50+60+70)/5


def test_blog_post(engine):
    (res,) = run(engine, "blog_post", ["https://m.blog.naver.com/tester/999"])
    assert res.status == "완료", res.message
    assert res.values == {"title": "포스팅 제목", "likes": 21, "comments": 4, "date": "2026. 10. 2. 9:00",
                          "nickname": "포스팅작성자"}


def test_kin(engine):
    (res,) = run(engine, "kin", ["https://kin.naver.com/qna/detail.naver?d1id=1&docId=2"])
    assert res.status == "완료", res.message
    assert res.values == {"title": "질문 제목", "views": 5678}


def test_missing_page_is_failure_not_crash(engine):
    (res,) = run(engine, "kin", ["https://kin.naver.com/qna/none"])
    assert res.status == "실패"


def test_stop_event_cancels(engine):
    stop = threading.Event()
    stop.set()
    seen = []
    finished = engine.run(TASK_BY_ID["kin"], [(0, "https://kin.naver.com/qna/detail.naver")], stop,
                          on_start=seen.append)
    assert finished is False and seen == []


def test_browser_start_failure_stops_whole_job(tmp_path, monkeypatch):
    """크롬을 못 띄우면 URL 마다 실패를 쌓지 않고 첫 줄에서 바로 멈춘다."""
    from naver_crawler.browser import BrowserError

    monkeypatch.setenv("NAVER_CRAWLER_HOME", str(tmp_path))
    eng = Engine(Settings(headless=True, keep_login=False, request_delay=0,
                          chromedriver_path=str(tmp_path / "missing-chromedriver"), chrome_binary=CHROME))
    eng.http = FakeHttp()
    results = {}
    with pytest.raises(BrowserError):
        eng.run(TASK_BY_ID["kin"], [(0, "https://kin.naver.com/a"), (1, "https://kin.naver.com/b")],
                threading.Event(), on_result=lambda k, r: results.__setitem__(k, r))
    assert list(results) == [0] and results[0].status == "실패"
