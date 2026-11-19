import pytest

from lodandsy.application.app_controller import AppController
from lodandsy.application.project_controller import ProjectController
from lodandsy.ui.app_shell import AppShell


@pytest.fixture
def project(qtbot):
    window = AppShell()
    qtbot.addWidget(window, before_close_func=lambda widget: setattr(widget, "close_guard", None))
    controller = AppController(window)
    project = ProjectController(controller)
    yield controller, project
    window.close_guard = None
    controller.modules.shutdown()
    controller.card_images.shutdown()
    project.saver.shutdown()
    if project.store:
        project.store.close()


def sample_store(root):
    """A new-format test world, not an old project or migration fixture."""
    from PySide6.QtGui import QImage

    from lodandsy.application.rich_html import text_document
    from lodandsy.application.sqlite_project_store import ProjectSnapshot, SQLiteProjectStore
    from lodandsy.domain.card_collection import CardCollection
    from lodandsy.domain.map_document import MapDocument, MapGrid, TokenInstance

    store = SQLiteProjectStore.create(root)
    image = QImage(24, 16, QImage.Format.Format_RGB32)
    image.fill(0xFF334455)
    source = root.parent / "sample.png"
    image.save(str(source))
    asset = store.import_asset(source)
    cards = CardCollection()
    first = cards.create("World", content=text_document("Original document"))
    second = cards.create("Child", first.id, content=text_document("Second document"))
    document = MapDocument(
        "Map",
        asset.id,
        tokens=(TokenInstance(second.id, 11, 9, cells_w=2, cells_h=1, image_override=asset.id),),
        grid=MapGrid(True, 80, -2, 3, 0.6),
    )
    table = text_table("Table", rows=("Forest", "", "0", "<text>"))
    store.save(ProjectSnapshot(cards.all(), 7, (asset,), (document,), (table,)))
    return store


def record_rows(table, values):
    from lodandsy.domain.table_document import RowRecord

    return tuple(RowRecord(i, ((table.columns[0].id, value),)) for i, value in enumerate(values))


def text_table(title, *, rows=(), id=None):
    from dataclasses import replace

    from lodandsy.domain.table_document import TableDocument

    table = TableDocument(title) if id is None else TableDocument(title, id)
    return replace(table, rows=record_rows(table, rows))


def text_values(table):
    return tuple(r.value(table.columns[0].id) for r in table.rows)
