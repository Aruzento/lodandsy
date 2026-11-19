"""Versioned column metadata for the normalized S3 adapter, without copied derived cells."""

import json
from dataclasses import asdict

from lodandsy.domain.table_document import ColumnDefinition

SETTINGS = frozenset(
    {
        "key",
        "ref_kind",
        "ref_card_type",
        "source_column_id",
        "field_key",
        "integer",
        "minimum",
        "maximum",
        "required",
        "default",
    }
)


def encode_settings(column):
    return json.dumps(
        {key: value for key, value in asdict(column).items() if key in SETTINGS},
        ensure_ascii=False,
        allow_nan=False,
    )


def decode_column(name, kind, position, key, settings):
    def pairs(values):
        result = {}
        for key, value in values:
            if key in result:
                raise ValueError("Duplicate column option")
            result[key] = value
        return result

    options = json.loads(settings, object_pairs_hook=pairs)
    if not isinstance(options, dict) or options.keys() != SETTINGS:
        raise ValueError("Unknown/missing column options")
    return ColumnDefinition(name, kind, position, key, **options)
