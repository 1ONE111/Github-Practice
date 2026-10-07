"""엑셀(.xlsx) 내보내기.

팀에서 쓰는 리스트 양식에 맞춘다:
B열부터 시작, B2 검정 제목줄 '제목 (건수)', 4행 검정 머리글, 5행 얇은 띠, 6행부터 데이터,
8pt 글꼴 · 얇은 검정 테두리 · 왼쪽 정렬, 표 아래 '*' 주석. 상태는 색 대신 '비고' 열에 글로 남긴다.
"""

from __future__ import annotations

import datetime as dt
import re
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Sequence

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.worksheet import Worksheet

from naver_crawler.crawlers import (
    EXCLUDED_STATUSES,
    STATUS_CANCELLED,
    STATUS_FAIL,
    STATUS_OK,
    STATUS_PARTIAL,
    Column,
)

HEAD_FONT = "나눔고딕"
BODY_FONT = "맑은 고딕"
SIZE = 8
BLACK = "000000"
NUMBER_FORMAT = "#,##0\\ "

TITLE_ROW = 2
HEADER_ROW = 4
FIRST_DATA_ROW = 6
EXCLUDED_SHEET = "제외 목록"

_THIN = Side(style="thin", color=BLACK)
_BORDER = Border(left=_THIN, right=_THIN, top=_THIN, bottom=_THIN)
_BLACK_FILL = PatternFill("solid", fgColor=BLACK)
_WHITE_FILL = PatternFill("solid", fgColor="FFFFFF")
_CELL_ALIGN = Alignment(horizontal="left", vertical="center")


@dataclass
class SheetData:
    title: str
    description: str
    columns: Sequence[Column]                                   # 작업 결과 열 (구분/URL/비고는 자동 추가)
    rows: list[dict[str, Any]] = field(default_factory=list)   # {"url", "status", "message", <열 key>…}
    notes: Sequence[str] = ()                                   # 표 아래 '*' 주석
    sort_desc: str | None = None                                # 이 열 큰 값부터 정렬 (값 없는 행은 맨 뒤)


def split_excluded(rows: list[dict]) -> tuple[list[dict], list[dict]]:
    """위젯없음 같은 제외 대상 행을 본 데이터에서 걸러낸다."""
    kept = [r for r in rows if r.get("status") not in EXCLUDED_STATUSES]
    dropped = [r for r in rows if r.get("status") in EXCLUDED_STATUSES]
    return kept, dropped


def note_for(row: dict) -> str:
    """상태를 '비고' 문구로. 정상 완료는 비워 둔다."""
    status, message = row.get("status"), (row.get("message") or "").strip()
    if status == STATUS_OK:
        return message
    if status == STATUS_PARTIAL:
        return message or STATUS_PARTIAL
    if status == STATUS_FAIL:
        return f"실패 - {message}" if message else "실패"
    if status == STATUS_CANCELLED:
        return "중지됨 (미수집)"
    if status in EXCLUDED_STATUSES:
        return message or str(status)
    return "미수집"


def _display_width(text: str) -> int:
    return sum(2 if unicodedata.east_asian_width(ch) in "WF" else 1 for ch in text)


def _safe_sheet_title(title: str, used: set[str]) -> str:
    base = re.sub(r"[\[\]:*?/\\]", " ", title).strip()[:31] or "Sheet"
    name, n = base, 2
    while name in used:
        suffix = f" ({n})"
        name = base[: 31 - len(suffix)] + suffix
        n += 1
    used.add(name)
    return name


def _ordered_columns(columns: Sequence[Column]) -> list[Column]:
    """구분 | 이름(첫 글자 열) | URL | 나머지 | 비고 순서. 작업이 URL 열 위치를 정했으면 그대로 따른다."""
    if any(c.key == "url" for c in columns):
        return [Column("_no", "구분", "int", width=6), *columns, Column("_note", "비고", width=40)]
    first_text = next((c for c in columns if c.kind == "text"), None)
    out = [Column("_no", "구분", "int", width=6)]
    if first_text is not None:
        out.append(first_text)
    out.append(Column("url", "URL", width=34))
    out += [c for c in columns if c is not first_text]
    out.append(Column("_note", "비고", width=40))
    return out


