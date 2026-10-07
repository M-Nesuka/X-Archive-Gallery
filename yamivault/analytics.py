"""Read-only parsing and post-level calculations for X Analytics CSV exports."""
from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import date, datetime
import hashlib
import io
import json
from pathlib import Path
from .i18n import tr,trf


FIELD_HEADERS = {
    'post_id': ('ポストID', '投稿ID', 'Post ID', 'Tweet ID', 'ID'),
    'posted_at': ('日付', '投稿日', 'Date', 'Post date', 'Post Date'),
    'permalink': ('ポストのリンク', '投稿リンク', 'Post link', 'Post URL', 'Permalink'),
    'impressions': ('インプレッション数', 'インプレッション', 'Impressions'),
    'likes': ('いいね', 'Likes'),
    'engagements': ('エンゲージメント', 'エンゲージメント数', 'Engagements', 'Engagement'),
    'bookmarks': ('ブックマーク', 'ブックマーク数', 'Bookmarks'),
    'shares': ('共有された回数', '共有数', 'Shares'),
    'new_follows': ('新しいフォロー', '新しいフォロワー', 'Follows', 'New follows'),
    'replies': ('返信', '返信数', 'Replies'),
    'reposts': ('リポスト', 'リポスト数', 'Reposts', 'Reposts (Retweets)'),
    'profile_visits': ('プロフィールへのアクセス数', 'プロフィール訪問数', 'User profile clicks', 'Profile visits'),
    'detail_clicks': ('詳細のクリック数', '詳細クリック数', 'Detail expands', 'Detail clicks'),
    'url_clicks': ('URLのクリック数', 'リンククリック数', 'URL clicks', 'Link clicks'),
    'hashtag_clicks': ('ハッシュタグのクリック数', 'Hashtag clicks'),
    'permalink_clicks': ('パーマリンクのクリック数', 'Permalink clicks'),
}

METRIC_LABELS = {
    'impressions': 'インプレッション',
    'likes': 'いいね',
    'engagements': 'エンゲージメント',
    'bookmarks': 'ブックマーク（保存）',
    'shares': '共有',
    'new_follows': '新しいフォロー',
    'replies': '返信',
    'reposts': 'リポスト（RP）',
    'profile_visits': 'プロフィールへのアクセス',
    'detail_clicks': '詳細クリック',
    'url_clicks': 'URLクリック',
    'hashtag_clicks': 'ハッシュタグクリック',
    'permalink_clicks': 'パーマリンククリック',
}

RATE_DEFINITIONS = {
    'like_rate': ('likes', '#高いいね率', '#いいね率1位'),
    'repost_rate': ('reposts', '#高RP率', '#RP率1位'),
    'bookmark_rate': ('bookmarks', '#高保存率', '#保存率1位'),
    'profile_rate': ('profile_visits', '#高Profile率', '#Profile率1位'),
    'engagement_rate': ('engagements', None, '#エンゲージメント率1位'),
}

HIGH_TAGS = {
    'impressions': '#高インプ',
    'like_rate': '#高いいね率',
    'repost_rate': '#高RP率',
    'bookmark_rate': '#高保存率',
    'profile_rate': '#高Profile率',
    'follows_per_1000': '#高Follow効率',
}

TOP_TAGS = {
    'impressions': '#インプ1位',
    'likes': '#いいね1位',
    'like_rate': '#いいね率1位',
    'reposts': '#RP1位',
    'repost_rate': '#RP率1位',
    'bookmarks': '#保存1位',
    'bookmark_rate': '#保存率1位',
    'profile_visits': '#プロフィール訪問数1位',
    'profile_rate': '#Profile率1位',
    'new_follows': '#フォロー獲得1位',
    'follows_per_1000': '#Follow効率1位',
    'engagements': '#エンゲージ1位',
    'engagement_rate': '#エンゲージメント率1位',
}

POST_METRICS = tuple(METRIC_LABELS)

def performance_tag_name(name):
    # Present older saved tags clearly without rewriting users' snapshots.
    return '#プロフィール訪問数1位' if name=='#Profile1位' else name
