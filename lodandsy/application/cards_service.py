"""Cards mutations/queries/drafts. Core owns hierarchy and project selection."""

from dataclasses import replace

from PySide6.QtCore import QObject, Signal

from lodandsy.application.entity_session import EntitySession
from lodandsy.application.field_edits import FieldEdits
from lodandsy.domain.actor_state import ActorRef, ActorState, ValueAddress, VariableValue
from lodandsy.domain.card import EMPTY_DOCUMENT, Card
from lodandsy.domain.card_collection import CardCollection
from lodandsy.domain.card_schema import (
    ACTOR_TYPES,
    CARD_TYPES,
    FIELD_DEFINITIONS,
    field_definition,
    permitted_fields,
)
from lodandsy.domain.currency import CoinAmount
from lodandsy.domain.entity_reference import ReferenceInfo
from lodandsy.domain.project_settings import ProjectSettings
from lodandsy.domain.rules_5e14 import ProjectRules, calculate


class CardsService(QObject):
    field_draft_changed = Signal(str, object)
    current_card_changed = Signal(object)
    card_created = Signal(str)
    card_changed = Signal(str, object)
    cards_deleted = Signal(object)
    cards_replaced = Signal()
    actor_changed = Signal(str, str, object)
    rules_changed = Signal()
    economy_changed = Signal()
    base_effective_changed = Signal(str)

    def __init__(self, cards=None, parent=None, *, core=None):
        super().__init__(parent)
        self.core = (
            core
            if core is not None
            else EntitySession(cards.entities if cards is not None else None, self)
        )
        self.cards = cards if cards is not None else CardCollection(entities=self.core.entities)
        self.cards.enable_addressed_validation()
        self.field_drafts = {}
        from lodandsy.domain.card_schema import parse_field

        self.field_edits = FieldEdits(
            self._read_edit,
            self._write_edit,
            lambda key, text: text if key[1] == "actor_name" else parse_field(key[1], text),
            self.field_drafts,
            self,
            self._publish_draft,
        )
        self.field_edits.format_value = self.format_value
        self._reference_cache = {}
        self.calculation_inputs = lambda card, actor: {}
        self.create_inventory = lambda card_id, name: None
        self._effective_cache = {}
        self._published_effective = {}
        self.core.prepare = self.reconcile
        self.current_entity_changed = self.core.selection_changed
        self.entity_changed = self.core.entity_changed
        self.entity_created = self.core.entity_created
        self.entities_deleted = self.core.entities_deleted
        self.entities_replaced = self.core.replaced
        self.core.selection_changed.connect(
            lambda key: self.current_card_changed.emit(self.current_card_id)
        )
        self.core.entities_deleted.connect(self._deleted)
        self.core.replaced.connect(self._replaced)

    @property
    def entities(self):
        return self.core.entities

    @property
    def current_entity_id(self):
        return self.core.selected_id

    @property
    def current_entity(self):
        return self.entities.get(self.core.selected_id) if self.core.selected_id else None

    def select_entity(self, key):
        self.core.select(key)

    def clear_selection(self):
        self.core.select(None)

    def _deleted(self, keys):
        self.field_edits.clear(set(keys))
        for key in keys:
            self._reference_cache.pop(key, None)
        for identity in tuple(self._published_effective):
            if identity[0] in keys:
                self._published_effective.pop(identity)
        for identity in tuple(self.field_drafts):
            if identity[0] in keys:
                self.field_drafts.pop(identity, None)
        self.cards_deleted.emit(keys)

    def _replaced(self):
        self.field_edits.clear()
        self._reference_cache.clear()
        self._effective_cache.clear()
        self._published_effective.clear()
        self.cards = CardCollection(entities=self.core.entities)
        self.cards.enable_addressed_validation()
        self.field_drafts.clear()
        self.cards_replaced.emit()

    def replace_cards(self, cards):
        self.core.replace(cards.entities)

    def get_card(self, key):
        return self.cards.get(key)

    @property
    def settings(self):
        return self.entities.settings or ProjectSettings()

    @property
    def rules(self):
        return self.settings.rules or ProjectRules()

    def effective(self, reference, *, rules=None):
        card_id = reference.card_id if isinstance(reference, ActorRef) else reference
        card = self.get_card(card_id)
        actor = card.actor(reference.actor_id) if isinstance(reference, ActorRef) else None
        inputs = self.calculation_inputs(card, actor)
        rules = rules or self.rules
        signature = (
            card.id,
            card.title,
            card.card_type,
            card.values,
            actor,
            rules,
            tuple(sorted(inputs.items())),
        )
        value = self._effective_cache.get(signature)
        if value is None:
            value = calculate(card, actor, rules, **inputs)
            if len(self._effective_cache) >= 2048:
                self._effective_cache.clear()
            self._effective_cache[signature] = value
        return value

    def reconcile(self, changes, *, complete=False):
        """Runs inside the outer transaction before validation/publication."""
        previous = {change.id: change.before_payload for change in changes.aggregates}
        removed = set()
        for change in changes.aggregates:
            before = getattr(change.before_payload, "actors", ())
            after = getattr(change.after_payload, "actors", ())
            if before != after:
                live = {actor.id for actor in after}
                removed.update((change.id, actor.id) for actor in before if actor.id not in live)
        if removed:

            def retire():
                addresses = {
                    key
                    for key in self.field_edits.keys
                    if isinstance(key, ValueAddress) and (key.card_id, key.actor_id) in removed
                }
                self.field_edits.discard_keys(addresses)
                for identity in removed:
                    self._published_effective.pop(identity, None)

            self.core.after_commit(retire)
        for card_id, contexts in self.cards.affected_contexts(changes, complete=complete).items():
            card = self.get_card(card_id)
            if None in contexts and card.card_type in ACTOR_TYPES:
                base = self.effective(card.id)
                signature = tuple(
                    (key, v.value, v.source, v.status, v.diagnostic)
                    for key, v in base.values.items()
                    if key in base.automatic
                )
                signature = (signature, base.equipment, base.sources)
                identity = card.id, None
                if self._published_effective.get(identity) != signature:

                    def publish_base(key=card.id, identity=identity, signature=signature):
                        self._published_effective[identity] = signature
                        self.base_effective_changed.emit(key)

                    self.core.after_commit(publish_base)
            actors = []
            for actor in card.actors:
                if actor.id not in contexts:
                    actors.append(actor)
                    continue
                effective = self.effective(ActorRef(card.id, actor.id))
                maximum = effective.get("hp_max")
                signature = tuple(
                    (key, value.value, value.source, value.status, value.diagnostic)
                    for key, value in effective.values.items()
                    if key in effective.automatic
                )
                signature = (signature, effective.equipment, effective.sources)
                identity = card.id, actor.id
                if self._published_effective.get(identity) != signature:

                    def publish(key=identity, result=signature):
                        self._published_effective[key] = result
                        self.actor_changed.emit(*key, frozenset({"effective"}))

                    self.core.after_commit(publish)
                current = actor.value("hp_current")
                if maximum.status == "ok" and current is not None and current > maximum.value:
                    old_actor = next(
                        (
                            a
                            for a in getattr(
                                previous.get(card.id, self.entities.payload(card.id)), "actors", (),
                            )
                            if a.id == actor.id
                        ),
                        None,
                    )
                    if old_actor is None or old_actor.value("hp_current") != current:
                        raise ValueError("Введённое текущее HP превышает максимум")
                    actor = actor.with_fields({"hp_current": maximum.value})
                actors.append(actor)
            if tuple(actors) != card.actors:
                self._update_card(card.id, actors=tuple(actors))

    @staticmethod
    def format_value(key, value):
        import json
        from dataclasses import asdict

        from lodandsy.application.field_edits import value_text

        if key[1] == "modifiers":
            return json.dumps([asdict(modifier) for modifier in value], ensure_ascii=False)
        if isinstance(value, CoinAmount):
            return value.to_text()
        return value_text(value)

    def participant_info(self, card_id, actor_id):
        reference = ActorRef(card_id, actor_id)
        actor = self.get_actor(reference)
        effective = self.effective(reference)
        maximum, current = effective.get("hp_max"), actor.value("hp_current")
        max_text = str(maximum.value) if maximum.status == "ok" else "—"
        summary = f"Хиты: {current if current is not None else '—'} / {max_text}"
        if actor.value("hp_temp"):
            summary += f" · временные {actor.value('hp_temp')}"
        if maximum.status == "ok" and maximum.value > 0 and current is not None:
            summary += f" · {100 * current / maximum.value:.1f}%"
        for key in ("ac", "speed"):
            value = effective.get(key)
            label = "КД" if key == "ac" else "Скорость, фт."
            summary += f" · {label}: {value.value if value.status == 'ok' else '—'}"
        return actor.name, summary, actor.inventory_id

    def preview_rules(self, overrides, *, expected_revision=None):
        if expected_revision is not None and self.rules.revision != expected_revision:
            raise ValueError("Правила изменились; обновите preview")
        candidate = ProjectRules(revision=self.rules.revision + 1, overrides=tuple(overrides))
        clamps = []
        for card in self.cards.all():
            contexts = (card.id, *(ActorRef(card.id, actor.id) for actor in card.actors))
            for context in contexts:
                values = self.effective(context, rules=candidate)
                errors = [
                    f"{key}: {value.diagnostic}"
                    for key, value in values.automatic.items()
                    if value.status == "error"
                ]
                if errors:
                    raise ValueError(card.title + ": " + "; ".join(errors))
                if isinstance(context, ActorRef):
                    actor = card.actor(context.actor_id)
                    maximum, current = values.get("hp_max"), actor.value("hp_current")
                    if maximum.status == "ok" and current is not None and current > maximum.value:
                        clamps.append((context, current, maximum.value))
        return candidate, self.core.serial, tuple(clamps)

    def apply_rules(self, preview):
        candidate, serial, clamps = preview
        if serial != self.core.serial or candidate.revision != self.rules.revision + 1:
            raise ValueError("Preview устарел; повторите проверку")
        with self.core.transaction():
            self.entities.put_settings(replace(self.settings, rules=candidate))
            self.core.after_commit(self.rules_changed.emit)
            self.core.mark_changed()
        return clamps

    def preview_effects(self, preview):
        candidate, serial, _ = preview
        if serial != self.core.serial or candidate.revision != self.rules.revision + 1:
            raise ValueError("Preview устарел; повторите проверку")
        changes = []
        for card in self.cards.all():
            if card.card_type not in ACTOR_TYPES:
                continue
            for context in (card.id, *(ActorRef(card.id, a.id) for a in card.actors)):
                before, after = self.effective(context), self.effective(context, rules=candidate)
                label = self.get_actor(context).name if isinstance(context, ActorRef) else "База"
                for key, value in after.automatic.items():
                    old = before.automatic[key]
                    if (old.value, old.status) != (value.value, value.status):
                        changes.append((card.title, label, key, old, value))
        return tuple(changes)

    def _read_edit(self, key):
        if isinstance(key, ValueAddress) and key.actor_id is not None:
            actor = self.get_actor(ActorRef(key.card_id, key.actor_id))
            return actor.name if key.field_id == "actor_name" else actor.value(key.field_id)
        return self.cards.get(key[0]).value(key[1])

    def _write_edit(self, key, value):
        if isinstance(key, ValueAddress) and key.actor_id is not None:
            return self.update_actor(ActorRef(key.card_id, key.actor_id), {key.field_id: value})
        return self.update_card_fields(key[0], {key[1]: value})

    def _publish_draft(self, key, raw):
        if isinstance(key, ValueAddress) and key.actor_id is not None:
            if raw is None:
                self.field_drafts.pop(key, None)
            else:
                self.field_drafts[key] = raw
            self.actor_changed.emit(key.card_id, key.actor_id, frozenset({"draft"}))
        else:
            self.set_field_draft(key[0], key[1], raw)

    def read_value(self, address):
        if address.field_id == "actor_name" and address.actor_id is None:
            raise ValueError("Имя участника требует Actor")
        if address.field_id != "actor_name" and field_definition(address.field_id).scope != (
            "actor" if address.actor_id else "card"
        ):
            raise ValueError("Неверный владелец значения")
        value = self._read_edit(address)
        owner = (
            self.get_actor(ActorRef(address.card_id, address.actor_id))
            if address.actor_id
            else self.get_card(address.card_id)
        )
        present = address.field_id in dict(owner.values)
        if address.field_id in {"title", "description", "actor_name"}:
            return VariableValue(value, "present", "actor" if address.actor_id else "document")
        return VariableValue(
            value,
            "null" if present and value is None else "present" if present else "absent",
            ("actor" if address.actor_id else "card") if present else "default",
        )

    def read_effective(self, reference, field_id):
        return self.effective(reference).get(field_id)

    def update_values(self, owner, patch, *, expected_values=None):
        if isinstance(owner, ActorRef):
            return self.update_actor(owner, patch, expected_values=expected_values)
        card = self.get_card(owner)
        for key, expected in (expected_values or {}).items():
            if card.value(key) != expected and patch.get(key) != card.value(key):
                raise ValueError("Значение изменено другим представлением")
        return self.update_card_fields(owner, patch)

    def get_actor(self, reference):
        return self.cards.get(reference.card_id).actor(reference.actor_id)

    def list_actors(self, card_id):
        return self.cards.get(card_id).actors

    def create_actor(self, card_id, *, name=None, inventory_id=None, set_default=False):
        with self.core.transaction():
            card = self.get_card(card_id)
            if card.card_type not in ACTOR_TYPES:
                raise ValueError("Этот тип не поддерживает участников")
            names = {actor.name for actor in card.actors}
            number = 1
            prefix = card.title[:1960]
            while f"{prefix} №{number}" in names:
                number += 1
            name = name or f"{prefix} №{number}"
            inventory_id = inventory_id or self.create_inventory(card_id, name)
            reference = self._create_actor(
                card_id, name=name, inventory_id=inventory_id, set_default=set_default
            )
        return reference

    def _create_actor(self, card_id, *, name=None, inventory_id=None, set_default=False):
        card = self.get_card(card_id)
        if card.card_type not in ACTOR_TYPES:
            raise ValueError("Этот тип не поддерживает участников")
        actor = ActorState(
            name,
            (("hp_current", card.value("hp_max")), ("hp_temp", 0)),
            inventory_id=inventory_id,
        )
        maximum = calculate(card, actor, self.rules, **self.calculation_inputs(card, actor)).get(
            "hp_max"
        )
        actor = actor.with_fields(
            {
                "hp_current": maximum.value if maximum.status == "ok" else None,
            }
        )
        self.update_card(
            card_id,
            actors=(*card.actors, actor),
            default_actor_id=actor.id if set_default else card.default_actor_id,
        )
        return ActorRef(card_id, actor.id)

    def update_actor(self, reference, changes, *, expected_values=None):
        from dataclasses import replace

        card = self.get_card(reference.card_id)
        actor = card.actor(reference.actor_id)
        for key, value in (expected_values or {}).items():
            current = actor.name if key == "actor_name" else actor.value(key)
            if current != value and changes.get(key) != current:
                raise ValueError("Участник изменён в другом представлении")
        name = changes.get("actor_name", actor.name)
        values = {k: v for k, v in changes.items() if k != "actor_name"}
        updated = replace(actor.with_fields(values), name=name)
        maximum = calculate(
            card, updated, self.rules, **self.calculation_inputs(card, updated)
        ).get("hp_max")
        if (
            "hp_current" in changes
            and maximum.status == "ok"
            and updated.value("hp_current") is not None
        ):
            if updated.value("hp_current") > maximum.value:
                raise ValueError("Текущее HP превышает максимум")
        self.update_card(
            card.id, actors=tuple(updated if a.id == actor.id else a for a in card.actors)
        )
        return updated

    def set_player(self, card_id, enabled, *, actor_id=None, create=False):
        with self.core.transaction():
            card = self.get_card(card_id)
            if enabled:
                if create or not card.actors:
                    reference = self.create_actor(card_id, set_default=True)
                    actor_id = reference.actor_id
                elif actor_id is None:
                    raise ValueError("Выберите основного участника явно")
                self.get_card(card_id).actor(actor_id)
                self.update_card(card_id, default_actor_id=actor_id)
            self.update_card_fields(card_id, {"player": enabled})

    def all(self):
        return self.cards.all()

    def prepare_card(self, title, parent_id=None, *, card_type="note"):
        return Card(title, parent_id=parent_id, card_type=card_type)

    def reference_info(self, key):
        from lodandsy.application.rich_html import html_text

        card = self.cards.get(key)
        cached = self._reference_cache.get(key)
        if cached is not None and cached[0] is card:
            return cached[1]
        summary = card.value("summary") or ""
        previous = cached[0] if cached is not None else None
        if summary.strip():
            preview = " ".join(summary.split())
        elif (
            previous is not None
            and previous.sections == card.sections
            and not previous.value("summary")
        ):
            preview = cached[1].value("description_preview")
        else:
            preview = " ".join(html_text(card.content).split())
        if len(preview) > 240:
            preview = preview[:237] + "…"
        values = tuple(
            (name, card.value(name))
            for name in sorted(permitted_fields(card.card_type))
            if name not in {"description", "aliases"}
            and field_definition(name).data_type not in {"modifier_list", "number_list"}
        )
        info = ReferenceInfo(
            card.id,
            "card",
            card.title,
            card_type=card.card_type,
            aliases=card.value("aliases") or (),
            image_id=card.portrait.asset_id if card.portrait else None,
            fields=(*values, ("description_preview", preview)),
        )
        self._reference_cache[key] = (card, info)
        return info

    @staticmethod
    def reference_types():
        return tuple((definition.title, key) for key, definition in CARD_TYPES.items())

    @staticmethod
    def projection_fields():
        return (
            ("Описание", "description_preview"),
            *(
                (definition.label, key)
                for key, definition in FIELD_DEFINITIONS.items()
                if key not in {"aliases", "description"}
                and definition.scope == "card"
                and definition.data_type not in {"modifier_list", "number_list"}
            ),
        )

    def create_card(self, title, parent_id=None, *, card_type="note"):
        with self.core.transaction():
            card = self.cards.create(title, parent_id, card_type=card_type)
            self.core.after_commit(lambda: self.core.entity_created.emit(card.id))
            self.core.after_commit(lambda: self.card_created.emit(card.id))
            self.core.mark_changed()
        return card

    def update_card(self, card_id, **changes):
        with self.core.transaction():
            self._update_card(card_id, **changes)
        return self.get_card(card_id)

    def set_field_draft(self, key, field, raw):
        self.cards.get(key)
        identity = key, field
        before = self.field_drafts.get(identity)
        if raw is None:
            self.field_drafts.pop(identity, None)
        else:
            self.field_drafts[identity] = raw
        if before != raw:
            self.field_draft_changed.emit(key, frozenset({field}))

    def discard_field_drafts(self, key):
        self.field_edits.clear({key})
        for identity in tuple(self.field_drafts):
            if identity[0] == key:
                self.set_field_draft(key, identity[1], None)

    def add_card_field(self, card_id, key):
        after = self.cards.get(card_id).add_field(key)
        return self.update_card(card_id, values=after.values)

    def update_section(self, card_id, section_id, **changes):
        from dataclasses import replace

        if changes.keys() - {"title", "content", "table_id"}:
            raise ValueError("Неподдерживаемые изменения раздела")
        card = self.cards.get(card_id)
        card.section(section_id)
        sections = tuple(
            replace(section, **changes) if section.id == section_id else section
            for section in card.sections
        )
        return self.update_card(card_id, sections=sections)

    def add_section(self, card_id, title, *, kind="rich_text", table_id=None):
        from lodandsy.domain.card import CardSection

        card = self.cards.get(card_id)
        if table_id is not None:
            entity = self.entities.get(table_id)
            if entity.kind != "table" or entity.parent_id != card_id:
                raise ValueError("Выберите дочернюю таблицу карточки")
        section = CardSection(
            title,
            len(card.sections),
            kind,
            content=EMPTY_DOCUMENT if kind == "rich_text" else None,
            table_id=table_id,
        )
        self.update_card(card_id, sections=(*card.sections, section))
        return section

    def delete_section(self, card_id, key):
        from dataclasses import replace

        card = self.cards.get(card_id)
        card.section(key)
        sections = tuple(
            replace(s, position=i) for i, s in enumerate(s for s in card.sections if s.id != key)
        )
        self.update_card(card_id, sections=sections)
        self.set_field_draft(card_id, key, None)

    def move_section(self, card_id, key, position):
        from dataclasses import replace

        card = self.cards.get(card_id)
        sections = list(card.sections)
        if type(position) is not int or not 0 <= position < len(sections):
            raise ValueError("Invalid section position")
        section = card.section(key)
        sections.remove(section)
        sections.insert(position, section)
        self.update_card(
            card_id, sections=tuple(replace(s, position=i) for i, s in enumerate(sections))
        )

    def update_card_fields(self, card_id, changes):
        if not isinstance(changes, dict):
            raise ValueError("Ожидается набор полей")
        before = self.cards.get(card_id)
        after = before.with_fields(changes)
        return self.update_card(
            card_id,
            title=after.title,
            sections=after.sections,
            portrait=after.portrait,
            values=after.values,
        )

    def _update_card(self, card_id: str, **changes: object) -> Card:
        previous = self.cards.get(card_id)
        if "content" in changes:
            from lodandsy.application.rich_html import validate_html

            validate_html(changes["content"])
        if "sections" in changes:
            from lodandsy.application.rich_html import validate_html

            previous_sections = {section.id: section for section in previous.sections}
            for section in changes["sections"]:
                old = previous_sections.get(section.id)
                if section.kind == "rich_text" and (old is None or old.content != section.content):
                    validate_html(section.content)
        previous_position = (
            self.cards.position(card_id) if changes.keys() & {"position", "parent_id"} else None
        )
        card = self.cards.update(card_id, **changes)
        fields = frozenset(
            field
            for field in changes
            if field not in {"position", "values", "content", "actors", "default_actor_id"}
            if getattr(previous, field) != getattr(card, field)
        )
        old_sections = {s.id: s for s in previous.sections}
        new_sections = {s.id: s for s in card.sections}
        fields |= {
            key
            for key in old_sections.keys() | new_sections.keys()
            if old_sections.get(key) != new_sections.get(key)
        }
        fields |= set(dict(previous.values)) ^ set(dict(card.values))
        fields |= {key for key in FIELD_DEFINITIONS if previous.value(key) != card.value(key)}
        old_actors = {a.id: a for a in previous.actors}
        new_actors = {a.id: a for a in card.actors}
        actor_changes = {}
        for key in old_actors.keys() | new_actors.keys():
            if old_actors.get(key) != new_actors.get(key):
                actor_changes[key] = frozenset({"state", "name", "inventory"})
        if previous.default_actor_id != card.default_actor_id:
            fields |= {"default_actor_id"}
        if previous_position is not None and previous_position != self.cards.position(card_id):
            fields |= {"position"}
        if fields or actor_changes:
            structural = fields & {"title", "parent_id", "position"}
            if structural:
                self.core.after_commit(lambda: self.core.entity_changed.emit(card_id, structural))
            if fields:
                self.core.after_commit(lambda: self.card_changed.emit(card_id, fields))
            for actor_id, changed in actor_changes.items():
                self.core.after_commit(
                    lambda a=actor_id, f=changed: self.actor_changed.emit(card_id, a, f)
                )
            for removed in old_sections.keys() - new_sections.keys():
                self.field_drafts.pop((card_id, removed), None)
            self.core.mark_changed()
        return card

    @property
    def current_card_id(self) -> str | None:
        entity = self.current_entity
        return entity.id if entity and entity.kind == "card" else None

    @property
    def current_card(self) -> Card | None:
        if self.current_card_id is None:
            return None

        return self.cards.get(self.current_card_id)

    def select_card(
        self,
        card_id: str,
    ) -> None:
        self.cards.get(card_id)

        self.select_entity(card_id)
