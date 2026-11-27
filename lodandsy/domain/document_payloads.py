from lodandsy.domain.card import Card, CardPayload
from lodandsy.domain.card_schema import ACTOR_TYPES, field_definition
from lodandsy.domain.currency import validate_wallet
from lodandsy.domain.entity import Entity, EntityCollection
from lodandsy.domain.equipment import EquipmentEntry, resolve_equipment
from lodandsy.domain.map_document import MapDocument, MapPayload
from lodandsy.domain.modifiers import ModifierSource
from lodandsy.domain.project_settings import ProjectSettings
from lodandsy.domain.rules_5e14 import ProjectRules, calculate
from lodandsy.domain.table_document import TableDocument, TablePayload


def inventory_inputs(collection, card, actor):
    entries, missing = [], []
    table_id = (
        actor.inventory_id
        if actor is not None
        else next((s.table_id for s in card.sections if s.purpose == "inventory"), None)
    )
    if table_id is None:
        return dict(sources=(), inventory_weight=0, incomplete="", equipment=resolve_equipment(()))
    try:
        target = collection.get(table_id)
        if target.kind != "table" or target.parent_id != card.id:
            raise ValueError("Inventory link is unavailable")
        payload = collection.payload(table_id)
    except ValueError:
        return dict(
            sources=(),
            inventory_weight=None,
            incomplete="Связанная таблица недоступна",
            equipment=resolve_equipment((), missing=(table_id,)),
        )
    try:
        validate_inventory_columns(collection, table_id)
    except ValueError as error:
        return dict(
            sources=(),
            inventory_weight=None,
            incomplete=str(error),
            equipment=resolve_equipment((), missing=(table_id,)),
        )
    columns = {column.key: column for column in payload.columns if column.key}
    item_column, quantity = columns.get("item"), columns.get("quantity")
    if item_column is None or quantity is None:
        return dict(
            sources=(),
            inventory_weight=None,
            incomplete="Нужны столбцы item/quantity",
            equipment=resolve_equipment((), missing=(table_id,)),
        )
    active, sources, weight, complete, diagnostic = columns.get("active"), [], 0, True, ""
    for row in payload.rows:
        target = row.value(item_column.id)
        count = row.value(quantity.id)
        enabled = active is not None and row.value(active.id) is True
        try:
            entity = collection.get(target)
            item = collection.payload(target)
            if entity.kind != "card" or item.card_type != "item":
                raise ValueError("Item unavailable")
        except ValueError:
            complete = False
            if enabled:
                diagnostic = "Активный предмет недоступен: " + str(target)
                missing.append(str(target))
            continue
        values = dict(item.values)
        unit_weight = values.get("weight", field_definition("weight").default)
        if unit_weight is None or count is None:
            complete = False
        else:
            weight += unit_weight * count
        if enabled:
            entries.append(
                EquipmentEntry(
                    row.id,
                    entity.id,
                    entity.title,
                    values.get("equipment_kind", "item"),
                    values.get("armor_category"),
                    values.get("armor_ac"),
                    values.get("shield_bonus"),
                )
            )
            for modifier in values.get("modifiers", ()):
                identity = (actor.id if actor else card.id, table_id, row.id, modifier.id)
                if len(sources) >= 4096:
                    return dict(
                        sources=tuple(sources),
                        inventory_weight=None,
                        incomplete="Превышен лимит 4096 активных модификаторов",
                        equipment=resolve_equipment(entries, missing=missing),
                    )
                sources.append(ModifierSource(identity, modifier, entity.title))
    return dict(
        sources=tuple(sources),
        inventory_weight=weight if complete else None,
        incomplete=diagnostic,
        equipment=resolve_equipment(entries, missing=missing),
    )


def card_projection(collection, key):
    entity, payload = collection.get(key), collection.payload(key)
    return Card(
        entity.title,
        key,
        entity.parent_id,
        sections=payload.sections,
        portrait=payload.portrait,
        card_type=payload.card_type,
        values=payload.values,
        actors=payload.actors,
        default_actor_id=payload.default_actor_id,
    )


