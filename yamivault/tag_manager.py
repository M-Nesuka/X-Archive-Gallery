"""Separate creation/editing drafts; bulk color choices apply immediately."""
from html import escape
import sqlite3
from PySide6.QtCore import Qt,Signal
from PySide6.QtGui import QColor,QIcon,QPixmap
from PySide6.QtWidgets import (QDialog,QVBoxLayout,QHBoxLayout,QGridLayout,QLabel,
    QLineEdit,QListWidget,QListWidgetItem,QComboBox,QPushButton,QTabWidget,QWidget,
    QInputDialog,QMessageBox,QCheckBox,QAbstractItemView,QScrollArea,QTreeWidget,QTreeWidgetItem,QStackedWidget)
from .i18n import tr,trf,error_text
from .tag_colors import PALETTE,DEFAULT_COLOR,tag_colors
from .appearance import theme_css
from .post_tags import names,normalized
from .tag_tree import TagTree,TagItem


class AliasEditor(QWidget):
    """A list editor exposing the old text API to the unchanged save handler."""
    def __init__(self):
        super().__init__();layout=QVBoxLayout(self);layout.setContentsMargins(0,0,0,0)
        row=QHBoxLayout();layout.addLayout(row)
        self.input=QLineEdit();self.input.setPlaceholderText(tr('例：テーマ'));row.addWidget(self.input,1)
        add=QPushButton(tr('追加'));add.setAutoDefault(False);add.clicked.connect(self.add_word);row.addWidget(add)
        self.input.returnPressed.connect(self.add_word)
        self.listing=QListWidget();layout.addWidget(self.listing,1)
        remove=QPushButton(tr('選んだ言葉を外す'));remove.setAutoDefault(False)
        remove.clicked.connect(lambda:self.listing.takeItem(self.listing.currentRow()) if self.listing.currentRow()>=0 else None)
        layout.addWidget(remove);self.status=QLabel();layout.addWidget(self.status)

    def text(self):
        values=[self.listing.item(i).text() for i in range(self.listing.count())]
        if self.input.text().strip():values+=names(self.input.text())
        return '\n'.join(values)

    def setText(self,value):
        self.listing.clear();self.listing.addItems(names(value));self.input.clear();self.status.clear()

    def clear(self):self.setText('')

    def setPlaceholderText(self,value):self.input.setPlaceholderText(value)

    def add_word(self):
        try:
            values=names(self.text());self.setText('\n'.join(values));self.input.setFocus()
        except ValueError as exc:self.status.setText(error_text(exc))


