"""Explicit edits of canonical Markdown; positions use QTextCursor's UTF-16 units."""

import re
from dataclasses import dataclass
from urllib.parse import quote, urlsplit

from lodandsy.application.markdown_links import escape_markdown_label, internal_card_id


def utf16_length(text):
    return len(text.encode("utf-16-le")) // 2


def _index(text, offset):
    encoded = text.encode("utf-16-le")
    if type(offset) is not int or offset < 0 or offset * 2 > len(encoded):
        raise ValueError("Invalid text position")
    try:
        return len(encoded[:offset * 2].decode("utf-16-le"))
    except UnicodeDecodeError:
        raise ValueError("Position splits a Unicode character") from None


@dataclass(frozen=True)
class MarkdownChange:
    start: int
    end: int
    text: str
    anchor: int
    position: int


def _change(source, start, end, replacement, reverse=False, inner=None):
    if source[start:end] == replacement:
        return None
    first, last = inner or (0, len(replacement))
    origin = utf16_length(source[:start])
    anchor, position = origin + utf16_length(replacement[:first]), origin + utf16_length(
        replacement[:last])
    if reverse:
        anchor, position = position, anchor
    return MarkdownChange(origin, utf16_length(source[:end]), replacement, anchor, position)


def _lines(source, start, end):
    first = source.rfind("\n", 0, start) + 1
    stop = end - 1 if end > start and source[end - 1:end] == "\n" else end
    last = source.find("\n", stop)
    return first, len(source) if last == -1 else last


def _code_wrap(text):
    runs = re.findall(r"`+", text)
    marker = "`" * max(1, max(map(len, runs), default=0) + 1)
    pad = " " if text.startswith("`") or text.endswith("`") else ""
    return marker + pad + text + pad + marker


def _code_unwrap(text):
    match = re.fullmatch(r"(`+)(?!`)(.*?)(?<!`)\1", text)
    if not match:
        return None
    content = match[2]
    if content.startswith(" ") and content.endswith(" ") and content.strip():
        content = content[1:-1]
    return content