def module_payload(document):
    if isinstance(document, MapDocument):
        return MapPayload(
            document.asset_id,
            document.tokens,
            document.grid,
            document.layers,
            document.objects,
            document.layers_initialized,
            document.fog,
            document.shapes,
            document.portals,
        )
    if isinstance(document, TableDocument):
        return TablePayload(document.columns, document.rows, document.wallet)
    return document.payload()


def module_document(entities, key):
    return entities.project(key, lambda entity, payload: _module_document(entity, payload))


def _module_document(entity, payload):
    key = entity.id
    if entity.kind == "map":
        return MapDocument(
            entity.title,
            payload.asset_id,
            key,
            payload.tokens,
            payload.grid,
            payload.layers,
            payload.objects,
            payload.layers_initialized,
            payload.fog,
            payload.shapes,
            payload.portals,
        )
    if entity.kind == "table":
        return TableDocument(entity.title, key, payload.columns, payload.rows, payload.wallet)
    raise ValueError("Unsupported module document")


def validate_inventory_columns(collection, table_id):
    columns = {c.key: c for c in collection.payload(table_id).columns if c.key}
    if not {"item", "quantity", "active", "description", "cost"} <= columns.keys():
        raise ValueError("Индивидуальный инвентарь требует item/quantity/active/projections")
    item, count, active = (columns[k] for k in ("item", "quantity", "active"))
    if (
        item.data_type != "entity_ref"
        or item.ref_kind != "card"
        or item.ref_card_type != "item"
        or count.data_type != "number"
        or not count.required
        or not count.integer
        or count.minimum is None
        or count.minimum < 1
        or active.data_type != "bool"
        or not active.required
    ):
        raise ValueError("Нарушены ограничения индивидуального инвентаря")
    for key, field_id in (("description", "description_preview"), ("cost", "cost")):
        column = columns[key]
        if (
            column.data_type != "projection"
            or column.source_column_id != item.id
            or column.field_key != field_id
        ):
            raise ValueError("Инвентарь требует живых проекций описания/стоимости")


def _validate_item(card, settings, category_ids):
    if card.card_type == "item":
        if (price := card.value("cost")) is not None:
            settings.currency.denomination(price.denomination_id)
        category = card.value("item_category")
        if category is not None and category not in category_ids:
            raise ValueError("Категория предмета отсутствует в настройках проекта")


def _validate_base(collection, card):
    if inventory_inputs(collection, card, None)["equipment"].conflicts:
        raise ValueError("В базовом инвентаре надето несколько доспехов или щитов")


def _validate_actor(collection, card, actor, rules):
    if actor.inventory_id is not None:
        target = collection.get(actor.inventory_id)
        if target.kind != "table" or target.parent_id != card.id:
            raise ValueError("Actor inventory has wrong owner/type")
        validate_inventory_columns(collection, actor.inventory_id)
    inputs = inventory_inputs(collection, card, actor)
    if inputs["equipment"].conflicts:
        raise ValueError("Надето несколько доспехов или щитов у участника")
    signature = (
        card.title, card.card_type, card.values, card.sections, actor.values, actor.inventory_id,
        rules, tuple(sorted(inputs.items())),
    )
    proof = actor._validation_proof
    if proof is not None and proof[0] == signature:
        maximum = proof[1]
    else:
        maximum = calculate(card, actor, rules, **inputs).get("hp_max")
        object.__setattr__(actor, "_validation_proof", (signature, maximum))
    current = actor.value("hp_current")
    if maximum.status == "ok" and current is not None and current > maximum.value:
        raise ValueError("Actor current HP exceeds effective maximum")


def _validate_wallet(collection, key, wallet, owned, settings):
    if not owned:
        raise ValueError("Кошелёк может принадлежать только инвентарю")
    validate_inventory_columns(collection, key)
    validate_wallet(wallet)
    for coin in wallet:
        settings.currency.denomination(coin.denomination_id)


def _validate_portal(collection, key, portal):
    if portal.target_id == key:
        raise ValueError("Портал не может ссылаться на текущую карту")
    try:
        target = collection.get(portal.target_id)
    except ValueError:
        return  # Deletion leaves a diagnosable soft portal reference.
    if target.kind != "map":
        raise ValueError("Цель портала должна быть картой")


