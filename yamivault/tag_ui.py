"""Compact manual-tag controls for the gallery and artwork detail panel."""
from .i18n import tr,trf,error_text
import sqlite3
from urllib.parse import unquote
from urllib.parse import quote
from html import escape
from .tag_cloud import TagCloud
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QIcon, QPixmap
from .tag_colors import PALETTE, DEFAULT_COLOR, tag_colors
from .appearance import theme_color
from PySide6.QtWidgets import (QWidget,QVBoxLayout,QHBoxLayout,QPushButton,QLineEdit,
    QMenu,QDialog,QListWidget,QListWidgetItem,QMessageBox,QLabel,QSizePolicy,QScrollArea,QComboBox)
from .manual_tags import filter_manual_tags


class ManualTagUiMixin:
    def manual_tag_icon(self,ident):
        swatch=QPixmap(14,14)
        swatch.fill(QColor(tag_colors(self.manual_colors.get(ident,DEFAULT_COLOR))[0]))
        return QIcon(swatch)

    def build_manual_tags(self, column):
        self.performance_tags=TagCloud()
        self.performance_tags.linkActivated.connect(self.detail_tag_clicked)
        self.performance_tags.setToolTip(tr('タグをクリックで絞り込み。付与・解除は画像の右クリックから操作します。'))
        column.addWidget(self.performance_tags)

    def detail_tag_clicked(self,link):
        if link.startswith('manual:'):self.toggle_manual_filter(link[7:])
        else:self.toggle_performance_filter(unquote(link.removeprefix('performance:')))

    def reload_manual_tags(self):
        self.manual_definitions=self.store.manual_tags(self.library_id) if self.library_id else {}
        self.manual_colors=self.store.manual_tag_colors(self.library_id) if self.library_id else {}
        self.manual_mapping=self.store.manual_tag_map(self.library_id) if self.library_id else {}
        if self.aggregate_entries:
            self.manual_definitions,self.manual_colors,self.manual_mapping=self.combined_manual_tags()
        self.selected_manual_tags.intersection_update(self.manual_definitions)
        self.tag_filter_button.setText(trf('タグ · {0}', len(self.selected_manual_tags)) if self.selected_manual_tags else tr('タグ ▾'))
        names=[self.manual_definitions[i] for i in self.selected_manual_tags]
        self.tag_filter_button.setToolTip(tr('すべての選択タグに一致（AND）\n')+' / '.join(names))
        self.gallery.manual_tags={sha:[self.manual_definitions[i] for i in sorted(ids) if i in self.manual_definitions]
                                  for sha,ids in self.manual_mapping.items()}
        self.gallery.manual_colors={name:self.manual_colors.get(i,DEFAULT_COLOR) for i,name in self.manual_definitions.items()}
        self.gallery.tag_hit_rects=[]
        self.update_manual_details()
        self.update_frequent_tags()

    def update_manual_details(self):
        if not hasattr(self,'performance_tags'):return
        targets=self.selected_tag_assets()
        if self.gallery.multi_selection and targets:
            ids=set.intersection(*(set(self.manual_mapping.get(a.annotation_key,set())) for a in targets))
            performance=set.intersection(*(set(self.performance_by_post.get(a.performance_key,{}).get('tags',[])) for a in targets))
        else:
            ids=self.manual_mapping.get(self.current.annotation_key,set()) if self.current else set()
            performance=set(self.performance_by_post.get(self.current.performance_key,{}).get('tags',[])) if self.current else set()
        links=[]
        for ident in sorted(ids,key=lambda i:self.manual_definitions.get(i,'')):
            if ident not in self.manual_definitions:continue
            links.append(self.detail_tag_link('manual:'+ident,'#'+self.manual_definitions[ident],ident in self.selected_manual_tags,
                manual_color=self.manual_colors.get(ident,DEFAULT_COLOR)))
        for name in sorted(performance):
            links.append(self.detail_tag_link('performance:'+quote(name,safe=''),tr(name),name in self.selected_performance_tags,'1位' in name))
        self.performance_tags.setText('<p style="margin:0;line-height:20px;">'+' &nbsp; '.join(links)+'</p>' if links else '')

    @staticmethod
    def detail_tag_link(link,name,selected,top=False,manual_color=None):
        color=theme_color('#b9aa80' if top else '#b3b9bf')
        background=''
        if manual_color is not None:
            bg,color=tag_colors(manual_color)
            background=f'background-color:{bg};'
        decoration='underline' if selected else 'none'
        label=escape(chr(0xfeff).join(name)).replace(' ','&nbsp;')
        if manual_color is not None:label='&nbsp;'+label+'&nbsp;'
        return f'<a href="{link}" title="{escape(name)}" style="color:{color};{background}text-decoration:{decoration};">'+label+'</a>'

    def attach_manual_tag(self, ident, enabled):
        if self.gallery.multi_selection:
            return self.apply_tag_batch([ident],enabled)
        if self.current:
            self.apply_account_tags([self.current],[ident],enabled)
            self.reload_manual_tags()
            self.apply_filters(preserve=True)
            self.update_frequent_tags()

    def toggle_manual_filter(self, ident):
        if ident in self.selected_manual_tags:
            self.selected_manual_tags.remove(ident)
        else:
            self.selected_manual_tags.add(ident)
        self.reload_manual_tags()
        self.apply_filters()

    def clear_manual_filters(self):
        self.selected_manual_tags.clear()
        self.reload_manual_tags()
        self.apply_filters()

    def manual_tag_menu(self, anchor, assign=False):
        menu=QMenu(anchor)
        for ident,name in self.manual_definitions.items():
            action=menu.addAction('#'+name)
            action.setIcon(self.manual_tag_icon(ident))
            action.setCheckable(True)
            targets=self.selected_tag_assets()
            action.setChecked(all(ident in self.manual_mapping.get(a.annotation_key,set()) for a in targets) if assign and targets else ident in self.selected_manual_tags)
            action.triggered.connect(lambda checked,i=ident:self.attach_manual_tag(i,checked) if assign else self.toggle_manual_filter(i))
        if not self.manual_definitions:
            action=menu.addAction(tr('タグは未登録です'))
            action.setEnabled(False)
        menu.addSeparator()
        menu.addAction(tr('タグを登録・管理…'),self.manage_manual_tags)
        menu.exec(anchor.mapToGlobal(anchor.rect().bottomLeft()))

    def manage_manual_tags(self):
        if not self.require_single_account() or not self.library_id:
            return
        dialog=QDialog(self)
        dialog.setWindowTitle(tr('手動タグの登録・管理'))
        dialog.resize(390,410)
        layout=QVBoxLayout(dialog)
        info=QLabel(tr('登録タグはどの作品にも使えます。\nタグの削除は、このライブラリの画像すべてから外します。'))
        info.setWordWrap(True)
        layout.addWidget(info)
        listing=QListWidget()
        layout.addWidget(listing,1)
        order=QComboBox()
        order.addItem(tr('使用数順'),'usage')
        order.addItem(tr('名前順'),'name')
        layout.addWidget(order)
        entry=QLineEdit()
        entry.setPlaceholderText(tr('新しいタグ／変更後の名前'))
        entry.setMaxLength(81)
        layout.addWidget(entry)
        colors=QComboBox()
        colors.setObjectName('manualTagColor')
        for key,(title,bg,_fg) in PALETTE.items():
            swatch=QPixmap(16,16);swatch.fill(QColor(bg))
            colors.addItem(QIcon(swatch),tr(title),key)
        color_row=QHBoxLayout();color_row.addWidget(QLabel(tr('背景色')));color_row.addWidget(colors,1)
        layout.addLayout(color_row)
        colors.setToolTip(tr('新しいタグは選んだ色で登録します。登録済みタグを選ぶと、そのタグの色を変更できます。'))
        def refresh():
            self.reload_manual_tags()
            self.apply_filters(preserve=True)
            listing.clear()
            counts=self.tag_usage_counts()
            identifiers=sorted(self.manual_definitions,key=lambda i:(-counts[i],self.manual_definitions[i].casefold()) if order.currentData()=='usage' else self.manual_definitions[i].casefold())
            for ident in identifiers:
                name=self.manual_definitions[ident]
                item=QListWidgetItem(f'{name}　{counts[ident]:,}')
                item.setData(Qt.ItemDataRole.UserRole,ident)
                item.setIcon(self.manual_tag_icon(ident))
                # List labels use the theme's foreground/selection colors.
                # Tag colors belong to swatches and chips, whose background is painted explicitly.
                listing.addItem(item)
        def edit(mode):
            if mode in ('add','rename') and not entry.text().strip():
                return
            item=listing.currentItem()
            try:
                if mode=='add':
                    self.store.create_manual_tag(self.library_id,entry.text(),colors.currentData())
                elif item and mode=='rename':
                    self.store.rename_manual_tag(self.library_id,item.data(Qt.ItemDataRole.UserRole),entry.text())
                elif item and mode=='delete':
                    if QMessageBox.question(dialog,tr('タグを削除'),trf('「{0}」を登録一覧と全画像から削除しますか？', item.text()))!=QMessageBox.StandardButton.Yes:
                        return
                    self.store.delete_manual_tag(self.library_id,item.data(Qt.ItemDataRole.UserRole))
                else:
                    return
                entry.clear()
                refresh()
            except (ValueError,sqlite3.IntegrityError) as error:
                QMessageBox.information(dialog,tr('タグ'),tr('同じ名前のタグがすでにあります。') if isinstance(error,sqlite3.IntegrityError) else error_text(error))
        def selected(item,_old):
            entry.setText(self.manual_definitions.get(item.data(Qt.ItemDataRole.UserRole),'') if item else '')
            if item:
                colors.blockSignals(True)
                colors.setCurrentIndex(colors.findData(self.manual_colors.get(item.data(Qt.ItemDataRole.UserRole),DEFAULT_COLOR)))
                colors.blockSignals(False)
        def change_color():
            item=listing.currentItem()
            if not item:return
            ident=item.data(Qt.ItemDataRole.UserRole)
            self.store.set_manual_tag_color(self.library_id,ident,colors.currentData())
            self.reload_manual_tags()
            item.setIcon(self.manual_tag_icon(ident))
            self.gallery.viewport().update()
        listing.currentItemChanged.connect(selected)
        colors.currentIndexChanged.connect(change_color)
        order.currentIndexChanged.connect(refresh)
        row=QHBoxLayout()
        for title,mode in [(tr('登録'),'add'),(tr('名前変更'),'rename'),(tr('削除'),'delete')]:
            b=QPushButton(title)
            b.setAutoDefault(False)
            b.setDefault(False)
            b.clicked.connect(lambda _checked=False,m=mode:edit(m))
            row.addWidget(b)
        layout.addLayout(row)
        entry.returnPressed.connect(lambda:edit('add'))
        refresh()
        dialog.exec()
