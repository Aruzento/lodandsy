from lodandsy.domain.entity import Entity, EntityCollection
from lodandsy.domain.map_document import MapDocument, MapPayload
from lodandsy.domain.table_document import TableDocument, TablePayload


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


def project_entities(cards=(), maps=(), tables=(), envelopes=()):
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
    return EntityCollection((by_id[d.id], module_payload(d)) for _, d in documents)
