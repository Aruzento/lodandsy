import threading

from PySide6.QtCore import QThread, QTimer
from PySide6.QtWidgets import QApplication

from lodandsy.application.save_coordinator import SaveCoordinator, SaveState
from lodandsy.application.sqlite_project_store import ProjectSnapshot


def test_autosave_debounces_and_ctrl_s_uses_the_same_path(qtbot):
    writes = []
    saver = SaveCoordinator(lambda revision: ProjectSnapshot((), revision), debounce_ms=20)
    saver.reset(0, lambda snapshot, base: writes.append((snapshot.revision, base)))
    saver.mark_dirty()
    saver.mark_dirty()
    qtbot.waitUntil(lambda: saver.state == SaveState.CLEAN)
    assert writes == [(2, 0)]
    saver.mark_dirty()
    assert saver.save()
    qtbot.wait(30)
    assert writes == [(2, 0), (3, 2)]
    saver.shutdown()


def test_error_remains_visible_after_edits_until_successful_retry(qtbot):
    failures = [True]
    def persist(snapshot, base):
        if failures[0]:
            raise OSError("disk full")
    saver = SaveCoordinator(lambda revision: ProjectSnapshot((), revision))
    saver.reset(0, persist)
    saver.mark_dirty()
    assert not saver.save()
    assert saver.state == SaveState.ERROR and saver.dirty
    saver.mark_dirty()
    assert saver.last_error == "disk full" and saver.state == SaveState.ERROR
    failures[0] = False
    assert saver.save()
    assert not saver.dirty and saver.last_error is None
    saver.shutdown()


def test_confirmation_only_cleans_saved_revision_while_new_edits_stay_dirty(qtbot):
    writes = []
    started, release = threading.Event(), threading.Event()
    saver = SaveCoordinator(lambda revision: ProjectSnapshot((), revision))
    def persist(snapshot, base):
        assert QThread.currentThread() != QApplication.instance().thread()
        writes.append(snapshot.revision)
        if snapshot.revision == 1:
            started.set()
            assert release.wait(2)
    saver.reset(0, persist)
    saver.mark_dirty()
    assert saver.request_save()
    qtbot.waitUntil(started.is_set)
    gui_events = []
    QTimer.singleShot(0, lambda: gui_events.append(True))
    saver.mark_dirty()
    qtbot.waitUntil(lambda: bool(gui_events))
    release.set()
    qtbot.waitUntil(lambda: not saver.saving)
    assert saver.saved_revision == 1 and saver.revision == 2
    assert saver.state == SaveState.DIRTY
    assert saver.save()
    assert writes == [1, 2] and not saver.dirty
    saver.shutdown()


def test_result_signals_are_applied_on_gui_thread_and_reentrant_flush_is_refused(qtbot):
    saver = SaveCoordinator(lambda revision: ProjectSnapshot((), revision))
    saver.reset(0, lambda snapshot, base: None)
    states = []
    def changed(state):
        assert QThread.currentThread() == QApplication.instance().thread()
        states.append(state)
        if state == SaveState.SAVING:
            assert not saver.save()
    saver.state_changed.connect(changed)
    saver.mark_dirty()
    assert saver.save()
    assert states == [SaveState.DIRTY, SaveState.SAVING, SaveState.CLEAN]
    saver.shutdown()


def test_safe_flush_observes_writer_even_without_queued_notification(qtbot):
    saver = SaveCoordinator(lambda revision: ProjectSnapshot((), revision))
    saver.reset(0, lambda snapshot, base: None)
    saver._result_ready.disconnect()
    saved = []
    saver.saved.connect(saved.append)
    saver.mark_dirty()
    assert saver.save()
    assert saved == [1] and saver.state == SaveState.CLEAN
    assert not saver.dirty and not saver.saving
    saver.shutdown()


def test_autosave_recovers_missing_ack_and_discards_late_result(qtbot):
    saver = SaveCoordinator(lambda rev: ProjectSnapshot((), rev), debounce_ms=20)
    entered, release = threading.Event(), threading.Event()

    def persist(snapshot, base):
        if snapshot.revision == 2:
            assert base == 1
            entered.set()
            assert release.wait(3)

    saver.reset(0, persist)
    saver._result_ready.disconnect()
    saved = []
    saver.saved.connect(saved.append)
    saver.mark_dirty()
    assert saver.request_save()
    old = saver._future
    qtbot.waitUntil(lambda: saved == [1])
    saver.mark_dirty()
    qtbot.waitUntil(entered.is_set)
    saver._on_result(old)
    assert saver.saving and saver.saved_revision == 1
    release.set()
    qtbot.waitUntil(lambda: saved == [1, 2])
    saver.reset(0, persist)
    saver._on_result(old)
    assert saver.saved_revision == 0 and not saver.dirty
    saver.shutdown()


def test_shutdown_observes_the_writer_without_qt_completion_delivery(qtbot):
    saver = SaveCoordinator(lambda rev: ProjectSnapshot((), rev))
    entered, release = threading.Event(), threading.Event()
    saved, rescue = [], []

    def persist(snapshot, base):
        entered.set()
        assert release.wait(3)

    saver.reset(0, persist)
    saver.saved.connect(saved.append)
    saver._result_ready.disconnect()
    saver.mark_dirty()
    assert saver.request_save()
    qtbot.waitUntil(entered.is_set)
    saver._completion_timer.stop()

    def restore_delivery():
        rescue.append(True)
        saver._observe_completed()

    # A regression can fail visibly instead of indefinitely blocking the suite.
    fallback = QTimer()
    fallback.setInterval(300)
    fallback.timeout.connect(restore_delivery)
    fallback.start()
    releaser = threading.Timer(0.04, release.set)
    releaser.start()
    try:
        saver.shutdown()
    finally:
        fallback.stop()
        releaser.join()
    assert saved == [1] and not saver.dirty and not rescue
