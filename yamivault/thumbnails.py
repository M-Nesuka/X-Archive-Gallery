"""Disposable derived files, bounded workers and foreground request priority."""
from __future__ import annotations

import os
import subprocess
import uuid
from collections import deque
from pathlib import Path

from PIL import Image, ImageOps
from PySide6.QtCore import QObject, QRunnable, QThreadPool, Signal, QTimer

VERSION = 1


def cache_path(cache: Path, sha: str):
    return Path(cache) / 'thumbnails-v1' / sha[:2] / (sha + '.jpg')


def make_thumbnail(source: Path, kind: str, destination: Path):
    """Only destination is writable. Source is never passed as ffmpeg output."""
    destination.parent.mkdir(parents=True, exist_ok=True)
    temp = destination.with_name(uuid.uuid4().hex + '.tmp.jpg')
    frame = destination.with_name(uuid.uuid4().hex + '.frame.png')
    try:
        still = source
        if kind in ('gif', 'video') and source.suffix.lower() not in ('.gif', '.png', '.jpg', '.jpeg', '.webp'):
            import imageio_ffmpeg
            import sys
            audited=Path(__file__).resolve().parents[1]/'third_party/ffmpeg-bin/ffmpeg.exe'
            executable=str(audited) if not getattr(sys,'frozen',False) and audited.is_file() else imageio_ffmpeg.get_ffmpeg_exe()
            process = subprocess.run([executable, '-nostdin', '-v', 'error', '-i', str(source),
                                      '-frames:v', '1', '-vf', 'scale=768:1024:force_original_aspect_ratio=decrease',
                                      '-y', str(frame)], capture_output=True, timeout=25,
                                     creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
            if process.returncode:
                raise ValueError('動画のプレビューを生成できません。')
            still = frame
        with Image.open(still) as original:
            image = ImageOps.exif_transpose(original)
            w, h = image.size
            image.thumbnail((768, 1024), Image.Resampling.LANCZOS)
            if image.mode in ('RGBA', 'LA', 'P'):
                rgba = image.convert('RGBA')
                background = Image.new('RGB', rgba.size, '#141418')
                background.paste(rgba, mask=rgba.getchannel('A'))
                image = background
            else:
                image = image.convert('RGB')
            image.save(temp, 'JPEG', quality=86, optimize=True)
        os.replace(temp, destination)
        return w, h
    finally:
        temp.unlink(missing_ok=True)
        frame.unlink(missing_ok=True)


class JobSignals(QObject):
    done = Signal(str, int, int, str, int)


class ThumbnailJob(QRunnable):
    def __init__(self, sha, source, kind, target, generation):
        super().__init__()
        self.sha, self.source, self.kind, self.target = sha, source, kind, target
        self.generation = generation
        self.signals = JobSignals()

    def run(self):
        try:
            w, h = make_thumbnail(self.source, self.kind, self.target)
            self.signals.done.emit(self.sha, w, h, '', self.generation)
        except Exception as exc:
            self.signals.done.emit(self.sha, 0, 0, str(exc), self.generation)


class ThumbnailManager(QObject):
    ready = Signal(str, int, int)
    progress = Signal(int, int, int)
    failed = Signal(str, str)

    def __init__(self, cache, parent=None):
        super().__init__(parent)
        self.cache = Path(cache)
        self.pool = QThreadPool(self)
        self.pool.setMaxThreadCount(2)
        self.assets = {}
        self.paths = {}
        self.background = deque()
        self.priority = deque()
        self.pending = {}
        self.finished = set()
        self.errors = {}
        self.generation = 0
        self.stopping = False
        self._paused = False
        self.timer = QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.timeout.connect(self.pump)

    @property
    def paused(self):
        return self._paused

    @paused.setter
    def paused(self, value):
        self._paused = bool(value)
        if self._paused:
            self.timer.stop()
        else:
            self.wake()

    def wake(self):
        if not self.stopping and not self.paused and (self.priority or self.background):
            if len(self.pending) < 2 and not self.timer.isActive():
                self.timer.start(0)

    def configure(self, assets, root, path_resolver=None):
        from .catalog import source_path
        self.generation += 1
        self.assets = {a.sha256: a for a in assets}
        resolve=path_resolver or (lambda asset:source_path(root,asset.relative_path))
        self.paths = {}
        for asset in assets:
            path=resolve(asset)
            if asset.sha256 not in self.paths or (not self.paths[asset.sha256].is_file() and path.is_file()):
                self.paths[asset.sha256]=path
                self.assets[asset.sha256]=asset
        self.finished = {sha for sha in self.assets if cache_path(self.cache, sha).is_file()}
        self.errors = {}
        self.priority.clear()
        self.background = deque(sha for sha in self.assets if sha not in self.finished)
        self.report()
        self.wake()

    def request(self, hashes):
        for sha in reversed(hashes):
            if sha in self.assets and sha not in self.finished and sha not in self.pending and sha not in self.errors:
                # Repaints should promote a request, not fill the queue with
                # repeated requests for the same visible thumbnail.
                try:
                    self.priority.remove(sha)
                except ValueError:
                    pass
                self.priority.appendleft(sha)
        # Only the newest viewport requests need high priority.
        while len(self.priority) > 200:
            self.priority.pop()
        self.wake()

    def invalidate(self, sha):
        if sha in self.assets:
            self.finished.discard(sha)
            self.errors.pop(sha, None)
            self.request([sha])

    def pump(self):
        if self.stopping or self.paused:
            return
        while len(self.pending) < 2:
            queue = self.priority if self.priority else self.background
            if not queue:
                break
            sha = queue.popleft()
            if sha not in self.assets or sha in self.finished or sha in self.pending or sha in self.errors:
                continue
            asset = self.assets[sha]
            job = ThumbnailJob(sha, self.paths[sha], asset.kind, cache_path(self.cache, sha), self.generation)
            job.signals.done.connect(self.complete)
            self.pending[sha] = job
            self.pool.start(job)

    def complete(self, sha, w, h, error, generation):
        self.pending.pop(sha, None)
        self.wake()
        if sha not in self.assets:
            return
        if error and generation != self.generation:
            # A refresh/library switch may have replaced an unavailable old
            # source with a valid file of the same content. Retry the current
            # source instead of poisoning the new library with the old error.
            self.request([sha])
            return
        if error:
            self.errors[sha] = error
            self.failed.emit(sha, error)
        else:
            self.finished.add(sha)
            self.ready.emit(sha, w, h)
        self.report()

    def report(self):
        self.progress.emit(len(self.finished), len(self.assets), len(self.errors))

    def shutdown(self):
        self.stopping = True
        self.timer.stop()
        self.pool.clear()
        self.pool.waitForDone()
