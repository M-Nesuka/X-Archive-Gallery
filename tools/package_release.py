"""Package the verified runtime using explicit, consumer-only input files."""
from pathlib import Path
import hashlib,json,runpy,zipfile
from distribution_guard import assert_runtime_clean

ROOT=Path(__file__).resolve().parents[1]
VERSION=runpy.run_path(str(ROOT/'yamivault/version.py'))['__version__']
runtime=ROOT/'releases'/('v'+VERSION)/'XArchiveGallery'
assert_runtime_clean(runtime)
out=ROOT/'delivery'
out.mkdir(exist_ok=True)
exe=ROOT/'single-build/dist/XArchiveGallery.exe'
inputs={Path('XArchiveGallery.exe'):exe,Path('はじめに.txt'):ROOT/'はじめに.txt',Path('使い方.txt'):ROOT/'使い方.txt',Path('LICENSE.md'):ROOT/'LICENSE.md',Path('THIRD_PARTY.md'):ROOT/'THIRD_PARTY.md'}
for p in sorted((runtime/'licenses').rglob('*')):
    if p.is_file():inputs[Path('licenses')/p.relative_to(runtime/'licenses')]=p
# Same hashes and dependency versions available outside the EXE for maintainers.
inputs[Path('licenses/build-info.json')]=runtime/'build-info.json'
checksum=out/'チェックサム.txt'
checksum.write_text('\n'.join(hashlib.file_digest(p.open('rb'),'sha256').hexdigest()+'  '+name.as_posix()
    for name,p in inputs.items())+'\n',encoding='utf-8-sig')
inputs[Path('チェックサム.txt')]=checksum
archive=out/f'XArchiveGallery_v{VERSION}_Windows_x64.zip'
with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED,compresslevel=9) as z:
    for name,p in inputs.items():z.write(p,'XArchiveGallery/'+name.as_posix())
with zipfile.ZipFile(archive) as z:
    assert z.testzip() is None
    assert set(z.namelist())=={'XArchiveGallery/'+n.as_posix() for n in inputs}
    for name,p in inputs.items():assert z.read('XArchiveGallery/'+name.as_posix())==p.read_bytes()
    for name in z.namelist():
        if Path(name).suffix.casefold() in {'.csv','.sqlite3','.sqlite','.db','.jpg','.png','.gif','.mp4','.webm','.log'}:
            raise ValueError('Unexpected private/test file in public package')
digest=hashlib.file_digest(archive.open('rb'),'sha256').hexdigest()
(out/'SHA256SUMS.txt').write_text(digest+'  '+archive.name+'\n'+hashlib.file_digest(exe.open('rb'),'sha256').hexdigest()+'  XArchiveGallery.exe\n',encoding='utf-8')
(out/'package-verification.json').write_text(json.dumps({'zip':archive.name,'bytes':archive.stat().st_size,
    'sha256':digest,'files':len(inputs),'crc_verified':True,'every_input_byte_verified':True,
    'private_data_included':False},indent=2),encoding='utf-8')
print('Verified package:',archive.name,archive.stat().st_size,digest,flush=True)
