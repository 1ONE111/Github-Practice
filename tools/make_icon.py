"""assets/app.ico 생성 (앱 아이콘을 바꾼 뒤 한 번 실행).

    python tools/make_icon.py
"""

import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from PIL import Image  # noqa: E402
from PySide6.QtCore import QBuffer, QIODevice  # noqa: E402
from PySide6.QtGui import QGuiApplication  # noqa: E402

from naver_crawler.ui.theme import app_icon_pixmap  # noqa: E402

app = QGuiApplication([])
buf = QBuffer()
buf.open(QIODevice.OpenModeFlag.WriteOnly)
app_icon_pixmap(256).save(buf, "PNG")
png = Path(__file__).resolve().parents[1] / "assets" / "app.png"
png.parent.mkdir(exist_ok=True)
png.write_bytes(bytes(buf.data()))
Image.open(png).save(png.with_suffix(".ico"), sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
print("saved", png.with_suffix(".ico"))
