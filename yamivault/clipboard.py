"""Windows-compatible clipboard payloads. No source-file writes or moves."""
from pathlib import Path
from PySide6.QtCore import QMimeData, QUrl, QBuffer, QIODevice, QByteArray
from PySide6.QtGui import QImage


def image_payload(image: QImage):
    if image.isNull():
        raise ValueError('この画像を読み込めませんでした。')
    mime = QMimeData()
    mime.setImageData(image)
    data = QByteArray()
    buffer = QBuffer(data)
    buffer.open(QIODevice.OpenModeFlag.WriteOnly)
    image.save(buffer, 'PNG')
    buffer.close()
    mime.setData('image/png', data)
    return mime


def file_payload(path: Path):
    if not Path(path).is_file():
        raise FileNotFoundError('元ファイルが見つかりません。ドライブの接続を確認してください。')
    mime = QMimeData()
    mime.setUrls([QUrl.fromLocalFile(str(Path(path).resolve()))])
    # Explorer must treat this as COPY, never CUT/MOVE.
    mime.setData('application/x-qt-windows-mime;value="Preferred DropEffect"', QByteArray(b'\x01\x00\x00\x00'))
    return mime
