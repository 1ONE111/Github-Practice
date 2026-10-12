"""화면: 왼쪽 링크 입력 · 실행, 오른쪽 결과 표, 위쪽 인스타 로그인 상태."""

from __future__ import annotations

import datetime as dt
import itertools
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from PySide6.QtCore import (
    QAbstractTableModel,
    QModelIndex,
    QObject,
    QSize,
    QSortFilterProxyModel,
    QStandardPaths,
    Qt,
    QThread,
    QUrl,
    Signal,
    Slot,
)
from PySide6.QtGui import QBrush, QColor, QDesktopServices, QFont, QGuiApplication, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QSplitter,
    QTableView,
    QVBoxLayout,
    QWidget,
)

from insta_crawler import APP_NAME, __version__
from insta_crawler.client import InstaClient
from insta_crawler.collector import (
    COLUMNS,
    RETRY_STATUSES,
    STATUS_CANCELLED,
    STATUS_FAIL,
    STATUS_OK,
    STATUS_PARTIAL,
    STATUS_PRIVATE,
    STATUS_RUNNING,
    STATUS_WAIT,
    RowResult,
    Runner,
    StopRun,
    notes,
)
from insta_crawler.config import Settings, chrome_profile_dir, clear_session, load_session, save_session
from insta_crawler.files import SUPPORTED, default_filename, export_xlsx, read_links_text
from insta_crawler.parsing import Target, parse_targets
from insta_crawler.theme import BLACK, MUTED, StatChips, StatusDelegate, brand_mark_pixmap, icon

def card(margins=(20, 18, 20, 18), spacing: int = 12) -> tuple[QFrame, QVBoxLayout]:
    frame = QFrame()
    frame.setObjectName("Card")
    layout = QVBoxLayout(frame)
    layout.setContentsMargins(*margins)
    layout.setSpacing(spacing)
    return frame, layout


# ---------------------------------------------------------------- 결과 표

SORT_ROLE = Qt.ItemDataRole.UserRole + 1
_ids = itertools.count(1)
TABLE_COLUMNS = [c for c in COLUMNS if c.key not in ("url",)]  # 링크는 엑셀에만 (표는 아이디로 충분)


@dataclass
class Row:
    target: Target
    id: int = field(default_factory=lambda: next(_ids))
    status: str = STATUS_WAIT
    message: str = ""
    values: dict[str, Any] = field(default_factory=dict)

    def url(self) -> str:
        return self.values.get("url") or (
            f"https://www.instagram.com/{self.target.username}/" if self.target.username else self.target.raw
        )


