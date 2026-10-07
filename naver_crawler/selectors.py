"""페이지 요소 선택자.

네이버 화면 구조가 바뀌면 프로그램을 다시 빌드하지 않아도
%APPDATA%\\NaverCrawler\\selectors.json 을 고쳐서 바로 반영할 수 있다.
각 항목은 앞에서부터 순서대로 시도한다 (구 화면 + 신 화면 후보를 함께 둔다).
"""

from __future__ import annotations

import copy
import json
from pathlib import Path

from naver_crawler.config import selectors_path

DEFAULT_SELECTORS: dict[str, dict[str, list[str]]] = {
    "cafe_info": {
        "frames": [],  # 카페 정보는 최상위 문서에 있다
        "name": [
            "#cafe-info-data .cafe-name",
            "body > h1",
            "h1.cafe_name",
            ".cafe_name",
            "[class*='CafeName']",
            "[class*='cafe_name']",
        ],
        "members": [
            "#cafe-info-data li.mem-cnt-info em",
            "li.mem-cnt-info em",
            ".mem-cnt-info em",
            "[class*='member_count']",
            "[class*='MemberCount']",
            "[class*='member'] [class*='count']",
        ],
    },
    "cafe_article": {
        "frames": ["cafe_main"],
        "title": [
            ".ArticleTitle .title_text",
            "h3.title_text",
            ".title_area .title_text",
            "[class*='ArticleTitle'] h3",
        ],
        "views": [
            ".article_info span.count",
            ".ArticleContentBox .article_info .count",
            ".WriterInfo .article_info .count",
            "[class*='article_info'] [class*='count']",
        ],
        "comments": [
            ".ReplyBox .box_left > a > strong",
            ".ReplyBox .button_comment strong",
            ".ReplyBox .button_comment .num",
            ".ArticleTool .button_comment .num",
            "a.button_comment strong",
            ".CommentBox .comment_count",
        ],
        "likes": [
            ".ReplyBox .like_article em.u_cnt._count",
            ".ReplyBox .box_left em.u_cnt._count",
            ".like_article em.u_cnt._count",
            ".like_article ._count",
            ".ReplyBox em.u_cnt._count",
            "[class*='like'] em.u_cnt",
        ],
        "nickname": [
            ".WriterInfo .nickname",
            ".WriterInfo .nick_box button",
            ".profile_info .nick_box .nickname",
            ".nick_box .nickname",
            "[class*='WriterInfo'] [class*='nick']",
        ],
        "date": [
            ".article_info span.date",
            ".WriterInfo .date",
            "[class*='article_info'] [class*='date']",
        ],
    },
    "cafe_list": {
        "frames": ["cafe_main"],
        "rows": [
            "#main-area div.article-board:not(#upperArticleList) tbody tr",
            ".article-board tbody tr",
            "table.article-table tbody tr",
            "[class*='ArticleList'] tbody tr",
            "tbody tr",
        ],
        "view_cell": [".td_view", "td.type_readCount", "[class*='read_count']", "[class*='readCount']"],
    },
    "blog_info": {
        "frames": ["mainFrame"],
        "nickname": ["#nickNameArea", ".nick", "strong.nick", ".blog_author .nick", "[class*='nickname']"],
        "buddies": ["#buddyCount", ".buddy_count", ".cnt_buddy", "[class*='buddy_cnt']"],
        "name": ["#blogTitleName", ".blog_title", "#blog-title", "[class*='blog_name']"],
    },
    "blog_post": {
        "frames": ["mainFrame"],
        "title": [
            ".se-title-text",
            ".pcol1 .htitle",
            ".se_title .se_textarea",
            "h3.se_textarea",
            ".tit_h3",
        ],
        "likes": [
            ".area_sympathy em.u_cnt._count",
            ".wrap_postcomment em.u_cnt._count",
            ".u_likeit_list_module em.u_cnt._count",
            ".u_likeit_text._count",
            ".area_sympathy ._count",
        ],
        "comments": [
            "#commentCount",
            "._commentCount",
            ".area_comment .num",
            "a.btn_comment ._count",
            ".btn_comment em",
        ],
        "nickname": [
            ".blog2_container .nick",
            ".writer .nick",
            ".se_author .nick",
            "span.nick",
            "#nickNameArea",
            "strong.nick",
        ],
        "date": [".se_publishDate", "span.se_publishDate", ".date", "p.date"],
    },
    "kin": {
        "frames": [],
        "title": [
            ".c-heading__title-inner .title",
            ".c-heading__title",
            ".question-content .title",
            ".endTitleSection",
        ],
        "views": [
            "#content .question-content .c-userinfo__left span:nth-child(3)",
            ".question-content .c-userinfo__info",
            ".c-userinfo__left .infos",
            ".c-userinfo__left span",
            ".c-userinfo span",
        ],
        "answers": [".answer-content__item", "._answerList > .answer-content__item"],
        "date": [".question-content .c-userinfo__info .date", ".c-userinfo__left .date"],
    },
}


def load_selectors(path: Path | None = None) -> dict[str, dict[str, list[str]]]:
    """기본 선택자에 사용자 파일 내용을 덮어쓴다 (사용자 항목이 앞에 오도록 병합)."""
    merged = copy.deepcopy(DEFAULT_SELECTORS)
    path = path or selectors_path()
    try:
        user = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return merged
    if not isinstance(user, dict):
        return merged
    for group, items in user.items():
        if not isinstance(items, dict):
            continue
        target = merged.setdefault(group, {})
        for key, values in items.items():
            if isinstance(values, str):
                values = [values]
            if not isinstance(values, list):
                continue
            base = target.get(key, [])
            target[key] = [v for v in values if isinstance(v, str)] + [v for v in base if v not in values]
    return merged


def write_default_selectors(path: Path | None = None) -> Path:
    path = path or selectors_path()
    if not path.exists():
        path.write_text(json.dumps(DEFAULT_SELECTORS, ensure_ascii=False, indent=2), encoding="utf-8")
    return path
