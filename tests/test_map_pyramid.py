import json
import os
import struct
import subprocess
import sys
import sysconfig
import zlib
from threading import Event, Timer
from uuid import uuid4

import pytest
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QImage, QPainter

from lodandsy.application.map_pyramid import cache_directory, ensure_pyramid, read_manifest
from lodandsy.application.map_tiles import MapTiles
from lodandsy.application.sqlite_project_store import SQLiteProjectStore
from lodandsy.ui.map_widget import MapView

pytest_plugins = ["tests.project_fixture"]


def source_image(path, size=(600, 300), fmt="PNG"):
    image = QImage(*size, QImage.Format.Format_RGB32)
    image.fill(Qt.GlobalColor.darkCyan)
    assert image.save(str(path), fmt)
    return path


def test_worker_limits_rebuild_version_checksum_missing_tiles_and_cancel(tmp_path):
    store = SQLiteProjectStore.create(tmp_path / "Мир")
    asset = store.import_asset(source_image(tmp_path / "карта.png"))
    orphan = cache_directory(store.root, asset.sha256).parent / (".staging-" + "f" * 32)
    orphan.mkdir(parents=True)
    (orphan / "incomplete.png").write_bytes(b"interrupted")
    progress = []
    pyramid = ensure_pyramid(store.root, asset, progress=progress.append)
    assert (pyramid.width, pyramid.height) == (600, 300) and progress[-1] == 100
    assert not orphan.exists()
    manifest = pyramid.root / "manifest.json"
    data = json.loads(manifest.read_text())
    data["version"] = 999
    manifest.write_text(json.dumps(data))
    assert read_manifest(pyramid.root, asset.sha256) is None
    assert ensure_pyramid(store.root, asset).width == 600
    pyramid.tile_path(pyramid.max_level, 0, 0).unlink()
    assert read_manifest(pyramid.root, asset.sha256) is None
    assert ensure_pyramid(store.root, asset).width == 600
    cancelled = Event()
    cancelled.set()
    with pytest.raises(ValueError, match="отмен"):
        ensure_pyramid(store.root, asset, cancelled)
    assert not list(pyramid.root.parent.glob(".staging-*"))
    (store.root / asset.path).write_bytes(b"changed")
    with pytest.raises(ValueError, match="Контрольная сумма"):
        ensure_pyramid(store.root, asset)
    assert manifest.exists()  # Existing cache is not silently accepted for changed source.
    store.close()


@pytest.mark.parametrize(
    "fmt,extension", [("JPEG", "jpg"), ("WEBP", "webp"), ("BMP", "bmp"), ("GIF", "gif")]
)
def test_supported_formats_and_old_m1_bmp_gif(tmp_path, fmt, extension):
    path = tmp_path / f"image.{extension}"
    if fmt == "GIF":
        # Qt is a GIF reader; a fixed valid single-frame image exercises legacy projects.
        import base64

        path.write_bytes(
            base64.b64decode("R0lGODlhAQABAIAAAAAAAP///yH5BAEAAAAALAAAAAABAAEAAAIBRAA7")
        )
    else:
        source_image(path, fmt=fmt)
    store = SQLiteProjectStore.create(tmp_path / "world")
    asset = store.import_asset(path)
    pyramid = ensure_pyramid(store.root, asset)
    assert pyramid.width > 0 and pyramid.height > 0
    store.close()


