"""공용 위젯: 카드, 상태 알약, 통계 칩, 빈 화면 안내."""

from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, QSize, Qt, Signal
from PySide6.QtGui import QColor, QFont, QFontMetrics, QPainter
from PySide6.QtWidgets import (
    QApplication,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QStyle,
    QStyledItemDelegate,
    QStyleOptionViewItem,
    QVBoxLayout,
    QWidget,
)

from naver_crawler.ui.theme import BLACK, STATUS_COLORS, icon_pixmap


def card(parent=None, margins=(20, 18, 20, 18), spacing: int = 12) -> tuple[QFrame, QVBoxLayout]:
    frame = QFrame(parent)
    frame.setObjectName("Card")
    layout = QVBoxLayout(frame)
    layout.setContentsMargins(*margins)
    layout.setSpacing(spacing)
    return frame, layout


class UrlEdit(QPlainTextEdit):
    """URL 입력칸. txt · csv · xlsx 파일을 끌어다 놓으면 files_dropped 로 알린다."""

    files_dropped = Signal(list)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAcceptDrops(True)

    @staticmethod
    def _local_files(event) -> list[str]:
        mime = event.mimeData()
        if not mime.hasUrls():
            return []
        return [u.toLocalFile() for u in mime.urls() if u.isLocalFile()]

    def dragEnterEvent(self, event) -> None:  # noqa: N802
        if self._local_files(event):
            event.acceptProposedAction()
        else:
            super().dragEnterEvent(event)

    def dragMoveEvent(self, event) -> None:  # noqa: N802
        if self._local_files(event):
            event.acceptProposedAction()
        else:
            super().dragMoveEvent(event)

    def dropEvent(self, event) -> None:  # noqa: N802
        files = self._local_files(event)
        if files:
            event.acceptProposedAction()
            self.files_dropped.emit(files)
        else:
            super().dropEvent(event)


class StatusDelegate(QStyledItemDelegate):
    """상태 열을 색깔 알약 모양으로 그린다."""

    def paint(self, painter: QPainter, option, index) -> None:
        opt = QStyleOptionViewItem(option)
        self.initStyleOption(opt, index)
        status = opt.text
        opt.text = ""
        style = opt.widget.style() if opt.widget else QApplication.style()
        style.drawControl(QStyle.ControlElement.CE_ItemViewItem, opt, painter, opt.widget)
        if not status:
            return
        fg, bg = STATUS_COLORS.get(status, ("#48484A", "#E5E5EA"))
        font = QFont(opt.font)
        font.setPointSizeF(max(8.0, opt.font.pointSizeF() - 1))
        font.setBold(True)
        fm = QFontMetrics(font)
        width = fm.horizontalAdvance(status) + 28
        height = 22
        rect = QRectF(
            opt.rect.center().x() - width / 2 + 0.5,
            opt.rect.center().y() - height / 2 + 0.5,
            width,
            height,
        )
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(bg or "#E5E5EA"))
        painter.drawRoundedRect(rect, height / 2, height / 2)
        painter.setBrush(QColor(fg))
        painter.drawEllipse(QPointF(rect.left() + 11, rect.center().y()), 3, 3)
        painter.setPen(QColor(fg))
        painter.setFont(font)
        painter.drawText(rect.adjusted(18, 0, -8, 0), Qt.AlignmentFlag.AlignCenter, status)
        painter.restore()

    def sizeHint(self, option, index) -> QSize:  # noqa: N802
        hint = super().sizeHint(option, index)
        return QSize(max(hint.width(), 96), max(hint.height(), 36))


class ElideMiddleDelegate(QStyledItemDelegate):
    """긴 URL 은 가운데를 줄여서 앞뒤가 모두 보이게."""

    def initStyleOption(self, option, index) -> None:  # noqa: N802
        super().initStyleOption(option, index)
        option.textElideMode = Qt.TextElideMode.ElideMiddle


class StatChips(QWidget):
    """'총 3 · 완료 2 · 위젯없음 1' 을 색깔 칩으로 보여준다."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._layout = QHBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setSpacing(6)
        self._parts: list[str] = []

    def set_counts(self, total: int, counts: list[tuple[str, int]]) -> None:
        while self._layout.count():
            item = self._layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self._parts = [f"총 {total}"]
        if not total:
            return
        self._add(f"총 {total}", "#FFFFFF", BLACK)
        for status, n in counts:
            if n:
                fg, bg = STATUS_COLORS.get(status, ("#48484A", "#E5E5EA"))
                self._add(f"{status} {n}", fg, bg)
                self._parts.append(f"{status} {n}")

    def _add(self, text: str, fg: str, bg: str) -> None:
        label = QLabel(text)
        label.setStyleSheet(
            f"color: {fg}; background: {bg}; border-radius: 10px; padding: 2px 9px; font-size: 12px; font-weight: 700;"
        )
        self._layout.addWidget(label)

    def text(self) -> str:
        return " · ".join(self._parts)


class EmptyState(QWidget):
    def __init__(self, title: str, hint: str, parent=None):
        super().__init__(parent)
        lay = QVBoxLayout(self)
        lay.addStretch(1)
        art = QLabel()
        art.setPixmap(icon_pixmap("empty", "#C7C7CC", 44))
        art.setAlignment(Qt.AlignmentFlag.AlignCenter)
        t = QLabel(title)
        t.setObjectName("EmptyTitle")
        t.setAlignment(Qt.AlignmentFlag.AlignCenter)
        h = QLabel(hint)
        h.setObjectName("EmptyHint")
        h.setAlignment(Qt.AlignmentFlag.AlignCenter)
        h.setWordWrap(True)
        lay.addWidget(art)
        lay.addSpacing(6)
        lay.addWidget(t)
        lay.addWidget(h)
        lay.addStretch(1)
