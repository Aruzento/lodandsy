"""Transactional cross-feature use cases; no widgets, workers or SQL."""

from dataclasses import replace

from PySide6.QtGui import QUndoCommand

from lodandsy.application.maps_service import map_payload
from lodandsy.domain.actor_state import ActorRef
from lodandsy.domain.card import Card, Portrait
from lodandsy.domain.card_schema import ACTOR_TYPES
from lodandsy.domain.document_payloads import inventory_inputs
from lodandsy.domain.entity import EntityCollection
from lodandsy.domain.map_document import TokenInstance


class PlacementEdit(QUndoCommand):
    """Receipt for one already-applied placement; unrelated state is never restored."""

    def __init__(self, actions, map_id, token, created_actor, default_before, inventory):
        super().__init__("Разместить карточку")
        self.actions, self.map_id, self.token = actions, map_id, token
        self.actor, self.default_before, self.inventory = created_actor, default_before, inventory
        self.default_after = actions.cards.get_card(token.card_id).default_actor_id
        self.generation = actions.core.generation
        self.initial = True

    def candidate(self, redo):
        actions, core = self.actions, self.actions.core
        if self.generation != core.generation:
            raise ValueError("История относится к другому проекту")
        records = {e.id: (e, core.entities.payload(e.id)) for e in core.entities.summaries()}
        document = actions.maps.get_map(self.map_id)
        actual = next((t for t in document.tokens if t.id == self.token.id), None)
        if actual != (None if redo else self.token):
            raise ValueError("Размещение изменено независимо")
        tokens = (
            (*document.tokens, self.token)
            if redo
            else tuple(t for t in document.tokens if t.id != self.token.id)
        )
        records[self.map_id] = (
            records[self.map_id][0],
            map_payload(replace(document, tokens=tokens)),
        )
        if self.actor is not None:
            card = actions.cards.get_card(self.token.card_id)
            existing = next((a for a in card.actors if a.id == self.actor.id), None)
            if existing != (None if redo else self.actor):
                raise ValueError("Состояние участника изменено; отмена создания недоступна")
            if not redo and any(
                t.actor_id == self.actor.id and t.id != self.token.id
                for m in actions.maps.maps.values()
                for t in m.tokens
            ):
                raise ValueError("У участника появились другие размещения")
            default = card.default_actor_id
            if self.default_before != self.default_after:
                if default != (self.default_before if redo else self.default_after):
                    raise ValueError("Выбор основного участника изменён")
                default = self.default_after if redo else self.default_before
            elif not redo and default == self.actor.id:
                raise ValueError("Участник позднее назначен основным")
            actors = (
                (*card.actors, self.actor)
                if redo
                else tuple(a for a in card.actors if a.id != self.actor.id)
            )
            records[card.id] = (
                records[card.id][0],
                replace(card.payload(), actors=actors, default_actor_id=default),
            )
            if self.inventory is not None:
                entity, payload = self.inventory
                if not redo:
                    if records.get(entity.id) != self.inventory:
                        raise ValueError("Инвентарь участника изменён")
                    del records[entity.id]
                    for key, (node, data) in tuple(records.items()):
                        if node.parent_id == entity.parent_id and node.position > entity.position:
                            records[key] = (replace(node, position=node.position - 1), data)
                else:
                    if entity.id in records:
                        raise ValueError("UUID инвентаря уже занят")
                    for key, (node, data) in tuple(records.items()):
                        if node.parent_id == entity.parent_id and node.position >= entity.position:
                            records[key] = (replace(node, position=node.position + 1), data)
                    records[entity.id] = self.inventory
        return records

    def check(self, redo):
        records = self.candidate(redo)
        core = self.actions.core
        EntityCollection(
            records.values(), settings=core.entities.settings, validator=core.entities.validator
        )

    def apply(self, redo):
        records = self.candidate(redo)
        actions, core = self.actions, self.actions.core
        with core.transaction():
            if self.actor is not None:
                entity, payload = records[self.token.card_id]
                actions.cards.update_card(
                    entity.id, actors=payload.actors, default_actor_id=payload.default_actor_id
                )
                if self.inventory is not None:
                    inventory, data = self.inventory
                    if redo:
                        core.entities.create(
                            "table", inventory.title, data, inventory.parent_id, id=inventory.id
                        )
                        core.entities.update(inventory.id, position=inventory.position)
                        core.after_commit(lambda: core.entity_created.emit(inventory.id))
                    else:
                        core.delete(inventory.id)
            actions.maps.commit_placements(self.map_id, records[self.map_id][1].tokens)

    def undo(self):
        self.apply(False)

    def redo(self):
        if self.initial:
            self.initial = False
        else:
            self.apply(True)


