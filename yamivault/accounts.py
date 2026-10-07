"""Account routing and private metadata; never relocates a backup or writes its DB."""
from dataclasses import replace
from pathlib import Path
import re
import json
import zipfile


def account_from_zip(path):
    from backup_engine.archive import records
    with zipfile.ZipFile(path) as archive:
        candidates=[i for i in archive.infolist() if i.filename.lower().endswith('/account.js') or i.filename.lower()=='account.js']
        if len(candidates)!=1 or candidates[0].file_size>4*1024*1024:
            return {}
        for row in records(archive,candidates[0]):
            data=row.get('account',row)
            owner=str(data.get('accountId') or data.get('id_str') or '')
            if owner:
                return {'owner':owner,'username':str(data.get('username') or '')[:80],
                        'account_display_name':str(data.get('accountDisplayName') or '')[:200]}
    return {}


def register_account(store,root,summary,completed=False):
    lid=store.library(root)
    old=store.get('library_account:'+lid,{})
    known=str(old.get('owner') or store.get('account:'+lid,'') or '')
    owner=str(summary.get('owner') or known)
    if known and owner and known!=owner:
        raise ValueError('別アカウントの保存先には取り込めません。保存先を選び直してください。')
    value={'owner':owner,'username':str(summary.get('username') or old.get('username') or '')[:80],
           'display_name':str(summary.get('account_display_name') or old.get('display_name') or '')[:200],
           'last_backup_at':store.now() if completed else old.get('last_backup_at','')}
    store.set('library_account:'+lid,value)
    if owner:store.set('account:'+lid,owner)
    if completed:store.set('last_backup_library',lid)
    return value


def libraries(store):
    result=[]
    for lid,root,added in store.db.execute('SELECT library_id,root,added_at FROM libraries'):
        meta=dict(store.get('library_account:'+lid,{}) or {})
        meta.setdefault('owner',str(store.get('account:'+lid,'') or ''))
        meta.update(library_id=lid,root=Path(root),added_at=added)
        result.append(meta)
    return result


def learn_existing_account(store,root,status):
    """Recover the handle from the recorded original ZIP, if still available."""
    lid=store.library(root)
    if store.get('library_account:'+lid,{}).get('username'):return
    row=store.db.execute('SELECT summary FROM import_jobs WHERE root=? ORDER BY updated_at DESC LIMIT 1',
                         (str(Path(root).resolve()),)).fetchone()
    # Older versions stored import roots with original casing.
    if not row:
        row=store.db.execute('SELECT summary FROM import_jobs WHERE lower(root)=? ORDER BY updated_at DESC LIMIT 1',
                            (str(Path(root).resolve()).lower(),)).fetchone()
    summary=json.loads(row[0]) if row else {}
    run=status.get('last_complete') or status.get('last_attempt') or {}
    path=summary.get('zip_path') or run.get('zip_path')
    if not summary.get('username') and path:
        try:
            found=account_from_zip(path)
            known=store.get('account:'+lid)
            if found and (not known or found['owner']==known):summary.update(found)
        except (OSError,ValueError,zipfile.BadZipFile):pass
    known=store.get('account:'+lid)
    if summary.get('owner') and (not known or str(summary['owner'])==str(known)):register_account(store,root,summary)


def account_groups(store):
    groups={}
    for entry in libraries(store):
        if not entry.get('owner') and not (entry['root']/'.system/catalog.sqlite3').is_file():continue
        key=entry.get('owner') or 'library:'+entry['library_id']
        group=groups.setdefault(key,{'key':key,'entries':[],'username':'','label':''})
        group['entries'].append(entry)
        if entry.get('username'):group['username']=entry['username']
    for group in groups.values():
        group['entries'].sort(key=lambda e:(e.get('last_backup_at',''),e['added_at']),reverse=True)
        group['label']='@'+group['username'] if group['username'] else (
            'アカウントID '+group['key'] if not group['key'].startswith('library:') else group['entries'][0]['root'].name+'（アカウント未確認）')
    return sorted(groups.values(),key=lambda g:g['label'].casefold())


def startup_root(store,remembered=None):
    entries=libraries(store)
    preferred=store.get('last_backup_library')
    selected=next((e for e in entries if e['library_id']==preferred),None)
    if selected and (selected['root']/'.system/catalog.sqlite3').is_file():return selected['root']
    for root, in store.db.execute("SELECT root FROM import_jobs WHERE phase IN ('complete','warnings') ORDER BY updated_at DESC"):
        if (Path(root)/'.system/catalog.sqlite3').is_file():return Path(root)
    return Path(remembered) if remembered else None


def folder_name(summary):
    handle=str(summary.get('username') or ('account-'+str(summary.get('owner') or 'unknown'))).lstrip('@')
    handle=re.sub(r'[^A-Za-z0-9_-]','_',handle).strip(' ._')[:64] or 'account'
    if re.fullmatch(r'(?i)(CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])',handle):handle='account-'+handle
    dates=[str(summary.get(k) or '')[:4] for k in ('media_min','media_max','earliest_post_at','latest_post_at')]
    years=sorted({y for y in dates if re.fullmatch(r'\d{4}',y) and 1900<=int(y)<=9999})
    period=(years[0] if years[0]==years[-1] else years[0]+'-'+years[-1]) if years else '年不明'
    return handle+'-'+period


def route_destination(store,base,summary):
    """Reuse the same account history; preview a new named child without creating it."""
    from .import_destination import validate_destination
    base=Path(base).resolve()
    owner=str(summary.get('owner') or '')
    if base.name==folder_name(summary) and not (base/'.system/catalog.sqlite3').is_file():
        return validate_destination(base,store.directory)
    if (base/'.system/catalog.sqlite3').is_file():
        from .backup_status import read_status
        learn_existing_account(store,base,read_status(base))
        lid=store.library(base)
        known=store.get('account:'+lid,'')
        if not owner or not known:
            raise ValueError('このZIPまたは既存保存先のアカウントを確認できません。新しい空の保存先を選んでください。')
        if str(known)==owner:return base
        base=base.parent
    # Existing named children (including a prior year range) stay in place.
    for entry in sorted(libraries(store),key=lambda e:e.get('last_backup_at',''),reverse=True):
        if owner and str(entry.get('owner') or '')==owner and entry['root'].parent.resolve()==base and (entry['root']/'.system/catalog.sqlite3').is_file():
            return validate_destination(entry['root'],store.directory)
    destination=base/folder_name(summary)
    if not destination.resolve().is_relative_to(base):
        raise ValueError('自動保存先が選択した場所の外へつながっています。別の保存場所を選んでください。')
    if destination.is_dir() and (destination/'.system/catalog.sqlite3').is_file():
        from .backup_status import read_status
        learn_existing_account(store,destination,read_status(destination))
        known=store.get('account:'+store.library(destination),'')
        if not owner or str(known)!=owner:
            destination=base/(folder_name(summary)+'-'+(re.sub(r'\W','_',owner)[:40] or 'new'))
    if not destination.resolve().is_relative_to(base):
        raise ValueError('自動保存先が選択した場所の外へつながっています。別の保存場所を選んでください。')
    return validate_destination(destination,store.directory)


def scoped_asset(asset,entry):
    return replace(asset,library_id=entry['library_id'],library_root=str(entry['root']),
                   account_name='@'+entry['username'] if entry.get('username') else entry.get('owner',''))
