"""Native, disposable review workspace. All operations use production application services."""

import argparse
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

parser = argparse.ArgumentParser()
parser.add_argument("--prepare-only", action="store_true")
args = parser.parse_args()
app = QApplication([])
apply_theme(app)
window = AppShell()
controller = AppController(window)
project = ProjectController(controller)
root = Path(".prototype-deps").resolve() / f"GUI-check-iteration5-{uuid4().hex[:8]}"
root.mkdir()
project.create_project(root / "Проверка итерации 5")
a = controller.create_card("Эйрин · хранитель перевала", card_type="character")
b = controller.create_card("Западный перевал", card_type="location")
controller.cards_service.update_card_fields(
    a.id,
    dict(
        summary="Следопыт, знающий тайные тропы северных гор.",
        aliases=("Смотритель",),
        race="Человек",
        class_or_role="Следопыт",
        hp=27,
        ac=14,
        speed=30,
        description=text_document(
            "Эйрин встречает путников у старого моста. Он обещал провести караван до рассвета."
        ),
    ),
)
image = QImage(320, 400, QImage.Format.Format_RGB32)
image.fill(0xFF556E64)
source = root / "portrait.png"
image.save(str(source))
asset = project.store.import_asset(source)
project.assets[asset.id] = asset
controller.cards_service.update_card(a.id, portrait=Portrait(asset.id))
background = QImage(1200, 800, QImage.Format.Format_RGB32)
background.fill(0xFF304B3A)
map_source = root / "map.png"
background.save(str(map_source))
controller.maps.import_map(map_source, "Северные горы")
controller.maps.wait_import()
document = next(iter(controller.maps_service.maps.values()))
controller.maps_service.add_token(document.id, a.id, 400, 350)
controller.maps_service.add_token(document.id, a.id, 600, 450, cells_w=2, cells_h=2)
layer = controller.maps_service.add_layer(document.id, "Декор")
controller.maps_service.add_object(document.id, layer.id, asset.id, 100, 100, 128, 160)
plan = inspect_source(
    Path("docs/iterations/2026-11-19-iteration-4/references/1790538099148-2682f598.md")
)
prepared = prepare_import(
    plan, project.store, controller.cards.all(), tuple(project.assets.values())
)
apply_import(controller.cards_service, prepared)
inventory = next(s for s in controller.cards.get(a.id).sections if s.purpose == "inventory")
controller.actions.section_table(a.id, inventory.id)
controller.maps.open_map_editor(document.id)
controller.dice.open()
controller.open_card_editor(b.id)
controller.open_card_editor(a.id)
window.resize(1400, 900)
window.show()
project.save_current()
print(str(root), flush=True)
try:
    project._save_ui_state()
    if not args.prepare_only:
        app.exec()
finally:
    controller.shutdown_features()
    project.saver.shutdown()
    if project.store:
        project.store.close()