RATE_METRICS = ('like_rate', 'repost_rate', 'bookmark_rate', 'profile_rate',
                'follows_per_1000', 'engagement_rate')


class AnalyticsCsvError(ValueError):
    pass


@dataclass
class AnalyticsPreview:
    path: Path
    file_sha256: str
    columns: list[str]
    field_columns: dict[str, str]
    rows: list[dict]
    period_start: str
    period_end: str
    blank_metrics: dict[str, int]
    scope: str
    duplicate_post_ids: list[str]
    invalid_rows: list[str]
    matched_posts: int
    unmatched_posts: int
    already_imported: bool = False

    @property
    def post_count(self):
        return len(self.rows)

    @property
    def recognized_metrics(self):
        return [key for key in POST_METRICS if key in self.field_columns]

    @property
    def missing_metrics(self):
        return [key for key in POST_METRICS if key not in self.field_columns]

    @property
    def can_import(self):
        return bool(self.rows) and not self.already_imported and not self.duplicate_post_ids and not self.invalid_rows


def _header_map(columns):
    lookup = {str(name or '').strip().casefold(): str(name or '').strip() for name in columns}
    found = {}
    for field, aliases in FIELD_HEADERS.items():
        for alias in aliases:
            actual = lookup.get(alias.casefold())
            if actual is not None:
                found[field] = actual
                break
    for required in ('post_id', 'posted_at'):
        if required not in found:
            expected = tr('ポストID / Post ID') if required == 'post_id' else tr('日付 / Date')
            raise AnalyticsCsvError(trf('必須列「{0}」を認識できませんでした。',expected))
    return found


def _parse_date(value):
    text = str(value or '').strip()
    if not text:
        return ''
    try:
        return date.fromisoformat(text[:10]).isoformat()
    except ValueError:
        pass
    for pattern in ('%a, %b %d, %Y', '%b %d, %Y', '%m/%d/%Y', '%d/%m/%Y'):
        try:
            return datetime.strptime(text, pattern).date().isoformat()
        except ValueError:
            continue
    return ''


def _parse_count(value):
    text = str(value or '').strip().replace(',', '').replace('\u00a0', '')
    if not text:
        return None
    if not text.isdecimal():
        raise ValueError(tr('整数ではありません'))
    return int(text)


def _read_csv_bytes(raw):
    try:
        return raw.decode('utf-8-sig')
    except UnicodeDecodeError:
        try:
            return raw.decode('cp932')
        except UnicodeDecodeError as exc:
            raise AnalyticsCsvError(tr('CSVの文字コードを読み取れません。UTF-8またはShift-JISのCSVを選択してください。')) from exc


