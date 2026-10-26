"""Compact manual-tag controls for the gallery and artwork detail panel."""
from .i18n import tr,trf
from urllib.parse import unquote
from urllib.parse import quote
from html import escape
from .tag_cloud import TagCloud
from PySide6.QtGui import QColor, QIcon, QPixmap
from .tag_colors import DEFAULT_COLOR, tag_colors
from .appearance import theme_color
from PySide6.QtWidgets import QMenu


class ManualTagUiMixin:
    @staticmethod
    def mark_tag_menu_action(action,label,selected):
        # Qt can replace its native check indicator with the tag's color icon.
        # Keep an explicit mark in the label so both are always visible.
        action.setCheckable(True)
        def update(checked):
            action.setText(('✓  ' if checked else '')+label)
            font=action.font();font.setBold(checked);action.setFont(font)
        action.toggled.connect(update)
        action.setChecked(selected)
        update(selected)

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
        self.tags_manage_button.setEnabled(bool(self.library_id) and not self.aggregate_entries)
        self.manual_definitions=self.store.manual_tags(self.library_id) if self.library_id else {}
        self.manual_colors=self.store.manual_tag_colors(self.library_id) if self.library_id else {}
        self.manual_mapping=self.store.manual_tag_map(self.library_id) if self.library_id else {}
        rules=self.store.post_tag_rules(self.library_id) if self.library_id else {}
        self.manual_search_aliases={i:rule.get('aliases',[]) for i,rule in rules.items()}
        if self.aggregate_entries:
            self.manual_definitions,self.manual_colors,self.manual_mapping=self.combined_manual_tags()
            self.manual_search_aliases={}
            for entry,_raw,_status in self.load_job.bundles:
                rules=self.store.post_tag_rules(entry['library_id'])
                for ident,sources in self.combined_tag_sources.items():
                    terms=rules.get(sources.get(entry['library_id']),{}).get('aliases',[])
                    self.manual_search_aliases.setdefault(ident,[]).extend(terms)
        self.manual_groups,self.manual_group_members=self.store.manual_tag_groups(self.library_id) if self.library_id else ({},{})
        if self.aggregate_entries:
            import hashlib
            for entry,_raw,_status in self.load_job.bundles:
                groups,members=self.store.manual_tag_groups(entry['library_id'])
                for ident,sources in self.combined_tag_sources.items():
                    local=sources.get(entry['library_id']);group=members.get(local)
                    if group in groups:
                        key='group:'+hashlib.sha256(groups[group].casefold().encode()).hexdigest()
                        self.manual_groups.setdefault(key,groups[group]);self.manual_group_members.setdefault(ident,key)
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
        self.populate_manual_tag_menu(menu,assign=assign,targets=self.selected_tag_assets())
        if not self.manual_definitions:
            action=menu.addAction(tr('タグは未登録です'))
            action.setEnabled(False)
        menu.addSeparator()
        menu.addAction(tr('タグを登録・管理…'),self.manage_manual_tags)
        menu.exec(anchor.mapToGlobal(anchor.rect().bottomLeft()))

    def populate_manual_tag_menu(self, menu, *, assign=False, frequent=False, targets=None):
        targets=list(targets or [])
        counts=self.tag_usage_counts()
        ordered=sorted(self.manual_definitions,key=lambda i:(-counts[i],self.manual_definitions[i].casefold()))
        members=getattr(self,'manual_group_members',{})
        groups=getattr(self,'manual_groups',{})
        def add(parent,ident):
            action=parent.addAction(self.manual_definitions[ident] if assign else '#'+self.manual_definitions[ident])
            action.setIcon(self.manual_tag_icon(ident))
            common=bool(targets) and all(ident in self.manual_mapping.get(a.annotation_key,set()) for a in targets)
            if assign:
                action.setCheckable(True);action.setChecked(common)
            else:
                self.mark_tag_menu_action(action,'#'+self.manual_definitions[ident],ident in self.selected_manual_tags)
            action.setToolTip(trf('{0:,}作品に使用 · 付与済みならクリックで解除',counts[ident]) if assign else tr('クリックで絞り込み'))
            if assign:action.triggered.connect(lambda _checked=False,i=ident,c=common:self.apply_tag_batch([i],not c,targets=targets))
            else:action.triggered.connect(lambda _checked=False,i=ident:self.toggle_manual_filter(i))
        ungrouped=[i for i in ordered if members.get(i) not in groups]
        for ident in ungrouped[:10] if frequent else ungrouped:add(menu,ident)
        populated={gid:[i for i in ordered if members.get(i)==gid] for gid in groups}
        for gid in sorted(groups,key=lambda key:(-max((counts[i] for i in populated[key]),default=0),groups[key].casefold())):
            if not populated[gid]:continue
            child=menu.addMenu(groups[gid])
            for ident in populated[gid]:add(child,ident)
        if frequent and len(ungrouped)>10:
            child=menu.addMenu(tr('その他のタグ'))
            for ident in ungrouped[10:]:add(child,ident)

    def manage_manual_tags(self):
        if self.importer.active or self.import_panel.analytics_busy:
            self.toast(tr('アーカイブ取り込みが終わってから操作してください。'));return
        if not self.require_single_account() or not self.library_id:
            return
        from .tag_manager import TagManagerDialog
        TagManagerDialog(self).exec()
