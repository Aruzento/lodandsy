"""Native, disposable review workspace. All operations use production application services."""

from pathlib import Path
from uuid import uuid4

from PySide6.QtGui import QImage
from PySide6.QtWidgets import QApplication

from lodandsy.application.app_controller import AppController
from lodandsy.application.mow_import import apply_import, inspect_source, prepare_import
from lodandsy.application.project_controller import ProjectController
from lodandsy.application.rich_html import text_document
from lodandsy.domain.card import Portrait
from lodandsy.ui.app_shell import AppShell
from lodandsy.ui.theme import apply_theme

app = QApplication([])
apply_theme(app)
window = AppShell()
controller = AppController(window)
project = ProjectController(controller)
root = Path(".prototype-deps").resolve() / f"GUI-check-iteration4-{uuid4().hex[:8]}"
root.mkdir()
project.create_project(root / "Проверка итерации 4")
a = controller.create_card(
    "Эйрин · хранитель перевала", template_id="character", card_type="character"
)
b = controller.create_card("Западный перевал", template_id="location", card_type="location")
controller.session.update_card_fields(
    a.id,
    dict(
        summary="Следопыт, знающий тайные тропы северных гор.",
        tags=("Союзник", "Север"),
        aliases=("Смотритель",),
        race="Человек",
        class_or_role="Следопыт",
        hp=27,
        ac=14,
        speed=30,
        description=text_document(
            "Эйрин встречает путников у старого моста. Он обещал провести караван до рассвета."
        ),
        history=text_document("Десять лет охраняет путь через перевал."),
    ),
)
image = QImage(320, 400, QImage.Format.Format_RGB32)
image.fill(0xFF556E64)
source = root / "portrait.png"
image.save(str(source))
asset = project.store.import_asset(source)
project.assets[asset.id] = asset
controller.session.update_card(
    a.id, portrait=Portrait(asset.id, "Тестовый портрет", "Хранитель перевала")
)
background = QImage(1200, 800, QImage.Format.Format_RGB32)
background.fill(0xFF304B3A)
map_source = root / "map.png"
background.save(str(map_source))
controller.modules.import_map(map_source, "Северные горы")
controller.modules.wait_import()
document = next(iter(controller.modules.session.maps.values()))
controller.modules.session.add_token(document.id, a.id, 400, 350)
controller.modules.session.add_token(document.id, a.id, 600, 450, cells_w=2, cells_h=2)
layer = controller.modules.session.add_layer(document.id, "Декор")
controller.modules.session.add_object(document.id, layer.id, asset.id, 100, 100, 128, 160)
plan = inspect_source(
    Path("docs/iterations/2026-11-19-iteration-4/references/1790538099148-2682f598.md")
)
prepared = prepare_import(
    plan, project.store, controller.cards.all(), tuple(project.assets.values())
)
apply_import(controller.session, prepared)
controller.open_card_editor(b.id)
controller.open_card_editor(a.id)
window.resize(1400, 900)
window.show()
project.save_current()
print(str(root), flush=True)
try:
    app.exec()
finally:
    controller.modules.shutdown()
    controller.card_images.shutdown()
    project.saver.shutdown()
    if project.store:
        project.store.close()
