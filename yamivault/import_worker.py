"""Background process, invoked by the same executable. No Qt UI is imported."""
from dataclasses import asdict
import json
import os
from pathlib import Path
import shutil
import time

from backup_engine.archive import analyze, Asset, Issue, Plan, Cancelled, fingerprint
from backup_engine.storage import run_backup


def atomic_json(path, value):
    path = Path(path)
    temp = path.with_suffix('.tmp')
    temp.write_text(json.dumps(value,ensure_ascii=False),encoding='utf-8')
    for attempt in range(30):
        try:
            os.replace(temp,path)
            break
        except PermissionError:
            if attempt == 29:
                raise
            time.sleep(.01)


def load_plan(path):
    data = json.loads(Path(path).read_text(encoding='utf-8'))
    data['fingerprint'] = tuple(data['fingerprint'])
    data['assets'] = [Asset(**a) for a in data['assets']]
    data['issues'] = [Issue(**i) for i in data['issues']]
    return Plan(**data)


def parent_alive(pid):
    if not pid:
        return True
    if os.name == 'nt':
        import ctypes
        from ctypes import wintypes
        kernel=ctypes.WinDLL('kernel32',use_last_error=True)
        kernel.OpenProcess.argtypes=[wintypes.DWORD,wintypes.BOOL,wintypes.DWORD]
        kernel.OpenProcess.restype=wintypes.HANDLE
        kernel.GetExitCodeProcess.argtypes=[wintypes.HANDLE,ctypes.POINTER(wintypes.DWORD)]
        kernel.CloseHandle.argtypes=[wintypes.HANDLE]
        handle=kernel.OpenProcess(0x1000,False,pid)
        if not handle:
            return False
        code=wintypes.DWORD()
        try:
            return bool(kernel.GetExitCodeProcess(handle,ctypes.byref(code))) and code.value==259
        finally:
            kernel.CloseHandle(handle)
    try:
        os.kill(pid,0)
        return True
    except OSError:
        return False


def run(job, action):
    job = Path(job).resolve()
    from .diagnostics import configure_logs
    configure_logs(job.parent.parent)
    request = json.loads((job/'request.json').read_text(encoding='utf-8'))
    last_progress = 0.0
    last_parent_check = 0.0
    alive = True

    def cancelled():
        nonlocal last_parent_check, alive
        if time.monotonic()-last_parent_check > 0.5:
            last_parent_check=time.monotonic()
            alive=parent_alive(request.get('parent_pid'))
        return (job/'cancel').exists() or not alive

    def progress(message, done, total):
        nonlocal last_progress
        now=time.monotonic()
        if now-last_progress < .15 and done != total:
            return
        last_progress=now
        try:
            atomic_json(job/'progress.json',{'message':message,'done':done,'total':total})
        except OSError:
            pass  # A progress display conflict must not fail a verified save.

    try:
        if action=='analyze':
            plan=analyze(request['zip_path'],progress,cancelled)
            atomic_json(job/'plan.json',asdict(plan))
            summary={key:value for key,value in asdict(plan).items() if key not in ('assets','issues')}
            summary.update({'total':len(plan.assets),'total_bytes':plan.total_bytes,
                            'post_ids':sorted({a.post_id for a in plan.assets if a.post_id}),
                            'media_min':min((a.posted_at for a in plan.assets),default=None),
                            'media_max':max((a.posted_at for a in plan.assets),default=None),
                            'warnings':sum(i.level=='注意' for i in plan.issues),
                            'errors':sum(i.level=='エラー' for i in plan.issues),
                            'issues':[asdict(i) for i in plan.issues]})
            atomic_json(job/'result.json',{'action':action,'ok':True,'summary':summary})
        elif action=='backup':
            plan=load_plan(job/'plan.json')
            if tuple(request.get('fingerprint',())) != plan.fingerprint or request['zip_path'] != plan.zip_path:
                raise ValueError('解析情報が一致しません。ZIPを選び直してください。')
            if fingerprint(plan.zip_path)!=plan.fingerprint:
                raise ValueError('解析後にZIPが変更されました。ZIPを選び直してください。')
            root=Path(request['root']).resolve()
            if job.is_relative_to(root):
                raise ValueError('バックアップ先とアプリ独自データの保存先を分けてください。')
            if request.get('destination_has_catalog') and not (root/'.system/catalog.sqlite3').is_file():
                raise ValueError('既存のバックアップのカタログが見つかりません。ドライブと保存先を確認してください。')
            from yamivault.import_destination import validate_destination
            root=validate_destination(root,request.get('private_data_dir',str(job)))
            # The user confirmed this destination with the Start Import button.
            # Analysis alone must never create a backup folder or catalog.
            root.mkdir(parents=True,exist_ok=True)
            reserve=max(64*1024**2,int(plan.total_bytes*.02))
            if shutil.disk_usage(root).free < plan.total_bytes+reserve:
                raise ValueError('空き容量が不足しています。保存済みの作品は変更していません。')
            result=run_backup(plan,str(root.parent),progress,cancelled,root_override=root,run_id=request['run_id'])
            status='cancelled' if result.cancelled else ('errors' if result.errors else ('warnings' if result.warnings else 'complete'))
            atomic_json(job/'result.json',{'action':action,'ok':True,'status':status,
                        'run_id':request['run_id'],'result':asdict(result)})
        else:
            raise ValueError('Unknown worker action')
    except Cancelled:
        atomic_json(job/'result.json',{'action':action,'ok':False,'cancelled':True,'error':'中止しました。'})
    except Exception as exc:
        from .diagnostics import friendly_error
        import logging
        logging.getLogger(__name__).exception('Import worker failed')
        atomic_json(job/'result.json',{'action':action,'ok':False,'error':friendly_error(exc,'アーカイブ取り込み')})
    return 0
