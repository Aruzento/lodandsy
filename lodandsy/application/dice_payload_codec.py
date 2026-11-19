import json
from dataclasses import asdict

from lodandsy.domain.dice_document import DiceConfig, DiceDocument, DicePreset


def encode_dice(document):
    return json.dumps([asdict(p) for p in document.presets], ensure_ascii=False)


def decode_dice(title, key, version, source):
    if version != 2:
        raise ValueError("Unsupported Dice payload version")
    if not isinstance(source, str) or len(source) > 2**20:
        raise ValueError("Dice payload exceeds budget")
    data = json.loads(source)
    if not isinstance(data, list) or len(data) > 200:
        raise ValueError("Invalid dice presets")
    presets = []
    for value in data:
        if not isinstance(value, dict) or value.keys() != {"id", "name", "config"}:
            raise ValueError("Unsupported preset fields")
        config = value["config"]
        if not isinstance(config, dict) or config.keys() != {"counts", "modifier"}:
            raise ValueError("Unsupported dice config")
        if not isinstance(config["counts"], list):
            raise ValueError("Invalid dice counts")
        presets.append(
            DicePreset(
                value["name"], DiceConfig(tuple(config["counts"]), config["modifier"]), value["id"]
            )
        )
    return DiceDocument(title, key, tuple(presets))
