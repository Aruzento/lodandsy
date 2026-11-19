"""One-way bounded MOW v1 reader. No MOW runtime or YAML object constructors."""

import csv
import json
import re
from dataclasses import dataclass, field
from html import escape
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote, urlsplit
from uuid import uuid4

from lodandsy.application.card_images import read_card_image
from lodandsy.application.rich_html import html_text, sanitize_html
from lodandsy.domain.card import Card, Portrait
from lodandsy.domain.card_schema import CARD_TYPES
from lodandsy.domain.module_values import validate_id

MAX_FILES = 500
MAX_TOTAL = 64 * 1024**2
MAX_FILE = 2 * 1024**2
VOID = {"img", "br", "hr", "input", "meta", "link"}
DROP = {
    "script",
    "style",
    "input",
    "select",
    "button",
    "iframe",
    "object",
    "embed",
    "form",
    "svg",
    "head",
}


@dataclass
class Node:
    tag: str
    attrs: dict = field(default_factory=dict)
    children: list = field(default_factory=list)

    def find(self, predicate):
        if predicate(self):
            yield self
        for child in self.children:
            if isinstance(child, Node):
                yield from child.find(predicate)

    def has(self, name):
        return name in self.attrs.get("class", "").split()


class Tree(HTMLParser):
    def __init__(self, body):
        super().__init__(convert_charrefs=True)
        self.root = Node("div")
        self.stack = [self.root]
        self.count = 0
        self.feed(body)
        self.close()

    def handle_starttag(self, tag, attrs):
        self.count += 1
        if self.count > 20000 or len(self.stack) > 64:
            raise ValueError("Превышена сложность HTML")
        node = Node(tag, dict(attrs))
        self.stack[-1].children.append(node)
        if tag not in VOID:
            self.stack.append(node)

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        if tag not in VOID:
            self.handle_endtag(tag)

    def handle_endtag(self, tag):
        for i in range(len(self.stack) - 1, 0, -1):
            if self.stack[i].tag == tag:
                del self.stack[i:]
                break

    def handle_data(self, data):
        self.stack[-1].children.append(data)


def scalar(value):
    value = value.strip()
    if len(value) > 8192:
        raise ValueError("Слишком длинное значение YAML")
    if value.startswith('"'):
        return json.loads(value)
    if value.startswith("'") and value.endswith("'"):
        return value[1:-1].replace("''", "'")
    if re.search(r"[&*!{}\[\]\x00]", value):
        raise ValueError("Неподдерживаемый конструктор YAML")
    if value in {"null", "~", ""}:
        return None
    if re.fullmatch(r"-?[0-9]+", value):
        return int(value)
    return value


def frontmatter(text):
    lines = text.removeprefix("\ufeff").splitlines(keepends=True)
    if not lines or lines[0].strip() != "---":
        raise ValueError("Нет YAML front matter")
    end = next((i for i in range(1, min(len(lines), 1024)) if lines[i].strip() == "---"), None)
    if end is None or sum(map(len, lines[:end])) > 65536:
        raise ValueError("Некорректный YAML header")
    result = {}
    for line in lines[1:end]:
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        if line[0].isspace() or ":" not in line:
            raise ValueError("Поддерживаются плоские YAML поля и inline списки")
        key, value = line.split(":", 1)
        if not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]*", key) or key in result:
            raise ValueError("Некорректное или повторное поле YAML")
        value = value.strip()
        if value.startswith("[") and value.endswith("]"):
            inside = value[1:-1].strip()
            values = next(csv.reader([inside], skipinitialspace=True)) if inside else []
            if len(values) > 64:
                raise ValueError("Слишком длинный YAML список")
            result[key] = [scalar(v) for v in values]
        else:
            result[key] = scalar(value)
    return result, "".join(lines[end + 1 :])


