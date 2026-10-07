# Build X Archive Gallery v1.5.0

Use Windows x64 and Python 3.12. Every application build script referenced here
is included in this source distribution. No internal `tests`, `engine_tests`,
`verify_distribution.py` or private fixture is required to build this release.

```bat
py -3.12 -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt -r requirements-dev.txt
.venv\Scripts\python.exe tools/build_single.py
.venv\Scripts\python.exe tools/package_release.py
```

The audited, prebuilt poster executable and its checksum are included under
`third_party/ffmpeg-bin/`. The build verifies it and replaces the unrelated Gyan
executable automatically collected from imageio-ffmpeg. Do not omit this step or
redistribute the unmodified upstream wheel's FFmpeg as this release's poster.
Qt's native FFmpeg playback DLLs stay separate and dynamically replaceable.

Source builds use that audited executable when running `main.py` too.
PyInstaller produces an inner folder runtime, validates its DLL imports and
wraps it in an EXE. The source allowlist rejects personal paths and private data.

## Rebuild the poster executable

Extract `XArchiveGallery_v1.5.0_ThirdPartySources.zip` from the same Release.
It supplies the exact FFmpeg 7.1.5, dav1d 1.5.1, zlib 1.3.1 source archives and
the matching build-only patch. The `tools/build_poster_ffmpeg.py` script applies
the response-file fix and converts generated paths for Windows GNU Make.
The patch changes build commands only, not decoding or application behavior.

Build tools: llvm-mingw **20250114 UCRT x86_64** (Clang 19.1.7), GNU Make 4.4.1,
pkgconf 3.0.7, an MSYS-compatible POSIX shell with standard Unix utilities,
Meson 1.7.0 and Ninja 1.11.1.3. These are development tools, not app runtime
requirements. Tool URLs/checksums are in the source manifest.
Use a build path without spaces for the native FFmpeg build.

```bat
.venv\Scripts\python.exe -m pip install meson==1.7.0 ninja==1.11.1.3
.venv\Scripts\python.exe tools/build_poster_ffmpeg.py --compiler PATH_TO_LLVM_MINGW --make PATH_TO_MINGW32_MAKE_EXE --pkgconf PATH_TO_PKGCONF_EXE --shell PATH_TO_SH_EXE --sources EXTRACTED_SOURCE_ARCHIVES --output poster-build --jobs 2
```

Source archives use the names in `third_party/source-manifest.json`.
The script retains source/build trees, generated configuration and patch.
To use your rebuilt library privately, replace `third_party/ffmpeg-bin/ffmpeg.exe`
and update its `manifest.json` SHA-256 before rebuilding the app.
The static poster is LGPL-2.1-or-later; GPL, version3 and nonfree are disabled.
Only local file/pipe input and PNG image output are needed by the app.
Do not confuse its build with Qt's separate DLL build.

## Qt/PySide and playback DLLs

The source bundle contains Qt 6.11.2 base/declarative/multimedia/svg/imageformats/
translations, pyside-setup 6.11.2 including Shiboken, and qt5's v6.11.2 provisioning
scripts. Use Qt's original CMake/Windows build instructions inside those archives
and the upstream `coin` provisioning scripts. The exact unmodified FFmpeg
`n7.1.5` Git tag archive is included; its SHA-1 matches Qt's tagged build script.
Qt uses MSVC shared FFmpeg with zlib 1.3.1. The original configure string is in
`third_party/notices/Qt-FFmpeg-build.txt`.
DLLs can be replaced without rebuilding the app if their interfaces remain compatible.

The proprietary app license does not apply to library source, patches of library
code, generated third-party artifacts or their original license documents.
See `THIRD_PARTY.md` and `docs/LIBRARY_REPLACEMENT.md`.

## Signing

Optional: set `XAG_SIGNTOOL`, `XAG_SIGN_CERT_SHA1` and an optional HTTPS
`XAG_SIGN_TIMESTAMP_URL`. `tools/sign_release.py` signs and verifies inner/outer
executables. Never include keys/certificates. Recompute release checksums after signing.
