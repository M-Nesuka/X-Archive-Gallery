"""Dark desktop shell; backup reads, private annotations and UI are separated."""
from __future__ import annotations
from .i18n import tr,trf,error_text

import logging
import os
import shutil
import subprocess
import sys
import sqlite3
from html import escape as escape_html
from urllib.parse import quote,unquote
from pathlib import Path

from PIL import Image
from PySide6.QtCore import Qt, QObject, QRunnable, QThreadPool, Signal, QTimer, QSize, QUrl, QPointF, QEvent
from PySide6.QtGui import QAction, QColor, QDesktopServices, QFont, QImage, QImageReader, QKeySequence, QPainter, QPixmap
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer
from PySide6.QtMultimediaWidgets import QVideoWidget
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QFrame, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QLineEdit, QComboBox, QSlider, QScrollArea,
    QStackedWidget, QSizePolicy, QMenu, QFileDialog, QMessageBox, QToolButton, QInputDialog, QCheckBox,QDialog,QTextBrowser,QLayout,
)

from .catalog import DEFAULT_ROOT, UNKNOWN_YEAR, Asset, read_catalog, filter_assets, source_path
from .store import VaultStore
from .thumbnails import ThumbnailManager, cache_path
from .gallery import Gallery
from .clipboard import image_payload, file_payload
from .style import STYLE
from .appearance import AppearanceMixin,theme_color
from .language_ui import LanguageMixin
from .i18n import set_language_code,language,unknown_date
from .importer import ImportController
from .backup_ui import BackupUiMixin
from .backup_status import read_status
from .grouping import content_key, group_index, representatives, representative_for
from .order import order_assets
from .version import __version__
from .power_saving import PowerSavingMixin
from .tag_ui import ManualTagUiMixin
from .manual_tags import filter_manual_tags
from .batch_tags import BatchTagUiMixin
from .navigation import NavigationMixin
from .discovery_ui import DiscoveryUiMixin
from .discovery import has_x_post_info
from .account_ui import AccountUiMixin

log = logging.getLogger(__name__)


def label(text='', name='', wrap=False):
    result = QLabel(text)
    result.setObjectName(name)
    result.setWordWrap(wrap)
    return result


def button(text, callback, name='', tip=''):
    result = QPushButton(text)
    result.setObjectName(name)
    result.clicked.connect(callback)
    if tip:
        result.setToolTip(tip)
    return result


class LoadSignals(QObject):
    done = Signal(object, object, str)


class LibraryJob(QRunnable):
    def __init__(self, root, dimensions):
        super().__init__()
        self.root = root
        self.dimensions = dict(dimensions)
        self.signals = LoadSignals()

    def run(self):
        try:
            catalog = self.root / '.system' / 'catalog.sqlite3'
            from .library_reset import is_empty_or_lock_only
            if self.root.is_dir() and not catalog.exists() and is_empty_or_lock_only(self.root):
                assets = []
            else:
                assets = read_catalog(self.root)
            self.status = read_status(self.root)
            # Read headers in a background thread so the initial masonry layout
            # already has the original aspect ratios before JPEG generation.
            for a in assets:
                if a.sha256 in self.dimensions or a.kind not in ('image', 'gif'):
                    continue
                try:
                    with Image.open(source_path(self.root, a.relative_path)) as image:
                        w, h = image.size
                        if image.getexif().get(274) in (5, 6, 7, 8):
                            w, h = h, w
                        self.dimensions[a.sha256] = (w, h)
                except (OSError, ValueError, Image.DecompressionBombError):
                    pass
            self.signals.done.emit(assets, self.dimensions, '')
        except Exception as exc:
            self.signals.done.emit([], {}, error_text(exc))


class ImageSignals(QObject):
    done = Signal(object, object, str)


class ImageJob(QRunnable):
    def __init__(self, token, path):
        super().__init__()
        self.token, self.path = token, path
        self.signals = ImageSignals()
        self.cancelled=False

    def run(self):
        if self.cancelled:
            self.signals.done.emit(self.token,QImage(),'')
            return
        reader = QImageReader(str(self.path))
        reader.setAutoTransform(True)
        image = reader.read()
        self.signals.done.emit(self.token, image, '' if not image.isNull() else reader.errorString())


class ImageView(QWidget):
    activated = Signal()
    wheel_navigated = Signal(int)
    zoom_changed = Signal(float)

    def __init__(self):
        super().__init__()
        self.pixmap = QPixmap()
        self.message = tr('作品を選択してください')
        self.zoom = 1.0
        self.pan = QPointF()
        self.drag_anchor = None
        self.navigate_on_wheel = True
        self.scroll_target = None
        self.setMouseTracking(True)
        self.setMinimumSize(100, 100)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

    def set_image(self, image):
        self.pixmap = QPixmap.fromImage(image) if isinstance(image, QImage) else image
        self.zoom = 1.0
        self.pan = QPointF()
        self.zoom_changed.emit(self.zoom)
        self.update()

    def clear(self, message=None):
        if message is None:message=tr('読み込み中…')
        self.pixmap = QPixmap()
        self.message = message
        self.zoom = 1.0
        self.pan = QPointF()
        self.zoom_changed.emit(self.zoom)
        self.update()

    def set_zoom(self,value):
        self.zoom=max(1.0,min(8.0,float(value)))
        if self.zoom<=1.0:
            self.pan=QPointF()
        self.clamp_pan()
        self.zoom_changed.emit(self.zoom)
        self.update()

    def clamp_pan(self):
        if self.pixmap.isNull():
            self.pan=QPointF()
            return
        size=self.pixmap.size().scaled(self.size(),Qt.AspectRatioMode.KeepAspectRatio)
        limit_x=max(0,(size.width()*self.zoom-self.width())/2)
        limit_y=max(0,(size.height()*self.zoom-self.height())/2)
        self.pan=QPointF(max(-limit_x,min(limit_x,self.pan.x())),
                        max(-limit_y,min(limit_y,self.pan.y())))

    def resizeEvent(self,event):
        self.clamp_pan()
        super().resizeEvent(event)

    def zoom_by(self,multiplier):
        self.set_zoom(self.zoom*multiplier)

    def paintEvent(self, event):
        p = QPainter(self)
        p.fillRect(self.rect(), QColor(theme_color('#0b0b0e')))
        if self.pixmap.isNull():
            p.setPen(QColor(theme_color('#a59bae')))
            p.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, self.message)
        else:
            p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
            size = self.pixmap.size().scaled(self.size(), Qt.AspectRatioMode.KeepAspectRatio)
            width,height=size.width()*self.zoom,size.height()*self.zoom
            x=(self.width()-width)//2+self.pan.x()
            y=(self.height()-height)//2+self.pan.y()
            p.drawPixmap(int(x),int(y),int(width),int(height),self.pixmap)

    def mouseDoubleClickEvent(self, event):
        self.activated.emit()

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            if self.zoom>1.0:
                self.drag_anchor=event.position()
                self.setCursor(Qt.CursorShape.ClosedHandCursor)
            else:
                self.activated.emit()

    def mouseMoveEvent(self,event):
        if self.drag_anchor is not None:
            delta=event.position()-self.drag_anchor
            self.pan+=delta
            self.clamp_pan()
            self.drag_anchor=event.position()
            self.update()
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self,event):
        if event.button()==Qt.MouseButton.LeftButton and self.drag_anchor is not None:
            self.drag_anchor=None
            self.unsetCursor()

    def wheelEvent(self,event):
        if not self.navigate_on_wheel:
            if self.scroll_target is not None:
                bar=self.scroll_target.verticalScrollBar()
                delta=event.pixelDelta().y() or event.angleDelta().y()/120*bar.singleStep()*3
                if delta:
                    bar.setValue(round(bar.value()-delta))
                    event.accept()
                    return
            event.ignore()
            return
        delta=event.angleDelta().y()
        if delta:
            if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
                self.zoom_by(1.2 if delta>0 else 1/1.2)
            else:
                self.wheel_navigated.emit(-1 if delta>0 else 1)
            event.accept()
            return
        super().wheelEvent(event)


class CombinedLibraryJob(LibraryJob):
    def __init__(self,entries,dimensions):
        super().__init__(entries[0]['root'],dimensions)
        self.entries=entries
        self.bundles=[]
        self.unavailable=[]

    def run(self):
        from .accounts import scoped_asset
        assets=[]
        for entry in self.entries:
            try:
                raw=read_catalog(entry['root'])
                status=read_status(entry['root'])
                self.bundles.append((entry,raw,status))
                assets.extend(scoped_asset(a,entry) for a in raw)
                for asset in raw:
                    if asset.sha256 in self.dimensions or asset.kind not in ('image','gif'):continue
                    try:
                        with Image.open(source_path(entry['root'],asset.relative_path)) as image:
                            w,h=image.size
                            if image.getexif().get(274) in (5,6,7,8):w,h=h,w
                            self.dimensions[asset.sha256]=(w,h)
                    except (OSError,ValueError,Image.DecompressionBombError):pass
            except (OSError,ValueError,RuntimeError,sqlite3.Error) as error:
                self.unavailable.append(entry.get('username') or entry['root'].name)
                log.warning('An account library is unavailable: %s',type(error).__name__)
        if not self.bundles:
            self.signals.done.emit([],{},tr('登録済みの保存先を開けません。ドライブの接続を確認してください。'));return
        statuses=[s for _,_,s in self.bundles]
        completed=[s['last_complete'] for s in statuses if s.get('last_complete')]
        self.status={'count':sum(s['count'] for s in statuses),'warnings':sum(s['warnings'] for s in statuses),
                     'errors':sum(s['errors'] for s in statuses),'latest':max((s['latest'] for s in statuses if s.get('latest')),default=None),
                     'last_complete':max(completed,key=lambda r:r['finished_at'],default=None),
                     'issues':[],'unfinished':sum(s.get('unfinished',0) for s in statuses)}
        self.signals.done.emit(assets,self.dimensions,'')


