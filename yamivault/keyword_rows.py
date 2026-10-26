"""Editable mapping rows; reuse the existing normalized keyword rule format."""
from PySide6.QtWidgets import QWidget,QVBoxLayout,QHBoxLayout,QLabel,QPushButton,QTableWidget,QTableWidgetItem,QHeaderView,QAbstractItemView,QStyledItemDelegate
from .i18n import tr
from .post_tags import names,normalized
from .manual_tags import normalize_tag


class KeywordCellDelegate(QStyledItemDelegate):
    def createEditor(self,parent,option,index):
        editor=super().createEditor(parent,option,index)
        # Table cells have their own geometry; gallery search padding clips them.
        editor.setStyleSheet('QLineEdit {padding:0px 4px;border:0px;border-radius:0px;}')
        return editor


class KeywordRows(QWidget):
    def __init__(self,rules=(),parent=None):
        super().__init__(parent)
        layout=QVBoxLayout(self);layout.setContentsMargins(0,0,0,0)
        guide=QLabel(tr('左に付けたいタグ、右に投稿から探す言葉を入れます。複数の言葉は「、」か「,」で区切ります。'))
        guide.setWordWrap(True);layout.addWidget(guide)
        example=QLabel(tr('例：登録タグ「風景」→ 検索「風景」\n登録タグ「動物」→ 検索「ねこ,いぬ」\nどれかの言葉が投稿にあれば、左のタグが付きます。'))
        example.setWordWrap(True);layout.addWidget(example)
        self.table=QTableWidget(0,2);self.table.setObjectName('keywordRuleRows')
        self.table.setItemDelegate(KeywordCellDelegate(self.table))
        self.table.verticalHeader().setDefaultSectionSize(max(34,self.table.fontMetrics().height()+12))
        self.table.setHorizontalHeaderLabels([tr('登録タグ'),tr('検索する言葉')])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setMinimumHeight(150);layout.addWidget(self.table,1)
        row=QHBoxLayout();layout.addLayout(row)
        add=QPushButton(tr('行を追加'));add.clicked.connect(lambda:self.add_row());row.addWidget(add)
        remove=QPushButton(tr('選んだ行を削除'));remove.clicked.connect(self.remove_rows);row.addWidget(remove);row.addStretch()
        self.set_rules(rules)

    def add_row(self,name='',words=''):
        index=self.table.rowCount();self.table.insertRow(index)
        self.table.setItem(index,0,QTableWidgetItem(name));self.table.setItem(index,1,QTableWidgetItem(words))
        self.table.setCurrentCell(index,0)

    def remove_rows(self):
        for index in sorted({i.row() for i in self.table.selectedIndexes()},reverse=True):self.table.removeRow(index)

    def set_rules(self,rules):
        self.table.setRowCount(0)
        for rule in rules:self.add_row(rule['name'],'、'.join(rule.get('aliases',[])))
        if not rules:self.add_row()

    def rules(self):
        result=[];seen=set()
        for index in range(self.table.rowCount()):
            name=self.table.item(index,0).text().strip();words=self.table.item(index,1).text().strip()
            if not name and not words:continue
            name=normalize_tag(name)
            if normalized(name) in seen:raise ValueError('同じ名前のタグがすでにあります。')
            seen.add(normalized(name));result.append({'name':name,'aliases':names(words) if words else []})
        return result
