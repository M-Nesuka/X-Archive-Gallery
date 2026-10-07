"""Release allowlists: never bundle libraries, annotations or generated QA fixtures."""
from pathlib import Path
import re,zipfile

FORBIDDEN_PARTS={'data','cache','warning_media','imports','qa-output','tests','engine_tests','.git','.venv','_tmp_build_env'}
FORBIDDEN_EXT={'.sqlite3','.sqlite','.db','.csv','.tsv','.log','.jpg','.jpeg','.png','.gif','.mp4','.webm','.mov','.zip'}
QA_MODULES={'qa','qa_import','qa_startup','qa_onboarding'}
PUBLIC_TOOLS={'build.py','build_single.py','distribution_guard.py','runtime_audit.py','sign_release.py','package_release.py','package_sources.py','build_poster_ffmpeg.py'}


def source_files(root):
    root=Path(root)
    files=[root/p for p in ('main.py','launcher.py','README.md','LICENSE.md','THIRD_PARTY.md','BUILDING.md','.gitignore','requirements.txt','requirements-dev.txt','使い方.txt','はじめに.txt')]
    files += sorted((root/'docs').glob('*.md'))
    files += sorted((root/'third_party').rglob('*.json'))
    files += [root/'third_party/BUILDING_FFMPEG.md']
    files += [p for p in (root/'third_party/notices').rglob('*') if p.is_file()]
    files += [root/'third_party/ffmpeg-bin/ffmpeg.exe']
    files += sorted((root/'third_party/patches').glob('*.patch'))
    for folder in ('yamivault','backup_engine'):
        files += [p for p in (root/folder).glob('*.py') if p.stem not in QA_MODULES]
    files += [root/'tools'/p for p in sorted(PUBLIC_TOOLS)]
    allowed_assets={'app.ico','licenses/GPL-3.0.txt','licenses/LGPL-3.0.txt'}
    actual_assets={p.relative_to(root/'assets').as_posix() for p in (root/'assets').rglob('*') if p.is_file()}
    if actual_assets != allowed_assets:raise ValueError('Unexpected file in release assets')
    files += [root/'assets'/name for name in sorted(allowed_assets)]
    for file in files:
        text=file.read_text(encoding='utf-8-sig') if file.suffix in {'.py','.md','.txt'} else ''
        if file.relative_to(root).parts[0]!='third_party' and re.search(r'[A-Za-z]:[\\/](?:Users|YAMI-VAULT|X作品バックアップ)',text,re.I):
            raise ValueError('Personal development path detected in public source')
    return sorted(set(files))


def assert_runtime_clean(runtime):
    runtime=Path(runtime)
    roots={'XArchiveGallery.exe','_internal','licenses','使い方.txt','現在の仕様書.txt','build-info.json'}
    for file in runtime.rglob('*'):
        rel=file.relative_to(runtime)
        if file.is_symlink() or getattr(file,'is_junction',lambda:False)():raise ValueError('Runtime contains links')
        legal_notice = rel.parts[:2] == ('licenses','notices')
        if rel.parts[0] not in roots or (not legal_notice and any(p.casefold() in FORBIDDEN_PARTS for p in rel.parts)):raise ValueError('Unexpected runtime content: '+str(rel))
        if not file.is_file():continue
        if rel.parts[:2]==('_internal','assets') and '/'.join(rel.parts[2:]) not in {'app.ico','licenses/GPL-3.0.txt','licenses/LGPL-3.0.txt'}:raise ValueError('Unexpected bundled asset')
        if file.suffix.lower() in FORBIDDEN_EXT:
            if rel.as_posix() not in {'_internal/base_library.zip','licenses/application-source.zip'}:raise ValueError('Forbidden data file: '+str(rel))
        if rel.as_posix()=='licenses/application-source.zip':
            with zipfile.ZipFile(file) as z:
                for name in z.namelist():
                    parts=Path(name).parts
                    legal_notice = parts[:2] == ('third_party','notices')
                    if not legal_notice and (any(p in FORBIDDEN_PARTS for p in parts) or Path(name).stem in QA_MODULES):raise ValueError('Validation data/code in public source')
    required=['XArchiveGallery.exe','_internal/python312.dll','_internal/PySide6/Qt6Core.dll','_internal/PySide6/Qt6Widgets.dll','_internal/PySide6/Qt6Multimedia.dll','_internal/PySide6/plugins/platforms/qwindows.dll','licenses/application-source.zip','licenses/THIRD-PARTY-NOTICES.txt','licenses/FFmpeg-license-and-build.txt']
    for name in required:
        if not (runtime/name).is_file():raise ValueError('Missing release dependency: '+name)
    if list(runtime.rglob('*VirtualKeyboard*')) or list(runtime.rglob('*virtualkeyboard*')):
        raise ValueError('GPL-only Virtual Keyboard is not part of this application')
    posters=list((runtime/'_internal').rglob('ffmpeg*.exe'))
    if not posters:raise ValueError('Missing FFmpeg poster executable')
    required += [p.relative_to(runtime).as_posix() for p in posters]
    for prefix in ('avcodec','avformat','avutil','swresample','swscale'):
        video_dlls=list((runtime/'_internal').rglob(prefix+'*.dll'))
        if not video_dlls:raise ValueError('Missing Qt video dependency: '+prefix)
        required += [p.relative_to(runtime).as_posix() for p in video_dlls]
    return required
