"""Import state machine and process ownership; gallery never calls storage writes."""
from .i18n import tr,trf
import json
import logging
import os
from pathlib import Path
import sys
import uuid

from PySide6.QtCore import QObject, QProcess, QTimer, Signal


class ImportController(QObject):
    changed = Signal()
    completed = Signal(object)
    activity = Signal(bool)

    def __init__(self, store, parent=None):
        super().__init__(parent)
        self.store=store
        self.phase='idle'
        self.message=tr('ZIPを選ぶと、保存前に内容を確認できます。')
        self.summary={}
        self.result={}
        self.job=None
        self.root=None
        self.progress=(0,0)
        self.cancel_requested=False
        self.process=QProcess(self)
        self.process.finished.connect(self.finished)
        self.process.errorOccurred.connect(self.process_error)
        self.timer=QTimer(self)
        self.timer.setInterval(150)
        self.timer.timeout.connect(self.poll)
        self.job_id=None
        self.recovered=store.recover_imports()
        if self.recovered:
            self.message=tr('前回の取り込み記録を確認しました。未完了の場合は同じZIPで再実行してください。')

    @property
    def active(self):
        return self.phase in ('analyzing','importing')

    def reset(self):
        if self.active:
            return
        self.phase='idle'
        self.message=tr('ZIPを選ぶと、保存前に内容を確認できます。')
        self.summary={}
        self.result={}
        self.job=None
        self.job_id=None
        self.root=None
        self.request={}
        self.changed.emit()

    def analyze(self, zip_path, root):
        if self.active:
            return
        from .import_destination import validate_destination
        root = validate_destination(root, self.store.directory)
        logging.getLogger(__name__).info('Archive analysis requested')
        self.job_id=uuid.uuid4().hex
        self.job=self.store.directory/'imports'/self.job_id
        self.job.mkdir(parents=True)
        self.root=root
        self.summary={}
        self.result={}
        self.request={'zip_path':str(Path(zip_path).resolve()),'root':str(self.root),
                      'run_id':self.job_id,'parent_pid':os.getpid(),
                      'private_data_dir':str(self.store.directory),
                      'destination_has_catalog':(self.root/'.system/catalog.sqlite3').is_file()}
        self.phase='analyzing'
        self.launch('analyze')

    def change_destination(self, root):
        if self.phase != 'ready':
            return False
        from .import_destination import validate_destination
        candidate = validate_destination(root, self.store.directory)
        from .accounts import route_destination
        self.root = route_destination(self.store,candidate,self.summary)
        self.request['root'] = str(self.root)
        self.request['destination_has_catalog'] = (self.root/'.system/catalog.sqlite3').is_file()
        self.store.save_import(self.job_id,self.root,self.phase,self.summary,self.result)
        self.changed.emit()
        return True

    def start_backup(self):
        if self.phase!='ready' or not self.summary.get('total'):
            return
        library=self.store.library(self.root)
        known=self.store.get('account:'+library)
        owner=self.summary.get('owner')
        if known and owner and known!=owner:
            self.message=tr('このZIPは別のアカウントです。ライブラリを選び直してください。')
            self.changed.emit()
            return
        self.request['fingerprint']=self.summary['fingerprint']
        self.phase='importing'
        self.launch('backup')

    def launch(self, action):
        self.action=action
        self.cancel_requested=False
        self.progress=(0,0)
        self.message=tr('アーカイブを解析しています…') if action=='analyze' else tr('作品を保存しています…')
        for name in ('result.json','progress.json','cancel'):
            (self.job/name).unlink(missing_ok=True)
        (self.job/'request.json').write_text(json.dumps(self.request,ensure_ascii=False),encoding='utf-8')
        self.store.save_import(self.job_id,self.root,self.phase,self.summary,{})
        if getattr(sys,'frozen',False):
            program=sys.executable
            args=['--import-worker',str(self.job),'--worker-action',action]
        else:
            program=sys.executable
            args=[str(Path(__file__).resolve().parents[1]/'main.py'),'--import-worker',str(self.job),'--worker-action',action]
        self.process.setProgram(program)
        self.process.setArguments(args)
        self.process.setStandardOutputFile(str(self.job/'worker-stdout.log'))
        self.process.setStandardErrorFile(str(self.job/'worker-stderr.log'))
        from PySide6.QtCore import QProcessEnvironment
        environment=QProcessEnvironment.systemEnvironment()
        environment.insert('PYINSTALLER_RESET_ENVIRONMENT','1')
        self.process.setProcessEnvironment(environment)
        self.activity.emit(True)
        self.changed.emit()
        self.timer.start()
        self.process.start()

    def cancel(self):
        if self.active:
            (self.job/'cancel').touch()
            self.cancel_requested=True
            self.message=tr('安全に中止しています。保存済みの作品は残ります。')
            self.changed.emit()

    def poll(self):
        try:
            value=json.loads((self.job/'progress.json').read_text(encoding='utf-8'))
            if not self.cancel_requested:
                self.message=value['message']
            self.progress=(value['done'],value['total'])
            self.changed.emit()
        except (OSError,ValueError,KeyError):
            pass

    def process_error(self, error):
        if error==QProcess.ProcessError.FailedToStart and self.active:
            self.finish_payload({'ok':False,'error':tr('取り込み処理を起動できません。')+self.process.errorString()})

    def finished(self, code, status):
        if not self.active:
            return
        try:
            value=json.loads((self.job/'result.json').read_text(encoding='utf-8'))
        except (OSError,ValueError):
            value={'ok':False,'error':tr('処理の完了を確認できません。同じZIPを選び直して再実行してください。')}
        if code!=0 or status!=QProcess.ExitStatus.NormalExit:
            value={'ok':False,'error':tr('取り込み処理が途中で終了しました。保存済み作品は保持されています。再実行してください。')}
        self.finish_payload(value)

    def finish_payload(self, value):
        importing=self.action=='backup'
        self.timer.stop()
        self.result=value
        logging.getLogger(__name__).info('Archive action %s finished: ok=%s',self.action,value.get('ok'))
        if not value.get('ok'):
            self.phase='cancelled' if value.get('cancelled') else 'error'
            self.message=value.get('error',tr('処理を完了できませんでした。'))
        elif not importing:
            self.summary=value['summary']
            self.phase='ready'
            try:
                from .accounts import route_destination
                self.root=route_destination(self.store,self.root,self.summary)
                self.request['root']=str(self.root)
                self.request['destination_has_catalog']=(self.root/'.system/catalog.sqlite3').is_file()
            except (OSError,ValueError) as exc:
                self.phase='error';self.message=str(exc)
            if self.phase=='ready':
                self.message=tr('解析完了。@ユーザー名と保存先を確認して「取り込み開始」を押してください。')
                if not self.summary['total']:
                    self.message=tr('保存できる対象がありません。確認事項をご覧ください。')
        else:
            self.phase=value['status']
            titles={'complete':tr('取り込みが完了しました。'),'warnings':tr('取り込みが完了しました（注意あり）。'),
                    'errors':tr('一部を保存できませんでした。確認事項をご覧ください。'),'cancelled':tr('中止しました。保存済み作品は残っています。')}
            self.message=titles.get(self.phase,tr('処理が終了しました。'))
            if self.phase in ('complete','warnings'):
                from .accounts import register_account
                register_account(self.store,self.root,self.summary,completed=True)
        self.store.save_import(self.job_id,self.root,self.phase,self.summary,value)
        self.activity.emit(False)
        self.changed.emit()
        if importing:
            self.completed.emit(value)