def _validate_token_binding(collection, token, *, actors=None):
    card = collection.get(token.card_id)
    if card.kind != "card":
        raise ValueError("Token requires Card")
    payload = collection.payload(card.id)
    if token.uses_object_transform and payload.card_type != "object":
        raise ValueError("Дробный размер и поворот доступны только объектам")
    if payload.card_type in ACTOR_TYPES and token.actor_id is None:
        raise ValueError("Игровой Token требует Actor")
    if token.actor_id is not None:
        owns_actor = (
            actors.get(token.actor_id) == token.card_id if actors is not None
            else any(actor.id == token.actor_id for actor in payload.actors)
        )
        if not owns_actor:
            raise ValueError("Token Actor/Card reference mismatch")


def validate_project(collection, previous=None):
    settings = collection.settings or ProjectSettings()
    if not isinstance(settings, ProjectSettings):
        raise ValueError("Invalid project settings")
    rules = settings.rules
    if rules is not None and not isinstance(rules, ProjectRules):
        raise ValueError("Invalid project rules")
    actors, tokens, owned_tables, template_tables = {}, set(), set(), set()
    entities = collection.summaries()
    entity_ids = {entity.id for entity in entities}
    category_ids = {category.id for category in settings.categories}
    old_owners = {
        actor.id: key
        for key, payload in (previous or {}).items()
        for actor in getattr(payload, "actors", ())
    }
    for entity in entities:
        payload = collection.payload(entity.id)
        if entity.kind != "card":
            continue
        card = card_projection(collection, entity.id)
        _validate_item(card, settings, category_ids)
        template_tables.update(
            (s.table_id, entity.id) for s in card.sections if s.purpose == "inventory"
        )
        _validate_base(collection, card)
        for actor in payload.actors:
            if (
                actor.id in entity_ids
                or actor.id in actors
                or old_owners.get(actor.id, entity.id) != entity.id
            ):
                raise ValueError("Actor UUID duplicated or original Card changed")
            actors[actor.id] = entity.id
            if actor.inventory_id is not None:
                if actor.inventory_id in owned_tables:
                    raise ValueError("Inventory cannot belong to two Actors")
                owned_tables.add(actor.inventory_id)
            _validate_actor(collection, card, actor, rules)
    for entity in entities:
        if entity.kind == "table" and (wallet := collection.payload(entity.id).wallet):
            owned = entity.id in owned_tables or (entity.id, entity.parent_id) in template_tables
            _validate_wallet(collection, entity.id, wallet, owned, settings)
        if entity.kind != "map":
            continue
        payload = collection.payload(entity.id)
        for value in (*payload.shapes, *payload.portals):
            if value.id in tokens or value.id in actors or value.id in entity_ids:
                raise ValueError("Duplicate vector UUID across maps")
            tokens.add(value.id)
        for portal in payload.portals:
            _validate_portal(collection, entity.id, portal)
        for token in payload.tokens:
            if token.id in tokens or token.id in actors or token.id in entity_ids:
                raise ValueError("Duplicate Token UUID across maps")
            tokens.add(token.id)
            _validate_token_binding(collection, token, actors=actors)


def _map_ids(payload):
    return {value.id for value in (*payload.tokens, *payload.shapes, *payload.portals)}


def _token_binding(token):
    return token.card_id, token.actor_id, token.uses_object_transform


def validate_map_candidate(collection, key, before, after):
    """Only a map is hypothetical here. Other aggregates remain canonical."""
    introduced = _map_ids(after) - _map_ids(before)
    if introduced:
        for entity in collection.summaries():
            if entity.id in introduced:
                raise ValueError("UUID объекта карты уже используется")
            if entity.id == key:
                continue
            payload = collection.payload(entity.id)
            if (
                (entity.kind == "map" and not introduced.isdisjoint(_map_ids(payload)))
                or (entity.kind == "card"
                    and not introduced.isdisjoint(actor.id for actor in payload.actors))
            ):
                raise ValueError("UUID объекта карты уже используется")
    old_tokens = {token.id: _token_binding(token) for token in before.tokens}
    for token in after.tokens:
        if _token_binding(token) != old_tokens.get(token.id):
            _validate_token_binding(collection, token)
    if before.portals is not after.portals:
        for portal in after.portals:
            _validate_portal(collection, key, portal)


