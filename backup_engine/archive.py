"""Read official archive data without executing JavaScript or extracting ZIP paths."""
from __future__ import annotations

import io
import re
import zipfile
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path, PurePosixPath
from typing import Callable
from urllib.parse import parse_qs, unquote, urlsplit

import ijson

JST = timezone(timedelta(hours=9), 'Asia/Tokyo')
IMAGES = {'.jpg', '.jpeg', '.png', '.webp', '.gif', '.bmp', '.tif', '.tiff', '.avif', '.heic', '.heif', '.jfif'}
VIDEOS = {'.mp4', '.mov', '.webm', '.m4v', '.mkv', '.avi', '.mpeg', '.mpg', '.3gp', '.ts'}
MEDIA_EXT = IMAGES | VIDEOS


class Cancelled(Exception):
    pass


def check_cancel(cancel):
    if cancel and cancel():
        raise Cancelled('中止しました。保存済みの作品はそのまま残っています。')


@dataclass
class Issue:
    level: str
    post_id: str
    date: str
    source: str
    reason: str


@dataclass
class Asset:
    post_id: str
    posted_at: str
    index: int
    variant: int
    source: str
    offset: int
    size: int
    crc: int
    kind: str
    extension: str

    @property
    def date(self):
        return self.posted_at[:10]

    @property
    def relative_path(self):
        day = self.date
        variant = '' if self.variant == 1 else f'_v{self.variant:02d}'
        return f'{day[:4]}/{day[5:7]}/{day}/{day}_{self.post_id}_{self.index:02d}{variant}{self.extension}'

    @property
    def key(self):
        # Post + attachment + variant. Identical works in different posts remain separate.
        return f'{self.post_id}:{self.index}:{self.variant}'


@dataclass
class Plan:
    zip_path: str
    fingerprint: tuple
    assets: list[Asset] = field(default_factory=list)
    issues: list[Issue] = field(default_factory=list)
    posts: int = 0
    media_posts: int = 0
    excluded_dm: int = 0
    excluded_other: int = 0
    unresolved: int = 0
    datasets: int = 0
    owner: str = ''
    username: str = ''
    account_display_name: str = ''
    earliest_post_at: str | None = None
    latest_post_at: str | None = None
    unknown_dates: int = 0

    @property
    def total_bytes(self):
        return sum(a.size for a in self.assets)


def fingerprint(path):
    stat = Path(path).stat()
    return stat.st_size, stat.st_mtime_ns


def category(name):
    normalized = name.replace('\\', '/').lower().replace('-', '_')
    parts = normalized.split('/')
    if any(p.startswith(('direct_message', 'directmessage', 'dm_media', 'dm_group')) for p in parts):
        return 'dm'
    if any(p.startswith(('profile', 'header', 'avatar', 'advert', 'ad_', 'ads', 'emoji', 'icon', 'moment', 'like', 'bookmark', 'retweet', 'periscope', 'spaces')) for p in parts[:-1]):
        return 'other'
    if any(p in {'assets', 'static', 'css', 'fonts', 'images', 'img'} for p in parts[:-1]):
        return 'other'
    return 'candidate'


class JsonPayload(io.RawIOBase):
    """Bounded-memory JSON reader: strips a JS assignment and final semicolon.

    A bracket-aware scanner stops at the JSON root, never evaluating archive code.
    """
    def __init__(self, raw):
        self.raw = raw
        head = raw.read(65536).lstrip(b'\xef\xbb\xbf \t\r\n')
        if head[:1] not in (b'[', b'{'):
            match = re.match(rb'(?:var\s+)?[\w.$\[\]"\' -]+\s*=\s*', head)
            if not match:
                raise ValueError('JSONまたは公式アーカイブのデータ代入形式ではありません')
            head = head[match.end():]
        if head[:1] not in (b'[', b'{'):
            raise ValueError('JSONの開始が見つかりません')
        self.root = chr(head[0])
        self.head = head
        self.pending = b''
        self.depth = 0
        self.in_string = False
        self.escape = False
        self.ended = False

    def readable(self):
        return True

    def _chunk(self):
        chunk = self.head if self.head else self.raw.read(65536)
        self.head = b''
        if not chunk:
            if not self.ended:
                raise ValueError('投稿データが途中で切れています')
            return b''
        for n, byte in enumerate(chunk):
            if self.in_string:
                if self.escape:
                    self.escape = False
                elif byte == 92:
                    self.escape = True
                elif byte == 34:
                    self.in_string = False
            elif byte == 34:
                self.in_string = True
            elif byte in (91, 123):
                self.depth += 1
            elif byte in (93, 125):
                self.depth -= 1
                if self.depth == 0:
                    self.ended = True
                    tail = chunk[n + 1:]
                    while True:
                        if tail.strip(b' \t\r\n;'):
                            raise ValueError('投稿データの末尾に未対応の内容があります')
                        tail = self.raw.read(65536)
                        if not tail:
                            break
                    return chunk[:n + 1]
        return chunk

    def readinto(self, buffer):
        if not self.pending and not self.ended:
            self.pending = self._chunk()
        count = min(len(buffer), len(self.pending))
        buffer[:count] = self.pending[:count]
        self.pending = self.pending[count:]
        return count


