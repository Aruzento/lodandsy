"""Built-in text templates. Applied once on creation, never bound to a Card."""
from dataclasses import dataclass


@dataclass(frozen=True)
class CardTemplate:
    id: str
    title: str
    version: int
    content: str


def _sections(*titles):
    return "\n\n".join(f"## {title}\n\n".rstrip() for title in titles) + "\n"


CARD_TEMPLATES = (
    CardTemplate("empty", "Пустая карточка", 1, ""),
    CardTemplate("article", "Статья", 1,
                 _sections("Краткое описание", "Содержание", "Связи", "Заметки")),
    CardTemplate("character", "Персонаж", 1,
                 _sections("Имя", "Описание", "Параметры", "История", "Связи",
                           "Инвентарь", "Заметки")),
    CardTemplate("location", "Локация", 1,
                 _sections("Описание", "Окружение", "Обитатели", "Важные места",
                           "Связи", "Заметки")),
    CardTemplate("item", "Предмет", 1,
                 _sections("Описание", "Свойства", "История", "Владелец", "Связи", "Заметки")),
)


def card_template(template_id="empty") -> CardTemplate:
    for template in CARD_TEMPLATES:
        if template.id == template_id:
            return template
    raise ValueError(f"Неизвестный шаблон карточки: {template_id}")
