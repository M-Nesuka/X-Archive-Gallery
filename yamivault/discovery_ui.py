"""Compact metadata-based rediscovery drawer, independent of the archive catalog."""
from .i18n import tr,trf
import secrets
import time
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame,QVBoxLayout,QHBoxLayout,QLabel,QPushButton,QComboBox,QCheckBox,QScrollArea,QWidget
from .discovery import discovery_filter,discovery_order
from .grouping import content_key


class DiscoveryUiMixin:
    def build_discovery_panel(self,browse_layout):
        self.discovery_panel=QFrame()
        self.discovery_panel.setObjectName('details')
        self.discovery_panel.setFixedWidth(320)
        outer=QVBoxLayout(self.discovery_panel)
        outer.setContentsMargins(0,0,0,0)
        scroll=QScrollArea()
        scroll.viewport().setObjectName('discoverySurface')
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        content=QWidget()
        content.setObjectName('discoverySurface')
        content.setAttribute(Qt.WidgetAttribute.WA_StyledBackground,True)
        column=QVBoxLayout(content)
        column.setContentsMargins(22,15,22,20)
        head=QHBoxLayout()
        head.addWidget(QLabel(tr('昔の作品を見つける')))
        head.addStretch()
        close=QPushButton('×')
        close.clicked.connect(self.discovery_panel.hide)
        head.addWidget(close)
        column.addLayout(head)
        note=QLabel(tr('現在の年月・種類・検索・タグ条件から、\n埋もれた作品を探します。'))
        note.setObjectName('muted')
        note.setWordWrap(True)
        column.addWidget(note)
        reroll=QPushButton(tr('↻ ランダム再抽選'))
        reroll.setObjectName('primary')
        reroll.clicked.connect(self.reroll_discovery)
        column.addWidget(reroll)
        self.discovery_mode=QComboBox()
        for text,mode in [(tr('通常の並び順'),'current'),(tr('ランダム'),'random'),(tr('古い作品を優先'),'old'),
                          (tr('しばらく見ていない順'),'unseen'),(tr('高成績タグが多い順'),'strong')]:self.discovery_mode.addItem(text,mode)
        column.addWidget(QLabel(tr('発掘の順番')))
        column.addWidget(self.discovery_mode)
        self.discovery_limit=QComboBox()
        for text,count in [(tr('すべて'),0),(tr('10件'),10),(tr('25件'),25),(tr('50件'),50)]:self.discovery_limit.addItem(text,count)
        column.addWidget(QLabel(tr('抽出件数（同じ内容は1作品）')))
        column.addWidget(self.discovery_limit)
        self.discovery_exclude_favorites=QCheckBox(tr('お気に入りを除外'))
        self.discovery_recent=QCheckBox(tr('最近見た作品を除外 · 24時間'))
        self.discovery_high=QCheckBox(tr('高成績タグがある作品のみ'))
        self.discovery_no1=QCheckBox(tr('NO.1タグがある作品のみ'))
        self.discovery_no_high_unfav=QCheckBox(tr('高成績タグなし・お気に入り未登録のみ'))
        self.discovery_no_high_unfav.setToolTip(tr('高成績・NO.1タグがなく、同じ画像内容がどの投稿でもお気に入り未登録の作品だけ表示します。Analytics未取り込み・未照合の作品も含みます。'))
        for box in (self.discovery_exclude_favorites,self.discovery_recent,self.discovery_high,self.discovery_no1,self.discovery_no_high_unfav):
            column.addWidget(box)
            box.toggled.connect(self.reconcile_discovery_performance if box in (self.discovery_high,self.discovery_no1,self.discovery_no_high_unfav) else self.apply_filters)
        self.discovery_post_info=QComboBox()
        for text,key in [(tr('X投稿情報 · すべて'),''),(tr('X投稿情報あり'),'yes'),(tr('X投稿情報なし／対応不明'),'unknown')]:self.discovery_post_info.addItem(text,key)
        column.addWidget(self.discovery_post_info)
        self.discovery_summary=QLabel('')
        self.discovery_summary.setWordWrap(True)
        self.discovery_summary.setObjectName('muted')
        column.addWidget(self.discovery_summary)
        note=QLabel(tr('お気に入り除外は同じ画像内容にも適用。\n閲覧履歴は作品選択・拡大時に記録します。\n履歴がない作品は「閲覧記録なし」として優先します。'))
        note.setWordWrap(True)
        note.setObjectName('muted')
        column.addWidget(note)
        clear=QPushButton(tr('発掘条件を解除'))
        clear.clicked.connect(self.reset_discovery)
        column.addWidget(clear)
        normal=QPushButton(tr('通常表示に戻す · 新しい順'))
        normal.clicked.connect(self.return_normal_gallery)
        column.addWidget(normal)
        column.addStretch()
        scroll.setWidget(content)
        outer.addWidget(scroll)
        browse_layout.addWidget(self.discovery_panel)
        self.discovery_panel.hide()
        for combo in (self.discovery_mode,self.discovery_limit,self.discovery_post_info):combo.currentIndexChanged.connect(self.apply_filters)

    def open_discovery(self):
        if self.discovery_panel.isVisible():self.discovery_panel.hide();return
        self.details.hide()
        self.import_panel.hide()
        self.discovery_panel.show()

    def reroll_discovery(self):
        self.discovery_seed=secrets.token_hex(24)
        self.discovery_mode.blockSignals(True)
        self.discovery_mode.setCurrentIndex(self.discovery_mode.findData('random'))
        self.discovery_mode.blockSignals(False)
        self.apply_filters()

    def reset_discovery(self):
        controls=(self.discovery_mode,self.discovery_limit,self.discovery_post_info,self.discovery_exclude_favorites,
                  self.discovery_recent,self.discovery_high,self.discovery_no1,self.discovery_no_high_unfav)
        for control in controls:
            control.blockSignals(True)
            if isinstance(control,QComboBox):control.setCurrentIndex(0)
            else:control.setChecked(False)
            control.blockSignals(False)
        self.apply_filters()

    def reconcile_discovery_performance(self,checked):
        if checked:
            controls=(self.discovery_high,self.discovery_no1) if self.sender() is self.discovery_no_high_unfav else (self.discovery_no_high_unfav,)
            for control in controls:
                blocked=control.blockSignals(True);control.setChecked(False);control.blockSignals(blocked)
        self.apply_filters()

    def return_normal_gallery(self):
        self.sort_order='newest'
        self.random_seed=''
        self.sort_combo.blockSignals(True)
        self.sort_combo.setCurrentIndex(self.sort_combo.findData('newest'))
        self.sort_combo.blockSignals(False)
        self.store.set('sort_order','newest')
        self.reset_discovery()
        self.toast(tr('発掘を解除し、新しい順に戻しました。年月・検索・タグ条件は維持しています。'))

    def filter_for_discovery(self,assets):
        favorite_hashes={a.annotation_key for a in self.assets if a.identity in self.favorites}
        exclusion=self.discovery_exclude_favorites.isChecked() or self.discovery_no_high_unfav.isChecked()
        options=dict(recent_cutoff=time.time()-86400 if self.discovery_recent.isChecked() else None,
            high_only=self.discovery_high.isChecked(),
            no1_only=self.discovery_no1.isChecked(),post_info=self.discovery_post_info.currentData(),
            no_high_unfav=self.discovery_no_high_unfav.isChecked())
        if self.discovery_no_high_unfav.isChecked():
            options['high_hashes']={a.annotation_key for a in self.assets if self.performance_by_post.get(a.performance_key,{}).get('high_count',0) or self.performance_by_post.get(a.performance_key,{}).get('top1_count',0)}
        # Count the favorite contents that match the other conditions, before sampling.
        candidates=discovery_filter(assets,self.performance_by_post,self.views,set(),**options)
        self.discovery_favorite_excluded=len({content_key(a) for a in candidates if a.annotation_key in favorite_hashes}) if exclusion else 0
        return [a for a in candidates if not exclusion or a.annotation_key not in favorite_hashes]

    def order_for_discovery(self,assets):
        return discovery_order(assets,self.discovery_mode.currentData(),self.sort_order,
            self.discovery_seed if self.discovery_mode.currentData()=='random' else self.random_seed,self.performance_by_post,self.views,True)

    def update_discovery_summary(self,pool_count):
        active=any((self.discovery_mode.currentIndex(),self.discovery_limit.currentIndex(),self.discovery_post_info.currentIndex(),
                    self.discovery_exclude_favorites.isChecked(),self.discovery_recent.isChecked(),self.discovery_high.isChecked(),
                    self.discovery_no1.isChecked(),self.discovery_no_high_unfav.isChecked()))
        self.discovery_button.setText(tr('発掘 ●') if active else tr('発掘'))
        exclusion_note=(trf('\nお気に入り除外 {0:,}作品（条件内・同じ画像内容も対象）', self.discovery_favorite_excluded)
            if self.discovery_exclude_favorites.isChecked() or self.discovery_no_high_unfav.isChecked() else '')
        works=len({(a.sha256,a.kind) for a in self.visible})
        self.discovery_summary.setText(trf('候補 {0:,}表示タイル\n表示 {1:,}タイル / 異なる作品 {2:,}件。\n抽出は同じ内容を1作品として行います。重複非表示をOFFにすると、その作品の別投稿も展開します。\n抽出件数より候補が少ない場合は候補のみ表示します。', pool_count, len(self.visible), works)+exclusion_note)

    def record_view(self,asset):
        if not asset or not self.account_library(asset):return
        key=(self.account_library(asset),asset.sha256)
        clock=time.monotonic()
        if clock-self.view_debounce.get(key,float('-inf'))<5:return
        stamp=self.store.record_asset_view(self.account_library(asset),asset.sha256)
        self.view_debounce[key]=clock
        previous=self.views.get(asset.annotation_key,{})
        self.views[asset.annotation_key]={'last_seen':stamp,'view_count':previous.get('view_count',0)+1}

    def browse_asset(self,asset):
        if not self._restoring_navigation and (not self.current or self.current.identity!=asset.identity):
            self.navigation_history.append((self.filter_state(),self.navigation_view()))
            self.navigation_history=self.navigation_history[-60:]
            self.back_button.setEnabled(True)
        self.record_view(asset)
        self.select_asset(asset)
