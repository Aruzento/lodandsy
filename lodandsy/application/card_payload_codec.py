import json
from dataclasses import asdict

from lodandsy.application.rich_html import validate_html
from lodandsy.domain.card import Card, Portrait


def encode_card(card):
    validate_html(card.content)
    return 2, json.dumps(
        {
            "document": {"format": "qt-richtext-html", "version": 1, "html": card.content},
            "portrait": asdict(card.portrait) if card.portrait is not None else None,
        },
        ensure_ascii=False,
    )


def decode_card(title, key, parent, version, source):
    if version != 2:
        raise ValueError(f"Unsupported Card payload version: {version}")
    data = json.loads(source)
    if not isinstance(data, dict) or data.keys() != {"document", "portrait"}:
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
    return Card(title, key, parent, document["html"], portrait)
