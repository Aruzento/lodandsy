from pathlib import Path

from PySide6.QtCore import QEventLoop, QObject, Qt, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QLabel,
    QPlainTextEdit,
    QProgressDialog,
    QVBoxLayout,
)

from lodandsy.application.background_tasks import BackgroundTasks
from lodandsy.application.mow_import import (
    apply_import,
    cleanup_assets,
    inspect_source,
    prepare_import,
)


class MowImportController(QObject):
    busy_changed = Signal()
    finished = Signal()

    def __init__(self, project):
        super().__init__(project.window)
        self.project = project
        self.app = project.controller
        self.progress = None
        self.importing = False
        self.tasks = BackgroundTasks(self, name="mow-import")

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
        self.tasks.shutdown()

    def _run(self, operation, callback):
        self.importing = True
        self.busy_changed.emit()
        self.progress = QProgressDialog("Импорт MOW…", "", 0, 0, self.app.window)
        self.progress.setCancelButton(None)
        self.progress.setWindowModality(Qt.WindowModality.ApplicationModal)
        self.progress.setMinimumDuration(0)
        self.progress.show()

        def complete(result, error):
            self.progress.close()
            self.progress.deleteLater()
            self.progress = None
            self.importing = False
            self.busy_changed.emit()
            self.finished.emit()
            if error:
                self.app.window.show_notice(error)
            else:
                callback(result)

        self.tasks.run(operation, complete)

    def request(self, directory=False):
        if self.project.busy:
            return
        if self.project.store is None and not self.project.save_current():
            return
        if directory:
            name = QFileDialog.getExistingDirectory(self.app.window, "Каталог MOW (только чтение)")
        else:
            name, _ = QFileDialog.getOpenFileName(self.app.window, "Карточка MOW", "", "MOW (*.md)")
        if name:
            self._run(lambda: inspect_source(Path(name)), self._preview)

    def _preview(self, plan):
        dialog = QDialog(self.app.window)
        dialog.setWindowTitle("Импорт MOW · предварительная проверка")
        dialog.resize(760, 540)
        layout = QVBoxLayout(dialog)
        parent = self.app.core.selected_id
        parent_name = self.app.core.entities.get(parent).title if parent else "корень проекта"
        layout.addWidget(QLabel("Место импорта: " + parent_name))
        report = QPlainTextEdit()
        report.setReadOnly(True)
        existing = self.app.cards.all()
        source_ids = {c.value("mow_id") or c.id for c in existing}
        count = sum(r.metadata["id"] in source_ids for r in plan.records)
        report.setPlainText(plan.report() + f"\nКонфликтов / повторных UUID: {count}")
        layout.addWidget(report, 1)
        policy = QComboBox()
        policy.addItem("Пропустить существующие source UUID", "skip")
        policy.addItem("Явно создать копии с новыми UUID", "remap")
        layout.addWidget(policy)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("Применить импорт")
        buttons.button(QDialogButtonBox.StandardButton.Ok).setEnabled(
            not plan.errors and bool(plan.records)
        )
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        store = self.project.store
        assets = tuple(self.project.assets.values())
        conflict_policy = policy.currentData()

        def prepared(result):
            try:
                with self.app.core.transaction():
                    apply_import(self.app.cards_service, result)
                    self.project.assets.update((a.id, a) for a in result.assets)
            except Exception as error:
                cleanup_assets(store, result.assets)
                self.app.window.show_notice("Импорт отменён: " + str(error))
                return
            report = QDialog(self.app.window)
            report.setWindowTitle("MOW · результат импорта")
            report.resize(760, 500)
            layout = QVBoxLayout(report)
            text = QPlainTextEdit()
            text.setReadOnly(True)
            text.setPlainText(
                f"Импортировано: {len(result.cards)} · новых ресурсов: {len(result.assets)}\n"
                + "\n".join(result.warnings)
            )
            layout.addWidget(text)
            buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
            buttons.rejected.connect(report.reject)
            layout.addWidget(buttons)
            if result.cards:
                self.app.open_card_editor(result.cards[0].id)
            report.exec()

        self._run(
            lambda: prepare_import(
                plan, store, existing, assets, conflicts=conflict_policy, parent_id=parent
            ),
            prepared,
        )
