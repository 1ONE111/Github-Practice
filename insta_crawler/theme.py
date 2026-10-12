"""색 · 스타일시트 · 아이콘 · 상태 알약. 네이버 크롤러와 같은 톤(밝은 회색 배경 + 흰 카드, 블랙/주황)에
인스타 느낌은 앱 아이콘 · 로고의 그라데이션 카메라로만 낸다."""

from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, QSize, Qt
from PySide6.QtGui import QColor, QFont, QFontMetrics, QIcon, QLinearGradient, QPainter, QPainterPath, QPalette, QPen, QPixmap
from PySide6.QtWidgets import QApplication, QHBoxLayout, QLabel, QStyle, QStyledItemDelegate, QStyleOptionViewItem, QWidget

from insta_crawler.collector import (
    STATUS_CANCELLED,
    STATUS_FAIL,
    STATUS_OK,
    STATUS_PARTIAL,
    STATUS_PRIVATE,
    STATUS_RUNNING,
    STATUS_WAIT,
)

BLACK = "#1C1C1E"
BLACK_HOVER = "#3A3A3C"
ORANGE = "#F26B1D"
ORANGE_HOVER = "#DD5A0E"
ORANGE_TEXT = "#C2410C"
ORANGE_SOFT = "#FFF0E5"
TEXT = "#1C1C1E"
MUTED = "#636366"
SUBTLE = "#AEAEB2"
BG = "#F2F2F7"
FILL = "#E9E9EB"
LINE = "#E5E5EA"
ICON = "#3A3A3C"
INSTA_GRADIENT = ("#FEDA75", "#FA7E1E", "#D62976", "#962FBF")  # 아이콘 · 로고에만

FONT_FAMILIES = ["Malgun Gothic", "맑은 고딕", "Apple SD Gothic Neo", "Noto Sans CJK KR", "Noto Sans KR", "WenQuanYi Zen Hei"]

STATUS_COLORS = {
    STATUS_OK: ("#1E7B34", "#E2F5E7"),
    STATUS_PARTIAL: ("#8A5A00", "#FFF2C7"),
    STATUS_FAIL: ("#D70015", "#FFE4E6"),
    STATUS_PRIVATE: ("#3634A3", "#E8E7FB"),
    STATUS_RUNNING: (ORANGE_TEXT, ORANGE_SOFT),
    STATUS_CANCELLED: ("#48484A", "#E5E5EA"),
    STATUS_WAIT: ("#8E8E93", BG),
}

