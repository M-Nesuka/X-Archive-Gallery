"""The only interface to the backup catalog. Never opens a writable connection."""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from functools import cached_property
from datetime import datetime, timezone, timedelta
from pathlib import Path
import sqlite3
from backup_engine.identity import attachment_identity

JST = timezone(timedelta(hours=9))
DEFAULT_ROOT = Path.home() / 'Pictures' / 'X Archive Gallery Library'
UNKNOWN_YEAR = '__unknown__'


@dataclass(frozen=True)
class Asset:
    asset_key: str
    sha256: str
    post_id: str
    posted_at: str
    relative_path: str
    kind: str
    media_index: int
    variant: int
    size: int
    total: int = 1
    date_precision: str = 'timestamp'
    display_filename: str = ''
    library_id: str = ''
    library_root: str = ''
    account_name: str = ''
    catalog_aliases: tuple = ()

    @property
    def identity(self):
        return ((self.library_id+'|'+self.asset_key) if self.library_id else self.asset_key, self.sha256)

    @property
    def source_identity(self):
        return self.asset_key, self.sha256

    @property
    def annotation_key(self):
        return (self.library_id+'|'+self.sha256) if self.library_id else self.sha256

    @property
    def performance_key(self):
        return (self.library_id+'|'+self.post_id) if self.library_id else self.post_id

    @cached_property
    def filename(self):
        return self.display_filename or Path(self.relative_path).name

    @cached_property
    def date(self):
        try:
            dt = datetime.fromisoformat(self.posted_at.replace('Z', '+00:00'))
            return (dt if dt.tzinfo else dt.replace(tzinfo=JST)).astimezone(JST)
        except (ValueError, TypeError):
            return None

    @property
    def day(self):
        return self.date.strftime('%Y.%m.%d') if self.has_known_date else '不明'

    @property
    def has_known_date(self):
        return self.date is not None and self.date_precision != 'unknown'

    @property
    def year(self):
        return str(self.date.year) if self.has_known_date else ''

    @property
    def month(self):
        return str(self.date.month) if self.has_known_date else ''


def source_path(root: Path, relative: str) -> Path:
    """Reject paths escaping the selected library, including junction targets."""
    root = Path(root).resolve()
    rel = Path(relative)
    if rel.is_absolute() or '..' in rel.parts or ':' in relative or relative.startswith(('\\', '/')):
        raise ValueError('管理情報の保存先がライブラリ外を指しています。')
    path = (root / rel).resolve()
    if path == root or not path.is_relative_to(root):
        raise ValueError('ライブラリ外のファイルは開けません。')
    return path


def read_catalog(root: Path) -> list[Asset]:
    path = source_path(root, '.system/catalog.sqlite3')
    if not path.is_file():
        raise FileNotFoundError('このフォルダーに .system/catalog.sqlite3 がありません。X作品バックアップのフォルダーを選択してください。')
    # Backup currently uses DELETE journaling. Never create a shared-memory file
    # for a foreign WAL-mode database in the protected library.
    if Path(str(path) + '-wal').exists():
        raise RuntimeError('カタログが更新中です。バックアップを終了してから更新してください。')
    db = sqlite3.connect(path.as_uri() + '?mode=ro', uri=True, timeout=3)
    try:
        db.execute('PRAGMA query_only=ON')
        columns = {row[1] for row in db.execute('PRAGMA table_info(assets)')}
        required = set(Asset.__dataclass_fields__) - {'total','date_precision','display_filename','library_id','library_root','account_name','catalog_aliases'}
        if not required.issubset(columns):
            raise ValueError('カタログの形式が対応していません。元のバックアップソフトのカタログを選択してください。')
        db.row_factory = sqlite3.Row
        rows = list(db.execute('SELECT asset_key,sha256,post_id,posted_at,relative_path,kind,media_index,variant,size FROM assets ORDER BY posted_at DESC,post_id DESC,media_index,variant'))
        aliases = {}
        if {'source','saved_at'}.issubset(columns):
            canonical = {}
            for row in db.execute('SELECT asset_key,sha256,post_id,media_index,kind,source,relative_path '
                                  'FROM assets ORDER BY saved_at,relative_path'):
                key = attachment_identity(row['post_id'],row['media_index'],row['kind'],row['source'])
                if not key[-1]:
                    continue
                identity = row['asset_key'], row['sha256']
                if key not in canonical:
                    canonical[key] = (identity, source_path(root,row['relative_path']).is_file())
                else:
                    previous, valid = canonical[key]
                    if not valid and source_path(root,row['relative_path']).is_file():
                        aliases.setdefault(identity, []).extend([previous,*aliases.pop(previous,[])])
                        canonical[key] = (identity, True)
                    else:
                        aliases.setdefault(previous, []).append(identity)
            excluded = {identity for values in aliases.values() for identity in values}
            rows = [row for row in rows if (row['asset_key'],row['sha256']) not in excluded]
    finally:
        db.close()
    counts = defaultdict(set)
    for row in rows:
        counts[row['post_id']].add(row['media_index'])
    result = []
    for row in rows:
        values = dict(row)
        source_path(root, values['relative_path'])
        if len(values['sha256']) != 64 or any(c not in '0123456789abcdef' for c in values['sha256']):
            raise ValueError('カタログのSHA-256が不正です。')
        result.append(Asset(**values, total=max(counts[row['post_id']], default=1),
                            catalog_aliases=tuple(aliases.get((row['asset_key'],row['sha256']),()))))
    return result


def filter_assets(assets, year='', month='', query='', favorites=None, kind=''):
    query = query.strip().casefold()
    return [a for a in assets if (not year or
                                  (not a.has_known_date if year == UNKNOWN_YEAR else a.year == year))
            and (not month or a.month == month)
            and (not kind or a.kind == kind)
            and (not query or query in (a.post_id + ' ' + a.filename).casefold())
            and (favorites is None or a.identity in favorites)]
