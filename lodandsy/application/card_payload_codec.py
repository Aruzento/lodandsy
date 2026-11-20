import json
from dataclasses import asdict

from lodandsy.application.rich_html import validate_html
from lodandsy.domain.card import Card, CardSection, Portrait
from lodandsy.domain.card_schema import field_definition


def encode_card(card):
    for section in card.sections:
        if section.kind == "rich_text":
            validate_html(section.content)
    return 5, json.dumps(
        dict(
            card_type=card.card_type,
            fields=dict(card.values),
            sections=[asdict(s) for s in card.sections],
            portrait=asdict(card.portrait) if card.portrait else None,
        ),
        ensure_ascii=False,
    )


def _unique_pairs(pairs):
    data = {}
    for key, value in pairs:
        if key in data:
            raise ValueError("Duplicate Card JSON field")
        data[key] = value
    return data


def decode_card(title, key, parent, version, source):
    if type(version) is not int or version != 5:
        raise ValueError(f"Unsupported Card payload version: {version}")
    if not isinstance(source, str) or len(source.encode("utf-8")) > 5 * 2**20:
        raise ValueError("Card payload exceeds budget")
    data = json.loads(source, object_pairs_hook=_unique_pairs)
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
        if definition.data_type == "text_list" and value is not None:
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
    )
