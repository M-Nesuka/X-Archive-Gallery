"""Switch language by safely rebuilding the window, without restarting a process."""
from PySide6.QtGui import QActionGroup
from PySide6.QtWidgets import QApplication
from .i18n import tr,set_language_code

class LanguageMixin:
    def build_language_menu(self,menu):
        languages=menu.addMenu('言語 / Language')
        languages.setObjectName('languageMenu')
        self.language_actions={};group=QActionGroup(languages);group.setExclusive(True)
        for code,title in (('ja','日本語'),('en','English')):
            action=languages.addAction(title);action.setCheckable(True)
            action.setChecked(self.ui_language==code);group.addAction(action)
            action.triggered.connect(lambda checked=False,c=code:self.set_ui_language(c))
            self.language_actions[code]=action
        self.language_group=group

    def set_ui_language(self,code):
        if code not in ('ja','en') or code==self.ui_language:return
        if self.loading or self.importer.active or self.import_panel.analytics_busy or self.import_panel.preview_busy:
            self.language_actions[self.ui_language].setChecked(True)
            self.toast(tr('読み込み・取り込みが終わってから切り替えられます。'));return
        # This avoids duplicate per-widget translations and preserves stable enum/tag keys.
        self.store.set('ui_language',code)
        directory=self.store.directory;root=self.root if self.library_configured else None
        geometry=self.saveGeometry();state=self.windowState()
        app=QApplication.instance();quit_on_close=app.quitOnLastWindowClosed()
        app.setQuitOnLastWindowClosed(False)
        old_code=self.ui_language
        try:
            self.close()
            replacement=type(self)(directory,root)
            replacement.restoreGeometry(geometry);replacement.setWindowState(state)
            app._xag_window=replacement
            replacement.show()
            self._language_replacement=replacement
            self.deleteLater()
        except Exception:
            # Leave the same library and data accessible even if rebuilding fails.
            from .store import VaultStore
            store=VaultStore(directory);store.set('ui_language',old_code);store.close()
            set_language_code(old_code)
            replacement=type(self)(directory,root);app._xag_window=replacement;replacement.show()
            self.deleteLater()
            raise
        finally:app.setQuitOnLastWindowClosed(quit_on_close)
