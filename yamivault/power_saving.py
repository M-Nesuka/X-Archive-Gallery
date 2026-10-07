"""Suspend gallery work while minimized without interrupting explicit imports."""
from PySide6.QtCore import QEvent,QTimer,QUrl
from PySide6.QtGui import QImage,QPixmapCache
from PySide6.QtMultimedia import QMediaPlayer


class PowerSavingMixin:
    def changeEvent(self,event):
        super().changeEvent(event)
        if event.type()!=QEvent.Type.WindowStateChange or not hasattr(self,'thumbs') or self.closing:return
        minimized=self.isMinimized()
        if minimized==getattr(self,'_minimized_idle',False):return
        self._minimized_idle=minimized
        if minimized:
            self.thumbs.paused=True
            self.slideshow_timer.stop()
            if self.autoplay.isChecked():
                self._slideshow_paused=True
                self.update_slideshow_pause_button()
            self._power_video_seek=None
            if self.current and self.current.kind=='video' and not self.media_player.source().isEmpty():
                self._power_video_seek=(self.current.identity,self.media_player.position())
            self.media_player.stop()
            self.media_player.setSource(QUrl())
            self._video_source_identity=None
            self.fullscreen_hide_timer.stop()
            for timer in (self.gallery.request_timer,self.gallery.layout_timer,self.gallery.drag_scroll_timer):timer.stop()
            for job in self.image_jobs.values():job.cancelled=True
            self.image_token+=1;self.pending_copy=None
            self.current_image=QImage();self.preview.clear();self.large.clear()
            self.gallery.pixmaps.clear();self.gallery.pixmap_bytes=0
            QPixmapCache.clear()
        else:
            self.thumbs.paused=self.importer.active
            QTimer.singleShot(0,self.restore_gallery_after_minimize)

    def restore_gallery_after_minimize(self):
        if self.closing or self._minimized_idle:return
        self.gallery.relayout();self.gallery.request_visible();self.gallery.viewport().update()
        if self.current and (self.details.isVisible() or self.stack.currentIndex()==1):
            self.load_image()
            if self.stack.currentIndex()==1:self.show_viewer_asset(self.current)
