# X Archive Gallery v1.5.0

**正式版 / Stable release — Created by M.Nesuka**

A local Windows gallery for images, GIFs and videos from your X archive.
Includes manual tags, favorites, exact-duplicate hiding, discovery, slideshow,
optional content Analytics, Japanese/English UI and dark/light themes.
No AI analysis, cloud API, web server or X account sign-in is used by the app.

## Download and update

Download `XArchiveGallery_v1.5.0_Windows_x64.zip` from this repository's v1.5.0
Release. Extract the ZIP and open `XArchiveGallery.exe`; Python is not required.
Keep the accompanying license documents. Read `はじめに.txt` and `使い方.txt`.

Existing v1.4.x users: close the app, replace its EXE with this release, and open
it under the same Windows user. **Do not reset or re-import your library.**
Works stay in your library; tags, favorites, Analytics and settings stay in
`%LOCALAPPDATA%/XArchiveGallery/data`. Database schema version 8 is unchanged.

First use: choose a save location → select the X archive ZIP → optionally select
a **content / post-level** Analytics CSV → import → view the gallery.
Analytics is optional. Language is selected from `… → 言語 / Language`.

To update works, import the newer full archive into the same library. Existing
post attachments retain their saved file and annotations even when X changes
the image encoding or export size. Only new attachments are added.
Identical bytes reused in another post share one verified backup file while
retaining separate post/Analytics links. Older duplicate attachment records
are displayed once; private annotations are merged
after a verified DB backup. Original catalog rows and artwork files are retained.

## License

M.Nesuka's original code is **Source Available**, not MIT or open source.
Viewing and private personal study/reference are allowed; redistribution of the
app/original source/modified versions and paid distribution require permission.
See [LICENSE.md](LICENSE.md). Third-party components keep their own licenses.
Library-replacement and debugging rights required by the LGPL are preserved.
See [THIRD_PARTY.md](THIRD_PARTY.md) for component sources and notices.

## Run the source (Windows x64, Python 3.12)

These commands use files included in this source folder and in
`licenses/application-source.zip`. Open Command Prompt in the extracted folder:

```bat
py -3.12 -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
.venv\Scripts\python.exe main.py
```

The audited poster-extraction FFmpeg is supplied with the release. To build,
follow [BUILDING.md](BUILDING.md); do not bundle the unrelated GPL executable
inside the upstream imageio-ffmpeg wheel.

## Build

```bat
.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.venv\Scripts\python.exe tools/build_single.py
```

First complete `BUILDING.md` prerequisites.
Output: `single-build/dist/XArchiveGallery.exe`.
The build rejects private data and audits dependencies and license inputs.
All referenced scripts are included. Internal tests and external QA fixtures
are not required and are not described as bundled files.

## Storage and privacy

User information is independent of the app folder and version. `--data-dir` is
an explicit developer override. Gallery access to `catalog.sqlite3` is read-only;
only a confirmed archive import updates it. Library IDs separate annotations.
Migrations check integrity, back up old DBs and use transactions.
Diagnostics exclude works, databases, CSVs and library/file histories.

## Library replacement and release information

The EXE expands a dynamically linked runtime into the user cache.
Interface-compatible LGPL libraries can be replaced there; see
`docs/LIBRARY_REPLACEMENT.md`. Third-party code is not relicensed under the app license.
Matching third-party source archives and checksums are supplied with the Release.
See `docs/PUBLISHING.md` and `third_party/source-manifest.json`.
Signing is optional and supported by `tools/sign_release.py`.

Author: **M.Nesuka**. This app is not affiliated with X Corp.