def source_image(root, value):
    try:
        parsed = urlsplit(value)
        name = unquote(parsed.path, errors="strict")
    except ValueError, UnicodeError:
        raise ValueError("Некорректный путь изображения") from None
    if (
        parsed.scheme
        or parsed.netloc
        or parsed.query
        or parsed.fragment
        or any(c in name for c in "\\:\0")
    ):
        raise ValueError("Заблокирован внешний или небезопасный путь")
    path = Path(name)
    if path.is_absolute() or ".." in path.parts:
        raise ValueError("Выход за пределы источника")
    root = Path(root).resolve()
    resolved = (root / path).resolve(strict=True)
    if not resolved.is_relative_to(root) or not resolved.is_file():
        raise ValueError("Выход за пределы источника")
    return resolved


def render(node, mapping, media, warnings):
    if isinstance(node, str):
        return escape(node)
    if node.tag in DROP or "data-runtime" in node.attrs:
        return ""
    attrs = {
        k: v
        for k, v in node.attrs.items()
        if k in {"style", "href", "src", "alt", "width", "height", "title"} and v is not None
    }
    target = node.attrs.get("data-page-id") or node.attrs.get("data-entity-id")
    if node.has("wiki-link") or target:
        if target in mapping:
            attrs = {"href": "lodandsy://entity/" + mapping[target]}
        else:
            warnings.append(
                "Неопределимая внутренняя ссылка: "
                + str(target or node.attrs.get("data-page-title", ""))
            )
            attrs = {}
        tag = "a" if attrs else "span"
    else:
        tag = node.tag
    if tag == "img":
        value = node.attrs.get("src")
        if node.attrs.get("data-asset"):
            warnings.append(
                "MOW data-asset требует недоступного manifest: " + node.attrs["data-asset"]
            )
            return "<p>[Изображение MOW: нужен manifest]</p>"
        try:
            if not value:
                raise ValueError("Путь не указан")
            attrs["src"] = media(value)
        except (ValueError, OSError) as error:
            warnings.append("Изображение: " + str(error))
            return "<p>[Изображение недоступно]</p>"
    if "href" in attrs and attrs["href"].startswith("lodandsy://entity/"):
        old = attrs["href"].rsplit("/", 1)[-1]
        if old in mapping:
            attrs["href"] = "lodandsy://entity/" + mapping[old]
        elif old not in mapping.values():
            warnings.append("Неопределимая ссылка: " + old)
    children = "".join(render(c, mapping, media, warnings) for c in node.children)
    attributes = "".join(f' {k}="{escape(v, quote=True)}"' for k, v in attrs.items())
    return f"<{tag}{attributes}>" + children + ("" if tag in VOID else f"</{tag}>")


@dataclass(frozen=True)
class MowRecord:
    source: Path
    metadata: dict
    tree: Node
    title: str
    summary: str
    body: Node
    portrait: Node | None


@dataclass
class ImportPlan:
    root: Path
    records: list = field(default_factory=list)
    warnings: list = field(default_factory=list)
    errors: list = field(default_factory=list)

    def report(self):
        images = sum(len(list(r.tree.find(lambda n: n.tag == "img"))) for r in self.records)
        links = sum(
            len(list(r.tree.find(lambda n: n.has("wiki-link") or n.attrs.get("data-page-id"))))
            for r in self.records
        )
        return (
            f"Карточек: {len(self.records)} · изображений: {images} · внутренних ссылок: {links}\n"
            + "\n".join([*("ОШИБКА: " + x for x in self.errors), *self.warnings])
        )


