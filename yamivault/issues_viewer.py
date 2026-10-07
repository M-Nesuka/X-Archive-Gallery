"""Review archive import issues and preview matching media directly from its ZIP."""
from .i18n import tr,trf,error_text
from .i18n import warning_reason,unknown_date
from .appearance import theme_css
from pathlib import Path, PurePosixPath
from io import BytesIO
import zipfile

from PIL import Image,ImageOps

from PySide6.QtCore import Qt,QThread,Signal
from PySide6.QtGui import QImage, QPixmap
from PySide6.QtWidgets import (QDialog,QHBoxLayout,QLabel,QListWidget,QListWidgetItem,
                               QSplitter,QVBoxLayout,QPushButton,QMessageBox,QSizePolicy)


IMAGE_EXTENSIONS={'.jpg','.jpeg','.png','.webp','.gif','.bmp','.tif','.tiff','.avif','.heic','.heif','.jfif'}
MAX_PREVIEW_BYTES=64*1024*1024
VIDEO_EXTENSIONS={'.mp4','.mov','.webm','.m4v','.mkv','.avi','.mpeg','.mpg','.3gp','.ts'}


class WarningMediaJob(QThread):
    completed=Signal(int,str)
    def __init__(self,data_dir,library_root,issues,parent=None):
        super().__init__(parent)
        self.data_dir=Path(data_dir)
        self.library_root=Path(library_root)
        self.issues=list(issues)
    def run(self):
        store=None
        try:
            from .store import VaultStore
            store=VaultStore(self.data_dir)
            library_id=store.library(self.library_root)
            count=store.add_warning_assets(library_id,self.issues)
            self.completed.emit(count,'')
        except Exception as exc:
            self.completed.emit(0,error_text(exc))
        finally:
            if store:
                store.close()


