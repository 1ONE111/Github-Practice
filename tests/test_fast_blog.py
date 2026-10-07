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
    assert res.values == {"nickname": "Alice", "name": "앨리스 일상나들이", "buddies": 8423, "avg": 2104}
    assert not eng.browser.is_running()  # 크롬을 띄우지 않았다


def test_widget_hidden_204_is_no_widget():
    _eng, results, _s, _d = run({
        VISITOR + "daily": (204, ""),
        REGO + "daily": rego("Daily", "D a i l y", 6192),
    }, ["daily"])
    assert results["daily"].status == "위젯없음"
    assert results["daily"].values["buddies"] == 6192


def test_widget_error_is_partial_not_no_widget():
    _eng, results, _s, _d = run({REGO + "x": rego("X", "엑스", 10)}, ["x"])  # 위젯 응답 자체가 없음
    res = results["x"]
    assert res.status == "일부 누락"
    assert "방문자 위젯 응답 없음" in res.message


def test_mobile_html_fallback_for_profile():
    html = '<script>{"blogName":"모바일명","nickName":"모닉","subscriberCount":321}</script><span>321명의 이웃</span>'
    _eng, results, _s, _d = run({
        VISITOR + "mob": widget(1, 2, 3, 4, 5),
        "https://m.blog.naver.com/mob": html,
    }, ["mob"])
    assert results["mob"].values == {"nickname": "모닉", "name": "모바일명", "buddies": 321, "avg": 3}


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
    assert all(results[b].values["buddies"] == i and results[b].values["avg"] == i for i, b in enumerate(ids))


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
    fast = RowResult({"nickname": "Alice", "name": "앨리스", "buddies": None, "avg": 10}, "일부 누락", "누락: 이웃수")
    slow = RowResult({"nickname": "엉뚱", "name": "엉뚱", "buddies": 99, "avg": 1}, "완료", "")
    merged = merge_results(task, fast, slow)
    assert merged.status == "완료"
    assert merged.values == {"nickname": "Alice", "name": "앨리스", "buddies": 99, "avg": 10}

    hidden = merge_results(task, RowResult({"nickname": "a", "buddies": 1}, "일부 누락", "x"),
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
