"""Guarded, exclusive deletion of one selected backup library's contents."""
from pathlib import Path
import shutil

from backup_engine.storage import store_lock


def _is_link(path):
    return path.is_symlink() or (hasattr(path,'is_junction') and path.is_junction())


def _reject_links(root):
    for path in root.rglob('*'):
        if _is_link(path):
            raise ValueError(f'リンク先を誤って削除しないよう中止しました: {path}')


def is_empty_or_lock_only(root):
    root=Path(root)
    children=list(root.iterdir()) if root.is_dir() else []
    if not children:
        return True
    system=root/'.system'
    return children==[system] and system.is_dir() and all(p.name=='backup.lock' for p in system.iterdir())


def clear_backup(root):
    """Delete every library file except the live OS lock; require a catalog marker."""
    root=Path(root).resolve(strict=True)
    if root.parent==root or not root.is_dir():
        raise ValueError('安全なバックアップフォルダーを選択してください。')
    system=root/'.system'
    catalog=system/'catalog.sqlite3'
    if not catalog.is_file():
        raise ValueError('カタログがないフォルダーは初期化できません。対象を確認してください。')
    _reject_links(root)
    with store_lock(system):
        _reject_links(root)
        for child in list(root.iterdir()):
            if child==system:
                for item in list(system.iterdir()):
                    if item.name=='backup.lock':
                        continue
                    if item.is_dir():
                        shutil.rmtree(item)
                    else:
                        item.unlink()
            elif child.is_dir():
                shutil.rmtree(child)
            else:
                child.unlink()
    if not is_empty_or_lock_only(root):
        raise RuntimeError('一部のバックアップファイルを削除できませんでした。残った項目を確認してください。')
    return root
