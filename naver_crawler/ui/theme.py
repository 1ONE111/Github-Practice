"""색상, 스타일시트, 직접 그리는 라인 아이콘.

SwiftUI(iOS 17 이전) 느낌의 밝은 그룹 배경 + 흰 카드, 포인트 색은 블랙/주황.
"""

from __future__ import annotations

import math

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QIcon, QPainter, QPainterPath, QPalette, QPen, QPixmap

from naver_crawler.crawlers import (
    STATUS_CANCELLED,
    STATUS_FAIL,
    STATUS_NO_WIDGET,
    STATUS_OK,
    STATUS_PARTIAL,
    STATUS_RUNNING,
    STATUS_WAIT,
)

BLACK = "#1C1C1E"          # 기본 글자 · 주요 버튼
BLACK_HOVER = "#3A3A3C"
ORANGE = "#F26B1D"         # 브랜드 주황 (채움)
ORANGE_HOVER = "#DD5A0E"
ORANGE_TEXT = "#C2410C"    # 흰 바탕 위 주황 글자 (대비 확보)
ORANGE_SOFT = "#FFF0E5"
TEXT = "#1C1C1E"
MUTED = "#636366"          # 보조 글자 (iOS secondaryLabel 보다 진하게)
SUBTLE = "#AEAEB2"
BG = "#F2F2F7"             # iOS grouped background
FILL = "#E9E9EB"           # 회색 버튼/입력 채움
LINE = "#E5E5EA"
ICON = "#3A3A3C"

FONT_FAMILIES = ["Malgun Gothic", "맑은 고딕", "Apple SD Gothic Neo", "Noto Sans CJK KR", "Noto Sans KR", "WenQuanYi Zen Hei"]

# 상태별 (글자색, 배경색) - 애플 고대비 시스템 색
STATUS_COLORS = {
    STATUS_OK: ("#1E7B34", "#E2F5E7"),
    STATUS_PARTIAL: ("#8A5A00", "#FFF2C7"),
    STATUS_FAIL: ("#D70015", "#FFE4E6"),
    STATUS_NO_WIDGET: ("#3634A3", "#E8E7FB"),
    STATUS_RUNNING: (ORANGE_TEXT, ORANGE_SOFT),
    STATUS_CANCELLED: ("#48484A", "#E5E5EA"),
    STATUS_WAIT: ("#8E8E93", "#F2F2F7"),
}

