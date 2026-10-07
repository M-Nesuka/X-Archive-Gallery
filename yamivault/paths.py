"""User-scoped persistent storage; legacy DB publication is atomic and reversible."""
import json,os,shutil,sqlite3,sys,tempfile
from datetime import datetime,timezone
from pathlib import Path


def app_home():
    if not getattr(sys,'frozen',False):return Path(__file__).resolve().parents[1]
    if os.environ.get('XAG_LAUNCHER_HOME'):return Path(os.environ['XAG_LAUNCHER_HOME']).resolve()
    executable=Path(sys.executable).resolve()
    if executable.parent.parent.parent.name=='releases':return executable.parent.parent.parent.parent
    return executable.parent


def default_data():
    local=Path(os.environ.get('LOCALAPPDATA',str(Path.home()/'AppData'/'Local')))
    return local/'XArchiveGallery'/'data'


def legacy_data():
    return app_home()/'release'/'YAMIVAULT'/'data'


def legacy_candidates():
    return [app_home()/'data',legacy_data()]


def migrate_legacy(source,destination):
    source,destination=Path(source).resolve(),Path(destination).resolve()
    old=source/'yami_vault.sqlite3';new=destination/'yami_vault.sqlite3'
    if source==destination or new.exists() or not old.is_file():return False
    if source.is_relative_to(destination) or destination.is_relative_to(source):
        raise ValueError('旧版データと移行先は別のフォルダーにしてください。')
    destination.mkdir(parents=True,exist_ok=True)
    stage=Path(tempfile.mkdtemp(prefix='.migration-',dir=destination))
    stamp=datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S-%f')
    try:
        src=sqlite3.connect(old.as_uri()+'?mode=ro',uri=True)
        dst=sqlite3.connect(stage/'yami_vault.sqlite3')
        try:
            if src.execute('PRAGMA integrity_check').fetchone()[0]!='ok':raise ValueError('旧版DBの整合性を確認できません。元データは保持しています。')
            src.backup(dst)
            if dst.execute('PRAGMA integrity_check').fetchone()[0]!='ok':raise ValueError('移行用DBを安全に作成できません。元データは保持しています。')
        finally:dst.close();src.close()
        media=source/'warning_media'
        if media.exists():
            if media.is_symlink() or getattr(media,'is_junction',lambda:False)() or any(p.is_symlink() or getattr(p,'is_junction',lambda:False)() for p in media.rglob('*')):
                raise ValueError('旧版の追加メディアにリンクがあります。元データを保持して移行を中止しました。')
            if (destination/'warning_media').exists():raise ValueError('移行先に追加メディアがあるため自動移行を中止しました。両方のデータは保持しています。')
            shutil.copytree(media,stage/'warning_media')
        backups=destination/'backups';backups.mkdir(exist_ok=True)
        backup=backups/('before-legacy-migration-'+stamp+'.sqlite3')
        shutil.copy2(stage/'yami_vault.sqlite3',backup)
        if (stage/'warning_media').exists():(stage/'warning_media').rename(destination/'warning_media')
        try:
            if new.exists():raise ValueError('移行先DBが既にあります。上書きせず中止しました。')
            (stage/'yami_vault.sqlite3').rename(new)
        except Exception:
            if media.exists() and (destination/'warning_media').exists():(destination/'warning_media').rename(stage/'warning_media')
            raise
        (destination/'migration.json').write_text(json.dumps({'identities_preserved':True,'source_preserved':True,'backup_filename':backup.name,'cache_regenerated':True},indent=2),encoding='utf-8')
        return True
    finally:
        if stage.exists() and stage.parent==destination and stage.name.startswith('.migration-'):shutil.rmtree(stage)
