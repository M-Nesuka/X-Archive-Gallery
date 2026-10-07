"""Background CSV preview/import; all performance data stays in the private DB."""
from .i18n import tr,trf
from pathlib import Path
import logging
from PySide6.QtCore import QObject,QRunnable,Signal
from .analytics import preview_analytics_csv


class AnalyticsSignals(QObject):
    done=Signal(object,str)


class AnalyticsJob(QRunnable):
    def __init__(self,path,assets,*,directory=None,root=None,expected_hash=None,keep_csv=False):
        super().__init__()
        self.path=Path(path);self.assets=list(assets)
        self.directory=directory;self.root=root;self.expected_hash=expected_hash
        self.keep_csv=keep_csv
        self.signals=AnalyticsSignals()

    def run(self):
        store=None
        try:
            preview=preview_analytics_csv(self.path,self.assets)
            if self.directory is None:
                self.signals.done.emit(preview,'');return
            if preview.file_sha256!=self.expected_hash:
                raise ValueError(tr('選択後にCSVの内容が変わりました。CSVを選び直してください。'))
            if not preview.can_import:
                raise ValueError(tr('CSVに入力不備または投稿ID重複があります。CSVを選び直してください。'))
            saved_csv=None
            if self.keep_csv:
                from .analytics_files import save_analytics_csv
                saved_csv=save_analytics_csv(preview,self.root)
            from .store import VaultStore
            store=VaultStore(self.directory)
            library_id=store.library(self.root)
            repeated=store.analytics_hash_imported(library_id,preview.file_sha256)
            if repeated:
                store.reconcile_analytics(library_id,self.assets)
                summary=store.analytics_summary(library_id)
            else:
                summary=store.import_analytics(library_id,preview,self.assets)
            self.signals.done.emit({'summary':summary,'repeated':repeated,'root':str(self.root),
                                   'saved_csv':str(saved_csv) if saved_csv else None},'')
        except Exception as error:
            logging.getLogger(__name__).exception('Analytics task failed')
            from .diagnostics import friendly_error
            self.signals.done.emit(None,friendly_error(error,tr('Analytics取り込み')))
        finally:
            if store:store.close()