STYLESHEET = f"""
* {{ outline: 0; }}
QMainWindow, QWidget#Content {{ background: {BG}; }}
QWidget {{ color: {TEXT}; }}
QToolTip {{ background: {BLACK}; color: white; border: none; padding: 6px 8px; }}

/* 사이드바 */
QFrame#Sidebar {{ background: white; border-right: 1px solid {LINE}; }}
QLabel#Brand {{ color: {BLACK}; font-size: 16px; font-weight: 700; }}
QLabel#BrandSub {{ color: {MUTED}; font-size: 11px; }}
QListWidget#Nav {{ background: transparent; border: none; font-size: 14px; }}
QListWidget#Nav::item {{ color: {TEXT}; padding: 9px 10px; margin: 1px 12px; border-radius: 9px; }}
QListWidget#Nav::item:hover {{ background: {BG}; }}
QListWidget#Nav::item:selected {{ background: {BLACK}; color: white; font-weight: 700; }}
QListWidget#Nav::item:disabled {{ color: {MUTED}; font-size: 11px; font-weight: 700; padding: 16px 10px 4px 10px; background: transparent; }}
QFrame#AccountCard {{ background: {BG}; border-radius: 12px; }}
QLabel#AccountTitle {{ color: {BLACK}; font-weight: 700; font-size: 13px; }}
QLabel#AccountState {{ color: {MUTED}; font-size: 12px; }}
QLabel#AccountState[ok="true"] {{ color: #1E7B34; font-weight: 700; }}
QLabel#SideInfo {{ color: {MUTED}; font-size: 11px; }}

/* 헤더 */
QLabel#PageTitle {{ color: {BLACK}; font-size: 24px; font-weight: 700; }}
QLabel#PageDesc {{ color: {MUTED}; font-size: 13px; }}

/* 카드 */
QFrame#Card {{ background: white; border: 1px solid {LINE}; border-radius: 14px; }}
QLabel#CardTitle {{ color: {BLACK}; font-size: 15px; font-weight: 700; }}
QLabel#CountChip {{ color: {ORANGE_TEXT}; background: {ORANGE_SOFT}; border-radius: 9px; padding: 1px 8px; font-size: 12px; font-weight: 700; }}
QLabel#Hint, QLabel#StatusText {{ color: {MUTED}; font-size: 12px; }}
QLabel#EmptyTitle {{ color: {BLACK}; font-size: 15px; font-weight: 700; }}
QLabel#EmptyHint {{ color: {MUTED}; font-size: 13px; }}
QLabel#OptionLabel {{ color: {MUTED}; font-size: 12px; }}

/* 버튼 */
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
QPushButton#Ghost:disabled {{ color: {SUBTLE}; background: transparent; }}
QPushButton#Link {{ background: transparent; color: {ORANGE_TEXT}; padding: 3px 6px; font-size: 12px; font-weight: 700; }}
QPushButton#Link:hover {{ color: {ORANGE_HOVER}; background: transparent; }}
QPushButton#Small {{ background: {FILL}; padding: 5px 11px; font-size: 12px; border-radius: 8px; font-weight: 700; }}
QPushButton#Small:hover {{ background: #DEDEE2; }}
QFrame#AccountCard QPushButton#Small {{ background: white; }}
QFrame#AccountCard QPushButton#Small:hover {{ background: #FAFAFA; }}
QToolButton#IconButton {{ border: none; background: transparent; border-radius: 8px; padding: 6px; }}
QToolButton#IconButton:hover {{ background: {FILL}; }}
QToolButton#IconButton::menu-indicator {{ image: none; }}
QToolButton#LogToggle {{ border: none; background: transparent; color: {MUTED}; padding: 2px 8px; font-size: 12px; }}
QToolButton#LogToggle:checked, QToolButton#LogToggle:hover {{ color: {BLACK}; }}

/* 입력 */
QPlainTextEdit, QLineEdit, QSpinBox, QDoubleSpinBox {{
    background: {BG}; border: 1px solid transparent; border-radius: 10px; padding: 8px;
    selection-background-color: {ORANGE}; selection-color: white; color: {BLACK};
}}
QPlainTextEdit:focus, QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus {{ border: 1px solid {ORANGE}; background: white; }}
QSpinBox, QDoubleSpinBox {{ padding: 4px 6px; border-radius: 8px; }}
QPlainTextEdit#UrlInput {{ font-size: 13px; }}
QPlainTextEdit#Log {{ background: white; color: #3A3A3C; font-family: Consolas, "D2Coding", monospace; font-size: 12px;
    border: none; border-top: 1px solid {LINE}; border-radius: 0; padding: 8px 16px; }}
QCheckBox {{ spacing: 8px; color: {BLACK}; }}

/* 표 */
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
QMenu::separator {{ height: 1px; background: {LINE}; margin: 5px 8px; }}
QStatusBar {{ background: white; border-top: 1px solid {LINE}; color: {MUTED}; font-size: 12px; }}
QStatusBar::item {{ border: none; }}
QDialog, QMessageBox {{ background: white; }}
"""


def app_font(size: int = 10) -> QFont:
    font = QFont()
    font.setFamilies(FONT_FAMILIES)
    font.setPointSize(size)
    return font


