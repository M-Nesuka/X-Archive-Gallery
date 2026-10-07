"""A spacious first-run presentation of the existing import controller."""
from .i18n import tr,trf
from .appearance import theme_css
from PySide6.QtCore import Qt,QTimer
from PySide6.QtWidgets import QWidget,QHBoxLayout,QLabel,QPushButton,QBoxLayout,QSpacerItem,QSizePolicy

class SetupPresentation:
    def refresh_appearance(self):
        self.setup_update_guide.setStyleSheet(theme_css('color:#c8c1d2; background:#211d29; padding:16px; border-radius:8px; font-size:16px;'))
        self.setStyleSheet(theme_css('''QLabel { font-size:16px; } QLabel#muted, QLabel#field { font-size:16px; }
            QLabel#setupHeading { font-size:30px; font-weight:600; color:#eeebf4; }
            QLabel#setupLead { font-size:18px; color:#bfb6cc; }
            QPushButton { font-size:16px; padding:10px 12px; }
            QPushButton#setupClose { font-size:18px; padding:0; }''' if self.onboarding else ''))
        if self.onboarding:
            for i,item in enumerate(self.step_labels,1):
                item.setStyleSheet(theme_css('font-size:16px; padding:12px 6px; border-radius:6px; '+('background:#2b2437; color:#e5d4ff;' if i==self.setup_step else 'color:#9c95a5;')))

    def build_setup_presentation(self):
        self.onboarding=False;self.setup_step=1;self.setup_override=None
        self.normal_analytics_explanation=self.analytics_explanation.text()
        self.setup_steps=QWidget();row=QHBoxLayout(self.setup_steps)
        row.setContentsMargins(40,12,40,12);row.setSpacing(12)
        self.step_labels=[]
        for text in (tr('① 保存場所'),tr('② Xのデータ'),tr('③ 成績・任意'),tr('④ ギャラリー')):
            item=QLabel(text);item.setAlignment(Qt.AlignmentFlag.AlignCenter)
            row.addWidget(item,1);self.step_labels.append(item)
        self.outer_layout.insertWidget(1,self.setup_steps);self.setup_steps.hide()
        self.setup_heading=QLabel();self.setup_heading.setObjectName('setupHeading');self.setup_heading.setWordWrap(True)
        self.setup_lead=QLabel();self.setup_lead.setObjectName('setupLead');self.setup_lead.setWordWrap(True)
        self.content_layout.insertWidget(0,self.setup_heading)
        self.content_layout.insertWidget(1,self.setup_lead)
        self.setup_update_guide=QLabel(
            tr('<b>後からの更新も、かんたんです</b><br><br>画面右上の「アーカイブを取り込む」から追加・更新できます。<br><br><b>作品：</b>新しいXのデータZIPを選びます。保存済みの作品は残ります。<br><br><b>成績：</b>直近1か月などのAnalytics CSVでOK。<br>保存済みの過去分と合わせて、高成績・NO.1タグを更新します。<br>Analyticsは任意です。後から追加しても大丈夫です。'))
        self.setup_update_guide.setObjectName('setupUpdateGuide')
        self.setup_update_guide.setWordWrap(True)
        self.setup_update_guide.setTextFormat(Qt.TextFormat.RichText)
        self.setup_update_guide.setMinimumWidth(0)
        self.setup_update_guide.setSizePolicy(QSizePolicy.Policy.Ignored,QSizePolicy.Policy.Preferred)
        self.setup_update_guide.setStyleSheet(theme_css('color:#c8c1d2; background:#211d29; padding:16px; border-radius:8px; font-size:16px;'))
        self.content_layout.insertWidget(self.content_layout.indexOf(self.progress)+1,self.setup_update_guide)
        self.setup_update_guide.hide()
        self.setup_zip_how=QLabel(tr('ZIPをまだ持っていない方へ\n\n1. Xの「設定とプライバシー」→「アカウント」から、データのアーカイブを申し込みます。\n2. 準備完了のメール・通知を待ちます。数日かかることもあります。\n3. XからZIPをPCに保存し、上の②で選びます。解凍は不要です。'))
        self.setup_zip_how.setWordWrap(True);self.setup_zip_how.setObjectName('setupLead')
        self.content_layout.insertWidget(self.content_layout.indexOf(self.archive_help_button),self.setup_zip_how)
        self.setup_existing=QPushButton(tr('保存済みの作品がある方はこちら'))
        self.setup_existing.clicked.connect(lambda:self.window().choose_library())
        self.content_layout.insertWidget(self.content_layout.indexOf(self.destination)+1,self.setup_existing)
        self.setup_back=QPushButton(tr('← 前の手順に戻る'))
        self.setup_back.clicked.connect(self.previous_setup_step)
        self.setup_actions=QWidget()
        self.setup_action_row=QHBoxLayout(self.setup_actions)
        self.setup_action_row.setContentsMargins(0,0,0,0)
        self.setup_action_row.setSpacing(12)
        self.setup_action_row.addWidget(self.setup_back)
        self.setup_action_row.addStretch()
        self.normal_skip_index=self.content_layout.indexOf(self.skip_analytics_button)
        self.outer_layout.addWidget(self.setup_actions)
        self.setup_tail=QSpacerItem(0,0,QSizePolicy.Policy.Minimum,QSizePolicy.Policy.Fixed)
        self.outer_layout.addItem(self.setup_tail)
        self.setup_actions.hide()
        for widget in (self.setup_heading,self.setup_lead,self.setup_zip_how,self.setup_existing,self.setup_back):widget.hide()

    def set_onboarding(self,enabled):
        if self.onboarding==enabled:return
        self.onboarding=enabled;self.setup_override=None
        # A bounded scroll area keeps actions near short guides while ensuring
        # they remain in view when CSV details are long.
        for widget in (self.start,self.view_gallery_button):
            if enabled:
                self.outer_layout.removeWidget(widget)
                self.setup_action_row.insertWidget(0,widget)
            else:
                self.setup_action_row.removeWidget(widget)
                self.outer_layout.addWidget(widget)
        if enabled:
            self.content_layout.removeWidget(self.skip_analytics_button)
            self.setup_action_row.insertWidget(self.setup_action_row.indexOf(self.setup_back),self.skip_analytics_button)
        else:
            self.setup_action_row.removeWidget(self.skip_analytics_button)
            self.content_layout.insertWidget(self.normal_skip_index,self.skip_analytics_button)
            self.scroll.setMinimumHeight(0);self.scroll.setMaximumHeight(16777215)
        self.outer_layout.setStretch(self.outer_layout.indexOf(self.scroll),0 if enabled else 1)
        self.setup_tail.changeSize(0,0,QSizePolicy.Policy.Minimum,QSizePolicy.Policy.Expanding if enabled else QSizePolicy.Policy.Fixed)
        self.setup_action_row.setContentsMargins(40,6,40,10) if enabled else self.setup_action_row.setContentsMargins(0,0,0,0)
        self.setup_actions.setVisible(enabled)
        self.analytics_row.setDirection(QBoxLayout.Direction.TopToBottom if enabled else QBoxLayout.Direction.LeftToRight)
        self.analytics_row.setStretch(0,0 if enabled else 1)
        self.analytics_row.setAlignment(self.analytics_import_button,Qt.AlignmentFlag.AlignLeft if enabled else Qt.AlignmentFlag(0))
        self.setMaximumWidth(16777215 if enabled else 440)
        self.content_layout.setContentsMargins(40,16,40,16) if enabled else self.content_layout.setContentsMargins(14,16,14,18)
        self.content_layout.setSpacing(12 if enabled else 14)
        self.setStyleSheet(theme_css('''QLabel { font-size:16px; } QLabel#muted, QLabel#field { font-size:16px; }
            QLabel#setupHeading { font-size:30px; font-weight:600; color:#eeebf4; }
            QLabel#setupLead { font-size:18px; color:#bfb6cc; }
            QPushButton { font-size:16px; padding:10px 12px; }
            QPushButton#setupClose { font-size:18px; padding:0; }''' if enabled else ''))
        for widget in (self.choose_destination_button,self.choose,self.archive_help_button,self.setup_existing,self.analytics_import_button,self.skip_analytics_button,self.retry,self.clear_csv_button):
            widget.setMaximumWidth(640 if enabled else 16777215)
            self.content_layout.setAlignment(widget,Qt.AlignmentFlag.AlignLeft if enabled else Qt.AlignmentFlag(0))
        for widget in (self.start,self.view_gallery_button):
            widget.setMaximumWidth(400 if enabled else 16777215)
        self.content_layout.setAlignment(self.setup_actions,Qt.AlignmentFlag.AlignLeft)
        self.setup_steps.setVisible(enabled)
        self.setup_help.setVisible(enabled)
        self.import_note.setVisible(not enabled)
        self.analytics_explanation.setText(tr('投稿の数値から、高成績・NO.1タグが自動で付きます。\nXの「コンテンツ（投稿別）」CSVが対象です。\n取得にはX Premiumなどの利用権限が必要です。後から追加できます。\n画像内容のAI解析ではありません。') if enabled else self.normal_analytics_explanation)
        if not enabled:
            self.setup_update_guide.hide()
            for widget in (self.setup_heading,self.setup_lead,self.setup_zip_how,self.setup_existing,self.setup_back):widget.hide()
            for widget in (self.choose_destination_button,self.choose,self.destination,self.zip_label,self.archive_explanation,self.archive_help_button,self.analytics_header,self.analytics_explanation,self.analytics_status,self.analytics_import_button,self.keep_csv,self.csv_summary,self.summary,self.message):widget.show()
            self.skip_analytics_button.setText(tr('今はスキップ'))
        self.update_state()

    def previous_setup_step(self):
        if self.controller.active or self.analytics_busy or self.preview_busy:return
        self.setup_override=max(1,min(3,self.setup_step-1));self.update_state()

    def start_selected_import(self):
        self.setup_override=None;self.window().start_combined_import()

    def skip_clicked(self):
        start=self.onboarding and self.setup_step==3
        self.skip_analytics()
        if start:self.start_selected_import()

    def render_setup(self):
        if not self.onboarding:return
        c=self.controller;busy=c.active or self.analytics_busy
        waiting=busy or self.awaiting_analytics or getattr(self.window(),'loading',False)
        complete=c.phase in ('complete','warnings','errors','cancelled')
        step=4 if (busy and c.phase!='analyzing') or complete else (3 if c.phase=='ready' else (2 if self.pending_destination else 1))
        if self.setup_override and not busy:step=self.setup_override
        self.setup_step=step
        headings={1:(tr('作品の保存場所を選びましょう'),tr('画像や動画を保存するフォルダーです。\n好きなドライブや外付けドライブを選べます。')),
                  2:(tr('Xの投稿・画像を取り込みましょう'),tr('Xから受け取ったZIPを選びます。\nまだ持っていない方は、下の入手方法をご覧ください。')),
                  3:(tr('投稿の成績も追加しますか？'),tr('任意です。なしでも作品の閲覧・タグ付け・お気に入りが使えます。')),
                  4:(tr('作品を保存しています…') if busy else (tr('ギャラリーを準備しています…') if waiting else tr('ギャラリーの準備ができました')),tr('このまま完了を待ちましょう。') if waiting else tr('下の「ギャラリーを見る」で、作品を眺めてみましょう。'))}
        if step==4 and c.phase in ('errors','cancelled'):
            headings[4]=(tr('取り込み結果を確認しましょう'),tr('下の説明をご確認ください。前の手順へ戻って、やり直すこともできます。'))
        if busy and c.phase=='analyzing':
            headings[2]=(tr('Xのデータを確認しています…'),tr('画像や動画が多いと、少し時間がかかります。このままお待ちください。'))
        self.setup_heading.setText(headings[step][0]);self.setup_lead.setText(headings[step][1])
        self.content_layout.setSpacing(10 if step==3 else 12)
        self.setup_heading.show();self.setup_lead.show()
        for i,item in enumerate(self.step_labels,1):
            item.setStyleSheet(theme_css('font-size:16px; padding:12px 6px; border-radius:6px; '+('background:#2b2437; color:#e5d4ff;' if i==step else 'color:#9c95a5;')))
        groups=((self.choose_destination_button,self.destination,self.setup_existing),
                (self.choose,self.archive_explanation,self.zip_label,self.archive_help_button,self.setup_zip_how),
                (self.analytics_header,self.analytics_explanation,self.analytics_status,self.analytics_import_button,self.keep_csv,self.csv_summary))
        for wanted,widgets in enumerate(groups,1):
            for widget in widgets:widget.setVisible(step==wanted and not busy)
        self.setup_update_guide.setVisible(waiting)
        self.message.setVisible(step in (2,4) or bool(self.destination_error or self.analytics_error))
        self.summary.setVisible(step in (3,4) and not waiting)
        self.clear_csv_button.setVisible(step==3 and self.pending_csv is not None)
        self.skip_analytics_button.setVisible(step==3);self.skip_analytics_button.setText(tr('今はスキップして取り込む'))
        self.retry.setVisible(step==2 and bool(self.pending_zip and self.pending_destination) and not busy and c.phase!='ready')
        self.reset_button.hide()
        self.preview_issues.setVisible(step in (3,4) and bool(c.summary.get('issues',[]) or c.result.get('result',{}).get('issues',[])))
        self.details_button.setVisible(step==4 and bool(c.result.get('result',{}).get('issues',[])))
        self.setup_back.setVisible(step>1 and not busy);self.setup_back.setEnabled(not self.preview_busy)
        self.start.setVisible(step==3)
        self.view_gallery_button.setVisible(step==4 and getattr(self.window(),'library_configured',False) and not busy and not getattr(self.window(),'loading',False))
        if step!=self._painted_setup_step:
            self.scroll.verticalScrollBar().setValue(0);self._painted_setup_step=step
        QTimer.singleShot(0,self.fit_setup_contents)

    def fit_setup_contents(self):
        if not self.onboarding:return
        outer=self.outer_layout
        fixed=sum(outer.itemAt(i).sizeHint().height() for i in range(outer.count())
                  if outer.itemAt(i).widget() is not self.scroll and outer.itemAt(i).spacerItem() is None)
        available=max(90,self.height()-fixed-max(0,outer.count()-1)*outer.spacing())
        width=max(1,self.scroll.viewport().width())
        desired=self.content_layout.totalHeightForWidth(width)
        if desired<0:desired=self.content_layout.sizeHint().height()
        height=min(available,max(90,desired+2))
        if self.scroll.minimumHeight()!=height:self.scroll.setFixedHeight(height)