def records(zf, info):
    with zf.open(info) as raw:
        payload = JsonPayload(raw)
        if payload.root == '[':
            prefix = 'item'
        else:
            match = re.search(rb'"(tweets|posts|data)"\s*:\s*\[', payload.head[:2048])
            if not match:
                raise ValueError('未対応の投稿データ構造です（配列が見つかりません）')
            prefix = match[1].decode() + '.item'
        yield from ijson.items(io.BufferedReader(payload), prefix)


def dataset_kind(name, head):
    path = name.lower().replace('\\', '/')
    base = PurePosixPath(path).stem.replace('_', '-')
    # These collections are not authored posts, even if they contain nested tweet objects.
    if re.search(r'(direct.?message|dm-|like|bookmark|moment|advert|^ad-|profile|account)', base):
        return 'account' if base == 'account' else ''
    if re.fullmatch(r'(?:(?:deleted|community)-)?(?:tweets?|posts?)(?:-part\d+)?', base):
        return 'posts'
    if re.search(rb'window\.YTD\.(?:(?:deleted|community)_)?(?:tweets?|posts?)\.part\d+\s*=', head):
        return 'posts'
    if b'window.YTD.account.' in head:
        return 'account'
    if '/tweets/' in path and b'Grailbird.data.tweets_' in head:
        return 'posts'
    # Renamed JSON files: require a clearly named collection, not arbitrary nested tweets.
    if path.endswith('.json') and re.match(rb'\s*\{\s*"(?:tweets|posts)"\s*:', head):
        return 'posts'
    return ''


def post_date(value):
    text = str(value or '')
    try:
        result = datetime.fromisoformat(text.replace('Z', '+00:00'))
    except ValueError:
        result = parsedate_to_datetime(text)
    if result is None or result.tzinfo is None:
        raise ValueError('投稿日時にタイムゾーンがありません')
    return result.astimezone(JST).isoformat()


def url_name(value):
    url = urlsplit(str(value))
    name = unquote(PurePosixPath(url.path).name)
    name = re.sub(r':(?:orig|large|medium|small|thumb)$', '', name)
    extension = parse_qs(url.query).get('format', [''])[0]
    if not PurePosixPath(name).suffix and re.fullmatch('[A-Za-z0-9]+', extension or ''):
        name += '.' + extension
    return name


def attached_media(tweet):
    result = []
    seen = set()
    for container in ('extended_entities', 'entities'):
        data = tweet.get(container) or {}
        for media in data.get('media', []):
            if not isinstance(media, dict):
                continue
            key = str(media.get('id_str') or media.get('id') or media.get('media_url_https') or media.get('media_url') or repr(media))
            if key not in seen:
                result.append(media)
                seen.add(key)
    return result


