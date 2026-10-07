"""Optional, byte-identical source CSV copies inside the selected library."""
import hashlib,os,re,tempfile
from pathlib import Path
from backup_engine.storage import reject_links


def save_analytics_csv(preview,root):
    if not re.fullmatch(r'[0-9a-f]{64}',preview.file_sha256):
        raise ValueError('CSVの確認情報が不正です。選び直してください。')
    root=reject_links(root)
    if not (root/'.system/catalog.sqlite3').is_file():
        raise ValueError('作品の保存先が見つかりません。ライブラリを開き直してください。')
    folder=reject_links(root/'Analytics')
    folder.mkdir(exist_ok=True)
    period=[]
    for value in (preview.period_start,preview.period_end):
        day=str(value)[:10]
        period.append(day if re.fullmatch(r'\d{4}-\d{2}-\d{2}',day) else '不明')
    target=reject_links(folder/('_'.join(period)+'_'+preview.file_sha256+'.csv'))
    if target.exists():
        with target.open('rb') as stream:actual=hashlib.file_digest(stream,'sha256').hexdigest()
        if actual!=preview.file_sha256:
            raise ValueError('保存済みのAnalytics CSVの内容が変わっています。上書きせず中止しました。')
        return target
    fd,name=tempfile.mkstemp(prefix='.csv-',suffix='.tmp',dir=folder)
    stage=Path(name)
    try:
        digest=hashlib.sha256();copied=0
        with os.fdopen(fd,'wb') as output,Path(preview.path).open('rb') as source:
            while block:=source.read(1024*1024):
                copied+=len(block)
                if copied>50*1024*1024:raise ValueError('CSVが確認後に変更されました。選び直してください。')
                digest.update(block);output.write(block)
            output.flush();os.fsync(output.fileno())
        if digest.hexdigest()!=preview.file_sha256:
            raise ValueError('CSVが確認後に変更されました。選び直してください。')
        # On Windows rename refuses to replace an existing destination.
        try:stage.rename(target)
        except FileExistsError:
            with target.open('rb') as stream:actual=hashlib.file_digest(stream,'sha256').hexdigest()
            if actual!=preview.file_sha256:raise ValueError('同名CSVを上書きせず中止しました。')
        return target
    finally:
        stage.unlink(missing_ok=True)