STYLESHEET = f"""
* {{ outline: 0; }}
QMainWindow, QWidget#Root {{ background: {BG}; }}
QWidget {{ color: {TEXT}; }}
QToolTip {{ background: {BLACK}; color: white; border: none; padding: 6px 8px; }}
QLabel#PageTitle {{ color: {BLACK}; font-size: 24px; font-weight: 700; }}
QLabel#PageDesc {{ color: {MUTED}; font-size: 13px; }}
QLabel#LoginState {{ color: {MUTED}; font-size: 12px; }}
QLabel#LoginState[ok="true"] {{ color: #1E7B34; font-weight: 700; }}

QFrame#Card {{ background: white; border: 1px solid {LINE}; border-radius: 14px; }}
QLabel#CardTitle {{ color: {BLACK}; font-size: 15px; font-weight: 700; }}
QLabel#CountChip {{ color: {ORANGE_TEXT}; background: {ORANGE_SOFT}; border-radius: 9px; padding: 1px 8px; font-size: 12px; font-weight: 700; }}
QLabel#StatusText, QLabel#OptionLabel {{ color: {MUTED}; font-size: 12px; }}

QPushButton {{ background: {FILL}; border: none; border-radius: 8px; padding: 7px 14px; color: {BLACK}; font-size: 13px; }}
QPushButton:hover {{ background: #DEDEE2; }}
QPushButton:pressed {{ background: #D1D1D6; }}
QPushButton:disabled {{ color: {SUBTLE}; background: {BG}; }}
QPushButton#Primary {{ background: {BLACK}; color: white; font-weight: 700; font-size: 15px; padding: 12px 18px; border-radius: 11px; }}
QPushButton#Primary:hover {{ background: {BLACK_HOVER}; }}
QPushButton#Primary:pressed {{ background: #000000; }}
QPushButton#Primary:disabled {{ background: #C7C7CC; color: white; }}
QPushButton#Stop {{ background: #D70015; color: white; font-weight: 700; font-size: 15px; padding: 12px 18px; border-radius: 11px; }}
QPushButton#Stop:hover {{ background: #B80012; }}
QPushButton#Excel {{ background: {ORANGE}; color: white; font-weight: 700; }}
QPushButton#Excel:hover {{ background: {ORANGE_HOVER}; }}
QPushButton#Excel:pressed {{ background: #C24F0B; }}
QPushButton#Excel:disabled {{ background: #F8C3A3; color: white; }}
QPushButton#ExcelSoft {{ background: {ORANGE_SOFT}; color: {ORANGE_TEXT}; font-weight: 700; }}
QPushButton#ExcelSoft:hover {{ background: #FFE2CC; }}
QPushButton#Ghost {{ background: transparent; color: {BLACK}; padding: 7px 10px; }}
QPushButton#Ghost:hover {{ background: {BG}; }}
QPushButton#Ghost:checked {{ background: {FILL}; }}
QPushButton#Ghost:disabled {{ color: {SUBTLE}; background: transparent; }}
QPushButton#Link {{ background: transparent; color: {ORANGE_TEXT}; padding: 3px 6px; font-size: 12px; font-weight: 700; }}
QPushButton#Link:hover {{ color: {ORANGE_HOVER}; background: transparent; }}
QPushButton#Small {{ background: {FILL}; padding: 5px 11px; font-size: 12px; border-radius: 8px; font-weight: 700; }}
QPushButton#Small:hover {{ background: #DEDEE2; }}
QPushButton#Seg {{ background: {FILL}; color: {MUTED}; font-weight: 700; font-size: 13px; padding: 7px 18px; border-radius: 0; }}
QPushButton#Seg[side="left"] {{ border-top-left-radius: 9px; border-bottom-left-radius: 9px; }}
QPushButton#Seg[side="right"] {{ border-top-right-radius: 9px; border-bottom-right-radius: 9px; }}
QPushButton#Seg:hover {{ color: {BLACK}; }}
QPushButton#Seg:checked {{ background: {BLACK}; color: white; }}
QPushButton#Seg:disabled {{ color: {SUBTLE}; }}
QPushButton#Seg:checked:disabled {{ background: #48484A; color: white; }}

QPlainTextEdit {{ background: {BG}; border: 1px solid transparent; border-radius: 10px; padding: 8px;
    selection-background-color: {ORANGE}; selection-color: white; color: {BLACK}; font-size: 13px; }}
QPlainTextEdit:focus {{ border: 1px solid {ORANGE}; background: white; }}
QPlainTextEdit#Log {{ background: white; color: #3A3A3C; font-family: Consolas, "D2Coding", monospace; font-size: 12px;
    border: none; border-top: 1px solid {LINE}; border-radius: 0; padding: 8px 16px; }}
QComboBox {{ background: {BG}; border: 1px solid transparent; border-radius: 8px; padding: 5px 10px; min-width: 52px; color: {BLACK}; }}
QComboBox:hover {{ border: 1px solid #D1D1D6; }}
QComboBox:focus {{ border: 1px solid {ORANGE}; }}
QComboBox QAbstractItemView {{ background: white; border: 1px solid #D1D1D6; selection-background-color: {ORANGE_SOFT};
    selection-color: {BLACK}; }}

QTableView {{ background: white; border: none; selection-background-color: {ORANGE_SOFT}; selection-color: {BLACK}; font-size: 13px; }}
QTableView::item {{ border-bottom: 1px solid #EFEFF4; padding: 0 8px; }}
QTableView::item:hover {{ background: #F7F7FA; }}
QHeaderView {{ background: white; }}
QHeaderView::section {{ background: white; border: none; border-bottom: 1px solid #D1D1D6; padding: 9px 8px;
    color: {MUTED}; font-size: 12px; font-weight: 700; }}
QHeaderView::section:hover {{ color: {BLACK}; }}
QTableCornerButton::section {{ background: white; border: none; }}
QScrollBar:vertical {{ background: transparent; width: 10px; margin: 2px; }}
QScrollBar::handle:vertical {{ background: #C7C7CC; border-radius: 3px; min-height: 30px; }}
QScrollBar:horizontal {{ background: transparent; height: 10px; margin: 2px; }}
QScrollBar::handle:horizontal {{ background: #C7C7CC; border-radius: 3px; min-width: 30px; }}
QScrollBar::add-line, QScrollBar::sub-line {{ width: 0; height: 0; }}
QScrollBar::add-page, QScrollBar::sub-page {{ background: transparent; }}

QProgressBar {{ border: none; background: {LINE}; border-radius: 2px; max-height: 4px; min-height: 4px; color: transparent; }}
QProgressBar::chunk {{ background: {ORANGE}; border-radius: 2px; }}
QSplitter::handle {{ background: transparent; }}
QSplitter::handle:horizontal {{ width: 16px; }}
QMenu {{ background: white; border: 1px solid #D1D1D6; border-radius: 10px; padding: 6px; }}
QMenu::item {{ padding: 7px 26px 7px 14px; border-radius: 6px; color: {BLACK}; }}
QMenu::item:selected {{ background: {BLACK}; color: white; }}
QMenu::item:disabled {{ color: {SUBTLE}; }}
QStatusBar {{ background: white; border-top: 1px solid {LINE}; color: {MUTED}; font-size: 12px; }}
QStatusBar::item {{ border: none; }}
QDialog, QMessageBox {{ background: white; }}
"""


