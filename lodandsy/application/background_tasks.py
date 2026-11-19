"""Queued GUI-thread completion with explicit generation invalidation for owned workers."""

from concurrent.futures import ThreadPoolExecutor

from PySide6.QtCore import QObject, Qt, Signal


class BackgroundTasks(QObject):
    completed = Signal(object)

    def __init__(self, parent=None, *, workers=1, name="lodandsy-work"):
        super().__init__(parent)
        self._executor = ThreadPoolExecutor(max_workers=workers, thread_name_prefix=name)
        self._generation = 0
        self.completed.connect(self._finish, Qt.ConnectionType.QueuedConnection)

    def run(self, operation, callback):
        generation = self._generation
        future = self._executor.submit(operation)

        def done(job):
            try:
                value, error = job.result(), None
            except Exception as failure:
                value, error = None, str(failure)
            try:
                self.completed.emit((generation, callback, value, error))
            except RuntimeError:
                pass

        future.add_done_callback(done)

    def _finish(self, result):
        generation, callback, value, error = result
        if generation == self._generation:
            callback(value, error)

    def invalidate(self):
        self._generation += 1

    def shutdown(self):
        self.invalidate()
        self._executor.shutdown(wait=True)
