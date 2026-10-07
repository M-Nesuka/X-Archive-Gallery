"""Append-only artwork store. No source modification and no artwork deletion."""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import sqlite3
import time
import uuid
import zipfile
from contextlib import contextmanager
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path

from PIL import Image

from .archive import Asset, Cancelled, IMAGES, Issue, JST, Plan, check_cancel, fingerprint
from .identity import attachment_identity

FOLDER = 'X作品バックアップ'
CHUNK = 1024 * 1024


def now():
    return datetime.now(JST).isoformat(timespec='seconds')


def reject_links(path):
    path = Path(path).absolute()
    for part in (path, *path.parents):
        if part.is_symlink() or (hasattr(part, 'is_junction') and part.is_junction()):
            raise ValueError(f'リンク経由の保存先は使えません。実際のフォルダを選んでください: {part}')
    return path


def backup_root(destination, create=False):
    if not destination:
        raise ValueError('先に保存先フォルダを選択してください')
    base = reject_links(destination)
    if not base.is_dir():
        raise ValueError('前回の保存先が見つかりません。保存先を選び直してください')
    root = reject_links(base / FOLDER)
    if create:
        root.mkdir(exist_ok=True)
    return root


def safe_path(root, relative):
    root = Path(root).absolute()
    if Path(relative).is_absolute() or '..' in Path(relative).parts or ':' in str(relative):
        raise ValueError('保存先の管理情報に不正なパスがあります')
    path = reject_links(root / relative)
    if not path.is_relative_to(root) or path == root:
        raise ValueError('保存先の管理情報に不正なパスがあります')
    return path


def capacity(destination, required):
    backup_root(destination)
    free = shutil.disk_usage(destination).free
    reserve = max(64 * 1024**2, int(required * 0.02))
    return free, required + reserve, free < required + reserve


def digest(path, cancel=None, tick=lambda n: None):
    h = hashlib.sha256()
    done = 0
    with open(path, 'rb') as file:
        while chunk := file.read(CHUNK):
            check_cancel(cancel)
            h.update(chunk)
            done += len(chunk)
            tick(done)
    return h.hexdigest()


