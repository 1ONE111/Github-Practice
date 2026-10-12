"""블로그 정보 빠른 수집(크롬 없이 동시 처리)."""

import json
import threading

from naver_crawler.config import Settings
from naver_crawler.crawlers import TASK_BY_ID, RowResult, merge_results
from naver_crawler.engine import Engine
from tests.fake_naver import FakeHttp

VISITOR = "https://blog.naver.com/NVisitorgp4Ajax.nhn?blogId="
REGO = "https://m.blog.naver.com/rego/BlogInfo.naver?blogId="


def widget(*counts):
    rows = "".join(f'<visitorcnt id="2026100{i}" cnt="{c}"/>' for i, c in enumerate(counts, 1))
    return f'<?xml version="1.0" encoding="utf-8"?><visitorcnts>{rows}</visitorcnts>'


def rego(nick, name, subscribers):
    return json.dumps({"isSuccess": True, "result": {"blogName": name, "nickName": nick,
                                                     "displayNickName": f"{nick}(x)", "subscriberCount": subscribers}})


def run(responses, blog_ids, **settings):
    eng = Engine(Settings(headless=True, keep_login=False, request_delay=0, browser_fallback=False, **settings))
    eng.http = FakeHttp(responses)
    results, started = {}, []
    lock = threading.Lock()

    def on_start(key):
        with lock:
            started.append(key)

    done = eng.run(TASK_BY_ID["blog_info"], [(b, f"https://blog.naver.com/{b}") for b in blog_ids],
                   threading.Event(), on_start=on_start, on_result=lambda k, r: results.__setitem__(k, r))
    return eng, results, started, done


def test_fast_path_reads_widget_and_profile_without_chrome():
    eng, results, _started, done = run({
        VISITOR + "alice": widget(2176, 2761, 2407, 2140, 1040),
        REGO + "alice": rego("Alice", "앨리스 일상나들이", 8423),
    }, ["alice"])
    assert done is True
    res = results["alice"]
    assert res.status == "완료", res.message
    assert res.values == {"nickname": "Alice", "name": "앨리스 일상나들이", "avg": 2104}
    assert not eng.browser.is_running()  # 크롬을 띄우지 않았다


def test_widget_hidden_204_is_no_widget():
    _eng, results, _s, _d = run({
        VISITOR + "daily": (204, ""),
        REGO + "daily": rego("Daily", "D a i l y", 6192),
    }, ["daily"])
    assert results["daily"].status == "위젯없음"
    assert results["daily"].values["nickname"] == "Daily"


def test_widget_error_is_partial_not_no_widget():
    _eng, results, _s, _d = run({REGO + "x": rego("X", "엑스", 10)}, ["x"])  # 위젯 응답 자체가 없음
    res = results["x"]
    assert res.status == "일부 누락"
    assert "방문자 위젯 응답 없음" in res.message


def test_mobile_html_fallback_for_profile():
    html = '<script>{"blogName":"모바일명","nickName":"모닉"}</script>'
    _eng, results, _s, _d = run({
        VISITOR + "mob": widget(1, 2, 3, 4, 5),
        "https://m.blog.naver.com/mob": html,
    }, ["mob"])
    assert results["mob"].values == {"nickname": "모닉", "name": "모바일명", "avg": 3}