def format_markdown(source, anchor, position, command):
    a, b = _index(source, anchor), _index(source, position)
    start, end = min(a, b), max(a, b)
    reverse = a > b
    marks = {"bold": "**", "italic": "*", "strike": "~~"}
    if command in {*marks, "inline-code"}:
        if start == end:
            start, end = _lines(source, start, end)
        content = source[start:end]
        if not content:
            content = "код" if command == "inline-code" else "текст"
        marker = marks.get(command)
        if marker:
            before, after = source[:start], source[end:]
            surrounds = before.endswith(marker) and after.startswith(marker)
            if surrounds:
                prefix = before[:-len(marker)]
                escapes = len(prefix) - len(prefix.rstrip("\\"))
                surrounds = escapes % 2 == 0
            if marker == "*" and surrounds:
                left = re.search(r"\*+$", before)[0]
                right = re.match(r"\*+", after)[0]
                surrounds = len(left) == len(right) and len(left) % 2 == 1
            if surrounds:
                return _change(source, start - len(marker), end + len(marker), content, reverse)
            lines = content.split("\n")
            cores = [line.strip() for line in lines if line.strip()]
            def wrapped(value):
                return (len(value) >= 2 * len(marker) and value.startswith(marker)
                        and value.endswith(marker))
            remove = bool(cores) and all(wrapped(value) for value in cores)
            output = []
            for line in lines:
                core = line.strip()
                if not core:
                    output.append(line)
                    continue
                left, right = len(line) - len(line.lstrip()), len(line.rstrip())
                value = core[len(marker):-len(marker)] if remove else (
                    core if wrapped(core) else marker + core + marker)
                output.append(line[:left] + value + line[right:])
            replacement = "\n".join(output)
            inner = None
            if len(lines) == 1 and not remove and not wrapped(content.strip()):
                lead = len(content) - len(content.lstrip()) + len(marker)
                inner = (lead, lead + len(content.strip()))
            return _change(source, start, end, replacement, reverse, inner)
        # Code spans choose a delimiter longer than embedded runs; no HTML conversion.
        before = re.search(r"(`+)( ?)$", source[:start])
        after = re.match(r"( ?)(`+)", source[end:])
        if before and after and before[1] == after[2] and before[2] == after[1]:
            return _change(source, start - len(before[0]), end + len(after[0]), content, reverse)
        lines = content.split("\n")
        decoded = [_code_unwrap(line) if line.strip() else line for line in lines]
        remove = all(value is not None for value in decoded)
        replacement = "\n".join(decoded if remove else [
            _code_wrap(line) if line.strip() else line for line in lines])
        return _change(source, start, end, replacement, reverse)
    start, end = _lines(source, start, end)
    content = source[start:end]
    if command == "rule":
        return _change(source, end, end, "\n\n---\n", inner=(6, 6))
    if command == "code-block":
        lines = content.split("\n")
        first = re.match(r"^(`{3,}|~{3,})[^\n]*$", lines[0])
        last = re.fullmatch(r"(`{3,}|~{3,})[ \t]*", lines[-1])
        if (len(lines) >= 2 and first and last and first[1][0] == last[1][0]
                and len(last[1]) >= len(first[1])):
            replacement = "\n".join(lines[1:-1])
        else:
            fence = "`" * max(3, max(map(len, re.findall(r"`+", content)), default=0) + 1)
            replacement = fence + "\n" + content + "\n" + fence
            if not content:
                return _change(source, start, end, replacement, reverse,
                               (len(fence) + 1, len(fence) + 1))
        return _change(source, start, end, replacement, reverse)
    patterns = {"quote": r"^> ?", "bullet": r"^[-+*] ", "numbered": r"^\d+[.)] "}
    lines = content.split("\n")
    if command in {"normal", "h1", "h2", "h3"}:
        prefix = "" if command == "normal" else "#" * int(command[-1]) + " "
        if not content and prefix:
            return _change(source, start, end, prefix, inner=(len(prefix), len(prefix)))
        remove = bool(prefix) and all(not line.strip() or line.startswith(prefix) for line in lines)
        output = [re.sub(r"^ {0,3}#{1,6} +", "", line) for line in lines]
        replacement = "\n".join(("" if remove else prefix) + line if line.strip() else line
                                for line in output)
    elif command in patterns:
        if not content:
            prefix = {"quote": "> ", "bullet": "- ", "numbered": "1. "}[command]
            return _change(source, start, end, prefix, inner=(len(prefix), len(prefix)))
        pattern = patterns[command]
        remove = all(not line.strip() or re.match(pattern, line) for line in lines)
        output, number = [], 0
        for line in lines:
            if not line.strip():
                output.append(line)
                continue
            number += 1
            if remove:
                output.append(re.sub(pattern, "", line, count=1))
            elif re.match(pattern, line):
                output.append(line)
            else:
                prefix = {"quote": "> ", "bullet": "- ", "numbered": f"{number}. "}[command]
                output.append(prefix + line)
        replacement = "\n".join(output)
    else:
        raise ValueError("Unknown Markdown command")
    return _change(source, start, end, replacement, reverse)


def markdown_link(label, target):
    if any(ord(char) < 32 for char in target):
        raise ValueError("Ссылка содержит управляющие символы")
    parsed = urlsplit(target)
    if parsed.scheme == "lodandsy":
        internal_card_id(target)
    elif parsed.scheme in {"http", "https"} and parsed.hostname:
        pass
    elif not parsed.scheme and not parsed.path and parsed.fragment:
        pass
    else:
        raise ValueError("Допустимы HTTP/HTTPS, ссылка на Card или #якорь")
    label = escape_markdown_label(label)
    return f"[{label}](<{quote(target, safe=':/%?&=#@!$+;,~-_')}>)"
