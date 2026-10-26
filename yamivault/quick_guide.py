"""Short, actionable beginner guide; detailed help remains available."""
from PySide6.QtWidgets import (QDialog,QVBoxLayout,QHBoxLayout,QTabWidget,QWidget,
    QLabel,QPushButton,QScrollArea)
from PySide6.QtCore import Qt
from .i18n import tr
from .appearance import theme_css


class QuickGuideDialog(QDialog):
    def __init__(self,window):
        super().__init__(window)
        self.setWindowTitle(tr('かんたんガイド'));self.resize(740,640)
        self.setMinimumSize(480,400)
        self.setStyleSheet(theme_css('''QDialog { background:#151419; }
            QLabel { font-size:16px; color:#e2dfe8; }
            QLabel#guideTitle { font-size:24px; font-weight:600; color:#eeebf4; }
            QLabel#guideSection { font-size:18px; font-weight:600; color:#e6d8f5; }
            QTabBar::tab { padding:10px 14px; font-size:15px; }
            QTabBar::tab:selected { background:#2b2437; color:#e5d4ff; }
            QPushButton#guideAction { background:#2b2437; color:#e5d4ff; border:1px solid #8a779e; }
            QPushButton#guideAction:disabled { color:#76707f; border-color:#39313f; }
            QPushButton { font-size:15px; padding:9px 12px; }'''))
        layout=QVBoxLayout(self);layout.setContentsMargins(20,18,20,18);layout.setSpacing(12)
        title=QLabel(tr('まずは、ここから。'));title.setObjectName('guideTitle');layout.addWidget(title)
        lead=QLabel(tr('やりたいことを選んでください。下のボタンから、その画面へ進めます。'))
        lead.setWordWrap(True);layout.addWidget(lead)
        self.tabs=QTabWidget();layout.addWidget(self.tabs,1)
        self.actions={}
        def page(name):
            scroll=QScrollArea();scroll.setWidgetResizable(True)
            content=QWidget();column=QVBoxLayout(content)
            column.setContentsMargins(16,16,16,16);column.setSpacing(16)
            scroll.setWidget(content);self.tabs.addTab(scroll,tr(name));return column
        def card(column,title,text,label=None,action=None,key=None,enabled=True):
            heading=QLabel(tr(title));heading.setObjectName('guideSection');heading.setWordWrap(True);column.addWidget(heading)
            body=QLabel(tr(text));body.setWordWrap(True);column.addWidget(body)
            if label:
                button=QPushButton(tr(label));button.setAutoDefault(False);button.setEnabled(enabled)
                button.setObjectName('guideAction');button.setMaximumWidth(360)
                button.clicked.connect(lambda:self.navigate(action))
                column.addWidget(button,alignment=Qt.AlignmentFlag.AlignLeft);self.actions[key]=button
        one=page('① 作品を入れる')
        card(one,'Xの画像・動画を、このアプリへ',
             '① 保存するフォルダーを選ぶ → ② Xから受け取ったZIPを選ぶ → ③ 取り込み開始。ZIPは解凍しなくて大丈夫です。',
             '作品を入れる画面へ',window.open_import,'archive')
        card(one,'XのZIPを持っていないとき',
             'Xの投稿と画像が入ったファイルです。入手方法を見ながら、Xで申し込めます。',
             'ZIPの入手方法を見る',self.archive_help,'zip_help')
        card(one,'成績データは、あとからでもOK',
             'Analyticsは投稿の成績をまとめたCSVです。入れると高成績・NO.1タグが付きます。持っていなくても、作品を見る・タグを付ける・お気に入りは使えます。追加・更新も「アーカイブを取り込む」画面からできます。')
        one.addStretch()
        two=page('② タグをつける')
        ready=bool(window.library_id and not window.aggregate_entries)
        card(two,'先に、使いたいタグを作りましょう',
             '「タグを管理」→「新しいタグ」で、名前と色を選び「このタグを作る」を押します。いつでも画面上の「タグを管理」から追加・変更できます。',
             'タグを作る・整理する',lambda:self.tags(window),'tags',ready)
        if not ready:
            card(two,'まず作品を取り込んでください',
                 '作品を入れると、タグを作れるようになります。複数アカウントを使う方は、左上でタグを作りたい@アカウントを1つ選びます。')
        card(two,'画像を右クリックして、タグを選ぶだけ',
             '「よく使うタグを付ける」から選びます。同じタグをもう一度選ぶと外れます。複数の画像はドラッグでまとめて選べます。タグをグループ分けすると、たくさんあっても探しやすくなります。')
        card(two,'投稿の言葉から、自動で付けることもできます',
             'タグ管理の「投稿から自動タグ」で設定します。「登録タグ」で「比較」を選び、「検索する言葉」に「比較」「テーマ」をそれぞれ入力して「追加」を押します。どちらかが投稿にあれば「比較」が付きます。画像をAIで判定する機能ではありません。')
        two.addStretch()
        three=page('③ 見る・探す')
        card(three,'画像を見る',
             '左クリックで詳細を表示。詳細の画像をクリックすると大きく見られます。右クリックでは、タグ・お気に入りなどのメニューが開きます。')
        card(three,'タグで探す',
             '画像のタグを押すか、「すべての作品 ▼」→「手動タグ」から選びます。選択中は✓が付きます。複数選ぶと、全部のタグを持つ作品が出ます。')
        card(three,'元の一覧へ戻りたいとき',
             '左上のXロゴ・アプリ名を押すとホームへ戻ります。「← 戻る」は、1つ前の絞り込みや表示へ戻るボタンです。')
        card(three,'新しいデータを追加したいとき',
             '「アーカイブを取り込む」から、新しいZIPやAnalytics CSVを追加します。初期化は不要です。同じアカウントの保存先へ追加すると、登録済みの作品やタグを引き継げます。')
        three.addStretch()
        footer=QHBoxLayout();layout.addLayout(footer)
        detail=QPushButton(tr('詳しい使い方を読む'));detail.clicked.connect(lambda:self.navigate(window.show_help));footer.addWidget(detail)
        close=QPushButton(tr('閉じる'));close.clicked.connect(self.close);footer.addWidget(close)

    def navigate(self,action):
        self.close();action()

    def archive_help(self):
        from .help_ui import ArchiveDownloadDialog
        ArchiveDownloadDialog(self.parentWidget()).exec()

    @staticmethod
    def tags(window):
        window.close_import();window.manage_manual_tags()
