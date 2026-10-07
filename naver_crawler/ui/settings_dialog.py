"""설정 창."""

from __future__ import annotations

from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from naver_crawler.config import Settings


def _path_row(edit: QLineEdit, caption: str, filt: str) -> QWidget:
    box = QWidget()
    lay = QHBoxLayout(box)
    lay.setContentsMargins(0, 0, 0, 0)
    lay.addWidget(edit, 1)
    btn = QPushButton("찾기…")

    def browse():
        path, _ = QFileDialog.getOpenFileName(box, caption, edit.text(), filt)
        if path:
            edit.setText(path)

    btn.clicked.connect(browse)
    lay.addWidget(btn)
    return box


class SettingsDialog(QDialog):
    def __init__(self, settings: Settings, parent=None):
        super().__init__(parent)
        self.setWindowTitle("설정")
        self.setMinimumWidth(520)
        self.settings = settings

        self.headless = QCheckBox("크롬 창을 숨기고 실행 (로그인할 때는 자동으로 보임)")
        self.headless.setChecked(settings.headless)
        self.keep_login = QCheckBox("로그인 유지 (크롤러 전용 크롬 프로필 사용)")
        self.keep_login.setChecked(settings.keep_login)
        self.debug_html = QCheckBox("실패한 페이지 HTML 저장 (문제 신고용)")
        self.debug_html.setChecked(settings.save_debug_html)

        self.delay = QDoubleSpinBox()
        self.delay.setRange(0, 30)
        self.delay.setSingleStep(0.5)
        self.delay.setSuffix(" 초")
        self.delay.setValue(settings.request_delay)
        self.timeout = QSpinBox()
        self.timeout.setRange(5, 120)
        self.timeout.setSuffix(" 초")
        self.timeout.setValue(settings.page_timeout)

        self.driver = QLineEdit(settings.chromedriver_path)
        self.driver.setPlaceholderText("비워두면 크롬 버전에 맞춰 자동 설치")
        self.chrome = QLineEdit(settings.chrome_binary)
        self.chrome.setPlaceholderText("비워두면 설치된 크롬 자동 탐색")

        form = QFormLayout()
        form.setSpacing(10)
        form.addRow(self.headless)
        form.addRow(self.keep_login)
        form.addRow(self.debug_html)
        form.addRow("URL 사이 대기", self.delay)
        form.addRow("페이지 최대 대기", self.timeout)
        form.addRow("ChromeDriver 경로", _path_row(self.driver, "chromedriver 선택", "chromedriver (chromedriver*)"))
        form.addRow("Chrome 경로", _path_row(self.chrome, "chrome 선택", "chrome (chrome*)"))

        note = QLabel("대기 시간을 너무 짧게 하면 네이버에서 접속을 막을 수 있습니다. 1초 이상을 권장합니다.")
        note.setObjectName("Hint")
        note.setWordWrap(True)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("저장")
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText("취소")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        root = QVBoxLayout(self)
        root.addLayout(form)
        root.addWidget(note)
        root.addWidget(buttons)

    def apply(self) -> bool:
        """설정을 반영한다. 크롬을 다시 띄워야 하면 True."""
        s = self.settings
        restart = (
            s.keep_login != self.keep_login.isChecked()
            or s.chromedriver_path != self.driver.text().strip()
            or s.chrome_binary != self.chrome.text().strip()
        )
        s.headless = self.headless.isChecked()
        s.keep_login = self.keep_login.isChecked()
        s.save_debug_html = self.debug_html.isChecked()
        s.request_delay = float(self.delay.value())
        s.page_timeout = int(self.timeout.value())
        s.chromedriver_path = self.driver.text().strip()
        s.chrome_binary = self.chrome.text().strip()
        return restart
