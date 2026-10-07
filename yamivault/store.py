"""X Archive Gallery metadata store. The backup catalog is never migrated."""
from __future__ import annotations

import json
import hashlib
import os
import re
import shutil
import sqlite3
import uuid
import zipfile
from pathlib import Path
from datetime import datetime, timezone


IMAGE_EXTENSIONS={'.jpg','.jpeg','.png','.webp','.gif','.bmp','.tif','.tiff','.avif','.heic','.heif','.jfif'}
VIDEO_EXTENSIONS={'.mp4','.mov','.webm','.m4v','.mkv','.avi','.mpeg','.mpg','.3gp','.ts'}
MAX_IMPORTED_MEDIA=1024*1024*1024


def warning_media_path(data_dir,relative):
    root=Path(data_dir).resolve()
    rel=Path(relative)
    if rel.is_absolute() or '..' in rel.parts or ':' in relative or not rel.parts or rel.parts[0]!='warning_media':
        raise ValueError('追加メディアの保存先が不正です。')
    path=(root/rel).resolve()
    if not path.is_relative_to(root) or path==root:
        raise ValueError('X Archive Galleryの保存領域外は開けません。')
    return path


class VaultStore:
    def __init__(self, directory: Path):
        self.directory = Path(directory).resolve()
        self.directory.mkdir(parents=True, exist_ok=True)
        self.path = self.directory / 'yami_vault.sqlite3'
        existed=self.path.exists()
        self.db = sqlite3.connect(self.path, timeout=5)
        self._analytics_rank_cache = {}
        try:
            version = self.db.execute('PRAGMA user_version').fetchone()[0]
            if version > 8:
                raise ValueError('このDBは新しい版のX Archive Galleryで作成されています。新しい版で開いてください。')
            if self.db.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
                raise ValueError('アプリDBの整合性を確認できません。元DBは保持しています。設定フォルダーのbackupsから復元してください。')
            if existed and version < 8:
                backups=self.directory/'backups';backups.mkdir(parents=True,exist_ok=True)
                stamp=datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S-%f')
                snapshot=sqlite3.connect(backups/f'before-schema-v{version}-to-v8-{stamp}.sqlite3')
                try:
                    self.db.backup(snapshot)
                    if snapshot.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
                        raise ValueError('更新前のアプリDBを安全に退避できませんでした。元DBは保持しています。')
                finally:snapshot.close()
            # Reopening a current database must not acquire a schema write lock.
            # Import workers open independent connections while the gallery is
            # running; migrations and snapshots remain limited to older schemas.
            if version < 8:
                self._initialize_schema()
            self.db.execute('PRAGMA journal_mode=WAL')
        except Exception:
            self.db.rollback()
            self.db.close()
            raise

    def _initialize_schema(self):
        self.db.executescript('''
            BEGIN IMMEDIATE;
            CREATE TABLE IF NOT EXISTS libraries (
                library_id TEXT PRIMARY KEY, root TEXT NOT NULL UNIQUE, added_at TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS favorites (
                library_id TEXT NOT NULL, asset_key TEXT NOT NULL, sha256 TEXT NOT NULL,
                created_at TEXT NOT NULL, PRIMARY KEY(library_id,asset_key,sha256));
            CREATE TABLE IF NOT EXISTS hidden_assets (
                library_id TEXT NOT NULL, sha256 TEXT NOT NULL, hidden_at TEXT NOT NULL,
                PRIMARY KEY(library_id,sha256));
            CREATE TABLE IF NOT EXISTS thumbnails (
                sha256 TEXT NOT NULL, version INTEGER NOT NULL, width INTEGER NOT NULL,
                height INTEGER NOT NULL, PRIMARY KEY(sha256,version));
            CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS import_jobs (
                job_id TEXT PRIMARY KEY, root TEXT NOT NULL, phase TEXT NOT NULL,
                started_at TEXT NOT NULL, updated_at TEXT NOT NULL,
                summary TEXT NOT NULL, result TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS warning_assets (
                library_id TEXT NOT NULL, asset_key TEXT NOT NULL, sha256 TEXT NOT NULL,
                post_id TEXT NOT NULL, posted_at TEXT NOT NULL, date_precision TEXT NOT NULL,
                relative_path TEXT NOT NULL, display_filename TEXT NOT NULL, kind TEXT NOT NULL,
                media_index INTEGER NOT NULL, variant INTEGER NOT NULL, size INTEGER NOT NULL,
                source_zip TEXT NOT NULL, source_member TEXT NOT NULL, added_at TEXT NOT NULL,
                PRIMARY KEY(library_id,asset_key,sha256));
            CREATE TABLE IF NOT EXISTS analytics_imports (
                import_id TEXT PRIMARY KEY, library_id TEXT NOT NULL,
                file_sha256 TEXT NOT NULL, source_filename TEXT NOT NULL,
                imported_at TEXT NOT NULL, period_start TEXT NOT NULL, period_end TEXT NOT NULL,
                post_count INTEGER NOT NULL, matched_posts INTEGER NOT NULL,
                unmatched_posts INTEGER NOT NULL, columns_json TEXT NOT NULL,
                metrics_json TEXT NOT NULL, scope TEXT NOT NULL,
                UNIQUE(library_id,file_sha256));
            CREATE INDEX IF NOT EXISTS analytics_imports_latest
                ON analytics_imports(library_id,imported_at DESC);
            CREATE TABLE IF NOT EXISTS analytics_posts (
                import_id TEXT NOT NULL, library_id TEXT NOT NULL, post_id TEXT NOT NULL,
                posted_at TEXT NOT NULL, permalink TEXT NOT NULL,
                impressions INTEGER, likes INTEGER, like_rate REAL,
                reposts INTEGER, repost_rate REAL, bookmarks INTEGER, bookmark_rate REAL,
                profile_visits INTEGER, profile_rate REAL,
                new_follows INTEGER, follows_per_1000 REAL,
                engagements INTEGER, engagement_rate REAL,
                shares INTEGER, replies INTEGER, detail_clicks INTEGER,
                url_clicks INTEGER, hashtag_clicks INTEGER, permalink_clicks INTEGER,
                extra_metrics_json TEXT NOT NULL,
                PRIMARY KEY(import_id,post_id));
            CREATE INDEX IF NOT EXISTS analytics_posts_by_post
                ON analytics_posts(library_id,post_id,import_id);
            CREATE TABLE IF NOT EXISTS analytics_asset_links (
                import_id TEXT NOT NULL, library_id TEXT NOT NULL, post_id TEXT NOT NULL,
                asset_key TEXT NOT NULL, sha256 TEXT NOT NULL,
                PRIMARY KEY(import_id,post_id,asset_key,sha256));
            CREATE INDEX IF NOT EXISTS analytics_links_by_asset
                ON analytics_asset_links(library_id,asset_key,sha256,import_id);
            CREATE TABLE IF NOT EXISTS performance_tags (
                import_id TEXT NOT NULL, library_id TEXT NOT NULL, post_id TEXT NOT NULL,
                tag_code TEXT NOT NULL, tag_name TEXT NOT NULL, metric_key TEXT NOT NULL,
                metric_value REAL NOT NULL, tag_type TEXT NOT NULL,
                threshold_value REAL NOT NULL, sample_size INTEGER NOT NULL,
                PRIMARY KEY(import_id,post_id,tag_code));
            CREATE INDEX IF NOT EXISTS performance_tags_by_post
                ON performance_tags(library_id,post_id,import_id);
            CREATE TABLE IF NOT EXISTS manual_tags (
                library_id TEXT NOT NULL, tag_id TEXT NOT NULL, name TEXT NOT NULL,
                name_key TEXT NOT NULL, PRIMARY KEY(library_id,tag_id), UNIQUE(library_id,name_key));
            CREATE TABLE IF NOT EXISTS manual_asset_tags (
                library_id TEXT NOT NULL, sha256 TEXT NOT NULL, tag_id TEXT NOT NULL,
                PRIMARY KEY(library_id,sha256,tag_id));
            CREATE TABLE IF NOT EXISTS manual_tag_colors (
                library_id TEXT NOT NULL, tag_id TEXT NOT NULL, color TEXT NOT NULL,
                PRIMARY KEY(library_id,tag_id));
            CREATE INDEX IF NOT EXISTS manual_tags_by_tag ON manual_asset_tags(library_id,tag_id);
            CREATE TABLE IF NOT EXISTS asset_views (
                library_id TEXT NOT NULL, sha256 TEXT NOT NULL, last_seen TEXT NOT NULL,
                view_count INTEGER NOT NULL, PRIMARY KEY(library_id,sha256));
            CREATE INDEX IF NOT EXISTS views_by_time ON asset_views(library_id,last_seen);
            PRAGMA user_version=8;
            COMMIT;
        ''')
        self.db.commit()

    def library(self, root):
        root = str(Path(root).resolve()).casefold()
        row = self.db.execute('SELECT library_id FROM libraries WHERE root=?', (root,)).fetchone()
        if row:
            return row[0]
        ident = uuid.uuid4().hex
        self.db.execute('INSERT INTO libraries VALUES (?,?,?)', (ident, root, self.now()))
        self.db.commit()
        return ident

    def manual_tags(self, library_id):
        return dict(self.db.execute('SELECT tag_id,name FROM manual_tags WHERE library_id=? ORDER BY name_key', (library_id,)))

    def consolidate_catalog_aliases(self, library_id, assets):
        """Keep annotations when older imports registered re-encoded attachments.

        Only the private DB changes. The original catalog and artwork files
        remain intact; a verified SQLite snapshot precedes the transaction.
        """
        pending = []
        active_hashes = {asset.sha256 for asset in assets}
        for asset in assets:
            for old_identity in asset.catalog_aliases:
                if old_identity == asset.source_identity:
                    continue
                marker = 'attachment-alias:' + library_id + ':' + hashlib.sha256(json.dumps(
                    [library_id, old_identity, asset.source_identity]).encode()).hexdigest()
                if self.get(marker) is None:
                    pending.append((asset,old_identity,marker))
        if not pending:
            return 0
        self.db.commit()
        backups = self.directory/'backups'
        backups.mkdir(parents=True,exist_ok=True)
        stamp = datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S-%f')
        snapshot = sqlite3.connect(backups/f'before-attachment-consolidation-{stamp}.sqlite3')
        try:
            self.db.backup(snapshot)
            if snapshot.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
                raise ValueError('重複作品の設定を安全に退避できませんでした。元データは保持しています。')
        finally:
            snapshot.close()
        with self.db:
            for asset,(old_key,old_sha),marker in pending:
                new_sha = asset.sha256
                self.db.execute('INSERT OR IGNORE INTO favorites '
                    'SELECT library_id,?,?,created_at FROM favorites WHERE library_id=? AND asset_key=? AND sha256=?',
                    (asset.asset_key,new_sha,library_id,old_key,old_sha))
                self.db.execute('DELETE FROM favorites WHERE library_id=? AND asset_key=? AND sha256=?',
                    (library_id,old_key,old_sha))
                if old_sha != new_sha:
                    self.db.execute('INSERT OR IGNORE INTO manual_asset_tags '
                        'SELECT library_id,?,tag_id FROM manual_asset_tags WHERE library_id=? AND sha256=?',
                        (new_sha,library_id,old_sha))
                    self.db.execute('INSERT OR IGNORE INTO hidden_assets '
                        'SELECT library_id,?,hidden_at FROM hidden_assets WHERE library_id=? AND sha256=?',
                        (new_sha,library_id,old_sha))
                    self.db.execute('''INSERT INTO asset_views
                        SELECT library_id,?,last_seen,view_count FROM asset_views WHERE library_id=? AND sha256=?
                        ON CONFLICT(library_id,sha256) DO UPDATE SET
                        last_seen=MAX(asset_views.last_seen,excluded.last_seen),
                        view_count=asset_views.view_count+excluded.view_count''', (new_sha,library_id,old_sha))
                    if old_sha not in active_hashes:
                        for table in ('manual_asset_tags','hidden_assets','asset_views'):
                            self.db.execute(f'DELETE FROM {table} WHERE library_id=? AND sha256=?',(library_id,old_sha))
                self.db.execute('INSERT INTO settings VALUES (?,?)',(marker,'true'))
        return len(pending)

    def manual_tag_colors(self, library_id):
        return dict(self.db.execute('SELECT tag_id,color FROM manual_tag_colors WHERE library_id=?', (library_id,)))

    def set_manual_tag_color(self, library_id, ident, color):
        from .tag_colors import PALETTE
        if color not in PALETTE:
            raise ValueError('一覧からタグの背景色を選んでください。')
        if ident not in self.manual_tags(library_id):
            raise ValueError('登録されていないタグです。')
        with self.db:
            self.db.execute('INSERT INTO manual_tag_colors VALUES (?,?,?) '
                'ON CONFLICT(library_id,tag_id) DO UPDATE SET color=excluded.color', (library_id,ident,color))

    def asset_views(self,library_id):
        return {sha:{'last_seen':datetime.fromisoformat(seen).timestamp(),'view_count':count}
                for sha,seen,count in self.db.execute('SELECT sha256,last_seen,view_count FROM asset_views WHERE library_id=?',(library_id,))}

    def record_asset_view(self,library_id,sha):
        stamp=self.now()
        with self.db:
            self.db.execute('''INSERT INTO asset_views VALUES (?,?,?,1)
                ON CONFLICT(library_id,sha256) DO UPDATE SET last_seen=excluded.last_seen,view_count=asset_views.view_count+1''',
                (library_id,sha,stamp))
        return datetime.fromisoformat(stamp).timestamp()

    def manual_tag_map(self, library_id):
        result = {}
        for sha, ident in self.db.execute('SELECT sha256,tag_id FROM manual_asset_tags WHERE library_id=?', (library_id,)):
            result.setdefault(sha, set()).add(ident)
        return result

    def create_manual_tag(self, library_id, name, color='teal'):
        from .manual_tags import normalize_tag
        from .tag_colors import PALETTE
        if color not in PALETTE:
            raise ValueError('一覧からタグの背景色を選んでください。')
        name = normalize_tag(name)
        ident = uuid.uuid4().hex
        with self.db:
            cursor=self.db.execute('INSERT OR IGNORE INTO manual_tags VALUES (?,?,?,?)', (library_id,ident,name,name.casefold()))
            if cursor.rowcount:
                self.db.execute('INSERT INTO manual_tag_colors VALUES (?,?,?)', (library_id,ident,color))
        return self.db.execute('SELECT tag_id FROM manual_tags WHERE library_id=? AND name_key=?', (library_id,name.casefold())).fetchone()[0]

    def rename_manual_tag(self, library_id, ident, name):
        from .manual_tags import normalize_tag
        name = normalize_tag(name)
        with self.db:
            self.db.execute('UPDATE manual_tags SET name=?,name_key=? WHERE library_id=? AND tag_id=?', (name,name.casefold(),library_id,ident))

    def set_manual_tag(self, library_id, sha, ident, enabled):
        if not self.db.execute('SELECT 1 FROM manual_tags WHERE library_id=? AND tag_id=?', (library_id,ident)).fetchone():
            raise ValueError('登録されていないタグです。')
        with self.db:
            if enabled:
                self.db.execute('INSERT OR IGNORE INTO manual_asset_tags VALUES (?,?,?)', (library_id,sha,ident))
            else:
                self.db.execute('DELETE FROM manual_asset_tags WHERE library_id=? AND sha256=? AND tag_id=?', (library_id,sha,ident))

    def delete_manual_tag(self, library_id, ident):
        with self.db:
            self.db.execute('DELETE FROM manual_asset_tags WHERE library_id=? AND tag_id=?', (library_id,ident))
            self.db.execute('DELETE FROM manual_tags WHERE library_id=? AND tag_id=?', (library_id,ident))
            self.db.execute('DELETE FROM manual_tag_colors WHERE library_id=? AND tag_id=?', (library_id,ident))

    def bulk_manual_tags(self,library_id,hashes,identifiers,enabled=True):
        hashes=set(hashes)
        identifiers=set(identifiers)
        if not identifiers <= set(self.manual_tags(library_id)):
            raise ValueError('登録されていないタグが含まれます。')
        changes=0
        with self.db:
            for sha in hashes:
                for ident in identifiers:
                    if enabled:
                        cursor=self.db.execute('INSERT OR IGNORE INTO manual_asset_tags VALUES (?,?,?)',(library_id,sha,ident))
                    else:
                        cursor=self.db.execute('DELETE FROM manual_asset_tags WHERE library_id=? AND sha256=? AND tag_id=?',(library_id,sha,ident))
                    changes+=cursor.rowcount
        return {'unique_images':len(hashes),'tag_count':len(identifiers),'changed':changes,
                'unchanged':len(hashes)*len(identifiers)-changes}

    @staticmethod
    def now():
        return datetime.now(timezone.utc).isoformat(timespec='seconds')

    def favorites(self, library_id):
        return set(self.db.execute('SELECT asset_key,sha256 FROM favorites WHERE library_id=?', (library_id,)))

    def set_favorite(self, library_id, identity, enabled):
        with self.db:
            if enabled:
                self.db.execute('INSERT OR IGNORE INTO favorites VALUES (?,?,?,?)', (library_id, *identity, self.now()))
            else:
                self.db.execute('DELETE FROM favorites WHERE library_id=? AND asset_key=? AND sha256=?', (library_id, *identity))

    def hidden_hashes(self, library_id):
        return {row[0] for row in self.db.execute(
            'SELECT sha256 FROM hidden_assets WHERE library_id=?', (library_id,))}

    def set_hidden(self, library_id, sha256, enabled):
        with self.db:
            if enabled:
                self.db.execute('INSERT OR IGNORE INTO hidden_assets VALUES (?,?,?)',
                                (library_id, sha256, self.now()))
            else:
                self.db.execute('DELETE FROM hidden_assets WHERE library_id=? AND sha256=?',
                                (library_id, sha256))

    def bulk_favorites(self, library_id, identities, enabled):
        identities=set(identities)
        with self.db:
            if enabled:
                self.db.executemany('INSERT OR IGNORE INTO favorites VALUES (?,?,?,?)',
                    [(library_id,*identity,self.now()) for identity in identities])
            else:
                self.db.executemany('DELETE FROM favorites WHERE library_id=? AND asset_key=? AND sha256=?',
                    [(library_id,*identity) for identity in identities])

    def bulk_hidden(self, library_id, hashes, enabled):
        hashes=set(hashes)
        with self.db:
            if enabled:
                self.db.executemany('INSERT OR IGNORE INTO hidden_assets VALUES (?,?,?)',
                    [(library_id,sha,self.now()) for sha in hashes])
            else:
                self.db.executemany('DELETE FROM hidden_assets WHERE library_id=? AND sha256=?',
                    [(library_id,sha) for sha in hashes])

    def dimensions(self, version=1):
        return {sha: (w, h) for sha, w, h in self.db.execute('SELECT sha256,width,height FROM thumbnails WHERE version=?', (version,))}

    def save_dimensions(self, rows, version=1):
        if rows:
            with self.db:
                self.db.executemany('''INSERT INTO thumbnails VALUES (?,?,?,?)
                    ON CONFLICT(sha256,version) DO UPDATE SET width=excluded.width,height=excluded.height
                    WHERE width<>excluded.width OR height<>excluded.height''',
                    ((sha, version, w, h) for sha, w, h in rows))

    def warning_assets(self, library_id):
        from .catalog import Asset
        rows=self.db.execute('''SELECT asset_key,sha256,post_id,posted_at,relative_path,kind,
            media_index,variant,size,date_precision,display_filename FROM warning_assets
            WHERE library_id=? ORDER BY added_at,asset_key''',(library_id,))
        return [Asset(*row[:9],0,*row[9:]) for row in rows]

    def add_warning_assets(self, library_id, issues):
        """Copy only explicitly selected warning media into X Archive Gallery's own store."""
        added=0
        archive_cache={}
        for issue in issues:
            if issue.get('level')!='注意':
                continue
            zip_path=Path(issue.get('zip_path') or '').resolve(strict=True)
            member=str(issue.get('source') or '')
            if not member or '\x00' in member:
                raise ValueError('ZIP内のファイル名がありません。')
            archive_key=str(zip_path)
            if archive_key not in archive_cache:
                zf=zipfile.ZipFile(zip_path)
                entries={}
                for entry in zf.infolist():
                    if not entry.is_dir():
                        entries.setdefault(entry.filename,[]).append(entry)
                archive_cache[archive_key]=(zf,entries)
            zf,entries=archive_cache[archive_key]
            matches=entries.get(member,[])
            if len(matches)!=1:
                raise ValueError(f'元ZIPに対象ファイルを一意に見つけられません: {member}')
            info=matches[0]
            suffix=Path(member.replace('\\','/')).suffix.lower()
            if suffix not in IMAGE_EXTENSIONS|VIDEO_EXTENSIONS:
                raise ValueError(f'画像・動画形式ではありません: {member}')
            if info.file_size>MAX_IMPORTED_MEDIA:
                raise ValueError(f'サイズが1GBを超えるため追加できません: {member}')
            reserve=64*1024*1024
            if shutil.disk_usage(self.directory).free<info.file_size+reserve:
                raise ValueError(f'X Archive Gallery側の空き容量が足りません: {member}')
            safe_name=Path(member.replace('\\','/')).name
            safe_name=re.sub(r'[<>:"/\\|?*\x00-\x1f]','_',safe_name).strip(' .')[:160] or 'unknown'+suffix
            source_tag=hashlib.sha256((str(zip_path)+'\0'+member).encode('utf-8')).hexdigest()[:32]
            relative=f'warning_media/{hashlib.sha256(member.encode("utf-8")).hexdigest()[:2]}/{source_tag}_{safe_name}'
            destination=warning_media_path(self.directory,relative)
            destination.parent.mkdir(parents=True,exist_ok=True)
            temp=destination.with_name(destination.name+'.'+uuid.uuid4().hex+'.tmp')
            digest=hashlib.sha256()
            copied=0
            try:
                with zf.open(info) as incoming,temp.open('xb') as outgoing:
                    while chunk:=incoming.read(1024*1024):
                        digest.update(chunk)
                        outgoing.write(chunk)
                        copied+=len(chunk)
                file_hash=digest.hexdigest()
                if copied!=info.file_size:
                    raise ValueError(f'ZIPから対象メディアを完全に読み出せません: {member}')
                reuse=False
                if destination.is_file() and destination.stat().st_size==copied:
                    existing=hashlib.sha256()
                    with destination.open('rb') as f:
                        while chunk:=f.read(1024*1024): existing.update(chunk)
                    reuse=existing.hexdigest()==file_hash
                if reuse:
                    temp.unlink()
                else:
                    os.replace(temp,destination)
            finally:
                temp.unlink(missing_ok=True)
            date_value=str(issue.get('date') or '').strip()
            precision='unknown'
            try:
                if re.fullmatch(r'\d{4}-\d{2}-\d{2}',date_value):
                    datetime.fromisoformat(date_value)
                    precision='day'
                elif 'T' in date_value:
                    datetime.fromisoformat(date_value.replace('Z','+00:00'))
                    precision='timestamp'
                else:
                    date_value=''
            except ValueError:
                date_value=''
            if not date_value:
                precision='unknown'
            kind='gif' if suffix=='.gif' else ('video' if suffix in VIDEO_EXTENSIONS else 'image')
            post_id=str(issue.get('post_id') or '').strip()
            identity='warning:'+source_tag
            values=(library_id,identity,file_hash,post_id,date_value,precision,relative,safe_name,kind,0,0,info.file_size,str(zip_path),member,self.now())
            with self.db:
                self.db.execute('''INSERT INTO warning_assets VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                    ON CONFLICT(library_id,asset_key,sha256) DO UPDATE SET
                    post_id=excluded.post_id,posted_at=excluded.posted_at,date_precision=excluded.date_precision,
                    relative_path=excluded.relative_path,display_filename=excluded.display_filename,
                    kind=excluded.kind,size=excluded.size,source_zip=excluded.source_zip,
                    source_member=excluded.source_member''',values)
            added+=1
        for zf,_ in archive_cache.values():
            zf.close()
        return added

    def get(self, key, default=None):
        row = self.db.execute('SELECT value FROM settings WHERE key=?', (key,)).fetchone()
        if not row:
            return default
        try:
            return json.loads(row[0])
        except ValueError:
            return default

    def set(self, key, value):
        with self.db:
            self.db.execute('INSERT OR REPLACE INTO settings VALUES (?,?)', (key, json.dumps(value, ensure_ascii=False)))

    def close(self):
        self.db.close()

    def save_import(self, job_id, root, phase, summary, result):
        with self.db:
            self.db.execute("""INSERT INTO import_jobs VALUES (?,?,?,?,?,?,?)
                ON CONFLICT(job_id) DO UPDATE SET root=excluded.root,phase=excluded.phase,
                updated_at=excluded.updated_at,summary=excluded.summary,result=excluded.result""",
                (job_id,str(root),phase,self.now(),self.now(),json.dumps(summary,ensure_ascii=False),json.dumps(result,ensure_ascii=False)))

    def clear_import_state(self, root, library_id):
        """Return this library's private state to a fresh-import baseline."""
        account_key='account:'+str(library_id)
        root=str(Path(root).resolve())
        rows=self.db.execute('SELECT job_id FROM import_jobs WHERE root=? COLLATE NOCASE',(root,)).fetchall()
        warning_paths=[row[0] for row in self.db.execute('SELECT relative_path FROM warning_assets WHERE library_id=?',(library_id,))]
        with self.db:
            self.db.execute('DELETE FROM settings WHERE key=?',(account_key,))
            self.db.execute('DELETE FROM settings WHERE key=?',('library_account:'+str(library_id),))
            if self.get('last_backup_library')==library_id:
                self.db.execute('DELETE FROM settings WHERE key=?',('last_backup_library',))
            self.db.execute('DELETE FROM settings WHERE key=?',('frequent_tags:'+str(library_id),))
            self.db.execute('DELETE FROM settings WHERE key LIKE ?',('attachment-alias:'+str(library_id)+':%',))
            self.db.execute('DELETE FROM import_jobs WHERE root=? COLLATE NOCASE',(root,))
            self.db.execute('DELETE FROM warning_assets WHERE library_id=?',(library_id,))
            self.db.execute('DELETE FROM favorites WHERE library_id=?',(library_id,))
            self.db.execute('DELETE FROM hidden_assets WHERE library_id=?',(library_id,))
            self.db.execute('DELETE FROM manual_asset_tags WHERE library_id=?',(library_id,))
            self.db.execute('DELETE FROM manual_tags WHERE library_id=?',(library_id,))
            self.db.execute('DELETE FROM manual_tag_colors WHERE library_id=?',(library_id,))
            self.db.execute('DELETE FROM asset_views WHERE library_id=?',(library_id,))
        imports=(self.directory/'imports').resolve()
        for (job_id,) in rows:
            if not job_id or Path(job_id).name!=job_id:
                continue
            job=(imports/job_id).resolve()
            if job.is_relative_to(imports) and job.is_dir():
                shutil.rmtree(job)
        for relative in warning_paths:
            still_used=self.db.execute('SELECT 1 FROM warning_assets WHERE relative_path=? LIMIT 1',(relative,)).fetchone()
            if still_used:
                continue
            path=warning_media_path(self.directory,relative)
            path.unlink(missing_ok=True)

    def analytics_hash_imported(self, library_id, file_sha256):
        return self.db.execute('''SELECT 1 FROM analytics_imports
            WHERE library_id=? AND file_sha256=? LIMIT 1''',(library_id,file_sha256)).fetchone() is not None

    def analytics_summary(self, library_id):
        query=self.db.execute('''SELECT import_id,source_filename,imported_at,period_start,period_end,
            post_count,matched_posts,unmatched_posts,scope FROM analytics_imports
            WHERE library_id=? ORDER BY imported_at DESC,rowid DESC LIMIT 1''',(library_id,)).fetchone()
        if not query:
            return None
        result=dict(zip(('import_id','source_filename','imported_at','period_start','period_end',
                        'post_count','matched_posts','unmatched_posts','scope'),query))
        cohort=self._current_analytics_ranking(library_id)
        result['cumulative_post_count']=len(cohort['posts'])
        dates=[r['posted_at'] for r in cohort['posts'].values() if r['posted_at']]
        result['cumulative_period_start']=min(dates,default='')
        result['cumulative_period_end']=max(dates,default='')
        result['ranking_scope']='latest_saved_posts'
        return result

    def _current_analytics_ranking(self, library_id):
        """Rank one library's accumulated posts using one latest snapshot per ID.

        Historical CSV rows and their original tags remain untouched. The current
        view is derived from persisted metrics, so existing v8 databases need no
        migration or reimport. Cache invalidation covers this connection's writes
        and committed imports/reconciliation/reset from other connections.
        """
        from .analytics import performance_tags
        epoch=(self.db.execute('PRAGMA data_version').fetchone()[0],self.db.total_changes)
        cached=self._analytics_rank_cache.get(library_id)
        if cached and cached[0]==epoch:
            return cached[1]
        query=self.db.execute('''WITH ranked_posts AS (
                SELECT p.*,i.imported_at,i.period_start,i.period_end,i.source_filename,
                       ROW_NUMBER() OVER (
                           PARTITION BY p.post_id
                           ORDER BY i.imported_at DESC,i.rowid DESC
                       ) AS snapshot_rank
                FROM analytics_posts p JOIN analytics_imports i USING(import_id,library_id)
                WHERE p.library_id=?
            ) SELECT * FROM ranked_posts WHERE snapshot_rank=1''',(library_id,))
        names=[c[0] for c in query.description]
        posts={}
        for values in query:
            record=dict(zip(names,values));record.pop('snapshot_rank')
            posts[record['post_id']]=record
        tags=performance_tags(list(posts.values()))
        records={}
        for post_id,items in tags.items():
            items.sort(key=lambda t:(t['tag_type']!='top1',t['metric_key']))
            records[post_id]={'tags':[t['tag_name'] for t in items],
                'tag_badges':[{'tag_name':t['tag_name'],'tag_type':t['tag_type']} for t in items],
                'high_count':sum(t['tag_type']=='high' for t in items),
                'top1_count':sum(t['tag_type']=='top1' for t in items)}
        result={'posts':posts,'tags':tags,'records':records}
        self._analytics_rank_cache[library_id]=(epoch,result)
        return result

    def analytics_performance(self, library_id, post_id):
        if not post_id:
            return None
        cohort=self._current_analytics_ranking(library_id)
        row=cohort['posts'].get(str(post_id))
        if not row:
            return None
        result=dict(row)
        result['tags']=list(cohort['records'][str(post_id)]['tags'])
        result['ranking_post_count']=len(cohort['posts'])
        result['ranking_scope']='latest_saved_posts'
        result['matched_assets']=self.db.execute('''SELECT count(*) FROM analytics_asset_links
            WHERE import_id=? AND library_id=? AND post_id=?''',
            (result['import_id'],library_id,str(post_id))).fetchone()[0]
        return result

    def analytics_performance_map(self, library_id):
        """Use the same cumulative ranking for tiles, details, filters and discovery."""
        if not library_id:
            return {}
        # Return separate containers: callers must not mutate cached tags.
        return {pid:{**record,'tags':list(record['tags']),
                'tag_badges':[dict(badge) for badge in record['tag_badges']]}
                for pid,record in self._current_analytics_ranking(library_id)['records'].items()}

    def import_analytics(self, library_id, preview, assets):
        """Persist one CSV snapshot and post-level links without touching the catalog."""
        if not preview.can_import:
            raise ValueError('このCSVは重複済み、投稿ID重複、または入力不備のため取り込めません。')
        if self.analytics_hash_imported(library_id,preview.file_sha256):
            raise ValueError('同じ内容のCSVはすでに取り込み済みです。')
        from .analytics import POST_METRICS, RATE_METRICS, performance_tags
        import_id=uuid.uuid4().hex
        asset_ids={}
        for asset in assets:
            post_id=str(getattr(asset,'post_id','') or '').strip()
            if post_id:
                asset_ids.setdefault(post_id,[]).append(asset)
        metric_names={
            'impressions':'インプレッション','likes':'いいね','engagements':'エンゲージメント',
            'bookmarks':'保存','shares':'共有','new_follows':'新しいフォロー','replies':'返信',
            'reposts':'リポスト','profile_visits':'プロフィールへのアクセス',
            'detail_clicks':'詳細クリック','url_clicks':'URLクリック',
            'hashtag_clicks':'ハッシュタグクリック','permalink_clicks':'パーマリンククリック',
        }
        metric_names.update({key:key for key in RATE_METRICS})
        tag_map=performance_tags(preview.rows)
        post_ids={row['post_id'] for row in preview.rows}
        matched_posts=len(post_ids & asset_ids.keys())
        with self.db:
            self.db.execute('''INSERT INTO analytics_imports VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)''',(
                import_id,library_id,preview.file_sha256,preview.path.name,self.now(),
                preview.period_start,preview.period_end,len(preview.rows),matched_posts,
                len(post_ids)-matched_posts,json.dumps(preview.columns,ensure_ascii=False),
                json.dumps([metric_names[m] for m in POST_METRICS if m in preview.field_columns]
                           +[metric_names[m] for m in RATE_METRICS if m in preview.field_columns],ensure_ascii=False),
                preview.scope))
            for row in preview.rows:
                self.db.execute('''INSERT INTO analytics_posts (
                    import_id,library_id,post_id,posted_at,permalink,impressions,likes,like_rate,
                    reposts,repost_rate,bookmarks,bookmark_rate,profile_visits,profile_rate,
                    new_follows,follows_per_1000,engagements,engagement_rate,shares,replies,
                    detail_clicks,url_clicks,hashtag_clicks,permalink_clicks,extra_metrics_json)
                    VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)''',(
                    import_id,library_id,row['post_id'],row['posted_at'],row['permalink'],
                    row['impressions'],row['likes'],row['like_rate'],row['reposts'],row['repost_rate'],
                    row['bookmarks'],row['bookmark_rate'],row['profile_visits'],row['profile_rate'],
                    row['new_follows'],row['follows_per_1000'],row['engagements'],row['engagement_rate'],
                    row['shares'],row['replies'],row['detail_clicks'],row['url_clicks'],
                    row['hashtag_clicks'],row['permalink_clicks'],row['extra_metrics_json']))
                for asset in asset_ids.get(row['post_id'],[]):
                    self.db.execute('INSERT OR IGNORE INTO analytics_asset_links VALUES (?,?,?,?,?)',(
                        import_id,library_id,row['post_id'],asset.asset_key,asset.sha256))
                for tag in tag_map[row['post_id']]:
                    self.db.execute('''INSERT INTO performance_tags VALUES (?,?,?,?,?,?,?,?,?,?)''',(
                        import_id,library_id,row['post_id'],tag['tag_code'],tag['tag_name'],
                        tag['metric_key'],tag['metric_value'],tag['tag_type'],tag['threshold_value'],
                        tag['sample_size']))
        return self.analytics_summary(library_id)

    def reconcile_analytics(self, library_id, assets):
        """Rebuild links from the current read-only catalog plus selected warning media."""
        imports=[r[0] for r in self.db.execute('SELECT import_id FROM analytics_imports WHERE library_id=?',(library_id,))]
        if not imports:
            return 0
        asset_ids={}
        for asset in assets:
            post_id=str(getattr(asset,'post_id','') or '').strip()
            if post_id:
                asset_ids.setdefault(post_id,[]).append(asset)
        # Read-only fast path: a normal refresh must not rewrite identical links.
        # Changed libraries still use the existing reconciliation below.
        posts=list(self.db.execute('SELECT import_id,post_id FROM analytics_posts WHERE library_id=?',
                                   (library_id,)))
        desired={(import_id,post_id,a.asset_key,a.sha256)
                 for import_id,post_id in posts for a in asset_ids.get(post_id,[])}
        existing=set(self.db.execute('''SELECT import_id,post_id,asset_key,sha256
            FROM analytics_asset_links WHERE library_id=?''',(library_id,)))
        expected={import_id:[0,0] for import_id in imports}
        for import_id,post_id in posts:
            expected[import_id][0 if post_id in asset_ids else 1]+=1
        counts={r[0]:[r[1],r[2]] for r in self.db.execute('''SELECT import_id,matched_posts,unmatched_posts
            FROM analytics_imports WHERE library_id=?''',(library_id,))}
        if desired==existing and counts==expected:
            return len({post_id for _,post_id in posts} & asset_ids.keys())
        with self.db:
            self.db.execute('DELETE FROM analytics_asset_links WHERE library_id=?',(library_id,))
            for import_id in imports:
                rows=self.db.execute('SELECT post_id FROM analytics_posts WHERE import_id=? AND library_id=?',
                                     (import_id,library_id)).fetchall()
                matched=set()
                for (post_id,) in rows:
                    for asset in asset_ids.get(post_id,[]):
                        self.db.execute('INSERT OR IGNORE INTO analytics_asset_links VALUES (?,?,?,?,?)',
                                        (import_id,library_id,post_id,asset.asset_key,asset.sha256))
                        matched.add(post_id)
                self.db.execute('UPDATE analytics_imports SET matched_posts=?,unmatched_posts=? WHERE import_id=? AND library_id=?',
                                (len(matched),len(rows)-len(matched),import_id,library_id))
        known_posts={r[0] for r in self.db.execute(
            'SELECT DISTINCT post_id FROM analytics_posts WHERE library_id=?',(library_id,))}
        return len(known_posts & asset_ids.keys())

    def clear_thumbnail_dimensions(self):
        """Remove only derived image-size metadata; user annotations stay intact."""
        with self.db:
            self.db.execute('DELETE FROM thumbnails')

    def recover_imports(self):
        rows=list(self.db.execute("SELECT job_id,root,summary FROM import_jobs WHERE phase IN ('analyzing','importing')"))
        for job_id,root,summary in rows:
            phase='interrupted'
            result={}
            try:
                result=json.loads((self.directory/'imports'/job_id/'result.json').read_text(encoding='utf-8'))
                if result.get('action')=='backup' and result.get('run_id')==job_id and result.get('ok'):
                    phase=result['status']
            except (OSError,ValueError,KeyError):
                pass
            self.save_import(job_id,root,phase,json.loads(summary),result)
        return len(rows)
