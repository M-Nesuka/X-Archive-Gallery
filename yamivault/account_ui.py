"""Compact account switcher and per-library routing for a combined gallery."""
from .i18n import tr,trf
from collections import defaultdict
from pathlib import Path
import hashlib
from .accounts import account_groups,scoped_asset


class AccountUiMixin:
    def account_library(self,asset):
        return asset.library_id or self.library_id

    def rebuild_account_menu(self):
        groups=account_groups(self.store)
        self.account_groups={g['key']:g for g in groups}
        self.account_switch.blockSignals(True)
        self.account_switch.clear()
        self.account_switch.addItem(tr('すべてのアカウント'),'all')
        selected='all' if self.account_scope=='all' else None
        for group in groups:
            self.account_switch.addItem(group['label'],group['key'])
            if selected is None and any(e['root'].resolve()==self.root.resolve() for e in group['entries']):selected=group['key']
        if not groups:self.account_switch.addItem(tr('アカウント未登録'),'')
        self.account_switch.addItem(tr('＋ アカウントを追加…'),'add')
        self.account_switch.setCurrentIndex(max(0,self.account_switch.findData(selected or '')))
        self.account_switch.blockSignals(False)

    def switch_account(self,index):
        key=self.account_switch.itemData(index)
        if self.loading or self.importer.active or self.import_panel.analytics_busy or self.import_panel.preview_busy:
            self.toast(tr('読み込み・取り込みが終わってから切り替えられます。'))
            self.rebuild_account_menu();return
        if not key:return
        if key=='add':
            self.open_import()
            self.importer.reset();self.import_panel.pending_zip=None;self.import_panel.clear_csv()
            self.import_panel.pending_destination=None
            self.import_panel.flow_hint.setText(tr('保存する場所を選び、別アカウントのZIPを追加してください。@ユーザー名と投稿年のフォルダーを自動で作ります。'))
            self.import_panel.update_state();self.rebuild_account_menu();return
        groups=account_groups(self.store)
        entries=[e for g in groups if key=='all' or g['key']==key for e in g['entries']]
        if not entries:return
        self.close_details();self.close_import();self.clear_multi_selection()
        self.go_home()
        self.account_scope=key
        self.aggregate_entries=entries if key=='all' or len(entries)>1 else []
        self._account_changed=True
        if self.aggregate_entries:self.refresh()
        else:self.refresh(entries[0]['root'])

    def load_combined_annotations(self):
        self.favorites=set();self.hidden_hashes=set();self.views={}
        for entry,raw_assets,_status in self.load_job.bundles:
            lid=entry['library_id']
            self.favorites.update((lid+'|'+key,sha) for key,sha in self.store.favorites(lid))
            self.hidden_hashes.update(lid+'|'+sha for sha in self.store.hidden_hashes(lid))
            self.views.update({lid+'|'+sha:v for sha,v in self.store.asset_views(lid).items()})

    def combined_manual_tags(self):
        definitions={};mapping={};colors={};self.combined_tag_sources={}
        for entry,_raw,_status in self.load_job.bundles:
            lid=entry['library_id'];local=self.store.manual_tags(lid)
            local_colors=self.store.manual_tag_colors(lid)
            local_to_global={ident:'all:'+hashlib.sha256(name.casefold().encode('utf-8')).hexdigest() for ident,name in local.items()}
            for ident,name in local.items():
                global_id=local_to_global[ident]
                definitions.setdefault(global_id,name)
                colors.setdefault(global_id,local_colors.get(ident,'teal'))
                self.combined_tag_sources.setdefault(global_id,{})[lid]=ident
            for sha,ids in self.store.manual_tag_map(lid).items():
                mapping[lid+'|'+sha]={local_to_global[i] for i in ids if i in local}
        return definitions,colors,mapping

    def apply_account_tags(self,targets,identifiers,enabled):
        if not self.aggregate_entries:
            return self.store.bulk_manual_tags(self.library_id,{a.sha256 for a in targets},identifiers,enabled)
        batches=defaultdict(set)
        for asset in targets:batches[self.account_library(asset)].add(asset.sha256)
        result={'unique_images':sum(len(v) for v in batches.values()),'tag_count':len(set(identifiers)),'changed':0,'unchanged':0}
        # One transaction across the selected accounts; an error rolls back all.
        names={i:self.manual_definitions[i] for i in identifiers}
        with self.store.db:
            for lid,hashes in batches.items():
                local={name.casefold():i for i,name in self.store.manual_tags(lid).items()}
                for ident,name in names.items():
                    actual=local.get(name.casefold())
                    if actual is None:
                        if not enabled:
                            result['unchanged']+=len(hashes);continue
                        import uuid
                        actual=uuid.uuid4().hex
                        self.store.db.execute('INSERT INTO manual_tags VALUES (?,?,?,?)',(lid,actual,name,name.casefold()))
                        self.store.db.execute('INSERT INTO manual_tag_colors VALUES (?,?,?)',(lid,actual,self.manual_colors.get(ident,'teal')))
                    for sha in hashes:
                        if enabled:
                            cursor=self.store.db.execute('INSERT OR IGNORE INTO manual_asset_tags VALUES (?,?,?)',(lid,sha,actual))
                        else:
                            cursor=self.store.db.execute('DELETE FROM manual_asset_tags WHERE library_id=? AND sha256=? AND tag_id=?',(lid,sha,actual))
                        result['changed']+=cursor.rowcount
                        result['unchanged']+=1-cursor.rowcount
        return result

    def route_selection_state(self,targets,mode,enabled):
        batches=defaultdict(list)
        for asset in targets:batches[self.account_library(asset)].append(asset)
        for lid,assets in batches.items():
            if mode=='favorite':self.store.bulk_favorites(lid,[a.source_identity for a in assets],enabled)
            else:self.store.bulk_hidden(lid,[a.sha256 for a in assets],enabled)
        if self.aggregate_entries:self.load_combined_annotations()
        else:
            self.favorites=self.store.favorites(self.library_id)
            self.hidden_hashes=self.store.hidden_hashes(self.library_id)

    def require_single_account(self):
        if not self.aggregate_entries:return True
        self.toast(tr('この操作は @アカウントを選んでから行ってください。'))
        self.account_switch.setFocus();self.account_switch.showPopup()
        return False