def _write_list(ws: Worksheet, title: str, cols: list[Column], rows: list[dict], notes: Sequence[str]) -> None:
    first_col, last_col = 2, 1 + len(cols)
    ws.column_dimensions["A"].width = 2.8

    # 제목줄
    ws.merge_cells(start_row=TITLE_ROW, start_column=first_col, end_row=TITLE_ROW, end_column=last_col)
    title_cell = ws.cell(row=TITLE_ROW, column=first_col, value=title)
    title_cell.font = Font(name=HEAD_FONT, size=SIZE, bold=True, color="FFFFFF")
    title_cell.fill = _BLACK_FILL
    title_cell.alignment = Alignment(horizontal="center", vertical="center")
    ws.row_dimensions[3].height = 12.75

    # 머리글
    for i, col in enumerate(cols):
        cell = ws.cell(row=HEADER_ROW, column=first_col + i, value=col.header)
        cell.font = Font(name=HEAD_FONT, size=SIZE, color="FFFFFF")
        cell.fill = _BLACK_FILL
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        cell.border = _BORDER
    ws.row_dimensions[HEADER_ROW + 1].height = 3.75

    minimum = {"_no": 6, "url": 28, "_note": 24}
    widths = [max(minimum.get(col.key, 6), _display_width(col.header) + 2) for col in cols]

    # 데이터
    for r, row in enumerate(rows):
        excel_row = FIRST_DATA_ROW + r
        ws.row_dimensions[excel_row].height = 18
        for i, col in enumerate(cols):
            cell = ws.cell(row=excel_row, column=first_col + i)
            cell.font = Font(name=BODY_FONT, size=SIZE, color=BLACK)
            cell.fill = _WHITE_FILL
            cell.border = _BORDER
            cell.alignment = _CELL_ALIGN
            if col.key == "_no":
                cell.value = r + 1
                text = str(r + 1)
            elif col.key == "url":
                cell.value = row.get("url") or ""
                text = cell.value
                if cell.value:
                    cell.hyperlink = cell.value
                    cell.font = Font(name=BODY_FONT, size=SIZE, color="0000FF", underline="single")
            elif col.key == "_note":
                cell.value = note_for(row)
                cell.number_format = "@"
                text = cell.value
            elif col.kind == "int":
                value = row.get(col.key)
                if isinstance(value, (int, float)) and not isinstance(value, bool):
                    cell.value = value
                    cell.number_format = NUMBER_FORMAT
                    text = f"{value:,} "
                else:
                    cell.value = "-"
                    text = "-"
            else:
                value = row.get(col.key)
                cell.value = "-" if value in (None, "") else str(value)
                cell.number_format = "@"
                text = cell.value
            cap = 45 if col.key in ("url",) else 60
            widths[i] = max(widths[i], min(_display_width(str(text)) * 0.9 + 2, cap))

    for i, width in enumerate(widths):
        ws.column_dimensions[get_column_letter(first_col + i)].width = round(width, 1)

    # 주석
    note_row = FIRST_DATA_ROW + len(rows) + 1
    for k, note in enumerate(notes):
        cell = ws.cell(row=note_row + k, column=first_col, value=note)
        cell.font = Font(name=BODY_FONT, size=SIZE, color=BLACK)
        cell.alignment = _CELL_ALIGN

    ws.page_setup.orientation = "landscape"
    ws.page_setup.paperSize = ws.PAPERSIZE_A4
    ws.page_setup.fitToWidth = 1
    ws.page_setup.fitToHeight = 0
    ws.sheet_properties.pageSetUpPr.fitToPage = True


def build_workbook(sheets: list[SheetData], generated: dt.datetime | None = None) -> Workbook:
    generated = generated or dt.datetime.now()
    wb = Workbook()
    wb.remove(wb.active)
    used: set[str] = set()
    excluded: list[tuple[str, dict]] = []

    for sheet in sheets:
        kept, dropped = split_excluded(sheet.rows)
        if sheet.sort_desc:
            key = sheet.sort_desc
            kept = sorted(kept, key=lambda r: (not isinstance(r.get(key), (int, float)), -(r.get(key) or 0)))
        excluded += [(sheet.title, row) for row in dropped]
        notes = [f"* 수집일시: {generated:%Y-%m-%d %H:%M}", *sheet.notes]
        if dropped:
            notes.append(f"* 방문자 위젯이 없는 블로그 {len(dropped)}건은 '{EXCLUDED_SHEET}' 시트로 분리")
        ws = wb.create_sheet(_safe_sheet_title(sheet.title, used))
        _write_list(ws, f"{sheet.title} ({len(kept)})", _ordered_columns(sheet.columns), kept, notes)

    if excluded:
        cols = [
            Column("_no", "구분", "int", width=6),
            Column("_task", "항목", width=12),
            Column("name", "이름", width=24),
            Column("url", "URL", width=34),
            Column("_note", "비고", width=40),
        ]
        rows = [{**row, "_task": task, "name": row.get("name") or row.get("title")} for task, row in excluded]
        ws = wb.create_sheet(_safe_sheet_title(EXCLUDED_SHEET, used))
        _write_list(ws, f"{EXCLUDED_SHEET} ({len(rows)})", cols, rows,
                    [f"* 수집일시: {generated:%Y-%m-%d %H:%M}", "* 본 시트 목록에서 자동으로 뺀 항목"])

    if not sheets:
        wb.create_sheet("결과")
    wb.properties.creator = "네이버 크롤러"
    return wb


def export_xlsx(path: str | Path, sheets: list[SheetData], generated: dt.datetime | None = None) -> Path:
    path = Path(path)
    if path.suffix.lower() != ".xlsx":
        path = path.with_suffix(".xlsx")
    build_workbook(sheets, generated).save(path)
    return path


def default_filename(label: str, when: dt.datetime | None = None) -> str:
    when = when or dt.datetime.now()
    clean = re.sub(r'[\\/:*?"<>|\s]+', "_", label).strip("_")
    return f"네이버크롤링_{clean}_{when:%y%m%d}.xlsx"
