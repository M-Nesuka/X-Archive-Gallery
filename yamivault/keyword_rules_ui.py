"""Plain-language form for mapping several post words to a tag."""
from copy import deepcopy
from PySide6.QtWidgets import (QDialog,QVBoxLayout,QHBoxLayout,QLabel,QPushButton,
    QListWidget,QLineEdit,QComboBox)
from .i18n import tr,error_text
from .appearance import theme_css
from .manual_tags import normalize_tag
from .post_tags import names,normalized


class KeywordRulesDialog(QDialog):
    def __init__(self,options):
        super().__init__(options);self.options=options
        self.rules=deepcopy(options.keyword_rules);self.editing=None
        self.setWindowTitle(tr('言葉を選んで、自動タグを設定'));self.resize(740,550)
        self.setStyleSheet(theme_css('''QLabel, QLineEdit, QComboBox, QPlainTextEdit { font-size:16px; }
            QPushButton#primary { border:1px solid #8a779e; padding:10px 14px; }'''))
        layout=QVBoxLayout(self)
        hint=QLabel(tr('登録タグを選んで、検索する言葉を追加しましょう。'))
        hint.setWordWrap(True);layout.addWidget(hint)
        body=QHBoxLayout();layout.addLayout(body,1)
        left=QVBoxLayout();body.addLayout(left,2)
        self.listing=QListWidget();self.listing.setObjectName('keywordRulesList');left.addWidget(self.listing,1)
        self.new_button=QPushButton(tr('新しい設定'));self.new_button.clicked.connect(self.new_rule);left.addWidget(self.new_button)
        self.delete_button=QPushButton(tr('この設定を外す'));self.delete_button.clicked.connect(self.delete_rule);left.addWidget(self.delete_button)
        right=QVBoxLayout();body.addLayout(right,3)
        right.addWidget(QLabel(tr('登録タグ')))
        self.tag=QComboBox();self.tag.setEditable(True);self.tag.setObjectName('keywordTargetTag')
        for name in sorted(options.window.manual_definitions.values()):self.tag.addItem(name)
        self.tag.setCurrentIndex(-1);self.tag.lineEdit().setPlaceholderText(tr('例：比較'))
        right.addWidget(self.tag)
        right.addWidget(QLabel(tr('検索する言葉')))
        word_entry=QHBoxLayout();right.addLayout(word_entry)
        self.word_input=QLineEdit();self.word_input.setObjectName('keywordWordInput')
        self.word_input.setPlaceholderText(tr('例：テーマ'));word_entry.addWidget(self.word_input,1)
        self.word_add=QPushButton(tr('追加'));self.word_add.clicked.connect(self.add_word);word_entry.addWidget(self.word_add)
        self.word_input.returnPressed.connect(self.add_word)
        self.words=QListWidget();self.words.setObjectName('keywordMatchWords');right.addWidget(self.words,1)
        self.word_remove=QPushButton(tr('選んだ言葉を外す'));self.word_remove.clicked.connect(self.remove_word);right.addWidget(self.word_remove)
        self.words.currentRowChanged.connect(lambda row:self.word_remove.setEnabled(row>=0))
        self.word_remove.setEnabled(False)
        example=QLabel(tr('この一覧のどれかが投稿にあれば、上の登録タグが付きます。言葉は複数追加できます。'))
        example.setWordWrap(True);right.addWidget(example)
        self.add_button=QPushButton(tr('一覧に追加'));self.add_button.clicked.connect(self.add_rule);right.addWidget(self.add_button)
        self.status=QLabel();self.status.setWordWrap(True);layout.addWidget(self.status)
        footer=QHBoxLayout();layout.addLayout(footer)
        cancel=QPushButton(tr('キャンセル'));cancel.clicked.connect(self.reject);footer.addWidget(cancel)
        self.apply_button=QPushButton(tr('保存して反映'));self.apply_button.setObjectName('primary')
        self.apply_button.clicked.connect(self.save);footer.addWidget(self.apply_button)
        for button in self.findChildren(QPushButton):button.setAutoDefault(False)
        self.listing.currentRowChanged.connect(self.select_rule)
        self.tag.activated.connect(self.choose_tag)
        self.refresh();self.new_rule()

    def choose_tag(self,index):
        existing=next((i for i,r in enumerate(self.rules) if normalized(r['name'])==normalized(self.tag.currentText())),None)
        if existing is not None:self.listing.setCurrentRow(existing);self.select_rule(existing)
        else:
            self.editing=None
            self.listing.blockSignals(True);self.listing.setCurrentRow(-1);self.listing.blockSignals(False)
            self.add_button.setText(tr('一覧に追加'));self.delete_button.setEnabled(False)

    def word_values(self):
        return [self.words.item(i).text() for i in range(self.words.count())]

    def add_word(self):
        value=self.word_input.text().strip()
        if not value:return
        for word in names([value]):
            if normalized(word) not in {normalized(w) for w in self.word_values()}:
                self.words.addItem(word)
        self.word_input.clear();self.word_input.setFocus()

    def remove_word(self):
        row=self.words.currentRow()
        if row>=0:self.words.takeItem(row)

    def refresh(self):
        self.listing.blockSignals(True);self.listing.clear()
        for rule in self.rules:self.listing.addItem(rule['name'])
        self.listing.blockSignals(False)

    def new_rule(self):
        self.editing=None;self.listing.setCurrentRow(-1)
        self.tag.setCurrentIndex(-1);self.tag.setEditText('');self.words.clear();self.word_input.clear()
        self.add_button.setText(tr('一覧に追加'));self.delete_button.setEnabled(False)
        self.tag.setFocus();self.status.clear()

    def select_rule(self,row):
        if row<0:return
        self.editing=row;rule=self.rules[row]
        self.tag.setEditText(rule['name']);self.words.clear();self.word_input.clear()
        self.words.addItems(rule.get('aliases',[]))
        self.add_button.setText(tr('変更を一覧に反映'));self.delete_button.setEnabled(True)
        self.status.clear()

    def commit_form(self):
        name=normalize_tag(self.tag.currentText())
        self.add_word()
        aliases=names(self.word_values())
        existing=next((i for i,r in enumerate(self.rules) if normalized(r['name'])==normalized(name)),None)
        if self.editing is not None and existing is not None and existing!=self.editing:
            raise ValueError('同じ名前のタグがすでにあります。')
        if self.editing is None:
            if existing is None:
                self.rules.append({'name':name,'aliases':aliases});index=len(self.rules)-1
            else:
                self.rules[existing]['aliases']=names(self.rules[existing].get('aliases',[])+aliases);index=existing
        else:
            index=self.editing;self.rules[index]={'name':name,'aliases':aliases}
        self.refresh();self.listing.setCurrentRow(index)

    def add_rule(self):
        try:self.commit_form();self.status.setText(tr('一覧に入れました。最後に「保存して反映」を押してください。'))
        except ValueError as exc:self.status.setText(error_text(exc))

    def delete_rule(self):
        if self.editing is None:return
        self.rules.pop(self.editing);self.refresh();self.new_rule()
        self.status.setText(tr('自動タグの設定から外しました。手動で付けたタグは残ります。'))

    def save(self):
        try:
            if self.tag.currentText().strip() or self.words.count() or self.word_input.text().strip():self.commit_form()
            previous=self.options.keyword_rules
            self.options.keyword_rules=deepcopy(self.rules)
            if self.options.save():
                self.options.refresh_keyword_summary();self.accept()
            else:
                self.options.keyword_rules=previous
                self.status.setText(self.options.status.text())
        except ValueError as exc:self.status.setText(error_text(exc))
