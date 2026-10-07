from __future__ import annotations

import argparse
import logging
import os
import sys
from pathlib import Path
from yamivault.version import __version__


def main():
    parser = argparse.ArgumentParser(description=f'X Archive Gallery v{__version__}')
    parser.add_argument('--data-dir', type=Path)
    parser.add_argument('--library', type=Path)
    parser.add_argument('--migrate-legacy',action='store_true',help='旧版の自分のアプリデータを標準ユーザー領域へ引き継ぐ')
    parser.add_argument('--qa', type=Path, help=argparse.SUPPRESS)
    parser.add_argument('--qa-import', type=Path, help=argparse.SUPPRESS)
    parser.add_argument('--qa-startup', type=Path, help=argparse.SUPPRESS)
    parser.add_argument('--qa-onboarding', type=Path, help=argparse.SUPPRESS)
    parser.add_argument('--qa-support', type=Path, help=argparse.SUPPRESS)
    parser.add_argument('--import-worker', type=Path, help=argparse.SUPPRESS)
    parser.add_argument('--worker-action', choices=['analyze','backup'], help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.qa and args.data_dir is None:
        parser.error('--qa requires an isolated --data-dir')
    if args.import_worker:
        from yamivault.import_worker import run
        return run(args.import_worker, args.worker_action)
    if args.qa_import:
        if not args.data_dir or not args.library or not args.library.resolve().is_relative_to(args.qa_import.resolve()):
            raise ValueError('Import QA requires isolated explicit paths')
        args.library.mkdir(parents=True,exist_ok=True)
    from yamivault.paths import default_data, legacy_data, legacy_candidates, migrate_legacy
    base = default_data()
    data_dir = (args.data_dir or base).resolve()
    if args.qa_onboarding and (not args.data_dir or args.library or not data_dir.is_relative_to(args.qa_onboarding.resolve())):
        parser.error('Onboarding QA requires isolated data and an unconfigured library')
    if args.qa_startup and not data_dir.is_relative_to(args.qa_startup.resolve()):
        parser.error('Startup QA requires a fully isolated user profile')
    if (args.qa or args.qa_import or args.qa_onboarding) and data_dir in (base.resolve(), legacy_data().resolve()):
        parser.error('QA cannot use the application user-data directory')
    # Own writes must never be routed into the protected backup library.
    from yamivault.catalog import DEFAULT_ROOT
    for root in (DEFAULT_ROOT,args.library):
        if root and (data_dir.is_relative_to(root.resolve()) or root.resolve().is_relative_to(data_dir)):
            raise ValueError('X Archive Galleryの保存先はバックアップフォルダーの外に指定してください。')
    data_dir.mkdir(parents=True,exist_ok=True)
    from yamivault.diagnostics import configure_logs, friendly_error
    configure_logs(data_dir)
    if any((args.qa,args.qa_import,args.qa_startup,args.qa_onboarding)):
        if not args.qa_support or not args.qa_support.is_dir():
            parser.error('QA requires an external --qa-support directory; validation code is not distributed')
        import yamivault
        yamivault.__path__.append(str(args.qa_support.resolve()))
    from PySide6.QtCore import QLockFile, Qt
    from PySide6.QtGui import QIcon, QPalette, QColor
    from PySide6.QtWidgets import QApplication, QMessageBox
    from yamivault.gui import MainWindow
    app = QApplication(sys.argv[:1])
    # Read only the language preference before any startup messages are shown.
    from yamivault.i18n import set_language_code,tr,preferred_language
    set_language_code(preferred_language(data_dir))
    app.setStyle('Fusion')
    palette = app.palette()
    for role, color in [(QPalette.ColorRole.Window,'#0b0b0e'),(QPalette.ColorRole.WindowText,'#eeebf4'),(QPalette.ColorRole.Base,'#17141c'),(QPalette.ColorRole.AlternateBase,'#201c26'),(QPalette.ColorRole.Text,'#eeebf4'),(QPalette.ColorRole.Button,'#211c29'),(QPalette.ColorRole.ButtonText,'#eeebf4'),(QPalette.ColorRole.Highlight,'#59446f'),(QPalette.ColorRole.HighlightedText,'#ffffff')]:
        palette.setColor(role,QColor(color))
    app.setPalette(palette)
    app.setApplicationName('X Archive Gallery')
    app.setOrganizationName('X Archive Gallery')
    lock = QLockFile(str(data_dir / 'yami_vault.lock'))
    lock.setStaleLockTime(0)
    if not lock.tryLock(100):
        QMessageBox.information(None,'X Archive Gallery',tr('X Archive Galleryはすでに起動しています。タスクバーから開いてください。'))
        return 0
    legacy_lock = None
    if args.data_dir is None:
        for source in legacy_candidates():
            if source.resolve()==data_dir or not (source/'yami_vault.sqlite3').is_file():continue
            if (data_dir/'yami_vault.sqlite3').exists():
                logging.getLogger('migration').warning('Legacy data retained; current private database is authoritative')
                continue
            if not args.migrate_legacy:
                choice=QMessageBox.question(None,tr('旧版データの引き継ぎ'),tr('このアプリのフォルダーに旧版データが見つかりました。自分のデータなら、タグ・お気に入り・AnalyticsをこのWindowsユーザーの保存先へコピーできます。引き継ぎますか？元データは残ります。'),QMessageBox.StandardButton.Yes|QMessageBox.StandardButton.No,QMessageBox.StandardButton.No)
                if choice!=QMessageBox.StandardButton.Yes:break
            legacy_lock=QLockFile(str(source/'yami_vault.lock'));legacy_lock.setStaleLockTime(0)
            if not legacy_lock.tryLock(100):
                QMessageBox.information(None,'X Archive Gallery',tr('旧版を閉じてから起動してください。お気に入りを安全に引き継ぎます。'))
                return 0
            migrate_legacy(source,data_dir)
            legacy_lock.unlock();legacy_lock=None
            break
    icon = Path(getattr(sys,'_MEIPASS',Path(__file__).parent)) / 'assets' / 'app.ico'
    if icon.is_file():
        app.setWindowIcon(QIcon(str(icon)))
    window = MainWindow(data_dir,args.library)
    app._xag_window=window
    window.show()
    if args.qa:
        import importlib
        importlib.import_module('yamivault.qa').run_qa(window,args.qa)
    if args.qa_import:
        import importlib
        importlib.import_module('yamivault.qa_import').run_import_qa(window,args.qa_import)
    if args.qa_startup:
        import importlib
        importlib.import_module('yamivault.qa_startup').run_startup_qa(window,args.qa_startup)
    if args.qa_onboarding:
        import importlib
        importlib.import_module('yamivault.qa_onboarding').run_onboarding_qa(window,args.qa_onboarding)
    def exception_hook(typ,value,tb):
        logging.getLogger('uncaught').error('Unhandled error',exc_info=(typ,value,tb))
        QMessageBox.warning(getattr(app,'_xag_window',window),tr('処理を完了できませんでした'),friendly_error(value))
    sys.excepthook = exception_hook
    result = app.exec()
    lock.unlock()
    if legacy_lock:
        legacy_lock.unlock()
    return result


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except Exception as error:
        logging.getLogger('startup').exception('Application could not start')
        if os.name == 'nt' and getattr(sys, 'frozen', False):
            import ctypes
            from yamivault.diagnostics import friendly_error
            from yamivault.i18n import tr
            ctypes.windll.user32.MessageBoxW(None, friendly_error(error,'起動'), tr('X Archive Galleryを起動できませんでした'), 0x10)
            sys.exit(1)
        raise
