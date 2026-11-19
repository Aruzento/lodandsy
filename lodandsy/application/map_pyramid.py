"""Rebuildable map cache and isolated decoder protocol. No world data lives here."""
import hashlib
import json
import math
import os
import re
import shutil
import subprocess
import sys
import sysconfig
import time
from dataclasses import dataclass
from pathlib import Path
from threading import Lock
from uuid import uuid4

TILE_SIZE = 256
CACHE_VERSION = 1
MAX_CACHE_BYTES = 4 * 1024**3
MAX_SOURCE_BYTES = 2 * 1024**3
MAX_TILES = 32768
WORKER_MEMORY_BYTES = 512 * 1024**2
_BUILD_LOCK = Lock()  # One heavy decoder process across all map windows.


def cache_estimate(width, height):
    """RGBA8 pyramid plus conservative filesystem metadata, including extreme aspect ratios."""
    maximum = (max(width, height) - 1).bit_length()
    count = sum(((width + 256 * 2**level - 1) // (256 * 2**level))
                * ((height + 256 * 2**level - 1) // (256 * 2**level))
                for level in range(maximum + 1))
    return count, (width * height * 16 + 2) // 3 + count * 4096


@dataclass(frozen=True)
class MapPyramid:
    root: Path
    width: int
    height: int
    source_sha256: str

    @property
    def max_level(self):
        return (max(self.width, self.height) - 1).bit_length()

    def tile_path(self, level, x, y):
        return self.root / "image_files" / str(level) / f"{x}_{y}.png"


def cache_directory(project_root, checksum):
    if re.fullmatch(r"[0-9a-f]{64}", checksum) is None:
        raise ValueError("Некорректная контрольная сумма карты")
    root = Path(project_root).resolve()
    cache = root / ".lodandsy-cache/maps-v1"
    if (cache.resolve() != cache or (cache / checksum).resolve() != cache / checksum):
        raise ValueError("Кеш карты находится вне проекта")
    return cache / checksum


def read_manifest(root, checksum):
    path = root / "manifest.json"
    if not path.is_file() or path.stat().st_size > 4096:
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if (data["version"] != CACHE_VERSION or data["sha256"] != checksum
                or data["tile_size"] != TILE_SIZE):
            return None
        width, height = data["width"], data["height"]
        if (type(width) is not int or type(height) is not int
                or width <= 0 or height <= 0 or width * height * 4 > MAX_CACHE_BYTES):
            return None
        count, estimate = cache_estimate(width, height)
        if count > MAX_TILES or estimate > MAX_CACHE_BYTES:
            return None
        pyramid = MapPyramid(root, width, height, checksum)
        for level in range(pyramid.max_level + 1):
            factor = 2 ** (pyramid.max_level - level)
            columns = math.ceil(math.ceil(width / factor) / TILE_SIZE)
            rows = math.ceil(math.ceil(height / factor) / TILE_SIZE)
            for y in range(rows):
                for x in range(columns):
                    tile = pyramid.tile_path(level, x, y)
                    if (not tile.resolve().is_relative_to(root.resolve())
                            or not tile.is_file() or not 0 < tile.stat().st_size <= 1024**2):
                        return None
        return pyramid
    except (OSError, ValueError, KeyError, TypeError):
        return None


def ensure_pyramid(project_root, asset, cancel=None, progress=lambda _percent: None):
    """Called off GUI. Child owns heavy decoding, parent can always cancel it."""
    while not _BUILD_LOCK.acquire(timeout=.1):
        if cancel is not None and cancel.is_set():
            raise ValueError("Загрузка карты отменена")
    try:
        return _ensure_pyramid(project_root, asset, cancel, progress)
    finally:
        _BUILD_LOCK.release()


def _ensure_pyramid(project_root, asset, cancel, progress):
    from lodandsy.application.resource_paths import resolve_asset_image

    source = resolve_asset_image(Path(project_root), asset.path)
    if source is None:
        raise ValueError("Исходное изображение отсутствует или находится вне assets")
    target = cache_directory(project_root, asset.sha256)
    target.parent.mkdir(parents=True, exist_ok=True)
    # The application holds the project's writer lease, and _BUILD_LOCK excludes
    # concurrent decoders. Recover at most 16 disposable stages left by a dead GUI.
    recovered = 0
    for abandoned in target.parent.glob(".staging-*"):
        if cancel is not None and cancel.is_set():
            raise ValueError("Импорт карты отменён")
        if (re.fullmatch(r"\.staging-[0-9a-f]{32}", abandoned.name)
                and abandoned.is_dir() and abandoned.resolve() == abandoned.absolute()
                and abandoned.resolve().parent == target.parent.resolve()):
            try:
                shutil.rmtree(abandoned.resolve())
            except OSError:
                continue
            recovered += 1
            if recovered == 16:
                break
    stage = target.with_name(f".staging-{uuid4().hex}")
    args = [str(source), str(target), str(stage), asset.sha256, str(os.getpid())]
    command = ([sys.executable, "--map-worker", *args] if getattr(sys, "frozen", False)
               else [sys.executable, "-m", "lodandsy.application.map_pyramid_worker", *args])
    environment = dict(os.environ, VIPS_CONCURRENCY="2")
    if os.name == "nt" and not getattr(sys, "frozen", False):
        # Windows venv python.exe is a redirector with a child process. Start the actual
        # interpreter so cancellation terminates the decoder, not just its redirector.
        command[0] = sys._base_executable
        environment["PYTHONPATH"] = os.pathsep.join([
            str(Path(__file__).resolve().parents[2]), sysconfig.get_path("purelib")])
    process = None
    start = time.monotonic()
    try:
        process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                   env=environment, creationflags=(
                                       subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0))
        last = -1
        while True:
            if cancel is not None and cancel.is_set():
                raise ValueError("Импорт карты отменён")
            if time.monotonic() - start > 900:
                raise ValueError("Обработка карты превысила 15 минут")
            try:
                output, errors = process.communicate(timeout=.1)
                finished = True
            except subprocess.TimeoutExpired as pending:
                output = pending.output or b""
                finished = False
            # Protocol is bounded: stage changes and at most 101 percentages.
            for line in output.splitlines():
                try:
                    value = json.loads(line).get("progress", -1)
                    if last < value <= 100:
                        progress(value)
                        last = value
                except (ValueError, TypeError):
                    pass
            if finished:
                break
        if process.returncode:
            message = "повреждённый файл или превышен лимит ресурсов"
            for line in errors.decode("utf-8", errors="replace").splitlines():
                try:
                    detail = json.loads(line).get("error")
                    if isinstance(detail, str):
                        message = detail[-2000:]
                except (ValueError, AttributeError):
                    pass
            raise ValueError("Не удалось обработать карту: " + message)
        pyramid = read_manifest(target, asset.sha256)
        if pyramid is None:
            raise ValueError("Пирамида карты не опубликована полностью")
        progress(100)
        return pyramid
    finally:
        if process is not None and process.poll() is None:
            process.kill()
            process.communicate()
        # Only this operation's disposable cache staging is removed, never assets.
        resolved = stage.resolve()
        if stage.exists() and resolved.parent == target.parent.resolve():
            shutil.rmtree(resolved)


def build_pyramid(source, target, stage, checksum, progress):
    """Worker-only. Source hash is verified even when a ready cache exists."""
    source, target, stage = Path(source), Path(target), Path(stage)
    root = target.parents[2].resolve()
    if (target.parent.name != "maps-v1" or target.parent.parent.name != ".lodandsy-cache"
            or target != cache_directory(root, checksum) or stage.parent != target.parent
            or re.fullmatch(r"\.staging-[0-9a-f]{32}", stage.name) is None
            or stage.resolve() != stage.absolute()
            or not source.resolve().is_relative_to((root / "assets").resolve())):
        raise ValueError("Некорректные пути worker: разрешены assets и производный кеш проекта")
    if source.stat().st_size > MAX_SOURCE_BYTES:
        raise ValueError("Исходный файл карты превышает бюджет 2 GiB")
    with source.open("rb") as stream:
        actual = hashlib.file_digest(stream, "sha256").hexdigest()
    if actual != checksum:
        raise ValueError("Контрольная сумма исходной карты не совпадает с проектом")
    progress(5)
    existing = read_manifest(target, checksum)
    if existing is not None:
        return existing
    stage.mkdir()
    with source.open("rb") as stream:
        signature = stream.read(16)
    import pyvips

    pyvips.cache_set_max_mem(32 * 1024**2)
    pyvips.cache_set_max(100)
    pyvips.cache_set_max_files(16)
    if signature.startswith(b"\x89PNG\r\n\x1a\n"):
        image = pyvips.Image.pngload(str(source), access="sequential", fail_on="warning")
    elif signature.startswith(b"\xff\xd8\xff"):
        image = pyvips.Image.jpegload(str(source), access="sequential", fail_on="warning")
    elif signature.startswith(b"RIFF") and signature[8:12] == b"WEBP":
        image = pyvips.Image.webpload(str(source), access="sequential", fail_on="warning")
    elif signature.startswith((b"BM", b"GIF87a", b"GIF89a")):
        # Preserve old M1 formats; their non-streaming Qt decoder remains bounded.
        from PySide6.QtGui import QImageReader

        reader = QImageReader(str(source))
        try:
            size = reader.size()
            if not size.isValid() or size.width() * size.height() > 16_000_000:
                raise ValueError("Большие BMP/GIF: преобразуйте файл в PNG/JPEG/WebP")
            raster = reader.read()
            if raster.isNull() or not raster.save(str(stage / "bounded-raster.png"), "PNG"):
                raise ValueError("Повреждённое изображение BMP/GIF")
        finally:
            if reader.device() is not None:
                reader.device().close()
        image = pyvips.Image.pngload(str(stage / "bounded-raster.png"), access="sequential")
    else:
        raise ValueError("Поддерживаются растровые PNG, JPEG, WebP, BMP и GIF")
    width, height = image.width, image.height
    count, estimate = cache_estimate(width, height)
    if (width <= 0 or height <= 0 or image.bands > 4 or estimate > MAX_CACHE_BYTES
            or count > MAX_TILES):
        raise ValueError("Карта превышает бюджет производного кеша 4 GiB")
    if shutil.disk_usage(stage).free < estimate + 64 * 1024**2:
        raise ValueError("Недостаточно свободного места для пирамиды карты")
    if image.interpretation == "cmyk":
        image = image.colourspace("srgb")
    if image.format == "ushort":
        # Remove the rgb16/grey16 interpretation too, or pngsave promotes uchar back to 16bit.
        image = image.cast("uchar", shift=True).copy(
            interpretation="b-w" if image.bands <= 2 else "srgb")
    image.set_progress(True)
    last = [5]
    def evaluated(_image, evaluation):
        percent = 5 + int(evaluation.percent * .85)
        if percent > last[0]:
            last[0] = percent
            progress(percent)
    image.signal_connect("eval", evaluated)
    image.dzsave(str(stage / "image"), tile_size=TILE_SIZE, overlap=0,
                 suffix=".png", keep="none")
    with source.open("rb") as stream:
        if hashlib.file_digest(stream, "sha256").hexdigest() != checksum:
            raise ValueError("Исходная карта изменилась во время обработки")
    (stage / "bounded-raster.png").unlink(missing_ok=True)
    manifest = {"version": CACHE_VERSION, "sha256": checksum, "tile_size": TILE_SIZE,
                "width": width, "height": height}
    with (stage / "manifest.json").open("x", encoding="utf-8") as stream:
        json.dump(manifest, stream)
        stream.flush()
        os.fsync(stream.fileno())
    if read_manifest(stage, checksum) is None:
        raise ValueError("Не все тайлы карты созданы")
    progress(95)
    invalid = None
    if target.exists():
        invalid = target.with_name(f".invalid-{uuid4().hex}")
        target.rename(invalid)
    os.replace(stage, target)
    if invalid is not None and invalid.resolve().parent == target.parent.resolve():
        if invalid.is_dir():
            # Rebuildable cache only, canonical assets stay untouched.
            shutil.rmtree(invalid.resolve())
        else:
            invalid.unlink()
    return MapPyramid(target, width, height, checksum)
