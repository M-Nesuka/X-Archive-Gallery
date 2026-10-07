"""Gallery integration hooks kept separate from artwork navigation."""
from .i18n import tr,trf,error_text
from datetime import datetime
from pathlib import Path
from PySide6.QtCore import QTimer, Qt, QPointF
from PySide6.QtGui import QPainter,QPen,QColor
from PySide6.QtWidgets import QFrame,QHBoxLayout,QLabel,QPushButton,QSizePolicy,QMessageBox,QFileDialog,QCheckBox,QStyleOptionButton,QStyle
from .import_panel import ImportPanel
from .catalog import JST
from .appearance import theme_color


def display_date(value, seconds=False):
    if not value:
        return tr('未記録')
    try:
        dt=datetime.fromisoformat(value.replace('Z','+00:00'))
        dt=(dt if dt.tzinfo else dt.replace(tzinfo=JST)).astimezone(JST)
        return dt.strftime('%Y/%m/%d %H:%M' if seconds else '%Y/%m/%d')
    except (ValueError,TypeError):
        return tr('不明')


class SubtleDuplicateCheckBox(QCheckBox):
    """Paint the check stroke directly so it never depends on Unicode fonts."""
    def paintEvent(self,event):
        super().paintEvent(event)
        if self.isChecked():
            option=QStyleOptionButton();self.initStyleOption(option)
            rect=self.style().subElementRect(QStyle.SubElement.SE_CheckBoxIndicator,option,self)
            painter=QPainter(self);painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            painter.setPen(QPen(QColor(theme_color('#b3b9bf')),1.5,Qt.PenStyle.SolidLine,Qt.PenCapStyle.RoundCap,Qt.PenJoinStyle.RoundJoin))
            painter.drawPolyline([QPointF(rect.left()+3,rect.center().y()),
                QPointF(rect.left()+5.5,rect.bottom()-3),QPointF(rect.right()-2,rect.top()+3)])
            painter.end()


