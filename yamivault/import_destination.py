"""Validate an import destination without creating files or opening it in the gallery."""
from .i18n import tr,trf
from pathlib import Path
import sqlite3
from .library_reset import is_empty_or_lock_only


def validate_destination(folder, private_data):
    root = Path(folder).resolve()
    private = Path(private_data).resolve()
    if root.parent == root:
        raise ValueError(tr('ドライブ全体ではなく、バックアップ専用のフォルダーを選んでください。'))
    if private.is_relative_to(root) or root.is_relative_to(private):
        raise ValueError(tr('アプリの設定・キャッシュとは別のバックアップ専用フォルダーを選んでください。'))
    if root.exists():
        if not root.is_dir():
            raise ValueError(tr('ファイルではなく、保存先フォルダーを選んでください。'))
        catalog = root/'.system/catalog.sqlite3'
        if catalog.is_file():
            from .catalog import read_catalog
            try:
                read_catalog(root)  # Validate with a read-only connection.
            except (sqlite3.Error,RuntimeError) as error:
                raise ValueError(tr('既存のバックアップを確認できません。')+str(error)) from error
        elif not is_empty_or_lock_only(root):
            raise ValueError(tr('このフォルダーには他のファイルがあります。新しい空のフォルダーを作成して選んでください。'))
    return root
