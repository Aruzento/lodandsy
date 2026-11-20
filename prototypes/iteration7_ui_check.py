"""Disposable synthetic world for native manual acceptance; no private references."""

import argparse
from pathlib import Path

from PySide6.QtCore import QSettings
from PySide6.QtGui import QColor, QImage, QPainterPath
from PySide6.QtWidgets import QApplication

from lodandsy.application.app_controller import AppController
from lodandsy.application.project_controller import ProjectController
from lodandsy.application.project_history import ProjectHistory
from lodandsy.domain.card import Portrait
from lodandsy.ui.app_shell import AppShell
from lodandsy.ui.theme import apply_theme


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("world", type=Path)
    args = parser.parse_args()
    if args.world.exists():
        raise ValueError("Choose a fresh disposable world")
    app = QApplication([])
    apply_theme(app)
    window = AppShell()
    owner = AppController(window)
    settings = QSettings(str(args.world.parent / "ui7-user.ini"), QSettings.Format.IniFormat)
    project = ProjectController(owner, ProjectHistory(settings))
    print("create", flush=True)
    project.create_project(args.world)
    image = QImage(600, 600, QImage.Format.Format_ARGB32)
    image.fill(QColor("#547663"))
    for x in range(600):
        for y in range(600):
            if (x // 100 + y // 100) % 2:
                image.setPixelColor(x, y, QColor("#738a94"))
    source = args.world.parent / "synthetic7.png"
    image.save(str(source))
    asset = project.store.import_asset(source)
    project.assets[asset.id] = asset
    cards = []
    print("cards", flush=True)
    for i, kind in enumerate(("character", "location", "item", "article", "note")):
        title = (
            "Серафина"
            if i == 0
            else "Длинное название карточки " * 5
            if i == 1
            else f"Карточка {i + 1}"
        )
        card = owner.create_card(title, card_type=kind)
        owner.cards_service.update_card_fields(
            card.id, {"summary": "Хранительница северных земель. " * (12 if i % 2 else 2)}
        )
        if i % 2 == 0:
            owner.cards_service.update_card(card.id, portrait=Portrait(asset.id))
        owner.open_card_editor(card.id)
        cards.append(card)
    print("map", flush=True)
    document = owner.maps_service.create_map("Проверка презентации7", asset.id)
    owner.maps_service.add_token(document.id, cards[0].id, 300, 300)
    path = QPainterPath()
    path.addRect(200, 200, 250, 250)
    owner.maps_service.edit_fog(document.id, path)
    owner.maps.open_map(document.id)
    owner.maps.open_presentation(document.id)
    print("save", flush=True)
    project.save_current()
    print("show", flush=True)
    window.show()
    owner.open_card_editor(cards[0].id)
    try:
        return app.exec()
    finally:
        owner.shutdown_features()
        project.saver.shutdown()
        if project.store:
            project.store.close()


if __name__ == "__main__":
    raise SystemExit(main())
