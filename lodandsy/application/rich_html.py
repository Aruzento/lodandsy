"""Bounded Qt HTML contract, independent of Qt and safe to use in the writer thread."""

import re
from html import escape
from html.parser import HTMLParser
from pathlib import PurePosixPath
from urllib.parse import unquote, urlsplit

from lodandsy.domain.card import DOCUMENT_HEADER, validate_card_id

MAX_HTML_BYTES = 2**21
MAX_NODES = 20_000
MAX_DEPTH = 64
FONTS = ("Segoe UI", "Georgia", "Consolas")
FONT_SIZES = (8, 9, 10, 11, 12, 14, 16, 18, 20, 24, 28, 32, 36, 48)
COLORS = ("#e8edf4", "#ceb075", "#9bc4fa", "#f19a9a", "#a8d5b0", "#aab7ca", "#000000")
HEADER = DOCUMENT_HEADER
TAGS = frozenset(
    "p div span a img br hr h1 h2 h3 h4 h5 h6 b strong i em u s del blockquote "
    "pre code ul ol li table tr td th thead tbody tfoot sub sup tt font".split()
)
DROP = frozenset(
    "script style head iframe object embed svg math form input button video audio "
    "link meta noscript".split()
)
VOID = frozenset({"img", "br", "hr", "link", "meta", "input", "embed"})


def internal_entity_id(value):
    parsed = urlsplit(value)
    if (
        parsed.scheme.lower() != "lodandsy"
        or parsed.netloc != "entity"
        or parsed.query
        or parsed.fragment
        or not parsed.path.startswith("/")
    ):
        raise ValueError("Некорректная или неподдерживаемая внутренняя ссылка")
    key = parsed.path[1:]
    validate_card_id(key)
    return key


def allowed_link(value):
    if not isinstance(value, str) or len(value) > 2048 or any(c in value for c in "\0\r\n"):
        return False
    try:
        p = urlsplit(value)
        if p.scheme.lower() == "lodandsy":
            internal_entity_id(value)
            return True
        return (
            p.scheme.lower() in {"http", "https"}
            and bool(p.hostname)
            or not p.scheme
            and not p.netloc
            and value.startswith("#")
        )
    except ValueError:
        return False


def allowed_asset(value):
    try:
        p = urlsplit(value)
        path = unquote(p.path, errors="strict")
    except ValueError, UnicodeError:
        return False
    parts = PurePosixPath(path).parts
    return (
        len(value) <= 1024
        and not p.scheme
        and not p.netloc
        and not p.query
        and not p.fragment
        and len(parts) >= 2
        and parts[0] == "assets"
        and ".." not in parts
        and not any(c in path for c in "\\:\0")
        and not PurePosixPath(path).is_absolute()
    )


def _style(name, value):
    if len(value) > 160 or re.search(r"url\s*\(|expression|[<>\\@]", value, re.I):
        return False
    if name == "font-family":
        return all(re.fullmatch(r"[\w -]{1,64}", part.strip(" '\"")) for part in value.split(","))
    if name == "font-size":
        if value in {"small", "medium", "large", "x-large", "xx-large"}:
            return True
        match = re.fullmatch(r"([0-9]+(?:\.[0-9]+)?)(pt|px)", value)
        return bool(match and 6 <= float(match[1]) <= 96)
    if name in {"color", "background-color", "border-color"}:
        return bool(re.fullmatch(r"#[0-9a-fA-F]{3,8}|black|white|transparent", value))
    options = {
        "font-weight": {"normal", "bold", *map(str, range(100, 1001, 100))},
        "font-style": {"normal", "italic", "oblique"},
        "text-decoration": {"none", "underline", "line-through", "underline line-through"},
        "text-align": {"left", "right", "center", "justify"},
        "white-space": {"pre", "pre-wrap", "normal"},
        "vertical-align": {"normal", "middle", "top", "bottom", "baseline", "sub", "super"},
        "border-collapse": {"collapse"},
        "border-style": {"none", "solid"},
        "-qt-paragraph-type": {"empty"},
        "-qt-table-type": {"root", "frame"},
    }
    if name in options:
        return value in options[name]
    if name in {"-qt-block-indent", "-qt-list-indent"}:
        return bool(re.fullmatch(r"[0-9]{1,2}", value) and int(value) <= 32)
    if name in {
        "margin-top",
        "margin-bottom",
        "margin-left",
        "margin-right",
        "text-indent",
        "padding",
        "border-width",
        "height",
        "line-height",
    }:
        match = re.fullmatch(r"(-?[0-9]+(?:\.[0-9]+)?)(px|pt|%)?", value)
        return bool(match and -256 <= float(match[1]) <= 256)
    return False


