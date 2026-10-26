"""Small settings dialog; ZIP text backfill runs off the UI thread."""
from pathlib import Path
from copy import deepcopy
from PySide6.QtCore import QObject,QRunnable,Signal,Qt
from PySide6.QtWidgets import QDialog,QVBoxLayout,QHBoxLayout,QLabel,QCheckBox,QPlainTextEdit,QPushButton,QFileDialog,QSpinBox,QTabWidget,QWidget,QListWidget,QScrollArea,QStackedWidget
from .i18n import tr,trf,error_text


class PostTextSignals(QObject):
    done=Signal(object,str)


class PostTagApplyJob(QRunnable):
    def __init__(self,directory,library_id,assets,*,create_tags=True):
        super().__init__();self.directory=directory;self.library_id=library_id
        self.assets=list(assets);self.create_tags=create_tags;self.signals=PostTextSignals()

    def run(self):
        store=None;result=None;error=''
        try:
            from .store import VaultStore
            store=VaultStore(self.directory)
            result=store.reconcile_post_tags(self.library_id,self.assets,create_tags=self.create_tags)
        except Exception as exc:
            from .diagnostics import friendly_error
            error=friendly_error(exc,'投稿文の読み込み')
        finally:
            if store:store.close()
        self.signals.done.emit(result,error)


class PostTextJob(QRunnable):
    def __init__(self,directory,root,path):
        super().__init__();self.directory=directory;self.root=root;self.path=path;self.signals=PostTextSignals()

    def run(self):
        store=None
        try:
            from backup_engine.archive import analyze
            from .catalog import read_catalog
            from .store import VaultStore
            plan=analyze(self.path)
            assets=read_catalog(self.root)
            store=VaultStore(self.directory);lid=store.library(self.root)
            owner=store.get('account:'+lid)
            if owner and plan.owner and owner!=plan.owner:
                raise ValueError('別のアカウントのZIPです。表示中のアカウントと同じZIPを選んでください。')
            post_ids={a.post_id for a in assets}
            metadata={pid:record for pid,record in plan.post_metadata.items() if pid in post_ids}
            if not metadata:raise ValueError('このライブラリと一致する投稿文がありません。同じアカウントのZIPを選んでください。')
            store.save_post_text(lid,metadata)
            result=store.reconcile_post_tags(lid,assets+store.warning_assets(lid))
            self.signals.done.emit(result,'')
        except Exception as exc:
            from .diagnostics import friendly_error
            self.signals.done.emit(None,friendly_error(exc,'投稿文の読み込み'))
        finally:
            if store:store.close()