def inspect_source(source):
    source = Path(source).resolve(strict=True)
    root = source if source.is_dir() else source.parent
    plan = ImportPlan(root)
    paths = []
    if source.is_file():
        paths = [source]
    else:
        for path in source.rglob("*.md"):
            paths.append(path)
            if len(paths) > MAX_FILES:
                plan.errors.append("Превышено 500 документов")
                return plan
    total = nodes = 0
    for path in sorted(paths):
        try:
            safe = source_image(root, path.relative_to(root).as_posix())
            size = safe.stat().st_size
            total += size
            if size > MAX_FILE or total > MAX_TOTAL:
                raise ValueError("Превышен бюджет импорта")
            with safe.open("rb") as stream:
                data = stream.read(MAX_FILE + 1)
            if len(data) > MAX_FILE:
                raise ValueError("Превышен бюджет документа")
            meta, body = frontmatter(data.decode("utf-8-sig"))
            validate_id(meta.get("id"))
            if meta.get("schemaVersion") != 1:
                raise ValueError("Поддерживается MOW schemaVersion 1")
            if meta.get("parent"):
                validate_id(meta["parent"])
            if type(meta.get("order", 0)) is not int:
                raise ValueError("Некорректный порядок")
            parsed_tree = Tree(body)
            nodes += parsed_tree.count
            if nodes > 200_000:
                raise ValueError("Превышен общий бюджет HTML узлов импорта")
            tree = parsed_tree.root

            def plain(node):
                return html_text(
                    sanitize_html(render(node, {}, lambda s: "assets/preview.png", []))[0]
                ).strip()

            header = next(tree.find(lambda n: n.tag == "h1"), None)
            title = plain(header) if header else meta.get("title") or path.stem
            summary_node = next(tree.find(lambda n: n.has("card-short-description")), None)
            summary = plain(summary_node) if summary_node else ""
            main = next(tree.find(lambda n: n.has("entity-main")), None)
            if main is None:
                raise ValueError("Нет entity-main card shell")
            blocks = list(main.find(lambda n: n.has("template-block")))
            body_node = Node("div")
            if blocks:
                for block in blocks:
                    kind = block.attrs.get("data-block-type")
                    if kind != "text" or block.attrs.get("data-block-version") not in {None, "1"}:
                        plan.warnings.append(
                            f"{path.name}: неподдержанный блок {kind}; "
                            "сохранён безопасный видимый фрагмент"
                        )
                    fields = list(block.find(lambda n: n.has("rich-text-field")))
                    heading = next(block.find(lambda n: n.tag == "h2"), None)
                    if (
                        heading
                        and fields
                        and any(
                            plain(node) or list(node.find(lambda n: n.tag == "img"))
                            for node in fields
                        )
                    ):
                        body_node.children.append(heading)
                    body_node.children.extend(fields or [block])
            else:
                body_node.children.extend(main.children)
            portrait = next(tree.find(lambda n: n.has("is-portrait")), None)
            portrait = next(portrait.find(lambda n: n.tag == "img"), None) if portrait else None
            for image in tree.find(lambda n: n.tag == "img"):
                try:
                    if image.attrs.get("data-asset"):
                        raise ValueError("data-asset требует manifest")
                    source_image(root, image.attrs.get("src") or "")
                except (ValueError, OSError) as error:
                    plan.warnings.append(path.name + ": изображение: " + str(error))
            plan.records.append(MowRecord(path, meta, tree, title, summary, body_node, portrait))
        except (OSError, ValueError, TypeError) as error:
            plan.errors.append(path.name + ": " + str(error))
    ids = [r.metadata["id"] for r in plan.records]
    if len(ids) != len(set(ids)):
        plan.errors.append("Повторный UUID в источнике")
    parents = {r.metadata["id"]: r.metadata.get("parent") for r in plan.records}
    for key in parents:
        seen = set()
        current = key
        while current in parents:
            if current in seen:
                plan.errors.append("Цикл иерархии: " + key)
                break
            seen.add(current)
            current = parents[current]
        parent = parents[key]
        if parent and parent not in parents:
            plan.warnings.append(key + ": отсутствующий parent будет корнем: " + parent)
    return plan