def apply_palette(app) -> None:
    """체크박스·기본 선택색 등 스타일시트가 닿지 않는 곳도 같은 색으로."""
    pal = app.palette()
    pal.setColor(QPalette.ColorRole.Window, QColor(BG))
    pal.setColor(QPalette.ColorRole.WindowText, QColor(TEXT))
    pal.setColor(QPalette.ColorRole.Base, QColor("white"))
    pal.setColor(QPalette.ColorRole.Text, QColor(TEXT))
    pal.setColor(QPalette.ColorRole.Button, QColor(FILL))
    pal.setColor(QPalette.ColorRole.ButtonText, QColor(BLACK))
    pal.setColor(QPalette.ColorRole.Highlight, QColor(ORANGE))
    pal.setColor(QPalette.ColorRole.HighlightedText, QColor("white"))
    pal.setColor(QPalette.ColorRole.Link, QColor(ORANGE_TEXT))
    app.setPalette(pal)


# ---------------------------------------------------------------- 라인 아이콘 (24 단위 격자)


def _draw(name: str, p: QPainter, color: QColor) -> None:
    pen = QPen(color, 1.8, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin)
    p.setPen(pen)
    p.setBrush(Qt.BrushStyle.NoBrush)
    if name == "cafe":
        p.drawRoundedRect(QRectF(4, 9, 12, 10), 2.5, 2.5)
        p.drawArc(QRectF(13, 10.5, 6.5, 6), -90 * 16, 180 * 16)
        p.drawLine(QPointF(8, 4), QPointF(8, 6))
        p.drawLine(QPointF(12, 4), QPointF(12, 6))
    elif name == "article":
        p.drawRoundedRect(QRectF(5, 3, 14, 18), 2.5, 2.5)
        for y, x2 in ((8.5, 15.5), (12.5, 15.5), (16.5, 12.5)):
            p.drawLine(QPointF(8.5, y), QPointF(x2, y))
    elif name == "chart":
        p.drawLine(QPointF(4, 20), QPointF(20, 20))
        for x, top in ((7, 13), (12, 6), (17, 10)):
            p.drawLine(QPointF(x, 17), QPointF(x, top))
    elif name == "blog":
        roof = QPainterPath(QPointF(3.5, 11.5))
        roof.lineTo(12, 4)
        roof.lineTo(20.5, 11.5)
        p.drawPath(roof)
        p.drawRoundedRect(QRectF(6, 10, 12, 10), 1.5, 1.5)
        p.drawLine(QPointF(12, 20), QPointF(12, 15))
    elif name == "post":
        pen_path = QPainterPath(QPointF(5, 19))
        pen_path.lineTo(6, 15)
        pen_path.lineTo(16, 5)
        pen_path.lineTo(19, 8)
        pen_path.lineTo(9, 18)
        pen_path.closeSubpath()
        p.drawPath(pen_path)
        p.drawLine(QPointF(14, 7), QPointF(17, 10))
    elif name == "kin":
        p.drawEllipse(QPointF(12, 12), 8.5, 8.5)
        q = QPainterPath(QPointF(9.5, 9.8))
        q.cubicTo(9.5, 6.8, 14.5, 6.8, 14.5, 9.8)
        q.cubicTo(14.5, 11.8, 12, 11.8, 12, 13.8)
        p.drawPath(q)
        p.setBrush(color)
        p.setPen(Qt.PenStyle.NoPen)
        p.drawEllipse(QPointF(12, 16.8), 1.1, 1.1)
    elif name == "gear":
        gear = QPainterPath()
        for k in range(8):
            base = k * 45
            for radius, deg in ((7.2, base - 16), (9.6, base - 8), (9.6, base + 8), (7.2, base + 16)):
                pt = QPointF(12 + radius * math.cos(math.radians(deg)), 12 + radius * math.sin(math.radians(deg)))
                if gear.elementCount() == 0:
                    gear.moveTo(pt)
                else:
                    gear.lineTo(pt)
        gear.closeSubpath()
        p.drawPath(gear)
        p.drawEllipse(QPointF(12, 12), 3, 3)
    elif name == "more":
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(color)
        for x in (6, 12, 18):
            p.drawEllipse(QPointF(x, 12), 1.7, 1.7)
    elif name == "user":
        p.drawEllipse(QPointF(12, 8.5), 4, 4)
        p.drawArc(QRectF(4.5, 14, 15, 13), 20 * 16, 140 * 16)
    elif name == "excel":
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
    elif name == "empty":
        p.drawRoundedRect(QRectF(4, 5, 16, 14), 2.5, 2.5)
        p.drawLine(QPointF(4, 9.5), QPointF(20, 9.5))
        p.drawLine(QPointF(8, 13.5), QPointF(16, 13.5))


