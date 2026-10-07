"""Build the portable X Archive Gallery release."""
from pathlib import Path
import importlib.metadata
import json
import shutil
import subprocess
import sys
import runpy
import os

from PIL import Image, ImageDraw, ImageFont

ROOT=Path(__file__).resolve().parents[1]
VERSION=runpy.run_path(str(ROOT/'yamivault/version.py'))['__version__']
poster=ROOT/'third_party/ffmpeg-bin/ffmpeg.exe'
poster_manifest=ROOT/'third_party/ffmpeg-bin/manifest.json'
if not poster.is_file() or not poster_manifest.is_file():
    raise RuntimeError('Use the audited poster build described in BUILDING.md before building the app.')
import hashlib
poster_info=json.loads(poster_manifest.read_text(encoding='utf8'))
if hashlib.file_digest(poster.open('rb'),'sha256').hexdigest()!=poster_info['sha256']:
    raise RuntimeError('Audited FFmpeg hash mismatch')
DIST=ROOT/'releases'/f'v{VERSION}'
if list(DIST.rglob('yami_vault.sqlite3')) if DIST.exists() else False:
    raise RuntimeError('Build target contains user data. Refusing to replace it.')
assets=ROOT/'assets'
assets.mkdir(exist_ok=True)
image=Image.new('RGBA',(256,256),'#101014')
d=ImageDraw.Draw(image)
d.rounded_rectangle((9,9,247,247),radius=52,fill='#17121f')
font=ImageFont.truetype(str(Path(os.environ['WINDIR'])/'Fonts'/'georgia.ttf'),124)
bbox=d.textbbox((0,0),'X',font=font)
d.text(((256-bbox[2])/2,(256-(bbox[3]-bbox[1]))/2-bbox[1]),'X',font=font,fill='#c9aff3')
image.save(assets/'app.ico',sizes=[(16,16),(24,24),(32,32),(48,48),(64,64),(128,128),(256,256)])
subprocess.run([sys.executable,'-m','PyInstaller','--noconfirm','--clean','--windowed','--name','XArchiveGallery',
                '--icon',str(assets/'app.ico'),'--add-data',str(assets)+';assets',
                '--hidden-import','PySide6.QtTest','--exclude-module','yamivault.qa','--exclude-module','yamivault.qa_import','--exclude-module','yamivault.qa_startup','--exclude-module','yamivault.qa_onboarding','--collect-data','imageio_ffmpeg','--hidden-import','ijson.backends.yajl2_c','--exclude-module','PySide6.QtWebEngineCore',
                '--exclude-module','PySide6.QtWebEngineWidgets','--distpath',str(DIST),
                '--workpath',str(ROOT/f'build-v{VERSION}'),str(ROOT/'main.py')],cwd=ROOT,check=True)
release=DIST/'XArchiveGallery'
internal=release/'_internal'
# PyInstaller collects unused GUI plugins. Never ship GPL-only Virtual Keyboard.
for relative in ('PySide6/plugins/platforminputcontexts/qtvirtualkeyboardplugin.dll','PySide6/Qt6VirtualKeyboard.dll',
                 'PySide6/plugins/imageformats/qpdf.dll','PySide6/Qt6Pdf.dll'):
    (internal/relative).unlink(missing_ok=True)
# Preserve the package's resolver filename, while replacing its unrelated Gyan build.
posters=list((internal/'imageio_ffmpeg/binaries').glob('ffmpeg*.exe'))
if len(posters)!=1:raise RuntimeError('Unexpected imageio FFmpeg binary layout')
shutil.copy2(poster,posters[0])
icu=internal/'icuuc.dll'
if icu.exists():
    import pefile
    consumers=[]
    for path in internal.rglob('*'):
        if path.suffix.lower() not in ('.dll','.pyd'):
            continue
        pe=pefile.PE(str(path),fast_load=True)
        pe.parse_data_directories(directories=[1])
        for entry in getattr(pe,'DIRECTORY_ENTRY_IMPORT',[]):
            if entry.dll.lower()==b'icuuc.dll':
                if any(i.name and i.name.endswith(b'_78') for i in entry.imports):
                    raise RuntimeError('Unexpected consumer requires ICU 78')
                consumers.append(str(path.relative_to(internal)))
        pe.close()
    if consumers != ['PySide6\\Qt6Core.dll']:
        raise RuntimeError(f'Unexpected ICU consumers: {consumers}')
    # This Qt build imports the unversioned Windows ICU API. ICU 78 exports
    # version-suffixed symbols and cannot satisfy those imports. Supported
    # Windows installs provide the API through System32/icuuc.dll -> icu.dll.
    icu.unlink()
