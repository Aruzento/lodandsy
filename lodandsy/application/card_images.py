"""Bounded raster decoding and immutable asset publication for visual documents."""
import time
from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from tempfile import TemporaryDirectory

from PySide6.QtCore import QEventLoop, QObject, QSize, Qt, Signal
from PySide6.QtGui import QImage, QImageReader, QTextCursor
from PySide6.QtWidgets import QFileDialog, QInputDialog

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
        reader.setScaledSize(size.scaled(QSize(THUMB_EDGE, THUMB_EDGE),
                                        Qt.AspectRatioMode.KeepAspectRatio))
    image = reader.read()
    if image.isNull():
        raise ValueError("Повреждённое изображение: " + reader.errorString())
    return (image.scaled(THUMB_EDGE, THUMB_EDGE, Qt.AspectRatioMode.KeepAspectRatio,
                        Qt.TransformationMode.SmoothTransformation)
            if max(image.width(), image.height()) > THUMB_EDGE else image)


class CardImages(QObject):
    ready = Signal(object, str)
    busy_changed = Signal()
    finished = Signal()
    _result = Signal(object)

    def __init__(self, app):
        super().__init__(app.window)
        self.app = app
        self.importing = False
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="card-images")
        self._cache = OrderedDict()
        self._lookup = OrderedDict()
        self._pending = set()
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
        def complete(value, error):
            self._pending.discard(key)
            self._cache[key] = value if not error else QImage()
            while (len(self._cache) > 128 or sum(
                    item.sizeInBytes() for item in self._cache.values() if item is not None
                    ) > 16 * 1024**2):
                self._cache.popitem(last=False)
            self.ready.emit(root, name)
        self._submit(lambda: read_card_image(path), complete)
        return None

    def _remember_lookup(self, lookup, key):
        self._lookup[lookup] = (time.monotonic(), key)
        self._lookup.move_to_end(lookup)
        while len(self._lookup) > 128:
            self._lookup.popitem(last=False)

    def cached_preview(self, root, name):
        """Tokens can share an immutable asset thousands of times in one scene frame."""
        stamp, key = self._lookup.get((root, name), (0, None))
        if time.monotonic() - stamp < .25:
            if key is None:
                return QImage()
            if key in self._cache:
                self._cache.move_to_end(key)
                return self._cache[key]
            if key in self._pending:
                return None
        return self.preview(root, name)

    def request(self, editor, source=None):
        if self.importing or editor.text_edit.isReadOnly():
            return
        project = getattr(self.app, "project_controller", None)
        if project is None:
            return
        if project.store is None and not project.save_current():
            return
        if source is None:
            name, _ = QFileDialog.getOpenFileName(editor, "Вставить изображение", "",
                "Изображения (*.png *.jpg *.jpeg *.webp *.bmp *.gif)")
            if not name:
                return
            source = Path(name)
        alt, accepted = QInputDialog.getText(editor, "Изображение", "Описание (alt):",
                                             text="Изображение")
        if accepted:
            self.insert(editor, source, alt)

    def insert(self, editor, source, alt):
        project = self.app.project_controller
        if self.importing or project.store is None or editor.card_id is None:
            raise ValueError("Дождитесь импорта и выберите проект и карточку")
        card_id = editor.card_id
        cursor = QTextCursor(editor.text_edit.textCursor())
        # Insertion survives intervening edits without replacing unrelated text.
        cursor.setPosition(cursor.selectionEnd())
        cursor.setKeepPositionOnInsert(True)
        def publish(asset, error):
            if error:
                self.app.window.show_notice(error)
                return False
            if not any(item.id == card_id for item in self.app.cards.all()):
                return False
            cursor.beginEditBlock()
            editor.insert_asset(cursor, asset.path, alt)
            cursor.endEditBlock()
            from lodandsy.application.rich_text_codec import serialize_document

            self.app.session.update_card(card_id, content=serialize_document(cursor.document()))
            return True
        self.import_image(source, publish)

    def import_image(self, source, publish):
        """Shared immutable resource path for Card images and graphical map tokens."""
        project = self.app.project_controller
        if self.importing or project.store is None:
            raise ValueError("Дождитесь импорта и выберите проект")
        store = project.store
        known = tuple(project.assets.values())
        self.importing = True
        self.busy_changed.emit()
        self.app.window.statusBar().showMessage("Импорт изображения…")
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
                if project.store is store:
                    previous = project.assets.get(asset.id) if asset is not None else None
                    if asset is not None:
                        project.assets[asset.id] = asset
                    if publish(asset, error) and asset is not None:
                        project.saver.mark_dirty()
                    elif asset is not None and previous is None:
                        project.assets.pop(asset.id, None)
            except (ValueError, RuntimeError) as failure:
                self.app.window.show_notice(str(failure))
            finally:
                self.importing = False
                self.busy_changed.emit()
                self.finished.emit()
                self.app.window.statusBar().clearMessage()
        self._submit(operation, complete)

    def portrait(self, editor, source=None):
        from dataclasses import replace

        from lodandsy.domain.card import Portrait

        project = self.app.project_controller
        if self.importing or editor.card_id is None:
            return
        if project.store is None and not project.save_current():
            return
        key = editor.card_id
        if source is None:
            name, _ = QFileDialog.getOpenFileName(editor, "Портрет", "",
                "Изображения (*.png *.jpg *.jpeg *.webp *.bmp *.gif)")
            if not name:
                return
            source = Path(name)
        def publish(asset, error):
            if error:
                self.app.window.show_notice(error)
                return False
            if not any(card.id == key for card in self.app.cards.all()):
                return False
            previous = self.app.cards.get(key).portrait or Portrait()
            self.app.session.update_card(key, portrait=replace(previous, asset_id=asset.id))
            return True
        self.import_image(source, publish)

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
