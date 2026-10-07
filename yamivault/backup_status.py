"""Read-only projection of authoritative backup history. No schema migration."""
import json
import sqlite3
from pathlib import Path
from datetime import datetime
from .catalog import source_path, JST


def read_status(root):
    path = source_path(root, '.system/catalog.sqlite3')
    if not path.exists():
        return {'latest':None, 'count':0, 'warnings':0, 'errors':0, 'last_complete':None,
                'last_attempt':None, 'unfinished':0}
    if Path(str(path)+'-wal').exists():
        raise RuntimeError('カタログが更新中です。更新が終わってから再読込してください。')
    db = sqlite3.connect(path.as_uri()+'?mode=ro',uri=True,timeout=2)
    db.row_factory = sqlite3.Row
    try:
        db.execute('PRAGMA query_only=ON')
        tables = {r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        dates = []
        count = 0
        for row in db.execute('SELECT posted_at FROM assets'):
            count += 1
            try:
                dt = datetime.fromisoformat(row[0].replace('Z','+00:00'))
                dates.append((dt if dt.tzinfo else dt.replace(tzinfo=JST)).astimezone(JST))
            except (ValueError,TypeError):
                pass
        issues = dict(db.execute('SELECT level,count(*) FROM issues WHERE active=1 GROUP BY level')) if 'issues' in tables else {}
        issue_details = [dict(r) for r in db.execute('SELECT level,post_id,date,source,reason,zip_path FROM issues WHERE active=1 ORDER BY id DESC LIMIT 500')] if 'issues' in tables else []
        runs = [dict(r) for r in db.execute('SELECT id,started_at,finished_at,status,result,zip_path FROM runs ORDER BY started_at DESC')] if 'runs' in tables else []
        last_complete = None
        for run in runs:
            if run['status'] not in ('complete','warnings') or not run['finished_at']:
                continue
            try:
                result = json.loads(run['result'] or '{}')
                if result.get('cancelled') or not isinstance(result.get('total'),int) or result.get('checked') != result.get('total'):
                    continue
                if any(i.get('level')=='エラー' for i in result.get('issues',[])):
                    continue
            except (ValueError,TypeError,AttributeError):
                continue
            last_complete = run
            break
        return {'latest':max(dates).isoformat() if dates else None, 'count':count,
                'warnings':issues.get('注意',0), 'errors':issues.get('エラー',0),
                'last_complete':last_complete, 'last_attempt':runs[0] if runs else None,
                'unfinished':sum(r['status']=='running' for r in runs), 'issues':issue_details}
    finally:
        db.close()