class PostTagOptionsDialog(QDialog):
    def __init__(self,manager=None,*,window=None,library_id=None,root=None):
        super().__init__(manager or window);self.manager=manager;self.window=manager.window if manager else window
        self.store=self.window.store;self.library_id=manager.library_id if manager else library_id;self.busy=False
        self.root=root or self.window.root
        self.setWindowTitle(tr('投稿から自動タグ'));self.resize(820,640);self.setMinimumSize(700,500)
        outer=QVBoxLayout(self)
        self.page_stack=QStackedWidget();outer.addWidget(self.page_stack,1)
        page=QWidget();self.page_stack.addWidget(page);layout=QVBoxLayout(page)
        options=self.store.post_tag_options(self.library_id)
        self._loaded_options=deepcopy(options)
        self.enabled=QCheckBox(tr('投稿文から自動でタグを付ける'))
        self.enabled.setChecked(options['hashtags'] or options['body']);layout.addWidget(self.enabled)
        self.settings=QWidget();settings_layout=QVBoxLayout(self.settings);settings_layout.setContentsMargins(0,8,0,0)
        layout.addWidget(self.settings,1)
        scroll=QScrollArea();scroll.setWidgetResizable(True);settings_layout.addWidget(scroll)
        contents=QWidget();scroll.setWidget(contents);content_layout=QVBoxLayout(contents)
        self.tabs=QTabWidget();content_layout.addWidget(self.tabs,1)
        basic=QWidget();basic_layout=QVBoxLayout(basic)
        self.hashes=QCheckBox(tr('ハッシュタグも登録済みのタグと照合する'));self.hashes.setChecked(options['hashtags']);basic_layout.addWidget(self.hashes)
        self.body=QCheckBox(tr('登録済みタグの名前・別名を本文から探す'));self.body.setChecked(options['body']);basic_layout.addWidget(self.body)
        self.discover=QCheckBox(tr('よく使うハッシュタグを自動登録'));self.discover.setChecked(options['discover_hashtags']);basic_layout.addWidget(self.discover)
        self.discover.setToolTip(tr('ONにした場合だけ、最低投稿数以上のハッシュタグを新しく登録します。登録済みタグや指定キーワードは1投稿でも対象です。'))
        self.discover.toggled.connect(lambda enabled:self.hashes.setChecked(True) if enabled else None)
        self.hashes.toggled.connect(lambda enabled:self.discover.setChecked(False) if not enabled else None)
        from .keyword_rows import KeywordRows
        self.keyword_rows=KeywordRows(options['keywords']);basic_layout.addWidget(self.keyword_rows,1)
        self.keyword_summary=QListWidget();self.keyword_summary.hide()
        self.keyword_button=QPushButton(tr('付けたいタグと、探す言葉を設定…'))
        self.keyword_button.setObjectName('configureKeywordRules');self.keyword_button.setAutoDefault(False)
        self.keyword_button.clicked.connect(self.edit_keyword_rules);self.keyword_button.hide()
        self.tabs.addTab(basic,tr('基本'));self.refresh_keyword_summary()
        detail=QWidget();detail_layout=QVBoxLayout(detail)
        note=QLabel(tr('登録済みタグは1投稿でも対象です。自動登録の条件は下で変更できます。'))
        note.setWordWrap(True);detail_layout.addWidget(note)
        note.setToolTip(tr('日本語1文字・英数字2文字以下は本文から探しません。ハッシュタグの完全一致は使えます。'))
        self.tidy=QCheckBox(tr('以前の自動生成タグを整理する（未使用のものだけ）'));self.tidy.setChecked(options['tidy']);detail_layout.addWidget(self.tidy)
        self.tidy.setToolTip(tr('手動で付けたタグ、編集したタグ、指定キーワードは残します。'))
        self.tidy.setVisible(any(r.get('created') for r in self.store.post_tag_rules(self.library_id).values()) if self.library_id else False)
        self.excluded=QPlainTextEdit();self.excluded.setObjectName('excludedPostTags')
        self.excluded.setPlainText('\n'.join(options['excluded']));self.excluded.setPlaceholderText(tr('除外したいハッシュタグを入力（任意）'))
        detail_layout.addWidget(QLabel(tr('取り込まないハッシュタグ（1行に1つ）')));detail_layout.addWidget(self.excluded,1)
        self.excluded.setToolTip(tr('除外は完全一致です。手動で付けたタグは残ります。別名は各タグの編集画面で登録できます。'))
        self.discovery_limits=QWidget();limits=QHBoxLayout(self.discovery_limits);limits.setContentsMargins(0,0,0,0)
        self.min_posts=QSpinBox();self.min_posts.setRange(1,1000000);self.min_posts.setValue(options['min_posts'])
        self.max_tags=QSpinBox();self.max_tags.setRange(0,1000000);self.max_tags.setValue(options['max_tags']);self.max_tags.setSpecialValueText(tr('制限なし'))
        limits.addWidget(QLabel(tr('自動登録する最低投稿数')));limits.addWidget(self.min_posts);limits.addWidget(QLabel(tr('自動登録する最大種類数')));limits.addWidget(self.max_tags)
        basic_layout.insertWidget(basic_layout.indexOf(self.discover)+1,self.discovery_limits)
        self.discovery_limits.setVisible(self.discover.isChecked());self.discover.toggled.connect(self.discovery_limits.setVisible)
        self.discovery_status=QLabel();self.discovery_status.setWordWrap(True)
        basic_layout.insertWidget(basic_layout.indexOf(self.discovery_limits)+1,self.discovery_status)
        self.max_tags.valueChanged.connect(self.update_discovery_status);self.discover.toggled.connect(self.update_discovery_status)
        self.update_discovery_status()
        self.tabs.addTab(detail,tr('詳細'))
        self.saved=QLabel();self.saved.setWordWrap(True);detail_layout.addWidget(self.saved);self.update_count()
        self.read=QPushButton(tr('投稿文をZIPから読み直す…'));self.read.setObjectName('readPostTextZip')
        self.read.setAutoDefault(False);self.read.clicked.connect(self.choose_zip);detail_layout.addWidget(self.read)
        self.read.setVisible(bool(self.library_id))
        self.read.setToolTip(tr('保存済みの投稿文があれば不要です。以前の版で本文を保存していなかった場合などに使います。'))
        self.apply=QPushButton(tr('保存して、今ある作品にも反映'));self.apply.setObjectName('applyPostTags')
        self.apply.setAutoDefault(False);self.apply.clicked.connect(self.save);layout.addWidget(self.apply)
        if not self.library_id:self.apply.setText(tr('これから取り込む作品用に設定を保存'))
        self.status=QLabel();self.status.setWordWrap(True);layout.addWidget(self.status)
        self._enabled_sources=(options['hashtags'],options['body'],options['discover_hashtags'])
        self.enabled.toggled.connect(self.toggle_enabled);self.settings.setVisible(self.enabled.isChecked())

    @property
    def keyword_rules(self):
        return self.keyword_rows.rules()

    @keyword_rules.setter
    def keyword_rules(self,value):
        self.keyword_rows.set_rules(value)

    def toggle_enabled(self,enabled):
        if not enabled:
            self._enabled_sources=(self.hashes.isChecked(),self.body.isChecked(),self.discover.isChecked())
            self.hashes.setChecked(False);self.body.setChecked(False)
        else:
            hashes,body,discover=self._enabled_sources
            self.hashes.setChecked(hashes);self.body.setChecked(body or not hashes);self.discover.setChecked(discover)
        self.settings.setVisible(enabled)

    def update_count(self):
        if not self.library_id:
            self.saved.setText(tr('登録済みタグは1投稿でも対象です。自動登録の条件は下で変更できます。'));return
        count=self.store.post_text_count(self.library_id)
        self.saved.setText(trf('投稿文を保存済み：{0:,}件',count)+'\n'+tr('設定を保存すれば、ZIPを読み直さず今ある作品にも反映できます。') if count else
            tr('以前の版で取り込んだ作品は、同じZIPの投稿文を一度読み直してください。作品を再保存する必要はありません。'))

    def update_discovery_status(self,*_):
        self.discovery_status.setVisible(self.discover.isChecked())
        if not self.library_id:
            self.discovery_status.setText(tr('指定したタグ・探す言葉は、1投稿でも対象です。'));return
        rules=self.store.post_tag_rules(self.library_id)
        count=sum(bool(rules.get(i,{}).get('created')) for i in self.store.manual_tags(self.library_id))
        maximum=self.max_tags.value()
        self.discovery_status.setText(trf('自動登録済み：{0}種類',count)+('\n'+tr('上限に達しています。新しいタグは、上限を増やすか「登録タグ」に指定してください。') if maximum and count>=maximum else ''))

    def refresh_keyword_summary(self):
        self.keyword_rows.set_rules(self.keyword_rules)
        self.keyword_summary.clear()
        for rule in self.keyword_rules:
            self.keyword_summary.addItem(trf('タグ「{0}」 ← 探す言葉：{1}',rule['name'],'、'.join(rule.get('aliases',[]) or [rule['name']])))
        if not self.keyword_rules:self.keyword_summary.addItem(tr('下のボタンから、付けたいタグを選びましょう。'))

    def edit_keyword_rules(self):
        from .keyword_rules_ui import KeywordRulesDialog
        editor=KeywordRulesDialog(self);editor.setWindowFlags(Qt.WindowType.Widget)
        self.page_stack.addWidget(editor);self.page_stack.setCurrentWidget(editor)
        def finish():
            self.page_stack.setCurrentIndex(0);self.page_stack.removeWidget(editor);editor.deleteLater()
        editor.accepted.connect(finish);editor.rejected.connect(finish)

    def save(self):
        if self.busy:return False
        if self.window.importer.active:
            self.status.setText(tr('アーカイブ取り込みが終わってから操作してください。'));return False
        try:
            self.save_options()
            if self.library_id:
                self.set_busy(True)
                self.status.setText(tr('登録した言葉を照合しています…'))
                self.job=PostTagApplyJob(self.store.directory,self.library_id,self.target_assets())
                self.job.signals.done.connect(self.tag_job_finished);self.window.jobs.start(self.job)
            else:self.status.setText(tr('設定を保存しました。次のアーカイブ取り込みから反映します。'))
            return True
        except Exception as exc:self.status.setText(error_text(exc));return False

    def sync_library_changes(self):
        """Merge external removals without resurrecting an old editor snapshot."""
        from .post_tags import normalized
        latest=self.store.post_tag_options(self.library_id)
        before={normalized(r['name']):r for r in self._loaded_options['keywords']}
        current={normalized(r['name']):r for r in latest['keywords']}
        if current!=before:
            table=self.keyword_rows.table
            draft_keys=set()
            for row in range(table.rowCount()-1,-1,-1):
                key=normalized(table.item(row,0).text())
                if key in before and key not in current:
                    table.removeRow(row);continue
                draft_keys.add(key)
                if key in before and key in current and current[key]!=before[key]:
                    old_words='、'.join(before[key].get('aliases',[]))
                    if table.item(row,1).text()==old_words:
                        table.item(row,1).setText('、'.join(current[key].get('aliases',[])))
            for key,rule in current.items():
                if key not in before and key not in draft_keys:
                    self.keyword_rows.add_row(rule['name'],'、'.join(rule.get('aliases',[])))
        if latest['excluded']!=self._loaded_options['excluded']:
            added=[n for n in latest['excluded'] if n not in self._loaded_options['excluded']]
            removed=set(self._loaded_options['excluded'])-set(latest['excluded'])
            draft=[n for n in self.excluded.toPlainText().splitlines() if n not in removed]
            self.excluded.setPlainText('\n'.join(dict.fromkeys(draft+added)))
        self._loaded_options=deepcopy(latest)

    def save_options(self):
        self.sync_library_changes()
        excluded=[line.strip().lstrip('#＃') for line in self.excluded.toPlainText().splitlines() if line.strip()]
        self.store.save_post_tag_options(self.library_id,self.hashes.isChecked(),self.body.isChecked(),excluded,
            min_posts=self.min_posts.value(),max_tags=self.max_tags.value(),keywords=self.keyword_rules,tidy=self.tidy.isChecked(),discover_hashtags=self.discover.isChecked())
        self._loaded_options=deepcopy(self.store.post_tag_options(self.library_id))

    def target_assets(self):
        if self.library_id==self.window.library_id:return self.window.assets
        from .catalog import read_catalog
        return read_catalog(self.root)+self.store.warning_assets(self.library_id)

    def choose_zip(self):
        if self.busy:return
        if self.window.importer.active:
            self.status.setText(tr('アーカイブ取り込みが終わってから操作してください。'));return
        path,_=QFileDialog.getOpenFileName(self,tr('X公式アーカイブZIPを選ぶ'),str(Path.home()),tr('ZIPアーカイブ (*.zip)'))
        if not path:return
        try:
            self.save_options()
        except ValueError as exc:self.status.setText(error_text(exc));return
        self.set_busy(True)
        self.status.setText(tr('投稿文を読み込んでいます。作品ファイルは変更しません。'))
        self.job=PostTextJob(self.store.directory,self.root,path)
        self.job.signals.done.connect(self.tag_job_finished);self.window.jobs.start(self.job)

    def tag_job_finished(self,result,error):
        self.set_busy(False)
        if self.window.closing:return
        if error:self.status.setText(error)
        else:self.show_result(result)
        self.update_count()
        self.update_discovery_status()

    def set_busy(self,busy):
        self.busy=busy;self.settings.setEnabled(not busy)
        self.enabled.setEnabled(not busy);self.read.setEnabled(not busy);self.apply.setEnabled(not busy)
        if self.manager:self.manager.set_busy(busy)

    def show_result(self,result):
        if self.manager and self.library_id==self.window.library_id:self.manager.refresh()
        elif self.library_id==self.window.library_id:self.window.reload_manual_tags();self.window.apply_filters(preserve=True)
        self.status.setText(trf('反映しました：{0:,}投稿 / 自動タグ付与 {1:,}件 / 新しいタグ {2:,}個',
            result['posts'],result['automatic_links'],result['new_tags']))
        self.update_count()

    def reject(self):
        if not self.busy:super().reject()

    def closeEvent(self,event):
        if self.busy:event.ignore()
        else:super().closeEvent(event)