class RichSubset(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.output, self.warnings, self.stack = [], [], []
        self.suppressed, self.nodes = 0, 0

    def handle_starttag(self, tag, attrs):
        self.nodes += 1
        if self.nodes > MAX_NODES:
            raise ValueError("В документе слишком много элементов")
        if self.suppressed:
            if tag not in VOID:
                self.suppressed += 1
            return
        if tag in DROP:
            if tag not in {"head", "meta", "style"}:
                self.warnings.append(f"Удалён неподдерживаемый объект: {tag}")
            if tag not in VOID:
                self.suppressed = 1
            return
        if tag in {"html", "body"}:
            return
        if tag not in TAGS:
            self.warnings.append(f"Неподдерживаемый элемент: {tag}")
            return
        clean = {}
        for key, value in attrs:
            value = value or ""
            if key == "style":
                styles = {}
                for entry in value.split(";"):
                    if ":" not in entry:
                        continue
                    name, val = (p.strip() for p in entry.split(":", 1))
                    if _style(name, val):
                        styles[name] = val
                    else:
                        self.warnings.append(f"Удалено оформление: {name}")
                if styles:
                    clean[key] = ";".join(f"{k}:{v}" for k, v in sorted(styles.items()))
            elif tag == "a" and key == "href" and allowed_link(value):
                clean[key] = value
            elif tag == "img" and key == "src" and allowed_asset(value):
                clean[key] = value
            elif key in {"alt", "title"}:
                clean[key] = value[:1000]
            elif key in {"align", "valign", "dir", "type", "face", "color", "name"}:
                if re.fullmatch(r"[A-Za-z0-9# ,'_-]{1,100}", value):
                    clean[key] = value
            elif key == "class" and tag == "li" and value in {"checked", "unchecked"}:
                clean[key] = value
            elif key in {
                "width",
                "height",
                "colspan",
                "rowspan",
                "border",
                "cellpadding",
                "cellspacing",
                "start",
                "size",
            }:
                if re.fullmatch(r"[0-9]{1,4}%?", value) and int(value.rstrip("%")) <= 2048:
                    clean[key] = value
            else:
                self.warnings.append(f"Удалён атрибут: {key}")
        if tag == "img" and "src" not in clean:
            self.output.append("[Изображение заблокировано]")
            self.warnings.append("Изображения разрешены только из assets проекта")
            return
        if tag == "a":
            if "text-decoration:" not in clean.get("style", ""):
                clean["style"] = (clean.get("style", "") + ";text-decoration:none").lstrip(";")
        attributes = "".join(f' {k}="{escape(v, quote=True)}"' for k, v in sorted(clean.items()))
        self.output.append(f"<{tag}{attributes}>")
        if tag not in VOID:
            self.stack.append(tag)
            if len(self.stack) > MAX_DEPTH:
                raise ValueError("Слишком глубокая вложенность документа")

    def handle_endtag(self, tag):
        if self.suppressed:
            self.suppressed -= 1
        elif tag in self.stack:
            while self.stack:
                current = self.stack.pop()
                self.output.append(f"</{current}>")
                if current == tag:
                    break

    def handle_data(self, value):
        if not self.suppressed:
            self.output.append(escape(value))


def sanitize_html(source):
    if (
        not isinstance(source, str)
        or "\0" in source
        or len(source.encode("utf-8")) > MAX_HTML_BYTES
    ):
        raise ValueError("Документ повреждён или превышает 2 MiB")
    parser = RichSubset()
    parser.feed(source)
    parser.close()
    while parser.stack:
        parser.output.append(f"</{parser.stack.pop()}>")
    result = "<html>" + HEADER + "<body>" + "".join(parser.output) + "</body></html>"
    if len(result.encode("utf-8")) > MAX_HTML_BYTES:
        raise ValueError("Документ превышает 2 MiB")
    return result, tuple(dict.fromkeys(parser.warnings))


def html_text(source):
    class Text(HTMLParser):
        def __init__(self):
            super().__init__(convert_charrefs=True)
            self.parts = []

        def handle_data(self, data):
            self.parts.append(data)

    parser = Text()
    # Only canonical content is searched, not the immutable migration backup or head CSS.
    body = source.split("<body>", 1)[-1]
    parser.feed(body)
    return " ".join(parser.parts)


def validate_html(source):
    clean, warnings = sanitize_html(source)
    if warnings or clean != source:
        raise ValueError("Неподдерживаемое содержимое визуального документа")


def text_document(text):
    """Plain text insertion/import into the single document format; never parses Markdown."""
    return sanitize_html("<p>" + escape(text).replace("\n", "<br>") + "</p>")[0]
