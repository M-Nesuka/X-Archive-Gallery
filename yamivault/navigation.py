"""Transient navigation history and compact collection filters; no catalog writes."""
from .i18n import tr,trf
from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import QMenu


class NavigationMixin:
    def filter_state(self):
        combos=('sort_combo','year','month','media_kind','discovery_mode','discovery_limit','discovery_post_info')
        boxes=('discovery_exclude_favorites','discovery_recent','discovery_high','discovery_no1','discovery_no_high_unfav')
        return {'combos':{n:getattr(self,n).currentData() for n in combos},
            'boxes':{n:getattr(self,n).isChecked() for n in boxes},
            'search':self.search.text(),'manual':tuple(sorted(self.selected_manual_tags)),
            'performance':tuple(sorted(self.selected_performance_tags)),'mode':self.performance_mode,
            'favorite':self.favorites_button.isChecked(),'hidden':self.hidden_only,
            'group':self.group_duplicates,'seed':self.random_seed,'discovery_seed':self.discovery_seed}

    def navigation_view(self):
        return {'scroll':self.gallery.verticalScrollBar().value(),
            'current':self.current.identity if self.current else None,
            'details':self.details.isVisible(),'details_scroll':self.details_scroll.verticalScrollBar().value()}

    def remember_filter_navigation(self):
        state=self.filter_state()
        if not self._restoring_navigation and self._last_filter_state is not None and self._last_filter_state!=state:
            self.navigation_history.append((self._last_filter_state,self.navigation_view()))
            self.navigation_history=self.navigation_history[-60:]
        self._last_filter_state=state
        self.back_button.setEnabled(bool(self.navigation_history))

    def go_back(self):
        if self.isFullScreen():self.close_large();return
        if self.stack.currentIndex()==1:self.close_large();return
        if not self.navigation_history:return
        state,view=self.navigation_history.pop()
        self._restoring_navigation=True
        self.search_timer.stop()
        try:
            for name,value in state['combos'].items():
                control=getattr(self,name);control.blockSignals(True)
                control.setCurrentIndex(max(0,control.findData(value)));control.blockSignals(False)
            for name,value in state['boxes'].items():
                control=getattr(self,name);control.blockSignals(True);control.setChecked(value);control.blockSignals(False)
            self.search.blockSignals(True);self.search.setText(state['search']);self.search.blockSignals(False)
            self.selected_manual_tags=set(state['manual']) & self.manual_definitions.keys()
            self.selected_performance_tags=set(state['performance']);self.performance_mode=state['mode']
            self.favorites_button.setChecked(state['favorite']);self.hidden_only=state['hidden']
            self.hidden_mode_button.setChecked(self.hidden_only)
            self.group_duplicates=state['group'];self.group_button.blockSignals(True)
            self.group_button.setChecked(self.group_duplicates);self.group_button.blockSignals(False)
            self.update_group_button_label(self.group_duplicates)
            self.sort_order=self.sort_combo.currentData();self.random_seed=state['seed'];self.discovery_seed=state['discovery_seed']
            self.store.set('sort_order',self.sort_order);self.store.set('group_duplicates',self.group_duplicates)
            self.month.setEnabled(self.year.currentData()!='__unknown__')
            self.reload_manual_tags();self.apply_filters()
            asset=next((a for a in self.matches if a.identity==view['current']),None)
            if asset and view['details']:self.select_asset(asset)
            else:self.close_details()
            self.gallery.verticalScrollBar().setValue(view['scroll'])
            self.details_scroll.verticalScrollBar().setValue(view['details_scroll'])
            QTimer.singleShot(0,lambda:self.gallery.verticalScrollBar().setValue(view['scroll'])
                if not self.closing and self._last_filter_state==state else None)
        finally:
            self._restoring_navigation=False
            self.back_button.setEnabled(bool(self.navigation_history))

    def go_home(self):
        """Return to the starting gallery without changing artwork annotations."""
        previous=self.filter_state();view=self.navigation_view()
        restoring=self._restoring_navigation
        self._restoring_navigation=True
        self.search_timer.stop()
        try:
            self.close_details();self.close_import();self.discovery_panel.hide()
            for name in ('sort_combo','year','month','media_kind','discovery_mode','discovery_limit','discovery_post_info'):
                control=getattr(self,name);blocked=control.blockSignals(True)
                control.setCurrentIndex(0);control.blockSignals(blocked)
            for name in ('discovery_exclude_favorites','discovery_recent','discovery_high','discovery_no1','discovery_no_high_unfav'):
                control=getattr(self,name);blocked=control.blockSignals(True)
                control.setChecked(False);control.blockSignals(blocked)
            blocked=self.search.blockSignals(True);self.search.clear();self.search.blockSignals(blocked)
            self.month.setEnabled(True)
            self.selected_manual_tags.clear();self.selected_performance_tags.clear();self.performance_mode=''
            self.hidden_only=False;self.hidden_mode_button.setChecked(False);self.favorites_button.setChecked(False)
            self.sort_order='newest';self.random_seed='';self.discovery_seed=''
            self.store.set('sort_order','newest')
            self.clear_multi_selection();self.reload_manual_tags();self.apply_filters()
            self.gallery.verticalScrollBar().setValue(0)
            state=self.filter_state()
            QTimer.singleShot(0,lambda:self.gallery.verticalScrollBar().setValue(0)
                if not self.closing and self._last_filter_state==state else None)
        finally:self._restoring_navigation=restoring
        if not restoring and (previous!=self.filter_state() or view!=self.navigation_view()):
            self.navigation_history.append((previous,view));self.navigation_history=self.navigation_history[-60:]
        self.back_button.setEnabled(bool(self.navigation_history))
        self.gallery.setFocus()

    def toggle_performance_filter(self,name):
        name='#'+name.lstrip('#')
        if name in self.selected_performance_tags:self.selected_performance_tags.remove(name)
        else:self.selected_performance_tags.add(name)
        self.apply_filters()
        if self.current:self.update_performance_details(self.current)

    def set_performance_mode(self,mode):
        self.performance_mode='' if self.performance_mode==mode else mode
        self.apply_filters()

    def clear_collection_filters(self):
        self.performance_mode='';self.selected_performance_tags.clear();self.selected_manual_tags.clear()
        self.hidden_only=False;self.hidden_mode_button.setChecked(False);self.favorites_button.setChecked(False)
        self.reload_manual_tags();self.apply_filters()

    def collection_menu(self):
        menu=QMenu(self)
        for title,checked,callback in [
            (trf('お気に入り · {0:,}', len(self.favorites)),self.favorites_button.isChecked(),lambda:self.set_favorites_only(not self.favorites_button.isChecked())),
            (tr('高成績タグあり'),self.performance_mode=='high',lambda:self.set_performance_mode('high')),
            (tr('NO.1タグあり'),self.performance_mode=='no1',lambda:self.set_performance_mode('no1')),
            (trf('非表示 · {0:,}', len(self.hidden_hashes)),self.hidden_only,lambda:self.set_hidden_only(not self.hidden_only))]:
            action=menu.addAction(title);action.setCheckable(True);action.setChecked(checked);action.triggered.connect(callback)
        manual=menu.addMenu(tr('手動タグ'))
        for ident,name in self.manual_definitions.items():
            action=manual.addAction('#'+name);action.setCheckable(True);action.setChecked(ident in self.selected_manual_tags)
            action.setIcon(self.manual_tag_icon(ident))
            action.triggered.connect(lambda _checked=False,i=ident:self.toggle_manual_filter(i))
        performance=menu.addMenu(tr('X成績タグ'))
        names=sorted({badge['tag_name'] for record in self.performance_by_post.values() for badge in record.get('tag_badges',[])})
        for name in names:
            action=performance.addAction(tr(name));action.setCheckable(True);action.setChecked(name in self.selected_performance_tags)
            action.triggered.connect(lambda _checked=False,n=name:self.toggle_performance_filter(n))
        if not names:performance.addAction(tr('成績タグはまだありません')).setEnabled(False)
        menu.addSeparator();menu.addAction(tr('手動タグを登録・管理…'),self.manage_manual_tags)
        return menu

    def clear_performance_filters(self):
        self.performance_mode='';self.selected_performance_tags.clear();self.apply_filters()

    def open_collection_menu(self):
        menu=self.collection_menu();menu.exec(self.all_button.mapToGlobal(self.all_button.rect().bottomLeft()));menu.deleteLater()

    def update_collection_label(self):
        parts=[]
        if self.hidden_only:parts.append(tr('非表示'))
        elif self.favorites_button.isChecked():parts.append(tr('お気に入り'))
        if self.performance_mode:parts.append(tr('高成績') if self.performance_mode=='high' else 'NO.1')
        if self.selected_manual_tags:parts.append(trf('タグ {0}', len(self.selected_manual_tags)))
        if self.selected_performance_tags:parts.append(trf('成績タグ {0}', len(self.selected_performance_tags)))
        self.all_button.setText((' · '.join(parts) if parts else tr('すべての作品'))+' ▼')
        self.all_button.setChecked(bool(parts))
