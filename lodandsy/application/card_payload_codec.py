import json
from dataclasses import asdict, replace

from lodandsy.application.rich_html import validate_html
from lodandsy.domain.actor_state import ActorState
from lodandsy.domain.card import Card, CardSection, Portrait
from lodandsy.domain.card_schema import field_definition
from lodandsy.domain.currency import CoinAmount
from lodandsy.domain.modifiers import Modifier


def encode_card(card):
    if card.actors or card.default_actor_id is not None:
        raise ValueError("Use aggregate codec for Card with Actors")
    for section in card.sections:
        if section.kind == "rich_text":
            validate_html(section.content)
    return 8, json.dumps(
        dict(
            card_type=card.card_type,
            fields={
                key: encode_field(key, value)
                for key, value in card.values
            },
            sections=[asdict(s) for s in card.sections],
            portrait=asdict(card.portrait) if card.portrait else None,
        ),
        ensure_ascii=False,
    )


def encode_field(key, value):
    if key == "modifiers":
        return [asdict(m) for m in value]
    if key == "cost" and value is not None:
        return asdict(value)
    return value


def encode_card_aggregate(card):
    version, definition = encode_card(replace(card, actors=(), default_actor_id=None))
    actors = tuple(
        (
            actor.id,
            card.id,
            actor.inventory_id,
            1,
            json.dumps({"name": actor.name, "values": dict(actor.values)}, ensure_ascii=False),
        )
        for actor in card.actors
    )
    return version, definition, actors, card.default_actor_id


def decode_actor(key, inventory_id, version, source):
    if type(version) is not int or version != 1:
        raise ValueError("Unsupported Actor version")
    if not isinstance(source, str) or len(source.encode("utf-8")) > 65536:
        raise ValueError("Invalid Actor payload budget")
    try:
        data = json.loads(source, object_pairs_hook=_unique_pairs)
    except RecursionError:
        raise ValueError("Actor JSON nesting exceeds budget") from None
    if not isinstance(data, dict) or data.keys() != {"name", "values"}:
        raise ValueError("Invalid Actor payload")
    if not isinstance(data["values"], dict):
        raise ValueError("Invalid Actor values")
    return ActorState(data["name"], tuple(data["values"].items()), key, inventory_id)


def _unique_pairs(pairs):
    data = {}
    for key, value in pairs:
        if key in data:
            raise ValueError("Duplicate Card JSON field")
        data[key] = value
    return data


def decode_card(title, key, parent, version, source, *, actors=(), default_actor_id=None):
    if type(version) is not int or version != 8:
        raise ValueError(f"Unsupported Card payload version: {version}")
    if not isinstance(source, str) or len(source.encode("utf-8")) > 5 * 2**20:
        raise ValueError("Card payload exceeds budget")
    try:
        data = json.loads(source, object_pairs_hook=_unique_pairs)
    except RecursionError:
        raise ValueError("Card JSON nesting exceeds budget") from None
    if not isinstance(data, dict) or data.keys() != {"card_type", "fields", "sections", "portrait"}:
        raise ValueError("Unsupported Card payload fields")
    if not isinstance(data["sections"], list) or not isinstance(data["fields"], dict):
        raise ValueError("Invalid Card sections/fields")
    expected = {"id", "title", "position", "kind", "content", "table_id", "purpose"}
    if any(not isinstance(s, dict) or s.keys() != expected for s in data["sections"]):
        raise ValueError("Unsupported section structure")
    sections = tuple(CardSection(**s) for s in data["sections"])
    for section in sections:
        if section.kind == "rich_text":
            validate_html(section.content)
    portrait = data["portrait"]
    if portrait is not None:
        if (
            not isinstance(portrait, dict)
            or portrait.keys() != {"asset_id", "crop"}
            or not isinstance(portrait["crop"], list)
        ):
            raise ValueError("Unsupported portrait structure")
        portrait = Portrait(portrait["asset_id"], tuple(portrait["crop"]))
    values = []
    for name, value in data["fields"].items():
        definition = field_definition(name)
        if definition.data_type == "coin_amount" and value is not None:
            if not isinstance(value, dict):
                raise ValueError("Invalid Item price")
            value = CoinAmount(**value)
        if definition.data_type == "modifier_list":
            if not isinstance(value, list):
                raise ValueError("Invalid modifier list")
            try:
                value = tuple(Modifier(**entry) for entry in value)
            except TypeError as error:
                raise ValueError("Invalid modifier structure") from error
        if definition.data_type in {"text_list", "number_list"} and value is not None:
            if not isinstance(value, list):
                raise ValueError("Invalid metadata list")
            value = tuple(value)
        values.append((name, value))
    return Card(
        title,
        key,
        parent,
        portrait=portrait,
        card_type=data["card_type"],
        values=tuple(values),
        sections=sections,
        actors=actors,
        default_actor_id=default_actor_id,
    )
