"""Small privacy-preserving diagnostics and actionable Japanese errors."""
from __future__ import annotations
import json,logging,os,platform,re,traceback,zipfile
from logging.handlers import RotatingFileHandler
from pathlib import Path
from .version import __version__
from .i18n import tr,language


def redact(text):
    text=str(text)
    # Full paths (including spaces), URLs and long account/post identifiers are unnecessary.
    text=re.sub(r'[A-Za-z]:[\\/][^\r\n\"\']*', '[path]',text)
    text=re.sub(r'\\\\[^\r\n\"\']*','[path]',text)
    text=re.sub(r'https?://\S+','[url]',text)
    text=re.sub(r'(?<!\d)\d{15,}(?!\d)','[id]',text)
    return text


class PrivateFormatter(logging.Formatter):
    def formatException(self,info):
        typ,_value,tb=info
        # Never include exception text, source lines, locals or absolute source paths.
        frames=traceback.extract_tb(tb)
        return '\n'.join([typ.__name__]+[f'{Path(f.filename).name}:{f.lineno} {f.name}' for f in frames])
    def format(self,record):
        return redact(super().format(record))


def configure_logs(data):
    logs=Path(data)/'logs';logs.mkdir(parents=True,exist_ok=True)
    handler=RotatingFileHandler(logs/f'session-{os.getpid()}.log',maxBytes=1_000_000,backupCount=2,encoding='utf-8')
    handler.setFormatter(PrivateFormatter('%(asctime)s %(levelname)s %(name)s %(message)s'))
    logger=logging.getLogger();logger.setLevel(logging.INFO)
    logger.addHandler(handler)
    logger.info('X Archive Gallery %s %s %s',__version__,platform.system(),platform.machine())
    for old in sorted(logs.glob('session-*.log*'),key=lambda p:p.stat().st_mtime,reverse=True)[30:]:
        try:old.unlink()
        except OSError:pass
    return handler


def friendly_error(error,action='処理'):
    if language()=='en':
        action=tr(action)
        if isinstance(error,PermissionError):return action+tr('を実行できません。書き込み権限がある保存先を選び、他のアプリがファイルを使用していないか確認してください。')
        if isinstance(error,FileNotFoundError):return action+tr('に必要なファイルが見つかりません。ドライブの接続と保存場所を確認し、ファイルを選び直してください。')
        if isinstance(error,OSError) and getattr(error,'errno',None)==28:return tr('空き容量が不足しています。保存先の空き容量を確保してから再実行してください。')
        if 'database is locked' in str(error):return tr('データが他の処理で使用されています。取り込みや他のアプリが終了してから再実行してください。')
        if action.startswith(('起動','Startup')):return tr('起動できませんでした。ドライブ・空き容量・保存先の権限を確認して再試行してください。続く場合は%LOCALAPPDATA%\\XArchiveGallery\\data\\logsのログを添えて報告してください。DBは削除せず保管してください。')
        if isinstance(error,ValueError) and tr(str(error))!=str(error):return tr(str(error))
        return action+tr('を完了できませんでした。保存先と空き容量を確認して再実行してください。続く場合は設定の「不具合報告用ログを保存」からログを保存してください。')
    if isinstance(error,PermissionError):
        return action+'を実行できません。書き込み権限がある保存先を選び、他のアプリがファイルを使用していないか確認してください。'
    if isinstance(error,FileNotFoundError):
        return action+'に必要なファイルが見つかりません。ドライブの接続と保存場所を確認し、ファイルを選び直してください。'
    if isinstance(error,OSError) and getattr(error,'errno',None)==28:
        return '空き容量が不足しています。保存先の空き容量を確保してから再実行してください。'
    text=str(error)
    if isinstance(error,ValueError) and re.search(r'[ぁ-んァ-ン一-龯]',text):
        return text
    if 'database is locked' in text:
        return 'データが他の処理で使用されています。取り込みや他のアプリが終了してから再実行してください。'
    if action.startswith('起動'):
        return '起動できませんでした。ドライブ・空き容量・保存先の権限を確認して再試行してください。続く場合は%LOCALAPPDATA%\\XArchiveGallery\\data\\logsのログを添えて報告してください。DBは削除せず保管してください。'
    return action+'を完了できませんでした。保存先と空き容量を確認して再実行してください。続く場合は設定の「不具合報告用ログを保存」からログを保存してください。'


def export_report(data,destination):
    data=Path(data).resolve();target=Path(destination).resolve()
    if target.suffix.casefold()!='.zip' or target.is_relative_to(data):raise ValueError('Save a ZIP outside application data')
    logs=data/'logs'
    files=[p for p in sorted(logs.glob('session-*.log*')) if p.is_file() and not p.is_symlink()]
    if any(target==p.resolve() for p in files):raise OSError('Choose another destination')
    with zipfile.ZipFile(target,'w',zipfile.ZIP_DEFLATED) as archive:
        archive.writestr('environment.json',json.dumps({'application':'X Archive Gallery','version':__version__,'system':platform.system(),'architecture':platform.machine()},ensure_ascii=False,indent=2))
        for file in files:
            archive.writestr('logs/'+file.name,redact(file.read_text(encoding='utf-8',errors='replace')))
