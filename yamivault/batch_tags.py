"""Batch annotation controls. Selection is transient; tag assignments are durable."""
from .i18n import tr,trf
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QWidget,QFrame,QHBoxLayout,QVBoxLayout,QGridLayout,QPushButton,
    QLabel,QCheckBox,QDialog,QListWidget,QListWidgetItem,QLineEdit,QPlainTextEdit,QMessageBox,QSizePolicy)


class BatchTagUiMixin:
    def build_batch_bar(self,layout):
        bar=self.backup_strip
        row=bar.layout()
        row.setSpacing(10)
        self.selection_count=QLabel(tr('0件選択'))
        self.selection_count.hide()
        row.insertWidget(3,self.selection_count)
        self.discovery_button=QPushButton(tr('発掘'))
        self.discovery_button.clicked.connect(self.open_discovery)
        row.addWidget(self.discovery_button)
        reroll=self.reroll_button=QPushButton(tr('↻ 再抽選'))
        reroll.setToolTip(tr('現在の絞り込み条件からランダムで再抽選します。件数は「発掘」で指定できます。'))
        reroll.clicked.connect(self.reroll_discovery)
        row.addWidget(reroll)
        self.batch_bar=bar

    def selected_tag_assets(self):
        if self.gallery.multi_selection:
            return [a for a in self.visible if a.identity in self.gallery.multi_selection]
        return [self.current] if self.current else []

    def select_all_visible(self):
        self.gallery.multi_selection={a.identity for a in self.visible}
        self.multi_selection_changed()
        self.gallery.viewport().update()

    def clear_multi_selection(self):
        self.gallery.multi_selection.clear()
        self.multi_selection_changed()
        self.gallery.viewport().update()

    def multi_selection_changed(self):
        count=len(self.gallery.multi_selection)
        self.selection_count.setText(trf('{0:,}件選択', count))
        self.selection_count.setVisible(count>0)
        self.selection_count.setToolTip(tr('選択中の作品にタグやお気に入りをまとめて設定できます。'))
        # Opening a sidebar while dragging changes tile positions mid-selection.
        self.update_frequent_tags()
        self.update_manual_details()

    def tag_usage_counts(self):
        hashes={a.annotation_key for a in self.assets}
        counts={i:0 for i in self.manual_definitions}
        for sha,ids in self.manual_mapping.items():
            if sha in hashes:
                for ident in ids:
                    if ident in counts:counts[ident]+=1
        return counts

    def frequent_tag_ids(self):
        counts=self.tag_usage_counts()
        return sorted(self.manual_definitions,key=lambda i:(-counts[i],self.manual_definitions[i].casefold()))[:10]

    def build_frequent_tags(self,column):
        title=QLabel(tr('よく使うタグ · クリックで付与'))
        title.setObjectName('muted')
        column.addWidget(title)
        self.frequent_widget=QWidget()
        self.frequent_layout=QGridLayout(self.frequent_widget)
        self.frequent_layout.setContentsMargins(0,0,0,0)
        self.frequent_layout.setSpacing(3)
        column.addWidget(self.frequent_widget)

    def update_frequent_tags(self):
        if not hasattr(self,'frequent_layout'):return
        while self.frequent_layout.count():
            item=self.frequent_layout.takeAt(0)
            if item.widget():
                item.widget().hide()
                item.widget().deleteLater()
        counts=self.tag_usage_counts()
        hashes={a.annotation_key for a in self.selected_tag_assets()}
        frequent=self.frequent_tag_ids()
        for n,ident in enumerate(frequent):
            common=bool(hashes) and all(ident in self.manual_mapping.get(sha,set()) for sha in hashes)
            name=self.manual_definitions[ident]
            b=QPushButton(('✓ ' if common else '')+name)
            b.setSizePolicy(QSizePolicy.Policy.Ignored,QSizePolicy.Policy.Preferred)
            b.setToolTip(trf('{0} · {1:,}作品', name, counts[ident])+(tr(' · 全対象に付与済み（クリックで解除）') if common else tr(' · クリックで付与')))
            b.setEnabled(bool(hashes))
            b.setObjectName('manualTag')
            from .tag_colors import tag_colors
            bg,fg=tag_colors(self.manual_colors.get(ident))
            b.setStyleSheet(f'QPushButton{{background:{bg};color:{fg};}}')
            b.clicked.connect(lambda _checked=False,i=ident:self.toggle_tag_batch(i))
            self.frequent_layout.addWidget(b,n//2,n%2)

    def toggle_tag_batch(self,ident):
        targets=self.selected_tag_assets()
        common=bool(targets) and all(ident in self.manual_mapping.get(a.annotation_key,set()) for a in targets)
        return self.apply_tag_batch([ident],not common)

    def apply_tag_batch(self,identifiers,enabled=True,*,targets=None):
        targets=list(targets) if targets is not None else self.selected_tag_assets()
        if not targets or not identifiers:return
        hashes={a.sha256 for a in targets}
        result=self.apply_account_tags(targets,identifiers,enabled)
        self.reload_manual_tags()
        self.apply_filters(preserve=True)
        operation=tr('新規付与') if enabled else tr('解除')
        self.last_batch_result={'selected_records':len(targets),**result}
        self.toast(trf('対象 {0:,}件 / 異なる画像 {1:,}作品 · {2} {3:,}件 · ', len(targets), len(hashes), operation, result['changed'])+
                   (tr('付与済み') if enabled else tr('元から未付与'))+trf(' {0:,}件（画像×タグ）', result['unchanged']))
        return result

    def batch_tag_dialog(self,enabled=True):
        if not self.selected_tag_assets():return
        dialog=QDialog(self)
        dialog.setWindowTitle(tr('タグ · チェックで付与 / チェック解除で外す'))
        dialog.resize(400,490)
        layout=QVBoxLayout(dialog)
        targets=self.selected_tag_assets()
        layout.addWidget(QLabel(trf('{0:,}件選択 / 異なる画像 {1:,}作品', len(targets), len({a.sha256 for a in targets}))))
        search=QLineEdit()
        search.setPlaceholderText(tr('登録タグを探す'))
        layout.addWidget(search)
        listing=QListWidget()
        counts=self.tag_usage_counts()
        for ident in sorted(self.manual_definitions,key=lambda i:(-counts[i],self.manual_definitions[i])):
            item=QListWidgetItem(f'{self.manual_definitions[ident]} · {counts[ident]:,}')
            item.setIcon(self.manual_tag_icon(ident))
            item.setData(Qt.ItemDataRole.UserRole,ident)
            common=all(ident in self.manual_mapping.get(a.annotation_key,set()) for a in targets)
            item.setCheckState(Qt.CheckState.Checked if common else Qt.CheckState.Unchecked)
            listing.addItem(item)
        search.textChanged.connect(lambda text:[listing.item(i).setHidden(text.casefold() not in listing.item(i).text().casefold()) for i in range(listing.count())])
        layout.addWidget(listing,1)
        listing.itemChanged.connect(lambda item:self.apply_tag_batch([item.data(Qt.ItemDataRole.UserRole)],
            item.checkState()==Qt.CheckState.Checked,targets=targets))
        actions=QHBoxLayout()
        cancel=QPushButton(tr('閉じる'))
        cancel.clicked.connect(dialog.reject)
        actions.addWidget(cancel)
        layout.addLayout(actions)
        dialog.exec()