def _template(payload):
    return next((s.table_id for s in payload.sections if s.purpose == "inventory"), None)


def _item_references(payload):
    if not isinstance(payload, TablePayload):
        return set()
    item = next((column for column in payload.columns if column.key == "item"), None)
    if item is None:
        return set()
    return {key for row in payload.rows if isinstance(key := row.value(item.id), str)}


def _table_contexts(collection, parent, table):
    if parent is None:
        return ()
    try:
        owner = collection.get(parent)
    except ValueError:
        return ()
    if owner.kind != "card":
        return ()
    payload = collection.payload(parent)
    base = (None,) if _template(payload) == table else ()
    return (*base, *(actor.id for actor in payload.actors if actor.inventory_id == table))


_ITEM_INPUT_FIELDS = (
    "weight", "equipment_kind", "armor_category", "armor_ac", "shield_bonus", "modifiers",
)


def _item_signature(entity, payload):
    if isinstance(payload, CardPayload) and payload.card_type == "item":
        values = dict(payload.values)
        return entity.title, tuple(values.get(field) for field in _ITEM_INPUT_FIELDS)
    return None


def _card_contexts(collection):
    return {
        entity.id: {None, *(actor.id for actor in collection.payload(entity.id).actors)}
        for entity in collection.summaries() if entity.kind == "card"
    }