class BackupUiMixin:
    def build_backup_strip(self, layout):
        strip=QFrame()
        self.backup_strip=strip
        strip.setObjectName('backupStrip')
        row=QHBoxLayout(strip)
        row.setContentsMargins(20,3,18,3)
        row.setSpacing(12)
        self.latest_post=QLabel(tr('最新収録投稿日  —'))
        self.latest_post.setObjectName('latestPost')
        self.latest_post.setSizePolicy(QSizePolicy.Policy.Minimum,QSizePolicy.Policy.Preferred)
        row.addWidget(self.latest_post)
        self.last_import=QLabel(tr('前回取り込み  —'))
        self.last_import.setObjectName('muted')
        self.last_import.setWordWrap(False)
        row.addWidget(self.last_import)
        self.saved_count=QLabel(tr('保存  —'))
        self.saved_count.setObjectName('muted')
        self.saved_count.setSizePolicy(QSizePolicy.Policy.Minimum,QSizePolicy.Policy.Preferred)
        row.addWidget(self.saved_count)
        row.addStretch()
        self.warning_button=QPushButton(tr('確認中'))
        self.warning_button.clicked.connect(self.open_issue_gallery)
        row.addWidget(self.warning_button)
        self.group_button=SubtleDuplicateCheckBox()
        self.group_button.setObjectName('duplicateSubtle')
        self.group_button.setChecked(self.group_duplicates)
        self.group_button.setToolTip(tr('起動時はON。完全に同じ内容のみをまとめ、投稿記録と元ファイルは残します。'))
        self.update_group_button_label(self.group_duplicates)
        self.group_button.toggled.connect(self.toggle_grouping)
        row.addWidget(self.group_button)
        layout.addWidget(strip)

    def build_import_panel(self, layout):
        self.import_panel=ImportPanel(self.importer,lambda:self.root,self.open_analytics_csv_import)
        self.analytics_status=self.import_panel.analytics_status
        self.analytics_import_button=self.import_panel.analytics_import_button
        self.import_panel.closed.connect(self.close_import)
        self.import_panel.hide()
        layout.addWidget(self.import_panel)

    def choose_combined_csv(self):
        panel=self.import_panel
        if self.importer.active or panel.analytics_busy or panel.preview_busy:return
        if self.aggregate_entries and not panel.pending_zip and not self.require_single_account():return
        path,_=QFileDialog.getOpenFileName(self,tr('X Analytics CSVを選択'),str(Path.home()),tr('CSVファイル (*.csv)'))
        if path:self.stage_combined_csv(path)

    def stage_combined_csv(self,path):
        panel=self.import_panel
        if panel.analytics_busy or panel.preview_busy:return
        if self.importer.phase not in ('ready','analyzing') and self.library_configured:
            panel.pending_zip=None
        panel.pending_csv=Path(path).resolve()
        panel.analytics_preview=None;panel.analytics_error='';panel.combined_message=''
        panel.preview_busy=True;panel.update_state()
        from .analytics_job import AnalyticsJob
        job=AnalyticsJob(panel.pending_csv,[])
        self.analytics_preview_job=job
        job.signals.done.connect(self.combined_csv_previewed)
        self.jobs.start(job)

    def combined_csv_previewed(self,preview,error):
        if self.closing:return
        panel=self.import_panel;panel.preview_busy=False
        if error:
            panel.analytics_error=tr('CSVを確認できません。')+error
        else:
            panel.analytics_preview=preview
            if not preview.can_import:
                reasons=[]
                if preview.invalid_rows:reasons.extend(preview.invalid_rows[:3])
                if preview.duplicate_post_ids:reasons.append(trf('投稿ID重複 {0:,}件', len(preview.duplicate_post_ids)))
                panel.analytics_error=tr('このCSVは取り込めません。')+ ' / '.join(reasons)
            target=panel.pending_destination or self.root
            if self.library_configured and target.resolve()==self.root.resolve():
                preview.already_imported=self.store.analytics_hash_imported(self.library_id,preview.file_sha256)
        panel.update_state()

    def start_combined_import(self):
        panel=self.import_panel
        if not panel.start.isEnabled():return
        panel.combined_message=''
        if self.importer.phase=='ready' and panel.pending_zip:
            panel.awaiting_analytics=panel.pending_csv is not None
            self.importer.start_backup()
            if not self.importer.active:panel.awaiting_analytics=False
        elif panel.analytics_preview and self.library_configured:
            if not self.require_single_account():return
            self.apply_combined_csv()

    def apply_combined_csv(self):
        panel=self.import_panel
        if panel.analytics_busy or not panel.analytics_preview:return
        panel.analytics_busy=True;panel.analytics_error='';panel.awaiting_analytics=False
        panel.update_state()
        from .analytics_job import AnalyticsJob
        job=AnalyticsJob(panel.pending_csv,self.assets,directory=self.store.directory,
                         root=self.root,expected_hash=panel.analytics_preview.file_sha256,keep_csv=panel.keep_csv.isChecked())
        self.analytics_apply_job=job
        job.signals.done.connect(self.combined_csv_applied)
        self.jobs.start(job)

    def combined_csv_applied(self,result,error):
        if self.closing:return
        panel=self.import_panel;panel.analytics_busy=False
        if error:
            panel.analytics_error=tr('アーカイブは保持されています。Analyticsを取り込めませんでした: ')+error
            panel.pending_zip=None
        else:
            summary=result['summary']
            panel.combined_message=(tr('CSVは取り込み済みのため照合を更新しました。') if result['repeated'] else tr('Analyticsの取り込みが完了しました。'))+trf('\n{0:,} posts · 照合 {1:,} · 未照合 {2:,}', summary['post_count'], summary['matched_posts'], summary['unmatched_posts'])
            panel.analytics_preview.already_imported=True
            if result.get('saved_csv'):
                panel.combined_message+=tr('\n元CSVをバックアップ内のAnalyticsフォルダーに保存しました。')
            self.update_analytics_status();self.apply_filters()
            if self.current:self.update_performance_details(self.current)
            self.toast(panel.combined_message)
            panel.pending_zip=None
        panel.update_state()

    def open_issue_gallery(self):
        if not self.require_single_account():return
        issues=self.backup_status.get('issues') or self.importer.summary.get('issues') or []
        fallback=self.importer.request.get('zip_path') if hasattr(self.importer,'request') else None
        issues=[dict(issue,zip_path=issue.get('zip_path') or fallback) for issue in issues]
        if not issues:
            QMessageBox.information(self,tr('確認事項'),tr('現在表示できる確認事項はありません。'))
            return
        from .issues_viewer import IssueGallery
        IssueGallery(issues,self.store.directory,self,library_root=self.root,on_added=self.warning_assets_added).exec()

    def open_import(self):
        self.discovery_panel.hide()
        self.close_large()
        self.details.hide()
        self.import_panel.set_onboarding(not self.library_configured or self.import_panel.onboarding)
        self.gallery.setVisible(not self.import_panel.onboarding)
        for widget in (self.backup_strip,self.gallery_toolbar,self.app_footer,self.search,self.refresh_button):
            widget.setVisible(not self.import_panel.onboarding)
        self.import_panel.update_state()
        self.import_panel.show()
        self.import_button.setText(tr('取り込みを閉じる'))

    def toggle_import_panel(self):
        if self.import_panel.isVisible():
            self.close_import()
        else:
            self.open_import()

    def close_import(self):
        self.import_panel.set_onboarding(False)
        self.import_panel.hide()
        self.gallery.show()
        for widget in (self.backup_strip,self.gallery_toolbar,self.app_footer,self.search,self.refresh_button):widget.show()
        self.import_button.setText(tr('取り込み状況を表示') if self.importer.active else tr('アーカイブを取り込む'))
        if self.current:
            self.details.show()

    def update_backup_status(self, value):
        self.backup_status=value
        date=display_date(value.get('latest')) if value.get('latest') else tr('未収録')
        self.latest_post.setText(tr('最新収録  ')+date)
        self.latest_post.setToolTip(tr('保存済み作品の最新投稿日（日本時間）: ')+display_date(value.get('latest'),True)+tr('\nこの日までの全投稿の完全性を保証する日付ではありません。'))
        done=value.get('last_complete')
        self.last_import.setText(tr('前回 ')+(display_date(done['finished_at']) if done else tr('未記録')))
        self.last_import.setToolTip(tr('前回取り込み ')+(display_date(done['finished_at'],True) if done else tr('未記録')))
        self.saved_count.setText(trf('保存  {0:,}件', value.get('count', 0)))
        warnings=value.get('warnings',0)
        errors=value.get('errors',0)
        self.warning_button.setText(trf('注意 {0:,}件', warnings)+(trf(' / エラー {0:,}件', errors) if errors else ''))
        tip=tr('前回の取り込み結果を確認')
        attempt=value.get('last_attempt')
        if attempt and attempt['status'] in ('errors','cancelled','running'):
            names={'errors':tr('失敗あり'),'cancelled':tr('中止'),'running':tr('完了未確認')}
            self.warning_button.setText(self.warning_button.text()+' · '+names[attempt['status']])
            tip=tr('直近の試行は')+names[attempt['status']]+tr('です。前回完了日時と区別して表示しています。')
        if done and done.get('status')=='warnings':
            tip+=tr('\n前回の完了には注意事項があります。')
        if value.get('unfinished'):
            tip+=trf('\n完了記録のない処理: {0}件。同じZIPでの再実行が必要です。', value['unfinished'])
        self.warning_button.setToolTip(tip)
        self.import_panel.history=value
        self.import_panel.update_state()
        self.backup_strip.layout().activate()

    def update_analytics_status(self):
        if self.aggregate_entries:
            self.performance_by_post={}
            summaries=[]
            for entry,_raw,_status in self.load_job.bundles:
                lid=entry['library_id']
                self.performance_by_post.update({lid+'|'+post:record for post,record in self.store.analytics_performance_map(lid).items()})
                summary=self.store.analytics_summary(lid)
                if summary:summaries.append(summary)
        else:
            self.performance_by_post=self.store.analytics_performance_map(self.library_id)
        if hasattr(self,'gallery'):
            self.gallery.set_performance_tags({post_id:record['tag_badges']
                                               for post_id,record in self.performance_by_post.items()})
        summary=self.store.analytics_summary(self.library_id) if self.library_id else None
        if self.aggregate_entries:
            self.import_panel.set_analytics_status(trf('{0}ライブラリ · ', len(summaries))+f"{sum(s['post_count'] for s in summaries):,} posts",
                tr('順位はライブラリごとに判定します。CSVを追加するときは、対応する @アカウントを先に選択してください。'))
            return
        if not summary:
            self.import_panel.set_analytics_status(tr('未取り込み'),tr('X Analytics CSVはまだ取り込まれていません。'))
            return
        end=summary.get('cumulative_period_end') or tr('不明')
        try:
            end=datetime.fromisoformat(end).strftime('%Y/%m/%d')
        except ValueError:
            pass
        self.import_panel.set_analytics_status(trf('累積 {0:,} posts · {1}まで', summary['cumulative_post_count'], end),
            trf('保存済みの全投稿から、投稿ごとの最新成績で上位10%・NO.1を判定します。\n最新CSV: {0:,} posts · 照合 {1:,}\nCSV期間 {2} ～ {3}\n未照合 {4:,} posts\nファイル {5}\nCSV内のorganic / promoted区分: {6}', summary['post_count'], summary['matched_posts'], summary.get('period_start') or '不明', summary.get('period_end') or '不明', summary['unmatched_posts'], summary['source_filename'], 'あり' if summary['scope'] == 'organic_promoted_columns' else 'なし'))

    def open_analytics_csv_import(self):
        self.open_import()
        self.choose_combined_csv()

    def import_activity(self, active):
        self.thumbs.paused=active or getattr(self,'_minimized_idle',False)
        self.analytics_import_button.setEnabled(not active and not self.loading)
        self.import_button.setText((tr('取り込みを閉じる') if self.import_panel.isVisible() else tr('取り込み状況を表示')) if active else tr('アーカイブを取り込む'))
        if active:
            self.progress.setText(tr('アーカイブを処理中…'))
        else:
            self.thumbs.report()
        self.refresh_button.setEnabled(not active and not self.loading)

    def import_changed(self):
        if self.importer.active:
            self.progress.setText(tr('Xのデータを確認中…') if self.importer.phase=='analyzing' else tr('作品を保存中…'))

    def import_completed(self, result):
        self.toast(self.importer.message)
        target=self.importer.root or self.root
        if not result.get('ok') or self.importer.phase not in ('complete','warnings'):
            self.import_panel.awaiting_analytics=False
        if (target/'.system/catalog.sqlite3').is_file():
            self.refresh(target)
        elif not self.library_configured:
            self.refresh()
        if self.exit_after_import:
            self.import_panel.awaiting_analytics=False
            QTimer.singleShot(50,self.close)
