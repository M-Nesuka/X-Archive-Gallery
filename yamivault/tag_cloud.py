"""Compact, wrapping tag links with a height measured from the actual text."""
from PySide6.QtCore import Qt
from PySide6.QtGui import QTextDocument
from PySide6.QtWidgets import QLabel,QSizePolicy


class TagCloud(QLabel):
    def __init__(self):
        super().__init__()
        self.setObjectName('tagCloud')
        self.setWordWrap(True)
        self.setTextFormat(Qt.TextFormat.RichText)
        self.setTextInteractionFlags(Qt.TextInteractionFlag.LinksAccessibleByMouse)
        self.setAlignment(Qt.AlignmentFlag.AlignTop|Qt.AlignmentFlag.AlignLeft)
        self.setSizePolicy(QSizePolicy.Policy.Ignored,QSizePolicy.Policy.Fixed)
        self.setMargin(0)

    def heightForWidth(self,width):
        doc=QTextDocument();doc.setDocumentMargin(0);doc.setDefaultFont(self.font())
        doc.setHtml(self.text());doc.setTextWidth(max(50,width))
        return int(doc.size().height())+4

    def setText(self,text):
        super().setText(text)
        self.setFixedHeight(self.heightForWidth(self.width()))
        self.setVisible(bool(text))

    def resizeEvent(self,event):
        super().resizeEvent(event)
        height=self.heightForWidth(event.size().width())
        if self.height()!=height:self.setFixedHeight(height)
