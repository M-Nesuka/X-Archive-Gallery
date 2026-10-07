"""Package the exact third-party archives supplied with the matching app Release."""
from pathlib import Path
import argparse,hashlib,json,zipfile

ROOT=Path(__file__).resolve().parents[1]
parser=argparse.ArgumentParser()
parser.add_argument('--sources',type=Path,required=True,help='Folder containing original archives listed in source-manifest.json')
parser.add_argument('--output',type=Path,default=ROOT/'delivery')
args=parser.parse_args()
manifest=json.loads((ROOT/'third_party/source-manifest.json').read_text(encoding='utf8'))
inputs={Path('source-manifest.json'):ROOT/'third_party/source-manifest.json',
        Path('tools/build_poster_ffmpeg.py'):ROOT/'tools/build_poster_ffmpeg.py',
        Path('patches/ffmpeg-windows-response-files.patch'):ROOT/'third_party/patches/ffmpeg-windows-response-files.patch',
        Path('LICENSE.LGPL-2.1.txt'):ROOT/'third_party/notices/LGPL-2.1.txt',
        Path('BUILDING.md'):ROOT/'third_party/BUILDING_FFMPEG.md',
        Path('Qt-FFmpeg-build.txt'):ROOT/'third_party/notices/Qt-FFmpeg-build.txt',
        Path('Poster-FFmpeg-build.txt'):ROOT/'third_party/notices/Poster-FFmpeg-build.txt'}
for row in manifest['sources']:
    path=args.sources/row['file']
    with path.open('rb') as stream:assert hashlib.file_digest(stream,'sha256').hexdigest()==row['sha256'],row['file']
    inputs[Path(row['source_path'])]=path
readme='''# Matching third-party sources — X Archive Gallery v1.5.0

Keep this asset publicly downloadable alongside the Windows app ZIP in the same
v1.5.0 GitHub Release, at no extra cost or restricted access.
These are original upstream sources, not M.Nesuka application code. Their own
copyright notices and licenses apply. The application Source Available license
does not apply to this bundle. The dedicated poster build recipe and build-only
patch are supplied under LGPL-2.1-or-later.

source-manifest.json identifies every archive and its SHA-256/upstream location.
Extract the original source archives as needed; each contains its license notices.
The original Qt module and pyside-setup sources are unmodified. qt5's v6.11.2
archive contains coin/provisioning Windows build scripts, including the exact
FFmpeg n7.1.5 script. The Qt FFmpeg tag archive hash matches that script.

To rebuild the separate static LGPL poster, use BUILDING.md and the included
tools/build_poster_ffmpeg.py. Pass the extracted bundle's sources directory as
--sources. Install the documented compiler, GNU Make, pkgconf, POSIX shell,
Python, Meson and Ninja first. The recipe needs only ffmpeg-7.1.5.tar.xz,
dav1d-1.5.1.tar.xz and zlib-1.3.1.tar.gz; it applies the documented build fix.

Qt/PySide and other original sources use their own upstream build instructions.
The bundle does not claim byte-identical upstream builds or include proprietary
compiler installers. Library replacement rights and instructions are provided
in the app's licenses/LIBRARY_REPLACEMENT.md.
'''
args.output.mkdir(parents=True,exist_ok=True)
archive=args.output/'XArchiveGallery_v1.5.0_ThirdPartySources.zip'
with zipfile.ZipFile(archive,'w',zipfile.ZIP_STORED) as z:
    z.writestr('README.md',readme)
    for name,path in sorted(inputs.items()):z.write(path,name.as_posix())
with zipfile.ZipFile(archive) as z:
    assert z.testzip() is None
    assert set(z.namelist())=={'README.md',*(name.as_posix() for name in inputs)}
    for name,path in inputs.items():
        with z.open(name.as_posix()) as stream:actual=hashlib.file_digest(stream,'sha256').hexdigest()
        with path.open('rb') as stream:assert actual==hashlib.file_digest(stream,'sha256').hexdigest(),name
print('Verified third-party source asset:',archive.name,archive.stat().st_size,flush=True)
