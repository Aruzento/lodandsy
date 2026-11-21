from lodandsy.domain.card import Card
from lodandsy.domain.card_schema import ACTOR_TYPES, field_definition
from lodandsy.domain.entity import Entity, EntityCollection
from lodandsy.domain.map_document import MapDocument, MapPayload
from lodandsy.domain.modifiers import ModifierSource
from lodandsy.domain.rules_5e14 import ProjectRules, calculate
from lodandsy.domain.table_document import TableDocument, TablePayload


def inventory_inputs(collection, card, actor):
    table_id = (
        actor.inventory_id
        if actor is not None
        else next((s.table_id for s in card.sections if s.purpose == "inventory"), None)
    )
    if table_id is None:
        return dict(sources=(), inventory_weight=0, incomplete="")
    try:
        target = collection.get(table_id)
        if target.kind != "table" or target.parent_id != card.id:
            raise ValueError("Inventory link is unavailable")
        payload = collection.payload(table_id)
    except ValueError:
        return dict(sources=(), inventory_weight=None, incomplete="Связанная таблица недоступна")
    columns = {column.key: column for column in payload.columns if column.key}
    item_column, quantity = columns.get("item"), columns.get("quantity")
    if item_column is None or quantity is None:
        return dict(sources=(), inventory_weight=None, incomplete="Нужны столбцы item/quantity")
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
            continue
        values = dict(item.values)
        unit_weight = values.get("weight", field_definition("weight").default)
        if unit_weight is None or count is None:
            complete = False
        else:
            weight += unit_weight * count
        if enabled:
            for modifier in values.get("modifiers", ()):
                identity = (actor.id if actor else card.id, table_id, row.id, modifier.id)
                if len(sources) >= 4096:
                    return dict(
                        sources=tuple(sources),
                        inventory_weight=None,
                        incomplete="Превышен лимит 4096 активных модификаторов",
                    )
                sources.append(ModifierSource(identity, modifier, entity.title))
    return dict(
        sources=tuple(sources), inventory_weight=weight if complete else None, incomplete=diagnostic
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
        )
    if isinstance(document, TableDocument):
        return TablePayload(document.columns, document.rows)
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
        )
    if entity.kind == "table":
        return TableDocument(entity.title, key, payload.columns, payload.rows)
    raise ValueError("Unsupported module document")


def validate_project(collection, previous=None):
    if collection.settings is not None and not isinstance(collection.settings, ProjectRules):
        raise ValueError("Invalid project rules")
    actors, tokens, owned_tables = {}, set(), set()
    entity_ids = {entity.id for entity in collection.summaries()}
    old_owners = {
        actor.id: key
        for key, payload in (previous or {}).items()
        for actor in getattr(payload, "actors", ())
    }
    for entity in collection.summaries():
        payload = collection.payload(entity.id)
        if entity.kind != "card":
            continue
        card = card_projection(collection, entity.id) if payload.actors else None
        for actor in payload.actors:
            if (
                actor.id in entity_ids
                or actor.id in actors
                or old_owners.get(actor.id, entity.id) != entity.id
            ):
                raise ValueError("Actor UUID duplicated or original Card changed")
            actors[actor.id] = entity.id
            if actor.inventory_id is not None:
                target = collection.get(actor.inventory_id)
                if target.kind != "table" or target.parent_id != entity.id:
                    raise ValueError("Actor inventory has wrong owner/type")
                if actor.inventory_id in owned_tables:
                    raise ValueError("Inventory cannot belong to two Actors")
                owned_tables.add(actor.inventory_id)
                columns = {
                    c.key: c for c in collection.payload(actor.inventory_id).columns if c.key
                }
                if not {"item", "quantity", "active", "description", "cost"} <= columns.keys():
                    raise ValueError(
                        "Индивидуальный инвентарь требует item/quantity/active/projections"
                    )
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
            inputs = inventory_inputs(collection, card, actor)
            signature = (
                card.title,
                card.card_type,
                card.values,
                card.sections,
                actor.values,
                actor.inventory_id,
                collection.settings,
                tuple(sorted(inputs.items())),
            )
            proof = actor._validation_proof
            if proof is not None and proof[0] == signature:
                maximum = proof[1]
            else:
                maximum = calculate(card, actor, collection.settings, **inputs).get("hp_max")
                object.__setattr__(actor, "_validation_proof", (signature, maximum))
            current = actor.value("hp_current")
            if maximum.status == "ok" and current is not None and current > maximum.value:
                raise ValueError("Actor current HP exceeds effective maximum")
    for entity in collection.summaries():
        if entity.kind != "map":
            continue
        for token in collection.payload(entity.id).tokens:
            if token.id in tokens or token.id in actors or token.id in entity_ids:
                raise ValueError("Duplicate Token UUID across maps")
            tokens.add(token.id)
            card = collection.get(token.card_id)
            if card.kind != "card":
                raise ValueError("Token requires Card")
            if collection.payload(card.id).card_type in ACTOR_TYPES and token.actor_id is None:
                raise ValueError("Игровой Token требует Actor")
            if token.actor_id is not None and actors.get(token.actor_id) != token.card_id:
                raise ValueError("Token Actor/Card reference mismatch")


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