class ColorPicker(QWidget):
    color_chosen=Signal(str)
    def __init__(self, object_name, parent=None):
        super().__init__(parent)
        layout=QVBoxLayout(self);layout.setContentsMargins(0,0,0,0);layout.setSpacing(6)
        self.combo=QComboBox();self.combo.setObjectName(object_name)
        self.buttons={}
        for key,(title,bg,fg) in PALETTE.items():
            pix=QPixmap(16,16);pix.fill(QColor(bg));self.combo.addItem(QIcon(pix),tr(title),key)
        layout.addWidget(self.combo)
        grid=QGridLayout();grid.setSpacing(3)
        for i,(key,(title,bg,fg)) in enumerate(PALETTE.items()):
            button=QPushButton('✓');button.setFixedHeight(24);button.setToolTip(tr(title))
            button.setAccessibleName(tr(title));button.setAutoDefault(False)
            button.clicked.connect(lambda _checked=False,k=key:self.choose_color(k))
            self.buttons[key]=button;grid.addWidget(button,i//7,i%7)
        layout.addLayout(grid)
        self.combo.activated.connect(lambda _index:self.color_chosen.emit(self.color()))
        self.combo.currentIndexChanged.connect(self.update_colors)
        self.set_color(DEFAULT_COLOR)

    def choose_color(self,key):
        self.set_color(key);self.color_chosen.emit(key)

    def color(self):return self.combo.currentData()

    def set_color(self,key):
        self.combo.setCurrentIndex(max(0,self.combo.findData(key)))
        self.update_colors()

    def update_colors(self):
        for key,button in self.buttons.items():
            bg,fg=tag_colors(key);selected=key==self.color()
            button.setText('✓' if selected else '')
            button.setStyleSheet(f'QPushButton{{background:{bg};color:{fg};border:2px solid '+
                ('#9086ac' if selected else '#808087')+';border-radius:5px;padding:0px;}')


class TagManagerDialog(QDialog):
    def __init__(self,window):
        super().__init__(window)
        self.window=window;self.store=window.store;self.library_id=window.library_id
        self.rule_fields={}
        self.busy=False
        self.setWindowTitle(tr('タグを管理'));self.resize(1000,740);self.setMinimumSize(800,540)
        layout=QVBoxLayout(self)
        body=QHBoxLayout();layout.addLayout(body,1)
        left=QVBoxLayout();body.addLayout(left,2)
        self.search=QLineEdit();self.search.setPlaceholderText(tr('タグを探す'));left.addWidget(self.search)
        self.new_tag_button=QPushButton(tr('新しいタグ'));self.new_tag_button.setAutoDefault(False)
        self.new_tag_button.clicked.connect(self.start_new_tag);left.addWidget(self.new_tag_button)
        self.filter=QComboBox();self.filter.setObjectName('tagGroupFilter');left.addWidget(self.filter)
        self.listing=TagTree();self.listing.setObjectName('tagManagerList');left.addWidget(self.listing,1)
        self.listing.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.listing.setDragEnabled(False)
        self.listing.setToolTip(tr('ドラッグで複数のタグを選択。Ctrlで追加、Shiftで範囲選択できます。'))
        self.bulk_group_row=QWidget();bulk_row=QHBoxLayout(self.bulk_group_row)
        bulk_row.setContentsMargins(0,0,0,0);bulk_row.setSpacing(4)
        self.bulk_group=QComboBox();self.bulk_group.setObjectName('bulkTagGroup')
        self.bulk_group.setToolTip(tr('選んだタグをまとめて移すグループ'))
        bulk_row.addWidget(self.bulk_group,1)
        self.bulk_move=QPushButton();self.bulk_move.setObjectName('moveSelectedTags')
        self.bulk_move.setAutoDefault(False);self.bulk_move.clicked.connect(self.move_selected_tags)
        bulk_row.addWidget(self.bulk_move);left.addWidget(self.bulk_group_row)
        self.bulk_delete=QPushButton();self.bulk_delete.setObjectName('deleteSelectedTags')
        self.bulk_delete.setAutoDefault(False);self.bulk_delete.clicked.connect(self.delete_tag);left.addWidget(self.bulk_delete)
        self.order=QComboBox();self.order.addItem(tr('使用数順'),'usage');self.order.addItem(tr('名前順'),'name');left.addWidget(self.order)
        groups=QPushButton(tr('グループを管理…'));groups.setAutoDefault(False);groups.clicked.connect(self.manage_groups);groups.hide()
        automatic=QPushButton(tr('投稿から自動タグ…'));automatic.setObjectName('postTagOptions')
        automatic.setAutoDefault(False);automatic.clicked.connect(self.auto_options);automatic.hide()
        self.workspace=QTabWidget();body.addWidget(self.workspace,3)
        self.tabs=QStackedWidget();self.workspace.addTab(self.tabs,tr('タグ編集'))
        self.new_page,self.new_name,self.new_group,self.new_color,self.new_preview=self.editor('new')
        self.edit_page,self.edit_name,self.edit_group,self.edit_color,self.edit_preview=self.editor('edit')
        self.tabs.addWidget(self.new_page);self.tabs.addWidget(self.edit_page)
        self.create_button=QPushButton(tr('このタグを作る'));self.create_button.setObjectName('createManualTag')
        self.create_button.setAutoDefault(False);self.create_button.clicked.connect(lambda:self.save(False));self.new_page.layout().addWidget(self.create_button)
        row=QHBoxLayout()
        self.save_button=QPushButton(tr('このタグに保存'));self.save_button.setObjectName('saveManualTag');self.save_button.setAutoDefault(False)
        self.save_button.clicked.connect(lambda:self.save(True));row.addWidget(self.save_button)
        for action in (self.create_button,self.save_button):
            action.setMinimumHeight(38)
            action.setStyleSheet(theme_css('QPushButton { background:#2b2437; color:#e5d4ff; border:1px solid #8a779e; border-radius:6px; padding:7px 12px; }'))
        self.delete_button=QPushButton(tr('タグを削除'));self.delete_button.setAutoDefault(False);self.delete_button.clicked.connect(self.delete_tag);row.addWidget(self.delete_button)
        self.edit_page.layout().addLayout(row)
        self.bulk_color_page=QWidget();bulk_color_layout=QVBoxLayout(self.bulk_color_page)
        self.bulk_color_title=QLabel();bulk_color_layout.addWidget(self.bulk_color_title)
        hint=QLabel(tr('色をクリックすると、選択したタグすべてにすぐ反映します。'));hint.setWordWrap(True);bulk_color_layout.addWidget(hint)
        self.bulk_color=ColorPicker('bulkManualTagColor');bulk_color_layout.addWidget(self.bulk_color)
        self.bulk_color.color_chosen.connect(lambda _color:self.color_selected_tags())
        bulk_color_layout.addStretch()
        self.bulk_color.combo.setPlaceholderText(tr('色を選ぶ'))
        self.tabs.addWidget(self.bulk_color_page)
        self.status=QLabel();self.status.setWordWrap(True);self.status.setMinimumHeight(32);layout.addWidget(self.status)
        self.auto_page=None;self.groups_page=None
        self.workspace.currentChanged.connect(lambda index:self.refresh_groups() if self.groups_page is not None and self.workspace.currentWidget() is self.groups_page else None)
        self.search.textChanged.connect(self.filter_list);self.filter.currentIndexChanged.connect(self.filter_list)
        self.order.currentIndexChanged.connect(lambda:self.refresh())
        self.listing.currentItemChanged.connect(self.selected)
        self.listing.itemSelectionChanged.connect(self.selection_changed)
        self.new_name.returnPressed.connect(lambda:self.save(False));self.edit_name.returnPressed.connect(lambda:self.save(True))
        self.refresh();self.edit_page.setEnabled(False)
        self.auto_options();self.manage_groups();self.workspace.setCurrentIndex(0)

    def start_new_tag(self):
        self.listing.clearSelection();self.listing.setCurrentRow(-1)
        self.new_name.clear();self.rule_fields['new'][1].clear()
        self.workspace.setCurrentWidget(self.tabs);self.tabs.setCurrentWidget(self.new_page)
        self.new_name.setFocus();self.status.clear()

    def editor(self,mode):
        page=QWidget();layout=QVBoxLayout(page);layout.setSpacing(6)
        sections=QTabWidget();layout.addWidget(sections,1)
        basic=QWidget();basic_layout=QVBoxLayout(basic)
        automatic=QWidget();auto_layout=QVBoxLayout(automatic)
        detail=QWidget();detail_layout=QVBoxLayout(detail)
        for title,widget in (('基本',basic),('自動タグ',automatic),('詳細',detail)):
            scroll=QScrollArea();scroll.setWidgetResizable(True);scroll.setWidget(widget);sections.addTab(scroll,tr(title))
        basic_layout.addWidget(QLabel(tr('タグの名前')))
        name=QLineEdit();name.setMaxLength(80);name.setObjectName('newManualTagName' if mode=='new' else 'editManualTagName')
        name.setPlaceholderText(tr('例：風景'));basic_layout.addWidget(name)
        basic_layout.addWidget(QLabel(tr('グループ')))
        group=QComboBox();group.setObjectName('newTagGroup' if mode=='new' else 'editTagGroup');basic_layout.addWidget(group)
        body=QCheckBox(tr('投稿本文の名前・別名から自動で付ける'));body.setChecked(True);auto_layout.addWidget(body)
        words=QWidget();words_layout=QVBoxLayout(words);words_layout.setContentsMargins(0,0,0,0)
        words_layout.addWidget(QLabel(tr('検索する言葉')))
        aliases=AliasEditor();aliases.setObjectName('postTagAliases'+mode);words_layout.addWidget(aliases)
        aliases.setToolTip(tr('本文の部分一致とハッシュタグの別名に使います。短すぎる名前は誤判定防止のため本文から探しません。'))
        auto_layout.addWidget(words);auto_layout.addStretch(1);body.toggled.connect(words.setVisible)
        prefix=QCheckBox(tr('同じ言葉で始まるハッシュタグもまとめる'));prefix.setChecked(True);detail_layout.addWidget(prefix);detail_layout.addStretch(1)
        self.rule_fields[mode]=(body,aliases,prefix)
        basic_layout.addWidget(QLabel(tr('背景色を選ぶ')))
        picker=ColorPicker('newManualTagColor' if mode=='new' else 'manualTagColor');basic_layout.addWidget(picker)
        preview=QLabel();preview.setMinimumHeight(40);basic_layout.addWidget(preview);basic_layout.addStretch(1)
        def update():
            bg,fg=tag_colors(picker.color())
            preview.setText('<span style="background-color:'+bg+';color:'+fg+';">&nbsp;#'+escape(name.text() or tr('プレビュー'))+'&nbsp;</span>')
        name.textChanged.connect(update);picker.combo.currentIndexChanged.connect(update);update()
        return page,name,group,picker,preview

    def refresh(self,select=None):
        if getattr(self,'auto_page',None) is not None:self.auto_page.sync_library_changes()
        current=self.listing.currentItem()
        ident=select or (current.data(Qt.ItemDataRole.UserRole) if current else None)
        self.window.reload_manual_tags();self.window.apply_filters(preserve=True)
        self.groups,self.members=self.store.manual_tag_groups(self.library_id)
        for combo,filtering in ((self.filter,True),(self.new_group,False),(self.edit_group,False),(self.bulk_group,False)):
            value=combo.currentData();combo.blockSignals(True);combo.clear()
            combo.addItem(tr('すべてのグループ') if filtering else tr('グループなし'),'')
            if filtering:combo.addItem(tr('グループなし'),'__none__')
            for key,name in sorted(self.groups.items(),key=lambda pair:pair[1].casefold()):combo.addItem(name,key)
            if combo is self.bulk_group:combo.addItem(tr('新しいグループ…'),'__new__')
            combo.setCurrentIndex(max(0,combo.findData(value)));combo.blockSignals(False)
        expanded={key:item.isExpanded() for key,item in self.listing.groups.items()}
        self.listing.blockSignals(True);self.listing.clear()
        counts=self.window.tag_usage_counts()
        keys=sorted(self.window.manual_definitions,key=lambda i:(-counts[i],self.window.manual_definitions[i].casefold()) if self.order.currentData()=='usage' else self.window.manual_definitions[i].casefold())
        used_groups={self.members.get(key,'') for key in keys}
        for group in sorted(used_groups,key=lambda key:self.groups.get(key,tr('グループなし')).casefold()):
            self.listing.add_group(group,self.groups.get(group,tr('グループなし')),expanded.get(group,True))
        for key in keys:
            item=TagItem()
            item.setData(Qt.ItemDataRole.UserRole+1,counts[key])
            item.setData(Qt.ItemDataRole.UserRole,key);item.setIcon(self.window.manual_tag_icon(key))
            group=self.members.get(key,'')
            self.listing.add_tag(group,item)
            if key==ident:
                if select:self.listing.expand_group(group)
                self.listing.setCurrentItem(item)
        self.listing.blockSignals(False)
        self.selected(self.listing.currentItem(),None,switch=False);self.filter_list()
        self.selection_changed()

    def filter_list(self,*_):
        value=self.filter.currentData();text=self.search.text().casefold()
        for i in range(self.listing.count()):
            item=self.listing.item(i);key=item.data(Qt.ItemDataRole.UserRole);group=self.members.get(key,'')
            name=self.window.manual_definitions[key]
            group_name=self.groups.get(group,tr('グループなし'))
            label=f'{name}　{item.data(Qt.ItemDataRole.UserRole+1):,}'
            item.setText(label)
            item.setToolTip(f'{group_name} — {label}')
            item.setHidden(text not in self.window.manual_definitions[key].casefold() or
                (value=='__none__' and bool(group)) or (bool(value) and value!='__none__' and value!=group))
            if item.isHidden():item.setSelected(False)
        for group,parent in self.listing.groups.items():
            parent.setHidden(all(QTreeWidgetItem.isHidden(parent.child(i)) for i in range(parent.childCount())))
            if text or value:self.listing.expand_group(group)
        self.selection_changed()

    def selection_changed(self):
        count=len([item for item in self.listing.selectedItems() if not item.isHidden()])
        self.bulk_delete.setVisible(count>0)
        self.bulk_group_row.setVisible(count>0)
        self.bulk_move.setText(trf('{0:,}個を移動',count))
        self.bulk_delete.setText(trf('選択した{0:,}個のタグを削除',count))
        self.edit_page.setEnabled(count==1)
        if count>1:
            self.bulk_color_title.setText(trf('選択した{0:,}個のタグ',count))
            colors={self.window.manual_colors.get(item.data(Qt.ItemDataRole.UserRole),DEFAULT_COLOR) for item in self.listing.selectedItems() if not item.isHidden()}
            if len(colors)==1:self.bulk_color.set_color(next(iter(colors)))
            else:self.bulk_color.combo.setCurrentIndex(-1);self.bulk_color.update_colors()
            self.tabs.setCurrentWidget(self.bulk_color_page);self.workspace.setCurrentWidget(self.tabs)
        elif self.tabs.currentWidget() is self.bulk_color_page:
            self.tabs.setCurrentWidget(self.edit_page if count==1 else self.new_page)

    def color_selected_tags(self):
        identifiers={item.data(Qt.ItemDataRole.UserRole) for item in self.listing.selectedItems() if not item.isHidden()}
        if not identifiers or self.bulk_color.color() is None:return
        try:
            changed=self.store.bulk_manual_tag_colors(self.library_id,identifiers,self.bulk_color.color())
            # Color cannot change membership, counts, filters or tile geometry.
            # Avoid loading annotation maps and laying out the full library.
            for ident in identifiers:self.window.manual_colors[ident]=self.bulk_color.color()
            for item in self.listing.tags:
                if item.data(Qt.ItemDataRole.UserRole) in identifiers:
                    item.setIcon(self.window.manual_tag_icon(item.data(Qt.ItemDataRole.UserRole)))
            for ident in identifiers:
                self.window.gallery.manual_colors[self.window.manual_definitions[ident]]=self.bulk_color.color()
            if changed:self.window.gallery.viewport().update()
            if self.window.current:self.window.update_performance_details(self.window.current)
            self.selection_changed()
            self.status.setText(trf('{0:,}個のタグの色を変更しました。',changed))
        except (ValueError,sqlite3.Error) as error:self.status.setText(error_text(error))

    def selected(self,item,_old,switch=True):
        self.edit_page.setEnabled(item is not None and len(self.listing.selectedItems())==1)
        if item is None or item.data(Qt.ItemDataRole.UserRole) not in self.window.manual_definitions:
            self.edit_page.setEnabled(False);return
        ident=item.data(Qt.ItemDataRole.UserRole)
        self.edit_name.setText(self.window.manual_definitions[ident])
        self.edit_group.setCurrentIndex(max(0,self.edit_group.findData(self.members.get(ident,''))))
        self.edit_color.set_color(self.window.manual_colors.get(ident,DEFAULT_COLOR))
        rule=self.store.post_tag_rules(self.library_id).get(ident,{})
        body,aliases,prefix=self.rule_fields['edit']
        body.setChecked(rule.get('body',True));aliases.setText(' / '.join(rule.get('aliases',[])))
        prefix.setChecked(rule.get('prefix',True))
        if switch:self.tabs.setCurrentWidget(self.edit_page);self.workspace.setCurrentWidget(self.tabs);self.status.clear();self.selection_changed()

    def save(self,editing):
        if self.busy or self.window.importer.active:return
        if editing and len(self.listing.selectedItems())!=1:return
        item=self.listing.currentItem();ident=item.data(Qt.ItemDataRole.UserRole) if editing and item else None
        if editing and ident is None:return
        name,group,picker=(self.edit_name,self.edit_group,self.edit_color) if editing else (self.new_name,self.new_group,self.new_color)
        if not name.text().strip():return
        try:
            body,aliases,prefix=self.rule_fields['edit' if editing else 'new']
            rule={'body':body.isChecked(),'aliases':aliases.text(),'prefix':prefix.isChecked()}
            result=self.store.save_manual_tag_details(self.library_id,name.text(),picker.color(),group.currentData() or '',ident,post_rule=rule)
            label=name.text()
            # Registry edits are saved immediately; matching existing works is
            # done on a separate connection with the dialog protected meanwhile.
            self.set_busy(True);self.status.setText(tr('登録した言葉を照合しています…'))
            from .post_tag_ui import PostTagApplyJob
            self.tag_job=PostTagApplyJob(self.store.directory,self.library_id,self.window.assets,create_tags=False)
            def finished(_summary,error):
                self.set_busy(False)
                if self.window.closing or self.window.library_id!=self.library_id:return
                self.refresh(select=result)
                self.status.setText(error or trf('「{0}」を保存しました。作品の右クリックから選べます。',label))
            self.tag_job.signals.done.connect(finished);self.window.jobs.start(self.tag_job)
            if not editing:self.new_name.clear();aliases.clear();self.new_name.setFocus()
        except (ValueError,sqlite3.Error) as error:self.status.setText(error_text(error))

    def set_busy(self,busy):
        self.busy=busy
        for widget in (self.workspace,self.search,self.new_tag_button,self.filter,self.listing,
                       self.bulk_group_row,self.bulk_delete,self.order):widget.setEnabled(not busy)

    def move_selected_tags(self):
        identifiers=[item.data(Qt.ItemDataRole.UserRole) for item in self.listing.selectedItems() if not item.isHidden()]
        if not identifiers:return
        group=self.bulk_group.currentData() or ''
        try:
            if group=='__new__':
                name,ok=QInputDialog.getText(self,tr('新しいグループ'),tr('グループの名前'))
                if not ok or not name.strip():return
                group=self.store.save_tag_group(self.library_id,name)
            count=self.store.move_manual_tags_to_group(self.library_id,identifiers,group)
            self.refresh()
            self.bulk_group.setCurrentIndex(max(0,self.bulk_group.findData(group)))
            self.listing.expand_group(group)
            self.listing.blockSignals(True)
            for row in range(self.listing.count()):
                item=self.listing.item(row)
                item.setSelected(not item.isHidden() and item.data(Qt.ItemDataRole.UserRole) in identifiers)
            self.listing.blockSignals(False);self.selection_changed()
            self.status.setText(trf('{0:,}個のタグを「{1}」へ移動しました。すでに同じグループ：{2:,}個。',count,
                self.groups.get(group,tr('グループなし')),len(identifiers)-count))
        except (ValueError,sqlite3.Error) as error:self.status.setText(error_text(error))

    def delete_tag(self):
        identifiers=[item.data(Qt.ItemDataRole.UserRole) for item in self.listing.selectedItems() if not item.isHidden()]
        if not identifiers:return
        preview=' / '.join(self.window.manual_definitions[i] for i in identifiers[:8])
        message=trf('選択した{0:,}個のタグを登録一覧と全作品から削除しますか？\n画像は消えません。同じハッシュタグは次回の取り込みから除外します。\n\n{1}',len(identifiers),preview)
        if QMessageBox.question(self,tr('タグを削除'),message)!=QMessageBox.StandardButton.Yes:return
        try:
            count=self.store.delete_manual_tags(self.library_id,identifiers)
            self.refresh();self.status.setText(trf('{0:,}個のタグを削除しました。',count))
        except (ValueError,sqlite3.Error) as error:self.status.setText(error_text(error))

    def manage_groups(self):
        if self.groups_page is None:
            page=QWidget();layout=QVBoxLayout(page)
            hint=QLabel(tr('グループを消しても、中のタグは残ります。'));hint.setWordWrap(True);layout.addWidget(hint)
            self.group_listing=QTreeWidget();self.group_listing.setHeaderLabels([tr('グループ名'),tr('タグ数')]);self.group_listing.setMinimumHeight(220)
            self.group_listing.setColumnWidth(0,300);layout.addWidget(self.group_listing,1)
            self.group_name=QLineEdit();self.group_name.setPlaceholderText(tr('グループの名前'));layout.addWidget(self.group_name)
            self.group_listing.currentItemChanged.connect(lambda item,old:self.group_name.setText(item.text(0) if item else ''))
            row=QHBoxLayout();layout.addLayout(row)
            for label,mode in (('追加','add'),('名前変更','rename'),('グループ削除','delete')):
                b=QPushButton(tr(label));b.setAutoDefault(False);b.clicked.connect(lambda checked=False,m=mode:self.group_action(m));row.addWidget(b)
            self.groups_page=page;self.workspace.addTab(page,tr('グループ'))
        self.refresh_groups();self.workspace.setCurrentWidget(self.groups_page)

    def refresh_groups(self,selected=None):
        self.group_listing.clear();groups,members=self.store.manual_tag_groups(self.library_id)
        for key,name in sorted(groups.items(),key=lambda pair:pair[1].casefold()):
            item=QTreeWidgetItem([name,str(sum(value==key for value in members.values()))]);item.setData(0,Qt.ItemDataRole.UserRole,key)
            self.group_listing.addTopLevelItem(item)
            if key==selected:self.group_listing.setCurrentItem(item)

    def group_action(self,mode):
        item=self.group_listing.currentItem();key=item.data(0,Qt.ItemDataRole.UserRole) if item else None
        if mode!='add' and not key:return
        try:
            if mode=='delete':self.store.delete_tag_group(self.library_id,key);key=None
            else:key=self.store.save_tag_group(self.library_id,self.group_name.text(),key if mode=='rename' else None)
            self.refresh();self.refresh_groups(key);self.group_name.clear();self.status.setText(tr('グループを更新しました。'))
        except ValueError as error:self.status.setText(error_text(error))

    def auto_options(self):
        if self.auto_page is None:
            from .post_tag_ui import PostTagOptionsDialog
            self.auto_page=PostTagOptionsDialog(self)
            self.auto_page.setWindowFlags(Qt.WindowType.Widget)
            self.auto_page.setMinimumSize(0,0)
            self.workspace.addTab(self.auto_page,tr('投稿から自動タグ'))
        self.workspace.setCurrentWidget(self.auto_page)

    def reject(self):
        if self.window.closing or (not self.busy and (self.auto_page is None or not self.auto_page.busy)):super().reject()

    def closeEvent(self,event):
        if not self.window.closing and (self.busy or (self.auto_page is not None and self.auto_page.busy)):event.ignore()
        else:super().closeEvent(event)
