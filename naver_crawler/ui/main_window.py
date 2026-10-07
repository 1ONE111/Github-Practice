"""메인 창: 왼쪽 사이드바(작업 목록 · 계정), 위쪽 헤더, 가운데 작업 화면, 아래 로그."""

from __future__ import annotations

import datetime as dt
import threading
from pathlib import Path

from PySide6.QtCore import QSize, QStandardPaths, Qt, QThread, QUrl, Slot
from PySide6.QtGui import QAction, QDesktopServices, QKeySequence
from PySide6.QtWidgets import (
    QApplication,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QSplitter,
    QStackedWidget,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from naver_crawler import APP_NAME, __version__
from naver_crawler.config import Settings, app_data_dir
from naver_crawler.crawlers import STATUS_FAIL, STATUS_NO_WIDGET, STATUS_OK, TASKS
from naver_crawler.engine import Engine
from naver_crawler.excel import default_filename, export_xlsx
from naver_crawler.selectors import write_default_selectors
from naver_crawler.ui.settings_dialog import SettingsDialog
from naver_crawler.ui.task_page import TaskPage
from naver_crawler.ui.theme import BLACK, ICON, ORANGE_TEXT, brand_mark_pixmap, icon
from naver_crawler.ui.worker import Job, LogBridge, start_job

NAV_SECTIONS = (
    ("카페", ("cafe_info", "cafe_article", "cafe_avg")),
    ("블로그", ("blog_info", "blog_post")),
    ("지식iN", ("kin",)),
)
NAV_ICONS = {"cafe_info": "cafe", "cafe_article": "article", "cafe_avg": "chart",
             "blog_info": "blog", "blog_post": "post", "kin": "kin"}
PAGE_ROLE = Qt.ItemDataRole.UserRole + 10

HELP_TEXT = """<h3>사용법</h3>
<ol>
<li>왼쪽에서 작업을 고릅니다 (카페 정보, 카페 게시글, 블로그 …).</li>
<li>URL 을 한 줄에 하나씩 붙여넣고 <b>수집 시작</b> (Ctrl+Enter).</li>
<li>결과 표에서 <b>엑셀 저장</b>을 누르면 서식이 적용된 .xlsx 가 만들어집니다.<br>
    여러 탭 결과를 한 파일로 저장하려면 오른쪽 위 <b>전체 엑셀 저장</b> (Ctrl+Shift+S).</li>
</ol>
<h3>팁</h3>
<ul>
<li>가입/로그인이 필요한 카페는 먼저 <b>네이버 로그인</b>을 한 번 해두세요. 로그인은 크롤러 전용 크롬 프로필에 유지됩니다.</li>
<li>방문자 위젯이 없는 블로그는 <b>위젯없음</b>으로 표시되고, 엑셀에서는 본 시트에서 빠져 <b>제외 목록</b> 시트로 갑니다.</li>
<li>실패한 항목만 다시 하려면 <b>실패 재시도</b>. 표에서 마우스 오른쪽 버튼으로 열 복사, 행 다시 수집 등을 할 수 있습니다.</li>
<li>크롬 버전에 맞는 드라이버는 자동으로 준비됩니다 (Chrome 155 포함).</li>
<li>네이버 화면이 바뀌어 값이 안 나오면 <b>⋯ → 선택자 설정 파일 열기</b>에서 선택자를 고칠 수 있습니다.</li>
</ul>"""


class MainWindow(QMainWindow):
    def __init__(self, settings: Settings):
        super().__init__()
        self.settings = settings
        self.bridge = LogBridge(self)
        self.bridge.message.connect(self.append_log)
        self.engine = Engine(settings, self.bridge.emit)
        self.stop_event = threading.Event()
        self.thread: QThread | None = None
        self.job: Job | None = None
        self.active_page: TaskPage | None = None
        self.busy = False

        self.setWindowTitle(f"{APP_NAME} {__version__}")
        self.setMinimumSize(1040, 640)
        screen = QApplication.primaryScreen()
        avail = screen.availableGeometry() if screen else None
        if avail is not None and avail.width() > 1100:
            self.resize(min(1500, int(avail.width() * 0.94)), min(920, int(avail.height() * 0.92)))
        else:
            self.resize(1320, 820)
        self._build()
        self._build_shortcuts()
        self.show_message("준비됨")

    # ------------------------------------------------------------ 화면 구성
    def _build(self) -> None:
        central = QWidget()
        h = QHBoxLayout(central)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(0)
        h.addWidget(self._build_sidebar())

        content = QWidget()
        content.setObjectName("Content")
        cv = QVBoxLayout(content)
        cv.setContentsMargins(0, 0, 0, 0)
        cv.setSpacing(0)
        cv.addWidget(self._build_header())

        self.stack = QStackedWidget()
        self.pages: list[TaskPage] = []
        for task in TASKS:
            page = TaskPage(task, self.settings)
            page.start_requested.connect(self.run_page)
            page.stop_requested.connect(self.stop)
            page.export_requested.connect(self.export_page)
            page.message.connect(self.show_message)
            self.pages.append(page)
            self.stack.addWidget(page)

        self.log = QPlainTextEdit()
        self.log.setObjectName("Log")
        self.log.setReadOnly(True)
        self.log.setMaximumBlockCount(3000)
        self.log.setVisible(False)

        self.vsplit = QSplitter(Qt.Orientation.Vertical)
        self.vsplit.addWidget(self.stack)
        self.vsplit.addWidget(self.log)
        self.vsplit.setStretchFactor(0, 1)
        self.vsplit.setSizes([650, 160])
        cv.addWidget(self.vsplit, 1)
        h.addWidget(content, 1)
        self.setCentralWidget(central)

        self.log_toggle = QToolButton()
        self.log_toggle.setObjectName("LogToggle")
        self.log_toggle.setText("실행 로그 보기")
        self.log_toggle.setCheckable(True)
        self.log_toggle.toggled.connect(self._toggle_log)
        self.statusBar().addPermanentWidget(self.log_toggle)
        self.statusBar().setSizeGripEnabled(False)

        self._populate_nav()

    def _build_sidebar(self) -> QWidget:
        side = QFrame()
        side.setObjectName("Sidebar")
        side.setFixedWidth(228)
        sv = QVBoxLayout(side)
        sv.setContentsMargins(0, 22, 0, 16)
        sv.setSpacing(4)

        brand = QHBoxLayout()
        brand.setContentsMargins(22, 0, 16, 6)
        brand.setSpacing(10)
        logo = QLabel()
        logo.setPixmap(brand_mark_pixmap(30))
        names = QVBoxLayout()
        names.setSpacing(0)
        title = QLabel(APP_NAME)
        title.setObjectName("Brand")
        sub = QLabel(f"버전 {__version__}")
        sub.setObjectName("BrandSub")
        names.addWidget(title)
        names.addWidget(sub)
        brand.addWidget(logo)
        brand.addLayout(names, 1)
        sv.addLayout(brand)

        self.nav = QListWidget()
        self.nav.setObjectName("Nav")
        self.nav.setIconSize(QSize(18, 18))
        self.nav.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.nav.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.nav.setCursor(Qt.CursorShape.PointingHandCursor)
        sv.addWidget(self.nav, 1)

        account = QFrame()
        account.setObjectName("AccountCard")
        av = QVBoxLayout(account)
        av.setContentsMargins(14, 12, 14, 12)
        av.setSpacing(8)
        row = QHBoxLayout()
        row.setSpacing(10)
        user = QLabel()
        user.setPixmap(icon("user", ICON).pixmap(QSize(20, 20)))
        texts = QVBoxLayout()
        texts.setSpacing(0)
        account_title = QLabel("네이버 계정")
        account_title.setObjectName("AccountTitle")
        self.login_state = QLabel("로그인 안 함")
        self.login_state.setObjectName("AccountState")
        texts.addWidget(account_title)
        texts.addWidget(self.login_state)
        row.addWidget(user)
        row.addLayout(texts, 1)
        av.addLayout(row)
        self.login_btn = QPushButton("로그인")
        self.login_btn.setObjectName("Small")
        self.login_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.login_btn.setToolTip("가입/로그인이 필요한 카페 글을 볼 때 한 번 해두세요")
        self.login_btn.clicked.connect(self.login)
        av.addWidget(self.login_btn)

        wrap = QVBoxLayout()
        wrap.setContentsMargins(14, 0, 14, 0)
        wrap.setSpacing(10)
        wrap.addWidget(account)
        self.browser_info = QLabel("Chrome 실행 전")
        self.browser_info.setObjectName("SideInfo")
        self.browser_info.setWordWrap(True)
        self.browser_info.setContentsMargins(6, 0, 6, 0)
        wrap.addWidget(self.browser_info)
        sv.addLayout(wrap)
        return side

    def _build_header(self) -> QWidget:
        header = QWidget()
        hl = QHBoxLayout(header)
        hl.setContentsMargins(28, 22, 22, 14)
        hl.setSpacing(8)
        texts = QVBoxLayout()
        texts.setSpacing(4)
        self.page_title = QLabel()
        self.page_title.setObjectName("PageTitle")
        self.page_desc = QLabel()
        self.page_desc.setObjectName("PageDesc")
        texts.addWidget(self.page_title)
        texts.addWidget(self.page_desc)
        hl.addLayout(texts, 1)

        export_all = QPushButton(" 전체 엑셀 저장")
        export_all.setObjectName("ExcelSoft")
        export_all.setIcon(icon("excel", ORANGE_TEXT))
        export_all.setIconSize(QSize(16, 16))
        export_all.setToolTip("모든 탭의 결과를 시트별로 한 파일에 저장 (Ctrl+Shift+S)")
        export_all.setCursor(Qt.CursorShape.PointingHandCursor)
        export_all.clicked.connect(self.export_all)
        hl.addWidget(export_all, 0, Qt.AlignmentFlag.AlignVCenter)

        settings_btn = QToolButton()
        settings_btn.setObjectName("IconButton")
        settings_btn.setIcon(icon("gear", BLACK))
        settings_btn.setIconSize(QSize(20, 20))
        settings_btn.setToolTip("설정 (Ctrl+,)")
        settings_btn.clicked.connect(self.open_settings)
        hl.addWidget(settings_btn, 0, Qt.AlignmentFlag.AlignVCenter)

        more = QToolButton()
        more.setObjectName("IconButton")
        more.setIcon(icon("more", BLACK))
        more.setIconSize(QSize(20, 20))
        more.setToolTip("더보기")
        more.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        menu = QMenu(more)
        menu.addAction("현재 탭 엑셀 저장\tCtrl+S", lambda: self.export_page(self.current_page()))
        menu.addAction("전체 탭 엑셀 저장\tCtrl+Shift+S", self.export_all)
        menu.addSeparator()
        menu.addAction("네이버 로그인", self.login)
        menu.addAction("크롬 닫기", self.close_browser)
        menu.addSeparator()
        menu.addAction("선택자 설정 파일 열기", self.open_selectors)
        menu.addAction("데이터 폴더 열기", lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(str(app_data_dir()))))
        menu.addSeparator()
        menu.addAction("사용법\tF1", self.show_help)
        menu.addAction("정보", self.show_about)
        more.setMenu(menu)
        hl.addWidget(more, 0, Qt.AlignmentFlag.AlignVCenter)
        return header

    def _populate_nav(self) -> None:
        index_of = {page.task.id: i for i, page in enumerate(self.pages)}
        for section, task_ids in NAV_SECTIONS:
            head = QListWidgetItem(section)
            head.setFlags(Qt.ItemFlag.NoItemFlags)
            self.nav.addItem(head)
            for task_id in task_ids:
                page_index = index_of[task_id]
                task = self.pages[page_index].task
                item = QListWidgetItem(icon(NAV_ICONS[task_id], ICON, selected="#FFFFFF", disabled=None), task.title)
                item.setData(PAGE_ROLE, page_index)
                item.setToolTip(task.description)
                self.nav.addItem(item)
        self.nav.currentItemChanged.connect(self._nav_changed)
        self.show_page(0)

    def _nav_changed(self, item: QListWidgetItem | None, _prev=None) -> None:
        if item is None or item.data(PAGE_ROLE) is None:
            return
        page = self.pages[int(item.data(PAGE_ROLE))]
        self.stack.setCurrentWidget(page)
        self.page_title.setText(page.task.title)
        self.page_desc.setText(page.task.description)

    def show_page(self, page_index: int) -> None:
        for row in range(self.nav.count()):
            item = self.nav.item(row)
            if item.data(PAGE_ROLE) == page_index:
                self.nav.setCurrentItem(item)
                return

    def _build_shortcuts(self) -> None:
        for keys, slot in (
            ("Ctrl+S", lambda: self.export_page(self.current_page())),
            ("Ctrl+Shift+S", self.export_all),
            ("Ctrl+,", self.open_settings),
            ("F1", self.show_help),
            ("Ctrl+Q", self.close),
        ):
            action = QAction(self)
            action.setShortcut(QKeySequence(keys))
            action.triggered.connect(slot)
            self.addAction(action)

    # ------------------------------------------------------------ 공통
    def current_page(self) -> TaskPage:
        return self.stack.currentWidget()

    @Slot(str)
    def append_log(self, text: str) -> None:
        self.log.appendPlainText(f"{dt.datetime.now():%H:%M:%S}  {text}")
        if text.startswith("[오류]") or "크롬" in text:
            self.statusBar().showMessage(text, 8000)

    @Slot(str)
    def show_message(self, text: str) -> None:
        self.statusBar().showMessage(text, 6000)

    def _toggle_log(self, checked: bool) -> None:
        self.log.setVisible(checked)
        self.log_toggle.setText("실행 로그 숨기기" if checked else "실행 로그 보기")
        if checked:
            self.vsplit.setSizes([max(300, self.vsplit.height() - 180), 180])

    def _set_busy(self, busy: bool, active: TaskPage | None = None) -> None:
        self.busy = busy
        self.active_page = active if busy else None
        for page in self.pages:
            page.set_running(busy and page is active, busy)
        self.login_btn.setEnabled(not busy)

    def _start(self, job: Job) -> None:
        self.job = job
        self.thread = start_job(job, self, self._thread_finished)

    @Slot()
    def _thread_finished(self) -> None:
        if self.sender() is self.thread:  # 이전 작업의 종료 신호가 새 작업 참조를 지우지 않게
            self.thread = None
            self.job = None

    def _ensure_idle(self) -> bool:
        if self.busy:
            QMessageBox.information(self, APP_NAME, "다른 작업이 진행 중입니다. 끝나거나 중지한 뒤에 다시 시도하세요.")
            return False
        return True

    # ------------------------------------------------------------ 수집
    @Slot(object, list)
    def run_page(self, page: TaskPage, ids: list) -> None:
        if not self._ensure_idle():
            return
        items = page.job_items(ids)
        if not items:
            return
        self.stop_event.clear()
        self._set_busy(True, page)
        page.job_started(len(items))
        self.append_log(f"── {page.task.title}: {len(items)}건 수집 시작")
        task, engine, stop = page.task, self.engine, self.stop_event

        def work(job: Job) -> bool:
            return engine.run(task, items, stop, on_start=job.row_started.emit, on_result=job.row_finished.emit)

        job = Job(work)
        job.row_started.connect(page.row_started)
        job.row_finished.connect(page.row_finished)
        job.finished.connect(self._job_done)
        self._start(job)

    @Slot(bool, str)
    def _job_done(self, completed: bool, error: str) -> None:
        page = self.active_page
        self._set_busy(False)
        if page is None:
            return
        page.job_finished(completed, error)
        self._update_browser_info()
        counts = page.model.counts()
        summary = (
            f"{page.task.title} {'완료' if completed else '중지'} · 완료 {counts.get(STATUS_OK, 0)} · "
            f"실패 {counts.get(STATUS_FAIL, 0)}"
            + (f" · 위젯없음 {counts[STATUS_NO_WIDGET]}" if counts.get(STATUS_NO_WIDGET) else "")
        )
        self.append_log(f"── {summary}")
        self.show_message(summary)
        QApplication.alert(self)
        if error:
            QMessageBox.warning(self, "수집 오류", error)

    @Slot()
    def stop(self) -> None:
        if self.busy:
            self.stop_event.set()
            self.show_message("중지 요청됨 · 현재 페이지가 끝나면 멈춥니다")

    # ------------------------------------------------------------ 로그인
    def login(self) -> None:
        if not self._ensure_idle():
            return
        self._set_busy(True)
        self._set_login_state("크롬 여는 중…", False)
        engine = self.engine

        def work(job: Job) -> bool:
            engine.open_login()
            return True

        job = Job(work)
        job.finished.connect(self._login_opened)
        self._start(job)

    @Slot(bool, str)
    def _login_opened(self, ok: bool, error: str) -> None:
        self._set_busy(False)
        self._update_browser_info()
        if not ok:
            self._set_login_state("로그인 창을 열지 못함", False)
            QMessageBox.warning(self, "네이버 로그인", error or "크롬을 열지 못했습니다.")
            return
        QMessageBox.information(
            self,
            "네이버 로그인",
            "열린 크롬 창에서 네이버에 로그인한 뒤 [확인]을 누르세요.\n\n"
            "로그인 정보는 이 프로그램 전용 크롬 프로필에 저장되어 다음 실행 때도 유지됩니다.\n"
            "(평소 쓰는 크롬과는 분리되어 있습니다)",
        )
        self._set_busy(True)
        browser = self.engine.browser
        job = Job(lambda job: browser.is_logged_in())
        job.finished.connect(self._login_checked)
        self._start(job)

    @Slot(bool, str)
    def _login_checked(self, logged_in: bool, error: str) -> None:
        self._set_busy(False)
        self._set_login_state("로그인됨" if logged_in else "로그인 안 됨", logged_in)
        self.append_log("네이버 로그인 " + ("확인됨" if logged_in else "안 됨"))

    def _set_login_state(self, text: str, ok: bool) -> None:
        self.login_state.setText(text)
        self.login_state.setProperty("ok", ok)
        self.login_state.style().unpolish(self.login_state)
        self.login_state.style().polish(self.login_state)
        self.login_btn.setText("다시 로그인" if ok else "로그인")

    def close_browser(self) -> None:
        if not self._ensure_idle():
            return
        self.engine.shutdown()
        self.browser_info.setText("Chrome 닫힘")
        self.append_log("크롬을 닫았습니다")

    def _update_browser_info(self) -> None:
        if self.engine.browser.version_text:
            self.browser_info.setText(self.engine.browser.version_text)

    # ------------------------------------------------------------ 엑셀
    @Slot(object)
    def export_page(self, page: TaskPage) -> None:
        if not page.model.rows:
            QMessageBox.information(self, "엑셀 저장", "저장할 결과가 없습니다.")
            return
        self._export([page.model.sheet_data()], page.task.title)

    def export_all(self) -> None:
        sheets = [p.model.sheet_data() for p in self.pages if p.model.rows]
        if not sheets:
            QMessageBox.information(self, "엑셀 저장", "저장할 결과가 없습니다.")
            return
        self._export(sheets, "전체")

    def _export(self, sheets, label: str) -> None:
        folder = self.settings.export_dir or QStandardPaths.writableLocation(QStandardPaths.StandardLocation.DocumentsLocation)
        suggested = str(Path(folder) / default_filename(label))
        path, _ = QFileDialog.getSaveFileName(self, "엑셀로 저장", suggested, "Excel 통합 문서 (*.xlsx)")
        if not path:
            return
        try:
            saved = export_xlsx(path, sheets)
        except PermissionError:
            QMessageBox.warning(self, "엑셀 저장", "파일이 엑셀에서 열려 있습니다. 닫고 다시 저장하세요.")
            return
        except OSError as exc:
            QMessageBox.warning(self, "엑셀 저장", f"저장하지 못했습니다: {exc}")
            return
        self.settings.export_dir = str(saved.parent)
        self.settings.save()
        self.append_log(f"엑셀 저장: {saved}")
        box = QMessageBox(self)
        box.setWindowTitle("엑셀 저장 완료")
        box.setText(f"{saved.name}\n저장했습니다.")
        open_file = box.addButton("파일 열기", QMessageBox.ButtonRole.AcceptRole)
        open_dir = box.addButton("폴더 열기", QMessageBox.ButtonRole.ActionRole)
        box.addButton("닫기", QMessageBox.ButtonRole.RejectRole)
        box.exec()
        if box.clickedButton() is open_file:
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(saved)))
        elif box.clickedButton() is open_dir:
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(saved.parent)))

    # ------------------------------------------------------------ 설정 · 도움말
    def open_settings(self) -> None:
        dlg = SettingsDialog(self.settings, self)
        if dlg.exec():
            restart = dlg.apply()
            self.settings.save()
            if restart and not self.busy:
                self.engine.shutdown()
            self.show_message("설정을 저장했습니다")

    def open_selectors(self) -> None:
        path = write_default_selectors()
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))
        self.show_message(f"선택자 파일: {path} (저장 후 다음 수집부터 적용)")

    def show_help(self) -> None:
        QMessageBox.information(self, "사용법", HELP_TEXT)

    def show_about(self) -> None:
        QMessageBox.about(
            self,
            "정보",
            f"<b>{APP_NAME}</b> {__version__}<br><br>"
            "네이버 카페 · 블로그 · 지식iN 지표 수집 도구<br>"
            "크롬 버전에 맞는 드라이버를 자동으로 준비합니다 (Selenium Manager).<br><br>"
            f"데이터 폴더: {app_data_dir()}",
        )

    # ------------------------------------------------------------ 종료
    def closeEvent(self, event) -> None:  # noqa: N802
        if self.busy:
            answer = QMessageBox.question(self, APP_NAME, "수집 중입니다. 중지하고 종료할까요?")
            if answer != QMessageBox.StandardButton.Yes:
                event.ignore()
                return
        self.stop_event.set()
        self.settings.save()
        self.engine.shutdown()
        if self.thread is not None:
            self.thread.wait(15000)
        event.accept()