def test_many_blogs_in_parallel():
    ids = [f"b{i}" for i in range(20)]
    responses = {}
    for i, b in enumerate(ids):
        responses[VISITOR + b + "&"] = ""  # 접두어 충돌 방지용 더미
        responses[REGO + b] = rego(f"n{i}", f"블로그{i}", i)
    # 'b1' 이 'b10' 의 접두어가 되지 않도록 정확한 키로만 위젯 응답
    fake_widget = {VISITOR + b: widget(i, i, i, i, i) for i, b in enumerate(ids)}
    responses = {**fake_widget, **{k: v for k, v in responses.items() if k.startswith(REGO)}}
    eng = Engine(Settings(headless=True, keep_login=False, request_delay=0, browser_fallback=False, workers=4))

    class ExactHttp(FakeHttp):
        def fetch(self, url, referer=None):
            self.calls.append(url)
            found = self.responses.get(url)
            if found is None:
                return None, ""
            return found if isinstance(found, tuple) else (200, found)

    eng.http = ExactHttp(responses)
    results = {}
    lock = threading.Lock()

    def on_result(k, r):
        with lock:
            results[k] = r

    assert eng.run(TASK_BY_ID["blog_info"], [(b, f"https://blog.naver.com/{b}") for b in ids],
                   threading.Event(), on_result=on_result) is True
    assert sorted(results) == sorted(ids)
    assert all(results[b].values["nickname"] == f"n{i}" and results[b].values["avg"] == i for i, b in enumerate(ids))


def test_stop_before_start_runs_nothing():
    eng = Engine(Settings(request_delay=0, browser_fallback=False))
    eng.http = FakeHttp({})
    stop = threading.Event()
    stop.set()
    seen = []
    assert eng.run(TASK_BY_ID["blog_info"], [(0, "https://blog.naver.com/a")], stop, on_start=seen.append) is False
    assert seen == []


def test_merge_prefers_fast_values_and_keeps_no_widget():
    task = TASK_BY_ID["blog_info"]
    fast = RowResult({"nickname": "Alice", "name": None, "avg": 10}, "일부 누락", "누락: 블로그명")
    slow = RowResult({"nickname": "엉뚱", "name": "앨리스", "avg": 1}, "완료", "")
    merged = merge_results(task, fast, slow)
    assert merged.status == "완료"
    assert merged.values == {"nickname": "Alice", "name": "앨리스", "avg": 10}

    hidden = merge_results(task, RowResult({"nickname": "a", "name": "b"}, "일부 누락", "x"),
                           RowResult({"nickname": "a", "avg": None}, "위젯없음", "방문자 위젯이 없는 블로그"))
    assert hidden.status == "위젯없음"


def test_settings_migration_turns_on_headless(tmp_path):
    path = tmp_path / "settings.json"
    path.write_text(json.dumps({"headless": False, "request_delay": 2}), encoding="utf-8")
    loaded = Settings.load(path)
    assert loaded.headless is True and loaded.request_delay == 2.0 and loaded.workers == 4
    loaded.headless = False
    loaded.save(path)
    assert Settings.load(path).headless is False  # 한 번 바꾼 뒤에는 사용자가 고른 값 유지



# ---------------------------------------------------------------- 블로그 포스팅 빠른 수집

LIKE = "https://blog.like.naver.com/v1/search/contents"
M_POST = "https://m.blog.naver.com/"


def likes_json(cid, *counts):
    reactions = [{"reactionType": t, "count": c} for t, c in zip(("like", "thanks", "wow"), counts)]
    return json.dumps({"contents": [{"serviceId": "BLOG", "contentsId": cid, "isDisplay": True, "reactions": reactions}]})


def run_posts(responses, urls):
    eng = Engine(Settings(headless=True, keep_login=False, request_delay=0, browser_fallback=False))
    eng.http = FakeHttp(responses)
    results = {}
    eng.run(TASK_BY_ID["blog_post"], list(enumerate(urls)), threading.Event(),
            on_result=lambda k, r: results.__setitem__(k, r))
    return eng, [results[i] for i in range(len(urls))]


