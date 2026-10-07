# Publish v1.5.0 on GitHub

Upload this organized application source folder as the repository contents.
Keep `LICENSE.md`, `THIRD_PARTY.md`, `third_party/` and build documentation.
It is **Source Available**, not MIT/open source. GitHub's public-repository
viewing/forking permissions still apply; the license acknowledges this.

Create the **v1.5.0** Release as a normal release, not a prerelease/Public Beta.
Upload these two assets in the same public Release:

- `XArchiveGallery_v1.5.0_Windows_x64.zip`
- `XArchiveGallery_v1.5.0_ThirdPartySources.zip`

Upload `SHA256SUMS.txt` too. Publish both download links together, at no added
charge or access restriction for source. Do not upload the application ZIP alone:
the matching third-party source archive is an essential part of this publication.
GitHub's automatic app-only “Source code” downloads do not replace that archive.

Suggested Release text:

> X Archive Gallery v1.5.0 — 正式版 / Stable release. Created by M.Nesuka.
> Windows x64; Python installation is not required. Extract the app ZIP and open
> XArchiveGallery.exe. Existing v1.4.x users: close the app, replace the EXE, then
> reopen under the same Windows user. Do not reset your library.
> The application is Source Available under LICENSE.md. It uses Qt/PySide6 under
> LGPLv3 and FFmpeg under LGPLv2.1-or-later. Matching third-party sources and build
> instructions are available in the ThirdPartySources asset on this same Release.

Never publish personal artworks, archives/CSV, catalogs, private databases,
preferences, test fixtures, logs or development work directories. No GitHub
upload, account change or release creation is performed by local build scripts.

The package is unsigned; Windows may show a warning for an unknown publisher.
Review the SHA-256 before replacing an EXE. A separate clean Windows PC acceptance
test is recommended; local isolated-profile tests are not a physical second-PC test.