class ProjectActions:
    def __init__(self, core, cards, tables, maps):
        self.core, self.cards, self.tables, self.maps = core, cards, tables, maps
        cards.create_inventory = self.create_actor_inventory
        cards.calculation_inputs = lambda card, actor: inventory_inputs(core.entities, card, actor)
        maps.place_card = self.place_card
        maps.validate_change = self.validate_map_candidate
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

    def validate_map_candidate(self, document):
        records = [
            (e, map_payload(document) if e.id == document.id else self.core.entities.payload(e.id))
            for e in self.core.entities.summaries()
        ]
        EntityCollection(
            records, settings=self.core.entities.settings, validator=self.core.entities.validator
        )

    def place_card(self, map_id, card_id, x, y, *, actor_id=None, **presentation):
        before = self.cards.get_card(card_id)
        created, inventory = None, None
        default_before = before.default_actor_id
        with self.core.transaction():
            if actor_id is None and before.card_type in ACTOR_TYPES:
                if before.value("player") and before.default_actor_id is not None:
                    actor_id = before.default_actor_id
                else:
                    if before.value("player") and before.actors:
                        raise ValueError("Выберите основного участника во вкладке «Связи»")
                    ref = self.cards.create_actor(card_id, set_default=before.value("player"))
                    actor_id = ref.actor_id
                    created = self.cards.get_actor(ref)
                    if created.inventory_id is not None:
                        inventory = (
                            self.core.entities.get(created.inventory_id),
                            self.core.entities.payload(created.inventory_id),
                        )
            if actor_id is not None:
                self.cards.get_actor(ActorRef(card_id, actor_id))
            token = TokenInstance(card_id, x, y, actor_id=actor_id, **presentation)
            document = self.maps.get_map(map_id)
            self.maps.commit_placements(map_id, (*document.tokens, token))
            receipt = PlacementEdit(self, map_id, token, created, default_before, inventory)
            self.core.after_commit(lambda: self.maps.record_operation(map_id, receipt))
        return token

    def copy_token(self, map_id, token_id, *, x=None, y=None):
        document = self.maps.get_map(map_id)
        token = next((t for t in document.tokens if t.id == token_id), None)
        if token is None:
            raise ValueError("Токен отсутствует")
        return self.place_card(
            map_id,
            token.card_id,
            token.x + 16 if x is None else x,
            token.y + 16 if y is None else y,
            cells_w=token.cells_w,
            cells_h=token.cells_h,
            z=token.z,
            label_override=token.label_override,
            image_override=token.image_override,
            kind_override=token.kind_override,
            layer_id=token.layer_id,
        )

    def create_actor_inventory(self, card_id, name):
        card = self.cards.get_card(card_id)
        source_id = next((s.table_id for s in card.sections if s.purpose == "inventory"), None)
        if source_id is not None and self.core.entities.get(source_id).parent_id != card_id:
            raise ValueError("Базовая таблица инвентаря больше не принадлежит Card")
        return self.tables.clone_inventory(source_id, card_id, name[:1980] + " — Инвентарь").id

    def actor_placements(self, reference):
        return tuple(
            (document.id, token.id, document.title)
            for document in self.maps.maps.values()
            for token in document.tokens
            if token.actor_id == reference.actor_id and token.card_id == reference.card_id
        )

    def delete_actor(self, reference, *, confirmed=False):
        card, actor = self.cards.get_card(reference.card_id), self.cards.get_actor(reference)
        if not confirmed:
            raise ValueError("Подтвердите удаление участника, инвентаря и всех размещений")
        if actor.inventory_id is not None and self.core.entities.child_ids(actor.inventory_id):
            raise ValueError("В инвентаре есть дочерние документы: перенесите их перед удалением")
        with self.core.transaction():
            for document in self.maps.maps.values():
                tokens = tuple(t for t in document.tokens if t.actor_id != reference.actor_id)
                if tokens != document.tokens:
                    self.maps.commit_placements(document.id, tokens)
            self.cards.update_card(
                card.id,
                actors=tuple(a for a in card.actors if a.id != actor.id),
                default_actor_id=None
                if card.default_actor_id == actor.id
                else card.default_actor_id,
            )
            if actor.inventory_id is not None:
                self.core.delete(actor.inventory_id)

    def update_entity(self, key, **changes):
        if self.core.entities.get(key).kind == "card":
            self.cards.update_card(key, **changes)
            return self.core.entities.get(key)
        return self.core.update(key, **changes)

    def delete_entity(self, key):
        planned = frozenset((key, *self.core.entities.descendant_ids(key)))
        if any(
            a.inventory_id in planned and card.id not in planned
            for card in self.cards.all()
            for a in card.actors
        ):
            raise ValueError("Инвентарь принадлежит участнику; удалите участника явно")
        return self.core.delete(key, self.maps.plan_delete(planned))

    def deletion_details(self, keys):
        actors = [
            (card, actor) for card in self.cards.all() if card.id in keys for actor in card.actors
        ]
        if not actors:
            return ""
        inventories = sum(a.inventory_id is not None for _, a in actors)
        return (
            f"\n\nУчастников: {len(actors)}; индивидуальных инвентарей: {inventories}. "
            "Их состояние будет удалено без Undo.\n"
            + "\n".join(f"{card.title} / {actor.name}" for card, actor in actors[:20])
            + (f"\nЕщё участников: {len(actors) - 20}" if len(actors) > 20 else "")
        )

    def add_card_placement(self, card, map_id, x, y, *, player=False):
        with self.core.transaction():
            self.core.entities.create(
                "card", card.title, card.payload(), card.parent_id, id=card.id
            )
            if player:
                self.cards.set_player(card.id, True, create=True)
            token = self.place_card(map_id, card.id, x, y)
            self.core.after_commit(lambda: self.core.entity_created.emit(card.id))
            self.core.after_commit(lambda: self.cards.card_created.emit(card.id))
            self.core.mark_changed()
        return token

    def create_card_placement(
        self, map_id, title, x, y, *, card_type="character", asset_id=None, player=False
    ):
        card = Card(title, card_type=card_type, portrait=Portrait(asset_id) if asset_id else None)
        return self.add_card_placement(card, map_id, x, y, player=player)

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
