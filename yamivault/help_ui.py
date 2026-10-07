"""Readable, topic-based in-app help; no browser or network is needed."""
from .i18n import tr,trf,language
from .appearance import theme_css
from html import escape
from PySide6.QtCore import Qt,QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QDialog,QVBoxLayout,QHBoxLayout,QLabel,QTabWidget,QTextBrowser,QPushButton
from .help_guide import GUIDE
from .version import __version__, __author__

ARCHIVE_HELP_URL='https://help.x.com/ja/managing-your-account/how-to-download-your-x-archive'
ARCHIVE_DOWNLOAD_STEPS=[
    ('1. Xを開いてログイン', '保存したいアカウントでXにログインします。複数アカウントがある方は、@ユーザー名を確認しましょう。'),
    ('2. Xの設定を開く', '「設定とプライバシー」→「アカウント」から、「データのアーカイブをダウンロード」または「Xデータ」を開きます。画面名はX側で変わることがあります。'),
    ('3. データを申し込む', 'Xの案内に従って本人確認をし、「アーカイブをリクエスト」などのボタンを押します。'),
    ('4. 通知が届くまで待つ', '準備ができると、Xからメールや通知が届きます。数日かかることもあるので、すぐに取得できなくても大丈夫です。'),
    ('5. ZIPをPCに保存して、ここへ戻る', 'Xの案内からZIPファイルをダウンロードします。解凍せずに残し、このアプリの②で選んでください。')]

class ArchiveDownloadDialog(QDialog):
    def __init__(self,parent=None):
        super().__init__(parent)
        self.setWindowTitle(tr('XのデータZIPを入手するには'))
        self.resize(620,650);self.setMinimumSize(480,400)
        layout=QVBoxLayout(self)
        self.guide=QTextBrowser()
        self.guide.setOpenExternalLinks(False)
        self.guide.setStyleSheet(theme_css('QTextBrowser { background:#151419; color:#e2dfe8; font-size:16px; padding:12px; border:0; }'))
        content=tr('<h2>あなたの投稿と画像を、Xから受け取ります。</h2><p>「アーカイブ」は、Xの投稿や画像・動画などが入ったデータ一式のことです。XからZIPという1つのファイルで受け取れます。</p>')
        for title,text in ARCHIVE_DOWNLOAD_STEPS:
            content+=f'<h3 style="color:#e6d8f5; margin-top:22px;">{escape(tr(title))}</h3><p>{escape(tr(text))}</p>'
        content+=tr('<p>申し込みや本人確認はXの画面で行います。このアプリにXのパスワードを入力する必要はありません。</p>')
        self.guide.setHtml(theme_css(content));layout.addWidget(self.guide,1)
        self.browser_error=QLabel(tr('ブラウザーを開けませんでした。Xのヘルプセンターで「全ポスト履歴をダウンロードする方法」を検索してください。'))
        self.browser_error.setWordWrap(True);self.browser_error.hide();layout.addWidget(self.browser_error)
        row=QHBoxLayout()
        self.official_button=QPushButton(tr('X公式の案内を開く ↗'))
        self.official_button.clicked.connect(self.open_official_help);row.addWidget(self.official_button)
        back=QPushButton(tr('取り込みに戻る'));back.setObjectName('primary');back.clicked.connect(self.accept);row.addWidget(back)
        layout.addLayout(row)

    def open_official_help(self):
        url=ARCHIVE_HELP_URL.replace('/ja/','/en/') if language()=='en' else ARCHIVE_HELP_URL
        self.browser_error.setVisible(not QDesktopServices.openUrl(QUrl(url)))


class HelpDialog(QDialog):
    def __init__(self,parent=None):
        super().__init__(parent)
        self.setWindowTitle(tr('使い方 · X Archive Gallery'))
        self.resize(810,650)
        self.setMinimumSize(650,420)
        self.setObjectName('helpDialog')
        self.setStyleSheet(theme_css('''
            QDialog#helpDialog { background:#151419; }
            QTabWidget, QTabBar { background:#151419; }
            QTabWidget::pane { border:0; background:#151419; }
            QTabBar::tab { background:#151419; color:#c7c0cf; padding:12px 10px; font-size:14px; border-bottom:2px solid transparent; }
            QTabBar::tab:selected { color:#efedf3; border-bottom:2px solid #b5a3d2; }
            QTabBar::tab:hover { color:#ffffff; background:#211e27; }
            QTextBrowser { background:#151419; border:0; padding:12px 18px; font-size:16px; color:#e2dfe8; }
        '''))
        layout=QVBoxLayout(self);layout.setContentsMargins(16,12,16,12);layout.setSpacing(8)
        title=QLabel(tr('知りたいことだけ、ここから。'))
        title.setStyleSheet(theme_css('font-size:20px; color:#eeebf4; padding:2px 4px;'))
        layout.addWidget(title)
        self.tabs=QTabWidget();self.tabs.setObjectName('helpTabs')
        self.tabs.tabBar().setExpanding(False)
        self.tabs.tabBar().setDrawBase(False)
        self.tabs.setDocumentMode(True)
        for tab,heading,lead,blocks in GUIDE:
            page=QTextBrowser();page.setOpenExternalLinks(False)
            page.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            content=f'<h1 style="font-size:24px; font-weight:600; margin-bottom:12px;">{escape(tr(heading))}</h1>'
            content+=f'<p style="color:#bfb6cc; font-size:16px; margin-bottom:24px;">{escape(tr(lead))}</p>'
            for name,paragraphs in blocks:
                content+=f'<h2 style="font-size:18px; font-weight:600; margin-top:24px; margin-bottom:10px; color:#e6d8f5;">{escape(tr(name))}</h2>'
                content+=''.join(f'<p style="margin-top:0; margin-bottom:12px; line-height:145%;">{escape(tr(p))}</p>' for p in paragraphs)
            page.setHtml(theme_css(content))
            page.verticalScrollBar().setValue(0)
            self.tabs.addTab(page,tr(tab))
        layout.addWidget(self.tabs,1)
        version=QLabel(f'X Archive Gallery · v{__version__}')
        version.setStyleSheet(theme_css('font-size:12px; color:#8f879a; padding:0 4px;'))
        footer=QHBoxLayout()
        footer.addWidget(version)
        footer.addStretch()
        creator=QLabel(f'Created by {__author__}')
        creator.setObjectName('creatorSignature')
        creator.setStyleSheet(theme_css('font-size:13px; color:#bfb6cc; padding:0 4px;'))
        footer.addWidget(creator)
        layout.addLayout(footer)
        libraries=QLabel('Qt / PySide6 · LGPLv3  |  FFmpeg · LGPLv2.1+')
        libraries.setObjectName('thirdPartyNotice')
        libraries.setStyleSheet(theme_css('font-size:13px; color:#bfb6cc; padding:0 4px;'))
        layout.addWidget(libraries)
