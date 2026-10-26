"""Unify private identities only for paths proven to be the same directory.

Never infer identity from an account handle or matching artwork. A verified
SQLite backup precedes an atomic merge; the artwork catalog is never written.
"""
from pathlib import Path
from datetime import datetime,timezone
import sqlite3,uuid,os
from .i18n import tr


def _rows(db,table,library):
    cursor=db.execute(f'SELECT * FROM {table} WHERE library_id=?',(library,))
    columns=[c[0] for c in cursor.description]
    return [dict(zip(columns,row)) for row in cursor]


def _insert(db,table,row):
    columns=list(row)
    db.execute(f'INSERT OR IGNORE INTO {table} ({",".join(columns)}) VALUES ({",".join("?" for _ in columns)})',list(row.values()))


def _merge(store,target,source):
    db=store.db
    tags=store.manual_tags(target);by_name={name.casefold():ident for ident,name in tags.items()};tag_map={}
    for row in _rows(db,'manual_tags',source):
        ident=by_name.get(row['name_key'])
        if ident is None:
            ident=row['tag_id'] if row['tag_id'] not in tags else uuid.uuid4().hex
            _insert(db,'manual_tags',dict(row,library_id=target,tag_id=ident))
            tags[ident]=row['name'];by_name[row['name_key']]=ident
        tag_map[row['tag_id']]=ident
    imports={}
    for row in _rows(db,'analytics_imports',source):
        existing=db.execute('SELECT import_id FROM analytics_imports WHERE library_id=? AND file_sha256=?',(target,row['file_sha256'])).fetchone()
        imports[row['import_id']]=existing[0] if existing else row['import_id']
        if not existing:db.execute('UPDATE analytics_imports SET library_id=? WHERE import_id=?',(target,row['import_id']))
    tables=('favorites','hidden_assets','warning_assets','manual_tag_colors','manual_asset_tags',
            'post_asset_tags','post_tag_suppressions','post_text','asset_views',
            'analytics_posts','analytics_asset_links','performance_tags')
    for table in tables:
        if table in ('analytics_posts','analytics_asset_links','performance_tags'):
            for ident,mapped in imports.items():
                if ident==mapped:db.execute(f'UPDATE {table} SET library_id=? WHERE library_id=? AND import_id=?',(target,source,ident))
        for row in _rows(db,table,source):
            row['library_id']=target
            if 'tag_id' in row:row['tag_id']=tag_map[row['tag_id']]
            if 'import_id' in row:row['import_id']=imports[row['import_id']]
            if table=='post_text':
                # The newer alias contains text from the new archive.
                db.execute('INSERT INTO post_text VALUES (?,?,?,?) ON CONFLICT(library_id,post_id) DO UPDATE SET text=excluded.text,hashtags_json=excluded.hashtags_json',
                           (target,row['post_id'],row['text'],row['hashtags_json']))
            elif table=='asset_views':
                db.execute('INSERT INTO asset_views VALUES (?,?,?,?) ON CONFLICT(library_id,sha256) DO UPDATE SET last_seen=MAX(asset_views.last_seen,excluded.last_seen),view_count=MAX(asset_views.view_count,excluded.view_count)',
                           (target,row['sha256'],row['last_seen'],row['view_count']))
            else:_insert(db,table,row)
        db.execute(f'DELETE FROM {table} WHERE library_id=?',(source,))
    db.execute('DELETE FROM analytics_imports WHERE library_id=?',(source,))
    groups,members=store.manual_tag_groups(target);other_groups,other_members=store.manual_tag_groups(source)
    group_map={}
    for ident,name in other_groups.items():
        match=next((i for i,n in groups.items() if n==name),None)
        mapped=match or (ident if ident not in groups else uuid.uuid4().hex)
        groups[mapped]=name;group_map[ident]=mapped
    for tag,group in other_members.items():
        if tag in tag_map:members.setdefault(tag_map[tag],group_map[group])
    store._write_tag_groups(target,groups,members)
    rules=store.post_tag_rules(target)
    for tag,rule in store.post_tag_rules(source).items():
        if tag not in tag_map:continue
        mapped=tag_map[tag]
        if mapped not in rules:rules[mapped]=rule
        else:rules[mapped]=dict(rules[mapped],aliases=list(dict.fromkeys(rules[mapped].get('aliases',[])+rule.get('aliases',[]))))
    store._write_post_setting('post_tag_rules:'+target,rules)
    left=store.post_tag_options(target);right=store.post_tag_options(source)
    keywords={k['name'].casefold():dict(k) for k in left['keywords']}
    for rule in right['keywords']:
        key=rule['name'].casefold()
        if key not in keywords:keywords[key]=dict(rule)
        else:keywords[key]['aliases']=list(dict.fromkeys(keywords[key].get('aliases',[])+rule.get('aliases',[])))
    left['keywords']=list(keywords.values());left['excluded']=list(dict.fromkeys(left['excluded']+right['excluded']))
    store._write_post_setting('post_tag_options:'+target,left)
    frequent=store.get('frequent_tags:'+target,[])
    frequent+= [tag_map[t] for t in store.get('frequent_tags:'+source,[]) if t in tag_map]
    store._write_post_setting('frequent_tags:'+target,list(dict.fromkeys(frequent)))
    meta=store.get('library_account:'+target,{}) or {};other=store.get('library_account:'+source,{}) or {}
    merged=dict(other,**meta);merged['last_backup_at']=max(meta.get('last_backup_at',''),other.get('last_backup_at',''))
    store._write_post_setting('library_account:'+target,merged)
    owner=store.get('account:'+target) or store.get('account:'+source)
    if owner:store._write_post_setting('account:'+target,owner)
    for key in ('last_backup_library',):
        if store.get(key)==source:store._write_post_setting(key,target)
    if store.get('account_selection')=='library:'+source:store._write_post_setting('account_selection','library:'+target)
    for prefix in ('manual_tag_groups:','post_tag_rules:','post_tag_options:','post_tag_cache_v1:','post_tag_cache_v2:','frequent_tags:','library_account:','account:'):
        db.execute('DELETE FROM settings WHERE key=?',(prefix+source,))
    for prefix in ('post_tag_cache_v1:','post_tag_cache_v2:'):
        db.execute('DELETE FROM settings WHERE key=?',(prefix+target,))
    db.execute('DELETE FROM manual_tags WHERE library_id=?',(source,))
    db.execute('DELETE FROM libraries WHERE library_id=?',(source,))


