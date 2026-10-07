"""백그라운드 실행 (화면이 멈추지 않도록 크롬 작업은 별도 스레드에서)."""

from __future__ import annotations

from typing import Callable

from PySide6.QtCore import QObject, QThread, Signal, Slot

from naver_crawler.browser import friendly_error


class LogBridge(QObject):
    """다른 스레드에서 남긴 로그를 화면 스레드로 넘긴다."""

    message = Signal(str)

    def emit(self, text: str) -> None:
        self.message.emit(text)


class Job(QObject):
    row_started = Signal(object)
    row_finished = Signal(object, object)
    finished = Signal(bool, str)   # (끝까지 완료했는지, 오류 메시지)

    def __init__(self, fn: Callable[["Job"], bool]):
        super().__init__()
        self.fn = fn

    @Slot()
    def run(self) -> None:
        try:
            completed = bool(self.fn(self))
            self.finished.emit(completed, "")
        except Exception as exc:  # noqa: BLE001
            self.finished.emit(False, friendly_error(exc))


def start_job(job: Job, parent: QObject, on_thread_finished: Callable[[], None] | None = None) -> QThread:
    thread = QThread(parent)
    job.moveToThread(thread)
    thread.started.connect(job.run)
    job.finished.connect(thread.quit)
    job.finished.connect(job.deleteLater)
    if on_thread_finished is not None:  # 시작 전에 연결해야 아주 짧은 작업도 놓치지 않는다
        thread.finished.connect(on_thread_finished)
    thread.finished.connect(thread.deleteLater)
    thread.start()
    return thread
