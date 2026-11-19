from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor

from PySide6.QtCore import QObject, Qt, Signal
from PySide6.QtGui import QImageReader


class MapTiles(QObject):
    ready = Signal()
    failed = Signal(str)
    _result = Signal(object)
    budget = 64 * 1024**2

    def __init__(self, parent):
        super().__init__(parent)
        self.images = OrderedDict()
        self.pending = set()
        self.errors = set()
        self.bytes = 0
        self._generation = 0
        self._executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="map-tiles")
        self._result.connect(self._finish, Qt.ConnectionType.QueuedConnection)

    def get(self, path):
        key = str(path)
        if key in self.images:
            self.images.move_to_end(key)
            return self.images[key]
        if key in self.pending or key in self.errors or len(self.pending) >= 64:
            return None
        self.pending.add(key)
        generation = self._generation
        def read():
            if not path.resolve().is_relative_to(path.parents[2].resolve()):
                raise ValueError("Тайл находится вне кеша карты")
            reader = QImageReader(key)
            try:
                size = reader.size()
                if (not size.isValid() or max(size.width(), size.height()) > 256
                        or bytes(reader.format()).lower() != b"png"):
                    raise ValueError("Повреждённый тайл; откройте карту повторно для перестройки")
                image = reader.read()
                if image.isNull():
                    raise ValueError("Не удалось прочитать тайл; откройте карту повторно")
                return image
            finally:
                if reader.device() is not None:
                    reader.device().close()
        def completed(job):
            try:
                value, error = job.result(), None
            except Exception as failure:
                value, error = None, str(failure)
            try:
                self._result.emit((generation, key, value, error))
            except RuntimeError:
                pass
        self._executor.submit(read).add_done_callback(completed)
        return None

    def _finish(self, result):
        generation, key, image, error = result
        if generation != self._generation:
            return
        self.pending.discard(key)
        if error:
            self.errors.add(key)
            # Invalidating readiness ensures reopen rebuilds instead of trusting bad tiles.
            from pathlib import Path
            manifest = Path(key).parents[2] / "manifest.json"
            try:
                manifest.unlink(missing_ok=True)
            except OSError:
                pass
            self.failed.emit(error)
        else:
            old = self.images.pop(key, None)
            if old is not None:
                self.bytes -= old.sizeInBytes()
            self.images[key] = image
            self.bytes += image.sizeInBytes()
            while self.bytes > self.budget:
                self.bytes -= self.images.popitem(last=False)[1].sizeInBytes()
        self.ready.emit()

    def reset(self):
        self._generation += 1
        self.pending.clear()
        self.images.clear()
        self.errors.clear()
        self.bytes = 0

    def shutdown(self):
        self._executor.shutdown(wait=True)