def resolve_library(store,root):
    root=Path(root).resolve();key=str(root).casefold()
    rows=store.db.execute('SELECT library_id,root,added_at FROM libraries ORDER BY added_at,library_id').fetchall()
    matches=[]
    for ident,stored,added in rows:
        if stored==key:matches.append((ident,stored,added));continue
        try:
            if root.is_dir() and Path(stored).is_dir() and os.path.samefile(root,stored):matches.append((ident,stored,added))
        except OSError:continue
    if not matches:return None
    if len(matches)==1 and matches[0][1]==key:return matches[0][0]
    if store.db.in_transaction:raise sqlite3.OperationalError('Library identity recovery requires a committed connection')
    owners={str(store.get('account:'+row[0]) or '') for row in matches}-{''}
    if len(owners)>1:raise ValueError(tr('同じ保存先のアカウント設定が一致しません。元データを保持して中止しました。'))
    backup=store.directory/'backups';backup.mkdir(exist_ok=True)
    stamp=datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S-%f')
    snapshot=sqlite3.connect(backup/('before-library-identity-'+stamp+'.sqlite3'))
    try:
        store.db.backup(snapshot)
        if snapshot.execute('PRAGMA integrity_check').fetchone()[0]!='ok':raise sqlite3.DatabaseError('Library identity backup failed integrity check')
    finally:snapshot.close()
    target=matches[0][0]
    with store.db:
        store.db.execute('BEGIN IMMEDIATE')
        for ident,stored,added in matches:
            current=store.db.execute('SELECT root,added_at FROM libraries WHERE library_id=?',(ident,)).fetchone()
            if current!=(stored,added):raise sqlite3.OperationalError('Library identities changed concurrently; reopen the library')
        for ident,stored,added in matches[1:]:_merge(store,target,ident)
        store.db.execute('UPDATE libraries SET root=? WHERE library_id=?',(key,target))
        store._write_post_setting('library_identity_recovery:'+target,{'merged_ids':[r[0] for r in matches[1:]],'backup':stamp})
        if store.db.execute('PRAGMA integrity_check').fetchone()[0]!='ok':raise sqlite3.DatabaseError('Library identity merge failed integrity check')
    store._analytics_rank_cache.clear()
    return target