def icon_pixmap(name: str, color: str = ICON, size: int = 20, ratio: float = 2.0) -> QPixmap:
    pix = QPixmap(int(size * ratio), int(size * ratio))
    pix.fill(Qt.GlobalColor.transparent)
    p = QPainter(pix)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.scale(size * ratio / 24, size * ratio / 24)
    _draw(name, p, QColor(color))
    p.end()
    pix.setDevicePixelRatio(ratio)
    return pix


def icon(name: str, color: str = ICON, selected: str | None = None, disabled: str | None = SUBTLE, size: int = 20) -> QIcon:
    result = QIcon()
    result.addPixmap(icon_pixmap(name, color, size), QIcon.Mode.Normal)
    result.addPixmap(icon_pixmap(name, color, size), QIcon.Mode.Active)
    if selected:
        result.addPixmap(icon_pixmap(name, selected, size), QIcon.Mode.Selected)
    if disabled:
        result.addPixmap(icon_pixmap(name, disabled, size), QIcon.Mode.Disabled)
    return result


# ---------------------------------------------------------------- 로고 (주황 사선 세 줄)


def _draw_mark(p: QPainter, rect: QRectF, color: QColor) -> None:
    """회사 로고의 주황 사선 세 줄 마크. rect 안에 맞춰 그린다 (24 단위 격자)."""
    p.save()
    p.translate(rect.topLeft())
    p.scale(rect.width() / 24, rect.height() / 24)
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(color)
    # (위쪽 왼끝, 위쪽 오른끝, y) - 아래로 갈수록 왼쪽으로 밀린 계단 모양
    stripes = ((8.0, 18.0, 3.0), (5.0, 16.5, 9.5), (2.0, 12.0, 16.0))
    height, slant = 5.0, 4.0
    for left, right, y in stripes:
        path = QPainterPath(QPointF(left + slant, y))
        path.lineTo(right + slant, y)
        path.lineTo(right, y + height)
        path.lineTo(left, y + height)
        path.closeSubpath()
        p.drawPath(path)
    p.restore()


def brand_mark_pixmap(size: int = 32, ratio: float = 2.0) -> QPixmap:
    pix = QPixmap(int(size * ratio), int(size * ratio))
    pix.fill(Qt.GlobalColor.transparent)
    p = QPainter(pix)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    _draw_mark(p, QRectF(0, 0, size * ratio, size * ratio), QColor(ORANGE))
    p.end()
    pix.setDevicePixelRatio(ratio)
    return pix


def app_icon_pixmap(size: int = 256) -> QPixmap:
    """작업 표시줄/exe 아이콘: 검정 라운드 사각형 + 주황 마크."""
    pix = QPixmap(size, size)
    pix.fill(Qt.GlobalColor.transparent)
    p = QPainter(pix)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    bg = QPainterPath()
    bg.addRoundedRect(QRectF(0, 0, size, size), size * 0.23, size * 0.23)
    p.fillPath(bg, QColor(BLACK))
    pad = size * 0.2
    _draw_mark(p, QRectF(pad, pad, size - 2 * pad, size - 2 * pad), QColor(ORANGE))
    p.end()
    return pix


def app_icon() -> QIcon:
    result = QIcon()
    for size in (16, 24, 32, 48, 64, 128, 256):
        result.addPixmap(app_icon_pixmap(size))
    return result
