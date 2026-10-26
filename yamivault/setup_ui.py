"""Progressive presentation of the unchanged archive import controller."""
from .i18n import tr
from .appearance import theme_css
from PySide6.QtCore import Qt,QTimer
from PySide6.QtWidgets import QWidget,QHBoxLayout,QVBoxLayout,QLabel,QPushButton,QCheckBox,QFrame,QSpinBox

class SetupPresentation:
    def refresh_appearance(self):
        self.setStyleSheet(theme_css("""QLabel#setupHeading {font-size:28px;font-weight:600;}
            QLabel#setupLead {font-size:17px;}
            QFrame#setupCard {background:#211d29;border:1px solid #3b3344;border-radius:12px;}
            QLabel#setupStepTitle {font-size:18px;font-weight:600;}
            QPushButton#primary {border:1px solid #8a779e;padding:12px 20px;font-size:17px;}
            QLabel#statusCard {background:#211d29;color:#c8c1d2;border-radius:8px;padding:12px;}
            """))

    def build_setup_presentation(self):
        self.onboarding=False;self.setup_step=1;self.setup_override=None
        self.normal_analytics_explanation=self.analytics_explanation.text()
        # Kept as compatibility hooks; the old four-step strip is no longer rendered.
        self.setup_steps=QWidget();self.step_labels=[];self.setup_steps.hide()
        self.setup_heading=QLabel();self.setup_heading.setObjectName('setupHeading');self.setup_heading.setWordWrap(True)
        self.setup_lead=QLabel();self.setup_lead.setObjectName('setupLead');self.setup_lead.setWordWrap(True)
        self.content_layout.insertWidget(0,self.setup_heading);self.content_layout.insertWidget(1,self.setup_lead)
        self.content_layout.insertWidget(2,self.message)
        self.setup_tag_card=QWidget();tag_layout=QHBoxLayout(self.setup_tag_card)
        self.setup_tag_button=QPushButton(tr('タグを作ってみる'))
        self.setup_tag_button.clicked.connect(lambda:(self.window().close_import(),self.window().manage_manual_tags()))
        tag_layout.addWidget(self.setup_tag_button);tag_layout.addStretch();self.content_layout.addWidget(self.setup_tag_card)
        self.setup_update_guide=QLabel(tr('更新は「…」から新しいZIPを追加。Analyticsは直近1か月分でも更新できます。'))
        self.setup_update_guide.setWordWrap(True);self.content_layout.addWidget(self.setup_update_guide)
        self.setup_zip_how=QLabel();self.setup_zip_how.hide()
        self.setup_existing=QPushButton(tr('保存済みの作品を開く…'))
        self.setup_existing.clicked.connect(lambda:self.window().choose_library());self.content_layout.addWidget(self.setup_existing)
        self.setup_back=QPushButton(tr('戻る'));self.setup_back.clicked.connect(self.previous_setup_step)
        self.setup_actions=QWidget();self.setup_action_row=QHBoxLayout(self.setup_actions)
        self.setup_action_row.setContentsMargins(24,8,24,16)
        self.setup_action_row.addWidget(self.setup_back);self.setup_action_row.addStretch()
        self.review_button=QPushButton(tr('内容確認へ'))
        def review():self.setup_override=None;self.update_state()
        self.review_button.clicked.connect(review);self.setup_action_row.addWidget(self.review_button)
        for w in (self.start,self.view_gallery_button):
            self.outer_layout.removeWidget(w);self.setup_action_row.addWidget(w)
        self.outer_layout.addWidget(self.setup_actions)
        self.analytics_toggle=QCheckBox(tr('Analyticsも追加しますか？（任意）'))
        self.analytics_toggle.toggled.connect(lambda:self.update_state())
        self.content_layout.insertWidget(self.content_layout.indexOf(self.analytics_header),self.analytics_toggle)
        self.import_details=QCheckBox(tr('詳細設定・確認事項'))
        self.import_details.toggled.connect(lambda:self.update_state())
        self.content_layout.addWidget(self.import_details)
        self.summary.setObjectName('statusCard')
        self.content_layout.removeWidget(self.summary);self.content_layout.addWidget(self.summary)
        self.choose_destination_button.setText(tr('作品の保存場所を選ぶ'))
        self.choose.setText(tr('XアーカイブZIPを選ぶ'))
        self.view_gallery_button.setText(tr('ギャラリーを見る'))
        self.analytics_header.setText(tr('ANALYTICS（任意）'))
        self.analytics_explanation.setText(tr('投稿の数値から高成績・NO.1タグが付きます。コンテンツ（投稿別）CSVが対象です。後から追加できます。'))
        self.analytics_explanation.setToolTip(self.normal_analytics_explanation)
        self.archive_help_button.setText(tr('？ ZIPの入手方法'))
        self.setup_help.setText(tr('？ 使い方'));self.setup_help.show()
        self.archive_explanation.hide();self.import_note.hide();self.flow_hint.hide()
        self.first_tag_options=QWidget()
        tag_box=QVBoxLayout(self.first_tag_options);tag_box.setContentsMargins(0,0,0,0);tag_box.setSpacing(6)
        discovery_row=QHBoxLayout();tag_box.addLayout(discovery_row)
        self.first_discover=QCheckBox(tr('よく使うハッシュタグを自動登録'))
        self.first_min_posts=QSpinBox();self.first_min_posts.setRange(1,1000000)
        self.first_max_tags=QSpinBox();self.first_max_tags.setRange(0,1000000);self.first_max_tags.setSpecialValueText(tr('制限なし'))
        discovery_row.addWidget(self.first_discover);discovery_row.addWidget(QLabel(tr('最低投稿数')));discovery_row.addWidget(self.first_min_posts)
        discovery_row.addWidget(QLabel(tr('上限の種類数')));discovery_row.addWidget(self.first_max_tags);discovery_row.addStretch()
        self.first_discover.setToolTip(tr('取り込み前に設定できます。後から変更しても、保存済みの投稿文に反映できるのでZIPの読み直しは不要です。'))
        self.first_max_tags.setToolTip(tr('自動登録だけの上限です。指定したタグは上限や投稿数に関係なく対象です。0は制限なし。'))
        self.first_discover.toggled.connect(self.save_first_discovery)
        self.first_min_posts.valueChanged.connect(self.save_first_discovery)
        self.first_max_tags.valueChanged.connect(self.save_first_discovery)
        tag_row=QHBoxLayout();tag_box.addLayout(tag_row);self.first_tag_row=tag_row;tag_row.setContentsMargins(0,0,0,0)
        self.first_tag_configure=QPushButton(tr('投稿文からのタグ付けを設定（任意）'))
        self.first_tag_configure.setObjectName('firstTagConfigure')
        self.first_tag_configure.clicked.connect(self.configure_first_tags)
        tag_row.addWidget(self.first_tag_configure)
        self.first_tag_status=QLabel();tag_row.addWidget(self.first_tag_status);tag_row.addStretch()
        self.content_layout.addWidget(self.first_tag_options)
        self.first_setup=QWidget()
        row=QHBoxLayout(self.first_setup);row.setContentsMargins(0,8,0,8);row.setSpacing(20)
        self.first_cards=[];self.first_titles=[]
        for caption,description in (
            ('STEP 1｜作品の保存先','作品を保存するフォルダを選びます。'),
            ('STEP 2｜Xアーカイブを追加','Xからダウンロードした公式ZIPを選びます。'),
            ('STEP 3｜ギャラリーを作成','選んだ内容を確認して、取り込みを始めます。')):
            card=QFrame();card.setObjectName('setupCard');card.setMinimumHeight(280);box=QVBoxLayout(card)
            box.setContentsMargins(20,22,20,22);box.setSpacing(14)
            title=QLabel(tr(caption));title.setWordWrap(True);title.setObjectName('setupStepTitle')
            hint=QLabel(tr(description));hint.setWordWrap(True)
            box.addWidget(title);box.addWidget(hint)
            row.addWidget(card,1);self.first_cards.append(box);self.first_titles.append(title)
        self.first_summary=QLabel();self.first_summary.setWordWrap(True)
        self.first_summary.setTextFormat(Qt.TextFormat.PlainText)
        self.first_cards[2].addWidget(self.first_summary)
        self.first_setup.hide();self.content_layout.insertWidget(2,self.first_setup)
        self.content_layout.removeWidget(self.setup_existing);self.content_layout.insertWidget(3,self.setup_existing)
        self.first_optional=QWidget();self.first_optional_layout=QVBoxLayout(self.first_optional)
        self.first_optional_layout.setContentsMargins(0,4,0,4);self.first_optional_layout.setSpacing(8)
        self.first_analytics_fields=QWidget();fields=QHBoxLayout(self.first_analytics_fields)
        fields.setContentsMargins(12,0,12,0);fields.setSpacing(20)
        left=QWidget();right=QWidget()
        self.first_analytics_left=QVBoxLayout(left);self.first_analytics_right=QVBoxLayout(right)
        for box in (self.first_analytics_left,self.first_analytics_right):box.setContentsMargins(0,0,0,0);box.setSpacing(8)
        fields.addWidget(left,2);fields.addWidget(right,1)
        self.first_csv_summary=QLabel();self.first_csv_summary.setWordWrap(True);self.first_csv_summary.setTextFormat(Qt.TextFormat.PlainText)
        self.first_analytics_right.addWidget(self.first_csv_summary)
        self.first_optional_layout.addWidget(self.first_analytics_fields)
        self.first_optional.hide();self.content_layout.insertWidget(3,self.first_optional)
        self.content_layout.removeWidget(self.first_tag_options);self.content_layout.insertWidget(4,self.first_tag_options)
        self._first_moved=[]
        self.refresh_appearance()

    def place_first_setup(self,enabled):
        if enabled and not self._first_moved:
            placements=((0,(self.choose_destination_button,self.destination)),
                        (1,(self.choose,self.zip_label,self.archive_help_button)),(2,(self.start,)),
                        (3,(self.analytics_toggle,)),(4,(self.analytics_explanation,self.keep_csv)),
                        (5,(self.analytics_import_button,self.clear_csv_button)),(6,(self.setup_existing,)))
            boxes=self.first_cards+[self.first_optional_layout,self.first_analytics_left,self.first_analytics_right,self.first_tag_row]
            for card,widgets in placements:
                for widget in widgets:
                    original=self.setup_action_row if widget is self.start else self.content_layout
                    self._first_moved.append((widget,original,original.indexOf(widget)))
            for card,widgets in placements:
                for widget in widgets:
                    original=self.setup_action_row if widget is self.start else self.content_layout
                    original.removeWidget(widget)
                    if card==3:boxes[card].insertWidget(0,widget)
                    else:boxes[card].addWidget(widget)
            for box in self.first_cards:box.addStretch()
        elif not enabled and self._first_moved:
            for box in self.first_cards:
                last=box.takeAt(box.count()-1)
                del last
            for widget,original,index in sorted(self._first_moved,key=lambda entry:entry[2]):
                widget.parentWidget().layout().removeWidget(widget)
                original.insertWidget(index,widget)
            self._first_moved=[]
        self.first_setup.setVisible(enabled)
        self.first_optional.setVisible(enabled)

    def set_onboarding(self,enabled):
        self.onboarding=enabled;self.setup_override=None
        self.place_first_setup(enabled)
        for button in (self.choose_destination_button,self.choose,self.start):button.setMinimumHeight(48 if enabled else 0)
        self.destination.setMinimumHeight(72 if enabled else 0)
        self.zip_label.setMinimumHeight(48 if enabled else 0)
        self.first_summary.setMinimumHeight(72 if enabled else 0)
        self.setMaximumWidth(16777215)
        self.content_layout.setContentsMargins(32,24,32,24);self.content_layout.setSpacing(16)
        self.scroll.setMinimumHeight(0);self.scroll.setMaximumHeight(16777215)
        self.refresh_appearance();self.update_state()
        self._setup_fit_mode=None;self.fit_setup_contents()

    def previous_setup_step(self):
        if self.controller.active or self.analytics_busy or self.preview_busy:return
        self.setup_override=2 if self.setup_step==4 else max(1,self.setup_step-1);self.update_state()

    def start_selected_import(self):
        self.setup_override=None;self.window().start_combined_import()

    def skip_clicked(self):
        self.skip_analytics();self.analytics_toggle.setChecked(False)

    def render_setup(self):
        self.first_tag_options.hide()
        if self.onboarding:
            self.render_first_setup();return
        self.setup_actions.show()
        self.choose_destination_button.setText(tr('作品の保存場所を選ぶ'))
        self.choose.setText(tr('XアーカイブZIPを選ぶ'))
        for widget in self.findChildren(QPushButton,'setupClose'):widget.show()
        c=self.controller;busy=c.active or self.analytics_busy or self.preview_busy
        waiting=busy or self.awaiting_analytics or getattr(self.window(),'loading',False)
        complete=c.phase in ('complete','warnings','errors','cancelled')
        csv_only=bool(self.pending_csv and not self.pending_zip and getattr(self.window(),'library_configured',False))
        step=4 if complete or (busy and c.phase!='analyzing' and not self.preview_busy) else 3 if c.phase=='ready' or csv_only else 2 if self.pending_destination else 1
        if self.setup_override and not busy:step=self.setup_override
        self.setup_step=step
        headings={1:(tr('X Archive Galleryへようこそ'),tr('Xのアーカイブから、あなたの作品ギャラリーを作ります。')),
                  2:(tr('XアーカイブZIPを選ぶ'),tr('Xから受け取ったZIPを、そのまま選びましょう。')),
                  3:(tr('内容を確認して、取り込みましょう'),tr('保存先と作品数を確認してください。')),
                  4:(tr('作品を保存しています…') if waiting else tr('ギャラリーの準備ができました'),tr('完了まで、このままお待ちください。') if waiting else tr('作品を見に行きましょう。'))}
        if busy and c.phase=='analyzing':headings[2]=(tr('Xのデータを確認しています…'),tr('完了まで、このままお待ちください。'))
        if step==4 and c.phase in ('error','errors','cancelled'):headings[4]=(tr('取り込み結果を確認しましょう'),tr('確認事項から結果を確認できます。'))
        if not self.onboarding and step==2:headings[2]=(tr('作品を追加・更新する'),tr('保存済みの作品はそのまま。新しいZIPを選びます。'))
        self.setup_heading.setText(headings[step][0]);self.setup_lead.setText(headings[step][1])
        for w in (self.choose_destination_button,self.choose,self.destination,self.zip_label,self.archive_help_button,self.setup_existing,self.summary,self.message,self.retry,self.post_tag_options_button,self.preview_issues,self.details_button,self.import_details,self.setup_tag_card):w.hide()
        self.choose_destination_button.setVisible(step==1 or (step in (2,3) and (self.import_details.isChecked() or c.phase=='error' or bool(self.destination_error))))
        self.setup_existing.setVisible(step==1)
        self.choose.setVisible(step==2 and not busy)
        self.archive_help_button.setVisible(step==2 and not busy)
        self.destination.setVisible(step in (2,3) and not waiting)
        self.zip_label.setVisible(step==3 and bool(self.pending_zip) and not waiting)
        self.summary.setVisible(step in (3,4) and not waiting or bool(self.history) and step==2)
        self.message.setVisible(waiting or bool(self.destination_error or self.analytics_error or self.combined_message) or c.phase in ('error','errors','cancelled') or c.phase=='ready' and not bool(c.summary.get('total')))
        self.retry.setVisible(step in (2,4) and bool(self.pending_zip and self.pending_destination) and not busy and c.phase!='ready')
        self.import_details.setVisible(step in (2,3,4) and not waiting)
        self.post_tag_options_button.setVisible(self.import_details.isChecked() and not waiting)
        issues=bool(c.summary.get('issues',[]) or c.result.get('result',{}).get('issues',[]))
        self.preview_issues.setVisible(issues and not waiting)
        self.details_button.setVisible(issues and self.import_details.isChecked() and not waiting)
        self.issues.setVisible(issues and self.import_details.isChecked() and self.details_button.isChecked())
        allow_analytics=not waiting and ((step==4 and getattr(self.window(),'library_configured',False)) or not self.onboarding and step in (2,3))
        self.analytics_toggle.setVisible(allow_analytics)
        analytics_open=allow_analytics and (self.analytics_toggle.isChecked() or bool(self.pending_csv))
        for w in (self.analytics_header,self.analytics_explanation,self.analytics_status,self.analytics_import_button,self.keep_csv,self.csv_summary):w.setVisible(analytics_open)
        self.skip_analytics_button.setVisible(analytics_open)
        self.clear_csv_button.setVisible(analytics_open and bool(self.pending_csv))
        self.setup_update_guide.setVisible(waiting and self.onboarding)
        self.setup_tag_card.setVisible(step==4 and not waiting and getattr(self.window(),'library_configured',False))
        self.start.setVisible(step==3 or step==4 and bool(self.pending_csv) and not waiting)
        self.view_gallery_button.setVisible(step==4 and getattr(self.window(),'library_configured',False) and not waiting)
        self.review_button.setVisible(step==2 and c.phase=='ready' and not waiting)
        self.highlight_next(self.review_button,True)
        self.highlight_next(self.start,step==3);self.highlight_next(self.choose,step==2 and c.phase!='ready');self.highlight_next(self.choose_destination_button,step==1)
        self.setup_back.setVisible(step>1 and not waiting);self.setup_back.setEnabled(not busy)
        if step!=self._painted_setup_step:self.scroll.verticalScrollBar().setValue(0);self._painted_setup_step=step

    def configure_first_tags(self):
        self.window().open_post_tag_options()
        self.update_state()

    def first_tag_library(self):
        target=self.controller.root if self.pending_zip and self.controller.root else self.pending_destination
        return self.controller.store.library(target) if target and (target/'.system/catalog.sqlite3').is_file() else None

    def save_first_discovery(self,*_):
        if not self.onboarding or self.controller.active or self.analytics_busy:return
        lid=self.first_tag_library();options=self.controller.store.post_tag_options(lid)
        options.update(discover_hashtags=self.first_discover.isChecked(),min_posts=self.first_min_posts.value(),max_tags=self.first_max_tags.value())
        if options['discover_hashtags']:options['hashtags']=True
        self.controller.store.save_post_tag_options(lid,**options)
        self.update_state()

    def render_first_setup(self):
        c=self.controller;busy=c.active or self.analytics_busy or self.preview_busy
        dest=bool(self.pending_destination and not self.destination_error)
        zip_ready=c.phase=='ready' and bool(c.summary.get('total'))
        zip_checked=bool(c.summary.get('total')) and c.phase in ('ready','importing','complete','warnings','errors','cancelled')
        self.setup_step=4 if busy and c.phase!='analyzing' else 3 if zip_ready else 2 if dest else 1
        self.setup_heading.setText(tr('X Archive Galleryへようこそ'))
        self.setup_lead.setText(tr('Xに投稿した画像・GIF・動画から、あなただけの作品ギャラリーを作りましょう。'))
        captions=(tr('STEP 1｜作品の保存先'),tr('STEP 2｜Xアーカイブを追加'),tr('STEP 3｜ギャラリーを作成'))
        for index,title in enumerate(self.first_titles):
            title.setText(('✓ ' if (dest if index==0 else zip_checked if index==1 else False) else '')+captions[index])
        self.choose_destination_button.setText(tr('保存先フォルダを選ぶ'))
        self.choose.setText(tr('アーカイブZIPを選ぶ'))
        self.start.setText(tr('作品とAnalyticsを取り込む') if self.pending_csv else tr('作品の取り込みを開始'))
        for widget in (self.choose_destination_button,self.destination,self.choose,self.zip_label,self.archive_help_button,self.start):widget.show()
        self.destination.setText(str(self.pending_destination).replace('\\','\\\u200b') if dest else tr('まだ選択していません'))
        self.choose.setEnabled(dest and not busy)
        if not self.pending_zip:self.zip_label.setText(tr('ZIPは解凍せず、そのまま選べます。'))
        self.first_summary.setText(tr('完了すると、ギャラリーが自動で開きます。') if busy and c.phase!='analyzing' else tr('まず保存先とZIPを選びましょう。') if not zip_ready else
            tr('保存先とZIPを確認できました。取り込みを開始できます。')+'\n'+str(c.summary.get('total',0))+tr('件の作品'))
        self.highlight_next(self.choose_destination_button,not dest)
        self.highlight_next(self.choose,dest and not zip_ready)
        self.highlight_next(self.start,zip_ready)
        self.destination.setToolTip(str(self.pending_destination or ''))
        self.setup_existing.setVisible(not busy)
        self.message.setVisible(busy or bool(self.destination_error or self.analytics_error or self.combined_message) or c.phase in ('error','errors','cancelled') or c.phase=='ready' and not bool(c.summary.get('total')))
        self.retry.setVisible(not busy and bool(self.pending_zip and self.pending_destination) and (c.phase in ('error','errors','cancelled') or bool(self.destination_error)))
        for widget in (self.summary,self.import_details,self.post_tag_options_button,self.setup_tag_card,
                       self.setup_back,self.review_button,self.view_gallery_button,self.analytics_toggle,
                       self.analytics_header,self.analytics_explanation,self.analytics_status,self.analytics_import_button,
                       self.keep_csv,self.csv_summary,self.clear_csv_button,self.skip_analytics_button,
                       self.preview_issues,self.details_button,self.issues,self.setup_actions):widget.hide()
        for widget in self.findChildren(QPushButton,'setupClose'):widget.hide()
        self.setup_update_guide.setVisible(busy)
        optional_visible=not c.active and not self.analytics_busy and not self.awaiting_analytics
        self.first_optional.setVisible(optional_visible)
        self.analytics_toggle.setText(tr('Analytics CSVを追加（任意）'))
        self.analytics_toggle.setVisible(optional_visible)
        opened=optional_visible and (self.analytics_toggle.isChecked() or bool(self.pending_csv))
        self.first_analytics_fields.setVisible(opened)
        for widget in (self.analytics_explanation,self.analytics_import_button,self.keep_csv):widget.setVisible(opened)
        self.clear_csv_button.setVisible(opened and bool(self.pending_csv))
        self.first_csv_summary.setVisible(opened and bool(self.pending_csv))
        if self.pending_csv:
            label=self.pending_csv.name
            if self.preview_busy:label+='\n'+tr('CSVを確認しています…')
            elif self.analytics_preview:label+='\n'+str(self.analytics_preview.post_count)+tr('件の投稿')
            self.first_csv_summary.setText(label);self.first_csv_summary.setToolTip(str(self.pending_csv))
        self.first_tag_options.setVisible(not busy)
        self.first_tag_configure.setEnabled(not busy)
        lid=self.first_tag_library()
        tags=self.controller.store.post_tag_options(lid)
        for control,value in ((self.first_discover,tags['discover_hashtags']),(self.first_min_posts,tags['min_posts']),(self.first_max_tags,tags['max_tags'])):
            control.blockSignals(True)
            if isinstance(control,QCheckBox):control.setChecked(value)
            else:control.setValue(value)
            control.blockSignals(False)
        self.first_min_posts.setEnabled(tags['discover_hashtags']);self.first_max_tags.setEnabled(tags['discover_hashtags'])
        self.first_tag_status.setText(tr('指定したタグ・探す言葉は、1投稿でも対象です。'))
        self.persist_setup_draft()

    def persist_setup_draft(self):
        draft={'destination':str(self.pending_destination) if self.pending_destination else '',
               'zip':str(self.pending_zip) if self.pending_zip else '',
               'csv':str(self.pending_csv) if self.pending_csv else '', 'keep_csv':self.keep_csv.isChecked()}
        if draft!=getattr(self,'_saved_setup_draft',None):
            self.controller.store.set('first_setup_draft',draft);self._saved_setup_draft=draft

    def fit_setup_contents(self):
        if not self.onboarding:return
        compact=self.height()<760
        mode=(compact,self.width()<1050)
        if mode==getattr(self,'_setup_fit_mode',None):return
        self._setup_fit_mode=mode
        self.content_layout.setContentsMargins(16 if compact else 32,10 if compact else 24,
                                              16 if compact else 32,10 if compact else 24)
        self.content_layout.setSpacing(6 if compact else 16)
        for box in self.first_cards:
            box.parentWidget().setMinimumHeight(190 if compact else 280)
            box.setContentsMargins(12 if compact else 20,12 if compact else 22,
                                  12 if compact else 20,12 if compact else 22)
            box.setSpacing(6 if compact else 14)
        for button in (self.choose_destination_button,self.choose,self.start):button.setMinimumHeight(36 if compact else 48)
        self.destination.setMinimumHeight(36 if compact else 72)
        self.zip_label.setMinimumHeight(32 if compact else 48)
        self.first_summary.setMinimumHeight(40 if compact else 72)
        self.first_tag_row.setDirection(QHBoxLayout.Direction.TopToBottom if mode[1] else QHBoxLayout.Direction.LeftToRight)
        self.first_tag_status.setWordWrap(True)

    def resizeEvent(self,event):
        super().resizeEvent(event)
        if getattr(self,'onboarding',False):QTimer.singleShot(0,self.fit_setup_contents)
