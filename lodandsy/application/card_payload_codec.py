import json
from dataclasses import asdict

from lodandsy.application.rich_html import validate_html
from lodandsy.domain.card import Card, Portrait
from lodandsy.domain.card_schema import field_definition


def encode_card(card):
    validate_html(card.content)
    for key, value in card.values:
        if field_definition(key).data_type == "richtext" and value is not None:
            validate_html(value)
    return 3, json.dumps(
        {
            "card_type": card.card_type,
            "template_id": card.template_id,
            "fields": dict(card.values),
            "document": {"format": "qt-richtext-html", "version": 1, "html": card.content},
            "portrait": asdict(card.portrait) if card.portrait is not None else None,
        },
        ensure_ascii=False,
    )


def _unique_pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate Card JSON field")
        result[key] = value
    return result


def decode_card(title, key, parent, version, source):
    if type(version) is not int or version != 3:
        raise ValueError(f"Unsupported Card payload version: {version}")
    if not isinstance(source, str) or len(source.encode("utf-8")) > 5 * 2**20:
        raise ValueError("Card payload exceeds budget")
    data = json.loads(source, object_pairs_hook=_unique_pairs)
    if not isinstance(data, dict) or data.keys() != {
        "card_type",
        "template_id",
        "fields",
        "document",
        "portrait",
    }:
        raise ValueError("Unsupported Card payload fields")
    document = data["document"]
    if (
        not isinstance(document, dict)
        or document.keys() != {"format", "version", "html"}
        or document["format"] != "qt-richtext-html"
        or type(document["version"]) is not int
        or document["version"] != 1
    ):
        raise ValueError("Unsupported Card document version or structure")
    validate_html(document["html"])
    portrait = data["portrait"]
    if portrait is not None:
        if not isinstance(portrait, dict) or portrait.keys() != {"asset_id", "alt", "caption"}:
            raise ValueError("Unsupported portrait structure")
        portrait = Portrait(**portrait)
    fields = data["fields"]
    if not isinstance(fields, dict):
        raise ValueError("Invalid Card fields")
    values = []
    for name, value in fields.items():
        definition = field_definition(name)
        if definition.data_type == "text_list" and value is not None:
            if not isinstance(value, list):
                raise ValueError("Invalid metadata list")
            value = tuple(value)
        if definition.data_type == "richtext" and value is not None:
            validate_html(value)
        values.append((name, value))
    return Card(
        title,
        key,
        parent,
        document["html"],
        portrait,
        data["card_type"],
        data["template_id"],
        tuple(values),
    )