class ResultsModel(QAbstractTableModel):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.columns = [("_no", "No", "int"), *[(c.key, c.header, c.kind) for c in TABLE_COLUMNS],
                        ("status", "상태", "text"), ("message", "비고", "text")]
        self.rows: list[Row] = []
        self._bold = QFont()
        self._bold.setBold(True)

    def rowCount(self, parent=QModelIndex()):  # noqa: N802
        return 0 if parent.isValid() else len(self.rows)

    def columnCount(self, parent=QModelIndex()):  # noqa: N802
        return 0 if parent.isValid() else len(self.columns)

    def headerData(self, section, orientation, role=Qt.ItemDataRole.DisplayRole):  # noqa: N802
        if orientation == Qt.Orientation.Horizontal and role == Qt.ItemDataRole.DisplayRole:
            return self.columns[section][1]
        return None

    def raw(self, row: Row, key: str, index: int) -> Any:
        if key == "_no":
            return index + 1
        if key == "status":
            return row.status
        if key == "message":
            return row.message
        if key == "username":
            name = row.values.get("username") or row.target.username
            return f"@{name}" if name else row.target.raw
        return row.values.get(key)

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid():
            return None
        row = self.rows[index.row()]
        key, _header, kind = self.columns[index.column()]
        value = self.raw(row, key, index.row())
        pending = row.status in (STATUS_WAIT, STATUS_RUNNING)
        if role == Qt.ItemDataRole.DisplayRole:
            if kind == "int":
                return f"{value:,}" if isinstance(value, int) else ("" if pending else "-")
            if value in (None, ""):
                return "" if pending or key == "message" else "-"
            return str(value)
        if role == SORT_ROLE:
            if kind == "int":
                return value if isinstance(value, int) else -1
            return "" if value is None else str(value)
        if role == Qt.ItemDataRole.TextAlignmentRole:
            if key in ("_no", "status"):
                return int(Qt.AlignmentFlag.AlignCenter)
            align = Qt.AlignmentFlag.AlignRight if kind == "int" else Qt.AlignmentFlag.AlignLeft
            return int(align | Qt.AlignmentFlag.AlignVCenter)
        if role == Qt.ItemDataRole.ForegroundRole and key in ("_no", "message"):
            return QBrush(QColor(MUTED))
        if role == Qt.ItemDataRole.FontRole and kind == "int" and key != "_no" and isinstance(value, int):
            return self._bold
        if role == Qt.ItemDataRole.ToolTipRole:
            parts = [row.target.raw]
            if row.message:
                parts.append(f"[{row.status}] {row.message}")
            return "\n".join(parts)
        return None

    # ------------------------------------------------------------ 조작
    def set_targets(self, targets: list[Target]) -> list[int]:
        self.beginResetModel()
        self.rows = [Row(t) for t in targets]
        self.endResetModel()
        return [r.id for r in self.rows]

    def find(self, row_id: int) -> tuple[int, Row | None]:
        for i, row in enumerate(self.rows):
            if row.id == row_id:
                return i, row
        return -1, None

    def _changed(self, i: int) -> None:
        self.dataChanged.emit(self.index(i, 0), self.index(i, len(self.columns) - 1))

    def mark(self, row_ids: list[int], status: str) -> None:
        for row_id in row_ids:
            i, row = self.find(row_id)
            if row is not None:
                row.status = status
                if status in (STATUS_WAIT, STATUS_RUNNING):
                    row.message = ""
                self._changed(i)

    def apply(self, row_id: int, result: RowResult) -> None:
        i, row = self.find(row_id)
        if row is None:
            return
        row.status, row.message = result.status, result.message
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

    def export_rows(self) -> list[dict]:
        rows = []
        for r in self.rows:
            username = r.values.get("username") or r.target.username or r.target.raw
            rows.append({**r.values, "username": username, "url": r.url(), "status": r.status, "message": r.message})
        return rows

    def tsv(self, rows: list[Row] | None = None) -> str:
        rows = self.rows if rows is None else rows
        lines = ["\t".join(h for _k, h, _kind in self.columns)]
        for row in rows:
            i = self.rows.index(row)
            cells = []
            for key, _h, _kind in self.columns:
                value = self.raw(row, key, i)
                cells.append("" if value is None else str(value).replace("\t", " ").replace("\n", " "))
            lines.append("\t".join(cells))
        return "\n".join(lines)


# ---------------------------------------------------------------- 백그라운드 작업


class Job(QObject):
    row_started = Signal(object)
    row_finished = Signal(object, object)
    log = Signal(str)
    finished = Signal(bool, str, object)  # (끝까지 완료했는지, 오류 메시지, 결과값)

    def __init__(self, fn: Callable[["Job"], Any]):
        super().__init__()
        self.fn = fn

    @Slot()
    def run(self) -> None:
        try:
            value = self.fn(self)
            self.finished.emit(value is not False, "", value)
        except StopRun as exc:
            self.finished.emit(False, str(exc), None)
        except Exception as exc:  # noqa: BLE001
            from insta_crawler.login import friendly_error

            self.finished.emit(False, friendly_error(exc), None)