class ProjectValidation:
    """Runtime proofs and reverse Item references over one verified collection."""

    def __init__(self, collection):
        self.full_validation = False
        self._item_tables = {}
        for entity in collection.summaries():
            if entity.kind == "table":
                self._update_item_links(entity.id, set(), _item_references(
                    collection.payload(entity.id)
                ))

    def _update_item_links(self, table, before, after):
        for item in before - after:
            tables = self._item_tables[item]
            tables.discard(table)
            if not tables:
                del self._item_tables[item]
        for item in after - before:
            self._item_tables.setdefault(item, set()).add(table)

    def affected_contexts(self, collection, changes, *, complete=False):
        before_rules = getattr(changes.settings_before, "rules", None)
        after_rules = getattr(changes.settings_after, "rules", None)
        if complete or before_rules != after_rules:
            return _card_contexts(collection)
        contexts, tables = {}, {}
        for change in changes.aggregates:
            old, new = change.before_payload, change.after_payload
            if isinstance(new, CardPayload):
                self._card_change(contexts, change)
            if _item_signature(change.before, old) != _item_signature(change.after, new):
                for table in self._item_tables.get(change.id, ()):
                    try:
                        parent = collection.get(table).parent_id
                    except ValueError:
                        continue
                    tables.setdefault(table, set()).add(parent)
            if isinstance(old, TablePayload) or isinstance(new, TablePayload):
                self._table_change(tables, change)
        for table, parents in tables.items():
            for parent in parents:
                if addressed := _table_contexts(collection, parent, table):
                    contexts.setdefault(parent, set()).update(addressed)
        return contexts

    @staticmethod
    def _card_change(contexts, change):
        old, new = change.before_payload, change.after_payload
        if (
            not isinstance(old, CardPayload)
            or old.values != new.values
            or change.before.title != change.after.title
            or old.card_type != new.card_type
        ):
            contexts[change.id] = {None, *(actor.id for actor in new.actors)}
            return
        addressed = {None} if _template(old) != _template(new) else set()
        if old.actors != new.actors:
            previous = {actor.id: actor for actor in old.actors}
            addressed.update(actor.id for actor in new.actors if previous.get(actor.id) != actor)
        if addressed:
            contexts[change.id] = addressed

    @staticmethod
    def _table_change(tables, change):
        old, new = change.before_payload, change.after_payload
        if (
            not isinstance(old, TablePayload) or not isinstance(new, TablePayload)
            or change.before.parent_id != change.after.parent_id
            or old.rows is not new.rows or old.columns is not new.columns
        ):
            tables.setdefault(change.id, set()).update(
                entity.parent_id for entity in (change.before, change.after) if entity is not None
            )

    @staticmethod
    def _requires_full(change):
        old, new = change.before_payload, change.after_payload
        before, after = change.before, change.after
        if before is None or after is None or before.kind != after.kind:
            return True
        if before.parent_id != after.parent_id:
            return True
        if before.kind == "card" and isinstance(old, CardPayload) and isinstance(new, CardPayload):
            return (
                old.card_type != new.card_type or _template(old) != _template(new)
                or _actor_links(old) != _actor_links(new)
            )
        if before.kind == "map" and isinstance(old, MapPayload) and isinstance(new, MapPayload):
            return False
        return not (
            before.kind == "table" and isinstance(old, TablePayload)
            and isinstance(new, TablePayload)
        )

    def __call__(self, collection, changes):
        maps = [
            change for change in changes.aggregates
            if change.before and change.before.kind == "map"
            and change.before_payload is not change.after_payload
        ]
        # Added identifiers on multiple edited maps must agree with one another.
        # The full validator remains the authority for structural and settings edits.
        if (
            self.full_validation or changes.settings_changed
            or any(self._requires_full(change) for change in changes.aggregates)
            or len(maps) > 1
        ):
            collection.validator(collection, changes.previous_payloads)
        else:
            self._validate_affected(collection, changes, maps)
        for change in changes.aggregates:
            if isinstance(change.before_payload, TablePayload) or isinstance(
                change.after_payload, TablePayload,
            ):
                self._update_item_links(
                    change.id, _item_references(change.before_payload),
                    _item_references(change.after_payload),
                )

    def _validate_affected(self, collection, changes, maps):
        settings = collection.settings or ProjectSettings()
        categories = None
        for change in changes.aggregates:
            payload = change.after_payload
            if isinstance(payload, CardPayload) and payload.card_type == "item":
                if categories is None:
                    categories = {category.id for category in settings.categories}
                _validate_item(card_projection(collection, change.id), settings, categories)
            if isinstance(payload, TablePayload) and payload.wallet:
                owned = _table_contexts(collection, change.after.parent_id, change.id)
                _validate_wallet(collection, change.id, payload.wallet, owned, settings)
        for key, contexts in self.affected_contexts(collection, changes).items():
            card = card_projection(collection, key)
            if None in contexts:
                _validate_base(collection, card)
            for actor in card.actors:
                if actor.id in contexts:
                    _validate_actor(collection, card, actor, settings.rules)
        for change in maps:
            validate_map_candidate(
                collection, change.id, change.before_payload, change.after_payload,
            )


def _actor_links(payload):
    return {(actor.id, actor.inventory_id) for actor in payload.actors}


def project_entities(cards=(), maps=(), tables=(), envelopes=(), *, settings=None):
    documents = [
        *(("card", c) for c in cards),
        *(("map", m) for m in maps),
        *(("table", t) for t in tables),
    ]
    if len({d.id for _, d in documents}) != len(documents):
        raise ValueError("Duplicate entity ID across modules; ids must be unique")
    if envelopes:
        by_id = {e.id: e for e in envelopes}
        if len(by_id) != len(envelopes) or set(by_id) != {d.id for _, d in documents}:
            raise ValueError("Entity envelope/payload inventory mismatch")
        for kind, document in documents:
            if by_id[document.id].kind != kind or by_id[document.id].title != document.title:
                raise ValueError("Entity envelope/payload mismatch")
    else:
        by_id, positions = {}, {}
        for kind, document in documents:
            parent = document.parent_id if kind == "card" else None
            position = positions.get(parent, 0)
            positions[parent] = position + 1
            by_id[document.id] = Entity(document.id, kind, document.title, parent, position)
    return EntityCollection(
        ((by_id[d.id], module_payload(d)) for _, d in documents),
        settings=settings,
        validator=validate_project,
    )
