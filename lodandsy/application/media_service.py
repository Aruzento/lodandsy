"""Bounded raster decoding and immutable asset publication for visual documents."""

import time
from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from tempfile import TemporaryDirectory

from PySide6.QtCore import QEventLoop, QObject, QSize, Qt, Signal
from PySide6.QtGui import QImage, QImageIOHandler, QImageReader

from lodandsy.application.resource_paths import resolve_asset_image

MAX_PIXELS = 32_000_000
MAX_BYTES = 64 * 1024**2
THUMB_EDGE = 1024


def read_card_image(path: Path) -> QImage:
    if path.stat().st_size > MAX_BYTES:
        raise ValueError("Изображение превышает 64 MiB")
    reader = QImageReader(str(path))
    try:
        return _decode_card_image(reader)
    finally:
        if reader.device() is not None:
            reader.device().close()


def _decode_card_image(reader):
    if bytes(reader.format()).lower() not in {b"png", b"jpeg", b"webp", b"bmp", b"gif"}:
        raise ValueError("Поддерживаются PNG, JPEG, WebP, BMP и GIF")
    size = reader.size()
    if not size.isValid() or size.width() * size.height() > MAX_PIXELS:
        raise ValueError("Изображение должно содержать не более 32 миллионов пикселей")
    reader.setAutoTransform(True)
    if max(size.width(), size.height()) > THUMB_EDGE:
        reader.setScaledSize(
            size.scaled(QSize(THUMB_EDGE, THUMB_EDGE), Qt.AspectRatioMode.KeepAspectRatio)
        )
    image = reader.read()
    if image.isNull():
        raise ValueError("Повреждённое изображение: " + reader.errorString())
    return (
        image.scaled(
            THUMB_EDGE,
            THUMB_EDGE,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        if max(image.width(), image.height()) > THUMB_EDGE
        else image
    )


class MediaService(QObject):
    ready = Signal(object, str)
    busy_changed = Signal()
    finished = Signal()
    _result = Signal(object)

    def __init__(self, resources, parent=None, notice=lambda text: None):
        super().__init__(parent)
        self.resources = resources
        self.notice = notice
        self.importing = False
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="media-images")
        self._cache = OrderedDict()
        self._lookup = OrderedDict()
        self._pending = set()
        self._generation = 0
        self._sizes = OrderedDict()
        self._result.connect(self._finish, Qt.ConnectionType.QueuedConnection)

    def _submit(self, operation, callback):
        future = self._executor.submit(operation)

        def done(job):
            try:
                result = job.result(), None
            except Exception as error:
                result = None, str(error)
            try:
                self._result.emit((callback, *result))
            except RuntimeError:
                pass

        future.add_done_callback(done)

    def _finish(self, result):
        callback, value, error = result
        callback(value, error)

    def preview(self, root, name):
        lookup = (root, name)
        key = None
        path = resolve_asset_image(root, name)
        if path is None:
            self._remember_lookup(lookup, None)
            return QImage()
        try:
            stat = path.stat()
        except OSError:
            return QImage()
        key = (str(path), stat.st_mtime_ns, stat.st_size)
        self._remember_lookup(lookup, key)
        if key in self._cache:
            self._cache.move_to_end(key)
            return self._cache[key]
        if key in self._pending or len(self._pending) >= 32:
            return None
        self._pending.add(key)
        generation = self._generation

        def complete(value, error):
            self._pending.discard(key)
            if generation != self._generation:
                self.ready.emit(root, name)
                return
            self._cache[key] = value if not error else QImage()
            while (
                len(self._cache) > 128
                or sum(item.sizeInBytes() for item in self._cache.values() if item is not None)
                > 16 * 1024**2
            ):
                self._cache.popitem(last=False)
            self.ready.emit(root, name)

        self._submit(lambda: read_card_image(path), complete)
        return None

    def invalidate(self):
        self._generation += 1
        self._cache.clear()
        self._lookup.clear()
        self._sizes.clear()

    def image_size(self, root, name):
        path = resolve_asset_image(root, name)
        if path is None:
            return None
        try:
            stat = path.stat()
            key = (str(path), stat.st_mtime_ns, stat.st_size)
            if key in self._cache and self._cache[key].isNull():
                return None
            if key in self._sizes:
                self._sizes.move_to_end(key)
                return self._sizes[key]
            reader = QImageReader(str(path))
            size = reader.size()
            if reader.transformation() & QImageIOHandler.Transformation.TransformationRotate90:
                size.transpose()
            supported = bytes(reader.format()).lower() in {b"png", b"jpeg", b"webp", b"bmp", b"gif"}
            if reader.device() is not None:
                reader.device().close()
            value = (
                size
                if supported and size.isValid() and size.width() * size.height() <= MAX_PIXELS
                else None
            )
            self._sizes[key] = value
            while len(self._sizes) > 256:
                self._sizes.popitem(last=False)
            return value
        except OSError:
            return None

    def _remember_lookup(self, lookup, key):
        self._lookup[lookup] = (time.monotonic(), key)
        self._lookup.move_to_end(lookup)
        while len(self._lookup) > 128:
            self._lookup.popitem(last=False)

    def cached_preview(self, root, name):
        """Tokens can share an immutable asset thousands of times in one scene frame."""
        stamp, key = self._lookup.get((root, name), (0, None))
        if time.monotonic() - stamp < 0.25:
            if key is None:
                return QImage()
            if key in self._cache:
                self._cache.move_to_end(key)
                return self._cache[key]
            if key in self._pending:
                return None
        return self.preview(root, name)

    def import_image(self, source, publish):
        """Shared immutable resource path for Card images and graphical map tokens."""
        project = self.resources
        if self.importing or project.store is None:
            raise ValueError("Дождитесь импорта и выберите проект")
        store = project.store
        generation = (project.core.generation, project.generation)
        known = tuple(project.assets.values())
        self.importing = True
        self.busy_changed.emit()

        def operation():
            with TemporaryDirectory(prefix="lodandsy-card-") as folder:
                if isinstance(source, QImage):
                    if source.isNull() or source.width() * source.height() > MAX_PIXELS:
                        raise ValueError("Размер изображения превышает ограничение карточки")
                    path = Path(folder) / "clipboard.png"
                    if not source.save(str(path), "PNG"):
                        raise ValueError("Не удалось прочитать изображение буфера обмена")
                else:
                    path = Path(source)
                read_card_image(path)
                asset = store.import_asset(path, known_assets=known, max_bytes=MAX_BYTES)
                read_card_image(store.root / asset.path)
                return asset

        def complete(asset, error):
            try:
                with project.core.transaction():
                    self._publish_import(project, store, asset, error, publish, generation)
            except (ValueError, RuntimeError) as failure:
                self.notice(str(failure))
            finally:
                self.importing = False
                self.busy_changed.emit()
                self.finished.emit()

        self._submit(operation, complete)

    def _publish_import(self, project, store, asset, error, publish, generation):
        if project.store is not store or generation != (
            project.core.generation,
            project.generation,
        ):
            return
        previous = project.assets.get(asset.id) if asset is not None else None
        if asset is not None:
            project.assets[asset.id] = asset
        accepted = False
        try:
            accepted = publish(asset, error)
        finally:
            if not accepted and asset is not None:
                if previous is None:
                    project.assets.pop(asset.id, None)
                else:
                    project.assets[asset.id] = previous
        if accepted and asset is not None:
            project.core.after_commit(lambda: project.asset_changed.emit(asset.id))
            project.core.mark_changed()

    def wait_import(self):
        if self.importing:
            loop = QEventLoop()
            self.finished.connect(loop.quit)
            try:
                if self.importing:
                    loop.exec()
            finally:
                self.finished.disconnect(loop.quit)

    def shutdown(self):
        self.wait_import()
        self._executor.shutdown(wait=True)
