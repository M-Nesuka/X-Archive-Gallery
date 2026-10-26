# X Archive Gallery v1.6.0

**Created by M.Nesuka**

A local Windows gallery for images, GIFs and videos from your X archive.
Includes manual tags, favorites, exact-duplicate hiding, discovery, slideshow,
optional content Analytics, Japanese/English UI and dark/light themes.
No AI analysis, cloud API, web server or X account sign-in is used by the app.

## Download and update

Download `XArchiveGallery_v1.6.0_Windows_x64.zip` from this repository's v1.6.0
Release. Extract the ZIP and open `XArchiveGallery.exe`; Python is not required.
Keep the accompanying license documents. Read `はじめに.txt` and `使い方.txt`.

Existing v1.4.x / v1.5.0 users: close the app, use the new EXE, and open
it under the same Windows user. **Do not reset or re-import your library.**
Works stay in your library; tags, favorites, Analytics and settings stay in
`%LOCALAPPDATA%/XArchiveGallery/data`. The private DB now uses schema 9.
An integrity-checked backup is made before upgrading older schemas; the library
catalog is not migrated. Use this revision after upgrading, rather than an older EXE.
To go back to public v1.5.0 (schema 8), close the app and restore the verified
pre-upgrade private DB backup first. Keep a copy of the current DB too.
Do not move your artwork folder as part of an app update: library identities
are associated with their existing locations.

First use: choose a save location → select the X archive ZIP → optionally select
a **content / post-level** Analytics CSV → import → view the gallery.
Analytics is optional. Language is selected from `… → 言語 / Language`.

Manual tags can be organized into named groups in the tag manager. Right-click
an artwork to choose a group and tag; choosing an applied tag again removes it.
Creating a tag and editing an existing tag use separate drafts with explicit
save buttons. Preview 34 background colors, including red, black, white, gold
and silver, before saving. Grouping changes no artwork or Analytics data.
Drag across the tag list to select multiple tags, then delete them together.
With multiple tags selected, clicking a color applies it immediately. No second
Apply button is needed. Groups and assignments remain unchanged.
Ctrl adds individual tags and Shift selects a range. Hidden filtered-out tags
are not deleted. Artwork files remain intact, and deleted hashtags are excluded
from future imports.

Automatic post tags start **OFF**. Opt in before importing or later in tag
management. By default it matches registered names and search words, even for one post.
Optionally enable frequent hashtag registration to discover new tags used in at least
20 posts, up to 50 automatic tag types. Choose counts and limits on the first setup screen, or later under Basic in Automatic post tags.
Saved post text can be retagged without rereading the ZIP. If the automatic tag limit is reached,
increase it or specify a Registered tag and Search words; specified tags match even one post.
Excluded/deleted tags and recorded per-image removals remain respected.
In the table, enter the tag name on the left and words to look for on the right:
`Animals` → `cat,dog`. Commas or Japanese commas separate alternatives.
Add per-tag aliases to combine name variants; hashtag prefix matching is optional.
Single Japanese characters and ASCII words shorter than three characters do not
match body text; exact hashtags can still match. Exclusions start empty.
Manual assignments and recorded removals survive rule changes. Existing legacy
automatic tags are kept, without extending them to newly imported posts.
Optional cleanup removes only unused legacy-generated tags; it preserves manual
assignments, edited tags and recorded removals. Old frequency/type-limit settings
are retained for compatibility but are no longer shown as effective controls.
For archives imported with older versions, use **Read post text from ZIP** once;
this reads metadata without writing artwork or the library catalog.
Unchanged matching inputs reuse a verified result. Large updates run in background
workers. Color-only edits avoid full filtering and layout. Original Analytics CSV
copies support Windows long paths without changing Windows settings; oversized CSV
files are rejected before a full read. All matching is local and deterministic. See [post tag design](docs/POST_TEXT_TAGS.md).

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

### Analyticsの比較対象 / Analytics ranking scope

高成績・NO.1は、このライブラリのギャラリー全体で作品がある投稿を比較します。過去と今回の保存済みCSVを合わせ、投稿ごとに最新の数値を使います。画像のない投稿や未収録の投稿は順位から除外しますが、元の成績は保存します。検索・年月・お気に入りの絞り込みでは順位は変わりません。Analyticsが未登録の作品は判定できません。

Performance and NO.1 compare all artwork posts in the library, combining saved CSV history and using the latest imported metrics per post. Unlinked posts remain saved but cannot displace artwork awards. Search, date and favorite filters do not affect rankings. Works without Analytics cannot be ranked. Rankings remain separate for each library/account.