class MainWindow(LanguageMixin,AppearanceMixin,PowerSavingMixin,AccountUiMixin,NavigationMixin,DiscoveryUiMixin,BatchTagUiMixin,ManualTagUiMixin,BackupUiMixin,QMainWindow):
    def __init__(self, data_dir, initial_root=None):
        super().__init__()
        self.store = VaultStore(data_dir)
        self.ui_language=self.store.get('ui_language','ja')
        if self.ui_language not in ('ja','en'):self.ui_language='ja'
        set_language_code(self.ui_language)
        self.white_mode=bool(self.store.get('white_mode',False))
        self._window_immersive=False
        self.cache = Path(data_dir) / 'cache'
        remembered_root = self.store.get('library_root')
        from .accounts import startup_root
        if not initial_root:remembered_root=startup_root(self.store,remembered_root)
        self.library_configured = bool(initial_root or remembered_root)
        self.root = Path(initial_root or remembered_root or DEFAULT_ROOT)
        self.library_id = None
        self.account_scope=''
        self.aggregate_entries=[]
        self._account_changed=False
        if not initial_root and self.library_configured:
            from .accounts import account_groups
            for group in account_groups(self.store):
                if len(group['entries'])>1 and any(e['root'].resolve()==self.root.resolve() for e in group['entries']):
                    self.aggregate_entries=group['entries'];self.account_scope=group['key'];break
        self.manual_definitions = {}
        self.manual_mapping = {}
        self.selected_manual_tags = set()
        self.selected_performance_tags=set()
        self.performance_mode=''
        self.navigation_history=[]
        self._last_filter_state=None
        self._restoring_navigation=False
        self._fullscreen_browse_return=None
        self.views = {}
        self.view_debounce = {}
        self.discovery_seed = os.urandom(16).hex()
        self.assets = []
        self.visible = []
        self.matches = []
        self.performance_by_post = {}
        self.content_groups = {}
        self.group_duplicates = True
        self.store.set('group_duplicates',True)
        self.sort_order = self.store.get('sort_order','newest')
        if self.sort_order not in ('newest','oldest','random'):
            self.sort_order='newest'
        if self.sort_order=='random':
            import secrets
            self.random_seed=secrets.token_hex(24)
        else:
            self.random_seed=''
        self.favorites = set()
        self.hidden_hashes = set()
        self.hidden_only = False
        self.current = None
        self.current_image = QImage()
        self.image_error = None
        self.image_token = 0
        self.image_jobs = {}
        self.pending_copy = None
        self.dimensions_pending = {}
        self.loading = False
        self.closing = False
        self._minimized_idle=False
        self._power_video_seek=None
        self.jobs = QThreadPool(self)
        self.jobs.setMaxThreadCount(2)
        self.setWindowTitle(f'X Archive Gallery — v{__version__}')
        self.setMinimumSize(880, 640)
        self.resize(1380, 930)
        self.setStyleSheet(STYLE)
        self.importer = ImportController(self.store,self)
        self.exit_after_import = False
        self.backup_status = {}
        self.build_ui()
        self.apply_appearance()
        self.thumbs = ThumbnailManager(self.cache, self)
        self.thumbs.ready.connect(self.thumbnail_ready)
        self.thumbs.progress.connect(self.thumbnail_progress)
        self.thumbs.failed.connect(self.thumbnail_failed)
        self.gallery.needed.connect(self.need_thumbnails)
        self.gallery.corrupt.connect(self.thumbs.invalidate)
        self.flush_timer = QTimer(self)
        self.flush_timer.setSingleShot(True)
        self.flush_timer.timeout.connect(self.flush_dimensions)
        self.search_timer = QTimer(self)
        self.search_timer.setSingleShot(True)
        self.search_timer.timeout.connect(self.apply_filters)
        self.search.textChanged.connect(lambda: self.search_timer.start(120))
        self.toast_timer = QTimer(self)
        self.toast_timer.setSingleShot(True)
        self.toast_timer.timeout.connect(lambda: self.notice.setText(''))
        self.setup_shortcuts()
        self.importer.activity.connect(self.import_activity)
        self.importer.changed.connect(self.import_changed)
        self.importer.completed.connect(self.import_completed)
        QTimer.singleShot(50, self.refresh)

    def build_ui(self):
        shell = QWidget()
        shell.setObjectName('shell')
        self.setCentralWidget(shell)
        layout = QVBoxLayout(shell)
        layout.setContentsMargins(0,0,0,0)
        layout.setSpacing(0)
        self.app_header = QFrame()
        self.app_header.setObjectName('top')
        top_row = QHBoxLayout(self.app_header)
        top_row.setContentsMargins(20,8,18,8)
        top_row.setSpacing(12)
        self.home_button=QPushButton()
        self.home_button.setObjectName('homeBrand')
        self.home_button.setAccessibleName(tr('ホームへ戻る · X Archive Gallery'))
        self.home_button.setToolTip(tr('ホームへ戻る：条件を解除してすべての作品を新しい順で表示'))
        self.home_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.home_button.clicked.connect(self.go_home)
        home_layout=QHBoxLayout(self.home_button)
        home_layout.setContentsMargins(0,0,0,0)
        home_layout.setSizeConstraint(QLayout.SizeConstraint.SetFixedSize)
        home_layout.setSpacing(16)
        monogram=label('X','monogram')
        monogram.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        home_layout.addWidget(monogram)
        brand = QVBoxLayout()
        brand.setSpacing(2)
        for text,name in [('X ARCHIVE GALLERY','brand'),('YOUR ARCHIVE, BEAUTIFULLY KEPT.','tagline')]:
            item=label(text,name)
            item.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
            brand.addWidget(item)
        home_layout.addLayout(brand)
        top_row.addWidget(self.home_button)
        top_row.addStretch()
        self.search = QLineEdit()
        self.search.setPlaceholderText(tr('ファイル名・投稿ID・#タグ'))
        self.search.setAccessibleName(tr('投稿ID・ファイル名・手動タグで検索'))
        self.search.setToolTip(tr('タグ名でも検索できます。#白髪 #角 は両方を持つ作品に絞ります。空白を含むタグは #"顔 アップ" と入力します。'))
        self.search.setClearButtonEnabled(True)
        self.search.setMinimumWidth(200)
        self.search.setMaximumWidth(420)
        top_row.addWidget(self.search, 1)
        self.refresh_button = button(tr('↻  ライブラリ更新'), self.refresh, tip=tr('バックアップに追加された作品を読み込みます（F5）'))
        self.refresh_button.setText('↻')
        self.refresh_button.setAccessibleName(tr('ライブラリ更新'))
        top_row.addWidget(self.refresh_button)
        self.import_button = button(tr('アーカイブを取り込む'),self.toggle_import_panel)
        top_row.addWidget(self.import_button)
        settings = QToolButton()
        settings.setText('•••')
        settings.setToolTip(tr('ライブラリとアプリの設定'))
        settings.setAccessibleName(tr('ライブラリとアプリの設定'))
        settings.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        menu = QMenu(settings)
        menu.addAction(tr('既存のバックアップを開く…'), self.choose_library)
        menu.addAction(tr('新しくバックアップを作る…'), self.open_import)
        menu.addAction(tr('不具合報告用ログを保存…'), self.export_diagnostics)
        menu.addAction(tr('アプリデータの保存先を開く'), lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.store.directory))))
        menu.addAction(tr('サムネイルを確認・再生成'), self.recheck_cache)
        menu.addAction(tr('サムネイルキャッシュを削除…'), self.clear_thumbnail_cache)
        menu.addSeparator()
        self.white_mode_action=menu.addAction(tr('ホワイトモード'))
        self.white_mode_action.setCheckable(True)
        self.white_mode_action.toggled.connect(self.set_white_mode)
        self.build_language_menu(menu)
        menu.addSeparator()
        menu.addAction(tr('使い方'), self.show_help)
        menu.addAction(tr('ライセンス・配布資料'), self.open_distribution_materials)
        settings.setMenu(menu)
        top_row.addWidget(settings)
        layout.addWidget(self.app_header)
        self.build_backup_strip(layout)

        self.gallery_toolbar = QFrame()
        self.gallery_toolbar.setObjectName('toolbar')
        self.toolbar_layout = QVBoxLayout(self.gallery_toolbar)
        self.toolbar_layout.setContentsMargins(18,3,18,3)
        self.toolbar_layout.setSpacing(3)
        self.gallery_toolbar.setStyleSheet('QComboBox { font-size:13px; padding:5px 8px; min-width:72px; } QPushButton { font-size:13px; padding:5px 7px; } QPushButton#tab { padding:5px 4px; margin-right:4px; }')
        self.toolbar_primary = tools = QHBoxLayout()
        self.toolbar_layout.addLayout(tools)
        tools.setSpacing(8)
        self.account_switch=QComboBox()
        self.account_switch.setObjectName('accountSwitch')
        self.account_switch.setAccessibleName(tr('表示するXアカウント'))
        self.account_switch.setToolTip(tr('@アカウントを選択。すべてのアカウントをまとめて表示することもできます。'))
        self.account_switch.setMinimumWidth(145)
        self.account_switch.setMaximumWidth(205)
        self.rebuild_account_menu()
        self.account_switch.currentIndexChanged.connect(self.switch_account)
        tools.addWidget(self.account_switch)
        self.back_button=button(tr('← 戻る'),self.go_back,tip=tr('ひとつ前の絞り込み・表示位置へ戻る（Alt+←）'))
        self.back_button.setEnabled(False)
        tools.addWidget(self.back_button)
        self.all_button = button(tr('すべての作品 ▼'),self.open_collection_menu,'tab')
        self.favorites_button = button(tr('♡  お気に入り · 0'), lambda: self.set_favorites_only(True), 'tab')
        self.hidden_mode_button = button(tr('非表示'), lambda _checked=False: self.set_hidden_only(not self.hidden_only), 'tab')
        for b in (self.all_button,self.favorites_button,self.hidden_mode_button):
            b.setCheckable(True)
            if b==self.all_button:tools.addWidget(b)
            else:b.hide()
        self.all_button.setChecked(True)
        self.tag_filter_button = button(tr('タグ ▾'),lambda:self.manual_tag_menu(self.tag_filter_button))
        self.tag_filter_button.hide()
        self.help_button=button(tr('使い方'),self.show_help,tip=tr('初めての方はこちら。見る・探す・タグ付けを案内します'))
        tools.addWidget(self.help_button)
        tools.addStretch()
        self.toolbar_filters = QWidget()
        filters = QHBoxLayout(self.toolbar_filters)
        filters.setContentsMargins(0,0,0,0)
        filters.setSpacing(8)
        tools.addWidget(self.toolbar_filters)
        self.toolbar_stacked = False
        self.sort_combo = QComboBox()
        self.sort_combo.setAccessibleName(tr('作品の並び順'))
        self.sort_combo.addItem(tr('新しい順'),'newest')
        self.sort_combo.addItem(tr('古い順'),'oldest')
        self.sort_combo.addItem(tr('ランダム'),'random')
        self.sort_combo.setToolTip(tr('並び順を選びます。高成績・NO.1の絞り込みは「すべての作品」メニューにあります。'))
        self.sort_combo.setCurrentIndex(max(0,self.sort_combo.findData(self.sort_order)))
        self.sort_combo.currentIndexChanged.connect(self.change_sort_order)
        filters.addWidget(self.sort_combo)
        self.year = QComboBox()
        self.year.setAccessibleName(tr('投稿年'))
        self.year.addItem(tr('すべての年'), '')
        self.month = QComboBox()
        self.month.setAccessibleName(tr('投稿月'))
        self.month.addItem(tr('すべての月'), '')
        for m in range(1,13):
            self.month.addItem(trf('{0}月', m), str(m))
        self.year.currentIndexChanged.connect(self.year_filter_changed)
        self.month.currentIndexChanged.connect(self.apply_filters)
        self.media_kind=QComboBox()
        self.media_kind.setAccessibleName(tr('メディアの種類'))
        self.media_kind.addItem(tr('すべて'),'')
        self.media_kind.addItem(tr('画像のみ'),'image')
        self.media_kind.addItem(tr('GIFのみ'),'gif')
        self.media_kind.addItem(tr('動画のみ'),'video')
        self.media_kind.setToolTip(tr('ギャラリー、ランダム表示、スライドショーの対象を切り替えます'))
        self.media_kind.setFixedWidth(104)
        self.media_kind.currentIndexChanged.connect(self.apply_filters)
        filters.addWidget(self.year)
        filters.addWidget(self.month)
        filters.addWidget(self.media_kind)
        filters.addStretch()
        self.count = label(tr('— 作品'), 'muted')
        self.count.setSizePolicy(QSizePolicy.Policy.Minimum,QSizePolicy.Policy.Preferred)
        self.count.setMinimumWidth(60)
        self.count.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self.slideshow_start=button(tr('▶ スライドショー'),self.start_slideshow,tip=tr('現在の作品一覧でスライドショーを開始'))
        self.slideshow_start.setAccessibleName(tr('スライドショーを開始'))
        self.slideshow_start.setMinimumWidth(125)
        filters.addWidget(self.slideshow_start)
        filters.addWidget(self.count)
        layout.addWidget(self.gallery_toolbar)
        self.build_batch_bar(layout)

        self.stack = QStackedWidget()
        self.browse = QWidget()
        browse_layout = QHBoxLayout(self.browse)
        browse_layout.setContentsMargins(0,0,0,0)
        browse_layout.setSpacing(0)
        self.gallery = Gallery(self.cache)
        self.gallery.multi_changed.connect(self.multi_selection_changed)
        self.gallery.tag_clicked.connect(lambda name:self.toggle_manual_filter(next(i for i,n in self.manual_definitions.items() if n==name)))
        self.gallery.performance_tag_clicked.connect(self.toggle_performance_filter)
        self.thumbnail_columns = {'極小': 0, '小': 1, '中': 0, '大': -1, '極大': -2}
        saved_size = self.store.get('thumbnail_size')
        if saved_size not in self.thumbnail_columns:
            # Older releases stored a free-form slider value. Start with a roomier
            # preset as requested, while keeping the old key for compatibility.
            saved_size = '大'
            self.store.set('thumbnail_size', saved_size)
        self.gallery.miniature = saved_size == '極小'
        self.gallery.width_target = 90 if self.gallery.miniature else 280
        self.gallery.column_adjustment = self.thumbnail_columns[saved_size]
        self.gallery.selected.connect(self.browse_asset)
        self.gallery.activated.connect(self.open_fullscreen)
        self.gallery.favorite.connect(self.toggle_favorite)
        self.gallery.context.connect(self.context_menu)
        browse_layout.addWidget(self.gallery, 1)
        self.build_details(browse_layout)
        self.build_import_panel(browse_layout)
        self.build_discovery_panel(browse_layout)
        self.stack.addWidget(self.browse)
        self.build_viewer()
        layout.addWidget(self.stack, 1)

        self.app_footer = QFrame()
        self.app_footer.setObjectName('footer')
        foot = QHBoxLayout(self.app_footer)
        foot.setContentsMargins(24,7,24,7)
        self.library_label = label(tr('X作品バックアップ'), 'muted')
        foot.addWidget(self.library_label)
        self.notice = label('', 'muted')
        self.notice.setSizePolicy(QSizePolicy.Policy.Ignored,QSizePolicy.Policy.Preferred)
        foot.addWidget(self.notice, 1)
        self.progress = label('', 'muted')
        foot.addWidget(self.progress)
        self.size_combo = QComboBox()
        self.size_combo.setObjectName('previewSize')
        self.size_combo.setFixedSize(60,24)
        self.size_combo.setStyleSheet('QComboBox#previewSize { font-size:12px; min-width:0; padding:2px 15px 2px 5px; border-radius:3px; background:transparent; } QComboBox#previewSize::drop-down { width:13px; } QComboBox#previewSize QAbstractItemView { min-width:70px; }')
        self.size_combo.setAccessibleName(tr('作品の表示サイズ'))
        self.size_combo.setToolTip(tr('極小はたくさんの作品を見渡せる小さな表示です。タグは作品をクリックして確認できます。中は通常のウィンドウ幅でも2列を維持します。小は1列多く、大は1列少なく、極大は2列少なく表示します'))
        for preset in ('極大','大','中','小','極小'):
            self.size_combo.addItem(tr(preset), preset)
        self.size_combo.setCurrentIndex(self.size_combo.findData(saved_size))
        self.size_combo.currentIndexChanged.connect(self.change_size_preset)
        foot.addWidget(self.size_combo)
        foot.addWidget(label(f'v{__version__}', 'muted'))
        layout.addWidget(self.app_footer)
        self.multi_selection_changed()

    def build_details(self, browse_layout):
        self.details = QFrame()
        self.details.setObjectName('details')
        self.details.setFixedWidth(320)
        outer = QVBoxLayout(self.details)
        outer.setContentsMargins(0,0,0,0)
        scroll = QScrollArea()
        self.details_scroll=scroll
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOn)
        content = QWidget()
        content.setObjectName('details')
        column = QVBoxLayout(content)
        column.setContentsMargins(23,15,23,24)
        column.setSpacing(14)
        head = QHBoxLayout()
        head.addWidget(label(tr('作品の情報'), 'field'))
        head.addStretch()
        self.kind = label('', 'field')
        head.addWidget(self.kind)
        head.addWidget(button('✕', self.close_details, tip=tr('詳細を閉じる')))
        column.addLayout(head)
        self.build_manual_tags(column)
        self.preview = ImageView()
        self.preview.navigate_on_wheel=False
        self.preview.scroll_target=scroll
        self.preview.setFixedHeight(260)
        self.preview.setToolTip(tr('クリックで大きく表示'))
        self.preview.activated.connect(lambda: self.open_fullscreen(self.current))
        column.addWidget(self.preview)
        self.detail_actions = QWidget()
        self.detail_actions.setObjectName('detailActions')
        actions = QHBoxLayout(self.detail_actions)
        actions.setContentsMargins(0,0,0,0)
        actions.setSpacing(3)
        self.favorite_button = button(tr('♡ お気に入り'), lambda: self.toggle_favorite(self.current), 'detailAction')
        self.favorite_button.setCheckable(True)
        actions.addWidget(self.favorite_button)
        self.hidden_button = button(tr('非表示'), lambda _checked=False: self.toggle_hidden_asset(self.current), 'detailAction')
        self.hidden_button.setCheckable(True)
        actions.addWidget(self.hidden_button)
        self.copy_button = QToolButton()
        self.copy_button.setObjectName('detailAction')
        self.copy_button.setText(tr('コピー ▾'))
        self.copy_button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self.copy_button.setMenu(self.make_copy_menu(self.copy_button))
        actions.addWidget(self.copy_button)
        actions.addStretch()
        column.addWidget(self.detail_actions)
        self.occurrence_label = label('', 'field', True)
        column.addWidget(self.occurrence_label)
        self.occurrence_picker = QComboBox()
        self.occurrence_picker.setAccessibleName(tr('同じ画像を使った投稿を切り替え'))
        self.occurrence_picker.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        self.occurrence_picker.setMinimumContentsLength(12)
        self.occurrence_picker.activated.connect(self.choose_occurrence)
        column.addWidget(self.occurrence_picker)
        self.fields = {}
        for key, title in [('date',tr('投稿日 · 日本時間')),('post',tr('投稿ID')),('filename',tr('ファイル名')),('order',tr('添付順')),('path',tr('保存先'))]:
            column.addWidget(label(title, 'field'))
            value = label('', '', True)
            value.setTextFormat(Qt.TextFormat.PlainText)
            value.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            value.setMinimumWidth(0)
            value.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
            column.addWidget(value)
            self.fields[key] = value
        self.post_info_label=label('', 'muted',True)
        column.addWidget(self.post_info_label)
        self.performance_summary=label('', 'muted', True)
        column.addWidget(self.performance_summary)
        self.series_title = label(tr('同じ投稿の作品'), 'field')
        column.addWidget(self.series_title)
        self.series_widget = QWidget()
        self.series = QHBoxLayout(self.series_widget)
        self.series.setContentsMargins(0,0,0,0)
        self.series.setSpacing(6)
        column.addWidget(self.series_widget)
        column.addWidget(button(tr('保存先を開く'), self.reveal_file))
        column.addStretch()
        scroll.setWidget(content)
        outer.addWidget(scroll)
        self.details.hide()
        browse_layout.addWidget(self.details)

    def build_viewer(self):
        viewer = QWidget()
        self.viewer=viewer
        viewer.setMouseTracking(True)
        column = QVBoxLayout(viewer)
        self.viewer_layout=column
        column.setContentsMargins(12,6,12,8)
        column.setSpacing(4)
        top = QHBoxLayout()
        top.setContentsMargins(0,0,0,0)
        top.setSpacing(4)
        info=QWidget()
        info_column=QVBoxLayout(info)
        info_column.setContentsMargins(4,0,4,0)
        info_column.setSpacing(1)
        self.viewer_title = label('', 'muted')
        self.viewer_title.setMinimumWidth(0)
        self.viewer_title.setSizePolicy(QSizePolicy.Policy.Ignored,QSizePolicy.Policy.Preferred)
        info_column.addWidget(self.viewer_title)
        top.addWidget(info,1)
        self.viewer_copy = button(tr('画像をコピー'), self.copy_image, tip=tr('Ctrl+C。元画像の解像度でコピーします'))
        top.addWidget(self.viewer_copy)
        self.open_media_button = button(tr('動画を開く'), self.open_media)
        top.addWidget(self.open_media_button)
        self.viewer_fullscreen=button(tr('⛶ 全画面'),self.toggle_fullscreen,tip=tr('全画面表示（F11）'))
        top.addWidget(self.viewer_fullscreen)
        self.viewer_window_fit=button(tr('□ ウィンドウいっぱい'),self.toggle_window_immersive,tip=tr('ウィンドウの大きさはそのままで、画像をいっぱいに表示。Escで戻ります'))
        top.addWidget(self.viewer_window_fit)
        self.viewer_close=button('×',self.close_large,tip=tr('ギャラリーへ戻る（Esc）'))
        self.viewer_close.setAccessibleName(tr('スライドショーを閉じる'))
        self.viewer_close.setFixedWidth(32)
        top.addWidget(self.viewer_close)
        self.viewer_top=QWidget()
        self.viewer_top.setLayout(top)
        column.addWidget(self.viewer_top)
        self.viewer_previous=button('❮', lambda: self.step(-1), tip=tr('前の作品（←）'))
        self.viewer_previous.setFixedWidth(32)
        top.insertWidget(0,self.viewer_previous)
        self.viewer_media=QStackedWidget()
        self.large = ImageView()
        self.large.activated.connect(lambda: None)
        self.viewer_media.addWidget(self.large)
        self.video_widget=QVideoWidget()
        self.video_widget.setMouseTracking(True)
        self.video_widget.setStyleSheet('background:#050506;')
        self.viewer_media.addWidget(self.video_widget)
        self.viewer_next=button('❯', lambda: self.step(1), tip=tr('次の作品（→）'))
        self.viewer_next.setFixedWidth(32)
        top.insertWidget(1,self.viewer_next)
        column.addWidget(self.viewer_media,1)
        self.viewer_meta = label('', 'muted')
        self.viewer_meta.setMinimumWidth(0)
        self.viewer_meta.setSizePolicy(QSizePolicy.Policy.Ignored,QSizePolicy.Policy.Preferred)
        info_column.addWidget(self.viewer_meta)
        self.zoom_controls=QWidget()
        zoom_row=QHBoxLayout(self.zoom_controls)
        zoom_row.setContentsMargins(0,0,0,0)
        zoom_row.setSpacing(2)
        zoom_row.addWidget(button('−',lambda:self.large.zoom_by(1/1.25),tip=tr('縮小')))
        zoom_row.addWidget(button(tr('全体表示'),lambda:self.large.set_zoom(1.0),tip=tr('画面内に全体を表示')))
        self.zoom_label=label('100%','muted')
        self.zoom_label.setToolTip(tr('画面に収まる表示を100%とした拡大率。Ctrl+ホイールでも拡大できます。'))
        self.large.zoom_changed.connect(lambda value:self.zoom_label.setText(f'{value:.0%}'))
        zoom_row.addWidget(self.zoom_label)
        zoom_row.addWidget(button('+',lambda:self.large.zoom_by(1.25),tip=tr('拡大')))
        column.addWidget(self.zoom_controls)
        self.video_controls=QWidget()
        video_row=QHBoxLayout(self.video_controls)
        video_row.setContentsMargins(0,0,0,0)
        self.video_play=button(tr('▶ 再生'),self.toggle_video_playback,'primary')
        self.video_play.setAccessibleName(tr('動画を再生または一時停止'))
        video_row.addWidget(self.video_play)
        self.audio_enabled=QCheckBox(tr('音声 ON'))
        self.audio_enabled.setAccessibleName(tr('動画の音声をオン'))
        self.audio_enabled.setToolTip(tr('初期状態では消音です。チェックで動画の音を出します。'))
        self.audio_enabled.toggled.connect(self.set_audio_enabled)
        video_row.addWidget(self.audio_enabled)
        self.video_position=QSlider(Qt.Orientation.Horizontal)
        self.video_position.setRange(0,0)
        self.video_position.setAccessibleName(tr('動画の再生位置'))
        video_row.addWidget(self.video_position,1)
        self.video_clock=label('0:00 / 0:00','muted')
        video_row.addWidget(self.video_clock)
        self.video_rate=QComboBox()
        self.video_rate.setAccessibleName(tr('動画の再生速度'))
        for text,rate in [('0.75×',0.75),('1×',1.0),('1.25×',1.25),('1.5×',1.5),('2×',2.0)]:
            self.video_rate.addItem(text,rate)
        self.video_rate.setCurrentIndex(1)
        self.video_rate.currentIndexChanged.connect(self.change_video_rate)
        video_row.addWidget(self.video_rate)
        self.video_controls.hide()
        column.addWidget(self.video_controls)
        self.media_status=label('', 'muted', True)
        column.addWidget(self.media_status)
        self.media_status.hide()
        self.audio_output=QAudioOutput(self)
        self.media_player=QMediaPlayer(self)
        self.media_player.setAudioOutput(self.audio_output)
        self.media_player.setVideoOutput(self.video_widget)
        self.audio_output.setVolume(0.8)
        self.audio_output.setMuted(True)
        self.media_player.playbackStateChanged.connect(self.update_video_play_button)
        self.media_player.positionChanged.connect(self.update_video_position)
        self.media_player.durationChanged.connect(self.update_video_duration)
        self.media_player.mediaStatusChanged.connect(self.video_media_status_changed)
        self.media_player.errorOccurred.connect(self.video_playback_error)
        self.video_position.sliderMoved.connect(self.media_player.setPosition)
        self._video_duration=0
        self._video_source_identity=None
        controls=QHBoxLayout()
        self.slideshow_controls=QWidget()
        self.slideshow_controls.setLayout(controls)
        controls.setContentsMargins(0,0,0,0)
        controls.setSpacing(6)
        self.autoplay=QCheckBox(tr('自動切り替え'))
        self.autoplay.setToolTip(tr('チェックすると表示中のギャラリー作品を順番に表示します'))
        self.autoplay.toggled.connect(self.toggle_autoplay)
        controls.addWidget(self.autoplay)
        self.pause_slideshow_button=button(tr('⏸ 一時停止'),self.toggle_slideshow_pause)
        controls.addWidget(self.pause_slideshow_button)
        self.slideshow_speed=QComboBox()
        self.slideshow_speed.setAccessibleName(tr('スライドショーの速度'))
        self.slideshow_speed.addItem(tr('遅め · 8秒'),8000)
        self.slideshow_speed.addItem(tr('中 · 4秒'),4000)
        self.slideshow_speed.addItem(tr('速め · 2秒'),2000)
        self.slideshow_speed.setCurrentIndex(1)
        self.slideshow_speed.currentIndexChanged.connect(self.change_slideshow_speed)
        controls.addWidget(self.slideshow_speed)
        column.addWidget(self.slideshow_controls)
        self.viewer_controls=QWidget()
        self.viewer_controls.setObjectName('viewerControls')
        compact=QHBoxLayout(self.viewer_controls)
        compact.setContentsMargins(0,0,0,0)
        compact.setSpacing(8)
        column.removeWidget(self.zoom_controls)
        column.removeWidget(self.slideshow_controls)
        compact.addWidget(self.zoom_controls)
        compact.addStretch()
        compact.addWidget(self.slideshow_controls)
        column.insertWidget(1,self.viewer_controls)
        column.removeWidget(self.video_controls)
        column.insertWidget(2,self.video_controls)
        column.removeWidget(self.media_status)
        column.insertWidget(3,self.media_status)
        self.slideshow_timer=QTimer(self)
        self.slideshow_timer.timeout.connect(lambda:self.step(1))
        self.large.wheel_navigated.connect(self.step)
        self.fullscreen_controls=QFrame(viewer)
        self.fullscreen_controls.setObjectName('fullscreenControls')
        fs=QHBoxLayout(self.fullscreen_controls)
        fs.setContentsMargins(10,7,10,7)
        fs.setSpacing(6)
        fs.addWidget(button('❮',lambda:self.step(-1),tip=tr('前の作品')))
        self.fullscreen_pause=button('⏸',self.toggle_fullscreen_pause,tip=tr('再生またはスライドショーを一時停止／再開'))
        fs.addWidget(self.fullscreen_pause)
        fs.addWidget(button('❯',lambda:self.step(1),tip=tr('次の作品')))
        self.fullscreen_status=label('', 'muted', True)
        self.fullscreen_status.setMaximumWidth(220)
        self.fullscreen_status.hide()
        fs.addWidget(self.fullscreen_status)
        self.fullscreen_audio=QCheckBox(tr('音声'))
        self.fullscreen_audio.toggled.connect(self.set_audio_enabled)
        fs.addWidget(self.fullscreen_audio)
        self.fullscreen_zoom=QWidget()
        fs_zoom=QHBoxLayout(self.fullscreen_zoom)
        fs_zoom.setContentsMargins(0,0,0,0)
        fs_zoom.setSpacing(2)
        fs_zoom.addWidget(button('−',lambda:self.large.zoom_by(1/1.25),tip=tr('縮小')))
        self.fullscreen_fit=button(tr('全体表示'),lambda:self.large.set_zoom(1.0),tip=tr('全体表示に戻す（Ctrl+0）'))
        fs_zoom.addWidget(self.fullscreen_fit)
        fs_zoom.addWidget(button('+',lambda:self.large.zoom_by(1.25),tip=tr('拡大。ドラッグで表示位置を移動')))
        fs.addWidget(self.fullscreen_zoom)
        self.fullscreen_pin=QToolButton()
        self.fullscreen_pin.setText(tr('UI固定'))
        self.fullscreen_pin.setCheckable(True)
        self.fullscreen_pin.setToolTip(tr('操作バーを表示したままにする'))
        self.fullscreen_pin.toggled.connect(self.pin_fullscreen_controls)
        fs.addWidget(self.fullscreen_pin)
        self.fullscreen_exit=button(tr('全画面を終了'),self.leave_immersive,tip=tr('表示を戻す（Esc）'))
        fs.addWidget(self.fullscreen_exit)
        self.fullscreen_controls.adjustSize()
        self.fullscreen_controls.hide()
        for widget in [self.fullscreen_controls,*self.fullscreen_controls.findChildren(QWidget)]:
            widget.setMouseTracking(True)
        self.fullscreen_hide_timer=QTimer(self)
        self.fullscreen_hide_timer.setSingleShot(True)
        self.fullscreen_hide_timer.setInterval(2600)
        self.fullscreen_hide_timer.timeout.connect(self.hide_fullscreen_controls)
        self._fullscreen_pinned=False
        self._restore_maximized=False
        self._slideshow_paused=False
        self.update_slideshow_pause_button()
        QApplication.instance().installEventFilter(self)
        self.stack.addWidget(viewer)

    def setup_shortcuts(self):
        def shortcut(key, callback):
            action = QAction(self)
            action.setShortcut(QKeySequence(key))
            action.triggered.connect(callback)
            self.addAction(action)
            return action
        shortcut('Ctrl+C', self.copy_image)
        shortcut('Ctrl+Shift+C', self.copy_file)
        shortcut('Ctrl+F', self.search.setFocus)
        shortcut('F5', self.refresh)
        shortcut('Alt+Left',self.go_back)
        shortcut('Escape', self.escape)
        shortcut('F11', self.toggle_fullscreen)
        shortcut('Ctrl+F11',self.toggle_window_immersive)
        shortcut('Ctrl+0', lambda:self.large.set_zoom(1.0))
        self.pause_action=shortcut('Space',self.toggle_fullscreen_pause)
        self.pause_action.setEnabled(False)
        self.previous_action = shortcut('Left', lambda: self.step(-1))
        self.next_action = shortcut('Right', lambda: self.step(1))
        self.previous_action.setEnabled(False)
        self.next_action.setEnabled(False)

    def make_copy_menu(self, parent, asset=None):
        menu = QMenu(parent)
        target = asset or self.current
        image_title = self.copy_image_title(target)
        menu.addAction(image_title + '  (Ctrl+C)', lambda: self.copy_image(asset))
        menu.addAction(tr('ファイルをコピー  (Ctrl+Shift+C)'), lambda: self.copy_file(asset))
        menu.addSeparator()
        menu.addAction(tr('投稿IDをコピー'), lambda: self.copy_text(((asset or self.current).post_id or tr('不明')) if (asset or self.current) else ''))
        menu.addAction(tr('保存先パスをコピー'), lambda: self.copy_text(str(self.asset_source_path(asset or self.current)) if (asset or self.current) else ''))
        return menu

    def asset_source_path(self,asset):
        if asset.asset_key.startswith('warning:'):
            from .store import warning_media_path
            return warning_media_path(self.store.directory,asset.relative_path)
        return source_path(Path(asset.library_root) if asset.library_root else self.root,asset.relative_path)

    def warning_assets_added(self):
        self.refresh()

    @staticmethod
    def copy_image_title(asset):
        if asset and asset.kind in ('video','gif'):
            return tr('プレビュー画像をコピー')
        return tr('画像をコピー')

    def toast(self, text):
        self.notice.setText(text)
        self.notice.setToolTip(text)
        self.toast_timer.start(5000)

    def choose_library(self):
        if self.loading or self.importer.active or self.import_panel.analytics_busy:
            self.toast(tr('取り込み処理が終わってからライブラリを変更できます'))
            return
        folder = QFileDialog.getExistingDirectory(self, tr('X作品バックアップのフォルダーを選択'), str(self.root.parent))
        if folder:
            target=Path(folder)
            if (target/'.system/catalog.sqlite3').is_file():
                self.refresh(target)
            else:
                self.open_import()
                self.import_panel.set_destination(target)

    def refresh(self, proposed_root=None):
        if self.closing:
            return
        if not self.library_configured and not isinstance(proposed_root, Path):
            self.update_backup_status({})
            self.progress.setText(tr('アーカイブを取り込むか、既存ライブラリを選択してください'))
            self.library_label.setText(tr('ライブラリ未選択'))
            self.gallery.empty_text = tr('あなたの作品を、ここに。\n右の①から始めましょう。\nアーカイブZIPだけで使えます。\n迷ったら「使い方」を開いてください。')
            self.gallery.viewport().update()
            QTimer.singleShot(0,self.open_import)
            return
        if self.loading:
            self.refresh_pending = True
            return
        if self.importer.active:
            self.toast(tr('取り込み終了後に自動更新します'))
            return
        if not isinstance(proposed_root, Path):
            proposed_root = self.root
        else:
            self.aggregate_entries=[]
            self.account_scope=''
        if self.store.directory.is_relative_to(proposed_root.resolve()):
            QMessageBox.warning(self,tr('ライブラリを選択できません'),tr('アプリデータの保存先と、バックアップの保存先は分けてください。'))
            return
        self.refresh_pending = False
        self.loading = True
        self.refresh_scroll = self.gallery.verticalScrollBar().value()
        self.proposed_root = proposed_root
        self.refresh_button.setEnabled(False)
        self.analytics_import_button.setEnabled(False)
        self.refresh_button.setText(tr('読み込み中…'))
        self.progress.setText(tr('ライブラリを読み込み中…'))
        self.load_job = (CombinedLibraryJob(self.aggregate_entries,self.store.dimensions()) if self.aggregate_entries
                         else LibraryJob(proposed_root, self.store.dimensions()))
        self.load_job.signals.done.connect(self.library_loaded)
        self.jobs.start(self.load_job)

    def library_loaded(self, assets, dimensions, error):
        if self.closing:
            return
        self.loading = False
        self.refresh_button.setEnabled(True)
        self.analytics_import_button.setEnabled(True)
        self.refresh_button.setText('↻')
        if error:
            self.account_scope=getattr(self,'_loaded_account_scope','')
            self.aggregate_entries=getattr(self,'_loaded_aggregate_entries',[])
            self.load_job=getattr(self,'_loaded_library_job',self.load_job)
            self._account_changed=False
            self.rebuild_account_menu()
            log.warning('Library load failed')
            self.progress.setText(tr('ライブラリを確認してください'))
            if not self.assets:
                self.gallery.empty_text = tr('ライブラリを開けませんでした。\n右上の ••• から「既存のバックアップを開く」を選んでください。')
                self.gallery.viewport().update()
            from .diagnostics import friendly_error
            QMessageBox.warning(self, tr('ライブラリを開けません'), friendly_error(ValueError(error),tr('ライブラリの読み込み')))
            return
        root_changed = self.root.resolve() != self.proposed_root.resolve() or self._account_changed
        self._account_changed=False
        self.library_configured = True
        self._loaded_account_scope=self.account_scope
        self._loaded_aggregate_entries=self.aggregate_entries
        self._loaded_library_job=self.load_job
        self.root = self.proposed_root
        if self.aggregate_entries:
            from .accounts import scoped_asset
            self.library_id=None
            self.assets=list(assets)
            for entry,raw,status in self.load_job.bundles:
                self.store.consolidate_catalog_aliases(entry['library_id'],raw)
                self.assets.extend(scoped_asset(a,entry) for a in self.store.warning_assets(entry['library_id']))
                self.store.reconcile_analytics(entry['library_id'],raw+self.store.warning_assets(entry['library_id']))
            self.load_combined_annotations()
        else:
            from .accounts import learn_existing_account
            self.library_id = self.store.library(self.root)
            self.store.consolidate_catalog_aliases(self.library_id,assets)
            learn_existing_account(self.store,self.root,self.load_job.status)
            self.store.set('library_root', str(self.root))
            self.favorites = self.store.favorites(self.library_id)
            self.hidden_hashes = self.store.hidden_hashes(self.library_id)
            self.assets = assets+self.store.warning_assets(self.library_id)
            self.views = self.store.asset_views(self.library_id)
        self.update_favorites_count()
        if root_changed:
            if not self.import_panel.awaiting_analytics and (not self.importer.root or self.importer.root.resolve()!=self.root.resolve()):
                self.import_panel.clear_csv()
            self.selected_manual_tags.clear()
            self.selected_performance_tags.clear();self.performance_mode=''
            self.navigation_history.clear();self._last_filter_state=None
        self.reload_manual_tags()
        if self.library_id:self.store.reconcile_analytics(self.library_id,self.assets)
        self.update_analytics_status()
        self.content_groups = group_index(self.assets)
        self.gallery.group_counts = {key:len(value) for key,value in self.content_groups.items()}
        self.gallery.dimensions = dimensions
        self.store.save_dimensions([(sha, *size) for sha, size in dimensions.items()])
        self.gallery.favorites = self.favorites
        self.gallery.hidden_hashes = self.hidden_hashes
        self.gallery.failed.clear()
        old_year = self.year.currentData()
        self.year.blockSignals(True)
        self.year.clear()
        self.year.addItem(tr('すべての年'),'')
        for year in sorted({a.year for a in self.assets if a.year}, reverse=True):
            self.year.addItem(year + tr('年'), year)
        self.year.addItem(tr('期間不明'), UNKNOWN_YEAR)
        index = self.year.findData(old_year)
        self.year.setCurrentIndex(max(0,index))
        self.year.blockSignals(False)
        self.year_filter_changed()
        self.hidden_mode_button.setText(trf('非表示 · {0:,}', len(self.hidden_hashes)))
        if root_changed:
            self.close_details()
            if not self.aggregate_entries and (not self.importer.root or self.importer.root.resolve()!=self.root.resolve()):
                self.importer.reset()
                self.import_panel.pending_zip=None
            if not self.aggregate_entries:self.import_panel.pending_destination=self.root
        elif self.current:
            self.current = next((a for a in self.assets if a.identity == self.current.identity), None)
        if not self.current:
            self.details.hide()
            self.gallery.selection = None
        self.update_backup_status(self.load_job.status)
        self.library_label.setText(tr('すべてのアカウント') if self.account_scope=='all' else self.root.name)
        self.library_label.setToolTip(tr('各アカウントの保存先を読み取り専用で表示') if self.aggregate_entries else str(self.root))
        self.rebuild_account_menu()
        self.apply_filters()
        drawer_open = self.import_panel.isVisible()
        discovery_open = self.discovery_panel.isVisible()
        if not root_changed:
            self.gallery.verticalScrollBar().setValue(self.refresh_scroll)
            if self.current:
                self.select_asset(self.current)
                if drawer_open:
                    self.details.hide()
                    self.import_panel.show()
                elif discovery_open:
                    self.details.hide()
                    self.discovery_panel.show()
        self.thumbs.configure(self.assets, self.root, self.asset_source_path)
        self.gallery.request_visible()
        if self.import_panel.onboarding and self.importer.phase=='idle':self.close_import()
        self.toast(trf('{0:,}件の保存記録を読み込みました', len(self.assets)))
        if self.aggregate_entries and self.load_job.unavailable:
            self.toast(trf('{0}個の保存先を開けません。接続できたアカウントだけを表示しています。', len(self.load_job.unavailable)))
        if self.refresh_pending:
            QTimer.singleShot(0,self.refresh)
        if self.import_panel.awaiting_analytics:
            if self.importer.root and self.root.resolve()==self.importer.root.resolve():
                self.apply_combined_csv()

    def set_favorites_only(self, enabled):
        self.favorites_button.setChecked(enabled)
        self.hidden_only = False
        self.hidden_mode_button.setChecked(False)
        self.all_button.setChecked(not enabled)
        self.apply_filters()

    def update_favorites_count(self):
        if hasattr(self,'favorites_button'):
            self.favorites_button.setText(trf('♡  お気に入り · {0:,}', len(self.favorites)))

    def set_hidden_only(self, enabled):
        self.hidden_only = bool(enabled)
        self.hidden_mode_button.setChecked(self.hidden_only)
        self.favorites_button.setChecked(False)
        self.all_button.setChecked(not self.hidden_only)
        self.apply_filters()

    def year_filter_changed(self,*_):
        unknown=self.year.currentData()==UNKNOWN_YEAR
        if unknown and self.month.currentIndex()!=0:
            self.month.blockSignals(True)
            self.month.setCurrentIndex(0)
            self.month.blockSignals(False)
        self.month.setEnabled(not unknown)
        self.apply_filters()

    def apply_filters(self, *, preserve=False):
        if not hasattr(self,'gallery'):
            return
        self.remember_filter_navigation()
        source_assets = ([a for a in self.assets if a.annotation_key in self.hidden_hashes]
                         if self.hidden_only else
                         [a for a in self.assets if a.annotation_key not in self.hidden_hashes])
        filtered = filter_assets(source_assets, self.year.currentData() or '', self.month.currentData() or '',
                                 '', self.favorites if self.favorites_button.isChecked() and not self.hidden_only else None,
                                 self.media_kind.currentData() or '')
        filtered = filter_manual_tags(filtered,self.search.text(),self.selected_manual_tags,self.manual_definitions,self.manual_mapping)
        def has_performance(a):
            record=self.performance_by_post.get(a.performance_key,{})
            if self.performance_mode=='high' and not record.get('high_count',0):return False
            if self.performance_mode=='no1' and not record.get('top1_count',0):return False
            return self.selected_performance_tags.issubset(record.get('tags',[]))
        filtered=[a for a in filtered if has_performance(a)]
        filtered = self.filter_for_discovery(filtered)
        self.matches = self.order_for_discovery(filtered)
        self.visible = representatives(self.matches) if self.group_duplicates else list(self.matches)
        pool_count=len(self.visible)
        limit=self.discovery_limit.currentData() or 0
        if limit:
            selected_contents={content_key(a) for a in representatives(self.matches)[:limit]}
            self.matches=[a for a in self.matches if content_key(a) in selected_contents]
            self.visible=representatives(self.matches) if self.group_duplicates else list(self.matches)
        self.update_discovery_summary(pool_count)
        self.gallery.grouped = self.group_duplicates
        self.count.setText(f'{len(self.visible):,} / {pool_count:,}' if limit else trf('{0:,}作品', len(self.visible)))
        self.count.setToolTip(trf('表示 {0:,}作品 / 条件に一致する保存ファイル {1:,}件。上部の保存件数は原本全体です。', len(self.visible), len(self.matches)))
        if self.hidden_only:
            self.gallery.empty_text = tr('非表示にした作品はありません。\n作品の詳細または右クリックメニューから追加できます。')
        elif self.favorites_button.isChecked() and not self.favorites:
            self.gallery.empty_text = tr('お気に入りを、少しずつ。\n作品のハートを押すと、ここに並びます。')
        else:
            self.gallery.empty_text = tr('作品が見つかりません。\n年月や検索条件を変更してください。')
        self.gallery.set_assets(self.visible,reset=not preserve)
        self.update_collection_label()
        self.slideshow_start.setEnabled(bool(self.visible))
        if self.current:
            rep = representative_for(self.current,self.visible,self.group_duplicates)
            if rep is None:
                self.close_details()
            elif not any(a.identity==self.current.identity for a in self.matches):
                self.select_asset(rep)
            else:
                self.gallery.selection = rep.identity
                self.gallery.viewport().update()

    def change_sort_order(self,index):
        self.sort_order=self.sort_combo.itemData(index) or 'newest'
        if self.sort_order=='random':
            import secrets
            self.random_seed=secrets.token_hex(24)
        else:
            self.random_seed=''
        self.store.set('sort_order',self.sort_order)
        self.discovery_mode.blockSignals(True)
        self.discovery_mode.setCurrentIndex(0)
        self.discovery_mode.blockSignals(False)
        self.apply_filters()

    def start_slideshow(self):
        if not self.visible:
            return
        asset=self.current if self.current and any(a.identity==self.current.identity for a in self.visible) else self.visible[0]
        self._slideshow_paused=False
        self.open_large(asset)
        self.autoplay.setChecked(True)
        self.toggle_autoplay(True)
        self.large.setFocus()

    def toggle_autoplay(self,enabled):
        if not enabled:
            self._slideshow_paused=False
        if enabled and self.stack.currentIndex()==1 and self.visible:
            if self._slideshow_paused:
                self.slideshow_timer.stop()
                self.media_player.pause()
            else:
                if self.current and self.current.kind=='video':
                    self.resume_video()
                if self.is_video_only():
                    self.slideshow_timer.stop()
                else:
                    self.slideshow_timer.start(self.slideshow_speed.currentData() or 4000)
        else:
            self.slideshow_timer.stop()
        if hasattr(self,'pause_slideshow_button'):
            self.update_slideshow_pause_button()

    def change_slideshow_speed(self,index):
        if self.autoplay.isChecked() and not self._slideshow_paused and self.stack.currentIndex()==1:
            if not (self.is_video_only() and self.current and self.current.kind=='video'):
                self.slideshow_timer.start(self.slideshow_speed.itemData(index) or 4000)

    def update_slideshow_pause_button(self):
        paused=self._slideshow_paused
        self.pause_slideshow_button.setText(tr('▶ 再開') if paused else tr('⏸ 一時停止'))
        self.pause_slideshow_button.setEnabled(self.autoplay.isChecked())
        if self.autoplay.isChecked():
            text=tr('▶ 再開') if paused else tr('⏸ 一時停止')
        elif self.current and self.current.kind=='video':
            playing=self.media_player.playbackState()==QMediaPlayer.PlaybackState.PlayingState
            text=tr('⏸ 一時停止') if playing else tr('▶ 再生')
        else:
            text=tr('▶ 自動送り')
        self.fullscreen_pause.setText(text)

    def toggle_slideshow_pause(self):
        if not self.autoplay.isChecked():
            self.autoplay.setChecked(True)
        if not self._slideshow_paused:
            self._slideshow_paused=True
            self.slideshow_timer.stop()
            if self.current and self.current.kind=='video':
                self.media_player.pause()
        else:
            self._slideshow_paused=False
            self.toggle_autoplay(True)
        self.update_slideshow_pause_button()

    def set_audio_enabled(self,enabled):
        self.audio_output.setMuted(not enabled)
        self.audio_enabled.blockSignals(True)
        self.audio_enabled.setChecked(enabled)
        self.audio_enabled.blockSignals(False)
        self.fullscreen_audio.blockSignals(True)
        self.fullscreen_audio.setChecked(enabled)
        self.fullscreen_audio.blockSignals(False)

    def toggle_fullscreen(self):
        if self._window_immersive:self.set_window_immersive(False)
        if not self.isFullScreen():
            if self.stack.currentIndex()!=1:
                asset=self.current or (self.visible[0] if self.visible else None)
                if not asset:
                    return
                self.open_large(asset)
            self._restore_maximized=self.isMaximized()
            self.showFullScreen()
            for widget in (self.app_header,self.backup_strip,self.gallery_toolbar,self.batch_bar,self.app_footer,
                           self.viewer_top,self.viewer_meta,self.viewer_controls,self.zoom_controls,self.video_controls,
                           self.media_status,self.slideshow_controls,self.viewer_previous,self.viewer_next):
                widget.hide()
            self.viewer_layout.setContentsMargins(0,0,0,0)
            self.viewer_layout.setSpacing(0)
            self._fullscreen_pinned=False
            self.fullscreen_pin.setChecked(False)
            self.update_fullscreen_media_controls()
            self.show_fullscreen_controls()
            self.fullscreen_hide_timer.start()
        else:
            self.fullscreen_hide_timer.stop()
            self.fullscreen_controls.hide()
            self.unsetCursor()
            for widget in (self.app_header,self.backup_strip,self.gallery_toolbar,self.batch_bar,self.app_footer,
                           self.viewer_top,self.viewer_meta,self.viewer_controls,self.slideshow_controls):
                widget.show()
            self.viewer_previous.show()
            self.viewer_next.show()
            self.viewer_layout.setContentsMargins(12,6,12,8)
            self.viewer_layout.setSpacing(4)
            self.viewer_layout.invalidate()
            if self._restore_maximized:
                self.showMaximized()
            else:
                self.showNormal()
            self.video_controls.setVisible(bool(self.current and self.current.kind=='video'))
            self.zoom_controls.setVisible(bool(self.current and self.current.kind!='video'))
            self.media_status.setVisible(bool(self.current and self.current.kind=='video'
                                               and self.media_player.error()!=QMediaPlayer.Error.NoError))
            if self._fullscreen_browse_return is not None:
                saved=self._fullscreen_browse_return
                self._fullscreen_browse_return=None
                self.close_large()
                self.details.setVisible(saved['details'])
                self.gallery.verticalScrollBar().setValue(saved['scroll'])
                QTimer.singleShot(0,lambda:self.gallery.verticalScrollBar().setValue(saved['scroll']) if not self.closing else None)
            self.update_viewer_chrome()

    def immersive_active(self):
        return self.isFullScreen() or self._window_immersive

    def toggle_window_immersive(self):
        if self.isFullScreen():self.toggle_fullscreen()
        if self._window_immersive:
            self.set_window_immersive(False)
            return
        if self.stack.currentIndex()!=1:
            asset=self.current or (self.visible[0] if self.visible else None)
            if not asset:return
            self.open_large(asset)
        self.set_window_immersive(True)

    def set_window_immersive(self,enabled):
        enabled=bool(enabled)
        if enabled==self._window_immersive:return
        self._window_immersive=enabled
        if enabled:
            self._window_viewer_minimum=self.minimumSize()
            self._window_panel_visibility={panel:not panel.isHidden() for panel in
                (self.details,self.import_panel,self.discovery_panel)}
            for panel in self._window_panel_visibility:panel.hide()
            self.setMinimumSize(360,260)
        else:
            self.setMinimumSize(self._window_viewer_minimum)
            for panel,visible in self._window_panel_visibility.items():panel.setVisible(visible)
        for widget in (self.app_header,self.viewer_top,self.viewer_controls,self.viewer_meta,
                       self.zoom_controls,self.video_controls,self.media_status,self.slideshow_controls,
                       self.viewer_previous,self.viewer_next):
            widget.setVisible(not enabled)
        if enabled:self.batch_bar.hide()
        else:self.multi_selection_changed()
        self.viewer_layout.setContentsMargins(0,0,0,0) if enabled else self.viewer_layout.setContentsMargins(12,6,12,8)
        self.viewer_layout.setSpacing(0 if enabled else 4)
        self.viewer_layout.invalidate()
        self._fullscreen_pinned=False
        self.fullscreen_pin.setChecked(False)
        self.fullscreen_exit.setText(tr('表示を戻す') if enabled else tr('全画面を終了'))
        if enabled:
            self.large.set_zoom(1.0)
            self.update_fullscreen_media_controls()
            self.show_fullscreen_controls()
        else:
            self.fullscreen_hide_timer.stop()
            self.fullscreen_controls.hide()
            self.unsetCursor()
            is_video=bool(self.current and self.current.kind=='video')
            self.zoom_controls.setVisible(not is_video)
            self.video_controls.setVisible(is_video)
            self.media_status.setVisible(is_video and self.media_player.error()!=QMediaPlayer.Error.NoError)
        self.update_viewer_chrome()

    def leave_immersive(self):
        if self._window_immersive:self.set_window_immersive(False)
        elif self.isFullScreen():self.toggle_fullscreen()

    def update_fullscreen_media_controls(self):
        is_video=bool(self.current and self.current.kind=='video')
        self.fullscreen_audio.setVisible(is_video)
        self.fullscreen_zoom.setVisible(not is_video)
        self.update_slideshow_pause_button()
        if self.immersive_active():
            self.position_fullscreen_controls()

    def show_fullscreen_controls(self):
        if not self.immersive_active():
            return
        self.fullscreen_controls.adjustSize()
        self.position_fullscreen_controls()
        self.fullscreen_controls.show()
        self.fullscreen_controls.raise_()
        self.setCursor(Qt.CursorShape.ArrowCursor)
        if not self._fullscreen_pinned:
            self.fullscreen_hide_timer.start()

    def hide_fullscreen_controls(self):
        if self.immersive_active() and not self._fullscreen_pinned:
            if self.fullscreen_controls.underMouse() or QApplication.mouseButtons():
                self.fullscreen_hide_timer.start()
                return
            self.fullscreen_controls.hide()
            self.setCursor(Qt.CursorShape.BlankCursor)

    def pin_fullscreen_controls(self,pinned):
        self._fullscreen_pinned=pinned
        if pinned:
            self.fullscreen_hide_timer.stop()
            self.show_fullscreen_controls()
        else:
            self.fullscreen_hide_timer.start()

    def position_fullscreen_controls(self):
        if not hasattr(self,'fullscreen_controls'):
            return
        roomy=self.viewer.width()>=640
        self.fullscreen_controls.setStyleSheet('QPushButton, QToolButton { padding:5px 7px; font-size:12px; } QCheckBox { font-size:12px; spacing:5px; }' if not roomy else '')
        self.fullscreen_pin.setVisible(roomy)
        self.fullscreen_zoom.setVisible(roomy and bool(self.current and self.current.kind!='video'))
        self.fullscreen_controls.adjustSize()
        x=max(8,(self.viewer.width()-self.fullscreen_controls.width())//2)
        y=12
        self.fullscreen_controls.move(x,y)

    def eventFilter(self,watched,event):
        if isinstance(watched,QWidget) and (watched is self or self.isAncestorOf(watched)):
            if self.immersive_active() and event.type() in (QEvent.Type.MouseMove,QEvent.Type.MouseButtonPress,
                                                        QEvent.Type.Wheel,QEvent.Type.KeyPress):
                self.show_fullscreen_controls()
            if watched is getattr(self,'video_widget',None) and event.type()==QEvent.Type.Wheel:
                delta=event.angleDelta().y()
                if delta:
                    self.step(-1 if delta>0 else 1)
                    event.accept()
                    return True
        return super().eventFilter(watched,event)

    def resizeEvent(self,event):
        super().resizeEvent(event)
        if hasattr(self,'toolbar_filters'):
            stacked = self.width() < 1200
            if stacked != self.toolbar_stacked:
                if stacked:
                    self.toolbar_primary.removeWidget(self.toolbar_filters)
                    self.toolbar_layout.addWidget(self.toolbar_filters)
                else:
                    self.toolbar_layout.removeWidget(self.toolbar_filters)
                    self.toolbar_primary.addWidget(self.toolbar_filters)
                self.toolbar_stacked = stacked
        if hasattr(self,'fullscreen_controls') and self.immersive_active():
            self.position_fullscreen_controls()

    def reset_backup(self):
        if not self.require_single_account():return
        if self.importer.active or self.loading or self.import_panel.analytics_busy or self.import_panel.preview_busy:
            QMessageBox.information(self,tr('初期化できません'),tr('取り込みまたはライブラリ更新が終わってから実行してください。'))
            return
        catalog=self.root/'.system'/'catalog.sqlite3'
        if not catalog.is_file():
            QMessageBox.information(self,tr('初期化できません'),tr('管理カタログがないフォルダーは初期化対象にできません。'))
            return
        count=int(self.backup_status.get('count',len(self.assets)))
        prompt=(trf('対象フォルダー:\n{0}\n\n管理カタログ上の保存記録: {1:,}件\nこのフォルダー内の画像・GIF・動画と管理カタログ、取り込み履歴をすべて削除します。\n選択したZIPがこのフォルダー内にある場合、そのZIPも削除されます。\nギャラリーへ個別追加した注意メディアも削除されます。\nこのライブラリのお気に入り・非表示設定・手動タグも削除します。\n削除した作品と設定は元に戻せません。表示順などアプリ全体の設定は保持します。\n\n実際のバックアップアプリで利用中の場合は、先にそちらを閉じてください。', self.root, count))
        answer=QMessageBox.warning(self,tr('バックアップをすべて削除します'),prompt,
            QMessageBox.StandardButton.Yes|QMessageBox.StandardButton.No,QMessageBox.StandardButton.No)
        if answer!=QMessageBox.StandardButton.Yes:
            return
        phrase,ok=QInputDialog.getText(self,tr('削除の最終確認'),
            tr('続行する場合は「バックアップを全て削除」と入力してください。'))
        if not ok or phrase.strip()!=('DELETE ALL BACKUP' if language()=='en' else 'バックアップを全て削除'):
            self.toast(tr('初期化を中止しました'))
            return
        self.thumbs.paused=True
        self.thumbs.pool.waitForDone()
        QApplication.processEvents()
        cache_cleared=False
        try:
            from .library_reset import clear_backup
            clear_backup(self.root)
            self.store.clear_import_state(self.root,self.library_id)
            self.favorites=set()
            self.update_favorites_count()
            self.hidden_hashes=set()
            self.hidden_only=False
            self.favorites_button.setChecked(False)
            self.hidden_mode_button.setChecked(False)
            self.all_button.setChecked(True)
            self.hidden_mode_button.setText(tr('非表示 · 0'))
            self.gallery.favorites=self.favorites
            self.gallery.hidden_hashes=self.hidden_hashes
            # A reset also removes disposable previews and their dimensions.
            self.assets=[]
            self.visible=[]
            self.gallery.set_assets([])
            cache_cleared=self.clear_thumbnail_cache(quiet=True,regenerate=False)
        except Exception as exc:
            self.thumbs.paused=False
            self.refresh()
            QMessageBox.warning(self,tr('初期化できませんでした'),error_text(exc))
            return
        self.thumbs.paused=False
        # Drop the old snapshot before resetting the controller; otherwise its
        # idle update can briefly repopulate warnings from stale history.
        from .backup_status import read_status
        self.update_backup_status(read_status(self.root))
        self.import_panel.history={}
        self.import_panel.pending_zip=None
        self.import_panel.clear_csv()
        self.importer.reset()
        self.current=None
        self.current_image=QImage()
        self.gallery.pixmaps.clear()
        self.gallery.pixmap_bytes=0
        self.close_details()
        self.views={}
        self.view_debounce.clear()
        self.selected_manual_tags.clear()
        self.selected_performance_tags.clear();self.performance_mode=''
        self.navigation_history.clear();self._last_filter_state=None
        self.reload_manual_tags()
        self.reset_discovery()
        self.refresh()
        if cache_cleared:
            self.toast(tr('バックアップとサムネイルキャッシュを初期化しました。新しいアーカイブを取り込めます。'))
        else:
            QMessageBox.warning(self,tr('キャッシュを削除できませんでした'),tr('バックアップは初期化しましたが、一部のサムネイルキャッシュを削除できませんでした。設定からもう一度削除できます。'))

    def clear_thumbnail_cache(self, quiet=False, regenerate=True):
        """Delete only rebuildable previews, never source media or favorites."""
        if self.importer.active or self.loading:
            if not quiet:
                QMessageBox.information(self,tr('キャッシュを削除できません'),tr('取り込みまたはライブラリ更新が終わってから実行してください。'))
            return False
        if not quiet:
            answer=QMessageBox.question(self,tr('サムネイルキャッシュを削除'),
                tr('作成済みのプレビュー画像を削除します。元の画像・動画とお気に入りは残り、必要になった分から自動で作り直します。'),
                QMessageBox.StandardButton.Yes|QMessageBox.StandardButton.No,QMessageBox.StandardButton.No)
            if answer!=QMessageBox.StandardButton.Yes:
                return False
        was_paused=self.thumbs.paused
        self.thumbs.paused=True
        self.thumbs.pool.waitForDone()
        QApplication.processEvents()
        try:
            if self.cache.exists():
                shutil.rmtree(self.cache,ignore_errors=False)
            self.cache.mkdir(parents=True,exist_ok=True)
            self.store.clear_thumbnail_dimensions()
        except OSError as exc:
            self.thumbs.paused=was_paused
            if not quiet:
                QMessageBox.warning(self,tr('キャッシュを削除できませんでした'),error_text(exc))
            return False
        self.gallery.pixmaps.clear()
        self.gallery.pixmap_bytes=0
        self.gallery.dimensions={}
        self.dimensions_pending.clear()
        assets=self.assets if regenerate else []
        self.thumbs.configure(assets,self.root,self.asset_source_path)
        self.thumbs.paused=was_paused
        if regenerate and not was_paused:
            self.gallery.request_visible()
        if not quiet:
            self.toast(tr('サムネイルキャッシュを削除しました。表示時に再生成します。'))
        return True

    def toggle_grouping(self):
        self.group_duplicates = self.group_button.isChecked()
        self.update_group_button_label(self.group_duplicates)
        self.store.set('group_duplicates',self.group_duplicates)
        scroll = self.gallery.verticalScrollBar().value()
        self.apply_filters()
        self.gallery.verticalScrollBar().setValue(scroll)

    def choose_occurrence(self,index):
        asset = self.occurrence_picker.itemData(index)
        if asset:
            self.select_asset(asset)

    def update_occurrences(self):
        members = self.content_groups.get(content_key(self.current),[self.current])
        self.occurrence_label.setVisible(len(members)>1)
        self.occurrence_picker.setVisible(len(members)>1)
        self.occurrence_label.setText(trf('同じ画像の保存記録 · 全{0}件（投稿を切り替え）', len(members)))
        self.occurrence_picker.blockSignals(True)
        self.occurrence_picker.clear()
        current_index = 0
        for i,asset in enumerate(members):
            date = asset.date.strftime('%Y.%m.%d %H:%M:%S') if asset.date else tr('日付不明')
            favorite = '♥ ' if asset.identity in self.favorites else ''
            self.occurrence_picker.addItem(trf('{0}{1} · {2} · 添付{3}', favorite, date, asset.post_id, asset.media_index),asset)
            if asset.identity==self.current.identity:
                current_index=i
        self.occurrence_picker.setCurrentIndex(current_index)
        self.occurrence_picker.blockSignals(False)
        self.occurrence_picker.setToolTip(tr('ライブラリ全体の同一画像です。年月や検索条件の外の投稿も選べます。コピーは選択中の投稿のファイルを使います。'))

    def update_group_button_label(self, checked):
        self.group_button.setText(tr('重複非表示'))

    def change_size_preset(self, _index):
        preset = self.size_combo.currentData()
        if preset not in self.thumbnail_columns:
            return
        miniature = preset == '極小'
        if miniature != self.gallery.miniature:
            self.gallery.pixmaps.clear()
            self.gallery.pixmap_bytes = 0
        self.gallery.miniature = miniature
        self.gallery.width_target = 90 if self.gallery.miniature else 280
        self.gallery.column_adjustment = self.thumbnail_columns[preset]
        self.gallery.tag_hit_rects = []
        self.gallery.performance_hit_rects = []
        self.gallery.layout_timer.start(40)
        self.store.set('thumbnail_size', preset)

    def toggle_favorite(self, asset):
        if not asset or not self.account_library(asset):
            return
        enabled = asset.identity not in self.favorites
        try:
            self.store.set_favorite(self.account_library(asset), asset.source_identity, enabled)
        except Exception as exc:
            QMessageBox.warning(self,tr('お気に入りを保存できません'),error_text(exc))
            return
        if enabled:
            self.favorites.add(asset.identity)
        else:
            self.favorites.discard(asset.identity)
        self.update_favorites_count()
        self.gallery.favorites = self.favorites
        self.gallery.viewport().update()
        if self.current and self.current.identity == asset.identity:
            self.update_favorite_button()
            self.update_occurrences()
        if self.favorites_button.isChecked() or self.discovery_exclude_favorites.isChecked() or self.discovery_no_high_unfav.isChecked():
            self.apply_filters(preserve=True)

    def toggle_hidden_asset(self,asset=None):
        asset=asset or self.current
        if not asset or not self.account_library(asset):
            return
        hide=asset.annotation_key not in self.hidden_hashes
        try:
            self.store.set_hidden(self.account_library(asset),asset.sha256,hide)
        except Exception as exc:
            QMessageBox.warning(self,tr('表示設定を保存できません'),error_text(exc))
            return
        if hide:
            self.hidden_hashes.add(asset.annotation_key)
        else:
            self.hidden_hashes.discard(asset.annotation_key)
        self.gallery.hidden_hashes=self.hidden_hashes
        self.hidden_mode_button.setText(trf('非表示 · {0:,}', len(self.hidden_hashes)))
        self.apply_filters()
        self.toast(tr('この画像を非表示にしました。非表示タブからいつでも戻せます。')
                   if hide else tr('この画像を通常のギャラリーに戻しました。'))

    def update_favorite_button(self):
        enabled = self.current and self.current.identity in self.favorites
        self.favorite_button.setChecked(bool(enabled))
        self.favorite_button.setText(tr('♥ 登録済み') if enabled else tr('♡ お気に入り'))
        self.favorite_button.setToolTip(tr('選択中の投稿のお気に入りです。他の投稿の登録状態は変更しません。'))

    def update_hidden_button(self):
        hidden=bool(self.current and self.current.annotation_key in self.hidden_hashes)
        self.hidden_button.blockSignals(True)
        self.hidden_button.setChecked(hidden)
        self.hidden_button.blockSignals(False)
        self.hidden_button.setText(tr('非表示解除') if hidden else tr('非表示'))
        self.hidden_button.setToolTip(tr('この画像と同じ内容の保存記録を通常表示に戻します。')
                                      if hidden else tr('元ファイルを残したまま、同じ内容の保存記録を通常表示から隠します。'))

    def select_asset(self, asset):
        if not asset:
            return
        self.close_import() if self.import_panel.onboarding else self.import_panel.hide()
        self.discovery_panel.hide()
        unchanged = self.current and self.current.identity == asset.identity
        self.current = asset
        rep = representative_for(asset,self.visible,self.group_duplicates)
        self.gallery.selection = rep.identity if rep else None
        self.details.show()
        self.update_favorite_button()
        self.update_hidden_button()
        self.update_performance_details(asset)
        self.update_manual_details()
        self.update_frequent_tags()
        account=(asset.account_name+' · ') if asset.account_name else ''
        self.kind.setText(account+asset.kind.upper())
        self.post_info_label.setText(tr('X投稿情報あり') if has_x_post_info(asset) else tr('X投稿情報なし／対応不明（未投稿とは断定しません）'))
        self.fields['date'].setText(asset.date.strftime('%Y.%m.%d' if asset.date_precision=='day' else '%Y.%m.%d  %H:%M:%S') if asset.has_known_date else tr('不明'))
        self.fields['post'].setText(asset.post_id or tr('不明'))
        self.fields['filename'].setText(asset.filename)
        self.fields['filename'].setToolTip(asset.filename)
        self.fields['order'].setText((trf('{0} / {1} 点目', asset.media_index, asset.total) + (trf('  ·  バージョン {0}', asset.variant) if asset.variant > 1 else '')) if asset.media_index>0 and asset.total>0 else tr('不明'))
        path = self.asset_source_path(asset)
        # Insert zero-width break opportunities for long Windows paths.
        self.fields['path'].setText(str(path).replace('\\','\\\u200b').replace('_','_\u200b'))
        self.fields['path'].setToolTip(str(path))
        old_menu = self.copy_button.menu()
        self.copy_button.setMenu(self.make_copy_menu(self.copy_button))
        if old_menu:
            old_menu.deleteLater()
        self.viewer_copy.setText(self.copy_image_title(asset))
        order=f'{asset.media_index} / {asset.total}' if asset.media_index>0 and asset.total>0 else tr('添付順不明')
        self.viewer_title.setText(f'{unknown_date(asset.day)}   /   {asset.kind.upper()}   /   {order}')
        self.viewer_meta.setText(trf('投稿 {0}   ·   {1}', asset.post_id or tr('不明'), asset.filename))
        self.viewer_meta.setToolTip(self.viewer_meta.text())
        self.open_media_button.setVisible(asset.kind != 'image')
        self.open_media_button.setText(tr('既定アプリで開く'))
        self.update_occurrences()
        self.update_siblings()
        if not unchanged or self.current_image.isNull():
            self.load_image()
        if self.stack.currentIndex()==1:
            self.show_viewer_asset(asset)
        self.gallery.viewport().update()

    def update_performance_details(self, asset):
        record=self.store.analytics_performance(self.account_library(asset),asset.post_id)
        if not record:
            self.update_manual_details()
            self.performance_summary.setText('')
            self.performance_summary.setToolTip('')
            return
        self.update_manual_details()
        self.performance_summary.setToolTip(
            trf('このライブラリの保存済み {0:,} 投稿で判定。\n同じ投稿は最新の取り込み値を使用します。CSVにない過去投稿も比較対象です。\nこの投稿の取り込み日時: {1}', record['ranking_post_count'], record['imported_at']))
        def count(value):
            return tr('不明') if value is None else f'{value:,}'
        def rate(value):
            return tr('不明') if value is None else f'{value*100:.2f}%'
        def per_thousand(value):
            return tr('不明') if value is None else f'{value:.2f}'
        self.performance_summary.setText(
            trf('IMP {0}  ·  いいね {1} / {2}\nRP {3} / {4}  ·  保存 {5} / {6}\nProfile {7} / {8}\nFollow {9} / 1,000imp {10}\nEngagement {11} / {12}', count(record['impressions']), count(record['likes']), rate(record['like_rate']), count(record['reposts']), rate(record['repost_rate']), count(record['bookmarks']), rate(record['bookmark_rate']), count(record['profile_visits']), rate(record['profile_rate']), count(record['new_follows']), per_thousand(record['follows_per_1000']), count(record['engagements']), rate(record['engagement_rate'])))

    def update_siblings(self):
        while self.series.count():
            item = self.series.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        siblings = sorted((a for a in self.assets if self.current.post_id and a.performance_key == self.current.performance_key), key=lambda a:(a.media_index,a.variant))
        self.series_title.setVisible(len(siblings)>1)
        self.series_widget.setVisible(len(siblings)>1)
        for sibling in siblings[:8]:
            b = QPushButton(str(sibling.media_index))
            b.setFixedSize(58,76)
            b.setCheckable(True)
            b.setChecked(sibling.identity==self.current.identity)
            b.setToolTip(trf('{0}点目 · {1}', sibling.media_index, sibling.filename))
            pix = self.gallery.pixmap(sibling.sha256)
            if pix:
                from PySide6.QtGui import QIcon
                b.setIcon(QIcon(pix))
                b.setIconSize(QSize(42,58))
                b.setText('')
            b.clicked.connect(lambda checked=False,a=sibling:self.select_asset(a))
            self.series.addWidget(b)
        self.series.addStretch()

    def load_image(self):
        if self._minimized_idle:return
        self.image_token += 1
        token = self.image_token
        self.current_image = QImage()
        self.image_error = None
        self.preview.clear()
        self.large.clear()
        self.pending_copy = None
        asset = self.current
        source = self.asset_source_path(asset)
        cached = cache_path(self.cache, asset.sha256)
        if cached.is_file():
            pix = self.gallery.pixmap(asset.sha256)
            if pix:
                self.preview.set_image(pix)
                self.large.set_image(pix)
        if asset.kind in ('video','gif') and source.suffix.lower() not in ('.gif','.png','.webp','.jpg','.jpeg'):
            if not cached.is_file():
                self.thumbs.request([asset.sha256])
                return
            source = cached
        job = ImageJob(token,source)
        self.image_jobs[token] = job
        job.signals.done.connect(self.image_loaded)
        self.jobs.start(job)

    def image_loaded(self, token, image, error):
        self.image_jobs.pop(token,None)
        if self.closing or self._minimized_idle or token != self.image_token or not self.current:
            return
        if error:
            self.image_error = error
            log.warning('Image read failed')
            self.preview.clear(tr('元ファイルを読み込めません'))
            self.large.clear(tr('元ファイルを読み込めません。ドライブの接続を確認してください。'))
            if self.pending_copy:
                self.toast(tr('画像を読み込めません。ファイルコピーをお試しください。'))
            self.pending_copy = None
            return
        self.current_image = image
        self.preview.set_image(image)
        self.large.set_image(image)
        if self.pending_copy == self.current.identity:
            self.pending_copy = None
            self.copy_image()

    def open_large(self, asset):
        if asset:
            self.select_asset(asset)
            self.stack.setCurrentIndex(1)
            self.update_viewer_chrome()
            self.show_viewer_asset(asset)
            self.previous_action.setEnabled(True)
            self.next_action.setEnabled(True)
            self.pause_action.setEnabled(True)

    def open_fullscreen(self,asset):
        if not asset:return
        if not self.isFullScreen() and self.stack.currentIndex()==0:
            self._fullscreen_browse_return={'scroll':self.gallery.verticalScrollBar().value(),'details':self.details.isVisible()}
        self.open_large(asset)
        if not self.isFullScreen():self.toggle_fullscreen()

    def is_video_only(self):
        return bool(self.visible) and all(asset.kind=='video' for asset in self.visible)

    def show_viewer_asset(self,asset):
        self.record_view(asset)
        is_video=asset.kind=='video'
        self.slideshow_timer.stop()
        self.video_controls.setVisible(is_video and not self.immersive_active())
        self.zoom_controls.setVisible(not is_video and not self.immersive_active())
        self.media_status.hide()
        self.fullscreen_status.hide()
        self.update_fullscreen_media_controls()
        if not is_video:
            self.media_player.stop()
            self.media_player.setSource(QUrl())
            self._video_source_identity=None
            self.viewer_media.setCurrentWidget(self.large)
            if self.autoplay.isChecked() and not self._slideshow_paused:
                self.slideshow_timer.start(self.slideshow_speed.currentData() or 4000)
            return
        self.viewer_media.setCurrentWidget(self.video_widget)
        if self._video_source_identity!=asset.identity:
            self.media_player.stop()
            source=self.asset_source_path(asset)
            if not source.is_file():
                self.media_status.setText(tr('元動画が見つかりません。ドライブを確認してください。'))
                self.show_video_error()
                self._video_source_identity=None
                return
            self._video_source_identity=asset.identity
            self.video_position.setRange(0,0)
            self.video_clock.setText('0:00 / 0:00')
            self.media_player.setSource(QUrl.fromLocalFile(str(source)))
            self.media_player.setPlaybackRate(self.video_rate.currentData() or 1.0)
        if self.autoplay.isChecked() and not self._slideshow_paused:
            self.toggle_autoplay(True)
        elif self.autoplay.isChecked() and self._slideshow_paused:
            self.slideshow_timer.stop()
            self.media_player.pause()
        elif self.media_player.mediaStatus()==QMediaPlayer.MediaStatus.EndOfMedia:
            self.media_player.setPosition(0)

    def toggle_video_playback(self):
        if self.autoplay.isChecked():
            self.toggle_slideshow_pause()
            return
        if self.media_player.playbackState()==QMediaPlayer.PlaybackState.PlayingState:
            self.media_player.pause()
        else:
            self.resume_video()

    def resume_video(self):
        if self.media_player.mediaStatus()==QMediaPlayer.MediaStatus.EndOfMedia:
            self.media_player.setPosition(0)
        self.media_player.play()

    def toggle_fullscreen_pause(self):
        if self.autoplay.isChecked():
            self.toggle_slideshow_pause()
        elif self.current and self.current.kind=='video':
            self.toggle_video_playback()
        elif self.stack.currentIndex()==1 and self.visible:
            self.autoplay.setChecked(True)

    def update_video_play_button(self,state):
        self.video_play.setText(tr('⏸ 一時停止') if state==QMediaPlayer.PlaybackState.PlayingState else tr('▶ 再生'))
        if hasattr(self,'fullscreen_pause'):
            self.update_slideshow_pause_button()

    def update_video_duration(self,duration):
        self._video_duration=duration
        self.video_position.setRange(0,duration)
        self.update_video_position(self.media_player.position())

    @staticmethod
    def format_media_time(milliseconds):
        seconds=max(0,int(milliseconds//1000))
        minutes,seconds=divmod(seconds,60)
        hours,minutes=divmod(minutes,60)
        return f'{hours}:{minutes:02d}:{seconds:02d}' if hours else f'{minutes}:{seconds:02d}'

    def update_video_position(self,position):
        if not self.video_position.isSliderDown():
            self.video_position.setValue(position)
        self.video_clock.setText(f'{self.format_media_time(position)} / {self.format_media_time(self._video_duration)}')

    def change_video_rate(self,index):
        rate=self.video_rate.itemData(index)
        if rate:
            self.media_player.setPlaybackRate(rate)

    def video_media_status_changed(self,status):
        if status==QMediaPlayer.MediaStatus.EndOfMedia:
            if self.autoplay.isChecked() and not self._slideshow_paused and self.is_video_only() and self.stack.currentIndex()==1:
                self.step(1)
            elif self.current and self.current.kind=='video':
                self.media_status.setText(tr('再生が終わりました。もう一度再生できます。'))
                self.media_status.setVisible(not self.immersive_active())
        elif status==QMediaPlayer.MediaStatus.LoadedMedia:
            seek=self._power_video_seek
            if seek:
                self._power_video_seek=None
                if self.current and self.current.identity==seek[0]:self.media_player.setPosition(seek[1])
            self.media_status.hide()

    def video_playback_error(self,error,message):
        if error==QMediaPlayer.Error.NoError:
            return
        self.media_status.setText(tr('この形式をアプリ内で再生できません。上の「既定アプリで開く」をお試しください。\n')+message)
        self.show_video_error()

    def show_video_error(self):
        self.media_status.setVisible(not self.immersive_active())
        self.fullscreen_status.setText(tr('動画を再生できません。全画面を終了して詳細を確認してください。'))
        self.fullscreen_status.setToolTip(self.media_status.text())
        self.fullscreen_status.show()
        if self.immersive_active():
            self.show_fullscreen_controls()

    def close_large(self):
        if self._window_immersive:self.set_window_immersive(False)
        if self.isFullScreen():
            self.toggle_fullscreen()
        if hasattr(self,'slideshow_timer'):
            self.slideshow_timer.stop()
            self.autoplay.setChecked(False)
        if hasattr(self,'media_player'):
            self.media_player.stop()
            self.media_player.setSource(QUrl())
            self._video_source_identity=None
        self.stack.setCurrentIndex(0)
        self.update_viewer_chrome()
        self.previous_action.setEnabled(False)
        self.next_action.setEnabled(False)
        self.pause_action.setEnabled(False)
        self.gallery.setFocus()

    def update_viewer_chrome(self):
        """Give the viewer room; restore gallery-only controls on returning."""
        visible=self.stack.currentIndex()==0 and not self.immersive_active() and not self.import_panel.onboarding
        for widget in (self.backup_strip,self.gallery_toolbar,self.app_footer):
            widget.setVisible(visible)

    def close_details(self):
        self.close_large()
        self.current = None
        self.current_image = QImage()
        self.image_token += 1
        self.preview.clear();self.large.clear()
        self.pending_copy = None
        self.gallery.selection = None
        self.details.hide()
        self.gallery.viewport().update()

    def escape(self):
        if self._window_immersive:
            self.set_window_immersive(False)
        elif self.isFullScreen():
            self.toggle_fullscreen()
        elif self.stack.currentIndex()==1:
            self.close_large()
        elif self.discovery_panel.isVisible():
            self.discovery_panel.hide()
        elif self.gallery.multi_selection:
            self.clear_multi_selection()
        elif self.current:
            self.close_details()
        elif self.search.text():
            self.search.clear()

    def step(self, direction):
        if not self.visible:
            return
        rep = representative_for(self.current,self.visible,self.group_duplicates)
        index = next((i for i,a in enumerate(self.visible) if rep and a.identity == rep.identity),0)
        self.select_asset(self.visible[(index+direction)%len(self.visible)])

    def build_context_menu(self, asset):
        menu = self.make_copy_menu(self,asset)
        menu.addSeparator()
        targets=self.selected_tag_assets() or [asset]
        counts=self.tag_usage_counts()
        names=self.frequent_tag_ids()
        frequent=menu.addMenu(tr('よく使うタグを付ける'))
        for ident in names:
            common=all(ident in self.manual_mapping.get(a.annotation_key,set()) for a in targets)
            action=frequent.addAction(self.manual_definitions[ident])
            action.setIcon(self.manual_tag_icon(ident))
            action.setToolTip(trf('{0:,}作品に使用 · 付与済みならクリックで解除', counts[ident]))
            action.setCheckable(True);action.setChecked(common)
            action.triggered.connect(lambda _checked=False,i=ident:self.toggle_tag_batch(i))
        if not names:
            frequent.addAction(tr('タグを登録してください')).setEnabled(False)
        menu.addAction(tr('登録済みタグを付ける / 外す…'),self.batch_tag_dialog)
        menu.addAction(tr('タグを登録・管理…'),self.manage_manual_tags)
        menu.addSeparator()
        for title,mode,enabled in [(tr('お気に入りに登録'),'favorite',True),(tr('お気に入りを解除'),'favorite',False),
                                   (tr('非表示にする'),'hidden',True),(tr('非表示を解除'),'hidden',False)]:
            menu.addAction(title,lambda _checked=False,m=mode,e=enabled,t=list(targets):self.apply_selection_state(t,m,e))
        menu.addAction(tr('大きく表示 · 全画面'), lambda:self.open_fullscreen(asset))
        menu.addAction(tr('保存先を開く'), lambda:self.reveal_file(asset))
        return menu

    def apply_selection_state(self,targets,mode,enabled):
        if not targets:return
        if mode=='favorite':
            self.route_selection_state(targets,mode,enabled)
            self.gallery.favorites=self.favorites
            self.update_favorites_count()
            self.update_favorite_button()
        else:
            self.route_selection_state(targets,mode,enabled)
            self.gallery.hidden_hashes=self.hidden_hashes
            self.hidden_mode_button.setText(trf('非表示 · {0:,}', len(self.hidden_hashes)))
        self.apply_filters(preserve=True)
        self.toast(trf('{0:,}件の', len(targets))+(tr('お気に入り') if mode=='favorite' else tr('非表示'))+(tr('を設定しました') if enabled else tr('を解除しました')))

    def context_menu(self, asset, point):
        menu=self.build_context_menu(asset)
        menu.exec(point)
        menu.deleteLater()

    def copy_image(self, asset=None):
        if isinstance(QApplication.focusWidget(),QLineEdit) and asset is None:
            QApplication.focusWidget().copy()
            return
        if not isinstance(asset,Asset):
            asset = self.current
        if not asset:
            self.toast(tr('コピーする作品を選択してください'))
            return
        if not self.current or self.current.identity != asset.identity:
            self.select_asset(asset)
        if self.image_error:
            self.toast(tr('元画像を読み込めません。ドライブの接続を確認して、作品を選び直してください。'))
            return
        if self.current_image.isNull():
            self.pending_copy = asset.identity
            self.toast(tr('画像を読み込んでからコピーします…'))
            return
        try:
            QApplication.clipboard().setMimeData(image_payload(self.current_image))
            if asset.kind == 'image':
                self.toast(trf('画像をコピーしました · {0} × {1} px', self.current_image.width(), self.current_image.height()))
            else:
                self.toast(tr('プレビューの静止画像をコピーしました。動画は「ファイルをコピー」を使えます。'))
        except Exception as exc:
            self.toast(error_text(exc))

    def copy_file(self, asset=None):
        if not isinstance(asset,Asset):
            asset = self.current
        if not asset:
            self.toast(tr('コピーする作品を選択してください'))
            return
        try:
            QApplication.clipboard().setMimeData(file_payload(self.asset_source_path(asset)))
            self.toast(tr('ファイルをコピーしました。貼り付け先で Ctrl+V を押してください。'))
        except Exception as exc:
            self.toast(error_text(exc))

    def copy_text(self, text):
        if text:
            QApplication.clipboard().setText(text)
            self.toast(tr('コピーしました'))

    def reveal_file(self,asset=None):
        if not isinstance(asset,Asset):asset=self.current
        if not asset:
            return
        path = self.asset_source_path(asset)
        if not path.is_file():
            self.toast(tr('元ファイルが見つかりません'))
            return
        subprocess.Popen(['explorer.exe','/select,',str(path)], creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)

    def open_media(self):
        if self.current:
            path = self.asset_source_path(self.current)
            if path.is_file():
                QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))
            else:
                self.toast(tr('元ファイルが見つかりません'))

    def need_thumbnails(self, hashes):
        for sha in hashes:
            if sha in self.thumbs.finished and not cache_path(self.cache,sha).is_file():
                self.thumbs.invalidate(sha)
        self.thumbs.request(hashes)

    def thumbnail_ready(self, sha, w, h):
        self.gallery.thumbnail_ready(sha,w,h)
        self.dimensions_pending[sha] = (w,h)
        if not self.flush_timer.isActive() and not self.closing:
            self.flush_timer.start(800)
        if self.current and self.current.sha256 == sha and self.current_image.isNull():
            pending_copy = self.pending_copy
            self.load_image()
            self.pending_copy = pending_copy

    def thumbnail_failed(self, sha, error):
        log.warning('Thumbnail failed')
        self.gallery.failed.add(sha)
        self.gallery.viewport().update()
        if self.current and self.current.sha256==sha and self.current_image.isNull():
            self.image_error = error
            self.preview.clear(tr('プレビューを生成できません'))
            self.large.clear(tr('プレビューを生成できません。「ファイルをコピー」または保存先から開けます。'))
            self.pending_copy = None

    def thumbnail_progress(self, done, total, failed):
        if self.importer.active:
            return
        if done+failed < total:
            text = tr('サムネイル準備中…')
        else:
            text = tr('プレビュー準備完了')
        if failed and done+failed >= total:
            text += trf(' · プレビューなし {0}', failed)
        self.progress.setText(text)

    def flush_dimensions(self):
        if not self.dimensions_pending:
            return
        try:
            self.store.save_dimensions([(sha,*size) for sha,size in self.dimensions_pending.items()])
            self.dimensions_pending.clear()
        except Exception:
            log.exception('Could not save disposable thumbnail metadata')

    def recheck_cache(self):
        if not self.assets:
            return
        self.gallery.pixmaps.clear()
        self.gallery.pixmap_bytes = 0
        self.thumbs.configure(self.assets,self.root,self.asset_source_path)
        self.gallery.request_visible()
        self.toast(tr('不足したサムネイルを再生成します'))

    def open_distribution_materials(self):
        if getattr(sys, 'frozen', False):
            folder = Path(sys.executable).resolve().parent / 'licenses'
        else:
            folder = Path(__file__).resolve().parents[1]
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(folder)))

    def export_diagnostics(self):
        from .diagnostics import export_report
        path,_=QFileDialog.getSaveFileName(self,tr('不具合報告用ログを保存'),tr('XArchiveGallery-診断ログ.zip'),tr('ZIPファイル (*.zip)'))
        if not path:return
        try:
            from .accounts import libraries
            if any(Path(path).resolve().is_relative_to(e['root'].resolve()) for e in libraries(self.store)):
                raise ValueError(tr('ログは作品ライブラリの外へ保存してください。'))
            export_report(self.store.directory,path)
            self.toast(tr('診断ログを保存しました。画像・DB・CSV・ライブラリ履歴は含まれません。'))
        except (OSError,ValueError):
            log.exception('Could not export diagnostics')
            QMessageBox.warning(self,tr('ログを保存できません'),tr('作品ライブラリとアプリデータの外にある、書き込み可能な場所へZIP形式で保存してください。'))

    def show_help(self):
        from .help_ui import HelpDialog
        HelpDialog(self).exec()

    def closeEvent(self,event):
        if self.closing:
            event.accept()
            return
        if self.importer.active:
            event.ignore()
            if self.exit_after_import:
                return
            choice=QMessageBox.question(self,tr('取り込み中です'),tr('安全に中止してからアプリを終了しますか？ 保存済みの作品は残ります。'),QMessageBox.StandardButton.Yes|QMessageBox.StandardButton.No,QMessageBox.StandardButton.No)
            if choice==QMessageBox.StandardButton.Yes:
                self.exit_after_import=True
                self.importer.cancel()
                def finish_close():
                    if not self.importer.active:
                        self.close()
                self.importer.changed.connect(finish_close)
            return
        self.closing = True
        QApplication.instance().removeEventFilter(self)
        if self.isFullScreen():
            self.toggle_fullscreen()
        self.media_player.stop()
        self.slideshow_timer.stop()
        self.fullscreen_hide_timer.stop()
        self.flush_timer.stop()
        self.hide()
        # Jobs never outlive the Python/Qt runtime. ffmpeg has a bounded timeout.
        self.thumbs.shutdown()
        self.jobs.waitForDone()
        self.flush_dimensions()
        self.store.close()
        event.accept()
