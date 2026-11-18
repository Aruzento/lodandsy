from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from enum import StrEnum

from PySide6.QtCore import QEventLoop, QObject, Qt, QTimer, Signal, Slot

from lodandsy.application.sqlite_project_store import ProjectSnapshot


class SaveState(StrEnum):
    CLEAN = "clean"
    DIRTY = "dirty"
    SAVING = "saving"
    ERROR = "error"


class SaveCoordinator(QObject):
    state_changed = Signal(object)
    saved = Signal(int)
    _result_ready = Signal(object)
    _finished = Signal()

    def __init__(self, snapshot: Callable[[int], ProjectSnapshot], parent=None, debounce_ms=750):
        super().__init__(parent)
        self._snapshot = snapshot
        self._persist: Callable[[ProjectSnapshot], None] | None = None
        self.revision = 0
        self.saved_revision = 0
        self.state = SaveState.CLEAN
        self.last_error: str | None = None
        self._saving = False
        self._waiting = False
        self._future = None
        self._job_revision = 0
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="lodandsy-save")
        self._result_ready.connect(self._on_result, Qt.ConnectionType.QueuedConnection)
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(debounce_ms)
        self._timer.timeout.connect(self.request_save)

    @property
    def dirty(self):
        return self.revision != self.saved_revision

    @property
    def saving(self):
        return self._saving

    def reset(self, revision: int, persist: Callable[[ProjectSnapshot], None] | None):
        if self._saving:
            raise RuntimeError("Wait for the current save before switching projects")
        self._timer.stop()
        self.revision = self.saved_revision = revision
        self._persist = persist
        self.last_error = None
        self._set_state(SaveState.CLEAN)

    def _set_state(self, state):
        self.state = state
        self.state_changed.emit(state)

    def mark_dirty(self, *_args):
        self.revision += 1
        if self._saving:
            return
        if self.last_error is not None:
            self._set_state(SaveState.ERROR)
            return
        self._set_state(SaveState.DIRTY)
        if self._persist is not None:
            self._timer.start()

    def request_save(self) -> bool:
        """Capture immutable data on GUI thread, then queue exactly one writer job."""
        self._timer.stop()
        if self._saving:
            return True
        if not self.dirty:
            return self.last_error is None
        try:
            if self._persist is None:
                raise ValueError("Create or open a project before saving")
            self._job_revision = self.revision
            snapshot = self._snapshot(self._job_revision)
            self._saving = True
            self._set_state(SaveState.SAVING)
            self._future = self._executor.submit(self._persist, snapshot)
            self._future.add_done_callback(self._completed)
            return True
        except Exception as error:
            self._saving = False
            self.last_error = str(error)
            self._set_state(SaveState.ERROR)
            self._finished.emit()
            return False

    def _completed(self, future):
        # Runs on the writer thread. No widget/session access here.
        try:
            future.result()
            error = None
        except Exception as failure:
            error = str(failure)
        self._result_ready.emit((future, error))

    @Slot(object)
    def _on_result(self, result):
        future, error = result
        if future is not self._future:
            return
        self._future = None
        self._saving = False
        self.last_error = error
        if error is not None:
            self._set_state(SaveState.ERROR)
        else:
            self.saved_revision = self._job_revision
            self._set_state(SaveState.DIRTY if self.dirty else SaveState.CLEAN)
            self.saved.emit(self.saved_revision)
            if self.dirty:
                self._timer.start()
        self._finished.emit()

    def wait_current(self):
        if self._saving:
            loop = QEventLoop()
            # Synchronous close also observes the future from the GUI thread;
            # completion does not depend solely on a queued signal during teardown.
            observer = QTimer()
            observer.setInterval(10)
            def observe():
                future = self._future
                if future is not None and future.done():
                    error = future.exception()
                    self._on_result((future, str(error) if error is not None else None))
            observer.timeout.connect(observe)
            self._finished.connect(loop.quit)
            try:
                observe()
                if self._saving:
                    observer.start()
                    loop.exec()
            finally:
                observer.stop()
                self._finished.disconnect(loop.quit)
        return self.last_error is None

    def save(self) -> bool:
        """Ctrl+S/close wait for this same pipeline while Qt keeps processing events."""
        if self._waiting:
            return False
        self._waiting = True
        try:
            while self.dirty:
                if not self._saving and not self.request_save():
                    return False
                if not self.wait_current():
                    return False
            return self.last_error is None
        finally:
            self._waiting = False

    def shutdown(self):
        self._timer.stop()
        self.wait_current()
        self._timer.stop()
        self._executor.shutdown(wait=True)