def test_large_map_import_multiple_windows_tokens_and_reopen(project, qtbot, tmp_path):
    app, project = project
    project.create_project(tmp_path / "world")
    # Real encoded PNG, 25MP > former 16MP barrier, exercised by production child worker.
    source = source_image(tmp_path / "25mp.png", (5000, 5000))
    app.maps.import_map(source, "Large")
    qtbot.waitUntil(lambda: not app.maps.importing, timeout=30000)
    document = next(iter(app.maps_service.maps.values()))
    widget = app.maps.open_map(document.id).widget()
    qtbot.waitUntil(lambda: widget.view.map_width == 5000, timeout=30000)
    card = app.create_card("Place")
    app.maps_service.add_token(document.id, card.id, 1850, 3050)
    app.maps.import_map(source, "Second")
    qtbot.waitUntil(lambda: not app.maps.importing, timeout=30000)
    second = next(item for item in app.maps_service.maps.values() if item.id != document.id)
    assert second.asset_id == document.asset_id and len(project.assets) == 1
    other = app.maps.open_map(second.id).widget()
    qtbot.waitUntil(lambda: other.view.map_width == 5000, timeout=30000)
    assert widget.view._tokens[0].pos().x() == 1850
    assert app.maps.tiles.bytes <= app.maps.tiles.budget
    assert project.save_current()
    original = project.store.load()
    project._save_ui_state()
    project.create_project(tmp_path / "other", preserve_current=False)
    project.open_project(tmp_path / "world")
    qtbot.waitUntil(
        lambda: app.maps.open_map(document.id).widget().view.map_width == 5000, timeout=30000
    )
    assert project.store.load().maps == original.maps
    assert app.maps_service.get_map(document.id).tokens[0].x == 1850


def test_tile_renderer_lod_memory_and_corrupt_cache(qtbot, tmp_path):
    store = SQLiteProjectStore.create(tmp_path / "world")
    asset = store.import_asset(source_image(tmp_path / "a.png", (2100, 1000)))
    pyramid = ensure_pyramid(store.root, asset)
    tiles = MapTiles(None)
    view = MapView()
    qtbot.addWidget(view)
    view.resize(800, 600)
    view.set_pyramid(pyramid, tiles)
    view.show()
    qtbot.waitUntil(lambda: len(tiles.images) > 0)
    canvas = QImage(800, 600, QImage.Format.Format_RGB32)
    for zoom in (0.1, 0.5, 1, 3, 10):
        view.resetTransform()
        view.scale(zoom, zoom)
        painter = QPainter(canvas)
        view.render(painter)
        painter.end()
        assert view._background.last_tile_count <= 64
        assert len(tiles.pending) <= 64 and tiles.bytes <= tiles.budget
    qtbot.waitUntil(lambda: not tiles.pending)
    tiles.reset()
    path = pyramid.tile_path(pyramid.max_level, 0, 0)
    path.write_bytes(b"broken")
    errors = []
    tiles.failed.connect(errors.append)
    tiles.get(path)
    qtbot.waitUntil(lambda: bool(errors))
    assert not (pyramid.root / "manifest.json").exists()
    tiles.shutdown()
    store.close()


def test_source_or_cache_path_escape_is_rejected(tmp_path):
    with pytest.raises(ValueError):
        cache_directory(tmp_path, "../outside")


def test_decoder_memory_limit_is_enforced_in_child_process():
    environment = dict(os.environ)
    environment["PYTHONPATH"] = os.pathsep.join([os.getcwd(), sysconfig.get_path("purelib")])
    result = subprocess.run(
        [
            sys._base_executable,
            "-c",
            "from lodandsy.application.map_pyramid_worker import limit_worker; "
            "limit_worker(); bytearray(600 * 1024**2)",
        ],
        env=environment,
        capture_output=True,
        timeout=15,
    )
    assert result.returncode != 0 and b"MemoryError" in result.stderr


def test_cancel_running_decoder_leaves_only_complete_or_no_cache(tmp_path):
    store = SQLiteProjectStore.create(tmp_path / "world")
    asset = store.import_asset(source_image(tmp_path / "large.png", (6000, 4000)))
    cancel = Event()
    timer = Timer(0.25, cancel.set)
    timer.start()
    try:
        with pytest.raises(ValueError, match="отмен"):
            ensure_pyramid(store.root, asset, cancel)
        target = cache_directory(store.root, asset.sha256)
        assert not target.exists() or read_manifest(target, asset.sha256) is not None
        assert not list(target.parent.glob(".staging-*"))
        assert store.load().maps == ()
    finally:
        timer.cancel()
        store.close()


