"""Compact in-window import drawer. No backup code runs on this UI thread."""
from .i18n import tr,trf,error_text
from .i18n import software_message
from PySide6.QtCore import Qt, Signal,QTimer
from pathlib import Path
import logging
from PySide6.QtWidgets import QFrame,QVBoxLayout,QHBoxLayout,QLabel,QPushButton,QProgressBar,QScrollArea,QTextBrowser,QFileDialog,QWidget,QSizePolicy,QCheckBox
from .setup_ui import SetupPresentation


class ImportPanel(SetupPresentation,QFrame):
    closed=Signal()
    def __init__(self, controller, get_root, on_analytics_import=None, parent=None):
        super().__init__(parent)
        self.history={}
        self.controller=controller
        self.get_root=get_root
        self.pending_zip=None
        self.pending_destination=None
        self.destination_error=''
        self.pending_csv=None
        self.analytics_preview=None
        self.analytics_error=''
        self.analytics_busy=False
        self.combined_message=''
        self.awaiting_analytics=False
        self.preview_busy=False
        self._csv_match_key=None
        self._csv_match_posts=set()
        self.setObjectName('details')
        self.setMinimumWidth(280)
        self.setMaximumWidth(440)
        self.setSizePolicy(QSizePolicy.Policy.Preferred,QSizePolicy.Policy.Expanding)
        outer=QVBoxLayout(self)
        self.outer_layout=outer
        outer.setContentsMargins(0,0,0,0)
        header=QHBoxLayout()
        title=QLabel(tr('作品をギャラリーに入れる'))
        header.addWidget(title,1)
        close=QPushButton('✕')
        close.setObjectName('setupClose')
        close.setFixedSize(38,38)
        close.setAccessibleName(tr('取り込みサイドバーを閉じる'))
        close.setToolTip(tr('取り込み中もパネルを閉じて閲覧できます'))
        close.clicked.connect(lambda checked=False:self.closed.emit())
        self.setup_help=QPushButton(tr('使い方'))
        self.setup_help.clicked.connect(lambda:self.window().show_help())
        self.setup_help.hide()
        header.addWidget(self.setup_help)
        header.addWidget(close)
        outer.addLayout(header)
        scroll=QScrollArea()
        self.scroll=scroll
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        content=QWidget()
        content.setObjectName('details')
        content.setMinimumWidth(0)
        content.setSizePolicy(QSizePolicy.Policy.Ignored,QSizePolicy.Policy.Preferred)
        layout=QVBoxLayout(content)
        self.content_layout=layout
        layout.setContentsMargins(14,16,14,18)
        layout.setSpacing(14)
        self.choose_destination_button=QPushButton(tr('① 作品の保存場所を選ぶ'))
        self.choose_destination_button.clicked.connect(self.choose_destination)
        self.choose_destination_button.setToolTip(tr('新規は保存する場所を選択。@ユーザー名と投稿年のフォルダーを自動で作ります。追加は既存のバックアップを選択します。'))
        layout.addWidget(self.choose_destination_button)
        self.destination=QLabel()
        self.destination.setObjectName('muted')
        self.destination.setWordWrap(True)
        self.destination.setMinimumWidth(0)
        self.destination.setSizePolicy(QSizePolicy.Policy.Ignored,QSizePolicy.Policy.Preferred)
        layout.addWidget(self.destination)
        self.choose=QPushButton(tr('② XのデータZIPを選ぶ'))
        self.choose.clicked.connect(self.choose_zip)
        layout.addWidget(self.choose)
        self.archive_explanation=QLabel(tr('Xの投稿・画像をまとめたファイルです。\nXから「データのアーカイブ」を取得して使います。'))
        self.archive_explanation.setObjectName('muted')
        self.archive_explanation.setWordWrap(True)
        self.archive_explanation.setMinimumWidth(0)
        self.archive_explanation.setSizePolicy(QSizePolicy.Policy.Ignored,QSizePolicy.Policy.Preferred)
        layout.addWidget(self.archive_explanation)
        self.archive_help_button=QPushButton(tr('ZIPの入手方法を見る'))
        self.archive_help_button.setToolTip(tr('Xでの申し込みから、ZIPを保存するまでを説明します'))
        self.archive_help_button.clicked.connect(self.show_archive_help)
        layout.addWidget(self.archive_help_button)
        self.zip_label=QLabel(tr('公式アーカイブZIPを選択してください。'))
        self.zip_label.setObjectName('muted')
        self.zip_label.setWordWrap(True)
        self.zip_label.setTextFormat(Qt.TextFormat.PlainText)
        self.zip_label.setMinimumWidth(0)
        self.zip_label.setSizePolicy(QSizePolicy.Policy.Ignored,QSizePolicy.Policy.Preferred)
        layout.addWidget(self.zip_label)
        self.flow_hint=QLabel(tr('① 保存先 → ② ZIP → ③ Analytics（任意）→ ギャラリー'))
        self.flow_hint.setObjectName('muted')
        self.flow_hint.setWordWrap(True)
        layout.addWidget(self.flow_hint)
        self.flow_hint.hide()
        self.message=QLabel(software_message(controller.message))
        self.message.setWordWrap(True)
        self.message.setTextFormat(Qt.TextFormat.PlainText)
        self.message.setMinimumWidth(0)
        self.message.setSizePolicy(QSizePolicy.Policy.Ignored,QSizePolicy.Policy.Preferred)
        layout.addWidget(self.message)
        layout.removeWidget(self.message)
        layout.insertWidget(0,self.message)
        self.progress=QProgressBar()
        self.progress.setTextVisible(False)
        self.progress.setFixedHeight(5)
        layout.addWidget(self.progress)
        self.retry=QPushButton(tr('もう一度確認する'))
        self.retry.clicked.connect(self.retry_analysis)
        layout.addWidget(self.retry)
        self.start=QPushButton(tr('取り込み開始'))
        self.start.setObjectName('primary')
        self.start.clicked.connect(self.start_selected_import)
        analytics_header=QLabel(tr('③ ANALYTICS（任意）'))
        self.analytics_header=analytics_header
        analytics_header.setObjectName('field')
        layout.addWidget(analytics_header)
        self.analytics_explanation=QLabel(tr('投稿の成績から、高成績・NO.1タグが自動で付きます。\nXの「コンテンツ（投稿別）」CSVが対象です。\n\nX Premium（青い認証バッジ対象プラン）などの利用権限が必要です。持っていなくても大丈夫。後から追加できます。\n\n画像をAIで解析する機能ではありません。'))
        self.analytics_explanation.setWordWrap(True)
        self.analytics_explanation.setObjectName('muted')
        self.analytics_explanation.setMinimumWidth(0)
        self.analytics_explanation.setSizePolicy(QSizePolicy.Policy.Ignored,QSizePolicy.Policy.Preferred)
        layout.addWidget(self.analytics_explanation)
        analytics_row=QHBoxLayout()
        self.analytics_row=analytics_row
        self.analytics_status=QLabel(tr('未取り込み'))
        self.analytics_status.setObjectName('muted')
        self.analytics_status.setWordWrap(True)
        self.analytics_status.setMinimumWidth(0)
        self.analytics_status.setSizePolicy(QSizePolicy.Policy.Ignored,QSizePolicy.Policy.Preferred)
        analytics_row.addWidget(self.analytics_status,1)
        self.analytics_import_button=QPushButton(tr('Analytics CSVを追加'))
        self.analytics_import_button.setToolTip(tr('コンテンツ（投稿別）のX Analytics CSVを選択します。'))
        self.analytics_import_button.setObjectName('analyticsImport')
        self.analytics_import_button.clicked.connect(lambda:self.window().choose_combined_csv())
        analytics_row.addWidget(self.analytics_import_button)
        layout.addLayout(analytics_row)
        self.keep_csv=QCheckBox(tr('元のCSVもバックアップに保存'))
        self.keep_csv.setChecked(bool(controller.store.get('keep_analytics_csv',False)))
        self.keep_csv.setToolTip(tr('ON：アカウント別バックアップのAnalyticsフォルダーに元CSVをコピーします。\nOFFでも成績データ・タグはアプリのDBに保存されます。'))
        self.keep_csv.toggled.connect(lambda enabled:controller.store.set('keep_analytics_csv',bool(enabled)))
        layout.addWidget(self.keep_csv)
        self.csv_summary=QLabel()
        self.csv_summary.setWordWrap(True)
        self.csv_summary.setTextFormat(Qt.TextFormat.PlainText)
        self.csv_summary.setMinimumWidth(0)
        self.csv_summary.setSizePolicy(QSizePolicy.Policy.Ignored,QSizePolicy.Policy.Preferred)
        layout.addWidget(self.csv_summary)
        self.clear_csv_button=QPushButton(tr('CSVの選択を解除'))
        self.clear_csv_button.clicked.connect(self.clear_csv)
        layout.addWidget(self.clear_csv_button)
        self.skip_analytics_button=QPushButton(tr('今はスキップ'))
        self.skip_analytics_button.setToolTip(tr('Analyticsなしで利用できます。後から同じ取り込み画面で追加できます。'))
        self.skip_analytics_button.clicked.connect(self.skip_clicked)
        layout.addWidget(self.skip_analytics_button)
        self.view_gallery_button=QPushButton(tr('④ ギャラリーを見る'))
        self.view_gallery_button.setObjectName('primary')
        self.view_gallery_button.clicked.connect(lambda:self.window().close_import())
        self.summary=QLabel()
        self.summary.setWordWrap(True)
        self.summary.setTextFormat(Qt.TextFormat.PlainText)
        self.summary.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.summary.setMinimumWidth(0)
        self.summary.setSizePolicy(QSizePolicy.Policy.Ignored,QSizePolicy.Policy.Preferred)
        layout.addWidget(self.summary)
        # Show the account, destination and counts before optional Analytics.
        layout.removeWidget(self.summary)
        layout.insertWidget(layout.indexOf(self.progress),self.summary)
        self.cancel=QPushButton(tr('安全に中止'))
        self.cancel.clicked.connect(controller.cancel)
        layout.addWidget(self.cancel)
        self.preview_issues=QPushButton(tr('注意対象の画像を確認'))
        self.preview_issues.clicked.connect(self.open_issue_gallery)
        layout.addWidget(self.preview_issues)
        self.reset_button=QPushButton(tr('保存した作品をすべて削除…'))
        self.reset_button.setToolTip(tr('選択中のバックアップ内の作品・管理情報をすべて削除します'))
        self.reset_button.clicked.connect(self._reset_library)
        layout.addWidget(self.reset_button)
        self.details_button=QPushButton(tr('確認事項を表示'))
        self.details_button.setCheckable(True)
        self.details_button.toggled.connect(self.toggle_issues)
        layout.addWidget(self.details_button)
        self.issues=QTextBrowser()
        self.issues.setOpenExternalLinks(False)
        self.issues.setMinimumHeight(180)
        self.issues.hide()
        layout.addWidget(self.issues)
        note=QLabel(tr('既存の作品は上書きしません。\n取り込み中もギャラリーを閲覧できます。'))
        self.import_note=note
        note.setObjectName('muted')
        note.setWordWrap(True)
        layout.addWidget(note)
        layout.addStretch()
        scroll.setWidget(content)
        outer.addWidget(scroll,1)
        # Keep the next action in view, including small windows and long CSVs.
        outer.addWidget(self.start)
        outer.addWidget(self.view_gallery_button)
        self._painted_setup_step=None
        self.build_setup_presentation()
        controller.changed.connect(self.update_state)
        self._detail_key=None
        self.update_state()

    def set_analytics_status(self, text, tooltip=''):
        self.analytics_status.setText(text)
        self.analytics_status.setToolTip(tooltip)

    def show_archive_help(self):
        from .help_ui import ArchiveDownloadDialog
        ArchiveDownloadDialog(self).exec()

    @staticmethod
    def highlight_next(button,active):
        name='primary' if active else ''
        if button.objectName()!=name:
            button.setObjectName(name)
            button.style().unpolish(button)
            button.style().polish(button)
            button.update()

    def choose_zip(self):
        if self.controller.active or self.analytics_busy:
            return
        path,_=QFileDialog.getOpenFileName(self,tr('X公式アーカイブZIPを選択'),'',tr('ZIPアーカイブ (*.zip)'))
        if path:
            self.setup_override=None
            self.pending_zip=Path(path).resolve()
            self.destination_error=''
            self.combined_message=''
            logging.getLogger(__name__).info('Archive selected')
            root=self.pending_destination
            if root is None and (self.get_root()/'.system/catalog.sqlite3').is_file():
                root=self.get_root()
            if root is None:
                self.controller.reset()
                self.update_state()
                self.choose_destination_button.setFocus()
            else:
                self.set_destination(root)

    def choose_destination(self):
        if self.controller.active or self.analytics_busy:
            return
        initial=self.pending_destination or self.get_root()
        initial=initial if initial.is_dir() else initial.parent
        folder=QFileDialog.getExistingDirectory(self,
            tr('バックアップ専用フォルダーを選択（新規は空のフォルダー）'),str(initial),QFileDialog.Option.ShowDirsOnly)
        if folder:
            selected=Path(folder).resolve()
            from .library_reset import is_empty_or_lock_only
            if not (selected/'.system/catalog.sqlite3').is_file() and (selected.parent==selected or not is_empty_or_lock_only(selected)):
                # A drive or Downloads is a parent, never a place to mix backups
                # with unrelated contents. Creation awaits the Start button.
                dedicated=selected/'X Archive Gallery Library'
                if dedicated.exists() and not (dedicated/'.system/catalog.sqlite3').is_file() and not is_empty_or_lock_only(dedicated):
                    dedicated=selected/'X Archive Gallery Library 2'
                folder=dedicated
            self.set_destination(folder)
        else:
            self.update_state()

    def set_destination(self, folder):
        if self.controller.active or self.analytics_busy:
            return False
        from .import_destination import validate_destination
        try:
            root=validate_destination(folder,self.controller.store.directory)
            self.destination_error=''
            self.pending_destination=root
            self.setup_override=None
            self.combined_message=''
            logging.getLogger(__name__).info('Destination selected')
            if self.pending_zip:
                current_zip=Path(self.controller.request.get('zip_path','')).resolve() if hasattr(self.controller,'request') else None
                if self.controller.phase=='ready' and current_zip==self.pending_zip:
                    self.controller.change_destination(root)
                else:
                    self.controller.analyze(self.pending_zip,root)
            self.update_state()
            return True
        except Exception as error:
            logging.getLogger(__name__).exception('Destination selection or analysis failed')
            from .diagnostics import friendly_error
            self.destination_error=friendly_error(error,tr('保存先の選択'))
            self.update_state()
            return False

    def retry_analysis(self):
        if self.pending_zip and self.pending_destination:
            try:
                self.destination_error='';self.combined_message=''
                self.controller.analyze(self.pending_zip,self.pending_destination)
            except Exception as error:
                logging.getLogger(__name__).exception('Archive analysis failed to start')
                from .diagnostics import friendly_error
                self.destination_error=friendly_error(error,tr('アーカイブの解析'));self.update_state()

    def clear_csv(self):
        if self.analytics_busy or self.preview_busy:return
        self.pending_csv=None;self.analytics_preview=None;self.analytics_error=''
        self.combined_message='';self.update_state()

    def skip_analytics(self):
        self.clear_csv()
        self.combined_message=tr('Analyticsはスキップしました。ギャラリー・手動タグ・お気に入り・検索はそのまま利用できます。後からここでCSVを追加できます。')
        self.update_state()

    def toggle_issues(self,checked):
        self.issues.setVisible(checked)

    def _reset_library(self):
        window=self.window()
        if hasattr(window,'reset_backup'):
            window.reset_backup()

    def open_issue_gallery(self):
        issues=self.controller.summary.get('issues',[]) or self.controller.result.get('result',{}).get('issues',[])
        fallback=self.controller.request.get('zip_path') if hasattr(self.controller,'request') else None
        issues=[dict(issue,zip_path=issue.get('zip_path') or fallback) for issue in issues]
        if not issues:
            return
        from .issues_viewer import IssueGallery
        window=self.window()
        target=self.controller.root or self.pending_destination or self.get_root()
        def added():
            if (target/'.system/catalog.sqlite3').is_file():
                window.refresh(target)
            else:
                window.toast(tr('追加した注意画像は、取り込み完了後に表示します'))
        IssueGallery(issues,self.controller.store.directory,self,library_root=target,
                     on_added=added).exec()

    def update_state(self):
        c=self.controller
        busy=c.active or self.analytics_busy
        signature=(self.onboarding,c.phase,self.analytics_busy,self.preview_busy,c.cancel_requested,
                   self.destination_error,self.analytics_error,self.combined_message,
                   self.pending_zip,self.pending_csv,self.pending_destination,id(c.summary),id(c.result),
                   getattr(self.window(),'library_configured',False),getattr(self.window(),'loading',False))
        if (busy or self.preview_busy) and signature==getattr(self,'_busy_signature',None):
            self.update_progress_meter()
            return
        self._busy_signature=signature
        if c.phase=='ready' and c.root:self.pending_destination=c.root
        s=c.summary
        busy=c.active or self.analytics_busy
        destination_ready=bool(self.pending_destination or (self.get_root()/'.system/catalog.sqlite3').is_file())
        self.choose.setEnabled(not busy and destination_ready)
        self.choose.setToolTip(tr('Xから取得したZIPを選びます。解凍せず、そのまま使えます。') if destination_ready else tr('まず①で、作品を保存する場所を選んでください。'))
        self.highlight_next(self.choose_destination_button,not busy and (not destination_ready or bool(self.destination_error)))
        self.highlight_next(self.choose,not busy and destination_ready and not self.pending_zip and not self.destination_error)
        self.choose_destination_button.setEnabled(not busy)
        self.analytics_import_button.setEnabled(not busy and not self.preview_busy)
        self.keep_csv.setEnabled(not busy and not self.preview_busy)
        self.clear_csv_button.setVisible(self.pending_csv is not None)
        self.clear_csv_button.setEnabled(not busy and not self.preview_busy)
        self.skip_analytics_button.setEnabled(not busy and not self.preview_busy)
        self.skip_analytics_button.setVisible(not getattr(self.window(),'library_configured',False) or bool(self.pending_zip or self.pending_csv))
        self.view_gallery_button.setVisible(getattr(self.window(),'library_configured',False) and not busy and not getattr(self.window(),'loading',False))
        self.retry.setVisible(bool(self.pending_zip and self.pending_destination) and not busy and c.phase!='ready')
        self.reset_button.setEnabled(not busy and not getattr(self.window(),'loading',False) and not getattr(self.window(),'aggregate_entries',[]))
        self.reset_button.setVisible((self.get_root()/'.system'/'catalog.sqlite3').is_file())
        issues_preview=c.summary.get('issues',[]) or c.result.get('result',{}).get('issues',[])
        self.preview_issues.setVisible(bool(issues_preview))
        csv_only=not self.pending_zip and self.pending_csv and getattr(self.window(),'library_configured',False)
        self.start.setVisible(not self.view_gallery_button.isVisible() or bool(self.pending_csv) or c.phase=='ready' or busy)
        archive_ready=c.phase=='ready' and bool(s.get('total'))
        csv_ready=bool(self.analytics_preview and self.analytics_preview.rows and not self.analytics_preview.duplicate_post_ids and not self.analytics_preview.invalid_rows)
        self.start.setEnabled(bool(archive_ready or csv_only and csv_ready) and not busy and not self.preview_busy and not self.destination_error and not self.analytics_error and (not self.pending_csv or csv_ready))
        self.start.setText(tr('アーカイブ＋Analyticsを取り込む') if self.pending_zip and self.pending_csv else (tr('Analyticsを取り込む') if csv_only else tr('取り込み開始')))
        self.cancel.setVisible(c.active)
        self.cancel.setEnabled(not c.cancel_requested)
        if self.analytics_error:
            self.message.setText(self.analytics_error)
        elif self.preview_busy:
            self.message.setText(tr('Analytics CSVを確認しています…'))
        elif self.analytics_busy:
            self.message.setText(tr('Analyticsを保存し、高成績タグを計算しています…'))
        elif self.destination_error:
            self.message.setText(self.destination_error)
        elif c.active:
            self.message.setText(tr('中止を準備しています…') if c.cancel_requested else
                                 tr('Xのデータを確認しています…') if c.phase=='analyzing' else tr('作品を保存しています…'))
        elif self.combined_message:
            self.message.setText(self.combined_message)
        elif self.pending_zip and not c.job:
            self.message.setText(tr('ZIPを選択しました。次に「① 作品の保存場所を選ぶ」を押してください。') if not self.pending_destination else tr('ZIPと保存先を確認してください。'))
        elif not self.pending_zip and not self.pending_csv and not getattr(self.window(),'library_configured',False):
            self.message.setText(tr('次は②で、Xから保存したZIPを選びましょう。') if self.pending_destination else tr('①で、作品を保存する場所を選びましょう。'))
        else:
            self.message.setText(software_message(c.message))
        self.update_progress_meter()
        target=c.root or self.pending_destination
        if target is None and (self.get_root()/'.system/catalog.sqlite3').is_file():
            target=self.get_root()
        self.destination.setText((str(target).replace('\\','\\\u200b')+(tr('\n取り込み開始後にこのフォルダーを作成します。') if not target.exists() else '')) if target else tr('未選択：①から保存先を指定してください。'))
        if self.pending_zip:
            self.zip_label.setText(tr('選択済み：')+self.pending_zip.name)
            self.zip_label.setToolTip(str(self.pending_zip))
        elif c.job:
            self.zip_label.setText(tr('選択済み：')+Path(c.request['zip_path']).name)
            self.zip_label.setToolTip(c.request['zip_path'])
        else:
            self.zip_label.setText(tr('ZIPをお持ちでない方は、上の「入手方法」を見てください。'))
        if self.analytics_preview:
            from .analytics import METRIC_LABELS
            p=self.analytics_preview
            post_ids=set(s.get('post_ids',[]))
            target=self.pending_destination or c.root or self.get_root()
            catalog=target/'.system/catalog.sqlite3'
            try:
                from .catalog import read_catalog
                stamp=catalog.stat().st_mtime_ns if catalog.is_file() else 0
                key=(str(target),stamp)
                if key!=self._csv_match_key:
                    self._csv_match_posts={a.post_id for a in read_catalog(target) if a.post_id} if stamp else set()
                    self._csv_match_key=key
                post_ids.update(self._csv_match_posts)
            except Exception:
                pass
            matched=len({r['post_id'] for r in p.rows}&post_ids)
            self.csv_summary.setText(trf('{0}\n投稿日 {1} ～ {2}\n{3:,}投稿 · 照合予定 {4:,} · 未照合 {5:,}\n認識した指標: ', self.pending_csv.name, p.period_start[:10], p.period_end[:10], p.post_count, matched, p.post_count - matched)+', '.join(tr(METRIC_LABELS[m]) for m in p.recognized_metrics)+(tr('\n同じCSVは取り込み済みです。二重登録せず、照合を更新します。') if p.already_imported else tr('\n取り込み後、投稿IDで作品と紐付けて高成績タグを更新します。')))
            self.csv_summary.show()
        else:
            self.csv_summary.setText(tr('CSVは任意です。アーカイブと一緒に選ぶと、1回の実行で両方を取り込めます。'))
        if s:
            dates=(s.get('media_min') or '')[:10]+' ～ '+(s.get('media_max') or '')[:10]
            account='@'+s['username'] if s.get('username') else 'ID '+(s.get('owner') or tr('確認できません'))
            text=trf('保存対象 {0:,}ファイル\n対象作品の投稿日 {1}\nアカウント {2}\n注意 {3:,}件 / エラー {4:,}件', s['total'], dates, account, s['warnings'], s['errors'])
            compact_confirmation=self.onboarding and c.phase=='ready'
            if compact_confirmation:
                text=trf('{0} · 保存対象 {1:,}ファイル · 注意 {2:,}件 / エラー {3:,}件\n投稿日 {4}', account, s['total'], s['warnings'], s['errors'], dates)
            library=c.store.library(c.root)
            known=c.store.get('account:'+library)
            if not known and not compact_confirmation:
                text+=tr('\n初回のため、アカウントと保存先を確認してください。')
            elif known and s.get('owner') and known!=s['owner']:
                text+=tr('\n別アカウントのZIPです。この保存先には取り込めません。')
                self.start.setEnabled(False)
            r=c.result.get('result')
            if r:
                text+=trf('\n\n新規 {0:,} / 既存確認 {1:,}\n処理済み {2:,} / {3:,}', r['images'] + r['gifs'] + r['videos'], r['skipped'], r['checked'], r['total'])
            self.summary.setText(text)
        else:
            h=self.history
            if h:
                from .backup_ui import display_date
                done=h.get('last_complete')
                self.summary.setText(tr('現在のライブラリ\n最新収録投稿日 ')+display_date(h.get('latest'),True)+trf('\n保存 {0:,}ファイル\n注意 {1:,}件 / エラー {2:,}件', h['count'], h['warnings'], h['errors'])+tr('\n前回完了 ')+(display_date(done['finished_at'],True) if done else tr('未記録')))
            else:
                self.summary.clear()
        # The persisted status is only a fallback while idle. Reset clears it
        # immediately, so a stale panel snapshot must never resurrect issues.
        if c.phase=='idle':
            issues=[]
        else:
            issues=c.result.get('result',{}).get('issues',s.get('issues',self.history.get('issues',[])))
        key=(c.job_id,c.phase,len(issues))
        if key!=self._detail_key:
            self._detail_key=key
            self.issues.setPlainText('\n\n'.join(f"{i['level']} · {i.get('date') or '日付不明'}\n{i.get('source','')}\n{i['reason']}" for i in issues))
        self.details_button.setVisible(bool(issues))
        if not issues:
            self.issues.hide()
        self.render_setup()

    def update_progress_meter(self):
        c=self.controller
        self.progress.setVisible(c.active or self.analytics_busy or self.preview_busy)
        self.progress.setRange(0,0 if self.analytics_busy or self.preview_busy else c.progress[1])
        self.progress.setValue(c.progress[0])

    def resizeEvent(self,event):
        super().resizeEvent(event)
        if hasattr(self,'setup_actions') and self.onboarding:
            QTimer.singleShot(0,self.fit_setup_contents)