def setup_app(app) -> None:
    font = QFont()
    font.setFamilies(FONT_FAMILIES)
    font.setPointSize(10)
    app.setFont(font)
    pal = app.palette()
    pal.setColor(QPalette.ColorRole.Window, QColor(BG))
    pal.setColor(QPalette.ColorRole.WindowText, QColor(TEXT))
    pal.setColor(QPalette.ColorRole.Base, QColor("white"))
    pal.setColor(QPalette.ColorRole.Text, QColor(TEXT))
    pal.setColor(QPalette.ColorRole.Button, QColor(FILL))
    pal.setColor(QPalette.ColorRole.ButtonText, QColor(BLACK))
    pal.setColor(QPalette.ColorRole.Highlight, QColor(ORANGE))
    pal.setColor(QPalette.ColorRole.HighlightedText, QColor("white"))
    app.setPalette(pal)
    app.setStyleSheet(STYLESHEET)
    app.setWindowIcon(app_icon())


# ---------------------------------------------------------------- 라인 아이콘 (24 단위 격자, 네이버 크롤러와 같은 그림)


def _draw(name: str, p: QPainter, color: QColor) -> None:
    p.setPen(QPen(color, 1.8, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
    p.setBrush(Qt.BrushStyle.NoBrush)
    if name == "excel":
        p.drawRoundedRect(QRectF(4, 4, 16, 16), 2.5, 2.5)
        p.drawLine(QPointF(4, 10), QPointF(20, 10))
        p.drawLine(QPointF(4, 15), QPointF(20, 15))
        p.drawLine(QPointF(10, 10), QPointF(10, 20))
    elif name == "copy":
        p.drawRoundedRect(QRectF(8, 8, 12, 12), 2.5, 2.5)
        p.drawPolyline([QPointF(16, 5), QPointF(6.5, 5), QPointF(5, 6.5), QPointF(5, 16)])
    elif name == "retry":
        p.drawArc(QRectF(5, 5, 14, 14), 60 * 16, 290 * 16)
        p.drawPolyline([QPointF(14, 3.8), QPointF(17.6, 5.4), QPointF(16, 9)])
    elif name == "play":
        tri = QPainterPath(QPointF(8, 5.5))
        tri.lineTo(18.5, 12)
        tri.lineTo(8, 18.5)
        tri.closeSubpath()
        p.setBrush(color)
        p.drawPath(tri)
    elif name == "stop":
        p.setBrush(color)
        p.drawRoundedRect(QRectF(7, 7, 10, 10), 2, 2)
    elif name == "log":
        p.drawRoundedRect(QRectF(3.5, 5, 17, 14), 2.5, 2.5)
        p.drawPolyline([QPointF(7.5, 10), QPointF(10, 12), QPointF(7.5, 14)])
        p.drawLine(QPointF(12, 14.5), QPointF(16, 14.5))
    elif name == "user":
        p.drawEllipse(QPointF(12, 8.5), 4, 4)
        p.drawArc(QRectF(4.5, 14, 15, 13), 20 * 16, 140 * 16)


def icon(name: str, color: str = ICON, disabled: str | None = SUBTLE, size: int = 20) -> QIcon:
    result = QIcon()
    for mode, c in ((QIcon.Mode.Normal, color), (QIcon.Mode.Active, color), (QIcon.Mode.Disabled, disabled)):
        if c is None:
            continue
        pix = QPixmap(size * 2, size * 2)
        pix.fill(Qt.GlobalColor.transparent)
        p = QPainter(pix)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.scale(size * 2 / 24, size * 2 / 24)
        _draw(name, p, QColor(c))
        p.end()
        pix.setDevicePixelRatio(2.0)
        result.addPixmap(pix, mode)
    return result


# ---------------------------------------------------------------- 인스타 카메라 마크 (그라데이션)


def _insta_gradient(rect: QRectF) -> QLinearGradient:
    grad = QLinearGradient(rect.bottomLeft(), rect.topRight())
    for i, c in enumerate(INSTA_GRADIENT):
        grad.setColorAt(i / (len(INSTA_GRADIENT) - 1), QColor(c))
    return grad


def _draw_camera(p: QPainter, rect: QRectF) -> None:
    s = rect.width() / 24
    pen = QPen(_insta_gradient(rect), 2.3 * s, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin)
    p.setPen(pen)
    p.setBrush(Qt.BrushStyle.NoBrush)
    x, y = rect.left(), rect.top()
    p.drawRoundedRect(QRectF(x + 3 * s, y + 3 * s, 18 * s, 18 * s), 5.2 * s, 5.2 * s)
    p.drawEllipse(QPointF(x + 12 * s, y + 12 * s), 4.2 * s, 4.2 * s)
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(_insta_gradient(rect))
    p.drawEllipse(QPointF(x + 17.1 * s, y + 6.9 * s), 1.25 * s, 1.25 * s)


def brand_mark_pixmap(size: int = 32, ratio: float = 2.0) -> QPixmap:
    pix = QPixmap(int(size * ratio), int(size * ratio))
    pix.fill(Qt.GlobalColor.transparent)
    p = QPainter(pix)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    _draw_camera(p, QRectF(0, 0, size * ratio, size * ratio))
    p.end()
    pix.setDevicePixelRatio(ratio)
    return pix


def app_icon_pixmap(size: int = 256) -> QPixmap:
    """작업 표시줄/exe 아이콘: 네이버 크롤러와 같은 검정 라운드 사각형 + 인스타 그라데이션 카메라."""
    pix = QPixmap(size, size)
    pix.fill(Qt.GlobalColor.transparent)
    p = QPainter(pix)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    bg = QPainterPath()
    bg.addRoundedRect(QRectF(0, 0, size, size), size * 0.23, size * 0.23)
    p.fillPath(bg, QColor(BLACK))
    pad = size * 0.14
    _draw_camera(p, QRectF(pad, pad, size - 2 * pad, size - 2 * pad))
    p.end()
    return pix


def app_icon() -> QIcon:
    result = QIcon()
    for size in (16, 24, 32, 48, 64, 128, 256):
        result.addPixmap(app_icon_pixmap(size))
    return result


# ---------------------------------------------------------------- 상태 알약 · 통계 칩


PILL_ROLE = Qt.ItemDataRole.UserRole + 2  # 모델이 True 를 주는 칸만 상태 알약으로 그린다


class StatusDelegate(QStyledItemDelegate):
    def paint(self, painter: QPainter, option, index) -> None:
        if not index.data(PILL_ROLE):
            super().paint(painter, option, index)
            return
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
        width = QFontMetrics(font).horizontalAdvance(status) + 28
        height = 22
        rect = QRectF(opt.rect.center().x() - width / 2 + 0.5, opt.rect.center().y() - height / 2 + 0.5, width, height)
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(bg))
        painter.drawRoundedRect(rect, height / 2, height / 2)
        painter.setBrush(QColor(fg))
        painter.drawEllipse(QPointF(rect.left() + 11, rect.center().y()), 3, 3)
        painter.setPen(QColor(fg))
        painter.setFont(font)
        painter.drawText(rect.adjusted(18, 0, -8, 0), Qt.AlignmentFlag.AlignCenter, status)
        painter.restore()

    def sizeHint(self, option, index) -> QSize:  # noqa: N802
        hint = super().sizeHint(option, index)
        if not index.data(PILL_ROLE):
            return hint
        return QSize(max(hint.width(), 96), max(hint.height(), 36))


class StatChips(QWidget):
    """'총 3 · 완료 2 · 비공개 1' 을 색깔 칩으로."""

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
        self._parts = []
        if not total:
            return
        self._add(f"총 {total}", "#FFFFFF", BLACK)
        self._parts.append(f"총 {total}")
        for status, n in counts:
            if n:
                fg, bg = STATUS_COLORS.get(status, ("#48484A", "#E5E5EA"))
                self._add(f"{status} {n}", fg, bg)
                self._parts.append(f"{status} {n}")

    def _add(self, text: str, fg: str, bg: str) -> None:
        label = QLabel(text)
        label.setStyleSheet(f"color: {fg}; background: {bg}; border-radius: 10px; padding: 2px 9px; font-size: 12px; font-weight: 700;")
        self._layout.addWidget(label)

    def text(self) -> str:
        return " · ".join(self._parts)
