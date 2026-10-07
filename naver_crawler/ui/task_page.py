"""작업 한 개(카페 정보, 블로그 포스팅 등)의 화면: 왼쪽 URL 입력 + 실행, 오른쪽 결과 표."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QSize, QSortFilterProxyModel, Qt, QUrl, Signal
from PySide6.QtGui import QDesktopServices, QGuiApplication, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QAbstractItemView,
    QFileDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMenu,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QSpinBox,
    QSplitter,
    QStackedWidget,
    QTableView,
    QVBoxLayout,
    QWidget,
)

from naver_crawler.config import Settings
from naver_crawler.crawlers import (
    STATUS_CANCELLED,
    STATUS_FAIL,
    STATUS_NO_WIDGET,
    STATUS_OK,
    STATUS_PARTIAL,
    STATUS_RUNNING,
    STATUS_WAIT,
    RowResult,
    TaskSpec,
)
from naver_crawler.links import SUPPORTED, dedupe, load_links_file
from naver_crawler.parsing import split_urls
from naver_crawler.ui.results_model import SORT_ROLE, ResultsModel
from naver_crawler.ui.theme import BLACK, icon
from naver_crawler.ui.widgets import ElideMiddleDelegate, EmptyState, StatChips, StatusDelegate, UrlEdit, card

RETRY_STATUSES = (STATUS_FAIL, STATUS_PARTIAL, STATUS_CANCELLED, STATUS_WAIT)
IDLE_HINT = "Ctrl+Enter 로도 시작할 수 있어요"


class TaskPage(QWidget):
    start_requested = Signal(object, list)   # (page, row_ids)
    stop_requested = Signal()
    export_requested = Signal(object)        # page
    message = Signal(str)

    def __init__(self, task: TaskSpec, settings: Settings, parent=None):
        super().__init__(parent)
        self.task = task
        self.settings = settings
        self.model = ResultsModel(task, self)
        self.proxy = QSortFilterProxyModel(self)
        self.proxy.setSourceModel(self.model)
        self.proxy.setSortRole(SORT_ROLE)
        self._total = 0
        self._done = 0
        self._running = False
        self._build()
        self.model.modelReset.connect(self._sync_empty)
        self.set_running(False, False)
        self.refresh_summary()

    # ------------------------------------------------------------ 화면 구성
    def _build(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(28, 4, 28, 22)
        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setChildrenCollapsible(False)
        splitter.addWidget(self._build_input())
        splitter.addWidget(self._build_results())
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([300, 920])
        root.addWidget(splitter, 1)

        QShortcut(QKeySequence("Ctrl+Return"), self, activated=self.start_all)
        QShortcut(QKeySequence.StandardKey.Copy, self.table, activated=self.copy_selection)

    def _build_input(self) -> QWidget:
        box, lv = card()
        box.setMinimumWidth(270)
        box.setMaximumWidth(460)

        head = QHBoxLayout()
        head.setSpacing(8)
        title = QLabel("URL 입력")
        title.setObjectName("CardTitle")
        self.url_count = QLabel("0개")
        self.url_count.setObjectName("CountChip")
        head.addWidget(title)
        head.addWidget(self.url_count)
        head.addStretch(1)
        open_btn = QPushButton("파일 불러오기")
        open_btn.setObjectName("Small")
        open_btn.setToolTip("txt · csv · xlsx 파일에서 링크만 읽어오기 (입력칸에 끌어다 놓아도 됨)")
        open_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        open_btn.clicked.connect(self._open_file)
        head.addWidget(open_btn)
        lv.addLayout(head)

        self.url_edit = UrlEdit()
        self.url_edit.setObjectName("UrlInput")
        self.url_edit.setPlaceholderText(
            self.task.placeholder
            + "\n\n글이 섞여 있어도 링크만 골라 읽습니다."
            + "\ntxt · 엑셀 파일을 여기로 끌어다 놓아도 됩니다."
        )
        self.url_edit.files_dropped.connect(self.load_files)
        self.url_edit.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        self.url_edit.textChanged.connect(self._update_url_count)
        lv.addWidget(self.url_edit, 1)

        tools = QHBoxLayout()
        tools.setSpacing(2)
        tools.setContentsMargins(0, 0, 0, 0)
        for text, slot, tip in (
            ("붙여넣기", self._paste, "클립보드 내용을 아래에 추가"),
            ("중복 제거", self._dedupe, "같은 주소를 하나만 남김"),
            ("비우기", self._clear_all, "입력과 결과를 모두 지움"),
        ):
            btn = QPushButton(text)
            btn.setObjectName("Link")
            btn.setToolTip(tip)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.clicked.connect(slot)
            tools.addWidget(btn)
        tools.addStretch(1)
        lv.addLayout(tools)

        if self.task.id == "cafe_avg":
            opt = QHBoxLayout()
            opt.setSpacing(6)
            for label, attr, lo, hi in (("페이지", "avg_page", 1, 1000), ("페이지당 글", "avg_per_page", 5, 50)):
                lab = QLabel(label)
                lab.setObjectName("OptionLabel")
                spin = QSpinBox()
                spin.setRange(lo, hi)
                spin.setValue(getattr(self.settings, attr))
                spin.valueChanged.connect(lambda v, a=attr: setattr(self.settings, a, v))
                opt.addWidget(lab)
                opt.addWidget(spin)
                opt.addSpacing(8)
            opt.addStretch(1)
            lv.addLayout(opt)

        self.start_btn = QPushButton("  수집 시작")
        self.start_btn.setObjectName("Primary")
        self.start_btn.setIcon(icon("play", "#FFFFFF", disabled="#FFFFFF"))
        self.start_btn.setIconSize(QSize(16, 16))
        self.start_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.start_btn.clicked.connect(self.start_all)
        self.stop_btn = QPushButton("  중지")
        self.stop_btn.setObjectName("Stop")
        self.stop_btn.setIcon(icon("stop", "#FFFFFF"))
        self.stop_btn.setIconSize(QSize(16, 16))
        self.stop_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.stop_btn.clicked.connect(self.stop_requested.emit)
        lv.addWidget(self.start_btn)
        lv.addWidget(self.stop_btn)

        self.progress = QProgressBar()
        self.progress.setRange(0, 1)
        self.progress.setValue(0)
        self.progress.setTextVisible(False)
        self.status_text = QLabel(IDLE_HINT)
        self.status_text.setObjectName("StatusText")
        lv.addWidget(self.progress)
        lv.addWidget(self.status_text)
        return box

    def _build_results(self) -> QWidget:
        box, rv = card(margins=(20, 16, 20, 12), spacing=10)
        head = QHBoxLayout()
        head.setSpacing(8)
        title = QLabel("결과")
        title.setObjectName("CardTitle")
        self.summary = StatChips()
        head.addWidget(title)
        head.addSpacing(4)
        head.addWidget(self.summary)
        head.addStretch(1)

        self.retry_btn = QPushButton(" 실패 재시도")
        self.retry_btn.setObjectName("Ghost")
        self.retry_btn.setIcon(icon("retry", BLACK))
        self.retry_btn.setToolTip("실패 · 일부 누락 · 중지된 항목만 다시 수집")
        self.retry_btn.clicked.connect(self._retry_failed)
        self.copy_btn = QPushButton(" 표 복사")
        self.copy_btn.setObjectName("Ghost")
        self.copy_btn.setIcon(icon("copy", BLACK))
        self.copy_btn.setToolTip("엑셀에 바로 붙여넣을 수 있게 전체 복사 (Ctrl+C 는 선택 영역만)")
        self.copy_btn.clicked.connect(self.copy_all)
        self.excel_btn = QPushButton(" 엑셀 저장")
        self.excel_btn.setObjectName("Excel")
        self.excel_btn.setIcon(icon("excel", "#FFFFFF", disabled="#FFFFFF"))
        self.excel_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.excel_btn.clicked.connect(lambda: self.export_requested.emit(self))
        for b in (self.retry_btn, self.copy_btn, self.excel_btn):
            b.setIconSize(QSize(16, 16))
            head.addWidget(b)
        rv.addLayout(head)

        self.table = QTableView()
        self.table.setModel(self.proxy)
        self.table.setSortingEnabled(True)
        self.table.sortByColumn(-1, Qt.SortOrder.AscendingOrder)
        self.table.setShowGrid(False)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectItems)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setWordWrap(False)
        self.table.setMouseTracking(True)
        self.table.verticalHeader().setVisible(False)
        self.table.verticalHeader().setDefaultSectionSize(40)
        self.table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self._context_menu)
        self.table.doubleClicked.connect(self._open_index)
        self._status_delegate = StatusDelegate(self.table)
        self._url_delegate = ElideMiddleDelegate(self.table)

        header = self.table.horizontalHeader()
        header.setHighlightSections(False)
        header.setStretchLastSection(False)
        header.setMinimumSectionSize(40)
        header.setDefaultAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        # URL 과 첫 텍스트 열(제목/카페명/블로그명)이 남는 폭을 나눠 쓰고, 숫자 열은 항상 보이게
        text_keys = [c.key for c in self.task.columns if c.kind == "text" and c.key != "url"]
        main_text = next((k for k in text_keys if k in ("title", "name")), text_keys[0] if text_keys else "url")
        stretch_keys = {"url", main_text}
        hidden_keys = {"message", "club_id", "blog_id"}  # 표에서는 숨기고 엑셀에는 포함
        fm = header.fontMetrics()
        for i, (key, _h, kind) in enumerate(self.model.columns):
            col = next((c for c in self.task.columns if c.key == key), None)
            if key == "status":
                self.table.setItemDelegateForColumn(i, self._status_delegate)
            if key == "url":
                self.table.setItemDelegateForColumn(i, self._url_delegate)
            if key in stretch_keys:
                header.setSectionResizeMode(i, QHeaderView.ResizeMode.Stretch)
                continue
            header.setSectionResizeMode(i, QHeaderView.ResizeMode.Interactive)
            if key == "_no":
                width = 48
            elif key == "status":
                width = 104
            elif kind == "int":
                width = max(72, fm.horizontalAdvance(_h) + 30)
            else:
                width = min(120, max(84, (col.width if col else 12) * 6))
            self.table.setColumnWidth(i, width)
            if key in hidden_keys:
                self.table.setColumnHidden(i, True)

        self.empty = EmptyState("아직 수집한 결과가 없어요", "왼쪽에 URL 을 붙여넣고 [수집 시작]을 누르세요.")
        self.result_stack = QStackedWidget()
        self.result_stack.addWidget(self.empty)
        self.result_stack.addWidget(self.table)
        rv.addWidget(self.result_stack, 1)
        return box

    def _sync_empty(self) -> None:
        self.result_stack.setCurrentWidget(self.table if self.model.rows else self.empty)

    # ------------------------------------------------------------ URL 입력
    def urls(self) -> list[str]:
        return split_urls(self.url_edit.toPlainText())

    def _update_url_count(self) -> None:
        self.url_count.setText(f"{len(self.urls())}개")

    def _open_file(self) -> None:
        patterns = " ".join(f"*{ext}" for ext in SUPPORTED)
        paths, _ = QFileDialog.getOpenFileNames(self, "링크 파일 열기", "", f"링크 파일 ({patterns});;모든 파일 (*)")
        if paths:
            self.load_files(paths)

    def load_files(self, paths: list) -> None:
        """파일 안의 링크만 뽑아 입력칸 뒤에 붙인다 (이미 있는 주소는 건너뜀)."""
        if self._running:
            return
        found: list[str] = []
        failed = []
        for path in paths:
            try:
                found += load_links_file(path)
            except Exception:  # noqa: BLE001 - 깨진 파일 하나 때문에 멈추지 않게
                failed.append(Path(path).name)
        new, skipped = dedupe(found, self.urls())
        if new:
            current = self.url_edit.toPlainText().rstrip()
            self.url_edit.setPlainText((current + "\n" if current else "") + "\n".join(new))
        names = ", ".join(Path(p).name for p in paths[:2]) + (" 외" if len(paths) > 2 else "")
        msg = f"{names}: 링크 {len(new)}개 추가" + (f" (중복 {skipped}개 제외)" if skipped else "")
        if not found:
            msg = f"{names}: 링크를 찾지 못했습니다"
        if failed:
            msg += f" · 읽기 실패: {', '.join(failed)}"
        self.message.emit(msg)

    def _paste(self) -> None:
        text = QGuiApplication.clipboard().text()
        if text:
            current = self.url_edit.toPlainText().rstrip()
            self.url_edit.setPlainText((current + "\n" if current else "") + text.strip())

    def _dedupe(self) -> None:
        urls = self.urls()
        out = list(dict.fromkeys(urls))
        self.url_edit.setPlainText("\n".join(out))
        self.message.emit(f"중복 {len(urls) - len(out)}개 제거")

    def _clear_all(self) -> None:
        if self._running:
            return
        self.url_edit.clear()
        self.model.clear()
        self.refresh_summary()
        self.progress.setValue(0)
        self.status_text.setText(IDLE_HINT)

    # ------------------------------------------------------------ 실행
    def start_all(self) -> None:
        if self._running or not self.start_btn.isEnabled():
            return
        urls = self.urls()
        if not urls:
            self.message.emit("URL 을 먼저 입력하세요.")
            self.url_edit.setFocus()
            return
        ids = self.model.set_urls(urls)
        self.refresh_summary()
        self.start_requested.emit(self, ids)

    def _retry_failed(self) -> None:
        if self._running:
            return
        ids = self.model.ids_with_status(RETRY_STATUSES)
        if not ids:
            self.message.emit("다시 수집할 항목이 없습니다.")
            return
        self.model.mark(ids, STATUS_WAIT)
        self.start_requested.emit(self, ids)

    def _retry_selected(self) -> None:
        ids = self.selected_ids()
        if ids and not self._running:
            self.model.mark(ids, STATUS_WAIT)
            self.start_requested.emit(self, ids)

    def job_items(self, ids: list[int]) -> list[tuple[int, str]]:
        return [(row_id, self.model.find(row_id).url) for row_id in ids if self.model.find(row_id)]

    def set_running(self, running: bool, other_busy: bool) -> None:
        self._running = running
        self.start_btn.setVisible(not running)
        self.stop_btn.setVisible(running)
        self.start_btn.setEnabled(not running and not other_busy)
        self.stop_btn.setEnabled(running)
        self.retry_btn.setEnabled(not running and not other_busy)
        self.url_edit.setReadOnly(running)
        self.start_btn.setToolTip("다른 탭에서 수집 중입니다" if other_busy and not running else "Ctrl+Enter")

    def job_started(self, total: int) -> None:
        self._total, self._done = total, 0
        self._finished_ids: set[int] = set()
        self.progress.setRange(0, max(1, total))
        self.progress.setValue(0)
        self.status_text.setText(f"준비 중… (0 / {total})")

    def row_started(self, row_id: int) -> None:
        self.model.mark([row_id], STATUS_RUNNING)
        i = self.model.row_index(row_id)
        if i >= 0:
            self.table.scrollTo(self.proxy.mapFromSource(self.model.index(i, 0)))
        if row_id in getattr(self, "_finished_ids", set()):
            self.status_text.setText(f"{self._done} / {self._total} · 빈 값 크롬으로 다시 확인 중…")
        else:
            self.status_text.setText(f"{self._done} / {self._total} 수집 중…")

    def row_finished(self, row_id: int, result: RowResult) -> None:
        self.model.apply(row_id, result)
        finished = getattr(self, "_finished_ids", set())
        if row_id not in finished:  # 크롬 재확인으로 같은 행이 두 번 끝나도 진행률은 한 번만
            finished.add(row_id)
            self._done += 1
            self.progress.setValue(self._done)
        self.refresh_summary()

    def job_finished(self, completed: bool, error: str) -> None:
        stuck = self.model.ids_with_status((STATUS_RUNNING,))
        self.model.mark(stuck, STATUS_CANCELLED)
        if error:
            self.status_text.setText(f"오류: {error}")
        elif completed:
            self.status_text.setText(f"완료 · {self._done}건 처리")
        else:
            self.status_text.setText(f"중지됨 · {self._done} / {self._total}")
        self.refresh_summary()
        self.apply_default_sort()

    def apply_default_sort(self) -> None:
        """작업에 정렬 기준이 있으면(블로그: 이웃수) 큰 값부터 정렬. 수집 중엔 행이 튀지 않게 끝난 뒤에만."""
        keys = [k for k, _h, _kind in self.model.columns]
        if self.task.sort_desc in keys:
            self.table.sortByColumn(keys.index(self.task.sort_desc), Qt.SortOrder.DescendingOrder)

    def refresh_summary(self) -> None:
        c = self.model.counts()
        self.summary.set_counts(
            len(self.model.rows),
            [(s, c.get(s, 0)) for s in (STATUS_OK, STATUS_PARTIAL, STATUS_FAIL, STATUS_NO_WIDGET)],
        )
        has_rows = bool(self.model.rows)
        self.copy_btn.setEnabled(has_rows)
        self.excel_btn.setEnabled(has_rows)
        self._sync_empty()

    # ------------------------------------------------------------ 표 조작
    def selected_ids(self) -> list[int]:
        rows = sorted({self.proxy.mapToSource(i).row() for i in self.table.selectionModel().selectedIndexes()})
        return [self.model.rows[r].id for r in rows if 0 <= r < len(self.model.rows)]

    def _visible_rows(self) -> list[int]:
        return [self.proxy.mapToSource(self.proxy.index(r, 0)).row() for r in range(self.proxy.rowCount())]

    def copy_all(self) -> None:
        keys = [k for k, _h, _kind in self.model.columns]
        lines = ["\t".join(h for _k, h, _kind in self.model.columns)]
        for src in self._visible_rows():
            row = self.model.rows[src]
            lines.append("\t".join(self.model.tsv_value(row, k, src) for k in keys))
        QGuiApplication.clipboard().setText("\n".join(lines))
        self.message.emit(f"{len(lines) - 1}행을 복사했습니다. 엑셀에 붙여넣기 하세요.")

    def copy_selection(self) -> None:
        indexes = self.table.selectionModel().selectedIndexes()
        if not indexes:
            return
        cells: dict[tuple[int, int], str] = {}
        for idx in indexes:
            src = self.proxy.mapToSource(idx)
            key = self.model.columns[src.column()][0]
            cells[(idx.row(), idx.column())] = self.model.tsv_value(self.model.rows[src.row()], key, src.row())
        rows = sorted({r for r, _ in cells})
        cols = sorted({c for _, c in cells})
        QGuiApplication.clipboard().setText("\n".join("\t".join(cells.get((r, c), "") for c in cols) for r in rows))
        self.message.emit(f"{len(indexes)}칸 복사")

    def copy_column(self, column: int) -> None:
        key = self.model.columns[column][0]
        values = [self.model.tsv_value(self.model.rows[src], key, src) for src in self._visible_rows()]
        QGuiApplication.clipboard().setText("\n".join(values))
        self.message.emit(f"'{self.model.columns[column][1]}' 열 {len(values)}개 복사")

    def _open_index(self, index) -> None:
        src = self.proxy.mapToSource(index)
        if self.model.columns[src.column()][0] == "url":
            QDesktopServices.openUrl(QUrl(self.model.rows[src.row()].url))

    def _remove_selected(self) -> None:
        self.model.remove_ids(set(self.selected_ids()))
        self.refresh_summary()

    def _context_menu(self, pos) -> None:
        index = self.table.indexAt(pos)
        menu = QMenu(self)
        menu.addAction("선택 영역 복사\tCtrl+C", self.copy_selection)
        if index.isValid():
            src = self.proxy.mapToSource(index)
            col_name = self.model.columns[src.column()][1]
            url = self.model.rows[src.row()].url
            menu.addAction(f"'{col_name}' 열 전체 복사", lambda: self.copy_column(src.column()))
            menu.addAction("브라우저로 열기", lambda: QDesktopServices.openUrl(QUrl(url)))
        menu.addSeparator()
        retry = menu.addAction("선택 행 다시 수집", self._retry_selected)
        remove = menu.addAction("선택 행 삭제", self._remove_selected)
        retry.setEnabled(not self._running)
        remove.setEnabled(not self._running)
        menu.exec(self.table.viewport().mapToGlobal(pos))
