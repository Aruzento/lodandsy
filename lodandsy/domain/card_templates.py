"""Templates define layout, never store a second edition of field values."""

from dataclasses import dataclass

from lodandsy.domain.card_schema import CARD_TYPES, SECTIONS


@dataclass(frozen=True, slots=True)
class TemplateDefinition:
    id: str
    title: str
    sections: tuple[str, ...]
    default_type: str = "note"
    portrait: bool = False
    version: int = 3

    def __post_init__(self):
        if self.default_type not in CARD_TYPES or any(k not in SECTIONS for k in self.sections):
            raise ValueError("Invalid built-in template")


CARD_TEMPLATES = (
    TemplateDefinition("empty", "Пустая карточка", ("description",)),
    TemplateDefinition("article", "Статья", ("description", "connections", "notes"), "article"),
    TemplateDefinition(
        "character",
        "Персонаж",
        ("description", "details", "history", "connections", "inventory", "notes"),
        "character",
        True,
    ),
    TemplateDefinition(
        "location", "Локация", ("description", "details", "connections", "notes"), "location"
    ),
    TemplateDefinition("item", "Предмет", ("description", "details", "history", "notes"), "item"),
)


def card_template(template_id="empty"):
    for template in CARD_TEMPLATES:
        if template.id == template_id:
            return template
    raise ValueError(f"Неизвестный шаблон карточки: {template_id}")
