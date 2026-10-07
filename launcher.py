"""Single-file distribution: install a verified, replaceable runtime into user cache.

No user library, catalog or annotation database is stored in this runtime.
"""
from __future__ import annotations

import ctypes
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import stat
import subprocess
import sys
import tempfile
import time
import zipfile
from contextlib import contextmanager


def digest(path):
    sha = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            sha.update(block)
    return sha.hexdigest()


@contextmanager
def cache_lock(path, timeout=90):
    """Serialize first-run extraction without holding the lock during app usage."""
    import msvcrt
    with Path(path).open('a+b') as stream:
        stream.seek(0, 2)
        if not stream.tell():
            stream.write(b'0')
            stream.flush()
        deadline = time.monotonic() + timeout
        while True:
            try:
                stream.seek(0)
                msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
                break
            except OSError:
                if time.monotonic() >= deadline:
                    raise TimeoutError('起動準備が完了しませんでした。少し待ってから再度起動してください。')
                time.sleep(0.1)
        try:
            yield
        finally:
            stream.seek(0)
            msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)


def extract_payload(payload, destination):
    destination = Path(destination).resolve()
    with zipfile.ZipFile(payload) as archive:
        members = archive.infolist()
        total = 0
        paths = set()
        for member in members:
            name = member.filename
            parts = PurePosixPath(name).parts
            key = name.casefold().rstrip('/')
            if (not parts or member.orig_filename != name or '\\' in name or ':' in name or name.startswith('/')
                    or any(p in ('.', '..') or p.endswith(('.', ' ')) for p in parts)
                    or stat.S_ISLNK(member.external_attr >> 16) or key in paths):
                raise ValueError('配布ファイルに不正なパスが含まれています。')
            paths.add(key)
            target = destination.joinpath(*parts)
            if not target.resolve().is_relative_to(destination):
                raise ValueError('配布ファイルの保存先が不正です。')
            total += member.file_size
            if total > 2_000_000_000:
                raise ValueError('配布ファイルの展開サイズが大きすぎます。')
        archive.extractall(destination)


def runtime_ready(target, manifest):
    try:
        marker = json.loads((target/'runtime-ready.json').read_text(encoding='utf-8'))
        if marker.get('payload_sha256') != manifest['payload_sha256']:
            return False
        if digest(target/'XArchiveGallery.exe') != manifest['exe_sha256']:
            return False
        return all((target/name).is_file() for name in manifest['required_files'])
    except (OSError, ValueError, KeyError):
        return False


def ensure_runtime(payload, manifest, base):
    base = Path(base).resolve()
    version = manifest['version']
    payload_sha = manifest['payload_sha256']
    if not all(c in '0123456789abcdef' for c in payload_sha) or len(payload_sha) != 64:
        raise ValueError('配布ファイルのハッシュが不正です。')
    if not version or any(c not in '0123456789.' for c in version):
        raise ValueError('配布ファイルのバージョンが不正です。')
    base.mkdir(parents=True, exist_ok=True)
    target = base / ('v'+version+'-'+payload_sha[:12])
    with cache_lock(base/'install.lock'):
        if runtime_ready(target, manifest):
            return target/'XArchiveGallery.exe'
        if digest(payload) != payload_sha:
            raise ValueError('配布ファイルが破損しています。元のEXEを入手し直してください。')
        stage = Path(tempfile.mkdtemp(prefix='.install-', dir=base)).resolve()
        try:
            extract_payload(payload, stage)
            (stage/'runtime-ready.json').write_text(json.dumps({
                'payload_sha256': payload_sha, 'version': version,
            }), encoding='utf-8')
            if not runtime_ready(stage, manifest):
                raise ValueError('実行ファイルの整合性を確認できませんでした。')
            if target.exists():
                # Preserve unknown contents instead of recursively deleting them.
                displaced = base/(target.name+'.damaged-'+str(time.time_ns()))
                target.rename(displaced)
            stage.rename(target)
            return target/'XArchiveGallery.exe'
        finally:
            # Only the unique directory created by this invocation can be removed.
            if stage.exists() and stage.parent == base and stage.name.startswith('.install-'):
                shutil.rmtree(stage)


def main():
    packaged = Path(getattr(sys, '_MEIPASS', Path(__file__).resolve().parent))
    manifest = json.loads((packaged/'runtime-manifest.json').read_text(encoding='utf-8'))
    local = Path(os.environ.get('LOCALAPPDATA', str(Path.home()/'AppData'/'Local')))
    base = Path(os.environ.get('XAG_RUNTIME_CACHE', str(local/'XArchiveGallery'/'runtime')))
    executable = ensure_runtime(packaged/'runtime-payload.zip', manifest, base)
    environment = os.environ.copy()
    environment['XAG_LAUNCHER_HOME'] = str(Path(sys.executable).resolve().parent)
    environment['PYINSTALLER_RESET_ENVIRONMENT'] = '1'
    # Parent application's Qt and Python search paths must not affect this runtime.
    for key in ('PYTHONHOME', 'PYTHONPATH', 'QT_PLUGIN_PATH', 'QT_QPA_PLATFORM_PLUGIN_PATH'):
        environment.pop(key, None)
    command = [str(executable), *sys.argv[1:]]
    qa = any(arg in ('--qa', '--qa-import', '--qa-startup', '--qa-onboarding') for arg in sys.argv[1:])
    flags = getattr(subprocess, 'CREATE_NO_WINDOW', 0)
    if qa:
        return subprocess.run(command, cwd=environment['XAG_LAUNCHER_HOME'], env=environment,
                              creationflags=flags).returncode
    subprocess.Popen(command, cwd=environment['XAG_LAUNCHER_HOME'], env=environment,
                     creationflags=flags)
    return 0


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except Exception as error:
        if os.name == 'nt':
            from yamivault.i18n import set_language_code,preferred_language,tr
            user_data=Path(os.environ.get('LOCALAPPDATA',str(Path.home()/'AppData'/'Local')))/'XArchiveGallery/data'
            set_language_code(preferred_language(user_data))
            from yamivault.diagnostics import configure_logs,friendly_error
            import logging
            try:
                local=Path(os.environ.get('LOCALAPPDATA',str(Path.home()/'AppData'/'Local')))
                configure_logs(local/'XArchiveGallery/data')
                logging.getLogger('launcher').exception('Runtime preparation failed')
            except OSError:pass
            ctypes.windll.user32.MessageBoxW(None,friendly_error(error,'起動'),tr('X Archive Galleryを起動できませんでした'),0x10)
            sys.exit(1)
        raise
