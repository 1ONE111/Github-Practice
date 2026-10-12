"""설정 · 로그인 세션 저장 위치: %APPDATA%\\InstaCrawler\\"""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, fields
from pathlib import Path

from insta_crawler import APP_ID


def app_data_dir() -> Path:
    base = os.environ.get("INSTA_CRAWLER_HOME")
    if base:
        path = Path(base)
    else:
        root = os.environ.get("APPDATA") or os.environ.get("XDG_CONFIG_HOME") or str(Path.home() / ".config")
        path = Path(root) / APP_ID
    path.mkdir(parents=True, exist_ok=True)
    return path


def chrome_profile_dir() -> Path:
    return app_data_dir() / "chrome-profile"


def session_path() -> Path:
    return app_data_dir() / "session.json"


@dataclass
class Settings:
    posts: int = 5                # 평균 낼 최근 게시물 수 (인스타가 한 번에 주는 최대 12)
    request_delay: float = 3.0    # 계정 사이 대기(초). 짧으면 인스타가 잠시 막는다
    cooldown: int = 90            # 요청 제한에 걸렸을 때 한 번 기다렸다 다시 시도하는 시간(초)
    chrome_binary: str = ""       # 로그인용 크롬 경로 (비우면 자동)
    chromedriver_path: str = ""   # 비우면 Selenium Manager 가 자동으로 맞춤
    export_dir: str = ""

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
            if key in known:
                try:
                    values[key] = type(known[key].default)(value)
                except (TypeError, ValueError):
                    continue
        return cls(**values)

    def save(self, path: Path | None = None) -> None:
        path = path or app_data_dir() / "settings.json"
        path.write_text(json.dumps(asdict(self), ensure_ascii=False, indent=2), encoding="utf-8")


def load_session(path: Path | None = None) -> list[dict]:
    """로그인 때 저장한 인스타 쿠키 목록. 없으면 빈 목록."""
    try:
        data = json.loads((path or session_path()).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    return [c for c in data if isinstance(c, dict) and c.get("name")] if isinstance(data, list) else []


def save_session(cookies: list[dict], path: Path | None = None) -> None:
    keep = [{k: c.get(k) for k in ("name", "value", "domain", "path")} for c in cookies if c.get("name")]
    (path or session_path()).write_text(json.dumps(keep, ensure_ascii=False, indent=2), encoding="utf-8")


def clear_session(path: Path | None = None) -> None:
    try:
        (path or session_path()).unlink()
    except OSError:
        pass
