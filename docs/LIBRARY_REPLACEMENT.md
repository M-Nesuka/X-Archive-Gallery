# Replacing LGPL libraries

X Archive Gallery uses Qt/PySide6 under LGPLv3 and FFmpeg under LGPLv2.1-or-later.
Their licenses permit modification/replacement and debugging of those modifications,
including necessary reverse engineering. `LICENSE.md` preserves these rights.

1. Start the official EXE once, then close the app.
2. Open `%LOCALAPPDATA%\XArchiveGallery\runtime\` in Explorer.
3. Open the matching `v1.5.0-...` runtime folder. See `runtime-ready.json` to
   identify it. User data is stored elsewhere, under `data`, and is not changed.
4. Save a copy of the DLLs you plan to replace. Under `_internal\PySide6\`, replace
   Qt/PySide/FFmpeg DLLs with compatible modified versions built from supplied sources.
   Include matching dependent libraries when needed. Keep the same ABI and filenames.
5. For the poster subprocess, replace
   `_internal\imageio_ffmpeg\binaries\ffmpeg-win-x86_64-v7.1.exe` with your modified
   executable supporting first-frame PNG output and the scale filter.
6. Run the outer EXE normally. It checks the application host and required file
   presence, but **does not reject modified third-party DLLs/executables by hash**.

You may instead run the extracted inner `XArchiveGallery.exe` directly, or build
the app from `licenses/application-source.zip` using `BUILDING.md`. No signature,
activation or online check is required for your modified libraries to run.
Do not delete `runtime-ready.json` or the inner application host while replacing
libraries; repairing a damaged application host may create a fresh runtime folder.
An app update creates a different runtime version; apply your modifications there.

The corresponding source archive is supplied next to the app ZIP in the same
GitHub Release. Original component licenses govern your library modifications
and their redistribution. App redistribution requires M.Nesuka's permission.
