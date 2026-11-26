"""Synthetic visual acceptance world; never reads private portraits/reference files."""

import argparse
import time
from pathlib import Path

from PySide6.QtGui import QColor, QImage, QPainter
from PySide6.QtWidgets import QApplication

from lodandsy.application.app_controller import AppController
from lodandsy.application.project_controller import ProjectController
from lodandsy.application.rich_html import sanitize_html
from lodandsy.domain.card import Portrait
from lodandsy.domain.currency import CoinAmount
from lodandsy.ui.app_shell import AppShell
from lodandsy.ui.theme import apply_theme


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("world", type=Path)
    parser.add_argument("--render", type=Path, help="Automated Qt render only, not native capture")
    args = parser.parse_args()
    if args.world.exists():
        raise ValueError("Use a fresh disposable folder; existing worlds are never overwritten")
    app = QApplication([])
    apply_theme(app)
    window = AppShell()
    owner = AppController(window)
    project = ProjectController(owner)
    try:
        project.create_project(args.world)
        folder = owner.create_card("Северные земли", card_type="folder")
        hero = owner.create_card("Серафина · проверка6", folder.id, card_type="character")
        second = owner.create_card("Город Вальмар", folder.id, card_type="location")
        item = owner.create_card("Стальной меч", folder.id, card_type="item")
        owner.cards_service.update_card_fields(
            hero.id,
            {
                "summary": (
                    "Хранительница северных земель. Тестовая карточка без пользовательских данных."
                ),
                "hp": 24,
                "ac": 15,
                "speed": 30,
            },
        )
        owner.cards_service.update_card_fields(
            item.id,
            {"summary": "Клинок из стали", "cost": CoinAmount(owner.economy.currency.base_id, 12)},
        )
        html = sanitize_html(
            "<h1>Легенда северных земель</h1><p>Путешествие начинается "
            "в городе у горных перевалов. Здесь можно готовить заметки, "
            "ссылки и события сессии.</p><blockquote>Каждая дорога ведёт "
            "к новой истории.</blockquote><h2>Встреча с отрядом</h2>"
            "<p>Этот мир создан автоматически только для проверки интерфейса.</p>"
        )[0]
        owner.cards_service.update_section(hero.id, hero.description_id, content=html)
        for i, card in enumerate((hero, second)):
            image = QImage(
                800 if i == 0 else 600, 600 if i == 0 else 900, QImage.Format.Format_ARGB32
            )
            image.fill(QColor("#536d56"))
            painter = QPainter(image)
            painter.fillRect(0, 0, image.width() // 2, image.height() // 2, QColor("#b06450"))
            painter.fillRect(
                image.width() // 2,
                image.height() // 2,
                image.width() // 2,
                image.height() // 2,
                QColor("#746386"),
            )
            painter.end()
            source = args.world.parent / f"synthetic-portrait-{i}.png"
            assert image.save(str(source))
            asset = project.store.import_asset(source)
            project.assets[asset.id] = asset
            side = min(image.width(), image.height()) * 0.8
            crop = (
                (image.width() - side) / image.width() / 2,
                (image.height() - side) / image.height() / 2,
                side / image.width(),
                side / image.height(),
            )
            owner.cards_service.update_card(card.id, portrait=Portrait(asset.id, crop))
        first = owner.open_card_editor(hero.id).widget()
        owner.open_card_editor(second.id)
        section = next(s for s in hero.sections if s.purpose == "inventory")
        inventory = owner.actions.section_table(hero.id, section.id)
        view = owner.tables.open_table(inventory.id).widget()
        view.add_row()
        view.model.setData(view.model.index(0, 0), item.id)
        view.model.setData(view.model.index(0, 1), "2")
        owner.dice.open()
        owner.open_card_editor(hero.id)
        owner.core.select(hero.id)
        window.show()
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            app.processEvents()
            if first.portrait_panel._image is not None:
                break
            time.sleep(0.005)
        assert project.save_current()
        project._save_ui_state()
        app.processEvents()
        if args.render:
            assert window.grab().save(str(args.render))
        print(str(args.world.resolve()))
    finally:
        window.close_guard = None
        owner.shutdown_features()
        project.saver.shutdown()
        if project.store:
            project.store.close()
        window.close()


if __name__ == "__main__":
    main()