def start_job(job: Job, parent: QObject, on_done: Callable[[], None]) -> QThread:
    thread = QThread(parent)
    job.moveToThread(thread)
    thread.started.connect(job.run)
    job.finished.connect(thread.quit)
    job.finished.connect(job.deleteLater)
    thread.finished.connect(on_done)
    thread.finished.connect(thread.deleteLater)
    thread.start()
    return thread


# ---------------------------------------------------------------- 메인 창

PLACEHOLDER = (
    "https://www.instagram.com/아이디\n"
    "@아이디 또는 아이디만 적어도 됩니다\n\n"
    "한 줄에 하나씩. 글이 섞여 있어도 인스타 링크만 골라 읽습니다.\n"
    "txt · 엑셀 파일을 여기로 끌어다 놓아도 됩니다."
)


class LinkEdit(QPlainTextEdit):
    files_dropped = Signal(list)

    def __init__(self):
        super().__init__()
        self.setAcceptDrops(True)

    @staticmethod
    def _files(event) -> list[str]:
        mime = event.mimeData()
        return [u.toLocalFile() for u in mime.urls() if u.isLocalFile()] if mime.hasUrls() else []

    def dragEnterEvent(self, event) -> None:  # noqa: N802
        event.acceptProposedAction() if self._files(event) else super().dragEnterEvent(event)

    def dragMoveEvent(self, event) -> None:  # noqa: N802
        event.acceptProposedAction() if self._files(event) else super().dragMoveEvent(event)

    def dropEvent(self, event) -> None:  # noqa: N802
        files = self._files(event)
        if files:
            event.acceptProposedAction()
            self.files_dropped.emit(files)
        else:
            super().dropEvent(event)


