"""결과 표 모델."""

from __future__ import annotations

import itertools
from dataclasses import dataclass, field
from typing import Any

from PySide6.QtCore import QAbstractTableModel, QModelIndex, Qt
from PySide6.QtGui import QBrush, QColor, QFont

from naver_crawler.crawlers import STATUS_RUNNING, STATUS_WAIT, RowResult, TaskSpec
from naver_crawler.excel import SheetData
from naver_crawler.ui.theme import MUTED, SUBTLE

SORT_ROLE = Qt.ItemDataRole.UserRole + 1
_ids = itertools.count(1)


@dataclass
class Row:
    url: str
    id: int = field(default_factory=lambda: next(_ids))
    status: str = STATUS_WAIT
    message: str = ""
    values: dict[str, Any] = field(default_factory=dict)


class ResultsModel(QAbstractTableModel):
    def __init__(self, task: TaskSpec, parent=None):
        super().__init__(parent)
        self.task = task
        self.columns: list[tuple[str, str, str]] = [
            ("_no", "No", "int"),
            ("url", "URL", "text"),
            *[(c.key, c.header, c.kind) for c in task.columns],
            ("status", "상태", "text"),
            ("message", "비고", "text"),
        ]
        self.rows: list[Row] = []
        self._bold = QFont()
        self._bold.setBold(True)

    # ------------------------------------------------------------ Qt 모델
    def rowCount(self, parent=QModelIndex()):  # noqa: N802
        return 0 if parent.isValid() else len(self.rows)

    def columnCount(self, parent=QModelIndex()):  # noqa: N802
        return 0 if parent.isValid() else len(self.columns)

    def headerData(self, section, orientation, role=Qt.ItemDataRole.DisplayRole):  # noqa: N802
        if orientation != Qt.Orientation.Horizontal:
            return None
        key, header, kind = self.columns[section]
        if role == Qt.ItemDataRole.DisplayRole:
            return header
        if role == Qt.ItemDataRole.TextAlignmentRole:
            if key == "status" or key == "_no":
                return int(Qt.AlignmentFlag.AlignCenter)
            if kind == "int":
                return int(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            return int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        return None

    def raw(self, row: Row, key: str, index: int) -> Any:
        if key == "_no":
            return index + 1
        if key == "url":
            return row.url
        if key == "status":
            return row.status
        if key == "message":
            return row.message
        return row.values.get(key)

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid():
            return None
        row = self.rows[index.row()]
        key, _header, kind = self.columns[index.column()]
        value = self.raw(row, key, index.row())

        if role == Qt.ItemDataRole.DisplayRole:
            if kind == "int":
                return f"{value:,}" if isinstance(value, int) else ("-" if row.status not in (STATUS_WAIT, STATUS_RUNNING) else "")
            if key == "status":
                return value
            if value in (None, ""):
                return "-" if key not in ("message",) and row.status not in (STATUS_WAIT, STATUS_RUNNING) else ""
            return str(value)
        if role == SORT_ROLE:
            if kind == "int":
                return value if isinstance(value, int) else -1
            return "" if value is None else str(value)
        if role == Qt.ItemDataRole.TextAlignmentRole:
            if kind == "int":
                align = Qt.AlignmentFlag.AlignCenter if key == "_no" else Qt.AlignmentFlag.AlignRight
                return int(align | Qt.AlignmentFlag.AlignVCenter)
            if key == "status":
                return int(Qt.AlignmentFlag.AlignCenter)
            return int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        if role == Qt.ItemDataRole.ForegroundRole:
            if key in ("_no", "message"):
                return QBrush(QColor(MUTED))
            if key == "url":
                return QBrush(QColor("#48484A"))
            if kind == "int" and not isinstance(value, int):
                return QBrush(QColor(SUBTLE))
        if role == Qt.ItemDataRole.FontRole and kind == "int" and key != "_no" and isinstance(value, int):
            return self._bold
        if role == Qt.ItemDataRole.ToolTipRole:
            parts = []
            if key in ("url", "title", "name") and value:
                parts.append(str(value))
            if row.message:
                parts.append(f"[{row.status}] {row.message}")
            return "\n".join(parts) or None
        return None

    # ------------------------------------------------------------ 조작
    def set_urls(self, urls: list[str]) -> list[int]:
        self.beginResetModel()
        self.rows = [Row(url) for url in urls]
        self.endResetModel()
        return [r.id for r in self.rows]

    def clear(self) -> None:
        self.beginResetModel()
        self.rows = []
        self.endResetModel()

    def row_index(self, row_id: int) -> int:
        for i, row in enumerate(self.rows):
            if row.id == row_id:
                return i
        return -1

    def find(self, row_id: int) -> Row | None:
        i = self.row_index(row_id)
        return self.rows[i] if i >= 0 else None

    def _changed(self, i: int) -> None:
        self.dataChanged.emit(self.index(i, 0), self.index(i, len(self.columns) - 1))

    def mark(self, row_ids: list[int], status: str) -> None:
        for row_id in row_ids:
            i = self.row_index(row_id)
            if i >= 0:
                self.rows[i].status = status
                if status in (STATUS_WAIT, STATUS_RUNNING):
                    self.rows[i].message = ""
                self._changed(i)

    def apply(self, row_id: int, result: RowResult) -> None:
        i = self.row_index(row_id)
        if i < 0:
            return
        row = self.rows[i]
        row.status = result.status
        row.message = result.message
        if result.values:
            row.values = dict(result.values)
        self._changed(i)

    def remove_ids(self, row_ids: set[int]) -> None:
        self.beginResetModel()
        self.rows = [r for r in self.rows if r.id not in row_ids]
        self.endResetModel()

    def ids_with_status(self, statuses: tuple[str, ...]) -> list[int]:
        return [r.id for r in self.rows if r.status in statuses]

    def counts(self) -> dict[str, int]:
        out: dict[str, int] = {}
        for r in self.rows:
            out[r.status] = out.get(r.status, 0) + 1
        return out

    def tsv_value(self, row: Row, key: str, index: int) -> str:
        value = self.raw(row, key, index)
        if value in (None, ""):
            return "-" if key not in ("message",) else ""
        return str(value).replace("\t", " ").replace("\n", " ")

    def sheet_data(self) -> SheetData:
        rows = [
            {"url": r.url, "status": r.status, "message": r.message, **r.values}
            for r in self.rows
        ]
        return SheetData(self.task.title, self.task.description, self.task.columns, rows, self.task.notes)
