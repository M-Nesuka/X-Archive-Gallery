"""Build the one-EXE distribution from the tested, dynamically linked runtime."""
from pathlib import Path
import hashlib
import json
import runpy
import subprocess
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[1]
VERSION = runpy.run_path(str(ROOT/'yamivault/version.py'))['__version__']
if '--runtime-ready' not in sys.argv:
    subprocess.run([sys.executable, str(ROOT/'tools/build.py')], cwd=ROOT, check=True)
runtime = ROOT/'releases'/('v'+VERSION)/'XArchiveGallery'
output = ROOT/'single-build'
output.mkdir(exist_ok=True)
from distribution_guard import source_files,assert_runtime_clean
public_sources=source_files(ROOT)
with zipfile.ZipFile(runtime/'licenses/application-source.zip', 'w', zipfile.ZIP_DEFLATED) as z:
    for file in public_sources:
        z.write(file, file.relative_to(ROOT))
for name in ('使い方.txt',):
    (runtime/name).write_bytes((ROOT/name).read_bytes())
for license_file in (ROOT/'assets/licenses').glob('*.txt'):
    (runtime/'licenses'/license_file.name).write_bytes(license_file.read_bytes())
spec = ROOT/'docs'/('X_Archive_Gallery_現在仕様_v'+VERSION+'.txt')
if spec.exists():
    (runtime/'現在の仕様書.txt').write_bytes(spec.read_bytes())
required_files=assert_runtime_clean(runtime)
from runtime_audit import audit_dependencies,inventory
dependency_report=audit_dependencies(runtime)
if dependency_report['unresolved']:
    raise RuntimeError('Unresolved runtime DLLs: '+str(dependency_report['unresolved']))
(runtime/'licenses/runtime-dependencies.json').write_text(json.dumps(dependency_report,indent=2),encoding='utf-8')
# File hashes make the exact third-party binaries and release inputs identifiable.
(runtime/'licenses/runtime-inventory.json').write_text(json.dumps(inventory(runtime),indent=2),encoding='utf-8')
payload = output/'runtime-payload.zip'
with zipfile.ZipFile(payload, 'w', zipfile.ZIP_DEFLATED, compresslevel=9) as z:
    for file in sorted(runtime.rglob('*')):
        if file.is_file():
            assert file.suffix.lower() not in ('.sqlite3', '.sqlite', '.log')
            z.write(file, file.relative_to(runtime))
manifest = {'version': VERSION, 'payload_sha256': hashlib.file_digest(payload.open('rb'), 'sha256').hexdigest(),
            'exe_sha256': hashlib.file_digest((runtime/'XArchiveGallery.exe').open('rb'), 'sha256').hexdigest(),
            'required_files': required_files}
(output/'runtime-manifest.json').write_text(json.dumps(manifest, indent=2), encoding='utf-8')
# Both the launcher and gallery have meaningful Windows version metadata and an icon.
version_info = output/'windows-version.txt'
version_numbers=tuple(map(int,VERSION.split('.')))+(0,)
version_info.write_text(f'''VSVersionInfo(ffi=FixedFileInfo(filevers={version_numbers}, prodvers={version_numbers}, mask=0x3f, flags=0x0, OS=0x40004, fileType=0x1, subtype=0x0, date=(0,0)), kids=[StringFileInfo([StringTable('040904b0',[StringStruct('FileDescription','X Archive Gallery'),StringStruct('FileVersion','{VERSION}'),StringStruct('ProductName','X Archive Gallery'),StringStruct('ProductVersion','{VERSION}'),StringStruct('OriginalFilename','XArchiveGallery.exe')])]),VarFileInfo([VarStruct('Translation',[1033,1200])])])''', encoding='utf-8')
subprocess.run([sys.executable, '-m', 'PyInstaller', '--noconfirm', '--clean', '--onefile', '--windowed',
                '--name', 'XArchiveGallery', '--icon', str(ROOT/'assets/app.ico'),
                '--version-file', str(version_info),
                '--add-data', str(payload)+';.', '--add-data', str(output/'runtime-manifest.json')+';.',
                '--distpath', str(output/'dist'), '--workpath', str(output/'work'),
                '--specpath', str(output), str(ROOT/'launcher.py')], cwd=ROOT, check=True)
print('Single executable:', output/'dist/XArchiveGallery.exe')

from sign_release import optional_sign
optional_sign(output/'dist/XArchiveGallery.exe')
