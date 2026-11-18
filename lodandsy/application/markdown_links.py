import re
import string
from html.parser import HTMLParser
from pathlib import Path, PurePosixPath
from urllib.parse import quote, unquote, urlsplit

from lodandsy.domain.card import validate_card_id


def card_link(card_id: str, title: str) -> str:
    validate_card_id(card_id)
    label = re.sub(f"([{re.escape(string.punctuation)}])", r"\\\1", title)
    return f"[{label}](lodandsy://card/{card_id})"


def preview_markdown(source: str) -> str:
    """Normalize HTML image tags only in the derived preview, preserving code examples."""
    protected = []
    offsets = [0]
    fence = None
    for line in source.splitlines(keepends=True):
        start = offsets[-1]
        match = re.match(r" {0,3}(`{3,}|~{3,})(.*)", line)
        if fence is not None:
            protected.append((start, start + len(line)))
            if match and match[1][0] == fence[0] and len(match[1]) >= fence[1]:
                if not match[2].strip():
                    fence = None
        elif match:
            fence = (match[1][0], len(match[1]))
            protected.append((start, start + len(line)))
        elif line.startswith(("    ", "\t")):
            protected.append((start, start + len(line)))
        offsets.append(start + len(line))
    for match in re.finditer(r"(?<!`)(`+)(?!`)(.*?)\1(?!`)", source, re.DOTALL):
        protected.append(match.span())

    replacements = []

    class Images(HTMLParser):
        def handle_starttag(self, tag, attributes):
            if tag.lower() != "img":
                return
            line, column = self.getpos()
            position = offsets[line - 1] + column
            if any(start <= position < end for start, end in protected):
                return
            attributes = dict(attributes)
            src = attributes.get("src") or ""
            alt = attributes.get("alt") or "Изображение"
            alt = re.sub(f"([{re.escape(string.punctuation)}])", r"\\\1", alt)
            src = quote(src, safe=":/%?&=#@!$'()*+,;~-_")
            replacement = f"![{alt}](<{src}>)" if src else "[Изображение без источника]"
            replacements.append((position, len(self.get_starttag_text()), replacement))

    try:
        Images(convert_charrefs=True).feed(source)
    except (AssertionError, ValueError):
        # Malformed HTML stays editable; the resource loader still enforces the policy.
        return source
    for position, length, replacement in reversed(replacements):
        source = source[:position] + replacement + source[position + length:]
    return source


def internal_card_id(url: str) -> str:
    parsed = urlsplit(url)
    if parsed.scheme.lower() != "lodandsy" or parsed.netloc != "card":
        raise ValueError("Неподдерживаемый тип внутренней ссылки")
    if parsed.query or parsed.fragment or not parsed.path.startswith("/"):
        raise ValueError("Некорректная внутренняя ссылка")
    card_id = parsed.path[1:]
    try:
        validate_card_id(card_id)
    except ValueError:
        raise ValueError("Некорректный UUID карточки в ссылке") from None
    return card_id


def resolve_asset_image(project_root: Path | None, url: str) -> Path | None:
    if project_root is None:
        return None
    try:
        parsed = urlsplit(url)
        path = unquote(parsed.path, errors="strict")
    except (ValueError, UnicodeError):
        return None
    parts = PurePosixPath(path).parts
    if (parsed.scheme or parsed.netloc or parsed.query or parsed.fragment or "\\" in path
            or ":" in path or "\x00" in path or ".." in parts or len(parts) < 2
            or parts[0] != "assets" or PurePosixPath(path).is_absolute()):
        return None
    try:
        root = project_root.resolve()
        assets = (root / "assets").resolve()
        candidate = (root / path).resolve()
        if not assets.is_relative_to(root) or not candidate.is_relative_to(assets):
            return None
        return candidate if candidate.is_file() else None
    except (OSError, RuntimeError):
        return None