@contextmanager
def store_lock(system):
    """An OS lock is released even if the process crashes; no stale lock cleanup."""
    lock_path = reject_links(system / 'backup.lock')
    file = open(lock_path, 'a+b')
    locked = False
    try:
        file.seek(0, 2)
        if not file.tell():
            file.write(b'0')
            file.flush()
        file.seek(0)
        try:
            if os.name == 'nt':
                import msvcrt
                msvcrt.locking(file.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            locked = True
        except OSError as exc:
            raise ValueError('この保存先は別のバックアップ処理で使用中です') from exc
        yield
    finally:
        if locked:
            file.seek(0)
            if os.name == 'nt':
                import msvcrt
                msvcrt.locking(file.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl
                fcntl.flock(file.fileno(), fcntl.LOCK_UN)
        file.close()


def database(system):
    path = reject_links(system / 'catalog.sqlite3')
    for suffix in ('-journal', '-wal', '-shm'):
        reject_links(Path(str(path) + suffix))
    db = sqlite3.connect(path)
    db.row_factory = sqlite3.Row
    db.execute('PRAGMA synchronous=FULL')
    db.executescript('''
        CREATE TABLE IF NOT EXISTS assets(
            asset_key TEXT NOT NULL, sha256 TEXT NOT NULL, post_id TEXT NOT NULL,
            posted_at TEXT NOT NULL, source TEXT NOT NULL, relative_path TEXT NOT NULL,
            kind TEXT NOT NULL, media_index INTEGER NOT NULL, variant INTEGER NOT NULL,
            size INTEGER NOT NULL, saved_at TEXT NOT NULL,
            PRIMARY KEY(asset_key, sha256));
        CREATE TABLE IF NOT EXISTS runs(
            id TEXT PRIMARY KEY, started_at TEXT NOT NULL, finished_at TEXT,
            zip_path TEXT NOT NULL, status TEXT NOT NULL, result TEXT);
        CREATE INDEX IF NOT EXISTS assets_by_attachment ON assets(post_id,media_index,kind);
        CREATE INDEX IF NOT EXISTS assets_by_content ON assets(sha256,kind,size);
        CREATE TABLE IF NOT EXISTS issues(
            id INTEGER PRIMARY KEY, zip_path TEXT NOT NULL, run_id TEXT NOT NULL,
            level TEXT NOT NULL, post_id TEXT, date TEXT, source TEXT, reason TEXT,
            active INTEGER NOT NULL DEFAULT 1);
    ''')
    db.commit()
    return db


@dataclass
class Result:
    mode: str
    destination: str
    images: int = 0
    gifs: int = 0
    videos: int = 0
    skipped: int = 0
    checked: int = 0
    total: int = 0
    posts: int = 0
    media_posts: int = 0
    excluded_dm: int = 0
    excluded_other: int = 0
    unresolved: int = 0
    cancelled: bool = False
    issues: list[Issue] = field(default_factory=list)

    @property
    def errors(self):
        return sum(i.level == 'エラー' for i in self.issues)

    @property
    def warnings(self):
        return sum(i.level == '注意' for i in self.issues)


def add_issue(db, zip_path, run_id, issue):
    db.execute('INSERT INTO issues(zip_path,run_id,level,post_id,date,source,reason) VALUES(?,?,?,?,?,?,?)',
               (zip_path, run_id, issue.level, issue.post_id, issue.date, issue.source, issue.reason))
    db.commit()


def publish_no_replace(temp, target):
    if os.name == 'nt':
        os.rename(temp, target)  # Windows rename fails if target exists.
    else:
        os.link(temp, target)
        os.unlink(temp)


def save_asset(zf, info, asset, root, system, db, cancel, progress):
    # A full X export can resize/re-encode an existing attachment (e.g. 1199
    # to 1200 pixels). Its post/position/media filename is the import identity;
    # SHA-256 still verifies the saved file, not whether the post is new.
    identity = attachment_identity(asset.post_id, asset.index, asset.kind, asset.source)
    for row in db.execute('SELECT * FROM assets WHERE post_id=? AND media_index=? AND kind=? '
                          'ORDER BY saved_at,relative_path', identity[:3]):
        check_cancel(cancel)
        if attachment_identity(row['post_id'], row['media_index'], row['kind'], row['source']) != identity:
            continue
        known = safe_path(root, row['relative_path'])
        if known.is_file() and known.stat().st_size == row['size'] and digest(known, cancel) == row['sha256']:
            progress(info.file_size, '保存済み作品を確認中')
            return True, known, row['sha256']
    # Existing records can be checked without writing every ZIP member to disk.
    # CRC/size alone are not proof of identity: compare SHA-256 on both sides.
    candidates=db.execute('SELECT sha256,relative_path,size FROM assets WHERE asset_key=? AND size=?',
                          (asset.key,info.file_size)).fetchall()
    candidates=[row for row in candidates if safe_path(root,row['relative_path']).is_file()]
    if candidates:
        incoming=hashlib.sha256()
        incoming_size=0
        with zf.open(info,'r') as source:
            while chunk:=source.read(CHUNK):
                check_cancel(cancel)
                incoming.update(chunk)
                incoming_size+=len(chunk)
                progress(incoming_size,'既存作品を照合中')
        if incoming_size!=info.file_size or not incoming_size:
            raise ValueError('ZIP内のサイズが一致しません')
        checksum=incoming.hexdigest()
        for row in candidates:
            check_cancel(cancel)
            known=safe_path(root,row['relative_path'])
            if row['sha256']==checksum and known.stat().st_size==incoming_size and digest(known,cancel)==checksum:
                return True,known,checksum
    target = safe_path(root, asset.relative_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    temp = safe_path(system, f'{uuid.uuid4().hex}.part')
    h = hashlib.sha256()
    copied = 0
    # Only our private unfinished temp file may be removed. Never remove artworks.
    try:
        with zf.open(info, 'r') as source, open(temp, 'xb') as output:
            while chunk := source.read(CHUNK):
                check_cancel(cancel)
                output.write(chunk)
                h.update(chunk)
                copied += len(chunk)
                progress(copied, 'コピー中')
            output.flush()
            os.fsync(output.fileno())
        if copied != info.file_size or copied == 0:
            raise ValueError('ファイルが0バイト、またはコピーしたサイズが一致しません')
        checksum = h.hexdigest()
        if digest(temp, cancel, lambda n: progress(n, '書き込み検証中')) != checksum:
            raise ValueError('書き込み後のSHA-256が一致しません')
        existing = db.execute('SELECT relative_path FROM assets WHERE asset_key=? AND sha256=?', (asset.key, checksum)).fetchone()
        if existing:
            known = safe_path(root, existing['relative_path'])
            if known.is_file() and known.stat().st_size == copied and digest(known, cancel) == checksum:
                return True, known, checksum
        # Reposting exactly the same bytes keeps the new post's metadata but
        # reuses the verified backup file instead of storing a second copy.
        for row in db.execute('SELECT relative_path FROM assets WHERE sha256=? AND kind=? AND size=?',
                              (checksum,asset.kind,copied)):
            check_cancel(cancel)
            known = safe_path(root,row['relative_path'])
            if known.is_file() and known.stat().st_size == copied and digest(known,cancel) == checksum:
                return True,known,checksum
        stem, suffix = target.stem, target.suffix
        number = 0
        while True:
            check_cancel(cancel)
            if target.exists():
                if target.is_file() and target.stat().st_size == copied and digest(target, cancel) == checksum:
                    return True, target, checksum
                number += 1
                marker = f'_{checksum[:12]}' + (f'_{number}' if number > 1 else '')
                target = safe_path(root, Path(asset.relative_path).with_name(stem + marker + suffix))
                continue
            try:
                publish_no_replace(temp, target)
                return False, target, checksum
            except FileExistsError:
                continue
    finally:
        if temp.exists():
            try:
                temp.unlink()
            except OSError:
                pass  # Inspection reports an unfinished file if the drive disappeared.


def run_backup(plan: Plan, destination, progress=lambda *x: None, cancel=None, *, root_override=None, run_id=None):
    if fingerprint(plan.zip_path) != plan.fingerprint:
        raise ValueError('解析後にZIPが変更されました。ZIPを選び直してください。')
    root = backup_root(destination, create=True) if root_override is None else reject_links(root_override)
    if not root.is_dir():
        raise ValueError("保存先が見つかりません")
    system = safe_path(root, '.system')
    system.mkdir(exist_ok=True)
    result = Result('backup', str(root), total=len(plan.assets), posts=plan.posts, media_posts=plan.media_posts,
                    excluded_dm=plan.excluded_dm, excluded_other=plan.excluded_other, unresolved=plan.unresolved, issues=list(plan.issues))
    run_id = run_id or uuid.uuid4().hex
    with store_lock(system):
        db = database(system)
        try:
            db.execute('UPDATE issues SET active=0 WHERE zip_path=?', (plan.zip_path,))
            db.execute('INSERT INTO runs VALUES(?,?,NULL,?,?,NULL)', (run_id, now(), plan.zip_path, 'running'))
            for issue in plan.issues:
                add_issue(db, plan.zip_path, run_id, issue)
            db.commit()
            with zipfile.ZipFile(plan.zip_path, 'r', allowZip64=True) as zf:
                offsets = {f.header_offset: f for f in zf.infolist()}
                for n, asset in enumerate(plan.assets):
                    check_cancel(cancel)
                    try:
                        info = offsets.get(asset.offset)
                        if not info or (info.filename, info.CRC, info.file_size) != (asset.source, asset.crc, asset.size):
                            raise ValueError('ZIPの目次が解析時から変化しています')
                        last_tick = [0.0]

                        def tick(done, phase):
                            current = time.monotonic()
                            if current - last_tick[0] >= 0.12 or done == asset.size:
                                last_tick[0] = current
                                progress(f'{phase} {n + 1:,}/{len(plan.assets):,}件：{done / 1024**2:.1f} / {asset.size / 1024**2:.1f} MB', n, len(plan.assets))

                        skipped, target, checksum = save_asset(zf, info, asset, root, system, db, cancel, tick)
                        # A skipped attachment keeps its original record and
                        # annotation identity, even if X renumbered variants.
                        registered = db.execute('SELECT 1 FROM assets WHERE post_id=? AND media_index=? '
                            'AND kind=? AND relative_path=? AND sha256=?',
                            (asset.post_id, asset.index, asset.kind, target.relative_to(root).as_posix(), checksum)).fetchone()
                        if not skipped or not registered:
                            db.execute('''INSERT INTO assets VALUES(?,?,?,?,?,?,?,?,?,?,?)
                            ON CONFLICT(asset_key,sha256) DO UPDATE SET relative_path=excluded.relative_path, source=excluded.source, saved_at=excluded.saved_at''',
                            (asset.key, checksum, asset.post_id, asset.posted_at, asset.source,
                             target.relative_to(root).as_posix(), asset.kind, asset.index, asset.variant, asset.size, now()))
                        db.commit()
                        if skipped:
                            result.skipped += 1
                        elif asset.kind == 'image':
                            result.images += 1
                        elif asset.kind == 'gif':
                            result.gifs += 1
                        else:
                            result.videos += 1
                    except Cancelled:
                        raise
                    except Exception as exc:
                        issue = Issue('エラー', asset.post_id, asset.date, asset.source, str(exc))
                        result.issues.append(issue)
                        add_issue(db, plan.zip_path, run_id, issue)
                        # On a missing/full/read-only destination, stop safely rather than repeat IO failures.
                        if not root.is_dir() or (isinstance(exc, OSError) and exc.errno in {13, 28, 30}):
                            raise ValueError('保存先へ書き込めないため処理を停止しました。未処理分は再実行してください。') from exc
                    result.checked += 1
                    progress(f'処理済み {result.checked:,} / {result.total:,}件', result.checked, result.total)
        except Cancelled:
            result.cancelled = True
            issue = Issue('注意', '', '', plan.zip_path, f'中止しました。{result.total - result.checked:,}件が未処理です。再実行してください。')
            result.issues.append(issue)
            add_issue(db, plan.zip_path, run_id, issue)
        except Exception as exc:
            issue = Issue('エラー', '', '', plan.zip_path, f'処理停止: {exc}')
            result.issues.append(issue)
            try:
                add_issue(db, plan.zip_path, run_id, issue)
            except sqlite3.Error:
                pass
        finally:
            status = 'cancelled' if result.cancelled else ('errors' if result.errors else ('warnings' if result.warnings else 'complete'))
            try:
                if status in {'complete', 'warnings'}:
                    db.execute("UPDATE runs SET status='recovered' WHERE zip_path=? AND status='running' AND id<>?", (plan.zip_path, run_id))
                db.execute('UPDATE runs SET finished_at=?, status=?, result=? WHERE id=?', (now(), status, json.dumps(asdict(result), ensure_ascii=False), run_id))
                db.commit()
            finally:
                db.close()
    return result


def inspect_backup(destination, progress=lambda *x: None, cancel=None):
    root = backup_root(destination)
    system = safe_path(root, '.system')
    catalog = safe_path(system, 'catalog.sqlite3')
    if not catalog.is_file():
        raise ValueError('この保存先にバックアップの管理情報がありません。先にバックアップしてください。')
    result = Result('inspect', str(root))
    with store_lock(system):
        db = sqlite3.connect(catalog.as_uri() + '?mode=ro', uri=True)
        db.row_factory = sqlite3.Row
        registered = set()
        try:
            if db.execute('PRAGMA quick_check').fetchone()[0] != 'ok':
                raise ValueError('管理データベースの整合性エラーです')
            result.total = db.execute('SELECT COUNT(*) FROM assets').fetchone()[0]
            for row in db.execute('SELECT * FROM assets ORDER BY posted_at,post_id,media_index,variant'):
                check_cancel(cancel)
                try:
                    path = safe_path(root, row['relative_path'])
                    registered.add(path)
                    if not path.is_file():
                        raise ValueError('作品ファイルがありません')
                    if path.stat().st_size == 0:
                        raise ValueError('作品ファイルが0バイトです')
                    if path.stat().st_size != row['size']:
                        raise ValueError('作品ファイルのサイズが保存時と違います')
                    if digest(path, cancel, lambda n: progress(f'検査中 {result.checked + 1:,}/{result.total:,}件：{n / 1024**2:.1f} MB', result.checked, result.total)) != row['sha256']:
                        raise ValueError('SHA-256が保存時と違います（ファイル変更・破損の可能性）')
                    if path.suffix.lower() in IMAGES:
                        # Decode all frames; never re-save or transcode the artwork.
                        with Image.open(path) as image:
                            image.verify()
                        with Image.open(path) as image:
                            for frame in range(getattr(image, 'n_frames', 1)):
                                check_cancel(cancel)
                                image.seek(frame)
                                image.load()
                    # Videos: existence, nonzero size and byte integrity. Playback is not claimed.
                except Cancelled:
                    raise
                except Exception as exc:
                    result.issues.append(Issue('エラー', row['post_id'], row['posted_at'][:10], row['relative_path'], str(exc)))
                result.checked += 1
                progress(f'検査済み {result.checked:,} / {result.total:,}件', result.checked, result.total)
            for row in db.execute('SELECT * FROM issues WHERE active=1'):
                result.issues.append(Issue(row['level'], row['post_id'], row['date'], row['source'], row['reason']))
            for row in db.execute("SELECT * FROM runs WHERE status='running'"):
                result.issues.append(Issue('注意', '', '', row['zip_path'], '完了記録のない処理があります。元ZIPで再実行してください。'))
            for folder, dirs, files in os.walk(root, followlinks=False):
                check_cancel(cancel)
                dirs[:] = [d for d in dirs if not (Path(folder) / d).is_symlink() and not (hasattr(Path(folder) / d, 'is_junction') and (Path(folder) / d).is_junction())]
                for name in files:
                    path = Path(folder) / name
                    if path.suffix == '.part':
                        result.issues.append(Issue('注意', '', '', str(path.relative_to(root)), '保存途中のファイルがあります。元ZIPで再実行してください。'))
                    elif '.system' not in path.relative_to(root).parts and path.suffix.lower() in IMAGES | {'.mp4', '.mov', '.webm', '.m4v', '.mkv', '.avi', '.mpeg', '.mpg', '.3gp', '.ts'} and path not in registered:
                        result.issues.append(Issue('注意', '', '', str(path.relative_to(root)), '管理DBに未登録の作品があります。削除せず残しています。'))
            if result.total == 0:
                result.issues.append(Issue('注意', '', '', str(catalog), '登録された作品は0件です'))
        except Cancelled:
            result.cancelled = True
        finally:
            db.close()
    return result


def last_backup(destination):
    try:
        root = backup_root(destination)
        path = safe_path(root, '.system/catalog.sqlite3')
        if not path.is_file():
            return 'まだありません'
        with sqlite3.connect(path.as_uri() + '?mode=ro', uri=True) as db:
            row = db.execute('SELECT finished_at,status FROM runs ORDER BY started_at DESC LIMIT 1').fetchone()
        if not row:
            return 'まだありません'
        labels = {'complete': '完了', 'warnings': '注意あり', 'errors': 'エラーあり', 'cancelled': '中止', 'running': '未完了'}
        return f'{(row[0] or "未完了")[:19].replace("T", " ")}（{labels.get(row[1], row[1])}）'
    except (OSError, ValueError, sqlite3.Error):
        return '確認できません'