def preview_analytics_csv(path, assets, already_imported=False):
    path = Path(path)
    try:
        raw = path.read_bytes()
    except OSError as exc:
        raise AnalyticsCsvError(trf('CSVを開けませんでした: {0}',exc)) from exc
    if len(raw) > 50 * 1024 * 1024:
        raise AnalyticsCsvError(tr('CSVが大きすぎます（上限50MB）。期間を分けて出力してください。'))
    text = _read_csv_bytes(raw)
    reader = csv.DictReader(io.StringIO(text, newline=''))
    columns = [str(name or '').strip() for name in (reader.fieldnames or [])]
    if not columns:
        raise AnalyticsCsvError(tr('CSVにヘッダー行がありません。'))
    fields = _header_map(columns)
    rows = []
    invalid = []
    counts_by_id = {}
    for row_number, source in enumerate(reader, start=2):
        post_id = str(source.get(fields['post_id']) or '').strip()
        if not post_id or not post_id.isdecimal():
            invalid.append(trf('{0}行目: 投稿IDが空欄または不正',row_number))
            continue
        counts_by_id[post_id] = counts_by_id.get(post_id, 0) + 1
        posted_at = _parse_date(source.get(fields['posted_at']))
        record = {'post_id': post_id, 'posted_at': posted_at,
                  'permalink': str(source.get(fields.get('permalink')) or '').strip() if fields.get('permalink') else ''}
        bad_fields = []
        for metric in POST_METRICS:
            if metric in fields:
                try:
                    record[metric] = _parse_count(source.get(fields[metric]))
                except ValueError:
                    bad_fields.append(METRIC_LABELS[metric])
            else:
                record[metric] = None
        if bad_fields:
            invalid.append(trf('{0}行目: 数値形式が不正（{1}）',row_number,", ".join(bad_fields)))
            continue
        if not posted_at:
            invalid.append(trf('{0}行目: 投稿日を認識できません',row_number))
        for rate in RATE_METRICS:
            record[rate] = None
        impressions = record['impressions']
        if impressions and impressions > 0:
            for rate, (numerator, _high, _top) in RATE_DEFINITIONS.items():
                value = record.get(numerator)
                if value is not None:
                    record[rate] = value / impressions
            if record['new_follows'] is not None:
                record['follows_per_1000'] = record['new_follows'] * 1000 / impressions
        known_fields = set(fields.values())
        extra = {str(k): v for k, v in source.items()
                 if k and k not in known_fields and v not in (None, '')
                 and not any(token in k.casefold() for token in ('本文', 'text', 'ポストのリンク', '投稿リンク', 'permalink', 'post url'))}
        record['extra_metrics_json'] = json.dumps(extra, ensure_ascii=False, separators=(',', ':'))
        rows.append(record)
    duplicate_ids = sorted(post_id for post_id, count in counts_by_id.items() if count > 1)
    dates = [row['posted_at'] for row in rows if row['posted_at']]
    post_ids = {row['post_id'] for row in rows}
    asset_post_ids = {str(asset.post_id).strip() for asset in assets if str(asset.post_id or '').strip()}
    lowered_headers = [column.casefold() for column in columns]
    scope = 'organic_promoted_columns' if any(('organic' in c or 'promoted' in c or 'オーガニック' in c or 'プロモーション' in c) for c in lowered_headers) else 'not_separated'
    return AnalyticsPreview(
        path=path, file_sha256=hashlib.sha256(raw).hexdigest(), columns=columns,
        field_columns=fields, rows=rows, period_start=min(dates) if dates else '',
        period_end=max(dates) if dates else '',
        blank_metrics={metric:sum(row.get(metric) is None for row in rows)
                       for metric in POST_METRICS if metric in fields},
        scope=scope,
        duplicate_post_ids=duplicate_ids, invalid_rows=invalid,
        matched_posts=len(post_ids & asset_post_ids), unmatched_posts=len(post_ids - asset_post_ids),
        already_imported=already_imported)


def performance_tags(rows):
    """Return high-percentile and tied-first-place tags for a unique-post cohort."""
    tags_by_post = {row['post_id']: [] for row in rows}
    rank_metrics = dict(HIGH_TAGS)
    rank_metrics.update({metric: None for metric in TOP_TAGS if metric not in rank_metrics})
    for metric, values in rank_metrics.items():
        eligible = [(row['post_id'], row.get(metric)) for row in rows if row.get(metric) is not None]
        if not eligible:
            continue
        ordered = sorted((value for _post_id, value in eligible), reverse=True)
        top_value = ordered[0]
        high_tag = HIGH_TAGS.get(metric)
        threshold = ordered[max(0, (len(ordered) + 9) // 10 - 1)] if high_tag else None
        top_tag = TOP_TAGS.get(metric)
        for post_id, value in eligible:
            if high_tag and value > 0 and value >= threshold:
                tags_by_post[post_id].append({'tag_code': f'high:{metric}', 'tag_name': high_tag,
                    'metric_key': metric, 'metric_value': value, 'tag_type': 'high',
                    'threshold_value': threshold, 'sample_size': len(eligible)})
            if top_tag and top_value > 0 and value == top_value:
                tags_by_post[post_id].append({'tag_code': f'top:{metric}', 'tag_name': top_tag,
                    'metric_key': metric, 'metric_value': value, 'tag_type': 'top1',
                    'threshold_value': top_value, 'sample_size': len(eligible)})
    return tags_by_post
