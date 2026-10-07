# Third-party components — X Archive Gallery v1.5.0

These components are **not** covered by M.Nesuka's Source Available restrictions.
Their original licenses and notices are retained in `licenses/` (binary release)
and `third_party/notices/` (application source).

| Component | Version | Applicable terms / purpose |
|---|---|---|
| Qt / PySide6 / Shiboken | 6.11.2 | LGPL-3.0, dynamically linked GUI/bindings |
| FFmpeg poster executable | 7.1.5 | LGPL-2.1-or-later; separate thumbnail process |
| FFmpeg libraries used by Qt | 7.1.5 | LGPL-2.1-or-later; replaceable playback DLLs |
| dav1d | 1.5.1 | BSD-2-Clause; AV1 poster decoding |
| zlib | 1.3.1 | Zlib; FFmpeg PNG output and Qt FFmpeg dependency |
| imageio-ffmpeg | 0.6.0 | BSD-2-Clause; executable resolver |
| Python | 3.12.14 | PSF and included dependency notices |
| Pillow | 12.3.0 | HPND and included third-party notices |
| ijson / YAJL | 3.5.1 / bundled source | BSD-3-Clause / ISC upstream notices |
| PyInstaller | 6.22.3 | GPL-2.0-or-later with bootloader exception allowing non-free apps |
| OpenSSL | 3.5.8 | Apache-2.0; Python runtime |
| Mesa software OpenGL | 11.2.2 | Permissive notices in Mesa source and COPYING |
| LLVM/mingw runtime | 20250114 toolchain | LLVM exception / mingw runtime notices |
| Microsoft VC / Windows runtime files | Binary inventory | Microsoft redistribution terms; not the app license |

## Corresponding sources supplied with this release

`XArchiveGallery_v1.5.0_ThirdPartySources.zip` contains the original source
archives identified by SHA-256 in `third_party/source-manifest.json`, Qt's tagged
Windows FFmpeg provisioning/build scripts, the poster build recipe and its small
Windows build-only patch. Qt module source archives contain their bundled
third-party sources and notices. PySide/Shiboken share the pyside-setup archive.
The source bundle is provided **alongside the application ZIP in the same GitHub
v1.5.0 Release**, with equivalent public access and without an extra fee/login.
The publisher must upload both assets; upstream links are supplementary references,
not a substitute for the supplied source files.

The old `7.1-essentials_build-www.gyan.dev` GPL static executable is **not** in
this release. It has been replaced, rather than claiming that its unknown static
dependency revisions have corresponding sources. The new poster executable has
no GPL/nonfree features and statically includes only the listed dav1d/zlib
dependencies and compiler runtime. It uses the same local first-frame/scale/PNG
interface; full video playback continues to use the Qt FFmpeg DLLs.

The unused GPL-only Qt Virtual Keyboard and unused PDF plugin are not shipped.
The supplied Qt sources cover the actual LGPL modules in the binary inventory.

## Modification and replacement rights

Users may modify and redistribute third-party components according to their
licenses, replace LGPL DLLs, relink with compatible versions and reverse engineer
the app to debug library modifications. See `docs/LIBRARY_REPLACEMENT.md`.
Those rights take precedence over the application's distribution restrictions.
No DRM or DLL-signature requirement prevents replacement.

## Notices

Full license texts, upstream copyright notices and Qt attribution files are
retained in the notice tree and original source archives. The source manifest
and runtime inventory identify the corresponding versions and exact binaries.
This app is independent of X Corp. User artworks and data are not redistributed.