def analyze(path, progress: Callable = lambda *x: None, cancel=None):
    path = str(Path(path).absolute())
    plan = Plan(path, fingerprint(path))
    progress('ZIPの目次を読み込んでいます', 0, 0)
    with zipfile.ZipFile(path, 'r', allowZip64=True) as zf:
        infos = zf.infolist()
        by_name = defaultdict(list)
        by_post = defaultdict(list)
        candidates = []
        datasets = []
        accounts = []
        for n, info in enumerate(infos):
            check_cancel(cancel)
            if n % 250 == 0:
                progress('ZIP内のファイルを確認しています', n, len(infos))
            if info.is_dir():
                continue
            extension = PurePosixPath(info.filename).suffix.lower()
            group = category(info.filename)
            if extension in MEDIA_EXT:
                if group == 'dm':
                    plan.excluded_dm += 1
                elif group == 'other':
                    plan.excluded_other += 1
                else:
                    candidates.append(info)
                    name = PurePosixPath(info.filename.replace('\\', '/')).name
                    by_name[name].append(info)
                    match = re.match(r'^(\d+)[-_]', name)
                    if match:
                        by_post[match[1]].append(info)
            elif extension in {'.js', '.json'} and group == 'candidate':
                try:
                    with zf.open(info) as raw:
                        head = raw.read(8192)
                    kind = dataset_kind(info.filename, head)
                    if kind == 'posts':
                        datasets.append(info)
                    elif kind == 'account':
                        accounts.append(info)
                except Exception as exc:
                    plan.issues.append(Issue('注意', '', '', info.filename, f'データ判別失敗: {exc}'))
        for info in accounts:
            try:
                for row in records(zf, info):
                    acc = row.get('account', row)
                    identity = str(acc.get('accountId') or acc.get('id_str') or '')
                    if identity:
                        if plan.owner and plan.owner != identity:
                            raise ValueError('複数アカウントのデータが混在しています')
                        plan.owner = identity
                        plan.username = str(acc.get('username') or '')[:80]
                        plan.account_display_name = str(acc.get('accountDisplayName') or '')[:200]
            except Exception as exc:
                raise ValueError(f'アカウント情報を確認できません: {info.filename}: {exc}') from exc
        if not datasets:
            raise ValueError('公式アーカイブの投稿データを見つけられませんでした。ZIPの種類または形式をご確認ください。')
        plan.datasets = len(datasets)
        seen_posts = set()
        seen_media_posts = set()
        used = set()
        deliberately_excluded = set()
        asset_identity = set()

        def match_files(pid, url):
            name = url_name(url)
            if not name:
                return []
            prefixed = by_name.get(pid + '-' + name, []) + by_name.get(pid + '_' + name, [])
            if prefixed:
                return prefixed
            plain = by_name.get(name, [])
            # An exact URL filename can appear without a post prefix in newer layouts.
            return plain if len(plain) == 1 else []

        for di, datafile in enumerate(datasets):
            check_cancel(cancel)
            progress(f'投稿データを解析しています ({di + 1}/{len(datasets)})', 0, 0)
            try:
                for row in records(zf, datafile):
                    check_cancel(cancel)
                    if not isinstance(row, dict):
                        plan.issues.append(Issue('エラー', '', '', datafile.filename, '投稿レコードがオブジェクトではありません'))
                        continue
                    tweet = row.get('tweet') or row.get('post') or row.get('deletedTweet') or row.get('communityTweet') or row
                    pid = str(tweet.get('id_str') or tweet.get('id') or '')
                    if not re.fullmatch(r'\d{1,30}', pid):
                        plan.issues.append(Issue('エラー', pid, '', datafile.filename, '投稿IDを読み取れません'))
                        continue
                    user = tweet.get('user') or {}
                    author = str(tweet.get('user_id_str') or tweet.get('author_id') or user.get('id_str') or user.get('id') or '')
                    text = str(tweet.get('full_text') or tweet.get('text') or '')
                    repost = bool(tweet.get('retweeted_status') or tweet.get('retweeted_status_id_str') or re.match(r'^RT\s+@', text))
                    if repost or (plan.owner and author and author != plan.owner):
                        deliberately_excluded.update(f.header_offset for f in by_post.get(pid, []))
                        continue
                    seen_posts.add(pid)
                    media_items = attached_media(tweet)
                    own_items = []
                    for index, media in enumerate(media_items, 1):
                        source_pid = str(media.get('source_status_id_str') or media.get('source_status_id') or '')
                        source_user = str(media.get('source_user_id_str') or media.get('source_user_id') or '')
                        expanded = re.search(r'/status/(\d+)', str(media.get('expanded_url') or ''))
                        foreign = (source_pid and source_pid != pid) or (plan.owner and source_user and source_user != plan.owner) or (expanded and expanded[1] != pid)
                        if foreign:
                            for url in [media.get('media_url_https', ''), media.get('media_url', '')] + [v.get('url', '') for v in (media.get('video_info') or {}).get('variants', [])]:
                                deliberately_excluded.update(f.header_offset for f in match_files(pid, url))
                            continue
                        own_items.append((index, media))
                    if own_items:
                        seen_media_posts.add(pid)
                    try:
                        posted_at = post_date(tweet.get('created_at') or tweet.get('createdAt'))
                    except Exception as exc:
                        plan.unknown_dates += 1
                        if own_items or by_post.get(pid):
                            plan.issues.append(Issue('エラー', pid, '', datafile.filename, f'投稿日時を読めません: {exc}'))
                        continue
                    plan.earliest_post_at = min(plan.earliest_post_at or posted_at, posted_at)
                    plan.latest_post_at = max(plan.latest_post_at or posted_at, posted_at)
                    # Official post-media directory + authored post ID is also a documented relation.
                    # Do not use this fallback for quotes, which can reference someone else's media.
                    if not media_items and not any(tweet.get(k) for k in ('is_quote_status', 'quoted_status', 'quoted_status_id', 'quoted_status_id_str')):
                        fallback = [f for f in by_post.get(pid, []) if any(re.fullmatch(r'(?:(?:deleted|community)_)?tweets?_media', p) for p in f.filename.lower().replace('-', '_').split('/')[:-1])]
                        for index, info in enumerate(sorted(fallback, key=lambda f: (f.filename, f.header_offset)), 1):
                            identity = (pid, info.header_offset)
                            if identity in asset_identity:
                                continue
                            ext = PurePosixPath(info.filename).suffix.lower()
                            asset_kind = 'gif' if ext == '.gif' else ('video' if ext in VIDEOS else 'image')
                            plan.assets.append(Asset(pid, posted_at, index, 1, info.filename, info.header_offset, info.file_size, info.CRC, asset_kind, ext))
                            asset_identity.add(identity)
                            used.add(info.header_offset)
                            seen_media_posts.add(pid)
                            plan.issues.append(Issue('注意', pid, posted_at[:10], info.filename, '添付情報がないため、公式投稿メディアフォルダと投稿IDの一致から保存対象にしました。'))
                    for index, media in own_items:
                        kind = str(media.get('type') or 'photo')
                        urls = []
                        if kind in {'video', 'animated_gif'}:
                            urls = [v.get('url', '') for v in (media.get('video_info') or {}).get('variants', []) if v.get('content_type') == 'video/mp4' or PurePosixPath(urlsplit(v.get('url', '')).path).suffix.lower() in VIDEOS]
                            # Thumbnails of videos are display assets, not the video itself.
                            for key in ('media_url_https', 'media_url'):
                                deliberately_excluded.update(f.header_offset for f in match_files(pid, media.get(key, '')))
                        else:
                            urls = [media.get('media_url_https', ''), media.get('media_url', '')]
                        matched = {}
                        for url in urls:
                            for f in match_files(pid, url):
                                ext = PurePosixPath(f.filename).suffix.lower()
                                if (kind in {'video', 'animated_gif'} and ext in VIDEOS | {'.gif'}) or (kind not in {'video', 'animated_gif'} and ext in IMAGES):
                                    matched[f.header_offset] = f
                        # Some exports omit video_info; a sole video under this post is unambiguous.
                        if not matched and kind in {'video', 'animated_gif'} and len(own_items) == 1:
                            video_files = [f for f in by_post.get(pid, []) if PurePosixPath(f.filename).suffix.lower() in VIDEOS | {'.gif'}]
                            if len(video_files) == 1:
                                matched[video_files[0].header_offset] = video_files[0]
                        if not matched:
                            plan.issues.append(Issue('エラー', pid, posted_at[:10], next((u for u in urls if u), datafile.filename), f'{index}番目の添付メディアがZIP内に見つかりません（または対応付けが曖昧です）'))
                            continue
                        for variant, info in enumerate(sorted(matched.values(), key=lambda f: (f.filename, f.header_offset)), 1):
                            identity = (pid, info.header_offset)
                            if identity in asset_identity:
                                continue
                            ext = PurePosixPath(info.filename).suffix.lower()
                            asset_kind = 'gif' if kind == 'animated_gif' or ext == '.gif' else ('video' if ext in VIDEOS else 'image')
                            plan.assets.append(Asset(pid, posted_at, index, variant, info.filename, info.header_offset, info.file_size, info.CRC, asset_kind, ext))
                            asset_identity.add(identity)
                            used.add(info.header_offset)
                    if len(seen_posts) % 200 == 0:
                        progress(f'投稿 {len(seen_posts):,}件・作品 {len(plan.assets):,}件を確認', 0, 0)
            except Cancelled:
                raise
            except Exception as exc:
                plan.issues.append(Issue('エラー', '', '', datafile.filename, f'投稿データの読み取りに失敗しました: {exc}'))
        plan.posts = len(seen_posts)
        plan.media_posts = len(seen_media_posts)
        for info in candidates:
            if info.header_offset in used:
                continue
            if info.header_offset in deliberately_excluded:
                plan.excluded_other += 1
            else:
                plan.unresolved += 1
                pid = re.match(r'^(\d+)[-_]', PurePosixPath(info.filename).name)
                plan.issues.append(Issue('注意', pid[1] if pid else '', '', info.filename, '自分の投稿添付メディアとの対応を確認できないため未保存です。元ZIPには残っています。'))
        plan.assets.sort(key=lambda a: (a.posted_at, a.post_id, a.index, a.variant, a.source))
    if fingerprint(path) != plan.fingerprint:
        raise ValueError('解析中にZIPが変更されました。選び直してください。')
    progress(f'解析完了：作品 {len(plan.assets):,}件', 1, 1)
    return plan
