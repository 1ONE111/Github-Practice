"""설정 저장/불러오기. 설정 파일은 %APPDATA%\\NaverCrawler\\settings.json 에 저장된다."""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, fields
from pathlib import Path

from naver_crawler import APP_ID


def app_data_dir() -> Path:
    base = os.environ.get("NAVER_CRAWLER_HOME")
    if base:
        path = Path(base)
    else:
        root = os.environ.get("APPDATA") or os.environ.get("XDG_CONFIG_HOME") or str(Path.home() / ".config")
        path = Path(root) / APP_ID
    path.mkdir(parents=True, exist_ok=True)
    return path


def chrome_profile_dir() -> Path:
    return app_data_dir() / "chrome-profile"


def debug_dir() -> Path:
    path = app_data_dir() / "debug"
    path.mkdir(parents=True, exist_ok=True)
    return path


def selectors_path() -> Path:
    return app_data_dir() / "selectors.json"


SETTINGS_VERSION = 2


@dataclass
class Settings:
    headless: bool = True           # 브라우저 창 숨기기 (로그인할 때만 창이 보임)
    keep_login: bool = True         # 전용 크롬 프로필에 로그인 유지
    request_delay: float = 1.0      # URL 사이 대기(초)
    page_timeout: int = 20          # 요소 대기 최대 시간(초)
    avg_page: int = 10              # 평균 조회수 계산할 페이지
    avg_per_page: int = 15          # 페이지당 글 수
    chromedriver_path: str = ""     # 비우면 Selenium Manager 가 자동으로 맞춤
    chrome_binary: str = ""         # 비우면 설치된 크롬 자동 탐색
    save_debug_html: bool = False   # 실패 시 페이지 HTML 저장
    workers: int = 4                # 크롬 없이 처리하는 작업(블로그 정보)의 동시 처리 수
    browser_fallback: bool = True   # 빠른 수집에서 빈 값만 크롬으로 다시 확인
    export_dir: str = ""
    settings_version: int = SETTINGS_VERSION

    @classmethod
    def load(cls, path: Path | None = None) -> "Settings":
        path = path or app_data_dir() / "settings.json"
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return cls()
        known = {f.name: f for f in fields(cls)}
        values = {}
        for key, value in raw.items():
            if key not in known:
                continue
            default = known[key].default
            try:
                values[key] = type(default)(value)
            except (TypeError, ValueError):
                continue
        if int(raw.get("settings_version", 1)) < 2:
            values["headless"] = True  # 2.0.2: 크롬 창 숨김을 기본으로 바꿈 (예전 설정 파일도 한 번 전환)
        values["settings_version"] = SETTINGS_VERSION
        return cls(**values)

    def save(self, path: Path | None = None) -> None:
        path = path or app_data_dir() / "settings.json"
        path.write_text(json.dumps(asdict(self), ensure_ascii=False, indent=2), encoding="utf-8")
