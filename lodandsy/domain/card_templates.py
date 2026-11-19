"""Built-in visual document templates; copied once on creation."""
from dataclasses import dataclass
from html import escape

from lodandsy.domain.card import DOCUMENT_HEADER, EMPTY_DOCUMENT, Portrait


@dataclass(frozen=True)
class CardTemplate:
    id: str
    title: str
    version: int
    content: str
    portrait: Portrait | None = None


def _sections(*titles):
    return ("<html>" + DOCUMENT_HEADER + "<body>"
            + "".join(f"<h2>{escape(title)}</h2>" for title in titles) + "</body></html>")


CARD_TEMPLATES = (
    CardTemplate("empty", "Пустая карточка", 2, EMPTY_DOCUMENT),
    CardTemplate("article", "Статья", 2,
                 _sections("Краткое описание", "Содержание", "Связи", "Заметки")),
    CardTemplate("character", "Персонаж", 2,
                 _sections("Имя", "Описание", "Параметры", "История", "Связи",
                           "Инвентарь", "Заметки"), Portrait()),
    CardTemplate("location", "Локация", 2,
                 _sections("Описание", "Окружение", "Обитатели", "Важные места",
                           "Связи", "Заметки")),
    CardTemplate("item", "Предмет", 2,
                 _sections("Описание", "Свойства", "История", "Владелец", "Связи", "Заметки")),
)


def card_template(template_id="empty") -> CardTemplate:
    for template in CARD_TEMPLATES:
        if template.id == template_id:
            return template
    raise ValueError(f"Неизвестный шаблон карточки: {template_id}")