icu_data=internal/'icudt78.dll'
removed=[]
if icu_data.exists():
    # PyInstaller can collect the build-host ICU data through its DLL search
    # path, even though the matching ICU 78 code is not used by this runtime.
    # Fail closed if a future dependency starts importing this data DLL.
    for path in internal.rglob('*'):
        if path.suffix.lower() not in ('.dll','.pyd','.exe') or path==icu_data:
            continue
        pe=pefile.PE(str(path),fast_load=True)
        try:
            pe.parse_data_directories(directories=[1,13])
            imports=list(getattr(pe,'DIRECTORY_ENTRY_IMPORT',[]))+list(getattr(pe,'DIRECTORY_ENTRY_DELAY_IMPORT',[]))
            if any(entry.dll.lower()==b'icudt78.dll' for entry in imports):
                raise RuntimeError('Runtime requires ICU 78 data: '+str(path.relative_to(internal)))
        finally:
            pe.close()
    if (internal/'icuuc.dll').exists():
        raise RuntimeError('Cannot remove ICU data while its code DLL exists')
    removed.append({'file':'_internal/icudt78.dll','bytes':icu_data.stat().st_size,'reason':'no ICU 78 consumer'})
    icu_data.unlink()
shutil.copy2(ROOT/'使い方.txt',release/'使い方.txt')
licenses=release/'licenses'
licenses.mkdir(exist_ok=True)
shutil.copytree(ROOT/'third_party/notices',licenses/'notices',dirs_exist_ok=True)
shutil.copy2(ROOT/'LICENSE.md',licenses/'APPLICATION-LICENSE.md')
shutil.copy2(ROOT/'THIRD_PARTY.md',licenses/'THIRD_PARTY.md')
shutil.copy2(ROOT/'third_party/source-manifest.json',licenses/'source-manifest.json')
shutil.copy2(ROOT/'docs/LIBRARY_REPLACEMENT.md',licenses/'LIBRARY_REPLACEMENT.md')
packages=['PySide6','PySide6_Essentials','PySide6_Addons','shiboken6','Pillow','imageio-ffmpeg','ijson','PyInstaller']
for package in packages:
    dist=importlib.metadata.distribution(package)
    for file in dist.files or []:
        path=Path(str(file))
        if ('license' in str(path).lower() or path.name.lower() in ('copying','notice','copyright')) and path.suffix.lower() not in ('.py','.pyc','.dll','.exe','.pyd'):
            source=Path(dist.locate_file(file))
            if source.is_file():
                target=licenses/package/path
                target.parent.mkdir(parents=True,exist_ok=True)
                shutil.copy2(source,target)
python_license=Path(sys.base_prefix)/'LICENSE.txt'
if python_license.is_file():
    shutil.copy2(python_license,licenses/'Python-LICENSE.txt')
shutil.copy2(ROOT/'third_party/notices/THIRD-PARTY-NOTICES.txt',licenses/'THIRD-PARTY-NOTICES.txt')
(release/'build-info.json').write_text(json.dumps({'application':'X Archive Gallery','version':VERSION,'author':'M.Nesuka','python':sys.version,'dependencies':{p:importlib.metadata.version(p) for p in packages},'license_metadata':{p:importlib.metadata.metadata(p).get('License','See bundled notices') for p in packages},'removed_unused_files':removed},indent=2),encoding='utf-8')
print('Release ready:',release)

import imageio_ffmpeg
license_text=subprocess.run([str(poster),'-L'],capture_output=True,
    creationflags=subprocess.CREATE_NO_WINDOW,text=True,encoding='utf-8',errors='replace',check=True)
(licenses/'FFmpeg-license-and-build.txt').write_text(license_text.stdout+'\n'+license_text.stderr,encoding='utf-8')




from sign_release import optional_sign
optional_sign(release/'XArchiveGallery.exe')
