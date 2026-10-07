"""Virtual masonry gallery: only visible tiles are painted or decoded."""
from __future__ import annotations
from .i18n import tr,trf
from .i18n import unknown_date

import bisect
import math
from collections import OrderedDict

from PySide6.QtCore import Qt, QRectF, QSize, Signal, QTimer, QPointF
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen, QFont, QPixmap,QLinearGradient,QImageReader
from PySide6.QtWidgets import QAbstractScrollArea, QApplication

from .thumbnails import cache_path
from .grouping import content_key
from .tag_colors import tag_colors
from .appearance import theme_color


class Gallery(QAbstractScrollArea):
    selected = Signal(object)
    activated = Signal(object)
    favorite = Signal(object)
    context = Signal(object, object)
    needed = Signal(object)
    corrupt = Signal(str)
    tag_clicked = Signal(str)
    performance_tag_clicked = Signal(str)
    multi_changed = Signal()

    def __init__(self, cache, parent=None):
        super().__init__(parent)
        self.cache = cache
        self.assets = []
        self.grouped = True
        self.group_counts = {}
        self.dimensions = {}
        self.favorites = set()
        self.performance_tags = {}
        self.manual_tags = {}
        self.manual_colors = {}
        self.tag_hit_rects = []
        self.performance_hit_rects=[]
        self.selection = None
        self.multi_selection = set()
        self.range_anchor = None
        self.hovered = None
        self.columns = []
        self.rects = []
        self.column_ys = []
        self.pixmaps = OrderedDict()
        self.pixmap_bytes = 0
        self.width_target = 280
        self.miniature = False
        # Presets adjust the baseline column count directly so that two
        # nearby target widths cannot collapse to the same masonry layout.
        self.column_adjustment = 0
        self.empty_text = tr('ライブラリを読み込んでいます…')
        self.failed = set()
        self.drag_origin = None
        self.drag_point = None
        self.drag_rect = None
        self.drag_base = set()
        self.pending_click = None
        self.drag_scroll_timer = QTimer(self)
        self.drag_scroll_timer.setInterval(30)
        self.drag_scroll_timer.timeout.connect(self.drag_scroll)
        self.setFrameShape(self.Shape.NoFrame)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        # A stable viewport width prevents masonry column oscillation when
        # short filtered results straddle the scrollbar threshold.
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOn)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.viewport().setMouseTracking(True)
        self.viewport().setAutoFillBackground(False)
        self.verticalScrollBar().valueChanged.connect(self.on_scroll)
        self.request_timer = QTimer(self)
        self.request_timer.setSingleShot(True)
        self.request_timer.timeout.connect(self.request_visible)
        self.layout_timer = QTimer(self)
        self.layout_timer.setSingleShot(True)
        self.layout_timer.timeout.connect(self.relayout)
        self.setAccessibleName(tr('作品ギャラリー。矢印キーで選択、Enterで拡大、Ctrl+Cで画像コピー'))

    def set_assets(self, assets, reset=True):
        self.tag_hit_rects=[]
        self.performance_hit_rects=[]
        anchor, offset = None, 0
        if not reset and self.rects:
            visible=self.visible_indices()
            if visible:
                i=visible[0]
                anchor=self.assets[i].identity
                offset=self.verticalScrollBar().value()-self.rects[i].top()
        self.assets = list(assets)
        previous = set(self.multi_selection)
        self.multi_selection.intersection_update(a.identity for a in self.assets)
        if previous != self.multi_selection:
            self.multi_changed.emit()
        if reset:
            self.verticalScrollBar().setValue(0)
        self.relayout(preserve=False)
        if anchor is not None:
            for i,asset in enumerate(self.assets):
                if asset.identity==anchor:
                    self.verticalScrollBar().setValue(int(self.rects[i].top()+offset))
                    break

    def set_performance_tags(self, tags_by_post):
        updated={str(post_id):list(tags) for post_id,tags in tags_by_post.items() if tags}
        if updated==self.performance_tags:
            return
        self.performance_tags=updated
        self.relayout(preserve=True)

    def footer_height(self, asset):
        return 18 if self.miniature else 26

    def invalidate(self, sha):
        old = self.pixmaps.pop(sha, None)
        if old:
            self.pixmap_bytes -= old.width() * old.height() * 4
        self.viewport().update()

    def thumbnail_ready(self, sha, w, h):
        old = self.dimensions.get(sha)
        self.dimensions[sha] = (w, h)
        self.failed.discard(sha)
        self.invalidate(sha)
        if old != (w, h) and not self.layout_timer.isActive():
            self.layout_timer.start(180)

    def relayout(self, preserve=True):
        anchor, offset = None, 0
        top = self.verticalScrollBar().value()
        if preserve and self.rects:
            for index in self.visible_indices():
                rect = self.rects[index]
                if rect.bottom() >= top:
                    anchor = self.assets[index].identity if index < len(self.assets) else None
                    offset = top - rect.top()
                    break
        margin, gap = (12, 8) if self.miniature else (24, 16)
        width = max(100, self.viewport().width() - margin * 2)
        base_count = max(1, int((width + gap) // (self.width_target + gap)))
        count = max(1, base_count + self.column_adjustment)
        # Keep the medium preset at two columns on a normal-width window; the
        # large preset then remains visibly larger even below maximized width.
        if self.column_adjustment == 0 and width >= 400:
            count = max(2, count)
        tile_w = (width - gap * (count - 1)) / count
        heights = [margin] * count
        self.rects = []
        self.columns = [[] for _ in range(count)]
        self.column_ys = [[] for _ in range(count)]
        anchor_y = None
        for index, asset in enumerate(self.assets):
            column = min(range(count), key=heights.__getitem__)
            w, h = self.dimensions.get(asset.sha256, (4, 5))
            image_h = min(180 if self.miniature else 780,
                          max(30 if self.miniature else 115, tile_w * h / max(1, w)))
            rect = QRectF(margin + column * (tile_w + gap), heights[column], tile_w,
                          image_h + self.footer_height(asset))
            self.rects.append(rect)
            self.columns[column].append(index)
            self.column_ys[column].append(rect.top())
            heights[column] += rect.height() + gap
            if asset.identity == anchor:
                anchor_y = rect.top()
        self.verticalScrollBar().setRange(0, max(0, math.ceil(max(heights) + 8 - self.viewport().height())))
        self.verticalScrollBar().setPageStep(self.viewport().height())
        self.verticalScrollBar().setSingleStep(70)
        if anchor_y is not None:
            self.verticalScrollBar().setValue(int(anchor_y + offset))
        self.viewport().update()
        self.request_timer.start(10)

    def visible_indices(self, extra=0):
        top = max(0, self.verticalScrollBar().value() - extra)
        bottom = self.verticalScrollBar().value() + self.viewport().height() + extra
        result = []
        for column, ys in zip(self.columns, self.column_ys):
            start = max(0, bisect.bisect_right(ys, top) - 1)
            end = bisect.bisect_right(ys, bottom)
            result.extend(column[start:end])
        return sorted(result)

    def request_visible(self):
        self.needed.emit([self.assets[i].sha256 for i in self.visible_indices(350) if i < len(self.assets)])

    def on_scroll(self):
        self.viewport().update()
        self.request_timer.start(25)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.relayout()

    def scrollContentsBy(self, dx, dy):
        self.viewport().update()

    def pixmap(self, sha):
        if sha in self.pixmaps:
            self.pixmaps.move_to_end(sha)
            return self.pixmaps[sha]
        path = cache_path(self.cache, sha)
        if not path.is_file():
            return None
        if self.miniature:
            reader = QImageReader(str(path))
            size = reader.size()
            if size.isValid():
                reader.setScaledSize(size.scaled(QSize(180,360),Qt.AspectRatioMode.KeepAspectRatio))
            pix = QPixmap.fromImage(reader.read())
        else:
            pix = QPixmap(str(path))
        if pix.isNull():
            self.corrupt.emit(sha)
            return None
        self.pixmaps[sha] = pix
        self.pixmap_bytes += pix.width() * pix.height() * 4
        while self.pixmap_bytes > 96 * 1024 * 1024 and len(self.pixmaps) > 1:
            _, old = self.pixmaps.popitem(last=False)
            self.pixmap_bytes -= old.width() * old.height() * 4
        return pix

    def paintEvent(self, event):
        if self.window().isMinimized():return
        self.tag_hit_rects = []
        self.performance_hit_rects=[]
        painter = QPainter(self.viewport())
        painter.fillRect(self.viewport().rect(), QColor(theme_color('#0b0b0e')))
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        if not self.assets:
            painter.setPen(QColor(theme_color('#a29baa')))
            painter.setFont(QFont('Yu Gothic UI', 12))
            painter.drawText(self.viewport().rect(), Qt.AlignmentFlag.AlignCenter, self.empty_text)
            return
        top = self.verticalScrollBar().value()
        for index in self.visible_indices():
            if index >= len(self.assets):
                continue
            asset = self.assets[index]
            rect = self.rects[index].translated(0, -top)
            photo = QRectF(rect.x(), rect.y(), rect.width(), rect.height() - self.footer_height(asset))
            clip = QPainterPath()
            clip.addRoundedRect(photo, 5, 5)
            painter.save()
            painter.setClipPath(clip)
            painter.fillRect(photo, QColor(theme_color('#17161c')))
            pix = self.pixmap(asset.sha256)
            if pix:
                size = pix.size().scaled(photo.size().toSize(), Qt.AspectRatioMode.KeepAspectRatio)
                target = QRectF(photo.center().x() - size.width() / 2, photo.center().y() - size.height() / 2, size.width(), size.height())
                painter.drawPixmap(target, pix, QRectF(pix.rect()))
            else:
                painter.setPen(QColor(theme_color('#777180')))
                painter.setFont(QFont('Yu Gothic UI', 10))
                painter.drawText(photo, Qt.AlignmentFlag.AlignCenter, tr('プレビューなし') if asset.sha256 in self.failed else tr('準備中'))
            painter.restore()
            if asset.identity in self.multi_selection:
                painter.setPen(QPen(QColor('#71e0ca'),3))
                painter.setBrush(QColor(35,155,130,35))
                painter.drawRoundedRect(photo.adjusted(-1,-1,1,1),6,6)
                if self.miniature:
                    self.badge(painter,QRectF(photo.x()+3,photo.y()+3,18,18),'✓')
                else:
                    self.badge(painter,QRectF(photo.x()+10,photo.y()+10,55,23),tr('✓ 選択'))
            if asset.identity == self.selection:
                painter.setPen(QPen(QColor('#c1abed'), 2))
                painter.setBrush(Qt.BrushStyle.NoBrush)
                painter.drawRoundedRect(photo.adjusted(-2, -2, 2, 2), 7, 7)
            favorite = asset.identity in self.favorites
            heart = self.heart_rect(photo)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor('#df1a181f'))
            painter.drawEllipse(heart)
            painter.setPen(QColor('#dfcaff') if favorite else QColor('#f5effb'))
            painter.setFont(QFont('Segoe UI Symbol', 10 if self.miniature else 15))
            painter.drawText(heart, Qt.AlignmentFlag.AlignCenter, '♥' if favorite else '♡')
            if asset.kind != 'image':
                if self.miniature:
                    if asset.identity not in self.multi_selection:
                        self.badge(painter,QRectF(photo.x()+3,photo.y()+3,18 if asset.kind=='video' else 27,18),'▶' if asset.kind=='video' else 'GIF')
                else:
                    self.badge(painter, QRectF(photo.x() + 10, photo.y() + 10, 61 if asset.kind == 'video' else 34, 23), '▶ VIDEO' if asset.kind == 'video' else 'GIF')
            duplicates = self.group_counts.get(content_key(asset),1)
            if asset.total > 1 and not self.miniature:
                self.badge(painter, QRectF(photo.right() - 55, photo.top() + 49, 45, 23), f'{asset.media_index} / {asset.total}')
            caption = QRectF(rect.x(), photo.bottom() + (1 if self.miniature else 4), rect.width(), 16 if self.miniature else 19)
            painter.setFont(QFont('Yu Gothic UI', 8 if self.miniature else 10))
            painter.setPen(QColor(theme_color('#a29baa')))
            if self.miniature:
                painter.drawText(caption, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                                 painter.fontMetrics().elidedText(unknown_date(asset.day),Qt.TextElideMode.ElideRight,max(1,int(caption.width()))))
                continue
            text=unknown_date(asset.day)+(trf(' · 同じ画像 {0}件', duplicates) if self.grouped and duplicates>1 else '')+((' · '+asset.account_name) if asset.account_name else '')
            text=painter.fontMetrics().elidedText(text,Qt.TextElideMode.ElideRight,max(1,int(caption.width()-53)))
            painter.drawText(caption, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,text)
            painter.setPen(QColor(theme_color('#76707f')))
            painter.drawText(caption, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, {'image':tr('画像'),'gif':'GIF','video':tr('動画')}.get(asset.kind,asset.kind.upper()))
            tags=self.performance_tags.get(asset.performance_key,[])
            tags=sorted(tags,key=lambda tag:0 if isinstance(tag,dict) and tag.get('tag_name')=='#プロフィール訪問数1位' else 1)
            manual=self.manual_tags.get(asset.annotation_key,[])
            row_count=bool(tags)+bool(manual)
            if row_count:
                overlay=QRectF(photo.x(),photo.bottom()-row_count*25-15,photo.width(),row_count*25+15)
                gradient=QLinearGradient(0,overlay.top(),0,overlay.bottom())
                gradient.setColorAt(0,QColor(11,11,14,0));gradient.setColorAt(0.35,QColor(11,11,14,170));gradient.setColorAt(1,QColor(11,11,14,220))
                painter.save();painter.setClipPath(clip);painter.fillRect(overlay,gradient);painter.restore()
                tag_row=QRectF(photo.x()+6,photo.bottom()-row_count*25,photo.width()-12,22)
            if tags:
                self.performance_hit_rects.extend(self.draw_performance_tags(painter,tag_row,tags))
            if manual:
                row=tag_row.translated(0,25 if tags else 0)
                self.tag_hit_rects.extend(self.draw_performance_tags(painter,row,['#'+name for name in manual],manual=True))
        if self.drag_rect is not None:
            painter.setPen(QPen(QColor('#71e0ca'),1))
            painter.setBrush(QColor(80,210,180,45))
            painter.drawRect(self.drag_rect.translated(0,-top))

    @staticmethod
    def badge(painter, rect, text):
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor('#df151319'))
        painter.drawRoundedRect(rect, 3, 3)
        painter.setFont(QFont('Yu Gothic UI', 10))
        painter.setPen(QColor('#f3edf7'))
        painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, text)

    def draw_performance_tags(self, painter, row, tags, manual=False):
        font=QFont('Segoe UI',9)
        painter.setFont(font)
        x=row.x()
        shown=0
        hits=[]
        for tag in tags[:2]:
            name=tag['tag_name'] if isinstance(tag,dict) else str(tag)
            display_name=name if manual else tr(name)
            is_no1=isinstance(tag,dict) and tag.get('tag_type')=='top1'
            manual_bg,manual_fg=tag_colors(self.manual_colors.get(name.lstrip('#')))
            star='★ ' if is_no1 else ''
            width=min(painter.fontMetrics().horizontalAdvance(star+display_name)+16,row.right()-x)
            if width<30:
                break
            chip=QRectF(x,row.y()+1,width,20)
            painter.setPen(QPen(QColor('#ffe7a0'),1) if is_no1 else Qt.PenStyle.NoPen)
            painter.setBrush(QColor(manual_bg) if manual else QColor('#d8ad45') if is_no1 else QColor('#392f46'))
            painter.drawRoundedRect(chip,5,5)
            hits.append((chip,name.lstrip('#')))
            painter.setPen(QColor(manual_fg) if manual else QColor('#251b09') if is_no1 else QColor('#e0d2f1'))
            painter.drawText(QRectF(x+8,row.y(),width-16,22),Qt.AlignmentFlag.AlignLeft|Qt.AlignmentFlag.AlignVCenter,
                             painter.fontMetrics().elidedText(star+display_name,Qt.TextElideMode.ElideRight,int(width-16)))
            x+=width+4
            shown+=1
        remaining=len(tags)-shown
        if remaining and x+30<=row.right():
            painter.setPen(QColor('#a99ab9'))
            painter.drawText(QRectF(x,row.y(),30,17),Qt.AlignmentFlag.AlignLeft|Qt.AlignmentFlag.AlignVCenter,f'+{remaining}')
        return hits

    def heart_rect(self, photo):
        if self.miniature:
            return QRectF(photo.right() - 25, photo.top() + 3, 22, 22)
        return QRectF(photo.right() - 43, photo.top() + 9, 34, 34)

    def hit(self, point):
        p = point.toPointF() if hasattr(point, 'toPointF') else point
        for i in self.visible_indices():
            rect = self.rects[i].translated(0, -self.verticalScrollBar().value())
            if rect.contains(p):
                return i, rect
        return None, None

    def mousePressEvent(self, event):
        modifiers = event.modifiers()
        multiple = bool(modifiers & (Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.ShiftModifier))
        if event.button() == Qt.MouseButton.LeftButton and not multiple:
            for rect,name in self.performance_hit_rects:
                if rect.contains(event.position()):
                    self.performance_tag_clicked.emit(name)
                    return
            for rect,name in self.tag_hit_rects:
                if rect.contains(event.position()):
                    self.tag_clicked.emit(name)
                    return
        index, rect = self.hit(event.position())
        if index is None:
            if event.button()==Qt.MouseButton.LeftButton:
                self.begin_drag(event,None)
            return
        asset = self.assets[index]
        self.setFocus()
        if event.button() == Qt.MouseButton.RightButton:
            if asset.identity not in self.multi_selection:
                self.multi_selection.clear()
                self.multi_changed.emit()
                self.selection = asset.identity
                self.selected.emit(asset)
            self.context.emit(asset, event.globalPosition().toPoint())
        elif event.button() == Qt.MouseButton.LeftButton:
            if multiple:
                self.choose_multiple(index,modifiers)
            elif self.heart_rect(rect).contains(event.position()):
                self.favorite.emit(asset)
            else:
                self.begin_drag(event,asset)
        self.viewport().update()

    def begin_drag(self,event,asset):
        self.pending_click=asset
        self.drag_origin=event.position()+QPointF(0,self.verticalScrollBar().value())
        self.drag_point=event.position()
        self.drag_rect=None
        self.drag_base=set()

    def mouseMoveEvent(self,event):
        if self.drag_origin is None:
            super().mouseMoveEvent(event)
            return
        self.drag_point=event.position()
        point=self.drag_point+QPointF(0,self.verticalScrollBar().value())
        if self.drag_rect is None and (point-self.drag_origin).manhattanLength()<QApplication.startDragDistance():
            return
        self.update_drag_selection()
        if not self.drag_scroll_timer.isActive():self.drag_scroll_timer.start()

    def update_drag_selection(self):
        point=self.drag_point+QPointF(0,self.verticalScrollBar().value())
        self.drag_rect=QRectF(self.drag_origin,point).normalized()
        self.multi_selection={self.assets[i].identity for i,rect in enumerate(self.rects) if rect.intersects(self.drag_rect)}|self.drag_base
        self.viewport().update()

    def drag_scroll(self):
        if self.drag_rect is None or self.drag_point is None:return
        y=self.drag_point.y();height=self.viewport().height()
        step=-24 if y<32 else 24 if y>height-32 else 0
        if step:
            scroll=self.verticalScrollBar();scroll.setValue(scroll.value()+step)
            self.update_drag_selection()

    def mouseReleaseEvent(self,event):
        if event.button()!=Qt.MouseButton.LeftButton or self.drag_origin is None:
            super().mouseReleaseEvent(event)
            return
        dragged=self.drag_rect is not None
        asset=self.pending_click
        self.drag_scroll_timer.stop()
        self.drag_origin=self.drag_point=self.drag_rect=self.pending_click=None
        if not dragged:
            self.multi_selection.clear()
            if asset:
                self.range_anchor=asset.identity
                self.selection=asset.identity
                self.selected.emit(asset)
        self.multi_changed.emit()
        self.viewport().update()

    def choose_multiple(self,index,modifiers):
        asset=self.assets[index]
        if modifiers & Qt.KeyboardModifier.ShiftModifier:
            anchor=next((i for i,a in enumerate(self.assets) if a.identity==self.range_anchor),index)
            if not modifiers & Qt.KeyboardModifier.ControlModifier:
                self.multi_selection.clear()
            start,end=sorted((anchor,index))
            self.multi_selection.update(a.identity for a in self.assets[start:end+1])
        else:
            if asset.identity in self.multi_selection:
                self.multi_selection.remove(asset.identity)
            else:
                self.multi_selection.add(asset.identity)
            self.range_anchor=asset.identity
        self.multi_changed.emit()
        self.viewport().update()

    def mouseDoubleClickEvent(self, event):
        if event.modifiers() & (Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.ShiftModifier):
            return
        # The first click may open the panel and reflow the masonry.
        asset = next((a for a in self.assets if a.identity == self.selection), None)
        if asset:
            self.activated.emit(asset)

    def keyPressEvent(self, event):
        keys = {Qt.Key.Key_Right:1, Qt.Key.Key_Down:1, Qt.Key.Key_Left:-1, Qt.Key.Key_Up:-1}
        if event.key() in keys and self.assets:
            current = next((i for i,a in enumerate(self.assets) if a.identity == self.selection), -1)
            index = max(0, min(len(self.assets)-1, current + keys[event.key()]))
            self.selection = self.assets[index].identity
            self.selected.emit(self.assets[index])
            rect = self.rects[index]
            scroll = self.verticalScrollBar()
            if rect.top() < scroll.value():
                scroll.setValue(int(rect.top()) - 24)
            elif rect.bottom() > scroll.value() + self.viewport().height():
                scroll.setValue(int(rect.bottom()) - self.viewport().height() + 24)
            self.viewport().update()
        elif event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter) and self.selection:
            asset = next((a for a in self.assets if a.identity == self.selection), None)
            if asset:
                self.activated.emit(asset)
        else:
            super().keyPressEvent(event)