def test_post_fast_likes_from_api_and_comments_from_mobile_page():
    # 실제 모바일 글 구조: <p class="blog_date"> <span class="txt">날짜</span> </p>
    m_html = ('<meta property="og:title" content="아이폰18 자급제 &amp; 요금제"/>'
              '<p class="blog_date"> <span class="txt">2026. 10. 2. 14:00</span> </p><a commentCount="3">댓글</a>')
    eng, (res,) = run_posts({
        LIKE: likes_json("smy2166_224429363630", 11),
        M_POST + "smy2166/224429363630": m_html,
        REGO + "smy2166": rego("희재맘 송민영", "블로그", 1),
    }, ["https://blog.naver.com/smy2166/224429363630"])
    assert res.status == "완료", res.message
    assert res.values == {"title": "아이폰18 자급제 & 요금제", "nickname": "희재맘 송민영", "likes": 11,
                          "comments": 3, "date": "2026. 10. 2. 14:00"}
    assert not eng.browser.is_running()


def test_post_fast_zero_values_are_zero():
    _eng, (res,) = run_posts({
        LIKE: json.dumps({"contents": [{"contentsId": "qwooo200_1", "reactions": []}]}),  # 공감 0
        M_POST + "qwooo200/1": '<meta property="og:title" content="글"/><a commentCount="0">',  # 댓글 0
    }, ["https://blog.naver.com/qwooo200/1"])
    assert (res.values["likes"], res.values["comments"]) == (0, 0)
    assert res.status in ("완료", "일부 누락") and "댓글" not in res.message and "공감" not in res.message


def test_post_fast_sums_reaction_types():
    _eng, (res,) = run_posts({LIKE: likes_json("a_1", 5, 2, 1), M_POST + "a/1": '<a commentCount="0">'},
                             ["https://blog.naver.com/a/1"])
    assert res.values["likes"] == 8


def test_post_fast_pc_page_empty_comment_box_means_zero():
    pc = '<div class="se-title-text">x</div><em id="commentCount" class="_commentCount"> </em>'
    _eng, (res,) = run_posts({
        LIKE: likes_json("b_2", 4),
        "https://blog.naver.com/PostView.naver?blogId=b&logNo=2": pc,
    }, ["https://blog.naver.com/b/2"])
    assert res.values["comments"] == 0 and res.values["likes"] == 4


def test_post_fast_comment_api_fallback():
    cbox = '/**/cb({"success":true,"result":{"count":{"comment":2,"reply":1,"exposeCount":3,"total":3}}});'
    _eng, (res,) = run_posts({
        LIKE: likes_json("c_3", 1),
        REGO + "c": json.dumps({"result": {"blogNo": 777, "nickName": "c"}}),
        "https://apis.naver.com/commentBox/cbox/web_naver_list_jsonp.json": cbox,
    }, ["https://blog.naver.com/c/3"])
    assert res.values["comments"] == 3


def test_post_without_log_no_fails_cleanly():
    _eng, (res,) = run_posts({}, ["https://blog.naver.com/onlyblog"])
    assert res.status == "실패" and "글 번호" in res.message


def test_post_date_formats():
    from naver_crawler.crawlers import _post_date_from_html

    assert _post_date_from_html('<span class="se_publishDate pcol2">2026. 10. 2. 14:00</span>') == "2026. 10. 2. 14:00"
    # 최근 글은 '3시간 전' 으로 보여서 작성 시각(addDate, 밀리초)으로 만든다
    relative = '<p class="blog_date"> <span class="txt">3시간 전</span> </p> addDate="1790917258641"'
    assert _post_date_from_html(relative) == "2026. 10. 2. 14:00"
    # 다른 글 목록의 날짜(class="date")는 쓰지 않는다
    assert _post_date_from_html('<span class="date pcol2">2026. 10. 6.</span>') is None


def test_post_fast_reads_pc_page_when_mobile_has_no_date():
    _eng, (res,) = run_posts({
        LIKE: likes_json("d_4", 2),
        M_POST + "d/4": '<meta property="og:title" content="t"/><a commentCount="1">',
        "https://blog.naver.com/PostView.naver?blogId=d&logNo=4": '<span class="se_publishDate pcol2">2026. 9. 1. 8:05</span>',
    }, ["https://blog.naver.com/d/4"])
    assert res.values["date"] == "2026. 9. 1. 8:05" and res.values["comments"] == 1