class IssueGallery(QDialog):
    def __init__(self, issues, data_dir, parent=None, library_root=None, on_added=None):
        super().__init__(parent)
        self.issues=list(issues)
        self.data_dir=Path(data_dir)
        self.library_root=Path(library_root) if library_root else None
        self.on_added=on_added
        self.addition=None
        self.current_image=None
        self.current_source=None
        self._updating_checks=False
        self.setWindowTitle(tr('バックアップの確認事項'))
        self.resize(1000,720)
        outer=QVBoxLayout(self)
        batch=QHBoxLayout()
        batch.addStretch()
        self.select_all=QPushButton(tr('すべて選択'))
        self.select_all.clicked.connect(self.toggle_select_all)
        batch.addWidget(self.select_all)
        outer.addLayout(batch)
        self.grok_notice=QLabel(
            tr('Grokチャットのメディア（data/grok_chat_media）には、会話に添付した画像とGrokが生成した画像の両方が含まれます。会話情報は data/grok-chat-item.js に記録され、ファイル名の数字IDが対応を調べる手がかりになります。X投稿との紐付けが確認できないものは自動保存されませんが、必要なものは選択してギャラリーに追加できます。')
        )
        self.grok_notice.setWordWrap(True)
        self.grok_notice.setTextFormat(Qt.TextFormat.PlainText)
        self.grok_notice.setStyleSheet(theme_css('background:#17141c; color:#c5bdce; padding:10px 12px; border-radius:8px;'))
        self.grok_notice.setSizePolicy(QSizePolicy.Policy.Ignored,QSizePolicy.Policy.Preferred)
        has_grok_media=any('grok_chat_media' in str(issue.get('source') or '').casefold()
                           for issue in self.issues)
        self.grok_notice.setVisible(has_grok_media)
        outer.addWidget(self.grok_notice)
        split=QSplitter(Qt.Orientation.Horizontal)
        self.list=QListWidget()
        self.preview=QLabel(tr('左側の確認事項を選んでください'))
        self.preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview.setMinimumSize(300,250)
        self.preview.setWordWrap(True)
        self.preview.setStyleSheet(theme_css('background:#0b0b0e; color:#c5bdce; padding:18px;'))
        split.addWidget(self.list)
        split.addWidget(self.preview)
        split.setSizes([400,580])
        outer.addWidget(split,1)
        footer=QHBoxLayout()
        self.info=QLabel('')
        self.info.setWordWrap(True)
        footer.addWidget(self.info,1)
        close=QPushButton(tr('閉じる'))
        close.clicked.connect(self.accept)
        self.add_button=QPushButton(tr('選択したメディアをギャラリーに追加'))
        self.add_button.setObjectName('primary')
        self.add_button.setEnabled(False)
        self.add_button.clicked.connect(self.add_selected)
        footer.addWidget(self.add_button)
        footer.addWidget(close)
        outer.addLayout(footer)
        for issue in self.issues:
            day=unknown_date(issue.get('date') or tr('不明'))
            post=issue.get('post_id') or tr('不明')
            text=f"{tr(issue.get('level','確認'))} · {day} · {post}\n{issue.get('source') or ''}\n{warning_reason(issue.get('reason') or '')}"
            item=QListWidgetItem(text)
            item.setData(Qt.ItemDataRole.UserRole,issue)
            ext=PurePosixPath(str(issue.get('source') or '').replace('\\','/')).suffix.lower()
            archive=Path(issue.get('zip_path') or '')
            selectable=(issue.get('level')=='注意' and ext in IMAGE_EXTENSIONS|VIDEO_EXTENSIONS and archive.is_file())
            item.setFlags(item.flags()|Qt.ItemFlag.ItemIsEnabled|Qt.ItemFlag.ItemIsSelectable)
            if selectable:
                item.setFlags(item.flags()|Qt.ItemFlag.ItemIsUserCheckable)
                item.setCheckState(Qt.CheckState.Unchecked)
            self.list.addItem(item)
        self.list.currentItemChanged.connect(self.show_issue)
        self.list.itemChanged.connect(self.update_add_button)
        self.update_add_button()
        if self.list.count():
            self.list.setCurrentRow(0)

    def update_add_button(self,*args):
        eligible=[self.list.item(i) for i in range(self.list.count())
                  if self.list.item(i).flags() & Qt.ItemFlag.ItemIsUserCheckable]
        selected=sum(1 for item in eligible if item.checkState()==Qt.CheckState.Checked)
        complete=bool(eligible) and selected==len(eligible)
        self.select_all.setVisible(bool(eligible))
        self.select_all.setText(tr('すべて解除') if complete else tr('すべて選択'))
        self.select_all.setToolTip(trf('ギャラリーへ追加できる注意メディア {0:,}件を一括選択', len(eligible)))
        self.add_button.setEnabled(bool(selected) and self.on_added is not None and not (self.addition and self.addition.isRunning()))
        self.add_button.setText(trf('選択したメディアをギャラリーに追加（{0}件）', selected))

    def toggle_select_all(self):
        eligible=[self.list.item(i) for i in range(self.list.count())
                  if self.list.item(i).flags() & Qt.ItemFlag.ItemIsUserCheckable]
        complete=bool(eligible) and all(item.checkState()==Qt.CheckState.Checked for item in eligible)
        target=Qt.CheckState.Unchecked if complete else Qt.CheckState.Checked
        self.list.blockSignals(True)
        for item in eligible:
            item.setCheckState(target)
        self.list.blockSignals(False)
        self.update_add_button()

    def add_selected(self):
        selected=[self.list.item(i).data(Qt.ItemDataRole.UserRole) for i in range(self.list.count())
                  if self.list.item(i).checkState()==Qt.CheckState.Checked]
        if not selected or self.on_added is None or self.library_root is None:
            return
        self.add_button.setEnabled(False)
        self.select_all.setEnabled(False)
        self.add_button.setText(trf('{0:,}件を追加中…', len(selected)))
        self.addition=WarningMediaJob(self.data_dir,self.library_root,selected,self)
        self.addition.completed.connect(self.addition_finished)
        self.addition.start()

    def addition_finished(self,count,error):
        self.select_all.setEnabled(True)
        if error:
            self.addition=None
            QMessageBox.warning(self,tr('ギャラリーに追加できません'),error)
            self.update_add_button()
            return
        if self.on_added:
            self.on_added()
        QMessageBox.information(self,tr('ギャラリーに追加しました'),
            trf('{0:,}件をX Archive Galleryの保存領域へ追加しました。投稿日・投稿IDなど不明な情報は「不明」と表示します。', count))
        self.accept()

    def closeEvent(self,event):
        if self.addition and self.addition.isRunning():
            event.ignore()
            return
        super().closeEvent(event)

    def show_issue(self,item,previous=None):
        self.preview.setPixmap(QPixmap())
        if item is None:
            return
        issue=item.data(Qt.ItemDataRole.UserRole)
        source=str(issue.get('source') or '')
        self.info.setText(trf('{0}  ·  投稿日 {1}  ·  投稿ID {2}\n{3}', tr(issue.get('level', '確認')), unknown_date(issue.get('date') or '不明'), issue.get('post_id') or tr('不明'), warning_reason(issue.get('reason') or '')))
        if PurePosixPath(source.replace('\\','/')).suffix.lower() not in IMAGE_EXTENSIONS:
            self.current_image=None
            self.current_source=None
            self.preview.setText(tr('この確認事項は画像形式ではないため、プレビュー対象外です。\n対応する動画は選択して追加するとギャラリーで確認できます。'))
            return
        archive=Path(issue.get('zip_path') or '')
        if not archive.is_file():
            self.current_image=None
            self.current_source=None
            self.preview.setText(trf('元のZIPが見つからないため画像を表示できません。\n{0}\n\n元のZIPを取り込み画面で再選択すると確認できます。', source))
            return
        try:
            if self.current_source!=(str(archive),source):
                with zipfile.ZipFile(archive) as zf:
                    matches=[info for info in zf.infolist() if info.filename==source and not info.is_dir()]
                    if len(matches)!=1:
                        raise ValueError(tr('ZIP内に同名のファイルが1つだけ見つかりません。'))
                    info=matches[0]
                    if info.file_size>MAX_PREVIEW_BYTES:
                        raise ValueError(tr('画像が大きいため、プレビューを省略しました。'))
                    raw=zf.read(info)
                with Image.open(BytesIO(raw)) as original:
                    width,height=original.size
                    if width*height>40_000_000:
                        raise ValueError(tr('画像の画素数が大きいため、プレビューを省略しました。'))
                    original.seek(0)
                    image=ImageOps.exif_transpose(original)
                    image.thumbnail((1800,1800),Image.Resampling.LANCZOS)
                    image=image.convert('RGBA' if 'A' in image.getbands() else 'RGB')
                    if image.mode=='RGBA':
                        self.current_image=QImage(image.tobytes(),image.width,image.height,image.width*4,QImage.Format.Format_RGBA8888).copy()
                    else:
                        self.current_image=QImage(image.tobytes(),image.width,image.height,image.width*3,QImage.Format.Format_RGB888).copy()
                self.current_source=(str(archive),source)
            pix=QPixmap.fromImage(self.current_image).scaled(self.preview.size(),Qt.AspectRatioMode.KeepAspectRatio,Qt.TransformationMode.SmoothTransformation)
            self.preview.setText('')
            self.preview.setPixmap(pix)
        except Exception as exc:
            self.current_image=None
            self.current_source=None
            self.preview.setText(trf('画像を表示できませんでした。\n{0}\n\n{1}', source, exc))

    def resizeEvent(self,event):
        super().resizeEvent(event)
        item=self.list.currentItem()
        if item:
            self.show_issue(item)
