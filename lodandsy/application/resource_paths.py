from pathlib import Path, PurePosixPath
from urllib.parse import unquote, urlsplit


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