def prepare_import(plan, store, existing_cards, known_assets, *, conflicts="skip", parent_id=None):
    if plan.errors:
        raise ValueError("Исправьте ошибки источника до применения")
    if conflicts not in {"skip", "remap"}:
        raise ValueError("Unknown conflict policy")
    existing_cards = tuple(existing_cards)
    by_source = {}
    for card in existing_cards:
        by_source.setdefault(card.value("mow_id") or card.id, []).append(card.id)
    mapping = {}
    selected = []
    warnings = list(plan.warnings)
    for record in plan.records:
        source_id = record.metadata["id"]
        collision = by_source.get(source_id, [])
        if collision and conflicts == "skip":
            if len(collision) == 1:
                mapping[source_id] = collision[0]
            warnings.append(record.title + ": конфликт/повторный импорт — пропущено")
        else:
            mapping[source_id] = str(uuid4())
            selected.append(record)
    assets = list(known_assets)
    imported = []

    def media(value):
        path = source_image(plan.root, value)
        read_card_image(path)
        asset = store.import_asset(path, known_assets=tuple(assets), max_bytes=32 * 1024**2)
        if asset.id not in {a.id for a in assets}:
            assets.append(asset)
            imported.append(asset)
        return asset.path

    cards = []
    try:
        for record in selected:
            meta = record.metadata
            body, issues = sanitize_html(render(record.body, mapping, media, warnings))
            warnings.extend(record.title + ": " + x for x in issues)
            excluded = [key for key in ("tags", "template") if key in meta]
            if record.portrait and any(key in record.portrait.attrs for key in ("alt", "title")):
                excluded.append("portrait description/caption")
            if excluded:
                warnings.append(record.title + ": намеренно исключены " + ", ".join(excluded))
            source_type = meta.get("type") or "note"
            kind = source_type if source_type in CARD_TYPES else "note"
            if kind != source_type:
                warnings.append(record.title + ": тип " + str(source_type) + " → note")
            values = {
                "mow_id": meta["id"],
                "mow_type": str(source_type),
                "summary": record.summary,
                "aliases": tuple(meta.get("aliases") or ()),
            }
            parent = mapping.get(meta.get("parent"), parent_id)
            portrait = None
            if record.portrait:
                value = record.portrait.attrs.get("src")
                try:
                    if record.portrait.attrs.get("data-asset"):
                        raise ValueError("data-asset требует manifest")
                    relative = media(value or "")
                    asset = next(a for a in assets if a.path == relative)
                    portrait = Portrait(asset.id)
                except (ValueError, OSError) as error:
                    warnings.append(record.title + ": портрет недоступен: " + str(error))
            cards.append(
                Card(
                    record.title,
                    id=mapping[meta["id"]],
                    parent_id=parent,
                    content=body,
                    portrait=portrait,
                    card_type=kind,
                    values=tuple(sorted(values.items())),
                )
            )
        order = {mapping[r.metadata["id"]]: r.metadata.get("order", 0) for r in selected}
        cards.sort(key=lambda c: (order[c.id], c.id))
        return PreparedImport(tuple(cards), tuple(imported), tuple(warnings))
    except Exception:
        cleanup_assets(store, imported)
        raise


@dataclass(frozen=True)
class PreparedImport:
    cards: tuple
    assets: tuple
    warnings: tuple


def cleanup_assets(store, assets):
    # Only files published by this uncommitted import; immutable existing files are never removed.
    for asset in assets:
        path = (store.root / asset.path).resolve()
        if path.is_relative_to((store.root / "assets").resolve()):
            path.unlink(missing_ok=True)


def apply_import(session, prepared):
    pending = list(prepared.cards)
    with session.entities.atomic():
        while pending:
            ready = [
                c
                for c in pending
                if c.parent_id is None or c.parent_id not in {p.id for p in pending}
            ]
            if not ready:
                raise ValueError("Цикл импортируемых карточек")
            for card in ready:
                session.entities.create(
                    "card", card.title, card.payload(), card.parent_id, id=card.id
                )
                pending.remove(card)
    for card in prepared.cards:
        session.card_created.emit(card.id)
    return tuple(c.id for c in prepared.cards)
