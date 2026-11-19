"""Transactional cross-feature use cases; no widgets, workers or SQL."""

from dataclasses import replace

from lodandsy.domain.card import Card, Portrait
from lodandsy.domain.map_document import TokenInstance


class ProjectActions:
    def __init__(self, core, cards, tables, maps):
        self.core, self.cards, self.tables, self.maps = core, cards, tables, maps
        from lodandsy.application.field_edits import FieldEdits
        from lodandsy.domain.module_values import validate_title

        self.title_edits = FieldEdits(
            lambda key: core.entities.get(key[0]).title,
            lambda key, value: self.update_entity(key[0], title=value),
            lambda key, text: validate_title(text),
            {},
            core,
        )
        core.replaced.connect(self.title_edits.discard)
        core.entities_deleted.connect(self.title_edits.remove_entities)

    def update_entity(self, key, **changes):
        if self.core.entities.get(key).kind == "card":
            self.cards.update_card(key, **changes)
            return self.core.entities.get(key)
        return self.core.update(key, **changes)

    def delete_entity(self, key):
        planned = frozenset((key, *self.core.entities.descendant_ids(key)))
        return self.core.delete(key, self.maps.plan_delete(planned))

    def add_card_placement(self, card, map_id, x, y):
        before = self.maps.get_map(map_id)
        token = TokenInstance(card.id, x, y)
        after = replace(before, tokens=(*before.tokens, token))
        from lodandsy.application.maps_service import map_payload

        with self.core.transaction():
            self.core.entities.create(
                "card", card.title, card.payload(), card.parent_id, id=card.id
            )
            self.core.entities.put_payload(map_id, map_payload(after))
            self.maps.record_card_placement(before, after)
            self.core.after_commit(lambda: self.core.entity_created.emit(card.id))
            self.core.after_commit(lambda: self.cards.card_created.emit(card.id))
            self.core.mark_changed()
        return token

    def create_card_placement(self, map_id, title, x, y, *, card_type="character", asset_id=None):
        card = Card(title, card_type=card_type, portrait=Portrait(asset_id) if asset_id else None)
        return self.add_card_placement(card, map_id, x, y)

    def create_object_card(self, title, asset_id):
        with self.core.transaction():
            card = self.cards.create_card(title, card_type="object")
            return self.cards.update_card(card.id, portrait=Portrait(asset_id))

    def section_table(self, card_id, key, *, existing_id=None, replace_link=False, title=None):
        from lodandsy.domain.table_document import ColumnDefinition, inventory_columns

        card = self.cards.cards.get(card_id)
        section = card.section(key)
        if section.kind != "table_ref":
            raise ValueError("Это не табличный раздел")
        target = existing_id if replace_link or not section.table_id else section.table_id
        if target:
            entity = self.core.entities.get(target)
            if entity.kind != "table" or entity.parent_id != card_id:
                raise ValueError("Связанная дочерняя таблица недоступна")
            table = self.tables.get_table(target)
        else:
            columns = (
                inventory_columns()
                if section.purpose == "inventory"
                else (ColumnDefinition("Столбец 1"),)
            )
            table = None
        with self.core.transaction():
            if table is None:
                table = self.tables.create_table(title or section.title, card_id, columns=columns)
            self.cards.update_section(card_id, key, table_id=table.id)
        return table