def test_resource_dangerous_png_header_is_rejected_without_publication(tmp_path):
    source = source_image(tmp_path / "huge-header.png", (2, 2))
    data = bytearray(source.read_bytes())
    data[16:24] = struct.pack(">II", 100000, 100000)
    data[29:33] = struct.pack(">I", zlib.crc32(data[12:29]))
    source.write_bytes(data)
    store = SQLiteProjectStore.create(tmp_path / "world")
    asset = store.import_asset(source)
    with pytest.raises(ValueError, match="Не удалось обработать"):
        ensure_pyramid(store.root, asset)
    assert store.load().maps == ()
    assert not cache_directory(store.root, asset.sha256).exists()
    store.close()


def test_sixteen_bit_png_display_cache_keeps_color_and_original_source(tmp_path):
    source = tmp_path / "16bit.png"
    image = QImage(32, 16, QImage.Format.Format_RGBA64)
    color = QColor("#80bc3f")
    image.fill(color)
    assert image.save(str(source))
    original = source.read_bytes()
    store = SQLiteProjectStore.create(tmp_path / "world")
    asset = store.import_asset(source)
    pyramid = ensure_pyramid(store.root, asset)
    tile = QImage(str(pyramid.tile_path(pyramid.max_level, 0, 0)))
    assert tile.pixelColor(0, 0) == color
    assert tile.depth() == 32
    assert (store.root / asset.path).read_bytes() == original
    store.close()


def test_large_aspect_map_camera_keeps_zoom_below_old_point_zero_one(qtbot):
    view = MapView()
    qtbot.addWidget(view)
    view.map_width, view.map_height = 1_000_000, 100
    view.restore_camera({"x": 0.4, "y": 0.5, "zoom": 0.0005})
    assert view.transform().m11() == 0.0005


def test_unloaded_map_camera_is_not_guessed_and_closed_preferences_survive(project):
    from lodandsy.application.workspace_state import capture_workspace

    app, _ = project
    document = app.maps_service.create_map("Pending background", str(uuid4()))
    widget = app.maps.open_map(document.id).widget()
    assert document.id not in capture_workspace(app)["maps"]
    camera = {"x": 0.4, "y": 0.6, "zoom": 0.0005}
    widget.restore_camera_state(camera)
    assert capture_workspace(app)["maps"][document.id] == camera
    app.window_manager.close_window(f"map:{document.id}")
    assert capture_workspace(app)["maps"][document.id] == camera


def test_loaded_map_camera_restore_does_not_mask_later_pan_zoom(project, qtbot, tmp_path):
    from lodandsy.application.workspace_state import capture_workspace, restore_workspace

    app, project = project
    project.create_project(tmp_path / "world")
    app.maps.import_map(source_image(tmp_path / "map.png"), "Map")
    qtbot.waitUntil(lambda: not app.maps.importing)
    document = next(iter(app.maps_service.maps.values()))
    widget = app.maps.open_map(document.id).widget()
    qtbot.waitUntil(lambda: widget.view._background is not None)
    data = capture_workspace(app)
    data["maps"][document.id] = {"x": 0.4, "y": 0.5, "zoom": 0.5}
    restore_workspace(app, data)
    assert widget.pending_camera is None
    widget.view.scale(1.5, 1.5)
    assert capture_workspace(app)["maps"][document.id]["zoom"] == 0.75


@pytest.mark.parametrize("registered", [True, False])
def test_backup_never_publishes_above_restore_budget(tmp_path, monkeypatch, registered):
    from lodandsy.application import sqlite_project_store as storage

    store = SQLiteProjectStore.create(tmp_path / "world")
    source = source_image(tmp_path / "image.png")
    if registered:
        asset = store.import_asset(source)
        store.save(storage.ProjectSnapshot((), 1, (asset,)))
    else:
        (store.root / "assets/unregistered.png").write_bytes(source.read_bytes())
    before = store.load()
    monkeypatch.setattr(storage, "MAX_BACKUP_BYTES", store.path.stat().st_size)
    destination = tmp_path / "previous.lodbackup"
    destination.write_bytes(b"preserve previous backup")
    with pytest.raises(storage.ProjectError, match="restore budget"):
        store.backup(destination)
    assert destination.read_bytes() == b"preserve previous backup"
    assert not list(tmp_path.glob("*.tmp"))
    assert store.load() == before
    store.close()
