import pytest

from naver_crawler.crawlers import _count, VIEW_LABELS, extract_read_counts
from naver_crawler.parsing import (
    club_id_from_html,
    find_dict,
    find_key,
    load_json_loose,
    parse_blog_url,
    parse_cafe_url,
    parse_count,
    parse_visitor_counts,
    regex_count,
    split_urls,
    strip_suffixes,
)


@pytest.mark.parametrize(
    "text,expected",
    [
        ("조회 1,234", 1234),
        ("1.2만", 12000),
        ("조회수 3천", 3000),
        ("999+", 999),
        ("댓글 0", 0),
        ("비공개", None),
        ("", None),
        (None, None),
        (42, 42),
        (True, None),
    ],
)
def test_parse_count(text, expected):
    assert parse_count(text) == expected


def test_label_number_wins_over_date():
    assert _count("작성일 2024.10.07. 조회수 1,523", VIEW_LABELS) == 1523
    assert _count("12", VIEW_LABELS) == 12
    assert regex_count("멤버수 : 12,345명", ["멤버수"]) == 12345


@pytest.mark.parametrize(
    "url,slug,club,article",
    [
        ("https://cafe.naver.com/joonggonara", "joonggonara", None, None),
        ("https://cafe.naver.com/joonggonara/123456", "joonggonara", None, "123456"),
        ("https://cafe.naver.com/ArticleRead.nhn?clubid=10050146&articleid=777", None, "10050146", "777"),
        ("https://cafe.naver.com/f-e/cafes/10050146/articles/888?menuid=1", None, "10050146", "888"),
        ("https://cafe.naver.com/ca-fe/cafes/10050146/articles/999", None, "10050146", "999"),
        ("https://m.cafe.naver.com/ca-fe/web/cafes/joonggonara/articles/55", "joonggonara", None, "55"),
        (
            "https://cafe.naver.com/joonggonara?iframe_url=/ArticleRead.nhn%3Fclubid=10050146%26articleid=31",
            "joonggonara",
            "10050146",
            "31",
        ),
        (
            "https://cafe.naver.com/joonggonara?iframe_url_utf8=%2FArticleRead.nhn%253Fclubid%3D10050146%2526articleid%3D32",
            "joonggonara",
            "10050146",
            "32",
        ),
    ],
)
def test_parse_cafe_url(url, slug, club, article):
    ref = parse_cafe_url(url)
    assert (ref.slug, ref.club_id, ref.article_id) == (slug, club, article)


@pytest.mark.parametrize(
    "url,blog_id,log_no",
    [
        ("https://blog.naver.com/naver_diary", "naver_diary", None),
        ("https://blog.naver.com/naver_diary/223000111222", "naver_diary", "223000111222"),
        ("https://blog.naver.com/PostView.naver?blogId=abc&logNo=22", "abc", "22"),
        ("https://m.blog.naver.com/abc/33", "abc", "33"),
        ("https://m.blog.naver.com/PostView.naver?blogId=abc&logNo=44", "abc", "44"),
        ("https://abc.blog.me/55", "abc", "55"),
        ("https://blog.naver.com/PostList.naver?blogId=xyz", "xyz", None),
    ],
)
def test_parse_blog_url(url, blog_id, log_no):
    ref = parse_blog_url(url)
    assert (ref.blog_id, ref.log_no) == (blog_id, log_no)


def test_split_urls_normalizes_and_skips_blank():
    text = "cafe.naver.com/a\n\n  https://blog.naver.com/b  \n# 메모\nhttps://x.com/c, https://x.com/d"
    assert split_urls(text) == [
        "https://cafe.naver.com/a",
        "https://blog.naver.com/b",
        "https://x.com/c",
        "https://x.com/d",
    ]


def test_visitor_xml():
    xml = (
        '<?xml version="1.0" encoding="utf-8"?><visitorcnts>'
        '<visitorcnt id="20261003" cnt="100"/><visitorcnt id="20261004" cnt="200"/>'
        '<visitorcnt id="20261005" cnt="300"/></visitorcnts>'
    )
    assert parse_visitor_counts(xml) == [("20261003", 100), ("20261004", 200), ("20261005", 300)]
    assert parse_visitor_counts("") == []


def test_json_helpers():
    data = {"result": {"article": {"articleId": 5, "readCount": 10, "commentCount": 2}, "others": [{"articleId": 6, "readCount": 99}]}}
    assert find_key(data, ["readCount"]) == 10
    assert find_dict(data, {"articleId": "6"}, ["readCount"])["readCount"] == 99
    assert load_json_loose('cb({"a": 1});') == {"a": 1}
    assert load_json_loose(")]}'\n{\"b\": 2}") == {"b": 2}
    assert load_json_loose("not json") is None


def test_extract_read_counts_skips_notices():
    data = {
        "result": {
            "articleList": [
                {"type": "NOTICE", "item": {"articleId": 1, "readCount": 5000}},
                {"type": "ARTICLE", "item": {"articleId": 2, "readCount": 10}},
                {"type": "ARTICLE", "item": {"articleId": 3, "readCount": 20}},
            ],
            "popular": [{"articleId": 9, "readCount": 1}],
        }
    }
    assert extract_read_counts(data) == [10, 20]


def test_club_id_from_html():
    assert club_id_from_html('<script>var g_sClubId = "10050146";</script>') == "10050146"
    assert club_id_from_html('<a href="/ArticleList.nhn?search.clubid=123456">') == "123456"
    assert club_id_from_html("nothing") is None


def test_strip_suffixes():
    assert strip_suffixes("내 블로그 : 네이버 블로그", [": 네이버 블로그"]) == "내 블로그"
    assert strip_suffixes("  ", [": 네이버 블로그"]) is None
