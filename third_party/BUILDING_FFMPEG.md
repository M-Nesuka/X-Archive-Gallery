<!-- Copyright (C) 2026 M.Nesuka; SPDX-License-Identifier: LGPL-2.1-or-later -->
# Corresponding-source build instructions

These instructions and the dedicated poster build recipe are LGPL-2.1-or-later.
This is library build documentation, outside the application's Source Available
license. The source archives retain their upstream licenses.

The matching source asset contains `source-manifest.json`, `sources/`,
`tools/build_poster_ffmpeg.py`, `patches/`, the complete LGPL-2.1 text and both
FFmpeg configure/license records. The manifest identifies archive SHA-256s.

## The separate poster process

Use Windows x64 and Python 3.12. Build in a directory without spaces.
Install llvm-mingw 20250114 UCRT x86_64 (Clang 19.1.7), GNU Make 4.4.1,
pkgconf 3.0.7 and a POSIX `sh` with standard Unix tools. The compiler download
URL and checksum are recorded in the manifest's `development_tools` section.
These are development tools; the application does not need them installed.

```bat
py -3.12 -m venv .venv
.venv\Scripts\python.exe -m pip install meson==1.7.0 ninja==1.11.1.3
.venv\Scripts\python.exe tools/build_poster_ffmpeg.py --compiler PATH_TO_LLVM_MINGW --make PATH_TO_MINGW32_MAKE_EXE --pkgconf PATH_TO_PKGCONF_EXE --shell PATH_TO_SH_EXE --sources sources --output poster-build --jobs 2
```

The recipe extracts the original `ffmpeg-7.1.5.tar.xz`, `dav1d-1.5.1.tar.xz` and
`zlib-1.3.1.tar.gz`. It builds static zlib/dav1d, configures FFmpeg with GPL,
nonfree, version3, autodetection and networking disabled, and enables PNG output,
local file/pipe input and scale/format/null filters. Native video decoders and
the dav1d AV1 decoder remain enabled. The full options are in the script and
`Poster-FFmpeg-build.txt`.

The only upstream source change is the response-file command in
`ffbuild/library.mak`; the patch is supplied separately and is applied by the
script. Generated Makefile drive paths are converted for native Windows Make.
No decoding code is patched. The script retains originals, build trees, options,
the applied patch and `poster-build/ffmpeg.exe`, so modifications can be rebuilt.
Compiler file-prefix maps replace private build locations in diagnostic strings.
When resuming a build after compiler flags change, use `--resume --clean`.

To use a rebuilt poster, replace the compatible poster executable in the app's
extracted runtime as described by its `licenses/LIBRARY_REPLACEMENT.md`.
No app activation/signature check prevents library replacement. If rebuilding
the application itself, use the separate public application source folder and
its `BUILDING.md`; this source bundle is the library source asset.

## Qt's separate playback DLLs

These are FFmpeg 7.1.5 LGPL-2.1-or-later shared DLLs, not the poster build.
The included `FFmpeg-n7.1.5.tar.gz` SHA-1 matches the tag archive required by
Qt's v6.11.2 `coin/provisioning/common/windows/install-ffmpeg.ps1`, inside the
included qt5 tag archive. That original script, `Qt-FFmpeg-build.txt`, and zlib
1.3.1 provide the source, configure options and Windows MSVC build instructions.
The FFmpeg sources are unmodified. Compatible modified DLLs can be substituted
under `_internal/PySide6/` using the application's library replacement guide.

## Qt/PySide and other sources

Qt module archives and pyside-setup 6.11.2 contain their original build scripts
and bundled third-party code. Use their upstream Windows CMake build instructions
and Qt's included `coin` provisioning scripts. The original Python, Pillow,
ijson/YAJL, imageio-ffmpeg, PyInstaller, OpenSSL and Mesa archives include their
own notices and build instructions. No owner data or proprietary compiler
installer is included, and byte-identical upstream builds are not claimed.