class MainWindow(QMainWindow):
    def __init__(self, settings: Settings):
        super().__init__()
        self.settings = settings
        self.model = ResultsModel(self)
        self.proxy = QSortFilterProxyModel(self)
        self.proxy.setSourceModel(self.model)
        self.proxy.setSortRole(SORT_ROLE)
        self.stop_event = threading.Event()
        self.thread: QThread | None = None
        self.job: Job | None = None  # 파이썬 쪽 참조를 잡아 둬야 작업 객체가 실행 전에 지워지지 않는다
        self.busy = False
        self._total = self._done = 0

        self.setWindowTitle(f"{APP_NAME} {__version__}")
        self.setMinimumSize(980, 600)
        self.resize(1280, 780)
        self._build()
        self.refresh_login()
        self._set_running(False)
        self._refresh_summary()
        self.statusBar().showMessage("준비됨")

    # ------------------------------------------------------------ 화면 구성
    def _build(self) -> None:
        self.log_view = QPlainTextEdit()
        self.log_view.setObjectName("Log")
        self.log_view.setReadOnly(True)
        self.log_view.setMaximumBlockCount(3000)
        self.log_view.setFixedHeight(150)
        self.log_view.setVisible(False)

        root = QWidget()
        root.setObjectName("Root")
        outer = QVBoxLayout(root)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        content = QWidget()
        v = QVBoxLayout(content)
        v.setContentsMargins(28, 22, 28, 20)
        v.setSpacing(16)

        head = QHBoxLayout()
        head.setSpacing(12)
        mark = QLabel()
        mark.setPixmap(brand_mark_pixmap(40))
        head.addWidget(mark, 0, Qt.AlignmentFlag.AlignVCenter)
        titles = QVBoxLayout()
        titles.setSpacing(2)
        title = QLabel("인스타 계정 지표")
        title.setObjectName("PageTitle")
        self.desc = QLabel()
        self.desc.setObjectName("PageDesc")
        titles.addWidget(title)
        titles.addWidget(self.desc)
        head.addLayout(titles)
        head.addStretch(1)
        self.login_state = QLabel()
        self.login_state.setObjectName("LoginState")
        self.login_btn = QPushButton(" 인스타 로그인")
        self.login_btn.setIconSize(QSize(16, 16))
        self.login_btn.clicked.connect(self.login_or_logout)
        head.addWidget(self.login_state, 0, Qt.AlignmentFlag.AlignVCenter)
        head.addSpacing(8)
        head.addWidget(self.login_btn, 0, Qt.AlignmentFlag.AlignVCenter)
        v.addLayout(head)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setChildrenCollapsible(False)
        splitter.setHandleWidth(16)
        splitter.addWidget(self._build_input())
        splitter.addWidget(self._build_results())
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([320, 920])
        v.addWidget(splitter, 1)
        outer.addWidget(content, 1)
        outer.addWidget(self.log_view)
        self.setCentralWidget(root)

        QShortcut(QKeySequence("Ctrl+Return"), self, activated=self.start_all)
        QShortcut(QKeySequence("Ctrl+S"), self, activated=self.export)
        QShortcut(QKeySequence.StandardKey.Copy, self.table, activated=self.copy_selection)

    def _build_input(self) -> QWidget:
        box, lv = card()
        box.setMinimumWidth(280)
        box.setMaximumWidth(460)
        head = QHBoxLayout()
        label = QLabel("링크 입력")
        label.setObjectName("CardTitle")
        self.count_chip = QLabel("0개")
        self.count_chip.setObjectName("CountChip")
        head.addWidget(label)
        head.addWidget(self.count_chip)
        head.addStretch(1)
        open_btn = QPushButton("파일 불러오기")
        open_btn.setObjectName("Small")
        open_btn.setToolTip("txt · csv · xlsx 에서 인스타 링크만 읽어오기")
        open_btn.clicked.connect(self._open_file)
        head.addWidget(open_btn)
        lv.addLayout(head)

        self.edit = LinkEdit()
        self.edit.setPlaceholderText(PLACEHOLDER)
        self.edit.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        self.edit.textChanged.connect(self._update_count)
        self.edit.files_dropped.connect(self.load_files)
        lv.addWidget(self.edit, 1)

        tools = QHBoxLayout()
        tools.setSpacing(2)
        for text, slot in (("붙여넣기", self._paste), ("중복 제거", self._dedupe), ("비우기", self._clear)):
            btn = QPushButton(text)
            btn.setObjectName("Link")
            btn.clicked.connect(slot)
            tools.addWidget(btn)
        tools.addStretch(1)
        lv.addLayout(tools)

        opts = QHBoxLayout()
        opts.setSpacing(6)
        self.posts_box = QComboBox()
        for n in range(1, 13):
            self.posts_box.addItem(f"{n}개", n)
        self.posts_box.setCurrentIndex(max(1, min(12, self.settings.posts)) - 1)
        self.posts_box.currentIndexChanged.connect(lambda i: self._posts_changed(i + 1))
        self.delay_box = QComboBox()
        delays = sorted({2.0, 3.0, 5.0, 10.0, float(self.settings.request_delay)})
        for d in delays:
            self.delay_box.addItem(f"{d:g}초", d)
        self.delay_box.setCurrentIndex(delays.index(float(self.settings.request_delay)))
        self.delay_box.setToolTip("계정 사이 대기 시간. 너무 짧으면 인스타가 잠시 막습니다 (3초 이상 권장)")
        self.delay_box.currentIndexChanged.connect(
            lambda _i: setattr(self.settings, "request_delay", float(self.delay_box.currentData()))
        )
        for text, combo in (("최근 게시물", self.posts_box), ("간격", self.delay_box)):
            lab = QLabel(text)
            lab.setObjectName("OptionLabel")
            opts.addWidget(lab)
            opts.addWidget(combo)
            opts.addSpacing(6)
        opts.addStretch(1)
        lv.addLayout(opts)

        self.start_btn = QPushButton("  수집 시작")
        self.start_btn.setObjectName("Primary")
        self.start_btn.setIcon(icon("play", "#FFFFFF", disabled="#FFFFFF"))
        self.start_btn.setIconSize(QSize(16, 16))
        self.start_btn.clicked.connect(self.start_all)
        self.stop_btn = QPushButton("  중지")
        self.stop_btn.setObjectName("Stop")
        self.stop_btn.setIcon(icon("stop", "#FFFFFF"))
        self.stop_btn.setIconSize(QSize(16, 16))
        self.stop_btn.clicked.connect(self.stop)
        lv.addWidget(self.start_btn)
        lv.addWidget(self.stop_btn)
        self.progress = QProgressBar()
        self.progress.setRange(0, 1)
        self.progress.setValue(0)
        self.progress.setTextVisible(False)
        self.status_text = QLabel("Ctrl+Enter 로도 시작할 수 있어요")
        self.status_text.setObjectName("StatusText")
        lv.addWidget(self.progress)
        lv.addWidget(self.status_text)
        self._posts_changed(self.posts_box.currentData())
        return box

    def _build_results(self) -> QWidget:
        box, rv = card(margins=(20, 16, 20, 12), spacing=10)
        head = QHBoxLayout()
        label = QLabel("결과")
        label.setObjectName("CardTitle")
        self.summary = StatChips()
        head.addWidget(label)
        head.addSpacing(6)
        head.addWidget(self.summary)
        head.addStretch(1)
        self.retry_btn = QPushButton(" 실패 재시도")
        self.retry_btn.setObjectName("Ghost")
        self.retry_btn.setIcon(icon("retry", BLACK))
        self.retry_btn.setToolTip("실패 · 일부 누락 · 중지된 항목만 다시 수집")
        self.retry_btn.clicked.connect(self.retry_failed)
        self.copy_btn = QPushButton(" 표 복사")
        self.copy_btn.setObjectName("Ghost")
        self.copy_btn.setIcon(icon("copy", BLACK))
        self.copy_btn.setToolTip("엑셀에 바로 붙여넣을 수 있게 전체 복사")
        self.copy_btn.clicked.connect(self.copy_all)
        self.log_btn = QPushButton(" 로그")
        self.log_btn.setObjectName("Ghost")
        self.log_btn.setIcon(icon("log", BLACK))
        self.log_btn.setToolTip("실행 로그 보기 · 숨기기")
        self.log_btn.setCheckable(True)
        self.log_btn.toggled.connect(self.log_view.setVisible)
        self.export_btn = QPushButton(" 엑셀 저장")
        self.export_btn.setObjectName("Excel")
        self.export_btn.setIcon(icon("excel", "#FFFFFF", disabled="#FFFFFF"))
        self.export_btn.clicked.connect(self.export)
        for btn in (self.retry_btn, self.copy_btn, self.log_btn, self.export_btn):
            head.addWidget(btn)
        rv.addLayout(head)

        self.table = QTableView()
        self.table.setModel(self.proxy)
        self.table.setSortingEnabled(True)
        self.table.sortByColumn(-1, Qt.SortOrder.AscendingOrder)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setShowGrid(False)
        self.table.setWordWrap(False)
        self.table.verticalHeader().setVisible(False)
        self.table.verticalHeader().setDefaultSectionSize(36)
        self.table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self._context_menu)
        self.table.doubleClicked.connect(lambda idx: self._open_profiles([self.proxy.mapToSource(idx).row()]))
        header = self.table.horizontalHeader()
        header.setHighlightSections(False)
        header.setStretchLastSection(True)
        header.setDefaultAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        widths = {"_no": 44, "username": 140, "name": 100, "followers": 90, "avg_views": 90, "videos": 60, "status": 96,
                  "message": 80}
        for i, (key, _h, kind) in enumerate(self.model.columns):
            self.table.setColumnWidth(i, widths.get(key, 82 if kind == "int" else 120))
        status_col = [k for k, _h, _kind in self.model.columns].index("status")
        self.table.setItemDelegateForColumn(status_col, StatusDelegate(self.table))
        rv.addWidget(self.table, 1)
        return box

    # ------------------------------------------------------------ 입력
    def _update_count(self) -> None:
        self.count_chip.setText(f"{len(parse_targets(self.edit.toPlainText()))}개")

    def _posts_changed(self, value: int) -> None:
        self.settings.posts = int(value)
        self.desc.setText(f"프로필 링크로 팔로워 · 최근 {value}개 게시물 평균 좋아요 · 댓글 · 조회수(릴스)를 가져옵니다")

    def _append_lines(self, lines: list[str]) -> None:
        current = self.edit.toPlainText().rstrip("\n")
        self.edit.setPlainText("\n".join([current, *lines]) if current else "\n".join(lines))

    def _paste(self) -> None:
        text = QGuiApplication.clipboard().text()
        targets = parse_targets(text)
        if not targets:
            self.statusBar().showMessage("클립보드에 인스타 링크가 없습니다", 4000)
            return
        self._append_lines([t.raw for t in targets])
        self.statusBar().showMessage(f"{len(targets)}개 추가", 4000)

    def _dedupe(self) -> None:
        seen, lines = set(), []
        for t in parse_targets(self.edit.toPlainText()):
            key = t.username or t.shortcode or t.raw
            if key not in seen:
                seen.add(key)
                lines.append(t.raw)
        removed = len(parse_targets(self.edit.toPlainText())) - len(lines)
        self.edit.setPlainText("\n".join(lines))
        self.statusBar().showMessage(f"중복 {removed}개 제거", 4000)

    def _clear(self) -> None:
        if self.busy:
            return
        self.edit.clear()
        self.model.set_targets([])
        self._refresh_summary()

    def _open_file(self) -> None:
        start = self.settings.export_dir or QStandardPaths.writableLocation(QStandardPaths.StandardLocation.DesktopLocation)
        pattern = " ".join(f"*{s}" for s in SUPPORTED)
        files, _ = QFileDialog.getOpenFileNames(self, "링크 파일 열기", start, f"링크 목록 ({pattern})")
        if files:
            self.load_files(files)

    def load_files(self, files: list[str]) -> None:
        added = 0
        for path in files:
            if Path(path).suffix.lower() not in SUPPORTED:
                continue
            try:
                targets = parse_targets(read_links_text(path))
            except Exception as exc:  # noqa: BLE001
                QMessageBox.warning(self, "파일 열기 실패", f"{Path(path).name}\n{exc}")
                continue
            self._append_lines([t.raw for t in targets])
            added += len(targets)
        self.statusBar().showMessage(f"파일에서 {added}개 링크를 읽었습니다", 5000)

    # ------------------------------------------------------------ 로그인
    def refresh_login(self) -> None:
        cookies = load_session()
        ok = any(c.get("name") == "sessionid" and c.get("value") for c in cookies)
        self.login_state.setText("인스타 로그인됨" if ok else "비로그인 (조금만 수집하면 막힐 수 있음)")
        self.login_state.setProperty("ok", "true" if ok else "false")
        self.login_state.style().unpolish(self.login_state)
        self.login_state.style().polish(self.login_state)
        self.login_btn.setText(" 로그아웃" if ok else " 인스타 로그인")
        self.login_btn.setObjectName("Small" if ok else "ExcelSoft")
        self.login_btn.setIcon(icon("user", BLACK if ok else "#C2410C"))
        self.login_btn.style().unpolish(self.login_btn)
        self.login_btn.style().polish(self.login_btn)

    def login_or_logout(self) -> None:
        if self.busy:
            return
        if load_session():
            if QMessageBox.question(self, "로그아웃", "저장된 인스타 로그인을 지울까요?") != QMessageBox.StandardButton.Yes:
                return
            clear_session()
            import shutil

            shutil.rmtree(chrome_profile_dir(), ignore_errors=True)
            self.refresh_login()
            self.append_log("로그아웃했습니다")
            return
        from insta_crawler.login import browser_login

        self.stop_event = threading.Event()
        settings, stop = self.settings, self.stop_event
        job = Job(lambda j: browser_login(settings, stop, j.log.emit))
        job.log.connect(self.append_log)
        job.finished.connect(self._login_finished)
        self._set_running(True, login=True)
        self.status_text.setText("크롬 창에서 인스타에 로그인하세요…")
        self.job = job
        self.thread = start_job(job, self, self._thread_done)

    def _login_finished(self, _ok: bool, error: str, cookies) -> None:
        self._set_running(False)
        if error:
            QMessageBox.warning(self, "로그인 실패", error)
        elif cookies:
            save_session(cookies)
            self.append_log("인스타 로그인 완료 - 쿠키를 저장했습니다")
            self.statusBar().showMessage("인스타 로그인 완료", 5000)
        else:
            self.statusBar().showMessage("로그인하지 않고 창이 닫혔습니다", 5000)
        self.status_text.setText("")
        self.refresh_login()

    # ------------------------------------------------------------ 실행
    def start_all(self) -> None:
        if self.busy:
            return
        targets = parse_targets(self.edit.toPlainText())
        if not targets:
            self.statusBar().showMessage("인스타 링크를 입력하세요", 4000)
            self.edit.setFocus()
            return
        self.table.sortByColumn(-1, Qt.SortOrder.AscendingOrder)
        self._run(self.model.set_targets(targets))

    def retry_failed(self) -> None:
        ids = self.model.ids_with_status(RETRY_STATUSES)
        if ids and not self.busy:
            self._run(ids)

    def _run(self, row_ids: list[int]) -> None:
        self.model.mark(row_ids, STATUS_WAIT)
        items = [(rid, self.model.find(rid)[1].target) for rid in row_ids]
        self.stop_event = threading.Event()
        runner = Runner(self.settings, InstaClient(load_session()))
        stop = self.stop_event
        job = Job(lambda j: runner.run(items, stop, on_start=j.row_started.emit, on_result=j.row_finished.emit))
        runner.log = job.log.emit
        job.log.connect(self.append_log)
        job.row_started.connect(self._row_started)
        job.row_finished.connect(self._row_finished)
        job.finished.connect(self._run_finished)
        self._total, self._done = len(row_ids), 0
        self.progress.setRange(0, self._total)
        self.progress.setValue(0)
        self._set_running(True)
        self.job = job
        self.thread = start_job(job, self, self._thread_done)

    def stop(self) -> None:
        self.stop_event.set()
        self.status_text.setText("중지하는 중…")

    def _row_started(self, row_id) -> None:
        self.model.mark([row_id], STATUS_RUNNING)
        self.status_text.setText(f"{self._done + 1} / {self._total} 수집 중…")

    def _row_finished(self, row_id, result: RowResult) -> None:
        self.model.apply(row_id, result)
        self._done += 1
        self.progress.setValue(self._done)
        self._refresh_summary()

    def _run_finished(self, completed: bool, error: str, _value) -> None:
        for row_id in self.model.ids_with_status((STATUS_RUNNING,)):
            self.model.apply(row_id, RowResult({}, STATUS_CANCELLED, "중지됨"))
        self._set_running(False)
        self._refresh_summary()
        counts = self.model.counts()
        done_text = f"완료 {counts.get(STATUS_OK, 0)} · 실패 {counts.get(STATUS_FAIL, 0)}"
        self.status_text.setText(("끝 · " if completed else "멈춤 · ") + done_text)
        if error:
            self.append_log(f"[멈춤] {error}")
            QMessageBox.warning(self, "수집을 멈췄습니다", error)

    def _thread_done(self) -> None:
        self.thread = None
        self.job = None

    def _set_running(self, running: bool, login: bool = False) -> None:
        self.busy = running
        self.start_btn.setVisible(not running or login)
        self.start_btn.setEnabled(not running)
        self.stop_btn.setVisible(running and not login)
        for w in (self.retry_btn, self.export_btn, self.login_btn, self.posts_box, self.edit):
            w.setEnabled(not running)
        self.progress.setVisible(running and not login)

    def _refresh_summary(self) -> None:
        counts = self.model.counts()
        order = (STATUS_OK, STATUS_PARTIAL, STATUS_PRIVATE, STATUS_FAIL, STATUS_CANCELLED)
        self.summary.set_counts(len(self.model.rows), [(status, counts.get(status, 0)) for status in order])
        self.retry_btn.setEnabled(not self.busy and bool(self.model.ids_with_status(RETRY_STATUSES)))

    def append_log(self, text: str) -> None:
        self.log_view.appendPlainText(f"{dt.datetime.now():%H:%M:%S}  {text}")

    # ------------------------------------------------------------ 결과 다루기
    def _selected_rows(self) -> list[int]:
        rows = {self.proxy.mapToSource(i).row() for i in self.table.selectionModel().selectedRows()}
        return sorted(rows)

    def _open_profiles(self, rows: list[int]) -> None:
        for i in rows[:20]:
            QDesktopServices.openUrl(QUrl(self.model.rows[i].url()))

    def _context_menu(self, pos) -> None:
        rows = self._selected_rows()
        if not rows:
            return
        menu = QMenu(self)
        menu.addAction("프로필 열기", lambda: self._open_profiles(rows))
        menu.addAction("선택 복사", self.copy_selection)
        retry = menu.addAction("선택 다시 수집", lambda: self._run([self.model.rows[i].id for i in rows]))
        delete = menu.addAction("선택 삭제", lambda: self.model.remove_ids({self.model.rows[i].id for i in rows}))
        retry.setEnabled(not self.busy)
        delete.setEnabled(not self.busy)
        menu.exec(self.table.viewport().mapToGlobal(pos))
        self._refresh_summary()

    def copy_all(self) -> None:
        QGuiApplication.clipboard().setText(self.model.tsv())
        self.statusBar().showMessage(f"{len(self.model.rows)}행 복사 - 엑셀에 붙여넣으세요", 4000)

    def copy_selection(self) -> None:
        rows = self._selected_rows()
        if rows:
            QGuiApplication.clipboard().setText(self.model.tsv([self.model.rows[i] for i in rows]))
            self.statusBar().showMessage(f"{len(rows)}행 복사", 3000)

    def export(self) -> None:
        if self.busy or not self.model.rows:
            self.statusBar().showMessage("저장할 결과가 없습니다", 4000)
            return
        folder = self.settings.export_dir or QStandardPaths.writableLocation(QStandardPaths.StandardLocation.DesktopLocation)
        path, _ = QFileDialog.getSaveFileName(self, "엑셀 저장", str(Path(folder) / default_filename()), "Excel (*.xlsx)")
        if not path:
            return
        try:
            saved = export_xlsx(path, "인스타 계정 지표", COLUMNS, self.model.export_rows(), notes(self.settings.posts))
        except PermissionError:
            QMessageBox.warning(self, "저장 실패", "같은 이름 파일이 엑셀에서 열려 있으면 닫고 다시 저장하세요.")
            return
        self.settings.export_dir = str(saved.parent)
        self.statusBar().showMessage(f"저장됨: {saved}", 8000)
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(saved)))

    def closeEvent(self, event) -> None:  # noqa: N802
        self.stop_event.set()
        if self.thread is not None:
            self.thread.quit()
            self.thread.wait(20000)  # 진행 중인 요청 하나가 끝날 때까지만
        try:
            self.settings.save()
        except OSError:
            pass
        super().closeEvent(event)
